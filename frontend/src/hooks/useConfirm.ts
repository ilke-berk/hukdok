import { createContext, useContext, ReactNode } from "react";

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

export interface ConfirmContextValue {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

/**
 * Onay diyaloğu context'i + hook'u. Provider bileşeni
 * `components/system/ConfirmDialog.tsx`'te durur (fast-refresh sınırı:
 * react-refresh/only-export-components).
 */
export const ConfirmContext = createContext<ConfirmContextValue | null>(null);

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    throw new Error("useConfirm must be used inside <ConfirmDialogProvider>");
  }
  return ctx.confirm;
}
