// @vitest-environment jsdom
// G253: dava açma sihirbazının inceleme adımında hizmet MÜVEKKİL BAŞINA seçilir — her
// müvekkil (CLIENT) satırında bir `HizmetSecici` (gerçek bileşen, gerçek Radix Popover +
// cmdk), kayıtlı carinin kategorisine göre ön seçim, "tüm müvekkillere uygula" kısayolu,
// hizmetsiz onaylı müvekkilde Kaydet kapalı, commit'te taraf başına `hizmet_turleri`.
// Eski "Hizmet Türü (Çoklu Seçim)" 5'li maskesi kalktı; enrich modunda seçici gizlidir.
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
  serviceTypes: [] as { code: string; name: string }[],
}));
// İnceleme adımı listeyi `useConfig()`'ten, `HizmetSecici` `useConfigList("serviceTypes")`'ten okur.
vi.mock("@/hooks/useConfig", () => ({
  useConfig: () => configApi,
  useConfigList: () => ({ data: configApi.serviceTypes, isLoading: false, isError: false, error: undefined }),
}));
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
import type { CaseIntakeApplyRequest, CaseIntakeCommitRequest, MergeDraft } from "@/lib/caseIntake";
import { buildFieldStates } from "@/lib/caseIntakeFields";
import { loadIntakeDraft, type DraftParty, type ReviewSnapshot } from "@/lib/intakeDraft";

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
const HASTANE = "Özel Şifa Hastanesi"; // kategorisi eşlemede yok → ön seçim yok
const HASTA = "Ayşe Gül";

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

const taraf = (name: string, over: Partial<DraftParty> = {}): DraftParty => ({
  name, role: "Davalı", party_type: "CLIENT", tc_no: "",
  client_id: null, matchName: null, matchCategory: null,
  approved: true, fromDraft: true,
  ...over,
});
const doktor = (over: Partial<DraftParty> = {}) =>
  taraf(DOKTOR, { client_id: 41, matchName: "AHMET YILMAZ", matchCategory: "Doktor", ...over });
const hastane = (over: Partial<DraftParty> = {}) =>
  taraf(HASTANE, { client_id: 63, matchName: "ÖZEL ŞİFA HASTANESİ", matchCategory: "Özel Hastane", ...over });
const hasta = (over: Partial<DraftParty> = {}) =>
  taraf(HASTA, { client_id: 52, matchName: "AYŞE GÜL", matchCategory: "Hasta", ...over });
const karsiTaraf = () => taraf("Mehmet Kaya", { party_type: "COUNTER", role: "Davacı" });

const review = (parties: DraftParty[]): ReviewSnapshot => ({
  fieldStates: buildFieldStates(draft),
  parties,
  selectedLawyers: [],
  istekKimligi: "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a",
  selectedPolicies: {},
  documents: [{ process_id: "p1", filename: "a.pdf", newName: "a.pdf", code: "", ozet: "", expired: false }],
  sendEmail: false,
  emailTo: [],
});

describe("IntakeReviewStep — müvekkil başına hizmet seçimi (G253)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  const onCommit = vi.fn<(req: CaseIntakeCommitRequest) => Promise<unknown>>();
  const onApply = vi.fn<(req: CaseIntakeApplyRequest) => Promise<unknown>>();

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    configApi.serviceTypes = SERVICE_TYPES;
    casesApi.getOfisNoOnizleme.mockResolvedValue({ onizleme: "YIL-0041-DR.A.YILMAZ-HUK" });
    onCommit.mockResolvedValue({ case: { id: 12, tracking_no: "YIL-0042-DR.A.YILMAZ-HUK", reused: false }, documents: [], policies: {} });
    onApply.mockResolvedValue({});
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

  function render(initialReview: ReviewSnapshot | null, mergeDraft: MergeDraft = draft) {
    act(() => root!.render(
      <MemoryRouter>
        <IntakeReviewStep
          draft={mergeDraft}
          isCommitting={false}
          onCommit={onCommit}
          onApply={onApply}
          initialReview={initialReview}
        />
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

  const seciciler = () =>
    Array.from(container.querySelectorAll<HTMLButtonElement>('[role=combobox][aria-label$="için hizmetler"]'));
  const secici = (ad: string) =>
    container.querySelector<HTMLButtonElement>(`[role=combobox][aria-label="${ad} için hizmetler"]`);
  const cipler = (ad: string) =>
    Array.from(secici(ad)!.querySelectorAll("[data-testid=hizmet-secici-cip]")).map(c => c.textContent);
  const uyari = (ad: string) =>
    secici(ad)!.closest("[data-testid=muvekkil-hizmet]")!.querySelector("[data-testid=hizmet-eksik-uyarisi]");
  const tumuneUygula = () => container.querySelector<HTMLButtonElement>("[data-testid=hizmet-tumune-uygula]");
  const saveButton = (text = "Kaydet ve Arşivle") =>
    Array.from(container.querySelectorAll("button")).find(b => b.textContent?.includes(text))!;
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

  async function save(): Promise<CaseIntakeCommitRequest> {
    const before = onCommit.mock.calls.length;
    await waitFor(() => !saveButton().disabled, "kaydet düğmesi açık");
    await act(async () => { saveButton().click(); });
    await waitFor(() => onCommit.mock.calls.length === before + 1, "commit isteği atıldı");
    await act(async () => { await Promise.resolve(); });
    return onCommit.mock.calls[before][0];
  }

  it("eski 5'li 'Hizmet Türü (Çoklu Seçim)' maskesi ekranda yok", () => {
    render(review([doktor()]));

    expect(container.textContent).not.toContain("Hizmet Türü (Çoklu Seçim)");
    for (const eski of ["Rapor", "Dava", "İcra", "Yazışma"]) {
      expect(Array.from(container.querySelectorAll("label")).some(l => l.textContent?.trim() === eski)).toBe(false);
    }
    expect(container.textContent).toContain("Dava Avukatları (Sorumluya Ek)");
  });

  it("her müvekkil satırında erişilebilir etiketli bir seçici; karşı taraf satırında YOK", () => {
    render(review([doktor(), hastane(), karsiTaraf()]));

    expect(seciciler().map(s => s.getAttribute("aria-label"))).toEqual([
      `${DOKTOR} için hizmetler`,
      `${HASTANE} için hizmetler`,
    ]);
  });

  it("ön seçim kayıtlı carinin kategorisinden gelir; kategori yoksa / cari eşleşmesi yoksa ön seçim yok", () => {
    render(review([
      doktor(),
      hasta(),
      hastane(),
      taraf("Yeni Kişi"),
      // Ad elle değişmiş: cari eşleşmesi düşmüş (client_id null), bayat kategoriye güvenilmez.
      taraf("Başka Biri", { matchCategory: "Doktor" }),
    ]));

    expect(cipler(DOKTOR)).toEqual(["Takip (doktor müvekkil)"]);
    expect(cipler(HASTA)).toEqual(["Takip (hasta vekilliği)"]);
    expect(cipler(HASTANE)).toEqual([]);
    expect(cipler("Yeni Kişi")).toEqual([]);
    expect(cipler("Başka Biri")).toEqual([]);
  });

  it("hizmeti olmayan onaylı müvekkilde Kaydet kapalı + satırda uyarı + kapı metni; seçilince açılır", () => {
    render(review([hastane()]));

    expect(saveButton().disabled).toBe(true);
    expect(uyari(HASTANE)?.textContent).toContain("Hizmet seçilmedi");
    expect(container.textContent).toContain(`Hizmet türü seçilmemiş müvekkil var: "${HASTANE}"`);

    hizmetDegistir(HASTANE, "Danışmanlık");

    expect(cipler(HASTANE)).toEqual(["Danışmanlık"]);
    expect(uyari(HASTANE)).toBeNull();
    expect(saveButton().disabled).toBe(false);
    expect(container.textContent).not.toContain("Hizmet türü seçilmemiş müvekkil var");
  });

  it("onaylanmamış (kayda gitmeyecek) müvekkil hizmet kapısını kapatmaz", () => {
    render(review([doktor(), hastane({ approved: false })]));

    expect(uyari(HASTANE)).toBeNull();
    // Kapı hizmetten değil, onaylanmamış taraf satırından kapalı.
    expect(container.textContent).not.toContain("Hizmet türü seçilmemiş müvekkil var");
    expect(container.textContent).toContain("Tüm taraf satırları onaylanmalı");
  });

  it("iki müvekkil AYRI seçilir: commit'te her taraf kendi hizmet_turleri kümesini taşır", async () => {
    render(review([doktor(), hastane(), karsiTaraf()]));
    // Listede SONRA gelen önce tıklanır → küme yine liste sırasında gider.
    hizmetDegistir(HASTANE, "Danışmanlık", "Lexis Rapor");

    const req = await save();
    expect(req.case.parties.map(p => [p.name, p.party_type, p.hizmet_turleri])).toEqual([
      [DOKTOR, "CLIENT", ["Takip (doktor müvekkil)"]],
      [HASTANE, "CLIENT", ["Lexis Rapor", "Danışmanlık"]],
      ["Mehmet Kaya", "COUNTER", undefined],
    ]);
    // Karşı taraf alanı HİÇ taşımaz (backend 422); eski maske de gönderilmez.
    expect(req.case.parties[2]).not.toHaveProperty("hizmet_turleri");
    expect(req.case).not.toHaveProperty("service_type");
    expect(toastApi.error).not.toHaveBeenCalled();
  });

  it("ön seçim değiştirilebilir; kaldırılan ön seçim geri GELMEZ ve Kaydet kapanır", () => {
    render(review([doktor()]));
    expect(saveButton().disabled).toBe(false);

    hizmetDegistir(DOKTOR, "Takip (doktor müvekkil)"); // ön seçimi kaldır

    expect(cipler(DOKTOR)).toEqual([]);
    expect(saveButton().disabled).toBe(true);
    expect(uyari(DOKTOR)).not.toBeNull();
  });

  it("hizmet seçmek onaylanmamış satırı kendiliğinden ONAYLAMAZ", () => {
    render(review([doktor(), hastane({ approved: false })]));

    hizmetDegistir(HASTANE, "Danışmanlık");

    expect(cipler(HASTANE)).toEqual(["Danışmanlık"]);
    const onay = container.querySelector(`[aria-label="${HASTANE} satırını onayla"]`);
    expect(onay?.getAttribute("aria-checked")).toBe("false");
  });

  it("'Aynı hizmetleri tüm müvekkillere uygula': ilk DOLU kümeyi diğer müvekkillere kopyalar, sonra tek tek değişir", async () => {
    render(review([hastane(), doktor(), hasta(), karsiTaraf()]));
    expect(tumuneUygula()?.textContent).toContain("Aynı hizmetleri tüm müvekkillere uygula");
    expect(tumuneUygula()!.disabled).toBe(false);

    act(() => tumuneUygula()!.click());

    // İlk satır (hastane) boştu; ilk DOLU seçici Doktor ön seçimi.
    for (const ad of [HASTANE, DOKTOR, HASTA]) expect(cipler(ad)).toEqual(["Takip (doktor müvekkil)"]);

    hizmetDegistir(HASTA, "Danışmanlık");
    expect(cipler(HASTA)).toEqual(["Takip (doktor müvekkil)", "Danışmanlık"]);
    expect(cipler(HASTANE)).toEqual(["Takip (doktor müvekkil)"]);

    const req = await save();
    expect(req.case.parties.map(p => p.hizmet_turleri)).toEqual([
      ["Takip (doktor müvekkil)"],
      ["Takip (doktor müvekkil)"],
      ["Takip (doktor müvekkil)", "Danışmanlık"],
      undefined,
    ]);
  });

  it("kısayol tek müvekkilde çizilmez; hiçbir seçici dolu değilken devre dışıdır", () => {
    render(review([doktor(), karsiTaraf()]));
    expect(tumuneUygula()).toBeNull();

    act(() => root!.unmount());
    root = createRoot(container);
    render(review([hastane(), taraf("Yeni Kişi")]));
    expect(tumuneUygula()).not.toBeNull();
    expect(tumuneUygula()!.disabled).toBe(true);
  });

  it("taslak hizmet seçimini korur: seçim diske yazılır (maske yazılmaz), devamda seçicide görünür", () => {
    render(review([hastane(), doktor()]));
    hizmetDegistir(HASTANE, "Danışmanlık", "Lexis Rapor");
    act(() => { window.dispatchEvent(new Event("pagehide")); }); // bekleyen taslak yazımını diske indirir

    const raw = sessionStorage.getItem("hukdok.intake-draft.v1") ?? "";
    expect(raw).not.toBe("");
    expect(raw).not.toContain("serviceMask");
    const saved = loadIntakeDraft()!.review;
    expect(saved.parties.map(p => p.hizmet_turleri)).toEqual([["Lexis Rapor", "Danışmanlık"], undefined]);

    // Yarım kalan taslaktan devam: aynı snapshot yeni bir inceleme adımına verilir.
    act(() => root!.unmount());
    root = createRoot(container);
    render(saved);
    expect(cipler(HASTANE)).toEqual(["Lexis Rapor", "Danışmanlık"]);
    expect(cipler(DOKTOR)).toEqual(["Takip (doktor müvekkil)"]); // dokunulmamış satır: ön seçim
    expect(saveButton().disabled).toBe(false);
  });

  it("enrich modunda (mevcut kart) seçici GİZLİ; apply isteği hizmet taşımaz", async () => {
    const enrichDraft = {
      ...draft,
      mode: "enrich",
      case: { id: 5, tracking_no: "YIL-0005-DR.A.YILMAZ-HUK", esas_no: "2026/5", court: null, updated_at: null },
    } as unknown as MergeDraft;
    render(review([doktor(), hastane()]), enrichDraft);

    expect(container.textContent).toContain("Mevcut dava zenginleştiriliyor");
    expect(seciciler()).toHaveLength(0);
    expect(container.querySelector("[data-testid=muvekkil-hizmet]")).toBeNull();
    expect(tumuneUygula()).toBeNull();
    // Hizmeti olmayan müvekkil zenginleştirmeyi kilitlemez (kural yalnız oluşturma kapısı).
    const guncelle = saveButton("Davayı Güncelle ve Arşivle");
    expect(guncelle.disabled).toBe(false);

    await act(async () => { guncelle.click(); });
    await waitFor(() => onApply.mock.calls.length === 1, "apply isteği atıldı");

    const req = onApply.mock.calls[0][0];
    expect(req.parties.map(p => p.name)).toEqual([DOKTOR, HASTANE]);
    for (const p of req.parties) expect(p).not.toHaveProperty("hizmet_turleri");
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("hizmet listesi BOŞKEN seçici çizilmez ve Kaydet kilitlenmez (backend ile aynı kural)", async () => {
    configApi.serviceTypes = [];
    render(review([hastane()]));

    expect(container.querySelector("[data-testid=muvekkil-hizmet]")).toBeNull();
    const req = await save();
    expect(req.case.parties.map(p => p.hizmet_turleri)).toEqual([[]]);
  });
});
