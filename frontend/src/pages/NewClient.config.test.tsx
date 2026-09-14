// @vitest-environment jsdom
// G185: NewClient yalnız formun okuduğu üç listeye (cities, specialties,
// client_categories) abone olur — useConfig() 32 `/api/config/*` ucu çağırıyordu.
// Gerçek useConfig modülü + gerçek QueryClient; ağ (authRequest), MSAL ve müvekkil
// hook'u taklit edilir. Radix Select düz DOM'a indirilir: seçenek SIRASI okunur.
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
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
// `clients` düzenleme effect'inin bağımlılığında — kimlik sabit.
const clientsApi = vi.hoisted(() => ({
  saveClient: async () => null,
  updateClient: async () => null,
  deleteClient: async () => null,
  getClientCaseSummary: async () => null,
  clients: [] as unknown[],
  isLoading: false,
}));
vi.mock("@/hooks/useClients", () => ({ useClients: () => clientsApi }));

type Kids = { children?: ReactNode };
vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: Kids) => <div>{children}</div>,
  SelectTrigger: ({ children }: Kids) => <div>{children}</div>,
  SelectValue: () => null,
  SelectContent: ({ children }: Kids) => <div>{children}</div>,
  SelectItem: ({ value, children }: Kids & { value: string }) => <div data-option={value}>{children}</div>,
}));

import NewClient from "./NewClient";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const configUrls = (): string[] =>
  authRequestMock.mock.calls
    .map(([url]) => url as string)
    .filter(u => u.startsWith("/api/config/"))
    .sort();

describe("NewClient — config aboneliği (G185)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  const routes = (bodies: Record<string, unknown>) =>
    authRequestMock.mockImplementation(async (url: string) => ({ ok: true, json: async () => bodies[url] ?? [] }));

  beforeEach(() => {
    vi.clearAllMocks();
    routes({});
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
          <NewClient />
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

  const listsLoaded = () =>
    ["cities", "specialties", "client_categories"]
      .every(k => queryClient.getQueryState(["config", k])?.status === "success");

  const ownText = (el: Element) =>
    Array.from(el.childNodes)
      .filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent ?? "")
      .join("")
      .trim();

  /** Etiketin en fazla 3 üst sarmalayıcısında bulunan seçici seçenek metinleri. */
  function optionTexts(label: string): (string | null)[] {
    for (const el of Array.from(container.querySelectorAll("*"))) {
      if (ownText(el) !== label) continue;
      let node: Element | null = el;
      for (let i = 0; i < 3 && node; i++) {
        const opts = node.querySelectorAll("[data-option]");
        if (opts.length > 0) return Array.from(opts).map(o => o.textContent);
        node = node.parentElement;
      }
    }
    return [];
  }

  it("monte edilince yalnız üç liste ucu çağrılır (useConfig 32 uç çağırıyordu)", async () => {
    render();
    await waitFor(listsLoaded, "üç liste yüklendi");
    await flush();

    expect(configUrls()).toEqual([
      "/api/config/cities",
      "/api/config/client_categories",
      "/api/config/specialties",
    ]);
    // Kategori listesi boş gelirse eski yedek kategoriler aynen kalır.
    expect(optionTexts("Grup / Kategori"))
      .toEqual(["Doktor", "Kurum", "Özel Hastane", "Bireysel", "Sigorta Şirketi", "Diğer"]);
  });

  it("il ve kategori seçicileri listeleri backend sırasıyla basar", async () => {
    routes({
      "/api/config/cities": [{ code: "65", name: "Van" }, { code: "01", name: "Adana" }],
      "/api/config/client_categories": [{ code: "K", name: "Kurum" }, { code: "D", name: "Doktor" }],
    });
    render();
    await waitFor(listsLoaded, "üç liste yüklendi");
    await waitFor(() => optionTexts("İl").length === 2, "il seçenekleri doldu");

    expect(optionTexts("İl")).toEqual(["Van", "Adana"]);
    expect(optionTexts("Grup / Kategori")).toEqual(["Kurum", "Doktor"]);
  });
});
