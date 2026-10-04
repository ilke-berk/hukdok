import { useLayoutEffect, useRef, type ReactNode, type TextareaHTMLAttributes } from "react";
import type { RozetTonu } from "./yardimcilar";

const TON_SINIFLARI: Record<RozetTonu, string> = {
  ok: "text-tone-ok border-tone-ok/40 bg-tone-ok/10",
  danger: "text-tone-danger border-tone-danger/40 bg-tone-danger/10",
  caution: "text-tone-caution border-tone-caution/40 bg-tone-caution/10",
  muted: "text-[var(--fg-muted)] border-[var(--border-strong)] bg-[var(--bg-sunken)]",
};

/** Küçük durum rozeti — madde durumu, dayanak türü, bağ durumu. */
export function Rozet({ ton = "muted", children, title }: { ton?: RozetTonu; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 border font-mono text-[9.5px] tracking-[0.1em] uppercase font-semibold whitespace-nowrap ${TON_SINIFLARI[ton]}`}
    >
      {children}
    </span>
  );
}

/** Bölge / kart başlığı: mono etiket + sağda isteğe bağlı içerik. */
export function BolgeBasligi({ children, sag }: { children: ReactNode; sag?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 min-w-0">
      <h3 className="font-mono text-[10px] tracking-[0.2em] uppercase font-semibold text-[var(--fg-subtle)] truncate">{children}</h3>
      {sag && <div className="shrink-0 flex items-center gap-1.5">{sag}</div>}
    </div>
  );
}

/** Simge düğmesi (28 px) — satır eylemleri. */
export function SimgeDugmesi({
  etiket,
  onClick,
  disabled,
  children,
}: {
  etiket: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={etiket}
      title={etiket}
      onClick={onClick}
      disabled={disabled}
      className="w-7 h-7 grid place-items-center rounded-[3px] text-[var(--fg-subtle)] hover:text-[var(--brand)] hover:bg-[var(--bg-sunken)] disabled:opacity-40 disabled:pointer-events-none shrink-0"
    >
      {children}
    </button>
  );
}

/** İçeriğine göre büyüyen metin alanı (taslak paragrafı, madde, alıntı). */
export function OtoMetinAlani({ value, className = "", ...kalan }: TextareaHTMLAttributes<HTMLTextAreaElement> & { value: string }) {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      className={`block w-full resize-none overflow-hidden bg-transparent border border-transparent rounded-[3px] px-2 py-1.5 -mx-2 text-[13.5px] leading-[1.65] text-[var(--fg)] placeholder:text-[var(--fg-subtle)] hover:border-[var(--border)] focus:border-[var(--brand)] focus:bg-[var(--bg)] focus:outline-none ${className}`}
      {...kalan}
    />
  );
}

/** Bölge içi boş durum / bilgi satırı. */
export function BosDurum({ children }: { children: ReactNode }) {
  return <p className="text-[12.5px] leading-[1.6] text-[var(--fg-muted)]">{children}</p>;
}
