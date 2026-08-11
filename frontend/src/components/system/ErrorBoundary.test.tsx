// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { ErrorBoundary } from "./ErrorBoundary";

// Beacon mock'lanır — boundary'nin raporlama SÖZLEŞMESİ test edilir, ağ değil.
const reportMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/errorBeacon", () => ({ reportCaughtRenderError: reportMock }));

// React'in act() uyarılarını susturmak için test ortamı bayrağı.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function Bomb(): never {
  throw new Error("kasıtlı render patlaması");
}

describe("ErrorBoundary (Faz 4.4)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  // React DEV modu render hatasını window'a da dispatch eder — jsdom'un
  // "Uncaught" gürültüsünü kesmek için standart preventDefault dinleyicisi.
  const swallowWindowError = (event: ErrorEvent) => event.preventDefault();

  beforeEach(() => {
    vi.clearAllMocks();
    container = document.createElement("div");
    document.body.appendChild(container);
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    window.addEventListener("error", swallowWindowError);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    window.removeEventListener("error", swallowWindowError);
    consoleErrorSpy.mockRestore();
  });

  it("hatasız çocuğu aynen render eder", () => {
    root = createRoot(container);
    act(() => {
      root!.render(
        <ErrorBoundary>
          <span>sağlıklı içerik</span>
        </ErrorBoundary>,
      );
    });

    expect(container.textContent).toContain("sağlıklı içerik");
    expect(reportMock).not.toHaveBeenCalled();
  });

  it("render hatasında fallback + 'Sayfayı Yenile' butonu gösterir", () => {
    root = createRoot(container);
    act(() => {
      root!.render(
        <ErrorBoundary>
          <Bomb />
        </ErrorBoundary>,
      );
    });

    expect(container.textContent).toContain("Beklenmedik bir hata oluştu");
    const button = container.querySelector("button");
    expect(button).not.toBeNull();
    expect(button!.textContent).toContain("Sayfayı Yenile");
  });

  it("yakalanan hatayı componentStack ile beacon'a raporlar", () => {
    root = createRoot(container);
    act(() => {
      root!.render(
        <ErrorBoundary>
          <Bomb />
        </ErrorBoundary>,
      );
    });

    expect(reportMock).toHaveBeenCalledTimes(1);
    const [error, componentStack] = reportMock.mock.calls[0];
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe("kasıtlı render patlaması");
    expect(typeof componentStack).toBe("string");
    expect(componentStack as string).toContain("Bomb");
  });
});
