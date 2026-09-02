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
 * G105 — Olay Türü liste filtresi. Sözleşme (G103 ile ortak, dondurulmuş):
 * query param adı `olay_turu`, değeri listenin ADIdır (ör. "Belgeleme Olayı").
 * Sayfa bileşeni test kapsamı dışında (repo deseni: hooks testleri) — param
 * mekaniği hook seviyesinde doğrulanır, CaseList seçimi olduğu gibi geçirir.
 */
describe("useCases — G105 olay_turu filtresi", () => {
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

  it("seçim yapılınca liste isteğine olay_turu param'ı eklenir (değer = listenin ADI)", async () => {
    authRequestMock.mockResolvedValue(jsonResponse([], { totalCount: "0" }));

    await act(async () => {
      await api().getCases({ limit: 15, olayTuru: "Belgeleme Olayı" });
    });

    expect(authRequestMock).toHaveBeenCalledTimes(1);
    const url = String(authRequestMock.mock.calls[0][0]);
    const params = new URLSearchParams(url.split("?")[1] ?? "");
    expect(params.get("olay_turu")).toBe("Belgeleme Olayı");
    // Diğer parametreler bozulmaz
    expect(params.get("limit")).toBe("15");
  });

  it("'Tümü' (ALL) seçiliyken ve hiç verilmediğinde olay_turu param'ı GÖNDERİLMEZ", async () => {
    authRequestMock.mockResolvedValue(jsonResponse([], { totalCount: "0" }));

    await act(async () => {
      await api().getCases({ olayTuru: "ALL" });
      await api().getCases({});
    });

    expect(authRequestMock).toHaveBeenCalledTimes(2);
    for (const call of authRequestMock.mock.calls) {
      expect(String(call[0])).not.toContain("olay_turu");
    }
  });
});
