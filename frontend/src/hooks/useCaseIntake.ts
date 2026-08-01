import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  analyzeIntakeFile,
  commitIntake,
  emlSummaryMessage,
  expandEmlFile,
  expandedEmlToFiles,
  keepaliveIntake,
  mergeIntake,
  planIntakeAppend,
  type CaseIntakeCommitRequest,
  type CommitResult,
  type IntakeExtraction,
  type MergeDraft,
} from "@/lib/caseIntake";
import { isEmlFile } from "@/lib/fileValidation";

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
  const [isExpandingEml, setIsExpandingEml] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isMerging, setIsMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);
  const [draft, setDraft] = useState<MergeDraft | null>(null);
  const [isCommitting, setIsCommitting] = useState(false);
  const [commitResult, setCommitResult] = useState<CommitResult | null>(null);

  // Sıralı analiz döngüsü iptali (sihirbazdan çıkışta akış durdurulur)
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => abortRef.current?.abort(), []);

  // Liste mutasyonları ref üzerinden akar: .eml genişletmesi sıralı-async
  // koştuğundan (await'ler arasında state bayatlar) taşma/dedup hesabı her
  // adımda güncel listeyle yapılmalı.
  const filesRef = useRef<IntakeFile[]>([]);
  const applyFiles = useCallback((updater: (prev: IntakeFile[]) => IntakeFile[]) => {
    filesRef.current = updater(filesRef.current);
    setFiles(filesRef.current);
  }, []);

  const makeIntakeFile = (file: File): IntakeFile => ({
    id: makeFileId(),
    file,
    status: "waiting",
    statusMessage: null,
    processId: null,
    extraction: null,
    error: null,
  });

  const fileKeys = () => filesRef.current.map(f => ({ name: f.file.name, size: f.file.size }));

  /**
   * Adım 1: dosya ekleme. .eml'ler önce expand-eml ile parçalara açılır
   * (gövde sanal PDF + izinli ekler); parçalar normal belge gibi listeye
   * girer, .eml'in kendisi GİRMEZ. MAX_INTAKE_FILES kontrolü genişleme
   * SONRASI toplam üzerinden yapılır — taşarsa uyarı + sığan kadarı eklenir.
   */
  const addFiles = useCallback(async (incoming: File[]) => {
    const regular = incoming.filter(f => !isEmlFile(f));
    const emls = incoming.filter(isEmlFile);

    if (regular.length > 0) {
      const plan = planIntakeAppend(fileKeys(), regular, MAX_INTAKE_FILES);
      if (plan.accepted.length > 0) {
        applyFiles(prev => [...prev, ...plan.accepted.map(makeIntakeFile)]);
      }
      if (plan.overflow > 0) {
        toast.warning(`En fazla ${MAX_INTAKE_FILES} belge yüklenebilir — ${plan.overflow} dosya eklenmedi.`);
      }
    }

    if (emls.length === 0) return;
    setIsExpandingEml(true);
    try {
      for (const eml of emls) {
        try {
          const result = await expandEmlFile(eml);
          const plan = planIntakeAppend(fileKeys(), expandedEmlToFiles(result), MAX_INTAKE_FILES);
          if (plan.accepted.length > 0) {
            applyFiles(prev => [...prev, ...plan.accepted.map(makeIntakeFile)]);
          }
          const summary = `${eml.name}: ${emlSummaryMessage(result, plan.overflow)}`;
          if (result.skipped.length > 0 || plan.overflow > 0) toast.warning(summary, { duration: 6000 });
          else toast.success(summary);
        } catch (e) {
          toast.error(
            e instanceof Error ? `${eml.name}: ${e.message}` : `${eml.name} açılamadı.`,
            { duration: 6000 },
          );
        }
      }
    } finally {
      setIsExpandingEml(false);
    }
  }, [applyFiles]);

  const removeFile = useCallback((id: string) => {
    applyFiles(prev => prev.filter(f => f.id !== id));
  }, [applyFiles]);

  const patchFile = (id: string, patch: Partial<IntakeFile>) => {
    applyFiles(prev => prev.map(f => (f.id === id ? { ...f, ...patch } : f)));
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
    applyFiles(() => []);
    setIsExpandingEml(false);
    setIsAnalyzing(false);
    setIsMerging(false);
    setMergeError(null);
    setDraft(null);
    setIsCommitting(false);
    setCommitResult(null);
  }, [applyFiles]);

  return {
    step,
    setStep,
    files,
    addFiles,
    isExpandingEml,
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
