import { useState } from "react";
import { Outlet } from "react-router";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { PageTitleProvider } from "@/components/system/PageTitleProvider";
import { DashboardViewProvider } from "@/components/system/DashboardViewProvider";
import { PageSearchProvider } from "@/components/system/PageSearch";

export function ShellLayout() {
  const [open, setOpen] = useState(false);

  return (
    <DashboardViewProvider>
      <PageTitleProvider>
        <PageSearchProvider>
          <div className="theme-classic flex h-screen w-full overflow-hidden bg-[var(--bg)] text-[var(--fg)] font-sans">
            {/* Sol kenar hover şeridi: fare kenara gelince menü açılır */}
            <div
              className="fixed left-0 top-0 h-full w-2 z-30"
              onMouseEnter={() => setOpen(true)}
            />
            <Sidebar open={open} onClose={() => setOpen(false)} />
            <div className="flex-1 flex flex-col min-w-0">
              <Topbar onOpenSidebar={() => setOpen(true)} />
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
