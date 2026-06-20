import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { AlertTriangle, CheckCircle2, X } from "lucide-react";
import { FlowButton } from "@/components/flow/primitives";

export type ConfirmTone = "destructive" | "warning" | "info";

export interface ConfirmOptions {
  tone: ConfirmTone;
  title: string;
  body?: ReactNode;
  context?: string;
  details?: { label: string; value: string }[];
  irreversible?: boolean;
  /** Doldurulması zorunlu eşleştirme metni (örn. "SİL"). Confirm bu metin yazılana kadar disabled kalır. */
  checkRequired?: string;
  cancelLabel?: string;
  confirmLabel?: string;
}

type ResolveFn = (value: boolean) => void;

interface ConfirmContextValue {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

const toneConfig: Record<ConfirmTone, { color: string; bg: string; soft: string; icon: typeof AlertTriangle; eyebrow: string; confirmLabel: string }> = {
  destructive: {
    color: "var(--brand)",
    bg: "var(--brand)",
    soft: "var(--brand-soft)",
    icon: AlertTriangle,
    eyebrow: "Yıkıcı işlem",
    confirmLabel: "Sil",
  },
  warning: {
    color: "#c47a1e",
    bg: "#c47a1e",
    soft: "rgba(196, 122, 30, 0.12)",
    icon: AlertTriangle,
    eyebrow: "Dikkat",
    confirmLabel: "Devam et",
  },
  info: {
    color: "var(--fg)",
    bg: "var(--fg)",
    soft: "var(--bg-sunken)",
    icon: CheckCircle2,
    eyebrow: "Onay gerekiyor",
    confirmLabel: "Onayla",
  },
};

export function ConfirmDialogProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const [checkInput, setCheckInput] = useState("");
  const resolverRef = useRef<ResolveFn | null>(null);

  const confirm = useCallback((opts: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setOptions(opts);
      setCheckInput("");
      setOpen(true);
    });
  }, []);

  const handleClose = useCallback((result: boolean) => {
    if (resolverRef.current) {
      resolverRef.current(result);
      resolverRef.current = null;
    }
    setOpen(false);
  }, []);

  const tone = options?.tone || "info";
  const config = toneConfig[tone];
  const Icon = config.icon;
  const checkPassed = !options?.checkRequired || checkInput === options.checkRequired;

  // Enter shortcut for confirm (when check passes)
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Enter" && checkPassed && !(e.target instanceof HTMLInputElement && options?.checkRequired)) {
        e.preventDefault();
        handleClose(true);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, checkPassed, options?.checkRequired, handleClose]);

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      <Dialog open={open} onOpenChange={(v) => !v && handleClose(false)}>
        <DialogContent
          className="theme-classic bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none p-0 gap-0 sm:max-w-[520px]"
          aria-label={options?.title}
        >
          {/* Üst brand accent şeridi */}
          <div className="h-[3px]" style={{ background: config.bg }} aria-hidden="true" />

          {/* Close button */}
          <button
            type="button"
            onClick={() => handleClose(false)}
            aria-label="Kapat"
            className="absolute top-3 right-3 w-7 h-7 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)] hover:bg-[var(--bg)] transition-colors z-10"
          >
            <X className="w-4 h-4" />
          </button>

          {/* Body */}
          <div className="px-6 py-6 grid gap-4">
            {options?.context && (
              <div className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                Bağlam · {options.context}
              </div>
            )}

            <div className="flex items-start gap-3">
              <div
                className="w-12 h-12 grid place-items-center shrink-0"
                style={{ background: config.soft, color: config.color }}
              >
                <Icon className="w-5 h-5" strokeWidth={1.8} />
              </div>
              <div className="flex-1 min-w-0 grid gap-1.5">
                <span
                  className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold"
                  style={{ color: config.color }}
                >
                  {config.eyebrow}
                </span>
                <h2 className="font-display font-medium text-[22px] tracking-[-0.005em] text-[var(--fg)] leading-tight">
                  {options?.title}
                </h2>
              </div>
            </div>

            {options?.body && (
              <div className="text-[13.5px] text-[var(--fg-muted)] leading-[1.6]">
                {options.body}
              </div>
            )}

            {options?.details && options.details.length > 0 && (
              <div className="bg-[var(--bg)] border border-[var(--border)] p-4 grid gap-2">
                {options.details.map((d, i) => (
                  <div key={i} className="flex items-baseline justify-between gap-3 font-mono text-[12px]">
                    <span className="text-[var(--fg-subtle)] tracking-[0.06em]">{d.label}</span>
                    <span className="text-[var(--fg)] tabular-nums truncate">{d.value}</span>
                  </div>
                ))}
              </div>
            )}

            {options?.irreversible && (
              <div
                className="border-l-2 px-4 py-3"
                style={{ background: config.soft, borderLeftColor: config.color }}
              >
                <p className="text-[12.5px] font-medium" style={{ color: config.color }}>
                  Bu işlem geri alınamaz.
                </p>
              </div>
            )}

            {options?.checkRequired && (
              <div className="grid gap-1.5">
                <label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                  Onaylamak için <span style={{ color: config.color }}>{options.checkRequired}</span> yazın
                </label>
                <input
                  type="text"
                  value={checkInput}
                  onChange={(e) => setCheckInput(e.target.value)}
                  autoFocus
                  className="w-full h-10 px-3 bg-[var(--bg)] border border-[var(--border)] rounded-[3px] font-mono text-[14px] tabular-nums text-[var(--fg)] focus:outline-none focus:border-[var(--brand)]"
                  placeholder={options.checkRequired}
                />
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-3 border-t border-[var(--border)] bg-[var(--bg)] flex items-center justify-between gap-3">
            <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
              esc · vazgeç
            </span>
            <div className="flex items-center gap-2">
              <FlowButton variant="secondary" size="sm" onClick={() => handleClose(false)}>
                {options?.cancelLabel || "Vazgeç"}
              </FlowButton>
              <FlowButton
                variant="primary"
                size="sm"
                disabled={!checkPassed}
                onClick={() => handleClose(true)}
                className={tone === "destructive" ? "!bg-[var(--brand)]" : tone === "warning" ? "!bg-[#c47a1e]" : ""}
              >
                {options?.confirmLabel || config.confirmLabel}
              </FlowButton>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    throw new Error("useConfirm must be used inside <ConfirmDialogProvider>");
  }
  return ctx.confirm;
}
