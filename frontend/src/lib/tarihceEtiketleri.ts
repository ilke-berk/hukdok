/**
 * Dava tarihçesi (`case_history.field_name`) → ekran etiketi.
 *
 * Panel eskiden ham alan adını basıyordu ("tku_birlestirme", "case_foys.sistem_no").
 * Tarihçe temizliğinden (11.09.2026) sonra kalan olay türleri sayılı; hepsi burada
 * Türkçe karşılığını bulur. Tanınmayan alan adı olduğu gibi döner — sessizce
 * yanlış etiket üretmektense ham adı göstermek tercih edilir.
 *
 * Aktarım/yazım turlarının olası alan adları da (avukat, taraf, dolgu alanları)
 * haritada: prod'da temizlik koşana dek ve sonraki paketlerde görünürler.
 */
const ETIKET: Record<string, string> = {
    // Olaylar
    status: "Durum Değişti",
    esas_no: "Esas No Değişti",
    court: "Mahkeme Değişti",
    tku_birlestirme: "Kart Birleştirildi (aynı dava, TKU)",
    mukerrer_birlestirme: "Mükerrer Kart Birleştirildi",
    "case_foys.sistem_no": "Föy Bağlandı",
    "case_foys.case_party_id": "Föy Müvekkile Bağlandı",
    avukat: "Avukat Eklendi",
    taraf: "Taraf Eklendi",
    // Kart alanları (aktarım/elle güncelleme)
    file_type: "Dosya Türü",
    sub_type: "Uzmanlık Alanı",
    sub_type_extra: "Alt Tür Notu",
    subject: "Dava Konusu",
    judicial_unit: "Yargı Birimi",
    opening_date: "Açılış Tarihi",
    acceptance_date: "İş Kabul Tarihi",
    arsiv_tarihi: "Arşiv Tarihi",
    atama_tarihi: "Atama Tarihi",
    responsible_lawyer_name: "Sorumlu Avukat",
    uyap_lawyer_name: "UYAP Avukatı",
    bureau_type: "Büro Özel Türü",
    service_type: "Hizmet Bloğu",
    muvekkil_tipi: "Müvekkil Tipi",
    hizmet_turu: "Hizmet Türü",
    klasor_no_2: "Klasör No",
    hasar_dosya_no: "Hasar Dosya No",
    hukuk_no: "Hukuk No",
    tracking_no: "Ofis Dosya No",
    maddi_tazminat: "Maddi Tazminat",
    manevi_tazminat: "Manevi Tazminat",
    dava_degeri: "Dava Değeri",
    para_birimi: "Para Birimi",
    islah_tutari: "Islah Tutarı",
    hukmedilen_maddi: "Hükmedilen Maddi",
    hukmedilen_manevi: "Hükmedilen Manevi",
    hukmedilen_toplam: "Hükmedilen Toplam",
    yerel_karar_durumu: "Yerel Karar Durumu",
    karar_no: "Karar No",
    karar_tarihi: "Karar Tarihi",
    karar_teblig_tarihi: "Karar Tebliğ Tarihi",
    karar_aciklama: "Karar Açıklaması",
    dosya_son_durumu: "Dosya Son Durumu",
    case_stage: "Dava Aşaması",
    istinaf_mahkemesi: "İstinaf Mahkemesi",
    istinaf_esas_no: "İstinaf Esas No",
    istinaf_karar_no: "İstinaf Karar No",
    istinaf_karar_durumu: "İstinaf Karar Durumu",
    istinaf_basvuru_tarihi: "İstinaf Başvuru Tarihi",
    istinaf_karar_tarihi: "İstinaf Karar Tarihi",
    temyiz_mahkemesi: "Temyiz Mahkemesi",
    temyiz_esas_no: "Temyiz Esas No",
    temyiz_karar_durumu: "Temyiz Karar Durumu",
    temyiz_karar_tarihi: "Temyiz Karar Tarihi",
    arabuluculuk_no: "Arabuluculuk No",
    arabuluculuk_karar_tarihi: "Arabuluculuk Karar Tarihi",
    tibbi_surec: "Tıbbi Süreç",
    tibbi_olay: "Tıbbi Olay",
    iddia_edilen_kusur: "İddia Edilen Kusur",
    hastada_olusan_zarar: "Hastada Oluşan Zarar",
    uygulanan_yontem: "Uygulanan Yöntem",
    olay_turu: "Olay Türü",
    hukumdeki_rol: "Hükümdeki Rol",
    notes: "Notlar",
};

/** Alan adını ekran etiketine çevirir; tanınmayan ad olduğu gibi döner. */
export const tarihceEtiketi = (field?: string | null): string =>
    field ? (ETIKET[field] ?? field) : "";
