// @vitest-environment jsdom
// G237: hızlı dava modalı ofis numarası ÜRETMEZ — sunucudan önizler, kayıt isteğinde
// `tracking_no` göndermez, tekrar korumalı `istek_kimligi` gönderir; başarıda yanıttaki
// (sunucunun verdiği) numarayı kullanır (karar 023).
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
// `clients` açılış effect'inin bağımlılığında — kimlik sabit. Kayıtlı müvekkil:
// "yeni müvekkil" onayı araya girmesin ve önizlemeye kayıt id'si gitsin.
const clientsApi = vi.hoisted(() => ({
  clients: [{ id: 41, name: "Ahmet Yılmaz" }, { id: 52, name: "Ayşe Gül" }],
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
import { CASE_ALREADY_SAVED_MESSAGE, OFIS_NO_ONIZLEME_ERROR } from "@/hooks/useCases";

const BODIES: Record<string, unknown> = {
  "/api/config/lawyers": [],
  "/api/config/file_types": [{ code: "H", name: "Hukuk" }],
  "/api/config/court_types": [],
  "/api/config/required_case_fields": { fields: [], party_rule: null },
};

const SUNUCU_NO = "YIL-0042-DR.A.YILMAZ-HUK";
const ONIZLEME_NO = "YIL-0041-DR.A.YILMAZ-HUK";
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const PREFILL = { muvekkil_adi: "Ahmet Yılmaz", esas_no: "2026/15" };
const noop = () => undefined;

type Payload = Record<string, unknown>;

describe("QuickCaseModal — ofis numarası önizlenir, üretilmez (G237)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    authRequestMock.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => BODIES[url] ?? [],
    }));
    casesApi.checkDuplicateCase.mockResolvedValue([]);
    casesApi.getOfisNoOnizleme.mockResolvedValue({ onizleme: ONIZLEME_NO });
    casesApi.saveCaseAndReturn.mockResolvedValue({ status: "success", id: 7, tracking_no: SUNUCU_NO });
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

  function render(open = true, onCaseCreated: (c: unknown) => void = noop) {
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <QuickCaseModal open={open} onClose={noop} prefill={PREFILL} onCaseCreated={onCaseCreated} />
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

  const onizlemeMetni = () => container.querySelector("[data-testid=ofis-no-onizleme]")?.textContent ?? "";
  const saveButton = () => Array.from(container.querySelectorAll("button"))
    .find(b => b.textContent?.includes("Davayı Aç ve Bağla"));
  const payloadOf = (call: number) => casesApi.saveCaseAndReturn.mock.calls[call][0] as Payload;

  async function save(): Promise<void> {
    const before = casesApi.saveCaseAndReturn.mock.calls.length;
    await waitFor(() => saveButton() !== undefined && !saveButton()!.disabled, "kaydet düğmesi hazır");
    await act(async () => { saveButton()!.click(); });
    await waitFor(() => casesApi.saveCaseAndReturn.mock.calls.length === before + 1, "kayıt isteği atıldı");
    await act(async () => { await Promise.resolve(); });
  }

  function typeClient(value: string): void {
    const input = container.querySelector<HTMLInputElement>('input[placeholder="Müvekkil adı"]')!;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    act(() => {
      setter.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  it("açılınca önizleme sunucudan istenir (kayıtlı müvekkil id'si + tür) ve gösterilir", async () => {
    render();
    await waitFor(() => onizlemeMetni().includes(ONIZLEME_NO), "önizleme göründü");

    expect(onizlemeMetni()).toBe(`Kaydedince verilecek: ${ONIZLEME_NO}`);
    expect(casesApi.getOfisNoOnizleme).toHaveBeenCalledWith("muvekkiller=41&file_type=Hukuk");
  });

  it("kapalı modal önizleme istemez", async () => {
    render(false);
    await act(async () => { await new Promise(r => setTimeout(r, 450)); });

    expect(casesApi.getOfisNoOnizleme).not.toHaveBeenCalled();
  });

  it("müvekkil değişince önizleme yenilenir; yazım sırasında tek istek atılır (debounce)", async () => {
    casesApi.getOfisNoOnizleme.mockImplementation(async (sorgu: string) => ({ onizleme: `NO[${sorgu}]` }));
    render();
    await waitFor(() => onizlemeMetni().includes("NO[muvekkiller=41&file_type=Hukuk]"), "ilk önizleme");
    expect(casesApi.getOfisNoOnizleme).toHaveBeenCalledTimes(1);

    typeClient("Ayşe");
    typeClient("Ayşe G");
    typeClient("Ayşe Gül");
    await waitFor(() => onizlemeMetni().includes("NO[muvekkiller=52&file_type=Hukuk]"), "yeni önizleme");

    // Ara değerler ("Ayşe", "Ayşe G") için istek atılmadı
    expect(casesApi.getOfisNoOnizleme).toHaveBeenCalledTimes(2);
    expect(casesApi.getOfisNoOnizleme).toHaveBeenLastCalledWith("muvekkiller=52&file_type=Hukuk");
  });

  it("kayıt isteği tracking_no TAŞIMAZ, istek kimliği taşır; bağlanan kart sunucunun numarasını alır", async () => {
    const onCaseCreated = vi.fn();
    render(true, onCaseCreated);
    await waitFor(() => onizlemeMetni().includes(ONIZLEME_NO), "önizleme göründü");
    await save();

    expect(payloadOf(0)).not.toHaveProperty("tracking_no");
    expect(JSON.stringify(payloadOf(0))).not.toContain(ONIZLEME_NO);
    expect(payloadOf(0).istek_kimligi).toMatch(UUID_V4);
    expect(onCaseCreated).toHaveBeenCalledWith(expect.objectContaining({ id: 7, tracking_no: SUNUCU_NO }));
    expect(toastApi.success).toHaveBeenCalledWith(
      expect.stringContaining("Dava açıldı"),
      expect.objectContaining({ description: `Ofis No: ${SUNUCU_NO}` }),
    );
  });

  it("önizleme alınamasa da dava açılır", async () => {
    casesApi.getOfisNoOnizleme.mockRejectedValue(new Error(OFIS_NO_ONIZLEME_ERROR));
    const onCaseCreated = vi.fn();
    render(true, onCaseCreated);
    await waitFor(() => onizlemeMetni() === OFIS_NO_ONIZLEME_ERROR, "önizleme hatası göründü");
    await save();

    expect(onCaseCreated).toHaveBeenCalledWith(expect.objectContaining({ id: 7, tracking_no: SUNUCU_NO }));
    expect(toastApi.error).not.toHaveBeenCalled();
  });

  it("hata sonrası yeniden denemede kimlik AYNI; başarıdan sonra yenilenir", async () => {
    casesApi.saveCaseAndReturn.mockResolvedValueOnce({ error: "Sunucu hatası" });
    render();
    await save(); // 1: hata
    await save(); // 2: aynı formun tekrarı — başarılı
    await save(); // 3: başarı sonrası yeni kayıt

    expect(payloadOf(0).istek_kimligi).toMatch(UUID_V4);
    expect(payloadOf(1).istek_kimligi).toBe(payloadOf(0).istek_kimligi);
    expect(payloadOf(2).istek_kimligi).toMatch(UUID_V4);
    expect(payloadOf(2).istek_kimligi).not.toBe(payloadOf(0).istek_kimligi);
    expect(toastApi.error).toHaveBeenCalledTimes(1);
  });

  it("modal kapanıp yeniden açılınca yeni kimlik üretilir", async () => {
    casesApi.saveCaseAndReturn.mockResolvedValue({ error: "Sunucu hatası" });
    render();
    await save();
    render(false);
    render(true);
    await save();

    expect(payloadOf(1).istek_kimligi).toMatch(UUID_V4);
    expect(payloadOf(1).istek_kimligi).not.toBe(payloadOf(0).istek_kimligi);
  });

  it("reused: true yanıtında 'açıldı' mesajı yerine mevcut kart bağlanır", async () => {
    casesApi.saveCaseAndReturn.mockResolvedValue({ status: "success", id: 7, tracking_no: SUNUCU_NO, reused: true });
    const onCaseCreated = vi.fn();
    render(true, onCaseCreated);
    await save();

    expect(toastApi.info).toHaveBeenCalledWith(
      CASE_ALREADY_SAVED_MESSAGE,
      expect.objectContaining({ description: expect.stringContaining(SUNUCU_NO) }),
    );
    expect(toastApi.success).not.toHaveBeenCalled();
    expect(onCaseCreated).toHaveBeenCalledWith(expect.objectContaining({ id: 7, tracking_no: SUNUCU_NO }));
  });
});
