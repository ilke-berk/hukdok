// @vitest-environment jsdom
// pdfAraclariApi (G270) — `apiClient.fetch` sahte: yükleme FormData ile `/api/pdf-araclari/yukle`'ye gider, `islem`
// JSON gövde, hata gövdesi (`detail` düz metin ya da `{mesaj, error_kod}`) → `PdfAraclariApiError` ve durum koduna göre
// kullanıcı mesajı (413/503/504), `indir` blob + `<a download>`, böl/damga aralık ayrıştırıcıları.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import {
  PdfAraclariApiError,
  bolAraliklariniAyristir,
  damgaSayfalariniAyristir,
  hataMesaji,
  indir,
  islem,
  istekKimligiUret,
  kartaBagla,
  karttanAl,
  onizlemeUrl,
  yukle,
} from "./pdfAraclariApi";
import type { Dosya } from "@/types/pdfAraclari";

const DOSYA: Dosya = { id: "u1", ad: "dilekce.pdf", sayfa: 3, boyut: 1234, sayfalar: [{ no: 1, genislik: 595, yukseklik: 842 }] };

function yanit(status: number, govde: unknown): Response {
  return new Response(JSON.stringify(govde), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => fetchMock.mockReset());
afterEach(() => vi.restoreAllMocks());

describe("yukle", () => {
  it("FormData ile /api/pdf-araclari/yukle'ye POST eder ve Dosya döner", async () => {
    fetchMock.mockResolvedValueOnce(yanit(200, DOSYA));
    const dosya = new File([new Uint8Array([1, 2, 3])], "dilekce.pdf", { type: "application/pdf" });
    const sonuc = await yukle(dosya);
    expect(sonuc).toEqual(DOSYA);
    const [yol, secenekler] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(yol).toBe("/api/pdf-araclari/yukle");
    expect(secenekler.method).toBe("POST");
    expect(secenekler.body).toBeInstanceOf(FormData);
    expect((secenekler.body as FormData).get("file")).toBe(dosya);
  });

  it.each([
    [413, { detail: { mesaj: "Dosya çok büyük. Maksimum 50MB.", error_kod: "boyut" } }, "Dosya çok büyük. Maksimum 50MB.", "boyut"],
    [415, { detail: { mesaj: "İzin verilmeyen dosya uzantısı: .exe", error_kod: "uzanti" } }, "İzin verilmeyen dosya uzantısı: .exe", "uzanti"],
    [503, { detail: { mesaj: "teknik metin", error_kod: "sistem_mesgul" } }, "Sistem şu anda meşgul; birkaç dakika sonra tekrar deneyin.", "sistem_mesgul"],
    [504, { detail: { mesaj: "teknik", error_kod: "zaman_asimi" } }, "İşlem zaman bütçesinde bitmedi; daha küçük parçalarla deneyin.", "zaman_asimi"],
    [422, { detail: "Dosya boş." }, "Dosya boş.", ""],
    [500, "gövde json değil", "PDF işlemi tamamlanamadı. (HTTP 500)", ""],
  ])("%s → PdfAraclariApiError (mesaj + error_kod)", async (status, govde, mesaj, kod) => {
    fetchMock.mockResolvedValueOnce(
      typeof govde === "string" ? new Response(govde, { status }) : yanit(status, govde),
    );
    const dosya = new File([new Uint8Array([1])], "x.pdf", { type: "application/pdf" });
    const hata = await yukle(dosya).catch((e: unknown) => e);
    expect(hata).toBeInstanceOf(PdfAraclariApiError);
    const h = hata as PdfAraclariApiError;
    expect(h.status).toBe(status);
    expect(h.message).toBe(mesaj);
    expect(h.errorKod).toBe(kod);
    expect(hataMesaji(h)).toBe(mesaj);
  });
});

describe("islem", () => {
  it("JSON gövdeyle /islem'e POST eder, ciktilar döner", async () => {
    fetchMock.mockResolvedValueOnce(yanit(200, { ciktilar: [DOSYA] }));
    const sonuc = await islem({ islem: "bol", girdiler: ["u1"], parametreler: { araliklar: [[1, 2]] }, cikti_adi: "p.pdf" });
    expect(sonuc).toEqual([DOSYA]);
    const [yol, secenekler] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(yol).toBe("/api/pdf-araclari/islem");
    expect(JSON.parse(secenekler.body as string)).toEqual({
      islem: "bol",
      girdiler: ["u1"],
      parametreler: { araliklar: [[1, 2]] },
      cikti_adi: "p.pdf",
    });
    expect((secenekler.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("ciktilar yoksa boş dizi", async () => {
    fetchMock.mockResolvedValueOnce(yanit(200, {}));
    expect(await islem({ islem: "birlestir", girdiler: ["a", "b"], parametreler: {} })).toEqual([]);
  });

  it("404 (başkasının id'si) PdfAraclariApiError", async () => {
    fetchMock.mockResolvedValueOnce(yanit(404, { detail: "Dosya bulunamadı veya süresi doldu." }));
    await expect(islem({ islem: "birlestir", girdiler: ["a", "b"], parametreler: {} })).rejects.toMatchObject({
      status: 404,
      message: "Dosya bulunamadı veya süresi doldu.",
    });
  });
});

describe("onizlemeUrl / indir", () => {
  it("önizleme yolu", () => {
    expect(onizlemeUrl("abc", 2)).toBe("/api/pdf-araclari/onizleme/abc/2?genislik=240");
    expect(onizlemeUrl("a/b", 1, 600)).toBe("/api/pdf-araclari/onizleme/a%2Fb/1?genislik=600");
  });

  it("indir: /api/download/{id} blob'unu <a download> ile kaydettirir", async () => {
    // jsdom Blob'u `Response` gövdesi olamaz (stream yok) → `blob()` doğrudan sahte
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, blob: async () => new Blob([new Uint8Array([37, 80, 68, 70])]) });
    const createObjectURL = vi.fn(() => "blob:x");
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const tik = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    await indir("u1", "dilekce.pdf");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/download/u1");
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(tik).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:x");
    expect(document.querySelector("a[download]")).toBeNull(); // eklenen <a> kaldırıldı
  });

  it("indir 404 → PdfAraclariApiError", async () => {
    fetchMock.mockResolvedValueOnce(yanit(404, { detail: "Dosya bulunamadı" }));
    await expect(indir("yok", "x.pdf")).rejects.toBeInstanceOf(PdfAraclariApiError);
  });
});

describe("kartaBagla / karttanAl (G273)", () => {
  it("kartaBagla JSON gövdeyle /karta-bagla'ya POST eder; yanıt {document_id, reused}", async () => {
    fetchMock.mockResolvedValueOnce(yanit(200, { document_id: 321, reused: false }));
    const istek = {
      id: "u1",
      case_id: 7,
      belge_turu_kodu: "TEBLIGAT______",
      dosya_adi: "tebligat.pdf",
      case_party_id: 11,
      istek_kimligi: "11111111-2222-4333-8444-555555555555",
      yon: "GELEN" as const,
      durum: "TASLAK" as const,
    };
    expect(await kartaBagla(istek)).toEqual({ document_id: 321, reused: false });
    const [yol, secenekler] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(yol).toBe("/api/pdf-araclari/karta-bagla");
    expect(secenekler.method).toBe("POST");
    expect(JSON.parse(secenekler.body as string)).toEqual(istek);
  });

  it("reused true → bayrak; 409 kilitli kart sunucu metniyle; 503 meşgul sabit metin", async () => {
    fetchMock.mockResolvedValueOnce(yanit(200, { document_id: 5, reused: true }));
    const r = await kartaBagla({ id: "u", case_id: 1, belge_turu_kodu: "X", dosya_adi: "a.pdf", istek_kimligi: "k" });
    expect(r).toEqual({ document_id: 5, reused: true });
    fetchMock.mockResolvedValueOnce(yanit(409, { detail: "Kayıt şu anda başka bir işlem tarafından kilitli; birkaç dakika sonra tekrar deneyin." }));
    const h409 = (await kartaBagla({ id: "u", case_id: 1, belge_turu_kodu: "X", dosya_adi: "a.pdf", istek_kimligi: "k" }).catch((e: unknown) => e)) as PdfAraclariApiError;
    expect(h409.status).toBe(409);
    expect(h409.message).toContain("kilitli");
    fetchMock.mockResolvedValueOnce(yanit(503, { detail: { mesaj: "teknik", error_kod: "sistem_mesgul" } }));
    const h503 = (await kartaBagla({ id: "u", case_id: 1, belge_turu_kodu: "X", dosya_adi: "a.pdf", istek_kimligi: "k" }).catch((e: unknown) => e)) as PdfAraclariApiError;
    expect(h503.message).toBe("Sistem şu anda meşgul; birkaç dakika sonra tekrar deneyin.");
    expect(h503.errorKod).toBe("sistem_mesgul");
  });

  it("karttanAl {document_id} gövdesiyle /karttan-al'a POST eder, Dosya döner; 404 ve 502 mesajları", async () => {
    fetchMock.mockResolvedValueOnce(yanit(200, DOSYA));
    expect(await karttanAl(42)).toEqual(DOSYA);
    const [yol, secenekler] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(yol).toBe("/api/pdf-araclari/karttan-al");
    expect(JSON.parse(secenekler.body as string)).toEqual({ document_id: 42 });
    fetchMock.mockResolvedValueOnce(yanit(404, { detail: "Belge bulunamadı." }));
    const h404 = (await karttanAl(1).catch((e: unknown) => e)) as PdfAraclariApiError;
    expect(h404.status).toBe(404);
    expect(h404.message).toBe("Belge bulunamadı.");
    fetchMock.mockResolvedValueOnce(yanit(502, { detail: { mesaj: "Graph 500 ...", error_kod: "sharepoint" } }));
    const h502 = (await karttanAl(1).catch((e: unknown) => e)) as PdfAraclariApiError;
    expect(h502.message).toBe("Belge arşivden (SharePoint) alınamadı; daha sonra tekrar deneyin.");
    expect(h502.errorKod).toBe("sharepoint");
  });

  it("istekKimligiUret UUID v4 biçiminde ve her çağrıda farklı", () => {
    const a = istekKimligiUret();
    const b = istekKimligiUret();
    expect(a).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(a).not.toBe(b);
  });
});

describe("bolAraliklariniAyristir", () => {
  it.each([
    ["1-3,4-7", 7, [[1, 3], [4, 7]]],
    ["1-3; 5", 7, [[1, 3], [5, 5]]],
    ["2", 3, [[2, 2]]],
    ["4-7, 1-3", 7, [[4, 7], [1, 3]]], // sıra serbest
    [" 1 - 2 ", 2, [[1, 2]]],
  ])("%s / %s sayfa → %j", (metin, toplam, beklenen) => {
    expect(bolAraliklariniAyristir(metin, toplam)).toEqual(beklenen);
  });

  it.each([
    ["", 5],
    ["abc", 5],
    ["0-2", 5],
    ["3-2", 5],
    ["1-6", 5],
    ["1-3,3-4", 5], // çakışma
    ["1-3,2", 5],
    ["1,,2", 0],
    ["1.5", 5],
    ["1-3 4-7", 7], // ayraç boşluk DEĞİL
  ])("geçersiz %s → null", (metin, toplam) => {
    expect(bolAraliklariniAyristir(metin, toplam)).toBeNull();
  });
});

describe("damgaSayfalariniAyristir", () => {
  it("boş ya da 'hepsi' → hepsi; liste → sayfa numaraları", () => {
    expect(damgaSayfalariniAyristir("", 3)).toBe("hepsi");
    expect(damgaSayfalariniAyristir(" Hepsi ", 3)).toBe("hepsi");
    expect(damgaSayfalariniAyristir("1,3-4", 5)).toEqual([1, 3, 4]);
    expect(damgaSayfalariniAyristir("9", 5)).toBeNull();
  });
});
