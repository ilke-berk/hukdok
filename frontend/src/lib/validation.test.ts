import { describe, expect, it } from "vitest";
import { validateTCIdentity } from "./validation";

describe("validateTCIdentity", () => {
    it("boş değer geçerli sayılır (zorunluluk formda ele alınır)", () => {
        expect(validateTCIdentity("").isValid).toBe(true);
    });

    it("rakam dışı karakter reddedilir", () => {
        const r = validateTCIdentity("12a45678901");
        expect(r.isValid).toBe(false);
        expect(r.message).toContain("rakam");
    });

    it("10 haneli vergi no geçerlidir", () => {
        expect(validateTCIdentity("1234567890").isValid).toBe(true);
    });

    it("geçerli 11 haneli TC kimlik no kabul edilir", () => {
        // Checksum elle doğrulandı: tek haneler 25, çift haneler 20,
        // 10. hane (25*7-20)%10=5, 11. hane (45+5)%10=0
        expect(validateTCIdentity("12345678950").isValid).toBe(true);
    });

    it("10. hane checksum hatası reddedilir", () => {
        expect(validateTCIdentity("12345678940").isValid).toBe(false);
    });

    it("11. hane checksum hatası reddedilir", () => {
        expect(validateTCIdentity("12345678951").isValid).toBe(false);
    });

    it("0 ile başlayan TC reddedilir", () => {
        const r = validateTCIdentity("01234567895");
        expect(r.isValid).toBe(false);
        expect(r.message).toContain("0 ile başlayamaz");
    });

    it("9 veya 12 hane reddedilir", () => {
        expect(validateTCIdentity("123456789").isValid).toBe(false);
        expect(validateTCIdentity("123456789012").isValid).toBe(false);
    });
});
