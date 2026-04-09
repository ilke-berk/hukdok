import { useParams, useNavigate } from "react-router-dom";
import { Header } from "@/components/Header";
import { Button } from "@/components/ui/button";
import { ArrowLeft, User, Scale, Clock, Gavel, FileText, CheckCircle2, AlertCircle, FileStack, TrendingUp, BarChart3, Users, History, Edit } from "lucide-react";
import { useCases } from "@/hooks/useCases";
import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
    DERDEST: { bg: "bg-emerald-500/15", text: "text-emerald-400", dot: "bg-emerald-400" },
    KARAR: { bg: "bg-blue-500/15", text: "text-blue-400", dot: "bg-blue-400" },
    KAPALI: { bg: "bg-gray-500/15", text: "text-gray-400", dot: "bg-gray-400" },
    TEMYIZ: { bg: "bg-purple-500/15", text: "text-purple-400", dot: "bg-purple-400" },
    INFAZ: { bg: "bg-orange-500/15", text: "text-orange-400", dot: "bg-orange-400" },
};

const getStatusStyle = (status: string) =>
    statusColors[status?.toLocaleUpperCase('tr-TR')] || { bg: "bg-primary/15", text: "text-primary", dot: "bg-primary" };

interface CaseDetailsData {
    status: string;
    esas_no?: string;
    tracking_no?: string;
    subject?: string;
    court?: string;
    responsible_lawyer_name?: string;
    uyap_lawyer_name?: string;
    opening_date?: string;
    maddi_tazminat?: number;
    manevi_tazminat?: number;
    history?: { date: string; action: string; user?: string; field?: string; old?: string; new?: string }[];
    parties?: { id: number; client_id?: number; party_type: string; name: string; role: string; tckn?: string; vergi_no?: string }[];
    lawyers?: { name: string; lawyer_id?: number | null }[];
    documents?: { id: number; created_at: string; uploaded_at?: string; document_type_code: string; belge_turu_adi?: string; summary?: string; stored_filename: string; original_filename: string; sharepoint_url?: string; case_party_id?: number | null; case_party_name?: string | null }[];
    [key: string]: unknown;
}

const CaseDetails = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { getCase, isLoading } = useCases();
    const [caseData, setCaseData] = useState<CaseDetailsData | null>(null);
    const [loadingLocal, setLoadingLocal] = useState(true);
    const [activeTab, setActiveTab] = useState("overview");

    useEffect(() => {
        const fetchCaseData = async () => {
            if (!id) return;
            setLoadingLocal(true);
            const data = await getCase(parseInt(id));
            if (data) {
                setCaseData(data);
            }
            setLoadingLocal(false);
        };
        fetchCaseData();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    if (loadingLocal || isLoading) {
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
                                                    <span key={i} className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium bg-primary/10 text-primary border border-primary/20 whitespace-nowrap">{l.name}</span>
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
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Tabs Container */}
                <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                    <TabsList className="grid w-full grid-cols-3 md:w-auto md:inline-flex mb-4">
                        <TabsTrigger value="overview" className="gap-2">
                            <BarChart3 className="w-4 h-4" />
                            <span className="hidden sm:inline">Genel Bilgiler</span>
                            <span className="sm:hidden">Genel</span>
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
                                                "CLIENT": "bg-blue-500/10 text-blue-500 border-blue-500/20",
                                                "COUNTER": "bg-red-500/10 text-red-500 border-red-500/20",
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
                                                </div>
                                            </div>
                                            <div className="shrink-0 max-sm:w-full">
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    className="w-full sm:w-auto"
                                                    onClick={() => {
                                                        if (doc.sharepoint_url) {
                                                            window.open(doc.sharepoint_url, '_blank', 'noopener,noreferrer');
                                                            toast.success("Belge Açılıyor", { description: "Dosya güvenli SharePoint arşivinden getiriliyor." });
                                                        } else {
                                                            toast.info("Belge Hazırlanıyor", { description: `"${doc.original_filename}" henüz SharePoint'e yüklenmemiş veya arka planda işleniyor olabilir.` });
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
        </div>
    );
};

export default CaseDetails;
