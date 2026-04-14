import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useClients } from "@/hooks/useClients";
import { useConfig } from "@/hooks/useConfig";
import { useCases, CaseData } from "@/hooks/useCases";
import { Header } from "@/components/Header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Gavel, User, FileText, Scale, Save, Briefcase, Building, Search, RefreshCw, Sparkles, Loader2, Upload, Check, ChevronsUpDown, Plus, X, Calendar, Banknote, Coins, Heart, Trash2 } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { FileUpload } from "@/components/FileUpload";
import { generateTrackingNumber } from "@/lib/caseNumberUtils";
import { cn } from "@/lib/utils";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

// Tüm listeler artık useConfig üzerinden dinamik olarak alınıyor.

interface EditModeParty {
    party_type: string;
    name: string;
    role: string;
    birth_year?: number;
    gender?: string;
    client_id?: number | null;
}

interface EditModeCaseData {
    id?: number;
    tracking_no: string;
    status: string;
    history?: { date: string; action: string; user?: string; old?: string; new?: string; field?: string }[];
    file_type?: string;
    sub_type?: string;
    subject?: string;
    court?: string;
    responsible_lawyer_name?: string;
    uyap_lawyer_name?: string;
    esas_no?: string;
    opening_date?: string;
    service_type?: string;
    maddi_tazminat?: number | string;
    manevi_tazminat?: number | string;
    acceptance_date?: string;
    bureau_type?: string;
    sub_type_extra?: string;
    judicial_unit?: string;
    parties?: EditModeParty[];
    lawyers?: { name: string; lawyer_id?: number | null }[];
}

interface CaseSearchResult {
    id: number;
    tracking_no: string;
    esas_no?: string;
    court?: string;
    status: string;
}


interface CaseHistoryEntry {
    date: string;
    action: string;
    user?: string;
    old?: string;
    new?: string;
    field?: string;
}

const toTitleCase = (str: string): string => {
    if (!str) return "";
    return str
        .split(/(\s+|[,;]+)/)
        .map(part => {
            if (/^(\s+|[,;]+)$/.test(part)) return part;
            if (part.length === 0) return part;
            return part.charAt(0).toLocaleUpperCase('tr-TR') + part.slice(1).toLocaleLowerCase('tr-TR');
        })
        .join("");
};

const toUpperTR = (str: string) => str.toLocaleUpperCase('tr-TR').trim();


const NewCase = () => {
    const navigate = useNavigate();
    const location = useLocation();

    // API Hooks
    const { saveCase, updateCase, deleteCase, getCase, isLoading: isSaving } = useCases();
    const { clients: dbClients, isLoading: isDbLoading } = useClients();
    const {
        caseSubjects, lawyers,
        fileTypes, courtTypesByParent, mainPartyRoles, thirdPartyRoles, bureauTypes, specialties,
    } = useConfig();

    const DOSYA_TURLERI = fileTypes.map(f => f.name ?? "");
    const ALT_TURLER: Record<string, string[]> = courtTypesByParent
        ? Object.fromEntries(Object.entries(courtTypesByParent).map(([k, v]) => [k, v.map(i => i.name ?? "")]))
        : {};
    const TARAF_ROLLERI = mainPartyRoles.map(r => r.name ?? "");
    const UCUNCU_TARAF_ROLLERI = thirdPartyRoles.map(r => r.name ?? "");
    const BURO_OZEL_TURU = bureauTypes.map(b => b.name ?? "");
    const HIZMET_TURLERI = [
        { label: "Rapor", index: 0 },
        { label: "Danışmanlık", index: 1 },
        { label: "Dava", index: 2 },
        { label: "İcra", index: 3 },
        { label: "Yazışma", index: 4 }
    ];

    // Check if we are in edit mode
    const editModeCase = location.state?.case as EditModeCaseData | undefined;
    const isEditMode = !!editModeCase;

    // Generate case tracking ID using central utility
    const [caseId, setCaseId] = useState(editModeCase?.tracking_no || generateTrackingNumber());
    const [isLoading, setIsLoading] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState<CaseSearchResult[]>([]);
    const [isSearchingCases, setIsSearchingCases] = useState(false);
    const [caseStatus, setCaseStatus] = useState(editModeCase?.status || "DERDEST");
    const [caseHistory, setCaseHistory] = useState<CaseHistoryEntry[]>(editModeCase?.history || []);

    // Config

    // Form States
    const [showClientConfirm, setShowClientConfirm] = useState(false);
    const [pendingUnregistered, setPendingUnregistered] = useState<{ name: string }[]>([]);
    const [clientSearchValues, setClientSearchValues] = useState<{ [key: number]: string }>({});

    const [formData, setFormData] = useState({
        fileType: editModeCase?.file_type || "",
        subType: editModeCase?.sub_type || "",
        subject: editModeCase?.subject || "",
        court: editModeCase?.court || "",
        category: "",
        lawyer: editModeCase?.responsible_lawyer_name || "",
        uyapLawyer: editModeCase?.uyap_lawyer_name || "",
        esasNo: editModeCase?.esas_no || "",
        fileOpeningDate: editModeCase?.opening_date || "",
        serviceType: "00000", // Default service type code
        maddiTazminat: editModeCase?.maddi_tazminat?.toString() || "",
        maneviTazminat: editModeCase?.manevi_tazminat?.toString() || "",
        acceptanceDate: editModeCase?.acceptance_date || "",
        bureauType: editModeCase?.bureau_type || "",
        subTypeExtra: editModeCase?.sub_type_extra || "",
        judicialUnit: editModeCase?.judicial_unit || ""
    });

    const [selectedLawyers, setSelectedLawyers] = useState<Array<{ name: string; lawyer_id?: number | null }>>(
        editModeCase?.lawyers?.map((l: any) => ({ name: l.name, lawyer_id: l.lawyer_id })) || []
    );

    // Multiple Clients (Müvekkil, Müdahil, etc.)
    const [clients, setClients] = useState<Array<{ name: string; role: string; birth_year?: number; gender?: string }>>(
        editModeCase?.parties?.filter((p: EditModeParty) => p.party_type === "CLIENT").map((p: EditModeParty) => ({ name: p.name, role: p.role, birth_year: p.birth_year, gender: p.gender })) ||
        [{ name: "", role: "Davacı" }]
    );

    // Multiple Counter-Parties (Karşı Taraf)
    const [counterParties, setCounterParties] = useState<Array<{ name: string; role: string }>>(
        editModeCase?.parties?.filter((p: EditModeParty) => p.party_type === "COUNTER").map((p: EditModeParty) => ({ name: p.name, role: p.role })) ||
        [{ name: "", role: "Davalı" }]
    );

    // Third Parties (Tanık, Bilirkişi, etc.)
    const [thirdParties, setThirdParties] = useState<Array<{ name: string; role: string }>>(
        editModeCase?.parties?.filter((p: EditModeParty) => p.party_type === "THIRD").map((p: EditModeParty) => ({ name: p.name, role: p.role })) ||
        []
    );
    // Open/Close states for client comboboxes
    const [clientComboboxesOpen, setClientComboboxesOpen] = useState<boolean[]>([]);

    // Combobox state for searchable subject dropdown
    const [subjectComboboxOpen, setSubjectComboboxOpen] = useState(false);

    // Approval Ticks State
    const [approvedFields, setApprovedFields] = useState({
        court: false,
        clients: [] as boolean[],
        counterParties: [] as boolean[],
        thirdParties: [] as boolean[]
    });

    // Animation States
    const [isShaking, setIsShaking] = useState(false);
    const triggerShake = () => {
        setIsShaking(true);
        setTimeout(() => setIsShaking(false), 400);
    };

    useEffect(() => {
        setApprovedFields({
            court: false,
            clients: new Array(clients.length).fill(false),
            counterParties: new Array(counterParties.length).fill(false),
            thirdParties: new Array(thirdParties.length).fill(false)
        });
    }, [clients.length, counterParties.length, thirdParties.length]);

    const handleFieldApproval = (type: 'court' | 'client' | 'counter' | 'third', idx?: number) => {
        if (type === 'court') {
            setFormData(prev => ({ ...prev, court: toTitleCase(prev.court) }));
            setApprovedFields(prev => ({ ...prev, court: !prev.court }));
        } else if (type === 'client' && idx !== undefined) {
            const updated = [...clients];
            updated[idx].name = toTitleCase(updated[idx].name);
            setClients(updated);
            const newApprovals = [...approvedFields.clients];
            newApprovals[idx] = !newApprovals[idx];
            setApprovedFields(prev => ({ ...prev, clients: newApprovals }));
        } else if (type === 'counter' && idx !== undefined) {
            const updated = [...counterParties];
            updated[idx].name = toTitleCase(updated[idx].name);
            setCounterParties(updated);
            const newApprovals = [...approvedFields.counterParties];
            newApprovals[idx] = !newApprovals[idx];
            setApprovedFields(prev => ({ ...prev, counterParties: newApprovals }));
        } else if (type === 'third' && idx !== undefined) {
            const updated = [...thirdParties];
            updated[idx].name = toTitleCase(updated[idx].name);
            setThirdParties(updated);
            const newApprovals = [...approvedFields.thirdParties];
            newApprovals[idx] = !newApprovals[idx];
            setApprovedFields(prev => ({ ...prev, thirdParties: newApprovals }));
        }
    };


    // Search cases effect
    const { searchCases, getClientCaseSequence } = useCases();
    useEffect(() => {
        const timer = setTimeout(async () => {
            if (searchQuery.length >= 2) {
                setIsSearchingCases(true);
                const results = await searchCases(searchQuery);
                setSearchResults(results || []);
                setIsSearchingCases(false);
            } else {
                setSearchResults([]);
            }
        }, 500);
        return () => clearTimeout(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [searchQuery]);

    // Yardımcı: Hizmet bitmask'ini güncelle (11000 formatı)
    const handleServiceToggle = (index: number, checked: boolean) => {
        const currentMask = formData.serviceType.split("");
        currentMask[index] = checked ? "1" : "0";
        const newMask = currentMask.join("");
        setFormData({ ...formData, serviceType: newMask });
        updateTrackingNumber(undefined, undefined, newMask);
    };

    const getOppositeRole = (role: string) => {
        if (role === "Davacı") return "Davalı";
        if (role === "Davalı") return "Davacı";
        if (role === "Müşteki") return "Sanık";
        if (role === "Sanık") return "Müşteki";
        return role;
    };

    // Yardımcı: Takip Numarasını Güncelle
    const updateTrackingNumber = async (clientInfo?: { category?: string, clientName?: string }, fType?: string, sType?: string) => {
        if (isEditMode) return;

        const cName = clientInfo?.clientName || (clients.length > 0 ? clients[0].name : "");
        let seq = 1;
        if (cName) {
            seq = await getClientCaseSequence(cName);
        }

        const tracking = generateTrackingNumber({
            category: clientInfo?.category !== undefined ? clientInfo.category : formData.category,
            clientName: cName,
            sequence: seq,
            processType: fType || formData.fileType,
            serviceType: sType || formData.serviceType
        });
        setCaseId(tracking);
    };

    const handleSelectCase = async (caseSummary: { id: number }) => {
        const fullCase = await getCase(caseSummary.id);
        if (fullCase) {
            navigate("/new-case", { state: { case: fullCase }, replace: true });
        }
    };

    // Effect to handle incoming case state (for editing)
    useEffect(() => {
        if (editModeCase) {
            setCaseId(editModeCase.tracking_no);
            setCaseStatus(editModeCase.status);
            setCaseHistory(editModeCase.history || []);
            setFormData({
                fileType: editModeCase.file_type || "",
                subType: editModeCase.sub_type || "",
                subject: editModeCase.subject || "",
                court: editModeCase.court || "",
                category: "",
                lawyer: editModeCase.responsible_lawyer_name || "",
                uyapLawyer: editModeCase.uyap_lawyer_name || "",
                esasNo: editModeCase.esas_no || "",
                fileOpeningDate: editModeCase.opening_date || "",
                serviceType: editModeCase.service_type || "00000",
                maddiTazminat: editModeCase.maddi_tazminat?.toString() || "",
                maneviTazminat: editModeCase.manevi_tazminat?.toString() || "",
                acceptanceDate: editModeCase.acceptance_date || "",
                bureauType: editModeCase.bureau_type || "",
                subTypeExtra: editModeCase.sub_type_extra || "",
                judicialUnit: editModeCase.judicial_unit || ""
            });
            setSelectedLawyers(editModeCase.lawyers?.map((l: any) => ({ name: l.name, lawyer_id: l.lawyer_id })) || []);
            setClients(editModeCase.parties?.filter((p: EditModeParty) => p.party_type === "CLIENT").map((p: EditModeParty) => ({ name: p.name, role: p.role, birth_year: p.birth_year, gender: p.gender })) || [{ name: "", role: "Davacı" }]);
            setCounterParties(editModeCase.parties?.filter((p: EditModeParty) => p.party_type === "COUNTER").map((p: EditModeParty) => ({ name: p.name, role: p.role })) || [{ name: "", role: "Davalı" }]);
            setThirdParties(editModeCase.parties?.filter((p: EditModeParty) => p.party_type === "THIRD").map((p: EditModeParty) => ({ name: p.name, role: p.role })) || []);
        }
    }, [editModeCase]);

    // File Upload States
    const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
    const [isAnalyzing, setIsAnalyzing] = useState(false);

    const handleFileSelect = (files: File | File[]) => {
        const newFiles = Array.isArray(files) ? files : [files];
        setSelectedFiles(prev => [...prev, ...newFiles]);
    };

    const handleClearFile = () => {
        setSelectedFiles([]);
    };

    const handleRemoveFile = (index: number) => {
        setSelectedFiles(prev => prev.filter((_, i) => i !== index));
    };

    const handleAnalyzeDocument = () => {
        if (selectedFiles.length === 0) return;

        setIsAnalyzing(true);
        toast.info(`${selectedFiles.length} belge yapay zeka ile analiz ediliyor...`);

        // Simulate AI Analysis
        setTimeout(() => {
            setIsAnalyzing(false);

            // Mock Extracted Data
            setFormData({
                fileType: "Hukuk Dava",
                subType: "Tüketici",
                subject: "Ayıplı Mal - Bedel İadesi",
                court: "Bursa Tüketici Mahkemesi (Tahmini)",
                category: "Genel", // Assuming "Genel" is a valid doctype.name
                lawyer: "İlke Berk", // Assuming "İlke Berk" is a valid lawyer.name
                uyapLawyer: "Av. Mehmet Demir", // Assuming "Av. Mehmet Demir" is a valid lawyer.name
                esasNo: "2024/111", // Extracted from doc
                fileOpeningDate: new Date().toISOString().split('T')[0], // Set to today's date
                serviceType: "00000",
                maddiTazminat: "",
                maneviTazminat: "",
                acceptanceDate: "",
                bureauType: "",
                subTypeExtra: "",
                judicialUnit: ""
            });

            setSelectedLawyers([{ name: "İlke Berk", lawyer_id: null }]);

            // Set clients
            setClients([{ name: "Ahmet Yılmaz", role: "Davacı" }]);

            // Set counter parties
            setCounterParties([{ name: "XYZ İnşaat Ltd. Şti.", role: "Davalı" }]);

            toast.success("Bilgiler belgelerden başarıyla çıkarıldı!", {
                icon: <Sparkles className="w-5 h-5 text-yellow-500" />
            });
        }, 2000);
    };

    // Simulate loading an existing case
    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        if (!searchQuery) return;

        setIsLoading(true);
        toast.info("Dosya aranıyor...");

        setTimeout(() => {
            setIsLoading(false);
            if (searchQuery.includes("123")) {
                toast.success("Dosya bulundu ve yüklendi: 2023/123");
                setCaseId("2023/123");
                // In a real app, we would set form values here
            } else {
                toast.error("Dosya bulunamadı, yeni bir kart oluşturuluyor.");
            }
        }, 1000);
    };

    const handleSubmit = async (e?: React.FormEvent, forceSave = false) => {
        if (e) e.preventDefault();

        // Validate that all people in 'clients' list are actually registered (Case-Insensitive Check)
        const unregistered = clients.filter(c =>
            c.name && !dbClients.some(db => toUpperTR(db.name) === toUpperTR(c.name))
        );
        if (!forceSave && unregistered.length > 0) {
            setPendingUnregistered(unregistered.map(u => ({ name: u.name })));
            setShowClientConfirm(true);
            return;
        }

        setShowClientConfirm(false);
        setPendingUnregistered([]);

        // Prepare data for backend
        const caseData = {
            tracking_no: caseId,
            esas_no: formData.esasNo,
            status: caseStatus,
            file_type: formData.fileType,
            sub_type: formData.subType,
            subject: formData.subject,
            court: formData.court,
            opening_date: formData.fileOpeningDate,
            responsible_lawyer_name: formData.lawyer,
            uyap_lawyer_name: formData.uyapLawyer,
            maddi_tazminat: formData.maddiTazminat ? Number(formData.maddiTazminat) : 0,
            manevi_tazminat: formData.maneviTazminat ? Number(formData.maneviTazminat) : 0,
            acceptance_date: formData.acceptanceDate || undefined,
            bureau_type: formData.bureauType || undefined,
            sub_type_extra: formData.subTypeExtra || undefined,
            parties: [
                ...clients.filter(c => c.name).map(c => ({
                    client_id: dbClients.find(db => toUpperTR(db.name) === toUpperTR(c.name))?.id,
                    name: c.name,
                    role: c.role,
                    party_type: "CLIENT" as const
                })),
                ...counterParties.filter(c => c.name).map(c => ({
                    name: c.name,
                    role: c.role,
                    party_type: "COUNTER" as const
                })),
                ...thirdParties.filter(t => t.name).map(t => ({
                    name: t.name,
                    role: t.role,
                    party_type: "THIRD" as const
                }))
            ],
            lawyers: selectedLawyers
        };

        let success;
        if (isEditMode && editModeCase?.id) {
            success = await updateCase(editModeCase.id, caseData as CaseData);
        } else {
            success = await saveCase(caseData as CaseData);
        }

        if (success) {
            toast.success(isEditMode ? "Dava kartı güncellendi!" : "Dava kartı veritabanına kaydedildi!", {
                description: `Ofis No: ${caseId} bilgileri başarıyla işlendi.`
            });

            if (isEditMode && editModeCase?.id) {
                // Refresh history after save
                const updated = await getCase(editModeCase.id);
                if (updated) setCaseHistory(updated.history || []);
            }
        } else {
            toast.error("Hata", { description: "Dava kartı kaydedilemedi. Sunucu hatası oluştu." });
        }
    };

    const handleDelete = async () => {
        if (!isEditMode || !editModeCase?.id) return;

        const success = await deleteCase(editModeCase.id);
        if (success) {
            toast.success("Silindi", { description: "Dava başarıyla silindi." });
            navigate(-1);
        } else {
            toast.error("Hata", { description: "Silme işlemi başarısız oldu." });
        }
    };

    const handleReset = () => {
        if (isLoading || isAnalyzing) return;

        // Reset main form data
        setFormData({
            fileType: "",
            subType: "",
            subject: "",
            court: "",
            category: "",
            lawyer: "",
            uyapLawyer: "",
            esasNo: "",
            fileOpeningDate: "",
            serviceType: "00000",
            maddiTazminat: "",
            maneviTazminat: "",
            acceptanceDate: "",
            bureauType: "",
            subTypeExtra: "",
            judicialUnit: ""
        });

        // Reset arrays
        setSelectedLawyers([]);
        setClients([{ name: "", role: "Davacı" }]);
        setCounterParties([{ name: "", role: "Davalı" }]);
        setThirdParties([]);

        // Reset files and search
        setSelectedFiles([]);
        setSearchQuery("");
        setCaseStatus("DERDEST");

        // Generate new random ID
        setCaseId(`2024/${Math.floor(Math.random() * 10000).toString().padStart(4, '0')}`);

        toast.info("Form ve yüklenen belgeler temizlendi.");
    };

    return (
        <div className="min-h-screen bg-background">
            <Header />

            <main className="max-w-[1400px] mx-auto px-6 py-8">
                {/* DASHBOARD HEADER */}
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-10">
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
                            {isEditMode ? "Dava Kartı Düzenle" : "Dava Kartı Yönetimi"}
                        </h1>
                        <p className="text-sm text-muted-foreground">
                            {isEditMode ? "Mevcut dosya bilgilerini güncelleyin ve geçmişi takip edin." : "Yeni dava açın veya mevcut dosyaları arayıp eksik bilgileri tamamlayın."}
                        </p>
                    </div>

                    <div className="flex flex-col sm:flex-row items-center gap-4">
                        <div className="relative w-full sm:w-80">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                            <Input
                                placeholder="Ofis No veya Müvekkil Ara..."
                                className="pl-10 bg-muted/20 border-border/50 focus:bg-background transition-all"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                            {searchResults.length > 0 && (
                                <Card className="absolute top-full left-0 right-0 mt-2 z-50 shadow-2xl border-primary/20 bg-background/95 backdrop-blur overflow-hidden">
                                    <div className="max-h-60 overflow-auto py-2">
                                        {searchResults.map((res) => (
                                            <button
                                                key={res.id}
                                                className="w-full text-left px-4 py-2 hover:bg-primary/5 transition-colors flex flex-col border-b border-border/40 last:border-0"
                                                onClick={() => handleSelectCase(res)}
                                            >
                                                <div className="flex justify-between items-center">
                                                    <span className="font-bold text-sm text-primary">{res.tracking_no}</span>
                                                    <span className="text-[10px] bg-primary/10 px-1.5 py-0.5 rounded text-primary font-bold">{res.status}</span>
                                                </div>
                                                <div className="text-xs text-muted-foreground truncate">
                                                    {res.esas_no || '(Esas No Yok)'} - {res.court || '(Mahkeme Yok)'}
                                                </div>
                                            </button>
                                        ))}
                                    </div>
                                </Card>
                            )}
                        </div>

                        <Button
                            className="w-full sm:w-auto font-semibold shadow-md bg-primary hover:bg-primary/90"
                            onClick={() => document.getElementById("case-file-upload")?.click()}
                            disabled={isAnalyzing}
                        >
                            {isAnalyzing ? (
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            ) : (
                                <Upload className="w-4 h-4 mr-2" />
                            )}
                            Belge Yükle {selectedFiles.length > 0 && `(${selectedFiles.length})`}
                        </Button>
                        <input
                            id="case-file-upload"
                            type="file"
                            className="hidden"
                            multiple
                            accept=".pdf,.docx,.udf"
                            onChange={(e) => e.target.files && handleFileSelect(Array.from(e.target.files))}
                        />
                    </div>
                </div>

                {/* FILE UPLOAD & ANALYSIS PREVIEW */}
                {selectedFiles.length > 0 && (
                    <div className="mb-8 animate-in fade-in slide-in-from-top-4 space-y-4">
                        <div className="bg-primary/5 border border-primary/20 rounded-xl p-6">
                            <div className="flex items-center justify-between mb-4">
                                <div>
                                    <h4 className="font-semibold text-lg flex items-center gap-2">
                                        <FileText className="w-5 h-5 text-primary" />
                                        Yüklenen Belgeler ({selectedFiles.length})
                                    </h4>
                                    <p className="text-sm text-muted-foreground">Bu belgeler analiz edilerek dava kartı oluşturulacak.</p>
                                </div>
                                <div className="flex gap-3">
                                    <Button variant="outline" size="sm" onClick={handleClearFile} disabled={isAnalyzing}>Temizle</Button>
                                    <Button onClick={handleAnalyzeDocument} disabled={isAnalyzing}>
                                        {isAnalyzing ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Sparkles className="w-4 h-4 mr-2" />}
                                        Analizi Başlat
                                    </Button>
                                </div>
                            </div>

                            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                                {selectedFiles.map((file, idx) => (
                                    <div key={idx} className="bg-background/50 border border-primary/10 rounded-lg p-3 flex items-center gap-3 relative group">
                                        <div className="bg-primary/20 p-2 rounded">
                                            <FileText className="w-4 h-4 text-primary" />
                                        </div>
                                        <div className="overflow-hidden">
                                            <p className="text-sm font-medium truncate" title={file.name}>{file.name}</p>
                                            <p className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
                                        </div>
                                        <button
                                            onClick={() => handleRemoveFile(idx)}
                                            className="absolute -top-2 -right-2 bg-destructive text-destructive-foreground rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity shadow-sm hover:bg-destructive/90"
                                            type="button"
                                        >
                                            <X className="w-3 h-3" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}


                <form onSubmit={handleSubmit}>
                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                        {/* LEFT COLUMN: PRIMARY INFO */}
                        <div className="lg:col-span-8 space-y-8">
                            <Card className="glass-card shadow-lg border-muted/40 overflow-hidden">
                                <div className="bg-muted/5 border-b border-border/40 p-6">
                                    <h3 className="text-sm font-bold flex items-center gap-2 text-primary uppercase tracking-widest">
                                        <User className="w-4 h-4" /> 1. Taraf Bilgileri
                                    </h3>
                                </div>
                                <CardContent className="p-8 space-y-10">
                                    {/* Müvekkil Section */}
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between border-b border-border/50 pb-2">
                                            <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                <div className="w-1 h-3 bg-primary" />
                                                Müvekkil Tarafı
                                            </Label>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => setClients([...clients, { name: "", role: "Müdahil" }])}
                                                className="h-7 text-xs gap-1 text-primary hover:text-primary hover:bg-primary/5"
                                            >
                                                <Plus className="w-3 h-3" /> Ekle
                                            </Button>
                                        </div>

                                        <div className="grid gap-3">
                                            {clients.map((client, index) => (
                                                <div key={index} className="flex gap-3 items-start animate-in fade-in slide-in-from-top-1 duration-200">
                                                    <div className="flex-1">
                                                        <Popover
                                                            open={clientComboboxesOpen[index]}
                                                            onOpenChange={(open) => {
                                                                const newOpen = [...clientComboboxesOpen];
                                                                newOpen[index] = open;
                                                                setClientComboboxesOpen(newOpen);
                                                            }}
                                                        >
                                                            <PopoverTrigger asChild>
                                                                <Button
                                                                    variant="outline"
                                                                    role="combobox"
                                                                    aria-expanded={clientComboboxesOpen[index]}
                                                                    className="w-full justify-between text-left font-normal bg-transparent border-border/60 h-9 px-3 text-sm shadow-none hover:bg-transparent hover:text-foreground"
                                                                >
                                                                    <div className={cn("flex-1 truncate text-left", !client.name && "text-muted-foreground")}>
                                                                        {client.name ? toTitleCase(client.name) : "Müvekkil Seçiniz..."}
                                                                    </div>
                                                                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-20" />
                                                                </Button>
                                                            </PopoverTrigger>
                                                            <PopoverContent className="w-[400px] p-0" align="start">
                                                                <Command>
                                                                    <CommandInput
                                                                        placeholder="Müvekkil ara..."
                                                                        value={clientSearchValues[index] || ""}
                                                                        onValueChange={(val) => {
                                                                            setClientSearchValues(prev => ({ ...prev, [index]: val }));
                                                                        }}
                                                                    />
                                                                    <CommandEmpty>
                                                                        <div className="p-4 text-center">
                                                                            <p className="text-sm text-muted-foreground mb-3">Müvekkil bulunamadı. <br /><strong>"{clientSearchValues[index]}"</strong> ismini kullanmak ister misiniz?</p>
                                                                            <Button
                                                                                size="sm"
                                                                                className="w-full bg-primary/20 text-primary hover:bg-primary/30 mt-2 border-primary/30"
                                                                                type="button"
                                                                                onClick={() => {
                                                                                    const val = clientSearchValues[index] || "";
                                                                                    if (!val.trim()) return;
                                                                                    const updated = [...clients];
                                                                                    updated[index].name = toTitleCase(val.trim());
                                                                                    setClients(updated);

                                                                                    if (index === 0) {
                                                                                        updateTrackingNumber({ clientName: val.trim() });
                                                                                    }

                                                                                    const newOpen = [...clientComboboxesOpen];
                                                                                    newOpen[index] = false;
                                                                                    setClientComboboxesOpen(newOpen);
                                                                                }}
                                                                            >
                                                                                <Plus className="w-4 h-4 mr-2" /> Hızlı Müvekkil Ekle
                                                                            </Button>
                                                                        </div>
                                                                    </CommandEmpty>
                                                                    <CommandGroup className="max-h-64 overflow-auto">
                                                                        {dbClients.map((dbClient) => (
                                                                            <CommandItem
                                                                                key={dbClient.id}
                                                                                value={`${dbClient.name} ${dbClient.cari_kod || ""} ${dbClient.tc_no || ""}`}
                                                                                onSelect={() => {
                                                                                    const updated = [...clients];
                                                                                    updated[index].name = toTitleCase(dbClient.name);
                                                                                    setClients(updated);

                                                                                    // Yeni protokol uyarınca takip nosunu güncelle
                                                                                    if (index === 0) {
                                                                                        updateTrackingNumber({
                                                                                            category: dbClient.category,
                                                                                            clientName: dbClient.name
                                                                                        });
                                                                                    }

                                                                                    const newOpen = [...clientComboboxesOpen];
                                                                                    newOpen[index] = false;
                                                                                    setClientComboboxesOpen(newOpen);
                                                                                }}
                                                                            >
                                                                                <Check
                                                                                    className={`mr-2 h-4 w-4 ${client.name === dbClient.name ? "opacity-100" : "opacity-0"}`}
                                                                                />
                                                                                <div className="flex flex-col">
                                                                                    <div className="flex items-center gap-2">
                                                                                        <span>{toTitleCase(dbClient.name)}</span>
                                                                                        {dbClient.cari_kod && (
                                                                                            <span className="text-[9px] bg-primary/10 text-primary px-1 rounded font-bold">
                                                                                                {dbClient.cari_kod}
                                                                                            </span>
                                                                                        )}
                                                                                    </div>
                                                                                    {dbClient.tc_no && <span className="text-[10px] text-muted-foreground">{dbClient.tc_no}</span>}
                                                                                </div>
                                                                            </CommandItem>
                                                                        ))}
                                                                    </CommandGroup>
                                                                </Command>
                                                            </PopoverContent>
                                                        </Popover>
                                                    </div>
                                                    <Checkbox
                                                        checked={approvedFields.clients[index]}
                                                        onCheckedChange={() => handleFieldApproval('client', index)}
                                                        className={cn("mt-2.5", approvedFields.clients[index] && "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success")}
                                                    />
                                                    <div className="w-40">
                                                        <Select
                                                            value={client.role}
                                                            onValueChange={(v) => {
                                                                const updated = [...clients];
                                                                updated[index].role = v;
                                                                setClients(updated);

                                                                // İlk müvekkil ise karşı tarafın rolünü otomatik ayarla
                                                                if (index === 0 && counterParties.length > 0) {
                                                                    const matched = [...counterParties];
                                                                    matched[0].role = getOppositeRole(v);
                                                                    setCounterParties(matched);
                                                                }
                                                            }}
                                                        >
                                                            <SelectTrigger className="h-9 bg-transparent border-border/60">
                                                                <SelectValue />
                                                            </SelectTrigger>
                                                            <SelectContent>
                                                                {TARAF_ROLLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                                            </SelectContent>
                                                        </Select>
                                                    </div>
                                                    {index > 0 && (
                                                        <Button
                                                            type="button"
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-9 w-9 text-muted-foreground hover:text-destructive hover:bg-destructive/5"
                                                            onClick={() => setClients(clients.filter((_, i) => i !== index))}
                                                        >
                                                            <X className="w-4 h-4" />
                                                        </Button>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Karşı Taraf Section */}
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between border-b border-border/50 pb-2">
                                            <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                <div className="w-1 h-3 bg-primary" />
                                                Karşı Taraf Bilgileri
                                            </Label>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => setCounterParties([...counterParties, { name: "", role: "Davalı" }])}
                                                className="h-7 text-xs gap-1 text-primary hover:text-primary hover:bg-primary/5"
                                            >
                                                <Plus className="w-3 h-3" /> Ekle
                                            </Button>
                                        </div>

                                        <div className="grid gap-3">
                                            {counterParties.map((party, index) => (
                                                <div key={index} className="flex gap-3 items-start animate-in fade-in slide-in-from-top-1 duration-200">
                                                    <div className="flex-1">
                                                        <Input
                                                            placeholder="Karşı Taraf Adı / Ünvanı"
                                                            value={party.name}
                                                            onChange={(e) => {
                                                                const updated = [...counterParties];
                                                                updated[index].name = e.target.value;
                                                                setCounterParties(updated);
                                                            }}
                                                            onBlur={(e) => {
                                                                const updated = [...counterParties];
                                                                updated[index].name = toTitleCase(e.target.value);
                                                                setCounterParties(updated);
                                                            }}
                                                            className="h-9 text-sm bg-transparent border-border/60 focus:border-primary/50 text-left"
                                                        />
                                                    </div>
                                                    <Checkbox
                                                        checked={approvedFields.counterParties[index]}
                                                        onCheckedChange={() => handleFieldApproval('counter', index)}
                                                        className={cn("mt-2.5", approvedFields.counterParties[index] && "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success")}
                                                    />
                                                    <div className="w-40">
                                                        <Select
                                                            value={party.role}
                                                            onValueChange={(v) => {
                                                                const updated = [...counterParties];
                                                                updated[index].role = v;
                                                                setCounterParties(updated);

                                                                // İlk karşı taraf ise müvekkilin rolünü otomatik ayarla
                                                                if (index === 0 && clients.length > 0) {
                                                                    const matched = [...clients];
                                                                    matched[0].role = getOppositeRole(v);
                                                                    setClients(matched);
                                                                }
                                                            }}
                                                        >
                                                            <SelectTrigger className="h-9 bg-transparent border-border/60">
                                                                <SelectValue />
                                                            </SelectTrigger>
                                                            <SelectContent>
                                                                {TARAF_ROLLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                                            </SelectContent>
                                                        </Select>
                                                    </div>
                                                    {index > 0 && (
                                                        <Button
                                                            type="button"
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-9 w-9 text-muted-foreground hover:text-destructive hover:bg-destructive/5"
                                                            onClick={() => setCounterParties(counterParties.filter((_, i) => i !== index))}
                                                        >
                                                            <X className="w-4 h-4" />
                                                        </Button>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Üçüncü Taraflar Section */}
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between border-b border-border/50 pb-2">
                                            <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                <div className="w-1 h-3 bg-primary" />
                                                Üçüncü Taraflar
                                            </Label>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="sm"
                                                className="h-7 text-xs gap-1 text-primary hover:text-primary hover:bg-primary/5"
                                                onClick={() => setThirdParties([...thirdParties, { name: "", role: "Tanık" }])}
                                            >
                                                <Plus className="w-3 h-3" /> Ekle
                                            </Button>
                                        </div>

                                        {thirdParties.length === 0 ? (
                                            <div className="text-[11px] text-muted-foreground italic py-1 px-1">
                                                Kayıtlı tanık veya bilirkişi bulunmuyor.
                                            </div>
                                        ) : (
                                            <div className="grid gap-2">
                                                {thirdParties.map((party, index) => (
                                                    <div key={index} className="flex gap-2 items-start animate-in fade-in slide-in-from-top-1 duration-200">
                                                        <div className="flex-1">
                                                            <Input
                                                                placeholder="İsim / Ünvan"
                                                                value={party.name}
                                                                onChange={(e) => {
                                                                    const updated = [...thirdParties];
                                                                    updated[index].name = e.target.value;
                                                                    setThirdParties(updated);
                                                                }}
                                                                onBlur={(e) => {
                                                                    const updated = [...thirdParties];
                                                                    updated[index].name = toTitleCase(e.target.value);
                                                                    setThirdParties(updated);
                                                                }}
                                                                className="h-9 text-sm bg-transparent border-border/40 focus:border-primary/40 text-left"
                                                            />
                                                        </div>
                                                        <Checkbox
                                                            checked={approvedFields.thirdParties[index]}
                                                            onCheckedChange={() => handleFieldApproval('third', index)}
                                                            className={cn("mt-2", approvedFields.thirdParties[index] && "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success")}
                                                        />
                                                        <div className="w-32">
                                                            <Select
                                                                value={party.role}
                                                                onValueChange={(v) => {
                                                                    const updated = [...thirdParties];
                                                                    updated[index].role = v;
                                                                    setThirdParties(updated);
                                                                }}
                                                            >
                                                                <SelectTrigger className="h-8 text-xs bg-transparent border-border/40">
                                                                    <SelectValue />
                                                                </SelectTrigger>
                                                                <SelectContent>
                                                                    {UCUNCU_TARAF_ROLLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                                                </SelectContent>
                                                            </Select>
                                                        </div>
                                                        <Button
                                                            type="button"
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/5"
                                                            onClick={() => setThirdParties(thirdParties.filter((_, i) => i !== index))}
                                                        >
                                                            <X className="w-3 h-3" />
                                                        </Button>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>

                            <Card className="glass-card shadow-lg border-muted/40 overflow-hidden">
                                <div className="bg-muted/5 border-b border-border/40 p-6">
                                    <h3 className="text-sm font-bold flex items-center gap-2 text-primary uppercase tracking-widest">
                                        <Gavel className="w-4 h-4" /> 2. Dava Bilgileri
                                    </h3>
                                </div>
                                <CardContent className="p-8 space-y-6">
                                    <div className="grid md:grid-cols-2 gap-x-8 gap-y-6">
                                        <div className="space-y-2 md:col-span-2">
                                            <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                <Building className="w-3 h-3" /> Mahkeme Bilgisi
                                            </Label>
                                            <div className="relative flex items-center gap-2">
                                                <Input
                                                    placeholder="Örn: Bursa 13. Tüketici Mahkemesi"
                                                    value={formData.court}
                                                    onChange={(e) => setFormData({ ...formData, court: e.target.value })}
                                                    className="text-base bg-transparent border-border/60 flex-1"
                                                />
                                                <Checkbox
                                                    checked={approvedFields.court}
                                                    onCheckedChange={() => handleFieldApproval('court')}
                                                    className={approvedFields.court ? "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success" : ""}
                                                />
                                            </div>
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                <FileText className="w-3 h-3" /> Esas No
                                            </Label>
                                            <Input
                                                placeholder="2024/123"
                                                value={formData.esasNo}
                                                onChange={(e) => setFormData({ ...formData, esasNo: e.target.value })}
                                                className="font-mono bg-transparent border-border/60"
                                            />
                                        </div>


                                        <div 
                                            className={cn(
                                                "grid grid-cols-2 gap-4 md:col-span-1 transition-all duration-300",
                                                isShaking && "animate-crazy-shake"
                                            )}
                                        >
                                            <div className="space-y-2">
                                                <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                    <Briefcase className="w-3 h-3" /> Yargı Türü
                                                </Label>
                                                <Select
                                                    value={formData.fileType}
                                                    onValueChange={(v) => {
                                                        setFormData({ ...formData, fileType: v, subType: "", judicialUnit: "" });
                                                        updateTrackingNumber(undefined, v);
                                                        triggerShake();
                                                    }}
                                                >
                                                    <SelectTrigger 
                                                        className="bg-transparent border-border/60 hover:border-primary/50 transition-colors"
                                                        onClick={() => triggerShake()}
                                                    >
                                                        <SelectValue placeholder="Seçiniz..." />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {DOSYA_TURLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                                    </SelectContent>
                                                </Select>
                                            </div>

                                            <div className="space-y-2">
                                                <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                    <Gavel className="w-3 h-3" /> Yargı Birimi
                                                </Label>
                                                <Select
                                                    value={formData.judicialUnit}
                                                    onValueChange={(v) => {
                                                        setFormData({ ...formData, judicialUnit: v });
                                                        triggerShake();
                                                    }}
                                                    disabled={!formData.fileType}
                                                >
                                                    <SelectTrigger 
                                                        className="bg-transparent border-border/60 overflow-hidden hover:border-primary/50 transition-colors"
                                                        onClick={() => triggerShake()}
                                                    >
                                                        <SelectValue placeholder={formData.fileType ? "Birim Seç..." : "Tür Seçin"} />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {(ALT_TURLER[formData.fileType] || []).map(t => (
                                                            <SelectItem key={t} value={t}>{t}</SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                <Scale className="w-3 h-3" /> Alt Tür (Yargı Türü Alt Kırılımı)
                                            </Label>
                                            <Popover>
                                                <PopoverTrigger asChild>
                                                    <Button
                                                        variant="outline"
                                                        role="combobox"
                                                        className={`w-full justify-between h-9 text-xs border-border/60 ${!formData.subType ? "text-muted-foreground bg-transparent" : "bg-transparent text-foreground"}`}
                                                    >
                                                        {formData.subType ? toTitleCase(formData.subType) : "Seçiniz..."}
                                                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                                    </Button>
                                                </PopoverTrigger>
                                                <PopoverContent className="w-full p-0 max-h-64" align="start">
                                                    <Command>
                                                        <CommandInput placeholder="Alt tür ara..." />
                                                        <CommandEmpty>Kayıt bulunamadı.</CommandEmpty>
                                                        <CommandGroup className="overflow-auto max-h-56">
                                                            {specialties.map((s) => (
                                                                <CommandItem
                                                                    key={s.code}
                                                                    value={s.name ?? ""}
                                                                    onSelect={(currentValue) => {
                                                                        setFormData({ ...formData, subType: currentValue === formData.subType ? "" : currentValue });
                                                                    }}
                                                                >
                                                                    <Check className={`mr-2 h-4 w-4 ${formData.subType === s.name ? "opacity-100" : "opacity-0"}`} />
                                                                    {toTitleCase(s.name ?? "")}
                                                                </CommandItem>
                                                            ))}
                                                        </CommandGroup>
                                                    </Command>
                                                </PopoverContent>
                                            </Popover>
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                <FileText className="w-3 h-3" /> Ek Alt Kırılım
                                            </Label>
                                            <Popover>
                                                <PopoverTrigger asChild>
                                                    <Button
                                                        variant="outline"
                                                        role="combobox"
                                                        className={`w-full justify-between h-9 text-xs border-border/60 ${!formData.subTypeExtra ? "text-muted-foreground bg-transparent" : "bg-transparent text-foreground"}`}
                                                    >
                                                        {formData.subTypeExtra ? toTitleCase(formData.subTypeExtra) : "Seçiniz..."}
                                                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                                    </Button>
                                                </PopoverTrigger>
                                                <PopoverContent className="w-full p-0 max-h-64" align="start">
                                                    <Command>
                                                        <CommandInput placeholder="Ek alt kırılım ara..." />
                                                        <CommandEmpty>Kayıt bulunamadı.</CommandEmpty>
                                                        <CommandGroup className="overflow-auto max-h-56">
                                                            {specialties.map((s) => (
                                                                <CommandItem
                                                                    key={s.code}
                                                                    value={s.name ?? ""}
                                                                    onSelect={(currentValue) => {
                                                                        setFormData({ ...formData, subTypeExtra: currentValue === formData.subTypeExtra ? "" : currentValue });
                                                                    }}
                                                                >
                                                                    <Check className={`mr-2 h-4 w-4 ${formData.subTypeExtra === s.name ? "opacity-100" : "opacity-0"}`} />
                                                                    {toTitleCase(s.name ?? "")}
                                                                </CommandItem>
                                                            ))}
                                                        </CommandGroup>
                                                    </Command>
                                                </PopoverContent>
                                            </Popover>
                                        </div>

                                        <div className="space-y-4 md:col-span-2">
                                            <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                <Briefcase className="w-3 h-3" /> Hizmet Türü (Çoklu Seçim)
                                            </Label>
                                            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 p-4 bg-muted/5 border border-border/40 rounded-lg">
                                                {HIZMET_TURLERI.map((t) => (
                                                    <div key={t.index} className="flex items-center space-x-2">
                                                        <Checkbox
                                                            id={`service-${t.index}`}
                                                            checked={formData.serviceType[t.index] === "1"}
                                                            onCheckedChange={(checked) => handleServiceToggle(t.index, !!checked)}
                                                        />
                                                        <Label
                                                            htmlFor={`service-${t.index}`}
                                                            className="text-sm font-medium leading-none cursor-pointer"
                                                        >
                                                            {t.label}
                                                        </Label>
                                                    </div>
                                                ))}
                                            </div>
                                            <p className="text-[10px] text-muted-foreground italic">
                                                Seçilen her hizmet dosya numarasının son bloğuna (11000 gibi) eklenir.
                                            </p>
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                <Calendar className="w-3 h-3" /> Dosya Açılış Tarihi
                                            </Label>
                                            <Input
                                                type="date"
                                                value={formData.fileOpeningDate}
                                                onChange={(e) => setFormData({ ...formData, fileOpeningDate: e.target.value })}
                                                className="bg-transparent border-border/60"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                <Calendar className="w-3 h-3" /> İş Kabul Tarihi
                                            </Label>
                                            <Input
                                                type="date"
                                                value={formData.acceptanceDate}
                                                onChange={(e) => setFormData({ ...formData, acceptanceDate: e.target.value })}
                                                className="bg-transparent border-border/60"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                                <Sparkles className="w-3 h-3" /> Davanın Konusu
                                            </Label>
                                            <Popover open={subjectComboboxOpen} onOpenChange={setSubjectComboboxOpen}>
                                                <PopoverTrigger asChild>
                                                    <Button
                                                        variant="outline"
                                                        role="combobox"
                                                        aria-expanded={subjectComboboxOpen}
                                                        className="w-full justify-between font-normal bg-transparent border-border/60"
                                                    >
                                                        {formData.subject || "Seçiniz..."}
                                                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                                    </Button>
                                                </PopoverTrigger>
                                                <PopoverContent className="w-[400px] p-0" align="start">
                                                    <Command>
                                                        <CommandInput placeholder="Dava konusu ara..." />
                                                        <CommandEmpty>Sonuç bulunamadı.</CommandEmpty>
                                                        <CommandGroup className="max-h-64 overflow-auto">
                                                            {[...caseSubjects].sort((a, b) => {
                                                                const specificSubjects = ["Rücuen Alacak (Tıbbi Kötü Uygulama)", "Tazminat (Tıbbi Kötü Uygulama)"];
                                                                const indexA = specificSubjects.indexOf(a.name);
                                                                const indexB = specificSubjects.indexOf(b.name);
                                                                if (indexA !== -1 && indexB !== -1) return indexA - indexB;
                                                                if (indexA !== -1) return -1;
                                                                if (indexB !== -1) return 1;
                                                                return 0; // Maintain original order for others
                                                            }).map((subject) => (
                                                                <CommandItem
                                                                    key={subject.code}
                                                                    value={subject.name}
                                                                    onSelect={(currentValue) => {
                                                                        setFormData({ ...formData, subject: currentValue === formData.subject ? "" : currentValue });
                                                                        setSubjectComboboxOpen(false);
                                                                    }}
                                                                >
                                                                    <Check
                                                                        className={`mr-2 h-4 w-4 ${formData.subject === subject.name ? "opacity-100" : "opacity-0"}`}
                                                                    />
                                                                    {subject.name}
                                                                </CommandItem>
                                                            ))}
                                                        </CommandGroup>
                                                    </Command>
                                                </PopoverContent>
                                            </Popover>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </div>

                        {/* RIGHT COLUMN: SUMMARY & SIDEBAR ACTIONS */}
                        <div className="lg:col-span-4 space-y-8 lg:sticky lg:top-8">
                            {/* CASE BADGE CARD */}
                            <Card className={`glass-card border-l-4 p-6 
                                ${caseStatus === 'DERDEST' ? 'border-primary/20 bg-primary/5 border-l-primary' :
                                    caseStatus === 'DANIŞ' ? 'border-blue-500/20 bg-blue-500/5 border-l-blue-500' :
                                        'border-muted/40 bg-muted/5 border-l-muted-foreground'}`}>
                                <div className="flex items-center justify-between mb-2">
                                    <span className={`text-[10px] font-bold uppercase tracking-widest 
                                        ${caseStatus === 'DERDEST' ? 'text-primary' :
                                            caseStatus === 'DANIŞ' ? 'text-blue-500' :
                                                'text-muted-foreground'}`}>Ofis No</span>
                                    <Select value={caseStatus} onValueChange={setCaseStatus}>
                                        <SelectTrigger className={`w-fit h-6 text-[10px] font-bold border-0 px-2 gap-1 rounded-md transition-colors focus:ring-0 focus:ring-offset-0 
                                            ${caseStatus === 'DERDEST' ? 'bg-primary/20 text-primary hover:bg-primary/30' :
                                                caseStatus === 'DANIŞ' ? 'bg-blue-500/20 text-blue-500 hover:bg-blue-500/30' :
                                                    'bg-muted text-muted-foreground hover:bg-muted/80'}`}>
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="DANIŞ" className="text-blue-500 font-medium">DANIŞ</SelectItem>
                                            <SelectItem value="DERDEST" className="text-primary font-medium">DERDEST</SelectItem>
                                            <SelectItem value="MAHZEN" className="text-muted-foreground font-medium">MAHZEN</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="text-lg sm:text-xl md:text-2xl font-mono font-bold break-words leading-tight">
                                    {caseId.split('.').map((part, i, arr) => (
                                        <span key={i} className="whitespace-nowrap">
                                            {part}
                                            {i < arr.length - 1 && '.\u200B'}
                                        </span>
                                    ))}
                                </div>
                                <p className="text-xs text-muted-foreground mt-2 italic">
                                    Sistem tarafından otomatik atanan takip numarasıdır.
                                </p>
                            </Card>

                            {/* RESPONSIBLE INFO */}
                            <Card className="glass-card border-border/40 overflow-hidden">
                                <div className="bg-muted/5 border-b border-border/40 p-4">
                                    <h3 className="text-xs font-bold flex items-center gap-2 text-primary uppercase tracking-widest">
                                        <Briefcase className="w-3 h-3" /> Sorumlu Bilgileri
                                    </h3>
                                </div>
                                <div className="p-5 space-y-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Sorumlu Avukat(lar)</Label>

                                        {selectedLawyers.length > 0 && (
                                            <div className="flex flex-wrap gap-2 mb-2">
                                                {selectedLawyers.map((sl, idx) => (
                                                    <div key={idx} className="flex items-center gap-1 bg-primary/10 text-primary px-2 py-1 rounded text-[11px] font-medium border border-primary/20 shadow-sm">
                                                        {sl.name}
                                                        <button
                                                            type="button"
                                                            onClick={(e) => { e.preventDefault(); setSelectedLawyers(prev => prev.filter((_, i) => i !== idx)); }}
                                                            className="hover:bg-primary/20 rounded-full p-0.5 transition-colors"
                                                        >
                                                            <X className="w-3 h-3" />
                                                        </button>
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        <Select onValueChange={(v) => {
                                            if (v && !selectedLawyers.find(l => l.name === v)) {
                                                const lawyerObj = lawyers.find((l: any) => l.name === v);
                                                setSelectedLawyers(prev => [...prev, { name: v, lawyer_id: lawyerObj ? lawyerObj.id : null }]);
                                            }
                                        }}>
                                            <SelectTrigger className="h-8 text-xs bg-transparent border-border/60">
                                                <SelectValue placeholder="Avukat Ekle..." />
                                            </SelectTrigger>
                                            <SelectContent className="max-h-64">
                                                {lawyers.map((t: any) => <SelectItem key={t.code || t.name} value={t.name}>{t.name}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">UYAP Avukat</Label>
                                        <Select value={formData.uyapLawyer} onValueChange={(v) => setFormData({ ...formData, uyapLawyer: v })}>
                                            <SelectTrigger className="h-8 text-xs bg-transparent border-border/60">
                                                <SelectValue placeholder="Seçiniz..." />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {lawyers.map(t => <SelectItem key={t.code} value={t.name}>{t.name}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </Card>

                            {/* BÜRO ÖZEL TÜRÜ */}
                            <Card className="glass-card border-border/40 overflow-hidden">
                                <div className="bg-muted/5 border-b border-border/40 p-4">
                                    <h3 className="text-xs font-bold flex items-center gap-2 text-primary uppercase tracking-widest">
                                        <Building className="w-3 h-3" /> Büro Özel Türü
                                    </h3>
                                </div>
                                <div className="p-5 space-y-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Tür Seçiniz</Label>
                                        <Select value={formData.bureauType} onValueChange={(v) => setFormData({ ...formData, bureauType: v })}>
                                            <SelectTrigger className="h-8 text-xs bg-transparent border-border/60">
                                                <SelectValue placeholder="Seçiniz..." />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {BURO_OZEL_TURU.map(t => <SelectItem key={t} value={t}>{toTitleCase(t)}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </Card>

                            {/* COMPENSATION CLAIMS */}
                            <Card className="glass-card border-border/40 overflow-hidden">
                                <div className="bg-muted/5 border-b border-border/40 p-4">
                                    <h3 className="text-xs font-bold flex items-center gap-2 text-primary uppercase tracking-widest">
                                        <Banknote className="w-3 h-3" /> Tazminat Talepleri
                                    </h3>
                                </div>
                                <div className="p-5 space-y-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                                            <Coins className="w-3 h-3" /> Maddi Tazminat
                                        </Label>
                                        <div className="relative">
                                            <Input
                                                type="text"
                                                placeholder="0,00"
                                                value={formData.maddiTazminat ? Number(formData.maddiTazminat).toLocaleString('tr-TR') : ''}
                                                onChange={(e) => {
                                                    const value = e.target.value.replace(/[^0-9]/g, '');
                                                    setFormData({ ...formData, maddiTazminat: value });
                                                }}
                                                className="h-9 text-base font-mono pr-10 bg-transparent border-border/60"
                                            />
                                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground font-bold font-mono">TL</span>
                                        </div>
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                                            <Heart className="w-3 h-3" /> Manevi Tazminat
                                        </Label>
                                        <div className="relative">
                                            <Input
                                                type="text"
                                                placeholder="0,00"
                                                value={formData.maneviTazminat ? Number(formData.maneviTazminat).toLocaleString('tr-TR') : ''}
                                                onChange={(e) => {
                                                    const value = e.target.value.replace(/[^0-9]/g, '');
                                                    setFormData({ ...formData, maneviTazminat: value });
                                                }}
                                                className="h-9 text-base font-mono pr-10 bg-transparent border-border/60"
                                            />
                                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground font-bold font-mono">TL</span>
                                        </div>
                                    </div>
                                </div>
                            </Card>

                            {/* GLOBAL ACTIONS */}
                            <div className="space-y-3 pt-4">
                                <Button type="submit" size="lg" className="w-full text-base font-semibold shadow-xl h-12" disabled={isLoading || isSaving}>
                                    {isSaving || isLoading ? (
                                        <>
                                            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                                            İşleniyor...
                                        </>
                                    ) : (
                                        <>
                                            <Save className="mr-2 h-5 w-5" />
                                            {isEditMode ? "Değişiklikleri Kaydet" : "Dava Kartını Kaydet"}
                                        </>
                                    )}
                                </Button>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="lg"
                                    className="w-full h-12 border-border/60"
                                    onClick={isEditMode ? () => navigate(-1) : handleReset}
                                    disabled={isLoading || isSaving}
                                >
                                    {isEditMode ? "Geri Dön" : "Vazgeç"}
                                </Button>

                                {isEditMode && (
                                    <AlertDialog>
                                        <AlertDialogTrigger asChild>
                                            <Button variant="destructive" size="lg" type="button" className="w-full h-12 mt-4 gap-2">
                                                <Trash2 className="w-5 h-5" />
                                                Bu Davayı Sil
                                            </Button>
                                        </AlertDialogTrigger>
                                        <AlertDialogContent>
                                            <AlertDialogHeader>
                                                <AlertDialogTitle>Davayı silmek istediğinize emin misiniz?</AlertDialogTitle>
                                                <AlertDialogDescription>
                                                    Bu işlem geri alınamaz. İlgili dava ve tüm geçmiş kayıtları sistemden kalıcı olarak silinecektir.
                                                </AlertDialogDescription>
                                            </AlertDialogHeader>
                                            <AlertDialogFooter>
                                                <AlertDialogCancel>İptal</AlertDialogCancel>
                                                <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Sil</AlertDialogAction>
                                            </AlertDialogFooter>
                                        </AlertDialogContent>
                                    </AlertDialog>
                                )}
                            </div>

                            {/* HISTORY SECTION (Only in Edit Mode) */}
                            {isEditMode && caseHistory.length > 0 && (
                                <Card className="glass-card border-border/40 overflow-hidden">
                                    <div className="bg-muted/5 border-b border-border/40 p-4">
                                        <h3 className="text-xs font-bold flex items-center gap-2 text-primary uppercase tracking-widest">
                                            <RefreshCw className="w-3 h-3" /> Değişiklik Geçmişi
                                        </h3>
                                    </div>
                                    <div className="p-4 max-h-[400px] overflow-auto">
                                        <div className="space-y-4">
                                            {caseHistory.map((h, i) => (
                                                <div key={i} className="text-xs border-l-2 border-primary/20 pl-3 py-1">
                                                    <div className="flex justify-between items-center mb-1">
                                                        <span className="font-bold text-primary">
                                                            {h.field === 'esas_no' ? 'Esas No Değişti' :
                                                                h.field === 'court' ? 'Mahkeme Değişti' :
                                                                    h.field === 'status' ? 'Durum Değişti' : h.field}
                                                        </span>
                                                        <span className="text-[10px] text-muted-foreground">
                                                            {new Date(h.date).toLocaleDateString('tr-TR')} {new Date(h.date).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}
                                                        </span>
                                                    </div>
                                                    <p className="text-muted-foreground line-through opacity-50">{h.old || '(Boş)'}</p>
                                                    <p className="font-medium">➔ {h.new}</p>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </Card>
                            )}
                        </div>
                    </div>
                </form>
                {/* Yeni Müvekkil Onay Modalı */}
                <AlertDialog open={showClientConfirm} onOpenChange={setShowClientConfirm}>
                    <AlertDialogContent>
                        <AlertDialogHeader>
                            <AlertDialogTitle>Yeni Müvekkil Kaydedilecek</AlertDialogTitle>
                            <AlertDialogDescription>
                                <strong>{pendingUnregistered.map(u => u.name).join(", ")}</strong> isimli müvekkiller sistemde bulunamadı. Dava oluşturulurken bu kişiler otomatik olarak sisteme yeni müvekkil olarak kaydedilecektir. Onaylıyor musunuz?
                            </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                            <AlertDialogCancel onClick={() => setShowClientConfirm(false)}>Vazgeç</AlertDialogCancel>
                            <AlertDialogAction onClick={() => handleSubmit(undefined, true)}>
                                Evet, Kaydet ve Davayı Aç
                            </AlertDialogAction>
                        </AlertDialogFooter>
                    </AlertDialogContent>
                </AlertDialog>
            </main>
        </div >
    );
};

export default NewCase;
