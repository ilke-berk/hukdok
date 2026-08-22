// @vitest-environment jsdom
// NotificationsPanel — G098: `markError` prop'u satır/başlık düzeyinde çizilir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: vi.fn() }),
}));

import { NotificationsPanel } from "./NotificationsPanel";
import { NOTIFICATION_MARK_ERROR, type NotificationItem } from "@/hooks/useNotifications";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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
  created_at: new Date().toISOString(),
  ...over,
});

describe("NotificationsPanel — markError (G098)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;

  beforeEach(() => {
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

  function render(props: Partial<Parameters<typeof NotificationsPanel>[0]> = {}) {
    const tam = {
      items: [bildirim({ id: 1 }), bildirim({ id: 2 })],
      isLoading: false,
      error: null as string | null,
      unreadCount: 2,
      onSelect: vi.fn(),
      onMarkAllRead: vi.fn(),
      onRetry: vi.fn(),
      ...props,
    };
    root = createRoot(container);
    act(() => {
      root!.render(<NotificationsPanel {...tam} />);
    });
    return tam;
  }

  const hatalar = () => Array.from(container.querySelectorAll("[data-testid='mark-error']"));

  it("markError verilmezse hiç hata çizilmez", () => {
    render();
    expect(hatalar()).toHaveLength(0);
  });

  it("id'li markError yalnız o satırın içinde çizilir", () => {
    render({ markError: { id: 2, message: NOTIFICATION_MARK_ERROR } });

    expect(hatalar()).toHaveLength(1);
    const satir = hatalar()[0].closest("li")!;
    expect(satir).not.toBeNull();
    expect(satir.textContent).toContain("Belge arşive yüklendi");
    // Diğer satırda yok:
    const satirlar = Array.from(container.querySelectorAll("li"));
    expect(satirlar[0].querySelector("[data-testid='mark-error']")).toBeNull();
    expect(satirlar[1].querySelector("[data-testid='mark-error']")).not.toBeNull();
  });

  it("id=null markError başlık altında çizilir, satırlarda değil", () => {
    render({ markError: { id: null, message: NOTIFICATION_MARK_ERROR } });

    expect(hatalar()).toHaveLength(1);
    expect(hatalar()[0].closest("li")).toBeNull();
    expect(hatalar()[0].textContent).toContain(NOTIFICATION_MARK_ERROR);
  });

  it("liste hatası (error) varken satırlar çizilmez; markError liste hatasını gölgelemez", () => {
    render({
      error: "Bildirimler alınamadı — sunucuya ulaşılamadı.",
      markError: { id: 1, message: NOTIFICATION_MARK_ERROR },
    });

    expect(container.querySelector("li")).toBeNull();
    expect(container.textContent).toContain("Bildirimler alınamadı");
  });

  it("satırdaki hata, satıra tıklamayı engellemez (tekrar deneme yolu açık)", () => {
    const tam = render({ markError: { id: 1, message: NOTIFICATION_MARK_ERROR } });
    const buton = container.querySelector<HTMLButtonElement>("li button")!;
    act(() => {
      buton.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(tam.onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
  });
});
