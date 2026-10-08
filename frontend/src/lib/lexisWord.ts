// Lexis Word çıktısı — sayfanın GERÇEK servise giden tek çağrısı (04.10.2026).
//
// - Yol: aynı origin `/lexis-api/word` (konteyner nginx allowlist'i, önek atılıp `lexis_api:8020`'ye iletilir —
//   `nginx.conf`, Hukukbot deseni). Servis ayrı depodadır (`lexis-rapor/servis`), ayrı stack'tir.
// - Kimlik: HUKDOK'un MSAL access token'ı; `apiClient.fetch` taşır (401 yenilemesi ve oturum-bitti akışı oradan).
//   Servis token'ı HUKDOK kuralıyla kendisi doğrular ve şimdilik yalnız yöneticiyi kabul eder.
// - Gövde: ekrandaki taslak olduğu gibi (`LexisTaslak`) + künye. Künye (hasar no, rapor no) taslakta yoktur;
//   HUKDOK adaptörü gelince sunucu karttan kendisi alacak, o zaman buradan kalkar.
// - Yanıt: dosyanın kendisi. Uyarılar başlıkta gelir: `X-Lexis-Uyari-Sayisi` (tam sayı) + `X-Lexis-Uyarilar`
//   (yüzde-kodlu JSON dizisi; başlığa sığan ilk kısım).
//
// Bu modül `lexisApi.ts`'ten DİNAMİK yüklenir: örnek adaptörün geri kalanı `apiClient`'ı (MSAL) hiç yüklemez.
import { apiClient } from "@/lib/api";
import { LexisApiError } from "@/lib/lexisApi";
import type { LexisTaslak } from "@/types/lexis";

export const LEXIS_API_ONEKI = "/lexis-api";
export const LEXIS_SERVIS_YOK = "Lexis servisine ulaşılamadı; Word üretilemedi.";
export const LEXIS_YETKI_MESAJI = "Lexis servisi oturumunuzu doğrulayamadı. Sayfayı yenileyip tekrar giriş yapın.";
const VARSAYILAN_DOSYA_ADI = "Lexis_taslak.docx";

export interface WordKunyesi {
  hasar_no: string | null;
  /** Ek rapor kapağında hasar no yerine yazılır. */
  hukuk_no?: string | null;
  /** Rapor no = dosya no (pilot raporların tamamında aynı). */
  rapor_no: string | null;
  /** ISO `yyyy-mm-dd`; verilmezse sunucu bugünü (Türkiye günü) yazar. */
  rapor_tarihi?: string | null;
  /** Gerçek davada taslağın koşusu: Word inince sunucu Geçmiş'te "indirildi" işaretler. Künyeyle birlikte gitmez. */
  kosu_id?: number | null;
}

export interface WordSonucu {
  dosya_adi: string;
  /** Sunucunun saydığı uyarı — `uyarilar` başlığa sığan kısımdır, daha kısa olabilir. */
  uyari_sayisi: number;
  uyarilar: string[];
}

/** FastAPI hata gövdesinden (`{"detail": "..."}`) metin; gövde JSON değilse (nginx HTML'i) null. */
async function detayOku(res: Response): Promise<string | null> {
  try {
    const govde = (await res.json()) as { detail?: unknown };
    if (typeof govde?.detail === "string" && govde.detail.trim()) return govde.detail;
  } catch {
    /* gövde JSON değil */
  }
  return null;
}

function dosyaAdi(res: Response, bicim: CiktiBicimi = "docx"): string {
  const m = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "");
  return m?.[1] || (bicim === "pdf" ? VARSAYILAN_DOSYA_ADI.replace(/\.docx$/, ".pdf") : VARSAYILAN_DOSYA_ADI);
}

function uyarilariOku(res: Response): string[] {
  try {
    const liste: unknown = JSON.parse(decodeURIComponent(res.headers.get("X-Lexis-Uyarilar") ?? "[]"));
    return Array.isArray(liste) ? liste.filter((u): u is string => typeof u === "string") : [];
  } catch {
    return [];
  }
}

function indir(blob: Blob, ad: string): void {
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = ad;
    document.body.appendChild(a);
    try {
      a.click();
    } finally {
      a.remove();
    }
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** İndirilecek biçim: Word ya da servisin LibreOffice'le çevirdiği PDF (`/word` gövdesinde `bicim: "pdf"`). */
export type CiktiBicimi = "docx" | "pdf";
const ICERIK_TURU: Record<CiktiBicimi, string> = { docx: "wordprocessingml", pdf: "application/pdf" };

/** `POST /lexis-api/word` — şirket şablonunda Word (ya da PDF) üretir ve tarayıcıya indirir. Hata `LexisApiError`. */
export async function wordIndir(taslak: LexisTaslak, kunye: WordKunyesi, signal?: AbortSignal, bicim: CiktiBicimi = "docx"): Promise<WordSonucu> {
  let res: Response;
  const { kosu_id, ...kapak } = kunye;
  try {
    res = await apiClient.fetch(`${LEXIS_API_ONEKI}/word`, {
      method: "POST",
      body: JSON.stringify({ taslak, kunye: kapak, ...(kosu_id != null ? { kosu_id } : {}), ...(bicim === "pdf" ? { bicim } : {}) }),
      signal,
    });
  } catch (e) {
    if ((e as Error)?.name === "AbortError") throw e;
    throw new LexisApiError(0, LEXIS_SERVIS_YOK);
  }
  if (!res.ok) {
    if (res.status === 401) throw new LexisApiError(401, LEXIS_YETKI_MESAJI);
    // Servisin kendi hataları JSON `detail` taşır; nginx'in 404'ü (uç proxy'de yok) ve 502/504'ü (servis kapalı) taşımaz.
    throw new LexisApiError(res.status, (await detayOku(res)) ?? ([404, 502, 504].includes(res.status) ? LEXIS_SERVIS_YOK : `${bicim === "pdf" ? "PDF" : "Word"} üretilemedi (HTTP ${res.status}).`));
  }
  // Proxy bu ucu tanımıyorsa istek SPA'ya düşüp 200 + HTML dönebilir: dosya sanılıp indirilmesin.
  if (!(res.headers.get("Content-Type") ?? "").includes(ICERIK_TURU[bicim])) throw new LexisApiError(502, LEXIS_SERVIS_YOK);

  const uyarilar = uyarilariOku(res);
  const sayi = Number.parseInt(res.headers.get("X-Lexis-Uyari-Sayisi") ?? "", 10);
  const ad = dosyaAdi(res, bicim);
  indir(await res.blob(), ad);
  return { dosya_adi: ad, uyari_sayisi: Number.isFinite(sayi) ? sayi : uyarilar.length, uyarilar };
}
