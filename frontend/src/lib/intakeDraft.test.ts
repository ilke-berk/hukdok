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
    // G253 (test taşıma): taslak artık 5'li maske (eski `serviceMask: "00100"`) TAŞIMAZ;
    // hizmet müvekkil satırının kümesidir.
    hizmet_turleri: ["Takip (doktor müvekkil)", "Danışmanlık"],
  }],
  selectedLawyers: [{ name: "Av. X", lawyer_id: 3 }],
  // G237 (test taşıma): taslak artık ofis numarası (eski `trackingNo: "HD-2026-1"`)
  // TAŞIMAZ; yerine kayıt isteğinin kimliğini taşır.
  istekKimligi: "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a",
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

// G237: numarayı sunucu verir — taslak numara taşımaz, istek kimliği taşır.
describe("taslakta ofis numarası yok, istek kimliği var (G237)", () => {
  const eskiTaslakYaz = (reviewEk: Record<string, unknown>) => {
    const { istekKimligi: _kimlik, ...kimliksiz } = review;
    sessionStorage.setItem(INTAKE_DRAFT_KEY, JSON.stringify({
      version: 1,
      savedAt: new Date().toISOString(),
      draft,
      review: { ...kimliksiz, ...reviewEk },
    }));
  };

  it("kaydedilen taslakta numara alanı bulunmaz, kimlik aynen geri okunur", () => {
    saveIntakeDraft(draft, review);
    const raw = sessionStorage.getItem(INTAKE_DRAFT_KEY) ?? "";
    expect(raw).not.toContain("trackingNo");
    expect(loadIntakeDraft()?.review.istekKimligi).toBe("3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a");
  });

  it("eski sürümün numara taşıyan taslağı yüklenir ama numara ATILIR", () => {
    eskiTaslakYaz({ trackingNo: "D1.I_KUTLUK...0007.HUKUK.00100" });
    const loaded = loadIntakeDraft();
    expect(loaded).not.toBeNull();
    expect(loaded!.review).not.toHaveProperty("trackingNo");
    expect(JSON.stringify(loaded)).not.toContain("I_KUTLUK");
    // Taslağın geri kalanı korunur
    expect(loaded!.review.parties).toEqual(review.parties);
    // G253 (test taşıma): eski beklenti `review.serviceMask "00100"` korunur idi — maske
    // kalktı; korunan şey müvekkilin hizmet kümesidir.
    expect(loaded!.review.parties[0].hizmet_turleri).toEqual(["Takip (doktor müvekkil)", "Danışmanlık"]);
  });

  // G253: eski sürümün 5'li hizmet maskesi yüklemede ATILIR (yeni kümeye çevrilemez).
  it("eski sürümün hizmet maskesi (serviceMask) taşıyan taslağı yüklenir ama maske ATILIR", () => {
    eskiTaslakYaz({ serviceMask: "00100", istekKimligi: "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a" });
    const loaded = loadIntakeDraft();
    expect(loaded).not.toBeNull();
    expect(loaded!.review).not.toHaveProperty("serviceMask");
    expect(JSON.stringify(loaded)).not.toContain("00100");
    // Taslağın geri kalanı (kimlik, taraflar) korunur
    expect(loaded!.review.istekKimligi).toBe("3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a");
    expect(loaded!.review.parties).toEqual(review.parties);
  });

  it("kaydedilen taslakta maske alanı bulunmaz; iki müvekkilin kümeleri AYRI geri okunur", () => {
    const ikiMuvekkil: ReviewSnapshot = {
      ...review,
      parties: [
        review.parties[0],
        { ...review.parties[0], name: "Özel Şifa Hastanesi", client_id: 9, matchCategory: "Özel Hastane", hizmet_turleri: ["Lexis Rapor"] },
        { ...review.parties[0], name: "Mehmet Kaya", party_type: "COUNTER", client_id: null, hizmet_turleri: undefined },
      ],
    };
    saveIntakeDraft(draft, ikiMuvekkil);

    expect(sessionStorage.getItem(INTAKE_DRAFT_KEY) ?? "").not.toContain("serviceMask");
    expect(loadIntakeDraft()?.review.parties.map(p => p.hizmet_turleri)).toEqual([
      ["Takip (doktor müvekkil)", "Danışmanlık"],
      ["Lexis Rapor"],
      undefined,
    ]);
  });

  it("eski taslakta istek kimliği yoktur — alan boş döner (review yenisini üretir)", () => {
    eskiTaslakYaz({ trackingNo: "X" });
    expect(loadIntakeDraft()?.review.istekKimligi).toBeUndefined();
  });

  it("UUID olmayan (bozuk) kimlik taşınmaz", () => {
    eskiTaslakYaz({ istekKimligi: "D1.I_KUTLUK...0007.HUKUK.00100" });
    const loaded = loadIntakeDraft();
    expect(loaded).not.toBeNull();
    expect(loaded!.review).not.toHaveProperty("istekKimligi");
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
