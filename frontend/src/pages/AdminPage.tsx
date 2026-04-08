import { useState, useEffect } from "react";
import { Header } from "@/components/Header";
import { useConfig, ConfigItem } from "@/hooks/useConfig";
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
        lawyers, statuses, doctypes, emailRecipients, caseSubjects, isLoading,
        addLawyer, deleteLawyer,
        addStatus, deleteStatus,
        addDoctype, deleteDoctype,
        addEmail, deleteEmail,
        addCaseSubject, deleteCaseSubject,
        reorderList
    } = useConfig();

    const [activeTab, setActiveTab] = useState("lawyers");

    // Local State for Optimistic Sorting
    const [localLawyers, setLocalLawyers] = useState<ConfigItem[]>([]);
    const [localStatuses, setLocalStatuses] = useState<ConfigItem[]>([]);
    const [localDocTypes, setLocalDocTypes] = useState<ConfigItem[]>([]);
    const [localEmails, setLocalEmails] = useState<ConfigItem[]>([]);
    const [localCaseSubjects, setLocalCaseSubjects] = useState<ConfigItem[]>([]); // Added

    // Sync from props when they change (unless we are dragging - handled by optimistics)
    useEffect(() => { setLocalLawyers(lawyers); }, [lawyers]);
    useEffect(() => { setLocalStatuses(statuses); }, [statuses]);
    useEffect(() => { setLocalDocTypes(doctypes); }, [doctypes]);
    useEffect(() => { setLocalEmails(emailRecipients); }, [emailRecipients]);
    useEffect(() => { setLocalCaseSubjects(caseSubjects); }, [caseSubjects]); // Added

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
                currentList = localLawyers;
                setList = setLocalLawyers;
                type = "lawyers";
            } else if (activeTab === "statuses") {
                currentList = localStatuses;
                setList = setLocalStatuses;
                type = "statuses";
            } else if (activeTab === "doctypes") {
                currentList = localDocTypes;
                setList = setLocalDocTypes;
                type = "doctypes";
            } else if (activeTab === "emails") {
                currentList = localEmails;
                setList = setLocalEmails;
                type = "emails";
            } else if (activeTab === "case_subjects") {
                currentList = localCaseSubjects;
                setList = setLocalCaseSubjects;
                type = "case_subjects";
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
    const [isCaseSubjectAddOpen, setIsCaseSubjectAddOpen] = useState(false); // Added

    // Form States
    const [lawyerForm, setLawyerForm] = useState({ code: "", name: "" });
    const [statusForm, setStatusForm] = useState({ code: "", name: "" });
    const [docTypeForm, setDocTypeForm] = useState({ code: "", name: "" });
    const [emailForm, setEmailForm] = useState({ email: "", name: "", description: "" });
    const [caseSubjectForm, setCaseSubjectForm] = useState({ name: "" }); // Added

    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleDelete = async (item: ConfigItem, type: string) => {
        if (!window.confirm(`Silinecek: ${item.name || item.code}. Emin misiniz?`)) return;

        let success = false;
        try {
            if (type === "lawyer" && item.code) success = await deleteLawyer(item.code);
            else if (type === "status" && item.code) success = await deleteStatus(item.code);
            else if (type === "doctype" && item.code) success = await deleteDoctype(item.code);
            else if (type === "email" && item.email) success = await deleteEmail(item.email);
            else if (type === "case_subject" && item.code) success = await deleteCaseSubject(item.code); // Added

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

    // Case Subject Handlers

    const handleSaveCaseSubject = async () => {
        if (!caseSubjectForm.name) { toast.warning("İsim zorunlu"); return; }
        setIsSubmitting(true);
        const success = await addCaseSubject(caseSubjectForm.name);
        setIsSubmitting(false);
        if (success) { toast.success("Eklendi"); setIsCaseSubjectAddOpen(false); setCaseSubjectForm({ name: "" }); }
        else toast.error("Hata");
    };

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
                <h1 className="text-3xl font-bold tracking-tight mb-2">Yönetim Paneli</h1>
                <p className="text-muted-foreground mb-8">Listeleri sürükleyerek sıralayabilirsiniz.</p>

                <Tabs defaultValue="lawyers" className="w-full" onValueChange={setActiveTab}>
                    <TabsList className="flex flex-wrap h-auto gap-2 justify-start mb-8 p-1 bg-muted/20">
                        <TabsTrigger value="lawyers">Avukatlar</TabsTrigger>
                        <TabsTrigger value="statuses">Durumlar</TabsTrigger>
                        <TabsTrigger value="doctypes">Belge Türleri</TabsTrigger>
                        <TabsTrigger value="case_subjects">Dava Konuları</TabsTrigger>
                        <TabsTrigger value="emails">E-posta Alıcıları</TabsTrigger>

                        {/* YAPILACAKLAR / EKLENECEKLER */}
                        <TabsTrigger value="court_types" className="border border-dashed border-primary/40 opacity-70">Mahkemeler</TabsTrigger>
                        <TabsTrigger value="case_types" className="border border-dashed border-primary/40 opacity-70">Dava Türleri</TabsTrigger>
                        <TabsTrigger value="party_roles" className="border border-dashed border-primary/40 opacity-70">Taraf Rolleri</TabsTrigger>
                        <TabsTrigger value="client_categories" className="border border-dashed border-primary/40 opacity-70">Kategoriler</TabsTrigger>
                        <TabsTrigger value="specialties" className="border border-dashed border-primary/40 opacity-70">Uzmanlıklar</TabsTrigger>
                        <TabsTrigger value="cities" className="border border-dashed border-primary/40 opacity-70">Şehirler</TabsTrigger>
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

                        {/* YENİ EKLENECEK PLACEHOLDER İÇERİKLER */}
                        <TabsContent value="court_types">
                            <Card className="glass-card shadow-lg border-primary/20 bg-primary/5">
                                <CardHeader>
                                    <CardTitle>Mahkeme Türleri (Yakında)</CardTitle>
                                    <CardDescription>Asliye Hukuk, Tüketici Mahkemesi vb. mahkeme tiplerinin dinamik yönetimi eklenecek.</CardDescription>
                                </CardHeader>
                            </Card>
                        </TabsContent>
                        <TabsContent value="case_types">
                            <Card className="glass-card shadow-lg border-primary/20 bg-primary/5">
                                <CardHeader>
                                    <CardTitle>Dava Türleri (Yakında)</CardTitle>
                                    <CardDescription>Belirsiz Alacak, Kısmi Dava, Tespit vs. dava açılış türleri eklenecek.</CardDescription>
                                </CardHeader>
                            </Card>
                        </TabsContent>
                        <TabsContent value="party_roles">
                            <Card className="glass-card shadow-lg border-primary/20 bg-primary/5">
                                <CardHeader>
                                    <CardTitle>Taraf Rolleri (Yakında)</CardTitle>
                                    <CardDescription>Davacı, Davalı, İhbar Olunan, Müdahil gibi dava içi roller eklenecek.</CardDescription>
                                </CardHeader>
                            </Card>
                        </TabsContent>
                        <TabsContent value="client_categories">
                            <Card className="glass-card shadow-lg border-primary/20 bg-primary/5">
                                <CardHeader>
                                    <CardTitle>Müvekkil Kategorileri (Yakında)</CardTitle>
                                    <CardDescription>Doktor, Hasta, Sigorta Acentesi vb. cari kişi / kurumsal gruplandırmalar eklenecek.</CardDescription>
                                </CardHeader>
                            </Card>
                        </TabsContent>
                        <TabsContent value="specialties">
                            <Card className="glass-card shadow-lg border-primary/20 bg-primary/5">
                                <CardHeader>
                                    <CardTitle>Uzmanlık Alanları (Yakında)</CardTitle>
                                    <CardDescription>Kardiyoloji, Dahiliye, Pratisyen gibi hekim uzmanlık alanları eklenecek.</CardDescription>
                                </CardHeader>
                            </Card>
                        </TabsContent>
                        <TabsContent value="cities">
                            <Card className="glass-card shadow-lg border-primary/20 bg-primary/5">
                                <CardHeader>
                                    <CardTitle>Şehir Listesi (Yakında)</CardTitle>
                                    <CardDescription>Uygulamada kullanılan il listesinin ve adliyelerin lokasyon yönetimi eklenecek.</CardDescription>
                                </CardHeader>
                            </Card>
                        </TabsContent>

                    </DndContext>
                </Tabs>
            </div>
        </div>
    );
};

export default AdminPage;
