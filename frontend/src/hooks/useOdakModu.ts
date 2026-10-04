import { createContext, useContext, useEffect } from "react";

export type OdakModuContextValue = {
  /** Sayfa odak modunda mı — kabuk Topbar'ı çizmez, `main` dolgusuz ve kaydırmasız olur. */
  odak: boolean;
  setOdak: (odak: boolean) => void;
  /** HUKDOK menüsünü (Sidebar) açar — odak modunda Topbar'daki ☰'nin yerini alan düğmeler çağırır. */
  menuyuAc: () => void;
};

/**
 * Kabuk odak modu (28.09, Hukukbot yeniden tasarımı). Provider `components/shell/Shell.tsx`'tedir.
 * Odak modundaki sayfa tam yüksekliği kendisi yönetir; kenar hover şeridi kapalıdır ve menü yalnız
 * açık tıkla açılır, dışarı tıklama / Esc ile kapanır (sayfanın kendi sol paneliyle çakışmasın).
 */
export const OdakModuContext = createContext<OdakModuContextValue | null>(null);

const BOS: OdakModuContextValue = { odak: false, setOdak: () => undefined, menuyuAc: () => undefined };

export function useOdakModuContext(): OdakModuContextValue {
  return useContext(OdakModuContext) ?? BOS;
}

/** Sayfa bağlıyken kabuğu odak moduna alır; ayrılınca geri bırakır. Menüyü açma işlevini döndürür. */
export function useOdakModu(): () => void {
  const { setOdak, menuyuAc } = useOdakModuContext();
  useEffect(() => {
    setOdak(true);
    return () => setOdak(false);
  }, [setOdak]);
  return menuyuAc;
}
