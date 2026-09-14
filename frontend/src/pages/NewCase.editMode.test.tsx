// @vitest-environment jsdom
// G186 (F10): düzenleme modunda `editModeCase` eskiden hem useState başlangıcına
// (her render'da yeniden hesaplanan, lazy OLMAYAN argüman) hem de mount sonrası
// bir effect'e kopyalanıyordu → form değerleri iki kez kurulup sayfa bir tur
// fazladan render ediliyordu. Beklenen: ilk commit'te alanlar dolu, form değeri
// tek kez hesaplanır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, Profiler } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock("@/hooks/useClients", () => ({ useClients: () => ({ clients: [] }) }));
// Effect bağımlılığında olabilecekleri için kimlikler sabit tutulur.
const configApi = vi.hoisted(() => ({
  caseSubjects: [],
  lawyers: [],
  fileTypes: [],
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
  saveCase: async () => ({ ok: true }),
  updateCase: async () => ({ ok: true }),
  deleteCase: async () => true,
  getCase: async () => null,
  checkDuplicateCase: async () => [],
  getClientCaseSequence: async () => 1,
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
// Gerçek fonksiyon korunur; yalnız çağrı sayısı izlenir.
vi.mock("@/lib/newCasePayload", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/newCasePayload")>();
  return { ...actual, editModeFormValues: vi.fn(actual.editModeFormValues) };
});

import NewCase from "./NewCase";
import { editModeFormValues, type EditModeCaseData } from "@/lib/newCasePayload";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
// Radix Checkbox (useSize) ResizeObserver ister; jsdom'da yok.
const globalWithRO = globalThis as { ResizeObserver?: unknown };
if (!globalWithRO.ResizeObserver) {
  globalWithRO.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

const EDIT_CASE: EditModeCaseData = {
  id: 42,
  tracking_no: "2026.00042.HUK.01.00100",
  status: "DERDEST",
  esas_no: "2026/55",
  court: "İstanbul 3. Asliye Hukuk Mahkemesi",
  subject: "Tazminat",
  parties: [
    { party_type: "CLIENT", name: "Ayşe Yılmaz", role: "Davacı" },
    { party_type: "COUNTER", name: "Mehmet Kaya", role: "Davalı" },
  ],
  lawyers: [{ name: "Av. Ali Demir", lawyer_id: 3 }],
};

describe("NewCase — düzenleme modu tek kurulum (G186 F10)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.mocked(editModeFormValues).mockClear();
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
  });

  const inputByPlaceholder = (placeholder: string) =>
    container.querySelector(`input[placeholder="${placeholder}"]`) as HTMLInputElement | null;

  const inputByValue = (value: string) =>
    Array.from(container.querySelectorAll("input")).find(el => el.value === value) ?? null;

  function renderEdit(onCommit?: (phase: string) => void): void {
    root = createRoot(container);
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[{ pathname: "/new-case/form", state: { case: EDIT_CASE } }]}>
          <Routes>
            <Route
              path="/new-case/form"
              element={
                <Profiler id="new-case" onRender={(_id, phase) => onCommit?.(phase)}>
                  <NewCase />
                </Profiler>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ));
  }

  it("ilk commit'te form alanları dolu gelir; hiçbir commit'te boş ara değer görünmez", () => {
    const esasValues: Array<{ phase: string; value: string | undefined }> = [];
    renderEdit(phase => {
      esasValues.push({ phase, value: inputByPlaceholder("2024/123")?.value });
    });

    expect(esasValues.length).toBeGreaterThan(0);
    expect(esasValues[0]).toEqual({ phase: "mount", value: "2026/55" });
    expect(esasValues.every(v => v.value === "2026/55")).toBe(true);
    // Taraf ve mahkeme de ilk kurulumdan dolu.
    expect(inputByValue("İstanbul 3. Asliye Hukuk Mahkemesi")).not.toBeNull();
    expect(container.textContent).toContain("Dava Kartı Düzenle");
  });

  it("düzenleme formu değerleri yalnız BİR kez hesaplanır (effect kopyası ve render başına yeniden hesap yok)", () => {
    renderEdit();

    expect(inputByPlaceholder("2024/123")?.value).toBe("2026/55");
    expect(vi.mocked(editModeFormValues)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(editModeFormValues)).toHaveBeenCalledWith(EDIT_CASE);
  });
});
