// Belgelerden rapor yazımı (lexis-rapor Aşama 14) — ekran tarafı: seçili belgeler `/yaz` gövdesine yalnız
// `belgelerden_yaz` iken gider; servisin yazım uyarıları bölümüyle ekrana düşer (zayıf kaynak paragrafın kendi
// işaretinden denetlenir, iki kez yazılmaz); karar-yalnız yazımda servis uyarıları eskisi gibi alınmaz.
// `apiClient` sahtedir (ağ ve MSAL yok). Veriler uydurmadır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiClient: apiMock }));

import { lexisApi, ornekDurumuSifirla, ornekGecikmeAyarla, sunucuUyarilari, veriKipiAyarla } from "./lexisApi";
import { denetle } from "./lexisDenetim";
import { ORNEK_DOSYALAR } from "./lexisOrnekVeri";
import type { LexisAkisOlayi, LexisTaslak, TaslakIstegi } from "@/types/lexis";

function yanit(govde: unknown): Response {
  return { ok: true, status: 200, headers: new Headers({ "Content-Type": "application/json" }), json: async () => govde } as unknown as Response;
}

const DOSYA = { ...ORNEK_DOSYALAR[9001], dava: { ...ORNEK_DOSYALAR[9001].dava, case_id: 501 }, iskelet: "ALTILI" as const };
const ISKELET = {
  etiketli: { hasar: [] },
  ozet: {},
  degerlendirme: { giris: "Tarafımıza iletilen belge ve bilgiler ile yapılan inceleme neticesinde;", maddeler: [{ metin: "[…] muallak", tur: "KALIP", dayanak_bolum: null, dayanak_alinti: null }], sulh_uygunluk: "", muallak_gerekcesi: "" },
  muallak: { maddi: null, manevi: null, dayanak: "YOK", gerekce: "", emsaller: [], teminat: "BELIRSIZ", uyarilar: [] },
  kosu_id: 7,
};
const YAZIM = {
  ozet: { iddia: [{ metin: "Üst yazıda müdahale sonrası zarar oluştuğu iddia edildiği belirtilmiştir.", kaynak_belge_id: 81, kaynak_karar_id: null, dayanak_alinti: "müdahale sonrası zarar oluştuğu iddia edilmektedir", zayif_kaynak: true }] },
  degerlendirme: ISKELET.degerlendirme,
  muallak: ISKELET.muallak,
  kararlar: [],
  belgeler: [81],
  uyarilar: ["iddia paragraf 1: zayıf kaynak (idare üst yazısı; asıl kaynak kartta yok: dava / şikâyet dilekçesi)", "beyan: kartta yok: hekim beyanı / cevap / savunma", "tutarlılık: tarih çelişiyor"],
  model: "sahte",
  maske: { bilinen: 1, kalip: 0, ogrenilen: 0 },
  gonderilen_karakter: 120,
};

function sunucu(yazimGovdeleri: unknown[]) {
  apiMock.fetch.mockImplementation(async (yol: string, init?: RequestInit) => {
    if (yol === "/lexis-api/iskelet") return yanit(ISKELET);
    if (yol === "/lexis-api/yaz") {
      yazimGovdeleri.push(JSON.parse(init!.body as string));
      return yanit(YAZIM);
    }
    if (yol === "/lexis-api/dosya/501") return yanit(DOSYA);
    if (yol === "/lexis-api/karar-bankasi") return yanit([]);
    throw new Error(`beklenmeyen istek ${yol}`);
  });
}

const istek = (ek: Partial<TaslakIstegi>): TaslakIstegi => ({ case_id: 501, sirket: "AK", rapor_turu: "ANA", iskelet: "ALTILI", belge_idleri: [81, 82], emsal_sha: [], karar_idleri: [], ...ek });

async function topla(i: TaslakIstegi): Promise<LexisAkisOlayi[]> {
  const olaylar: LexisAkisOlayi[] = [];
  for await (const o of lexisApi.taslakYaz(i)) olaylar.push(o);
  return olaylar;
}

beforeEach(() => {
  ornekDurumuSifirla();
  ornekGecikmeAyarla(0);
  apiMock.fetch.mockReset();
  veriKipiAyarla("gercek");
});
afterEach(() => veriKipiAyarla("ornek"));

describe("belgelerden yazım — ekran", () => {
  it("belgelerden_yaz iken seçili belgeler /yaz'a gider; servis uyarıları bölümüyle ekrana düşer, zayıf kaynak tek kez", async () => {
    const govdeler: unknown[] = [];
    sunucu(govdeler);
    const olaylar = await topla(istek({ belgelerden_yaz: true }));
    expect(govdeler).toEqual([expect.objectContaining({ case_id: 501, karar_idleri: [], belge_idleri: [81, 82] })]);
    const son = olaylar.at(-1)!;
    expect(son.status).toBe("complete");
    const uyarilar = son.status === "complete" ? son.uyarilar : [];
    expect(uyarilar.filter((u) => u.kod === "ZAYIF_KAYNAK").map((u) => u.bolum)).toEqual(["iddia"]);
    const yazim = uyarilar.filter((u) => u.kod === "YAZIM_UYARISI").map((u) => [u.bolum, u.metin]);
    expect(yazim).toEqual([["beyan", "beyan: kartta yok: hekim beyanı / cevap / savunma"], [null, "tutarlılık: tarih çelişiyor"]]);
    expect(olaylar.some((o) => o.status === "info" && o.mesaj.startsWith("2 belge maskelenip"))).toBe(true);
  });

  it("belgelerden_yaz yoksa (yazım kapalı) belge gönderilmez, iskelet kalır", async () => {
    const govdeler: unknown[] = [];
    sunucu(govdeler);
    const olaylar = await topla(istek({}));
    expect(govdeler).toEqual([]);
    expect(olaylar.at(-1)?.status).toBe("complete");
  });

  it("sunucu yazım uyarıları 'Yeniden denetle'de kaybolmaz; karar paragraflarının uyarısı iki kez yazılmaz", async () => {
    sunucu([]);
    const olaylar = await topla(istek({ belgelerden_yaz: true }));
    const son = olaylar.at(-1)!;
    const taslak = { case_id: 501, sirket: "AK", rapor_turu: "ANA", iskelet: "ALTILI", etiketli: {}, ozet: YAZIM.ozet, degerlendirme: null, muallak: null, muallak_maddi: null, muallak_manevi: null, emsaller: [], kararlar: [] } as LexisTaslak;
    const yeniden = await lexisApi.denetle(taslak);
    const metin = (u: { metin: string }[]) => u.filter((x) => x.metin.startsWith("beyan:")).map((x) => x.metin);
    expect(son.status === "complete" && metin(son.uyarilar)).toEqual(["beyan: kartta yok: hekim beyanı / cevap / savunma"]);
    expect(metin(yeniden)).toEqual(["beyan: kartta yok: hekim beyanı / cevap / savunma"]);
    expect(sunucuUyarilari(["yargi_sureci paragraf 1: kaynak kararda geçmiyor: 2021/5", "tutarlılık: iki karar tarihi çelişiyor"]).map((u) => u.metin)).toEqual(["tutarlılık: iki karar tarihi çelişiyor"]);
  });

  it("sunucuUyarilari: önekten bölüm, zayıf kaynak satırı alınmaz", () => {
    expect(sunucuUyarilari(["iddia paragraf 2: dayanak alıntısı belgede bulunamadı", "iddia paragraf 1: zayıf kaynak (x)", "belge 82 okunamadı: biçim"]).map((u) => [u.kod, u.bolum])).toEqual([
      ["YAZIM_UYARISI", "iddia"],
      ["YAZIM_UYARISI", null],
    ]);
  });

  it("zayıf kaynaklı paragraf denetimde uyarı olur; işaretsiz paragraf olmaz", () => {
    const taslak = (zayif: boolean): LexisTaslak => ({
      case_id: 501, sirket: "AK", rapor_turu: "ANA", iskelet: "ALTILI", etiketli: {},
      ozet: { iddia: [{ metin: "Üst yazıda zarar iddia edildiği belirtilmiştir.", kaynak_belge_id: 81, zayif_kaynak: zayif }] },
      degerlendirme: null, muallak: null, muallak_maddi: null, muallak_manevi: null, emsaller: [], kararlar: [],
    });
    const kod = (zayif: boolean) => denetle({ taslak: taslak(zayif), dosya: DOSYA, emsalMetinleri: [], kararBankasi: [] }).filter((u) => u.kod === "ZAYIF_KAYNAK");
    expect(kod(true).map((u) => [u.bolum, u.seviye])).toEqual([["iddia", "UYARI"]]);
    expect(kod(false)).toEqual([]);
  });
});
