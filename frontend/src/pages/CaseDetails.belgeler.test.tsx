// @vitest-environment jsdom
// CaseDetails "Belgeler": Gelen · Taslak · Giden alt filtresi (G283, plan §6 K11/K12). Kilitlenen davranışlar: üç filtre
// sayıları ve listeleri; seçim URL'de `?belgeler=` (varsayılan gelen yazılmaz, `?hata=` korunur; URL ile açılış);
// tür çipleri alt filtreyle birlikte; çip etiketleri (durum/yön/kaynak); taslak satırında e-posta + PDF tezgâhı eylemleri
// GİZLİ, "Word'de aç"/"Kesinleştir" yer tutucu, "N sürüm", silme kalır; kesin satırında "Kesinleşti:"; alanları olmayan
// eski yanıt GELEN/KESIN sayılır. Kurulum CaseDetails.docCard.test.tsx deseni.
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
vi.mock("@/hooks/useCases", () => ({ useCases: () => ({ getCase: async () => CASE }) }));
vi.mock("@/lib/api", () => ({ apiClient: { fetch: async () => ({ ok: false, json: async () => ({}) }) } }));
vi.mock("@/components/RelatedCasesPanel", () => ({ default: () => null }));
vi.mock("@/components/CaseTrackingPanel", () => ({ default: () => null }));
vi.mock("@/components/CaseFoyPanel", () => ({ default: () => null }));
vi.mock("@/components/email/EmailModal", () => ({ EmailModal: () => null }));

import CaseDetails from "./CaseDetails";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function UrlSondasi() {
  const { search } = useLocation();
  return <pre data-testid="url">{search}</pre>;
}

describe("CaseDetails — Belgeler: Gelen · Taslak · Giden (G283)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    authRequestMock.mockImplementation(async () => ({ ok: true, json: async () => [] }));
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    container = document.createElement("div");
    document.body.appendChild(container);
    CASE.documents = [
      belge(1, { yon: "GELEN", durum: "KESIN", kaynak: "BELGE_HATTI", belge_turu_adi: "Tebligat", document_type_code: "TEBLIGAT______" }),
      belge(2, { yon: "GELEN", durum: "KESIN", kaynak: "ARSIV_AKTARIM" }),
      belge(3, { yon: "GIDEN", durum: "KESIN", kaynak: "PDF_ARACLARI", kesinlesme_tarihi: "2026-10-07T09:30:00Z" }),
      belge(4, { yon: "GIDEN", durum: "TASLAK", kaynak: "WORD", surum_sayisi: 3, email_sent: false, sharepoint_url: "https://sp/4" }),
      belge(5, {}), // eski yanıt: yon/durum yok → gelen/kesin
    ];
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

  async function renderDocumentsTab(url = "/cases/7"): Promise<void> {
    root = createRoot(container);
    act(() =>
      root!.render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[url]}>
            <Routes>
              <Route
                path="/cases/:id"
                element={
                  <>
                    <CaseDetails />
                    <UrlSondasi />
                  </>
                }
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      ),
    );
    await waitFor(() => container.textContent?.includes("T-7") === true, "dava kartı basıldı");
    const tab = Array.from(container.querySelectorAll('[role="tab"]')).find((el) => el.getAttribute("id")?.endsWith("-trigger-documents"));
    expect(tab).toBeTruthy();
    act(() => {
      tab!.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
    });
    await waitFor(() => container.querySelector('[data-testid="belge-kume-filtresi"]') !== null, "evrak listesi basıldı");
  }

  const kumeDugmesi = (kume: string) => container.querySelector<HTMLButtonElement>(`[data-testid="belge-kume-filtresi"] button[data-kume="${kume}"]`)!;
  const satirlar = () => Array.from(container.querySelectorAll<HTMLDivElement>("div[data-belge-id]")).map((d) => Number(d.dataset.belgeId));
  const satir = (id: number) => container.querySelector<HTMLDivElement>(`div[data-belge-id="${id}"]`)!;
  const url = () => container.querySelector('[data-testid="url"]')!.textContent;
  const tikla = (el: HTMLElement) => act(async () => el.click());

  it("varsayılan Gelen; üç filtre sayı rozetli; listeler kümeye göre; URL yalnız gelen dışı için yazılır", async () => {
    await renderDocumentsTab();
    expect(kumeDugmesi("gelen").getAttribute("aria-pressed")).toBe("true");
    expect(kumeDugmesi("gelen").textContent).toBe("Gelen3");
    expect(kumeDugmesi("taslak").textContent).toBe("Taslak1");
    expect(kumeDugmesi("giden").textContent).toBe("Giden1");
    expect(satirlar()).toEqual([1, 2, 5]); // eski yanıt (5) gelen sayılır
    expect(url()).toBe("");

    await tikla(kumeDugmesi("giden"));
    expect(kumeDugmesi("giden").getAttribute("aria-pressed")).toBe("true");
    expect(satirlar()).toEqual([3]);
    expect(url()).toBe("?belgeler=giden");

    await tikla(kumeDugmesi("taslak"));
    expect(satirlar()).toEqual([4]);
    expect(url()).toBe("?belgeler=taslak");

    await tikla(kumeDugmesi("gelen"));
    expect(url()).toBe("");
  });

  it("URL ile açılış (?belgeler=giden) ve `?hata=` korunur; tür çipleri kümedeki türlerden", async () => {
    await renderDocumentsTab("/cases/7?hata=12&belgeler=giden");
    expect(kumeDugmesi("giden").getAttribute("aria-pressed")).toBe("true");
    expect(satirlar()).toEqual([3]);
    await tikla(kumeDugmesi("gelen"));
    expect(url()).toBe("?hata=12");
    // gelen kümesinde Tebligat (1) + Dilekçe (2, 5) → tür çipleri: Tümü 3, Dilekçe 2, Tebligat 1
    const cipler = Array.from(container.querySelectorAll<HTMLButtonElement>('[aria-label="Belge türüne göre süz"] button')).map((b) => b.textContent);
    expect(cipler).toEqual(["Tümü3", "Dilekçe2", "Tebligat1"]);
    await tikla(container.querySelector<HTMLButtonElement>('[aria-label="Belge türüne göre süz"] button:nth-child(3)')!);
    expect(satirlar()).toEqual([1]);
  });

  it("çip etiketleri: durum / yön / kaynak; kesin satırında 'Kesinleşti:'; eski yanıt Kesin · Gelen · Belge hattı", async () => {
    await renderDocumentsTab("/cases/7?belgeler=giden");
    const cip3 = satir(3).querySelector('[data-testid="belge-durum-cipi"]')!;
    expect(cip3.getAttribute("data-durum")).toBe("KESIN");
    expect(Array.from(cip3.querySelectorAll('[role="img"]')).map((e) => e.getAttribute("aria-label"))).toEqual(["Kesin", "Giden belge", "Kaynak: PDF tezgâhı"]);
    expect(satir(3).querySelector('[data-testid="belge-kesinlesme"]')!.textContent).toBe("Kesinleşti: 07.10.2026");
    expect(satir(3).querySelector('[data-testid="belge-surum-sayisi"]')).toBeNull();
    await tikla(kumeDugmesi("gelen"));
    const cip5 = satir(5).querySelector('[data-testid="belge-durum-cipi"]')!;
    expect(Array.from(cip5.querySelectorAll('[role="img"]')).map((e) => e.getAttribute("aria-label"))).toEqual(["Kesin", "Gelen belge", "Kaynak: Belge hattı (yükle → analiz → onay)"]);
    expect(satir(2).querySelector('[data-testid="belge-durum-cipi"]')!.getAttribute("data-kaynak")).toBe("ARSIV_AKTARIM");
  });

  it("taslak satırı: e-posta ve PDF tezgâhı eylemleri gizli, Word'de aç / Kesinleştir yer tutucu, '3 sürüm', silme kalır", async () => {
    await renderDocumentsTab("/cases/7?belgeler=taslak");
    const s = satir(4);
    expect(s.dataset.taslak).toBe("true");
    const dugmeler = Array.from(s.querySelectorAll<HTMLButtonElement>("button")).map((b) => [b.textContent?.trim(), b.disabled, b.title] as const);
    expect(dugmeler.map((d) => d[0])).toEqual(["Word'de aç", "Kesinleştir", "Detay / Görüntüle", ""]);
    expect(dugmeler[0][1]).toBe(true);
    expect(dugmeler[0][2]).toContain("Sonraki sürümde");
    expect(dugmeler[1][1]).toBe(true);
    expect(s.querySelector('button[title="Belgeyi sil"]')).not.toBeNull();
    expect(s.textContent).not.toContain("Tekrar Gönder");
    expect(s.textContent).not.toContain("PDF araçlarında aç");
    expect(s.querySelector('input[type="checkbox"]')).toBeNull();
    expect(s.querySelector('[data-testid="belge-surum-sayisi"]')!.textContent).toBe("3 sürüm");
    expect(s.querySelector('[data-testid="belge-durum-cipi"]')!.getAttribute("data-durum")).toBe("TASLAK");
    expect(s.textContent).toContain("Taslak");
    // kesin satırında eylemler yerinde
    await tikla(kumeDugmesi("gelen"));
    expect(satir(1).textContent).toContain("PDF araçlarında aç");
    expect(satir(1).querySelector('input[type="checkbox"]')).not.toBeNull();
  });

  it("kümede belge yoksa açıklama satırı", async () => {
    CASE.documents = [belge(1, { yon: "GELEN", durum: "KESIN" })];
    await renderDocumentsTab("/cases/7?belgeler=taslak");
    expect(container.querySelector('[data-testid="belge-kume-bos"]')!.textContent).toContain("taslak belge yok");
    expect(satirlar()).toEqual([]);
  });
});
