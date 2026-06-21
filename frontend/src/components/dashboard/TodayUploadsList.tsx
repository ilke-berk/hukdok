import { FileText, ArrowRight } from "lucide-react";
import { HairlineCard } from "@/components/dashboard/primitives";
import type { TodayUploadItem, TodayUploadStatus } from "@/lib/todayUploads";

interface TodayUploadsListProps {
  items: TodayUploadItem[];
  onShowAll?: () => void;
}

// Durum → renk/etiket. Renkler projedeki diğer durum rozetleriyle aynı paleti kullanır.
const STATUS_META: Record<TodayUploadStatus, { label: string; color: string }> = {
  BAĞLANDI: { label: "Bağlandı", color: "#2f8a5d" },
  ARŞİVLENDİ: { label: "Arşivlendi", color: "var(--fg-muted)" },
  İŞLENİYOR: { label: "İşleniyor", color: "#c47a1e" },
  SIRADA: { label: "Sırada", color: "var(--fg-subtle)" },
};

function formatSize(bytes: number): string {
  if (!bytes || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(1)} MB`;
}

// "az önce" / "12 dk" / "3 sa" — aynı gün içi olduğundan tarih nadiren gerekir.
function formatAgo(ts: number): string {
  const diffMs = Date.now() - ts;
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return "az önce";
  if (min < 60) return `${min} dk`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} sa`;
  return new Date(ts).toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
}

export function TodayUploadsList({ items, onShowAll }: TodayUploadsListProps) {
  if (items.length === 0) {
    return (
      <HairlineCard className="mt-3">
        <div className="grid place-items-center gap-3 py-8 text-center text-[var(--fg-subtle)]">
          <FileText className="w-8 h-8 opacity-40" />
          <div>
            <p className="text-[13px] text-[var(--fg-muted)] font-medium">Bugün henüz belge yüklemediniz</p>
            <p className="text-[11px] mt-1.5 max-w-[42ch] mx-auto leading-relaxed">
              Yüklediğiniz belgeler, bağlandıkları dava ve işlenme durumlarıyla burada listelenecek.
            </p>
          </div>
          {onShowAll && (
            <button
              type="button"
              onClick={onShowAll}
              className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] inline-flex items-center gap-1 mt-2 pb-1 border-b border-[var(--border)] hover:border-[var(--brand)]"
            >
              Aktivite Geçmişi <ArrowRight className="w-3 h-3" />
            </button>
          )}
        </div>
      </HairlineCard>
    );
  }

  return (
    <HairlineCard className="mt-3" padded={false}>
      <div className="flex flex-col">
        {items.map((item, idx) => {
          const status = STATUS_META[item.status] ?? STATUS_META.ARŞİVLENDİ;
          return (
            <div
              key={item.id}
              className={`grid grid-cols-[auto_1fr_auto] md:grid-cols-[auto_minmax(0,1.4fr)_minmax(0,1fr)_auto_auto] gap-x-4 gap-y-1 items-center px-4 py-3 ${idx > 0 ? "border-t border-[var(--border)]" : ""}`}
            >
              {/* Dosya türü rozeti */}
              <span className="grid h-9 w-9 place-items-center rounded-[3px] border border-[var(--border-strong)] bg-[var(--bg)] font-mono text-[8px] tracking-[0.08em] font-semibold text-[var(--fg-subtle)]">
                {item.ext}
              </span>

              {/* Dosya adı + boyut · yükleyen */}
              <div className="min-w-0">
                <div className="font-mono text-[12px] tracking-[0.01em] text-[var(--fg)] truncate font-medium">
                  {item.filename}
                </div>
                <div className="font-mono text-[10px] tracking-[0.06em] uppercase text-[var(--fg-subtle)] mt-0.5 truncate">
                  {formatSize(item.sizeBytes)}
                  {item.uploader ? ` · ${item.uploader}` : ""}
                </div>
              </div>

              {/* Müvekkil + esas no */}
              <div className="min-w-0 col-start-2 md:col-start-3 row-start-2 md:row-start-auto">
                <div className="text-[12.5px] text-[var(--fg)] truncate">
                  {item.clientName || "—"}
                </div>
                {item.caseNo && (
                  <div className="font-mono text-[10px] tracking-[0.04em] text-[var(--fg-subtle)] mt-0.5 truncate">
                    № {item.caseNo}
                  </div>
                )}
              </div>

              {/* Durum */}
              <div className="col-start-3 md:col-start-4 row-start-1 md:row-start-auto justify-self-end md:justify-self-start inline-flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: status.color }} />
                <span className="font-mono text-[9px] tracking-[0.16em] uppercase font-semibold" style={{ color: status.color }}>
                  {status.label}
                </span>
              </div>

              {/* Süre */}
              <div className="hidden md:block justify-self-end font-mono text-[10px] tracking-[0.04em] text-[var(--fg-subtle)] tabular-nums whitespace-nowrap">
                {formatAgo(item.ts)}
              </div>
            </div>
          );
        })}
      </div>
    </HairlineCard>
  );
}
