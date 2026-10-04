// Lexis sayfasının metin yardımcıları: alıntıyı kaynak metinde bulma (dayanak vurgusu) ve tutar/tarih yazımı.
// Alıntı eşleşmesi çekirdeğin dayanak kuralıyla aynı toleransı taşır (`lexis_rapor/yazici.py`): boşluk,
// tırnak, noktalama ve büyük-küçük harf farkı sayılmaz; `…` ile atlanan yerden bölünür.

const HARF_RAKAM = /[\p{L}\p{N}]/u;

/** Doldurulmamış yer işareti — çekirdekle aynı (`taslak.py::BOS`). */
export const BOS = "[…]";

/** Karşılaştırma anahtarı: yalnız harf ve rakamlar, Türkçe küçük harfle. */
export function katla(metin: string): string {
  let sonuc = "";
  for (const ch of metin) {
    if (HARF_RAKAM.test(ch)) sonuc += ch.toLocaleLowerCase("tr");
  }
  return sonuc;
}

/** Alıntıdaki harf + rakam sayısı — 12'den azı "çok kısa" sayılır. */
export function alintiUzunlugu(alinti: string): number {
  return katla(alinti).length;
}

export const ALINTI_ALT_SINIRI = 12;

/** `…` / `...` ile atlanmış alıntının parçaları (boş parçalar atılır). */
export function alintiParcalari(alinti: string): string[] {
  return alinti
    .split(/…|\.{3}/)
    .map((p) => p.trim())
    .filter((p) => katla(p).length > 0);
}

export interface MetinAraligi {
  bas: number;
  son: number;
}

/**
 * Katlanmış metin ve her katlanmış karakterin özgün metindeki [baş, son) konumu. Türkçe küçük harfe çevirme
 * tek karakteri birden çok karaktere açabilir ("İ" → "i̇"); konum dizisi katlanmış karakter başına tutulur.
 */
function katlaKonumlu(metin: string): { katli: string; baslar: number[]; sonlar: number[] } {
  let katli = "";
  const baslar: number[] = [];
  const sonlar: number[] = [];
  let i = 0;
  for (const ch of metin) {
    const son = i + ch.length;
    if (HARF_RAKAM.test(ch)) {
      const kucuk = ch.toLocaleLowerCase("tr");
      for (let k = 0; k < kucuk.length; k += 1) {
        baslar.push(i);
        sonlar.push(son);
      }
      katli += kucuk;
    }
    i = son;
  }
  return { katli, baslar, sonlar };
}

/**
 * Alıntının `metin` içindeki aralıkları (özgün metnin karakter konumları). Parçalar sırayla aranır; biri
 * bulunamazsa `null`. Vurgulama bu aralıkları kullanır.
 */
export function alintiAraliklari(metin: string, alinti: string): MetinAraligi[] | null {
  const parcalar = alintiParcalari(alinti);
  if (parcalar.length === 0) return null;
  const { katli, baslar, sonlar } = katlaKonumlu(metin);
  const araliklar: MetinAraligi[] = [];
  let baslangic = 0;
  for (const parca of parcalar) {
    const anahtar = katla(parca);
    const konum = katli.indexOf(anahtar, baslangic);
    if (konum === -1) return null;
    const bitis = konum + anahtar.length;
    araliklar.push({ bas: baslar[konum], son: sonlar[bitis - 1] });
    baslangic = bitis;
  }
  return araliklar;
}

/** Alıntı metinde geçiyor mu. */
export function alintiGeciyor(metin: string, alinti: string): boolean {
  return alintiAraliklari(metin, alinti) !== null;
}

/** `135418` → `135.418,00 TL`; boşsa `[…]`. */
export function tutarYaz(tutar: number | null | undefined): string {
  if (tutar === null || tutar === undefined) return BOS;
  return `${tutar.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} TL`;
}

/** ISO `yyyy-mm-dd` → `dd.mm.yyyy`; boşsa `[…]`, biçim tanınmazsa olduğu gibi. */
export function tarihYaz(iso: string | null | undefined): string {
  if (!iso) return BOS;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
}

/** ISO zaman damgası → `dd.mm.yyyy HH:MM` (Türkiye saati). */
export function tarihSaatYaz(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("tr-TR", {
    timeZone: "Europe/Istanbul",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
