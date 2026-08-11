// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

// authRequest mock'lanır — G002 testleri "hata ≠ boş veri" sözleşmesini doğrular.
const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));

import { useCases, CASE_LIST_ERROR, CASE_SEQUENCE_ERROR } from "./useCases";

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

/** ok/hatalı yanıt üreticisi — headers yalnız X-Total-Count için okunur. */
const jsonResponse = (body: unknown, init: { ok?: boolean; totalCount?: string } = {}) => ({
  ok: init.ok ?? true,
  json: async () => body,
  headers: { get: (k: string) => (k === "X-Total-Count" ? init.totalCount ?? null : null) },
}) as unknown as Response;

describe("useCases — hata ≠ boş veri (G002)", () => {
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

  it("getCases başarılı yanıtta listeyi ve toplamı döndürür", async () => {
    authRequestMock.mockResolvedValue(jsonResponse([{ id: 1 }], { totalCount: "42" }));

    let result: { cases: unknown[]; total: number } | null = null;
    await act(async () => {
      result = await api().getCases();
    });

    expect(result!.cases).toHaveLength(1);
    expect(result!.total).toBe(42);
  });

  it("getCases hatada BOŞ LİSTE döndürmez, fırlatır", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({ detail: "bozuk" }, { ok: false }));

    await act(async () => {
      await expect(api().getCases()).rejects.toThrow(CASE_LIST_ERROR);
    });
  });

  it("getCases oturum/ağ yokluğunda (authRequest null) da fırlatır", async () => {
    authRequestMock.mockResolvedValue(null);

    await act(async () => {
      await expect(api().getCases()).rejects.toThrow(CASE_LIST_ERROR);
    });
  });

  it("getClientCaseSequence başarılı yanıtta sıra numarasını döndürür", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({ sequence: 7 }));

    let seq: number | null = null;
    await act(async () => {
      seq = await api().getClientCaseSequence("HANYALOĞLU ACAR", "H_ACAR________");
    });

    expect(seq).toBe(7);
  });

  it("getClientCaseSequence hatada sessizce 1 DÖNMEZ, fırlatır", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({}, { ok: false }));

    await act(async () => {
      await expect(api().getClientCaseSequence("BİR MÜVEKKİL")).rejects.toThrow(CASE_SEQUENCE_ERROR);
    });
  });

  it("getClientCaseSequence sequence alanı sayı değilse fırlatır", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({ sequence: null }));

    await act(async () => {
      await expect(api().getClientCaseSequence("BİR MÜVEKKİL")).rejects.toThrow(CASE_SEQUENCE_ERROR);
    });
  });

  it("getClientCaseSequence gövde JSON değilse fırlatır", async () => {
    authRequestMock.mockResolvedValue({
      ok: true,
      json: async () => { throw new SyntaxError("Unexpected token <"); },
      headers: { get: () => null },
    } as unknown as Response);

    await act(async () => {
      await expect(api().getClientCaseSequence("BİR MÜVEKKİL")).rejects.toThrow(CASE_SEQUENCE_ERROR);
    });
  });
});
