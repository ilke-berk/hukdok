/**
 * Dava kartının tarihli notları (G215; backend sözleşmesi `gorevler/gorev/G214.md` "Sözleşme").
 *
 * - `GET    /api/cases/{id}/notes`            → 200 `CaseNote[]` (en yeni üstte, silinmişler hariç)
 * - `POST   /api/cases/{id}/notes` `{body}`   → 201 tek `CaseNote`; trim sonrası 1-5000 karakter, aksi 422
 * - `DELETE /api/cases/{id}/notes/{noteId}`   → 204; yazan/admin değil 403, yok/başka dava 404
 *
 * Eski tek serbest metin alanı (`cases.notes`) bundan ayrıdır — kartta "Genel not" olarak kalır.
 * Tüm çağrılar `apiClient` (Bearer + zaman aşımı + GET tekrar denemesi) üzerinden gider; başarısız
 * yanıt Türkçe mesajlı `CaseNoteError` fırlatır (çağıran toast'lar / panelde gösterir).
 */
import { apiClient } from "@/lib/api";

export interface CaseNote {
    id: number;
    body: string;
    author_name: string | null;
    author_email: string;
    /** ISO 8601, UTC ("Z" ya da offset'li). */
    created_at: string;
    can_delete: boolean;
}

/** Sunucu sınırıyla aynı (trim sonrası). */
export const NOT_AZAMI_UZUNLUK = 5000;
/** Kalan karakter göstergesi bu uzunluktan SONRA görünür. */
export const NOT_SAYAC_ESIGI = 4500;

export class CaseNoteError extends Error {
    readonly status: number;

    constructor(message: string, status: number) {
        super(message);
        this.name = "CaseNoteError";
        this.status = status;
    }
}

/** Ekle düğmesi yalnız trim sonrası 1..5000 karakterde etkin. */
export function notGecerliMi(body: string): boolean {
    const t = body.trim();
    return t.length > 0 && t.length <= NOT_AZAMI_UZUNLUK;
}

/** Yazan adı; yoksa (null/boş) e-posta. */
export function yazanEtiketi(note: Pick<CaseNote, "author_name" | "author_email">): string {
    const ad = note.author_name?.trim();
    return ad ? ad : note.author_email;
}

/** TR biçimli tarih-saat, Türkiye saatiyle (tarayıcının dilimi ne olursa olsun). */
export function notTarihi(iso: string): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return new Intl.DateTimeFormat("tr-TR", {
        timeZone: "Europe/Istanbul",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
    }).format(d);
}

const notlarYolu = (caseId: number) => `/api/cases/${encodeURIComponent(String(caseId))}/notes`;

export async function listele(caseId: number): Promise<CaseNote[]> {
    const res = await apiClient.fetch(notlarYolu(caseId));
    if (!res.ok) {
        throw new CaseNoteError(
            res.status === 404 ? "Dava bulunamadı." : "Notlar yüklenemedi.",
            res.status,
        );
    }
    return (await res.json()) as CaseNote[];
}

export async function ekle(caseId: number, body: string): Promise<CaseNote> {
    const res = await apiClient.fetch(notlarYolu(caseId), {
        method: "POST",
        body: JSON.stringify({ body }),
    });
    if (!res.ok) {
        const mesaj =
            res.status === 422 ? `Not boş olamaz ve en fazla ${NOT_AZAMI_UZUNLUK} karakter olabilir.`
            : res.status === 404 ? "Dava bulunamadı."
            : "Not eklenemedi.";
        throw new CaseNoteError(mesaj, res.status);
    }
    return (await res.json()) as CaseNote;
}

export async function sil(caseId: number, noteId: number): Promise<void> {
    const res = await apiClient.fetch(
        `${notlarYolu(caseId)}/${encodeURIComponent(String(noteId))}`,
        { method: "DELETE" },
    );
    if (!res.ok) {
        const mesaj =
            res.status === 403 ? "Bu notu silme yetkiniz yok (yalnız yazan ya da yönetici silebilir)."
            : res.status === 404 ? "Not bulunamadı; daha önce silinmiş olabilir."
            : "Not silinemedi.";
        throw new CaseNoteError(mesaj, res.status);
    }
}
