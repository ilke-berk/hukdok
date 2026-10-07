// ÖRNEK ADAPTÖRÜN denetimi — `/lexis` önizlemesinde "düzenle → yeniden denetle" döngüsü çalışsın diye.
// Gerçek denetim çekirdektedir (`lexis_rapor/yazici.py::dogrula`, `_dayanak_uyarilari`, `word.py`); bu dosya
// onun kurallarını ekranı sürecek kadar taklit eder ve entegrasyonda KALKAR (uyarılar sunucudan yapılı gelir).
import { ALINTI_ALT_SINIRI, BOS, alintiGeciyor, alintiUzunlugu, katla, kaynaktaOlmayanlar, tarihYaz, tutarYaz } from "@/lib/lexisMetin";
import {
  BEKLENEN_BELGELER,
  BELGE_TURU_ADLARI,
  GIRIS_KALIPLARI,
  ISKELET_BOLUMLERI,
  type BolumKodu,
  type DosyaGirdisi,
  type KararKaydi,
  type LexisTaslak,
  type LexisUyari,
  type RafKarariAyrinti,
  type UyariKodu,
  type UyariSeviyesi,
} from "@/types/lexis";

export interface DenetimGirdisi {
  taslak: LexisTaslak;
  dosya: DosyaGirdisi;
  /** Bakılan emsal raporların metinleri (emsalden taşınma denetimi), `taslak.emsaller` sırasıyla. */
  emsalMetinleri: string[];
  kararBankasi: KararKaydi[];
  /**
   * Taslağın yazıldığı kararların kaynak metni (karar kimliği → `kararKaynakMetni`; `taslak.kararlar`). Maddelerin dayanak alıntısı
   * dosya metninin yanında bunlarda da aranır; karardan yazılan özet paragrafı kendi kararına karşı denetlenir.
   * Metni alınamayan karar haritada yoktur: o kararın paragrafı denetlenmez (yanlış alarm verilmez).
   */
  kaynakMetinleri?: Record<number, string>;
}

/**
 * Bir kararın denetimde kaynak sayılan metni: künye satırı + karar metni. Künye de kaynaktır — modele giden istemde
 * kararın başlığı (mahkeme, esas / karar no, tarih) yazar; özet paragrafı numarayı ve tarihi oradan da alabilir.
 */
export function kararKaynakMetni(k: Pick<RafKarariAyrinti, "mahkeme" | "esas_no" | "karar_no" | "karar_tarihi" | "metin">): string {
  const kunye = [k.mahkeme, k.esas_no && `${k.esas_no} E.`, k.karar_no && `${k.karar_no} K.`, k.karar_tarihi && tarihYaz(k.karar_tarihi)].filter(Boolean).join(" · ");
  return `${kunye}\n${k.metin}`;
}

const MASKE_YER_TUTUCULARI = ["[SİGORTALI]", "[HASTA]", "[KİŞİ]", "[TC]"];

/** "onam formu yer almadığından", "raporu iletilmediği" — belgenin YOKLUĞU iddiası (içeriğin değil). */
const YOKLUK_KALIBI =
  /(form\S*|rapor\S*|belge\S*|kayıt\S*|kayd\S*|epikriz\S*|dosya\S*)\s+(?:\S+\s+){0,3}?(yer almadığ|iletilmediğ|sunulmadığ|ibraz edilmediğ|gönderilmediğ)/i;

const ATIF_KALIBI = /(\d{4}\/\d+)\s*E\.?\s*,?\s*(\d{4}\/\d+)\s*K/g;

/** Dosyanın modele giden metni: künye özeti + özet (olgu) bölümleri. Dayanak alıntısı burada aranır. */
export function dosyaMetni(taslak: LexisTaslak, dosya: DosyaGirdisi): string {
  const parcalar: string[] = [];
  for (const deger of [dosya.mahkeme, dosya.esas_no, dosya.hasar_no, dosya.uzmanlik, dosya.hastane]) {
    if (deger) parcalar.push(deger);
  }
  for (const satirlar of Object.values(taslak.etiketli)) {
    for (const s of satirlar ?? []) if (s.deger) parcalar.push(`${s.etiket}: ${s.deger}`);
  }
  for (const paragraflar of Object.values(taslak.ozet)) {
    for (const p of paragraflar ?? []) parcalar.push(p.metin);
  }
  return parcalar.join("\n");
}

export function denetle({ taslak, dosya, emsalMetinleri, kararBankasi, kaynakMetinleri = {} }: DenetimGirdisi): LexisUyari[] {
  const uyarilar: LexisUyari[] = [];
  const ekle = (
    kod: UyariKodu,
    seviye: UyariSeviyesi,
    metin: string,
    yer: { bolum?: BolumKodu | null; madde?: number | null; alan?: string | null } = {},
  ) => {
    const bolum = yer.bolum ?? null;
    const madde = yer.madde ?? null;
    const alan = yer.alan ?? null;
    uyarilar.push({ id: `${kod}:${bolum ?? ""}:${madde ?? ""}:${alan ?? ""}:${uyarilar.length}`, kod, seviye, bolum, madde, alan, metin });
  };

  // 1. Dosya girdisi: eksik belge, kart ↔ belge çelişkisi
  for (const tur of BEKLENEN_BELGELER) {
    if (!dosya.belgeler.some((b) => b.tur === tur)) {
      ekle("EKSIK_BELGE", "UYARI", `Dava kartında belge yok: ${BELGE_TURU_ADLARI[tur]}`);
    }
  }
  for (const c of dosya.celiskiler) {
    ekle("KART_BELGE_CELISKISI", "UYARI", `${c.etiket}: kartta "${c.kart}", belgede "${c.belge}"`, { bolum: "hasar", alan: c.alan });
  }

  // 2. Bölümler: boş zorunlu alan, boş bölüm, doldurulmamış yer, maske kalıntısı
  for (const tanim of ISKELET_BOLUMLERI[taslak.iskelet]) {
    if (tanim.tur === "ETIKETLI") {
      for (const s of taslak.etiketli[tanim.kod] ?? []) {
        if (s.zorunlu && !s.deger?.trim()) {
          ekle("ALAN_BOS", "UYARI", `Alan boş: ${s.etiket}`, { bolum: tanim.kod, alan: s.alan });
        }
      }
    } else if (tanim.tur === "OZET") {
      const paragraflar = (taslak.ozet[tanim.kod] ?? []).filter((p) => p.metin.trim());
      if (paragraflar.length === 0) ekle("BOLUM_BOS", "UYARI", `Bölüm boş: ${tanim.baslik}`, { bolum: tanim.kod });
      paragraflar.forEach((p, i) => {
        metinDenetimi(p.metin, tanim.kod, null);
        // Karardan yazılan paragraf: alıntısı ve içindeki tutar / tarih / numara kaynak kararda geçmelidir.
        const kaynak = p.kaynak_karar_id != null ? kaynakMetinleri[p.kaynak_karar_id] : undefined;
        if (kaynak === undefined) return;
        const yer = { bolum: tanim.kod };
        const no = `${tanim.baslik}, paragraf ${i + 1}`;
        const alinti = p.dayanak_alinti?.trim() ?? "";
        if (alinti === "") ekle("DAYANAKSIZ", "UYARI", `${no}: dayanak alıntısı yok`, yer);
        else if (alintiUzunlugu(alinti) < ALINTI_ALT_SINIRI) ekle("ALINTI_KISA", "UYARI", `${no}: dayanak alıntısı çok kısa`, yer);
        else if (!alintiGeciyor(kaynak, alinti)) ekle("ALINTI_BULUNAMADI", "HATA", `${no}: dayanak alıntısı kaynak kararda bulunamadı`, yer);
        for (const olgu of kaynaktaOlmayanlar(p.metin, kaynak)) {
          ekle("OLGU_KAYNAKTA_YOK", "UYARI", `${no}: kaynak kararda geçmiyor: ${olgu}`, yer);
        }
      });
    }
  }

  function metinDenetimi(metin: string, bolum: BolumKodu, madde: number | null) {
    if (metin.includes(BOS)) ekle("DOLDURULMAMIS", "UYARI", `Metinde doldurulmamış yer var (${BOS})`, { bolum, madde });
    if (MASKE_YER_TUTUCULARI.some((y) => metin.includes(y))) {
      ekle("MASKE_KALINTISI", "HATA", "Metinde maske yer tutucusu var", { bolum, madde });
    }
  }

  // 3. Değerlendirme: giriş kalıbı, dayanak kuralı (K13), atıf doğrulaması
  const deg = taslak.degerlendirme;
  if (deg) {
    // Dayanak dosyanın metninde ya da taslağın yazıldığı kararlarda aranır (çekirdekte kararlar dosyanın
    // `yargi_sureci` olgusudur — `servis/yazim.py`).
    const hedef = [dosyaMetni(taslak, dosya), ...Object.values(kaynakMetinleri)].join("\n");
    const hedefKatli = katla(hedef);
    if (!katla(deg.giris).startsWith(GIRIS_KALIPLARI[taslak.iskelet])) {
      ekle("GIRIS_KALIBI", "UYARI", "Giriş cümlesi kalıba uymuyor", { bolum: "degerlendirme" });
    }
    const son = deg.maddeler.length;
    if (son === 0 || deg.maddeler[son - 1].tur !== "KALIP") {
      ekle("KALIP_YERI", "UYARI", "Son madde muallak cümlesi değil", { bolum: "degerlendirme", madde: son || null });
    }
    deg.maddeler.forEach((m, i) => {
      const n = i + 1;
      const yer = { bolum: "degerlendirme" as const, madde: n };
      metinDenetimi(m.metin, "degerlendirme", n);
      if (m.tur === "KALIP") {
        if (n !== son) ekle("KALIP_YERI", "UYARI", `Madde ${n}: KALIP türü yalnız son (muallak) maddede kullanılabilir`, yer);
        return;
      }
      const alinti = m.dayanak_alinti?.trim() ?? "";
      const yokluk = YOKLUK_KALIBI.test(m.metin);
      const dogrulandi = alinti !== "" && alintiUzunlugu(alinti) >= ALINTI_ALT_SINIRI && alintiGeciyor(hedef, alinti);
      if (alinti === "") {
        ekle("DAYANAKSIZ", "HATA", `Madde ${n} dayanaksız: alıntı yok`, yer);
      } else if (alintiUzunlugu(alinti) < ALINTI_ALT_SINIRI) {
        ekle("ALINTI_KISA", "UYARI", `Madde ${n}: dayanak alıntısı çok kısa`, yer);
      } else if (!dogrulandi) {
        const emsalSirasi = emsalMetinleri.findIndex((metin) => alintiGeciyor(metin, alinti));
        if (emsalSirasi >= 0) {
          ekle("EMSALDEN_TASINMA", "HATA", `Madde ${n}: dayanak alıntısı dosyada değil, emsal ${emsalSirasi + 1} raporunda geçiyor`, yer);
        } else {
          ekle("ALINTI_BULUNAMADI", "HATA", `Madde ${n}: dayanak alıntısı dosyada bulunamadı`, yer);
        }
      }
      // Yokluk iddiası alıntıyla doğrulanamaz; dosya metni yokluğu açıkça söylüyorsa (doğrulanmış alıntı da
      // yokluk bildiriyorsa) geçer.
      if (yokluk && !(dogrulandi && YOKLUK_KALIBI.test(alinti))) {
        ekle("BELGE_YOKLUGU", "UYARI", `Madde ${n}: dosyada bir belgenin bulunmadığı ileri sürülüyor; belge listesinden bakılmalı`, yer);
      }
      for (const atif of m.metin.matchAll(ATIF_KALIBI)) {
        const [, esas, karar] = atif;
        const bankada = kararBankasi.some((k) => k.esas_no === esas && k.karar_no === karar);
        const dosyada = hedefKatli.includes(katla(esas)) && hedefKatli.includes(katla(karar));
        if (!bankada && !dosyada) {
          ekle("ATIF_DOGRULANAMADI", "HATA", `Madde ${n}: doğrulanamayan atıf ${esas} E., ${karar} K.`, yer);
        }
      }
    });
  }

  // 4. Muallak (K11): dayanak yoksa uyarı; tutar talebi ve teminat limitini aşamaz
  if (taslak.muallak) {
    const maddi = taslak.muallak_maddi ?? taslak.muallak.maddi;
    const manevi = taslak.muallak_manevi ?? taslak.muallak.manevi;
    if (taslak.muallak.dayanak === "YOK" && maddi === null && manevi === null) {
      ekle("MUALLAK_DAYANAK_YOK", "UYARI", "Muallak dayanağı yok: kriter tablosu ve benzer emsal bulunamadı", { bolum: "degerlendirme" });
    }
    const sinir = (ad: string, tutar: number | null, talep: number | null) => {
      if (tutar !== null && talep !== null && tutar > talep) {
        ekle("MUALLAK_TALEBI_ASIYOR", "HATA", `Muallak ${ad} talebi aşıyor: ${tutarYaz(tutar)} > ${tutarYaz(talep)}`, { bolum: "degerlendirme" });
      }
    };
    sinir("maddi", maddi, dosya.talep_maddi);
    sinir("manevi", manevi, dosya.talep_manevi);
    const toplam = (maddi ?? 0) + (manevi ?? 0);
    if (dosya.teminat_limiti !== null && toplam > dosya.teminat_limiti) {
      ekle("MUALLAK_LIMITI_ASIYOR", "HATA", `Muallak toplamı teminat limitini aşıyor: ${tutarYaz(toplam)} > ${tutarYaz(dosya.teminat_limiti)}`, {
        bolum: "degerlendirme",
      });
    }
  }

  return uyarilar;
}
