import { useEffect, useRef, useState } from "react";

/**
 * Yükleme göstergesini titretmeden açıp kapatan bayrak (algılanan hız, Faz 5).
 *
 * - `flag` `delay` ms'den kısa sürerse gösterge HİÇ görünmez (hızlı yanıtta yanıp sönme yok).
 * - Bir kez göründüyse en az `minVisible` ms kalır (göz kırpması kadar görünüp kaybolmasın).
 */
export function useDelayedFlag(flag: boolean, delay = 250, minVisible = 400): boolean {
  const [visible, setVisible] = useState(false);
  const gorundu = useRef(0);

  useEffect(() => {
    if (flag) {
      if (visible) return;
      const t = setTimeout(() => {
        gorundu.current = Date.now();
        setVisible(true);
      }, delay);
      return () => clearTimeout(t);
    }
    if (!visible) return;
    const kalan = minVisible - (Date.now() - gorundu.current);
    if (kalan <= 0) {
      setVisible(false);
      return;
    }
    const t = setTimeout(() => setVisible(false), kalan);
    return () => clearTimeout(t);
  }, [flag, visible, delay, minVisible]);

  return visible;
}
