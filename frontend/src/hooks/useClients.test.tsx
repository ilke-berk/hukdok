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

import { useClients, CLIENT_LIST_ERROR } from "./useClients";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type ClientsApi = ReturnType<typeof useClients>;

describe("useClients — hata ≠ boş liste (G002)", () => {
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

  /** Sorgu mount anında koştuğu için hook, mock kurulduktan SONRA bağlanır. */
  function mount(): () => ClientsApi {
    let captured: ClientsApi | null = null;
    const Harness = () => {
      captured = useClients();
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

  it("başarılı yanıtta listeyi verir, hata bayrağı kapalıdır", async () => {
    authRequestMock.mockResolvedValue({ ok: true, json: async () => [{ id: 1, name: "MÜVEKKİL" }] });
    const api = mount();

    await waitFor(() => api().clients.length > 0, "müvekkil listesi doldu");

    expect(api().isClientsError).toBe(false);
    expect(api().clientsError).toBeUndefined();
  });

  it("hatada boş liste + 'kayıt yok' yerine hata state'ine düşer", async () => {
    authRequestMock.mockResolvedValue({ ok: false, json: async () => ({}) });
    const api = mount();

    await waitFor(() => api().isClientsError, "hata state'i");

    expect(api().clientsError).toBe(CLIENT_LIST_ERROR);
    // Liste boş kalır ama çağıran isClientsError sayesinde boş listeyle karıştırmaz.
    expect(api().clients).toEqual([]);
  });

  it("ağ tamamen yoksa (authRequest null) da hata state'ine düşer", async () => {
    authRequestMock.mockResolvedValue(null);
    const api = mount();

    await waitFor(() => api().isClientsError, "hata state'i");

    expect(api().clientsError).toBe(CLIENT_LIST_ERROR);
  });

  it("tekrar dene başarılı olunca hata state'i temizlenir", async () => {
    authRequestMock.mockResolvedValue({ ok: false, json: async () => ({}) });
    const api = mount();
    await waitFor(() => api().isClientsError, "ilk hata");

    authRequestMock.mockResolvedValue({ ok: true, json: async () => [{ id: 2, name: "GERİ GELDİ" }] });
    await act(async () => { await api().refetchClients(); });

    await waitFor(() => !api().isClientsError, "hata temizlendi");
    expect(api().clients).toHaveLength(1);
  });
});
