import { describe, expect, it } from "vitest";
import {
    BELGE_KUMELERI, BELGE_KUMESI_PARAM, FILTRE_KARARLAR, FILTRE_TUMU, VARSAYILAN_BELGE_KUMESI,
    belgeKumeSayilari, belgeKumesi, belgeKumesiCoz, belgeKumesiUygula,
    evrakFiltreCipleri, evrakFiltreUygula, evrakTurAnahtari,
} from "@/lib/evrakFiltresi";

const docs = [
    { id: 1, belge_turu_kodu: "DVDLKC______", belge_turu_adi: "Dava Dilekçesi" },
    { id: 2, belge_turu_kodu: "GEREKCELI-KRR_", belge_turu_adi: "Gerekçeli Karar" },
    { id: 3, belge_turu_kodu: "ISTINAFKRR", belge_turu_adi: "İstinaf Kararı" },
    { id: 4, belge_turu_kodu: "ARA-KRR", belge_turu_adi: "Ara Karar" },
    { id: 5, belge_turu_kodu: "DVDLKC", belge_turu_adi: "Dava Dilekçesi" },
    { id: 6, belge_turu_kodu: null, belge_turu_adi: null },
];

describe("evrakFiltresi", () => {
    it("padding'li ve ayraçlı kodları aynı türde toplar", () => {
        expect(evrakTurAnahtari(docs[0])).toBe(evrakTurAnahtari(docs[4]));
    });

    it("çipler: Tümü, Kararlar, sonra türler çoktan aza", () => {
        const cipler = evrakFiltreCipleri(docs);
        expect(cipler[0]).toEqual({ anahtar: FILTRE_TUMU, etiket: "Tümü", sayi: 6 });
        expect(cipler[1]).toEqual({ anahtar: FILTRE_KARARLAR, etiket: "Kararlar", sayi: 3 });
        expect(cipler[2]).toMatchObject({ etiket: "Dava Dilekçesi", sayi: 2 });
        expect(cipler.map(c => c.etiket)).toContain("Türü belirsiz");
        expect(cipler).toHaveLength(2 + 5);
    });

    it("karar yoksa Kararlar çipi basılmaz", () => {
        const cipler = evrakFiltreCipleri([docs[0]]);
        expect(cipler.map(c => c.anahtar)).not.toContain(FILTRE_KARARLAR);
    });

    it("süzme: Kararlar ara kararı da kapsar; tür anahtarı tek türü getirir", () => {
        expect(evrakFiltreUygula(docs, FILTRE_KARARLAR).map(d => d.id)).toEqual([2, 3, 4]);
        expect(evrakFiltreUygula(docs, evrakTurAnahtari(docs[0])).map(d => d.id)).toEqual([1, 5]);
        expect(evrakFiltreUygula(docs, FILTRE_TUMU)).toHaveLength(6);
    });
});

describe("belge kümeleri — Gelen · Taslak · Giden (G283)", () => {
    const belgeler = [
        { id: 1, yon: "GELEN", durum: "KESIN" },
        { id: 2, yon: "GIDEN", durum: "KESIN" },
        { id: 3, yon: "GIDEN", durum: "TASLAK" }, // taslak, yönü ne olursa olsun
        { id: 4, yon: "GELEN", durum: "TASLAK" },
        { id: 5 }, // eski yanıt: alan yok → GELEN/KESIN
        { id: 6, yon: "giden", durum: "kesin" }, // küçük harf tanınır
    ];

    it("küme belgenin yön + durumundan türer; eksik alan gelen sayılır", () => {
        expect(belgeler.map(belgeKumesi)).toEqual(["gelen", "giden", "taslak", "taslak", "gelen", "giden"]);
    });

    it("sayılar ve süzme tutarlı", () => {
        expect(belgeKumeSayilari(belgeler)).toEqual({ gelen: 2, taslak: 2, giden: 2 });
        expect(belgeKumesiUygula(belgeler, "giden").map(d => d.id)).toEqual([2, 6]);
        expect(belgeKumesiUygula(belgeler, "taslak").map(d => d.id)).toEqual([3, 4]);
        expect(belgeKumesiUygula([], "gelen")).toEqual([]);
    });

    it("URL parametresi: tanınan değer, aksi varsayılan 'gelen'", () => {
        expect(belgeKumesiCoz("giden")).toBe("giden");
        expect(belgeKumesiCoz("TASLAK")).toBe("taslak");
        expect(belgeKumesiCoz(null)).toBe(VARSAYILAN_BELGE_KUMESI);
        expect(belgeKumesiCoz("hepsi")).toBe("gelen");
        expect(BELGE_KUMELERI).toEqual(["gelen", "taslak", "giden"]);
        expect(BELGE_KUMESI_PARAM).toBe("belgeler");
    });

    it("tür çipleri alt filtreyle birlikte: küme süzgecinden sonra tür süzgeci", () => {
        const karma = [
            { id: 1, yon: "GIDEN", durum: "KESIN", belge_turu_kodu: "DVDLKC______", belge_turu_adi: "Dava Dilekçesi" },
            { id: 2, yon: "GELEN", durum: "KESIN", belge_turu_kodu: "DVDLKC______", belge_turu_adi: "Dava Dilekçesi" },
            { id: 3, yon: "GIDEN", durum: "KESIN", belge_turu_kodu: "ARA-KRR", belge_turu_adi: "Ara Karar" },
        ];
        const giden = belgeKumesiUygula(karma, "giden");
        expect(evrakFiltreCipleri(giden)[0]).toEqual({ anahtar: FILTRE_TUMU, etiket: "Tümü", sayi: 2 });
        expect(evrakFiltreUygula(giden, evrakTurAnahtari(karma[0])).map(d => d.id)).toEqual([1]);
    });
});
