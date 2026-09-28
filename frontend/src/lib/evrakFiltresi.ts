/**
 * Dava detayı "Evrak Listesi" belge türü süzgeci.
 *
 * Çipler davada GERÇEKTEN bulunan türlerden türetilir (boş tür çipi basılmaz).
 * "Kararlar" toplu çipi: tebliğ-süresi karar kümesi (`kararDoctype.ts`) + ara
 * karar — avukat davadaki tüm kararları tek tıkla görebilsin diye. Tür anahtarı
 * `normalizeDoctypeKey` ile `_` padding'inden arındırılır.
 */
import { isKararDoctype, normalizeDoctypeKey } from "@/lib/kararDoctype";

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
