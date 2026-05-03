import { useState, useEffect, useRef } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Printer, ChevronRight, ChevronLeft, FileText, Download, Loader2 } from "lucide-react";
import { useConfig } from "@/hooks/useConfig";
import { useAuthRequest } from "@/hooks/useAuthRequest";
import type { Client } from "@/pages/ClientList";

interface Props {
    open: boolean;
    onClose: () => void;
    client: Client;
}

interface AvukatDetay {
    ad: string;
    tc: string;
    sicil: string;
}

const CACHE_KEY = "yetki_belgesi_avukat_cache";

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

export function YetkiBelgesiModal({ open, onClose, client }: Props) {
    const { lawyers } = useConfig();
    const { authRequest } = useAuthRequest();
    const [step, setStep] = useState<1 | 2 | 3>(1);
    const [udfLoading, setUdfLoading] = useState(false);

    const avukatListesi: string[] = (client.vekil_avukatlar || "")
        .split(";").map(s => s.trim()).filter(Boolean);

    // Step 1
    const [verenAd, setVerenAd] = useState("");
    const [yetkiliAdlar, setYetkiliAdlar] = useState<string[]>([]);

    // Step 2 — avukat detayları
    const [buroAdres, setBuroAdres] = useState(client.address || "");
    const [verenDetay, setVerenDetay] = useState<AvukatDetay>({ ad: "", tc: "", sicil: "" });
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

    function lookupAvukat(ad: string): { tc: string; sicil: string } {
        const cache = loadCache();
        const normalAd = normalizeName(ad);
        const match = lawyers.find(l => normalizeName(l.name) === normalAd);
        if (match && (match.tc_no || match.sicil_no)) {
            return { tc: match.tc_no || "", sicil: match.sicil_no || "" };
        }
        return cache[normalAd] || { tc: "", sicil: "" };
    }

    useEffect(() => {
        if (step !== 2) return;
        const v = lookupAvukat(verenAd);
        setVerenDetay({ ad: verenAd, tc: v.tc, sicil: v.sicil });
        setYetkiliDetaylar(yetkiliAdlar.map(ad => {
            const l = lookupAvukat(ad);
            return { ad, tc: l.tc, sicil: l.sicil };
        }));
    }, [step]);

    function toggleYetkili(ad: string) {
        setYetkiliAdlar(prev =>
            prev.includes(ad) ? prev.filter(a => a !== ad) : [...prev, ad]
        );
    }

    function updateYetkili(idx: number, field: "tc" | "sicil", value: string) {
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
        if (!win) return;
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
                yetkililar: yetkiliDetaylar.map(d => ({ ad: d.ad, tc: d.tc, sicil: d.sicil })),
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
            if (!res?.ok) throw new Error("Sunucu hatası");
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `yetki_belgesi_${(client.name || "belge").replace(/\s+/g, "_").substring(0, 30)}.udf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            console.error("UDF indirme hatası:", e);
        } finally {
            setUdfLoading(false);
        }
    }

    function reset() {
        setStep(1); setVerenAd(""); setYetkiliAdlar([]);
        setBuroAdres(client.address || "");
        setVerenDetay({ ad: "", tc: "", sicil: "" }); setYetkiliDetaylar([]);
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

    // Dayanak satırı
    const dayanakSatiri = [
        dayNoterlik,
        dayTarih ? `${dayTarih} tarihli` : "",
        dayYevmiye ? `Yevmiye No: ${dayYevmiye}` : "",
    ].filter(Boolean).join(", ");

    const step1Valid = verenAd !== "" && yetkiliAdlar.length > 0;
    const step2Valid = verenDetay.tc.trim() !== "";

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="max-w-[640px] max-h-[90vh] overflow-y-auto bg-card border-border text-foreground">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-[16px]">
                        <FileText className="w-5 h-5 text-rose-500" />
                        Yetki Belgesi Oluştur
                    </DialogTitle>
                </DialogHeader>

                {/* Adım göstergesi */}
                <div className="flex items-center gap-2 mb-1">
                    {[1, 2, 3].map(s => (
                        <div key={s} className="flex items-center gap-2">
                            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-colors
                                ${step === s ? "bg-rose-600 border-rose-600 text-white"
                                    : step > s ? "bg-rose-600/20 border-rose-600/50 text-rose-400"
                                        : "bg-secondary border-border text-muted-foreground"}`}>
                                {s}
                            </div>
                            {s < 3 && <div className={`h-px w-8 ${step > s ? "bg-rose-600/50" : "bg-border"}`} />}
                        </div>
                    ))}
                    <span className="text-xs text-muted-foreground ml-2">
                        {step === 1 && "Tarafları Seç"}
                        {step === 2 && "Bilgileri Tamamla"}
                        {step === 3 && "Önizle ve Yazdır"}
                    </span>
                </div>

                {/* ── ADIM 1 ── */}
                {step === 1 && (
                    <div className="flex flex-col gap-6">
                        <div className="flex flex-col gap-3">
                            <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Yetki Belgesi Veren Avukat</span>
                            <div className="flex flex-col gap-2">
                                {avukatListesi.map(ad => (
                                    <label key={ad} className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${verenAd === ad ? "border-rose-500/60 bg-rose-500/5" : "border-border hover:bg-accent/5"}`}>
                                        <input type="radio" name="veren" value={ad} checked={verenAd === ad}
                                            onChange={() => { setVerenAd(ad); setYetkiliAdlar(prev => prev.filter(a => a !== ad)); }}
                                            className="accent-rose-600 w-4 h-4" />
                                        <span className="text-[14px] font-medium">Av. {toUpper(ad)}</span>
                                    </label>
                                ))}
                            </div>
                        </div>

                        <div className="flex flex-col gap-3">
                            <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Yetkili Kılınan Avukatlar</span>
                            <div className="flex flex-col gap-2">
                                {avukatListesi.filter(ad => ad !== verenAd).map(ad => (
                                    <label key={ad} className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${yetkiliAdlar.includes(ad) ? "border-rose-500/60 bg-rose-500/5" : "border-border hover:bg-accent/5"}`}>
                                        <Checkbox checked={yetkiliAdlar.includes(ad)} onCheckedChange={() => toggleYetkili(ad)}
                                            className="border-muted-foreground data-[state=checked]:bg-rose-600 data-[state=checked]:border-rose-600" />
                                        <span className="text-[14px] font-medium">Av. {toUpper(ad)}</span>
                                    </label>
                                ))}
                                {verenAd === "" && <p className="text-xs text-muted-foreground italic px-1">Önce yetki veren avukatı seçin.</p>}
                            </div>
                        </div>

                        <div className="flex justify-end pt-2">
                            <Button disabled={!step1Valid} onClick={() => setStep(2)} className="bg-rose-600 hover:bg-rose-700 text-white gap-2">
                                İleri <ChevronRight className="w-4 h-4" />
                            </Button>
                        </div>
                    </div>
                )}

                {/* ── ADIM 2 ── */}
                {step === 2 && (
                    <div className="flex flex-col gap-5">

                        {/* Büro adresi */}
                        <div className="flex flex-col gap-2 p-4 rounded-xl bg-secondary/20 border border-border">
                            <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Büro Adresi (Avukatlar için ortak)</span>
                            <Input value={buroAdres} onChange={e => setBuroAdres(e.target.value)}
                                placeholder="BÜYÜKDERE CADDESİ NO:239/9 SARIYER İSTANBUL"
                                className="bg-secondary/30 border-border" />
                        </div>

                        {/* Yetki veren avukat */}
                        <div className="flex flex-col gap-3 p-4 rounded-xl bg-secondary/20 border border-border">
                            <span className="text-[11px] font-bold uppercase tracking-widest text-rose-400">Yetki Veren Avukat</span>
                            <p className="text-[13px] font-semibold">Av. {toUpper(verenDetay.ad)}</p>
                            <div className="grid grid-cols-2 gap-3">
                                <div className="space-y-1">
                                    <Label className="text-[11px] text-muted-foreground">T.C. Kimlik No <span className="text-rose-500">*</span></Label>
                                    <Input value={verenDetay.tc} onChange={e => setVerenDetay(d => ({ ...d, tc: e.target.value }))}
                                        placeholder="00000000000" maxLength={11} className="bg-secondary/30 border-border font-mono" />
                                </div>
                                <div className="space-y-1">
                                    <Label className="text-[11px] text-muted-foreground">Baro Sicil No</Label>
                                    <Input value={verenDetay.sicil} onChange={e => setVerenDetay(d => ({ ...d, sicil: e.target.value }))}
                                        placeholder="18670" className="bg-secondary/30 border-border font-mono" />
                                </div>
                            </div>
                        </div>

                        {/* Yetkili kılınanlar */}
                        <div className="flex flex-col gap-3">
                            <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Yetkili Kılınan Avukatlar</span>
                            {yetkiliDetaylar.map((detay, idx) => (
                                <div key={detay.ad} className="flex flex-col gap-2 p-4 rounded-xl bg-secondary/10 border border-border">
                                    <p className="text-[12px] font-semibold">{idx + 1}. Av. {toUpper(detay.ad)}</p>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="space-y-1">
                                            <Label className="text-[11px] text-muted-foreground">T.C. Kimlik No</Label>
                                            <Input value={detay.tc} onChange={e => updateYetkili(idx, "tc", e.target.value)}
                                                placeholder="00000000000" maxLength={11} className="bg-secondary/30 border-border font-mono text-sm" />
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-[11px] text-muted-foreground">Baro Sicil No</Label>
                                            <Input value={detay.sicil} onChange={e => updateYetkili(idx, "sicil", e.target.value)}
                                                placeholder="24174" className="bg-secondary/30 border-border font-mono text-sm" />
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* Vekil eden (müvekkil) */}
                        <div className="flex flex-col gap-3 p-4 rounded-xl bg-secondary/20 border border-border">
                            <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Vekil Eden (Müvekkil)</span>
                            <p className="text-[12px] font-semibold text-foreground/80">{toUpper(client.name)}</p>
                            <div className="grid grid-cols-1 gap-3">
                                <div className="space-y-1">
                                    <Label className="text-[11px] text-muted-foreground">Adres</Label>
                                    <Input value={muvekkillAdres} onChange={e => setMuvekkillAdres(e.target.value)}
                                        placeholder="MASLAK MAH. MASLAK MEYDAN SOK. NO.3/14" className="bg-secondary/30 border-border" />
                                </div>
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="space-y-1">
                                        <Label className="text-[11px] text-muted-foreground">İl</Label>
                                        <Input value={muvekkillIl} onChange={e => setMuvekkillIl(e.target.value)}
                                            placeholder="SARIYER İSTANBUL" className="bg-secondary/30 border-border" />
                                    </div>
                                    <div className="space-y-1">
                                        <Label className="text-[11px] text-muted-foreground">
                                            {client.client_type === "Corporate" ? "Vergi No" : "T.C. Kimlik No"}
                                        </Label>
                                        <Input value={vergiNo} onChange={e => setVergiNo(e.target.value)}
                                            placeholder={client.client_type === "Corporate" ? "3450249570" : "00000000000"}
                                            maxLength={client.client_type === "Corporate" ? 10 : 11}
                                            className="bg-secondary/30 border-border font-mono" />
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Dayanak Vekaletname */}
                        <div className="flex flex-col gap-3 p-4 rounded-xl bg-secondary/20 border border-border">
                            <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Dayanak Vekaletname</span>
                            <div className="grid grid-cols-1 gap-3">
                                <div className="space-y-1">
                                    <Label className="text-[11px] text-muted-foreground">Noterlik</Label>
                                    <Input value={dayNoterlik} onChange={e => setDayNoterlik(e.target.value)}
                                        placeholder="BEYOĞLU 60. NOTERLİĞİ" className="bg-secondary/30 border-border" />
                                </div>
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="space-y-1">
                                        <Label className="text-[11px] text-muted-foreground">Tarih (GG.AA.YYYY)</Label>
                                        <Input value={dayTarih} onChange={e => setDayTarih(e.target.value)}
                                            placeholder="27.01.2020" className="bg-secondary/30 border-border font-mono" />
                                    </div>
                                    <div className="space-y-1">
                                        <Label className="text-[11px] text-muted-foreground">Yevmiye No</Label>
                                        <Input value={dayYevmiye} onChange={e => setDayYevmiye(e.target.value)}
                                            placeholder="3639" className="bg-secondary/30 border-border font-mono" />
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Kapsam */}
                        <div className="flex flex-col gap-2 p-4 rounded-xl bg-secondary/20 border border-border">
                            <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Yetki Belgesi Kapsamı</span>
                            <Input value={kapsam} onChange={e => setKapsam(e.target.value)}
                                className="bg-secondary/30 border-border" />
                        </div>

                        <div className="flex justify-between pt-1">
                            <Button variant="ghost" onClick={() => setStep(1)} className="gap-2 text-muted-foreground">
                                <ChevronLeft className="w-4 h-4" /> Geri
                            </Button>
                            <Button disabled={!step2Valid} onClick={goToStep3} className="bg-rose-600 hover:bg-rose-700 text-white gap-2">
                                Önizle <ChevronRight className="w-4 h-4" />
                            </Button>
                        </div>
                    </div>
                )}

                {/* ── ADIM 3 ── */}
                {step === 3 && (
                    <div className="flex flex-col gap-4">
                        <div className="border border-border rounded-xl overflow-auto bg-white text-black p-8 font-serif leading-relaxed shadow-inner max-h-[58vh]" style={{ fontSize: "11pt" }}>
                            <div ref={printRef}>

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
                                        {verenDetay.sicil && `, ${verenDetay.sicil} sicil no'lu`}
                                        {verenDetay.tc && `, Vergi Daire ve No: ${verenDetay.tc}`})
                                    </div>
                                </div>

                                {/* Yetkili kılınanlar */}
                                <div style={{ fontWeight: "bold", marginTop: "20px", marginBottom: "6px" }}>YETKİLİ KILINAN AVUKATLAR :</div>
                                {yetkiliDetaylar.map((detay, idx) => (
                                    <div key={detay.ad} style={{ paddingLeft: "16px", marginBottom: "10px" }}>
                                        <div style={{ fontWeight: "bold" }}>{idx + 1}. Av. {toUpper(detay.ad)}</div>
                                        <div>
                                            (Aynı adreste mukim
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
                                        {client.client_type === "Corporate"
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
                                            {toUpper(dayanakSatiri)}
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

                        <div className="flex justify-between pt-1 gap-2">
                            <Button variant="ghost" onClick={() => setStep(2)} className="gap-2 text-muted-foreground shrink-0">
                                <ChevronLeft className="w-4 h-4" /> Geri
                            </Button>
                            <div className="flex gap-2">
                                <Button
                                    variant="outline"
                                    onClick={handleDownloadUdf}
                                    disabled={udfLoading}
                                    className="gap-2 border-border text-foreground/70 hover:border-rose-500/40 hover:text-rose-400"
                                >
                                    {udfLoading
                                        ? <Loader2 className="w-4 h-4 animate-spin" />
                                        : <Download className="w-4 h-4" />}
                                    UDF İndir
                                </Button>
                                <Button onClick={handlePrint} className="bg-rose-600 hover:bg-rose-700 text-white gap-2 px-5">
                                    <Printer className="w-4 h-4" /> Yazdır / PDF
                                </Button>
                            </div>
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
