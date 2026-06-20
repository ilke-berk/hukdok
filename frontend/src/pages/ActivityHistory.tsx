import { useEffect, useState } from "react";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { Loader2, Eye, FileText, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { apiClient } from "@/lib/api";
import { toast } from "sonner";
import {
  ActivityReportModal,
  ActivityReport,
} from "@/components/ActivityReportModal";
import { MetricCard, SectionHeader, HairlineCard, Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";

interface HistoryRow {
  id: number;
  report_date: string;
  total_documents: number;
  mailed_documents: number;
  unmailed_documents: number;
  error_documents: number;
  is_acknowledged: boolean;
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function formatWeekday(iso: string): string {
  try {
    return new Date(iso + "T00:00:00").toLocaleDateString("tr-TR", { weekday: "short" });
  } catch {
    return "";
  }
}

const ActivityHistory = () => {
  useSetPageTitle("Aktivite Geçmişi", ["Avukat Paneli"]);
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ActivityReport | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await apiClient.fetch("/api/activity/history?days=30");
      if (!res.ok) throw new Error("Liste alınamadı");
      const data = await res.json();
      setRows(Array.isArray(data) ? data : []);
    } catch {
      toast.error("Geçmiş yüklenemedi.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleOpen = async (id: number) => {
    setOpeningId(id);
    try {
      const res = await apiClient.fetch(`/api/activity/history/${id}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setDetail({
        ...data,
        has_unmailed: data.unmailed_documents > 0,
      } as ActivityReport);
    } catch {
      toast.error("Rapor detayı yüklenemedi.");
    } finally {
      setOpeningId(null);
    }
  };

  const totalSummary = rows.reduce(
    (acc, r) => ({
      total: acc.total + r.total_documents,
      mailed: acc.mailed + r.mailed_documents,
      unmailed: acc.unmailed + r.unmailed_documents,
      errors: acc.errors + r.error_documents,
    }),
    { total: 0, mailed: 0, unmailed: 0, errors: 0 }
  );

  return (
    <div className="grid gap-7">

      {/* Başlık */}
      <div>
        <Eyebrow>01 · Günlük</Eyebrow>
        <h1 className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium">
          Aktivite Geçmişim
        </h1>
        <p className="text-[13px] text-[var(--fg-muted)] mt-2 max-w-[60ch] leading-relaxed">
          Son 30 gün içinde işlediğiniz belgelerin günlük raporları. Bir satıra tıklayarak
          o günün detaylı belge listesini görebilirsiniz.
        </p>
      </div>

      {/* Metrikler */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Toplam Belge"
          value={loading ? "—" : totalSummary.total}
          icon={<FileText className="w-4 h-4" />}
          tone="brand"
          hint="Son 30 gün"
        />
        <MetricCard
          label="E-posta ile İletildi"
          value={loading ? "—" : totalSummary.mailed}
          icon={<CheckCircle2 className="w-4 h-4" />}
          tone="success"
          hint="Başarılı gönderim"
        />
        <MetricCard
          label="E-postasız"
          value={loading ? "—" : totalSummary.unmailed}
          icon={<AlertTriangle className="w-4 h-4" />}
          tone="warning"
          hint="Manuel iletim"
        />
        <MetricCard
          label="Hatalı"
          value={loading ? "—" : totalSummary.errors}
          icon={<XCircle className="w-4 h-4" />}
          tone="neutral"
          hint="İşlenemeyen"
        />
      </section>

      {/* Tablo */}
      <HairlineCard padded={false}>
        <div className="px-5 py-4 border-b border-[var(--border)]">
          <SectionHeader
            eyebrow="02 · Dönem"
            title="Günlük Raporlar"
            italic="— son 30 gün"
            meta={
              <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                {loading ? "Yükleniyor…" : `${rows.length} gün`}
              </span>
            }
          />
        </div>

        {loading ? (
          <div className="grid place-items-center gap-3 py-20 text-[var(--fg-subtle)]">
            <Loader2 className="w-7 h-7 animate-spin" />
            <span className="font-mono text-[10px] tracking-[0.18em] uppercase">Yükleniyor</span>
          </div>
        ) : rows.length === 0 ? (
          <div className="grid place-items-center gap-3 py-20 text-center text-[var(--fg-subtle)]">
            <FileText className="w-9 h-9 opacity-30" />
            <p className="text-[13px]">Son 30 gün içinde size ait rapor bulunamadı.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-[var(--bg)] border-b border-[var(--border)]">
                  <th className="text-left px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">Tarih</th>
                  <th className="text-right px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">Toplam</th>
                  <th className="text-right px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">Mailli</th>
                  <th className="text-right px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">Mailsiz</th>
                  <th className="text-right px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">Hatalı</th>
                  <th className="text-left px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">Durum</th>
                  <th className="text-right px-5 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr
                    key={r.id}
                    onClick={() => handleOpen(r.id)}
                    className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--bg)] cursor-pointer transition-colors"
                  >
                    <td className="px-5 py-3.5 align-middle">
                      <div className="font-mono text-[13px] tabular-nums text-[var(--fg)] font-medium">
                        {formatDate(r.report_date)}
                      </div>
                      <div className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] mt-0.5">
                        {formatWeekday(r.report_date)}
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-right font-mono text-[14px] tabular-nums font-medium text-[var(--fg)]">
                      {r.total_documents}
                    </td>
                    <td className="px-5 py-3.5 text-right font-mono text-[13px] tabular-nums text-[#2f8a5d]">
                      {r.mailed_documents}
                    </td>
                    <td className="px-5 py-3.5 text-right font-mono text-[13px] tabular-nums text-[#c47a1e]">
                      {r.unmailed_documents}
                    </td>
                    <td className="px-5 py-3.5 text-right font-mono text-[13px] tabular-nums text-[#a8323b]">
                      {r.error_documents}
                    </td>
                    <td className="px-5 py-3.5 align-middle">
                      {r.is_acknowledged ? (
                        <span className="inline-flex items-center gap-1 font-mono text-[10px] tracking-[0.12em] uppercase text-[#2f8a5d]">
                          <CheckCircle2 className="w-3 h-3" />
                          Onaylandı
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 font-mono text-[10px] tracking-[0.12em] uppercase text-[#c47a1e]">
                          <AlertTriangle className="w-3 h-3" />
                          Bekliyor
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <FlowButton
                        variant="ghost"
                        size="sm"
                        disabled={openingId !== null}
                        onClick={(e) => { e.stopPropagation(); handleOpen(r.id); }}
                      >
                        {openingId === r.id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <>
                            <Eye className="w-3.5 h-3.5" />
                            Detay
                          </>
                        )}
                      </FlowButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </HairlineCard>

      {detail && (
        <ActivityReportModal
          report={detail}
          onClose={() => setDetail(null)}
          readOnly
        />
      )}
    </div>
  );
};

export default ActivityHistory;
