// reportsChat özet modu (12.09) — okunur tanım ayrıntısı gruplama/ölçüm satırları, özet sayaçları, tanım eşitliği.
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import { OP_BY_TIP, type FiltreKontrolu, type Katalog, type KatalogKolon, type KolonTipi, type RaporTanimi } from "@/lib/reports";
import { tanimAyni, tanimAyrintisi, tanimOzeti } from "./reportsChat";

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
const KATALOG: Katalog = {
    veri_kaynaklari: [{
        anahtar: "davalar", etiket: "Davalar", aciklama: "", varsayilan_kolonlar: ["tracking_no"],
        kolonlar: [
            kolon({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" }),
            kolon({ anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih" }),
            kolon({ anahtar: "responsible_lawyer_name", etiket: "Sorumlu Avukat", tip: "metin" }),
            kolon({ anahtar: "maddi_tazminat", etiket: "Maddi Tazminat", tip: "para" }),
        ],
        hizli_filtreler: [], kolon_setleri: [],
    }],
    limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 },
};
const OZET: RaporTanimi = {
    veri_kaynagi: "davalar", kolonlar: ["tracking_no"], filtreler: [{ alan: "opening_date", op: "gte", deger: "2025-01-01" }],
    siralama: [{ alan: "toplam:maddi_tazminat", yon: "desc" }, { alan: "opening_date", yon: "asc" }],
    gruplama: [{ alan: "opening_date", kirilim: "ay" }, { alan: "responsible_lawyer_name" }],
    olcumler: [{ islem: "sayi" }, { islem: "toplam", alan: "maddi_tazminat" }],
};

describe("reportsChat — özet modu", () => {
    it("tanimAyrintisi: gruplama kırılımlı, ölçümler etiketli, sıralama ölçüm/gruplama etiketiyle", () => {
        const a = tanimAyrintisi(OZET, KATALOG);
        expect(a.gruplama).toEqual(["Açılış Tarihi (ay)", "Sorumlu Avukat"]);
        expect(a.olcumler).toEqual(["Kayıt sayısı", "Toplam Maddi Tazminat"]);
        expect(a.siralama).toEqual(["Toplam Maddi Tazminat ↓", "Açılış Tarihi (ay) ↑"]);
        expect(a.filtreler).toEqual(["Açılış Tarihi · ≥ (en az) · 01.01.2025"]);
        const liste = tanimAyrintisi({ veri_kaynagi: "davalar", kolonlar: ["tracking_no"], filtreler: [], siralama: [{ alan: "opening_date", yon: "desc" }] }, KATALOG);
        expect(liste.gruplama).toEqual([]);
        expect(liste.olcumler).toEqual([]);
        expect(liste.siralama).toEqual(["Açılış Tarihi ↓"]);
        expect(tanimAyrintisi(OZET, null).olcumler).toEqual(["Kayıt sayısı", "Toplam maddi_tazminat"]);
    });

    it("tanimOzeti özet sayaçları", () => {
        expect(tanimOzeti(OZET)).toEqual({ kaynak: "davalar", kolon: 1, filtre: 1, siralama: 2, gruplama: 2, olcum: 2, ozet: true });
        expect(tanimOzeti({ veri_kaynagi: "davalar", kolonlar: ["a", "b"], filtreler: [], siralama: [] }))
            .toEqual({ kaynak: "davalar", kolon: 2, filtre: 0, siralama: 0, gruplama: 0, olcum: 0, ozet: false });
    });

    it("tanimAyni: boş/eksik gruplama-ölçüm listeleri eşdeğer; dolu listeler karşılaştırılır", () => {
        const liste: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["tracking_no"], filtreler: [], siralama: [] };
        expect(tanimAyni(liste, { ...liste, gruplama: [], olcumler: [] })).toBe(true);
        expect(tanimAyni(liste, { ...liste, olcumler: [{ islem: "sayi" }] })).toBe(false);
        expect(tanimAyni(OZET, JSON.parse(JSON.stringify(OZET)))).toBe(true);
        expect(tanimAyni(OZET, { ...OZET, gruplama: [{ alan: "opening_date", kirilim: "yil" }, { alan: "responsible_lawyer_name" }] })).toBe(false);
        expect(tanimAyni(OZET, { ...OZET, olcumler: [{ islem: "sayi" }] })).toBe(false);
        expect(tanimAyni(OZET, { ...OZET, gruplama: [{ alan: "opening_date", kirilim: "ay" }, { alan: "responsible_lawyer_name", kirilim: null }] })).toBe(true);
    });
});
