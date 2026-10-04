// /hukukbot sayfasının (G205) saf yardımcıları — bileşen dışı (react-refresh sınırı), ayrı test edilir.
import {
  HUKUKBOT_GENEL_HATA,
  HUKUKBOT_HIZ_MESAJI,
  HUKUKBOT_YETKI_MESAJI,
  HukukbotApiError,
  HukukbotHizSiniriError,
  HukukbotYetkiError,
} from "@/lib/hukukbotApi";
import type { HukukbotKaynak, HukukbotMesaj, HukukbotOturumOzeti } from "@/types/hukukbot";

/** hukbot'un kendi açtığı oturumda kullandığı başlık uzunluğu — biz de aynısını kullanırız. */
export const BASLIK_UZUNLUGU = 50;

export const YENI_SOHBET_BASLIGI = "Yeni sohbet";
export const AKIS_HATA_MESAJI = "Hukukbot yanıt verirken bir hata oluştu. Lütfen tekrar deneyin.";
export const OTURUM_BULUNAMADI = "Sohbet bulunamadı ya da silinmiş.";
export const KAYIT_BULUNAMADI = "İstenen kayıt Hukukbot'ta bulunamadı.";

/** Ekrandaki mesaj — sunucu mesajı + akış/hata durumu. `anahtar` React key'i ve akış hedefidir. */
export interface EkranMesaji {
  anahtar: string;
  role: HukukbotMesaj["role"];
  content: string;
  sources?: HukukbotKaynak[] | null;
  /** Model yanıtı şu an akıyor. */
  akiyor?: boolean;
  /** Akıştaki son `status` olayı — metin gelene dek "yazıyor" yerine gösterilir (kaydedilmez). */
  durum?: string | null;
  /** Kullanıcı "Durdur"a bastı — yanıt yarım kaldı. */
  durduruldu?: boolean;
  /** Türkçe hata metni (akış/istek hatası). */
  hata?: string | null;
}

let sayac = 0;
/** Oturum-içi benzersiz mesaj anahtarı. */
export function mesajAnahtari(onek: string): string {
  sayac += 1;
  return `${onek}-${Date.now().toString(36)}-${sayac}`;
}

/** Sunucudan gelen mesajları ekran modeline çevirir. */
export function ekranMesajlari(mesajlar: HukukbotMesaj[]): EkranMesaji[] {
  return mesajlar.map((m, i) => ({
    anahtar: `sunucu-${i}`,
    role: m.role,
    content: m.content ?? "",
    sources: m.sources ?? null,
  }));
}

/** `/ask` `history` alanı: yalnız tamamlanmış, hatasız, dolu mesajlar. */
export function gecmisUret(mesajlar: EkranMesaji[]): HukukbotMesaj[] {
  return mesajlar
    .filter((m) => !m.akiyor && !m.hata && m.content.trim() !== "")
    .map((m) => ({ role: m.role, content: m.content }));
}

/** Soru metninden oturum başlığı (ilk 50 karakter, boşluk sadeleşmiş). */
export function baslikUret(soru: string): string {
  const temiz = soru.replace(/\s+/g, " ").trim();
  return temiz.slice(0, BASLIK_UZUNLUGU) || YENI_SOHBET_BASLIGI;
}

function zaman(iso: string): number {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 0 : t;
}

/** Sabitlenenler üstte, her grupta en yeni önce (sunucu sırasıyla aynı kural; yerel değişiklikten sonra). */
export function oturumlariSirala(oturumlar: HukukbotOturumOzeti[]): HukukbotOturumOzeti[] {
  return [...oturumlar].sort((a, b) => {
    if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
    return zaman(b.created_at) - zaman(a.created_at);
  });
}

export type TarihGrubu = "Bugün" | "Dün" | "Son 7 gün" | "Son 30 gün" | "Daha eski";
const TARIH_GRUPLARI: TarihGrubu[] = ["Bugün", "Dün", "Son 7 gün", "Son 30 gün", "Daha eski"];

/** Yerel takvim gününe göre grup (saat farkı değil gün farkı: dün 23:59 "Dün"dür). Tarihi bozuk → "Daha eski". */
export function tarihGrubu(iso: string, simdi: Date = new Date()): TarihGrubu {
  const t = zaman(iso);
  if (!t) return "Daha eski";
  const gunBasi = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const fark = Math.round((gunBasi(simdi) - gunBasi(new Date(t))) / 86_400_000);
  if (fark <= 0) return "Bugün";
  if (fark === 1) return "Dün";
  if (fark < 7) return "Son 7 gün";
  if (fark < 30) return "Son 30 gün";
  return "Daha eski";
}

/**
 * Sabitlenmemiş sohbetleri tarih gruplarına böler (sıra korunur; boş grup dönmez).
 * Girdi `oturumlariSirala` sırasındadır — gruplar da böylece yeniden eskiye akar.
 */
export function tariheGoreGrupla(
  oturumlar: HukukbotOturumOzeti[],
  simdi: Date = new Date(),
): { grup: TarihGrubu; oturumlar: HukukbotOturumOzeti[] }[] {
  const kovalar = new Map<TarihGrubu, HukukbotOturumOzeti[]>();
  for (const o of oturumlar) {
    const g = tarihGrubu(o.created_at, simdi);
    kovalar.set(g, [...(kovalar.get(g) ?? []), o]);
  }
  return TARIH_GRUPLARI.filter((g) => kovalar.has(g)).map((g) => ({ grup: g, oturumlar: kovalar.get(g)! }));
}

/** Türkçe büyük/küçük harf ve aksandan bağımsız karşılaştırma anahtarı ("İŞ" ~ "iş" ~ "is"). */
function aramaAnahtari(metin: string): string {
  return metin.toLocaleLowerCase("tr-TR").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ı/g, "i");
}

/** Sohbet listesi araması: başlık ya da son soru önizlemesi terimi içeriyorsa kalır (boş terim = hepsi). */
export function oturumlariSuz(oturumlar: HukukbotOturumOzeti[], terim: string): HukukbotOturumOzeti[] {
  const t = aramaAnahtari(terim.trim());
  if (!t) return oturumlar;
  return oturumlar.filter((o) => aramaAnahtari(`${o.title} ${o.preview ?? ""}`).includes(t));
}

/** Kullanıcının "Durdur"u / sayfa değişimi kaynaklı iptal mi? */
export function iptalMi(hata: unknown): boolean {
  return (
    typeof hata === "object" &&
    hata !== null &&
    "name" in hata &&
    (hata as { name?: unknown }).name === "AbortError"
  );
}

/**
 * Kaynağın HUKDOK belge numarası: önce hukbot'un `hukdok_id` alanı, yoksa `metadata.hukdok_id` (alan eklenmeden
 * ÖNCE kaydedilmiş mesajlar için — ingest metadata'sında zaten vardı). Store sayıyı dize/float döndürebilir.
 * Geçerli pozitif tamsayı değilse null → sayfa eski `/download/{filename}` yolunu kullanır.
 */
export function kaynakHukdokId(kaynak: HukukbotKaynak): number | null {
  for (const aday of [kaynak.hukdok_id, kaynak.metadata?.hukdok_id]) {
    if (aday === null || aday === undefined || typeof aday === "boolean" || aday === "") continue;
    const sayi = Number(aday);
    if (Number.isFinite(sayi) && sayi > 0) return Math.trunc(sayi);
  }
  return null;
}

export const HUKDOK_BELGE_ACILAMADI = "Belge HUKDOK arşivinden açılamadı.";

/** Her istek hatası için kullanıcıya gösterilecek Türkçe metin (429 daima sabit Türkçe metin). */
export function hataMetni(hata: unknown): string {
  if (hata instanceof HukukbotHizSiniriError) return HUKUKBOT_HIZ_MESAJI;
  if (hata instanceof HukukbotYetkiError) return HUKUKBOT_YETKI_MESAJI;
  if (hata instanceof HukukbotApiError) {
    if (hata.status === 404) return KAYIT_BULUNAMADI;
    return `${HUKUKBOT_GENEL_HATA} (HTTP ${hata.status})`;
  }
  return HUKUKBOT_GENEL_HATA;
}
