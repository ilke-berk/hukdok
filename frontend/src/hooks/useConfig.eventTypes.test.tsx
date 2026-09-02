// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
// Oturum açık kabul edilir (enabled: accounts.length > 0).
vi.mock("@azure/msal-react", () => ({ useMsal: () => ({ accounts: [{ username: "a@b.c" }] }) }));

import { useConfig, CONFIG_LIST_ERROR } from "./useConfig";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type ConfigApi = ReturnType<typeof useConfig>;

/** URL'e göre yanıt üretir; verilmeyen uçlar başarılı ve boş döner. */
const routeMock = (handlers: Record<string, { ok: boolean; body?: unknown }>) => {
  authRequestMock.mockImplementation(async (url: string) => {
    for (const [fragment, res] of Object.entries(handlers)) {
      if (url.includes(fragment)) return { ok: res.ok, json: async () => res.body ?? {} };
    }
    return { ok: true, json: async () => [] };
  });
};

/**
 * G105 — belgeleme olayı kapalı listeleri (event_types / judgment_roles).
 * Uçlar alleged_faults biçimindedir (code/name/active/sequence, backend
 * sequence ile sıralı döner); dava kartı ve liste filtresi BURADAN beslenir.
 */
describe("useConfig — G105 event_types / judgment_roles", () => {
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
  function mount(): () => ConfigApi {
    let captured: ConfigApi | null = null;
    const Harness = () => {
      captured = useConfig();
      return null;
    };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    root = createRoot(container);
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <Harness />
      </QueryClientProvider>,
    ));
    return () => captured!;
  }

  async function waitFor(condition: () => boolean, label: string): Promise<void> {
    for (let i = 0; i < 100; i++) {
      if (condition()) return;
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
    throw new Error(`Koşul sağlanmadı: ${label}`);
  }

  it("iki listeyi kendi uçlarından backend sırasıyla verir (sözleşme değerleri)", async () => {
    routeMock({
      "/api/config/event_types": {
        ok: true,
        body: [
          { code: "TIBBI", name: "Tıbbi Olay" },
          { code: "BELGELEME", name: "Belgeleme Olayı" },
          { code: "TIBBI_BELGELEME", name: "Tıbbi + Belgeleme" },
        ],
      },
      "/api/config/judgment_roles": {
        ok: true,
        body: [
          { code: "TEK_GEREKCE", name: "Tek Gerekçe" },
          { code: "YAN_GEREKCE", name: "Yan Gerekçe" },
          { code: "YALNIZ_SAPTAMA", name: "Yalnız Saptama" },
          { code: "REDDEDILMIS", name: "Reddedilmiş İddia" },
        ],
      },
      "/api/config/required_case_fields": { ok: true, body: { fields: [], party_rule: null } },
    });
    const api = mount();

    await waitFor(() => api().eventTypes.length > 0, "olay türü listesi doldu");
    await waitFor(() => api().judgmentRoles.length > 0, "hükümdeki rol listesi doldu");

    expect(api().eventTypes.map(i => i.name))
      .toEqual(["Tıbbi Olay", "Belgeleme Olayı", "Tıbbi + Belgeleme"]);
    expect(api().judgmentRoles.map(i => i.name))
      .toEqual(["Tek Gerekçe", "Yan Gerekçe", "Yalnız Saptama", "Reddedilmiş İddia"]);
    expect(api().isConfigError).toBe(false);
  });

  it("uç hata verirse G019 kuralı yeni listelerde de işler: boş liste + hata bayrağı", async () => {
    routeMock({
      "/api/config/event_types": { ok: false, body: { detail: "bozuk" } },
      "/api/config/required_case_fields": { ok: true, body: { fields: [], party_rule: null } },
    });
    const api = mount();

    await waitFor(() => api().isConfigError, "config hata state'i");

    expect(api().configError).toBe(CONFIG_LIST_ERROR);
    // Boş liste "değer yok" diye okunmasın — bayrak kesintiyi ayırt ettirir.
    expect(api().eventTypes).toEqual([]);
  });
});
