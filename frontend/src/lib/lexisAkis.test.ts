// @vitest-environment jsdom
// lexisAkis (G264) — `POST /lexis-api/emsal-ara` NDJSON okuyucusu (`hukukbotApi.ask` deseni) ve `lexisServis`'in
// emsal uçları (`emsal-belge` JSON / multipart, `emsal-sonuc`, `emsal-durum`, inceleme paketi indirme). `apiClient`
// sahtedir (ağ ve MSAL yok): sahte `ReadableStream` okuyucusuyla satır tamponu, `failed` sonrası bitiş, akış
// sırasında iptal, akış başlamadan tipli HTTP hataları (401 / 409 / 429 / 503) sınanır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiClient: apiMock }));

import { EMSAL_HAT_KAPALI, EMSAL_KOSU_SURUYOR, EMSAL_KOTA_DOLDU, EMSAL_SERVIS_YOK, emsalAkisi, olayCoz, sonucCoz } from "./lexisAkis";
import { LexisApiError } from "./lexisApi";
import { LEXIS_DAVA_SERVISI_YOK, emsalBelgeKarttan, emsalBelgeYukle, emsalDurum, emsalIndir, emsalIndirUrl, emsalSonuc } from "./lexisServis";
import { LEXIS_YETKI_MESAJI } from "./lexisWord";
import type { EmsalAkisOlayi } from "@/types/lexis";

const SHA = "a".repeat(64);

function jsonYanit(status: number, govde: unknown, tur = "application/json"): Response {
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

/** Ham parçaları satır sınırına bakmadan veren sahte NDJSON akışı; `cancel` çağrısı izlenir. */
function akisYaniti(parcalar: (string | Uint8Array)[], tur = "application/x-ndjson") {
  const encoder = new TextEncoder();
  const kodlu = parcalar.map((p) => (typeof p === "string" ? encoder.encode(p) : p));
  let i = 0;
  let okuma = 0;
  const cancel = vi.fn(async () => undefined);
  const res = {
    ok: true,
    status: 200,
    headers: new Headers({ "Content-Type": tur }),
    body: {
      getReader: () => ({
        read: async () => {
          okuma += 1;
          return i < kodlu.length ? { value: kodlu[i++], done: false } : { value: undefined, done: true };
        },
        cancel,
      }),
    },
  } as unknown as Response;
  return { res, cancel, okumaSayisi: () => okuma };
}

const satir = (o: unknown) => JSON.stringify(o) + "\n";

async function hepsi(akis: AsyncIterable<EmsalAkisOlayi>): Promise<EmsalAkisOlayi[]> {
  const olaylar: EmsalAkisOlayi[] = [];
  for await (const o of akis) olaylar.push(o);
  return olaylar;
}

const ONERI = {
  id: 7001,
  belge_turu: "karar",
  mahkeme: "Örnekköy 1. İdare Mahkemesi",
  derece: "YEREL",
  esas_no: "2023/404",
  karar_no: "2025/118",
  karar_tarihi: "2025-03-12",
  uzmanlik: null,
  kart_id: 9004,
  kart_bagi: "TEK_KART",
  asamaya_bagli: true,
  metin_uzunluk: 1200,
  hukum_sinifi: "RED_ESASTAN",
  hukum_yonleri: ["RED"],
  sonuc_muvekkil: "RED_ESASTAN",
  sonuc_iliskisi: "AYNI",
  hukmedilen_maddi: [],
  hukmedilen_manevi: [],
  hukmedilen_birlesik: [],
  talep_maddi: [],
  talep_manevi: [],
  olay: null,
  maluliyet_orani: [],
  kusur_orani: [],
  dayanak_kurul: [],
  faiz: [],
  konular: {},
  puan: 91,
  gerekce: "Aynı olay.",
  alinti: "omuz takılmasının doğumun öngörülemeyen bir komplikasyonu olduğu bildirilmiştir",
  fark: "Aynı kart.",
  ayni_kart: true,
  kaynak: "model",
  fts_sira: 1,
  denetim_uyarilari: [],
  bilesenler: [],
};
const KUNYE = { uzmanlik: "Kadın Hastalıkları ve Doğum", tibbi_islem: "doğum", iddia: "Omuz takılması.", taraf_turu: "davacı hasta", yargi_yolu: "IDARE", sorgular: [{ metin: "omuz takılması", tur: "tibbi" }], istem_surumu: "2026-10-07a" };
const SAYILAR = { aday: 6, okunan: 6, dusen: 1, onbellek: 0, model_cagrisi: 7, token: 0, saniye: 1.5 };
const COMPLETE = { status: "complete", sha256: SHA, kunye: KUNYE, model: "sahte", sorgu_modeli: "sahte", oneriler: [ONERI], sayilar: SAYILAR };

beforeEach(() => {
  apiMock.fetch.mockReset();
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("emsalAkisi — NDJSON okuyucusu", () => {
  it("POST /lexis-api/emsal-ara gövdesi {sha256} (+ aday, yeniden yalnız verilince); olaylar tipli ve sıralı gelir", async () => {
    const { res } = akisYaniti([
      satir({ status: "info", asama: "kunye", kaynak: "model", sorgu: 3 }),
      satir({ status: "info", asama: "aday", aday: 6, sorgu: 3, ayni_kart: 1 }),
      satir({ status: "info", asama: "okuma", ilerleme: [1, 6], belge_id: 7001, kaynak: "model" }),
      satir({ status: "warning", asama: "denetim", belge_id: 7002, message: "aday düştü: alıntı kararda bulunamadı" }),
      satir({ status: "info", asama: "denetim", gecen: 1, dusen: 1 }),
      satir(COMPLETE),
    ]);
    apiMock.fetch.mockResolvedValueOnce(res);

    const olaylar = await hepsi(emsalAkisi(SHA));

    const [yol, init] = apiMock.fetch.mock.calls[0] as [string, RequestInit];
    expect(yol).toBe("/lexis-api/emsal-ara");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ sha256: SHA });
    expect(olaylar.map((o) => o.status)).toEqual(["info", "info", "info", "warning", "info", "complete"]);
    expect(olaylar[0]).toEqual({ status: "info", asama: "kunye", kaynak: "model", sorgu: 3 });
    expect(olaylar[2]).toEqual({ status: "info", asama: "okuma", ilerleme: [1, 6], belge_id: 7001, kaynak: "model" });
    expect(olaylar[3]).toEqual({ status: "warning", asama: "denetim", belge_id: 7002, message: "aday düştü: alıntı kararda bulunamadı" });
    const son = olaylar[5];
    expect(son.status).toBe("complete");
    if (son.status === "complete") {
      expect(son.oneriler).toHaveLength(1);
      expect(son.oneriler[0]).toMatchObject({ id: 7001, puan: 91, ayni_kart: true, alinti: ONERI.alinti });
      expect(son.kunye).toEqual(KUNYE);
      expect(son.sayilar).toEqual(SAYILAR);
      expect(son.model).toBe("sahte");
    }

    apiMock.fetch.mockResolvedValueOnce(akisYaniti([satir(COMPLETE)]).res);
    await hepsi(emsalAkisi(SHA, { aday: 50, yeniden: true }));
    expect(JSON.parse((apiMock.fetch.mock.calls[1][1] as RequestInit).body as string)).toEqual({ sha256: SHA, aday: 50, yeniden: true });
  });

  it("parça sınırında (çok baytlı karakterin içinden bile) bölünen satırlar birleşir; \\n'siz son satır işlenir", async () => {
    const tam = satir({ status: "info", asama: "kunye", mesaj: "Künye üretiliyor — ı harfi" }) + satir({ status: "warning", message: "ikinci" }) + JSON.stringify(COMPLETE);
    const bayt = new TextEncoder().encode(tam);
    const ortaBayt = bayt.indexOf(0xc4) + 1; // "ı" = C4 B1: iki baytın arasından kes
    expect(ortaBayt).toBeGreaterThan(1);
    const kesler = [5, 19, ortaBayt, 70, 100].filter((k) => k < bayt.length).sort((a, b) => a - b);
    const parcalar: Uint8Array[] = [];
    let onceki = 0;
    for (const k of [...new Set([...kesler, bayt.length])]) {
      parcalar.push(bayt.slice(onceki, k));
      onceki = k;
    }
    apiMock.fetch.mockResolvedValueOnce(akisYaniti(parcalar).res);

    const olaylar = await hepsi(emsalAkisi(SHA));

    expect(olaylar).toHaveLength(3);
    expect(olaylar[0]).toEqual({ status: "info", asama: "kunye", mesaj: "Künye üretiliyor — ı harfi" });
    expect(olaylar[1]).toEqual({ status: "warning", message: "ikinci" });
    expect(olaylar[2].status).toBe("complete");
  });

  it("bozuk satır, tanınmayan status ve sözleşme dışı info (aşamasız) atlanır; akış kırılmaz", async () => {
    apiMock.fetch.mockResolvedValueOnce(
      akisYaniti([
        "{bozuk json\n",
        satir({ status: "gelecekte_eklenecek", data: 1 }),
        satir({ status: "info", mesaj: "aşaması yok" }),
        satir({ status: "info", asama: "bilinmeyen_asama" }),
        satir({ type: "content", data: "Hukukbot sözleşmesi" }),
        satir({ status: "warning" }),
        satir(COMPLETE),
      ]).res,
    );

    const olaylar = await hepsi(emsalAkisi(SHA));

    expect(olaylar.map((o) => o.status)).toEqual(["warning", "complete"]);
    expect(olaylar[0]).toEqual({ status: "warning", message: "Uyarı" });
  });

  it("failed SON olaydır: sonrasındaki satırlar okunmaz, okuyucu bırakılır", async () => {
    const akis = akisYaniti([
      satir({ status: "info", asama: "kunye" }) +
        satir({ status: "failed", error_ozet: "Belgede aday bulunamadı.", error_kod: "aday_yok" }) +
        satir(COMPLETE) +
        satir({ status: "info", asama: "denetim" }),
    ]);
    apiMock.fetch.mockResolvedValueOnce(akis.res);

    const olaylar = await hepsi(emsalAkisi(SHA));

    expect(olaylar).toEqual([
      { status: "info", asama: "kunye" },
      { status: "failed", error_ozet: "Belgede aday bulunamadı.", error_kod: "aday_yok" },
    ]);
    expect(akis.cancel).toHaveBeenCalledTimes(1);
    // Satırlar tek parçada geldi: ikinci okuma hiç yapılmadı (failed'dan sonra done beklenmez).
    expect(akis.okumaSayisi()).toBe(1);
  });

  it("failed gövdesi eksikse yedek metin ve analysis_error kodu konur", () => {
    expect(olayCoz(JSON.stringify({ status: "failed" }))).toEqual({ status: "failed", error_ozet: "Emsal araması başlatılamadı.", error_kod: "analysis_error" });
    expect(olayCoz("")).toBeNull();
    expect(olayCoz("[1,2]")).toBeNull();
  });

  it("complete: öneri satırlarında eksik liste alanları boş listeyle dolar; id / puan olmayan satır düşer; öneri listesi yoksa olay yok sayılır", () => {
    const sonuc = sonucCoz({ ...COMPLETE, oneriler: [{ id: 7, puan: 50, hukum_yonleri: null, kunye: null }, { puan: 10 }, "bozuk"] });
    expect(sonuc?.oneriler).toHaveLength(1);
    expect(sonuc?.oneriler[0]).toMatchObject({ id: 7, puan: 50, gerekce: "", alinti: "", fark: "", ayni_kart: false, kaynak: "model", fts_sira: null, denetim_uyarilari: [], bilesenler: [], hukum_yonleri: [], konular: {} });
    expect(olayCoz(JSON.stringify({ status: "complete", sha256: SHA }))).toBeNull();
    // Künye ve sayılar eksikse boş / sıfır gelir (ekran `map` ve `toLocaleString` çağırır).
    const bos = sonucCoz({ status: "complete", oneriler: [] });
    expect(bos?.kunye).toEqual({ uzmanlik: null, tibbi_islem: null, iddia: "", taraf_turu: null, yargi_yolu: "DIGER", sorgular: [] });
    expect(bos?.sayilar).toEqual({ aday: 0, okunan: 0, dusen: 0, onbellek: 0, model_cagrisi: 0, token: 0, saniye: 0 });
  });

  it("akış SIRASINDA AbortSignal: okuyucu kapatılır, AbortError fırlar", async () => {
    const encoder = new TextEncoder();
    let bekleyen: ((v: { value: undefined; done: true }) => void) | null = null;
    let okuma = 0;
    const cancel = vi.fn(async () => {
      bekleyen?.({ value: undefined, done: true });
    });
    const res = {
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/x-ndjson" }),
      body: {
        getReader: () => ({
          read: () => {
            okuma += 1;
            if (okuma === 1) return Promise.resolve({ value: encoder.encode(satir({ status: "info", asama: "kunye" })), done: false });
            return new Promise((r) => {
              bekleyen = r;
            });
          },
          cancel,
        }),
      },
    } as unknown as Response;
    apiMock.fetch.mockResolvedValueOnce(res);
    const controller = new AbortController();

    const akis = emsalAkisi(SHA, { signal: controller.signal });
    expect((await akis.next()).value).toEqual({ status: "info", asama: "kunye" });
    const ikinci = akis.next();
    controller.abort();

    await expect(ikinci).rejects.toMatchObject({ name: "AbortError" });
    expect(cancel).toHaveBeenCalled();
  });

  it("tüketici erken çıkarsa (break) bağlantı bırakılır", async () => {
    const akis = akisYaniti([satir({ status: "info", asama: "kunye" }), satir({ status: "info", asama: "aday" })]);
    apiMock.fetch.mockResolvedValueOnce(akis.res);

    for await (const _olay of emsalAkisi(SHA)) break;

    expect(akis.cancel).toHaveBeenCalledTimes(1);
  });

  it("HTTP hatası akış başlamadan LexisApiError: 401 yetki, 409 koşu sürüyor, 429 kota, 503 hat kapalı; detail varsa o", async () => {
    apiMock.fetch.mockResolvedValueOnce(jsonYanit(401, { detail: "Oturum doğrulanamadı." }));
    await expect(hepsi(emsalAkisi(SHA))).rejects.toMatchObject({ status: 401, message: LEXIS_YETKI_MESAJI });

    apiMock.fetch.mockResolvedValueOnce(jsonYanit(409, { detail: "Bu kullanıcının bir emsal araması sürüyor; bitmesini bekleyin." }));
    await expect(hepsi(emsalAkisi(SHA))).rejects.toMatchObject({ status: 409, message: "Bu kullanıcının bir emsal araması sürüyor; bitmesini bekleyin." });
    apiMock.fetch.mockResolvedValueOnce(jsonYanit(409, {}));
    await expect(hepsi(emsalAkisi(SHA))).rejects.toMatchObject({ status: 409, message: EMSAL_KOSU_SURUYOR });

    apiMock.fetch.mockResolvedValueOnce(jsonYanit(429, null, "text/plain"));
    await expect(hepsi(emsalAkisi(SHA))).rejects.toMatchObject({ status: 429, message: EMSAL_KOTA_DOLDU });

    apiMock.fetch.mockResolvedValueOnce(jsonYanit(503, { detail: "Emsal ajan hattı bu kurulumda kapalı." }));
    const hata = await hepsi(emsalAkisi(SHA)).catch((e) => e);
    expect(hata).toBeInstanceOf(LexisApiError);
    expect(hata).toMatchObject({ status: 503, message: EMSAL_HAT_KAPALI });

    apiMock.fetch.mockResolvedValueOnce(jsonYanit(404, { detail: "Belge kaydı bulunamadı." }));
    await expect(hepsi(emsalAkisi(SHA))).rejects.toMatchObject({ status: 404, message: "Belge kaydı bulunamadı." });
    // Proxy ucu tanımıyor: istek SPA'ya düştü (200 + HTML) ya da 502.
    apiMock.fetch.mockResolvedValueOnce(akisYaniti([], "text/html").res);
    await expect(hepsi(emsalAkisi(SHA))).rejects.toMatchObject({ status: 502, message: EMSAL_SERVIS_YOK });
    apiMock.fetch.mockResolvedValueOnce(jsonYanit(502, null, "text/html"));
    await expect(hepsi(emsalAkisi(SHA))).rejects.toMatchObject({ status: 502, message: EMSAL_SERVIS_YOK });
    apiMock.fetch.mockRejectedValueOnce(new TypeError("ağ yok"));
    await expect(hepsi(emsalAkisi(SHA))).rejects.toMatchObject({ status: 0, message: EMSAL_SERVIS_YOK });
    expect(EMSAL_SERVIS_YOK).toBe(LEXIS_DAVA_SERVISI_YOK);
  });

  it("istek öncesi iptal edilmiş sinyal fetch'e iletilir (ağ iptali)", async () => {
    apiMock.fetch.mockRejectedValueOnce(new DOMException("aborted", "AbortError"));
    const controller = new AbortController();
    controller.abort();
    await expect(hepsi(emsalAkisi(SHA, { signal: controller.signal }))).rejects.toMatchObject({ name: "AbortError" });
    expect((apiMock.fetch.mock.calls[0][1] as RequestInit).signal).toBe(controller.signal);
  });
});

describe("lexisServis — emsal uçları", () => {
  const BELGE = { sha256: SHA, kaynak: "kart", bicim: "pdf", boyut: 120000, sayfa: 6, metin_uzunluk: 9000, bolumler: [], maske_dokumu: { bilinen: 2, kalip: 1, ogrenilen: 0 }, case_id: 501, hukdok_belge_id: 101, yukleme: "2026-10-07T20:00:00+00:00", mevcut: false, arsiv: "gerekmiyor", sharepoint_url: null };

  it("kart belgesi JSON {case_id, belge_id} ile, yükleme multipart `dosya` (+ case_id) ile gider; JSON başlığı FormData'ya konmaz", async () => {
    apiMock.fetch.mockResolvedValueOnce(jsonYanit(200, BELGE));
    expect(await emsalBelgeKarttan(501, 101)).toEqual(BELGE);
    let [yol, init] = apiMock.fetch.mock.calls[0] as [string, RequestInit];
    expect(yol).toBe("/lexis-api/emsal-belge");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ case_id: 501, belge_id: 101 });

    const dosya = new File(["%PDF-1.4"], "dilekce.pdf", { type: "application/pdf" });
    apiMock.fetch.mockResolvedValueOnce(jsonYanit(200, { ...BELGE, kaynak: "yukleme", hukdok_belge_id: null }));
    expect((await emsalBelgeYukle(dosya, 501)).kaynak).toBe("yukleme");
    [yol, init] = apiMock.fetch.mock.calls[1] as [string, RequestInit];
    expect(yol).toBe("/lexis-api/emsal-belge");
    expect(init.body).toBeInstanceOf(FormData);
    const govde = init.body as FormData;
    expect((govde.get("dosya") as File).name).toBe("dilekce.pdf");
    expect(govde.get("case_id")).toBe("501");
    expect(init.headers).toBeUndefined();

    // Kartsız yüklemede `case_id` alanı hiç gitmez.
    apiMock.fetch.mockResolvedValueOnce(jsonYanit(200, { ...BELGE, kaynak: "yukleme", case_id: null }));
    await emsalBelgeYukle(dosya, null);
    expect(((apiMock.fetch.mock.calls[2][1] as RequestInit).body as FormData).has("case_id")).toBe(false);
  });

  it("`/emsal-belge` hata deseni `detail: {kod, mesaj}` mesajıyla gelir", async () => {
    apiMock.fetch.mockResolvedValueOnce(jsonYanit(422, { detail: { kod: "metin_yok", mesaj: "Belgede metin katmanı yok (taranmış belge); OCR yapılmıyor." } }));
    await expect(emsalBelgeKarttan(501, 101)).rejects.toMatchObject({ status: 422, message: "Belgede metin katmanı yok (taranmış belge); OCR yapılmıyor." });
  });

  it("emsal-sonuc ve emsal-durum GET ile gider", async () => {
    apiMock.fetch.mockResolvedValueOnce(jsonYanit(200, { ...COMPLETE }));
    expect((await emsalSonuc(SHA)).oneriler).toHaveLength(1);
    expect(apiMock.fetch.mock.calls[0][0]).toBe(`/lexis-api/emsal-sonuc/${SHA}`);
    const durum = { acik: true, kip: "sahte", neden: null, sorgu_modeli: "sahte", okuyucu_modeli: "sahte", aday: 30, eszamanli: 6, karar_karakter: 20000, gunluk_token: 0, istem_surumu: "2026-10-07a", kullanilan_token: 0, acik_is: false };
    apiMock.fetch.mockResolvedValueOnce(jsonYanit(200, durum));
    expect(await emsalDurum()).toEqual(durum);
    expect(apiMock.fetch.mock.calls[1][0]).toBe("/lexis-api/emsal-durum");
    expect((apiMock.fetch.mock.calls[1][1] as RequestInit).method).toBe("GET");
  });

  describe("emsalIndir — inceleme paketi", () => {
    const createUrl = vi.fn(() => "blob:paket");
    const revokeUrl = vi.fn();
    let tiklamalar: { href: string; download: string }[];

    beforeEach(() => {
      tiklamalar = [];
      createUrl.mockClear();
      revokeUrl.mockClear();
      (URL as unknown as { createObjectURL: unknown }).createObjectURL = createUrl;
      (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = revokeUrl;
      vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
        tiklamalar.push({ href: this.getAttribute("href") ?? "", download: this.download });
      });
    });

    it("Bearer'lı fetch → blob → <a download>; ad Content-Disposition'dan, URL serbest bırakılır", async () => {
      expect(emsalIndirUrl(SHA)).toBe(`/lexis-api/emsal-sonuc/${SHA}/indir`);
      const blob = new Blob(["PK"], { type: "application/zip" });
      apiMock.fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Type": "application/zip", "Content-Disposition": `attachment; filename="inceleme_${SHA.slice(0, 12)}.zip"` }),
        blob: async () => blob,
      } as unknown as Response);

      expect(await emsalIndir(SHA)).toBe(`inceleme_${SHA.slice(0, 12)}.zip`);
      expect(apiMock.fetch.mock.calls[0][0]).toBe(emsalIndirUrl(SHA));
      expect(createUrl).toHaveBeenCalledWith(blob);
      expect(tiklamalar).toEqual([{ href: "blob:paket", download: `inceleme_${SHA.slice(0, 12)}.zip` }]);
      expect(revokeUrl).toHaveBeenCalledWith("blob:paket");
      expect(document.querySelector("a[download]")).toBeNull();
    });

    it("sonuç yoksa (ya da uç kurulu değilse) 404 LexisApiError; blob oluşmaz", async () => {
      apiMock.fetch.mockResolvedValueOnce(jsonYanit(404, { detail: "Sonuç bulunamadı." }));
      await expect(emsalIndir(SHA)).rejects.toMatchObject({ status: 404, message: "Sonuç bulunamadı." });
      apiMock.fetch.mockResolvedValueOnce(jsonYanit(404, null, "text/html")); // proxy allowlist dışı: nginx 404
      await expect(emsalIndir(SHA)).rejects.toMatchObject({ status: 404, message: "İnceleme paketi bulunamadı." });
      expect(createUrl).not.toHaveBeenCalled();
      expect(tiklamalar).toEqual([]);
    });
  });
});
