// Rapor Oluşturucu'nun yerel durumu (G133 → G138 filtre şeridi). Sunucu sözleşmesi
// `RaporTanimi`'dir (lib/reports.ts); burada filtreler §4.3 kontrol durumu olarak tutulur
// ve `tanimOlustur` ile her zaman aynı JSON'a derlenir. Boş kontrol tanıma GİRMEZ.
import type {
    Filtre, Gruplama, HizliFiltreSunumu, KatalogVeriKaynagi, KontrolDurumu, Olcum, RaporTanimi, Siralama, SiralamaYonu,
    TarihKirilimi,
} from "@/lib/reports";
import {
    TANIM_LIMITLERI, bosKontrol, filtredenKontrol, kolonSecilebilirMi, kontrolDoluMu, kontroldenFiltre, olcumAnahtari,
} from "@/lib/reports";

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
    /** Özet modu (12.09): `olcumler` doluysa özet; boşken `tanimOlustur` iki alanı YAZMAZ (eski sözleşme). */
    gruplama: Gruplama[];
    olcumler: Olcum[];
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
        gruplama: [],
        olcumler: [],
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
 * anahtarına, `arama contains` arama kutusuna, `in` içindeki `null` "Boş" seçimine, tarih/sayı/metin
 * `is_null` kontrolün "Boş" çipine — §7.1, gelişmiş çip değil); hızlı filtre
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
        gruplama: (tanim.gruplama ?? []).map(g => (g.kirilim ? { alan: g.alan, kirilim: g.kirilim } : { alan: g.alan })),
        olcumler: (tanim.olcumler ?? []).map(o => (o.alan ? { islem: o.islem, alan: o.alan } : { islem: o.islem })),
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
    const tanim: RaporTanimi = {
        veri_kaynagi: durum.veri_kaynagi,
        kolonlar: [...durum.kolonlar],
        filtreler: seritFiltreleri(durum.serit),
        siralama: durum.siralama.map(s => ({ alan: s.alan, yon: s.yon })),
    };
    // Özet modu alanları yalnız doluyken (sunucu serileştirmesiyle birebir; liste görünümü gövdesi değişmez)
    if (durum.gruplama.length > 0) tanim.gruplama = durum.gruplama.map(g => ({ ...g }));
    if (durum.olcumler.length > 0) tanim.olcumler = durum.olcumler.map(o => ({ ...o }));
    return tanim;
}

// ---------------------------------------------------------------------------
// Özet modu yardımcıları (12.09): saf; gruplanabilirlik/uygunluk kararı çağıranın (şerit süzülmüş verir).
// Özet modu = `olcumler` dolu. Sıralama çıktı kolonlarına göre süzülür (motor 422 yedirmemek için).
// ---------------------------------------------------------------------------

/** Özet modunda sıralama yalnız gruplama alanı / ölçüm anahtarı; liste modunda ölçüm anahtarları düşer. */
function siralamayiUyarla(durum: OlusturucuDurumu): Siralama[] {
    if (durum.olcumler.length > 0) {
        const izinli = new Set([...durum.gruplama.map(g => g.alan), ...durum.olcumler.map(olcumAnahtari)]);
        return durum.siralama.filter(s => izinli.has(s.alan));
    }
    // Liste görünümüne dönüş: ölçüm anahtarları (`sayi`, `toplam:x`) kolon değildir — düşer
    return durum.siralama.filter(s => !s.alan.includes(":") && s.alan !== "sayi");
}

/** Özet modunu açar: ölçüm yoksa "Kayıt sayısı" eklenir; zaten açıksa AYNI nesne. */
export function ozetAc(durum: OlusturucuDurumu): OlusturucuDurumu {
    if (durum.olcumler.length > 0) return durum;
    const yeni = { ...durum, olcumler: [{ islem: "sayi" as const }] };
    return { ...yeni, siralama: siralamayiUyarla(yeni) };
}

/** Liste görünümüne döner: gruplama + ölçümler boşalır, ölçüm anahtarlı sıralama düşer; zaten kapalıysa AYNI nesne. */
export function ozetKapat(durum: OlusturucuDurumu): OlusturucuDurumu {
    if (durum.olcumler.length === 0 && durum.gruplama.length === 0) return durum;
    const yeni = { ...durum, gruplama: [], olcumler: [] };
    return { ...yeni, siralama: siralamayiUyarla(yeni) };
}

/** Gruplama ekler (özet modunu açar); aynı alan varsa ya da `gruplama_max` (3) doluysa AYNI nesne. */
export function gruplamaEkle(durum: OlusturucuDurumu, alan: string, kirilim?: TarihKirilimi | null): OlusturucuDurumu {
    if (durum.gruplama.some(g => g.alan === alan) || durum.gruplama.length >= TANIM_LIMITLERI.gruplama_max) return durum;
    const g: Gruplama = kirilim ? { alan, kirilim } : { alan };
    const yeni = ozetAc({ ...durum, gruplama: [...durum.gruplama, g] });
    return { ...yeni, siralama: siralamayiUyarla(yeni) };
}

/** Gruplamayı kaldırır (ölçümler kalır — gruplamasız özet = tek toplam satırı); yoksa AYNI nesne. */
export function gruplamaKaldir(durum: OlusturucuDurumu, alan: string): OlusturucuDurumu {
    if (!durum.gruplama.some(g => g.alan === alan)) return durum;
    const yeni = { ...durum, gruplama: durum.gruplama.filter(g => g.alan !== alan) };
    return { ...yeni, siralama: siralamayiUyarla(yeni) };
}

/** Tarih gruplamasının kırılımını değiştirir; alan yoksa ya da aynıysa AYNI nesne. */
export function kirilimDegistir(durum: OlusturucuDurumu, alan: string, kirilim: TarihKirilimi): OlusturucuDurumu {
    const g = durum.gruplama.find(x => x.alan === alan);
    if (!g || (g.kirilim ?? "gun") === kirilim) return durum;
    return { ...durum, gruplama: durum.gruplama.map(x => (x.alan === alan ? { alan, kirilim } : x)) };
}

/** Ölçüm ekler (özet modunu açar); aynı anahtar varsa ya da `olcum_max` (5) doluysa AYNI nesne. */
export function olcumEkle(durum: OlusturucuDurumu, olcum: Olcum): OlusturucuDurumu {
    const anahtar = olcumAnahtari(olcum);
    if (durum.olcumler.some(o => olcumAnahtari(o) === anahtar) || durum.olcumler.length >= TANIM_LIMITLERI.olcum_max) return durum;
    const yeni = { ...durum, olcumler: [...durum.olcumler, olcum.alan ? { islem: olcum.islem, alan: olcum.alan } : { islem: olcum.islem }] };
    return { ...yeni, siralama: siralamayiUyarla(yeni) };
}

/** Ölçümü kaldırır; SON ölçüm kalkınca özet kapanır (`ozetKapat`); yoksa AYNI nesne. */
export function olcumKaldir(durum: OlusturucuDurumu, anahtar: string): OlusturucuDurumu {
    if (!durum.olcumler.some(o => olcumAnahtari(o) === anahtar)) return durum;
    const kalan = durum.olcumler.filter(o => olcumAnahtari(o) !== anahtar);
    if (kalan.length === 0) return ozetKapat(durum);
    const yeni = { ...durum, olcumler: kalan };
    return { ...yeni, siralama: siralamayiUyarla(yeni) };
}

// ---------------------------------------------------------------------------
// G173 — tanım şeridi yardımcıları (TanimSeridi): saf, kataloğa bakmaz (seçilebilirlik/filtrelenebilirlik
// kararı çağıranın — şerit listeyi zaten süzülmüş verir). Mevcut imzalar değişmez.
// ---------------------------------------------------------------------------

/**
 * Kolon ekler: zaten seçili olanlar ve listede tekrar edenler atlanır, `kolon_max` (60) tavanı aşılmaz
 * (sığmayanlar sırayla düşer). Sıra = ekleme sırası (§2.1 "kolonlar sıralıdır"). Değişiklik yoksa AYNI nesne.
 */
export function kolonEkle(durum: OlusturucuDurumu, anahtarlar: readonly string[]): OlusturucuDurumu {
    const kolonlar = [...durum.kolonlar];
    const kume = new Set(kolonlar);
    for (const a of anahtarlar) {
        if (kolonlar.length >= TANIM_LIMITLERI.kolon_max) break;
        if (kume.has(a)) continue;
        kume.add(a);
        kolonlar.push(a);
    }
    return kolonlar.length === durum.kolonlar.length ? durum : { ...durum, kolonlar };
}

/** Kolonu çıkarır; SON kolon çıkarılmaz (tanım en az 1 kolon ister) — o durumda ve kolon yoksa AYNI nesne. */
export function kolonKaldir(durum: OlusturucuDurumu, anahtar: string): OlusturucuDurumu {
    if (durum.kolonlar.length <= 1 || !durum.kolonlar.includes(anahtar)) return durum;
    return { ...durum, kolonlar: durum.kolonlar.filter(k => k !== anahtar) };
}

/**
 * Şeride alan için boş kontrol ekler (`eklenenOge(bosKontrol(kolon))`, `hizli:false`). Aynı alanda BOŞ bir
 * öğe zaten varsa (boş hızlı yuva ya da doldurulmadan bırakılmış eklenen alan) yenisi eklenmez — şerit o
 * öğenin düzenleyicisini açar (`seritteBosOge`). `filtre_max` (20) dolu öğede dolunca eklenmez. Değişiklik
 * yoksa AYNI nesne.
 */
export function filtreEkle(durum: OlusturucuDurumu, kolon: Parameters<typeof bosKontrol>[0]): OlusturucuDurumu {
    if (seritteBosOge(durum.serit, kolon.anahtar)) return durum;
    if (seritFiltreleri(durum.serit).length >= TANIM_LIMITLERI.filtre_max) return durum;
    return { ...durum, serit: [...durum.serit, eklenenOge(bosKontrol(kolon))] };
}

/** Alanın şeritteki BOŞ öğesi (varsa) — `filtreEkle` sonrası açılacak düzenleyicinin hedefi. */
export function seritteBosOge(serit: readonly SeritOgesi[], alan: string): SeritOgesi | undefined {
    return serit.find(o => o.durum.alan === alan && !kontrolDoluMu(o.durum));
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
