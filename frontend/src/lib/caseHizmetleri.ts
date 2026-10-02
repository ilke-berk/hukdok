/**
 * Dava kartının hizmet kayıtları (G252; backend sözleşmesi `routes/case_hizmetleri.py`, G248).
 *
 * "Bu kartta bu müvekkile bu hizmet verildi" satırları — muhasebe ayrımı müvekkil başınadır.
 *
 * - `GET /api/cases/{id}/hizmetler`                       → 200 `CaseHizmeti[]` (müvekkil adı → hizmet adı sıralı)
 * - `PUT /api/cases/{id}/hizmetler/{case_party_id}` `{hizmet_turleri}` → 200 kartın güncel listesi.
 *   Müvekkilin ELLE kümesi verilen kümeye getirilir (eksik eklenir, fazla elle satır silinir);
 *   föy kaynaklı satıra dokunulmaz; boş liste = elle satırların tamamı silinir.
 *
 * Hatalar: 404 dava yok; 422 taraf bu kartın müvekkili değil / hizmet adı `service_types`
 * listesinde yok (hiçbir satır yazılmaz); 409 kayıt toplu veri işleminde kilitli. Sunucu
 * `detail`'i Türkçe metin olarak verir — varsa o gösterilir, yoksa buradaki varsayılan.
 *
 * Tüm çağrılar `apiClient` üzerinden gider; başarısız yanıt Türkçe mesajlı `CaseHizmetError` fırlatır.
 */
import { apiClient } from "@/lib/api";

export type HizmetKaynagi = "foy" | "elle";

export interface CaseHizmeti {
    id: number;
    case_party_id: number;
    muvekkil_adi: string | null;
    hizmet_turu: string;
    /** "foy": aktarım yazdı, panelden değişmez · "elle": panelden seçildi. */
    kaynak: HizmetKaynagi;
    foy_id: number | null;
    /** Yalnız föy kaynaklı satırda dolu. */
    sistem_no: string | null;
}

/** Panelin müvekkil satırı için gereken alt küme (`cases.parties` CLIENT satırı). */
export interface HizmetMuvekkili {
    id: number;
    name: string;
}

export interface MuvekkilHizmetGrubu {
    casePartyId: number;
    muvekkilAdi: string;
    /** Föy kaynaklı satırlar (salt okunur). */
    foy: CaseHizmeti[];
    /** Elle satırlar (seçiciden değişir). */
    elle: CaseHizmeti[];
    /** Satırın tarafı kartın müvekkil listesinde yok (bayat kart verisi) — yalnız gösterilir. */
    kartDisi: boolean;
}

export class CaseHizmetError extends Error {
    readonly status: number;

    constructor(message: string, status: number) {
        super(message);
        this.name = "CaseHizmetError";
        this.status = status;
    }
}

/**
 * Satırları kartın müvekkillerine göre gruplar. Müvekkil sırası kartın taraf sırasıdır;
 * hizmeti olmayan müvekkil de boş grupla gelir ("Hizmet girilmemiş"). Tarafı müvekkil
 * listesinde bulunmayan satır kaybolmaz: sona `kartDisi` grubu olarak eklenir.
 */
export function muvekkileGoreGrupla(
    muvekkiller: HizmetMuvekkili[],
    satirlar: CaseHizmeti[],
): MuvekkilHizmetGrubu[] {
    const gruplar = new Map<number, MuvekkilHizmetGrubu>();
    for (const m of muvekkiller) {
        gruplar.set(m.id, { casePartyId: m.id, muvekkilAdi: m.name, foy: [], elle: [], kartDisi: false });
    }
    for (const s of satirlar) {
        let grup = gruplar.get(s.case_party_id);
        if (!grup) {
            grup = {
                casePartyId: s.case_party_id,
                muvekkilAdi: s.muvekkil_adi?.trim() || `Taraf #${s.case_party_id}`,
                foy: [],
                elle: [],
                kartDisi: true,
            };
            gruplar.set(s.case_party_id, grup);
        }
        (s.kaynak === "foy" ? grup.foy : grup.elle).push(s);
    }
    return Array.from(gruplar.values());
}

/** Tekrarsız adlar, ilk görülme sırasıyla. */
export function tekilAdlar(adlar: string[]): string[] {
    return Array.from(new Set(adlar));
}

/** İki ad kümesi aynı mı (sıra ve tekrar önemsiz). */
export function ayniKume(a: string[], b: string[]): boolean {
    const sa = new Set(a);
    const sb = new Set(b);
    if (sa.size !== sb.size) return false;
    for (const ad of sa) if (!sb.has(ad)) return false;
    return true;
}

const hizmetlerYolu = (caseId: number) => `/api/cases/${encodeURIComponent(String(caseId))}/hizmetler`;

/** Sunucunun Türkçe `detail` metni (string ise); doğrulama dizisi/boş gövde → null. */
async function sunucuMesaji(res: Response): Promise<string | null> {
    try {
        const govde = (await res.json()) as { detail?: unknown } | null;
        const detay = govde?.detail;
        return typeof detay === "string" && detay.trim() ? detay.trim() : null;
    } catch {
        return null;
    }
}

export async function listele(caseId: number): Promise<CaseHizmeti[]> {
    const res = await apiClient.fetch(hizmetlerYolu(caseId));
    if (!res.ok) {
        throw new CaseHizmetError(
            res.status === 404 ? "Dava bulunamadı." : "Hizmetler yüklenemedi.",
            res.status,
        );
    }
    return (await res.json()) as CaseHizmeti[];
}

/**
 * Müvekkilin ELLE hizmet kümesini yazar (tek `PUT`). `hizmetTurleri` yalnız elle kümedir —
 * föy kaynaklı adlar gövdeye girmez. Dönüş kartın güncel satır listesidir.
 */
export async function kumeyiYaz(
    caseId: number,
    casePartyId: number,
    hizmetTurleri: string[],
): Promise<CaseHizmeti[]> {
    const res = await apiClient.fetch(
        `${hizmetlerYolu(caseId)}/${encodeURIComponent(String(casePartyId))}`,
        { method: "PUT", body: JSON.stringify({ hizmet_turleri: hizmetTurleri }) },
    );
    if (!res.ok) {
        const detay = await sunucuMesaji(res);
        const mesaj =
            res.status === 422 ? (detay ?? "Seçilen hizmet kaydedilemedi: hizmet türü listede yok ya da taraf bu kartın müvekkili değil.")
            : res.status === 409 ? (detay ?? "Bu kayıt şu an başka bir işlemde kullanılıyor; birkaç dakika sonra tekrar deneyin.")
            : res.status === 404 ? "Dava bulunamadı."
            : "Hizmetler kaydedilemedi.";
        throw new CaseHizmetError(mesaj, res.status);
    }
    return (await res.json()) as CaseHizmeti[];
}
