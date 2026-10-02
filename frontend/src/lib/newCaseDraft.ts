import { istekKimligiGecerli, yeniIstekKimligi } from "@/lib/caseNumberUtils";
import { createDraftStore } from "@/lib/formDraft";

// =====================================================================
// Yeni dava formu taslağı (G004 · sertleştirme 4-C).
//
// NewCase.tsx'te doldurulan uzun form sekme yenilenmesinde/kaza
// navigasyonunda kaybolmasın diye sessionStorage'a alınır.
//
// DİKKAT — ofis numarası (tracking_no) taslakta TAŞINMAZ. Numarayı kayıt
// anında SUNUCU verir (G236/G237, karar 023); form yalnız önizleme gösterir
// ve geri yüklemede önizleme yeniden istenir.
//
// İstek kimliği (`istekKimligi`) ise TAŞINIR: taslak, gönderilmiş ama yanıtı
// kaybolmuş bir kaydın devamı olabilir — aynı kimlikle tekrar gönderim ikinci
// kartı açmaz (sunucu ilk kartı `reused: true` ile döndürür). Eski taslakta
// alan yoktur; geri yüklemede yeni kimlik üretilir.
//
// Hizmet (G253): eski 5'li `formData.serviceType` maskesi KALKTI. Hizmet müvekkil
// satırının alanıdır (`clients[i].hizmet_turleri`) ve taslakla taşınır. Eski
// taslaktaki `serviceType` anahtarı okunmaz (kirlilik de saymaz).
// =====================================================================

export const NEW_CASE_DRAFT_KEY = "hukdok.newcase-draft.v1";

/** Bayat taslak sınırı. sessionStorage zaten sekme ömrüyle sınırlı; bu sınır
 *  günlerce açık kalan bir sekmede dünkü formun dirilmesini engeller. */
export const NEW_CASE_DRAFT_MAX_AGE_MS = 12 * 60 * 60 * 1000; // 12 saat

export const DEFAULT_CASE_STATUS = "DERDEST";

export interface NewCaseDraftParty {
  name: string;
  role: string;
  category?: string;
  birth_year?: number;
  gender?: string;
  tc_no?: string;
  /**
   * Yalnız müvekkil satırında (G253): kullanıcının AÇIK hizmet seçimi (`service_types`
   * adları). Alan yoksa seçiciye dokunulmamıştır — ekran kategoriye göre ön seçim
   * gösterir (`lib/muvekkilHizmetleri.etkinHizmetler`).
   */
  hizmet_turleri?: string[];
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
  /** Kayıt isteğinin kimliği (UUID) — kirlilik SAYILMAZ; eski taslakta yoktur. */
  istekKimligi?: string;
}

/**
 * Geri yüklenen taslağın istek kimliği: taslakta geçerli bir UUID varsa O
 * kullanılır (yarım kalan gönderimin devamı), yoksa/bozuksa `uret()` ile yenisi.
 */
export function taslakIstekKimligi(
  data: Pick<NewCaseDraftData, "istekKimligi"> | null | undefined,
  uret: () => string = yeniIstekKimligi,
): string {
  return istekKimligiGecerli(data?.istekKimligi) ? data.istekKimligi : uret();
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

  // G253: müvekkil satırında seçilmiş hizmet de saklamaya değer (ad henüz yazılmamış olsa bile).
  if (data.clients.some(client => (client.hizmet_turleri ?? []).length > 0)) return true;

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
