import { useEffect, useRef, useState } from "react";
import {
  Layers,
  Mail,
  Wand2,
  X,
  ArrowRight,
  Plus,
  User,
  Check,
} from "lucide-react";
import { toast } from "sonner";
import { useConfig } from "@/hooks/useConfig";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
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
import { Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton, AiPill } from "@/components/flow/primitives";
import { predictDocTypeFromName } from "@/lib/predictDocType";

// ------------------------------------------------------------------
// Tipler
// ------------------------------------------------------------------

interface FileRow {
  id: string;
  file: File;
  name: string;
  size: number;
  docType: string;     // seçili tür kodu ("" = otomatik/AI)
  predicted: boolean;  // docType dosya adından mı tahmin edildi (ve değiştirilmedi)
  email: boolean;      // bu dosya için e-posta gönderilsin mi
}

export interface BulkPrepResult {
  file: File;
  docType: string;
  email: boolean;
}

export interface BulkUploadStartConfig {
  results: BulkPrepResult[];
  emailConfig: {
    to: { name: string; email: string }[];
    cc: { name: string; email: string }[];
    tebligTarihi: string;
    confirmPerFile: boolean;
  };
}

interface BulkUploadWorkbenchProps {
  files: File[];
  onCancel: () => void;
  onStart: (config: BulkUploadStartConfig) => void;
}

const AUTO_VALUE = "__auto__";
const cleanCode = (code: string | undefined) => (code ?? "").replace(/_+$/, "");

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ------------------------------------------------------------------
// BulkUploadWorkbench — toplu yükleme ÖN HAZIRLIK tezgâhı (analiz YOK).
// Burada belge türleri (dosya adından tahminle) ve e-posta ayarları toplanır.
// Analiz, "Onaya Geç" sonrası varsayılan tek-tek akışta başlar.
// ------------------------------------------------------------------

export function BulkUploadWorkbench({ files, onCancel, onStart }: BulkUploadWorkbenchProps) {
  const { doctypes, emailRecipients } = useConfig();

  const [rows, setRows] = useState<FileRow[]>([]);
  const [masterType, setMasterType] = useState<string>(""); // "" = otomatik
  const predictedOnceRef = useRef(false);

  // E-posta ayarları (alıcılar batch genelinde paylaşılır; per-row toggle gönderimi açar/kapatır)
  const [toRecipients, setToRecipients] = useState<{ name: string; email: string }[]>([]);
  const [ccRecipients, setCcRecipients] = useState<{ name: string; email: string }[]>([]);
  const [showCc, setShowCc] = useState(false);
  const [openTo, setOpenTo] = useState(false);
  const [openCc, setOpenCc] = useState(false);
  const [tebligTarihi, setTebligTarihi] = useState("");
  const [confirmPerFile, setConfirmPerFile] = useState(false);

  const doctypeName = (code: string) => {
    if (!code) return "— Otomatik (AI) —";
    return doctypes.find((d) => cleanCode(d.code) === code)?.name ?? code;
  };

  // Dosya değişiminde satırları kur (tahmin doctypes yüklenince yapılır).
  useEffect(() => {
    setRows(
      files.map((f, i) => ({
        id: `${i}-${f.name}-${f.size}`,
        file: f,
        name: f.name,
        size: f.size,
        docType: "",
        predicted: false,
        email: true,
      })),
    );
    predictedOnceRef.current = false;
  }, [files]);

  // doctypes yüklendiğinde (bir kez) dosya adından tür tahmini yap.
  useEffect(() => {
    if (predictedOnceRef.current) return;
    if (doctypes.length === 0 || rows.length === 0) return;
    predictedOnceRef.current = true;
    setRows((prev) =>
      prev.map((r) => {
        const code = predictDocTypeFromName(r.name, doctypes);
        return code ? { ...r, docType: code, predicted: true } : r;
      }),
    );
  }, [doctypes, rows.length]);

  // --- Kontroller ---
  const applyMasterType = (value: string) => {
    const code = value === AUTO_VALUE ? "" : value;
    setMasterType(code);
    if (code === "") {
      // Otomatik seçilirse dosya adı tahminlerini geri getir.
      setRows((prev) =>
        prev.map((r) => {
          const pred = predictDocTypeFromName(r.name, doctypes);
          return pred ? { ...r, docType: pred, predicted: true } : { ...r, docType: "", predicted: false };
        }),
      );
    } else {
      setRows((prev) => prev.map((r) => ({ ...r, docType: code, predicted: false })));
    }
  };

  const applyMasterEmail = (value: boolean) => {
    setRows((prev) => prev.map((r) => ({ ...r, email: value })));
  };

  const setRowType = (id: string, value: string) => {
    const code = value === AUTO_VALUE ? "" : value;
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, docType: code, predicted: false } : r)));
  };

  const setRowEmail = (id: string, value: boolean) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, email: value } : r)));
  };

  const removeRow = (id: string) => {
    setRows((prev) => prev.filter((r) => r.id !== id));
  };

  // --- E-posta alıcı kontrolleri ---
  const selectRecipient = (type: "to" | "cc", r: { name: string; email: string }) => {
    const setter = type === "to" ? setToRecipients : setCcRecipients;
    setter((prev) => (prev.find((x) => x.email === r.email) ? prev : [...prev, r]));
    if (type === "to") setOpenTo(false); else setOpenCc(false);
  };
  const removeRecipient = (type: "to" | "cc", email: string) => {
    const setter = type === "to" ? setToRecipients : setCcRecipients;
    setter((prev) => prev.filter((x) => x.email !== email));
  };

  // --- Türetilen ---
  const total = rows.length;
  const predictedCount = rows.filter((r) => r.predicted).length;
  const anyEmailOn = rows.some((r) => r.email);

  const handleStart = () => {
    if (rows.length === 0) {
      toast.error("Hazırlanacak dosya yok.");
      return;
    }
    if (anyEmailOn && toRecipients.length === 0 && !confirmPerFile) {
      toast.error(
        'E-posta açık ama alıcı seçilmedi. Alıcı ekleyin, "Her dosyada ayrıca onayla"yı açın ya da e-postayı kapatın.',
      );
      return;
    }

    onStart({
      results: rows.map((r) => ({ file: r.file, docType: r.docType, email: r.email })),
      emailConfig: { to: toRecipients, cc: ccRecipients, tebligTarihi, confirmPerFile },
    });
  };

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <div className="min-h-screen">
      <main className="max-w-screen-2xl mx-auto grid gap-6">
        {/* Başlık */}
        <div className="flex items-start gap-3">
          <div className="w-11 h-11 grid place-items-center bg-[var(--brand-soft)] text-[var(--brand)] shrink-0">
            <Layers className="w-5 h-5" strokeWidth={1.6} />
          </div>
          <div className="min-w-0 grid gap-1">
            <Eyebrow tone="brand">Toplu Yükleme · Ön Hazırlık</Eyebrow>
            <h1 className="font-display text-[22px] font-medium tracking-[-0.01em] text-[var(--fg)] leading-tight">
              Belge Türü &amp; E-posta Ayarları
              <span className="italic text-[var(--fg-muted)] font-normal ml-2 text-[15px]">— {total} dosya</span>
            </h1>
            <p className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed max-w-[640px]">
              Belge türlerini ve e-posta ayarlarını belirleyin. Türler dosya adından otomatik tahmin edildi
              ({predictedCount}/{total}); gerekiyorsa düzeltin. <strong>Analiz, "Onaya Geç" dedikten sonra başlar.</strong>
            </p>
          </div>
        </div>

        {/* Master şerit */}
        <div className="bg-[var(--bg-elevated)] border border-[var(--border)] flex items-center gap-5 px-5 py-3 flex-wrap">
          <span className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] inline-flex items-center gap-1.5">
            <Wand2 className="w-3 h-3" /> Tümüne Uygula
          </span>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] tracking-[0.1em] uppercase text-[var(--fg-subtle)]">Belge Türü</span>
            <Select value={masterType === "" ? AUTO_VALUE : masterType} onValueChange={applyMasterType}>
              <SelectTrigger className="h-8 w-[210px] text-xs bg-[var(--bg)] border-[var(--border)] rounded-[3px] border-0">
                <SelectValue placeholder="— Otomatik (AI) —" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={AUTO_VALUE}>— Otomatik (AI) —</SelectItem>
                {doctypes.map((d) => {
                  const code = cleanCode(d.code);
                  if (!code) return null;
                  return <SelectItem key={code} value={code}>{d.name}</SelectItem>;
                })}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] tracking-[0.1em] uppercase text-[var(--fg-subtle)]">E-posta</span>
            <Switch checked={anyEmailOn} onCheckedChange={applyMasterEmail} className="data-[state=checked]:bg-[var(--brand)]" />
          </div>
        </div>

        {/* Dosya tablosu */}
        <div className="bg-[var(--bg-elevated)] border border-[var(--border)]">
          <div className="grid grid-cols-[36px_1fr_280px_64px_40px] gap-3 px-4 py-2.5 border-b border-[var(--border)] font-mono text-[9px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] font-semibold">
            <span>#</span>
            <span>Dosya</span>
            <span>Belge Türü</span>
            <span className="text-center">E-posta</span>
            <span></span>
          </div>
          <div className="divide-y divide-[var(--border)]">
            {rows.map((r, i) => (
              <div key={r.id} className="grid grid-cols-[36px_1fr_280px_64px_40px] gap-3 px-4 py-3 items-center">
                <span className="font-mono text-[11px] text-[var(--fg-subtle)] tabular-nums">{String(i + 1).padStart(2, "0")}</span>

                <div className="min-w-0">
                  <div className="text-[13px] text-[var(--fg)] truncate" title={r.name}>{r.name}</div>
                  <div className="font-mono text-[10px] text-[var(--fg-subtle)]">{formatSize(r.size)}</div>
                </div>

                <div className="flex items-center gap-2 min-w-0">
                  <Select value={(r.docType ?? "") === "" ? AUTO_VALUE : r.docType} onValueChange={(v) => setRowType(r.id, v)}>
                    <SelectTrigger className="h-8 flex-1 text-xs bg-[var(--bg)] border-[var(--border)] rounded-[3px] border-0">
                      <SelectValue>{doctypeName(r.docType ?? "")}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={AUTO_VALUE}>— Otomatik (AI) —</SelectItem>
                      {doctypes.map((d) => {
                        const code = cleanCode(d.code);
                        if (!code) return null;
                        return <SelectItem key={code} value={code}>{d.name}</SelectItem>;
                      })}
                    </SelectContent>
                  </Select>
                  {r.predicted && (
                    <AiPill label="AD" className="shrink-0" />
                  )}
                </div>

                <div className="flex justify-center">
                  <Switch checked={r.email} onCheckedChange={(v) => setRowEmail(r.id, v)} className="data-[state=checked]:bg-[var(--brand)]" />
                </div>

                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => removeRow(r.id)}
                    title="Kuyruktan çıkar"
                    className="w-7 h-7 grid place-items-center text-[var(--fg-subtle)] hover:text-[#b3284c] hover:bg-[#b3284c]/10 rounded-[3px] transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
            {rows.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-[var(--fg-muted)]">Dosya kalmadı.</div>
            )}
          </div>
          {predictedCount > 0 && (
            <div className="px-4 py-2 border-t border-[var(--border)] flex items-center gap-2">
              <AiPill label="AD" />
              <span className="font-mono text-[10px] text-[var(--fg-subtle)]">= belge türü dosya adından tahmin edildi</span>
            </div>
          )}
        </div>

        {/* E-posta ayarları */}
        <div className="bg-[var(--bg-elevated)] border border-[var(--border)] p-5 grid gap-4">
          <div className="flex items-center gap-2">
            <Mail className="w-3.5 h-3.5 text-[var(--brand)]" />
            <Eyebrow tone="brand">E-posta Ayarları</Eyebrow>
            <span className="font-mono text-[10px] text-[var(--fg-subtle)]">— alıcılar tüm batch için ortak; satır anahtarı gönderimi açar/kapatır</span>
          </div>

          {/* Kime */}
          <div className="grid gap-2">
            <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">Kime</Label>
            {toRecipients.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {toRecipients.map((r) => (
                  <span key={r.email} className="inline-flex items-center gap-1 px-2.5 py-1 bg-[var(--bg-sunken)] border border-[var(--border)] text-[12px] rounded-[3px]">
                    <User className="w-3 h-3 opacity-50" />{r.name}
                    <X className="w-3 h-3 cursor-pointer ml-1 hover:text-[#b3284c]" onClick={() => removeRecipient("to", r.email)} />
                  </span>
                ))}
              </div>
            )}
            <Popover open={openTo} onOpenChange={setOpenTo}>
              <PopoverTrigger asChild>
                <Button variant="outline" role="combobox" className="w-full justify-start bg-[var(--bg)] border-[var(--border)] rounded-[3px] border-0 text-[var(--fg-muted)] text-sm">
                  <Plus className="w-4 h-4 mr-2" /> Alıcı Ara / Ekle...
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[400px] p-0 z-[100]" align="start">
                <Command>
                  <CommandInput placeholder="İsim ara..." />
                  <CommandList>
                    <CommandEmpty>Alıcı bulunamadı.</CommandEmpty>
                    <CommandGroup>
                      {emailRecipients.map((r) => (
                        <CommandItem key={r.email} value={r.name} onSelect={() => selectRecipient("to", { name: r.name, email: r.email ?? "" })}>
                          <Check className={cn("mr-2 h-4 w-4", toRecipients.find((x) => x.email === r.email) ? "opacity-100" : "opacity-0")} />
                          {r.name}
                          <span className="ml-auto text-[10px] text-[var(--fg-muted)]">{r.email}</span>
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
            <button type="button" onClick={() => setShowCc(true)} className="justify-self-start text-xs text-[var(--fg-muted)] hover:text-[var(--brand)] inline-flex items-center gap-1">
              <Plus className="w-3 h-3" /> CC Ekle
            </button>
          ) : (
            <div className="grid gap-2">
              <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">Bilgi (CC)</Label>
              {ccRecipients.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {ccRecipients.map((r) => (
                    <span key={r.email} className="inline-flex items-center gap-1 px-2.5 py-1 bg-[var(--bg-sunken)] border border-[var(--border)] text-[12px] rounded-[3px]">
                      <User className="w-3 h-3 opacity-50" />{r.name}
                      <X className="w-3 h-3 cursor-pointer ml-1 hover:text-[#b3284c]" onClick={() => removeRecipient("cc", r.email)} />
                    </span>
                  ))}
                </div>
              )}
              <Popover open={openCc} onOpenChange={setOpenCc}>
                <PopoverTrigger asChild>
                  <Button variant="outline" role="combobox" className="w-full justify-start bg-[var(--bg)] border-[var(--border)] rounded-[3px] border-0 text-[var(--fg-muted)] text-sm">
                    <Plus className="w-4 h-4 mr-2" /> CC'ye Alıcı Ekle...
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[400px] p-0 z-[100]" align="start">
                  <Command>
                    <CommandInput placeholder="İsim ara..." />
                    <CommandList>
                      <CommandEmpty>Alıcı bulunamadı.</CommandEmpty>
                      <CommandGroup>
                        {emailRecipients.map((r) => (
                          <CommandItem key={r.email} value={r.name} onSelect={() => selectRecipient("cc", { name: r.name, email: r.email ?? "" })}>
                            <Check className={cn("mr-2 h-4 w-4", ccRecipients.find((x) => x.email === r.email) ? "opacity-100" : "opacity-0")} />
                            {r.name}
                            <span className="ml-auto text-[10px] text-[var(--fg-muted)]">{r.email}</span>
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            </div>
          )}

          <div className="grid sm:grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="wb-teblig" className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">Tebliğ Tarihi (Opsiyonel)</Label>
              <Input id="wb-teblig" type="date" className="bg-[var(--bg)] border-[var(--border)] rounded-[3px]" value={tebligTarihi} onChange={(e) => setTebligTarihi(e.target.value)} />
            </div>
            <div className="flex items-start justify-between gap-3 p-3 bg-[var(--bg)] border border-[var(--border)]">
              <div className="min-w-0">
                <Label htmlFor="wb-confirm-per-file" className="font-display text-[13px] font-medium text-[var(--fg)]">Her dosyada e-posta ayarlarını ayrıca onayla</Label>
                <p className="text-[11.5px] text-[var(--fg-muted)] leading-relaxed mt-0.5">Kapalıyken e-posta penceresi açılmaz — yukarıdaki ayarlar tüm batch için kullanılır.</p>
              </div>
              <Switch id="wb-confirm-per-file" checked={confirmPerFile} onCheckedChange={setConfirmPerFile} className="data-[state=checked]:bg-[var(--brand)]" />
            </div>
          </div>
        </div>

        {/* Footer aksiyonları */}
        <div className="flex items-center justify-between gap-3 pb-8">
          <FlowButton variant="ghost" onClick={onCancel}>İptal</FlowButton>
          <FlowButton variant="primary" onClick={handleStart} disabled={total === 0} className="min-w-[200px]">
            Onaya Geç &amp; Analizi Başlat ({total} dosya)
            <ArrowRight className="w-3.5 h-3.5" />
          </FlowButton>
        </div>
      </main>
    </div>
  );
}
