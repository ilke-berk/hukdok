import { describe, expect, it } from "vitest";
import {
    MEDICAL_CARD_FIELDS, OFFICE_CARD_FIELDS, PROCESS_CARD_FIELDS,
    closedListState, filledFields, hasAnyValue,
} from "./caseCardFields";
import { TRACKING_DRAFT_KEYS } from "./trackingDraft";

/**
 * G121 — Müvekkil Tipi + Hizmet Türü büro kartı alanları (DB-2026-002).
 * Sözleşme G119 ile ORTAK (dondurulmuş): alan anahtarları muvekkil_tipi /
 * hizmet_turu, liste anahtarları client_types / service_types; liste uçları
 * event_types biçiminde (code/name/active/sequence) döner — burada mock'u
 * yalnız name taşır, closedListState de yalnız name okur.
 */

const CLIENT_TYPES = [
    { name: "Sigorta" }, { name: "Doktor" }, { name: "Kurum" },
    { name: "Hasta" }, { name: "Diğer Sağlık Çalışanı" },
];
const SERVICE_TYPES = [
    { name: "Takip (doktor müvekkil)" }, { name: "Lexis Rapor" },
    { name: "Vekaletsiz Takip" }, { name: "Vekaletli Takip" },
    { name: "Vekalet Ücreti Alacağı" }, { name: "Takip (hasta vekilliği)" },
    { name: "Takip (kurum vekilliği)" }, { name: "Danışmanlık" },
    { name: "Takip (sağlık personeli)" },
];

describe("G121 — büro kartında iki yeni kapalı liste alanı", () => {
    it("muvekkil_tipi ve hizmet_turu bureau_type'ın ALTINA girer (büro/hizmet bilgisi tek grupta)", () => {
        const keys = OFFICE_CARD_FIELDS.map(f => f.key);
        expect(keys.indexOf("muvekkil_tipi")).toBe(keys.indexOf("bureau_type") + 1);
        expect(keys.indexOf("hizmet_turu")).toBe(keys.indexOf("bureau_type") + 2);
        expect(OFFICE_CARD_FIELDS.slice(-2).map(f => [f.key, f.label, f.type, f.list])).toEqual([
            ["muvekkil_tipi", "Müvekkil Tipi", "closedList", "client_types"],
            ["hizmet_turu", "Hizmet Türü", "closedList", "service_types"],
        ]);
    });

    it("tıbbi karta ve kanun yolu kartına KONMAZ", () => {
        const digerleri = [...MEDICAL_CARD_FIELDS, ...PROCESS_CARD_FIELDS].map(f => f.key);
        expect(digerleri).not.toContain("muvekkil_tipi");
        expect(digerleri).not.toContain("hizmet_turu");
    });

    it("sabit değer listesi frontend'de TUTULMAZ — yalnız liste anahtarı taşınır", () => {
        const yeniler = OFFICE_CARD_FIELDS.filter(f => f.type === "closedList");
        expect(yeniler.every(f => !("options" in f))).toBe(true);
    });

    it("closedListState yeni listelerde mevcut davranışın eşini verir", () => {
        expect(closedListState("Lexis Rapor", SERVICE_TYPES)).toBe("in-list");
        // tr-TR normalize: büyük/küçük harf ve kenar boşluğu liste dışı saymaz
        expect(closedListState(" LEXİS RAPOR ", SERVICE_TYPES)).toBe("in-list");
        expect(closedListState("Bilinmeyen Hizmet", SERVICE_TYPES)).toBe("off-list");
        expect(closedListState("Diğer Sağlık Çalışanı", CLIENT_TYPES)).toBe("in-list");
        expect(closedListState("Avukat", CLIENT_TYPES)).toBe("off-list");
        // Liste boş doğar (G044 dersi alleged_faults'ta olduğu gibi) — damga yok
        expect(closedListState("Sigorta", [])).toBe("unknown");
        expect(closedListState("Sigorta", undefined)).toBe("unknown");
        expect(closedListState(null, CLIENT_TYPES)).toBe("unknown");
    });

    it("yeni alanlar boşken büro kartı bugünkü gibi görünür (filledFields boş satır basmaz)", () => {
        const data = { acceptance_date: "2026-01-05", bureau_type: "Sigorta", muvekkil_tipi: null, hizmet_turu: undefined };
        expect(filledFields(data, OFFICE_CARD_FIELDS).map(f => f.key)).toEqual(["acceptance_date", "bureau_type"]);
        // Grubun tamamı boşsa kart hiç doğmaz — yeni alanlar bu kuralı bozmaz
        expect(hasAnyValue({ muvekkil_tipi: "", hizmet_turu: "  " }, OFFICE_CARD_FIELDS)).toBe(false);
    });

    it("yeni alanlar doluysa kartta büro özel türünün altında sırayla basılır", () => {
        const data = { bureau_type: "Sigorta", muvekkil_tipi: "Doktor", hizmet_turu: "Lexis Rapor" };
        expect(filledFields(data, OFFICE_CARD_FIELDS).map(f => f.key))
            .toEqual(["bureau_type", "muvekkil_tipi", "hizmet_turu"]);
        // Yalnız hizmet türü dolu (aktarım partiyle geldi) → kart yalnız onu basar
        expect(filledFields({ hizmet_turu: "Danışmanlık" }, OFFICE_CARD_FIELDS).map(f => f.key))
            .toEqual(["hizmet_turu"]);
    });

    it("takip paneli taslağıyla kesişmez — bir kavram tek ekranda (G074 kuralı)", () => {
        expect(TRACKING_DRAFT_KEYS).not.toContain("muvekkil_tipi");
        expect(TRACKING_DRAFT_KEYS).not.toContain("hizmet_turu");
    });
});
