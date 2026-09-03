import { useCallback, useEffect, useState, ReactNode } from "react";
import { DashboardViewContext, type DashboardView } from "@/hooks/useDashboardView";

const STORAGE_KEY = "hukdok.dashboard.view";
const DEFAULT_VIEW: DashboardView = "avukat";

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
