import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/theme-provider";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, useNavigate } from "react-router-dom";
import { MsalProvider, useMsal } from "@azure/msal-react";
import { msalInstance } from "@/config/msalConfig";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { ProtectedAdminRoute } from "@/components/ProtectedAdminRoute";
import { ShellLayout } from "@/components/shell/Shell";
import { ConfirmDialogProvider } from "@/components/system/ConfirmDialog";
import { useIdleTimeout } from "@/hooks/useIdleTimeout";
import { ActivityReportModal, ActivityReport } from "@/components/ActivityReportModal";
import { apiClient } from "@/lib/api";
import Index from "./pages/Index";
import AvukatDashboard from "./pages/dashboards/AvukatDashboard";
import IdariDashboard from "./pages/dashboards/IdariDashboard";
import { useDashboardView } from "@/hooks/useDashboardView";
import Login from "./pages/Login";
import AdminPage from "./pages/AdminPage";
import NewCase from "./pages/NewCase";
import CaseList from "./pages/CaseList";
import NewClient from "./pages/NewClient";
import ClientList from "./pages/ClientList";
import NotFound from "./pages/NotFound";
import CaseDetails from "./pages/CaseDetails";
import CaseGroup from "./pages/CaseGroup";
import UnlinkedDocuments from "./pages/UnlinkedDocuments";
import ActivityHistory from "./pages/ActivityHistory";
import { useEffect, useState } from "react";

const queryClient = new QueryClient();

// Dashboard router — Sidebar'daki view toggle'a göre Avukat veya İdari render eder.
const DashboardRouter = () => {
  const { view } = useDashboardView();
  return view === "idari" ? <IdariDashboard /> : <AvukatDashboard />;
};

// Wrapper component to use hooks inside MsalProvider
const AppContent = () => {
  useIdleTimeout(30, 5);
  const { accounts } = useMsal();
  const [activityReport, setActivityReport] = useState<ActivityReport | null>(null);

  // Oturum açıldıktan sonra bir kez günlük raporu kontrol et
  useEffect(() => {
    if (accounts.length === 0) return;

    let cancelled = false;
    const check = async () => {
      try {
        const res = await apiClient.fetch("/api/activity/daily-report");
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (data && data.id) {
          setActivityReport(data as ActivityReport);
        }
      } catch {
        // sessizce geç — kritik değil
      }
    };
    check();
    return () => { cancelled = true; };
  }, [accounts.length]);

  return (
    <>
      {activityReport && (
        <ActivityReportModal
          report={activityReport}
          onClose={() => setActivityReport(null)}
        />
      )}
    <BrowserRouter>
      <Routes>
        {/* Public Route */}
        <Route path="/login" element={<Login />} />

        {/* Protected Routes — App Shell ile sarılı */}
        <Route
          element={
            <ProtectedRoute>
              <ShellLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<DashboardRouter />} />
          <Route path="/upload" element={<Index />} />
          <Route path="/unlinked-documents" element={<UnlinkedDocuments />} />
          <Route path="/new-case" element={<CaseList />} />
          <Route path="/cases" element={<CaseList />} />
          <Route path="/new-case/form" element={<NewCase />} />
          <Route path="/new-client" element={<NewClient />} />
          <Route path="/clients" element={<ClientList />} />
          <Route path="/cases/:id" element={<CaseDetails />} />
          <Route path="/case-groups/:groupId" element={<CaseGroup />} />
          <Route path="/activity-history" element={<ActivityHistory />} />
          <Route
            path="/admin"
            element={
              <ProtectedAdminRoute>
                <AdminPage />
              </ProtectedAdminRoute>
            }
          />
        </Route>

        {/* 404 */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  </>
  );
};

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
      } catch (error: unknown) {
        console.error("❌ MSAL hatası:", error);
        if (error instanceof Error) {
          console.error("📄 Hata detayları:", {
            message: error.message,
            stack: error.stack,
            errorObj: error
          });
        }

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
          <div className="rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
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
            <ConfirmDialogProvider>
              <Toaster />
              <Sonner />
              <AppContent />
            </ConfirmDialogProvider>
          </TooltipProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </MsalProvider>
  );
};

export default App;
