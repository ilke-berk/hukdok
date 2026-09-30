// @vitest-environment jsdom
// G237: dava açma sihirbazının inceleme adımı ofis numarasını ÜRETMEZ — sunucudan
// önizler; commit isteği `tracking_no` taşımaz, tekrar korumalı `istek_kimligi` taşır;
// 409'da numara yeniden üretip otomatik tekrar deneme döngüsü yoktur (karar 023).
// Form, "yarım kalan taslaktan devam" yoluyla (`initialReview`) kurulur: müvekkil onaylı
// gelir ve "taslak geri yüklemede taslağın kimliği" / "eski numaralı taslak" yolları da
// aynı kurulumla sınanır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";

const toastApi = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastApi }));
// Kimlikler sabit: listeler effect/memo bağımlılıklarında.
const configApi = vi.hoisted(() => ({
  lawyers: [],
  doctypes: [],
  emailRecipients: [],
  courtTypesByParent: {},
  caseSubjects: [],
  specialties: [],
  bureauTypes: [],
  requiredCaseFields: [],
}));
vi.mock("@/hooks/useConfig", () => ({ useConfig: () => configApi }));
const casesApi = vi.hoisted(() => ({ getOfisNoOnizleme: vi.fn() }));
vi.mock("@/hooks/useCases", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/useCases")>()),
  useCases: () => casesApi,
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiClient: { fetch: vi.fn(async () => ({ ok: false, json: async () => ({}) })) },
}));
vi.mock("@/components/PartyMatchIndicator", () => ({ PartyMatchIndicator: () => null }));

import { IntakeReviewStep } from "./IntakeReviewStep";
import { CASE_ALREADY_SAVED_MESSAGE, OFIS_NO_ONIZLEME_ERROR } from "@/hooks/useCases";
import { CommitConflictError, type CaseIntakeCommitRequest, type MergeDraft } from "@/lib/caseIntake";
import { buildFieldStates } from "@/lib/caseIntakeFields";
import { loadIntakeDraft, type ReviewSnapshot } from "@/lib/intakeDraft";

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

const TASLAK_KIMLIGI = "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a";
const ESKI_NUMARA = "D1.A_YILMAZ...0007.HUKUK.00100";
const SUNUCU_NO = "YIL-0042-DR.A.YILMAZ-HUK";
const ONIZLEME_NO = "YIL-0041-DR.A.YILMAZ-HUK";
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const draft = {
  fields: {},
  parties: [],
  policies: [],
  warnings: [],
  documents: [{
    process_id: "p1", filename: "a.pdf", belge_turu_kodu: null,
    belge_turu_tahmini: null, ozet: null, status: "ok",
  }],
  duplicate_case: null,
  priors: {},
} as unknown as MergeDraft;

const review = (over: Record<string, unknown> = {}): ReviewSnapshot => ({
  fieldStates: buildFieldStates(draft),
  parties: [{
    name: "Ahmet Yılmaz", role: "Davacı", party_type: "CLIENT", tc_no: "",
    client_id: 41, matchName: "AHMET YILMAZ", matchCategory: "Doktor",
    approved: true, fromDraft: true,
  }],
  serviceMask: "00100",
  selectedLawyers: [],
  istekKimligi: TASLAK_KIMLIGI,
  selectedPolicies: {},
  documents: [{ process_id: "p1", filename: "a.pdf", newName: "a.pdf", code: "", ozet: "", expired: false }],
  sendEmail: false,
  emailTo: [],
  ...over,
} as ReviewSnapshot);

describe("IntakeReviewStep — ofis numarası önizlenir, üretilmez (G237)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  const onCommit = vi.fn<(req: CaseIntakeCommitRequest) => Promise<unknown>>();

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    casesApi.getOfisNoOnizleme.mockResolvedValue({ onizleme: ONIZLEME_NO });
    onCommit.mockResolvedValue({ case: { id: 12, tracking_no: SUNUCU_NO, reused: false }, documents: [], policies: {} });
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
    sessionStorage.clear();
    document.body.innerHTML = "";
  });

  function render(initialReview: ReviewSnapshot | null) {
    act(() => root!.render(
      <MemoryRouter>
        <IntakeReviewStep draft={draft} isCommitting={false} onCommit={onCommit} initialReview={initialReview} />
      </MemoryRouter>,
    ));
  }

  async function waitFor(condition: () => boolean, label: string): Promise<void> {
    for (let i = 0; i < 200; i++) {
      if (condition()) return;
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
    throw new Error(`Koşul sağlanmadı: ${label}`);
  }

  const onizlemeKutusu = () => container.querySelector<HTMLInputElement>("[data-testid=ofis-no-onizleme]");
  const saveButton = () => Array.from(container.querySelectorAll("button"))
    .find(b => b.textContent?.includes("Kaydet ve Arşivle"));
  const caseOf = (call: number) => onCommit.mock.calls[call][0].case as unknown as Record<string, unknown>;

  async function save(): Promise<void> {
    const before = onCommit.mock.calls.length;
    await waitFor(() => saveButton() !== undefined && !saveButton()!.disabled, "kaydet düğmesi açık");
    await act(async () => { saveButton()!.click(); });
    await waitFor(() => onCommit.mock.calls.length >= before + 1, "commit isteği atıldı");
    await act(async () => { await Promise.resolve(); });
  }

  it("onaylı müvekkille önizleme sunucudan istenir ve salt-okunur kutuda gösterilir", async () => {
    render(review());
    await waitFor(() => onizlemeKutusu()?.value === ONIZLEME_NO, "önizleme göründü");

    expect(casesApi.getOfisNoOnizleme).toHaveBeenCalledTimes(1);
    expect(casesApi.getOfisNoOnizleme).toHaveBeenCalledWith("muvekkiller=41");
    expect(onizlemeKutusu()!.readOnly).toBe(true);
    // Eski "sıra numarasını yeniden sorgula" düğmesi kalktı
    expect(container.querySelector('button[title="Sıra numarasını yeniden sorgula"]')).toBeNull();
  });

  it("commit isteği tracking_no TAŞIMAZ; taslaktan devamda TASLAĞIN kimliği gider", async () => {
    render(review());
    await waitFor(() => onizlemeKutusu()?.value === ONIZLEME_NO, "önizleme göründü");
    await save();

    expect(caseOf(0)).not.toHaveProperty("tracking_no");
    expect(JSON.stringify(onCommit.mock.calls[0][0])).not.toContain(ONIZLEME_NO);
    expect(caseOf(0).istek_kimligi).toBe(TASLAK_KIMLIGI);
    expect(onCommit.mock.calls[0][0].documents.map(d => d.process_id)).toEqual(["p1"]);
  });

  it("eski numara taşıyan taslak geri yüklendiğinde numara GÖNDERİLMEZ ve gösterilmez", async () => {
    render(review({ trackingNo: ESKI_NUMARA, istekKimligi: undefined }));
    await waitFor(() => onizlemeKutusu()?.value === ONIZLEME_NO, "önizleme göründü");
    await save();

    expect(caseOf(0)).not.toHaveProperty("tracking_no");
    expect(JSON.stringify(onCommit.mock.calls[0][0])).not.toContain(ESKI_NUMARA);
    expect(container.innerHTML).not.toContain(ESKI_NUMARA);
    // Eski taslakta kimlik yok → yenisi üretilir
    expect(caseOf(0).istek_kimligi).toMatch(UUID_V4);
  });

  it("önizleme alınamasa da kayıt yapılabilir", async () => {
    casesApi.getOfisNoOnizleme.mockRejectedValue(new Error(OFIS_NO_ONIZLEME_ERROR));
    render(review());
    await waitFor(
      () => container.querySelector("[data-testid=ofis-no-onizleme-hatasi]") !== null,
      "önizleme hatası göründü",
    );
    expect(onizlemeKutusu()!.value).toBe("");
    expect(saveButton()!.disabled).toBe(false);

    await save();
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(toastApi.error).not.toHaveBeenCalled();
  });

  it("409'da numara yeniden üretip otomatik tekrar DENEMEZ; elle tekrar AYNI kimlikle gider", async () => {
    onCommit.mockRejectedValueOnce(new CommitConflictError("Bu kayıt isteği daha önce kullanılmış."));
    render(review({ istekKimligi: undefined }));
    await save();
    await waitFor(() => toastApi.error.mock.calls.length === 1, "hata gösterildi");

    // Eski davranış: 409 → sıra yenile → ikinci commit. Artık tek çağrı.
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(toastApi.error).toHaveBeenCalledWith(
      "Kayıt başarısız",
      expect.objectContaining({ description: "Bu kayıt isteği daha önce kullanılmış." }),
    );

    await save(); // kullanıcı yeniden dener
    expect(onCommit).toHaveBeenCalledTimes(2);
    expect(caseOf(0).istek_kimligi).toMatch(UUID_V4);
    expect(caseOf(1).istek_kimligi).toBe(caseOf(0).istek_kimligi);
  });

  it("yeni açılan inceleme adımı (yeni sihirbaz) yeni kimlik üretir", async () => {
    render(review({ istekKimligi: undefined }));
    await save();
    act(() => root!.unmount());
    root = createRoot(container);
    render(review({ istekKimligi: undefined }));
    await save();

    expect(caseOf(1).istek_kimligi).toMatch(UUID_V4);
    expect(caseOf(1).istek_kimligi).not.toBe(caseOf(0).istek_kimligi);
  });

  it("reused: true yanıtında 'zaten kaydedilmiş' bilgisi gösterilir", async () => {
    onCommit.mockResolvedValue({ case: { id: 12, tracking_no: SUNUCU_NO, reused: true }, documents: [], policies: {} });
    render(review());
    await save();
    await waitFor(() => toastApi.info.mock.calls.length === 1, "bilgi gösterildi");

    expect(toastApi.info).toHaveBeenCalledWith(
      CASE_ALREADY_SAVED_MESSAGE,
      expect.objectContaining({ description: expect.stringContaining(SUNUCU_NO) }),
    );
    expect(toastApi.error).not.toHaveBeenCalled();
  });

  it("taslağa numara yazılmaz, istek kimliği yazılır", async () => {
    render(review({ istekKimligi: undefined }));
    await waitFor(() => onizlemeKutusu()?.value === ONIZLEME_NO, "önizleme göründü");
    act(() => { window.dispatchEvent(new Event("pagehide")); }); // bekleyen taslak yazımını diske indirir

    const raw = sessionStorage.getItem("hukdok.intake-draft.v1") ?? "";
    expect(raw).not.toBe("");
    expect(raw).not.toContain("trackingNo");
    expect(raw).not.toContain(ONIZLEME_NO);
    expect(loadIntakeDraft()?.review.istekKimligi).toMatch(UUID_V4);
  });
});
