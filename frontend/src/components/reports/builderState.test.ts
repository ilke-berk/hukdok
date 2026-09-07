// builderState (G138) — filtre şeridi modeli: kaynağın hızlı filtre yuvaları boş açılır,
// şablon/asistan tanımı yuvalara ve "eklenen alan"lara kayıpsız çözülür (sıra korunur),
// `tanimOlustur` daima §2.1 JSON'unu verir; başlıktan sıralama döngüsü + tavan 3.
import { describe, expect, it, vi } from "vitest";

// lib/reports `apiClient`'ı içe aktarır; msalConfig `window` ister — node ortamında sahte.
vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import {
    OP_BY_TIP, type FiltreKontrolu, type HizliFiltre, type KatalogKolon, type KatalogVeriKaynagi, type KolonTipi, type RaporTanimi,
} from "@/lib/reports";
import { kaynakIcinBaslangic, seritFiltreleri, seritiTemizle, siralamaDongusu, tanimOlustur, tanimdanDurum } from "./builderState";

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
        hf("opening_date", { alternatifler: ["karar_tarihi", "silinmis_alan"] }),
        hf("status"),
        hf("muvekkil_adlari"), // filtrelenemez → yuva açılmaz
        hf("maddi_tazminat"),
    ],
    kolon_setleri: [{ ad: "Temel", kolonlar: ["tracking_no", "subject"] }],
};

/** §5.1 müvekkil şeridi (katalog sahtesi §5.2 sözleşmesiyle): arama · kategori çipleri · il · uzmanlık · davası var/yok · e-postası yok · cep yok. */
const MUVEKKILLER: KatalogVeriKaynagi = {
    anahtar: "muvekkiller",
    etiket: "Müvekkiller",
    aciklama: "",
    varsayilan_kolonlar: ["name", "arama", "category"],
    kolonlar: [
        kolon({ anahtar: "name", etiket: "Ad", tip: "metin" }),
        kolon({ anahtar: "arama", etiket: "Ara", tip: "metin", turetilmis: true, siralanabilir: false, secilebilir: false, oplar: ["contains"] }),
        kolon({ anahtar: "category", etiket: "Kategori", tip: "liste", secenekler: ["Doktor", "Hasta"], grup: "Sınıflandırma" }),
        kolon({ anahtar: "il", etiket: "İl", tip: "metin", kontrol: "coklu_secim", secenek_kaynagi: "veri", secenekler: ["İstanbul", "Ankara", "İzmir"], grup: "İletişim" }),
        kolon({ anahtar: "specialty", etiket: "Uzmanlık", tip: "metin", kontrol: "coklu_secim", secenek_kaynagi: "veri", secenekler: ["Ortopedi"], grup: "Sınıflandırma" }),
        kolon({ anahtar: "client_type", etiket: "Müvekkil Türü", tip: "metin", kontrol: "coklu_secim", secenek_kaynagi: "veri",
            secenekler: ["Individual", "Corporate"], secenek_etiketleri: { Individual: "Gerçek kişi", Corporate: "Tüzel kişi" }, grup: "Sınıflandırma" }),
        kolon({ anahtar: "dava_sayisi", etiket: "Dava Sayısı", tip: "sayi", turetilmis: true, siralanabilir: false, grup: "Sistem" }),
        kolon({ anahtar: "email", etiket: "E-posta", tip: "metin", grup: "İletişim" }),
        kolon({ anahtar: "mobile_phone", etiket: "Cep Telefonu", tip: "metin", grup: "İletişim" }),
    ],
    hizli_filtreler: [
        hf("arama", { sunum: "arama" }),
        hf("category", { sunum: "cipler" }),
        hf("il"),
        hf("specialty"),
        hf("dava_sayisi", { sunum: "var_yok", etiket: "Davası var" }),
        hf("email", { sunum: "bos_anahtari", etiket: "E-postası yok" }),
        hf("mobile_phone", { sunum: "bos_anahtari", etiket: "Cep telefonu yok" }),
    ],
    kolon_setleri: [{ ad: "Temel", kolonlar: ["name", "arama"] }],
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
        // Eklenen/yuva ayrımı: yuvalar varsayılan sunumla, etiket yok
        expect(d.serit.map(o => [o.sunum, o.etiket])).toEqual([["varsayilan", null], ["varsayilan", null], ["varsayilan", null]]);
    });

    it("§5.1 müvekkil şeridi: yuvalar §5.2 sırası ve sunumuyla; var/yok ve boş anahtarı kendi kontrolüyle; `secilebilir=false` varsayılan kolondan düşer", () => {
        const d = kaynakIcinBaslangic(MUVEKKILLER);
        expect(d.kolonlar).toEqual(["name", "category"]);
        expect(d.serit.map(o => [o.durum.alan, o.durum.kontrol, o.sunum, o.etiket])).toEqual([
            ["arama", "metin_icerir", "arama", null],
            ["category", "coklu_secim", "cipler", null],
            ["il", "coklu_secim", "varsayilan", null],
            ["specialty", "coklu_secim", "varsayilan", null],
            ["dava_sayisi", "var_yok", "var_yok", "Davası var"],
            ["email", "bos_anahtari", "bos_anahtari", "E-postası yok"],
            ["mobile_phone", "bos_anahtari", "bos_anahtari", "Cep telefonu yok"],
        ]);
        expect(d.serit.every(o => o.hizli)).toBe(true);
        expect(tanimOlustur(d).filtreler).toEqual([]);
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

    it("§5.3 müvekkil şeridi gidiş-dönüş: arama contains → arama kutusu, in içinde null → (boş) seçimi, gte 1 → var/yok, is_null → boş anahtarı; JSON aynı", () => {
        const tanim: RaporTanimi = {
            veri_kaynagi: "muvekkiller",
            kolonlar: ["name"],
            filtreler: [
                { alan: "arama", op: "contains", deger: "Ayşe" },
                { alan: "category", op: "in", deger: ["Doktor", "Hasta"] },
                { alan: "il", op: "in", deger: ["Ankara", null] },
                { alan: "client_type", op: "eq", deger: "Individual" },   // yuva yok → eklenen alan (çoklu seçim, ham kod)
                { alan: "dava_sayisi", op: "gte", deger: 1 },
                { alan: "email", op: "is_null" },
                { alan: "mobile_phone", op: "contains", deger: "05" },    // boş anahtarı yuvasına oturmaz → eklenen metin, yuva boş kalır
            ],
            siralama: [],
        };
        const d = tanimdanDurum(tanim, MUVEKKILLER);
        expect(d.serit.map(o => [o.durum.alan, o.durum.kontrol, o.sunum, o.hizli])).toEqual([
            ["arama", "metin_icerir", "arama", true],
            ["category", "coklu_secim", "cipler", true],
            ["il", "coklu_secim", "varsayilan", true],
            ["client_type", "coklu_secim", "varsayilan", false],
            ["dava_sayisi", "var_yok", "var_yok", true],
            ["email", "bos_anahtari", "bos_anahtari", true],
            ["mobile_phone", "metin_icerir", "varsayilan", false],
            ["specialty", "coklu_secim", "varsayilan", true],
            ["mobile_phone", "bos_anahtari", "bos_anahtari", true],
        ]);
        expect(d.serit[2].durum).toEqual({ kontrol: "coklu_secim", alan: "il", secili: ["Ankara", null] });
        expect(d.serit[4].durum).toEqual({ kontrol: "var_yok", alan: "dava_sayisi", durum: "var" });
        expect(d.serit[5].durum).toEqual({ kontrol: "bos_anahtari", alan: "email", acik: true });
        expect(JSON.stringify(tanimOlustur(d))).toBe(JSON.stringify(tanim));

        // `dava_sayisi gte 5` var/yok yuvasına oturmaz: sayı aralığı olarak eklenen alan, yuva boş kalır
        const d2 = tanimdanDurum({ ...tanim, filtreler: [{ alan: "dava_sayisi", op: "gte", deger: 5 }] }, MUVEKKILLER);
        expect(d2.serit.filter(o => o.durum.alan === "dava_sayisi").map(o => [o.durum.kontrol, o.hizli]))
            .toEqual([["sayi_araligi", false], ["var_yok", true]]);
        expect(tanimOlustur(d2).filtreler).toEqual([{ alan: "dava_sayisi", op: "gte", deger: 5 }]);
    });

    it("seritiTemizle: yuvalar kendi sunumuyla boşa döner (arama dahil), eklenenler kalkar", () => {
        const d = tanimdanDurum({
            veri_kaynagi: "muvekkiller", kolonlar: ["name"], siralama: [],
            filtreler: [{ alan: "arama", op: "contains", deger: "x" }, { alan: "dava_sayisi", op: "eq", deger: 0 }, { alan: "name", op: "contains", deger: "y" }],
        }, MUVEKKILLER);
        const temiz = seritiTemizle(d.serit, MUVEKKILLER);
        expect(temiz.map(o => [o.durum.alan, o.durum.kontrol, o.sunum])).toEqual([
            ["arama", "metin_icerir", "arama"],
            ["dava_sayisi", "var_yok", "var_yok"],
            ["category", "coklu_secim", "cipler"],
            ["il", "coklu_secim", "varsayilan"],
            ["specialty", "coklu_secim", "varsayilan"],
            ["email", "bos_anahtari", "bos_anahtari"],
            ["mobile_phone", "bos_anahtari", "bos_anahtari"],
        ]);
        expect(seritFiltreleri(temiz)).toEqual([]);
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
