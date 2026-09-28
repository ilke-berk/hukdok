import type { HukukbotKaynak } from "@/types/hukukbot";

/**
 * Metin içi atıflar → numaralı rozet (28.09). Model her iddianın sonuna "(Kaynak: 2026-07-29_BILIRKISI-RPR_…pdf)"
 * yazıyor; uzun ham dosya adları paragrafları bölüyor, aynı ad tekrar tekrar geçiyordu. Atıflar ilk geçiş
 * sırasıyla numaralanır ve metinde `[1](#atif-1)` bağlantısına çevrilir (`HukukbotMarkdown` rozet çizer);
 * kaynak listesi aynı numarayı kartında gösterir.
 *
 * Ayrıştırma hukbot `app/citation_check.py` ile BİREBİR (CITATION_RE, `atif_adlari`, `norm_ad`) — rozet
 * numarası ile kartın doğrulama rozeti aynı eşleşmeye dayansın. Kaynak listesi akışın SONUNDA gelir; numara
 * metinden türediği için akış sırasında da sabittir.
 */

/** hukbot CITATION_RE — "(Kaynak: X)", "(Kaynak Belge: X)", köşeli parantez/bold sarmalı. */
const ATIF_RE = /\s*\(Kaynak(?:\s+Belge)?:\s*\*{0,2}\[?([^)\]\n]+?)\]?\*{0,2}\)/g;
const PDF_ADI_RE = /[^\s,;/()[\]]+\.pdf/gi;

export const ATIF_HREF_ONEKI = "#atif-";

/** hukbot `atif_adlari`: tek parantezdeki adlar ("A.pdf, B.pdf" / "A.pdf / B.pdf" / "A.pdf ve B.pdf"). */
export function atifAdlari(grup: string): string[] {
  const adlar: string[] = [];
  for (const ham of grup.split(/[,;/]|\sve\s/)) {
    const parca = ham.trim();
    if (!parca) continue;
    if (!parca.toLowerCase().endsWith(".pdf") || (parca.match(/ /g)?.length ?? 0) >= 3) {
      const gomulu = parca.match(PDF_ADI_RE);
      if (gomulu) {
        adlar.push(...gomulu);
        continue;
      }
    }
    adlar.push(parca);
  }
  return adlar;
}

/** hukbot `norm_ad` (+ uzantısız anılan adı da eşlemek için `.pdf` atılır). */
export function adAnahtari(ad: string): string {
  return (ad ?? "").trim().toLowerCase().replace(/ /g, "_").replace(/\.pdf$/, "");
}

export type AtifliMetin = {
  /** Atıfları `[n](#atif-n)` bağlantısına çevrilmiş markdown. */
  metin: string;
  /** Numara sırasıyla atıf adları (tekilsiz): `adlar[n-1]` n numaralı atıf. */
  adlar: string[];
};

/** Metindeki atıfları numaralar; aynı belge her geçişte aynı numarayı alır. */
export function atiflariNumarala(icerik: string): AtifliMetin {
  const adlar: string[] = [];
  const anahtarlar: string[] = [];
  const metin = icerik.replace(ATIF_RE, (_tum, grup: string) => {
    const numaralar = atifAdlari(grup).map((ad) => {
      const anahtar = adAnahtari(ad);
      let i = anahtarlar.indexOf(anahtar);
      if (i < 0) {
        anahtarlar.push(anahtar);
        adlar.push(ad);
        i = anahtarlar.length - 1;
      }
      return i + 1;
    });
    return [...new Set(numaralar)].map((n) => `[${n}](${ATIF_HREF_ONEKI}${n})`).join("");
  });
  return { metin, adlar };
}

/** Kaynağın atıf numarası (1'den); metinde anılmadıysa null. */
export function kaynakNumarasi(kaynak: HukukbotKaynak, adlar: string[]): number | null {
  const anahtarlar = new Set([adAnahtari(kaynak.filename), adAnahtari(kaynak.file_display_name)]);
  const i = adlar.findIndex((ad) => anahtarlar.has(adAnahtari(ad)));
  return i < 0 ? null : i + 1;
}
