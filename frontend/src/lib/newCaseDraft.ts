import { createDraftStore } from "@/lib/formDraft";

// =====================================================================
// Yeni dava formu taslağı (G004 · sertleştirme 4-C).
//
// NewCase.tsx'te doldurulan uzun form sekme yenilenmesinde/kaza
// navigasyonunda kaybolmasın diye sessionStorage'a alınır.
//
// DİKKAT — ofis numarası (tracking_no) taslakta TAŞINMAZ. Numara sunucudan
// alınan müvekkil sıra numarasına bağlıdır (G002: alınamazsa kayıt bloke);
// saklanan bayat bir numara dolu bir ofis numarasını önerip 409'a düşürürdü.
// Geri yüklemede numara sunucudan YENİDEN üretilir — "taslak veri taşır,
// süreç yeniden koşar" kuralı.
// =====================================================================

export const NEW_CASE_DRAFT_KEY = "hukdok.newcase-draft.v1";

/** Bayat taslak sınırı. sessionStorage zaten sekme ömrüyle sınırlı; bu sınır
 *  günlerce açık kalan bir sekmede dünkü formun dirilmesini engeller. */
export const NEW_CASE_DRAFT_MAX_AGE_MS = 12 * 60 * 60 * 1000; // 12 saat

export const DEFAULT_CASE_STATUS = "DERDEST";
export const DEFAULT_SERVICE_TYPE = "00000";

export interface NewCaseDraftParty {
  name: string;
  role: string;
  category?: string;
  birth_year?: number;
  gender?: string;
  tc_no?: string;
}

export interface NewCaseFormValues {
  fileType: string;
  subType: string;
  subject: string;
  court: string;
  category: string;
  lawyer: string;
  uyapLawyer: string;
  esasNo: string;
  fileOpeningDate: string;
  serviceType: string;
  maddiTazminat: string;
  maneviTazminat: string;
  acceptanceDate: string;
  bureauType: string;
  subTypeExtra: string;
  judicialUnit: string;
  atamaTarihi: string;
  hasarDosyaNo: string;
  hukukNo: string;
  klasorNo2: string;
  notes: string;
}

export interface NewCaseDraftData {
  caseStatus: string;
  formData: NewCaseFormValues;
  selectedLawyers: Array<{ name: string; lawyer_id?: number | null }>;
  clients: NewCaseDraftParty[];
  counterParties: NewCaseDraftParty[];
  thirdParties: NewCaseDraftParty[];
}

/** Boş formun referans değerleri — kirlilik denetimi buna göre yapılır. */
export const EMPTY_NEW_CASE_FORM: NewCaseFormValues = {
  fileType: "",
  subType: "",
  subject: "",
  court: "",
  category: "",
  lawyer: "",
  uyapLawyer: "",
  esasNo: "",
  fileOpeningDate: "",
  serviceType: DEFAULT_SERVICE_TYPE,
  maddiTazminat: "",
  maneviTazminat: "",
  acceptanceDate: "",
  bureauType: "",
  subTypeExtra: "",
  judicialUnit: "",
  atamaTarihi: "",
  hasarDosyaNo: "",
  hukukNo: "",
  klasorNo2: "",
  notes: "",
};

/**
 * "Saklamaya değer bir şey var mı?" — boş satırlar ve varsayılan roller
 * kirlilik saymaz, aksi hâlde sayfayı açıp kapatan kullanıcı her seferinde
 * "yarım kalan form" uyarısı alırdı.
 */
export function isNewCaseDraftDirty(data: NewCaseDraftData): boolean {
  if (data.caseStatus !== DEFAULT_CASE_STATUS) return true;
  if (data.selectedLawyers.length > 0) return true;

  for (const key of Object.keys(EMPTY_NEW_CASE_FORM) as Array<keyof NewCaseFormValues>) {
    if ((data.formData[key] ?? "") !== EMPTY_NEW_CASE_FORM[key]) return true;
  }

  return [...data.clients, ...data.counterParties, ...data.thirdParties].some(
    party => (party.name ?? "").trim() !== "" || (party.tc_no ?? "").trim() !== "",
  );
}

/** Şema iskeleti denetimi — eski/bozuk kayıt sessizce atılsın. */
export function isNewCaseDraftShape(value: unknown): boolean {
  const draft = value as NewCaseDraftData | null;
  return (
    !!draft &&
    typeof draft.caseStatus === "string" &&
    !!draft.formData &&
    typeof draft.formData === "object" &&
    Array.isArray(draft.selectedLawyers) &&
    Array.isArray(draft.clients) &&
    Array.isArray(draft.counterParties) &&
    Array.isArray(draft.thirdParties)
  );
}

export const newCaseDraftStore = createDraftStore<NewCaseDraftData>({
  key: NEW_CASE_DRAFT_KEY,
  version: 1,
  maxAgeMs: NEW_CASE_DRAFT_MAX_AGE_MS,
  isValid: isNewCaseDraftShape,
});
