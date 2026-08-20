import { AlertTriangle, BellOff, CheckCheck, Loader2 } from "lucide-react";
import { formatAgo } from "@/lib/relativeTime";
import type { NotificationItem } from "@/hooks/useNotifications";

export const NOTIFICATIONS_EMPTY_TEXT = "Bildiriminiz yok.";

type NotificationsPanelProps = {
  items: NotificationItem[];
  isLoading: boolean;
  /** Liste ucundan gelen hata metni. `null` = hata yok. */
  error: string | null;
  unreadCount: number;
  onSelect: (item: NotificationItem) => void;
  onMarkAllRead: () => void;
  onRetry: () => void;
};

/**
 * Zil butonunun altında açılan bildirim listesi. Salt sunum — veri ve
 * işaretleme çağrıları `useNotifications`ta, açma/kapama `NotificationBell`de.
 *
 * ÜÇ DURUM AYRI ÇİZİLİR: hata, boş, dolu. Hatanın boş listeye çevrilmesi
 * (G002 dersi) burada bilinçli olarak yasak — "bildiriminiz yok" ekranı,
 * ulaşılamayan sunucuyu maskeleyip kullanıcıya sahte huzur verirdi.
 */
export function NotificationsPanel({
  items,
  isLoading,
  error,
  unreadCount,
  onSelect,
  onMarkAllRead,
  onRetry,
}: NotificationsPanelProps) {
  return (
    <div
      role="dialog"
      aria-label="Bildirimler"
      className="absolute right-0 top-[calc(100%+8px)] z-50 w-[360px] max-w-[calc(100vw-2rem)] border border-[var(--border)] bg-[var(--bg-elevated)] rounded-[4px] shadow-[0_18px_40px_-20px_rgba(0,0,0,0.45)] overflow-hidden"
    >
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-[var(--border)]">
        <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
          Bildirimler
        </span>
        <button
          type="button"
          onClick={onMarkAllRead}
          disabled={unreadCount === 0}
          className="inline-flex items-center gap-1 text-[11px] text-[var(--fg-muted)] transition-colors hover:text-[var(--brand)] disabled:opacity-40 disabled:cursor-default disabled:hover:text-[var(--fg-muted)]"
        >
          <CheckCheck className="w-3 h-3" />
          Tümünü okundu işaretle
        </button>
      </div>

      <div className="max-h-[380px] overflow-y-auto">
        {error ? (
          <div role="alert" className="px-3.5 py-6 flex flex-col items-center gap-2 text-center">
            <AlertTriangle className="w-4 h-4 text-[var(--danger,#b3261e)]" />
            <p className="text-[12.5px] text-[var(--fg)]">{error}</p>
            <button
              type="button"
              onClick={onRetry}
              className="text-[11.5px] text-[var(--brand)] underline underline-offset-2"
            >
              Tekrar dene
            </button>
          </div>
        ) : isLoading && items.length === 0 ? (
          <div className="px-3.5 py-6 flex items-center justify-center gap-2 text-[12.5px] text-[var(--fg-muted)]">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Yükleniyor…
          </div>
        ) : items.length === 0 ? (
          <div className="px-3.5 py-6 flex flex-col items-center gap-2 text-center">
            <BellOff className="w-4 h-4 text-[var(--fg-subtle)]" />
            <p className="text-[12.5px] text-[var(--fg-muted)]">{NOTIFICATIONS_EMPTY_TEXT}</p>
          </div>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onSelect(item)}
                  className="w-full text-left px-3.5 py-2.5 flex gap-2.5 transition-colors hover:bg-[var(--brand-soft)]"
                >
                  <span
                    aria-hidden="true"
                    className={
                      "mt-[6px] w-1.5 h-1.5 rounded-full shrink-0 " +
                      (item.is_read ? "bg-transparent" : "bg-[var(--brand)]")
                    }
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-2">
                      <span
                        className={
                          "text-[13px] truncate " +
                          (item.is_read
                            ? "text-[var(--fg-muted)]"
                            : "text-[var(--fg)] font-medium")
                        }
                      >
                        {item.title}
                      </span>
                      <span className="font-mono text-[10px] text-[var(--fg-subtle)] shrink-0">
                        {formatAgo(item.created_at)}
                      </span>
                    </span>
                    {item.body && (
                      <span className="block mt-0.5 text-[11.5px] text-[var(--fg-muted)] line-clamp-2">
                        {item.body}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
