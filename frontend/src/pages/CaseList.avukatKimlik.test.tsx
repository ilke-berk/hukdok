// @vitest-environment jsdom
// G229: dava listesinin "Sorumlu Avukat" filtresi avukatın kurumsal KİMLİĞİNİ (`AVK-…`, G228)
// değer olarak taşır ve dava isteğine `lawyer=<kimlik>` olarak gider; ekranda yalnız ad
// görünür, kod/kimlik basılmaz. "Tüm Avukatlar" (ALL) değişmez.
// Harness CaseList.config.test.tsx ile aynı (gerçek useConfig + QueryClient, düz DOM'a
// indirilmiş popover/command); CommandItem tıklanınca bileşenin `onSelect`'ini çağırır.
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
const casesApi = vi.hoisted(() => ({
  getCases: vi.fn(async () => ({ cases: [], total: 0 })),
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
vi.mock("@/components/ui/popover", () => ({
  Popover: ({ children }: Kids) => <div>{children}</div>,
  PopoverTrigger: ({ children }: Kids) => <div>{children}</div>,
  PopoverContent: ({ children }: Kids) => <div>{children}</div>,
}));
vi.mock("@/components/ui/command", () => ({
  Command: ({ children }: Kids) => <div>{children}</div>,
  CommandInput: () => null,
  CommandList: ({ children }: Kids) => <div>{children}</div>,
  CommandGroup: ({ children }: Kids) => <div>{children}</div>,
  CommandItem: ({ value, children, onSelect }: Kids & { value: string; onSelect?: (v: string) => void }) =>
    <div data-option={value} onClick={() => onSelect?.(value)}>{children}</div>,
}));

import CaseList from "./CaseList";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Sunucu G228 sözleşmesiyle hem iç kodu hem kurumsal kimliği döner; istemci kodu kullanmaz.
const LAWYERS = [
  { code: "ZZ", kimlik: "AVK-00001", name: "Av. Zeynep Zor" },
  { code: "AA", kimlik: "AVK-00002", name: "Av. Ali Ak" },
];

describe("CaseList — avukat filtresi kurumsal kimlikle (G229)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    const bodies: Record<string, unknown> = { "/api/config/lawyers": LAWYERS };
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

  const ownText = (el: Element) =>
    Array.from(el.childNodes)
      .filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent ?? "")
      .join("")
      .trim();

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

  const lastLawyerOption = () =>
    (casesApi.getCases.mock.calls.at(-1) as unknown as [{ lawyer?: string }] | undefined)?.[0]?.lawyer;

  it("seçenek değerleri kurumsal kimlik; ekranda ad var, kod/kimlik yok", async () => {
    render();
    await waitFor(() => optionsUnder("Sorumlu Avukat").length === 3, "avukat seçenekleri doldu");

    const opts = optionsUnder("Sorumlu Avukat");
    expect(opts.map(o => o.getAttribute("data-option"))).toEqual(["ALL", "AVK-00001", "AVK-00002"]);
    expect(opts.map(o => o.textContent)).toEqual(["Tüm Avukatlar", "Av. Zeynep Zor", "Av. Ali Ak"]);

    const text = container.textContent ?? "";
    expect(text).not.toContain("AVK-");
    expect(text).not.toMatch(/\bZZ\b|\bAA\b/);
  });

  it("avukat seçilince dava isteği lawyer=<kimlik> taşır; Tüm Avukatlar'a dönünce ALL", async () => {
    render();
    await waitFor(() => optionsUnder("Sorumlu Avukat").length === 3, "avukat seçenekleri doldu");
    await waitFor(() => casesApi.getCases.mock.calls.length > 0, "ilk dava isteği");
    expect(lastLawyerOption()).toBe("ALL");

    const ali = optionsUnder("Sorumlu Avukat").find(o => o.getAttribute("data-option") === "AVK-00002")!;
    act(() => ali.click());
    await waitFor(() => lastLawyerOption() === "AVK-00002", "kimlikle istek");
    expect(lastLawyerOption()).toBe("AVK-00002");

    const all = optionsUnder("Sorumlu Avukat").find(o => o.getAttribute("data-option") === "ALL")!;
    act(() => all.click());
    await waitFor(() => lastLawyerOption() === "ALL", "filtre kalktı");
    expect(lastLawyerOption()).toBe("ALL");
  });
});
