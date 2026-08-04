import { useState, useEffect } from "react";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { useConfig, ConfigItem, ListUsage, DeleteMode } from "@/hooks/useConfig";
import { Eyebrow } from "@/components/dashboard/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Plus, Trash2, Edit2, Loader2, GripVertical, Eye, Download } from "lucide-react";
import { ActivityReportModal, ActivityReport } from "@/components/ActivityReportModal";
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

// Türkçe büyük harf: toUpperCase() 'i'yi 'I' yapar, locale şart.
// Kod alanları ve harf duyarsız karşılaştırmalar için kullanılır.
const trUpper = (s: string) => s.toLocaleUpperCase("tr-TR");

// Liste adlarının saklama formatı: her kelimenin ilk harfi büyük, kalanı küçük.
// Yazarken uygulanır; boşlukları olduğu gibi bırakır ki kullanıcı yazmaya devam edebilsin.
const trTitle = (s: string) =>
    s.toLocaleLowerCase("tr-TR").replace(/(^|\s)(\S)/gu, (_, sep: string, ch: string) => sep + ch.toLocaleUpperCase("tr-TR"));

// Türkçe duyarsız "içerir" — liste aramalarında kullanılır
const trMatch = (hay: string | undefined | null, needle: string) =>
    !needle || (hay ?? "").toLocaleLowerCase("tr-TR").includes(needle.toLocaleLowerCase("tr-TR"));

// Basit Levenshtein mesafesi — benzer kayıt uyarısı için
const editDistance = (a: string, b: string): number => {
    const m = a.length, n = b.length;
    if (!m) return n;
    if (!n) return m;
    let prev = Array.from({ length: n + 1 }, (_, i) => i);
    for (let i = 1; i <= m; i++) {
        const cur = [i];
        for (let j = 1; j <= n; j++) {
            cur[j] = a[i - 1] === b[j - 1]
                ? prev[j - 1]
                : 1 + Math.min(prev[j - 1], prev[j], cur[j - 1]);
        }
        prev = cur;
    }
    return prev[n];
};

// Birebir aynı olmayan ama çok benzeyen mevcut kaydı bulur (birebir aynıyı backend 409 ile engeller)
const findSimilar = (name: string, items: ConfigItem[]): string | null => {
    const target = trUpper(name).trim();
    if (!target) return null;
    for (const it of items) {
        const other = trUpper(it.name ?? "").trim();
        if (!other || other === target) continue;
        if (target.length >= 5 && editDistance(target, other) <= 2) return it.name;
        if ((target.includes(other) || other.includes(target)) && Math.abs(target.length - other.length) <= 4) return it.name;
    }
    return null;
};

// Benzer kayıt varsa kullanıcıya sorar; eklemeye devam edilecekse true döner
const confirmSimilar = (name: string, items: ConfigItem[]): boolean => {
    const similar = findSimilar(name, items);
    if (!similar) return true;
    return window.confirm(`Benzer kayıt zaten listede var: "${similar}". Yine de eklensin mi?`);
};

// Avukat tablosu ekrana sığmayacak kadar geniş; işlem butonları sağda sabitlenir
// yoksa yatay kaydırmadan görünmüyorlar. Arka plan kart rengiyle aynı olmalı ki
// altından kayan hücreler görünmesin.
const STICKY_ACTIONS = "text-right sticky right-0 bg-[var(--bg-elevated)] shadow-[-8px_0_8px_-8px_rgba(0,0,0,0.15)]";

// Sekme değeri → backend liste tipi. Çoğu birebir; yalnızca "Dava Türleri"
// sekmesi file_types listesini yönetir. Excel dışa aktarımı buradan çözülür.
const TAB_TO_LIST: Record<string, string> = {
    lawyers: "lawyers", statuses: "statuses", doctypes: "doctypes",
    case_subjects: "case_subjects", emails: "emails", case_types: "file_types",
    court_types: "court_types", party_roles: "party_roles",
    bureau_types: "bureau_types", client_categories: "client_categories",
    file_statuses: "file_statuses", specialties: "specialties", cities: "cities",
};

// Düzenleme formundaki tek bir alan. options verilirse açılır liste, aksi hâlde metin kutusu.
interface FieldDef {
    key: string;
    label: string;
    format?: "title";                                  // yazarken Türkçe başlık formatına çevir
    options?: { value: string; label: string }[];
    mono?: boolean;
    maxLength?: number;
}

interface EditState {
    type: string;                        // backend liste tipi ("statuses", "lawyers", …)
    id: string;                          // kimlik (kod ya da e-posta)
    title: string;                       // diyalog başlığında gösterilen mevcut ad
    values: Record<string, string>;
}

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
    useSetPageTitle("Yönetim", ["Yönetici Paneli"]);
    const {
        lawyers, statuses, doctypes, emailRecipients, caseSubjects,
        fileTypes, courtTypes, partyRoles, bureauTypes, cities, specialties, clientCategories,
        fileStatuses,
        isLoading,
        addLawyer, addStatus, addDoctype, addEmail, addCaseSubject,
        addFileType, addCourtType, addPartyRole, addBureauType,
        addCity, addSpecialty, addClientCategory, addFileStatus,
        reorderList, updateItem, deleteItem, fetchUsage
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
    const [localFileStatuses, setLocalFileStatuses] = useState<ConfigItem[]>([]);

    // Court types: filtered by selected parent
    const [courtParentFilter, setCourtParentFilter] = useState<string>("");
    const [localCourtTypes, setLocalCourtTypes] = useState<ConfigItem[]>([]);

    useEffect(() => {
        const gorevOrder: Record<string, number> = { 'AVUKAT': 0, 'DIŞ AVUKAT': 1, 'DİĞER': 2 };
        setLocalLawyers([...lawyers].sort((a, b) => (gorevOrder[a.gorev ?? ''] ?? 3) - (gorevOrder[b.gorev ?? ''] ?? 3)));
    }, [lawyers]);
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
    useEffect(() => { setLocalFileStatuses(fileStatuses); }, [fileStatuses]);
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
            } else if (activeTab === "file_statuses") {
                currentList = localFileStatuses; setList = setLocalFileStatuses; type = "file_statuses";
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
                try {
                    await reorderList(type, orderedIds);
                } catch {
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
    const [isFileStatusAddOpen, setIsFileStatusAddOpen] = useState(false);

    // Form States
    const [lawyerForm, setLawyerForm] = useState({ code: "", name: "", tc_no: "", sicil_no: "", city: "" });
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
    const [fileStatusForm, setFileStatusForm] = useState({ name: "" });
    // Aktif sekmedeki listeyi kelimeyle filtreler; sekme değişince sıfırlanır
    const [listSearch, setListSearch] = useState("");

    const [isSubmitting, setIsSubmitting] = useState(false);

    // Ortak ekleme akışı: başarıda formu kapatır, hatada backend'in mesajını
    // (örn. 409 "… zaten listede mevcut") toast olarak gösterir.
    const runAdd = async (fn: () => Promise<boolean>, onOk: () => void) => {
        setIsSubmitting(true);
        try {
            await fn();
            toast.success("Eklendi");
            onOk();
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Hata");
        } finally {
            setIsSubmitting(false);
        }
    };

    // --- DÜZENLEME / SİLME (tüm listeler için ortak) ---

    // Her listenin düzenlenebilir alanları — backend'deki ListSpec.editable ile eşleşir.
    // Kod alanı burada yok: kimlik olduğu ve arşivdeki dosya adlarında geçtiği için sabittir.
    const editFieldsFor = (type: string): FieldDef[] => {
        switch (type) {
            case "lawyers":
                return [
                    { key: "name", label: "Ad Soyad", format: "title" },
                    { key: "gorev", label: "Görev", options: [{ value: "AVUKAT", label: "AVUKAT" }, { value: "DIŞ AVUKAT", label: "DIŞ AVUKAT" }] },
                    { key: "city", label: "Şehir", options: cities.map(c => ({ value: c.name ?? "", label: c.name ?? "" })) },
                    { key: "tc_no", label: "T.C. No", mono: true, maxLength: 11 },
                    { key: "sicil_no", label: "Baro Sicil No", mono: true },
                    { key: "email", label: "E-posta" },
                    { key: "phone", label: "Telefon" },
                    { key: "address", label: "Adres" },
                ];
            case "emails":
                return [
                    { key: "name", label: "Ad Soyad", format: "title" },
                    { key: "email", label: "E-posta" },
                    { key: "description", label: "Rol" },
                ];
            case "court_types":
                return [
                    { key: "name", label: "Mahkeme Adı", format: "title" },
                    { key: "parent_code", label: "Dava Türü", options: fileTypes.map(ft => ({ value: ft.name ?? "", label: ft.name ?? "" })) },
                ];
            case "party_roles":
                return [
                    { key: "name", label: "Ad", format: "title" },
                    { key: "role_type", label: "Tür", options: [{ value: "MAIN", label: "Ana Taraf" }, { value: "THIRD", label: "Üçüncü Taraf" }] },
                ];
            default:
                return [{ key: "name", label: "Ad", format: "title" }];
        }
    };

    // Listenin kimlik alanı: e-posta alıcıları e-posta ile, diğerleri kod ile tanımlanır
    const identifierOf = (type: string, item: ConfigItem) => (type === "emails" ? item.email : item.code) ?? "";

    // "Başka değere taşı" seçeneğinin adaylarını üretmek için tip → liste eşlemesi
    const itemsOfType: Record<string, ConfigItem[]> = {
        lawyers, statuses, doctypes, case_subjects: caseSubjects, emails: emailRecipients,
        file_types: fileTypes, court_types: courtTypes, party_roles: partyRoles,
        bureau_types: bureauTypes, cities, specialties, client_categories: clientCategories,
        file_statuses: fileStatuses,
    };

    const [editing, setEditing] = useState<EditState | null>(null);
    const [deleting, setDeleting] = useState<{ type: string; id: string; label: string } | null>(null);
    const [usage, setUsage] = useState<ListUsage | null>(null);
    const [usageLoading, setUsageLoading] = useState(false);
    const [deleteMode, setDeleteMode] = useState<"clear" | "reassign">("clear");
    const [reassignTarget, setReassignTarget] = useState("");

    // Açık sekmedeki listeyi Excel olarak indirir (dosya adını backend belirler:
    // hukdok-<liste>-<tarih>.xlsx)
    const [isExporting, setIsExporting] = useState(false);
    const handleExport = async () => {
        const listType = TAB_TO_LIST[activeTab];
        if (!listType) return;
        setIsExporting(true);
        try {
            const { apiClient } = await import("@/lib/api");
            const res = await apiClient.fetch(`/api/config/export/${listType}`);
            if (!res.ok) throw new Error("Dosya oluşturulamadı");
            const blob = await res.blob();
            // Dosya adı Content-Disposition'dan okunur; okunamazsa makul bir yedek kullanılır
            const disposition = res.headers.get("Content-Disposition") ?? "";
            const name = /filename="?([^"]+)"?/.exec(disposition)?.[1]
                ?? `hukdok-${listType}-${new Date().toISOString().slice(0, 10)}.xlsx`;
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = name;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            toast.success(`İndirildi: ${name}`);
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Excel indirilemedi");
        } finally {
            setIsExporting(false);
        }
    };

    const openEdit = (type: string, item: ConfigItem) => {
        const fields = editFieldsFor(type);
        setEditing({
            type,
            id: identifierOf(type, item),
            title: item.name || item.email || "",
            values: Object.fromEntries(fields.map(f => [f.key, (item as Record<string, unknown>)[f.key] as string ?? ""])),
        });
    };

    const handleSaveEdit = async () => {
        if (!editing) return;
        if (!(editing.values.name ?? "").trim() && editFieldsFor(editing.type).some(f => f.key === "name")) {
            toast.warning("Ad boş olamaz"); return;
        }
        setIsSubmitting(true);
        try {
            const updated = await updateItem(editing.type, editing.id, editing.values);
            toast.success(updated > 0 ? `Güncellendi — eski adı taşıyan ${updated} kayıt da yansıtıldı` : "Güncellendi");
            setEditing(null);
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Hata");
        } finally {
            setIsSubmitting(false);
        }
    };

    const openDelete = async (type: string, item: ConfigItem) => {
        const id = identifierOf(type, item);
        setDeleting({ type, id, label: item.name || item.email || id });
        setUsage(null);
        setReassignTarget("");
        setUsageLoading(true);
        try {
            const found = await fetchUsage(type, id);
            setUsage(found);
            // Zorunlu alanlarda kullanılıyorsa boşaltma mümkün değil — taşımayı öner
            setDeleteMode(found.clearable ? "clear" : "reassign");
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Kullanım bilgisi alınamadı");
            setDeleting(null);
        } finally {
            setUsageLoading(false);
        }
    };

    const handleConfirmDelete = async () => {
        if (!deleting || !usage) return;
        // Kullanımda değilse mod sorusu anlamsız; doğrudan sil
        const mode: DeleteMode = usage.total === 0 ? "keep" : deleteMode;
        if (mode === "reassign" && !reassignTarget) { toast.warning("Taşınacak kaydı seçin"); return; }
        setIsSubmitting(true);
        try {
            const affected = await deleteItem(deleting.type, deleting.id, mode, reassignTarget || undefined);
            toast.success(affected > 0
                ? `Silindi — ${affected} kayıt ${mode === "reassign" ? "taşındı" : "boşaltıldı"}`
                : "Silindi");
            setDeleting(null);
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Silinemedi");
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleSaveLawyer = () => {
        if (!lawyerForm.code || !lawyerForm.name) { toast.warning("Zorunlu alanlar eksik"); return; }
        runAdd(() => addLawyer(lawyerForm.code, lawyerForm.name, lawyerForm.tc_no || undefined, lawyerForm.sicil_no || undefined,
            undefined, undefined, undefined, undefined, lawyerForm.city || undefined),
            () => { setIsLawyerAddOpen(false); setLawyerForm({ code: "", name: "", tc_no: "", sicil_no: "", city: "" }); });
    };

    const handleSaveStatus = () => {
        if (!statusForm.code || !statusForm.name) { toast.warning("Zorunlu alanlar eksik"); return; }
        if (!confirmSimilar(statusForm.name, statuses)) return;
        runAdd(() => addStatus(statusForm.code, statusForm.name),
            () => { setIsStatusAddOpen(false); setStatusForm({ code: "", name: "" }); });
    };
    const handleSaveDocType = () => {
        if (!docTypeForm.code || !docTypeForm.name) { toast.warning("Zorunlu alanlar eksik"); return; }
        if (!confirmSimilar(docTypeForm.name, doctypes)) return;
        runAdd(() => addDoctype(docTypeForm.code, docTypeForm.name),
            () => { setIsDocTypeAddOpen(false); setDocTypeForm({ code: "", name: "" }); });
    };
    const handleSaveEmail = () => {
        if (!emailForm.email || !emailForm.name) { toast.warning("Zorunlu alanlar eksik"); return; }
        runAdd(() => addEmail(emailForm.name, emailForm.email, emailForm.description),
            () => { setIsEmailAddOpen(false); setEmailForm({ email: "", name: "", description: "" }); });
    };

    const handleSaveCaseSubject = () => {
        if (!caseSubjectForm.name) { toast.warning("İsim zorunlu"); return; }
        if (!confirmSimilar(caseSubjectForm.name, caseSubjects)) return;
        runAdd(() => addCaseSubject(caseSubjectForm.name),
            () => { setIsCaseSubjectAddOpen(false); setCaseSubjectForm({ name: "" }); });
    };

    const handleSaveFileType = () => {
        if (!fileTypeForm.name) { toast.warning("İsim zorunlu"); return; }
        if (!confirmSimilar(fileTypeForm.name, fileTypes)) return;
        const code = fileTypeForm.code || fileTypeForm.name.trim();
        runAdd(() => addFileType(code, fileTypeForm.name),
            () => { setIsFileTypeAddOpen(false); setFileTypeForm({ code: "", name: "" }); });
    };

    const handleSaveCourtType = () => {
        if (!courtTypeForm.name || !courtTypeForm.parent_code) { toast.warning("Zorunlu alanlar eksik"); return; }
        if (!confirmSimilar(courtTypeForm.name, courtTypes.filter(c => c.parent_code === courtTypeForm.parent_code))) return;
        const code = courtTypeForm.code || (courtTypeForm.parent_code.slice(0, 3) + "-" + courtTypeForm.name.slice(0, 8)).toUpperCase().replace(/\s/g, "");
        runAdd(() => addCourtType(code, courtTypeForm.name, courtTypeForm.parent_code),
            () => { setIsCourtTypeAddOpen(false); setCourtTypeForm({ code: "", name: "", parent_code: courtTypeForm.parent_code }); });
    };

    const handleSavePartyRole = () => {
        if (!partyRoleForm.name) { toast.warning("İsim zorunlu"); return; }
        if (!confirmSimilar(partyRoleForm.name, partyRoles.filter(r => r.role_type === partyRoleForm.role_type))) return;
        // Aynı ad iki türde de bulunabilir; kod çakışmasın diye üçüncü taraf
        // kodları seed ile aynı biçimde "3-" öneki alır
        const code = partyRoleForm.code || (partyRoleForm.role_type === "THIRD" ? "3-" : "") + partyRoleForm.name.toUpperCase().replace(/\s/g, "-");
        runAdd(() => addPartyRole(code, partyRoleForm.name, partyRoleForm.role_type),
            () => { setIsPartyRoleAddOpen(false); setPartyRoleForm({ code: "", name: "", role_type: "MAIN" }); });
    };

    const handleSaveBureauType = () => {
        if (!bureauTypeForm.name) { toast.warning("İsim zorunlu"); return; }
        if (!confirmSimilar(bureauTypeForm.name, bureauTypes)) return;
        const code = bureauTypeForm.code || bureauTypeForm.name.toUpperCase().replace(/\s/g, "-");
        runAdd(() => addBureauType(code, bureauTypeForm.name),
            () => { setIsBureauTypeAddOpen(false); setBureauTypeForm({ code: "", name: "" }); });
    };

    const handleSaveCity = () => {
        if (!cityForm.name) { toast.warning("İsim zorunlu"); return; }
        if (!confirmSimilar(cityForm.name, cities)) return;
        const code = cityForm.code || cityForm.name.toUpperCase().replace(/\s/g, "-").replace(/İ/g, "I").replace(/Ş/g, "S").replace(/Ğ/g, "G").replace(/Ü/g, "U").replace(/Ö/g, "O").replace(/Ç/g, "C");
        runAdd(() => addCity(code, cityForm.name),
            () => { setIsCityAddOpen(false); setCityForm({ code: "", name: "" }); });
    };

    const handleSaveSpecialty = () => {
        if (!specialtyForm.name) { toast.warning("İsim zorunlu"); return; }
        if (!confirmSimilar(specialtyForm.name, specialties)) return;
        const code = specialtyForm.code || (specialtyForm.name.slice(0, 15).toUpperCase().replace(/\s/g, "-") + "-" + Math.random().toString(36).slice(2, 5).toUpperCase());
        runAdd(() => addSpecialty(code, specialtyForm.name),
            () => { setIsSpecialtyAddOpen(false); setSpecialtyForm({ code: "", name: "" }); });
    };

    const handleSaveClientCategory = () => {
        if (!clientCategoryForm.name) { toast.warning("İsim zorunlu"); return; }
        if (!confirmSimilar(clientCategoryForm.name, clientCategories)) return;
        const code = clientCategoryForm.code || clientCategoryForm.name.toUpperCase().replace(/\s/g, "-").replace(/İ/g, "I").replace(/Ş/g, "S").replace(/Ğ/g, "G").replace(/Ü/g, "U").replace(/Ö/g, "O").replace(/Ç/g, "C");
        runAdd(() => addClientCategory(code, clientCategoryForm.name),
            () => { setIsClientCategoryAddOpen(false); setClientCategoryForm({ code: "", name: "" }); });
    };

    const handleSaveFileStatus = () => {
        if (!fileStatusForm.name) { toast.warning("İsim zorunlu"); return; }
        if (!confirmSimilar(fileStatusForm.name, fileStatuses)) return;
        const code = fileStatusForm.name.toUpperCase().replace(/\s/g, "-").replace(/\//g, "-").replace(/İ/g, "I").replace(/Ş/g, "S").replace(/Ğ/g, "G").replace(/Ü/g, "U").replace(/Ö/g, "O").replace(/Ç/g, "C");
        runAdd(() => addFileStatus(code, fileStatusForm.name),
            () => { setIsFileStatusAddOpen(false); setFileStatusForm({ name: "" }); });
    };

    if (isLoading) {
        return (
            <div>
                <div className="max-w-[1600px] mx-auto flex justify-center py-10">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                </div>
            </div>
        );
    }

    return (
        <div>
            <div className="max-w-[1600px] mx-auto">
                <div className="mb-8 flex items-start justify-between gap-4">
                    <div>
                        <Eyebrow>01 · Yönetim</Eyebrow>
                        <h1 className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium">
                            Yönetim Paneli
                        </h1>
                        <p className="text-[13px] text-[var(--fg-muted)] mt-2 max-w-[60ch] leading-relaxed">
                            Listeleri sürükleyerek sıralayabilirsiniz. Her sekme ayrı bir sözlüğü yönetir.
                        </p>
                    </div>
                    {/* Açık sekmedeki tabloyu Excel'e aktarır; aktarımı olmayan sekmede gizlenir */}
                    {TAB_TO_LIST[activeTab] && (
                        <Button variant="outline" size="sm" className="gap-2 shrink-0" onClick={handleExport} disabled={isExporting}>
                            {isExporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                            Excel'e Aktar
                        </Button>
                    )}
                </div>

                {/* Ortak düzenleme diyaloğu — alanlar listeye göre editFieldsFor'dan gelir */}
                <Dialog open={!!editing} onOpenChange={open => !open && setEditing(null)}>
                    <DialogContent className="max-w-lg">
                        <DialogHeader>
                            <DialogTitle>Düzenle</DialogTitle>
                            <DialogDescription>
                                <span className="font-mono text-xs">{editing?.id}</span>
                                {" — "}Ad değişirse eski adı kullanan dava / müvekkil / belge kayıtları da yeni ada güncellenir.
                            </DialogDescription>
                        </DialogHeader>
                        <div className="grid gap-3 py-2">
                            {editing && editFieldsFor(editing.type).map(field => (
                                <div key={field.key} className="grid grid-cols-4 items-center gap-4">
                                    <Label className="text-right text-xs">{field.label}</Label>
                                    {field.options ? (
                                        <select
                                            className="col-span-3 border rounded px-2 py-1.5 text-sm bg-background text-foreground border-border"
                                            value={editing.values[field.key] ?? ""}
                                            onChange={e => setEditing(p => p ? { ...p, values: { ...p.values, [field.key]: e.target.value } } : null)}
                                        >
                                            <option value="">— Seçiniz —</option>
                                            {field.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                                        </select>
                                    ) : (
                                        <Input
                                            className={`col-span-3 ${field.mono ? "font-mono" : ""}`}
                                            maxLength={field.maxLength}
                                            value={editing.values[field.key] ?? ""}
                                            onChange={e => {
                                                const v = field.format === "title" ? trTitle(e.target.value) : e.target.value;
                                                setEditing(p => p ? { ...p, values: { ...p.values, [field.key]: v } } : null);
                                            }}
                                        />
                                    )}
                                </div>
                            ))}
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setEditing(null)}>İptal</Button>
                            <Button onClick={handleSaveEdit} disabled={isSubmitting}>Kaydet</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>

                {/* Ortak silme diyaloğu — bağlı kayıtları sayar, boşalt/taşı seçtirir */}
                <Dialog open={!!deleting} onOpenChange={open => !open && setDeleting(null)}>
                    <DialogContent className="max-w-lg">
                        <DialogHeader>
                            <DialogTitle>Sil: {deleting?.label}</DialogTitle>
                            <DialogDescription>
                                {usageLoading
                                    ? "Bağlı kayıtlar taranıyor…"
                                    : usage?.total
                                        ? "Bu değer başka kayıtlarda kullanılıyor. Silmeden önce onlara ne olacağını seçin."
                                        : "Bu değer hiçbir kayıtta kullanılmıyor, güvenle silinebilir."}
                            </DialogDescription>
                        </DialogHeader>

                        {usageLoading && (
                            <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
                        )}

                        {!usageLoading && usage && usage.total > 0 && (
                            <div className="space-y-4 py-2">
                                <ul className="text-sm border border-[var(--border)] divide-y divide-[var(--border)]">
                                    {usage.items.map(u => (
                                        <li key={u.label} className="flex justify-between px-3 py-2">
                                            <span className="text-muted-foreground">{u.label}</span>
                                            <span className="font-mono">{u.count}{!u.clearable && <span className="ml-2 text-xs text-amber-600">zorunlu alan</span>}</span>
                                        </li>
                                    ))}
                                </ul>

                                <div className="space-y-2">
                                    <label className={`flex gap-2 items-start text-sm ${usage.clearable ? "" : "opacity-50"}`}>
                                        <input type="radio" className="mt-1" checked={deleteMode === "clear"} disabled={!usage.clearable}
                                            onChange={() => setDeleteMode("clear")} />
                                        <span>
                                            <span className="font-medium">Alanı boşalt</span>
                                            <span className="block text-xs text-muted-foreground">
                                                {usage.clearable
                                                    ? "Bağlı kayıtlarda bu alan boş kalır; kayıtların kendisi silinmez."
                                                    : "Bu değer zorunlu bir alanda kullanıldığı için boşaltılamaz — taşımayı seçin."}
                                            </span>
                                        </span>
                                    </label>
                                    <label className="flex gap-2 items-start text-sm">
                                        <input type="radio" className="mt-1" checked={deleteMode === "reassign"}
                                            onChange={() => setDeleteMode("reassign")} />
                                        <span className="flex-1">
                                            <span className="font-medium">Başka bir değere taşı</span>
                                            <span className="block text-xs text-muted-foreground mb-2">
                                                Bağlı kayıtlar seçtiğiniz kayda aktarılır (aynı değerin iki yazımını birleştirmek için).
                                            </span>
                                            <select
                                                className="w-full border rounded px-2 py-1.5 text-sm bg-background text-foreground border-border"
                                                value={reassignTarget}
                                                onChange={e => { setReassignTarget(e.target.value); setDeleteMode("reassign"); }}
                                            >
                                                <option value="">— Hedef seçin —</option>
                                                {(itemsOfType[deleting?.type ?? ""] ?? [])
                                                    .filter(i => identifierOf(deleting?.type ?? "", i) !== deleting?.id)
                                                    .map(i => {
                                                        const id = identifierOf(deleting?.type ?? "", i);
                                                        // Mahkemelerde aynı ad farklı dava türleri altında olabilir — üst türü de göster
                                                        const label = deleting?.type === "court_types" ? `${i.parent_code} — ${i.name}` : (i.name || i.email);
                                                        return <option key={id} value={id}>{label}</option>;
                                                    })}
                                            </select>
                                        </span>
                                    </label>
                                </div>
                            </div>
                        )}

                        <DialogFooter>
                            <Button variant="outline" onClick={() => setDeleting(null)}>Vazgeç</Button>
                            <Button variant="destructive" onClick={handleConfirmDelete} disabled={isSubmitting || usageLoading || !usage}>Sil</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>

                <Tabs defaultValue="lawyers" className="w-full" onValueChange={v => { setActiveTab(v); setListSearch(""); }}>
                    <TabsList className="flex flex-wrap h-auto gap-1 justify-start mb-6 p-1 bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="lawyers">Avukatlar</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="statuses">Durumlar</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="doctypes">Belge Türleri</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="case_subjects">Dava Konuları</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="emails">E-posta Alıcıları</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="case_types">Dava Türleri</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="court_types">Mahkemeler</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="party_roles">Taraf Rolleri</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="bureau_types">Büro Türleri</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="client_categories">Kategoriler</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="file_statuses">Dosya Durumları</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="specialties">Uzmanlıklar</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="cities">Şehirler</TabsTrigger>
                        <TabsTrigger className="rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase" value="activity_test">Aktivite Raporu Testi</TabsTrigger>
                    </TabsList>

                    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>

                        {/* LAWYERS TAB */}
                        <TabsContent value="lawyers">
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Avukat Listesi</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isLawyerAddOpen} onOpenChange={setIsLawyerAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Avukat</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Avukat Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Kod</Label><Input value={lawyerForm.code} onChange={e => setLawyerForm({ ...lawyerForm, code: e.target.value })} className="col-span-3" placeholder="AGB" /></div>
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">İsim</Label><Input value={lawyerForm.name} onChange={e => setLawyerForm({ ...lawyerForm, name: trTitle(e.target.value) })} className="col-span-3" placeholder="Av. Ahmet Güzel" /></div>
                                                <div className="grid grid-cols-4 items-center gap-4">
                                                    <Label className="text-right">Şehir</Label>
                                                    <select className="col-span-3 border rounded px-2 py-1.5 text-sm bg-background text-foreground border-border" value={lawyerForm.city} onChange={e => setLawyerForm({ ...lawyerForm, city: e.target.value })}>
                                                        <option value="">— Seçiniz —</option>
                                                        {cities.map(c => <option key={c.code} value={c.name ?? ""}>{c.name}</option>)}
                                                    </select>
                                                </div>
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">T.C. No</Label><Input value={lawyerForm.tc_no} onChange={e => setLawyerForm({ ...lawyerForm, tc_no: e.target.value })} className="col-span-3 font-mono" placeholder="00000000000" maxLength={11} /></div>
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Sicil No</Label><Input value={lawyerForm.sicil_no} onChange={e => setLawyerForm({ ...lawyerForm, sicil_no: e.target.value })} className="col-span-3 font-mono" placeholder="12345" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveLawyer} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader>
                                            <TableRow>
                                                <TableHead className="w-[50px]"></TableHead>
                                                <TableHead>Kod</TableHead>
                                                <TableHead>Ad Soyad</TableHead>
                                                <TableHead>Görev</TableHead>
                                                <TableHead>Şehir</TableHead>
                                                <TableHead>T.C. No</TableHead>
                                                <TableHead>Sicil</TableHead>
                                                <TableHead>E-posta</TableHead>
                                                <TableHead>Telefon</TableHead>
                                                {/* Geniş tablo yatay kayabiliyor; işlemler sağda sabit kalsın */}
                                                <TableHead className={STICKY_ACTIONS}>İşlemler</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            <SortableContext items={localLawyers.map(i => i.code ?? "")} strategy={verticalListSortingStrategy}>
                                                {localLawyers.filter(i => trMatch(i.name, listSearch) || trMatch(i.code, listSearch) || trMatch(i.city, listSearch)).map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? ""}>
                                                        <TableCell className="font-mono text-xs text-muted-foreground">{item.code}</TableCell>
                                                        <TableCell className="font-medium whitespace-nowrap">{item.name}</TableCell>
                                                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{item.gorev || <span className="opacity-30">—</span>}</TableCell>
                                                        <TableCell className="text-xs whitespace-nowrap">{item.city || <span className="opacity-30">—</span>}</TableCell>
                                                        <TableCell className="font-mono text-xs">{item.tc_no || <span className="opacity-30">—</span>}</TableCell>
                                                        <TableCell className="font-mono text-xs">{item.sicil_no || <span className="opacity-30">—</span>}</TableCell>
                                                        <TableCell className="text-xs">{item.email || <span className="opacity-30">—</span>}</TableCell>
                                                        <TableCell className="text-xs whitespace-nowrap">{item.phone || <span className="opacity-30">—</span>}</TableCell>
                                                        <TableCell className={STICKY_ACTIONS}>
                                                            <Button variant="ghost" size="icon" onClick={() => openEdit("lawyers", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button>
                                                            <Button variant="ghost" size="icon" onClick={() => openDelete("lawyers", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Durum Listesi</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isStatusAddOpen} onOpenChange={setIsStatusAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Durum</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Durum Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Kod</Label><Input value={statusForm.code} onChange={e => setStatusForm({ ...statusForm, code: trUpper(e.target.value) })} className="col-span-3" /></div>
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Açıklama</Label><Input value={statusForm.name} onChange={e => setStatusForm({ ...statusForm, name: trTitle(e.target.value) })} className="col-span-3" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveStatus} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Kod</TableHead><TableHead>Açıklama</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localStatuses.map(i => i.code ?? "")} strategy={verticalListSortingStrategy}>
                                                {localStatuses.filter(i => trMatch(i.name, listSearch) || trMatch(i.code, listSearch)).map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? ""}>
                                                        <TableCell>{item.code}</TableCell>
                                                        <TableCell>{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => openEdit("statuses", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button><Button variant="ghost" size="icon" onClick={() => openDelete("statuses", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Belge Türleri</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isDocTypeAddOpen} onOpenChange={setIsDocTypeAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Belge Türü</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Belge Türü Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Kod</Label><Input value={docTypeForm.code} onChange={e => setDocTypeForm({ ...docTypeForm, code: trUpper(e.target.value) })} className="col-span-3" /></div>
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Adı</Label><Input value={docTypeForm.name} onChange={e => setDocTypeForm({ ...docTypeForm, name: trTitle(e.target.value) })} className="col-span-3" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveDocType} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Kod</TableHead><TableHead>Açıklama</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localDocTypes.map(i => i.code ?? "")} strategy={verticalListSortingStrategy}>
                                                {localDocTypes.filter(i => trMatch(i.name, listSearch) || trMatch(i.code, listSearch)).map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? ""}>
                                                        <TableCell className="font-medium">{item.code}</TableCell>
                                                        <TableCell>{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => openEdit("doctypes", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button><Button variant="ghost" size="icon" onClick={() => openDelete("doctypes", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Dava Konuları</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isCaseSubjectAddOpen} onOpenChange={setIsCaseSubjectAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Konu</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Dava Konusu Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">İsim</Label><Input value={caseSubjectForm.name} onChange={e => setCaseSubjectForm({ ...caseSubjectForm, name: trTitle(e.target.value) })} className="col-span-3" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveCaseSubject} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Dava Konusu</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localCaseSubjects.map(i => i.code ?? "")} strategy={verticalListSortingStrategy}>
                                                {localCaseSubjects.filter(i => trMatch(i.name, listSearch)).map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? ""}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => openEdit("case_subjects", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button><Button variant="ghost" size="icon" onClick={() => openDelete("case_subjects", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>E-posta Alıcıları</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isEmailAddOpen} onOpenChange={setIsEmailAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni E-posta</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni E-posta Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">İsim</Label><Input value={emailForm.name} onChange={e => setEmailForm({ ...emailForm, name: trTitle(e.target.value) })} className="col-span-3" /></div>
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
                                            <SortableContext items={localEmails.map(i => i.email ?? "")} strategy={verticalListSortingStrategy}>
                                                {localEmails.filter(i => trMatch(i.name, listSearch) || trMatch(i.email, listSearch) || trMatch(i.description, listSearch)).map((item) => (
                                                    <SortableRow key={item.email} id={item.email ?? ""}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell>{item.email}</TableCell>
                                                        <TableCell>{item.description || "-"}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => openEdit("emails", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button>
                                                            <Button variant="ghost" size="icon" onClick={() => openDelete("emails", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Dava Türleri</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isFileTypeAddOpen} onOpenChange={setIsFileTypeAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Tür</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Dava Türü Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={fileTypeForm.name} onChange={e => setFileTypeForm({ ...fileTypeForm, name: trTitle(e.target.value) })} className="col-span-3" placeholder="Ceza" /></div>
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
                                                {localFileTypes.filter(i => trMatch(i.name, listSearch)).map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? item.name}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => openEdit("file_types", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button><Button variant="ghost" size="icon" onClick={() => openDelete("file_types", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div className="flex flex-col gap-2">
                                        <CardTitle>Mahkeme Türleri</CardTitle>
                                        <div><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
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
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Mahkeme Adı</Label><Input value={courtTypeForm.name} onChange={e => setCourtTypeForm({ ...courtTypeForm, name: trTitle(e.target.value) })} className="col-span-3" placeholder="Sulh Hukuk Mahkemesi" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveCourtType} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead>Dava Türü</TableHead><TableHead>Mahkeme Adı</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            {localCourtTypes.filter(i => trMatch(i.name, listSearch) || trMatch(i.parent_code, listSearch)).map((item) => (
                                                <TableRow key={item.code}>
                                                    <TableCell className="text-muted-foreground text-sm">{item.parent_code}</TableCell>
                                                    <TableCell className="font-medium">{item.name}</TableCell>
                                                    <TableCell className="text-right">
                                                        <Button variant="ghost" size="icon" onClick={() => openEdit("court_types", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button><Button variant="ghost" size="icon" onClick={() => openDelete("court_types", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Taraf Rolleri</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isPartyRoleAddOpen} onOpenChange={setIsPartyRoleAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Rol</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Taraf Rolü Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={partyRoleForm.name} onChange={e => setPartyRoleForm({ ...partyRoleForm, name: trTitle(e.target.value) })} className="col-span-3" placeholder="Davacı" /></div>
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
                                                {localPartyRoles.filter(i => trMatch(i.name, listSearch)).map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? item.name}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-xs text-muted-foreground">{item.role_type === "THIRD" ? "Üçüncü Taraf" : "Ana Taraf"}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => openEdit("party_roles", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button><Button variant="ghost" size="icon" onClick={() => openDelete("party_roles", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Büro Özel Türleri</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isBureauTypeAddOpen} onOpenChange={setIsBureauTypeAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Tür</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Büro Türü Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={bureauTypeForm.name} onChange={e => setBureauTypeForm({ ...bureauTypeForm, name: trTitle(e.target.value) })} className="col-span-3" placeholder="Aleyhe" /></div>
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
                                                {localBureauTypes.filter(i => trMatch(i.name, listSearch)).map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? item.name}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => openEdit("bureau_types", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button><Button variant="ghost" size="icon" onClick={() => openDelete("bureau_types", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Müvekkil Kategorileri</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isClientCategoryAddOpen} onOpenChange={setIsClientCategoryAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Kategori</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Kategori Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={clientCategoryForm.name} onChange={e => setClientCategoryForm({ ...clientCategoryForm, name: trTitle(e.target.value) })} className="col-span-3" placeholder="Doktor" /></div>
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
                                                {localClientCategories.filter(i => trMatch(i.name, listSearch)).map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? item.name}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => openEdit("client_categories", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button><Button variant="ghost" size="icon" onClick={() => openDelete("client_categories", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                        </TableCell>
                                                    </SortableRow>
                                                ))}
                                            </SortableContext>
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* DOSYA DURUMLARI TAB */}
                        <TabsContent value="file_statuses">
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Dosya Son Durumları</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isFileStatusAddOpen} onOpenChange={setIsFileStatusAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Durum</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Dosya Durumu Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={fileStatusForm.name} onChange={e => setFileStatusForm({ name: trTitle(e.target.value) })} className="col-span-3" placeholder="Bilirkişide" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveFileStatus} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead className="w-[50px]"></TableHead><TableHead>Ad</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            <SortableContext items={localFileStatuses.map(i => i.code ?? i.name)} strategy={verticalListSortingStrategy}>
                                                {localFileStatuses.filter(i => trMatch(i.name, listSearch)).map((item) => (
                                                    <SortableRow key={item.code} id={item.code ?? item.name}>
                                                        <TableCell className="font-medium">{item.name}</TableCell>
                                                        <TableCell className="text-right">
                                                            <Button variant="ghost" size="icon" onClick={() => openEdit("file_statuses", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button><Button variant="ghost" size="icon" onClick={() => openDelete("file_statuses", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Uzmanlık Alanları</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isSpecialtyAddOpen} onOpenChange={setIsSpecialtyAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Uzmanlık</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Uzmanlık Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={specialtyForm.name} onChange={e => setSpecialtyForm({ ...specialtyForm, name: trTitle(e.target.value) })} className="col-span-3" placeholder="Kardiyoloji" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveSpecialty} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead>Uzmanlık Adı</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            {localSpecialties.filter(i => trMatch(i.name, listSearch)).map((item) => (
                                                <TableRow key={item.code}>
                                                    <TableCell className="font-medium">{item.name}</TableCell>
                                                    <TableCell className="text-right">
                                                        <Button variant="ghost" size="icon" onClick={() => openEdit("specialties", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button><Button variant="ghost" size="icon" onClick={() => openDelete("specialties", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <div>
                                        <CardTitle>Şehir Listesi</CardTitle>
                                        <div className="mt-2"><Input placeholder="Ara..." value={listSearch} onChange={e => setListSearch(e.target.value)} className="max-w-xs" /></div>
                                    </div>
                                    <Dialog open={isCityAddOpen} onOpenChange={setIsCityAddOpen}>
                                        <DialogTrigger asChild><Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> Yeni Şehir</Button></DialogTrigger>
                                        <DialogContent>
                                            <DialogHeader><DialogTitle>Yeni Şehir Ekle</DialogTitle></DialogHeader>
                                            <div className="grid gap-4 py-4">
                                                <div className="grid grid-cols-4 items-center gap-4"><Label className="text-right">Ad</Label><Input value={cityForm.name} onChange={e => setCityForm({ ...cityForm, name: trTitle(e.target.value) })} className="col-span-3" placeholder="İstanbul" /></div>
                                            </div>
                                            <DialogFooter><Button onClick={handleSaveCity} disabled={isSubmitting}>Kaydet</Button></DialogFooter>
                                        </DialogContent>
                                    </Dialog>
                                </CardHeader>
                                <CardContent>
                                    <Table>
                                        <TableHeader><TableRow><TableHead>Şehir</TableHead><TableHead className="text-right">İşlemler</TableHead></TableRow></TableHeader>
                                        <TableBody>
                                            {localCities.filter(i => trMatch(i.name, listSearch)).map((item) => (
                                                <TableRow key={item.code}>
                                                    <TableCell className="font-medium">{item.name}</TableCell>
                                                    <TableCell className="text-right">
                                                        <Button variant="ghost" size="icon" onClick={() => openEdit("cities", item)}><Edit2 className="h-4 w-4 text-muted-foreground" /></Button><Button variant="ghost" size="icon" onClick={() => openDelete("cities", item)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                                                    </TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        </TabsContent>

                    </DndContext>

                    {/* Aktivite Raporu Test Paneli — DnD dışında */}
                    <ActivityTestPanel />

                </Tabs>
            </div>
        </div>
    );
};

// ---------------------------------------------------------------------------
// Aktivite Raporu Test Paneli
// ---------------------------------------------------------------------------
function ActivityTestPanel() {
    const [targetDate, setTargetDate] = useState(() => {
        const d = new Date();
        d.setDate(d.getDate() - 1); // dün
        return d.toISOString().slice(0, 10);
    });
    const [forceEmail, setForceEmail] = useState("");
    const [loading, setLoading] = useState<string | null>(null);
    interface ReportRow {
        id: number;
        report_date: string;
        display?: string;
        user_email?: string;
        is_legacy?: boolean;
        total: number;
        mailed: number;
        unmailed: number;
        acknowledged?: boolean;
    }
    interface TriggerDiagnosis {
        date_range_utc: string;
        total_docs_in_range: number;
        docs_with_email: number;
        docs_without_email: number;
    }
    const [reports, setReports] = useState<ReportRow[]>([]);
    const [triggerResult, setTriggerResult] = useState<string | null>(null);
    const [diagnosis, setDiagnosis] = useState<TriggerDiagnosis | null>(null);
    const [detail, setDetail] = useState<ActivityReport | null>(null);
    const [openingId, setOpeningId] = useState<number | null>(null);

    const callApi = async (endpoint: string, method = "GET", params?: Record<string, string>) => {
        const { apiClient } = await import("@/lib/api");
        let url = endpoint;
        if (params) {
            const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
            if (qs) url += "?" + qs;
        }
        return apiClient.fetch(url, { method });
    };

    const handleTrigger = async () => {
        setLoading("trigger");
        setTriggerResult(null);
        setDiagnosis(null);
        try {
            const params: Record<string, string> = { target_date: targetDate };
            if (forceEmail) params.force_user_email = forceEmail;
            const res = await callApi("/api/activity/admin/trigger", "POST", params);
            const data = await res.json();
            setTriggerResult(data.message || JSON.stringify(data));
            if (data.diagnosis) setDiagnosis(data.diagnosis);
            if (data.success) await handleList();
        } catch (e) {
            setTriggerResult("Hata: " + (e instanceof Error ? e.message : String(e)));
        } finally {
            setLoading(null);
        }
    };

    const handleCatchUp = async () => {
        setLoading("catchup");
        setTriggerResult(null);
        try {
            const res = await callApi("/api/activity/admin/catch-up", "POST");
            const data = await res.json();
            setTriggerResult(data.message || JSON.stringify(data));
            await handleList();
        } catch (e) {
            setTriggerResult("Hata: " + (e instanceof Error ? e.message : String(e)));
        } finally {
            setLoading(null);
        }
    };

    const handleList = async () => {
        setLoading("list");
        try {
            const res = await callApi("/api/activity/admin/list");
            const data = await res.json();
            setReports(Array.isArray(data) ? data : []);
        } catch {
            setReports([]);
        } finally {
            setLoading(null);
        }
    };

    const handleViewDetail = async (reportId: number) => {
        setOpeningId(reportId);
        try {
            const res = await callApi(`/api/activity/admin/report/${reportId}`);
            if (!res.ok) throw new Error("Detay alınamadı");
            const data = await res.json();
            setDetail({
                ...data,
                has_unmailed: data.unmailed_documents > 0,
            } as ActivityReport);
        } catch (e) {
            setTriggerResult("Detay yükleme hatası: " + (e instanceof Error ? e.message : String(e)));
        } finally {
            setOpeningId(null);
        }
    };

    const handleReset = async (date: string) => {
        if (!confirm(`${date} tarihindeki raporlar silinsin mi?`)) return;
        setLoading("reset");
        try {
            const res = await callApi("/api/activity/admin/reset", "DELETE", { target_date: date });
            const data = await res.json();
            setTriggerResult(`${data.deleted_count} rapor silindi (${date})`);
            await handleList();
        } catch (e) {
            setTriggerResult("Hata: " + (e instanceof Error ? e.message : String(e)));
        } finally {
            setLoading(null);
        }
    };

    return (
        <TabsContent value="activity_test">
            <Card>
                <CardHeader>
                    <CardTitle>Aktivite Raporu Test Paneli</CardTitle>
                    <CardDescription>
                        Günlük rapor sistemini test edin. Belirli bir tarihin raporunu elle üretin,
                        geçmiş verileri kontrol edin veya kayıtları sıfırlayın.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">

                    {/* Tetikleyici form */}
                    <div className="rounded-lg border p-4 space-y-4">
                        <p className="text-sm font-medium">Rapor Üret</p>

                        <div className="flex flex-wrap gap-3 items-end">
                            <div className="space-y-1">
                                <Label className="text-xs">Tarih</Label>
                                <Input
                                    type="date"
                                    value={targetDate}
                                    onChange={e => setTargetDate(e.target.value)}
                                    className="w-44"
                                />
                            </div>
                            <div className="space-y-1 flex-1 min-w-52">
                                <Label className="text-xs">
                                    Kullanıcı e-postası <span className="text-muted-foreground">(opsiyonel — eski belgeler için)</span>
                                </Label>
                                <Input
                                    type="email"
                                    placeholder="kullanici@firma.com"
                                    value={forceEmail}
                                    onChange={e => setForceEmail(e.target.value)}
                                />
                            </div>
                            <Button onClick={handleTrigger} disabled={loading !== null}>
                                {loading === "trigger" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                                Rapor Üret
                            </Button>
                        </div>

                        <p className="text-xs text-muted-foreground">
                            <strong>Kullanıcı e-postası boşsa:</strong> Sadece bu kod deploy edildikten sonra
                            yüklenen belgeler (uploaded_by_email dolu olanlar) sayılır.<br />
                            <strong>Kullanıcı e-postası doluysa:</strong> O tarihteki TÜM belgeler o kullanıcıya
                            atanır — eski (deploy öncesi) belgeler için kullanın.
                        </p>
                    </div>

                    {/* Catch-up */}
                    <div className="rounded-lg border p-4 flex items-center justify-between gap-4">
                        <div>
                            <p className="text-sm font-medium">Catch-up Çalıştır</p>
                            <p className="text-xs text-muted-foreground mt-1">
                                Backend restart senaryosunu simüle eder. Son 30 gün içindeki
                                eksik raporları otomatik tamamlar.
                            </p>
                        </div>
                        <Button variant="outline" onClick={handleCatchUp} disabled={loading !== null}>
                            {loading === "catchup" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                            Catch-up Başlat
                        </Button>
                    </div>

                    {/* Sonuç mesajı */}
                    {triggerResult && (
                        <div className="rounded-lg bg-muted px-4 py-3 text-sm font-mono space-y-2">
                            <p>{triggerResult}</p>
                            {diagnosis && (
                                <div className="border-t pt-2 text-xs space-y-1 text-muted-foreground">
                                    <p className="font-semibold text-foreground">Tanı:</p>
                                    <p>Tarih aralığı (UTC): {diagnosis.date_range_utc}</p>
                                    <p>O tarihte toplam belge: <strong>{diagnosis.total_docs_in_range}</strong></p>
                                    <p className="text-green-600 dark:text-green-400">
                                        → E-postası dolu (yeni): {diagnosis.docs_with_email}
                                    </p>
                                    <p className="text-amber-600 dark:text-amber-400">
                                        → E-postası boş (eski belgeler): {diagnosis.docs_without_email}
                                    </p>
                                    {diagnosis.docs_without_email > 0 && !forceEmail && (
                                        <p className="text-red-500 font-medium mt-1">
                                            ⚠ Eski belgeler için yukarıdaki "Kullanıcı e-postası" alanını doldurup tekrar deneyin.
                                        </p>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Rapor listesi */}
                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <p className="text-sm font-medium">Son 30 Günün Raporları</p>
                            <Button variant="ghost" size="sm" onClick={handleList} disabled={loading !== null}>
                                {loading === "list" ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                                Listele
                            </Button>
                        </div>

                        {reports.length > 0 && (
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Tarih</TableHead>
                                        <TableHead>Kullanıcı</TableHead>
                                        <TableHead className="text-center">Toplam</TableHead>
                                        <TableHead className="text-center">Maillenmiş</TableHead>
                                        <TableHead className="text-center">Mailsiz</TableHead>
                                        <TableHead className="text-center">Onaylandı</TableHead>
                                        <TableHead className="text-right">İşlem</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {reports.map(r => (
                                        <TableRow key={r.id}>
                                            <TableCell className="font-mono text-sm">
                                                {r.report_date}
                                            </TableCell>
                                            <TableCell className="text-sm max-w-48 truncate">
                                                {r.display || r.user_email}
                                                {r.is_legacy && (
                                                    <span className="ml-1 text-xs text-amber-500">(eski kayıt)</span>
                                                )}
                                            </TableCell>
                                            <TableCell className="text-center">{r.total}</TableCell>
                                            <TableCell className="text-center text-green-600">{r.mailed}</TableCell>
                                            <TableCell className="text-center text-amber-600">{r.unmailed}</TableCell>
                                            <TableCell className="text-center">
                                                {r.acknowledged
                                                    ? <span className="text-green-600 text-xs">✓ Evet</span>
                                                    : <span className="text-amber-600 text-xs">⏳ Bekliyor</span>
                                                }
                                            </TableCell>
                                            <TableCell className="text-right space-x-1">
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => handleViewDetail(r.id)}
                                                    disabled={loading !== null || openingId !== null}
                                                >
                                                    {openingId === r.id ? (
                                                        <Loader2 className="h-3 w-3 animate-spin" />
                                                    ) : (
                                                        <>
                                                            <Eye className="h-3 w-3 mr-1" />
                                                            Detay
                                                        </>
                                                    )}
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="text-destructive hover:text-destructive"
                                                    onClick={() => handleReset(r.report_date)}
                                                    disabled={loading !== null}
                                                >
                                                    <Trash2 className="h-3 w-3 mr-1" />
                                                    Sil
                                                </Button>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        )}

                        {reports.length === 0 && (
                            <p className="text-xs text-muted-foreground text-center py-4">
                                "Listele" butonuna tıklayın veya rapor üretin.
                            </p>
                        )}
                    </div>
                </CardContent>
            </Card>
            {detail && (
                <ActivityReportModal
                    report={detail}
                    onClose={() => setDetail(null)}
                    readOnly
                />
            )}
        </TabsContent>
    );
}

export default AdminPage;
