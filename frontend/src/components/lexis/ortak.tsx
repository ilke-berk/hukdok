import { useLayoutEffect, useRef, useState, type ReactNode, type TextareaHTMLAttributes } from "react";
import { tutarOku } from "@/lib/lexisMetin";
import { cn } from "@/lib/utils";
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
export function OtoMetinAlani({ value, className, ...kalan }: TextareaHTMLAttributes<HTMLTextAreaElement> & { value: string }) {
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
      // `cn` (tailwind-merge): çağıranın sınıfı çakışan temel sınıfı ezer (ör. kenarlıklı, kaymasız alan)
      className={cn(
        "block w-full resize-none overflow-hidden bg-transparent border border-transparent rounded-[3px] px-2 py-1.5 -mx-2 text-[13.5px] leading-[1.65] text-[var(--fg)] placeholder:text-[var(--fg-subtle)] hover:border-[var(--border)] focus:border-[var(--brand)] focus:bg-[var(--bg)] focus:outline-none",
        className,
      )}
      {...kalan}
    />
  );
}

const tutarMetni = (n: number | null) => (n === null ? "" : n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

/**
 * Tutar girişi: yazarken serbest metin, alandan çıkınca sayıya çevrilir (`tutarOku`); tanınmayan metin alanı
 * eski değerine döndürür. Değer dışarıdan değişince çağıran `key` ile yeniden bağlar — effect'le eşitleme yok.
 * `etiket` görünür etikettir; yoksa `ariaEtiket` (tablo hücresi).
 */
export function TutarGirdisi({
  etiket,
  ariaEtiket,
  deger,
  oneri = null,
  kilitli = false,
  onDegistir,
}: {
  etiket?: string;
  ariaEtiket?: string;
  deger: number | null;
  /** Boş alanın yer tutucusu (ör. önerilen tutar). */
  oneri?: number | null;
  kilitli?: boolean;
  onDegistir: (deger: number | null) => void;
}) {
  const [metin, setMetin] = useState(tutarMetni(deger));
  const girdi = (
    <input
      type="text"
      inputMode="decimal"
      value={metin}
      disabled={kilitli}
      aria-label={ariaEtiket}
      placeholder={oneri === null ? "—" : tutarMetni(oneri)}
      onChange={(e) => setMetin(e.target.value)}
      onBlur={() => {
        const okunan = tutarOku(metin);
        if (okunan === undefined || okunan === deger) setMetin(tutarMetni(deger));
        else onDegistir(okunan);
      }}
      className="w-full h-8 px-2 border border-[var(--border)] bg-[var(--bg-elevated)] rounded-[3px] font-mono text-[12.5px] tabular-nums text-right text-[var(--fg)] placeholder:text-[var(--fg-subtle)] focus:border-[var(--brand)] focus:outline-none"
    />
  );
  if (!etiket) return girdi;
  return (
    <label className="grid gap-1 min-w-0">
      <span className="text-[11px] text-[var(--fg-subtle)]">{etiket}</span>
      {girdi}
    </label>
  );
}

/** Bölge içi boş durum / bilgi satırı. */
export function BosDurum({ children }: { children: ReactNode }) {
  return <p className="text-[12.5px] leading-[1.6] text-[var(--fg-muted)]">{children}</p>;
}
