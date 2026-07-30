import { AlertCircle, CheckCircle2, FileText, Loader2, RefreshCw } from "lucide-react";

import { FlowButton, FlowCard } from "@/components/flow/primitives";
import { ANALYZE_SECONDS_PER_DOC, type IntakeFile } from "@/hooks/useCaseIntake";

interface IntakeProgressStepProps {
  files: IntakeFile[];
  isAnalyzing: boolean;
  isMerging: boolean;
  mergeError: string | null;
  onRetryMerge: () => void;
}

/** Sonuç çipleri: esas no / mahkeme / N taraf — satırda hızlı doğrulama için. */
const resultChips = (f: IntakeFile): string[] => {
  const ext = f.extraction;
  if (!ext) return [];
  const chips: string[] = [];
  if (ext.esas_no) chips.push(String(ext.esas_no));
  if (ext.mahkeme) chips.push(String(ext.mahkeme));
  const nParty = ext.taraflar?.length ?? 0;
  if (nParty > 0) chips.push(`${nParty} taraf`);
  if (ext.belge_turu_tahmini) chips.push(String(ext.belge_turu_tahmini));
  return chips;
};

/**
 * Adım 2 — Çıkarım ilerlemesi: dosyalar sırayla analiz edilir; satır başına
 * canlı durum, bitince sonuç çipleri, hatada kırmızı özet (akış devam eder,
 * başarısız belge merge dışı kalır). Hepsi bitince otomatik merge → review.
 */
export function IntakeProgressStep({
  files, isAnalyzing, isMerging, mergeError, onRetryMerge,
}: IntakeProgressStepProps) {
  const doneCount = files.filter(f => f.status === "done").length;
  const errorCount = files.filter(f => f.status === "error").length;
  const remaining = files.filter(f => f.status === "waiting" || f.status === "analyzing").length;

  return (
    <div className="grid gap-5">
      <FlowCard padded={false}>
        <div className="px-5 py-3 border-b border-[var(--border)] flex items-center justify-between">
          <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
            Analiz · <span className="text-[var(--fg)] font-semibold">{doneCount}</span>/{files.length} tamamlandı
            {errorCount > 0 && <span className="text-[var(--brand)]"> · {errorCount} başarısız</span>}
          </span>
          {remaining > 0 && (
            <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
              kalan ≈ {Math.max(1, Math.round((remaining * ANALYZE_SECONDS_PER_DOC) / 60))} dk
            </span>
          )}
        </div>

        <ul className="divide-y divide-[var(--border)]">
          {files.map(f => (
            <li key={f.id} className="px-5 py-3 flex items-start gap-3">
              <span className="mt-0.5 shrink-0">
                {f.status === "analyzing" && <Loader2 className="w-4 h-4 text-[var(--brand)] animate-spin" />}
                {f.status === "done" && <CheckCircle2 className="w-4 h-4 text-emerald-600" strokeWidth={1.8} />}
                {f.status === "error" && <AlertCircle className="w-4 h-4 text-[var(--brand)]" strokeWidth={1.8} />}
                {f.status === "waiting" && <FileText className="w-4 h-4 text-[var(--fg-subtle)]" strokeWidth={1.5} />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] text-[var(--fg)] break-all">{f.file.name}</p>
                {f.status === "analyzing" && f.statusMessage && (
                  <p className="text-[12px] text-[var(--fg-muted)] mt-0.5">{f.statusMessage}</p>
                )}
                {f.status === "waiting" && (
                  <p className="text-[12px] text-[var(--fg-subtle)] mt-0.5">Sırada</p>
                )}
                {f.status === "error" && (
                  <p className="text-[12px] text-[var(--brand)] mt-0.5">
                    Başarısız — bu belge dava taslağına katılmayacak. {f.error}
                  </p>
                )}
                {f.status === "done" && (
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    {resultChips(f).map((chip, i) => (
                      <span
                        key={i}
                        className="inline-flex px-1.5 py-0.5 border border-[var(--border-strong)] bg-[var(--bg-sunken)] font-mono text-[10px] tracking-[0.05em] text-[var(--fg-muted)]"
                      >
                        {chip}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      </FlowCard>

      {isMerging && (
        <FlowCard className="flex items-center gap-3">
          <Loader2 className="w-4 h-4 text-[var(--brand)] animate-spin" />
          <span className="text-[13px] text-[var(--fg-muted)]">
            Belgeler tek dava kartı taslağında birleştiriliyor…
          </span>
        </FlowCard>
      )}

      {!isAnalyzing && !isMerging && mergeError && (
        <FlowCard className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <AlertCircle className="w-4 h-4 text-[var(--brand)] shrink-0" />
            <span className="text-[13px] text-[var(--fg-muted)] break-words">{mergeError}</span>
          </div>
          <FlowButton variant="secondary" size="sm" onClick={onRetryMerge}>
            <RefreshCw className="w-3.5 h-3.5" />
            Birleştirmeyi Tekrar Dene
          </FlowButton>
        </FlowCard>
      )}
    </div>
  );
}
