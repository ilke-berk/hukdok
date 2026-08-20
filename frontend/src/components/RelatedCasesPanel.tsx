import { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import {
    Link2, Trash2, Plus, ExternalLink, Pin, Sparkles,
    User, Scale, Gavel, FileText, Building2, BarChart3,
} from "lucide-react";
import { useCases } from "@/hooks/useCases";
import AddRelationModal from "./AddRelationModal";

// ---- Tipler ----
export type RelationType =
    // Elle kurulan bağlar (AddRelationModal'daki seçenekler)
    | "ICRA_CEZA" | "ICRA_HUKUK" | "ASIL_TEMYIZ"
    | "ASIL_YENIDEN" | "BIRLESEN" | "AYRISTIRILAN" | "ILGILI"
    // Otomatik katman — backend'de services/case_relations_auto.py üretir,
    // hiçbir tabloya yazılmaz (TKU grubu + esas/mahkeme ikizi dedektörleri)
    | "AYNI_DAVA" | "YENIDEN_ACILAN" | "ARABULUCULUK_ONCULU"
    | "ICRA_PARALEL" | "CEZA_PARALEL" | "SAVCILIK_PARALEL" | "ADLI_IDARI_PARALEL";

export interface RelatedCase {
    id: number;
    tracking_no: string;
    esas_no?: string | null;
    court?: string | null;
    status: string;
    file_type?: string | null;
    parties: { name: string; role: string }[];
    relation_id?: number;
    relation_type: RelationType | string;
    match_reason: string;
    is_manual: boolean;
    note?: string | null;
}

export interface RelatedCasesResponse {
    manual: RelatedCase[];
    automatic: RelatedCase[];
}

// ---- İlişki etiketi Türkçeleri ----
const RELATION_TYPE_LABELS: Record<string, string> = {
    ICRA_CEZA:    "İcra → Ceza",
    ICRA_HUKUK:   "İcra → Hukuk",
    ASIL_TEMYIZ:  "Asıl → Temyiz",
    ASIL_YENIDEN: "Asıl → Yeniden Yargılama",
    BIRLESEN:     "Birleştirilen",
    AYRISTIRILAN: "Ayrıştırılan",
    ILGILI:       "İlgili Dava",
    // Otomatik katman
    AYNI_DAVA:           "Aynı Dava",
    YENIDEN_ACILAN:      "Yeniden Açılan / Mahkeme Değişikliği",
    ARABULUCULUK_ONCULU: "Arabuluculuk → Dava",
    ICRA_PARALEL:        "İcra Takibi",
    CEZA_PARALEL:        "Ceza Dosyası",
    SAVCILIK_PARALEL:    "Savcılık Dosyası",
    ADLI_IDARI_PARALEL:  "Adli ↔ İdari Paralel",
};

// AYNI_DAVA sıradan bir ilişki değil, bir UYARIDIR: iki kart tek davayı gösteriyor
// (ölçümde çoğu "aynı dava, farklı müvekkil"). Panelde ayrı renkle durur.
const AYNI_DAVA = "AYNI_DAVA";

// ---- Dosya türü meta ----
const fileTypeMeta: Record<string, { color: string; bg: string; border: string; icon: React.ReactNode }> = {
    Hukuk:   { color: "text-[var(--brand)]", bg: "bg-[var(--brand-soft)]", border: "border-[var(--brand)]/30", icon: <Scale className="w-3.5 h-3.5" /> },
    İcra:    { color: "text-[#c47a1e]",     bg: "bg-[#c47a1e]/10",     border: "border-[#c47a1e]/30",     icon: <Building2 className="w-3.5 h-3.5" /> },
    Ceza:    { color: "text-[#a8323b]",     bg: "bg-[#a8323b]/10",     border: "border-[#a8323b]/30",     icon: <Gavel className="w-3.5 h-3.5" /> },
    İdare:   { color: "text-[#7a3f8a]",     bg: "bg-[#7a3f8a]/10",     border: "border-[#7a3f8a]/30",     icon: <FileText className="w-3.5 h-3.5" /> },
    Ticaret: { color: "text-[#2f8a5d]",     bg: "bg-[#2f8a5d]/10",     border: "border-[#2f8a5d]/30",     icon: <BarChart3 className="w-3.5 h-3.5" /> },
};
const getFileTypeMeta = (type?: string | null) =>
    fileTypeMeta[type ?? ""] ?? { color: "text-[var(--brand)]", bg: "bg-[var(--brand-soft)]", border: "border-[var(--brand)]/30", icon: <FileText className="w-3.5 h-3.5" /> };

// ---- Statü renkleri ----
const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
    DERDEST: { bg: "bg-[#2f8a5d]/15",      text: "text-[#2f8a5d]",       dot: "bg-[#2f8a5d]" },
    ISTINAF: { bg: "bg-[#c47a1e]/15",      text: "text-[#c47a1e]",       dot: "bg-[#c47a1e]" },
    TEMYIZ:  { bg: "bg-[#7a3f8a]/15",      text: "text-[#7a3f8a]",       dot: "bg-[#7a3f8a]" },
    KARAR:   { bg: "bg-[var(--brand-soft)]", text: "text-[var(--brand)]",  dot: "bg-[var(--brand)]" },
    KAPALI:  { bg: "bg-[var(--bg-sunken)]",  text: "text-[var(--fg-subtle)]", dot: "bg-[var(--fg-subtle)]" },
};
const getStatusStyle = (status: string) =>
    statusColors[status?.toLocaleUpperCase("tr-TR")] ?? { bg: "bg-[var(--brand-soft)]", text: "text-[var(--brand)]", dot: "bg-[var(--brand)]" };

// =================================================================
// Ana panel bileşeni
// =================================================================
interface RelatedCasesPanelProps {
    caseId: number;
    onCountChange?: (count: number) => void;
}

const RelatedCasesPanel = ({ caseId, onCountChange }: RelatedCasesPanelProps) => {
    const navigate = useNavigate();
    const { getRelatedCases, removeCaseRelation, addCaseRelation } = useCases();

    const [manualList, setManualList] = useState<RelatedCase[]>([]);
    const [autoList, setAutoList] = useState<RelatedCase[]>([]);
    const [loading, setLoading] = useState(true);
    const [addModalOpen, setAddModalOpen] = useState(false);
    const [deletingId, setDeletingId] = useState<number | null>(null);
    const [pinningId, setPinningId] = useState<number | null>(null);

    const load = async () => {
        setLoading(true);
        const result = await getRelatedCases(caseId);
        const manual = result?.manual ?? [];
        const automatic = result?.automatic ?? [];
        setManualList(manual);
        setAutoList(automatic);
        // Rozet sayısı iki katmanı birden sayar: kullanıcı için "bu davanın kaç
        // ilişkisi var" sorusunun cevabı bağın elle mi kurulduğuna bakmaz.
        onCountChange?.(manual.length + automatic.length);
        setLoading(false);
    };

    useEffect(() => { load(); }, [caseId]); // eslint-disable-line react-hooks/exhaustive-deps

    const handleDelete = async (relationId: number) => {
        setDeletingId(relationId);
        const ok = await removeCaseRelation(caseId, relationId);
        if (ok) {
            toast.success("Bağlantı kaldırıldı");
            await load();
        } else {
            toast.error("Bağlantı kaldırılamadı");
        }
        setDeletingId(null);
    };

    /** Otomatik öneriyi kalıcı bağa çevirir — kayıt manuel katmana taşınır.
     *  Backend elle bağlanmış kartı otomatik listede tekrar etmediği için satır
     *  yeniden yüklemede kendiliğinden "Sistemin bulduğu"ndan çıkar. */
    const handlePin = async (rc: RelatedCase) => {
        setPinningId(rc.id);
        const result = await addCaseRelation(caseId, {
            target_case_id: rc.id,
            relation_type: rc.relation_type,
            note: rc.match_reason,
        });
        if (result) {
            toast.success("Bağlantı kalıcı hâle getirildi");
            await load();
        } else {
            toast.error("Bağlantı kaydedilemedi");
        }
        setPinningId(null);
    };

    const handleAddRelation = async (targetCaseId: number, relationType: string, note: string | null) => {
        const result = await addCaseRelation(caseId, { target_case_id: targetCaseId, relation_type: relationType, note });
        if (result) {
            toast.success("Dava bağlantısı eklendi");
            await load();
            return true;
        }
        toast.error("Bağlantı eklenemedi");
        return false;
    };

    // ---- Loading ----
    if (loading) {
        return (
            <div className="space-y-3">
                <div className="flex justify-between items-center">
                    <Skeleton className="h-5 w-40" />
                    <Skeleton className="h-8 w-24" />
                </div>
                {[1, 2].map(i => <Skeleton key={i} className="h-24 w-full rounded-none" />)}
            </div>
        );
    }

    // ---- Empty ----
    if (manualList.length === 0 && autoList.length === 0) {
        return (
            <>
                <div className="flex justify-between items-center mb-4">
                    <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                        İlişkili Davalar
                    </h3>
                    <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setAddModalOpen(true)}>
                        <Plus className="w-3.5 h-3.5" />
                        Dava Bağla
                    </Button>
                </div>
                <div className="text-center py-16 border border-dashed rounded-none text-muted-foreground">
                    <Link2 className="w-10 h-10 opacity-20 mx-auto mb-3" />
                    <p className="font-medium text-foreground">İlişkili dava yok</p>
                    <p className="text-sm mt-1 mb-4">
                        Bu dava henüz başka bir davayla ilişkilendirilmemiş.
                    </p>
                    <Button variant="outline" className="gap-2" onClick={() => setAddModalOpen(true)}>
                        <Plus className="w-4 h-4" />
                        Dava Bağla
                    </Button>
                </div>
                <AddRelationModal
                    open={addModalOpen}
                    currentCaseId={caseId}
                    onClose={() => setAddModalOpen(false)}
                    onSave={handleAddRelation}
                />
            </>
        );
    }

    return (
        <>
            {/* Başlık + Bağla butonu */}
            <div className="flex justify-between items-center mb-5">
                <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                        İlişkili Davalar
                    </h3>
                    <Badge variant="secondary" className="text-xs px-2">
                        {manualList.length + autoList.length}
                    </Badge>
                </div>
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setAddModalOpen(true)}>
                    <Plus className="w-3.5 h-3.5" />
                    Dava Bağla
                </Button>
            </div>

            {manualList.length > 0 && (
                <div className="space-y-2.5">
                    {manualList.map(rc => (
                        <RelatedCaseCard
                            key={rc.id}
                            rc={rc}
                            isDeleting={deletingId === rc.relation_id}
                            onNavigate={() => navigate(`/cases/${rc.id}`)}
                            onDelete={() => rc.relation_id && handleDelete(rc.relation_id)}
                        />
                    ))}
                </div>
            )}

            {autoList.length > 0 && (
                <div className={manualList.length > 0 ? "mt-6" : ""}>
                    <div className="flex items-center gap-2 mb-3">
                        <Sparkles className="w-3.5 h-3.5 text-muted-foreground" />
                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                            Sistemin bulduğu
                        </h4>
                        <Badge variant="secondary" className="text-xs px-2">{autoList.length}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mb-3">
                        Eski sistemin TKU numarası ile aynı mahkeme/esas eşleşmesinden türetildi;
                        kayıtlı bir bağlantı değildir.
                    </p>
                    <div className="space-y-2.5">
                        {autoList.map(rc => (
                            <RelatedCaseCard
                                key={rc.id}
                                rc={rc}
                                isPinning={pinningId === rc.id}
                                onNavigate={() => navigate(`/cases/${rc.id}`)}
                                onPin={() => handlePin(rc)}
                            />
                        ))}
                    </div>
                </div>
            )}

            <AddRelationModal
                open={addModalOpen}
                currentCaseId={caseId}
                onClose={() => setAddModalOpen(false)}
                onSave={handleAddRelation}
            />
        </>
    );
};

// =================================================================
// Tekil ilişkili dava kartı
// =================================================================
interface CardProps {
    rc: RelatedCase;
    isDeleting?: boolean;
    isPinning?: boolean;
    onNavigate: () => void;
    onDelete?: () => void;
    onPin?: () => void;
}

const RelatedCaseCard = ({ rc, isDeleting, isPinning, onNavigate, onDelete, onPin }: CardProps) => {
    const ftMeta = getFileTypeMeta(rc.file_type);
    const st = getStatusStyle(rc.status);
    const relationLabel = RELATION_TYPE_LABELS[rc.relation_type] ?? rc.relation_type;
    const isAyniDava = rc.relation_type === AYNI_DAVA;

    return (
        <div className={`group rounded-none border bg-card/60 transition-all overflow-hidden ${
            isAyniDava
                ? "border-[#c47a1e]/50 hover:border-[#c47a1e]"
                : "border-border/60 hover:border-border"
        }`}>
            <div className="p-4 flex flex-col sm:flex-row sm:items-start gap-4">
                {/* Sol: bilgiler */}
                <div className="flex-1 min-w-0 space-y-2">
                    {/* Üst satır: tür + ilişki etiketi + statü */}
                    <div className="flex flex-wrap items-center gap-2">
                        {rc.file_type && (
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold border ${ftMeta.bg} ${ftMeta.color} ${ftMeta.border}`}>
                                {ftMeta.icon}
                                {rc.file_type}
                            </span>
                        )}
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold border ${
                            isAyniDava
                                ? "bg-[#c47a1e]/10 text-[#c47a1e] border-[#c47a1e]/30"
                                : "bg-secondary/40 text-muted-foreground border-border/50"
                        }`}>
                            <Link2 className={`w-3 h-3 ${isAyniDava ? "text-[#c47a1e]" : "text-primary"}`} />
                            {relationLabel}
                        </span>
                        <Badge className={`text-[10px] px-2 py-0.5 border-0 ${st.bg} ${st.text}`}>
                            <span className={`w-1.5 h-1.5 rounded-full mr-1 ${st.dot}`} />
                            {rc.status}
                        </Badge>
                    </div>

                    {/* Esas no + Mahkeme */}
                    <div>
                        <p className="font-bold tabular-nums text-[15px] leading-tight">
                            {rc.esas_no || rc.tracking_no}
                        </p>
                        <p className="text-sm text-muted-foreground mt-0.5 truncate">{rc.court || "Mahkeme belirtilmemiş"}</p>
                    </div>

                    {/* Taraflar */}
                    {rc.parties.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                            {rc.parties.slice(0, 3).map((p, i) => (
                                <span key={i} className="inline-flex items-center gap-1 text-[11px] text-muted-foreground bg-secondary/30 px-2 py-0.5 rounded-full border border-border/40">
                                    <User className="w-2.5 h-2.5" />
                                    {p.name}
                                    <span className="opacity-50">· {p.role}</span>
                                </span>
                            ))}
                        </div>
                    )}

                    {/* Not (elle bağlarda kullanıcının notu) */}
                    {rc.note && (
                        <p className="text-xs text-muted-foreground italic border-l-2 border-primary/30 pl-2.5 mt-1">
                            {rc.note}
                        </p>
                    )}

                    {/* Gerekçe — otomatik ilişkinin hangi kanıttan geldiği.
                        Elle bağlarda gösterilmez, orada gerekçe kullanıcının kendisidir. */}
                    {!rc.is_manual && rc.match_reason && (
                        <p className="text-xs text-muted-foreground border-l-2 border-border pl-2.5 mt-1">
                            {rc.match_reason}
                        </p>
                    )}
                </div>

                {/* Sağ: aksiyon butonları */}
                <div className="flex sm:flex-col gap-2 shrink-0">
                    <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5 h-8 text-xs"
                        onClick={onNavigate}
                    >
                        <ExternalLink className="w-3.5 h-3.5" />
                        Git
                    </Button>
                    {onDelete && (
                        <Button
                            size="sm"
                            variant="ghost"
                            className="gap-1.5 h-8 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive"
                            onClick={onDelete}
                            disabled={isDeleting}
                        >
                            <Trash2 className="w-3.5 h-3.5" />
                            {isDeleting ? "..." : "Sil"}
                        </Button>
                    )}
                    {onPin && (
                        <Button
                            size="sm"
                            variant="ghost"
                            className="gap-1.5 h-8 text-xs"
                            onClick={onPin}
                            disabled={isPinning}
                        >
                            <Pin className="w-3.5 h-3.5" />
                            {isPinning ? "..." : "Kalıcı Bağla"}
                        </Button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default RelatedCasesPanel;
