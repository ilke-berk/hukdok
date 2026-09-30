// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

// authRequest mock'lanır — G002 testleri "hata ≠ boş veri" sözleşmesini doğrular.
const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));

import {
  useCases, useOfisNoOnizleme,
  CASE_LIST_ERROR, OFIS_NO_ONIZLEME_ERROR, CASE_DUPLICATE_CHECK_ERROR, OFIS_NO_ONIZLEME_DEBOUNCE_MS,
  type OfisNoOnizleme, type OfisNoOnizlemeDurumu,
} from "./useCases";

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

  // G237 (insan onaylı test taşıma): `getClientCaseSequence` (client-sequence ucu +
  // sıra numarası) kalktı — istemci numara kurmaz. Aynı dört "hata ≠ uydurma değer"
  // beklentisi önizleme ucuna (`getOfisNoOnizleme`) çevrildi.
  it("getOfisNoOnizleme başarılı yanıtta sunucunun önizlemesini döndürür", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({ onizleme: "AXA-3297-DR.E.ALTUNC-HUK", kod: "AXA" }));

    let onizleme: OfisNoOnizleme | null = null;
    await act(async () => {
      onizleme = await api().getOfisNoOnizleme("muvekkiller=41&file_type=Hukuk");
    });

    expect(onizleme!.onizleme).toBe("AXA-3297-DR.E.ALTUNC-HUK");
  });

  it("getOfisNoOnizleme hatada uydurma numara DÖNMEZ, fırlatır", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({}, { ok: false }));

    await act(async () => {
      await expect(api().getOfisNoOnizleme("muvekkiller=B%C4%B0R")).rejects.toThrow(OFIS_NO_ONIZLEME_ERROR);
    });
  });

  it("getOfisNoOnizleme onizleme alanı metin değilse fırlatır", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({ onizleme: null }));

    await act(async () => {
      await expect(api().getOfisNoOnizleme("muvekkiller=B%C4%B0R")).rejects.toThrow(OFIS_NO_ONIZLEME_ERROR);
    });
  });

  it("getOfisNoOnizleme gövde JSON değilse fırlatır", async () => {
    authRequestMock.mockResolvedValue({
      ok: true,
      json: async () => { throw new SyntaxError("Unexpected token <"); },
      headers: { get: () => null },
    } as unknown as Response);

    await act(async () => {
      await expect(api().getOfisNoOnizleme("muvekkiller=B%C4%B0R")).rejects.toThrow(OFIS_NO_ONIZLEME_ERROR);
    });
  });

  // --- G237: önizleme ucu + kayıt yanıtı ---

  it("getOfisNoOnizleme önizleme ucuna gider; eski client-sequence ucu çağrılmaz", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({ onizleme: "AXA-3297-DR.E.ALTUNC-HUK", sigortali_eksik: true }));

    let onizleme: OfisNoOnizleme | null = null;
    await act(async () => {
      onizleme = await api().getOfisNoOnizleme("muvekkiller=41&file_type=Hukuk");
    });

    expect(authRequestMock).toHaveBeenCalledTimes(1);
    expect(authRequestMock).toHaveBeenCalledWith("/api/cases/ofis-no-onizleme?muvekkiller=41&file_type=Hukuk", "GET");
    expect(authRequestMock.mock.calls.some(([url]) => String(url).includes("client-sequence"))).toBe(false);
    expect(onizleme!.sigortali_eksik).toBe(true);
    expect("getClientCaseSequence" in api()).toBe(false);
  });

  it("saveCase sunucunun verdiği numarayı ve kart kimliğini döndürür", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({ status: "success", id: 12, tracking_no: "AXA-3297-DR.E.ALTUNC-HUK" }));

    let result: Awaited<ReturnType<CasesApi["saveCase"]>> | null = null;
    await act(async () => {
      result = await api().saveCase({ status: "DERDEST", parties: [], istek_kimligi: "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a" });
    });

    expect(result).toEqual({ ok: true, id: 12, tracking_no: "AXA-3297-DR.E.ALTUNC-HUK", reused: false });
    const body = authRequestMock.mock.calls[0][2] as Record<string, unknown>;
    expect(body).not.toHaveProperty("tracking_no");
    expect(body.istek_kimligi).toBe("3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a");
  });

  it("saveCase tekrar eden istekte reused: true bildirir", async () => {
    authRequestMock.mockResolvedValue(jsonResponse({ status: "success", id: 12, tracking_no: "AXA-3297", reused: true }));

    let result: Awaited<ReturnType<CasesApi["saveCase"]>> | null = null;
    await act(async () => {
      result = await api().saveCase({ status: "DERDEST", parties: [] });
    });

    expect(result!.reused).toBe(true);
    expect(result!.id).toBe(12);
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
        // G237 (test taşıma): yükte `tracking_no` yok — numarayı sunucu verir.
        await api().saveCase({ status: "DERDEST", parties: [] });
      } catch { /* kapı: tüketici burada toast basıp return eder */ }
    });

    expect(saveAttempted).toBe(false);
    expect(authRequestMock).not.toHaveBeenCalledWith("/api/cases", "POST", expect.anything());
  });
});

// G237: üç dava açma yolunun ortak önizleme kancası — debounce + yenileme + hata.
describe("useOfisNoOnizleme — debounce'lu önizleme (G237)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let durum: OfisNoOnizlemeDurumu;
  const istek = vi.fn<(sorgu: string) => Promise<OfisNoOnizleme>>();

  const Harness = ({ sorgu }: { sorgu: string | null }) => {
    durum = useOfisNoOnizleme(sorgu, istek);
    return null;
  };
  const render = (sorgu: string | null) => act(() => root!.render(<Harness sorgu={sorgu} />));
  /** Zamanı ilerletir ve bekleyen promise zincirini boşaltır. */
  const ilerlet = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

  beforeEach(() => {
    vi.useFakeTimers();
    istek.mockReset();
    istek.mockImplementation(async sorgu => ({ onizleme: `NO[${sorgu}]` }));
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
    vi.useRealTimers();
  });

  it("müvekkil yokken (sorgu null) istek atılmaz, önizleme boştur", async () => {
    render(null);
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS * 3);

    expect(istek).not.toHaveBeenCalled();
    expect(durum).toEqual({ onizleme: null, sigortaliEksik: false, isLoading: false, error: null });
  });

  it("istek debounce süresi dolmadan ATILMAZ; dolunca bir kez atılır", async () => {
    render("muvekkiller=41");
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS - 1);
    expect(istek).not.toHaveBeenCalled();
    expect(durum.isLoading).toBe(true);

    await ilerlet(1);
    expect(istek).toHaveBeenCalledTimes(1);
    expect(istek).toHaveBeenCalledWith("muvekkiller=41");
    expect(durum).toEqual({ onizleme: "NO[muvekkiller=41]", sigortaliEksik: false, isLoading: false, error: null });
  });

  it("art arda değişen sorgu (tuş vuruşları) tek isteğe iner — yalnız SON değer sorulur", async () => {
    render("muvekkiller=A");
    await ilerlet(100);
    render("muvekkiller=Ah");
    await ilerlet(100);
    render("muvekkiller=Ahmet");
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS);

    expect(istek).toHaveBeenCalledTimes(1);
    expect(istek).toHaveBeenCalledWith("muvekkiller=Ahmet");
    expect(durum.onizleme).toBe("NO[muvekkiller=Ahmet]");
  });

  it("müvekkil / tür değişince önizleme yenilenir", async () => {
    render("muvekkiller=41&file_type=Hukuk");
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS);
    expect(durum.onizleme).toBe("NO[muvekkiller=41&file_type=Hukuk]");

    render("muvekkiller=41&file_type=Ceza");
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS);
    expect(istek).toHaveBeenCalledTimes(2);
    expect(durum.onizleme).toBe("NO[muvekkiller=41&file_type=Ceza]");

    render("muvekkiller=52&file_type=Ceza");
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS);
    expect(istek).toHaveBeenCalledTimes(3);
    expect(durum.onizleme).toBe("NO[muvekkiller=52&file_type=Ceza]");
  });

  it("aynı sorguyla yeniden render yeni istek atmaz", async () => {
    render("muvekkiller=41");
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS);
    render("muvekkiller=41");
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS * 2);

    expect(istek).toHaveBeenCalledTimes(1);
  });

  it("önizleme alınamazsa uydurma numara gösterilmez; hata BİLGİ olarak döner", async () => {
    istek.mockRejectedValue(new Error(OFIS_NO_ONIZLEME_ERROR));
    render("muvekkiller=41");
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS);

    expect(durum).toEqual({ onizleme: null, sigortaliEksik: false, isLoading: false, error: OFIS_NO_ONIZLEME_ERROR });
  });

  it("bayat yanıt (arada sorgu değişti) güncel önizlemeyi ezmez", async () => {
    let eskiyiCoz: (v: OfisNoOnizleme) => void = () => undefined;
    istek.mockImplementationOnce(() => new Promise<OfisNoOnizleme>(resolve => { eskiyiCoz = resolve; }));
    render("muvekkiller=eski");
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS);

    render("muvekkiller=yeni");
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS);
    expect(durum.onizleme).toBe("NO[muvekkiller=yeni]");

    await act(async () => { eskiyiCoz({ onizleme: "BAYAT" }); });
    expect(durum.onizleme).toBe("NO[muvekkiller=yeni]");
  });

  it("sigortalı eksikse bayrak taşınır; müvekkil silinince önizleme kapanır", async () => {
    istek.mockResolvedValue({ onizleme: "AXA-3297", sigortali_eksik: true });
    render("muvekkiller=AXA");
    await ilerlet(OFIS_NO_ONIZLEME_DEBOUNCE_MS);
    expect(durum.sigortaliEksik).toBe(true);

    render(null);
    await ilerlet(0);
    expect(durum).toEqual({ onizleme: null, sigortaliEksik: false, isLoading: false, error: null });
  });
});
