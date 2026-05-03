export const CATEGORY_MAP: Record<string, string> = {
    "Doktor": "D1",
    "Özel Hastane": "H2",
    "Sigorta": "S0",
    "Hasta": "H1",
    "Diğer": "X1"
};

export const PROCESS_MAP: Record<string, string> = {
    "İdari Yargı": "IDARI",
    "Hukuk": "HUKUK",
    "Ceza": "CEZAA",
    "İcra": "ICRAA",
    "Arabuluculuk": "ARABU",
    "Savcılık": "SAVCI"
};

export const INSURANCE_CODES: Record<string, string> = {
    "AK": "1",
    "ANADOLU": "2",
    "AXA": "3",
    "CORPUS": "4",
    "QUICK": "4",
    "EUREKO": "5",
    "NIPPON": "6",
    "SOMPO": "7"
};

// Kurum adlarında anlamsız jenerik kelimeler
const CORP_STOP: Set<string> = new Set([
    "SIGORTA", "HAYAT", "ANONIM", "TURK", "SIRKETI", "KOOPERATIFI",
    "TIC", "TICARETI", "SAN", "SANAYI", "SANAYII",
    "INS", "INSAAT", "TAAHHUT",
    "LTD", "STI", "AS",
    "HASTANE", "HASTANESI", "SAGLIK", "HIZ", "HIZMETLERI", "HIZM",
    "OZEL", "TIBBI", "MALZ",
    "SITE", "SITESI", "YONETICILIGI", "YONETIM", "KURULU", "MERKEZ",
    "VE", "VEYA",
    "PAZ", "PAZARLAMA", "DAG", "DAGITIM",
    "ORG", "ORGANIZASYON", "YAPIM", "TANITIM",
    "URETIM", "ISLETMECILIGI", "DANISMANLIK",
    "GLOBAL", "SISTEMLERI", "HIZMETLER",
]);

// Kişi kategorileri — bu kategorilerde slugifyName kullanılır
const PERSON_CATEGORIES = new Set(["Doktor", "Hasta", "Bireysel"]);

const normalizeAscii = (s: string): string =>
    s.replace(/ı/g, 'i').replace(/ğ/g, 'g').replace(/ü/g, 'u')
     .replace(/ş/g, 's').replace(/ö/g, 'o').replace(/ç/g, 'c')
     .replace(/İ/g, 'I').replace(/Ğ/g, 'G').replace(/Ü/g, 'U')
     .replace(/Ş/g, 'S').replace(/Ö/g, 'O').replace(/Ç/g, 'C');

/** Kişi adları: ilk isim baş harfi + soyisim  →  I_KUTLUK.. */
const slugifyName = (name: string): string => {
    if (!name) return "XXXXXXXXXX";
    const clean = normalizeAscii(name.trim())
        .toUpperCase()
        .replace(/[^A-Z\s]/g, '');
    const parts = clean.split(/\s+/).filter(Boolean);
    if (parts.length === 0) return "XXXXXXXXXX";
    if (parts.length === 1) return parts[0].padEnd(10, '.').slice(0, 10);
    const surname = parts[parts.length - 1];
    return `${parts[0].charAt(0)}_${surname}`.padEnd(10, '.').slice(0, 10);
};

/** Kurum adları: jenerik kelimeler atılır, ilk anlamlı kelime alınır  →  ANADOLU.. */
const slugifyCorp = (name: string): string => {
    if (!name) return "XXXXXXXXXX";
    const clean = normalizeAscii(name.trim())
        .toUpperCase()
        .replace(/[^A-Z\s]/g, '');
    const parts = clean.split(/\s+/).filter(p => !CORP_STOP.has(p) && p.length > 1);
    const word = parts.length > 0
        ? parts[0]
        : clean.split(/\s+/).filter(Boolean)[0] || "KURUM";
    return word.slice(0, 10).padEnd(10, '.');
};

interface TrackingParams {
    category?: string;       // block1 (kategori kodu) için — tüm müvekkillerin en iyi kodu
    clientName?: string;     // isim bloğu için seçilen müvekkil
    clientCategory?: string; // seçilen müvekkilin kategorisi (kişi mi kurum mu kararı)
    sequence?: number;
    processType?: string;
    serviceType?: string;
}

export const generateTrackingNumber = (params?: TrackingParams): string => {
    // 1. Blok: Kategori kodu
    const normalizedCategory = (params?.category || "").toLocaleUpperCase('tr-TR');
    let block1 = "X1";
    for (const [key, val] of Object.entries(CATEGORY_MAP)) {
        if (normalizedCategory.includes(key.toLocaleUpperCase('tr-TR'))) {
            block1 = val;
            break;
        }
    }
    const upperName = (params?.clientName || "").toLocaleUpperCase('tr-TR');
    const isSigorta = normalizedCategory.includes("SIGORTA") ||
                      normalizedCategory.includes("SİGORTA") ||
                      upperName.includes("SIGORTA") ||
                      upperName.includes("SİGORTA");
    if (isSigorta && params?.clientName) {
        if (block1 === "X1") block1 = "S0";
        for (const [key, code] of Object.entries(INSURANCE_CODES)) {
            if (upperName.includes(key)) { block1 = `S${code}`; break; }
        }
    }

    // 2. Blok: İsim — clientCategory'e göre kişi/kurum formatı seç
    const clientCat = params?.clientCategory || "";
    const isPersonClient = PERSON_CATEGORIES.has(clientCat) || clientCat === "";
    const block2 = isPersonClient
        ? slugifyName(params?.clientName || "")
        : slugifyCorp(params?.clientName || "");

    // 3. Blok: Sıra no
    const block3 = (params?.sequence?.toString() || "0001").padStart(4, '0');

    // 4. Blok: Yargı süreci
    const block4 = PROCESS_MAP[params?.processType || ""] || "HUKUK";

    // 5. Blok: Hizmet türü
    const block5 = (params?.serviceType || "00000").padStart(5, '0');

    return `${block1}.${block2}.${block3}.${block4}.${block5}`;
};

/**
 * Birden fazla müvekkil arasından isim bloğu için en uygun olanı seç.
 * Kişi (Doktor/Hasta/Bireysel) > Kurum > Sigorta Şirketi
 */
export const pickNameClient = (
    clients: Array<{ name: string; category?: string }>
): { name: string; category: string } => {
    if (clients.length === 0) return { name: "", category: "" };

    const priority = (cat?: string): number => {
        if (!cat) return 3;
        if (cat === "Doktor")   return 0;
        if (cat === "Hasta")    return 1;
        if (cat === "Bireysel") return 2;
        if (cat.toLowerCase().includes("sigorta")) return 10;
        return 5;
    };

    const sorted = [...clients].sort((a, b) => priority(a.category) - priority(b.category));
    return { name: sorted[0].name, category: sorted[0].category || "" };
};

/**
 * Tüm müvekkillerden en iyi kategori kodunu döner.
 * Özgül sigorta (S1-S7) > S0 > D1 > H2 > H1 > X1
 */
export const bestCategoryCode = (
    clients: Array<{ name: string; category?: string }>
): string => {
    if (clients.length === 0) return "X1";

    const getCode = (name: string, cat: string): string => {
        const nc = normalizeAscii(cat).toUpperCase();
        const nn = normalizeAscii(name).toUpperCase();
        let code = "X1";
        for (const [key, val] of Object.entries(CATEGORY_MAP)) {
            if (nc.includes(normalizeAscii(key).toUpperCase())) { code = val; break; }
        }
        if (nn.includes("SIGORTA") || nc.includes("SIGORTA")) {
            if (code === "X1") code = "S0";
            for (const [key, ins] of Object.entries(INSURANCE_CODES)) {
                if (nn.includes(key)) { code = `S${ins}`; break; }
            }
        }
        return code;
    };

    const codes = clients.map(c => getCode(c.name, c.category || ""));
    for (const c of codes) if (c.startsWith("S") && c !== "S0") return c;
    for (const c of codes) if (c === "S0") return c;
    for (const c of codes) if (c !== "X1") return c;
    return codes[0];
};

export const validateCaseNumber = (caseNumber: string): boolean => {
    if (!caseNumber) return false;
    return /^[A-Z0-9]{2}\.[A-Z0-9_.]{10}\.[A-Z0-9]{4}\.[A-Z0-9]{5}\.[A-Z0-9]{5}$/.test(caseNumber);
};
