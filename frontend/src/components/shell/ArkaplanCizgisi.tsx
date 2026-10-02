import { useIsFetching, type Query } from "@tanstack/react-query";
import { useDelayedFlag } from "@/hooks/useDelayedFlag";

// Faz 5 (algılanan hız): ekranda veri dururken arkada tazeleme sürdüğünü gösteren 2 px çizgi.
// İçeriği bloklamaz, spinner değildir. Yalnız "ekrandaki veri yenileniyor" durumunu sayar:
// - gözlemcisi olan (ekranda bir bileşenin beklediği) sorgu → önden yükleme/ısıtma (Faz 4)
//   gözlemcisizdir, fare gezinirken çizgi yanıp sönmez;
// - elinde verisi olan sorgu → ilk yükleme zaten iskelet gösterir, çift gösterge olmaz.
// 250 ms'den kısa tazelemede hiç görünmez, göründüyse en az 400 ms kalır (`useDelayedFlag`).

export const ekrandakiVeriTazeleniyor = (q: Query): boolean =>
  q.getObserversCount() > 0 && q.state.data !== undefined;

export function ArkaplanCizgisi() {
  const tazelenen = useIsFetching({ predicate: ekrandakiVeriTazeleniyor });
  const gorunur = useDelayedFlag(tazelenen > 0);
  if (!gorunur) return null;
  return (
    <div
      data-testid="arkaplan-cizgisi"
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-0 top-0 z-20 h-0.5 overflow-hidden"
    >
      <div className="arkaplan-cizgisi-parca h-full bg-[var(--brand)]" />
    </div>
  );
}
