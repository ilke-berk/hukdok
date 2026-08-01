import { describe, expect, it, vi } from "vitest";

// caseIntake.ts import zinciri apiClient üzerinden msalConfig'e (window)
// ulaşır — saf fark listesi testleri için API istemcisi mock'lanır.
vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import type { MergeDraft, MergeField } from "@/lib/caseIntake";
import { INTAKE_FIELDS, type IntakeFieldState } from "@/lib/caseIntakeFields";
import {
  buildEnrichFields,
  confirmedFieldLabels,
  enrichApplySummary,
  enrichCurrentString,
  enrichFieldLabel,
  enrichRowGroup,
  selectEnrichParties,
} from "@/lib/intakeEnrich";

// =====================================================================
// Faz 7 — fark listesi saf yardımcıları (plan: vitest fark listesi reducer'ı)
// =====================================================================

const field = (over: Partial<MergeField> = {}): MergeField => ({
  value: null,
  agreement: null,
  confidence: null,
  candidates: [],
  sources: [],
  ...over,
});

const draftWith = (fields: Record<string, MergeField>): MergeDraft => ({
  fields: fields as MergeDraft["fields"],
  parties: [],
  policies: [],
  warnings: [],
  documents: [],
  duplicate_case: null,
  priors: {},
  mode: "enrich",
  case: { id: 55, tracking_no: "2024/0055", esas_no: "2024/123", court: null, status: "DERDEST" },
});

const def = (key: string) => {
  const hit = INTAKE_FIELDS.find(f => f.key === key);
  if (!hit) throw new Error(`tanımsız alan: ${key}`);
  return hit;
};

const state = (value: string, approved: boolean): IntakeFieldState => ({
  value,
  aiValue: value,
  approved,
  touched: false,
});

describe("enrichRowGroup", () => {
  it("fill ve conflict alanları action satırıdır", () => {
    const draft = draftWith({
      hasar_dosya_no: field({ value: "HSR-9", enrich: { status: "fill", current: null } }),
      esas_no: field({ value: "2025/7", enrich: { status: "conflict", current: "2024/123" } }),
    });
    expect(enrichRowGroup(def("hasar_dosya_no"), draft)).toBe("action");
    expect(enrichRowGroup(def("esas_no"), draft)).toBe("action");
  });

  it("confirm özet grubuna, keep ve enrich'siz alan gizliye düşer", () => {
    const draft = draftWith({
      esas_no: field({ value: "2024/123", enrich: { status: "confirm", current: "2024/123" } }),
      subject: field({ enrich: { status: "keep", current: "Tazminat" } }),
      hukuk_no: field(), // iki taraf da boş — enrich bilgisi yok
    });
    expect(enrichRowGroup(def("esas_no"), draft)).toBe("confirmed");
    expect(enrichRowGroup(def("subject"), draft)).toBe("hidden");
    expect(enrichRowGroup(def("hukuk_no"), draft)).toBe("hidden");
  });

  it("draftKey'siz (elle girilen) alanlar enrich'te daima gizlidir", () => {
    const draft = draftWith({});
    expect(enrichRowGroup(def("klasor_no_2"), draft)).toBe("hidden");
    expect(enrichRowGroup(def("notes"), draft)).toBe("hidden");
  });
});

describe("buildEnrichFields", () => {
  it("yalnız tik'li ve kayıtlı değerden farklı action alanları gönderir", () => {
    const draft = draftWith({
      esas_no: field({ value: "2025/7", enrich: { status: "conflict", current: "2024/123" } }),
      hasar_dosya_no: field({ value: "HSR-9", enrich: { status: "fill", current: null } }),
      court: field({ value: "ANKARA", enrich: { status: "fill", current: null } }),
    });
    const states = {
      esas_no: state("2025/7", true),
      hasar_dosya_no: state("HSR-9", false),   // tik yok — gönderilmez
      court: state("ANKARA", true),
    };
    expect(buildEnrichFields(states, draft)).toEqual({
      esas_no: "2025/7",
      court: "ANKARA",
    });
  });

  it("kayıtlı değerle aynı kalan tik'li alan gönderilmez (no-op)", () => {
    const draft = draftWith({
      esas_no: field({ value: "2025/7", enrich: { status: "conflict", current: "2024/123" } }),
    });
    // Kullanıcı adaydan kayıtlı değeri seçti — fark kalmadı
    const states = { esas_no: state("2024/123", true) };
    expect(buildEnrichFields(states, draft)).toEqual({});
  });

  it("boşaltılan alan null gönderir (silme), money sayısal karşılaştırır", () => {
    const draft = draftWith({
      esas_no: field({ value: "2025/7", enrich: { status: "conflict", current: "2024/123" } }),
      maddi_tazminat: field({ value: 50000, enrich: { status: "fill", current: 0 } }),
      manevi_tazminat: field({ value: 100000, enrich: { status: "conflict", current: "100000.0" } }),
    });
    const states = {
      esas_no: state("", true),
      maddi_tazminat: state("50000", true),
      manevi_tazminat: state("100000", true), // "100000" == 100000.0 → no-op
    };
    expect(buildEnrichFields(states, draft)).toEqual({
      esas_no: null,
      maddi_tazminat: 50000,
    });
  });

  it("confirm/keep/gizli alanlar tik'li olsa da asla gönderilmez", () => {
    const draft = draftWith({
      esas_no: field({ value: "2024/123", enrich: { status: "confirm", current: "2024/123" } }),
      subject: field({ enrich: { status: "keep", current: "Tazminat" } }),
    });
    const states = {
      esas_no: state("2024/123", true),
      subject: state("Başka Konu", true),
      klasor_no_2: state("ESKI-1", true),
    };
    expect(buildEnrichFields(states, draft)).toEqual({});
  });
});

describe("taraf seçimi (yalnız EKLEME)", () => {
  it("kayıtlı taraf ve tik'siz/adsız satırlar elenir", () => {
    const parties = [
      { approved: true, name: "Yeni Müdahil", existingId: null },
      { approved: true, name: "Ahmet YILMAZ", existingId: 71 },  // zaten davada
      { approved: false, name: "Tik'siz Kişi", existingId: null },
      { approved: true, name: "   ", existingId: null },
    ];
    expect(selectEnrichParties(parties).map(p => p.name)).toEqual(["Yeni Müdahil"]);
  });
});

describe("özet yardımcıları", () => {
  it("confirmedFieldLabels teyit edilen alan etiketlerini döner", () => {
    const draft = draftWith({
      esas_no: field({ value: "2024/123", enrich: { status: "confirm", current: "2024/123" } }),
      court: field({ value: "ANKARA", enrich: { status: "confirm", current: "ANKARA" } }),
    });
    expect(confirmedFieldLabels(draft)).toEqual(["Esas No", "Mahkeme"]);
  });

  it("enrichCurrentString null'u boş stringe çevirir", () => {
    const draft = draftWith({
      esas_no: field({ enrich: { status: "keep", current: "2024/123" } }),
      court: field({ enrich: { status: "fill", current: null } }),
    });
    expect(enrichCurrentString(def("esas_no"), draft)).toBe("2024/123");
    expect(enrichCurrentString(def("court"), draft)).toBe("");
  });

  it("enrichFieldLabel bilinen anahtarı etikete, bilinmeyeni aynen çevirir", () => {
    expect(enrichFieldLabel("esas_no")).toBe("Esas No");
    expect(enrichFieldLabel("taraf")).toBe("taraf");
  });

  it("enrichApplySummary sayaçları birleştirir", () => {
    expect(enrichApplySummary({ fields: 2, parties: 1, documents: 3, policies: 0 }))
      .toBe("2 alan uygulanacak · 1 taraf eklenecek · 3 belge arşivlenecek");
    expect(enrichApplySummary({ fields: 0, parties: 0, documents: 0, policies: 0 }))
      .toContain("seçilmedi");
  });
});
