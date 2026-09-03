import { createContext, useContext } from "react";

export type Theme = "dark" | "light" | "system";

export type ThemeProviderState = {
    theme: Theme;
    setTheme: (theme: Theme) => void;
};

const initialState: ThemeProviderState = {
    theme: "system",
    setTheme: () => null,
};

/**
 * Tema context'i ve hook'u. Provider bileşeni `components/theme-provider.tsx`'te
 * durur; hook'un ayrı dosyada olması fast-refresh sınırı içindir
 * (react-refresh/only-export-components).
 */
export const ThemeProviderContext = createContext<ThemeProviderState>(initialState);

export const useTheme = () => {
    const context = useContext(ThemeProviderContext);

    if (context === undefined)
        throw new Error("useTheme must be used within a ThemeProvider");

    return context;
};
