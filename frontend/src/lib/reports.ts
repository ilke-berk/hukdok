// Raporlama modülü — tipler + API fonksiyonları (G133).
// Backend sözleşmesi: backend/schemas_rapor.py + docs/plan/raporlama-plani-2026-09-06.md §2.
// Sözleşme DONDURULMUŞTUR: alan adları ve op listeleri plandaki JSON'la birebir; bir
// değişiklik gerekirse ÖNCE plan dosyası güncellenir. Şablon/export/koşu fonksiyonları
// G134'te eklendi (dosyanın sonu); chat fonksiyonları G135'te eklenir — tipleri burada.
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

/**
 * `deger` biçimi: str / number / bool / list (in, between). `is_null`/`not_null` değer taşımaz.
 * §5.2: `in` listesinde `null` öğesi "(boş)" demektir (motor `IN (...) OR IS NULL`); diğer op'larda
 * `null` sunucuda 422 — `filtreTamamMi` `between` uçlarında reddeder.
 */
export type FiltreDeger = string | number | boolean | (string | number | null)[];

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

/** Filtre kontrol türü (§4.2; tipten türetilir, filtrelenemeyen kolonda null). */
export type FiltreKontrolu = "tarih_araligi" | "coklu_secim" | "metin_icerir" | "sayi_araligi" | "mantik";

/**
 * Seçenek listesinin kaynağı (§5.2): `sabit` = `liste` tipi kapalı küme; `veri` = metin kolonun DISTINCT
 * değerleri (sıklığa göre azalan — ilk 8 "Sık" bölümü); seçeneksiz kolonda null.
 */
export type SecenekKaynagi = "sabit" | "veri";

export interface KatalogKolon {
    anahtar: string;
    etiket: string;
    tip: KolonTipi;
    filtrelenebilir: boolean;
    siralanabilir: boolean;
    /** Türetilmiş kolon; §4.2'den beri filtrelenebilirlik kolon bazındadır (taraf kolonları EXISTS ile süzülür). */
    turetilmis: boolean;
    /** Kapalı liste seçenekleri (`liste` tipi ya da §5.2 veriden liste); diğerlerinde null. SIRASI katalogdan — istemci yeniden sıralamaz. */
    secenekler: string[] | null;
    /** Kaynağa göre kapalı grup kümesi (§4.2) — alan seçicideki başlık. */
    grup: string;
    /** Filtre kontrolü; filtrelenemeyen kolonda null. */
    kontrol: FiltreKontrolu | null;
    /** Kolon başına izinli op listesi (§4.3 şerhi); filtrelenemeyen kolonda `[]`. */
    oplar: FiltreOp[];
    /** `onerili` metin kolonlarının DISTINCT değerleri (≤300); yoksa null. */
    oneriler: string[] | null;
    /** Öneri listesi 300'ü aşıp kesildi. */
    oneri_kesik: boolean;
    /** §5.2 seçenek kaynağı; seçeneksiz kolonda null. */
    secenek_kaynagi: SecenekKaynagi | null;
    /** §5.2 ham kod → gösterim etiketi (client_type: Individual→"Gerçek kişi"); filtre değeri HAM gider. */
    secenek_etiketleri: Record<string, string> | null;
    /** §5.2 false = yalnız filtre (sanal `arama` kolonu): Kolonlar panelinde ve setlerde yok, `kolonlar`da 422. */
    secilebilir: boolean;
    /** Kolon açıklaması (arama kutusu placeholder'ı); sunucu vermezse yok. */
    aciklama?: string | null;
}

/** Hızlı filtre yuvasının sunumu (§5.2): kontrol seçimi `kontrol` + `sunum` ikilisinden (§5.3). */
export type HizliFiltreSunumu = "varsayilan" | "arama" | "cipler" | "var_yok" | "bos_anahtari";

/**
 * Şeritte hazır gelen filtre; `alternatifler` yalnız tarih aralığında alan değiştirici (§4.2);
 * `sunum`/`etiket` §5.2 (anahtar metni, ör. "Davası var", "E-postası yok").
 */
export interface HizliFiltre {
    alan: string;
    alternatifler: string[];
    sunum: HizliFiltreSunumu;
    etiket: string | null;
}

export interface KolonSeti {
    ad: string;
    kolonlar: string[];
}

export interface KatalogVeriKaynagi {
    anahtar: string;
    etiket: string;
    aciklama: string;
    varsayilan_kolonlar: string[];
    kolonlar: KatalogKolon[];
    /** Sıralı (§4.2). */
    hizli_filtreler: HizliFiltre[];
    kolon_setleri: KolonSeti[];
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
    // Listedeki `null` "(boş)" öğesidir — tekil/ikili şekle taşınmaz (o op'larda sunucu reddeder).
    const ilk = Array.isArray(onceki) ? onceki.find(x => x !== null) : onceki;
    if (sekil === "tekil") return ilk ?? undefined;
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
function ikiliUc(v: FiltreDeger | null | undefined): string | number {
    if (v === undefined || v === null || typeof v === "boolean" || Array.isArray(v)) return "";
    return v;
}

/**
 * Kolonun izinli op'ları: katalog `oplar` (§4.3 şerhi; taraf kolonlarında `eq` yok) — alan
 * yoksa/boşsa tip tablosuna düşülür. Filtrelenemeyen kolonda boş.
 */
export function kolonOplari(kolon: Pick<KatalogKolon, "tip" | "filtrelenebilir" | "oplar">): readonly FiltreOp[] {
    if (!kolon.filtrelenebilir) return [];
    return kolon.oplar && kolon.oplar.length > 0 ? kolon.oplar : opsForTip(kolon.tip);
}

/** Rapor kolonu olarak seçilebilir mi? (§5.2 `secilebilir`; alan yoksa — eski katalog — evet.) Katalogda olmayan kolon hayır. */
export function kolonSecilebilirMi(kolon: Pick<KatalogKolon, "secilebilir"> | undefined): boolean {
    if (!kolon) return false;
    return kolon.secilebilir !== false;
}

/** Kolonun seçenek etiketi (§5.2 `secenek_etiketleri` ∨ ham değer); `null` → "(boş)". Filtre değeri daima HAM. */
export const BOS_SECENEK_ETIKETI = "(boş)";

export function secenekEtiketi(kolon: Pick<KatalogKolon, "secenek_etiketleri">, deger: string | null): string {
    if (deger === null) return BOS_SECENEK_ETIKETI;
    return kolon.secenek_etiketleri?.[deger] ?? deger;
}

/**
 * Bir filtre satırı gönderilebilir mi? (§2.1: `between` iki dolu uç, `in` en az 1 değer,
 * tekil op boş olamaz; `is_null`/`not_null` değer gerektirmez.) Tip uyumu op listesiyle sınanır;
 * `oplar` verilirse (kolon başına izinli liste) tip tablosu yerine o kullanılır.
 */
export function filtreTamamMi(f: Filtre, tip: KolonTipi | undefined, oplar?: readonly FiltreOp[]): boolean {
    if (!f.alan || !tip) return false;
    if (!(oplar ?? opsForTip(tip)).includes(f.op)) return false;
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
 * Tanım otomatik önizlemeye yeter mi? Kolon yoksa geçersiz; eksik filtre ya da alan
 * seçilmemiş sıralama da geçersiz (sunucuya 422 yedirmemek için). Filtre/sıralama kapısı
 * motorla aynı: kolon bazında `filtrelenebilir`/`siralanabilir` + kolonun `oplar` listesi
 * (§4.2: türetilmiş taraf kolonları EXISTS ile filtrelenebilir; `turetilmis` tek başına engel değildir).
 */
export function tanimGecerliMi(tanim: RaporTanimi, kaynak: KatalogVeriKaynagi | undefined): boolean {
    if (!kaynak || tanim.veri_kaynagi !== kaynak.anahtar) return false;
    if (tanim.kolonlar.length < 1 || tanim.kolonlar.length > TANIM_LIMITLERI.kolon_max) return false;
    if (new Set(tanim.kolonlar).size !== tanim.kolonlar.length) return false;
    if (tanim.filtreler.length > TANIM_LIMITLERI.filtre_max) return false;
    if (tanim.siralama.length > TANIM_LIMITLERI.siralama_max) return false;
    const kolonOf = (anahtar: string) => kaynak.kolonlar.find(k => k.anahtar === anahtar);
    // §5.2 `secilebilir=false` (sanal arama kolonu) `kolonlar`da 422 — kapı da reddeder.
    if (!tanim.kolonlar.every(k => kolonSecilebilirMi(kolonOf(k)))) return false;
    if (!tanim.filtreler.every(f => {
        const k = kolonOf(f.alan);
        return k !== undefined && k.filtrelenebilir && filtreTamamMi(f, k.tip, kolonOplari(k));
    })) return false;
    return tanim.siralama.every(s => {
        const k = kolonOf(s.alan);
        return k !== undefined && k.siralanabilir;
    });
}

// ---------------------------------------------------------------------------
// §4.3 Kontrol ↔ op çevirisi (G138) — sunum katmanı; sunucu sözleşmesi DEĞİŞMEZ
// ---------------------------------------------------------------------------

/** Çoklu seçimde seçili değer: ham kod ya da `null` = "(boş)" (§5.2 `in` içinde `null`). */
export type Secim = string | null;

/** Var/yok anahtarının üç durumu (§5.3): hepsi = filtre yok, var = `gte 1`, yok = `eq 0`. */
export type VarYokDurumu = "hepsi" | "var" | "yok";

/** Şerit kontrol türleri: katalog `kontrol`ü + §5.3 sunum kontrolleri (`var_yok`, `bos_anahtari`). */
export type KontrolTuru = FiltreKontrolu | "var_yok" | "bos_anahtari";

/**
 * Şeritteki bir kontrolün durumu. Boş kontrol (değer girilmemiş) tanıma GİRMEZ
 * (`kontroldenFiltre` → null). "boş olanlar" yan kutucuğu YOK (§5.1 madde 8): çoklu seçimde
 * "(boş)" seçeneği (`secili` içinde `null`), `var_yok`/`bos_anahtari` sunum kontrolleri; tarih/sayı/
 * metin/mantık boşluğu çipin "…" menüsünden `is_null` (gelişmiş çip).
 * `gelismis`: §4.3 tablosuna çözülemeyen op (`ne`, `not_null`, tarih/sayıda `eq`/`is_null`, metinde `in`)
 * — filtre olduğu gibi korunur, çip olarak gösterilir, kaybolmaz.
 */
export type KontrolDurumu =
    | { kontrol: "tarih_araligi"; alan: string; baslangic: string; bitis: string }
    | { kontrol: "sayi_araligi"; alan: string; en_az: number | null; en_cok: number | null }
    | { kontrol: "coklu_secim"; alan: string; secili: Secim[] }
    | { kontrol: "metin_icerir"; alan: string; metin: string; tam: boolean }
    | { kontrol: "mantik"; alan: string; deger: boolean | null }
    | { kontrol: "var_yok"; alan: string; durum: VarYokDurumu }
    | { kontrol: "bos_anahtari"; alan: string; acik: boolean }
    | { kontrol: "gelismis"; alan: string; op: FiltreOp; deger?: FiltreDeger };

type KontrolKolonu = Pick<KatalogKolon, "anahtar" | "kontrol" | "tip" | "filtrelenebilir" | "oplar">;

/**
 * Kolon (+ hızlı filtre sunumu) için değer girilmemiş (boş) kontrol; filtrelenemeyen kolonda gelişmiş
 * çipe düşer. `var_yok` yalnız sayı aralığı kolonunda, `bos_anahtari` `is_null` izinli kolonda anlamlıdır;
 * uymuyorsa kolonun kendi kontrolü (katalog tutarsızlığına karşı).
 */
export function bosKontrol(kolon: KontrolKolonu, sunum: HizliFiltreSunumu = "varsayilan"): KontrolDurumu {
    const alan = kolon.anahtar;
    if (sunum === "var_yok" && kolon.kontrol === "sayi_araligi") return { kontrol: "var_yok", alan, durum: "hepsi" };
    if (sunum === "bos_anahtari" && kolon.kontrol && kolonOplari(kolon).includes("is_null")) {
        return { kontrol: "bos_anahtari", alan, acik: false };
    }
    switch (kolon.kontrol) {
        case "tarih_araligi": return { kontrol: "tarih_araligi", alan, baslangic: "", bitis: "" };
        case "sayi_araligi": return { kontrol: "sayi_araligi", alan, en_az: null, en_cok: null };
        case "coklu_secim": return { kontrol: "coklu_secim", alan, secili: [] };
        case "metin_icerir": return { kontrol: "metin_icerir", alan, metin: "", tam: false };
        case "mantik": return { kontrol: "mantik", alan, deger: null };
        default: return { kontrol: "gelismis", alan, op: kolonOplari(kolon)[0] ?? "eq" };
    }
}

/** Kontrol değer taşıyor mu (tanıma girecek mi)? */
export function kontrolDoluMu(d: KontrolDurumu): boolean {
    return kontroldenFiltre(d) !== null;
}

const sayiMi = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const metinMi = (v: unknown): v is string => typeof v === "string";
const secimMi = (v: unknown): v is Secim => v === null || metinMi(v);
const secimListesiMi = (v: unknown): v is Secim[] => Array.isArray(v) && v.every(secimMi);

/**
 * §4.3 + §5.3 tablosu: kontrol durumu → sunucu filtresi. Boş kontrol → null (tanıma girmez).
 * tarih/sayı: iki uç → `between`, yalnız başlangıç → `gte`, yalnız bitiş → `lte`;
 * çoklu seçim: 1 dolu → `eq`, n → `in` ("(boş)" = `null` öğesi), yalnız "(boş)" → `is_null`;
 * metin: `contains` (combobox seçiminde `tam` → `eq`); mantık: `eq true/false`;
 * var_yok: var → `gte 1`, yok → `eq 0`, hepsi → yok; bos_anahtari: açık → `is_null`.
 */
export function kontroldenFiltre(d: KontrolDurumu): Filtre | null {
    switch (d.kontrol) {
        case "gelismis":
            return d.deger === undefined ? { alan: d.alan, op: d.op } : { alan: d.alan, op: d.op, deger: d.deger };
        case "tarih_araligi": {
            const b = d.baslangic.trim();
            const e = d.bitis.trim();
            if (b && e) return { alan: d.alan, op: "between", deger: [b, e] };
            if (b) return { alan: d.alan, op: "gte", deger: b };
            if (e) return { alan: d.alan, op: "lte", deger: e };
            return null;
        }
        case "sayi_araligi": {
            const a = sayiMi(d.en_az) ? d.en_az : null;
            const c = sayiMi(d.en_cok) ? d.en_cok : null;
            if (a !== null && c !== null) return { alan: d.alan, op: "between", deger: [a, c] };
            if (a !== null) return { alan: d.alan, op: "gte", deger: a };
            if (c !== null) return { alan: d.alan, op: "lte", deger: c };
            return null;
        }
        case "coklu_secim": {
            if (d.secili.length === 0) return null;
            const dolu = d.secili.filter((s): s is string => s !== null);
            if (dolu.length === 0) return { alan: d.alan, op: "is_null" };
            if (d.secili.length === 1) return { alan: d.alan, op: "eq", deger: dolu[0] };
            return { alan: d.alan, op: "in", deger: [...d.secili] };
        }
        case "metin_icerir": {
            const m = d.metin.trim();
            if (!m) return null;
            return { alan: d.alan, op: d.tam ? "eq" : "contains", deger: m };
        }
        case "mantik":
            if (d.deger === null) return null;
            return { alan: d.alan, op: "eq", deger: d.deger };
        case "var_yok":
            if (d.durum === "var") return { alan: d.alan, op: "gte", deger: 1 };
            if (d.durum === "yok") return { alan: d.alan, op: "eq", deger: 0 };
            return null;
        case "bos_anahtari":
            return d.acik ? { alan: d.alan, op: "is_null" } : null;
    }
}

/**
 * Sunucu filtresi → kontrol durumu (şablon/asistan/koşu tanımı şeride çözülürken). `sunum` verilirse
 * önce sunum kontrolü denenir (`var_yok`: `gte 1`/`eq 0`; `bos_anahtari`: `is_null`), oturmazsa kolonun
 * kendi kontrolü. Çözülemeyen op ya da kontrolsüz kolon → `gelismis` (filtre kaybolmaz). Gidiş-dönüş:
 * `kontroldenFiltre(filtredenKontrol(f, k)) ≡ f` — istisnalar eş anlamlı: tek değerli `in` → `eq`,
 * `in [null]` → `is_null`.
 */
export function filtredenKontrol(f: Filtre, kolon: KontrolKolonu | undefined, sunum: HizliFiltreSunumu = "varsayilan"): KontrolDurumu {
    const gelismis: KontrolDurumu = f.deger === undefined
        ? { kontrol: "gelismis", alan: f.alan, op: f.op }
        : { kontrol: "gelismis", alan: f.alan, op: f.op, deger: f.deger };
    if (!kolon || !kolon.kontrol) return gelismis;
    const d = f.deger;
    if (sunum === "var_yok" || sunum === "bos_anahtari") {
        const sunumBos = bosKontrol(kolon, sunum);
        if (sunumBos.kontrol === "var_yok") {
            if (f.op === "gte" && d === 1) return { ...sunumBos, durum: "var" };
            if (f.op === "eq" && d === 0) return { ...sunumBos, durum: "yok" };
        }
        if (sunumBos.kontrol === "bos_anahtari" && f.op === "is_null") return { ...sunumBos, acik: true };
    }
    const bos = bosKontrol(kolon);
    switch (bos.kontrol) {
        case "tarih_araligi":
            if (f.op === "between" && Array.isArray(d) && d.length === 2 && metinMi(d[0]) && metinMi(d[1])) {
                return { ...bos, baslangic: d[0], bitis: d[1] };
            }
            if (f.op === "gte" && metinMi(d)) return { ...bos, baslangic: d };
            if (f.op === "lte" && metinMi(d)) return { ...bos, bitis: d };
            return gelismis;
        case "sayi_araligi":
            if (f.op === "between" && Array.isArray(d) && d.length === 2 && sayiMi(d[0]) && sayiMi(d[1])) {
                return { ...bos, en_az: d[0], en_cok: d[1] };
            }
            if (f.op === "gte" && sayiMi(d)) return { ...bos, en_az: d };
            if (f.op === "lte" && sayiMi(d)) return { ...bos, en_cok: d };
            return gelismis;
        case "coklu_secim":
            if (f.op === "eq" && metinMi(d)) return { ...bos, secili: [d] };
            if (f.op === "in" && secimListesiMi(d) && d.length > 0) return { ...bos, secili: [...d] };
            if (f.op === "is_null") return { ...bos, secili: [null] };
            return gelismis;
        case "metin_icerir":
            if (f.op === "contains" && metinMi(d)) return { ...bos, metin: d, tam: false };
            if (f.op === "eq" && metinMi(d)) return { ...bos, metin: d, tam: true };
            return gelismis;
        case "mantik":
            if (f.op === "eq" && typeof d === "boolean") return { ...bos, deger: d };
            return gelismis;
        default:
            return gelismis;
    }
}

/**
 * Kontrolün kendi ürettiği op'lar (§4.3/§5.3); "…" menüsü `oplar` ∖ bunları gelişmiş op olarak sunar.
 * `is_null` yalnız çoklu seçimde ("(boş)" seçeneği) ve boş anahtarında doğaldır; tarih/sayı/metin/mantıkta
 * "boş" çipin "…" menüsünden gelir (§5.1 madde 8).
 */
export const KONTROL_DOGAL_OPLARI: Record<KontrolTuru, readonly FiltreOp[]> = {
    tarih_araligi: ["between", "gte", "lte"],
    sayi_araligi: ["between", "gte", "lte"],
    coklu_secim: ["eq", "in", "is_null"],
    metin_icerir: ["contains", "eq"],
    mantik: ["eq"],
    var_yok: ["gte", "eq"],
    bos_anahtari: ["is_null"],
};

/**
 * Çipin "…" menüsündeki gelişmiş op'lar: kolonun izinli listesinde olup kontrolün doğal üretmedikleri.
 * `tur` verilmezse kolonun katalog kontrolü (sunum kontrollerinde çip kendi türünü verir).
 */
export function gelismisOplar(kolon: Pick<KatalogKolon, "tip" | "filtrelenebilir" | "oplar" | "kontrol">, tur?: KontrolTuru): FiltreOp[] {
    const etkin = tur ?? kolon.kontrol;
    const dogal = etkin ? KONTROL_DOGAL_OPLARI[etkin] : [];
    return kolonOplari(kolon).filter(op => !dogal.includes(op));
}

const TR_OZET_SAYI = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });

function degerOzeti(v: FiltreDeger | null | undefined, tip: KolonTipi, etiketler?: Record<string, string> | null): string {
    if (v === undefined) return "";
    if (v === null) return "boş";
    if (Array.isArray(v)) return v.map(x => degerOzeti(x, tip, etiketler)).join(", ");
    if (typeof v === "boolean") return v ? "Evet" : "Hayır";
    if (typeof v === "number") return TR_OZET_SAYI.format(v);
    if (tip === "tarih") return tarihBicimle(v);
    return etiketler?.[v] ?? v;
}

/**
 * Çipte basılan kısa özet: "Derdest, Karar" · "01.01.2025 – 31.12.2025" · "≥ 1.000" · "içerir \"x\"" · "boş".
 * `etiketler` (§5.2 `secenek_etiketleri`) verilirse ham kod yerine etiket; "(boş)" → "boş".
 */
export function kontrolOzeti(d: KontrolDurumu, tip: KolonTipi, etiketler?: Record<string, string> | null): string {
    switch (d.kontrol) {
        case "gelismis": {
            const deger = degerOzeti(d.deger, tip, etiketler);
            return deger ? `${OP_ETIKETLERI[d.op]} ${deger}` : OP_ETIKETLERI[d.op];
        }
        case "tarih_araligi": {
            const b = d.baslangic.trim();
            const e = d.bitis.trim();
            if (b && e) return `${tarihBicimle(b)} – ${tarihBicimle(e)}`;
            if (b) return `≥ ${tarihBicimle(b)}`;
            if (e) return `≤ ${tarihBicimle(e)}`;
            return "";
        }
        case "sayi_araligi": {
            const a = d.en_az;
            const c = d.en_cok;
            if (a !== null && c !== null) return `${TR_OZET_SAYI.format(a)} – ${TR_OZET_SAYI.format(c)}`;
            if (a !== null) return `≥ ${TR_OZET_SAYI.format(a)}`;
            if (c !== null) return `≤ ${TR_OZET_SAYI.format(c)}`;
            return "";
        }
        case "coklu_secim":
            return d.secili.map(s => degerOzeti(s, tip, etiketler)).join(", ");
        case "metin_icerir": {
            const m = d.metin.trim();
            if (!m) return "";
            return d.tam ? `= "${m}"` : `içerir "${m}"`;
        }
        case "mantik":
            return d.deger === null ? "" : d.deger ? "Evet" : "Hayır";
        case "var_yok":
            return d.durum === "hepsi" ? "" : d.durum;
        case "bos_anahtari":
            return d.acik ? "boş" : "";
    }
}

// ---------------------------------------------------------------------------
// §6.2 Favori (şablon) ad önerisi (G144)
// ---------------------------------------------------------------------------

/** Önerilen şablon adı en fazla bu kadar karakter (tekrar eki dahil). */
export const SABLON_AD_ONERI_MAX = 60;
/** Ada giren filtre özeti sayısı tavanı. */
const SABLON_AD_FILTRE_MAX = 2;
const AD_AYRAC = " · ";

const ilkHarfKucuk = (s: string) => (s ? s.charAt(0).toLocaleLowerCase("tr-TR") + s.slice(1) : s);
const yil = (iso: string) => /^(\d{4})-\d{2}-\d{2}/.exec(iso.trim())?.[1] ?? null;

/**
 * Tek filtrenin ada girecek kısa özeti; "" = ada girmez. Çip özetinden (`kontrolOzeti`) daha kısa:
 * çoklu seçim değerleri ("Doktor"), metin yalnız aranan ("Ankara"), tarih aralığı aynı yıldaysa yıl
 * ("2025"), var/yok ve boş anahtarı hızlı filtre etiketiyle ("davası var"); sayı/gelişmiş op kolon
 * etiketiyle ("Maddi ≥ 1.000"). Sanal arama kolonu (`secilebilir=false`) ve katalogda olmayan alan girmez.
 */
function filtreAdOzeti(f: Filtre, kaynak: KatalogVeriKaynagi): string {
    const kolon = kaynak.kolonlar.find(k => k.anahtar === f.alan);
    if (!kolon || kolon.secilebilir === false) return "";
    const hf = kaynak.hizli_filtreler.find(h => h.alan === f.alan);
    const d = filtredenKontrol(f, kolon, hf?.sunum ?? "varsayilan");
    const ozet = kontrolOzeti(d, kolon.tip, kolon.secenek_etiketleri);
    switch (d.kontrol) {
        case "coklu_secim":
            return ozet;
        case "metin_icerir":
            return d.metin.trim();
        case "tarih_araligi": {
            const b = yil(d.baslangic);
            const e = yil(d.bitis);
            if (b && e) return b === e ? b : `${b}–${e}`;
            return ozet ? `${kolon.etiket} ${ozet}` : "";
        }
        case "var_yok": {
            const kucuk = kolon.etiket.toLocaleLowerCase("tr-TR");
            if (d.durum === "hepsi") return "";
            if (d.durum === "var") return hf?.etiket ? ilkHarfKucuk(hf.etiket) : `${kucuk} var`;
            return `${kucuk} yok`;
        }
        case "bos_anahtari":
            if (!d.acik) return "";
            return hf?.etiket ? ilkHarfKucuk(hf.etiket) : `${kolon.etiket.toLocaleLowerCase("tr-TR")} boş`;
        case "mantik":
            if (d.deger === null) return "";
            return d.deger ? kolon.etiket : `${kolon.etiket} değil`;
        default:
            return ozet ? `${kolon.etiket} ${ozet}` : "";
    }
}

/**
 * Favori önerisi için ad (§6.2, saf): "<Kaynak etiketi> · <en fazla iki filtre özeti>"; filtre yoksa
 * "<Kaynak> · Temel". Toplam `SABLON_AD_ONERI_MAX` (60) karakteri aşmaz ("…" ile kısaltılır);
 * `mevcutAdlar` içinde aynı ad (büyük/küçük harf duyarsız) varsa " (2)", " (3)"… eki — ek dahil tavan korunur.
 */
export function sablonAdiOner(
    tanim: RaporTanimi,
    katalog: Pick<Katalog, "veri_kaynaklari">,
    mevcutAdlar: readonly string[] = [],
): string {
    const kaynak = katalog.veri_kaynaklari.find(k => k.anahtar === tanim.veri_kaynagi);
    const kaynakEtiketi = (kaynak?.etiket ?? tanim.veri_kaynagi).trim() || tanim.veri_kaynagi;
    const ozetler: string[] = [];
    if (kaynak) {
        for (const f of tanim.filtreler) {
            if (ozetler.length >= SABLON_AD_FILTRE_MAX) break;
            const o = filtreAdOzeti(f, kaynak).replace(/\s+/g, " ").trim();
            if (o && !ozetler.includes(o)) ozetler.push(o);
        }
    }
    const taban = [kaynakEtiketi, ...(ozetler.length > 0 ? ozetler : ["Temel"])].join(AD_AYRAC);

    const kisalt = (s: string, tavan: number) => {
        const t = Math.max(1, tavan);
        return s.length <= t ? s : (t === 1 ? "…" : s.slice(0, t - 1).trimEnd() + "…");
    };
    const anahtar = (s: string) => s.trim().toLocaleLowerCase("tr-TR");
    const mevcut = new Set(mevcutAdlar.map(anahtar));

    let aday = kisalt(taban, SABLON_AD_ONERI_MAX);
    for (let n = 2; mevcut.has(anahtar(aday)); n++) {
        const ek = ` (${n})`;
        aday = kisalt(taban, SABLON_AD_ONERI_MAX - ek.length) + ek;
    }
    return aday;
}

// ---------------------------------------------------------------------------
// Tarih kısayolları (şerit: bu yıl / geçen yıl / son 30 gün / son 12 ay)
// ---------------------------------------------------------------------------

export type TarihKisayolu = "bu_yil" | "gecen_yil" | "son_30_gun" | "son_12_ay";

export const TARIH_KISAYOL_ETIKETLERI: Record<TarihKisayolu, string> = {
    bu_yil: "Bu yıl",
    gecen_yil: "Geçen yıl",
    son_30_gun: "Son 30 gün",
    son_12_ay: "Son 12 ay",
};

/** Yerel tarih → `YYYY-MM-DD` (UTC kayması olmadan; `<input type=date>` biçimi). */
export function isoGun(d: Date): string {
    const iki = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${iki(d.getMonth() + 1)}-${iki(d.getDate())}`;
}

/**
 * Kısayol → [başlangıç, bitiş] ISO gün. "Bu yıl" 1 Ocak–bugün, "geçen yıl" tam yıl,
 * "son 30 gün" bugün dahil 30 gün, "son 12 ay" bir yıl önceki aynı günden bugüne.
 * `bugun` testte sabitlenir.
 */
export function tarihKisayolu(ad: TarihKisayolu, bugun: Date = new Date()): [string, string] {
    const y = bugun.getFullYear();
    switch (ad) {
        case "bu_yil":
            return [`${y}-01-01`, isoGun(bugun)];
        case "gecen_yil":
            return [`${y - 1}-01-01`, `${y - 1}-12-31`];
        case "son_30_gun": {
            const b = new Date(bugun.getFullYear(), bugun.getMonth(), bugun.getDate() - 29);
            return [isoGun(b), isoGun(bugun)];
        }
        case "son_12_ay": {
            const b = new Date(bugun.getFullYear() - 1, bugun.getMonth(), bugun.getDate());
            return [isoGun(b), isoGun(bugun)];
        }
    }
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

// ---------------------------------------------------------------------------
// §2.4 Şablonlar (G134)
// ---------------------------------------------------------------------------

export const RAPOR_SABLON_LISTE_HATASI = "Rapor şablonları yüklenemedi.";
export const RAPOR_SABLON_KAYIT_HATASI = "Şablon kaydedilemedi.";
export const RAPOR_SABLON_SILME_HATASI = "Şablon silinemedi.";
export const RAPOR_SABLON_YETKI_HATASI = "Bu şablon size ait değil; yalnız sahibi güncelleyebilir/silebilir.";

/** `GET /api/reports/templates` — kendi + paylaşımlılar (silinmişler hariç). */
export async function listTemplates(): Promise<RaporSablonu[]> {
    const res = await apiClient.fetch("/api/reports/templates");
    if (!res.ok) throw await raporHatasiCevir(res, RAPOR_SABLON_LISTE_HATASI);
    return (await res.json()) as RaporSablonu[];
}

/** `POST /api/reports/templates` — gövde `{ad, aciklama, tanim, paylasimli}` (§2.4), 201. */
export async function createTemplate(govde: RaporSablonuGovdesi): Promise<RaporSablonu> {
    const res = await apiClient.fetch("/api/reports/templates", {
        method: "POST",
        body: JSON.stringify(govde),
    });
    if (!res.ok) throw await raporHatasiCevir(res, RAPOR_SABLON_KAYIT_HATASI);
    return (await res.json()) as RaporSablonu;
}

/** `PUT /api/reports/templates/{id}` — TAM gövde (kısmi değil); başkasının şablonu → 403. */
export async function updateTemplate(id: number, govde: RaporSablonuGovdesi): Promise<RaporSablonu> {
    const res = await apiClient.fetch(`/api/reports/templates/${id}`, {
        method: "PUT",
        body: JSON.stringify(govde),
    });
    if (res.status === 403) throw new RaporApiError(RAPOR_SABLON_YETKI_HATASI, 403);
    if (!res.ok) throw await raporHatasiCevir(res, RAPOR_SABLON_KAYIT_HATASI);
    return (await res.json()) as RaporSablonu;
}

/** `DELETE /api/reports/templates/{id}` — 204 (soft); başkasının şablonu → 403. */
export async function deleteTemplate(id: number): Promise<void> {
    const res = await apiClient.fetch(`/api/reports/templates/${id}`, { method: "DELETE" });
    if (res.status === 403) throw new RaporApiError(RAPOR_SABLON_YETKI_HATASI, 403);
    if (!res.ok) throw await raporHatasiCevir(res, RAPOR_SABLON_SILME_HATASI);
}

/**
 * Şablonun sahibi mi? `olusturan` sunucuda küçük harfli e-postadır (`require_admin`
 * `preferred_username|upn|email` üçlüsünü lower'lar); istemci MSAL `username`'i aynı
 * biçime indirger. Sahip değilse Güncelle/Sil UI'da HİÇ gösterilmez (sunucu 403 zaten atar).
 */
export function sablonSahibiMi(sablon: Pick<RaporSablonu, "olusturan">, kullanici: string | undefined | null): boolean {
    if (!kullanici) return false;
    return sablon.olusturan.trim().toLowerCase() === kullanici.trim().toLowerCase();
}

// ---------------------------------------------------------------------------
// §2.4 Export + koşular (G134)
// ---------------------------------------------------------------------------

export const RAPOR_EXPORT_HATASI = "Rapor dosyası oluşturulamadı.";
export const RAPOR_KOSU_LISTE_HATASI = "İndirme geçmişi yüklenemedi.";
export const RAPOR_KOSU_INDIRME_HATASI = "Saklanan çıktı indirilemedi.";
export const RAPOR_KOSU_SURESI_DOLDU = "Çıktının saklama süresi dolmuş; raporu yeniden oluşturup indirin.";

export interface IndirilenDosya {
    blob: Blob;
    /** Sunucunun `Content-Disposition`'ından; istemci ad UYDURMAZ. */
    dosyaAdi: string;
}

export interface ExportSonucu extends IndirilenDosya {
    /** `X-Rapor-Kosu-Id` başlığı (İndirme geçmişi satırı); başlık yoksa null. */
    kosuId: number | null;
}

/**
 * `Content-Disposition: attachment; filename="..."` → dosya adı (`AdminPage.tsx` handleExport
 * deseni). RFC 5987 `filename*=UTF-8''...` varsa o yeğlenir (Türkçe ad güvenli).
 */
export function dispositionDosyaAdi(disposition: string | null | undefined): string | null {
    if (!disposition) return null;
    const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
    if (utf8) {
        try {
            return decodeURIComponent(utf8.trim());
        } catch {
            // düşer: düz filename'e bak
        }
    }
    const duz = /filename="?([^";]+)"?/i.exec(disposition)?.[1];
    return duz ? duz.trim() : null;
}

function yedekDosyaAdi(onek: string, format: RaporFormati): string {
    // Sunucu başlığı yoksa (proxy sıyırmış olabilir) uzantı en azından doğru olsun;
    // normal yolda BU AD HİÇ kullanılmaz (test: başlık kazanır).
    return `${onek}.${format}`;
}

/**
 * `POST /api/reports/export` — gövde `{tanim, format, sablon_id, kaynak}` (§2.4 birebir).
 * 413 `{"detail":{"sebep":"satir_limiti","toplam","limit"}}` → okunur `RaporApiError`
 * (`raporHatasiCevir`). Dosya adı `Content-Disposition`'dan, koşu id'si `X-Rapor-Kosu-Id`'den.
 */
export async function exportReport(
    tanim: RaporTanimi,
    format: RaporFormati,
    sablonId: number | null,
    kaynak: RaporKaynagi,
): Promise<ExportSonucu> {
    const res = await apiClient.fetch("/api/reports/export", {
        method: "POST",
        body: JSON.stringify({ tanim, format, sablon_id: sablonId, kaynak }),
    });
    if (!res.ok) throw await raporHatasiCevir(res, RAPOR_EXPORT_HATASI);
    const blob = await res.blob();
    const dosyaAdi = dispositionDosyaAdi(res.headers.get("Content-Disposition")) ?? yedekDosyaAdi("hukdok-rapor", format);
    const kosuHam = res.headers.get("X-Rapor-Kosu-Id");
    const kosuId = kosuHam !== null && /^\d+$/.test(kosuHam.trim()) ? Number(kosuHam.trim()) : null;
    return { blob, dosyaAdi, kosuId };
}

/** `GET /api/reports/runs?limit=&offset=` — tüm yöneticilerin koşuları, yeni→eski. */
export async function listRuns(limit: number, offset: number): Promise<RaporKosuListesi> {
    const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    const res = await apiClient.fetch(`/api/reports/runs?${q.toString()}`);
    if (!res.ok) throw await raporHatasiCevir(res, RAPOR_KOSU_LISTE_HATASI);
    return (await res.json()) as RaporKosuListesi;
}

/** `GET /api/reports/runs/{id}/download` — saklanan dosya; temizlenmişse 410 → okunur mesaj. */
export async function downloadRun(id: number): Promise<IndirilenDosya> {
    const res = await apiClient.fetch(`/api/reports/runs/${id}/download`);
    if (res.status === 410) throw new RaporApiError(RAPOR_KOSU_SURESI_DOLDU, 410);
    if (!res.ok) throw await raporHatasiCevir(res, RAPOR_KOSU_INDIRME_HATASI);
    const blob = await res.blob();
    const dosyaAdi = dispositionDosyaAdi(res.headers.get("Content-Disposition")) ?? yedekDosyaAdi(`hukdok-rapor-${id}`, "xlsx");
    return { blob, dosyaAdi };
}

/**
 * Blob'u tarayıcıya indirtir (`<a download>`; `AdminPage.tsx` handleExport kalıbı).
 * Ad daima sunucudan gelen `dosyaAdi`dir.
 */
export function dosyayiIndir(dosya: IndirilenDosya): void {
    const url = URL.createObjectURL(dosya.blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = dosya.dosyaAdi;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Biçimlendirme (RunsTable / TemplateBar)
// ---------------------------------------------------------------------------

const iki = (n: number) => String(n).padStart(2, "0");

/** ISO datetime → yerel `dd.MM.yyyy HH:mm`; parse edilemezse ham metin. */
export function tarihSaatBicimle(iso: string | null | undefined): string {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return `${iki(d.getDate())}.${iki(d.getMonth() + 1)}.${d.getFullYear()} ${iki(d.getHours())}:${iki(d.getMinutes())}`;
}

/** Bayt → "12,3 KB" / "1,2 MB" (tr-TR ondalık); null → "—". */
export function boyutBicimle(bayt: number | null | undefined): string {
    if (bayt === null || bayt === undefined || !Number.isFinite(bayt)) return "—";
    if (bayt < 1024) return `${bayt} B`;
    const kb = bayt / 1024;
    if (kb < 1024) return `${kb.toLocaleString("tr-TR", { maximumFractionDigits: 1 })} KB`;
    const mb = kb / 1024;
    return `${mb.toLocaleString("tr-TR", { maximumFractionDigits: 1 })} MB`;
}

export const FORMAT_ETIKETLERI: Record<RaporFormati, string> = { xlsx: "Excel", csv: "CSV" };
export const KAYNAK_ETIKETLERI: Record<RaporKaynagi, string> = { manuel: "Manuel", asistan: "Asistan" };
