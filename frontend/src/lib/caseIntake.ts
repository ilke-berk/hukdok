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

// --- Expand (.eml) -----------------------------------------------------
// Tek .eml → gövde sanal belge (PDF) + izinli ekler. Parçalar normal dosya
// gibi listeye eklenir; .eml'in kendisi listeye girmez ve arşivlenmez.
// Backend sözleşmesi: POST /api/case-intake/expand-eml (routes/case_intake.py).

export interface EmlExpandedPart {
  filename: string;
  data_b64: string;
}

export interface EmlSkippedPart {
  filename: string;
  reason: string;
}

export interface EmlExpandResult {
  body: EmlExpandedPart | null;
  attachments: EmlExpandedPart[];
  skipped: EmlSkippedPart[];
}

export async function expandEmlFile(file: File): Promise<EmlExpandResult> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.fetch("/api/case-intake/expand-eml", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* gövde JSON değilse statusText kalır */ }
    throw new Error("E-posta açılamadı: " + detail);
  }
  return await response.json() as EmlExpandResult;
}

// Uzantı → MIME eşlemesi (base64 parçadan File üretirken; backend zaten
// beyaz liste dışını elemiştir, bilinmeyen uzantı octet-stream kalır).
const EXT_MIME: Record<string, string> = {
  ".pdf": "application/pdf",
  ".doc": "application/msword",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".xls": "application/vnd.ms-excel",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".tif": "image/tiff",
  ".tiff": "image/tiff",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".udf": "application/octet-stream",
};

export function mimeFromFilename(filename: string): string {
  const name = filename.toLowerCase();
  const hit = Object.keys(EXT_MIME).find(ext => name.endsWith(ext));
  return hit ? EXT_MIME[hit] : "application/octet-stream";
}

export function base64ToFile(dataB64: string, filename: string): File {
  const binary = atob(dataB64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new File([bytes], filename, { type: mimeFromFilename(filename) });
}

/** Expand yanıtındaki parçaları (gövde önde) File nesnelerine çevirir. */
export function expandedEmlToFiles(result: EmlExpandResult): File[] {
  const parts = [...(result.body ? [result.body] : []), ...result.attachments];
  return parts.map(p => base64ToFile(p.data_b64, p.filename));
}

/**
 * Toast özeti: "E-posta açıldı: gövde + 5 ek eklendi, 2 parça atlandı (inline görsel)".
 * overflow: MAX_INTAKE_FILES nedeniyle listeye sığmayan parça sayısı.
 */
export function emlSummaryMessage(result: EmlExpandResult, overflow = 0): string {
  const added: string[] = [];
  if (result.body) added.push("gövde");
  if (result.attachments.length > 0) added.push(`${result.attachments.length} ek`);
  let msg = added.length > 0
    ? `E-posta açıldı: ${added.join(" + ")} eklendi`
    : "E-posta açıldı: eklenebilir parça bulunamadı";
  if (result.skipped.length > 0) {
    const reasons = [...new Set(result.skipped.map(s => s.reason))].join(", ");
    msg += `, ${result.skipped.length} parça atlandı (${reasons})`;
  }
  if (overflow > 0) {
    msg += ` — ${overflow} parça belge sınırına sığmadı`;
  }
  return msg;
}

/**
 * Listeye ekleme planı (saf): ad+boyut dedup + MAX_INTAKE_FILES tavanı.
 * Taşan parçalar overflow olarak döner — sığan kadarı eklenir (plan B2).
 */
export function planIntakeAppend(
  existing: { name: string; size: number }[],
  incoming: File[],
  max: number,
): { accepted: File[]; overflow: number } {
  const seen = new Set(existing.map(p => `${p.name}|${p.size}`));
  const unique: File[] = [];
  for (const f of incoming) {
    const key = `${f.name}|${f.size}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(f);
  }
  const room = Math.max(0, max - existing.length);
  return { accepted: unique.slice(0, room), overflow: Math.max(0, unique.length - room) };
}

// --- Merge -------------------------------------------------------------

export interface MergeFieldCandidate {
  value: unknown;
  count: number;
  sources: string[];
}

// Faz 7 — zenginleştirme modunda alan başına durum (annotate_enrich_status):
// fill: dava alanı boş + belgede değer var; confirm: dolu + aynı;
// conflict: dolu + farklı; keep: dolu + belge önerisi yok.
export type EnrichStatus = "fill" | "confirm" | "conflict" | "keep";

export interface MergeFieldEnrich {
  status: EnrichStatus;
  current: unknown;                   // kayıtlı davadaki mevcut değer
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
  enrich?: MergeFieldEnrich;          // yalnız enrich modunda
}

/** Kayıtlı dava kaynaklı adayın sources etiketi (backend SAVED_CASE_SOURCE). */
export const SAVED_CASE_SOURCE = "kayıtlı dava";

// merge_fields çıktı anahtarları (backend services/case_intake.py)
// judicial_unit: mahkemeden türetilir (route 4b); hasar/hukuk no: atama yazısından
export type MergeFieldKey =
  | "esas_no" | "court" | "file_type" | "teblig_tarihi" | "sub_type_extra"
  | "subject" | "maddi_tazminat" | "manevi_tazminat" | "opening_date"
  | "judicial_unit" | "hasar_dosya_no" | "hukuk_no";

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

export interface MergePartyExisting {
  case_party_id: number;
  name: string;               // davadaki kayıtlı yazım
  role: string | null;
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
  // Enrich modu: davada zaten kayıtlı tarafla eşleşme (yalnız EKLEME önerilir)
  existing?: MergePartyExisting | null;
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

/** Enrich modunda hedef davanın özeti (merge yanıtındaki case bloğu). */
export interface MergeCaseSummary {
  id: number;
  tracking_no: string;
  esas_no: string | null;
  court: string | null;
  status: string;
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
  // Faz 7: "new" = açılış sihirbazı, "enrich" = mevcut davayı doldur/teyit
  mode?: "new" | "enrich";
  case?: MergeCaseSummary | null;
}

export interface MergeDocumentIn {
  process_id: string;
  filename: string;
  extraction: IntakeExtraction;
}

export async function mergeIntake(
  documents: MergeDocumentIn[],
  caseId?: number | null,
): Promise<MergeDraft> {
  const response = await apiClient.fetch("/api/case-intake/merge", {
    method: "POST",
    body: JSON.stringify({ documents, ...(caseId != null ? { case_id: caseId } : {}) }),
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
  judicial_unit?: string | null;
  hasar_dosya_no?: string | null;
  hukuk_no?: string | null;
  klasor_no_2?: string | null;
  acceptance_date?: string | null;
  bureau_type?: string | null;
  atama_tarihi?: string | null;
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
  case: {
    id: number;
    tracking_no: string;
    /** Sunucu kararı: zorunlu alanlar tamsa DERDEST, eksikse DANIŞ */
    status?: string;
    missing_required_fields?: { field: string; label: string }[];
  };
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

// --- Apply (Faz 7 — zenginleştirme modu) -------------------------------
// Backend sözleşmesi: POST /api/case-intake/apply (schemas_intake.py).
// fields yalnız tik'lenen (uygulanacak) alanları içerir — gönderilmeyen alan
// davada DOKUNULMAZ, null gönderilen SİLİNİR (exclude_unset semantiği).

export interface CaseIntakeApplyRequest {
  case_id: number;
  fields: Record<string, string | number | null>;
  parties: CommitCasePartyIn[];         // yalnız EKLENECEK taraflar
  documents: CommitDocumentIn[];
  policies: CommitPolicyIn[];
  options: { send_email: boolean; email_to: string[] };
}

export interface ApplyUpdatedField {
  field: string;
  old: string | null;
  new: string | null;
}

export interface ApplyResult {
  case: { id: number; tracking_no: string };
  updated_fields: ApplyUpdatedField[];
  added_parties: string[];
  documents: CommitDocumentResult[];
  policies: { saved: number; skipped: number; error?: string };
}

export async function applyIntake(req: CaseIntakeApplyRequest): Promise<ApplyResult> {
  const response = await apiClient.fetch("/api/case-intake/apply", {
    method: "POST",
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* gövde JSON değilse statusText kalır */ }
    throw new Error("Güncelleme başarısız: " + detail);
  }
  return await response.json() as ApplyResult;
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
