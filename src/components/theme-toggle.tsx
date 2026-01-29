import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/components/theme-provider";

export function ThemeToggle() {
    const { theme, setTheme } = useTheme();

    const toggleTheme = () => {
        setTheme(theme === "light" ? "dark" : "light");
    };

    return (
        <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            className="text-white hover:bg-white/10 hover:text-white transition-all rounded-full"
            title={theme === "light" ? "Koyu tema" : "Açık tema"}
        >
            {theme === "light" ? (
                <Moon className="h-5 w-5 transition-transform rotate-0 scale-100" />
            ) : (
                <Sun className="h-5 w-5 transition-transform rotate-0 scale-100" />
            )}
            <span className="sr-only">Tema değiştir</span>
        </Button>
    );
}
