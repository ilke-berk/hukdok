// =====================================================================
// Ofis numarası — istemci tarafı (G237, karar 023).
//
// Numarayı SUNUCU verir: kanonik kaynak `backend/services/ofis_no.py`. Bu dosyada
// eskiden duran istemci üreticisi (kategori/sigorta/yargı kod haritaları, isim
// bloğu, sıra numarasıyla numara kurma, biçim doğrulama) KALDIRILDI — iki kopya
// ayrışıyor, istemcinin kurduğu numara dolu çıkıp kaydı 409'a düşürüyordu.
//
// Burada yalnız şunlar kalır:
//   - YARGI_TURLERI: sihirbazın yargı türü seçicisi (yalnız AD listesi, kod yok),
//   - ofisNoOnizlemeSorgusu: `GET /api/cases/ofis-no-onizleme` sorgu dizgisi,
//   - yeniIstekKimligi: kayıt isteğinin tekrar korumalı kimliği (UUID).
// =====================================================================

// Sihirbazın yargı türü seçicisi. İdari yargının tek türü "İdare"dir (17.09);
// eski "İdari Yargı" seçeneği yoktur.
export const YARGI_TURLERI: readonly string[] = [
    "Hukuk",
    "Ceza",
    "İcra",
    "Arabuluculuk",
    "Savcılık",
    "İdare",
    "Tahkim",
    "Vergi",
    "Danışmanlık",
];

/** Sigortacı müvekkilde numaranın üçüncü bloğunu veren taraf rolü (backend ile aynı ad). */
export const SIGORTALI_ROLU = "Sigortalı";

const upperTR = (s: string): string => s.toLocaleUpperCase("tr-TR").trim();

// "Ad1;Ad2" biçiminde tek satıra yazılan çoklu isimler ayrı kişilerdir.
const splitNames = (value: string): string[] =>
    value.split(";").map(s => s.trim()).filter(Boolean);

export interface OfisNoOnizlemeGirdisi {
    /** Formdaki müvekkil satırları; `client_id` biliniyorsa doğrudan kullanılır. */
    clients: Array<{ name: string; client_id?: number | null }>;
    /** Kayıtlı müvekkiller — adı eşleşen satır sunucuya kaydın id'siyle gider. */
    dbClients?: Array<{ id?: number; name: string }>;
    fileType?: string | null;
    /** Müvekkil dışı taraflar; yalnız "Sigortalı" rolündekiler sunucuya iletilir. */
    otherParties?: Array<{ name: string; role?: string }>;
}

/**
 * Önizleme ucunun sorgu dizgisi. Müvekkil yoksa `null` döner — sunucu müvekkilsiz
 * numara vermez (422), istek hiç atılmaz.
 *
 * İstemci HİÇBİR kod türetmez: ad / kayıt id'si / yargı türü ham hâliyle gider,
 * numarayı `services/ofis_no` kurar.
 */
export function ofisNoOnizlemeSorgusu(girdi: OfisNoOnizlemeGirdisi): string | null {
    const params = new URLSearchParams();
    for (const client of girdi.clients) {
        for (const name of splitNames(client.name || "")) {
            const kayitli = client.client_id
                ?? girdi.dbClients?.find(db => upperTR(db.name) === upperTR(name))?.id;
            params.append("muvekkiller", kayitli != null ? String(kayitli) : name);
        }
    }
    if (!params.has("muvekkiller")) return null;

    const fileType = (girdi.fileType || "").trim();
    if (fileType) params.append("file_type", fileType);

    for (const party of girdi.otherParties ?? []) {
        if ((party.role || "").trim() !== SIGORTALI_ROLU) continue;
        for (const name of splitNames(party.name || "")) params.append("sigortali", name);
    }
    return params.toString();
}

const UUID_BICIMI = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Saklanan (taslak) kimlik kullanılabilir mi? Backend `istek_kimligi` alanı UUID ister. */
export const istekKimligiGecerli = (value: unknown): value is string =>
    typeof value === "string" && UUID_BICIMI.test(value);

/**
 * Kayıt isteğinin kimliği (G236 sözleşmesi). Form/modal/sihirbaz AÇILDIĞINDA bir kez
 * üretilir; aynı formun tekrar gönderiminde AYNI kalır, sunucu ikinci kartı açmaz
 * (`reused: true`). Başarılı kayıttan ya da form temizlenince yenilenir.
 */
export function yeniIstekKimligi(): string {
    const c = globalThis.crypto;
    if (c && typeof c.randomUUID === "function") return c.randomUUID();
    // Güvenli bağlam dışı (randomUUID yok): v4 biçimi elle kurulur.
    const bytes = new Uint8Array(16);
    if (c && typeof c.getRandomValues === "function") c.getRandomValues(bytes);
    else for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
