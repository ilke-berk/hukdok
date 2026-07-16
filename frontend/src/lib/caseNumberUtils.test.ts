import { describe, expect, it } from "vitest";
import {
    bestCategoryCode,
    generateNameBlock,
    generateTrackingNumber,
    pickNameClient,
    validateCaseNumber,
} from "./caseNumberUtils";

describe("generateTrackingNumber", () => {
    it("parametresiz çağrı güvenli varsayılanları üretir", () => {
        expect(generateTrackingNumber()).toBe("X1.XXXXXXXXXX.0001.HUKUK.00000");
    });

    it("kişi müvekkilde ad bloğu 'başharf_soyad' formatındadır", () => {
        const no = generateTrackingNumber({
            category: "Doktor",
            clientName: "İlke Berk Kutluk",
            clientCategory: "Doktor",
        });
        expect(no.split(".")[0]).toBe("D1");
        // Blok 2, 10 karaktere nokta ile doldurulur → "I_KUTLUK.."
        expect(no).toContain(".I_KUTLUK..");
    });

    it("kurum müvekkilde jenerik kelimeler atılır", () => {
        const no = generateTrackingNumber({
            category: "Sigorta",
            clientName: "Anadolu Sigorta A.Ş.",
            clientCategory: "Sigorta",
        });
        // "Sigorta"/"A.Ş." jenerik → ilk anlamlı kelime ANADOLU; Anadolu → S2
        expect(no.startsWith("S2.ANADOLU...")).toBe(true);
    });

    it("bilinen sigorta şirketi özgül kod alır", () => {
        const no = generateTrackingNumber({
            category: "Sigorta",
            clientName: "AXA Sigorta",
            clientCategory: "Sigorta",
        });
        expect(no.split(".")[0]).toBe("S3");
    });

    it("bilinmeyen sigorta S0 alır", () => {
        const no = generateTrackingNumber({
            category: "Sigorta",
            clientName: "Bilinmedik Sigorta",
            clientCategory: "Sigorta",
        });
        expect(no.split(".")[0]).toBe("S0");
    });

    it("süreç tipi ve sıra numarası bloklara yansır", () => {
        const no = generateTrackingNumber({ processType: "İcra", sequence: 12 });
        const parts = no.split(".");
        expect(parts[parts.length - 2]).toBe("ICRAA");
        expect(no).toContain(".0012.");
    });

    it("üretilen numara validateCaseNumber'dan geçer", () => {
        const cases = [
            generateTrackingNumber(),
            generateTrackingNumber({
                category: "Doktor",
                clientName: "İlke Berk Kutluk",
                clientCategory: "Doktor",
                sequence: 7,
                processType: "Ceza",
            }),
            generateTrackingNumber({
                category: "Sigorta",
                clientName: "AXA Sigorta",
                clientCategory: "Sigorta",
            }),
        ];
        for (const c of cases) expect(validateCaseNumber(c)).toBe(true);
    });
});

describe("generateNameBlock", () => {
    it("üretilen blok her zaman 10 karakterdir", () => {
        expect(generateNameBlock("İlke Berk Kutluk", "Doktor")).toHaveLength(10);
        expect(generateNameBlock("Anadolu Sigorta A.Ş.", "Sigorta")).toHaveLength(10);
        expect(generateNameBlock("", "")).toHaveLength(10);
    });

    it("generateTrackingNumber'ın 2. bloğuyla birebir aynıdır", () => {
        const samples: Array<{ name: string; cat: string }> = [
            { name: "İlke Berk Kutluk", cat: "Doktor" },
            { name: "Anadolu Sigorta A.Ş.", cat: "Sigorta" },
            { name: "Mehmet Öz", cat: "" },
        ];
        for (const s of samples) {
            const tracking = generateTrackingNumber({
                clientName: s.name,
                clientCategory: s.cat,
            });
            // Blok2 = 4..13 arası sabit genişlikli alan (blok2 nokta içerebildiği
            // için split(".") kullanılamaz)
            expect(tracking.slice(3, 13)).toBe(generateNameBlock(s.name, s.cat));
        }
    });

    it("kategori boşsa kişi formatı kullanılır", () => {
        expect(generateNameBlock("İlke Berk Kutluk")).toBe("I_KUTLUK..");
    });
});

describe("pickNameClient", () => {
    it("kişi kategorileri sigortaya tercih edilir", () => {
        const picked = pickNameClient([
            { name: "AXA Sigorta", category: "Sigorta Şirketi" },
            { name: "Mehmet Öz", category: "Doktor" },
        ]);
        expect(picked.name).toBe("Mehmet Öz");
    });

    it("öncelik sırası Doktor > Hasta > Bireysel", () => {
        const picked = pickNameClient([
            { name: "B", category: "Bireysel" },
            { name: "H", category: "Hasta" },
            { name: "D", category: "Doktor" },
        ]);
        expect(picked.name).toBe("D");
    });

    it("boş liste boş sonuç döner", () => {
        expect(pickNameClient([])).toEqual({ name: "", category: "" });
    });
});

describe("bestCategoryCode", () => {
    it("özgül sigorta kodu her şeyi yener", () => {
        const code = bestCategoryCode([
            { name: "Mehmet Öz", category: "Doktor" },
            { name: "AXA Sigorta", category: "Sigorta" },
        ]);
        expect(code).toBe("S3");
    });

    it("özgül sigorta yoksa S0 öne geçer", () => {
        const code = bestCategoryCode([
            { name: "Hasta Kişi", category: "Hasta" },
            { name: "Bilinmedik Sigorta", category: "Sigorta" },
        ]);
        expect(code).toBe("S0");
    });

    it("sigorta yoksa ilk anlamlı kod", () => {
        expect(bestCategoryCode([{ name: "Mehmet", category: "Hasta" }])).toBe("H1");
    });

    it("boş liste X1", () => {
        expect(bestCategoryCode([])).toBe("X1");
    });
});

describe("validateCaseNumber", () => {
    it("geçerli format kabul edilir", () => {
        expect(validateCaseNumber("D1.I_KUTLUK...0007.CEZAA.00000")).toBe(true);
    });

    it("bozuk formatlar reddedilir", () => {
        expect(validateCaseNumber("")).toBe(false);
        expect(validateCaseNumber("d1.i_kutluk...0007.cezaa.00000")).toBe(false); // küçük harf
        expect(validateCaseNumber("D1.KISA.0007.CEZAA.00000")).toBe(false);       // blok2 ≠ 10
        expect(validateCaseNumber("D1.I_KUTLUK...07.CEZAA.00000")).toBe(false);   // blok3 ≠ 4
    });
});
