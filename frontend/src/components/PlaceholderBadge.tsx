import { Sparkles } from "lucide-react";

type PlaceholderBadgeProps = {
  /** Etiket metni. Default: "YAKINDA" */
  label?: string;
  /** İkon göstersin mi (Sparkles). Default: false */
  icon?: boolean;
  /** Konumlandırma. "inline" akış içinde, "corner" parent'a göre absolute sağ-üst köşe. */
  position?: "inline" | "corner";
  className?: string;
};

/**
 * Henüz aktif olmayan placeholder UI parçalarını işaretler.
 * `corner` modunda parent element `relative` olmalıdır.
 */
export function PlaceholderBadge({
  label = "YAKINDA",
  icon = false,
  position = "inline",
  className = "",
}: PlaceholderBadgeProps) {
  const base =
    "inline-flex items-center gap-1 px-1.5 py-[2px] font-mono text-[8.5px] tracking-[0.18em] uppercase font-semibold " +
    "bg-[var(--brand-soft)] text-[var(--brand)] border border-[var(--brand)]/35 rounded-[2px] pointer-events-none select-none";
  const placement = position === "corner" ? "absolute -top-1.5 -right-1.5 z-10" : "";
  return (
    <span className={[base, placement, className].join(" ")} aria-hidden="true">
      {icon && <Sparkles className="w-2.5 h-2.5" strokeWidth={1.8} />}
      {label}
    </span>
  );
}
