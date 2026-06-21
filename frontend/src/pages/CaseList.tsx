import { useState, useEffect, useCallback, useMemo } from "react";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { usePageSearch } from "@/components/system/PageSearch";
import {
  Search, FolderOpen, Scale, FileText,
  Plus, ChevronRight, ChevronLeft,
  Briefcase, Copy, Check, HelpCircle,
  TrendingUp, Loader2, RefreshCw, AlertTriangle,
  SlidersHorizontal, CalendarClock,
} from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";
import { useCases } from "../hooks/useCases";
import { useConfig } from "../hooks/useConfig";
import { apiClient } from "@/lib/api";
import { toast } from "sonner";
import { useDebounce } from "../hooks/useDebounce";
import { formatAgo } from "@/lib/relativeTime";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { MetricCard, HairlineCard, Eyebrow } from "@/components/dashboard/primitives";
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
  updated_at?: string;
  dosya_son_durumu?: string;
  parties?: { party_type: string; name: string; role: string }[];
}

interface Hearing {
  case_id: number;
  hearing_date: string;
}

interface CalEvent {
  id: number;
  title: string;
  event_date: string;
}

const ITEMS_PER_PAGE = 15;

// Yaklaşan uyarısı için pencere (gün)
const URGENT_WINDOW_DAYS = 7;

// Durum çipi sıralama önceliği — bilinmeyenler ortada, MAHZEN/KAPALI sonda
const STATUS_ORDER = ["DANIŞ", "DERDEST", "ISTINAF", "TEMYIZ", "KARAR", "KAPALI", "MAHZEN"];

const STATUS_TONE: Record<string, string> = {
  DANIŞ: "text-[#3b6fa0] border-[#3b6fa0]/30 bg-[#3b6fa0]/10",
  DERDEST: "text-[#2f8a5d] border-[#2f8a5d]/30 bg-[#2f8a5d]/10",
  MAHZEN: "text-[var(--fg-subtle)] border-[var(--border)] bg-[var(--bg-sunken)]",
  // Eski kayıtlar için tonlar
  ISTINAF: "text-[#c47a1e] border-[#c47a1e]/30 bg-[#c47a1e]/10",
  TEMYIZ: "text-[#7a3f8a] border-[#7a3f8a]/30 bg-[#7a3f8a]/10",
  KARAR: "text-[var(--brand)] border-[var(--brand)]/35 bg-[var(--brand-soft)]",
  KAPALI: "text-[var(--fg-subtle)] border-[var(--border)] bg-[var(--bg-sunken)]",
};

function StatusChip({ status }: { status: string }) {
  const tone = STATUS_TONE[status] || STATUS_TONE.MAHZEN;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-mono tracking-[0.14em] uppercase border ${tone}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" />
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

// Ad → baş harf avatarı (en fazla 2 harf)
function initials(name?: string): string {
  if (!name) return "—";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "—";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// Tarih (yyyy-mm-dd…) → bugünden itibaren kalan gün sayısı (yerel)
function daysUntil(dateStr: string): number {
  const d = new Date(dateStr.slice(0, 10) + "T00:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / 86400000);
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
  const [stats, setStats] = useState<{
    total: number; active: number; closed: number; danis_active: number;
    statuses: Record<string, number>;
  }>({ total: 0, active: 0, closed: 0, danis_active: 0, statuses: {} });
  const [isLoading, setIsLoading] = useState(true);

  // Takvim verisi — yaklaşan uyarıları için
  const [hearings, setHearings] = useState<Hearing[]>([]);
  const [calEvents, setCalEvents] = useState<CalEvent[]>([]);

  // Filter states — arama tek mutlak üst bardan sürülür (usePageSearch)
  const { query: searchQuery, setQuery: setSearchQuery } = usePageSearch({
    placeholder: "Esas no, müvekkil adı veya konu ile ara…",
    seed: (location.state as { clientName?: string })?.clientName,
  });
  const debouncedSearch = useDebounce(searchQuery, 400);
  const [selectedStatus, setSelectedStatus] = useState<string>("ALL");
  const [selectedLawyer, setSelectedLawyer] = useState<string>("ALL");
  const [selectedFileType, setSelectedFileType] = useState<string>("ALL");
  const [onlyUrgent, setOnlyUrgent] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);

  const fetchCases = useCallback(async () => {
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
  }, [getCases, currentPage, selectedStatus, selectedLawyer, selectedFileType, debouncedSearch]);

  const fetchStats = useCallback(async () => {
    try {
      const statsData = await getCaseStats();
      if (statsData) setStats({ statuses: {}, ...statsData });
    } catch (error) {
      console.error("İstatistikler yüklenemedi", error);
    }
  }, [getCaseStats]);

  const fetchCalendar = useCallback(() => {
    apiClient.fetch("/api/hearing-dates")
      .then(r => r.ok ? r.json() : Promise.resolve([]))
      .then((d: unknown) => setHearings(Array.isArray(d) ? (d as Hearing[]) : []))
      .catch(() => setHearings([]));
    apiClient.fetch("/api/calendar-events")
      .then(r => r.ok ? r.json() : Promise.resolve([]))
      .then((d: unknown) => setCalEvents(Array.isArray(d) ? (d as CalEvent[]) : []))
      .catch(() => setCalEvents([]));
  }, []);

  useEffect(() => { fetchCases(); }, [fetchCases]);
  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => { fetchCalendar(); }, [fetchCalendar]);
  useEffect(() => { setCurrentPage(1); }, [debouncedSearch, selectedStatus, selectedLawyer, selectedFileType]);

  // case_id → en yakın yaklaşan duruşmaya kalan gün (0..URGENT_WINDOW_DAYS)
  const urgentByCase = useMemo(() => {
    const map = new Map<number, number>();
    for (const h of hearings) {
      if (!h.hearing_date) continue;
      const days = daysUntil(h.hearing_date);
      if (days < 0 || days > URGENT_WINDOW_DAYS) continue;
      const prev = map.get(h.case_id);
      if (prev === undefined || days < prev) map.set(h.case_id, days);
    }
    return map;
  }, [hearings]);

  // Önümüzdeki 7 gündeki serbest takvim işaretleri (süre sonu vb.) — davaya bağlı değil
  const upcomingMarks = useMemo(
    () => calEvents.filter(e => {
      if (!e.event_date) return false;
      const days = daysUntil(e.event_date);
      return days >= 0 && days <= URGENT_WINDOW_DAYS;
    }),
    [calEvents],
  );

  const clearFilters = () => {
    setSelectedStatus("ALL");
    setSelectedLawyer("ALL");
    setSelectedFileType("ALL");
    setOnlyUrgent(false);
    setSearchQuery("");
  };

  // Durum çipleri — stats.statuses'tan dinamik üretilir
  const statusChips = useMemo(() => {
    const keys = Object.keys(stats.statuses || {});
    keys.sort((a, b) => {
      const ia = STATUS_ORDER.indexOf(a); const ib = STATUS_ORDER.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
    return keys;
  }, [stats.statuses]);

  const activeFilterCount = [
    debouncedSearch && "search",
    selectedStatus !== "ALL" && "status",
    selectedLawyer !== "ALL" && "lawyer",
    selectedFileType !== "ALL" && "filetype",
    onlyUrgent && "urgent",
  ].filter(Boolean).length;

  // Sayfada gösterilen liste (onlyUrgent ise sayfa içi süzme)
  const displayedCases = useMemo(
    () => onlyUrgent ? cases.filter(c => urgentByCase.has(c.id)) : cases,
    [cases, onlyUrgent, urgentByCase],
  );

  // Üst bardaki "N DOSYA" — mümkün olduğunca gerçek sayım
  const headerCount = useMemo(() => {
    if (onlyUrgent) return displayedCases.length;
    const onlyStatus = !debouncedSearch && selectedLawyer === "ALL" && selectedFileType === "ALL";
    if (onlyStatus && selectedStatus === "ALL") return stats.total;
    if (onlyStatus && stats.statuses[selectedStatus] !== undefined) return stats.statuses[selectedStatus];
    return displayedCases.length;
  }, [onlyUrgent, displayedCases.length, debouncedSearch, selectedLawyer, selectedFileType, selectedStatus, stats]);

  const totalPages = Math.ceil(totalCount / ITEMS_PER_PAGE) || 1;

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
          label="Danış"
          value={stats.danis_active}
          icon={<HelpCircle className="w-4 h-4" />}
          tone="neutral"
          hint="Danışma aşaması"
          onClick={() => setSelectedStatus("DANIŞ")}
        />
        <MetricCard
          label="Aktif (Derdest)"
          value={stats.active}
          icon={<TrendingUp className="w-4 h-4" />}
          tone="neutral"
          hint="Süren davalar"
          onClick={() => setSelectedStatus("DERDEST")}
        />
        <MetricCard
          label="Kapalı"
          value={stats.closed}
          icon={<FolderOpen className="w-4 h-4" />}
          tone="neutral"
          hint="Mahzen / Arşiv"
          onClick={() => setSelectedStatus("MAHZEN")}
        />
        <MetricCard
          label="Toplam Dava"
          value={stats.total}
          icon={<Scale className="w-4 h-4" />}
          tone="neutral"
          hint="Tüm dosyalar"
          onClick={() => setSelectedStatus("ALL")}
        />
      </section>

      {/* Filtre rail + Tablo */}
      <section className="grid grid-cols-1 xl:grid-cols-[260px_1fr] gap-5 items-start">
        {/* Filtre rail */}
        <HairlineCard className="flex flex-col gap-6 sticky top-2">
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] uppercase text-[var(--fg)] font-semibold">
              <SlidersHorizontal className="w-3.5 h-3.5 text-[var(--fg-muted)]" />
              Dosya Filtrele
            </span>
            {activeFilterCount > 0 && (
              <button
                type="button"
                onClick={clearFilters}
                className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] transition-colors"
              >
                Temizle
              </button>
            )}
          </div>

          <div>
            <Eyebrow>Durum</Eyebrow>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <ChipButton
                active={selectedStatus === "ALL"}
                label="Tümü"
                count={stats.total}
                onClick={() => setSelectedStatus("ALL")}
              />
              {statusChips.map(s => (
                <ChipButton
                  key={s}
                  active={selectedStatus === s}
                  label={s}
                  count={stats.statuses[s]}
                  onClick={() => setSelectedStatus(s)}
                />
              ))}
            </div>
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

          <div>
            <Eyebrow>Sorumlu Avukat</Eyebrow>
            <Select value={selectedLawyer} onValueChange={setSelectedLawyer}>
              <SelectTrigger className="mt-2 h-10 bg-[var(--bg)] border-[var(--border)] text-[13px] rounded-[3px]">
                <SelectValue placeholder="Avukat seçin" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">Tüm Avukatlar</SelectItem>
                {lawyers.map(l => (
                  <SelectItem key={l.code || l.name} value={l.code || l.name}>{l.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Acil filtre */}
          <div>
            <Eyebrow>Acil Filtre</Eyebrow>
            <button
              type="button"
              onClick={() => setOnlyUrgent(v => !v)}
              className={[
                "mt-2 w-full text-left border p-3 transition-colors",
                onlyUrgent
                  ? "border-[#b3284c]/50 bg-[#b3284c]/5"
                  : "border-[var(--border)] bg-[var(--bg)] hover:border-[var(--border-strong)]",
              ].join(" ")}
            >
              <div className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.12em] uppercase text-[#b3284c]">
                <AlertTriangle className="w-3 h-3" />
                Süre Yaklaşan
              </div>
              <div className="mt-1.5 font-display text-[22px] font-medium leading-none text-[var(--fg)]">
                {urgentByCase.size} dosya
              </div>
              <div className="mt-1.5 text-[11px] text-[var(--fg-subtle)] leading-snug">
                Önümüzdeki {URGENT_WINDOW_DAYS} gün içinde duruşması olan
                {onlyUrgent && <span className="text-[#b3284c]"> · filtre açık</span>}
              </div>
              {upcomingMarks.length > 0 && (
                <div className="mt-2 pt-2 border-t border-[var(--border)] inline-flex items-center gap-1.5 text-[11px] text-[var(--fg-muted)]">
                  <CalendarClock className="w-3 h-3" />
                  {upcomingMarks.length} takvim süre işareti
                </div>
              )}
            </button>
          </div>
        </HairlineCard>

        {/* Tablo */}
        <HairlineCard padded={false}>
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border)] gap-4">
            <span className="font-mono text-[11px] tracking-[0.12em] uppercase text-[var(--fg-muted)]">
              <span className="text-[var(--fg)] font-semibold tabular-nums">{headerCount.toLocaleString("tr-TR")}</span> dosya
              {activeFilterCount > 0 && (
                <span className="text-[var(--fg-subtle)]"> · {activeFilterCount} filtre uygulandı</span>
              )}
              {debouncedSearch && (
                <span className="text-[var(--fg-subtle)] normal-case tracking-normal italic"> — "{debouncedSearch}"</span>
              )}
            </span>
            <FlowButton
              variant="ghost"
              size="sm"
              onClick={() => { fetchCases(); fetchStats(); fetchCalendar(); }}
              disabled={isLoading}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
              Yenile
            </FlowButton>
          </div>

          {isLoading ? (
            <div className="grid place-items-center gap-3 py-20 text-[var(--fg-subtle)]">
              <Loader2 className="w-7 h-7 animate-spin" />
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase">Yükleniyor</span>
            </div>
          ) : displayedCases.length === 0 ? (
            <div className="grid place-items-center gap-3 py-20 text-center text-[var(--fg-subtle)]">
              <Search className="w-9 h-9 opacity-30" />
              <p className="text-[13px]">
                {onlyUrgent
                  ? "Bu sayfada süresi yaklaşan dosya yok."
                  : "Bu kriterlere uygun dosya bulunamadı."}
              </p>
              {activeFilterCount > 0 && (
                <FlowButton variant="secondary" size="sm" onClick={clearFilters}>
                  Filtreleri temizle
                </FlowButton>
              )}
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
                  {displayedCases.map(c => {
                    const client = c.parties?.find(p => p.party_type === "CLIENT")?.name || "—";
                    const urgentDays = urgentByCase.get(c.id);
                    const isUrgent = urgentDays !== undefined;
                    return (
                      <tr
                        key={c.id}
                        onClick={() => navigate(`/cases/${c.id}`)}
                        className={[
                          "border-b border-[var(--border)] last:border-b-0 cursor-pointer transition-colors",
                          isUrgent
                            ? "bg-[linear-gradient(90deg,var(--brand-soft)_0%,transparent_30%)] hover:bg-[linear-gradient(90deg,var(--brand-soft)_0%,var(--bg)_40%)]"
                            : "hover:bg-[var(--bg)]",
                        ].join(" ")}
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
                          <div className="flex items-center gap-2">
                            <span className="w-7 h-7 grid place-items-center shrink-0 border border-[var(--border)] bg-[var(--bg-sunken)] font-mono text-[10px] tracking-[0.04em] text-[var(--fg-muted)]">
                              {initials(c.responsible_lawyer_name)}
                            </span>
                            <div className="min-w-0">
                              <div className="text-[12px] text-[var(--fg)] truncate max-w-[140px]">
                                {c.responsible_lawyer_name?.split(" ")[0] || "Atanmadı"}
                              </div>
                              {c.updated_at && (
                                <div className="font-mono text-[9.5px] tracking-[0.04em] text-[var(--fg-subtle)] mt-0.5">
                                  Güncellendi · {formatAgo(c.updated_at)}
                                </div>
                              )}
                            </div>
                          </div>
                          {isUrgent && (
                            <div className="mt-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[2px] bg-[#b3284c]/[0.12] text-[#b3284c] font-mono text-[9.5px] tracking-[0.12em] uppercase font-semibold">
                              <AlertTriangle className="w-2.5 h-2.5" />
                              {urgentDays === 0 ? "Bugün" : `Süre ${urgentDays} gün`}
                            </div>
                          )}
                        </td>
                        <td className="px-5 py-4 text-right align-top">
                          <StatusChip status={c.status} />
                          {c.dosya_son_durumu && (
                            <div className="mt-1.5 text-[10px] text-[var(--fg-subtle)] italic truncate max-w-[160px] ml-auto">
                              {c.dosya_son_durumu}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {!onlyUrgent && totalCount > 0 && (
            <div className="flex items-center justify-between px-5 py-3 border-t border-[var(--border)] bg-[var(--bg)]">
              <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                Sayfa {currentPage} · {cases.length} kayıt
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

// Sayım rozetli durum çipi
function ChipButton({ active, label, count, onClick }: { active: boolean; label: string; count?: number; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "inline-flex items-center gap-1.5 px-2.5 py-1 font-mono text-[10px] tracking-[0.1em] uppercase border transition-colors",
        active
          ? "bg-[var(--brand)] text-[var(--brand-fg)] border-[var(--brand)]"
          : "bg-transparent text-[var(--fg-muted)] border-[var(--border)] hover:border-[var(--border-strong)] hover:text-[var(--fg)]",
      ].join(" ")}
    >
      {label}
      {count !== undefined && (
        <span className={`tabular-nums ${active ? "opacity-80" : "text-[var(--fg-subtle)]"}`}>
          {count.toLocaleString("tr-TR")}
        </span>
      )}
    </button>
  );
}

export default CaseList;
