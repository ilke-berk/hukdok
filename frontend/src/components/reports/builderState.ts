// Rapor Oluşturucu'nun yerel durumu (G133 → G138 filtre şeridi). Sunucu sözleşmesi
// `RaporTanimi`'dir (lib/reports.ts); burada filtreler §4.3 kontrol durumu olarak tutulur
// ve `tanimOlustur` ile her zaman aynı JSON'a derlenir. Boş kontrol tanıma GİRMEZ.
import type {
    Filtre, HizliFiltreSunumu, KatalogVeriKaynagi, KontrolDurumu, RaporTanimi, Siralama, SiralamaYonu,
} from "@/lib/reports";
import { TANIM_LIMITLERI, bosKontrol, filtredenKontrol, kolonSecilebilirMi, kontroldenFiltre } from "@/lib/reports";

/** Şeritteki bir kontrol: hızlı filtre yuvası (kaynağın listesi) ya da "+ Başka alan" ile eklenen. */
export interface SeritOgesi {
    /** Yalnız React key — sunucuya GİTMEZ. */
    id: string;
    durum: KontrolDurumu;
    /** Tarih aralığında alan değiştirici seçenekleri (hızlı filtre `alan` + `alternatifler`); yoksa boş. */
    alanSecenekleri: string[];
    /** Kaynağın hızlı filtre yuvası: × ile silinmez, boşa döner. Eklenen alan: × şeritten kaldırır. */
    hizli: boolean;
    /** §5.2 sunum — kontrol bileşeni bununla seçilir (§5.3); eklenen alanda `varsayilan`. */
    sunum: HizliFiltreSunumu;
    /** §5.2 anahtar metni (`var_yok`/`bos_anahtari`: "Davası var", "E-postası yok"); yoksa kolon etiketi. */
    etiket: string | null;
}

/** "+ Başka alan" ile eklenen öğe (yuva değil, `varsayilan` sunum). */
export function eklenenOge(durum: KontrolDurumu): SeritOgesi {
    return { id: yeniSatirId(), durum, alanSecenekleri: [], hizli: false, sunum: "varsayilan", etiket: null };
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
        // Eski katalog cevabı (`sunum` yok) varsayılan sunumla açılır.
        const sunum: HizliFiltreSunumu = hf.sunum ?? "varsayilan";
        yuvalar.push({
            id: yeniSatirId(),
            durum: bosKontrol(kolon, sunum),
            alanSecenekleri: kolon.kontrol === "tarih_araligi" && alternatifler.length > 0 ? [hf.alan, ...alternatifler] : [],
            hizli: true,
            sunum,
            etiket: hf.etiket ?? null,
        });
    }
    return yuvalar;
}

/** Kaynak seçilince/değişince başlangıç durumu: varsayılan kolonlar, hızlı filtreler boş, sıralama boş. */
export function kaynakIcinBaslangic(kaynak: KatalogVeriKaynagi): OlusturucuDurumu {
    return {
        veri_kaynagi: kaynak.anahtar,
        // §5.2: `secilebilir=false` (sanal arama) varsayılan listeye sızsa da kolon olamaz; katalogda olmayan elenir.
        kolonlar: kaynak.varsayilan_kolonlar.filter(k => kolonSecilebilirMi(kolonOf(kaynak, k))),
        serit: hizliYuvalar(kaynak),
        siralama: [],
    };
}

/**
 * Çözülen kontrol yuvanın sunumuna oturuyor mu? (`var_yok`/`bos_anahtari` yuvası yalnız kendi türünü,
 * `arama`/`cipler`/`varsayilan` yuvası kolonun katalog kontrolünü alır; gelişmiş çip yuvayı ezmez.)
 */
function yuvayaUyarMi(durum: KontrolDurumu, yuva: SeritOgesi): boolean {
    if (durum.kontrol === "gelismis") return false;
    if (yuva.sunum === "var_yok") return durum.kontrol === "var_yok";
    if (yuva.sunum === "bos_anahtari") return durum.kontrol === "bos_anahtari";
    return durum.kontrol !== "var_yok" && durum.kontrol !== "bos_anahtari";
}

/**
 * Sunucu tanımı → oluşturucu durumu (şablon / koşu / asistan). Filtreler `filtredenKontrol`
 * ile çözülür (yuvanın `sunum`u ile — `dava_sayisi gte 1` var/yok anahtarına, `email is_null` boş
 * anahtarına, `arama contains` arama kutusuna, `in` içindeki `null` "(boş)" seçimine); hızlı filtre
 * yuvasına düşenler (alan yuva alanı ya da bir alternatifi, yuva boşken) yuvayı doldurur, kalanlar
 * "+ Başka alan" ile eklenmiş gibi görünür. Dolu öğeler TANIMDAKİ SIRAYLA önce gelir, boş yuvalar
 * arkasından — böylece `tanimOlustur` filtre sırasını korur (şablon karşılaştırması ve gidiş-dönüş
 * için şart). Çözülemeyen op gelişmiş çip; yuvaya oturmayan (ör. `dava_sayisi gte 5` var/yok yuvasında)
 * kolonun kendi kontrolüyle eklenen alan olur, yuva boş kalır.
 */
export function tanimdanDurum(tanim: RaporTanimi, kaynak: KatalogVeriKaynagi): OlusturucuDurumu {
    const bosYuvalar = hizliYuvalar(kaynak);
    const dolu: SeritOgesi[] = [];
    for (const f of tanim.filtreler) {
        const kolon = kolonOf(kaynak, f.alan);
        const yuvaIdx = bosYuvalar.findIndex(y =>
            y.durum.alan === f.alan || y.alanSecenekleri.includes(f.alan),
        );
        if (yuvaIdx >= 0) {
            const yuva = bosYuvalar[yuvaIdx];
            const durum = filtredenKontrol(f, kolon, yuva.sunum);
            // Alternatif alana çözülen tarih filtresi yuvanın alan değiştiricisini o alana çeker;
            // gelişmiş çipe/başka kontrole düşen filtre yuvanın kontrolünü ezmez (yuva boş kalır).
            bosYuvalar.splice(yuvaIdx, 1);
            if (yuvayaUyarMi(durum, yuva)) {
                dolu.push({ ...yuva, durum });
            } else {
                dolu.push(eklenenOge(filtredenKontrol(f, kolon)));
                bosYuvalar.push(yuva);
            }
        } else {
            dolu.push(eklenenOge(filtredenKontrol(f, kolon)));
        }
    }
    return {
        veri_kaynagi: tanim.veri_kaynagi,
        kolonlar: [...tanim.kolonlar],
        serit: [...dolu, ...bosYuvalar],
        siralama: tanim.siralama.map(s => ({ alan: s.alan, yon: s.yon })),
    };
}

/**
 * Şeridi boşaltır (G139 boş sonuç kısayolu; QuickFilters "Filtreleri temizle" ile aynı kural):
 * hızlı yuvalar kendi alanlarında boş kontrole döner, "+ Başka alan" ile eklenenler şeritten kalkar.
 */
export function seritiTemizle(serit: SeritOgesi[], kaynak: KatalogVeriKaynagi): SeritOgesi[] {
    const yeni: SeritOgesi[] = [];
    for (const o of serit) {
        if (!o.hizli) continue;
        const yuvaKolon = o.alanSecenekleri.length > 0 ? kolonOf(kaynak, o.alanSecenekleri[0]) : kolonOf(kaynak, o.durum.alan);
        if (yuvaKolon) yeni.push({ ...o, durum: bosKontrol(yuvaKolon, o.sunum) });
    }
    return yeni;
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
