import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  analyzeIntakeFile,
  ApplyConflictError,
  applyIntake,
  commitIntake,
  emlSummaryMessage,
  expandEmlFile,
  expandedEmlToFiles,
  keepaliveIntake,
  mergeIntake,
  planIntakeAppend,
  type ApplyResult,
  type CaseIntakeApplyRequest,
  type CaseIntakeCommitRequest,
  type CommitResult,
  type IntakeExtraction,
  type MergeDraft,
} from "@/lib/caseIntake";
import { isEmlFile } from "@/lib/fileValidation";
import {
  clearIntakeDraft,
  loadIntakeDraft,
  markExpiredDocuments,
  type IntakeDraftSnapshot,
  type ReviewSnapshot,
} from "@/lib/intakeDraft";

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

export function useCaseIntake(initialEnrichCaseId: number | null = null) {
  const [step, setStep] = useState<IntakeStep>("upload");
  const [files, setFiles] = useState<IntakeFile[]>([]);
  const [isExpandingEml, setIsExpandingEml] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isMerging, setIsMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);
  const [draft, setDraft] = useState<MergeDraft | null>(null);
  const [isCommitting, setIsCommitting] = useState(false);
  const [commitResult, setCommitResult] = useState<CommitResult | null>(null);
  const [applyResult, setApplyResult] = useState<ApplyResult | null>(null);

  // Faz 7 — zenginleştirme modu: dolu ise merge case_id ile çağrılır ve
  // Kaydet commit yerine apply'a gider. Ref: merge async akışlarında (sıralı
  // analiz sonu / duplicate köprüsü) state bayatlamasın.
  const enrichCaseIdRef = useRef<number | null>(initialEnrichCaseId);
  const [enrichCaseId, setEnrichCaseIdState] = useState<number | null>(initialEnrichCaseId);
  const setEnrichCaseId = useCallback((caseId: number | null) => {
    enrichCaseIdRef.current = caseId;
    setEnrichCaseIdState(caseId);
  }, []);

  // Faz 6.2: yarım kalan taslak (oturum düşmesi / sayfa yenileme sonrası).
  // Açılışta bir kez okunur; kullanıcı "devam et" derse review'a restore edilir.
  const [pendingDraft, setPendingDraft] = useState<IntakeDraftSnapshot | null>(
    () => loadIntakeDraft(),
  );
  const [restoredReview, setRestoredReview] = useState<ReviewSnapshot | null>(null);
  const [isResuming, setIsResuming] = useState(false);

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
        enrichCaseIdRef.current,
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
        enrichCaseIdRef.current,
      );
      setDraft(merged);
      setStep("review");
    } catch (e) {
      setMergeError(e instanceof Error ? e.message : "Birleştirme başarısız.");
    } finally {
      setIsMerging(false);
    }
  }, []);

  /**
   * Duplicate uyarısından "bu davayı zenginleştir" köprüsü: analiz sonuçları
   * korunur, merge hedef davayla yeniden koşar — review "mevcut dava" moduna
   * geçer (draft.mode === "enrich"). Yeni analiz yapılmaz.
   */
  const enrichExisting = useCallback(async (caseId: number) => {
    setEnrichCaseId(caseId);
    await retryMerge(filesRef.current);
  }, [retryMerge, setEnrichCaseId]);

  // Review adımı açıkken 10 dk'da bir keepalive — PROCESS_CACHE TTL'i (30 dk)
  // tazelenir ki kullanıcı incelemede oyalansa da commit'te belgeler canlı olsun.
  // İd kaynağı draft.documents (files DEĞİL): restore edilen taslakta files boş.
  useEffect(() => {
    if (step !== "review" || !draft) return;
    const ids = draft.documents.map(d => d.process_id);
    if (ids.length === 0) return;
    const tick = () => { keepaliveIntake(ids).catch(() => { /* sessiz — bir sonraki tick dener */ }); };
    const interval = setInterval(tick, 10 * 60 * 1000);
    return () => clearInterval(interval);
  }, [step, draft]);

  /**
   * Yarım kalan taslağa devam: önce keepalive ile hangi process_id'lerin hâlâ
   * canlı olduğu öğrenilir; expired dönenler taslakta "yeniden yükle" olarak
   * işaretlenir (commit onları zaten dışarıda bırakır). Ardından review'a geçilir.
   */
  const resumeDraft = useCallback(async () => {
    if (!pendingDraft || isResuming) return;
    setIsResuming(true);
    try {
      let review = pendingDraft.review;
      const ids = pendingDraft.draft.documents.map(d => d.process_id);
      if (ids.length > 0) {
        try {
          const result = await keepaliveIntake(ids);
          review = markExpiredDocuments(review, result.expired);
        } catch {
          // keepalive ulaşılamadı — mevcut expired bayraklarıyla devam;
          // gerçekten ölmüş belgeler commit yanıtında görünür (Faz 4 izolasyonu)
        }
      }
      // Enrich taslağı: hedef dava kimliği taslağın içinden geri yüklenir
      setEnrichCaseId(pendingDraft.draft.case?.id ?? null);
      setDraft(pendingDraft.draft);
      setRestoredReview(review);
      setPendingDraft(null);
      setStep("review");
    } finally {
      setIsResuming(false);
    }
  }, [pendingDraft, isResuming, setEnrichCaseId]);

  const discardDraft = useCallback(() => {
    clearIntakeDraft();
    setPendingDraft(null);
  }, []);

  /**
   * Tek "Kaydet ve Arşivle". 409 (duplicate tracking_no) CommitConflictError
   * olarak fırlar — çağıran (wizard) sequence yenileyip BİR kez otomatik dener
   * (karar 3; 409'da hiçbir belge tüketilmemiştir, retry güvenli — Faz 4).
   */
  const commit = useCallback(async (req: CaseIntakeCommitRequest): Promise<CommitResult> => {
    setIsCommitting(true);
    try {
      const result = await commitIntake(req);
      clearIntakeDraft(); // dava kaydoldu — taslak artık bayat
      setCommitResult(result);
      setStep("result");
      return result;
    } finally {
      setIsCommitting(false);
    }
  }, []);

  /**
   * Enrich modunun tek "Kaydet"i: apply — mevcut davaya kısmi güncelleme.
   * 409 (stale_case): dava review açıkken güncellendi — backend hiçbir alanı
   * yazmamış, hiçbir belgeyi tüketmemiştir. Merge otomatik tazelenir (analiz
   * sonuçları korunur, Gemini'ye gidilmez); review yeni draft'la yeniden
   * kurulur ve kullanıcı farkları tekrar tik'leyip Kaydet'e basar — otomatik
   * yeniden-apply YOK, çakışmada karar daima kullanıcının.
   */
  const apply = useCallback(async (req: CaseIntakeApplyRequest): Promise<ApplyResult> => {
    setIsCommitting(true);
    try {
      const result = await applyIntake(req);
      clearIntakeDraft(); // değişiklikler uygulandı — taslak artık bayat
      setApplyResult(result);
      setStep("result");
      return result;
    } catch (e) {
      if (e instanceof ApplyConflictError) {
        const ready = filesRef.current.filter(f => f.status === "done" && f.processId && f.extraction);
        if (ready.length > 0) {
          toast.warning("Dava bu arada güncellendi — öneriler güncel değerlerle tazeleniyor...", {
            duration: 6000,
          });
          await retryMerge(filesRef.current);
        } else {
          // Restore edilmiş taslak: analiz sonuçları elde yok, re-merge imkânsız
          toast.error("Dava bu ekran açıkken güncellendi", {
            description: "Taslak tazelenemiyor — sihirbazı dava kartından yeniden açın.",
            duration: 8000,
          });
        }
      }
      throw e;
    } finally {
      setIsCommitting(false);
    }
  }, [retryMerge]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    clearIntakeDraft();
    setStep("upload");
    applyFiles(() => []);
    setIsExpandingEml(false);
    setIsAnalyzing(false);
    setIsMerging(false);
    setMergeError(null);
    setDraft(null);
    setRestoredReview(null);
    setIsCommitting(false);
    setCommitResult(null);
    setApplyResult(null);
    // Sihirbaz dava detayından (?enrichCase) açıldıysa mod korunur; duplicate
    // köprüsüyle geçilmişse yeni sihirbaz "yeni dava" moduna döner.
    setEnrichCaseId(initialEnrichCaseId);
  }, [applyFiles, setEnrichCaseId, initialEnrichCaseId]);

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
    apply,
    applyResult,
    enrichCaseId,
    enrichExisting,
    reset,
    pendingDraft,
    isResuming,
    resumeDraft,
    discardDraft,
    restoredReview,
  };
}
