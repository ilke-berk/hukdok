// @vitest-environment jsdom
// useNotifications — polling sözleşmesi (G083).
//
// Kilitlenen davranışlar: 60 sn periyot, `document.hidden` iken İSTEK YOK,
// sekmeye dönüşte periyodu beklemeden bir tazeleme, ve "hata ≠ boş liste".
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));

import {
  useNotifications,
  NOTIFICATION_LIST_ERROR,
  NOTIFICATION_POLL_MS,
  type NotificationItem,
  type NotificationsApi,
} from "./useNotifications";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const jsonResponse = (body: unknown, ok = true) =>
  ({ ok, json: async () => body }) as unknown as Response;

const bildirim = (over: Partial<NotificationItem> = {}): NotificationItem => ({
  id: 1,
  type: "doc-processed",
  severity: "info",
  title: "Belge arşive yüklendi",
  body: "TEBLIGAT — 2024/123",
  case_id: 42,
  document_id: 7,
  due_date: null,
  read_at: null,
  is_read: false,
  created_at: "2026-08-20T09:00:00",
  ...over,
});

/** jsdom'da `document.hidden` salt-okunur getter'dır; test için değiştirilebilir kılınır. */
let gizli = false;
function setHidden(value: boolean) {
  gizli = value;
}
Object.defineProperty(document, "hidden", {
  configurable: true,
  get: () => gizli,
});

const countCalls = () =>
  authRequestMock.mock.calls.filter((c) => c[0] === "/api/notifications/count").length;

describe("useNotifications", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    setHidden(false);
    container = document.createElement("div");
    document.body.appendChild(container);
    authRequestMock.mockImplementation(async (url: string) => {
      if (url.startsWith("/api/notifications/count")) return jsonResponse({ unread: 3 });
      if (url.startsWith("/api/notifications?")) return jsonResponse([bildirim()]);
      return jsonResponse({ success: true });
    });
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    vi.useRealTimers();
  });

  async function mountHook(): Promise<() => NotificationsApi> {
    let captured: NotificationsApi | null = null;
    const Harness = () => {
      captured = useNotifications();
      return null;
    };
    root = createRoot(container);
    await act(async () => {
      root!.render(<Harness />);
    });
    return () => captured!;
  }

  const ilerlet = async (ms: number) => {
    await act(async () => {
      vi.advanceTimersByTime(ms);
    });
  };

  const gorunurlukOlayi = async () => {
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
  };

  it("mount'ta sayacı bir kez çeker ve okunmamış adedini yazar", async () => {
    const api = await mountHook();

    expect(countCalls()).toBe(1);
    expect(api().unreadCount).toBe(3);
  });

  it("60 saniyede bir tazeler", async () => {
    await mountHook();
    expect(countCalls()).toBe(1);

    await ilerlet(NOTIFICATION_POLL_MS);
    expect(countCalls()).toBe(2);

    await ilerlet(NOTIFICATION_POLL_MS);
    expect(countCalls()).toBe(3);
  });

  it("periyot dolmadan tazeleme YOK", async () => {
    await mountHook();

    await ilerlet(NOTIFICATION_POLL_MS - 1);
    expect(countCalls()).toBe(1);
  });

  it("sekme gizlenince polling durur — hiç istek atılmaz", async () => {
    await mountHook();
    expect(countCalls()).toBe(1);

    setHidden(true);
    await gorunurlukOlayi();

    await ilerlet(NOTIFICATION_POLL_MS * 3);
    expect(countCalls()).toBe(1);
  });

  it("sekme geri görünür olunca periyodu BEKLEMEDEN bir kez tazeler", async () => {
    await mountHook();
    setHidden(true);
    await gorunurlukOlayi();
    await ilerlet(NOTIFICATION_POLL_MS * 2);
    expect(countCalls()).toBe(1);

    setHidden(false);
    await gorunurlukOlayi();
    expect(countCalls()).toBe(2); // zaman ilerlemeden, anında

    // ve saat yeniden kurulmuş olmalı
    await ilerlet(NOTIFICATION_POLL_MS);
    expect(countCalls()).toBe(3);
  });

  it("gizli sekmede mount edilirse hiç istek atmaz", async () => {
    setHidden(true);
    await mountHook();

    expect(countCalls()).toBe(0);
    await ilerlet(NOTIFICATION_POLL_MS * 2);
    expect(countCalls()).toBe(0);
  });

  it("unmount'tan sonra zamanlayıcı susar", async () => {
    await mountHook();
    act(() => root!.unmount());
    root = null;

    await ilerlet(NOTIFICATION_POLL_MS * 3);
    expect(countCalls()).toBe(1);
  });

  it("sayaç isteği başarısızsa son bilinen değer KORUNUR (0'a düşmez)", async () => {
    const api = await mountHook();
    expect(api().unreadCount).toBe(3);

    authRequestMock.mockImplementation(async () => jsonResponse(null, false));
    await ilerlet(NOTIFICATION_POLL_MS);

    expect(api().unreadCount).toBe(3);
  });

  it("loadList satırları yazar, hata bırakmaz", async () => {
    const api = await mountHook();
    await act(async () => {
      await api().loadList();
    });

    expect(api().items).toHaveLength(1);
    expect(api().items[0].title).toBe("Belge arşive yüklendi");
    expect(api().listError).toBeNull();
  });

  it("liste hatası boş listeye ÇEVRİLMEZ — listError dolar", async () => {
    const api = await mountHook();
    authRequestMock.mockImplementation(async (url: string) => {
      if (url.startsWith("/api/notifications?")) return jsonResponse(null, false);
      return jsonResponse({ unread: 3 });
    });

    await act(async () => {
      await api().loadList();
    });

    expect(api().items).toHaveLength(0);
    expect(api().listError).toBe(NOTIFICATION_LIST_ERROR);
  });

  it("beklenmedik gövde (dizi değil) de hata sayılır", async () => {
    const api = await mountHook();
    authRequestMock.mockImplementation(async (url: string) => {
      if (url.startsWith("/api/notifications?")) return jsonResponse({ items: [] });
      return jsonResponse({ unread: 3 });
    });

    await act(async () => {
      await api().loadList();
    });

    expect(api().listError).toBe(NOTIFICATION_LIST_ERROR);
  });

  it("markRead satırı okundu yapar ve sayacı bir düşürür", async () => {
    const api = await mountHook();
    await act(async () => {
      await api().loadList();
    });

    await act(async () => {
      await api().markRead(1);
    });

    expect(authRequestMock).toHaveBeenCalledWith("/api/notifications/1/read", "POST");
    expect(api().items[0].is_read).toBe(true);
    expect(api().unreadCount).toBe(2);
  });

  it("markRead sunucu hatasında yerel durumu DEĞİŞTİRMEZ", async () => {
    const api = await mountHook();
    await act(async () => {
      await api().loadList();
    });

    authRequestMock.mockImplementation(async () => jsonResponse(null, false));
    await act(async () => {
      await api().markRead(1);
    });

    expect(api().items[0].is_read).toBe(false);
    expect(api().unreadCount).toBe(3);
  });

  it("markAllRead rozeti sıfırlar ve tüm satırları okundu yapar", async () => {
    authRequestMock.mockImplementation(async (url: string) => {
      if (url.startsWith("/api/notifications/count")) return jsonResponse({ unread: 2 });
      if (url.startsWith("/api/notifications?")) {
        return jsonResponse([bildirim({ id: 1 }), bildirim({ id: 2 })]);
      }
      return jsonResponse({ success: true, updated: 2 });
    });

    const api = await mountHook();
    await act(async () => {
      await api().loadList();
    });
    expect(api().unreadCount).toBe(2);

    await act(async () => {
      await api().markAllRead();
    });

    expect(authRequestMock).toHaveBeenCalledWith("/api/notifications/read-all", "POST");
    expect(api().unreadCount).toBe(0);
    expect(api().items.every((n) => n.is_read)).toBe(true);
  });
});
