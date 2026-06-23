import { useState, useEffect, useCallback } from "react";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { useCases } from "@/hooks/useCases";
import { useDebounce } from "@/hooks/useDebounce";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { FileText, Search, Loader2, Link2, Inbox, User, Calendar, X } from "lucide-react";

interface UnlinkedDoc {
  id: number;
  original_filename: string;
  belge_turu_adi?: string | null;
  muvekkil_adi?: string | null;
  esas_no?: string | null;
  uploaded_at?: string | null;
  uploaded_by?: string | null;
}

interface CaseResult {
  id: number;
  tracking_no: string;
  esas_no?: string | null;
  court?: string | null;
  status: string;
}

const formatDate = (iso?: string | null) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("tr-TR", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return "—";
  }
};

// ── Tek belge satırı: bilgiler + davaya bağlama arama kutusu ───────────────
const DocRow = ({ doc, onLinked }: { doc: UnlinkedDoc; onLinked: (docId: number) => void }) => {
  const { searchCases, linkDocument } = useCases();

  const [query, setQuery] = useState("");
  const debounced = useDebounce(query, 350);
  const [results, setResults] = useState<CaseResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [linkingId, setLinkingId] = useState<number | null>(null);

  useEffect(() => {
    if (!debounced || debounced.length < 2) {
      setResults([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setSearching(true);
      const data = await searchCases(debounced);
      if (cancelled) return;
      setResults((Array.isArray(data) ? data : data?.cases ?? []).slice(0, 8));
      setSearching(false);
    })();
    return () => { cancelled = true; };
  }, [debounced, searchCases]);

  const handleLink = async (c: CaseResult) => {
    setLinkingId(c.id);
    const ok = await linkDocument(doc.id, c.id);
    setLinkingId(null);
    if (ok) {
      toast.success(`📎 Belge "${c.esas_no || c.tracking_no}" davasına bağlandı.`);
      onLinked(doc.id);
    } else {
      toast.error("Belge bağlanamadı. Lütfen tekrar deneyin.");
    }
  };

  return (
    <div className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-[3px] p-4 grid gap-3 md:grid-cols-[1fr_auto] md:items-start">
      {/* Belge bilgileri */}
      <div className="min-w-0 space-y-1.5">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-[var(--brand)] shrink-0" />
          <span className="text-sm font-semibold truncate" title={doc.original_filename}>
            {doc.original_filename}
          </span>
          {doc.belge_turu_adi && (
            <Badge variant="outline" className="text-[10px] shrink-0">{doc.belge_turu_adi}</Badge>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--fg-muted)] pl-6">
          {doc.muvekkil_adi && (
            <span className="inline-flex items-center gap-1"><User className="w-3 h-3" />{doc.muvekkil_adi}</span>
          )}
          {doc.esas_no && (
            <span className="inline-flex items-center gap-1 tabular-nums">Esas: {doc.esas_no}</span>
          )}
          <span className="inline-flex items-center gap-1"><Calendar className="w-3 h-3" />{formatDate(doc.uploaded_at)}</span>
          {doc.uploaded_by && <span className="truncate">· {doc.uploaded_by}</span>}
        </div>
      </div>

      {/* Davaya bağlama arama kutusu */}
      <div className="md:w-[300px] w-full">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--fg-muted)]" />
          <Input
            className="pl-9 h-9 text-sm"
            placeholder="Esas no, mahkeme veya müvekkil ile ara..."
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          {searching && <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 animate-spin text-[var(--fg-muted)]" />}
          {query && !searching && (
            <button
              type="button"
              onClick={() => { setQuery(""); setResults([]); }}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--fg-muted)] hover:text-[var(--fg)]"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {debounced.length >= 2 && (
          <div className="mt-1 border border-[var(--border)] rounded-[3px] overflow-hidden max-h-56 overflow-y-auto">
            {results.length === 0 ? (
              <p className="px-3 py-2.5 text-xs text-[var(--fg-muted)] text-center">
                {searching ? "Aranıyor..." : "Sonuç bulunamadı"}
              </p>
            ) : (
              results.map(c => (
                <button
                  key={c.id}
                  type="button"
                  disabled={linkingId != null}
                  onClick={() => handleLink(c)}
                  className="w-full text-left px-3 py-2 hover:bg-[var(--brand-soft)] transition-colors border-b border-[var(--border)]/40 last:border-0 disabled:opacity-50"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium truncate tabular-nums">{c.esas_no || c.tracking_no}</span>
                    {linkingId === c.id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                    ) : (
                      <Badge variant="outline" className="text-[10px] shrink-0">{c.status}</Badge>
                    )}
                  </div>
                  <p className="text-xs text-[var(--fg-muted)] truncate mt-0.5">{c.court || "Mahkeme yok"}</p>
                </button>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};

const UnlinkedDocuments = () => {
  useSetPageTitle("Bağlantısız Belgeler", ["Belge", "Bağlantısız"]);
  const { getDocuments } = useCases();

  const [docs, setDocs] = useState<UnlinkedDoc[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const data = await getDocuments("UNLINKED", 200);
    setDocs(Array.isArray(data) ? data : []);
    setLoading(false);
  }, [getDocuments]);

  useEffect(() => { load(); }, [load]);

  const handleLinked = (docId: number) => {
    setDocs(prev => prev.filter(d => d.id !== docId));
  };

  return (
    <main className="flex-1 container mx-auto py-6 px-4 space-y-5">
      <div className="flex items-center gap-3">
        <Link2 className="w-5 h-5 text-[var(--brand)]" />
        <div>
          <h1 className="text-lg font-semibold">Bağlantısız Belgeler</h1>
          <p className="text-sm text-[var(--fg-muted)]">
            Bir davaya bağlanmadan yüklenmiş belgeler. Arayıp ilgili davaya bağlayın.
          </p>
        </div>
        {!loading && (
          <Badge variant="secondary" className="ml-auto text-xs">{docs.length}</Badge>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-24 w-full rounded-[3px]" />)}
        </div>
      ) : docs.length === 0 ? (
        <div className="text-center py-20 border border-dashed border-[var(--border)] rounded-[3px] text-[var(--fg-muted)]">
          <Inbox className="w-10 h-10 opacity-20 mx-auto mb-3" />
          <p className="font-medium text-[var(--fg)]">Bağlantısız belge yok</p>
          <p className="text-sm mt-1">Tüm belgeler bir davaya bağlı. 🎉</p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {docs.map(doc => (
            <DocRow key={doc.id} doc={doc} onLinked={handleLinked} />
          ))}
        </div>
      )}
    </main>
  );
};

export default UnlinkedDocuments;
