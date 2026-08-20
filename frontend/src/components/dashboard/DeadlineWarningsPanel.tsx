import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { AlertTriangle, CalendarClock, Info } from "lucide-react";
import { apiClient } from "@/lib/api";
import { HairlineCard } from "@/components/dashboard/primitives";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import type { NotificationItem } from "@/hooks/useNotifications";
import {
  DEADLINE_DISCLAIMER,
  DURUSMA_TYPE,
  countdownLabel,
  selectDeadlineRows,
  type DeadlineRow,
} from "@/components/dashboard/deadlineBody";

/**
 * G086 — Avukat panosu "02 · Süre / Vade · Süre Uyarıları".
 *
 * Kaynak G085 gece tarayıcısının yazdığı bildirimlerdir; uç G081'in
 * `GET /api/notifications`ı ve YALNIZ isteği yapan kullanıcının satırlarını
 * döner — panel "kendi sürelerim" listesidir, ayrı bir yetki kuralı taşımaz.
 *
 * Uçta tür filtresi YOK (G081 yalnız `unread_only` + `limit` alıyor); süzme
 * burada yapılır ve bu yüzden tavana kadar (`DEADLINE_FETCH_LIMIT`) satır
 * çekilir. Bildirim hacmi bu tavanı aşarsa uca `type=` filtresi eklemek ayrı
 * (backend bandı) iştir — bkz. görev raporu.
 *
 * Veri gerçeği (G085 ölçümü, 2026-08-20): tebliğ tarihi yalnız YEREL aşamada
 * dolu ve 750 satır — panel ilk gün BİR AVUÇ uyarı gösterir. Bu bir kusur
 * değildir; boş liste "yaklaşan süre yok" der, ÖRNEK SATIR ÜRETİLMEZ.
 */

export const DEADLINE_PANEL_ERROR = "Süre uyarıları alınamadı.";

/** Uç tavanı `MAX_LIMIT = 200` (routes/notifications.py). Süzme istemcide. */
export const DEADLINE_FETCH_LIMIT = 200;

function toneClass(daysLeft: number): string {
  // Geri sayım DAİMA taze `due_date`ten; `severity` yazım anında donmuş olabilir.
  return daysLeft <= 3
    ? "text-[var(--danger,#b3261e)] border-[var(--danger,#b3261e)]/40 bg-[var(--danger,#b3261e)]/10"
    : "text-[#c47a1e] border-[#c47a1e]/40 bg-[#c47a1e]/10";
}

function DeadlineRowView({ row, onOpen }: { row: DeadlineRow; onOpen: (caseId: number) => void }) {
  const { item, parsed, daysLeft, headline } = row;
  const caseId = item.case_id;
  const Etiket = item.type === DURUSMA_TYPE ? CalendarClock : AlertTriangle;

  const govde = (
    <>
      <div className="flex items-center gap-2 min-w-0">
        <Etiket className="w-3.5 h-3.5 shrink-0 text-[var(--brand)]" strokeWidth={1.7} />
        <span className="font-display font-medium text-[13.5px] text-[var(--fg)] truncate">
          {headline}
        </span>
      </div>
      <dl className="mt-1.5 grid gap-0.5">
        {parsed.fields.map((f, i) => (
          <div key={`${f.label}-${i}`} className="flex gap-2 text-[11.5px] leading-relaxed min-w-0">
            <dt className="font-mono text-[10px] tracking-[0.1em] uppercase text-[var(--fg-subtle)] shrink-0 pt-[2px] w-[104px]">
              {f.label}
            </dt>
            <dd className="text-[var(--fg-muted)] min-w-0 break-words">{f.value}</dd>
          </div>
        ))}
        {parsed.extras.map((line, i) => (
          <div key={`extra-${i}`} className="text-[11.5px] text-[var(--fg-muted)] break-words">
            {line}
          </div>
        ))}
      </dl>
      {parsed.calendarWarning && (
        <p
          data-testid="calendar-warning"
          className="mt-2 flex items-start gap-1.5 border border-[#c47a1e]/40 bg-[#c47a1e]/10 px-2 py-1.5 text-[11px] leading-relaxed text-[#c47a1e]"
        >
          <Info className="w-3.5 h-3.5 shrink-0 mt-[1px]" strokeWidth={1.8} />
          <span>{parsed.calendarWarning}</span>
        </p>
      )}
    </>
  );

  return (
    <div
      data-testid="deadline-row"
      data-days-left={daysLeft}
      className="grid grid-cols-[92px_1fr] gap-3 items-start px-4 py-3.5 border-t border-[var(--border)] first:border-t-0"
    >
      <span
        className={`inline-flex items-center justify-center px-1.5 py-1 border font-mono text-[10px] tracking-[0.1em] uppercase font-semibold text-center tabular-nums ${toneClass(daysLeft)}`}
      >
        {countdownLabel(daysLeft)}
      </span>
      {caseId !== null ? (
        <button
          type="button"
          onClick={() => onOpen(caseId)}
          className="min-w-0 text-left transition-colors hover:text-[var(--brand)]"
        >
          {govde}
        </button>
      ) : (
        <div className="min-w-0">{govde}</div>
      )}
    </div>
  );
}

export function DeadlineWarningsPanel() {
  const navigate = useNavigate();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  // null = hata yok. Boş liste ile kesinti AYRI durumlardır (G002 dersi):
  // kesintide "yaklaşan süre yok" yazmak, süreyi kaçırtabilecek bir yalandır.
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);
  const openCase = useCallback((caseId: number) => navigate(`/cases/${caseId}`), [navigate]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const response = await apiClient.fetch(`/api/notifications?limit=${DEADLINE_FETCH_LIMIT}`);
        if (!response.ok) throw new Error(DEADLINE_PANEL_ERROR);
        const data: unknown = await response.json();
        if (cancelled) return;
        // Beklenmedik gövde de hatadır — boş listeye ÇEVRİLMEZ.
        if (!Array.isArray(data)) throw new Error(DEADLINE_PANEL_ERROR);
        setItems(data as NotificationItem[]);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        console.warn("Süre uyarıları alınamadı:", err);
        setError(err instanceof Error && err.message ? err.message : DEADLINE_PANEL_ERROR);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const rows = useMemo(() => (error ? [] : selectDeadlineRows(items)), [items, error]);

  return (
    <HairlineCard className="mt-3" padded={false}>
      {/* Kullanıcı şartı: şerh panelde BİR KEZ ve görünür yerde — satır başına tekrar etmez. */}
      <p
        data-testid="deadline-disclaimer"
        className="flex items-start gap-2 px-4 py-2.5 border-b border-[var(--border)] bg-[var(--bg-sunken)] text-[11px] leading-relaxed text-[var(--fg-muted)]"
      >
        <Info className="w-3.5 h-3.5 shrink-0 mt-[1px] text-[var(--fg-subtle)]" strokeWidth={1.8} />
        <span>{DEADLINE_DISCLAIMER}</span>
      </p>

      {loading ? (
        <div className="p-4 grid gap-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-[var(--bg-sunken)] animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <DataErrorBanner description={error} onRetry={retry} className="border-0" />
      ) : rows.length === 0 ? (
        <div className="grid place-items-center gap-3 py-8 text-center text-[var(--fg-subtle)]">
          <CalendarClock className="w-8 h-8 opacity-40" />
          <div>
            <p className="text-[13px] text-[var(--fg-muted)] font-medium">Yaklaşan süre yok</p>
            <p className="text-[11px] mt-1.5 max-w-[38ch] mx-auto leading-relaxed">
              Tebligat ve duruşma tarihlerinden hesaplanan kanuni süreler yaklaştıkça burada
              geri sayımıyla listelenir.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex flex-col">
          {rows.map((row) => (
            <DeadlineRowView key={row.item.id} row={row} onOpen={openCase} />
          ))}
        </div>
      )}
    </HairlineCard>
  );
}

export default DeadlineWarningsPanel;
