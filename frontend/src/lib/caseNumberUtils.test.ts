import { describe, expect, it } from "vitest";
import {
    CATEGORY_MAP,
    INSURANCE_CODES,
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

    it("sağlık çalışanı D2 kodu ve kişi formatı alır", () => {
        const no = generateTrackingNumber({
            category: "Sağlık Çalışanı",
            clientName: "Ayşe Yılmaz",
            clientCategory: "Sağlık Çalışanı",
        });
        expect(no.split(".")[0]).toBe("D2");
        expect(no).toContain(".A_YILMAZ..");
    });

    it("süreç tipi ve sıra numarası bloklara yansır", () => {
        const no = generateTrackingNumber({ processType: "İcra", sequence: 12 });
        const parts = no.split(".");
        expect(parts[parts.length - 2]).toBe("ICRAA");
        expect(no).toContain(".0012.");
    });

    // 2026-08-05: bu 4 tür haritada eksikti ve sessizce HUKUK üretiyordu
    it.each([
        ["İdare", "IDARE"],
        ["Tahkim", "TAHKM"],
        ["Vergi", "VERGI"],
        ["Danışmanlık", "DANIS"],
    ])("%s türü blok4'te %s üretir (HUKUK'a düşmez)", (processType, expected) => {
        const no = generateTrackingNumber({ processType });
        const parts = no.split(".");
        expect(parts[parts.length - 2]).toBe(expected);
        expect(validateCaseNumber(no)).toBe(true);
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

    it("öncelik sırası Doktor > Sağlık Çalışanı > Hasta > Bireysel", () => {
        const picked = pickNameClient([
            { name: "B", category: "Bireysel" },
            { name: "H", category: "Hasta" },
            { name: "S", category: "Sağlık Çalışanı" },
            { name: "D", category: "Doktor" },
        ]);
        expect(picked.name).toBe("D");

        const withoutDoctor = pickNameClient([
            { name: "B", category: "Bireysel" },
            { name: "H", category: "Hasta" },
            { name: "S", category: "Sağlık Çalışanı" },
        ]);
        expect(withoutDoctor.name).toBe("S");
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

    it("sigorta yoksa açık öncelik: D1 > D2 > H2 > H1 (liste sırasından bağımsız)", () => {
        expect(bestCategoryCode([
            { name: "Hasta Kişi", category: "Hasta" },
            { name: "Hemşire Ayşe", category: "Sağlık Çalışanı" },
            { name: "Mehmet Öz", category: "Doktor" },
        ])).toBe("D1");

        expect(bestCategoryCode([
            { name: "Hasta Kişi", category: "Hasta" },
            { name: "Özel Hastane A.Ş.", category: "Özel Hastane" },
            { name: "Hemşire Ayşe", category: "Sağlık Çalışanı" },
        ])).toBe("D2");
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

// G223: NewCase/Intake `category` olarak `bestCategoryCode` çıktısını (B1 KODU) geçer;
// fonksiyon önceden yalnız kategori ADI bekleyip kodu X1'e düşürüyordu.
describe("generateTrackingNumber — B1 kodu ile çağrı (G223)", () => {
    const b1 = (no: string) => no.split(".")[0];

    it("geçerli B1 kodu verilirse aynen kullanılır", () => {
        expect(b1(generateTrackingNumber({
            category: "D1", clientName: "Ayşe Gül Öztürk", clientCategory: "Doktor",
        }))).toBe("D1");
        expect(generateTrackingNumber({ category: "D1" }).startsWith("D1.")).toBe(true);
        expect(b1(generateTrackingNumber({ category: "H2", clientName: "X Hastanesi", clientCategory: "Özel Hastane" }))).toBe("H2");
        expect(b1(generateTrackingNumber({ category: "S4", clientName: "Quick Sigorta A.Ş.", clientCategory: "Sigorta" }))).toBe("S4");
    });

    it("kategori adıyla çağrı eski davranışı korur", () => {
        expect(b1(generateTrackingNumber({ category: "Doktor", clientName: "Mehmet Öz", clientCategory: "Doktor" }))).toBe("D1");
        expect(b1(generateTrackingNumber({ category: "Özel Hastane", clientName: "Acıbadem", clientCategory: "Özel Hastane" }))).toBe("H2");
    });

    // NewCase.tsx / IntakeReviewStep.tsx'in gerçek çağrı biçimi
    const cagriBicimi = (clients: Array<{ name: string; category?: string }>) => {
        const named = pickNameClient(clients);
        return generateTrackingNumber({
            category: bestCategoryCode(clients),
            clientName: named.name,
            clientCategory: named.category,
            sequence: 1,
            processType: "Hukuk",
        });
    };

    it("NewCase/Intake çağrı biçiminde Doktor müvekkil D1 alır (X1 değil)", () => {
        const no = cagriBicimi([{ name: "Ayşe Gül Öztürk", category: "Doktor" }]);
        // Blok 2 = "A_OZTURK.." (10 karakter) + ayraç nokta
        expect(no).toBe("D1.A_OZTURK...0001.HUKUK.00000");
    });

    it("NewCase/Intake çağrı biçiminde Hasta müvekkil haritadaki kodu alır", () => {
        const no = cagriBicimi([{ name: "Mehmet Yılmaz", category: "Hasta" }]);
        expect(b1(no)).toBe(CATEGORY_MAP["Hasta"]);
    });

    it("NewCase/Intake çağrı biçiminde Sağlık Çalışanı ve Özel Hastane doğru kod alır", () => {
        expect(b1(cagriBicimi([{ name: "Hemşire Ayşe", category: "Sağlık Çalışanı" }]))).toBe(CATEGORY_MAP["Sağlık Çalışanı"]);
        expect(b1(cagriBicimi([{ name: "Acıbadem Hastanesi", category: "Özel Hastane" }]))).toBe(CATEGORY_MAP["Özel Hastane"]);
    });
});

describe("sigorta kodu ASCII normalize adla aranır (G223)", () => {
    const b1 = (no: string) => no.split(".")[0];

    it("küçük harfli Quick → INSURANCE_CODES['QUICK']", () => {
        const no = generateTrackingNumber({
            category: "Sigorta", clientName: "Quick Sigorta A.Ş.", clientCategory: "Sigorta",
        });
        expect(b1(no)).toBe(`S${INSURANCE_CODES["QUICK"]}`);
        expect(b1(no)).toBe("S4");
    });

    it("küçük harfli Nippon → INSURANCE_CODES['NIPPON']", () => {
        const no = generateTrackingNumber({
            category: "Sigorta", clientName: "Nippon Sigorta", clientCategory: "Sigorta",
        });
        expect(b1(no)).toBe(`S${INSURANCE_CODES["NIPPON"]}`);
        expect(b1(no)).toBe("S6");
    });

    it("kategorisiz çağrıda da adda 'Sigorta' + marka yakalanır", () => {
        expect(b1(generateTrackingNumber({ clientName: "Nippon Sigorta" }))).toBe("S6");
    });

    it("bestCategoryCode ile aynı sonucu verir", () => {
        for (const name of ["Quick Sigorta A.Ş.", "Nippon Sigorta", "Axa Sigorta", "Bilinmedik Sigorta"]) {
            expect(b1(generateTrackingNumber({ category: "Sigorta", clientName: name, clientCategory: "Sigorta" })))
                .toBe(bestCategoryCode([{ name, category: "Sigorta" }]));
        }
    });
});
