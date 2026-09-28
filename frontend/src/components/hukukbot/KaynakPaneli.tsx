import { useEffect, useMemo, useRef, useState } from "react";
import { BookOpen, X } from "lucide-react";
import type { HukukbotKaynak } from "@/types/hukukbot";
import { KaynakListesi } from "./KaynakListesi";
import { atiflariNumarala } from "./atiflar";
import type { EkranMesaji } from "./yardimcilar";

/** Rozet tıklaması: hangi numara, `tik` aynı numaraya ikinci tıklamada da efekti yeniden tetikler. */
export type KaynakVurgusu = { n: number; tik: number };

type KaynakPaneliProps = {
  /** Kaynakları gösterilen model mesajı. */
  mesaj: EkranMesaji;
  vurgu: KaynakVurgusu | null;
  onKapat: () => void;
  onIndir: (kaynak: HukukbotKaynak) => void;
  inen?: string | null;
};

/**
 * Sağdaki kaynak paneli (28.09): kaynak kartları metnin altında değil burada. Geniş ekranda (xl+) sohbetin yanında
 * sabit sütun, dar ekranda sağdan açılan çekmece (sayfa yerleşimi `HukukbotPage`'de). Kart numaraları metindeki
 * atıf rozetleriyle aynı (`atiflariNumarala`); rozete tıklanınca o karta kaydırılır ve kart kısa süre vurgulanır.
 */
export function KaynakPaneli({ mesaj, vurgu, onKapat, onIndir, inen }: KaynakPaneliProps) {
  const onek = `kaynak-paneli-${mesaj.anahtar}`;
  const { adlar } = useMemo(() => atiflariNumarala(mesaj.content), [mesaj.content]);
  const kaynaklar = mesaj.sources ?? [];
  const [vurgulu, setVurgulu] = useState<number | null>(null);
  const zamanlayici = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!vurgu) return;
    document.getElementById(`${onek}-kaynak-${vurgu.n}`)?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    setVurgulu(vurgu.n);
    if (zamanlayici.current) clearTimeout(zamanlayici.current);
    zamanlayici.current = setTimeout(() => setVurgulu(null), 1600);
  }, [vurgu, onek]);
  useEffect(() => () => {
    if (zamanlayici.current) clearTimeout(zamanlayici.current);
  }, []);

  return (
    <div className="h-full flex flex-col min-h-0" data-testid="kaynak-paneli">
      <div className="h-12 shrink-0 flex items-center justify-between gap-2 px-4 border-b border-[var(--border)]">
        <span className="inline-flex items-center gap-2 text-[13px] font-medium text-[var(--fg)]">
          <BookOpen className="w-4 h-4 text-[var(--brand)]" aria-hidden="true" />
          Kaynaklar · {kaynaklar.length}
        </span>
        <button
          type="button"
          onClick={onKapat}
          aria-label="Kaynak panelini kapat"
          title="Kapat"
          className="w-8 h-8 grid place-items-center rounded-[3px] text-[var(--fg-subtle)] hover:text-[var(--brand)] hover:bg-[var(--bg-elevated)]"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3">
        <KaynakListesi
          kaynaklar={kaynaklar}
          onIndir={onIndir}
          inen={inen}
          atifAdlari={adlar}
          idOneki={onek}
          vurgulu={vurgulu}
        />
      </div>
    </div>
  );
}
