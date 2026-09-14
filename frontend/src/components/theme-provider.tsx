import { useEffect, useState } from "react";
// Context + useTheme hook'u ayrı dosyada: bu dosya yalnız bileşen export eder (fast-refresh).
import { ThemeProviderContext, type Theme } from "@/hooks/useTheme";

type ThemeProviderProps = {
    children: React.ReactNode;
    defaultTheme?: Theme;
    storageKey?: string;
};

// G188 (F7): localStorage erişimi fırlatabilir (Safari private, kurumsal politika,
// kota dolu). Sağlayıcı açılışta çizildiği için korumasız okuma tüm uygulamayı beyaz
// ekrana çeviriyordu. Desen: components/system/DashboardViewProvider.tsx::readStored.
function readStoredTheme(storageKey: string, defaultTheme: Theme): Theme {
    try {
        const raw = localStorage.getItem(storageKey);
        return raw === "dark" || raw === "light" || raw === "system" ? raw : defaultTheme;
    } catch {
        return defaultTheme;
    }
}

export function ThemeProvider({
    children,
    defaultTheme = "dark",
    storageKey = "hukudok-theme",
    ...props
}: ThemeProviderProps) {
    const [theme, setTheme] = useState<Theme>(() => readStoredTheme(storageKey, defaultTheme));

    useEffect(() => {
        const root = window.document.documentElement;

        root.classList.remove("light", "dark");

        if (theme === "system") {
            const systemTheme = window.matchMedia("(prefers-color-scheme: dark)")
                .matches
                ? "dark"
                : "light";

            root.classList.add(systemTheme);
            return;
        }

        root.classList.add(theme);
    }, [theme]);

    const value = {
        theme,
        setTheme: (theme: Theme) => {
            try {
                localStorage.setItem(storageKey, theme);
            } catch {
                // Depo kapalı/kota dolu: seçim kalıcı olmaz, bu oturumda yine uygulanır.
            }
            setTheme(theme);
        },
    };

    return (
        <ThemeProviderContext.Provider {...props} value={value}>
            {children}
        </ThemeProviderContext.Provider>
    );
}
