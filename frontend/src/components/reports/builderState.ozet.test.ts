// builderState özet modu (12.09) — gruplama/ölçüm yardımcıları saf; `tanimOlustur` boş listeleri YAZMAZ.
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import { OP_BY_TIP, TANIM_LIMITLERI, type FiltreKontrolu, type KatalogKolon, type KatalogVeriKaynagi, type KolonTipi } from "@/lib/reports";
import {
    gruplamaEkle, gruplamaKaldir, kaynakIcinBaslangic, kirilimDegistir, olcumEkle, olcumKaldir, ozetAc, ozetKapat,
    tanimOlustur, tanimdanDurum,
} from "./builderState";

const KONTROL: Record<KolonTipi, FiltreKontrolu> = {
    metin: "metin_icerir", liste: "coklu_secim", tarih: "tarih_araligi", sayi: "sayi_araligi", para: "sayi_araligi", mantik: "mantik",
};
function kolon(k: Pick<KatalogKolon, "anahtar" | "etiket" | "tip"> & Partial<KatalogKolon>): KatalogKolon {
    return {
        filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null, grup: "Kimlik", kontrol: KONTROL[k.tip],
        oplar: [...OP_BY_TIP[k.tip]], oneriler: null, oneri_kesik: false, secenek_kaynagi: null, secenek_etiketleri: null,
        secilebilir: true, ...k,
    };
}
const DAVALAR: KatalogVeriKaynagi = {
    anahtar: "davalar", etiket: "Davalar", aciklama: "", varsayilan_kolonlar: ["tracking_no", "subject"],
    kolonlar: [
        kolon({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" }),
        kolon({ anahtar: "subject", etiket: "Konu", tip: "metin" }),
        kolon({ anahtar: "status", etiket: "Durum", tip: "liste", secenekler: ["Derdest"] }),
        kolon({ anahtar: "opening_date", etiket: "Açılış", tip: "tarih" }),
        kolon({ anahtar: "maddi_tazminat", etiket: "Maddi", tip: "para" }),
    ],
    hizli_filtreler: [], kolon_setleri: [],
};

describe("builderState — özet modu", () => {
    it("başlangıç boş; tanimOlustur boş listeleri yazmaz; dolu listeler aynen gider", () => {
        const d = kaynakIcinBaslangic(DAVALAR);
        expect(d.gruplama).toEqual([]);
        expect(d.olcumler).toEqual([]);
        expect(tanimOlustur(d)).toEqual({ veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [] });
        const o = gruplamaEkle(d, "status");
        expect(tanimOlustur(o)).toEqual({
            veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [],
            gruplama: [{ alan: "status" }], olcumler: [{ islem: "sayi" }],
        });
    });

    it("gruplamaEkle özet modunu açar (Kayıt sayısı), tekrar/tavan AYNI nesne; kırılım taşınır ve değişir", () => {
        const d = kaynakIcinBaslangic(DAVALAR);
        const a = gruplamaEkle(d, "opening_date", "ay");
        expect(a.gruplama).toEqual([{ alan: "opening_date", kirilim: "ay" }]);
        expect(a.olcumler).toEqual([{ islem: "sayi" }]);
        expect(gruplamaEkle(a, "opening_date", "yil")).toBe(a);
        const b = kirilimDegistir(a, "opening_date", "yil");
        expect(b.gruplama).toEqual([{ alan: "opening_date", kirilim: "yil" }]);
        expect(kirilimDegistir(b, "opening_date", "yil")).toBe(b);
        expect(kirilimDegistir(b, "yok", "gun")).toBe(b);
        let c = b;
        for (const alan of ["status", "tracking_no", "subject"]) c = gruplamaEkle(c, alan);
        expect(c.gruplama).toHaveLength(TANIM_LIMITLERI.gruplama_max);
        expect(c.gruplama.map(g => g.alan)).toEqual(["opening_date", "status", "tracking_no"]);
    });

    it("olcumEkle/olcumKaldir: tekrar ve tavan; son ölçüm kalkınca liste görünümü (gruplama da boşalır)", () => {
        const d = ozetAc(kaynakIcinBaslangic(DAVALAR));
        expect(d.olcumler).toEqual([{ islem: "sayi" }]);
        expect(ozetAc(d)).toBe(d);
        const a = olcumEkle(d, { islem: "toplam", alan: "maddi_tazminat" });
        expect(a.olcumler).toEqual([{ islem: "sayi" }, { islem: "toplam", alan: "maddi_tazminat" }]);
        expect(olcumEkle(a, { islem: "toplam", alan: "maddi_tazminat" })).toBe(a);
        expect(olcumEkle(a, { islem: "sayi", alan: null })).toBe(a);
        let b = a;
        for (const islem of ["ortalama", "min", "max"] as const) b = olcumEkle(b, { islem, alan: "maddi_tazminat" });
        expect(b.olcumler).toHaveLength(TANIM_LIMITLERI.olcum_max);
        expect(olcumEkle(b, { islem: "min", alan: "opening_date" })).toBe(b);
        const g = gruplamaEkle(a, "status");
        const kalan = olcumKaldir(g, "toplam:maddi_tazminat");
        expect(kalan.olcumler).toEqual([{ islem: "sayi" }]);
        expect(kalan.gruplama).toEqual([{ alan: "status" }]);
        const liste = olcumKaldir(kalan, "sayi");
        expect(liste.olcumler).toEqual([]);
        expect(liste.gruplama).toEqual([]);
        expect(olcumKaldir(liste, "sayi")).toBe(liste);
        expect(ozetKapat(liste)).toBe(liste);
    });

    it("sıralama çıktı kolonlarına göre süzülür: özete girerken kolon sıralaması düşer, çıkarken ölçüm anahtarı düşer", () => {
        const d = { ...kaynakIcinBaslangic(DAVALAR), siralama: [{ alan: "tracking_no", yon: "asc" as const }] };
        const o = gruplamaEkle(d, "status");
        expect(o.siralama).toEqual([]);
        const s = { ...o, siralama: [{ alan: "sayi", yon: "desc" as const }, { alan: "status", yon: "asc" as const }] };
        expect(gruplamaKaldir(s, "status").siralama).toEqual([{ alan: "sayi", yon: "desc" }]);
        expect(gruplamaKaldir(s, "yok")).toBe(s);
        expect(ozetKapat(s).siralama).toEqual([{ alan: "status", yon: "asc" }]);
        expect(olcumKaldir(s, "sayi").siralama).toEqual([{ alan: "status", yon: "asc" }]);
    });

    it("tanimdanDurum sunucu tanımının gruplama/ölçümlerini taşır; eski tanım (alan yok) boş listelerle", () => {
        const d = tanimdanDurum({
            veri_kaynagi: "davalar", kolonlar: ["tracking_no"], filtreler: [], siralama: [{ alan: "sayi", yon: "desc" }],
            gruplama: [{ alan: "opening_date", kirilim: "ay" }, { alan: "status", kirilim: null }],
            olcumler: [{ islem: "sayi" }, { islem: "toplam", alan: "maddi_tazminat" }],
        }, DAVALAR);
        expect(d.gruplama).toEqual([{ alan: "opening_date", kirilim: "ay" }, { alan: "status" }]);
        expect(d.olcumler).toEqual([{ islem: "sayi" }, { islem: "toplam", alan: "maddi_tazminat" }]);
        expect(d.siralama).toEqual([{ alan: "sayi", yon: "desc" }]);
        const eski = tanimdanDurum({ veri_kaynagi: "davalar", kolonlar: ["tracking_no"], filtreler: [], siralama: [] }, DAVALAR);
        expect(eski.gruplama).toEqual([]);
        expect(eski.olcumler).toEqual([]);
    });
});
