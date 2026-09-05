// multiValue — çok değerli hücre sözleşmesi (G124), backend services/multi_value ikizi.
import { describe, expect, it } from "vitest";
import { joinValues, splitValues, MULTI_SEPARATOR } from "./multiValue";

describe("splitValues", () => {
    it("noktalı virgülle ayırır, kırpar, boş ve mükerrer parçayı düşürür", () => {
        expect(splitValues("Komplikasyon Yönetimi ; Takip Eksikliği;; takip eksikliği ")).toEqual([
            "Komplikasyon Yönetimi", "Takip Eksikliği",
        ]);
    });
    it("virgül ayraç DEĞİLDİR — değerler virgül içerebilir", () => {
        expect(splitValues("Kaynamama / Yanlış Kaynama (Psödoartroz), Gecikmiş")).toEqual([
            "Kaynamama / Yanlış Kaynama (Psödoartroz), Gecikmiş",
        ]);
    });
    it("boş/null → []", () => {
        expect(splitValues(null)).toEqual([]);
        expect(splitValues("")).toEqual([]);
        expect(splitValues(" ; ")).toEqual([]);
    });
});

describe("joinValues", () => {
    it("kanonik ayraçla birleştirir, boş parçayı düşürür", () => {
        expect(joinValues(["A", " B ", ""])).toBe(`A${MULTI_SEPARATOR}B`);
        expect(joinValues([])).toBe("");
    });
    it("split ∘ join birebir geri döner", () => {
        const s = "Vajinal ; Sezaryen";
        expect(joinValues(splitValues(s))).toBe(s);
    });
});
