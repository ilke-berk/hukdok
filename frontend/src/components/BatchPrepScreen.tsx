import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  FileText,
  Mail,
  Plus,
  X,
  ArrowRight,
  User,
  Check,
  Layers,
  Wand2,
} from "lucide-react";
import { useConfig } from "@/hooks/useConfig";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";

export interface BatchPrepConfig {
  docTypes: string[];
  emailConfig: {
    sendEmail: boolean;
    to: { name: string; email: string }[];
    cc: { name: string; email: string }[];
    tebligTarihi: string;
    confirmPerFile: boolean;
  };
}

interface BatchPrepScreenProps {
  isOpen: boolean;
  files: File[];
  onCancel: () => void;
  onStart: (config: BatchPrepConfig) => void;
}

const AUTO_VALUE = "__auto__";

export function BatchPrepScreen({
  isOpen,
  files,
  onCancel,
  onStart,
}: BatchPrepScreenProps) {
  const { doctypes, emailRecipients } = useConfig();

  const [docTypes, setDocTypes] = useState<string[]>([]);
  const [bulkDocType, setBulkDocType] = useState<string>("");

  const [sendEmail, setSendEmail] = useState(true);
  const [toRecipients, setToRecipients] = useState<{ name: string; email: string }[]>([]);
  const [ccRecipients, setCcRecipients] = useState<{ name: string; email: string }[]>([]);
  const [showCc, setShowCc] = useState(false);
  const [openToCombobox, setOpenToCombobox] = useState(false);
  const [openCcCombobox, setOpenCcCombobox] = useState(false);
  const [tebligTarihi, setTebligTarihi] = useState("");
  const [confirmPerFile, setConfirmPerFile] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setDocTypes(files.map(() => ""));
      setBulkDocType("");
      setSendEmail(true);
      setToRecipients([]);
      setCcRecipients([]);
      setShowCc(false);
      setTebligTarihi("");
      setConfirmPerFile(false);
    }
  }, [isOpen, files]);

  const cleanCode = (code: string | undefined) => (code ?? "").replace(/_+$/, "");

  const doctypeName = (code: string) => {
    if (!code) return "— Otomatik (AI) —";
    const item = doctypes.find((d) => cleanCode(d.code) === code);
    return item?.name ?? code;
  };

  const handleBulkApply = (value: string) => {
    const code = value === AUTO_VALUE ? "" : value;
    setBulkDocType(code);
    setDocTypes(files.map(() => code));
  };

  const handlePerFileChange = (index: number, value: string) => {
    const code = value === AUTO_VALUE ? "" : value;
    setDocTypes((prev) => prev.map((c, i) => (i === index ? code : c)));
  };

  const handleSelectRecipient = (
    type: "to" | "cc",
    recipient: { name: string; email: string },
  ) => {
    if (type === "to") {
      if (!toRecipients.find((r) => r.email === recipient.email)) {
        setToRecipients((prev) => [...prev, recipient]);
      }
      setOpenToCombobox(false);
    } else {
      if (!ccRecipients.find((r) => r.email === recipient.email)) {
        setCcRecipients((prev) => [...prev, recipient]);
      }
      setOpenCcCombobox(false);
    }
  };

  const removeRecipient = (type: "to" | "cc", email: string) => {
    if (type === "to") {
      setToRecipients((prev) => prev.filter((r) => r.email !== email));
    } else {
      setCcRecipients((prev) => prev.filter((r) => r.email !== email));
    }
  };

  const handleStart = () => {
    if (sendEmail && toRecipients.length === 0 && !confirmPerFile) {
      toast.error(
        "E-posta açık ama alıcı seçilmedi. Ya alıcı ekleyin, ya \"Her dosyada ayrıca onayla\" seçeneğini açın, ya da e-postayı kapatın.",
      );
      return;
    }

    onStart({
      docTypes,
      emailConfig: {
        sendEmail,
        to: toRecipients,
        cc: ccRecipients,
        tebligTarihi,
        confirmPerFile,
      },
    });
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="theme-classic bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none p-0 gap-0 sm:max-w-[760px] max-h-[92vh] overflow-y-auto">
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-[var(--border)]">
          <div className="flex items-start gap-3">
            <div className="w-11 h-11 grid place-items-center bg-[var(--brand-soft)] text-[var(--brand)] shrink-0">
              <Layers className="w-5 h-5" strokeWidth={1.6} />
            </div>
            <div className="min-w-0 grid gap-1">
              <Eyebrow tone="brand">Toplu Yükleme · Hazırlık</Eyebrow>
              <div className="flex items-baseline gap-3 flex-wrap">
                <DialogTitle className="font-display text-[20px] font-medium tracking-[-0.005em] text-[var(--fg)] leading-tight">
                  Belge Türü &amp; E-posta Ayarları
                </DialogTitle>
                <span className="inline-flex items-center px-2 py-0.5 font-mono text-[10px] tracking-[0.14em] uppercase border border-[var(--brand)]/30 bg-[var(--brand-soft)] text-[var(--brand)]">
                  {files.length} dosya
                </span>
              </div>
              <p className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed">
                Analiz başlamadan önce belge türlerini ve e-posta ayarlarını belirleyin.
                Bu adım AI'ın doğru özel prompt'u kullanmasını sağlar.
              </p>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-6 px-6 py-5">
          {/* SECTION 1: BELGE TÜRLERİ */}
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <FileText className="w-3.5 h-3.5 text-[var(--brand)]" />
              <Eyebrow tone="brand">01 · Belge Türleri</Eyebrow>
            </div>

            <div className="border border-[var(--border)] bg-[var(--bg)] p-3 space-y-2">
              <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] flex items-center gap-1.5">
                <Wand2 className="w-3 h-3" />
                Tümüne uygula
              </Label>
              <Select
                value={bulkDocType === "" ? AUTO_VALUE : bulkDocType}
                onValueChange={handleBulkApply}
              >
                <SelectTrigger className="bg-[var(--bg)] border-[var(--border)] rounded-[3px] border-0">
                  <SelectValue placeholder="— Otomatik (AI) —" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={AUTO_VALUE}>— Otomatik (AI) —</SelectItem>
                  {doctypes.map((d) => {
                    const code = cleanCode(d.code);
                    if (!code) return null;
                    return (
                      <SelectItem key={code} value={code}>
                        {d.name}
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </div>

            <div className="rounded-[3px] border border-[var(--border)] divide-y divide-[var(--border)] max-h-[280px] overflow-y-auto">
              {files.map((file, index) => (
                <div
                  key={`${file.name}-${index}`}
                  className="flex items-center gap-3 p-3 hover:bg-[var(--bg-sunken)] transition-colors"
                >
                  <span className="text-xs font-mono text-[var(--fg-muted)] shrink-0 w-6">
                    {index + 1}.
                  </span>
                  <span
                    className="flex-1 text-sm truncate min-w-0"
                    title={file.name}
                  >
                    {file.name}
                  </span>
                  <Select
                    value={(docTypes[index] ?? "") === "" ? AUTO_VALUE : docTypes[index]}
                    onValueChange={(v) => handlePerFileChange(index, v)}
                  >
                    <SelectTrigger className="h-8 w-[200px] text-xs bg-[var(--bg)] border-[var(--border)] rounded-[3px] border-0 shrink-0">
                      <SelectValue>{doctypeName(docTypes[index] ?? "")}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={AUTO_VALUE}>— Otomatik (AI) —</SelectItem>
                      {doctypes.map((d) => {
                        const code = cleanCode(d.code);
                        if (!code) return null;
                        return (
                          <SelectItem key={code} value={code}>
                            {d.name}
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>
          </section>

          {/* SECTION 2: E-POSTA AYARLARI */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Mail className="w-3.5 h-3.5 text-[var(--brand)]" />
                <Eyebrow tone="brand">02 · E-posta Ayarları</Eyebrow>
              </div>
              <div className="flex items-center gap-2">
                <Label htmlFor="batch-send-email" className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                  E-posta gönder
                </Label>
                <Switch
                  id="batch-send-email"
                  checked={sendEmail}
                  onCheckedChange={setSendEmail}
                  className="data-[state=checked]:bg-[var(--brand)]"
                />
              </div>
            </div>

            {sendEmail && (
              <div className="border border-[var(--border)] bg-[var(--bg)] p-4 space-y-4 animate-in fade-in slide-in-from-top-2 duration-200">
                {/* Kime */}
                <div className="space-y-2">
                  <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">Kime</Label>
                  <div className="flex flex-wrap gap-2">
                    {toRecipients.map((r) => (
                      <Badge
                        key={r.email}
                        variant="secondary"
                        className="px-3 py-1 flex items-center gap-1 hover:bg-[#a8323b]/15 hover:text-[#a8323b] transition-colors text-sm"
                      >
                        <User className="w-3 h-3 mr-1 opacity-50" />
                        {r.name}
                        <X
                          className="w-3 h-3 cursor-pointer ml-1"
                          onClick={() => removeRecipient("to", r.email)}
                        />
                      </Badge>
                    ))}
                  </div>
                  <Popover open={openToCombobox} onOpenChange={setOpenToCombobox}>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        role="combobox"
                        className="w-full justify-between bg-[var(--bg)] border-[var(--border)] rounded-[3px] border-0"
                      >
                        <span className="text-[var(--fg-muted)] flex items-center text-sm">
                          <Plus className="w-4 h-4 mr-2" />
                          Alıcı Ara / Ekle...
                        </span>
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[400px] p-0 z-[100]" align="start">
                      <Command>
                        <CommandInput placeholder="İsim ara..." />
                        <CommandList>
                          <CommandEmpty>Alıcı bulunamadı.</CommandEmpty>
                          <CommandGroup>
                            {emailRecipients.map((r) => (
                              <CommandItem
                                key={r.email}
                                value={r.name}
                                onSelect={() =>
                                  handleSelectRecipient("to", {
                                    name: r.name,
                                    email: r.email ?? "",
                                  })
                                }
                              >
                                <Check
                                  className={cn(
                                    "mr-2 h-4 w-4",
                                    toRecipients.find((x) => x.email === r.email)
                                      ? "opacity-100"
                                      : "opacity-0",
                                  )}
                                />
                                {r.name}
                                <span className="ml-auto text-[10px] text-[var(--fg-muted)]">
                                  {r.email}
                                </span>
                              </CommandItem>
                            ))}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                </div>

                {/* CC */}
                {!showCc ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-xs text-[var(--fg-muted)] hover:text-[var(--brand)]"
                    onClick={() => setShowCc(true)}
                  >
                    <Plus className="w-3 h-3 mr-1" /> CC Ekle
                  </Button>
                ) : (
                  <div className="space-y-2 animate-in slide-in-from-top-2 duration-200">
                    <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">Bilgi (CC)</Label>
                    <div className="flex flex-wrap gap-2">
                      {ccRecipients.map((r) => (
                        <Badge
                          key={r.email}
                          variant="secondary"
                          className="px-3 py-1 flex items-center gap-1 hover:bg-[#a8323b]/15 hover:text-[#a8323b] transition-colors text-sm"
                        >
                          <User className="w-3 h-3 mr-1 opacity-50" />
                          {r.name}
                          <X
                            className="w-3 h-3 cursor-pointer ml-1"
                            onClick={() => removeRecipient("cc", r.email)}
                          />
                        </Badge>
                      ))}
                    </div>
                    <Popover open={openCcCombobox} onOpenChange={setOpenCcCombobox}>
                      <PopoverTrigger asChild>
                        <Button
                          variant="outline"
                          role="combobox"
                          className="w-full justify-between bg-[var(--bg)] border-[var(--border)] rounded-[3px] border-0"
                        >
                          <span className="text-[var(--fg-muted)] flex items-center text-sm">
                            <Plus className="w-4 h-4 mr-2" />
                            CC'ye Alıcı Ekle...
                          </span>
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-[400px] p-0 z-[100]" align="start">
                        <Command>
                          <CommandInput placeholder="İsim ara..." />
                          <CommandList>
                            <CommandEmpty>Alıcı bulunamadı.</CommandEmpty>
                            <CommandGroup>
                              {emailRecipients.map((r) => (
                                <CommandItem
                                  key={r.email}
                                  value={r.name}
                                  onSelect={() =>
                                    handleSelectRecipient("cc", {
                                      name: r.name,
                                      email: r.email ?? "",
                                    })
                                  }
                                >
                                  <Check
                                    className={cn(
                                      "mr-2 h-4 w-4",
                                      ccRecipients.find((x) => x.email === r.email)
                                        ? "opacity-100"
                                        : "opacity-0",
                                    )}
                                  />
                                  {r.name}
                                  <span className="ml-auto text-[10px] text-[var(--fg-muted)]">
                                    {r.email}
                                  </span>
                                </CommandItem>
                              ))}
                            </CommandGroup>
                          </CommandList>
                        </Command>
                      </PopoverContent>
                    </Popover>
                  </div>
                )}

                {/* Tebliğ Tarihi */}
                <div className="space-y-2">
                  <Label htmlFor="batch-teblig-tarihi" className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                    Tebliğ Tarihi (Opsiyonel)
                  </Label>
                  <Input
                    id="batch-teblig-tarihi"
                    type="date"
                    className="bg-[var(--bg)] border-[var(--border)] rounded-[3px]"
                    value={tebligTarihi}
                    onChange={(e) => setTebligTarihi(e.target.value)}
                  />
                </div>
              </div>
            )}

            <div className="flex items-start justify-between gap-3 p-4 bg-[var(--bg)] border border-[var(--border)]">
              <div className="space-y-1 flex-1 min-w-0">
                <Label
                  htmlFor="batch-confirm-per-file"
                  className="font-display text-[13px] font-medium text-[var(--fg)] tracking-[-0.005em]"
                >
                  Her dosyada e-posta ayarlarını ayrıca onayla
                </Label>
                <p className="text-[11.5px] text-[var(--fg-muted)] leading-relaxed">
                  Kapalıyken sıradaki dosyalarda e-posta penceresi hiç açılmaz —
                  yukarıdaki ayarlar tüm batch için kullanılır.
                </p>
              </div>
              <Switch
                id="batch-confirm-per-file"
                checked={confirmPerFile}
                onCheckedChange={setConfirmPerFile}
                className="data-[state=checked]:bg-[var(--brand)]"
              />
            </div>
          </section>
        </div>

        <DialogFooter className="px-6 py-4 gap-2 sm:justify-between border-t border-[var(--border)] bg-[var(--bg)]">
          <FlowButton variant="ghost" onClick={onCancel}>
            İptal
          </FlowButton>
          <FlowButton variant="primary" onClick={handleStart} className="min-w-[180px]">
            Analize Başla
            <ArrowRight className="w-3.5 h-3.5" />
          </FlowButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
