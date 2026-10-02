// @vitest-environment jsdom
// G252: HizmetSecici — hizmet türü çoklu seçicisi. Gerçek Radix Popover + cmdk (düzleştirilmez);
// seçenek kaynağı `useConfigList("serviceTypes")` sahte. Kilitlenenler: liste sırası, çoklu seçim
// listeyi açık tutar, yayılan değer liste sırasında, kilitli ad işaretli + değişmez ve değere
// girmez, kapalıyken çip / yer tutucu, liste dışı değer seçenek olarak sunulmaz, erişilebilir etiket.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

const configMock = vi.hoisted(() => ({
  serviceTypes: [] as { code?: string; name: string }[],
  error: undefined as string | undefined,
  keys: [] as string[],
}));
vi.mock("@/hooks/useConfig", () => ({
  useConfigList: (key: string) => {
    configMock.keys.push(key);
    return { data: configMock.serviceTypes, isLoading: false, isError: Boolean(configMock.error), error: configMock.error };
  },
}));

import { HizmetSecici } from "./HizmetSecici";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
Element.prototype.scrollIntoView = function () { /* jsdom */ };
const globalWithRO = globalThis as { ResizeObserver?: unknown };
if (!globalWithRO.ResizeObserver) {
  globalWithRO.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Liste sırası (sequence) bilinçli olarak alfabetik DEĞİL.
const SERVICE_TYPES = [
  { code: "TD", name: "Takip (doktor müvekkil)" },
  { code: "DN", name: "Danışmanlık" },
  { code: "LR", name: "Lexis Rapor" },
  { code: "TH", name: "Takip (hasta vekilliği)" },
];

describe("HizmetSecici", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    configMock.serviceTypes = SERVICE_TYPES;
    configMock.error = undefined;
    configMock.keys = [];
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    document.body.innerHTML = "";
  });

  const trigger = () => container.querySelector<HTMLButtonElement>("[role=combobox]")!;
  const searchInput = () => document.body.querySelector<HTMLInputElement>("[cmdk-input]");
  const items = () => Array.from(document.body.querySelectorAll<HTMLElement>("[cmdk-item]"));
  const item = (ad: string) => items().find(el => el.getAttribute("data-hizmet") === ad) ?? null;
  const chips = () => Array.from(container.querySelectorAll<HTMLElement>("[data-testid=hizmet-secici-cip]"));

  function open() {
    act(() => {
      trigger().dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, pointerType: "mouse" }));
      trigger().click();
    });
    expect(searchInput()).not.toBeNull();
  }

  function type(text: string) {
    const input = searchInput()!;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    act(() => {
      setter.call(input, text);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  function key(k: string) {
    act(() => {
      searchInput()!.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
    });
  }

  function Sarmal({
    initial = [] as string[], kilitli, onValue, disabled, defaultOpen,
  }: {
    initial?: string[]; kilitli?: string[]; onValue?: (v: string[]) => void; disabled?: boolean; defaultOpen?: boolean;
  }) {
    const [v, setV] = useState<string[]>(initial);
    return (
      <HizmetSecici
        value={v}
        onChange={n => { setV(n); onValue?.(n); }}
        kilitli={kilitli}
        disabled={disabled}
        defaultOpen={defaultOpen}
        aria-label="Dr. Ayşe Kaya için hizmetler"
      />
    );
  }

  it("seçenekler serviceTypes listesinden, LİSTE SIRASIYLA gelir", () => {
    act(() => root.render(<Sarmal />));
    expect(configMock.keys).toContain("serviceTypes");
    expect(new Set(configMock.keys)).toEqual(new Set(["serviceTypes"]));
    open();
    expect(items().map(el => el.getAttribute("data-hizmet"))).toEqual(SERVICE_TYPES.map(s => s.name));
    expect(items().every(el => el.getAttribute("data-checked") === "false")).toBe(true);
  });

  it("erişilebilir etiket tetikleyicide; hiç seçim yokken yer tutucu görünür", () => {
    act(() => root.render(<Sarmal />));
    expect(trigger().getAttribute("aria-label")).toBe("Dr. Ayşe Kaya için hizmetler");
    expect(trigger().getAttribute("aria-expanded")).toBe("false");
    expect(container.querySelector("[data-testid=hizmet-secici-yer-tutucu]")?.textContent).toBe("Hizmet seçin…");
    expect(chips()).toHaveLength(0);
  });

  it("çoklu seçim: iki hizmet işaretlenir, liste açık kalır, değer liste sırasında yayılır", () => {
    const onValue = vi.fn();
    act(() => root.render(<Sarmal onValue={onValue} />));
    open();
    // Önce listede SONRA gelen, ardından önce gelen seçilir → yayılan değer liste sırasında.
    act(() => item("Lexis Rapor")!.click());
    expect(onValue).toHaveBeenLastCalledWith(["Lexis Rapor"]);
    expect(searchInput()).not.toBeNull();
    act(() => item("Takip (doktor müvekkil)")!.click());
    expect(onValue).toHaveBeenLastCalledWith(["Takip (doktor müvekkil)", "Lexis Rapor"]);
    expect(searchInput()).not.toBeNull();
    expect(item("Lexis Rapor")!.getAttribute("data-checked")).toBe("true");
    expect(item("Danışmanlık")!.getAttribute("data-checked")).toBe("false");
    // Kapalıyken de görünen çipler (tetikleyicide), liste sırasıyla.
    expect(chips().map(c => c.textContent)).toEqual(["Takip (doktor müvekkil)", "Lexis Rapor"]);
  });

  it("işaretli hizmete tekrar tıklamak seçimi kaldırır", () => {
    const onValue = vi.fn();
    act(() => root.render(<Sarmal initial={["Danışmanlık", "Lexis Rapor"]} onValue={onValue} />));
    open();
    act(() => item("Danışmanlık")!.click());
    expect(onValue).toHaveBeenLastCalledWith(["Lexis Rapor"]);
    expect(chips().map(c => c.textContent)).toEqual(["Lexis Rapor"]);
  });

  it("kilitli ad işaretli + devre dışı görünür, tıklanınca değişmez ve değere GİRMEZ", () => {
    const onValue = vi.fn();
    act(() => root.render(<Sarmal kilitli={["Danışmanlık"]} onValue={onValue} />));
    // Kapalıyken kilitli ad çip olarak görünür (kilitli işaretli).
    expect(chips().map(c => [c.textContent, c.getAttribute("data-kilitli")])).toEqual([["Danışmanlık", "true"]]);
    open();
    const kilitli = item("Danışmanlık")!;
    expect(kilitli.getAttribute("data-checked")).toBe("true");
    expect(kilitli.getAttribute("data-kilitli")).toBe("true");
    expect(kilitli.getAttribute("aria-disabled")).toBe("true");
    expect(kilitli.textContent).toContain("paket");
    act(() => kilitli.click());
    expect(onValue).not.toHaveBeenCalled();
    // Başka bir hizmet seçilince yayılan değerde kilitli ad YOK.
    act(() => item("Lexis Rapor")!.click());
    expect(onValue).toHaveBeenLastCalledWith(["Lexis Rapor"]);
  });

  it("value içinde kilitli ad gelse bile yayılan değere girmez", () => {
    const onValue = vi.fn();
    act(() => root.render(<Sarmal initial={["Danışmanlık"]} kilitli={["Danışmanlık"]} onValue={onValue} />));
    open();
    act(() => item("Takip (hasta vekilliği)")!.click());
    expect(onValue).toHaveBeenLastCalledWith(["Takip (hasta vekilliği)"]);
  });

  it("arama Türkçe katlamalı ve büyük/küçük harf duyarsız", () => {
    act(() => root.render(<Sarmal />));
    open();
    type("DANISMAN");
    expect(items().map(el => el.getAttribute("data-hizmet"))).toEqual(["Danışmanlık"]);
    type("zzz");
    expect(items()).toHaveLength(0);
    expect(document.body.querySelector("[data-testid=hizmet-secici-bos]")?.textContent).toBe("Hizmet bulunamadı");
  });

  it("klavye: ↓ ile gezilir, Enter işaretler, Esc kapatır", () => {
    const onValue = vi.fn();
    act(() => root.render(<Sarmal onValue={onValue} />));
    open();
    key("ArrowDown");
    key("Enter");
    expect(onValue).toHaveBeenCalledTimes(1);
    expect(onValue.mock.calls[0][0]).toHaveLength(1);
    expect(SERVICE_TYPES.map(s => s.name)).toContain(onValue.mock.calls[0][0][0]);
    act(() => {
      searchInput()!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    expect(searchInput()).toBeNull();
  });

  it("liste dışı seçili değer çipte damgalı durur, seçenek olarak sunulmaz; yalnız kaldırılabilir", () => {
    const onValue = vi.fn();
    act(() => root.render(<Sarmal initial={["Eski Hizmet", "Lexis Rapor"]} onValue={onValue} />));
    const eski = chips().find(c => c.textContent === "Eski Hizmet")!;
    expect(eski.getAttribute("data-liste-disi")).toBe("true");
    expect(chips().find(c => c.textContent === "Lexis Rapor")!.getAttribute("data-liste-disi")).toBe("false");
    open();
    const satir = item("Eski Hizmet")!;
    expect(satir.getAttribute("data-liste-disi")).toBe("true");
    expect(satir.textContent).toContain("liste dışı");
    act(() => satir.click());
    expect(onValue).toHaveBeenLastCalledWith(["Lexis Rapor"]);
    // Kaldırılınca listeden de düşer — yeniden seçilemez.
    expect(item("Eski Hizmet")).toBeNull();
    expect(items().map(el => el.getAttribute("data-hizmet"))).toEqual(SERVICE_TYPES.map(s => s.name));
  });

  it("disabled: tetikleyici devre dışı, liste açılmaz", () => {
    act(() => root.render(<Sarmal disabled defaultOpen />));
    expect(trigger().disabled).toBe(true);
    expect(searchInput()).toBeNull();
    act(() => trigger().click());
    expect(searchInput()).toBeNull();
  });

  it("defaultOpen: ilk çizimde liste açık gelir", () => {
    act(() => root.render(<Sarmal defaultOpen />));
    expect(searchInput()).not.toBeNull();
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
  });

  it("liste alınamadıysa hata metni, liste boşsa bilgi metni görünür", () => {
    configMock.serviceTypes = [];
    configMock.error = "Ayar listeleri alınamadı — sunucuya ulaşılamadı.";
    act(() => root.render(<Sarmal defaultOpen />));
    expect(document.body.querySelector("[data-testid=hizmet-secici-bos]")?.textContent)
      .toBe("Ayar listeleri alınamadı — sunucuya ulaşılamadı.");
    act(() => root.unmount());
    configMock.error = undefined;
    root = createRoot(container);
    act(() => root.render(<Sarmal defaultOpen />));
    expect(document.body.querySelector("[data-testid=hizmet-secici-bos]")?.textContent).toBe("Hizmet türü listesi boş");
  });
});
