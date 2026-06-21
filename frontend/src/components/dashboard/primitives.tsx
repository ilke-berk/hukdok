import { ReactNode } from "react";

type EyebrowProps = {
  children: ReactNode;
  className?: string;
  tone?: "brand" | "subtle";
};

export function Eyebrow({ children, className = "", tone = "subtle" }: EyebrowProps) {
  const color = tone === "brand" ? "text-[var(--brand)]" : "text-[var(--fg-subtle)]";
  return (
    <span className={`font-mono text-[10px] tracking-[0.22em] uppercase font-semibold ${color} ${className}`}>
      {children}
    </span>
  );
}

type SectionHeaderProps = {
  eyebrow?: string;
  title: string;
  meta?: ReactNode;
  className?: string;
  italic?: string;
};

export function SectionHeader({ eyebrow, title, meta, italic, className = "" }: SectionHeaderProps) {
  return (
    <div className={`flex items-baseline justify-between gap-4 ${className}`}>
      <div className="min-w-0 flex flex-col gap-1">
        {eyebrow && <Eyebrow tone="brand">{eyebrow}</Eyebrow>}
        <h2 className="font-display font-medium text-[17px] tracking-[-0.005em] text-[var(--fg)]">
          {title}
          {italic && <span className="italic text-[var(--fg-muted)] font-normal ml-1.5 text-[14px]">{italic}</span>}
        </h2>
      </div>
      {meta && <div className="shrink-0 text-[var(--fg-subtle)]">{meta}</div>}
    </div>
  );
}

type HairlineCardProps = {
  children: ReactNode;
  className?: string;
  padded?: boolean;
};

export function HairlineCard({ children, className = "", padded = true }: HairlineCardProps) {
  return (
    <div
      className={[
        "bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none",
        padded ? "p-5" : "",
        className,
      ].join(" ")}
    >
      {children}
    </div>
  );
}

type MetricCardProps = {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  hint?: string;
  tone?: "brand" | "neutral" | "success" | "warning";
  onClick?: () => void;
};

// Minimal tasarım: tonlar renkten arındırıldı — tüm ikonlar tek tip ince/nötr.
// Vurgu gerektiğinde yalnızca `brand` hafif bir renk taşır, diğerleri gri kalır.
const neutralTone = {
  iconBg: "bg-[var(--bg-sunken)]",
  iconColor: "text-[var(--fg-subtle)]",
  value: "text-[var(--fg)]",
};

const toneStyles: Record<NonNullable<MetricCardProps["tone"]>, { iconBg: string; iconColor: string; value: string }> = {
  brand: {
    iconBg: "bg-[var(--bg-sunken)]",
    iconColor: "text-[var(--fg-muted)]",
    value: "text-[var(--fg)]",
  },
  neutral: neutralTone,
  success: neutralTone,
  warning: neutralTone,
};

export function MetricCard({ label, value, icon, hint, tone = "neutral", onClick }: MetricCardProps) {
  const t = toneStyles[tone];
  const interactive = !!onClick;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!interactive}
      className={[
        "text-left bg-[var(--bg-elevated)] border border-[var(--border)] p-4 grid gap-3",
        "transition-colors",
        interactive ? "cursor-pointer hover:border-[var(--border-strong)]" : "cursor-default",
      ].join(" ")}
    >
      <div className="flex items-center justify-between">
        <Eyebrow>{label}</Eyebrow>
        {icon && (
          <div className={`grid place-items-center ${t.iconColor}`}>
            {icon}
          </div>
        )}
      </div>
      <div className={`font-display font-medium text-[28px] tracking-[-0.02em] leading-none ${t.value}`}>
        {value}
      </div>
      {hint && (
        <div className="font-mono text-[10px] tracking-[0.04em] text-[var(--fg-subtle)] uppercase">
          {hint}
        </div>
      )}
    </button>
  );
}
