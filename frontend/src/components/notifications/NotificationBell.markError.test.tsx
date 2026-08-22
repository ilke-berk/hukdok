// @vitest-environment jsdom
// NotificationBell — G098: loadList yan etkisi updater dışında, işaretleme hatası
// panel içinde (toast YOK), panel kapanınca temizlenir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import type { NotificationItem, NotificationsApi } from "@/hooks/useNotifications";

const navigateMock = vi.hoisted(() => vi.fn());
vi.mock("react-router", () => ({ useNavigate: () => navigateMock }));

// Toast kütüphanesi gözlem altında: zil paneli onu HİÇ çağırmamalı (G002 toast seli dersi).
const toastMock = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: toastMock }));

const hookMocks = vi.hoisted(() => ({
  loadList: vi.fn(),
  markRead: vi.fn(),
  markAllRead: vi.fn(),
  refreshCount: vi.fn(),
  clearMarkError: vi.fn(),
}));

let hookState: NotificationsApi;
vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: () => hookState,
}));

import { NotificationBell } from "./NotificationBell";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const MARK_ERROR_TEXT = "İşaretlenemedi — tekrar deneyin.";

const bildirim = (over: Partial<NotificationItem> = {}): NotificationItem => ({
  id: 1,
  type: "doc-processed",
  severity: "info",
  title: "Belge arşive yüklendi",
  body: "TEBLIGAT",
  case_id: null,
  document_id: 7,
  due_date: null,
  read_at: null,
  is_read: false,
  created_at: new Date().toISOString(),
  ...over,
});

describe("NotificationBell — G098", () => {
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
      markError: null,
      clearMarkError: hookMocks.clearMarkError,
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

  /** Hook durumunu değiştirip aynı ağacı yeniden çizer (hook mock'u senkron okunur). */
  function rerender(state: Partial<NotificationsApi>) {
    hookState = { ...hookState, ...state };
    act(() => {
      root!.render(<NotificationBell />);
    });
  }

  const zil = () => container.querySelector<HTMLButtonElement>("button[aria-label='Bildirimler']")!;
  const panel = () => container.querySelector("[role='dialog']");
  const isaretHatasi = () => container.querySelector("[data-testid='mark-error']");

  const tikla = async (el: Element) => {
    await act(async () => {
      el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
  };

  it("kapalıdan açılınca liste TAM BİR kez çekilir; açıktan kapanınca ÇEKİLMEZ", async () => {
    render();
    expect(hookMocks.loadList).not.toHaveBeenCalled();

    await tikla(zil()); // kapalı → açık
    expect(panel()).not.toBeNull();
    expect(hookMocks.loadList).toHaveBeenCalledTimes(1);

    await tikla(zil()); // açık → kapalı
    expect(panel()).toBeNull();
    expect(hookMocks.loadList).toHaveBeenCalledTimes(1);

    await tikla(zil()); // yeniden açılış → yeniden çekilir
    expect(hookMocks.loadList).toHaveBeenCalledTimes(2);
  });

  it("markRead başarısız: satır okunmamış kalır, satır düzeyinde hata görünür, toast YOK", async () => {
    render({ unreadCount: 2, items: [bildirim({ id: 7 }), bildirim({ id: 8 })] });
    await tikla(zil());

    // Hook, POST başarısız olunca satırı değiştirmez ve markError'ı doldurur.
    rerender({ markError: { id: 7, message: MARK_ERROR_TEXT } });

    const satirlar = Array.from(container.querySelectorAll("li"));
    expect(satirlar[0].textContent).toContain(MARK_ERROR_TEXT);
    expect(satirlar[1].textContent).not.toContain(MARK_ERROR_TEXT);
    expect(container.querySelectorAll("[data-testid='mark-error']")).toHaveLength(1);

    // Okunmamış noktası hâlâ 7 nolu satırda (is_read değişmedi).
    expect(hookState.items[0].is_read).toBe(false);

    expect(toastMock.error).not.toHaveBeenCalled();
    expect(toastMock.warning).not.toHaveBeenCalled();
    expect(toastMock.info).not.toHaveBeenCalled();
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it("markAllRead başarısız: hata başlık altında görünür, satırlarda değil, toast YOK", async () => {
    render({ unreadCount: 2, items: [bildirim({ id: 7 }), bildirim({ id: 8 })] });
    await tikla(zil());

    rerender({ markError: { id: null, message: MARK_ERROR_TEXT } });

    expect(isaretHatasi()).not.toBeNull();
    expect(isaretHatasi()!.closest("li")).toBeNull();
    expect(container.textContent).toContain(MARK_ERROR_TEXT);
    expect(toastMock.error).not.toHaveBeenCalled();
  });

  it("hata temizlenince (başarılı işlem) panelden kaybolur", async () => {
    render({ items: [bildirim({ id: 7 })] });
    await tikla(zil());
    rerender({ markError: { id: 7, message: MARK_ERROR_TEXT } });
    expect(isaretHatasi()).not.toBeNull();

    rerender({ markError: null });
    expect(isaretHatasi()).toBeNull();
  });

  it("panel kapanınca clearMarkError çağrılır", async () => {
    render({ items: [bildirim({ id: 7 })] });
    await tikla(zil());
    hookMocks.clearMarkError.mockClear();

    await tikla(zil()); // kapat

    expect(panel()).toBeNull();
    expect(hookMocks.clearMarkError).toHaveBeenCalled();
  });

  it("hook clearMarkError sunmuyorsa (eski mock) bileşen çökmez", async () => {
    render({ clearMarkError: undefined, markError: undefined });
    await tikla(zil());
    await tikla(zil());
    expect(panel()).toBeNull();
  });
});
