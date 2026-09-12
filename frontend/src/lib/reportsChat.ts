// Rapor asistanı — `/api/reports/chat` NDJSON okuyucusu + anahtar kapısı okuyucusu (G135).
// Sözleşme: docs/plan/raporlama-plani-2026-09-06.md §2.6 (K6/K7/K8). Olaylar
// `info|warning|complete|failed`; `complete` ve `failed` SON olaydır (sonrası yok sayılır).
// NDJSON okuma kalıbı `analyzeDocument.ts:132-204` ile aynı: yarım satır buffer + TextDecoder.
// Sohbet geçmişi sunucuda SAKLANMAZ (K6): istemci `mesajlar` listesini taşır, en fazla 20.
import { apiClient } from "@/lib/api";
import {
    OP_ETIKETLERI, gruplamaEtiketi, kolonOplari, olcumAnahtari, olcumEtiketi, ozetModu, raporHatasiCevir, secenekEtiketi,
    tanimNormalize, tarihBicimle,
    type AsistanEylemi, type AsistanMesaji, type AsistanOlayi, type Filtre, type Katalog, type KatalogKolon,
    type KatalogVeriKaynagi, type RaporTanimi,
} from "@/lib/reports";

/** K6: sunucuya giden geçmiş en fazla bu kadar mesaj (en yeni 20). */
export const ASISTAN_MESAJ_MAX = 20;

/** Admin anahtarı (K8, `SETTINGS_REGISTRY`); varsayılan KAPALI. */
export const RAPOR_ASISTANI_ANAHTARI = "rapor_asistani";

export const ASISTAN_HATASI = "Asistan yanıt veremedi.";
export const ASISTAN_AKIS_EKSIK = "Asistan akışı tamamlanmadı (yanıt eksik).";
export const ASISTAN_KAPALI_MESAJI =
    "Rapor asistanı yönetici panelinden kapalı. Manuel rapor oluşturucu çalışmaya devam eder.";
export const ASISTAN_YETKI_MESAJI = "Rapor asistanı yalnız yöneticilere açık.";

/** 409 — anahtar kapalı (K8). Çağıran paneli pasifleştirir. */
export class AsistanKapaliError extends Error {
    readonly kod = "asistan_kapali" as const;
    constructor() {
        super(ASISTAN_KAPALI_MESAJI);
        this.name = "AsistanKapaliError";
    }
}

/** 403 — yönetici değil. */
export class AsistanYetkiError extends Error {
    constructor() {
        super(ASISTAN_YETKI_MESAJI);
        this.name = "AsistanYetkiError";
    }
}

/**
 * `failed` olayı: nihai başarısızlık, `error_ozet` kullanıcı-dostu metin, `error_kod` etiket.
 * Etiket uzayı açık; tanınmayan etiket `analysis_error` gibi ele alınır (`errorKodIpucu`).
 */
export class AsistanFailedError extends Error {
    readonly kod: string;
    constructor(ozet: string, kod: string) {
        super(ozet);
        this.name = "AsistanFailedError";
        this.kod = kod;
    }
}

/** `error_kod` → kısa kullanıcı ipucu; bilinmeyen etiket `analysis_error` ipucuna düşer. */
const ERROR_KOD_IPUCU: Record<string, string> = {
    gemini_saturated: "Yapay zekâ servisi yoğun — biraz sonra tekrar deneyin.",
    gemini_blocked: "İstek yapay zekâ servisi tarafından engellendi — ifadeyi değiştirip tekrar deneyin.",
    gemini_truncated: "Yanıt yarım kaldı — isteği kısaltıp tekrar deneyin.",
    schema_invalid: "Asistan geçerli bir rapor tanımı üretemedi — isteği daha somut yazın (veri kaynağı, kolonlar, filtre).",
    analysis_error: "Beklenmeyen bir hata oldu — tekrar deneyin; sürerse yöneticiye bildirin.",
    // İstemci tarafı etiketleri (sunucu sözleşmesinde yok; 409/403 için panel kaydı).
    asistan_kapali: "Yönetici panelinde 'Rapor asistanı' anahtarı açılınca panel yeniden kullanılabilir.",
    yetki_yok: "Bu sayfa ve asistan yalnız yönetici hesaplarına açık.",
};

export function errorKodIpucu(kod: string | undefined | null): string {
    return ERROR_KOD_IPUCU[kod ?? ""] ?? ERROR_KOD_IPUCU.analysis_error;
}

export interface ChatCallbacks {
    /** `info` olayı — akış durumu satırı (canlı). */
    onInfo?: (message: string) => void;
    /** `warning` olayı — mesajın altında sarı şerit. */
    onWarning?: (message: string) => void;
}

export interface ChatSonucu {
    cevap: string;
    tanim: RaporTanimi | null;
    eylem: AsistanEylemi | null;
    /** Akış boyunca gelen `warning` mesajları (sırayla). */
    uyarilar: string[];
}

/** Geçmişi sunucu sınırına indirger: yalnız son `ASISTAN_MESAJ_MAX` mesaj gider (en yeniler). */
export function gecmisiKirp(mesajlar: AsistanMesaji[]): AsistanMesaji[] {
    return mesajlar.length > ASISTAN_MESAJ_MAX ? mesajlar.slice(-ASISTAN_MESAJ_MAX) : [...mesajlar];
}

/**
 * `POST /api/reports/chat` — gövde `{mesajlar, mevcut_tanim}` (§2.6 birebir), NDJSON akışı.
 * `complete` → sonuç; `failed` → `AsistanFailedError`; ikisi de gelmezse `ASISTAN_AKIS_EKSIK`.
 * `complete`/`failed` SON olaydır: sonraki satırlar okunmaz. 409 → `AsistanKapaliError`,
 * 403 → `AsistanYetkiError`, diğer hatalar `raporHatasiCevir` ile okunur mesaja çevrilir.
 */
export async function chatReport(
    mesajlar: AsistanMesaji[],
    mevcutTanim: RaporTanimi | null,
    callbacks: ChatCallbacks = {},
    signal?: AbortSignal,
): Promise<ChatSonucu> {
    const res = await apiClient.fetch("/api/reports/chat", {
        method: "POST",
        body: JSON.stringify({ mesajlar: gecmisiKirp(mesajlar), mevcut_tanim: mevcutTanim }),
        signal,
    });
    if (res.status === 409) throw new AsistanKapaliError();
    if (res.status === 403) throw new AsistanYetkiError();
    if (!res.ok) throw await raporHatasiCevir(res, ASISTAN_HATASI);
    if (!res.body) throw new Error("ReadableStream not supported");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const uyarilar: string[] = [];

    /** Bir olayı işler; `complete` sonucu döner, `failed` fırlatır, diğerleri null. */
    const olayIsle = (olay: AsistanOlayi): ChatSonucu | null => {
        switch (olay.status) {
            case "info":
                callbacks.onInfo?.(olay.message);
                return null;
            case "warning":
                uyarilar.push(olay.message);
                callbacks.onWarning?.(olay.message);
                return null;
            case "complete":
                return {
                    cevap: typeof olay.cevap === "string" ? olay.cevap : "",
                    tanim: olay.tanim ?? null,
                    eylem: olay.eylem ?? null,
                    uyarilar,
                };
            case "failed":
                throw new AsistanFailedError(
                    olay.error_ozet || "Asistan isteği tamamlanamadı.",
                    olay.error_kod || "analysis_error",
                );
            default:
                // Tanınmayan status: sözleşme dışı, yok sayılır (akış devam eder).
                return null;
        }
    };

    /** Satırları sırayla işler; nihai olay (`complete`) görülünce sonucu döner. */
    const satirlariIsle = (satirlar: string[]): ChatSonucu | null => {
        for (const satir of satirlar) {
            if (!satir.trim()) continue;
            let olay: AsistanOlayi;
            try {
                olay = JSON.parse(satir) as AsistanOlayi;
            } catch (e) {
                console.warn("Asistan akışında bozuk satır atlandı", e);
                continue;
            }
            const sonuc = olayIsle(olay);
            if (sonuc) return sonuc;
        }
        return null;
    };

    let sonuc: ChatSonucu | null = null;
    try {
        while (sonuc === null) {
            const { value, done } = await reader.read();
            if (value) {
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop() || ""; // yarım satır tamponda kalır
                sonuc = satirlariIsle(lines);
            }
            if (done) {
                // Akış kapandı: tamponda kalan son (yeni satırsız) satır da işlenir.
                if (sonuc === null && buffer.trim()) sonuc = satirlariIsle([buffer]);
                break;
            }
        }
    } finally {
        // Nihai olaydan (complete/failed) sonra okuma sürmez; bağlantıyı bırak.
        try {
            await reader.cancel();
        } catch {
            /* cancel desteklenmiyorsa (sahte okuyucu / kapalı akış) sorun değil */
        }
    }

    if (sonuc === null) throw new Error(ASISTAN_AKIS_EKSIK);
    return sonuc;
}

/**
 * Anahtar kapısı (K8): `GET /api/admin/settings` → `rapor_asistani` değeri. Okunamazsa
 * (ağ, 403, kayıt yok) **false** — panel gizli kalır, manuel akış etkilenmez; toast/log yok
 * (sayfanın katalog toast'ını gölgelemesin). Asıl kapı sunucuda: `/chat` 409 döner.
 */
export async function raporAsistaniAcikMi(): Promise<boolean> {
    try {
        const res = await apiClient.fetch("/api/admin/settings");
        if (!res.ok) return false;
        const data = (await res.json()) as { settings?: { key?: string; value?: unknown }[] } | null;
        const kayit = data?.settings?.find(s => s.key === RAPOR_ASISTANI_ANAHTARI);
        return kayit?.value === true;
    } catch {
        return false;
    }
}

/**
 * Örnek istemler kaynağa göre (G143): AssistantBar çipleri seçili veri kaynağının örneklerini gösterir
 * (tıklayınca girdiye yazılır, ikinci tık gönderir). Tanınmayan/boş kaynak → genel liste.
 * G174: kaynak başına üçüncü örnek "hangi … var" — yerel liste balonunu (`listeNiyeti`) keşfettirir; üçlü sayı korunur.
 */
const ORNEK_ISTEMLER_KAYNAGA_GORE: Record<string, readonly string[]> = {
    davalar: [
        "2025'te açılan derdest davaları avukat adıyla listele, Excel ver",
        "Derdest davaları ofis numarası, konu ve mahkeme kolonlarıyla listele",
        "Hangi mahkemeler var?",
    ],
    muvekkiller: [
        "Ankara'daki doktor müvekkillerin telefon ve e-postasını göster",
        "İstanbul'daki müvekkilleri ad ve şehir kolonlarıyla Excel olarak indir",
        "Hangi şehirler var?",
    ],
    belgeler: [
        "Son 30 günde işlenen tebligatları dava ofis numarasıyla listele",
        "Bu ay eklenen belgeleri türüne ve davasına göre CSV olarak indir",
        "Hangi belge türleri var?",
    ],
    foyler: [
        "Karar aşamasındaki föyleri dava ofis numarası ve konusuyla listele",
        "Bu yıl kapanan föyleri son durumuna göre sırala",
        "Hangi aşamalar var?",
    ],
};

const ORNEK_ISTEMLER_GENEL: readonly string[] = [
    "Derdest davaları ofis numarası, konu ve mahkeme kolonlarıyla listele",
    "İstanbul'daki müvekkilleri ad ve şehir kolonlarıyla Excel olarak indir",
    "Son 30 günde işlenen belgeleri dava ofis numarasıyla listele",
];

/** Seçili kaynağın örnek istemleri (3); kaynak tanınmıyor/boşsa genel liste. Sonuç değişmez (readonly). */
export function ornekIstemler(veriKaynagi: string | null | undefined): readonly string[] {
    return ORNEK_ISTEMLER_KAYNAGA_GORE[veriKaynagi ?? ""] ?? ORNEK_ISTEMLER_GENEL;
}

/** Panel mesaj listesi kaydı — sunucuya gitmez; `AsistanMesaji`'ne `sohbetGecmisi` çevirir. */
export interface SohbetKaydi {
    id: number;
    rol: "user" | "assistant";
    icerik: string;
    /** Asistan cevabındaki tanım (varsa). */
    tanim?: RaporTanimi | null;
    eylem?: AsistanEylemi | null;
    uyarilar?: string[];
    /** `failed` olayı: kırmızı kutu + ipucu; bu kayıt geçmişe GİTMEZ. */
    hata?: { ozet: string; kod: string };
    /** Tanım oluşturucuya uygulandı (düğme yerine rozet). */
    uygulandi?: boolean;
    /** G167: sunucuya gitmeden arayüzün ürettiği asistan satırı (yerel onay). Geçmişe girer. */
    yerel?: boolean;
    /** G174: kataloğa uymayan metin filtre değerleri (`degerEsle`) — kart bekler, aday çipleri gösterir. */
    sorunlar?: DegerSorunu[];
    /** G174: "hangi X'ler var" cevabı — bu kolonun değer listesi balonu (`DegerListesi`). */
    liste?: KatalogKolon;
    /** G174: liste niyeti birden çok kolona uydu — "Hangisi?" çipleri. */
    kolonAdaylari?: KatalogKolon[];
}

/**
 * Panel kayıtları → sunucu `mesajlar` listesi: hata kayıtları düşer (asistan üretmedi),
 * boş içerik düşer, son `ASISTAN_MESAJ_MAX` mesaj kalır.
 */
export function sohbetGecmisi(kayitlar: SohbetKaydi[]): AsistanMesaji[] {
    const mesajlar = kayitlar
        .filter(k => !k.hata && k.icerik.trim())
        .map(k => ({ rol: k.rol, icerik: k.icerik }));
    return gecmisiKirp(mesajlar);
}

/** Tanım özeti kartı için sayılar. */
export function tanimOzeti(tanim: RaporTanimi): {
    kaynak: string; kolon: number; filtre: number; siralama: number; gruplama: number; olcum: number; ozet: boolean;
} {
    return {
        kaynak: tanim.veri_kaynagi,
        kolon: tanim.kolonlar.length,
        filtre: tanim.filtreler.length,
        siralama: tanim.siralama.length,
        gruplama: tanim.gruplama?.length ?? 0,
        olcum: tanim.olcumler?.length ?? 0,
        ozet: ozetModu(tanim),
    };
}

export const EYLEM_ETIKETLERI: Record<AsistanEylemi, string> = {
    onizle: "Önizleme",
    indir_xlsx: "Excel indirme",
    indir_csv: "CSV indirme",
};

// ---------------------------------------------------------------------------
// G167 — teyit döngüsü: okunur tanım ayrıntısı + tanım eşitliği
// ---------------------------------------------------------------------------

export interface TanimAyrintisi {
    /** Veri kaynağı etiketi (katalogda yoksa anahtar). */
    kaynak: string;
    /** Kolon etiketleri, tanımdaki sırayla (katalogda yoksa anahtar). */
    kolonlar: string[];
    /** "Açılış Tarihi · aralıkta · 01.04.2026 – 31.08.2026" biçiminde satırlar. */
    filtreler: string[];
    /** "Açılış Tarihi ↓" biçiminde satırlar (özet modunda ölçüm anahtarı etiketiyle: "Kayıt sayısı ↓"). */
    siralama: string[];
    /** Özet modu (12.09): "Açılış Tarihi (ay)" biçiminde gruplama satırları; liste görünümünde boş. */
    gruplama: string[];
    /** Özet modu: "Kayıt sayısı", "Toplam Maddi Tazminat"; liste görünümünde boş. */
    olcumler: string[];
}

const BOS_DEGER = "(boş)";

function tekDegerMetni(kolon: KatalogKolon | undefined, d: string | number | boolean | null): string {
    if (d === null || d === undefined) return BOS_DEGER;
    if (typeof d === "boolean") return d ? "Evet" : "Hayır";
    if (kolon?.tip === "tarih" && typeof d === "string") return tarihBicimle(d);
    if (kolon?.secenek_etiketleri && typeof d === "string") return secenekEtiketi(kolon, d);
    return String(d);
}

function degerMetni(kolon: KatalogKolon | undefined, f: Filtre): string | null {
    if (f.op === "is_null" || f.op === "not_null") return null;
    const d = f.deger;
    if (d === undefined) return null;
    if (Array.isArray(d)) {
        const parcalar = d.map(x => tekDegerMetni(kolon, x));
        return f.op === "between" && parcalar.length === 2 ? `${parcalar[0]} – ${parcalar[1]}` : parcalar.join(", ");
    }
    return tekDegerMetni(kolon, d);
}

/**
 * Asistan tanımını kullanıcının teyit edebileceği okunur satırlara çevirir (G167): kolon/filtre/sıralama
 * anahtarları katalog ETİKETİYLE (bağlı kolon "Müvekkil kartı · Telefon" dahil), operatör `OP_ETIKETLERI`,
 * tarih dd.MM.yyyy, `between` "a – b", `in` virgüllü ve `null` "(boş)", mantık Evet/Hayır, seçenek etiketi
 * varsa o (ham değer değil). Katalogda olmayan anahtar olduğu gibi yazılır — kart hiçbir zaman boş kalmaz.
 * Saf fonksiyon; kart bileşeni yalnız bunu basar.
 */
export function tanimAyrintisi(tanim: RaporTanimi, katalog: Katalog | null): TanimAyrintisi {
    const kaynak = katalog?.veri_kaynaklari.find(v => v.anahtar === tanim.veri_kaynagi);
    const kolonBul = (anahtar: string) => kaynak?.kolonlar.find(k => k.anahtar === anahtar);
    const olcumler = tanim.olcumler ?? [];
    const gruplama = tanim.gruplama ?? [];
    // Özet modunda sıralama anahtarı ölçüm olabilir ("sayi", "toplam:x") → ölçüm etiketi; gruplama alanı → kırılımlı etiket
    const etiket = (anahtar: string) => {
        const o = olcumler.find(x => olcumAnahtari(x) === anahtar);
        if (o) return olcumEtiketi(o, o.alan ? kolonBul(o.alan) : undefined);
        const g = gruplama.find(x => x.alan === anahtar);
        if (g) return gruplamaEtiketi(g, kolonBul(g.alan));
        return kolonBul(anahtar)?.etiket ?? anahtar;
    };
    return {
        kaynak: kaynak?.etiket ?? tanim.veri_kaynagi,
        kolonlar: tanim.kolonlar.map(a => kolonBul(a)?.etiket ?? a),
        filtreler: tanim.filtreler.map(f => {
            const deger = degerMetni(kolonBul(f.alan), f);
            return [kolonBul(f.alan)?.etiket ?? f.alan, OP_ETIKETLERI[f.op], ...(deger === null ? [] : [deger])].join(" · ");
        }),
        siralama: tanim.siralama.map(s => `${etiket(s.alan)} ${s.yon === "desc" ? "↓" : "↑"}`),
        gruplama: gruplama.map(g => gruplamaEtiketi(g, kolonBul(g.alan))),
        olcumler: olcumler.map(o => olcumEtiketi(o, o.alan ? kolonBul(o.alan) : undefined)),
    };
}

// Kısa onay/indirme mesajları (G167, 10.09 prod dersi): "tamam" Gemini'ye gidince model tanımı ufak da
// olsa değiştirebiliyor → `tanimAyni` düşüyor, kart yeniden onay istiyordu. Onay niyeti ARAYÜZDE tanınır,
// bekleyen tanım LLM'siz uygulanır. Mesaj yalnız bu kelimelerden oluşuyorsa (dolgu kelimeler serbest) onaydır;
// içinde başka bir kelime varsa ("tamam ama telefonu ekle") düzeltmedir → Gemini'ye gider.
const ONAY_KELIMELERI = new Set([
    "tamam", "tamamdir", "evet", "onayla", "onayliyorum", "onaylandi", "onay", "uygula", "uygulayalim", "dogru",
    "olur", "ok", "okey", "peki", "goster", "onizle", "devam", "aynen", "kabul", "yap", "olustur", "listele", "getir",
    "hazirla", "calistir",
]);
const INDIRME_KELIMELERI = new Set(["indir", "indirelim", "indirebilirsin", "indirin", "indirme", "ver", "cikar", "kaydet"]);
const EXCEL_KELIMELERI = new Set(["excel", "xlsx", "exel"]);
const CSV_KELIMELERI = new Set(["csv"]);
const DOLGU_KELIMELERI = new Set([
    "ve", "hadi", "lutfen", "bunu", "simdi", "artik", "raporu", "rapor", "bu", "sekilde", "boyle", "olarak", "dosya",
    "dosyasi", "halinde", "formatinda", "o", "zaman", "haydi", "iyi", "guzel", "super", "harika", "tesekkurler",
    "sagol", "tanimi", "tanim", "listeyi", "liste", "onu", "sonucu", "sonuc",
]);

function kelimeler(metin: string): string[] {
    return metin
        .toLowerCase()
        .replace(/i̇/g, "i")
        .replace(/[çğıöşü]/g, c => ({ "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u" })[c] ?? c)
        .replace(/[^a-z0-9\s]/g, " ")
        .split(/\s+/)
        .filter(Boolean);
}

/**
 * Kullanıcı mesajı bekleyen tanımı ONAYLIYOR mu (G167): yalnız onay/indirme/dolgu kelimelerinden oluşan kısa
 * mesaj → `onizle` (onay) ya da `indir_xlsx` / `indir_csv` (indirme; format yoksa Excel). Başka kelime
 * geçiyorsa `null` (düzeltme/soru → Gemini). Bekleyen tanım yokken çağıran bunu kullanmaz.
 */
export function onayNiyeti(metin: string): AsistanEylemi | null {
    const k = kelimeler(metin);
    if (k.length === 0 || k.length > 8) return null;
    let onay = false, indir = false, excel = false, csv = false;
    for (const w of k) {
        if (ONAY_KELIMELERI.has(w)) onay = true;
        else if (INDIRME_KELIMELERI.has(w)) indir = true;
        else if (EXCEL_KELIMELERI.has(w)) excel = true;
        else if (CSV_KELIMELERI.has(w)) csv = true;
        else if (!DOLGU_KELIMELERI.has(w)) return null;
    }
    if (csv) return "indir_csv";
    if (excel) return "indir_xlsx";
    if (indir) return "indir_xlsx";
    return onay ? "onizle" : null;
}

// G168 — sohbetten şablon kaydı: "bunu haftalık rapor olarak kaydet" / "kaydet" / "favorilere ekle".
const KAYDET_FIIL = String.raw`(?:kaydet|kayıt et|kayit et|sakla|favorile|favorilere ekle|şablon(?:a|u)? (?:olarak )?(?:kaydet|ekle|yap)|sablon(?:a|u)? (?:olarak )?(?:kaydet|ekle|yap))`;
const KAYDET_ONEK = String.raw`(?:bunu|bu raporu|bu tanımı|bu tanimi|raporu|tanımı|tanimi|lütfen|lutfen|hadi)?\s*`;
const KAYDET_ADLI = new RegExp(String.raw`^${KAYDET_ONEK}["'“”]?(.+?)["'“”]?\s+(?:olarak|adıyla|adiyla|ismiyle|adında|adinda|diye)\s+${KAYDET_FIIL}\s*[.!]?$`, "iu");
const KAYDET_ADSIZ = new RegExp(String.raw`^${KAYDET_ONEK}${KAYDET_FIIL}\s*[.!]?$`, "iu");

/**
 * Kullanıcı mesajı bekleyen/mevcut tanımı ŞABLON olarak kaydetmek istiyor mu (G168): `{ ad }` (ad null =
 * öneri kullanılsın) ya da `null` (kaydetme isteği değil → Gemini). "telefonu kaydet" gibi başka kelimeli
 * mesaj eşleşmez.
 */
export function kaydetNiyeti(metin: string): { ad: string | null } | null {
    const m = metin.trim().replace(/\s+/g, " ");
    if (!m) return null;
    if (KAYDET_ADSIZ.test(m)) return { ad: null };          // "şablon olarak kaydet": "şablon" ad değil
    const adli = KAYDET_ADLI.exec(m);
    if (adli) {
        const ad = adli[1].trim().replace(/^(?:bunu|bu raporu|raporu)\s+/iu, "");
        return { ad: ad || null };
    }
    return null;
}

const TR_SAYI = new Intl.NumberFormat("tr-TR");

/**
 * Uygulama sonrası sonuç satırı (G168): önizleme toplamı sohbete yazılır; boş sonuçta filtreler sayılıp
 * gevşetme önerilir (asistan veriyi görmez, K6 — satır sayısı zaten önizlemeden gelir).
 */
export function sonucSatiri(tanim: RaporTanimi, toplam: number, katalog: Katalog | null): string {
    if (toplam > 0) return `${TR_SAYI.format(toplam)} kayıt bulundu.`;
    const filtreler = tanimAyrintisi(tanim, katalog).filtreler;
    if (filtreler.length === 0) return "Sonuç boş: bu kaynakta hiç kayıt yok.";
    return "Sonuç boş. Filtreleri gevşetebilirim — hangisini kaldırayım ya da değiştireyim? "
        + filtreler.map(f => `• ${f}`).join(" ")
        + ` (ör. ${gevsetmeOrnekleri(tanim, katalog).map(o => `"${o}"`).join(", ")})`;
}

/** Boş sonuçta örnek düzeltme istemleri, GERÇEK filtrelerden (2026-09-12: tarih filtresi yokken "tarihi bu yıla
 * genişlet" önerisi saçmaydı): tarih → "<etiket> aralığını genişlet", metin contains/eq → "<etiket> değerini
 * değiştir", liste/diğer → "<etiket> filtresini kaldır". Etiket küçük harfle, en çok iki örnek. */
export function gevsetmeOrnekleri(tanim: RaporTanimi, katalog: Katalog | null): string[] {
    const kaynak = katalog?.veri_kaynaklari.find(v => v.anahtar === tanim.veri_kaynagi);
    const ornekler: string[] = [];
    for (const f of tanim.filtreler) {
        const kolon = kaynak?.kolonlar.find(k => k.anahtar === f.alan);
        const ad = (kolon?.etiket ?? f.alan).toLocaleLowerCase("tr-TR");
        const tip = kolon?.tip;
        let ornek: string;
        if (tip === "tarih") ornek = `${ad} aralığını genişlet`;
        else if (tip === "metin" && (f.op === "contains" || f.op === "eq")) ornek = `${ad} değerini değiştir`;
        else ornek = `${ad} filtresini kaldır`;
        if (!ornekler.includes(ornek)) ornekler.push(ornek);
        if (ornekler.length === 2) break;
    }
    return ornekler;
}

/** İki tanım aynı mı (kaynak, kolon sırası, filtreler, sıralama) — "tamam/uygula/indir" cevabında asistan
 * bekleyen tanımı AYNEN döndürürse bu onaydır (G167). Alan sırası JSON sırasına bağlı kalmasın diye alan alan. */
export function tanimAyni(a: RaporTanimi | null | undefined, b: RaporTanimi | null | undefined): boolean {
    if (!a || !b) return false;
    const filtre = (f: Filtre) => JSON.stringify([f.alan, f.op, f.deger ?? null]);
    const na = tanimNormalize(a);
    const nb = tanimNormalize(b);
    return a.veri_kaynagi === b.veri_kaynagi
        && JSON.stringify(a.kolonlar) === JSON.stringify(b.kolonlar)
        && JSON.stringify(a.filtreler.map(filtre)) === JSON.stringify(b.filtreler.map(filtre))
        && JSON.stringify(a.siralama.map(s => [s.alan, s.yon])) === JSON.stringify(b.siralama.map(s => [s.alan, s.yon]))
        // Özet modu (12.09): boş/eksik listeler eşdeğer (`tanimNormalize` ikisini de düşürür)
        && JSON.stringify(na.gruplama ?? []) === JSON.stringify(nb.gruplama ?? [])
        && JSON.stringify(na.olcumler ?? []) === JSON.stringify(nb.olcumler ?? []);
}

// ---------------------------------------------------------------------------
// G174 — değer eşleme (katalog önerileri) + "hangi X'ler var" liste niyeti. Gemini'siz: öneriler zaten
// katalogla istemcide (K6 korunur — asistan veri görmez, eşleme ve liste arayüzde çözülür).
// ---------------------------------------------------------------------------

/** Karta gelen en çok aday çipi. */
export const DEGER_ADAY_MAX = 5;

/** Liste balonunda gösterilen en çok satır (katalog öneri tavanıyla aynı). */
export const DEGER_LISTESI_MAX = 300;

/**
 * Değer karşılaştırma anahtarı: `trim` + `toLocaleLowerCase("tr-TR")` + NFD birleşik işaret temizliği
 * (İ → i, "i̇" U+0307 → i, ş/ç/ğ/ö/ü → s/c/g/o/u) + iç boşluk tekilleştirme. `caseCardFields`/`party_check`
 * deseniyle aynı; eşleme, aday sıralaması ve liste araması bunu kullanır.
 */
export function degerAnahtari(s: string): string {
    return s
        .trim()
        .toLocaleLowerCase("tr-TR")
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .replace(/\s+/g, " ");
}

function anahtarKelimeleri(anahtar: string): string[] {
    return anahtar.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
}

export interface DegerSorunu {
    /** `tanim.filtreler` içindeki sıra. */
    indeks: number;
    alan: string;
    /** Ham (asistanın yazdığı) değer. */
    deger: string;
    /** En yakın öneriler (≤ `DEGER_ADAY_MAX`), katalogdaki yazımıyla. */
    adaylar: string[];
    /** Kolonun öneri listesi 300 tavanında kesik — aranan değer listede olmayabilir. */
    kesik: boolean;
}

export interface DegerEslemesi {
    temiz: boolean;
    sorunlar: DegerSorunu[];
}

/**
 * Aday sıralaması: normalize edilmiş kelime kesişimi sayısı (çok → az), sonra ortak önek uzunluğu, sonra
 * katalog sırası. Ne kesişimi ne de ≥2 karakter ortak öneki olan öneri aday değildir. En çok `max` aday.
 */
export function degerAdaylari(deger: string, oneriler: readonly string[], max = DEGER_ADAY_MAX): string[] {
    const n = degerAnahtari(deger);
    if (!n) return [];
    const kelimeler = new Set(anahtarKelimeleri(n));
    return oneriler
        .map((o, sira) => {
            const on = degerAnahtari(o);
            const kesisim = new Set(anahtarKelimeleri(on).filter(w => kelimeler.has(w))).size;
            let onek = 0;
            while (onek < n.length && onek < on.length && n[onek] === on[onek]) onek++;
            return { o, sira, kesisim, onek };
        })
        .filter(x => x.kesisim > 0 || x.onek >= 2)
        .sort((a, b) => b.kesisim - a.kesisim || b.onek - a.onek || a.sira - b.sira)
        .slice(0, max)
        .map(x => x.o);
}

/**
 * Asistan tanımındaki METİN filtre değerlerini katalog listelerine karşı dener (saf, Gemini'siz).
 * Yalnız `contains`/`eq` + string değer + kolonun bir listesi varsa bakılır: liste = `oneriler` (metin kolon,
 * ≤300 DISTINCT) yoksa `secenekler` (kapalı liste — veriden gelen "Uzmanlık Alanı" gibi ya da sabit kodlu; kodlu
 * listede `secenek_etiketleri` etiketi de kabul). 2026-09-12 dersi: "Kadın Doğum" ≠ "Kadın Hastalıkları ve Doğum"
 * yalnız `secenekler` taşıyan kolondaydı, eşleme atlıyordu → 0 satır. `contains` için normalize değer en az bir
 * öğenin ALT DİZESİ ise temiz ("Ankara" → "Ankara 3. Asliye Ticaret"), `eq` için birebir. `in`/`between`/tarih/
 * sayı/mantık filtreleri ve listesiz kolonlar daima temiz. Tutmayan satır `sorunlar`a en yakın ≤5 adayla düşer;
 * `temiz=false` → kart bekler (AssistantBar), aksi hâlde tanım hemen uygulanır.
 */
export function degerEsle(tanim: RaporTanimi, katalog: Katalog | null): DegerEslemesi {
    const kaynak = katalog?.veri_kaynaklari.find(v => v.anahtar === tanim.veri_kaynagi);
    const sorunlar: DegerSorunu[] = [];
    if (kaynak) {
        tanim.filtreler.forEach((f, indeks) => {
            if (f.op !== "contains" && f.op !== "eq") return;
            if (typeof f.deger !== "string") return;
            const kolon = kaynak.kolonlar.find(k => k.anahtar === f.alan);
            if (!kolon) return;
            const onerili = (kolon.oneriler?.length ?? 0) > 0;
            const liste = onerili ? kolon.oneriler! : (kolon.secenekler ?? []);
            if (liste.length === 0) return;
            const n = degerAnahtari(f.deger);
            if (!n) return;
            const etiketler = onerili ? null : kolon.secenek_etiketleri;
            const anahtarlar = (o: string) => [degerAnahtari(o), ...(etiketler?.[o] ? [degerAnahtari(etiketler[o])] : [])];
            const tutuyor = f.op === "contains"
                ? liste.some(o => anahtarlar(o).some(a => a.includes(n)))
                : liste.some(o => anahtarlar(o).includes(n));
            if (tutuyor) return;
            sorunlar.push({ indeks, alan: f.alan, deger: f.deger, adaylar: degerAdaylari(f.deger, liste), kesik: onerili && kolon.oneri_kesik === true });
        });
    }
    return { temiz: sorunlar.length === 0, sorunlar };
}

/**
 * Aday çipi tıklanınca: `indeks`teki filtrenin değeri katalog yazımıyla değişir; op kolonda `eq` izinliyse
 * `eq` (aday katalogdaki tam değer), yoksa `contains`; kolon bilinmiyorsa op olduğu gibi kalır. Yeni nesne döner.
 */
export function filtreDegeriDegistir(
    tanim: RaporTanimi, indeks: number, deger: string,
    kolon: Pick<KatalogKolon, "tip" | "filtrelenebilir" | "oplar"> | undefined,
): RaporTanimi {
    return {
        ...tanim,
        filtreler: tanim.filtreler.map((f, i) => {
            if (i !== indeks) return f;
            const op = kolon ? (kolonOplari(kolon).includes("eq") ? "eq" : "contains") : f.op;
            return { ...f, op, deger };
        }),
    };
}

// "hangi mahkemeler var" / "mahkeme listesi" / "durum seçenekleri neler" → liste niyeti. Kalıp tanıma
// `kelimeler()` (ASCII katlama) üstünde; kolon çözümü etiket + hızlı filtre etiketi + anahtar + kısa eşanlamlılar.
const LISTE_SORU_KELIMELERI = new Set(["hangi", "hangileri", "hangisi", "neler", "nelerdir", "nedir"]);
const LISTE_VARLIK_KELIMELERI = new Set(["var", "mevcut", "bulunuyor", "bulunur", "kayitli", "tanimli", "gecerli", "olabilir", "kullanilabilir"]);
const LISTE_AD_KELIMELERI = /^(?:liste(?:si|sini|sine|yi|ler)?|secenek(?:ler|leri|lerini)?|secenegi|deger(?:ler|leri|lerini)?|degeri)$/;
/** Bu fiiller geçiyorsa liste değil eylem/düzeltme isteğidir → Gemini. */
const LISTE_EYLEM_KELIMELERI = new Set([
    "kaldir", "cikar", "sil", "ekle", "listele", "sirala", "degistir", "guncelle", "indir", "kaydet", "uygula", "filtrele",
    "olustur", "yap", "koy",
]);
/** Kolon eşlemesine girmeyen dolgu/soru sözcükleri. */
const LISTE_DOLGU_KELIMELERI = new Set([
    ...LISTE_SORU_KELIMELERI, ...LISTE_VARLIK_KELIMELERI, "ne", "mi", "mu", "bana", "bize", "soyle", "soyler", "misin",
    "misiniz", "lutfen", "sistemde", "bizde", "elimizde", "kolon", "kolonu", "kolonunda", "kolonda", "alan", "alani",
    "alaninda", "filtre", "filtresi", "filtresinde", "icin", "icinde", "kac", "tane", "olan", "olarak", "tum", "butun",
    "acaba", "peki", "ve", "ile", "bir", "su", "bu", "o", "farkli", "mevcut", "kayitlar", "kayitlarda", "kayit", "veri",
    "veride", "tanimli", "toplam",
]);
const ES_ANLAM_GRUPLARI: readonly (readonly string[])[] = [
    ["il", "sehir", "city"],
    ["mahkeme", "court"],
    ["durum", "status"],
    ["avukat", "lawyer"],
    ["konu", "subject"],
    ["uzmanlik", "brans", "specialty"],
    ["tur", "turu", "type", "tip"],
    ["asama", "stage"],
    ["muvekkil", "client"],
    ["doktor", "doctor", "hekim"],
    ["hastane", "hospital"],
    ["kategori", "category"],
    ["rol", "role"],
    ["olay", "event"],
    ["belge", "document", "doc"],
    ["ilce", "district"],
];
const ES_ANLAM: Map<string, readonly string[]> = new Map(
    ES_ANLAM_GRUPLARI.flatMap(g => g.map(w => [w, g] as const)),
);

/** Sözcüğün eşleme biçimleri: kendisi, çoğul/iyelik eki düşmüş hâlleri ("iller" → "il", "ili" → "il") ve eşanlamlıları. */
function sozcukBicimleri(w: string): string[] {
    const tekil = w.replace(/(?:lerin|larin|leri|lari|ler|lar)$/, "");
    const iyelik = tekil.replace(/(?:si|su|i|u)$/, "");
    const temel = [w, tekil, iyelik].filter(b => b.length >= 2);
    return Array.from(new Set(temel.flatMap(b => [b, ...(ES_ANLAM.get(b) ?? [])])));
}

/** İki sözcük biçimi uyuşuyor mu: eşitlik, ya da ≥3 harfli ortak gövde (ek düşümü: "konusu" ~ "konu", "mahkemeyi" ~ "mahkeme"). */
function bicimUyar(a: string, b: string): boolean {
    if (a === b) return true;
    if (a.length < 3 || b.length < 3) return false;
    return a.startsWith(b) || b.startsWith(a);
}

const ANAHTAR_JENERIK = new Set(["sub", "type", "name", "id", "date", "no", "extra", "code", "at", "by", "is"]);

function kolonSozcukleri(kolon: KatalogKolon, kaynak: KatalogVeriKaynagi): string[] {
    // Bağlı kolon etiketi "Müvekkil kartı · Telefon": kolonun kendi adı son parça.
    const etiket = kolon.etiket.split("·").pop() ?? kolon.etiket;
    const hizli = kaynak.hizli_filtreler.find(h => h.alan === kolon.anahtar)?.etiket ?? "";
    const anahtar = (kolon.anahtar.split(".").pop() ?? kolon.anahtar).replace(/_/g, " ");
    // Anahtarın jenerik parçaları eşlemeye girmez: "sub_type" → "sub" ön-ekiyle "subject"e, "type" ile "tür"e
    // uyuyordu (2026-09-12: "hangi konular var" Uzmanlık Alanı'na düşüyordu).
    const anahtarKelimeleri = kelimeler(anahtar).filter(w => !ANAHTAR_JENERIK.has(w));
    const ham = [...kelimeler(etiket), ...kelimeler(hizli), ...anahtarKelimeleri]
        .filter(w => !LISTE_DOLGU_KELIMELERI.has(w) && !["adi", "ad", "no", "numarasi", "tarihi", "karti", "kart"].includes(w));
    return Array.from(new Set(ham.flatMap(sozcukBicimleri)));
}

/**
 * "Hangi X'ler var" liste niyeti (G174, Gemini'siz): mesaj bir liste sorusuysa ("hangi mahkemeler var",
 * "mahkeme listesi", "durum seçenekleri neler", "hangi iller var", "durum değerleri") kaynağın `oneriler`
 * ya da `secenekler` taşıyan filtrelenebilir kolonları arasında X'i arar: etiket, hızlı filtre etiketi,
 * anahtar ve kısa eşanlamlılar ("il" → şehir/city, "mahkeme" → court). Dönüş: eşleşen kolonlar (1 → liste
 * balonu; >1 → "Hangisi?" çipleri), liste sorusu değilse ya da hiç kolon uymuyorsa `null` (mesaj Gemini'ye
 * gider). Eylem fiilli mesajlar ("mahkemeyi kaldır", "listele davaları", "tamam") liste sorusu DEĞİLDİR.
 */
export function listeNiyeti(metin: string, kaynak: KatalogVeriKaynagi | null | undefined): KatalogKolon[] | null {
    if (!kaynak) return null;
    const k = kelimeler(metin);
    if (k.length === 0 || k.length > 12) return null;
    if (k.some(w => LISTE_EYLEM_KELIMELERI.has(w))) return null;
    const soru = k.some(w => LISTE_SORU_KELIMELERI.has(w));
    const ad = k.some(w => LISTE_AD_KELIMELERI.test(w));
    const varlik = k.some(w => LISTE_VARLIK_KELIMELERI.has(w));
    // Kalıplar: "hangi … (var)" · "… listesi" · "… seçenekleri/değerleri (neler)" · "… neler (var)"
    if (!(soru || ad || (varlik && k.length <= 4))) return null;

    const icerik = k.filter(w => !LISTE_DOLGU_KELIMELERI.has(w) && !LISTE_AD_KELIMELERI.test(w));
    if (icerik.length === 0) return null;
    const bicimler = icerik.map(sozcukBicimleri);

    const puanli = kaynak.kolonlar
        .filter(kol => kol.filtrelenebilir && ((kol.oneriler?.length ?? 0) > 0 || (kol.secenekler?.length ?? 0) > 0))
        .map(kol => {
            const sozcukler = kolonSozcukleri(kol, kaynak);
            const puan = bicimler.filter(bs => bs.some(b => sozcukler.some(s => bicimUyar(b, s)))).length;
            return { kol, puan };
        })
        .filter(x => x.puan > 0)
        .sort((a, b) => b.puan - a.puan);
    if (puanli.length === 0) return null;
    // En yüksek puanı paylaşanlar aday; tek kalırsa kesin.
    const tepe = puanli[0].puan;
    return puanli.filter(x => x.puan === tepe).map(x => x.kol);
}
