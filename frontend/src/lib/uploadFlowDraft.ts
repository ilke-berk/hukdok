import { createDraftStore } from "@/lib/formDraft";

// =====================================================================
// Belge yükleme akışı taslağı (G004 · sertleştirme 4-C, Index.tsx).
//
// NE SAKLANIR: kullanıcının EMEK verdiği bağlam — seçtiği belge türü, bağladığı
// dava ve (yalnız şeritte göstermek için) dosya adı.
//
// NE SAKLANMAZ ve NEDEN:
//  - `process_id`: PROCESS_CACHE TTL'ine (30 dk, keepalive'lı) bağlı. Bayat bir
//    id ile /confirm çağırmak ya "süreç bulunamadı" hatası verir ya da başka bir
//    belgeye ait kayda yazar. Taslak VERİ taşır; analiz YENİDEN koşar.
//  - `File` objesi: serileştirilemez. Kullanıcı belgeyi yeniden seçer; şerit
//    hangi dosyayı seçmesi gerektiğini adıyla hatırlatır.
//  - Analiz sonucu (`analysisData`): process_id'siz kullanılamaz, üstelik
//    belgenin AI özeti/tarafları KVKK açısından gereksiz yere saklanır.
//  - "Belge kime ait" (`selectedPartyId`): Index.tsx'te bağlı dava değişince
//    bu seçimi BİLEREK sıfırlayan bir effect var (önceki dosyanın müvekkili
//    sıradakine sızmasın diye). Taslaktan geri yüklenen seçim o effect
//    tarafından anında silinirdi — saklanmıyor, kullanıcı tek tıkla seçer.
// =====================================================================

export const UPLOAD_FLOW_DRAFT_KEY = "hukdok.upload-flow-draft.v1";

/** Yarım kalan yükleme bağlamı için makul sınır: bir çalışma seansı. */
export const UPLOAD_FLOW_DRAFT_MAX_AGE_MS = 2 * 60 * 60 * 1000; // 2 saat

export interface UploadFlowLinkedCase {
  id: number;
  tracking_no: string;
  esas_no?: string;
  court?: string;
}

export interface UploadFlowDraftData {
  docType: string;
  /** Yalnız kullanıcıya hatırlatma amaçlı; dosya içeriği saklanmaz. */
  filename: string | null;
  linkedCase: UploadFlowLinkedCase | null;
}

/** Belge türü ya da dava bağlantısı seçilmişse geri yüklemeye değer. */
export function isUploadFlowDraftDirty(data: UploadFlowDraftData): boolean {
  return data.docType.trim() !== "" || data.linkedCase !== null;
}

export function isUploadFlowDraftShape(value: unknown): boolean {
  const draft = value as UploadFlowDraftData | null;
  if (!draft || typeof draft.docType !== "string") return false;
  if (draft.linkedCase !== null && typeof draft.linkedCase?.id !== "number") return false;
  return true;
}

export const uploadFlowDraftStore = createDraftStore<UploadFlowDraftData>({
  key: UPLOAD_FLOW_DRAFT_KEY,
  version: 1,
  maxAgeMs: UPLOAD_FLOW_DRAFT_MAX_AGE_MS,
  isValid: isUploadFlowDraftShape,
});
