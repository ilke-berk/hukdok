// Lexis bileşenlerinin ortak saf yardımcıları (durum türetme, dayanak arama, kimlikler).
import { alintiAraliklari, tutarYaz, type MetinAraligi } from "@/lib/lexisMetin";
import { LexisApiError } from "@/lib/lexisApi";
import {
  SIRKET_ADLARI,
  type BolumKodu,
  type LexisTaslak,
  type LexisUyari,
  type Madde,
  type RaporOkuma,
  type UyariKodu,
  type UyariSeviyesi,
} from "@/types/lexis";

/** Raporun tek satırlık künyesi: şirket · tür · yıl. */
export function raporKunyesi(okuma: Pick<RaporOkuma, "sirket" | "rapor_turu" | "rapor_tarihi">): string {
  return [okuma.sirket ? SIRKET_ADLARI[okuma.sirket] : null, okuma.rapor_turu === "EK" ? "Ek rapor" : "Ana rapor", okuma.rapor_tarihi?.slice(0, 4)]
    .filter(Boolean)
    .join(" · ");
}

/** Raporun muallağı tek satırda; ikisi de boşsa `null`. */
export function muallakOzeti(okuma: Pick<RaporOkuma, "muallak_maddi" | "muallak_manevi">): string | null {
  const parcalar = [
    okuma.muallak_maddi !== null && `maddi ${tutarYaz(okuma.muallak_maddi)}`,
    okuma.muallak_manevi !== null && `manevi ${tutarYaz(okuma.muallak_manevi)}`,
  ].filter(Boolean);
  return parcalar.length > 0 ? parcalar.join(" · ") : null;
}

/**
 * Metin bağlantısı / bağlantı görünümlü düğme. Yazı `--fg`, alt çizgi bordo: koyu temada kurumsal bordo yazı
 * okunmuyor (25.09 kararıyla bordo aynen korunur; kontrast 1.66:1) — işlevsel metin bu yüzden bordo yazılmaz.
 */
export const BAGLANTI_SINIFI =
  "text-[var(--fg)] underline decoration-[var(--brand)] decoration-1 underline-offset-[3px] hover:decoration-2 disabled:opacity-50";

export const iptalMi =(e: unknown): boolean => e instanceof DOMException && e.name === "AbortError";

export function hataMetni(e: unknown, yedek = "İstek tamamlanamadı."): string {
  if (e instanceof LexisApiError) return e.message;
  return e instanceof Error && e.message ? e.message : yedek;
}

/** Kaydırma hedefleri — uyarıya tıklanınca ilgili yere gidilir. */
export const bolumKimligi = (kod: BolumKodu) => `lexis-bolum-${kod}`;
export const maddeKimligi = (sira: number) => `lexis-madde-${sira}`;
export const alanKimligi = (bolum: BolumKodu, alan: string) => `lexis-alan-${bolum}-${alan}`;

/** Uyarının götürdüğü öğenin kimliği: madde → etiketli satır → bölüm. */
export function uyariHedefi(u: LexisUyari): string | null {
  if (u.madde !== null) return maddeKimligi(u.madde);
  if (u.bolum && u.alan) return alanKimligi(u.bolum, u.alan);
  return u.bolum ? bolumKimligi(u.bolum) : null;
}

export type RozetTonu = "ok" | "danger" | "caution" | "muted";

export interface MaddeRozeti {
  kod: UyariKodu | "DOGRULANDI" | "KALIP" | "DENETLENMEDI";
  ad: string;
  ton: RozetTonu;
}

const UYARI_ROZET_ADLARI: Partial<Record<UyariKodu, string>> = {
  DAYANAKSIZ: "Dayanaksız",
  ALINTI_KISA: "Alıntı çok kısa",
  ALINTI_BULUNAMADI: "Alıntı dosyada yok",
  EMSALDEN_TASINMA: "Emsalden taşınma",
  BELGE_YOKLUGU: "Belge yokluğu iddiası",
  KALIP_YERI: "Kalıp yanlış yerde",
  ATIF_DOGRULANAMADI: "Atıf doğrulanamadı",
  DOLDURULMAMIS: "Doldurulmamış yer",
  MASKE_KALINTISI: "Maske kalıntısı",
};

export const seviyeTonu = (seviye: UyariSeviyesi): RozetTonu => (seviye === "HATA" ? "danger" : seviye === "UYARI" ? "caution" : "muted");

/**
 * Madde kartının rozetleri. `degisti`: madde son denetimden sonra düzenlendi → eski sonuç gösterilmez.
 * Uyarısız TESPIT maddesi "Doğrulandı"dır (alıntı dosyada bulundu); KALIP maddesi dayanak istemez.
 */
export function maddeRozetleri(madde: Madde, uyarilar: LexisUyari[], degisti: boolean): MaddeRozeti[] {
  if (degisti) return [{ kod: "DENETLENMEDI", ad: "Denetlenmedi", ton: "muted" }];
  const rozetler: MaddeRozeti[] = uyarilar.map((u) => ({ kod: u.kod, ad: UYARI_ROZET_ADLARI[u.kod] ?? u.kod, ton: seviyeTonu(u.seviye) }));
  if (madde.tur === "KALIP") return [{ kod: "KALIP", ad: "Kalıp", ton: "muted" }, ...rozetler];
  return rozetler.length > 0 ? rozetler : [{ kod: "DOGRULANDI", ad: "Doğrulandı", ton: "ok" }];
}

export interface DayanakKonumu {
  bolum: BolumKodu;
  paragraf: number;
  metin: string;
  araliklar: MetinAraligi[];
}

/**
 * Alıntının taslaktaki yeri: önce maddenin gösterdiği bölümde, sonra diğer özet bölümlerde aranır (çekirdek de
 * `dayanak_bolum`'u bilgi sayar, alıntıyı dosyanın bütün metninde arar). Bulunamazsa `null`.
 */
export function dayanakBul(taslak: LexisTaslak, madde: Madde): DayanakKonumu | null {
  const alinti = madde.dayanak_alinti?.trim();
  if (!alinti) return null;
  const kodlar = Object.keys(taslak.ozet) as BolumKodu[];
  const sirali = madde.dayanak_bolum ? [madde.dayanak_bolum, ...kodlar.filter((k) => k !== madde.dayanak_bolum)] : kodlar;
  for (const bolum of sirali) {
    const paragraflar = taslak.ozet[bolum] ?? [];
    for (let i = 0; i < paragraflar.length; i += 1) {
      const araliklar = alintiAraliklari(paragraflar[i].metin, alinti);
      if (araliklar) return { bolum, paragraf: i, metin: paragraflar[i].metin, araliklar };
    }
  }
  return null;
}

/** Metni vurgu aralıklarına göre parçalar: `{metin, vurgulu}` dizisi. */
export function vurguParcalari(metin: string, araliklar: MetinAraligi[]): { metin: string; vurgulu: boolean }[] {
  const parcalar: { metin: string; vurgulu: boolean }[] = [];
  let konum = 0;
  for (const a of araliklar) {
    if (a.bas > konum) parcalar.push({ metin: metin.slice(konum, a.bas), vurgulu: false });
    parcalar.push({ metin: metin.slice(a.bas, a.son), vurgulu: true });
    konum = a.son;
  }
  if (konum < metin.length) parcalar.push({ metin: metin.slice(konum), vurgulu: false });
  return parcalar;
}

/** Bölüm başına uyarı sayısı (gezgin rozetleri). */
export function bolumUyariSayilari(uyarilar: LexisUyari[]): Partial<Record<BolumKodu, number>> {
  const sayilar: Partial<Record<BolumKodu, number>> = {};
  for (const u of uyarilar) if (u.bolum) sayilar[u.bolum] = (sayilar[u.bolum] ?? 0) + 1;
  return sayilar;
}
