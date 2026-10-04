// Lexis istemcisi — `/lexis` sayfası araca YALNIZ bununla konuşur (`lib/hukukbotApi.ts` deseni).
//
// BUGÜN: çekirdek ayrı depoda (`lexis-rapor`) ve yalnız Word ucu var. `lexisApi` bellekte çalışan ÖRNEK
// adaptördür (`lib/lexisOrnekVeri.ts`, sentetik veri) — sayfa yenilenince durum sıfırlanır. `ORNEK_VERI` bayrağı
// sayfadaki "Örnek veri" şeridini sürer. TEK ağ isteği Word'dür: `wordIndir` örnek taslağı gerçek servise
// (`lib/lexisWord.ts` → `/lexis-api/word`) gönderir, gerçek şirket şablonunda dosya döner.
//
// ENTEGRASYON: `LexisApi` arayüzü sözleşmedir. Gerçek adaptör aynı arayüzü `apiClient.fetch` ile uygular
// (`taslakYaz` NDJSON akışı için `hukukbotApi.ask` okuyucusu), `lexisApi` ona bağlanır, `ORNEK_VERI` false olur;
// örnek veri, `lexisDenetim.ts` ve buradaki puanlama KALKAR.
import { denetle as ornekDenetle } from "@/lib/lexisDenetim";
import { katla } from "@/lib/lexisMetin";
import type { WordSonucu } from "@/lib/lexisWord";
import {
  ORNEK_DAVALAR,
  ORNEK_DOSYALAR,
  ORNEK_GECMIS,
  ORNEK_HEDEF_ETIKETLER,
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
  type KutuphaneFiltresi,
  type KutuphaneKaydi,
  type LexisAkisOlayi,
  type LexisDava,
  type LexisSirket,
  type LexisTaslak,
  type LexisUyari,
  type RaporBagi,
  type RaporEtiketleri,
  type RaporTuru,
  type SirketProfili,
  type TaslakIstegi,
  type TaslakKosusu,
} from "@/types/lexis";

/** Sayfa örnek veriyle mi çalışıyor — entegrasyonda false. */
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
  /** Şirket şablonunu doldurup Word'ü indirir; şablon yazımının uyarılarıyla döner. */
  wordIndir(taslak: LexisTaslak, signal?: AbortSignal): Promise<WordSonucu>;
  gecmis(signal?: AbortSignal): Promise<TaslakKosusu[]>;
  kutuphaneAra(filtre: KutuphaneFiltresi, signal?: AbortSignal): Promise<KutuphaneKaydi[]>;
  raporGetir(sha256: string, signal?: AbortSignal): Promise<KutuphaneKaydi>;
  kararBankasi(signal?: AbortSignal): Promise<KararKaydi[]>;
  /** `TEK` dışındaki bağlar (inceleme listesi). */
  kartBaglari(signal?: AbortSignal): Promise<RaporBagi[]>;
  /** İnsan seçimi (K8); `kartId = null` seçimi geri alır. */
  kartSec(rapor: string, kartId: number | null, signal?: AbortSignal): Promise<RaporBagi>;
  profiller(signal?: AbortSignal): Promise<SirketProfili[]>;
  profilKaydet(profil: SirketProfili, signal?: AbortSignal): Promise<SirketProfili>;
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
};

export const lexisApi: LexisApi = ornekLexisApi;
