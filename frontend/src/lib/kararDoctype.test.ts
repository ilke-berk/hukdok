import { describe, expect, it } from "vitest";
import { isKararDoctype, normalizeDoctypeKey } from "./kararDoctype";

describe("kararDoctype", () => {
    it("pad'li, tireli ve düz yazımları aynı anahtara indirger", () => {
        expect(normalizeDoctypeKey("GEREKCELI-KRR_")).toBe("GEREKCELIKRR");
        expect(normalizeDoctypeKey("gerekcelikrr")).toBe("GEREKCELIKRR");
        expect(normalizeDoctypeKey("ISTINAF-KRR___")).toBe("ISTINAFKRR");
    });

    it("yalnız karar belgelerini tanır; tebligat ve dilekçe karar değildir", () => {
        expect(isKararDoctype("GEREKCELI-KRR_")).toBe(true);
        expect(isKararDoctype("ISTINAFKRR")).toBe(true);
        expect(isKararDoctype("YARGITAY-KRR__")).toBe(true);
        expect(isKararDoctype("KRR_DZLTM-KRR_")).toBe(true);
        expect(isKararDoctype("TEBLIGAT______")).toBe(false);
        expect(isKararDoctype("ARA-KRR_______")).toBe(false);
        expect(isKararDoctype("ISTINAF-BSVR__")).toBe(false);
        expect(isKararDoctype("")).toBe(false);
        expect(isKararDoctype(undefined)).toBe(false);
    });
});
