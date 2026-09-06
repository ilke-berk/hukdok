// Raporlama modülü — tipler + API fonksiyonları (G133).
// Backend sözleşmesi: backend/schemas_rapor.py + docs/plan/raporlama-plani-2026-09-06.md §2.
// Sözleşme DONDURULMUŞTUR: alan adları ve op listeleri plandaki JSON'la birebir; bir
// değişiklik gerekirse ÖNCE plan dosyası güncellenir. Şablon/koşu/chat FONKSİYONLARI
// G134/G135'te bu dosyaya eklenir — tipleri şimdiden burada (tek okuma turu).
import { apiClient } from "@/lib/api";

// ---------------------------------------------------------------------------
// §2.1 Rapor tanımı
// ---------------------------------------------------------------------------

/** Katalog kolon tipleri (§2.2). */
export type KolonTipi = "metin" | "liste" | "tarih" | "sayi" | "para" | "mantik";

/** Filtre operatörleri (§2.2 — tümü; tip başına izinli alt küme `OP_BY_TIP`). */
export type FiltreOp =
    | "eq" | "ne" | "contains" | "in"
    | "gte" | "lte" | "between"
    | "is_null" | "not_null";

/** `deger` biçimi: str / number / bool / list (in, between). `is_null`/`not_null` değer taşımaz. */
export type FiltreDeger = string | number | boolean | (string | number)[];

export interface Filtre {
    alan: string;
    op: FiltreOp;
    deger?: FiltreDeger;
}

export type SiralamaYonu = "asc" | "desc";

export interface Siralama {
    alan: string;
    yon: SiralamaYonu;
}

export interface RaporTanimi {
    veri_kaynagi: string;
    /** Sıralıdır; en az 1, en fazla 60, tekrarsız. */
    kolonlar: string[];
    /** En fazla 20. */
    filtreler: Filtre[];
    /** En fazla 3. */
    siralama: Siralama[];
}

// Plan §2.1 sınırları — istemci tarafı ön-doğrulama (sunucu 422 ile yine doğrular).
export const TANIM_LIMITLERI = {
    kolon_max: 60,
    filtre_max: 20,
    in_deger_max: 200,
    siralama_max: 3,
} as const;

// ---------------------------------------------------------------------------
// §2.4 Katalog + önizleme cevabı
// ---------------------------------------------------------------------------

export interface KatalogKolon {
    anahtar: string;
    etiket: string;
    tip: KolonTipi;
    filtrelenebilir: boolean;
    siralanabilir: boolean;
    turetilmis: boolean;
    /** Kapalı liste (`liste` tipi) seçenekleri; diğer tiplerde null. */
    secenekler: string[] | null;
}

export interface KatalogVeriKaynagi {
    anahtar: string;
    etiket: string;
    aciklama: string;
    varsayilan_kolonlar: string[];
    kolonlar: KatalogKolon[];
}

export interface KatalogLimitleri {
    onizleme_sayfa_boyu_max: number;
    export_max_satir: number;
}

export interface Katalog {
    veri_kaynaklari: KatalogVeriKaynagi[];
    limitler: KatalogLimitleri;
}

export interface OnizlemeKolonu {
    anahtar: string;
    etiket: string;
    tip: KolonTipi;
}

/** Hücre değeri: tarih ISO string, para/sayı JSON number, boş `null`. */
export type HucreDegeri = string | number | boolean | null;

export interface OnizlemeCevabi {
    kolonlar: OnizlemeKolonu[];
    satirlar: Record<string, HucreDegeri>[];
    toplam: number;
    sayfa: number;
    sayfa_boyu: number;
}

// ---------------------------------------------------------------------------
// §2.4 Şablon + koşu (fonksiyonlar G134'te)
// ---------------------------------------------------------------------------

export type RaporFormati = "xlsx" | "csv";
export type RaporKaynagi = "manuel" | "asistan";

export interface RaporSablonu {
    id: number;
    ad: string;
    aciklama: string | null;
    tanim: RaporTanimi;
    olusturan: string;
    paylasimli: boolean;
    created_at: string;
    updated_at: string;
}

export interface RaporSablonuGovdesi {
    ad: string;
    aciklama: string | null;
    tanim: RaporTanimi;
    paylasimli: boolean;
}

export interface RaporKosusu {
    id: number;
    sablon_id: number | null;
    sablon_adi: string | null;
    format: RaporFormati;
    kaynak: RaporKaynagi;
    veri_kaynagi: string;
    kolon_sayisi: number;
    satir_sayisi: number;
    kullanici: string;
    baslangic: string;
    sure_ms: number | null;
    dosya_adi: string;
    dosya_boyutu: number | null;
    sha256: string | null;
    dosya_mevcut: boolean;
    tanim: RaporTanimi;
}

export interface RaporKosuListesi {
    toplam: number;
    kosular: RaporKosusu[];
}

// ---------------------------------------------------------------------------
// §2.6 Asistan (fonksiyonlar G135'te)
// ---------------------------------------------------------------------------

export type AsistanRolu = "user" | "assistant";

export interface AsistanMesaji {
    rol: AsistanRolu;
    icerik: string;
}

export type AsistanEylemi = "onizle" | "indir_xlsx" | "indir_csv";

/** `/api/reports/chat` NDJSON olayları (analyzer._failed_event ile uyumlu; complete/failed SON olaydır). */
export type AsistanOlayi =
    | { status: "info"; message: string }
    | { status: "warning"; message: string }
    | { status: "complete"; cevap: string; tanim: RaporTanimi | null; eylem: AsistanEylemi | null }
    | { status: "failed"; error_ozet: string; error_kod: string };

// ---------------------------------------------------------------------------
// §2.2 tip ↔ op tablosu
// ---------------------------------------------------------------------------

/** Kolon tipi başına İZİNLİ operatörler — plan §2.2 tablosunun birebir kopyası. Aşılmaz. */
export const OP_BY_TIP: Record<KolonTipi, readonly FiltreOp[]> = {
    metin: ["eq", "ne", "contains", "in", "is_null", "not_null"],
    liste: ["eq", "ne", "in", "is_null", "not_null"],
    tarih: ["eq", "gte", "lte", "between", "is_null", "not_null"],
    sayi: ["eq", "gte", "lte", "between", "is_null", "not_null"],
    para: ["eq", "gte", "lte", "between", "is_null", "not_null"],
    mantik: ["eq", "is_null"],
};

export const OP_ETIKETLERI: Record<FiltreOp, string> = {
    eq: "eşittir",
    ne: "eşit değil",
    contains: "içerir",
    in: "şunlardan biri",
    gte: "≥ (en az)",
    lte: "≤ (en çok)",
    between: "aralıkta",
    is_null: "boş",
    not_null: "dolu",
};

export function opsForTip(tip: KolonTipi): readonly FiltreOp[] {
    return OP_BY_TIP[tip] ?? [];
}

/** `is_null`/`not_null` değer taşımaz. */
export function opDegerAlir(op: FiltreOp): boolean {
    return op !== "is_null" && op !== "not_null";
}

/** Op için değer şekli: tekil / liste (in) / ikili (between) / yok. */
export type DegerSekli = "yok" | "tekil" | "liste" | "ikili";

export function opDegerSekli(op: FiltreOp): DegerSekli {
    if (!opDegerAlir(op)) return "yok";
    if (op === "in") return "liste";
    if (op === "between") return "ikili";
    return "tekil";
}

/**
 * Op değiştiğinde önceki değerin yeni şekle uyarlanması — kullanıcı `eq`'ten
 * `between`'e geçince ilk kutu dolu kalır, tersinde ilk eleman korunur.
 */
export function degerSekleUyarla(op: FiltreOp, onceki: FiltreDeger | undefined): FiltreDeger | undefined {
    const sekil = opDegerSekli(op);
    if (sekil === "yok") return undefined;
    const ilk = Array.isArray(onceki) ? onceki[0] : onceki;
    if (sekil === "tekil") return ilk;
    if (sekil === "ikili") {
        const a = Array.isArray(onceki) ? onceki[0] : onceki;
        const b = Array.isArray(onceki) ? onceki[1] : undefined;
        return [ikiliUc(a), ikiliUc(b)];
    }
    // liste
    if (Array.isArray(onceki)) return onceki;
    return ilk === undefined || typeof ilk === "boolean" ? [] : [ilk];
}

/** `between` ucu: sayı number KALIR (§2.1 `[min, max]` JSON number), metin olduğu gibi; boş/mantık → "". */
function ikiliUc(v: FiltreDeger | undefined): string | number {
    if (v === undefined || v === null || typeof v === "boolean" || Array.isArray(v)) return "";
    return v;
}

/**
 * Bir filtre satırı gönderilebilir mi? (§2.1: `between` iki dolu uç, `in` en az 1 değer,
 * tekil op boş olamaz; `is_null`/`not_null` değer gerektirmez.) Tip uyumu op listesiyle sınanır.
 */
export function filtreTamamMi(f: Filtre, tip: KolonTipi | undefined): boolean {
    if (!f.alan || !tip) return false;
    if (!opsForTip(tip).includes(f.op)) return false;
    const sekil = opDegerSekli(f.op);
    if (sekil === "yok") return true;
    const d = f.deger;
    if (sekil === "ikili") {
        return Array.isArray(d) && d.length === 2 && d.every(x => x !== "" && x !== null && x !== undefined);
    }
    if (sekil === "liste") {
        return Array.isArray(d) && d.length >= 1 && d.length <= TANIM_LIMITLERI.in_deger_max;
    }
    if (Array.isArray(d)) return false;
    if (tip === "mantik") return typeof d === "boolean";
    return d !== undefined && d !== null && d !== "";
}

/**
 * Tanım Önizle düğmesine yeter mi? Kolon yoksa geçersiz; eksik filtre satırı ya da
 * alan seçilmemiş sıralama da geçersiz (sunucuya 422 yedirmemek için).
 */
export function tanimGecerliMi(tanim: RaporTanimi, kaynak: KatalogVeriKaynagi | undefined): boolean {
    if (!kaynak || tanim.veri_kaynagi !== kaynak.anahtar) return false;
    if (tanim.kolonlar.length < 1 || tanim.kolonlar.length > TANIM_LIMITLERI.kolon_max) return false;
    if (new Set(tanim.kolonlar).size !== tanim.kolonlar.length) return false;
    if (tanim.filtreler.length > TANIM_LIMITLERI.filtre_max) return false;
    if (tanim.siralama.length > TANIM_LIMITLERI.siralama_max) return false;
    const kolonOf = (anahtar: string) => kaynak.kolonlar.find(k => k.anahtar === anahtar);
    if (!tanim.kolonlar.every(k => kolonOf(k) !== undefined)) return false;
    // Türetilmiş kolon filtrelenemez/sıralanamaz (§2.2) — UI listelemez, kapı da geçirmez.
    if (!tanim.filtreler.every(f => {
        const k = kolonOf(f.alan);
        return k !== undefined && k.filtrelenebilir && !k.turetilmis && filtreTamamMi(f, k.tip);
    })) return false;
    return tanim.siralama.every(s => {
        const k = kolonOf(s.alan);
        return k !== undefined && k.siralanabilir && !k.turetilmis;
    });
}

// ---------------------------------------------------------------------------
// Hücre biçimlendirme (PreviewTable)
// ---------------------------------------------------------------------------

const TR_SAYI = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });
const TR_PARA = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** ISO `YYYY-MM-DD` ya da ISO datetime → `dd.MM.yyyy` (saat atılır; parse edilemezse ham metin). */
export function tarihBicimle(iso: string): string {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    if (!m) return iso;
    return `${m[3]}.${m[2]}.${m[1]}`;
}

/** Tabloda basılan metin: `null` → "—", tarih dd.MM.yyyy, para/sayı tr-TR, mantık Evet/Hayır. */
export function hucreBicimle(deger: HucreDegeri | undefined, tip: KolonTipi): string {
    if (deger === null || deger === undefined || deger === "") return "—";
    switch (tip) {
        case "tarih":
            return typeof deger === "string" ? tarihBicimle(deger) : String(deger);
        case "para":
            return typeof deger === "number" ? TR_PARA.format(deger) : String(deger);
        case "sayi":
            return typeof deger === "number" ? TR_SAYI.format(deger) : String(deger);
        case "mantik":
            if (typeof deger === "boolean") return deger ? "Evet" : "Hayır";
            return String(deger);
        default:
            return String(deger);
    }
}

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------

export const RAPOR_KATALOG_HATASI = "Rapor kataloğu yüklenemedi.";
export const RAPOR_ONIZLEME_HATASI = "Rapor önizlemesi alınamadı.";

/** Sunucunun rapor uçlarından dönen okunur hata; 422'de `alan`/`sebep` dolu. */
export class RaporApiError extends Error {
    readonly status: number;
    readonly alan?: string;
    readonly sebep?: string;

    constructor(message: string, status: number, alan?: string, sebep?: string) {
        super(message);
        this.name = "RaporApiError";
        this.status = status;
        this.alan = alan;
        this.sebep = sebep;
    }
}

interface DetayGovdesi {
    detail?: unknown;
}

function detayAl(govde: unknown): Record<string, unknown> | string | unknown[] | undefined {
    if (!govde || typeof govde !== "object") return undefined;
    const d = (govde as DetayGovdesi).detail;
    if (d === undefined || d === null) return undefined;
    return d as Record<string, unknown> | string | unknown[];
}

/**
 * Yanıtı okunur hataya çevirir. 422 sözleşmesi (§2.1): `detail: {alan, sebep}` → "…: <alan> — <sebep>".
 * FastAPI'nin standart liste biçimli 422'si (`detail: [{loc, msg}]`) de okunur metne çevrilir;
 * 413 satır limiti (§2.4) ve düz metin `detail` de ele alınır.
 */
export async function raporHatasiCevir(res: Response, varsayilan: string): Promise<RaporApiError> {
    let govde: unknown = null;
    try {
        govde = await res.json();
    } catch {
        govde = null;
    }
    const detay = detayAl(govde);

    if (detay && typeof detay === "object" && !Array.isArray(detay)) {
        const alan = typeof detay.alan === "string" ? detay.alan : undefined;
        const sebep = typeof detay.sebep === "string" ? detay.sebep : undefined;
        if (res.status === 413 && sebep === "satir_limiti") {
            const toplam = typeof detay.toplam === "number" ? detay.toplam.toLocaleString("tr-TR") : "?";
            const limit = typeof detay.limit === "number" ? detay.limit.toLocaleString("tr-TR") : "?";
            return new RaporApiError(
                `Rapor satır limitini aşıyor (${toplam} satır, limit ${limit}). Filtre daraltın.`,
                res.status, alan, sebep,
            );
        }
        if (alan || sebep) {
            const parca = [alan, sebep].filter(Boolean).join(" — ");
            return new RaporApiError(`Geçersiz rapor tanımı: ${parca}`, res.status, alan, sebep);
        }
    }
    if (Array.isArray(detay)) {
        const mesajlar = detay
            .map(d => (d && typeof d === "object" && typeof (d as { msg?: unknown }).msg === "string")
                ? (d as { msg: string }).msg
                : null)
            .filter((m): m is string => !!m);
        if (mesajlar.length > 0) {
            return new RaporApiError(`Geçersiz rapor tanımı: ${mesajlar.join("; ")}`, res.status);
        }
    }
    if (typeof detay === "string" && detay.trim()) {
        return new RaporApiError(detay, res.status);
    }
    return new RaporApiError(`${varsayilan} (HTTP ${res.status})`, res.status);
}

export async function getCatalog(): Promise<Katalog> {
    const res = await apiClient.fetch("/api/reports/catalog");
    if (!res.ok) throw await raporHatasiCevir(res, RAPOR_KATALOG_HATASI);
    return (await res.json()) as Katalog;
}

/** `POST /api/reports/preview` — gövde `{tanim, sayfa, sayfa_boyu}` (§2.4; sayfa_boyu ≤ 200). */
export async function previewReport(tanim: RaporTanimi, sayfa: number, sayfaBoyu: number): Promise<OnizlemeCevabi> {
    const res = await apiClient.fetch("/api/reports/preview", {
        method: "POST",
        body: JSON.stringify({ tanim, sayfa, sayfa_boyu: sayfaBoyu }),
    });
    if (!res.ok) throw await raporHatasiCevir(res, RAPOR_ONIZLEME_HATASI);
    return (await res.json()) as OnizlemeCevabi;
}
