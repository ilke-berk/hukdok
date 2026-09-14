// @vitest-environment jsdom
// G186 (F8, F9): Index yeniden render düzeltmeleri.
//  - F8: "bugünkü yüklemeler" kaydı her render'da iki kez localStorage'dan okunup
//    JSON.parse ediliyordu (lazy olmayan useState argümanı). Beklenen: monte +
//    yeniden render'larda anahtar en fazla BİR kez okunur; sayaç ve liste aynı
//    okumadan türer.
//  - F9: müvekkil bilgilendirme effect'i `finalData`/`analysisData` NESNELERİNE
//    bağlıydı, gövde yalnız `belge_turu_kodu` kullanıyor. Modal açıkken aynı kodla
//    yeni nesne kimliği gelince hedef ucu TEKRAR çağrılmamalı.
// Kurulum Index.config.test.tsx ile aynı desen; akışı sürmek için drop zone,
// toplu hazırlık tezgâhı, analiz sonucu paneli ve e-posta modalı taklit edilir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AnalysisData } from "@/lib/analyzeDocument";
import type { BulkUploadStartConfig } from "@/components/BulkUploadWorkbench";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
const msal = vi.hoisted(() => ({ accounts: [{ username: "a@b.c", name: "Test Kullanıcı" }] }));
vi.mock("@azure/msal-react", () => ({ useMsal: () => msal }));
vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
// Effect bağımlılığında oldukları için fonksiyon kimlikleri sabit tutulur.
const casesApi = vi.hoisted(() => ({
  getCases: async () => ({ cases: [], total: 0 }),
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
// Çıktı klasörü seçili kabul edilir (onay düğmesi aksi hâlde kilitli).
vi.mock("@/lib/directoryStorage", () => ({
  getStoredOutputDir: async () => ({ name: "cikti" }),
  setStoredOutputDir: async () => undefined,
}));
const analyzeMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/analyzeDocument", () => ({ analyzeDocument: analyzeMock }));

type ValidationHandler = (isValid: boolean, data: AnalysisData) => void;
const captured = vi.hoisted(() => ({
  onValidationChange: null as null | ((isValid: boolean, data: never) => void),
  emailOpen: false,
}));
vi.mock("@/components/flow/FlowDropZone", () => ({
  FlowDropZone: (props: { onFileSelect: (files: File | File[]) => void; todayCount?: number; selectedFile: File | null }) => (
    <div>
      <span data-testid="today-count">{props.todayCount}</span>
      {!props.selectedFile && (
        <button
          type="button"
          data-testid="pick-files"
          onClick={() => props.onFileSelect([
            new File(["a"], "tebligat.pdf", { type: "application/pdf" }),
            new File(["b"], "ek.pdf", { type: "application/pdf" }),
          ])}
        />
      )}
    </div>
  ),
}));
vi.mock("@/components/BulkUploadWorkbench", () => ({
  BulkUploadWorkbench: (props: { files: File[]; onStart: (config: BulkUploadStartConfig) => void }) => (
    <button
      type="button"
      data-testid="start-batch"
      onClick={() => props.onStart({
        results: [{ file: props.files[0], docType: "TEBLIGAT", email: false }],
        emailConfig: { to: [], cc: [], tebligTarihi: "", confirmPerFile: true },
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
  EmailModal: (props: { isOpen: boolean }) => {
    captured.emailOpen = props.isOpen;
    return null;
  },
}));
vi.mock("@/components/QuickCaseModal", () => ({ QuickCaseModal: () => null }));

import Index from "./Index";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const TODAY_KEY = "hukudok-today-uploads";

function localDateKey(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const ANALYSIS: AnalysisData = {
  tarih: "2026-09-01",
  belge_turu_kodu: "TEBLIGAT",
  muvekkil_kodu: "",
  muvekkil_adi: "Ayşe Yılmaz",
  belgede_gecen_isimler: [],
  esas_no: "2026/55",
  durum: "",
  ofis_dosya_no: "",
  yedek1: "",
  yedek2: "",
  ozet: "ilk özet",
  generated_filename: "tebligat.pdf",
  hash: "h",
};

// parties dolu ve id'li → Index tam davayı ayrıca çekmez (fetch sayacı temiz kalır).
const PRESELECT = {
  id: 5,
  tracking_no: "T-5",
  esas_no: "2026/55",
  status: "DERDEST",
  parties: [{ id: 51, name: "Ayşe Yılmaz", party_type: "CLIENT" }],
};

describe("Index — yeniden render düzeltmeleri (G186)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    captured.onValidationChange = null;
    captured.emailOpen = false;
    localStorage.clear();
    authRequestMock.mockImplementation(async () => ({ ok: true, json: async () => [] }));
    apiFetchMock.mockImplementation(async (url: string) => {
      if (url.includes("/client-notice-target")) {
        return {
          ok: true,
          json: async () => ({
            eligible: true,
            feature_enabled: true,
            lawyer: { name: "Av. Ali Demir", email: "ali@example.com" },
            client_name: "Ayşe Yılmaz",
          }),
        };
      }
      return { ok: false, json: async () => ({}) };
    });
    analyzeMock.mockImplementation(async () => ({ analysisData: { ...ANALYSIS }, processId: "p-1" }));
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

  function tree(state?: unknown) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[{ pathname: "/", state }]}>
          <Index />
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  describe("F8 — bugünkü yüklemeler tek okuma", () => {
    it("monte + iki yeniden render'da kayıt anahtarı en fazla bir kez okunur", async () => {
      const getItemSpy = vi.spyOn(Storage.prototype, "getItem");
      try {
        root = createRoot(container);
        act(() => root!.render(tree()));
        act(() => root!.render(tree()));
        act(() => root!.render(tree()));
        await flush();

        const todayReads = getItemSpy.mock.calls.filter(([key]) => key === TODAY_KEY).length;
        expect(todayReads).toBeLessThanOrEqual(1);
      } finally {
        getItemSpy.mockRestore();
      }
    });

    it("sayaç ve liste aynı kayıttan beslenir (davranış aynı)", async () => {
      localStorage.setItem(TODAY_KEY, JSON.stringify({
        date: localDateKey(),
        items: [
          { id: "1", filename: "karar-bugun.pdf", sizeBytes: 10, ext: "PDF", status: "ARŞİVLENDİ", ts: Date.now() },
          { id: "2", filename: "tebligat-bugun.pdf", sizeBytes: 20, ext: "PDF", status: "BAĞLANDI", ts: Date.now() },
        ],
      }));

      root = createRoot(container);
      act(() => root!.render(tree()));
      await flush();

      expect(container.querySelector('[data-testid="today-count"]')?.textContent).toBe("2");
      expect(container.textContent).toContain("karar-bugun.pdf");
      expect(container.textContent).toContain("tebligat-bugun.pdf");
    });
  });

  describe("F9 — müvekkil bilgilendirme effect'i primitif bağımlılık", () => {
    const noticeCalls = () =>
      apiFetchMock.mock.calls
        .map(([url]) => url as string)
        .filter(u => u.includes("/client-notice-target"));

    const validate = (data: AnalysisData) => {
      act(() => (captured.onValidationChange as unknown as ValidationHandler)(true, data));
    };

    async function openEmailModal(): Promise<void> {
      root = createRoot(container);
      act(() => root!.render(tree({ preselectCase: PRESELECT })));
      await waitFor(() => container.querySelector('[data-testid="pick-files"]') !== null, "drop zone basıldı");

      act(() => (container.querySelector('[data-testid="pick-files"]') as HTMLButtonElement).click());
      await waitFor(() => container.querySelector('[data-testid="start-batch"]') !== null, "hazırlık tezgâhı açıldı");
      act(() => (container.querySelector('[data-testid="start-batch"]') as HTMLButtonElement).click());

      await waitFor(() => captured.onValidationChange !== null, "analiz sonucu paneli basıldı");
      validate({ ...ANALYSIS, ozet: "onaylı özet" });

      const confirmButton = () =>
        Array.from(container.querySelectorAll("button"))
          .find(b => b.textContent?.includes("Onayla ve İşlemi Tamamla")) as HTMLButtonElement | undefined;
      await waitFor(() => !!confirmButton() && !confirmButton()!.disabled, "onay düğmesi etkin");
      act(() => confirmButton()!.click());

      await waitFor(() => captured.emailOpen, "e-posta modalı açıldı");
      await waitFor(() => noticeCalls().length === 1, "bildirim hedefi çekildi");
      await flush();
    }

    it("modal açıkken aynı belge_turu_kodu ile yeni nesne gelince hedef ucu TEKRAR çağrılmaz", async () => {
      await openEmailModal();
      expect(noticeCalls()).toEqual(["/api/cases/5/client-notice-target?belge_turu_kodu=TEBLIGAT"]);

      // İçeriği farklı (özet değişti) → finalData yeni nesne kimliği; kod aynı.
      validate({ ...ANALYSIS, ozet: "düzeltilmiş özet" });
      await flush();
      validate({ ...ANALYSIS, ozet: "bir daha düzeltilmiş özet" });
      await flush();

      expect(noticeCalls()).toHaveLength(1);
    });

    it("belge_turu_kodu değişince hedef yeni kodla yeniden çekilir (kontrol)", async () => {
      await openEmailModal();

      validate({ ...ANALYSIS, belge_turu_kodu: "KARAR", ozet: "karar özeti" });
      await waitFor(() => noticeCalls().length === 2, "yeni kodla yeniden çekildi");

      expect(noticeCalls()[1]).toBe("/api/cases/5/client-notice-target?belge_turu_kodu=KARAR");
    });
  });
});
