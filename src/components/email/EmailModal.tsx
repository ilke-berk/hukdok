import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { X, Mail, Plus, Loader2, User, Check, ZapOff, Send } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { getApiUrl } from "@/lib/api";
import { useConfig } from "../../hooks/useConfig";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

interface EmailModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: (to: string[], cc: string[], shouldSendEmail: boolean, tebligTarihi?: string) => void;
    defaultTo?: string[];
    defaultCc?: string[];
    isLoading?: boolean;
    batchCount?: number; // 0 veya undefined ise normal mod, > 0 ise Batch Modu
}

export function EmailModal({
    isOpen,
    onClose,
    onConfirm,
    defaultTo = [],
    defaultCc = [],
    isLoading = false,
    batchCount = 0
}: EmailModalProps) {

    const { emailRecipients } = useConfig();

    const [sendEmail, setSendEmail] = useState(true);
    const [tebligTarihi, setTebligTarihi] = useState("");

    // State for To list (Selected Recipients)
    const [selectedRecipients, setSelectedRecipients] = useState<{ name: string, email: string }[]>([]);
    const [openCombobox, setOpenCombobox] = useState(false);

    // State for CC list
    const [ccRecipients, setCcRecipients] = useState<{ name: string, email: string }[]>([]);
    const [openCcCombobox, setOpenCcCombobox] = useState(false);

    const [showCc, setShowCc] = useState(false);

    // Initialize with defaults when opened
    useEffect(() => {
        if (isOpen) {
            setSelectedRecipients([]); // Reset on open
            setCcRecipients([]);
            setShowCc(defaultCc.length > 0);
            setSendEmail(true); // Default to true
            setTebligTarihi(""); // Reset date
        }
    }, [isOpen]);

    // Handler for selecting recipient
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

    // Remove handler
    const removeRecipient = (type: 'to' | 'cc', email: string) => {
        if (type === 'to') {
            setSelectedRecipients(selectedRecipients.filter(r => r.email !== email));
        } else {
            setCcRecipients(ccRecipients.filter(r => r.email !== email));
        }
    };

    const handleConfirm = () => {
        if (sendEmail && selectedRecipients.length === 0) {
            toast.error("En az bir alıcı (Kime) seçmelisiniz.");
            return;
        }

        // Generate format: "Name <email@domain.com>"
        const toList = selectedRecipients.map(r => `${r.name} <${r.email}>`);
        const ccList = ccRecipients.map(r => `${r.name} <${r.email}>`);

        onConfirm(toList, ccList, sendEmail, tebligTarihi);
    };

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-[600px] glass-card border-none shadow-2xl overflow-visible">
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

                            {/* TO Field - Recipient Selection */}
                            <div className="space-y-2">
                                <Label className="text-sm font-semibold">Kime (Alıcı Seç)</Label>
                                <div className="flex flex-col gap-2">
                                    {/* Selected Chips */}
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

                                    {/* Combobox */}
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

                            {/* CC Field - Recipient Selection */}
                            {showCc && (
                                <div className="space-y-2 animate-in slide-in-from-top-2 duration-200">
                                    <Label className="text-sm font-semibold">Bilgi (CC)</Label>
                                    <div className="flex flex-col gap-2">
                                        {/* Selected Chips */}
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

                                        {/* Combobox */}
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
