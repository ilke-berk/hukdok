/**
 * QuickCaseModal.tsx
 *
 * Belge işlenirken dava bulunamadığında açılan hızlı dava kartı oluşturma modalı.
 * Analiz verisiyle otomatik doldurulur (esas_no, müvekkil, avukat).
 * Kaydettikten sonra yeni dava otomatik olarak belgeye bağlanır.
 */
import { useState, useEffect, useRef } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Gavel, AlertTriangle, Loader2, User, FileText, Scale, Building } from "lucide-react";
import { Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";
import { toast } from "sonner";
import { CaseData, DuplicateCaseMatch, useCases, CASE_SEQUENCE_ERROR, CASE_DUPLICATE_CHECK_ERROR } from "@/hooks/useCases";
import { useConfig } from "@/hooks/useConfig";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { ClientData, useClients } from "@/hooks/useClients";
import { generateTrackingNumber, generateNameBlock } from "@/lib/caseNumberUtils";
import { parseCourt } from "@/lib/courtParse";
import { closestName } from "@/lib/nameSimilarity";
import { PartyMatchIndicator } from "@/components/PartyMatchIndicator";

const upperTR = (s: string) => s.trim().toLocaleUpperCase("tr-TR");

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

export const QuickCaseModal = ({ open, onClose, prefill, onCaseCreated }: QuickCaseModalProps) => {
    const { saveCaseAndReturn, getClientCaseSequence, checkDuplicateCase, isLoading: isCaseLoading } = useCases();
    const { clients, isLoading: isClientLoading } = useClients();
    const {
        lawyers, requiredCaseFields, fileTypes, courtTypesByParent,
        configError, requiredFieldsError, refetchConfig, isRefetchingConfig,
    } = useConfig();

    // Yargı türü/alt tür listeleri DB'den (NewCase ile aynı kaynak) — önceden
    // buradaki sabit kopya referans listesinden geri kalıyordu.
    const DOSYA_TURLERI = fileTypes.map(f => f.name ?? "").filter(Boolean);
    const ALT_TURLER: Record<string, string[]> = courtTypesByParent
        ? Object.fromEntries(Object.entries(courtTypesByParent).map(([k, v]) => [k, v.map(i => i.name ?? "")]))
        : {};

    const [existingClientNames, setExistingClientNames] = useState<string[]>([]);
    const [existingClientsData, setExistingClientsData] = useState<ClientData[]>([]);
    const [missingClients, setMissingClients] = useState<string[]>([]);
    const [showNewClientConfirm, setShowNewClientConfirm] = useState(false);

    // Kayıt türü: DERDEST (gerçek dava) | MAHZEN (arşiv — derdestle aynı bilgiler) | DANIŞ (danışma — yeni müvekkil oluşturmaz)
    const [status, setStatus] = useState<"DERDEST" | "MAHZEN" | "DANIŞ">("DERDEST");
    const [notes, setNotes] = useState(""); // Danışma notu (ileride hatırlamak için)
    const [showConsultCheck, setShowConsultCheck] = useState(false);
    const [consultTypoHints, setConsultTypoHints] = useState<{ typed: string; suggestion: string }[]>([]);
    // Zorunlu alan uyarısı: eksik alan kaydı engellemez, onaylanırsa DERDEST kaydedilir
    const [showMissingConfirm, setShowMissingConfirm] = useState(false);
    const [pendingMissing, setPendingMissing] = useState<{ field: string; label: string }[]>([]);
    const missingAcknowledged = useRef(false);
    // Mükerrer dava uyarısı
    const [showDuplicateConfirm, setShowDuplicateConfirm] = useState(false);
    const [pendingDuplicates, setPendingDuplicates] = useState<DuplicateCaseMatch[]>([]);
    const duplicateAcknowledged = useRef(false);

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
    // Tanıdık sorgu: isim (TR-upper) → TC eşlemesi; TC popover içinden girilir
    const [tcByName, setTcByName] = useState<Record<string, string>>({});
    const handleTcChange = (name: string, tc: string) =>
        setTcByName(prev => ({ ...prev, [upperTR(name)]: tc }));
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
            // Mahkeme ayrıştırma: courtBase + courtDaireNo (ortak yardımcı — lib/courtParse)
            const rawCourt = prefill?.court || "";
            const { base, daireNo } = parseCourt(rawCourt);
            setCourtBase(toTitleCase(base));
            setCourtDaireNo(daireNo);
            setClientRole("Davalı");
            setCounterRole("Davacı");
            setFileType("Hukuk");
            setSubType("");
            setMissingClients([]);
            setShowNewClientConfirm(false);
            setStatus("DERDEST");
            setNotes("");
            setShowConsultCheck(false);
            setConsultTypoHints([]);
            setTcByName({});

            // avukat_kodu (örn. "AGH") → lawyers listesinden tam adı bul (örn. "Av. Ayşe Gül Hanyaloğlu")
            if (prefill?.avukat_kodu && lawyers.length > 0) {
                const matched = lawyers.find(l =>
                    l.code === prefill.avukat_kodu ||
                    l.name === prefill.avukat_kodu
                );
                setLawyer(matched ? matched.name : prefill.avukat_kodu);
            } else {
                setLawyer("");
            }

            // Db'deki mevcut müvekkil isimlerini cache'den al
            setExistingClientsData(clients);
            setExistingClientNames(clients.map(c => (c.name as string).toLocaleUpperCase('tr-TR').trim()));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, prefill, lawyers, clients]);


    const isConsult = status === "DANIŞ";

    /** Önerilen düzeltmeleri müvekkil alanına uygular (yazım hatası onarımı). */
    const applyTypoSuggestions = () => {
        const parts = clientName.split(',').map(n => n.trim()).filter(n => n);
        const fixed = parts.map(p => {
            const hint = consultTypoHints.find(
                h => h.typed.toLocaleLowerCase('tr-TR') === p.toLocaleLowerCase('tr-TR')
            );
            return hint ? hint.suggestion : p;
        });
        setClientName(fixed.join(', '));
        setShowConsultCheck(false);
        setConsultTypoHints([]);
    };

    const handleSave = async (forceSave = false) => {
        if (!clientName.trim()) {
            toast.error("En az bir müvekkil adı girilmeli.");
            return;
        }

        // G019: zorunlu alan listesi alınamadıysa kapı SESSİZCE açılıyordu
        // (boş liste = "hiçbir alan zorunlu değil"). Kayıt BLOKE.
        if (status === "DERDEST" && requiredFieldsError) {
            toast.error("Kaydedilemez: zorunlu alan listesi doğrulanamadı", {
                description: `${requiredFieldsError} Yukarıdaki şeritten "Tekrar dene" ile yenileyin.`,
            });
            return;
        }

        // Zorunlu alan uyarısı (kullanıcı kararı 2026-07-31 rev.2): eksik alan
        // kaydı ENGELLEMEZ — onaylanırsa dosya DERDEST açılır, panelde "eksik"
        // uyarısıyla görünür. Hızlı form tüm alanları toplamadığından uyarı
        // DERDEST'te neredeyse her zaman çıkar; tamamlanma yeri tam dava kartı.
        if (status === "DERDEST" && !missingAcknowledged.current) {
            const values: Record<string, string | undefined> = {
                esas_no: esasNo,
                court: courtBase,
                file_type: fileType,
                sub_type: subType,
                opening_date: openingDate,
                responsible_lawyer_name: lawyer,
            };
            const missingReq = requiredCaseFields.filter(f => !(values[f.field] ?? "").trim());
            if (missingReq.length > 0) {
                setPendingMissing(missingReq);
                setShowMissingConfirm(true);
                return;
            }
        }

        // Mükerrer dava kontrolü: aynı esas no'lu aktif kayıt varsa onaysız açma
        if (!duplicateAcknowledged.current && esasNo.trim()) {
            // G019: kontrol yapılamadıysa "mükerrer yok" varsayılmaz — kayıt BLOKE.
            let dups: DuplicateCaseMatch[];
            try {
                dups = await checkDuplicateCase(esasNo, courtBase);
            } catch (error) {
                console.error(error);
                toast.error("Dava açılamadı: mükerrer dava kontrolü yapılamadı", {
                    description: error instanceof Error ? error.message : CASE_DUPLICATE_CHECK_ERROR,
                });
                return;
            }
            if (dups.length > 0) {
                setPendingDuplicates(dups);
                setShowDuplicateConfirm(true);
                return;
            }
        }

        const namesToCheck = clientName.split(',').map(n => n.trim()).filter(n => n);
        const missing = existingClientNames.length > 0
            ? namesToCheck.filter(name => !existingClientNames.includes(name.toLocaleUpperCase('tr-TR')))
            : [];

        if (isConsult) {
            // Danışmada yeni müvekkil OLUŞTURULMAZ. Listede olmayan isimler için
            // yalnızca olası yazım hatasını kontrol edip en yakın müvekkili öneririz.
            if (!forceSave && missing.length > 0) {
                const candidatePool = existingClientsData.map(c => String(c.name));
                const hints = missing
                    .map(name => ({ typed: name, suggestion: closestName(name, candidatePool) }))
                    .filter((h): h is { typed: string; suggestion: string } => !!h.suggestion);
                if (hints.length > 0) {
                    setConsultTypoHints(hints);
                    setShowConsultCheck(true);
                    return; // Yazım hatası şüphesi — kullanıcı kararını bekle
                }
                // Yazım hatası şüphesi yok → doğrudan kaydet (yeni müvekkil eklenmez)
            }
        } else if (!forceSave && missing.length > 0) {
            // --- YENİ MÜVEKKİL ONAYI (gerçek dava) ---
            setMissingClients(missing);
            setShowNewClientConfirm(true);
            return; // Kullanıcı onayını bekle
        }
        setMissingClients([]);
        setShowNewClientConfirm(false);
        setShowConsultCheck(false);

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
        // "SİGORTA" kelimesi veya marka adı AYRI KELİME olarak geçmeli.
        // Substring kontrolü ("AK" gibi) "Burak Akman" tipi kişi isimlerini
        // yanlışlıkla Sigorta kategorisine (S1 koduna) düşürüyordu.
        // Aksigorta zaten "SİGORTA" içerdiği için markalar listesinde "AK" yok.
        const sigortaMarkalari = ["ANADOLU", "AXA", "CORPUS", "QUICK", "EUREKO", "NIPPON", "SOMPO"];
        const upperFirst = firstClientName.toLocaleUpperCase('tr-TR');
        const nameTokens = upperFirst.split(/\s+/);
        if (!autoCategory && (upperFirst.includes("SİGORTA") || upperFirst.includes("SIGORTA") || nameTokens.some(t => sigortaMarkalari.includes(t)))) {
            autoCategory = "Sigorta";
        }

        // Kategori isim bloğuna da geçmeli: kategorisiz çağrıda sigorta şirketi
        // kişi formatına ("A_SIGORTA.") düşüyordu; NewCase ile tutarlı olsun.
        // G002: sıra numarası alınamazsa fırlar — sessiz `1` ile dolu bir ofis
        // numarası üretip kaydı 409'a düşürmektense kaydetmeyi BLOKE ediyoruz.
        let seq = 1;
        if (firstClientName) {
            try {
                seq = await getClientCaseSequence(firstClientName, generateNameBlock(firstClientName, autoCategory));
            } catch (error) {
                console.error(error);
                toast.error("Dava açılamadı: ofis numarası alınamadı", {
                    description: error instanceof Error ? error.message : CASE_SEQUENCE_ERROR,
                });
                return;
            }
        }

        const trackingNo = generateTrackingNumber({
            category: autoCategory,
            clientName: firstClientName,
            clientCategory: autoCategory,
            processType: fileType,
            serviceType: "00000", // QuickCase varsayılan
            sequence: seq
        });

        const caseData = {
            tracking_no: trackingNo,
            esas_no: esasNo.trim() || undefined,
            status,
            file_type: fileType,
            sub_type: subType || undefined,
            court: courtBase.trim() || undefined,
            opening_date: openingDate || undefined,
            responsible_lawyer_name: lawyer || undefined,
            notes: notes.trim() || undefined,
            parties: [
                ...clientNames.map(name => ({
                    name,
                    role: clientRole,
                    party_type: "CLIENT" as const,
                    tc_no: tcByName[upperTR(name)] || undefined
                })),
                ...counterNames.map(name => ({
                    name,
                    role: counterRole,
                    party_type: "COUNTER" as const,
                    tc_no: tcByName[upperTR(name)] || undefined
                })),
            ],
        };

        const result = await saveCaseAndReturn(caseData as unknown as CaseData);
        if (result && result.id) {
            toast.success(
                isConsult
                    ? "✅ Danışma kaydı açıldı ve belgeye bağlandı!"
                    : `✅ Dava açıldı ve belgeye bağlandı! (${esasNo})`
            );
            onCaseCreated({
                id: result.id,
                tracking_no: result.tracking_no || trackingNo,
                esas_no: esasNo.trim(),
                court: courtDaireNo
                    ? `${courtBase.trim()} ${courtDaireNo}. Daire`.trim()
                    : courtBase.trim() || "",
                responsible_lawyer_name: lawyer || "",
                status,
            });
            onClose();
        } else {
            toast.error(result?.error || "Dava kaydedilemedi. Sunucu hatası.");
        }
    };

    return (
        <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
            <DialogContent className="max-w-lg sm:max-w-xl theme-classic bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none p-0 gap-0">
                <DialogHeader className="px-6 pt-6 pb-4 border-b border-[var(--border)]">
                    <div className="flex items-start gap-3">
                        <div className="w-11 h-11 grid place-items-center bg-[#c47a1e]/15 text-[#c47a1e] shrink-0">
                            <AlertTriangle className="w-5 h-5" strokeWidth={1.8} />
                        </div>
                        <div className="grid gap-1 min-w-0">
                            <Eyebrow tone="brand">{isConsult ? "Hızlı Danışma · Yeni Kayıt" : "Hızlı Dava · Yeni Kayıt"}</Eyebrow>
                            <DialogTitle className="font-display text-[20px] font-medium tracking-[-0.005em] text-[var(--fg)] leading-tight">
                                {isConsult ? "Danışma Kaydı" : "Dava Bulunamadı"}
                            </DialogTitle>
                            <DialogDescription className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed">
                                {isConsult
                                    ? "Ortada henüz dava yok. Sadece taraflar ve kısa bir not yeterli; belge bu danışma kaydına bağlanır."
                                    : "Bu belge henüz açılmamış bir davaya ait görünüyor. Belgeyi kaydetmeden önce davayı açın."}
                            </DialogDescription>
                        </div>
                    </div>
                </DialogHeader>

                <div className="grid gap-4 px-6 py-5">
                    {/* G019: config listeleri alınamadıysa boş dropdown'lar "liste boş"
                        sanılmasın — hata görünür, zorunlu alan kapısı kaydı bloke eder. */}
                    {(configError || requiredFieldsError) && (
                        <DataErrorBanner
                            description={`${configError ?? ""}${configError && requiredFieldsError ? " " : ""}${requiredFieldsError ?? ""}`.trim()}
                            onRetry={() => { void refetchConfig(); }}
                            isRetrying={isRefetchingConfig}
                        />
                    )}

                    {/* Kayıt Türü: Derdest / Danış */}
                    <div className="grid grid-cols-4 items-center gap-3">
                        <Label className="text-right font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] col-span-1">
                            Kayıt Türü
                        </Label>
                        <div className="col-span-3 flex rounded-[3px] overflow-hidden border border-[var(--border)] w-fit">
                            <button
                                type="button"
                                onClick={() => setStatus("DERDEST")}
                                className={`px-3 py-1.5 text-[11px] font-semibold transition-colors ${status === "DERDEST"
                                    ? "bg-[var(--brand)] text-[var(--brand-fg)]"
                                    : "bg-[var(--bg)] text-[var(--fg-muted)] hover:bg-[var(--bg-sunken)]"
                                    }`}
                            >Derdest</button>
                            <button
                                type="button"
                                onClick={() => setStatus("MAHZEN")}
                                className={`px-3 py-1.5 text-[11px] font-semibold transition-colors border-l border-[var(--border)] ${status === "MAHZEN"
                                    ? "bg-zinc-500 text-white"
                                    : "bg-[var(--bg)] text-[var(--fg-muted)] hover:bg-[var(--bg-sunken)]"
                                    }`}
                            >Mahzen</button>
                            <button
                                type="button"
                                onClick={() => setStatus("DANIŞ")}
                                className={`px-3 py-1.5 text-[11px] font-semibold transition-colors border-l border-[var(--border)] ${status === "DANIŞ"
                                    ? "bg-blue-500 text-white"
                                    : "bg-[var(--bg)] text-[var(--fg-muted)] hover:bg-[var(--bg-sunken)]"
                                    }`}
                            >Danış</button>
                        </div>
                    </div>

                    {/* Esas No */}
                    <div className="grid grid-cols-4 items-center gap-3">
                        <Label className="text-right font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] col-span-1 flex items-center justify-end gap-1.5">
                            <FileText className="w-3 h-3" /> {isConsult ? "Esas No" : "Esas No *"}
                        </Label>
                        <Input
                            value={esasNo}
                            onChange={e => setEsasNo(e.target.value)}
                            placeholder={isConsult ? "Varsa esas no (opsiyonel)" : "2024/1234"}
                            className="col-span-3 font-mono h-9 bg-[var(--bg)] border-[var(--border)] rounded-[3px]"
                        />
                    </div>

                    {/* Müvekkil */}
                    <div className="grid grid-cols-4 items-center gap-3">
                        <Label className="text-right font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] col-span-1 flex items-center justify-end gap-1.5">
                            <User className="w-3 h-3" /> Müvekkil *
                        </Label>
                        <div className="col-span-3 flex items-center gap-2">
                            <Input
                                value={clientName}
                                onChange={e => setClientName(e.target.value)}
                                placeholder="Müvekkil adı"
                                className="flex-1 h-9 bg-[var(--bg)] border-[var(--border)] rounded-[3px]"
                            />
                            <PartyMatchIndicator
                                value={clientName}
                                partyType="CLIENT"
                                tcByName={tcByName}
                                onTcChange={handleTcChange}
                            />
                            <div className="flex rounded-[3px] overflow-hidden border border-[var(--border)] shrink-0">
                                <button
                                    type="button"
                                    onClick={() => setClientRole("Davacı")}
                                    className={`px-2 py-1 text-[10px] font-semibold transition-colors ${clientRole === "Davacı"
                                        ? "bg-[var(--brand)] text-[var(--brand-fg)]"
                                        : "bg-[var(--bg)] text-[var(--fg-muted)] hover:bg-[var(--bg-sunken)]"
                                        }`}
                                >Davacı</button>
                                <button
                                    type="button"
                                    onClick={() => setClientRole("Davalı")}
                                    className={`px-2 py-1 text-[10px] font-semibold transition-colors ${clientRole === "Davalı"
                                        ? "bg-[var(--brand)] text-[var(--brand-fg)]"
                                        : "bg-[var(--bg)] text-[var(--fg-muted)] hover:bg-[var(--bg-sunken)]"
                                        }`}
                                >Davalı</button>
                            </div>
                        </div>
                    </div>

                    {/* Karşı Taraf */}
                    <div className="grid grid-cols-4 items-center gap-3">
                        <Label className="text-right font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] col-span-1">
                            Karşı Taraf
                        </Label>
                        <div className="col-span-3 flex items-center gap-2">
                            <Input
                                value={counterPartyName}
                                onChange={e => setCounterPartyName(e.target.value)}
                                placeholder="Karşı taraf adı (opsiyonel)"
                                className="flex-1 h-9 bg-[var(--bg)] border-[var(--border)] rounded-[3px]"
                            />
                            <PartyMatchIndicator
                                value={counterPartyName}
                                partyType="COUNTER"
                                tcByName={tcByName}
                                onTcChange={handleTcChange}
                            />
                            <div className="flex rounded-[3px] overflow-hidden border border-[var(--border)] shrink-0">
                                <button
                                    type="button"
                                    onClick={() => setCounterRole("Davacı")}
                                    className={`px-2 py-1 text-[10px] font-semibold transition-colors ${counterRole === "Davacı"
                                        ? "bg-[var(--brand)] text-[var(--brand-fg)]"
                                        : "bg-[var(--bg)] text-[var(--fg-muted)] hover:bg-[var(--bg-sunken)]"
                                        }`}
                                >Davacı</button>
                                <button
                                    type="button"
                                    onClick={() => setCounterRole("Davalı")}
                                    className={`px-2 py-1 text-[10px] font-semibold transition-colors ${counterRole === "Davalı"
                                        ? "bg-[var(--brand)] text-[var(--brand-fg)]"
                                        : "bg-[var(--bg)] text-[var(--fg-muted)] hover:bg-[var(--bg-sunken)]"
                                        }`}
                                >Davalı</button>
                            </div>
                        </div>
                    </div>

                    {/* Mahkeme */}
                    <div className="grid grid-cols-4 items-center gap-3">
                        <Label className="text-right font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] col-span-1 flex items-center justify-end gap-1.5">
                            <Building className="w-3 h-3" /> Mahkeme
                        </Label>
                        <div className="col-span-3">
                            <Input
                                value={courtBase}
                                onChange={e => setCourtBase(e.target.value)}
                                placeholder="Örn: Samsun 2. Tüketici Mahkemesi"
                                className="w-full h-9 bg-[var(--bg)] border-[var(--border)] rounded-[3px] text-sm"
                            />
                        </div>
                    </div>

                    {/* Danışma Notu — yalnızca danış modunda */}
                    {isConsult && (
                        <div className="grid grid-cols-4 items-start gap-3">
                            <Label className="text-right font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] col-span-1 flex items-center justify-end gap-1.5 mt-2">
                                <FileText className="w-3 h-3" /> Not
                            </Label>
                            <Textarea
                                value={notes}
                                onChange={e => setNotes(e.target.value)}
                                placeholder="Danışma ile ilgili kısa not (ileride hatırlamak için)..."
                                className="col-span-3 min-h-[72px] bg-[var(--bg)] border-[var(--border)] rounded-[3px] text-sm resize-none"
                            />
                        </div>
                    )}

                    {/* Dava ve Kategorizasyon Bilgileri — danışta gizli */}
                    {!isConsult && (
                    <>
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                            <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] flex items-center gap-1.5">
                                <Gavel className="w-3 h-3" /> Dosya Türü
                            </Label>
                            <Select value={fileType} onValueChange={(v) => {
                                setFileType(v);
                                setSubType("");
                            }}>
                                <SelectTrigger className="h-9 bg-[var(--bg)] border-[var(--border)] rounded-[3px] text-sm">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {DOSYA_TURLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-1.5">
                            <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] flex items-center gap-1.5">
                                <Scale className="w-3 h-3" /> Alt Tür
                            </Label>
                            <Select
                                value={subType}
                                onValueChange={setSubType}
                                disabled={!fileType || (ALT_TURLER[fileType]?.length ?? 0) === 0}
                            >
                                <SelectTrigger className="h-9 bg-[var(--bg)] border-[var(--border)] rounded-[3px] text-sm">
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
                            <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] flex items-center gap-1.5">
                                <Scale className="w-3 h-3" /> Avukat
                            </Label>
                            <Select value={lawyer} onValueChange={setLawyer}>
                                <SelectTrigger className="h-9 bg-[var(--bg)] border-[var(--border)] rounded-[3px] text-sm">
                                    <SelectValue placeholder="Seçiniz" />
                                </SelectTrigger>
                                <SelectContent>
                                    {lawyers.map(l => (
                                        <SelectItem key={l.code} value={l.name || l.code || ""}>
                                            {l.name || l.code}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-1.5">
                            <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] flex items-center gap-1.5">
                                <div className="w-3 h-3 border-r-2 border-b-2 border-[var(--fg-subtle)]/50" /> Açılış Tarihi
                            </Label>
                            <Input
                                type="date"
                                value={openingDate}
                                onChange={e => setOpeningDate(e.target.value)}
                                className="h-9 bg-[var(--bg)] border-[var(--border)] rounded-[3px] text-sm"
                            />
                        </div>
                    </div>
                    </>
                    )}
                </div>

                {showDuplicateConfirm ? (
                    <div className="bg-red-500/5 border-y border-red-500/30 px-6 py-4 flex flex-col gap-3">
                        <div className="flex items-start gap-3">
                            <div className="w-8 h-8 grid place-items-center bg-red-500 text-white shrink-0">
                                <AlertTriangle className="w-4 h-4" strokeWidth={1.8} />
                            </div>
                            <div className="min-w-0">
                                <Eyebrow tone="brand">Mükerrer Kayıt Şüphesi</Eyebrow>
                                <h4 className="font-display text-[15px] font-medium text-[var(--fg)] mt-0.5">
                                    Bu esas no zaten kayıtlı olabilir
                                </h4>
                                <ul className="mt-2 space-y-1">
                                    {pendingDuplicates.map(d => (
                                        <li key={d.id} className="text-[12px] text-[var(--fg)]">
                                            <span className="font-mono font-semibold">{d.esas_no}</span>
                                            {" · "}{d.court || "Mahkeme belirtilmemiş"}
                                            {d.court_match && <strong className="ml-1 text-red-500">(aynı mahkeme!)</strong>}
                                            <span className="text-[var(--fg-subtle)] font-mono ml-1">· {d.tracking_no}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        </div>
                        <div className="flex gap-2 justify-end mt-1">
                            <FlowButton variant="secondary" size="sm" onClick={() => setShowDuplicateConfirm(false)}>
                                Vazgeç
                            </FlowButton>
                            <FlowButton variant="primary" size="sm" onClick={() => {
                                duplicateAcknowledged.current = true;
                                setShowDuplicateConfirm(false);
                                handleSave(false);
                            }}>
                                Yine de Aç
                            </FlowButton>
                        </div>
                    </div>
                ) : showMissingConfirm ? (
                    <div className="bg-amber-500/5 border-y border-amber-500/30 px-6 py-4 flex flex-col gap-3">
                        <div className="flex items-start gap-3">
                            <div className="w-8 h-8 grid place-items-center bg-amber-500 text-white shrink-0">
                                <AlertTriangle className="w-4 h-4" strokeWidth={1.8} />
                            </div>
                            <div className="min-w-0">
                                <Eyebrow tone="brand">Zorunlu Alanlar Eksik</Eyebrow>
                                <h4 className="font-display text-[15px] font-medium text-[var(--fg)] mt-0.5">
                                    Dosya eksik alanlarla açılacak
                                </h4>
                                <p className="text-[12px] text-[var(--fg-muted)] mt-1.5 leading-relaxed">
                                    Eksik: <strong className="text-[var(--fg)] font-semibold">{pendingMissing.map(m => m.label).join(", ")}</strong>.
                                    {" "}Kaydederseniz dava <strong>DERDEST</strong> olarak açılır ve panelde
                                    <strong> "eksik alan"</strong> uyarısıyla görünür; tam dava kartından tamamlayabilirsiniz.
                                </p>
                            </div>
                        </div>
                        <div className="flex gap-2 justify-end mt-1">
                            <FlowButton variant="secondary" size="sm" onClick={() => setShowMissingConfirm(false)}>
                                Geri Dön
                            </FlowButton>
                            <FlowButton variant="primary" size="sm" onClick={() => {
                                missingAcknowledged.current = true;
                                setShowMissingConfirm(false);
                                handleSave(false);
                            }}>
                                Eksik Olarak Kaydet
                            </FlowButton>
                        </div>
                    </div>
                ) : showNewClientConfirm ? (
                    <div className="bg-[var(--brand-soft)] border-y border-[var(--brand)]/30 px-6 py-4 flex flex-col gap-3">
                        <div className="flex items-start gap-3">
                            <div className="w-8 h-8 grid place-items-center bg-[var(--brand)] text-[var(--brand-fg)] shrink-0">
                                <User className="w-4 h-4" strokeWidth={1.8} />
                            </div>
                            <div className="min-w-0">
                                <Eyebrow tone="brand">Onay Gerekiyor</Eyebrow>
                                <h4 className="font-display text-[15px] font-medium text-[var(--fg)] mt-0.5">
                                    {missingClients.length > 1 ? "Yeni Müvekkiller Kaydedilecek" : "Yeni Müvekkil Kaydedilecek"}
                                </h4>
                                <p className="text-[12px] text-[var(--fg-muted)] mt-1.5 leading-relaxed">
                                    <strong className="text-[var(--fg)] font-semibold">{missingClients.join(", ")}</strong>
                                    {missingClients.length > 1 ? " isimli müvekkiller sistemde bulunamadı." : " isimli müvekkil sistemde bulunamadı."}
                                    {" "}Dava oluşturulurken bu kişiler otomatik olarak <strong>Yeni Müvekkiller</strong> tarafına kaydedilir.
                                </p>
                            </div>
                        </div>
                        <div className="flex gap-2 justify-end mt-1">
                            <FlowButton variant="secondary" size="sm" onClick={() => setShowNewClientConfirm(false)}>
                                Vazgeç
                            </FlowButton>
                            <FlowButton variant="primary" size="sm" onClick={() => handleSave(true)}>
                                Onayla & Kaydet
                            </FlowButton>
                        </div>
                    </div>
                ) : showConsultCheck ? (
                    <div className="bg-blue-500/5 border-y border-blue-500/30 px-6 py-4 flex flex-col gap-3">
                        <div className="flex items-start gap-3">
                            <div className="w-8 h-8 grid place-items-center bg-blue-500 text-white shrink-0">
                                <User className="w-4 h-4" strokeWidth={1.8} />
                            </div>
                            <div className="min-w-0">
                                <Eyebrow tone="brand">Yazım Kontrolü</Eyebrow>
                                <h4 className="font-display text-[15px] font-medium text-[var(--fg)] mt-0.5">
                                    Bunları mı demek istediniz?
                                </h4>
                                <p className="text-[12px] text-[var(--fg-muted)] mt-1.5 leading-relaxed">
                                    Aşağıdaki isimler müvekkil listesinde yok ama benzer kayıt(lar) bulundu.
                                    Danışmada <strong>yeni müvekkil oluşturulmaz</strong>; istersen düzelt, ya da böyle kaydet.
                                </p>
                                <ul className="mt-2 space-y-1">
                                    {consultTypoHints.map((h, i) => (
                                        <li key={i} className="text-[12px] text-[var(--fg)]">
                                            <span className="line-through opacity-60">{h.typed}</span>
                                            <span className="mx-1.5 text-blue-500">→</span>
                                            <strong className="font-semibold">{h.suggestion}</strong>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        </div>
                        <div className="flex gap-2 justify-end mt-1">
                            <FlowButton variant="secondary" size="sm" onClick={() => { setShowConsultCheck(false); setConsultTypoHints([]); }}>
                                Vazgeç
                            </FlowButton>
                            <FlowButton variant="secondary" size="sm" onClick={applyTypoSuggestions}>
                                Önerileri Uygula
                            </FlowButton>
                            <FlowButton variant="primary" size="sm" onClick={() => handleSave(true)}>
                                Böyle Kaydet
                            </FlowButton>
                        </div>
                    </div>
                ) : (
                    <>
                        <div className={`border-y px-6 py-3 text-[12px] flex items-start gap-2 ${isConsult ? "bg-blue-500/10 border-blue-500/25 text-blue-600" : "bg-[#c47a1e]/10 border-[#c47a1e]/25 text-[#c47a1e]"}`}>
                            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" strokeWidth={1.8} />
                            <span className="leading-relaxed">
                                {isConsult
                                    ? <>Danışma kaydıdır; listede olmayan isim <strong className="font-semibold">yeni müvekkil olarak eklenmez</strong>.</>
                                    : <>Bu form hızlı kayıt içindir. Tam dava kartına <strong className="font-semibold">Davalar</strong> menüsünden ulaşabilirsiniz.</>}
                            </span>
                        </div>

                        <DialogFooter className="px-6 py-4 gap-2 border-t border-[var(--border)] bg-[var(--bg)]">
                            <FlowButton variant="secondary" onClick={onClose} disabled={isCaseLoading || isClientLoading}>
                                İptal
                            </FlowButton>
                            <FlowButton
                                variant="primary"
                                onClick={() => handleSave(false)}
                                disabled={isCaseLoading || isClientLoading || (!isConsult && !esasNo.trim()) || !clientName.trim()}
                            >
                                {isCaseLoading ? (
                                    <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Kaydediliyor…</>
                                ) : (
                                    <><Gavel className="w-3.5 h-3.5" /> {isConsult ? "Danışmayı Aç ve Bağla" : "Davayı Aç ve Bağla"}</>
                                )}
                            </FlowButton>
                        </DialogFooter>
                    </>
                )}
            </DialogContent>
        </Dialog>
    );
};
