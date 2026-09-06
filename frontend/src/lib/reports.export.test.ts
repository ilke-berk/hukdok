// @vitest-environment jsdom
// lib/reports — şablon / export / koşu fonksiyonları (G134): gövdeler plan §2.4 ile birebir,
// dosya adı sunucunun Content-Disposition'ından (istemci ad uydurmaz), 413 satır limiti ve
// 410 saklama süresi okunur mesaja döner, 403 sahiplik hatası. Sözleşme:
// docs/plan/raporlama-plani-2026-09-06.md §2.4.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import {
    RAPOR_KOSU_SURESI_DOLDU, RAPOR_SABLON_YETKI_HATASI, RaporApiError,
    boyutBicimle, createTemplate, deleteTemplate, dispositionDosyaAdi, dosyayiIndir, downloadRun, exportReport,
    listRuns, listTemplates, sablonSahibiMi, tarihSaatBicimle, updateTemplate,
    type RaporSablonu, type RaporTanimi,
} from "./reports";

const TANIM: RaporTanimi = {
    veri_kaynagi: "davalar",
    kolonlar: ["tracking_no", "subject"],
    filtreler: [{ alan: "status", op: "in", deger: ["Derdest"] }],
    siralama: [{ alan: "opening_date", yon: "desc" }],
};

const SABLON: RaporSablonu = {
    id: 7, ad: "Derdest", aciklama: null, tanim: TANIM, olusturan: "admin@lexis.com.tr",
    paylasimli: false, created_at: "2026-09-06T10:00:00Z", updated_at: "2026-09-06T10:00:00Z",
};

const okJson = (payload: unknown, status = 200) =>
    ({ ok: true, status, json: async () => payload }) as unknown as Response;
const failJson = (status: number, payload: unknown) =>
    ({ ok: false, status, json: async () => payload }) as unknown as Response;
const okBlob = (headers: Record<string, string>, icerik = "dosya") =>
    ({
        ok: true,
        status: 200,
        headers: { get: (k: string) => headers[k] ?? headers[k.toLowerCase()] ?? null },
        blob: async () => new Blob([icerik]),
        json: async () => { throw new Error("blob"); },
    }) as unknown as Response;

const sonCagri = () => {
    const [url, opts] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [string, RequestInit | undefined];
    return { url, opts, govde: opts?.body ? JSON.parse(opts.body as string) : undefined };
};

beforeEach(() => {
    fetchMock.mockReset();
});

describe("şablon uçları (§2.4)", () => {
    it("listTemplates GET /api/reports/templates", async () => {
        fetchMock.mockResolvedValueOnce(okJson([SABLON]));
        expect(await listTemplates()).toEqual([SABLON]);
        expect(sonCagri().url).toBe("/api/reports/templates");
    });

    it("createTemplate gövdesi {ad, aciklama, tanim, paylasimli} — anahtarlar birebir, fazlası yok", async () => {
        fetchMock.mockResolvedValueOnce(okJson(SABLON, 201));
        const govde = { ad: "Derdest", aciklama: null, tanim: TANIM, paylasimli: false };
        expect(await createTemplate(govde)).toEqual(SABLON);
        const c = sonCagri();
        expect(c.url).toBe("/api/reports/templates");
        expect(c.opts?.method).toBe("POST");
        expect(Object.keys(c.govde).sort()).toEqual(["aciklama", "ad", "paylasimli", "tanim"]);
        expect(c.govde).toEqual(govde);
    });

    it("updateTemplate PUT /templates/{id} TAM gövdeyle; 403 sahiplik mesajı", async () => {
        fetchMock.mockResolvedValueOnce(okJson({ ...SABLON, ad: "Yeni ad" }));
        const govde = { ad: "Yeni ad", aciklama: "x", tanim: TANIM, paylasimli: true };
        expect((await updateTemplate(7, govde)).ad).toBe("Yeni ad");
        const c = sonCagri();
        expect(c.url).toBe("/api/reports/templates/7");
        expect(c.opts?.method).toBe("PUT");
        expect(c.govde).toEqual(govde);

        fetchMock.mockResolvedValueOnce(failJson(403, { detail: "yasak" }));
        await expect(updateTemplate(7, govde)).rejects.toMatchObject({ name: "RaporApiError", status: 403, message: RAPOR_SABLON_YETKI_HATASI });
    });

    it("deleteTemplate DELETE /templates/{id} (204); 403 sahiplik mesajı", async () => {
        fetchMock.mockResolvedValueOnce({ ok: true, status: 204 } as unknown as Response);
        await expect(deleteTemplate(7)).resolves.toBeUndefined();
        const c = sonCagri();
        expect(c.url).toBe("/api/reports/templates/7");
        expect(c.opts?.method).toBe("DELETE");

        fetchMock.mockResolvedValueOnce(failJson(403, { detail: "yasak" }));
        await expect(deleteTemplate(7)).rejects.toMatchObject({ status: 403, message: RAPOR_SABLON_YETKI_HATASI });
    });

    it("sablonSahibiMi: e-posta büyük/küçük harf duyarsız; kullanıcı yoksa false", () => {
        expect(sablonSahibiMi(SABLON, "Admin@Lexis.com.tr")).toBe(true);
        expect(sablonSahibiMi(SABLON, "baskasi@lexis.com.tr")).toBe(false);
        expect(sablonSahibiMi(SABLON, undefined)).toBe(false);
        expect(sablonSahibiMi(SABLON, "")).toBe(false);
    });
});

describe("export (§2.4)", () => {
    it("gövde {tanim, format, sablon_id, kaynak} birebir; dosya adı Content-Disposition'dan, koşu id başlıktan", async () => {
        fetchMock.mockResolvedValueOnce(okBlob({
            "Content-Disposition": 'attachment; filename="hukdok-rapor-davalar-20260906-1405.xlsx"',
            "X-Rapor-Kosu-Id": "42",
        }));
        const sonuc = await exportReport(TANIM, "xlsx", 7, "manuel");
        const c = sonCagri();
        expect(c.url).toBe("/api/reports/export");
        expect(c.opts?.method).toBe("POST");
        expect(Object.keys(c.govde).sort()).toEqual(["format", "kaynak", "sablon_id", "tanim"]);
        expect(c.govde).toEqual({ tanim: TANIM, format: "xlsx", sablon_id: 7, kaynak: "manuel" });
        expect(sonuc.dosyaAdi).toBe("hukdok-rapor-davalar-20260906-1405.xlsx");
        expect(sonuc.kosuId).toBe(42);
        expect(sonuc.blob).toBeInstanceOf(Blob);
    });

    it("csv + şablonsuz: sablon_id null gider; koşu başlığı yoksa kosuId null", async () => {
        fetchMock.mockResolvedValueOnce(okBlob({ "Content-Disposition": 'attachment; filename="r.csv"' }));
        const sonuc = await exportReport(TANIM, "csv", null, "asistan");
        expect(sonCagri().govde).toEqual({ tanim: TANIM, format: "csv", sablon_id: null, kaynak: "asistan" });
        expect(sonuc.dosyaAdi).toBe("r.csv");
        expect(sonuc.kosuId).toBeNull();
    });

    it("413 satir_limiti → toplam/limit ile okunur mesaj + filtre daraltma önerisi", async () => {
        fetchMock.mockResolvedValueOnce(failJson(413, { detail: { sebep: "satir_limiti", toplam: 120000, limit: 50000 } }));
        const hata: unknown = await exportReport(TANIM, "xlsx", null, "manuel").catch(e => e);
        expect(hata).toBeInstanceOf(RaporApiError);
        if (!(hata instanceof RaporApiError)) throw new Error("RaporApiError bekleniyordu");
        expect(hata.status).toBe(413);
        expect(hata.sebep).toBe("satir_limiti");
        expect(hata.message).toContain("120.000");
        expect(hata.message).toContain("50.000");
        expect(hata.message).toContain("Filtre daraltın");
    });

    it("dispositionDosyaAdi: tırnaklı/tırnaksız/RFC 5987 (UTF-8) biçimleri; başlık yoksa null", () => {
        expect(dispositionDosyaAdi('attachment; filename="a b.xlsx"')).toBe("a b.xlsx");
        expect(dispositionDosyaAdi("attachment; filename=a.csv")).toBe("a.csv");
        expect(dispositionDosyaAdi("attachment; filename=\"a.csv\"; filename*=UTF-8''rapor%20%C3%A7%C4%B1kt%C4%B1.csv")).toBe("rapor çıktı.csv");
        expect(dispositionDosyaAdi(null)).toBeNull();
        expect(dispositionDosyaAdi("inline")).toBeNull();
    });
});

describe("koşular (§2.4)", () => {
    it("listRuns GET /api/reports/runs?limit=&offset=", async () => {
        const liste = { toplam: 0, kosular: [] };
        fetchMock.mockResolvedValueOnce(okJson(liste));
        expect(await listRuns(50, 100)).toEqual(liste);
        expect(sonCagri().url).toBe("/api/reports/runs?limit=50&offset=100");
    });

    it("downloadRun GET /runs/{id}/download — dosya adı başlıktan; 410 saklama süresi mesajı", async () => {
        fetchMock.mockResolvedValueOnce(okBlob({ "Content-Disposition": 'attachment; filename="eski.xlsx"' }));
        const dosya = await downloadRun(5);
        expect(sonCagri().url).toBe("/api/reports/runs/5/download");
        expect(dosya.dosyaAdi).toBe("eski.xlsx");

        fetchMock.mockResolvedValueOnce(failJson(410, { detail: "gone" }));
        await expect(downloadRun(5)).rejects.toMatchObject({ status: 410, message: RAPOR_KOSU_SURESI_DOLDU });
    });
});

describe("indirme + biçimlendirme", () => {
    const createUrl = vi.fn(() => "blob:sahte");
    const revokeUrl = vi.fn();
    let tiklamalar: string[];

    beforeEach(() => {
        tiklamalar = [];
        (URL as unknown as { createObjectURL: unknown }).createObjectURL = createUrl;
        (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = revokeUrl;
        vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
            tiklamalar.push(this.download);
        });
    });
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("dosyayiIndir <a download> adını sunucudan gelen adla kurar, URL'yi serbest bırakır", () => {
        dosyayiIndir({ blob: new Blob(["x"]), dosyaAdi: "sunucu-adi.xlsx" });
        expect(tiklamalar).toEqual(["sunucu-adi.xlsx"]);
        expect(createUrl).toHaveBeenCalledTimes(1);
        expect(revokeUrl).toHaveBeenCalledWith("blob:sahte");
        expect(document.querySelector("a[download]")).toBeNull();
    });

    it("tarihSaatBicimle yerel dd.MM.yyyy HH:mm; bozuk metin olduğu gibi; boş —", () => {
        const yerel = new Date(2026, 8, 6, 14, 5);
        expect(tarihSaatBicimle(yerel.toISOString())).toBe("06.09.2026 14:05");
        expect(tarihSaatBicimle("saçma")).toBe("saçma");
        expect(tarihSaatBicimle(null)).toBe("—");
    });

    it("boyutBicimle B / KB / MB (tr-TR ondalık); null —", () => {
        expect(boyutBicimle(512)).toBe("512 B");
        expect(boyutBicimle(12_600)).toBe("12,3 KB");
        expect(boyutBicimle(2_400_000)).toBe("2,3 MB");
        expect(boyutBicimle(null)).toBe("—");
    });
});
