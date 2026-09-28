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
 * Kaynağın HukuDok belge numarası: önce hukbot'un `hukdok_id` alanı, yoksa `metadata.hukdok_id` (alan eklenmeden
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

export const HUKUDOK_BELGE_ACILAMADI = "Belge HukuDok arşivinden açılamadı.";

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
