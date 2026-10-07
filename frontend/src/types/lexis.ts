// Lexis rapor aracı sözleşmesi — `/lexis` önizleme sayfası (04.10.2026). İstemci: `lib/lexisApi.ts`.
//
// İki katman:
// 1. ÇEKİRDEK tipleri: ayrı depodaki `lexis-rapor` paketinin veri sınıflarından OKUNARAK yazıldı
//    (`lexis_rapor/model.py`, `taslak.py`, `yazici.py`, `kutuphane.py`, `bag.py`, `cikarim.py`; 04.10 hâli).
//    Alan adları Python adlarıyla birebir (Türkçe ASCII snake_case), tarih ISO `yyyy-mm-dd` metni, tutar TL
//    `number`. Çekirdek değişirse burası da değişir.
// 2. ARAYÜZ tipleri ("çekirdekte yok" notlu): çekirdeğin henüz vermediği, ekranın ihtiyaç duyduğu şekiller.
//    Entegrasyon ucu bunları üretmek zorundadır; bugün yalnız örnek adaptör (`lib/lexisOrnekVeri.ts`) üretir.

// ---------------------------------------------------------------------------------------------
// Çekirdek: künye sabitleri
// ---------------------------------------------------------------------------------------------

/** `alanlar.py` şirket kodları. */
export type LexisSirket = "AK" | "ANADOLU" | "AXA" | "NIPPON" | "QUICK" | "EUREKO";
export type RaporTuru = "ANA" | "EK";
/** `iskelet.py` — `ESKI` (2018-2019 AXA) ve `BILINMEYEN` yalnız okunan eski raporlarda görülür. */
export type Iskelet = "ANADOLU" | "ALTILI" | "KISA" | "EK" | "ESKI" | "BILINMEYEN";
/** Yeni rapor yazılabilen iskeletler. */
export type YazilabilirIskelet = "ANADOLU" | "ALTILI" | "KISA" | "EK";

/** `RaporOkuma.bolumler` anahtarları (`iskelet.py::BOLUM_ANAHTARLARI` + `kunye`, `dipnotlar`). */
export type BolumKodu =
  | "kunye"
  | "hasar"
  | "hastane"
  | "sulh_muallak"
  | "iddia"
  | "beyan"
  | "police"
  | "yargi_sureci"
  | "uzman_gorusu"
  | "ek_inceleme"
  | "degerlendirme"
  | "giris"
  | "ekler"
  | "dipnotlar";

// ---------------------------------------------------------------------------------------------
// Çekirdek: okuyucu (`model.py`)
// ---------------------------------------------------------------------------------------------

/** Rapor metninde esas ve karar numarasıyla anılan yargı kararı. */
export interface Karar {
  merci: string | null;
  esas_no: string;
  karar_no: string;
  tarih: string | null;
  /** true: emsal karar · false: raporun kendi dosyası · null: belirlenemedi */
  emsal: boolean | null;
}

/** `RaporOkuma.tarihler` anahtarları (`alanlar.py`). */
export type TarihAnahtari =
  | "tibbi_mudahale"
  | "talep"
  | "sigortaya_ihbar"
  | "hekim_ogrenme"
  | "dava"
  | "arabuluculuk"
  | "idari_basvuru";

/** Bir rapor dosyasından belirlenimci yolla çıkan her şey. Kütüphanede yalnız MASKELİ hâli durur. */
export interface RaporOkuma {
  dosya: string;
  sha256: string;
  bicim: string;
  sirket: LexisSirket | null;
  rapor_turu: RaporTuru;
  iskelet: Iskelet;
  rapor_tarihi: string | null;
  rapor_no: string | null;
  hasar_no: string | null;
  hukuk_no: string | null;
  sigortali: string | null;
  uzmanlik: string | null;
  magdur: string | null;
  hastane: string | null;
  police_no: string | null;
  police_baslangic: string | null;
  police_bitis: string | null;
  teminat_limiti: number | null;
  mahkeme: string | null;
  esas_no: string | null;
  tarihler: Partial<Record<TarihAnahtari, string>>;
  talep_maddi: number | null;
  talep_manevi: number | null;
  talep_birlesik: number | null;
  muallak_maddi: number | null;
  muallak_manevi: number | null;
  muallak_cumlesi: string | null;
  mesleki_hata: string | null;
  mesleki_hata_sonucu: string | null;
  sulh_uygunluk: string | null;
  kararlar: Karar[];
  kurullar: string[];
  /** Bölüm kodu → metin (satırlar `\n` ile ayrılır). */
  bolumler: Partial<Record<BolumKodu, string>>;
  uyarilar: string[];
}

// ---------------------------------------------------------------------------------------------
// Çekirdek: etiket çıkarımı (`cikarim.py`)
// ---------------------------------------------------------------------------------------------

export type ZararKisi = "BEBEK" | "COCUK" | "YETISKIN" | "BELIRSIZ";
export type YargiYolu = "IDARE" | "TUKETICI" | "ASLIYE_HUKUK" | "CEZA" | "ARABULUCULUK" | "DAVA_YOK" | "DIGER";
export type KurumTuru = "KAMU" | "OZEL" | "BELIRSIZ";
export type KusurTespiti = "HATA_YOK" | "KOMPLIKASYON" | "KOMPLIKASYON_YONETIMI" | "HATA_VAR" | "BELIRSIZ";
export type RiskDuzeyi = "DUSUK" | "RISKLI" | "BELIRSIZ";
export type Teminat = "ICINDE" | "DISINDA" | "BELIRSIZ";
export type Rucu = "UYGUN" | "UYGUN_DEGIL" | "IHTIMAL_VAR" | "DEGINILMEMIS";
export type MuallakDayanagi = "KARAR" | "BILIRKISI" | "UZMAN" | "EMSAL" | "TALEP" | "YOK";

export interface RaporEtiketleri {
  uzmanlik: string | null;
  tibbi_islem: string | null;
  tibbi_surec: string[];
  tibbi_olay: string[];
  iddia_edilen_kusur: string[];
  hastada_olusan_zarar: string[];
  uygulanan_yontem: string[];
  zarar_kisi: ZararKisi;
  yargi_yolu: YargiYolu;
  kurum_turu: KurumTuru;
  kusur_tespiti: KusurTespiti;
  risk_duzeyi: RiskDuzeyi;
  teminat: Teminat;
  rucu: Rucu;
  muallak_dayanagi: MuallakDayanagi;
  iddia_ozeti: string;
  talep_maddi: number | null;
  talep_manevi: number | null;
  muallak_maddi: number | null;
  muallak_manevi: number | null;
  havuz_disi: string[];
}

// ---------------------------------------------------------------------------------------------
// Çekirdek: emsal kütüphanesi (`kutuphane.py`)
// ---------------------------------------------------------------------------------------------

export interface KutuphaneKaydi {
  okuma: RaporOkuma;
  etiketler: RaporEtiketleri;
  klasor: string | null;
  dosya_no: string | null;
}

/** Puanın bir parçası; katkı = `agirlik × benzerlik`. */
export interface Bilesen {
  ad: string;
  agirlik: number;
  /** 0-1 */
  benzerlik: number;
  ortak: string[];
}

export interface Emsal {
  kayit: KutuphaneKaydi;
  /** Bileşen katkılarının toplamı; tavan 20. */
  puan: number;
  bilesenler: Bilesen[];
  /** Çekirdekte `Emsal.gerekce()` yöntemidir; tel üzerinde hazır metin gelir. */
  gerekce: string;
}

/** Kütüphanede anılan bir karar ve geçtiği raporlar (sha256). */
export interface KararKaydi {
  merci: string | null;
  esas_no: string;
  karar_no: string;
  tarih: string | null;
  emsal: boolean | null;
  raporlar: string[];
}

// ---------------------------------------------------------------------------------------------
// Çekirdek: yazıcı (`yazici.py`)
// ---------------------------------------------------------------------------------------------

/** TESPIT: dosyadaki olguya dayanır · KALIP: yalnız son (muallak) madde. */
export type MaddeTuru = "TESPIT" | "KALIP";

/** Değerlendirmenin tek maddesi. `metin` rapora girer; diğer alanlar yalnız denetim içindir. */
export interface Madde {
  metin: string;
  tur: MaddeTuru;
  dayanak_bolum: BolumKodu | null;
  /** Hedef dosyadan AYNEN alınmış kısa alıntı. */
  dayanak_alinti: string | null;
}

/**
 * Değerlendirme bölümü taslağı. Muallak tutarı burada YOKTUR (K11): model yalnız sınıfları verir, tutarı ve son
 * maddeyi kod kurar (`muallak.py` → `MuallakOnerisi`). Çekirdekte üç sınıf (kusur, risk, teminat) bu nesnededir;
 * telde `MuallakOnerisi` ile gelir. `muallak_gerekcesi` sınıfların gerekçesidir.
 */
export interface DegerlendirmeTaslagi {
  giris: string;
  maddeler: Madde[];
  sulh_uygunluk: string;
  muallak_gerekcesi: string;
}

// ---------------------------------------------------------------------------------------------
// Çekirdek: kart bağı (`bag.py`)
// ---------------------------------------------------------------------------------------------

export type BagDurumu = "TEK" | "COK_ADAY" | "CELISKI" | "YOK";
export type BagAnahtari = "HASAR_NO" | "DOSYA_NO" | "ESAS_NO";

/** Kart kimlik tablosunun satırı (kişi adı içermez). Çekirdekteki küme alanları telde dizidir. */
export interface BagKarti {
  kart_id: number;
  hasar_nolari: string[];
  dosya_nolari: string[];
  mahkeme: string | null;
  esas_no: string | null;
  durum: string | null;
  asama: string | null;
}

/** Aday kart ve raporun hangi anahtarlarının onda tuttuğu. */
export interface Aday {
  kart: BagKarti;
  hasar: boolean;
  dosya: boolean;
  esas: boolean;
}

export interface KartBagi {
  durum: BagDurumu;
  anahtar: BagAnahtari | null;
  /** Sıralı: dosya no'su tutan, sonra esas no'su tutan üstte. Sıralama seçim DEĞİLDİR (K8). */
  adaylar: Aday[];
  /** TEK'te o kart; diğer durumlarda yalnız insan seçimiyle dolar. */
  birincil: number | null;
  insan_secimi: boolean;
  uyarilar: string[];
}

// ---------------------------------------------------------------------------------------------
// Arayüz (çekirdekte yok): iskeletlerin bölüm sırası
// ---------------------------------------------------------------------------------------------

/** ETIKETLI: kod doldurur · OZET: model belgelerden yazar · MUHAKEME: değerlendirme (`PLAN.md` Aşama 4b). */
export type BolumTuru = "ETIKETLI" | "OZET" | "MUHAKEME";

export interface BolumTanimi {
  kod: BolumKodu;
  baslik: string;
  tur: BolumTuru;
}

const ETIKETLI_BOLUMLER: readonly BolumKodu[] = ["kunye", "hasar", "hastane", "sulh_muallak"];

function bolum(kod: BolumKodu, baslik: string): BolumTanimi {
  const tur: BolumTuru = kod === "degerlendirme" ? "MUHAKEME" : ETIKETLI_BOLUMLER.includes(kod) ? "ETIKETLI" : "OZET";
  return { kod, baslik, tur };
}

/**
 * Çekirdek iskelet başına SIRALI bölüm listesi ve görünen başlık tutmuyor (bölümler belgedeki sırayla
 * gelir). Aşağıdaki sıra pilot ölçümündeki iskelet tarifinden; başlıklar `BOLUM_ANAHTARLARI` anahtarlarının
 * açık yazımı. Entegrasyonda şirket şablonlarından doğrulanır.
 */
export const ISKELET_BOLUMLERI: Record<YazilabilirIskelet, BolumTanimi[]> = {
  ANADOLU: [
    bolum("hasar", "Hasar Bilgileri"),
    bolum("hastane", "Hastaneye İlişkin Bilgiler"),
    bolum("sulh_muallak", "Sulh ve Muallak Bilgileri"),
    bolum("iddia", "Davada Yer Alan İddia"),
    bolum("yargi_sureci", "Yargı Sürecindeki Gelişme"),
    bolum("uzman_gorusu", "Tıbbi Görüş"),
    bolum("police", "Poliçe İncelemesi"),
    bolum("degerlendirme", "Değerlendirme ve Sonuç"),
  ],
  ALTILI: [
    bolum("hasar", "Mahkeme ve Tazminat Bilgisi"),
    bolum("iddia", "Davada Yer Alan İddia"),
    bolum("beyan", "Sigortalı Hekim Beyan Özeti"),
    bolum("police", "Poliçe Tespiti"),
    bolum("uzman_gorusu", "Uzman Görüşü"),
    bolum("degerlendirme", "Değerlendirme"),
  ],
  KISA: [
    bolum("hasar", "Hasar Bilgileri"),
    bolum("iddia", "İnceleme Konusu İddia"),
    bolum("uzman_gorusu", "Uzman Görüşü"),
    bolum("degerlendirme", "Değerlendirme"),
  ],
  // Ek raporda hasar bölümü yoktur; künye satırları (Konu, Sigortalı, Poliçe No — çekirdekte `duzen.DUZENLER.EK.kunye`)
  // kendi bölümünde durur, yoksa Word'de `[…]` çıkar.
  EK: [bolum("kunye", "Künye"), bolum("ek_inceleme", "Ek İnceleme"), bolum("degerlendirme", "Değerlendirme")],
};

/**
 * Değerlendirme giriş cümlesinin iskelete göre kalıbı (çekirdekte `yazici.KALIPLAR`): cümlenin katlanmış
 * (Türkçe küçük harf, yalnız harf/rakam) başlangıcı. Ek rapor "Dosyada … ;" ile başlar.
 */
export const GIRIS_KALIPLARI: Record<YazilabilirIskelet, string> = {
  ANADOLU: "tarafımızailetilen",
  ALTILI: "tarafımızailetilen",
  KISA: "tarafımızailetilen",
  EK: "dosyada",
};

// ---------------------------------------------------------------------------------------------
// Arayüz (çekirdekte yok): dosya girdisi
// ---------------------------------------------------------------------------------------------

/** Dava arama sonucu — entegrasyonda HUKDOK kart yanıtından türetilir. */
export interface LexisDava {
  case_id: number;
  ofis_no: string;
  sirket: LexisSirket | null;
  mahkeme: string | null;
  esas_no: string | null;
  hasar_no: string | null;
  dosya_no: string | null;
  sigortali: string | null;
  karsi_taraf: string | null;
  uzmanlik: string | null;
  durum: string | null;
}

/** Rapor yazımının beklediği belge türleri + diğerleri. */
export type LexisBelgeTuru = "DILEKCE" | "HEKIM_BEYANI" | "BILIRKISI" | "POLICE" | "KARAR" | "DIGER";

/** Eksikse uyarı verilen türler (`lexis-rapor/PLAN.md` K10). */
export const BEKLENEN_BELGELER: readonly LexisBelgeTuru[] = ["DILEKCE", "HEKIM_BEYANI", "BILIRKISI", "POLICE"];

export const BELGE_TURU_ADLARI: Record<LexisBelgeTuru, string> = {
  DILEKCE: "Dava / şikâyet dilekçesi",
  HEKIM_BEYANI: "Sigortalı hekim beyanı",
  BILIRKISI: "Bilirkişi / ATK raporu",
  POLICE: "Poliçe",
  KARAR: "Mahkeme kararı",
  DIGER: "Diğer",
};

/** Dava kartındaki bir belge — entegrasyonda `GET /api/cases/{id}/documents` satırından. */
export interface LexisBelge {
  id: number;
  ad: string;
  tur: LexisBelgeTuru;
  /** ISO `yyyy-mm-dd` (yükleme günü). */
  tarih: string;
  ozet: string | null;
  sayfa: number | null;
}

/** Künye değerinin geldiği yer: dava kartı, dosyanın belgesi ya da kullanıcının elle girişi. */
export type DegerKaynagi = "KART" | "BELGE" | "ELLE";

/** Kart ile belge aynı alan için farklı değer veriyorsa ikisi de gösterilir; sessizce biri seçilmez. */
export interface KartBelgeCeliskisi {
  alan: string;
  etiket: string;
  kart: string;
  belge: string;
  belge_id: number;
}

/** Çekirdeğin tek girdisi (`PLAN.md` Aşama 2 `DosyaGirdisi`) — arayüzün gördüğü hâli. */
export interface DosyaGirdisi {
  dava: LexisDava;
  sirket: LexisSirket | null;
  rapor_turu: RaporTuru;
  iskelet: YazilabilirIskelet;
  mahkeme: string | null;
  esas_no: string | null;
  hasar_no: string | null;
  hukuk_no: string | null;
  police_no: string | null;
  teminat_limiti: number | null;
  talep_maddi: number | null;
  talep_manevi: number | null;
  uzmanlik: string | null;
  sigortali: string | null;
  magdur: string | null;
  hastane: string | null;
  belgeler: LexisBelge[];
  celiskiler: KartBelgeCeliskisi[];
  /** Ek raporda: aynı hasarın kütüphanedeki önceki raporu (sha256). */
  onceki_rapor: string | null;
}

// ---------------------------------------------------------------------------------------------
// Arayüz (çekirdekte yok): taslak, uyarı, muallak
// ---------------------------------------------------------------------------------------------

/** Etiketli bölümün bir satırı. Çekirdekte `RaporTaslagi.alanlar` (alan kodu → metin) + şablon etiketi. */
export interface EtiketliSatir {
  alan: string;
  etiket: string;
  deger: string | null;
  /** Boş kalırsa `[…]` yazılır ve uyarı düşer (`word.py` zorunlu alanları). */
  zorunlu: boolean;
  kaynak: DegerKaynagi | null;
}

/** Özet bölümün bir paragrafı; her paragraf hangi belgeden yazıldığını taşır (`PLAN.md` Aşama 4b). */
export interface OzetParagraf {
  metin: string;
  kaynak_belge_id: number | null;
  /** Kararlardan yazımda: paragrafın dayandığı karar (karar veritabanı kimliği, `RafKarari.id`). */
  kaynak_karar_id?: number | null;
  /** O karardan AYNEN alınmış kısa alıntı; rapora girmez, denetim kaynak kararda arar. */
  dayanak_alinti?: string | null;
}

export type UyariSeviyesi = "HATA" | "UYARI" | "BILGI";

/** Çekirdek uyarıları düz metindir (`yazici.dogrula`, `word_yaz`); ekran için kodlu ve yer bilgili gerekir. */
export type UyariKodu =
  | "DAYANAKSIZ"
  | "ALINTI_KISA"
  | "ALINTI_BULUNAMADI"
  | "EMSALDEN_TASINMA"
  | "BELGE_YOKLUGU"
  | "KALIP_YERI"
  | "ATIF_DOGRULANAMADI"
  | "GIRIS_KALIBI"
  | "MUALLAK_DAYANAK_YOK"
  | "MUALLAK_TALEBI_ASIYOR"
  | "MUALLAK_LIMITI_ASIYOR"
  | "ALAN_BOS"
  | "BOLUM_BOS"
  | "DOLDURULMAMIS"
  | "MASKE_KALINTISI"
  | "KART_BELGE_CELISKISI"
  | "EKSIK_BELGE"
  /** Özet paragrafındaki tutar, tarih ya da esas / karar numarası kaynak kararda geçmiyor. */
  | "OLGU_KAYNAKTA_YOK";

export interface LexisUyari {
  id: string;
  kod: UyariKodu;
  seviye: UyariSeviyesi;
  bolum: BolumKodu | null;
  /** Değerlendirme maddesinin sırası, 1'den başlar. */
  madde: number | null;
  /** Etiketli satırın alan kodu. */
  alan: string | null;
  metin: string;
}

export type MuallakDayanakTuru = "KRITER" | "EMSAL" | "YOK";

export interface MuallakDayanakSatiri {
  tur: "KRITER" | "EMSAL";
  aciklama: string;
  maddi: number | null;
  manevi: number | null;
  yil: number | null;
  /** Emsal satırında kütüphanedeki rapor. */
  rapor_sha: string | null;
}

/** Muallağı kod hesaplar, model seçmez (`PLAN.md` K11, Aşama 10 `MuallakOnerisi`). */
export interface MuallakOnerisi {
  maddi: number | null;
  manevi: number | null;
  dayanak: MuallakDayanakTuru;
  dayanak_satirlari: MuallakDayanakSatiri[];
  /** Modelin verdiği sınıflar — tutarın seçildiği tablo satırını belirler. */
  kusur_tespiti: KusurTespiti;
  risk_duzeyi: RiskDuzeyi;
  teminat: Teminat;
  uyarilar: string[];
}

/** Ekrandaki çalışma taslağı. Çekirdek karşılığı `RaporTaslagi` + `DegerlendirmeTaslagi`. */
export interface LexisTaslak {
  case_id: number;
  sirket: LexisSirket | null;
  rapor_turu: RaporTuru;
  iskelet: YazilabilirIskelet;
  etiketli: Partial<Record<BolumKodu, EtiketliSatir[]>>;
  ozet: Partial<Record<BolumKodu, OzetParagraf[]>>;
  degerlendirme: DegerlendirmeTaslagi | null;
  muallak: MuallakOnerisi | null;
  /** İnsanın yazdığı kesin tutarlar; boşsa öneri geçerlidir. */
  muallak_maddi: number | null;
  muallak_manevi: number | null;
  /** Bakılan eski raporların sha256'ları (K3: hangi raporlara bakıldığı gösterilir). */
  emsaller: string[];
  /** Taslağın yazıldığı kararlar (`RafKarari.id`); dayanak alıntıları bunların metninde aranır. Eski kayıtta yok. */
  kararlar?: number[];
}

// ---------------------------------------------------------------------------------------------
// Arayüz (çekirdekte yok): karar rafı — servisin karar veritabanı (`lexis-rapor/servis/karar_raf.py`)
// ---------------------------------------------------------------------------------------------

/**
 * Raftaki bir büro belgesi (metinsiz). SONUÇ İKİ AYRI ALANDIR (kullanıcı kararı K22): `hukum_sinifi` kararın
 * BÜTÜNÜDÜR (koddan, hükümden okunur), `sonuc_muvekkil` müvekkil yönünden sonuçtur (HUKDOK etiketinden). Hükmedilen
 * tutar kararın bütününe aittir. Kodun bulamadığı alan boş gelir (uydurulmaz).
 */
export interface RafKarari {
  id: number;
  /** `karar` | `bilirkisi_raporu` | `atk_raporu` */
  belge_turu: string;
  mahkeme: string | null;
  derece: string | null;
  esas_no: string | null;
  karar_no: string | null;
  /** ISO `yyyy-mm-dd`. */
  karar_tarihi: string | null;
  uzmanlik: string | null;
  /** HUKDOK kart kimliği; karta bağlanamamış belgede `null`. */
  kart_id: number | null;
  kart_bagi: string | null;
  asamaya_bagli: boolean;
  metin_uzunluk: number;
  hukum_sinifi: string | null;
  hukum_yonleri: string[];
  sonuc_muvekkil: string | null;
  /** `AYNI` | `KARMA` | `KARMA_TALEP` | `AYRISIK` — iki sonuç alanının ilişkisi. */
  sonuc_iliskisi: string | null;
  hukmedilen_maddi: number[];
  hukmedilen_manevi: number[];
  hukmedilen_birlesik: number[];
  talep_maddi: number[];
  talep_manevi: number[];
  /** `OLUM` | `YARALANMA` */
  olay: string | null;
  maluliyet_orani: string[];
  kusur_orani: string[];
  dayanak_kurul: string[];
  faiz: string[];
  /** Gerekçe konusu → o konuya değinen paragraf sayısı (`kusur`, `illiyet`, `onam`, `usul`, `tazminat`, `bilirkisi`). */
  konular: Record<string, number>;
}

export interface GerekceParagrafi {
  metin: string;
  konular: string[];
}

/** Tek karar: künye + alanlar + sunucuda kesilmiş parçalar + birebir metin. Metin maskesizdir (büronun kendi kararı). */
export interface RafKarariAyrinti extends RafKarari {
  /** Künye alanı → kaynağı (`insan` | `hukdok_db` | `dosya_adi` | `paket`). */
  kunye_kaynak: Record<string, string>;
  vekalet_ucreti: number[];
  yargilama_gideri: number[];
  hukum_kaynagi: string | null;
  yas: string[];
  davaci_sayisi: string | null;
  parcalar: { hukum: string | null; iddia: string[]; savunma: string[]; gerekce: GerekceParagrafi[] };
  metin: string;
}

export interface RafSuzgeci {
  belge_turu?: string | null;
  derece?: string | null;
  hukum_sinifi?: string | null;
  sonuc_muvekkil?: string | null;
  uzmanlik?: string | null;
  konu?: string | null;
  yalniz_kartli?: boolean;
  metin?: string;
  limit?: number;
  offset?: number;
}

export interface RafSayfasi {
  toplam: number;
  kararlar: RafKarari[];
}

export type RafSecenekleri = Record<"derece" | "uzmanlik" | "belge_turu" | "hukum_sinifi" | "sonuc_muvekkil", string[]>;

/** Kararlardan yazım bu kurulumda açık mı (`LEXIS_YAZIM`); `neden`: `kapali` | `anahtar_yok` | `paket_yok`. */
export interface YazimDurumu {
  acik: boolean;
  neden: string | null;
  model: string | null;
}

/** `GET /lexis-api/kararlar/{case_id}` — dava kartına bağlı büro kararları + yazım durumu. */
export interface KartKararlari {
  kararlar: RafKarari[];
  yazim: YazimDurumu;
}

/** `POST /lexis-api/yaz` — kararlardan yazılan bölümler. Uyarılar çekirdeğin düz metin uyarılarıdır. */
export interface YazimSonucu {
  ozet: Partial<Record<BolumKodu, OzetParagraf[]>>;
  degerlendirme: DegerlendirmeTaslagi;
  muallak: MuallakOnerisi;
  kararlar: number[];
  uyarilar: string[];
  model: string;
  maske: { bilinen: number; kalip: number; ogrenilen: number };
  gonderilen_karakter: number;
}

export const HUKUM_SINIFI_ADLARI: Record<string, string> = {
  RED_ESASTAN: "Ret (esastan)",
  RED_USULDEN: "Ret (usulden)",
  KABUL: "Kabul",
  KISMEN_KABUL: "Kısmen kabul",
  BASVURU_RET: "Başvuru reddi",
  KALDIRMA: "Kaldırma",
  KALDIRMA_YENIDEN_HUKUM: "Kaldırma · yeniden hüküm",
  ONAMA: "Onama",
  DUZELTEREK_ONAMA: "Düzelterek onama",
  BOZMA: "Bozma",
  KISMEN_ONAMA_BOZMA: "Kısmen onama · bozma",
  ACILMAMIS: "Açılmamış sayılma",
  FERAGAT: "Feragat",
  KARAR_VERILMESINE_YER_OLMADIGINA: "Karar verilmesine yer olmadığına",
  CEZA: "Ceza kararı",
  DIGER: "Diğer",
};

/** Künye iki sözlükle gelir: büyük harfli değer HUKDOK aşama kaydından, küçük harfli değer karar paketinden. */
export const DERECE_ADLARI: Record<string, string> = {
  YEREL: "Yerel mahkeme",
  ISTINAF: "İstinaf",
  TEMYIZ: "Temyiz",
  KARAR_DUZELTME: "Karar düzeltme",
  ilk_derece: "İlk derece (paket)",
  bam: "BAM (paket)",
  danistay: "Danıştay (paket)",
  yargitay: "Yargıtay (paket)",
  diger: "Diğer (paket)",
};

export const BELGE_TURU_RAF_ADLARI: Record<string, string> = {
  karar: "Mahkeme kararı",
  bilirkisi_raporu: "Bilirkişi raporu",
  atk_raporu: "ATK raporu",
};

export const KONU_ADLARI: Record<string, string> = {
  kusur: "Kusur",
  illiyet: "İlliyet",
  onam: "Onam",
  usul: "Usul",
  tazminat: "Tazminat",
  bilirkisi: "Bilirkişi / ATK",
};

export const SONUC_ILISKISI_ADLARI: Record<string, string> = {
  AYNI: "aynı yön",
  KARMA: "karma hüküm (taraflara göre)",
  KARMA_TALEP: "karma hüküm (taleplere göre) — incele",
  AYRISIK: "ayrışıyor — incele",
};

export const rafAdi = (sozluk: Record<string, string>, deger: string | null | undefined): string => (deger ? (sozluk[deger] ?? deger) : "—");

// ---------------------------------------------------------------------------------------------
// Arayüz (çekirdekte yok): taslak akışı
// ---------------------------------------------------------------------------------------------

export type UretimAsamasi = "olgular" | "emsaller" | "bolumler" | "muallak" | "denetim";

export const URETIM_ASAMALARI: readonly { kod: UretimAsamasi; ad: string }[] = [
  { kod: "olgular", ad: "Olgular" },
  { kod: "emsaller", ad: "Emsaller" },
  { kod: "bolumler", ad: "Bölümler" },
  { kod: "muallak", ad: "Muallak" },
  { kod: "denetim", ad: "Denetim" },
];

export interface TaslakIstegi {
  case_id: number;
  sirket: LexisSirket | null;
  rapor_turu: RaporTuru;
  iskelet: YazilabilirIskelet;
  /** Modele gidecek belgeler — kullanıcı gönderim onayında görür (K4). */
  belge_idleri: number[];
  emsal_sha: string[];
  /**
   * Gerçek davada: taslağın yazılacağı kararlar (`RafKarari.id`). Doluysa kararların MASKELİ metni modele gider
   * (kullanıcı gönderim onayında görür); boşsa taslak iskelettir, hiçbir şey gönderilmez.
   */
  karar_idleri?: number[];
}

/**
 * `taslakYaz` NDJSON olayları — HUKDOK stream sözleşmesinin biçimi (`analyzer.py::_failed_event`):
 * `failed` SON olaydır ve `error_kod` taşır; başarılı akış `complete` ile biter.
 */
export type LexisAkisOlayi =
  | { status: "info"; asama: UretimAsamasi; mesaj: string }
  /** Akışı KESMEYEN sorun: kararlardan yazım yapılamadı, taslak iskelet olarak sürüyor. */
  | { status: "warning"; mesaj: string }
  | { status: "bolum"; bolum: BolumKodu; etiketli?: EtiketliSatir[]; ozet?: OzetParagraf[]; degerlendirme?: DegerlendirmeTaslagi }
  | { status: "muallak"; oneri: MuallakOnerisi }
  | { status: "complete"; kosu_id: string; uyarilar: LexisUyari[] }
  | { status: "failed"; error_ozet: string; error_kod: string };

// ---------------------------------------------------------------------------------------------
// Arayüz (çekirdekte yok): geçmiş, kütüphane filtresi, kart bağı satırı, şirket profili
// ---------------------------------------------------------------------------------------------

export interface TaslakKosusu {
  id: string;
  /** ISO zaman damgası. */
  tarih: string;
  kullanici: string;
  case_id: number;
  ofis_no: string;
  sirket: LexisSirket | null;
  rapor_turu: RaporTuru;
  iskelet: YazilabilirIskelet;
  emsal_sayisi: number;
  uyari_sayisi: number;
  /** Word indirildiyse dolu. */
  indirme_tarihi: string | null;
}

export interface KutuphaneFiltresi {
  sirket?: LexisSirket | null;
  rapor_turu?: RaporTuru | null;
  iskelet?: Iskelet | null;
  uzmanlik?: string | null;
  kusur_tespiti?: KusurTespiti | null;
  risk_duzeyi?: RiskDuzeyi | null;
  metin?: string;
}

/** Kart bağı inceleme listesinin satırı: bir eski rapor ve karta bağı. */
export interface RaporBagi {
  /** İnsan seçiminin anahtarı (`bag.py` seçim kaydı): servis listesinde klasör adının özeti — kişi adı taşımaz. */
  rapor: string;
  /** Klasörün yalnız numarası; numarası olmayan klasörde "numarasız". */
  klasor: string;
  sirket: LexisSirket | null;
  rapor_turu: RaporTuru;
  rapor_no: string | null;
  hasar_no: string | null;
  mahkeme: string | null;
  esas_no: string | null;
  bag: KartBagi;
}

export interface MuallakKriterSatiri {
  yil: number;
  kusur_tespiti: KusurTespiti;
  risk_duzeyi: RiskDuzeyi;
  maddi: number | null;
  manevi: number | null;
  aciklama: string;
}

/** `docs/plan/lexis-raporu-plani-2026-10-03.md` §4 `lexis_sirket_profilleri`. */
export interface SirketProfili {
  sirket_kodu: LexisSirket;
  ad: string;
  iskelet_ana: YazilabilirIskelet;
  iskelet_ek: YazilabilirIskelet;
  /** Sabit metin anahtarı → metin (giriş cümlesi, saygı cümlesi, poliçe genel şart paragrafı). */
  sabit_metinler: Record<string, string>;
  kriter_metni: string;
  muallak_tablosu: MuallakKriterSatiri[];
  /** ISO tarih ya da zaman damgası; hiç kaydedilmemiş (koddaki varsayılan) profilde `null`. */
  guncelleme: string | null;
}

// ---------------------------------------------------------------------------------------------
// Arayüz (çekirdekte yok): kayıtlı taslak — servisin kendi veritabanında durur (`lexis-rapor/servis/depo.py`)
// ---------------------------------------------------------------------------------------------

/** Taslakla birlikte saklanan ekran durumu (sunucu içeriğine bakmaz). */
export interface TaslakEkranDurumu {
  /** Bölüm kodu → `bos | yazildi | duzenlendi` (`BolumGezgini`). */
  bolum_durumlari?: Partial<Record<BolumKodu, string>>;
  /** Yazımda seçili bırakılan belgeler. */
  secili_belgeler?: number[];
  /** Yazımda seçili bırakılan kararlar (`RafKarari.id`). */
  secili_kararlar?: number[];
}

/** `GET /lexis-api/taslak/{case_id}` — davanın kayıtlı çalışma taslağı. */
export interface KayitliTaslak {
  taslak: LexisTaslak;
  ekran: TaslakEkranDurumu;
  /** İyimser kilit: kayıt, okunan sürümle yazılır; başka oturum araya girdiyse sunucu 409 döner. */
  surum: number;
  kosu_id: number | null;
  guncelleyen: string;
  /** ISO zaman damgası (UTC). */
  guncelleme: string;
}

/** `PUT /lexis-api/taslak/{case_id}` gövdesi. `surum` ilk kayıtta `null`. */
export interface TaslakKaydi {
  taslak: LexisTaslak;
  ekran: TaslakEkranDurumu;
  surum: number | null;
  kosu_id: number | null;
  uyari_sayisi: number;
}

export type TaslakKayitSonucu = Pick<KayitliTaslak, "surum" | "guncelleme" | "guncelleyen">;

// ---------------------------------------------------------------------------------------------
// Görünen adlar
// ---------------------------------------------------------------------------------------------

export const SIRKET_ADLARI: Record<LexisSirket, string> = {
  AK: "Ak Sigorta",
  ANADOLU: "Anadolu Sigorta",
  AXA: "AXA Sigorta",
  NIPPON: "Nippon Sigorta",
  QUICK: "Quick Sigorta",
  EUREKO: "Eureko Sigorta",
};

export const KUSUR_ADLARI: Record<KusurTespiti, string> = {
  HATA_YOK: "Hata yok",
  KOMPLIKASYON: "Komplikasyon",
  KOMPLIKASYON_YONETIMI: "Komplikasyon yönetimi",
  HATA_VAR: "Hata var",
  BELIRSIZ: "Belirsiz",
};

export const RISK_ADLARI: Record<RiskDuzeyi, string> = {
  DUSUK: "Düşük",
  RISKLI: "Riskli",
  BELIRSIZ: "Belirsiz",
};

export const TEMINAT_ADLARI: Record<Teminat, string> = {
  ICINDE: "Teminat içinde",
  DISINDA: "Teminat dışında",
  BELIRSIZ: "Belirsiz",
};

export const BAG_DURUMU_ADLARI: Record<BagDurumu, string> = {
  TEK: "Tek kart",
  COK_ADAY: "Çok aday",
  CELISKI: "Çelişki",
  YOK: "Bağ yok",
};

export const BAG_ANAHTARI_ADLARI: Record<BagAnahtari, string> = {
  HASAR_NO: "hasar no",
  DOSYA_NO: "dosya no",
  ESAS_NO: "mahkeme + esas no",
};
