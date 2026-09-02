import { describe, expect, it } from "vitest";
import {
    MEDICAL_CARD_FIELDS, closedListState, filledFields,
    isDocumentationEventCandidate,
} from "./caseCardFields";

/**
 * G105 — belgeleme olayı alanları + "belgeleme olayı olabilir" rozeti.
 * Sözleşme G103 ile ORTAK (dondurulmuş): alan anahtarları olay_turu /
 * hukumdeki_rol, liste anahtarları event_types / judgment_roles; liste uçları
 * alleged_faults biçiminde (code/name/active/sequence) döner — burada mock'u
 * yalnız name taşır, closedListState de yalnız name okur.
 */

const EVENT_TYPES = [
    { name: "Tıbbi Olay" }, { name: "Belgeleme Olayı" }, { name: "Tıbbi + Belgeleme" },
];
const JUDGMENT_ROLES = [
    { name: "Tek Gerekçe" }, { name: "Yan Gerekçe" },
    { name: "Yalnız Saptama" }, { name: "Reddedilmiş İddia" },
];

describe("G105 — iki yeni kapalı liste alanı", () => {
    it("olay_turu ve hukumdeki_rol tıbbi karta beşlinin ALTINA girer (G048: tek grup)", () => {
        expect(MEDICAL_CARD_FIELDS.slice(5).map(f => [f.key, f.label, f.type, f.list])).toEqual([
            ["olay_turu", "Olay Türü", "closedList", "event_types"],
            ["hukumdeki_rol", "Hükümdeki Rol", "closedList", "judgment_roles"],
        ]);
    });

    it("closedListState yeni listelerde mevcut davranışın eşini verir", () => {
        expect(closedListState("Belgeleme Olayı", EVENT_TYPES)).toBe("in-list");
        // tr-TR normalize: büyük/küçük harf ve kenar boşluğu liste dışı saymaz
        expect(closedListState(" TIBBİ OLAY ", EVENT_TYPES)).toBe("in-list");
        expect(closedListState("Bilinmeyen Tür", EVENT_TYPES)).toBe("off-list");
        expect(closedListState("Reddedilmiş İddia", JUDGMENT_ROLES)).toBe("in-list");
        // Liste boş doğar (G044 dersi alleged_faults'ta olduğu gibi) — damga yok
        expect(closedListState("Tek Gerekçe", [])).toBe("unknown");
        expect(closedListState(null, JUDGMENT_ROLES)).toBe("unknown");
    });

    it("yeni alanlar boşken kart bugünkü gibi görünür (filledFields boş satır basmaz)", () => {
        const data = { tibbi_olay: "Ameliyat", olay_turu: null, hukumdeki_rol: undefined };
        expect(filledFields(data, MEDICAL_CARD_FIELDS).map(f => f.key)).toEqual(["tibbi_olay"]);
    });

    it("yeni alanlar doluysa kartta beşlinin altında sırayla basılır", () => {
        const data = { tibbi_olay: "Ameliyat", olay_turu: "Belgeleme Olayı", hukumdeki_rol: "Tek Gerekçe" };
        expect(filledFields(data, MEDICAL_CARD_FIELDS).map(f => f.key))
            .toEqual(["tibbi_olay", "olay_turu", "hukumdeki_rol"]);
    });
});

describe("G105 — 'belgeleme olayı olabilir' rozeti (NULL ≠ 0)", () => {
    it("maddi=0 VE manevi>0 VE olay_turu boş → rozet VAR", () => {
        expect(isDocumentationEventCandidate({
            hukmedilen_maddi: 0, hukmedilen_manevi: 50_000, olay_turu: null,
        })).toBe(true);
        expect(isDocumentationEventCandidate({ hukmedilen_maddi: 0, hukmedilen_manevi: 1 })).toBe(true);
    });

    it("maddi=null/undefined → rozet YOK — NULL ≠ 0, 'girilmedi' reddedilmiş sayılmaz", () => {
        expect(isDocumentationEventCandidate({ hukmedilen_maddi: null, hukmedilen_manevi: 50_000 })).toBe(false);
        expect(isDocumentationEventCandidate({ hukmedilen_manevi: 50_000 })).toBe(false);
    });

    it("olay_turu doluysa rozet KAYBOLUR — kullanıcı sınıflandırmayı yapmıştır", () => {
        expect(isDocumentationEventCandidate({
            hukmedilen_maddi: 0, hukmedilen_manevi: 50_000, olay_turu: "Belgeleme Olayı",
        })).toBe(false);
        // "Tıbbi Olay" seçimi de rozeti düşürür — koşul "boş", "belgeleme değil" DEĞİL
        expect(isDocumentationEventCandidate({
            hukmedilen_maddi: 0, hukmedilen_manevi: 50_000, olay_turu: "Tıbbi Olay",
        })).toBe(false);
        // Yalnız boşluk = boş (isFilled kuralı) → rozet DURUR
        expect(isDocumentationEventCandidate({
            hukmedilen_maddi: 0, hukmedilen_manevi: 50_000, olay_turu: "   ",
        })).toBe(true);
    });

    it("maddi>0 → rozet YOK — maddi talep (kısmen de olsa) kabul edilmiş", () => {
        expect(isDocumentationEventCandidate({ hukmedilen_maddi: 10_000, hukmedilen_manevi: 50_000 })).toBe(false);
    });

    it("manevi 0 / null / yok → rozet YOK — imza 'maddi red + manevi kabul' İKİLİSİDİR", () => {
        expect(isDocumentationEventCandidate({ hukmedilen_maddi: 0, hukmedilen_manevi: 0 })).toBe(false);
        expect(isDocumentationEventCandidate({ hukmedilen_maddi: 0, hukmedilen_manevi: null })).toBe(false);
        expect(isDocumentationEventCandidate({ hukmedilen_maddi: 0 })).toBe(false);
    });
});
