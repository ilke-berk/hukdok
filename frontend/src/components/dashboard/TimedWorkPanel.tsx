import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { AlertTriangle, CalendarClock, Info, MailCheck, MailQuestion, UserX } from "lucide-react";
import { apiClient } from "@/lib/api";
import { HairlineCard } from "@/components/dashboard/primitives";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { DEADLINE_DISCLAIMER, DURUSMA_TYPE } from "@/components/dashboard/deadlineBody";
import {
  OVERVIEW_ENDPOINT,
  OVERVIEW_ERROR,
  UNRESOLVED_ENDPOINT,
  UNRESOLVED_ERROR,
  capNote,
  overviewSummary,
  parseOverviewEnvelope,
  parseUnresolvedEnvelope,
  timedWorkRows,
  unresolvedSummary,
  type OverviewEnvelope,
  type TimedWorkRow,
  type UnresolvedEnvelope,
} from "@/components/dashboard/timedWorkOverview";

/**
 * G086 (idari yarı) — İdari pano "04 · İnceleme · Süreli İşler".
 *
 * Sorusu avukat panelininkinden FARKLIDIR: "benim sürelerim" değil, **hangi süre
 * kime bildirildi ve okundu mu**. Kaynak G087'nin iki salt okuma ucudur; ikisi de
 * `get_current_user` kapılıdır (rol ayrımı yok — kullanıcı kararı, G087 dosyası).
 *
 * İki uç BAĞIMSIZ ele alınır: biri kesilince diğeri gösterilmeye devam eder ve
 * kesilen taraf kendi hata satırını yazar. Tek bir "hata" durumuna indirgemek,
 * ayakta olan veriyi de gizlerdi.
 *
 * Panel SALT OKUMADIR: hiçbir satırı okundu işaretlemez (uçlar da işaretlemez) —
 * idari panelde bir uyarıya bakmak avukatın okunmamış sayacını düşürmez.
 */

export function TimedWorkPanel() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<OverviewEnvelope | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [unresolved, setUnresolved] = useState<UnresolvedEnvelope | null>(null);
  const [unresolvedError, setUnresolvedError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);
  const openCase = useCallback((caseId: number) => navigate(`/cases/${caseId}`), [navigate]);

  useEffect(() => {
    let cancelled = false;

    async function oku<T>(endpoint: string, ayikla: (data: unknown) => T | null, hata: string) {
      try {
        const response = await apiClient.fetch(endpoint);
        if (!response.ok) throw new Error(hata);
        const parsed = ayikla(await response.json());
        // Beklenmedik gövde de hatadır — boş listeye ÇEVRİLMEZ (G002 dersi).
        if (!parsed) throw new Error(hata);
        return { data: parsed, error: null as string | null };
      } catch (err) {
        console.warn(hata, err);
        return { data: null, error: err instanceof Error && err.message ? err.message : hata };
      }
    }

    (async () => {
      setLoading(true);
      const [ozet, hedefsiz] = await Promise.all([
        oku(OVERVIEW_ENDPOINT, parseOverviewEnvelope, OVERVIEW_ERROR),
        oku(UNRESOLVED_ENDPOINT, parseUnresolvedEnvelope, UNRESOLVED_ERROR),
      ]);
      if (cancelled) return;
      setOverview(ozet.data);
      setOverviewError(ozet.error);
      setUnresolved(hedefsiz.data);
      setUnresolvedError(hedefsiz.error);
      setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const rows = useMemo(() => timedWorkRows(overview?.items), [overview]);
  const note = overview ? capNote(overview.total, rows.length) : null;

  return (
    <HairlineCard className="mt-3" padded={false}>
      {/* Şerh panelde BİR KEZ: liste dolu, boş ya da hatalı olsun daima görünür. */}
      <p
        data-testid="timed-work-disclaimer"
        className="flex items-start gap-2 px-4 py-2.5 border-b border-[var(--border)] bg-[var(--bg-sunken)] text-[11px] leading-relaxed text-[var(--fg-muted)]"
      >
        <Info className="w-3.5 h-3.5 shrink-0 mt-[1px] text-[var(--fg-subtle)]" strokeWidth={1.8} />
        <span>{DEADLINE_DISCLAIMER}</span>
      </p>

      <UnresolvedStrip env={unresolved} error={unresolvedError} loading={loading} />

      {loading ? (
        <div className="p-4 grid gap-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-14 bg-[var(--bg-sunken)] animate-pulse" />
          ))}
        </div>
      ) : overviewError ? (
        <DataErrorBanner description={overviewError} onRetry={retry} className="border-0" />
      ) : !overview || rows.length === 0 ? (
        <div className="grid place-items-center gap-3 py-8 text-center text-[var(--fg-subtle)]">
          <CalendarClock className="w-8 h-8 opacity-40" />
          <div>
            <p className="text-[13px] text-[var(--fg-muted)] font-medium">
              Bildirilmiş süre uyarısı yok
            </p>
            <p className="text-[11px] mt-1.5 max-w-[40ch] mx-auto leading-relaxed">
              Son {overview?.days ?? ""} günde sorumlu avukatlara gönderilen süre ve duruşma
              uyarıları burada alıcısı ve okunma durumuyla listelenir.
            </p>
          </div>
        </div>
      ) : (
        <>
          <div
            data-testid="timed-work-summary"
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2 border-b border-[var(--border)] font-mono text-[10px] tracking-[0.1em] uppercase text-[var(--fg-subtle)]"
          >
            <span>{overviewSummary(overview.total, overview.unread)}</span>
            <span className="normal-case tracking-normal font-sans text-[11px]">
              son {overview.days} gün
            </span>
            {note && (
              <span className="normal-case tracking-normal font-sans text-[11px]">{note}</span>
            )}
          </div>
          <div className="flex flex-col">
            {rows.map((row) => (
              <TimedWorkRowView key={row.item.id} row={row} onOpen={openCase} />
            ))}
          </div>
        </>
      )}
    </HairlineCard>
  );
}

/** G080 hedefsiz sayacı: sorumlusu bir alıcıya çözülemeyen davalar. */
function UnresolvedStrip({
  env,
  error,
  loading,
}: {
  env: UnresolvedEnvelope | null;
  error: string | null;
  loading: boolean;
}) {
  if (loading) return null;

  if (error) {
    return (
      <p
        data-testid="unresolved-error"
        className="flex items-start gap-2 px-4 py-2.5 border-b border-[var(--border)] text-[11px] leading-relaxed text-[#c47a1e]"
      >
        <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-[1px]" strokeWidth={1.8} />
        <span>{error}</span>
      </p>
    );
  }

  if (!env) return null;

  return (
    <div
      data-testid="unresolved-targets"
      className="px-4 py-2.5 border-b border-[var(--border)]"
    >
      <div className="flex items-center gap-2 text-[11.5px] text-[var(--fg-muted)]">
        <UserX className="w-3.5 h-3.5 shrink-0 text-[var(--fg-subtle)]" strokeWidth={1.8} />
        <span className="font-medium text-[var(--fg)]">Bildirim hedefi bulunamayan davalar</span>
        {env.total_cases > 0 && (
          <span className="font-mono text-[10px] tracking-[0.1em] uppercase tabular-nums text-[var(--fg-subtle)]">
            {unresolvedSummary(env)}
          </span>
        )}
      </div>
      {env.total_cases === 0 ? (
        <p className="mt-1 text-[11px] text-[var(--fg-subtle)]">
          Sorumlusu bildirime çözülemeyen dava yok.
        </p>
      ) : (
        <ul className="mt-1.5 grid gap-0.5">
          {env.items.map((t) => (
            <li
              key={t.name}
              data-testid="unresolved-row"
              className="flex items-baseline justify-between gap-3 text-[11.5px] text-[var(--fg-muted)]"
            >
              <span className="min-w-0 break-words">{t.name}</span>
              <span className="font-mono text-[11px] tabular-nums shrink-0">{t.case_count}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function toneClass(row: TimedWorkRow): string {
  if (row.daysLeft === null) return "text-[var(--fg-subtle)] border-[var(--border)]";
  // Renk tek başına anlam taşımaz: etiketin kendisi "3 gün geçti" yazar.
  return row.daysLeft <= 3
    ? "text-[var(--danger,#b3261e)] border-[var(--danger,#b3261e)]/40 bg-[var(--danger,#b3261e)]/10"
    : "text-[#c47a1e] border-[#c47a1e]/40 bg-[#c47a1e]/10";
}

function TimedWorkRowView({
  row,
  onOpen,
}: {
  row: TimedWorkRow;
  onOpen: (caseId: number) => void;
}) {
  const { item } = row;
  const caseId = item.case_id;
  const Etiket = item.type === DURUSMA_TYPE ? CalendarClock : AlertTriangle;
  const Okunma = item.is_read ? MailCheck : MailQuestion;

  const govde = (
    <>
      <div className="flex items-center gap-2 min-w-0">
        <Etiket className="w-3.5 h-3.5 shrink-0 text-[var(--brand)]" strokeWidth={1.7} />
        <span className="font-display font-medium text-[13.5px] text-[var(--fg)] truncate">
          {row.title}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-[var(--fg-muted)] min-w-0">
        <span data-testid="timed-work-recipient" className="min-w-0 break-all">
          {row.recipient}
        </span>
        <span className="font-mono text-[10px] tracking-[0.1em] uppercase text-[var(--fg-subtle)] tabular-nums">
          Son gün {row.dueLabel}
        </span>
        <span
          data-testid="timed-work-read"
          className={`inline-flex items-center gap-1 ${
            item.is_read ? "text-[var(--fg-subtle)]" : "text-[var(--fg)] font-medium"
          }`}
        >
          <Okunma className="w-3.5 h-3.5 shrink-0" strokeWidth={1.8} />
          {row.readLabel}
        </span>
      </div>
    </>
  );

  return (
    <div
      data-testid="timed-work-row"
      data-days-left={row.daysLeft === null ? "" : row.daysLeft}
      data-read={item.is_read ? "1" : "0"}
      className="grid grid-cols-[92px_1fr] gap-3 items-start px-4 py-3 border-t border-[var(--border)] first:border-t-0"
    >
      <span
        className={`inline-flex items-center justify-center px-1.5 py-1 border font-mono text-[10px] tracking-[0.1em] uppercase font-semibold text-center tabular-nums ${toneClass(row)}`}
      >
        {row.countdown}
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

export default TimedWorkPanel;
