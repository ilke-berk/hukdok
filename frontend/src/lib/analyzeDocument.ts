import { apiClient } from "@/lib/api";

// Ortak tipler — hem tek-dosya akışı (Index) hem toplu hazırlık tezgâhı
// (BulkUploadWorkbench) bu tipleri paylaşır.
export interface SuggestedCase {
  case_id: number;
  tracking_no: string;
  esas_no: string;
  court: string;
  responsible_lawyer_name: string;
  status: string;
  score: number;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  match_reasons: string[];
  all_candidates: SuggestedCase[];
  karsi_taraf?: string;
  counter_parties?: string[];
  client_parties?: string[];
  parties?: { id?: number; name?: string; role?: string; party_type?: string; client_id?: number; birth_year?: number; gender?: string }[];
  matched_doc_names?: string[];
}

export interface AnalysisData {
  tarih: string;
  belge_turu_kodu: string;
  muvekkil_kodu: string;
  muvekkil_adi?: string;
  muvekkiller?: string[];
  karsi_taraf?: string;
  suggested_karsi_taraf?: string;       // AI'ın bulduğu karşı taraf (QuickCaseModal için)
  belgede_gecen_isimler: string[];
  esas_no: string;
  durum: string;
  ofis_dosya_no: string;
  yedek1: string;
  yedek2: string;
  ozet: string;
  generated_filename: string;
  hash: string;
  court?: string;                          // Mahkeme adı (QuickCaseModal için)
  suggested_case?: SuggestedCase | null;
  sonraki_durusma_tarihi?: string;
  sonraki_durusma_saati?: string;
}

export interface AnalyzeResult {
  analysisData: AnalysisData;
  processId: string | null;
}

// Bilinen stream mesaj tipleri — info/error toast'ları çağıran tarafa bırakılır.
type StreamMessage =
  | { status: "info"; message: string }
  | { status: "error"; message: string }
  | { status: "complete"; process_id?: string; data: Record<string, unknown> };

export interface AnalyzeOptions {
  /** "info" stream mesajları geldiğinde (örn. tekli akışta toast göstermek için). */
  onInfo?: (message: string) => void;
  /** Harici iptal sinyali. Verilmezse 5 dk timeout'lu kendi controller'ı kullanılır. */
  signal?: AbortSignal;
}

// resultData (backend) → AnalysisData. docTypeCode öncelikli (hazırlık ekranından
// gelen tür), yoksa AI'ın bulduğu değere düşülür.
function mapAnalysisData(resultData: Record<string, unknown>, docTypeCode?: string): AnalysisData {
  const r = resultData as Record<string, unknown> & {
    muvekkil_adi?: string;
    suggested_case?: SuggestedCase | null;
  };
  return {
    tarih: (r.tarih as string) || "",
    belge_turu_kodu: docTypeCode || (r.belge_turu_kodu as string) || "",
    muvekkil_kodu: r.muvekkil_adi || "",
    muvekkil_adi: r.muvekkil_adi || "",
    muvekkiller: (r.muvekkiller as string[]) || [],
    karsi_taraf: (r.karsi_taraf as string) || "",
    suggested_karsi_taraf: (r.suggested_karsi_taraf as string) || "",
    belgede_gecen_isimler: (r.belgede_gecen_isimler as string[]) || [],
    esas_no: (r.esas_no as string) || "",
    durum: (r.durum as string) || "G",
    ofis_dosya_no: (r.ofis_dosya_no as string) || "000000000",
    yedek1: "X",
    yedek2: "XX",
    ozet: (r.ozet as string) || "",
    generated_filename: "",
    hash: (r.hash as string) || "",
    court: (r.court as string) || undefined,
    suggested_case: r.suggested_case || null,
    sonraki_durusma_tarihi: (r.sonraki_durusma_tarihi as string) || undefined,
    sonraki_durusma_saati: (r.sonraki_durusma_saati as string) || undefined,
  };
}

/**
 * Tek bir belgeyi backend `/process` ucuna gönderip streaming yanıtı parse eder.
 * `handleAnalyze` ve `preloadNextFile` arasındaki kopya mantığı tek kaynağa toplar.
 *
 * `complete` mesajı gelmezse hata fırlatır (analiz tamamlanamadı).
 */
export async function analyzeDocument(
  file: File,
  docTypeCode?: string,
  options: AnalyzeOptions = {},
): Promise<AnalyzeResult> {
  // Harici signal verilmediyse 5 dk'lık kendi timeout'umuzu kuruyoruz.
  const ownController = options.signal ? null : new AbortController();
  const signal = options.signal ?? ownController!.signal;
  const timeoutId = ownController
    ? setTimeout(() => ownController.abort(), 300000)
    : null;

  try {
    const formData = new FormData();
    formData.append("file", file);
    if (docTypeCode) formData.append("belge_turu_kodu", docTypeCode);

    const response = await apiClient.fetch("/process", {
      method: "POST",
      body: formData,
      signal,
    });

    if (!response.ok) {
      throw new Error("Sunucu hatası: " + response.statusText);
    }
    if (!response.body) throw new Error("ReadableStream not supported");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let analysisData: AnalysisData | null = null;
    let processId: string | null = null;

    while (true) {
      const { value, done } = await reader.read();

      if (value) {
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.trim()) continue;
          let msg: StreamMessage;
          try {
            msg = JSON.parse(line) as StreamMessage;
          } catch (e) {
            console.error("JSON Parse Error on Stream chunk", e);
            continue;
          }

          if (msg.status === "info") {
            options.onInfo?.(msg.message);
          } else if (msg.status === "error") {
            throw new Error(msg.message);
          } else if (msg.status === "complete") {
            if (msg.process_id) processId = msg.process_id;
            analysisData = mapAnalysisData(msg.data, docTypeCode);
          }
        }
      }

      if (done) break;
    }

    if (!analysisData) {
      throw new Error("Analiz tamamlanamadı (yanıt eksik).");
    }

    return { analysisData, processId };
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}
