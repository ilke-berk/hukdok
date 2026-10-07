// @vitest-environment jsdom
// CaseDetails → Belge tezgâhı köprüsü (G273): belge satırındaki "PDF araçlarında aç" tek belgeyle, Evrak Listesi'ndeki
// çoklu seçim şeridi ("Seçilenleri PDF araçlarında birleştir") seçim SIRASIYLA `navigate("/belge-tezgahi", { state:
// { document_ids, case } })` yapar; arşivde olmayan (`sharepoint_url` boş) belge ne açılır ne seçilir. Kurulum
// CaseDetails.docCard.test.tsx deseni; `/belge-tezgahi` rotasına `location.state`'i basan bir sonda bağlanır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({ useAuthRequest: () => ({ authRequest: authRequestMock }) }));
const msal = vi.hoisted(() => ({ accounts: [{ username: "a@b.c" }] }));
vi.mock("@azure/msal-react", () => ({ useMsal: () => msal }));
vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const CASE = vi.hoisted(() => ({
  id: 7,
  status: "DERDEST",
  tracking_no: "T-7",
  esas_no: "2026/15",
  court: "İstanbul 3. ATM",
  parties: [{ id: 11, party_type: "CLIENT", name: "Ayşe Yılmaz", role: "Davacı" }],
  documents: [
    { id: 101, created_at: "2026-09-01T10:00:00Z", document_type_code: "TEBLIGAT______", belge_turu_adi: "Tebligat", stored_filename: "tebligat-101.pdf", original_filename: "tebligat.pdf", sharepoint_url: "https://sp/101", case_party_id: null, email_sent: true },
    { id: 102, created_at: "2026-09-02T10:00:00Z", document_type_code: "DILEKCE_______", belge_turu_adi: "Dilekçe", stored_filename: "bekleyen-102.pdf", original_filename: "bekleyen.pdf", case_party_id: null, email_sent: true },
    { id: 103, created_at: "2026-09-03T10:00:00Z", document_type_code: "KARAR_________", belge_turu_adi: "Karar", stored_filename: "karar-103.pdf", original_filename: "karar.pdf", sharepoint_url: "https://sp/103", case_party_id: 11, case_party_name: "Ayşe Yılmaz", email_sent: true },
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

function TezgahSondasi() {
  const { state } = useLocation();
  return <pre data-testid="tezgah-state">{JSON.stringify(state)}</pre>;
}

describe("CaseDetails → Belge tezgâhı (G273)", () => {
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
      await act(async () => {
        await new Promise((r) => setTimeout(r, 10));
      });
    }
    throw new Error(`Koşul sağlanmadı: ${label}`);
  }

  async function renderDocumentsTab(): Promise<void> {
    root = createRoot(container);
    act(() =>
      root!.render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/cases/7"]}>
            <Routes>
              <Route path="/cases/:id" element={<CaseDetails />} />
              <Route path="/belge-tezgahi" element={<TezgahSondasi />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      ),
    );
    // Başlık `esas_no || tracking_no` basar (CaseDetails.tsx:649) — kartta esas no var.
    await waitFor(() => container.textContent?.includes("2026/15") === true, "dava kartı basıldı");
    const tab = Array.from(container.querySelectorAll('[role="tab"]')).find((el) => el.getAttribute("id")?.endsWith("-trigger-documents"));
    expect(tab).toBeTruthy();
    act(() => {
      tab!.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
    });
    await waitFor(() => container.textContent?.includes("tebligat-101.pdf") === true, "evrak listesi basıldı");
  }

  const acDugmeleri = () => Array.from(container.querySelectorAll<HTMLButtonElement>("button")).filter((b) => b.textContent?.trim() === "PDF araçlarında aç");
  const secKutusu = (ad: string) => container.querySelector<HTMLInputElement>(`input[aria-label="Tezgâh için seç: ${ad}"]`)!;
  const sonda = () => {
    const el = container.querySelector('[data-testid="tezgah-state"]');
    return el ? JSON.parse(el.textContent || "null") : null;
  };
  const KART_OZETI = {
    id: 7,
    tracking_no: "T-7",
    esas_no: "2026/15",
    court: "İstanbul 3. ATM",
    status: "DERDEST",
    parties: [{ id: 11, party_type: "CLIENT", name: "Ayşe Yılmaz", role: "Davacı" }],
  };

  it("'PDF araçlarında aç' tek belgeyle /belge-tezgahi'ne state taşır; arşivde olmayan belgede kapalı", async () => {
    await renderDocumentsTab();
    const dugmeler = acDugmeleri();
    expect(dugmeler).toHaveLength(3);
    const bekleyen = dugmeler.find((b) => b.closest("div.group")?.textContent?.includes("bekleyen-102.pdf"))!;
    expect(bekleyen.disabled).toBe(true);
    expect(bekleyen.title).toContain("Arşivde yok");
    const tebligat = dugmeler.find((b) => b.closest("div.group")?.textContent?.includes("tebligat-101.pdf"))!;
    expect(tebligat.disabled).toBe(false);
    await act(async () => tebligat.click());
    await waitFor(() => sonda() !== null, "tezgâh rotasına geçildi");
    expect(sonda()).toEqual({ document_ids: [101], case: KART_OZETI });
  });

  it("çoklu seçim şeridi: seçim sırasıyla document_ids; URL'siz belge seçilemez; 'Seçimi temizle' şeridi kaldırır", async () => {
    await renderDocumentsTab();
    expect(container.querySelector('[data-testid="pdf-secim-seridi"]')).toBeNull();
    expect(secKutusu("bekleyen-102.pdf").disabled).toBe(true);
    await act(async () => secKutusu("karar-103.pdf").click());
    await act(async () => secKutusu("tebligat-101.pdf").click());
    const serit = container.querySelector('[data-testid="pdf-secim-seridi"]')!;
    expect(serit.textContent).toContain("2 belge seçili");

    const temizle = Array.from(serit.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === "Seçimi temizle")!;
    await act(async () => temizle.click());
    expect(container.querySelector('[data-testid="pdf-secim-seridi"]')).toBeNull();
    expect(secKutusu("karar-103.pdf").checked).toBe(false);

    await act(async () => secKutusu("karar-103.pdf").click());
    await act(async () => secKutusu("tebligat-101.pdf").click());
    const birlestir = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === "Seçilenleri PDF araçlarında birleştir")!;
    await act(async () => birlestir.click());
    await waitFor(() => sonda() !== null, "tezgâh rotasına geçildi");
    expect(sonda()).toEqual({ document_ids: [103, 101], case: KART_OZETI });
  });
});
