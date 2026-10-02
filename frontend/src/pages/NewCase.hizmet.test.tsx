// @vitest-environment jsdom
// G253: yeni dava formunda hizmet MÜVEKKİL BAŞINA seçilir — müvekkil satırı başına bir
// `HizmetSecici` (gerçek bileşen, gerçek Radix Popover + cmdk), kategoriye göre ön seçim,
// "tüm müvekkillere uygula" kısayolu, hizmetsiz müvekkilde Kaydet kapalı, gönderimde taraf
// başına `hizmet_turleri`. Eski "Hizmet Türü (Çoklu Seçim)" 5'li maskesi ekrandan kalktı.
// Müvekkiller forma taslak şeridindeki "Taslağı geri yükle" ile konur (NewCase.ofisNo deseni).
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
  clients: [
    { id: 41, name: "Ahmet Yılmaz", category: "Doktor" },
    { id: 52, name: "Ayşe Gül", category: "Hasta" },
    { id: 63, name: "Özel Şifa Hastanesi", category: "Özel Hastane" },
    { id: 74, name: "Devlet Hastanesi", category: "Kurum" },
  ],
}));
vi.mock("@/hooks/useClients", () => ({ useClients: () => clientsApi }));
const configApi = vi.hoisted(() => ({
  caseSubjects: [],
  lawyers: [],
  fileTypes: [{ code: "H", name: "Hukuk" }],
  courtTypesByParent: {},
  mainPartyRoles: [],
  thirdPartyRoles: [],
  bureauTypes: [],
  specialties: [],
  serviceTypes: [] as { code: string; name: string }[],
  requiredCaseFields: [],
  requiredPartyRule: null,
  configError: null,
  requiredFieldsError: null,
  refetchConfig: () => undefined,
  isRefetchingConfig: false,
}));
// Sayfa listeyi `useConfig()`'ten, `HizmetSecici` `useConfigList("serviceTypes")`'ten okur — aynı liste.
vi.mock("@/hooks/useConfig", () => ({
  useConfig: () => configApi,
  useConfigList: () => ({ data: configApi.serviceTypes, isLoading: false, isError: false, error: undefined }),
}));
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
import { EMPTY_NEW_CASE_FORM, newCaseDraftStore, type NewCaseDraftData, type NewCaseDraftParty } from "@/lib/newCaseDraft";
import type { EditModeCaseData } from "@/lib/newCasePayload";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
Element.prototype.scrollIntoView = function () { /* jsdom */ };
const globalWithRO = globalThis as { ResizeObserver?: unknown };
if (!globalWithRO.ResizeObserver) {
  globalWithRO.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Liste sırası (sequence) bilinçli olarak alfabetik DEĞİL — yayılan küme liste sırasındadır.
const SERVICE_TYPES = [
  { code: "TD", name: "Takip (doktor müvekkil)" },
  { code: "LR", name: "Lexis Rapor" },
  { code: "TH", name: "Takip (hasta vekilliği)" },
  { code: "TK", name: "Takip (kurum vekilliği)" },
  { code: "DN", name: "Danışmanlık" },
];

const DOKTOR = "Ahmet Yılmaz";
const HASTA = "Ayşe Gül";
const OZEL_HASTANE = "Özel Şifa Hastanesi"; // kategorisi eşlemede yok → ön seçim yok
const KURUM = "Devlet Hastanesi";

const muvekkil = (name: string, over: Partial<NewCaseDraftParty> = {}): NewCaseDraftParty =>
  ({ name, role: "Davalı", ...over });

const taslak = (clients: NewCaseDraftParty[]): NewCaseDraftData => ({
  caseStatus: "DERDEST",
  formData: { ...EMPTY_NEW_CASE_FORM, fileType: "Hukuk" },
  selectedLawyers: [],
  clients,
  counterParties: [{ name: "Mehmet Kaya", role: "Davacı" }],
  thirdParties: [],
  istekKimligi: "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a",
});

type Party = { name: string; party_type: string; hizmet_turleri?: string[] };
type Payload = { parties: Party[] } & Record<string, unknown>;

describe("NewCase — müvekkil başına hizmet seçimi (G253)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    configApi.serviceTypes = SERVICE_TYPES;
    casesApi.checkDuplicateCase.mockResolvedValue([]);
    casesApi.getOfisNoOnizleme.mockResolvedValue({ onizleme: "YIL-0041-DR.A.YILMAZ-HUK" });
    casesApi.saveCase.mockResolvedValue({ ok: true, id: 12, tracking_no: "YIL-0042-DR.A.YILMAZ-HUK", reused: false });
    casesApi.updateCase.mockResolvedValue({ ok: true });
    casesApi.getCase.mockResolvedValue(null);
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
    document.body.innerHTML = "";
  });

  function renderForm(editCase?: EditModeCaseData): void {
    root = createRoot(container);
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[{ pathname: "/new-case/form", state: editCase ? { case: editCase } : undefined }]}>
          <Routes>
            <Route path="/new-case/form" element={<NewCase />} />
            <Route path="/cases/:id" element={<div data-testid="dava-karti">Dava kartı sayfası</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ));
  }

  const button = (text: string) =>
    Array.from(container.querySelectorAll("button")).find(b => b.textContent?.includes(text));

  /** Taslağı diske koyar, formu açar, "Taslağı geri yükle" ile müvekkilleri forma alır. */
  function renderWithClients(clients: NewCaseDraftParty[]): void {
    newCaseDraftStore.save(taslak(clients));
    renderForm();
    expect(button("Taslağı geri yükle")).toBeDefined();
    act(() => button("Taslağı geri yükle")!.click());
  }

  async function waitFor(condition: () => boolean, label: string): Promise<void> {
    for (let i = 0; i < 200; i++) {
      if (condition()) return;
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
    throw new Error(`Koşul sağlanmadı: ${label}`);
  }

  const seciciler = () =>
    Array.from(container.querySelectorAll<HTMLButtonElement>('[role=combobox][aria-label$="için hizmetler"]'));
  const secici = (ad: string) =>
    container.querySelector<HTMLButtonElement>(`[role=combobox][aria-label="${ad} için hizmetler"]`);
  const cipler = (ad: string) =>
    Array.from(secici(ad)!.querySelectorAll("[data-testid=hizmet-secici-cip]")).map(c => c.textContent);
  const satir = (ad: string) => secici(ad)!.closest("[data-testid=muvekkil-hizmet]")!;
  const uyari = (ad: string) => satir(ad).querySelector("[data-testid=hizmet-eksik-uyarisi]");
  const kapi = () => container.querySelector("[data-testid=hizmet-eksik-kapisi]");
  const submitButton = () => container.querySelector<HTMLButtonElement>("button[type=submit]")!;
  const tumuneUygula = () => container.querySelector<HTMLButtonElement>("[data-testid=hizmet-tumune-uygula]");
  const item = (hizmet: string) =>
    document.body.querySelector<HTMLElement>(`[cmdk-item][data-hizmet="${hizmet}"]`);

  function tetikle(ad: string): void {
    act(() => {
      secici(ad)!.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, pointerType: "mouse" }));
      secici(ad)!.click();
    });
  }

  /** Müvekkilin seçicisini açar, verilen hizmetleri işaretler/kaldırır, seçiciyi kapatır. */
  function hizmetDegistir(ad: string, ...hizmetler: string[]): void {
    tetikle(ad);
    for (const hizmet of hizmetler) {
      expect(item(hizmet)).not.toBeNull();
      act(() => item(hizmet)!.click());
    }
    tetikle(ad);
    expect(document.body.querySelector("[cmdk-input]")).toBeNull();
  }

  async function submit(): Promise<Payload> {
    const before = casesApi.saveCase.mock.calls.length;
    await act(async () => { submitButton().click(); });
    await waitFor(() => casesApi.saveCase.mock.calls.length === before + 1, "kayıt isteği atıldı");
    await act(async () => { await Promise.resolve(); });
    return casesApi.saveCase.mock.calls[before][0] as Payload;
  }

  const muvekkilTaraflari = (payload: Payload) => payload.parties.filter(p => p.party_type === "CLIENT");

  it("eski 5'li 'Hizmet Türü (Çoklu Seçim)' maskesi ve 'dosya numarasının son bloğu' metni ekranda yok", () => {
    renderForm();

    expect(container.textContent).not.toContain("Hizmet Türü (Çoklu Seçim)");
    expect(container.textContent).not.toContain("son bloğuna");
    expect(container.querySelector("#service-0")).toBeNull();
    for (const eski of ["Rapor", "Dava", "İcra", "Yazışma"]) {
      expect(Array.from(container.querySelectorAll("label")).some(l => l.textContent?.trim() === eski)).toBe(false);
    }
  });

  it("müvekkil satırı başına erişilebilir etiketli bir seçici çizilir", () => {
    renderWithClients([muvekkil(DOKTOR), muvekkil(OZEL_HASTANE), muvekkil("")]);

    expect(seciciler().map(s => s.getAttribute("aria-label"))).toEqual([
      `${DOKTOR} için hizmetler`,
      `${OZEL_HASTANE} için hizmetler`,
      "3. müvekkil için hizmetler",
    ]);
    expect(container.querySelectorAll("[data-testid=muvekkil-hizmet]")).toHaveLength(3);
  });

  it("ön seçim müvekkilin kategorisinden gelir: Doktor / Hasta / Kurum; bilgi yoksa ön seçim yok", () => {
    renderWithClients([muvekkil(DOKTOR), muvekkil(HASTA), muvekkil(KURUM), muvekkil(OZEL_HASTANE), muvekkil("Yeni Kişi")]);

    expect(cipler(DOKTOR)).toEqual(["Takip (doktor müvekkil)"]);
    expect(cipler(HASTA)).toEqual(["Takip (hasta vekilliği)"]);
    expect(cipler(KURUM)).toEqual(["Takip (kurum vekilliği)"]);
    expect(cipler(OZEL_HASTANE)).toEqual([]);
    expect(cipler("Yeni Kişi")).toEqual([]);
  });

  it("hizmeti olmayan müvekkilde Kaydet kapalı + satırda uyarı; hizmet seçilince açılır", () => {
    renderWithClients([muvekkil(OZEL_HASTANE)]);

    expect(submitButton().disabled).toBe(true);
    expect(uyari(OZEL_HASTANE)?.textContent).toContain("Hizmet seçilmedi");
    expect(kapi()?.textContent).toContain(`Hizmet türü seçilmemiş müvekkil var: "${OZEL_HASTANE}"`);

    hizmetDegistir(OZEL_HASTANE, "Danışmanlık");

    expect(cipler(OZEL_HASTANE)).toEqual(["Danışmanlık"]);
    expect(submitButton().disabled).toBe(false);
    expect(uyari(OZEL_HASTANE)).toBeNull();
    expect(kapi()).toBeNull();
  });

  it("adı yazılmamış boş satır hizmet istemez (uyarı yok, Kaydet o satır yüzünden kapanmaz)", () => {
    renderWithClients([muvekkil(DOKTOR), muvekkil("")]);

    expect(uyari("2. müvekkil")).toBeNull();
    expect(submitButton().disabled).toBe(false);
  });

  it("iki müvekkil AYRI seçilir: gönderimde her taraf kendi hizmet_turleri kümesini taşır", async () => {
    renderWithClients([muvekkil(DOKTOR), muvekkil(OZEL_HASTANE)]);
    // Listede SONRA gelen önce tıklanır → küme yine liste sırasında gider.
    hizmetDegistir(OZEL_HASTANE, "Danışmanlık", "Lexis Rapor");

    expect(cipler(DOKTOR)).toEqual(["Takip (doktor müvekkil)"]);
    expect(cipler(OZEL_HASTANE)).toEqual(["Lexis Rapor", "Danışmanlık"]);

    const payload = await submit();
    expect(muvekkilTaraflari(payload).map(p => [p.name, p.hizmet_turleri])).toEqual([
      [DOKTOR, ["Takip (doktor müvekkil)"]],
      [OZEL_HASTANE, ["Lexis Rapor", "Danışmanlık"]],
    ]);
    // Karşı taraf hizmet taşımaz (backend 422); eski maske de gönderilmez.
    const karsi = payload.parties.find(p => p.party_type === "COUNTER")!;
    expect(karsi.name).toBe("Mehmet Kaya");
    expect(karsi).not.toHaveProperty("hizmet_turleri");
    expect(payload).not.toHaveProperty("service_type");
    expect(toastApi.error).not.toHaveBeenCalled();
  });

  it("ön seçim değiştirilebilir; kaldırılan ön seçim geri GELMEZ ve Kaydet kapanır", () => {
    renderWithClients([muvekkil(DOKTOR)]);
    expect(cipler(DOKTOR)).toEqual(["Takip (doktor müvekkil)"]);
    expect(submitButton().disabled).toBe(false);

    hizmetDegistir(DOKTOR, "Takip (doktor müvekkil)"); // ön seçimi kaldır

    expect(cipler(DOKTOR)).toEqual([]);
    expect(submitButton().disabled).toBe(true);
    expect(uyari(DOKTOR)).not.toBeNull();

    hizmetDegistir(DOKTOR, "Lexis Rapor");
    expect(cipler(DOKTOR)).toEqual(["Lexis Rapor"]);
    expect(submitButton().disabled).toBe(false);
  });

  it("'Aynı hizmetleri tüm müvekkillere uygula': tek müvekkilde yok; 2+ müvekkilde ilk DOLU kümeyi kopyalar", async () => {
    renderWithClients([muvekkil(OZEL_HASTANE), muvekkil(DOKTOR), muvekkil(HASTA)]);
    expect(tumuneUygula()?.textContent).toContain("Aynı hizmetleri tüm müvekkillere uygula");
    expect(tumuneUygula()!.disabled).toBe(false);
    // İlk satır boş; ilk DOLU seçici ikinci satır (Doktor ön seçimi).
    expect(cipler(OZEL_HASTANE)).toEqual([]);

    act(() => tumuneUygula()!.click());

    for (const ad of [OZEL_HASTANE, DOKTOR, HASTA]) expect(cipler(ad)).toEqual(["Takip (doktor müvekkil)"]);
    expect(submitButton().disabled).toBe(false);

    // Sonradan tek tek değiştirilebilir: yalnız o müvekkilin kümesi değişir.
    hizmetDegistir(HASTA, "Danışmanlık");
    expect(cipler(HASTA)).toEqual(["Takip (doktor müvekkil)", "Danışmanlık"]);
    expect(cipler(OZEL_HASTANE)).toEqual(["Takip (doktor müvekkil)"]);

    const payload = await submit();
    expect(muvekkilTaraflari(payload).map(p => p.hizmet_turleri)).toEqual([
      ["Takip (doktor müvekkil)"],
      ["Takip (doktor müvekkil)"],
      ["Takip (doktor müvekkil)", "Danışmanlık"],
    ]);
  });

  it("kısayol tek müvekkilde çizilmez; hiçbir seçici dolu değilken devre dışıdır", () => {
    renderWithClients([muvekkil(DOKTOR)]);
    expect(tumuneUygula()).toBeNull();

    act(() => root!.unmount());
    root = null;
    renderWithClients([muvekkil(OZEL_HASTANE), muvekkil("Yeni Kişi")]);
    expect(tumuneUygula()).not.toBeNull();
    expect(tumuneUygula()!.disabled).toBe(true);
  });

  it("taslak hizmet seçimini korur: seçim diske yazılır, geri yüklenince seçicide görünür", () => {
    renderWithClients([muvekkil(OZEL_HASTANE), muvekkil(DOKTOR)]);
    hizmetDegistir(OZEL_HASTANE, "Danışmanlık", "Lexis Rapor");

    act(() => root!.unmount()); // unmount bekleyen taslak yazımını diske indirir
    root = null;
    const saved = newCaseDraftStore.load()?.data;
    expect(saved?.clients.map(c => c.hizmet_turleri)).toEqual([["Lexis Rapor", "Danışmanlık"], undefined]);
    expect(saved?.formData).not.toHaveProperty("serviceType");

    renderForm();
    act(() => button("Taslağı geri yükle")!.click());
    expect(cipler(OZEL_HASTANE)).toEqual(["Lexis Rapor", "Danışmanlık"]);
    expect(cipler(DOKTOR)).toEqual(["Takip (doktor müvekkil)"]); // dokunulmamış satır: ön seçim
    expect(submitButton().disabled).toBe(false);
  });

  it("sunucu 422 dönerse (hizmetsiz müvekkil) mesajı gösterilir", async () => {
    const mesaj = 'Hizmet türü seçilmemiş müvekkil var: "Ahmet Yılmaz". Her müvekkil için en az bir hizmet türü seçin.';
    casesApi.saveCase.mockResolvedValue({ ok: false, error: mesaj });
    renderWithClients([muvekkil(DOKTOR)]);

    await submit();

    expect(toastApi.error).toHaveBeenCalledWith("Hata", expect.objectContaining({ description: mesaj }));
    // (Taslak geri yükleme kendi "başarı" bildirimini atar — kayıt başarı bildirimi atılmadı.)
    expect(toastApi.success).not.toHaveBeenCalledWith("Dava kartı veritabanına kaydedildi!", expect.anything());
  });

  it("düzenleme modunda seçici GİZLİ: PUT gövdesi hizmet taşımaz, kayıttaki eski maske korunur", async () => {
    const editCase: EditModeCaseData = {
      id: 42,
      tracking_no: "YIL-0042-DR.A.YILMAZ-HUK",
      status: "DERDEST",
      service_type: "01001",
      parties: [
        { party_type: "CLIENT", name: OZEL_HASTANE, role: "Davalı" },
        { party_type: "COUNTER", name: "Mehmet Kaya", role: "Davacı" },
      ],
      lawyers: [],
    };
    renderForm(editCase);

    expect(container.textContent).toContain("Dava Kartı Düzenle");
    expect(container.querySelector("[data-testid=muvekkil-hizmet]")).toBeNull();
    expect(seciciler()).toHaveLength(0);
    expect(tumuneUygula()).toBeNull();
    // Hizmeti olmayan müvekkil düzenlemeyi kilitlemez (kural yalnız oluşturma kapısı).
    expect(submitButton().disabled).toBe(false);

    await act(async () => { submitButton().click(); });
    await waitFor(() => casesApi.updateCase.mock.calls.length === 1, "güncelleme isteği atıldı");

    const [id, payload] = casesApi.updateCase.mock.calls[0] as [number, Payload];
    expect(id).toBe(42);
    expect(payload.service_type).toBe("01001");
    expect(muvekkilTaraflari(payload)).toHaveLength(1);
    expect(muvekkilTaraflari(payload)[0]).not.toHaveProperty("hizmet_turleri");
    expect(casesApi.saveCase).not.toHaveBeenCalled();
  });

  it("hizmet listesi BOŞKEN seçici çizilmez ve Kaydet kilitlenmez (backend ile aynı kural)", async () => {
    configApi.serviceTypes = [];
    renderWithClients([muvekkil(OZEL_HASTANE)]);

    expect(container.querySelector("[data-testid=muvekkil-hizmet]")).toBeNull();
    expect(submitButton().disabled).toBe(false);

    const payload = await submit();
    expect(muvekkilTaraflari(payload).map(p => p.hizmet_turleri)).toEqual([[]]);
  });
});
