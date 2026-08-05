import { describe, it, expect, vi } from "vitest";

// caseIntake.ts import zinciri apiClient üzerinden msalConfig'e (window)
// ulaşır — saf eşleme testleri için API istemcisi mock'lanır.
vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import { apiClient } from "@/lib/api";
import {
  type CaseIntakeApplyRequest,
  type EmlExpandResult,
  type MergeDraft,
  type MergePolicy,
  ApplyConflictError,
  applyIntake,
  base64ToFile,
  emlSummaryMessage,
  expandedEmlToFiles,
  mimeFromFilename,
  normalizeFileType,
  planIntakeAppend,
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
    judicial_unit: field(null),
    hasar_dosya_no: field(null),
    hukuk_no: field(null),
  } as MergeDraft["fields"],
  parties: [],
  policies: [],
  warnings: [],
  documents: [],
  duplicate_case: null,
  priors: {},
});

describe("buildFieldStates", () => {
  it("AI değerlerini ön-doldurur; tüm alanlar tiksiz başlar (boşlar dahil)", () => {
    const states = buildFieldStates(makeDraft());
    expect(states.esas_no).toEqual({
      value: "2026/123", aiValue: "2026/123", approved: false, touched: false,
    });
    // file_type sözlüğe normalize edilir
    expect(states.file_type.value).toBe("İdari Yargı");
    // Boş AI alanı da tiksiz gelir — kullanıcı doldurunca otomatik tiklenir
    expect(states.manevi_tazminat.approved).toBe(false);
    // draftKey'siz alanlar (avukat, notlar) boş başlar — ön-dolgu yok, tiksiz
    expect(states.responsible_lawyer_name.value).toBe("");
    expect(states.responsible_lawyer_name.approved).toBe(false);
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

  it("zorunlu alan boşken de tik ister; boş-onay ('bilgi elimde yok') sayacı tamamlar", () => {
    const states = buildFieldStates(makeDraft());
    const required = new Set(["esas_no", "manevi_tazminat"]);
    for (const s of Object.values(states)) {
      if (s.value !== "") s.approved = true;
    }
    // manevi_tazminat boş + zorunlu → onaysız complete olmaz
    expect(fieldApprovalProgress(states, required).complete).toBe(false);
    // Onay diyaloğundan geçip tiklendi → tamamlanır
    states.manevi_tazminat.approved = true;
    expect(fieldApprovalProgress(states, required).complete).toBe(true);
    // Zorunlu seti verilmezse eski davranış: boş alan sayılmaz
    states.manevi_tazminat.approved = false;
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

// --- .eml genişletme yardımcıları ---------------------------------------

// "PDF" → base64 (backend data_b64 alanının minyatürü)
const B64_PDF = btoa("%PDF-1.4 test");

const makeExpandResult = (over: Partial<EmlExpandResult> = {}): EmlExpandResult => ({
  body: { filename: "E-posta_govdesi.pdf", data_b64: B64_PDF },
  attachments: [
    { filename: "ustyazi_77.pdf", data_b64: B64_PDF },
    { filename: "dava_dilekcesi.udf", data_b64: B64_PDF },
  ],
  skipped: [
    { filename: "image001.png", reason: "inline görsel" },
    { filename: "belgeler.zip", reason: "uzantı desteklenmiyor (.zip)" },
  ],
  ...over,
});

describe("base64ToFile / expandedEmlToFiles", () => {
  it("base64 içeriği doğru MIME ile File'a çevirir", async () => {
    const file = base64ToFile(B64_PDF, "ustyazi_77.pdf");
    expect(file.name).toBe("ustyazi_77.pdf");
    expect(file.type).toBe("application/pdf");
    const text = new TextDecoder().decode(await file.arrayBuffer());
    expect(text).toBe("%PDF-1.4 test");
  });

  it("mimeFromFilename bilinen uzantıları eşler, bilinmeyene octet-stream düşer", () => {
    expect(mimeFromFilename("dilekce.UDF")).toBe("application/octet-stream");
    expect(mimeFromFilename("tablo.xlsx")).toBe("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    expect(mimeFromFilename("tarama.tiff")).toBe("image/tiff");
    expect(mimeFromFilename("bilinmeyen.qqq")).toBe("application/octet-stream");
  });

  it("gövdeyi önde tutarak tüm parçaları File listesine açar; gövdesiz de çalışır", () => {
    const files = expandedEmlToFiles(makeExpandResult());
    expect(files.map(f => f.name)).toEqual([
      "E-posta_govdesi.pdf", "ustyazi_77.pdf", "dava_dilekcesi.udf",
    ]);
    const noBody = expandedEmlToFiles(makeExpandResult({ body: null }));
    expect(noBody.map(f => f.name)).toEqual(["ustyazi_77.pdf", "dava_dilekcesi.udf"]);
  });
});

describe("emlSummaryMessage — skipped toast mantığı", () => {
  it("gövde + ek + atlanan parçaları nedenleriyle özetler", () => {
    expect(emlSummaryMessage(makeExpandResult())).toBe(
      "E-posta açıldı: gövde + 2 ek eklendi, 2 parça atlandı " +
      "(inline görsel, uzantı desteklenmiyor (.zip))",
    );
  });

  it("aynı nedeni tekrarlamaz, taşmayı belirtir", () => {
    const result = makeExpandResult({
      skipped: [
        { filename: "a.png", reason: "inline görsel" },
        { filename: "b.png", reason: "inline görsel" },
      ],
    });
    expect(emlSummaryMessage(result, 3)).toBe(
      "E-posta açıldı: gövde + 2 ek eklendi, 2 parça atlandı (inline görsel) " +
      "— 3 parça belge sınırına sığmadı",
    );
  });

  it("hiç parça eklenemediyse bunu söyler", () => {
    expect(emlSummaryMessage(makeExpandResult({ body: null, attachments: [], skipped: [] })))
      .toBe("E-posta açıldı: eklenebilir parça bulunamadı");
  });
});

// --- applyIntake — 409 stale_case ayrımı (sertleştirme İş 2) -------------

const applyReq = (): CaseIntakeApplyRequest => ({
  case_id: 55,
  expected_updated_at: "2026-08-01T12:00:00",
  fields: {},
  parties: [],
  documents: [],
  policies: [],
  options: { send_email: false, email_to: [] },
});

const mockResponse = (status: number, body: unknown) =>
  vi.mocked(apiClient.fetch).mockResolvedValueOnce({
    ok: status < 400,
    status,
    statusText: String(status),
    json: async () => body,
  } as unknown as Response);

describe("applyIntake — 409 ayrımı", () => {
  it("409'u ApplyConflictError olarak fırlatır (backend detail mesajıyla)", async () => {
    mockResponse(409, { detail: "Dava bu ekran açıldıktan sonra güncellendi." });
    await expect(applyIntake(applyReq())).rejects.toThrowError(ApplyConflictError);
    // İmza istek gövdesinde aynen gitmiş olmalı
    const call = vi.mocked(apiClient.fetch).mock.calls.at(-1)!;
    expect(JSON.parse(call[1]!.body as string).expected_updated_at)
      .toBe("2026-08-01T12:00:00");
  });

  it("diğer hatalar düz Error kalır (genel toast yolu)", async () => {
    mockResponse(500, { detail: "Dava güncellenemedi." });
    const err = await applyIntake(applyReq()).catch(e => e);
    expect(err).toBeInstanceOf(Error);
    expect(err).not.toBeInstanceOf(ApplyConflictError);
  });
});

describe("planIntakeAppend — MAX_INTAKE_FILES taşma davranışı", () => {
  const f = (name: string) => new File(["x"], name);

  it("ad+boyut dedup yapar (mevcut liste + aynı parti içi)", () => {
    const existing = [{ name: "a.pdf", size: 1 }];
    const plan = planIntakeAppend(existing, [f("a.pdf"), f("b.pdf"), f("b.pdf")], 15);
    expect(plan.accepted.map(x => x.name)).toEqual(["b.pdf"]);
    expect(plan.overflow).toBe(0);
  });

  it("sınırı aşan parçalardan sığan kadarını kabul eder, kalanını overflow sayar", () => {
    const existing = Array.from({ length: 13 }, (_, i) => ({ name: `e${i}.pdf`, size: 1 }));
    const plan = planIntakeAppend(existing, [f("x.pdf"), f("y.pdf"), f("z.pdf")], 15);
    expect(plan.accepted.map(x => x.name)).toEqual(["x.pdf", "y.pdf"]);
    expect(plan.overflow).toBe(1);
  });

  it("liste doluysa hiçbir şey eklemez, hepsi overflow", () => {
    const existing = Array.from({ length: 15 }, (_, i) => ({ name: `e${i}.pdf`, size: 1 }));
    const plan = planIntakeAppend(existing, [f("x.pdf")], 15);
    expect(plan.accepted).toEqual([]);
    expect(plan.overflow).toBe(1);
  });
});
