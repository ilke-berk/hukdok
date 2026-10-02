import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Outlet } from "react-router";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { PageTitleProvider } from "@/components/system/PageTitleProvider";
import { DashboardViewProvider } from "@/components/system/DashboardViewProvider";
import { PageSearchProvider } from "@/components/system/PageSearch";
import { OdakModuContext } from "@/hooks/useOdakModu";
import { PageSkeleton } from "@/components/skeletons/Skeletons";
import { ArkaplanCizgisi } from "./ArkaplanCizgisi";

export function ShellLayout() {
  const [open, setOpen] = useState(false);
  // Odak modu (Hukukbot): Topbar yok, main dolgusuz; menü kenar hover'ıyla DEĞİL yalnız tıkla açılır ve
  // sayfanın sol paneli ÜSTÜNE biner (perde + dışarı tık / Esc kapatır) — iki sol panel yan yana dizilmez.
  const [odak, setOdak] = useState(false);
  const menuyuAc = useCallback(() => setOpen(true), []);
  const odakDegeri = useMemo(() => ({ odak, setOdak, menuyuAc }), [odak, menuyuAc]);

  useEffect(() => {
    if (!open || !odak) return;
    const tus = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", tus);
    return () => document.removeEventListener("keydown", tus);
  }, [open, odak]);

  return (
    <DashboardViewProvider>
      <PageTitleProvider>
        <PageSearchProvider>
          <OdakModuContext.Provider value={odakDegeri}>
            <div className="theme-classic flex h-screen w-full overflow-hidden bg-[var(--bg)] text-[var(--fg)] font-sans">
              {/* Sol kenar hover şeridi: fare kenara gelince menü açılır (odak modunda kapalı) */}
              {!odak && (
                <div
                  className="fixed left-0 top-0 h-full w-2 z-30"
                  onMouseEnter={() => setOpen(true)}
                />
              )}
              {odak && open && (
                <button
                  type="button"
                  aria-label="Menüyü kapat"
                  tabIndex={-1}
                  data-testid="shell-menu-perdesi"
                  className="fixed inset-0 z-[45] bg-black/40 cursor-default"
                  onClick={() => setOpen(false)}
                />
              )}
              <Sidebar open={open} onClose={() => setOpen(false)} hoverIleKapan={!odak} />
              <div className="relative flex-1 flex flex-col min-w-0">
                {/* Faz 5: ekrandaki veri arkada tazelenirken üstte ince çizgi (içeriği bloklamaz) */}
                <ArkaplanCizgisi />
                {!odak && <Topbar onOpenSidebar={() => setOpen(true)} />}
                <main className={odak ? "flex-1 min-h-0 overflow-hidden" : "flex-1 overflow-y-auto px-7 pt-6 pb-7"}>
                  {/* Sayfa parçası (lazy route) burada iner: menü/üst bar yerinde kalır, içerikte iskelet.
                      App.tsx'teki dış Suspense yalnız kabuk dışı yedektir. */}
                  <Suspense fallback={<PageSkeleton />}>
                    <Outlet />
                  </Suspense>
                </main>
              </div>
            </div>
          </OdakModuContext.Provider>
        </PageSearchProvider>
      </PageTitleProvider>
    </DashboardViewProvider>
  );
}
