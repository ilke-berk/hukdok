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

/**
 * G256 — yönetim panelinin "Hizmet Türleri" sekmesi. Genel güncelle/sil/sırala uçları ve
 * yeni `addServiceType` sonrası `["config","service_types"]` sorgusu geçersizleşir:
 * karttaki ve yeni dava ekranındaki hizmet seçicisi yeni listeyi görür. G256 öncesi
 * `typeToKey`'de `service_types` yoktu → bu listede mutasyon sonrası yeniden çekme olmuyordu.
 */
describe("useConfig — G256 service_types önbellek tazeleme", () => {
  const SERVICE_URL = "/api/config/service_types";
  let container: HTMLDivElement;
  let root: Root | null = null;

  beforeEach(() => {
    vi.clearAllMocks();
    authRequestMock.mockImplementation(async (url: string, method: string) => {
      if (url === SERVICE_URL && method === "GET") return { ok: true, json: async () => SERVICE_TYPES };
      if (url === "/api/config/required_case_fields") return { ok: true, json: async () => ({ fields: [], party_rule: null }) };
      if (url === "/api/config/update") return { ok: true, json: async () => ({ status: "success", updated: 3 }) };
      if (url === "/api/config/delete") return { ok: true, json: async () => ({ status: "success", affected: 2 }) };
      if (method === "POST") return { ok: true, json: async () => ({ status: "success" }) };
      return { ok: true, json: async () => [] };
    });
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

  const calls = (url: string, method: string) =>
    authRequestMock.mock.calls.filter(([u, m]) => u === url && m === method);
  const serviceGets = () => calls(SERVICE_URL, "GET").length;

  async function mountLoaded(): Promise<() => ConfigApi> {
    const api = mount();
    await waitFor(() => api().serviceTypes.length === 9, "hizmet türü listesi doldu");
    expect(serviceGets()).toBe(1);
    return api;
  }

  it("yeniden adlandırma (updateItem) sonrası service_types sorgusu yeniden çekilir", async () => {
    const api = await mountLoaded();

    let updated = -1;
    await act(async () => {
      updated = await api().updateItem("service_types", "LEXIS-RAPOR", { name: "Lexis Raporu" });
    });

    expect(updated).toBe(3);
    expect(calls("/api/config/update", "POST").map(c => c[2]))
      .toEqual([{ type: "service_types", code: "LEXIS-RAPOR", fields: { name: "Lexis Raporu" } }]);
    await waitFor(() => serviceGets() === 2, "service_types yeniden çekildi");
  });

  it("silme (deleteItem) sonrası service_types sorgusu yeniden çekilir", async () => {
    const api = await mountLoaded();

    let affected = -1;
    await act(async () => {
      affected = await api().deleteItem("service_types", "LEXIS-RAPOR", "reassign", "DANISMANLIK");
    });

    expect(affected).toBe(2);
    expect(calls("/api/config/delete", "POST").map(c => c[2]))
      .toEqual([{ type: "service_types", code: "LEXIS-RAPOR", mode: "reassign", target_code: "DANISMANLIK" }]);
    await waitFor(() => serviceGets() === 2, "service_types yeniden çekildi");
  });

  it("sıralama (reorderList) sonrası service_types sorgusu yeniden çekilir", async () => {
    const api = await mountLoaded();

    await act(async () => {
      await api().reorderList("service_types", ["DANISMANLIK", "LEXIS-RAPOR"]);
    });

    expect(calls("/api/config/reorder", "POST").map(c => c[2]))
      .toEqual([{ type: "service_types", ordered_ids: ["DANISMANLIK", "LEXIS-RAPOR"] }]);
    await waitFor(() => serviceGets() === 2, "service_types yeniden çekildi");
  });

  it("addServiceType(code, name) POST /api/config/service_types atar ve aynı anahtarı geçersizler", async () => {
    const api = await mountLoaded();

    await act(async () => {
      await api().addServiceType("ARABULUCULUK", "Arabuluculuk");
    });

    expect(calls(SERVICE_URL, "POST").map(c => c[2])).toEqual([{ code: "ARABULUCULUK", name: "Arabuluculuk" }]);
    await waitFor(() => serviceGets() === 2, "service_types yeniden çekildi");
  });

  it("başka listenin mutasyonu service_types sorgusunu yeniden ÇEKMEZ (anahtar yalnız kendi tipine bağlı)", async () => {
    const api = await mountLoaded();

    await act(async () => {
      await api().updateItem("file_statuses", "BILIRKISIDE", { name: "Bilirkişide" });
    });
    await act(async () => { await new Promise(r => setTimeout(r, 30)); });

    expect(calls("/api/config/file_statuses", "GET").length).toBe(2);
    expect(serviceGets()).toBe(1);
  });
});
