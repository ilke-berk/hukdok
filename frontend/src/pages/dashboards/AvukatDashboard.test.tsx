// @vitest-environment jsdom
// Avukat paneli dosya durumu kutuları (kullanıcı kararı 26.09.2026):
// Derdest · İstinafta · Temyizde · Arşiv. İstinaf/Temyiz backend'in
// `derdest_stages` sayacından (derdest dosyanın en ileri aşaması); Danış kutusu yok.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
const casesApi = vi.hoisted(() => ({
  getCases: async (): Promise<{ cases: unknown[]; total: number }> => ({ cases: [], total: 0 }),
  getCaseStats: async (): Promise<unknown> => ({
    total: 14383, active: 3050, closed: 11333, appeal: 26, danis_active: 0,
    statuses: { DERDEST: 3050, MAHZEN: 11333 },
    derdest_stages: { ISTINAF: 475, TEMYIZ: 261 },
  }),
}));
vi.mock("@/hooks/useCases", () => ({
  useCases: () => casesApi,
  CASE_LIST_ERROR: "Dava listesi alınamadı — sunucuya ulaşılamadı.",
}));
vi.mock("@/lib/api", () => ({ apiClient: { fetch: async () => ({ ok: true, json: async () => [] }) } }));
vi.mock("@/components/dashboard/DashboardCalendar", () => ({ DashboardCalendar: () => null }));
vi.mock("@/components/dashboard/RecentDocumentsPanel", () => ({ RecentDocumentsPanel: () => null }));
vi.mock("@/components/dashboard/DeadlineWarningsPanel", () => ({ DeadlineWarningsPanel: () => null }));

import AvukatDashboard from "./AvukatDashboard";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("AvukatDashboard — dosya durumu kutuları", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;
  const ciz = () =>
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><AvukatDashboard /></MemoryRouter>
      </QueryClientProvider>,
    ));

  beforeEach(() => {
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
  });

  it("Derdest · İstinafta · Temyizde · Arşiv sırasıyla sayıları basar", async () => {
    root = createRoot(container);
    ciz();
    for (let i = 0; i < 50 && !container.textContent?.includes("3050"); i++) {
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
    const section = container.querySelector("section")!;
    const kutular = Array.from(section.querySelectorAll("button")).map(b => b.textContent);
    expect(kutular).toHaveLength(4);
    expect(kutular[0]).toContain("Derdest");
    expect(kutular[0]).toContain("3050");
    expect(kutular[1]).toContain("İstinafta");
    expect(kutular[1]).toContain("475");
    expect(kutular[2]).toContain("Temyizde");
    expect(kutular[2]).toContain("261");
    expect(kutular[3]).toContain("Arşiv");
    expect(kutular[3]).toContain("11333");
    expect(section.textContent).not.toContain("Danış");
  });

  it("Faz 3: panele geri dönüşte önbellekteki sayılar ANINDA çizilir — tazeleme sürerken iskelet/— yok", async () => {
    root = createRoot(container);
    ciz();
    for (let i = 0; i < 50 && !container.textContent?.includes("3050"); i++) {
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
    act(() => root!.unmount());

    // İkinci ziyaret: sunucu hiç yanıt vermiyor (yavaş ağ) — yine de eldeki veri görünmeli.
    const orijinalStats = casesApi.getCaseStats;
    const orijinalCases = casesApi.getCases;
    casesApi.getCaseStats = () => new Promise(() => {});
    casesApi.getCases = () => new Promise(() => {});
    try {
      root = createRoot(container);
      ciz();
      const section = container.querySelector("section")!;
      const kutular = Array.from(section.querySelectorAll("button")).map(b => b.textContent ?? "");
      expect(kutular[0]).toContain("3050");
      expect(kutular[3]).toContain("11333");
      // Yükleme yer tutucusu ("—") hiçbir kutuda yok
      kutular.forEach(k => expect(k).not.toContain("—"));
      expect(container.querySelector("[role='status']")).toBeNull();
    } finally {
      casesApi.getCaseStats = orijinalStats;
      casesApi.getCases = orijinalCases;
    }
  });
});
