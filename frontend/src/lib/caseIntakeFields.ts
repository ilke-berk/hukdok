import type { CommitCaseIn, MergeDraft } from "@/lib/caseIntake";
import { normalizeFileType } from "@/lib/caseIntake";

// =====================================================================
// Sihirbaz review adımının alan sözlüğü (Faz 5).
// Alanlar bu listeden render edilir; alan çıkarmak = enabled:false.
// 2026-08-01 eşitleme: manuel sayfada (NewCase) girilebilen her dava alanı
// sihirbazda da var — karar 8-10 geri alındı (hasar/hukuk no atama yazısından
// AI ile de dolar; klasör no, kabul/atama tarihi, büro türü elle girilir).
// Hizmet Türü alan satırı değildir: IntakeReviewStep'te maske bloğu (NewCase
// deseni), ofis numarasının son bloğunu şekillendirir.
// NOT: teblig_tarihi merge taslağında var ama CaseCreate'te alanı yok —
// dava kartına yazılamadığından listede değil (takip paneli alanı, Faz 6 adayı).
// =====================================================================

export type IntakeWidget = "text" | "date" | "court" | "select" | "combobox" | "money" | "textarea";

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
  /** Review kartındaki bölüm başlığı (ardışık aynı değerler gruplanır) */
  section?: string;
  /** İki sütunlu ızgarada tam satır kaplar (uzun değerli alanlar) */
  wide?: boolean;
}

export const INTAKE_FIELDS: IntakeFieldDef[] = [
  { key: "esas_no",                 draftKey: "esas_no",        label: "Esas No",            widget: "text",     enabled: true, section: "Dosya Kimliği" },
  { key: "court",                   draftKey: "court",          label: "Mahkeme",            widget: "court",    enabled: true, section: "Dosya Kimliği", wide: true },
  { key: "file_type",               draftKey: "file_type",      priorsKey: "file_type",      label: "Yargı Türü", widget: "select", required: true, enabled: true, section: "Dosya Kimliği" },
  // Yargı Birimi: mahkeme adından backend'de türetilir (route 4b), NewCase ile
  // aynı kaynak (courtTypesByParent) sunulur
  { key: "judicial_unit",           draftKey: "judicial_unit",  label: "Yargı Birimi",       widget: "select",   enabled: true, section: "Dosya Kimliği" },
  // Uzmanlık Alanı: NewCase ile aynı — specialties listesi. Etiket 2026-08-12'de
  // düzeldi (FAZ F §1.4 / G044+G048): alan zaten uzmanlık tutuyordu, adı yanıltıcıydı.
  // Kolon adı (`sub_type`) BİLİNÇLİ korundu — değişen yalnız Türkçe ad.
  { key: "sub_type",                                            priorsKey: "sub_type",       label: "Uzmanlık Alanı", widget: "combobox", enabled: true, section: "Dosya Kimliği" },
  // Geçici gizli (2026-08-04): Ek Alt Kırılım dropdown'u güncellenecek, sonra
  // kullanıma açılacak (NewCase'teki blok ve required_fields.py ile birlikte
  // geri al). enabled:false → state kurulmaz; enrich modunda alan davaya
  // dokunmaz, kayıtlı değer korunur.
  { key: "sub_type_extra",          draftKey: "sub_type_extra", label: "Uzmanlık / Tıbbi İşlem", widget: "combobox", enabled: false, section: "Dosya Kimliği" },
  { key: "subject",                 draftKey: "subject",        priorsKey: "subject",        label: "Dava Konusu", widget: "combobox", enabled: true, section: "Dava Bilgileri", wide: true },
  { key: "opening_date",            draftKey: "opening_date",   label: "Dava Açılış Tarihi", widget: "date",     enabled: true, section: "Dava Bilgileri" },
  { key: "maddi_tazminat",          draftKey: "maddi_tazminat", label: "Maddi Tazminat (₺)", widget: "money",    enabled: true, section: "Dava Bilgileri" },
  { key: "manevi_tazminat",         draftKey: "manevi_tazminat", label: "Manevi Tazminat (₺)", widget: "money",  enabled: true, section: "Dava Bilgileri" },
  // Sigorta atama yazısından AI dolabilir; yoksa elle girilir
  { key: "hasar_dosya_no",          draftKey: "hasar_dosya_no", label: "Hasar Dosya No",     widget: "text",     enabled: true, section: "Sigorta & Büro" },
  { key: "hukuk_no",                draftKey: "hukuk_no",       label: "Hukuk No",           widget: "text",     enabled: true, section: "Sigorta & Büro" },
  { key: "klasor_no_2",                                         label: "Klasör No 2 (Eski Sistem)", widget: "text", enabled: true, section: "Sigorta & Büro" },
  { key: "acceptance_date",                                     label: "İş Kabul Tarihi",    widget: "date",     enabled: true, section: "Sigorta & Büro" },
  { key: "atama_tarihi",                                        label: "Atama Tarihi",       widget: "date",     enabled: true, section: "Sigorta & Büro" },
  { key: "bureau_type",                                         label: "Büro Özel Türü",     widget: "select",   enabled: true, section: "Sigorta & Büro" },
  { key: "responsible_lawyer_name",                             priorsKey: "responsible_lawyer_name", label: "Sorumlu Avukat", widget: "select", required: true, enabled: true, section: "Sorumlular & Notlar" },
  { key: "uyap_lawyer_name",                                    label: "UYAP Avukatı",       widget: "select",   enabled: true, section: "Sorumlular & Notlar" },
  { key: "notes",                                               label: "Notlar",             widget: "textarea", enabled: true, section: "Sorumlular & Notlar", wide: true },
];

/** Review'da render edilen (enabled) alanlar. */
export const activeIntakeFields = (): IntakeFieldDef[] =>
  INTAKE_FIELDS.filter(f => f.enabled);

/** Review adımındaki tek alanın durumu. */
export interface IntakeFieldState {
  value: string;        // tüm widget'lar string tutar; commit'te tipe çevrilir
  aiValue: string;      // AI ön-dolgusu (boşsa "") — onay gereksinimi buradan
  approved: boolean;    // onay semantiği: boş olmayan AI değeri tiklenmeli; boş alan tiksiz ve pasif
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
      approved: false,  // boş alan tiksiz başlar; kullanıcı doldurunca otomatik tiklenir
      touched: false,
    };
  }
  return states;
}

/**
 * Onay kapısı: boş olmayan her alan onaylanmadan Kaydet pasif kalır.
 * Zorunlu alanlar (requiredKeys) BOŞKEN de tik ister — kullanıcı "bu bilgi
 * şu anda elimde yok" onayıyla tikler (IntakeFieldRow'daki diyalog).
 * Zorunlu olmayan boş alan onay istemez.
 */
export function fieldApprovalProgress(
  states: Record<string, IntakeFieldState>,
  requiredKeys?: ReadonlySet<string>,
): {
  approved: number;
  required: number;
  complete: boolean;
} {
  let approved = 0;
  let required = 0;
  for (const [key, s] of Object.entries(states)) {
    if (s.value === "" && !requiredKeys?.has(key)) continue; // zorunlu olmayan boş alan onay istemez
    required += 1;
    if (s.approved) approved += 1;
  }
  return { approved, required, complete: approved === required };
}
