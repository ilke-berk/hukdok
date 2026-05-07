import { useParams, useNavigate } from "react-router-dom";
import { Header } from "@/components/Header";
import { Button } from "@/components/ui/button";
import { ArrowLeft, User, Scale, Clock, Gavel, FileText, AlertCircle, FileStack, TrendingUp, BarChart3, Users, Edit, Link2, Building2, Plus, Activity, Copy, Check, CheckCircle2, XCircle, MinusCircle, RotateCcw } from "lucide-react";
import { useCases } from "@/hooks/useCases";
import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import AddRelationModal from "@/components/AddRelationModal";
import CaseTrackingPanel from "@/components/CaseTrackingPanel";
import { EmailModal } from "@/components/email/EmailModal";
import { apiClient } from "@/lib/api";

const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
    DERDEST: { bg: "bg-emerald-500/15", text: "text-emerald-400", dot: "bg-emerald-400" },
    KARAR:   { bg: "bg-indigo-500/15",  text: "text-indigo-400",  dot: "bg-indigo-400" },
    KAPALI:  { bg: "bg-gray-500/15",    text: "text-gray-400",    dot: "bg-gray-400" },
    TEMYIZ:  { bg: "bg-amber-500/15",   text: "text-amber-400",   dot: "bg-amber-400" },
    INFAZ:   { bg: "bg-orange-500/15",  text: "text-orange-400",  dot: "bg-orange-400" },
};

const getStatusStyle = (status: string) =>
    statusColors[status?.toLocaleUpperCase('tr-TR')] || { bg: "bg-primary/15", text: "text-primary", dot: "bg-primary" };

interface CaseDetailsData {
    status: string;
    esas_no?: string;
    tracking_no?: string;
    subject?: string;
    court?: string;
    file_type?: string;
    responsible_lawyer_name?: string;
    uyap_lawyer_name?: string;
    opening_date?: string;
    maddi_tazminat?: number;
    manevi_tazminat?: number;
    case_group_id?: number;
    hasar_dosya_no?: string;
    hukuk_no?: string;
    klasor_no_2?: string;
    atama_tarihi?: string;
    notes?: string;
    related_cases?: { id: number; esas_no?: string; tracking_no?: string; file_type?: string; court?: string; status: string }[];
    history?: { date: string; action: string; user?: string; field?: string; old?: string; new?: string }[];
    parties?: { id: number; client_id?: number; party_type: string; name: string; role: string; tckn?: string; vergi_no?: string }[];
    lawyers?: { name: string; lawyer_id?: number | null }[];
    documents?: { id: number; created_at: string; uploaded_at?: string; document_type_code: string; belge_turu_adi?: string; belge_turu_kodu?: string; summary?: string; stored_filename: string; original_filename: string; sharepoint_url?: string; case_party_id?: number | null; case_party_name?: string | null; muvekkil_adi?: string | null; email_sent?: boolean | null; email_error?: string | null }[];
    [key: string]: unknown;
}

// Tip badge renkleri (CaseGroup ile tutarlı)
const fileTypeMeta: Record<string, { color: string; bg: string; border: string; dot: string; icon: React.ReactNode }> = {
    Hukuk:   { color: "text-blue-400",   bg: "bg-blue-500/10",   border: "border-blue-500/30",   dot: "bg-blue-400",   icon: <Scale className="w-4 h-4" /> },
    İcra:    { color: "text-amber-400",  bg: "bg-amber-500/10",  border: "border-amber-500/30",  dot: "bg-amber-400",  icon: <Building2 className="w-4 h-4" /> },
    Ceza:    { color: "text-red-400",    bg: "bg-red-500/10",    border: "border-red-500/30",    dot: "bg-red-400",    icon: <Gavel className="w-4 h-4" /> },
    İdare:   { color: "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/30", dot: "bg-purple-400", icon: <FileText className="w-4 h-4" /> },
    Ticaret: { color: "text-teal-400",   bg: "bg-teal-500/10",   border: "border-teal-500/30",   dot: "bg-teal-400",   icon: <BarChart3 className="w-4 h-4" /> },
};
const getFileTypeMeta = (type?: string) =>
    fileTypeMeta[type ?? ""] ?? { color: "text-primary", bg: "bg-primary/10", border: "border-primary/30", dot: "bg-primary", icon: <FileText className="w-4 h-4" /> };

interface RelatedCaseBrief {
    id: number;
    tracking_no: string;
    esas_no?: string | null;
    court?: string | null;
    status: string;
    file_type?: string | null;
    relation_id?: number;
    is_manual: boolean;
}

const CopyButton = ({ value }: { value: string }) => {
    const [copied, setCopied] = useState(false);
    return (
        <button
            onClick={() => { navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
            className="ml-1 p-0.5 rounded opacity-50 hover:opacity-100 transition-opacity"
            title="Kopyala"
        >
            {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
        </button>
    );
};

const CaseDetails = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { getCase, getRelatedCases, addCaseRelation, removeCaseRelation } = useCases();
    const [caseData, setCaseData] = useState<CaseDetailsData | null>(null);
    const [loadingLocal, setLoadingLocal] = useState(true);
    const [activeTab, setActiveTab] = useState("overview");
    const [relatedBrief, setRelatedBrief] = useState<RelatedCaseBrief[]>([]);
    const [addRelationOpen, setAddRelationOpen] = useState(false);
    const [resendDoc, setResendDoc] = useState<NonNullable<CaseDetailsData["documents"]>[number] | null>(null);
    const [resendLoading, setResendLoading] = useState(false);

    const fetchRelated = async () => {
        if (!id) return;
        const result = await getRelatedCases(parseInt(id));
        if (result) setRelatedBrief(result.manual ?? []);
    };

    const handleAddRelation = async (targetCaseId: number, relationType: string, note: string | null) => {
        const result = await addCaseRelation(parseInt(id!), { target_case_id: targetCaseId, relation_type: relationType, note });
        if (result) {
            toast.success("Dava bağlantısı eklendi");
            await fetchRelated();
            return true;
        }
        toast.error("Bağlantı eklenemedi");
        return false;
    };

    const handleRemoveRelation = async (relationId: number) => {
        const ok = await removeCaseRelation(parseInt(id!), relationId);
        if (ok) {
            toast.success("Bağlantı kaldırıldı");
            await fetchRelated();
        } else {
            toast.error("Bağlantı kaldırılamadı");
        }
    };

    const handleResendConfirm = async (
        to: string[],
        cc: string[],
        shouldSend: boolean,
        _teblig?: string,
        perRecipientMessages?: Record<string, string>,
    ) => {
        if (!resendDoc || !shouldSend) { setResendDoc(null); return; }
        setResendLoading(true);
        try {
            const res = await apiClient.fetch(`/api/documents/${resendDoc.id}/resend-email`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ to, cc, messages: perRecipientMessages }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Hata");
            }
            toast.success("E-posta yeniden gönderildi");
            const data = await getCase(parseInt(id!));
            if (data) setCaseData(data);
        } catch (e: unknown) {
            toast.error("E-posta gönderilemedi", { description: e instanceof Error ? e.message : String(e) });
        } finally {
            setResendLoading(false);
            setResendDoc(null);
        }
    };

    const handleAssignParty = async (docId: number, partyId: number | null) => {
        try {
            const res = await apiClient.fetch(`/api/documents/${docId}/party`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ case_party_id: partyId }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Güncelleme başarısız");
            }
            toast.success(partyId ? "Belge müvekkile atandı" : "Belge dava geneline alındı");
            // Refresh case data to reflect new grouping
            const data = await getCase(parseInt(id!));
            if (data) setCaseData(data);
        } catch (e: unknown) {
            toast.error("Müvekkil ataması başarısız", { description: e instanceof Error ? e.message : String(e) });
        }
    };

    useEffect(() => {
        const fetchCaseData = async () => {
            if (!id) return;
            setLoadingLocal(true);
            const data = await getCase(parseInt(id));
            if (data) setCaseData(data);
            setLoadingLocal(false);
        };
        fetchCaseData();
        fetchRelated();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    if (loadingLocal) {
        return (
            <div className="min-h-screen bg-background flex flex-col">
                <Header />
                <main className="flex-1 container mx-auto py-6 px-4 space-y-6">
                    <Button variant="ghost" className="gap-2 w-fit mb-4" disabled>
                        <ArrowLeft className="w-4 h-4" />
                        Listeye Dön
                    </Button>
                    <Skeleton className="h-24 w-full rounded-xl" />
                    <Skeleton className="h-10 w-full rounded-xl" />
                    <Skeleton className="h-[400px] w-full rounded-xl" />
                </main>
            </div>
        );
    }

    if (!caseData) {
        return (
            <div className="min-h-screen bg-background flex flex-col">
                <Header />
                <main className="flex-1 container mx-auto py-6 px-4 flex flex-col items-center justify-center space-y-4">
                    <AlertCircle className="w-16 h-16 text-muted-foreground opacity-50" />
                    <h2 className="text-xl font-semibold">Dava Bulunamadı</h2>
                    <p className="text-muted-foreground text-center">Aradığınız dava sistemde bulunamadı veya silinmiş olabilir.</p>
                    <Button onClick={() => navigate("/")} className="gap-2 mt-4">
                        <ArrowLeft className="w-4 h-4" />
                        Dashboard'a Dön
                    </Button>
                </main>
            </div>
        );
    }

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" }).format(amount);
    };

    const style = getStatusStyle(caseData.status);

    return (
        <div className="min-h-screen bg-background flex flex-col">
            <Header />

            <main className="flex-1 container mx-auto py-6 px-4 space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <Button variant="ghost" className="gap-2 w-fit hover:bg-muted" onClick={() => navigate("/")}>
                        <ArrowLeft className="w-4 h-4" />
                        Dava Listesine Dön
                    </Button>
                    <div className="flex gap-2">
                        <Button
                            variant="default"
                            size="sm"
                            className="gap-2 bg-primary text-primary-foreground hover:bg-primary/90"
                            onClick={() => navigate("/new-case/form", { state: { case: caseData } })}
                        >
                            <Edit className="w-4 h-4" />
                            Davayı Güncelle
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            className="gap-2"
                            onClick={() => navigate("/upload", { state: { preselectCase: caseData } })}
                        >
                            <FileStack className="w-4 h-4" />
                            Evrak Ekle
                        </Button>
                    </div>
                </div>

                {/* Case Header Card */}
                <Card className="border-border/60 bg-card/80 overflow-hidden relative">
                    {/* Top colored line according to status */}
                    <div className={`absolute top-0 left-0 w-full h-1.5 ${style.dot}`} />

                    <CardContent className="p-6 md:p-8">
                        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
                            <div className="space-y-4 flex-1">
                                <div className="flex flex-wrap items-center gap-3">
                                    <div className="flex items-center gap-2">
                                        <Gavel className="w-6 h-6 text-primary shrink-0" />
                                        <h1 className="text-2xl md:text-3xl font-bold tracking-tight">
                                            {caseData.esas_no || caseData.tracking_no}
                                        </h1>
                                    </div>
                                    <Badge className={`text-sm px-3 py-1 font-semibold ${style.bg} ${style.text} hover:${style.bg} border-0`}>
                                        {caseData.status}
                                    </Badge>
                                </div>

                                <div className="flex items-center gap-2 text-muted-foreground">
                                    <FileText className="w-4 h-4 shrink-0" />
                                    <p className="text-lg md:text-xl font-medium text-foreground/80">
                                        {caseData.subject || "Konu belirtilmemiş"}
                                    </p>
                                </div>

                                {/* Hasar / Hukuk No pill badges */}
                                {(caseData.hasar_dosya_no || caseData.hukuk_no) && (
                                    <div className="flex flex-wrap gap-2">
                                        {caseData.hasar_dosya_no && (
                                            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary/40 border border-border/60 text-foreground/70">
                                                <FileText className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
                                                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Hasar No</span>
                                                <span className="font-mono font-bold text-sm">{caseData.hasar_dosya_no}</span>
                                                <CopyButton value={caseData.hasar_dosya_no} />
                                            </div>
                                        )}
                                        {caseData.hukuk_no && (
                                            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary/40 border border-border/60 text-foreground/70">
                                                <Scale className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
                                                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Hukuk No</span>
                                                <span className="font-mono font-bold text-sm">{caseData.hukuk_no}</span>
                                                <CopyButton value={caseData.hukuk_no} />
                                            </div>
                                        )}
                                    </div>
                                )}

                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-y-4 gap-x-8 text-sm pt-4">
                                    <div className="flex items-center gap-2.5">
                                        <Scale className="w-4 h-4 text-muted-foreground shrink-0" />
                                        <span className="text-muted-foreground">Mahkeme:</span>
                                        <span className="font-medium">{caseData.court || "Belirtilmemiş"}</span>
                                    </div>
                                    <div className="flex items-start gap-2.5">
                                        <User className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                                        <span className="text-muted-foreground mt-0.5">Sorumlu Avukat:</span>
                                        <div className="font-medium flex flex-wrap gap-1">
                                            {caseData.lawyers && caseData.lawyers.length > 0 ? (
                                                caseData.lawyers.map((l, i) => (
                                                    <span key={i} className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium bg-secondary/40 text-foreground/80 border border-border/60 whitespace-nowrap">{l.name}</span>
                                                ))
                                            ) : (
                                                <span>{caseData.responsible_lawyer_name || "Atanmadı"}</span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2.5">
                                        <User className="w-4 h-4 text-muted-foreground shrink-0" />
                                        <span className="text-muted-foreground">UYAP Avukatı:</span>
                                        <span className="font-medium">{caseData.uyap_lawyer_name || "Atanmadı"}</span>
                                    </div>
                                    <div className="flex items-center gap-2.5">
                                        <Clock className="w-4 h-4 text-muted-foreground shrink-0" />
                                        <span className="text-muted-foreground">Açılış Tarihi:</span>
                                        <span className="font-medium">
                                            {caseData.opening_date ? new Date(caseData.opening_date).toLocaleDateString("tr-TR") : "-"}
                                        </span>
                                    </div>
                                </div>

                                {/* İlişkili davalar — her zaman görünür */}
                                <div className="pt-4 border-t border-border/40">
                                    <div className="flex items-center justify-between mb-3">
                                        <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-1.5">
                                            <Link2 className="w-3.5 h-3.5 text-primary" />
                                            Bağlantılı Davalar
                                            {relatedBrief.length > 0 && (
                                                <span className="ml-1 px-1.5 py-0.5 rounded-full bg-primary/10 text-primary text-[10px] font-bold">{relatedBrief.length}</span>
                                            )}
                                        </p>
                                        <button
                                            onClick={() => setAddRelationOpen(true)}
                                            className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-primary transition-colors px-2 py-1 rounded-lg hover:bg-primary/10"
                                        >
                                            <Plus className="w-3.5 h-3.5" />
                                            Dava Bağla
                                        </button>
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        {/* Mevcut dava — aktif */}
                                        <div className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl border-2 ${style.bg} border-current ${style.text} cursor-default`}>
                                            <Gavel className="w-4 h-4 shrink-0" />
                                            <div className="flex flex-col">
                                                <span className="text-xs font-bold leading-none">{caseData.file_type || "Bu Dava"}</span>
                                                <span className="text-[10px] opacity-70 font-mono mt-0.5 tabular-nums">{caseData.esas_no || caseData.tracking_no}</span>
                                            </div>
                                            <span className={`w-2 h-2 rounded-full ${style.dot} ring-2 ring-current ring-offset-1 ring-offset-transparent`} />
                                        </div>

                                        {/* Bağlı davalar */}
                                        {relatedBrief.map(rc => {
                                            const meta = getFileTypeMeta(rc.file_type ?? undefined);
                                            const rst = getStatusStyle(rc.status);
                                            return (
                                                <div key={rc.id} className="group flex items-center gap-1">
                                                    <button
                                                        onClick={() => navigate(`/cases/${rc.id}`)}
                                                        className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl border border-border/60 bg-card/60 hover:border-primary/40 hover:bg-primary/5 text-muted-foreground hover:text-foreground transition-all"
                                                    >
                                                        <span className={`${meta.color}`}>{meta.icon}</span>
                                                        <div className="flex flex-col items-start">
                                                            <span className="text-xs font-bold leading-none">{rc.file_type || "Dava"}</span>
                                                            <span className="text-[10px] opacity-60 font-mono mt-0.5 tabular-nums">{rc.esas_no || rc.tracking_no}</span>
                                                        </div>
                                                        <span className={`w-1.5 h-1.5 rounded-full ${rst.dot}`} />
                                                    </button>
                                                    {rc.relation_id && (
                                                        <button
                                                            onClick={() => handleRemoveRelation(rc.relation_id!)}
                                                            className="opacity-0 group-hover:opacity-100 p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                                                            title="Bağlantıyı kaldır"
                                                        >
                                                            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                                                        </button>
                                                    )}
                                                </div>
                                            );
                                        })}

                                        {/* Boş durum */}
                                        {relatedBrief.length === 0 && (
                                            <button
                                                onClick={() => setAddRelationOpen(true)}
                                                className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl border border-dashed border-border/60 text-muted-foreground hover:border-primary/40 hover:text-primary hover:bg-primary/5 transition-all text-xs"
                                            >
                                                <Plus className="w-3.5 h-3.5" />
                                                Bağlantılı dava ekle
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Tabs Container */}
                <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                    <TabsList className="grid w-full grid-cols-4 md:w-auto md:inline-flex mb-4">
                        <TabsTrigger value="overview" className="gap-2">
                            <BarChart3 className="w-4 h-4" />
                            <span className="hidden sm:inline">Genel Bilgiler</span>
                            <span className="sm:hidden">Genel</span>
                        </TabsTrigger>
                        <TabsTrigger value="tracking" className="gap-2">
                            <Activity className="w-4 h-4" />
                            <span className="hidden sm:inline">Takip</span>
                            <span className="sm:hidden">Takip</span>
                        </TabsTrigger>
                        <TabsTrigger value="parties" className="gap-2">
                            <Users className="w-4 h-4" />
                            <span className="hidden sm:inline">Taraflar</span>
                            <span className="sm:hidden">Taraflar</span>
                            {caseData.parties?.length > 0 && (
                                <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-[10px] h-4">
                                    {caseData.parties.length}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger value="documents" className="gap-2">
                            <FileStack className="w-4 h-4" />
                            <span className="hidden sm:inline">Belgeler</span>
                            <span className="sm:hidden">Belgeler</span>
                            {caseData.documents?.length > 0 && (
                                <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-[10px] h-4">
                                    {caseData.documents.length}
                                </Badge>
                            )}
                        </TabsTrigger>
                    </TabsList>

                    {/* Overview Tab */}
                    <TabsContent value="overview" className="space-y-4">
                        {/* Dosya / Hasar Bilgileri */}
                        {(caseData.hasar_dosya_no || caseData.hukuk_no || caseData.klasor_no_2 || caseData.atama_tarihi || caseData.notes) && (
                            <Card className="bg-card/60">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-lg flex items-center gap-2">
                                        <FileText className="w-4 h-4 text-primary" />
                                        Dosya Bilgileri
                                    </CardTitle>
                                    <CardDescription>Hasar, hukuk numaraları ve ek bilgiler</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                        {caseData.hasar_dosya_no && (
                                            <div className="flex flex-col gap-0.5 p-3 rounded-lg border bg-background/50">
                                                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Hasar Dosya No</span>
                                                <span className="font-mono font-medium">{caseData.hasar_dosya_no as string}</span>
                                            </div>
                                        )}
                                        {caseData.hukuk_no && (
                                            <div className="flex flex-col gap-0.5 p-3 rounded-lg border bg-background/50">
                                                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Hukuk No</span>
                                                <span className="font-mono font-medium">{caseData.hukuk_no as string}</span>
                                            </div>
                                        )}
                                        {caseData.klasor_no_2 && (
                                            <div className="flex flex-col gap-0.5 p-3 rounded-lg border bg-background/50">
                                                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Klasör No (Eski)</span>
                                                <span className="font-mono font-medium text-sm truncate" title={caseData.klasor_no_2 as string}>{caseData.klasor_no_2 as string}</span>
                                            </div>
                                        )}
                                        {caseData.atama_tarihi && (
                                            <div className="flex flex-col gap-0.5 p-3 rounded-lg border bg-background/50">
                                                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Atama Tarihi</span>
                                                <span className="font-medium">{new Date(caseData.atama_tarihi as string).toLocaleDateString("tr-TR")}</span>
                                            </div>
                                        )}
                                    </div>
                                    {caseData.notes && (
                                        <div className="mt-3 p-3 rounded-lg border bg-background/50">
                                            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Notlar</span>
                                            <p className="text-sm whitespace-pre-wrap">{caseData.notes as string}</p>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        )}

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <Card className="bg-card/60">
                                <CardHeader>
                                    <CardTitle className="text-lg">Tazminat Bilgileri</CardTitle>
                                    <CardDescription>Davaya ait parantez içi maddi değerler</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div className="flex items-center justify-between p-3 rounded-lg border bg-background/50">
                                        <span className="text-muted-foreground">Maddi Tazminat</span>
                                        <span className="font-semibold text-lg">{formatCurrency(caseData.maddi_tazminat || 0)}</span>
                                    </div>
                                    <div className="flex items-center justify-between p-3 rounded-lg border bg-background/50">
                                        <span className="text-muted-foreground">Manevi Tazminat</span>
                                        <span className="font-semibold text-lg">{formatCurrency(caseData.manevi_tazminat || 0)}</span>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card className="bg-card/60">
                                <CardHeader>
                                    <CardTitle className="text-lg">Dava Geçmişi</CardTitle>
                                    <CardDescription>Sistem üzerindeki durum değişiklikleri</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    {caseData.history?.length > 0 ? (
                                        <div className="space-y-4 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-border before:to-transparent">
                                            {caseData.history.map((h: { date: string; action: string; user?: string; field?: string; old?: string; new?: string }, idx: number) => (
                                                <div key={idx} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                                                    <div className="flex items-center justify-center w-10 h-10 rounded-full border border-primary/20 bg-background shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow flex-col relative z-20 mx-auto">
                                                        <div className="w-2 h-2 rounded-full bg-primary" />
                                                    </div>
                                                    <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-3 rounded-lg border bg-background/50 text-sm">
                                                        <div className="flex items-center justify-between space-x-2 mb-1">
                                                            <div className="font-bold text-foreground">
                                                                {h.field === "status" ? "Statü Değişikliği" : h.field}
                                                            </div>
                                                            <time className="text-xs text-muted-foreground">
                                                                {new Date(h.date).toLocaleDateString("tr-TR")}
                                                            </time>
                                                        </div>
                                                        <div className="text-muted-foreground text-xs flex items-center gap-2">
                                                            <span className="line-through opacity-70">{h.old || "-"}</span>
                                                            <ArrowLeft className="w-3 h-3 rotate-180" />
                                                            <span className="font-medium text-primary">{h.new}</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="text-center py-8 text-muted-foreground">
                                            <TrendingUp className="w-8 h-8 opacity-20 mx-auto mb-2" />
                                            <p className="text-sm">Henüz bir geçmiş kaydı bulunmuyor.</p>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    </TabsContent>

                    {/* Tracking Tab */}
                    <TabsContent value="tracking">
                        <CaseTrackingPanel
                            caseId={parseInt(id!)}
                            caseData={caseData as Record<string, unknown>}
                            onRefresh={async () => {
                                const data = await getCase(parseInt(id!));
                                if (data) setCaseData(data);
                            }}
                        />
                    </TabsContent>

                    {/* Parties Tab */}
                    <TabsContent value="parties">
                        <Card className="bg-card/60">
                            <CardHeader>
                                <CardTitle className="text-lg">Taraf Bilgileri</CardTitle>
                                <CardDescription>Davacı, davalı ve diğer ilgililer</CardDescription>
                            </CardHeader>
                            <CardContent>
                                {caseData.parties?.length > 0 ? (
                                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                                        {caseData.parties.map((party: { id: number; client_id?: number; party_type: string; name: string; role: string; tckn?: string; vergi_no?: string }, idx: number) => {
                                            const roleColors: Record<string, string> = {
                                                "CLIENT": "bg-primary/10 text-primary border-primary/20",
                                                "COUNTER": "bg-transparent text-red-500 border-red-500/40",
                                                "THIRD": "bg-gray-500/10 text-gray-500 border-gray-500/20",
                                            };
                                            const colorClass = roleColors[party.party_type] || "bg-primary/10 text-primary border-primary/20";

                                            // Make party_type more readable
                                            const typeLabel = party.party_type === "CLIENT" ? "Müvekkil" : party.party_type === "COUNTER" ? "Karşı Taraf" : "Üçüncü Şahıs";

                                            return (
                                                <div 
                                                    key={idx} 
                                                    className="flex flex-col p-4 rounded-xl border bg-background/50 gap-2 cursor-pointer hover:border-primary/50 transition-colors group"
                                                    onClick={() => {
                                                        setActiveTab("documents");
                                                        setTimeout(() => {
                                                            const el = document.getElementById(`party-docs-${party.id}`);
                                                            if (el) {
                                                                el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                                            } else {
                                                                toast.info("Belge Bulunamadı", { description: "Bu tarafa ait özel bir belge henüz sisteme yüklenmemiş." });
                                                            }
                                                        }, 150);
                                                    }}
                                                >
                                                    <div className="flex justify-between items-start gap-2">
                                                        <div className="font-semibold group-hover:text-primary transition-colors flex items-center gap-2">
                                                            {party.name}
                                                        </div>
                                                        {party.client_id && (
                                                            <Badge variant="outline" className="text-[10px] shrink-0">Kayıtlı</Badge>
                                                        )}
                                                    </div>
                                                    <div className="flex justify-between items-end mt-auto pt-2">
                                                        <div className="flex gap-2">
                                                            <Badge className={`text-xs ${colorClass}`} variant="outline">
                                                                {typeLabel}
                                                            </Badge>
                                                            <Badge variant="secondary" className="text-xs">
                                                                {party.role}
                                                            </Badge>
                                                        </div>
                                                        <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 text-[10px] text-muted-foreground mr-1">
                                                            <FileStack className="w-3 h-3" />
                                                            <span>Dosyalar</span>
                                                        </div>
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

                    {/* Documents Tab */}
                    <TabsContent value="documents">
                        <Card className="bg-card/60">
                            <CardHeader>
                                <CardTitle className="text-lg">Evrak Listesi</CardTitle>
                                <CardDescription>Davaya bağlanan ve analiz edilen tüm belgeler</CardDescription>
                            </CardHeader>
                            <CardContent>
                                {caseData.documents?.length > 0 ? (() => {
                                    // Belgeleri grupla: null → dava geneli, dolu → müvekkile ait
                                    const caseWide = caseData.documents!.filter(d => d.case_party_id == null);
                                    const byParty = caseData.documents!.reduce<Record<string, { name: string; docs: typeof caseData.documents }>>((acc, d) => {
                                        if (d.case_party_id == null) return acc;
                                        const key = String(d.case_party_id);
                                        if (!acc[key]) acc[key] = { name: d.case_party_name || `Taraf #${key}`, docs: [] };
                                        acc[key].docs!.push(d);
                                        return acc;
                                    }, {});

                                    const clientParties = (caseData.parties || []).filter(p => p.party_type === "CLIENT");

                                    const DocCard = ({ doc }: { doc: NonNullable<typeof caseData.documents>[number] }) => (
                                        <div key={doc.id} className="group flex flex-col sm:flex-row items-start sm:items-center justify-between p-4 rounded-xl border bg-background/50 hover:border-primary/40 transition-all gap-4">
                                            <div className="flex items-start gap-4 flex-1 min-w-0">
                                                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                                                    <FileText className="w-5 h-5 text-primary" />
                                                </div>
                                                <div className="min-w-0 flex-1">
                                                    <h4 className="font-semibold text-sm truncate" title={doc.stored_filename || doc.original_filename}>
                                                        {doc.stored_filename || doc.original_filename}
                                                    </h4>
                                                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                                                        {doc.belge_turu_adi && (
                                                            <Badge variant="secondary" className="text-[10px] sm:text-xs font-normal">
                                                                {doc.belge_turu_adi}
                                                            </Badge>
                                                        )}
                                                        {doc.uploaded_at && (
                                                            <div className="flex items-center text-xs text-muted-foreground gap-1">
                                                                <Clock className="w-3 h-3" />
                                                                {new Date(doc.uploaded_at).toLocaleString("tr-TR")}
                                                            </div>
                                                        )}
                                                    </div>
                                                    {/* Müvekkil atama seçici — sadece CLIENT taraf varsa göster */}
                                                    {clientParties.length > 0 && (
                                                        <div className="mt-2">
                                                            <Select
                                                                value={doc.case_party_id != null ? String(doc.case_party_id) : "all"}
                                                                onValueChange={(v) => handleAssignParty(doc.id, v === "all" ? null : Number(v))}
                                                            >
                                                                <SelectTrigger className="h-7 text-[11px] w-44 border-dashed">
                                                                    <Users className="w-3 h-3 mr-1 shrink-0" />
                                                                    <SelectValue />
                                                                </SelectTrigger>
                                                                <SelectContent>
                                                                    <SelectItem value="all">Tüm Dava</SelectItem>
                                                                    {clientParties.map(p => (
                                                                        <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                                                                    ))}
                                                                </SelectContent>
                                                            </Select>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="shrink-0 max-sm:w-full flex flex-col sm:flex-row sm:items-center gap-2">
                                                {/* Email durum ikonu */}
                                                {doc.email_sent === true && (
                                                    <span title="E-posta gönderildi" className="text-emerald-400 flex items-center gap-1 text-xs whitespace-nowrap">
                                                        <CheckCircle2 className="w-4 h-4 shrink-0" />
                                                        <span className="hidden sm:inline">Gönderildi</span>
                                                    </span>
                                                )}
                                                {doc.email_sent === false && (
                                                    <span title={doc.email_error || "E-posta gönderilemedi"} className="text-red-400 flex items-center gap-1 text-xs whitespace-nowrap">
                                                        <XCircle className="w-4 h-4 shrink-0" />
                                                        <span className="hidden sm:inline">Başarısız</span>
                                                    </span>
                                                )}
                                                {doc.email_sent == null && (
                                                    <span title="E-posta gönderilmedi / atlandı" className="text-muted-foreground/40 flex items-center">
                                                        <MinusCircle className="w-4 h-4" />
                                                    </span>
                                                )}
                                                {/* Tekrar Gönder butonu */}
                                                {doc.email_sent === false && (
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        className="w-full sm:w-auto text-xs border-red-500/40 text-red-400 hover:bg-red-500/10 hover:text-red-400"
                                                        onClick={() => setResendDoc(doc)}
                                                    >
                                                        <RotateCcw className="w-3 h-3 mr-1" />
                                                        Tekrar Gönder
                                                    </Button>
                                                )}
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    className="w-full sm:w-auto"
                                                    onClick={async () => {
                                                        if (!doc.sharepoint_url) {
                                                            toast.info("Belge Hazırlanıyor", { description: `"${doc.original_filename}" henüz SharePoint'e yüklenmemiş veya arka planda işleniyor olabilir.` });
                                                            return;
                                                        }
                                                        toast.info("İndiriliyor...", { description: "Belge güvenli arşivden getiriliyor." });
                                                        try {
                                                            const res = await apiClient.fetch(`/api/documents/${doc.id}/download`);
                                                            if (!res.ok) throw new Error("Sunucu hatası");
                                                            const blob = await res.blob();
                                                            const url = URL.createObjectURL(blob);
                                                            const a = document.createElement("a");
                                                            a.href = url;
                                                            a.download = doc.original_filename || "belge";
                                                            a.click();
                                                            URL.revokeObjectURL(url);
                                                        } catch {
                                                            toast.error("İndirme Hatası", { description: "Belge indirilemedi. Lütfen tekrar deneyin." });
                                                        }
                                                    }}
                                                >
                                                    Detay / İndir
                                                </Button>
                                            </div>
                                        </div>
                                    );

                                    return (
                                        <div className="space-y-6">
                                            {/* Grup 1: Tüm davayı ilgilendiren belgeler */}
                                            {caseWide.length > 0 && (
                                                <div className="space-y-2">
                                                    <div className="flex items-center gap-2 pb-1 border-b">
                                                        <FileStack className="w-4 h-4 text-muted-foreground" />
                                                        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Dava Belgeleri</span>
                                                        <Badge variant="outline" className="text-[10px] ml-auto">{caseWide.length}</Badge>
                                                    </div>
                                                    <div className="space-y-3">
                                                        {caseWide.map(doc => <DocCard key={doc.id} doc={doc} />)}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Grup 2+: Müvekkile ait belgeler */}
                                            {Object.entries(byParty).map(([partyId, group]) => (
                                                <div key={partyId} id={`party-docs-${partyId}`} className="space-y-2 scroll-mt-20">
                                                    <div className="flex items-center gap-2 pb-1 border-b">
                                                        <Users className="w-4 h-4 text-muted-foreground" />
                                                        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground truncate">{group.name}</span>
                                                        <Badge variant="outline" className="text-[10px] ml-auto shrink-0">{group.docs!.length}</Badge>
                                                    </div>
                                                    <div className="space-y-3">
                                                        {group.docs!.map(doc => <DocCard key={doc.id} doc={doc} />)}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    );
                                })() : (
                                    <div className="text-center py-12 text-muted-foreground border border-dashed rounded-xl">
                                        <FileStack className="w-10 h-10 opacity-20 mx-auto mb-3" />
                                        <p className="font-medium text-foreground">Henüz evrak yüklenmemiş</p>
                                        <p className="text-sm mt-1 mb-4">Bu davaya ait belge bulunmuyor. Yeni bir belge yükleyerek davaya bağlayabilirsiniz.</p>
                                        <Button variant="outline" onClick={() => navigate("/upload", { state: { preselectCase: caseData } })} className="gap-2">
                                            <FileStack className="w-4 h-4" />
                                            Evrak Yükle
                                        </Button>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                </Tabs>

            </main>

            <AddRelationModal
                open={addRelationOpen}
                currentCaseId={parseInt(id!)}
                onClose={() => setAddRelationOpen(false)}
                onSave={handleAddRelation}
            />

            <EmailModal
                isOpen={resendDoc != null}
                onClose={() => setResendDoc(null)}
                onConfirm={handleResendConfirm}
                isLoading={resendLoading}
                analysisContext={resendDoc ? {
                    muvekkil_adi: resendDoc.muvekkil_adi ?? undefined,
                    belge_turu_kodu: resendDoc.belge_turu_kodu ?? undefined,
                } : undefined}
            />
        </div>
    );
};

export default CaseDetails;
