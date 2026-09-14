// @vitest-environment jsdom
// G185: Index yalnız okuduğu config listesine (doctypes) abone olur — useConfig()
// monte edilince 32 `/api/config/*` ucuna birden istek atıyordu.
// Gerçek useConfig modülü + gerçek QueryClient; yalnız ağ (authRequest), MSAL ve
// sayfanın ağır çocukları taklit edilir. Çocukların kendi uçları kendi testlerinde
// (QuickCaseModal.config.test.tsx, EmailModal.config.test.tsx).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
// Oturum açık kabul edilir (config sorguları enabled: accounts.length > 0).
const msal = vi.hoisted(() => ({ accounts: [{ username: "a@b.c", name: "Test Kullanıcı" }] }));
vi.mock("@azure/msal-react", () => ({ useMsal: () => msal }));
vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
// Effect bağımlılığında oldukları için fonksiyon kimlikleri sabit tutulur.
const casesApi = vi.hoisted(() => ({
  getCases: async () => ({ cases: [], total: 0 }),
  searchCases: async () => [],
}));
vi.mock("@/hooks/useCases", () => ({
  useCases: () => casesApi,
  CASE_LIST_ERROR: "Dava listesi alınamadı — sunucuya ulaşılamadı.",
}));
// Kısmi taklit: useFormDraft modülün diğer dışa verimlerini (SESSION_EXPIRED_EVENT) kullanır.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiClient: { fetch: async () => ({ ok: false, json: async () => ({}) }) },
}));
// IndexedDB jsdom'da yok; çıktı klasörü testin konusu değil.
vi.mock("@/lib/directoryStorage", () => ({
  getStoredOutputDir: async () => null,
  setStoredOutputDir: async () => undefined,
}));
vi.mock("@/components/QuickCaseModal", () => ({ QuickCaseModal: () => null }));
vi.mock("@/components/email/EmailModal", () => ({ EmailModal: () => null }));
vi.mock("@/components/BulkUploadWorkbench", () => ({ BulkUploadWorkbench: () => null }));
vi.mock("@/components/AnalysisResults", () => ({ AnalysisResults: () => null }));

import Index from "./Index";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const configUrls = (): string[] =>
  authRequestMock.mock.calls
    .map(([url]) => url as string)
    .filter(u => u.startsWith("/api/config/"))
    .sort();

describe("Index — config aboneliği (G185)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    authRequestMock.mockImplementation(async () => ({ ok: true, json: async () => [] }));
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    queryClient.clear();
  });

  async function waitFor(condition: () => boolean, label: string): Promise<void> {
    for (let i = 0; i < 100; i++) {
      if (condition()) return;
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
    throw new Error(`Koşul sağlanmadı: ${label}`);
  }

  /** Geç kalan istek varsa sayaca düşsün diye birkaç tur boşaltır. */
  async function flush(): Promise<void> {
    for (let i = 0; i < 5; i++) {
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
  }

  it("monte edilince yalnız /api/config/doctypes çağrılır (useConfig 32 uç çağırıyordu)", async () => {
    root = createRoot(container);
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Index />
        </MemoryRouter>
      </QueryClientProvider>,
    ));

    await waitFor(
      () => queryClient.getQueryState(["config", "doctypes"])?.status === "success",
      "belge türü listesi yüklendi",
    );
    await flush();

    expect(configUrls()).toEqual(["/api/config/doctypes"]);
  });
});
