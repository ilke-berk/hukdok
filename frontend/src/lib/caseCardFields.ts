/**
 * Dava kartındaki FAZ F aktarım alanları (G048).
 *
 * Neden ayrı dosya: CaseDetails.tsx zaten 1000+ satır ve tamamı JSX — gruplama,
 * "boş alan kartı kirletmesin" kuralı ve kapalı liste denetimi orada test
 * edilemezdi. Alan tanımları + saf yardımcılar burada, render orada.
 *
 * SALT OKUNUR: G044 kolonları açtı ama yazma yolunu (CaseCreate /
 * CaseTrackingUpdate) BİLEREK açmadı — o FAZ F'nin işi. Bu yüzden kartta
 * düzenleme kontrolü yoktur; aktarımla gelen veri yalnız görünür olur.
 */

export type CardFieldType = "text" | "date" | "closedList";

/** Kapalı liste alanlarının değerlerini besleyen backend referans listesi. */
export type ClosedListKey = "alleged_faults" | "appealing_parties";

export interface CardFieldDef {
    /** Backend alan adı (CaseRead ile birebir). */
    key: string;
    label: string;
    type: CardFieldType;
    /** type === "closedList" ise zorunlu — değerler bu listeden gelir. */
    list?: ClosedListKey;
}

/**
 * Beş tıbbi alan TEK grupta durur (G048 kriteri): dava kartına dağıtılınca
 * malpraktis dosyasının tıbbi tablosu okunamaz hâle geliyordu.
 */
export const MEDICAL_CARD_FIELDS: CardFieldDef[] = [
    { key: "tibbi_surec", label: "Tıbbi Süreç", type: "text" },
    { key: "tibbi_olay", label: "Tıbbi Olay", type: "text" },
    { key: "iddia_edilen_kusur", label: "İddia Edilen Kusur", type: "closedList", list: "alleged_faults" },
    { key: "hastada_olusan_zarar", label: "Hastada Oluşan Zarar", type: "text" },
    { key: "uygulanan_yontem", label: "Uygulanan Yöntem", type: "text" },
];

/**
 * Kanun yolu bilgisi: kartta kalan TEK süreç alanı.
 *
 * G074'te üç alan buradan ÇIKTI — `arabuluculuk_no`,
 * `arabuluculuk_karar_tarihi` (davanın ön aşaması) ve `arsiv_tarihi`
 * (kapanış olayı) artık takip panelinden YAZILIYOR (G073 `TRACKING_FIELDS`);
 * aynı alanı iki ekranda göstermek "hangisi doğru?" sorusunu doğururdu.
 *
 * `istinaf_basvuran_taraf` KALDI: takip panelinin yazma yolunda değil (aşama
 * fotoğrafının hedefi, tek yazıcısı `stage_decisions`), yani "hangisinden
 * düzeltirim" belirsizliği doğurmuyor. Takip panelindeki aşama tarihçesi onu
 * satır bazında da gösterir — kart özet, tarihçe ayrıntıdır.
 */
export const PROCESS_CARD_FIELDS: CardFieldDef[] = [
    { key: "istinaf_basvuran_taraf", label: "İstinaf Başvuran Taraf", type: "closedList", list: "appealing_parties" },
];

/**
 * Büro/işletme bilgileri: dosyanın hukuki değil TİCARİ tarafı — işi ne zaman
 * kabul ettik, hangi kova altında takip ediyoruz, bugünkü durumu ne.
 *
 * Backend bu alanları zaten döndürüyordu (`case_manager.get_case`) ama kartta
 * hiç basılmıyordu; HUKDOK aktarımı doldurunca (2026-08-19 tam koşusu:
 * kabul tarihi 5.382 · büro türü 5.156 kart) veri görünmez kalıyordu.
 * Aktarılan veriyi göremeyen kullanıcı doğrulayamaz da.
 *
 * `dosya_son_durumu` G074'te buradan ÇIKTI: takip paneli onu ZATEN yazıyordu,
 * kart 2026-08-19'da yalnız okuma amaçlı basmıştı — aynı değerin iki ekranda
 * durması bu görevin kapattığı sapmanın ta kendisiydi.
 */
export const OFFICE_CARD_FIELDS: CardFieldDef[] = [
    { key: "acceptance_date", label: "İş Kabul Tarihi", type: "date" },
    { key: "bureau_type", label: "Büro Özel Türü", type: "text" },
];

/** Boş = null | undefined | yalnız boşluk. 0 ve "0" DOLUDUR. */
export const isFilled = (value: unknown): boolean =>
    value !== null && value !== undefined && String(value).trim() !== "";

/** Grubun tamamı boşsa kart hiç basılmaz — boş kart gürültüdür. */
export const hasAnyValue = (
    data: Record<string, unknown>,
    fields: CardFieldDef[],
): boolean => fields.some(f => isFilled(data[f.key]));

/** Grubun basılacak (dolu) alanları — kartta boş satır kalmaz. */
export const filledFields = (
    data: Record<string, unknown>,
    fields: CardFieldDef[],
): CardFieldDef[] => fields.filter(f => isFilled(data[f.key]));

/**
 * Tarihler backend'den ISO string gelir (case_manager.get_case). Aktarım verisi
 * kirli olabildiği için ayrıştırılamayan değer "Invalid Date" yerine HAM basılır —
 * kullanıcı bozuk veriyi görüp düzeltebilsin.
 */
export const formatCardValue = (value: unknown, type: CardFieldType): string => {
    const raw = String(value ?? "").trim();
    if (type !== "date") return raw;
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? raw : parsed.toLocaleDateString("tr-TR");
};

/**
 * Kapalı liste değerinin durumu.
 * - `unknown`: liste henüz gelmedi ya da BOŞ. alleged_faults tam olarak böyle
 *   doğuyor (G044: 7 değerin kendisi teslim paketinde yok) — boş listeye karşı
 *   "liste dışı" damgası vurmak her kaydı yanlış işaretlerdi.
 * - `off-list`: aktarım kapalı listede olmayan bir değer getirmiş; görünür olmalı.
 */
export type ClosedListState = "unknown" | "in-list" | "off-list";

const normalize = (s: string): string => s.trim().toLocaleLowerCase("tr-TR");

export const closedListState = (
    value: unknown,
    options: { name: string }[] | undefined,
): ClosedListState => {
    if (!isFilled(value) || !options || options.length === 0) return "unknown";
    const target = normalize(String(value));
    return options.some(o => normalize(o.name ?? "") === target) ? "in-list" : "off-list";
};
