// @vitest-environment jsdom
// G100 — Takvim raporu yazdırma popup'ı CSP uyumlu: popup'a yazılan HTML'de
// inline handler/script YOK, window.print() AÇANDAN tetiklenir (readyState
// "complete" ise hemen, değilse load olayında). Popup engellenince toast aynen.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: apiFetchMock } }));

const navigateMock = vi.hoisted(() => vi.fn());
vi.mock("react-router", () => ({ useNavigate: () => navigateMock }));

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));

// Radix Dialog portal/odak makinesi jsdom'da gereksiz: açıkken çocuklarını basan
// düz sarmalayıcı yeter (test edilen şey yazdırma tetiği, diyalog değil).
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: { open: boolean; children?: unknown }) => (open ? <>{children as never}</> : null),
  DialogContent: ({ children }: { children?: unknown }) => <div>{children as never}</div>,
  DialogHeader: ({ children }: { children?: unknown }) => <div>{children as never}</div>,
  DialogTitle: ({ children }: { children?: unknown }) => <div>{children as never}</div>,
}));

import { DashboardCalendar } from "./DashboardCalendar";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function jsonOk(payload: unknown) {
  return { ok: true, status: 200, json: async () => payload };
}

const SATIRLAR = [
  {
    date_str: "03.08.2026", time: "10:30", type: "Duruşma", title: "Ön inceleme",
    esas_no: "2026/123", court: "İstanbul 5. Asliye Hukuk", client: "Ayşe Yılmaz",
    counter: "X Sigorta A.Ş.", lawyer: "Av. Deniz Kaya", case_id: 42,
  },
];

/** window.open mock'u: readyState parametrik, print/addEventListener casuslu popup. */
function popupKur(readyState: "complete" | "loading") {
  const listeners: Record<string, Array<() => void>> = {};
  let yazilan = "";
  const popup = {
    document: {
      readyState,
      open: vi.fn(),
      write: vi.fn((html: string) => { yazilan += html; }),
      close: vi.fn(),
    },
    print: vi.fn(),
    addEventListener: vi.fn((tip: string, cb: () => void) => {
      (listeners[tip] ||= []).push(cb);
    }),
  };
  return {
    popup,
    yazilanHtml: () => yazilan,
    loadAtesle: () => { (listeners.load || []).forEach((cb) => cb()); },
  };
}

describe("DashboardCalendar — yazdırma popup'ı CSP uyumlu (G100)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  const ozgunOpen = window.open;

  beforeEach(() => {
    vi.clearAllMocks();
    apiFetchMock.mockImplementation(async (url: string) => {
      if (url.startsWith("/api/calendar-report")) return jsonOk({ rows: SATIRLAR });
      return jsonOk([]);
    });
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    window.open = ozgunOpen;
  });

  function buton(metin: string): HTMLButtonElement {
    const b = Array.from(container.querySelectorAll("button"))
      .find((x) => x.textContent?.trim() === metin);
    if (!b) throw new Error(`'${metin}' butonu bulunamadı`);
    return b;
  }

  async function raporuAcVeYazdir() {
    root = createRoot(container);
    await act(async () => { root!.render(<DashboardCalendar />); });
    await act(async () => { buton("Rapor").click(); });
    // Önizleme fetch'i çözülsün (Yazdır butonu previewLoading'de kapalı).
    await act(async () => { await Promise.resolve(); });
    const yazdir = buton("Yazdır");
    expect(yazdir.disabled).toBe(false);
    await act(async () => { yazdir.click(); });
  }

  it("popup'a yazılan HTML'de <script ve onload= YOK; tablo gövdesi aynen gidiyor", async () => {
    const { popup, yazilanHtml } = popupKur("complete");
    window.open = vi.fn(() => popup as unknown as Window);

    await raporuAcVeYazdir();

    expect(popup.document.write).toHaveBeenCalledTimes(1);
    const html = yazilanHtml();
    expect(html).not.toMatch(/<script/i);
    expect(html).not.toMatch(/onload=/i);
    // İçerik değişmedi: tablo + satır verisi + stil bloğu popup'ta.
    expect(html).toContain("<table");
    expect(html).toContain("<style>");
    expect(html).toContain("Takvim Raporu");
    expect(html).toContain("Ön inceleme");
    expect(html).toContain("2026/123");
    expect(html).toContain("1 kayıt");
    expect(popup.document.close).toHaveBeenCalledTimes(1);
  });

  it("readyState 'complete' ise print() açandan HEMEN çağrılır", async () => {
    const { popup } = popupKur("complete");
    window.open = vi.fn(() => popup as unknown as Window);

    await raporuAcVeYazdir();

    expect(popup.print).toHaveBeenCalledTimes(1);
    expect(popup.addEventListener).not.toHaveBeenCalled();
  });

  it("readyState 'loading' ise print() load olayını bekler, load'da bir kez çağrılır", async () => {
    const { popup, loadAtesle } = popupKur("loading");
    window.open = vi.fn(() => popup as unknown as Window);

    await raporuAcVeYazdir();

    expect(popup.print).not.toHaveBeenCalled();
    expect(popup.addEventListener).toHaveBeenCalledWith("load", expect.any(Function), { once: true });
    loadAtesle();
    expect(popup.print).toHaveBeenCalledTimes(1);
  });

  it("popup engellenince (window.open null) toast hatası AYNEN, yazma yok", async () => {
    window.open = vi.fn(() => null);

    await raporuAcVeYazdir();

    expect(toastMock.error).toHaveBeenCalledWith(
      "Yazdırma penceresi açılamadı (açılır pencere engelleyiciyi kontrol edin).",
    );
  });
});
