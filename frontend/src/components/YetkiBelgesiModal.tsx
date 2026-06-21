import { useState, useEffect, useRef, Fragment, type ReactNode } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Printer, ChevronRight, ChevronLeft, FileText, Download, Loader2, ChevronDown, Check, X, Plus } from "lucide-react";
import { useConfig } from "@/hooks/useConfig";
import { useAuthRequest } from "@/hooks/useAuthRequest";
import { FlowButton } from "@/components/flow/primitives";
import { Eyebrow } from "@/components/dashboard/primitives";
import type { Client } from "@/pages/ClientList";
import { toast } from "sonner";

interface Props {
    open: boolean;
    onClose: () => void;
    client: Client;
}

interface AvukatDetay {
    ad: string;
    tc: string;
    sicil: string;
    address: string;
}

const CACHE_KEY = "yetki_belgesi_avukat_cache";

const STEP_DEFS = [
    { n: 1, label: "Avukatlar" },
    { n: 2, label: "Detaylar" },
    { n: 3, label: "Önizleme" },
] as const;

const inputCls = "bg-[var(--bg)] border-[var(--border)] rounded-[3px] h-10 text-sm";
const monoCls = `${inputCls} font-mono tracking-[0.02em]`;

function loadCache(): Record<string, { tc: string; sicil: string }> {
    try { return JSON.parse(localStorage.getItem(CACHE_KEY) || "{}"); }
    catch { return {}; }
}

function saveCache(cache: Record<string, { tc: string; sicil: string }>) {
    localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
}

function normalizeName(name: string): string {
    return name.toLocaleUpperCase("tr-TR").replace(/^AV\.\s*/i, "").replace(/\s+/g, " ").trim();
}

function formatDate(dateStr?: string): string {
    if (!dateStr) return "";
    // dateStr may be "2020-01-27" or "27.01.2020"
    if (dateStr.includes("-")) {
        const [y, m, d] = dateStr.split("-");
        return `${d}.${m}.${y}`;
    }
    return dateStr;
}

function toUpper(str?: string): string {
    return (str || "").toLocaleUpperCase("tr-TR");
}

function onlyDigits(value: string, max?: number): string {
    const d = value.replace(/\D/g, "");
    return max ? d.slice(0, max) : d;
}

function maskDate(value: string): string {
    const d = value.replace(/\D/g, "").slice(0, 8);
    if (d.length <= 2) return d;
    if (d.length <= 4) return `${d.slice(0, 2)}.${d.slice(2)}`;
    return `${d.slice(0, 2)}.${d.slice(2, 4)}.${d.slice(4)}`;
}

function isValidDateFormat(value: string): boolean {
    if (!value) return true;
    return /^\d{2}\.\d{2}\.\d{4}$/.test(value);
}

function sanitizeFilename(value: string): string {
    const ascii = value.normalize("NFKD").replace(/[̀-ͯ]/g, "");
    return ascii.replace(/[^A-Za-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
}

// ALLCAPS mono başlık + alt çizgi — Step 2 bölüm ayırıcısı
function SectionTitle({ children }: { children: ReactNode }) {
    return (
        <div className="flex items-center gap-3">
            <span className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--brand)] whitespace-nowrap">
                {children}
            </span>
            <span className="flex-1 h-px bg-[var(--border)]" />
        </div>
    );
}

// Label (ALLCAPS mono) + input sarmalayıcı
function Field({ label, required, hint, children }: { label: string; required?: boolean; hint?: string; children: ReactNode }) {
    return (
        <div className="flex flex-col gap-1.5 min-w-0">
            <label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                {label}{required && <span className="text-[var(--brand)] ml-1">*</span>}
            </label>
            {children}
            {hint && <span className="font-mono text-[9.5px] tracking-[0.02em] text-[var(--fg-subtle)]">{hint}</span>}
        </div>
    );
}

export function YetkiBelgesiModal({ open, onClose, client }: Props) {
    const { lawyers } = useConfig();
    const { authRequest } = useAuthRequest();
    const [step, setStep] = useState<1 | 2 | 3>(1);
    const [udfLoading, setUdfLoading] = useState(false);

    const avukatListesi: string[] = lawyers
        .map(l => l.name)
        .sort((a, b) => a.localeCompare(b, "tr"));

    // Step 1
    const [verenAd, setVerenAd] = useState("");
    const [yetkiliAdlar, setYetkiliAdlar] = useState<string[]>([]);
    const [verenOpen, setVerenOpen] = useState(false);
    const [yetkiliOpen, setYetkiliOpen] = useState(false);

    // Step 2 — avukat detayları
    const [buroAdres, setBuroAdres] = useState("");
    const [verenDetay, setVerenDetay] = useState<AvukatDetay>({ ad: "", tc: "", sicil: "", address: "" });
    const [yetkiliDetaylar, setYetkiliDetaylar] = useState<AvukatDetay[]>([]);

    // Step 2 — müvekkil (VEKİL EDEN) ek alanlar
    const [muvekkillAdres, setMuvekkillAdres] = useState(client.address || "");
    const [muvekkillIl, setMuvekkillIl] = useState(client.il || "");
    const [vergiNo, setVergiNo] = useState(client.tc_no || "");

    // Step 2 — Dayanak Vekaletname (müvekkilden otomatik, düzenlenebilir)
    const [dayNoterlik, setDayNoterlik] = useState(client.noterlik || "");
    const [dayTarih, setDayTarih] = useState(
        client.vekaletname_tarihi ? formatDate(String(client.vekaletname_tarihi)) : ""
    );
    const [dayYevmiye, setDayYevmiye] = useState(client.yevmiye_no || "");

    // Step 2 — Kapsam
    const [kapsam, setKapsam] = useState("İlgili Vekaletnamedeki yetkilerin tamamı");

    const printRef = useRef<HTMLDivElement>(null);

    function lookupAvukat(ad: string): { tc: string; sicil: string; address: string } {
        const cache = loadCache();
        const normalAd = normalizeName(ad);
        const cached = cache[normalAd] || { tc: "", sicil: "" };
        const match = lawyers.find(l => normalizeName(l.name) === normalAd);
        if (match) {
            return {
                tc: match.tc_no || cached.tc || "",
                sicil: match.sicil_no || cached.sicil || "",
                address: match.address || "",
            };
        }
        return { tc: cached.tc || "", sicil: cached.sicil || "", address: "" };
    }

    useEffect(() => {
        if (step !== 2) return;

        if (verenDetay.ad !== verenAd) {
            const v = lookupAvukat(verenAd);
            setVerenDetay({ ad: verenAd, tc: v.tc, sicil: v.sicil, address: v.address });
            if (v.address) setBuroAdres(v.address);
        }

        setYetkiliDetaylar(prev => yetkiliAdlar.map(ad => {
            const existing = prev.find(d => d.ad === ad);
            if (existing) return existing;
            const l = lookupAvukat(ad);
            return { ad, tc: l.tc, sicil: l.sicil, address: l.address };
        }));
    }, [step, verenAd, yetkiliAdlar.join(",")]);

    function toggleYetkili(ad: string) {
        setYetkiliAdlar(prev =>
            prev.includes(ad) ? prev.filter(a => a !== ad) : [...prev, ad]
        );
    }

    function updateYetkili(idx: number, field: "tc" | "sicil" | "address", value: string) {
        setYetkiliDetaylar(prev => prev.map((d, i) => i === idx ? { ...d, [field]: value } : d));
    }

    function goToStep3() {
        const cache = loadCache();
        cache[normalizeName(verenDetay.ad)] = { tc: verenDetay.tc, sicil: verenDetay.sicil };
        yetkiliDetaylar.forEach(d => { cache[normalizeName(d.ad)] = { tc: d.tc, sicil: d.sicil }; });
        saveCache(cache);
        setStep(3);
    }

    function handlePrint() {
        const content = printRef.current?.innerHTML;
        if (!content) return;
        const win = window.open("", "_blank", "width=820,height=960");
        if (!win) {
            toast.error("Yazdırma penceresi açılamadı. Tarayıcınızın bu site için pop-up engelleyiciyi devre dışı bırakın.");
            return;
        }
        win.document.write(`<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8"/>
  <title>Yetki Belgesi</title>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:"Times New Roman",Times,serif;font-size:12pt;color:#000;background:#fff;padding:40px 55px;line-height:1.7}
    .yb-title{text-align:center;font-size:15pt;font-weight:bold;letter-spacing:3px;margin-bottom:32px;border-bottom:2px solid #000;padding-bottom:10px}
    .yb-sec{font-weight:bold;font-size:11pt;margin-top:22px;margin-bottom:6px;letter-spacing:.5px}
    .yb-row{padding-left:16px;margin-bottom:10px}
    .yb-name{font-weight:bold}
    .yb-detail{font-size:11pt}
    .yb-kanun{margin-top:32px;font-size:11pt;line-height:1.8;border-top:1px solid #bbb;padding-top:16px}
    .yb-imza{margin-top:44px;font-weight:bold;font-size:12pt}
    @media print{body{padding:25px 35px}}
  </style>
</head>
<body>${content}<script>window.onload=function(){window.print()}<\/script></body>
</html>`);
        win.document.close();
    }

    async function handleDownloadUdf() {
        setUdfLoading(true);
        try {
            const payload = {
                veren: { ad: verenDetay.ad, tc: verenDetay.tc, sicil: verenDetay.sicil },
                yetkililar: yetkiliDetaylar.map(d => ({ ad: d.ad, tc: d.tc, sicil: d.sicil, address: d.address })),
                buro_adres: buroAdres,
                muvekkil: {
                    ad: client.name,
                    adres: muvekkillAdres,
                    il: muvekkillIl,
                    tc_vergi: vergiNo,
                    client_type: client.client_type || "Individual",
                },
                dayanak: { noterlik: dayNoterlik, tarih: dayTarih, yevmiye: dayYevmiye },
                kapsam,
            };
            const res = await authRequest("/api/yetki-belgesi/udf", "POST", payload);
            if (!res?.ok) throw new Error(`Sunucu hatası (${res?.status ?? "bilinmiyor"})`);
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `yetki_belgesi_${(sanitizeFilename(client.name || "belge") || "belge").substring(0, 30)}.udf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            toast.success("UDF dosyası indirildi.");
        } catch (e) {
            console.error("UDF indirme hatası:", e);
            const msg = e instanceof Error ? e.message : "Bilinmeyen hata";
            toast.error(`UDF indirilemedi: ${msg}`);
        } finally {
            setUdfLoading(false);
        }
    }

    function reset() {
        setStep(1); setVerenAd(""); setYetkiliAdlar([]);
        setVerenOpen(false); setYetkiliOpen(false);
        setBuroAdres("");
        setVerenDetay({ ad: "", tc: "", sicil: "", address: "" }); setYetkiliDetaylar([]);
        setMuvekkillAdres(client.address || ""); setMuvekkillIl(client.il || "");
        setVergiNo(client.tc_no || "");
        setDayNoterlik(client.noterlik || "");
        setDayTarih(client.vekaletname_tarihi ? formatDate(String(client.vekaletname_tarihi)) : "");
        setDayYevmiye(client.yevmiye_no || "");
        setKapsam("İlgili Vekaletnamedeki yetkilerin tamamı");
    }

    function handleClose() { reset(); onClose(); }

    // Belge önizleme için müvekkil tam adres satırı
    const muvekkillTamAdres = [muvekkillAdres, muvekkillIl].filter(Boolean).join(" ");

    // Dayanak satırı — UDF üreticisiyle aynı kurallar: noterlik büyük, tarih/yevmiye olduğu gibi
    const dayanakSatiri = [
        toUpper(dayNoterlik),
        dayTarih ? `${dayTarih} tarihli` : "",
        dayYevmiye ? `Yevmiye No: ${dayYevmiye}` : "",
    ].filter(Boolean).join(", ");

    const step1Valid = verenAd !== "" && yetkiliAdlar.length > 0;
    const step2Valid =
        verenDetay.tc.trim().length === 11 &&
        verenDetay.sicil.trim() !== "" &&
        yetkiliDetaylar.every(d => d.ad.trim() !== "") &&
        isValidDateFormat(dayTarih);

    const forwardDisabled = (step === 1 && !step1Valid) || (step === 2 && !step2Valid);

    function handleForward() {
        if (step === 1 && step1Valid) setStep(2);
        else if (step === 2 && step2Valid) goToStep3();
    }

    // Step 1 — eklenebilecek (veren değil + henüz seçilmemiş) avukatlar
    const eklenebilir = avukatListesi.filter(ad => ad !== verenAd && !yetkiliAdlar.includes(ad));
    const isCorporate = client.client_type === "Corporate";

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="theme-classic max-w-[760px] max-h-[90vh] flex flex-col bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none p-0 gap-0">
                {/* ── Başlık ── */}
                <DialogHeader className="shrink-0 px-6 pt-6 pb-5 border-b border-[var(--border)]">
                    <div className="flex items-start gap-3">
                        <div className="w-11 h-11 grid place-items-center bg-[var(--brand-soft)] text-[var(--brand)] shrink-0">
                            <FileText className="w-5 h-5" strokeWidth={1.6} />
                        </div>
                        <div className="min-w-0 grid gap-1.5">
                            <div className="flex items-center gap-2.5 flex-wrap">
                                <DialogTitle className="font-display text-[20px] font-medium tracking-[-0.005em] text-[var(--fg)] leading-tight">
                                    Yetki Belgesi Oluştur
                                </DialogTitle>
                                <span className="font-mono text-[9px] tracking-[0.16em] uppercase font-semibold text-[var(--brand)] bg-[var(--brand-soft)] border border-[var(--brand)]/30 px-1.5 py-0.5">
                                    3 Adım
                                </span>
                            </div>
                            <DialogDescription className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed">
                                <span className="font-semibold text-[var(--fg)]">{toUpper(client.name)}</span> müvekkili için vekaletten doğan yetki belgesi düzenleyin.
                            </DialogDescription>
                        </div>
                    </div>
                </DialogHeader>

                {/* ── Adım göstergesi ── */}
                <div className="shrink-0 flex items-center gap-3 px-6 pt-5 pb-4 border-b border-[var(--border)]">
                    {STEP_DEFS.map((s, i) => (
                        <Fragment key={s.n}>
                            <div className="flex items-center gap-2.5">
                                <div className={`w-7 h-7 rounded-full grid place-items-center font-mono text-[11px] font-semibold border transition-all
                                    ${step > s.n ? "bg-[var(--brand)] border-[var(--brand)] text-[var(--brand-fg)]"
                                        : step === s.n ? "bg-[var(--brand-soft)] border-[var(--brand)] text-[var(--brand)]"
                                            : "bg-[var(--bg)] border-[var(--border-strong)] text-[var(--fg-subtle)]"}`}>
                                    {step > s.n ? <Check className="w-3.5 h-3.5" strokeWidth={2.6} /> : s.n}
                                </div>
                                <span className={`font-mono text-[10px] tracking-[0.18em] uppercase font-semibold transition-colors
                                    ${step >= s.n ? "text-[var(--fg)]" : "text-[var(--fg-subtle)]"}`}>
                                    {s.label}
                                </span>
                            </div>
                            {i < STEP_DEFS.length - 1 && (
                                <div className={`flex-1 h-px transition-colors ${step > s.n ? "bg-[var(--brand)]" : "bg-[var(--border)]"}`} />
                            )}
                        </Fragment>
                    ))}
                </div>

                {/* ── Gövde (scroll) ── */}
                <div className="flex-1 overflow-y-auto min-h-0 px-6 py-5">

                    {/* ── ADIM 1 ── */}
                    {step === 1 && (
                        <div className="flex flex-col gap-6">
                            {/* Bilgi banner'ı */}
                            <div className="bg-[var(--brand-soft)] border-l-[3px] border-[var(--brand)] px-4 py-3">
                                <Eyebrow tone="brand">1. Adım · Avukat Seçimi</Eyebrow>
                                <p className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed mt-1.5">
                                    <span className="font-semibold text-[var(--fg)]">{toUpper(client.name)}</span> isimli müvekkil için yetki belgesi düzenlenecektir. Belgeyi <strong className="font-semibold text-[var(--fg)]">veren</strong> avukatı ve <strong className="font-semibold text-[var(--fg)]">yetkilendirilen</strong> avukatları seçin.
                                </p>
                            </div>

                            {/* Veren avukat */}
                            <div className="flex flex-col gap-2">
                                <Eyebrow>Veren Avukat</Eyebrow>
                                <Popover open={verenOpen} onOpenChange={setVerenOpen}>
                                    <PopoverTrigger asChild>
                                        <button
                                            type="button"
                                            role="combobox"
                                            aria-expanded={verenOpen}
                                            className="flex items-center justify-between w-full h-10 px-3 bg-[var(--bg)] border border-[var(--border)] rounded-[3px] text-sm text-left hover:border-[var(--border-strong)] transition-colors"
                                        >
                                            {verenAd
                                                ? <span className="font-medium text-[var(--fg)] truncate">{toUpper(verenAd)}</span>
                                                : <span className="text-[var(--fg-subtle)]">Avukat seçin…</span>}
                                            <ChevronDown className="w-4 h-4 shrink-0 opacity-50" />
                                        </button>
                                    </PopoverTrigger>
                                    <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                                        <Command>
                                            <CommandInput placeholder="Avukat ara..." className="h-9" />
                                            <CommandList>
                                                <CommandEmpty>Sonuç bulunamadı.</CommandEmpty>
                                                <CommandGroup>
                                                    {avukatListesi.map(ad => (
                                                        <CommandItem
                                                            key={ad}
                                                            value={ad}
                                                            onSelect={() => {
                                                                setVerenAd(ad);
                                                                setYetkiliAdlar(prev => prev.filter(a => a !== ad));
                                                                setVerenOpen(false);
                                                            }}
                                                        >
                                                            <Check className={`mr-2 w-4 h-4 ${verenAd === ad ? "opacity-100 text-[var(--brand)]" : "opacity-0"}`} />
                                                            {toUpper(ad)}
                                                        </CommandItem>
                                                    ))}
                                                </CommandGroup>
                                            </CommandList>
                                        </Command>
                                    </PopoverContent>
                                </Popover>
                            </div>

                            {/* Yetkilendirilen avukatlar — chip picker */}
                            <div className="flex flex-col gap-2">
                                <div className="flex items-center justify-between">
                                    <Eyebrow>Yetkilendirilen Avukat(lar)</Eyebrow>
                                    <span className="font-mono text-[10px] tracking-[0.06em] text-[var(--fg-subtle)]">
                                        ({yetkiliAdlar.length} seçili)
                                    </span>
                                </div>
                                <div className="flex flex-wrap items-center gap-2">
                                    {yetkiliAdlar.map(ad => (
                                        <span key={ad} className="inline-flex items-center gap-1.5 text-[11px] font-semibold bg-[var(--brand-soft)] text-[var(--brand)] border border-[var(--brand)]/30 rounded-[3px] pl-2.5 pr-1.5 py-1.5">
                                            {toUpper(ad)}
                                            <button
                                                type="button"
                                                onClick={() => toggleYetkili(ad)}
                                                className="grid place-items-center hover:text-[var(--brand-hover)] transition-colors"
                                                aria-label={`${toUpper(ad)} kaldır`}
                                            >
                                                <X className="w-3 h-3" />
                                            </button>
                                        </span>
                                    ))}

                                    <Popover open={yetkiliOpen} onOpenChange={v => { if (verenAd) setYetkiliOpen(v); }}>
                                        <PopoverTrigger asChild>
                                            <button
                                                type="button"
                                                disabled={!verenAd}
                                                className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-[var(--fg-muted)] border border-dashed border-[var(--border-strong)] rounded-[3px] px-2.5 py-1.5 hover:text-[var(--brand)] hover:border-[var(--brand)]/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                <Plus className="w-3.5 h-3.5" /> Avukat Ekle
                                            </button>
                                        </PopoverTrigger>
                                        <PopoverContent className="w-[260px] p-0" align="start">
                                            <Command>
                                                <CommandInput placeholder="Avukat ara..." className="h-9" />
                                                <CommandList>
                                                    <CommandEmpty>Eklenebilecek başka avukat yok.</CommandEmpty>
                                                    <CommandGroup>
                                                        {eklenebilir.map(ad => (
                                                            <CommandItem
                                                                key={ad}
                                                                value={ad}
                                                                onSelect={() => toggleYetkili(ad)}
                                                            >
                                                                <Plus className="mr-2 w-4 h-4 text-[var(--brand)]" />
                                                                {toUpper(ad)}
                                                            </CommandItem>
                                                        ))}
                                                    </CommandGroup>
                                                </CommandList>
                                            </Command>
                                        </PopoverContent>
                                    </Popover>
                                </div>
                                {!verenAd && (
                                    <span className="font-mono text-[9.5px] tracking-[0.02em] text-[var(--fg-subtle)]">
                                        Önce yetki veren avukatı seçin.
                                    </span>
                                )}
                            </div>
                        </div>
                    )}

                    {/* ── ADIM 2 ── */}
                    {step === 2 && (
                        <div className="flex flex-col gap-7">

                            {/* Veren avukat detayları */}
                            <div className="flex flex-col gap-3">
                                <SectionTitle>Veren Avukat · Detayları</SectionTitle>
                                <p className="font-display text-[16px] font-medium text-[var(--fg)]">{toUpper(verenDetay.ad)}</p>
                                <div className="grid grid-cols-2 gap-4">
                                    <Field label="T.C. Kimlik No" required>
                                        <Input value={verenDetay.tc} onChange={e => setVerenDetay(d => ({ ...d, tc: onlyDigits(e.target.value, 11) }))}
                                            inputMode="numeric" maxLength={11} className={monoCls} />
                                    </Field>
                                    <Field label="Sicil No" required>
                                        <Input value={verenDetay.sicil} onChange={e => setVerenDetay(d => ({ ...d, sicil: onlyDigits(e.target.value, 10) }))}
                                            inputMode="numeric" className={monoCls} />
                                    </Field>
                                </div>
                                <Field label="Büro Adresi">
                                    <Input value={buroAdres} onChange={e => setBuroAdres(e.target.value)} className={inputCls} />
                                </Field>
                            </div>

                            {/* Yetkilendirilen avukatlar */}
                            <div className="flex flex-col gap-3">
                                <SectionTitle>
                                    Yetkilendirilen Avukat{yetkiliDetaylar.length > 1 ? `(${yetkiliDetaylar.length})` : ""} · Detayları
                                </SectionTitle>
                                {yetkiliDetaylar.length === 0 && (
                                    <p className="text-[12px] text-[var(--fg-subtle)]">Henüz yetkilendirilen avukat seçilmedi.</p>
                                )}
                                {yetkiliDetaylar.map((detay, idx) => (
                                    <div key={detay.ad} className="border-l-[3px] border-[var(--brand)] bg-[var(--bg-sunken)]/40 pl-4 pr-4 py-3 flex flex-col gap-3">
                                        <p className="font-display text-[14px] font-medium text-[var(--fg)]">{toUpper(detay.ad)}</p>
                                        <div className="grid grid-cols-2 gap-4">
                                            <Field label="T.C. Kimlik No">
                                                <Input value={detay.tc} onChange={e => updateYetkili(idx, "tc", onlyDigits(e.target.value, 11))}
                                                    inputMode="numeric" maxLength={11} className={monoCls} />
                                            </Field>
                                            <Field label="Sicil No">
                                                <Input value={detay.sicil} onChange={e => updateYetkili(idx, "sicil", onlyDigits(e.target.value, 10))}
                                                    inputMode="numeric" className={monoCls} />
                                            </Field>
                                        </div>
                                        <Field label="Adres" hint='Boşsa "Aynı adreste mukim" yazılır'>
                                            <Input value={detay.address} onChange={e => updateYetkili(idx, "address", e.target.value)} className={inputCls} />
                                        </Field>
                                    </div>
                                ))}
                            </div>

                            {/* Müvekkil (vekil eden) ek bilgiler */}
                            <div className="flex flex-col gap-3">
                                <SectionTitle>Müvekkil (Vekil Eden) · Ek Bilgiler</SectionTitle>
                                <Field label="Tam Ad / Ticari Ünvan">
                                    <Input value={toUpper(client.name)} readOnly className={`${inputCls} text-[var(--fg-muted)]`} />
                                </Field>
                                <div className="grid grid-cols-2 gap-4">
                                    <Field label={isCorporate ? "Vergi No" : "T.C. / Vergi No"}>
                                        <Input value={vergiNo} onChange={e => setVergiNo(onlyDigits(e.target.value, isCorporate ? 10 : 11))}
                                            inputMode="numeric" maxLength={isCorporate ? 10 : 11} className={monoCls} />
                                    </Field>
                                    <Field label="İl">
                                        <Input value={muvekkillIl} onChange={e => setMuvekkillIl(e.target.value)} className={inputCls} />
                                    </Field>
                                </div>
                                <Field label="Adres">
                                    <Input value={muvekkillAdres} onChange={e => setMuvekkillAdres(e.target.value)} className={inputCls} />
                                </Field>
                            </div>

                            {/* Dayanak vekaletname */}
                            <div className="flex flex-col gap-3">
                                <SectionTitle>Dayanak Vekaletname</SectionTitle>
                                <div className="grid grid-cols-[1.4fr_1fr_1fr] gap-4">
                                    <Field label="Noterlik">
                                        <Input value={dayNoterlik} onChange={e => setDayNoterlik(e.target.value)} className={inputCls} />
                                    </Field>
                                    <Field label="Tarih (GG.AA.YYYY)">
                                        <Input value={dayTarih} onChange={e => setDayTarih(maskDate(e.target.value))}
                                            inputMode="numeric" maxLength={10}
                                            className={`${monoCls} ${dayTarih && !isValidDateFormat(dayTarih) ? "border-[var(--brand)]" : ""}`} />
                                        {dayTarih && !isValidDateFormat(dayTarih) && (
                                            <span className="font-mono text-[9.5px] text-[var(--brand)]">GG.AA.YYYY formatında olmalı</span>
                                        )}
                                    </Field>
                                    <Field label="Yevmiye No">
                                        <Input value={dayYevmiye} onChange={e => setDayYevmiye(onlyDigits(e.target.value, 12))}
                                            inputMode="numeric" className={monoCls} />
                                    </Field>
                                </div>
                            </div>

                            {/* Kapsam */}
                            <div className="flex flex-col gap-3">
                                <SectionTitle>Yetki Kapsamı</SectionTitle>
                                <Input value={kapsam} onChange={e => setKapsam(e.target.value)} className={inputCls} />
                            </div>
                        </div>
                    )}

                    {/* ── ADIM 3 ── */}
                    {step === 3 && (
                        <div className="flex flex-col gap-4">
                            {/* Önizleme şeridi */}
                            <div className="bg-[var(--brand-soft)] border-l-[3px] border-[var(--brand)] px-4 py-3">
                                <Eyebrow tone="brand">Önizleme</Eyebrow>
                                <p className="text-[12px] text-[var(--fg-muted)] leading-relaxed mt-1.5">
                                    Aşağıdaki belge yazdırılacak veya UYAP'a UDF formatında kaydedilecektir. Bilgileri kontrol edin.
                                </p>
                            </div>

                            {/* Kağıt simülasyonu — temadan bağımsız, daima krem + serif */}
                            <div
                                className="overflow-y-auto max-h-[52vh]"
                                style={{
                                    background: "#fdfaf3",
                                    color: "#14110d",
                                    boxShadow: "0 8px 28px -12px rgba(20,15,12,0.25), 0 1px 3px rgba(20,15,12,0.08)",
                                }}
                            >
                                <div ref={printRef} style={{ fontFamily: 'Georgia, "Times New Roman", serif', fontSize: "11pt", lineHeight: 1.7, padding: "34px 40px" }}>

                                    {/* Başlık */}
                                    <div style={{ textAlign: "center", fontWeight: "bold", fontSize: "15pt", letterSpacing: "3px", marginBottom: "30px", borderBottom: "2px solid #000", paddingBottom: "10px" }}>
                                        YETKİ BELGESİ
                                    </div>

                                    {/* Yetki veren */}
                                    <div style={{ fontWeight: "bold", marginTop: "20px", marginBottom: "6px" }}>YETKİ BELGESİ VEREN AVUKAT :</div>
                                    <div style={{ paddingLeft: "16px", marginBottom: "14px" }}>
                                        <div style={{ fontWeight: "bold" }}>1. Av. {toUpper(verenDetay.ad)}</div>
                                        <div>
                                            ({toUpper(buroAdres)} adresinde mukim
                                            {verenDetay.tc && `, T.C. Kimlik No: ${verenDetay.tc}`}
                                            {verenDetay.sicil && `, ${verenDetay.sicil} sicil no'lu`})
                                        </div>
                                    </div>

                                    {/* Yetkili kılınanlar */}
                                    <div style={{ fontWeight: "bold", marginTop: "20px", marginBottom: "6px" }}>YETKİLİ KILINAN AVUKATLAR :</div>
                                    {yetkiliDetaylar.map((detay, idx) => (
                                        <div key={detay.ad} style={{ paddingLeft: "16px", marginBottom: "10px" }}>
                                            <div style={{ fontWeight: "bold" }}>{idx + 1}. Av. {toUpper(detay.ad)}</div>
                                            <div>
                                                ({detay.address ? `${toUpper(detay.address)} adresinde mukim` : "Aynı adreste mukim"}
                                                {detay.tc && `, T.C. Kimlik No: ${detay.tc}`}
                                                {detay.sicil && `, ${detay.sicil} sicil no'lu`})
                                            </div>
                                        </div>
                                    ))}

                                    {/* Vekil eden */}
                                    <div style={{ fontWeight: "bold", marginTop: "20px", marginBottom: "6px" }}>VEKİL EDEN :</div>
                                    <div style={{ paddingLeft: "16px", marginBottom: "14px" }}>
                                        <div style={{ fontWeight: "bold" }}>1. {toUpper(client.name)}</div>
                                        <div>
                                            ({toUpper(muvekkillTamAdres)} adresinde mukim
                                            {isCorporate
                                                ? (vergiNo ? `, Vergi No: ${vergiNo}` : "")
                                                : (vergiNo ? `, T.C. Kimlik No: ${vergiNo}` : "")
                                            })
                                        </div>
                                    </div>

                                    {/* Dayanak vekaletname */}
                                    {dayanakSatiri && (
                                        <>
                                            <div style={{ fontWeight: "bold", marginTop: "20px", marginBottom: "6px" }}>DAYANAK VEKALETNAME :</div>
                                            <div style={{ paddingLeft: "16px", marginBottom: "14px" }}>
                                                {dayanakSatiri}
                                            </div>
                                        </>
                                    )}

                                    {/* Kapsam */}
                                    {kapsam && (
                                        <>
                                            <div style={{ fontWeight: "bold", marginTop: "20px", marginBottom: "6px" }}>YETKİ BELGESİNİN KAPSAMI :</div>
                                            <div style={{ paddingLeft: "16px", marginBottom: "14px" }}>{kapsam}</div>
                                        </>
                                    )}

                                    {/* Kanun maddesi */}
                                    <div style={{ marginTop: "28px", fontSize: "11pt", lineHeight: "1.8", borderTop: "1px solid #bbb", paddingTop: "14px" }}>
                                        1136 sayılı Avukatlık Kanunu'nu değiştiren 4667 Sayılı Kanunun 36. maddesi ile 56. maddesine eklenen hüküm uyarınca vekaletname yerine geçmek üzere işbu yetki belgesi tarafımdan düzenlenmiştir.
                                    </div>

                                    {/* İmza */}
                                    <div style={{ marginTop: "42px", fontWeight: "bold", fontSize: "12pt" }}>
                                        Av. {toUpper(verenDetay.ad)}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* ── Footer navigasyonu ── */}
                <div className="shrink-0 flex items-center gap-2 px-6 py-4 border-t border-[var(--border)] bg-[var(--bg)]">
                    {step > 1 && (
                        <FlowButton variant="ghost" onClick={() => setStep(step === 3 ? 2 : 1)}>
                            <ChevronLeft className="w-4 h-4" /> Geri
                        </FlowButton>
                    )}
                    <div className="ml-auto flex items-center gap-2">
                        <FlowButton variant="secondary" onClick={handleClose}>İptal</FlowButton>
                        {step < 3 ? (
                            <FlowButton variant="primary" disabled={forwardDisabled} onClick={handleForward}>
                                Devam <ChevronRight className="w-4 h-4" />
                            </FlowButton>
                        ) : (
                            <>
                                <FlowButton variant="secondary" onClick={handleDownloadUdf} disabled={udfLoading}>
                                    {udfLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />} UDF İndir
                                </FlowButton>
                                <FlowButton variant="primary" onClick={handlePrint}>
                                    <Printer className="w-4 h-4" /> Yazdır
                                </FlowButton>
                            </>
                        )}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
