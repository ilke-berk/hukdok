import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { X, Mail, Plus, Loader2, User, Check, ZapOff, Sparkles, Paperclip, FileText, Image, ArrowLeft, ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { useConfig } from "../../hooks/useConfig";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api";

interface EmailModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: (to: string[], cc: string[], shouldSendEmail: boolean, tebligTarihi?: string, perRecipientMessages?: Record<string, string>, extraAttachments?: File[]) => void;
    defaultTo?: string[];
    defaultCc?: string[];
    isLoading?: boolean;
    batchCount?: number;
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

    // Step: "setup" | "preview"
    const [step, setStep] = useState<"setup" | "preview">("setup");

    const [sendEmail, setSendEmail] = useState(true);
    const [tebligTarihi, setTebligTarihi] = useState("");

    // Recipients
    const [selectedRecipients, setSelectedRecipients] = useState<{ name: string, email: string }[]>([]);
    const [openCombobox, setOpenCombobox] = useState(false);
    const [ccRecipients, setCcRecipients] = useState<{ name: string, email: string }[]>([]);
    const [openCcCombobox, setOpenCcCombobox] = useState(false);
    const [showCc, setShowCc] = useState(false);

    // Extra attachments
    const [extraAttachments, setExtraAttachments] = useState<File[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Per-recipient messages: { email → message text }
    const [perRecipientMessages, setPerRecipientMessages] = useState<Record<string, string>>({});
    const [isGeneratingPreviews, setIsGeneratingPreviews] = useState(false);

    useEffect(() => {
        if (isOpen) {
            setStep("setup");
            setSelectedRecipients([]);
            setCcRecipients([]);
            setShowCc(defaultCc.length > 0);
            setSendEmail(true);
            setTebligTarihi("");
            setPerRecipientMessages({});
            setExtraAttachments([]);
        }
    }, [isOpen, defaultCc.length]);

    const handleSelectRecipient = (type: 'to' | 'cc', recipient: { name: string, email: string }) => {
        if (type === 'to') {
            if (!selectedRecipients.find(r => r.email === recipient.email)) {
                setSelectedRecipients(prev => [...prev, recipient]);
            }
            setOpenCombobox(false);
        } else {
            if (!ccRecipients.find(r => r.email === recipient.email)) {
                setCcRecipients(prev => [...prev, recipient]);
            }
            setOpenCcCombobox(false);
        }
    };

    const removeRecipient = (type: 'to' | 'cc', email: string) => {
        if (type === 'to') {
            setSelectedRecipients(prev => prev.filter(r => r.email !== email));
        } else {
            setCcRecipients(prev => prev.filter(r => r.email !== email));
        }
    };

    const handleExtraFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || []);
        setExtraAttachments(prev => {
            const existing = new Set(prev.map(f => f.name + f.size));
            return [...prev, ...files.filter(f => !existing.has(f.name + f.size))];
        });
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const removeExtraAttachment = (index: number) => {
        setExtraAttachments(prev => prev.filter((_, i) => i !== index));
    };

    const getFileIcon = (file: File) => {
        if (file.type.startsWith("image/")) return <Image className="w-3 h-3" />;
        return <FileText className="w-3 h-3" />;
    };

    // Step 1 → Step 2: AI'a her alıcı için mesaj ürettir
    const handleProceedToPreview = async () => {
        if (!sendEmail) {
            onConfirm([], [], false, tebligTarihi, undefined, extraAttachments.length > 0 ? extraAttachments : undefined);
            return;
        }
        if (selectedRecipients.length === 0) {
            toast.error("En az bir alıcı (Kime) seçmelisiniz.");
            return;
        }

        setIsGeneratingPreviews(true);
        setStep("preview");

        const generated: Record<string, string> = {};

        await Promise.all(
            selectedRecipients.map(async (recipient) => {
                try {
                    const formData = new FormData();
                    formData.append("recipient_name", recipient.name);
                    if (analysisContext?.muvekkil_adi) formData.append("muvekkil_adi", analysisContext.muvekkil_adi);
                    if (analysisContext?.muvekkiller) formData.append("muvekkiller_json", JSON.stringify(analysisContext.muvekkiller));
                    if (analysisContext?.belge_turu_kodu) formData.append("belge_turu_kodu", analysisContext.belge_turu_kodu);
                    if (analysisContext?.tarih) formData.append("tarih", analysisContext.tarih);
                    if (tebligTarihi) formData.append("teblig_tarihi", tebligTarihi);

                    const response = await apiClient.fetch("/preview-email-body", {
                        method: "POST",
                        body: formData,
                    });

                    if (!response.ok) throw new Error();
                    const data = await response.json();
                    generated[recipient.email] = data.body || "";
                } catch {
                    generated[recipient.email] = `Sayın ${recipient.name},\n\nBelge ektedir.\n\nSaygılarımızla,\nHukuDok Belge Arşiv Sistemi`;
                }
            })
        );

        setPerRecipientMessages(generated);
        setIsGeneratingPreviews(false);
    };

    // Step 2: Onayla ve Gönder
    const handleConfirm = () => {
        const toList = selectedRecipients.map(r => `${r.name} <${r.email}>`);
        const ccList = ccRecipients.map(r => `${r.name} <${r.email}>`);
        onConfirm(toList, ccList, true, tebligTarihi, perRecipientMessages, extraAttachments.length > 0 ? extraAttachments : undefined);
    };

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className={cn(
                "glass-card border-none shadow-2xl transition-all duration-300 flex flex-col",
                step === "preview" ? "sm:max-w-[1024px] w-[95vw] h-[90vh] max-h-[90vh] overflow-hidden" : "sm:max-w-[640px] max-h-[92vh] overflow-y-auto"
            )}>
                <DialogHeader className="shrink-0">
                    <DialogTitle className="flex items-center gap-2 text-xl font-bold bg-gradient-to-r from-primary to-blue-600 bg-clip-text text-transparent">
                        <Mail className="w-6 h-6 text-primary" />
                        {step === "setup" ? "İşlem Onayı ve Bildirim" : "Mesaj Önizleme"}
                    </DialogTitle>
                    {step === "preview" && !isGeneratingPreviews && (
                        <p className="text-sm text-muted-foreground pt-1">
                            Her alıcı için AI tarafından oluşturulmuş mesajlar aşağıdadır. Panelden farklı kişilere geçiş yapabilir ve metinleri düzenleyebilirsiniz.
                        </p>
                    )}
                </DialogHeader>

                <div className={cn("py-2", step === "preview" ? "flex-1 min-h-0 flex flex-col overflow-hidden" : "space-y-6")}>

                    {/* ── STEP 1: SETUP ── */}
                    {step === "setup" && (
                        <div className="space-y-6">
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
                                <Switch id="email-mode" checked={sendEmail} onCheckedChange={setSendEmail} />
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
                                        <p className="text-[10px] text-muted-foreground">Seçilirse e-posta metninde belirtilecektir.</p>
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
                                                        <X className="w-3 h-3 cursor-pointer ml-1" onClick={() => removeRecipient('to', r.email)} />
                                                    </Badge>
                                                ))}
                                            </div>
                                            <Popover open={openCombobox} onOpenChange={setOpenCombobox}>
                                                <PopoverTrigger asChild>
                                                    <Button variant="outline" role="combobox" aria-expanded={openCombobox} className="w-full justify-between">
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
                                                                        <Check className={cn("mr-2 h-4 w-4", selectedRecipients.find(r => r.email === recipient.email) ? "opacity-100" : "opacity-0")} />
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
                                        <Button variant="ghost" size="sm" className="text-xs text-muted-foreground hover:text-primary" onClick={() => setShowCc(true)}>
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
                                                            <X className="w-3 h-3 cursor-pointer ml-1" onClick={() => removeRecipient('cc', r.email)} />
                                                        </Badge>
                                                    ))}
                                                </div>
                                                <Popover open={openCcCombobox} onOpenChange={setOpenCcCombobox}>
                                                    <PopoverTrigger asChild>
                                                        <Button variant="outline" role="combobox" aria-expanded={openCcCombobox} className="w-full justify-between">
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
                                                                            <Check className={cn("mr-2 h-4 w-4", ccRecipients.find(r => r.email === recipient.email) ? "opacity-100" : "opacity-0")} />
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
                                        <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleExtraFileSelect} />
                                        {extraAttachments.length > 0 && (
                                            <div className="flex flex-wrap gap-2 mt-2">
                                                {extraAttachments.map((file, i) => (
                                                    <Badge key={i} variant="secondary" className="px-2 py-1 flex items-center gap-1 text-xs">
                                                        {getFileIcon(file)}
                                                        <span className="max-w-[120px] truncate">{file.name}</span>
                                                        <X className="w-3 h-3 cursor-pointer ml-0.5 opacity-60 hover:opacity-100" onClick={() => removeExtraAttachment(i)} />
                                                    </Badge>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* ── STEP 2: PER-RECIPIENT PREVIEW ── */}
                    {step === "preview" && (
                        <div className="flex-1 flex flex-col min-h-0 animate-in fade-in slide-in-from-right-2 duration-300 relative">
                            {isGeneratingPreviews ? (
                                <div className="flex flex-col items-center justify-center py-24 gap-4 text-muted-foreground flex-1">
                                    <Loader2 className="w-12 h-12 animate-spin text-primary" />
                                    <div className="text-center space-y-1">
                                        <p className="text-base font-medium">{selectedRecipients.length} alıcı için mesaj oluşturuluyor...</p>
                                        <p className="text-sm opacity-60">AI her kişiye özel metin yazıyor</p>
                                    </div>
                                </div>
                            ) : (
                                <Tabs defaultValue={selectedRecipients[0]?.email} className="w-full flex-1 flex flex-col min-h-0 relative">
                                    <div className="overflow-x-auto pb-1 shrink-0 hide-scrollbar ring-offset-background custom-scrollbar-thin">
                                        <TabsList className="h-auto flex w-max min-w-full justify-start gap-2 bg-secondary/30 p-2 border border-border/40 rounded-xl">
                                            {selectedRecipients.map((recipient) => (
                                                <TabsTrigger 
                                                    key={recipient.email} 
                                                    value={recipient.email} 
                                                    className="flex flex-col items-start px-4 py-2 hover:bg-background/50 data-[state=active]:bg-background data-[state=active]:shadow-sm rounded-lg border border-transparent data-[state=active]:border-border/50 transition-all text-left max-w-[200px] shrink-0"
                                                >
                                                    <span className="font-semibold text-sm truncate w-full">{recipient.name}</span>
                                                    <span className="text-[11px] opacity-70 truncate w-full">{recipient.email}</span>
                                                </TabsTrigger>
                                            ))}
                                        </TabsList>
                                    </div>
                                    
                                    <div className="flex-1 mt-3 bg-secondary/10 rounded-xl border border-border/60 overflow-hidden flex flex-col shadow-inner relative">
                                        {selectedRecipients.map((recipient, index) => (
                                            <TabsContent key={recipient.email} value={recipient.email} className="m-0 h-full flex-1 focus-visible:outline-none outline-none data-[state=active]:flex flex-col data-[state=inactive]:hidden">
                                                {/* Recipient Header */}
                                                <div className="flex items-center gap-3 px-5 py-4 bg-secondary/30 border-b border-border/40 shrink-0">
                                                    <div className="w-10 h-10 rounded-full bg-primary/15 flex items-center justify-center shrink-0">
                                                        <User className="w-5 h-5 text-primary" />
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        <p className="text-base font-semibold truncate">{recipient.name}</p>
                                                        <p className="text-sm text-muted-foreground truncate">{recipient.email}</p>
                                                    </div>
                                                    <Badge variant="outline" className="text-xs py-1 px-2 shrink-0 bg-background/50 border-border/60">
                                                        Alıcı {index + 1}
                                                    </Badge>
                                                </div>
                                                {/* Message Body */}
                                                <div className="p-0 flex-1 flex flex-col">
                                                    <Textarea
                                                        className="w-full h-full flex-1 text-[15px] leading-relaxed font-mono resize-none bg-transparent border-0 focus-visible:ring-0 px-5 py-4 min-h-[350px]"
                                                        value={perRecipientMessages[recipient.email] ?? ""}
                                                        onChange={(e) =>
                                                            setPerRecipientMessages(prev => ({ ...prev, [recipient.email]: e.target.value }))
                                                        }
                                                        placeholder="Bu alıcı için gönderilecek e-posta metni..."
                                                    />
                                                </div>
                                            </TabsContent>
                                        ))}
                                    </div>
                                </Tabs>
                            )}
                        </div>
                    )}

                </div>

                <DialogFooter className="gap-2 sm:justify-between shrink-0 mb-1 mt-2">
                    {step === "setup" ? (
                        <>
                            <Button variant="ghost" onClick={onClose} disabled={isLoading}>
                                İptal
                            </Button>
                            {sendEmail ? (
                                <Button onClick={handleProceedToPreview} disabled={isLoading} className="bg-primary hover:bg-primary/90 min-w-[160px]">
                                    <Sparkles className="w-4 h-4 mr-2" />
                                    Mesajları Oluştur
                                    <ArrowRight className="w-4 h-4 ml-2" />
                                </Button>
                            ) : (
                                <Button onClick={() => onConfirm([], [], false, tebligTarihi, undefined, undefined)} disabled={isLoading} className="min-w-[160px]">
                                    <ZapOff className="w-4 h-4 mr-2" />
                                    E-Postasız Kaydet
                                </Button>
                            )}
                        </>
                    ) : (
                        <>
                            <Button variant="ghost" onClick={() => setStep("setup")} disabled={isLoading || isGeneratingPreviews}>
                                <ArrowLeft className="w-4 h-4 mr-2" />
                                Geri
                            </Button>
                            <Button onClick={handleConfirm} disabled={isLoading || isGeneratingPreviews} className="bg-primary hover:bg-primary/90 min-w-[160px]">
                                {isLoading ? (
                                    <>
                                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                        İşleniyor...
                                    </>
                                ) : (
                                    <>
                                        <Mail className="w-4 h-4 mr-2" />
                                        Onayla ve Gönder
                                    </>
                                )}
                            </Button>
                        </>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
