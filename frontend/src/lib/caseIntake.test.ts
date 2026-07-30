import { describe, it, expect, vi } from "vitest";

// caseIntake.ts import zinciri apiClient üzerinden msalConfig'e (window)
// ulaşır — saf eşleme testleri için API istemcisi mock'lanır.
vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import {
  type MergeDraft,
  type MergePolicy,
  normalizeFileType,
  policyKey,
  selectCommitPolicies,
  toCommitPolicy,
} from "./caseIntake";
import { buildFieldStates, fieldApprovalProgress } from "./caseIntakeFields";

const makePolicy = (over: Partial<MergePolicy> = {}): MergePolicy => ({
  police_no: "P-123",
  police_turu: "ZORUNLU",
  sigorta_sirketi: "SOMPO SİGORTA",
  baslangic: "2025-01-01",
  bitis: "2026-01-01",
  retroaktif: "2020-01-01",
  sigortali: "AHMET YILMAZ",
  sigortali_kurum: "ÖZEL X HASTANESİ",
  teminat_limiti: 500000,
  client_id: 6250,
  source: "police.pdf",
  process_id: "pid-1",
  saved: false,
  relevant: true,
  ...over,
});

describe("toCommitPolicy — merge→commit anahtar eşlemesi (Faz 4 devir notu a)", () => {
  it("baslangic/bitis/retroaktif/source anahtarlarını ClientPolicyCreate adlarına çevirir", () => {
    const out = toCommitPolicy(makePolicy());
    expect(out).toEqual({
      client_id: 6250,
      police_no: "P-123",
      police_turu: "ZORUNLU",
      sigorta_sirketi: "SOMPO SİGORTA",
      baslangic_tarihi: "2025-01-01",
      bitis_tarihi: "2026-01-01",
      retroaktif_tarihi: "2020-01-01",
      sigortali_kurum: "ÖZEL X HASTANESİ",
      teminat_limiti: 500000,
      source_document: "police.pdf",
    });
    // Merge'e özgü anahtarlar sızmamalı
    expect(out).not.toHaveProperty("baslangic");
    expect(out).not.toHaveProperty("source");
    expect(out).not.toHaveProperty("saved");
    expect(out).not.toHaveProperty("sigortali");
  });

  it("client_id'siz poliçeyi göndermez", () => {
    expect(toCommitPolicy(makePolicy({ client_id: null }))).toBeNull();
  });

  it("zaten kayıtlı (saved=true) poliçeyi göndermez", () => {
    expect(toCommitPolicy(makePolicy({ saved: true }))).toBeNull();
  });
});

describe("selectCommitPolicies", () => {
  it("yalnız client_id'li ve kayıtsız poliçeleri eşleyip listeler", () => {
    const out = selectCommitPolicies([
      makePolicy(),
      makePolicy({ police_no: "P-456", saved: true }),
      makePolicy({ police_no: "P-789", client_id: null }),
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].police_no).toBe("P-123");
  });
});

describe("policyKey", () => {
  it("normalize poliçe no + dönem başı ile tekilleştirir", () => {
    expect(policyKey(makePolicy({ police_no: " p-123 " })))
      .toBe(policyKey(makePolicy({ police_no: "P-123" })));
    // Aynı numaralı yenileme (farklı dönem) ayrı anahtar kalır
    expect(policyKey(makePolicy({ baslangic: "2026-01-01" })))
      .not.toBe(policyKey(makePolicy()));
  });
});

describe("normalizeFileType", () => {
  it("çıkarım değerlerini PROCESS_MAP sözlüğüne çevirir", () => {
    expect(normalizeFileType("İdari")).toBe("İdari Yargı");
    expect(normalizeFileType("İdari Yargı")).toBe("İdari Yargı");
    expect(normalizeFileType("HUKUK")).toBe("Hukuk");
    expect(normalizeFileType("icra")).toBe("İcra");
    expect(normalizeFileType("Savcılık")).toBe("Savcılık");
  });

  it("bilinmeyen değeri olduğu gibi geçirir, boş değeri null döner", () => {
    expect(normalizeFileType("Tahkim")).toBe("Tahkim");
    expect(normalizeFileType(null)).toBeNull();
    expect(normalizeFileType("")).toBeNull();
  });
});

const field = (value: unknown) => ({
  value,
  agreement: 1,
  confidence: 1,
  candidates: [],
  sources: ["a.pdf"],
});

const makeDraft = (): MergeDraft => ({
  fields: {
    esas_no: field("2026/123"),
    court: field("ANKARA 1. ASLİYE HUKUK MAHKEMESİ"),
    file_type: field("İdari"),
    teblig_tarihi: field(null),
    sub_type_extra: field(null),
    subject: field("Tazminat davası"),
    maddi_tazminat: field(50000),
    manevi_tazminat: field(null),
    opening_date: field("2026-05-01"),
  } as MergeDraft["fields"],
  parties: [],
  policies: [],
  warnings: [],
  documents: [],
  duplicate_case: null,
  priors: {},
});

describe("buildFieldStates", () => {
  it("AI değerlerini ön-doldurur; boş olmayanlar onay bekler, boşlar onaylı sayılır", () => {
    const states = buildFieldStates(makeDraft());
    expect(states.esas_no).toEqual({
      value: "2026/123", aiValue: "2026/123", approved: false, touched: false,
    });
    // file_type sözlüğe normalize edilir
    expect(states.file_type.value).toBe("İdari Yargı");
    // Boş AI alanı tik istemez
    expect(states.manevi_tazminat.approved).toBe(true);
    // draftKey'siz alanlar (avukat, notlar) boş başlar — ön-dolgu yok
    expect(states.responsible_lawyer_name.value).toBe("");
    expect(states.responsible_lawyer_name.approved).toBe(true);
    // Sayısal değer string'e çevrilir
    expect(states.maddi_tazminat.value).toBe("50000");
  });
});

describe("fieldApprovalProgress", () => {
  it("boş olmayan tüm alanlar onaylanana dek complete=false", () => {
    const states = buildFieldStates(makeDraft());
    const before = fieldApprovalProgress(states);
    expect(before.complete).toBe(false);
    expect(before.required).toBeGreaterThan(0);
    expect(before.approved).toBe(0);

    for (const s of Object.values(states)) {
      if (s.value !== "") s.approved = true;
    }
    expect(fieldApprovalProgress(states).complete).toBe(true);
  });

  it("kullanıcının boşalttığı alan onay gerektirmez", () => {
    const states = buildFieldStates(makeDraft());
    for (const s of Object.values(states)) {
      if (s.value !== "") s.approved = true;
    }
    // esas_no'yu boşalt, onayını kaldır — boş alan onay istemediğinden hâlâ complete
    states.esas_no.value = "";
    states.esas_no.approved = false;
    expect(fieldApprovalProgress(states).complete).toBe(true);
  });
});
