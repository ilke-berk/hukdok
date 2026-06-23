import { useMsal } from "@azure/msal-react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  Home,
  Upload,
  FolderOpen,
  Link2,
  Users,
  Clock,
  ShieldCheck,
  ChevronsLeft,
  Moon,
  Sun,
  LogOut,
  Scale,
} from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import { useDashboardView } from "@/hooks/useDashboardView";

type NavItemDef = {
  id: string;
  label: string;
  path: string;
  Icon: typeof Home;
  matches?: (pathname: string) => boolean;
};

const NAV: NavItemDef[] = [
  { id: "home", label: "Anasayfa", path: "/", Icon: Home, matches: p => p === "/" },
  { id: "upload", label: "Belge Yükleme", path: "/upload", Icon: Upload },
  { id: "cases", label: "Dava Dosyaları", path: "/cases", Icon: FolderOpen, matches: p => p.startsWith("/cases") || p.startsWith("/new-case") || p.startsWith("/case-groups") },
  { id: "unlinked", label: "Bağlantısız Belgeler", path: "/unlinked-documents", Icon: Link2 },
  { id: "clients", label: "Müvekkiller", path: "/clients", Icon: Users, matches: p => p.startsWith("/clients") || p.startsWith("/new-client") },
  { id: "activity", label: "Aktivite Geçmişi", path: "/activity-history", Icon: Clock },
];

const ADMIN_EMAIL = "ilkekutluk@lexisbio.onmicrosoft.com";

type SidebarProps = {
  collapsed: boolean;
  onToggle: () => void;
};

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { instance, accounts } = useMsal();
  const { theme, setTheme } = useTheme();
  const { view, setView } = useDashboardView();

  const account = accounts[0];
  const username = (account?.username || "").toLowerCase();
  const isAdminUser = username === ADMIN_EMAIL.toLowerCase();

  const displayName = account?.name || "Kullanıcı";
  const initials = displayName
    .split(" ")
    .map(s => s.trim()[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase() || "—";

  const navItems: NavItemDef[] = isAdminUser
    ? [...NAV, { id: "admin", label: "Yönetim", path: "/admin", Icon: ShieldCheck }]
    : NAV;

  const isActive = (item: NavItemDef) => {
    if (item.matches) return item.matches(location.pathname);
    return location.pathname === item.path;
  };

  const handleLogout = () => {
    try {
      const currentAccount = instance.getActiveAccount();
      instance.logoutRedirect({
        account: currentAccount,
        postLogoutRedirectUri: window.location.origin + "/login",
      });
    } catch (error) {
      console.error("❌ Logout failed:", error);
      sessionStorage.clear();
      localStorage.clear();
      window.location.reload();
    }
  };

  const toggleTheme = () => {
    setTheme(theme === "light" ? "dark" : "light");
  };

  return (
    <aside
      aria-hidden={collapsed}
      className={[
        "shrink-0 grid overflow-hidden relative",
        "bg-[var(--bg-sunken)] border-r border-[var(--border)]",
        collapsed ? "w-0 p-0 border-r-0" : "w-[248px] pt-[22px] px-4 pb-4",
      ].join(" ")}
      style={{
        gridTemplateRows: "auto 1fr auto",
        transition: "width 240ms cubic-bezier(0.4,0,0.2,1), padding 240ms cubic-bezier(0.4,0,0.2,1), border-right-width 240ms cubic-bezier(0.4,0,0.2,1)",
      }}
    >
      <div
        className="w-[216px] grid"
        style={{
          gridTemplateRows: "auto 1fr auto",
          opacity: collapsed ? 0 : 1,
          transition: "opacity 160ms ease",
          transitionDelay: collapsed ? "0s" : "100ms",
        }}
      >
        {/* Mark + collapse */}
        <div className="flex items-center justify-between gap-3 pb-[22px] pl-1 pr-1 border-b border-[var(--border)] min-h-[56px]">
          <button
            type="button"
            onClick={() => navigate("/")}
            className="flex items-center gap-3 cursor-pointer outline-none"
            tabIndex={collapsed ? -1 : 0}
          >
            <Scale className="w-7 h-7 text-[var(--brand)] stroke-[1.25]" />
            <span className="font-display text-[18px] font-medium tracking-[0.16em] text-[var(--fg)] whitespace-nowrap">
              HUKDOK
            </span>
          </button>
          <button
            type="button"
            onClick={onToggle}
            aria-label="Menüyü daralt"
            title="Menüyü daralt"
            tabIndex={collapsed ? -1 : 0}
            className="w-[26px] h-[26px] grid place-items-center rounded-[4px] border border-[var(--border)] bg-transparent text-[var(--fg-muted)] cursor-pointer transition-colors hover:text-[var(--brand)] hover:border-[var(--brand)] hover:bg-[var(--brand-soft)]"
          >
            <ChevronsLeft className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Nav */}
        <div>
          <div className="font-mono text-[9px] tracking-[0.22em] uppercase text-[var(--fg-subtle)] pt-4 pb-2 px-2">
            Çalışma
          </div>
          <nav className="flex flex-col gap-0.5">
            {navItems.map(item => {
              const active = isActive(item);
              const { Icon } = item;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => navigate(item.path)}
                  tabIndex={collapsed ? -1 : 0}
                  className={[
                    "flex items-center gap-3 px-2.5 py-2.5 rounded-[4px] text-left relative",
                    "font-sans text-[13px] font-medium tracking-[0.005em]",
                    "transition-colors",
                    active
                      ? "text-[var(--brand)] bg-[var(--brand-soft)] font-semibold"
                      : "text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-[var(--bg-elevated)]",
                  ].join(" ")}
                >
                  {active && (
                    <span className="absolute -left-4 top-2 bottom-2 w-[2px] bg-[var(--brand)]" />
                  )}
                  <Icon className="w-4 h-4 opacity-90 shrink-0" />
                  <span className="whitespace-nowrap">{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Footer: user + view switcher + theme/logout */}
        <div className="border-t border-[var(--border)] pt-3.5 grid gap-2.5">
          <div className="flex items-center gap-2.5 px-1.5 py-2">
            <div className="w-[34px] h-[34px] rounded-full bg-[var(--brand)] text-[var(--brand-fg)] grid place-items-center font-display font-medium text-[13px] tracking-[0.02em] shrink-0 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]">
              {initials}
            </div>
            <div className="min-w-0">
              <div className="text-[13px] text-[var(--fg)] font-semibold leading-[1.2] truncate">
                {displayName}
              </div>
              <div className="text-[10.5px] text-[var(--fg-subtle)] mt-0.5 tracking-[0.04em] truncate">
                {isAdminUser ? "Yönetici" : "Avukat"}
              </div>
            </div>
          </div>

          {/* Görünüm seçici */}
          <div className="px-1.5">
            <div className="font-mono text-[9px] tracking-[0.22em] uppercase text-[var(--fg-subtle)] mb-1.5">
              Görünüm
            </div>
            <div className="grid grid-cols-2 border border-[var(--border)] rounded-[4px] overflow-hidden">
              {(["avukat", "idari"] as const).map(v => {
                const active = view === v;
                return (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setView(v)}
                    tabIndex={collapsed ? -1 : 0}
                    className={[
                      "px-2 py-1.5 font-sans text-[11px] font-medium tracking-[0.04em] transition-colors",
                      active
                        ? "bg-[var(--brand)] text-[var(--brand-fg)]"
                        : "bg-[var(--bg-elevated)] text-[var(--fg-muted)] hover:text-[var(--fg)]",
                    ].join(" ")}
                  >
                    {v === "avukat" ? "Avukat" : "İdari"}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={toggleTheme}
              tabIndex={collapsed ? -1 : 0}
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-2.5 py-2 border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--fg-muted)] font-sans text-[11px] font-medium tracking-[0.04em] rounded-[4px] cursor-pointer transition-colors hover:text-[var(--fg)] hover:border-[var(--border-strong)]"
              title={theme === "light" ? "Koyu tema" : "Açık tema"}
            >
              {theme === "light" ? <Moon className="w-3.5 h-3.5" /> : <Sun className="w-3.5 h-3.5" />}
              <span>Tema</span>
            </button>
            <button
              type="button"
              onClick={handleLogout}
              tabIndex={collapsed ? -1 : 0}
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-2.5 py-2 border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--fg-muted)] font-sans text-[11px] font-medium tracking-[0.04em] rounded-[4px] cursor-pointer transition-colors hover:text-[var(--fg)] hover:border-[var(--border-strong)]"
              title={`Çıkış Yap (${displayName})`}
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>Çıkış</span>
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
