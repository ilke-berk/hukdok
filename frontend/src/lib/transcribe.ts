/**
 * Sesi yazıya çevirme istemcisi (G217; backend sözleşmesi `gorevler/gorev/G216.md` "Sözleşme").
 *
 * - `POST /api/transcribe`, `multipart/form-data`, tek alan `ses` (dosya) → 200 `{"metin": str}`
 *   (strip'li; konuşma yoksa boş string).
 * - 413 (> 2 MB) · 415 (desteklenmeyen tür) · 422 (boş dosya) · 503 (Gemini meşgul/başarısız) ayrı
 *   Türkçe mesajla `SesCeviriHatasi` fırlatır; çağıran mesajı kutunun altında gösterir.
 *
 * Ses Hukukbot'a GİTMEZ — yalnız HukuDok. İstek `apiClient` üzerinden gider (Bearer + 401'de sessiz
 * yenileme + FormData gövdesi → uzun zaman aşımı katmanı). Çağıranın `signal`'i iptalde aynen fırlar
 * (AbortError) — hook bunu hata saymaz.
 */
import { apiClient } from "@/lib/api";

export const SES_UCU = "/api/transcribe";

/** Sunucunun 503 gövdesindeki sabit metin (sözleşme); gövde okunamazsa da bu gösterilir. */
export const SES_MESGUL_MESAJI = "Ses şu an yazıya çevrilemedi, lütfen tekrar deneyin.";

export const SES_HATA_MESAJLARI: Readonly<Record<number, string>> = {
    413: "Kayıt çok uzun (2 MB sınırı aşıldı). Daha kısa konuşup tekrar deneyin.",
    415: "Bu tarayıcının ses kayıt biçimi desteklenmiyor.",
    422: "Ses kaydı boş geldi. Tekrar deneyin.",
    503: SES_MESGUL_MESAJI,
};

const GENEL_HATA = "Ses yazıya çevrilemedi.";

export class SesCeviriHatasi extends Error {
    readonly status: number;

    constructor(message: string, status: number) {
        super(message);
        this.name = "SesCeviriHatasi";
        this.status = status;
    }
}

/** MIME türü → dosya uzantısı; `;codecs=opus` gibi parametreler atılır. Tanınmayan tür `webm`. */
export function sesUzantisi(tur: string): string {
    const temel = tur.split(";")[0].trim().toLowerCase();
    switch (temel) {
        case "audio/webm":
            return "webm";
        case "audio/ogg":
            return "ogg";
        case "audio/mp4":
            return "m4a";
        case "audio/mpeg":
            return "mp3";
        case "audio/wav":
            return "wav";
        default:
            return "webm";
    }
}

async function detayOku(res: Response): Promise<string | null> {
    try {
        const govde = (await res.json()) as { detail?: unknown };
        return typeof govde?.detail === "string" && govde.detail.trim() ? govde.detail : null;
    } catch {
        return null;
    }
}

/** Kaydı sunucuya gönderir, yazıya çevrilmiş metni (trim'li; konuşma yoksa "") döner. */
export async function sesiYaziyaCevir(blob: Blob, signal?: AbortSignal): Promise<string> {
    const form = new FormData();
    form.append("ses", blob, `kayit.${sesUzantisi(blob.type)}`);
    const res = await apiClient.fetch(SES_UCU, { method: "POST", body: form, signal });
    if (!res.ok) {
        if (res.status === 503) {
            throw new SesCeviriHatasi((await detayOku(res)) ?? SES_MESGUL_MESAJI, 503);
        }
        if (res.status === 401) {
            throw new SesCeviriHatasi("Oturum süresi doldu; tekrar giriş yapın.", 401);
        }
        throw new SesCeviriHatasi(SES_HATA_MESAJLARI[res.status] ?? GENEL_HATA, res.status);
    }
    const govde = (await res.json()) as { metin?: unknown };
    return typeof govde?.metin === "string" ? govde.metin.trim() : "";
}
