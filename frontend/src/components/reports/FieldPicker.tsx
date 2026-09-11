import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import type { KatalogKolon } from "@/lib/reports";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { LINK_BTN_CLS, useDisariTiklama } from "./ui";

/**
 * cmdk'nın varsayılan bulanık skoru ("kon" → "tracking_no"yu da getirir) yerine düz alt-dize:
 * kullanıcı yazdığı parçayı içeren etiket/anahtarları görür (tr-TR küçük harf).
 */
function altDizeFiltresi(value: string, search: string, keywords?: string[]): number {
    const q = search.trim().toLocaleLowerCase("tr-TR");
    if (!q) return 1;
    return [value, ...(keywords ?? [])].some(v => v.toLocaleLowerCase("tr-TR").includes(q)) ? 1 : 0;
}

type FieldPickerProps = {
    /** Seçilebilir alanlar: yalnız `filtrelenebilir`, zaten şeritte olanlar çağıran tarafından elenmiş. */
    kolonlar: KatalogKolon[];
    onSec: (anahtar: string) => void;
    disabled?: boolean;
    /** Düğme metni (G173 tanım şeridi "Filtre" der); varsayılan "Başka alan". */
    etiket?: string;
    /** Düğmenin `title` ipucu (tavan dolunca "En çok 20 filtre" gibi). */
    title?: string;
};

/**
 * "+ Başka alan" — cmdk `Command` ile aranabilir, `grup` başlıklı alan seçici (§4.1 madde 2).
 * 80+ öğeli düz `<select>`in yerine geçer; seçim şeride aynı türde kontrol olarak eklenir.
 */
export function FieldPicker({ kolonlar, onSec, disabled, etiket = "Başka alan", title }: FieldPickerProps) {
    const [acik, setAcik] = useState(false);
    const ref = useDisariTiklama<HTMLDivElement>(acik, () => setAcik(false));

    // Grup sırası: katalogdaki ilk görülme sırası (kaynağın kapalı kümesi zaten sıralı).
    const gruplar = useMemo(() => {
        const sira: string[] = [];
        const harita = new Map<string, KatalogKolon[]>();
        for (const k of kolonlar) {
            const g = k.grup || "Diğer";
            if (!harita.has(g)) {
                harita.set(g, []);
                sira.push(g);
            }
            harita.get(g)!.push(k);
        }
        return sira.map(g => ({ grup: g, kolonlar: harita.get(g)! }));
    }, [kolonlar]);

    return (
        <div ref={ref} className="relative shrink-0">
            <button
                type="button"
                className={LINK_BTN_CLS + " inline-flex items-center gap-0.5"}
                aria-expanded={acik}
                aria-haspopup="dialog"
                disabled={disabled || kolonlar.length === 0}
                title={title}
                onClick={() => setAcik(v => !v)}
            >
                <Plus className="w-3 h-3" />
                {etiket}
            </button>
            {acik && (
                <div
                    role="dialog"
                    aria-label="Alan seç"
                    data-testid="alan-secici"
                    // Sola hizalı: düğme şeridin sol tarafında (12.09 bulgusu: `right-0` panel sol kenardan taşıp kesiliyordu)
                    className="absolute left-0 z-30 mt-1 w-[280px] max-w-[calc(100vw-2rem)] border border-[var(--border)] bg-[var(--bg-elevated)] shadow-md"
                >
                    <Command loop filter={altDizeFiltresi} className="bg-transparent text-[var(--fg)]">
                        <CommandInput aria-label="Alan ara" placeholder="Alan ara…" autoFocus className="h-9 text-[12px]" />
                        <CommandList className="max-h-72">
                            <CommandEmpty className="py-3 text-[11px] text-[var(--fg-subtle)]">Alan bulunamadı.</CommandEmpty>
                            {gruplar.map(g => (
                                <CommandGroup
                                    key={g.grup}
                                    heading={g.grup}
                                    className="[&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:text-[9.5px] [&_[cmdk-group-heading]]:tracking-[0.14em] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:text-[var(--fg-subtle)]"
                                >
                                    {g.kolonlar.map(k => (
                                        <CommandItem
                                            key={k.anahtar}
                                            value={k.etiket}
                                            keywords={[k.anahtar]}
                                            data-alan={k.anahtar}
                                            onSelect={() => { onSec(k.anahtar); setAcik(false); }}
                                            className="text-[12px] py-1"
                                        >
                                            {k.etiket}
                                        </CommandItem>
                                    ))}
                                </CommandGroup>
                            ))}
                        </CommandList>
                    </Command>
                </div>
            )}
        </div>
    );
}
