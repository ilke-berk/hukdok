import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { FlowStageStrip, type FlowStage } from "@/components/flow/primitives";
import { IntakeUploadStep } from "@/components/intake/IntakeUploadStep";
import { IntakeProgressStep } from "@/components/intake/IntakeProgressStep";
import { IntakeReviewStep } from "@/components/intake/IntakeReviewStep";
import { IntakeResultStep } from "@/components/intake/IntakeResultStep";
import { useCaseIntake, type IntakeStep } from "@/hooks/useCaseIntake";
import { useSetPageTitle } from "@/hooks/usePageTitle";

// =====================================================================
// Otonom dava açma sihirbazı (Faz 5): belgeleri tek seferde yükle →
// sistem dava kartını doldurur → tik'lerle onayla → tek "Kaydet ve
// Arşivle" ile dava + belgeler + poliçeler kaydolur.
// =====================================================================

const STAGE_FOR_STEP: Record<IntakeStep, FlowStage> = {
  upload: "upload",
  analyze: "analyze",
  review: "confirm",
  result: "done",
};

const CaseIntakeWizard = () => {
  useSetPageTitle("Belgelerden Dava Aç");
  const navigate = useNavigate();
  const intake = useCaseIntake();

  const filenamesByProcessId = useMemo(() => {
    const map: Record<string, string> = {};
    for (const f of intake.files) {
      if (f.processId) map[f.processId] = f.file.name;
    }
    return map;
  }, [intake.files]);

  const startAnalysis = () => {
    intake.startAnalysis(intake.files.filter(f => f.status === "waiting"));
  };

  // Ayrılma koruması: analiz/review yarıda kapatılırsa emek (ve Gemini
  // çağrıları) çöpe gider — kaydedilmemiş iş varken sekme kapatma/yenileme
  // tarayıcı onayına takılır. SPA içi rota değişimini kapsamaz (duman testi
  // bulgusu 4: oturum düşmesindeki state kaybının kalıcı çözümü Faz 6).
  const hasUnsavedWork = intake.step === "analyze" || intake.step === "review";
  useEffect(() => {
    if (!hasUnsavedWork) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = ""; // eski tarayıcılar için (mesaj metni gösterilmez)
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [hasUnsavedWork]);

  return (
    <div className="grid gap-7">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-[var(--fg-subtle)]">
            02 · Otomatik Dava Açma
          </p>
          <h1 className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium">
            Belgelerden Dava Aç
          </h1>
        </div>
        <button
          type="button"
          onClick={() => navigate("/new-case/form")}
          className="font-mono text-[11px] tracking-[0.1em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] transition-colors"
        >
          Manuel form ile aç →
        </button>
      </div>

      <FlowStageStrip
        active={STAGE_FOR_STEP[intake.step]}
        meta={intake.files.length > 0 ? `${intake.files.length} belge` : undefined}
      />

      {intake.step === "upload" && (
        <IntakeUploadStep
          files={intake.files}
          onAddFiles={intake.addFiles}
          onRemoveFile={intake.removeFile}
          onStart={startAnalysis}
        />
      )}

      {intake.step === "analyze" && (
        <IntakeProgressStep
          files={intake.files}
          isAnalyzing={intake.isAnalyzing}
          isMerging={intake.isMerging}
          mergeError={intake.mergeError}
          onRetryMerge={() => intake.retryMerge(intake.files)}
        />
      )}

      {intake.step === "review" && intake.draft && (
        <IntakeReviewStep
          draft={intake.draft}
          isCommitting={intake.isCommitting}
          onCommit={intake.commit}
        />
      )}

      {intake.step === "result" && intake.commitResult && (
        <IntakeResultStep
          result={intake.commitResult}
          filenames={filenamesByProcessId}
          onRestart={intake.reset}
        />
      )}
    </div>
  );
};

export default CaseIntakeWizard;
