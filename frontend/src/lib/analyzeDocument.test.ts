import { beforeEach, describe, expect, it, vi } from "vitest";

// apiClient mock'lanır — G002 testleri stream SÖZLEŞMESİNİ doğrular, ağı değil.
const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import { analyzeDocument, AnalysisFailedError } from "./analyzeDocument";

/** NDJSON satırlarını tek tek chunk olarak veren sahte Response. */
function streamResponse(lines: string[]): Response {
  const encoder = new TextEncoder();
  const chunks = lines.map(line => encoder.encode(line + "\n"));
  let i = 0;
  return {
    ok: true,
    statusText: "OK",
    body: {
      getReader: () => ({
        read: async () =>
          i < chunks.length
            ? { value: chunks[i++], done: false }
            : { value: undefined, done: true },
      }),
    },
  } as unknown as Response;
}

// FormData'ya konan değerin Blob olması şart değil — testte dosya içeriği okunmaz.
const dummyFile = { name: "dilekce.pdf" } as unknown as File;

const COMPLETE_LINE = JSON.stringify({
  status: "complete",
  process_id: "p-1",
  data: { tarih: "01.01.2026", ozet: "özet", esas_no: "2026/1" },
});

describe("analyzeDocument — failed olayı (G002 sözleşmesi)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("complete olayında analiz verisini ve process_id'yi döndürür", async () => {
    fetchMock.mockResolvedValue(streamResponse([COMPLETE_LINE]));

    const { analysisData, processId } = await analyzeDocument(dummyFile);

    expect(processId).toBe("p-1");
    expect(analysisData.esas_no).toBe("2026/1");
  });

  it("failed olayında error_ozet'i taşıyan AnalysisFailedError fırlatır", async () => {
    fetchMock.mockResolvedValue(
      streamResponse([
        JSON.stringify({
          status: "failed",
          error_ozet: "Yapay zekâ servisi şu an yoğun, birkaç dakika sonra deneyin.",
          error_kod: "gemini_saturated",
        }),
      ]),
    );

    const promise = analyzeDocument(dummyFile);

    await expect(promise).rejects.toBeInstanceOf(AnalysisFailedError);
    await expect(promise).rejects.toThrow(
      "Yapay zekâ servisi şu an yoğun, birkaç dakika sonra deneyin.",
    );
    await promise.catch((e: AnalysisFailedError) => {
      expect(e.code).toBe("gemini_saturated");
    });
  });

  it("etiket/özet eksikse varsayılan mesaj ve analysis_error koduyla reddeder", async () => {
    fetchMock.mockResolvedValue(streamResponse([JSON.stringify({ status: "failed" })]));

    await analyzeDocument(dummyFile).catch((e: AnalysisFailedError) => {
      expect(e).toBeInstanceOf(AnalysisFailedError);
      expect(e.message).toBe("Belge analizi tamamlanamadı.");
      expect(e.code).toBe("analysis_error");
    });
    expect.assertions(3);
  });

  it("failed'dan önce complete gelse bile veri DÖNMEZ (form varsayılanla dolmaz)", async () => {
    fetchMock.mockResolvedValue(
      streamResponse([
        COMPLETE_LINE,
        JSON.stringify({ status: "failed", error_ozet: "Şema doğrulanamadı.", error_kod: "schema_invalid" }),
      ]),
    );

    await expect(analyzeDocument(dummyFile)).rejects.toThrow("Şema doğrulanamadı.");
  });

  it("info mesajlarını iletir, ardından gelen failed akışı yine de reddeder", async () => {
    const onInfo = vi.fn();
    fetchMock.mockResolvedValue(
      streamResponse([
        JSON.stringify({ status: "info", message: "Belge okunuyor…" }),
        JSON.stringify({ status: "failed", error_ozet: "Analiz hatası.", error_kod: "analysis_error" }),
      ]),
    );

    await expect(analyzeDocument(dummyFile, undefined, { onInfo })).rejects.toThrow("Analiz hatası.");
    expect(onInfo).toHaveBeenCalledWith("Belge okunuyor…");
  });

  it("mevcut error olayı sözleşmesi korunur (düz Error)", async () => {
    fetchMock.mockResolvedValue(
      streamResponse([JSON.stringify({ status: "error", message: "Sunucu hatası" })]),
    );

    const promise = analyzeDocument(dummyFile);
    await expect(promise).rejects.toThrow("Sunucu hatası");
    await expect(promise).rejects.not.toBeInstanceOf(AnalysisFailedError);
  });
});
