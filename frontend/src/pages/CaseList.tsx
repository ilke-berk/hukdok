import { useState, useEffect, useCallback, useMemo } from "react";
import { Header } from "@/components/Header";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
    Search, Gavel, FolderOpen, Scale, FileText, 
    Plus, Filter, ChevronRight, ChevronLeft, 
    Building2, Briefcase, Clock, CheckCircle2,
    TrendingUp, TrendingDown, MoreHorizontal,
    Library, ShieldCheck, FileBadge, ListChecks,
    Users, Calendar, X, Loader2
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useCases } from "../hooks/useCases";
import { useConfig } from "../hooks/useConfig";
import { toast } from "sonner";
import { useDebounce } from "../hooks/useDebounce";
import { Badge } from "@/components/ui/badge";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";

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
    parties?: { party_type: string; name: string; role: string }[];
}

const ITEMS_PER_PAGE = 15;

const CaseList = () => {
    const navigate = useNavigate();
    const { getCases, getCaseStats, isLoading: isHookLoading } = useCases();
    const { lawyers } = useConfig();

    // Core data state
    const [cases, setCases] = useState<Case[]>([]);
    const [totalCount, setTotalCount] = useState(0);
    const [stats, setStats] = useState({ total: 0, active: 0, closed: 0, appeal: 0 });
    const [isLoading, setIsLoading] = useState(true);

    // Filter states
    const [searchQuery, setSearchQuery] = useState("");
    const debouncedSearch = useDebounce(searchQuery, 400);
    const [selectedStatus, setSelectedStatus] = useState<string>("ALL");
    const [selectedLawyer, setSelectedLawyer] = useState<string>("ALL");
    const [selectedFileType, setSelectedFileType] = useState<string>("ALL");
    const [currentPage, setCurrentPage] = useState(1);

    const fetchCases = useCallback(async () => {
        // If no search and filters are at defaults, don't fetch automatically
        // Unless we want to show 'Recent' or 'All' - but user specifically asked NOT to
        if (!debouncedSearch && selectedStatus === "ALL" && selectedLawyer === "ALL" && selectedFileType === "ALL") {
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
                offset: offset,
                status: selectedStatus,
                lawyer: selectedLawyer,
                q: debouncedSearch || undefined
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
            if (statsData) setStats(statsData);
        } catch (error) {
            console.error("İstatistikler yüklenemedi", error);
        }
    }, [getCaseStats]);

    useEffect(() => {
        fetchCases();
    }, [fetchCases]);

    useEffect(() => {
        fetchStats();
    }, [fetchStats]);

    // Reset page on filter change
    useEffect(() => {
        setCurrentPage(1);
    }, [debouncedSearch, selectedStatus, selectedLawyer, selectedFileType]);

    const totalPages = Math.ceil(totalCount / ITEMS_PER_PAGE) || 1;
    const displayedCases = cases;

    const getStatusBadge = (status: string) => {
        const s = status.toUpperCase();
        if (s === "DERDEST") return <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20">Derdest</Badge>;
        if (s === "KAPALI") return <Badge className="bg-gray-500/10 text-gray-500 border-gray-500/20">Kapalı</Badge>;
        if (s === "TEMYIZ" || s === "ISTINAF") return <Badge className="bg-purple-500/10 text-purple-500 border-purple-500/20">Üst Yargı</Badge>;
        if (s === "KARAR") return <Badge className="bg-blue-500/10 text-blue-500 border-blue-500/20">Karar</Badge>;
        return <Badge variant="outline">{status}</Badge>;
    };

    return (
        <div className="min-h-screen bg-background text-foreground font-sans flex flex-col">
            <Header />

            <main className="flex-1 w-full px-4 sm:px-8 lg:px-12 py-8 flex flex-col gap-8">
                


                {/* STATS CARDS */}
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
                    <StatCard 
                        title="Yerel Mahkemeler" 
                        value={stats.active} 
                        description="Aktif Derdest Dosyalar"
                        icon={<Gavel className="w-6 h-6 text-primary" />}
                        trend="+15%"
                        trendUp={true}
                    />
                    <StatCard 
                        title="İstinaf Aşaması" 
                        value={stats.appeal} 
                        description="BAM'daki Dosya Sayısı"
                        icon={<Library className="w-6 h-6 text-rose-500/70" />}
                        trend="-2%"
                        trendUp={false}
                    />
                    <StatCard 
                        title="Yargıtay İncelemesi" 
                        value={Math.floor(stats.appeal * 0.4)} 
                        description="Temyizdeki Dosyalar"
                        icon={<ShieldCheck className="w-6 h-6 text-rose-500/70" />}
                        trend="+8%"
                        trendUp={true}
                    />
                    <StatCard 
                        title="Toplam Dosya" 
                        value={stats.total} 
                        description="Genel Arşiv Toplamı"
                        icon={<ListChecks className="w-6 h-6 text-rose-500/70" />}
                        trend="+4%"
                        trendUp={true}
                    />
                </div>

                {/* CENTERED SEARCH BAR */}
                <div className="flex justify-center -mt-2">
                    <div className="w-full max-w-3xl relative group">
                        <div className="absolute inset-0 bg-primary/5 rounded-2xl blur-2xl group-focus-within:bg-primary/10 transition-all duration-500 opacity-0 group-focus-within:opacity-100" />
                        <div className="relative">
                            <Search className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground group-focus-within:text-primary transition-colors" />
                            <Input 
                                className="pl-14 pr-12 h-16 text-[15px] bg-card/50 backdrop-blur-xl border-border/50 focus:border-primary/40 focus:ring-0 transition-all rounded-2xl shadow-lg hover:shadow-xl hover:border-border group-focus-within:bg-card/80 group-focus-within:shadow-primary/5"
                                placeholder="Dosya numarası, müvekkil adı veya konu ile hızlıca arayın..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                            {searchQuery && (
                                <button 
                                    onClick={() => setSearchQuery("")}
                                    className="absolute right-5 top-1/2 -translate-y-1/2 p-2 hover:bg-secondary rounded-full transition-colors"
                                >
                                    <X className="w-4 h-4 text-muted-foreground" />
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                <div className="flex flex-col xl:flex-row gap-6 items-start flex-1 min-h-0">
                    
                    {/* FILTERS SIDEBAR */}
                    <div className="w-full xl:w-[280px] shrink-0 flex flex-col gap-6">
                        <div className="bg-card rounded-xl border border-border p-6 flex flex-col gap-8 shadow-sm">
                            <div className="flex items-center justify-between">
                                <h3 className="text-[13px] font-bold text-foreground/80 uppercase tracking-widest flex items-center gap-2">
                                    <Filter className="w-4 h-4 text-primary" />
                                    Dosya Filtrele
                                </h3>
                                <button 
                                    onClick={() => {
                                        setSelectedStatus("ALL");
                                        setSelectedLawyer("ALL");
                                        setSelectedFileType("ALL");
                                        setSearchQuery("");
                                    }}
                                    className="text-[11px] text-muted-foreground hover:text-rose-600 transition-colors font-medium border-b border-transparent hover:border-rose-600"
                                >
                                    Temizle
                                </button>
                            </div>

                            <div className="space-y-6">
                                {/* File Type */}
                                <div className="space-y-3">
                                    <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest pl-1">DOSYA TÜRÜ</span>
                                    <Select value={selectedFileType} onValueChange={setSelectedFileType}>
                                        <SelectTrigger className="bg-secondary/30 border-border h-11 transition-all focus:ring-1 focus:ring-primary/40">
                                            <SelectValue placeholder="Tür Seçin" />
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

                                {/* Status */}
                                <div className="space-y-3">
                                    <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest pl-1">DURUM</span>
                                    <div className="flex flex-wrap gap-2">
                                        {["ALL", "DERDEST", "KARAR", "KAPALI", "TEMYIZ"].map(s => (
                                            <button
                                                key={s}
                                                onClick={() => setSelectedStatus(s)}
                                                className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all border ${
                                                    selectedStatus === s 
                                                    ? "bg-primary/20 border-primary text-primary" 
                                                    : "bg-secondary/30 border-border text-muted-foreground hover:bg-secondary/50"
                                                }`}
                                            >
                                                {s === "ALL" ? "Tümü" : s}
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {/* Lawyer */}
                                <div className="space-y-3">
                                    <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest pl-1">SORUMLU AVUKAT</span>
                                    <Select value={selectedLawyer} onValueChange={setSelectedLawyer}>
                                        <SelectTrigger className="bg-secondary/30 border-border h-11">
                                            <SelectValue placeholder="Avukat Seçin" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="ALL">Tüm Avukatlar</SelectItem>
                                            {lawyers.map(l => (
                                                <SelectItem key={l.name} value={l.name}>{l.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>
                        </div>

                        {/* ADD NEW CASE BUTTON */}
                        <Button 
                            onClick={() => navigate("/new-case/form")}
                            className="w-full bg-[#8B1430] hover:bg-[#701026] text-white font-semibold py-7 rounded-xl shadow-lg border-none transition-all active:scale-[0.98] flex items-center justify-center gap-3 group"
                        >
                            <Plus className="w-5 h-5 transition-transform group-hover:scale-110" />
                            <span className="text-[15px] tracking-wide">Yeni Dava Aç</span>
                        </Button>
                    </div>

                    {/* MAIN TABLE AREA */}
                    <div className="flex-1 min-w-0 bg-card rounded-xl border border-border flex flex-col overflow-hidden shadow-sm">
                        


                        {/* Table */}
                        <div className="flex-1 overflow-auto min-h-[400px]">
                            {isLoading ? (
                                <div className="h-full flex flex-col items-center justify-center p-20 gap-4">
                                    <Loader2 className="w-10 h-10 animate-spin text-primary/60" />
                                    <span className="text-sm text-muted-foreground font-medium animate-pulse">Dosya verileri alınıyor...</span>
                                </div>
                            ) : displayedCases.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center p-20 gap-3">
                                    {(!debouncedSearch && selectedStatus === "ALL" && selectedLawyer === "ALL" && selectedFileType === "ALL") ? (
                                        <>
                                            <Search className="w-12 h-12 text-primary/10" />
                                            <p className="text-muted-foreground font-medium text-center">
                                                Dosya aramak için yukarıdaki arama kutusunu kullanabilir <br/>
                                                veya soldaki filtrelerden birini seçebilirsiniz.
                                            </p>
                                        </>
                                    ) : (
                                        <>
                                            <X className="w-12 h-12 text-destructive/20" />
                                            <p className="text-muted-foreground font-medium">Aradığınız kriterlere uygun dosya bulunamadı.</p>
                                        </>
                                    )}
                                </div>
                            ) : (
                                <table className="w-full text-left border-collapse">
                                    <thead className="sticky top-0 bg-muted/40 backdrop-blur-md z-10 font-bold">
                                        <tr className="border-b border-border">
                                            <th className="px-8 py-5 text-[11px] font-bold text-muted-foreground uppercase tracking-widest w-[20%]">Müvekkil</th>
                                            <th className="px-8 py-5 text-[11px] font-bold text-muted-foreground uppercase tracking-widest w-[20%]">Dosya / Ofis No</th>
                                            <th className="px-8 py-5 text-[11px] font-bold text-muted-foreground uppercase tracking-widest w-[25%]">Mahkeme / Merci</th>
                                            <th className="px-8 py-5 text-[11px] font-bold text-muted-foreground uppercase tracking-widest w-[15%]">Avukat</th>
                                            <th className="px-8 py-5 text-[11px] font-bold text-muted-foreground uppercase tracking-widest w-[15%] text-right pr-12">Durum</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border/40">
                                        {displayedCases.map((c) => (
                                            <tr 
                                                key={c.id} 
                                                onClick={() => navigate(`/cases/${c.id}`)}
                                                className="group hover:bg-primary/[0.03] transition-colors cursor-pointer"
                                            >
                                                <td className="px-8 py-6">
                                                    <div className="flex flex-col gap-1">
                                                        <span className="font-bold text-[14px] text-foreground group-hover:text-primary transition-colors truncate max-w-[200px]">
                                                            {c.parties?.find(p => p.party_type === "CLIENT")?.name || "-"}
                                                        </span>
                                                        <span className="text-[11px] text-muted-foreground uppercase tracking-tight font-medium">Müvekkil</span>
                                                    </div>
                                                </td>
                                                <td className="px-8 py-6">
                                                    <div className="flex flex-col gap-1">
                                                        <span className="font-semibold text-[14px] text-foreground tabular-nums">
                                                            {c.esas_no || "Esas Belirtilmedi"}
                                                        </span>
                                                        <div className="flex items-center gap-1.5 opacity-60">
                                                            <Briefcase className="w-3 h-3" />
                                                            <span className="text-[11px] font-medium tracking-tighter">{c.tracking_no}</span>
                                                        </div>
                                                    </div>
                                                </td>
                                                <td className="px-8 py-6">
                                                    <div className="flex flex-col gap-1">
                                                        <span className="text-[13px] font-medium text-foreground/80 leading-relaxed truncate max-w-[300px]">
                                                            {c.court || "-"}
                                                        </span>
                                                        <span className="text-[11px] text-muted-foreground truncate italic">
                                                            {c.subject || "Konu belirtilmemiş"}
                                                        </span>
                                                    </div>
                                                </td>
                                                <td className="px-8 py-6">
                                                    <div className="flex items-center gap-2">
                                                        <Users className="w-3.5 h-3.5 text-primary opacity-40" />
                                                        <span className="text-[13px] font-medium text-muted-foreground">
                                                            {c.responsible_lawyer_name?.split(' ')[0] || "Atanmadı"}
                                                        </span>
                                                    </div>
                                                </td>
                                                <td className="px-8 py-6 text-right pr-12">
                                                    {getStatusBadge(c.status)}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>

                        {/* Pagination Footer */}
                        {totalCount > 0 && (
                            <div className="p-6 border-t border-border/40 flex justify-between items-center bg-secondary/10">
                                <span className="text-[12px] text-muted-foreground font-medium">
                                    Görüntülenen: <strong>{displayedCases.length}</strong> / Toplam: <strong>{totalCount}</strong>
                                </span>
                                <div className="flex items-center gap-2">
                                    <Button 
                                        variant="ghost" 
                                        size="sm" 
                                        disabled={currentPage === 1}
                                        onClick={() => setCurrentPage(p => p - 1)}
                                        className="h-9 gap-1 hover:bg-secondary"
                                    >
                                        <ChevronLeft className="w-4 h-4" />
                                        Geri
                                    </Button>
                                    <div className="px-3 h-9 flex items-center justify-center bg-secondary/40 border border-border rounded-lg text-xs font-bold tabular-nums">
                                        {currentPage} / {totalPages}
                                    </div>
                                    <Button 
                                        variant="ghost" 
                                        size="sm"
                                        disabled={currentPage === totalPages}
                                        onClick={() => setCurrentPage(p => p + 1)}
                                        className="h-9 gap-1 hover:bg-secondary"
                                    >
                                        İleri
                                        <ChevronRight className="w-4 h-4" />
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </main>
        </div>
    );
};

const StatCard = ({ title, value, description, icon, trend, trendUp }: any) => (
    <div className="bg-card border border-border rounded-xl p-6 flex items-center justify-start gap-5 shadow-sm relative overflow-hidden h-[120px] hover:shadow-md transition-shadow group">
        {icon && (
            <div className="z-10 bg-secondary/30 p-3 rounded-full border border-border flex-shrink-0 group-hover:bg-primary/5 transition-colors">
                {icon}
            </div>
        )}
        <div className="flex flex-col gap-1 z-10">
            <div className="flex items-center gap-3">
                <span className="text-[13px] text-muted-foreground font-semibold tracking-wide leading-none">{title}</span>
                <div className={`flex items-center gap-1 px-1.5 py-0.5 rounded-full border text-[9px] font-bold ${
                    trendUp 
                    ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-500" 
                    : "bg-rose-500/10 border-rose-500/20 text-rose-500"
                }`}>
                    {trendUp ? <TrendingUp className="w-2.5 h-2.5" /> : <TrendingDown className="w-2.5 h-2.5" />}
                    {trend}
                </div>
            </div>
            <span className="text-[28px] font-bold tracking-tight leading-none mt-0.5">{value}</span>
            <p className="text-[11px] text-muted-foreground font-medium mt-1">{description}</p>
        </div>

        {/* Subtle decorative background gradient */}
        <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-gradient-to-l from-rose-500/[0.03] to-transparent pointer-events-none"></div>
    </div>
);

export default CaseList;
