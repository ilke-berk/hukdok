// Lexis istemcisi — `/lexis` sayfası araca YALNIZ bununla konuşur (`lib/hukukbotApi.ts` deseni).
//
// İKİ ADAPTÖR (kipi sayfa seçer, `veriKipi()`):
// - ÖRNEK (varsayılan): bellekte çalışır (`lib/lexisOrnekVeri.ts`, sentetik veri) — sayfa yenilenince durum
//   sıfırlanır, hiçbir şey kaydedilmez. TEK ağ isteği Word'dür: `wordIndir` örnek taslağı gerçek servise
//   (`lib/lexisWord.ts` → `/lexis-api/word`) gönderir, gerçek şirket şablonunda dosya döner.
// - GERÇEK (`?veri=gercek`): her yöntem Lexis servisine gider (`lib/lexisServis.ts`); taslak, koşu geçmişi, kart
//   seçimi ve şirket profili servisin kendi veritabanında saklanır (`kalici`). Denetim hâlâ buradaki
//   `lexisDenetim.ts` ile koşar. Taslak karttan kurulan iskelettir; dava kartına bağlı karar seçilirse (ve servis
//   yazımı açmışsa) özet + değerlendirme o kararlardan modele yazdırılır (`/lexis-api/yaz`, kararlar maskeli gider).
//   Karar rafı (Kütüphane › Karar rafı, tezgâhtaki "Kararlar") servisin karar veritabanından gelir.
//
// ENTEGRASYON: `LexisApi` arayüzü sözleşmedir. Dilekçe / beyan / poliçeden yazım gelince `taslakYaz` NDJSON akışına
// bağlanır (`hukukbotApi.ask` okuyucusu), `ORNEK_VERI` false olur; örnek veri, `lexisDenetim.ts` ve buradaki puanlama KALKAR.
import { denetle as ornekDenetle, kararKaynakMetni } from "@/lib/lexisDenetim";
import { katla } from "@/lib/lexisMetin";
import type { WordSonucu } from "@/lib/lexisWord";
import {
  ORNEK_DAVALAR,
  ORNEK_DOSYALAR,
  ORNEK_GECMIS,
  ORNEK_HEDEF_ETIKETLER,
  ORNEK_KARARLAR,
  ORNEK_KART_BAGLARI,
  ORNEK_KUTUPHANE,
  ORNEK_PROFILLER,
  ORNEK_TASLAKLAR,
} from "@/lib/lexisOrnekVeri";
import {
  ISKELET_BOLUMLERI,
  type Bilesen,
  type DosyaGirdisi,
  type Emsal,
  type KararKaydi,
  type KartKararlari,
  type KayitliTaslak,
  type KutuphaneFiltresi,
  type KutuphaneKaydi,
  type KusurTespiti,
  type LexisAkisOlayi,
  type LexisDava,
  type LexisSirket,
  type LexisTaslak,
  type LexisUyari,
  type MuallakOnerisi,
  type RafKarari,
  type RafKarariAyrinti,
  type RafSayfasi,
  type RafSecenekleri,
  type RafSuzgeci,
  type RaporBagi,
  type RaporEtiketleri,
  type RaporTuru,
  type RiskDuzeyi,
  type SirketProfili,
  type TaslakIstegi,
  type TaslakKaydi,
  type TaslakKayitSonucu,
  type TaslakKosusu,
  type Teminat,
  type YazimSonucu,
} from "@/types/lexis";

/** Örnek adaptör devrede mi — entegrasyon tamamlanınca false. Dava bölgesinin kipi ayrıca `veriKipi()`. */
export const ORNEK_VERI = true;

export const LEXIS_GENEL_HATA = "Lexis isteği tamamlanamadı.";

export class LexisApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "LexisApiError";
    this.status = status;
  }
}

export interface EmsalIstegi {
  case_id: number;
  sirket: LexisSirket | null;
  rapor_turu: RaporTuru;
  /** Kaç emsal (varsayılan 3 — çekirdekte `emsal_bul(k=3)`). */
  k?: number;
}

/** Muallak önerisinin sınıfları — belgelerden yazım gelene kadar insan seçer; talep ve dosya no'yu sunucu karttan okur. */
export interface MuallakIstegi {
  case_id: number;
  sirket: LexisSirket | null;
  kusur_tespiti: KusurTespiti;
  risk_duzeyi: RiskDuzeyi;
  teminat: Teminat;
}

export interface LexisApi {
  /** Lexis raporu yazılabilecek davalar (müvekkili sigorta şirketi olanlar). Boş sorgu son davaları verir. */
  davaAra(sorgu: string, signal?: AbortSignal): Promise<LexisDava[]>;
  /** Kart alanları + belge listesi → çekirdeğin girdisi. */
  dosyaGetir(caseId: number, signal?: AbortSignal): Promise<DosyaGirdisi>;
  /** En benzer eski raporlar, puan ve gerekçesiyle (K3). */
  emsalOner(istek: EmsalIstegi, signal?: AbortSignal): Promise<Emsal[]>;
  /** Kütüphanedeki tek rapor için dosyaya göre puan — elle eklenen emsalde. */
  emsalPuanla(caseId: number, sha256: string, signal?: AbortSignal): Promise<Emsal>;
  /** Taslak akışı (NDJSON); `failed` SON olaydır. */
  taslakYaz(istek: TaslakIstegi, signal?: AbortSignal): AsyncGenerator<LexisAkisOlayi, void, void>;
  /** Düzenlenmiş taslağı yeniden denetler. */
  denetle(taslak: LexisTaslak, signal?: AbortSignal): Promise<LexisUyari[]>;
  /** Sınıflar değişince muallak önerisini yeniden hesaplatır (tutarı kod belirler, K11). */
  muallakOner(istek: MuallakIstegi, signal?: AbortSignal): Promise<MuallakOnerisi>;
  /** Şirket şablonunu doldurup Word'ü indirir; şablon yazımının uyarılarıyla döner. */
  wordIndir(taslak: LexisTaslak, signal?: AbortSignal): Promise<WordSonucu>;
  gecmis(signal?: AbortSignal): Promise<TaslakKosusu[]>;
  kutuphaneAra(filtre: KutuphaneFiltresi, signal?: AbortSignal): Promise<KutuphaneKaydi[]>;
  raporGetir(sha256: string, signal?: AbortSignal): Promise<KutuphaneKaydi>;
  kararBankasi(signal?: AbortSignal): Promise<KararKaydi[]>;
  /** Karar rafı: süzgeçlere uyan büro kararları (metinsiz), en yeni karar önce. */
  kararAra(suzgec: RafSuzgeci, signal?: AbortSignal): Promise<RafSayfasi>;
  rafSecenekleri(signal?: AbortSignal): Promise<RafSecenekleri>;
  /** Dava kartına bağlı kararlar + kararlardan yazımın açık olup olmadığı. */
  kartKararlari(caseId: number, signal?: AbortSignal): Promise<KartKararlari>;
  /** Tek karar: künye, iki sonuç alanı, tutarlar, parçalar ve tam metin. */
  kararGetir(id: number, signal?: AbortSignal): Promise<RafKarariAyrinti>;
  /** `TEK` dışındaki bağlar (inceleme listesi). */
  kartBaglari(signal?: AbortSignal): Promise<RaporBagi[]>;
  /** İnsan seçimi (K8); `kartId = null` seçimi geri alır. */
  kartSec(rapor: string, kartId: number | null, signal?: AbortSignal): Promise<RaporBagi>;
  profiller(signal?: AbortSignal): Promise<SirketProfili[]>;
  profilKaydet(profil: SirketProfili, signal?: AbortSignal): Promise<SirketProfili>;
  /** Taslak, geçmiş, kart seçimi ve profil sunucuda saklanıyor mu. Örnek kipte `false`: hiçbir şey kaydedilmez. */
  readonly kalici: boolean;
  /** Davanın kayıtlı taslağı; yoksa (ve örnek kipte) `null`. */
  taslakGetir(caseId: number, signal?: AbortSignal): Promise<KayitliTaslak | null>;
  /** Taslağı okunan sürümle yazar; başka oturum araya girdiyse 409 (`LexisApiError`). Örnek kipte `null`. */
  taslakKaydet(caseId: number, kayit: Omit<TaslakKaydi, "kosu_id">, signal?: AbortSignal): Promise<TaslakKayitSonucu | null>;
  /** Kayıtlı taslağı siler (künye değişip taslak bilerek bırakıldığında). */
  taslakSil(caseId: number, signal?: AbortSignal): Promise<void>;
}

// ---------------------------------------------------------------------------------------------
// Örnek adaptör
// ---------------------------------------------------------------------------------------------

const kopya = <T>(deger: T): T => JSON.parse(JSON.stringify(deger)) as T;

interface OrnekDurum {
  gecmis: TaslakKosusu[];
  baglar: RaporBagi[];
  profiller: SirketProfili[];
  kosuSayaci: number;
}

const ilkDurum = (): OrnekDurum => ({
  gecmis: kopya(ORNEK_GECMIS),
  baglar: kopya(ORNEK_KART_BAGLARI),
  profiller: kopya(ORNEK_PROFILLER),
  kosuSayaci: ORNEK_GECMIS.length,
});

let durum = ilkDurum();
let gecikmeMs = 320;

/** Test yardımcısı: örnek adaptörün bellek durumunu başa alır. */
export function ornekDurumuSifirla(): void {
  durum = ilkDurum();
  kip = "ornek";
  gercekDosyalar.clear();
  gercekEmsalMetinleri.clear();
  gercekKosular.clear();
  gercekKararMetinleri.clear();
  gercekKararBankasi = null;
}

/** Akış ve istek gecikmesi (ms) — testler 0 yapar. */
export function ornekGecikmeAyarla(ms: number): void {
  gecikmeMs = ms;
}

function iptalHatasi(): DOMException {
  return new DOMException("İstek iptal edildi", "AbortError");
}

function bekle(signal?: AbortSignal, carpan = 1): Promise<void> {
  if (signal?.aborted) return Promise.reject(iptalHatasi());
  const ms = gecikmeMs * carpan;
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const zamanlayici = setTimeout(() => {
      signal?.removeEventListener("abort", iptal);
      resolve();
    }, ms);
    const iptal = () => {
      clearTimeout(zamanlayici);
      reject(iptalHatasi());
    };
    signal?.addEventListener("abort", iptal, { once: true });
  });
}

function dosyaBul(caseId: number): DosyaGirdisi {
  const dosya = ORNEK_DOSYALAR[caseId];
  if (!dosya) throw new LexisApiError(404, "Dava bulunamadı.");
  return dosya;
}

function kayitBul(sha256: string): KutuphaneKaydi {
  const kayit = ORNEK_KUTUPHANE.find((k) => k.okuma.sha256 === sha256);
  if (!kayit) throw new LexisApiError(404, "Rapor kütüphanede bulunamadı.");
  return kayit;
}

/** Emsal raporun modele giden metni (bölümlerin birleşimi). */
function kayitMetni(kayit: KutuphaneKaydi): string {
  return Object.values(kayit.okuma.bolumler).join("\n");
}

// Puan bileşenleri — ağırlık ve görünen adlar çekirdektekiyle aynı (`kutuphane.py::AGIRLIKLAR`). Benzerlik
// burada küme örtüşmesidir; çekirdek sözcük kökü + seyreklik ağırlığı kullanır (örnek puan yaklaşık).
const BILESENLER: readonly { ad: string; agirlik: number; gorunen: string }[] = [
  { ad: "sirket", agirlik: 3, gorunen: "şirket" },
  { ad: "rapor_turu", agirlik: 2, gorunen: "rapor türü" },
  { ad: "uzmanlik", agirlik: 2, gorunen: "uzmanlık" },
  { ad: "tibbi_islem", agirlik: 2.5, gorunen: "işlem" },
  { ad: "tibbi_olay", agirlik: 4, gorunen: "olay" },
  { ad: "hastada_olusan_zarar", agirlik: 2.5, gorunen: "zarar" },
  { ad: "iddia_edilen_kusur", agirlik: 1, gorunen: "kusur" },
  { ad: "uygulanan_yontem", agirlik: 1.5, gorunen: "yöntem" },
  { ad: "tibbi_surec", agirlik: 0.5, gorunen: "süreç" },
  { ad: "yargi_yolu", agirlik: 1, gorunen: "yargı yolu" },
];

/** Bileşenin ekranda görünen adı (`gerekce` satırı ve puan dökümü). */
export function bilesenAdi(ad: string): string {
  return BILESENLER.find((b) => b.ad === ad)?.gorunen ?? ad;
}

function kumeOrtusmesi(a: string[], b: string[]): { benzerlik: number; ortak: string[] } {
  const ortak = a.filter((x) => b.includes(x));
  const birlesim = new Set([...a, ...b]).size;
  return { benzerlik: birlesim === 0 ? 0 : ortak.length / birlesim, ortak };
}

const sozcukler = (metin: string | null): string[] => (metin ?? "").split(/\s+/).map(katla).filter(Boolean);

interface PuanHedefi {
  sirket: LexisSirket | null;
  rapor_turu: RaporTuru;
  uzmanlik: string | null;
  etiketler: RaporEtiketleri;
}

function puanla(hedef: PuanHedefi, kayit: KutuphaneKaydi): Emsal {
  const e = kayit.etiketler;
  const esit = (x: string | null, y: string | null, ortak: boolean): { benzerlik: number; ortak: string[] } =>
    x && y && x === y ? { benzerlik: 1, ortak: ortak ? [x] : [] } : { benzerlik: 0, ortak: [] };
  const olcum: Record<string, { benzerlik: number; ortak: string[] }> = {
    sirket: esit(hedef.sirket, kayit.okuma.sirket, false),
    rapor_turu: esit(hedef.rapor_turu, kayit.okuma.rapor_turu, false),
    uzmanlik: esit(hedef.uzmanlik, e.uzmanlik ?? kayit.okuma.uzmanlik, true),
    tibbi_islem: (() => {
      const o = kumeOrtusmesi(sozcukler(hedef.etiketler.tibbi_islem), sozcukler(e.tibbi_islem));
      return { benzerlik: o.benzerlik, ortak: o.benzerlik > 0 && e.tibbi_islem ? [e.tibbi_islem] : [] };
    })(),
    tibbi_olay: kumeOrtusmesi(hedef.etiketler.tibbi_olay, e.tibbi_olay),
    hastada_olusan_zarar: kumeOrtusmesi(hedef.etiketler.hastada_olusan_zarar, e.hastada_olusan_zarar),
    iddia_edilen_kusur: kumeOrtusmesi(hedef.etiketler.iddia_edilen_kusur, e.iddia_edilen_kusur),
    uygulanan_yontem: kumeOrtusmesi(hedef.etiketler.uygulanan_yontem, e.uygulanan_yontem),
    tibbi_surec: kumeOrtusmesi(hedef.etiketler.tibbi_surec, e.tibbi_surec),
    yargi_yolu: esit(hedef.etiketler.yargi_yolu, e.yargi_yolu, true),
  };
  const bilesenler: Bilesen[] = BILESENLER.map((b) => ({ ad: b.ad, agirlik: b.agirlik, ...olcum[b.ad] }));
  const katki = (b: Bilesen) => b.agirlik * b.benzerlik;
  const puan = Math.round(bilesenler.reduce((t, b) => t + katki(b), 0) * 10) / 10;
  const gerekce = bilesenler
    .filter((b) => katki(b) > 0)
    .sort((a, b) => katki(b) - katki(a))
    .map((b) => (b.ortak.length > 0 ? `${bilesenAdi(b.ad)}: ${b.ortak.join(", ")}` : `aynı ${bilesenAdi(b.ad)}`))
    .join(" · ");
  return { kayit, puan, bilesenler, gerekce };
}

function hedefOlustur(caseId: number, sirket: LexisSirket | null, raporTuru: RaporTuru): PuanHedefi {
  const dosya = dosyaBul(caseId);
  return { sirket, rapor_turu: raporTuru, uzmanlik: dosya.uzmanlik, etiketler: ORNEK_HEDEF_ETIKETLER[caseId] };
}

/** Raf listesinin satırı: ayrıntıdan metin, parçalar ve yalnız ayrıntıda gelen alanlar atılır. */
const AYRINTI_ALANLARI = ["metin", "parcalar", "kunye_kaynak", "vekalet_ucreti", "yargilama_gideri", "hukum_kaynagi", "yas", "davaci_sayisi"] as const;

function rafOzeti(karar: RafKarariAyrinti): RafKarari {
  const ozet: Record<string, unknown> = { ...karar };
  for (const alan of AYRINTI_ALANLARI) delete ozet[alan];
  return ozet as unknown as RafKarari;
}

function kararBankasiKur(): KararKaydi[] {
  const banka = new Map<string, KararKaydi>();
  for (const kayit of ORNEK_KUTUPHANE) {
    for (const karar of kayit.okuma.kararlar) {
      const anahtar = `${karar.merci ?? ""}|${karar.esas_no}|${karar.karar_no}`;
      const mevcut = banka.get(anahtar);
      if (mevcut) {
        mevcut.raporlar.push(kayit.okuma.sha256);
        mevcut.emsal = mevcut.emsal || karar.emsal;
      } else {
        banka.set(anahtar, { ...karar, raporlar: [kayit.okuma.sha256] });
      }
    }
  }
  return [...banka.values()];
}

const ornekLexisApi: LexisApi = {
  async davaAra(sorgu, signal) {
    await bekle(signal, 0.5);
    const anahtar = katla(sorgu);
    if (!anahtar) return kopya(ORNEK_DAVALAR);
    return kopya(
      ORNEK_DAVALAR.filter((d) =>
        [d.ofis_no, d.mahkeme, d.esas_no, d.hasar_no, d.dosya_no, d.sigortali, d.karsi_taraf].some((alan) => alan && katla(alan).includes(anahtar)),
      ),
    );
  },

  async dosyaGetir(caseId, signal) {
    await bekle(signal);
    return kopya(dosyaBul(caseId));
  },

  async emsalOner(istek, signal) {
    await bekle(signal);
    const dosya = dosyaBul(istek.case_id);
    const hedef = hedefOlustur(istek.case_id, istek.sirket, istek.rapor_turu);
    // Dosyanın kendi eski raporu emsal değildir (çekirdekte `haric_dosya_no`); ek raporda ayrıca girdidir.
    return kopya(
      ORNEK_KUTUPHANE.filter((k) => k.dosya_no !== dosya.dava.dosya_no)
        .map((k) => puanla(hedef, k))
        .sort((a, b) => b.puan - a.puan)
        .slice(0, istek.k ?? 3),
    );
  },

  async emsalPuanla(caseId, sha256, signal) {
    await bekle(signal, 0.5);
    const dosya = dosyaBul(caseId);
    return kopya(puanla(hedefOlustur(caseId, dosya.sirket, dosya.rapor_turu), kayitBul(sha256)));
  },

  async *taslakYaz(istek, signal) {
    const icerik = ORNEK_TASLAKLAR[istek.case_id];
    const dosya = ORNEK_DOSYALAR[istek.case_id];
    if (!icerik || !dosya) {
      yield { status: "failed", error_ozet: "Bu dava için taslak üretilemedi.", error_kod: "analysis_error" };
      return;
    }
    yield { status: "info", asama: "olgular", mesaj: `${istek.belge_idleri.length} belge okunuyor` };
    await bekle(signal, 2);
    yield { status: "info", asama: "emsaller", mesaj: `${istek.emsal_sha.length} emsal rapor hazırlanıyor` };
    await bekle(signal);
    yield { status: "info", asama: "bolumler", mesaj: "Bölümler yazılıyor" };
    for (const tanim of ISKELET_BOLUMLERI[istek.iskelet]) {
      await bekle(signal, tanim.tur === "ETIKETLI" ? 1 : 2);
      if (tanim.tur === "ETIKETLI") {
        yield { status: "bolum", bolum: tanim.kod, etiketli: kopya(icerik.etiketli[tanim.kod] ?? []) };
      } else if (tanim.tur === "OZET") {
        yield { status: "bolum", bolum: tanim.kod, ozet: kopya(icerik.ozet[tanim.kod] ?? []) };
      } else {
        yield { status: "bolum", bolum: tanim.kod, degerlendirme: kopya(icerik.degerlendirme) };
      }
    }
    yield { status: "info", asama: "muallak", mesaj: "Muallak önerisi hesaplanıyor" };
    await bekle(signal);
    yield { status: "muallak", oneri: kopya(icerik.muallak) };
    yield { status: "info", asama: "denetim", mesaj: "Dayanaklar ve atıflar denetleniyor" };
    await bekle(signal);

    const taslak: LexisTaslak = {
      case_id: istek.case_id,
      sirket: istek.sirket,
      rapor_turu: istek.rapor_turu,
      iskelet: istek.iskelet,
      etiketli: icerik.etiketli,
      ozet: icerik.ozet,
      degerlendirme: icerik.degerlendirme,
      muallak: icerik.muallak,
      muallak_maddi: null,
      muallak_manevi: null,
      emsaller: istek.emsal_sha,
    };
    const uyarilar = await ornekLexisApi.denetle(taslak);
    durum.kosuSayaci += 1;
    const kosu: TaslakKosusu = {
      id: `kosu-${String(durum.kosuSayaci).padStart(4, "0")}`,
      tarih: new Date().toISOString(),
      kullanici: "siz",
      case_id: istek.case_id,
      ofis_no: dosya.dava.ofis_no,
      sirket: istek.sirket,
      rapor_turu: istek.rapor_turu,
      iskelet: istek.iskelet,
      emsal_sayisi: istek.emsal_sha.length,
      uyari_sayisi: uyarilar.length,
      indirme_tarihi: null,
    };
    durum.gecmis = [kosu, ...durum.gecmis];
    yield { status: "complete", kosu_id: kosu.id, uyarilar };
  },

  async denetle(taslak, signal) {
    if (signal?.aborted) throw iptalHatasi();
    const emsalMetinleri = taslak.emsaller.map((sha) => {
      const kayit = ORNEK_KUTUPHANE.find((k) => k.okuma.sha256 === sha);
      return kayit ? kayitMetni(kayit) : "";
    });
    return ornekDenetle({ taslak, dosya: dosyaBul(taslak.case_id), emsalMetinleri, kararBankasi: kararBankasiKur() });
  },

  // Örnek kipte tutar yeniden hesaplanmaz: örnek öneri seçilen sınıflarla döner.
  async muallakOner(istek, signal) {
    await bekle(signal, 0.5);
    const oneri = ORNEK_TASLAKLAR[istek.case_id]?.muallak;
    if (!oneri) throw new LexisApiError(404, "Bu dava için muallak önerisi yok.");
    return kopya({ ...oneri, kusur_tespiti: istek.kusur_tespiti, risk_duzeyi: istek.risk_duzeyi, teminat: istek.teminat });
  },

  // Word örnek modda da GERÇEK servise gider: örnek taslak + örnek dosyanın künyesi. Modül dinamik yüklenir —
  // adaptörün geri kalanı `apiClient`'ı (MSAL) hiç yüklemez.
  async wordIndir(taslak, signal) {
    const dosya = dosyaBul(taslak.case_id);
    const { wordIndir } = await import("@/lib/lexisWord");
    const sonuc = await wordIndir(taslak, { hasar_no: dosya.hasar_no, rapor_no: dosya.dava.dosya_no }, signal);
    // Geçmiş en yeni koşu başta tutulur: bu davanın son koşusu "Word indirildi" olur.
    const kosu = durum.gecmis.find((k) => k.case_id === taslak.case_id);
    if (kosu) kosu.indirme_tarihi = new Date().toISOString();
    return sonuc;
  },

  async gecmis(signal) {
    await bekle(signal);
    return kopya(durum.gecmis);
  },

  async kutuphaneAra(filtre, signal) {
    await bekle(signal, 0.5);
    const metin = katla(filtre.metin ?? "");
    return kopya(
      ORNEK_KUTUPHANE.filter((k) => {
        const { okuma, etiketler } = k;
        if (filtre.sirket && okuma.sirket !== filtre.sirket) return false;
        if (filtre.rapor_turu && okuma.rapor_turu !== filtre.rapor_turu) return false;
        if (filtre.iskelet && okuma.iskelet !== filtre.iskelet) return false;
        if (filtre.uzmanlik && (etiketler.uzmanlik ?? okuma.uzmanlik) !== filtre.uzmanlik) return false;
        if (filtre.kusur_tespiti && etiketler.kusur_tespiti !== filtre.kusur_tespiti) return false;
        if (filtre.risk_duzeyi && etiketler.risk_duzeyi !== filtre.risk_duzeyi) return false;
        if (!metin) return true;
        const aranan = [kayitMetni(k), etiketler.iddia_ozeti, etiketler.tibbi_islem, okuma.rapor_no, okuma.mahkeme, ...etiketler.tibbi_olay];
        return aranan.some((alan) => alan && katla(alan).includes(metin));
      }),
    );
  },

  async raporGetir(sha256, signal) {
    await bekle(signal, 0.5);
    return kopya(kayitBul(sha256));
  },

  async kararBankasi(signal) {
    await bekle(signal, 0.5);
    return kararBankasiKur();
  },

  // Örnek raf: uydurma üç karar. Yazım örnek kipte hep kapalıdır (örnek taslak hazır gelir, model çağrılmaz).
  async kararAra(suzgec, signal) {
    await bekle(signal, 0.5);
    const aranan = katla(suzgec.metin ?? "");
    const uyan = ORNEK_KARARLAR.filter(
      (k) =>
        (!suzgec.belge_turu || k.belge_turu === suzgec.belge_turu) &&
        (!suzgec.derece || k.derece === suzgec.derece) &&
        (!suzgec.hukum_sinifi || k.hukum_sinifi === suzgec.hukum_sinifi) &&
        (!suzgec.sonuc_muvekkil || k.sonuc_muvekkil === suzgec.sonuc_muvekkil) &&
        (!suzgec.uzmanlik || k.uzmanlik === suzgec.uzmanlik) &&
        (!suzgec.konu || (k.konular[suzgec.konu] ?? 0) > 0) &&
        (!suzgec.yalniz_kartli || k.kart_id !== null) &&
        (!aranan || [k.mahkeme, k.esas_no, k.karar_no, k.uzmanlik, k.metin].some((alan) => alan && katla(alan).includes(aranan))),
    ).sort((a, b) => (b.karar_tarihi ?? "").localeCompare(a.karar_tarihi ?? ""));
    const bas = suzgec.offset ?? 0;
    return { toplam: uyan.length, kararlar: kopya(uyan.slice(bas, bas + (suzgec.limit ?? 50)).map(rafOzeti)) };
  },

  async rafSecenekleri(signal) {
    await bekle(signal, 0.5);
    const tekil = (alan: "derece" | "uzmanlik" | "belge_turu" | "hukum_sinifi" | "sonuc_muvekkil") =>
      [...new Set(ORNEK_KARARLAR.map((k) => k[alan]).filter((d): d is string => !!d))].sort((a, b) => a.localeCompare(b, "tr"));
    return { derece: tekil("derece"), uzmanlik: tekil("uzmanlik"), belge_turu: tekil("belge_turu"), hukum_sinifi: tekil("hukum_sinifi"), sonuc_muvekkil: tekil("sonuc_muvekkil") };
  },

  async kartKararlari(caseId, signal) {
    await bekle(signal, 0.5);
    const kararlar = ORNEK_KARARLAR.filter((k) => k.kart_id === caseId).sort((a, b) => (b.karar_tarihi ?? "").localeCompare(a.karar_tarihi ?? ""));
    return { kararlar: kopya(kararlar.map(rafOzeti)), yazim: { acik: false, neden: "ornek", model: null } };
  },

  async kararGetir(id, signal) {
    await bekle(signal, 0.5);
    const karar = ORNEK_KARARLAR.find((k) => k.id === id);
    if (!karar) throw new LexisApiError(404, "Karar rafta bulunamadı.");
    return kopya(karar);
  },

  async kartBaglari(signal) {
    await bekle(signal);
    return kopya(durum.baglar);
  },

  async kartSec(rapor, kartId, signal) {
    await bekle(signal, 0.5);
    const satir = durum.baglar.find((b) => b.rapor === rapor);
    if (!satir) throw new LexisApiError(404, "Rapor bulunamadı.");
    if (kartId !== null && !satir.bag.adaylar.some((a) => a.kart.kart_id === kartId)) {
      throw new LexisApiError(422, "Seçilen kart adaylar arasında değil.");
    }
    satir.bag.birincil = kartId;
    satir.bag.insan_secimi = kartId !== null;
    return kopya(satir);
  },

  async profiller(signal) {
    await bekle(signal);
    return kopya(durum.profiller);
  },

  async profilKaydet(profil, signal) {
    await bekle(signal, 0.5);
    const kayit: SirketProfili = { ...kopya(profil), guncelleme: new Date().toISOString().slice(0, 10) };
    const sira = durum.profiller.findIndex((p) => p.sirket_kodu === profil.sirket_kodu);
    if (sira >= 0) durum.profiller[sira] = kayit;
    else durum.profiller.push(kayit);
    return kopya(kayit);
  },

  // Örnek kipte taslak saklanmaz (sayfa yenilenince gider); tezgâh `kalici`ye bakıp kayıt akışını hiç başlatmaz.
  kalici: false,
  async taslakGetir() {
    return null;
  },
  async taslakKaydet() {
    return null;
  },
  async taslakSil() {},
};

// ---------------------------------------------------------------------------------------------
// Veri kipi: örnek (varsayılan) ya da gerçek dava
// ---------------------------------------------------------------------------------------------

/**
 * `ornek`: her şey bellekteki sentetik veriden; hiçbir şey kaydedilmez. `gercek`: beş sekmenin tamamı Lexis
 * servisinden gelir (`lib/lexisServis.ts`). "Taslağı yaz" iskelet üretir (künye karttan, özet boş — modele bir şey
 * gitmez), muallak sınıfları insan seçer, Word gerçek servisten iner; denetim buradaki `lexisDenetim` ile koşar.
 * Taslak, koşu geçmişi, kart seçimi ve şirket profili servisin KENDİ veritabanında saklanır (`kalici`). Kipi sayfa
 * seçer (`LexisPage`, `?veri=gercek`).
 */
export type VeriKipi = "ornek" | "gercek";

let kip: VeriKipi = "ornek";

export function veriKipi(): VeriKipi {
  return kip;
}

export function veriKipiAyarla(yeni: VeriKipi): void {
  kip = yeni;
}

/** Gerçek davada karar seçilmeden (ya da yazım kapalıyken) "Taslağı yaz"ın ne ürettiği — düğmenin üstünde ve onay kutusunda gösterilir. */
export const GERCEK_ISKELET_NOTU =
  "Gerçek davada taslak iskelet olarak gelir: künye dava kartından dolar, özet bölümlerini ve maddeleri siz yazarsınız. Modele hiçbir şey gönderilmez.";

/** Gerçek davada karar seçiliyken "Taslağı yaz"ın ne yaptığı — gönderim onayında gösterilir (K4). */
export const GERCEK_YAZIM_NOTU =
  "Künye dava kartından dolar. Seçili kararların metni kişi adları maskelenerek, emsal raporların maskeli bölümleriyle birlikte modele gönderilir; iddia / yargı süreci özeti ve değerlendirme maddeleri bu kararlardan yazılır. Her madde karardan alıntıyla dayanak gösterir; muallak tutarını kod hesaplar.";

// Gerçek kipin oturum belleği: denetim ve Word, seçili davanın kartını ve bakılan emsallerin metnini ister.
const gercekDosyalar = new Map<number, DosyaGirdisi>();
const gercekEmsalMetinleri = new Map<string, string>();
// Dava → taslağının koşusu (Geçmiş satırı): iskelet yanıtından ya da kayıtlı taslaktan öğrenilir; kayıt ve Word taşır.
const gercekKosular = new Map<number, number>();
// Karar kimliği → metin: denetim, dayanak alıntısını taslağın yazıldığı kararlarda arar.
const gercekKararMetinleri = new Map<number, string>();
let gercekKararBankasi: KararKaydi[] | null = null;

// Dinamik: örnek kip `apiClient`'ı (MSAL) hiç yüklemez. Yükleme TEK kez başlatılır ve paylaşılır: dava seçilince
// birkaç istek aynı anda yola çıkar (dosya, emsal, kararlar); başarısız yükleme (parça alınamadı) yeniden denenir.
let servisModulu: Promise<typeof import("@/lib/lexisServis")> | null = null;
const servis = () =>
  (servisModulu ??= import("@/lib/lexisServis").catch((e: unknown) => {
    servisModulu = null;
    throw e;
  }));

async function gercekDosya(caseId: number, signal?: AbortSignal): Promise<DosyaGirdisi> {
  const bellekte = gercekDosyalar.get(caseId);
  if (bellekte) return bellekte;
  const dosya = await (await servis()).dosyaGetir(caseId, signal);
  gercekDosyalar.set(caseId, dosya);
  return dosya;
}

/**
 * Taslağın yazıldığı kararların metni (kimlik → metin), oturum belleğinden ya da servisten. Alınamayan karar haritaya
 * girmez: denetim o kararın paragrafını atlar (yanlış "alıntı bulunamadı" vermez).
 */
async function gercekKaynakMetinleri(taslak: LexisTaslak, signal?: AbortSignal): Promise<Record<number, string>> {
  const sonuc: Record<number, string> = {};
  await Promise.all(
    (taslak.kararlar ?? []).map(async (id) => {
      let metin = gercekKararMetinleri.get(id);
      if (metin === undefined) {
        try {
          metin = kararKaynakMetni(await (await servis()).kararGetir(id, signal));
        } catch (e) {
          if ((e as Error)?.name === "AbortError") throw e;
          return;
        }
        gercekKararMetinleri.set(id, metin);
      }
      sonuc[id] = metin;
    }),
  );
  return sonuc;
}

async function gercekDenetle(taslak: LexisTaslak, signal?: AbortSignal): Promise<LexisUyari[]> {
  const dosya = await gercekDosya(taslak.case_id, signal);
  // Karar bankası alınamazsa denetim yine koşar: atıflar yalnız dosya metninde aranır.
  gercekKararBankasi ??= await (await servis()).kararBankasi(signal).catch(() => null);
  const emsalMetinleri = taslak.emsaller.map((sha) => gercekEmsalMetinleri.get(sha) ?? "");
  const kaynakMetinleri = await gercekKaynakMetinleri(taslak, signal);
  return ornekDenetle({ taslak, dosya, emsalMetinleri, kararBankasi: gercekKararBankasi ?? [], kaynakMetinleri });
}

const gercekLexisApi: LexisApi = {
  ...ornekLexisApi,
  async davaAra(sorgu, signal) {
    return (await servis()).davaAra(sorgu, signal);
  },
  async dosyaGetir(caseId, signal) {
    const dosya = await (await servis()).dosyaGetir(caseId, signal);
    gercekDosyalar.set(caseId, dosya);
    return dosya;
  },
  async emsalOner(istek, signal) {
    const emsaller = await (await servis()).emsalOner(istek, signal);
    for (const e of emsaller) gercekEmsalMetinleri.set(e.kayit.okuma.sha256, kayitMetni(e.kayit));
    return emsaller;
  },
  // Elle eklenen emsal dosyanın kartına göre puanlanır; metni denetim için belleğe alınır.
  async emsalPuanla(caseId, sha256, signal) {
    const dosya = await gercekDosya(caseId, signal);
    const emsal = await (await servis()).emsalPuanla({ case_id: caseId, sha256, sirket: dosya.sirket, rapor_turu: dosya.rapor_turu }, signal);
    gercekEmsalMetinleri.set(sha256, kayitMetni(emsal.kayit));
    return emsal;
  },
  async kutuphaneAra(filtre, signal) {
    return (await servis()).kutuphaneAra(filtre, signal);
  },
  async raporGetir(sha256, signal) {
    return (await servis()).raporGetir(sha256, signal);
  },
  async kararBankasi(signal) {
    return (await servis()).kararBankasi(signal);
  },
  // Önce İSKELET: etiketli satırlar karttan, son madde koddan (modele bir şey gitmez). Karar seçildiyse ARDINDAN
  // kararlardan yazım: iddia / yargı süreci ve değerlendirme modelden gelir (kararlar maskeli gider; onayı tezgâh
  // alır). Yazım başarısız olursa iskelet ekranda kalır, hata `warning` olayıyla bildirilir.
  async *taslakYaz(istek, signal) {
    yield { status: "info", asama: "olgular", mesaj: "Künye dava kartından dolduruluyor" };
    let iskelet: Awaited<ReturnType<Awaited<ReturnType<typeof servis>>["iskelet"]>>;
    try {
      iskelet = await (await servis()).iskelet(istek, signal);
    } catch (e) {
      if ((e as Error)?.name === "AbortError") throw e;
      yield { status: "failed", error_ozet: e instanceof LexisApiError ? e.message : LEXIS_GENEL_HATA, error_kod: "analysis_error" };
      return;
    }
    if (iskelet.kosu_id != null) gercekKosular.set(istek.case_id, iskelet.kosu_id);
    else gercekKosular.delete(istek.case_id); // veritabanı yok: koşu loglanmadı, eski koşuya da yazılmasın
    const bolumler = ISKELET_BOLUMLERI[istek.iskelet];
    for (const tanim of bolumler) {
      if (tanim.tur === "ETIKETLI") yield { status: "bolum", bolum: tanim.kod, etiketli: iskelet.etiketli[tanim.kod] ?? [] };
    }

    const kararIdleri = istek.karar_idleri ?? [];
    let yazim: YazimSonucu | null = null;
    if (kararIdleri.length > 0) {
      yield { status: "info", asama: "bolumler", mesaj: `${kararIdleri.length} karar maskelenip modele gönderiliyor; özet ve değerlendirme yazılıyor` };
      try {
        yazim = await (await servis()).yaz({ ...istek, karar_idleri: kararIdleri }, signal);
      } catch (e) {
        if ((e as Error)?.name === "AbortError") throw e;
        yield { status: "warning", mesaj: `Kararlardan yazım yapılamadı: ${e instanceof LexisApiError ? e.message : LEXIS_GENEL_HATA} Taslak iskelet olarak bırakıldı.` };
      }
    } else {
      yield { status: "info", asama: "bolumler", mesaj: "Bölümler hazırlanıyor" };
    }
    const ozet = { ...iskelet.ozet, ...(yazim?.ozet ?? {}) };
    const degerlendirme = yazim?.degerlendirme ?? iskelet.degerlendirme;
    const muallak = yazim?.muallak ?? iskelet.muallak;
    for (const tanim of bolumler) {
      if (tanim.tur === "OZET") yield { status: "bolum", bolum: tanim.kod, ozet: ozet[tanim.kod] ?? [] };
      else if (tanim.tur === "MUHAKEME") yield { status: "bolum", bolum: tanim.kod, degerlendirme };
    }
    yield { status: "info", asama: "muallak", mesaj: "Muallak önerisi hesaplanıyor" };
    yield { status: "muallak", oneri: muallak };
    yield { status: "info", asama: "denetim", mesaj: "Taslak denetleniyor" };
    const taslak: LexisTaslak = {
      case_id: istek.case_id,
      sirket: istek.sirket,
      rapor_turu: istek.rapor_turu,
      iskelet: istek.iskelet,
      etiketli: iskelet.etiketli,
      ozet,
      degerlendirme,
      muallak,
      muallak_maddi: null,
      muallak_manevi: null,
      emsaller: istek.emsal_sha,
      kararlar: kararIdleri,
    };
    yield { status: "complete", kosu_id: iskelet.kosu_id != null ? String(iskelet.kosu_id) : `iskelet-${istek.case_id}`, uyarilar: await gercekDenetle(taslak, signal) };
  },
  async kararAra(suzgec, signal) {
    return (await servis()).kararAra(suzgec, signal);
  },
  async rafSecenekleri(signal) {
    return (await servis()).rafSecenekleri(signal);
  },
  async kartKararlari(caseId, signal) {
    return (await servis()).kartKararlari(caseId, signal);
  },
  async kararGetir(id, signal) {
    const karar = await (await servis()).kararGetir(id, signal);
    gercekKararMetinleri.set(id, kararKaynakMetni(karar));
    return karar;
  },
  async denetle(taslak, signal) {
    if (signal?.aborted) throw iptalHatasi();
    return gercekDenetle(taslak, signal);
  },
  async muallakOner(istek, signal) {
    return (await servis()).muallakOner(istek, signal);
  },
  async wordIndir(taslak, signal) {
    const dosya = await gercekDosya(taslak.case_id, signal);
    const { wordIndir } = await import("@/lib/lexisWord");
    const kosu = gercekKosular.get(taslak.case_id);
    return wordIndir(taslak, { hasar_no: dosya.hasar_no, hukuk_no: dosya.hukuk_no, rapor_no: dosya.dava.dosya_no, ...(kosu != null ? { kosu_id: kosu } : {}) }, signal);
  },

  // --- kalıcılık: servisin kendi veritabanı ---
  kalici: true,
  async taslakGetir(caseId, signal) {
    const kayit = await (await servis()).taslakGetir(caseId, signal);
    if (kayit?.kosu_id != null) gercekKosular.set(caseId, kayit.kosu_id);
    return kayit;
  },
  async taslakKaydet(caseId, kayit, signal) {
    return (await servis()).taslakKaydet(caseId, { ...kayit, kosu_id: gercekKosular.get(caseId) ?? null }, signal);
  },
  async taslakSil(caseId, signal) {
    await (await servis()).taslakSil(caseId, signal);
    gercekKosular.delete(caseId);
  },
  async gecmis(signal) {
    return (await servis()).gecmis(signal);
  },
  async kartBaglari(signal) {
    return (await servis()).kartBaglari(signal);
  },
  async kartSec(rapor, kartId, signal) {
    return (await servis()).kartSec(rapor, kartId, signal);
  },
  async profiller(signal) {
    return (await servis()).profiller(signal);
  },
  async profilKaydet(profil, signal) {
    return (await servis()).profilKaydet(profil, signal);
  },
};

/** Sayfanın tek kapısı: her çağrı o anki kipin adaptörüne gider. */
export const lexisApi: LexisApi = new Proxy(ornekLexisApi, {
  get: (_hedef, ad) => (kip === "gercek" ? gercekLexisApi : ornekLexisApi)[ad as keyof LexisApi],
});
