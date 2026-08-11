// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

// authRequest mock'lanır — G002 testleri "hata ≠ boş veri" sözleşmesini doğrular.
const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));

import { useCases, CASE_LIST_ERROR, CASE_SEQUENCE_ERROR, CASE_DUPLICATE_CHECK_ERROR } from "./useCases";

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

  // --- G019: mükerrer dava kapısı ---

  it("checkDuplicateCase başarılı yanıtta eşleşmeleri döndürür", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({
      matches: [{ id: 1, tracking_no: "X", esas_no: "2024/1", status: "DERDEST", court_match: true }],
    }));

    let dups: unknown[] | null = null;
    await act(async () => {
      dups = await api().checkDuplicateCase("2024/1", "Ankara 1. Asliye Hukuk");
    });

    expect(dups!).toHaveLength(1);
  });

  it("checkDuplicateCase eşleşme yoksa boş liste döndürür (hata değil)", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({ matches: [] }));

    let dups: unknown[] | null = null;
    await act(async () => {
      dups = await api().checkDuplicateCase("2024/1");
    });

    expect(dups!).toEqual([]);
  });

  it("checkDuplicateCase hatada 'mükerrer yok' DEMEZ, fırlatır", async () => {
    // Backend eşi (G014) bu durumda 503 + {detail} döner.
    authRequestMock.mockResolvedValue(jsonResponse({ detail: "kontrol yapılamıyor" }, { ok: false }));

    await act(async () => {
      await expect(api().checkDuplicateCase("2024/1")).rejects.toThrow(CASE_DUPLICATE_CHECK_ERROR);
    });
  });

  it("checkDuplicateCase sözleşme dışı gövdede de fırlatır", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({}));

    await act(async () => {
      await expect(api().checkDuplicateCase("2024/1")).rejects.toThrow(CASE_DUPLICATE_CHECK_ERROR);
    });
  });

  it("checkDuplicateCase esas no boşsa uca hiç gitmez", async () => {
    let dups: unknown[] | null = null;
    await act(async () => {
      dups = await api().checkDuplicateCase("   ");
    });

    expect(dups!).toEqual([]);
    expect(authRequestMock).not.toHaveBeenCalled();
  });

  /**
   * Tüketici deseninin (NewCase.tsx / QuickCaseModal.tsx handleSubmit) kapı
   * davranışı: kontrol fırlarsa kayıt POST'una HİÇ ulaşılmaz. Bileşenlerin
   * kendisi bu görevin test kapsamı dışında (yalnız hooks testleri), bu yüzden
   * desen hook seviyesinde doğrulanır.
   */
  it("kontrol fırlarsa kayıt POST'u hiç yapılmaz (tüketici kapısı)", async () => {
    authRequestMock.mockImplementation(async (url: string) =>
      url.includes("check-duplicate")
        ? jsonResponse({ detail: "kontrol yapılamıyor" }, { ok: false })
        : jsonResponse({ id: 1 }),
    );

    let saveAttempted = false;
    await act(async () => {
      try {
        await api().checkDuplicateCase("2024/1");
        saveAttempted = true;
        await api().saveCase({ tracking_no: "X", status: "DERDEST", parties: [] });
      } catch { /* kapı: tüketici burada toast basıp return eder */ }
    });

    expect(saveAttempted).toBe(false);
    expect(authRequestMock).not.toHaveBeenCalledWith("/api/cases", "POST", expect.anything());
  });
});
