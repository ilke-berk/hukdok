// @vitest-environment jsdom
// G253: hızlı dava modalında hizmet MÜVEKKİL BAŞINA seçilir — virgülle yazılan her müvekkil
// adı için bir `HizmetSecici` (gerçek bileşen, gerçek Radix Popover + cmdk), kayıtlı
// müvekkilin kategorisine göre ön seçim, "tüm müvekkillere uygula" kısayolu, hizmetsiz
// müvekkilde Kaydet kapalı, gönderimde taraf başına `hizmet_turleri`.
// Gerçek useConfig modülü + gerçek QueryClient (liste `/api/config/service_types`'tan gelir);
// ağ (authRequest), MSAL, dava/müvekkil hook'ları taklit edilir. Dialog ve Select düz DOM.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

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

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
const msal = vi.hoisted(() => ({ accounts: [{ username: "a@b.c" }] }));
vi.mock("@azure/msal-react", () => ({ useMsal: () => msal }));
const toastApi = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastApi }));
const casesApi = vi.hoisted(() => ({
  saveCaseAndReturn: vi.fn(),
  getOfisNoOnizleme: vi.fn(),
  checkDuplicateCase: vi.fn(),
  isLoading: false,
}));
vi.mock("@/hooks/useCases", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/useCases")>()),
  useCases: () => casesApi,
}));
// `clients` açılış effect'inin bağımlılığında — kimlik sabit. Hepsi kayıtlı müvekkil:
// "yeni müvekkil" onayı araya girmesin, ön seçim kategoriden okunabilsin.
const clientsApi = vi.hoisted(() => ({
  clients: [
    { id: 41, name: "Ahmet Yılmaz", category: "Doktor" },
    { id: 52, name: "Ayşe Gül", category: "Hasta" },
    { id: 63, name: "Özel Şifa Hastanesi", category: "Özel Hastane" },
  ],
  isLoading: false,
}));
vi.mock("@/hooks/useClients", () => ({ useClients: () => clientsApi }));
vi.mock("@/components/PartyMatchIndicator", () => ({ PartyMatchIndicator: () => null }));

type Kids = { children?: ReactNode };
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: Kids & { open: boolean }) => (open ? <div>{children}</div> : null),
  DialogContent: ({ children }: Kids) => <div>{children}</div>,
  DialogHeader: ({ children }: Kids) => <div>{children}</div>,
  DialogTitle: ({ children }: Kids) => <div>{children}</div>,
  DialogDescription: ({ children }: Kids) => <div>{children}</div>,
  DialogFooter: ({ children }: Kids) => <div>{children}</div>,
}));
vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: Kids) => <div>{children}</div>,
  SelectTrigger: ({ children }: Kids) => <div>{children}</div>,
  SelectValue: () => null,
  SelectContent: ({ children }: Kids) => <div>{children}</div>,
  SelectItem: ({ value, children }: Kids & { value: string }) => <div data-option={value}>{children}</div>,
}));

import { QuickCaseModal } from "./QuickCaseModal";

// Liste sırası (sequence) bilinçli olarak alfabetik DEĞİL — yayılan küme liste sırasındadır.
const SERVICE_TYPES = [
  { code: "TD", name: "Takip (doktor müvekkil)" },
  { code: "LR", name: "Lexis Rapor" },
  { code: "TH", name: "Takip (hasta vekilliği)" },
  { code: "DN", name: "Danışmanlık" },
];
const SERVICE_URL = "/api/config/service_types";

const bodies = (serviceTypes: unknown): Record<string, unknown> => ({
  "/api/config/lawyers": [],
  "/api/config/file_types": [{ code: "H", name: "Hukuk" }],
  "/api/config/court_types": [],
  "/api/config/required_case_fields": { fields: [], party_rule: null },
  [SERVICE_URL]: serviceTypes,
});

const DOKTOR = "Ahmet Yılmaz";
const HASTA = "Ayşe Gül";
const HASTANE = "Özel Şifa Hastanesi"; // kategorisi eşlemede yok → ön seçim yok
const noop = () => undefined;

type Party = { name: string; party_type: string; hizmet_turleri?: string[] };
type Payload = { parties: Party[] } & Record<string, unknown>;

describe("QuickCaseModal — müvekkil başına hizmet seçimi (G253)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  function ag(serviceTypes: unknown = SERVICE_TYPES) {
    const table = bodies(serviceTypes);
    authRequestMock.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => table[url] ?? [],
    }));
  }

  beforeEach(() => {
    vi.clearAllMocks();
    ag();
    casesApi.checkDuplicateCase.mockResolvedValue([]);
    casesApi.getOfisNoOnizleme.mockResolvedValue({ onizleme: "YIL-0041-DR.A.YILMAZ-HUK" });
    casesApi.saveCaseAndReturn.mockResolvedValue({ status: "success", id: 7, tracking_no: "YIL-0042-DR.A.YILMAZ-HUK" });
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    queryClient.clear();
    document.body.innerHTML = "";
  });

  function render(muvekkiller: string[], open = true) {
    // Prefill kimliği sabit kalsın diye çağıran aynı diziyi yeniden vermez; her render yeni prefill = yeniden açılış.
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <QuickCaseModal
          open={open}
          onClose={noop}
          prefill={{ muvekkiller, esas_no: "2026/15" }}
          onCaseCreated={noop}
        />
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

  const seciciler = () =>
    Array.from(container.querySelectorAll<HTMLButtonElement>('[role=combobox][aria-label$="için hizmetler"]'));
  const secici = (ad: string) =>
    container.querySelector<HTMLButtonElement>(`[role=combobox][aria-label="${ad} için hizmetler"]`);
  const cipler = (ad: string) =>
    Array.from(secici(ad)!.querySelectorAll("[data-testid=hizmet-secici-cip]")).map(c => c.textContent);
  const uyari = (ad: string) =>
    secici(ad)!.closest("[data-testid=muvekkil-hizmet]")!.querySelector("[data-testid=hizmet-eksik-uyarisi]");
  const tumuneUygula = () => container.querySelector<HTMLButtonElement>("[data-testid=hizmet-tumune-uygula]");
  const saveButton = () => Array.from(container.querySelectorAll("button"))
    .find(b => b.textContent?.includes("Davayı Aç ve Bağla"))!;
  const item = (hizmet: string) =>
    document.body.querySelector<HTMLElement>(`[cmdk-item][data-hizmet="${hizmet}"]`);
  const serviceCalls = () => authRequestMock.mock.calls.filter(([url]) => url === SERVICE_URL).length;
  const hizmetlerGeldi = (ad: string) => waitFor(() => secici(ad) !== null, "hizmet seçicisi çizildi");

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

  function typeClient(value: string): void {
    const input = container.querySelector<HTMLInputElement>('input[placeholder="Müvekkil adı"]')!;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    act(() => {
      setter.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  async function save(): Promise<Payload> {
    const before = casesApi.saveCaseAndReturn.mock.calls.length;
    await waitFor(() => !saveButton().disabled, "kaydet düğmesi hazır");
    await act(async () => { saveButton().click(); });
    await waitFor(() => casesApi.saveCaseAndReturn.mock.calls.length === before + 1, "kayıt isteği atıldı");
    await act(async () => { await Promise.resolve(); });
    return casesApi.saveCaseAndReturn.mock.calls[before][0] as Payload;
  }

  const muvekkilTaraflari = (payload: Payload) => payload.parties.filter(p => p.party_type === "CLIENT");

  it("kapalı modal hizmet listesini ÇEKMEZ (G185 sınırı); açılınca bir kez çeker — seçiciyle önbellek ortak", async () => {
    render([DOKTOR], false);
    await act(async () => { await new Promise(r => setTimeout(r, 100)); });
    expect(serviceCalls()).toBe(0);

    render([DOKTOR], true);
    await hizmetlerGeldi(DOKTOR);
    await act(async () => { await new Promise(r => setTimeout(r, 50)); });

    // Modalın sorgusu + her HizmetSecici'nin `useConfigList("serviceTypes")` aboneliği = TEK istek.
    expect(serviceCalls()).toBe(1);
  });

  it("her müvekkil adı için erişilebilir etiketli bir seçici çizilir; ad eklenince seçici de eklenir", async () => {
    render([DOKTOR]);
    await hizmetlerGeldi(DOKTOR);
    expect(seciciler().map(s => s.getAttribute("aria-label"))).toEqual([`${DOKTOR} için hizmetler`]);

    typeClient(`${DOKTOR}, ${HASTANE}`);

    expect(seciciler().map(s => s.getAttribute("aria-label"))).toEqual([
      `${DOKTOR} için hizmetler`,
      `${HASTANE} için hizmetler`,
    ]);
  });

  it("ön seçim kayıtlı müvekkilin kategorisinden gelir; bilgi yoksa ön seçim yok", async () => {
    render([DOKTOR, HASTA, HASTANE]);
    await hizmetlerGeldi(DOKTOR);

    expect(cipler(DOKTOR)).toEqual(["Takip (doktor müvekkil)"]);
    expect(cipler(HASTA)).toEqual(["Takip (hasta vekilliği)"]);
    expect(cipler(HASTANE)).toEqual([]);
  });

  it("hizmeti olmayan müvekkilde Kaydet kapalı + satırda uyarı; hizmet seçilince açılır ve yüke girer", async () => {
    render([HASTANE]);
    await hizmetlerGeldi(HASTANE);

    expect(saveButton().disabled).toBe(true);
    expect(uyari(HASTANE)?.textContent).toContain("Hizmet seçilmedi");

    hizmetDegistir(HASTANE, "Danışmanlık");

    expect(uyari(HASTANE)).toBeNull();
    expect(saveButton().disabled).toBe(false);

    const payload = await save();
    expect(muvekkilTaraflari(payload).map(p => [p.name, p.hizmet_turleri])).toEqual([[HASTANE, ["Danışmanlık"]]]);
    expect(payload).not.toHaveProperty("service_type");
  });

  it("iki müvekkil AYRI seçilir: gönderimde her taraf kendi hizmet_turleri kümesini taşır", async () => {
    render([DOKTOR, HASTANE]);
    await hizmetlerGeldi(DOKTOR);
    // Listede SONRA gelen önce tıklanır → küme yine liste sırasında gider.
    hizmetDegistir(HASTANE, "Danışmanlık", "Lexis Rapor");

    const payload = await save();
    expect(muvekkilTaraflari(payload).map(p => [p.name, p.hizmet_turleri])).toEqual([
      [DOKTOR, ["Takip (doktor müvekkil)"]],
      [HASTANE, ["Lexis Rapor", "Danışmanlık"]],
    ]);
    expect(toastApi.error).not.toHaveBeenCalled();
  });

  it("karşı taraf hizmet taşımaz (backend 422)", async () => {
    render([DOKTOR]);
    await hizmetlerGeldi(DOKTOR);
    const karsi = container.querySelector<HTMLInputElement>('input[placeholder="Karşı taraf adı (opsiyonel)"]')!;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    act(() => {
      setter.call(karsi, "Mehmet Kaya");
      karsi.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const payload = await save();
    const karsiTaraf = payload.parties.find(p => p.party_type === "COUNTER")!;
    expect(karsiTaraf.name).toBe("Mehmet Kaya");
    expect(karsiTaraf).not.toHaveProperty("hizmet_turleri");
  });

  it("'Aynı hizmetleri tüm müvekkillere uygula': tek müvekkilde yok; ilk DOLU kümeyi kopyalar, sonra tek tek değişir", async () => {
    render([DOKTOR]);
    await hizmetlerGeldi(DOKTOR);
    expect(tumuneUygula()).toBeNull();

    typeClient(`${HASTANE}, ${DOKTOR}, ${HASTA}`);
    expect(tumuneUygula()?.textContent).toContain("Aynı hizmetleri tüm müvekkillere uygula");
    expect(cipler(HASTANE)).toEqual([]);

    act(() => tumuneUygula()!.click());

    // İlk satır (hastane) boştu; ilk DOLU seçici Doktor ön seçimi.
    for (const ad of [HASTANE, DOKTOR, HASTA]) expect(cipler(ad)).toEqual(["Takip (doktor müvekkil)"]);

    hizmetDegistir(HASTA, "Danışmanlık");
    expect(cipler(HASTA)).toEqual(["Takip (doktor müvekkil)", "Danışmanlık"]);
    expect(cipler(HASTANE)).toEqual(["Takip (doktor müvekkil)"]);

    const payload = await save();
    expect(muvekkilTaraflari(payload).map(p => p.hizmet_turleri)).toEqual([
      ["Takip (doktor müvekkil)"],
      ["Takip (doktor müvekkil)"],
      ["Takip (doktor müvekkil)", "Danışmanlık"],
    ]);
  });

  it("hiçbir seçici dolu değilken kısayol devre dışıdır", async () => {
    render([HASTANE, "Yeni Kişi"]);
    await hizmetlerGeldi(HASTANE);

    expect(tumuneUygula()).not.toBeNull();
    expect(tumuneUygula()!.disabled).toBe(true);
    expect(saveButton().disabled).toBe(true);
  });

  it("ön seçim değiştirilebilir; kaldırılan ön seçim geri GELMEZ ve Kaydet kapanır", async () => {
    render([DOKTOR]);
    await hizmetlerGeldi(DOKTOR);
    expect(saveButton().disabled).toBe(false);

    hizmetDegistir(DOKTOR, "Takip (doktor müvekkil)"); // ön seçimi kaldır

    expect(cipler(DOKTOR)).toEqual([]);
    expect(saveButton().disabled).toBe(true);
    expect(uyari(DOKTOR)).not.toBeNull();
  });

  it("modal yeniden açılınca hizmet seçimleri sıfırlanır (ön seçime döner)", async () => {
    render([DOKTOR]);
    await hizmetlerGeldi(DOKTOR);
    hizmetDegistir(DOKTOR, "Danışmanlık");
    expect(cipler(DOKTOR)).toEqual(["Takip (doktor müvekkil)", "Danışmanlık"]);

    render([DOKTOR], false);
    render([DOKTOR], true);
    await hizmetlerGeldi(DOKTOR);

    expect(cipler(DOKTOR)).toEqual(["Takip (doktor müvekkil)"]);
  });

  it("sunucu 422 dönerse (hizmetsiz müvekkil) mesajı gösterilir", async () => {
    const mesaj = 'Hizmet türü seçilmemiş müvekkil var: "Ahmet Yılmaz". Her müvekkil için en az bir hizmet türü seçin.';
    casesApi.saveCaseAndReturn.mockResolvedValue({ error: mesaj });
    render([DOKTOR]);
    await hizmetlerGeldi(DOKTOR);

    await save();

    expect(toastApi.error).toHaveBeenCalledWith(mesaj);
    expect(toastApi.success).not.toHaveBeenCalled();
  });

  it("hizmet listesi BOŞKEN seçici çizilmez ve Kaydet kilitlenmez (backend ile aynı kural)", async () => {
    ag([]);
    render([HASTANE]);
    await waitFor(() => queryClient.getQueryState(["config", "service_types"])?.status === "success", "liste geldi");

    expect(container.querySelector("[data-testid=muvekkil-hizmet]")).toBeNull();
    const payload = await save();
    expect(muvekkilTaraflari(payload).map(p => p.hizmet_turleri)).toEqual([[]]);
  });

  it("hizmet listesi ALINAMAZSA hata şeridi görünür (hata ≠ boş liste)", async () => {
    authRequestMock.mockImplementation(async (url: string) => (
      url === SERVICE_URL
        ? { ok: false, json: async () => ({}) }
        : { ok: true, json: async () => bodies([])[url] ?? [] }
    ));
    render([HASTANE]);
    await waitFor(() => container.querySelector("[role=alert]") !== null, "hata şeridi çıktı");

    expect(container.querySelector("[role=alert]")?.textContent).toContain("Ayar listeleri alınamadı");
  });
});
