import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
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

const ADMIN_EMAIL = "ilkekutluk@lexisbio.onmicrosoft.com";

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

/**
 * Liste dışı sayfalarda üst barın altında açılan global arama paneli.
 * Modal değildir; davaları + müvekkilleri tarar, seçince ilgili sayfaya gider.
 * Boşken hızlı eylemler ve sayfa kısayollarını gösterir.
 */
export function GlobalSearchDropdown({
  query,
  onClose,
}: {
  query: string;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const debouncedQuery = useDebounce(query, 200);
  const { searchCases } = useCases();
  const { clients } = useClients();
  const { accounts } = useMsal();
  const isAdmin = (accounts[0]?.username || "").toLowerCase() === ADMIN_EMAIL.toLowerCase();

  const [caseResults, setCaseResults] = useState<CasePreview[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const cancelRef = useRef(false);

  // Sorgu değişince dava araması
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
    return () => {
      cancelRef.current = true;
    };
  }, [debouncedQuery, searchCases]);

  // Müvekkil filtresi (yüklü listeden)
  const clientResults: ClientPreview[] = useMemo(() => {
    const q = debouncedQuery.trim().toLocaleLowerCase("tr-TR");
    if (q.length < 2) return [];
    return clients
      .filter(c => c.name.toLocaleLowerCase("tr-TR").includes(q))
      .slice(0, 6)
      .map(c => ({ id: c.id, name: c.name, category: c.category }));
  }, [clients, debouncedQuery]);

  const go = (path: string, state?: Record<string, unknown>) => {
    navigate(path, state ? { state } : undefined);
    onClose();
  };

  const isIdle = debouncedQuery.trim().length === 0;
  const hasResults = caseResults.length > 0 || clientResults.length > 0;

  return (
    <div className="absolute left-0 right-0 top-full mt-2 z-50 bg-[var(--bg-elevated)] border border-[var(--border-strong)] rounded-[4px] overflow-hidden shadow-[0_18px_50px_-12px_rgba(0,0,0,0.45)]">
      <div className="max-h-[400px] overflow-y-auto">
        {isIdle ? (
          <>
            <GroupHeading>Hızlı Eylemler</GroupHeading>
            <ResultItem icon={Upload} label="Belge Yükle" kind="EYLEM" onSelect={() => go("/upload")} />
            <ResultItem icon={Plus} label="Yeni Dava Aç" kind="EYLEM" onSelect={() => go("/new-case/form")} />
            <ResultItem icon={User} label="Yeni Müvekkil Ekle" kind="EYLEM" onSelect={() => go("/new-client")} />

            <GroupHeading>Sayfalar</GroupHeading>
            <ResultItem icon={Home} label="Anasayfa" kind="SAYFA" onSelect={() => go("/")} />
            <ResultItem icon={Upload} label="Belge Yükleme" kind="SAYFA" onSelect={() => go("/upload")} />
            <ResultItem icon={FolderOpen} label="Dava Dosyaları" kind="SAYFA" onSelect={() => go("/cases")} />
            <ResultItem icon={Users} label="Müvekkiller" kind="SAYFA" onSelect={() => go("/clients")} />
            <ResultItem icon={Clock} label="Aktivite Geçmişi" kind="SAYFA" onSelect={() => go("/activity-history")} />
            {isAdmin && (
              <ResultItem icon={ShieldCheck} label="Yönetim Paneli" kind="SAYFA" onSelect={() => go("/admin")} />
            )}
          </>
        ) : (
          <>
            {isSearching && !hasResults && (
              <div className="px-3 py-6 text-center font-mono text-[11px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                Aranıyor…
              </div>
            )}

            {caseResults.length > 0 && (
              <>
                <GroupHeading>Davalar</GroupHeading>
                {caseResults.map(c => (
                  <ResultItem
                    key={`case-${c.id}`}
                    icon={Gavel}
                    label={c.esas_no || c.tracking_no}
                    meta={c.court || c.subject}
                    kind={c.status || "DAVA"}
                    onSelect={() => go(`/cases/${c.id}`)}
                    highlight={debouncedQuery}
                  />
                ))}
              </>
            )}

            {clientResults.length > 0 && (
              <>
                <GroupHeading>Müvekkiller</GroupHeading>
                {clientResults.map(c => (
                  <ResultItem
                    key={`client-${c.id}`}
                    icon={User}
                    label={c.name}
                    meta={c.category}
                    kind="MÜVEKKİL"
                    onSelect={() => go("/cases", { clientName: c.name })}
                    highlight={debouncedQuery}
                  />
                ))}
              </>
            )}

            {!isSearching && !hasResults && (
              <div className="px-3 py-10 text-center grid gap-3 place-items-center">
                <Search className="w-7 h-7 text-[var(--fg-subtle)] opacity-50" />
                <p className="text-[13px] text-[var(--fg-muted)]">
                  "{debouncedQuery}" için sonuç bulunamadı
                </p>
              </div>
            )}
          </>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between gap-4 px-4 py-2.5 border-t border-[var(--border)] bg-[var(--bg)] font-mono text-[9.5px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
        <span className="inline-flex items-center gap-1">
          <kbd className="px-1 py-0.5 border border-[var(--border)] bg-[var(--bg-elevated)] rounded-[2px]">esc</kbd>
          kapat
        </span>
        <span className="inline-flex items-center gap-1.5 text-[var(--brand)]">
          <Bot className="w-3 h-3" />
          AI Anlamsal Arama
        </span>
      </div>
    </div>
  );
}

type IconType = typeof Home;

function GroupHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[9.5px] tracking-[0.22em] uppercase font-semibold text-[var(--fg-subtle)] px-3 py-2">
      {children}
    </div>
  );
}

function ResultItem({
  icon: Icon,
  label,
  meta,
  kind,
  onSelect,
  highlight,
}: {
  icon: IconType;
  label: string;
  meta?: string;
  kind?: string;
  onSelect: () => void;
  highlight?: string;
}) {
  const labelNode = highlight ? <HighlightedText text={label} query={highlight} /> : label;
  return (
    <button
      type="button"
      // input blur'undan önce seçim çalışsın diye mousedown kullanıyoruz
      onMouseDown={(e) => {
        e.preventDefault();
        onSelect();
      }}
      className="group w-full text-left flex items-center gap-3 px-3 py-2.5 cursor-pointer border-l-2 border-transparent hover:bg-[var(--brand-soft)] hover:border-l-[var(--brand)] transition-colors"
    >
      <Icon className="w-4 h-4 text-[var(--fg-muted)] group-hover:text-[var(--brand)] shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-[13.5px] text-[var(--fg)] truncate">{labelNode}</div>
        {meta && (
          <div className="text-[11px] text-[var(--fg-subtle)] truncate mt-0.5">{meta}</div>
        )}
      </div>
      {kind && (
        <span className="font-mono text-[9px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] shrink-0">
          {kind}
        </span>
      )}
    </button>
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
