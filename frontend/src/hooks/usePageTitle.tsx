import { createContext, useContext, useEffect, useState, ReactNode } from "react";

type PageTitleContextValue = {
  title: string;
  setTitle: (t: string) => void;
  breadcrumb: string[];
  setBreadcrumb: (b: string[]) => void;
};

const PageTitleContext = createContext<PageTitleContextValue | null>(null);

export function PageTitleProvider({ children }: { children: ReactNode }) {
  const [title, setTitle] = useState("Anasayfa");
  const [breadcrumb, setBreadcrumb] = useState<string[]>(["Avukat Paneli"]);
  return (
    <PageTitleContext.Provider value={{ title, setTitle, breadcrumb, setBreadcrumb }}>
      {children}
    </PageTitleContext.Provider>
  );
}

export function usePageTitle() {
  const ctx = useContext(PageTitleContext);
  if (!ctx) {
    throw new Error("usePageTitle must be used inside <PageTitleProvider>");
  }
  return ctx;
}

export function useSetPageTitle(title: string, breadcrumb?: string[]) {
  const { setTitle, setBreadcrumb } = usePageTitle();
  useEffect(() => {
    setTitle(title);
    if (breadcrumb) setBreadcrumb(breadcrumb);
  }, [title, breadcrumb?.join("|"), setTitle, setBreadcrumb]);
}
