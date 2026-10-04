import { Check, Minus } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FlowButton } from "@/components/flow/primitives";
import { BAG_ANAHTARI_ADLARI, SIRKET_ADLARI, type RaporBagi } from "@/types/lexis";
import { Rozet } from "./ortak";

type KartSecimDiyaloguProps = {
  /** Kartı seçilecek rapor; `null` diyaloğu kapatır. */
  satir: RaporBagi | null;
  /** Süren seçim isteği: düğmeler kilitlenir. */
  isleniyor: boolean;
  onSec: (kartId: number) => void;
  onKapat: () => void;
};

function Tutan({ ad, tutuyor }: { ad: string; tutuyor: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[11.5px] ${tutuyor ? "text-tone-ok" : "text-[var(--fg-subtle)]"}`}>
      {tutuyor ? <Check className="w-3 h-3" aria-hidden="true" /> : <Minus className="w-3 h-3" aria-hidden="true" />}
      {ad}
      <span className="sr-only">{tutuyor ? "tutuyor" : "tutmuyor"}</span>
    </span>
  );
}

/**
 * Bir rapor birden çok karta düşünce (ya da anahtarlar çelişince) kartı İNSAN seçer (K8): adaylar ayırt edici
 * alanlarıyla yan yana gösterilir; hangi anahtarın (hasar no, dosya no, mahkeme + esas no) o kartta tuttuğu
 * işaretlidir. Sıralama öneridir — otomatik seçim yoktur.
 */
export function KartSecimDiyalogu({ satir, isleniyor, onSec, onKapat }: KartSecimDiyaloguProps) {
  return (
    <Dialog open={satir !== null} onOpenChange={(o) => !o && onKapat()}>
      {satir && (
        <DialogContent
          className="theme-classic max-w-4xl max-h-[88vh] overflow-y-auto bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none sm:rounded-none text-[var(--fg)]"
          data-testid="lexis-kart-secim"
        >
          <DialogHeader>
            <DialogTitle className="font-display text-[19px] font-medium text-[var(--fg)]">Bu rapor hangi dava kartına ait?</DialogTitle>
            <DialogDescription className="text-[12.5px] leading-[1.55] text-[var(--fg-muted)]">
              {satir.bag.durum === "CELISKI"
                ? "Hasar no ile dosya no farklı kartlara götürüyor. Seçerseniz rapor yalnız o karta bağlanır."
                : `Raporun ${satir.bag.anahtar ? BAG_ANAHTARI_ADLARI[satir.bag.anahtar] : "anahtarı"} ${satir.bag.adaylar.length} karta düşüyor. Seçilene kadar rapor adayların hepsine bağlı kalır.`}{" "}
              Sıralama öneridir; seçim sizindir.
            </DialogDescription>
          </DialogHeader>

          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-[12.5px]">
            {(
              [
                ["Rapor", [satir.sirket && SIRKET_ADLARI[satir.sirket], satir.rapor_turu === "EK" ? "ek" : "ana", satir.rapor_no].filter(Boolean).join(" · ")],
                ["Hasar no", satir.hasar_no],
                ["Mahkeme", satir.mahkeme],
                ["Esas no", satir.esas_no],
              ] as const
            ).map(([etiket, deger]) => (
              <div key={etiket} className="min-w-0">
                <dt className="text-[11px] text-[var(--fg-subtle)]">{etiket}</dt>
                <dd className="text-[var(--fg)] break-words">{deger || "—"}</dd>
              </div>
            ))}
          </dl>

          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {satir.bag.adaylar.map((a) => {
              const secili = satir.bag.birincil === a.kart.kart_id;
              return (
                <li
                  key={a.kart.kart_id}
                  data-testid="lexis-aday-kart"
                  className={`grid content-start gap-2 border px-3 py-2.5 bg-[var(--bg)] ${secili ? "border-[var(--brand)]" : "border-[var(--border)]"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[12px] font-semibold text-[var(--fg)]">Kart #{a.kart.kart_id}</span>
                    {secili && <Rozet ton="ok">seçili</Rozet>}
                  </div>
                  <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2.5 gap-y-0.5 text-[12.5px]">
                    <dt className="text-[var(--fg-subtle)]">Dosya no</dt>
                    <dd className="font-mono text-[11.5px] text-[var(--fg)]">{a.kart.dosya_nolari.join("; ") || "—"}</dd>
                    <dt className="text-[var(--fg-subtle)]">Mahkeme</dt>
                    <dd className="text-[var(--fg)] break-words">{a.kart.mahkeme ?? "—"}</dd>
                    <dt className="text-[var(--fg-subtle)]">Esas no</dt>
                    <dd className="font-mono text-[11.5px] text-[var(--fg)]">{a.kart.esas_no ?? "—"}</dd>
                    <dt className="text-[var(--fg-subtle)]">Durum</dt>
                    <dd className="text-[var(--fg)]">{[a.kart.durum, a.kart.asama].filter(Boolean).join(" · ") || "—"}</dd>
                  </dl>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                    <Tutan ad="hasar no" tutuyor={a.hasar} />
                    <Tutan ad="dosya no" tutuyor={a.dosya} />
                    <Tutan ad="esas no" tutuyor={a.esas} />
                  </div>
                  <FlowButton variant={secili ? "secondary" : "primary"} size="sm" disabled={isleniyor || secili} onClick={() => onSec(a.kart.kart_id)}>
                    {secili ? "Seçili kart" : "Bu kart"}
                  </FlowButton>
                </li>
              );
            })}
          </ul>
        </DialogContent>
      )}
    </Dialog>
  );
}
