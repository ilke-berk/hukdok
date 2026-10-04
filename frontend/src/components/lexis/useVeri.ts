import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { hataMetni, iptalMi } from "./yardimcilar";

export interface VeriDurumu<T> {
  /** `null`: henüz gelmedi (iskelet). */
  veri: T | null;
  hata: string | null;
  yukleniyor: boolean;
  yenile: () => void;
  setVeri: Dispatch<SetStateAction<T | null>>;
}

/**
 * Sekme verisini bağlanınca çeker; `anahtar` değişince (filtre) ya da `yenile` çağrılınca yeniden. Süren istek
 * iptal edilir; hata boş listeyle karıştırılmaz (çağıran `hata`yı ayrı gösterir). Lexis sekmeleri bununla
 * çalışır — araç sayfaları react-query kullanmıyor (`ReportsPage`, `HukukbotPage` deseni).
 */
export function useVeri<T>(getir: (signal: AbortSignal) => Promise<T>, anahtar = ""): VeriDurumu<T> {
  const [veri, setVeri] = useState<T | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [tik, setTik] = useState(0);
  // Çağıranlar `getir`i satır içi yazar (her render'da yeni kimlik); güncel işlev ref'ten okunur.
  const getirRef = useRef(getir);
  getirRef.current = getir;

  useEffect(() => {
    const ac = new AbortController();
    setYukleniyor(true);
    getirRef
      .current(ac.signal)
      .then((sonuc) => {
        setVeri(sonuc);
        setHata(null);
      })
      .catch((e: unknown) => {
        if (!iptalMi(e)) setHata(hataMetni(e));
      })
      .finally(() => {
        if (!ac.signal.aborted) setYukleniyor(false);
      });
    return () => ac.abort();
  }, [anahtar, tik]);

  const yenile = useCallback(() => setTik((t) => t + 1), []);
  return { veri, hata, yukleniyor, yenile, setVeri };
}
