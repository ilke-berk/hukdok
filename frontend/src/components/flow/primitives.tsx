import { ReactNode } from "react";
import { Check, Bot } from "lucide-react";

// ------------------------------------------------------------------
// FlowStageStrip — 4 aşama göstericisi: Yükleme → Analiz → Onay → Tamam
// ------------------------------------------------------------------

export type FlowStage = "upload" | "analyze" | "confirm" | "done";

const STAGES: { id: FlowStage; label: string; index: number }[] = [
  { id: "upload", label: "Yükleme", index: 1 },
  { id: "analyze", label: "Analiz", index: 2 },
  { id: "confirm", label: "Onay", index: 3 },
  { id: "done", label: "Tamamlandı", index: 4 },
];

type FlowStageStripProps = {
  active: FlowStage;
  meta?: ReactNode;
  className?: string;
};

export function FlowStageStrip({ active, meta, className = "" }: FlowStageStripProps) {
  const activeIndex = STAGES.findIndex(s => s.id === active);

  return (
    <div className={`flex items-center justify-between gap-4 ${className}`}>
      <div className="flex items-center gap-2 flex-wrap">
        {STAGES.map((stage, i) => {
          const isPast = i < activeIndex;
          const isActive = i === activeIndex;
          return (
            <div key={stage.id} className="flex items-center gap-2">
              <div
                className={[
                  "inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase px-2 py-1",
                  isPast && "text-[var(--fg-muted)]",
                  isActive && "text-[var(--brand)] border-b border-[var(--brand)]",
                  !isPast && !isActive && "text-[var(--fg-subtle)]",
                ].filter(Boolean).join(" ")}
              >
                {isPast ? (
                  <Check className="w-3 h-3" strokeWidth={2.2} />
                ) : (
                  <span className="font-semibold tabular-nums">0{stage.index}</span>
                )}
                <span>{stage.label}</span>
              </div>
              {i < STAGES.length - 1 && (
                <span className="h-px w-4 bg-[var(--border)]" aria-hidden="true" />
              )}
            </div>
          );
        })}
      </div>
      {meta && (
        <div className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
          {meta}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------
// FlowButton — primary / secondary / ghost
// ------------------------------------------------------------------

type FlowButtonProps = {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md";
  type?: "button" | "submit";
  disabled?: boolean;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  children: ReactNode;
  className?: string;
  title?: string;
};

const variantStyles = {
  primary: "bg-[var(--brand)] text-[var(--brand-fg)] hover:bg-[var(--brand-hover)] border-transparent",
  secondary: "bg-transparent text-[var(--fg-muted)] border-[var(--border-strong)] hover:text-[var(--fg)] hover:border-[var(--fg-muted)]",
  ghost: "bg-transparent text-[var(--fg-muted)] border-transparent hover:text-[var(--fg)] hover:bg-[var(--bg-elevated)]",
};

const sizeStyles = {
  sm: "px-3 py-1.5 text-[12px]",
  md: "px-4 py-2.5 text-[13px]",
};

export function FlowButton({
  variant = "primary",
  size = "md",
  type = "button",
  disabled = false,
  onClick,
  children,
  className = "",
  title,
}: FlowButtonProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={[
        "inline-flex items-center justify-center gap-2 border font-sans font-medium tracking-[0.03em] rounded-[3px] transition-colors cursor-pointer",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        variantStyles[variant],
        sizeStyles[size],
        variant === "primary" ? "shadow-[0_1px_0_rgba(0,0,0,0.04),0_6px_18px_-10px_rgba(109,36,52,0.35)]" : "",
        className,
      ].join(" ")}
    >
      {children}
    </button>
  );
}

// ------------------------------------------------------------------
// FlowCard — hairline border kart, 24px padding default
// ------------------------------------------------------------------

type FlowCardProps = {
  children: ReactNode;
  className?: string;
  padded?: boolean;
};

export function FlowCard({ children, className = "", padded = true }: FlowCardProps) {
  return (
    <div
      className={[
        "bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none",
        padded ? "p-6" : "",
        className,
      ].join(" ")}
    >
      {children}
    </div>
  );
}

// ------------------------------------------------------------------
// AiPill — AI önerisi rozeti, opsiyonel confidence skoru
// ------------------------------------------------------------------

type AiPillProps = {
  label?: string;
  confidence?: number; // 0..100
  className?: string;
};

export function AiPill({ label = "AI", confidence, className = "" }: AiPillProps) {
  const tone =
    confidence === undefined ? "brand"
      : confidence >= 90 ? "brand"
        : confidence >= 60 ? "muted"
          : "subtle";

  const toneStyles = {
    brand: "text-[var(--brand)] border-[var(--brand)]/40 bg-[var(--brand-soft)]",
    muted: "text-[var(--fg-muted)] border-[var(--border-strong)] bg-[var(--bg-sunken)]",
    subtle: "text-[var(--fg-subtle)] border-[var(--border)] bg-transparent",
  } as const;

  return (
    <span
      className={[
        "inline-flex items-center gap-1 px-1.5 py-0.5 border font-mono text-[9.5px] tracking-[0.12em] uppercase",
        toneStyles[tone],
        className,
      ].join(" ")}
    >
      <Bot className="w-2.5 h-2.5" strokeWidth={1.6} />
      <span className="font-semibold">{label}</span>
      {confidence !== undefined && (
        <span className="opacity-70">· %{confidence}</span>
      )}
    </span>
  );
}

// ------------------------------------------------------------------
// FlowField — Label (ALLCAPS Mono) + AiPill + input/select wrapper
// ------------------------------------------------------------------

type FlowFieldProps = {
  label: string;
  htmlFor?: string;
  ai?: AiPillProps | boolean;
  hint?: string;
  required?: boolean;
  missing?: boolean;
  children: ReactNode;
  className?: string;
};

export function FlowField({
  label,
  htmlFor,
  ai,
  hint,
  required,
  missing,
  children,
  className = "",
}: FlowFieldProps) {
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <label
          htmlFor={htmlFor}
          className={[
            "font-mono text-[10px] tracking-[0.18em] uppercase font-semibold",
            missing ? "text-[var(--brand)]" : "text-[var(--fg-subtle)]",
          ].join(" ")}
        >
          {label}
          {required && <span className="text-[var(--brand)] ml-1">*</span>}
        </label>
        {ai && (typeof ai === "object" ? <AiPill {...ai} /> : <AiPill />)}
      </div>
      <div className={missing ? "ring-1 ring-[var(--brand)]/30" : ""}>
        {children}
      </div>
      {hint && (
        <div className="font-mono text-[10px] tracking-[0.04em] text-[var(--fg-subtle)]">
          {hint}
        </div>
      )}
    </div>
  );
}
