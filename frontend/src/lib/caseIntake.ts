import { apiClient } from "@/lib/api";

// =====================================================================
// Otonom dava açma — sihirbaz API katmanı (Faz 5).
// Backend sözleşmeleri: backend/routes/case_intake.py + schemas_intake.py
// (analyze NDJSON, merge taslağı, keepalive, commit).
// =====================================================================

// --- Analyze -----------------------------------------------------------

export interface IntakeParty {
  ad: string;
  rol: string; // DAVACI|DAVALI|MUDAHIL|IHBAR_OLUNAN|VEKIL|SIGORTALI|SIGORTA_SIRKETI|DIGER
  tc_no?: string | null;
}

// /analyze terminal olayındaki data. Alan seti motora bağlı evrildiğinden
// merge'e AYNEN geri gönderilir (MergeDocumentIn.extraction serbest şekilli) —
// burada yalnız UI'ın okuduğu alanlar tiplenir, gerisi index signature ile taşınır.
export interface IntakeExtraction {
  belge_turu_tahmini?: string | null;
  belge_turu_kodu_tahmini?: string | null;
  belge_tarihi?: string | null;
  mahkeme?: string | null;
  esas_no?: string | null;
  yargi_turu?: string | null;
  dava_konusu?: string | null;
  dava_acilis_tarihi?: string | null;
  taraflar?: IntakeParty[];
  ozet?: string | null;
  [key: string]: unknown;
}

export interface IntakeAnalyzeResult {
  processId: string;
  extraction: IntakeExtraction;
}

type StreamMessage =
  | { status: "info" | "warning"; message: string }
  | { status: "error"; message: string }
  | { status: "complete"; process_id?: string; data: IntakeExtraction };

export interface IntakeAnalyzeOptions {
  /** info/warning stream mesajları — ilerleme satırında canlı durum metni. */
  onInfo?: (message: string) => void;
  signal?: AbortSignal;
}

/**
 * Tek belgeyi /api/case-intake/analyze'a gönderip NDJSON akışını parse eder.
 * analyzeDocument.ts ile aynı akış deseni; terminal "complete" olayı gelmezse
 * hata fırlatır. Tam PDF backend'te PROCESS_CACHE'e girer (TTL 30 dk) —
 * dönen processId merge + keepalive + commit'te kullanılır.
 */
export async function analyzeIntakeFile(
  file: File,
  options: IntakeAnalyzeOptions = {},
): Promise<IntakeAnalyzeResult> {
  const ownController = options.signal ? null : new AbortController();
  const signal = options.signal ?? ownController!.signal;
  const timeoutId = ownController
    ? setTimeout(() => ownController.abort(), 300000)
    : null;

  try {
    const formData = new FormData();
    formData.append("file", file);

    const response = await apiClient.fetch("/api/case-intake/analyze", {
      method: "POST",
      body: formData,
      signal,
    });

    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        if (body?.detail) detail = body.detail;
      } catch { /* gövde JSON değilse statusText kalır */ }
      throw new Error("Sunucu hatası: " + detail);
    }
    if (!response.body) throw new Error("ReadableStream not supported");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let extraction: IntakeExtraction | null = null;
    let processId: string | null = null;

    while (true) {
      const { value, done } = await reader.read();

      if (value) {
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;
          let msg: StreamMessage;
          try {
            msg = JSON.parse(line) as StreamMessage;
          } catch (e) {
            console.error("JSON Parse Error on Stream chunk", e);
            continue;
          }

          if (msg.status === "info" || msg.status === "warning") {
            options.onInfo?.(msg.message);
          } else if (msg.status === "error") {
            throw new Error(msg.message);
          } else if (msg.status === "complete") {
            if (msg.process_id) processId = msg.process_id;
            extraction = msg.data;
          }
        }
      }

      if (done) break;
    }

    if (!extraction || !processId) {
      throw new Error("Analiz tamamlanamadı (yanıt eksik).");
    }
    return { processId, extraction };
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

// --- Merge -------------------------------------------------------------

export interface MergeFieldCandidate {
  value: unknown;
  count: number;
  sources: string[];
}

export interface MergeField {
  value: unknown;
  agreement: number | null;
  confidence: number | null;
  candidates: MergeFieldCandidate[];
  sources: string[];
  // Yalnız bazı alanlarda dolu gelen ekler:
  verified?: boolean | null;          // esas_no doğrulayıcı (Katman 2)
  regex_check?: boolean | null;       // esas_no regex çapraz kontrolü
  arbiter?: { secilen_deger: string; gerekce?: string | null } | null;
  known_court_suggestion?: string;    // court: bilinen yazım önerisi
  derived_from?: string;              // opening_date: "belge_tarihi" türetmesi
}

// merge_fields çıktı anahtarları (backend services/case_intake.py)
export type MergeFieldKey =
  | "esas_no" | "court" | "file_type" | "teblig_tarihi" | "sub_type_extra"
  | "subject" | "maddi_tazminat" | "manevi_tazminat" | "opening_date";

export interface MergeClientMatch {
  client_id: number | null;
  name: string;
  category?: string | null;
  contact_type?: string | null;
  matched_on: string; // tc_no | name_exact | name_fuzzy
  score: number;
}

export interface MergePartyCheckMatch {
  source: string;      // client | case_party
  strength: string;    // certain | probable | possible
  [key: string]: unknown;
}

export interface MergeParty {
  name: string;
  rol: string;
  party_type: "CLIENT" | "COUNTER" | "THIRD";
  tc_no: string | null;
  doc_count: number;
  agreement: number | null;
  sources: string[];
  match: MergeClientMatch | null;
  check?: { conflict: boolean; matches: MergePartyCheckMatch[] };
}

export interface MergePolicy {
  police_no: string | null;
  police_turu: string | null;       // ZORUNLU | TAMAMLAYICI | DIGER
  sigorta_sirketi: string | null;
  baslangic: string | null;         // ISO — commit'te baslangic_tarihi olur
  bitis: string | null;
  retroaktif: string | null;
  sigortali: string | null;
  sigortali_kurum: string | null;
  teminat_limiti: number | null;
  client_id: number | null;
  source: string | null;            // kaynak dosya adı / "kayıtlı poliçe"
  process_id: string | null;
  saved: boolean;                   // true: zaten client_policies'te kayıtlı
  relevant?: boolean;               // dava açılış tarihini kapsayan dönem
}

export interface MergeWarning {
  code: string;
  message: string;
}

export interface MergeDocumentSummary {
  process_id: string;
  filename: string;
  belge_turu_kodu: string | null;
  belge_turu_tahmini: string | null;
  ozet: string | null;
  status: "ok" | "expired";
}

export interface MergeDuplicateCase {
  id: number;
  tracking_no: string;
  esas_no: string | null;
  court: string | null;
  score: number;
  confidence: string;
}

export interface ClientPrior {
  value: string;
  count: number;
  total: number;
}

export interface MergeDraft {
  fields: Record<MergeFieldKey, MergeField> & Record<string, MergeField>;
  parties: MergeParty[];
  policies: MergePolicy[];
  warnings: MergeWarning[];
  documents: MergeDocumentSummary[];
  duplicate_case: MergeDuplicateCase | null;
  // client_id (string) → alan → öneri (file_type/sub_type/responsible_lawyer_name/subject)
  priors: Record<string, Record<string, ClientPrior>>;
}

export interface MergeDocumentIn {
  process_id: string;
  filename: string;
  extraction: IntakeExtraction;
}

export async function mergeIntake(documents: MergeDocumentIn[]): Promise<MergeDraft> {
  const response = await apiClient.fetch("/api/case-intake/merge", {
    method: "POST",
    body: JSON.stringify({ documents }),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* gövde JSON değilse statusText kalır */ }
    throw new Error("Birleştirme başarısız: " + detail);
  }
  return await response.json() as MergeDraft;
}

// --- Keepalive ---------------------------------------------------------

export interface KeepaliveResult {
  refreshed: string[];
  expired: string[];
}

export async function keepaliveIntake(processIds: string[]): Promise<KeepaliveResult> {
  const response = await apiClient.fetch("/api/case-intake/keepalive", {
    method: "POST",
    body: JSON.stringify({ process_ids: processIds }),
  });
  if (!response.ok) throw new Error("Keepalive başarısız: " + response.statusText);
  return await response.json() as KeepaliveResult;
}

// --- Commit ------------------------------------------------------------

export interface CommitDocumentIn {
  process_id: string;
  new_filename: string;
  original_filename?: string | null;
  belge_turu_kodu?: string | null;
  ai_ozet?: string | null;
  esas_no?: string | null;
  muvekkil_adi?: string | null;
}

// backend schemas.ClientPolicyCreate + client_id (CommitPolicyIn)
export interface CommitPolicyIn {
  client_id: number;
  police_no: string | null;
  police_turu: string | null;
  sigorta_sirketi: string | null;
  baslangic_tarihi: string | null;
  bitis_tarihi: string | null;
  retroaktif_tarihi: string | null;
  sigortali_kurum: string | null;
  teminat_limiti: number | null;
  source_document: string | null;
}

export interface CommitCasePartyIn {
  client_id?: number | null;
  name: string;
  role: string;
  party_type: "CLIENT" | "COUNTER" | "THIRD";
  tc_no?: string | null;
}

// schemas.CaseCreate ile aynı anahtarlar (parties/lawyers dahil)
export interface CommitCaseIn {
  tracking_no: string;
  esas_no?: string | null;
  status?: string;
  service_type?: string | null;
  file_type?: string | null;
  sub_type?: string | null;
  subject?: string | null;
  court?: string | null;
  opening_date?: string | null;
  responsible_lawyer_name?: string | null;
  uyap_lawyer_name?: string | null;
  maddi_tazminat?: number | null;
  manevi_tazminat?: number | null;
  sub_type_extra?: string | null;
  notes?: string | null;
  parties: CommitCasePartyIn[];
  lawyers: { lawyer_id?: number | null; name: string }[];
}

export interface CaseIntakeCommitRequest {
  case: CommitCaseIn;
  documents: CommitDocumentIn[];
  policies: CommitPolicyIn[];
  // email_to boş + send_email=true → backend pre-check zarifçe düşer (belge durumu etkilenmez)
  options: { send_email: boolean; email_to: string[] };
}

export interface CommitDocumentResult {
  process_id: string;
  status: "queued" | "failed" | "expired";
  document_id: number | null;
  error_ozet: string | null;
}

export interface CommitResult {
  case: { id: number; tracking_no: string };
  documents: CommitDocumentResult[];
  policies: { saved: number; skipped: number; error?: string };
}

/** 409 duplicate_tracking_no — sihirbaz sequence yenileyip 1 kez otomatik dener. */
export class CommitConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CommitConflictError";
  }
}

export async function commitIntake(req: CaseIntakeCommitRequest): Promise<CommitResult> {
  const response = await apiClient.fetch("/api/case-intake/commit", {
    method: "POST",
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* gövde JSON değilse statusText kalır */ }
    if (response.status === 409) throw new CommitConflictError(detail);
    throw new Error("Kayıt başarısız: " + detail);
  }
  return await response.json() as CommitResult;
}

// --- Saf eşleme yardımcıları (vitest kapsamında) -----------------------

/**
 * Merge poliçe satırı → commit CommitPolicyIn eşlemesi.
 * DİKKAT (Faz 4 devir notu a): merge anahtarları `baslangic/bitis/retroaktif/source`,
 * commit ClientPolicyCreate adları `baslangic_tarihi/bitis_tarihi/retroaktif_tarihi/
 * source_document` — eşleme burada, TEK yerde yapılır.
 * client_id'siz veya zaten kayıtlı (saved=true) poliçe gönderilmez → null.
 */
export function toCommitPolicy(p: MergePolicy): CommitPolicyIn | null {
  if (p.client_id == null || p.saved) return null;
  return {
    client_id: p.client_id,
    police_no: p.police_no,
    police_turu: p.police_turu,
    sigorta_sirketi: p.sigorta_sirketi,
    baslangic_tarihi: p.baslangic,
    bitis_tarihi: p.bitis,
    retroaktif_tarihi: p.retroaktif,
    sigortali_kurum: p.sigortali_kurum,
    teminat_limiti: p.teminat_limiti,
    source_document: p.source,
  };
}

/** Kullanıcının review'da onayladığı poliçelerden commit listesi üretir. */
export function selectCommitPolicies(policies: MergePolicy[]): CommitPolicyIn[] {
  return policies
    .map(toCommitPolicy)
    .filter((p): p is CommitPolicyIn => p !== null);
}

/**
 * Poliçe satırının UI seçim anahtarı (backend _policy_key ile aynı semantik:
 * normalize police_no + dönem başı — aynı poliçenin kopyası tekilleşir).
 */
export function policyKey(p: MergePolicy): string {
  const no = (p.police_no || "").trim().toUpperCase().replace(/\s+/g, " ");
  return `${no}|${p.baslangic || ""}`;
}

/**
 * Çıkarımdaki yargı türünü NewCase'in file_type sözlüğüne (PROCESS_MAP
 * anahtarları) normalize eder. Backend "İdari" döndürebilir, form "İdari Yargı"
 * bekler; bilinmeyen değer olduğu gibi geçer (kullanıcı düzeltir).
 */
export function normalizeFileType(value: string | null | undefined): string | null {
  if (!value) return null;
  const v = value.trim();
  const upper = v.toLocaleUpperCase("tr-TR");
  if (upper.startsWith("İDARİ") || upper.startsWith("IDARI")) return "İdari Yargı";
  const known = ["Hukuk", "Ceza", "İcra", "Arabuluculuk", "Savcılık"];
  const hit = known.find(k => k.toLocaleUpperCase("tr-TR") === upper);
  return hit || v;
}
