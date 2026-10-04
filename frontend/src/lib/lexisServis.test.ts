// Gerçek dava kipi — `lexisApi`'nin dosya bölgesi yöntemleri Lexis servisine gider (`lexisServis.ts`), taslak
// yazımı bağlı değildir, diğer sekmeler örnek veride kalır. `apiClient` sahtedir (ağ ve MSAL yok).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiClient: apiMock }));

import { GERCEK_EMSAL_EKLE_YOK, GERCEK_TASLAK_YOK, lexisApi, ornekDurumuSifirla, ornekGecikmeAyarla, veriKipi, veriKipiAyarla } from "./lexisApi";
import { LEXIS_DAVA_SERVISI_YOK } from "./lexisServis";
import { LEXIS_YETKI_MESAJI } from "./lexisWord";
import type { LexisAkisOlayi } from "@/types/lexis";

function yanit(status: number, govde: unknown, tur = "application/json"): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "Content-Type": tur }),
    json: async () => {
      if (tur !== "application/json") throw new Error("JSON değil");
      return govde;
    },
  } as unknown as Response;
}

const DAVA = { case_id: 501, ofis_no: "ANADOLU-9001-DR.ORNEK-HUK", sirket: "ANADOLU" };

beforeEach(() => {
  ornekDurumuSifirla();
  ornekGecikmeAyarla(0);
  apiMock.fetch.mockReset();
  veriKipiAyarla("gercek");
});

afterEach(() => veriKipiAyarla("ornek"));

describe("gerçek dava kipi", () => {
  it("dava arama, dosya ve emsal önerisi servise gider", async () => {
    apiMock.fetch.mockResolvedValueOnce(yanit(200, [DAVA]));
    expect(await lexisApi.davaAra("  2025/77 ")).toEqual([DAVA]);
    expect(apiMock.fetch.mock.calls[0][0]).toBe("/lexis-api/davalar?q=2025%2F77");

    apiMock.fetch.mockResolvedValueOnce(yanit(200, { dava: DAVA, belgeler: [] }));
    expect(await lexisApi.dosyaGetir(501)).toEqual({ dava: DAVA, belgeler: [] });
    expect(apiMock.fetch.mock.calls[1][0]).toBe("/lexis-api/dosya/501");

    apiMock.fetch.mockResolvedValueOnce(yanit(200, []));
    const istek = { case_id: 501, sirket: "ANADOLU" as const, rapor_turu: "ANA" as const, k: 3 };
    expect(await lexisApi.emsalOner(istek)).toEqual([]);
    const [yol, init] = apiMock.fetch.mock.calls[2] as [string, RequestInit];
    expect(yol).toBe("/lexis-api/emsal-oner");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(istek);
  });

  it("örnek kipte servise hiç gidilmez", async () => {
    veriKipiAyarla("ornek");
    expect((await lexisApi.davaAra("")).map((d) => d.case_id)).toContain(9001);
    expect(apiMock.fetch).not.toHaveBeenCalled();
    expect(veriKipi()).toBe("ornek");
  });

  it("servisin hatası kendi metniyle, proxy hatası 'servise ulaşılamadı' ile gelir", async () => {
    apiMock.fetch.mockResolvedValueOnce(yanit(503, { detail: "Emsal kütüphanesi sunucuda yok; öneri yapılamadı." }));
    await expect(lexisApi.emsalOner({ case_id: 501, sirket: null, rapor_turu: "ANA" })).rejects.toMatchObject({
      status: 503,
      message: "Emsal kütüphanesi sunucuda yok; öneri yapılamadı.",
    });
    for (const status of [404, 502, 504]) {
      apiMock.fetch.mockResolvedValueOnce(yanit(status, null, "text/html"));
      await expect(lexisApi.dosyaGetir(501)).rejects.toMatchObject({ status, message: LEXIS_DAVA_SERVISI_YOK });
    }
    apiMock.fetch.mockResolvedValueOnce(yanit(200, null, "text/html")); // istek SPA'ya düşmüş
    await expect(lexisApi.davaAra("x")).rejects.toMatchObject({ status: 502, message: LEXIS_DAVA_SERVISI_YOK });
    apiMock.fetch.mockResolvedValueOnce(yanit(401, { detail: "Oturum doğrulanamadı." }));
    await expect(lexisApi.davaAra("x")).rejects.toMatchObject({ status: 401, message: LEXIS_YETKI_MESAJI });
    apiMock.fetch.mockRejectedValueOnce(new TypeError("ağ yok"));
    await expect(lexisApi.davaAra("x")).rejects.toMatchObject({ status: 0, message: LEXIS_DAVA_SERVISI_YOK });
  });

  it("taslak yazımı ve elle emsal ekleme henüz bağlı değildir; diğer sekmeler örnek veride kalır", async () => {
    const olaylar: LexisAkisOlayi[] = [];
    const istek = { case_id: 501, sirket: null, rapor_turu: "ANA" as const, iskelet: "KISA" as const, belge_idleri: [], emsal_sha: [] };
    for await (const olay of lexisApi.taslakYaz(istek)) olaylar.push(olay);
    expect(olaylar).toEqual([{ status: "failed", error_ozet: GERCEK_TASLAK_YOK, error_kod: "analysis_error" }]);
    await expect(lexisApi.emsalPuanla(501, "a")).rejects.toMatchObject({ status: 501, message: GERCEK_EMSAL_EKLE_YOK });
    expect((await lexisApi.profiller()).length).toBeGreaterThan(0);
    expect(apiMock.fetch).not.toHaveBeenCalled();
  });
});
