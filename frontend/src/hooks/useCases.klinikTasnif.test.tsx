// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));

import { useCases } from "./useCases";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type CasesApi = ReturnType<typeof useCases>;

/** Hook'u gerçek bir render ağacında kurup dışa verdiği fonksiyonları yakalar. */
function mountUseCases(container: HTMLDivElement): { root: Root; api: () => CasesApi } {
  let captured: CasesApi | null = null;
  const Harness = () => {
    captured = useCases();
    return null;
  };
  const root = createRoot(container);
  act(() => root.render(<Harness />));
  return { root, api: () => captured! };
}

const jsonResponse = (body: unknown, init: { ok?: boolean; totalCount?: string } = {}) => ({
  ok: init.ok ?? true,
  json: async () => body,
  headers: { get: (k: string) => (k === "X-Total-Count" ? init.totalCount ?? null : null) },
}) as unknown as Response;

/**
 * 02.10 — klinik tasnif liste filtreleri: `tibbi_surec` / `tibbi_olay` param'ları,
 * değer havuz öğesinin ADI; "Tümü" (ALL) ya da verilmeyince param GÖNDERİLMEZ.
 */
describe("useCases — tibbi_surec / tibbi_olay filtreleri", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let api: () => CasesApi;

  beforeEach(() => {
    vi.clearAllMocks();
    container = document.createElement("div");
    document.body.appendChild(container);
    const mounted = mountUseCases(container);
    root = mounted.root;
    api = mounted.api;
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
  });

  it("seçimler liste isteğine ad olarak eklenir", async () => {
    authRequestMock.mockResolvedValue(jsonResponse([], { totalCount: "0" }));

    await act(async () => {
      await api().getCases({ limit: 15, tibbiSurec: "Doğum Yönetimi", tibbiOlay: "Omuz Distosisi" });
    });

    const params = new URLSearchParams(String(authRequestMock.mock.calls[0][0]).split("?")[1] ?? "");
    expect(params.get("tibbi_surec")).toBe("Doğum Yönetimi");
    expect(params.get("tibbi_olay")).toBe("Omuz Distosisi");
    expect(params.get("limit")).toBe("15");
  });

  it("'Tümü' (ALL) ve verilmeyince param GÖNDERİLMEZ", async () => {
    authRequestMock.mockResolvedValue(jsonResponse([], { totalCount: "0" }));

    await act(async () => {
      await api().getCases({ tibbiSurec: "ALL", tibbiOlay: "ALL" });
      await api().getCases({});
    });

    for (const call of authRequestMock.mock.calls) {
      expect(String(call[0])).not.toContain("tibbi_");
    }
  });
});
