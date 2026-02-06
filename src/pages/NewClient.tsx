import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Header } from "@/components/Header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { UserPlus, Save, User, MapPin, Phone, CreditCard, Mail, Edit, Users } from "lucide-react";
import { toast } from "sonner";

import { useClients } from "@/hooks/useClients";
import { validateTCIdentity } from "@/lib/validation";
import { FileUpload } from "@/components/FileUpload";

const NewClient = () => {
    const { saveClient, updateClient, isLoading } = useClients();
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
        email: "",
        address: "",
        notes: "",
        client_type: "Individual", // Default
        category: "",
        contact_type: initialContactType
    });

    const [tcError, setTcError] = useState<string | null>(null);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);

    useEffect(() => {
        if (editModeClient) {
            setFormData({
                name: editModeClient.name || "",
                tcNo: editModeClient.tc_no || "",
                phone: editModeClient.phone || "",
                email: editModeClient.email || "",
                address: editModeClient.address || "",
                notes: editModeClient.notes || "",
                client_type: editModeClient.client_type || "Individual",
                category: editModeClient.category || "",
                contact_type: editModeClient.contact_type || "Client"
            });
        }
    }, [editModeClient]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        const clientData = {
            name: formData.name,
            tc_no: formData.tcNo,
            phone: formData.phone,
            email: formData.email,
            address: formData.address,
            notes: formData.notes,
            client_type: formData.client_type,
            category: formData.category,
            contact_type: formData.contact_type
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
                    email: "",
                    address: "",
                    notes: "",
                    client_type: "Individual",
                    category: "",
                    contact_type: initialContactType
                });
            }
        } else {
            toast.error("Hata oluştu", { description: isEditMode ? "Güncelleme başarısız." : `${typeLabel} kaydedilemedi.` });
        }
    };

    return (
        <div className="min-h-screen bg-background">
            <Header />

            <main className="container max-w-4xl mx-auto px-6 py-8">
                <div className="mb-8 text-center space-y-2">
                    <h1 className="text-3xl font-bold tracking-tight text-primary">
                        {isClient ? "Müvekkil Yönetimi" : "Diğer Kişi Yönetimi"}
                    </h1>
                    <p className="text-muted-foreground">
                        {isEditMode ? `Mevcut ${typeLabel.toLowerCase()} bilgilerini güncelleyin.` : `Yeni ${typeLabel.toLowerCase()} ekleyin veya iletişim bilgilerini güncelleyin.`}
                    </p>
                </div>

                <form onSubmit={handleSubmit}>
                    <div className="mb-8">
                        <FileUpload
                            onFileSelect={(file) => {
                                if (Array.isArray(file)) {
                                    setSelectedFile(file[0]);
                                } else {
                                    setSelectedFile(file);
                                }
                            }}
                            selectedFile={selectedFile}
                            onClearFile={() => setSelectedFile(null)}
                            title={`${typeLabel} Belgesi Yükle`}
                            description="Bilgileri otomatik doldurmak için belge yükleyiniz (Opsiyonel)"
                            uploadText="Belge Yükle"
                        />
                    </div>

                    <Card className="glass-card shadow-lg border-muted/40 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <CardHeader className="bg-muted/5 border-b border-border/50 pb-6">
                            <div className="flex items-center justify-between">
                                <div className="space-y-1">
                                    <CardTitle className="flex items-center gap-2 text-xl">
                                        {isEditMode ? <Edit className="w-5 h-5 text-primary" /> : (isClient ? <UserPlus className="w-5 h-5 text-primary" /> : <Users className="w-5 h-5 text-primary" />)}
                                        {isEditMode ? `${typeLabel} Düzenle` : `${typeLabel} Kartı`}
                                    </CardTitle>
                                    <CardDescription>
                                        {isEditMode ? "Aşağıdaki bilgileri düzenleyip kaydedin" : "Kişisel ve iletişim bilgilerini giriniz"}
                                    </CardDescription>
                                </div>
                            </div>
                        </CardHeader>

                        <CardContent className="p-8 space-y-8">
                            {/* KİŞİSEL BİLGİLER */}
                            <div className="grid md:grid-cols-2 gap-6">
                                <div className="space-y-2 md:col-span-2">
                                    <Label className="flex items-center gap-2">
                                        <User className="w-4 h-4 text-muted-foreground" />
                                        Ad Soyad / Ticari Ünvan
                                    </Label>
                                    <Input
                                        placeholder="Örn: Ahmet Yılmaz veya Yılmaz İnşaat A.Ş."
                                        required
                                        value={formData.name}
                                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                        className="text-lg"
                                    />
                                </div>

                                <div className="space-y-2">
                                    <Label>{typeLabel} Tipi</Label>
                                    <div className="flex gap-4 pt-1">
                                        <label className="flex items-center gap-2 cursor-pointer">
                                            <input
                                                type="radio"
                                                name="client_type"
                                                value="Individual"
                                                checked={formData.client_type === "Individual"}
                                                onChange={(e) => setFormData({ ...formData, client_type: e.target.value })}
                                                className="w-4 h-4 text-primary"
                                            />
                                            <span>Gerçek Kişi</span>
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
                                            <span>Tüzel Kişi</span>
                                        </label>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label>Grup / Kategori</Label>
                                    <Input
                                        placeholder="Örn: Sigorta, Özel, Şirketler..."
                                        value={formData.category}
                                        onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                                    />
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
                                            // Only allow digits
                                            if (val === '' || /^\d+$/.test(val)) {
                                                setFormData({ ...formData, tcNo: val });
                                                // Clear error when user changes input, or validate immediately
                                                if (tcError) setTcError(null);
                                            }
                                        }}
                                        onBlur={() => {
                                            const validation = validateTCIdentity(formData.tcNo);
                                            setTcError(validation.isValid ? null : validation.message);
                                        }}
                                        className={tcError ? "border-red-500 focus-visible:ring-red-500" : ""}
                                    />
                                    {tcError && (
                                        <p className="text-sm font-medium text-red-500 animate-in fade-in slide-in-from-top-1">
                                            {tcError}
                                        </p>
                                    )}
                                </div>

                                <div className="space-y-2">
                                    <Label className="flex items-center gap-2">
                                        <Mail className="w-4 h-4 text-muted-foreground" />
                                        E-Posta Adresi
                                    </Label>
                                    <Input
                                        type="email"
                                        placeholder="ornek@email.com"
                                        value={formData.email}
                                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                                    />
                                </div>
                            </div>

                            <Separator />

                            {/* İLETİŞİM BİLGİLERİ */}
                            <div className="space-y-4">
                                <h3 className="text-sm font-semibold flex items-center gap-2 text-muted-foreground uppercase tracking-wider">
                                    <MapPin className="w-4 h-4" /> İletişim Detayları
                                </h3>

                                <div className="grid md:grid-cols-2 gap-6">
                                    <div className="space-y-2">
                                        <Label className="flex items-center gap-2">
                                            <Phone className="w-4 h-4 text-muted-foreground" />
                                            Telefon Numarası
                                        </Label>
                                        <Input
                                            placeholder="05XX XXX XX XX"
                                            value={formData.phone}
                                            onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                                        />
                                    </div>
                                    <div className="space-y-2 md:col-span-2">
                                        <Label className="flex items-center gap-2">
                                            <MapPin className="w-4 h-4 text-muted-foreground" />
                                            Adres
                                        </Label>
                                        <Textarea
                                            placeholder="Tam açık adres..."
                                            className="h-24"
                                            value={formData.address}
                                            onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                                        />
                                    </div>
                                    <div className="space-y-2 md:col-span-2">
                                        <Label>Özel Notlar</Label>
                                        <Textarea
                                            placeholder={`${typeLabel} hakkında hatırlatmalar...`}
                                            className="h-20"
                                            value={formData.notes}
                                            onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                                        />
                                    </div>
                                </div>
                            </div>
                        </CardContent>

                        {/* FOOTER ACTION */}
                        <div className="bg-muted/5 border-t border-border p-6 flex justify-end gap-4">
                            <Button type="button" variant="outline" size="lg" onClick={() => navigate(-1)}>İptal</Button>
                            <Button type="submit" size="lg" className="px-8 font-semibold shadow-lg bg-primary hover:bg-primary/90 text-white" disabled={isLoading}>
                                {isLoading ? (
                                    <>Kaydediliyor...</>
                                ) : (
                                    <>
                                        <Save className="w-4 h-4 mr-2" />
                                        {isEditMode ? "Güncelle" : `${typeLabel} Kaydet`}
                                    </>
                                )}
                            </Button>
                        </div>
                    </Card>
                </form>
            </main>
        </div>
    );
};

export default NewClient;
