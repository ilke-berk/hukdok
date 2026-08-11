// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import {
  EMPTY_NEW_CASE_FORM,
  isNewCaseDraftDirty,
  isNewCaseDraftShape,
  NEW_CASE_DRAFT_KEY,
  NEW_CASE_DRAFT_MAX_AGE_MS,
  newCaseDraftStore,
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

  it("hizmet maskesi varsayılandan sapınca kirli olur", () => {
    const data = pristine();
    data.formData.serviceType = "00100";
    expect(isNewCaseDraftDirty(data)).toBe(true);
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
