// Rapor Oluşturucu'nun yerel durumu (G133 → G138 filtre şeridi). Sunucu sözleşmesi
// `RaporTanimi`'dir (lib/reports.ts); burada filtreler §4.3 kontrol durumu olarak tutulur
// ve `tanimOlustur` ile her zaman aynı JSON'a derlenir. Boş kontrol tanıma GİRMEZ.
import type { Filtre, KatalogVeriKaynagi, KontrolDurumu, RaporTanimi, Siralama, SiralamaYonu } from "@/lib/reports";
import { TANIM_LIMITLERI, bosKontrol, filtredenKontrol, kontroldenFiltre } from "@/lib/reports";

/** Şeritteki bir kontrol: hızlı filtre yuvası (kaynağın listesi) ya da "+ Başka alan" ile eklenen. */
export interface SeritOgesi {
    /** Yalnız React key — sunucuya GİTMEZ. */
    id: string;
    durum: KontrolDurumu;
    /** Tarih aralığında alan değiştirici seçenekleri (hızlı filtre `alan` + `alternatifler`); yoksa boş. */
    alanSecenekleri: string[];
    /** Kaynağın hızlı filtre yuvası: × ile silinmez, boşa döner. Eklenen alan: × şeritten kaldırır. */
    hizli: boolean;
}

export interface OlusturucuDurumu {
    veri_kaynagi: string;
    kolonlar: string[];
    serit: SeritOgesi[];
    siralama: Siralama[];
}

let sayac = 0;
export function yeniSatirId(): string {
    sayac += 1;
    return `f${sayac}`;
}

const kolonOf = (kaynak: KatalogVeriKaynagi, anahtar: string) => kaynak.kolonlar.find(k => k.anahtar === anahtar);

/** Kaynağın hızlı filtre yuvaları, boş kontrollerle (katalogda olmayan/filtrelenemeyen alan atlanır). */
function hizliYuvalar(kaynak: KatalogVeriKaynagi): SeritOgesi[] {
    const yuvalar: SeritOgesi[] = [];
    for (const hf of kaynak.hizli_filtreler) {
        const kolon = kolonOf(kaynak, hf.alan);
        if (!kolon || !kolon.filtrelenebilir) continue;
        const alternatifler = hf.alternatifler.filter(a => {
            const k = kolonOf(kaynak, a);
            return k !== undefined && k.filtrelenebilir && k.kontrol === "tarih_araligi";
        });
        yuvalar.push({
            id: yeniSatirId(),
            durum: bosKontrol(kolon),
            alanSecenekleri: kolon.kontrol === "tarih_araligi" && alternatifler.length > 0 ? [hf.alan, ...alternatifler] : [],
            hizli: true,
        });
    }
    return yuvalar;
}

/** Kaynak seçilince/değişince başlangıç durumu: varsayılan kolonlar, hızlı filtreler boş, sıralama boş. */
export function kaynakIcinBaslangic(kaynak: KatalogVeriKaynagi): OlusturucuDurumu {
    const gecerli = new Set(kaynak.kolonlar.map(k => k.anahtar));
    return {
        veri_kaynagi: kaynak.anahtar,
        kolonlar: kaynak.varsayilan_kolonlar.filter(k => gecerli.has(k)),
        serit: hizliYuvalar(kaynak),
        siralama: [],
    };
}

/**
 * Sunucu tanımı → oluşturucu durumu (şablon / koşu / asistan). Filtreler `filtredenKontrol`
 * ile çözülür; hızlı filtre yuvasına düşenler (alan yuva alanı ya da bir alternatifi, yuva boşken)
 * yuvayı doldurur, kalanlar "+ Başka alan" ile eklenmiş gibi görünür. Dolu öğeler TANIMDAKİ
 * SIRAYLA önce gelir, boş yuvalar arkasından — böylece `tanimOlustur` filtre sırasını korur
 * (şablon karşılaştırması ve gidiş-dönüş için şart). Çözülemeyen op gelişmiş çip.
 */
export function tanimdanDurum(tanim: RaporTanimi, kaynak: KatalogVeriKaynagi): OlusturucuDurumu {
    const bosYuvalar = hizliYuvalar(kaynak);
    const dolu: SeritOgesi[] = [];
    for (const f of tanim.filtreler) {
        const kolon = kolonOf(kaynak, f.alan);
        const durum = filtredenKontrol(f, kolon);
        const yuvaIdx = bosYuvalar.findIndex(y =>
            y.durum.alan === f.alan || y.alanSecenekleri.includes(f.alan),
        );
        if (yuvaIdx >= 0) {
            const [yuva] = bosYuvalar.splice(yuvaIdx, 1);
            // Alternatif alana çözülen tarih filtresi yuvanın alan değiştiricisini o alana çeker;
            // gelişmiş çipe düşen filtre yuvanın kontrolünü ezmez (yuva yeniden boş açılır).
            if (durum.kontrol === "gelismis") {
                dolu.push({ id: yeniSatirId(), durum, alanSecenekleri: [], hizli: false });
                bosYuvalar.push(yuva);
            } else {
                dolu.push({ ...yuva, durum });
            }
        } else {
            dolu.push({ id: yeniSatirId(), durum, alanSecenekleri: [], hizli: false });
        }
    }
    return {
        veri_kaynagi: tanim.veri_kaynagi,
        kolonlar: [...tanim.kolonlar],
        serit: [...dolu, ...bosYuvalar],
        siralama: tanim.siralama.map(s => ({ alan: s.alan, yon: s.yon })),
    };
}

/** Şeritten etkin filtreler (boş kontroller düşer), şerit sırasıyla. */
export function seritFiltreleri(serit: SeritOgesi[]): Filtre[] {
    const sonuc: Filtre[] = [];
    for (const o of serit) {
        const f = kontroldenFiltre(o.durum);
        if (f) sonuc.push(f);
    }
    return sonuc;
}

/** Yerel durum → sunucu gövdesi (`id`/yuva bilgisi düşer, `deger` yalnız taşıyan op'larda kalır). */
export function tanimOlustur(durum: OlusturucuDurumu): RaporTanimi {
    return {
        veri_kaynagi: durum.veri_kaynagi,
        kolonlar: [...durum.kolonlar],
        filtreler: seritFiltreleri(durum.serit),
        siralama: durum.siralama.map(s => ({ alan: s.alan, yon: s.yon })),
    };
}

/**
 * Başlıktan sıralama döngüsü (§4.1 madde 4): yok → artan → azalan → kaldır. En fazla
 * `siralama_max` alan; dördüncüde EN ESKİ düşer.
 */
export function siralamaDongusu(siralama: Siralama[], alan: string): Siralama[] {
    const i = siralama.findIndex(s => s.alan === alan);
    if (i < 0) {
        const yeni = [...siralama, { alan, yon: "asc" as SiralamaYonu }];
        return yeni.length > TANIM_LIMITLERI.siralama_max ? yeni.slice(yeni.length - TANIM_LIMITLERI.siralama_max) : yeni;
    }
    if (siralama[i].yon === "asc") return siralama.map((s, j) => (j === i ? { alan, yon: "desc" as SiralamaYonu } : s));
    return siralama.filter((_, j) => j !== i);
}
