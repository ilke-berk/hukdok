import { useState, useEffect, useCallback } from "react";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import {
  Search, Gavel, FolderOpen, Scale, FileText,
  Plus, ChevronRight, ChevronLeft,
  Briefcase, Copy, Check,
  TrendingUp, AlertCircle, Loader2, X,
} from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";
import { useCases } from "../hooks/useCases";
import { useConfig } from "../hooks/useConfig";
import { toast } from "sonner";
import { useDebounce } from "../hooks/useDebounce";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { MetricCard, SectionHeader, HairlineCard, Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";

interface Case {
  id: number;
  tracking_no: string;
  esas_no?: string;
  status: string;
  court?: string;
  opening_date?: string;
  responsible_lawyer_name?: string;
  file_type?: string;
  subject?: string;
  hasar_dosya_no?: string;
  hukuk_no?: string;
  parties?: { party_type: string; name: string; role: string }[];
}

const ITEMS_PER_PAGE = 15;

const STATUS_OPTIONS = ["ALL", "DERDEST", "KARAR", "ISTINAF", "TEMYIZ", "KAPALI"] as const;

const STATUS_TONE: Record<string, string> = {
  DERDEST: "text-[#2f8a5d] border-[#2f8a5d]/30 bg-[#2f8a5d]/10",
  ISTINAF: "text-[#c47a1e] border-[#c47a1e]/30 bg-[#c47a1e]/10",
  TEMYIZ: "text-[#7a3f8a] border-[#7a3f8a]/30 bg-[#7a3f8a]/10",
  KARAR: "text-[var(--brand)] border-[var(--brand)]/35 bg-[var(--brand-soft)]",
  KAPALI: "text-[var(--fg-subtle)] border-[var(--border)] bg-[var(--bg-sunken)]",
};

function StatusChip({ status }: { status: string }) {
  const tone = STATUS_TONE[status] || STATUS_TONE.KAPALI;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-mono tracking-[0.14em] uppercase border ${tone}`}>
      {status}
    </span>
  );
}

function CopyBadge({ value, icon: Icon }: { value: string; icon: typeof FileText }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      title={`${value} — Kopyala`}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 font-mono text-[10px] tracking-[0.04em] border border-[var(--border)] bg-[var(--bg-sunken)] text-[var(--fg-muted)] hover:text-[var(--fg)] hover:border-[var(--border-strong)] transition-colors"
    >
      <Icon className="w-2.5 h-2.5 shrink-0 opacity-70" />
      <span className="truncate max-w-[110px]">{value}</span>
      {copied ? <Check className="w-2.5 h-2.5 text-[var(--brand)]" /> : <Copy className="w-2.5 h-2.5 opacity-50" />}
    </button>
  );
}

const CaseList = () => {
  useSetPageTitle("Dava Dosyaları", ["Avukat Paneli", "Davalar"]);
  const navigate = useNavigate();
  const location = useLocation();
  const { getCases, getCaseStats } = useCases();
  const { lawyers } = useConfig();

  // Core data state
  const [cases, setCases] = useState<Case[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [stats, setStats] = useState({ total: 0, active: 0, closed: 0, appeal: 0 });
  const [isLoading, setIsLoading] = useState(true);

  // Filter states
  const [searchQuery, setSearchQuery] = useState(
    (location.state as { clientName?: string })?.clientName ?? ""
  );
  const debouncedSearch = useDebounce(searchQuery, 400);
  const [selectedStatus, setSelectedStatus] = useState<string>("ALL");
  const [selectedLawyer, setSelectedLawyer] = useState<string>("ALL");
  const [selectedFileType, setSelectedFileType] = useState<string>("ALL");
  const [currentPage, setCurrentPage] = useState(1);

  const noFilterActive = !debouncedSearch && selectedStatus === "ALL" && selectedLawyer === "ALL" && selectedFileType === "ALL";

  const fetchCases = useCallback(async () => {
    if (noFilterActive) {
      setCases([]);
      setTotalCount(0);
      setIsLoading(false);
      return;
    }
    try {
      setIsLoading(true);
      const offset = (currentPage - 1) * ITEMS_PER_PAGE;
      const data = await getCases({
        limit: ITEMS_PER_PAGE,
        offset,
        status: selectedStatus,
        lawyer: selectedLawyer,
        q: debouncedSearch || undefined,
      });
      if (Array.isArray(data)) {
        setCases(data);
        setTotalCount(data.length > 0 ? (currentPage * ITEMS_PER_PAGE + (data.length === ITEMS_PER_PAGE ? 1 : 0)) : 0);
      } else if (data && data.cases) {
        setCases(data.cases);
        setTotalCount(data.total || 0);
      }
    } catch (error) {
      console.error(error);
      toast.error("Dosyalar yüklenirken bir hata oluştu.");
    } finally {
      setIsLoading(false);
    }
  }, [getCases, currentPage, selectedStatus, selectedLawyer, selectedFileType, debouncedSearch, noFilterActive]);

  const fetchStats = useCallback(async () => {
    try {
      const statsData = await getCaseStats();
      if (statsData) setStats(statsData);
    } catch (error) {
      console.error("İstatistikler yüklenemedi", error);
    }
  }, [getCaseStats]);

  useEffect(() => { fetchCases(); }, [fetchCases]);
  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => { setCurrentPage(1); }, [debouncedSearch, selectedStatus, selectedLawyer, selectedFileType]);

  const clearFilters = () => {
    setSelectedStatus("ALL");
    setSelectedLawyer("ALL");
    setSelectedFileType("ALL");
    setSearchQuery("");
  };

  const totalPages = Math.ceil(totalCount / ITEMS_PER_PAGE) || 1;
  const activeFilterCount = [
    debouncedSearch && "search",
    selectedStatus !== "ALL" && "status",
    selectedLawyer !== "ALL" && "lawyer",
    selectedFileType !== "ALL" && "filetype",
  ].filter(Boolean).length;

  return (
    <div className="grid gap-7 max-w-[1600px]">

      {/* Üst başlık */}
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <Eyebrow>01 · Liste</Eyebrow>
          <h1 className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium">
            Dava Dosyaları
          </h1>
        </div>
        <FlowButton variant="primary" onClick={() => navigate("/new-case/form")}>
          <Plus className="w-3.5 h-3.5" />
          Yeni Dava Aç
        </FlowButton>
      </div>

      {/* Metrikler */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Aktif (Derdest)"
          value={stats.active}
          icon={<TrendingUp className="w-4 h-4" />}
          tone="success"
          hint="Süren davalar"
          onClick={() => setSelectedStatus("DERDEST")}
        />
        <MetricCard
          label="İstinaf / Temyiz"
          value={stats.appeal}
          icon={<AlertCircle className="w-4 h-4" />}
          tone="warning"
          hint="Üst yargı"
          onClick={() => setSelectedStatus("ISTINAF")}
        />
        <MetricCard
          label="Kapalı"
          value={stats.closed}
          icon={<FolderOpen className="w-4 h-4" />}
          tone="neutral"
          hint="Karar / İnfaz"
          onClick={() => setSelectedStatus("KAPALI")}
        />
        <MetricCard
          label="Toplam Dava"
          value={stats.total}
          icon={<Scale className="w-4 h-4" />}
          tone="brand"
          hint="Tüm dosyalar"
          onClick={() => setSelectedStatus("ALL")}
        />
      </section>

      {/* Arama */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--fg-subtle)] pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Esas no, müvekkil adı veya konu ile ara…"
            className="w-full h-11 pl-10 pr-10 bg-[var(--bg-elevated)] border border-[var(--border)] text-[14px] text-[var(--fg)] placeholder:text-[var(--fg-subtle)] focus:border-[var(--brand)] focus:outline-none transition-colors rounded-[3px]"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-[var(--fg-subtle)] hover:text-[var(--brand)] transition-colors"
              aria-label="Aramayı temizle"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
        {activeFilterCount > 0 && (
          <FlowButton variant="ghost" size="sm" onClick={clearFilters}>
            <X className="w-3 h-3" />
            {activeFilterCount} filtre · temizle
          </FlowButton>
        )}
      </div>

      {/* Filtre rail + Tablo */}
      <section className="grid grid-cols-1 xl:grid-cols-[260px_1fr] gap-5 items-start">
        {/* Filtre rail */}
        <HairlineCard className="flex flex-col gap-6 sticky top-2">
          <div>
            <Eyebrow>Durum</Eyebrow>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {STATUS_OPTIONS.map(s => {
                const active = selectedStatus === s;
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSelectedStatus(s)}
                    className={[
                      "px-2.5 py-1 font-mono text-[10px] tracking-[0.1em] uppercase border transition-colors",
                      active
                        ? "bg-[var(--brand)] text-[var(--brand-fg)] border-[var(--brand)]"
                        : "bg-transparent text-[var(--fg-muted)] border-[var(--border)] hover:border-[var(--border-strong)] hover:text-[var(--fg)]",
                    ].join(" ")}
                  >
                    {s === "ALL" ? "Tümü" : s}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <Eyebrow>Sorumlu Avukat</Eyebrow>
            <Select value={selectedLawyer} onValueChange={setSelectedLawyer}>
              <SelectTrigger className="mt-2 h-10 bg-[var(--bg)] border-[var(--border)] text-[13px] rounded-[3px]">
                <SelectValue placeholder="Avukat seçin" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">Tüm Avukatlar</SelectItem>
                {lawyers.map(l => (
                  <SelectItem key={l.name} value={l.name}>{l.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Eyebrow>Dosya Türü</Eyebrow>
            <Select value={selectedFileType} onValueChange={setSelectedFileType}>
              <SelectTrigger className="mt-2 h-10 bg-[var(--bg)] border-[var(--border)] text-[13px] rounded-[3px]">
                <SelectValue placeholder="Tür seçin" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">Tüm Türler</SelectItem>
                <SelectItem value="Hukuk">Hukuk</SelectItem>
                <SelectItem value="Ceza">Ceza</SelectItem>
                <SelectItem value="İcra">İcra</SelectItem>
                <SelectItem value="İdari">İdari</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </HairlineCard>

        {/* Tablo */}
        <HairlineCard padded={false}>
          <div className="flex items-baseline justify-between px-5 py-4 border-b border-[var(--border)]">
            <SectionHeader
              title={debouncedSearch ? "Arama Sonuçları" : "Filtreli Dosyalar"}
              italic={debouncedSearch ? `— "${debouncedSearch}"` : undefined}
              className="flex-1"
              meta={
                <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                  {noFilterActive ? "Filtre seçin" : isLoading ? "Yükleniyor…" : `${cases.length} kayıt`}
                </span>
              }
            />
          </div>

          {noFilterActive ? (
            <div className="grid place-items-center gap-3 py-20 text-center text-[var(--fg-subtle)]">
              <Search className="w-9 h-9 opacity-30" />
              <p className="text-[13px] max-w-[40ch]">
                Arama yapın veya soldaki bir filtreyi seçin — listeler büyük olduğu için
                varsayılan olarak yüklenmiyor.
              </p>
            </div>
          ) : isLoading ? (
            <div className="grid place-items-center gap-3 py-20 text-[var(--fg-subtle)]">
              <Loader2 className="w-7 h-7 animate-spin" />
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase">Yükleniyor</span>
            </div>
          ) : cases.length === 0 ? (
            <div className="grid place-items-center gap-3 py-20 text-center text-[var(--fg-subtle)]">
              <X className="w-9 h-9 opacity-30" />
              <p className="text-[13px]">Bu kriterlere uygun dosya bulunamadı.</p>
              <FlowButton variant="secondary" size="sm" onClick={clearFilters}>
                Filtreleri temizle
              </FlowButton>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-[var(--bg)] border-b border-[var(--border)]">
                    <th className="text-left px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">Müvekkil</th>
                    <th className="text-left px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">Esas / Ofis No</th>
                    <th className="text-left px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">Mahkeme · Konu</th>
                    <th className="text-left px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">Avukat</th>
                    <th className="text-right px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">Durum</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map(c => {
                    const client = c.parties?.find(p => p.party_type === "CLIENT")?.name || "—";
                    return (
                      <tr
                        key={c.id}
                        onClick={() => navigate(`/cases/${c.id}`)}
                        className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--bg)] cursor-pointer transition-colors"
                      >
                        <td className="px-5 py-4 align-top">
                          <div className="font-display text-[14px] font-medium text-[var(--fg)] truncate max-w-[200px]">
                            {client}
                          </div>
                          <div className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] mt-1">
                            Müvekkil
                          </div>
                        </td>
                        <td className="px-5 py-4 align-top">
                          <div className="font-mono text-[13px] tabular-nums text-[var(--fg)] font-medium">
                            {c.esas_no || "—"}
                          </div>
                          <div className="flex items-center gap-1.5 mt-1">
                            <Briefcase className="w-3 h-3 text-[var(--fg-subtle)]" />
                            <span className="font-mono text-[10px] tracking-[0.04em] text-[var(--fg-subtle)]">
                              {c.tracking_no}
                            </span>
                          </div>
                          {(c.hasar_dosya_no || c.hukuk_no) && (
                            <div className="flex flex-wrap gap-1 mt-1.5">
                              {c.hasar_dosya_no && <CopyBadge value={c.hasar_dosya_no} icon={FileText} />}
                              {c.hukuk_no && <CopyBadge value={c.hukuk_no} icon={Scale} />}
                            </div>
                          )}
                        </td>
                        <td className="px-5 py-4 align-top">
                          <div className="text-[13px] text-[var(--fg)] leading-snug truncate max-w-[320px]">
                            {c.court || "—"}
                          </div>
                          {c.subject && (
                            <div className="text-[11px] text-[var(--fg-muted)] italic mt-1 truncate max-w-[320px]">
                              {c.subject}
                            </div>
                          )}
                        </td>
                        <td className="px-5 py-4 align-top">
                          <span className="text-[12px] text-[var(--fg-muted)]">
                            {c.responsible_lawyer_name?.split(" ")[0] || "Atanmadı"}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-right align-top">
                          <StatusChip status={c.status} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {totalCount > 0 && (
            <div className="flex items-center justify-between px-5 py-3 border-t border-[var(--border)] bg-[var(--bg)]">
              <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                {cases.length} / {totalCount} kayıt
              </span>
              <div className="flex items-center gap-2">
                <FlowButton
                  variant="ghost"
                  size="sm"
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage(p => p - 1)}
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  Geri
                </FlowButton>
                <span className="font-mono text-[11px] tabular-nums px-2.5 py-1 border border-[var(--border)] bg-[var(--bg-elevated)]">
                  {currentPage} / {totalPages}
                </span>
                <FlowButton
                  variant="ghost"
                  size="sm"
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage(p => p + 1)}
                >
                  İleri
                  <ChevronRight className="w-3.5 h-3.5" />
                </FlowButton>
              </div>
            </div>
          )}
        </HairlineCard>
      </section>
    </div>
  );
};

export default CaseList;
