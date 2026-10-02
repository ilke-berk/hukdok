// lib/hataBildirimleri — saf yardımcılar (ağ çağrıları bileşen testinde: components/hata/HataBildirimi.test.tsx).
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import {
    type HataAliciAdayi,
    HATA_ACIKLAMA_AZAMI,
    HATA_DEGER_AZAMI,
    alicilarMetni,
    guvenliIcYol,
    kisiEtiketi,
    onSecim,
    taslakGecerliMi,
} from "./hataBildirimleri";

describe("taslakGecerliMi", () => {
    it("doğru değer ya da açıklamadan en az biri dolu olmalı", () => {
        expect(taslakGecerliMi("", "")).toBe(false);
        expect(taslakGecerliMi("  ", "\n ")).toBe(false);
        expect(taslakGecerliMi("2024/65", "")).toBe(true);
        expect(taslakGecerliMi("", "Esas no yanlış")).toBe(true);
    });

    it("sunucu sınırlarını trim sonrası uygular", () => {
        expect(taslakGecerliMi("x".repeat(HATA_DEGER_AZAMI), "")).toBe(true);
        expect(taslakGecerliMi("x".repeat(HATA_DEGER_AZAMI + 1), "")).toBe(false);
        expect(taslakGecerliMi("", ` ${"x".repeat(HATA_ACIKLAMA_AZAMI)} `)).toBe(true);
        expect(taslakGecerliMi("ok", "x".repeat(HATA_ACIKLAMA_AZAMI + 1))).toBe(false);
    });
});

describe("kisiEtiketi", () => {
    it("ad varsa ad, yoksa e-posta", () => {
        expect(kisiEtiketi("Av. Ayşe Kaya", "ayse@example.com")).toBe("Av. Ayşe Kaya");
        expect(kisiEtiketi("  ", "ayse@example.com")).toBe("ayse@example.com");
        expect(kisiEtiketi(null, null)).toBe("");
    });
});

describe("onSecim", () => {
    const adaylar: HataAliciAdayi[] = [
        { email: "nurten@x.tr", ad: "Nurten Meral", grup: "IDARI", varsayilan: true },
        { email: "serap@x.tr", ad: "Serap Turgal", grup: "AVUKAT", varsayilan: false },
        { email: "ilke@y.tr", ad: "İlke", grup: "YONETICI", varsayilan: false },
    ];

    it("son seçimden hâlâ aday olanlar, aday sırasıyla", () => {
        expect(onSecim(adaylar, ["ilke@y.tr", "ayrilan@x.tr", "serap@x.tr"])).toEqual(["serap@x.tr", "ilke@y.tr"]);
    });

    it("hatırlanan kimse kalmadıysa varsayılan alıcılar; o da yoksa boş", () => {
        expect(onSecim(adaylar, [])).toEqual(["nurten@x.tr"]);
        expect(onSecim(adaylar, ["ayrilan@x.tr"])).toEqual(["nurten@x.tr"]);
        expect(onSecim(adaylar.slice(1), [])).toEqual([]);
    });
});

describe("alicilarMetni", () => {
    it("adları virgülle birleştirir; adı olmayan e-postasıyla, boş liste boş metin", () => {
        expect(alicilarMetni([{ email: "n@x.tr", ad: "Nurten Meral" }, { email: "i@y.tr", ad: " " }])).toBe("Nurten Meral, i@y.tr");
        expect(alicilarMetni([])).toBe("");
        expect(alicilarMetni(undefined)).toBe("");
    });
});

describe("guvenliIcYol", () => {
    it("yalnız uygulama içi mutlak yolu kabul eder", () => {
        expect(guvenliIcYol("/cases/12?hata=5")).toBe("/cases/12?hata=5");
        expect(guvenliIcYol("/clients?client=7&hata=6")).toBe("/clients?client=7&hata=6");
    });

    it("dış adresi, protokol-göreli yolu ve boş değeri reddeder", () => {
        expect(guvenliIcYol("https://evil.example/x")).toBeNull();
        expect(guvenliIcYol("//evil.example/x")).toBeNull();
        expect(guvenliIcYol("/\\evil.example")).toBeNull();
        expect(guvenliIcYol("cases/12")).toBeNull();
        expect(guvenliIcYol("")).toBeNull();
        expect(guvenliIcYol(null)).toBeNull();
        expect(guvenliIcYol(undefined)).toBeNull();
    });
});
