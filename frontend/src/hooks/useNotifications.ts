import { useCallback, useEffect, useRef, useState } from "react";
import { useAuthRequest } from "@/hooks/useAuthRequest";

/**
 * Uygulama içi bildirim uçlarının (G081, `backend/routes/notifications.py`)
 * frontend tarafı.
 *
 * Kanal kararı (G083): YALNIZ uygulama içi polling. SSE/WebSocket bilinçli
 * olarak seçilmedi — backend 2 worker'la koşuyor ve konteyner nginx'inin
 * `proxy_read_timeout`u uzun ömürlü bağlantılar için ayarlı değil; zil rozeti
 * için 60 sn gecikme fazlasıyla yeterli.
 *
 * `document.hidden` iken sayaç isteği HİÇ atılmaz: arka planda duran sekmeler
 * (bu uygulama gün boyu açık kalıyor) boşuna trafik üretmesin. Sekme geri
 * görünür olunca beklemeden BİR KEZ tazelenir, sonra periyot yeniden kurulur.
 */

export interface NotificationItem {
    id: number;
    type: string;
    severity: string | null;
    title: string;
    body: string | null;
    case_id: number | null;
    document_id: number | null;
    due_date: string | null;
    read_at: string | null;
    is_read: boolean;
    created_at: string | null;
}

/** Liste ucundan çekilen satır sayısı — panel sayfalamaz, "son N"i gösterir. */
export const NOTIFICATION_LIST_LIMIT = 20;

/** Sayaç tazeleme periyodu. Testler de bu sabiti kullanır. */
export const NOTIFICATION_POLL_MS = 60_000;

export const NOTIFICATION_LIST_ERROR =
    "Bildirimler alınamadı — sunucuya ulaşılamadı.";

/** Okundu işaretleme başarısız olunca panelde satır/başlık düzeyinde gösterilen metin (G098). */
export const NOTIFICATION_MARK_ERROR = "İşaretlenemedi — tekrar deneyin.";

/**
 * Başarısız okundu işaretlemesinin yeri: `id` dolu = o satır (`markRead`),
 * `id === null` = "tümünü okundu işaretle" (`markAllRead`). Toast DEĞİL —
 * G002 toast seli dersi; bir sonraki başarılı işlemde ya da panel kapanınca
 * temizlenir.
 */
export interface NotificationMarkError {
    id: number | null;
    message: string;
}

export interface NotificationsApi {
    unreadCount: number;
    items: NotificationItem[];
    isLoading: boolean;
    listError: string | null;
    refreshCount: () => Promise<void>;
    loadList: () => Promise<void>;
    markRead: (id: number) => Promise<void>;
    markAllRead: () => Promise<void>;
    // G098'de eklendi; opsiyonel tutuldu ki hook'u mock'layan eski tüketiciler
    // (NotificationBell.test.tsx `hookState`) alan eklemeden derlenmeye devam etsin.
    markError?: NotificationMarkError | null;
    clearMarkError?: () => void;
}

export const useNotifications = (): NotificationsApi => {
    const { authRequest } = useAuthRequest();

    const [unreadCount, setUnreadCount] = useState(0);
    const [items, setItems] = useState<NotificationItem[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [listError, setListError] = useState<string | null>(null);
    const [markError, setMarkError] = useState<NotificationMarkError | null>(null);

    const clearMarkError = useCallback(() => setMarkError(null), []);

    const refreshCount = useCallback(async () => {
        const response = await authRequest("/api/notifications/count", "GET");
        // Hata durumunda sayaç SIFIRLANMAZ: 0 "okunmamış bildirimin yok" der ve
        // gerçek arızayı (kesinti) kullanıcıdan gizlerdi. Son bilinen değer kalır.
        if (!response || !response.ok) return;
        const data = await response.json().catch(() => null);
        const adet = Number((data as { unread?: unknown } | null)?.unread);
        if (Number.isFinite(adet) && adet >= 0) setUnreadCount(adet);
    }, [authRequest]);

    const loadList = useCallback(async () => {
        setIsLoading(true);
        setListError(null);
        try {
            const response = await authRequest(
                `/api/notifications?limit=${NOTIFICATION_LIST_LIMIT}`,
                "GET",
            );
            if (!response || !response.ok) throw new Error(NOTIFICATION_LIST_ERROR);
            const data = await response.json();
            // G002 dersi: hata boş listeye ÇEVRİLMEZ. Beklenmedik gövde de hatadır —
            // "bildirim yok" ekranı, ulaşılamayan sunucuyu maskelememeli.
            if (!Array.isArray(data)) throw new Error(NOTIFICATION_LIST_ERROR);
            setItems(data as NotificationItem[]);
            // Başarılı bir işlem bayat işaretleme hatasını temizler.
            setMarkError(null);
        } catch {
            setItems([]);
            setListError(NOTIFICATION_LIST_ERROR);
        } finally {
            setIsLoading(false);
        }
    }, [authRequest]);

    const markRead = useCallback(async (id: number) => {
        const response = await authRequest(`/api/notifications/${id}/read`, "POST");
        // Başarısızlık (HTTP hatası ya da `authRequest` null = 401/ağ) sessiz
        // geçilmez: yerel durum DEĞİŞMEZ, satır düzeyinde hata gösterilir.
        if (!response || !response.ok) {
            setMarkError({ id, message: NOTIFICATION_MARK_ERROR });
            return;
        }
        setMarkError(null);
        setItems((prev) =>
            prev.map((n) =>
                n.id === id && !n.is_read
                    ? { ...n, is_read: true, read_at: new Date().toISOString() }
                    : n,
            ),
        );
        // Sayaç yerelde düşürülür (bir sonraki polling zaten mutabık kılar);
        // negatife düşmesin diye taban 0.
        setUnreadCount((prev) => (prev > 0 ? prev - 1 : 0));
    }, [authRequest]);

    const markAllRead = useCallback(async () => {
        const response = await authRequest("/api/notifications/read-all", "POST");
        if (!response || !response.ok) {
            setMarkError({ id: null, message: NOTIFICATION_MARK_ERROR });
            return;
        }
        setMarkError(null);
        const simdi = new Date().toISOString();
        setItems((prev) =>
            prev.map((n) => (n.is_read ? n : { ...n, is_read: true, read_at: simdi })),
        );
        setUnreadCount(0);
    }, [authRequest]);

    // Sayaç polling'i + sekme görünürlüğü.
    const refreshRef = useRef(refreshCount);
    refreshRef.current = refreshCount;

    useEffect(() => {
        let timer: ReturnType<typeof setInterval> | null = null;

        const durdur = () => {
            if (timer !== null) {
                clearInterval(timer);
                timer = null;
            }
        };
        const basla = () => {
            if (timer === null) {
                timer = setInterval(() => { void refreshRef.current(); }, NOTIFICATION_POLL_MS);
            }
        };

        const gorunurlukDegisti = () => {
            if (document.hidden) {
                durdur();
                return;
            }
            // Sekmeye dönüldü: periyodu beklemeden tazele, sonra saati yeniden kur.
            void refreshRef.current();
            basla();
        };

        if (!document.hidden) {
            void refreshRef.current();
            basla();
        }
        document.addEventListener("visibilitychange", gorunurlukDegisti);

        return () => {
            durdur();
            document.removeEventListener("visibilitychange", gorunurlukDegisti);
        };
    }, []);

    return {
        unreadCount,
        items,
        isLoading,
        listError,
        refreshCount,
        loadList,
        markRead,
        markAllRead,
        markError,
        clearMarkError,
    };
};
