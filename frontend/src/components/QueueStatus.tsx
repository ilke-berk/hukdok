import { X, CheckCircle2, Loader2, Circle } from "lucide-react";

interface QueueStatusProps {
  totalFiles: number;
  currentIndex: number;
  processedCount: number;
  onRemoveFile?: (index: number) => void;
}

export const QueueStatus = ({ totalFiles, currentIndex, processedCount, onRemoveFile }: QueueStatusProps) => {
  if (totalFiles <= 1) return null;

  const progressPct = totalFiles > 0 ? Math.round((processedCount / totalFiles) * 100) : 0;
  const waiting = Math.max(0, totalFiles - processedCount - (currentIndex >= processedCount ? 1 : 0));

  return (
    <div className="bg-[var(--bg-elevated)] border border-[var(--border)] mb-4">
      <div className="grid grid-cols-[auto_1fr_auto] gap-5 items-center px-5 py-4">
        {/* Büyük sayaç */}
        <div className="flex items-baseline gap-2 shrink-0">
          <span className="font-display text-[44px] font-medium tracking-[-0.02em] leading-none text-[var(--fg)] tabular-nums">
            {currentIndex + 1}
          </span>
          <span className="font-mono text-[14px] text-[var(--fg-subtle)] tabular-nums">
            / {totalFiles}
          </span>
        </div>

        {/* Orta: progress bar + meta */}
        <div className="min-w-0 grid gap-2">
          <div className="flex items-baseline justify-between gap-3">
            <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">
              İşlem Kuyruğu
            </div>
            <div className="font-mono text-[11px] tracking-[0.04em] text-[var(--fg-muted)] tabular-nums">
              %{progressPct}
            </div>
          </div>
          <div className="relative h-1.5 bg-[var(--bg-sunken)] overflow-hidden">
            <span
              className="absolute inset-y-0 left-0 bg-[var(--brand)] transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
            {progressPct < 100 && (
              <span
                className="absolute inset-y-0 bg-[var(--brand)]/30"
                style={{
                  left: `${progressPct}%`,
                  width: "12%",
                  animation: "hk-q-shimmer 1.8s ease-in-out infinite",
                }}
              />
            )}
          </div>
          <div className="flex items-center gap-4 font-mono text-[10px] tracking-[0.04em] text-[var(--fg-muted)]">
            <span className="inline-flex items-center gap-1.5">
              <CheckCircle2 className="w-3 h-3 text-[#2f8a5d]" />
              {processedCount} tamam
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Loader2 className="w-3 h-3 text-[var(--brand)] animate-spin" />
              1 işleniyor
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Circle className="w-3 h-3 text-[var(--fg-subtle)]" />
              {waiting} sırada
            </span>
          </div>
        </div>

        {/* Dot strip */}
        <div className="flex items-center gap-1.5 shrink-0 max-w-[40vw] overflow-x-auto">
          {Array.from({ length: totalFiles }).map((_, i) => {
            const isDone = i < processedCount;
            const isCurrent = i === currentIndex;
            const isFuture = i > currentIndex;
            const removable = isFuture && !!onRemoveFile;

            const dotClass = isDone
              ? "bg-[#2f8a5d]"
              : isCurrent
                ? "bg-[var(--brand)]"
                : "bg-[var(--bg-sunken)] border border-[var(--border-strong)]";

            return (
              <div key={i} className="relative group">
                <div
                  className={`w-2 h-2 rounded-full transition-colors ${dotClass} ${isCurrent ? "animate-pulse" : ""}`}
                  title={
                    isDone ? `${i + 1}. tamamlandı`
                      : isCurrent ? `${i + 1}. işleniyor`
                        : `${i + 1}. sırada`
                  }
                />
                {removable && (
                  <button
                    type="button"
                    onClick={() => onRemoveFile?.(i)}
                    title="Sıradan çıkar"
                    aria-label={`${i + 1}. dosyayı sıradan çıkar`}
                    className="absolute -top-2 -right-2 hidden group-hover:flex items-center justify-center w-3.5 h-3.5 bg-[var(--brand)] text-[var(--brand-fg)] rounded-full"
                  >
                    <X className="w-2 h-2" strokeWidth={2.5} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <style>{`
        @keyframes hk-q-shimmer {
          0%, 100% { opacity: 0.4; transform: translateX(-50%); }
          50% { opacity: 0.8; transform: translateX(0%); }
        }
      `}</style>
    </div>
  );
};
