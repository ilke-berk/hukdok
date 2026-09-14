// @vitest-environment jsdom
// G186 (F5): DocCard eskiden CaseDetails'in render'ı içindeki IIFE'de tanımlıydı —
// her render'da YENİ bir bileşen türü doğuyor, React tüm belge kartlarını (ve
// içlerindeki müvekkil Select'lerini) unmount/mount ediyordu. Silme gerekçesi
// yazmak gibi ilgisiz bir state değişimi kartların DOM düğümlerini yeniden
// üretmemeli. Kurulum CaseDetails.config.test.tsx ile aynı desen.
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

// İki CLIENT taraf → belge kartında müvekkil atama Select'i basılır.
const CASE = vi.hoisted(() => ({
  id: 7,
  status: "DERDEST",
  tracking_no: "T-7",
  parties: [
    { id: 11, party_type: "CLIENT", name: "Ayşe Yılmaz", role: "Davacı" },
    { id: 12, party_type: "CLIENT", name: "Ali Demir", role: "Davacı" },
  ],
  documents: [
    {
      id: 101,
      created_at: "2026-09-01T10:00:00Z",
      document_type_code: "TEBLIGAT______",
      belge_turu_adi: "Tebligat",
      stored_filename: "tebligat-101.pdf",
      original_filename: "tebligat.pdf",
      case_party_id: null,
      email_sent: true,
    },
    {
      id: 102,
      created_at: "2026-09-02T10:00:00Z",
      document_type_code: "KARAR_________",
      belge_turu_adi: "Karar",
      stored_filename: "karar-102.pdf",
      original_filename: "karar.pdf",
      case_party_id: 11,
      case_party_name: "Ayşe Yılmaz",
      email_sent: true,
    },
  ],
}));
vi.mock("@/hooks/useCases", () => ({ useCases: () => ({ getCase: async () => CASE }) }));
vi.mock("@/lib/api", () => ({ apiClient: { fetch: async () => ({ ok: false, json: async () => ({}) }) } }));
vi.mock("@/components/RelatedCasesPanel", () => ({ default: () => null }));
vi.mock("@/components/CaseTrackingPanel", () => ({ default: () => null }));
vi.mock("@/components/CaseFoyPanel", () => ({ default: () => null }));
vi.mock("@/components/email/EmailModal", () => ({ EmailModal: () => null }));

import CaseDetails from "./CaseDetails";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("CaseDetails — DocCard kimliği (G186 F5)", () => {
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

  async function renderDocumentsTab(): Promise<void> {
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
    await waitFor(() => container.textContent?.includes("T-7") === true, "dava kartı basıldı");

    // Radix Tabs sekmeyi sol tuş mousedown'unda etkinleştirir.
    const tab = Array.from(container.querySelectorAll('[role="tab"]'))
      .find(el => el.getAttribute("id")?.endsWith("-trigger-documents"));
    expect(tab).toBeTruthy();
    act(() => {
      tab!.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
    });
    await waitFor(() => container.textContent?.includes("tebligat-101.pdf") === true, "evrak listesi basıldı");
  }

  const selectTriggers = () => Array.from(container.querySelectorAll('button[role="combobox"]'));

  function typeInto(el: HTMLTextAreaElement, value: string): void {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
    act(() => {
      setter.call(el, value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  it("silme gerekçesi yazılırken belge kartlarındaki Select DOM düğümleri AYNI kalır", async () => {
    await renderDocumentsTab();

    const before = selectTriggers();
    expect(before).toHaveLength(2);

    // Silme diyaloğunu aç (CaseDetails state'i değişir) ve gerekçe yaz.
    const trash = container.querySelector('button[title="Belgeyi sil"]') as HTMLButtonElement | null;
    expect(trash).toBeTruthy();
    act(() => trash!.click());

    const textarea = document.body.querySelector(
      'textarea[placeholder="Silme gerekçesi (zorunlu)…"]',
    ) as HTMLTextAreaElement | null;
    expect(textarea).toBeTruthy();
    typeInto(textarea!, "m");
    typeInto(textarea!, "mük");
    typeInto(textarea!, "mükerrer");
    expect(textarea!.value).toBe("mükerrer");

    const after = selectTriggers();
    expect(after).toHaveLength(2);
    expect(after[0]).toBe(before[0]);
    expect(after[1]).toBe(before[1]);
    expect(before[0].isConnected).toBe(true);
  });

  it("kart içeriği ve müvekkil seçimi korunur (davranış aynı)", async () => {
    await renderDocumentsTab();

    const text = container.textContent ?? "";
    expect(text).toContain("tebligat-101.pdf");
    expect(text).toContain("karar-102.pdf");
    // Dava geneli belgede "Tüm Dava", müvekkile atanmış belgede müvekkil adı seçili.
    const [caseWide, byParty] = selectTriggers();
    expect(caseWide.textContent).toContain("Tüm Dava");
    expect(byParty.textContent).toContain("Ayşe Yılmaz");
  });
});
