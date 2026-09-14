// @vitest-environment jsdom
// G185: CaseDetails yalnız kartın okuduğu altı kapalı listeye abone olur —
// useConfig() 32 `/api/config/*` ucu çağırıyordu. Gerçek useConfig modülü + gerçek
// QueryClient; ağ (authRequest), MSAL, dava hook'u ve kendi config aboneliği olan
// ağır çocuk paneller (takip paneli, e-posta modalı) taklit edilir.
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

// Olay türü değeri bilinçli olarak HİZMET türü listesindeki bir ad: listeler kart
// anahtarlarına ters bağlansaydı iki rozetin damgası yer değiştirirdi.
const CASE = vi.hoisted(() => ({
  id: 7,
  status: "DERDEST",
  tracking_no: "T-7",
  olay_turu: "Dava Takibi",
  hizmet_turu: "Dava Takibi",
}));
vi.mock("@/hooks/useCases", () => ({ useCases: () => ({ getCase: async () => CASE }) }));
vi.mock("@/lib/api", () => ({ apiClient: { fetch: async () => ({ ok: false, json: async () => ({}) }) } }));
vi.mock("@/components/RelatedCasesPanel", () => ({ default: () => null }));
vi.mock("@/components/CaseTrackingPanel", () => ({ default: () => null }));
vi.mock("@/components/CaseFoyPanel", () => ({ default: () => null }));
vi.mock("@/components/email/EmailModal", () => ({ EmailModal: () => null }));

import CaseDetails from "./CaseDetails";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const EVENT_TYPES = [{ code: "TO", name: "Tıbbi Olay" }];
const SERVICE_TYPES = [{ code: "DT", name: "Dava Takibi" }];
const OFF_LIST_TITLE = "Bu değer kapalı listede yok — aktarımdan gelmiş olabilir";
const CLOSED_LIST_KEYS = [
  "alleged_faults", "appealing_parties", "event_types", "judgment_roles", "client_types", "service_types",
];

const configUrls = (): string[] =>
  authRequestMock.mock.calls
    .map(([url]) => url as string)
    .filter(u => u.startsWith("/api/config/"))
    .sort();

describe("CaseDetails — config aboneliği (G185)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    const bodies: Record<string, unknown> = {
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

  async function flush(): Promise<void> {
    for (let i = 0; i < 5; i++) {
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
  }

  const listsLoaded = () =>
    CLOSED_LIST_KEYS.every(k => queryClient.getQueryState(["config", k])?.status === "success");

  const ownText = (el: Element) =>
    Array.from(el.childNodes)
      .filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent ?? "")
      .join("")
      .trim();

  /** Kart alanının rozeti: etiket span'iyle aynı sarmalayıcıdaki son öğe. */
  function badgeFor(label: string): Element | null {
    const labelEl = Array.from(container.querySelectorAll("span")).find(el => ownText(el) === label);
    return labelEl?.parentElement?.lastElementChild ?? null;
  }

  it("monte edilince yalnız altı kapalı liste ucu çağrılır (useConfig 32 uç çağırıyordu)", async () => {
    render();
    await waitFor(() => container.textContent?.includes("T-7") === true, "dava kartı basıldı");
    await waitFor(listsLoaded, "altı liste yüklendi");
    await flush();

    expect(configUrls()).toEqual(CLOSED_LIST_KEYS.map(k => `/api/config/${k}`).sort());
  });

  it("kapalı liste rozetleri doğru listeye bağlı: liste dışı değer damgalanır, listedeki değer damgasız", async () => {
    render();
    await waitFor(listsLoaded, "altı liste yüklendi");
    await waitFor(() => badgeFor("Olay Türü") !== null && badgeFor("Hizmet Türü") !== null, "rozetler basıldı");
    await flush();

    const olay = badgeFor("Olay Türü")!;
    const hizmet = badgeFor("Hizmet Türü")!;
    expect(olay.textContent).toBe("Dava Takibi");
    expect(hizmet.textContent).toBe("Dava Takibi");
    // event_types "Dava Takibi"ni içermez → liste dışı; service_types içerir → damgasız.
    expect(olay.getAttribute("title")).toBe(OFF_LIST_TITLE);
    expect(hizmet.getAttribute("title")).toBeNull();
  });
});
