/**
 * Dava detayı "Evrak Listesi" belge türü süzgeci.
 *
 * Çipler davada GERÇEKTEN bulunan türlerden türetilir (boş tür çipi basılmaz).
 * "Kararlar" toplu çipi: tebliğ-süresi karar kümesi (`kararDoctype.ts`) + ara
 * karar — avukat davadaki tüm kararları tek tıkla görebilsin diye. Tür anahtarı
 * `normalizeDoctypeKey` ile `_` padding'inden arındırılır.
 */
import { isKararDoctype, normalizeDoctypeKey } from "@/lib/kararDoctype";
import { belgeYonu, taslakMi, type KartBelgesi } from "@/types/belge";

type YonDurumlu = Pick<KartBelgesi, "yon" | "kaynak" | "durum">;

export const FILTRE_TUMU = "__TUMU__";
export const FILTRE_KARARLAR = "__KARARLAR__";
const TURSUZ = "__TURSUZ__";

export interface EvrakTurlu {
    belge_turu_kodu?: string | null;
    belge_turu_adi?: string | null;
}

export interface EvrakFiltreCipi {
    anahtar: string;
    etiket: string;
    sayi: number;
}

export function isKararEvraki(doc: EvrakTurlu): boolean {
    return isKararDoctype(doc.belge_turu_kodu) || normalizeDoctypeKey(doc.belge_turu_kodu) === "ARAKRR";
}

export function evrakTurAnahtari(doc: EvrakTurlu): string {
    const kod = normalizeDoctypeKey(doc.belge_turu_kodu);
    if (kod) return kod;
    const ad = (doc.belge_turu_adi ?? "").trim();
    return ad ? `AD:${ad.toLocaleUpperCase("tr-TR")}` : TURSUZ;
}

/** Tümü + (varsa) Kararlar + türler; türler çoktan aza, eşitte Türkçe ada göre. */
export function evrakFiltreCipleri(docs: readonly EvrakTurlu[]): EvrakFiltreCipi[] {
    const turler = new Map<string, EvrakFiltreCipi>();
    let kararSayisi = 0;
    for (const d of docs) {
        if (isKararEvraki(d)) kararSayisi += 1;
        const anahtar = evrakTurAnahtari(d);
        const mevcut = turler.get(anahtar);
        if (mevcut) {
            mevcut.sayi += 1;
        } else {
            const etiket = (d.belge_turu_adi ?? "").trim() || (d.belge_turu_kodu ?? "").replace(/_+$/, "") || "Türü belirsiz";
            turler.set(anahtar, { anahtar, etiket, sayi: 1 });
        }
    }
    const sirali = [...turler.values()].sort(
        (a, b) => b.sayi - a.sayi || a.etiket.localeCompare(b.etiket, "tr-TR"),
    );
    const cipler: EvrakFiltreCipi[] = [{ anahtar: FILTRE_TUMU, etiket: "Tümü", sayi: docs.length }];
    if (kararSayisi > 0) cipler.push({ anahtar: FILTRE_KARARLAR, etiket: "Kararlar", sayi: kararSayisi });
    return cipler.concat(sirali);
}

export function evrakFiltreUygula<T extends EvrakTurlu>(docs: readonly T[], filtre: string): T[] {
    if (filtre === FILTRE_TUMU) return [...docs];
    if (filtre === FILTRE_KARARLAR) return docs.filter(isKararEvraki);
    return docs.filter(d => evrakTurAnahtari(d) === filtre);
}

// ── G283: Gelen · Taslak · Giden alt filtresi (plan §6 K11/K12) ──────────────
// Küme belgenin yön + durumundan türer: TASLAK (yönü ne olursa olsun) → "taslak"; KESIN + GIDEN → "giden"; gerisi
// "gelen". Eski yanıtta alanlar yoksa GELEN/KESIN varsayılır (`types/belge.ts`), yani "gelen". Tür çipleri alt filtreyle
// BİRLİKTE çalışır: önce küme, sonra tür. Seçim URL'de `?belgeler=giden|taslak` (varsayılan "gelen" yazılmaz).

export const BELGE_KUMELERI = ["gelen", "taslak", "giden"] as const;
export type BelgeKumesi = (typeof BELGE_KUMELERI)[number];
export const VARSAYILAN_BELGE_KUMESI: BelgeKumesi = "gelen";
export const BELGE_KUMESI_PARAM = "belgeler";

export const BELGE_KUMESI_ETIKETLERI: Record<BelgeKumesi, string> = {
    gelen: "Gelen",
    taslak: "Taslak",
    giden: "Giden",
};

export function belgeKumesi(doc: YonDurumlu): BelgeKumesi {
    if (taslakMi(doc)) return "taslak";
    return belgeYonu(doc) === "GIDEN" ? "giden" : "gelen";
}

export function belgeKumeSayilari(docs: readonly YonDurumlu[]): Record<BelgeKumesi, number> {
    const sayilar: Record<BelgeKumesi, number> = { gelen: 0, taslak: 0, giden: 0 };
    for (const d of docs) sayilar[belgeKumesi(d)] += 1;
    return sayilar;
}

export function belgeKumesiUygula<T extends YonDurumlu>(docs: readonly T[], kume: BelgeKumesi): T[] {
    return docs.filter(d => belgeKumesi(d) === kume);
}

/** URL parametresi → küme; tanınmayan / boş değer varsayılan ("gelen"). */
export function belgeKumesiCoz(param: string | null | undefined): BelgeKumesi {
    const v = (param ?? "").trim().toLocaleLowerCase("tr-TR");
    return (BELGE_KUMELERI as readonly string[]).includes(v) ? (v as BelgeKumesi) : VARSAYILAN_BELGE_KUMESI;
}
