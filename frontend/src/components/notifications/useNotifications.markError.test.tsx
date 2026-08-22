// @vitest-environment jsdom
// useNotifications — G098: okundu işaretleme hatası geri bildirimi + 401/null yolu.
//
// Kilitlenen davranışlar:
//  - markRead / markAllRead başarısızken yerel durum DEĞİŞMEZ ve `markError` dolar
//    (satır için id, tümü için null); başarılı işlem / clearMarkError temizler.
//  - `authRequest` null (useAuthRequest istisnada null döner: 401/ağ) →
//    sayaç korunur; loadList'te listError dolar, items boşalır.
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
  NOTIFICATION_MARK_ERROR,
  NOTIFICATION_POLL_MS,
  type NotificationItem,
  type NotificationsApi,
} from "@/hooks/useNotifications";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const jsonResponse = (body: unknown, ok = true) =>
  ({ ok, json: async () => body }) as unknown as Response;

const bildirim = (over: Partial<NotificationItem> = {}): NotificationItem => ({
  id: 1,
  type: "doc-processed",
  severity: "info",
  title: "Belge arşive yüklendi",
  body: null,
  case_id: 42,
  document_id: 7,
  due_date: null,
  read_at: null,
  is_read: false,
  created_at: "2026-08-20T09:00:00",
  ...over,
});

/** Varsayılan sunucu: sayaç 2, iki okunmamış satır, POST'lar başarılı. */
const saglikliSunucu = async (url: string) => {
  if (url.startsWith("/api/notifications/count")) return jsonResponse({ unread: 2 });
  if (url.startsWith("/api/notifications?")) {
    return jsonResponse([bildirim({ id: 1 }), bildirim({ id: 2 })]);
  }
  return jsonResponse({ success: true });
};

/** Yalnız POST'lar (okundu işaretleme) başarısız; GET'ler sağlıklı. */
const postlarBozuk = async (url: string, method?: string) => {
  if (method === "POST") return jsonResponse(null, false);
  return saglikliSunucu(url);
};

describe("useNotifications — işaretleme hatası (G098)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    container = document.createElement("div");
    document.body.appendChild(container);
    authRequestMock.mockImplementation(saglikliSunucu);
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

  async function mountWithList(): Promise<() => NotificationsApi> {
    const api = await mountHook();
    await act(async () => {
      await api().loadList();
    });
    expect(api().items).toHaveLength(2);
    expect(api().unreadCount).toBe(2);
    return api;
  }

  it("başlangıçta markError boş, clearMarkError sunulur", async () => {
    const api = await mountHook();
    expect(api().markError).toBeNull();
    expect(typeof api().clearMarkError).toBe("function");
  });

  it("markRead başarısız → satır okunmuş GÖRÜNMEZ, markError o satırın id'siyle dolar", async () => {
    const api = await mountWithList();
    authRequestMock.mockImplementation(postlarBozuk);

    await act(async () => {
      await api().markRead(2);
    });

    expect(api().items.find((n) => n.id === 2)!.is_read).toBe(false);
    expect(api().unreadCount).toBe(2);
    expect(api().markError).toEqual({ id: 2, message: NOTIFICATION_MARK_ERROR });
  });

  it("markAllRead başarısız → hiçbir satır okunmaz, markError id=null ile dolar", async () => {
    const api = await mountWithList();
    authRequestMock.mockImplementation(postlarBozuk);

    await act(async () => {
      await api().markAllRead();
    });

    expect(api().items.some((n) => n.is_read)).toBe(false);
    expect(api().unreadCount).toBe(2);
    expect(api().markError).toEqual({ id: null, message: NOTIFICATION_MARK_ERROR });
  });

  it("authRequest null (401) ile markRead de aynı hatayı verir, durum değişmez", async () => {
    const api = await mountWithList();
    authRequestMock.mockImplementation(async (url: string, method?: string) =>
      method === "POST" ? null : saglikliSunucu(url),
    );

    await act(async () => {
      await api().markRead(1);
    });

    expect(api().items[0].is_read).toBe(false);
    expect(api().markError).toEqual({ id: 1, message: NOTIFICATION_MARK_ERROR });
  });

  it("başarılı markRead önceki hatayı temizler", async () => {
    const api = await mountWithList();
    authRequestMock.mockImplementation(postlarBozuk);
    await act(async () => {
      await api().markRead(1);
    });
    expect(api().markError).not.toBeNull();

    authRequestMock.mockImplementation(saglikliSunucu);
    await act(async () => {
      await api().markRead(1);
    });

    expect(api().markError).toBeNull();
    expect(api().items[0].is_read).toBe(true);
    expect(api().unreadCount).toBe(1);
  });

  it("başarılı markAllRead önceki hatayı temizler", async () => {
    const api = await mountWithList();
    authRequestMock.mockImplementation(postlarBozuk);
    await act(async () => {
      await api().markAllRead();
    });
    expect(api().markError).toEqual({ id: null, message: NOTIFICATION_MARK_ERROR });

    authRequestMock.mockImplementation(saglikliSunucu);
    await act(async () => {
      await api().markAllRead();
    });

    expect(api().markError).toBeNull();
    expect(api().unreadCount).toBe(0);
  });

  it("başarılı loadList de bayat işaretleme hatasını temizler", async () => {
    const api = await mountWithList();
    authRequestMock.mockImplementation(postlarBozuk);
    await act(async () => {
      await api().markRead(1);
    });
    expect(api().markError).not.toBeNull();

    authRequestMock.mockImplementation(saglikliSunucu);
    await act(async () => {
      await api().loadList();
    });

    expect(api().markError).toBeNull();
  });

  it("clearMarkError hatayı temizler, satırlara dokunmaz", async () => {
    const api = await mountWithList();
    authRequestMock.mockImplementation(postlarBozuk);
    await act(async () => {
      await api().markRead(1);
    });
    expect(api().markError).not.toBeNull();

    act(() => {
      api().clearMarkError!();
    });

    expect(api().markError).toBeNull();
    expect(api().items).toHaveLength(2);
    expect(api().items[0].is_read).toBe(false);
  });
});

describe("useNotifications — authRequest null yolu (401/ağ)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    container = document.createElement("div");
    document.body.appendChild(container);
    authRequestMock.mockImplementation(saglikliSunucu);
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

  it("sayaç isteği null dönerse unreadCount DEĞİŞMEZ (son bilinen değer kalır)", async () => {
    const api = await mountHook();
    expect(api().unreadCount).toBe(2);

    authRequestMock.mockImplementation(async () => null);
    await act(async () => {
      vi.advanceTimersByTime(NOTIFICATION_POLL_MS);
    });

    expect(api().unreadCount).toBe(2);
    // ve polling null yüzünden ölmedi: bir sonraki periyotta yine denendi
    const oncekiAdet = authRequestMock.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(NOTIFICATION_POLL_MS);
    });
    expect(authRequestMock.mock.calls.length).toBe(oncekiAdet + 1);
  });

  it("mount'ta sayaç null dönerse sayaç 0'da kalır, istisna fırlamaz", async () => {
    authRequestMock.mockImplementation(async () => null);
    const api = await mountHook();

    expect(api().unreadCount).toBe(0);
  });

  it("liste isteği null dönerse listError dolar, items boşalır", async () => {
    const api = await mountHook();
    await act(async () => {
      await api().loadList();
    });
    expect(api().items).toHaveLength(2);

    authRequestMock.mockImplementation(async (url: string) =>
      url.startsWith("/api/notifications?") ? null : saglikliSunucu(url),
    );
    await act(async () => {
      await api().loadList();
    });

    expect(api().items).toHaveLength(0);
    expect(api().listError).toBe(NOTIFICATION_LIST_ERROR);
    expect(api().isLoading).toBe(false);
  });
});
