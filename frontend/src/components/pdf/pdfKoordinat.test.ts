// pdfKoordinat (G272): piksel ↔ PDF puanı. Kilitlenen kural: ölçek = sayfa.genislik / görüntü genişliği; görünür düzlem
// olduğu için döndürülmüş sayfada (842×595) EK dönüşüm YOK — çekirdek (`page.derotation_matrix`) çevirir; kırpma sayfa
// sınırına; normalize; en küçük alan 4×4 pt.
import { describe, expect, it } from "vitest";
import {
  KARARTMA_MIN_PT,
  NOT_MAX_KARAKTER,
  alanBoyutMetni,
  dikdortgenNormalize,
  dikdortgeniPuana,
  karartmaAlaniGecerli,
  pikseldenPuana,
  puandanPiksele,
} from "./pdfKoordinat";

const A4 = { genislik: 595, yukseklik: 842 };
const A4_YAN = { genislik: 842, yukseklik: 595 }; // 90°/270° döndürülmüş görünür boyut

describe("pikseldenPuana", () => {
  it("ölçek 0,5 (595 pt sayfa, 1190 px görüntü): (100,200) px → (50,100) pt", () => {
    expect(pikseldenPuana({ x: 100, y: 200 }, 1190, A4)).toEqual({ x: 50, y: 100 });
  });

  it("ölçek 2 (595 pt sayfa, 297,5 px görüntü): (100,200) px → (200,400) pt", () => {
    expect(pikseldenPuana({ x: 100, y: 200 }, 297.5, A4)).toEqual({ x: 200, y: 400 });
  });

  it("sayfa sınırına kırpar: negatif → 0, aşan → genişlik/yükseklik", () => {
    expect(pikseldenPuana({ x: -40, y: -1 }, 1190, A4)).toEqual({ x: 0, y: 0 });
    expect(pikseldenPuana({ x: 5000, y: 9000 }, 1190, A4)).toEqual({ x: 595, y: 842 });
  });

  it("döndürülmüş sayfa (842×595 görünür): aynı kural, ek dönüşüm yok — ölçek genişlikten, y yüksekliğe kırpılır", () => {
    // 1684 px görüntü → ölçek 0,5; (1000, 1500) px → (500, 595) pt (y 750 → sayfa yüksekliği 595'e kırpıldı)
    expect(pikseldenPuana({ x: 1000, y: 1500 }, 1684, A4_YAN)).toEqual({ x: 500, y: 595 });
    expect(pikseldenPuana({ x: 200, y: 100 }, 1684, A4_YAN)).toEqual({ x: 100, y: 50 });
  });

  it("görüntü genişliği 0 ya da geçersiz sayfa → (0,0) (bölme hatası yok)", () => {
    expect(pikseldenPuana({ x: 10, y: 10 }, 0, A4)).toEqual({ x: 0, y: 0 });
    expect(pikseldenPuana({ x: 10, y: 10 }, 100, { genislik: 0, yukseklik: 0 })).toEqual({ x: 0, y: 0 });
    expect(pikseldenPuana({ x: Number.NaN, y: 10 }, 1190, A4)).toEqual({ x: 0, y: 5 });
  });

  it("iki ondalığa yuvarlar", () => {
    expect(pikseldenPuana({ x: 1, y: 1 }, 1190, A4)).toEqual({ x: 0.5, y: 0.5 });
    expect(pikseldenPuana({ x: 1, y: 1 }, 1000, A4)).toEqual({ x: 0.6, y: 0.6 }); // 0.595 → 0.6
  });
});

describe("puandanPiksele", () => {
  it("pikseldenPuana'nın tersidir (ölçek 0,5 ve 2)", () => {
    expect(puandanPiksele({ x: 50, y: 100 }, 1190, A4)).toEqual({ x: 100, y: 200 });
    expect(puandanPiksele({ x: 200, y: 400 }, 297.5, A4)).toEqual({ x: 100, y: 200 });
    const p = pikseldenPuana({ x: 333, y: 444 }, 1190, A4);
    expect(puandanPiksele(p, 1190, A4)).toEqual({ x: 333, y: 444 });
  });

  it("döndürülmüş sayfada da yalnız ölçek", () => {
    expect(puandanPiksele({ x: 421, y: 297.5 }, 1684, A4_YAN)).toEqual({ x: 842, y: 595 });
  });
});

describe("dikdortgeniPuana / normalize / geçerlilik", () => {
  it("ters çizilen dikdörtgen normalize edilir ve kırpılır", () => {
    expect(dikdortgeniPuana({ x0: 300, y0: 500, x1: 100, y1: 200 }, 1190, A4)).toEqual({ x0: 50, y0: 100, x1: 150, y1: 250 });
    expect(dikdortgeniPuana({ x0: -50, y0: -50, x1: 5000, y1: 5000 }, 1190, A4)).toEqual({ x0: 0, y0: 0, x1: 595, y1: 842 });
  });

  it("dikdortgenNormalize köşeleri sıralar", () => {
    expect(dikdortgenNormalize({ x0: 5, y0: 9, x1: 1, y1: 2 })).toEqual({ x0: 1, y0: 2, x1: 5, y1: 9 });
  });

  it(`karartmaAlaniGecerli: en az ${KARARTMA_MIN_PT}×${KARARTMA_MIN_PT} pt`, () => {
    expect(karartmaAlaniGecerli({ x0: 0, y0: 0, x1: 4, y1: 4 })).toBe(true);
    expect(karartmaAlaniGecerli({ x0: 0, y0: 0, x1: 3.9, y1: 40 })).toBe(false);
    expect(karartmaAlaniGecerli({ x0: 0, y0: 0, x1: 40, y1: 3 })).toBe(false);
    expect(karartmaAlaniGecerli({ x0: 10, y0: 10, x1: 2, y1: 2 })).toBe(true); // ters çizim normalize edilir
  });

  it("alanBoyutMetni yuvarlanmış genişlik×yükseklik", () => {
    expect(alanBoyutMetni({ x0: 50, y0: 100, x1: 150.4, y1: 250.6 })).toBe("100×151 pt");
  });

  it("NOT_MAX_KARAKTER sunucuyla aynı (2.000)", () => {
    expect(NOT_MAX_KARAKTER).toBe(2000);
  });
});
