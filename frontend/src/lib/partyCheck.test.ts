import { describe, expect, it } from "vitest";
import { splitCheckNames, partyNameKey, MIN_CHECK_LENGTH } from "./partyCheck";

describe("splitCheckNames", () => {
    it("noktalı virgülle ayrılmış isimleri böler", () => {
        expect(splitCheckNames("Ahmet Yılmaz; Ayşe Kaya")).toEqual(["Ahmet Yılmaz", "Ayşe Kaya"]);
    });

    it("virgülle ayrılmış isimleri böler (QuickCase formatı)", () => {
        expect(splitCheckNames("Ahmet Yılmaz, Ayşe Kaya")).toEqual(["Ahmet Yılmaz", "Ayşe Kaya"]);
    });

    it("boş parçaları ve fazla boşlukları temizler", () => {
        expect(splitCheckNames("  Ahmet Yılmaz ;; , ")).toEqual(["Ahmet Yılmaz"]);
    });

    it("tek isim tek eleman döner", () => {
        expect(splitCheckNames("Ahmet Yılmaz")).toEqual(["Ahmet Yılmaz"]);
    });

    it("boş string boş dizi döner", () => {
        expect(splitCheckNames("")).toEqual([]);
    });
});

describe("partyNameKey", () => {
    it("Türkçe büyük harfe çevirir ve kırpar", () => {
        expect(partyNameKey("  ilker öztürk ")).toBe("İLKER ÖZTÜRK");
    });
});

describe("MIN_CHECK_LENGTH", () => {
    it("kısa isim eşiği 4'tür (backend party_check._NAME_MIN_LEN ile aynı)", () => {
        expect(MIN_CHECK_LENGTH).toBe(4);
    });
});
