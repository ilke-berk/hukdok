// Dava tarihçesi etiketleri — panel ham alan adı basmaz (11.09.2026).
import { describe, expect, it } from "vitest";

import { tarihceEtiketi } from "./tarihceEtiketleri";

describe("tarihceEtiketi", () => {
    it("olay türleri Türkçe okunur", () => {
        expect(tarihceEtiketi("status")).toBe("Durum Değişti");
        expect(tarihceEtiketi("esas_no")).toBe("Esas No Değişti");
        expect(tarihceEtiketi("court")).toBe("Mahkeme Değişti");
        expect(tarihceEtiketi("tku_birlestirme")).toBe("Kart Birleştirildi (aynı dava, TKU)");
        expect(tarihceEtiketi("mukerrer_birlestirme")).toBe("Mükerrer Kart Birleştirildi");
        expect(tarihceEtiketi("case_foys.sistem_no")).toBe("Föy Bağlandı");
        expect(tarihceEtiketi("avukat")).toBe("Avukat Eklendi");
    });

    it("kart alanları etiketlenir, tanınmayan ad olduğu gibi döner", () => {
        expect(tarihceEtiketi("bureau_type")).toBe("Büro Özel Türü");
        expect(tarihceEtiketi("yepyeni_alan")).toBe("yepyeni_alan");
        expect(tarihceEtiketi(null)).toBe("");
        expect(tarihceEtiketi(undefined)).toBe("");
    });
});
