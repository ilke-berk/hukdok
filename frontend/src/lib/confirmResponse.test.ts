import { describe, expect, it } from "vitest";

import {
  confirmErrorMessage,
  extractConfirmFlags,
  type ConfirmHttpResponse,
} from "./confirmResponse";

const jsonResponse = (status: number, body: unknown): ConfirmHttpResponse => ({
  ok: status < 400,
  status,
  json: () => Promise.resolve(body),
});

// 504'te nginx'in döndürdüğü HTML gövde — json() SyntaxError'la reddeder.
const htmlResponse = (status: number): ConfirmHttpResponse => ({
  ok: false,
  status,
  json: () => Promise.reject(new SyntaxError("Unexpected token '<', \"<html>\" is not valid JSON")),
});

describe("confirmErrorMessage (Faz 4.3: ok önce, parse sonra)", () => {
  it("504'te gövde HİÇ okunmaz ve 'TEKRAR YÜKLEMEYİN' mesajı döner", async () => {
    let jsonCalled = false;
    const response: ConfirmHttpResponse = {
      ok: false,
      status: 504,
      json: () => {
        jsonCalled = true;
        return Promise.reject(new SyntaxError("okunmamalıydı"));
      },
    };

    const message = await confirmErrorMessage(response);

    expect(jsonCalled).toBe(false);
    expect(message).toContain("504");
    expect(message).toContain("TEKRAR YÜKLEMEYİN");
    expect(message).toContain("sunucuda sürüyor olabilir");
  });

  it("502 ve 503 de aynı 'tekrar yüklemeyin' ailesindedir", async () => {
    for (const status of [502, 503]) {
      const message = await confirmErrorMessage(htmlResponse(status));
      expect(message).toContain(String(status));
      expect(message).toContain("TEKRAR YÜKLEMEYİN");
    }
  });

  it("409'da backend detail'i OLDUĞU GİBİ döner (3-D 'işlem sürüyor' sözleşmesi)", async () => {
    const detail =
      "Bu belge için kayıt işlemi hâlâ sürüyor — lütfen TEKRAR GÖNDERMEYİN, birkaç dakika sonra deneyin.";
    expect(await confirmErrorMessage(jsonResponse(409, { detail }))).toBe(detail);
  });

  it("400 gibi uygulama hatalarında JSON detail gösterilir", async () => {
    expect(await confirmErrorMessage(jsonResponse(400, { detail: "Geçersiz belge türü." })))
      .toBe("Geçersiz belge türü.");
  });

  it("500 + JSON olmayan gövdede SyntaxError SIZMAZ, genel mesaja düşülür", async () => {
    const message = await confirmErrorMessage(htmlResponse(500));
    expect(message).toContain("500");
    expect(message).not.toContain("Unexpected token");
    expect(message).toContain("Kayıt işlemi sırasında bir hata oluştu");
  });

  it("detail string değilse (FastAPI validation dizisi) genel mesaja düşülür", async () => {
    const body = { detail: [{ loc: ["body", "file"], msg: "field required" }] };
    const message = await confirmErrorMessage(jsonResponse(422, body));
    expect(message).toContain("422");
    expect(message).toContain("Kayıt işlemi sırasında bir hata oluştu");
  });
});

describe("extractConfirmFlags (3-D replay + 3-F conversion_pending)", () => {
  it("idempotent_replay=true okunur", () => {
    const flags = extractConfirmFlags({ results: { idempotent_replay: true } });
    expect(flags.idempotentReplay).toBe(true);
    expect(flags.conversionPending).toBe(false);
  });

  it("conversion_pending + warning + archived_filename birlikte okunur", () => {
    const flags = extractConfirmFlags({
      results: {
        conversion_pending: true,
        conversion_warning: "Belge kaydedildi; PDF dönüşümü gece tamamlanacak.",
        archived_filename: "2026-08-11_dilekce.udf",
      },
    });
    expect(flags.conversionPending).toBe(true);
    expect(flags.conversionWarning).toContain("gece");
    expect(flags.archivedFilename).toBe("2026-08-11_dilekce.udf");
  });

  it("alan yokken güvenli varsayılanlar döner", () => {
    for (const input of [{}, { results: {} }, { results: null }, null, undefined, "bozuk"]) {
      const flags = extractConfirmFlags(input);
      expect(flags.idempotentReplay).toBe(false);
      expect(flags.conversionPending).toBe(false);
      expect(flags.conversionWarning).toBeNull();
      expect(flags.archivedFilename).toBeNull();
    }
  });

  it("truthy-ama-true-olmayan değerler bayrak saymaz, boş string'ler null olur", () => {
    const flags = extractConfirmFlags({
      results: { idempotent_replay: "true", conversion_pending: 1, conversion_warning: "  ", archived_filename: "" },
    });
    expect(flags.idempotentReplay).toBe(false);
    expect(flags.conversionPending).toBe(false);
    expect(flags.conversionWarning).toBeNull();
    expect(flags.archivedFilename).toBeNull();
  });
});
