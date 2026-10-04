import { Check, Square } from "lucide-react";
import { FlowButton } from "@/components/flow/primitives";
import { URETIM_ASAMALARI, type UretimAsamasi } from "@/types/lexis";

type UretimSeridiProps = {
  /** Süren aşama. */
  asama: UretimAsamasi;
  mesaj: string | null;
  onDurdur: () => void;
};

/** Taslak yazılırken akışın aşamaları: olgular → emsaller → bölümler → muallak → denetim. */
export function UretimSeridi({ asama, mesaj, onDurdur }: UretimSeridiProps) {
  const etkin = URETIM_ASAMALARI.findIndex((a) => a.kod === asama);
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="lexis-uretim-seridi"
      className="flex flex-wrap items-center gap-x-4 gap-y-2 border border-brand/40 bg-[var(--brand-soft)] px-3 py-2"
    >
      <ol className="flex flex-wrap items-center gap-x-1 gap-y-1">
        {URETIM_ASAMALARI.map((a, i) => {
          const gecti = i < etkin;
          const suren = i === etkin;
          return (
            <li key={a.kod} className="flex items-center gap-1">
              <span
                aria-current={suren ? "step" : undefined}
                className={[
                  "inline-flex items-center gap-1 px-1.5 py-0.5 font-mono text-[10px] tracking-[0.16em] uppercase",
                  gecti ? "text-[var(--fg-muted)]" : suren ? "text-[var(--fg)] font-semibold border-b-2 border-[var(--brand)]" : "text-[var(--fg-subtle)]",
                ].join(" ")}
              >
                {gecti ? <Check className="w-3 h-3" strokeWidth={2.2} aria-hidden="true" /> : <span className="tabular-nums">0{i + 1}</span>}
                {a.ad}
              </span>
              {i < URETIM_ASAMALARI.length - 1 && <span className="h-px w-3 bg-[var(--border-strong)]" aria-hidden="true" />}
            </li>
          );
        })}
      </ol>
      <span className="min-w-0 flex-1 text-[12.5px] text-[var(--fg-muted)] truncate">{mesaj ?? "Taslak yazılıyor…"}</span>
      <FlowButton variant="secondary" size="sm" onClick={onDurdur}>
        <Square className="w-3 h-3" aria-hidden="true" />
        Durdur
      </FlowButton>
    </div>
  );
}
