import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";

export type DashboardView = "avukat" | "idari";

const STORAGE_KEY = "hukdok.dashboard.view";
const DEFAULT_VIEW: DashboardView = "avukat";

type ContextValue = {
  view: DashboardView;
  setView: (v: DashboardView) => void;
};

const DashboardViewContext = createContext<ContextValue | null>(null);

function readStored(): DashboardView {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw === "idari" || raw === "avukat" ? raw : DEFAULT_VIEW;
  } catch {
    return DEFAULT_VIEW;
  }
}

export function DashboardViewProvider({ children }: { children: ReactNode }) {
  const [view, setViewState] = useState<DashboardView>(() => readStored());

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, view); } catch { /* ignore */ }
  }, [view]);

  const setView = useCallback((v: DashboardView) => setViewState(v), []);

  return (
    <DashboardViewContext.Provider value={{ view, setView }}>
      {children}
    </DashboardViewContext.Provider>
  );
}

export function useDashboardView(): ContextValue {
  const ctx = useContext(DashboardViewContext);
  if (!ctx) {
    throw new Error("useDashboardView must be used inside <DashboardViewProvider>");
  }
  return ctx;
}
