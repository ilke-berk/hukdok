import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import {
  Home,
  Upload,
  FolderOpen,
  Users,
  Clock,
  ShieldCheck,
  Plus,
  Gavel,
  User,
  Search,
  Bot,
} from "lucide-react";
import { useMsal } from "@azure/msal-react";
import { useCases } from "@/hooks/useCases";
import { useClients } from "@/hooks/useClients";
import { useDebounce } from "@/hooks/useDebounce";

interface CommandPaletteContextValue {
  open: boolean;
  setOpen: (v: boolean) => void;
  toggle: () => void;
}

const CommandPaletteContext = createContext<CommandPaletteContextValue | null>(null);

type CasePreview = {
  id: number;
  tracking_no: string;
  esas_no?: string;
  status?: string;
  court?: string;
  subject?: string;
};

type ClientPreview = {
  id: number;
  name: string;
  category?: string;
};

const ADMIN_EMAIL = "ilkekutluk@lexisbio.onmicrosoft.com";

export function CommandPaletteProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 200);
  const navigate = useNavigate();
  const { searchCases } = useCases();
  const { clients } = useClients();
  const { accounts } = useMsal();
  const isAdmin = (accounts[0]?.username || "").toLowerCase() === ADMIN_EMAIL.toLowerCase();
  const [caseResults, setCaseResults] = useState<CasePreview[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const cancelRef = useRef(false);

  const toggle = useCallback(() => setOpen(v => !v), []);

  // Global ⌘K / Ctrl+K listener
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(v => !v);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  // Sorgu değişince case search
  useEffect(() => {
    const q = debouncedQuery.trim();
    if (q.length < 2) {
      setCaseResults([]);
      setIsSearching(false);
      return;
    }
    setIsSearching(true);
    cancelRef.current = false;
    (async () => {
      try {
        const data = await searchCases(q);
        if (cancelRef.current) return;
        setCaseResults(((data as CasePreview[]) || []).slice(0, 8));
      } catch {
        if (!cancelRef.current) setCaseResults([]);
      } finally {
        if (!cancelRef.current) setIsSearching(false);
      }
    })();
    return () => { cancelRef.current = true; };
  }, [debouncedQuery, searchCases]);

  // Client filter (mevcut clients listesinden)
  const clientResults: ClientPreview[] = useMemo(() => {
    const q = debouncedQuery.trim().toLocaleLowerCase("tr-TR");
    if (q.length < 2) return [];
    return clients
      .filter(c => c.name.toLocaleLowerCase("tr-TR").includes(q))
      .slice(0, 6)
      .map(c => ({ id: c.id, name: c.name, category: c.category }));
  }, [clients, debouncedQuery]);

  const close = () => { setOpen(false); setQuery(""); };

  const go = (path: string) => {
    navigate(path);
    close();
  };

  const isIdle = debouncedQuery.trim().length === 0;
  const hasResults = caseResults.length > 0 || clientResults.length > 0;

  const value: CommandPaletteContextValue = { open, setOpen, toggle };

  return (
    <CommandPaletteContext.Provider value={value}>
      {children}
      <Dialog open={open} onOpenChange={(v) => { if (!v) close(); }}>
        <DialogContent
          className="theme-classic bg-[var(--bg-elevated)] border border-[var(--border-strong)] rounded-none p-0 gap-0 sm:max-w-[720px] overflow-hidden"
          showCloseButton={false as unknown as undefined}
        >
          <Command className="bg-transparent rounded-none">
            {/* Search row */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border)]">
              <Search className="w-4 h-4 text-[var(--fg-subtle)] shrink-0" />
              <CommandInput
                value={query}
                onValueChange={setQuery}
                placeholder="Esas no, müvekkil, mahkeme veya konu ara…"
                className="flex-1 h-9 bg-transparent border-0 text-[15px] placeholder:text-[var(--fg-subtle)] focus:outline-none"
              />
              <kbd className="inline-flex items-center px-1.5 py-0.5 border border-[var(--border)] rounded-[3px] font-mono text-[10px] text-[var(--fg-subtle)] tracking-[0.04em] bg-[var(--bg)]">
                esc
              </kbd>
            </div>

            {/* Body */}
            <CommandList className="max-h-[400px] overflow-y-auto p-0">
              {isIdle ? (
                <>
                  <CommandGroup
                    heading={
                      <span className="font-mono text-[9.5px] tracking-[0.22em] uppercase font-semibold text-[var(--fg-subtle)] px-3 py-2 inline-block">
                        Hızlı Eylemler
                      </span>
                    }
                  >
                    <PaletteItem icon={Upload} label="Belge Yükle" kind="EYLEM" shortcut="G U" onSelect={() => go("/upload")} />
                    <PaletteItem icon={Plus} label="Yeni Dava Aç" kind="EYLEM" shortcut="G N" onSelect={() => go("/new-case/form")} />
                    <PaletteItem icon={User} label="Yeni Müvekkil Ekle" kind="EYLEM" shortcut="G C" onSelect={() => go("/new-client")} />
                  </CommandGroup>

                  <CommandGroup
                    heading={
                      <span className="font-mono text-[9.5px] tracking-[0.22em] uppercase font-semibold text-[var(--fg-subtle)] px-3 py-2 inline-block">
                        Sayfalar
                      </span>
                    }
                  >
                    <PaletteItem icon={Home} label="Anasayfa" kind="SAYFA" onSelect={() => go("/")} />
                    <PaletteItem icon={Upload} label="Belge Yükleme" kind="SAYFA" onSelect={() => go("/upload")} />
                    <PaletteItem icon={FolderOpen} label="Dava Dosyaları" kind="SAYFA" onSelect={() => go("/cases")} />
                    <PaletteItem icon={Users} label="Müvekkiller" kind="SAYFA" onSelect={() => go("/clients")} />
                    <PaletteItem icon={Clock} label="Aktivite Geçmişi" kind="SAYFA" onSelect={() => go("/activity-history")} />
                    {isAdmin && (
                      <PaletteItem icon={ShieldCheck} label="Yönetim Paneli" kind="SAYFA" onSelect={() => go("/admin")} />
                    )}
                  </CommandGroup>
                </>
              ) : (
                <>
                  {isSearching && !hasResults && (
                    <div className="px-3 py-6 text-center font-mono text-[11px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                      Aranıyor…
                    </div>
                  )}

                  {caseResults.length > 0 && (
                    <CommandGroup
                      heading={
                        <span className="font-mono text-[9.5px] tracking-[0.22em] uppercase font-semibold text-[var(--fg-subtle)] px-3 py-2 inline-block">
                          Davalar
                        </span>
                      }
                    >
                      {caseResults.map(c => (
                        <PaletteItem
                          key={`case-${c.id}`}
                          icon={Gavel}
                          label={c.esas_no || c.tracking_no}
                          meta={c.court || c.subject}
                          kind={c.status || "DAVA"}
                          onSelect={() => go(`/cases/${c.id}`)}
                          highlight={debouncedQuery}
                        />
                      ))}
                    </CommandGroup>
                  )}

                  {clientResults.length > 0 && (
                    <CommandGroup
                      heading={
                        <span className="font-mono text-[9.5px] tracking-[0.22em] uppercase font-semibold text-[var(--fg-subtle)] px-3 py-2 inline-block">
                          Müvekkiller
                        </span>
                      }
                    >
                      {clientResults.map(c => (
                        <PaletteItem
                          key={`client-${c.id}`}
                          icon={User}
                          label={c.name}
                          meta={c.category}
                          kind="MÜVEKKİL"
                          onSelect={() => go("/cases", { state: { clientName: c.name } })}
                          highlight={debouncedQuery}
                        />
                      ))}
                    </CommandGroup>
                  )}

                  {!isSearching && !hasResults && (
                    <CommandEmpty>
                      <div className="px-3 py-10 text-center grid gap-3 place-items-center">
                        <Search className="w-7 h-7 text-[var(--fg-subtle)] opacity-50" />
                        <p className="text-[13px] text-[var(--fg-muted)]">
                          "{debouncedQuery}" için sonuç bulunamadı
                        </p>
                      </div>
                    </CommandEmpty>
                  )}
                </>
              )}
            </CommandList>

            {/* Footer */}
            <div className="flex items-center justify-between gap-4 px-4 py-2.5 border-t border-[var(--border)] bg-[var(--bg)] font-mono text-[9.5px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
              <div className="flex items-center gap-3">
                <span className="inline-flex items-center gap-1">
                  <kbd className="px-1 py-0.5 border border-[var(--border)] bg-[var(--bg-elevated)] rounded-[2px]">↑↓</kbd>
                  gez
                </span>
                <span className="inline-flex items-center gap-1">
                  <kbd className="px-1 py-0.5 border border-[var(--border)] bg-[var(--bg-elevated)] rounded-[2px]">↩</kbd>
                  aç
                </span>
                <span className="inline-flex items-center gap-1">
                  <kbd className="px-1 py-0.5 border border-[var(--border)] bg-[var(--bg-elevated)] rounded-[2px]">esc</kbd>
                  kapat
                </span>
              </div>
              <span className="inline-flex items-center gap-1.5 text-[var(--brand)]">
                <Bot className="w-3 h-3" />
                AI Anlamsal Arama
              </span>
            </div>
          </Command>
        </DialogContent>
      </Dialog>
    </CommandPaletteContext.Provider>
  );
}

type IconType = typeof Home;

function PaletteItem({
  icon: Icon,
  label,
  meta,
  kind,
  shortcut,
  onSelect,
  highlight,
}: {
  icon: IconType;
  label: string;
  meta?: string;
  kind?: string;
  shortcut?: string;
  onSelect: () => void;
  highlight?: string;
}) {
  const labelNode = highlight ? <HighlightedText text={label} query={highlight} /> : label;
  return (
    <CommandItem
      onSelect={onSelect}
      className="group flex items-center gap-3 px-3 py-2.5 cursor-pointer rounded-none data-[selected=true]:bg-[var(--brand-soft)] data-[selected=true]:border-l-2 data-[selected=true]:border-l-[var(--brand)] border-l-2 border-transparent"
    >
      <Icon className="w-4 h-4 text-[var(--fg-muted)] group-data-[selected=true]:text-[var(--brand)] shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-[13.5px] text-[var(--fg)] truncate">{labelNode}</div>
        {meta && (
          <div className="text-[11px] text-[var(--fg-subtle)] truncate mt-0.5">
            {meta}
          </div>
        )}
      </div>
      {kind && (
        <span className="font-mono text-[9px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] shrink-0">
          {kind}
        </span>
      )}
      {shortcut && (
        <kbd className="font-mono text-[10px] text-[var(--fg-subtle)] tracking-[0.04em] px-1.5 py-0.5 border border-[var(--border)] bg-[var(--bg)] rounded-[2px] shrink-0">
          {shortcut}
        </kbd>
      )}
    </CommandItem>
  );
}

function HighlightedText({ text, query }: { text: string; query: string }) {
  const idx = text.toLocaleLowerCase("tr-TR").indexOf(query.toLocaleLowerCase("tr-TR"));
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <span className="text-[var(--brand)] font-semibold">{text.slice(idx, idx + query.length)}</span>
      {text.slice(idx + query.length)}
    </>
  );
}

export function useCommandPalette() {
  const ctx = useContext(CommandPaletteContext);
  if (!ctx) throw new Error("useCommandPalette must be used inside <CommandPaletteProvider>");
  return ctx;
}

export { ADMIN_EMAIL };
