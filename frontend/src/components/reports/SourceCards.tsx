import type { ComponentType } from "react";
import { Briefcase, FileText, Folder, Table2, Users } from "lucide-react";
import type { KatalogVeriKaynagi } from "@/lib/reports";

type SourceCardsProps = {
    kaynaklar: KatalogVeriKaynagi[];
    secili: string;
    /** Kart tıklaması — sayfa kaynağı değiştirir (`kaynakIcinBaslangic`, önizleme hemen yenilenir). */
    onSec: (anahtar: string) => void;
};

/** Kaynak anahtarı → simge; tanınmayan kaynak tablo simgesi alır (katalog genişlerse kart yine çıkar). */
const SIMGE: Record<string, ComponentType<{ className?: string }>> = {
    davalar: Briefcase,
    muvekkiller: Users,
    belgeler: FileText,
    foyler: Folder,
};

/**
 * Kaynak kartları (§4.1 madde 1, G139): "ne listeleyeceğim" seçimi — etiket + tek satır `aciklama`
 * + simge; seçili kart vurgulu. `role="radiogroup"` / `role="radio"` + `aria-checked`: erişilebilirlik
 * ve testin tek kimliği `[data-kaynak]`. Kaynak açıklaması YALNIZ burada yazılır (sadeleştirme);
 * `lg` altında kartlar yatay kaydırılır, gövde kaydırmaz.
 */
export function SourceCards({ kaynaklar, secili, onSec }: SourceCardsProps) {
    return (
        <div
            role="radiogroup"
            aria-label="Veri kaynağı"
            data-testid="kaynak-kartlari"
            className="flex gap-4 overflow-x-auto pb-1 -mb-1 lg:grid lg:grid-cols-4 lg:overflow-visible lg:pb-0 lg:mb-0"
        >
            {kaynaklar.map(k => {
                const aktif = k.anahtar === secili;
                const Simge = SIMGE[k.anahtar] ?? Table2;
                return (
                    <button
                        key={k.anahtar}
                        type="button"
                        role="radio"
                        aria-checked={aktif}
                        data-kaynak={k.anahtar}
                        onClick={() => onSec(k.anahtar)}
                        title={k.aciklama || k.etiket}
                        className={[
                            "flex items-start gap-3 text-left px-5 py-4 border rounded-none transition-colors",
                            "min-w-[220px] shrink-0 lg:min-w-0 lg:shrink",
                            aktif
                                ? "border-[var(--brand)] bg-[var(--brand-soft)] text-[var(--fg)]"
                                : "border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--fg-muted)] hover:border-[var(--fg-muted)] hover:text-[var(--fg)]",
                        ].join(" ")}
                    >
                        <Simge className={`w-4 h-4 mt-0.5 shrink-0 ${aktif ? "text-[var(--brand)]" : "text-[var(--fg-subtle)]"}`} />
                        <span className="min-w-0 flex flex-col gap-1">
                            <span className="font-display text-[15px] tracking-[-0.01em] font-medium leading-tight">{k.etiket}</span>
                            {k.aciklama && (
                                <span className="text-[11px] leading-snug text-[var(--fg-subtle)] truncate">{k.aciklama}</span>
                            )}
                        </span>
                    </button>
                );
            })}
        </div>
    );
}
