import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/theme-provider";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Routes, Route, useNavigate } from "react-router-dom";
import { MsalProvider } from "@azure/msal-react";
import { msalInstance } from "@/config/msalConfig";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import Index from "./pages/Index";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import { useEffect, useState } from "react";

const queryClient = new QueryClient();

const App = () => {
  console.log("App component rendering");
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    // Initialize MSAL and handle redirect
    const initializeMsal = async () => {
      try {
        // CRITICAL: Initialize MSAL instance first
        console.log("🔄 MSAL başlatılıyor...");
        console.log("📋 Config:", {
          clientId: import.meta.env.VITE_AZURE_CLIENT_ID,
          tenantId: import.meta.env.VITE_AZURE_TENANT_ID,
          redirectUri: window.location.origin
        });

        await msalInstance.initialize();
        console.log("✅ MSAL başarıyla başlatıldı");

        // Then handle redirect response from Microsoft login
        console.log("🔄 Redirect promise kontrol ediliyor...");
        const response = await msalInstance.handleRedirectPromise();

        if (response) {
          console.log("✅ Login başarılı:", {
            username: response.account?.username,
            name: response.account?.name,
            tenantId: response.account?.tenantId
          });

          // CRITICAL: Set the active account so useMsal() can detect it
          if (response.account) {
            msalInstance.setActiveAccount(response.account);
            console.log("✅ Active account ayarlandı:", response.account.username);
          }
        } else {
          console.log("ℹ️ Redirect response yok (ilk yükleme veya başarısız giriş)");

          // Check if there's already an account cached
          const accounts = msalInstance.getAllAccounts();
          if (accounts.length > 0) {
            msalInstance.setActiveAccount(accounts[0]);
            console.log("✅ Mevcut hesap kullanılıyor:", accounts[0].username);
          }
        }
      } catch (error: any) {
        console.error("❌ MSAL hatası:", error);
        console.error("📄 Hata detayları:", {
          message: error.message,
          errorCode: error.errorCode,
          errorMessage: error.errorMessage,
          subError: error.subError,
          stack: error.stack
        });

        // Show user-friendly error message
        import("sonner").then(({ toast }) => {
          toast.error("Oturum Açma Hatası", {
            description: "Giriş işlemi tamamlanamadı. Lütfen yetkili bir hesapla tekrar deneyin.",
            duration: 5000
          });
        });
      } finally {
        setIsReady(true);
      }
    };

    initializeMsal();
  }, []);

  if (!isReady) {
    // Show loading while initializing MSAL
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Yükleniyor...</p>
        </div>
      </div>
    );
  }

  return (
    <MsalProvider instance={msalInstance}>
      <ThemeProvider defaultTheme="dark" storageKey="hukudok-theme">
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            <Toaster />
            <Sonner />
            <HashRouter>
              <Routes>
                {/* Public Route */}
                <Route path="/login" element={<Login />} />

                {/* Protected Routes */}
                <Route
                  path="/"
                  element={
                    <ProtectedRoute>
                      <Index />
                    </ProtectedRoute>
                  }
                />

                {/* 404 */}
                <Route path="*" element={<NotFound />} />
              </Routes>
            </HashRouter>
          </TooltipProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </MsalProvider>
  );
};

export default App;
