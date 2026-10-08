import { FileDown, RefreshCw } from "lucide-react";
import { FlowButton } from "@/components/flow/primitives";

type CiktiCubuguProps = {
  hataSayisi: number;
  uyariSayisi: number;
  /** Son denetimden sonra taslak değişti. */
  bayat: boolean;
  denetleniyor: boolean;
  /** Son denetimin saati (`HH:MM`). */
  sonDenetim: string | null;
  onDenetle: () => void;
  onWord: () => void;
  /** "PDF indir" (servis Word'ü PDF'e çevirir); verilmezse düğme çizilmez. */
  onPdf?: () => void;
  kilitli?: boolean;
};

/** Tezgâhın çıktı çubuğu: denetim durumu, "Yeniden denetle", "Word indir" ve "PDF indir". Uyarılar indirmeyi engellemez; sayı gösterilir. */
export function CiktiCubugu({ hataSayisi, uyariSayisi, bayat, denetleniyor, sonDenetim, onDenetle, onWord, onPdf, kilitli = false }: CiktiCubuguProps) {
  const ozet = bayat
    ? "Taslak değişti — yeniden denetleyin"
    : hataSayisi + uyariSayisi === 0
      ? "Denetim temiz"
      : [hataSayisi > 0 && `${hataSayisi} düzeltilmeli`, uyariSayisi > 0 && `${uyariSayisi} gözden geçirilmeli`].filter(Boolean).join(" · ");
  return (
    <div data-testid="lexis-cikti-cubugu" className="grid gap-2">
      <div className="flex items-center justify-between gap-2 text-[12px]">
        <span className={bayat ? "text-[var(--fg-muted)]" : hataSayisi > 0 ? "text-tone-danger" : uyariSayisi > 0 ? "text-tone-caution" : "text-tone-ok"}>{ozet}</span>
        {sonDenetim && <span className="font-mono text-[10.5px] text-[var(--fg-subtle)] shrink-0">denetim {sonDenetim}</span>}
      </div>
      <div className={`grid gap-2 ${onPdf ? "grid-cols-3" : "grid-cols-2"}`}>
        <FlowButton variant="secondary" size="sm" onClick={onDenetle} disabled={kilitli || denetleniyor}>
          <RefreshCw className={`w-3.5 h-3.5 ${denetleniyor ? "animate-spin" : ""}`} aria-hidden="true" />
          Yeniden denetle
        </FlowButton>
        <FlowButton
          variant="primary"
          size="sm"
          onClick={onWord}
          disabled={kilitli}
          title={hataSayisi > 0 ? "Düzeltilmesi gereken uyarılar var; Word yine de indirilebilir" : undefined}
        >
          <FileDown className="w-3.5 h-3.5" aria-hidden="true" />
          Word indir
        </FlowButton>
        {onPdf && (
          <FlowButton
            variant="secondary"
            size="sm"
            onClick={onPdf}
            disabled={kilitli}
            title={hataSayisi > 0 ? "Düzeltilmesi gereken uyarılar var; PDF yine de indirilebilir" : undefined}
          >
            <FileDown className="w-3.5 h-3.5" aria-hidden="true" />
            PDF indir
          </FlowButton>
        )}
      </div>
    </div>
  );
}
