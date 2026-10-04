// Gerçek dava kipi — `lexisApi`'nin dosya bölgesi yöntemleri Lexis servisine gider (`lexisServis.ts`), taslak
// yazımı bağlı değildir, diğer sekmeler örnek veride kalır. `apiClient` sahtedir (ağ ve MSAL yok).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiClient: apiMock }));

import { lexisApi, ornekDurumuSifirla, ornekGecikmeAyarla, veriKipi, veriKipiAyarla } from "./lexisApi";
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

  const DOSYA = { dava: DAVA, hasar_no: "99000111", hukuk_no: null, belgeler: [], celiskiler: [] };
  const MUALLAK = { maddi: null, manevi: null, dayanak: "YOK", dayanak_satirlari: [], kusur_tespiti: "BELIRSIZ", risk_duzeyi: "BELIRSIZ", teminat: "BELIRSIZ", uyarilar: [] };
  const ISKELET = {
    etiketli: { hasar: [{ alan: "sigortali", etiket: "Sigortalı", deger: "Dr. Örnek Bir", zorunlu: true, kaynak: "KART" }] },
    ozet: {},
    degerlendirme: { giris: "Tarafımıza iletilen belge ve bilgiler ile yapılan inceleme neticesinde;", maddeler: [{ metin: "[…] muallak", tur: "KALIP", dayanak_bolum: null, dayanak_alinti: null }], sulh_uygunluk: "", muallak_gerekcesi: "" },
    muallak: MUALLAK,
  };
  const ISTEK = { case_id: 501, sirket: "QUICK" as const, rapor_turu: "ANA" as const, iskelet: "KISA" as const, belge_idleri: [1], emsal_sha: [] };

  /** Yola göre yanıt veren sahte servis. */
  function servisKur(ek: Record<string, Response> = {}) {
    apiMock.fetch.mockImplementation(async (yol: string) => {
      const uc = yol.replace("/lexis-api", "").split("?")[0];
      return ek[uc] ?? { "/iskelet": yanit(200, ISKELET), "/dosya/501": yanit(200, DOSYA), "/karar-bankasi": yanit(200, []), "/muallak-oner": yanit(200, { ...MUALLAK, manevi: 40000, dayanak: "EMSAL" }) }[uc] ?? yanit(404, null, "text/html");
    });
  }

  it("taslak iskelet olarak gelir: künye karttan, özet boş; akış complete ile biter", async () => {
    servisKur();
    const olaylar: LexisAkisOlayi[] = [];
    for await (const olay of lexisApi.taslakYaz(ISTEK)) olaylar.push(olay);

    const [yol, init] = apiMock.fetch.mock.calls[0] as [string, RequestInit];
    expect(yol).toBe("/lexis-api/iskelet");
    expect(JSON.parse(init.body as string)).toEqual({ case_id: 501, sirket: "QUICK", rapor_turu: "ANA", iskelet: "KISA" }); // belge/emsal GİTMEZ
    expect(olaylar.filter((o) => o.status === "bolum").map((o) => (o.status === "bolum" ? o.bolum : ""))).toEqual(["hasar", "iddia", "uzman_gorusu", "degerlendirme"]);
    expect(olaylar.find((o) => o.status === "bolum" && o.bolum === "hasar")).toMatchObject({ etiketli: ISKELET.etiketli.hasar });
    expect(olaylar.find((o) => o.status === "muallak")).toMatchObject({ oneri: MUALLAK });
    const son = olaylar[olaylar.length - 1];
    expect(son.status).toBe("complete");
    // Boş özet bölümleri ve doldurulmamış son madde denetimde uyarı olarak gelir (insan yazacak).
    expect(son.status === "complete" ? son.uyarilar.map((u) => u.kod) : []).toEqual(expect.arrayContaining(["BOLUM_BOS"]));
  });

  it("iskelet alınamazsa akış failed ile biter; servisin metni gösterilir", async () => {
    servisKur({ "/iskelet": yanit(404, { detail: "Dava kartı bulunamadı." }) });
    const olaylar: LexisAkisOlayi[] = [];
    for await (const olay of lexisApi.taslakYaz(ISTEK)) olaylar.push(olay);
    expect(olaylar[olaylar.length - 1]).toEqual({ status: "failed", error_ozet: "Dava kartı bulunamadı.", error_kod: "analysis_error" });
  });

  it("kütüphane taraması, tek rapor, karar bankası ve elle emsal puanlaması servise gider", async () => {
    const kayit = { okuma: { sha256: "a", bolumler: { iddia: "[HASTA] iddiası." }, kararlar: [] }, etiketler: {}, klasor: "a", dosya_no: "9.2001" };
    const emsal = { kayit, puan: 5, bilesenler: [], gerekce: "aynı şirket" };
    servisKur({ "/kutuphane": yanit(200, [kayit]), "/rapor/a": yanit(200, kayit), "/emsal-puanla": yanit(200, emsal) });

    const filtre = { sirket: "AXA" as const, metin: "yanık" };
    expect(await lexisApi.kutuphaneAra(filtre)).toEqual([kayit]);
    let [yol, init] = apiMock.fetch.mock.calls[0] as [string, RequestInit];
    expect(yol).toBe("/lexis-api/kutuphane"); // arama metni URL'de değil gövdededir
    expect(JSON.parse(init.body as string)).toEqual(filtre);

    expect(await lexisApi.raporGetir("a")).toEqual(kayit);
    expect(apiMock.fetch.mock.calls[1][0]).toBe("/lexis-api/rapor/a");
    expect(await lexisApi.kararBankasi()).toEqual([]);
    expect(apiMock.fetch.mock.calls[2][0]).toBe("/lexis-api/karar-bankasi");

    // Puanlama dosyanın kartındaki şirket ve rapor türüyle istenir (dosya bellekte yoksa önce getirilir).
    expect(await lexisApi.emsalPuanla(501, "a")).toEqual(emsal);
    const cagrilar = apiMock.fetch.mock.calls.map((c) => c[0] as string);
    expect(cagrilar.slice(3)).toEqual(["/lexis-api/dosya/501", "/lexis-api/emsal-puanla"]);
    [yol, init] = apiMock.fetch.mock.calls[4] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toMatchObject({ case_id: 501, sha256: "a" });
  });

  it("muallak önerisi seçilen sınıflarla servisten gelir; Geçmiş, Kart bağı ve Şirketler örnek veride kalır", async () => {
    servisKur();
    const istek = { case_id: 501, sirket: "QUICK" as const, kusur_tespiti: "KOMPLIKASYON" as const, risk_duzeyi: "RISKLI" as const, teminat: "ICINDE" as const };
    expect(await lexisApi.muallakOner(istek)).toMatchObject({ manevi: 40000, dayanak: "EMSAL" });
    const [yol, init] = apiMock.fetch.mock.calls[0] as [string, RequestInit];
    expect(yol).toBe("/lexis-api/muallak-oner");
    expect(JSON.parse(init.body as string)).toEqual(istek);

    apiMock.fetch.mockClear();
    expect((await lexisApi.profiller()).length).toBeGreaterThan(0);
    expect((await lexisApi.gecmis()).length).toBeGreaterThan(0);
    expect((await lexisApi.kartBaglari()).length).toBeGreaterThan(0);
    expect(apiMock.fetch).not.toHaveBeenCalled();
  });
});
