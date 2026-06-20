import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Upload,
  Gavel,
  UserPlus,
  TrendingUp,
  Scale,
  FolderOpen,
  Clock,
  Activity,
  ArrowRight,
  Users,
} from "lucide-react";
import { useCases } from "@/hooks/useCases";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { MetricCard, SectionHeader, HairlineCard, Eyebrow } from "@/components/dashboard/primitives";
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

interface CaseStats {
  total: number;
  active: number;
  closed: number;
  appeal: number;
  danis_active?: number;
}

type QuickAction = {
  id: string;
  label: string;
  hint: string;
  icon: typeof Upload;
  path: string;
};

const QUICK_ACTIONS: QuickAction[] = [
  {
    id: "upload",
    label: "Belge Yükle",
    hint: "PDF / DOCX · AI ile analiz",
    icon: Upload,
    path: "/upload",
  },
  {
    id: "new-case",
    label: "Yeni Dava Aç",
    hint: "Müvekkil + esas no",
    icon: Gavel,
    path: "/new-case/form",
  },
  {
    id: "new-client",
    label: "Müvekkil Ekle",
    hint: "TC, vekalet, iletişim",
    icon: UserPlus,
    path: "/new-client",
  },
];

export default function IdariDashboard() {
  useSetPageTitle("Anasayfa", ["İdari Panel"]);
  const navigate = useNavigate();
  const { getCases, getCaseStats } = useCases();
  const [stats, setStats] = useState<CaseStats>({ total: 0, active: 0, closed: 0, appeal: 0 });
  const [recentCases, setRecentCases] = useState<DashboardCase[]>([]);
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
        });
      }
      setRecentCases((casesData || []) as DashboardCase[]);
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [getCases, getCaseStats]);

  const today = new Date().toLocaleDateString("tr-TR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div className="grid gap-7">
      {/* Üst selamlama */}
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <Eyebrow>{today}</Eyebrow>
          <h1 className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium">
            İdari Panel
          </h1>
        </div>
      </div>

      {/* Hızlı Eylemler */}
      <section>
        <SectionHeader
          eyebrow="01 · Hızlı Eylem"
          title="Sık kullanılanlar"
          italic="— tek tıkla işleme"
        />
        <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-4">
          {QUICK_ACTIONS.map(a => {
            const { icon: Icon } = a;
            return (
              <button
                key={a.id}
                type="button"
                onClick={() => navigate(a.path)}
                className="group text-left p-5 border border-[var(--border)] bg-[var(--bg-elevated)] transition-colors hover:border-[var(--brand)] hover:bg-[var(--brand-soft)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="w-11 h-11 grid place-items-center bg-[var(--brand)] text-[var(--brand-fg)] transition-transform group-hover:scale-105">
                    <Icon className="w-5 h-5" strokeWidth={1.6} />
                  </div>
                  <ArrowRight className="w-4 h-4 text-[var(--fg-subtle)] mt-1 transition-colors group-hover:text-[var(--brand)]" />
                </div>
                <div className="mt-4">
                  <div className="font-display font-medium text-[16px] tracking-[-0.005em] text-[var(--fg)]">
                    {a.label}
                  </div>
                  <div className="font-mono text-[10px] tracking-[0.08em] uppercase text-[var(--fg-subtle)] mt-1.5">
                    {a.hint}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Metrikler */}
      <section>
        <SectionHeader eyebrow="02 · Genel" title="Bürodaki durum" italic="— canlı sayım" />
        <div className="mt-3 grid grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            label="Danış"
            value={loading ? "—" : stats.danis_active ?? "—"}
            icon={<Users className="w-4 h-4" />}
            tone="neutral"
            hint="Danışmanlık"
            onClick={() => navigate("/cases")}
          />
          <MetricCard
            label="Aktif (Derdest)"
            value={loading ? "—" : stats.active}
            icon={<TrendingUp className="w-4 h-4" />}
            tone="success"
            hint="Süren davalar"
            onClick={() => navigate("/cases")}
          />
          <MetricCard
            label="Kapalı"
            value={loading ? "—" : stats.closed}
            icon={<FolderOpen className="w-4 h-4" />}
            tone="neutral"
            hint="Karar / İnfaz"
            onClick={() => navigate("/cases")}
          />
          <MetricCard
            label="Toplam Dava"
            value={loading ? "—" : stats.total}
            icon={<Scale className="w-4 h-4" />}
            tone="brand"
            hint="Tüm dosyalar"
            onClick={() => navigate("/cases")}
          />
        </div>
      </section>

      {/* İkili Grid: Son Davalar | (Takvim + Süreli İşler) */}
      <section className="grid grid-cols-1 lg:grid-cols-5 gap-5 items-start">
        {/* Son Davalar */}
        <div className="lg:col-span-3">
          <SectionHeader
            eyebrow="03 · Dosyalar"
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
                        <span className="font-mono text-[9px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] px-1.5 py-0.5 border border-[var(--border)]">
                          {c.status}
                        </span>
                      </div>
                      {c.subject && (
                        <div className="text-[12px] text-[var(--fg-muted)] mt-1 truncate">
                          {c.subject}
                        </div>
                      )}
                      <div className="flex items-center gap-3 mt-1.5 text-[11px] text-[var(--fg-subtle)]">
                        {c.responsible_lawyer_name && (
                          <span className="inline-flex items-center gap-1">
                            <Users className="w-3 h-3" />
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

        {/* Takvim (üstte) + Süreli İşler (altta) — aynı genişlikte sağ sütun */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          {/* Takvim */}
          <div>
            <DashboardCalendar eyebrow="04 · Takvim" />
          </div>

          {/* Süreli İşler (placeholder, backend hazır olunca dolacak) */}
          <div>
          <SectionHeader
            eyebrow="05 · İnceleme"
            title="Süreli İşler"
            italic="— avukat bilgilendirmesi"
            meta={<PlaceholderBadge />}
          />
          <HairlineCard className="mt-3 relative">
            <div className="grid place-items-center gap-3 py-8 text-center text-[var(--fg-subtle)]">
              <Activity className="w-8 h-8 opacity-40" />
              <div>
                <p className="text-[13px] text-[var(--fg-muted)] font-medium">Yakında aktif olacak</p>
                <p className="text-[11px] mt-1.5 max-w-[24ch] mx-auto leading-relaxed">
                  Belgelerden tespit edilen süreler ve sorumlu avukat bildirimleri burada listelenecek.
                </p>
              </div>
              <button
                type="button"
                onClick={() => navigate("/activity-history")}
                className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] inline-flex items-center gap-1 mt-2 pb-1 border-b border-[var(--border)] hover:border-[var(--brand)]"
              >
                Aktivite Geçmişi <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          </HairlineCard>
          </div>
        </div>
      </section>
    </div>
  );
}
