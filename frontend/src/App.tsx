import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/theme-provider";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router";
import { MsalProvider, useMsal } from "@azure/msal-react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { msalInstance } from "@/config/msalConfig";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { ProtectedAdminRoute } from "@/components/ProtectedAdminRoute";
import { ShellLayout } from "@/components/shell/Shell";
import { ConfirmDialogProvider } from "@/components/system/ConfirmDialog";
import { ErrorBoundary } from "@/components/system/ErrorBoundary";
import { useIdleTimeout } from "@/hooks/useIdleTimeout";
import { ActivityReportModal, ActivityReport } from "@/components/ActivityReportModal";
import { apiClient } from "@/lib/api";
import { importWithReload } from "@/lib/chunkReload";
import { useDashboardView } from "@/hooks/useDashboardView";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import { Suspense, lazy, useEffect, useState } from "react";

// G182: sayfalar route başına ayrı parça (tek 1,5 MB paket yerine). Login ve NotFound
// statik kalır: oturumsuz ilk açılış ve 404 ek ağ turu beklemeden çizilsin.
// /reports + /admin parçaları (rapor katmanı, @dnd-kit) admin olmayan kullanıcıya
// hiç inmez. importWithReload: deploy sonrası bayat parça → sayfa BİR kez yenilenir
// (src/lib/chunkReload.ts).
const Index = lazy(() => importWithReload(() => import("./pages/Index")));
const AvukatDashboard = lazy(() => importWithReload(() => import("./pages/dashboards/AvukatDashboard")));
const IdariDashboard = lazy(() => importWithReload(() => import("./pages/dashboards/IdariDashboard")));
const AdminPage = lazy(() => importWithReload(() => import("./pages/AdminPage")));
const NewCase = lazy(() => importWithReload(() => import("./pages/NewCase")));
const CaseIntakeWizard = lazy(() => importWithReload(() => import("./pages/CaseIntakeWizard")));
const CaseList = lazy(() => importWithReload(() => import("./pages/CaseList")));
const NewClient = lazy(() => importWithReload(() => import("./pages/NewClient")));
const ClientList = lazy(() => importWithReload(() => import("./pages/ClientList")));
const CaseDetails = lazy(() => importWithReload(() => import("./pages/CaseDetails")));
const ActivityHistory = lazy(() => importWithReload(() => import("./pages/ActivityHistory")));
const ReportsPage = lazy(() => importWithReload(() => import("./pages/ReportsPage")));

// G184: pencere/sekme odağında yeniden çekme KAPALI. Açıkken 5 dk staleTime dolunca her
// odak useConfig'in 32 listesini (32 liste × odak = 32 istek) topluca yeniden çekiyordu.
// Tazelik mutasyon sonrası invalidate + staleTime/yeniden bağlanmayla gelir; bildirim
// sayacı react-query değil kendi setInterval + visibilitychange döngüsüdür (etkilenmez).
const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });

// Parça inerken gösterilen küçük gösterge. BrowserRouter gezinmeleri startTransition
// içinde yaptığı için sayfalar arası geçişte eski sayfa yerinde kalır; bu gösterge
// pratikte yalnız ilk açılışta (henüz çizilmiş içerik yokken) görünür.
const PageLoading = () => (
  <div
    role="status"
    aria-live="polite"
    className="min-h-screen flex items-center justify-center gap-2 bg-background text-sm text-muted-foreground"
  >
    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
    <span>Yükleniyor...</span>
  </div>
);

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
      <Suspense fallback={<PageLoading />}>
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
          <Route path="/new-case" element={<CaseList />} />
          <Route path="/cases" element={<CaseList />} />
          <Route path="/new-case/form" element={<NewCase />} />
          <Route path="/new-case/auto" element={<CaseIntakeWizard />} />
          <Route path="/new-client" element={<NewClient />} />
          <Route path="/clients" element={<ClientList />} />
          <Route path="/cases/:id" element={<CaseDetails />} />
          <Route path="/activity-history" element={<ActivityHistory />} />
          <Route
            path="/reports"
            element={
              <ProtectedAdminRoute>
                <ReportsPage />
              </ProtectedAdminRoute>
            }
          />
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
      </Suspense>
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
        // G182: sonner zaten statik yüklü (ui/sonner + 24 dosya) — dinamik import bölme yapmıyordu.
        toast.error("Oturum Açma Hatası", {
          description: "Giriş işlemi tamamlanamadı. Lütfen yetkili bir hesapla tekrar deneyin.",
          duration: 5000
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
              {/* Faz 4.4: render hatası SPA'yı boş ekrana çevirmesin — fallback + yenile */}
              <ErrorBoundary>
                <AppContent />
              </ErrorBoundary>
            </ConfirmDialogProvider>
          </TooltipProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </MsalProvider>
  );
};

export default App;
