// Rapor asistanı — `/api/reports/chat` NDJSON okuyucusu + anahtar kapısı okuyucusu (G135).
// Sözleşme: docs/plan/raporlama-plani-2026-09-06.md §2.6 (K6/K7/K8). Olaylar
// `info|warning|complete|failed`; `complete` ve `failed` SON olaydır (sonrası yok sayılır).
// NDJSON okuma kalıbı `analyzeDocument.ts:132-204` ile aynı: yarım satır buffer + TextDecoder.
// Sohbet geçmişi sunucuda SAKLANMAZ (K6): istemci `mesajlar` listesini taşır, en fazla 20.
import { apiClient } from "@/lib/api";
import {
    raporHatasiCevir,
    type AsistanEylemi, type AsistanMesaji, type AsistanOlayi, type RaporTanimi,
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
 */
const ORNEK_ISTEMLER_KAYNAGA_GORE: Record<string, readonly string[]> = {
    davalar: [
        "2025'te açılan derdest davaları avukat adıyla listele, Excel ver",
        "Derdest davaları ofis numarası, konu ve mahkeme kolonlarıyla listele",
        "Bu yıl açılan davaları açılış tarihine göre yeniden eskiye sırala",
    ],
    muvekkiller: [
        "Ankara'daki doktor müvekkillerin telefon ve e-postasını göster",
        "İstanbul'daki müvekkilleri ad ve şehir kolonlarıyla Excel olarak indir",
        "Birden fazla davası olan müvekkilleri dava sayısına göre sırala",
    ],
    belgeler: [
        "Son 30 günde işlenen tebligatları dava ofis numarasıyla listele",
        "Bu ay eklenen belgeleri türüne ve davasına göre CSV olarak indir",
        "Dönüşümü başarısız belgeleri dosya adı ve hata ile göster",
    ],
    foyler: [
        "Karar aşamasındaki föyleri dava ofis numarası ve konusuyla listele",
        "Bu yıl kapanan föyleri son durumuna göre sırala",
        "Föyleri dosya numarası ve aşamasıyla Excel olarak indir",
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
export function tanimOzeti(tanim: RaporTanimi): { kaynak: string; kolon: number; filtre: number; siralama: number } {
    return {
        kaynak: tanim.veri_kaynagi,
        kolon: tanim.kolonlar.length,
        filtre: tanim.filtreler.length,
        siralama: tanim.siralama.length,
    };
}

export const EYLEM_ETIKETLERI: Record<AsistanEylemi, string> = {
    onizle: "Önizleme",
    indir_xlsx: "Excel indirme",
    indir_csv: "CSV indirme",
};
