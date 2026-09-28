// Metin içi atıf numaralama (28.09): hukbot `citation_check` kalıbıyla birebir ayrıştırma; aynı belge aynı
// numarayı alır; parantezdeki çoklu ad ("A, B" / "A / B" / "A ve B") ayrı rozet olur; kaynak kartı dosya adıyla,
// görünen adla ya da uzantısız anılışla eşleşir; atıf olmayan parantez metne dokunulmaz.
import { describe, expect, it } from "vitest";
import type { HukukbotKaynak } from "@/types/hukukbot";
import { alintiDogrulandi, atifAdlari, atiflariNumarala, kaynakNumarasi } from "./atiflar";

const kaynak = (filename: string, file_display_name = filename): HukukbotKaynak => ({
  filename,
  file_display_name,
  text_preview: "",
});

describe("atiflariNumarala", () => {
  it("ilk geçiş sırasıyla numaralar; tekrar eden belge aynı numara; önceki boşluk yutulur", () => {
    const { metin, adlar } = atiflariNumarala(
      "Sorumluluk hekimdedir (Kaynak: 2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf).\n" +
        "- Doktor gerekir (Kaynak: KARAR_LEHE_048.pdf).\n" +
        "- Gecikme hekime yüklenemez (Kaynak: 2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf).",
    );
    expect(adlar).toEqual(["2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf", "KARAR_LEHE_048.pdf"]);
    expect(metin).toBe(
      "Sorumluluk hekimdedir[1](#atif-1).\n- Doktor gerekir[2](#atif-2).\n- Gecikme hekime yüklenemez[1](#atif-1).",
    );
  });

  it("tek parantezde birden çok belge ayrı rozet; köşeli/bold sarmal ve 'Kaynak Belge' varyantı", () => {
    expect(atiflariNumarala("x (Kaynak: A.pdf, B.pdf) y (Kaynak Belge: **[C.pdf]**)").metin).toBe(
      "x[1](#atif-1)[2](#atif-2) y[3](#atif-3)",
    );
    expect(atifAdlari("A.pdf / B.pdf ve C.pdf")).toEqual(["A.pdf", "B.pdf", "C.pdf"]);
    expect(atifAdlari("gerekçe için bkz. KARAR_12.pdf")).toEqual(["KARAR_12.pdf"]);
  });

  it("aynı parantezde aynı belge iki kez yazılsa tek rozet", () => {
    expect(atiflariNumarala("x (Kaynak: A.pdf; a.pdf)").metin).toBe("x[1](#atif-1)");
  });

  it("atıf olmayan parantez ve kapanmamış (akış sürerken) atıf aynen kalır", () => {
    expect(atiflariNumarala("Madde 24 (3. fıkra) uyarınca").metin).toBe("Madde 24 (3. fıkra) uyarınca");
    const yarim = "Sorumluluk (Kaynak: 2026-07-29_BILIR";
    expect(atiflariNumarala(yarim)).toEqual({ metin: yarim, adlar: [], alintilar: [] });
  });

  it("alıntı `[metin](#alinti-i)` olur (köşeli parantezli/siz, tipografik tırnak); içindeki köşeli parantez kaçırılır", () => {
    const { metin, alintilar } = atiflariNumarala(
      '[Alıntı: "davanın reddine"] (Kaynak: A.pdf) ve Alıntı: “sevk [ek] gerekir” sonra',
    );
    expect(alintilar).toEqual(["davanın reddine", "sevk [ek] gerekir"]);
    expect(metin).toBe("[davanın reddine](#alinti-0)[1](#atif-1) ve [sevk \\[ek\\] gerekir](#alinti-1) sonra");
  });
});

describe("alintiDogrulandi", () => {
  it("kaynak kartlarındaki alıntı sonucunu döndürür; bulunamazsa null", () => {
    const kaynaklar: HukukbotKaynak[] = [
      { ...kaynak("A.pdf"), alintilar: [{ metin: "davanın reddine", dogrulandi: true }] },
      { ...kaynak("B.pdf"), alintilar: [{ metin: "uydurma cümle", dogrulandi: false }] },
    ];
    expect(alintiDogrulandi("davanın reddine", kaynaklar)).toBe(true);
    expect(alintiDogrulandi(" uydurma cümle ", kaynaklar)).toBe(false);
    expect(alintiDogrulandi("başka", kaynaklar)).toBeNull();
  });
});

describe("kaynakNumarasi", () => {
  const adlar = ["KARAR_LEHE_048.pdf", "Bilirkisi Raporu"];
  it("dosya adıyla (büyük/küçük harf, boşluk=alt çizgi) ve uzantısız anılışla eşler", () => {
    expect(kaynakNumarasi(kaynak("karar_lehe_048.pdf"), adlar)).toBe(1);
    expect(kaynakNumarasi(kaynak("Bilirkisi_Raporu.pdf"), adlar)).toBe(2);
  });
  it("görünen adla eşler; anılmayan kaynak null", () => {
    expect(kaynakNumarasi(kaynak("x-123.pdf", "KARAR_LEHE_048.pdf"), adlar)).toBe(1);
    expect(kaynakNumarasi(kaynak("BASKA.pdf"), adlar)).toBeNull();
  });
});
