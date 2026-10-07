// PDF araçları istemcisi (G270, plan §3) — Belge tezgâhı sunucuyla YALNIZ bununla konuşur.
//
// - Yollar `/api/pdf-araclari/{yukle,islem,onizleme}` + mevcut `/api/download/{id}` (nginx `location /api`, K10).
// - Kimlik `apiClient.fetch` (lib/api.ts): Bearer, 401 yenilemesi, zaman aşımı. Yükleme FormData'dır → uzun katman
//   (300 sn) kendiliğinden; `islem` JSON → varsayılan 30 sn (lib/api.ts'e dokunulmadı — bkz. G270 raporu).
// - Hata gövdesi: PDF araçları uçları `{"detail": {"mesaj", "error_kod"}}` döner (`routes/pdf_araclari._hata`),
//   diğer uçlar düz `{"detail": "..."}`; ikisi de `PdfAraclariApiError`'a (status + errorKod + kullanıcı mesajı) çevrilir.
import { apiClient } from "@/lib/api";
import type { Dosya, IslemIstegi, IslemYaniti } from "@/types/pdfAraclari";

export const PDF_ARACLARI_ONEKI = "/api/pdf-araclari";
export const PDF_ARACLARI_GENEL_HATA = "PDF işlemi tamamlanamadı.";

/** Durum koduna göre kullanıcı mesajı; sunucunun `mesaj`ı varsa 4xx'te o kazanır. */
const DURUM_MESAJLARI: Record<number, string> = {
  413: "Dosya boyutu ya da sayfa sayısı sınırı aşıldı.",
  415: "Desteklenmeyen dosya türü.",
  422: "İstek geçersiz; girdileri kontrol edin.",
  503: "Sistem şu anda meşgul; birkaç dakika sonra tekrar deneyin.",
  504: "İşlem zaman bütçesinde bitmedi; daha küçük parçalarla deneyin.",
};

export class PdfAraclariApiError extends Error {
  readonly status: number;
  readonly errorKod: string;
  constructor(status: number, message: string, errorKod = "") {
    super(message);
    this.name = "PdfAraclariApiError";
    this.status = status;
    this.errorKod = errorKod;
  }
}

async function hataUret(res: Response): Promise<PdfAraclariApiError> {
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
  const varsayilan = DURUM_MESAJLARI[res.status] ?? `${PDF_ARACLARI_GENEL_HATA} (HTTP ${res.status})`;
  // 5xx'te sunucu metni teknik olabilir → sabit mesaj; 4xx'te sunucunun kullanıcıya dönük metni kazanır.
  const metin = res.status >= 500 || !mesaj ? varsayilan : mesaj;
  return new PdfAraclariApiError(res.status, metin, kod);
}

async function istek(yol: string, secenekler: RequestInit = {}): Promise<Response> {
  const res = await apiClient.fetch(yol, secenekler);
  if (!res.ok) throw await hataUret(res);
  return res;
}

/** Tek dosya yükler; sunucu PDF'e çevirir (K3). FormData → `apiClient` uzun katmanı (300 sn). */
export async function yukle(file: File, signal?: AbortSignal): Promise<Dosya> {
  const form = new FormData();
  form.append("file", file);
  const res = await istek(`${PDF_ARACLARI_ONEKI}/yukle`, { method: "POST", body: form, signal });
  return (await res.json()) as Dosya;
}

/** Tek işlem; çıktılar yeni id'lerle döner (`bol` birden çok). */
export async function islem(istek_: IslemIstegi, signal?: AbortSignal): Promise<Dosya[]> {
  const res = await istek(`${PDF_ARACLARI_ONEKI}/islem`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(istek_),
    signal,
  });
  const yanit = (await res.json()) as IslemYaniti;
  return Array.isArray(yanit?.ciktilar) ? yanit.ciktilar : [];
}

/** Sayfa PNG'sinin yolu (`genislik` 64-1600). Bearer taşımaz; `<img src>` için değil, `onizlemeBlob` ile çekilir (G271). */
export function onizlemeUrl(id: string, sayfa: number, genislik = 240): string {
  return `${PDF_ARACLARI_ONEKI}/onizleme/${encodeURIComponent(id)}/${sayfa}?genislik=${genislik}`;
}

/** Sayfa PNG'sini yetkili istekle indirir (sunucu `Cache-Control: private, max-age=3600`). */
export async function onizlemeBlob(id: string, sayfa: number, genislik = 240, signal?: AbortSignal): Promise<Blob> {
  const res = await istek(onizlemeUrl(id, sayfa, genislik), { signal });
  return res.blob();
}

/** Çalışma dosyasını mevcut `/api/download/{id}` ucundan indirir ve tarayıcıya `ad` ile kaydettirir. */
export async function indir(id: string, ad: string): Promise<void> {
  const res = await istek(`/api/download/${encodeURIComponent(id)}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = ad;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Hata nesnesinden kullanıcı mesajı (`PdfAraclariApiError`, `ApiTimeoutError`, ağ hatası). */
export function hataMesaji(e: unknown): string {
  if (e instanceof Error && e.message.trim()) return e.message;
  return PDF_ARACLARI_GENEL_HATA;
}

/**
 * Böl aralık metni → `araliklar`. Biçim: `1-3,4-7` ya da tek sayfa `5` (= `5-5`); ayraç virgül ya da noktalı virgül,
 * boşluklar serbest (` 1 - 2 `). 1 tabanlı kapalı aralık; sınır aşımı, ters aralık, çakışma, boş metin → `null` (düğme
 * kapalı kalır; sunucu da 422 der). Kullanıcı aralıkları artan sırada yazmak zorunda DEĞİL; yalnız çakışma reddedilir.
 */
export function bolAraliklariniAyristir(metin: string, toplamSayfa: number): [number, number][] | null {
  const parcalar = metin
    .split(/[,;]+/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (parcalar.length === 0 || toplamSayfa < 1) return null;
  const araliklar: [number, number][] = [];
  for (const p of parcalar) {
    const m = /^(\d+)(?:\s*-\s*(\d+))?$/.exec(p);
    if (!m) return null;
    const bas = Number(m[1]);
    const bit = m[2] === undefined ? bas : Number(m[2]);
    if (!Number.isInteger(bas) || !Number.isInteger(bit) || bas < 1 || bit < bas || bit > toplamSayfa) return null;
    araliklar.push([bas, bit]);
  }
  const sirali = [...araliklar].sort((a, b) => a[0] - b[0]);
  for (let i = 1; i < sirali.length; i++) if (sirali[i][0] <= sirali[i - 1][1]) return null;
  return araliklar;
}

/** Damga sayfa metni → `"hepsi"` ya da sayfa listesi; geçersiz → `null`. */
export function damgaSayfalariniAyristir(metin: string, toplamSayfa: number): "hepsi" | number[] | null {
  const temiz = metin.trim();
  if (!temiz || temiz.toLowerCase() === "hepsi") return "hepsi";
  const araliklar = bolAraliklariniAyristir(temiz, toplamSayfa);
  if (!araliklar) return null;
  const sayfalar: number[] = [];
  for (const [bas, bit] of araliklar) for (let n = bas; n <= bit; n++) sayfalar.push(n);
  return sayfalar;
}

export const pdfAraclariApi = { yukle, islem, onizlemeUrl, onizlemeBlob, indir };
