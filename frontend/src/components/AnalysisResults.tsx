import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Check, FileText, Calendar, User, FileCode, ChevronsUpDown } from "lucide-react";
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
import { useState, useEffect } from "react";
import { useToast } from "@/components/ui/use-toast";
import { useConfig } from "@/hooks/useConfig";

interface AnalysisData {
  tarih: string;
  belge_turu_kodu: string;
  muvekkil_kodu: string;
  muvekkil_adi?: string;
  muvekkiller?: string[];
  karsi_taraf?: string;
  belgede_gecen_isimler: string[];
  esas_no: string;
  durum: string;
  ofis_dosya_no: string;
  yedek1: string;
  yedek2: string;
  ozet: string;
  generated_filename: string;
  hash: string;
  court?: string;
  city?: string;
  merci?: string;
}

interface LinkedCaseData {
  esas_no?: string;
  client_parties?: string[];
  muvekkil_adi?: string;
  karsi_taraf?: string | string[];
  court?: string;
  parties?: { party_type: string; name: string }[];
  [key: string]: unknown;
}

interface AnalysisResultsProps {
  data: AnalysisData;
  onValidationChange: (isValid: boolean, data: AnalysisData) => void;
  linkedCase?: LinkedCaseData | null;
}

interface Lawyer {
  code?: string;
  name: string;
}

interface DocTypeItem {
  code?: string;
  name: string;
}

export const AnalysisResults = ({
  data,
  onValidationChange,
  linkedCase,
}: AnalysisResultsProps) => {
  const { toast } = useToast();
  const [lawyerOptions, setLawyerOptions] = useState<Lawyer[]>([]);
  const [docTypeOptions, setDocTypeOptions] = useState<DocTypeItem[]>([]);
  const [editedData, setEditedData] = useState(data);
  const [openDocType, setOpenDocType] = useState(false);
  const [openClientSelect, setOpenClientSelect] = useState(false);
  const [localClientList, setLocalClientList] = useState<string[]>(data.muvekkiller || []);

  const [approvedFields, setApprovedFields] = useState({
    tarih: false,
    belge_turu_kodu: false,
    muvekkil_kodu: false,
    esas_no: false,
    karsi_taraf: false,
  });

  const allFieldsApproved = Object.values(approvedFields).every((v) => v);

  const { lawyers: loadedLawyers, doctypes: loadedDocTypes, isLoading: isConfigLoading } = useConfig();

  useEffect(() => {
    if (!isConfigLoading) {
      setLawyerOptions(loadedLawyers);
      setDocTypeOptions(loadedDocTypes);
    }
  }, [loadedLawyers, loadedDocTypes, isConfigLoading]);

  useEffect(() => {
    const normalizedData = { ...data };

    if (normalizedData.belge_turu_kodu) {
      // Keep code clean but don't pad — new format uses code as-is (e.g. ARA, KRR)
      const code = toEnglishUpper(normalizedData.belge_turu_kodu).trim().replace(/[^A-Z0-9]/g, '');
      normalizedData.belge_turu_kodu = code;
    }

    normalizedData.muvekkil_kodu = toTitleCase(normalizedData.muvekkil_kodu || "");
    normalizedData.karsi_taraf = toTitleCase(normalizedData.karsi_taraf || "");

    setEditedData(normalizedData);
    const initialClients = [...(normalizedData.muvekkiller || [])];
    if (normalizedData.muvekkil_adi && !initialClients.includes(normalizedData.muvekkil_adi)) {
      initialClients.push(normalizedData.muvekkil_adi);
    }
    setLocalClientList(initialClients);
    setApprovedFields({
      tarih: false,
      belge_turu_kodu: false,
      muvekkil_kodu: false,
      esas_no: false,
      karsi_taraf: false,
    });
    onValidationChange(false, normalizedData);
  }, [data]);

  useEffect(() => {
    setEditedData(prev => ({ ...prev, muvekkiller: localClientList }));
  }, [localClientList]);

  useEffect(() => {
    if (!linkedCase) return;

    const nextData = { ...editedData };
    const nextApprovals = { ...approvedFields };
    let hasChanges = false;
    const changedFields: string[] = [];

    if (linkedCase.esas_no) {
      nextData.esas_no = linkedCase.esas_no;
      nextApprovals.esas_no = true;
      hasChanges = true;
      changedFields.push("Esas No");
    }

    let linkedMuvekkil: string | null = null;
    let linkedMuvekkilList: string[] = [];

    if (linkedCase.client_parties && Array.isArray(linkedCase.client_parties) && linkedCase.client_parties.length > 0) {
      linkedMuvekkilList = linkedCase.client_parties;
      linkedMuvekkil = linkedCase.client_parties[0];
    } else if (linkedCase.muvekkil_adi) {
      linkedMuvekkil = linkedCase.muvekkil_adi;
      linkedMuvekkilList = [linkedCase.muvekkil_adi];
    } else if (linkedCase.parties && Array.isArray(linkedCase.parties)) {
      const clients = linkedCase.parties
        .filter((p) => p.party_type === "CLIENT" || p.party_type === "MUVEKKIL")
        .map((p) => p.name);
      if (clients.length > 0) {
        linkedMuvekkilList = clients;
        linkedMuvekkil = clients[0];
      }
    }

    if (linkedMuvekkil) {
      nextData.muvekkil_kodu = toTitleCase(linkedMuvekkil);
      nextApprovals.muvekkil_kodu = true;
      setLocalClientList(linkedMuvekkilList);
      hasChanges = true;
      changedFields.push("Müvekkil");
    }

    let linkedKarsiTaraf = linkedCase.karsi_taraf;
    if (!linkedKarsiTaraf && linkedCase.parties && Array.isArray(linkedCase.parties)) {
      const counters = linkedCase.parties
        .filter((p) => p.party_type === "COUNTER")
        .map((p) => p.name);
      if (counters.length > 0) linkedKarsiTaraf = counters.join(", ");
    }

    if (linkedKarsiTaraf) {
      nextData.karsi_taraf = toTitleCase(Array.isArray(linkedKarsiTaraf)
        ? linkedKarsiTaraf.join(", ")
        : linkedKarsiTaraf);
      nextApprovals.karsi_taraf = true;
      hasChanges = true;
      changedFields.push("Karşı Taraf");
    }

    if (hasChanges) {
      setEditedData(nextData);
      setApprovedFields(nextApprovals);
      toast({
        title: "✅ Dava Bilgileri Yüklendi",
        description: `Güncellenen alanlar: ${changedFields.join(", ")}`,
        variant: "default",
      });
    }
  }, [linkedCase, lawyerOptions]);

  // ─── Utility Functions ───────────────────────────────────────────────────────

  const toEnglishUpper = (str: string): string => {
    if (!str) return "";
    let result = str.toLocaleUpperCase('tr-TR');
    const mapping: Record<string, string> = {
      'Ç': 'C', 'Ğ': 'G', 'İ': 'I', 'I': 'I', 'Ö': 'O', 'Ş': 'S', 'Ü': 'U',
      'ç': 'C', 'ğ': 'G', 'ı': 'I', 'i': 'I', 'ö': 'O', 'ş': 'S', 'ü': 'U'
    };
    result = result.replace(/[ÇĞİIÖŞÜçğıöşü]/g, char => mapping[char] || char);
    return result;
  };

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

  /** Turkish/special chars → ASCII equivalent (lowercase preserving) */
  const toAsciiChar = (str: string): string => {
    const mapping: Record<string, string> = {
      'Ç': 'C', 'ç': 'c', 'Ğ': 'G', 'ğ': 'g',
      'İ': 'I', 'ı': 'i', 'Ö': 'O', 'ö': 'o',
      'Ş': 'S', 'ş': 's', 'Ü': 'U', 'ü': 'u',
    };
    return str.replace(/[ÇçĞğİıÖöŞşÜü]/g, ch => mapping[ch] || ch);
  };

  /**
   * Parse various date formats to ISO 8601 (YYYY-MM-DD).
   * Supported inputs: YYYY-MM-DD, DD.MM.YYYY, YYYY/MM/DD, DD/MM/YYYY,
   *                   "DD Ay YYYY" (Turkish month names)
   */
  const parseDateToISO = (dateInput: string): string => {
    const raw = (dateInput || '').trim();
    if (!raw) return 'XXXX-XX-XX';

    // Already ISO
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;

    // DD.MM.YYYY
    const dotMatch = raw.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
    if (dotMatch) {
      return `${dotMatch[3]}-${dotMatch[2].padStart(2, '0')}-${dotMatch[1].padStart(2, '0')}`;
    }

    // YYYY/MM/DD
    const isoSlash = raw.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
    if (isoSlash) {
      return `${isoSlash[1]}-${isoSlash[2].padStart(2, '0')}-${isoSlash[3].padStart(2, '0')}`;
    }

    // DD/MM/YYYY
    const dmySlash = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (dmySlash) {
      return `${dmySlash[3]}-${dmySlash[2].padStart(2, '0')}-${dmySlash[1].padStart(2, '0')}`;
    }

    // "DD Ay YYYY" Turkish text
    const months: Record<string, string> = {
      ocak: '01', 'şubat': '02', mart: '03', nisan: '04', 'mayıs': '05', haziran: '06',
      temmuz: '07', 'ağustos': '08', 'eylül': '09', ekim: '10', 'kasım': '11', 'aralık': '12',
      oca: '01', 'şub': '02', mar: '03', nis: '04', may: '05', haz: '06',
      tem: '07', agu: '08', eyl: '09', eki: '10', kas: '11', ara: '12',
    };
    const textMatch = raw.toLowerCase().match(/^(\d{1,2})\s+([a-z\u00e7\u011f\u0131\u00f6\u015f\u00fc]+)\s+(\d{4})$/);
    if (textMatch) {
      const m = months[textMatch[2]];
      if (m) return `${textMatch[3]}-${m}-${textMatch[1].padStart(2, '0')}`;
    }

    return 'XXXX-XX-XX';
  };

  /**
   * Format esas_no to YY-NUMBER (e.g. "2021/413" → "21-413").
   * No leading zeros, hyphen separator.
   */
  const formatEsasNo = (raw: string): string => {
    if (!raw) return 'XX-XX';
    const match = raw.match(/(\d{2,4})[/\-\s](\d+)/);
    if (match) {
      const year = match[1].slice(-2);
      const number = match[2];
      return `${year}-${number}`;
    }
    return toEnglishUpper(raw).replace(/[^A-Z0-9-]/g, '') || 'XX-XX';
  };

  /**
   * Format client name to "A.Soyad" or "A.Soyad_vd" per naming standard.
   *
   * Rules:
   *  - Person  → initial of first name + "." + surname (ASCII, TitleCase)
   *  - Company → first letter + "." + sector keyword or first word
   *  - Double surname → hyphen: S.Yilmaz-Demir
   *  - Double first name → only first initial: M.Kaya
   *  - Multiple clients → append "_vd"
   */
  const formatClientName = (fullName: string, clientCount: number): string => {
    const name = (fullName || '').trim();
    if (!name) return 'XXXXX';

    const companyMarkers = [
      'A.Ş', 'AŞ', 'A.S.', 'LTD', 'LİMİTED', 'LIMITED', 'ŞTİ', 'STI',
      'SİGORTA', 'SIGORTA', 'HOLDİNG', 'HOLDING', 'BANKA', 'BANK',
      'BANKAS', 'GRUP', 'GROUP', 'ŞİRKET', 'SIRKETI', 'CORP', 'INC',
    ];
    const sectorWords: Record<string, string> = {
      sigorta: 'Sigorta', holding: 'Holding', banka: 'Banka', finans: 'Finans',
      grup: 'Grup', yatirim: 'Yatirim',
    };

    const upperName = toEnglishUpper(name);
    const isCompany = companyMarkers.some(m => upperName.includes(m));

    let result: string;

    if (isCompany) {
      const words = name.trim().split(/\s+/);
      const firstLetter = toAsciiChar(words[0]).charAt(0).toUpperCase();

      // Look for a known sector keyword in the name
      let sectorFound = '';
      for (const word of words) {
        const key = toAsciiChar(word).toLowerCase();
        if (sectorWords[key]) { sectorFound = sectorWords[key]; break; }
      }

      if (sectorFound) {
        result = `${firstLetter}.${sectorFound}`;
      } else {
        // Use first word as the identifier
        const firstWord = toAsciiChar(words[0]).replace(/[^A-Za-z0-9]/g, '');
        result = firstWord.charAt(0).toUpperCase() + firstWord.slice(1).toLowerCase();
      }
    } else {
      // Strip titles
      const cleaned = name
        .replace(/\b(AV|DR|PROF|UZM|DOÇ|DOC|MÜH|MIH|MİMAR|MIMAR)\.?\s*/gi, '')
        .trim();
      const parts = cleaned.split(/\s+/).filter(p => p.length > 0);

      if (parts.length === 0) return 'XXXXX';

      if (parts.length === 1) {
        const w = toAsciiChar(parts[0]);
        result = w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
      } else {
        // First initial (only first name's first char, handles double first names)
        const initial = toAsciiChar(parts[0]).charAt(0).toUpperCase();
        // Last part = surname (handles double surnames by keeping the hyphenated form if already there)
        const surnameRaw = toAsciiChar(parts[parts.length - 1]);
        const surname = surnameRaw.charAt(0).toUpperCase() + surnameRaw.slice(1).toLowerCase();
        result = `${initial}.${surname}`;
      }
    }

    // Strip any remaining unsafe chars
    result = result.replace(/[^A-Za-z0-9._-]/g, '');

    if (clientCount > 1) result += '_vd';

    return result;
  };

  // ─── Filename Generation ──────────────────────────────────────────────────────

  /**
   * Builds the filename per the new standard:
   *   YYYY-MM-DD_TÜR_YY-ESASNO_A.Soyad.pdf
   */
  const generateFilename = (): string => {
    // 1. Date → YYYY-MM-DD
    const rawDate = approvedFields.tarih ? editedData.tarih : data.tarih;
    const date = parseDateToISO(rawDate || '');

    // 2. Document type code — strip trailing underscores (padding), keep hyphens
    // e.g. "AYM-KRR______" → "AYM-KRR",  "ARA-KRR-RUCU_" → "ARA-KRR-RUCU"
    const rawType = approvedFields.belge_turu_kodu ? editedData.belge_turu_kodu : data.belge_turu_kodu;
    const docType = toEnglishUpper(rawType || '').replace(/_+$/, '').replace(/[^A-Z0-9-]/g, '') || 'XXX';

    // 3. Esas No → YY-NUMBER (no leading zeros, hyphen)
    const rawEsas = approvedFields.esas_no ? editedData.esas_no : data.esas_no;
    const esasNo = formatEsasNo(rawEsas || '');

    // 4. Counter party name → A.Soyad (or A.Soyad_vd if multiple)
    const rawKarsi = approvedFields.karsi_taraf ? (editedData.karsi_taraf || '') : (data.karsi_taraf || '');
    const karsiParts = rawKarsi.split(/[,;]/).map(p => p.trim()).filter(Boolean);
    const firstKarsi = karsiParts[0] || '';
    const counterName = formatClientName(firstKarsi, karsiParts.length);

    return `${date}_${docType}_${esasNo}_${counterName}`;
  };

  const currentGeneratedFilename = generateFilename();

  useEffect(() => {
    const isAllApproved = Object.values(approvedFields).every((v) => v);
    onValidationChange(isAllApproved, { ...editedData, generated_filename: currentGeneratedFilename });
  }, [editedData, approvedFields, onValidationChange, currentGeneratedFilename]);

  const handleFieldChange = (field: keyof typeof editedData, value: any) => {
    setEditedData((prev) => ({ ...prev, [field]: value }));
  };

  const handleFieldApproval = (field: keyof typeof approvedFields, checked: boolean) => {
    if (checked) {
      if (field === "muvekkil_kodu") {
        setEditedData(prev => ({ ...prev, muvekkil_kodu: toTitleCase(prev.muvekkil_kodu) }));
      } else if (field === "karsi_taraf") {
        setEditedData(prev => ({ ...prev, karsi_taraf: toTitleCase(prev.karsi_taraf || "") }));
      }
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
            variant={allFieldsApproved ? "default" : "secondary"}
            className={allFieldsApproved ? "bg-success/90 text-success-foreground glow-success" : "bg-muted text-muted-foreground"}
          >
            {allFieldsApproved ? "✓ Onaylandı" : `${currentGeneratedFilename.replace(".pdf", "").length} karakter`}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-6 space-y-6">
        <p className="text-sm text-muted-foreground">Aşağıdaki verileri kontrol edin ve onaylayın.</p>
        <div className="glass-input rounded-xl p-4">
          <div className="flex items-center gap-3">
            <code className="text-sm font-mono text-foreground flex-1 break-all">{currentGeneratedFilename}</code>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label className="flex items-center gap-2 text-xs text-muted-foreground"><Calendar className="w-3 h-3" /> [A] TARİH</Label>
            <div className="relative flex items-center gap-2">
              <Input value={editedData.tarih} onChange={(e) => handleFieldChange("tarih", e.target.value)} className="font-mono glass-input" disabled={approvedFields.tarih} />
              <Checkbox checked={approvedFields.tarih} onCheckedChange={(c) => handleFieldApproval("tarih", !!c)} />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="flex items-center gap-2 text-xs text-muted-foreground">
              <User className="w-3 h-3" /> [B] MÜVEKKİL
              {localClientList.length > 1 && <Badge variant="outline" className="ml-1">+{localClientList.length - 1}</Badge>}
            </Label>
            <div className="relative flex items-center gap-2">
              <Input value={editedData.muvekkil_kodu} onChange={(e) => handleFieldChange("muvekkil_kodu", e.target.value)} className="font-mono glass-input flex-1" disabled={approvedFields.muvekkil_kodu} />
              <Popover open={openClientSelect} onOpenChange={setOpenClientSelect}>
                <PopoverTrigger asChild><Button variant="outline" className="w-10 px-0 glass-input border-0" disabled={approvedFields.muvekkil_kodu}><ChevronsUpDown className="h-4 w-4 opacity-50" /></Button></PopoverTrigger>
                <PopoverContent className="w-[300px] p-0 glass z-[100]" align="end">
                  <Command>
                    <CommandInput placeholder="Ara..." />
                    <CommandList>
                      <CommandEmpty>Sonuç yok.</CommandEmpty>
                      <CommandGroup heading="Müvekkiller">
                        {localClientList.map((name) => (
                          <CommandItem key={name} onSelect={() => { handleFieldChange("muvekkil_kodu", name); setOpenClientSelect(false); }}>
                            <Check className={cn("mr-2 h-4 w-4", editedData.muvekkil_kodu === name ? "opacity-100" : "opacity-0")} />
                            {name}
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
              <Checkbox checked={approvedFields.muvekkil_kodu} onCheckedChange={(c) => handleFieldApproval("muvekkil_kodu", !!c)} />
            </div>
          </div>

          <div className="col-span-2 space-y-2">
            <Label className="flex items-center gap-2 text-xs text-muted-foreground"><User className="w-3 h-3" /> [VS] KARŞI TARAF</Label>
            <div className="relative flex items-center gap-2">
              <Input value={editedData.karsi_taraf || ""} onChange={(e) => handleFieldChange("karsi_taraf", e.target.value)} className="font-mono glass-input flex-1" disabled={approvedFields.karsi_taraf} />
              <Checkbox checked={approvedFields.karsi_taraf} onCheckedChange={(c) => handleFieldApproval("karsi_taraf", !!c)} />
            </div>
          </div>

          <div className="col-span-2 space-y-2">
            <Label className="flex items-center gap-2 text-xs text-muted-foreground"><FileText className="w-3 h-3" /> [C] BELGE TÜRÜ</Label>
            <div className="relative flex items-center gap-2">
              <Popover open={openDocType} onOpenChange={setOpenDocType}>
                <PopoverTrigger asChild><Button variant="outline" className="w-full justify-between glass-input font-mono border-0" disabled={approvedFields.belge_turu_kodu}>{editedData.belge_turu_kodu || "Seçin..."}<ChevronsUpDown className="h-4 w-4 opacity-50" /></Button></PopoverTrigger>
                <PopoverContent className="w-[300px] p-0 glass z-[100]" align="start">
                  <Command>
                    <CommandInput placeholder="Ara..." />
                    <CommandList>
                      <CommandEmpty>Sonuç yok.</CommandEmpty>
                      {docTypeOptions.map((item) => (
                        <CommandItem key={item.code} onSelect={() => { handleFieldChange("belge_turu_kodu", item.code); setOpenDocType(false); }}>{item.code} - {item.name}</CommandItem>
                      ))}
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
              <Checkbox checked={approvedFields.belge_turu_kodu} onCheckedChange={(c) => handleFieldApproval("belge_turu_kodu", !!c)} />
            </div>
          </div>

          <div className="col-span-2 space-y-2">
            <Label className="text-xs text-muted-foreground">[F] ESAS NO</Label>
            <div className="relative flex items-center gap-2">
              <Input value={editedData.esas_no} onChange={(e) => handleFieldChange("esas_no", e.target.value)} className="font-mono glass-input" disabled={approvedFields.esas_no} />
              <Checkbox checked={approvedFields.esas_no} onCheckedChange={(c) => handleFieldApproval("esas_no", !!c)} />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
