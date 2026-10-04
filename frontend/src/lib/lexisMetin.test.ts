// Lexis metin yardımcıları: dayanak alıntısı kaynak metinde çekirdeğin toleransıyla bulunur (boşluk, tırnak,
// noktalama, büyük-küçük harf sayılmaz; `…` ile atlanan yerden bölünür) ve aralık ÖZGÜN metnin konumlarıdır.
import { describe, expect, it } from "vitest";
import { alintiAraliklari, alintiGeciyor, alintiParcalari, alintiUzunlugu, katla, tarihYaz, tutarOku, tutarYaz } from "./lexisMetin";

describe("katla", () => {
  it("yalnız harf ve rakamı tutar, Türkçe küçük harfe çevirir", () => {
    expect(katla("  İddia: “IŞIK” 2025/101 E. ")).toBe("iddiaışık2025101e");
  });
});

describe("alintiAraliklari", () => {
  const metin = "Raporda, “uygulamada  tıbbi hata saptanmadığı” ve tedavinin ZAMANINDA başlatıldığı ifade edilmiştir.";

  it("noktalama ve boşluk farkına rağmen bulur; aralık özgün metni keser", () => {
    const araliklar = alintiAraliklari(metin, "Uygulamada tıbbi hata saptanmadığı");
    expect(araliklar).toHaveLength(1);
    const [a] = araliklar!;
    expect(metin.slice(a.bas, a.son)).toBe("uygulamada  tıbbi hata saptanmadığı");
  });

  it("… ile atlanan alıntı parça parça ve sırayla aranır", () => {
    const araliklar = alintiAraliklari(metin, "tıbbi hata saptanmadığı … zamanında başlatıldığı");
    expect(araliklar!.map((a) => metin.slice(a.bas, a.son))).toEqual(["tıbbi hata saptanmadığı", "ZAMANINDA başlatıldığı"]);
    // Sıra ters ise bulunmaz
    expect(alintiAraliklari(metin, "zamanında başlatıldığı … tıbbi hata saptanmadığı")).toBeNull();
  });

  it("metinde geçmeyen ya da boş alıntı null döner", () => {
    expect(alintiAraliklari(metin, "onam formu alınmadığı")).toBeNull();
    expect(alintiAraliklari(metin, " … ")).toBeNull();
    expect(alintiGeciyor(metin, "ifade edilmiştir")).toBe(true);
  });

  it("alıntı uzunluğu harf + rakam sayısıdır", () => {
    expect(alintiUzunlugu("a b, c!")).toBe(3);
    expect(alintiParcalari("bir ... iki … üç")).toEqual(["bir", "iki", "üç"]);
  });
});

describe("yazım", () => {
  it("tutar Türkçe biçimde, boş değer […] olarak yazılır", () => {
    expect(tutarYaz(135418)).toBe("135.418,00 TL");
    expect(tutarYaz(null)).toBe("[…]");
  });

  it("yazılan tutar sayıya çevrilir; boş null, tanınmayan undefined", () => {
    expect(tutarOku("135.418,00")).toBe(135418);
    expect(tutarOku("250.000 TL")).toBe(250000);
    expect(tutarOku("1500,5")).toBe(1500.5);
    expect(tutarOku("  ")).toBeNull();
    expect(tutarOku("yüz bin")).toBeUndefined();
    expect(tutarOku("1.5.0")).toBeUndefined();
  });

  it("ISO tarih gg.aa.yyyy olur", () => {
    expect(tarihYaz("2025-03-14")).toBe("14.03.2025");
    expect(tarihYaz(null)).toBe("[…]");
  });
});
