// Lexis servisinin dava uçları — "gerçek dava" kipinde `lexisApi`'nin arkası (04.10.2026).
//
// - Yol: aynı origin `/lexis-api/{davalar,dosya,emsal-oner,iskelet,muallak-oner,karar-bankasi,kutuphane,rapor,
//   emsal-puanla,taslak,gecmis,kart-baglari,kart-sec,profiller,profil,karar-rafi,kararlar,karar,yaz}` (konteyner
//   nginx allowlist'i → `lexis_api:8020`). `taslak` … `profil` servisin KENDİ veritabanına yazar/okur (taslak, koşu
//   logu, kart seçimi, profil); `karar-rafi`, `kararlar`, `karar` karar veritabanını okur; `yaz` modeli çağırır.
// - Kimlik: HUKDOK'un MSAL access token'ı (`apiClient.fetch`). Servis token'ı kendisi doğrular, kartı ve belge
//   listesini HUKDOK'un mevcut uçlarından AYNI token'la okur (`lexis-rapor/servis/hukdok.py`, K9).
// - Yanıtlar `types/lexis.ts` tipleriyle aynıdır (`LexisDava`, `DosyaGirdisi`, `Emsal`); emsal metni maskelidir.
//
// Bu modül `lexisApi.ts`'ten DİNAMİK yüklenir: örnek kip `apiClient`'ı (MSAL) hiç yüklemez.
import { apiClient } from "@/lib/api";
import { LexisApiError, type EmsalIstegi, type MuallakIstegi } from "@/lib/lexisApi";
import { LEXIS_API_ONEKI, LEXIS_YETKI_MESAJI } from "@/lib/lexisWord";
import type {
  DegerlendirmeTaslagi,
  DosyaGirdisi,
  Emsal,
  KararKaydi,
  KartKararlari,
  KayitliTaslak,
  KutuphaneFiltresi,
  KutuphaneKaydi,
  LexisDava,
  LexisTaslak,
  MuallakOnerisi,
  RafKarariAyrinti,
  RafSayfasi,
  RafSecenekleri,
  RafSuzgeci,
  RaporBagi,
  SirketProfili,
  TaslakIstegi,
  TaslakKaydi,
  TaslakKayitSonucu,
  TaslakKosusu,
  YazimSonucu,
} from "@/types/lexis";

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

/**
 * Taslak iskeleti: etiketli satırlar karttan dolu, özet boş, değerlendirmede giriş + kodun son maddesi.
 * `kosu_id`: Geçmiş sekmesindeki koşu satırı; servisin veritabanı yoksa `null` (taslak yine gelir).
 */
export type TaslakIskeleti = Pick<LexisTaslak, "etiketli" | "ozet"> & { degerlendirme: DegerlendirmeTaslagi; muallak: MuallakOnerisi; kosu_id?: number | null };

/**
 * `POST /lexis-api/iskelet` — modele hiçbir şey gitmez; künye dava kartından doldurulur. Emsallerin yalnız SAYISI
 * gider (koşu logu için); belge ve emsal metni gitmez.
 */
export function iskelet(istek: Pick<TaslakIstegi, "case_id" | "sirket" | "rapor_turu" | "iskelet" | "emsal_sha">, signal?: AbortSignal): Promise<TaslakIskeleti> {
  const { case_id, sirket, rapor_turu, iskelet: bicim, emsal_sha } = istek;
  return jsonGetir<TaslakIskeleti>("/iskelet", { method: "POST", body: JSON.stringify({ case_id, sirket, rapor_turu, iskelet: bicim, emsal_sayisi: emsal_sha.length }) }, signal);
}

/** `POST /lexis-api/muallak-oner` — seçilen sınıflarla öneri ve dayanağı (tutarı kod hesaplar, K11). */
export function muallakOner(istek: MuallakIstegi, signal?: AbortSignal): Promise<MuallakOnerisi> {
  return jsonGetir<MuallakOnerisi>("/muallak-oner", { method: "POST", body: JSON.stringify(istek) }, signal);
}

/** `POST /lexis-api/kutuphane` — süzgeçlere uyan eski raporlar (maskeli); liste bölüm metni taşımaz. */
export function kutuphaneAra(filtre: KutuphaneFiltresi, signal?: AbortSignal): Promise<KutuphaneKaydi[]> {
  return jsonGetir<KutuphaneKaydi[]>("/kutuphane", { method: "POST", body: JSON.stringify(filtre) }, signal);
}

/** `GET /lexis-api/rapor/{sha256}` — tek rapor, bölüm metinleriyle (maskeli). */
export function raporGetir(sha256: string, signal?: AbortSignal): Promise<KutuphaneKaydi> {
  return jsonGetir<KutuphaneKaydi>(`/rapor/${encodeURIComponent(sha256)}`, { method: "GET" }, signal);
}

/** `POST /lexis-api/emsal-puanla` — kütüphaneden elle seçilen raporun dosyaya göre puanı ve gerekçesi. */
export function emsalPuanla(istek: EmsalIstegi & { sha256: string }, signal?: AbortSignal): Promise<Emsal> {
  const { case_id, sha256, sirket, rapor_turu } = istek;
  return jsonGetir<Emsal>("/emsal-puanla", { method: "POST", body: JSON.stringify({ case_id, sha256, sirket, rapor_turu }) }, signal);
}

/** `GET /lexis-api/karar-bankasi` — kütüphanedeki raporlarda anılan kararlar (atıf doğrulaması). */
export function kararBankasi(signal?: AbortSignal): Promise<KararKaydi[]> {
  return jsonGetir<KararKaydi[]>("/karar-bankasi", { method: "GET" }, signal);
}

// --- karar rafı ve kararlardan yazım (`lexis-rapor/servis/karar_raf.py`, `yazim.py`) ---

/** `POST /lexis-api/karar-rafi` — süzgeçlere uyan büro kararları (metinsiz), en yeni karar önce. Arama metni gövdededir. */
export function kararAra(suzgec: RafSuzgeci, signal?: AbortSignal): Promise<RafSayfasi> {
  return jsonGetir<RafSayfasi>("/karar-rafi", { method: "POST", body: JSON.stringify(suzgec) }, signal);
}

/** `GET /lexis-api/karar-rafi` — rafın süzgeç seçenekleri. */
export function rafSecenekleri(signal?: AbortSignal): Promise<RafSecenekleri> {
  return jsonGetir<RafSecenekleri>("/karar-rafi", { method: "GET" }, signal);
}

/** `GET /lexis-api/kararlar/{case_id}` — dava kartına bağlı büro kararları + kararlardan yazım açık mı. */
export function kartKararlari(caseId: number, signal?: AbortSignal): Promise<KartKararlari> {
  return jsonGetir<KartKararlari>(`/kararlar/${caseId}`, { method: "GET" }, signal);
}

/** `GET /lexis-api/karar/{id}` — tek karar: künye, alanlar, parçalar, tam metin. */
export function kararGetir(id: number, signal?: AbortSignal): Promise<RafKarariAyrinti> {
  return jsonGetir<RafKarariAyrinti>(`/karar/${id}`, { method: "GET" }, signal);
}

/**
 * `POST /lexis-api/yaz` — seçilen kararlardan özet bölümleri + değerlendirme. Kararların MASKELİ metni ve emsal
 * raporların maskeli bölümleri modele gider; çağıran önce kullanıcı onayı alır (K4). Servis kapalıysa 503.
 */
export function yaz(istek: Pick<TaslakIstegi, "case_id" | "sirket" | "rapor_turu" | "iskelet" | "emsal_sha"> & { karar_idleri: number[] }, signal?: AbortSignal): Promise<YazimSonucu> {
  const { case_id, sirket, rapor_turu, iskelet: bicim, emsal_sha, karar_idleri } = istek;
  return jsonGetir<YazimSonucu>("/yaz", { method: "POST", body: JSON.stringify({ case_id, sirket, rapor_turu, iskelet: bicim, karar_idleri, emsal_sha }) }, signal);
}

// --- kalıcılık: servisin kendi veritabanı (`lexis-rapor/servis/depo.py`) ---

/** `GET /lexis-api/taslak/{case_id}` — davanın kayıtlı taslağı; yoksa `null` (hata değil). */
export function taslakGetir(caseId: number, signal?: AbortSignal): Promise<KayitliTaslak | null> {
  return jsonGetir<KayitliTaslak | null>(`/taslak/${caseId}`, { method: "GET" }, signal);
}

/** `PUT /lexis-api/taslak/{case_id}` — okunan sürümle yazar; başka oturum araya girdiyse 409 (`LexisApiError`). */
export function taslakKaydet(caseId: number, kayit: TaslakKaydi, signal?: AbortSignal): Promise<TaslakKayitSonucu> {
  return jsonGetir<TaslakKayitSonucu>(`/taslak/${caseId}`, { method: "PUT", body: JSON.stringify(kayit) }, signal);
}

/** `DELETE /lexis-api/taslak/{case_id}` — künye değişip taslak bilerek silindiğinde. */
export async function taslakSil(caseId: number, signal?: AbortSignal): Promise<void> {
  await jsonGetir<{ silindi: boolean }>(`/taslak/${caseId}`, { method: "DELETE" }, signal);
}

/** `GET /lexis-api/gecmis` — "Taslağı yaz" koşularının logu, en yeni önce. */
export function gecmis(signal?: AbortSignal): Promise<TaslakKosusu[]> {
  return jsonGetir<TaslakKosusu[]>("/gecmis", { method: "GET" }, signal);
}

/** `GET /lexis-api/kart-baglari` — tek karta inmeyen eski raporlar (çok aday, çelişki, bağ yok). */
export function kartBaglari(signal?: AbortSignal): Promise<RaporBagi[]> {
  return jsonGetir<RaporBagi[]>("/kart-baglari", { method: "GET" }, signal);
}

/** `POST /lexis-api/kart-sec` — insan seçimi (K8); `kartId = null` seçimi geri alır. */
export function kartSec(rapor: string, kartId: number | null, signal?: AbortSignal): Promise<RaporBagi> {
  return jsonGetir<RaporBagi>("/kart-sec", { method: "POST", body: JSON.stringify({ rapor, kart_id: kartId }) }, signal);
}

/** `GET /lexis-api/profiller` — şirket profilleri (kaydı olmayan şirket koddaki varsayılanla gelir). */
export function profiller(signal?: AbortSignal): Promise<SirketProfili[]> {
  return jsonGetir<SirketProfili[]>("/profiller", { method: "GET" }, signal);
}

/** `PUT /lexis-api/profil/{şirket}` — şirket kodu, ad ve güncelleme damgası sunucunundur; gövdeye girmez. */
export function profilKaydet(profil: SirketProfili, signal?: AbortSignal): Promise<SirketProfili> {
  const { iskelet_ana, iskelet_ek, sabit_metinler, kriter_metni, muallak_tablosu } = profil;
  return jsonGetir<SirketProfili>(
    `/profil/${encodeURIComponent(profil.sirket_kodu)}`,
    { method: "PUT", body: JSON.stringify({ iskelet_ana, iskelet_ek, sabit_metinler, kriter_metni, muallak_tablosu }) },
    signal,
  );
}
