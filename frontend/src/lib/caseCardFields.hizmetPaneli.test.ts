// G252: "Hizmet Türü" satırı Büro Bilgileri kartından ÇIKTI — hizmet artık müvekkil başına
// kayıttır ve kartta Hizmetler panelinde (CaseHizmetPanel) görünür; aynı bilgiyi iki yerde
// basmak çift gösterim olurdu. Bu dosya o kararı kilitler.
import { describe, expect, it } from "vitest";

import {
    MEDICAL_CARD_FIELDS,
    OFFICE_CARD_FIELDS,
    PROCESS_CARD_FIELDS,
    filledFields,
    hasAnyValue,
} from "./caseCardFields";

describe("caseCardFields — G252 hizmet türü Büro Bilgileri kartında basılmaz", () => {
    it("OFFICE_CARD_FIELDS üç alandır; hizmet_turu yoktur", () => {
        expect(OFFICE_CARD_FIELDS.map(f => f.key)).toEqual(["acceptance_date", "bureau_type", "muvekkil_tipi"]);
        expect(OFFICE_CARD_FIELDS.some(f => f.list === "service_types")).toBe(false);
    });

    it("hiçbir kart grubunda hizmet_turu alanı yok (tek gösterim yeri Hizmetler paneli)", () => {
        const tumu = [...MEDICAL_CARD_FIELDS, ...PROCESS_CARD_FIELDS, ...OFFICE_CARD_FIELDS].map(f => f.key);
        expect(tumu).not.toContain("hizmet_turu");
    });

    it("yalnız hizmet_turu dolu kartta Büro Bilgileri kartı DOĞMAZ", () => {
        const data = { hizmet_turu: "Danışmanlık ; Lexis Rapor" };
        expect(hasAnyValue(data, OFFICE_CARD_FIELDS)).toBe(false);
        expect(filledFields(data, OFFICE_CARD_FIELDS)).toEqual([]);
    });

    it("müvekkil tipi yerinde: büro özel türünün hemen altında, client_types listesinden", () => {
        const keys = OFFICE_CARD_FIELDS.map(f => f.key);
        expect(keys.indexOf("muvekkil_tipi")).toBe(keys.indexOf("bureau_type") + 1);
        expect(OFFICE_CARD_FIELDS.find(f => f.key === "muvekkil_tipi")).toEqual({
            key: "muvekkil_tipi", label: "Müvekkil Tipi", type: "closedList", list: "client_types",
        });
    });
});
