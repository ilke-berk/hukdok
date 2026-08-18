// trackingDraft — panel geneli tek taslak birim testleri (Faz 1)
import { describe, it, expect } from "vitest";
import {
    STAGE_FIELDS,
    TRACKING_DRAFT_KEYS,
    initTrackingDraft,
    setDraftField,
    dirtyKeys,
    isDirty,
    rebaseDraft,
    buildPatch,
    commitDraft,
    normalizeMoney,
} from "./trackingDraft";

const caseData = {
    karar_tarihi: "2026-01-15",
    karar_no: "2026/12",
    istinaf_mahkemesi: "İstanbul BAM 4. HD",
    dosya_son_durumu: "İstinafta",
};

describe("initTrackingDraft", () => {
    it("tüm taslak anahtarlarını kapsar, eksik/boş değer null olur", () => {
        const d = initTrackingDraft(caseData);
        expect(Object.keys(d.values).sort()).toEqual([...TRACKING_DRAFT_KEYS].sort());
        expect(d.values.karar_tarihi).toBe("2026-01-15");
        expect(d.values.temyiz_esas_no).toBeNull();
        expect(d.values.dosya_son_durumu).toBe("İstinafta");
        expect(isDirty(d)).toBe(false);
    });

    it("dosya_son_durumu taslağın parçası", () => {
        expect(TRACKING_DRAFT_KEYS).toContain("dosya_son_durumu");
    });

    it("case_stage taslağın parçası DEĞİL (aşama geçişi ayrı yol)", () => {
        expect(TRACKING_DRAFT_KEYS).not.toContain("case_stage");
    });

    it("hükmedilen tutarlar taslağın parçası (2026-08-05)", () => {
        expect(TRACKING_DRAFT_KEYS).toContain("hukmedilen_maddi");
        expect(TRACKING_DRAFT_KEYS).toContain("hukmedilen_manevi");
        expect(TRACKING_DRAFT_KEYS).toContain("hukmedilen_toplam");
    });
});

describe("karar durumu alanları — resmî kapalı listeler (G061)", () => {
    const field = (stage: string, key: string) =>
        STAGE_FIELDS[stage].find(f => f.key === key);

    it("dört karar durumu select'i config listesine bağlı, gömülü options taşımaz", () => {
        const bindings: [string, string, string][] = [
            ["KARAR",          "yerel_karar_durumu",    "local_decisions"],
            ["ISTINAF",        "istinaf_karar_durumu",  "appeal_decisions"],
            ["TEMYIZ",         "temyiz_karar_durumu",   "cassation_decisions"],
            ["KARAR_DUZELTME", "karar_duzeltme_durumu", "revision_decisions"],
        ];
        for (const [stage, key, list] of bindings) {
            const f = field(stage, key);
            expect(f, `${stage}.${key} tanımlı olmalı`).toBeDefined();
            expect(f!.type).toBe("select");
            expect(f!.optionsFrom).toBe(list);
            // Eski gömülü diziler ("ONANMADI/BOZULDU/…") kaldırıldı — tek kaynak config
            expect(f!.options).toBeUndefined();
        }
    });

    it("yeni alanlar taslak anahtarlarında — dirty/patch akışına girerler", () => {
        expect(TRACKING_DRAFT_KEYS).toContain("yerel_karar_durumu");
        expect(TRACKING_DRAFT_KEYS).toContain("temyiz_karar_durumu");
        let d = initTrackingDraft(caseData);
        d = setDraftField(d, "yerel_karar_durumu", "Derdest");
        expect(buildPatch(d)).toEqual({ yerel_karar_durumu: "Derdest" });
    });

    it("karar_turu/karar_lehine gömülü options'ları BİREBİR duruyor (bilinçli ayrı kaba alanlar)", () => {
        expect(field("KARAR", "karar_turu")).toEqual({
            label: "Karar Türü", key: "karar_turu", type: "select",
            options: ["KABUL", "RED", "KISMI_KABUL", "FERAGAT", "UZLASMA", "DUSME"],
        });
        expect(field("KARAR", "karar_lehine")).toEqual({
            label: "Karar Lehine", key: "karar_lehine", type: "select",
            options: ["LEHINE", "ALEYHINE", "KISMI"],
        });
    });
});

describe("normalizeMoney", () => {
    it("TR biçimi düz sayıya çevrilir (Pydantic float coercion uyumu)", () => {
        expect(normalizeMoney("1.500,25")).toBe("1500.25");
        expect(normalizeMoney("150.000")).toBe("150000");
        expect(normalizeMoney("1.234.567,89")).toBe("1234567.89");
    });

    it("EN/düz biçim olduğu gibi kalır", () => {
        expect(normalizeMoney("1500.25")).toBe("1500.25");
        expect(normalizeMoney("150000")).toBe("150000");
    });

    it("para birimi ve boşluklar temizlenir", () => {
        expect(normalizeMoney("₺ 150.000")).toBe("150000");
        expect(normalizeMoney("1.500,25 TL")).toBe("1500.25");
    });

    it("geçersiz girdi boş döner (alan silinir, 422 üretmez)", () => {
        expect(normalizeMoney("abc")).toBe("");
        expect(normalizeMoney("")).toBe("");
        expect(normalizeMoney("1,2,3")).toBe("");
    });

    it("money alanı dirty/patch akışına girer", () => {
        let d = initTrackingDraft(caseData);
        d = setDraftField(d, "hukmedilen_maddi", normalizeMoney("1.500,25"));
        expect(dirtyKeys(d)).toEqual(["hukmedilen_maddi"]);
        expect(buildPatch(d)).toEqual({ hukmedilen_maddi: "1500.25" });
    });
});

describe("setDraftField / dirty", () => {
    it("değişiklik dirty yapar, baseline'a dönüş temizler", () => {
        let d = initTrackingDraft(caseData);
        d = setDraftField(d, "karar_no", "2026/99");
        expect(dirtyKeys(d)).toEqual(["karar_no"]);
        d = setDraftField(d, "karar_no", "2026/12");
        expect(isDirty(d)).toBe(false);
    });

    it("boş string null'a normalize edilir — '' ↔ null sahte dirty üretmez", () => {
        let d = initTrackingDraft(caseData);
        d = setDraftField(d, "temyiz_esas_no", "");
        expect(isDirty(d)).toBe(false);
    });

    it("farklı aşamaların alanları aynı taslakta birikir", () => {
        let d = initTrackingDraft(caseData);
        d = setDraftField(d, "karar_no", "2026/99");           // KARAR aşaması
        d = setDraftField(d, "istinaf_esas_no", "2026/500");   // ISTINAF aşaması
        expect(dirtyKeys(d).sort()).toEqual(["istinaf_esas_no", "karar_no"]);
    });
});

describe("buildPatch", () => {
    it("yalnız değişen alanları içerir", () => {
        let d = initTrackingDraft(caseData);
        d = setDraftField(d, "karar_turu", "KABUL");
        expect(buildPatch(d)).toEqual({ karar_turu: "KABUL" });
    });

    it("boşaltılan alan null olarak gider (backend siler)", () => {
        let d = initTrackingDraft(caseData);
        d = setDraftField(d, "karar_tarihi", "");
        expect(buildPatch(d)).toEqual({ karar_tarihi: null });
    });

    it("temiz taslakta boş patch", () => {
        expect(buildPatch(initTrackingDraft(caseData))).toEqual({});
    });
});

describe("rebaseDraft", () => {
    it("refresh temiz alanları günceller, dirty alanları KORUR (veri kaybı bug'ı)", () => {
        let d = initTrackingDraft(caseData);
        d = setDraftField(d, "karar_no", "2026/99");
        // Aşama geçişi sonrası refresh: sunucu istinaf mahkemesini değiştirmiş olsun
        const refreshed = { ...caseData, istinaf_mahkemesi: "Ankara BAM 1. HD" };
        d = rebaseDraft(d, refreshed);
        expect(d.values.istinaf_mahkemesi).toBe("Ankara BAM 1. HD"); // temiz → sunucu değeri
        expect(d.values.karar_no).toBe("2026/99");                    // dirty → korunur
        expect(dirtyKeys(d)).toEqual(["karar_no"]);
    });

    it("sunucu dirty alanla aynı değere gelirse alan temizlenir", () => {
        let d = initTrackingDraft(caseData);
        d = setDraftField(d, "karar_no", "2026/99");
        d = rebaseDraft(d, { ...caseData, karar_no: "2026/99" });
        expect(isDirty(d)).toBe(false);
    });
});

describe("commitDraft", () => {
    it("kayıt sonrası değerler yeni baseline olur", () => {
        let d = initTrackingDraft(caseData);
        d = setDraftField(d, "kesinlesme_tarihi", "2026-08-01");
        d = commitDraft(d);
        expect(isDirty(d)).toBe(false);
        expect(d.values.kesinlesme_tarihi).toBe("2026-08-01");
        expect(buildPatch(d)).toEqual({});
    });
});
