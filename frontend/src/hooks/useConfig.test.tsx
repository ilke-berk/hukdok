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

import { useConfig, CONFIG_LIST_ERROR, REQUIRED_FIELDS_ERROR } from "./useConfig";

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

describe("useConfig — hata ≠ boş liste (G019)", () => {
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

  it("başarılı yanıtta listeleri verir, hata bayrakları kapalıdır", async () => {
    routeMock({
      "/api/config/lawyers": { ok: true, body: [{ code: "AGH", name: "Av. Ayşe Gül Hanyaloğlu" }] },
      "/api/config/required_case_fields": {
        ok: true,
        body: { fields: [{ field: "esas_no", label: "Esas No" }], party_rule: null },
      },
    });
    const api = mount();

    await waitFor(() => api().lawyers.length > 0, "avukat listesi doldu");

    expect(api().isConfigError).toBe(false);
    expect(api().configError).toBeUndefined();
    expect(api().isRequiredFieldsError).toBe(false);
    expect(api().requiredCaseFields).toHaveLength(1);
  });

  it("liste ucu hata verince BOŞ LİSTE + normal görünüm DEĞİL, hata state'i", async () => {
    routeMock({ "/api/config/": { ok: false, body: { detail: "bozuk" } } });
    const api = mount();

    await waitFor(() => api().isConfigError, "config hata state'i");

    expect(api().configError).toBe(CONFIG_LIST_ERROR);
    // Listeler boş kalır ama çağıran configError sayesinde boş listeyle karıştırmaz.
    expect(api().lawyers).toEqual([]);
    expect(api().fileTypes).toEqual([]);
  });

  it("ağ tamamen yoksa (authRequest null) da hata state'ine düşer", async () => {
    authRequestMock.mockResolvedValue(null);
    const api = mount();

    await waitFor(() => api().isConfigError, "config hata state'i");

    expect(api().configError).toBe(CONFIG_LIST_ERROR);
    expect(api().isRequiredFieldsError).toBe(true);
    expect(api().requiredFieldsError).toBe(REQUIRED_FIELDS_ERROR);
  });

  it("zorunlu alan ucu hata verince kapı sessizce açılmaz: liste boş AMA hata görünür", async () => {
    routeMock({ "/api/config/required_case_fields": { ok: false, body: {} } });
    const api = mount();

    await waitFor(() => api().isRequiredFieldsError, "zorunlu alan hata state'i");

    expect(api().requiredFieldsError).toBe(REQUIRED_FIELDS_ERROR);
    // Boş liste "hiçbir alan zorunlu değil" diye okunmasın diye bayrak şart.
    expect(api().requiredCaseFields).toEqual([]);
    expect(api().requiredPartyRule).toBeNull();
    // Diğer listeler sağlamsa genel config hatası yanmaz.
    expect(api().isConfigError).toBe(false);
  });

  it("karar sonucu listeleri (G060 uçları) resmî sırayla gelir, hata yakmaz (G061)", async () => {
    routeMock({
      "/api/config/local_decisions": { ok: true, body: [{ code: "DERDEST", name: "Derdest" }] },
      // Sıra bilinçli alfabetik DEĞİL: kayıt sırası = resmi havuz sırası korunmalı
      "/api/config/appeal_decisions": {
        ok: true,
        body: [{ code: "KALDIRMA", name: "Kaldırma" }, { code: "BASVURU_RET", name: "Başvuru Ret" }],
      },
      "/api/config/required_case_fields": { ok: true, body: { fields: [], party_rule: null } },
    });
    const api = mount();

    await waitFor(() => api().appealDecisions.length > 0, "istinaf karar listesi doldu");

    expect(api().appealDecisions.map(i => i.name)).toEqual(["Kaldırma", "Başvuru Ret"]);
    expect(api().localDecisions.map(i => i.name)).toEqual(["Derdest"]);
    // Verilmeyen uçlar routeMock'ta boş döner — boş liste hata DEĞİLDİR (G019 ayrımı)
    expect(api().cassationDecisions).toEqual([]);
    expect(api().revisionDecisions).toEqual([]);
    expect(api().isConfigError).toBe(false);
  });

  it("tekrar dene başarılı olunca hata state'i temizlenir", async () => {
    routeMock({ "/api/config/": { ok: false, body: {} } });
    const api = mount();
    await waitFor(() => api().isConfigError, "ilk hata");

    routeMock({
      "/api/config/lawyers": { ok: true, body: [{ code: "AGH", name: "GERİ GELDİ" }] },
      "/api/config/required_case_fields": { ok: true, body: { fields: [], party_rule: null } },
    });
    await act(async () => { await api().refetchConfig(); });

    await waitFor(() => !api().isConfigError, "hata temizlendi");
    expect(api().lawyers).toHaveLength(1);
  });
});
