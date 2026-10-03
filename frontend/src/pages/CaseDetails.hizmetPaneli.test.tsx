// @vitest-environment jsdom
// G252: dava kartında Hizmetler paneli Büro Bilgileri'ndeki tek değerli "Hizmet Türü" satırının
// yerini alır. Gerçek CaseDetails + gerçek CaseHizmetPanel; ağ (`apiClient`, `authRequest`), MSAL,
// dava hook'u ve ağır çocuk paneller taklit edilir. Kilitlenenler: panel TARAFLAR sekmesinde (Genel
// Bilgiler'de değil — 03.10 kullanıcı geri bildirimi), kartın CLIENT taraflarıyla basılır (karşı
// taraf satır almaz), `GET /api/cases/{id}/hizmetler` çağrılır, Büro Bilgileri
// kartında "Hizmet Türü" satırı YOK ve açıklaması "…müvekkil tipi" ile biter.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
const msal = vi.hoisted(() => ({ accounts: [{ username: "a@b.c" }] }));
vi.mock("@azure/msal-react", () => ({ useMsal: () => msal }));
vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const CASE = vi.hoisted(() => ({
  id: 7,
  status: "DERDEST",
  tracking_no: "T-7",
  bureau_type: "Sigorta",
  muvekkil_tipi: "Doktor",
  hizmet_turu: "Danışmanlık ; Dava Takibi",
  parties: [
    { id: 11, party_type: "CLIENT", name: "Dr. Ayşe Kaya", role: "Davalı" },
    { id: 12, party_type: "CLIENT", name: "Özel Şifa Hastanesi", role: "Davalı" },
    { id: 13, party_type: "COUNTER", name: "Mehmet Hasta", role: "Davacı" },
  ],
  // Kart yanıtındaki hizmet satırları (get_case, G248) — müvekkil kartındaki özet buradan okunur.
  hizmetler: [
    { id: 1, case_party_id: 11, muvekkil_adi: "Dr. Ayşe Kaya", hizmet_turu: "Dava Takibi", kaynak: "foy", foy_id: 70, sistem_no: "S-100" },
    { id: 3, case_party_id: 11, muvekkil_adi: "Dr. Ayşe Kaya", hizmet_turu: "Dava Takibi", kaynak: "foy", foy_id: 71, sistem_no: "S-101" },
    { id: 2, case_party_id: 12, muvekkil_adi: "Özel Şifa Hastanesi", hizmet_turu: "Danışmanlık", kaynak: "elle", foy_id: null, sistem_no: null },
  ],
}));
vi.mock("@/hooks/useCases", () => ({ useCases: () => ({ getCase: async () => CASE }) }));

const HIZMETLER = [
  { id: 1, case_party_id: 11, muvekkil_adi: "Dr. Ayşe Kaya", hizmet_turu: "Dava Takibi", kaynak: "foy", foy_id: 70, sistem_no: "S-100" },
  { id: 2, case_party_id: 12, muvekkil_adi: "Özel Şifa Hastanesi", hizmet_turu: "Danışmanlık", kaynak: "elle", foy_id: null, sistem_no: null },
];
const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: apiFetchMock } }));
vi.mock("@/components/RelatedCasesPanel", () => ({ default: () => null }));
vi.mock("@/components/CaseTrackingPanel", () => ({ default: () => null }));
vi.mock("@/components/CaseFoyPanel", () => ({ default: () => null }));
vi.mock("@/components/CaseNotesPanel", () => ({ default: () => null }));
vi.mock("@/components/email/EmailModal", () => ({ EmailModal: () => null }));

import CaseDetails from "./CaseDetails";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SERVICE_TYPES = [{ code: "DT", name: "Dava Takibi" }, { code: "DN", name: "Danışmanlık" }];
const CLIENT_TYPES = [{ code: "DR", name: "Doktor" }];

describe("CaseDetails — Hizmetler paneli (G252)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    const bodies: Record<string, unknown> = {
      "/api/config/service_types": SERVICE_TYPES,
      "/api/config/client_types": CLIENT_TYPES,
    };
    authRequestMock.mockImplementation(async (url: string) => ({ ok: true, json: async () => bodies[url] ?? [] }));
    apiFetchMock.mockImplementation(async (yol: string) =>
      yol === "/api/cases/7/hizmetler"
        ? new Response(JSON.stringify(HIZMETLER), { status: 200, headers: { "Content-Type": "application/json" } })
        : new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
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
        <MemoryRouter initialEntries={["/cases/7"]}>
          <Routes>
            <Route path="/cases/:id" element={<CaseDetails />} />
          </Routes>
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
  const etiketVar = (label: string) =>
    Array.from(container.querySelectorAll("span")).some(el => ownText(el) === label);
  const qa = (testId: string) => Array.from(container.querySelectorAll<HTMLElement>(`[data-testid="${testId}"]`));

  /** Panel Taraflar sekmesindedir (03.10). Radix Tabs sekmeyi sol tuş mousedown'unda etkinleştirir. */
  async function taraflarSekmesiniAc(): Promise<void> {
    await waitFor(() => container.textContent?.includes("T-7") === true, "dava kartı basıldı");
    const tab = Array.from(container.querySelectorAll('[role="tab"]'))
      .find(el => el.getAttribute("id")?.endsWith("-trigger-parties"));
    expect(tab).toBeTruthy();
    act(() => {
      tab!.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
    });
  }

  it("panel Taraflar sekmesinde, kartın müvekkil (CLIENT) taraflarıyla basılır; karşı taraf satır almaz", async () => {
    render();
    await waitFor(() => etiketVar("Müvekkil Tipi"), "Genel Bilgiler basıldı");
    // Genel Bilgiler sekmesinde panel YOK — müvekkiller Taraflar'da listelenir, hizmetleri de orada.
    expect(qa("case-hizmet-panel")).toHaveLength(0);

    await taraflarSekmesiniAc();
    await waitFor(() => qa("case-hizmet-cip").length === 2, "hizmet çipleri basıldı");

    expect(apiFetchMock.mock.calls.map(([yol]) => yol)).toContain("/api/cases/7/hizmetler");
    expect(qa("case-hizmet-muvekkil-adi").map(e => e.textContent)).toEqual(["Dr. Ayşe Kaya", "Özel Şifa Hastanesi"]);
    expect(qa("case-hizmet-cip-adi").map(e => e.textContent)).toEqual(["Dava Takibi", "Danışmanlık"]);
    // Kartı açabilen düzenleyebilir: her müvekkilde "Hizmet ekle", 2 müvekkilde toplu uygulama.
    expect(qa("case-hizmet-sec")).toHaveLength(2);
    expect(qa("case-hizmet-toplu-ac")).toHaveLength(1);

    // Taraf kartları panelin ÜSTÜNDE kalır (karta tıklamak o tarafın belgelerine götürür — panel
    // kartları ekran dışına itmesin); müvekkil kartı hizmetlerini tekrarsız özetler, karşı taraf özetlemez.
    const taraflar = Array.from(container.querySelectorAll("h3, div"))
      .find(el => ownText(el) === "Taraf Bilgileri")!;
    const panel = qa("case-hizmet-panel")[0];
    expect(taraflar.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(qa("taraf-hizmetleri").map(e => e.textContent)).toEqual(["Dava Takibi", "Danışmanlık"]);
  });

  it("Büro Bilgileri kartında 'Hizmet Türü' satırı yok (çift gösterim olmaz); açıklama müvekkil tipiyle biter", async () => {
    render();
    await waitFor(() => etiketVar("Müvekkil Tipi"), "Büro Bilgileri kartı basıldı");

    expect(etiketVar("Büro Özel Türü")).toBe(true);
    expect(etiketVar("Hizmet Türü")).toBe(false);
    expect(container.textContent).toContain("İş kabulü, büro özel türü ve müvekkil tipi");
    expect(container.textContent).not.toContain("müvekkil tipi ve hizmet türü");
    // Türetilmiş özet metni ("A ; B") kartta ayrıca basılmaz — hizmetler yalnız panelde.
    expect(container.textContent).not.toContain("Danışmanlık ; Dava Takibi");

    // Taraflar sekmesine geçince de özet metni basılmaz; hizmetler çip olarak panelde.
    await taraflarSekmesiniAc();
    await waitFor(() => qa("case-hizmet-cip").length === 2, "hizmet çipleri basıldı");
    expect(container.textContent).not.toContain("Danışmanlık ; Dava Takibi");
  });
});
