// @vitest-environment jsdom
// G237: yeni dava formu ofis numarasını ÜRETMEZ — sunucudan önizler, kayıt yanıtındaki
// gerçek numarayı gösterir (karar 023). Kayıt isteği `tracking_no` taşımaz, tekrar
// korumalı `istek_kimligi` taşır.
// Müvekkil, taslak şeridindeki "Taslağı geri yükle" ile forma konur (combobox'ı sürmek
// yerine): böylece "taslak geri yüklemede taslağın kimliği" yolu da aynı kurulumla sınanır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
const toastApi = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastApi }));
// Kimlikler sabit: `dbClients` önizleme sorgusunun bağımlılığında.
const clientsApi = vi.hoisted(() => ({
  clients: [{ id: 41, name: "Ahmet Yılmaz", category: "Doktor" }],
}));
vi.mock("@/hooks/useClients", () => ({ useClients: () => clientsApi }));
const configApi = vi.hoisted(() => ({
  caseSubjects: [],
  lawyers: [],
  fileTypes: [{ code: "H", name: "Hukuk" }, { code: "C", name: "Ceza" }],
  courtTypesByParent: {},
  mainPartyRoles: [],
  thirdPartyRoles: [],
  bureauTypes: [],
  specialties: [],
  requiredCaseFields: [],
  requiredPartyRule: null,
  configError: null,
  requiredFieldsError: null,
  refetchConfig: () => undefined,
  isRefetchingConfig: false,
}));
vi.mock("@/hooks/useConfig", () => ({ useConfig: () => configApi }));
const casesApi = vi.hoisted(() => ({
  saveCase: vi.fn(),
  updateCase: vi.fn(),
  deleteCase: vi.fn(),
  getCase: vi.fn(),
  checkDuplicateCase: vi.fn(),
  getOfisNoOnizleme: vi.fn(),
  isLoading: false,
}));
vi.mock("@/hooks/useCases", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/useCases")>()),
  useCases: () => casesApi,
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiClient: { fetch: async () => ({ ok: false, json: async () => ({}) }) },
}));
vi.mock("@/components/PartyMatchIndicator", () => ({ PartyMatchIndicator: () => null }));

import NewCase from "./NewCase";
import { CASE_ALREADY_SAVED_MESSAGE, OFIS_NO_ONIZLEME_ERROR } from "@/hooks/useCases";
import { EMPTY_NEW_CASE_FORM, newCaseDraftStore, type NewCaseDraftData } from "@/lib/newCaseDraft";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const globalWithRO = globalThis as { ResizeObserver?: unknown };
if (!globalWithRO.ResizeObserver) {
  globalWithRO.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

const TASLAK_KIMLIGI = "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a";
const SUNUCU_NO = "YIL-0042-DR.A.YILMAZ-HUK";
const ONIZLEME_NO = "YIL-0041-DR.A.YILMAZ-HUK";
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const taslak = (over: Partial<NewCaseDraftData> = {}): NewCaseDraftData => ({
  caseStatus: "DERDEST",
  formData: { ...EMPTY_NEW_CASE_FORM, fileType: "Hukuk" },
  selectedLawyers: [],
  clients: [{ name: "Ahmet Yılmaz", role: "Davacı" }],
  counterParties: [{ name: "", role: "Davalı" }],
  thirdParties: [],
  istekKimligi: TASLAK_KIMLIGI,
  ...over,
});

type Payload = Record<string, unknown>;

describe("NewCase — ofis numarası önizlenir, üretilmez (G237)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    casesApi.checkDuplicateCase.mockResolvedValue([]);
    casesApi.getOfisNoOnizleme.mockResolvedValue({ onizleme: ONIZLEME_NO });
    casesApi.saveCase.mockResolvedValue({ ok: true, id: 12, tracking_no: SUNUCU_NO, reused: false });
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
    sessionStorage.clear();
  });

  function renderNew(): void {
    root = createRoot(container);
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/new-case/form"]}>
          <Routes>
            <Route path="/new-case/form" element={<NewCase />} />
            <Route path="/cases/:id" element={<div data-testid="dava-karti">Dava kartı sayfası</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ));
  }

  async function waitFor(condition: () => boolean, label: string): Promise<void> {
    for (let i = 0; i < 200; i++) {
      if (condition()) return;
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
    throw new Error(`Koşul sağlanmadı: ${label}`);
  }

  const button = (text: string) =>
    Array.from(container.querySelectorAll("button")).find(b => b.textContent?.includes(text));
  const ofisNo = () => container.querySelector("[data-testid=ofis-no]");
  const payloadOf = (call: number) => casesApi.saveCase.mock.calls[call][0] as Payload;

  /** Taslağı diske koyar, formu açar, "Taslağı geri yükle" ile müvekkili forma alır. */
  async function renderWithClient(over: Partial<NewCaseDraftData> = {}): Promise<void> {
    newCaseDraftStore.save(taslak(over));
    renderNew();
    expect(button("Taslağı geri yükle")).toBeDefined();
    act(() => button("Taslağı geri yükle")!.click());
  }

  /** Kontrollü React input'una yazar (native setter + input olayı). */
  function typeEsasNo(value: string): void {
    const input = container.querySelector<HTMLInputElement>('input[placeholder="Örn. 2026/123"]')!;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    act(() => {
      setter.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  async function submit(): Promise<void> {
    const before = casesApi.saveCase.mock.calls.length;
    await act(async () => { container.querySelector<HTMLButtonElement>("button[type=submit]")!.click(); });
    await waitFor(() => casesApi.saveCase.mock.calls.length === before + 1, "kayıt isteği atıldı");
    await act(async () => { await Promise.resolve(); });
  }

  it("boş formda numara üretilmez: önizleme istenmez, yer tutucu numara basılmaz", async () => {
    renderNew();
    await act(async () => { await new Promise(r => setTimeout(r, 450)); });

    expect(casesApi.getOfisNoOnizleme).not.toHaveBeenCalled();
    expect(ofisNo()?.getAttribute("data-durum")).toBe("onizleme");
    expect(ofisNo()?.textContent).toBe("Müvekkil seçilince gösterilir");
    expect(container.textContent).not.toContain("XXXXXXXXXX");
    expect(container.textContent).not.toMatch(/X1\.|\.HUKUK\.00000/);
  });

  it("müvekkil gelince önizleme sunucudan istenir (kayıtlı müvekkil id'siyle) ve gösterilir", async () => {
    await renderWithClient();
    await waitFor(() => ofisNo()?.textContent === ONIZLEME_NO, "önizleme göründü");

    expect(casesApi.getOfisNoOnizleme).toHaveBeenCalledTimes(1);
    expect(casesApi.getOfisNoOnizleme).toHaveBeenCalledWith("muvekkiller=41&file_type=Hukuk");
    expect(ofisNo()?.getAttribute("data-durum")).toBe("onizleme");
    expect(container.textContent).toContain("Kaydedince verilecek numaranın önizlemesidir");
  });

  it("kayıt isteği tracking_no TAŞIMAZ; kayıttan sonra ekranda SUNUCUNUN numarası görünür", async () => {
    await renderWithClient();
    await waitFor(() => ofisNo()?.textContent === ONIZLEME_NO, "önizleme göründü");
    await submit();
    await waitFor(() => ofisNo()?.textContent === SUNUCU_NO, "sunucunun numarası göründü");

    expect(payloadOf(0)).not.toHaveProperty("tracking_no");
    expect(JSON.stringify(payloadOf(0))).not.toContain(ONIZLEME_NO);
    expect(ofisNo()?.getAttribute("data-durum")).toBe("kaydedildi");
    expect(toastApi.success).toHaveBeenCalledWith(
      "Dava kartı veritabanına kaydedildi!",
      expect.objectContaining({ description: expect.stringContaining(SUNUCU_NO) }),
    );
  });

  it("önizleme alınamasa da kayıt yapılır; hata yalnız bilgi olarak görünür", async () => {
    casesApi.getOfisNoOnizleme.mockRejectedValue(new Error(OFIS_NO_ONIZLEME_ERROR));
    await renderWithClient();
    await waitFor(
      () => container.querySelector("[data-testid=ofis-no-onizleme-hatasi]") !== null,
      "önizleme hatası göründü",
    );
    expect(container.querySelector("[data-testid=ofis-no-onizleme-hatasi]")?.textContent).toBe(OFIS_NO_ONIZLEME_ERROR);
    expect(container.querySelector<HTMLButtonElement>("button[type=submit]")!.disabled).toBe(false);

    await submit();
    await waitFor(() => ofisNo()?.textContent === SUNUCU_NO, "sunucunun numarası göründü");

    expect(casesApi.saveCase).toHaveBeenCalledTimes(1);
    expect(toastApi.error).not.toHaveBeenCalled();
    expect(container.querySelector("[data-testid=ofis-no-onizleme-hatasi]")).toBeNull();
  });

  it("taslak geri yüklenince istek TASLAĞIN kimliğiyle gider", async () => {
    await renderWithClient();
    await submit();

    expect(payloadOf(0).istek_kimligi).toBe(TASLAK_KIMLIGI);
  });

  it("eski (kimliksiz) taslak geri yüklenince yeni bir UUID üretilir", async () => {
    await renderWithClient({ istekKimligi: undefined });
    await submit();

    expect(payloadOf(0).istek_kimligi).toMatch(UUID_V4);
    expect(payloadOf(0).istek_kimligi).not.toBe(TASLAK_KIMLIGI);
  });

  it("hata sonrası yeniden denemede kimlik AYNI kalır; başarıdan sonra yenilenir", async () => {
    casesApi.saveCase.mockResolvedValueOnce({ ok: false, error: "Sunucu hatası" });
    await renderWithClient();
    await submit(); // 1: hata
    await submit(); // 2: aynı formun tekrarı — başarılı
    await waitFor(() => ofisNo()?.textContent === SUNUCU_NO, "kayıt tamamlandı");
    await submit(); // 3: başarı sonrası yeni kayıt

    expect(payloadOf(0).istek_kimligi).toBe(TASLAK_KIMLIGI);
    expect(payloadOf(1).istek_kimligi).toBe(TASLAK_KIMLIGI);
    expect(payloadOf(2).istek_kimligi).not.toBe(TASLAK_KIMLIGI);
    expect(String(payloadOf(2).istek_kimligi)).toHaveLength(36);
    expect(toastApi.error).toHaveBeenCalledTimes(1);
  });

  it("'Vazgeç' (formu temizle) sonrası kimlik yenilenir ve numara gösterimi sıfırlanır", async () => {
    await renderWithClient();
    await waitFor(() => ofisNo()?.textContent === ONIZLEME_NO, "önizleme göründü");

    act(() => button("Vazgeç")!.click());
    await waitFor(() => ofisNo()?.textContent === "Müvekkil seçilince gösterilir", "önizleme kapandı");
    expect(container.textContent).not.toMatch(/2024\/\d{4}/); // eski rastgele `2024/NNNN` numarası yok

    // Temizlenen form yeni bir kayıttır: sonraki taslak yazımı YENİ kimliği taşır.
    typeEsasNo("2026/9");
    act(() => root!.unmount()); // unmount bekleyen taslak yazımını diske indirir
    root = null;
    const saved = newCaseDraftStore.load();
    expect(saved?.data.formData.esasNo).toBe("2026/9");
    expect(saved?.data.istekKimligi).toMatch(UUID_V4);
    expect(saved?.data.istekKimligi).not.toBe(TASLAK_KIMLIGI);
  });

  it("temizlenmeyen formda taslak, geri yüklenen kimliği taşımaya devam eder", async () => {
    await renderWithClient();
    typeEsasNo("2026/9");
    act(() => root!.unmount());
    root = null;

    const saved = newCaseDraftStore.load();
    expect(saved?.data.formData.esasNo).toBe("2026/9");
    expect(saved?.data.istekKimligi).toBe(TASLAK_KIMLIGI);
    expect(JSON.stringify(saved)).not.toContain("tracking");
  });

  it("reused: true yanıtında ikinci 'kaydedildi' akışı yerine mevcut karta gidilir", async () => {
    casesApi.saveCase.mockResolvedValue({ ok: true, id: 12, tracking_no: SUNUCU_NO, reused: true });
    await renderWithClient();
    await submit();
    await waitFor(() => container.querySelector("[data-testid=dava-karti]") !== null, "dava kartına gidildi");

    expect(toastApi.info).toHaveBeenCalledWith(
      CASE_ALREADY_SAVED_MESSAGE,
      expect.objectContaining({ description: expect.stringContaining(SUNUCU_NO) }),
    );
    expect(toastApi.success).not.toHaveBeenCalledWith("Dava kartı veritabanına kaydedildi!", expect.anything());
    expect(container.querySelector("button[type=submit]")).toBeNull();
  });
});
