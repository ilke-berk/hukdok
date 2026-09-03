// @vitest-environment jsdom
// NotificationBell — rozet, açma/kapama ve satıra tıklama davranışı (G083).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import type { NotificationItem, NotificationsApi } from "@/hooks/useNotifications";

const navigateMock = vi.hoisted(() => vi.fn());
vi.mock("react-router", () => ({ useNavigate: () => navigateMock }));

const hookMocks = vi.hoisted(() => ({
  loadList: vi.fn(),
  markRead: vi.fn(),
  markAllRead: vi.fn(),
  refreshCount: vi.fn(),
}));

// Hook'un kendi sözleşmesi useNotifications.test.tsx'te kilitli; burada yalnız
// bileşenin ona nasıl bağlandığı sınanır.
let hookState: NotificationsApi;
vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: () => hookState,
}));

import { NotificationBell } from "./NotificationBell";
import { formatBadge } from "./badge";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const bildirim = (over: Partial<NotificationItem> = {}): NotificationItem => ({
  id: 1,
  type: "doc-processed",
  severity: "info",
  title: "Belge arşive yüklendi",
  body: "TEBLIGAT",
  case_id: 42,
  document_id: 7,
  due_date: null,
  read_at: null,
  is_read: false,
  created_at: new Date().toISOString(),
  ...over,
});

describe("NotificationBell", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;

  beforeEach(() => {
    vi.clearAllMocks();
    hookMocks.loadList.mockResolvedValue(undefined);
    hookMocks.markRead.mockResolvedValue(undefined);
    hookMocks.markAllRead.mockResolvedValue(undefined);
    hookState = {
      unreadCount: 0,
      items: [],
      isLoading: false,
      listError: null,
      refreshCount: hookMocks.refreshCount,
      loadList: hookMocks.loadList,
      markRead: hookMocks.markRead,
      markAllRead: hookMocks.markAllRead,
    };
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
  });

  function render(state: Partial<NotificationsApi> = {}) {
    hookState = { ...hookState, ...state };
    root = createRoot(container);
    act(() => {
      root!.render(<NotificationBell />);
    });
  }

  const zil = () => container.querySelector<HTMLButtonElement>("button[aria-label='Bildirimler']")!;
  const rozet = () => container.querySelector("[data-testid='notification-badge']");
  const panel = () => container.querySelector("[role='dialog']");

  const tikla = async (el: Element) => {
    await act(async () => {
      el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
  };

  it("formatBadge tavanı 9+ ile keser", () => {
    expect(formatBadge(1)).toBe("1");
    expect(formatBadge(9)).toBe("9");
    expect(formatBadge(10)).toBe("9+");
    expect(formatBadge(240)).toBe("9+");
  });

  it("okunmamış 0 iken rozet HİÇ çizilmez", () => {
    render({ unreadCount: 0 });
    expect(rozet()).toBeNull();
  });

  it("okunmamış varsa rozet sayıyı gösterir", () => {
    render({ unreadCount: 3 });
    expect(rozet()?.textContent).toBe("3");
  });

  it("rozet tavanı ekranda da 9+ görünür", () => {
    render({ unreadCount: 42 });
    expect(rozet()?.textContent).toBe("9+");
  });

  it("zile tıklayınca panel açılır ve liste çekilir", async () => {
    render({ items: [bildirim()] });
    expect(panel()).toBeNull();

    await tikla(zil());

    expect(panel()).not.toBeNull();
    expect(hookMocks.loadList).toHaveBeenCalledTimes(1);
    expect(zil().getAttribute("aria-expanded")).toBe("true");
  });

  it("zile ikinci kez tıklayınca kapanır", async () => {
    render();
    await tikla(zil());
    await tikla(zil());
    expect(panel()).toBeNull();
  });

  it("dışarı tıklama paneli kapatır", async () => {
    render();
    await tikla(zil());
    expect(panel()).not.toBeNull();

    await act(async () => {
      document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    });

    expect(panel()).toBeNull();
  });

  it("panel içine tıklamak kapatmaz", async () => {
    render({ items: [bildirim()] });
    await tikla(zil());

    await act(async () => {
      panel()!.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    });

    expect(panel()).not.toBeNull();
  });

  it("Escape paneli kapatır", async () => {
    render();
    await tikla(zil());

    await act(async () => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });

    expect(panel()).toBeNull();
  });

  it("bildirime tıklayınca okundu işaretlenir ve davaya gidilir", async () => {
    render({ items: [bildirim({ id: 77, case_id: 42 })] });
    await tikla(zil());

    const satir = Array.from(container.querySelectorAll("li button"))[0];
    await tikla(satir);

    expect(hookMocks.markRead).toHaveBeenCalledWith(77);
    expect(navigateMock).toHaveBeenCalledWith("/cases/42");
    expect(panel()).toBeNull(); // gezinmeden önce kapanır
  });

  it("okunmuş bildirim yeniden okundu işaretlenmez", async () => {
    render({ items: [bildirim({ id: 5, is_read: true, read_at: "2026-08-20T10:00:00" })] });
    await tikla(zil());

    await tikla(Array.from(container.querySelectorAll("li button"))[0]);

    expect(hookMocks.markRead).not.toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith("/cases/42");
  });

  it("case_id'siz bildirim gezinmez, panel açık kalır", async () => {
    render({ items: [bildirim({ id: 9, case_id: null })] });
    await tikla(zil());

    await tikla(Array.from(container.querySelectorAll("li button"))[0]);

    expect(hookMocks.markRead).toHaveBeenCalledWith(9);
    expect(navigateMock).not.toHaveBeenCalled();
    expect(panel()).not.toBeNull();
  });

  it("veri_teslim bildirimi davasız olsa da Yönetim > Veri Teslimleri sekmesine gider (G117)", async () => {
    render({ items: [bildirim({ id: 11, type: "veri_teslim", case_id: null, document_id: null })] });
    await tikla(zil());

    await tikla(Array.from(container.querySelectorAll("li button"))[0]);

    expect(hookMocks.markRead).toHaveBeenCalledWith(11);
    expect(navigateMock).toHaveBeenCalledWith("/admin?tab=deliveries");
    expect(panel()).toBeNull(); // gezinmeden önce kapanır
  });

  it("'Tümünü okundu işaretle' hook'u çağırır", async () => {
    render({ unreadCount: 2, items: [bildirim({ id: 1 }), bildirim({ id: 2 })] });
    await tikla(zil());

    const b = Array.from(container.querySelectorAll("button")).find((x) =>
      x.textContent?.includes("Tümünü okundu işaretle"),
    )!;
    await tikla(b);

    expect(hookMocks.markAllRead).toHaveBeenCalledTimes(1);
  });

  it("liste hatası panelde görünür", async () => {
    render({ listError: "Bildirimler alınamadı — sunucuya ulaşılamadı." });
    await tikla(zil());

    expect(container.querySelector("[role='alert']")).not.toBeNull();
    expect(container.textContent).toContain("Bildirimler alınamadı");
  });
});
