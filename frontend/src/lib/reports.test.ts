// lib/reports — plan §2.1/§2.2 sözleşmesinin istemci tarafı (G133): tip↔op tablosu,
// `between`/`in` değer biçimi, tanım ön-doğrulaması, hücre biçimlendirme, 422 çevirisi
// ve önizleme gövdesi. Sözleşme: docs/plan/raporlama-plani-2026-09-06.md §2.
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import {
    KONTROL_DOGAL_OPLARI, OP_BY_TIP, RaporApiError, bosKontrol, degerSekleUyarla, filtreTamamMi, filtredenKontrol,
    gelismisOplar, hucreBicimle, kolonOplari, kolonSecilebilirMi, kontrolDoluMu, kontrolOzeti, kontroldenFiltre,
    opDegerSekli, opsForTip, previewReport, getCatalog, raporHatasiCevir, secenekEtiketi, tanimGecerliMi, tarihBicimle,
    tarihKisayolu,
    type Filtre, type FiltreKontrolu, type FiltreOp, type HizliFiltre, type KatalogKolon, type KatalogVeriKaynagi,
    type KolonTipi, type KontrolDurumu, type KontrolTuru, type RaporTanimi,
} from "./reports";

const okJson = (payload: unknown, status = 200) =>
    ({ ok: true, status, json: async () => payload }) as unknown as Response;
const failJson = (status: number, payload: unknown) =>
    ({ ok: false, status, json: async () => payload }) as unknown as Response;
const failText = (status: number) =>
    ({ ok: false, status, json: async () => { throw new Error("json değil"); } }) as unknown as Response;

// §4.2/§5.2 katalog şekli: tipten türetilen `kontrol`, tip tablosu kadar `oplar` (aksi verilmedikçe),
// seçeneksiz/etiketsiz/seçilebilir kolon (aksi verilmedikçe).
const KONTROL: Record<KolonTipi, FiltreKontrolu> = {
    metin: "metin_icerir", liste: "coklu_secim", tarih: "tarih_araligi", sayi: "sayi_araligi", para: "sayi_araligi", mantik: "mantik",
};
type KolonSahtesi = Pick<KatalogKolon, "anahtar" | "etiket" | "tip"> & Partial<KatalogKolon>;
function kolon(k: KolonSahtesi): KatalogKolon {
    const filtrelenebilir = k.filtrelenebilir ?? true;
    return {
        filtrelenebilir, siralanabilir: true, turetilmis: false, secenekler: null, grup: "Kimlik",
        kontrol: filtrelenebilir ? KONTROL[k.tip] : null,
        oplar: filtrelenebilir ? [...OP_BY_TIP[k.tip]] : [],
        oneriler: null, oneri_kesik: false,
        secenek_kaynagi: k.tip === "liste" ? "sabit" : null, secenek_etiketleri: null, secilebilir: true,
        ...k,
    };
}
const hf = (alan: string, ek: Partial<HizliFiltre> = {}): HizliFiltre =>
    ({ alan, alternatifler: [], sunum: "varsayilan", etiket: null, ...ek });

const KAYNAK: KatalogVeriKaynagi = {
    anahtar: "davalar",
    etiket: "Davalar",
    aciklama: "",
    varsayilan_kolonlar: ["tracking_no", "subject"],
    kolonlar: [
        kolon({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" }),
        kolon({ anahtar: "subject", etiket: "Konu", tip: "metin" }),
        kolon({ anahtar: "status", etiket: "Durum", tip: "liste", secenekler: ["Derdest", "Karar"] }),
        kolon({ anahtar: "opening_date", etiket: "Açılış", tip: "tarih", grup: "Tarihler" }),
        kolon({ anahtar: "maddi_tazminat", etiket: "Maddi", tip: "para", grup: "Tutarlar" }),
        kolon({ anahtar: "active", etiket: "Aktif", tip: "mantik", siralanabilir: false }),
        kolon({ anahtar: "muvekkil_adlari", etiket: "Müvekkiller", tip: "metin", filtrelenebilir: false, siralanabilir: false, turetilmis: true, grup: "Taraflar" }),
        // §4.2 taraf bağlantılı: türetilmiş AMA filtrelenebilir, `eq` yok (EXISTS "herhangi biri içerir")
        kolon({ anahtar: "karsi_taraf_adlari", etiket: "Karşı Taraflar", tip: "metin", siralanabilir: false, turetilmis: true, grup: "Taraflar",
            oplar: ["contains", "is_null", "not_null"], oneriler: ["Sigorta A.Ş.", "Hastane"] }),
        // §5.2 veriden kapalı liste: tip metin KALIR, kontrol çoklu seçim, seçenekler sıklık sırasıyla
        kolon({ anahtar: "court", etiket: "Mahkeme", tip: "metin", kontrol: "coklu_secim", secenek_kaynagi: "veri",
            secenekler: ["Ankara 1. Asliye", "İzmir 3. Asliye"], grup: "Mahkeme ve konu" }),
        // §5.2 etiketli seçenekler: ham kod saklanır, gösterim etiketli
        kolon({ anahtar: "client_type", etiket: "Müvekkil Türü", tip: "metin", kontrol: "coklu_secim", secenek_kaynagi: "veri",
            secenekler: ["Individual", "Corporate"], secenek_etiketleri: { Individual: "Gerçek kişi", Corporate: "Tüzel kişi" } }),
        // §5.2 sanal arama kolonu: yalnız filtre
        kolon({ anahtar: "arama", etiket: "Ara", tip: "metin", turetilmis: true, siralanabilir: false, secilebilir: false, oplar: ["contains"] }),
        kolon({ anahtar: "dava_sayisi", etiket: "Dava Sayısı", tip: "sayi", turetilmis: true, grup: "Sistem" }),
        kolon({ anahtar: "email", etiket: "E-posta", tip: "metin", grup: "İletişim" }),
    ],
    hizli_filtreler: [
        hf("arama", { sunum: "arama" }),
        hf("opening_date"),
        hf("status"),
        hf("dava_sayisi", { sunum: "var_yok", etiket: "Davası var" }),
        hf("email", { sunum: "bos_anahtari", etiket: "E-postası yok" }),
    ],
    kolon_setleri: [{ ad: "Temel", kolonlar: ["tracking_no", "subject"] }],
};
const kolonOf = (anahtar: string) => KAYNAK.kolonlar.find(k => k.anahtar === anahtar)!;

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

    it("eq → between sayıda: number stringleşmez (§2.1 [min, max] JSON number); boş/mantık uç \"\" olur", () => {
        expect(degerSekleUyarla("between", 1000)).toEqual([1000, ""]);
        expect(degerSekleUyarla("between", [1000, 5000])).toEqual([1000, 5000]);
        expect(degerSekleUyarla("between", true)).toEqual(["", ""]);
        expect(degerSekleUyarla("between", undefined)).toEqual(["", ""]);
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

    it("§5.2 `in` listesinde `null` \"(boş)\" geçerlidir; `between` ucunda null geçersiz; tekil op'a taşınmaz", () => {
        expect(filtreTamamMi({ alan: "court", op: "in", deger: ["Ankara", null] }, "metin")).toBe(true);
        expect(filtreTamamMi({ alan: "court", op: "in", deger: [null] }, "metin")).toBe(true);
        expect(filtreTamamMi({ alan: "opening_date", op: "between", deger: ["2025-01-01", null] }, "tarih")).toBe(false);
        // in → eq: ilk DOLU değer; yalnız (boş) → değersiz
        expect(degerSekleUyarla("eq", [null, "Ankara"])).toBe("Ankara");
        expect(degerSekleUyarla("eq", [null])).toBeUndefined();
        expect(degerSekleUyarla("between", [null, "x"])).toEqual(["", "x"]);
        expect(degerSekleUyarla("in", ["Ankara", null])).toEqual(["Ankara", null]);
    });
});

describe("§5.2 seçenek etiketi ve seçilebilirlik", () => {
    it("secenekEtiketi: etiket haritasından, yoksa ham; null → \"(boş)\"", () => {
        expect(secenekEtiketi(kolonOf("client_type"), "Individual")).toBe("Gerçek kişi");
        expect(secenekEtiketi(kolonOf("client_type"), "Bilinmeyen")).toBe("Bilinmeyen");
        expect(secenekEtiketi(kolonOf("court"), "Ankara 1. Asliye")).toBe("Ankara 1. Asliye");
        expect(secenekEtiketi(kolonOf("court"), null)).toBe("(boş)");
    });

    it("kolonSecilebilirMi: secilebilir=false hayır, alan yoksa (eski katalog) evet, katalogda olmayan hayır", () => {
        expect(kolonSecilebilirMi(kolonOf("arama"))).toBe(false);
        expect(kolonSecilebilirMi(kolonOf("subject"))).toBe(true);
        expect(kolonSecilebilirMi({} as Pick<KatalogKolon, "secilebilir">)).toBe(true);
        expect(kolonSecilebilirMi(undefined)).toBe(false);
    });
});

describe("tanimGecerliMi — Önizle kapısı", () => {
    const temel: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["tracking_no"], filtreler: [], siralama: [] };

    it("kolon yoksa geçersiz, tek kolonla geçerli", () => {
        expect(tanimGecerliMi({ ...temel, kolonlar: [] }, KAYNAK)).toBe(false);
        expect(tanimGecerliMi(temel, KAYNAK)).toBe(true);
    });

    it("filtrelenemeyen türetilmiş kolon filtre/sıralama alanı olamaz ama kolon olarak seçilebilir", () => {
        expect(tanimGecerliMi({ ...temel, kolonlar: ["muvekkil_adlari"] }, KAYNAK)).toBe(true);
        expect(tanimGecerliMi({ ...temel, filtreler: [{ alan: "muvekkil_adlari", op: "eq", deger: "x" }] }, KAYNAK)).toBe(false);
        expect(tanimGecerliMi({ ...temel, siralama: [{ alan: "muvekkil_adlari", yon: "asc" }] }, KAYNAK)).toBe(false);
    });

    it("§4.2 taraf kolonu: türetilmiş ama filtrelenebilir — kapı kolonun `oplar`ına bakar (contains geçer, eq geçmez), sıralanamaz", () => {
        expect(tanimGecerliMi({ ...temel, filtreler: [{ alan: "karsi_taraf_adlari", op: "contains", deger: "Sigorta" }] }, KAYNAK)).toBe(true);
        expect(tanimGecerliMi({ ...temel, filtreler: [{ alan: "karsi_taraf_adlari", op: "is_null" }] }, KAYNAK)).toBe(true);
        expect(tanimGecerliMi({ ...temel, filtreler: [{ alan: "karsi_taraf_adlari", op: "eq", deger: "Sigorta" }] }, KAYNAK)).toBe(false);
        expect(tanimGecerliMi({ ...temel, siralama: [{ alan: "karsi_taraf_adlari", yon: "asc" }] }, KAYNAK)).toBe(false);
        expect(kolonOplari(kolonOf("karsi_taraf_adlari"))).toEqual(["contains", "is_null", "not_null"]);
        expect(kolonOplari(kolonOf("muvekkil_adlari"))).toEqual([]);
        // `oplar` boş/eksikse tip tablosuna düşülür (eski katalog cevabı)
        expect(kolonOplari({ tip: "liste", filtrelenebilir: true, oplar: [] })).toEqual(OP_BY_TIP.liste);
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

    it("§5.2 sanal `arama` kolonu: kolon olarak seçilemez (sunucu 422), filtre olarak contains geçer; `in` içinde null geçer", () => {
        expect(tanimGecerliMi({ ...temel, kolonlar: ["arama"] }, KAYNAK)).toBe(false);
        expect(tanimGecerliMi({ ...temel, filtreler: [{ alan: "arama", op: "contains", deger: "Ayşe" }] }, KAYNAK)).toBe(true);
        expect(tanimGecerliMi({ ...temel, filtreler: [{ alan: "court", op: "in", deger: ["Ankara 1. Asliye", null] }] }, KAYNAK)).toBe(true);
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

// ---------------------------------------------------------------------------
// G138 — §4.3 kontrol ↔ op çevirisi (sunum katmanı; sunucu sözleşmesi değişmez)
// ---------------------------------------------------------------------------

describe("§4.3 kontroldenFiltre — her kontrol doğru op'u üretir", () => {
    const tarih = (ek: Partial<Extract<KontrolDurumu, { kontrol: "tarih_araligi" }>>): KontrolDurumu =>
        ({ ...bosKontrol(kolonOf("opening_date")), ...ek } as KontrolDurumu);
    const sayi = (ek: Partial<Extract<KontrolDurumu, { kontrol: "sayi_araligi" }>>): KontrolDurumu =>
        ({ ...bosKontrol(kolonOf("maddi_tazminat")), ...ek } as KontrolDurumu);

    it("boş kontrol tanıma girmez (null); kontrolDoluMu false", () => {
        for (const anahtar of ["opening_date", "maddi_tazminat", "status", "subject", "active"]) {
            const b = bosKontrol(kolonOf(anahtar));
            expect(kontroldenFiltre(b)).toBeNull();
            expect(kontrolDoluMu(b)).toBe(false);
        }
    });

    it("tarih aralığı: iki uç between (ISO iki öğe), yalnız başlangıç gte, yalnız bitiş lte", () => {
        expect(kontroldenFiltre(tarih({ baslangic: "2025-01-01", bitis: "2025-12-31" })))
            .toEqual({ alan: "opening_date", op: "between", deger: ["2025-01-01", "2025-12-31"] });
        expect(kontroldenFiltre(tarih({ baslangic: "2025-01-01" }))).toEqual({ alan: "opening_date", op: "gte", deger: "2025-01-01" });
        expect(kontroldenFiltre(tarih({ bitis: "2025-12-31" }))).toEqual({ alan: "opening_date", op: "lte", deger: "2025-12-31" });
    });

    it("sayı/para aralığı: between iki JSON number, gte/lte number; 0 geçerli bir uçtur", () => {
        expect(kontroldenFiltre(sayi({ en_az: 1000, en_cok: 5000 }))).toEqual({ alan: "maddi_tazminat", op: "between", deger: [1000, 5000] });
        expect(kontroldenFiltre(sayi({ en_az: 0 }))).toEqual({ alan: "maddi_tazminat", op: "gte", deger: 0 });
        expect(kontroldenFiltre(sayi({ en_cok: 99.5 }))).toEqual({ alan: "maddi_tazminat", op: "lte", deger: 99.5 });
    });

    it("çoklu seçim: 1 seçim eq, n seçim in (dizi); serbest metin yolu YOK", () => {
        const b = bosKontrol(kolonOf("status"));
        expect(kontroldenFiltre({ ...b, secili: ["Derdest"] } as KontrolDurumu)).toEqual({ alan: "status", op: "eq", deger: "Derdest" });
        expect(kontroldenFiltre({ ...b, secili: ["Derdest", "Karar"] } as KontrolDurumu)).toEqual({ alan: "status", op: "in", deger: ["Derdest", "Karar"] });
        expect(Object.keys(b)).not.toContain("metin");
        expect(Object.keys(b)).not.toContain("bos");
    });

    it("§5.2 çoklu seçimde \"(boş)\": seçimle birlikte `in` içinde null öğesi, yalnız (boş) → is_null; etiketli kolon HAM kodla gider", () => {
        const b = bosKontrol(kolonOf("court"));
        expect(b).toEqual({ kontrol: "coklu_secim", alan: "court", secili: [] });
        expect(kontroldenFiltre({ ...b, secili: ["Ankara 1. Asliye", null] } as KontrolDurumu))
            .toEqual({ alan: "court", op: "in", deger: ["Ankara 1. Asliye", null] });
        expect(kontroldenFiltre({ ...b, secili: [null] } as KontrolDurumu)).toEqual({ alan: "court", op: "is_null" });
        expect(kontroldenFiltre({ ...b, secili: [null, "İzmir 3. Asliye"] } as KontrolDurumu))
            .toEqual({ alan: "court", op: "in", deger: [null, "İzmir 3. Asliye"] });
        const t = bosKontrol(kolonOf("client_type"));
        expect(kontroldenFiltre({ ...t, secili: ["Individual"] } as KontrolDurumu)).toEqual({ alan: "client_type", op: "eq", deger: "Individual" });
    });

    it("§5.3 var/yok: hepsi → filtre yok, var → gte 1, yok → eq 0; yalnız sayı aralığı kolonunda (metinde kolonun kontrolü)", () => {
        const b = bosKontrol(kolonOf("dava_sayisi"), "var_yok");
        expect(b).toEqual({ kontrol: "var_yok", alan: "dava_sayisi", durum: "hepsi" });
        expect(kontroldenFiltre(b)).toBeNull();
        expect(kontroldenFiltre({ ...b, durum: "var" } as KontrolDurumu)).toEqual({ alan: "dava_sayisi", op: "gte", deger: 1 });
        expect(kontroldenFiltre({ ...b, durum: "yok" } as KontrolDurumu)).toEqual({ alan: "dava_sayisi", op: "eq", deger: 0 });
        expect(bosKontrol(kolonOf("subject"), "var_yok").kontrol).toBe("metin_icerir");
    });

    it("§5.3 boş anahtarı: açık → is_null değersiz, kapalı → yok; `is_null` izinsiz kolonda kolonun kontrolü", () => {
        const b = bosKontrol(kolonOf("email"), "bos_anahtari");
        expect(b).toEqual({ kontrol: "bos_anahtari", alan: "email", acik: false });
        expect(kontroldenFiltre(b)).toBeNull();
        expect(kontroldenFiltre({ ...b, acik: true } as KontrolDurumu)).toEqual({ alan: "email", op: "is_null" });
        expect(bosKontrol(kolonOf("arama"), "bos_anahtari").kontrol).toBe("metin_icerir");
    });

    it("§5.3 arama kutusu (`arama` kolonu, sunum arama): metin kontrolü, yalnız contains", () => {
        const b = bosKontrol(kolonOf("arama"), "arama");
        expect(b).toEqual({ kontrol: "metin_icerir", alan: "arama", metin: "", tam: false });
        expect(kontroldenFiltre({ ...b, metin: "Ayşe" } as KontrolDurumu)).toEqual({ alan: "arama", op: "contains", deger: "Ayşe" });
    });

    it("metin: contains; combobox seçimi (tam) eq; boşluk kırpılır", () => {
        const b = bosKontrol(kolonOf("subject"));
        expect(kontroldenFiltre({ ...b, metin: " Tazminat " } as KontrolDurumu)).toEqual({ alan: "subject", op: "contains", deger: "Tazminat" });
        expect(kontroldenFiltre({ ...b, metin: "Tazminat", tam: true } as KontrolDurumu)).toEqual({ alan: "subject", op: "eq", deger: "Tazminat" });
        expect(kontroldenFiltre({ ...b, metin: "   " } as KontrolDurumu)).toBeNull();
    });

    it("mantık: eq true/false; null boş", () => {
        const b = bosKontrol(kolonOf("active"));
        expect(kontroldenFiltre({ ...b, deger: true } as KontrolDurumu)).toEqual({ alan: "active", op: "eq", deger: true });
        expect(kontroldenFiltre({ ...b, deger: false } as KontrolDurumu)).toEqual({ alan: "active", op: "eq", deger: false });
    });

    it("\"boş olanlar\" anahtarı hiçbir kontrolde YOK (§5.1 madde 8): tarih/sayı/metin/mantık boşluğu gelişmiş çipten is_null", () => {
        for (const anahtar of ["opening_date", "maddi_tazminat", "subject", "active", "status"]) {
            expect(Object.keys(bosKontrol(kolonOf(anahtar)))).not.toContain("bos");
        }
        expect(kontroldenFiltre({ kontrol: "gelismis", alan: "opening_date", op: "is_null" })).toEqual({ alan: "opening_date", op: "is_null" });
        expect(kontroldenFiltre(tarih({ baslangic: "2025-01-01" }))).toEqual({ alan: "opening_date", op: "gte", deger: "2025-01-01" });
    });

    it("gelişmiş çip filtreyi olduğu gibi taşır (deger yoksa anahtar da yok)", () => {
        expect(kontroldenFiltre({ kontrol: "gelismis", alan: "status", op: "ne", deger: "Karar" })).toEqual({ alan: "status", op: "ne", deger: "Karar" });
        expect(kontroldenFiltre({ kontrol: "gelismis", alan: "status", op: "not_null" })).toEqual({ alan: "status", op: "not_null" });
    });
});

describe("§4.3 filtredenKontrol — şablon/asistan tanımı şeride kayıpsız çözülür", () => {
    const ORNEKLER: Array<[string, Filtre, FiltreKontrolu | "gelismis"]> = [
        ["opening_date", { alan: "opening_date", op: "between", deger: ["2025-01-01", "2025-12-31"] }, "tarih_araligi"],
        ["opening_date", { alan: "opening_date", op: "gte", deger: "2025-01-01" }, "tarih_araligi"],
        ["opening_date", { alan: "opening_date", op: "lte", deger: "2025-12-31" }, "tarih_araligi"],
        ["opening_date", { alan: "opening_date", op: "is_null" }, "gelismis"],
        ["opening_date", { alan: "opening_date", op: "eq", deger: "2025-01-01" }, "gelismis"],
        ["opening_date", { alan: "opening_date", op: "not_null" }, "gelismis"],
        ["maddi_tazminat", { alan: "maddi_tazminat", op: "between", deger: [1000, 5000] }, "sayi_araligi"],
        ["maddi_tazminat", { alan: "maddi_tazminat", op: "gte", deger: 0 }, "sayi_araligi"],
        ["maddi_tazminat", { alan: "maddi_tazminat", op: "lte", deger: 10 }, "sayi_araligi"],
        ["maddi_tazminat", { alan: "maddi_tazminat", op: "eq", deger: 1000 }, "gelismis"],
        ["status", { alan: "status", op: "eq", deger: "Derdest" }, "coklu_secim"],
        ["status", { alan: "status", op: "in", deger: ["Derdest", "Karar"] }, "coklu_secim"],
        ["status", { alan: "status", op: "is_null" }, "coklu_secim"],
        ["status", { alan: "status", op: "ne", deger: "Karar" }, "gelismis"],
        ["status", { alan: "status", op: "not_null" }, "gelismis"],
        ["subject", { alan: "subject", op: "contains", deger: "Tazminat" }, "metin_icerir"],
        ["subject", { alan: "subject", op: "eq", deger: "Tazminat" }, "metin_icerir"],
        ["subject", { alan: "subject", op: "in", deger: ["a", "b"] }, "gelismis"],
        ["subject", { alan: "subject", op: "ne", deger: "x" }, "gelismis"],
        ["subject", { alan: "subject", op: "is_null" }, "gelismis"],
        ["active", { alan: "active", op: "eq", deger: true }, "mantik"],
        ["active", { alan: "active", op: "is_null" }, "gelismis"],
        ["karsi_taraf_adlari", { alan: "karsi_taraf_adlari", op: "contains", deger: "Sigorta" }, "metin_icerir"],
        // §5.2: veriden liste `in` içinde null "(boş)"; etiketli kolon ham kodla; sanal arama
        ["court", { alan: "court", op: "in", deger: ["Ankara 1. Asliye", null] }, "coklu_secim"],
        ["court", { alan: "court", op: "in", deger: [null, "İzmir 3. Asliye", "Ankara 1. Asliye"] }, "coklu_secim"],
        ["court", { alan: "court", op: "eq", deger: "İzmir 3. Asliye" }, "coklu_secim"],
        ["court", { alan: "court", op: "contains", deger: "Ank" }, "gelismis"],
        ["client_type", { alan: "client_type", op: "in", deger: ["Individual", "Corporate"] }, "coklu_secim"],
        ["arama", { alan: "arama", op: "contains", deger: "Ayşe" }, "metin_icerir"],
        ["email", { alan: "email", op: "is_null" }, "gelismis"],
        ["dava_sayisi", { alan: "dava_sayisi", op: "gte", deger: 1 }, "sayi_araligi"],
    ];

    it.each(ORNEKLER)("%s %j → %s ve gidiş-dönüş aynı filtreyi verir", (anahtar, f, beklenenKontrol) => {
        const d = filtredenKontrol(f, kolonOf(anahtar));
        expect(d.kontrol).toBe(beklenenKontrol);
        expect(kontroldenFiltre(d)).toEqual(f);
    });

    it("tek değerli `in` eş anlamlı `eq`'e, `in [null]` eş anlamlı `is_null`'a normalize olur (bilinen iki istisna)", () => {
        const d = filtredenKontrol({ alan: "status", op: "in", deger: ["Derdest"] }, kolonOf("status"));
        expect(d.kontrol).toBe("coklu_secim");
        expect(kontroldenFiltre(d)).toEqual({ alan: "status", op: "eq", deger: "Derdest" });
        const b = filtredenKontrol({ alan: "court", op: "in", deger: [null] }, kolonOf("court"));
        expect(b).toEqual({ kontrol: "coklu_secim", alan: "court", secili: [null] });
        expect(kontroldenFiltre(b)).toEqual({ alan: "court", op: "is_null" });
        // is_null → çoklu seçimde "(boş)" seçili görünür (yan kutucuk değil)
        expect(filtredenKontrol({ alan: "court", op: "is_null" }, kolonOf("court"))).toEqual({ kontrol: "coklu_secim", alan: "court", secili: [null] });
    });

    it("§5.3 sunumla çözüm: var/yok yuvası gte 1 / eq 0'ı alır (gte 5 almaz → kolonun kontrolü), boş anahtarı is_null'ı alır; gidiş-dönüş aynı", () => {
        const dava = kolonOf("dava_sayisi");
        const var_ = filtredenKontrol({ alan: "dava_sayisi", op: "gte", deger: 1 }, dava, "var_yok");
        expect(var_).toEqual({ kontrol: "var_yok", alan: "dava_sayisi", durum: "var" });
        expect(kontroldenFiltre(var_)).toEqual({ alan: "dava_sayisi", op: "gte", deger: 1 });
        const yok = filtredenKontrol({ alan: "dava_sayisi", op: "eq", deger: 0 }, dava, "var_yok");
        expect(yok).toEqual({ kontrol: "var_yok", alan: "dava_sayisi", durum: "yok" });
        expect(kontroldenFiltre(yok)).toEqual({ alan: "dava_sayisi", op: "eq", deger: 0 });
        expect(filtredenKontrol({ alan: "dava_sayisi", op: "gte", deger: 5 }, dava, "var_yok"))
            .toEqual({ kontrol: "sayi_araligi", alan: "dava_sayisi", en_az: 5, en_cok: null });
        expect(filtredenKontrol({ alan: "dava_sayisi", op: "eq", deger: 2 }, dava, "var_yok").kontrol).toBe("gelismis");

        const email = kolonOf("email");
        const bos = filtredenKontrol({ alan: "email", op: "is_null" }, email, "bos_anahtari");
        expect(bos).toEqual({ kontrol: "bos_anahtari", alan: "email", acik: true });
        expect(kontroldenFiltre(bos)).toEqual({ alan: "email", op: "is_null" });
        expect(filtredenKontrol({ alan: "email", op: "contains", deger: "@" }, email, "bos_anahtari"))
            .toEqual({ kontrol: "metin_icerir", alan: "email", metin: "@", tam: false });
        // arama/cipler sunumu kolonun kontrolünü değiştirmez
        expect(filtredenKontrol({ alan: "arama", op: "contains", deger: "x" }, kolonOf("arama"), "arama").kontrol).toBe("metin_icerir");
        expect(filtredenKontrol({ alan: "court", op: "in", deger: ["Ankara 1. Asliye", null] }, kolonOf("court"), "cipler"))
            .toEqual({ kontrol: "coklu_secim", alan: "court", secili: ["Ankara 1. Asliye", null] });
    });

    it("kolon yok ya da filtrelenemez → gelişmiş çip; değer tipi uymayan op da gelişmiş", () => {
        expect(filtredenKontrol({ alan: "yok", op: "eq", deger: "x" }, undefined).kontrol).toBe("gelismis");
        expect(filtredenKontrol({ alan: "muvekkil_adlari", op: "contains", deger: "x" }, kolonOf("muvekkil_adlari")).kontrol).toBe("gelismis");
        // between ama tek öğe: tarih kontrolüne oturmaz, kaybolmaz
        const d = filtredenKontrol({ alan: "opening_date", op: "between", deger: ["2025-01-01"] }, kolonOf("opening_date"));
        expect(d.kontrol).toBe("gelismis");
        expect(kontroldenFiltre(d)).toEqual({ alan: "opening_date", op: "between", deger: ["2025-01-01"] });
    });
});

describe("gelişmiş op'lar ve çip özeti", () => {
    it("\"…\" menüsü yalnız kolonun `oplar`ında olup kontrolün doğal üretmediklerini sunar; tarih/sayı/metin/mantıkta \"boş\" (is_null) buradadır", () => {
        expect(gelismisOplar(kolonOf("status"))).toEqual(["ne", "not_null"]);
        expect(gelismisOplar(kolonOf("opening_date"))).toEqual(["eq", "is_null", "not_null"]);
        expect(gelismisOplar(kolonOf("subject"))).toEqual(["ne", "in", "is_null", "not_null"]);
        expect(gelismisOplar(kolonOf("active"))).toEqual(["is_null"]);
        // Taraf kolonu: oplar [contains, is_null, not_null] → is_null + not_null
        expect(gelismisOplar(kolonOf("karsi_taraf_adlari"))).toEqual(["is_null", "not_null"]);
        // Veriden liste: "(boş)" seçeneği doğal → is_null menüde değil; contains gelişmiş
        expect(gelismisOplar(kolonOf("court"))).toEqual(["ne", "contains", "not_null"]);
        // Sunum kontrolleri kendi türüyle: var/yok gte+eq doğal, boş anahtarı is_null doğal
        expect(gelismisOplar(kolonOf("dava_sayisi"), "var_yok")).toEqual(["lte", "between", "is_null", "not_null"]);
        expect(gelismisOplar(kolonOf("email"), "bos_anahtari")).toEqual(["eq", "ne", "contains", "in", "not_null"]);
        const her: FiltreOp[] = ["eq", "ne", "contains", "in", "gte", "lte", "between", "is_null", "not_null"];
        for (const k of Object.keys(KONTROL_DOGAL_OPLARI) as KontrolTuru[]) {
            for (const op of KONTROL_DOGAL_OPLARI[k]) expect(her).toContain(op);
        }
        for (const k of ["tarih_araligi", "sayi_araligi", "metin_icerir", "mantik"] as FiltreKontrolu[]) {
            expect(KONTROL_DOGAL_OPLARI[k]).not.toContain("is_null");
        }
    });

    it("özet: tarih dd.MM.yyyy aralığı, sayı tr-TR, çoklu virgülle ((boş) → boş, etiketli), metin içerir/=, var/yok, boş anahtarı, gelişmiş op etiketi", () => {
        expect(kontrolOzeti({ kontrol: "tarih_araligi", alan: "a", baslangic: "2025-01-01", bitis: "2025-12-31" }, "tarih")).toBe("01.01.2025 – 31.12.2025");
        expect(kontrolOzeti({ kontrol: "tarih_araligi", alan: "a", baslangic: "2025-01-01", bitis: "" }, "tarih")).toBe("≥ 01.01.2025");
        expect(kontrolOzeti({ kontrol: "sayi_araligi", alan: "a", en_az: 1000, en_cok: null }, "para")).toBe("≥ 1.000");
        expect(kontrolOzeti({ kontrol: "coklu_secim", alan: "a", secili: ["Derdest", "Karar"] }, "liste")).toBe("Derdest, Karar");
        expect(kontrolOzeti({ kontrol: "coklu_secim", alan: "a", secili: ["Ankara", null] }, "metin")).toBe("Ankara, boş");
        expect(kontrolOzeti({ kontrol: "coklu_secim", alan: "a", secili: [null] }, "metin")).toBe("boş");
        expect(kontrolOzeti({ kontrol: "coklu_secim", alan: "a", secili: ["Individual", "X"] }, "metin", { Individual: "Gerçek kişi" })).toBe("Gerçek kişi, X");
        expect(kontrolOzeti({ kontrol: "metin_icerir", alan: "a", metin: "x", tam: false }, "metin")).toBe("içerir \"x\"");
        expect(kontrolOzeti({ kontrol: "metin_icerir", alan: "a", metin: "x", tam: true }, "metin")).toBe("= \"x\"");
        expect(kontrolOzeti({ kontrol: "var_yok", alan: "a", durum: "var" }, "sayi")).toBe("var");
        expect(kontrolOzeti({ kontrol: "var_yok", alan: "a", durum: "hepsi" }, "sayi")).toBe("");
        expect(kontrolOzeti({ kontrol: "bos_anahtari", alan: "a", acik: true }, "metin")).toBe("boş");
        expect(kontrolOzeti({ kontrol: "gelismis", alan: "a", op: "ne", deger: "Karar" }, "liste")).toBe("eşit değil Karar");
        expect(kontrolOzeti({ kontrol: "gelismis", alan: "a", op: "not_null" }, "liste")).toBe("dolu");
        expect(kontrolOzeti({ kontrol: "gelismis", alan: "a", op: "in", deger: ["Individual", null] }, "metin", { Individual: "Gerçek kişi" })).toBe("şunlardan biri Gerçek kişi, boş");
    });
});

describe("tarihKisayolu — sabit bugünle", () => {
    const bugun = new Date(2026, 8, 7); // 7 Eylül 2026 (yerel)

    it("bu yıl 1 Ocak–bugün; geçen yıl tam yıl", () => {
        expect(tarihKisayolu("bu_yil", bugun)).toEqual(["2026-01-01", "2026-09-07"]);
        expect(tarihKisayolu("gecen_yil", bugun)).toEqual(["2025-01-01", "2025-12-31"]);
    });

    it("son 30 gün bugün dahil; son 12 ay bir yıl önceki aynı gün", () => {
        expect(tarihKisayolu("son_30_gun", bugun)).toEqual(["2026-08-09", "2026-09-07"]);
        expect(tarihKisayolu("son_12_ay", bugun)).toEqual(["2025-09-07", "2026-09-07"]);
        // Ay/yıl sınırı: 1 Ocak'tan 30 gün geri geçen yılın Aralık'ına düşer
        expect(tarihKisayolu("son_30_gun", new Date(2026, 0, 1))).toEqual(["2025-12-03", "2026-01-01"]);
    });
});
