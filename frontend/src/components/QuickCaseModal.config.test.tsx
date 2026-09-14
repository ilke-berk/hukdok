// @vitest-environment jsdom
// G185: QuickCaseModal yalnız okuduğu üç listeye (lawyers, file_types, court_types)
// ve zorunlu alan ucuna abone olur — useConfig() 32 liste ucu + zorunlu alan ucu
// çağırıyordu. Modal Index'te KAPALIYKEN de monte edildiği için sayfa yüküne
// doğrudan yansıyordu.
// Zorunlu alan sorgusu useConfig.ts'teki ile aynı anahtar/seçeneklerle bileşende
// kurulur; buradaki "önbellek ortak" testleri iki kopyanın ayrışmasının bekçisidir.
// Gerçek useConfig modülü + gerçek QueryClient; ağ (authRequest), MSAL, dava/müvekkil
// hook'ları taklit edilir. Dialog ve Select düz DOM'a indirilir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
const msal = vi.hoisted(() => ({ accounts: [{ username: "a@b.c" }] }));
vi.mock("@azure/msal-react", () => ({ useMsal: () => msal }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
const casesApi = vi.hoisted(() => ({
  saveCaseAndReturn: async () => null,
  getClientCaseSequence: async () => 1,
  checkDuplicateCase: async () => [],
  isLoading: false,
}));
vi.mock("@/hooks/useCases", () => ({
  useCases: () => casesApi,
  CASE_SEQUENCE_ERROR: "Sıra numarası alınamadı.",
  CASE_DUPLICATE_CHECK_ERROR: "Mükerrer kontrolü yapılamadı.",
}));
// `clients` açılış effect'inin bağımlılığında — kimlik sabit.
const clientsApi = vi.hoisted(() => ({ clients: [] as { name: string }[], isLoading: false }));
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
import { useConfig, CONFIG_LIST_ERROR, REQUIRED_FIELDS_ERROR } from "@/hooks/useConfig";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Bilinçli alfabetik DEĞİL: listeler backend sırasıyla basılmalı.
const LAWYERS = [{ code: "ZZ", name: "Av. Zeynep Zor" }, { code: "AA", name: "Av. Ali Ak" }];
const FILE_TYPES = [{ code: "H", name: "Hukuk" }, { code: "C", name: "Ceza" }];
const COURT_TYPES = [
  { code: "TK", name: "tüketici", parent_code: "Hukuk" },
  { code: "IDR", name: "idare", parent_code: "İdari" },
  { code: "AS", name: "asliye hukuk", parent_code: "Hukuk" },
];
const FIELDS = [{ field: "esas_no", label: "Esas No" }];

const PREFILL = {};
const noop = () => undefined;

type Reply = { ok: boolean; body?: unknown };
const OK_BODIES: Record<string, Reply> = {
  "/api/config/lawyers": { ok: true, body: LAWYERS },
  "/api/config/file_types": { ok: true, body: FILE_TYPES },
  "/api/config/court_types": { ok: true, body: COURT_TYPES },
  "/api/config/required_case_fields": { ok: true, body: { fields: FIELDS, party_rule: null } },
};

const routes = (overrides: Record<string, Reply> = {}) => {
  const table = { ...OK_BODIES, ...overrides };
  authRequestMock.mockImplementation(async (url: string) => {
    const r = table[url] ?? { ok: true, body: [] };
    return { ok: r.ok, json: async () => r.body ?? {} };
  });
};

const allUrls = (): string[] => authRequestMock.mock.calls.map(([url]) => url as string);
const configUrls = (): string[] => allUrls().filter(u => u.startsWith("/api/config/")).sort();
const callsTo = (url: string): number => allUrls().filter(u => u === url).length;

const captured = { config: null as ReturnType<typeof useConfig> | null };
const ConfigHarness = () => {
  captured.config = useConfig();
  return null;
};

describe("QuickCaseModal — config aboneliği (G185)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    captured.config = null;
    routes();
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
  });

  /** Aynı kök yeniden render edilir: sonradan eklenen bileşen önbelleği hazır bulur. */
  function render(ui: ReactNode) {
    act(() => root!.render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>));
  }

  const modal = (open: boolean) => (
    <QuickCaseModal open={open} onClose={noop} prefill={PREFILL} onCaseCreated={noop} />
  );

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

  const settled = (key: string) => {
    const status = queryClient.getQueryState(["config", key])?.status;
    return status === "success" || status === "error";
  };
  const ownKeysSettled = () => ["lawyers", "file_types", "court_types", "required_case_fields"].every(settled);

  const ownText = (el: Element) =>
    Array.from(el.childNodes)
      .filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent ?? "")
      .join("")
      .trim();

  /** Etiketin en fazla 3 üst sarmalayıcısında bulunan seçici seçenek metinleri. */
  function optionTexts(label: string): (string | null)[] {
    for (const el of Array.from(container.querySelectorAll("*"))) {
      if (ownText(el) !== label) continue;
      let node: Element | null = el;
      for (let i = 0; i < 3 && node; i++) {
        const opts = node.querySelectorAll("[data-option]");
        if (opts.length > 0) return Array.from(opts).map(o => o.textContent);
        node = node.parentElement;
      }
    }
    return [];
  }

  const banner = () => container.querySelector("[role=alert]");

  it("kapalıyken monte edilince yalnız üç liste + zorunlu alan ucu çağrılır (useConfig 33 uç çağırıyordu)", async () => {
    render(modal(false));
    await waitFor(ownKeysSettled, "dört uç sonuçlandı");
    await flush();

    expect(configUrls()).toEqual([
      "/api/config/court_types",
      "/api/config/file_types",
      "/api/config/lawyers",
      "/api/config/required_case_fields",
    ]);
  });

  it("açıkken seçiciler aynı sırayla: dosya türü, üst türe göre gruplu alt tür, avukat", async () => {
    render(modal(true));
    await waitFor(ownKeysSettled, "dört uç sonuçlandı");
    await waitFor(() => optionTexts("Avukat").length === 2, "avukat seçenekleri doldu");

    expect(optionTexts("Dosya Türü")).toEqual(["Hukuk", "Ceza"]);
    // Varsayılan dosya türü "Hukuk": yalnız parent_code=Hukuk olan mahkeme türleri, sırası korunur.
    expect(optionTexts("Alt Tür")).toEqual(["Tüketici", "Asliye Hukuk"]);
    expect(optionTexts("Avukat")).toEqual(["Av. Zeynep Zor", "Av. Ali Ak"]);
    expect(banner()).toBeNull();
  });

  it("hata ≠ boş liste (G019): şerit iki mesajı da gösterir, Tekrar dene dört ucu yeniden çeker", async () => {
    routes({
      "/api/config/lawyers": { ok: false, body: {} },
      "/api/config/required_case_fields": { ok: false, body: {} },
    });
    render(modal(true));
    await waitFor(() => banner() !== null, "hata şeridi çıktı");
    await waitFor(
      () => (banner()?.textContent ?? "").includes(REQUIRED_FIELDS_ERROR)
        && (banner()?.textContent ?? "").includes(CONFIG_LIST_ERROR),
      "şerit iki mesajı taşıyor",
    );

    routes();
    const retry = Array.from(container.querySelectorAll("button"))
      .find(b => b.textContent?.includes("Tekrar dene"));
    expect(retry).toBeDefined();
    act(() => retry!.click());
    await waitFor(() => banner() === null, "şerit kalktı");

    for (const key of ["lawyers", "file_types", "court_types", "required_case_fields"]) {
      expect(callsTo(`/api/config/${key}`)).toBe(2);
    }
  });

  it("zorunlu alan önbelleği useConfig ile ortak: modal önce, useConfig sonra monte → uç yine 1 kez", async () => {
    render(modal(false));
    await waitFor(ownKeysSettled, "modal uçları sonuçlandı");

    render(<>{modal(false)}<ConfigHarness /></>);
    await waitFor(
      () => captured.config !== null && !captured.config.isLoading && captured.config.requiredCaseFields.length > 0,
      "useConfig doldu",
    );
    await flush();

    expect(callsTo("/api/config/required_case_fields")).toBe(1);
    expect(callsTo("/api/config/lawyers")).toBe(1);
    // useConfig aynı önbellek girdisinden okur: veri şekli ({fields, party_rule}) uyumlu.
    expect(captured.config!.requiredCaseFields).toEqual(FIELDS);
    expect(captured.config!.requiredFieldsError).toBeUndefined();
  });

  it("zorunlu alan önbelleği useConfig ile ortak: useConfig önce, modal sonra monte → taze veri yeniden çekilmez", async () => {
    render(<ConfigHarness />);
    await waitFor(
      () => captured.config !== null && !captured.config.isLoading && captured.config.requiredCaseFields.length > 0,
      "useConfig doldu",
    );
    expect(callsTo("/api/config/required_case_fields")).toBe(1);

    render(<><ConfigHarness />{modal(true)}</>);
    await waitFor(() => optionTexts("Avukat").length === 2, "modal önbellekten doldu");
    await flush();

    // Modalın sorgusu aynı anahtar + 5 dk staleTime taşımasaydı burada ikinci istek giderdi.
    expect(callsTo("/api/config/required_case_fields")).toBe(1);
    expect(callsTo("/api/config/lawyers")).toBe(1);
    expect(banner()).toBeNull();
  });
});
