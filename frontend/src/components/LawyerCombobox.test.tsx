// @vitest-environment jsdom
// G213: LawyerCombobox — yazarak aranan avukat seçimi. Gerçek Radix Popover + cmdk
// (düzleştirilmez): Türkçe katlamalı arama, gorev rozeti (İç/Dış), tekli/çoklu seçim,
// çipten çıkarma, klavye (↓/Enter/Esc) ve "Avukat bulunamadı" boş durumu.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

import { LawyerCombobox, type LawyerOption } from "./LawyerCombobox";

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

const LAWYERS: LawyerOption[] = [
  { name: "Av. Ayşe Gül Hanyaloğlu", gorev: "AVUKAT" },
  { name: "Av. İsmail Şahin", gorev: "DIŞ AVUKAT" },
  { name: "Av. Ömer Çağlar", gorev: "DİĞER" },
  { name: "Av. Zeynep Irmak", gorev: null },
];

describe("LawyerCombobox", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
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
  /** Görünür (süzgeçten geçen) satırların avukat adları. */
  const visibleNames = () =>
    Array.from(document.body.querySelectorAll<HTMLElement>("[cmdk-item]")).map(el => el.getAttribute("data-lawyer"));
  const item = (name: string) => document.body.querySelector<HTMLElement>(`[cmdk-item][data-lawyer="${name}"]`);
  const chips = () => Array.from(container.querySelectorAll("[data-testid=lawyer-chip]")).map(c => c.textContent);

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

  function Single({ initial = "", onValue }: { initial?: string; onValue?: (v: string) => void }) {
    const [v, setV] = useState(initial);
    return <LawyerCombobox mode="single" lawyers={LAWYERS} value={v} onChange={n => { setV(n); onValue?.(n); }} placeholder="Seçiniz..." />;
  }

  function Multi({ initial = [] as string[], onValue }: { initial?: string[]; onValue?: (v: string[]) => void }) {
    const [v, setV] = useState<string[]>(initial);
    return <LawyerCombobox mode="multi" lawyers={LAWYERS} value={v} onChange={n => { setV(n); onValue?.(n); }} />;
  }

  it("açınca tüm avukatlar gorev rozetleriyle listelenir (DİĞER/boş rozetsiz)", () => {
    act(() => root.render(<Single />));
    expect(trigger().textContent).toContain("Seçiniz...");
    open();
    expect(visibleNames()).toEqual(LAWYERS.map(l => l.name));
    const rozet = (name: string) => item(name)!.querySelector("[data-testid=lawyer-gorev-rozeti]")?.textContent ?? null;
    expect(rozet("Av. Ayşe Gül Hanyaloğlu")).toBe("İç");
    expect(rozet("Av. İsmail Şahin")).toBe("Dış");
    expect(rozet("Av. Ömer Çağlar")).toBeNull();
    expect(rozet("Av. Zeynep Irmak")).toBeNull();
  });

  it("arama Türkçe katlamalı: 'sahin' → Şahin, 'OMER' → Ömer, 'ırmak' → Irmak", () => {
    act(() => root.render(<Single />));
    open();
    type("sahin");
    expect(visibleNames()).toEqual(["Av. İsmail Şahin"]);
    type("OMER");
    expect(visibleNames()).toEqual(["Av. Ömer Çağlar"]);
    type("ırmak");
    expect(visibleNames()).toEqual(["Av. Zeynep Irmak"]);
  });

  it("arama: ğ/ş/ü/ç/İ katlaması, çok kelimeli alt-dize, boşluk-yalnız sorgu hepsini gösterir", () => {
    act(() => root.render(<Single />));
    open();
    type("hanyaloglu");
    expect(visibleNames()).toEqual(["Av. Ayşe Gül Hanyaloğlu"]);
    type("AYSE GUL");
    expect(visibleNames()).toEqual(["Av. Ayşe Gül Hanyaloğlu"]);
    type("ismail sahin");
    expect(visibleNames()).toEqual(["Av. İsmail Şahin"]);
    type("İSMAİL");
    expect(visibleNames()).toEqual(["Av. İsmail Şahin"]);
    type("cag");
    expect(visibleNames()).toEqual(["Av. Ömer Çağlar"]);
    type("   ");
    expect(visibleNames()).toEqual(LAWYERS.map(l => l.name));
  });

  it("rozet gorev yazımına dayanıklı: küçük harf / çift boşluk 'dış  avukat' → Dış, 'avukat' → İç", () => {
    const lw: LawyerOption[] = [
      { name: "Av. A", gorev: "avukat" },
      { name: "Av. B", gorev: "dış  avukat" },
      { name: "Av. C", gorev: "" },
    ];
    act(() => root.render(<LawyerCombobox mode="single" lawyers={lw} value="" onChange={() => undefined} />));
    open();
    const rozet = (name: string) => item(name)!.querySelector("[data-testid=lawyer-gorev-rozeti]")?.textContent ?? null;
    expect(rozet("Av. A")).toBe("İç");
    expect(rozet("Av. B")).toBe("Dış");
    expect(rozet("Av. C")).toBeNull();
  });

  it("sonuç yoksa 'Avukat bulunamadı' görünür", () => {
    act(() => root.render(<Single />));
    open();
    type("qqqq");
    expect(visibleNames()).toEqual([]);
    expect(document.body.textContent).toContain("Avukat bulunamadı");
  });

  it("tekli: tıklama değeri adla verir ve listeyi kapatır; seçili satır işaretli", () => {
    const got: string[] = [];
    act(() => root.render(<Single onValue={v => got.push(v)} />));
    open();
    act(() => item("Av. İsmail Şahin")!.click());
    expect(got).toEqual(["Av. İsmail Şahin"]);
    expect(trigger().textContent).toContain("Av. İsmail Şahin");
    expect(searchInput()).toBeNull();

    open();
    expect(item("Av. İsmail Şahin")!.getAttribute("data-checked")).toBe("true");
    expect(item("Av. Ömer Çağlar")!.getAttribute("data-checked")).toBe("false");
  });

  it("klavye: yaz + ↓ + Enter seçer, Esc kapatır", () => {
    const got: string[] = [];
    act(() => root.render(<Single onValue={v => got.push(v)} />));
    open();
    type("av.");
    key("ArrowDown");
    key("Enter");
    expect(got).toEqual(["Av. İsmail Şahin"]);
    expect(searchInput()).toBeNull();

    open();
    key("Escape");
    expect(searchInput()).toBeNull();
  });

  it("tekli: listede olmayan mevcut değer de gösterilir ve işaretlidir", () => {
    act(() => root.render(<Single initial="Av. Eski Kayıt" />));
    expect(trigger().textContent).toContain("Av. Eski Kayıt");
    open();
    expect(item("Av. Eski Kayıt")!.getAttribute("data-checked")).toBe("true");
  });

  it("çoklu: seçim çip olur, liste açık kalır, seçili işaretli; tekrar seçmek çıkarır", () => {
    const got: string[][] = [];
    act(() => root.render(<Multi onValue={v => got.push(v)} />));
    open();
    act(() => item("Av. Ayşe Gül Hanyaloğlu")!.click());
    act(() => item("Av. İsmail Şahin")!.click());
    expect(got[got.length - 1]).toEqual(["Av. Ayşe Gül Hanyaloğlu", "Av. İsmail Şahin"]);
    expect(chips()).toEqual(["Av. Ayşe Gül Hanyaloğlu", "Av. İsmail Şahin"]);
    expect(searchInput()).not.toBeNull();
    expect(item("Av. Ayşe Gül Hanyaloğlu")!.getAttribute("data-checked")).toBe("true");
    expect(item("Av. Ömer Çağlar")!.getAttribute("data-checked")).toBe("false");

    act(() => item("Av. Ayşe Gül Hanyaloğlu")!.click());
    expect(got[got.length - 1]).toEqual(["Av. İsmail Şahin"]);
    expect(chips()).toEqual(["Av. İsmail Şahin"]);
  });

  it("çoklu: çipteki × avukatı çıkarır", () => {
    const got: string[][] = [];
    act(() => root.render(<Multi initial={["Av. Ömer Çağlar", "Av. Zeynep Irmak"]} onValue={v => got.push(v)} />));
    expect(chips()).toEqual(["Av. Ömer Çağlar", "Av. Zeynep Irmak"]);
    const x = container.querySelector<HTMLButtonElement>('[aria-label="Av. Ömer Çağlar avukatını çıkar"]')!;
    act(() => x.click());
    expect(got).toEqual([["Av. Zeynep Irmak"]]);
    expect(chips()).toEqual(["Av. Zeynep Irmak"]);
  });

  it("disabled iken açılmaz", () => {
    act(() => root.render(<LawyerCombobox mode="single" lawyers={LAWYERS} value="" onChange={() => undefined} disabled />));
    expect(trigger().disabled).toBe(true);
    act(() => trigger().click());
    expect(searchInput()).toBeNull();
  });
});
