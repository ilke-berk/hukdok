import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";
import { toast } from "sonner";
import {
  FileCheck,
  Mail,
  MailX,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
} from "lucide-react";

export interface ActivityReportDoc {
  id: number;
  filename: string;
  belge_turu: string;
  muvekkil: string;
  tracking_no: string;
  case_id: number | null;
  uploaded_at: string | null;
  email_error: string;
}

export interface ActivityReport {
  id: number;
  report_date: string;
  total_documents: number;
  mailed_documents: number;
  unmailed_documents: number;
  error_documents: number;
  has_unmailed: boolean;
  mailed_docs: ActivityReportDoc[];
  unmailed_docs: ActivityReportDoc[];
  error_docs: ActivityReportDoc[];
}

interface Props {
  report: ActivityReport;
  onClose: () => void;
  readOnly?: boolean;
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function DocList({
  docs,
  showError = false,
}: {
  docs: ActivityReportDoc[];
  showError?: boolean;
}) {
  if (docs.length === 0) {
    return (
      <p className="px-4 py-3 text-xs text-muted-foreground italic">
        Bu kategoride belge yok.
      </p>
    );
  }
  return (
    <ul className="divide-y border-t">
      {docs.map((d, i) => (
        <li key={d.id} className="px-4 py-2 text-xs">
          <div className="flex items-start gap-2">
            <span className="text-muted-foreground tabular-nums w-5 shrink-0">
              {i + 1}.
            </span>
            <div className="flex-1 min-w-0">
              <div className="font-medium truncate" title={d.filename}>
                {d.filename || "(dosya adı yok)"}
              </div>
              <div className="text-muted-foreground flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
                {d.muvekkil && <span>👤 {d.muvekkil}</span>}
                {d.belge_turu && <span>📄 {d.belge_turu}</span>}
                {d.tracking_no && <span>📁 {d.tracking_no}</span>}
              </div>
              {showError && d.email_error && (
                <div className="text-red-600 dark:text-red-400 mt-1 break-words">
                  ⚠ {d.email_error}
                </div>
              )}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

interface CategorySectionProps {
  icon: React.ReactNode;
  label: string;
  count: number;
  colorClass: string;
  docs: ActivityReportDoc[];
  showError?: boolean;
  defaultOpen?: boolean;
}

function CategorySection({
  icon,
  label,
  count,
  colorClass,
  docs,
  showError,
  defaultOpen,
}: CategorySectionProps) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className={`rounded-lg border ${colorClass}`}>
      <CollapsibleTrigger
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
        disabled={count === 0}
      >
        <span className="flex items-center gap-2 text-sm">
          {icon}
          {label}
        </span>
        <span className="flex items-center gap-2">
          <span className="font-semibold">{count}</span>
          {count > 0 && (
            <ChevronDown
              className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`}
            />
          )}
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <DocList docs={docs} showError={showError} />
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ActivityReportModal({ report, onClose, readOnly = false }: Props) {
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
    <Dialog open onOpenChange={(open) => { if (!open) { if (readOnly) onClose(); else handleAcknowledge(); } }}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileCheck className="h-5 w-5 text-primary" />
            Günlük Arşiv Özeti — {dateStr}
          </DialogTitle>
          <DialogDescription>
            {readOnly
              ? `${dateStr} tarihindeki belge işlem geçmişi`
              : `${dateStr} tarihinde sizin işlediğiniz belgelerin özeti`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {/* Toplam */}
          <div className="flex items-center justify-between rounded-lg border px-4 py-3 bg-muted/30">
            <span className="text-sm text-muted-foreground">Toplam işlediğiniz belge</span>
            <span className="font-semibold text-lg">{report.total_documents}</span>
          </div>

          {/* Mailli */}
          <CategorySection
            icon={<Mail className="h-4 w-4 text-green-700 dark:text-green-400" />}
            label="E-posta ile iletildi"
            count={report.mailed_documents}
            colorClass="border-green-500/20 bg-green-500/5 text-green-700 dark:text-green-400"
            docs={report.mailed_docs}
          />

          {/* Mailsiz */}
          <CategorySection
            icon={<MailX className="h-4 w-4 text-amber-700 dark:text-amber-400" />}
            label="E-postasız arşivlendi"
            count={report.unmailed_documents}
            colorClass="border-amber-500/20 bg-amber-500/5 text-amber-700 dark:text-amber-400"
            docs={report.unmailed_docs}
            defaultOpen={report.unmailed_documents > 0}
          />

          {/* Hatalı */}
          <CategorySection
            icon={<AlertCircle className="h-4 w-4 text-red-700 dark:text-red-400" />}
            label="E-posta gönderilemedi (hata)"
            count={report.error_documents}
            colorClass="border-red-500/20 bg-red-500/5 text-red-700 dark:text-red-400"
            docs={report.error_docs}
            showError
            defaultOpen={report.error_documents > 0}
          />

          {!readOnly && report.has_unmailed && (
            <p className="text-sm text-muted-foreground pt-1">
              <strong>{report.unmailed_documents} adet</strong> belge e-posta gönderilmeden
              arşivlendi. Bu belgeler için bildirim göndermek ister misiniz?
            </p>
          )}
        </div>

        <DialogFooter className="flex-col gap-2 sm:flex-row">
          {readOnly ? (
            <Button variant="outline" onClick={onClose}>Kapat</Button>
          ) : report.has_unmailed ? (
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
