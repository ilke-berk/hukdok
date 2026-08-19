import { describe, expect, it } from "vitest";
import {
    MEDICAL_CARD_FIELDS, PROCESS_CARD_FIELDS, OFFICE_CARD_FIELDS,
    isFilled, hasAnyValue, filledFields, formatCardValue, closedListState,
} from "./caseCardFields";
import { TRACKING_DRAFT_KEYS } from "./trackingDraft";

describe("caseCardFields — alan tanımları (G048)", () => {
    it("beş tıbbi alan TEK grupta toplanır, dağıtılmaz", () => {
        expect(MEDICAL_CARD_FIELDS.map(f => f.key)).toEqual([
            "tibbi_surec", "tibbi_olay", "iddia_edilen_kusur",
            "hastada_olusan_zarar", "uygulanan_yontem",
        ]);
    });

    it("iki kapalı liste alanı serbest metin DEĞİL, backend listesine bağlıdır", () => {
        const closed = [...MEDICAL_CARD_FIELDS, ...PROCESS_CARD_FIELDS]
            .filter(f => f.type === "closedList");
        expect(closed.map(f => [f.key, f.list])).toEqual([
            ["iddia_edilen_kusur", "alleged_faults"],
            ["istinaf_basvuran_taraf", "appealing_parties"],
        ]);
        // Sabit değer listesi frontend'de TUTULMAZ — yalnız liste anahtarı taşınır.
        expect(closed.every(f => !("options" in f))).toBe(true);
    });

    it("iki grup aynı alanı iki kez basmaz", () => {
        const keys = [...MEDICAL_CARD_FIELDS, ...PROCESS_CARD_FIELDS].map(f => f.key);
        expect(new Set(keys).size).toBe(keys.length);
    });
});

describe("caseCardFields — boş alan kartı kirletmez", () => {
    it("null / undefined / boşluk BOŞ sayılır", () => {
        expect(isFilled(null)).toBe(false);
        expect(isFilled(undefined)).toBe(false);
        expect(isFilled("")).toBe(false);
        expect(isFilled("   ")).toBe(false);
    });

    it("0 ve '0' DOLU sayılır — tutar/sayı alanı sıfırken gizlenmez", () => {
        expect(isFilled(0)).toBe(true);
        expect(isFilled("0")).toBe(true);
    });

    it("grubun tamamı boşsa kart basılmaz", () => {
        const bos = { tibbi_surec: null, tibbi_olay: "", iddia_edilen_kusur: undefined };
        expect(hasAnyValue(bos, MEDICAL_CARD_FIELDS)).toBe(false);
        expect(hasAnyValue({ tibbi_olay: "Ameliyat" }, MEDICAL_CARD_FIELDS)).toBe(true);
    });

    it("yalnız dolu alanlar basılır", () => {
        const data = { tibbi_surec: "Doğum", tibbi_olay: null, uygulanan_yontem: "Sezaryen" };
        expect(filledFields(data, MEDICAL_CARD_FIELDS).map(f => f.key))
            .toEqual(["tibbi_surec", "uygulanan_yontem"]);
    });
});

describe("caseCardFields — değer biçimleme", () => {
    it("ISO tarih tr-TR biçimine döner", () => {
        expect(formatCardValue("2026-03-09", "date")).toBe("09.03.2026");
    });

    it("ayrıştırılamayan tarih 'Invalid Date' yerine HAM basılır", () => {
        expect(formatCardValue("belirsiz", "date")).toBe("belirsiz");
    });

    it("metin alanı kırpılır, dönüştürülmez", () => {
        expect(formatCardValue("  Sezaryen  ", "text")).toBe("Sezaryen");
    });
});

describe("caseCardFields — kapalı liste denetimi", () => {
    const parties = [{ name: "Davacı" }, { name: "Davalı" }, { name: "Her İki Taraf" }];

    it("listedeki değer 'in-list'", () => {
        expect(closedListState("Davalı", parties)).toBe("in-list");
    });

    it("büyük/küçük harf ve boşluk farkı liste dışı saymaz (tr-TR)", () => {
        expect(closedListState(" DAVACI ", parties)).toBe("in-list");
    });

    it("listede olmayan aktarım değeri 'off-list' — görünür kalmalı", () => {
        expect(closedListState("Müdahil", parties)).toBe("off-list");
    });

    it("liste BOŞ ise damga vurulmaz — alleged_faults tam olarak boş doğuyor", () => {
        expect(closedListState("Teşhis Hatası", [])).toBe("unknown");
        expect(closedListState("Teşhis Hatası", undefined)).toBe("unknown");
    });

    it("değer boşsa durum sorulmaz", () => {
        expect(closedListState(null, parties)).toBe("unknown");
    });
});

describe("caseCardFields — bir kavram tek ekranda (G073 → G074)", () => {
    const TASINANLAR = ["arabuluculuk_no", "arabuluculuk_karar_tarihi", "arsiv_tarihi"];

    it("takibe taşınan üç alan kart gruplarından ÇIKTI", () => {
        const kartAnahtarlari = [...MEDICAL_CARD_FIELDS, ...PROCESS_CARD_FIELDS, ...OFFICE_CARD_FIELDS]
            .map(f => f.key);
        for (const key of TASINANLAR) expect(kartAnahtarlari).not.toContain(key);
    });

    it("dosya_son_durumu karttan çıktı — panel onu ZATEN yazıyordu", () => {
        expect(OFFICE_CARD_FIELDS.map(f => f.key)).toEqual(["acceptance_date", "bureau_type"]);
    });

    it("kartta yazılabilir alan kalmadı: kart listeleri ile takip taslağının kesişimi BOŞ", () => {
        // Kabul kriterinin mekanik kilidi — aynı alan iki ekranda düzenlenemez.
        const kartAnahtarlari = new Set(
            [...MEDICAL_CARD_FIELDS, ...PROCESS_CARD_FIELDS, ...OFFICE_CARD_FIELDS].map(f => f.key),
        );
        const kesisim = TRACKING_DRAFT_KEYS.filter(k => kartAnahtarlari.has(k));
        expect(kesisim).toEqual([]);
    });

    it("kanun yolu grubu boşalmadı: istinaf_basvuran_taraf kartta kaldı", () => {
        // Takip panelinin yazma yolunda DEĞİL (aşama fotoğrafının hedefi) —
        // "hangisinden düzeltirim" belirsizliği doğurmuyor, bu yüzden kalıyor.
        expect(PROCESS_CARD_FIELDS.map(f => f.key)).toEqual(["istinaf_basvuran_taraf"]);
        expect(TRACKING_DRAFT_KEYS).not.toContain("istinaf_basvuran_taraf");
    });
});
