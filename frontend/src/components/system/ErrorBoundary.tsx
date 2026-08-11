import { Component, type ErrorInfo, type ReactNode } from "react";
import { reportCaughtRenderError } from "@/lib/errorBeacon";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

/**
 * Faz 4.4: <AppContent/> çevresindeki son savunma hattı. Boundary'siz her
 * render hatası tüm SPA'yı sessizce boş beyaz ekrana çeviriyordu — kullanıcı
 * "site çöktü" sanıp ne olduğunu bildiremiyordu.
 *
 * Bilinçli olarak küçük bir class component (react-error-boundary paketi
 * EKLENMEDİ — tek kullanım için bağımlılık gerekmez). Render hataları window
 * "error" olayına düşmediğinden beacon'ın global dinleyicileri bunları
 * göremez; componentDidCatch'ten errorBeacon'a elle raporlanır (aynı
 * kısma/dedup kuralları geçerli).
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    // Konsol prod'da susturulur (main.tsx) — sunucudan görünürlük beacon'la.
    console.error("ErrorBoundary render hatası yakaladı:", error, info.componentStack);
    reportCaughtRenderError(error, info.componentStack ?? undefined);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-background">
          <div className="text-center max-w-md px-6">
            <h1 className="mb-3 text-2xl font-bold text-foreground">Beklenmedik bir hata oluştu</h1>
            <p className="mb-6 text-muted-foreground">
              Sayfa görüntülenirken bir sorun yaşandı ve ekip bilgilendirildi.
              Sayfayı yenilemek genellikle sorunu çözer; kaydedilmemiş son
              girdileriniz kaybolmuş olabilir.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex items-center justify-center rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Sayfayı Yenile
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
