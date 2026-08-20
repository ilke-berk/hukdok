import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { Bell } from "lucide-react";
import { useNotifications, type NotificationItem } from "@/hooks/useNotifications";
import { NotificationsPanel } from "@/components/notifications/NotificationsPanel";
import { formatBadge } from "@/components/notifications/badge";

/**
 * Üst bardaki zil: okunmamış rozeti + açılır bildirim paneli (G083).
 *
 * Sayaç arka planda 60 sn'de bir tazelenir (`useNotifications`); LİSTE ise
 * yalnız panel açılınca çekilir — kapalı zil için satırları taşımak boşuna
 * trafik olurdu.
 */
export function NotificationBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const {
    unreadCount,
    items,
    isLoading,
    listError,
    loadList,
    markRead,
    markAllRead,
  } = useNotifications();

  // Dışarı tıklama + Escape kapatır. Dinleyiciler yalnız panel AÇIKKEN bağlanır.
  useEffect(() => {
    if (!open) return;

    const disariTiklama = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const tusaBasildi = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };

    document.addEventListener("mousedown", disariTiklama);
    document.addEventListener("keydown", tusaBasildi);
    return () => {
      document.removeEventListener("mousedown", disariTiklama);
      document.removeEventListener("keydown", tusaBasildi);
    };
  }, [open]);

  const zileTiklandi = useCallback(() => {
    setOpen((onceki) => {
      // Her açılışta liste yeniden çekilir: panel kapalıyken gelen bildirimler
      // (ve başka sekmede yapılan okumalar) bayat görünmesin.
      if (!onceki) void loadList();
      return !onceki;
    });
  }, [loadList]);

  const bildirimeTiklandi = useCallback(async (item: NotificationItem) => {
    if (!item.is_read) await markRead(item.id);
    // Davası olmayan bildirim (ör. genel duyuru) panelde kalır — gidecek yer yok.
    if (item.case_id) {
      setOpen(false);
      navigate(`/cases/${item.case_id}`);
    }
  }, [markRead, navigate]);

  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        aria-label="Bildirimler"
        aria-haspopup="dialog"
        aria-expanded={open}
        className="w-[38px] h-[38px] grid place-items-center border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--fg-muted)] cursor-pointer rounded-[4px] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--fg)]"
        onClick={zileTiklandi}
      >
        <Bell className="w-4 h-4" />
      </button>

      {/* Okunmamış yoksa rozet HİÇ çizilmez — "0" rozeti gürültüdür. */}
      {unreadCount > 0 && (
        <span
          data-testid="notification-badge"
          aria-label={`${unreadCount} okunmamış bildirim`}
          className="absolute -top-1.5 -right-1.5 z-10 min-w-[17px] h-[17px] px-1 grid place-items-center bg-[var(--brand)] text-[var(--brand-fg)] rounded-full font-mono text-[9.5px] font-semibold leading-none pointer-events-none select-none"
        >
          {formatBadge(unreadCount)}
        </span>
      )}

      {open && (
        <NotificationsPanel
          items={items}
          isLoading={isLoading}
          error={listError}
          unreadCount={unreadCount}
          onSelect={(item) => { void bildirimeTiklandi(item); }}
          onMarkAllRead={() => { void markAllRead(); }}
          onRetry={() => { void loadList(); }}
        />
      )}
    </div>
  );
}
