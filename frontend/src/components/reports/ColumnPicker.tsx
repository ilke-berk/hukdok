import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, GripVertical, Search, X } from "lucide-react";
import {
    DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors,
    type DragEndEvent,
} from "@dnd-kit/core";
import {
    SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { KatalogKolon } from "@/lib/reports";
import { TANIM_LIMITLERI } from "@/lib/reports";
import { Eyebrow } from "@/components/dashboard/primitives";
import { ICON_BTN_CLS, INPUT_CLS, LINK_BTN_CLS } from "./ui";

type ColumnPickerProps = {
    kolonlar: KatalogKolon[];
    secili: string[];
    varsayilan: string[];
    onChange: (next: string[]) => void;
};

const TIP_KISA: Record<KatalogKolon["tip"], string> = {
    metin: "abc", liste: "liste", tarih: "tarih", sayi: "123", para: "₺", mantik: "e/h",
};

/**
 * Katalog kolonları (arama + checkbox) ve seçilenlerin sıralı listesi (sürükle-bırak
 * dnd-kit + ↑↓ düğmeleri: klavye/erişilebilirlik ve jsdom testi için ikinci yol).
 * Seçim sırası = rapordaki kolon sırası (§2.1 "kolonlar sıralıdır").
 */
export function ColumnPicker({ kolonlar, secili, varsayilan, onChange }: ColumnPickerProps) {
    const [arama, setArama] = useState("");

    const etiketOf = useMemo(() => new Map(kolonlar.map(k => [k.anahtar, k])), [kolonlar]);

    const gorunen = useMemo(() => {
        const q = arama.trim().toLocaleLowerCase("tr-TR");
        if (!q) return kolonlar;
        return kolonlar.filter(k =>
            k.etiket.toLocaleLowerCase("tr-TR").includes(q) || k.anahtar.toLowerCase().includes(q),
        );
    }, [kolonlar, arama]);

    const tavanDolu = secili.length >= TANIM_LIMITLERI.kolon_max;

    const toggle = (anahtar: string) => {
        if (secili.includes(anahtar)) onChange(secili.filter(k => k !== anahtar));
        else if (!tavanDolu) onChange([...secili, anahtar]);
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
        <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
                <Eyebrow>Kolonlar</Eyebrow>
                <div className="flex items-center gap-3">
                    <button
                        type="button"
                        className={LINK_BTN_CLS}
                        onClick={() => onChange(varsayilan.filter(k => etiketOf.has(k)))}
                        disabled={varsayilan.length === 0}
                    >
                        Varsayılanları seç
                    </button>
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

            <div
                role="group"
                aria-label="Katalog kolonları"
                className="max-h-56 overflow-y-auto border border-[var(--border)] bg-[var(--bg)] divide-y divide-[var(--border)]"
            >
                {gorunen.length === 0 ? (
                    <div className="px-3 py-4 text-[12px] text-[var(--fg-subtle)]">Aramaya uyan kolon yok.</div>
                ) : (
                    gorunen.map(k => {
                        const isaretli = secili.includes(k.anahtar);
                        const kilitli = !isaretli && tavanDolu;
                        return (
                            <label
                                key={k.anahtar}
                                className={[
                                    "flex items-center gap-2.5 px-3 py-1.5 text-[12px] cursor-pointer",
                                    kilitli ? "opacity-50 cursor-not-allowed" : "hover:bg-[var(--bg-elevated)]",
                                ].join(" ")}
                            >
                                <input
                                    type="checkbox"
                                    checked={isaretli}
                                    disabled={kilitli}
                                    onChange={() => toggle(k.anahtar)}
                                    aria-label={k.etiket}
                                    className="accent-[var(--brand)]"
                                />
                                <span className="flex-1 min-w-0 truncate text-[var(--fg)]">{k.etiket}</span>
                                {k.turetilmis && (
                                    <span
                                        title="Türetilmiş kolon — filtrelenemez, sıralanamaz"
                                        className="font-mono text-[9px] tracking-[0.12em] uppercase text-[var(--fg-subtle)] border border-[var(--border)] px-1"
                                    >
                                        türetilmiş
                                    </span>
                                )}
                                <span className="font-mono text-[9.5px] tracking-[0.08em] text-[var(--fg-subtle)] shrink-0">
                                    {TIP_KISA[k.tip] ?? k.tip}
                                </span>
                            </label>
                        );
                    })
                )}
            </div>

            <div className="flex items-center justify-between">
                <Eyebrow>Seçili · sıra</Eyebrow>
                <span className="font-mono text-[10px] tracking-[0.1em] text-[var(--fg-subtle)] tabular-nums">
                    {secili.length} / {TANIM_LIMITLERI.kolon_max}
                </span>
            </div>

            {secili.length === 0 ? (
                <div className="border border-dashed border-[var(--border)] px-3 py-3 text-[12px] text-[var(--fg-subtle)]">
                    Henüz kolon seçilmedi — rapor için en az bir kolon gerekir.
                </div>
            ) : (
                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                    <SortableContext items={secili} strategy={verticalListSortingStrategy}>
                        <ol aria-label="Seçili kolonlar" className="flex flex-col gap-1">
                            {secili.map((anahtar, i) => (
                                <SeciliKolon
                                    key={anahtar}
                                    anahtar={anahtar}
                                    etiket={etiketOf.get(anahtar)?.etiket ?? anahtar}
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
            )}
        </div>
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
