// Dava takip paneli — panel geneli TEK taslak (Faz 1).
//
// Panelin üç ayrı kayıt yolu (aşama alanları, dosya son durumu, aşama geçişi)
// tek taslakta birleşti: taslak TÜM aşamaların alanlarını + dosya_son_durumu'nu
// kapsar, aşama seçimi taslağı sıfırlamaz. Kaydet yalnız baseline'dan sapan
// alanları PATCH'ler (backend exclude_unset: gönderilmeyen dokunulmaz,
// null gönderilen silinir). Aşama geçişi (case_stage) taslağın DIŞINDA kalır.

export interface FieldDef {
    label: string;
    key: string;
    type: "date" | "text" | "select" | "textarea";
    options?: string[];
    wide?: boolean; // 2 kolon kaplar
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
        { label: "Karar No",            key: "karar_no",            type: "text" },
        { label: "Açıklama",            key: "karar_aciklama",      type: "textarea", wide: true },
    ],
    ISTINAF: [
        { label: "Başvuru Tarihi",  key: "istinaf_basvuru_tarihi",  type: "date" },
        { label: "Mahkeme",         key: "istinaf_mahkemesi",       type: "text", wide: true },
        { label: "Esas No",         key: "istinaf_esas_no",         type: "text" },
        { label: "Karar No",        key: "istinaf_karar_no",        type: "text" },
        { label: "Karar Tarihi",    key: "istinaf_karar_tarihi",    type: "date" },
        { label: "Karar Durumu",    key: "istinaf_karar_durumu",    type: "select", options: ["ONANMADI","BOZULDU","DÜZELTILEREK_ONANMADI","KISMI_BOZMA","FERAGAT","DUSME"] },
        { label: "Tebliğ Tarihi",   key: "istinaf_teblig_tarihi",   type: "date" },
        { label: "Açıklama",        key: "istinaf_karar_aciklama",  type: "textarea", wide: true },
    ],
    TEMYIZ: [
        { label: "Mahkeme",        key: "temyiz_mahkemesi",        type: "text", wide: true },
        { label: "Karar Tarihi",   key: "temyiz_karar_tarihi",     type: "date" },
        { label: "Esas No",        key: "temyiz_esas_no",          type: "text" },
        { label: "Karar No",       key: "temyiz_karar_no",         type: "text" },
        { label: "Tarih Bilgisi",  key: "temyiz_basvuru_tarihi",   type: "date" },
        { label: "Tebliğ Tarihi",  key: "temyiz_teblig_tarihi",    type: "date" },
        { label: "Temyiz Eden",    key: "temyiz_eden_durumu",      type: "text" },
        { label: "Açıklama",       key: "temyiz_karar_aciklama",   type: "textarea", wide: true },
    ],
    KARAR_DUZELTME: [
        { label: "Kararı Durumu",  key: "karar_duzeltme_durumu",        type: "select", options: ["ONANMADI","BOZULDU","DÜZELTILEREK_ONANMADI","FERAGAT","DUSME"] },
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

// Taslağın kapsadığı tüm anahtarlar (aşama alanları + dosya son durumu)
export const TRACKING_DRAFT_KEYS: string[] = [
    ...new Set([
        ...Object.values(STAGE_FIELDS).flat().map(f => f.key),
        "dosya_son_durumu",
    ]),
];

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
