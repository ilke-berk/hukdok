import { useEffect, useRef, useState } from "react";
import { useMsal } from "@azure/msal-react";
import { useNavigate } from "react-router-dom";
import { Menu, Search, Bell, Plus, X } from "lucide-react";
import { usePageTitle } from "@/hooks/usePageTitle";
import { PlaceholderBadge } from "@/components/PlaceholderBadge";
import { usePageSearchContext } from "@/components/system/PageSearch";
import { GlobalSearchDropdown } from "@/components/system/GlobalSearchDropdown";

type TopbarProps = {
  collapsed: boolean;
  onOpenSidebar: () => void;
};

const DEFAULT_PLACEHOLDER = "Esas no, müvekkil, mahkeme veya konu ara…";

export function Topbar({ collapsed, onOpenSidebar }: TopbarProps) {
  const navigate = useNavigate();
  const { accounts } = useMsal();
  const { title, breadcrumb } = usePageTitle();
  const { query, setQuery, registration } = usePageSearchContext();

  const account = accounts[0];
  const firstName = (account?.name || "Kullanıcı").split(" ")[0];

  const inputRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);

  // Sayfa kayıt yaptıysa o sayfayı yerinde filtreler; yoksa global mod.
  const isGlobal = registration === null;
  const placeholder = registration?.placeholder ?? DEFAULT_PLACEHOLDER;
  // Global modda: odaklanınca (boşken hızlı eylemler) veya yazınca dropdown açılır.
  const showDropdown = isGlobal && focused;

  // ⌘K / Ctrl+K → barı odakla
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  return (
    <header
      className="h-16 shrink-0 border-b border-[var(--border)] grid items-center px-7 gap-6 bg-[var(--bg)]"
      style={{ gridTemplateColumns: "1fr auto" }}
    >
      {/* Left: opener + title */}
      <div className="flex items-center gap-3.5 min-w-0">
        {collapsed && (
          <button
            type="button"
            onClick={onOpenSidebar}
            aria-label="Menüyü aç"
            title="Menüyü aç"
            className="w-[38px] h-[38px] grid place-items-center rounded-[4px] border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--fg-muted)] cursor-pointer transition-colors shrink-0 hover:text-[var(--brand)] hover:border-[var(--brand)] hover:bg-[var(--brand-soft)]"
          >
            <Menu className="w-4 h-4" />
          </button>
        )}
        <div className="flex flex-col min-w-0">
          <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
            {(breadcrumb || ["Avukat Paneli"]).join(" / ")}
          </div>
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="font-display font-medium text-[22px] tracking-[-0.01em] text-[var(--fg)] truncate">
              {title}
            </span>
            <span className="italic text-[var(--fg-muted)] font-normal text-[15px] truncate">
              — iyi günler, {firstName}.
            </span>
          </div>
        </div>
      </div>

      {/* Right: search + notifications + CTA */}
      <div className="flex items-center gap-3 relative">
        {/* Tek mutlak arama barı */}
        <div className="hidden lg:block relative w-[340px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--fg-muted)] pointer-events-none" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            // Dropdown içindeki seçim mousedown ile çalıştığı için blur'ı erteliyoruz
            onBlur={() => setFocused(false)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                if (query) setQuery("");
                inputRef.current?.blur();
              }
            }}
            placeholder={placeholder}
            aria-label="Ara"
            className="w-full h-10 pl-9 pr-16 bg-[var(--bg-elevated)] border border-[var(--border)] text-[13px] text-[var(--fg)] placeholder:text-[var(--fg-muted)] rounded-[4px] transition-colors focus:border-[var(--brand)] focus:outline-none"
          />
          {query ? (
            <button
              type="button"
              onClick={() => { setQuery(""); inputRef.current?.focus(); }}
              aria-label="Aramayı temizle"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-[var(--fg-subtle)] hover:text-[var(--brand)] transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          ) : (
            <span className="absolute right-2.5 top-1/2 -translate-y-1/2 inline-flex items-center gap-0.5 px-1.5 py-0.5 border border-[var(--border)] rounded-[3px] font-mono text-[10px] text-[var(--fg-subtle)] tracking-[0.04em] bg-[var(--bg)] pointer-events-none">
              ⌘K
            </span>
          )}

          {showDropdown && (
            <GlobalSearchDropdown
              query={query}
              onClose={() => { setQuery(""); inputRef.current?.blur(); }}
            />
          )}
        </div>

        <div className="relative">
          <button
            type="button"
            aria-label="Bildirimler"
            className="w-[38px] h-[38px] grid place-items-center border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--fg-muted)] cursor-pointer rounded-[4px] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--fg)]"
            onClick={() => { /* TODO: bildirim paneli */ }}
          >
            <Bell className="w-4 h-4" />
          </button>
          <PlaceholderBadge position="corner" />
        </div>
        <button
          type="button"
          onClick={() => navigate("/upload")}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-[var(--brand)] text-[var(--brand-fg)] border-0 rounded-[4px] font-sans text-[13px] font-medium tracking-[0.03em] cursor-pointer transition-colors hover:bg-[var(--brand-hover)]"
          style={{ boxShadow: "0 1px 0 rgba(0,0,0,0.04), 0 6px 18px -10px rgba(109,36,52,0.35)" }}
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Belge Yükle</span>
        </button>
      </div>
    </header>
  );
}
