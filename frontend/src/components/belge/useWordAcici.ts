// İki yollu Word açma (G285, plan §6.5 "Word Online mı masaüstü mü"): önce `ms-word:ofe|u|<url>` ile masaüstü Word,
// `WORD_ACILMA_BEKLEMESI_MS` içinde pencere odağı kaybolmadıysa `yedekUrl` dolar → çağıran "Word Online'da aç"
// bağlantısını gösterir. Bileşen sökülünce zamanlayıcı temizlenir.
import { useCallback, useEffect, useRef, useState } from "react";
import { wordProtokoluylaAc } from "@/lib/belgeYasamApi";

export function useWordAcici() {
  const [yedekUrl, setYedekUrl] = useState<string | null>(null);
  const temizle = useRef<(() => void) | null>(null);

  useEffect(() => () => temizle.current?.(), []);

  const ac = useCallback((wordAc: string, wordUrl: string) => {
    temizle.current?.();
    setYedekUrl(null);
    temizle.current = wordProtokoluylaAc(wordAc, () => setYedekUrl(wordUrl));
  }, []);

  const sifirla = useCallback(() => {
    temizle.current?.();
    temizle.current = null;
    setYedekUrl(null);
  }, []);

  return { ac, yedekUrl, sifirla };
}
