// Hukukbot istemcisi (karar 021, G204) — `/hukukbot` sayfası (G205) Hukukbot'a YALNIZ bununla konuşur.
//
// - Yol: aynı origin `/hukukbot-api/...` (konteyner nginx allowlist'i: ask | sessions | download,
//   önek atılıp hukbot'a iletilir — `nginx.conf`, G203). Ayrı env değişkeni YOK.
// - Kimlik: HukuDok'un MSAL access token'ı (`loginRequest` scope'u, idToken DEĞİL — G8). Token
//   `apiClient.fetch` (lib/api.ts) içinde alınır; 401'de forceRefresh + BİR kez tekrar ve kurtarılamayan
//   401'de oturum-bitti akışı da oradan AYNEN gelir (token yardımcısı kopyalanmaz).
// - Sözleşme: hukbot `app/api.py` + `app/schemas.py`'den okundu → `types/hukukbot.ts`.
// - `/ask`: oturum `session-id` BAŞLIĞIYLA gider (FastAPI `Header()` parametre adındaki `_`'yi `-`'ye
//   çevirir; nginx de alt çizgili başlığı varsayılanda düşürür). Yanıt `application/x-ndjson`.
import { apiClient } from "@/lib/api";
import type {
  HukukbotAkisOlayi,
  HukukbotOturum,
  HukukbotOturumGuncelleme,
  HukukbotOturumOzeti,
  HukukbotSoru,
} from "@/types/hukukbot";

/** Tüm çağrıların öneki — göreli, aynı origin. */
export const HUKUKBOT_API_ONEKI = "/hukukbot-api";

export const HUKUKBOT_YETKI_MESAJI = "Hukukbot oturumunuzu doğrulayamadı. Sayfayı yenileyip tekrar giriş yapın.";
export const HUKUKBOT_HIZ_MESAJI = "Çok fazla soru gönderdiniz. Lütfen bir dakika sonra tekrar deneyin.";
export const HUKUKBOT_GENEL_HATA = "Hukukbot isteği tamamlanamadı.";
export const HUKUKBOT_AKIS_YOK = "Hukukbot yanıt akışı okunamadı.";

/** Genel HTTP hatası — `status` ve (varsa) sunucunun `detail` metni. */
export class HukukbotApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "HukukbotApiError";
    this.status = status;
  }
}

/** 401 — token yenilemesi sonrası da reddedildi (oturum-bitti akışı `apiClient`'ta tetiklendi). */
export class HukukbotYetkiError extends HukukbotApiError {
  constructor() {
    super(401, HUKUKBOT_YETKI_MESAJI);
    this.name = "HukukbotYetkiError";
  }
}

/** 429 — hukbot'un kullanıcı başına `/ask` hız sınırı (varsayılan dakikada 20). */
export class HukukbotHizSiniriError extends HukukbotApiError {
  constructor(message: string = HUKUKBOT_HIZ_MESAJI) {
    super(429, message);
    this.name = "HukukbotHizSiniriError";
  }
}

function hukukbotYolu(yol: string): string {
  return `${HUKUKBOT_API_ONEKI}${yol.startsWith("/") ? yol : "/" + yol}`;
}

/** FastAPI hata gövdesinden (`{"detail": "..."}`) okunur metin; okunamazsa `yedek`. */
async function detayOku(res: Response, yedek: string): Promise<string> {
  try {
    const govde = (await res.json()) as { detail?: unknown };
    if (typeof govde?.detail === "string" && govde.detail.trim()) return govde.detail;
  } catch {
    /* gövde JSON değil / boş — yedek metin */
  }
  return yedek;
}

/** Başarısız yanıtı tipli hataya çevirir: 401 → Yetki, 429 → HızSınırı, diğerleri → ApiError. */
async function hataUret(res: Response): Promise<HukukbotApiError> {
  if (res.status === 401) return new HukukbotYetkiError();
  if (res.status === 429) return new HukukbotHizSiniriError(await detayOku(res, HUKUKBOT_HIZ_MESAJI));
  return new HukukbotApiError(res.status, await detayOku(res, `${HUKUKBOT_GENEL_HATA} (HTTP ${res.status})`));
}

async function istek(yol: string, secenekler: RequestInit = {}): Promise<Response> {
  const res = await apiClient.fetch(hukukbotYolu(yol), secenekler);
  if (!res.ok) throw await hataUret(res);
  return res;
}

async function jsonIstek<T>(yol: string, secenekler: RequestInit = {}): Promise<T> {
  const res = await istek(yol, secenekler);
  return (await res.json()) as T;
}

const oturumYolu = (id: string) => `/sessions/${encodeURIComponent(id)}`;

// --- Oturum CRUD ----------------------------------------------------------

/** `GET /sessions` — pinliler önce, sonra en yeni; mesaj gövdesi yok. */
export function oturumlariListele(signal?: AbortSignal): Promise<HukukbotOturumOzeti[]> {
  return jsonIstek<HukukbotOturumOzeti[]>("/sessions", { signal });
}

/** `GET /sessions/{id}` — mesajlarıyla. */
export function oturumGetir(id: string, signal?: AbortSignal): Promise<HukukbotOturum> {
  return jsonIstek<HukukbotOturum>(oturumYolu(id), { signal });
}

/** `POST /sessions` — gövde `{title}`. */
export function oturumOlustur(title: string): Promise<HukukbotOturum> {
  return jsonIstek<HukukbotOturum>("/sessions", { method: "POST", body: JSON.stringify({ title }) });
}

/** `PATCH /sessions/{id}` — başlık ve/veya `is_pinned`; yanıtta `messages` boştur. */
export function oturumGuncelle(id: string, degisiklik: HukukbotOturumGuncelleme): Promise<HukukbotOturum> {
  return jsonIstek<HukukbotOturum>(oturumYolu(id), { method: "PATCH", body: JSON.stringify(degisiklik) });
}

/** `DELETE /sessions/{id}`. */
export async function oturumSil(id: string): Promise<void> {
  await istek(oturumYolu(id), { method: "DELETE" });
}

// --- /ask NDJSON akışı -----------------------------------------------------

export interface SoruSecenekleri {
  /** Mevcut oturum; yoksa hukbot yeni oturum açar (başlık = sorunun ilk 50 karakteri). */
  sessionId?: string | null;
  /** İptal: istek öncesi ya da akış SIRASINDA — okuyucu kapatılır, `AbortError` fırlar. */
  signal?: AbortSignal;
}

function iptalHatasi(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("İstek iptal edildi.", "AbortError");
}

function olayCoz(satir: string): HukukbotAkisOlayi | null {
  if (!satir.trim()) return null;
  let olay: { type?: unknown; data?: unknown };
  try {
    olay = JSON.parse(satir);
  } catch (e) {
    console.warn("Hukukbot akışında bozuk satır atlandı", e);
    return null;
  }
  switch (olay?.type) {
    case "content":
      return { type: "content", data: typeof olay.data === "string" ? olay.data : "" };
    case "sources":
      return { type: "sources", data: Array.isArray(olay.data) ? olay.data : [] };
    case "status":
      return typeof olay.data === "string" && olay.data.trim() ? { type: "status", data: olay.data } : null;
    case "error":
      return { type: "error", data: typeof olay.data === "string" ? olay.data : HUKUKBOT_GENEL_HATA };
    default:
      // Sözleşme dışı tür: yok sayılır (sunucu yeni tür eklerse istemci kırılmaz).
      return null;
  }
}

/**
 * `POST /ask` — olayları satır satır veren async iterator:
 * `for await (const olay of ask({question}, {sessionId, signal})) { ... }`.
 * Parça sınırında bölünen satır tamponda birleşir; akış `\n`'siz biterse son satır da işlenir.
 * HTTP hataları akış başlamadan tipli hata olarak fırlar (401/429 ayrı türler).
 */
export async function* ask(
  soru: HukukbotSoru,
  secenekler: SoruSecenekleri = {},
): AsyncGenerator<HukukbotAkisOlayi, void, undefined> {
  const { sessionId, signal } = secenekler;
  const headers: Record<string, string> = {};
  if (sessionId) headers["session-id"] = sessionId;

  const res = await istek("/ask", {
    method: "POST",
    headers,
    body: JSON.stringify(soru),
    signal,
  });
  if (!res.body) throw new Error(HUKUKBOT_AKIS_YOK);

  const reader = res.body.getReader();
  // apiClient çağıranın sinyalini yalnız yanıt başlıklarına kadar fetch'e bağlar; akış
  // sırasındaki iptal burada okuyucuyu kapatarak işlenir.
  const iptalEt = () => {
    reader.cancel().catch(() => undefined);
  };
  signal?.addEventListener("abort", iptalEt, { once: true });

  const decoder = new TextDecoder();
  let tampon = "";
  let bitti = false;
  try {
    if (signal?.aborted) throw iptalHatasi(signal);
    while (true) {
      const { value, done } = await reader.read();
      if (signal?.aborted) throw iptalHatasi(signal);
      if (value) {
        tampon += decoder.decode(value, { stream: true });
        const satirlar = tampon.split("\n");
        tampon = satirlar.pop() ?? ""; // yarım satır tamponda bekler
        for (const satir of satirlar) {
          const olay = olayCoz(satir);
          if (olay) yield olay;
        }
      }
      if (done) {
        tampon += decoder.decode();
        const olay = olayCoz(tampon); // `\n`'siz gelen son satır
        tampon = "";
        if (olay) yield olay;
        bitti = true;
        break;
      }
    }
  } finally {
    signal?.removeEventListener("abort", iptalEt);
    // Tüketici erken çıktıysa (break/return/hata) bağlantıyı bırak.
    if (!bitti) reader.cancel().catch(() => undefined);
  }
}

// --- Yetkili PDF indirme ---------------------------------------------------

/**
 * `GET /download/{filename}` — düz `<a href>` ÇALIŞMAZ (Authorization gerekir): `fetch` + blob +
 * geçici object URL + `<a download>`; URL tıklamadan hemen sonra `revokeObjectURL` ile bırakılır.
 */
export async function indir(filename: string): Promise<void> {
  const res = await istek(`/download/${encodeURIComponent(filename)}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
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

/**
 * HukuDok'tan aktarılmış kaynağı HukuDok'un KENDİ ucundan açar: `GET /api/documents/{id}/download?inline=true`
 * (SharePoint arşivinden HukuDok'un uygulama yetkisiyle; kullanıcının SharePoint üyeliği gerekmez — iki büro
 * için de çalışır). Hukukbot'a DEĞİL HukuDok backend'ine gider (önek yok).
 *
 * `sekme`: tıklama anında (ilk `await`'ten ÖNCE) `window.open("", "_blank")` ile açılmış boş sekme — sonradan
 * açılan sekmeyi pop-up engelleyicisi keser. `noopener` KULLANILMAZ: blob URL'i opener bağlamında üretilir
 * (CaseDetails "Görüntüle" ile aynı desen). Sekme yoksa (engellendiyse) yeni pencere denenir.
 */
export async function hukudokBelgesiniAc(belgeId: number, sekme: Window | null): Promise<void> {
  const res = await apiClient.fetch(`/api/documents/${encodeURIComponent(String(belgeId))}/download?inline=true`);
  if (!res.ok) {
    throw new HukukbotApiError(res.status, await detayOku(res, `Belge HukuDok arşivinden açılamadı (HTTP ${res.status}).`));
  }
  const url = URL.createObjectURL(await res.blob());
  if (sekme) sekme.location.href = url;
  else window.open(url, "_blank");
  // Sekme blob'u okuyabilsin diye URL biraz sonra bırakılır.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Sayfanın tek giriş noktası (G205): `hukukbotApi.ask(...)` vb. */
export const hukukbotApi = {
  oturumlariListele,
  oturumGetir,
  oturumOlustur,
  oturumGuncelle,
  oturumSil,
  ask,
  indir,
  hukudokBelgesiniAc,
};
