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

/** Sözleşme (G119 ile ortak, dondurulmuş): 5 müvekkil tipi, 9 hizmet türü, bildirim sırasıyla. */
const CLIENT_TYPES = [
  { code: "SIGORTA", name: "Sigorta" },
  { code: "DOKTOR", name: "Doktor" },
  { code: "KURUM", name: "Kurum" },
  { code: "HASTA", name: "Hasta" },
  { code: "DIGER-SAGLIK-CALISANI", name: "Diğer Sağlık Çalışanı" },
];
const SERVICE_TYPES = [
  { code: "TAKIP-DOKTOR-MUVEKKIL", name: "Takip (doktor müvekkil)" },
  { code: "LEXIS-RAPOR", name: "Lexis Rapor" },
  { code: "VEKALETSIZ-TAKIP", name: "Vekaletsiz Takip" },
  { code: "VEKALETLI-TAKIP", name: "Vekaletli Takip" },
  { code: "VEKALET-UCRETI-ALACAGI", name: "Vekalet Ücreti Alacağı" },
  { code: "TAKIP-HASTA-VEKILLIGI", name: "Takip (hasta vekilliği)" },
  { code: "TAKIP-KURUM-VEKILLIGI", name: "Takip (kurum vekilliği)" },
  { code: "DANISMANLIK", name: "Danışmanlık" },
  { code: "TAKIP-SAGLIK-PERSONELI", name: "Takip (sağlık personeli)" },
];

/**
 * G121 — Müvekkil Tipi / Hizmet Türü kapalı listeleri (client_types /
 * service_types). Uçlar event_types biçimindedir (code/name/active/sequence,
 * backend sequence ile sıralı döner); büro kartı ve liste filtresi BURADAN beslenir.
 */
describe("useConfig — G121 client_types / service_types", () => {
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
      "/api/config/client_types": { ok: true, body: CLIENT_TYPES },
      "/api/config/service_types": { ok: true, body: SERVICE_TYPES },
      "/api/config/required_case_fields": { ok: true, body: { fields: [], party_rule: null } },
    });
    const api = mount();

    await waitFor(() => api().clientTypes.length > 0, "müvekkil tipi listesi doldu");
    await waitFor(() => api().serviceTypes.length > 0, "hizmet türü listesi doldu");

    expect(api().clientTypes.map(i => i.name))
      .toEqual(["Sigorta", "Doktor", "Kurum", "Hasta", "Diğer Sağlık Çalışanı"]);
    expect(api().serviceTypes.map(i => i.name)).toEqual([
      "Takip (doktor müvekkil)", "Lexis Rapor", "Vekaletsiz Takip", "Vekaletli Takip",
      "Vekalet Ücreti Alacağı", "Takip (hasta vekilliği)", "Takip (kurum vekilliği)",
      "Danışmanlık", "Takip (sağlık personeli)",
    ]);
    expect(api().isConfigError).toBe(false);

    // Uçlar doğru adla çağrıldı — sözleşme: /api/config/client_types + /api/config/service_types
    const urls = authRequestMock.mock.calls.map(c => String(c[0]));
    expect(urls).toContain("/api/config/client_types");
    expect(urls).toContain("/api/config/service_types");
  });

  it("uç hata verirse G019 kuralı yeni listelerde de işler: boş liste + hata bayrağı", async () => {
    routeMock({
      "/api/config/service_types": { ok: false, body: { detail: "bozuk" } },
      "/api/config/required_case_fields": { ok: true, body: { fields: [], party_rule: null } },
    });
    const api = mount();

    await waitFor(() => api().isConfigError, "config hata state'i");

    expect(api().configError).toBe(CONFIG_LIST_ERROR);
    // Boş liste "değer yok" diye okunmasın — bayrak kesintiyi ayırt ettirir.
    expect(api().serviceTypes).toEqual([]);
  });
});
