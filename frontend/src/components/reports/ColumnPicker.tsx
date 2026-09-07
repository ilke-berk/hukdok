import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, GripVertical, Search, X } from "lucide-react";
import {
    DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors,
    type DragEndEvent,
} from "@dnd-kit/core";
import {
    SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { KatalogKolon, KolonSeti } from "@/lib/reports";
import { TANIM_LIMITLERI } from "@/lib/reports";
import { Eyebrow } from "@/components/dashboard/primitives";
import { ICON_BTN_CLS, INPUT_CLS, LINK_BTN_CLS } from "./ui";

type ColumnPickerProps = {
    kolonlar: KatalogKolon[];
    secili: string[];
    /** Kaynağın varsayılan kolonları — katalogda "Temel" seti yoksa o adla ilk set olur. */
    varsayilan: string[];
    /** Katalog `kolon_setleri` (§4.2); tık = seçimi setle DEĞİŞTİRİR. */
    setler: KolonSeti[];
    onChange: (next: string[]) => void;
};

const TIP_ETIKETI: Record<KatalogKolon["tip"], string> = {
    metin: "metin", liste: "liste", tarih: "tarih", sayi: "sayı", para: "para", mantik: "evet/hayır",
};

const TEMEL_SET_ADI = "Temel";

/** Sıra bağımsız aynı küme mi (set rozeti "seçili" vurgusu için). */
function ayniKume(a: string[], b: string[]): boolean {
    if (a.length !== b.length) return false;
    const s = new Set(a);
    return b.every(k => s.has(k));
}

/**
 * Kolon seçici (G133 → G139 yan panel gövdesi): üstte hazır setler (`kolon_setleri`, "Temel" =
 * varsayılan), arama, `grup` başlıklı checkbox listesi (grup başlığında "tümünü seç"), altta
 * seçilenlerin sıralı listesi (dnd-kit + ↑↓: klavye/erişilebilirlik ve jsdom testi için ikinci yol).
 * Tip rozeti YOK — tip yalnız satırın `title` ipucunda. Seçim sırası = rapordaki kolon sırası
 * (§2.1 "kolonlar sıralıdır"); set tıklaması sırayı setin sırasına çeker.
 */
export function ColumnPicker({ kolonlar, secili, varsayilan, setler, onChange }: ColumnPickerProps) {
    const [arama, setArama] = useState("");

    const kolonOf = useMemo(() => new Map(kolonlar.map(k => [k.anahtar, k])), [kolonlar]);

    // Katalogdaki setler (geçersiz anahtarlar düşer); "Temel" yoksa varsayılan kolonlarla başa eklenir.
    const hazirSetler = useMemo(() => {
        const temiz = setler
            .map(s => ({ ad: s.ad, kolonlar: s.kolonlar.filter(k => kolonOf.has(k)) }))
            .filter(s => s.kolonlar.length > 0);
        if (temiz.some(s => s.ad === TEMEL_SET_ADI)) return temiz;
        const temel = varsayilan.filter(k => kolonOf.has(k));
        return temel.length > 0 ? [{ ad: TEMEL_SET_ADI, kolonlar: temel }, ...temiz] : temiz;
    }, [setler, varsayilan, kolonOf]);

    const gorunen = useMemo(() => {
        const q = arama.trim().toLocaleLowerCase("tr-TR");
        if (!q) return kolonlar;
        return kolonlar.filter(k =>
            k.etiket.toLocaleLowerCase("tr-TR").includes(q) || k.anahtar.toLowerCase().includes(q),
        );
    }, [kolonlar, arama]);

    // Gruplar katalogdaki ilk görülme sırasıyla; aramada boş kalan grup çıkmaz.
    const gruplar = useMemo(() => {
        const sira: string[] = [];
        const uyeler = new Map<string, KatalogKolon[]>();
        for (const k of gorunen) {
            const g = k.grup || "Diğer";
            if (!uyeler.has(g)) {
                sira.push(g);
                uyeler.set(g, []);
            }
            uyeler.get(g)!.push(k);
        }
        return sira.map(ad => ({ ad, kolonlar: uyeler.get(ad)! }));
    }, [gorunen]);

    const seciliKume = useMemo(() => new Set(secili), [secili]);
    const tavanDolu = secili.length >= TANIM_LIMITLERI.kolon_max;

    const toggle = (anahtar: string) => {
        if (seciliKume.has(anahtar)) onChange(secili.filter(k => k !== anahtar));
        else if (!tavanDolu) onChange([...secili, anahtar]);
    };

    /** Grup başlığı: hepsi seçiliyse grubu kaldır; değilse eksikleri tavana kadar ekle. */
    const grupToggle = (uyeler: KatalogKolon[]) => {
        const anahtarlar = uyeler.map(k => k.anahtar);
        const hepsi = anahtarlar.every(k => seciliKume.has(k));
        if (hepsi) {
            const kume = new Set(anahtarlar);
            onChange(secili.filter(k => !kume.has(k)));
            return;
        }
        const yer = TANIM_LIMITLERI.kolon_max - secili.length;
        const eksik = anahtarlar.filter(k => !seciliKume.has(k)).slice(0, Math.max(0, yer));
        if (eksik.length > 0) onChange([...secili, ...eksik]);
    };

    const tasi = (index: number, yon: -1 | 1) => {
        const hedef = index + yon;
        if (hedef < 0 || hedef >= secili.length) return;
        onChange(arrayMove(secili, index, hedef));
    };

    const sensors = useSensors(
        useSensor(PointerSensor),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
    );

    const onDragEnd = (e: DragEndEvent) => {
        const { active, over } = e;
        if (!over || active.id === over.id) return;
        const from = secili.indexOf(String(active.id));
        const to = secili.indexOf(String(over.id));
        if (from === -1 || to === -1) return;
        onChange(arrayMove(secili, from, to));
    };

    return (
        <div className="flex flex-col gap-4 min-h-0">
            {/* Hazır setler */}
            {hazirSetler.length > 0 && (
                <div className="flex flex-col gap-2">
                    <Eyebrow>Hazır setler</Eyebrow>
                    <div role="group" aria-label="Kolon setleri" className="flex flex-wrap gap-1.5">
                        {hazirSetler.map(s => {
                            const aktif = ayniKume(s.kolonlar, secili);
                            return (
                                <button
                                    key={s.ad}
                                    type="button"
                                    data-kolon-seti={s.ad}
                                    aria-pressed={aktif}
                                    onClick={() => onChange([...s.kolonlar])}
                                    title={`${s.kolonlar.length} kolon — seçimi bu setle değiştirir`}
                                    className={[
                                        "px-2.5 py-1 text-[11.5px] border rounded-[3px] transition-colors",
                                        aktif
                                            ? "border-[var(--brand)] bg-[var(--brand-soft)] text-[var(--brand)]"
                                            : "border-[var(--border)] bg-[var(--bg)] text-[var(--fg-muted)] hover:text-[var(--fg)] hover:border-[var(--fg-muted)]",
                                    ].join(" ")}
                                >
                                    {s.ad}
                                    <span className="ml-1 font-mono text-[9.5px] tabular-nums opacity-70">{s.kolonlar.length}</span>
                                </button>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Arama */}
            <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--fg-subtle)] pointer-events-none" />
                <input
                    type="search"
                    value={arama}
                    onChange={e => setArama(e.target.value)}
                    placeholder="Kolon ara…"
                    aria-label="Kolon ara"
                    className={`${INPUT_CLS} pl-8`}
                />
            </div>

            {/* Gruplu liste */}
            <div
                role="group"
                aria-label="Katalog kolonları"
                className="max-h-[38vh] overflow-y-auto border border-[var(--border)] bg-[var(--bg)]"
            >
                {gruplar.length === 0 ? (
                    <div className="px-3 py-4 text-[12px] text-[var(--fg-subtle)]">Aramaya uyan kolon yok.</div>
                ) : (
                    gruplar.map(g => (
                        <GrupBolumu
                            key={g.ad}
                            ad={g.ad}
                            kolonlar={g.kolonlar}
                            seciliKume={seciliKume}
                            tavanDolu={tavanDolu}
                            onToggle={toggle}
                            onGrupToggle={() => grupToggle(g.kolonlar)}
                        />
                    ))
                )}
            </div>

            {/* Seçili · sıra */}
            <div className="flex items-center justify-between">
                <Eyebrow>Seçili · sıra</Eyebrow>
                <div className="flex items-center gap-3">
                    <span className="font-mono text-[10px] tracking-[0.1em] text-[var(--fg-subtle)] tabular-nums">
                        {secili.length} / {TANIM_LIMITLERI.kolon_max}
                    </span>
                    <button
                        type="button"
                        className={LINK_BTN_CLS}
                        onClick={() => onChange([])}
                        disabled={secili.length === 0}
                    >
                        Temizle
                    </button>
                </div>
            </div>

            {secili.length === 0 ? (
                <div className="border border-dashed border-[var(--border)] px-3 py-3 text-[12px] text-[var(--fg-subtle)]">
                    Kolon seçilmedi — rapor için en az bir kolon gerekir.
                </div>
            ) : (
                <div className="max-h-[30vh] overflow-y-auto">
                    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                        <SortableContext items={secili} strategy={verticalListSortingStrategy}>
                            <ol aria-label="Seçili kolonlar" className="flex flex-col gap-1">
                                {secili.map((anahtar, i) => (
                                    <SeciliKolon
                                        key={anahtar}
                                        anahtar={anahtar}
                                        etiket={kolonOf.get(anahtar)?.etiket ?? anahtar}
                                        sira={i + 1}
                                        ilk={i === 0}
                                        son={i === secili.length - 1}
                                        onYukari={() => tasi(i, -1)}
                                        onAsagi={() => tasi(i, 1)}
                                        onKaldir={() => toggle(anahtar)}
                                    />
                                ))}
                            </ol>
                        </SortableContext>
                    </DndContext>
                </div>
            )}
        </div>
    );
}

type GrupBolumuProps = {
    ad: string;
    kolonlar: KatalogKolon[];
    seciliKume: Set<string>;
    tavanDolu: boolean;
    onToggle: (anahtar: string) => void;
    onGrupToggle: () => void;
};

/** Bir grup: başlıkta "tümünü seç" (kısmi seçimde indeterminate), altında üyeler. */
function GrupBolumu({ ad, kolonlar, seciliKume, tavanDolu, onToggle, onGrupToggle }: GrupBolumuProps) {
    const seciliSayisi = kolonlar.filter(k => seciliKume.has(k.anahtar)).length;
    const hepsi = seciliSayisi === kolonlar.length;
    const kismi = seciliSayisi > 0 && !hepsi;
    const grupRef = useRef<HTMLInputElement>(null);
    useEffect(() => {
        if (grupRef.current) grupRef.current.indeterminate = kismi;
    }, [kismi]);

    return (
        <section data-kolon-grubu={ad} className="border-b border-[var(--border)] last:border-b-0">
            <label className="flex items-center gap-2.5 px-3 py-1.5 bg-[var(--bg-elevated)] cursor-pointer sticky top-0">
                <input
                    ref={grupRef}
                    type="checkbox"
                    checked={hepsi}
                    disabled={!hepsi && tavanDolu}
                    onChange={onGrupToggle}
                    aria-label={`${ad} tümünü seç`}
                    className="accent-[var(--brand)]"
                />
                <span className="flex-1 font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] font-semibold">
                    {ad}
                </span>
                <span className="font-mono text-[9.5px] tabular-nums text-[var(--fg-subtle)]">
                    {seciliSayisi}/{kolonlar.length}
                </span>
            </label>
            {kolonlar.map(k => {
                const isaretli = seciliKume.has(k.anahtar);
                const kilitli = !isaretli && tavanDolu;
                // G137 sonrası türetilmiş kolonların bir kısmı filtrelenebilir (taraf kolonları, dava_sayisi);
                // ipucu bayrağa değil, katalogdaki gerçek yeteneklere bakar.
                const kisitlar = [
                    !k.filtrelenebilir ? "filtrelenemez" : null,
                    !k.siralanabilir ? "sıralanamaz" : null,
                ].filter(Boolean);
                const kisitMetni = kisitlar.length ? ` (${kisitlar.join(", ")})` : "";
                const ek = k.turetilmis ? ` · türetilmiş${kisitMetni}` : kisitMetni ? ` ·${kisitMetni}` : "";
                const ipucu = `${k.etiket} · ${TIP_ETIKETI[k.tip] ?? k.tip}${ek}`;
                return (
                    <label
                        key={k.anahtar}
                        title={ipucu}
                        className={[
                            "flex items-center gap-2.5 pl-7 pr-3 py-1.5 text-[12px] cursor-pointer",
                            kilitli ? "opacity-50 cursor-not-allowed" : "hover:bg-[var(--bg-elevated)]",
                        ].join(" ")}
                    >
                        <input
                            type="checkbox"
                            checked={isaretli}
                            disabled={kilitli}
                            onChange={() => onToggle(k.anahtar)}
                            aria-label={k.etiket}
                            className="accent-[var(--brand)]"
                        />
                        <span className="flex-1 min-w-0 truncate text-[var(--fg)]">{k.etiket}</span>
                    </label>
                );
            })}
        </section>
    );
}

type SeciliKolonProps = {
    anahtar: string;
    etiket: string;
    sira: number;
    ilk: boolean;
    son: boolean;
    onYukari: () => void;
    onAsagi: () => void;
    onKaldir: () => void;
};

function SeciliKolon({ anahtar, etiket, sira, ilk, son, onYukari, onAsagi, onKaldir }: SeciliKolonProps) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: anahtar });
    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        zIndex: isDragging ? 2 : undefined,
        position: isDragging ? ("relative" as const) : undefined,
    };
    return (
        <li
            ref={setNodeRef}
            style={style}
            data-kolon={anahtar}
            className={[
                "flex items-center gap-1.5 px-2 py-1 border border-[var(--border)] bg-[var(--bg)] text-[12px]",
                isDragging ? "shadow-[0_6px_18px_-8px_rgba(0,0,0,0.35)]" : "",
            ].join(" ")}
        >
            <button
                type="button"
                {...attributes}
                {...listeners}
                className="cursor-grab text-[var(--fg-subtle)] hover:text-[var(--fg)] touch-none"
                aria-label={`${etiket} sürükle`}
                title="Sürükleyerek sırala"
            >
                <GripVertical className="w-3.5 h-3.5" />
            </button>
            <span className="font-mono text-[9.5px] text-[var(--fg-subtle)] tabular-nums w-5 shrink-0">{sira}.</span>
            <span className="flex-1 min-w-0 truncate text-[var(--fg)]">{etiket}</span>
            <button type="button" className={ICON_BTN_CLS} onClick={onYukari} disabled={ilk} aria-label={`${etiket} yukarı`}>
                <ArrowUp className="w-3 h-3" />
            </button>
            <button type="button" className={ICON_BTN_CLS} onClick={onAsagi} disabled={son} aria-label={`${etiket} aşağı`}>
                <ArrowDown className="w-3 h-3" />
            </button>
            <button type="button" className={ICON_BTN_CLS} onClick={onKaldir} aria-label={`${etiket} kaldır`}>
                <X className="w-3 h-3" />
            </button>
        </li>
    );
}
