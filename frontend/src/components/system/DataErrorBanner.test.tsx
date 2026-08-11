// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { DataErrorBanner } from "./DataErrorBanner";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("DataErrorBanner (G002)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
  });

  it("kesinti mesajını ve 'kayıtlarınız silinmedi' güvencesini gösterir", () => {
    act(() => root!.render(<DataErrorBanner description="Dava listesi alınamadı." />));

    expect(container.querySelector("[role='alert']")).not.toBeNull();
    expect(container.textContent).toContain("Sunucuya ulaşılamadı");
    expect(container.textContent).toContain("Dava listesi alınamadı.");
    expect(container.textContent).toContain("kayıtlarınız silinmedi");
  });

  it("onRetry verilmezse tekrar dene butonu çıkmaz", () => {
    act(() => root!.render(<DataErrorBanner />));

    expect(container.querySelector("button")).toBeNull();
  });

  it("tekrar dene butonu onRetry'ı çağırır", () => {
    const onRetry = vi.fn();
    act(() => root!.render(<DataErrorBanner onRetry={onRetry} />));

    const button = container.querySelector("button");
    expect(button!.textContent).toContain("Tekrar dene");
    act(() => { button!.click(); });

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("tekrar denenirken buton kilitlenir", () => {
    act(() => root!.render(<DataErrorBanner onRetry={() => {}} isRetrying />));

    expect(container.querySelector("button")!.disabled).toBe(true);
  });
});
