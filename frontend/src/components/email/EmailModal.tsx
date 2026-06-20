import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { X, Mail, Plus, Loader2, User, Check, ZapOff, Sparkles, Paperclip, FileText, Image, ArrowLeft, ArrowRight, AlertTriangle, Layers } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";
import { useConfig } from "../../hooks/useConfig";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api";

interface EmailModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: (to: string[], cc: string[], shouldSendEmail: boolean, tebligTarihi?: string, perRecipientMessages?: Record<string, string>, extraAttachments?: File[], sendClientNotice?: boolean, clientNoticeMessage?: string) => void;
    // Faz 6: prefill için recipient objesi kabul ediyoruz; hazırlık ekranından gelen
    // ayarlar burada başlangıç state'ine basılır.
    defaultTo?: { name: string; email: string }[];
    defaultCc?: { name: string; email: string }[];
    defaultSendEmail?: boolean;
    defaultTebligTarihi?: string;
    isLoading?: boolean;
    batchCount?: number;
    totalFiles?: number;
    analysisContext?: {
        muvekkil_adi?: string;
        muvekkiller?: string[];
        belge_turu_kodu?: string;
        tarih?: string;
        // Müvekkil bilgilendirme metninin asıl kaynağı: belgenin AI özeti ve dava bağlamı.
        ozet?: string;
        karsi_taraf?: string;
        sonraki_durusma_tarihi?: string;
        sonraki_durusma_saati?: string;
    };
    // Müvekkil bilgilendirme — metin müvekkile DEĞİL, davanın sorumlu avukatına
    // "[Müvekkil Bilgilendirme]" konusuyla gider; avukat müvekkile iletir.
    clientNoticeLawyer?: { name: string; email: string } | null; // sorumlu avukat (alıcı)
    clientNoticeClientName?: string | null;                      // metinde hitap edilecek müvekkil
    // Bu belge türü için müvekkil bilgilendirmesi gönderilmeli mi (backend gating).
    clientNotifyEligible?: boolean;
    // Dava bağlı değil / sorumlu avukat yok gibi durumlarda gösterilecek uyarı.
    clientWarning?: string | null;
}

export function EmailModal({
    isOpen,
    onClose,
    onConfirm,
    defaultTo = [],
    defaultCc = [],
    defaultSendEmail,
    defaultTebligTarihi,
    isLoading = false,
    batchCount = 0,
    totalFiles = 0,
    analysisContext,
    clientNoticeLawyer = null,
    clientNoticeClientName = null,
    clientNotifyEligible = false,
    clientWarning = null,
}: EmailModalProps) {

    const { emailRecipients } = useConfig();

    // Step: "setup" | "preview"
    const [step, setStep] = useState<"setup" | "preview">("setup");
    const [showNoEmailConfirm, setShowNoEmailConfirm] = useState(false);

    const [sendEmail, setSendEmail] = useState(true);
    const [tebligTarihi, setTebligTarihi] = useState("");

    // Recipients
    const [selectedRecipients, setSelectedRecipients] = useState<{ name: string, email: string }[]>([]);
    const [openCombobox, setOpenCombobox] = useState(false);
    const [ccRecipients, setCcRecipients] = useState<{ name: string, email: string }[]>([]);
    const [openCcCombobox, setOpenCcCombobox] = useState(false);
    const [showCc, setShowCc] = useState(false);

    // Müvekkil bilgilendirme — sorumlu avukata gidecek tek taslak metin.
    const [notifyClient, setNotifyClient] = useState(true);
    const [clientNoticeMessage, setClientNoticeMessage] = useState("");

    // Sorumlu avukatın e-postası varsa bilgilendirme gönderilebilir.
    const clientNoticeAvailable = clientNotifyEligible && !!clientNoticeLawyer?.email;

    // Extra attachments
    const [extraAttachments, setExtraAttachments] = useState<File[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Per-recipient messages: { email → message text }
    const [perRecipientMessages, setPerRecipientMessages] = useState<Record<string, string>>({});
    const [isGeneratingPreviews, setIsGeneratingPreviews] = useState(false);

    const isBatchMode = totalFiles > 1;

    useEffect(() => {
        if (isOpen) {
            setStep("setup");
            // Faz 6: hazırlık ekranındaki ayarlar prefill olarak yüklenir.
            setSelectedRecipients(defaultTo);
            setCcRecipients(defaultCc);
            setShowCc(defaultCc.length > 0);
            setSendEmail(defaultSendEmail ?? true);
            setTebligTarihi(defaultTebligTarihi ?? "");
            setPerRecipientMessages({});
            setExtraAttachments([]);
            setShowNoEmailConfirm(false);
            // Müvekkil bilgilendirme: sorumlu avukat e-postası varsa varsayılan açık.
            setNotifyClient(clientNotifyEligible && !!clientNoticeLawyer?.email);
            setClientNoticeMessage("");
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, clientNotifyEligible, clientNoticeLawyer?.email]);

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

    // Müvekkil bilgilendirme bu gönderimde gidecek mi?
    const sendClientNotice = notifyClient && clientNoticeAvailable;

    // Önizleme sekmeleri: avukat alıcıları + (varsa) tek müvekkil bilgilendirme taslağı.
    // Müvekkil taslağı benzersiz id ("__client_notice__") taşır; sorumlu avukat aynı
    // zamanda avukat alıcısıysa email çakışmasını önler.
    type PreviewItem = { id: string; title: string; subtitle: string; kind: "lawyer" | "client" };
    const previewItems: PreviewItem[] = [
        ...selectedRecipients.map(r => ({ id: r.email, title: r.name, subtitle: r.email, kind: "lawyer" as const })),
        ...(sendClientNotice && clientNoticeLawyer
            ? [{ id: "__client_notice__", title: "Müvekkil Bilgilendirme", subtitle: `Av. ${clientNoticeLawyer.name} • ${clientNoticeLawyer.email}`, kind: "client" as const }]
            : []),
    ];

    // Step 1 → Step 2: AI'a her alıcı için mesaj ürettir
    const handleProceedToPreview = async () => {
        if (!sendEmail) {
            onConfirm([], [], false, tebligTarihi, undefined, extraAttachments.length > 0 ? extraAttachments : undefined, false, undefined);
            return;
        }
        if (selectedRecipients.length === 0) {
            toast.error("En az bir alıcı (Kime) seçmelisiniz.");
            return;
        }

        setIsGeneratingPreviews(true);
        setStep("preview");

        const generated: Record<string, string> = {};

        // Avukat / ilgili alıcılar — mevcut endpoint.
        const lawyerJobs = selectedRecipients.map(async (recipient) => {
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
        });

        // Müvekkil bilgilendirme taslağı — sorumlu avukata gidecek tek metin.
        // Müvekkile özel endpoint'i, metinde hitap edilecek müvekkil adıyla çağırır.
        const clientNoticeName = clientNoticeClientName || analysisContext?.muvekkil_adi || (analysisContext?.muvekkiller?.[0]) || "Müvekkil";
        let noticeBody = "";
        const clientNoticeJob = sendClientNotice ? (async () => {
            try {
                const formData = new FormData();
                formData.append("client_name", clientNoticeName);
                if (analysisContext?.belge_turu_kodu) formData.append("belge_turu_kodu", analysisContext.belge_turu_kodu);
                if (analysisContext?.tarih) formData.append("tarih", analysisContext.tarih);
                if (tebligTarihi) formData.append("teblig_tarihi", tebligTarihi);
                if (analysisContext?.ozet) formData.append("ai_ozet", analysisContext.ozet);
                if (analysisContext?.karsi_taraf) formData.append("karsi_taraf", analysisContext.karsi_taraf);
                if (analysisContext?.sonraki_durusma_tarihi) formData.append("sonraki_durusma_tarihi", analysisContext.sonraki_durusma_tarihi);
                if (analysisContext?.sonraki_durusma_saati) formData.append("sonraki_durusma_saati", analysisContext.sonraki_durusma_saati);

                const response = await apiClient.fetch("/preview-client-email-body", {
                    method: "POST",
                    body: formData,
                });

                if (!response.ok) throw new Error();
                const data = await response.json();
                noticeBody = data.body || "";
            } catch {
                noticeBody = `Sayın ${clientNoticeName},\n\nDosyanıza yeni bir belge işlenmiş olup bilginize sunulmuştur.\n\nSaygılarımızla,\nHukuDok Belge Arşiv Sistemi`;
            }
        })() : Promise.resolve();

        await Promise.all([...lawyerJobs, clientNoticeJob]);

        setPerRecipientMessages(generated);
        if (sendClientNotice) setClientNoticeMessage(noticeBody);
        setIsGeneratingPreviews(false);
    };

    // Step 2: Onayla ve Gönder
    const handleConfirm = () => {
        const toList = selectedRecipients.map(r => `${r.name} <${r.email}>`);
        const ccList = ccRecipients.map(r => `${r.name} <${r.email}>`);
        onConfirm(
            toList, ccList, true, tebligTarihi, perRecipientMessages,
            extraAttachments.length > 0 ? extraAttachments : undefined,
            sendClientNotice, sendClientNotice ? clientNoticeMessage : undefined,
        );
    };

    return (
        <>
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className={cn(
                "theme-classic bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none p-0 gap-0 transition-all duration-300 flex flex-col",
                step === "preview" ? "sm:max-w-[1024px] w-[95vw] h-[90vh] max-h-[90vh] overflow-hidden" : "sm:max-w-[680px] max-h-[92vh] overflow-y-auto"
            )}>
                <DialogHeader className="shrink-0 px-6 pt-6 pb-4 border-b border-[var(--border)]">
                    <div className="flex items-start gap-3">
                        <div className="w-11 h-11 grid place-items-center bg-[var(--brand-soft)] text-[var(--brand)] shrink-0">
                            <Mail className="w-5 h-5" strokeWidth={1.6} />
                        </div>
                        <div className="flex-1 min-w-0 grid gap-1">
                            <div className="flex items-baseline justify-between gap-3 flex-wrap">
                                <Eyebrow tone="brand">{step === "setup" ? "Bildirim · Ayarlar" : "Bildirim · Önizleme"}</Eyebrow>
                                {isBatchMode && batchCount > 0 && (
                                    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 font-mono text-[10px] tracking-[0.14em] uppercase border border-[var(--brand)]/30 bg-[var(--brand-soft)] text-[var(--brand)]">
                                        <Layers className="w-3 h-3" />
                                        Dosya {batchCount}/{totalFiles}
                                    </span>
                                )}
                            </div>
                            <DialogTitle className="font-display text-[20px] font-medium tracking-[-0.005em] text-[var(--fg)] leading-tight">
                                {step === "setup" ? "İşlem Onayı ve Bildirim" : "Mesaj Önizleme"}
                            </DialogTitle>
                            {step === "preview" && !isGeneratingPreviews && (
                                <p className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed">
                                    Her alıcı için AI tarafından oluşturulmuş mesajlar aşağıdadır. Sekmeler arasında geçiş yapabilir ve metinleri düzenleyebilirsiniz.
                                </p>
                            )}
                        </div>
                    </div>
                </DialogHeader>

                <div className={cn(step === "preview" ? "flex-1 min-h-0 flex flex-col overflow-hidden px-6 py-4" : "space-y-5 px-6 py-5")}>

                    {/* ── STEP 1: SETUP ── */}
                    {step === "setup" && (
                        <div className="space-y-6">
                            {/* SEND EMAIL TOGGLE */}
                            <div className="flex items-center justify-between p-4 bg-[var(--bg)] border border-[var(--border)]">
                                <div className="space-y-1 min-w-0">
                                    <Label htmlFor="email-mode" className="font-display text-[14px] font-medium text-[var(--fg)] tracking-[-0.005em]">
                                        E-Posta Bildirimi
                                    </Label>
                                    <p className="text-[12px] text-[var(--fg-muted)] leading-relaxed">
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
                                    className="data-[state=checked]:bg-[var(--brand)] shrink-0"
                                />
                            </div>

                            {sendEmail && (
                                <div className="space-y-6 animate-in fade-in slide-in-from-top-2 duration-300">

                                    {/* TEBLİĞ TARİHİ */}
                                    <div className="space-y-2">
                                        <Label htmlFor="teblig-tarihi" className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">Tebliğ Tarihi (Opsiyonel)</Label>
                                        <Input
                                            id="teblig-tarihi"
                                            type="date"
                                            className="bg-[var(--bg)] border-[var(--border)] rounded-[3px]"
                                            value={tebligTarihi}
                                            onChange={(e) => setTebligTarihi(e.target.value)}
                                        />
                                        <p className="text-[10px] text-[var(--fg-muted)]">Seçilirse e-posta metninde belirtilecektir.</p>
                                    </div>

                                    {/* TO Field */}
                                    <div className="space-y-2">
                                        <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">Kime (Alıcı Seç)</Label>
                                        <div className="flex flex-col gap-2">
                                            <div className="flex flex-wrap gap-2 mb-2">
                                                {selectedRecipients.map(r => (
                                                    <Badge key={r.email} variant="secondary" className="px-3 py-1 flex items-center gap-1 hover:bg-[#a8323b]/15 hover:text-[#a8323b] transition-colors text-sm">
                                                        <User className="w-3 h-3 mr-1 opacity-50" />
                                                        {r.name}
                                                        <X className="w-3 h-3 cursor-pointer ml-1" onClick={() => removeRecipient('to', r.email)} />
                                                    </Badge>
                                                ))}
                                            </div>
                                            <Popover open={openCombobox} onOpenChange={setOpenCombobox}>
                                                <PopoverTrigger asChild>
                                                    <Button variant="outline" role="combobox" aria-expanded={openCombobox} className="w-full justify-between">
                                                        <span className="text-[var(--fg-muted)] flex items-center">
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
                                                                        <span className="ml-auto text-[10px] text-[var(--fg-muted)]">{recipient.email}</span>
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
                                        <Button variant="ghost" size="sm" className="text-xs text-[var(--fg-muted)] hover:text-[var(--brand)]" onClick={() => setShowCc(true)}>
                                            <Plus className="w-3 h-3 mr-1" /> CC Ekle
                                        </Button>
                                    )}

                                    {/* CC Field */}
                                    {showCc && (
                                        <div className="space-y-2 animate-in slide-in-from-top-2 duration-200">
                                            <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">Bilgi (CC)</Label>
                                            <div className="flex flex-col gap-2">
                                                <div className="flex flex-wrap gap-2 mb-2">
                                                    {ccRecipients.map(r => (
                                                        <Badge key={r.email} variant="secondary" className="px-3 py-1 flex items-center gap-1 hover:bg-[#a8323b]/15 hover:text-[#a8323b] transition-colors text-sm">
                                                            <User className="w-3 h-3 mr-1 opacity-50" />
                                                            {r.name}
                                                            <X className="w-3 h-3 cursor-pointer ml-1" onClick={() => removeRecipient('cc', r.email)} />
                                                        </Badge>
                                                    ))}
                                                </div>
                                                <Popover open={openCcCombobox} onOpenChange={setOpenCcCombobox}>
                                                    <PopoverTrigger asChild>
                                                        <Button variant="outline" role="combobox" aria-expanded={openCcCombobox} className="w-full justify-between">
                                                            <span className="text-[var(--fg-muted)] flex items-center">
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
                                                                            <span className="ml-auto text-[10px] text-[var(--fg-muted)]">{recipient.email}</span>
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

                                    {/* MÜVEKKİL BİLGİLENDİRME (SORUMLU AVUKATA) */}
                                    <div className="space-y-2 border-t border-[var(--border)] pt-5">
                                        <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] flex items-center gap-1.5">
                                            <User className="w-3.5 h-3.5" />
                                            Müvekkil Bilgilendirme
                                        </Label>

                                        {clientWarning ? (
                                            <div className="flex items-start gap-2 p-3 bg-[#c47a1e]/10 border border-[#c47a1e]/40 text-[#c47a1e]">
                                                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" strokeWidth={1.8} />
                                                <p className="text-[12px] leading-relaxed">{clientWarning}</p>
                                            </div>
                                        ) : !clientNotifyEligible ? (
                                            <p className="text-[12px] text-[var(--fg-muted)] leading-relaxed">
                                                Bu belge türü için müvekkil bilgilendirmesi gönderilmeyecek.
                                            </p>
                                        ) : !clientNoticeLawyer?.email ? (
                                            <p className="text-[12px] text-[var(--fg-muted)] leading-relaxed">
                                                {clientNoticeLawyer?.name
                                                    ? `Sorumlu avukatın (${clientNoticeLawyer.name}) kayıtlı e-postası yok — bilgilendirme gönderilemez.`
                                                    : "Davanın sorumlu avukatı bulunamadı — bilgilendirme gönderilemez."}
                                            </p>
                                        ) : (
                                            <div className="space-y-3">
                                                <div className="flex items-center justify-between gap-3">
                                                    <p className="text-[12px] text-[var(--fg-muted)] leading-relaxed">
                                                        {notifyClient
                                                            ? <>Müvekkili bilgilendirme metni, <strong className="text-[var(--fg)]">sorumlu avukata</strong> “[Müvekkil Bilgilendirme]” konusuyla ayrı bir e-posta olarak gönderilecek (avukat müvekkiline iletir).</>
                                                            : "Müvekkil bilgilendirmesi gönderilmeyecek."}
                                                    </p>
                                                    <Switch
                                                        checked={notifyClient}
                                                        onCheckedChange={setNotifyClient}
                                                        className="data-[state=checked]:bg-[var(--brand)] shrink-0"
                                                    />
                                                </div>
                                                {notifyClient && (
                                                    <div className="flex flex-wrap items-center gap-2 text-[12px]">
                                                        <Badge variant="secondary" className="px-3 py-1 flex items-center gap-1 text-sm">
                                                            <User className="w-3 h-3 mr-1 opacity-50" />
                                                            {clientNoticeLawyer.name}
                                                            <span className="ml-1 text-[10px] opacity-60">{clientNoticeLawyer.email}</span>
                                                        </Badge>
                                                        {clientNoticeClientName && (
                                                            <span className="text-[var(--fg-muted)]">· Müvekkil: {clientNoticeClientName}</span>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>

                                    {/* EK BELGELER */}
                                    <div className="space-y-2">
                                        <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] flex items-center gap-1.5">
                                            <Paperclip className="w-3.5 h-3.5" />
                                            Ek Belgeler
                                        </Label>
                                        <div
                                            className="border border-dashed border-[var(--border-strong)] p-4 text-center cursor-pointer hover:border-[var(--brand)] hover:bg-[var(--brand-soft)]/40 transition-colors"
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
                                            <p className="text-xs text-[var(--fg-muted)]">
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
                                <div className="flex flex-col items-center justify-center py-24 gap-4 text-[var(--fg-muted)] flex-1">
                                    <Loader2 className="w-12 h-12 animate-spin text-[var(--brand)]" />
                                    <div className="text-center space-y-1">
                                        <p className="text-base font-medium">{previewItems.length} mesaj oluşturuluyor...</p>
                                        <p className="text-sm opacity-60">AI her kişiye özel metin yazıyor</p>
                                    </div>
                                </div>
                            ) : (
                                <Tabs defaultValue={previewItems[0]?.id} className="w-full flex-1 flex flex-col min-h-0 relative">
                                    <div className="overflow-x-auto pb-1 shrink-0">
                                        <TabsList className="h-auto flex w-max min-w-full justify-start gap-1.5 bg-[var(--bg)] p-1.5 border border-[var(--border)] rounded-none">
                                            {previewItems.map((item) => (
                                                <TabsTrigger
                                                    key={item.id}
                                                    value={item.id}
                                                    className={cn(
                                                        "flex flex-col items-start px-3 py-1.5 hover:bg-[var(--bg-elevated)] data-[state=active]:bg-[var(--bg-elevated)] data-[state=active]:border-l-2 rounded-none border-l-2 border-transparent transition-colors text-left max-w-[220px] shrink-0",
                                                        item.kind === "client" ? "data-[state=active]:border-l-[#2f8a5d]" : "data-[state=active]:border-l-[var(--brand)]"
                                                    )}
                                                >
                                                    <span className="font-display font-medium text-[13px] truncate w-full text-[var(--fg)] flex items-center gap-1">
                                                        {item.kind === "client" && (
                                                            <span className="inline-flex items-center px-1 py-px font-mono text-[8px] tracking-[0.1em] uppercase border border-[#2f8a5d]/40 text-[#2f8a5d] shrink-0">Müvekkil</span>
                                                        )}
                                                        <span className="truncate">{item.title}</span>
                                                    </span>
                                                    <span className="font-mono text-[10px] tracking-[0.04em] opacity-70 truncate w-full">{item.subtitle}</span>
                                                </TabsTrigger>
                                            ))}
                                        </TabsList>
                                    </div>

                                    <div className="flex-1 mt-3 bg-[var(--bg)] border border-[var(--border)] overflow-hidden flex flex-col relative">
                                        {previewItems.map((item, index) => (
                                            <TabsContent key={item.id} value={item.id} className="m-0 h-full flex-1 focus-visible:outline-none outline-none data-[state=active]:flex flex-col data-[state=inactive]:hidden">
                                                {/* Recipient Header */}
                                                <div className="flex items-center gap-3 px-5 py-4 bg-[var(--bg-elevated)] border-b border-[var(--border)] shrink-0">
                                                    <div className={cn(
                                                        "w-10 h-10 grid place-items-center text-[var(--brand-fg)] shrink-0",
                                                        item.kind === "client" ? "bg-[#2f8a5d]" : "bg-[var(--brand)]"
                                                    )}>
                                                        <User className="w-4 h-4" strokeWidth={1.8} />
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        <p className="font-display text-[15px] font-medium text-[var(--fg)] truncate">{item.title}</p>
                                                        <p className="font-mono text-[11px] tracking-[0.04em] text-[var(--fg-muted)] truncate">{item.subtitle}</p>
                                                    </div>
                                                    <span className={cn(
                                                        "inline-flex items-center px-2 py-0.5 font-mono text-[10px] tracking-[0.14em] uppercase border bg-[var(--bg)] shrink-0",
                                                        item.kind === "client" ? "border-[#2f8a5d]/40 text-[#2f8a5d]" : "border-[var(--border)] text-[var(--fg-subtle)]"
                                                    )}>
                                                        {item.kind === "client" ? "Müvekkil Bilgilendirme" : `Alıcı ${index + 1}`}
                                                    </span>
                                                </div>
                                                {/* Client notice için açıklama satırı */}
                                                {item.kind === "client" && (
                                                    <div className="px-5 py-2 bg-[#2f8a5d]/8 border-b border-[#2f8a5d]/20 text-[11px] text-[#2f8a5d] leading-relaxed">
                                                        Bu metin “[Müvekkil Bilgilendirme]” konusuyla sorumlu avukata gönderilecek; müvekkile iletilmek üzere hazırlanmıştır.
                                                    </div>
                                                )}
                                                {/* Message Body */}
                                                <div className="p-0 flex-1 flex flex-col">
                                                    <Textarea
                                                        className="w-full h-full flex-1 text-[15px] leading-relaxed font-mono resize-none bg-transparent border-0 focus-visible:ring-0 px-5 py-4 min-h-[350px]"
                                                        value={item.kind === "client" ? clientNoticeMessage : (perRecipientMessages[item.id] ?? "")}
                                                        onChange={(e) =>
                                                            item.kind === "client"
                                                                ? setClientNoticeMessage(e.target.value)
                                                                : setPerRecipientMessages(prev => ({ ...prev, [item.id]: e.target.value }))
                                                        }
                                                        placeholder={item.kind === "client" ? "Müvekkile iletilecek bilgilendirme metni..." : "Bu alıcı için gönderilecek e-posta metni..."}
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

                <DialogFooter className="px-6 py-4 gap-2 sm:justify-between shrink-0 border-t border-[var(--border)] bg-[var(--bg)]">
                    {step === "setup" ? (
                        <>
                            <FlowButton variant="ghost" onClick={onClose} disabled={isLoading}>
                                İptal
                            </FlowButton>
                            {sendEmail ? (
                                <FlowButton variant="primary" onClick={handleProceedToPreview} disabled={isLoading || selectedRecipients.length === 0} className="min-w-[180px]">
                                    <Sparkles className="w-3.5 h-3.5" />
                                    Mesajları Oluştur
                                    <ArrowRight className="w-3.5 h-3.5" />
                                </FlowButton>
                            ) : (
                                <FlowButton variant="secondary" onClick={() => setShowNoEmailConfirm(true)} disabled={isLoading} className="min-w-[180px] border-[#c47a1e]/50 text-[#c47a1e]">
                                    <ZapOff className="w-3.5 h-3.5" />
                                    E-Postasız Kaydet
                                </FlowButton>
                            )}
                        </>
                    ) : (
                        <>
                            <FlowButton variant="ghost" onClick={() => setStep("setup")} disabled={isLoading || isGeneratingPreviews}>
                                <ArrowLeft className="w-3.5 h-3.5" />
                                Geri
                            </FlowButton>
                            <FlowButton variant="primary" onClick={handleConfirm} disabled={isLoading || isGeneratingPreviews} className="min-w-[180px]">
                                {isLoading ? (
                                    <>
                                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                        İşleniyor…
                                    </>
                                ) : (
                                    <>
                                        <Mail className="w-3.5 h-3.5" />
                                        Onayla ve Gönder
                                    </>
                                )}
                            </FlowButton>
                        </>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>

        <AlertDialog open={showNoEmailConfirm} onOpenChange={setShowNoEmailConfirm}>
            <AlertDialogContent className="theme-classic bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                <AlertDialogHeader>
                    <AlertDialogTitle className="flex items-center gap-2 font-display font-medium text-[18px] text-[#c47a1e]">
                        <AlertTriangle className="w-5 h-5" strokeWidth={1.8} />
                        E-posta gönderilmeyecek
                    </AlertDialogTitle>
                    <AlertDialogDescription className="text-[13px] text-[var(--fg-muted)] leading-relaxed">
                        Bu belgeyi <strong className="text-[var(--fg)] font-semibold">e-posta göndermeden</strong> kaydedeceksiniz.
                        <br /><br />
                        İlgili kişiler bilgilendirilmeyecek. Devam etmek istediğinizden emin misiniz?
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel className="bg-transparent border-[var(--border-strong)] text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-[var(--bg)] rounded-[3px]">
                        Geri Dön
                    </AlertDialogCancel>
                    <AlertDialogAction
                        className="bg-[#c47a1e] hover:bg-[#c47a1e]/90 text-white rounded-[3px]"
                        onClick={() => onConfirm([], [], false, tebligTarihi, undefined, extraAttachments.length > 0 ? extraAttachments : undefined, false, undefined)}
                    >
                        Evet, E-Postasız Kaydet
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
        </>
    );
}
