// Emsal ajan hattının NDJSON okuyucusu — `POST /lexis-api/emsal-ara` (G264; `hukukbotApi.ask` okuyucusunun AYNI
// deseni: satır tamponu, `AbortSignal` ile okuyucu kapatma, sözleşme dışı tür yok sayılır).
//
// - Olaylar `types/lexis.ts` `EmsalAkisOlayi` (HUKDOK stream sözleşmesi): `info | warning | complete | failed`;
//   `failed` SON olaydır — okuyucu ondan sonra okumaz. Tanınmayan `status` ve bozuk satır atlanır (sunucu yeni tür
//   eklerse istemci kırılmaz).
// - HTTP hatası akış başlamadan `LexisApiError` olarak fırlar: 401 yetki, 409 "koşu sürüyor", 429 gün kotası,
//   503 hat kapalı (sahte / gemini kipi anahtarsız) — sunucunun `detail` metni varsa o, yoksa buradaki yedek.
// - Kimlik HUKDOK'un MSAL access token'ı (`apiClient.fetch`). Bu modül `lexisServis.ts` gibi DİNAMİK yüklenir:
//   örnek kip `apiClient`'ı hiç yüklemez.
import { apiClient } from "@/lib/api";
import { LexisApiError } from "@/lib/lexisApi";
import { LEXIS_API_ONEKI, LEXIS_YETKI_MESAJI } from "@/lib/lexisWord";
import type { EmsalAkisOlayi, EmsalAsamasi, EmsalOnerisi, EmsalSonucu, KunyeAkisOlayi, KunyeAkisSecenekleri, KunyeOkunamayan, KunyeOnerisi } from "@/types/lexis";

/** `lexisServis.LEXIS_DAVA_SERVISI_YOK` ile aynı metin (döngüsel içe aktarma olmasın diye burada yinelenir). */
export const EMSAL_SERVIS_YOK = "Lexis servisine ulaşılamadı.";
export const EMSAL_AKIS_YOK = "Emsal arama akışı okunamadı.";
export const EMSAL_KOSU_SURUYOR = "Bir emsal aramanız zaten sürüyor; bitmesini bekleyin.";
export const EMSAL_KOTA_DOLDU = "Günlük model token tavanı doldu; yarın yeniden deneyin.";
export const EMSAL_HAT_KAPALI = "Emsal ajan hattı bu kurulumda kapalı.";
export const EMSAL_GENEL_HATA = "Emsal araması başlatılamadı.";
export const KUNYE_HAT_KAPALI = "Belgeden künye çıkarımı bu kurulumda kapalı.";
export const KUNYE_GENEL_HATA = "Künye çıkarımı başlatılamadı.";

export interface EmsalAkisSecenekleri {
  /** Aday tavanı (≤ 100); yoksa servisin `LEXIS_EMSAL_ADAY` değeri. */
  aday?: number;
  /** Künye ve okumalar önbellekten değil yeniden üretilir. */
  yeniden?: boolean;
  /** İptal: istek öncesi ya da akış SIRASINDA — okuyucu kapatılır, `AbortError` fırlar. */
  signal?: AbortSignal;
}

const ASAMALAR: readonly string[] = ["kunye", "aday", "okuma", "denetim"];

async function detayOku(res: Response): Promise<string | null> {
  if (!(res.headers.get("Content-Type") ?? "").includes("application/json")) return null;
  const govde = (await res.json().catch(() => null)) as { detail?: unknown } | null;
  const detail = govde?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  // `/emsal-belge` deseni: `detail: {kod, mesaj}`.
  if (detail && typeof detail === "object" && typeof (detail as { mesaj?: unknown }).mesaj === "string") return (detail as { mesaj: string }).mesaj;
  return null;
}

const EMSAL_YEDEKLERI: Record<number, string> = { 409: EMSAL_KOSU_SURUYOR, 429: EMSAL_KOTA_DOLDU, 503: EMSAL_HAT_KAPALI };

/** Başarısız yanıtı tipli hataya çevirir; akış hiç başlamaz. `yedek`: sunucu `detail` vermezse durum koduna göre metin. */
async function hataUret(res: Response, yedek: Record<number, string> = EMSAL_YEDEKLERI, genel = EMSAL_GENEL_HATA): Promise<LexisApiError> {
  if (res.status === 401) return new LexisApiError(401, LEXIS_YETKI_MESAJI);
  const detay = await detayOku(res);
  if (detay) return new LexisApiError(res.status, detay);
  if (yedek[res.status]) return new LexisApiError(res.status, yedek[res.status]);
  return new LexisApiError(res.status, [404, 502, 504].includes(res.status) ? EMSAL_SERVIS_YOK : `${genel} (HTTP ${res.status})`);
}

function iptalHatasi(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("İstek iptal edildi.", "AbortError");
}

const nesne = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const metin = (v: unknown, yedek = ""): string => (typeof v === "string" ? v : yedek);

/** Öneri satırı: `id` ve `puan` sayı olmalı; eksik liste alanları boş listeyle dolar (ekran `map` çağırır). */
function oneriCoz(ham: unknown): EmsalOnerisi | null {
  if (!nesne(ham) || typeof ham.id !== "number" || typeof ham.puan !== "number") return null;
  const liste = (v: unknown) => (Array.isArray(v) ? v : []);
  return {
    ...(ham as unknown as EmsalOnerisi),
    gerekce: metin(ham.gerekce),
    alinti: metin(ham.alinti),
    fark: metin(ham.fark),
    ayni_kart: ham.ayni_kart === true,
    kaynak: metin(ham.kaynak, "model"),
    fts_sira: typeof ham.fts_sira === "number" ? ham.fts_sira : null,
    denetim_uyarilari: liste(ham.denetim_uyarilari).filter((u): u is string => typeof u === "string"),
    bilesenler: liste(ham.bilesenler),
    hukum_yonleri: liste(ham.hukum_yonleri),
    hukmedilen_maddi: liste(ham.hukmedilen_maddi),
    hukmedilen_manevi: liste(ham.hukmedilen_manevi),
    hukmedilen_birlesik: liste(ham.hukmedilen_birlesik),
    talep_maddi: liste(ham.talep_maddi),
    talep_manevi: liste(ham.talep_manevi),
    maluliyet_orani: liste(ham.maluliyet_orani),
    kusur_orani: liste(ham.kusur_orani),
    dayanak_kurul: liste(ham.dayanak_kurul),
    faiz: liste(ham.faiz),
    konular: nesne(ham.konular) ? (ham.konular as Record<string, number>) : {},
  };
}

/** `complete` gövdesini `EmsalSonucu`ya çevirir; öneri listesi yoksa `null` (sözleşme dışı). */
export function sonucCoz(ham: unknown): EmsalSonucu | null {
  if (!nesne(ham) || !Array.isArray(ham.oneriler)) return null;
  const kunye = nesne(ham.kunye) ? ham.kunye : {};
  const sayilar = nesne(ham.sayilar) ? ham.sayilar : {};
  const sayi = (v: unknown) => (typeof v === "number" ? v : 0);
  return {
    sha256: metin(ham.sha256),
    kunye: {
      uzmanlik: metin(kunye.uzmanlik) || null,
      tibbi_islem: metin(kunye.tibbi_islem) || null,
      iddia: metin(kunye.iddia),
      taraf_turu: metin(kunye.taraf_turu) || null,
      yargi_yolu: metin(kunye.yargi_yolu, "DIGER"),
      sorgular: (Array.isArray(kunye.sorgular) ? kunye.sorgular : []).flatMap((s: unknown) => (nesne(s) && typeof s.metin === "string" ? [{ metin: s.metin, tur: metin(s.tur) }] : [])),
      ...(typeof kunye.istem_surumu === "string" ? { istem_surumu: kunye.istem_surumu } : {}),
    },
    model: metin(ham.model),
    sorgu_modeli: metin(ham.sorgu_modeli),
    oneriler: ham.oneriler.flatMap((o) => {
      const oneri = oneriCoz(o);
      return oneri ? [oneri] : [];
    }),
    sayilar: {
      aday: sayi(sayilar.aday),
      okunan: sayi(sayilar.okunan),
      dusen: sayi(sayilar.dusen),
      onbellek: sayi(sayilar.onbellek),
      model_cagrisi: sayi(sayilar.model_cagrisi),
      token: sayi(sayilar.token),
      saniye: sayi(sayilar.saniye),
      ...(typeof sayilar.kaynak === "string" ? { kaynak: sayilar.kaynak } : {}),
    },
  };
}

/** NDJSON satırı → tipli olay; boş / bozuk satır ve sözleşme dışı tür `null`. */
export function olayCoz(satir: string): EmsalAkisOlayi | null {
  if (!satir.trim()) return null;
  let ham: unknown;
  try {
    ham = JSON.parse(satir);
  } catch (e) {
    console.warn("Emsal akışında bozuk satır atlandı", e);
    return null;
  }
  if (!nesne(ham)) return null;
  switch (ham.status) {
    case "info": {
      if (typeof ham.asama !== "string" || !ASAMALAR.includes(ham.asama)) return null;
      const ilerleme = Array.isArray(ham.ilerleme) && ham.ilerleme.length === 2 && ham.ilerleme.every((n) => typeof n === "number") ? (ham.ilerleme as [number, number]) : undefined;
      const sayi = (v: unknown) => (typeof v === "number" ? v : undefined);
      return {
        status: "info",
        asama: ham.asama as EmsalAsamasi,
        ...(typeof ham.mesaj === "string" ? { mesaj: ham.mesaj } : {}),
        ...(ilerleme ? { ilerleme } : {}),
        ...(typeof ham.kaynak === "string" ? { kaynak: ham.kaynak } : {}),
        ...(sayi(ham.aday) !== undefined ? { aday: sayi(ham.aday) } : {}),
        ...(sayi(ham.sorgu) !== undefined ? { sorgu: sayi(ham.sorgu) } : {}),
        ...(sayi(ham.ayni_kart) !== undefined ? { ayni_kart: sayi(ham.ayni_kart) } : {}),
        ...(sayi(ham.gecen) !== undefined ? { gecen: sayi(ham.gecen) } : {}),
        ...(sayi(ham.dusen) !== undefined ? { dusen: sayi(ham.dusen) } : {}),
        ...(sayi(ham.belge_id) !== undefined ? { belge_id: sayi(ham.belge_id) } : {}),
      };
    }
    case "warning":
      return {
        status: "warning",
        message: metin(ham.message) || metin(ham.mesaj) || "Uyarı",
        ...(typeof ham.asama === "string" && ASAMALAR.includes(ham.asama) ? { asama: ham.asama as EmsalAsamasi } : {}),
        ...(typeof ham.belge_id === "number" ? { belge_id: ham.belge_id } : {}),
        ...(typeof ham.error_kod === "string" ? { error_kod: ham.error_kod } : {}),
      };
    case "complete": {
      const sonuc = sonucCoz(ham);
      return sonuc ? { status: "complete", ...sonuc } : null;
    }
    case "failed":
      return { status: "failed", error_ozet: metin(ham.error_ozet) || EMSAL_GENEL_HATA, error_kod: metin(ham.error_kod, "analysis_error") || "analysis_error" };
    default:
      return null;
  }
}

/**
 * `POST /lexis-api/emsal-ara` — olayları satır satır veren async iterator:
 * `for await (const olay of emsalAkisi(sha, { signal })) { ... }`.
 * Parça sınırında bölünen satır tamponda birleşir; akış `\n`'siz biterse son satır da işlenir; `failed`
 * görülünce okuma biter (sunucu da kapatır). HTTP hataları akış başlamadan `LexisApiError` olarak fırlar.
 */
export async function* emsalAkisi(sha256: string, secenekler: EmsalAkisSecenekleri = {}): AsyncGenerator<EmsalAkisOlayi, void, undefined> {
  const { aday, yeniden, signal } = secenekler;
  const govde = { sha256, ...(aday ? { aday } : {}), ...(yeniden ? { yeniden: true } : {}) };
  yield* ndjsonAkisi("/emsal-ara", govde, olayCoz, signal, EMSAL_YEDEKLERI, EMSAL_GENEL_HATA);
}

/** Genel NDJSON okuyucu (emsal ve künye akışı): POST + satır tamponu + iptal; `failed` SON olaydır. */
async function* ndjsonAkisi<T extends { status: string }>(
  yol: string,
  govde: unknown,
  coz: (satir: string) => T | null,
  signal: AbortSignal | undefined,
  yedek: Record<number, string>,
  genel: string,
): AsyncGenerator<T, void, undefined> {
  let res: Response;
  try {
    res = await apiClient.fetch(`${LEXIS_API_ONEKI}${yol}`, { method: "POST", body: JSON.stringify(govde), signal });
  } catch (e) {
    if ((e as Error)?.name === "AbortError") throw e;
    throw new LexisApiError(0, EMSAL_SERVIS_YOK);
  }
  if (!res.ok) throw await hataUret(res, yedek, genel);
  // Proxy ucu tanımıyorsa istek SPA'ya düşüp 200 + HTML dönebilir.
  if (!(res.headers.get("Content-Type") ?? "").includes("ndjson")) throw new LexisApiError(502, EMSAL_SERVIS_YOK);
  if (!res.body) throw new LexisApiError(502, EMSAL_AKIS_YOK);

  const reader = res.body.getReader();
  // apiClient çağıranın sinyalini yalnız yanıt başlıklarına kadar fetch'e bağlar; akış sırasındaki iptal burada
  // okuyucuyu kapatarak işlenir.
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
          const olay = coz(satir);
          if (!olay) continue;
          yield olay;
          if (olay.status === "failed") return; // SON olay: gerisi okunmaz
        }
      }
      if (done) {
        tampon += decoder.decode();
        const olay = coz(tampon); // `\n`'siz gelen son satır
        tampon = "";
        bitti = true;
        if (olay) yield olay;
        break;
      }
    }
  } finally {
    signal?.removeEventListener("abort", iptalEt);
    // Tüketici erken çıktıysa (break / return / hata / failed) bağlantıyı bırak.
    if (!bitti) reader.cancel().catch(() => undefined);
  }
}

// --- belgeden künye çıkarımı (`POST /lexis-api/kunye-oneri`, Aşama 13) -----------------------------

const KUNYE_YEDEKLERI: Record<number, string> = { 503: KUNYE_HAT_KAPALI };

/** Öneri satırı: `id`, `belge_id` sayı, `alan` / `deger` metin olmalı; değilse `null`. */
export function kunyeOnerisiCoz(ham: unknown): KunyeOnerisi | null {
  if (!nesne(ham) || typeof ham.id !== "number" || typeof ham.belge_id !== "number" || typeof ham.alan !== "string" || typeof ham.deger !== "string") return null;
  return {
    ...(ham as unknown as KunyeOnerisi),
    alinti: metin(ham.alinti),
    deger_sayi: typeof ham.deger_sayi === "number" ? ham.deger_sayi : null,
    kart_degeri: typeof ham.kart_degeri === "string" ? ham.kart_degeri : null,
    durum: ham.durum === "kabul" || ham.durum === "ret" ? ham.durum : "oneri",
  };
}

const okunamayanlar = (v: unknown): KunyeOkunamayan[] =>
  (Array.isArray(v) ? v : []).filter((o): o is KunyeOkunamayan => nesne(o) && typeof o.belge_id === "number").map((o) => ({ belge_id: o.belge_id, neden: metin(o.neden) }));

/** Künye akışının NDJSON satırı → tipli olay; bozuk satır ve tanınmayan tür `null`. */
export function kunyeOlayCoz(satir: string): KunyeAkisOlayi | null {
  if (!satir.trim()) return null;
  let ham: unknown;
  try {
    ham = JSON.parse(satir);
  } catch {
    return null;
  }
  if (!nesne(ham)) return null;
  const sayi = (v: unknown) => (typeof v === "number" ? v : undefined);
  switch (ham.status) {
    case "info":
      return {
        status: "info",
        asama: metin(ham.asama),
        ...(sayi(ham.belge_id) !== undefined ? { belge_id: sayi(ham.belge_id) } : {}),
        ...(sayi(ham.sira) !== undefined ? { sira: sayi(ham.sira) } : {}),
        ...(sayi(ham.toplam) !== undefined ? { toplam: sayi(ham.toplam) } : {}),
        ...(sayi(ham.aday) !== undefined ? { aday: sayi(ham.aday) } : {}),
      };
    case "warning":
      return {
        status: "warning",
        message: metin(ham.message) || "Uyarı",
        ...(typeof ham.asama === "string" ? { asama: ham.asama } : {}),
        ...(sayi(ham.belge_id) !== undefined ? { belge_id: sayi(ham.belge_id) } : {}),
      };
    case "complete": {
      if (!Array.isArray(ham.oneriler)) return null;
      const sayilar: Record<string, number> = {};
      if (nesne(ham.sayilar)) for (const [k, v] of Object.entries(ham.sayilar)) if (typeof v === "number") sayilar[k] = v;
      return {
        status: "complete",
        case_id: sayi(ham.case_id) ?? 0,
        model: metin(ham.model),
        oneriler: ham.oneriler.map(kunyeOnerisiCoz).filter((o): o is KunyeOnerisi => o !== null),
        okunamayanlar: okunamayanlar(ham.okunamayanlar),
        sayilar,
      };
    }
    case "failed":
      return {
        status: "failed",
        error_ozet: metin(ham.error_ozet) || KUNYE_GENEL_HATA,
        error_kod: metin(ham.error_kod) || "analysis_error",
        ...(Array.isArray(ham.okunamayanlar) ? { okunamayanlar: okunamayanlar(ham.okunamayanlar) } : {}),
      };
    default:
      return null;
  }
}

/** `POST /lexis-api/kunye-oneri` — künye çıkarımı akışı. Gerçek kipte `onay: true` olmadan sunucu 422 döner. */
export async function* kunyeAkisi(caseId: number, secenekler: KunyeAkisSecenekleri = {}): AsyncGenerator<KunyeAkisOlayi, void, undefined> {
  const { belgeIdleri, onay, yeniden, signal } = secenekler;
  const govde = { case_id: caseId, ...(belgeIdleri ? { belge_idleri: belgeIdleri } : {}), ...(onay ? { onay: true } : {}), ...(yeniden ? { yeniden: true } : {}) };
  yield* ndjsonAkisi("/kunye-oneri", govde, kunyeOlayCoz, signal, KUNYE_YEDEKLERI, KUNYE_GENEL_HATA);
}
