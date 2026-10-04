// Lexis servisinin dava uçları — "gerçek dava" kipinde `lexisApi`'nin arkası (04.10.2026).
//
// - Yol: aynı origin `/lexis-api/{davalar,dosya,emsal-oner,iskelet,muallak-oner,karar-bankasi}` (konteyner nginx
//   allowlist'i → `lexis_api:8020`).
// - Kimlik: HUKDOK'un MSAL access token'ı (`apiClient.fetch`). Servis token'ı kendisi doğrular, kartı ve belge
//   listesini HUKDOK'un mevcut uçlarından AYNI token'la okur (`lexis-rapor/servis/hukdok.py`, K9).
// - Yanıtlar `types/lexis.ts` tipleriyle aynıdır (`LexisDava`, `DosyaGirdisi`, `Emsal`); emsal metni maskelidir.
//
// Bu modül `lexisApi.ts`'ten DİNAMİK yüklenir: örnek kip `apiClient`'ı (MSAL) hiç yüklemez.
import { apiClient } from "@/lib/api";
import { LexisApiError, type EmsalIstegi, type MuallakIstegi } from "@/lib/lexisApi";
import { LEXIS_API_ONEKI, LEXIS_YETKI_MESAJI } from "@/lib/lexisWord";
import type { DegerlendirmeTaslagi, DosyaGirdisi, Emsal, KararKaydi, LexisDava, LexisTaslak, MuallakOnerisi, TaslakIstegi } from "@/types/lexis";

export const LEXIS_DAVA_SERVISI_YOK = "Lexis servisine ulaşılamadı.";

async function jsonGetir<T>(yol: string, init: RequestInit, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await apiClient.fetch(`${LEXIS_API_ONEKI}${yol}`, { ...init, signal });
  } catch (e) {
    if ((e as Error)?.name === "AbortError") throw e;
    throw new LexisApiError(0, LEXIS_DAVA_SERVISI_YOK);
  }
  // Proxy ucu tanımıyorsa istek SPA'ya düşüp 200 + HTML dönebilir; servisin kendi hataları JSON `detail` taşır.
  const json = (res.headers.get("Content-Type") ?? "").includes("application/json");
  if (!res.ok) {
    if (res.status === 401) throw new LexisApiError(401, LEXIS_YETKI_MESAJI);
    let detay: string | null = null;
    if (json) {
      const govde = (await res.json().catch(() => null)) as { detail?: unknown } | null;
      if (typeof govde?.detail === "string" && govde.detail.trim()) detay = govde.detail;
    }
    throw new LexisApiError(res.status, detay ?? ([404, 502, 504].includes(res.status) ? LEXIS_DAVA_SERVISI_YOK : `Lexis isteği tamamlanamadı (HTTP ${res.status}).`));
  }
  if (!json) throw new LexisApiError(502, LEXIS_DAVA_SERVISI_YOK);
  return (await res.json()) as T;
}

/** `GET /lexis-api/davalar?q=` — müvekkili sigorta şirketi olan davalar önde; boş sorgu son davalar. */
export function davaAra(sorgu: string, signal?: AbortSignal): Promise<LexisDava[]> {
  return jsonGetir<LexisDava[]>(`/davalar?q=${encodeURIComponent(sorgu.trim())}`, { method: "GET" }, signal);
}

/** `GET /lexis-api/dosya/{case_id}` — dava kartı + belge listesi. */
export function dosyaGetir(caseId: number, signal?: AbortSignal): Promise<DosyaGirdisi> {
  return jsonGetir<DosyaGirdisi>(`/dosya/${caseId}`, { method: "GET" }, signal);
}

/** `POST /lexis-api/emsal-oner` — kütüphanedeki en benzer eski raporlar (maskeli), puan ve gerekçesiyle. */
export function emsalOner(istek: EmsalIstegi, signal?: AbortSignal): Promise<Emsal[]> {
  return jsonGetir<Emsal[]>("/emsal-oner", { method: "POST", body: JSON.stringify(istek) }, signal);
}

/** Taslak iskeleti: etiketli satırlar karttan dolu, özet boş, değerlendirmede giriş + kodun son maddesi. */
export type TaslakIskeleti = Pick<LexisTaslak, "etiketli" | "ozet"> & { degerlendirme: DegerlendirmeTaslagi; muallak: MuallakOnerisi };

/** `POST /lexis-api/iskelet` — modele hiçbir şey gitmez; künye dava kartından doldurulur. */
export function iskelet(istek: Pick<TaslakIstegi, "case_id" | "sirket" | "rapor_turu" | "iskelet">, signal?: AbortSignal): Promise<TaslakIskeleti> {
  const { case_id, sirket, rapor_turu, iskelet: bicim } = istek;
  return jsonGetir<TaslakIskeleti>("/iskelet", { method: "POST", body: JSON.stringify({ case_id, sirket, rapor_turu, iskelet: bicim }) }, signal);
}

/** `POST /lexis-api/muallak-oner` — seçilen sınıflarla öneri ve dayanağı (tutarı kod hesaplar, K11). */
export function muallakOner(istek: MuallakIstegi, signal?: AbortSignal): Promise<MuallakOnerisi> {
  return jsonGetir<MuallakOnerisi>("/muallak-oner", { method: "POST", body: JSON.stringify(istek) }, signal);
}

/** `GET /lexis-api/karar-bankasi` — kütüphanedeki raporlarda anılan kararlar (atıf doğrulaması). */
export function kararBankasi(signal?: AbortSignal): Promise<KararKaydi[]> {
  return jsonGetir<KararKaydi[]>("/karar-bankasi", { method: "GET" }, signal);
}
