import { useCallback, useState, ReactNode } from "react";
// Context + hook'lar (usePageSearchContext / usePageSearch) ayrı dosyada:
// bu dosya yalnız bileşen export eder (react-refresh/only-export-components).
// Altyapının açıklaması orada.
import { PageSearchContext, type SearchRegistration } from "@/hooks/usePageSearch";

export function PageSearchProvider({ children }: { children: ReactNode }) {
  const [query, setQuery] = useState("");
  const [registration, setRegistration] = useState<SearchRegistration | null>(null);

  const register = useCallback((config: SearchRegistration) => setRegistration(config), []);
  const unregister = useCallback(() => setRegistration(null), []);

  return (
    <PageSearchContext.Provider
      value={{ query, setQuery, registration, register, unregister }}
    >
      {children}
    </PageSearchContext.Provider>
  );
}
