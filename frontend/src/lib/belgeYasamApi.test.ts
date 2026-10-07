// @vitest-environment jsdom
// belgeYasamApi (G285, plan §6.3): beş uç yolu + gövdesi birebir, hata gövdesi `{detail: {mesaj, error_kod}}` →
// `BelgeYasamApiError` (4xx sunucu metni, 5xx sabit metin, düz `detail` 409 kilit metni), ad ön-izlemesi sunucunun
// `docx_adi` + `sanitize_filename_text` kuralıyla, varsayılan ad, `ms-word:` bağlantısı ve 1,5 sn yedek zamanlayıcısı.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import {
  BelgeYasamApiError,
  WORD_ACILMA_BEKLEMESI_MS,
  docxAdiOnizleme,
  kesinlestir,
  surumKaydet,
  surumler,
  tarayici,
  varsayilanBelgeAdi,
  wordAcBaglantisi,
  wordProtokoluylaAc,
  yeniBelge,
  yeniSurumTaslagi,
} from "./belgeYasamApi";

const yanit = (status: number, govde: unknown) =>
  ({ ok: status >= 200 && status < 300, status, json: async () => govde }) as unknown as Response;

const sonCagri = () => {
  const [yol, secenek] = fetchMock.mock.calls.at(-1)! as [string, RequestInit];
  return { yol, method: secenek?.method ?? "GET", govde: secenek?.body ? JSON.parse(String(secenek.body)) : undefined };
};

beforeEach(() => fetchMock.mockReset());

describe("uçlar (§6.3 birebir)", () => {
  it("yeni: yol + gövde (sablon bos varsayılan) + yanıt", async () => {
    fetchMock.mockResolvedValue(yanit(200, { document_id: 91, word_url: "https://sp/a.docx", word_ac: "ms-word:ofe|u|https://sp/a.docx" }));
    const y = await yeniBelge(7, { belge_turu_kodu: "DILEKCE_______", ad: "Cevap", case_party_id: 11 });
    expect(sonCagri()).toEqual({
      yol: "/api/cases/7/belgeler/yeni",
      method: "POST",
      govde: { sablon: "bos", belge_turu_kodu: "DILEKCE_______", ad: "Cevap", case_party_id: 11 },
    });
    expect(y).toEqual({ document_id: 91, word_url: "https://sp/a.docx", word_ac: "ms-word:ofe|u|https://sp/a.docx" });
  });

  it("surum: not kırpılır, boş not gövdeye girmez; degisti:false korunur", async () => {
    fetchMock.mockResolvedValue(yanit(200, { surum_no: 2, sha256: "ab", degisti: false }));
    expect(await surumKaydet(5, "  düzeltme  ")).toEqual({ surum_no: 2, sha256: "ab", degisti: false });
    expect(sonCagri()).toEqual({ yol: "/api/documents/5/surum", method: "POST", govde: { not: "düzeltme" } });
    await surumKaydet(5, "   ");
    expect(sonCagri().govde).toEqual({});
  });

  it("surumler: GET liste; dizi değilse boş", async () => {
    const satir = { surum_no: 1, sha256: "a", not: null, olusturan_email: "a@x", olusturulma: "2026-10-08T09:00:00Z", kesin: false };
    fetchMock.mockResolvedValue(yanit(200, [satir]));
    expect(await surumler(5)).toEqual([satir]);
    expect(sonCagri()).toMatchObject({ yol: "/api/documents/5/surumler", method: "GET" });
    fetchMock.mockResolvedValue(yanit(200, { x: 1 }));
    expect(await surumler(5)).toEqual([]);
  });

  it("kesinlestir + yeni-surum-taslagi: istek_kimligi gövdede, reused", async () => {
    fetchMock.mockResolvedValue(yanit(200, { document_id: 5, reused: true }));
    expect(await kesinlestir(5, "u-1")).toEqual({ document_id: 5, reused: true });
    expect(sonCagri()).toEqual({ yol: "/api/documents/5/kesinlestir", method: "POST", govde: { istek_kimligi: "u-1" } });
    fetchMock.mockResolvedValue(yanit(200, { document_id: 9, reused: false, word_url: "https://sp/a-v2.docx", word_ac: "ms-word:x" }));
    expect(await yeniSurumTaslagi(5, "u-2")).toEqual({ document_id: 9, reused: false, word_url: "https://sp/a-v2.docx", word_ac: "ms-word:x" });
    expect(sonCagri()).toEqual({ yol: "/api/documents/5/yeni-surum-taslagi", method: "POST", govde: { istek_kimligi: "u-2" } });
  });
});

describe("hata gövdesi", () => {
  it("4xx sunucu metni + error_kod; 5xx sabit metin; düz detail (kilit 409)", async () => {
    fetchMock.mockResolvedValue(yanit(409, { detail: { mesaj: "Belge zaten kesinleşmiş.", error_kod: "zaten_kesin" } }));
    const e1 = await kesinlestir(5, "u").catch((e) => e);
    expect(e1).toBeInstanceOf(BelgeYasamApiError);
    expect([e1.status, e1.errorKod, e1.message]).toEqual([409, "zaten_kesin", "Belge zaten kesinleşmiş."]);

    fetchMock.mockResolvedValue(yanit(503, { detail: { mesaj: "teknik ayrıntı", error_kod: "sistem_mesgul" } }));
    const e2 = await kesinlestir(5, "u").catch((e) => e);
    expect([e2.status, e2.errorKod]).toEqual([503, "sistem_mesgul"]);
    expect(e2.message).toContain("meşgul");
    expect(e2.message).not.toContain("teknik");

    fetchMock.mockResolvedValue(yanit(409, { detail: "Bu kayıt şu an toplu bir veri işleminde kullanılıyor." }));
    const e3 = await yeniBelge(7, { belge_turu_kodu: "X", ad: "a" }).catch((e) => e);
    expect([e3.status, e3.errorKod, e3.message]).toEqual([409, "", "Bu kayıt şu an toplu bir veri işleminde kullanılıyor."]);
  });
});

describe("ad ön-izlemesi (sunucu docx_adi ile aynı kural)", () => {
  it.each([
    ["Cevap Dilekçesi 08.10.2026", "Cevap Dilekçesi 08.10.2026.docx"],
    ["cevap.docx", "cevap.docx"],
    ["eski.doc", "eski.docx"],
    ["a/b\\c:d*e?.docx", "c_d_e_.docx"],
    ["Bilirkişi  raporu (itiraz)", "Bilirkişi  raporu (itiraz).docx"],
    ["çok...nokta", "çok.nokta.docx"],
    ["", null],
    ["   ", null],
    [".docx", null],
    ["___", null],
  ])("%j → %j", (girdi, beklenen) => {
    expect(docxAdiOnizleme(girdi)).toBe(beklenen);
  });

  it("varsayılan ad: tür etiketi + gg.aa.yyyy", () => {
    expect(varsayilanBelgeAdi("Cevap Dilekçesi", new Date(2026, 9, 8))).toBe("Cevap Dilekçesi 08.10.2026");
  });
});

describe("Word açma (ms-word + yedek)", () => {
  afterEach(() => vi.useRealTimers());

  it("bağlantı biçimi", () => {
    expect(wordAcBaglantisi("https://sp/a.docx")).toBe("ms-word:ofe|u|https://sp/a.docx");
  });

  it("1,5 sn'de odak kaybolmazsa yedek; kaybolursa yedek yok; temizleyici zamanlayıcıyı durdurur", () => {
    vi.useFakeTimers();
    const git = vi.spyOn(tarayici, "git").mockImplementation(() => undefined);
    const yedek = vi.fn();
    wordProtokoluylaAc("ms-word:ofe|u|https://sp/a.docx", yedek);
    expect(git).toHaveBeenCalledWith("ms-word:ofe|u|https://sp/a.docx");
    vi.advanceTimersByTime(WORD_ACILMA_BEKLEMESI_MS - 1);
    expect(yedek).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(yedek).toHaveBeenCalledTimes(1);

    const yedek2 = vi.fn();
    wordProtokoluylaAc("ms-word:x", yedek2);
    window.dispatchEvent(new Event("blur"));
    vi.advanceTimersByTime(WORD_ACILMA_BEKLEMESI_MS);
    expect(yedek2).not.toHaveBeenCalled();

    const yedek3 = vi.fn();
    const temizle = wordProtokoluylaAc("ms-word:x", yedek3);
    temizle();
    vi.advanceTimersByTime(WORD_ACILMA_BEKLEMESI_MS);
    expect(yedek3).not.toHaveBeenCalled();
    git.mockRestore();
  });
});
