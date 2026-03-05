/**
 * Kategori eşleşmeleri (1. Blok: 2 Hane)
 */
export const CATEGORY_MAP: Record<string, string> = {
    "Doktor": "D1",
    "Özel Hastane": "H2",
    "Sigorta": "S0",
    "Hasta": "H1",
    "Diğer": "X1"
};

/**
 * Yargı süreci eşleşmeleri (4. Blok: 5 Harf)
 */
export const PROCESS_MAP: Record<string, string> = {
    "İdari Yargı": "IDARI",
    "Hukuk": "HUKUK",
    "Ceza": "CEZAA", // 5 haneye tamamlamak için
    "İcra": "ICRAA", // 5 haneye tamamlamak için
    "Arabuluculuk": "ARABU",
    "Savcılık": "SAVCI"
};

/**
 * Belirli Sigorta Şirketleri için Tek Haneli Kodlar
 * Kategori bloğunda (1. Blok) S harfinin sonuna eklenecek.
 * Kullanıcı talebi üzerine CORPUS ve QUICK aynı numaraya sahiptir.
 */
export const INSURANCE_CODES: Record<string, string> = {
    "AK": "1",
    "ANADOLU": "2",
    "AXA": "3",
    "CORPUS": "4", // Corpus ve Quick aynı numara
    "QUICK": "4",  // Corpus ve Quick aynı numara
    "EUREKO": "5",
    "NIPPON": "6",
    "SOMPO": "7"
};

interface TrackingParams {
    category?: string;
    clientName?: string;
    sequence?: number;
    processType?: string;
    serviceType?: string;
}

/**
 * İsmi 14 karakterlik, ASCII uyumlu bir koda dönüştürür.
 * Örn: "Abdülhamit Soysal" -> "ABDULHAMITSOYS"
 */
const slugifyName = (name: string): string => {
    if (!name) return "XXXXXXXXXXXXXX";
    return name
        .trim()
        .replace(/ı/g, 'i').replace(/ğ/g, 'g').replace(/ü/g, 'u')
        .replace(/ş/g, 's').replace(/ö/g, 'o').replace(/ç/g, 'c')
        .replace(/İ/g, 'I').replace(/Ğ/g, 'G').replace(/Ü/g, 'U')
        .replace(/Ş/g, 'S').replace(/Ö/g, 'O').replace(/Ç/g, 'C')
        .toLocaleUpperCase('tr-TR')
        .replace(/[^A-Z\s]/g, '')
        .replace(/\s+/g, '_')
        .padEnd(14, '.')
        .slice(0, 14);
};

/**
 * Yeni protokol uyarınca ofis takip numarası üretir.
 * Format: [KATEGORİ].[İSİM].[OFİS_NO].[YARGI_SÜRECİ].[HİZMET_TÜRÜ]
 * Örnek: S1.ABDULHAMITSOYS.0001.HUKUK.00000
 */
export const generateTrackingNumber = (params?: TrackingParams): string => {
    // 1. Blok: Kategori (2 Hane)
    let block1 = CATEGORY_MAP[params?.category || ""] || "X1";

    // Eğer Kategori "Sigorta" ise ve isim bir sigorta şirketini içeriyorsa, S harfine özel tek haneli kod ekle
    if (params?.category === "Sigorta" && params?.clientName) {
        const upperName = params.clientName.toLocaleUpperCase('tr-TR');
        for (const [key, code] of Object.entries(INSURANCE_CODES)) {
            if (upperName.includes(key)) {
                block1 = `S${code}`;
                break;
            }
        }
    }

    // 2. Blok: İsim Kısaltması (14 Karakter)
    const block2 = slugifyName(params?.clientName || "");

    // 3. Blok: Ofis No / Sıra No / Dava Sayısı (4 Hane)
    const block3 = (params?.sequence?.toString() || "0001").padStart(4, '0');

    // 4. Blok: Yargı Süreci (5 Harf)
    const block4 = PROCESS_MAP[params?.processType || ""] || "HUKUK";

    // 5. Blok: Hizmet Türü (5 Hane)
    const block5 = (params?.serviceType || "00000").padStart(5, '0');

    return `${block1}.${block2}.${block3}.${block4}.${block5}`;
};

/**
 * Verilen bir dosya numarasının kurallara uygunluğunu denetler.
 */
export const validateCaseNumber = (caseNumber: string): boolean => {
    if (!caseNumber) return false;
    // Bloklar arası noktalarla birlikte format kontrolü (İsim: 14, Ofis No: 4, Diğer sayısal bloklar: 5 hane/harf)
    return /^[A-Z0-9]{2}\.[A-Z0-9_.]{14}\.[A-Z0-9]{4}\.[A-Z0-9]{5}\.[A-Z0-9]{5}$/.test(caseNumber);
};
