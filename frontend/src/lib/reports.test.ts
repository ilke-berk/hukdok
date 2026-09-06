// lib/reports — plan §2.1/§2.2 sözleşmesinin istemci tarafı (G133): tip↔op tablosu,
// `between`/`in` değer biçimi, tanım ön-doğrulaması, hücre biçimlendirme, 422 çevirisi
// ve önizleme gövdesi. Sözleşme: docs/plan/raporlama-plani-2026-09-06.md §2.
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import {
    OP_BY_TIP, RaporApiError, degerSekleUyarla, filtreTamamMi, hucreBicimle, opDegerSekli, opsForTip,
    previewReport, getCatalog, raporHatasiCevir, tanimGecerliMi, tarihBicimle,
    type KatalogVeriKaynagi, type KolonTipi, type RaporTanimi,
} from "./reports";

const okJson = (payload: unknown, status = 200) =>
    ({ ok: true, status, json: async () => payload }) as unknown as Response;
const failJson = (status: number, payload: unknown) =>
    ({ ok: false, status, json: async () => payload }) as unknown as Response;
const failText = (status: number) =>
    ({ ok: false, status, json: async () => { throw new Error("json değil"); } }) as unknown as Response;

const KAYNAK: KatalogVeriKaynagi = {
    anahtar: "davalar",
    etiket: "Davalar",
    aciklama: "",
    varsayilan_kolonlar: ["tracking_no", "subject"],
    kolonlar: [
        { anahtar: "tracking_no", etiket: "Ofis No", tip: "metin", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null },
        { anahtar: "subject", etiket: "Konu", tip: "metin", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null },
        { anahtar: "status", etiket: "Durum", tip: "liste", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: ["Derdest", "Karar"] },
        { anahtar: "opening_date", etiket: "Açılış", tip: "tarih", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null },
        { anahtar: "maddi_tazminat", etiket: "Maddi", tip: "para", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null },
        { anahtar: "active", etiket: "Aktif", tip: "mantik", filtrelenebilir: true, siralanabilir: false, turetilmis: false, secenekler: null },
        { anahtar: "muvekkil_adlari", etiket: "Müvekkiller", tip: "metin", filtrelenebilir: false, siralanabilir: false, turetilmis: true, secenekler: null },
    ],
};

describe("§2.2 tip ↔ op tablosu", () => {
    it("her tipin op listesi plandaki tabloyla birebir aynıdır (aşılmaz)", () => {
        expect(OP_BY_TIP.metin).toEqual(["eq", "ne", "contains", "in", "is_null", "not_null"]);
        expect(OP_BY_TIP.liste).toEqual(["eq", "ne", "in", "is_null", "not_null"]);
        expect(OP_BY_TIP.tarih).toEqual(["eq", "gte", "lte", "between", "is_null", "not_null"]);
        expect(OP_BY_TIP.sayi).toEqual(["eq", "gte", "lte", "between", "is_null", "not_null"]);
        expect(OP_BY_TIP.para).toEqual(["eq", "gte", "lte", "between", "is_null", "not_null"]);
        expect(OP_BY_TIP.mantik).toEqual(["eq", "is_null"]);
    });

    it("liste tipinde `contains` YOK, mantık tipinde `ne`/`not_null` YOK", () => {
        expect(opsForTip("liste")).not.toContain("contains");
        expect(opsForTip("mantik")).not.toContain("ne");
        expect(opsForTip("mantik")).not.toContain("not_null");
    });

    it("op değer şekli: is_null/not_null değersiz, in liste, between ikili, kalanı tekil", () => {
        expect(opDegerSekli("is_null")).toBe("yok");
        expect(opDegerSekli("not_null")).toBe("yok");
        expect(opDegerSekli("in")).toBe("liste");
        expect(opDegerSekli("between")).toBe("ikili");
        expect(opDegerSekli("contains")).toBe("tekil");
        expect(opDegerSekli("gte")).toBe("tekil");
    });
});

describe("değer biçimi — between dizi, in liste (§2.1 JSON)", () => {
    it("eq → between: mevcut değer ilk uç olur, ikinci boş", () => {
        expect(degerSekleUyarla("between", "2025-01-01")).toEqual(["2025-01-01", ""]);
    });

    it("between → eq: ilk uç korunur", () => {
        expect(degerSekleUyarla("eq", ["2025-01-01", "2025-12-31"])).toBe("2025-01-01");
    });

    it("eq → in: tekil değer tek elemanlı listeye sarılır; in → is_null: değer düşer", () => {
        expect(degerSekleUyarla("in", "Derdest")).toEqual(["Derdest"]);
        expect(degerSekleUyarla("is_null", ["Derdest"])).toBeUndefined();
    });

    it("between yalnız iki DOLU uçla tamamdır", () => {
        expect(filtreTamamMi({ alan: "opening_date", op: "between", deger: ["2025-01-01", "2025-12-31"] }, "tarih")).toBe(true);
        expect(filtreTamamMi({ alan: "opening_date", op: "between", deger: ["2025-01-01", ""] }, "tarih")).toBe(false);
        expect(filtreTamamMi({ alan: "opening_date", op: "between", deger: "2025-01-01" }, "tarih")).toBe(false);
        expect(filtreTamamMi({ alan: "maddi_tazminat", op: "between", deger: [0, 1000] }, "para")).toBe(true);
    });

    it("in en az bir değer ister; is_null değersiz tamamdır; tip dışı op tamam değildir", () => {
        expect(filtreTamamMi({ alan: "status", op: "in", deger: [] }, "liste")).toBe(false);
        expect(filtreTamamMi({ alan: "status", op: "in", deger: ["Derdest"] }, "liste")).toBe(true);
        expect(filtreTamamMi({ alan: "status", op: "is_null" }, "liste")).toBe(true);
        expect(filtreTamamMi({ alan: "status", op: "contains", deger: "x" }, "liste")).toBe(false);
        expect(filtreTamamMi({ alan: "active", op: "eq", deger: true }, "mantik")).toBe(true);
        expect(filtreTamamMi({ alan: "active", op: "eq", deger: "true" }, "mantik")).toBe(false);
        expect(filtreTamamMi({ alan: "x", op: "eq", deger: "a" }, undefined)).toBe(false);
    });
});

describe("tanimGecerliMi — Önizle kapısı", () => {
    const temel: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["tracking_no"], filtreler: [], siralama: [] };

    it("kolon yoksa geçersiz, tek kolonla geçerli", () => {
        expect(tanimGecerliMi({ ...temel, kolonlar: [] }, KAYNAK)).toBe(false);
        expect(tanimGecerliMi(temel, KAYNAK)).toBe(true);
    });

    it("türetilmiş kolon filtre/sıralama alanı olamaz ama kolon olarak seçilebilir", () => {
        expect(tanimGecerliMi({ ...temel, kolonlar: ["muvekkil_adlari"] }, KAYNAK)).toBe(true);
        expect(tanimGecerliMi({ ...temel, filtreler: [{ alan: "muvekkil_adlari", op: "eq", deger: "x" }] }, KAYNAK)).toBe(false);
    });

    it("eksik filtre satırı, alan seçilmemiş sıralama ve 4. sıralama geçersizdir", () => {
        expect(tanimGecerliMi({ ...temel, filtreler: [{ alan: "", op: "eq" }] }, KAYNAK)).toBe(false);
        expect(tanimGecerliMi({ ...temel, siralama: [{ alan: "", yon: "asc" }] }, KAYNAK)).toBe(false);
        const dort = Array.from({ length: 4 }, () => ({ alan: "subject", yon: "asc" as const }));
        expect(tanimGecerliMi({ ...temel, siralama: dort }, KAYNAK)).toBe(false);
        expect(tanimGecerliMi({ ...temel, siralama: dort.slice(0, 3) }, KAYNAK)).toBe(true);
    });

    it("kaynak eşleşmiyorsa ya da tekrarlı kolon varsa geçersiz", () => {
        expect(tanimGecerliMi({ ...temel, veri_kaynagi: "belgeler" }, KAYNAK)).toBe(false);
        expect(tanimGecerliMi({ ...temel, kolonlar: ["subject", "subject"] }, KAYNAK)).toBe(false);
        expect(tanimGecerliMi(temel, undefined)).toBe(false);
    });
});

describe("hücre biçimlendirme", () => {
    it("tarih ISO → dd.MM.yyyy (datetime'da saat atılır)", () => {
        expect(tarihBicimle("2025-03-07")).toBe("07.03.2025");
        expect(hucreBicimle("2025-03-07T10:20:00+03:00", "tarih")).toBe("07.03.2025");
        expect(hucreBicimle("bozuk", "tarih")).toBe("bozuk");
    });

    it("para tr-TR iki ondalık, sayı binlik ayraçlı", () => {
        expect(hucreBicimle(1234.5, "para")).toBe("1.234,50");
        expect(hucreBicimle(1234, "sayi")).toBe("1.234");
        expect(hucreBicimle(0, "para")).toBe("0,00");
    });

    it("null / boş → —, mantık Evet/Hayır", () => {
        const her: KolonTipi[] = ["metin", "liste", "tarih", "sayi", "para", "mantik"];
        for (const tip of her) {
            expect(hucreBicimle(null, tip)).toBe("—");
            expect(hucreBicimle(undefined, tip)).toBe("—");
        }
        expect(hucreBicimle(true, "mantik")).toBe("Evet");
        expect(hucreBicimle(false, "mantik")).toBe("Hayır");
        expect(hucreBicimle("Derdest", "liste")).toBe("Derdest");
    });
});

describe("raporHatasiCevir — 422 alan/sebep okunur mesaj", () => {
    it("detail.{alan,sebep} → 'Geçersiz rapor tanımı: alan — sebep'", async () => {
        const err = await raporHatasiCevir(failJson(422, { detail: { alan: "filtreler[0].op", sebep: "liste tipinde contains izinli değil" } }), "x");
        expect(err).toBeInstanceOf(RaporApiError);
        expect(err.status).toBe(422);
        expect(err.alan).toBe("filtreler[0].op");
        expect(err.sebep).toBe("liste tipinde contains izinli değil");
        expect(err.message).toBe("Geçersiz rapor tanımı: filtreler[0].op — liste tipinde contains izinli değil");
    });

    it("FastAPI liste biçimli 422 de okunur", async () => {
        const err = await raporHatasiCevir(failJson(422, { detail: [{ loc: ["body", "tanim"], msg: "field required" }] }), "x");
        expect(err.message).toBe("Geçersiz rapor tanımı: field required");
    });

    it("413 satir_limiti toplam/limit ile", async () => {
        const err = await raporHatasiCevir(failJson(413, { detail: { sebep: "satir_limiti", toplam: 60000, limit: 50000 } }), "x");
        expect(err.status).toBe(413);
        expect(err.message).toContain("60.000");
        expect(err.message).toContain("50.000");
    });

    it("düz metin detail aynen; JSON olmayan gövde → varsayılan + HTTP kodu", async () => {
        expect((await raporHatasiCevir(failJson(409, { detail: "rapor_asistani kapalı" }), "x")).message).toBe("rapor_asistani kapalı");
        expect((await raporHatasiCevir(failText(502), "Önizleme alınamadı.")).message).toBe("Önizleme alınamadı. (HTTP 502)");
    });
});

describe("HTTP fonksiyonları", () => {
    beforeEach(() => fetchMock.mockReset());

    it("previewReport gövdesi {tanim, sayfa, sayfa_boyu} ile POST /api/reports/preview", async () => {
        const cevap = { kolonlar: [], satirlar: [], toplam: 0, sayfa: 2, sayfa_boyu: 50 };
        fetchMock.mockResolvedValueOnce(okJson(cevap));
        const tanim: RaporTanimi = {
            veri_kaynagi: "davalar",
            kolonlar: ["tracking_no"],
            filtreler: [{ alan: "opening_date", op: "between", deger: ["2025-01-01", "2025-12-31"] }],
            siralama: [{ alan: "opening_date", yon: "desc" }],
        };
        const sonuc = await previewReport(tanim, 2, 50);
        expect(sonuc).toEqual(cevap);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [url, opts] = fetchMock.mock.calls[0] as [string, RequestInit];
        expect(url).toBe("/api/reports/preview");
        expect(opts.method).toBe("POST");
        expect(JSON.parse(opts.body as string)).toEqual({ tanim, sayfa: 2, sayfa_boyu: 50 });
    });

    it("previewReport 422'yi RaporApiError olarak fırlatır", async () => {
        fetchMock.mockResolvedValueOnce(failJson(422, { detail: { alan: "kolonlar", sebep: "en az 1" } }));
        const tanim: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: [], filtreler: [], siralama: [] };
        await expect(previewReport(tanim, 1, 50)).rejects.toMatchObject({ name: "RaporApiError", alan: "kolonlar", sebep: "en az 1" });
    });

    it("getCatalog GET /api/reports/catalog", async () => {
        const katalog = { veri_kaynaklari: [KAYNAK], limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 } };
        fetchMock.mockResolvedValueOnce(okJson(katalog));
        expect(await getCatalog()).toEqual(katalog);
        expect(fetchMock.mock.calls[0][0]).toBe("/api/reports/catalog");
    });
});
