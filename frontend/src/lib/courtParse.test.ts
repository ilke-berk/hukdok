import { describe, expect, it } from "vitest";

import { parseCourt } from "./courtParse";

describe("parseCourt", () => {
  it("şehir + daire no + mahkeme türü (title case)", () => {
    expect(parseCourt("Samsun 2. Tüketici Mahkemesi")).toEqual({
      base: "Samsun Tüketici Mahkemesi",
      daireNo: "2",
    });
  });

  it("tam büyük harf Türkçe (intake merge çıktısı) — İ katlaması tuzağı", () => {
    expect(parseCourt("MERSİN 3. TÜKETİCİ MAHKEMESİ")).toEqual({
      base: "MERSİN TÜKETİCİ MAHKEMESİ",
      daireNo: "3",
    });
  });

  it("bölge mahkemesi + numaralı daire", () => {
    expect(parseCourt("Ankara Bölge İdare Mahkemesi 10. İdari Dava Dairesi")).toEqual({
      base: "Ankara Bölge İdare Mahkemesi",
      daireNo: "10",
    });
  });

  it("sözel daire sırası sayıya çevrilir", () => {
    expect(parseCourt("Ankara Bölge İdare Mahkemesi Üçüncü İdari Dava Dairesi")).toEqual({
      base: "Ankara Bölge İdare Mahkemesi",
      daireNo: "3",
    });
  });

  it("sözel daire — büyük harf ve İ/ı içeren sıra adları", () => {
    expect(parseCourt("ANKARA BÖLGE İDARE MAHKEMESİ İKİNCİ İDARİ DAVA DAİRESİ").daireNo).toBe("2");
    expect(parseCourt("ANKARA BÖLGE İDARE MAHKEMESİ ALTINCI İDARİ DAVA DAİRESİ").daireNo).toBe("6");
  });

  it("ayrıştırılamayan ad olduğu gibi base olur", () => {
    expect(parseCourt("İstanbul Anadolu 5. Asliye Ticaret Mahkemesi")).toEqual({
      base: "İstanbul Anadolu 5. Asliye Ticaret Mahkemesi",
      daireNo: "",
    });
    expect(parseCourt("Yargıtay")).toEqual({ base: "Yargıtay", daireNo: "" });
  });

  it("boş girdi", () => {
    expect(parseCourt("")).toEqual({ base: "", daireNo: "" });
  });
});
