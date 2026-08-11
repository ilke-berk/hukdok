/**
 * Faz 4.3: /confirm yanıtının değerlendirilmesi — Index.tsx'ten test edilebilir
 * birimlere ayrıldı.
 *
 * Kritik sıra: `response.ok` kontrolü JSON parse'tan ÖNCE. 504'te nginx HTML
 * hata sayfası döndürür; eski akış koşulsuz `response.json()` çağırdığından
 * kullanıcı ham `SyntaxError: Unexpected token '<'` toast'ı görüyordu.
 *
 * Backend sözleşmeleri (3-D/3-F):
 * - 502/503/504: işlem sunucuda hâlâ sürüyor olabilir — kullanıcı belgeyi
 *   TEKRAR YÜKLEMEMELİ; birkaç dakika sonra aynı ekrandan tekrar denemeli
 *   (3-D idempotency kapısı tamamlanmış işlemi aynen döndürür).
 * - 409: aynı process_id ile işlem hâlâ sürüyor; detail "TEKRAR GÖNDERMEYİN"
 *   metnini taşır ve olduğu gibi gösterilir (form sıfırlanmaz).
 * - Başarıda results.idempotent_replay / conversion_pending / conversion_warning
 *   / archived_filename alanları gelebilir.
 */

// Testlerde gerçek Response kurmadan çalışabilmek için yapısal alt küme.
export interface ConfirmHttpResponse {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}

const GATEWAY_STATUSES = new Set([502, 503, 504]);

/**
 * Başarısız (!ok) /confirm yanıtından kullanıcıya gösterilecek mesajı üretir.
 * 502/503/504'te gövde HİÇ okunmaz (nginx HTML'i olabilir); diğer durumlarda
 * FastAPI `detail` alanı denenir, gövde JSON değilse duruma göre genel mesaj.
 */
export async function confirmErrorMessage(response: ConfirmHttpResponse): Promise<string> {
  if (GATEWAY_STATUSES.has(response.status)) {
    return (
      `Sunucudan yanıt alınamadı (HTTP ${response.status}). ` +
      "İşlem sunucuda sürüyor olabilir — belgeyi TEKRAR YÜKLEMEYİN; " +
      "birkaç dakika bekleyip aynı ekrandan kaydetmeyi tekrar deneyin."
    );
  }

  let detail: string | null = null;
  try {
    const body = (await response.json()) as { detail?: unknown } | null;
    if (body && typeof body.detail === "string" && body.detail.trim()) {
      detail = body.detail;
    }
  } catch {
    // Gövde JSON değil — ham SyntaxError kullanıcıya sızmaz, genel mesaja düşülür.
  }

  return detail || `Kayıt işlemi sırasında bir hata oluştu (HTTP ${response.status}).`;
}

/** Başarılı /confirm yanıtındaki 3-D/3-F bayrakları (eksikse güvenli varsayılan). */
export interface ConfirmResultFlags {
  /** 3-D: aynı process_id'nin tamamlanmış işlemi — pipeline tekrar KOŞMADI. */
  idempotentReplay: boolean;
  /** 3-F: PDF dönüşümü başarısız, belge orijinal uzantısıyla arşivlendi; gece denenecek. */
  conversionPending: boolean;
  /** 3-F: gerçek nedenli kullanıcı uyarısı metni. */
  conversionWarning: string | null;
  /** 3-F: arşivde GERÇEKTEN duran dosya adı (orijinal uzantılı). */
  archivedFilename: string | null;
}

export function extractConfirmFlags(result: unknown): ConfirmResultFlags {
  const results =
    result && typeof result === "object"
      ? ((result as { results?: unknown }).results as Record<string, unknown> | undefined)
      : undefined;

  const str = (v: unknown): string | null =>
    typeof v === "string" && v.trim() ? v : null;

  return {
    idempotentReplay: results?.idempotent_replay === true,
    conversionPending: results?.conversion_pending === true,
    conversionWarning: str(results?.conversion_warning),
    archivedFilename: str(results?.archived_filename),
  };
}
