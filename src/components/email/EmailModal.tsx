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

    const { lawyers } = useConfig();

    const [sendEmail, setSendEmail] = useState(true);
    const [tebligTarihi, setTebligTarihi] = useState("");

    // State for To list (Selected Lawyers)
    const [selectedLawyers, setSelectedLawyers] = useState<{ name: string, code: string }[]>([]);
    const [openCombobox, setOpenCombobox] = useState(false);

    // State for CC list
    const [ccLawyers, setCcLawyers] = useState<{ name: string, code: string }[]>([]);
    const [openCcCombobox, setOpenCcCombobox] = useState(false);

    const [showCc, setShowCc] = useState(false);

    // Initialize with defaults when opened
    useEffect(() => {
        if (isOpen) {
            setSelectedLawyers([]); // Reset on open
            setCcLawyers([]);
            setShowCc(defaultCc.length > 0);
            setSendEmail(true); // Default to true
            setTebligTarihi(""); // Reset date
        }
    }, [isOpen]);

    // Handler for selecting lawyer
    const handleSelectLawyer = (type: 'to' | 'cc', lawyer: { name: string, code: string }) => {
        if (type === 'to') {
            if (!selectedLawyers.find(l => l.code === lawyer.code)) {
                setSelectedLawyers([...selectedLawyers, lawyer]);
            }
            setOpenCombobox(false);
        } else {
            if (!ccLawyers.find(l => l.code === lawyer.code)) {
                setCcLawyers([...ccLawyers, lawyer]);
            }
            setOpenCcCombobox(false);
        }
    };

    // Remove handler
    const removeLawyer = (type: 'to' | 'cc', code: string) => {
        if (type === 'to') {
            setSelectedLawyers(selectedLawyers.filter(l => l.code !== code));
        } else {
            setCcLawyers(ccLawyers.filter(l => l.code !== code));
        }
    };

    const handleConfirm = () => {
        if (sendEmail && selectedLawyers.length === 0) {
            toast.error("En az bir alıcı (Kime) seçmelisiniz.");
            return;
        }

        // Generate names
        const toList = selectedLawyers.map(l => `${l.name} <${l.code}@lexis.test>`);
        const ccList = ccLawyers.map(l => `${l.name} <${l.code}@lexis.test>`);

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

                            {/* TO Field - Lawyer Selection */}
                            <div className="space-y-2">
                                <Label className="text-sm font-semibold">Kime (Avukat Seç)</Label>
                                <div className="flex flex-col gap-2">
                                    {/* Selected Chips */}
                                    <div className="flex flex-wrap gap-2 mb-2">
                                        {selectedLawyers.map(l => (
                                            <Badge key={l.code} variant="secondary" className="px-3 py-1 flex items-center gap-1 hover:bg-destructive/20 hover:text-destructive transition-colors text-sm">
                                                <User className="w-3 h-3 mr-1 opacity-50" />
                                                {l.name}
                                                <X
                                                    className="w-3 h-3 cursor-pointer ml-1"
                                                    onClick={() => removeLawyer('to', l.code)}
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
                                                    Avukat Ara / Ekle...
                                                </span>
                                            </Button>
                                        </PopoverTrigger>
                                        <PopoverContent className="w-[400px] p-0" align="start">
                                            <Command>
                                                <CommandInput placeholder="Avukat ismi ara..." />
                                                <CommandList>
                                                    <CommandEmpty>Avukat bulunamadı.</CommandEmpty>
                                                    <CommandGroup>
                                                        {lawyers.map((lawyer) => (
                                                            <CommandItem
                                                                key={lawyer.code}
                                                                value={lawyer.name}
                                                                onSelect={() => handleSelectLawyer('to', { name: lawyer.name, code: lawyer.code })}
                                                            >
                                                                <Check
                                                                    className={cn(
                                                                        "mr-2 h-4 w-4",
                                                                        selectedLawyers.find(l => l.code === lawyer.code) ? "opacity-100" : "opacity-0"
                                                                    )}
                                                                />
                                                                {lawyer.name}
                                                                <span className="ml-auto text-xs text-muted-foreground">{lawyer.code}</span>
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

                            {/* CC Field - Lawyer Selection */}
                            {showCc && (
                                <div className="space-y-2 animate-in slide-in-from-top-2 duration-200">
                                    <Label className="text-sm font-semibold">Bilgi (CC)</Label>
                                    <div className="flex flex-col gap-2">
                                        {/* Selected Chips */}
                                        <div className="flex flex-wrap gap-2 mb-2">
                                            {ccLawyers.map(l => (
                                                <Badge key={l.code} variant="secondary" className="px-3 py-1 flex items-center gap-1 hover:bg-destructive/20 hover:text-destructive transition-colors text-sm">
                                                    <User className="w-3 h-3 mr-1 opacity-50" />
                                                    {l.name}
                                                    <X
                                                        className="w-3 h-3 cursor-pointer ml-1"
                                                        onClick={() => removeLawyer('cc', l.code)}
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
                                                        CC'ye Avukat Ekle...
                                                    </span>
                                                </Button>
                                            </PopoverTrigger>
                                            <PopoverContent className="w-[400px] p-0" align="start">
                                                <Command>
                                                    <CommandInput placeholder="Avukat ismi ara..." />
                                                    <CommandList>
                                                        <CommandEmpty>Avukat bulunamadı.</CommandEmpty>
                                                        <CommandGroup>
                                                            {lawyers.map((lawyer) => (
                                                                <CommandItem
                                                                    key={lawyer.code}
                                                                    value={lawyer.name}
                                                                    onSelect={() => handleSelectLawyer('cc', { name: lawyer.name, code: lawyer.code })}
                                                                >
                                                                    <Check
                                                                        className={cn(
                                                                            "mr-2 h-4 w-4",
                                                                            ccLawyers.find(l => l.code === lawyer.code) ? "opacity-100" : "opacity-0"
                                                                        )}
                                                                    />
                                                                    {lawyer.name}
                                                                    <span className="ml-auto text-xs text-muted-foreground">{lawyer.code}</span>
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
                                    ℹ️ <strong>Test Modu:</strong> Seçtiğiniz avukatların kodları sisteme iletilecektir.
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
