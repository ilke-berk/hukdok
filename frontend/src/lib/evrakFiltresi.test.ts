import { describe, expect, it } from "vitest";
import {
    FILTRE_KARARLAR, FILTRE_TUMU, evrakFiltreCipleri, evrakFiltreUygula, evrakTurAnahtari,
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
