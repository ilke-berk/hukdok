import { useMemo } from "react";
import { ArrowDownUp, Filter, Plus, Play, SlidersHorizontal, X } from "lucide-react";
import type { Katalog, KatalogVeriKaynagi, SiralamaYonu } from "@/lib/reports";
import { TANIM_LIMITLERI } from "@/lib/reports";
import { Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";
import { ColumnPicker } from "./ColumnPicker";
import { FilterRow } from "./FilterRow";
import { kaynakIcinBaslangic, yeniSatirId, type FiltreSatiri, type OlusturucuDurumu } from "./builderState";
import { ICON_BTN_CLS, LINK_BTN_CLS, SELECT_CLS } from "./ui";

type ReportBuilderProps = {
    katalog: Katalog;
    durum: OlusturucuDurumu;
    onChange: (next: OlusturucuDurumu) => void;
    onOnizle: () => void;
    /** Tanım geçersizken (kolon yok / eksik filtre) düğme kapalıdır. */
    onizleAktif: boolean;
    onizleniyor: boolean;
    /** Son önizlemeden beri tanım değişti. */
    bayat: boolean;
};

/**
 * Rapor Oluşturucu (sol sütun): veri kaynağı → kolonlar → filtreler → sıralama → Önizle.
 * Sunucuya giden gövde `tanimOlustur(durum)` (builderState.ts) ile kurulur.
 */
export function ReportBuilder({ katalog, durum, onChange, onOnizle, onizleAktif, onizleniyor, bayat }: ReportBuilderProps) {
    const kaynak: KatalogVeriKaynagi | undefined = useMemo(
        () => katalog.veri_kaynaklari.find(k => k.anahtar === durum.veri_kaynagi),
        [katalog, durum.veri_kaynagi],
    );

    const filtrelenebilir = useMemo(
        () => (kaynak?.kolonlar ?? []).filter(k => k.filtrelenebilir && !k.turetilmis),
        [kaynak],
    );
    const siralanabilir = useMemo(
        () => (kaynak?.kolonlar ?? []).filter(k => k.siralanabilir && !k.turetilmis),
        [kaynak],
    );

    const kaynakDegisti = (anahtar: string) => {
        const yeni = katalog.veri_kaynaklari.find(k => k.anahtar === anahtar);
        if (!yeni) return;
        onChange(kaynakIcinBaslangic(yeni));
    };

    const filtreEkle = () => {
        if (durum.filtreler.length >= TANIM_LIMITLERI.filtre_max) return;
        const satir: FiltreSatiri = { id: yeniSatirId(), alan: "", op: "eq" };
        onChange({ ...durum, filtreler: [...durum.filtreler, satir] });
    };

    const filtreGuncelle = (id: string, next: FiltreSatiri) =>
        onChange({ ...durum, filtreler: durum.filtreler.map(f => (f.id === id ? next : f)) });

    const filtreKaldir = (id: string) =>
        onChange({ ...durum, filtreler: durum.filtreler.filter(f => f.id !== id) });

    const siralamaEkle = () => {
        if (durum.siralama.length >= TANIM_LIMITLERI.siralama_max) return;
        onChange({ ...durum, siralama: [...durum.siralama, { alan: "", yon: "asc" }] });
    };

    const siralamaGuncelle = (i: number, alan: string, yon: SiralamaYonu) =>
        onChange({ ...durum, siralama: durum.siralama.map((s, j) => (j === i ? { alan, yon } : s)) });

    const siralamaKaldir = (i: number) =>
        onChange({ ...durum, siralama: durum.siralama.filter((_, j) => j !== i) });

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] uppercase text-[var(--fg)] font-semibold">
                    <SlidersHorizontal className="w-3.5 h-3.5 text-[var(--fg-muted)]" />
                    Rapor Oluşturucu
                </span>
                {bayat && (
                    <span
                        data-testid="bayat-rozeti"
                        className="font-mono text-[9.5px] tracking-[0.12em] uppercase px-1.5 py-0.5 border border-[var(--brand)]/40 text-[var(--brand)] bg-[var(--brand-soft)]"
                    >
                        Önizleme bayat
                    </span>
                )}
            </div>

            {/* Veri kaynağı */}
            <div className="flex flex-col gap-2">
                <label htmlFor="rapor-kaynak">
                    <Eyebrow>Veri kaynağı</Eyebrow>
                </label>
                <select
                    id="rapor-kaynak"
                    value={durum.veri_kaynagi}
                    onChange={e => kaynakDegisti(e.target.value)}
                    className={SELECT_CLS}
                >
                    {katalog.veri_kaynaklari.map(k => (
                        <option key={k.anahtar} value={k.anahtar}>{k.etiket}</option>
                    ))}
                </select>
                {kaynak?.aciklama && (
                    <p className="text-[11px] text-[var(--fg-subtle)] leading-snug">{kaynak.aciklama}</p>
                )}
            </div>

            {/* Kolonlar */}
            {kaynak && (
                <ColumnPicker
                    kolonlar={kaynak.kolonlar}
                    secili={durum.kolonlar}
                    varsayilan={kaynak.varsayilan_kolonlar}
                    onChange={kolonlar => onChange({ ...durum, kolonlar })}
                />
            )}

            {/* Filtreler */}
            <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5">
                        <Filter className="w-3 h-3 text-[var(--fg-subtle)]" />
                        <Eyebrow>Filtreler</Eyebrow>
                    </span>
                    <button
                        type="button"
                        className={LINK_BTN_CLS}
                        onClick={filtreEkle}
                        disabled={!kaynak || durum.filtreler.length >= TANIM_LIMITLERI.filtre_max}
                    >
                        <Plus className="w-3 h-3 inline -mt-0.5 mr-0.5" />
                        Filtre ekle
                    </button>
                </div>
                {durum.filtreler.length === 0 ? (
                    <p className="text-[11px] text-[var(--fg-subtle)]">Filtre yok — tüm kayıtlar.</p>
                ) : (
                    <div className="flex flex-col gap-1.5">
                        {durum.filtreler.map(f => (
                            <FilterRow
                                key={f.id}
                                filtre={f}
                                kolonlar={filtrelenebilir}
                                onChange={next => filtreGuncelle(f.id, next)}
                                onRemove={() => filtreKaldir(f.id)}
                            />
                        ))}
                    </div>
                )}
            </div>

            {/* Sıralama */}
            <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5">
                        <ArrowDownUp className="w-3 h-3 text-[var(--fg-subtle)]" />
                        <Eyebrow>Sıralama</Eyebrow>
                    </span>
                    <button
                        type="button"
                        className={LINK_BTN_CLS}
                        onClick={siralamaEkle}
                        disabled={!kaynak || durum.siralama.length >= TANIM_LIMITLERI.siralama_max}
                    >
                        <Plus className="w-3 h-3 inline -mt-0.5 mr-0.5" />
                        Sıralama ekle
                    </button>
                </div>
                {durum.siralama.length === 0 ? (
                    <p className="text-[11px] text-[var(--fg-subtle)]">Sıralama yok — sunucu varsayılanı.</p>
                ) : (
                    <div className="flex flex-col gap-1.5">
                        {durum.siralama.map((s, i) => (
                            <div key={i} data-testid="siralama-satiri" className="grid grid-cols-[1fr_88px_auto] gap-1.5 items-center">
                                <select
                                    aria-label={`Sıralama alanı ${i + 1}`}
                                    value={s.alan}
                                    onChange={e => siralamaGuncelle(i, e.target.value, s.yon)}
                                    className={SELECT_CLS}
                                >
                                    <option value="">Alan seçiniz</option>
                                    {siralanabilir.map(k => <option key={k.anahtar} value={k.anahtar}>{k.etiket}</option>)}
                                </select>
                                <select
                                    aria-label={`Sıralama yönü ${i + 1}`}
                                    value={s.yon}
                                    onChange={e => siralamaGuncelle(i, s.alan, e.target.value as SiralamaYonu)}
                                    className={SELECT_CLS}
                                >
                                    <option value="asc">Artan</option>
                                    <option value="desc">Azalan</option>
                                </select>
                                <button type="button" className={ICON_BTN_CLS} onClick={() => siralamaKaldir(i)} aria-label={`Sıralama ${i + 1} kaldır`}>
                                    <X className="w-3 h-3" />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <FlowButton
                variant="primary"
                onClick={onOnizle}
                disabled={!onizleAktif || onizleniyor}
                title={onizleAktif ? "Önizlemeyi sunucudan al" : "Önizleme için en az bir kolon seçin ve filtreleri tamamlayın"}
            >
                <Play className="w-3.5 h-3.5" />
                {onizleniyor ? "Önizleniyor…" : "Önizle"}
            </FlowButton>
        </div>
    );
}
