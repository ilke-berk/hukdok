// Word yaşam döngüsü istemcisi (G285, plan §6.3 birebir; uçlar G284 `backend/routes/belge_yasam.py`):
// `yeni` · `surum` · `surumler` · `kesinlestir` · `yeni-surum-taslagi`. Kart ve tezgâh bu uçlarla YALNIZ bununla konuşur.
//
// - Kimlik `apiClient.fetch` (lib/api.ts). `kesinlestir` PDF/A dönüşümünü senkron koşar (sunucu bütçesi 270 sn), diğerleri
//   SharePoint'e senkron gider → dört yol `LONG_TIMEOUT_MARKERS`'ta (uzun katman). İstemci yine de düşerse sunucu işi
//   bitirir; aynı `istek_kimligi` ile tekrar deneme `reused: true` döner (idempotent).
// - Hata gövdesi PDF araçlarıyla aynı: `{"detail": {"mesaj", "error_kod"}}`; `KayitMesgulError` 409 düz metin. 4xx'te
//   sunucunun kullanıcıya dönük metni kazanır, 5xx'te sabit metin (`BelgeYasamApiError`: status + errorKod).
// - Word açma: `word_ac` (`ms-word:ofe|u|<url>`) masaüstü Word'ü açar; açılmazsa `word_url` Word Online'dır (§6.5).
import { apiClient } from "@/lib/api";
import type {
  BelgeSurumu,
  KesinlestirYaniti,
  SurumKaydetYaniti,
  YeniBelgeIstegi,
  YeniBelgeYaniti,
  YeniSurumTaslagiYaniti,
} from "@/types/belge";

export const BELGE_YASAM_GENEL_HATA = "Belge işlemi tamamlanamadı.";

/** Durum koduna göre varsayılan mesaj; 4xx'te sunucunun `mesaj`ı varsa o kazanır. */
const DURUM_MESAJLARI: Record<number, string> = {
  404: "Belge ya da dava kartı bulunamadı.",
  409: "Kayıt şu anda meşgul; birkaç dakika sonra tekrar deneyin.",
  413: "Belge boyut sınırını aşıyor.",
  422: "İstek geçersiz; girdileri kontrol edin.",
  502: "Belge arşive (SharePoint) ulaşamadı; daha sonra tekrar deneyin.",
  503: "Dönüşüm hattı şu anda meşgul; birkaç dakika sonra tekrar deneyin.",
  504: "İşlem zaman bütçesinde bitmedi; birkaç dakika sonra aynı düğmeyle tekrar deneyin.",
};

export class BelgeYasamApiError extends Error {
  readonly status: number;
  readonly errorKod: string;
  constructor(status: number, message: string, errorKod = "") {
    super(message);
    this.name = "BelgeYasamApiError";
    this.status = status;
    this.errorKod = errorKod;
  }
}

async function hataUret(res: Response): Promise<BelgeYasamApiError> {
  let mesaj = "";
  let kod = "";
  try {
    const govde = (await res.json()) as { detail?: unknown };
    const detay = govde?.detail;
    if (typeof detay === "string") mesaj = detay.trim();
    else if (detay && typeof detay === "object") {
      const d = detay as { mesaj?: unknown; error_kod?: unknown };
      if (typeof d.mesaj === "string") mesaj = d.mesaj.trim();
      if (typeof d.error_kod === "string") kod = d.error_kod;
    }
  } catch {
    /* gövde JSON değil / boş */
  }
  const varsayilan = DURUM_MESAJLARI[res.status] ?? `${BELGE_YASAM_GENEL_HATA} (HTTP ${res.status})`;
  const metin = res.status >= 500 || !mesaj ? varsayilan : mesaj;
  return new BelgeYasamApiError(res.status, metin, kod);
}

async function istek(yol: string, secenekler: RequestInit = {}): Promise<Response> {
  const res = await apiClient.fetch(yol, secenekler);
  if (!res.ok) throw await hataUret(res);
  return res;
}

function jsonPost(govde: unknown, signal?: AbortSignal): RequestInit {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde), signal };
}

/** K15: `bos.docx` → `03_TASLAKLAR/<ofis_no>/<ad>.docx`; TASLAK/GIDEN/WORD satır. */
export async function yeniBelge(caseId: number, govde: YeniBelgeIstegi, signal?: AbortSignal): Promise<YeniBelgeYaniti> {
  const res = await istek(`/api/cases/${caseId}/belgeler/yeni`, jsonPost({ sablon: "bos", ...govde }, signal));
  const y = (await res.json()) as Partial<YeniBelgeYaniti>;
  return { document_id: Number(y?.document_id), word_url: String(y?.word_url ?? ""), word_ac: String(y?.word_ac ?? "") };
}

/** K13: bilinçli sürüm kaydı (`not` opsiyonel; boş not gövdeye girmez). */
export async function surumKaydet(documentId: number, not?: string, signal?: AbortSignal): Promise<SurumKaydetYaniti> {
  const temiz = not?.trim();
  const res = await istek(`/api/documents/${documentId}/surum`, jsonPost(temiz ? { not: temiz } : {}, signal));
  const y = (await res.json()) as Partial<SurumKaydetYaniti>;
  return { surum_no: Number(y?.surum_no), sha256: String(y?.sha256 ?? ""), degisti: y?.degisti !== false };
}

export async function surumler(documentId: number, signal?: AbortSignal): Promise<BelgeSurumu[]> {
  const res = await istek(`/api/documents/${documentId}/surumler`, { signal });
  const y = (await res.json()) as unknown;
  return Array.isArray(y) ? (y as BelgeSurumu[]) : [];
}

/** K14: aynı satır KESIN + PDF/A + arşiv; zaten KESIN 409, dönüşüm meşgul 503. */
export async function kesinlestir(documentId: number, istekKimligi: string, signal?: AbortSignal): Promise<KesinlestirYaniti> {
  const res = await istek(`/api/documents/${documentId}/kesinlestir`, jsonPost({ istek_kimligi: istekKimligi }, signal));
  const y = (await res.json()) as Partial<KesinlestirYaniti>;
  return { document_id: Number(y?.document_id), reused: y?.reused === true };
}

/** K14 düzeltme yolu: KESIN belgeden yeni TASLAK (`onceki_document_id`). */
export async function yeniSurumTaslagi(documentId: number, istekKimligi: string, signal?: AbortSignal): Promise<YeniSurumTaslagiYaniti> {
  const res = await istek(`/api/documents/${documentId}/yeni-surum-taslagi`, jsonPost({ istek_kimligi: istekKimligi }, signal));
  const y = (await res.json()) as Partial<YeniSurumTaslagiYaniti>;
  return {
    document_id: Number(y?.document_id),
    reused: y?.reused === true,
    word_url: y?.word_url ? String(y.word_url) : null,
    word_ac: y?.word_ac ? String(y.word_ac) : null,
  };
}

/** `word_url`'den masaüstü Word protokol bağlantısı (sunucunun `word_ac`'ıyla aynı biçim; kart satırı yalnız URL taşır). */
export function wordAcBaglantisi(wordUrl: string): string {
  return `ms-word:ofe|u|${wordUrl}`;
}

/** Tarayıcı yönlendirmesi — testte taklit edilir (jsdom gezinme yapamaz). */
export const tarayici = {
  git(url: string): void {
    window.location.href = url;
  },
};

/** Masaüstü Word açıldı mı? — protokol işleyicisi açılınca pencere odağı kaybeder; bu süre içinde kaybetmezse yedek bağlantı. */
export const WORD_ACILMA_BEKLEMESI_MS = 1500;

/**
 * `ms-word:` bağlantısıyla Word'ü açmayı dener; `bekleme` içinde pencere odağı kaybolmadıysa `onAcilmadi` çağrılır
 * (çağıran "Word Online'da aç" bağlantısını gösterir). Dönen işlev zamanlayıcıyı ve dinleyiciyi temizler.
 */
export function wordProtokoluylaAc(wordAc: string, onAcilmadi: () => void, bekleme = WORD_ACILMA_BEKLEMESI_MS): () => void {
  let acildi = false;
  const odakKaybi = () => {
    acildi = true;
  };
  window.addEventListener("blur", odakKaybi);
  const zamanlayici = window.setTimeout(() => {
    window.removeEventListener("blur", odakKaybi);
    if (!acildi && !document.hidden) onAcilmadi();
  }, bekleme);
  tarayici.git(wordAc);
  return () => {
    window.clearTimeout(zamanlayici);
    window.removeEventListener("blur", odakKaybi);
  };
}

/**
 * `services/belge_yasam.docx_adi` + `text_utils.sanitize_filename_text` ön-izlemesi: sunucunun yazacağı ad (çakışma eki
 * `-2` hariç). Güvensiz karakter `_`, ardışık `_`/`.` teke, `.docx` zorunlu (`.doc` → `.docx`); gövde boşsa `null`.
 */
export function docxAdiOnizleme(ad: string): string | null {
  const ham = (ad ?? "").trim().replace(/\\/g, "/").split("/").pop() ?? "";
  let govde = ham.toLowerCase().endsWith(".docx") ? ham.slice(0, -5) : ham;
  if (govde.toLowerCase().endsWith(".doc")) govde = govde.slice(0, -4);
  govde = govde.replace(/^[ .]+|[ .]+$/g, "");
  if (!govde.replace(/^[_-]+|[_-]+$/g, "")) return null;
  const temiz = `${govde}.docx`
    .replace(/\0/g, "")
    .replace(/[^a-zA-ZğüşıöçĞÜŞİÖÇâîûÂÎÛ0-9._\-() ]/g, "_")
    .replace(/_+/g, "_")
    .replace(/\.+/g, ".")
    .trim();
  const kok = temiz.slice(0, -5).replace(/^[ ._-]+|[ ._-]+$/g, "");
  return kok && temiz.toLowerCase().endsWith(".docx") ? temiz : null;
}

/** Varsayılan belge adı: tür etiketi + bugünün tarihi (`Cevap Dilekçesi 08.10.2026`). */
export function varsayilanBelgeAdi(turEtiketi: string, tarih: Date = new Date()): string {
  const gun = String(tarih.getDate()).padStart(2, "0");
  const ay = String(tarih.getMonth() + 1).padStart(2, "0");
  return `${turEtiketi.trim()} ${gun}.${ay}.${tarih.getFullYear()}`.trim();
}

export const belgeYasamApi = { yeniBelge, surumKaydet, surumler, kesinlestir, yeniSurumTaslagi };
