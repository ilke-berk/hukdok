import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Check, FileText, Calendar, User, FileCode, ChevronsUpDown, Hash, Users as UsersIcon, AlertCircle } from "lucide-react";
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
import { HairlineCard, Eyebrow } from "@/components/dashboard/primitives";
import { AiPill } from "@/components/flow/primitives";

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
  sonraki_durusma_tarihi?: string;
  sonraki_durusma_saati?: string;
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
    sonraki_durusma_tarihi: false,
  });

  const isDurusmaZapt = (() => {
    const code = (editedData.belge_turu_kodu || "").toUpperCase();
    return code.includes("DURUSMA") || code.includes("ZABIT") || code.includes("TUTANAK") || code.includes("TENSIP");
  })();

  const allFieldsApproved = Object.entries(approvedFields).every(([k, v]) => {
    if (k === "sonraki_durusma_tarihi" && !isDurusmaZapt) return true;
    return v;
  });

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
    // sonraki_durusma_tarihi zaten ISO formatta gelir, dokunmaya gerek yok

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
      sonraki_durusma_tarihi: false,
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
    onValidationChange(allFieldsApproved, { ...editedData, generated_filename: currentGeneratedFilename });
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

  // Bir alanın AI tarafından doldurulup kullanıcı tarafından değiştirilmediğini kontrol eder.
  // Override edilince AiPill kaybolur.
  const isAi = (field: keyof typeof editedData) => {
    const original = (data[field] ?? "") as string;
    const current = (editedData[field] ?? "") as string;
    return Boolean(original) && original === current;
  };

  return (
    <HairlineCard padded={false}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-[var(--border)] flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 min-w-0">
          <FileCode className="w-4 h-4 text-[var(--brand)] shrink-0" />
          <Eyebrow tone="brand">03 · Onay</Eyebrow>
          <h2 className="font-display text-[15px] font-medium text-[var(--fg)] tracking-[-0.005em]">
            Önerilen Dosya Adı
          </h2>
        </div>
        {allFieldsApproved ? (
          <span className="inline-flex items-center gap-1 px-2 py-1 font-mono text-[10px] tracking-[0.14em] uppercase border border-[#2f8a5d]/40 bg-[#2f8a5d]/15 text-[#2f8a5d]">
            <Check className="w-3 h-3" strokeWidth={2.2} />
            Onaylandı
          </span>
        ) : (
          <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
            {currentGeneratedFilename.replace(".pdf", "").length} karakter
          </span>
        )}
      </div>

      <div className="p-5 grid gap-5">
        <p className="text-[13px] text-[var(--fg-muted)] leading-relaxed">
          AI çıkarımlarını gözden geçirin ve onay kutularını işaretleyin.
          Bir alanı değiştirirseniz AI rozeti kaybolur.
        </p>

        {/* Filename önizleme */}
        <div className="bg-[var(--bg-sunken)] border border-[var(--border)] px-4 py-3">
          <div className="font-mono text-[9.5px] tracking-[0.22em] uppercase text-[var(--fg-subtle)] mb-1.5">
            Önizleme
          </div>
          <code className="block font-mono text-[13px] text-[var(--fg)] break-all leading-relaxed">
            {currentGeneratedFilename}
          </code>
        </div>

        {/* Form alanları */}
        <div className="grid grid-cols-2 gap-4">
          {/* Tarih */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between gap-2">
              <label className="inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                <Calendar className="w-3 h-3" />
                [A] Tarih
              </label>
              {isAi("tarih") && !approvedFields.tarih && <AiPill />}
            </div>
            <div className="flex items-center gap-2">
              <Input
                value={editedData.tarih}
                onChange={(e) => handleFieldChange("tarih", e.target.value)}
                className="font-mono bg-[var(--bg)] border-[var(--border)] rounded-[3px] flex-1"
                disabled={approvedFields.tarih}
              />
              <Checkbox
                checked={approvedFields.tarih}
                onCheckedChange={(c) => handleFieldApproval("tarih", !!c)}
                className="w-5 h-5 rounded-[2px] data-[state=checked]:bg-[var(--brand)] data-[state=checked]:border-[var(--brand)]"
              />
            </div>
          </div>

          {/* Müvekkil */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between gap-2">
              <label className="inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                <User className="w-3 h-3" />
                [B] Müvekkil
                {localClientList.length > 1 && (
                  <span className="ml-1 px-1.5 py-0.5 bg-[var(--bg-sunken)] border border-[var(--border)] text-[var(--fg-muted)] tracking-[0.04em] normal-case">
                    +{localClientList.length - 1}
                  </span>
                )}
              </label>
              {isAi("muvekkil_kodu") && !approvedFields.muvekkil_kodu && <AiPill />}
            </div>
            <div className="flex items-center gap-2">
              <Input
                value={editedData.muvekkil_kodu}
                onChange={(e) => handleFieldChange("muvekkil_kodu", e.target.value)}
                className="font-mono bg-[var(--bg)] border-[var(--border)] rounded-[3px] flex-1"
                disabled={approvedFields.muvekkil_kodu}
              />
              {localClientList.length > 1 && (
                <Popover open={openClientSelect} onOpenChange={setOpenClientSelect}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className="w-9 h-9 px-0 bg-[var(--bg)] border-[var(--border)] rounded-[3px]"
                      disabled={approvedFields.muvekkil_kodu}
                    >
                      <ChevronsUpDown className="h-3.5 w-3.5 opacity-50" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[300px] p-0 z-[100] bg-[var(--bg-elevated)] border-[var(--border)]" align="end">
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
              )}
              <Checkbox
                checked={approvedFields.muvekkil_kodu}
                onCheckedChange={(c) => handleFieldApproval("muvekkil_kodu", !!c)}
                className="w-5 h-5 rounded-[2px] data-[state=checked]:bg-[var(--brand)] data-[state=checked]:border-[var(--brand)]"
              />
            </div>
          </div>

          {/* Karşı Taraf */}
          <div className="col-span-2 flex flex-col gap-1.5">
            <div className="flex items-center justify-between gap-2">
              <label className="inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                <UsersIcon className="w-3 h-3" />
                [VS] Karşı Taraf
              </label>
              {isAi("karsi_taraf") && !approvedFields.karsi_taraf && <AiPill />}
            </div>
            <div className="flex items-center gap-2">
              <Input
                value={editedData.karsi_taraf || ""}
                onChange={(e) => handleFieldChange("karsi_taraf", e.target.value)}
                className="font-mono bg-[var(--bg)] border-[var(--border)] rounded-[3px] flex-1"
                disabled={approvedFields.karsi_taraf}
              />
              <Checkbox
                checked={approvedFields.karsi_taraf}
                onCheckedChange={(c) => handleFieldApproval("karsi_taraf", !!c)}
                className="w-5 h-5 rounded-[2px] data-[state=checked]:bg-[var(--brand)] data-[state=checked]:border-[var(--brand)]"
              />
            </div>
          </div>

          {/* Belge Türü */}
          <div className="col-span-2 flex flex-col gap-1.5">
            <div className="flex items-center justify-between gap-2">
              <label className="inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                <FileText className="w-3 h-3" />
                [C] Belge Türü
              </label>
              {isAi("belge_turu_kodu") && !approvedFields.belge_turu_kodu && <AiPill />}
            </div>
            <div className="flex items-center gap-2">
              <Popover open={openDocType} onOpenChange={setOpenDocType}>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    className="w-full justify-between bg-[var(--bg)] border-[var(--border)] rounded-[3px] text-[var(--fg)] font-normal h-10"
                    disabled={approvedFields.belge_turu_kodu}
                  >
                    <span className="truncate">
                      {editedData.belge_turu_kodu
                        ? (docTypeOptions.find(d => (d.code ?? "").replace(/_+$/, "") === editedData.belge_turu_kodu)?.name ?? editedData.belge_turu_kodu)
                        : "Seçin..."}
                    </span>
                    <ChevronsUpDown className="h-3.5 w-3.5 opacity-50 shrink-0" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[340px] p-0 z-[100] bg-[var(--bg-elevated)] border-[var(--border)]" align="start">
                  <Command>
                    <CommandInput placeholder="Ara..." />
                    <CommandList>
                      <CommandEmpty>Sonuç yok.</CommandEmpty>
                      {docTypeOptions.map((item) => {
                        const cleanCode = (item.code ?? "").replace(/_+$/, "");
                        return (
                          <CommandItem key={item.code} onSelect={() => { handleFieldChange("belge_turu_kodu", cleanCode); setOpenDocType(false); }}>
                            {item.name}
                          </CommandItem>
                        );
                      })}
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
              <Checkbox
                checked={approvedFields.belge_turu_kodu}
                onCheckedChange={(c) => handleFieldApproval("belge_turu_kodu", !!c)}
                className="w-5 h-5 rounded-[2px] data-[state=checked]:bg-[var(--brand)] data-[state=checked]:border-[var(--brand)]"
              />
            </div>
          </div>

          {/* Esas No */}
          <div className="col-span-2 flex flex-col gap-1.5">
            <div className="flex items-center justify-between gap-2">
              <label className="inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                <Hash className="w-3 h-3" />
                [F] Esas No
              </label>
              {isAi("esas_no") && !approvedFields.esas_no && <AiPill />}
            </div>
            <div className="flex items-center gap-2">
              <Input
                value={editedData.esas_no}
                onChange={(e) => handleFieldChange("esas_no", e.target.value)}
                className="font-mono bg-[var(--bg)] border-[var(--border)] rounded-[3px] flex-1"
                disabled={approvedFields.esas_no}
              />
              <Checkbox
                checked={approvedFields.esas_no}
                onCheckedChange={(c) => handleFieldApproval("esas_no", !!c)}
                className="w-5 h-5 rounded-[2px] data-[state=checked]:bg-[var(--brand)] data-[state=checked]:border-[var(--brand)]"
              />
            </div>
          </div>

          {/* Duruşma — sadece duruşma zaptlarında */}
          {isDurusmaZapt && (
            <div className="col-span-2 bg-[#c47a1e]/10 border border-[#c47a1e]/40 p-4 grid gap-2">
              <div className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[#c47a1e]">
                <Calendar className="w-3.5 h-3.5" />
                Sonraki Duruşma — Ajandaya Eklenecek
              </div>
              <div className="flex gap-2">
                <Input
                  type="date"
                  value={editedData.sonraki_durusma_tarihi || ""}
                  onChange={(e) => handleFieldChange("sonraki_durusma_tarihi", e.target.value)}
                  className="font-mono bg-[var(--bg)] border-[var(--border)] rounded-[3px] flex-1"
                  disabled={approvedFields.sonraki_durusma_tarihi}
                />
                <Input
                  type="time"
                  value={editedData.sonraki_durusma_saati || ""}
                  onChange={(e) => handleFieldChange("sonraki_durusma_saati", e.target.value)}
                  className="font-mono bg-[var(--bg)] border-[var(--border)] rounded-[3px] w-28"
                  disabled={approvedFields.sonraki_durusma_tarihi}
                  placeholder="--:--"
                />
                <Checkbox
                  checked={approvedFields.sonraki_durusma_tarihi}
                  onCheckedChange={(c) => handleFieldApproval("sonraki_durusma_tarihi", !!c)}
                  className="w-5 h-5 self-center rounded-[2px] data-[state=checked]:bg-[#c47a1e] data-[state=checked]:border-[#c47a1e]"
                />
              </div>
              {!editedData.sonraki_durusma_tarihi && (
                <p className="inline-flex items-center gap-1.5 text-[11px] text-[#c47a1e]/80">
                  <AlertCircle className="w-3 h-3" />
                  Tarih belgeden çıkarılamadı. Manuel girin veya boş bırakıp onaylayın.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </HairlineCard>
  );
};
