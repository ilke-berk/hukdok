import { useParams, useNavigate } from "react-router-dom";
import { Header } from "@/components/Header";
import { Button } from "@/components/ui/button";
import {
    ArrowLeft, Gavel, Scale, Clock, FileText, AlertCircle,
    FileStack, Users, History, Edit, Plus, Link2,
    Building2, ChevronRight, BarChart3, TrendingUp,
    User, CheckCircle2
} from "lucide-react";
import { useCases } from "@/hooks/useCases";
import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";

// --- Tip renkleri ---
const fileTypeConfig: Record<string, { label: string; color: string; bg: string; border: string; icon: React.ReactNode }> = {
    Hukuk:   { label: "Hukuk",   color: "text-blue-400",   bg: "bg-blue-500/10",   border: "border-blue-500/30",   icon: <Scale className="w-4 h-4" /> },
    İcra:    { label: "İcra",    color: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/30", icon: <Building2 className="w-4 h-4" /> },
    Ceza:    { label: "Ceza",    color: "text-red-400",    bg: "bg-red-500/10",    border: "border-red-500/30",    icon: <Gavel className="w-4 h-4" /> },
    İdare:   { label: "İdare",   color: "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/30", icon: <FileText className="w-4 h-4" /> },
    Ticaret: { label: "Ticaret", color: "text-green-400",  bg: "bg-green-500/10",  border: "border-green-500/30",  icon: <BarChart3 className="w-4 h-4" /> },
};

const getFileTypeConfig = (type?: string) =>
    fileTypeConfig[type ?? ""] ?? {
        label: type || "Diğer",
        color: "text-primary",
        bg: "bg-primary/10",
        border: "border-primary/30",
        icon: <FileText className="w-4 h-4" />,
    };

// --- Statü renkleri ---
const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
    DERDEST: { bg: "bg-emerald-500/15", text: "text-emerald-400", dot: "bg-emerald-400" },
    KARAR:   { bg: "bg-blue-500/15",    text: "text-blue-400",    dot: "bg-blue-400" },
    KAPALI:  { bg: "bg-gray-500/15",    text: "text-gray-400",    dot: "bg-gray-400" },
    TEMYIZ:  { bg: "bg-purple-500/15",  text: "text-purple-400",  dot: "bg-purple-400" },
    INFAZ:   { bg: "bg-orange-500/15",  text: "text-orange-400",  dot: "bg-orange-400" },
};
const getStatusStyle = (status: string) =>
    statusColors[status?.toLocaleUpperCase("tr-TR")] ?? { bg: "bg-primary/15", text: "text-primary", dot: "bg-primary" };

// --- Tipler ---
interface CaseInGroup {
    id: number;
    tracking_no: string;
    esas_no?: string;
    status: string;
    file_type?: string;
    court?: string;
    opening_date?: string;
    subject?: string;
    responsible_lawyer_name?: string;
    uyap_lawyer_name?: string;
    maddi_tazminat?: number;
    manevi_tazminat?: number;
    parties?: { id: number; client_id?: number; party_type: string; name: string; role: string }[];
    lawyers?: { name: string; lawyer_id?: number | null }[];
    documents?: {
        id: number;
        created_at: string;
        uploaded_at?: string;
        document_type_code: string;
        belge_turu_adi?: string;
        summary?: string;
        stored_filename: string;
        original_filename: string;
        sharepoint_url?: string;
        case_party_id?: number | null;
        case_party_name?: string | null;
    }[];
    history?: { date: string; action: string; user?: string; field?: string; old?: string; new?: string }[];
}

interface CaseGroupData {
    id: number;
    name?: string;
    client_name?: string;
    subject?: string;
    created_at?: string;
    cases: CaseInGroup[];
}

// -------------------------------------------------------
// Ana bileşen
// -------------------------------------------------------
const CaseGroup = () => {
    const { groupId } = useParams<{ groupId: string }>();
    const navigate = useNavigate();
    const { getCaseGroup } = useCases();

    const [groupData, setGroupData] = useState<CaseGroupData | null>(null);
    const [loadingLocal, setLoadingLocal] = useState(true);
    const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
    const [activeDetailTab, setActiveDetailTab] = useState("overview");

    useEffect(() => {
        const fetch = async () => {
            if (!groupId) return;
            setLoadingLocal(true);
            const data = await getCaseGroup(parseInt(groupId));
            if (data) {
                setGroupData(data);
                if (data.cases.length > 0) setSelectedCaseId(data.cases[0].id);
            }
            setLoadingLocal(false);
        };
        fetch();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [groupId]);

    // URL'den gelen case parametresi (deep-link: /case-groups/1?case=42)
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const caseParam = params.get("case");
        if (caseParam && groupData) {
            const found = groupData.cases.find(c => c.id === parseInt(caseParam));
            if (found) setSelectedCaseId(found.id);
        }
    }, [groupData]);

    const selectedCase = groupData?.cases.find(c => c.id === selectedCaseId) ?? null;

    const formatCurrency = (amount?: number) =>
        new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" }).format(amount ?? 0);

    // ---- Loading ----
    if (loadingLocal) {
        return (
            <div className="min-h-screen bg-background flex flex-col">
                <Header />
                <main className="flex-1 container mx-auto py-6 px-4 space-y-6">
                    <Skeleton className="h-8 w-40" />
                    <Skeleton className="h-28 w-full rounded-xl" />
                    <Skeleton className="h-12 w-full rounded-xl" />
                    <Skeleton className="h-[400px] w-full rounded-xl" />
                </main>
            </div>
        );
    }

    // ---- Not found ----
    if (!groupData) {
        return (
            <div className="min-h-screen bg-background flex flex-col">
                <Header />
                <main className="flex-1 container mx-auto py-6 px-4 flex flex-col items-center justify-center space-y-4">
                    <AlertCircle className="w-16 h-16 text-muted-foreground opacity-50" />
                    <h2 className="text-xl font-semibold">Dava Dosyası Bulunamadı</h2>
                    <p className="text-muted-foreground text-center">
                        Aradığınız dava dosyası sistemde bulunamadı veya silinmiş olabilir.
                    </p>
                    <Button onClick={() => navigate("/cases")} className="gap-2 mt-4">
                        <ArrowLeft className="w-4 h-4" />
                        Dava Listesine Dön
                    </Button>
                </main>
            </div>
        );
    }

    const clientName =
        groupData.client_name ??
        groupData.cases[0]?.parties?.find(p => p.party_type === "CLIENT")?.name ??
        "Bilinmeyen Müvekkil";

    const groupSubject = groupData.subject ?? groupData.cases[0]?.subject ?? "Konu belirtilmemiş";

    return (
        <div className="min-h-screen bg-background flex flex-col">
            <Header />

            <main className="flex-1 container mx-auto py-6 px-4 space-y-6">

                {/* Breadcrumb + actions */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <Button
                        variant="ghost"
                        className="gap-2 w-fit hover:bg-muted"
                        onClick={() => navigate("/cases")}
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Dava Listesine Dön
                    </Button>
                    <div className="flex gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            className="gap-2"
                            onClick={() => {
                                if (selectedCase) navigate("/new-case/form", { state: { case: selectedCase } });
                            }}
                        >
                            <Edit className="w-4 h-4" />
                            Davayı Güncelle
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            className="gap-2"
                            onClick={() => toast.info("Yeni İlişkili Dava", { description: "Bu dosyaya yeni bir ilişkili dava eklemek için Yeni Dava formunu kullanın." })}
                        >
                            <Plus className="w-4 h-4" />
                            İlişkili Dava Ekle
                        </Button>
                    </div>
                </div>

                {/* === GRUP BAŞLIK KARTI === */}
                <Card className="border-border/60 bg-card/80 overflow-hidden relative">
                    <div className="absolute top-0 left-0 w-full h-1.5 bg-primary" />
                    <CardContent className="p-6 md:p-8">
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                            <div className="space-y-1.5">
                                <div className="flex items-center gap-2 text-muted-foreground text-sm">
                                    <Link2 className="w-4 h-4 text-primary" />
                                    <span className="font-semibold text-primary">Dava Dosyası</span>
                                    <ChevronRight className="w-3 h-3" />
                                    <span>#{groupData.id}</span>
                                </div>
                                <h1 className="text-2xl md:text-3xl font-bold tracking-tight">{clientName}</h1>
                                <p className="text-muted-foreground text-base">{groupSubject}</p>
                            </div>

                            {/* Sağ: istatistikler */}
                            <div className="flex gap-3 shrink-0 flex-wrap">
                                {[
                                    { val: groupData.cases.length, label: "Dava" },
                                    { val: groupData.cases.reduce((s, c) => s + (c.documents?.length ?? 0), 0), label: "Evrak" },
                                    { val: groupData.cases.filter(c => c.status?.toUpperCase() === "DERDEST").length, label: "Aktif" },
                                    { val: groupData.cases.filter(c => c.status?.toUpperCase() === "KAPALI").length, label: "Kapalı" },
                                ].map(({ val, label }) => (
                                    <div key={label} className="bg-secondary/30 rounded-xl border border-border/50 px-5 py-3 text-center min-w-[72px]">
                                        <p className="text-2xl font-bold">{val}</p>
                                        <p className="text-[11px] text-muted-foreground mt-0.5">{label}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* === DAVA TÜRÜ SEÇİCİ === */}
                <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${groupData.cases.length}, minmax(0, 1fr))` }}>
                    {groupData.cases.map(c => {
                        const cfg = getFileTypeConfig(c.file_type);
                        const st = getStatusStyle(c.status);
                        const isActive = c.id === selectedCaseId;
                        const docCount = c.documents?.length ?? 0;
                        const partyCount = c.parties?.length ?? 0;
                        return (
                            <button
                                key={c.id}
                                onClick={() => { setSelectedCaseId(c.id); setActiveDetailTab("overview"); }}
                                className={`relative group flex flex-col text-left rounded-2xl border-2 p-5 transition-all duration-200 overflow-hidden
                                    ${isActive
                                        ? `${cfg.bg} ${cfg.border} shadow-lg shadow-black/10`
                                        : "bg-card/60 border-border/40 hover:border-border hover:bg-card/80"
                                    }`}
                            >
                                {/* Aktifken renkli sol şerit */}
                                {isActive && (
                                    <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl ${cfg.color.replace("text-", "bg-")}`} />
                                )}

                                {/* İkon */}
                                <div className={`w-11 h-11 rounded-xl flex items-center justify-center mb-3 transition-all
                                    ${isActive ? `${cfg.bg} border ${cfg.border}` : "bg-secondary/40 border border-border/50"}`}>
                                    <span className={`scale-125 ${isActive ? cfg.color : "text-muted-foreground"}`}>
                                        {cfg.icon}
                                    </span>
                                </div>

                                {/* Tür adı */}
                                <p className={`text-base font-bold leading-tight ${isActive ? cfg.color : "text-foreground"}`}>
                                    {cfg.label}
                                </p>

                                {/* Esas no */}
                                <p className="text-xs font-mono text-muted-foreground mt-1 tabular-nums truncate">
                                    {c.esas_no || c.tracking_no}
                                </p>

                                {/* Mahkeme */}
                                <p className="text-[11px] text-muted-foreground/70 mt-0.5 truncate leading-tight">
                                    {c.court || "Mahkeme belirtilmemiş"}
                                </p>

                                {/* Alt satır: durum + mini istatistik */}
                                <div className="flex items-center justify-between mt-3 pt-3 border-t border-border/30">
                                    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full ${st.bg} ${st.text}`}>
                                        <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
                                        {c.status}
                                    </span>
                                    <div className="flex items-center gap-2.5 text-[10px] text-muted-foreground">
                                        {docCount > 0 && (
                                            <span className="flex items-center gap-0.5">
                                                <FileText className="w-3 h-3" />{docCount}
                                            </span>
                                        )}
                                        {partyCount > 0 && (
                                            <span className="flex items-center gap-0.5">
                                                <Users className="w-3 h-3" />{partyCount}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </button>
                        );
                    })}
                </div>

                {/* === SEÇİLİ DAVA DETAYI === */}
                {selectedCase ? (
                    <div className="space-y-4">
                        {/* Seçili dava başlık satırı */}
                        <SelectedCaseHeader
                            c={selectedCase}
                            onViewFull={() => navigate(`/cases/${selectedCase.id}`)}
                        />

                        {/* Seçili dava tab'ları */}
                        <Tabs value={activeDetailTab} onValueChange={setActiveDetailTab}>
                            <TabsList className="grid w-full grid-cols-3 md:w-auto md:inline-flex mb-4">
                                <TabsTrigger value="overview" className="gap-2">
                                    <BarChart3 className="w-4 h-4" />
                                    <span className="hidden sm:inline">Genel Bilgiler</span>
                                    <span className="sm:hidden">Genel</span>
                                </TabsTrigger>
                                <TabsTrigger value="parties" className="gap-2">
                                    <Users className="w-4 h-4" />
                                    <span>Taraflar</span>
                                    {(selectedCase.parties?.length ?? 0) > 0 && (
                                        <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-[10px] h-4">
                                            {selectedCase.parties!.length}
                                        </Badge>
                                    )}
                                </TabsTrigger>
                                <TabsTrigger value="documents" className="gap-2">
                                    <FileStack className="w-4 h-4" />
                                    <span>Belgeler</span>
                                    {(selectedCase.documents?.length ?? 0) > 0 && (
                                        <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-[10px] h-4">
                                            {selectedCase.documents!.length}
                                        </Badge>
                                    )}
                                </TabsTrigger>
                            </TabsList>

                            {/* Genel Bilgiler */}
                            <TabsContent value="overview" className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <Card className="bg-card/60">
                                        <CardHeader>
                                            <CardTitle className="text-lg">Tazminat Bilgileri</CardTitle>
                                            <CardDescription>Davaya ait parasal değerler</CardDescription>
                                        </CardHeader>
                                        <CardContent className="space-y-3">
                                            <div className="flex items-center justify-between p-3 rounded-lg border bg-background/50">
                                                <span className="text-muted-foreground">Maddi Tazminat</span>
                                                <span className="font-semibold text-lg">{formatCurrency(selectedCase.maddi_tazminat)}</span>
                                            </div>
                                            <div className="flex items-center justify-between p-3 rounded-lg border bg-background/50">
                                                <span className="text-muted-foreground">Manevi Tazminat</span>
                                                <span className="font-semibold text-lg">{formatCurrency(selectedCase.manevi_tazminat)}</span>
                                            </div>
                                        </CardContent>
                                    </Card>

                                    <Card className="bg-card/60">
                                        <CardHeader>
                                            <CardTitle className="text-lg">Dava Geçmişi</CardTitle>
                                            <CardDescription>Durum değişiklikleri</CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                            {(selectedCase.history?.length ?? 0) > 0 ? (
                                                <div className="space-y-3 max-h-56 overflow-y-auto pr-1">
                                                    {selectedCase.history!.map((h, idx) => (
                                                        <div key={idx} className="flex items-start gap-3 text-sm">
                                                            <div className="w-2 h-2 rounded-full bg-primary mt-1.5 shrink-0" />
                                                            <div>
                                                                <span className="font-medium">
                                                                    {h.field === "status" ? "Statü Değişikliği" : h.field}
                                                                </span>
                                                                <div className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
                                                                    <span className="line-through opacity-70">{h.old || "-"}</span>
                                                                    <ArrowLeft className="w-3 h-3 rotate-180" />
                                                                    <span className="font-medium text-primary">{h.new}</span>
                                                                    <span className="ml-auto">{new Date(h.date).toLocaleDateString("tr-TR")}</span>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            ) : (
                                                <div className="text-center py-8 text-muted-foreground">
                                                    <TrendingUp className="w-8 h-8 opacity-20 mx-auto mb-2" />
                                                    <p className="text-sm">Henüz geçmiş kaydı yok.</p>
                                                </div>
                                            )}
                                        </CardContent>
                                    </Card>
                                </div>
                            </TabsContent>

                            {/* Taraflar */}
                            <TabsContent value="parties">
                                <Card className="bg-card/60">
                                    <CardHeader>
                                        <CardTitle className="text-lg">Taraf Bilgileri</CardTitle>
                                        <CardDescription>Davacı, davalı ve diğer ilgililer</CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        {(selectedCase.parties?.length ?? 0) > 0 ? (
                                            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                                                {selectedCase.parties!.map((party, idx) => {
                                                    const roleColors: Record<string, string> = {
                                                        CLIENT: "bg-blue-500/10 text-blue-500 border-blue-500/20",
                                                        COUNTER: "bg-red-500/10 text-red-500 border-red-500/20",
                                                        THIRD: "bg-gray-500/10 text-gray-500 border-gray-500/20",
                                                    };
                                                    const colorClass = roleColors[party.party_type] || "bg-primary/10 text-primary border-primary/20";
                                                    const typeLabel =
                                                        party.party_type === "CLIENT" ? "Müvekkil" :
                                                        party.party_type === "COUNTER" ? "Karşı Taraf" : "Üçüncü Şahıs";
                                                    return (
                                                        <div key={idx} className="flex flex-col p-4 rounded-xl border bg-background/50 gap-2">
                                                            <div className="font-semibold flex items-center gap-2">
                                                                {party.name}
                                                                {party.client_id && (
                                                                    <Badge variant="outline" className="text-[10px]">Kayıtlı</Badge>
                                                                )}
                                                            </div>
                                                            <div className="flex gap-2 mt-auto pt-2">
                                                                <Badge className={`text-xs ${colorClass}`} variant="outline">{typeLabel}</Badge>
                                                                <Badge variant="secondary" className="text-xs">{party.role}</Badge>
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        ) : (
                                            <div className="text-center py-12 text-muted-foreground border border-dashed rounded-xl">
                                                <Users className="w-10 h-10 opacity-20 mx-auto mb-3" />
                                                <p>Bu davaya eklenmiş taraf bulunmuyor.</p>
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>
                            </TabsContent>

                            {/* Belgeler */}
                            <TabsContent value="documents">
                                <Card className="bg-card/60">
                                    <CardHeader>
                                        <CardTitle className="text-lg">Evrak Listesi</CardTitle>
                                        <CardDescription>Bu davaya bağlı belgeler</CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        {(selectedCase.documents?.length ?? 0) > 0 ? (
                                            <div className="space-y-3">
                                                {selectedCase.documents!.map(doc => (
                                                    <div key={doc.id} className="flex flex-col sm:flex-row items-start sm:items-center justify-between p-4 rounded-xl border bg-background/50 hover:border-primary/40 transition-all gap-4">
                                                        <div className="flex items-start gap-4 flex-1 min-w-0">
                                                            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                                                                <FileText className="w-5 h-5 text-primary" />
                                                            </div>
                                                            <div className="min-w-0 flex-1">
                                                                <h4 className="font-semibold text-sm truncate">{doc.stored_filename || doc.original_filename}</h4>
                                                                <div className="flex items-center gap-2 mt-1 flex-wrap">
                                                                    {doc.belge_turu_adi && (
                                                                        <Badge variant="secondary" className="text-[10px]">{doc.belge_turu_adi}</Badge>
                                                                    )}
                                                                    {doc.uploaded_at && (
                                                                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                                                                            <Clock className="w-3 h-3" />
                                                                            {new Date(doc.uploaded_at).toLocaleString("tr-TR")}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <Button
                                                            variant="outline"
                                                            size="sm"
                                                            className="shrink-0"
                                                            onClick={() => {
                                                                if (doc.sharepoint_url) {
                                                                    window.open(doc.sharepoint_url, "_blank", "noopener,noreferrer");
                                                                } else {
                                                                    toast.info("Belge hazırlanıyor", { description: "Dosya henüz işlenmemiş olabilir." });
                                                                }
                                                            }}
                                                        >
                                                            Detay / İndir
                                                        </Button>
                                                    </div>
                                                ))}
                                            </div>
                                        ) : (
                                            <div className="text-center py-12 text-muted-foreground border border-dashed rounded-xl">
                                                <FileStack className="w-10 h-10 opacity-20 mx-auto mb-3" />
                                                <p className="font-medium text-foreground">Henüz evrak yüklenmemiş</p>
                                                <p className="text-sm mt-1 mb-4">Bu davaya ait belge bulunmuyor.</p>
                                                <Button
                                                    variant="outline"
                                                    onClick={() => navigate("/upload", { state: { preselectCase: selectedCase } })}
                                                    className="gap-2"
                                                >
                                                    <FileStack className="w-4 h-4" />
                                                    Evrak Yükle
                                                </Button>
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>
                            </TabsContent>
                        </Tabs>
                    </div>
                ) : (
                    <Card className="bg-card/60">
                        <CardContent className="py-12 flex flex-col items-center gap-3 text-muted-foreground">
                            <Gavel className="w-10 h-10 opacity-20" />
                            <p>Detayları görmek için yukarıdan bir dava türü seçin.</p>
                        </CardContent>
                    </Card>
                )}

                {/* === GRUP ÖZET TABLOSU === */}
                <Card className="bg-card/60">
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                            <Link2 className="w-4 h-4 text-primary" />
                            Dosyadaki Tüm Davalar
                        </CardTitle>
                        <CardDescription>
                            Aynı dava dosyasına bağlı tüm davalar — herhangi bir esas numarası bu dosyayı açar
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="rounded-xl border border-border overflow-hidden">
                            <table className="w-full text-sm">
                                <thead className="bg-muted/40">
                                    <tr className="border-b border-border">
                                        <th className="px-4 py-3 text-left text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Tür</th>
                                        <th className="px-4 py-3 text-left text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Esas No</th>
                                        <th className="px-4 py-3 text-left text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Mahkeme</th>
                                        <th className="px-4 py-3 text-left text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Avukat</th>
                                        <th className="px-4 py-3 text-left text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Açılış</th>
                                        <th className="px-4 py-3 text-right text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Durum</th>
                                        <th className="px-4 py-3 text-right text-[11px] font-bold text-muted-foreground uppercase tracking-wider"></th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-border/40">
                                    {groupData.cases.map(c => {
                                        const cfg = getFileTypeConfig(c.file_type);
                                        const st = getStatusStyle(c.status);
                                        const isActive = c.id === selectedCaseId;
                                        return (
                                            <tr
                                                key={c.id}
                                                onClick={() => { setSelectedCaseId(c.id); setActiveDetailTab("overview"); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                                                className={`group cursor-pointer transition-colors ${isActive ? "bg-primary/5" : "hover:bg-muted/30"}`}
                                            >
                                                <td className="px-4 py-4">
                                                    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold ${cfg.bg} ${cfg.color} ${cfg.border} border`}>
                                                        {cfg.icon}
                                                        {cfg.label}
                                                    </div>
                                                </td>
                                                <td className="px-4 py-4 font-mono text-[13px] font-semibold tabular-nums">
                                                    {c.esas_no || <span className="text-muted-foreground italic text-xs">Belirtilmedi</span>}
                                                </td>
                                                <td className="px-4 py-4 text-muted-foreground max-w-[200px] truncate">{c.court || "-"}</td>
                                                <td className="px-4 py-4 text-muted-foreground">
                                                    {c.lawyers?.[0]?.name ?? c.responsible_lawyer_name?.split(" ")[0] ?? "Atanmadı"}
                                                </td>
                                                <td className="px-4 py-4 text-muted-foreground text-xs tabular-nums">
                                                    {c.opening_date ? new Date(c.opening_date).toLocaleDateString("tr-TR") : "-"}
                                                </td>
                                                <td className="px-4 py-4 text-right">
                                                    <Badge className={`${st.bg} ${st.text} border-0`}>{c.status}</Badge>
                                                </td>
                                                <td className="px-4 py-4 text-right">
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        className="opacity-0 group-hover:opacity-100 transition-opacity h-7 text-xs gap-1"
                                                        onClick={e => { e.stopPropagation(); navigate(`/cases/${c.id}`); }}
                                                    >
                                                        Tam Görünüm
                                                        <ChevronRight className="w-3 h-3" />
                                                    </Button>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </CardContent>
                </Card>
            </main>
        </div>
    );
};

// --- Seçili dava başlık alt bileşeni ---
const SelectedCaseHeader = ({ c, onViewFull }: { c: CaseInGroup; onViewFull: () => void }) => {
    const cfg = getFileTypeConfig(c.file_type);
    const st = getStatusStyle(c.status);
    return (
        <Card className={`border ${cfg.border} bg-card/80 overflow-hidden relative`}>
            <div className={`absolute top-0 left-0 w-full h-1 ${cfg.color.replace("text-", "bg-")}`} />
            <CardContent className="p-5">
                <div className="flex flex-wrap items-start gap-4 justify-between">
                    <div className="space-y-2">
                        <div className="flex items-center gap-2 flex-wrap">
                            <div className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold ${cfg.bg} ${cfg.color} ${cfg.border} border`}>
                                {cfg.icon}
                                {cfg.label} Davası
                            </div>
                            <Badge className={`text-xs px-2.5 py-1 font-semibold ${st.bg} ${st.text} border-0`}>
                                <span className={`w-1.5 h-1.5 rounded-full ${st.dot} mr-1.5 inline-block`} />
                                {c.status}
                            </Badge>
                        </div>
                        <div className="flex items-center gap-2">
                            <Gavel className={`w-5 h-5 ${cfg.color}`} />
                            <span className="text-xl font-bold tracking-tight tabular-nums">
                                {c.esas_no || c.tracking_no}
                            </span>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-8 gap-y-2 text-sm text-muted-foreground pt-1">
                            <div className="flex items-center gap-2">
                                <Scale className="w-3.5 h-3.5 shrink-0" />
                                <span>{c.court || "Mahkeme belirtilmemiş"}</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <User className="w-3.5 h-3.5 shrink-0" />
                                <span>{c.lawyers?.[0]?.name ?? c.responsible_lawyer_name ?? "Avukat atanmadı"}</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <Clock className="w-3.5 h-3.5 shrink-0" />
                                <span>
                                    {c.opening_date
                                        ? new Date(c.opening_date).toLocaleDateString("tr-TR")
                                        : "Tarih belirtilmemiş"}
                                </span>
                            </div>
                        </div>
                    </div>
                    <Button variant="outline" size="sm" className="gap-1.5 shrink-0" onClick={onViewFull}>
                        Tam Dava Sayfası
                        <ChevronRight className="w-3.5 h-3.5" />
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
};

export default CaseGroup;
