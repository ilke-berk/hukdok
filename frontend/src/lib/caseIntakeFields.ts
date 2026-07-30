import type { CommitCaseIn, MergeDraft } from "@/lib/caseIntake";
import { normalizeFileType } from "@/lib/caseIntake";

// =====================================================================
// Sihirbaz review adımının alan sözlüğü (Faz 5).
// Alanlar bu listeden render edilir; alan çıkarmak = enabled:false.
// Çıkarma adayları (klasör/hasar/hukuk no, atama/iş kabul tarihi, hizmet türü,
// büro özel türü) bu listeye HİÇ girmez (plan İş Kalemi 2, karar 8-10).
// NOT: teblig_tarihi merge taslağında var ama CaseCreate'te alanı yok —
// dava kartına yazılamadığından listede değil (takip paneli alanı, Faz 6 adayı).
// =====================================================================

export type IntakeWidget = "text" | "date" | "court" | "select" | "money" | "textarea";

export interface IntakeFieldDef {
  /** CaseCreate / commit case anahtarı */
  key: keyof CommitCaseIn & string;
  /** Merge taslağı fields anahtarı; yoksa AI ön-dolgusu olmayan (elle/priors) alan */
  draftKey?: string;
  /** priors sözlüğündeki anahtar (müvekkil geçmişi ön-dolgu önerisi) */
  priorsKey?: string;
  label: string;
  widget: IntakeWidget;
  required?: boolean;
  enabled: boolean;
}

export const INTAKE_FIELDS: IntakeFieldDef[] = [
  { key: "esas_no",                 draftKey: "esas_no",        label: "Esas No",            widget: "text",     enabled: true },
  { key: "court",                   draftKey: "court",          label: "Mahkeme",            widget: "court",    enabled: true },
  { key: "file_type",               draftKey: "file_type",      priorsKey: "file_type",      label: "Yargı Türü", widget: "select", required: true, enabled: true },
  { key: "sub_type",                                            priorsKey: "sub_type",       label: "Dosya Alt Türü", widget: "select", enabled: true },
  { key: "sub_type_extra",          draftKey: "sub_type_extra", label: "Uzmanlık / Tıbbi İşlem", widget: "text", enabled: true },
  { key: "opening_date",            draftKey: "opening_date",   label: "Dava Açılış Tarihi", widget: "date",     enabled: true },
  { key: "subject",                 draftKey: "subject",        priorsKey: "subject",        label: "Dava Konusu", widget: "textarea", enabled: true },
  { key: "maddi_tazminat",          draftKey: "maddi_tazminat", label: "Maddi Tazminat (₺)", widget: "money",    enabled: true },
  { key: "manevi_tazminat",         draftKey: "manevi_tazminat", label: "Manevi Tazminat (₺)", widget: "money",  enabled: true },
  { key: "responsible_lawyer_name",                             priorsKey: "responsible_lawyer_name", label: "Sorumlu Avukat", widget: "select", required: true, enabled: true },
  { key: "uyap_lawyer_name",                                    label: "UYAP Avukatı",       widget: "select",   enabled: true },
  { key: "notes",                                               label: "Notlar",             widget: "textarea", enabled: true },
];

/** Review'da render edilen (enabled) alanlar. */
export const activeIntakeFields = (): IntakeFieldDef[] =>
  INTAKE_FIELDS.filter(f => f.enabled);

/** Review adımındaki tek alanın durumu. */
export interface IntakeFieldState {
  value: string;        // tüm widget'lar string tutar; commit'te tipe çevrilir
  aiValue: string;      // AI ön-dolgusu (boşsa "") — onay gereksinimi buradan
  approved: boolean;    // onay semantiği: boş olmayan AI değeri tiklenmeli
  touched: boolean;     // kullanıcı düzenledi (düzenlemek otomatik tikler)
}

const draftValueToString = (value: unknown): string => {
  if (value === null || value === undefined) return "";
  return String(value);
};

/**
 * Merge taslağından review alan durumlarını kurar (AI ön-dolgu).
 * file_type PROCESS_MAP sözlüğüne normalize edilir; draftKey'siz alanlar boş
 * başlar (priors önerisi UI'da ayrı rozet olarak gösterilir, ön-dolgu yapılmaz —
 * düşük güvenli öneri onay zorunluluğu doğurmasın).
 */
export function buildFieldStates(draft: MergeDraft): Record<string, IntakeFieldState> {
  const states: Record<string, IntakeFieldState> = {};
  for (const def of activeIntakeFields()) {
    let raw = def.draftKey ? draftValueToString(draft.fields[def.draftKey]?.value) : "";
    if (def.key === "file_type") raw = normalizeFileType(raw) || "";
    states[def.key] = {
      value: raw,
      aiValue: raw,
      approved: raw === "",  // boş AI alanı tik istemez
      touched: false,
    };
  }
  return states;
}

/**
 * Onay kapısı: boş olmayan her alan onaylanmadan Kaydet pasif kalır.
 * (Kullanıcının boşalttığı alan boş kaydedilir ve tik istemez.)
 */
export function fieldApprovalProgress(states: Record<string, IntakeFieldState>): {
  approved: number;
  required: number;
  complete: boolean;
} {
  let approved = 0;
  let required = 0;
  for (const s of Object.values(states)) {
    if (s.value === "") continue; // boş alan onay istemez
    required += 1;
    if (s.approved) approved += 1;
  }
  return { approved, required, complete: approved === required };
}
