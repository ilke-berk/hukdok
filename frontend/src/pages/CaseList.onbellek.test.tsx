// @vitest-environment jsdom
// Faz 3 (algılanan hız, 02.10): Dava Listesi react-query önbelleğinden çizer
// (`hooks/useCaseQueries.ts`). Kilitlenenler: ilk açılışta iskelet; geri dönüşte eldeki satırlar
// anında + sessiz tazeleme; filtre değişiminde eski satırlar soluk (keepPreviousData); G002 hata şeridi.
// Taklit düzeni CaseList.config.test.tsx ile aynı.
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
// Testler getCases'i değiştirir (yavaş ağ = hiç çözülmeyen söz); nesne kimliği sabit kalır.
const casesApi = vi.hoisted(() => ({
  getCases: vi.fn(),
  getCaseStats: vi.fn(),
}));
vi.mock("@/hooks/useCases", () => ({
  useCases: () => casesApi,
  CASE_LIST_ERROR: "Dava listesi alınamadı — sunucuya ulaşılamadı.",
}));
const olayIstekleri = vi.hoisted(() => [] as string[]);
vi.mock("@/lib/api", () => ({
  apiClient: {
    fetch: async (url: string) => {
      if (!url.startsWith("/api/cases/tibbi-olay-secenekleri")) return { ok: true, json: async () => [] };
      olayIstekleri.push(url);
      const body = url.includes("tibbi_surec=")
        ? [{ name: "Omuz Distosisi", count: 97 }]
        : [{ name: "Omuz Distosisi", count: 97 }, { name: "Asfiksik Doğum", count: 90 }];
      return { ok: true, json: async () => body };
    },
  },
}));

type Kids = { children?: ReactNode };
vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: Kids) => <div>{children}</div>,
  SelectTrigger: ({ children }: Kids) => <div>{children}</div>,
  SelectValue: () => null,
  SelectContent: ({ children }: Kids) => <div>{children}</div>,
  SelectItem: ({ value, children }: Kids & { value: string }) => <div data-option={value}>{children}</div>,
}));
// 27.09: "Sorumlu Avukat" filtresi artık LawyerCombobox (ui/popover + ui/command). Gerçek bileşen
// kullanılır; popover/command düz DOM'a indirilir ve CommandItem aynı `[data-option]` düğümünü
// basar — avukat beklentileri (metin + kod değeri + sıra) aynen okunur (G222 deseni).
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
  CommandItem: ({ value, children, onSelect }: Kids & { value: string; onSelect?: () => void }) => (
    <div data-option={value} onClick={onSelect}>{children}</div>
  ),
}));

import CaseList from "./CaseList";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const kart = (id: number, esas: string) => ({
  id, tracking_no: `T-${id}`, esas_no: esas, status: "DERDEST", court: "Mahkeme", subject: "Konu",
});
const ASKIDA = () => new Promise<never>(() => {});

describe("CaseList — önbellekten anında çizim (Faz 3, algılanan hız)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    authRequestMock.mockImplementation(async () => ({ ok: true, json: async () => [] }));
    casesApi.getCases.mockImplementation(async () => ({ cases: [kart(1, "2024/111"), kart(2, "2024/222")], total: 2 }));
    casesApi.getCaseStats.mockImplementation(async () => ({ total: 2, active: 2, closed: 0, danis_active: 0, statuses: { DERDEST: 2 } }));
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

  const iskelet = () => container.querySelector("[data-testid='table-skeleton']");
  const satirVar = () => container.textContent?.includes("2024/111") ?? false;

  it("ilk açılışta (önbellek boş) tablo iskeleti, yanıt gelince satırlar", async () => {
    casesApi.getCases.mockImplementation(ASKIDA);
    render();
    expect(iskelet()).not.toBeNull();
    expect(container.textContent).not.toContain("bulunamadı");
  });

  it("sayfaya geri dönüşte eldeki satırlar ANINDA çizilir; tazeleme sürerken iskelet yok, liste soluk değil", async () => {
    render();
    await waitFor(satirVar, "ilk satırlar");
    act(() => root!.unmount());

    casesApi.getCases.mockImplementation(ASKIDA);   // ikinci ziyaret: ağ yavaş
    casesApi.getCaseStats.mockImplementation(ASKIDA);
    render();
    expect(satirVar()).toBe(true);
    expect(iskelet()).toBeNull();
    const kap = container.querySelector("[aria-busy]")!;
    expect(kap.getAttribute("aria-busy")).toBe("true");          // tazeleme arkada sürüyor
    expect(kap.className).not.toContain("opacity-50");            // ama sessiz
  });

  it("filtre değişiminde eski satırlar yerinde ve soluk kalır, yenisi gelince yer değiştirir", async () => {
    render();
    await waitFor(satirVar, "ilk satırlar");

    let coz!: (v: unknown) => void;
    casesApi.getCases.mockImplementation(() => new Promise(r => { coz = r; }));
    const derdest = Array.from(container.querySelectorAll("button"))
      .find(b => b.textContent?.includes("Aktif (Derdest)"))!;
    act(() => { derdest.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await waitFor(() => casesApi.getCases.mock.calls.length >= 2, "filtreli istek");

    expect(satirVar()).toBe(true);
    expect(iskelet()).toBeNull();
    expect(container.querySelector("[aria-busy]")!.className).toContain("opacity-50");

    await act(async () => { coz({ cases: [kart(3, "2025/333")], total: 1 }); });
    await waitFor(() => container.textContent?.includes("2025/333") ?? false, "yeni satırlar");
    expect(satirVar()).toBe(false);
    expect(container.querySelector("[aria-busy]")!.className).not.toContain("opacity-50");
  });

  it("G002: liste hatası 'bulunamadı' görünümü değil hata şeridi verir", async () => {
    casesApi.getCases.mockImplementation(async () => { throw new Error("Dava listesi alınamadı — sunucuya ulaşılamadı."); });
    render();
    await waitFor(() => container.textContent?.includes("Dava listesi alınamadı") ?? false, "hata şeridi");
    expect(container.textContent).not.toContain("Bu kriterlere uygun dosya bulunamadı");
    expect(iskelet()).toBeNull();
  });
});
