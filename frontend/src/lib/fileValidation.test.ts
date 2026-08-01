import { describe, expect, it } from "vitest";
import {
  ACCEPT_ATTRIBUTE,
  INTAKE_ACCEPT_ATTRIBUTE,
  isEmlFile,
  isValidFile,
  isValidIntakeFile,
} from "./fileValidation";

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

  it.each(["belge.udf", "TENSIP_TUTANAGI.udf.zip", "tarama.tif", "tarama.tiff"])(
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
    for (const ext of [".pdf", ".udf", ".udf.zip", ".doc", ".docx", ".xls", ".xlsx", ".tif", ".tiff", ".jpg", ".jpeg", ".png"]) {
      expect(exts).toContain(ext);
    }
  });

  it(".eml YALNIZ intake accept'inde bulunur — genel liste değişmez", () => {
    expect(ACCEPT_ATTRIBUTE.split(",")).not.toContain(".eml");
    expect(INTAKE_ACCEPT_ATTRIBUTE.split(",")).toContain(".eml");
  });
});

describe("intake .eml kabulü", () => {
  it("isValidFile .eml'i REDDEDER (genel yollar mail almamalı)", () => {
    expect(isValidFile(makeFile("atama.eml", "message/rfc822"))).toBe(false);
  });

  it("isValidIntakeFile .eml'i ve genel formatları kabul eder", () => {
    expect(isValidIntakeFile(makeFile("atama.eml", "message/rfc822"))).toBe(true);
    expect(isValidIntakeFile(makeFile("ATAMA.EML", ""))).toBe(true);
    expect(isValidIntakeFile(makeFile("belge.pdf", "application/pdf"))).toBe(true);
    expect(isValidIntakeFile(makeFile("zararli.exe", "application/x-msdownload"))).toBe(false);
  });

  it("isEmlFile uzantıya bakar, MIME'a güvenmez", () => {
    expect(isEmlFile(makeFile("mail.eml", ""))).toBe(true);
    expect(isEmlFile(makeFile("mail.pdf", "message/rfc822"))).toBe(false);
  });
});
