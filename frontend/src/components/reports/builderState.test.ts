// builderState (G138) — filtre şeridi modeli: kaynağın hızlı filtre yuvaları boş açılır,
// şablon/asistan tanımı yuvalara ve "eklenen alan"lara kayıpsız çözülür (sıra korunur),
// `tanimOlustur` daima §2.1 JSON'unu verir; başlıktan sıralama döngüsü + tavan 3.
import { describe, expect, it, vi } from "vitest";

// lib/reports `apiClient`'ı içe aktarır; msalConfig `window` ister — node ortamında sahte.
vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import { OP_BY_TIP, type FiltreKontrolu, type KatalogKolon, type KatalogVeriKaynagi, type KolonTipi, type RaporTanimi } from "@/lib/reports";
import { kaynakIcinBaslangic, seritFiltreleri, siralamaDongusu, tanimOlustur, tanimdanDurum } from "./builderState";

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
        ...k,
    };
}

const DAVALAR: KatalogVeriKaynagi = {
    anahtar: "davalar",
    etiket: "Davalar",
    aciklama: "",
    varsayilan_kolonlar: ["tracking_no", "subject", "yok_boyle_kolon"],
    kolonlar: [
        kolon({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" }),
        kolon({ anahtar: "subject", etiket: "Konu", tip: "metin" }),
        kolon({ anahtar: "status", etiket: "Durum", tip: "liste", secenekler: ["Derdest", "Karar"] }),
        kolon({ anahtar: "opening_date", etiket: "Açılış", tip: "tarih", grup: "Tarihler" }),
        kolon({ anahtar: "karar_tarihi", etiket: "Karar Tarihi", tip: "tarih", grup: "Tarihler" }),
        kolon({ anahtar: "maddi_tazminat", etiket: "Maddi", tip: "para", grup: "Tutarlar" }),
        kolon({ anahtar: "muvekkil_adlari", etiket: "Müvekkiller", tip: "metin", filtrelenebilir: false, siralanabilir: false, turetilmis: true }),
    ],
    hizli_filtreler: [
        { alan: "opening_date", alternatifler: ["karar_tarihi", "silinmis_alan"] },
        { alan: "status", alternatifler: [] },
        { alan: "muvekkil_adlari", alternatifler: [] }, // filtrelenemez → yuva açılmaz
        { alan: "maddi_tazminat", alternatifler: [] },
    ],
    kolon_setleri: [{ ad: "Temel", kolonlar: ["tracking_no", "subject"] }],
};

describe("kaynakIcinBaslangic", () => {
    it("varsayılan kolonlar (katalogda olmayan elenir), hızlı filtre yuvaları BOŞ ve sıralı, sıralama boş", () => {
        const d = kaynakIcinBaslangic(DAVALAR);
        expect(d.veri_kaynagi).toBe("davalar");
        expect(d.kolonlar).toEqual(["tracking_no", "subject"]);
        expect(d.serit.map(o => o.durum.alan)).toEqual(["opening_date", "status", "maddi_tazminat"]);
        expect(d.serit.every(o => o.hizli)).toBe(true);
        expect(d.serit.map(o => o.durum.kontrol)).toEqual(["tarih_araligi", "coklu_secim", "sayi_araligi"]);
        // Alan değiştirici yalnız tarih yuvasında; katalogda olmayan alternatif elenir
        expect(d.serit[0].alanSecenekleri).toEqual(["opening_date", "karar_tarihi"]);
        expect(d.serit[1].alanSecenekleri).toEqual([]);
        expect(d.siralama).toEqual([]);
        // Boş yuvalar tanıma girmez
        expect(tanimOlustur(d)).toEqual({ veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [] });
    });
});

describe("tanimdanDurum ↔ tanimOlustur — gidiş-dönüş", () => {
    const TANIM: RaporTanimi = {
        veri_kaynagi: "davalar",
        kolonlar: ["tracking_no", "status"],
        filtreler: [
            { alan: "subject", op: "contains", deger: "Tazminat" },                   // yuva yok → eklenen alan
            { alan: "status", op: "in", deger: ["Derdest", "Karar"] },               // yuva
            { alan: "karar_tarihi", op: "between", deger: ["2025-01-01", "2025-12-31"] }, // tarih yuvasının ALTERNATİFİ
            { alan: "status", op: "ne", deger: "Karar" },                            // yuva dolu + çözülemez → gelişmiş, eklenen
            { alan: "maddi_tazminat", op: "gte", deger: 1000 },                      // yuva
        ],
        siralama: [{ alan: "opening_date", yon: "desc" }],
    };

    it("filtreler yuvalara ve eklenen alanlara çözülür; dolu öğeler tanım sırasıyla önce, boş yuvalar sonra", () => {
        const d = tanimdanDurum(TANIM, DAVALAR);
        expect(d.kolonlar).toEqual(["tracking_no", "status"]);
        expect(d.siralama).toEqual([{ alan: "opening_date", yon: "desc" }]);
        expect(d.serit.map(o => [o.durum.alan, o.durum.kontrol, o.hizli])).toEqual([
            ["subject", "metin_icerir", false],
            ["status", "coklu_secim", true],
            ["karar_tarihi", "tarih_araligi", true],
            ["status", "gelismis", false],
            ["maddi_tazminat", "sayi_araligi", true],
        ]);
        // Alternatife çözülen tarih yuvası değiştiricisini korur
        expect(d.serit[2].alanSecenekleri).toEqual(["opening_date", "karar_tarihi"]);
        // Boş yuva kalmadı (üçü de doldu)
        expect(d.serit.filter(o => o.hizli)).toHaveLength(3);
    });

    it("tanimOlustur aynı JSON'u aynı sırayla geri verir (şablon karşılaştırması buna dayanır)", () => {
        const d = tanimdanDurum(TANIM, DAVALAR);
        expect(JSON.stringify(tanimOlustur(d))).toBe(JSON.stringify(TANIM));
    });

    it("gelişmiş çipe düşen filtre yuvayı ezmez: yuva boş kalır, filtre eklenen alan olarak korunur", () => {
        const tanim: RaporTanimi = {
            veri_kaynagi: "davalar", kolonlar: ["tracking_no"],
            filtreler: [{ alan: "opening_date", op: "not_null" }], siralama: [],
        };
        const d = tanimdanDurum(tanim, DAVALAR);
        expect(d.serit.map(o => [o.durum.alan, o.durum.kontrol, o.hizli])).toEqual([
            ["opening_date", "gelismis", false],
            ["status", "coklu_secim", true],
            ["maddi_tazminat", "sayi_araligi", true],
            ["opening_date", "tarih_araligi", true],
        ]);
        expect(seritFiltreleri(d.serit)).toEqual([{ alan: "opening_date", op: "not_null" }]);
    });

    it("aynı alanda iki filtre: ilki yuvayı doldurur, ikincisi eklenen alan olur; ikisi de kalır", () => {
        const tanim: RaporTanimi = {
            veri_kaynagi: "davalar", kolonlar: ["tracking_no"],
            filtreler: [
                { alan: "opening_date", op: "gte", deger: "2025-01-01" },
                { alan: "opening_date", op: "lte", deger: "2025-06-30" },
            ],
            siralama: [],
        };
        const d = tanimdanDurum(tanim, DAVALAR);
        expect(d.serit.slice(0, 2).map(o => o.hizli)).toEqual([true, false]);
        expect(tanimOlustur(d).filtreler).toEqual(tanim.filtreler);
    });

    it("katalogda olmayan alanın filtresi de gelişmiş çip olarak korunur (tanım kaybolmaz; kapı geçersiz sayar)", () => {
        const tanim: RaporTanimi = {
            veri_kaynagi: "davalar", kolonlar: ["tracking_no"],
            filtreler: [{ alan: "eski_alan", op: "eq", deger: "x" }], siralama: [],
        };
        const d = tanimdanDurum(tanim, DAVALAR);
        expect(d.serit[0].durum).toEqual({ kontrol: "gelismis", alan: "eski_alan", op: "eq", deger: "x" });
        expect(tanimOlustur(d).filtreler).toEqual(tanim.filtreler);
    });
});

describe("siralamaDongusu — başlıktan sıralama", () => {
    it("yok → artan → azalan → kaldır", () => {
        let s = siralamaDongusu([], "opening_date");
        expect(s).toEqual([{ alan: "opening_date", yon: "asc" }]);
        s = siralamaDongusu(s, "opening_date");
        expect(s).toEqual([{ alan: "opening_date", yon: "desc" }]);
        s = siralamaDongusu(s, "opening_date");
        expect(s).toEqual([]);
    });

    it("en fazla 3 alan; dördüncüde en eski düşer, diğerlerinin sırası ve yönü korunur", () => {
        let s = siralamaDongusu([], "a");
        s = siralamaDongusu(s, "b");
        s = siralamaDongusu(s, "b"); // b desc
        s = siralamaDongusu(s, "c");
        expect(s).toEqual([{ alan: "a", yon: "asc" }, { alan: "b", yon: "desc" }, { alan: "c", yon: "asc" }]);
        s = siralamaDongusu(s, "d");
        expect(s).toEqual([{ alan: "b", yon: "desc" }, { alan: "c", yon: "asc" }, { alan: "d", yon: "asc" }]);
        // Mevcut alanı çevirmek tavanı tetiklemez
        s = siralamaDongusu(s, "c");
        expect(s).toEqual([{ alan: "b", yon: "desc" }, { alan: "c", yon: "desc" }, { alan: "d", yon: "asc" }]);
    });
});
