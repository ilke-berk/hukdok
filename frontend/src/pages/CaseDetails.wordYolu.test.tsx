// @vitest-environment jsdom
// CaseDetails — Word yaşam döngüsü (G285, plan K13-K15): taslak satırında "Word'de aç" → `ms-word:ofe|u|<word_url>` +
// 1,5 sn'de açılmazsa "Word Online'da aç"; "Sürümler" → SurumPaneli; "Kesinleştir" → onay → `kesinlestir` → kart yenilenir
// + `?belgeler=giden`; kesin Word belgesinde "Yeni sürüm taslağı" → `yeni-surum-taslagi` → `?belgeler=taslak`; yeni
// taslak satırında "v2 (önceki: …)"; kesin satırda Word düğmesi yok, Word dışı kesinde "Yeni sürüm taslağı" yok;
// başlıktaki "Yeni belge" diyaloğu açar (kart ön-seçili). Kurulum CaseDetails.belgeler.test.tsx deseni; Dialog düz DOM.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({ useAuthRequest: () => ({ authRequest: authRequestMock }) }));
const msal = vi.hoisted(() => ({ accounts: [{ username: "a@b.c" }] }));
vi.mock("@azure/msal-react", () => ({ useMsal: () => msal }));
vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
const yasam = vi.hoisted(() => ({ kesinlestir: vi.fn(), yeniSurumTaslagi: vi.fn(), surumler: vi.fn(), surumKaydet: vi.fn(), yeniBelge: vi.fn() }));
vi.mock("@/lib/belgeYasamApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/belgeYasamApi")>()),
  ...yasam,
}));
type Kids = { children?: ReactNode; className?: string; "data-testid"?: string };
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: Kids & { open: boolean }) => (open ? <div>{children}</div> : null),
  DialogContent: ({ children, className, ...rest }: Kids) => (
    <div className={className} data-testid={rest["data-testid"]}>
      {children}
    </div>
  ),
  DialogHeader: ({ children }: Kids) => <div>{children}</div>,
  DialogTitle: ({ children }: Kids) => <div>{children}</div>,
  DialogDescription: ({ children }: Kids) => <div>{children}</div>,
  DialogFooter: ({ children }: Kids) => <div>{children}</div>,
}));

const belge = (id: number, ek: Record<string, unknown>) => ({
  id,
  created_at: "2026-09-01T10:00:00Z",
  document_type_code: "DILEKCE_______",
  belge_turu_adi: "Dilekçe",
  stored_filename: `belge-${id}.pdf`,
  original_filename: `belge-${id}.pdf`,
  sharepoint_url: `https://sp/${id}`,
  case_party_id: null,
  email_sent: true,
  ...ek,
});
const CASE = vi.hoisted(() => ({ id: 7, status: "DERDEST", tracking_no: "T-7", parties: [], documents: [] as Record<string, unknown>[] }));
const getCaseMock = vi.hoisted(() => vi.fn());
const searchCasesMock = vi.hoisted(() => vi.fn(async () => []));
vi.mock("@/hooks/useCases", () => ({ useCases: () => ({ getCase: getCaseMock, searchCases: searchCasesMock }) }));
vi.mock("@/lib/api", () => ({ apiClient: { fetch: async () => ({ ok: false, json: async () => ({}) }) } }));
vi.mock("@/components/RelatedCasesPanel", () => ({ default: () => null }));
vi.mock("@/components/CaseTrackingPanel", () => ({ default: () => null }));
vi.mock("@/components/CaseFoyPanel", () => ({ default: () => null }));
vi.mock("@/components/email/EmailModal", () => ({ EmailModal: () => null }));

import CaseDetails from "./CaseDetails";
import { WORD_ACILMA_BEKLEMESI_MS, tarayici } from "@/lib/belgeYasamApi";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function UrlSondasi() {
  const { search } = useLocation();
  return <pre data-testid="url">{search}</pre>;
}

describe("CaseDetails — Word yolu (G285)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;
  let git: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    authRequestMock.mockImplementation(async () => ({ ok: true, json: async () => [] }));
    getCaseMock.mockImplementation(async () => CASE);
    git = vi.spyOn(tarayici, "git").mockImplementation(() => undefined);
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    container = document.createElement("div");
    document.body.appendChild(container);
    CASE.documents = [
      belge(1, { yon: "GELEN", durum: "KESIN", kaynak: "BELGE_HATTI" }),
      belge(4, { yon: "GIDEN", durum: "TASLAK", kaynak: "WORD", surum_sayisi: 1, stored_filename: "Cevap.docx", word_url: "https://sp/03_TASLAKLAR/Cevap.docx" }),
      belge(6, { yon: "GIDEN", durum: "KESIN", kaynak: "WORD", stored_filename: "Istinaf.pdf", word_url: "https://sp/03_TASLAKLAR/Istinaf.docx", kesinlesme_tarihi: "2026-10-07T09:00:00Z" }),
      belge(8, { yon: "GIDEN", durum: "TASLAK", kaynak: "WORD", stored_filename: "Istinaf-v2.docx", word_url: "https://sp/03_TASLAKLAR/Istinaf-v2.docx", onceki_document_id: 6 }),
      belge(9, { yon: "GIDEN", durum: "KESIN", kaynak: "PDF_ARACLARI" }),
    ];
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    queryClient.clear();
    git.mockRestore();
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

  async function renderDocumentsTab(url: string): Promise<void> {
    root = createRoot(container);
    act(() =>
      root!.render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[url]}>
            <Routes>
              <Route path="/cases/:id" element={<><CaseDetails /><UrlSondasi /></>} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      ),
    );
    await waitFor(() => container.textContent?.includes("T-7") === true, "dava kartı basıldı");
    const tab = Array.from(container.querySelectorAll('[role="tab"]')).find((el) => el.getAttribute("id")?.endsWith("-trigger-documents"));
    act(() => {
      tab!.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
    });
    await waitFor(() => container.querySelector('[data-testid="belge-kume-filtresi"]') !== null, "evrak listesi basıldı");
  }

  const satir = (id: number) => container.querySelector<HTMLDivElement>(`div[data-belge-id="${id}"]`)!;
  const dugmeIn = (el: ParentNode, ad: string) => Array.from(el.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === ad);
  const url = () => container.querySelector('[data-testid="url"]')!.textContent;
  const tikla = (el: HTMLElement | undefined) => act(async () => el!.click());

  it("Word'de aç → ms-word bağlantısı; 1,5 sn sonra Word Online yedeği (word_url)", async () => {
    await renderDocumentsTab("/cases/7?belgeler=taslak");
    await tikla(dugmeIn(satir(4), "Word'de aç"));
    expect(git).toHaveBeenCalledWith("ms-word:ofe|u|https://sp/03_TASLAKLAR/Cevap.docx");
    expect(satir(4).querySelector('[data-testid="word-online-yedek"]')).toBeNull();
    await act(async () => {
      await new Promise((r) => setTimeout(r, WORD_ACILMA_BEKLEMESI_MS + 50));
    });
    const a = satir(4).querySelector<HTMLAnchorElement>('[data-testid="word-online-yedek"] a')!;
    expect(a.getAttribute("href")).toBe("https://sp/03_TASLAKLAR/Cevap.docx");
  });

  it("Sürümler → SurumPaneli (liste surumler'den)", async () => {
    yasam.surumler.mockResolvedValue([{ surum_no: 1, sha256: "abcdef0123", not: "ilk", olusturan_email: "a@b.c", olusturulma: null, kesin: false }]);
    await renderDocumentsTab("/cases/7?belgeler=taslak");
    const ac = dugmeIn(satir(4), "Sürümler")!;
    expect(ac.getAttribute("aria-expanded")).toBe("false");
    await tikla(ac);
    await waitFor(() => satir(4).querySelector('[data-testid="surum-listesi"]') !== null, "sürüm listesi");
    expect(yasam.surumler).toHaveBeenCalledWith(4);
    expect(satir(4).querySelector('[data-testid="surum-listesi"]')!.textContent).toContain("ilk");
  });

  it("Kesinleştir → onay → kesinlestir(id, uuid) → kart yenilenir + Giden sekmesi", async () => {
    yasam.kesinlestir.mockResolvedValue({ document_id: 4, reused: false });
    await renderDocumentsTab("/cases/7?belgeler=taslak");
    const cekimOnce = getCaseMock.mock.calls.length;
    await tikla(dugmeIn(satir(4), "Kesinleştir"));
    const onay = container.querySelector<HTMLElement>('[data-testid="kesinlestir-onayi"]')!;
    expect(onay.textContent).toContain("Cevap.docx");
    expect(onay.textContent).toContain("Word'de kaydettiğinizden emin olun.");
    await tikla(dugmeIn(onay, "Kesinleştir"));
    expect(yasam.kesinlestir).toHaveBeenCalledWith(4, expect.stringMatching(/^[0-9a-f-]{36}$/));
    expect(url()).toBe("?belgeler=giden");
    expect(container.querySelector('[data-testid="kesinlestir-onayi"]')).toBeNull();
    await waitFor(() => getCaseMock.mock.calls.length > cekimOnce, "kart yeniden çekildi");
  });

  it("kesin Word belgesi: 'Yeni sürüm taslağı' → onay → yeniSurumTaslagi → Taslak sekmesi; Word düğmesi yok; Word dışı kesinde yok", async () => {
    yasam.yeniSurumTaslagi.mockResolvedValue({ document_id: 10, reused: false, word_url: null, word_ac: null });
    await renderDocumentsTab("/cases/7?belgeler=giden");
    expect(dugmeIn(satir(6), "Word'de aç")).toBeUndefined();
    expect(dugmeIn(satir(9), "Yeni sürüm taslağı")).toBeUndefined();
    await tikla(dugmeIn(satir(6), "Yeni sürüm taslağı"));
    const onay = container.querySelector<HTMLElement>('[data-testid="yeni-surum-onayi"]')!;
    expect(onay.textContent).toContain("Istinaf.pdf");
    await tikla(dugmeIn(onay, "Yeni taslak aç"));
    expect(yasam.yeniSurumTaslagi).toHaveBeenCalledWith(6, expect.stringMatching(/^[0-9a-f-]{36}$/));
    expect(url()).toBe("?belgeler=taslak");
  });

  it("yeni sürüm taslağı satırı: 'v2 (önceki: …)'; bağsız taslakta etiket yok", async () => {
    await renderDocumentsTab("/cases/7?belgeler=taslak");
    expect(satir(8).querySelector('[data-testid="belge-surum-zinciri"]')!.textContent).toBe("v2 (önceki: Istinaf.pdf)");
    expect(satir(4).querySelector('[data-testid="belge-surum-zinciri"]')).toBeNull();
  });

  it("başlıktaki 'Yeni belge' diyaloğu açar (kart ön-seçili, arama yok)", async () => {
    await renderDocumentsTab("/cases/7");
    expect(container.querySelector('[data-testid="yeni-belge-diyalogu"]')).toBeNull();
    await tikla(dugmeIn(container, "Yeni belge"));
    const d = container.querySelector<HTMLElement>('[data-testid="yeni-belge-diyalogu"]')!;
    expect(d.querySelector('[data-testid="secili-kart"]')!.textContent).toContain("T-7");
    expect(d.querySelector('input[aria-label="Dava ara"]')).toBeNull();
  });
});
