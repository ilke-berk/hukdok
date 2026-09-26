import { Fragment, useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { usePageSearch } from "@/hooks/usePageSearch";
import {
  Search, FolderOpen, Scale, FileText,
  Plus, ChevronRight, ChevronLeft, ChevronDown,
  Briefcase, Copy, Check, HelpCircle,
  TrendingUp, Loader2, RefreshCw, AlertTriangle,
  SlidersHorizontal, CalendarClock, Sparkles,
} from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useNavigate, useLocation } from "react-router";
import { useCases, CASE_LIST_ERROR } from "../hooks/useCases";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { useConfigList } from "../hooks/useConfig";
import { apiClient } from "@/lib/api";
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
  /** Uzmanlık alanı (G123: kartta ve listede basılır; 6.464 kart doluydu, görünmüyordu). */
  sub_type?: string;
  subject?: string;
  hasar_dosya_no?: string;
  hukuk_no?: string;
  updated_at?: string;
  dosya_son_durumu?: string;
  missing_required_fields?: { field: string; label: string }[];
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

// Dava durumu üçlüsü (kullanıcı kararı 12.09.2026): DERDEST | DANIŞ | MAHZEN.
// Temyiz/istinaf durum değil aşamadır (case_stage); eski değerler migrasyon 50
// ile üçlüye çekildi. Çip sırası: bilinmeyenler ortada, MAHZEN sonda.
const STATUS_ORDER = ["DANIŞ", "DERDEST", "MAHZEN"];
// Sanal durum satırları (26.09.2026): DURUM değil, derdest dosyanın ulaştığı en ileri
// kanun yolu — avukat paneli kutularıyla aynı tanım; backend `status` filtresi tanır.
// Ağaç: Derdest → İstinafta / Temyizde → Yargıtay / Danıştay (Temyizde = ikisinin toplamı;
// karar düzeltme temyize dahil, mercii dosya türünden: İdare → Danıştay).
type DerdestAsamaKey = "ISTINAF" | "TEMYIZ" | "TEMYIZ_YARGITAY" | "TEMYIZ_DANISTAY";
const DERDEST_ASAMA_AGACI: { key: DerdestAsamaKey; label: string; depth: 1 | 2 }[] = [
  { key: "ISTINAF", label: "İstinafta", depth: 1 },
  { key: "TEMYIZ", label: "Temyizde", depth: 1 },
  { key: "TEMYIZ_YARGITAY", label: "Yargıtay", depth: 2 },
  { key: "TEMYIZ_DANISTAY", label: "Danıştay", depth: 2 },
];

const STATUS_TONE: Record<string, string> = {
  DANIŞ: "text-tone-info border-tone-info/30 bg-tone-info/10",
  DERDEST: "text-tone-ok border-tone-ok/30 bg-tone-ok/10",
  MAHZEN: "text-[var(--fg-subtle)] border-[var(--border)] bg-[var(--bg-sunken)]",
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
  // G185: yalnız filtrelerin okuduğu üç listeye abone olunur (useConfig 32 sorgu kuruyordu).
  const { data: lawyers } = useConfigList("lawyers");
  const { data: eventTypes } = useConfigList("eventTypes");
  const { data: serviceTypes } = useConfigList("serviceTypes");

  // Core data state
  const [cases, setCases] = useState<Case[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [stats, setStats] = useState<{
    total: number; active: number; closed: number; danis_active: number;
    statuses: Record<string, number>;
    // Derdest dosyaların en ileri kanun yolu (backend `derdest_stages`)
    derdest_stages?: Partial<Record<DerdestAsamaKey, number>>;
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
  // G105: Olay Türü filtresi — değer listenin ADIdır (sözleşme: olay_turu param'ı)
  const [selectedOlayTuru, setSelectedOlayTuru] = useState<string>("ALL");
  // G121: Hizmet Türü filtresi — değer listenin ADIdır (sözleşme: hizmet_turu param'ı);
  // "Lexis Rapor" föyleri dava takibi değil, liste bu ayrımı görebilmeli.
  const [selectedHizmetTuru, setSelectedHizmetTuru] = useState<string>("ALL");
  const [onlyUrgent, setOnlyUrgent] = useState(false);
  const [onlyMissing, setOnlyMissing] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  // G002: liste hatası boş listeden ayrı tutulur (null = hata yok)
  const [loadError, setLoadError] = useState<string | null>(null);

  // Yarış durumu koruması: geç dönen eski isteklerin yenisini ezmesini engeller
  const reqIdRef = useRef(0);

  const fetchCases = useCallback(async () => {
    const reqId = ++reqIdRef.current;
    try {
      setIsLoading(true);
      const offset = (currentPage - 1) * ITEMS_PER_PAGE;
      const data = await getCases<Case>({
        limit: ITEMS_PER_PAGE,
        offset,
        status: selectedStatus,
        lawyer: selectedLawyer,
        q: debouncedSearch || undefined,
        fileType: selectedFileType,
        olayTuru: selectedOlayTuru,
        hizmetTuru: selectedHizmetTuru,
        urgentDays: onlyUrgent ? URGENT_WINDOW_DAYS : undefined,
        missingRequired: onlyMissing || undefined,
      });
      // Bu yanıt en güncel istek değilse (kullanıcı yazmaya devam etti) yok say
      if (reqId !== reqIdRef.current) return;
      setCases(data.cases);
      setTotalCount(data.total);
      setLoadError(null);
    } catch (error) {
      if (reqId !== reqIdRef.current) return;
      console.error(error);
      // G002: kaybolan toast yerine kalıcı şerit — "kayıt yok" görünümünün
      // yerine geçer, kullanıcı kesintiyi veri kaybıyla karıştırmasın.
      setLoadError(error instanceof Error ? error.message : CASE_LIST_ERROR);
    } finally {
      if (reqId === reqIdRef.current) setIsLoading(false);
    }
  }, [getCases, currentPage, selectedStatus, selectedLawyer, selectedFileType, selectedOlayTuru, selectedHizmetTuru, debouncedSearch, onlyUrgent, onlyMissing]);

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
  useEffect(() => { setCurrentPage(1); }, [debouncedSearch, selectedStatus, selectedLawyer, selectedFileType, selectedOlayTuru, selectedHizmetTuru, onlyUrgent, onlyMissing]);

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
    setSelectedOlayTuru("ALL");
    setSelectedHizmetTuru("ALL");
    setOnlyUrgent(false);
    setOnlyMissing(false);
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
    selectedOlayTuru !== "ALL" && "olayturu",
    selectedHizmetTuru !== "ALL" && "hizmetturu",
    onlyUrgent && "urgent",
    onlyMissing && "missing",
  ].filter(Boolean).length;

  // Tüm filtreler (acil dahil) artık sunucuda — totalCount gerçek toplam
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
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <span>
              <FlowButton variant="primary">
                <Plus className="w-3.5 h-3.5" />
                Yeni Dava Aç
                <ChevronDown className="w-3.5 h-3.5" />
              </FlowButton>
            </span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => navigate("/new-case/auto")}>
              <Sparkles className="w-3.5 h-3.5 mr-2" />
              Belgelerden Otomatik Aç
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate("/new-case/form")}>
              <FileText className="w-3.5 h-3.5 mr-2" />
              Manuel Aç
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
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
            <div className="mt-2 flex flex-col gap-px" role="list" aria-label="Durum filtresi">
              <StatusRow
                active={selectedStatus === "ALL"}
                label="Tümü"
                count={stats.total}
                onClick={() => setSelectedStatus("ALL")}
              />
              {statusChips.map(s => (
                <Fragment key={s}>
                  <StatusRow
                    active={selectedStatus === s}
                    label={s}
                    count={stats.statuses[s]}
                    onClick={() => setSelectedStatus(s)}
                  />
                  {s === "DERDEST" && DERDEST_ASAMA_AGACI.map(a => (
                    <StatusRow
                      key={a.key}
                      depth={a.depth}
                      active={selectedStatus === a.key}
                      label={a.label}
                      count={stats.derdest_stages?.[a.key] ?? 0}
                      onClick={() => setSelectedStatus(a.key)}
                    />
                  ))}
                </Fragment>
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
                <SelectItem value="İdare">İdare</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* G105: Olay Türü — event_types kapalı listesinden beslenir;
              seçim liste isteğine olay_turu param'ı olarak gider (değer = ad) */}
          <div>
            <Eyebrow>Olay Türü</Eyebrow>
            <Select value={selectedOlayTuru} onValueChange={setSelectedOlayTuru}>
              <SelectTrigger className="mt-2 h-10 bg-[var(--bg)] border-[var(--border)] text-[13px] rounded-[3px]">
                <SelectValue placeholder="Olay türü seçin" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">Tümü</SelectItem>
                {eventTypes.map(t => (
                  <SelectItem key={t.code || t.name} value={t.name}>{t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* G121: Hizmet Türü — service_types kapalı listesinden beslenir;
              seçim liste isteğine hizmet_turu param'ı olarak gider (değer = ad).
              Olay Türü ile aynı desen; "Tümü" seçiliyken param gönderilmez. */}
          <div>
            <Eyebrow>Hizmet Türü</Eyebrow>
            <Select value={selectedHizmetTuru} onValueChange={setSelectedHizmetTuru}>
              <SelectTrigger className="mt-2 h-10 bg-[var(--bg)] border-[var(--border)] text-[13px] rounded-[3px]">
                <SelectValue placeholder="Hizmet türü seçin" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">Tümü</SelectItem>
                {serviceTypes.map(t => (
                  <SelectItem key={t.code || t.name} value={t.name}>{t.name}</SelectItem>
                ))}
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
                  ? "border-tone-urgent/50 bg-tone-urgent/5"
                  : "border-[var(--border)] bg-[var(--bg)] hover:border-[var(--border-strong)]",
              ].join(" ")}
            >
              <div className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.12em] uppercase text-tone-urgent">
                <AlertTriangle className="w-3 h-3" />
                Süre Yaklaşan
              </div>
              <div className="mt-1.5 font-display text-[22px] font-medium leading-none text-[var(--fg)]">
                {urgentByCase.size} dosya
              </div>
              <div className="mt-1.5 text-[11px] text-[var(--fg-subtle)] leading-snug">
                Önümüzdeki {URGENT_WINDOW_DAYS} gün içinde duruşması olan
                {onlyUrgent && <span className="text-tone-urgent"> · filtre açık</span>}
              </div>
              {upcomingMarks.length > 0 && (
                <div className="mt-2 pt-2 border-t border-[var(--border)] inline-flex items-center gap-1.5 text-[11px] text-[var(--fg-muted)]">
                  <CalendarClock className="w-3 h-3" />
                  {upcomingMarks.length} takvim süre işareti
                </div>
              )}
            </button>
          </div>

          {/* Eksik alan filtresi — zorunlu alanları tamamlanmamış dosyalar */}
          <div>
            <Eyebrow>Eksik Alan</Eyebrow>
            <button
              type="button"
              onClick={() => setOnlyMissing(v => !v)}
              className={[
                "mt-2 w-full text-left border p-3 transition-colors",
                onlyMissing
                  ? "border-amber-500/50 bg-amber-500/5"
                  : "border-[var(--border)] bg-[var(--bg)] hover:border-[var(--border-strong)]",
              ].join(" ")}
            >
              <div className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.12em] uppercase text-amber-600 dark:text-amber-400">
                <AlertTriangle className="w-3 h-3" />
                Eksik Alanlı Dosyalar
              </div>
              <div className="mt-1.5 text-[11px] text-[var(--fg-subtle)] leading-snug">
                Zorunlu alanları tamamlanmamış dosyaları göster
                {onlyMissing && <span className="text-amber-600 dark:text-amber-400"> · filtre açık</span>}
              </div>
            </button>
          </div>
        </HairlineCard>

        {/* Tablo */}
        <HairlineCard padded={false}>
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border)] gap-4">
            <span className="font-mono text-[11px] tracking-[0.12em] uppercase text-[var(--fg-muted)]">
              <span className="text-[var(--fg)] font-semibold tabular-nums">{totalCount.toLocaleString("tr-TR")}</span> dosya
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

          {loadError && (
            <DataErrorBanner
              description={loadError}
              onRetry={() => { fetchCases(); fetchStats(); }}
              isRetrying={isLoading}
              className="mx-5 mb-4"
            />
          )}

          {isLoading ? (
            <div className="grid place-items-center gap-3 py-20 text-[var(--fg-subtle)]">
              <Loader2 className="w-7 h-7 animate-spin" />
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase">Yükleniyor</span>
            </div>
          ) : cases.length === 0 ? (
            // G002: hatada "bulunamadı" görünümü ASLA çıkmaz — yerini şerit alır.
            loadError ? null : (
            <div className="grid place-items-center gap-3 py-20 text-center text-[var(--fg-subtle)]">
              <Search className="w-9 h-9 opacity-30" />
              <p className="text-[13px]">
                {onlyUrgent
                  ? "Süresi yaklaşan dosya yok."
                  : onlyMissing
                    ? "Eksik alanlı dosya yok — tüm zorunlu alanlar tamamlanmış."
                    : "Bu kriterlere uygun dosya bulunamadı."}
              </p>
              {activeFilterCount > 0 && (
                <FlowButton variant="secondary" size="sm" onClick={clearFilters}>
                  Filtreleri temizle
                </FlowButton>
              )}
            </div>
            )
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
                          {(c.missing_required_fields?.length ?? 0) > 0 && (
                            <div
                              className="mt-1.5 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[2px] bg-amber-500/[0.14] text-amber-600 dark:text-amber-400 font-mono text-[9.5px] tracking-[0.12em] uppercase font-semibold"
                              title={`Eksik zorunlu alanlar: ${c.missing_required_fields!.map(m => m.label).join(", ")}`}
                            >
                              <AlertTriangle className="w-2.5 h-2.5" />
                              Eksik alan · {c.missing_required_fields!.length}
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
                          {c.sub_type && (
                            <div className="font-mono text-[9.5px] tracking-[0.06em] uppercase text-[var(--fg-subtle)] mt-1 truncate max-w-[320px]">
                              {c.sub_type}
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
                            <div className="mt-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[2px] bg-tone-urgent/[0.12] text-tone-urgent font-mono text-[9.5px] tracking-[0.12em] uppercase font-semibold">
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

          {totalCount > 0 && (
            <div className="flex items-center justify-between px-5 py-3 border-t border-[var(--border)] bg-[var(--bg)]">
              <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                Toplam {totalCount.toLocaleString("tr-TR")} kayıt
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

// Durum filtresinin satırı: etiket solda, sayı sağda hizalı. `depth` alt kırılımı
// (derdest aşamaları) sol çizgili girintiyle gösterir; kök satırlar büyük harf.
const STATUS_ROW_INDENT = { 0: "", 1: "ml-3", 2: "ml-6" } as const;

function StatusRow({ active, label, count, onClick, depth = 0 }: {
  active: boolean; label: string; count?: number; onClick: () => void; depth?: 0 | 1 | 2;
}) {
  return (
    <div role="listitem" className={depth ? `${STATUS_ROW_INDENT[depth]} border-l border-[var(--border)] pl-2` : ""}>
      <button
        type="button"
        onClick={onClick}
        aria-pressed={active}
        className={[
          "w-full flex items-center justify-between gap-3 px-2.5 font-mono tracking-[0.1em] border-l-2 transition-colors",
          depth === 0 ? "py-1.5 text-[11px] uppercase" : "py-1 text-[10.5px]",
          active
            ? "bg-brand-solid text-[var(--brand-fg)] border-brand-solid"
            : "border-transparent text-[var(--fg-muted)] hover:bg-[var(--bg-sunken)] hover:text-[var(--fg)]",
        ].join(" ")}
      >
        <span className="truncate">{label}</span>
        {count !== undefined && (
          <span className={`tabular-nums shrink-0 ${active ? "opacity-80" : "text-[var(--fg-subtle)]"}`}>
            {count.toLocaleString("tr-TR")}
          </span>
        )}
      </button>
    </div>
  );
}

export default CaseList;
