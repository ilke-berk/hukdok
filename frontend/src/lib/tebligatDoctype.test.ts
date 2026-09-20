import { describe, expect, it } from "vitest";
import { isTebligatDoctype } from "./tebligatDoctype";

describe("tebligatDoctype", () => {
    it("pad'li ve düz yazımları tanır", () => {
        expect(isTebligatDoctype("TEBLIGAT______")).toBe(true);
        expect(isTebligatDoctype("TEBLIGAT")).toBe(true);
        expect(isTebligatDoctype("tebligat")).toBe(true);
    });

    it("diğer türler, boş ve undefined tebligat değildir", () => {
        expect(isTebligatDoctype("DILEKCE_______")).toBe(false);
        expect(isTebligatDoctype("GEREKCELI-KRR_")).toBe(false);
        expect(isTebligatDoctype("DAVA-DLK")).toBe(false);
        expect(isTebligatDoctype("")).toBe(false);
        expect(isTebligatDoctype(undefined)).toBe(false);
        expect(isTebligatDoctype(null)).toBe(false);
    });
});
