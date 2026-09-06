// Rapor Oluşturucu'nun yerel durumu (G133). Sunucu sözleşmesi `RaporTanimi`'dir
// (lib/reports.ts); burada yalnız React anahtarı için filtre satırlarına `id` eklenir.
import type { Filtre, KatalogVeriKaynagi, RaporTanimi, Siralama } from "@/lib/reports";

export interface FiltreSatiri extends Filtre {
    /** Yalnız React key — sunucuya GİTMEZ. */
    id: string;
}

export interface OlusturucuDurumu {
    veri_kaynagi: string;
    kolonlar: string[];
    filtreler: FiltreSatiri[];
    siralama: Siralama[];
}

let sayac = 0;
export function yeniSatirId(): string {
    sayac += 1;
    return `f${sayac}`;
}

/** Kaynak seçilince/değişince başlangıç durumu: varsayılan kolonlar, filtre ve sıralama boş. */
export function kaynakIcinBaslangic(kaynak: KatalogVeriKaynagi): OlusturucuDurumu {
    const gecerli = new Set(kaynak.kolonlar.map(k => k.anahtar));
    return {
        veri_kaynagi: kaynak.anahtar,
        kolonlar: kaynak.varsayilan_kolonlar.filter(k => gecerli.has(k)),
        filtreler: [],
        siralama: [],
    };
}

/** Yerel durum → sunucu gövdesi (`id` düşer, `deger` yalnız taşıyan op'larda kalır). */
export function tanimOlustur(durum: OlusturucuDurumu): RaporTanimi {
    return {
        veri_kaynagi: durum.veri_kaynagi,
        kolonlar: [...durum.kolonlar],
        filtreler: durum.filtreler.map(({ alan, op, deger }) =>
            deger === undefined ? { alan, op } : { alan, op, deger },
        ),
        siralama: durum.siralama.map(s => ({ alan: s.alan, yon: s.yon })),
    };
}
