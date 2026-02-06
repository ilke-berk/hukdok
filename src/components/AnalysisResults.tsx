import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Copy, Check, FileText, Calendar, User, FileCode, AlertCircle, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useState, useEffect, useMemo } from "react";
// import { toast } from "sonner"; // Use shadcn toast instead if useToast is used
import { useToast } from "@/components/ui/use-toast";
import { getApiUrl } from "@/lib/api";
import { useConfig } from "@/hooks/useConfig";


interface AnalysisData {
  tarih: string;
  belge_turu_kodu: string;
  muvekkil_kodu: string;
  // Make sure this matches backend/analyzer.py output EXACTLY
  muvekkil_adi?: string;
  muvekkiller?: string[];
  karsi_taraf?: string; // Yeni Alan
  belgede_gecen_isimler: string[];

  esas_no: string;
  avukat_kodu: string;
  durum: string;
  ofis_dosya_no: string;
  yedek1: string;
  yedek2: string;
  ozet: string;
  generated_filename: string;
  hash: string;
}

interface AnalysisResultsProps {
  data: AnalysisData;
  onValidationChange: (isValid: boolean, data: AnalysisData) => void;
}

// --- DYNAMIC TYPE DEFINITION ---
interface Lawyer {
  code: string;
  name: string;
}

interface StatusItem {
  code: string;
  name: string;
}

interface DocTypeItem {
  code: string;
  name: string;
}

export const AnalysisResults = ({
  data,
  onValidationChange,
}: AnalysisResultsProps) => {
  const { toast } = useToast();
  const [lawyerOptions, setLawyerOptions] = useState<Lawyer[]>([]);
  const [statusOptions, setStatusOptions] = useState<StatusItem[]>([]);
  const [docTypeOptions, setDocTypeOptions] = useState<DocTypeItem[]>([]);
  const [isLoadingLawyers, setIsLoadingLawyers] = useState(false);
  const [isLoadingStatuses, setIsLoadingStatuses] = useState(false);
  const [isLoadingDocTypes, setIsLoadingDocTypes] = useState(false);
  const [copied, setCopied] = useState(false);
  const [editedData, setEditedData] = useState(data);
  const [openDocType, setOpenDocType] = useState(false);
  const [openClientSelect, setOpenClientSelect] = useState(false);
  const [localClientList, setLocalClientList] = useState<string[]>(data.muvekkiller || []);

  const [approvedFields, setApprovedFields] = useState({
    tarih: false,
    belge_turu_kodu: false,
    muvekkil_kodu: false,
    esas_no: false,
    avukat_kodu: false,
    durum: false,
    ofis_dosya_no: true,
    yedek1: true,
    yedek2: true,
    karsi_taraf: false, // Yeni alan
  });

  const [openKarsiTarafSelect, setOpenKarsiTarafSelect] = useState(false);

  // Calculate if all required fields are approved
  const allFieldsApproved = Object.values(approvedFields).every((v) => v);

  // --- FETCH DYNAMIC LAWYERS & STATUSES ---

  const { lawyers: loadedLawyers, statuses: loadedStatuses, doctypes: loadedDocTypes, isLoading: isConfigLoading } = useConfig();

  useEffect(() => {
    if (!isConfigLoading) {
      setLawyerOptions(loadedLawyers);
      setStatusOptions(loadedStatuses);
      setDocTypeOptions(loadedDocTypes);
      console.log("Config loaded from hook:", { loadedLawyers, loadedStatuses, loadedDocTypes });
    }
  }, [loadedLawyers, loadedStatuses, loadedDocTypes, isConfigLoading]);

  // --- INITIAL DATA POPULATION ---
  // Sync editedData when new data prop arrives
  useEffect(() => {
    const normalizedData = { ...data };

    // Normalize Belge Turu (Pad with _ to 14 chars to match Select options)
    if (normalizedData.belge_turu_kodu) {
      let code = toEnglishUpper(normalizedData.belge_turu_kodu).trim();
      // Remove invalid chars just in case
      code = code.replace(/[^A-Z0-9_-]/g, '');
      if (code.length > 0 && code.length < 14) {
        code = code.padEnd(14, '_');
      } else if (code.length > 14) {
        code = code.substring(0, 14);
      }
      normalizedData.belge_turu_kodu = code;
    }

    setEditedData(normalizedData);
    setLocalClientList(normalizedData.muvekkiller || []);
    setApprovedFields({
      tarih: false,
      belge_turu_kodu: false,
      muvekkil_kodu: false,
      esas_no: false,
      avukat_kodu: false,
      durum: false,
      ofis_dosya_no: true,
      yedek1: true,
      yedek2: true,
      karsi_taraf: false,
    });
    setCopied(false);
    // Reset validation in parent
    onValidationChange(false, normalizedData);
  }, [data]);

  // Sync localClientList to editedData whenever it changes
  useEffect(() => {
    setEditedData(prev => ({ ...prev, muvekkiller: localClientList }));
  }, [localClientList]);



  // Helper: Turkish to English Uppercase (Defined early for use in effects and other functions)
  const toEnglishUpper = (str: string): string => {
    if (!str) return "";
    let result = str.toLocaleUpperCase('tr-TR');

    // Mapping for Turkish characters to English equivalents
    const mapping: Record<string, string> = {
      'Ç': 'C', 'Ğ': 'G', 'İ': 'I', 'I': 'I', 'Ö': 'O', 'Ş': 'S', 'Ü': 'U',
      'ç': 'C', 'ğ': 'G', 'ı': 'I', 'i': 'I', 'ö': 'O', 'ş': 'S', 'ü': 'U'
    };

    result = result.replace(/[ÇĞİIÖŞÜçğıöşü]/g, char => mapping[char] || char);
    return result;
  };

  // Müvekkil adını kurala uygun koda dönüştür
  const convertToMuvekkilKodu = (fullName: string): string => {
    // 1. Türkçe karakterleri İngilizce karşılıklarına çevir (toEnglishUpper kullanarak basitleştirildi)
    // Şirket ve İsim işleme mantığı korundu

    // 2. Şirket Göstergeleri
    const companyIndicators = [
      'A.Ş.', 'A.Ş', 'AŞ', 'A.S.', 'AS', 'LTD', 'LTD.', 'LİMİTED', 'LIMITED', 'ŞTİ', 'ŞTİ.', 'ŞİRKETİ', 'SIRKETI',
      'SİGORTA', 'SIGORTA', 'HOLDİNG', 'HOLDING', 'BANK', 'BANKA', 'BANKAS', 'GRUP', 'GROUP', 'CORP', 'INC', 'CO.',
      'SOMPO', 'NIPPON', 'AXA', 'QUICK', 'AKSIGORTA', 'ANADOLU', 'ALLIANZ', 'MAPFRE', 'HDI', 'ZURICH', 'ERGO'
    ];

    const upperName = toEnglishUpper(fullName); // Use centralized helper
    const isCompany = companyIndicators.some(indicator => upperName.includes(indicator));

    if (isCompany) {
      let cleanedName = upperName.trim(); // Already uppercase and English chars
      const insuranceCompanyMap: Record<string, string> = {
        'AXA': 'AXA-SIGORTA', 'AKSIGORTA': 'AKSIGORTA', 'ANADOLU': 'ANADOLU-SIGORT',
        'SOMPO': 'SOMPO-SIGORTA', 'NIPPON': 'NIPPON-SIGORTA', 'QUICK': 'QUICK-SIGORTA',
        'ALLIANZ': 'ALLIANZ-SIGORT', 'MAPFRE': 'MAPFRE-SIGORT', 'HDI': 'HDI-SIGORTA',
        'ZURICH': 'ZURICH-SIGORT', 'ERGO': 'ERGO-SIGORTA',
      };

      for (const [key, formattedName] of Object.entries(insuranceCompanyMap)) {
        if (cleanedName.includes(key)) {
          // formattedName keys are already safe, but safety check
          const converted = toEnglishUpper(formattedName);
          if (converted.length >= 14) return converted.substring(0, 14);
          else return converted.padEnd(14, '-');
        }
      }

      cleanedName = cleanedName.replace(/[.,;:'"!?()[\]{}]/g, '').replace(/\s+/g, '-');
      const converted = toEnglishUpper(cleanedName); // Redundant if already done but safe
      if (converted.length >= 14) return converted.substring(0, 14);
      else return converted.padEnd(14, '-');
    }

    // 3. Şahıs İsmi İşleme
    let cleanedName = fullName;
    const titlesToRemove = [
      'PROF.', 'PROF', 'PROFESÖR', 'PROFESSOR', 'DR.', 'DR', 'DOKTOR', 'DOCTOR', 'UZMAN DR.', 'UZMAN DR', 'UZMAN',
      'MİMAR', 'MIMAR', 'MÜHENDİS', 'MUHENDIS', 'AV.', 'AV', 'AVUKAT', 'PHD', 'PH.D', 'BSC', 'MSC', 'MBA'
    ];
    let upperClean = toEnglishUpper(cleanedName);
    for (const title of titlesToRemove) {
      upperClean = upperClean.replace(new RegExp(`\\b${title}\\b`, 'g'), '');
    }

    cleanedName = upperClean.replace(/[.,;:'"!?()[\]{}]/g, '').trim();
    const parts = cleanedName.split(/\s+/).filter(p => p.length > 0);

    if (parts.length === 0) return 'XXXXXXXXXXXXXX';

    let result = '';
    if (parts.length === 1) {
      // Tek Kelime
      result = toEnglishUpper(parts[0]);
    } else {
      // Ad Soyad (Format: A_SOYAD - güvenli dosya adı için)
      const initial = toEnglishUpper(parts[0].charAt(0));
      const surname = toEnglishUpper(parts[parts.length - 1]);
      result = `${initial}_${surname}`;
    }

    // 4. Uzunluk ve Padding (14 Karakter Sabit)
    if (result.length > 14) {
      return result.substring(0, 14);
    } else {
      return result.padEnd(14, '_');
    }
  };

  const parseDateToYYMMDD = (dateInput: string): string => {
    const input = dateInput.trim().toLowerCase();
    if (!input || input.length === 0) return 'XXXXXX';
    const months: Record<string, string> = {
      ocak: "01", oca: "01", şubat: "02", şub: "02", mart: "03", mar: "03", nisan: "04", nis: "04",
      mayıs: "05", may: "05", haziran: "06", haz: "06", temmuz: "07", tem: "07", ağustos: "08", agu: "08",
      eylül: "09", eyl: "09", ekim: "10", eki: "10", kasım: "11", kas: "11", aralık: "12", ara: "12",
    };
    const formatYear = (y: string) => y.length === 4 ? y.slice(-2) : y.padStart(2, "0");
    const hyphenMatch = input.match(/^(\d{4}|\d{1,2})[-/](\d{1,2})[-/](\d{4}|\d{1,2})$/);
    if (hyphenMatch) {
      let d, m, y;
      if (hyphenMatch[1].length === 4) { y = hyphenMatch[1]; m = hyphenMatch[2]; d = hyphenMatch[3]; }
      else { d = hyphenMatch[1]; m = hyphenMatch[2]; y = hyphenMatch[3]; }
      return `${formatYear(y)}${m.padStart(2, "0")}${d.padStart(2, "0")}`;
    }
    const dotMatch = input.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})$/);
    if (dotMatch) {
      const d = dotMatch[1].padStart(2, "0"); const m = dotMatch[2].padStart(2, "0"); const y = formatYear(dotMatch[3]);
      return `${y}${m}${d}`;
    }
    const textMatch = input.match(/^(\d{1,2})\s+([a-zçğıöşü]+)\s+(\d{4}|\d{2})$/);
    if (textMatch) {
      const d = textMatch[1].padStart(2, "0"); const m = months[textMatch[2]] || "00"; const y = formatYear(textMatch[3]);
      if (m !== "00") return `${y}${m}${d}`;
    }
    if (/^\d{6}$/.test(input)) return input.toUpperCase();
    return 'XXXXXX';
  };

  const generateFilename = () => {
    const hash6 = toEnglishUpper((approvedFields.ofis_dosya_no ? editedData.hash : data.hash)).substring(0, 6);
    const parts = [
      approvedFields.tarih ? editedData.tarih : data.tarih,
      approvedFields.belge_turu_kodu ? editedData.belge_turu_kodu : toEnglishUpper(data.belge_turu_kodu),
      // MÜVEKKİL KODU İŞLEME
      (() => {
        let baseCode = approvedFields.muvekkil_kodu ? editedData.muvekkil_kodu : data.muvekkil_kodu;

        // Her zaman formatla - tire/boşlukları düzelt
        if (baseCode && baseCode.includes('-')) {
          // HASAN-HAZAR formatını H_HAZAR formatına çevir
          const cleanedName = baseCode.replace(/-+/g, ' ').replace(/_+/g, ' ').trim();
          baseCode = convertToMuvekkilKodu(cleanedName);
        }

        // localClientList kullan (kullanıcının seçtiği müvekkiller)
        const count = localClientList.length;

        // Müvekkil sayısını 14 karakterden SONRA ayrı segment olarak ekle
        // baseCode zaten convertToMuvekkilKodu tarafından veya toEnglishUpper tarafından işlenmeli
        // Eğer data'dan geliyorsa ve hyphen yoksa raw gelebilir, onu sanitize edelim
        if (!approvedFields.muvekkil_kodu && !baseCode.includes('_')) { // Basit kontrol, daha sağlamı:
          if (!baseCode.includes('-') && !baseCode.includes('_') && /[ÇĞİIÖŞÜçğıöşü]/.test(baseCode)) {
            baseCode = toEnglishUpper(baseCode);
          }
        }

        return `${baseCode}_${count > 0 ? count : 1}`;
      })(),
      // ESAS NO: Dosya adı için YY-NNNNN formatı (metadata'da orijinal kalır)
      (() => {
        const esasNo = approvedFields.esas_no ? editedData.esas_no : data.esas_no;
        if (!esasNo) return esasNo;

        // 2024/12345 veya 2024-12345 formatını parse et
        const match = esasNo.match(/(\d{2,4})[\/\-](\d+)/);
        if (match) {
          const year = match[1].slice(-2); // Son 2 hane (2024 → 24)
          const number = match[2].padStart(5, '0'); // 5 hane (12 → 00012)
          return `${year}-${number}`;
        }
        return toEnglishUpper(esasNo).replace(/\//g, '-'); // Fallback sanitize
      })(),
      toEnglishUpper(approvedFields.avukat_kodu ? editedData.avukat_kodu : data.avukat_kodu),
      toEnglishUpper(approvedFields.durum ? editedData.durum : data.durum),
      toEnglishUpper(approvedFields.ofis_dosya_no ? editedData.ofis_dosya_no : data.ofis_dosya_no),
      toEnglishUpper(approvedFields.yedek1 ? editedData.yedek1 : data.yedek1),
      toEnglishUpper(approvedFields.yedek2 ? editedData.yedek2 : data.yedek2),
      hash6,
    ];
    return parts.join("_");
  };

  const generatedFilename = generateFilename();

  useEffect(() => {
    const isAllApproved = Object.values(approvedFields).every((v) => v);
    onValidationChange(isAllApproved, { ...editedData, generated_filename: generatedFilename });
  }, [editedData, approvedFields, onValidationChange, generatedFilename]);

  const handleCopy = () => {
    if (!allFieldsApproved) {
      toast({ variant: "destructive", title: "Hata", description: "Lütfen tüm alanları onaylayın", });
      return;
    }
    if (generatedFilename.length !== 77) {
      toast({ variant: "destructive", title: "Hata", description: "Dosya adı 77 karakter olmalı", });
      return;
    }
    navigator.clipboard.writeText(generatedFilename);
    setCopied(true);
    toast({ title: "Başarılı", description: "Dosya adı kopyalandı", });
    setTimeout(() => setCopied(false), 2000);
  };

  const handleFieldChange = (field: keyof typeof editedData, value: string) => {
    setEditedData((prev) => ({ ...prev, [field]: value }));
  };

  const handleFieldApproval = (field: keyof typeof approvedFields, checked: boolean) => {
    if (checked) {
      let formattedValue = editedData[field as keyof typeof editedData] as string;
      if (field === "tarih") {
        formattedValue = parseDateToYYMMDD(formattedValue);
      } else if (field === "belge_turu_kodu") {
        formattedValue = toEnglishUpper(formattedValue);
        formattedValue = formattedValue.replace(/[^A-Z0-9_-]/g, '').substring(0, 14);
        if (formattedValue.length < 14) formattedValue = formattedValue.padEnd(14, '_');
      } else if (field === "muvekkil_kodu") {
        // Her zaman convertToMuvekkilKodu uygula (A_SOYAD formatı için)
        // İsim içeriyorsa formatla, değilse padding uygula
        const hasLetters = /[A-Za-zÇĞİÖŞÜçğıöşü]/.test(formattedValue);
        if (hasLetters && formattedValue.length > 0) {
          // İsim veya kod - tire/boşlukları parse et ve formatla
          const cleanedName = formattedValue.replace(/-+/g, ' ').replace(/_+/g, ' ').trim();
          formattedValue = convertToMuvekkilKodu(cleanedName);
        } else {
          formattedValue = toEnglishUpper(formattedValue);
          if (formattedValue.length >= 14) formattedValue = formattedValue.substring(0, 14);
          else if (formattedValue.length === 0) formattedValue = '______________';
          else formattedValue = formattedValue.padEnd(14, '_');
        }
      } else if (field === "esas_no") {
        formattedValue = toEnglishUpper(formattedValue);
        // Allow YYYY/NNNN or YYYY-NNNN
        const match = formattedValue.match(/(\d{4})[\/\-\s]*(\d+)/);
        if (match) {
          const year = match[1];
          const number = match[2];
          // Standard Format: YYYY/NNNN (No padding for number, standard slash)
          formattedValue = `${year}/${number}`;
        } else {
          // Fallback for short years or other formats
          const shortMatch = formattedValue.match(/(\d{2})[\/\-\s]*(\d+)/);
          if (shortMatch) {
            const year = "20" + shortMatch[1];
            const number = shortMatch[2];
            formattedValue = `${year}/${number}`;
          } else {
            formattedValue = formattedValue.length === 0 ? '--------' : formattedValue;
          }
        }
      } else if (field === "ofis_dosya_no") {
        formattedValue = toEnglishUpper(formattedValue);
        if (formattedValue.length >= 9) formattedValue = formattedValue.substring(0, 9);
        else formattedValue = formattedValue.length === 0 ? 'XXXXXXXXX' : formattedValue.padEnd(9, 'X');
      } else if (field === "avukat_kodu") {
        formattedValue = toEnglishUpper(formattedValue);
        if (formattedValue.length === 0) formattedValue = 'XXX';
        else if (formattedValue.length >= 3) formattedValue = formattedValue.substring(0, 3);
        else formattedValue = formattedValue.padEnd(3, 'X');
      } else if (field === "durum") {
        formattedValue = toEnglishUpper(formattedValue);
        formattedValue = formattedValue.length === 0 ? 'X' : formattedValue.substring(0, 1);
      } else if (field === "yedek1") {
        formattedValue = toEnglishUpper(formattedValue);
        formattedValue = formattedValue.length === 0 ? '-' : formattedValue.substring(0, 1);
      } else if (field === "yedek2") {
        formattedValue = toEnglishUpper(formattedValue);
        formattedValue = formattedValue.length === 0 ? '--' : (formattedValue.length >= 2 ? formattedValue.substring(0, 2) : formattedValue.padEnd(2, '-'));
      } else {
        formattedValue = toEnglishUpper(formattedValue);
      }
      setEditedData((prev) => ({ ...prev, [field]: formattedValue }));
    }
    setApprovedFields((prev) => ({ ...prev, [field]: checked }));
  };

  return (
    <Card className="glass-card animate-fade-in overflow-hidden">
      <CardHeader className="glass-header rounded-t-xl pb-4">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-xl text-primary-foreground drop-shadow">
            <FileCode className="w-5 h-5" />
            Önerilen Dosya Adı
          </CardTitle>
          <Badge
            variant={generatedFilename.length === 75 ? "default" : "secondary"}
            className={generatedFilename.length === 75 ? "bg-success/90 text-success-foreground glow-success" : "bg-muted text-muted-foreground"}
          >
            UZUNLUK {generatedFilename.length} / 75
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-6 space-y-6">
        <p className="text-sm text-muted-foreground">Aşağıdaki verileri kontrol edin ve onaylayın. Tüm alanlar onaylandığında işleme devam edebilirsiniz.</p>
        <div className="glass-input rounded-xl p-4">
          <div className="flex items-center gap-3">
            <code className="text-sm font-mono text-foreground flex-1 break-all">{generatedFilename}</code>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Calendar className="w-3 h-3" /> [A] TARİH
            </Label>
            <div className="relative flex items-center gap-2">
              <Input
                value={editedData.tarih}
                onChange={(e) => handleFieldChange("tarih", e.target.value)}
                className="font-mono glass-input pr-10" maxLength={30} disabled={approvedFields.tarih}
              />
              <Checkbox checked={approvedFields.tarih} onCheckedChange={(checked) => handleFieldApproval("tarih", checked as boolean)} className={approvedFields.tarih ? "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success" : ""} />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="flex items-center gap-2 text-xs text-muted-foreground">
              <User className="w-3 h-3" /> [B] MÜVEKKİL/İLGİLİ
              {(localClientList.length > 1) && (
                <Badge variant="outline" className="h-5 px-1.5 text-[0.65rem] border-primary/30 text-primary bg-primary/5">
                  +{localClientList.length - 1} DİĞER
                </Badge>
              )}
            </Label>
            <div className="relative flex items-center gap-2">
              <Input
                value={editedData.muvekkil_kodu || ""}
                onChange={(e) => handleFieldChange("muvekkil_kodu", e.target.value)}
                className="font-mono glass-input flex-1"
                maxLength={30}
                placeholder="Müvekkil Adı"
                disabled={approvedFields.muvekkil_kodu}
              />

              {/* ADVANCED MULTI-CLIENT SELECTION POPOVER */}
              <Popover open={openClientSelect} onOpenChange={setOpenClientSelect}>
                <PopoverTrigger asChild>
                  <Button variant="outline" role="combobox" aria-expanded={openClientSelect} disabled={approvedFields.muvekkil_kodu} className="w-[40px] px-0 font-mono glass-input h-10">
                    <ChevronsUpDown className="h-4 w-4 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[350px] p-0 glass z-[100]" align="end">
                  <Command>
                    <CommandInput placeholder="İsim ara..." />
                    <CommandList className="max-h-[300px] overflow-y-auto">
                      <CommandEmpty>İsim bulunamadı.</CommandEmpty>
                      <CommandGroup heading="ÖNERİLENLER">
                        {/* Sistem + Manuel eklenen tüm müvekkilleri göster */}
                        {(() => {
                          // Tüm müvekkilleri birleştir (sistem + manuel)
                          const systemClients = data.muvekkiller || [];
                          const allClients = [...new Set([...localClientList, ...systemClients])];

                          return allClients.map((name, idx) => {
                            const isSelected = localClientList.includes(name);
                            const isPrimary = (name === editedData.muvekkil_kodu);
                            const isManuallyAdded = !systemClients.includes(name);

                            return (
                              <CommandItem key={`rec-${idx}`} value={name} className="flex items-center gap-2 px-2 py-1.5 cursor-pointer rounded-sm" onSelect={() => { }}>
                                <div className="flex items-center h-full p-1" onClick={(e) => {
                                  e.stopPropagation();
                                  let newList = [...localClientList];
                                  if (isSelected) newList = newList.filter(n => n !== name);
                                  else newList.push(name);
                                  setLocalClientList(newList);

                                  // Eğer ana müvekkil kaldırıldıysa, temizle
                                  if (isSelected && isPrimary) {
                                    handleFieldChange("muvekkil_kodu", "");
                                  }
                                }}>
                                  <Checkbox checked={isSelected} className="translate-y-[1px]" />
                                </div>
                                <div className="flex-1 text-xs font-mono truncate select-none flex items-center justify-between"
                                  onClick={() => {
                                    if (!isSelected) {
                                      toast({ title: "İşlem Engellendi", description: "Bu kişiyi Ana Müvekkil yapabilmek için önce solundaki kutucuğu işaretleyerek listeye eklemelisiniz.", variant: "destructive" });
                                      return;
                                    }
                                    const formattedCode = convertToMuvekkilKodu(name);
                                    handleFieldChange("muvekkil_kodu", formattedCode);
                                    setOpenClientSelect(false);
                                    toast({ title: "Ana Müvekkil Seçildi", description: name });
                                  }}
                                >
                                  <span className={cn("font-medium", isSelected ? "text-primary" : "text-muted-foreground", isPrimary && "font-bold text-primary")}>
                                    {name}
                                  </span>
                                  <div className="flex items-center gap-1">
                                    {isManuallyAdded && <Badge variant="outline" className="text-[0.55rem] h-3.5 px-1 bg-amber-500/10 text-amber-600 border-amber-500/30">MANUEL</Badge>}
                                    {isPrimary && <Badge variant="default" className="text-[0.6rem] h-4 px-1">ANA</Badge>}
                                  </div>
                                </div>
                              </CommandItem>
                            );
                          });
                        })()}
                      </CommandGroup>

                      <CommandGroup heading="DİĞER İSİMLER">
                        {(() => {
                          const detectedSet = new Set(data.muvekkiller || []);
                          // Create a set of lawyer names/codes for filtering
                          const lawyerSet = new Set(lawyerOptions.map(l => l.name.toUpperCase()));
                          // Also add lawyer codes just in case
                          lawyerOptions.forEach(l => lawyerSet.add(l.code.toUpperCase()));

                          const otherNames = (editedData.belgede_gecen_isimler || [])
                            .filter(name => {
                              const upper = name.trim().toUpperCase();
                              return upper.length > 0 &&
                                !detectedSet.has(name) &&
                                !lawyerSet.has(upper) &&
                                !upper.includes("AVUKAT") && !upper.includes("AV.") &&
                                !upper.includes("VEKİLİ");
                            });

                          if (otherNames.length === 0) return <CommandItem value="NO_OTHER_NAMES" disabled className="text-xs text-muted-foreground">Başka isim bulunamadı.</CommandItem>;

                          return otherNames.map((name, idx) => {
                            const isSelected = localClientList.includes(name);
                            const isPrimary = (name === editedData.muvekkil_kodu);
                            return (
                              <CommandItem key={`other-${idx}`} value={name} className="flex items-center gap-2 px-2 py-1.5 cursor-pointer rounded-sm" onSelect={() => { }}>
                                <div className="flex items-center h-full p-1" onClick={(e) => {
                                  e.stopPropagation();
                                  let newList = [...localClientList];
                                  if (isSelected) newList = newList.filter(n => n !== name);
                                  else newList.push(name);
                                  setLocalClientList(newList);
                                }}>
                                  <Checkbox checked={isSelected} className="translate-y-[1px]" />
                                </div>
                                <div className="flex-1 text-xs font-mono truncate select-none flex items-center justify-between"
                                  onClick={() => {
                                    const formattedCode = convertToMuvekkilKodu(name);
                                    handleFieldChange("muvekkil_kodu", formattedCode);
                                    if (!isSelected) setLocalClientList(prev => [...prev, name]);
                                    setOpenClientSelect(false);
                                    toast({ title: "Ana Müvekkil Seçildi", description: name });
                                  }}
                                >
                                  <span className={cn(isSelected ? "text-foreground" : "text-muted-foreground", isPrimary && "font-bold text-primary")}>
                                    {name}
                                  </span>
                                  {isPrimary && <Badge variant="default" className="text-[0.6rem] h-4 px-1 ml-2">ANA</Badge>}
                                </div>
                              </CommandItem>
                            );
                          });
                        })()}
                      </CommandGroup>

                      {/* YENİ MÜVEKKİL EKLE */}
                      <div className="border-t border-border/30 p-2">
                        <p className="text-xs text-muted-foreground mb-2 px-2">💡 Listede yoksa manuel yazın:</p>
                        <div className="flex gap-2 px-2">
                          <Input
                            placeholder="Yeni müvekkil adı..."
                            className="h-8 text-xs"
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                const value = (e.target as HTMLInputElement).value.trim();
                                if (value) {
                                  const formattedCode = convertToMuvekkilKodu(value);
                                  handleFieldChange("muvekkil_kodu", formattedCode);
                                  if (!localClientList.includes(value)) {
                                    setLocalClientList(prev => [...prev, value]);
                                  }
                                  setOpenClientSelect(false);
                                  toast({ title: "Müvekkil Eklendi", description: value });
                                }
                              }
                            }}
                          />
                        </div>
                      </div>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>

              <Checkbox checked={approvedFields.muvekkil_kodu} onCheckedChange={(checked) => handleFieldApproval("muvekkil_kodu", checked as boolean)} className={approvedFields.muvekkil_kodu ? "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success" : ""} />
            </div>
          </div>

          <div className="col-span-2 space-y-2">
            <Label className="flex items-center gap-2 text-xs text-muted-foreground"><User className="w-3 h-3" /> [VS] KARŞI TARAF / MUHATAP</Label>
            <div className="relative flex items-center gap-2">
              <Popover open={openKarsiTarafSelect} onOpenChange={setOpenKarsiTarafSelect}>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={openKarsiTarafSelect}
                    disabled={approvedFields.karsi_taraf}
                    className="w-full justify-between font-mono glass-input h-auto min-h-[40px] px-3 py-2 text-sm whitespace-normal text-left"
                  >
                    <span className="line-clamp-2">
                      {editedData.karsi_taraf || "Karşı Taraf Seçin..."}
                    </span>
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[350px] p-0 glass z-[100]" align="end">
                  <Command>
                    <CommandInput placeholder="İsim ara..." />
                    <CommandList className="max-h-[300px] overflow-y-auto">
                      <CommandEmpty>İsim bulunamadı.</CommandEmpty>
                      <CommandGroup heading="DİĞER İSİMLER (ÖNERİLER)">
                        {(() => {
                          const excludeSet = new Set(localClientList);
                          if (editedData.muvekkil_kodu) excludeSet.add(editedData.muvekkil_kodu);

                          // Avukatları da çıkar
                          const lawyerSet = new Set(lawyerOptions.map(l => l.name.toUpperCase()));

                          const candidates = (editedData.belgede_gecen_isimler || [])
                            .filter(name => {
                              const upper = name.toUpperCase().trim();
                              return !excludeSet.has(name) && !lawyerSet.has(upper) && upper.length > 2;
                            });

                          // Mevcut seçili listeyi parse et (Daha esnek split: virgül veya noktalı virgül)
                          const currentSelection = editedData.karsi_taraf
                            ? editedData.karsi_taraf.split(/[,;]+/).map(s => s.trim()).filter(Boolean)
                            : [];

                          if (candidates.length === 0) return <CommandItem disabled>Öneri yok</CommandItem>;

                          return candidates.map((name, idx) => {
                            const isSelected = currentSelection.includes(name);
                            return (
                              <CommandItem
                                key={`kt-${idx}`}
                                value={name}
                                className="flex items-center gap-2 cursor-pointer"
                                onSelect={() => {
                                  // Toggle logic (Select/Deselect)
                                  let newSelection = [...currentSelection];
                                  if (isSelected) {
                                    newSelection = newSelection.filter(s => s !== name);
                                  } else {
                                    newSelection.push(name);
                                  }

                                  const newString = newSelection.join(', ');
                                  handleFieldChange("karsi_taraf", newString);
                                  // Don't close popover to allow multiple selections
                                }}
                              >
                                <div className="flex items-center h-full p-1" onClick={(e) => e.stopPropagation()}>
                                  <Checkbox
                                    checked={isSelected}
                                    onCheckedChange={() => {
                                      // Toggle logic for Checkbox click
                                      let newSelection = [...currentSelection];
                                      if (isSelected) {
                                        newSelection = newSelection.filter(s => s !== name);
                                      } else {
                                        newSelection.push(name);
                                      }
                                      const newString = newSelection.join(', ');
                                      handleFieldChange("karsi_taraf", newString);
                                    }}
                                  />
                                </div>
                                {name}
                              </CommandItem>
                            );
                          });
                        })()}
                      </CommandGroup>
                      {/* Üstte Hızlı Temizle Butonu (Grup olarak) */}
                      <CommandGroup>
                        <CommandItem
                          value="CLEAR_ALL"
                          className="text-destructive font-bold justify-center cursor-pointer bg-destructive/10 hover:bg-destructive/20"
                          onSelect={() => {
                            handleFieldChange("karsi_taraf", "");
                            toast({ title: "Temizlendi", description: "Karşı taraf listesi sıfırlandı." });
                          }}
                        >
                          🗑️ LİSTEYİ TEMİZLE
                        </CommandItem>
                      </CommandGroup>

                      <div className="border-t border-border/30 p-2">
                        <p className="text-xs text-muted-foreground mb-2 px-2">💡 Listede yoksa manuel yazın (Enter ile ekle):</p>
                        <div className="flex gap-2 px-2">
                          <Input
                            placeholder="Yeni isim..."
                            className="h-8 text-xs"
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                const value = (e.target as HTMLInputElement).value.trim();
                                if (value) {
                                  const currentSelection = editedData.karsi_taraf
                                    ? editedData.karsi_taraf.split(/[,;]+/).map(s => s.trim()).filter(Boolean)
                                    : [];

                                  if (!currentSelection.includes(value)) {
                                    const newString = [...currentSelection, value].join(', ');
                                    handleFieldChange("karsi_taraf", newString);
                                    toast({ title: "Eklendi", description: value });
                                    (e.target as HTMLInputElement).value = ""; // Clear input
                                  }
                                }
                              }
                            }}
                          />
                        </div>
                      </div>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
              <Checkbox
                checked={approvedFields.karsi_taraf}
                onCheckedChange={(checked) => handleFieldApproval("karsi_taraf", checked as boolean)}
                className={approvedFields.karsi_taraf ? "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success" : ""}
              />
            </div>
          </div>

          <div className="col-span-2 space-y-2">
            <Label className="flex items-center gap-2 text-xs text-muted-foreground"><FileText className="w-3 h-3" /> [C] BELGE TÜRÜ</Label>
            <div className="relative flex items-center gap-2">
              <Popover open={openDocType} onOpenChange={setOpenDocType}>
                <PopoverTrigger asChild>
                  <Button variant="outline" role="combobox" aria-expanded={openDocType} disabled={approvedFields.belge_turu_kodu} className="w-full justify-between font-mono glass-input h-10 px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50">
                    <span className="truncate">
                      {editedData.belge_turu_kodu
                        ? docTypeOptions.find((item) => item.code === editedData.belge_turu_kodu)
                          ? `${docTypeOptions.find((item) => item.code === editedData.belge_turu_kodu)?.code} - ${docTypeOptions.find((item) => item.code === editedData.belge_turu_kodu)?.name}`
                          : editedData.belge_turu_kodu
                        : "Belge türü seçin..."}
                    </span>
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[400px] p-0 glass z-[50]" align="start">
                  <Command className="w-full">
                    <CommandInput placeholder="Belge türü ara (Kod veya İsim)..." />
                    <CommandList className="max-h-[300px] overflow-y-auto">
                      <CommandEmpty>Belge türü bulunamadı.</CommandEmpty>
                      <CommandGroup>
                        {docTypeOptions.map((item) => (
                          <CommandItem key={item.code} value={`${item.code} ${item.name}`} onSelect={() => { handleFieldChange("belge_turu_kodu", item.code); setOpenDocType(false); }}>
                            <Check className={cn("mr-2 h-4 w-4", editedData.belge_turu_kodu === item.code ? "opacity-100" : "opacity-0")} />
                            {item.code} - {item.name}
                          </CommandItem>
                        ))}
                        <CommandItem key="HICBIRI" value="HICBIRI_______ Hiçbiri" onSelect={() => { handleFieldChange("belge_turu_kodu", "HICBIRI_______"); setOpenDocType(false); }}>
                          <Check className={cn("mr-2 h-4 w-4", editedData.belge_turu_kodu === "HICBIRI_______" ? "opacity-100" : "opacity-0")} />
                          HICBIRI_______ - Hiçbiri (Tanımsız)
                        </CommandItem>
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
              <Checkbox checked={approvedFields.belge_turu_kodu} onCheckedChange={(checked) => handleFieldApproval("belge_turu_kodu", checked as boolean)} className={approvedFields.belge_turu_kodu ? "data-[state=checked]:bg-success data-[state=checked]:border-success" : ""} />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="flex items-center gap-2 text-xs text-muted-foreground"><User className="w-3 h-3" /> [D] AVUKAT</Label>
            <div className="relative flex items-center gap-2">
              <Select value={editedData.avukat_kodu} onValueChange={(value) => handleFieldChange("avukat_kodu", value)} disabled={approvedFields.avukat_kodu}>
                <SelectTrigger className="font-mono glass-input"><SelectValue placeholder="Avukat seçin" /></SelectTrigger>
                <SelectContent className="max-h-[300px] glass z-50">
                  {isLoadingLawyers ? (<SelectItem value="LOADING" disabled>Yükleniyor...</SelectItem>) : (lawyerOptions.map((lawyer) => (<SelectItem key={lawyer.code} value={lawyer.code}>{lawyer.code} – {lawyer.name}</SelectItem>)))}
                  {!isLoadingLawyers && lawyerOptions.length === 0 && (<SelectItem value="ERROR" disabled>Liste Yüklenemedi</SelectItem>)}
                  <SelectItem value="XXX">XXX – Herhangi bir Avukat tespit edilemedi</SelectItem>
                </SelectContent>
              </Select>
              <Checkbox checked={approvedFields.avukat_kodu} onCheckedChange={(checked) => handleFieldApproval("avukat_kodu", checked as boolean)} className={approvedFields.avukat_kodu ? "data-[state=checked]:bg-success data-[state=checked]:border-success" : ""} />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">[E] DURUM</Label>
            <div className="relative flex items-center gap-2">
              <Select value={editedData.durum} onValueChange={(value) => handleFieldChange("durum", value)} disabled={approvedFields.durum}>
                <SelectTrigger className="font-mono glass-input"><SelectValue placeholder="Durum seçin" /></SelectTrigger>
                <SelectContent className="max-h-[300px] glass z-50">
                  {isLoadingStatuses ? (<SelectItem value="LOADING" disabled>Yükleniyor...</SelectItem>) : (statusOptions.length > 0 ? (statusOptions.map((status) => (<SelectItem key={status.code} value={status.code}>{status.code} – {status.name}</SelectItem>))) : (<><SelectItem value="G">G – Gelen belge (Varsayılan)</SelectItem><SelectItem value="F">F – Final (gönderilecek) Belge</SelectItem><SelectItem value="C">C – Çalışma yapılacak Belge</SelectItem><SelectItem value="X">X – Mahrem Bilgi Notu</SelectItem><SelectItem value="B">B – Büro içi kalacak Not</SelectItem></>))}
                </SelectContent>
              </Select>
              <Checkbox checked={approvedFields.durum} onCheckedChange={(checked) => handleFieldApproval("durum", checked as boolean)} className={approvedFields.durum ? "data-[state=checked]:bg-success data-[state=checked]:border-success" : ""} />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">[Ö] ÖZEL NO (SİSTEM)</Label>
            <div className="relative flex items-center gap-2">
              <Input
                value={editedData.ofis_dosya_no}
                readOnly
                className="font-mono glass-input bg-muted/50 text-muted-foreground cursor-not-allowed"
                title="Bu alan sistem tarafından otomatik verilir"
              />
              <Checkbox
                checked={true}
                disabled
                className="data-[state=checked]:bg-muted data-[state=checked]:text-muted-foreground opacity-50"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">[F] ESAS NO</Label>
            <div className="relative flex items-center gap-2">
              <Input value={editedData.esas_no} onChange={(e) => handleFieldChange("esas_no", e.target.value)} className="font-mono glass-input pr-10" maxLength={30} disabled={approvedFields.esas_no} />
              <Checkbox checked={approvedFields.esas_no} onCheckedChange={(checked) => handleFieldApproval("esas_no", checked as boolean)} className={approvedFields.esas_no ? "data-[state=checked]:bg-success data-[state=checked]:border-success glow-success" : ""} />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">[G] YEDEK1</Label>
            <div className="relative flex items-center gap-2">
              <Input value={editedData.yedek1} onChange={(e) => handleFieldChange("yedek1", e.target.value)} placeholder="1 Karakter" className="font-mono glass-input pr-10" maxLength={1} disabled={approvedFields.yedek1} />
              <Checkbox checked={approvedFields.yedek1} onCheckedChange={(checked) => handleFieldApproval("yedek1", checked as boolean)} className={approvedFields.yedek1 ? "data-[state=checked]:bg-success data-[state=checked]:border-success" : ""} />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">[H] YEDEK2</Label>
            <div className="relative flex items-center gap-2">
              <Input value={editedData.yedek2} onChange={(e) => handleFieldChange("yedek2", e.target.value)} placeholder="2 Karakter" className="font-mono glass-input pr-10" maxLength={2} disabled={approvedFields.yedek2} />
              <Checkbox checked={approvedFields.yedek2} onCheckedChange={(checked) => handleFieldApproval("yedek2", checked as boolean)} className={approvedFields.yedek2 ? "data-[state=checked]:bg-success data-[state=checked]:border-success" : ""} />
            </div>
          </div>
        </div>

        <div className="space-y-2 pt-4 border-t border-border/30">
          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">[K] DOSYA İMZASI (SHA256 ilk 6 karakter)</Label>
            <Badge variant="secondary" className="font-mono text-xs glass">{data.hash.substring(0, 6).toUpperCase()}</Badge>
          </div>
          <code className="block text-xs font-mono text-muted-foreground glass-input p-3 rounded-lg break-all">Tam Hash: {data.hash}</code>
        </div>
      </CardContent>
    </Card>
  );
};
