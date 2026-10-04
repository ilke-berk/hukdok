// Gerçek dava kipi — `lexisApi`'nin bütün yöntemleri Lexis servisine gider (`lexisServis.ts`): dosya bölgesi,
// taslak iskeleti, kütüphane ve kalıcılık (taslak, geçmiş, kart seçimi, şirket profili). `apiClient` sahtedir
// (ağ ve MSAL yok).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiClient: apiMock }));

import { lexisApi, ornekDurumuSifirla, ornekGecikmeAyarla, veriKipi, veriKipiAyarla } from "./lexisApi";
import { LEXIS_DAVA_SERVISI_YOK } from "./lexisServis";
import { LEXIS_YETKI_MESAJI } from "./lexisWord";
import type { LexisAkisOlayi, LexisTaslak } from "@/types/lexis";

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
    // Belge ve emsal metni GİTMEZ; emsallerin yalnız sayısı gider (koşu logu).
    expect(JSON.parse(init.body as string)).toEqual({ case_id: 501, sirket: "QUICK", rapor_turu: "ANA", iskelet: "KISA", emsal_sayisi: 0 });
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

  it("muallak önerisi seçilen sınıflarla servisten gelir", async () => {
    servisKur();
    const istek = { case_id: 501, sirket: "QUICK" as const, kusur_tespiti: "KOMPLIKASYON" as const, risk_duzeyi: "RISKLI" as const, teminat: "ICINDE" as const };
    expect(await lexisApi.muallakOner(istek)).toMatchObject({ manevi: 40000, dayanak: "EMSAL" });
    const [yol, init] = apiMock.fetch.mock.calls[0] as [string, RequestInit];
    expect(yol).toBe("/lexis-api/muallak-oner");
    expect(JSON.parse(init.body as string)).toEqual(istek);
  });

  const cagri = (sira: number) => {
    const [yol, init] = apiMock.fetch.mock.calls[sira] as [string, RequestInit];
    return { yol, yontem: init.method, govde: init.body ? JSON.parse(init.body as string) : undefined };
  };

  it("Geçmiş, Kart bağı ve Şirketler servisten gelir; seçim ve profil servise yazılır", async () => {
    const kosu = { id: "7", case_id: 501, ofis_no: DAVA.ofis_no };
    const bag = { rapor: "AK:abc", klasor: "03054", bag: { durum: "COK_ADAY", adaylar: [], birincil: 8102, insan_secimi: true, uyarilar: [] } };
    const profil = { sirket_kodu: "AXA" as const, ad: "AXA SİGORTA A.Ş.", iskelet_ana: "KISA" as const, iskelet_ek: "EK" as const, sabit_metinler: {}, kriter_metni: "", muallak_tablosu: [], guncelleme: null };
    servisKur({ "/gecmis": yanit(200, [kosu]), "/kart-baglari": yanit(200, [bag]), "/kart-sec": yanit(200, bag), "/profiller": yanit(200, [profil]), "/profil/AXA": yanit(200, { ...profil, guncelleme: "2026-10-04T20:00:00+00:00" }) });

    expect(lexisApi.kalici).toBe(true);
    expect(await lexisApi.gecmis()).toEqual([kosu]);
    expect(await lexisApi.kartBaglari()).toEqual([bag]);
    expect(await lexisApi.kartSec("AK:abc", 8102)).toEqual(bag);
    expect(cagri(2)).toEqual({ yol: "/lexis-api/kart-sec", yontem: "POST", govde: { rapor: "AK:abc", kart_id: 8102 } });
    await lexisApi.kartSec("AK:abc", null);
    expect(cagri(3).govde).toEqual({ rapor: "AK:abc", kart_id: null }); // seçimi geri al

    expect(await lexisApi.profiller()).toEqual([profil]);
    expect((await lexisApi.profilKaydet({ ...profil, kriter_metni: "yazılı kural" })).guncelleme).toBe("2026-10-04T20:00:00+00:00");
    // Şirket kodu yolda gider; ad ve güncelleme damgası sunucunundur, gövdeye girmez.
    expect(cagri(5)).toEqual({ yol: "/lexis-api/profil/AXA", yontem: "PUT", govde: { iskelet_ana: "KISA", iskelet_ek: "EK", sabit_metinler: {}, kriter_metni: "yazılı kural", muallak_tablosu: [] } });
  });

  it("taslak sürümle kaydedilir, okunur, silinir; koşu kimliği iskeletten öğrenilip kayda eklenir", async () => {
    const taslak: LexisTaslak = { case_id: 501, sirket: "QUICK", rapor_turu: "ANA", iskelet: "KISA", etiketli: {}, ozet: {}, degerlendirme: null, muallak: null, muallak_maddi: null, muallak_manevi: null, emsaller: [] };
    const kayitli = { taslak, ekran: {}, surum: 3, kosu_id: 41, guncelleyen: "yonetici@ornek.test", guncelleme: "2026-10-04T20:00:00+00:00" };
    const sonuc = { surum: 4, guncelleme: "2026-10-04T20:05:00+00:00", guncelleyen: "yonetici@ornek.test" };
    servisKur({ "/taslak/501": yanit(200, kayitli), "/taslak/502": yanit(200, null), "/iskelet": yanit(200, { ...ISKELET, kosu_id: 77 }) });

    expect(await lexisApi.taslakGetir(502)).toBeNull(); // kayıt yok: hata değil
    expect(await lexisApi.taslakGetir(501)).toEqual(kayitli);
    apiMock.fetch.mockClear();

    // Kayıtlı taslağın koşusu (41) kayda eklenir; yeni yazımdan sonra iskeletin açtığı koşu (77) geçer.
    servisKur({ "/taslak/501": yanit(200, sonuc), "/iskelet": yanit(200, { ...ISKELET, kosu_id: 77 }) });
    const govde = { taslak: { ...taslak }, ekran: { secili_belgeler: [1] }, surum: 3, uyari_sayisi: 2 };
    expect(await lexisApi.taslakKaydet(501, govde)).toEqual(sonuc);
    expect(cagri(0)).toEqual({ yol: "/lexis-api/taslak/501", yontem: "PUT", govde: { ...govde, kosu_id: 41 } });

    const olaylar: LexisAkisOlayi[] = [];
    for await (const olay of lexisApi.taslakYaz(ISTEK)) olaylar.push(olay);
    expect(olaylar[olaylar.length - 1]).toMatchObject({ status: "complete", kosu_id: "77" });
    apiMock.fetch.mockClear();
    await lexisApi.taslakKaydet(501, govde);
    expect(cagri(0).govde.kosu_id).toBe(77);

    servisKur({ "/taslak/501": yanit(200, { silindi: true }) });
    apiMock.fetch.mockClear();
    await lexisApi.taslakSil(501);
    expect(cagri(0)).toMatchObject({ yol: "/lexis-api/taslak/501", yontem: "DELETE" });
  });

  it("başka oturumun yazdığı taslak ezilmez: 409 servisin metniyle gelir; veritabanı yoksa 503", async () => {
    const taslak = { case_id: 501 } as never;
    apiMock.fetch.mockResolvedValueOnce(yanit(409, { detail: "Bu davanın taslağı başka bir oturumda değişmiş." }));
    await expect(lexisApi.taslakKaydet(501, { taslak, ekran: {}, surum: 1, uyari_sayisi: 0 })).rejects.toMatchObject({ status: 409, message: "Bu davanın taslağı başka bir oturumda değişmiş." });
    apiMock.fetch.mockResolvedValueOnce(yanit(503, { detail: "Lexis veritabanına ulaşılamadı; biraz sonra tekrar deneyin." }));
    await expect(lexisApi.gecmis()).rejects.toMatchObject({ status: 503, message: "Lexis veritabanına ulaşılamadı; biraz sonra tekrar deneyin." });
  });

  it("örnek kipte hiçbir şey kaydedilmez", async () => {
    veriKipiAyarla("ornek");
    expect(lexisApi.kalici).toBe(false);
    expect(await lexisApi.taslakGetir(9001)).toBeNull();
    expect(await lexisApi.taslakKaydet(9001, { taslak: { case_id: 9001 } as never, ekran: {}, surum: null, uyari_sayisi: 0 })).toBeNull();
    await lexisApi.taslakSil(9001);
    expect((await lexisApi.profiller()).length).toBeGreaterThan(0); // örnek profiller bellekten
    expect(apiMock.fetch).not.toHaveBeenCalled();
  });
});
