// Piksel ↔ PDF puanı dönüşümü (G272; plan §3 `karart`/`not`, §5 "karartma koordinatı", çekirdek G267 kuralı).
//
// Sunucu sözleşmesi: alanlar ve not noktası **görünür** sayfa düzlemindedir — sol-üst orijin, PDF puanı;
// `Dosya.sayfalar[].genislik/yukseklik` döndürme UYGULANMIŞ görünür boyuttur ve önizleme PNG'si de görünür düzlemi
// çizer. Bu yüzden tarayıcı tarafında döndürme için EK dönüşüm YOKTUR: ölçek yalnız `sayfa.genislik / görüntü genişliği`
// (çekirdek `page.derotation_matrix` ile açıklama düzlemine kendisi çevirir; `pdfKoordinat.test.ts` bunu belgeler).
// Değerler sayfa sınırına kırpılır (sunucu da kırpar, ama "sayfa dışı/boş alan" 422'sine düşmemek için).
import type { DosyaSayfasi, KarartmaAlani } from "@/types/pdfAraclari";

export type Nokta = { x: number; y: number };
export type Dikdortgen = { x0: number; y0: number; x1: number; y1: number };

/** Karartma alanının kabul edilen en küçük kenarı (PDF puanı); daha küçük sürüklemeler yok sayılır. */
export const KARARTMA_MIN_PT = 4;

/** Not metni üst sınırı — sunucu `NOT_MAX_KARAKTER` ile aynı (plan §3). */
export const NOT_MAX_KARAKTER = 2000;

function sinirla(v: number, ust: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.min(Math.max(v, 0), ust);
}

function yuvarla(v: number): number {
  return Math.round(v * 100) / 100;
}

/** Görüntüdeki piksel → görünür düzlemde PDF puanı; ölçek `sayfa.genislik / goruntuGenislik`, sayfa sınırına kırpılır. */
export function pikseldenPuana(nokta: Nokta, goruntuGenislik: number, sayfa: Pick<DosyaSayfasi, "genislik" | "yukseklik">): Nokta {
  if (!(goruntuGenislik > 0) || !(sayfa.genislik > 0)) return { x: 0, y: 0 };
  const olcek = sayfa.genislik / goruntuGenislik;
  return {
    x: yuvarla(sinirla(nokta.x * olcek, sayfa.genislik)),
    y: yuvarla(sinirla(nokta.y * olcek, sayfa.yukseklik)),
  };
}

/** Overlay'deki pointer konumu → görünür düzlem PDF puanı (overlay genişliği = görüntü genişliği; 0 ise `null`). */
export function overlayNoktasi(
  e: { clientX: number; clientY: number; currentTarget: Element },
  sayfa: Pick<DosyaSayfasi, "genislik" | "yukseklik">,
): Nokta | null {
  const r = e.currentTarget.getBoundingClientRect();
  if (!(r.width > 0)) return null;
  return pikseldenPuana({ x: e.clientX - r.left, y: e.clientY - r.top }, r.width, sayfa);
}

/** `pikseldenPuana`'nın tersi: PDF puanı → görüntü pikseli (kırpmasız; çizim katmanı için). */
export function puandanPiksele(nokta: Nokta, goruntuGenislik: number, sayfa: Pick<DosyaSayfasi, "genislik" | "yukseklik">): Nokta {
  if (!(goruntuGenislik > 0) || !(sayfa.genislik > 0)) return { x: 0, y: 0 };
  const olcek = goruntuGenislik / sayfa.genislik;
  return { x: yuvarla(nokta.x * olcek), y: yuvarla(nokta.y * olcek) };
}

/** Piksel dikdörtgeni → PDF puanı; köşeler normalize edilir (x0 ≤ x1, y0 ≤ y1) ve sayfa sınırına kırpılır. */
export function dikdortgeniPuana(dik: Dikdortgen, goruntuGenislik: number, sayfa: Pick<DosyaSayfasi, "genislik" | "yukseklik">): Dikdortgen {
  const a = pikseldenPuana({ x: dik.x0, y: dik.y0 }, goruntuGenislik, sayfa);
  const b = pikseldenPuana({ x: dik.x1, y: dik.y1 }, goruntuGenislik, sayfa);
  return dikdortgenNormalize({ x0: a.x, y0: a.y, x1: b.x, y1: b.y });
}

export function dikdortgenNormalize(dik: Dikdortgen): Dikdortgen {
  return {
    x0: Math.min(dik.x0, dik.x1),
    y0: Math.min(dik.y0, dik.y1),
    x1: Math.max(dik.x0, dik.x1),
    y1: Math.max(dik.y0, dik.y1),
  };
}

/** Alan en az `KARARTMA_MIN_PT × KARARTMA_MIN_PT` puan mı (aksi yok sayılır)? */
export function karartmaAlaniGecerli(alan: Dikdortgen): boolean {
  const n = dikdortgenNormalize(alan);
  return n.x1 - n.x0 >= KARARTMA_MIN_PT && n.y1 - n.y0 >= KARARTMA_MIN_PT;
}

/** Listede gösterim: `120×45 pt`. */
export function alanBoyutMetni(alan: Pick<KarartmaAlani, "x0" | "y0" | "x1" | "y1">): string {
  const n = dikdortgenNormalize(alan);
  return `${Math.round(n.x1 - n.x0)}×${Math.round(n.y1 - n.y0)} pt`;
}
