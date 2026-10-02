/**
 * Türkçe katlama: tr-TR küçük harf + ç/ğ/ı/ş/ö/ü → c/g/i/s/o/u + birleşik
 * işaretlerin atılması ("İ".toLowerCase() kalıntısı dahil). "ŞAHİN" ≡ "sahin".
 * (Repodaki `predictDocType.foldTr` modül-içi ve alfanümerik dışını da sildiği
 * için arama alt-dizesine uygun değil — burada boşluk/nokta korunur.)
 */
export function foldTr(s: string): string {
  return s
    .toLocaleLowerCase("tr-TR")
    .replace(/ç/g, "c")
    .replace(/ğ/g, "g")
    .replace(/ı/g, "i")
    .replace(/ş/g, "s")
    .replace(/ö/g, "o")
    .replace(/ü/g, "u")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}
