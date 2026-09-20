// @vitest-environment jsdom
// Toplu yüklemede ek bağlama — Index kuyruk akışı.
//  - Tezgâhta dilekçeye bağlanan mazbata, dilekçenin /confirm gövdesine
//    `extra_attachment_files` olarak biner; mazbata satırı kendi /confirm'ünde
//    send_email=false ve eksiz gider.
//  - "Her dosyada ayrıca onayla" KAPALIYKEN bile e-postası açık tebligat satırında ya da
//    bağlı eki olan satırda EmailModal ZORLA açılır; diğer satırlar sessiz geçer.
//  - Dosya başına meta File anahtarlıdır: kuyruktan çıkarma sonrası sonraki dosya
//    KENDİ ayarlarını okur (eski dizin hizalı diziler bir kayıyordu).
// Kurulum Index.rerender.test.tsx ile aynı desen; tezgâh ve modal senaryoya göre taklit edilir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AnalysisData } from "@/lib/analyzeDocument";
import type { BulkPrepResult, BulkUploadStartConfig } from "@/components/BulkUploadWorkbench";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
const msal = vi.hoisted(() => ({ accounts: [{ username: "a@b.c", name: "Test Kullanıcı" }] }));
vi.mock("@azure/msal-react", () => ({ useMsal: () => msal }));
vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));

// Dava bağlama: sonraki dosyalarda linkedCase sıfırlanır; arama kutusuna bir harf
// yazılınca "son davalar" listesi (getCases) basılır, oradan seçilir.
const PRESELECT = {
  id: 5,
  tracking_no: "T-5",
  esas_no: "2026/55",
  status: "DERDEST",
  parties: [{ id: 51, name: "Ayşe Yılmaz", party_type: "CLIENT" }],
};
const casesApi = vi.hoisted(() => ({
  getCases: async () => ({ cases: [{
    id: 5, tracking_no: "T-5", esas_no: "2026/55", status: "DERDEST",
    parties: [{ id: 51, name: "Ayşe Yılmaz", party_type: "CLIENT" }],
  }], total: 1 }),
  searchCases: async () => [],
}));
vi.mock("@/hooks/useCases", () => ({
  useCases: () => casesApi,
  CASE_LIST_ERROR: "Dava listesi alınamadı — sunucuya ulaşılamadı.",
}));
const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiClient: { fetch: apiFetchMock },
}));
vi.mock("@/lib/directoryStorage", () => ({
  getStoredOutputDir: async () => ({ name: "cikti" }),
  setStoredOutputDir: async () => undefined,
}));
const analyzeMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/analyzeDocument", () => ({ analyzeDocument: analyzeMock }));

// Senaryo: drop zone'un vereceği dosyalar + tezgâhın "Onaya Geç" payload'ı.
const scenario = vi.hoisted(() => ({
  files: [] as File[],
  results: ((files: File[]) => files.map(f => ({ file: f, docType: "", email: true }))) as (files: File[]) => BulkPrepResult[],
  confirmPerFile: false,
}));
type ValidationHandler = (isValid: boolean, data: AnalysisData) => void;
const captured = vi.hoisted(() => ({
  onValidationChange: null as null | ((isValid: boolean, data: never) => void),
  emailOpen: false,
  defaultExtraAttachments: undefined as File[] | undefined,
  onRemoveFile: null as null | ((index: number) => void),
}));
vi.mock("@/components/flow/FlowDropZone", () => ({
  FlowDropZone: (props: { onFileSelect: (files: File | File[]) => void; selectedFile: File | null }) => (
    !props.selectedFile
      ? <button type="button" data-testid="pick-files" onClick={() => props.onFileSelect(scenario.files)} />
      : null
  ),
}));
vi.mock("@/components/BulkUploadWorkbench", () => ({
  BulkUploadWorkbench: (props: { files: File[]; onStart: (config: BulkUploadStartConfig) => void }) => (
    <button
      type="button"
      data-testid="start-batch"
      onClick={() => props.onStart({
        results: scenario.results(props.files),
        emailConfig: { to: [{ name: "Av. Ali", email: "ali@x.com" }], cc: [], tebligTarihi: "", confirmPerFile: scenario.confirmPerFile },
      })}
    />
  ),
}));
vi.mock("@/components/AnalysisResults", () => ({
  AnalysisResults: (props: { onValidationChange: (isValid: boolean, data: never) => void }) => {
    captured.onValidationChange = props.onValidationChange;
    return null;
  },
}));
vi.mock("@/components/email/EmailModal", () => ({
  EmailModal: (props: {
    isOpen: boolean;
    defaultExtraAttachments?: File[];
    onConfirm: (to: string[], cc: string[], send: boolean, teblig?: string, msgs?: Record<string, string>, extras?: File[]) => void;
  }) => {
    captured.emailOpen = props.isOpen;
    captured.defaultExtraAttachments = props.defaultExtraAttachments;
    return props.isOpen
      ? <button type="button" data-testid="modal-confirm" onClick={() => props.onConfirm(["Av. Ali <ali@x.com>"], [], true, undefined, undefined, props.defaultExtraAttachments)} />
      : null;
  },
}));
vi.mock("@/components/QueueStatus", () => ({
  QueueStatus: (props: { onRemoveFile?: (index: number) => void }) => {
    captured.onRemoveFile = props.onRemoveFile ?? null;
    return null;
  },
}));
vi.mock("@/components/QuickCaseModal", () => ({ QuickCaseModal: () => null }));

import Index from "./Index";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const ANALYSIS: AnalysisData = {
  tarih: "2026-09-01",
  belge_turu_kodu: "DILEKCE_______",
  muvekkil_kodu: "",
  muvekkil_adi: "Ayşe Yılmaz",
  belgede_gecen_isimler: [],
  esas_no: "2026/55",
  durum: "",
  ofis_dosya_no: "",
  yedek1: "",
  yedek2: "",
  ozet: "özet",
  generated_filename: "belge.pdf",
  hash: "h",
};

// Dosya adına göre analiz sonucu: mazbata/tebligat → TEBLIGAT, diğerleri → DILEKCE.
function analysisFor(file: File): AnalysisData {
  const tebligat = /mazbata|tebligat/i.test(file.name);
  return { ...ANALYSIS, belge_turu_kodu: tebligat ? "TEBLIGAT______" : "DILEKCE_______", generated_filename: file.name };
}

const pdf = (name: string) => new File([name], name, { type: "application/pdf" });

describe("Index — toplu yüklemede ek bağlama", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;
  let confirmBodies: FormData[];

  beforeEach(() => {
    vi.clearAllMocks();
    captured.onValidationChange = null;
    captured.emailOpen = false;
    captured.defaultExtraAttachments = undefined;
    captured.onRemoveFile = null;
    confirmBodies = [];
    scenario.confirmPerFile = false;
    localStorage.clear();
    authRequestMock.mockImplementation(async () => ({ ok: true, json: async () => [] }));
    apiFetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/confirm") {
        confirmBodies.push(init!.body as FormData);
        return { ok: true, json: async () => ({ results: { email_success: true } }) };
      }
      return { ok: false, json: async () => ({}) };
    });
    analyzeMock.mockImplementation(async (file: File) => ({ analysisData: analysisFor(file), processId: `p-${file.name}` }));
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
    localStorage.clear();
  });

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

  const byTestId = (id: string) => container.querySelector(`[data-testid="${id}"]`) as HTMLButtonElement | null;
  const clickTestId = (id: string) => act(() => byTestId(id)!.click());
  const confirmButton = () =>
    Array.from(container.querySelectorAll("button"))
      .find(b => b.textContent?.includes("Onayla ve İşlemi Tamamla")) as HTMLButtonElement | undefined;

  async function startBatch(): Promise<void> {
    root = createRoot(container);
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[{ pathname: "/", state: { preselectCase: PRESELECT } }]}>
          <Index />
        </MemoryRouter>
      </QueryClientProvider>,
    ));
    await waitFor(() => byTestId("pick-files") !== null, "drop zone basıldı");
    clickTestId("pick-files");
    await waitFor(() => byTestId("start-batch") !== null, "hazırlık tezgâhı açıldı");
    clickTestId("start-batch");
    await waitFor(() => captured.onValidationChange !== null, "0. dosya analiz sonucu basıldı");
  }

  // Aktif dosyayı onaylar: analiz sonucunu doğrula, gerekiyorsa dava bağla, onay düğmesine bas.
  async function confirmCurrent(file: File, { linkCase = false } = {}): Promise<void> {
    act(() => (captured.onValidationChange as unknown as ValidationHandler)(true, analysisFor(file)));
    if (linkCase) {
      const search = container.querySelector("input[placeholder*='Esas no']") as HTMLInputElement;
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      act(() => {
        setter.call(search, "2");
        search.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await waitFor(() => Array.from(container.querySelectorAll("button")).some(b => b.textContent?.includes("2026/55")), "dava listesi basıldı");
      act(() => Array.from(container.querySelectorAll("button")).find(b => b.textContent?.includes("2026/55"))!.click());
    }
    await waitFor(() => !!confirmButton() && !confirmButton()!.disabled, "onay düğmesi etkin");
    act(() => confirmButton()!.click());
  }

  const extrasOf = (body: FormData) => body.getAll("extra_attachment_files").map(f => (f as File).name);

  it("ekli dilekçede modal ZORLA açılır, ekler prefill gelir; dilekçenin /confirm'ü mazbatayı taşır, mazbata sessiz ve e-postasız geçer", async () => {
    const dilekce = pdf("dilekce.pdf");
    const mazbata = pdf("mazbata.pdf");
    scenario.files = [dilekce, mazbata];
    scenario.results = (files) => [
      { file: files[0], docType: "DILEKCE", email: true, attachments: [files[1]] },
      { file: files[1], docType: "TEBLIGAT", email: false, attachments: [] },
    ];
    await startBatch();

    await confirmCurrent(dilekce);
    await waitFor(() => captured.emailOpen, "dilekçede e-posta penceresi zorla açıldı");
    expect(captured.defaultExtraAttachments).toEqual([mazbata]);
    expect(captured.defaultExtraAttachments![0]).toBe(mazbata);
    expect(confirmBodies).toHaveLength(0);

    clickTestId("modal-confirm");
    await waitFor(() => confirmBodies.length === 1, "dilekçe /confirm gönderildi");
    expect(confirmBodies[0].get("send_email")).toBe("true");
    expect(extrasOf(confirmBodies[0])).toEqual(["mazbata.pdf"]);
    expect(confirmBodies[0].getAll("extra_attachment_files")[0]).toBe(mazbata);

    // Sıradaki dosya: mazbata — ön-yüklemeden gelir, dava bağlanır, sessiz geçer.
    await flush();
    await confirmCurrent(mazbata, { linkCase: true });
    await waitFor(() => confirmBodies.length === 2, "mazbata /confirm gönderildi");
    expect(captured.emailOpen).toBe(false);
    expect(confirmBodies[1].get("send_email")).toBe("false");
    expect(extrasOf(confirmBodies[1])).toEqual([]);
  });

  it("eksiz, tebligat olmayan satır eski sessiz yolu korur (kontrol)", async () => {
    const dilekce = pdf("dilekce.pdf");
    scenario.files = [dilekce, pdf("baska.pdf")];
    scenario.results = (files) => files.map(f => ({ file: f, docType: "DILEKCE", email: true, attachments: [] }));
    await startBatch();

    await confirmCurrent(dilekce);
    await waitFor(() => confirmBodies.length === 1, "dilekçe /confirm gönderildi");
    expect(captured.emailOpen).toBe(false);
    expect(confirmBodies[0].get("send_email")).toBe("true");
    expect(extrasOf(confirmBodies[0])).toEqual([]);
  });

  it("tebligat türü + e-posta açık → eki olmasa da modal açılır (tür analiz sonucundan)", async () => {
    const tebligat = pdf("tebligat.pdf");
    scenario.files = [tebligat, pdf("baska.pdf")];
    // Tezgâhta tür boş (otomatik) bırakıldı; analiz TEBLIGAT______ döner.
    scenario.results = (files) => files.map(f => ({ file: f, docType: "", email: true, attachments: [] }));
    await startBatch();

    await confirmCurrent(tebligat);
    await waitFor(() => captured.emailOpen, "tebligatta e-posta penceresi açıldı");
    expect(confirmBodies).toHaveLength(0);
  });

  it("e-postası kapalı tebligat satırı modal açmaz", async () => {
    const tebligat = pdf("tebligat.pdf");
    scenario.files = [tebligat, pdf("baska.pdf")];
    scenario.results = (files) => files.map(f => ({ file: f, docType: "TEBLIGAT", email: false, attachments: [] }));
    await startBatch();

    await confirmCurrent(tebligat);
    await waitFor(() => confirmBodies.length === 1, "tebligat /confirm gönderildi");
    expect(captured.emailOpen).toBe(false);
    expect(confirmBodies[0].get("send_email")).toBe("false");
  });

  it("sunucu extra_attachments_warning döndürünce toast.warning gösterilir", async () => {
    apiFetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/confirm") {
        confirmBodies.push(init!.body as FormData);
        return { ok: true, json: async () => ({ results: { email_success: true, extra_attachments_warning: "Bazı ekler doğrulamadan geçemediği için e-postaya eklenmedi: mazbata.exe" } }) };
      }
      return { ok: false, json: async () => ({}) };
    });
    const dilekce = pdf("dilekce.pdf");
    scenario.files = [dilekce, pdf("baska.pdf")];
    scenario.results = (files) => files.map(f => ({ file: f, docType: "DILEKCE", email: true, attachments: [] }));
    await startBatch();

    await confirmCurrent(dilekce);
    await waitFor(() => confirmBodies.length === 1, "/confirm gönderildi");
    await flush();
    expect(toastMock.warning).toHaveBeenCalledWith(expect.stringContaining("mazbata.exe"), expect.anything());
  });

  it("kuyruktan çıkarma sonrası sonraki dosya KENDİ ayarlarını okur (File anahtarlı meta, off-by-one yok)", async () => {
    const a = pdf("a.pdf");
    const b = pdf("b.pdf");
    const c = pdf("c.pdf");
    scenario.files = [a, b, c];
    scenario.results = (files) => [
      { file: files[0], docType: "DILEKCE", email: true, attachments: [] },
      { file: files[1], docType: "DILEKCE", email: false, attachments: [] },   // çıkarılacak
      { file: files[2], docType: "DILEKCE", email: true, attachments: [] },
    ];
    await startBatch();

    await waitFor(() => captured.onRemoveFile !== null, "kuyruk şeridi basıldı");
    act(() => captured.onRemoveFile!(1));   // b kuyruktan çıkar

    await confirmCurrent(a);
    await waitFor(() => confirmBodies.length === 1, "a /confirm gönderildi");
    expect(confirmBodies[0].get("send_email")).toBe("true");

    await flush();
    await confirmCurrent(c, { linkCase: true });
    await waitFor(() => confirmBodies.length === 2, "c /confirm gönderildi");
    // Eski dizin hizalı okuma emailFlags[1] = b'nin false'unu okurdu.
    expect(confirmBodies[1].get("send_email")).toBe("true");
    expect(confirmBodies[1].get("new_filename")).toBe("c.pdf");
  });
});
