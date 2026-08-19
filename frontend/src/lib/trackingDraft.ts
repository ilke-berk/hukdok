// Dava takip paneli — panel geneli TEK taslak (Faz 1).
//
// Panelin üç ayrı kayıt yolu (aşama alanları, dosya son durumu, aşama geçişi)
// tek taslakta birleşti: taslak TÜM aşamaların alanlarını + dosya_son_durumu'nu
// kapsar, aşama seçimi taslağı sıfırlamaz. Kaydet yalnız baseline'dan sapan
// alanları PATCH'ler (backend exclude_unset: gönderilmeyen dokunulmaz,
// null gönderilen silinir). Aşama geçişi (case_stage) taslağın DIŞINDA kalır.

/** Karar sonucu resmî kapalı listeleri (G060 backend uçları). Dropdown seçenekleri
 *  panelde useConfig üzerinden bu anahtarlarla çözülür — frontend'de sabit değer
 *  listesi tutulmaz (G048 kuralı); liste güncellemesi panelden gelir. */
export type DecisionListKey =
    | "local_decisions"      // Yerel Karar Durumları    → yerel_karar_durumu
    | "appeal_decisions"     // İstinaf Karar Durumları  → istinaf_karar_durumu
    | "cassation_decisions"  // Temyiz Onama Durumları   → temyiz_karar_durumu
    | "revision_decisions";  // Karar Düzeltme Durumları → karar_duzeltme_durumu

export interface FieldDef {
    label: string;
    key: string;
    type: "date" | "text" | "select" | "textarea" | "money";
    options?: string[];
    /** Seçenekleri resmî kapalı listeden alan select (G061). `options` ile birlikte
     *  kullanılmaz — gömülü options yalnız karar_turu/karar_lehine kaba
     *  sınıflandırmalarında kalır (bilinçli AYRI alanlardır, listelere bağlanmaz). */
    optionsFrom?: DecisionListKey;
    wide?: boolean; // 2 kolon kaplar
}

/** Para girişini backend'in kabul ettiği düz sayı string'ine çevirir.
 *  "1.500,25" → "1500.25" · "150.000" → "150000" · "1500.25" → "1500.25".
 *  Geçersiz girdi "" döner (norm → null → alan silinir). Pydantic Optional[float]
 *  yalnız düz "1500.25" biçimini coerce eder; TR biçimi 422 üretirdi. */
export function normalizeMoney(raw: string): string {
    const v = raw.replace(/[₺\s]|TL/gi, "").trim();
    if (!v) return "";
    let out: string;
    if (v.includes(",")) {
        // TR biçimi: nokta binlik, virgül ondalık
        out = v.replace(/\./g, "").replace(",", ".");
    } else if (/^\d{1,3}(\.\d{3})+$/.test(v)) {
        // Yalnız binlik noktalar: "150.000" → "150000"
        out = v.replace(/\./g, "");
    } else {
        out = v;
    }
    return /^\d+(\.\d+)?$/.test(out) ? out : "";
}

export const STAGES = [
    { key: "KARAR",          label: "Yerel Mahkeme", short: "Yerel" },
    { key: "ISTINAF",        label: "İstinaf",       short: "İst." },
    { key: "TEMYIZ",         label: "Temyiz",        short: "Tem." },
    { key: "KARAR_DUZELTME", label: "K.Düzeltme",   short: "K.Düz." },
    { key: "KESINLESME",     label: "Kesinleşme",   short: "Kes." },
    { key: "KAPALI",         label: "Kapalı",        short: "Kap." },
];
export const STAGE_KEYS = STAGES.map(s => s.key);

export const STAGE_FIELDS: Record<string, FieldDef[]> = {
    KARAR: [
        { label: "Karar Tarihi",        key: "karar_tarihi",        type: "date" },
        { label: "Tebliğ Tarihi",       key: "karar_teblig_tarihi", type: "date" },
        { label: "Kesinleşme Tarihi",   key: "kesinlesme_tarihi",   type: "date" },
        { label: "Karar Türü",          key: "karar_turu",          type: "select", options: ["KABUL","RED","KISMI_KABUL","FERAGAT","UZLASMA","DUSME"] },
        { label: "Karar Lehine",        key: "karar_lehine",        type: "select", options: ["LEHINE","ALEYHINE","KISMI"] },
        { label: "Karar Durumu",        key: "yerel_karar_durumu",  type: "select", optionsFrom: "local_decisions" },
        { label: "Karar No",            key: "karar_no",            type: "text" },
        { label: "Hükmedilen Maddi",    key: "hukmedilen_maddi",    type: "money" },
        { label: "Hükmedilen Manevi",   key: "hukmedilen_manevi",   type: "money" },
        { label: "Hükmedilen Toplam",   key: "hukmedilen_toplam",   type: "money" },
        { label: "Açıklama",            key: "karar_aciklama",      type: "textarea", wide: true },
    ],
    ISTINAF: [
        { label: "Başvuru Tarihi",  key: "istinaf_basvuru_tarihi",  type: "date" },
        { label: "Mahkeme",         key: "istinaf_mahkemesi",       type: "text", wide: true },
        { label: "Esas No",         key: "istinaf_esas_no",         type: "text" },
        { label: "Karar No",        key: "istinaf_karar_no",        type: "text" },
        { label: "Karar Tarihi",    key: "istinaf_karar_tarihi",    type: "date" },
        { label: "Karar Durumu",    key: "istinaf_karar_durumu",    type: "select", optionsFrom: "appeal_decisions" },
        { label: "Tebliğ Tarihi",   key: "istinaf_teblig_tarihi",   type: "date" },
        { label: "Açıklama",        key: "istinaf_karar_aciklama",  type: "textarea", wide: true },
    ],
    TEMYIZ: [
        { label: "Mahkeme",        key: "temyiz_mahkemesi",        type: "text", wide: true },
        { label: "Karar Tarihi",   key: "temyiz_karar_tarihi",     type: "date" },
        { label: "Karar Durumu",   key: "temyiz_karar_durumu",     type: "select", optionsFrom: "cassation_decisions" },
        { label: "Esas No",        key: "temyiz_esas_no",          type: "text" },
        { label: "Karar No",       key: "temyiz_karar_no",         type: "text" },
        { label: "Tarih Bilgisi",  key: "temyiz_basvuru_tarihi",   type: "date" },
        { label: "Tebliğ Tarihi",  key: "temyiz_teblig_tarihi",    type: "date" },
        { label: "Temyiz Eden",    key: "temyiz_eden_durumu",      type: "text" },
        { label: "Açıklama",       key: "temyiz_karar_aciklama",   type: "textarea", wide: true },
    ],
    KARAR_DUZELTME: [
        { label: "Kararı Durumu",  key: "karar_duzeltme_durumu",        type: "select", optionsFrom: "revision_decisions" },
        { label: "Esas No",        key: "karar_duzeltme_esas_no",       type: "text" },
        { label: "Karar No",       key: "karar_duzeltme_karar_no",      type: "text" },
        { label: "Tebliğ Tarihi",  key: "karar_duzeltme_teblig_tarihi", type: "date" },
        { label: "Yeni Esas No / Mahkemesi", key: "yeni_esas_no",       type: "text", wide: true },
        { label: "Karar Tarihi",   key: "karar_duzeltme_tarihi",        type: "date" },
        { label: "Açıklama",       key: "karar_duzeltme_aciklama",      type: "textarea", wide: true },
    ],
    KESINLESME: [
        { label: "Kesinleşme Tarihi", key: "kesinlesme_tarihi", type: "date" },
    ],
    KAPALI: [],
};

/**
 * AŞAMADAN BAĞIMSIZ takip alanları (G073 → G074).
 *
 * Arabuluculuk davanın ÖN aşaması, arşiv tarihi KAPANIŞ olayıdır; ikisi de
 * `STAGE_FIELDS`teki bir aşama sekmesine ait değil. Sekmeye gömülemezler,
 * çünkü aşama alanları yalnız "gelinmiş" aşamada (`isReached`) düzenlenebilir
 * ve `case_stage` lokal kopyada 14.345 kartın 14.344'ünde BOŞ — sekmeye
 * konsalar 3.346 dolu arşiv tarihinin hiçbiri düzenlenemezdi. Bu yüzden
 * `dosya_son_durumu` ile aynı yerde, her zaman görünür bloktalar.
 */
export const PANEL_FIELDS: FieldDef[] = [
    { label: "Arabuluculuk No",           key: "arabuluculuk_no",            type: "text" },
    { label: "Arabuluculuk Karar Tarihi", key: "arabuluculuk_karar_tarihi",  type: "date" },
    { label: "Arşiv Tarihi",              key: "arsiv_tarihi",               type: "date" },
];

// Taslağın kapsadığı tüm anahtarlar (aşama alanları + aşamadan bağımsızlar)
export const TRACKING_DRAFT_KEYS: string[] = [
    ...new Set([
        ...Object.values(STAGE_FIELDS).flat().map(f => f.key),
        ...PANEL_FIELDS.map(f => f.key),
        "dosya_son_durumu",
    ]),
];

/**
 * Panel aşama anahtarı → `case_stage_decisions.stage` etiketi (G072 route'u).
 *
 * Tek fark YEREL'dedir: panel tarihsel olarak "KARAR" der, backend "YEREL".
 * `KESINLESME`/`KAPALI` haritada YOKTUR — onlar karar aşaması değil dosya
 * durumudur (`DECISION_STAGES` ONCEKI'yi dışlarken uyguladığı ayrımın aynısı).
 */
export const DECISION_STAGE_BY_PANEL_KEY: Record<string, string> = {
    KARAR: "YEREL",
    ISTINAF: "ISTINAF",
    TEMYIZ: "TEMYIZ",
    KARAR_DUZELTME: "KARAR_DUZELTME",
};

export type TrackingValue = string | null;

export interface TrackingDraft {
    baseline: Record<string, TrackingValue>;
    values: Record<string, TrackingValue>;
}

// Boş string ile null aynı "boş" durumdur; tek forma indirgenir ki
// "" ↔ null farkı sahte dirty üretmesin.
const norm = (v: unknown): TrackingValue => {
    if (v === undefined || v === null || v === "") return null;
    return String(v);
};

export function initTrackingDraft(caseData: Record<string, unknown>): TrackingDraft {
    const baseline: Record<string, TrackingValue> = {};
    for (const k of TRACKING_DRAFT_KEYS) baseline[k] = norm(caseData[k]);
    return { baseline, values: { ...baseline } };
}

export function setDraftField(draft: TrackingDraft, key: string, value: string | null): TrackingDraft {
    return { ...draft, values: { ...draft.values, [key]: norm(value) } };
}

export function dirtyKeys(draft: TrackingDraft): string[] {
    return TRACKING_DRAFT_KEYS.filter(k => draft.values[k] !== draft.baseline[k]);
}

export function isDirty(draft: TrackingDraft): boolean {
    return dirtyKeys(draft).length > 0;
}

/** caseData yenilenince baseline tazelenir; kullanıcının kaydedilmemiş
 *  değişiklikleri (dirty alanlar) KORUNUR — aşama geçişi/refresh veri kaybetmez. */
export function rebaseDraft(draft: TrackingDraft, caseData: Record<string, unknown>): TrackingDraft {
    const fresh = initTrackingDraft(caseData);
    const values = { ...fresh.baseline };
    for (const k of dirtyKeys(draft)) values[k] = draft.values[k];
    return { baseline: fresh.baseline, values };
}

/** Yalnız değişen alanlar; boşaltılan alan null olarak gider (backend siler). */
export function buildPatch(draft: TrackingDraft): Record<string, string | null> {
    const patch: Record<string, string | null> = {};
    for (const k of dirtyKeys(draft)) patch[k] = draft.values[k];
    return patch;
}

/** Başarılı kayıttan sonra: mevcut değerler yeni baseline olur (dirty sıfırlanır). */
export function commitDraft(draft: TrackingDraft): TrackingDraft {
    return { baseline: { ...draft.values }, values: { ...draft.values } };
}
