import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { PageTitleProvider } from "@/hooks/usePageTitle";
import { DashboardViewProvider } from "@/hooks/useDashboardView";
import { PageSearchProvider } from "@/components/system/PageSearch";

const COLLAPSED_KEY = "hukdok.sidebar.collapsed";

export function ShellLayout() {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try { localStorage.setItem(COLLAPSED_KEY, String(collapsed)); } catch { /* ignore */ }
  }, [collapsed]);

  return (
    <DashboardViewProvider>
      <PageTitleProvider>
        <PageSearchProvider>
          <div className="theme-classic flex h-screen w-full overflow-hidden bg-[var(--bg)] text-[var(--fg)] font-sans">
            <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
            <div className="flex-1 flex flex-col min-w-0">
              <Topbar collapsed={collapsed} onOpenSidebar={() => setCollapsed(false)} />
              <main className="flex-1 overflow-y-auto px-7 pt-6 pb-7">
                <Outlet />
              </main>
            </div>
          </div>
        </PageSearchProvider>
      </PageTitleProvider>
    </DashboardViewProvider>
  );
}
