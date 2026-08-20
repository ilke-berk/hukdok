import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { FileText, ArrowRight, User } from "lucide-react";
import { apiClient } from "@/lib/api";
import { HairlineCard } from "@/components/dashboard/primitives";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { formatAgo } from "@/lib/relativeTime";

/**
 * G079 — Avukat panosu "Yeni İşlenen — son 24 saat" akışı.
 *
 * Kaynak uç G078'de yazıldı: `GET /api/documents/recent?since_hours=…&limit=…`.
 * Uç YALNIZ dava bağlamı olan (case_id NOT NULL), silinmemiş ve tenant'ı eşleşen
 * belgeleri döner — bu panel filtre/kural kopyalamaz, gelen listeyi çizer.
 *
 * Mail rozeti üç ayrı durumu gösterir; alanları YAZAN taraf (document_pipeline,
 * resend-email) bu görevde DEĞİŞMEDİ — burada yalnız durum görünür oluyor.
 */

export interface RecentDocument {
  id: number;
  case_id: number;
  tracking_no?: string | null;
  esas_no?: string | null;
  original_filename?: string | null;
  belge_turu_kodu?: string | null;
  belge_turu_adi?: string | null;
  case_party_name?: string | null;
  muvekkil_adi?: string | null;
  uploaded_at?: string | null;
  uploaded_by?: string | null;
  email_sent?: boolean | null;
  email_error?: string | null;
}

export const RECENT_DOCS_ERROR = "Son işlenen belgeler alınamadı.";

type MailState = "sent" | "failed" | "none";

const MAIL_META: Record<MailState, { label: string; className: string }> = {
  // Üç durum renk + metin + nokta dolgusuyla ayrışır; yalnız renge yaslanmaz.
  sent: {
    label: "mail gönderildi",
    className: "text-[#2f8a5d] border-[#2f8a5d]/40 bg-[#2f8a5d]/10",
  },
  failed: {
    label: "mail hatası",
    className: "text-[var(--danger,#b3261e)] border-[var(--danger,#b3261e)]/40 bg-[var(--danger,#b3261e)]/10",
  },
  none: {
    label: "mail gönderilmedi",
    className: "text-[var(--fg-subtle)] border-[var(--border)] bg-[var(--bg-sunken)]",
  },
};

/**
 * `email_sent` üç değerlidir ve üçü de FARKLI anlam taşır:
 *   true  → müvekkil bilgilendirme maili gitti
 *   false → gönderim DENENDİ ve başarısız (email_error dolu olabilir)
 *   null  → hiç denenmedi (bu belge türü mail göndermiyor ya da sırada)
 * `!email_sent` kısayolu false ile null'ı birleştirip hatayı gizlerdi.
 */
function mailState(sent: boolean | null | undefined): MailState {
  if (sent === true) return "sent";
  if (sent === false) return "failed";
  return "none";
}

/** Doctype kodları `_` ile pad'lidir (TEBLIGAT______) — gösterimden önce kırpılır. */
function docTitle(doc: RecentDocument): string {
  const adi = doc.belge_turu_adi?.trim();
  if (adi) return adi;
  const kod = doc.belge_turu_kodu?.replace(/_+$/, "").trim();
  if (kod) return kod;
  return doc.original_filename?.trim() || "Belge";
}

function MailBadge({ doc }: { doc: RecentDocument }) {
  const state = mailState(doc.email_sent);
  const meta = MAIL_META[state];
  return (
    <span
      data-testid="mail-badge"
      data-mail-state={state}
      title={state === "failed" && doc.email_error ? doc.email_error : undefined}
      className={`inline-flex items-center gap-1.5 shrink-0 px-1.5 py-0.5 border font-mono text-[9px] tracking-[0.14em] uppercase font-semibold ${meta.className}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full border border-current ${state === "none" ? "" : "bg-current"}`}
      />
      {meta.label}
    </span>
  );
}

interface RecentDocumentsPanelProps {
  /** Pencere genişliği — uç 1..720 saat kabul eder. */
  sinceHours?: number;
  limit?: number;
  /** Boş durumda gösterilen "Belge Yükle" kısayolu. */
  onUpload?: () => void;
}

export function RecentDocumentsPanel({ sinceHours = 24, limit = 8, onUpload }: RecentDocumentsPanelProps) {
  const navigate = useNavigate();
  const [docs, setDocs] = useState<RecentDocument[]>([]);
  const [loading, setLoading] = useState(true);
  // null = hata yok. Boş liste ile kesinti AYRI durumlardır (G002 dersi).
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const retry = useCallback(() => setReloadKey(k => k + 1), []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const response = await apiClient.fetch(
          `/api/documents/recent?since_hours=${sinceHours}&limit=${limit}`,
        );
        if (!response.ok) throw new Error(RECENT_DOCS_ERROR);
        const data: unknown = await response.json();
        if (cancelled) return;
        setDocs(Array.isArray(data) ? (data as RecentDocument[]) : []);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        console.warn("Son işlenen belgeler alınamadı:", err);
        setError(err instanceof Error && err.message ? err.message : RECENT_DOCS_ERROR);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sinceHours, limit, reloadKey]);

  if (loading) {
    return (
      <HairlineCard className="mt-3" padded={false}>
        <div className="p-4 grid gap-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-14 bg-[var(--bg-sunken)] animate-pulse" />
          ))}
        </div>
      </HairlineCard>
    );
  }

  if (error) {
    return (
      <HairlineCard className="mt-3" padded={false}>
        <DataErrorBanner description={error} onRetry={retry} className="border-0" />
      </HairlineCard>
    );
  }

  if (docs.length === 0) {
    return (
      <HairlineCard className="mt-3">
        <div className="grid place-items-center gap-3 py-8 text-center text-[var(--fg-subtle)]">
          <FileText className="w-8 h-8 opacity-40" />
          <div>
            <p className="text-[13px] text-[var(--fg-muted)] font-medium">
              Son 24 saatte işlenen belge yok
            </p>
            <p className="text-[11px] mt-1.5 max-w-[28ch] mx-auto leading-relaxed">
              AI ile analiz edilip davaya bağlanan belgeler burada akış halinde görünür.
            </p>
          </div>
          {onUpload && (
            <button
              type="button"
              onClick={onUpload}
              className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] inline-flex items-center gap-1 mt-2 pb-1 border-b border-[var(--border)] hover:border-[var(--brand)]"
            >
              Belge Yükle <ArrowRight className="w-3 h-3" />
            </button>
          )}
        </div>
      </HairlineCard>
    );
  }

  return (
    <HairlineCard className="mt-3" padded={false}>
      <div className="flex flex-col">
        {docs.map((doc, idx) => {
          const caseNo = doc.esas_no || doc.tracking_no;
          const party = doc.case_party_name || doc.muvekkil_adi;
          return (
            <button
              key={doc.id}
              type="button"
              data-testid="recent-doc-row"
              onClick={() => navigate(`/cases/${doc.case_id}`)}
              className={`grid grid-cols-[auto_1fr] gap-3 items-start px-4 py-3 text-left transition-colors hover:bg-[var(--bg)] ${idx > 0 ? "border-t border-[var(--border)]" : ""}`}
            >
              <FileText className="w-4 h-4 text-[var(--brand)] mt-0.5 shrink-0" />
              <div className="min-w-0">
                <div className="flex items-baseline justify-between gap-2 min-w-0">
                  <span className="font-display font-medium text-[13.5px] text-[var(--fg)] truncate">
                    {docTitle(doc)}
                  </span>
                  <span className="font-mono text-[10px] tracking-[0.04em] text-[var(--fg-subtle)] tabular-nums whitespace-nowrap shrink-0">
                    {formatAgo(doc.uploaded_at)}
                  </span>
                </div>
                {party && (
                  <div className="text-[12px] text-[var(--fg-muted)] mt-1 truncate inline-flex items-center gap-1.5 max-w-full">
                    <User className="w-3 h-3 shrink-0" />
                    <span className="truncate">{party}</span>
                  </div>
                )}
                <div className="flex items-center justify-between gap-2 mt-1.5 min-w-0">
                  {caseNo ? (
                    <span className="font-mono text-[10.5px] tracking-[0.04em] text-[var(--brand)] truncate">
                      № {caseNo}
                    </span>
                  ) : (
                    <span />
                  )}
                  <MailBadge doc={doc} />
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </HairlineCard>
  );
}

export default RecentDocumentsPanel;
