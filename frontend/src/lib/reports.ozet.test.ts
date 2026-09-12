// Özet modu (12.09) — lib/reports: tanım geçerlilik kapısı (motor._ozeti_dogrula ikizi), etiketler, kanonik biçim.
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import {
    OP_BY_TIP, gruplamaEtiketi, kolonGruplanabilirMi, olcumAnahtari, olcumEtiketi, olcumUygunMu, ozetModu,
    ozetSiralamaAnahtarlari, tanimGecerliMi, tanimNormalize,
    type FiltreKontrolu, type KatalogKolon, type KatalogVeriKaynagi, type KolonTipi, type RaporTanimi,
} from "./reports";

const KONTROL: Record<KolonTipi, FiltreKontrolu> = {
    metin: "metin_icerir", liste: "coklu_secim", tarih: "tarih_araligi", sayi: "sayi_araligi", para: "sayi_araligi", mantik: "mantik",
};
type KolonSahtesi = Pick<KatalogKolon, "anahtar" | "etiket" | "tip"> & Partial<KatalogKolon>;
function kolon(k: KolonSahtesi): KatalogKolon {
    return {
        filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null, grup: "Kimlik",
        kontrol: KONTROL[k.tip], oplar: [...OP_BY_TIP[k.tip]], oneriler: null, oneri_kesik: false,
        secenek_kaynagi: null, secenek_etiketleri: null, secilebilir: true, ...k,
    };
}
const DAVALAR: KatalogVeriKaynagi = {
    anahtar: "davalar", etiket: "Davalar", aciklama: "", varsayilan_kolonlar: ["tracking_no"],
    kolonlar: [
        kolon({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" }),
        kolon({ anahtar: "status", etiket: "Durum", tip: "liste", secenekler: ["Derdest"] }),
        kolon({ anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih" }),
        kolon({ anahtar: "maddi_tazminat", etiket: "Maddi Tazminat", tip: "para" }),
        kolon({ anahtar: "muvekkil_adlari", etiket: "Müvekkiller", tip: "metin", turetilmis: true, siralanabilir: false }),
        kolon({ anahtar: "arama", etiket: "Ara", tip: "metin", secilebilir: false, siralanabilir: false }),
        kolon({ anahtar: "yeni_sunucu", etiket: "Sunucu der", tip: "metin", gruplanabilir: false }),
    ],
    hizli_filtreler: [], kolon_setleri: [],
};
const temel = (ek: Partial<RaporTanimi> = {}): RaporTanimi =>
    ({ veri_kaynagi: "davalar", kolonlar: ["tracking_no"], filtreler: [], siralama: [], ...ek });

describe("özet modu — geçerlilik kapısı", () => {
    it("gruplama + ölçüm geçerli; ölçümsüz gruplama, tekrar, tavan, uygun olmayan tip geçersiz", () => {
        expect(tanimGecerliMi(temel({ gruplama: [{ alan: "status" }], olcumler: [{ islem: "sayi" }] }), DAVALAR)).toBe(true);
        expect(tanimGecerliMi(temel({ olcumler: [{ islem: "toplam", alan: "maddi_tazminat" }] }), DAVALAR)).toBe(true);
        expect(tanimGecerliMi(temel({ gruplama: [{ alan: "status" }] }), DAVALAR)).toBe(false);
        expect(tanimGecerliMi(temel({ gruplama: [{ alan: "status" }, { alan: "status" }], olcumler: [{ islem: "sayi" }] }), DAVALAR)).toBe(false);
        expect(tanimGecerliMi(temel({ olcumler: [{ islem: "sayi" }, { islem: "sayi" }] }), DAVALAR)).toBe(false);
        expect(tanimGecerliMi(temel({ olcumler: [{ islem: "toplam", alan: "status" }] }), DAVALAR)).toBe(false);
        expect(tanimGecerliMi(temel({ olcumler: [{ islem: "toplam" }] }), DAVALAR)).toBe(false);
        expect(tanimGecerliMi(temel({ olcumler: [{ islem: "min", alan: "opening_date" }] }), DAVALAR)).toBe(true);
        const cok = ["tracking_no", "status", "opening_date", "maddi_tazminat"].map(alan => ({ alan }));
        expect(tanimGecerliMi(temel({ gruplama: cok, olcumler: [{ islem: "sayi" }] }), DAVALAR)).toBe(false);
    });

    it("gruplanamaz: türetilmiş/sıralanamaz, sanal arama, sunucu `gruplanabilir:false`; kırılım yalnız tarihte", () => {
        expect(kolonGruplanabilirMi(DAVALAR.kolonlar[0])).toBe(true);
        expect(kolonGruplanabilirMi(DAVALAR.kolonlar[4])).toBe(false);
        expect(kolonGruplanabilirMi(DAVALAR.kolonlar[5])).toBe(false);
        expect(kolonGruplanabilirMi(DAVALAR.kolonlar[6])).toBe(false);
        expect(kolonGruplanabilirMi(undefined)).toBe(false);
        expect(tanimGecerliMi(temel({ gruplama: [{ alan: "muvekkil_adlari" }], olcumler: [{ islem: "sayi" }] }), DAVALAR)).toBe(false);
        expect(tanimGecerliMi(temel({ gruplama: [{ alan: "status", kirilim: "ay" }], olcumler: [{ islem: "sayi" }] }), DAVALAR)).toBe(false);
        expect(tanimGecerliMi(temel({ gruplama: [{ alan: "opening_date", kirilim: "ay" }], olcumler: [{ islem: "sayi" }] }), DAVALAR)).toBe(true);
    });

    it("özet modunda sıralama yalnız gruplama alanı / ölçüm anahtarı; liste modunda kolon", () => {
        const ozet = temel({ gruplama: [{ alan: "status" }], olcumler: [{ islem: "sayi" }, { islem: "toplam", alan: "maddi_tazminat" }] });
        expect(ozetSiralamaAnahtarlari(ozet)).toEqual(["status", "sayi", "toplam:maddi_tazminat"]);
        expect(tanimGecerliMi({ ...ozet, siralama: [{ alan: "sayi", yon: "desc" }] }, DAVALAR)).toBe(true);
        expect(tanimGecerliMi({ ...ozet, siralama: [{ alan: "toplam:maddi_tazminat", yon: "asc" }] }, DAVALAR)).toBe(true);
        expect(tanimGecerliMi({ ...ozet, siralama: [{ alan: "tracking_no", yon: "asc" }] }, DAVALAR)).toBe(false);
        expect(tanimGecerliMi(temel({ siralama: [{ alan: "sayi", yon: "asc" }] }), DAVALAR)).toBe(false);
        expect(ozetModu(ozet)).toBe(true);
        expect(ozetModu(temel())).toBe(false);
        expect(ozetModu(temel({ olcumler: [] }))).toBe(false);
    });
});

describe("özet modu — etiketler ve kanonik biçim", () => {
    it("ölçüm anahtarı/etiketi ve gruplama etiketi motorla aynı", () => {
        expect(olcumAnahtari({ islem: "sayi" })).toBe("sayi");
        expect(olcumAnahtari({ islem: "toplam", alan: "maddi_tazminat" })).toBe("toplam:maddi_tazminat");
        expect(olcumEtiketi({ islem: "sayi" }, undefined)).toBe("Kayıt sayısı");
        expect(olcumEtiketi({ islem: "sayi", alan: "status" }, DAVALAR.kolonlar[1])).toBe("Durum sayısı");
        expect(olcumEtiketi({ islem: "toplam", alan: "maddi_tazminat" }, DAVALAR.kolonlar[3])).toBe("Toplam Maddi Tazminat");
        expect(olcumEtiketi({ islem: "ortalama", alan: "maddi_tazminat" }, DAVALAR.kolonlar[3])).toBe("Ortalama Maddi Tazminat");
        expect(olcumEtiketi({ islem: "min", alan: "x" }, undefined)).toBe("En küçük x");
        expect(olcumEtiketi({ islem: "max", alan: "opening_date" }, DAVALAR.kolonlar[2])).toBe("En büyük Açılış Tarihi");
        expect(gruplamaEtiketi({ alan: "opening_date", kirilim: "ay" }, DAVALAR.kolonlar[2])).toBe("Açılış Tarihi (ay)");
        expect(gruplamaEtiketi({ alan: "opening_date", kirilim: "yil" }, DAVALAR.kolonlar[2])).toBe("Açılış Tarihi (yıl)");
        expect(gruplamaEtiketi({ alan: "opening_date" }, DAVALAR.kolonlar[2])).toBe("Açılış Tarihi");
        expect(gruplamaEtiketi({ alan: "status", kirilim: "ay" }, DAVALAR.kolonlar[1])).toBe("Durum");
        expect(gruplamaEtiketi({ alan: "yok" }, undefined)).toBe("yok");
        expect(olcumUygunMu("toplam", DAVALAR.kolonlar[3])).toBe(true);
        expect(olcumUygunMu("toplam", DAVALAR.kolonlar[2])).toBe(false);
        expect(olcumUygunMu("sayi", DAVALAR.kolonlar[5])).toBe(false);
    });

    it("tanimNormalize: boş listeler düşer, kirilim/alan boşsa düşer, alan sırası sabit", () => {
        const a: RaporTanimi = { siralama: [], filtreler: [{ op: "eq", alan: "status", deger: "Derdest" }], kolonlar: ["tracking_no"], veri_kaynagi: "davalar", gruplama: [], olcumler: [] };
        expect(JSON.stringify(tanimNormalize(a))).toBe(JSON.stringify(temel({ filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }] })));
        const b = tanimNormalize(temel({ gruplama: [{ alan: "status", kirilim: null }], olcumler: [{ islem: "sayi", alan: null }] }));
        expect(b.gruplama).toEqual([{ alan: "status" }]);
        expect(b.olcumler).toEqual([{ islem: "sayi" }]);
        expect(Object.keys(b)).toEqual(["veri_kaynagi", "kolonlar", "filtreler", "siralama", "gruplama", "olcumler"]);
        expect(Object.keys(tanimNormalize(temel()))).toEqual(["veri_kaynagi", "kolonlar", "filtreler", "siralama"]);
    });
});
