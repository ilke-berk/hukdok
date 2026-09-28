// @vitest-environment jsdom
// G222: QuickCaseModal "Avukat" alanı düz Select değil LawyerCombobox (tekli). Gerçek
// Radix Popover + cmdk (düzleştirilmez) — yazarak arama, seçim ve değer sözleşmesi:
// seçilen avukat ADI string'i `responsible_lawyer_name` olarak aynen gönderilir;
// prefill'de avukat kodu yok sayılır (G229: avukat kodu arayüzden kalktı).
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
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
const casesApi = vi.hoisted(() => ({
  saveCaseAndReturn: vi.fn(async () => ({ id: 7, tracking_no: "T-7" })),
  getClientCaseSequence: vi.fn(async () => 1),
  checkDuplicateCase: vi.fn(async () => []),
  isLoading: false,
}));
vi.mock("@/hooks/useCases", () => ({
  useCases: () => casesApi,
  CASE_SEQUENCE_ERROR: "Sıra numarası alınamadı.",
  CASE_DUPLICATE_CHECK_ERROR: "Mükerrer kontrolü yapılamadı.",
}));
const clientsApi = vi.hoisted(() => ({ clients: [] as { name: string }[], isLoading: false }));
vi.mock("@/hooks/useClients", () => ({ useClients: () => clientsApi }));
vi.mock("@/components/PartyMatchIndicator", () => ({ PartyMatchIndicator: () => null }));

type Kids = { children?: ReactNode };
// Dialog düz DOM (Radix Dialog'un odak tuzağı popover'ı engellemesin); Select dokunulmaz alanlar için düz.
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

const LAWYERS = [
  { code: "ZZ", name: "Av. Zeynep Zor", gorev: "AVUKAT" },
  { code: "AA", name: "Av. Ali Ak", gorev: "DIŞ AVUKAT" },
];

const BODIES: Record<string, unknown> = {
  "/api/config/lawyers": LAWYERS,
  "/api/config/file_types": [{ code: "H", name: "Hukuk" }],
  "/api/config/court_types": [],
  "/api/config/required_case_fields": { fields: [], party_rule: null },
};

const noop = () => undefined;

describe("QuickCaseModal — avukat LawyerCombobox (G222)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    authRequestMock.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => BODIES[url] ?? [],
    }));
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

  function render(prefill: Record<string, unknown>, onCaseCreated = noop) {
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <QuickCaseModal open onClose={noop} prefill={prefill} onCaseCreated={onCaseCreated} />
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

  const trigger = () => container.querySelector<HTMLButtonElement>("[role=combobox][aria-label=Avukat]");
  const item = (name: string) => document.body.querySelector<HTMLElement>(`[cmdk-item][data-lawyer="${name}"]`);
  const lawyersLoaded = () => queryClient.getQueryState(["config", "lawyers"])?.status === "success";

  function openCombobox() {
    act(() => {
      trigger()!.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, pointerType: "mouse" }));
      trigger()!.click();
    });
  }

  it("Avukat alanı yazarak aranan combobox: config sırasıyla tüm avukatlar + görev rozeti", async () => {
    render({});
    await waitFor(lawyersLoaded, "avukat listesi geldi");

    expect(trigger()).not.toBeNull();
    expect(trigger()!.closest("[data-testid=lawyer-combobox]")).not.toBeNull();
    expect(trigger()!.textContent).toBe("Seçiniz");

    openCombobox();
    // 27.09: DIŞ AVUKAT ayrı sekmede — ofis sekmesi varsayılan.
    await waitFor(() => item("Av. Zeynep Zor") !== null, "liste açıldı");
    const names = () => Array.from(document.body.querySelectorAll<HTMLElement>("[cmdk-item]"))
      .map(el => el.getAttribute("data-lawyer"));
    const rozetler = () => Array.from(document.body.querySelectorAll("[data-testid=lawyer-gorev-rozeti]"))
      .map(r => r.textContent);
    expect(names()).toEqual(["Av. Zeynep Zor"]);
    expect(rozetler()).toEqual(["İç"]);
    act(() => document.body.querySelector<HTMLButtonElement>("[data-testid=lawyer-sekme-dis]")!.click());
    expect(names()).toEqual(["Av. Ali Ak"]);
    expect(rozetler()).toEqual(["Dış"]);
  });

  // G229 (27.09 test taşıma izni): eski "avukat_kodu → tam ad" ön-doldurması kalktı; kod gelse
  // bile avukat seçilmez, alan "Seçiniz" kalır (avukat kodu arayüzden tümüyle çıktı).
  it("prefill'deki eski avukat_kodu yok sayılır; avukat alanı boş kalır", async () => {
    render({ avukat_kodu: "AA" });
    await waitFor(lawyersLoaded, "avukat listesi geldi");
    expect(trigger()!.textContent).toBe("Seçiniz");
  });

  it("seçilen avukat ADI responsible_lawyer_name olarak gönderilir (payload sözleşmesi aynı)", async () => {
    const onCaseCreated = vi.fn();
    render({ muvekkil_adi: "Ahmet Yılmaz", esas_no: "2026/15" }, onCaseCreated);
    await waitFor(lawyersLoaded, "avukat listesi geldi");

    openCombobox();
    await waitFor(() => item("Av. Zeynep Zor") !== null, "liste açıldı");
    act(() => item("Av. Zeynep Zor")!.click());
    await waitFor(() => trigger()?.textContent === "Av. Zeynep Zor", "seçim tetikleyicide");

    const save = Array.from(container.querySelectorAll("button"))
      .find(b => b.textContent?.includes("Davayı Aç ve Bağla"));
    expect(save).toBeDefined();
    await act(async () => { save!.click(); });
    await waitFor(() => casesApi.saveCaseAndReturn.mock.calls.length === 1, "kayıt çağrıldı");

    const payload = (casesApi.saveCaseAndReturn.mock.calls[0] as unknown as [Record<string, unknown>])[0];
    expect(payload.responsible_lawyer_name).toBe("Av. Zeynep Zor");
    expect(onCaseCreated).toHaveBeenCalledWith(expect.objectContaining({ responsible_lawyer_name: "Av. Zeynep Zor" }));
  });
});
