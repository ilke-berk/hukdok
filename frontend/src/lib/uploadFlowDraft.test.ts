// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import {
  isUploadFlowDraftDirty,
  isUploadFlowDraftShape,
  UPLOAD_FLOW_DRAFT_KEY,
  UPLOAD_FLOW_DRAFT_MAX_AGE_MS,
  uploadFlowDraftStore,
  type UploadFlowDraftData,
} from "./uploadFlowDraft";

const empty = (): UploadFlowDraftData => ({
  docType: "",
  filename: null,
  linkedCase: null,
});

beforeEach(() => sessionStorage.clear());

describe("isUploadFlowDraftDirty", () => {
  it("boş bağlam saklanmaya değmez", () => {
    expect(isUploadFlowDraftDirty(empty())).toBe(false);
  });

  it("yalnız dosya adı bağlam sayılmaz (dosya zaten kurtarılamıyor)", () => {
    expect(isUploadFlowDraftDirty({ ...empty(), filename: "karar.pdf" })).toBe(false);
  });

  it("belge türü seçilince saklanır", () => {
    expect(isUploadFlowDraftDirty({ ...empty(), docType: "ARA-KRR" })).toBe(true);
  });

  it("dava bağlanınca saklanır", () => {
    expect(isUploadFlowDraftDirty({
      ...empty(),
      linkedCase: { id: 7, tracking_no: "HD-1", esas_no: "2026/17" },
    })).toBe(true);
  });
});

describe("isUploadFlowDraftShape", () => {
  it("geçerli taslak kabul edilir", () => {
    expect(isUploadFlowDraftShape(empty())).toBe(true);
  });

  it.each([
    ["null", null],
    ["docType yok", { filename: null, linkedCase: null }],
    ["id'siz linkedCase", { ...empty(), linkedCase: { tracking_no: "HD-1" } }],
  ])("bozuk şema reddedilir: %s", (_label, value) => {
    expect(isUploadFlowDraftShape(value)).toBe(false);
  });
});

describe("uploadFlowDraftStore", () => {
  it("process_id ve analiz sonucu ASLA saklanmaz (bayat confirm tuzağı)", () => {
    uploadFlowDraftStore.save({
      docType: "ARA-KRR",
      filename: "karar.pdf",
      linkedCase: { id: 7, tracking_no: "HD-1", esas_no: "2026/17", court: "Ankara 1. ATM" },
    });
    const raw = sessionStorage.getItem(UPLOAD_FLOW_DRAFT_KEY) ?? "";
    expect(raw).not.toContain("process_id");
    expect(raw).not.toContain("processId");
    expect(raw).not.toContain("analysis");
    expect(raw).not.toContain("selectedPartyId");
  });

  it("round-trip: bağlam korunur", () => {
    const data: UploadFlowDraftData = {
      docType: "ARA-KRR",
      filename: "karar.pdf",
      linkedCase: { id: 7, tracking_no: "HD-1", esas_no: "2026/17" },
    };
    uploadFlowDraftStore.save(data);
    expect(uploadFlowDraftStore.load()?.data).toEqual(data);
  });

  it("bayat bağlam okunmaz (analiz yeniden koşsun)", () => {
    uploadFlowDraftStore.save({ ...empty(), docType: "ARA-KRR" }, 0);
    expect(uploadFlowDraftStore.load(UPLOAD_FLOW_DRAFT_MAX_AGE_MS + 1)).toBeNull();
  });
});
