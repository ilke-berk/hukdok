// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearIntakeDraft,
  debounce,
  INTAKE_DRAFT_KEY,
  loadIntakeDraft,
  markExpiredDocuments,
  saveIntakeDraft,
  type ReviewSnapshot,
} from "./intakeDraft";
import { resumeAllDrafts, suppressAllDrafts } from "./formDraft";
import type { MergeDraft } from "./caseIntake";

// Taslak testleri gerçek MergeDraft'ın tamamına ihtiyaç duymaz — yalnız
// load'un doğruladığı iskelet alanlar kurulur.
const draft = {
  fields: {},
  parties: [],
  policies: [],
  warnings: [],
  documents: [{ process_id: "p1", filename: "a.pdf", belge_turu_kodu: null, belge_turu_tahmini: null, ozet: null, status: "ok" }],
  duplicate_case: null,
  priors: {},
} as unknown as MergeDraft;

const review: ReviewSnapshot = {
  fieldStates: { esas_no: { value: "2024/1", aiValue: "2024/1", approved: true, touched: false } },
  parties: [{
    name: "Ahmet Yılmaz", role: "Davacı", party_type: "CLIENT", tc_no: "",
    client_id: 7, matchName: "AHMET YILMAZ", matchCategory: "Doktor",
    approved: true, fromDraft: true,
  }],
  serviceMask: "00100",
  selectedLawyers: [{ name: "Av. X", lawyer_id: 3 }],
  trackingNo: "HD-2026-1",
  selectedPolicies: { "k1": true },
  documents: [{ process_id: "p1", filename: "a.pdf", newName: "a.pdf", code: "ARA-KRR", ozet: "", expired: false }],
  sendEmail: false,
  emailTo: [],
};

beforeEach(() => sessionStorage.clear());

describe("saveIntakeDraft / loadIntakeDraft", () => {
  it("kaydedilen taslak aynen geri okunur (round-trip)", () => {
    saveIntakeDraft(draft, review);
    const loaded = loadIntakeDraft();
    expect(loaded?.version).toBe(1);
    expect(loaded?.review).toEqual(review);
    expect(loaded?.draft.documents[0].process_id).toBe("p1");
    expect(typeof loaded?.savedAt).toBe("string");
  });

  it("taslak yokken null döner", () => {
    expect(loadIntakeDraft()).toBeNull();
  });

  it("bozuk JSON temizlenir ve null döner", () => {
    sessionStorage.setItem(INTAKE_DRAFT_KEY, "{bozuk");
    expect(loadIntakeDraft()).toBeNull();
    expect(sessionStorage.getItem(INTAKE_DRAFT_KEY)).toBeNull();
  });

  it("şema uyuşmazlığı (eski versiyon) temizlenir ve null döner", () => {
    sessionStorage.setItem(INTAKE_DRAFT_KEY, JSON.stringify({ version: 0, draft: {}, review: {} }));
    expect(loadIntakeDraft()).toBeNull();
    expect(sessionStorage.getItem(INTAKE_DRAFT_KEY)).toBeNull();
  });

  it("clearIntakeDraft taslağı siler", () => {
    saveIntakeDraft(draft, review);
    clearIntakeDraft();
    expect(loadIntakeDraft()).toBeNull();
  });

  // G004 denetim düzeltmesi: sihirbaz taslağı (tc_no taşır) da logout
  // bastırmasına uyar — IntakeReviewStep'in pagehide flush'ı, çıkışta
  // clearAppStorage'ın sildiği taslağı geri yazamaz.
  it("suppressAllDrafts kuruluyken saveIntakeDraft diske YAZMAZ; resume geri açar", () => {
    suppressAllDrafts();
    try {
      saveIntakeDraft(draft, review);
      expect(sessionStorage.getItem(INTAKE_DRAFT_KEY)).toBeNull();
    } finally {
      resumeAllDrafts();
    }
    saveIntakeDraft(draft, review);
    expect(loadIntakeDraft()?.review).toEqual(review);
  });
});

describe("markExpiredDocuments", () => {
  it("expired dönen process_id'ler işaretlenir, diğerleri dokunulmaz", () => {
    const multi: ReviewSnapshot = {
      ...review,
      documents: [
        { process_id: "p1", filename: "a.pdf", newName: "a.pdf", code: "", ozet: "", expired: false },
        { process_id: "p2", filename: "b.pdf", newName: "b.pdf", code: "", ozet: "", expired: false },
      ],
    };
    const marked = markExpiredDocuments(multi, ["p2"]);
    expect(marked.documents.map(d => d.expired)).toEqual([false, true]);
    // orijinal mutasyona uğramaz
    expect(multi.documents[1].expired).toBe(false);
  });

  it("boş expired listesinde aynı referans döner", () => {
    expect(markExpiredDocuments(review, [])).toBe(review);
  });
});

describe("debounce", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("ardışık çağrılar tek koşuya iner, süre dolunca çalışır", () => {
    const fn = vi.fn();
    const d = debounce(fn, 1000);
    d(); d(); d();
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("flush bekletmeden çalıştırır ve bekleyen zamanlayıcıyı iptal eder", () => {
    const fn = vi.fn();
    const d = debounce(fn, 1000);
    d();
    d.flush();
    expect(fn).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(2000);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("cancel bekleyen çağrıyı düşürür", () => {
    const fn = vi.fn();
    const d = debounce(fn, 1000);
    d();
    d.cancel();
    vi.advanceTimersByTime(2000);
    expect(fn).not.toHaveBeenCalled();
  });
});
