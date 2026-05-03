import { useState, useEffect } from "react";
import { useCases, CaseTrackingUpdate } from "@/hooks/useCases";
import { useConfig } from "@/hooks/useConfig";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { CheckCircle2, Circle, ChevronRight, Save, Info } from "lucide-react";

// ── Aşamalar ──────────────────────────────────────────────────────────────────
const STAGES = [
    { key: "KARAR",          label: "Yerel Mahkeme", short: "Yerel" },
    { key: "ISTINAF",        label: "İstinaf",       short: "İst." },
    { key: "TEMYIZ",         label: "Temyiz",        short: "Tem." },
    { key: "KARAR_DUZELTME", label: "K.Düzeltme",   short: "K.Düz." },
    { key: "KESINLESME",     label: "Kesinleşme",   short: "Kes." },
    { key: "KAPALI",         label: "Kapalı",        short: "Kap." },
];
const STAGE_KEYS = STAGES.map(s => s.key);


// ── Her aşamanın alanları ─────────────────────────────────────────────────────
interface FieldDef {
    label: string;
    key: string;
    type: "date" | "text" | "select" | "textarea";
    options?: string[];
    wide?: boolean; // 2 kolon kaplar
}

const STAGE_FIELDS: Record<string, FieldDef[]> = {
    KARAR: [
        { label: "Karar Tarihi",        key: "karar_tarihi",        type: "date" },
        { label: "Tebliğ Tarihi",       key: "karar_teblig_tarihi", type: "date" },
        { label: "Kesinleşme Tarihi",   key: "kesinlesme_tarihi",   type: "date" },
        { label: "Karar Türü",          key: "karar_turu",          type: "select", options: ["KABUL","RED","KISMI_KABUL","FERAGAT","UZLASMA","DUSME"] },
        { label: "Karar Lehine",        key: "karar_lehine",        type: "select", options: ["LEHINE","ALEYHINE","KISMI"] },
        { label: "Karar No",            key: "karar_no",            type: "text" },
        { label: "Açıklama",            key: "karar_aciklama",      type: "textarea", wide: true },
    ],
    ISTINAF: [
        { label: "Başvuru Tarihi",  key: "istinaf_basvuru_tarihi",  type: "date" },
        { label: "Mahkeme",         key: "istinaf_mahkemesi",       type: "text", wide: true },
        { label: "Esas No",         key: "istinaf_esas_no",         type: "text" },
        { label: "Karar No",        key: "istinaf_karar_no",        type: "text" },
        { label: "Karar Tarihi",    key: "istinaf_karar_tarihi",    type: "date" },
        { label: "Karar Durumu",    key: "istinaf_karar_durumu",    type: "select", options: ["ONANMADI","BOZULDU","DÜZELTILEREK_ONANMADI","KISMI_BOZMA","FERAGAT","DUSME"] },
        { label: "Tebliğ Tarihi",   key: "istinaf_teblig_tarihi",   type: "date" },
        { label: "Açıklama",        key: "istinaf_karar_aciklama",  type: "textarea", wide: true },
    ],
    TEMYIZ: [
        { label: "Mahkeme",        key: "temyiz_mahkemesi",        type: "text", wide: true },
        { label: "Karar Tarihi",   key: "temyiz_karar_tarihi",     type: "date" },
        { label: "Esas No",        key: "temyiz_esas_no",          type: "text" },
        { label: "Karar No",       key: "temyiz_karar_no",         type: "text" },
        { label: "Tarih Bilgisi",  key: "temyiz_basvuru_tarihi",   type: "date" },
        { label: "Tebliğ Tarihi",  key: "temyiz_teblig_tarihi",    type: "date" },
        { label: "Temyiz Eden",    key: "temyiz_eden_durumu",      type: "text" },
        { label: "Açıklama",       key: "temyiz_karar_aciklama",   type: "textarea", wide: true },
    ],
    KARAR_DUZELTME: [
        { label: "Kararı Durumu",  key: "karar_duzeltme_durumu",        type: "select", options: ["ONANMADI","BOZULDU","DÜZELTILEREK_ONANMADI","FERAGAT","DUSME"] },
        { label: "Esas No",        key: "karar_duzeltme_esas_no",       type: "text" },
        { label: "Karar No",       key: "karar_duzeltme_karar_no",      type: "text" },
        { label: "Tebliğ Tarihi",  key: "karar_duzeltme_teblig_tarihi", type: "date" },
        { label: "Yeni Esas No / Mahkemesi", key: "yeni_esas_no",       type: "text", wide: true },
        { label: "Karar Tarihi",   key: "karar_duzeltme_tarihi",        type: "date" },
        { label: "Açıklama",       key: "karar_duzeltme_aciklama",      type: "textarea", wide: true },
    ],
    KESINLESME: [
        { label: "Kesinleşme Tarihi", key: "kesinlesme_tarihi", type: "date" },
    ],
    KAPALI: [],
};

const inputCls = "w-full px-3 py-2 text-sm rounded-lg border bg-background border-border focus:border-primary focus:outline-none";

interface Props {
    caseId: number;
    caseData: Record<string, unknown>;
    onRefresh: () => void;
}

const CaseTrackingPanel = ({ caseId, caseData, onRefresh }: Props) => {
    const { updateCaseTracking } = useCases();
    const { fileStatuses } = useConfig();
    const [saving, setSaving] = useState(false);

    const currentStage = (caseData.case_stage as string) ?? null;
    const currentIdx   = currentStage ? STAGE_KEYS.indexOf(currentStage) : -1;

    // Seçili aşama
    const [selectedKey, setSelectedKey] = useState<string>(currentStage ?? "KARAR");

    // Aşama geçiş onay dialogu
    const [stageDialog, setStageDialog] = useState<{ key: string; label: string } | null>(null);
    const [stageNote, setStageNote]     = useState("");

    // Dosya Son Durumu
    const [dosyaSonDurumu, setDosyaSonDurumu] = useState<string | null>(
        (caseData.dosya_son_durumu as string) ?? null
    );
    const [dosyaDirty, setDosyaDirty] = useState(false);

    // caseData değişince dosya son durumunu senkronize et
    useEffect(() => {
        setDosyaSonDurumu((caseData.dosya_son_durumu as string) ?? null);
        setDosyaDirty(false);
    }, [caseData.dosya_son_durumu]);

    const saveDosyaSonDurumu = async (value: string | null) => {
        setSaving(true);
        const ok = await updateCaseTracking(caseId, { dosya_son_durumu: value || null });
        setSaving(false);
        if (ok) {
            toast.success("Dosya son durumu kaydedildi");
            setDosyaDirty(false);
            onRefresh();
        } else toast.error("Güncelleme başarısız");
    };

    // Inline form değerleri (seçili aşamanın alanları)
    const [form, setForm] = useState<Partial<CaseTrackingUpdate>>({});
    const [dirty, setDirty] = useState(false);

    // caseData değişince aktif aşamanın form alanlarını senkronize et
    useEffect(() => {
        const initial: Partial<CaseTrackingUpdate> = {};
        (STAGE_FIELDS[selectedKey] ?? []).forEach(f => {
            initial[f.key as keyof CaseTrackingUpdate] = (caseData[f.key] as string) ?? null;
        });
        setForm(initial);
        setDirty(false);
    }, [caseData, selectedKey]);

    const selectedIdx  = STAGE_KEYS.indexOf(selectedKey);
    const isReached    = selectedIdx <= currentIdx;
    const fields       = STAGE_FIELDS[selectedKey] ?? [];

    // Timeline'a tıklanınca
    const handleStageClick = (key: string) => {
        setSelectedKey(key);
        // Form'u caseData ile doldur
        const initial: Partial<CaseTrackingUpdate> = {};
        (STAGE_FIELDS[key] ?? []).forEach(f => {
            initial[f.key as keyof CaseTrackingUpdate] = (caseData[f.key] as string) ?? null;
        });
        setForm(initial);
        setDirty(false);
    };

    const setField = (key: keyof CaseTrackingUpdate, val: string | null) => {
        setForm(prev => ({ ...prev, [key]: val || null }));
        setDirty(true);
    };

    // Aşama alanlarını kaydet
    const saveFields = async () => {
        setSaving(true);
        const ok = await updateCaseTracking(caseId, form as CaseTrackingUpdate);
        setSaving(false);
        if (ok) {
            toast.success("Kaydedildi");
            setDirty(false);
            onRefresh();
        } else toast.error("Güncelleme başarısız");
    };

    // Aşama geçişi
    const openStageDialog = (stage: typeof STAGES[number]) => {
        if (stage.key === currentStage) return;
        setStageNote("");
        setStageDialog(stage);
    };

    const confirmStage = async () => {
        if (!stageDialog) return;
        setSaving(true);
        const ok = await updateCaseTracking(caseId, {
            case_stage: stageDialog.key,
            note: stageNote || null,
        });
        setSaving(false);
        if (ok) {
            toast.success(`"${stageDialog.label}" aşamasına geçildi`);
            setStageDialog(null);
            onRefresh();
        } else toast.error("Güncelleme başarısız");
    };

    // ── Son Durum özet satırları ────────────────────────────────────────────────
    const sonDurumItems: { label: string; value: string | null | undefined }[] = (() => {
        if (!currentStage) return [];
        const d = caseData;
        const fmt = (v: unknown) => v ? new Date(v as string).toLocaleDateString("tr-TR") : null;
        switch (currentStage) {
            case "KARAR":
                return [
                    { label: "Karar Tarihi",  value: fmt(d.karar_tarihi) },
                    { label: "Tebliğ Tarihi", value: fmt(d.karar_teblig_tarihi) },
                    { label: "Karar Türü",    value: d.karar_turu as string },
                    { label: "Sonuç",         value: d.karar_lehine as string },
                    { label: "Karar No",      value: d.karar_no as string },
                ];
            case "ISTINAF":
                return [
                    { label: "Başvuru",       value: fmt(d.istinaf_basvuru_tarihi) },
                    { label: "Karar Tarihi",  value: fmt(d.istinaf_karar_tarihi) },
                    { label: "Durumu",        value: d.istinaf_karar_durumu as string },
                    { label: "Esas No",       value: d.istinaf_esas_no as string },
                    { label: "Mahkeme",       value: d.istinaf_mahkemesi as string },
                ];
            case "TEMYIZ":
                return [
                    { label: "Başvuru",       value: fmt(d.temyiz_basvuru_tarihi) },
                    { label: "Karar Tarihi",  value: fmt(d.temyiz_karar_tarihi) },
                    { label: "Durumu",        value: d.temyiz_karar_durumu as string },
                    { label: "Esas No",       value: d.temyiz_esas_no as string },
                    { label: "Temyiz Eden",   value: d.temyiz_eden_durumu as string },
                ];
            case "KARAR_DUZELTME":
                return [
                    { label: "Karar Tarihi",  value: fmt(d.karar_duzeltme_tarihi) },
                    { label: "Durumu",        value: d.karar_duzeltme_durumu as string },
                    { label: "Esas No",       value: d.karar_duzeltme_esas_no as string },
                    { label: "Yeni Esas No",  value: d.yeni_esas_no as string },
                ];
            case "KESINLESME":
                return [{ label: "Kesinleşme Tarihi", value: fmt(d.kesinlesme_tarihi) }];
            default:
                return [];
        }
    })().filter(i => i.value);

    return (
        <div className="space-y-4">

            {/* ── Davanın Son Durumu — her zaman görünür ───────────────────── */}
            <Card className="bg-primary/5 border-primary/20">
                <CardContent className="pt-3 pb-4 px-5">
                    <div className="flex items-center gap-2 mb-3">
                        <Info className="w-4 h-4 text-primary shrink-0" />
                        <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Davanın Son Durumu</span>
                        {currentStage ? (
                            <Badge className="ml-auto bg-primary/15 text-primary border-primary/30 text-xs font-bold px-2">
                                {STAGES.find(s => s.key === currentStage)?.label ?? currentStage}
                            </Badge>
                        ) : (
                            <Badge variant="outline" className="ml-auto text-xs text-muted-foreground">Aşama girilmemiş</Badge>
                        )}
                    </div>
                    {sonDurumItems.length > 0 ? (
                        <div className="flex flex-wrap gap-x-6 gap-y-2">
                            {sonDurumItems.map(item => (
                                <div key={item.label}>
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{item.label}</p>
                                    <p className="text-sm font-medium text-foreground">{item.value}</p>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <p className="text-xs text-muted-foreground">
                            {currentStage ? "Bu aşama için henüz veri girilmemiş." : "Takip bilgisi girmek için aşağıdaki zaman çizelgesini kullanın."}
                        </p>
                    )}
                    {/* ── Dosya Son Durumu seçici ── */}
                    <div className="mt-4 pt-3 border-t border-primary/15">
                        <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1.5">Dosya Son Durumu</p>
                        <div className="flex items-center gap-2">
                            <select
                                className={`${inputCls} flex-1`}
                                value={dosyaSonDurumu ?? ""}
                                onChange={e => {
                                    setDosyaSonDurumu(e.target.value || null);
                                    setDosyaDirty(true);
                                }}
                            >
                                <option value="">— Seçiniz —</option>
                                {fileStatuses.map(opt => (
                                    <option key={opt.code} value={opt.name}>{opt.name}</option>
                                ))}
                            </select>
                            {dosyaDirty && (
                                <Button size="sm" onClick={() => saveDosyaSonDurumu(dosyaSonDurumu)} disabled={saving}>
                                    <Save className="w-3.5 h-3.5 mr-1" />Kaydet
                                </Button>
                            )}
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* ── Timeline ─────────────────────────────────────────────────── */}
            <Card className="bg-card/60">
                <CardContent className="pt-3 pb-5 px-4 sm:px-6">
                    <div className="flex items-center gap-0 overflow-x-auto py-3">
                        {STAGES.map((stage, idx) => {
                            const done     = idx < currentIdx;
                            const active   = idx === currentIdx;
                            const future   = idx > currentIdx;
                            const selected = stage.key === selectedKey;

                            return (
                                <div key={stage.key} className="flex items-center">
                                    <button
                                        type="button"
                                        onClick={() => handleStageClick(stage.key)}
                                        className="flex flex-col items-center gap-1.5 min-w-[56px] sm:min-w-[66px] group"
                                    >
                                        <div className={`
                                            w-9 h-9 rounded-full flex items-center justify-center border-2 transition-all
                                            ${done || active ? "bg-primary border-primary text-primary-foreground" : "bg-muted/40 border-border text-muted-foreground"}
                                            ${selected       ? "ring-2 ring-primary/50 ring-offset-2 ring-offset-background scale-110" : "group-hover:scale-105"}
                                        `}>
                                            {done || active
                                                ? <CheckCircle2 className="w-4 h-4" />
                                                : <Circle className="w-4 h-4" />
                                            }
                                        </div>
                                        <span className={`
                                            text-[10px] font-semibold text-center whitespace-nowrap transition-colors
                                            ${selected              ? "text-primary"          : ""}
                                            ${!selected && (done || active) ? "text-foreground" : ""}
                                            ${!selected && future   ? "text-muted-foreground" : ""}
                                        `}>
                                            <span className="hidden sm:inline">{stage.label}</span>
                                            <span className="sm:hidden">{stage.short}</span>
                                        </span>
                                    </button>
                                    {idx < STAGES.length - 1 && (
                                        <div className={`h-0.5 w-4 sm:w-5 flex-shrink-0 mx-0.5 rounded-full ${idx < currentIdx ? "bg-primary" : "bg-border"}`} />
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </CardContent>
            </Card>

            {/* ── Seçili Aşama Detay / Düzenleme ──────────────────────────── */}
            <Card className={`transition-all ${isReached ? "bg-card/60" : "bg-muted/10 border-dashed"}`}>
                <CardContent className="pt-4 pb-5 px-5">

                    {/* Başlık */}
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${isReached ? "bg-primary" : "bg-border"}`} />
                            <span className="text-sm font-bold">
                                {STAGES[selectedIdx]?.label}
                            </span>
                            {currentStage === selectedKey && (
                                <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary border-primary/30 px-1.5 py-0">
                                    Mevcut
                                </Badge>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            {dirty && (
                                <Button size="sm" onClick={saveFields} disabled={saving} className="h-7 px-3 gap-1 text-xs">
                                    <Save className="w-3.5 h-3.5" />
                                    {saving ? "Kaydediliyor…" : "Kaydet"}
                                </Button>
                            )}
                            {selectedKey !== currentStage && (
                                <Button size="sm" variant="outline"
                                    className="h-7 px-3 gap-1 text-xs"
                                    onClick={() => openStageDialog(STAGES[selectedIdx])}>
                                    <ChevronRight className="w-3.5 h-3.5" />
                                    Bu Aşamaya Geç
                                </Button>
                            )}
                        </div>
                    </div>

                    {/* KAPALI */}
                    {selectedKey === "KAPALI" && isReached && (
                        <p className="text-sm text-muted-foreground">Dava kapatılmış.</p>
                    )}

                    {/* Aşamaya gelinmemişse */}
                    {!isReached && (
                        <p className="text-sm text-muted-foreground py-1">
                            Bu aşamaya henüz gelinmedi.
                            {" "}
                            <button className="text-primary underline underline-offset-2"
                                onClick={() => openStageDialog(STAGES[selectedIdx])}>
                                Geçmek için tıkla
                            </button>
                        </p>
                    )}

                    {/* Aşama alanları — inline düzenlenebilir */}
                    {fields.length > 0 && isReached && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
                            {fields.map(f => (
                                <div key={f.key} className={f.wide ? "sm:col-span-2" : ""}>
                                    <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                                        {f.label}
                                    </label>
                                    {f.type === "date" && (
                                        <input type="date"
                                            value={(form[f.key as keyof CaseTrackingUpdate] as string) ?? ""}
                                            onChange={e => setField(f.key as keyof CaseTrackingUpdate, e.target.value)}
                                            className={inputCls} />
                                    )}
                                    {f.type === "text" && (
                                        <input type="text"
                                            value={(form[f.key as keyof CaseTrackingUpdate] as string) ?? ""}
                                            onChange={e => setField(f.key as keyof CaseTrackingUpdate, e.target.value)}
                                            className={inputCls} />
                                    )}
                                    {f.type === "select" && (
                                        <select
                                            value={(form[f.key as keyof CaseTrackingUpdate] as string) ?? ""}
                                            onChange={e => setField(f.key as keyof CaseTrackingUpdate, e.target.value)}
                                            className={inputCls}>
                                            <option value="">Seçiniz</option>
                                            {f.options?.map(o => <option key={o} value={o}>{o}</option>)}
                                        </select>
                                    )}
                                    {f.type === "textarea" && (
                                        <textarea rows={2}
                                            value={(form[f.key as keyof CaseTrackingUpdate] as string) ?? ""}
                                            onChange={e => setField(f.key as keyof CaseTrackingUpdate, e.target.value)}
                                            className={`${inputCls} resize-none`} />
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* ── Aşama Geçiş Onay Dialogu ─────────────────────────────────── */}
            <Dialog open={!!stageDialog} onOpenChange={() => setStageDialog(null)}>
                <DialogContent className="max-w-sm">
                    <DialogHeader>
                        <DialogTitle>Aşamayı Değiştir</DialogTitle>
                    </DialogHeader>
                    <div className="py-3 space-y-4">
                        <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/30 border">
                            <div className="text-center">
                                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Mevcut</p>
                                <p className="text-sm font-semibold">
                                    {currentStage ? STAGES.find(s => s.key === currentStage)?.label : "—"}
                                </p>
                            </div>
                            <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
                            <div className="text-center">
                                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Yeni</p>
                                <p className="text-sm font-bold text-primary">{stageDialog?.label}</p>
                            </div>
                        </div>
                        <div>
                            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                                Not (opsiyonel)
                            </label>
                            <textarea value={stageNote}
                                onChange={e => setStageNote(e.target.value)}
                                rows={2}
                                placeholder="Bu değişiklik hakkında not..."
                                className={`${inputCls} resize-none`} />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setStageDialog(null)} disabled={saving}>İptal</Button>
                        <Button onClick={confirmStage} disabled={saving}>
                            {saving ? "Kaydediliyor…" : "Geç"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
};

export default CaseTrackingPanel;
