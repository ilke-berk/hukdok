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
import { Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";
import { apiClient } from "@/lib/api";
import { toast } from "sonner";
import {
  FileCheck,
  Mail,
  MailX,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Loader2,
  User,
  FileText,
  FolderOpen,
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

type Tone = "success" | "warning" | "error";

const TONE: Record<Tone, { color: string; soft: string }> = {
  success: { color: "#2f8a5d", soft: "rgba(47, 138, 93, 0.12)" },
  warning: { color: "#c47a1e", soft: "rgba(196, 122, 30, 0.12)" },
  error: { color: "#c0453a", soft: "rgba(192, 69, 58, 0.12)" },
};

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
      <p className="px-4 py-3 font-mono text-[10px] tracking-[0.08em] uppercase text-[var(--fg-subtle)]">
        Bu kategoride belge yok.
      </p>
    );
  }
  return (
    <ul className="border-t border-[var(--border)] divide-y divide-[var(--border)]">
      {docs.map((d, i) => (
        <li key={d.id} className="px-4 py-2.5 flex items-start gap-2.5">
          <span className="font-mono text-[10px] text-[var(--fg-subtle)] tabular-nums w-5 shrink-0 pt-0.5">
            {String(i + 1).padStart(2, "0")}
          </span>
          <div className="flex-1 min-w-0">
            <div
              className="font-mono text-[11.5px] text-[var(--fg)] truncate"
              title={d.filename}
            >
              {d.filename || "(dosya adı yok)"}
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[10.5px] text-[var(--fg-muted)]">
              {d.muvekkil && (
                <span className="inline-flex items-center gap-1">
                  <User className="w-3 h-3" strokeWidth={1.8} /> {d.muvekkil}
                </span>
              )}
              {d.belge_turu && (
                <span className="inline-flex items-center gap-1">
                  <FileText className="w-3 h-3" strokeWidth={1.8} /> {d.belge_turu}
                </span>
              )}
              {d.tracking_no && (
                <span className="inline-flex items-center gap-1 font-mono">
                  <FolderOpen className="w-3 h-3" strokeWidth={1.8} /> {d.tracking_no}
                </span>
              )}
            </div>
            {showError && d.email_error && (
              <div
                className="mt-1.5 flex items-start gap-1.5 text-[10.5px] break-words"
                style={{ color: TONE.error.color }}
              >
                <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" strokeWidth={1.8} />
                <span>{d.email_error}</span>
              </div>
            )}
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
  tone: Tone;
  docs: ActivityReportDoc[];
  showError?: boolean;
  defaultOpen?: boolean;
}

function CategorySection({
  icon,
  label,
  count,
  tone,
  docs,
  showError,
  defaultOpen,
}: CategorySectionProps) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  const t = TONE[tone];
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="border border-[var(--border)] bg-[var(--bg)]"
      style={{ borderLeft: `2px solid ${t.color}` }}
    >
      <CollapsibleTrigger
        className="w-full flex items-center justify-between px-4 py-3 transition-colors hover:bg-[var(--bg-sunken)] disabled:hover:bg-transparent disabled:cursor-default"
        disabled={count === 0}
      >
        <span className="flex items-center gap-2.5">
          <span
            className="w-7 h-7 grid place-items-center shrink-0"
            style={{ background: t.soft, color: t.color }}
          >
            {icon}
          </span>
          <span className="text-[13px] font-medium text-[var(--fg)]">{label}</span>
        </span>
        <span className="flex items-center gap-2.5">
          <span
            className="font-display text-[18px] font-medium leading-none tabular-nums"
            style={{ color: count > 0 ? t.color : "var(--fg-subtle)" }}
          >
            {count}
          </span>
          {count > 0 && (
            <ChevronDown
              className={`w-3.5 h-3.5 text-[var(--fg-subtle)] transition-transform ${open ? "rotate-180" : ""}`}
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
      <DialogContent className="theme-classic max-w-lg max-h-[88vh] overflow-y-auto bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none p-0 gap-0">
        {/* Üst brand accent şeridi */}
        <div className="h-[3px] bg-[var(--brand)]" aria-hidden="true" />

        <DialogHeader className="px-6 pt-5 pb-4 border-b border-[var(--border)] space-y-0 text-left">
          <div className="flex items-start gap-3">
            <div className="w-11 h-11 grid place-items-center bg-[var(--brand-soft)] text-[var(--brand)] shrink-0">
              <FileCheck className="w-5 h-5" strokeWidth={1.8} />
            </div>
            <div className="grid gap-1 min-w-0">
              <Eyebrow tone="brand">Günlük Arşiv · {dateStr}</Eyebrow>
              <DialogTitle className="font-display text-[20px] font-medium tracking-[-0.005em] text-[var(--fg)] leading-tight">
                Günlük Arşiv Özeti
              </DialogTitle>
              <DialogDescription className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed">
                {readOnly
                  ? `${dateStr} tarihindeki belge işlem geçmişi`
                  : `${dateStr} tarihinde sizin işlediğiniz belgelerin özeti`}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="grid gap-3 px-6 py-5">
          {/* Toplam */}
          <div className="flex items-center justify-between border border-[var(--border)] bg-[var(--bg-sunken)] px-4 py-3.5">
            <span className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
              Toplam işlediğiniz belge
            </span>
            <span className="font-display text-[26px] font-medium leading-none tabular-nums text-[var(--fg)]">
              {report.total_documents}
            </span>
          </div>

          {/* Mailli */}
          <CategorySection
            icon={<Mail className="w-3.5 h-3.5" strokeWidth={1.8} />}
            label="E-posta ile iletildi"
            count={report.mailed_documents}
            tone="success"
            docs={report.mailed_docs}
          />

          {/* Mailsiz */}
          <CategorySection
            icon={<MailX className="w-3.5 h-3.5" strokeWidth={1.8} />}
            label="E-postasız arşivlendi"
            count={report.unmailed_documents}
            tone="warning"
            docs={report.unmailed_docs}
            defaultOpen={report.unmailed_documents > 0}
          />

          {/* Hatalı */}
          <CategorySection
            icon={<AlertCircle className="w-3.5 h-3.5" strokeWidth={1.8} />}
            label="E-posta gönderilemedi (hata)"
            count={report.error_documents}
            tone="error"
            docs={report.error_docs}
            showError
            defaultOpen={report.error_documents > 0}
          />

          {!readOnly && report.has_unmailed && (
            <div
              className="border-l-2 px-4 py-3"
              style={{ background: TONE.warning.soft, borderLeftColor: TONE.warning.color }}
            >
              <p className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed">
                <strong className="text-[var(--fg)] font-semibold">
                  {report.unmailed_documents} adet
                </strong>{" "}
                belge e-posta gönderilmeden arşivlendi. Bu belgeler için bildirim göndermek
                ister misiniz?
              </p>
            </div>
          )}
        </div>

        <DialogFooter className="px-6 py-4 gap-2 border-t border-[var(--border)] bg-[var(--bg)] sm:justify-end">
          {readOnly ? (
            <FlowButton variant="secondary" onClick={onClose}>
              Kapat
            </FlowButton>
          ) : report.has_unmailed ? (
            <>
              <FlowButton
                variant="secondary"
                onClick={handleAcknowledge}
                disabled={loading !== null}
              >
                {loading === "acknowledge" ? (
                  <><Loader2 className="w-3.5 h-3.5 animate-spin" /> İşleniyor…</>
                ) : (
                  <><CheckCircle2 className="w-3.5 h-3.5" /> Evet, mailsiz kaydı onaylıyorum</>
                )}
              </FlowButton>
              <FlowButton
                variant="primary"
                onClick={handleSendEmails}
                disabled={loading !== null}
              >
                {loading === "send" ? (
                  <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Gönderiliyor…</>
                ) : (
                  <><Mail className="w-3.5 h-3.5" /> Bildirim e-postası gönder</>
                )}
              </FlowButton>
            </>
          ) : (
            <FlowButton variant="primary" onClick={handleAcknowledge} disabled={loading !== null}>
              {loading === "acknowledge" ? (
                <><Loader2 className="w-3.5 h-3.5 animate-spin" /> İşleniyor…</>
              ) : (
                "Tamam"
              )}
            </FlowButton>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
