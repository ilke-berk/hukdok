import { useState, useEffect, useMemo, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useClients } from "@/hooks/useClients";
import { useConfig } from "@/hooks/useConfig";
import { useCases, CaseData, DuplicateCaseMatch, CASE_SEQUENCE_ERROR } from "@/hooks/useCases";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { Card, CardContent } from "@/components/ui/card";
import { Eyebrow } from "@/components/dashboard/primitives";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Gavel, User, FileText, Scale, Save, Briefcase, Building, RefreshCw, Sparkles, Loader2, Check, ChevronsUpDown, Plus, X, Calendar, Banknote, Coins, Heart, Trash2 } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { generateTrackingNumber, generateNameBlock, pickNameClient, bestCategoryCode } from "@/lib/caseNumberUtils";
import { cn } from "@/lib/utils";
import { PartyMatchIndicator } from "@/components/PartyMatchIndicator";
import { useFormDraft } from "@/hooks/useFormDraft";
import { describeDraftAge } from "@/lib/formDraft";
import {
    EMPTY_NEW_CASE_FORM,
    isNewCaseDraftDirty,
    newCaseDraftStore,
    type NewCaseDraftData,
} from "@/lib/newCaseDraft";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

// Tüm listeler artık useConfig üzerinden dinamik olarak alınıyor.

interface EditModeParty {
    party_type: string;
    name: string;
    role: string;
    birth_year?: number;
    gender?: string;
    client_id?: number | null;
    tc_no?: string | null;
}

interface EditModeCaseData {
    id?: number;
    tracking_no: string;
    status: string;
    history?: { date: string; action: string; user?: string; old?: string; new?: string; field?: string }[];
    file_type?: string;
    sub_type?: string;
    subject?: string;
    court?: string;
    responsible_lawyer_name?: string;
    uyap_lawyer_name?: string;
    esas_no?: string;
    opening_date?: string;
    service_type?: string;
    maddi_tazminat?: number | string;
    manevi_tazminat?: number | string;
    acceptance_date?: string;
    bureau_type?: string;
    sub_type_extra?: string;
    judicial_unit?: string;
    atama_tarihi?: string;
    hasar_dosya_no?: string;
    hukuk_no?: string;
    klasor_no_2?: string;
    notes?: string;
    parties?: EditModeParty[];
    lawyers?: { name: string; lawyer_id?: number | null }[];
}

interface CaseHistoryEntry {
    date: string;
    action: string;
    user?: string;
    old?: string;
    new?: string;
    field?: string;
}

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

const toUpperTR = (str: string) => str.toLocaleUpperCase('tr-TR').trim();


const NewCase = () => {
    useSetPageTitle("Yeni Dava", ["Avukat Paneli", "Davalar", "Yeni"]);
    const navigate = useNavigate();
    const location = useLocation();

    const queryClient = useQueryClient();

    // API Hooks
    const { saveCase, updateCase, deleteCase, getCase, checkDuplicateCase, isLoading: isSaving } = useCases();
    const { clients: dbClients } = useClients();
    const {
        caseSubjects, lawyers,
        fileTypes, courtTypesByParent, mainPartyRoles, thirdPartyRoles, bureauTypes, specialties,
        requiredCaseFields, requiredPartyRule,
    } = useConfig();

    const DOSYA_TURLERI = fileTypes.map(f => f.name ?? "");
    const ALT_TURLER: Record<string, string[]> = courtTypesByParent
        ? Object.fromEntries(Object.entries(courtTypesByParent).map(([k, v]) => [k, v.map(i => i.name ?? "")]))
        : {};
    const TARAF_ROLLERI = mainPartyRoles.map(r => r.name ?? "");
    // 3. taraf dropdown'ı THIRD rollerine ek olarak ana taraf rollerini de sunar
    const UCUNCU_TARAF_ROLLERI = [...new Set([...thirdPartyRoles, ...mainPartyRoles].map(r => r.name ?? ""))];
    const BURO_OZEL_TURU = bureauTypes.map(b => b.name ?? "");
    const HIZMET_TURLERI = [
        { label: "Rapor", index: 0 },
        { label: "Danışmanlık", index: 1 },
        { label: "Dava", index: 2 },
        { label: "İcra", index: 3 },
        { label: "Yazışma", index: 4 }
    ];

    // Check if we are in edit mode
    const editModeCase = location.state?.case as EditModeCaseData | undefined;
    const isEditMode = !!editModeCase;

    // Generate case tracking ID using central utility
    const [caseId, setCaseId] = useState(editModeCase?.tracking_no || generateTrackingNumber());
    // G002: ofis no sırası alınamadıysa dolu (yanlış) numarayla kayıt yapılmasın
    const [sequenceError, setSequenceError] = useState<string | null>(null);
    const [isLoading, _setIsLoading] = useState(false);
    const [caseStatus, setCaseStatus] = useState(editModeCase?.status || "DERDEST");
    const [caseHistory, setCaseHistory] = useState<CaseHistoryEntry[]>(editModeCase?.history || []);

    // Config

    // Form States
    const [showClientConfirm, setShowClientConfirm] = useState(false);
    const [pendingUnregistered, setPendingUnregistered] = useState<{ name: string }[]>([]);
    // Zorunlu alan uyarısı: eksik alan kaydı engellemez, onaylanırsa DERDEST
    // kaydedilir ve panelde "eksik" rozetiyle görünür
    const [showMissingConfirm, setShowMissingConfirm] = useState(false);
    const [pendingMissing, setPendingMissing] = useState<{ field: string; label: string }[]>([]);
    const missingAcknowledged = useRef(false);
    // Mükerrer dava uyarısı: aynı esas no'lu aktif kayıt varsa onay istenir
    const [showDuplicateConfirm, setShowDuplicateConfirm] = useState(false);
    const [pendingDuplicates, setPendingDuplicates] = useState<DuplicateCaseMatch[]>([]);
    const duplicateAcknowledged = useRef(false);
    const [clientSearchValues, setClientSearchValues] = useState<{ [key: number]: string }>({});

    const [formData, setFormData] = useState({
        fileType: editModeCase?.file_type || "",
        subType: editModeCase?.sub_type || "",
        subject: editModeCase?.subject || "",
        court: editModeCase?.court || "",
        category: "",
        lawyer: editModeCase?.responsible_lawyer_name || "",
        uyapLawyer: editModeCase?.uyap_lawyer_name || "",
        esasNo: editModeCase?.esas_no || "",
        fileOpeningDate: editModeCase?.opening_date || "",
        serviceType: "00000", // Default service type code
        maddiTazminat: editModeCase?.maddi_tazminat?.toString() || "",
        maneviTazminat: editModeCase?.manevi_tazminat?.toString() || "",
        acceptanceDate: editModeCase?.acceptance_date || "",
        bureauType: editModeCase?.bureau_type || "",
        subTypeExtra: editModeCase?.sub_type_extra || "",
        judicialUnit: editModeCase?.judicial_unit || "",
        atamaTarihi: editModeCase?.atama_tarihi || "",
        hasarDosyaNo: editModeCase?.hasar_dosya_no || "",
        hukukNo: editModeCase?.hukuk_no || "",
        klasorNo2: editModeCase?.klasor_no_2 || "",
        notes: editModeCase?.notes || "",
    });

    const [selectedLawyers, setSelectedLawyers] = useState<Array<{ name: string; lawyer_id?: number | null }>>(
        editModeCase?.lawyers?.map(l => ({ name: l.name, lawyer_id: l.lawyer_id })) || []
    );

    // Multiple Clients (Müvekkil, Müdahil, etc.)
    const [clients, setClients] = useState<Array<{ name: string; role: string; category?: string; birth_year?: number; gender?: string }>>(
        editModeCase?.parties?.filter((p: EditModeParty) => p.party_type === "CLIENT").map((p: EditModeParty) => ({ name: p.name, role: p.role, birth_year: p.birth_year, gender: p.gender })) ||
        [{ name: "", role: "Davacı" }]
    );

    // Multiple Counter-Parties (Karşı Taraf)
    const [counterParties, setCounterParties] = useState<Array<{ name: string; role: string; tc_no?: string }>>(
        editModeCase?.parties?.filter((p: EditModeParty) => p.party_type === "COUNTER").map((p: EditModeParty) => ({ name: p.name, role: p.role, tc_no: p.tc_no || undefined })) ||
        [{ name: "", role: "Davalı" }]
    );

    // Third Parties (Tanık, Bilirkişi, etc.)
    const [thirdParties, setThirdParties] = useState<Array<{ name: string; role: string; tc_no?: string }>>(
        editModeCase?.parties?.filter((p: EditModeParty) => p.party_type === "THIRD").map((p: EditModeParty) => ({ name: p.name, role: p.role, tc_no: p.tc_no || undefined })) ||
        []
    );

    // Tanıdık sorgu: satır bazında eşleşme durumu ("counter-0" / "third-1")
    // — eşleşme varsa satırın altında eşleşen isim + TC ve opsiyonel TC alanı belirir
    type RowMatchState = { hasMatch: boolean; conflict: boolean; matched: Array<{ name: string; tc_no?: string | null }> };
    const [partyMatchFlags, setPartyMatchFlags] = useState<Record<string, RowMatchState>>({});
    const setRowMatchFlag = (key: string, s: RowMatchState) =>
        setPartyMatchFlags(prev => {
            const cur = prev[key];
            if (cur && cur.hasMatch === s.hasMatch && cur.conflict === s.conflict &&
                JSON.stringify(cur.matched) === JSON.stringify(s.matched)) return prev;
            return { ...prev, [key]: s };
        });
    // "Eşleşen: Ahmet Yılmaz (TC 12345678901) · ..." biçiminde satır altı özeti
    const rowMatchSummary = (key: string, tcEntered?: string, withTcHint = true): string => {
        const st = partyMatchFlags[key];
        if (!st || st.matched.length === 0) {
            return tcEntered ? "Eşleşme yok — TC ile doğrulandı, farklı kişi" : "";
        }
        const list = st.matched.slice(0, 3)
            .map(m => m.tc_no ? `${m.name} (TC ${m.tc_no})` : m.name)
            .join(" · ");
        return `Eşleşen: ${list}${!tcEntered && withTcHint ? " — TC girerek kesinleştirebilirsiniz" : ""}`;
    };
    // Open/Close states for client comboboxes
    const [clientComboboxesOpen, setClientComboboxesOpen] = useState<boolean[]>([]);

    // Combobox state for searchable subject dropdown
    const [subjectComboboxOpen, setSubjectComboboxOpen] = useState(false);

    // Approval Ticks State
    const [approvedFields, setApprovedFields] = useState({
        court: false,
        clients: [] as boolean[],
        counterParties: [] as boolean[],
        thirdParties: [] as boolean[]
    });

    // Animation States
    const [isShaking, setIsShaking] = useState(false);
    const triggerShake = () => {
        setIsShaking(true);
        setTimeout(() => setIsShaking(false), 400);
    };

    // --- G004: Taslak kalıcılığı ---------------------------------------
    // Doldurulan form sekme yenilenmesinde/kaza navigasyonunda kaybolmasın.
    // Düzenleme modunda KAPALI: orada tek doğru kaynak sunucudaki kayıttır;
    // taslak, kapatılıp yeniden açılan bir kartta eski düzenlemeyi diriltirdi.
    const draftData: NewCaseDraftData = useMemo(() => ({
        caseStatus,
        formData,
        selectedLawyers,
        clients,
        counterParties,
        thirdParties,
    }), [caseStatus, formData, selectedLawyers, clients, counterParties, thirdParties]);

    const draftDirty = !isEditMode && isNewCaseDraftDirty(draftData);
    const draft = useFormDraft(newCaseDraftStore, {
        data: draftData,
        dirty: draftDirty,
        enabled: !isEditMode,
    });

    useEffect(() => {
        setApprovedFields({
            court: false,
            clients: new Array(clients.length).fill(false),
            counterParties: new Array(counterParties.length).fill(false),
            thirdParties: new Array(thirdParties.length).fill(false)
        });
    }, [clients.length, counterParties.length, thirdParties.length]);

    const handleFieldApproval = (type: 'court' | 'client' | 'counter' | 'third', idx?: number) => {
        if (type === 'court') {
            setFormData(prev => ({ ...prev, court: toTitleCase(prev.court) }));
            setApprovedFields(prev => ({ ...prev, court: !prev.court }));
        } else if (type === 'client' && idx !== undefined) {
            const updated = [...clients];
            updated[idx].name = toTitleCase(updated[idx].name);
            setClients(updated);
            const newApprovals = [...approvedFields.clients];
            newApprovals[idx] = !newApprovals[idx];
            setApprovedFields(prev => ({ ...prev, clients: newApprovals }));
        } else if (type === 'counter' && idx !== undefined) {
            const updated = [...counterParties];
            updated[idx].name = toTitleCase(updated[idx].name);
            setCounterParties(updated);
            const newApprovals = [...approvedFields.counterParties];
            newApprovals[idx] = !newApprovals[idx];
            setApprovedFields(prev => ({ ...prev, counterParties: newApprovals }));
        } else if (type === 'third' && idx !== undefined) {
            const updated = [...thirdParties];
            updated[idx].name = toTitleCase(updated[idx].name);
            setThirdParties(updated);
            const newApprovals = [...approvedFields.thirdParties];
            newApprovals[idx] = !newApprovals[idx];
            setApprovedFields(prev => ({ ...prev, thirdParties: newApprovals }));
        }
    };


    const { getClientCaseSequence } = useCases();

    // Yardımcı: Hizmet bitmask'ini güncelle (11000 formatı)
    const handleServiceToggle = (index: number, checked: boolean) => {
        const currentMask = formData.serviceType.split("");
        currentMask[index] = checked ? "1" : "0";
        const newMask = currentMask.join("");
        setFormData({ ...formData, serviceType: newMask });
        updateTrackingNumber(undefined, newMask);
    };

    // "Ad1;Ad2" biçiminde tek satıra yazılan çoklu isimleri ayrı kişilere böler
    const splitPartyNames = (value: string): string[] =>
        value.split(";").map(s => s.trim()).filter(Boolean);

    // Yardımcı: Takip Numarasını Güncelle
    // clientsOverride: setClients henüz commit olmadan önce güncel listeyi iletmek için
    const updateTrackingNumber = async (
        fType?: string,
        sType?: string,
        clientsOverride?: Array<{ name: string; category?: string }>
    ) => {
        if (isEditMode) return;

        const source = (clientsOverride || clients).filter(c => c.name);
        const named = pickNameClient(source);
        const catCode = bestCategoryCode(source);
        const cName = named.name || "";

        let seq = 1;
        if (cName) {
            // İsim bloğu (blok2) ile sorgula: backend mevcut en yüksek sıra numarasından
            // devam eder, dolu ofis numarası önerilmez.
            try {
                seq = await getClientCaseSequence(cName, generateNameBlock(cName, named.category));
            } catch (error) {
                // G002: sıra numarası alınamadıysa uydurma numara ÜRETİLMEZ —
                // handleSubmit bu bayrağı görüp kaydı bloke eder.
                console.error(error);
                setSequenceError(error instanceof Error ? error.message : CASE_SEQUENCE_ERROR);
                toast.error("Ofis numarası üretilemedi", {
                    description: error instanceof Error ? error.message : CASE_SEQUENCE_ERROR,
                });
                return;
            }
        }
        setSequenceError(null);

        const tracking = generateTrackingNumber({
            category: catCode,
            clientName: cName,
            clientCategory: named.category,
            sequence: seq,
            processType: fType || formData.fileType,
            serviceType: sType || formData.serviceType
        });
        setCaseId(tracking);
    };

    // Taslak şeridindeki "geri yükle". Sessiz sihir YOK: kullanıcı açıkça basar.
    const handleRestoreDraft = () => {
        const data = draft.restore();
        if (!data) return;

        setCaseStatus(data.caseStatus);
        // EMPTY tabanı: eski sürümde olmayan alanlar undefined kalmasın.
        setFormData({ ...EMPTY_NEW_CASE_FORM, ...data.formData });
        setSelectedLawyers(data.selectedLawyers);
        setClients(data.clients.length > 0 ? data.clients : [{ name: "", role: "Davacı" }]);
        setCounterParties(data.counterParties.length > 0 ? data.counterParties : [{ name: "", role: "Davalı" }]);
        setThirdParties(data.thirdParties);

        // Ofis numarası taslakta TAŞINMAZ (bkz. newCaseDraft.ts): sunucudan
        // yeniden üretilir. Sıra alınamazsa updateTrackingNumber sequenceError
        // kurar ve G002 kuralı kaydı bloke eder.
        updateTrackingNumber(data.formData.fileType, data.formData.serviceType, data.clients);

        toast.success("Taslak geri yüklendi", {
            description: "Ofis numarası sunucudan yeniden alınıyor.",
        });
    };

    // Effect to handle incoming case state (for editing)
    useEffect(() => {
        if (editModeCase) {
            setCaseId(editModeCase.tracking_no);
            setCaseStatus(editModeCase.status);
            setCaseHistory(editModeCase.history || []);
            setFormData({
                fileType: editModeCase.file_type || "",
                subType: editModeCase.sub_type || "",
                subject: editModeCase.subject || "",
                court: editModeCase.court || "",
                category: "",
                lawyer: editModeCase.responsible_lawyer_name || "",
                uyapLawyer: editModeCase.uyap_lawyer_name || "",
                esasNo: editModeCase.esas_no || "",
                fileOpeningDate: editModeCase.opening_date || "",
                serviceType: editModeCase.service_type || "00000",
                maddiTazminat: editModeCase.maddi_tazminat?.toString() || "",
                maneviTazminat: editModeCase.manevi_tazminat?.toString() || "",
                acceptanceDate: editModeCase.acceptance_date || "",
                bureauType: editModeCase.bureau_type || "",
                subTypeExtra: editModeCase.sub_type_extra || "",
                judicialUnit: editModeCase.judicial_unit || "",
                atamaTarihi: editModeCase.atama_tarihi || "",
                hasarDosyaNo: editModeCase.hasar_dosya_no || "",
                hukukNo: editModeCase.hukuk_no || "",
                klasorNo2: editModeCase.klasor_no_2 || "",
                notes: editModeCase.notes || "",
            });
            setSelectedLawyers(editModeCase.lawyers?.map(l => ({ name: l.name, lawyer_id: l.lawyer_id })) || []);
            setClients(editModeCase.parties?.filter((p: EditModeParty) => p.party_type === "CLIENT").map((p: EditModeParty) => ({ name: p.name, role: p.role, birth_year: p.birth_year, gender: p.gender })) || [{ name: "", role: "Davacı" }]);
            setCounterParties(editModeCase.parties?.filter((p: EditModeParty) => p.party_type === "COUNTER").map((p: EditModeParty) => ({ name: p.name, role: p.role, tc_no: p.tc_no || undefined })) || [{ name: "", role: "Davalı" }]);
            setThirdParties(editModeCase.parties?.filter((p: EditModeParty) => p.party_type === "THIRD").map((p: EditModeParty) => ({ name: p.name, role: p.role, tc_no: p.tc_no || undefined })) || []);
        }
    }, [editModeCase]);

    // Zorunlu alan denetimi — liste backend'den gelir (tek kaynak: required_fields.py).
    const getMissingRequired = (): { field: string; label: string }[] => {
        const values: Record<string, string | undefined> = {
            esas_no: formData.esasNo,
            court: formData.court,
            file_type: formData.fileType,
            judicial_unit: formData.judicialUnit,
            sub_type: formData.subType,
            sub_type_extra: formData.subTypeExtra,
            opening_date: formData.fileOpeningDate,
            subject: formData.subject,
            responsible_lawyer_name: formData.lawyer,
            uyap_lawyer_name: formData.uyapLawyer,
            service_type: formData.serviceType,
            acceptance_date: formData.acceptanceDate,
            bureau_type: formData.bureauType,
            atama_tarihi: formData.atamaTarihi,
        };
        const missing = requiredCaseFields.filter(f => !(values[f.field] ?? "").trim());
        const namedCounters = counterParties.filter(c => c.name);
        if (requiredPartyRule && namedCounters.length > 0 && !namedCounters.some(c => (c.tc_no || "").trim())) {
            missing.push(requiredPartyRule);
        }
        return missing;
    };

    const handleSubmit = async (e?: React.FormEvent, forceSave = false) => {
        if (e) e.preventDefault();

        // G002: ofis numarası sunucudan alınamadıysa kayıt BLOKE — aksi halde
        // dolu bir numarayla kaydedip 409'a düşülüyor ya da yanlış numara açılıyordu.
        // (Düzenlemede numara sabittir, kontrol yalnız yeni kayıtta.)
        if (!isEditMode && sequenceError) {
            toast.error("Kaydedilemez: ofis numarası doğrulanamadı", {
                description: `${sequenceError} Bağlantı düzelince müvekkil alanını yeniden seçin.`,
            });
            return;
        }

        // Zorunlu alan uyarısı: eksik alan kaydı ENGELLEMEZ — kullanıcı onaylarsa
        // dosya DERDEST kaydedilir, panelde "eksik" uyarısıyla görünür/filtrelenir.
        if (caseStatus === "DERDEST" && !missingAcknowledged.current) {
            const missing = getMissingRequired();
            if (missing.length > 0) {
                setPendingMissing(missing);
                setShowMissingConfirm(true);
                return;
            }
        }

        // Mükerrer dava kontrolü: aynı esas no'lu aktif kayıt varsa onaysız açma
        // (anket: "aynı dava ara sıra iki kez açılıyor"). Yalnız yeni kayıtta.
        if (!isEditMode && !duplicateAcknowledged.current && formData.esasNo.trim()) {
            const dups = await checkDuplicateCase(formData.esasNo, formData.court);
            if (dups.length > 0) {
                setPendingDuplicates(dups);
                setShowDuplicateConfirm(true);
                return;
            }
        }

        // Validate that all people in 'clients' list are actually registered (Case-Insensitive Check)
        // Danışmada (DANIŞ) yeni müvekkil oluşturulmadığı için bu onay atlanır.
        const unregistered = clients.filter(c =>
            c.name && !dbClients.some(db => toUpperTR(db.name) === toUpperTR(c.name))
        );
        if (!forceSave && caseStatus !== "DANIŞ" && unregistered.length > 0) {
            setPendingUnregistered(unregistered.map(u => ({ name: u.name })));
            setShowClientConfirm(true);
            return;
        }

        setShowClientConfirm(false);
        setPendingUnregistered([]);

        // Prepare data for backend
        const caseData = {
            tracking_no: caseId,
            esas_no: formData.esasNo,
            status: caseStatus,
            file_type: formData.fileType,
            sub_type: formData.subType,
            subject: formData.subject,
            court: formData.court,
            opening_date: formData.fileOpeningDate,
            responsible_lawyer_name: formData.lawyer,
            uyap_lawyer_name: formData.uyapLawyer,
            maddi_tazminat: formData.maddiTazminat ? Number(formData.maddiTazminat) : 0,
            manevi_tazminat: formData.maneviTazminat ? Number(formData.maneviTazminat) : 0,
            acceptance_date: formData.acceptanceDate || undefined,
            bureau_type: formData.bureauType || undefined,
            sub_type_extra: formData.subTypeExtra || undefined,
            judicial_unit: formData.judicialUnit || undefined,
            atama_tarihi: formData.atamaTarihi || undefined,
            hasar_dosya_no: formData.hasarDosyaNo || undefined,
            hukuk_no: formData.hukukNo || undefined,
            klasor_no_2: formData.klasorNo2 || undefined,
            notes: formData.notes || undefined,
            parties: [
                // splitPartyNames: blur tetiklenmeden kalan ";"li girişler kayda ayrı kişiler olarak gitsin
                ...clients.filter(c => c.name).flatMap(c => splitPartyNames(c.name).map(name => ({
                    client_id: dbClients.find(db => toUpperTR(db.name) === toUpperTR(name))?.id,
                    name,
                    role: c.role,
                    party_type: "CLIENT" as const
                }))),
                ...counterParties.filter(c => c.name).flatMap(c => {
                    const names = splitPartyNames(c.name);
                    return names.map(name => ({
                        name,
                        role: c.role,
                        party_type: "COUNTER" as const,
                        // TC tek isimli satırda anlamlı; çoklu isimde kime ait belirsiz
                        tc_no: names.length === 1 ? (c.tc_no || undefined) : undefined
                    }));
                }),
                ...thirdParties.filter(t => t.name).flatMap(t => {
                    const names = splitPartyNames(t.name);
                    return names.map(name => ({
                        name,
                        role: t.role,
                        party_type: "THIRD" as const,
                        tc_no: names.length === 1 ? (t.tc_no || undefined) : undefined
                    }));
                })
            ],
            lawyers: selectedLawyers
        };

        let success: boolean;
        let errorMessage: string | undefined;
        if (isEditMode && editModeCase?.id) {
            const result = await updateCase(editModeCase.id, caseData as CaseData);
            success = result.ok;
            errorMessage = result.error;
        } else {
            const result = await saveCase(caseData as CaseData);
            success = result.ok;
            errorMessage = result.error;
        }

        if (success) {
            // Kaydedilen verinin taslak hayaleti kalmasın (yenilemede "yarım
            // kalan form" diye geri teklif edilirdi).
            draft.clear();
            queryClient.invalidateQueries({ queryKey: ["clients"] });
            toast.success(isEditMode ? "Dava kartı güncellendi!" : "Dava kartı veritabanına kaydedildi!", {
                description: `Ofis No: ${caseId} bilgileri başarıyla işlendi.`
            });

            if (isEditMode && editModeCase?.id) {
                // Refresh history after save
                const updated = await getCase(editModeCase.id);
                if (updated) setCaseHistory(updated.history || []);
            }
        } else {
            toast.error("Hata", { description: errorMessage || "Dava kartı kaydedilemedi. Sunucu hatası oluştu." });
        }
    };

    // Soft-delete gerekçesi (zorunlu, min 3 karakter) — backend Query kısıtıyla birebir
    const [deleteReason, setDeleteReason] = useState("");

    const handleDelete = async () => {
        if (!isEditMode || !editModeCase?.id) return;
        if (deleteReason.trim().length < 3) return;

        const success = await deleteCase(editModeCase.id, deleteReason.trim());
        if (success) {
            toast.success("Arşive taşındı", { description: "Dava listelerden kaldırıldı; yönetici panelinden geri alınabilir." });
            navigate(-1);
        } else {
            toast.error("Hata", { description: "Silme işlemi başarısız oldu." });
        }
    };

    const handleReset = () => {
        // G004: koşul eskiden tanımsız `isAnalyzing`'e bakıyordu — "Temizle"
        // butonu ReferenceError ile sayfayı düşürüyordu. NewCase'te analiz akışı
        // yok; yalnız isLoading kaldı.
        if (isLoading) return;

        // Reset main form data (boş form referansı newCaseDraft.ts'te tek kaynak)
        setFormData({ ...EMPTY_NEW_CASE_FORM });

        // Reset arrays
        setSelectedLawyers([]);
        setClients([{ name: "", role: "Davacı" }]);
        setCounterParties([{ name: "", role: "Davalı" }]);
        setThirdParties([]);

        setCaseStatus("DERDEST");

        // Generate new random ID
        setCaseId(`2024/${Math.floor(Math.random() * 10000).toString().padStart(4, '0')}`);

        // Kullanıcı formu bilinçli temizledi — taslak da gitsin.
        draft.clear();

        toast.info("Form temizlendi.");
    };

    // DANIŞ (danışma) modunda ortada henüz dava olmadığı için form sadeleşir:
    // sadece taraflar, mahkeme, esas no, dava konusu ve notlar gösterilir.
    // Durum DERDEST'e dönünce klasik tam dava kartı geri gelir.
    const isConsult = caseStatus === "DANIŞ";

    return (
        <div>

            <main className="max-w-[1400px] mx-auto">
                {/* DASHBOARD HEADER */}
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-8">
                    <div>
                        <Eyebrow>{isEditMode ? "01 · Düzenleme" : "01 · Yeni Dava"}</Eyebrow>
                        <h1 className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium">
                            {isEditMode ? "Dava Kartı Düzenle" : "Dava Kartı Yönetimi"}
                        </h1>
                        <p className="text-[13px] text-[var(--fg-muted)] mt-2 max-w-[60ch] leading-relaxed">
                            {isEditMode ? "Mevcut dosya bilgilerini güncelleyin ve geçmişi takip edin." : "Yeni dava kartı oluşturun."}
                        </p>
                    </div>

                </div>

                {/* G004: Yarım kalan taslak şeridi — geri yükleme SESSİZ değil,
                    kullanıcı görür ve karar verir. */}
                {draft.pending && (
                    <div className="mb-8 flex flex-wrap items-center gap-3 border border-[var(--brand)]/40 bg-[var(--brand-soft)] px-4 py-3 rounded-[3px]">
                        <RefreshCw className="w-4 h-4 text-[var(--brand)] shrink-0" />
                        <div className="text-[13px] leading-relaxed">
                            <span className="font-semibold text-[var(--fg)]">Yarım kalan dava kartı bulundu</span>
                            <span className="text-[var(--fg-muted)]">
                                {" "}— {describeDraftAge(draft.pending.ageMs)} kaydedildi. Geri yüklerseniz ofis numarası sunucudan yeniden alınır.
                            </span>
                        </div>
                        <div className="ml-auto flex items-center gap-2">
                            <Button type="button" size="sm" onClick={handleRestoreDraft}>
                                Taslağı geri yükle
                            </Button>
                            <Button type="button" size="sm" variant="ghost" onClick={draft.dismiss}>
                                Yoksay
                            </Button>
                        </div>
                    </div>
                )}

                <form onSubmit={handleSubmit}>
                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                        {/* LEFT COLUMN: PRIMARY INFO */}
                        <div className="lg:col-span-8 space-y-8">
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none overflow-hidden">
                                <div className="bg-[var(--bg)] border-b border-[var(--border)] p-6">
                                    <h3 className="flex items-center gap-2 font-mono text-[11px] tracking-[0.2em] uppercase font-semibold text-[var(--brand)] [&>svg]:w-3.5 [&>svg]:h-3.5">
                                        <User className="w-4 h-4" /> 1. Taraf Bilgileri
                                    </h3>
                                </div>
                                <CardContent className="p-8 space-y-10">
                                    {/* Müvekkil Section */}
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between border-b border-border/50 pb-2">
                                            <Label className="text-xs font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <div className="w-1 h-3 bg-primary" />
                                                Müvekkil Tarafı
                                            </Label>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => setClients([...clients, { name: "", role: "Müdahil" }])}
                                                className="h-7 text-xs gap-1 text-primary hover:text-primary hover:bg-primary/5"
                                            >
                                                <Plus className="w-3 h-3" /> Ekle
                                            </Button>
                                        </div>

                                        <div className="grid gap-3">
                                            {clients.map((client, index) => (
                                                <div key={index} className="flex gap-3 items-start animate-in fade-in slide-in-from-top-1 duration-200">
                                                    <div className="flex-1">
                                                        <Popover
                                                            open={clientComboboxesOpen[index]}
                                                            onOpenChange={(open) => {
                                                                const newOpen = [...clientComboboxesOpen];
                                                                newOpen[index] = open;
                                                                setClientComboboxesOpen(newOpen);
                                                            }}
                                                        >
                                                            <PopoverTrigger asChild>
                                                                <Button
                                                                    variant="outline"
                                                                    role="combobox"
                                                                    aria-expanded={clientComboboxesOpen[index]}
                                                                    className="w-full justify-between text-left font-normal bg-[var(--bg)] border-[var(--border-strong)] h-9 px-3 text-sm shadow-none hover:bg-transparent hover:text-foreground"
                                                                >
                                                                    <div className={cn("flex-1 truncate text-left", !client.name && "text-muted-foreground")}>
                                                                        {client.name ? toTitleCase(client.name) : "Müvekkil Seçiniz..."}
                                                                    </div>
                                                                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-20" />
                                                                </Button>
                                                            </PopoverTrigger>
                                                            <PopoverContent className="w-[400px] p-0" align="start">
                                                                <Command>
                                                                    <CommandInput
                                                                        placeholder="Müvekkil ara..."
                                                                        value={clientSearchValues[index] || ""}
                                                                        onValueChange={(val) => {
                                                                            setClientSearchValues(prev => ({ ...prev, [index]: val }));
                                                                        }}
                                                                    />
                                                                    <CommandEmpty>
                                                                        <div className="p-4 text-center">
                                                                            <p className="text-sm text-muted-foreground mb-3">Müvekkil bulunamadı. <br /><strong>"{clientSearchValues[index]}"</strong> ismini kullanmak ister misiniz?</p>
                                                                            <Button
                                                                                size="sm"
                                                                                className="w-full bg-primary/20 text-primary hover:bg-primary/30 mt-2 border-primary/30"
                                                                                type="button"
                                                                                onClick={() => {
                                                                                    const val = clientSearchValues[index] || "";
                                                                                    if (!val.trim()) return;
                                                                                    const names = splitPartyNames(val);
                                                                                    const updated = [...clients];
                                                                                    updated[index].name = toTitleCase(names[0] ?? val.trim());
                                                                                    if (names.length > 1) {
                                                                                        updated.splice(index + 1, 0, ...names.slice(1).map(n => ({ name: toTitleCase(n), role: updated[index].role })));
                                                                                    }
                                                                                    setClients(updated);
                                                                                    updateTrackingNumber(undefined, undefined, updated);

                                                                                    const newOpen = [...clientComboboxesOpen];
                                                                                    newOpen[index] = false;
                                                                                    setClientComboboxesOpen(newOpen);
                                                                                }}
                                                                            >
                                                                                <Plus className="w-4 h-4 mr-2" /> Hızlı Müvekkil Ekle
                                                                            </Button>
                                                                        </div>
                                                                    </CommandEmpty>
                                                                    <CommandGroup className="max-h-64 overflow-auto">
                                                                        {dbClients.map((dbClient) => (
                                                                            <CommandItem
                                                                                key={dbClient.id}
                                                                                value={`${dbClient.name} ${dbClient.cari_kod || ""} ${dbClient.tc_no || ""}`}
                                                                                onSelect={() => {
                                                                                    const updated = [...clients];
                                                                                    updated[index].name = toTitleCase(dbClient.name);
                                                                                    updated[index].category = dbClient.category;
                                                                                    setClients(updated);
                                                                                    updateTrackingNumber(undefined, undefined, updated);

                                                                                    const newOpen = [...clientComboboxesOpen];
                                                                                    newOpen[index] = false;
                                                                                    setClientComboboxesOpen(newOpen);
                                                                                }}
                                                                            >
                                                                                <Check
                                                                                    className={`mr-2 h-4 w-4 ${client.name === dbClient.name ? "opacity-100" : "opacity-0"}`}
                                                                                />
                                                                                <div className="flex flex-col">
                                                                                    <div className="flex items-center gap-2">
                                                                                        <span>{toTitleCase(dbClient.name)}</span>
                                                                                        {dbClient.cari_kod && (
                                                                                            <span className="text-[9px] bg-primary/10 text-primary px-1 rounded font-bold">
                                                                                                {dbClient.cari_kod}
                                                                                            </span>
                                                                                        )}
                                                                                    </div>
                                                                                    {dbClient.tc_no && <span className="text-[10px] text-muted-foreground">{dbClient.tc_no}</span>}
                                                                                </div>
                                                                            </CommandItem>
                                                                        ))}
                                                                    </CommandGroup>
                                                                </Command>
                                                            </PopoverContent>
                                                        </Popover>
                                                        {partyMatchFlags[`client-${index}`]?.hasMatch && (
                                                            <div className={cn(
                                                                "mt-1 text-[10px]",
                                                                partyMatchFlags[`client-${index}`]?.conflict ? "text-red-600 font-semibold" : "text-muted-foreground"
                                                            )}>
                                                                {rowMatchSummary(`client-${index}`, undefined, false)}
                                                            </div>
                                                        )}
                                                    </div>
                                                    <PartyMatchIndicator
                                                        value={client.name}
                                                        partyType="CLIENT"
                                                        excludeCaseId={editModeCase?.id}
                                                        onStateChange={(s) => setRowMatchFlag(`client-${index}`, s)}
                                                        className="mt-[13px]"
                                                    />
                                                    <Checkbox
                                                        checked={approvedFields.clients[index]}
                                                        onCheckedChange={() => handleFieldApproval('client', index)}
                                                        className={cn("mt-2.5", approvedFields.clients[index] && "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success")}
                                                    />
                                                    <div className="w-40">
                                                        <Select
                                                            value={client.role}
                                                            onValueChange={(v) => {
                                                                const updated = [...clients];
                                                                updated[index].role = v;
                                                                setClients(updated);
                                                            }}
                                                        >
                                                            <SelectTrigger className="h-9 bg-[var(--bg)] border-[var(--border-strong)]">
                                                                <SelectValue />
                                                            </SelectTrigger>
                                                            <SelectContent>
                                                                {TARAF_ROLLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                                            </SelectContent>
                                                        </Select>
                                                    </div>
                                                    {index > 0 && (
                                                        <Button
                                                            type="button"
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-9 w-9 text-muted-foreground hover:text-destructive hover:bg-destructive/5"
                                                            onClick={() => setClients(clients.filter((_, i) => i !== index))}
                                                        >
                                                            <X className="w-4 h-4" />
                                                        </Button>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Karşı Taraf Section */}
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between border-b border-border/50 pb-2">
                                            <Label className="text-xs font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <div className="w-1 h-3 bg-primary" />
                                                Karşı Taraf Bilgileri
                                            </Label>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => setCounterParties([...counterParties, { name: "", role: "Davalı" }])}
                                                className="h-7 text-xs gap-1 text-primary hover:text-primary hover:bg-primary/5"
                                            >
                                                <Plus className="w-3 h-3" /> Ekle
                                            </Button>
                                        </div>

                                        <div className="grid gap-3">
                                            {counterParties.map((party, index) => (
                                                <div key={index} className="flex gap-3 items-start animate-in fade-in slide-in-from-top-1 duration-200">
                                                    <div className="flex-1">
                                                        <Input
                                                            placeholder="Karşı Taraf Adı / Ünvanı"
                                                            value={party.name}
                                                            onChange={(e) => {
                                                                const updated = [...counterParties];
                                                                updated[index].name = e.target.value;
                                                                setCounterParties(updated);
                                                            }}
                                                            onBlur={(e) => {
                                                                const names = splitPartyNames(e.target.value);
                                                                const updated = [...counterParties];
                                                                updated[index].name = toTitleCase(names[0] ?? e.target.value);
                                                                if (names.length > 1) {
                                                                    updated.splice(index + 1, 0, ...names.slice(1).map(n => ({ name: toTitleCase(n), role: updated[index].role })));
                                                                }
                                                                setCounterParties(updated);
                                                            }}
                                                            className="h-9 text-sm bg-[var(--bg)] border-[var(--border-strong)] focus:border-primary/50 text-left"
                                                        />
                                                        {(partyMatchFlags[`counter-${index}`]?.hasMatch || party.tc_no) && splitPartyNames(party.name).length === 1 && (
                                                            <div className="mt-1.5 flex items-center gap-2">
                                                                <Input
                                                                    inputMode="numeric"
                                                                    maxLength={11}
                                                                    placeholder="TC Kimlik No (opsiyonel)"
                                                                    value={party.tc_no || ""}
                                                                    onChange={(e) => {
                                                                        const updated = [...counterParties];
                                                                        updated[index].tc_no = e.target.value.replace(/\D/g, "");
                                                                        setCounterParties(updated);
                                                                    }}
                                                                    className="h-7 w-48 text-xs font-mono bg-[var(--bg)] border-[var(--border)]"
                                                                />
                                                                <span className={cn(
                                                                    "text-[10px]",
                                                                    partyMatchFlags[`counter-${index}`]?.conflict ? "text-red-600 font-semibold" : "text-muted-foreground"
                                                                )}>
                                                                    {rowMatchSummary(`counter-${index}`, party.tc_no)}
                                                                </span>
                                                            </div>
                                                        )}
                                                    </div>
                                                    <PartyMatchIndicator
                                                        value={party.name}
                                                        partyType="COUNTER"
                                                        excludeCaseId={editModeCase?.id}
                                                        tcByName={party.tc_no && party.name ? { [toUpperTR(party.name)]: party.tc_no } : undefined}
                                                        onStateChange={(s) => setRowMatchFlag(`counter-${index}`, s)}
                                                        className="mt-[13px]"
                                                    />
                                                    <Checkbox
                                                        checked={approvedFields.counterParties[index]}
                                                        onCheckedChange={() => handleFieldApproval('counter', index)}
                                                        className={cn("mt-2.5", approvedFields.counterParties[index] && "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success")}
                                                    />
                                                    <div className="w-40">
                                                        <Select
                                                            value={party.role}
                                                            onValueChange={(v) => {
                                                                const updated = [...counterParties];
                                                                updated[index].role = v;
                                                                setCounterParties(updated);
                                                            }}
                                                        >
                                                            <SelectTrigger className="h-9 bg-[var(--bg)] border-[var(--border-strong)]">
                                                                <SelectValue />
                                                            </SelectTrigger>
                                                            <SelectContent>
                                                                {TARAF_ROLLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                                            </SelectContent>
                                                        </Select>
                                                    </div>
                                                    {index > 0 && (
                                                        <Button
                                                            type="button"
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-9 w-9 text-muted-foreground hover:text-destructive hover:bg-destructive/5"
                                                            onClick={() => setCounterParties(counterParties.filter((_, i) => i !== index))}
                                                        >
                                                            <X className="w-4 h-4" />
                                                        </Button>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Üçüncü Taraflar Section — danışma modunda gizli */}
                                    {!isConsult && (
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between border-b border-border/50 pb-2">
                                            <Label className="text-xs font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <div className="w-1 h-3 bg-primary" />
                                                Üçüncü Taraflar
                                            </Label>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="sm"
                                                className="h-7 text-xs gap-1 text-primary hover:text-primary hover:bg-primary/5"
                                                onClick={() => setThirdParties([...thirdParties, { name: "", role: "Tanık" }])}
                                            >
                                                <Plus className="w-3 h-3" /> Ekle
                                            </Button>
                                        </div>

                                        {thirdParties.length === 0 ? (
                                            <div className="text-[11px] text-muted-foreground italic py-1 px-1">
                                                Kayıtlı tanık veya bilirkişi bulunmuyor.
                                            </div>
                                        ) : (
                                            <div className="grid gap-2">
                                                {thirdParties.map((party, index) => (
                                                    <div key={index} className="flex gap-2 items-start animate-in fade-in slide-in-from-top-1 duration-200">
                                                        <div className="flex-1">
                                                            <Input
                                                                placeholder="İsim / Ünvan"
                                                                value={party.name}
                                                                onChange={(e) => {
                                                                    const updated = [...thirdParties];
                                                                    updated[index].name = e.target.value;
                                                                    setThirdParties(updated);
                                                                }}
                                                                onBlur={(e) => {
                                                                    const names = splitPartyNames(e.target.value);
                                                                    const updated = [...thirdParties];
                                                                    updated[index].name = toTitleCase(names[0] ?? e.target.value);
                                                                    if (names.length > 1) {
                                                                        updated.splice(index + 1, 0, ...names.slice(1).map(n => ({ name: toTitleCase(n), role: updated[index].role })));
                                                                    }
                                                                    setThirdParties(updated);
                                                                }}
                                                                className="h-9 text-sm bg-[var(--bg)] border-[var(--border-strong)] focus:border-primary/40 text-left"
                                                            />
                                                            {(partyMatchFlags[`third-${index}`]?.hasMatch || party.tc_no) && splitPartyNames(party.name).length === 1 && (
                                                                <div className="mt-1.5 flex items-center gap-2">
                                                                    <Input
                                                                        inputMode="numeric"
                                                                        maxLength={11}
                                                                        placeholder="TC Kimlik No (opsiyonel)"
                                                                        value={party.tc_no || ""}
                                                                        onChange={(e) => {
                                                                            const updated = [...thirdParties];
                                                                            updated[index].tc_no = e.target.value.replace(/\D/g, "");
                                                                            setThirdParties(updated);
                                                                        }}
                                                                        className="h-7 w-48 text-xs font-mono bg-[var(--bg)] border-[var(--border)]"
                                                                    />
                                                                    <span className={cn(
                                                                        "text-[10px]",
                                                                        partyMatchFlags[`third-${index}`]?.conflict ? "text-red-600 font-semibold" : "text-muted-foreground"
                                                                    )}>
                                                                        {rowMatchSummary(`third-${index}`, party.tc_no)}
                                                                    </span>
                                                                </div>
                                                            )}
                                                        </div>
                                                        <PartyMatchIndicator
                                                            value={party.name}
                                                            partyType="THIRD"
                                                            excludeCaseId={editModeCase?.id}
                                                            tcByName={party.tc_no && party.name ? { [toUpperTR(party.name)]: party.tc_no } : undefined}
                                                            onStateChange={(s) => setRowMatchFlag(`third-${index}`, s)}
                                                            className="mt-[13px]"
                                                        />
                                                        <Checkbox
                                                            checked={approvedFields.thirdParties[index]}
                                                            onCheckedChange={() => handleFieldApproval('third', index)}
                                                            className={cn("mt-2", approvedFields.thirdParties[index] && "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success")}
                                                        />
                                                        <div className="w-32">
                                                            <Select
                                                                value={party.role}
                                                                onValueChange={(v) => {
                                                                    const updated = [...thirdParties];
                                                                    updated[index].role = v;
                                                                    setThirdParties(updated);
                                                                }}
                                                            >
                                                                <SelectTrigger className="h-8 text-xs bg-[var(--bg)] border-[var(--border-strong)]">
                                                                    <SelectValue />
                                                                </SelectTrigger>
                                                                <SelectContent>
                                                                    {UCUNCU_TARAF_ROLLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                                                </SelectContent>
                                                            </Select>
                                                        </div>
                                                        <Button
                                                            type="button"
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/5"
                                                            onClick={() => setThirdParties(thirdParties.filter((_, i) => i !== index))}
                                                        >
                                                            <X className="w-3 h-3" />
                                                        </Button>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                    )}
                                </CardContent>
                            </Card>

                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none overflow-hidden">
                                <div className="bg-[var(--bg)] border-b border-[var(--border)] p-6">
                                    <h3 className="flex items-center gap-2 font-mono text-[11px] tracking-[0.2em] uppercase font-semibold text-[var(--brand)] [&>svg]:w-3.5 [&>svg]:h-3.5">
                                        <Gavel className="w-4 h-4" /> {isConsult ? "2. Danışma Bilgileri" : "2. Dava Bilgileri"}
                                    </h3>
                                </div>
                                <CardContent className="p-8 space-y-6">
                                    <div className="grid md:grid-cols-2 gap-x-8 gap-y-6">
                                        <div className="space-y-2 md:col-span-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <Building className="w-3 h-3" /> Mahkeme Bilgisi
                                            </Label>
                                            <div className="relative flex items-center gap-2">
                                                <Input
                                                    placeholder="Örn: Bursa 13. Tüketici Mahkemesi"
                                                    value={formData.court}
                                                    onChange={(e) => setFormData({ ...formData, court: e.target.value })}
                                                    className="text-base bg-[var(--bg)] border-[var(--border-strong)] flex-1"
                                                />
                                                <Checkbox
                                                    checked={approvedFields.court}
                                                    onCheckedChange={() => handleFieldApproval('court')}
                                                    className={approvedFields.court ? "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success" : ""}
                                                />
                                            </div>
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <FileText className="w-3 h-3" /> Esas No
                                            </Label>
                                            <Input
                                                placeholder="2024/123"
                                                value={formData.esasNo}
                                                onChange={(e) => setFormData({ ...formData, esasNo: e.target.value })}
                                                className="font-mono bg-[var(--bg)] border-[var(--border-strong)]"
                                            />
                                        </div>

                                        {/* Aşağıdaki teknik alanlar yalnızca gerçek dava (DERDEST/MAHZEN) için gösterilir */}
                                        {!isConsult && (
                                        <>
                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <FileText className="w-3 h-3" /> Hasar Dosya No
                                            </Label>
                                            <Input
                                                placeholder="Hasar Dosya Numarası"
                                                value={formData.hasarDosyaNo}
                                                onChange={(e) => setFormData({ ...formData, hasarDosyaNo: e.target.value })}
                                                className="font-mono bg-[var(--bg)] border-[var(--border-strong)]"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <FileText className="w-3 h-3" /> Hukuk No
                                            </Label>
                                            <Input
                                                placeholder="Hukuk Numarası"
                                                value={formData.hukukNo}
                                                onChange={(e) => setFormData({ ...formData, hukukNo: e.target.value })}
                                                className="font-mono bg-[var(--bg)] border-[var(--border-strong)]"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <FileText className="w-3 h-3" /> Klasör No (Eski Sistem)
                                            </Label>
                                            <Input
                                                placeholder="Eski sistem klasör no"
                                                value={formData.klasorNo2}
                                                onChange={(e) => setFormData({ ...formData, klasorNo2: e.target.value })}
                                                className="font-mono bg-[var(--bg)] border-[var(--border-strong)]"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <Calendar className="w-3 h-3" /> Atama Tarihi
                                            </Label>
                                            <Input
                                                type="date"
                                                value={formData.atamaTarihi}
                                                onChange={(e) => setFormData({ ...formData, atamaTarihi: e.target.value })}
                                                className="bg-[var(--bg)] border-[var(--border-strong)]"
                                            />
                                        </div>


                                        <div 
                                            className={cn(
                                                "grid grid-cols-2 gap-4 md:col-span-1 transition-all duration-300",
                                                isShaking && "animate-crazy-shake"
                                            )}
                                        >
                                            <div className="space-y-2">
                                                <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                    <Briefcase className="w-3 h-3" /> Yargı Türü
                                                </Label>
                                                <Select
                                                    value={formData.fileType}
                                                    onValueChange={(v) => {
                                                        setFormData({ ...formData, fileType: v, subType: "", judicialUnit: "" });
                                                        updateTrackingNumber(v);
                                                        triggerShake();
                                                    }}
                                                >
                                                    <SelectTrigger 
                                                        className="bg-[var(--bg)] border-[var(--border-strong)] hover:border-primary/50 transition-colors"
                                                        onClick={() => triggerShake()}
                                                    >
                                                        <SelectValue placeholder="Seçiniz..." />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {DOSYA_TURLERI.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                                    </SelectContent>
                                                </Select>
                                            </div>

                                            <div className="space-y-2">
                                                <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                    <Gavel className="w-3 h-3" /> Yargı Birimi
                                                </Label>
                                                <Select
                                                    value={formData.judicialUnit}
                                                    onValueChange={(v) => {
                                                        setFormData({ ...formData, judicialUnit: v });
                                                        triggerShake();
                                                    }}
                                                    disabled={!formData.fileType}
                                                >
                                                    <SelectTrigger 
                                                        className="bg-[var(--bg)] border-[var(--border-strong)] overflow-hidden hover:border-primary/50 transition-colors"
                                                        onClick={() => triggerShake()}
                                                    >
                                                        <SelectValue placeholder={formData.fileType ? "Birim Seç..." : "Tür Seçin"} />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {(ALT_TURLER[formData.fileType] || []).map(t => (
                                                            <SelectItem key={t} value={t}>{t}</SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <Scale className="w-3 h-3" /> Alt Tür (Yargı Türü Alt Kırılımı)
                                            </Label>
                                            <Popover>
                                                <PopoverTrigger asChild>
                                                    <Button
                                                        variant="outline"
                                                        role="combobox"
                                                        className={`w-full justify-between h-9 text-xs border-[var(--border-strong)] ${!formData.subType ? "text-muted-foreground bg-transparent" : "bg-transparent text-foreground"}`}
                                                    >
                                                        {formData.subType ? toTitleCase(formData.subType) : "Seçiniz..."}
                                                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                                    </Button>
                                                </PopoverTrigger>
                                                <PopoverContent className="w-full p-0 max-h-64" align="start">
                                                    <Command>
                                                        <CommandInput placeholder="Alt tür ara..." />
                                                        <CommandEmpty>Kayıt bulunamadı.</CommandEmpty>
                                                        <CommandGroup className="overflow-auto max-h-56">
                                                            {specialties.map((s) => (
                                                                <CommandItem
                                                                    key={s.code}
                                                                    value={s.name ?? ""}
                                                                    onSelect={(currentValue) => {
                                                                        setFormData({ ...formData, subType: currentValue === formData.subType ? "" : currentValue });
                                                                    }}
                                                                >
                                                                    <Check className={`mr-2 h-4 w-4 ${formData.subType === s.name ? "opacity-100" : "opacity-0"}`} />
                                                                    {toTitleCase(s.name ?? "")}
                                                                </CommandItem>
                                                            ))}
                                                        </CommandGroup>
                                                    </Command>
                                                </PopoverContent>
                                            </Popover>
                                        </div>

                                        {/* Ek Alt Kırılım geçici olarak gizli (2026-08-04): dropdown listesi
                                            güncellenecek, sonra tekrar kullanıma açılacak. formData.subTypeExtra
                                            state'i ve kayıt payload'ı korunuyor — düzenleme modunda mevcut değer
                                            silinmesin. Geri açarken required_fields.py ve caseIntakeFields.ts'teki
                                            sub_type_extra satırlarını da geri al.
                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <FileText className="w-3 h-3" /> Ek Alt Kırılım
                                            </Label>
                                            <Popover>
                                                <PopoverTrigger asChild>
                                                    <Button
                                                        variant="outline"
                                                        role="combobox"
                                                        className={`w-full justify-between h-9 text-xs border-[var(--border-strong)] ${!formData.subTypeExtra ? "text-muted-foreground bg-transparent" : "bg-transparent text-foreground"}`}
                                                    >
                                                        {formData.subTypeExtra ? toTitleCase(formData.subTypeExtra) : "Seçiniz..."}
                                                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                                    </Button>
                                                </PopoverTrigger>
                                                <PopoverContent className="w-full p-0 max-h-64" align="start">
                                                    <Command>
                                                        <CommandInput placeholder="Ek alt kırılım ara..." />
                                                        <CommandEmpty>Kayıt bulunamadı.</CommandEmpty>
                                                        <CommandGroup className="overflow-auto max-h-56">
                                                            {specialties.map((s) => (
                                                                <CommandItem
                                                                    key={s.code}
                                                                    value={s.name ?? ""}
                                                                    onSelect={(currentValue) => {
                                                                        setFormData({ ...formData, subTypeExtra: currentValue === formData.subTypeExtra ? "" : currentValue });
                                                                    }}
                                                                >
                                                                    <Check className={`mr-2 h-4 w-4 ${formData.subTypeExtra === s.name ? "opacity-100" : "opacity-0"}`} />
                                                                    {toTitleCase(s.name ?? "")}
                                                                </CommandItem>
                                                            ))}
                                                        </CommandGroup>
                                                    </Command>
                                                </PopoverContent>
                                            </Popover>
                                        </div>
                                        */}

                                        <div className="space-y-4 md:col-span-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <Briefcase className="w-3 h-3" /> Hizmet Türü (Çoklu Seçim)
                                            </Label>
                                            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 p-4 bg-muted/5 border border-border/40 rounded-lg">
                                                {HIZMET_TURLERI.map((t) => (
                                                    <div key={t.index} className="flex items-center space-x-2">
                                                        <Checkbox
                                                            id={`service-${t.index}`}
                                                            checked={formData.serviceType[t.index] === "1"}
                                                            onCheckedChange={(checked) => handleServiceToggle(t.index, !!checked)}
                                                        />
                                                        <Label
                                                            htmlFor={`service-${t.index}`}
                                                            className="text-sm font-medium leading-none cursor-pointer"
                                                        >
                                                            {t.label}
                                                        </Label>
                                                    </div>
                                                ))}
                                            </div>
                                            <p className="text-[10px] text-muted-foreground italic">
                                                Seçilen her hizmet dosya numarasının son bloğuna (11000 gibi) eklenir.
                                            </p>
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <Calendar className="w-3 h-3" /> Dosya Açılış Tarihi
                                            </Label>
                                            <Input
                                                type="date"
                                                value={formData.fileOpeningDate}
                                                onChange={(e) => setFormData({ ...formData, fileOpeningDate: e.target.value })}
                                                className="bg-[var(--bg)] border-[var(--border-strong)]"
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <Calendar className="w-3 h-3" /> İş Kabul Tarihi
                                            </Label>
                                            <Input
                                                type="date"
                                                value={formData.acceptanceDate}
                                                onChange={(e) => setFormData({ ...formData, acceptanceDate: e.target.value })}
                                                className="bg-[var(--bg)] border-[var(--border-strong)]"
                                            />
                                        </div>
                                        </>
                                        )}

                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <Sparkles className="w-3 h-3" /> {isConsult ? "Danışma Konusu" : "Davanın Konusu"}
                                            </Label>
                                            <Popover open={subjectComboboxOpen} onOpenChange={setSubjectComboboxOpen}>
                                                <PopoverTrigger asChild>
                                                    <Button
                                                        variant="outline"
                                                        role="combobox"
                                                        aria-expanded={subjectComboboxOpen}
                                                        className="w-full justify-between font-normal bg-[var(--bg)] border-[var(--border-strong)]"
                                                    >
                                                        {formData.subject || "Seçiniz..."}
                                                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                                    </Button>
                                                </PopoverTrigger>
                                                <PopoverContent className="w-[400px] p-0" align="start">
                                                    <Command>
                                                        <CommandInput placeholder="Dava konusu ara..." />
                                                        <CommandEmpty>Sonuç bulunamadı.</CommandEmpty>
                                                        <CommandGroup className="max-h-64 overflow-auto">
                                                            {[...caseSubjects].sort((a, b) => {
                                                                const specificSubjects = ["Rücuen Alacak (Tıbbi Kötü Uygulama)", "Tazminat (Tıbbi Kötü Uygulama)"];
                                                                const indexA = specificSubjects.indexOf(a.name);
                                                                const indexB = specificSubjects.indexOf(b.name);
                                                                if (indexA !== -1 && indexB !== -1) return indexA - indexB;
                                                                if (indexA !== -1) return -1;
                                                                if (indexB !== -1) return 1;
                                                                return 0; // Maintain original order for others
                                                            }).map((subject) => (
                                                                <CommandItem
                                                                    key={subject.code}
                                                                    value={subject.name}
                                                                    onSelect={(currentValue) => {
                                                                        setFormData({ ...formData, subject: currentValue === formData.subject ? "" : currentValue });
                                                                        setSubjectComboboxOpen(false);
                                                                    }}
                                                                >
                                                                    <Check
                                                                        className={`mr-2 h-4 w-4 ${formData.subject === subject.name ? "opacity-100" : "opacity-0"}`}
                                                                    />
                                                                    {subject.name}
                                                                </CommandItem>
                                                            ))}
                                                        </CommandGroup>
                                                    </Command>
                                                </PopoverContent>
                                            </Popover>
                                        </div>
                                        <div className="space-y-2 md:col-span-2">
                                            <Label className="text-[11px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em] flex items-center gap-2">
                                                <FileText className="w-3 h-3" /> Notlar
                                            </Label>
                                            <Textarea
                                                placeholder="Dosyaya özel notlar..."
                                                value={formData.notes}
                                                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                                                className="bg-[var(--bg)] border-[var(--border-strong)] resize-none min-h-[80px]"
                                            />
                                        </div>

                                    </div>
                                </CardContent>
                            </Card>
                        </div>

                        {/* RIGHT COLUMN: SUMMARY & SIDEBAR ACTIONS */}
                        <div className="lg:col-span-4 space-y-8 lg:sticky lg:top-8">
                            {/* CASE BADGE CARD */}
                            <Card className={`bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none border-l-4 p-6 
                                ${caseStatus === 'DERDEST' ? 'border-primary/20 bg-primary/5 border-l-primary' :
                                    caseStatus === 'DANIŞ' ? 'border-blue-500/20 bg-blue-500/5 border-l-blue-500' :
                                        'border-muted/40 bg-muted/5 border-l-muted-foreground'}`}>
                                <div className="flex items-center justify-between mb-2">
                                    <span className={`text-[10px] font-bold uppercase tracking-widest 
                                        ${caseStatus === 'DERDEST' ? 'text-primary' :
                                            caseStatus === 'DANIŞ' ? 'text-blue-500' :
                                                'text-muted-foreground'}`}>Ofis No</span>
                                    <Select value={caseStatus} onValueChange={setCaseStatus}>
                                        <SelectTrigger className={`w-fit h-6 text-[10px] font-bold border-0 px-2 gap-1 rounded-md transition-colors focus:ring-0 focus:ring-offset-0 
                                            ${caseStatus === 'DERDEST' ? 'bg-primary/20 text-primary hover:bg-primary/30' :
                                                caseStatus === 'DANIŞ' ? 'bg-blue-500/20 text-blue-500 hover:bg-blue-500/30' :
                                                    'bg-muted text-muted-foreground hover:bg-muted/80'}`}>
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="DANIŞ" className="text-blue-500 font-medium">DANIŞ</SelectItem>
                                            <SelectItem value="DERDEST" className="text-primary font-medium">DERDEST</SelectItem>
                                            <SelectItem value="MAHZEN" className="text-muted-foreground font-medium">MAHZEN</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="text-lg sm:text-xl md:text-2xl font-mono font-bold break-words leading-tight">
                                    {caseId.split('.').map((part, i, arr) => (
                                        <span key={i} className="whitespace-nowrap">
                                            {part}
                                            {i < arr.length - 1 && '.\u200B'}
                                        </span>
                                    ))}
                                </div>
                                <p className="text-xs text-muted-foreground mt-2 italic">
                                    Sistem tarafından otomatik atanan takip numarasıdır.
                                </p>
                                {/* G002: sıra numarası alınamadı — gösterilen numara GÜNCEL DEĞİL, kayıt bloke */}
                                {sequenceError && !isEditMode && (
                                    <p role="alert" className="text-xs text-destructive mt-2">
                                        {sequenceError} Numara doğrulanana kadar kayıt yapılamaz.
                                    </p>
                                )}
                            </Card>

                            {/* Sorumlu / Büro / Tazminat — danışma modunda gizli */}
                            {!isConsult && (
                            <>
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none overflow-hidden">
                                <div className="bg-[var(--bg)] border-b border-[var(--border)] p-4">
                                    <h3 className="font-mono text-[10px] tracking-[0.22em] uppercase font-semibold text-[var(--brand)] flex items-center gap-2">
                                        <Briefcase className="w-3 h-3" /> Sorumlu Bilgileri
                                    </h3>
                                </div>
                                <div className="p-5 space-y-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em]">Sorumlu Avukat(lar)</Label>

                                        {selectedLawyers.length > 0 && (
                                            <div className="flex flex-wrap gap-2 mb-2">
                                                {selectedLawyers.map((sl, idx) => (
                                                    <div key={idx} className="flex items-center gap-1 bg-primary/10 text-primary px-2 py-1 rounded text-[11px] font-medium border border-primary/20 shadow-sm">
                                                        {sl.name}
                                                        <button
                                                            type="button"
                                                            onClick={(e) => { e.preventDefault(); setSelectedLawyers(prev => prev.filter((_, i) => i !== idx)); }}
                                                            className="hover:bg-primary/20 rounded-full p-0.5 transition-colors"
                                                        >
                                                            <X className="w-3 h-3" />
                                                        </button>
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        <Select onValueChange={(v) => {
                                            if (v && !selectedLawyers.find(l => l.name === v)) {
                                                const lawyerObj = lawyers.find(l => l.name === v);
                                                setSelectedLawyers(prev => [...prev, { name: v, lawyer_id: lawyerObj ? lawyerObj.id : null }]);
                                            }
                                        }}>
                                            <SelectTrigger className="h-8 text-xs bg-[var(--bg)] border-[var(--border-strong)]">
                                                <SelectValue placeholder="Avukat Ekle..." />
                                            </SelectTrigger>
                                            <SelectContent className="max-h-64">
                                                {lawyers.map(t => <SelectItem key={t.code || t.name} value={t.name}>{t.name}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em]">UYAP Avukat</Label>
                                        <Select value={formData.uyapLawyer} onValueChange={(v) => setFormData({ ...formData, uyapLawyer: v })}>
                                            <SelectTrigger className="h-8 text-xs bg-[var(--bg)] border-[var(--border-strong)]">
                                                <SelectValue placeholder="Seçiniz..." />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {lawyers.map(t => <SelectItem key={t.code} value={t.name}>{t.name}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </Card>

                            {/* BÜRO ÖZEL TÜRÜ */}
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none overflow-hidden">
                                <div className="bg-[var(--bg)] border-b border-[var(--border)] p-4">
                                    <h3 className="font-mono text-[10px] tracking-[0.22em] uppercase font-semibold text-[var(--brand)] flex items-center gap-2">
                                        <Building className="w-3 h-3" /> Büro Özel Türü
                                    </h3>
                                </div>
                                <div className="p-5 space-y-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-mono font-semibold text-[var(--fg-subtle)] uppercase tracking-[0.16em]">Tür Seçiniz</Label>
                                        <Select value={formData.bureauType} onValueChange={(v) => setFormData({ ...formData, bureauType: v })}>
                                            <SelectTrigger className="h-8 text-xs bg-[var(--bg)] border-[var(--border-strong)]">
                                                <SelectValue placeholder="Seçiniz..." />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {BURO_OZEL_TURU.map(t => <SelectItem key={t} value={t}>{toTitleCase(t)}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </Card>

                            {/* COMPENSATION CLAIMS */}
                            <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none overflow-hidden">
                                <div className="bg-[var(--bg)] border-b border-[var(--border)] p-4">
                                    <h3 className="font-mono text-[10px] tracking-[0.22em] uppercase font-semibold text-[var(--brand)] flex items-center gap-2">
                                        <Banknote className="w-3 h-3" /> Tazminat Talepleri
                                    </h3>
                                </div>
                                <div className="p-5 space-y-4">
                                    <div className="space-y-1.5">
                                        <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] flex items-center gap-1.5">
                                            <Coins className="w-3 h-3" /> Maddi Tazminat
                                        </Label>
                                        <div className="relative">
                                            <Input
                                                type="text"
                                                placeholder="0,00"
                                                value={formData.maddiTazminat ? Number(formData.maddiTazminat).toLocaleString('tr-TR') : ''}
                                                onChange={(e) => {
                                                    const value = e.target.value.replace(/[^0-9]/g, '');
                                                    setFormData({ ...formData, maddiTazminat: value });
                                                }}
                                                className="h-9 text-base font-mono pr-10 bg-[var(--bg)] border-[var(--border-strong)]"
                                            />
                                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground font-bold font-mono">TL</span>
                                        </div>
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] flex items-center gap-1.5">
                                            <Heart className="w-3 h-3" /> Manevi Tazminat
                                        </Label>
                                        <div className="relative">
                                            <Input
                                                type="text"
                                                placeholder="0,00"
                                                value={formData.maneviTazminat ? Number(formData.maneviTazminat).toLocaleString('tr-TR') : ''}
                                                onChange={(e) => {
                                                    const value = e.target.value.replace(/[^0-9]/g, '');
                                                    setFormData({ ...formData, maneviTazminat: value });
                                                }}
                                                className="h-9 text-base font-mono pr-10 bg-[var(--bg)] border-[var(--border-strong)]"
                                            />
                                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground font-bold font-mono">TL</span>
                                        </div>
                                    </div>
                                </div>
                            </Card>
                            </>
                            )}

                            {/* GLOBAL ACTIONS — sağ sticky işlem kartı */}
                            <div className="bg-[var(--bg-elevated)] border border-[var(--border)] sticky top-4">
                                <div className="px-5 py-4 border-b border-[var(--border)]">
                                    <Eyebrow tone="brand">{isEditMode ? "İşlemi Tamamla" : "Kayıt"}</Eyebrow>
                                </div>
                                <div className="p-5 grid gap-2.5">
                                    <Button
                                        type="submit"
                                        className="w-full h-11 bg-[var(--brand)] hover:bg-[var(--brand-hover)] text-[var(--brand-fg)] rounded-[3px] font-medium tracking-[0.03em] gap-2"
                                        disabled={isLoading || isSaving}
                                    >
                                        {isSaving || isLoading ? (
                                            <>
                                                <Loader2 className="h-4 w-4 animate-spin" />
                                                İşleniyor…
                                            </>
                                        ) : (
                                            <>
                                                <Save className="h-4 w-4" />
                                                {isEditMode ? "Kaydet" : isConsult ? "Danışma Kartını Aç" : "Dava Kartını Aç"}
                                            </>
                                        )}
                                    </Button>
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        className="w-full h-10 bg-transparent border border-[var(--border-strong)] text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-[var(--bg)] rounded-[3px] font-medium"
                                        onClick={isEditMode ? () => navigate(-1) : handleReset}
                                        disabled={isLoading || isSaving}
                                    >
                                        {isEditMode ? "Geri Dön" : "Vazgeç"}
                                    </Button>

                                    {isEditMode && (
                                        <AlertDialog>
                                            <AlertDialogTrigger asChild>
                                                <Button
                                                    type="button"
                                                    className="w-full h-10 mt-2 bg-transparent border border-[#a8323b]/30 text-[#a8323b] hover:bg-[#a8323b]/10 rounded-[3px] font-medium gap-2"
                                                >
                                                    <Trash2 className="w-3.5 h-3.5" />
                                                    Davayı Sil
                                                </Button>
                                            </AlertDialogTrigger>
                                            <AlertDialogContent className="theme-classic bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                                                <AlertDialogHeader>
                                                    <AlertDialogTitle className="font-display font-medium text-[18px] text-[#a8323b] flex items-center gap-2">
                                                        <Trash2 className="w-4 h-4" />
                                                        Davayı silmek istediğinize emin misiniz?
                                                    </AlertDialogTitle>
                                                    <AlertDialogDescription className="text-[13px] text-[var(--fg-muted)] leading-relaxed">
                                                        Dava listelerden kaldırılır ve arşive taşınır; <strong className="text-[var(--fg)]">yönetici panelinden geri alınabilir.</strong> Gerekçe zorunludur ve kayıt altına alınır.
                                                    </AlertDialogDescription>
                                                </AlertDialogHeader>
                                                <textarea
                                                    rows={2}
                                                    value={deleteReason}
                                                    onChange={e => setDeleteReason(e.target.value)}
                                                    placeholder="Silme gerekçesi (zorunlu)…"
                                                    className="w-full text-[13px] p-2 bg-[var(--bg)] border border-[var(--border-strong)] rounded-[3px] text-[var(--fg)] placeholder:text-[var(--fg-muted)] resize-none focus:outline-none focus:border-[#a8323b]/60"
                                                />
                                                <AlertDialogFooter>
                                                    <AlertDialogCancel className="bg-transparent border-[var(--border-strong)] text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-[var(--bg)] rounded-[3px]">İptal</AlertDialogCancel>
                                                    <AlertDialogAction
                                                        onClick={handleDelete}
                                                        disabled={deleteReason.trim().length < 3}
                                                        className="bg-[#a8323b] hover:bg-[#a8323b]/90 text-white rounded-[3px] disabled:opacity-40 disabled:pointer-events-none"
                                                    >Sil</AlertDialogAction>
                                                </AlertDialogFooter>
                                            </AlertDialogContent>
                                        </AlertDialog>
                                    )}
                                </div>
                            </div>

                            {/* HISTORY SECTION (Only in Edit Mode) */}
                            {isEditMode && caseHistory.length > 0 && (
                                <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none overflow-hidden">
                                    <div className="bg-[var(--bg)] border-b border-[var(--border)] p-4">
                                        <h3 className="font-mono text-[10px] tracking-[0.22em] uppercase font-semibold text-[var(--brand)] flex items-center gap-2">
                                            <RefreshCw className="w-3 h-3" /> Değişiklik Geçmişi
                                        </h3>
                                    </div>
                                    <div className="p-4 max-h-[400px] overflow-auto">
                                        <div className="space-y-4">
                                            {caseHistory.map((h, i) => (
                                                <div key={i} className="text-xs border-l-2 border-primary/20 pl-3 py-1">
                                                    <div className="flex justify-between items-center mb-1">
                                                        <span className="font-bold text-primary">
                                                            {h.field === 'esas_no' ? 'Esas No Değişti' :
                                                                h.field === 'court' ? 'Mahkeme Değişti' :
                                                                    h.field === 'status' ? 'Durum Değişti' : h.field}
                                                        </span>
                                                        <span className="text-[10px] text-muted-foreground">
                                                            {new Date(h.date).toLocaleDateString('tr-TR')} {new Date(h.date).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}
                                                        </span>
                                                    </div>
                                                    <p className="text-muted-foreground line-through opacity-50">{h.old || '(Boş)'}</p>
                                                    <p className="font-medium">➔ {h.new}</p>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </Card>
                            )}
                        </div>
                    </div>
                </form>
                {/* Yeni Müvekkil Onay Modalı */}
                <AlertDialog open={showClientConfirm} onOpenChange={setShowClientConfirm}>
                    <AlertDialogContent>
                        <AlertDialogHeader>
                            <AlertDialogTitle>Yeni Müvekkil Kaydedilecek</AlertDialogTitle>
                            <AlertDialogDescription>
                                <strong>{pendingUnregistered.map(u => u.name).join(", ")}</strong> isimli müvekkiller sistemde bulunamadı. Dava oluşturulurken bu kişiler otomatik olarak sisteme yeni müvekkil olarak kaydedilecektir. Onaylıyor musunuz?
                            </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                            <AlertDialogCancel onClick={() => setShowClientConfirm(false)}>Vazgeç</AlertDialogCancel>
                            <AlertDialogAction onClick={() => handleSubmit(undefined, true)}>
                                Evet, Kaydet ve Davayı Aç
                            </AlertDialogAction>
                        </AlertDialogFooter>
                    </AlertDialogContent>
                </AlertDialog>
                {/* Zorunlu Alan Eksik Modalı — kaydı engellemez, uyarır */}
                <AlertDialog open={showMissingConfirm} onOpenChange={setShowMissingConfirm}>
                    <AlertDialogContent>
                        <AlertDialogHeader>
                            <AlertDialogTitle>Zorunlu Alanlar Eksik</AlertDialogTitle>
                            <AlertDialogDescription asChild>
                                <div>
                                    <p>Aşağıdaki zorunlu alanlar boş:</p>
                                    <ul className="list-disc pl-5 mt-2 space-y-0.5">
                                        {pendingMissing.map(m => (
                                            <li key={m.field} className="font-medium">{m.label}</li>
                                        ))}
                                    </ul>
                                    <p className="mt-3">
                                        Yine de kaydederseniz dosya <strong>DERDEST</strong> olarak açılır ve dava
                                        panelinde <strong>"eksik alan"</strong> uyarısıyla görünür; alanları sonradan
                                        tamamlayabilirsiniz.
                                    </p>
                                </div>
                            </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                            <AlertDialogCancel onClick={() => setShowMissingConfirm(false)}>Geri Dön ve Tamamla</AlertDialogCancel>
                            <AlertDialogAction onClick={() => {
                                missingAcknowledged.current = true;
                                setShowMissingConfirm(false);
                                handleSubmit(undefined, false);
                            }}>
                                Eksik Olarak Kaydet
                            </AlertDialogAction>
                        </AlertDialogFooter>
                    </AlertDialogContent>
                </AlertDialog>
                {/* Mükerrer Dava Uyarı Modalı */}
                <AlertDialog open={showDuplicateConfirm} onOpenChange={setShowDuplicateConfirm}>
                    <AlertDialogContent>
                        <AlertDialogHeader>
                            <AlertDialogTitle>Bu Esas No Zaten Kayıtlı Olabilir</AlertDialogTitle>
                            <AlertDialogDescription asChild>
                                <div>
                                    <p>Aynı esas numarasını taşıyan aktif kayıt(lar) bulundu:</p>
                                    <ul className="mt-2 space-y-1.5">
                                        {pendingDuplicates.map(d => (
                                            <li key={d.id} className="border border-[var(--border)] p-2 text-sm">
                                                <span className="font-mono font-semibold">{d.esas_no}</span>
                                                {" · "}{d.court || "Mahkeme belirtilmemiş"}
                                                {d.court_match && <span className="ml-1 text-red-500 font-semibold">(aynı mahkeme!)</span>}
                                                <span className="block text-muted-foreground font-mono text-xs mt-0.5">
                                                    {d.tracking_no} · {d.status}
                                                </span>
                                            </li>
                                        ))}
                                    </ul>
                                    <p className="mt-3">Bu dava daha önce açılmış olabilir. Yine de yeni kayıt açmak istiyor musunuz?</p>
                                </div>
                            </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                            <AlertDialogCancel onClick={() => setShowDuplicateConfirm(false)}>Vazgeç</AlertDialogCancel>
                            <AlertDialogAction onClick={() => {
                                duplicateAcknowledged.current = true;
                                setShowDuplicateConfirm(false);
                                handleSubmit(undefined, false);
                            }}>
                                Yine de Aç
                            </AlertDialogAction>
                        </AlertDialogFooter>
                    </AlertDialogContent>
                </AlertDialog>
            </main>
        </div >
    );
};

export default NewCase;
