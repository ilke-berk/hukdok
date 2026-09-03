import { createContext, useContext, useEffect, useRef } from "react";

export type PageTitleContextValue = {
  title: string;
  setTitle: (t: string) => void;
  breadcrumb: string[];
  setBreadcrumb: (b: string[]) => void;
};

/**
 * Sayfa başlığı context'i + hook'ları. Provider bileşeni
 * `components/system/PageTitleProvider.tsx`'te durur (fast-refresh sınırı:
 * react-refresh/only-export-components).
 */
export const PageTitleContext = createContext<PageTitleContextValue | null>(null);

export function usePageTitle() {
  const ctx = useContext(PageTitleContext);
  if (!ctx) {
    throw new Error("usePageTitle must be used inside <PageTitleProvider>");
  }
  return ctx;
}

export function useSetPageTitle(title: string, breadcrumb?: string[]) {
  const { setTitle, setBreadcrumb } = usePageTitle();
  // Çağıranlar breadcrumb'ı satır içi dizi olarak verir (her render'da yeni
  // kimlik). Diziyi doğrudan bağımlılığa koymak setBreadcrumb → re-render →
  // yeni dizi döngüsü açar; bu yüzden içerik anahtarı üzerinden izlenir,
  // güncel dizi ref'ten okunur.
  const breadcrumbRef = useRef(breadcrumb);
  breadcrumbRef.current = breadcrumb;
  const breadcrumbKey = breadcrumb?.join("|");
  useEffect(() => {
    setTitle(title);
    if (breadcrumbRef.current) setBreadcrumb(breadcrumbRef.current);
  }, [title, breadcrumbKey, setTitle, setBreadcrumb]);
}
