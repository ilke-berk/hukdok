// Ofis no kod listeleri (karar 023, G235 uçları) — yönetim panelinin api yardımcısı.
// Uçlar: GET|POST /api/admin/sigorta-kodlari, PATCH /api/admin/sigorta-kodlari/{id},
// GET /api/admin/kategori-kodlari, PATCH /api/admin/kategori-kodlari/{code}.
// Kurallar (çakışma, SG sabiti, biçim) SUNUCUDADIR; buradaki biçimleme yalnız
// yazarken yardımcıdır — asıl kapı backend'in 409/422 cevabıdır.
import { apiClient } from "@/lib/api";

export interface SigortaKodu {
    id: number;
    kod: string;
    ad: string;
    eslesme_anahtarlari: string[];
    aktif: boolean;
}

export interface KategoriKodu {
    code: string;
    name: string;
    ofis_no_kodu: string | null;
    active: boolean;
}

export interface SigortaKoduGirdisi {
    kod: string;
    ad: string;
    eslesme_anahtarlari: string[];
    aktif?: boolean;
}

export const KOD_EN_AZ = 2;
export const KOD_EN_COK = 10;

const TR_ASCII: Record<string, string> = {
    "İ": "I", "I": "I", "ı": "I", "i": "I",
    "Ş": "S", "ş": "S", "Ğ": "G", "ğ": "G",
    "Ü": "U", "ü": "U", "Ö": "O", "ö": "O", "Ç": "C", "ç": "C",
};

/** Yazılan metni büyük ASCII harfe indirir (Türkçe harf katlanır, harf dışı atılır). */
export function asciiBuyuk(metin: string): string {
    return Array.from(metin)
        .map(h => TR_ASCII[h] ?? h.toUpperCase())
        .join("")
        .replace(/[^A-Z]/g, "");
}

/** Kod alanı: büyük ASCII harf, en çok 10 karakter. */
export function kodBicimle(metin: string): string {
    return asciiBuyuk(metin).slice(0, KOD_EN_COK);
}

/** Kod kaydedilebilir mi? Değilse kullanıcıya gösterilecek sebep. */
export function kodSorunu(kod: string): string | null {
    if (!kod) return "Kod boş olamaz";
    if (kod.length < KOD_EN_AZ) return `Kod en az ${KOD_EN_AZ} harf olmalı`;
    return null;
}

/** "axa, aksa sigorta" → ["AXA", "AKSA"] — virgül/boşlukla ayrılmış eşleşme kelimeleri. */
export function anahtarlariAyir(metin: string): string[] {
    const sonuc: string[] = [];
    for (const parca of metin.split(/[\s,;]+/)) {
        const temiz = asciiBuyuk(parca);
        if (temiz && !sonuc.includes(temiz)) sonuc.push(temiz);
    }
    return sonuc;
}

// Önizleme örnekleri — sıra ve ad temsilîdir; gerçek numarayı sunucu verir.
const ORNEK_SIRA = "0001";
const ORNEK_TUR = "HUK";
const ORNEK_KISI = "A.YILMAZ";
const ORNEK_KURUM = "ENTHONE";

// `services/ofis_no.KISI_KATEGORILERI` ile aynı küme: ad `<baş harf>.<SOYAD>` olur.
const KISI_KATEGORILERI = new Set(["DOKTOR", "SAGLIK-CALISANI", "HASTA", "BIREYSEL"]);

/** Sigorta şirketi satırı örneği: `AXA-0001-DR.A.YILMAZ-HUK`. */
export function sigortaOrnegi(kod: string, doktorKodu = "DR"): string {
    return `${kod}-${ORNEK_SIRA}-${doktorKodu}.${ORNEK_KISI}-${ORNEK_TUR}`;
}

/** Kategori satırı örneği: kişi `DR.A.YILMAZ-0001-HUK`, kurum `KR.ENTHONE-0001-HUK`. */
export function kategoriOrnegi(kod: string, kisi: boolean): string {
    return `${kod}.${kisi ? ORNEK_KISI : ORNEK_KURUM}-${ORNEK_SIRA}-${ORNEK_TUR}`;
}

/** Kategori kişi mi? Çekirdek dört kategori ya da kodu onlardan biriyle aynı olan özel kategori. */
export function kisiKategorisiMi(kategori: KategoriKodu, tumu: KategoriKodu[]): boolean {
    if (KISI_KATEGORILERI.has(kategori.code)) return true;
    if (!kategori.ofis_no_kodu) return false;
    return tumu.some(k => KISI_KATEGORILERI.has(k.code) && k.ofis_no_kodu === kategori.ofis_no_kodu);
}

/** Sunucu hatasından okunur metin: 409 `detail` düz metin, 422 `detail` alan listesidir. */
async function hataMetni(res: Response, varsayilan: string): Promise<string> {
    let detail: unknown;
    try {
        detail = (await res.json())?.detail;
    } catch {
        return varsayilan;
    }
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length > 0) {
        // Pydantic 422: kod biçimi sunucuda da reddedildi.
        const alanlar = detail
            .map(d => (Array.isArray(d?.loc) ? String(d.loc[d.loc.length - 1]) : ""))
            .filter(Boolean);
        if (alanlar.some(a => a === "kod" || a === "ofis_no_kodu")) {
            return `Kod ${KOD_EN_AZ}-${KOD_EN_COK} büyük ASCII harf olmalı`;
        }
        return `Geçersiz alan: ${alanlar.join(", ") || "bilinmiyor"}`;
    }
    return varsayilan;
}

async function istek<T>(url: string, varsayilanHata: string, method?: string, body?: unknown): Promise<T> {
    const res = method
        ? await apiClient.fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        })
        : await apiClient.fetch(url);
    if (!res.ok) throw new Error(await hataMetni(res, varsayilanHata));
    return res.json() as Promise<T>;
}

export const ofisNoKodlariApi = {
    sigortaKodlari: () =>
        istek<{ kodlar: SigortaKodu[]; varsayilan_kod: string }>(
            "/api/admin/sigorta-kodlari", "Sigorta kodları alınamadı"),
    sigortaKoduEkle: (girdi: SigortaKoduGirdisi) =>
        istek<SigortaKodu>("/api/admin/sigorta-kodlari", "Sigorta kodu eklenemedi", "POST", girdi),
    sigortaKoduGuncelle: (id: number, alanlar: Partial<SigortaKoduGirdisi>) =>
        istek<SigortaKodu>(`/api/admin/sigorta-kodlari/${id}`, "Sigorta kodu güncellenemedi", "PATCH", alanlar),
    kategoriKodlari: () =>
        istek<{ kategoriler: KategoriKodu[] }>("/api/admin/kategori-kodlari", "Kategori kodları alınamadı"),
    kategoriKoduGuncelle: (code: string, ofisNoKodu: string) =>
        istek<KategoriKodu>(
            `/api/admin/kategori-kodlari/${encodeURIComponent(code)}`, "Kategori kodu güncellenemedi",
            "PATCH", { ofis_no_kodu: ofisNoKodu }),
    /** Yeni müvekkil kategorisi — genel referans liste ucu (yalnız kod+ad taşır). */
    kategoriEkle: (code: string, name: string) =>
        istek<unknown>("/api/config/client_categories", "Kategori eklenemedi", "POST", { code, name }),
};
