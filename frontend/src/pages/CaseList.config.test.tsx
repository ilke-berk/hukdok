// @vitest-environment jsdom
// G185: CaseList yalnız filtre rayının okuduğu üç listeye (lawyers, event_types,
// service_types) abone olur — useConfig() 32 `/api/config/*` ucu çağırıyordu.
// Gerçek useConfig modülü + gerçek QueryClient; ağ (authRequest), MSAL, dava hook'u
// taklit edilir. Radix Select içeriği jsdom'da kapalıyken basılmadığı için Select
// düz DOM'a indirilir: seçenek SIRASI ve değeri doğrudan okunur.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
const msal = vi.hoisted(() => ({ accounts: [{ username: "a@b.c" }] }));
vi.mock("@azure/msal-react", () => ({ useMsal: () => msal }));
vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("@/hooks/usePageSearch", () => ({ usePageSearch: () => ({ query: "", setQuery: () => undefined }) }));
// fetchCases/fetchStats useCallback bağımlılığında — kimlikler sabit.
const casesApi = vi.hoisted(() => ({
  getCases: async () => ({ cases: [], total: 0 }),
  getCaseStats: async () => ({ total: 0, active: 0, closed: 0, danis_active: 0, statuses: {} }),
}));
vi.mock("@/hooks/useCases", () => ({
  useCases: () => casesApi,
  CASE_LIST_ERROR: "Dava listesi alınamadı — sunucuya ulaşılamadı.",
}));
vi.mock("@/lib/api", () => ({ apiClient: { fetch: async () => ({ ok: true, json: async () => [] }) } }));

type Kids = { children?: ReactNode };
vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: Kids) => <div>{children}</div>,
  SelectTrigger: ({ children }: Kids) => <div>{children}</div>,
  SelectValue: () => null,
  SelectContent: ({ children }: Kids) => <div>{children}</div>,
  SelectItem: ({ value, children }: Kids & { value: string }) => <div data-option={value}>{children}</div>,
}));

import CaseList from "./CaseList";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Bilinçli alfabetik DEĞİL: liste backend sırasıyla (sequence) basılmalı.
const LAWYERS = [{ code: "ZZ", name: "Av. Zeynep Zor" }, { code: "AA", name: "Av. Ali Ak" }];
const EVENT_TYPES = [{ code: "TO", name: "Tıbbi Olay" }, { code: "BO", name: "Belgeleme Olayı" }];
const SERVICE_TYPES = [{ code: "LR", name: "Lexis Rapor" }, { code: "DT", name: "Dava Takibi" }];

const configUrls = (): string[] =>
  authRequestMock.mock.calls
    .map(([url]) => url as string)
    .filter(u => u.startsWith("/api/config/"))
    .sort();

describe("CaseList — config aboneliği (G185)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    const bodies: Record<string, unknown> = {
      "/api/config/lawyers": LAWYERS,
      "/api/config/event_types": EVENT_TYPES,
      "/api/config/service_types": SERVICE_TYPES,
    };
    authRequestMock.mockImplementation(async (url: string) => ({ ok: true, json: async () => bodies[url] ?? [] }));
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

  function render() {
    root = createRoot(container);
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CaseList />
        </MemoryRouter>
      </QueryClientProvider>,
    ));
  }

  async function waitFor(condition: () => boolean, label: string): Promise<void> {
    for (let i = 0; i < 100; i++) {
      if (condition()) return;
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
    throw new Error(`Koşul sağlanmadı: ${label}`);
  }

  async function flush(): Promise<void> {
    for (let i = 0; i < 5; i++) {
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
  }

  const ownText = (el: Element) =>
    Array.from(el.childNodes)
      .filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent ?? "")
      .join("")
      .trim();

  /** Etiketin en fazla 3 üst sarmalayıcısında bulunan seçici seçenekleri. */
  function optionsUnder(label: string): HTMLElement[] {
    for (const el of Array.from(container.querySelectorAll("*"))) {
      if (ownText(el) !== label) continue;
      let node: Element | null = el;
      for (let i = 0; i < 3 && node; i++) {
        const opts = node.querySelectorAll<HTMLElement>("[data-option]");
        if (opts.length > 0) return Array.from(opts);
        node = node.parentElement;
      }
    }
    return [];
  }

  const texts = (els: HTMLElement[]) => els.map(e => e.textContent);
  const values = (els: HTMLElement[]) => els.map(e => e.getAttribute("data-option"));

  it("monte edilince yalnız üç liste ucu çağrılır (≤ 3; useConfig 32 uç çağırıyordu)", async () => {
    render();
    await waitFor(
      () => ["lawyers", "event_types", "service_types"]
        .every(k => queryClient.getQueryState(["config", k])?.status === "success"),
      "üç liste yüklendi",
    );
    await flush();

    expect(configUrls()).toEqual([
      "/api/config/event_types",
      "/api/config/lawyers",
      "/api/config/service_types",
    ]);
  });

  it("filtre seçicileri listeleri backend sırasıyla ve aynı değerlerle basar", async () => {
    render();
    await waitFor(() => optionsUnder("Sorumlu Avukat").length === 3, "avukat seçenekleri doldu");
    await waitFor(() => optionsUnder("Olay Türü").length === 3, "olay türü seçenekleri doldu");
    await waitFor(() => optionsUnder("Hizmet Türü").length === 3, "hizmet türü seçenekleri doldu");

    const lawyers = optionsUnder("Sorumlu Avukat");
    expect(texts(lawyers)).toEqual(["Tüm Avukatlar", "Av. Zeynep Zor", "Av. Ali Ak"]);
    expect(values(lawyers)).toEqual(["ALL", "ZZ", "AA"]);

    const events = optionsUnder("Olay Türü");
    expect(texts(events)).toEqual(["Tümü", "Tıbbi Olay", "Belgeleme Olayı"]);
    expect(values(events)).toEqual(["ALL", "Tıbbi Olay", "Belgeleme Olayı"]);

    const services = optionsUnder("Hizmet Türü");
    expect(texts(services)).toEqual(["Tümü", "Lexis Rapor", "Dava Takibi"]);
    expect(values(services)).toEqual(["ALL", "Lexis Rapor", "Dava Takibi"]);
  });
});
