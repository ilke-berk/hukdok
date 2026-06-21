import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Upload,
  Gavel,
  UserPlus,
  Scale,
  FolderOpen,
  Clock,
  Activity,
  ArrowRight,
  ChevronRight,
  Users,
} from "lucide-react";
import { useCases } from "@/hooks/useCases";
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

type QuickAction = {
  id: string;
  label: string;
  desc: string;
  cta: string;
  kbd: string;
  icon: typeof Upload;
  path: string;
  primary?: boolean;
};

// Birincil eylem (Belge Yükle) bilinçli olarak daha geniş + dolu bordo kart.
// Diğer ikisi sade krem zemin; bordo yalnızca ikon ve CTA'da vurgu.
const QUICK_ACTIONS: QuickAction[] = [
  {
    id: "upload",
    label: "Belge Yükle",
    desc: "PDF veya DOCX bırakın; yapay zeka belgeyi okur, isimlendirir ve davaya bağlar.",
    cta: "Sürükle bırak veya tıkla",
    kbd: "U",
    icon: Upload,
    path: "/upload",
    primary: true,
  },
  {
    id: "new-case",
    label: "Yeni Dava Aç",
    desc: "Müvekkil ve esas no ile yeni dava dosyası oluşturun.",
    cta: "Dosya oluştur",
    kbd: "N",
    icon: Gavel,
    path: "/new-case/form",
  },
  {
    id: "new-client",
    label: "Müvekkil Ekle",
    desc: "TC, vekalet ve iletişim bilgileriyle yeni müvekkil kaydı açın.",
    cta: "Müvekkil kaydı",
    kbd: "M",
    icon: UserPlus,
    path: "/new-client",
  },
];

// Klavye kısayolu: "G" sonra ilgili harf (Gmail/Linear tarzı sıralı kısayol).
// Tarayıcının kendi Ctrl kısayollarıyla çakışmaz; rozet "G U" biçiminde gösterilir.
const SEQUENCE_TIMEOUT_MS = 1000;
const shortcutLabel = (key: string) => `G ${key}`;

export default function IdariDashboard() {
  useSetPageTitle("Anasayfa", ["İdari Panel"]);
  const navigate = useNavigate();
  const { getCases } = useCases();
  const [recentCases, setRecentCases] = useState<DashboardCase[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      const casesData = await getCases({ limit: 8, offset: 0 });
      if (cancelled) return;
      setRecentCases((casesData || []) as DashboardCase[]);
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [getCases]);

  // "G" sonra U/N/M sıralı kısayolu → ilgili sayfaya git. Bir input/textarea içinde
  // yazarken veya bir modifier (Ctrl/Alt/Cmd) basılıyken devre dışı kalır.
  useEffect(() => {
    let gPressedAt = 0;
    const isTyping = (target: EventTarget | null) => {
      const el = target as HTMLElement | null;
      if (!el) return false;
      return (
        el.tagName === "INPUT" ||
        el.tagName === "TEXTAREA" ||
        el.tagName === "SELECT" ||
        el.isContentEditable
      );
    };
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
      const key = e.key.toLowerCase();
      if (key === "g") {
        gPressedAt = Date.now();
        return;
      }
      if (Date.now() - gPressedAt < SEQUENCE_TIMEOUT_MS) {
        const action = QUICK_ACTIONS.find(a => a.kbd.toLowerCase() === key);
        if (action) {
          e.preventDefault();
          gPressedAt = 0;
          navigate(action.path);
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [navigate]);

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
        {/* Eşit-olmayan grid: birincil kart (Belge Yükle) %40 daha geniş. */}
        <div className="mt-3 grid grid-cols-1 gap-4 md:[grid-template-columns:1.4fr_1fr_1fr]">
          {QUICK_ACTIONS.map(a => {
            const { icon: Icon } = a;
            return (
              <button
                key={a.id}
                type="button"
                onClick={() => navigate(a.path)}
                className={[
                  "group relative flex min-h-[132px] flex-col justify-between gap-[18px] px-6 py-[22px] text-left",
                  "border transition-[border-color,transform] duration-150 active:translate-y-px",
                  a.primary
                    ? "border-[var(--brand)] text-[#fdf2f4] [background:linear-gradient(140deg,var(--brand)_0%,var(--burgundy-800,var(--brand-hover))_100%)]"
                    : "border-[var(--border)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)]",
                ].join(" ")}
              >
                {/* Üst: ikon kutusu + klavye kısayolu rozeti */}
                <div className="flex items-start justify-between">
                  <span
                    className={[
                      "grid h-10 w-10 place-items-center rounded-[4px] border",
                      a.primary
                        ? "border-white/30 bg-white/[0.08] text-[#fdf2f4]"
                        : "border-[var(--border-strong)] bg-[var(--bg)] text-[var(--brand)]",
                    ].join(" ")}
                  >
                    <Icon className="h-[18px] w-[18px]" strokeWidth={1.6} />
                  </span>
                  <kbd
                    className={[
                      "font-mono text-[10px] leading-none rounded-[3px] border px-1.5 py-[3px]",
                      a.primary ? "border-white/25 text-[#fdf2f4]/80" : "border-[var(--border)] text-[var(--fg-subtle)]",
                    ].join(" ")}
                  >
                    {shortcutLabel(a.kbd)}
                  </kbd>
                </div>

                {/* Orta: serif başlık + açıklama */}
                <div>
                  <div className="font-display font-medium text-[22px] tracking-[-0.015em] leading-[1.15]">
                    {a.label}
                  </div>
                  <p
                    className={[
                      "mt-2 text-[12.5px] leading-[1.5]",
                      a.primary ? "text-[#fdf2f4]/75" : "text-[var(--fg-muted)]",
                    ].join(" ")}
                  >
                    {a.desc}
                  </p>
                </div>

                {/* Alt: monospace CTA — link-eylem dili */}
                <span
                  className={[
                    "inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.16em]",
                    a.primary ? "text-[#fdf2f4]" : "text-[var(--brand)]",
                  ].join(" ")}
                >
                  {a.cta}
                  <ChevronRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {/* İkili Grid: Son Davalar | (Takvim + Süreli İşler) */}
      <section className="grid grid-cols-1 lg:grid-cols-5 gap-5 items-start">
        {/* Son Davalar */}
        <div className="lg:col-span-3">
          <SectionHeader
            eyebrow="02 · Dosyalar"
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
            <DashboardCalendar eyebrow="03 · Takvim" />
          </div>

          {/* Süreli İşler (placeholder, backend hazır olunca dolacak) */}
          <div>
          <SectionHeader
            eyebrow="04 · İnceleme"
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
