import { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Header } from "@/components/Header";
import { useConfig, ConfigItem } from "@/hooks/useConfig";
import { useAuthRequest } from "@/hooks/useAuthRequest";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Plus, Trash2, Edit2, Loader2, GripVertical } from "lucide-react";
import { toast } from "sonner";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";

// DnD Kit Imports
import {
    DndContext,
    closestCenter,
    KeyboardSensor,
    PointerSensor,
    useSensor,
    useSensors,
    DragEndEvent
} from '@dnd-kit/core';
import {
    arrayMove,
    SortableContext,
    sortableKeyboardCoordinates,
    verticalListSortingStrategy,
    useSortable
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

// --- Sortable Row Component ---
const SortableRow = ({ id, children, className }: { id: string, children: React.ReactNode, className?: string }) => {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging
    } = useSortable({ id });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        zIndex: isDragging ? 2 : 1,
        position: isDragging ? 'relative' as const : undefined,
        backgroundColor: isDragging ? 'var(--background)' : undefined,
    };

    return (
        <TableRow ref={setNodeRef} style={style} className={className}>
            <TableCell>
                <div {...attributes} {...listeners} className="cursor-grab hover:text-primary">
                    <GripVertical className="h-4 w-4 text-muted-foreground" />
                </div>
            </TableCell>
            {children}
        </TableRow>
    );
};

const AdminPage = () => {
    const {
        lawyers, statuses, doctypes, emailRecipients, caseSubjects,
        fileTypes, courtTypes, partyRoles, bureauTypes, cities, specialties, clientCategories,
        isLoading,
        addLawyer, deleteLawyer,
        addStatus, deleteStatus,
        addDoctype, deleteDoctype,
        addEmail, deleteEmail,
        addCaseSubject, deleteCaseSubject,
        addFileType, deleteFileType,
        addCourtType, deleteCourtType,
        addPartyRole, deletePartyRole,
        addBureauType, deleteBureauType,
        addCity, deleteCity,
        addSpecialty, deleteSpecialty,
        addClientCategory, deleteClientCategory,
        reorderList
    } = useConfig();

    const [activeTab, setActiveTab] = useState("lawyers");

    // Local State for Optimistic Sorting
    const [localLawyers, setLocalLawyers] = useState<ConfigItem[]>([]);
    const [localStatuses, setLocalStatuses] = useState<ConfigItem[]>([]);
    const [localDocTypes, setLocalDocTypes] = useState<ConfigItem[]>([]);
    const [localEmails, setLocalEmails] = useState<ConfigItem[]>([]);
    const [localCaseSubjects, setLocalCaseSubjects] = useState<ConfigItem[]>([]);
    const [localFileTypes, setLocalFileTypes] = useState<ConfigItem[]>([]);
    const [localPartyRoles, setLocalPartyRoles] = useState<ConfigItem[]>([]);
    const [localBureauTypes, setLocalBureauTypes] = useState<ConfigItem[]>([]);
    const [localCities, setLocalCities] = useState<ConfigItem[]>([]);
    const [localSpecialties, setLocalSpecialties] = useState<ConfigItem[]>([]);
    const [localClientCategories, setLocalClientCategories] = useState<ConfigItem[]>([]);

    // Court types: filtered by selected parent
    const [courtParentFilter, setCourtParentFilter] = useState<string>("");
    const [localCourtTypes, setLocalCourtTypes] = useState<ConfigItem[]>([]);

    useEffect(() => { setLocalLawyers(lawyers); }, [lawyers]);
    useEffect(() => { setLocalStatuses(statuses); }, [statuses]);
    useEffect(() => { setLocalDocTypes(doctypes); }, [doctypes]);
    useEffect(() => { setLocalEmails(emailRecipients); }, [emailRecipients]);
    useEffect(() => { setLocalCaseSubjects(caseSubjects); }, [caseSubjects]);
    useEffect(() => { setLocalFileTypes(fileTypes); }, [fileTypes]);
    useEffect(() => { setLocalPartyRoles(partyRoles); }, [partyRoles]);
    useEffect(() => { setLocalBureauTypes(bureauTypes); }, [bureauTypes]);
    useEffect(() => { setLocalCities(cities); }, [cities]);
    useEffect(() => { setLocalSpecialties(specialties); }, [specialties]);
    useEffect(() => { setLocalClientCategories(clientCategories); }, [clientCategories]);
    useEffect(() => {
        const filtered = courtParentFilter
            ? courtTypes.filter(c => c.parent_code === courtParentFilter)
            : courtTypes;
        setLocalCourtTypes(filtered);
    }, [courtTypes, courtParentFilter]);

    // Sensors
    const sensors = useSensors(
        useSensor(PointerSensor),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    );

    const handleDragEnd = async (event: DragEndEvent) => {
        const { active, over } = event;

        if (active.id !== over?.id) {
            let oldIndex = -1;
            let newIndex = -1;
            let currentList: ConfigItem[] = [];
            let setList: React.Dispatch<React.SetStateAction<ConfigItem[]>> | null = null;
            let type = "";

            if (activeTab === "lawyers") {
                currentList = localLawyers; setList = setLocalLawyers; type = "lawyers";
            } else if (activeTab === "statuses") {
                currentList = localStatuses; setList = setLocalStatuses; type = "statuses";
            } else if (activeTab === "doctypes") {
                currentList = localDocTypes; setList = setLocalDocTypes; type = "doctypes";
            } else if (activeTab === "emails") {
                currentList = localEmails; setList = setLocalEmails; type = "emails";
            } else if (activeTab === "case_subjects") {
                currentList = localCaseSubjects; setList = setLocalCaseSubjects; type = "case_subjects";
            } else if (activeTab === "case_types") {
                currentList = localFileTypes; setList = setLocalFileTypes; type = "file_types";
            } else if (activeTab === "party_roles") {
                currentList = localPartyRoles; setList = setLocalPartyRoles; type = "party_roles";
            } else if (activeTab === "bureau_types") {
                currentList = localBureauTypes; setList = setLocalBureauTypes; type = "bureau_types";
            } else if (activeTab === "cities") {
                currentList = localCities; setList = setLocalCities; type = "cities";
            } else if (activeTab === "specialties") {
                currentList = localSpecialties; setList = setLocalSpecialties; type = "specialties";
            } else if (activeTab === "client_categories") {
                currentList = localClientCategories; setList = setLocalClientCategories; type = "client_categories";
            }

            oldIndex = currentList.findIndex(item => (item.code || item.email) === active.id);
            newIndex = currentList.findIndex(item => (item.code || item.email) === over?.id);

            if (oldIndex !== -1 && newIndex !== -1 && setList) {
                // Optimistic Update
                const newOrder = arrayMove(currentList, oldIndex, newIndex);
                setList(newOrder);

                // API Call
                // Use code/email as ID for persistence
                const orderedIds = newOrder.map(item => item.code || item.email || "");
                const success = await reorderList(type, orderedIds);
                if (!success) {
                    toast.error("Sıralama kaydedilemedi.");
                    // Revert? For now, assume success or refresh.
                }
            }
        }
    };

    // Dialog States
    const [isLawyerAddOpen, setIsLawyerAddOpen] = useState(false);
    const [isStatusAddOpen, setIsStatusAddOpen] = useState(false);
    const [isDocTypeAddOpen, setIsDocTypeAddOpen] = useState(false);
    const [isEmailAddOpen, setIsEmailAddOpen] = useState(false);
    const [isCaseSubjectAddOpen, setIsCaseSubjectAddOpen] = useState(false);
    const [isFileTypeAddOpen, setIsFileTypeAddOpen] = useState(false);
    const [isCourtTypeAddOpen, setIsCourtTypeAddOpen] = useState(false);
    const [isPartyRoleAddOpen, setIsPartyRoleAddOpen] = useState(false);
    const [isBureauTypeAddOpen, setIsBureauTypeAddOpen] = useState(false);
    const [isCityAddOpen, setIsCityAddOpen] = useState(false);
    const [isSpecialtyAddOpen, setIsSpecialtyAddOpen] = useState(false);
    const [isClientCategoryAddOpen, setIsClientCategoryAddOpen] = useState(false);

    // Form States
    const [lawyerForm, setLawyerForm] = useState({ code: "", name: "" });
    const [statusForm, setStatusForm] = useState({ code: "", name: "" });
    const [docTypeForm, setDocTypeForm] = useState({ code: "", name: "" });
    const [emailForm, setEmailForm] = useState({ email: "", name: "", description: "" });
    const [caseSubjectForm, setCaseSubjectForm] = useState({ name: "" });
    const [fileTypeForm, setFileTypeForm] = useState({ code: "", name: "" });
    const [courtTypeForm, setCourtTypeForm] = useState({ code: "", name: "", parent_code: "" });
    const [partyRoleForm, setPartyRoleForm] = useState({ code: "", name: "", role_type: "MAIN" });
    const [bureauTypeForm, setBureauTypeForm] = useState({ code: "", name: "" });
    const [cityForm, setCityForm] = useState({ code: "", name: "" });
    const [specialtyForm, setSpecialtyForm] = useState({ code: "", name: "" });
    const [clientCategoryForm, setClientCategoryForm] = useState({ code: "", name: "" });
    const [citySearch, setCitySearch] = useState("");
    const [specialtySearch, setSpecialtySearch] = useState("");

    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleDelete = async (item: ConfigItem, type: string) => {
        if (!window.confirm(`Silinecek: ${item.name || item.code}. Emin misiniz?`)) return;

        let success = false;
        try {
            if (type === "lawyer" && item.code) success = await deleteLawyer(item.code);
            else if (type === "status" && item.code) success = await deleteStatus(item.code);
            else if (type === "doctype" && item.code) success = await deleteDoctype(item.code);
            else if (type === "email" && item.email) success = await deleteEmail(item.email);
            else if (type === "case_subject" && item.code) success = await deleteCaseSubject(item.code);
            else if (type === "file_type" && item.code) success = await deleteFileType(item.code);
            else if (type === "court_type" && item.code) success = await deleteCourtType(item.code);
            else if (type === "party_role" && item.code) success = await deletePartyRole(item.code);
            else if (type === "bureau_type" && item.code) success = await deleteBureauType(item.code);
            else if (type === "city" && item.code) success = await deleteCity(item.code);
            else if (type === "specialty" && item.code) success = await deleteSpecialty(item.code);
            else if (type === "client_category" && item.code) success = await deleteClientCategory(item.code);

            if (success) {
                toast.success("Silindi!");
            } else {
                toast.error("Silinemedi.");
            }
        } catch (e) {
            console.error(e);
            toast.error("Hata oluştu.");
        }
    };

    // --- SAVE HANDLERS ---
    const handleSaveLawyer = async () => {
        if (!lawyerForm.code || !lawyerForm.name) { toast.warning("Zorunlu alanlar eksik"); return; }
        setIsSubmitting(true);
        const success = await addLawyer(lawyerForm.code, lawyerForm.name);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsLawyerAddOpen(false); setLawyerForm({ code: "", name: "" }); }
        else toast.error("Hata");
    };
    const handleSaveStatus = async () => {
        if (!statusForm.code || !statusForm.name) { toast.warning("Zorunlu alanlar eksik"); return; }
        setIsSubmitting(true);
        const success = await addStatus(statusForm.code, statusForm.name);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsStatusAddOpen(false); setStatusForm({ code: "", name: "" }); }
        else toast.error("Hata");
    };
    const handleSaveDocType = async () => {
        if (!docTypeForm.code || !docTypeForm.name) { toast.warning("Zorunlu alanlar eksik"); return; }
        setIsSubmitting(true);
        const success = await addDoctype(docTypeForm.code, docTypeForm.name);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsDocTypeAddOpen(false); setDocTypeForm({ code: "", name: "" }); }
        else toast.error("Hata");
    };
    const handleSaveEmail = async () => {
        if (!emailForm.email || !emailForm.name) { toast.warning("Zorunlu alanlar eksik"); return; }
        setIsSubmitting(true);
        const success = await addEmail(emailForm.name, emailForm.email, emailForm.description);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsEmailAddOpen(false); setEmailForm({ email: "", name: "", description: "" }); }
        else toast.error("Hata");
    };

    const handleSaveCaseSubject = async () => {
        if (!caseSubjectForm.name) { toast.warning("İsim zorunlu"); return; }
        setIsSubmitting(true);
        const success = await addCaseSubject(caseSubjectForm.name);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsCaseSubjectAddOpen(false); setCaseSubjectForm({ name: "" }); }
        else toast.error("Hata");
    };

    const handleSaveFileType = async () => {
        if (!fileTypeForm.name) { toast.warning("İsim zorunlu"); return; }
        const code = fileTypeForm.code || fileTypeForm.name.trim();
        setIsSubmitting(true);
        const success = await addFileType(code, fileTypeForm.name);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsFileTypeAddOpen(false); setFileTypeForm({ code: "", name: "" }); }
        else toast.error("Hata");
    };

    const handleSaveCourtType = async () => {
        if (!courtTypeForm.name || !courtTypeForm.parent_code) { toast.warning("Zorunlu alanlar eksik"); return; }
        const code = courtTypeForm.code || (courtTypeForm.parent_code.slice(0, 3) + "-" + courtTypeForm.name.slice(0, 8)).toUpperCase().replace(/\s/g, "");
        setIsSubmitting(true);
        const success = await addCourtType(code, courtTypeForm.name, courtTypeForm.parent_code);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsCourtTypeAddOpen(false); setCourtTypeForm({ code: "", name: "", parent_code: courtTypeForm.parent_code }); }
        else toast.error("Hata");
    };

    const handleSavePartyRole = async () => {
        if (!partyRoleForm.name) { toast.warning("İsim zorunlu"); return; }
        const code = partyRoleForm.code || partyRoleForm.name.toUpperCase().replace(/\s/g, "-");
        setIsSubmitting(true);
        const success = await addPartyRole(code, partyRoleForm.name, partyRoleForm.role_type);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsPartyRoleAddOpen(false); setPartyRoleForm({ code: "", name: "", role_type: "MAIN" }); }
        else toast.error("Hata");
    };

    const handleSaveBureauType = async () => {
        if (!bureauTypeForm.name) { toast.warning("İsim zorunlu"); return; }
        const code = bureauTypeForm.code || bureauTypeForm.name.toUpperCase().replace(/\s/g, "-");
        setIsSubmitting(true);
        const success = await addBureauType(code, bureauTypeForm.name);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsBureauTypeAddOpen(false); setBureauTypeForm({ code: "", name: "" }); }
        else toast.error("Hata");
    };

    const handleSaveCity = async () => {
        if (!cityForm.name) { toast.warning("İsim zorunlu"); return; }
        const code = cityForm.code || cityForm.name.toUpperCase().replace(/\s/g, "-").replace(/İ/g, "I").replace(/Ş/g, "S").replace(/Ğ/g, "G").replace(/Ü/g, "U").replace(/Ö/g, "O").replace(/Ç/g, "C");
        setIsSubmitting(true);
        const success = await addCity(code, cityForm.name);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsCityAddOpen(false); setCityForm({ code: "", name: "" }); }
        else toast.error("Hata");
    };

    const handleSaveSpecialty = async () => {
        if (!specialtyForm.name) { toast.warning("İsim zorunlu"); return; }
        const code = specialtyForm.code || (specialtyForm.name.slice(0, 15).toUpperCase().replace(/\s/g, "-") + "-" + Math.random().toString(36).slice(2, 5).toUpperCase());
        setIsSubmitting(true);
        const success = await addSpecialty(code, specialtyForm.name);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsSpecialtyAddOpen(false); setSpecialtyForm({ code: "", name: "" }); }
        else toast.error("Hata");
    };

    const handleSaveClientCategory = async () => {
        if (!clientCategoryForm.name) { toast.warning("İsim zorunlu"); return; }
        const code = clientCategoryForm.code || clientCategoryForm.name.toUpperCase().replace(/\s/g, "-").replace(/İ/g, "I").replace(/Ş/g, "S").replace(/Ğ/g, "G").replace(/Ü/g, "U").replace(/Ö/g, "O").replace(/Ç/g, "C");
        setIsSubmitting(true);
        const success = await addClientCategory(code, clientCategoryForm.name);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsClientCategoryAddOpen(false); setClientCategoryForm({ code: "", name: "" }); }
        else toast.error("Hata");
    };

    const { authRequest } = useAuthRequest();
    const queryClient = useQueryClient();

    if (isLoading) {
        return (
            <div className="min-h-screen bg-background">
                <Header />
                <div className="container mx-auto py-10 flex justify-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background text-foreground">
            <Header />
            <div className="container mx-auto py-10 px-4">
                <div className="flex items-center justify-between mb-2">
                    <h1 className="text-3xl font-bold tracking-tight">Yönetim Paneli</h1>
                </div>
                <p className="text-muted-foreground mb-8">Listeleri sürükleyerek sıralayabilirsiniz.</p>

                <Tabs defaultValue="lawyers" className="w-full" onValueChange={setActiveTab}>
                    <TabsList className="flex flex-wrap h-auto gap-2 justify-start mb-8 p-1 bg-muted/20">
                        <TabsTrigger value="lawyers">Avukatlar</TabsTrigger>
                        <TabsTrigger value="statuses">Durumlar</TabsTrigger>
                        <TabsTrigger value="doctypes">Belge Türleri</TabsTrigger>
                        <TabsTrigger value="case_subjects">Dava Konuları</TabsTrigger>
                        <TabsTrigger value="emails">E-posta Alıcıları</TabsTrigger>
                        <TabsTrigger value="case_types">Dava Türleri</TabsTrigger>
                        <TabsTrigger value="court_types">Mahkemeler</TabsTrigger>
                        <TabsTrigger value="party_roles">Taraf Rolleri</TabsTrigger>
                        <TabsTrigger value="bureau_types">Büro Türleri</TabsTrigger>
                        <TabsTrigger value="client_categories">Kategoriler</TabsTrigger>
                        <TabsTrigger value="specialties">Uzmanlıklar</TabsTrigger>
                        <TabsTrigger value="cities">Şehirler</TabsTrigger>
                    </TabsList>

                    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>

                        {/* LAWYERS TAB */}
                        <TabsContent value="lawyers">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle>Avukat Listesi</CardTitle>
                                    <Dialog open={isLawyerAddOpen} onOpenChange={setIsLawyerAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Avukat</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Avukat Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Kod</Label><Input value={lawyerForm.code} onChange={e => setLawyerForm({ ...lawyerForm, code: e.target.value })} className="col-span-3" /></div>
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">İsim</Label><Input value={lawyerForm.name} onChange={e => setLawyerForm({ ...lawyerForm, name: e.target.value })} className="col-span-3" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveLawyer} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Kod</TableHead><TableHead>Ad Soyad</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localLawyers.map(i => i.code)} strategy={verticalListSortingStrategy}>
                                                {localLawyers.map((item) => (
                                                    <SortableRow key={item.code} id={item.code}>
                                                        <TableCell className="font-mono">{item.code}</TableCell>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "lawyer")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                        </TableCell>
                                                    </SortableRow>
                                                ))}
                                            </SortableContext>
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* STATUSES TAB */}
                        <TabsContent value="statuses">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle>Durum Listesi</CardTitle>
                                    <Dialog open={isStatusAddOpen} onOpenChange={setIsStatusAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Durum</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Durum Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Kod</Label><Input value={statusForm.code} onChange={e => setStatusForm({ ...statusForm, code: e.target.value })} className="col-span-3" /></div>
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Açıklama</Label><Input value={statusForm.name} onChange={e => setStatusForm({ ...statusForm, name: e.target.value })} className="col-span-3" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveStatus} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Kod</TableHead><TableHead>Açıklama</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localStatuses.map(i => i.code)} strategy={verticalListSortingStrategy}>
                                                {localStatuses.map((item) => (
                                                    <SortableRow key={item.code} id={item.code}>
                                                        <TableCell>{item.code}</TableCell>
                                                        <TableCell>{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "status")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                        </TableCell>
                                                    </SortableRow>
                                                ))}
                                            </SortableContext>
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* DOCTYPES TAB */}
                        <TabsContent value="doctypes">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle>Belge Türleri</CardTitle>
                                    <Dialog open={isDocTypeAddOpen} onOpenChange={setIsDocTypeAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Belge Türü</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Belge Türü Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Kod</Label><Input value={docTypeForm.code} onChange={e => setDocTypeForm({ ...docTypeForm, code: e.target.value })} className="col-span-3" /></div>
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Adı</Label><Input value={docTypeForm.name} onChange={e => setDocTypeForm({ ...docTypeForm, name: e.target.value })} className="col-span-3" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveDocType} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Kod</TableHead><TableHead>Açıklama</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localDocTypes.map(i => i.code)} strategy={verticalListSortingStrategy}>
                                                {localDocTypes.map((item) => (
                                                    <SortableRow key={item.code} id={item.code}>
                                                        <TableCell className="font-medium">{item.code}</TableCell>
                                                        <TableCell>{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "doctype")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                        </TableCell>
                                                    </SortableRow>
                                                ))}
                                            </SortableContext>
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* CASE SUBJECTS TAB */}
                        <TabsContent value="case_subjects">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle>Dava Konuları</CardTitle>
                                    <Dialog open={isCaseSubjectAddOpen} onOpenChange={setIsCaseSubjectAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Konu</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Dava Konusu Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">İsim</Label><Input value={caseSubjectForm.name} onChange={e => setCaseSubjectForm({ ...caseSubjectForm, name: e.target.value })} className="col-span-3" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveCaseSubject} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Dava Konusu</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localCaseSubjects.map(i => i.code)} strategy={verticalListSortingStrategy}>
                                                {localCaseSubjects.map((item) => (
                                                    <SortableRow key={item.code} id={item.code}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "case_subject")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                        </TableCell>
                                                    </SortableRow>
                                                ))}
                                            </SortableContext>
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* EMAILS TAB */}
                        <TabsContent value="emails">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle>E-posta Alıcıları</CardTitle>
                                    <Dialog open={isEmailAddOpen} onOpenChange={setIsEmailAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni E-posta</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni E-posta Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">İsim</Label><Input value={emailForm.name} onChange={e => setEmailForm({ ...emailForm, name: e.target.value })} className="col-span-3" /></div>
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">E-posta</Label><Input value={emailForm.email} onChange={e => setEmailForm({ ...emailForm, email: e.target.value })} className="col-span-3" /></div>
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Rol</Label><Input value={emailForm.description} onChange={e => setEmailForm({ ...emailForm, description: e.target.value })} className="col-span-3" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveEmail} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Ad Soyad</TableHead><TableHead>E-posta</TableHead><TableHead>Rol</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localEmails.map(i => i.email)} strategy={verticalListSortingStrategy}>
                                                {localEmails.map((item) => (
                                                    <SortableRow key={item.email} id={item.email}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell>{item.email}</TableCell>
                                                        <TableCell>{item.description || "-"}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "email")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                        </TableCell>
                                                    </SortableRow>
                                                ))}
                                            </SortableContext>
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* DAVA TÜRLERİ TAB */}
                        <TabsContent value="case_types">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle>Dava Türleri</CardTitle>
                                    <Dialog open={isFileTypeAddOpen} onOpenChange={setIsFileTypeAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Tür</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Dava Türü Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={fileTypeForm.name} onChange={e => setFileTypeForm({ ...fileTypeForm, name: e.target.value })} className="col-span-3" placeholder="Ceza" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveFileType} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Ad</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localFileTypes.map(i => i.code ?? i.name)} strategy={verticalListSortingStrategy}>
                                                {localFileTypes.map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? item.name}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "file_type")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                        </TableCell>
                                                    </SortableRow>
                                                ))}
                                            </SortableContext>
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* MAHKEME TÜRLERİ TAB */}
                        <TabsContent value="court_types">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div className="flex flex-col gap-2">
                                        <CardTitle>Mahkeme Türleri</CardTitle>
                                        <div className="flex gap-2 flex-wrap">
                                            <Button size="sm" variant={courtParentFilter === "" ? "default" : "outline"} onClick={() => setCourtParentFilter("")}>Tümü</Button>
                                            {fileTypes.map(ft => (
                                                <Button key={ft.code} size="sm" variant={courtParentFilter === ft.name ? "default" : "outline"} onClick={() => setCourtParentFilter(ft.name ?? "")}>{ft.name}</Button>
                                            ))}
                                        </div>
                                    </div>
                                    <Dialog open={isCourtTypeAddOpen} onOpenChange={setIsCourtTypeAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Mahkeme</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Mahkeme Türü Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4">
                                                    <Label className="text-right">Dava Türü</Label>
                                                    <select className="col-span-3 border rounded px-2 py-1 bg-background text-foreground" value={courtTypeForm.parent_code} onChange={e => setCourtTypeForm({ ...courtTypeForm, parent_code: e.target.value })}>
                                                        <option value="">Seçin...</option>
                                                        {fileTypes.map(ft => <option key={ft.code} value={ft.name ?? ""}>{ft.name}</option>)}
                                                    </select>
                                                </div>
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Mahkeme Adı</Label><Input value={courtTypeForm.name} onChange={e => setCourtTypeForm({ ...courtTypeForm, name: e.target.value })} className="col-span-3" placeholder="SULH HUKUK MAHKEMESİ" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveCourtType} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead>Dava Türü</TableHead><TableHead>Mahkeme Adı</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            {localCourtTypes.map((item) => (
                                                <TableRow key={item.code}>
                                                    <TableCell className="text-muted-foreground text-sm">{item.parent_code}</TableCell>
                                                    <TableCell className="font-medium">{item.name}</TableCell>
                                                    <TableCell className="text-right">
                                                        <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "court_type")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                    </TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* TARAF ROLLERİ TAB */}
                        <TabsContent value="party_roles">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle>Taraf Rolleri</CardTitle>
                                    <Dialog open={isPartyRoleAddOpen} onOpenChange={setIsPartyRoleAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Rol</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Taraf Rolü Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={partyRoleForm.name} onChange={e => setPartyRoleForm({ ...partyRoleForm, name: e.target.value })} className="col-span-3" placeholder="Davacı" /></div>
                                                <div className="grid grid-cols-4 items-center gap-4">
                                                    <Label className="text-right">Tür</Label>
                                                    <select className="col-span-3 border rounded px-2 py-1 bg-background text-foreground" value={partyRoleForm.role_type} onChange={e => setPartyRoleForm({ ...partyRoleForm, role_type: e.target.value })}>
                                                        <option value="MAIN">Ana Taraf</option>
                                                        <option value="THIRD">Üçüncü Taraf</option>
                                                    </select>
                                                </div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSavePartyRole} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Ad</TableHead><TableHead>Tür</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localPartyRoles.map(i => i.code ?? i.name)} strategy={verticalListSortingStrategy}>
                                                {localPartyRoles.map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? item.name}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-xs text-muted-foreground">{item.role_type === "THIRD" ? "Üçüncü Taraf" : "Ana Taraf"}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "party_role")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                        </TableCell>
                                                    </SortableRow>
                                                ))}
                                            </SortableContext>
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* BÜRO TÜRLERİ TAB */}
                        <TabsContent value="bureau_types">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle>Büro Özel Türleri</CardTitle>
                                    <Dialog open={isBureauTypeAddOpen} onOpenChange={setIsBureauTypeAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Tür</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Büro Türü Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={bureauTypeForm.name} onChange={e => setBureauTypeForm({ ...bureauTypeForm, name: e.target.value })} className="col-span-3" placeholder="ALEYHE" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveBureauType} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Ad</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localBureauTypes.map(i => i.code ?? i.name)} strategy={verticalListSortingStrategy}>
                                                {localBureauTypes.map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? item.name}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "bureau_type")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                        </TableCell>
                                                    </SortableRow>
                                                ))}
                                            </SortableContext>
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* KATEGORİLER TAB */}
                        <TabsContent value="client_categories">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle>Müvekkil Kategorileri</CardTitle>
                                    <Dialog open={isClientCategoryAddOpen} onOpenChange={setIsClientCategoryAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Kategori</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Kategori Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={clientCategoryForm.name} onChange={e => setClientCategoryForm({ ...clientCategoryForm, name: e.target.value })} className="col-span-3" placeholder="Doktor" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveClientCategory} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Ad</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localClientCategories.map(i => i.code ?? i.name)} strategy={verticalListSortingStrategy}>
                                                {localClientCategories.map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? item.name}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "client_category")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                        </TableCell>
                                                    </SortableRow>
                                                ))}
                                            </SortableContext>
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* UZMANLIKLAR TAB */}
                        <TabsContent value="specialties">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Uzmanlık Alanları</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={specialtySearch} onChange={e => setSpecialtySearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isSpecialtyAddOpen} onOpenChange={setIsSpecialtyAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Uzmanlık</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Uzmanlık Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={specialtyForm.name} onChange={e => setSpecialtyForm({ ...specialtyForm, name: e.target.value })} className="col-span-3" placeholder="Kardiyoloji" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveSpecialty} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead>Uzmanlık Adı</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            {localSpecialties.filter(i => !specialtySearch || i.name.toLowerCase().includes(specialtySearch.toLowerCase())).map((item) => (
                                                <TableRow key={item.code}>
                                                    <TableCell className="font-medium">{item.name}</TableCell>
                                                    <TableCell className="text-right">
                                                        <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "specialty")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                    </TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* ŞEHİRLER TAB */}
                        <TabsContent value="cities">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Şehir Listesi</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={citySearch} onChange={e => setCitySearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isCityAddOpen} onOpenChange={setIsCityAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Şehir</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Şehir Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={cityForm.name} onChange={e => setCityForm({ ...cityForm, name: e.target.value })} className="col-span-3" placeholder="İstanbul" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveCity} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead>Şehir</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            {localCities.filter(i => !citySearch || i.name.toLowerCase().includes(citySearch.toLowerCase())).map((item) => (
                                                <TableRow key={item.code}>
                                                    <TableCell className="font-medium">{item.name}</TableCell>
                                                    <TableCell className="text-right">
                                                        <Button variant="ghost" size="icon" onClick={() => handleDelete(item, "city")}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                    </TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                    </DndContext>
                </Tabs>
            </div>
        </div>
    );
};

export default AdminPage;
