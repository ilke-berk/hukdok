import { useState } from "react";
import { Columns3 } from "lucide-react";
import type { KatalogVeriKaynagi } from "@/lib/reports";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ColumnPicker } from "./ColumnPicker";

type ColumnSheetProps = {
    kaynak: KatalogVeriKaynagi;
    secili: string[];
    onChange: (next: string[]) => void;
};

/**
 * "Kolonlar (N)" düğmesi + sağdan açılan yan panel (shadcn `Sheet`, G139 §4.1 madde 3). Kolonlar ana
 * ekranda liste olarak DURMAZ; seçim/sıra `ColumnPicker`'da. Her değişiklik anında sayfaya yazılır
 * (yapısal değişiklik → önizleme hemen, G138 otomatik yolu); panel kapanınca ek istek gerekmez.
 * Panel Radix portal'ında açılır — testler `document.body` üzerinden okur (SaveTemplateDialog kalıbı).
 */
export function ColumnSheet({ kaynak, secili, onChange }: ColumnSheetProps) {
    const [acik, setAcik] = useState(false);

    return (
        <Sheet open={acik} onOpenChange={setAcik}>
            <button
                type="button"
                data-testid="kolon-dugmesi"
                aria-haspopup="dialog"
                aria-expanded={acik}
                onClick={() => setAcik(true)}
                title="Kolonları seç ve sırala"
                className={[
                    "inline-flex items-center gap-2 h-8 px-3 text-[12px] font-medium tracking-[0.03em] rounded-[3px] border transition-colors",
                    secili.length === 0
                        ? "border-[var(--brand)] text-[var(--brand)] bg-[var(--brand-soft)]"
                        : "border-[var(--border-strong)] text-[var(--fg-muted)] hover:text-[var(--fg)] hover:border-[var(--fg-muted)]",
                ].join(" ")}
            >
                <Columns3 className="w-3.5 h-3.5" />
                Kolonlar ({secili.length})
            </button>
            <SheetContent side="right" className="sm:max-w-xl overflow-y-auto" data-testid="kolon-paneli">
                {/* Minimal (07.09): alt açıklama kalktı; sıra bilgisi seçili listenin numaralarında zaten var. */}
                <SheetHeader>
                    <SheetTitle>Kolonlar · {kaynak.etiket}</SheetTitle>
                </SheetHeader>
                <ColumnPicker
                    kolonlar={kaynak.kolonlar}
                    secili={secili}
                    varsayilan={kaynak.varsayilan_kolonlar}
                    setler={kaynak.kolon_setleri}
                    onChange={onChange}
                />
            </SheetContent>
        </Sheet>
    );
}
