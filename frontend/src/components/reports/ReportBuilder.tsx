import { useMemo } from "react";
import { SlidersHorizontal } from "lucide-react";
import type { Katalog, KatalogVeriKaynagi } from "@/lib/reports";
import { Eyebrow } from "@/components/dashboard/primitives";
import { ColumnPicker } from "./ColumnPicker";
import { kaynakIcinBaslangic, type OlusturucuDurumu } from "./builderState";
import { SELECT_CLS } from "./ui";

type ReportBuilderProps = {
    katalog: Katalog;
    durum: OlusturucuDurumu;
    onChange: (next: OlusturucuDurumu) => void;
};

/**
 * Rapor Oluşturucu (sol sütun): veri kaynağı → kolonlar. G138: filtreler önizlemenin üstündeki
 * şeride (QuickFilters), sıralama tablo başlığına taşındı; Önizle düğmesi ve "bayat" rozeti
 * kalktı (önizleme otomatik). Kaynak değişince taslak o kaynağın varsayılanına döner
 * (`kaynakIcinBaslangic`); kolon seçici G139'a kadar burada kalır.
 */
export function ReportBuilder({ katalog, durum, onChange }: ReportBuilderProps) {
    const kaynak: KatalogVeriKaynagi | undefined = useMemo(
        () => katalog.veri_kaynaklari.find(k => k.anahtar === durum.veri_kaynagi),
        [katalog, durum.veri_kaynagi],
    );

    const kaynakDegisti = (anahtar: string) => {
        const yeni = katalog.veri_kaynaklari.find(k => k.anahtar === anahtar);
        if (!yeni || yeni.anahtar === durum.veri_kaynagi) return;
        onChange(kaynakIcinBaslangic(yeni));
    };

    return (
        <div className="flex flex-col gap-6">
            <span className="inline-flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] uppercase text-[var(--fg)] font-semibold">
                <SlidersHorizontal className="w-3.5 h-3.5 text-[var(--fg-muted)]" />
                Rapor Oluşturucu
            </span>

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
        </div>
    );
}
