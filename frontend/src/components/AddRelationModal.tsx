import { useState, useEffect, useRef } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, Loader2, Scale, Building2, Gavel, FileText, X, AlertCircle } from "lucide-react";
import { useCases } from "@/hooks/useCases";
import { useDebounce } from "@/hooks/useDebounce";

// ---- İlişki türleri ----
const RELATION_TYPES = [
    { value: "ILGILI",       label: "İlgili Dava",               description: "Genel ilişki" },
    { value: "ICRA_HUKUK",   label: "İcra → Hukuk",              description: "İcra takibinden doğan hukuk davası" },
    { value: "ICRA_CEZA",    label: "İcra → Ceza",               description: "İcra takibinden doğan ceza davası" },
    { value: "ASIL_TEMYIZ",  label: "Asıl → Temyiz",             description: "Asıl dava ve temyiz süreci" },
    { value: "ASIL_YENIDEN", label: "Asıl → Yeniden Yargılama",  description: "Yeniden yargılama kararı" },
    { value: "BIRLESEN",     label: "Birleştirilen Dava",         description: "Mahkemece birleştirilen dava" },
    { value: "AYRISTIRILAN", label: "Ayrıştırılan Dava",          description: "Mahkemece ayrıştırılan dava" },
];

// ---- Dosya türü ikonları ----
const FILE_TYPE_ICONS: Record<string, React.ReactNode> = {
    Hukuk:   <Scale className="w-3.5 h-3.5 text-blue-400" />,
    İcra:    <Building2 className="w-3.5 h-3.5 text-orange-400" />,
    Ceza:    <Gavel className="w-3.5 h-3.5 text-red-400" />,
    İdare:   <FileText className="w-3.5 h-3.5 text-purple-400" />,
    Ticaret: <FileText className="w-3.5 h-3.5 text-green-400" />,
};
const getFileTypeIcon = (type?: string | null) =>
    FILE_TYPE_ICONS[type ?? ""] ?? <FileText className="w-3.5 h-3.5 text-muted-foreground" />;

const STATUS_COLORS: Record<string, string> = {
    DERDEST: "bg-emerald-500/15 text-emerald-400",
    KARAR:   "bg-blue-500/15 text-blue-400",
    KAPALI:  "bg-gray-500/15 text-gray-400",
    TEMYIZ:  "bg-purple-500/15 text-purple-400",
};

interface CaseSearchResult {
    id: number;
    tracking_no: string;
    esas_no?: string | null;
    court?: string | null;
    status: string;
    file_type?: string | null;
    parties?: { party_type: string; name: string; role: string }[];
}

interface AddRelationModalProps {
    open: boolean;
    currentCaseId: number;
    onClose: () => void;
    onSave: (targetCaseId: number, relationType: string, note: string | null) => Promise<boolean>;
}

const AddRelationModal = ({ open, currentCaseId, onClose, onSave }: AddRelationModalProps) => {
    const { searchCases } = useCases();

    const [query, setQuery] = useState("");
    const debouncedQuery = useDebounce(query, 350);
    const [searchResults, setSearchResults] = useState<CaseSearchResult[]>([]);
    const [searching, setSearching] = useState(false);
    const [selectedCase, setSelectedCase] = useState<CaseSearchResult | null>(null);

    const [relationType, setRelationType] = useState("ILGILI");
    const [note, setNote] = useState("");
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Arama sonuçlarını getir
    useEffect(() => {
        if (!debouncedQuery || debouncedQuery.length < 2) {
            setSearchResults([]);
            return;
        }
        const run = async () => {
            setSearching(true);
            const results = await searchCases(debouncedQuery);
            // Kendisini ve zaten seçileni çıkar
            setSearchResults(
                (Array.isArray(results) ? results : results?.cases ?? [])
                    .filter((c: CaseSearchResult) => c.id !== currentCaseId)
                    .slice(0, 8)
            );
            setSearching(false);
        };
        run();
    }, [debouncedQuery, currentCaseId]); // eslint-disable-line react-hooks/exhaustive-deps

    const reset = () => {
        setQuery("");
        setSearchResults([]);
        setSelectedCase(null);
        setRelationType("ILGILI");
        setNote("");
        setError(null);
        setSaving(false);
    };

    const handleClose = () => {
        reset();
        onClose();
    };

    const handleSave = async () => {
        if (!selectedCase) {
            setError("Lütfen bağlanacak davayı seçin.");
            return;
        }
        setSaving(true);
        setError(null);
        const ok = await onSave(selectedCase.id, relationType, note.trim() || null);
        setSaving(false);
        if (ok) handleClose();
    };

    const clientName = (c: CaseSearchResult) =>
        c.parties?.find(p => p.party_type === "CLIENT")?.name ?? null;

    return (
        <Dialog open={open} onOpenChange={v => !v && handleClose()}>
            <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        Dava Bağlantısı Ekle
                    </DialogTitle>
                    <DialogDescription>
                        Bu davayı başka bir davayla ilişkilendirin. İki dava aynı dava dosyasından
                        erişilebilir hâle gelir.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-5 py-2">
                    {/* Dava arama */}
                    <div className="space-y-2">
                        <Label>İlişkili Dava <span className="text-destructive">*</span></Label>

                        {selectedCase ? (
                            /* Seçili dava kartı */
                            <div className="flex items-start gap-3 p-3 rounded-xl border border-primary/30 bg-primary/5">
                                <div className="flex-1 min-w-0 space-y-1">
                                    <div className="flex items-center gap-2">
                                        {getFileTypeIcon(selectedCase.file_type)}
                                        <span className="font-semibold tabular-nums text-sm">
                                            {selectedCase.esas_no || selectedCase.tracking_no}
                                        </span>
                                        <Badge
                                            className={`text-[10px] border-0 ${STATUS_COLORS[selectedCase.status?.toUpperCase()] ?? "bg-primary/15 text-primary"}`}
                                        >
                                            {selectedCase.status}
                                        </Badge>
                                    </div>
                                    <p className="text-xs text-muted-foreground truncate">{selectedCase.court || "Mahkeme belirtilmemiş"}</p>
                                    {clientName(selectedCase) && (
                                        <p className="text-xs text-muted-foreground">Müvekkil: {clientName(selectedCase)}</p>
                                    )}
                                </div>
                                <Button
                                    size="icon"
                                    variant="ghost"
                                    className="w-7 h-7 shrink-0 text-muted-foreground hover:text-foreground"
                                    onClick={() => { setSelectedCase(null); setQuery(""); }}
                                >
                                    <X className="w-4 h-4" />
                                </Button>
                            </div>
                        ) : (
                            /* Arama kutusu */
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                <Input
                                    className="pl-9"
                                    placeholder="Esas no, tracking no veya müvekkil adı..."
                                    value={query}
                                    onChange={e => setQuery(e.target.value)}
                                    autoFocus
                                />
                                {searching && (
                                    <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 animate-spin text-muted-foreground" />
                                )}

                                {/* Sonuç listesi */}
                                {(searchResults.length > 0 || (debouncedQuery.length >= 2 && !searching)) && (
                                    <div className="absolute top-full left-0 right-0 z-50 mt-1 bg-popover border border-border rounded-xl shadow-xl overflow-hidden max-h-60 overflow-y-auto">
                                        {searchResults.length === 0 ? (
                                            <div className="px-4 py-3 text-sm text-muted-foreground text-center">
                                                Sonuç bulunamadı
                                            </div>
                                        ) : (
                                            searchResults.map(c => (
                                                <button
                                                    key={c.id}
                                                    className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors border-b border-border/30 last:border-0"
                                                    onClick={() => { setSelectedCase(c); setQuery(""); setSearchResults([]); }}
                                                >
                                                    <div className="mt-0.5">{getFileTypeIcon(c.file_type)}</div>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <span className="font-semibold text-sm tabular-nums">
                                                                {c.esas_no || c.tracking_no}
                                                            </span>
                                                            <Badge
                                                                className={`text-[10px] border-0 px-1.5 ${STATUS_COLORS[c.status?.toUpperCase()] ?? "bg-primary/15 text-primary"}`}
                                                            >
                                                                {c.status}
                                                            </Badge>
                                                        </div>
                                                        <p className="text-xs text-muted-foreground truncate mt-0.5">
                                                            {c.court || "Mahkeme belirtilmemiş"}
                                                        </p>
                                                        {clientName(c) && (
                                                            <p className="text-xs text-muted-foreground/70">{clientName(c)}</p>
                                                        )}
                                                    </div>
                                                </button>
                                            ))
                                        )}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* İlişki türü */}
                    <div className="space-y-2">
                        <Label>İlişki Türü <span className="text-destructive">*</span></Label>
                        <Select value={relationType} onValueChange={setRelationType}>
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {RELATION_TYPES.map(rt => (
                                    <SelectItem key={rt.value} value={rt.value}>
                                        <div>
                                            <span className="font-medium">{rt.label}</span>
                                            <span className="text-muted-foreground text-xs ml-2">— {rt.description}</span>
                                        </div>
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Not */}
                    <div className="space-y-2">
                        <Label>Not <span className="text-muted-foreground text-xs font-normal">(opsiyonel)</span></Label>
                        <Textarea
                            placeholder="Bu bağlantıyla ilgili açıklama veya not ekleyin..."
                            value={note}
                            onChange={e => setNote(e.target.value)}
                            className="resize-none"
                            rows={3}
                        />
                    </div>

                    {/* Hata mesajı */}
                    {error && (
                        <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg border border-destructive/20">
                            <AlertCircle className="w-4 h-4 shrink-0" />
                            {error}
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="ghost" onClick={handleClose} disabled={saving}>
                        İptal
                    </Button>
                    <Button onClick={handleSave} disabled={saving || !selectedCase}>
                        {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                        {saving ? "Kaydediliyor..." : "Kaydet"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};

export default AddRelationModal;
