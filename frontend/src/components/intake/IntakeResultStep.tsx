import { AlertCircle, CheckCircle2, Clock, ExternalLink, RotateCcw } from "lucide-react";
import { Link } from "react-router-dom";

import { FlowButton, FlowCard } from "@/components/flow/primitives";
import type { CommitResult } from "@/lib/caseIntake";

interface IntakeResultStepProps {
  result: CommitResult;
  /** process_id → orijinal dosya adı (sonuç satırında ad göstermek için) */
  filenames: Record<string, string>;
  onRestart: () => void;
}

const STATUS_META = {
  queued: { icon: CheckCircle2, cls: "text-emerald-600", label: "Arşive kuyruklandı" },
  failed: { icon: AlertCircle, cls: "text-[var(--brand)]", label: "Başarısız" },
  expired: { icon: Clock, cls: "text-amber-600", label: "Süresi dolmuş" },
} as const;

/**
 * Adım 4 — Sonuç: dava linki + belge başına arşiv durumu. failed/expired
 * belgeler için yönlendirme: dava kartından yeniden yükleme (karar 4 —
 * commit retry YOK, dava zaten oluştu).
 */
export function IntakeResultStep({ result, filenames, onRestart }: IntakeResultStepProps) {
  const failedCount = result.documents.filter(d => d.status !== "queued").length;
  const missing = result.case.missing_required_fields ?? [];

  return (
    <div className="grid gap-5 max-w-[720px]">
      <FlowCard className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-11 h-11 grid place-items-center shrink-0 bg-emerald-500/10 text-emerald-600">
            <CheckCircle2 className="w-5 h-5" strokeWidth={1.8} />
          </div>
          <div className="min-w-0">
            <p className="font-display text-[17px] font-medium text-[var(--fg)]">
              Dava oluşturuldu
            </p>
            <p className="font-mono text-[12px] text-[var(--fg-muted)] mt-0.5">
              Ofis No: {result.case.tracking_no}
            </p>
          </div>
        </div>
        <Link to={`/cases/${result.case.id}`}>
          <FlowButton variant="primary">
            Davaya Git <ExternalLink className="w-3.5 h-3.5" />
          </FlowButton>
        </Link>
      </FlowCard>

      {missing.length > 0 && (
        <FlowCard className="border-amber-500/40 bg-amber-500/5">
          <p className="text-[13px] text-[var(--fg)] leading-relaxed">
            <span className="font-semibold text-amber-600">Zorunlu alanlar eksik:</span>
            {" "}<span className="font-medium">{missing.map(m => m.label).join(", ")}</span>.
            {" "}Dosya dava panelinde "eksik alan" uyarısıyla görünecek — dava kartından tamamlayabilirsiniz.
          </p>
        </FlowCard>
      )}

      <FlowCard padded={false}>
        <div className="px-5 py-3 border-b border-[var(--border)]">
          <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
            Belge arşiv durumu
            {failedCount > 0 && <span className="text-[var(--brand)]"> · {failedCount} sorunlu</span>}
          </span>
        </div>
        <ul className="divide-y divide-[var(--border)]">
          {result.documents.map(d => {
            const meta = STATUS_META[d.status];
            const Icon = meta.icon;
            return (
              <li key={d.process_id} className="px-5 py-3 flex items-start gap-3">
                <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${meta.cls}`} strokeWidth={1.8} />
                <div className="min-w-0">
                  <p className="text-[13px] text-[var(--fg)] break-all">
                    {filenames[d.process_id] || d.process_id}
                  </p>
                  <p className={`text-[12px] mt-0.5 ${d.status === "queued" ? "text-[var(--fg-muted)]" : meta.cls}`}>
                    {meta.label}{d.error_ozet ? ` — ${d.error_ozet}` : ""}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
        {(result.policies.saved > 0 || result.policies.skipped > 0 || result.policies.error) && (
          <div className="px-5 py-3 border-t border-[var(--border)] text-[12px] text-[var(--fg-muted)]">
            Poliçeler: {result.policies.saved} kaydedildi, {result.policies.skipped} zaten kayıtlıydı.
            {result.policies.error && (
              <span className="text-[var(--brand)]"> {result.policies.error}</span>
            )}
          </div>
        )}
      </FlowCard>

      <div>
        <FlowButton variant="secondary" onClick={onRestart}>
          <RotateCcw className="w-3.5 h-3.5" />
          Yeni Sihirbaz Başlat
        </FlowButton>
      </div>
    </div>
  );
}
