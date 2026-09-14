// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import appSource from "@/App.tsx?raw";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
// Oturum açık kabul edilir (enabled: accounts.length > 0).
vi.mock("@azure/msal-react", () => ({ useMsal: () => ({ accounts: [{ username: "a@b.c" }] }) }));

import {
  useConfig,
  useConfigList,
  CONFIG_LIST_ERROR,
  groupCourtTypesByParent,
  splitPartyRoles,
  type ConfigItem,
} from "./useConfig";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const LAWYERS: ConfigItem[] = [{ code: "AGH", name: "Av. Ayşe Gül Hanyaloğlu" }];

/** URL'e göre yanıt üretir; verilmeyen uçlar başarılı ve boş döner. */
const routeMock = (handlers: Record<string, { ok: boolean; body?: unknown }>) => {
  authRequestMock.mockImplementation(async (url: string) => {
    for (const [fragment, res] of Object.entries(handlers)) {
      if (url.includes(fragment)) return { ok: res.ok, json: async () => res.body ?? {} };
    }
    return { ok: true, json: async () => [] };
  });
};

const calledUrls = (): string[] => authRequestMock.mock.calls.map(([url]) => url as string);
const callsTo = (url: string): number => calledUrls().filter(u => u === url).length;

describe("useConfigList — liste başına abonelik (G184)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;

  beforeEach(() => {
    vi.clearAllMocks();
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
  });

  /** Sorgular mount anında koştuğu için hook, mock kurulduktan SONRA bağlanır. */
  function mount<T>(useHook: () => T, queryClient: QueryClient): () => T {
    let captured: { value: T } | null = null;
    const Harness = () => {
      captured = { value: useHook() };
      return null;
    };
    root = createRoot(container);
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <Harness />
      </QueryClientProvider>,
    ));
    return () => captured!.value;
  }

  const testClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

  async function waitFor(condition: () => boolean, label: string): Promise<void> {
    for (let i = 0; i < 100; i++) {
      if (condition()) return;
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
    throw new Error(`Koşul sağlanmadı: ${label}`);
  }

  /** Bekleyen istek/yeniden çekme varsa sonuçlansın diye birkaç tur boşaltır. */
  async function flush(): Promise<void> {
    for (let i = 0; i < 5; i++) {
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
  }

  it("useConfigList('lawyers') yalnız /api/config/lawyers ucunu BİR kez çağırır", async () => {
    routeMock({ "/api/config/lawyers": { ok: true, body: LAWYERS } });
    const api = mount(() => useConfigList("lawyers"), testClient());

    await waitFor(() => api().data.length > 0, "avukat listesi doldu");
    await flush();

    expect(calledUrls()).toEqual(["/api/config/lawyers"]);
    expect(api().data).toEqual(LAWYERS);
    expect(api().isLoading).toBe(false);
    expect(api().isError).toBe(false);
    expect(api().error).toBeUndefined();
  });

  it("uç yolu anahtarın ikinci parçasıdır (emailRecipients → /api/config/email_recipients)", async () => {
    routeMock({});
    const api = mount(() => useConfigList("emailRecipients"), testClient());

    await waitFor(() => !api().isLoading, "liste yüklendi");
    await flush();

    expect(calledUrls()).toEqual(["/api/config/email_recipients"]);
  });

  it("useConfig() + useConfigList('lawyers') aynı bileşende → önbellek ortak, /api/config/lawyers yine 1 kez", async () => {
    routeMock({ "/api/config/lawyers": { ok: true, body: LAWYERS } });
    const api = mount(() => ({ all: useConfig(), list: useConfigList("lawyers") }), testClient());

    await waitFor(
      () => api().list.data.length > 0 && api().all.lawyers.length > 0 && !api().all.isLoading,
      "iki hook da doldu",
    );
    await flush();

    expect(callsTo("/api/config/lawyers")).toBe(1);
    // Aynı önbellek girdisi: iki hook aynı dizi referansını görür.
    expect(api().list.data).toBe(api().all.lawyers);
  });

  it("uç hata verince BOŞ LİSTE değil hata state'i (G019 sözleşmesi)", async () => {
    routeMock({ "/api/config/lawyers": { ok: false, body: { detail: "bozuk" } } });
    const api = mount(() => useConfigList("lawyers"), testClient());

    await waitFor(() => api().isError, "hata state'i");

    expect(api().error).toBe(CONFIG_LIST_ERROR);
    expect(api().data).toEqual([]);
  });

  it("refetch uca yeniden gider ve hata temizlenir", async () => {
    routeMock({ "/api/config/lawyers": { ok: false, body: {} } });
    const api = mount(() => useConfigList("lawyers"), testClient());
    await waitFor(() => api().isError, "ilk hata");

    routeMock({ "/api/config/lawyers": { ok: true, body: LAWYERS } });
    await act(async () => { await api().refetch(); });

    await waitFor(() => !api().isError, "hata temizlendi");
    expect(api().data).toEqual(LAWYERS);
    expect(callsTo("/api/config/lawyers")).toBe(2);
  });

  /** Veriyi 10 dk önce alınmış gibi işaretler (staleTime 5 dk) ve odak olaylarını yayar. */
  async function staleAndFocus(queryClient: QueryClient): Promise<void> {
    act(() => {
      queryClient.setQueryData(["config", "lawyers"], LAWYERS, { updatedAt: Date.now() - 10 * 60 * 1000 });
    });
    expect(queryClient.getQueryState(["config", "lawyers"])?.isInvalidated).toBe(false);
    act(() => {
      window.dispatchEvent(new Event("focus"));
      window.dispatchEvent(new Event("visibilitychange"));
      document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
    });
    await flush();
  }

  it("App QueryClient ayarıyla pencere odağında bayat sorgu YENİDEN çekilmez", async () => {
    routeMock({ "/api/config/lawyers": { ok: true, body: LAWYERS } });
    // App.tsx'teki ayarın aynısı (aşağıdaki kaynak bekçisi bu satırı App.tsx'te arar).
    const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });
    const api = mount(() => useConfigList("lawyers"), queryClient);
    await waitFor(() => api().data.length > 0, "avukat listesi doldu");
    expect(callsTo("/api/config/lawyers")).toBe(1);

    await staleAndFocus(queryClient);

    expect(callsTo("/api/config/lawyers")).toBe(1);
  });

  it("kontrol: varsayılan QueryClient'ta aynı odak olayı bayat sorguyu yeniden çeker (test boşa çalışmıyor)", async () => {
    routeMock({ "/api/config/lawyers": { ok: true, body: LAWYERS } });
    const queryClient = new QueryClient();
    const api = mount(() => useConfigList("lawyers"), queryClient);
    await waitFor(() => api().data.length > 0, "avukat listesi doldu");
    expect(callsTo("/api/config/lawyers")).toBe(1);

    await staleAndFocus(queryClient);

    expect(callsTo("/api/config/lawyers")).toBe(2);
  });

  it("kaynak bekçisi: App.tsx QueryClient'ı refetchOnWindowFocus:false ile kurar", () => {
    expect(appSource).toMatch(
      /new QueryClient\(\{\s*defaultOptions:\s*\{\s*queries:\s*\{\s*refetchOnWindowFocus:\s*false\s*\}\s*\}\s*\}\)/,
    );
  });
});

describe("useConfig türetilmiş yardımcıları (G184)", () => {
  it("groupCourtTypesByParent üst koda göre gruplar, üst kodsuz öğe boş anahtara düşer", () => {
    const items: ConfigItem[] = [
      { code: "AS", name: "Asliye Hukuk", parent_code: "HUKUK" },
      { code: "IDR", name: "İdare", parent_code: "IDARI" },
      { code: "TK", name: "Tüketici", parent_code: "HUKUK" },
      { code: "X", name: "Üst kodsuz" },
    ];
    expect(groupCourtTypesByParent(items)).toEqual({
      HUKUK: [items[0], items[2]],
      IDARI: [items[1]],
      "": [items[3]],
    });
  });

  it("splitPartyRoles MAIN/THIRD ayırır, diğer türleri dışarıda bırakır", () => {
    const items: ConfigItem[] = [
      { code: "DAVACI", name: "Davacı", role_type: "MAIN" },
      { code: "FER", name: "Fer'i Müdahil", role_type: "THIRD" },
      { code: "DAVALI", name: "Davalı", role_type: "MAIN" },
      { code: "?", name: "Türsüz" },
    ];
    expect(splitPartyRoles(items)).toEqual({ main: [items[0], items[2]], third: [items[1]] });
  });
});
