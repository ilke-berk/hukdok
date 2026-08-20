// @vitest-environment jsdom
// NotificationsPanel — üç durum ayrı ayrı çizilir: dolu, boş, hata.
// Hatanın "bildiriminiz yok" gibi görünmesi G002 dersiyle yasak.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

// Hata metni sabitini hook modülünden okuyoruz; o modülün MSAL zinciri
// (useAuthRequest → api.ts → msalConfig) testte kurulmasın diye susturulur.
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: vi.fn() }),
}));

import { NotificationsPanel, NOTIFICATIONS_EMPTY_TEXT } from "./NotificationsPanel";
import { NOTIFICATION_LIST_ERROR, type NotificationItem } from "@/hooks/useNotifications";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const bildirim = (over: Partial<NotificationItem> = {}): NotificationItem => ({
  id: 1,
  type: "doc-processed",
  severity: "info",
  title: "Belge arşive yüklendi",
  body: "TEBLIGAT — Kadıköy 3. Asliye Hukuk",
  case_id: 42,
  document_id: 7,
  due_date: null,
  read_at: null,
  is_read: false,
  created_at: new Date().toISOString(),
  ...over,
});

describe("NotificationsPanel", () => {
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
      items: [] as NotificationItem[],
      isLoading: false,
      error: null as string | null,
      unreadCount: 0,
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

  const buton = (metin: string) =>
    Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.includes(metin),
    );

  it("dolu durum: satırlar başlık ve gövdeyle çizilir", () => {
    render({
      items: [
        bildirim({ id: 1, title: "Belge arşive yüklendi" }),
        bildirim({ id: 2, title: "Duruşma yaklaşıyor", body: "3 gün kaldı" }),
      ],
      unreadCount: 2,
    });

    expect(container.textContent).toContain("Belge arşive yüklendi");
    expect(container.textContent).toContain("Duruşma yaklaşıyor");
    expect(container.textContent).toContain("3 gün kaldı");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.textContent).not.toContain(NOTIFICATIONS_EMPTY_TEXT);
  });

  it("boş durum: 'bildiriminiz yok' yazar, hata şeridi ÇIKMAZ", () => {
    render({ items: [] });

    expect(container.textContent).toContain(NOTIFICATIONS_EMPTY_TEXT);
    expect(container.querySelector("[role='alert']")).toBeNull();
  });

  it("hata durumu: boş durumdan AYRI çizilir ve tekrar dene sunar", () => {
    const props = render({ items: [], error: NOTIFICATION_LIST_ERROR });

    expect(container.querySelector("[role='alert']")).not.toBeNull();
    expect(container.textContent).toContain(NOTIFICATION_LIST_ERROR);
    // Kritik: hata "bildiriminiz yok" gibi GÖRÜNMEMELİ.
    expect(container.textContent).not.toContain(NOTIFICATIONS_EMPTY_TEXT);

    act(() => {
      buton("Tekrar dene")!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(props.onRetry).toHaveBeenCalledTimes(1);
  });

  it("yükleniyor durumu boş listeyle karışmaz", () => {
    render({ items: [], isLoading: true });

    expect(container.textContent).toContain("Yükleniyor");
    expect(container.textContent).not.toContain(NOTIFICATIONS_EMPTY_TEXT);
  });

  it("satıra tıklayınca onSelect o bildirimle çağrılır", () => {
    const item = bildirim({ id: 77, title: "Belge arşive yüklendi" });
    const props = render({ items: [item], unreadCount: 1 });

    act(() => {
      buton("Belge arşive yüklendi")!.dispatchEvent(
        new MouseEvent("click", { bubbles: true }),
      );
    });

    expect(props.onSelect).toHaveBeenCalledWith(item);
  });

  it("'Tümünü okundu işaretle' okunmamış yokken kilitli, varken çalışır", () => {
    const bos = render({ items: [], unreadCount: 0 });
    expect(buton("Tümünü okundu işaretle")!.disabled).toBe(true);
    act(() => root!.unmount());
    root = null;

    const dolu = render({ items: [bildirim()], unreadCount: 1 });
    const b = buton("Tümünü okundu işaretle")!;
    expect(b.disabled).toBe(false);
    act(() => {
      b.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(dolu.onMarkAllRead).toHaveBeenCalledTimes(1);
    expect(bos.onMarkAllRead).not.toHaveBeenCalled();
  });
});
