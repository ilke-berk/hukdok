import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";
import { toast } from "sonner";
import { FileCheck, Mail, MailX, AlertCircle, CheckCircle2 } from "lucide-react";

export interface ActivityReport {
  id: number;
  report_date: string;
  total_documents: number;
  mailed_documents: number;
  unmailed_documents: number;
  error_documents: number;
  has_unmailed: boolean;
}

interface Props {
  report: ActivityReport;
  onClose: () => void;
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

export function ActivityReportModal({ report, onClose }: Props) {
  const [loading, setLoading] = useState<"acknowledge" | "send" | null>(null);

  const handleAcknowledge = async () => {
    setLoading("acknowledge");
    try {
      await apiClient.fetch(`/api/activity/daily-report/${report.id}/acknowledge`, {
        method: "POST",
      });
      onClose();
    } catch {
      toast.error("Onaylama başarısız, lütfen tekrar deneyin.");
    } finally {
      setLoading(null);
    }
  };

  const handleSendEmails = async () => {
    setLoading("send");
    try {
      const res = await apiClient.fetch(
        `/api/activity/daily-report/${report.id}/send-emails`,
        { method: "POST" }
      );
      const data = await res.json();
      toast.success(data.message || "Bildirim e-postası gönderiliyor.");
      onClose();
    } catch {
      toast.error("E-posta gönderimi başlatılamadı.");
    } finally {
      setLoading(null);
    }
  };

  const dateStr = formatDate(report.report_date);

  return (
    <Dialog open onOpenChange={(open) => { if (!open) handleAcknowledge(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileCheck className="h-5 w-5 text-primary" />
            Günlük Arşiv Özeti — {dateStr}
          </DialogTitle>
          <DialogDescription>
            Dün gerçekleştirilen belge arşiv işlemlerinin özeti
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {/* Toplam */}
          <div className="flex items-center justify-between rounded-lg border px-4 py-3">
            <span className="text-sm text-muted-foreground">Toplam yüklenen belge</span>
            <span className="font-semibold text-lg">{report.total_documents}</span>
          </div>

          {/* Mailenmiş */}
          <div className="flex items-center justify-between rounded-lg border border-green-500/20 bg-green-500/5 px-4 py-3">
            <span className="flex items-center gap-2 text-sm text-green-700 dark:text-green-400">
              <Mail className="h-4 w-4" />
              E-posta ile iletildi
            </span>
            <span className="font-semibold text-green-700 dark:text-green-400">
              {report.mailed_documents}
            </span>
          </div>

          {/* Mailsiz */}
          {report.unmailed_documents > 0 && (
            <div className="flex items-center justify-between rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3">
              <span className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
                <MailX className="h-4 w-4" />
                E-posta gönderilmeden kaydedildi
              </span>
              <span className="font-semibold text-amber-700 dark:text-amber-400">
                {report.unmailed_documents}
              </span>
            </div>
          )}

          {/* Hatalı */}
          {report.error_documents > 0 && (
            <div className="flex items-center justify-between rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3">
              <span className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400">
                <AlertCircle className="h-4 w-4" />
                E-posta gönderilemedi (hata)
              </span>
              <span className="font-semibold text-red-700 dark:text-red-400">
                {report.error_documents}
              </span>
            </div>
          )}

          {/* Soru */}
          {report.has_unmailed && (
            <p className="text-sm text-muted-foreground pt-1">
              <strong>{report.unmailed_documents} adet</strong> belge e-posta gönderilmeden
              arşivlendi. Bu belgeler için bildirim göndermek ister misiniz?
            </p>
          )}
        </div>

        <DialogFooter className="flex-col gap-2 sm:flex-row">
          {report.has_unmailed ? (
            <>
              <Button
                variant="outline"
                onClick={handleAcknowledge}
                disabled={loading !== null}
                className="flex items-center gap-2"
              >
                <CheckCircle2 className="h-4 w-4" />
                {loading === "acknowledge" ? "İşleniyor..." : "Evet, mailsiz kaydı onaylıyorum"}
              </Button>
              <Button
                onClick={handleSendEmails}
                disabled={loading !== null}
                className="flex items-center gap-2"
              >
                <Mail className="h-4 w-4" />
                {loading === "send" ? "Gönderiliyor..." : "Bildirim e-postası gönder"}
              </Button>
            </>
          ) : (
            <Button onClick={handleAcknowledge} disabled={loading !== null}>
              {loading === "acknowledge" ? "İşleniyor..." : "Tamam"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
