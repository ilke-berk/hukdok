import { describe, expect, it } from "vitest";
import { ACCEPT_ATTRIBUTE, isValidFile } from "./fileValidation";

function makeFile(name: string, type: string): File {
  return new File(["x"], name, { type });
}

describe("isValidFile", () => {
  it.each([
    ["belge.pdf", "application/pdf"],
    ["belge.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    ["eski.doc", "application/msword"],
    ["tablo.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    ["eski.xls", "application/vnd.ms-excel"],
    ["tarama.tiff", "image/tiff"],
    ["foto.jpg", "image/jpeg"],
    ["ekran.png", "image/png"],
  ])("MIME ile kabul eder: %s", (name, type) => {
    expect(isValidFile(makeFile(name, type))).toBe(true);
  });

  it.each(["belge.udf", "tarama.tif", "tarama.tiff"])(
    "boş MIME'da uzantı fallback'i ile kabul eder: %s",
    (name) => {
      expect(isValidFile(makeFile(name, ""))).toBe(true);
    }
  );

  it.each([
    ["zararli.exe", "application/x-msdownload"],
    ["video.mp4", "video/mp4"],
    ["notlar.txt", "text/plain"],
  ])("reddeder: %s", (name, type) => {
    expect(isValidFile(makeFile(name, type))).toBe(false);
  });
});

describe("ACCEPT_ATTRIBUTE", () => {
  it("desteklenen tüm uzantıları içerir", () => {
    const exts = ACCEPT_ATTRIBUTE.split(",");
    for (const ext of [".pdf", ".udf", ".doc", ".docx", ".xls", ".xlsx", ".tif", ".tiff", ".jpg", ".jpeg", ".png"]) {
      expect(exts).toContain(ext);
    }
  });
});
