import { areDraftsSuppressed } from "@/lib/formDraft";
import type { MergeDraft } from "@/lib/caseIntake";
import type { IntakeFieldState } from "@/lib/caseIntakeFields";

// =====================================================================
// Sihirbaz taslak dayanıklılığı (Faz 6.2 katman 2).
// Review form durumu sessionStorage'a debounce'lu yazılır; oturum düşmesi
// (logout redirect) veya sayfa yenilemede sihirbaz açılışında "yarım kalan
// taslak bulundu — devam et / at" teklif edilir.
// KVKK: sessionStorage sekme kapanınca ölür; kalıcı localStorage KULLANILMAZ.
// DİKKAT: process_id'ler PROCESS_CACHE TTL'ine bağlı (30 dk, keepalive'lı) —
// restore'da keepalive koşulur, expired dönen belgeler "yeniden yükle" olarak
// işaretlenir (markExpiredDocuments).
// =====================================================================

export const INTAKE_DRAFT_KEY = "hukdok.intake-draft.v1";

/** ReviewParty'nin id'siz hali — id'ler oturuma özgü sayaçtan geldiği için
 *  saklanmaz, restore'da taze üretilir. */
export interface DraftParty {
  name: string;
  role: string;
  party_type: "CLIENT" | "COUNTER" | "THIRD";
  tc_no: string;
  client_id: number | null;
  matchName: string | null;
  matchCategory: string | null;
  approved: boolean;
  fromDraft: boolean;
  // Faz 7 — enrich modu: davada zaten kayıtlı tarafın id'si (restore'da korunur)
  existingId?: number | null;
}

export interface DraftDocument {
  process_id: string;
  filename: string;
  newName: string;
  code: string;
  ozet: string;
  expired: boolean;
}

/** IntakeReviewStep form durumunun serileştirilebilir anlık görüntüsü. */
export interface ReviewSnapshot {
  fieldStates: Record<string, IntakeFieldState>;
  parties: DraftParty[];
  serviceMask: string;
  selectedLawyers: Array<{ name: string; lawyer_id?: number | null }>;
  trackingNo: string;
  selectedPolicies: Record<string, boolean>;
  documents: DraftDocument[];
  sendEmail: boolean;
  emailTo: string[];
}

export interface IntakeDraftSnapshot {
  version: 1;
  savedAt: string; // ISO — teklif ekranında "HH:mm" olarak gösterilir
  draft: MergeDraft;
  review: ReviewSnapshot;
}

const getStorage = (): Storage | null => {
  try {
    return window.sessionStorage;
  } catch {
    return null; // storage erişimi engelli (gizli mod kısıtı vb.) — taslak özelliği sessizce devre dışı
  }
};

export function saveIntakeDraft(draft: MergeDraft, review: ReviewSnapshot): void {
  // Çıkış bastırması (G004 denetim düzeltmesi): sihirbaz da pagehide'da flush
  // eder (IntakeReviewStep) ve taslağı tc_no taşır — logoutRedirect'in
  // tetiklediği flush, clearAppStorage'ın sildiği taslağı geri yazmasın.
  // (Oturum düşmesi 401 bayrağı KURMAZ; o flush bilinçli özellik, aynen çalışır.)
  if (areDraftsSuppressed()) return;
  const storage = getStorage();
  if (!storage) return;
  const snapshot: IntakeDraftSnapshot = {
    version: 1,
    savedAt: new Date().toISOString(),
    draft,
    review,
  };
  try {
    storage.setItem(INTAKE_DRAFT_KEY, JSON.stringify(snapshot));
  } catch {
    // kota dolu vb. — taslak kaydı best-effort, akışı asla kırmaz
  }
}

export function loadIntakeDraft(): IntakeDraftSnapshot | null {
  const storage = getStorage();
  if (!storage) return null;
  const raw = storage.getItem(INTAKE_DRAFT_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as IntakeDraftSnapshot;
    if (
      parsed?.version !== 1 ||
      !parsed.draft?.documents ||
      !parsed.review?.fieldStates ||
      !Array.isArray(parsed.review.parties) ||
      !Array.isArray(parsed.review.documents)
    ) {
      storage.removeItem(INTAKE_DRAFT_KEY); // şema uyuşmazlığı → bayat taslak atılır
      return null;
    }
    return parsed;
  } catch {
    storage.removeItem(INTAKE_DRAFT_KEY);
    return null;
  }
}

export function clearIntakeDraft(): void {
  getStorage()?.removeItem(INTAKE_DRAFT_KEY);
}

/** Keepalive'dan expired dönen process_id'leri taslakta işaretler (saf). */
export function markExpiredDocuments(
  review: ReviewSnapshot,
  expiredIds: string[],
): ReviewSnapshot {
  if (expiredIds.length === 0) return review;
  const expired = new Set(expiredIds);
  return {
    ...review,
    documents: review.documents.map(d =>
      expired.has(d.process_id) ? { ...d, expired: true } : d,
    ),
  };
}

// G004: `debounce` sayfadan bağımsız taslak motoruna (formDraft.ts) taşındı —
// tek kopya kalsın diye buradan yeniden dışa veriliyor (mevcut çağıranlar bozulmaz).
export { debounce } from "@/lib/formDraft";
export type { DebouncedFn } from "@/lib/formDraft";
