import { useState, ReactNode } from "react";
import { PageTitleContext } from "@/hooks/usePageTitle";

export function PageTitleProvider({ children }: { children: ReactNode }) {
  const [title, setTitle] = useState("Anasayfa");
  const [breadcrumb, setBreadcrumb] = useState<string[]>(["Avukat Paneli"]);
  return (
    <PageTitleContext.Provider value={{ title, setTitle, breadcrumb, setBreadcrumb }}>
      {children}
    </PageTitleContext.Provider>
  );
}
