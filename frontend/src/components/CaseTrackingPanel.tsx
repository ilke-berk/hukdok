import { useState, useEffect } from "react";
import {
    useCases, CaseTrackingUpdate, CaseStageDecisions, CASE_STAGE_DECISIONS_ERROR,
} from "@/hooks/useCases";
import { useConfig, ConfigItem } from "@/hooks/useConfig";
import {
    STAGES, STAGE_KEYS, STAGE_FIELDS, PANEL_FIELDS, EVENT_FIELDS, DECISION_STAGE_BY_PANEL_KEY,
    suggestedStageFromDecisions, PanelListKey, FieldDef,
    TrackingDraft, initTrackingDraft, setDraftField, dirtyKeys, isDirty,
    rebaseDraft, buildPatch, commitDraft, normalizeMoney,
} from "@/lib/trackingDraft";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { CheckCircle2, Circle, ChevronRight, Save, Info, AlertTriangle } from "lucide-react";

const inputCls = "w-full px-3 py-2 text-sm rounded-lg border bg-background border-border focus:border-primary focus:outline-none";

const trTarih = (v: unknown) => (v ? new Date(v as string).toLocaleDateString("tr-TR") : null);

/**
 * `dogrulama_durumu` rozeti — tahmin yasağının ekran karşılığı (G062).
 *
 * Kullanıcı "bu bilgi nereden geldi"yi görmeden karara güvenmemeli. Lokal
 * ölçüm (2026-08-19 aktarımı): 3.604 satır TURETILDI, 1.367 satır BELIRSIZ —
 * hiçbiri UYAP/BELGE değil, yani rozet bugün ÇOĞUNLUKLA uyarı basacak.
 */
const DAMGA_STILI: Record<string, string> = {
    UYAP:      "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
    BELGE:     "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
    TURETILDI: "bg-muted text-muted-foreground border-border",
    BELIRSIZ:  "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30",
};
const DAMGA_ETIKETI: Record<string, string> = {
    UYAP: "UYAP", BELGE: "Belge", TURETILDI: "Türetildi", BELIRSIZ: "Belirsiz",
};

interface Props {
    caseId: number;
    caseData: Record<string, unknown>;
    onRefresh: () => void;
    /** Panelde kaydedilmemiş değişiklik olup olmadığını üst bileşene bildirir
     *  (sekme değişiminde ayrılma koruması için). */
    onDirtyChange?: (dirty: boolean) => void;
}

const CaseTrackingPanel = ({ caseId, caseData, onRefresh, onDirtyChange }: Props) => {
    const { updateCaseTracking, getCaseStageDecisions } = useCases();
    const {
        fileStatuses,
        localDecisions, appealDecisions, cassationDecisions, revisionDecisions,
        eventTypes, judgmentRoles,
    } = useConfig();
    const [saving, setSaving] = useState(false);

    // Select seçenekleri — resmî kapalı listeler (karar listeleri G060/G061;
    // belgeleme listeleri G103/G105, panele G106'da bağlandı).
    // Sıra = resmi havuz sırası (backend sequence ile sıralı döner).
    const configLists: Record<PanelListKey, ConfigItem[]> = {
        local_decisions: localDecisions,
        appeal_decisions: appealDecisions,
        cassation_decisions: cassationDecisions,
        revision_decisions: revisionDecisions,
        event_types: eventTypes,
        judgment_roles: judgmentRoles,
    };

    const currentStage = (caseData.case_stage as string) ?? null;
    const currentIdx   = currentStage ? STAGE_KEYS.indexOf(currentStage) : -1;

    // Seçili aşama (yalnız görünüm — taslağa dokunmaz)
    const [selectedKey, setSelectedKey] = useState<string>(currentStage ?? "KARAR");

    // Aşama geçiş onay dialogu
    const [stageDialog, setStageDialog] = useState<{ key: string; label: string } | null>(null);
    const [stageNote, setStageNote]     = useState("");

    // ── Aşama/karar tarihçesi (SALT OKUNUR, G072 route'u) ───────────────────
    // Kaydetme akışına karışmaz: taslağın parçası değil, ayrı okuma.
    const [tarihce, setTarihce] = useState<CaseStageDecisions | null>(null);
    const [tarihceHatasi, setTarihceHatasi] = useState<string | null>(null);

    useEffect(() => {
        let iptal = false;
        setTarihce(null);
        setTarihceHatasi(null);
        getCaseStageDecisions(caseId)
            .then(sonuc => { if (!iptal) setTarihce(sonuc); })
            .catch(hata => {
                if (!iptal) setTarihceHatasi(hata instanceof Error ? hata.message : CASE_STAGE_DECISIONS_ERROR);
            });
        return () => { iptal = true; };
    }, [caseId, getCaseStageDecisions]);

    /** Panel aşamasının karar satırları — backend zaten sira_no sırasında döndürür. */
    const asamaSatirlari = (panelKey: string) => {
        const etiket = DECISION_STAGE_BY_PANEL_KEY[panelKey];
        if (!etiket || !tarihce) return [];
        return tarihce.decisions.filter(d => d.stage === etiket);
    };

    // ── Panel geneli TEK taslak: tüm aşamaların alanları + dosya_son_durumu ──
    const [draft, setDraft] = useState<TrackingDraft>(() => initTrackingDraft(caseData));
    const dirty = isDirty(draft);
    const dirtyCount = dirtyKeys(draft).length;

    // caseData yenilenince (refresh, aşama geçişi) baseline tazelenir;
    // kaydedilmemiş değişiklikler rebaseDraft içinde KORUNUR.
    useEffect(() => {
        setDraft(prev => rebaseDraft(prev, caseData));
    }, [caseData]);

    // Ayrılma koruması: üst bileşene dirty bildir + sayfa kapanışında uyar
    useEffect(() => {
        onDirtyChange?.(dirty);
    }, [dirty, onDirtyChange]);
    useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);

    useEffect(() => {
        if (!dirty) return;
        const handler = (e: BeforeUnloadEvent) => {
            e.preventDefault();
            e.returnValue = "";
        };
        window.addEventListener("beforeunload", handler);
        return () => window.removeEventListener("beforeunload", handler);
    }, [dirty]);

    const selectedIdx  = STAGE_KEYS.indexOf(selectedKey);
    // Aşama BİLİNMİYORSA hiçbir aşama "gelinmemiş" sayılamaz (G075). `case_stage`
    // yalnız kullanıcı "Bu Aşamaya Geç" dediğinde yazılıyor ve lokal kopyada
    // 14.345 aktif kartın 14.344'ünde BOŞ → kapı `currentIdx = -1` ile her
    // aşamada kapalı kalıyordu: panel 2.074 yerel + 1.159 istinaf + 448 temyiz
    // künyesini ne gösteriyor ne düzelttiriyordu. Bilinmeyen aşamayı "bu
    // aşamaya gelinmedi" diye okumak da bir İDDİADIR; bilmiyorsak kilitlemeyiz.
    const stageBilinmiyor = !currentStage;
    const isReached    = stageBilinmiyor || selectedIdx <= currentIdx;
    const fields       = STAGE_FIELDS[selectedKey] ?? [];
    const gecmisKararlar = asamaSatirlari(selectedKey);
    const oncekiEsaslar  = tarihce?.onceki_esaslar ?? [];
    // Aşama boşken karar kayıtlarından türeyen ÖNERİ (yazmaz — kullanıcı onaylar)
    const onerilenAsama  = stageBilinmiyor
        ? suggestedStageFromDecisions((tarihce?.decisions ?? []).map(d => d.stage))
        : null;

    // Timeline'a tıklanınca: yalnız görünüm değişir, taslak sıfırlanMAZ
    const handleStageClick = (key: string) => setSelectedKey(key);

    const setField = (key: string, val: string | null) => {
        setDraft(prev => setDraftField(prev, key, val));
    };

    const fieldValue = (key: string) => draft.values[key] ?? "";

    /** Tek alan bloğu (etiket + kontrol). Aşama alanları ile aşamadan bağımsız
     *  alanlar AYNI kontrolü kullansın diye ayrıldı — iki kopya iki davranış olurdu. */
    const renderField = (f: FieldDef) => (
        <div key={f.key} className={f.wide ? "sm:col-span-2" : ""}>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                {f.label}
            </label>
            {f.type === "date" && (
                <input type="date"
                    value={fieldValue(f.key)}
                    onChange={e => setField(f.key, e.target.value)}
                    className={inputCls} />
            )}
            {f.type === "text" && (
                <input type="text"
                    value={fieldValue(f.key)}
                    onChange={e => setField(f.key, e.target.value)}
                    className={inputCls} />
            )}
            {f.type === "money" && (
                <input type="text" inputMode="decimal"
                    placeholder="150000 veya 1.500,25"
                    value={fieldValue(f.key)}
                    onChange={e => setField(f.key, e.target.value)}
                    onBlur={e => setField(f.key, normalizeMoney(e.target.value))}
                    className={inputCls} />
            )}
            {f.type === "select" && (() => {
                // optionsFrom → resmî kapalı liste (config); yoksa gömülü options
                // (karar_turu/karar_lehine — davranışları birebir korunur).
                const fromConfig = f.optionsFrom ? configLists[f.optionsFrom].map(o => o.name) : null;
                const names = fromConfig ?? f.options ?? [];
                const value = fieldValue(f.key);
                // Kayıtlı değer listeden çıkarılmışsa KAYBOLMASIN: geçici seçenek
                // olarak eklenir. Liste boşken (yüklenemedi/boş doğdu) "liste dışı"
                // damgası vurulmaz — closedListState "unknown" kuralının select
                // karşılığı (caseCardFields.ts, G048).
                const missing = fromConfig !== null && value !== "" && !fromConfig.includes(value);
                const offList = missing && fromConfig.length > 0;
                return (
                    <select
                        value={value}
                        onChange={e => setField(f.key, e.target.value)}
                        className={inputCls}>
                        <option value="">Seçiniz</option>
                        {missing && (
                            <option value={value}>{offList ? `${value} (liste dışı)` : value}</option>
                        )}
                        {names.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                );
            })()}
            {f.type === "textarea" && (
                <textarea rows={2}
                    value={fieldValue(f.key)}
                    onChange={e => setField(f.key, e.target.value)}
                    className={`${inputCls} resize-none`} />
            )}
        </div>
    );

    // Tek Kaydet: yalnız değişen alanlar PATCH'lenir (boşaltılan alan null → silinir)
    const saveAll = async () => {
        const patch = buildPatch(draft);
        if (Object.keys(patch).length === 0) return;
        setSaving(true);
        const ok = await updateCaseTracking(caseId, patch as CaseTrackingUpdate);
        setSaving(false);
        if (ok) {
            setDraft(prev => commitDraft(prev));
            toast.success("Takip bilgileri kaydedildi");
            onRefresh();
        } else toast.error("Güncelleme başarısız");
    };

    // Aşama geçişi — istisna: dialog onaylı, anlık (CaseStageLog olayı)
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

            {/* ── Kaydedilmemiş değişiklik çubuğu — panel geneli tek Kaydet ── */}
            {dirty && (
                <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2.5">
                    <div className="flex items-center gap-2 min-w-0">
                        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                        <Badge className="bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30 shrink-0">
                            Kaydedilmemiş
                        </Badge>
                        <span className="text-xs text-muted-foreground truncate">
                            {dirtyCount} alan değişti — kaydetmeden ayrılırsanız kaybolur.
                        </span>
                    </div>
                    <Button size="sm" onClick={saveAll} disabled={saving} className="shrink-0 gap-1">
                        <Save className="w-3.5 h-3.5" />
                        {saving ? "Kaydediliyor…" : "Kaydet"}
                    </Button>
                </div>
            )}

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

                    {/* ── Aşama önerisi (G075) ──
                        Aşama boş ama karar kaydı VAR: "temyiz kararı olan dosya en az
                        temyiz aşamasındadır" kayıttan okunan bir alt sınırdır. Kolona
                        SESSİZCE yazmıyoruz — değer kullanıcının onayıyla, mevcut aşama
                        geçişi yolundan (CaseStageLog kaydı üreterek) giriyor. */}
                    {stageBilinmiyor && onerilenAsama && (
                        <div className="mt-3 flex items-center gap-2 flex-wrap rounded-lg border border-primary/25 bg-primary/5 px-3 py-2">
                            <Info className="w-3.5 h-3.5 text-primary shrink-0" />
                            <span className="text-xs text-muted-foreground">
                                Karar kayıtlarına göre bu dosya en az{" "}
                                <span className="font-semibold text-foreground">
                                    {STAGES.find(s => s.key === onerilenAsama)?.label}
                                </span>{" "}
                                aşamasında görünüyor.
                            </span>
                            <Button
                                size="sm" variant="outline"
                                className="h-6 px-2 text-[11px] ml-auto"
                                onClick={() => openStageDialog(STAGES[STAGE_KEYS.indexOf(onerilenAsama)])}
                            >
                                Aşamayı ayarla
                            </Button>
                        </div>
                    )}
                    {/* ── Önceki esas numaraları (SALT OKUNUR, G072) ──
                        Görevsizlik/yetkisizlik sonrası numara değişir; eski numara
                        kayıt değeridir (aktarımda 517 satır) ve bugüne kadar hiçbir
                        ekranda yoktu. `cases.esas_no` GÜNCEL olanı taşır, bu liste
                        yalnız artık kullanılmayanları. */}
                    {oncekiEsaslar.length > 0 && (
                        <div className="mt-4 pt-3 border-t border-primary/15">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1.5">
                                Önceki Esas Numaraları
                            </p>
                            <div className="flex flex-wrap gap-x-4 gap-y-1">
                                {oncekiEsaslar.map(e => (
                                    <span key={e.id} className="text-sm">
                                        <span className="font-medium">{e.esas_no}</span>
                                        {e.court && <span className="text-muted-foreground"> · {e.court}</span>}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* ── Aşamadan bağımsız takip alanları — taslağın parçası ──
                        Arabuluculuk davanın ÖN aşaması, arşiv KAPANIŞ olayı;
                        `dosya_son_durumu` ile birlikte hiçbir aşama sekmesine ait
                        değiller (G073 yerleşim kararı). */}
                    <div className="mt-4 pt-3 border-t border-primary/15">
                        <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1.5">Dosya Son Durumu</p>
                        <select
                            className={inputCls}
                            value={fieldValue("dosya_son_durumu")}
                            onChange={e => setField("dosya_son_durumu", e.target.value)}
                        >
                            <option value="">— Seçiniz —</option>
                            {fileStatuses.map(opt => (
                                <option key={opt.code} value={opt.name}>{opt.name}</option>
                            ))}
                        </select>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-4 mt-4">
                            {PANEL_FIELDS.map(renderField)}
                        </div>
                    </div>

                    {/* ── Belgeleme olayı alanları (G103 → G106) ──
                        Değer TEK SLOT — güncel kademedeki hükmü anlatır; aşama
                        sekmesine gömülmez (sekme "aşama başına değer" iddiası
                        doğururdu). Karar dropdown'larının bileşen deseni birebir
                        (renderField select yolu: Seçiniz + liste dışı damgası). */}
                    <div className="mt-4 pt-3 border-t border-primary/15">
                        <p
                            className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1"
                            title="Değerler dosyanın güncel kademesindeki hükme göredir; kademe değişince burada güncellenir."
                        >
                            Belgeleme Olayı
                        </p>
                        <p className="text-[11px] text-muted-foreground mb-2">
                            Değerler güncel kademedeki hükme göredir; kademe değişince burada güncellenir.
                        </p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
                            {EVENT_FIELDS.map(renderField)}
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
                            const stageDirty = (STAGE_FIELDS[stage.key] ?? []).some(f => dirtyKeys(draft).includes(f.key));
                            // Sekmeli görünümün bedeli: kullanıcı diğer aşamada karar
                            // olduğunu bilmezdi. Sayaç bunu görünür kılar (G074).
                            const kararSayisi = asamaSatirlari(stage.key).length;

                            return (
                                <div key={stage.key} className="flex items-center">
                                    <button
                                        type="button"
                                        onClick={() => handleStageClick(stage.key)}
                                        className="flex flex-col items-center gap-1.5 min-w-[56px] sm:min-w-[66px] group relative"
                                    >
                                        {stageDirty && (
                                            <span className="absolute -top-0.5 right-1.5 w-2 h-2 rounded-full bg-amber-500" title="Kaydedilmemiş değişiklik" />
                                        )}
                                        {kararSayisi > 0 && (
                                            <span
                                                className="absolute -top-1 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-primary/15 text-primary border border-primary/30 text-[9px] font-bold flex items-center justify-center"
                                                title={`${kararSayisi} kayıtlı karar`}
                                            >
                                                {kararSayisi}
                                            </span>
                                        )}
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
                        {selectedKey !== currentStage && (
                            <Button size="sm" variant="outline"
                                className="h-7 px-3 gap-1 text-xs"
                                onClick={() => openStageDialog(STAGES[selectedIdx])}>
                                <ChevronRight className="w-3.5 h-3.5" />
                                Bu Aşamaya Geç
                            </Button>
                        )}
                    </div>

                    {/* KAPALI — "kapatılmış" bir İDDİADIR: yalnız aşama gerçekten
                        KAPALI ise basılır (aşama bilinmiyorken basılamaz, G075). */}
                    {selectedKey === "KAPALI" && currentStage === "KAPALI" && (
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
                            {fields.map(renderField)}
                        </div>
                    )}

                    {/* ── Bu aşamanın geçmiş kararları (SALT OKUNUR, G072/G074) ──
                        `isReached` kapısının DIŞINDA: tarihçe `case_stage`ten
                        bağımsızdır ve lokal kopyada 14.345 kartın 14.344'ünde
                        `case_stage` BOŞ — kapıya bağlansaydı 4.971 satırın
                        hiçbiri görünmezdi. */}
                    {tarihceHatasi && (
                        <p className="mt-4 text-xs text-amber-700 dark:text-amber-400">{tarihceHatasi}</p>
                    )}
                    {gecmisKararlar.length > 0 && (
                        <div className="mt-5 pt-4 border-t border-border/60">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
                                Bu aşamanın geçmiş kararları ({gecmisKararlar.length})
                            </p>
                            <div className="space-y-2">
                                {gecmisKararlar.map(satir => {
                                    const kunye = [
                                        satir.esas_no && `Esas ${satir.esas_no}`,
                                        satir.karar_no && `Karar ${satir.karar_no}`,
                                        trTarih(satir.karar_tarihi),
                                    ].filter(Boolean).join(" · ");
                                    const ek = [
                                        satir.teblig_tarihi && `Tebliğ: ${trTarih(satir.teblig_tarihi)}`,
                                        satir.basvuran_taraf && `Başvuran: ${satir.basvuran_taraf}`,
                                    ].filter(Boolean).join(" · ");
                                    return (
                                        <div key={satir.id} className="rounded-lg border bg-background/50 px-3 py-2">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">
                                                    {satir.sira_no}
                                                </Badge>
                                                {satir.karar_durumu && (
                                                    <span className="text-sm font-semibold">{satir.karar_durumu}</span>
                                                )}
                                                <Badge
                                                    variant="outline"
                                                    className={`ml-auto text-[10px] px-1.5 py-0 ${DAMGA_STILI[satir.dogrulama_durumu] ?? DAMGA_STILI.BELIRSIZ}`}
                                                    title="Bu satır hangi kaynakla doğrulandı?"
                                                >
                                                    {DAMGA_ETIKETI[satir.dogrulama_durumu] ?? satir.dogrulama_durumu}
                                                </Badge>
                                            </div>
                                            {satir.mahkeme && (
                                                <p className="text-xs text-foreground mt-0.5">{satir.mahkeme}</p>
                                            )}
                                            {kunye && <p className="text-xs text-muted-foreground mt-0.5">{kunye}</p>}
                                            {ek && <p className="text-xs text-muted-foreground mt-0.5">{ek}</p>}
                                            {satir.aciklama && (
                                                <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap">{satir.aciklama}</p>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
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
                        {dirty && (
                            <p className="text-xs text-amber-700 dark:text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
                                Kaydedilmemiş alan değişiklikleriniz bu geçişle kaydedilmez;
                                geçiş sonrası panelde durur, "Kaydet" ile kaydedin.
                            </p>
                        )}
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
