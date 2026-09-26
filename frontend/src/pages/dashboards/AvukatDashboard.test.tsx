// @vitest-environment jsdom
// Avukat paneli dosya durumu kutuları (kullanıcı kararı 26.09.2026):
// Derdest · İstinafta · Temyizde · Arşiv. İstinaf/Temyiz backend'in
// `derdest_stages` sayacından (derdest dosyanın en ileri aşaması); Danış kutusu yok.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
const casesApi = vi.hoisted(() => ({
  getCases: async () => ({ cases: [], total: 0 }),
  getCaseStats: async () => ({
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

  beforeEach(() => {
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
    act(() => root!.render(<MemoryRouter><AvukatDashboard /></MemoryRouter>));
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
});
