import { Header } from "@/components/Header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCases } from "@/hooks/useCases";
import { useEffect, useState, useMemo, useCallback } from "react";
import {
    Calendar as CalendarIcon,
    Clock,
    Gavel,
    FileText,
    User,
    Search,
    Plus,
    Upload,
    TrendingUp,
    AlertCircle,
    CheckCircle2,
    FolderOpen,
    ChevronRight,
    Scale,
    BarChart3,
    Filter,
    AlertTriangle,
    Wrench,
    Users,
} from "lucide-react";
import { Calendar } from "@/components/ui/calendar";
import { useNavigate, useLocation } from "react-router-dom";
import { getApiUrl } from "@/lib/api";
import { useMsal } from "@azure/msal-react";
import { useConfig } from "@/hooks/useConfig";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";

const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
    DERDEST: { bg: "bg-emerald-500/15", text: "text-emerald-400", dot: "bg-emerald-400" },
    KARAR: { bg: "bg-blue-500/15", text: "text-blue-400", dot: "bg-blue-400" },
    KAPALI: { bg: "bg-gray-500/15", text: "text-gray-400", dot: "bg-gray-400" },
    TEMYIZ: { bg: "bg-purple-500/15", text: "text-purple-400", dot: "bg-purple-400" },
    INFAZ: { bg: "bg-orange-500/15", text: "text-orange-400", dot: "bg-orange-400" },
};

const formatStatus = (status: string) => {
    if (!status) return "";
    if (status === "DERDEST") return "Derdest";
    if (status === "MAHZEN") return "Mahzen";
    if (status === "KAPALI") return "Kapalı";
    if (status === "TEMYIZ") return "Temyiz";
    if (status === "INFAZ") return "İnfaz";
    if (status === "KARAR") return "Karar";
    return status.charAt(0).toLocaleUpperCase('tr-TR') + status.slice(1).toLocaleLowerCase('tr-TR');
};

const getStatusStyle = (status: string) =>
    statusColors[status?.toLocaleUpperCase('tr-TR')] || { bg: "bg-primary/15", text: "text-primary", dot: "bg-primary" };

interface HomeCaseData {
    id: number;
    esas_no?: string;
    tracking_no?: string;
    status?: string;
    court?: string;
    opening_date?: string;
    responsible_lawyer_name?: string;
    file_type?: string;
    subject?: string;
    parties?: { party_type: string; name: string }[];
    [key: string]: unknown;
}

const Home = () => {
    const { getCases, getCaseStats, getCase, searchCases } = useCases();
    const { instance, accounts } = useMsal();
    const navigate = useNavigate();
    const location = useLocation();
    const [cases, setCases] = useState<HomeCaseData[]>([]);
    const [searchResults, setSearchResults] = useState<HomeCaseData[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [stats, setStats] = useState({ active: 0, closed: 0, appeal: 0, total: 0 });
    const [uniqueStatuses, setUniqueStatuses] = useState<string[]>(["DERDEST", "KARAR", "KAPALI", "TEMYIZ", "INFAZ"]);
    const [loading, setLoading] = useState(true);
    const [selectedDate, setSelectedDate] = useState<Date | undefined>(new Date());
    const [searchQuery, setSearchQuery] = useState((location.state as { searchQuery?: string } | null)?.searchQuery || "");
    const [statusFilter, setStatusFilter] = useState<string>("ALL");
    const [listLawyerFilter, setListLawyerFilter] = useState<string>("ALL");
    const [calendarLawyerFilter, setCalendarLawyerFilter] = useState<string>("ALL");
    const [offset, setOffset] = useState(0);
    const [hasMore, setHasMore] = useState(true);
    const LIMIT = 100;
    const { lawyers } = useConfig();

    const calendarLawyerOptions = useMemo(() => {
        // Konfigürasyondaki isimleri al
        const configNames = lawyers.map(l => l.name);

        // Davalardan gelen isimleri normalize et (kod ise tam isme çevir)
        const caseLawyerNames = cases.map(c => {
            const rawName = c.responsible_lawyer_name;
            if (!rawName) return null;

            // Eğer bir kod ise (AGH gibi), tam ismi bul
            const matchedByCode = lawyers.find(l => l.code === rawName);
            if (matchedByCode) return matchedByCode.name;

            return rawName;
        }).filter(Boolean) as string[];

        // Tümünü birleştir, dublikeleri temizle, istenmeyenleri çıkar ve sırala
        const EXCLUDED_NAMES = ["Başka Büro / Harici", "Hanyaloğlu & Acar"];
        return Array.from(new Set([...configNames, ...caseLawyerNames]))
            .filter(name => !EXCLUDED_NAMES.includes(name))
            .sort();
    }, [lawyers, cases]);

    const [incompleteTasks, setIncompleteTasks] = useState<{
        incomplete_cases: Record<string, unknown>[];
        incomplete_clients: Record<string, unknown>[];
        total_incomplete_cases: number;
        total_incomplete_clients: number;
    } | null>(null);
    const [incompleteLoading, setIncompleteLoading] = useState(true);

    const loadCases = useCallback(async (isMore = false) => {
        const currentOffset = isMore ? offset + LIMIT : 0;
        if (!isMore) setLoading(true);
        else setIsSearching(true); // Reuse searching state for Load More spinner

        const data = await getCases({
            limit: LIMIT,
            offset: currentOffset,
            status: statusFilter,
            lawyer: listLawyerFilter,
            q: searchQuery.length >= 2 ? searchQuery : undefined
        });

        if (isMore) {
            setCases(prev => [...prev, ...(data || [])]);
            setOffset(currentOffset);
        } else {
            setCases(data || []);
            setOffset(0);
        }

        setHasMore((data?.length || 0) === LIMIT);
        setLoading(false);
        setIsSearching(false);
    }, [getCases, statusFilter, listLawyerFilter, searchQuery, offset]);

    useEffect(() => {
        const fetchStats = async () => {
            const statsData = await getCaseStats();
            if (statsData) {
                setStats({
                    active: statsData.active || 0,
                    closed: statsData.closed || 0,
                    appeal: statsData.appeal || 0,
                    total: statsData.total || 0
                });
                if (statsData.statuses && Object.keys(statsData.statuses).length > 0) {
                    setUniqueStatuses(Object.keys(statsData.statuses));
                }
            }
        };
        fetchStats();

        // Yarım kalan işleri getir
        const fetchIncompleteTasks = async () => {
            setIncompleteLoading(true);
            try {
                const baseUrl = await getApiUrl();
                const account = instance.getActiveAccount() || accounts[0];
                if (!account) return;
                const tokenResponse = await instance.acquireTokenSilent({
                    scopes: ["User.Read"],
                    account,
                });
                const res = await fetch(`${baseUrl}/api/incomplete-tasks`, {
                    headers: { Authorization: `Bearer ${tokenResponse.idToken}` },
                });
                if (res.ok) {
                    const data = await res.json();
                    setIncompleteTasks(data);
                }
            } catch (e) {
                console.error("Incomplete tasks fetch error:", e);
            } finally {
                setIncompleteLoading(false);
            }
        };
        fetchIncompleteTasks();
    }, [getCaseStats, instance, accounts]);

    // Triger loadCases on filter change
    useEffect(() => {
        const timeoutId = setTimeout(() => {
            loadCases(false);
        }, searchQuery.length >= 2 ? 400 : 0);
        return () => clearTimeout(timeoutId);
    }, [statusFilter, listLawyerFilter, searchQuery]);

    // Calendar events
    const calendarEvents = useMemo(() => {
        const events: Record<string, HomeCaseData[]> = {};
        cases.forEach((c) => {
            // Apply lawyer filter for calendar
            if (calendarLawyerFilter !== "ALL") {
                const caseLawyer = c.responsible_lawyer_name;
                if (!caseLawyer) return;

                // Eşleşmeyi kontrol et (Seçilen isimle direkt eşleşme VEYA seçilen ismin koduna sahip olma)
                const isDirectMatch = caseLawyer === calendarLawyerFilter;
                const isCodeMatch = lawyers.find(l => l.name === calendarLawyerFilter)?.code === caseLawyer;

                if (!isDirectMatch && !isCodeMatch) {
                    return;
                }
            }

            if (c.opening_date) {
                const dateStr = new Date(c.opening_date).toDateString();
                if (!events[dateStr]) events[dateStr] = [];
                events[dateStr].push(c);
            }
        });
        return events;
    }, [cases, calendarLawyerFilter, lawyers]);

    const selectedDateEvents = useMemo(() => {
        if (!selectedDate) return [];
        return calendarEvents[selectedDate.toDateString()] || [];
    }, [selectedDate, calendarEvents]);

    // Statistics are now from server state `stats`

    // Filtered cases
    const filteredCases = cases;

    // uniqueStatuses is now updated from server stats, no recalculation needed from local cases.

    const today = new Date().toLocaleDateString("tr-TR", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
    });

    return (
        <div className="min-h-screen bg-background flex flex-col">
            <Header />

            <main className="flex-1 container mx-auto py-6 px-4 space-y-6">

                {/* Welcome Bar + Quick Actions */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                        <p className="text-xs text-muted-foreground uppercase tracking-widest mb-1">{today}</p>
                        <h2 className="text-2xl font-bold tracking-tight">Dashboard</h2>
                    </div>

                </div>

                {/* Stats Row */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <Card className="border-primary/20 bg-card/80 hover:shadow-lg transition-all duration-300 hover:border-primary/40 group">
                        <CardContent className="p-4 flex items-center gap-4">
                            <div className="w-12 h-12 rounded-xl bg-primary/15 flex items-center justify-center shrink-0 group-hover:bg-primary/25 transition-colors">
                                <Scale className="w-6 h-6 text-primary" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold">{loading ? "–" : stats.total}</p>
                                <p className="text-xs text-muted-foreground">Toplam Dava</p>
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="border-emerald-500/20 bg-card/80 hover:shadow-lg transition-all duration-300 hover:border-emerald-500/40 group">
                        <CardContent className="p-4 flex items-center gap-4">
                            <div className="w-12 h-12 rounded-xl bg-emerald-500/15 flex items-center justify-center shrink-0 group-hover:bg-emerald-500/25 transition-colors">
                                <TrendingUp className="w-6 h-6 text-emerald-400" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-emerald-400">{loading ? "–" : stats.active}</p>
                                <p className="text-xs text-muted-foreground">Aktif (Derdest)</p>
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="border-purple-500/20 bg-card/80 hover:shadow-lg transition-all duration-300 hover:border-purple-500/40 group">
                        <CardContent className="p-4 flex items-center gap-4">
                            <div className="w-12 h-12 rounded-xl bg-purple-500/15 flex items-center justify-center shrink-0 group-hover:bg-purple-500/25 transition-colors">
                                <BarChart3 className="w-6 h-6 text-purple-400" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-purple-400">{loading ? "–" : stats.appeal}</p>
                                <p className="text-xs text-muted-foreground">Temyiz</p>
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="border-gray-500/20 bg-card/80 hover:shadow-lg transition-all duration-300 hover:border-gray-500/40 group">
                        <CardContent className="p-4 flex items-center gap-4">
                            <div className="w-12 h-12 rounded-xl bg-gray-500/15 flex items-center justify-center shrink-0 group-hover:bg-gray-500/25 transition-colors">
                                <CheckCircle2 className="w-6 h-6 text-gray-400" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-gray-400">{loading ? "–" : stats.closed}</p>
                                <p className="text-xs text-muted-foreground">Kapalı</p>
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Yarım Kalan İşler */}
                {!incompleteLoading && incompleteTasks && (incompleteTasks.total_incomplete_cases > 0 || incompleteTasks.total_incomplete_clients > 0) && (
                    <Card className="border-amber-500/30 bg-card/80 hover:shadow-lg transition-all duration-300">
                        <CardHeader className="pb-3">
                            <div className="flex items-center justify-between">
                                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                                    <span className="text-amber-400">Yarım Kalan İşler</span>
                                    <Badge variant="outline" className="h-5 px-1.5 text-[0.65rem] border-amber-500/30 text-amber-400 bg-amber-500/10 ml-1">
                                        {(incompleteTasks.total_incomplete_cases || 0) + (incompleteTasks.total_incomplete_clients || 0)}
                                    </Badge>
                                </CardTitle>
                                <CardDescription className="text-xs">
                                    Hızlı kayıtlarda eksik kalan bilgileri tamamlayın
                                </CardDescription>
                            </div>
                        </CardHeader>
                        <CardContent className="pb-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[300px] overflow-y-auto pr-1">

                                {/* Eksik Davalar */}
                                {incompleteTasks.incomplete_cases?.slice(0, 6).map((task: { id: number; status: string; case_id: number; tracking_no: string; esas_no?: string; court?: string; missing_fields: string[] }) => {
                                    const style = getStatusStyle(task.status);
                                    return (
                                        <div
                                            key={`case-${task.id}`}
                                            onClick={async () => {
                                                const fullCase = await getCase(task.id);
                                                if (fullCase) {
                                                    navigate("/new-case", { state: { case: fullCase } });
                                                }
                                            }}
                                            className="group flex items-start gap-3 p-3 rounded-lg bg-background/60 border border-border/50 hover:border-amber-500/40 cursor-pointer transition-all duration-200"
                                        >
                                            <div className="w-8 h-8 rounded-lg bg-amber-500/15 flex items-center justify-center shrink-0 group-hover:bg-amber-500/25 transition-colors">
                                                <Gavel className="w-4 h-4 text-amber-400" />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center justify-between gap-2">
                                                    <span className="font-semibold text-xs truncate">{task.esas_no}</span>
                                                    <span className={`text-[0.6rem] font-medium px-1.5 py-0.5 rounded-full shrink-0 ${style.bg} ${style.text}`}>{formatStatus(task.status as string)}</span>
                                                </div>
                                                <div className="flex flex-wrap gap-1 mt-1.5">
                                                    {task.missing_fields?.map((f: string, i: number) => (
                                                        <Badge key={i} variant="outline" className="text-[0.55rem] h-4 px-1.5 border-amber-500/20 text-amber-500/80 bg-amber-500/5">
                                                            {f}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </div>
                                            <Wrench className="w-3.5 h-3.5 text-muted-foreground/30 group-hover:text-amber-400 transition-colors shrink-0 mt-0.5" />
                                        </div>
                                    );
                                })}

                                {/* Eksik Müvekkiller */}
                                {incompleteTasks.incomplete_clients?.slice(0, 6).map((task: { id: number; name: string; missing_fields: string[]; client_type?: string }) => (
                                    <div
                                        key={`client-${task.id}`}
                                        onClick={() => navigate("/new-client", { state: { client: { id: task.id, name: task.name } } })}
                                        className="group flex items-start gap-3 p-3 rounded-lg bg-background/60 border border-border/50 hover:border-blue-500/40 cursor-pointer transition-all duration-200"
                                    >
                                        <div className="w-8 h-8 rounded-lg bg-blue-500/15 flex items-center justify-center shrink-0 group-hover:bg-blue-500/25 transition-colors">
                                            <User className="w-4 h-4 text-blue-400" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center justify-between gap-2">
                                                <span className="font-semibold text-xs truncate">{task.name}</span>
                                                <span className="text-[0.6rem] text-muted-foreground">{task.client_type}</span>
                                            </div>
                                            <div className="flex flex-wrap gap-1 mt-1.5">
                                                {task.missing_fields?.map((f: string, i: number) => (
                                                    <Badge key={i} variant="outline" className="text-[0.55rem] h-4 px-1.5 border-blue-500/20 text-blue-500/80 bg-blue-500/5">
                                                        {f}
                                                    </Badge>
                                                ))}
                                            </div>
                                        </div>
                                        <Wrench className="w-3.5 h-3.5 text-muted-foreground/30 group-hover:text-blue-400 transition-colors shrink-0 mt-0.5" />
                                    </div>
                                ))}
                            </div>

                            {/* Fazla varsa uyarı */}
                            {((incompleteTasks.total_incomplete_cases || 0) > 6 || (incompleteTasks.total_incomplete_clients || 0) > 6) && (
                                <p className="text-center text-xs text-muted-foreground mt-3 pt-2 border-t border-border/30">
                                    +{Math.max(0, (incompleteTasks.total_incomplete_cases || 0) - 6) + Math.max(0, (incompleteTasks.total_incomplete_clients || 0) - 6)} daha fazla eksik kayıt var
                                </p>
                            )}
                        </CardContent>
                    </Card>
                )}

                {/* Main Content */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                    {/* Left: Case List */}
                    <div className="lg:col-span-2 space-y-4">

                        {/* Search & Filter */}
                        <div className="flex flex-col gap-3">
                            <div className="flex flex-col sm:flex-row gap-3">
                                <div className="relative flex-1">
                                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                    <Input
                                        placeholder="Esas no, avukat, mahkeme veya konu ara..."
                                        className="pl-9 glass-input"
                                        value={searchQuery}
                                        onChange={(e) => setSearchQuery(e.target.value)}
                                    />
                                </div>
                                <div className="w-full sm:w-[200px]">
                                    <Select
                                        value={listLawyerFilter}
                                        onValueChange={setListLawyerFilter}
                                    >
                                        <SelectTrigger className="glass-input">
                                            <div className="flex items-center gap-2">
                                                <Users className="w-4 h-4 text-muted-foreground" />
                                                <SelectValue placeholder="Avukat Seçin" />
                                            </div>
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="ALL">Tüm Avukatlar</SelectItem>
                                            {calendarLawyerOptions.map(name => (
                                                <SelectItem key={name} value={name}>{name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>

                            <div className="flex items-center gap-2 overflow-x-auto pb-0.5 no-scrollbar">
                                <Filter className="w-4 h-4 text-muted-foreground shrink-0" />
                                <Button
                                    size="sm"
                                    variant={statusFilter === "ALL" ? "default" : "outline"}
                                    className={`h-9 shrink-0 ${statusFilter === "ALL" ? "bg-primary text-primary-foreground" : "bg-card/50"}`}
                                    onClick={() => setStatusFilter("ALL")}
                                >
                                    Tümü
                                </Button>
                                {uniqueStatuses.map((s) => {
                                    const isActive = statusFilter === s;
                                    return (
                                        <Button
                                            key={s}
                                            size="sm"
                                            variant={isActive ? "default" : "outline"}
                                            className={`h-9 shrink-0 ${isActive ? "bg-primary text-primary-foreground" : "bg-card/50"}`}
                                            onClick={() => setStatusFilter(s)}
                                        >
                                            {formatStatus(s)}
                                        </Button>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Case List Header */}
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                <FolderOpen className="w-4 h-4" />
                                {searchQuery.trim().length >= 2 ? "Arama Sonuçları" : "Son Eklenen Davalar"}
                            </h3>
                            <span className="text-xs text-muted-foreground">
                                {loading || isSearching ? "Yükleniyor..." : `${filteredCases.length} dava gösteriliyor`}
                            </span>
                        </div>

                        {/* Cases */}
                        {loading || isSearching ? (
                            <div className="space-y-3">
                                {[1, 2, 3, 4].map((i) => (
                                    <div key={i} className="h-24 rounded-xl bg-card/60 animate-pulse border border-border/50" />
                                ))}
                            </div>
                        ) : filteredCases.length === 0 ? (
                            <div className="py-16 text-center text-muted-foreground border border-dashed border-border rounded-xl flex flex-col items-center gap-3">
                                <AlertCircle className="w-10 h-10 opacity-30" />
                                <div>
                                    <p className="font-medium">Dava bulunamadı</p>
                                    <p className="text-xs mt-1">Arama kriterlerinizi değiştirin veya yeni dava ekleyin.</p>
                                </div>
                                <Button size="sm" className="mt-2 gap-2" onClick={() => navigate("/new-case")}>
                                    <Plus className="w-4 h-4" />
                                    Yeni Dava Oluştur
                                </Button>
                            </div>
                        ) : (
                            <div className="space-y-3 max-h-[calc(100vh-380px)] overflow-y-auto pr-1">
                                {cases.map((c) => {
                                    const style = getStatusStyle(c.status as string);
                                    return (
                                        <div
                                            key={c.id}
                                            onClick={() => navigate(`/cases/${c.id}`)}
                                            className="group flex items-start gap-4 p-4 rounded-xl bg-card/70 border border-border/60 hover:border-primary/40 hover:bg-card transition-all duration-200 cursor-pointer shadow-sm"
                                        >
                                            {/* Left accent */}
                                            <div className={`w-1 h-full min-h-[60px] rounded-full ${style.dot} opacity-70 shrink-0`} />

                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-start justify-between gap-2">
                                                    <div className="flex items-center gap-2 min-w-0 text-sm font-semibold">
                                                        <Gavel className="w-4 h-4 text-primary shrink-0" />
                                                        <span className="truncate">
                                                            {c.esas_no || c.tracking_no || "Esas No Yok"}
                                                        </span>
                                                    </div>
                                                    <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full shrink-0 ${style.bg} ${style.text} border border-border/20`}>
                                                        {formatStatus(c.status as string)}
                                                    </span>
                                                </div>

                                                <div className="mt-2.5 grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px] text-muted-foreground">
                                                    <div className="flex items-center gap-1.5 bg-background/40 px-2 py-1 rounded-md border border-border/30">
                                                        <User className="w-3 h-3 shrink-0 text-primary/60" />
                                                        <span className="truncate">{c.responsible_lawyer_name || "Atanmadı"}</span>
                                                    </div>
                                                    <div className="flex items-center gap-1.5 bg-background/40 px-2 py-1 rounded-md border border-border/30">
                                                        <Scale className="w-3 h-3 shrink-0 text-primary/60" />
                                                        <span className="truncate">{c.court || "Mahkeme belirtilmedi"}</span>
                                                    </div>
                                                    <div className="flex items-center gap-1.5 bg-background/40 px-2 py-1 rounded-md border border-border/30">
                                                        {c.opening_date ? (
                                                            <>
                                                                <Clock className="w-3 h-3 shrink-0 text-emerald-400" />
                                                                <span className="text-emerald-400/90 font-medium">
                                                                    {new Date(c.opening_date as string).toLocaleDateString("tr-TR")}
                                                                </span>
                                                            </>
                                                        ) : (
                                                            <span className="italic opacity-50">Tarih yok</span>
                                                        )}
                                                    </div>
                                                </div>

                                                {c.subject && (
                                                    <div className="mt-2 flex items-center gap-1.5 text-[10px] text-muted-foreground/80 pl-1">
                                                        <FileText className="w-3 h-3 shrink-0" />
                                                        <span className="truncate italic uppercase tracking-tighter">{c.subject}</span>
                                                    </div>
                                                )}

                                                {c.parties && c.parties.some((p: { party_type: string }) => p.party_type === 'COUNTER') && (
                                                    <div className="mt-2 flex items-center gap-1.5 text-[10px] text-amber-500 font-bold pl-1 uppercase tracking-wider">
                                                        <Users className="w-3 h-3 shrink-0" />
                                                        <span className="truncate">
                                                            {c.parties.filter((p: { party_type: string; name?: string }) => p.party_type === 'COUNTER').map((p: { name?: string }) => p.name).join(", ")}
                                                        </span>
                                                    </div>
                                                )}
                                            </div>

                                            <div className="w-8 h-8 rounded-full bg-primary/5 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300">
                                                <ChevronRight className="w-4 h-4 text-primary" />
                                            </div>
                                        </div>
                                    );
                                })}

                                {hasMore && (
                                    <div className="flex justify-center pt-4 pb-8">
                                        <Button
                                            variant="outline"
                                            className="w-full max-w-[200px] border-primary/20 hover:bg-primary/10 gap-2 h-10 shadow-sm"
                                            onClick={() => loadCases(true)}
                                            disabled={isSearching}
                                        >
                                            {isSearching ? (
                                                <Clock className="w-4 h-4 animate-spin" />
                                            ) : (
                                                <Plus className="w-4 h-4" />
                                            )}
                                            Daha Fazla Yükle
                                        </Button>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Right: Calendar + Quick Access */}
                    <div className="space-y-4">

                        {/* Quick Actions */}
                        <Card className="border-border/60 bg-card/80">
                            <CardHeader className="pb-3">
                                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                                    <Plus className="w-4 h-4 text-primary" />
                                    Hızlı İşlemler
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-2 pb-4">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="w-full justify-start gap-3 h-10 hover:bg-primary/10 hover:border-primary/40"
                                    onClick={() => navigate("/upload")}
                                >
                                    <Upload className="w-4 h-4 text-primary" />
                                    Belge Yükle & Analiz Et
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="w-full justify-start gap-3 h-10 hover:bg-emerald-500/10 hover:border-emerald-500/40"
                                    onClick={() => navigate("/new-case")}
                                >
                                    <Gavel className="w-4 h-4 text-emerald-400" />
                                    Yeni Dava Açılışı
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="w-full justify-start gap-3 h-10 hover:bg-blue-500/10 hover:border-blue-500/40"
                                    onClick={() => navigate("/new-client")}
                                >
                                    <User className="w-4 h-4 text-blue-400" />
                                    Yeni Müvekkil Ekle
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="w-full justify-start gap-3 h-10 hover:bg-purple-500/10 hover:border-purple-500/40"
                                    onClick={() => navigate("/clients")}
                                >
                                    <FolderOpen className="w-4 h-4 text-purple-400" />
                                    Müvekkil Listesi
                                </Button>
                            </CardContent>
                        </Card>

                        {/* Calendar */}
                        <Card className="border-primary/20 bg-card/80">
                            <CardHeader className="pb-2">
                                <div className="flex items-center justify-between gap-2 mb-1">
                                    <div className="flex items-center gap-2">
                                        <CalendarIcon className="w-4 h-4 text-primary" />
                                        <CardTitle className="text-sm font-semibold">
                                            Avukat Ajandası
                                        </CardTitle>
                                    </div>
                                    <Select
                                        value={calendarLawyerFilter}
                                        onValueChange={setCalendarLawyerFilter}
                                    >
                                        <SelectTrigger className="h-7 w-[130px] text-[10px] bg-background/50 border-primary/20">
                                            <SelectValue placeholder="Avukat Seçin" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="ALL" className="text-xs">Tümü</SelectItem>
                                            {calendarLawyerOptions.map(name => (
                                                <SelectItem key={name} value={name} className="text-xs">
                                                    {name}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <CardDescription className="text-xs">Önemli tarihler & duruşmalar</CardDescription>
                            </CardHeader>
                            <CardContent className="px-3 pb-4">
                                <Calendar
                                    mode="single"
                                    selected={selectedDate}
                                    onSelect={setSelectedDate}
                                    className="rounded-lg border-0 bg-transparent p-0 w-full"
                                    classNames={{
                                        months: "flex flex-col",
                                        month: "w-full",
                                        caption: "flex justify-center pt-1 relative items-center mb-2",
                                        caption_label: "text-sm font-medium",
                                        nav: "space-x-1 flex items-center",
                                        nav_button: "h-7 w-7 bg-transparent p-0 opacity-50 hover:opacity-100",
                                        table: "w-full border-collapse",
                                        head_row: "flex w-full",
                                        head_cell: "text-muted-foreground rounded-md flex-1 font-normal text-[0.7rem] text-center",
                                        row: "flex w-full mt-1",
                                        cell: "flex-1 text-center text-xs p-0",
                                        day: "h-7 w-full p-0 font-normal aria-selected:opacity-100 hover:bg-primary/20 rounded-md transition-colors",
                                        day_selected: "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground rounded-md",
                                        day_today: "bg-accent text-accent-foreground rounded-md",
                                        day_outside: "opacity-30",
                                    }}
                                    modifiers={{
                                        hasEvent: (date) => !!calendarEvents[date.toDateString()],
                                    }}
                                    modifiersStyles={{
                                        hasEvent: { fontWeight: "bold", textDecoration: "underline", color: "hsl(var(--primary))" },
                                    }}
                                />

                                {/* Selected Date Events */}
                                <div className="mt-3 space-y-2">
                                    <div className="flex items-center justify-between border-t border-border/50 pt-3">
                                        <p className="text-xs font-semibold text-muted-foreground">
                                            {selectedDate
                                                ? selectedDate.toLocaleDateString("tr-TR", { day: "numeric", month: "long" })
                                                : "Tarih Seçin"}
                                        </p>
                                        <Badge variant="outline" className="text-xs h-5">
                                            {selectedDateEvents.length} Etkinlik
                                        </Badge>
                                    </div>

                                    <div className="space-y-1.5 max-h-[140px] overflow-y-auto pr-1">
                                        {selectedDateEvents.length > 0 ? (
                                            selectedDateEvents.map((evt, idx) => (
                                                <div
                                                    key={idx}
                                                    onClick={() => navigate(`/cases/${evt.id}`)}
                                                    className="p-2.5 bg-background/60 border border-border/50 rounded-lg text-xs cursor-pointer hover:border-primary/40 transition-colors"
                                                >
                                                    <div className="font-semibold text-primary truncate">
                                                        {evt.esas_no || evt.tracking_no}
                                                    </div>
                                                    <div className="flex justify-between items-center text-muted-foreground mt-0.5">
                                                        <span className="truncate max-w-[120px]">{evt.court || "Mahkeme Yok"}</span>
                                                        <span className="flex items-center gap-1 shrink-0">
                                                            <User className="w-2.5 h-2.5" />
                                                            {evt.responsible_lawyer_name?.split(" ")[0] || "Av."}
                                                        </span>
                                                    </div>
                                                </div>
                                            ))
                                        ) : (
                                            <div className="text-center text-xs text-muted-foreground py-3">
                                                Bu tarihte ajanda boş.
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default Home;
