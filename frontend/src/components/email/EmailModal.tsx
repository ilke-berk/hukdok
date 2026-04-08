import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { X, Mail, Plus, Loader2, User, Check, ZapOff, Sparkles, RefreshCw, Paperclip, FileText, Image } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { useConfig } from "../../hooks/useConfig";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api";

interface EmailModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: (to: string[], cc: string[], shouldSendEmail: boolean, tebligTarihi?: string, customMessage?: string, extraAttachments?: File[]) => void;
    defaultTo?: string[];
    defaultCc?: string[];
    isLoading?: boolean;
    batchCount?: number;
    // Context for AI preview generation
    analysisContext?: {
        muvekkil_adi?: string;
        muvekkiller?: string[];
        belge_turu_kodu?: string;
        tarih?: string;
    };
}

export function EmailModal({
    isOpen,
    onClose,
    onConfirm,
    defaultTo = [],
    defaultCc = [],
    isLoading = false,
    batchCount = 0,
    analysisContext,
}: EmailModalProps) {

    const { emailRecipients } = useConfig();

    const [sendEmail, setSendEmail] = useState(true);
    const [tebligTarihi, setTebligTarihi] = useState("");

    // Recipients
    const [selectedRecipients, setSelectedRecipients] = useState<{ name: string, email: string }[]>([]);
    const [openCombobox, setOpenCombobox] = useState(false);
    const [ccRecipients, setCcRecipients] = useState<{ name: string, email: string }[]>([]);
    const [openCcCombobox, setOpenCcCombobox] = useState(false);
    const [showCc, setShowCc] = useState(false);

    // AI Message
    const [customMessage, setCustomMessage] = useState("");
    const [isGeneratingPreview, setIsGeneratingPreview] = useState(false);
    const [previewGenerated, setPreviewGenerated] = useState(false);

    // Extra attachments
    const [extraAttachments, setExtraAttachments] = useState<File[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (isOpen) {
            setSelectedRecipients([]);
            setCcRecipients([]);
            setShowCc(defaultCc.length > 0);
            setSendEmail(true);
            setTebligTarihi("");
            setCustomMessage("");
            setPreviewGenerated(false);
            setExtraAttachments([]);
        }
    }, [isOpen, defaultCc.length]);

    const handleSelectRecipient = (type: 'to' | 'cc', recipient: { name: string, email: string }) => {
        if (type === 'to') {
            if (!selectedRecipients.find(r => r.email === recipient.email)) {
                setSelectedRecipients([...selectedRecipients, recipient]);
            }
            setOpenCombobox(false);
        } else {
            if (!ccRecipients.find(r => r.email === recipient.email)) {
                setCcRecipients([...ccRecipients, recipient]);
            }
            setOpenCcCombobox(false);
        }
    };

    const removeRecipient = (type: 'to' | 'cc', email: string) => {
        if (type === 'to') {
            setSelectedRecipients(selectedRecipients.filter(r => r.email !== email));
        } else {
            setCcRecipients(ccRecipients.filter(r => r.email !== email));
        }
    };

    const generateAiPreview = async () => {
        setIsGeneratingPreview(true);
        try {
            const firstRecipient = selectedRecipients[0];
            const recipientName = firstRecipient?.name || "İlgili";

            const formData = new FormData();
            formData.append("recipient_name", recipientName);
            if (analysisContext?.muvekkil_adi) formData.append("muvekkil_adi", analysisContext.muvekkil_adi);
            if (analysisContext?.muvekkiller) formData.append("muvekkiller_json", JSON.stringify(analysisContext.muvekkiller));
            if (analysisContext?.belge_turu_kodu) formData.append("belge_turu_kodu", analysisContext.belge_turu_kodu);
            if (analysisContext?.tarih) formData.append("tarih", analysisContext.tarih);
            if (tebligTarihi) formData.append("teblig_tarihi", tebligTarihi);

            const response = await apiClient.fetch("/preview-email-body", {
                method: "POST",
                body: formData,
            });

            if (!response.ok) throw new Error("Önizleme oluşturulamadı");

            const data = await response.json();
            setCustomMessage(data.body || "");
            setPreviewGenerated(true);
        } catch (err) {
            toast.error("AI mesajı oluşturulurken hata oluştu.");
        } finally {
            setIsGeneratingPreview(false);
        }
    };

    const handleExtraFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || []);
        setExtraAttachments(prev => {
            const existing = new Set(prev.map(f => f.name + f.size));
            const newFiles = files.filter(f => !existing.has(f.name + f.size));
            return [...prev, ...newFiles];
        });
        // Reset input so same file can be re-selected after removal
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const removeExtraAttachment = (index: number) => {
        setExtraAttachments(prev => prev.filter((_, i) => i !== index));
    };

    const getFileIcon = (file: File) => {
        if (file.type.startsWith("image/")) return <Image className="w-3 h-3" />;
        return <FileText className="w-3 h-3" />;
    };

    const handleConfirm = () => {
        if (sendEmail && selectedRecipients.length === 0) {
            toast.error("En az bir alıcı (Kime) seçmelisiniz.");
            return;
        }

        const toList = selectedRecipients.map(r => `${r.name} <${r.email}>`);
        const ccList = ccRecipients.map(r => `${r.name} <${r.email}>`);

        onConfirm(toList, ccList, sendEmail, tebligTarihi, customMessage || undefined, extraAttachments.length > 0 ? extraAttachments : undefined);
    };

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-[620px] glass-card border-none shadow-2xl overflow-visible max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-xl font-bold bg-gradient-to-r from-primary to-blue-600 bg-clip-text text-transparent">
                        <Mail className="w-6 h-6 text-primary" />
                        İşlem Onayı ve Bildirim
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-6 py-4">

                    {/* SEND EMAIL TOGGLE */}
                    <div className="flex items-center justify-between p-4 rounded-lg bg-secondary/30 border border-border/50">
                        <div className="space-y-0.5">
                            <Label htmlFor="email-mode" className="text-base font-semibold">E-Posta Bildirimi</Label>
                            <p className="text-xs text-muted-foreground">
                                {sendEmail
                                    ? (batchCount > 0
                                        ? `Toplam ${batchCount} adet belge tek bir e-posta ekinde gönderilecek.`
                                        : "Belge işlendikten sonra ilgili kişilere e-posta gönderilecek.")
                                    : "Sadece SharePoint'e yüklenecek, e-posta gönderilmeyecek."}
                            </p>
                        </div>
                        <Switch
                            id="email-mode"
                            checked={sendEmail}
                            onCheckedChange={setSendEmail}
                        />
                    </div>

                    {sendEmail && (
                        <div className="space-y-6 animate-in fade-in slide-in-from-top-2 duration-300">

                            {/* TEBLİĞ TARİHİ */}
                            <div className="space-y-2">
                                <Label htmlFor="teblig-tarihi" className="text-sm font-semibold">Tebliğ Tarihi (Opsiyonel)</Label>
                                <Input
                                    id="teblig-tarihi"
                                    type="date"
                                    className="glass-input"
                                    value={tebligTarihi}
                                    onChange={(e) => setTebligTarihi(e.target.value)}
                                />
                                <p className="text-[10px] text-muted-foreground">Eğer seçilirse e-posta metninde belirtilecektir.</p>
                            </div>

                            {/* TO Field */}
                            <div className="space-y-2">
                                <Label className="text-sm font-semibold">Kime (Alıcı Seç)</Label>
                                <div className="flex flex-col gap-2">
                                    <div className="flex flex-wrap gap-2 mb-2">
                                        {selectedRecipients.map(r => (
                                            <Badge key={r.email} variant="secondary" className="px-3 py-1 flex items-center gap-1 hover:bg-destructive/20 hover:text-destructive transition-colors text-sm">
                                                <User className="w-3 h-3 mr-1 opacity-50" />
                                                {r.name}
                                                <X
                                                    className="w-3 h-3 cursor-pointer ml-1"
                                                    onClick={() => removeRecipient('to', r.email)}
                                                />
                                            </Badge>
                                        ))}
                                    </div>
                                    <Popover open={openCombobox} onOpenChange={setOpenCombobox}>
                                        <PopoverTrigger asChild>
                                            <Button
                                                variant="outline"
                                                role="combobox"
                                                aria-expanded={openCombobox}
                                                className="w-full justify-between"
                                            >
                                                <span className="text-muted-foreground flex items-center">
                                                    <Plus className="w-4 h-4 mr-2" />
                                                    Alıcı Ara / Ekle...
                                                </span>
                                            </Button>
                                        </PopoverTrigger>
                                        <PopoverContent className="w-[400px] p-0" align="start">
                                            <Command>
                                                <CommandInput placeholder="İsim ara..." />
                                                <CommandList>
                                                    <CommandEmpty>Alıcı bulunamadı.</CommandEmpty>
                                                    <CommandGroup>
                                                        {emailRecipients.map((recipient) => (
                                                            <CommandItem
                                                                key={recipient.email}
                                                                value={recipient.name}
                                                                onSelect={() => handleSelectRecipient('to', { name: recipient.name, email: recipient.email })}
                                                            >
                                                                <Check
                                                                    className={cn(
                                                                        "mr-2 h-4 w-4",
                                                                        selectedRecipients.find(r => r.email === recipient.email) ? "opacity-100" : "opacity-0"
                                                                    )}
                                                                />
                                                                {recipient.name}
                                                                <span className="ml-auto text-[10px] text-muted-foreground">{recipient.email}</span>
                                                            </CommandItem>
                                                        ))}
                                                    </CommandGroup>
                                                </CommandList>
                                            </Command>
                                        </PopoverContent>
                                    </Popover>
                                </div>
                            </div>

                            {/* CC Toggle */}
                            {!showCc && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="text-xs text-muted-foreground hover:text-primary"
                                    onClick={() => setShowCc(true)}
                                >
                                    <Plus className="w-3 h-3 mr-1" /> CC Ekle
                                </Button>
                            )}

                            {/* CC Field */}
                            {showCc && (
                                <div className="space-y-2 animate-in slide-in-from-top-2 duration-200">
                                    <Label className="text-sm font-semibold">Bilgi (CC)</Label>
                                    <div className="flex flex-col gap-2">
                                        <div className="flex flex-wrap gap-2 mb-2">
                                            {ccRecipients.map(r => (
                                                <Badge key={r.email} variant="secondary" className="px-3 py-1 flex items-center gap-1 hover:bg-destructive/20 hover:text-destructive transition-colors text-sm">
                                                    <User className="w-3 h-3 mr-1 opacity-50" />
                                                    {r.name}
                                                    <X
                                                        className="w-3 h-3 cursor-pointer ml-1"
                                                        onClick={() => removeRecipient('cc', r.email)}
                                                    />
                                                </Badge>
                                            ))}
                                        </div>
                                        <Popover open={openCcCombobox} onOpenChange={setOpenCcCombobox}>
                                            <PopoverTrigger asChild>
                                                <Button
                                                    variant="outline"
                                                    role="combobox"
                                                    aria-expanded={openCcCombobox}
                                                    className="w-full justify-between"
                                                >
                                                    <span className="text-muted-foreground flex items-center">
                                                        <Plus className="w-4 h-4 mr-2" />
                                                        CC'ye Alıcı Ekle...
                                                    </span>
                                                </Button>
                                            </PopoverTrigger>
                                            <PopoverContent className="w-[400px] p-0" align="start">
                                                <Command>
                                                    <CommandInput placeholder="İsim ara..." />
                                                    <CommandList>
                                                        <CommandEmpty>Alıcı bulunamadı.</CommandEmpty>
                                                        <CommandGroup>
                                                            {emailRecipients.map((recipient) => (
                                                                <CommandItem
                                                                    key={recipient.email}
                                                                    value={recipient.name}
                                                                    onSelect={() => handleSelectRecipient('cc', { name: recipient.name, email: recipient.email })}
                                                                >
                                                                    <Check
                                                                        className={cn(
                                                                            "mr-2 h-4 w-4",
                                                                            ccRecipients.find(r => r.email === recipient.email) ? "opacity-100" : "opacity-0"
                                                                        )}
                                                                    />
                                                                    {recipient.name}
                                                                    <span className="ml-auto text-[10px] text-muted-foreground">{recipient.email}</span>
                                                                </CommandItem>
                                                            ))}
                                                        </CommandGroup>
                                                    </CommandList>
                                                </Command>
                                            </PopoverContent>
                                        </Popover>
                                    </div>
                                </div>
                            )}

                            {/* EK BELGELER */}
                            <div className="space-y-2">
                                <Label className="text-sm font-semibold flex items-center gap-1.5">
                                    <Paperclip className="w-3.5 h-3.5" />
                                    Ek Belgeler
                                </Label>
                                <div
                                    className="border-2 border-dashed border-border/60 rounded-lg p-3 text-center cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-colors"
                                    onClick={() => fileInputRef.current?.click()}
                                    onDragOver={(e) => e.preventDefault()}
                                    onDrop={(e) => {
                                        e.preventDefault();
                                        const files = Array.from(e.dataTransfer.files);
                                        setExtraAttachments(prev => {
                                            const existing = new Set(prev.map(f => f.name + f.size));
                                            return [...prev, ...files.filter(f => !existing.has(f.name + f.size))];
                                        });
                                    }}
                                >
                                    <p className="text-xs text-muted-foreground">
                                        <Paperclip className="w-3 h-3 inline mr-1" />
                                        Belge Ekle (veya sürükle-bırak)
                                    </p>
                                </div>
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    multiple
                                    className="hidden"
                                    onChange={handleExtraFileSelect}
                                />
                                {extraAttachments.length > 0 && (
                                    <div className="flex flex-wrap gap-2 mt-2">
                                        {extraAttachments.map((file, i) => (
                                            <Badge key={i} variant="secondary" className="px-2 py-1 flex items-center gap-1 text-xs">
                                                {getFileIcon(file)}
                                                <span className="max-w-[120px] truncate">{file.name}</span>
                                                <X
                                                    className="w-3 h-3 cursor-pointer ml-0.5 opacity-60 hover:opacity-100"
                                                    onClick={() => removeExtraAttachment(i)}
                                                />
                                            </Badge>
                                        ))}
                                    </div>
                                )}
                                {extraAttachments.length > 0 && (
                                    <p className="text-[10px] text-muted-foreground">Eklenen belgeler e-posta ekinde gönderilecektir.</p>
                                )}
                            </div>

                            {/* MESAJ METNİ */}
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <Label className="text-sm font-semibold">Mesaj Metni</Label>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-xs text-primary hover:text-primary/80 h-7 px-2"
                                        onClick={generateAiPreview}
                                        disabled={isGeneratingPreview}
                                    >
                                        {isGeneratingPreview ? (
                                            <>
                                                <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                                                Oluşturuluyor...
                                            </>
                                        ) : previewGenerated ? (
                                            <>
                                                <RefreshCw className="w-3 h-3 mr-1" />
                                                Yeniden Oluştur
                                            </>
                                        ) : (
                                            <>
                                                <Sparkles className="w-3 h-3 mr-1" />
                                                AI ile Oluştur
                                            </>
                                        )}
                                    </Button>
                                </div>
                                <Textarea
                                    placeholder="Buraya mesajınızı yazın veya AI ile otomatik oluşturun..."
                                    className="glass-input min-h-[140px] text-sm font-mono resize-y"
                                    value={customMessage}
                                    onChange={(e) => setCustomMessage(e.target.value)}
                                />
                                {!customMessage && (
                                    <p className="text-[10px] text-muted-foreground">
                                        Boş bırakırsanız AI otomatik olarak mesaj oluşturacaktır.
                                    </p>
                                )}
                            </div>

                            <div className="p-3 bg-blue-50/5 dark:bg-blue-900/10 rounded-lg border border-blue-100/20">
                                <p className="text-xs text-muted-foreground">
                                    ℹ️ <strong>Seçim:</strong> Seçtiğiniz kişilere gerçek e-posta adresleri üzerinden bildirim gönderilecektir.
                                </p>
                            </div>
                        </div>
                    )}

                </div>

                <DialogFooter className="gap-2 sm:justify-between">
                    <Button variant="ghost" onClick={onClose} disabled={isLoading}>
                        İptal
                    </Button>
                    <Button onClick={handleConfirm} disabled={isLoading} className="bg-primary hover:bg-primary/90 min-w-[140px]">
                        {isLoading ? (
                            <>
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                İşleniyor...
                            </>
                        ) : (
                            sendEmail ? (
                                <>
                                    <Mail className="w-4 h-4 mr-2" />
                                    Onayla ve Gönder
                                </>
                            ) : (
                                <>
                                    <ZapOff className="w-4 h-4 mr-2" />
                                    E-Postasız Kaydet
                                </>
                            )
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
