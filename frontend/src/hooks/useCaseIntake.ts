import { useCallback, useEffect, useRef, useState } from "react";

import {
  analyzeIntakeFile,
  commitIntake,
  keepaliveIntake,
  mergeIntake,
  type CaseIntakeCommitRequest,
  type CommitResult,
  type IntakeExtraction,
  type MergeDraft,
} from "@/lib/caseIntake";

// =====================================================================
// Sihirbaz durum makinesi (Faz 5): upload → analyze → review → result.
// Review adımının form durumu (alan onayları, taraflar, poliçe seçimi)
// CaseIntakeWizard'da yaşar; bu hook analiz kuyruğu + merge + keepalive +
// commit borusunu yönetir.
// =====================================================================

export const MAX_INTAKE_FILES = 15;

/** Kalibrasyon ölçümü: ensemble=3 ile belge başına ~25-30 sn (plan İş Kalemi 2). */
export const ANALYZE_SECONDS_PER_DOC = 30;

export type IntakeStep = "upload" | "analyze" | "review" | "result";

export type IntakeFileStatus = "waiting" | "analyzing" | "done" | "error";

export interface IntakeFile {
  id: string;
  file: File;
  status: IntakeFileStatus;
  /** Analiz sırasında akan son info mesajı (canlı durum satırı). */
  statusMessage: string | null;
  processId: string | null;
  extraction: IntakeExtraction | null;
  error: string | null;
}

let nextFileId = 0;
const makeFileId = () => `intake-${++nextFileId}`;

export function useCaseIntake() {
  const [step, setStep] = useState<IntakeStep>("upload");
  const [files, setFiles] = useState<IntakeFile[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isMerging, setIsMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);
  const [draft, setDraft] = useState<MergeDraft | null>(null);
  const [isCommitting, setIsCommitting] = useState(false);
  const [commitResult, setCommitResult] = useState<CommitResult | null>(null);

  // Sıralı analiz döngüsü iptali (sihirbazdan çıkışta akış durdurulur)
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => abortRef.current?.abort(), []);

  const addFiles = useCallback((incoming: File[]) => {
    setFiles(prev => {
      const room = MAX_INTAKE_FILES - prev.length;
      const fresh = incoming
        .filter(f => !prev.some(p => p.file.name === f.name && p.file.size === f.size))
        .slice(0, Math.max(0, room))
        .map((file): IntakeFile => ({
          id: makeFileId(),
          file,
          status: "waiting",
          statusMessage: null,
          processId: null,
          extraction: null,
          error: null,
        }));
      return [...prev, ...fresh];
    });
  }, []);

  const removeFile = useCallback((id: string) => {
    setFiles(prev => prev.filter(f => f.id !== id));
  }, []);

  const patchFile = (id: string, patch: Partial<IntakeFile>) => {
    setFiles(prev => prev.map(f => (f.id === id ? { ...f, ...patch } : f)));
  };

  /**
   * Adım 2: dosyaları SIRAYLA analiz eder (plan İş Kalemi 2 — backend tek
   * belgelik akış; paralellik Gemini kota/limitine yüklenir). Başarısız belge
   * akışı durdurmaz — merge dışı kalır ama listede kırmızı görünür. Hepsi
   * bitince otomatik merge çağrılır ve review'a geçilir.
   */
  const startAnalysis = useCallback(async (pending: IntakeFile[]) => {
    if (pending.length === 0 || isAnalyzing) return;
    setIsAnalyzing(true);
    setStep("analyze");
    setMergeError(null);

    const controller = new AbortController();
    abortRef.current = controller;

    const analyzed: IntakeFile[] = [];
    for (const item of pending) {
      if (controller.signal.aborted) break;
      patchFile(item.id, { status: "analyzing", statusMessage: "Analiz başlıyor..." });
      try {
        const result = await analyzeIntakeFile(item.file, {
          signal: controller.signal,
          onInfo: message => patchFile(item.id, { statusMessage: message }),
        });
        const done: IntakeFile = {
          ...item,
          status: "done",
          statusMessage: null,
          processId: result.processId,
          extraction: result.extraction,
          error: null,
        };
        analyzed.push(done);
        patchFile(item.id, done);
      } catch (e) {
        if (controller.signal.aborted) break;
        patchFile(item.id, {
          status: "error",
          statusMessage: null,
          error: e instanceof Error ? e.message : "Analiz başarısız.",
        });
      }
    }

    setIsAnalyzing(false);
    if (controller.signal.aborted) return;

    if (analyzed.length === 0) {
      setMergeError("Hiçbir belge analiz edilemedi — dosyaları kontrol edip tekrar deneyin.");
      return;
    }

    setIsMerging(true);
    try {
      const merged = await mergeIntake(
        analyzed.map(f => ({
          process_id: f.processId!,
          filename: f.file.name,
          extraction: f.extraction!,
        })),
      );
      setDraft(merged);
      setStep("review");
    } catch (e) {
      setMergeError(e instanceof Error ? e.message : "Birleştirme başarısız.");
    } finally {
      setIsMerging(false);
    }
  }, [isAnalyzing]);

  /** Merge'i elle tekrar dener (analiz sonuçları durur, yalnız merge koşar). */
  const retryMerge = useCallback(async (analyzedFiles: IntakeFile[]) => {
    const ready = analyzedFiles.filter(f => f.status === "done" && f.processId && f.extraction);
    if (ready.length === 0) return;
    setIsMerging(true);
    setMergeError(null);
    try {
      const merged = await mergeIntake(
        ready.map(f => ({
          process_id: f.processId!,
          filename: f.file.name,
          extraction: f.extraction!,
        })),
      );
      setDraft(merged);
      setStep("review");
    } catch (e) {
      setMergeError(e instanceof Error ? e.message : "Birleştirme başarısız.");
    } finally {
      setIsMerging(false);
    }
  }, []);

  // Review adımı açıkken 10 dk'da bir keepalive — PROCESS_CACHE TTL'i (30 dk)
  // tazelenir ki kullanıcı incelemede oyalansa da commit'te belgeler canlı olsun.
  useEffect(() => {
    if (step !== "review") return;
    const ids = files.filter(f => f.processId).map(f => f.processId!) ;
    if (ids.length === 0) return;
    const tick = () => { keepaliveIntake(ids).catch(() => { /* sessiz — bir sonraki tick dener */ }); };
    const interval = setInterval(tick, 10 * 60 * 1000);
    return () => clearInterval(interval);
  }, [step, files]);

  /**
   * Tek "Kaydet ve Arşivle". 409 (duplicate tracking_no) CommitConflictError
   * olarak fırlar — çağıran (wizard) sequence yenileyip BİR kez otomatik dener
   * (karar 3; 409'da hiçbir belge tüketilmemiştir, retry güvenli — Faz 4).
   */
  const commit = useCallback(async (req: CaseIntakeCommitRequest): Promise<CommitResult> => {
    setIsCommitting(true);
    try {
      const result = await commitIntake(req);
      setCommitResult(result);
      setStep("result");
      return result;
    } finally {
      setIsCommitting(false);
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setStep("upload");
    setFiles([]);
    setIsAnalyzing(false);
    setIsMerging(false);
    setMergeError(null);
    setDraft(null);
    setIsCommitting(false);
    setCommitResult(null);
  }, []);

  return {
    step,
    setStep,
    files,
    addFiles,
    removeFile,
    isAnalyzing,
    startAnalysis,
    isMerging,
    mergeError,
    retryMerge,
    draft,
    isCommitting,
    commit,
    commitResult,
    reset,
  };
}
