import { createContext, useCallback, useContext, useEffect, useRef } from "react";

/**
 * Tek mutlak arama barı altyapısının context'i ve hook'ları. Provider bileşeni
 * `components/system/PageSearch.tsx`'te durur (fast-refresh sınırı:
 * react-refresh/only-export-components).
 *
 * - Üst bar (Topbar) her sayfada sabit durur.
 * - Bir liste sayfası `usePageSearch(...)` çağırarak kendini "arama sahibi"
 *   olarak kaydeder; bar o sayfanın placeholder'ını gösterir ve girilen sorgu
 *   doğrudan o sayfanın filtresini sürer (yerinde arama).
 * - Hiçbir sayfa kayıt yapmadıysa (Anasayfa, Yükleme, Detay, Yönetim...) bar
 *   global arama moduna düşer; sonuçlar barın altında dropdown olarak çıkar.
 */

export type SearchRegistration = {
  placeholder: string;
};

export interface PageSearchContextValue {
  query: string;
  setQuery: (v: string) => void;
  /** Aktif sayfa bir arama kaydettiyse dolu, aksi halde null (global mod). */
  registration: SearchRegistration | null;
  register: (config: SearchRegistration) => void;
  unregister: () => void;
}

export const PageSearchContext = createContext<PageSearchContextValue | null>(null);

export function usePageSearchContext() {
  const ctx = useContext(PageSearchContext);
  if (!ctx) {
    throw new Error("usePageSearchContext must be used inside <PageSearchProvider>");
  }
  return ctx;
}

/**
 * Liste sayfalarının çağırdığı hook. Mount olunca barı bu sayfaya kilitler
 * (placeholder + opsiyonel başlangıç değeri), unmount olunca sorguyu temizler
 * ve barı global moda geri bırakır.
 */
export function usePageSearch({
  placeholder,
  seed,
}: {
  placeholder: string;
  seed?: string;
}) {
  const { query, setQuery, register, unregister } = usePageSearchContext();
  const seedRef = useRef(seed);
  const placeholderRef = useRef(placeholder);
  placeholderRef.current = placeholder;

  useEffect(() => {
    register({ placeholder: placeholderRef.current });
    setQuery(seedRef.current ?? "");
    return () => {
      unregister();
      setQuery("");
    };
  }, [register, unregister, setQuery]);

  const clear = useCallback(() => setQuery(""), [setQuery]);

  return { query, setQuery, clear };
}
