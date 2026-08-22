// @vitest-environment jsdom
// G100 — Yetki Belgesi yazdırma popup'ı CSP uyumlu: popup'a yazılan HTML'de
// inline <script> YOK, window.print() AÇANDAN tetiklenir (readyState
// "complete" ise hemen, değilse load olayında). Popup engellenince toast aynen.
// Adım 1-2-3 gerçek bileşen akışıyla geçilir; Radix Dialog/Popover/cmdk
// yalnız jsdom'da gereksiz olan portal/odak katmanı için düzleştirilir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const LAWYERS = vi.hoisted(() => [
  { name: "Deniz Kaya", tc_no: "12345678901", sicil_no: "4567", address: "Büro Cad. No:1 Kadıköy" },
  { name: "Ali Vural", tc_no: "", sicil_no: "", address: "" },
]);
vi.mock("@/hooks/useConfig", () => ({ useConfig: () => ({ lawyers: LAWYERS }) }));

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({ useAuthRequest: () => ({ authRequest: authRequestMock }) }));

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));

type Kids = { children?: unknown };

// vi.mock fabrikaları dosya başına kaldırılır: paylaşılan üst-düzey değişken
// kullanılamaz, düz sarmalayıcı her fabrikada yerinde tanımlanır.
vi.mock("@/components/ui/dialog", () => {
  const duz = ({ children }: Kids) => <div>{children as never}</div>;
  return {
    Dialog: ({ open, children }: { open: boolean } & Kids) => (open ? <>{children as never}</> : null),
    DialogContent: duz,
    DialogHeader: duz,
    DialogTitle: duz,
    DialogDescription: duz,
  };
});
// Popover: içerik daima basılır (açık/kapalı durumu testin konusu değil).
vi.mock("@/components/ui/popover", () => ({
  Popover: ({ children }: Kids) => <>{children as never}</>,
  PopoverTrigger: ({ children }: Kids) => <>{children as never}</>,
  PopoverContent: ({ children }: Kids) => <div>{children as never}</div>,
}));
// cmdk: CommandItem → onSelect'i tıklamaya bağlı düz buton.
vi.mock("@/components/ui/command", () => {
  const duz = ({ children }: Kids) => <div>{children as never}</div>;
  return {
    Command: duz,
    CommandInput: () => null,
    CommandList: duz,
    CommandEmpty: duz,
    CommandGroup: duz,
    CommandItem: ({ children, onSelect, value }: Kids & { onSelect?: () => void; value?: string }) => (
      <button type="button" data-cmd-item={value} onClick={onSelect}>{children as never}</button>
    ),
  };
});

import { YetkiBelgesiModal } from "./YetkiBelgesiModal";
import type { Client } from "@/pages/ClientList";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const MUVEKKIL: Client = {
  id: 7,
  name: "Ayşe Yılmaz",
  tc_no: "98765432109",
  address: "Bağdat Cad. No:5",
  il: "İstanbul",
  noterlik: "Kadıköy 3. Noterliği",
  vekaletname_tarihi: "2025-01-27",
  yevmiye_no: "1234",
};

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

describe("YetkiBelgesiModal — yazdırma popup'ı CSP uyumlu (G100)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  const ozgunOpen = window.open;

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
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

  /** Popover'lar düzleştirildiği için iki liste de DOM'da: veren listesi önce, "Avukat Ekle" listesi sonra. */
  function cmdItem(value: string, liste: "veren" | "yetkili"): HTMLButtonElement {
    const hepsi = Array.from(container.querySelectorAll<HTMLButtonElement>(`button[data-cmd-item="${value}"]`));
    const b = liste === "veren" ? hepsi[0] : hepsi[hepsi.length - 1];
    if (!b || (liste === "yetkili" && hepsi.length < 2)) throw new Error(`'${value}' seçeneği (${liste}) bulunamadı`);
    return b;
  }

  /** Adım 1 (avukat seçimi) → Adım 2 (Deniz Kaya'nın TC/sicil'i config'den dolu) → Adım 3 → Yazdır. */
  async function adim3eGitVeYazdir() {
    root = createRoot(container);
    await act(async () => {
      root!.render(<YetkiBelgesiModal open onClose={() => {}} client={MUVEKKIL} />);
    });
    await act(async () => { cmdItem("Deniz Kaya", "veren").click(); });
    await act(async () => { cmdItem("Ali Vural", "yetkili").click(); });
    expect(container.textContent).toContain("(1 seçili)");
    expect(buton("Devam").disabled).toBe(false);
    await act(async () => { buton("Devam").click(); });          // → adım 2
    expect(container.textContent).toContain("Veren Avukat · Detayları");
    expect(buton("Devam").disabled).toBe(false);                 // TC 11 hane + sicil config'den
    await act(async () => { buton("Devam").click(); });          // → adım 3
    expect(container.textContent).toContain("YETKİ BELGESİ VEREN AVUKAT");
    await act(async () => { buton("Yazdır").click(); });
  }

  it("popup'a yazılan HTML'de <script ve onload= YOK; printRef içeriği aynen gidiyor", async () => {
    const { popup, yazilanHtml } = popupKur("complete");
    window.open = vi.fn(() => popup as unknown as Window);

    await adim3eGitVeYazdir();

    expect(popup.document.write).toHaveBeenCalledTimes(1);
    const html = yazilanHtml();
    expect(html).not.toMatch(/<script/i);
    expect(html).not.toMatch(/onload=/i);
    // İçerik değişmedi: stil bloğu (.yb-title kuralı) + printRef'teki belge metni.
    expect(html).toContain("<style>");
    expect(html).toContain(".yb-title");
    expect(html).toContain("YETKİ BELGESİ");
    expect(html).toContain("Av. DENİZ KAYA");
    expect(html).toContain("Av. ALİ VURAL");
    expect(html).toContain("AYŞE YILMAZ");
    expect(html).toContain("T.C. Kimlik No: 12345678901");
    expect(html).toContain("4667 Sayılı Kanunun 36. maddesi");
    expect(popup.document.close).toHaveBeenCalledTimes(1);
  });

  it("readyState 'complete' ise print() açandan HEMEN çağrılır", async () => {
    const { popup } = popupKur("complete");
    window.open = vi.fn(() => popup as unknown as Window);

    await adim3eGitVeYazdir();

    expect(popup.print).toHaveBeenCalledTimes(1);
    expect(popup.addEventListener).not.toHaveBeenCalled();
  });

  it("readyState 'loading' ise print() load olayını bekler, load'da bir kez çağrılır", async () => {
    const { popup, loadAtesle } = popupKur("loading");
    window.open = vi.fn(() => popup as unknown as Window);

    await adim3eGitVeYazdir();

    expect(popup.print).not.toHaveBeenCalled();
    expect(popup.addEventListener).toHaveBeenCalledWith("load", expect.any(Function), { once: true });
    loadAtesle();
    expect(popup.print).toHaveBeenCalledTimes(1);
  });

  it("popup engellenince (window.open null) toast hatası AYNEN", async () => {
    window.open = vi.fn(() => null);

    await adim3eGitVeYazdir();

    expect(toastMock.error).toHaveBeenCalledWith(
      "Yazdırma penceresi açılamadı. Tarayıcınızın bu site için pop-up engelleyiciyi devre dışı bırakın.",
    );
  });
});
