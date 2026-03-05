/**
 * QuickCaseModal.tsx
 *
 * Belge işlenirken dava bulunamadığında açılan hızlı dava kartı oluşturma modalı.
 * Analiz verisiyle otomatik doldurulur (esas_no, müvekkil, avukat).
 * Kaydettikten sonra yeni dava otomatik olarak belgeye bağlanır.
 */
import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Gavel, AlertTriangle, Loader2, Sparkles, User, FileText, Scale, Building } from "lucide-react";
import { toast } from "sonner";
import { CaseData, useCases } from "@/hooks/useCases";
import { useConfig } from "@/hooks/useConfig";
import { useClients } from "@/hooks/useClients";
import { generateTrackingNumber } from "@/lib/caseNumberUtils";

const toTitleCase = (str: string): string => {
    if (!str) return "";
    return str
        .split(/(\s+|[,;]+)/)
        .map(part => {
            if (/^(\s+|[,;]+)$/.test(part)) return part;
            if (part.length === 0) return part;
            return part.charAt(0).toLocaleUpperCase('tr-TR') + part.slice(1).toLocaleLowerCase('tr-TR');
        })
        .join("");
};

interface QuickCaseModalProps {
    open: boolean;
    onClose: () => void;
    /** Analiz sonucundan gelen veriler — form önceden dolar */
    prefill?: {
        esas_no?: string;
        muvekkiller?: string[];
        muvekkil_adi?: string;
        karsi_taraf?: string;
        avukat_kodu?: string;
        court?: string;
        tarih?: string;
    };
    /** Modal kayıt başarılı olunca çağrılır, yeni dava nesnesiyle */
    onCaseCreated: (newCase: { id: number; tracking_no: string; esas_no: string; court: string; responsible_lawyer_name: string; status: string }) => void;
}

const DOSYA_TURLERI = ["Ceza", "Hukuk", "İcra", "İdari Yargı", "Arabuluculuk", "Savcılık"];
const ALT_TURLER: Record<string, string[]> = {
    "Ceza": [
        "AĞIR CEZA MAHKEMESİ",
        "ASLİYE CEZA MAHKEMESİ",
        "BÖLGE ADLİYE MAH. CEZA DAİRESİ",
        "ÇOCUK AĞIR CEZA MAHKEMESİ",
        "ÇOCUK MAHKEMESİ",
        "FİKRİ VE SINAİ HAKLAR CEZA MAHKEMESİ",
        "İCRA CEZA HAKİMLİĞİ",
        "İNFAZ HAKİMLİĞİ",
        "İSTİNAF CEZA DAİRESİ (İLK DERECE)",
        "SULH CEZA HAKİMLİĞİ",
        "YARGITAY CEZA DAİRESİ (İLK DERECE)",
    ],
    "Hukuk": [
        "AİLE MAHKEMESİ",
        "ASLİYE HUKUK MAHKEMESİ",
        "ASLİYE TİCARET MAHKEMESİ",
        "BAM HUKUK DAİRESİ (İLK DERECE)",
        "BÖLGE ADLİYE MAH. HUKUK DAİRESİ",
        "FİKRİ VE SINAİ HAKLAR HUKUK MAHKEMESİ",
        "İCRA HUKUK MAHKEMESİ",
        "İŞ MAHKEMESİ",
        "KADASTRO MAHKEMESİ",
        "KADASTRO MAHKEMESİ (MÜŞ)",
        "SULH HUKUK MAHKEMESİ",
        "TÜKETİCİ MAHKEMESİ",
    ],
    "İcra": ["İCRA DAİRESİ"],
    "İdari Yargı": ["BÖLGE İDARE MAHKEMESİ", "İDARE MAHKEMESİ", "VERGİ MAHKEMESİ"],
    "Arabuluculuk": ["ARABULUCULUK DAİRE BAŞKANLIĞI", "ARABULUCULUK MERKEZİ"],
    "Savcılık": [],
};

/**
 * Analizden gelen çeşitli tarih formatlarını HTML input[type=date] için
 * gereken YYYY-MM-DD formatına çevirir.
 * Geçersiz formatlarda bugünün tarihi döner.
 */
function parseToHtmlDate(raw?: string): string {
    const today = new Date().toISOString().split("T")[0];
    if (!raw || !raw.trim()) return today;
    const s = raw.trim();

    // YYYY-MM-DD — zaten doğru format
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;

    // DD.MM.YYYY veya DD/MM/YYYY
    const dotSlash = s.match(/^(\d{2})[./](\d{2})[./](\d{4})$/);
    if (dotSlash) return `${dotSlash[3]}-${dotSlash[2]}-${dotSlash[1]}`;

    // DDMMYYYY (8 haneli bitişik)
    if (/^\d{8}$/.test(s)) {
        const d = s.slice(0, 2), m = s.slice(2, 4), y = s.slice(4, 8);
        if (+d <= 31 && +m <= 12) return `${y}-${m}-${d}`;
        // YYYYMMDD (ISO bitişik)
        const y2 = s.slice(0, 4), m2 = s.slice(4, 6), d2 = s.slice(6, 8);
        if (+m2 <= 12 && +d2 <= 31) return `${y2}-${m2}-${d2}`;
    }

    // YYMMDD (6 haneli — analiz çıktısı örn: '221208')
    if (/^\d{6}$/.test(s)) {
        const yy = s.slice(0, 2), mm = s.slice(2, 4), dd = s.slice(4, 6);
        if (+mm <= 12 && +dd <= 31) {
            const fullYear = +yy >= 50 ? `19${yy}` : `20${yy}`;
            return `${fullYear}-${mm}-${dd}`;
        }
        // DDMMYY
        const dd2 = s.slice(0, 2), mm2 = s.slice(2, 4), yy2 = s.slice(4, 6);
        if (+mm2 <= 12 && +dd2 <= 31) {
            const fullYear2 = +yy2 >= 50 ? `19${yy2}` : `20${yy2}`;
            return `${fullYear2}-${mm2}-${dd2}`;
        }
    }

    return today;
}

export const QuickCaseModal = ({ open, onClose, prefill, onCaseCreated }: QuickCaseModalProps) => {
    const { saveCaseAndReturn, getClientCaseSequence, isLoading: isCaseLoading } = useCases();
    const { getClients, isLoading: isClientLoading } = useClients();
    const { lawyers } = useConfig();

    const [existingClientNames, setExistingClientNames] = useState<string[]>([]);
    const [existingClientsData, setExistingClientsData] = useState<{ name: string; category?: string; tc_no?: string;[key: string]: unknown }[]>([]);
    const [missingClients, setMissingClients] = useState<string[]>([]);
    const [showNewClientConfirm, setShowNewClientConfirm] = useState(false);

    const [esasNo, setEsasNo] = useState(prefill?.esas_no || "");
    const [courtBase, setCourtBase] = useState("");   // Mahkeme adı (saysz)
    const [courtDaireNo, setCourtDaireNo] = useState(""); // Daire/sıra no (1-20)
    const [fileType, setFileType] = useState("Hukuk");
    const [subType, setSubType] = useState("");
    const [lawyer, setLawyer] = useState(prefill?.avukat_kodu || "");
    const [openingDate, setOpeningDate] = useState("");;

    // Müvekkil isimlerini akıllı birleştirme: hem muvekkil_adi hem de muvekkiller listesini kullan
    const getInitialClients = () => {
        const list = prefill?.muvekkiller || [];
        const single = prefill?.muvekkil_adi;
        const all = single ? [single, ...list] : list;

        // Büyük/Küçük harf duyarsız temizlik
        const seen = new Set<string>();
        const unique: string[] = [];

        for (const name of all) {
            if (!name) continue;
            const normalized = name.trim().toLocaleUpperCase('tr-TR');
            if (!seen.has(normalized)) {
                seen.add(normalized);
                unique.push(name.trim());
            }
        }

        return toTitleCase(unique.filter(n => n).join(", "));
    };

    const [clientName, setClientName] = useState(getInitialClients());
    const [counterPartyName, setCounterPartyName] = useState(prefill?.karsi_taraf || "");
    // Taraf rolleri: "Davacı" veya "Davalı"
    const [clientRole, setClientRole] = useState<"Davacı" | "Davalı">("Davalı");
    const [counterRole, setCounterRole] = useState<"Davacı" | "Davalı">("Davacı");

    // Modal her açıldığında en güncel prefill verisiyle senkronize et ve müvekkilleri yükle
    useEffect(() => {
        if (open) {
            setEsasNo(prefill?.esas_no || "");
            setClientName(getInitialClients());
            setCounterPartyName(toTitleCase(prefill?.karsi_taraf || ""));
            setOpeningDate("");
            // Mahkeme ayrıştırma: courtBase + courtDaireNo
            const rawCourt = prefill?.court || "";

            // Yardımcı: başlıktaki numara parse et
            const parseCourt = (raw: string): { base: string; daireNo: string } => {
                if (!raw) return { base: '', daireNo: '' };

                // Pattern 1: "Samsun 2. Tüketici Mahkemesi"
                // Şehir adı + sayı + mahkeme türü
                const p1 = raw.match(/^([A-ZÇĞİIÖŞÜ][a-zçğıiöşü]+)\s+(\d+)\.\s+(.+Mahkemesi)$/i);
                if (p1) return { base: `${p1[1]} ${p1[3]}`, daireNo: p1[2] };

                // Pattern 2: "Ankara Bölge İdare Mahkemesi 10. İdari Dava Dairesi"
                // Mahkemesi + sayı + daire
                const p2 = raw.match(/^(.+?Mahkemesi)\s+(\d+)\.\s*.+Dairesi$/i);
                if (p2) return { base: p2[1], daireNo: p2[2] };

                // Pattern 3: Sözel ("Üçüncü İdari Dava Dairesi") — sayıya dönüdür
                const ordinalMap: Record<string, string> = {
                    'birinci': '1', 'ikinci': '2', 'üçüncü': '3', 'dördüncü': '4', 'beşinci': '5',
                    'altıncı': '6', 'yedinci': '7', 'sekizinci': '8', 'dokuzuncu': '9', 'onuncu': '10'
                };
                for (const [word, num] of Object.entries(ordinalMap)) {
                    const re = new RegExp(word + '\\s+.*daire', 'i');
                    if (re.test(raw)) {
                        const base = raw.replace(new RegExp('\\s*' + word + '.*$', 'i'), '').trim();
                        return { base: base || raw, daireNo: num };
                    }
                }

                return { base: raw, daireNo: '' };
            };

            const { base, daireNo } = parseCourt(rawCourt);
            setCourtBase(toTitleCase(base));
            setCourtDaireNo(daireNo);
            setClientRole("Davalı");
            setCounterRole("Davacı");
            setFileType("Hukuk");
            setSubType("");
            setMissingClients([]);
            setShowNewClientConfirm(false);

            // avukat_kodu (örn. "AGH") → lawyers listesinden tam adı bul (örn. "Av. Ayşe Gül Hanyaloğlu")
            if (prefill?.avukat_kodu && lawyers.length > 0) {
                const matched = lawyers.find((l: { code: string; name: string }) =>
                    l.code === prefill.avukat_kodu ||
                    l.name === prefill.avukat_kodu
                );
                setLawyer(matched ? matched.name : prefill.avukat_kodu);
            } else {
                setLawyer("");
            }

            // Db'deki mevcut müvekkil isimlerini çek
            getClients().then(clients => {
                if (clients) {
                    setExistingClientsData(clients);
                    setExistingClientNames(clients.map(c => c.name.toLocaleUpperCase('tr-TR').trim()));
                }
            });
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, prefill, lawyers, getClients]);


    const handleSave = async (forceSave = false) => {
        if (!esasNo.trim()) {
            toast.error("Esas No zorunludur.");
            return;
        }
        if (!clientName.trim()) {
            toast.error("En az bir müvekkil adı girilmeli.");
            return;
        }

        // --- YENİ MÜVEKKİL ONAYI ---
        const namesToCheck = clientName.split(',').map(n => n.trim()).filter(n => n);

        if (!forceSave && existingClientNames.length > 0 && namesToCheck.length > 0) {
            const missing = namesToCheck.filter(name => !existingClientNames.includes(name.toLocaleUpperCase('tr-TR')));
            if (missing.length > 0) {
                setMissingClients(missing);
                setShowNewClientConfirm(true);
                return; // Kullanıcı onayını bekle
            }
        }
        setMissingClients([]);
        setShowNewClientConfirm(false);

        // İsimleri listelere böl
        const clientNames = clientName.split(',').map(n => n.trim()).filter(n => n);
        const counterNames = counterPartyName.split(',').map(n => n.trim()).filter(n => n);

        const firstClientName = clientNames[0] || "";
        const matchedClient = existingClientsData.find(c =>
            c.name.toLocaleUpperCase('tr-TR').trim() === firstClientName.toLocaleUpperCase('tr-TR').trim()
        );
        const category = (matchedClient?.category as string) || "";
        // Eğer kategori yoksa veya müşteri yeni eklenecekse ama adı biliniyorsa QuickCase üzerinden de sigorta olup olmadığını belirleyebiliriz:
        // Eğer adında CORPUS, QUICK vs geçiyorsa category = "Sigorta" yapabiliriz. Fakat NewCase.tsx de aynısını bekliyor.
        // `generateTrackingNumber` içine category="Sigorta" geçersek sigorta mantığını çalıştırır, 
        // Aksi takdirde X1 veya diğerlerini kullanır. Ancak, eğer sigorta şirketi adı varsa otomatik Sigorta atamalıyız:
        let autoCategory = category;
        const sigortaSirketleri = ["AK", "ANADOLU", "AXA", "CORPUS", "QUICK", "EUREKO", "NIPPON", "SOMPO", "SİGORTA"];
        if (!autoCategory && sigortaSirketleri.some(s => firstClientName.toLocaleUpperCase('tr-TR').includes(s))) {
            autoCategory = "Sigorta";
        }

        const seq = firstClientName ? await getClientCaseSequence(firstClientName) : 1;

        const trackingNo = generateTrackingNumber({
            category: autoCategory,
            clientName: firstClientName,
            processType: fileType,
            serviceType: "00000", // QuickCase varsayılan
            sequence: seq
        });

        const caseData = {
            tracking_no: trackingNo,
            esas_no: esasNo.trim(),
            status: "DERDEST",
            file_type: fileType,
            sub_type: subType || undefined,
            court: courtBase.trim() || undefined,
            opening_date: openingDate || undefined,
            responsible_lawyer_name: lawyer || undefined,
            parties: [
                ...clientNames.map(name => ({
                    name,
                    role: clientRole,
                    party_type: "CLIENT" as const
                })),
                ...counterNames.map(name => ({
                    name,
                    role: counterRole,
                    party_type: "COUNTER" as const
                })),
            ],
        };

        const result = await saveCaseAndReturn(caseData as unknown as CaseData);
        if (result && result.id) {
            toast.success(`✅ Dava açıldı ve belgeye bağlandı! (${esasNo})`);
            onCaseCreated({
                id: result.id,
                tracking_no: result.tracking_no || trackingNo,
                esas_no: esasNo.trim(),
                court: courtDaireNo
                    ? `${courtBase.trim()} ${courtDaireNo}. Daire`.trim()
                    : courtBase.trim() || "",
                responsible_lawyer_name: lawyer || "",
                status: "DERDEST",
            });
            onClose();
        } else {
            toast.error("Dava kaydedilemedi. Sunucu hatası.");
        }
    };

    return (
        <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
            <DialogContent className="max-w-lg sm:max-w-xl glass-card border-border/60">
                <DialogHeader>
                    <div className="flex items-center gap-3 mb-1">
                        <div className="w-10 h-10 rounded-xl bg-amber-500/15 flex items-center justify-center">
                            <AlertTriangle className="w-5 h-5 text-amber-400" />
                        </div>
                        <div>
                            <DialogTitle className="text-lg font-semibold">Dava Bulunamadı</DialogTitle>
                            <DialogDescription className="text-xs mt-0.5">
                                Bu belge henüz açılmamış bir davaya ait görünüyor. Belgeyi kaydetmeden önce davayı açın.
                            </DialogDescription>
                        </div>
                    </div>


                </DialogHeader>

                <div className="grid gap-4 py-2">
                    {/* Esas No */}
                    <div className="grid grid-cols-4 items-center gap-3">
                        <Label className="text-right text-xs text-muted-foreground col-span-1 flex items-center justify-end gap-1.5">
                            <FileText className="w-3 h-3" /> Esas No *
                        </Label>
                        <Input
                            value={esasNo}
                            onChange={e => setEsasNo(e.target.value)}
                            placeholder="2024/1234"
                            className="col-span-3 font-mono h-9 glass-input"
                        />
                    </div>

                    {/* Müvekkil */}
                    <div className="grid grid-cols-4 items-center gap-3">
                        <Label className="text-right text-xs text-muted-foreground col-span-1 flex items-center justify-end gap-1.5">
                            <User className="w-3 h-3" /> Müvekkil *
                        </Label>
                        <div className="col-span-3 flex items-center gap-2">
                            <Input
                                value={clientName}
                                onChange={e => setClientName(e.target.value)}
                                placeholder="Müvekkil adı"
                                className="flex-1 h-9 glass-input"
                            />
                            <div className="flex rounded-md overflow-hidden border border-border shrink-0">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setClientRole("Davacı");
                                        setCounterRole("Davalı");
                                    }}
                                    className={`px-2 py-1 text-[10px] font-semibold transition-colors ${clientRole === "Davacı"
                                        ? "bg-blue-600 text-white"
                                        : "bg-background text-muted-foreground hover:bg-muted"
                                        }`}
                                >Davacı</button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setClientRole("Davalı");
                                        setCounterRole("Davacı");
                                    }}
                                    className={`px-2 py-1 text-[10px] font-semibold transition-colors ${clientRole === "Davalı"
                                        ? "bg-rose-600 text-white"
                                        : "bg-background text-muted-foreground hover:bg-muted"
                                        }`}
                                >Davalı</button>
                            </div>
                        </div>
                    </div>

                    {/* Karşı Taraf */}
                    <div className="grid grid-cols-4 items-center gap-3">
                        <Label className="text-right text-xs text-muted-foreground col-span-1">
                            Karşı Taraf
                        </Label>
                        <div className="col-span-3 flex items-center gap-2">
                            <Input
                                value={counterPartyName}
                                onChange={e => setCounterPartyName(e.target.value)}
                                placeholder="Karşı taraf adı (opsiyonel)"
                                className="flex-1 h-9 glass-input"
                            />
                            <div className="flex rounded-md overflow-hidden border border-border shrink-0">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setCounterRole("Davacı");
                                        setClientRole("Davalı");
                                    }}
                                    className={`px-2 py-1 text-[10px] font-semibold transition-colors ${counterRole === "Davacı"
                                        ? "bg-blue-600 text-white"
                                        : "bg-background text-muted-foreground hover:bg-muted"
                                        }`}
                                >Davacı</button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setCounterRole("Davalı");
                                        setClientRole("Davacı");
                                    }}
                                    className={`px-2 py-1 text-[10px] font-semibold transition-colors ${counterRole === "Davalı"
                                        ? "bg-rose-600 text-white"
                                        : "bg-background text-muted-foreground hover:bg-muted"
                                        }`}
                                >Davalı</button>
                            </div>
                        </div>
                    </div>

                    {/* Mahkeme */}
                    <div className="grid grid-cols-4 items-center gap-3">
                        <Label className="text-right text-xs text-muted-foreground col-span-1 flex items-center justify-end gap-1.5">
                            <Building className="w-3 h-3" /> Mahkeme
                        </Label>
                        <div className="col-span-3">
                            <Input
                                value={courtBase}
                                onChange={e => setCourtBase(e.target.value)}
                                placeholder="Örn: Samsun 2. Tüketici Mahkemesi"
                                className="w-full h-9 glass-input text-sm"
                            />
                        </div>
                    </div>

                    {/* Dava ve Kategorizasyon Bilgileri */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
                                <Gavel className="w-3 h-3" /> Dosya Türü
                            </Label>
                            <Select value={fileType} onValueChange={(v) => {
                                setFileType(v);
                                setSubType("");
                            }}>
                                <SelectTrigger className="h-9 glass-input text-sm">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {DOSYA_TURLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
                                <Scale className="w-3 h-3" /> Alt Tür
                            </Label>
                            <Select
                                value={subType}
                                onValueChange={setSubType}
                                disabled={!fileType || (ALT_TURLER[fileType]?.length ?? 0) === 0}
                            >
                                <SelectTrigger className="h-9 glass-input text-sm">
                                    <SelectValue placeholder={
                                        !fileType
                                            ? "Önce dosya türü seçin"
                                            : (ALT_TURLER[fileType]?.length ?? 0) === 0
                                                ? "Alt tür yok"
                                                : "Seçiniz"
                                    } />
                                </SelectTrigger>
                                <SelectContent>
                                    {(ALT_TURLER[fileType] ?? []).map(t => (
                                        <SelectItem key={t} value={t}>{toTitleCase(t)}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
                                <Scale className="w-3 h-3" /> Avukat
                            </Label>
                            <Select value={lawyer} onValueChange={setLawyer}>
                                <SelectTrigger className="h-9 glass-input text-sm">
                                    <SelectValue placeholder="Seçiniz" />
                                </SelectTrigger>
                                <SelectContent>
                                    {lawyers.map((l: { code: string; name: string }) => (
                                        <SelectItem key={l.code} value={l.name || l.code}>
                                            {l.name || l.code}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
                                <div className="w-3 h-3 border-r-2 border-b-2 border-muted-foreground/40" /> Açılış Tarihi
                            </Label>
                            <Input
                                type="date"
                                value={openingDate}
                                onChange={e => setOpeningDate(e.target.value)}
                                className="h-9 glass-input text-sm"
                            />
                        </div>
                    </div>
                </div>

                {showNewClientConfirm ? (
                    <div className="bg-primary/10 border border-primary/20 rounded-lg p-4 mb-2 flex flex-col gap-3">
                        <div className="flex items-start gap-3">
                            <User className="w-5 h-5 text-primary shrink-0 mt-0.5" />
                            <div>
                                <h4 className="text-sm font-semibold text-primary">
                                    {missingClients.length > 1 ? "Yeni Müvekkiller Kaydedilecek" : "Yeni Müvekkil Kaydedilecek"}
                                </h4>
                                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                                    <strong className="text-foreground">{missingClients.join(", ")}</strong>
                                    {missingClients.length > 1 ? " isimli müvekkiller sistemde bulunamadı." : " isimli müvekkil sistemde bulunamadı."}
                                    {" "}Dava oluşturulurken bu kişiler otomatik olarak <strong>Yeni Müvekkiller Tarafına</strong> kaydedilecektir. Onaylıyor musunuz?
                                </p>
                            </div>
                        </div>
                        <div className="flex gap-2 justify-end mt-2">
                            <Button variant="outline" size="sm" onClick={() => setShowNewClientConfirm(false)}>
                                Vazgeç
                            </Button>
                            <Button size="sm" className="bg-primary hover:bg-primary/90" onClick={() => handleSave(true)}>
                                Evet, {missingClients.length > 1 ? "Müvekkilleri" : "Müvekkili"} Kaydet ve Davayı Aç
                            </Button>
                        </div>
                    </div>
                ) : (
                    <>
                        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 text-xs text-amber-300 flex items-start gap-2 mt-1">
                            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                            <span>
                                Bu form hızlı kayıt içindir. Tam dava kartına <strong>Dava Kartı Yönetimi</strong> menüsünden ulaşabilirsiniz.
                            </span>
                        </div>

                        <DialogFooter className="gap-2 mt-2">
                            <Button variant="outline" onClick={onClose} disabled={isCaseLoading || isClientLoading}>
                                İptal
                            </Button>
                            <Button
                                onClick={() => handleSave(false)}
                                disabled={isCaseLoading || isClientLoading || !esasNo.trim() || !clientName.trim()}
                                className="bg-primary hover:bg-primary/90 gap-2"
                            >
                                {isCaseLoading ? (
                                    <><Loader2 className="w-4 h-4 animate-spin" /> Kaydediliyor...</>
                                ) : (
                                    <><Gavel className="w-4 h-4" /> Davayı Aç ve Belgeye Bağla</>
                                )}
                            </Button>
                        </DialogFooter>
                    </>
                )}
            </DialogContent>
        </Dialog>
    );
};
