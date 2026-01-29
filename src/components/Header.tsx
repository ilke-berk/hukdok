
import { ThemeToggle } from "@/components/theme-toggle";
import HukdokLogo from "./HukdokLogo";
import { Button } from "@/components/ui/button";
import { RefreshCw, LogOut } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import { useMsal } from "@azure/msal-react";

export const Header = () => {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const { instance, accounts } = useMsal();
  const currentUser = accounts[0]?.name || "Kullanıcı";

  const handleLogout = () => {
    try {
      console.log("🚪 Yerel çıkış yapılıyor...");

      // 1. Clear Active Account
      instance.setActiveAccount(null);

      // 2. Manually clear MSAL Cache from LocalStorage
      // This 'forgets' the user in this browser tab WITHOUT redirecting to Microsoft
      const keys = Object.keys(localStorage);
      keys.forEach(key => {
        // MSAL keys usually contain the Client ID or 'msal'
        if (key.toLowerCase().includes("msal") || key.includes(import.meta.env.VITE_AZURE_CLIENT_ID)) {
          localStorage.removeItem(key);
        }
      });
      sessionStorage.clear();

      // 3. Redirect to Login Page immediately
      window.location.hash = "/login";
      toast.success("Çıkış yapıldı");

    } catch (error) {
      console.error("❌ Logout failed:", error);
      window.location.hash = "/login";
    }
  };

  const handleRefresh = async () => {
    if (isRefreshing) return;

    setIsRefreshing(true);
    toast.info("SharePoint'ten veriler çekiliyor...");

    try {
      const response = await apiClient.fetch("/api/refresh", {
        method: "POST",
      });

      if (response.status === 429) {
        toast.error("Çok hızlı! Lütfen 1 dakika bekleyin.");
        return;
      }

      if (!response.ok) {
        throw new Error("Yenileme başarısız");
      }

      const data = await response.json();

      // Başarılı - sayfayı yenile (frontend config'leri tekrar çeksin)
      toast.success(`${data.message} Sayfa yenileniyor...`);

      // Kısa gecikme ile sayfayı yenile
      setTimeout(() => {
        window.location.reload();
      }, 1000);

    } catch (error) {
      console.error("Refresh error:", error);
      toast.error("Yenileme sırasında hata oluştu");
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <header className="glass-header text-primary-foreground py-8 px-6 relative">
      <div className="absolute top-4 right-6 flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="text-primary-foreground hover:bg-white/10"
          title="SharePoint'ten Listeleri Yenile"
        >
          <RefreshCw className={`h-5 h-5 ${isRefreshing ? "animate-spin" : ""}`} />
        </Button>
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
