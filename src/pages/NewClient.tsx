import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Header } from "@/components/Header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { UserPlus, Save, User, MapPin, Phone, CreditCard, Mail, Edit, Users, Trash2, Tag, Hash, Calendar, Upload, FileText, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
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

import { useClients } from "@/hooks/useClients";
import { validateTCIdentity } from "@/lib/validation";
import { FileUpload } from "@/components/FileUpload";

const TURKEY_CITIES = [
    "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Amasya", "Ankara", "Antalya", "Artvin", "Aydın", "Balıkesir",
    "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum", "Denizli",
    "Diyarbakır", "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari",
    "Hatay", "Isparta", "Mersin", "İstanbul", "İzmir", "Kars", "Kastamonu", "Kayseri", "Kırklareli", "Kırşehir",
    "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa", "Kahramanmaraş", "Mardin", "Muğla", "Muş", "Nevşehir",
    "Niğde", "Ordu", "Rize", "Sakarya", "Samsun", "Siirt", "Sinop", "Sivas", "Tekirdağ", "Tokat",
    "Trabzon", "Tunceli", "Şanlıurfa", "Uşak", "Van", "Yozgat", "Zonguldak", "Aksaray", "Bayburt", "Karaman",
    "Kırıkkale", "Batman", "Şırnak", "Bartın", "Ardahan", "Iğdır", "Yalova", "Karabük", "Kilis", "Osmaniye",
    "Düzce"
].sort((a, b) => a.localeCompare(b, 'tr')); // Alfabetik sıra için sırala

const NewClient = () => {
    const categories = ["Doktor", "Özel Hastane", "Hasta", "Sigorta", "Diğer"];
    const { saveClient, updateClient, deleteClient, getClients, isLoading } = useClients();
    const navigate = useNavigate();
    const location = useLocation();

    // Check if we are in edit mode
    const editModeClient = location.state?.client;
    const isEditMode = !!editModeClient;

    // Determine contact type (Default to Client)
    const initialContactType = location.state?.contact_type || editModeClient?.contact_type || "Client";
    const isClient = initialContactType === "Client";
    const typeLabel = isClient ? "Müvekkil" : "Kişi";

    // Form State
    const [formData, setFormData] = useState({
        name: "",
        tcNo: "",
        phone: "",
        mobile_phone: "",
        email: "",
        address: "",
        notes: "",
        client_type: "Individual", // Default
        category: "",
        cari_kod: "",
        contact_type: initialContactType,
        birth_year: undefined as number | undefined,
        gender: "Belirtilmemiş",
        specialty: ""
    });

    const [tcError, setTcError] = useState<string | null>(null);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);

    useEffect(() => {
        if (editModeClient) {
            // Eğer sadece id ve name geliyorsa (dashboard'dan), API'den tam veriyi çek
            if (editModeClient.id && !editModeClient.phone && !editModeClient.email && !editModeClient.tc_no) {
                const fetchFullClient = async () => {
                    const clients = await getClients();
                    const full = clients?.find((c: { id: number }) => c.id === editModeClient.id);
                    if (full) {
                        setFormData({
                            name: full.name || "",
                            tcNo: full.tc_no || "",
                            phone: full.phone || "",
                            mobile_phone: full.mobile_phone || "",
                            email: full.email || "",
                            address: full.address || "",
                            notes: full.notes || "",
                            client_type: full.client_type || "Individual",
                            category: full.category || "",
                            cari_kod: full.cari_kod || "",
                            contact_type: full.contact_type || "Client",
                            birth_year: full.birth_year,
                            gender: full.gender || "Belirtilmemiş",
                            specialty: full.specialty || ""
                        });
                    } else {
                        // Fallback: sadece gelen veriyi kullan
                        setFormData(prev => ({ ...prev, name: editModeClient.name || "" }));
                    }
                };
                fetchFullClient();
            } else {
                setFormData({
                    name: editModeClient.name || "",
                    tcNo: editModeClient.tc_no || "",
                    phone: editModeClient.phone || "",
                    mobile_phone: editModeClient.mobile_phone || "",
                    email: editModeClient.email || "",
                    address: editModeClient.address || "",
                    notes: editModeClient.notes || "",
                    client_type: editModeClient.client_type || "Individual",
                    category: editModeClient.category || "",
                    cari_kod: editModeClient.cari_kod || "",
                    contact_type: editModeClient.contact_type || "Client",
                    birth_year: editModeClient.birth_year,
                    gender: editModeClient.gender || "Belirtilmemiş",
                    specialty: editModeClient.specialty || ""
                });
            }
        }
    }, [editModeClient, getClients]);

    const handleDelete = async () => {
        if (!isEditMode) return;

        const success = await deleteClient(editModeClient.id);
        if (success) {
            toast.success("Silindi", { description: `${typeLabel} başarıyla silindi.` });
            navigate(-1);
        } else {
            toast.error("Hata", { description: "Silme işlemi başarısız oldu." });
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        const clientData = {
            name: formData.name,
            tc_no: formData.tcNo,
            phone: formData.phone,
            mobile_phone: formData.mobile_phone,
            email: formData.email,
            address: formData.address,
            notes: formData.notes,
            client_type: formData.client_type,
            category: formData.category,
            cari_kod: formData.cari_kod,
            contact_type: formData.contact_type,
            birth_year: formData.birth_year,
            gender: formData.gender === "Belirtilmemiş" ? undefined : formData.gender,
            specialty: formData.category === "Doktor" ? formData.specialty : undefined
        };

        // Final Validation before submit
        const validation = validateTCIdentity(formData.tcNo);
        if (!validation.isValid) {
            setTcError(validation.message);
            toast.error("Form Hatası", { description: "Lütfen TC Kimlik No alanını kontrol ediniz." });
            return;
        }

        let success;

        if (isEditMode) {
            success = await updateClient(editModeClient.id, clientData);
        } else {
            success = await saveClient(clientData);
        }

        if (success) {
            toast.success(isEditMode ? `${typeLabel} güncellendi!` : `${typeLabel} kaydedildi!`, {
                description: `${formData.name} ${isEditMode ? "bilgileri güncellendi" : "sisteme eklendi"}.`
            });

            if (isEditMode) {
                // Return to list after edit
                navigate(-1);
            } else {
                // Reset form after add
                setFormData({
                    name: "",
                    tcNo: "",
                    phone: "",
                    mobile_phone: "",
                    email: "",
                    address: "",
                    notes: "",
                    client_type: "Individual",
                    category: "",
                    cari_kod: "",
                    contact_type: initialContactType,
                    birth_year: undefined,
                    gender: "Belirtilmemiş",
                    specialty: ""
                });
            }
        } else {
            toast.error("Hata oluştu", { description: isEditMode ? "Güncelleme başarısız." : `${typeLabel} kaydedilemedi.` });
        }
    };

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

    return (
        <div className="min-h-screen bg-background">
            <Header />

            <main className="max-w-[1400px] mx-auto px-6 py-8">
                {/* DASHBOARD HEADER */}
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-10">
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
                            {isClient ? "Müvekkil Yönetimi" : "Diğer Kişi Yönetimi"}
                        </h1>
                        <p className="text-sm text-muted-foreground">
                            {isEditMode ? `Mevcut ${typeLabel.toLowerCase()} bilgilerini güncelleyin.` : `Yeni ${typeLabel.toLowerCase()} ekleyin veya iletişim bilgilerini güncelleyin.`}
                        </p>
                    </div>

                    <div className="flex items-center gap-4">
                        <Button
                            type="button"
                            className="w-full sm:w-auto font-semibold shadow-md bg-primary hover:bg-primary/90"
                            onClick={() => document.getElementById("client-file-upload")?.click()}
                        >
                            <Upload className="w-4 h-4 mr-2" />
                            {selectedFile ? "Belge Değiştir" : "Belge Yükle"}
                        </Button>
                        <input
                            id="client-file-upload"
                            type="file"
                            className="hidden"
                            accept=".pdf,.docx,.jpg,.jpeg,.png,.udf"
                            onChange={(e) => {
                                if (e.target.files && e.target.files.length > 0) {
                                    setSelectedFile(e.target.files[0]);
                                }
                            }}
                        />
                    </div>
                </div>

                {/* FILE UPLOAD PREVIEW */}
                {selectedFile && (
                    <div className="mb-8 animate-in fade-in slide-in-from-top-4">
                        <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="bg-primary/20 p-2 rounded">
                                    <FileText className="w-5 h-5 text-primary" />
                                </div>
                                <div className="overflow-hidden">
                                    <h4 className="font-semibold text-sm">Yüklenen Belge</h4>
                                    <p className="text-xs text-muted-foreground truncate" title={selectedFile.name}>{selectedFile.name}</p>
                                </div>
                            </div>
                            <Button variant="outline" size="sm" type="button" onClick={() => setSelectedFile(null)}>Temizle</Button>
                        </div>
                    </div>
                )}

                <form onSubmit={handleSubmit}>
                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                        {/* LEFT COLUMN: PRIMARY INFO */}
                        <div className="lg:col-span-8 space-y-8">

                            {/* 1. KİŞİSEL BİLGİLER */}
                            <Card className="glass-card shadow-lg border-muted/40 overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 delay-75">
                                <div className="bg-muted/5 border-b border-border/40 p-6">
                                    <h3 className="text-sm font-bold flex items-center gap-2 text-primary uppercase tracking-widest">
                                        <User className="w-4 h-4" /> 1. Kişisel Bilgiler
                                    </h3>
                                </div>
                                <CardContent className="p-8 space-y-6">
                                    <div className="grid md:grid-cols-2 gap-x-8 gap-y-6">
                                        <div className="space-y-2 md:col-span-2">
                                            <Label className="flex items-center gap-2">
                                                <User className="w-4 h-4 text-muted-foreground" />
                                                Ad Soyad / Ticari Ünvan
                                            </Label>
                                            <Input
                                                placeholder="Örn: Ahmet Yılmaz veya Yılmaz İnşaat A.Ş."
                                                required
                                                value={formData.name}
                                                onChange={(e) => setFormData({ ...formData, name: toTitleCase(e.target.value) })}
                                                className="text-lg bg-transparent border-border/60"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="flex items-center gap-2">
                                                <Users className="w-4 h-4 text-muted-foreground" />
                                                {typeLabel} Tipi
                                            </Label>
                                            <div className="flex gap-4 h-10 items-center pt-1">
                                                <label className="flex items-center gap-2 cursor-pointer">
                                                    <input
                                                        type="radio"
                                                        name="client_type"
                                                        value="Individual"
                                                        checked={formData.client_type === "Individual"}
                                                        onChange={(e) => setFormData({ ...formData, client_type: e.target.value })}
                                                        className="w-4 h-4 text-primary"
                                                    />
                                                    <span className="text-sm">Şahıs</span>
                                                </label>
                                                <label className="flex items-center gap-2 cursor-pointer">
                                                    <input
                                                        type="radio"
                                                        name="client_type"
                                                        value="Corporate"
                                                        checked={formData.client_type === "Corporate"}
                                                        onChange={(e) => setFormData({ ...formData, client_type: e.target.value })}
                                                        className="w-4 h-4 text-primary"
                                                    />
                                                    <span className="text-sm">Kurum</span>
                                                </label>
                                            </div>
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="flex items-center gap-2">
                                                <CreditCard className="w-4 h-4 text-muted-foreground" />
                                                TC Kimlik / Vergi No
                                            </Label>
                                            <Input
                                                placeholder="11 Haneli TC veya 10 Haneli Vergi No"
                                                value={formData.tcNo}
                                                onChange={(e) => {
                                                    const val = e.target.value;
                                                    if (val === '' || /^\d+$/.test(val)) {
                                                        setFormData({ ...formData, tcNo: val });
                                                        if (tcError) setTcError(null);
                                                    }
                                                }}
                                                onBlur={() => {
                                                    const validation = validateTCIdentity(formData.tcNo);
                                                    setTcError(validation.isValid ? null : validation.message);
                                                }}
                                                className={`bg-transparent border-border/60 ${tcError ? "border-red-500 focus-visible:ring-red-500" : ""}`}
                                            />
                                            {tcError ? (
                                                <p className="text-[10px] font-medium text-red-500 animate-in fade-in slide-in-from-top-1">
                                                    {tcError}
                                                </p>
                                            ) : (
                                                <p className="text-[10px] text-muted-foreground">TC veya Vergi numarası doğrulaması yapılır.</p>
                                            )}
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="flex items-center gap-2">
                                                <Calendar className="w-4 h-4 text-muted-foreground" />
                                                Doğum Yılı
                                            </Label>
                                            <Input
                                                type="number"
                                                placeholder="Örn: 1990"
                                                value={formData.birth_year || ""}
                                                onChange={(e) => {
                                                    const val = e.target.value;
                                                    setFormData({ ...formData, birth_year: val ? parseInt(val) : undefined });
                                                }}
                                                min={1900}
                                                max={new Date().getFullYear()}
                                                className="bg-transparent border-border/60"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="flex items-center gap-2">
                                                <User className="w-4 h-4 text-muted-foreground" />
                                                Cinsiyet
                                            </Label>
                                            <Select
                                                value={formData.gender}
                                                onValueChange={(v) => setFormData({ ...formData, gender: v })}
                                            >
                                                <SelectTrigger className="w-full bg-transparent border-border/60">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="Belirtilmemiş">Belirtilmemiş</SelectItem>
                                                    <SelectItem value="Erkek">Erkek</SelectItem>
                                                    <SelectItem value="Kadın">Kadın</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>

                            {/* 2. İLETİŞİM BİLGİLERİ */}
                            <Card className="glass-card shadow-lg border-muted/40 overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 delay-100">
                                <div className="bg-muted/5 border-b border-border/40 p-6">
                                    <h3 className="text-sm font-bold flex items-center gap-2 text-primary uppercase tracking-widest">
                                        <MapPin className="w-4 h-4" /> 2. İletişim Detayları
                                    </h3>
                                </div>
                                <CardContent className="p-8 space-y-6">
                                    <div className="grid md:grid-cols-2 gap-x-8 gap-y-6">
                                        <div className="space-y-2 md:col-span-2">
                                            <Label className="flex items-center gap-2">
                                                <Mail className="w-4 h-4 text-muted-foreground" />
                                                E-Posta Adresi
                                            </Label>
                                            <Input
                                                type="email"
                                                placeholder="ornek@email.com"
                                                value={formData.email}
                                                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                                                className="bg-transparent border-border/60"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="flex items-center gap-2">
                                                <Phone className="w-4 h-4 text-muted-foreground" />
                                                Sabit Telefon
                                            </Label>
                                            <Input
                                                placeholder="02XX XXX XX XX"
                                                value={formData.phone}
                                                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                                                className="bg-transparent border-border/60"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="flex items-center gap-2">
                                                <Phone className="w-4 h-4 text-muted-foreground" />
                                                Cep Telefonu
                                            </Label>
                                            <Input
                                                placeholder="05XX XXX XX XX"
                                                value={formData.mobile_phone}
                                                onChange={(e) => setFormData({ ...formData, mobile_phone: e.target.value })}
                                                className="bg-transparent border-border/60"
                                            />
                                        </div>

                                        <div className="space-y-2 md:col-span-2">
                                            <Label className="flex items-center gap-2">
                                                <MapPin className="w-4 h-4 text-muted-foreground" />
                                                Şehir
                                            </Label>
                                            <Select
                                                value={formData.address}
                                                onValueChange={(v) => setFormData({ ...formData, address: v })}
                                            >
                                                <SelectTrigger className="w-full bg-transparent border-border/60">
                                                    <SelectValue placeholder="Şehir seçiniz..." />
                                                </SelectTrigger>
                                                <SelectContent className="max-h-[300px]">
                                                    {TURKEY_CITIES.map(city => (
                                                        <SelectItem key={city} value={city}>{city}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </div>

                        {/* RIGHT COLUMN: ADDITIONAL INFO & ACTIONS */}
                        <div className="lg:col-span-4 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500 delay-150">
                            {/* 3. EK BİLGİLER */}
                            <Card className="glass-card shadow-lg border-muted/40 overflow-hidden">
                                <div className="bg-muted/5 border-b border-border/40 p-6">
                                    <h3 className="text-sm font-bold flex items-center gap-2 text-primary uppercase tracking-widest">
                                        <Tag className="w-4 h-4" /> 3. Ek Bilgiler
                                    </h3>
                                </div>
                                <CardContent className="p-8 space-y-6">
                                    <div className="space-y-2">
                                        <Label className="flex items-center gap-2">
                                            <Tag className="w-4 h-4 text-muted-foreground" />
                                            Grup / Kategori
                                        </Label>
                                        <Select
                                            value={formData.category}
                                            onValueChange={(v) => setFormData({ ...formData, category: v })}
                                        >
                                            <SelectTrigger className="w-full bg-transparent border-border/60">
                                                <SelectValue placeholder="Kategori seçiniz..." />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {categories.map(c => (
                                                    <SelectItem key={c} value={c}>{c}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    {formData.category === "Doktor" && (
                                        <div className="space-y-2 animate-in fade-in slide-in-from-top-1 duration-300">
                                            <Label className="flex items-center gap-2">
                                                <Tag className="w-4 h-4 text-muted-foreground" />
                                                Uzmanlık Alanı
                                            </Label>
                                            <Select
                                                value={formData.specialty}
                                                onValueChange={(v) => setFormData({ ...formData, specialty: v })}
                                            >
                                                <SelectTrigger className="w-full bg-transparent border-border/60">
                                                    <SelectValue placeholder="Uzmanlık seçiniz..." />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="Pratisyen">Pratisyen</SelectItem>
                                                    <SelectItem value="Kardiyoloji">Kardiyoloji</SelectItem>
                                                    <SelectItem value="Dahiliye">Dahiliye</SelectItem>
                                                    <SelectItem value="Ortopedi">Ortopedi</SelectItem>
                                                    <SelectItem value="Genel Cerrahi">Genel Cerrahi</SelectItem>
                                                    <SelectItem value="Kadın Doğum">Kadın Doğum</SelectItem>
                                                    <SelectItem value="Göz Hastalıkları">Göz Hastalıkları</SelectItem>
                                                    <SelectItem value="Diş Hekimi">Diş Hekimi</SelectItem>
                                                    <SelectItem value="Diğer">Diğer</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    )}


                                    <div className="space-y-2">
                                        <Label>Özel Notlar</Label>
                                        <Textarea
                                            placeholder={`${typeLabel} hakkında hatırlatmalar...`}
                                            className="h-24 bg-transparent border-border/60"
                                            value={formData.notes}
                                            onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                                        />
                                    </div>
                                </CardContent>
                            </Card>

                            {/* 4. İŞLEMLER */}
                            <Card className="glass-card shadow-lg border-primary/20 bg-primary/5 sticky top-24">
                                <CardHeader className="pb-4">
                                    <CardTitle className="text-lg">İşlemi Tamamla</CardTitle>
                                    <CardDescription>Bilgileri doğruladıktan sonra kaydedin.</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <Button type="submit" className="w-full font-bold shadow-md h-12" disabled={isLoading}>
                                        {isLoading ? (
                                            <>Kaydediliyor...</>
                                        ) : (
                                            <>
                                                <Save className="w-5 h-5 mr-2" />
                                                {isEditMode ? "Güncelle" : `${typeLabel} Kaydet`}
                                            </>
                                        )}
                                    </Button>
                                    <Button type="button" variant="outline" className="w-full h-10 border-border/50 hover:bg-muted" onClick={() => navigate(-1)}>
                                        İptal
                                    </Button>

                                    {isEditMode && (
                                        <AlertDialog>
                                            <AlertDialogTrigger asChild>
                                                <Button variant="ghost" type="button" className="w-full h-10 text-destructive hover:text-destructive hover:bg-destructive/10 mt-2">
                                                    <Trash2 className="w-4 h-4 mr-2" />
                                                    Kaydı Sil
                                                </Button>
                                            </AlertDialogTrigger>
                                            <AlertDialogContent>
                                                <AlertDialogHeader>
                                                    <AlertDialogTitle>Emin misiniz?</AlertDialogTitle>
                                                    <AlertDialogDescription>
                                                        Bu işlem geri alınamaz. Bu {typeLabel.toLowerCase()} kalıcı olarak sunucularımızdan silinecektir.
                                                    </AlertDialogDescription>
                                                </AlertDialogHeader>
                                                <AlertDialogFooter>
                                                    <AlertDialogCancel>İptal</AlertDialogCancel>
                                                    <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Sil</AlertDialogAction>
                                                </AlertDialogFooter>
                                            </AlertDialogContent>
                                        </AlertDialog>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    </div>
                </form>
            </main>
        </div>
    );
};

export default NewClient;
