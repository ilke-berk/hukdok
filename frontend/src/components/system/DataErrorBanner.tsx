import { AlertTriangle, RefreshCw } from "lucide-react";
import { FlowButton } from "@/components/flow/primitives";

interface DataErrorBannerProps {
  /** Hook'un fırlattığı hata mesajı — hangi listenin alınamadığını söyler. */
  description?: string;
  /** Verilirse "Tekrar dene" butonu çıkar. */
  onRetry?: () => void;
  /** Tekrar denenirken butonu kilitler ve ikonu döndürür. */
  isRetrying?: boolean;
  className?: string;
}

/**
 * G002: Liste uçları kesintide artık boş liste DEĞİL hata döndürüyor. Bu şerit,
 * o hatayı "kayıt yok" görünümünün YERİNE gösterir — kullanıcı kesintiyi veri
 * kaybıyla karıştırmasın diye kayıtların yerinde durduğu açıkça yazılır.
 */
export function DataErrorBanner({
  description,
  onRetry,
  isRetrying = false,
  className = "",
}: DataErrorBannerProps) {
  return (
    <div
      role="alert"
      className={`flex items-start gap-3 border border-[var(--danger,#b3261e)]/40 bg-[var(--danger,#b3261e)]/5 px-4 py-3 ${className}`}
    >
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-[var(--danger,#b3261e)]" />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium text-[var(--fg)]">
          Sunucuya ulaşılamadı — liste yüklenemedi.
        </p>
        <p className="text-[12px] text-[var(--fg-muted)] mt-0.5">
          {description ? `${description} ` : ""}
          Bu bir bağlantı/sunucu hatasıdır; kayıtlarınız silinmedi.
        </p>
      </div>
      {onRetry && (
        <FlowButton variant="secondary" size="sm" onClick={onRetry} disabled={isRetrying}>
          <RefreshCw className={`w-3.5 h-3.5 ${isRetrying ? "animate-spin" : ""}`} />
          Tekrar dene
        </FlowButton>
      )}
    </div>
  );
}
