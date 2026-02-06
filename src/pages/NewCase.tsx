import { useState } from "react";
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
import { Gavel, User, FileText, Scale, Save, Briefcase, Building, Search, RefreshCw, Sparkles, Loader2, Upload, Check, ChevronsUpDown } from "lucide-react";
import { toast } from "sonner";
import { FileUpload } from "@/components/FileUpload";

// Mock Data
const DOSYA_TURLERI = ["Hukuk Dava", "Ceza Dava", "İcra", "İdare", "Vergi", "Değişik İş"];
const MAHKEME_TURLERI = ["Asliye Hukuk", "Tüketici", "Sulh Hukuk", "Aile", "İş", "Ticaret", "İcra Hukuk"];
const KATEGORILER = ["Genel", "Özel Müvekkil", "Sigorta (AXA)", "Ticari Danışmanlık", "Ceza Dosyaları"];
const AVUKATLAR = ["İlke Berk", "Ahmet Yılmaz", "Ayşe Demir", "Stajyer Mehmet"];
const TARAF_ROLLERI = ["Davacı", "Davalı", "Müşteki", "Sanık", "İhbar Olunan", "Müdahil"];
const UCUNCU_TARAF_ROLLERI = ["Tanık", "Bilirkişi", "Uzman", "Arabulucu", "Diğer"];
const DAVA_KONULARI = [
    "Alacak Davası",
    "Tazminat Davası",
    "İşe İade Davası",
    "Nafaka Davası",
    "Boşanma Davası",
    "Tahliye Davası",
    "Ayıplı Mal - Bedel İadesi",
    "İstihkak Davası",
    "Menfi Tespit Davası",
    "Ecrimisil Davası"
    // Kullanıcı gerçek listeyi verdiğinde bu liste güncellenecek
];

const NewCase = () => {
    // Generate a random mock case ID for display
    const [caseId, setCaseId] = useState(`2024/${Math.floor(Math.random() * 10000).toString().padStart(4, '0')}`);
    const [isLoading, setIsLoading] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");

    // Form States
    const [formData, setFormData] = useState({
        fileType: "",
        subType: "",
        subject: "",
        court: "",
        category: "",
        lawyer: "",
        uyapLawyer: "",
        esasNo: "",
        merciNo: "",
        fileOpeningDate: "",
        maddiTazminat: "",
        maneviTazminat: ""
    });

    // Multiple Clients (Müvekkil, Müdahil, etc.)
    const [clients, setClients] = useState<Array<{ name: string; role: string }>>([
        { name: "", role: "Davacı" }
    ]);

    // Multiple Counter-Parties (Karşı Taraf)
    const [counterParties, setCounterParties] = useState<Array<{ name: string; role: string }>>([
        { name: "", role: "Davalı" }
    ]);

    // Third Parties (Tanık, Bilirkişi, etc.)
    const [thirdParties, setThirdParties] = useState<Array<{ name: string; role: string }>>([]);

    // Combobox state for searchable subject dropdown
    const [subjectComboboxOpen, setSubjectComboboxOpen] = useState(false);

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
                category: "Genel",
                lawyer: "İlke Berk",
                uyapLawyer: "Av. Mehmet Demir",
                esasNo: "2024/111", // Extracted from doc
                merciNo: "1", // Merci numarası
                fileOpeningDate: new Date().toISOString().split('T')[0], // Set to today's date
                maddiTazminat: "",
                maneviTazminat: ""
            });

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

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);

        // Mock save delay
        setTimeout(() => {
            setIsLoading(false);
            toast.success("Dava kartı güncellendi!", {
                description: `Dosya No: ${caseId} bilgileri kaydedildi.`
            });
        }, 1500);
    };

    return (
        <div className="min-h-screen bg-background">
            <Header />

            <main className="container max-w-4xl mx-auto px-6 py-8">
                <div className="mb-8 text-center space-y-2">
                    <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
                        Dava Kartı Yönetimi
                    </h1>
                    <p className="text-muted-foreground">
                        Yeni dava açın veya mevcut dosyaları arayıp eksik bilgileri tamamlayın.
                    </p>
                </div>

                {/* SEARCH SECTION */}
                <div className="grid md:grid-cols-3 gap-6 mb-8">
                    <div className="md:col-span-2 space-y-4">
                        <Label className="text-muted-foreground font-semibold">Mevcut Dosya Sorgulama</Label>
                        <Card className="glass-card">
                            <CardContent className="p-4 flex gap-4 items-center">
                                <Search className="w-5 h-5 text-muted-foreground" />
                                <Input
                                    placeholder="Dosya No (2023/123) veya Müvekkil..."
                                    className="border-0 bg-transparent focus-visible:ring-0 text-lg"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                />
                                <Button variant="secondary" onClick={handleSearch} disabled={isLoading}>
                                    {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : "Bul"}
                                </Button>
                            </CardContent>
                        </Card>
                    </div>

                    <div className="space-y-4">
                        <Label className="text-muted-foreground font-semibold flex items-center gap-2">
                            <Sparkles className="w-4 h-4 text-primary" />
                            Otomatik Dava Açılışı
                        </Label>
                        <Button
                            className="w-full h-[72px] text-lg font-semibold shadow-lg bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 transition-all hover:scale-[1.02]"
                            onClick={() => document.getElementById("case-file-upload")?.click()}
                            disabled={isAnalyzing}
                        >
                            {isAnalyzing ? (
                                <>
                                    <Loader2 className="w-5 h-5 mr-3 animate-spin" />
                                    Analiz Ediliyor...
                                </>
                            ) : (
                                <>
                                    <Upload className="w-6 h-6 mr-3" />
                                    Belge Yükle ({selectedFiles.length})
                                </>
                            )}
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
                                            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}


                <form onSubmit={handleSubmit}>
                    <Card className="glass-card shadow-lg border-muted/40 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <CardHeader className="bg-muted/5 border-b border-border/50 pb-6">
                            <div className="flex items-center justify-between">
                                <div className="space-y-1">
                                    <CardTitle className="flex items-center gap-2 text-xl">
                                        <Gavel className="w-5 h-5 text-primary" />
                                        Dava Künyesi
                                    </CardTitle>
                                    <CardDescription>
                                        Eksik bilgileri daha sonra tamamlayabilirsiniz.
                                    </CardDescription>
                                </div>
                                <div className="bg-primary/10 px-4 py-2 rounded-full border border-primary/20">
                                    <span className="text-sm font-semibold text-primary block text-center text-xs uppercase tracking-wider opacity-70">
                                        Özel No
                                    </span>
                                    <span className="text-lg font-mono font-bold text-foreground">
                                        {caseId}
                                    </span>
                                </div>
                            </div>
                        </CardHeader>

                        <CardContent className="p-8 space-y-8">
                            {/* BÖLÜM 1: TEMEL BİLGİLER */}
                            <div className="grid md:grid-cols-2 gap-6">
                                <div className="space-y-2">
                                    <Label className="flex items-center gap-2">
                                        <FileText className="w-4 h-4 text-muted-foreground" />
                                        Esas No (Mahkeme)
                                    </Label>
                                    <Input
                                        placeholder="Örn: 2024/123"
                                        value={formData.esasNo}
                                        onChange={(e) => setFormData({ ...formData, esasNo: e.target.value })}
                                        className="text-lg font-mono"
                                    />
                                </div>

                                <div className="space-y-2">
                                    <Label className="flex items-center gap-2">
                                        <FileText className="w-4 h-4 text-muted-foreground" />
                                        Merci No
                                    </Label>
                                    <Input
                                        placeholder="Örn: 1"
                                        value={formData.merciNo}
                                        onChange={(e) => setFormData({ ...formData, merciNo: e.target.value })}
                                        className="text-lg font-mono"
                                    />
                                </div>

                                <div className="space-y-2 md:col-span-2">
                                    <Label className="flex items-center gap-2">
                                        <FileText className="w-4 h-4 text-muted-foreground" />
                                        Dosya Açılış Tarihi
                                    </Label>
                                    <Input
                                        type="date"
                                        value={formData.fileOpeningDate}
                                        onChange={(e) => setFormData({ ...formData, fileOpeningDate: e.target.value })}
                                        className="text-lg"
                                    />
                                </div>

                                <div className="space-y-2">
                                    <Label className="flex items-center gap-2">
                                        <FileText className="w-4 h-4 text-muted-foreground" />
                                        Dosya Türü
                                    </Label>
                                    <Select value={formData.fileType} onValueChange={(v) => setFormData({ ...formData, fileType: v })}>
                                        <SelectTrigger>
                                            <SelectValue placeholder="Seçiniz..." />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {DOSYA_TURLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-2">
                                    <Label className="flex items-center gap-2">
                                        <Scale className="w-4 h-4 text-muted-foreground" />
                                        Alt Tür
                                    </Label>
                                    <Select value={formData.subType} onValueChange={(v) => setFormData({ ...formData, subType: v })}>
                                        <SelectTrigger>
                                            <SelectValue placeholder="Seçiniz..." />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {MAHKEME_TURLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-2 md:col-span-2">
                                    <Label className="flex items-center gap-2">
                                        <Scale className="w-4 h-4 text-muted-foreground" />
                                        Davanın Konusu
                                    </Label>
                                    <Popover open={subjectComboboxOpen} onOpenChange={setSubjectComboboxOpen}>
                                        <PopoverTrigger asChild>
                                            <Button
                                                variant="outline"
                                                role="combobox"
                                                aria-expanded={subjectComboboxOpen}
                                                className="w-full justify-between text-lg font-normal"
                                            >
                                                {formData.subject || "Dava konusunu seçin veya arayın..."}
                                                <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                            </Button>
                                        </PopoverTrigger>
                                        <PopoverContent className="w-full p-0" align="start">
                                            <Command>
                                                <CommandInput placeholder="Dava konusu ara..." />
                                                <CommandEmpty>Sonuç bulunamadı.</CommandEmpty>
                                                <CommandGroup className="max-h-64 overflow-auto">
                                                    {DAVA_KONULARI.map((konu) => (
                                                        <CommandItem
                                                            key={konu}
                                                            value={konu}
                                                            onSelect={(currentValue) => {
                                                                setFormData({ ...formData, subject: currentValue === formData.subject ? "" : currentValue });
                                                                setSubjectComboboxOpen(false);
                                                            }}
                                                        >
                                                            <Check
                                                                className={`mr-2 h-4 w-4 ${formData.subject === konu ? "opacity-100" : "opacity-0"}`}
                                                            />
                                                            {konu}
                                                        </CommandItem>
                                                    ))}
                                                </CommandGroup>
                                            </Command>
                                        </PopoverContent>
                                    </Popover>
                                </div>
                            </div>

                            <Separator />

                            {/* BÖLÜM 2: TARAFLAR */}
                            <div className="space-y-4">
                                <h3 className="text-sm font-semibold flex items-center gap-2 text-muted-foreground uppercase tracking-wider">
                                    <User className="w-4 h-4" /> Taraf Bilgileri
                                </h3>

                                {/* Müvekkil / Clients Section */}
                                <div className="mb-2">
                                    <h4 className="text-sm font-medium text-muted-foreground">Müvekkil Tarafı</h4>
                                </div>

                                {clients.map((client, index) => (
                                    <div key={index} className="relative grid md:grid-cols-12 gap-4 items-end bg-muted/20 p-4 rounded-lg border border-dashed border-muted-foreground/20">
                                        {index === 0 && (
                                            <button
                                                type="button"
                                                onClick={() => setClients([...clients, { name: "", role: "Müdahil" }])}
                                                className="absolute top-2 right-2 h-6 w-6 rounded-full hover:bg-muted flex items-center justify-center transition-colors z-10"
                                                title="Ek Müvekkil Ekle"
                                            >
                                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                                    <path d="M5 12h14" />
                                                    <path d="M12 5v14" />
                                                </svg>
                                            </button>
                                        )}
                                        <div className="md:col-span-4 space-y-2">
                                            <Label>{index === 0 ? "Müvekkil Adı / Ünvanı" : `Ek Müvekkil ${index}`}</Label>
                                            <Input
                                                placeholder="Örn: Ahmet Yılmaz"
                                                value={client.name}
                                                onChange={(e) => {
                                                    const updated = [...clients];
                                                    updated[index].name = e.target.value;
                                                    setClients(updated);
                                                }}
                                            />
                                        </div>
                                        <div className="md:col-span-3 space-y-2">
                                            <Label>Sıfatı</Label>
                                            <Select
                                                value={client.role}
                                                onValueChange={(v) => {
                                                    const updated = [...clients];
                                                    updated[index].role = v;
                                                    setClients(updated);
                                                }}
                                            >
                                                <SelectTrigger>
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {TARAF_ROLLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="md:col-span-5 flex items-end justify-end gap-2">
                                            {index === 0 && (
                                                <div className="text-xs text-muted-foreground flex-1">
                                                    Müvekkil firmalar için tam ticari ünvan girilmesi önerilir.
                                                </div>
                                            )}
                                            {index > 0 && (
                                                <Button
                                                    type="button"
                                                    variant="destructive"
                                                    size="sm"
                                                    onClick={() => setClients(clients.filter((_, i) => i !== index))}
                                                >
                                                    Sil
                                                </Button>
                                            )}
                                        </div>
                                    </div>
                                ))}

                                {/* Karşı Taraf / Counter Parties Section */}
                                <div className="mb-2 mt-6">
                                    <h4 className="text-sm font-medium text-muted-foreground">Karşı Taraf</h4>
                                </div>

                                {counterParties.map((party, index) => (
                                    <div key={index} className="relative grid md:grid-cols-12 gap-4 items-end bg-muted/20 p-4 rounded-lg border border-dashed border-muted-foreground/20">
                                        {index === 0 && (
                                            <button
                                                type="button"
                                                onClick={() => setCounterParties([...counterParties, { name: "", role: "Davalı" }])}
                                                className="absolute top-2 right-2 h-6 w-6 rounded-full hover:bg-muted flex items-center justify-center transition-colors z-10"
                                                title="Ek Karşı Taraf Ekle"
                                            >
                                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                                    <path d="M5 12h14" />
                                                    <path d="M12 5v14" />
                                                </svg>
                                            </button>
                                        )}
                                        <div className="md:col-span-4 space-y-2">
                                            <Label>{index === 0 ? "Karşı Taraf" : `Ek Karşı Taraf ${index}`}</Label>
                                            <Input
                                                placeholder="Örn: XYZ İnşaat Ltd. Şti."
                                                value={party.name}
                                                onChange={(e) => {
                                                    const updated = [...counterParties];
                                                    updated[index].name = e.target.value;
                                                    setCounterParties(updated);
                                                }}
                                            />
                                        </div>
                                        <div className="md:col-span-3 space-y-2">
                                            <Label>Sıfatı</Label>
                                            <Select
                                                value={party.role}
                                                onValueChange={(v) => {
                                                    const updated = [...counterParties];
                                                    updated[index].role = v;
                                                    setCounterParties(updated);
                                                }}
                                            >
                                                <SelectTrigger>
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {TARAF_ROLLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="md:col-span-5 flex items-end justify-end">
                                            {index > 0 && (
                                                <Button
                                                    type="button"
                                                    variant="destructive"
                                                    size="sm"
                                                    onClick={() => setCounterParties(counterParties.filter((_, i) => i !== index))}
                                                >
                                                    Sil
                                                </Button>
                                            )}
                                        </div>
                                    </div>
                                ))}

                                {/* Üçüncü Taraflar / Third Parties Section */}
                                <div className="mb-2 mt-6">
                                    <h4 className="text-sm font-medium text-muted-foreground">Üçüncü Taraflar (Tanık, Bilirkişi, vb.)</h4>
                                </div>

                                {thirdParties.length === 0 ? (
                                    <div className="relative bg-amber-50/50 dark:bg-amber-950/20 p-8 rounded-lg border border-amber-200 dark:border-amber-800 border-dashed">
                                        <button
                                            type="button"
                                            onClick={() => setThirdParties([...thirdParties, { name: "", role: "Tanık" }])}
                                            className="absolute top-2 right-2 h-6 w-6 rounded-full hover:bg-amber-100 dark:hover:bg-amber-900 flex items-center justify-center transition-colors z-10"
                                            title="Üçüncü Taraf Ekle"
                                        >
                                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                                <path d="M5 12h14" />
                                                <path d="M12 5v14" />
                                            </svg>
                                        </button>
                                        <p className="text-sm text-muted-foreground text-center">Üçüncü taraf eklemek için + butonuna tıklayın</p>
                                    </div>
                                ) : (
                                    thirdParties.map((party, index) => (
                                        <div key={index} className="relative grid md:grid-cols-12 gap-4 items-end bg-amber-50/50 dark:bg-amber-950/20 p-4 rounded-lg border border-amber-200 dark:border-amber-800">
                                            {index === 0 && (
                                                <button
                                                    type="button"
                                                    onClick={() => setThirdParties([...thirdParties, { name: "", role: "Tanık" }])}
                                                    className="absolute top-2 right-2 h-6 w-6 rounded-full hover:bg-amber-100 dark:hover:bg-amber-900 flex items-center justify-center transition-colors z-10"
                                                    title="Üçüncü Taraf Ekle"
                                                >
                                                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                                        <path d="M5 12h14" />
                                                        <path d="M12 5v14" />
                                                    </svg>
                                                </button>
                                            )}
                                            <div className="md:col-span-4 space-y-2">
                                                <Label className="text-amber-700 dark:text-amber-400">Üçüncü Taraf {index + 1}</Label>
                                                <Input
                                                    placeholder="İsim / Ünvan"
                                                    value={party.name}
                                                    onChange={(e) => {
                                                        const updated = [...thirdParties];
                                                        updated[index].name = e.target.value;
                                                        setThirdParties(updated);
                                                    }}
                                                />
                                            </div>
                                            <div className="md:col-span-3 space-y-2">
                                                <Label className="text-amber-700 dark:text-amber-400">Sıfatı</Label>
                                                <Select
                                                    value={party.role}
                                                    onValueChange={(v) => {
                                                        const updated = [...thirdParties];
                                                        updated[index].role = v;
                                                        setThirdParties(updated);
                                                    }}
                                                >
                                                    <SelectTrigger>
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {UCUNCU_TARAF_ROLLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                            <div className="md:col-span-5 flex items-end justify-end">
                                                <Button
                                                    type="button"
                                                    variant="destructive"
                                                    size="sm"
                                                    onClick={() => setThirdParties(thirdParties.filter((_, i) => i !== index))}
                                                >
                                                    Sil
                                                </Button>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>

                            <Separator />

                            {/* BÖLÜM 3: TAZMİNAT TALEPLERİ */}
                            <div className="space-y-4">
                                <h3 className="text-sm font-semibold flex items-center gap-2 text-muted-foreground uppercase tracking-wider">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4"><line x1="12" x2="12" y1="2" y2="22" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" /></svg>
                                    Tazminat Talepleri
                                </h3>

                                <div className="grid md:grid-cols-2 gap-6">
                                    <div className="space-y-2">
                                        <Label className="flex items-center gap-2">
                                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 text-muted-foreground"><rect width="20" height="14" x="2" y="5" rx="2" /><line x1="2" x2="22" y1="10" y2="10" /></svg>
                                            Maddi Tazminat
                                        </Label>
                                        <div className="relative">
                                            <Input
                                                type="text"
                                                placeholder="0"
                                                value={formData.maddiTazminat ? Number(formData.maddiTazminat).toLocaleString('tr-TR') : ''}
                                                onChange={(e) => {
                                                    const value = e.target.value.replace(/[^0-9]/g, '');
                                                    setFormData({ ...formData, maddiTazminat: value });
                                                }}
                                                className="text-lg font-mono pr-12"
                                            />
                                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground font-semibold">TL</span>
                                        </div>
                                        <p className="text-xs text-muted-foreground">Talep edilen maddi tazminat tutarı</p>
                                    </div>

                                    <div className="space-y-2">
                                        <Label className="flex items-center gap-2">
                                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 text-muted-foreground"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" /></svg>
                                            Manevi Tazminat
                                        </Label>
                                        <div className="relative">
                                            <Input
                                                type="text"
                                                placeholder="0"
                                                value={formData.maneviTazminat ? Number(formData.maneviTazminat).toLocaleString('tr-TR') : ''}
                                                onChange={(e) => {
                                                    const value = e.target.value.replace(/[^0-9]/g, '');
                                                    setFormData({ ...formData, maneviTazminat: value });
                                                }}
                                                className="text-lg font-mono pr-12"
                                            />
                                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground font-semibold">TL</span>
                                        </div>
                                        <p className="text-xs text-muted-foreground">Talep edilen manevi tazminat tutarı</p>
                                    </div>
                                </div>
                            </div>

                            <Separator />

                            {/* BÖLÜM 4: DETAYLAR */}
                            <div className="grid md:grid-cols-2 gap-6">

                                <div className="space-y-2">
                                    <Label className="flex items-center gap-2">
                                        <Building className="w-4 h-4 text-muted-foreground" />
                                        Mahkeme Bilgisi
                                    </Label>
                                    <Input
                                        placeholder="Örn: Bursa 13. Tüketici Mahkemesi"
                                        value={formData.court}
                                        onChange={(e) => setFormData({ ...formData, court: e.target.value })}
                                    />
                                </div>

                                <div className="space-y-2">
                                    <Label className="flex items-center gap-2">
                                        <Briefcase className="w-4 h-4 text-muted-foreground" />
                                        Kategori
                                    </Label>
                                    <Select value={formData.category} onValueChange={(v) => setFormData({ ...formData, category: v })}>
                                        <SelectTrigger>
                                            <SelectValue placeholder="Kategori Seç..." />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {KATEGORILER.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-2">
                                    <Label>Sorumlu Avukat</Label>
                                    <Select value={formData.lawyer} onValueChange={(v) => setFormData({ ...formData, lawyer: v })}>
                                        <SelectTrigger>
                                            <SelectValue placeholder="Avukat Seç..." />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {AVUKATLAR.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-2">
                                    <Label>UYAP Kayıtlı Avukat</Label>
                                    <Input
                                        placeholder="Örn: Av. Mehmet Demir"
                                        value={formData.uyapLawyer}
                                        onChange={(e) => setFormData({ ...formData, uyapLawyer: e.target.value })}
                                    />
                                </div>
                            </div>
                        </CardContent>

                        {/* FOOTER ACTION */}
                        <div className="bg-muted/5 border-t border-border p-6 flex justify-end gap-4">
                            <Button type="button" variant="outline" size="lg">İptal</Button>
                            <Button type="submit" size="lg" className="px-8 font-semibold shadow-lg" disabled={isLoading}>
                                {isLoading ? (
                                    <>Kaydediliyor...</>
                                ) : (
                                    <>
                                        <Save className="w-4 h-4 mr-2" />
                                        Kaydet / Güncelle
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

export default NewCase;
