
import { ThemeToggle } from "@/components/theme-toggle";
import HukdokLogo from "./HukdokLogo";
import { Button } from "@/components/ui/button";
import { LogOut, ShieldCheck } from "lucide-react";

import { useMsal } from "@azure/msal-react";

import { useNavigate, useLocation } from "react-router-dom";

export const Header = () => {
  const { instance, accounts } = useMsal();
  const navigate = useNavigate();
  const location = useLocation();
  const currentUser = accounts[0]?.name || "Kullanıcı";

  const handleLogout = () => {
    try {
      console.log("🚪 Güvenli çıkış yapılıyor...");

      const currentAccount = instance.getActiveAccount();

      instance.logoutRedirect({
        account: currentAccount,
        postLogoutRedirectUri: window.location.origin + "/login",
      });

    } catch (error) {
      console.error("❌ Logout failed:", error);
      // Fallback
      sessionStorage.clear();
      localStorage.clear();
      window.location.reload();
    }
  };



  return (
    <header className="glass-header text-primary-foreground py-8 px-6 relative">
      <div className="absolute top-4 right-6 flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/")}
          className={`text-primary-foreground hover:bg-white/10 gap-2 ${location.pathname === "/" ? "bg-white/10" : ""}`}
        >
          Anasayfa
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/upload")}
          className={`text-primary-foreground hover:bg-white/10 gap-2 ${location.pathname === "/upload" ? "bg-white/10" : ""}`}
        >
          Belge Yükleme
        </Button>

        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/cases")}
          className={`text-primary-foreground hover:bg-white/10 gap-2 ${location.pathname === "/cases" || location.pathname === "/new-case" ? "bg-white/10" : ""}`}
        >
          Dava Dosyaları
        </Button>

        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/clients")}
          className={`text-primary-foreground hover:bg-white/10 gap-2 ${location.pathname === "/clients" ? "bg-white/10" : ""}`}
        >
          Müvekkiller
        </Button>

        {/* ADMIN LINK CHECK (Frontend Only) */}
        {(accounts[0]?.username || "").toLowerCase() === "ilkekutluk@lexisbio.onmicrosoft.com".toLowerCase() && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/admin")}
            className={`text-primary-foreground hover:bg-white/10 gap-2 ${location.pathname === "/admin" ? "bg-white/10" : "bg-red-500/20 hover:bg-red-500/30"}`}
          >
            <ShieldCheck className="h-4 w-4" />
            Yönetim
          </Button>
        )}

        <div className="h-4 w-px bg-white/20 mx-1" />


        <Button
          variant="ghost"
          size="sm"
          onClick={handleLogout}
          className="text-primary-foreground hover:bg-white/10 gap-2"
          title={`Çıkış Yap (${currentUser})`}
        >
          <LogOut className="w-4 h-4" />
          Çıkış
        </Button>
        <ThemeToggle />
      </div>
      <div className="container mx-auto">
        <div className="flex items-center justify-center gap-4 mb-3">
          <HukdokLogo className="drop-shadow-lg transition-transform hover:scale-105" />
        </div>
        <h1 className="text-4xl font-bold text-center mb-2 tracking-tight drop-shadow-lg">HUKDOK</h1>
        <p className="text-center text-sm opacity-90 font-medium tracking-wide">
          HANYALOĞLU&ACAR HUKUK BÜROSU DÖKÜMAN OTOMASYON SİSTEMİ BY TRAGIC
        </p>
      </div>
    </header>
  );
};
