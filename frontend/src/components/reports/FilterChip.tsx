import { useState } from "react";
import { MoreHorizontal, X } from "lucide-react";
import type { FiltreOp, KatalogKolon, KontrolDurumu } from "@/lib/reports";
import { OP_ETIKETLERI, bosKontrol, degerSekleUyarla, gelismisOplar, kolonOplari, kontrolOzeti } from "@/lib/reports";
import type { SeritOgesi } from "./builderState";
import { useDisariTiklama } from "./ui";

type FilterChipProps = {
    oge: SeritOgesi;
    kolon: KatalogKolon;
    onDegistir: (durum: KontrolDurumu) => void;
    /** × — hızlı filtre yuvası boşa döner, eklenen alan şeritten kalkar (QuickFilters karar verir). */
    onKaldir: () => void;
};

type MenuOgesi = { anahtar: string; etiket: string; secili?: boolean; uygula: () => void };

/** Mevcut kontrolün tekil değeri (gelişmiş `ne`/`eq`'e geçerken korunur). */
function tekilDeger(d: KontrolDurumu): string | number | undefined {
    switch (d.kontrol) {
        case "coklu_secim": return d.secili[0];
        case "metin_icerir": return d.metin.trim() || undefined;
        case "tarih_araligi": return d.baslangic.trim() || d.bitis.trim() || undefined;
        case "sayi_araligi": return d.en_az ?? d.en_cok ?? undefined;
        default: return undefined;
    }
}

/**
 * Etkin filtre çipi: `etiket · özet` · "…" menüsü (gelişmiş op'lar: kolonun `oplar`ında olup
 * kontrolün doğal üretmedikleri — `ne`/`not_null`; metinde "tam eşitlik" anahtarı) · ×.
 * Gelişmiş çipte menü: diğer izinli op'lar + "Basit kontrole dön". Sunucu sözleşmesi değişmez.
 */
export function FilterChip({ oge, kolon, onDegistir, onKaldir }: FilterChipProps) {
    const [menuAcik, setMenuAcik] = useState(false);
    const ref = useDisariTiklama<HTMLSpanElement>(menuAcik, () => setMenuAcik(false));
    const d = oge.durum;
    const etiket = kolon.etiket;
    const ozet = kontrolOzeti(d, kolon.tip);
    const gelismis = d.kontrol === "gelismis";

    const menu: MenuOgesi[] = [];
    if (d.kontrol === "gelismis") {
        for (const op of kolonOplari(kolon)) {
            if (op === d.op) continue;
            menu.push({
                anahtar: op,
                etiket: OP_ETIKETLERI[op],
                uygula: () => {
                    const deger = degerSekleUyarla(op, d.deger);
                    onDegistir(deger === undefined ? { kontrol: "gelismis", alan: d.alan, op } : { kontrol: "gelismis", alan: d.alan, op, deger });
                },
            });
        }
        if (kolon.kontrol) {
            menu.push({ anahtar: "basit", etiket: "Basit kontrole dön", uygula: () => onDegistir(bosKontrol(kolon)) });
        }
    } else {
        if (d.kontrol === "metin_icerir" && kolon.oplar.includes("eq")) {
            menu.push({
                anahtar: "tam",
                etiket: "Tam eşitlik",
                secili: d.tam,
                uygula: () => onDegistir({ ...d, tam: !d.tam }),
            });
        }
        for (const op of gelismisOplar(kolon)) {
            menu.push({
                anahtar: op,
                etiket: OP_ETIKETLERI[op],
                uygula: () => {
                    const deger = degerSekleUyarla(op as FiltreOp, tekilDeger(d));
                    onDegistir(deger === undefined ? { kontrol: "gelismis", alan: d.alan, op } : { kontrol: "gelismis", alan: d.alan, op, deger });
                },
            });
        }
    }

    return (
        <span
            ref={ref}
            data-testid="filtre-cipi"
            data-alan={d.alan}
            data-gelismis={gelismis ? "true" : undefined}
            className={[
                "relative inline-flex items-center gap-1 pl-2 pr-0.5 py-0.5 text-[11.5px] border rounded-[3px] max-w-full",
                gelismis
                    ? "border-[var(--brand)]/50 bg-[var(--brand-soft)] text-[var(--fg)]"
                    : "border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[var(--fg)]",
            ].join(" ")}
        >
            <span className="font-mono text-[9.5px] tracking-[0.1em] uppercase text-[var(--fg-subtle)] shrink-0">
                {etiket}
                {gelismis && <span className="ml-1 text-[var(--brand)]">gelişmiş</span>}
            </span>
            <span className="truncate" title={ozet}>{ozet}</span>
            {menu.length > 0 && (
                <button
                    type="button"
                    aria-label={`${etiket} filtre seçenekleri`}
                    aria-expanded={menuAcik}
                    aria-haspopup="menu"
                    onClick={() => setMenuAcik(v => !v)}
                    className="w-5 h-5 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--fg)] rounded-[2px]"
                >
                    <MoreHorizontal className="w-3.5 h-3.5" />
                </button>
            )}
            <button
                type="button"
                aria-label={`${etiket} filtresini kaldır`}
                onClick={onKaldir}
                className="w-5 h-5 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)] rounded-[2px]"
            >
                <X className="w-3 h-3" />
            </button>
            {menuAcik && menu.length > 0 && (
                <div
                    role="menu"
                    aria-label={`${etiket} gelişmiş`}
                    className="absolute left-0 top-full z-30 mt-1 min-w-[160px] border border-[var(--border)] bg-[var(--bg-elevated)] shadow-md p-1 flex flex-col"
                >
                    {menu.map(m => (
                        <button
                            key={m.anahtar}
                            type="button"
                            role="menuitemcheckbox"
                            aria-checked={m.secili ?? false}
                            onClick={() => { m.uygula(); setMenuAcik(false); }}
                            className="text-left px-2 py-1 text-[12px] text-[var(--fg)] hover:bg-[var(--bg)] whitespace-nowrap"
                        >
                            {m.secili ? "✓ " : ""}{m.etiket}
                        </button>
                    ))}
                </div>
            )}
        </span>
    );
}
