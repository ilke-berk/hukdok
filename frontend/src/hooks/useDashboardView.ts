import { createContext, useContext } from "react";

export type DashboardView = "avukat" | "idari";

export type DashboardViewContextValue = {
  view: DashboardView;
  setView: (v: DashboardView) => void;
};

/**
 * Panel görünümü context'i + hook'u. Provider bileşeni
 * `components/system/DashboardViewProvider.tsx`'te durur (fast-refresh sınırı:
 * react-refresh/only-export-components).
 */
export const DashboardViewContext = createContext<DashboardViewContextValue | null>(null);

export function useDashboardView(): DashboardViewContextValue {
  const ctx = useContext(DashboardViewContext);
  if (!ctx) {
    throw new Error("useDashboardView must be used inside <DashboardViewProvider>");
  }
  return ctx;
}
