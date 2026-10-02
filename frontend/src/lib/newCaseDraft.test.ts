// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import {
  EMPTY_NEW_CASE_FORM,
  isNewCaseDraftDirty,
  isNewCaseDraftShape,
  NEW_CASE_DRAFT_KEY,
  NEW_CASE_DRAFT_MAX_AGE_MS,
  newCaseDraftStore,
  taslakIstekKimligi,
  type NewCaseDraftData,
} from "./newCaseDraft";

/** NewCase.tsx'in açılış durumu — bu hâl KİRLİ SAYILMAMALI. */
const pristine = (): NewCaseDraftData => ({
  caseStatus: "DERDEST",
  formData: { ...EMPTY_NEW_CASE_FORM },
  selectedLawyers: [],
  clients: [{ name: "", role: "Davacı" }],
  counterParties: [{ name: "", role: "Davalı" }],
  thirdParties: [],
});

beforeEach(() => sessionStorage.clear());

describe("isNewCaseDraftDirty", () => {
  it("dokunulmamış form kirli sayılmaz", () => {
    expect(isNewCaseDraftDirty(pristine())).toBe(false);
  });

  it("boş satır eklemek kirlilik üretmez", () => {
    const data = pristine();
    data.clients.push({ name: "", role: "Müdahil" });
    data.thirdParties.push({ name: "", role: "Tanık" });
    expect(isNewCaseDraftDirty(data)).toBe(false);
  });

  it("müvekkil adı girilince kirli olur", () => {
    const data = pristine();
    data.clients[0].name = "Ahmet Yılmaz";
    expect(isNewCaseDraftDirty(data)).toBe(true);
  });

  it("yalnız TC girilmiş karşı taraf da kirli sayılır", () => {
    const data = pristine();
    data.counterParties[0].tc_no = "12345678901";
    expect(isNewCaseDraftDirty(data)).toBe(true);
  });

  it("boşluktan ibaret isim kirlilik üretmez", () => {
    const data = pristine();
    data.clients[0].name = "   ";
    expect(isNewCaseDraftDirty(data)).toBe(false);
  });

  it("esas no gibi tek bir form alanı kirlilik üretir", () => {
    const data = pristine();
    data.formData.esasNo = "2026/17";
    expect(isNewCaseDraftDirty(data)).toBe(true);
  });

  // G253 (test taşıma): eski beklenti "hizmet maskesi (`formData.serviceType = "00100"`)
  // varsayılandan sapınca kirli olur" idi — maske kalktı, hizmet müvekkil satırının kümesi.
  it("müvekkil satırında hizmet seçilince kirli olur", () => {
    const data = pristine();
    data.clients[0].hizmet_turleri = ["Danışmanlık"];
    expect(isNewCaseDraftDirty(data)).toBe(true);
  });

  it("boş hizmet kümesi (seçim kaldırıldı) tek başına kirlilik üretmez", () => {
    const data = pristine();
    data.clients[0].hizmet_turleri = [];
    expect(isNewCaseDraftDirty(data)).toBe(false);
  });

  it("eski taslağın maske alanı (formData.serviceType) kirlilik saymaz", () => {
    const data = pristine();
    (data.formData as unknown as Record<string, string>).serviceType = "00100";
    expect(isNewCaseDraftDirty(data)).toBe(false);
  });

  it("durum DANIŞ'a çekilince kirli olur", () => {
    const data = pristine();
    data.caseStatus = "DANIŞ";
    expect(isNewCaseDraftDirty(data)).toBe(true);
  });

  it("avukat seçilince kirli olur", () => {
    const data = pristine();
    data.selectedLawyers = [{ name: "Av. X", lawyer_id: 3 }];
    expect(isNewCaseDraftDirty(data)).toBe(true);
  });
});

describe("isNewCaseDraftShape", () => {
  it("geçerli taslak kabul edilir", () => {
    expect(isNewCaseDraftShape(pristine())).toBe(true);
  });

  it.each([
    ["null", null],
    ["dizi olmayan clients", { ...pristine(), clients: "x" }],
    ["formData yok", { ...pristine(), formData: undefined }],
    ["caseStatus yok", { ...pristine(), caseStatus: 5 }],
  ])("bozuk şema reddedilir: %s", (_label, value) => {
    expect(isNewCaseDraftShape(value)).toBe(false);
  });
});

describe("newCaseDraftStore", () => {
  it("ofis numarası (tracking_no) taslakta TAŞINMAZ", () => {
    const data = pristine();
    data.clients[0].name = "Ahmet Yılmaz";
    newCaseDraftStore.save(data);
    const raw = sessionStorage.getItem(NEW_CASE_DRAFT_KEY) ?? "";
    expect(raw).not.toContain("tracking");
    expect(raw).not.toContain("caseId");
  });

  it("round-trip: taraflar ve form alanları korunur", () => {
    const data = pristine();
    data.formData.esasNo = "2026/17";
    data.counterParties[0] = { name: "Karşı Taraf A.Ş.", role: "Davalı", tc_no: "" };
    newCaseDraftStore.save(data);
    expect(newCaseDraftStore.load()?.data).toEqual(data);
  });

  // --- G253: müvekkil başına hizmet taslakla taşınır ---
  it("round-trip: her müvekkilin hizmet kümesi AYRI korunur", () => {
    const data = pristine();
    data.clients = [
      { name: "Dr. Ahmet Yılmaz", role: "Davalı", hizmet_turleri: ["Takip (doktor müvekkil)"] },
      { name: "Özel Şifa Hastanesi", role: "Davalı", hizmet_turleri: ["Danışmanlık", "Lexis Rapor"] },
      { name: "Ayşe Kaya", role: "Müdahil" }, // seçiciye dokunulmadı — alan yok kalır
    ];
    newCaseDraftStore.save(data);

    const loaded = newCaseDraftStore.load()?.data;
    expect(loaded?.clients.map(c => c.hizmet_turleri)).toEqual([
      ["Takip (doktor müvekkil)"],
      ["Danışmanlık", "Lexis Rapor"],
      undefined,
    ]);
    expect(loaded?.formData).not.toHaveProperty("serviceType");
  });

  // --- G237: istek kimliği taslakla taşınır ---
  it("istek kimliği taslakta taşınır ve geri okunur", () => {
    const data = { ...pristine(), istekKimligi: "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a" };
    data.clients[0].name = "Ahmet Yılmaz";
    newCaseDraftStore.save(data);
    expect(newCaseDraftStore.load()?.data.istekKimligi).toBe("3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a");
  });

  it("yalnız istek kimliği taşıyan boş form kirli sayılmaz", () => {
    expect(isNewCaseDraftDirty({ ...pristine(), istekKimligi: "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a" })).toBe(false);
  });

  it("taslakIstekKimligi: taslakta geçerli kimlik varsa O kullanılır", () => {
    const uret = () => "yeni-kimlik";
    expect(taslakIstekKimligi({ istekKimligi: "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a" }, uret))
      .toBe("3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a");
  });

  it("taslakIstekKimligi: eski taslakta (alan yok / bozuk) yeni kimlik üretilir", () => {
    const uret = () => "yeni-kimlik";
    expect(taslakIstekKimligi(pristine(), uret)).toBe("yeni-kimlik");
    expect(taslakIstekKimligi({ istekKimligi: "2026.00001.HUK" }, uret)).toBe("yeni-kimlik");
    expect(taslakIstekKimligi(null, uret)).toBe("yeni-kimlik");
    // Varsayılan üretici gerçek bir UUID verir
    expect(taslakIstekKimligi(pristine())).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });

  it("bayat taslak (sınırın ötesi) okunmaz", () => {
    newCaseDraftStore.save(pristine(), 0);
    expect(newCaseDraftStore.load(NEW_CASE_DRAFT_MAX_AGE_MS + 1)).toBeNull();
  });

  it("KVKK: taslak localStorage'a yazılmaz", () => {
    newCaseDraftStore.save(pristine());
    expect(localStorage.getItem(NEW_CASE_DRAFT_KEY)).toBeNull();
    expect(sessionStorage.getItem(NEW_CASE_DRAFT_KEY)).not.toBeNull();
  });
});
