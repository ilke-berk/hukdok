import { useEffect, useMemo, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { FlowButton, FlowCard, FlowStageStrip, type FlowStage } from "@/components/flow/primitives";
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
  const navigate = useNavigate();
  // Faz 7 — dava detayından giriş: /new-case/auto?enrichCase=<id> sihirbazı
  // "mevcut davayı zenginleştir" modunda açar (merge case_id ile koşar).
  const [searchParams] = useSearchParams();
  const enrichParamRef = useRef<number | null>((() => {
    const raw = searchParams.get("enrichCase");
    const parsed = raw ? Number(raw) : NaN;
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  })());
  const intake = useCaseIntake(enrichParamRef.current);
  const enrichMode = intake.enrichCaseId != null;
  useSetPageTitle(enrichMode ? "Belgeden Doldur / Teyit Et" : "Belgelerden Dava Aç");

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
            {enrichMode ? "02 · Belgeden Doldur / Teyit Et" : "02 · Otomatik Dava Açma"}
          </p>
          <h1 className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium">
            {enrichMode
              ? `Davayı Belgeden Zenginleştir${intake.draft?.case ? ` — ${intake.draft.case.tracking_no}` : ""}`
              : "Belgelerden Dava Aç"}
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

      {intake.step === "upload" && intake.pendingDraft && (
        <FlowCard className="flex items-center justify-between gap-4 flex-wrap border-[var(--brand)]">
          <div>
            <p className="text-[13px] font-medium text-[var(--fg)]">
              Yarım kalan taslak bulundu
              {(() => {
                const t = new Date(intake.pendingDraft.savedAt);
                return isNaN(t.getTime())
                  ? ""
                  : ` (${t.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })})`;
              })()}
            </p>
            <p className="mt-0.5 text-[12px] text-[var(--fg-subtle)]">
              Oturum kesintisinden önce inceleme adımında kalınmıştı — kaldığın
              yerden devam edebilirsin. Süresi dolan belgeler işaretlenir.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <FlowButton size="sm" onClick={intake.resumeDraft} disabled={intake.isResuming}>
              {intake.isResuming ? "Yükleniyor..." : "Devam Et"}
            </FlowButton>
            <FlowButton size="sm" variant="ghost" onClick={intake.discardDraft} disabled={intake.isResuming}>
              At
            </FlowButton>
          </div>
        </FlowCard>
      )}

      {intake.step === "upload" && (
        <IntakeUploadStep
          files={intake.files}
          onAddFiles={intake.addFiles}
          onRemoveFile={intake.removeFile}
          onStart={startAnalysis}
          isExpandingEml={intake.isExpandingEml}
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
          // Mod/hedef değişiminde (duplicate köprüsü → enrich merge) form
          // durumu taslaktan yeniden kurulmalı — key remount'u zorlar.
          key={`${intake.draft.mode ?? "new"}-${intake.draft.case?.id ?? 0}`}
          draft={intake.draft}
          isCommitting={intake.isCommitting}
          onCommit={intake.commit}
          onApply={intake.apply}
          onEnrichExisting={intake.enrichExisting}
          initialReview={intake.restoredReview}
        />
      )}

      {intake.step === "result" && intake.commitResult && (
        <IntakeResultStep
          result={intake.commitResult}
          filenames={filenamesByProcessId}
          onRestart={intake.reset}
        />
      )}

      {intake.step === "result" && intake.applyResult && (
        <IntakeResultStep
          result={{
            case: intake.applyResult.case,
            documents: intake.applyResult.documents,
            policies: intake.applyResult.policies,
          }}
          filenames={filenamesByProcessId}
          onRestart={intake.reset}
          enrich={{
            updatedFields: intake.applyResult.updated_fields,
            addedParties: intake.applyResult.added_parties,
          }}
        />
      )}
    </div>
  );
};

export default CaseIntakeWizard;
