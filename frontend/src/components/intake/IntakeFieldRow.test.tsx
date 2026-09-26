// @vitest-environment jsdom
// G213 (denetim onarımı): intake "Sorumlu Avukat" / "UYAP Avukatı" alanları `widget: "select"`
// tanımlı olsa da IntakeReviewStep bunlara `renderEditor` ile LawyerCombobox verir. Bekçi:
// özel editör verilince düz Radix Select YERİNE o çizilir, etiket onu gösterir; Türkçe
// katlamalı arama ("sahin" → Şahin) satırın onChange'ine avukat ADI string'ini iletir.
// renderEditor verilmezse eski select editörü aynen durur.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

import { IntakeFieldRow } from "./IntakeFieldRow";
import { LawyerCombobox, type LawyerOption } from "@/components/LawyerCombobox";
import type { IntakeFieldDef, IntakeFieldState } from "@/lib/caseIntakeFields";

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
];

const DEF: IntakeFieldDef = {
  key: "responsible_lawyer_name",
  label: "Sorumlu Avukat",
  widget: "select",
  required: true,
  enabled: true,
};

const EMPTY: IntakeFieldState = { value: "", aiValue: "", approved: false, touched: false };

describe("IntakeFieldRow — renderEditor (G213)", () => {
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

  function Harness({ onValue }: { onValue: (v: string) => void }) {
    const [state, setState] = useState<IntakeFieldState>(EMPTY);
    const change = (value: string) => {
      setState(s => ({ ...s, value, touched: true, approved: true }));
      onValue(value);
    };
    return (
      <IntakeFieldRow
        def={DEF}
        state={state}
        options={LAWYERS.map(l => l.name)}
        onChange={change}
        onApprove={() => undefined}
        renderEditor={inputId => (
          <LawyerCombobox mode="single" id={inputId} lawyers={LAWYERS} value={state.value} onChange={change} />
        )}
      />
    );
  }

  it("özel editör düz select'in yerine çizilir; 'sahin' araması Şahin'i seçip adı iletir", () => {
    const onValue = vi.fn();
    act(() => root.render(<Harness onValue={onValue} />));

    const combobox = container.querySelector<HTMLButtonElement>("[data-testid=lawyer-combobox] [role=combobox]");
    expect(combobox).not.toBeNull();
    // Etiket combobox'ı gösterir; başka bir (Radix Select) tetikleyici yok.
    expect(combobox!.id).toBe("intake-field-responsible_lawyer_name");
    expect(container.querySelector("label")!.getAttribute("for")).toBe(combobox!.id);
    expect(container.querySelectorAll("[role=combobox]").length).toBe(1);

    act(() => {
      combobox!.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, pointerType: "mouse" }));
      combobox!.click();
    });
    const input = document.body.querySelector<HTMLInputElement>("[cmdk-input]")!;
    expect(input).not.toBeNull();
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    act(() => {
      setter.call(input, "sahin");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const visible = Array.from(document.body.querySelectorAll("[cmdk-item]")).map(el => el.getAttribute("data-lawyer"));
    expect(visible).toEqual(["Av. İsmail Şahin"]);

    act(() => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    });
    expect(onValue).toHaveBeenCalledWith("Av. İsmail Şahin");
    expect(combobox!.textContent).toContain("Av. İsmail Şahin");
  });

  it("renderEditor verilmezse select editörü değişmeden durur", () => {
    act(() => root.render(
      <IntakeFieldRow
        def={DEF}
        state={EMPTY}
        options={LAWYERS.map(l => l.name)}
        onChange={() => undefined}
        onApprove={() => undefined}
      />,
    ));
    expect(container.querySelector("[data-testid=lawyer-combobox]")).toBeNull();
    const trigger = container.querySelector("#intake-field-responsible_lawyer_name");
    expect(trigger).not.toBeNull();
    expect(trigger!.textContent).toContain("Seçiniz...");
  });
});
