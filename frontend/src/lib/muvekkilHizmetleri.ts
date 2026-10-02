import { foldTr } from "@/lib/aramaKatlama";

// =====================================================================
// Müvekkil başına hizmet seçimi (G253) — yeni dava formu, dava açma sihirbazı
// ve hızlı dava modalının ORTAK saf yardımcıları.
//
// Kart açılırken her müvekkil KENDİ hizmet kümesiyle gider
// (`parties[i].hizmet_turleri`, backend G250). Kural backend'inkiyle aynıdır
// (`case_manager._taraf_hizmetlerini_dogrula`):
//   - kullanıcı yolunda hizmeti olmayan müvekkille kart AÇILMAZ (422);
//   - `service_types` listesi BOŞSA zorunluluk aranmaz (seçilecek hizmet yok).
// Ekranlar bu yüzden liste boşken seçici çizmez ve Kaydet'i kilitlemez.
// =====================================================================

/**
 * Ön seçim eşlemesi — TEK kaynak: müvekkilin kategorisi/tipi (katlanmış ad) →
 * önerilen hizmet türü ADI (`service_types`). Eşleşme TAM addır: "Özel Hastane"
 * "hasta" sayılmaz. Eşlemede olmayan kategori (Sigorta Şirketi, Bireysel, …) ya da
 * kategorisiz müvekkil için ön seçim yoktur.
 */
export const KATEGORI_ON_SECIM_HIZMETI: Readonly<Record<string, string>> = {
  doktor: "Takip (doktor müvekkil)",
  hasta: "Takip (hasta vekilliği)",
  kurum: "Takip (kurum vekilliği)",
};

/** Karşılaştırma anahtarı: Türkçe katlama + boşluk sadeleştirme. */
const anahtar = (s: string): string => foldTr(s).replace(/\s+/g, " ").trim();

/**
 * Kategoriye göre önerilen hizmet kümesi (0 ya da 1 öğe). Öneri yalnız hizmet
 * LİSTEDEYSE verilir ve listedeki yazımıyla döner (liste panelden yeniden
 * adlandırılmış olabilir: "Takip (Doktor Müvekkil)") — listede olmayan ad backend'de 422'dir.
 */
export function onSecimHizmetleri(
  kategori: string | null | undefined,
  hizmetAdlari: readonly string[],
): string[] {
  const hedef = KATEGORI_ON_SECIM_HIZMETI[anahtar(kategori ?? "")];
  if (!hedef) return [];
  const listedeki = hizmetAdlari.find(ad => anahtar(ad) === anahtar(hedef));
  return listedeki ? [listedeki] : [];
}

/**
 * Seçicide görünen ve kayda giden küme. `secim` kullanıcının AÇIK seçimidir:
 * `undefined` = seçiciye hiç dokunulmadı → kategoriye göre ön seçim; dizi (boş
 * dahil) = kullanıcının kararı, ön seçim bir daha devreye girmez.
 */
export function etkinHizmetler(
  secim: readonly string[] | null | undefined,
  kategori: string | null | undefined,
  hizmetAdlari: readonly string[],
): string[] {
  return secim ? [...secim] : onSecimHizmetleri(kategori, hizmetAdlari);
}

/**
 * "Aynı hizmetleri tüm müvekkillere uygula" kısayolunun kaynağı: sırayla İLK
 * dolu küme. Hiçbiri dolu değilse `null` (kısayol devre dışı).
 */
export function ilkDoluKume(kumeler: ReadonlyArray<readonly string[]>): string[] | null {
  const dolu = kumeler.find(k => k.length > 0);
  return dolu ? [...dolu] : null;
}

/**
 * Hizmeti seçilmemiş müvekkil adları (backend 422 kuralının istemci ikizi).
 * Adsız satır müvekkil sayılmaz; hizmet listesi boşsa zorunluluk yoktur → `[]`.
 */
export function hizmetsizMuvekkiller(
  muvekkiller: ReadonlyArray<{ name: string; hizmetler: readonly string[] }>,
  hizmetAdlari: readonly string[],
): string[] {
  if (hizmetAdlari.length === 0) return [];
  return muvekkiller
    .filter(m => m.name.trim() !== "" && m.hizmetler.length === 0)
    .map(m => m.name.trim());
}

/** Müvekkil satırının altındaki uyarı. */
export const HIZMET_EKSIK_UYARISI = "Hizmet seçilmedi — kayıt için en az bir hizmet türü seçin.";

/** Kısayol düğmesinin metni (üç ekranda aynı). */
export const TUMUNE_UYGULA_ETIKETI = "Aynı hizmetleri tüm müvekkillere uygula";

/** Kaydet kapısının metni — backend 422 mesajıyla aynı kalıp. */
export function hizmetEksikMesaji(adlar: readonly string[]): string {
  return `Hizmet türü seçilmemiş müvekkil var: ${adlar.map(a => `"${a}"`).join(", ")}. `
    + "Her müvekkil için en az bir hizmet türü seçin.";
}
