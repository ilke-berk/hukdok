import { describe, expect, it } from "vitest";
import { closestName, levenshtein } from "./nameSimilarity";

describe("levenshtein", () => {
    it("özdeş stringler için 0 döner", () => {
        expect(levenshtein("mehmet", "mehmet")).toBe(0);
    });

    it("boş string için diğerinin uzunluğunu döner", () => {
        expect(levenshtein("", "abc")).toBe(3);
        expect(levenshtein("abc", "")).toBe(3);
    });

    it("klasik kitten→sitting örneği 3'tür", () => {
        expect(levenshtein("kitten", "sitting")).toBe(3);
    });

    it("tek harf değişimi 1'dir", () => {
        expect(levenshtein("mehmet", "mahmet")).toBe(1);
    });

    it("ekleme ve silme sayılır", () => {
        expect(levenshtein("ali", "alli")).toBe(1);
        expect(levenshtein("alli", "ali")).toBe(1);
    });
});

describe("closestName", () => {
    const candidates = ["Mehmet Yılmaz", "Ayşe Kaya", "Ali Can"];

    it("tam eşleşme (mesafe 0) null döner — öneri gerekmez", () => {
        expect(closestName("Mehmet Yılmaz", candidates)).toBe(null);
    });

    it("yazım hatasında en yakın adayın orijinal hâlini döner", () => {
        expect(closestName("Mehmet Yilmaz", candidates)).toBe("Mehmet Yılmaz");
    });

    it("büyük/küçük harf farkı tr-TR ile normalize edilir", () => {
        // Normalize sonrası özdeş → mesafe 0 → null
        expect(closestName("MEHMET YILMAZ", ["mehmet yılmaz"])).toBe(null);
    });

    it("eşik üstü farklar null döner", () => {
        expect(closestName("Tamamen Farklı Kişi", candidates)).toBe(null);
    });

    it("kısa adlarda eşik 1'dir", () => {
        expect(closestName("Alu", ["Ali"])).toBe("Ali");     // mesafe 1 → öneri
        expect(closestName("AXY", ["Ali"])).toBe(null);       // mesafe 2 → eşik üstü
    });

    it("boş hedef veya boş aday listesi null döner", () => {
        expect(closestName("", candidates)).toBe(null);
        expect(closestName("   ", candidates)).toBe(null);
        expect(closestName("Mehmet", [])).toBe(null);
    });
});
