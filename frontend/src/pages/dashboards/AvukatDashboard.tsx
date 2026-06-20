import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Scale,
  FolderOpen,
  AlertTriangle,
  CalendarDays,
  ArrowRight,
  Gavel,
  Clock,
  User,
  FileText,
  Archive,
} from "lucide-react";
import { useCases } from "@/hooks/useCases";
import { apiClient } from "@/lib/api";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { SectionHeader, HairlineCard, Eyebrow } from "@/components/dashboard/primitives";
import { DashboardCalendar } from "@/components/dashboard/DashboardCalendar";
import { PlaceholderBadge } from "@/components/PlaceholderBadge";

interface DashboardCase {
  id: number;
  tracking_no: string;
  esas_no?: string;
  status: string;
  court?: string;
  subject?: string;
  opening_date?: string;
  responsible_lawyer_name?: string;
}

interface HearingItem {
  id?: number;
  case_id: number;
  esas_no?: string;
  tracking_no?: string;
  hearing_date: string;
  hearing_time?: string;
  court?: string;
  lawyer_name?: string;
  note?: string;
}

interface CaseStats {
  total: number;
  active: number;
  closed: number;
  appeal: number;
  danis_active?: number;
  statuses?: Record<string, number>;
}

function formatFull(d: Date): string {
  return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "short", weekday: "short" });
}

function parseDate(date: string): Date {
  return new Date(date + (date.includes("T") ? "" : "T00:00:00"));
}

function daysFromToday(date: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = parseDate(date);
  target.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

const STATUS_TONE: Record<string, string> = {
  DERDEST: "text-[#2f8a5d] border-[#2f8a5d]/30 bg-[#2f8a5d]/10",
  ISTINAF: "text-[#c47a1e] border-[#c47a1e]/30 bg-[#c47a1e]/10",
  TEMYIZ: "text-[#7a3f8a] border-[#7a3f8a]/30 bg-[#7a3f8a]/10",
  KARAR: "text-[var(--brand)] border-[var(--brand)]/30 bg-[var(--brand-soft)]",
  KAPALI: "text-[var(--fg-subtle)] border-[var(--border)] bg-[var(--bg-sunken)]",
};

function statusChip(status: string) {
  const tone = STATUS_TONE[status] || STATUS_TONE.KAPALI;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-mono tracking-[0.12em] uppercase border ${tone}`}>
      {status}
    </span>
  );
}

export default function AvukatDashboard() {
  useSetPageTitle("Anasayfa", ["Avukat Paneli"]);
  const navigate = useNavigate();
  const { getCases, getCaseStats } = useCases();
  const [stats, setStats] = useState<CaseStats>({ total: 0, active: 0, closed: 0, appeal: 0, statuses: {} });
  const [recentCases, setRecentCases] = useState<DashboardCase[]>([]);
  const [hearings, setHearings] = useState<HearingItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      const [statsData, casesData] = await Promise.all([
        getCaseStats(),
        getCases({ limit: 8, offset: 0 }),
      ]);
      if (cancelled) return;
      if (statsData) {
        setStats({
          total: statsData.total || 0,
          active: statsData.active || 0,
          closed: statsData.closed || 0,
          appeal: statsData.appeal || 0,
          danis_active: statsData.danis_active || 0,
          statuses: statsData.statuses || {},
        });
      }
      setRecentCases((casesData || []) as DashboardCase[]);
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [getCases, getCaseStats]);

  useEffect(() => {
    apiClient.fetch("/api/hearing-dates")
      .then(r => r.ok ? r.json() : Promise.resolve([]))
      .then((data: unknown) => setHearings(Array.isArray(data) ? (data as HearingItem[]) : []))
      .catch(() => setHearings([]));
  }, []);

  const today = new Date().toLocaleDateString("tr-TR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  // --- Dosya durumu metrikleri (gerçek statuses verisinden) ---
  const statusCards = useMemo(() => {
    const s = stats.statuses || {};
    return [
      { key: "DERDEST", label: "Derdest", value: s.DERDEST ?? stats.active, hint: "Aktif yerel dosya", Icon: Gavel },
      { key: "ISTINAF", label: "İstinaf", value: s.ISTINAF ?? 0, hint: "BAM aşaması", Icon: Archive },
      { key: "TEMYIZ", label: "Yargıtay", value: s.TEMYIZ ?? 0, hint: "Temyiz incelemesi", Icon: Scale },
      { key: "KAPALI", label: "Kapalı", value: stats.closed, hint: "Arşivlenen dosya", Icon: FolderOpen },
    ];
  }, [stats]);

  // --- Yaklaşan duruşmalar, güne göre gruplu ---
  const hearingGroups = useMemo(() => {
    const items = hearings
      .map(h => ({ ...h, daysLeft: daysFromToday(h.hearing_date) }))
      .filter(h => h.daysLeft >= 0 && h.daysLeft <= 30)
      .sort((a, b) => a.daysLeft - b.daysLeft)
      .slice(0, 10);
    const order: string[] = [];
    const map = new Map<string, typeof items>();
    for (const h of items) {
      const label = h.daysLeft === 0 ? "Bugün" : h.daysLeft === 1 ? "Yarın" : formatFull(parseDate(h.hearing_date));
      if (!map.has(label)) { map.set(label, []); order.push(label); }
      map.get(label)!.push(h);
    }
    return order.map(label => ({ label, items: map.get(label)! }));
  }, [hearings]);

  const hearingCount = hearingGroups.reduce((n, g) => n + g.items.length, 0);

  return (
    <div className="grid gap-7">
      {/* Üst selamlama */}
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <Eyebrow>{today}</Eyebrow>
          <h1 className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium">
            Avukat Paneli
          </h1>
        </div>
      </div>

      {/* Dosya Durumu */}
      <section>
        <SectionHeader eyebrow="01 · Dosya Durumu" title="Genel durum" italic="— statü dağılımı" />
        <div className="mt-3 grid grid-cols-2 lg:grid-cols-4 gap-4">
          {statusCards.map(({ key, label, value, hint, Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => navigate("/cases", { state: { statusFilter: key } })}
              className="group relative text-left bg-[var(--bg-elevated)] border border-[var(--border)] p-5 grid gap-2 transition-colors hover:border-[var(--border-strong)] overflow-hidden"
            >
              <span className="absolute top-0 right-0 w-0.5 h-6 bg-[var(--brand)] opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="flex items-center gap-2">
                <span className="w-[26px] h-[26px] grid place-items-center border border-[var(--border-strong)] bg-[var(--bg)] text-[var(--brand)] rounded-[3px]">
                  <Icon className="w-3.5 h-3.5" strokeWidth={1.6} />
                </span>
                <Eyebrow>{label}</Eyebrow>
              </div>
              <div className="font-display font-medium text-[38px] leading-none tracking-[-0.025em] text-[var(--fg)]">
                {loading ? "—" : value}
              </div>
              <div className="text-[11px] text-[var(--fg-subtle)]">{hint}</div>
            </button>
          ))}
        </div>
      </section>

      {/* Süre / Vade Uyarıları — backend otomatik tespit hazır olunca dolacak */}
      <section>
        <SectionHeader
          eyebrow="02 · Süre / Vade"
          title="Süre Uyarıları"
          italic="— belgelerden otomatik tespit"
          meta={<PlaceholderBadge />}
        />
        <HairlineCard className="mt-3">
          <div className="grid place-items-center gap-3 py-8 text-center text-[var(--fg-subtle)]">
            <AlertTriangle className="w-8 h-8 opacity-40" />
            <div>
              <p className="text-[13px] text-[var(--fg-muted)] font-medium">Yakında aktif olacak</p>
              <p className="text-[11px] mt-1.5 max-w-[36ch] mx-auto leading-relaxed">
                Tebligat ve karar metinlerinden tespit edilen cevap, istinaf ve itiraz süreleri burada
                geri sayımıyla listelenecek.
              </p>
            </div>
          </div>
        </HairlineCard>
      </section>

      {/* Duruşmalar | Yeni İşlenen Belgeler */}
      <section className="grid grid-cols-1 lg:grid-cols-5 gap-5 items-start">
        {/* Duruşmalar */}
        <div className="lg:col-span-3">
          <SectionHeader
            eyebrow="03 · Ajanda"
            title="Duruşmalar"
            italic="— sonraki 30 gün"
            meta={
              <button
                type="button"
                onClick={() => navigate("/cases")}
                className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] inline-flex items-center gap-1"
              >
                {hearingCount} adet <ArrowRight className="w-3 h-3" />
              </button>
            }
          />
          <HairlineCard className="mt-3" padded={false}>
            {hearingGroups.length === 0 ? (
              <div className="p-7 grid place-items-center gap-2 text-center text-[var(--fg-subtle)]">
                <CalendarDays className="w-7 h-7 opacity-40" />
                <p className="text-[13px]">Önümüzdeki 30 gün için duruşma yok.</p>
              </div>
            ) : (
              <div className="flex flex-col px-4 pb-2">
                {hearingGroups.map(group => (
                  <div key={group.label}>
                    <div className="flex items-center justify-between pt-3 pb-2 border-t border-[var(--border)] first:border-t-0">
                      <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
                        {group.label}
                      </span>
                      <span className="font-mono text-[9.5px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                        {group.items.length} duruşma
                      </span>
                    </div>
                    {group.items.map((h, idx) => (
                      <button
                        key={h.id ?? `${h.case_id}-${idx}`}
                        type="button"
                        onClick={() => navigate(`/cases/${h.case_id}`)}
                        className="w-full grid grid-cols-[72px_1fr_auto] gap-4 items-center py-3 text-left border-t border-[var(--border)] transition-colors hover:bg-[var(--bg)]"
                      >
                        <div>
                          <div className="font-mono text-[18px] font-medium tracking-[-0.02em] text-[var(--fg)]">
                            {h.hearing_time || "—"}
                          </div>
                          <div
                            className={`mt-1 inline-flex items-center gap-1.5 font-mono text-[9px] tracking-[0.14em] uppercase ${
                              h.daysLeft === 0 ? "text-[var(--brand)]" : "text-[var(--fg-subtle)]"
                            }`}
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-current" />
                            {h.daysLeft === 0 ? "Bugün" : h.daysLeft === 1 ? "Yarın" : `${h.daysLeft} gün`}
                          </div>
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-baseline gap-2 min-w-0">
                            {(h.esas_no || h.tracking_no) && (
                              <span className="font-mono text-[11px] tracking-[0.04em] text-[var(--brand)] shrink-0">
                                № {h.esas_no || h.tracking_no}
                              </span>
                            )}
                            <span className="font-display font-medium text-[14px] text-[var(--fg)] truncate">
                              {h.court || "Duruşma"}
                            </span>
                          </div>
                          {h.lawyer_name && (
                            <div className="text-[12px] text-[var(--fg-muted)] mt-1 truncate flex items-center gap-1.5">
                              <User className="w-3 h-3 shrink-0" />
                              {h.lawyer_name}
                            </div>
                          )}
                        </div>
                        <span className="font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-muted)] px-2 py-1 border border-[var(--border-strong)] bg-[var(--bg)] shrink-0">
                          {h.note || "Duruşma"}
                        </span>
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </HairlineCard>
        </div>

        {/* Yeni İşlenen Belgeler — placeholder */}
        <div className="lg:col-span-2">
          <SectionHeader
            eyebrow="04 · Belgeler"
            title="Yeni İşlenen"
            italic="— son 24 saat"
            meta={<PlaceholderBadge />}
          />
          <HairlineCard className="mt-3">
            <div className="grid place-items-center gap-3 py-8 text-center text-[var(--fg-subtle)]">
              <FileText className="w-8 h-8 opacity-40" />
              <div>
                <p className="text-[13px] text-[var(--fg-muted)] font-medium">Yakında aktif olacak</p>
                <p className="text-[11px] mt-1.5 max-w-[28ch] mx-auto leading-relaxed">
                  AI ile analiz edilip davaya bağlanan yeni belgeler burada akış halinde görünecek.
                </p>
              </div>
              <button
                type="button"
                onClick={() => navigate("/upload")}
                className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] inline-flex items-center gap-1 mt-2 pb-1 border-b border-[var(--border)] hover:border-[var(--brand)]"
              >
                Belge Yükle <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          </HairlineCard>
        </div>
      </section>

      {/* Son Açılan Dosyalar | Takvim */}
      <section className="grid grid-cols-1 lg:grid-cols-5 gap-5 items-start">
        {/* Son Açılan Dosyalar */}
        <div className="lg:col-span-3">
          <SectionHeader
            eyebrow="05 · Dosyalar"
            title="Son Düzenlenen Davalar"
            italic="— en son işlem"
            meta={
              <button
                type="button"
                onClick={() => navigate("/cases")}
                className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] inline-flex items-center gap-1"
              >
                Tümü <ArrowRight className="w-3 h-3" />
              </button>
            }
          />
          <HairlineCard className="mt-3" padded={false}>
            {loading ? (
              <div className="p-4 grid gap-2">
                {[1, 2, 3, 4].map(i => (
                  <div key={i} className="h-16 bg-[var(--bg-sunken)] animate-pulse" />
                ))}
              </div>
            ) : recentCases.length === 0 ? (
              <div className="p-7 grid place-items-center gap-2 text-center text-[var(--fg-subtle)]">
                <FolderOpen className="w-7 h-7 opacity-40" />
                <p className="text-[13px]">Dava bulunamadı.</p>
              </div>
            ) : (
              <div className="flex flex-col">
                {recentCases.map((c, idx) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => navigate(`/cases/${c.id}`)}
                    className={`grid grid-cols-[auto_1fr_auto] gap-4 items-start px-4 py-3.5 text-left transition-colors hover:bg-[var(--bg)] ${idx > 0 ? "border-t border-[var(--border)]" : ""}`}
                  >
                    <Gavel className="w-4 h-4 text-[var(--brand)] mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-mono text-[12px] tracking-[0.04em] text-[var(--fg)] truncate font-medium">
                          {c.esas_no || c.tracking_no}
                        </span>
                        {statusChip(c.status)}
                      </div>
                      {c.subject && (
                        <div className="text-[12px] text-[var(--fg-muted)] mt-1 truncate">
                          {c.subject}
                        </div>
                      )}
                      <div className="flex items-center gap-3 mt-1.5 text-[11px] text-[var(--fg-subtle)]">
                        {c.responsible_lawyer_name && (
                          <span className="inline-flex items-center gap-1">
                            <User className="w-3 h-3" />
                            {c.responsible_lawyer_name}
                          </span>
                        )}
                        {c.court && (
                          <span className="inline-flex items-center gap-1 truncate">
                            <Scale className="w-3 h-3 shrink-0" />
                            <span className="truncate">{c.court}</span>
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      {c.opening_date && (
                        <div className="font-mono text-[10px] tracking-[0.04em] text-[var(--fg-subtle)] inline-flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {new Date(c.opening_date).toLocaleDateString("tr-TR")}
                        </div>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </HairlineCard>
        </div>

        {/* Takvim — duruşma + elle işaretler, tarih işaretleme butonlu */}
        <div className="lg:col-span-2">
          <DashboardCalendar eyebrow="06 · Takvim" />
        </div>
      </section>
    </div>
  );
}
