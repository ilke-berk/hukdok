from enum import Enum
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContactType(str, Enum):
    CLIENT = "Client"
    OTHER = "Other"


class ConfigItem(BaseModel):
    code: str
    name: str
    tc_no: Optional[str] = None
    sicil_no: Optional[str] = None
    gorev: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None


class LawyerConfigItem(BaseModel):
    """POST /api/config/lawyers gövdesi (G228): `ConfigItem`'ın avukat ikizi; `code`
    OPSİYONEL ve YOK SAYILIR — iç kodu ve kurumsal kimliği sunucu üretir. Diğer listeler
    `ConfigItem` ile `code` zorunlu kalır."""
    code: Optional[str] = None
    name: str
    tc_no: Optional[str] = None
    sicil_no: Optional[str] = None
    gorev: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None


class EmailItem(BaseModel):
    name: str
    email: str
    description: Optional[str] = ""


class DeleteRequest(BaseModel):
    code: Optional[str] = None
    email: Optional[str] = None


class AppSettingUpdate(BaseModel):
    """Yönetici aç/kapa ayarı — /api/admin/settings/{key} gövdesi."""
    value: bool


# ---- Veri teslim defteri (G108 — /api/admin/aktarim/*) ----

class AktarimTeslimiOzetOut(BaseModel):
    """Teslim satırının liste görünümü (`durum_gecmisi` ve `spool_path` liste dışı).

    Sözleşme: gorevler/gorev/G108.md — G111 paneli bu alanları okur; tarihler
    ISO 8601 string olarak serileştirilir.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    dosya_adi: str
    sha256: str
    kaynak: str
    durum: str
    onceki_teslim_adi: Optional[str] = None
    zincir_tamam: Optional[bool] = None
    okunan: Optional[int] = None
    islenen: Optional[int] = None
    atlanan: Optional[int] = None
    hata_sayisi: Optional[int] = None
    alan_degisikligi: Optional[int] = None
    kart_degisen: Optional[int] = None
    envanter_denk: Optional[bool] = None
    kapi_karari: Optional[str] = None
    kapi_gerekcesi: Optional[str] = None
    cevap_yuklendi: Optional[bool] = None
    uygulayan: Optional[str] = None
    hata_mesaji: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    done_at: Optional[datetime] = None
    # G115: bir önceki uygulanmış teslime göre yapı farkı (model property'si
    # `AktarimTeslimi.yapi_farki`; `yapi` kolonunun kendisi liste dışı) —
    # {"yeni_basliklar", "kaybolan_basliklar", "yeni_sayfalar",
    #  "kaybolan_sayfalar", "taninmayan_basliklar"}; doğrulanmamışsa None.
    yapi_farki: Optional[Dict[str, Any]] = None


class AktarimTeslimiOut(AktarimTeslimiOzetOut):
    """Tek teslim (tam): liste alanları + durum geçmişi + spool yolu."""
    durum_gecmisi: Optional[List[Dict[str, Any]]] = None
    spool_path: Optional[str] = None


class TeslimUygulaRequest(BaseModel):
    """`POST /api/admin/aktarim/teslimler/{id}/uygula` gövdesi — bilinçli onay şart."""
    onay: bool = False


class ReorderRequest(BaseModel):
    type: str
    ordered_ids: List[str]

class RenameRequest(BaseModel):
    type: str
    code: str
    name: str


class ListUpdateRequest(BaseModel):
    """Liste öğesi düzenleme — fields yalnızca ilgili listenin editable kolonlarını içerir."""
    type: str
    code: str
    fields: Dict[str, Optional[str]]


class ListDeleteRequest(BaseModel):
    """Liste öğesi silme; mode bağlı kayıtlara ne olacağını belirler."""
    type: str
    code: str
    mode: str = "block"          # "block" | "clear" | "reassign" | "keep"
    target_code: Optional[str] = None   # mode="reassign" için hedef öğe kodu

class LawyerUpdateItem(BaseModel):
    tc_no: Optional[str] = None
    sicil_no: Optional[str] = None
    gorev: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class CourtTypeItem(BaseModel):
    code: str
    name: str
    parent_code: str

class PartyRoleItem(BaseModel):
    code: str
    name: str
    role_type: str = "MAIN"


class ClientPolicyCreate(BaseModel):
    """Müvekkil poliçe kaydı — intake sihirbazından toplu veya karttan tekil besleme."""
    police_no: Optional[str] = None
    police_turu: Optional[str] = None          # ZORUNLU | TAMAMLAYICI | DIGER
    sigorta_sirketi: Optional[str] = None
    baslangic_tarihi: Optional[date] = None
    bitis_tarihi: Optional[date] = None
    retroaktif_tarihi: Optional[date] = None
    sigortali_kurum: Optional[str] = None
    teminat_limiti: Optional[float] = None
    source_document: Optional[str] = None


class ClientPolicySaveRequest(BaseModel):
    policies: List[ClientPolicyCreate] = Field(..., min_length=1, max_length=30)


class ClientPolicyRead(ClientPolicyCreate):
    id: int
    client_id: int
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ClientCreate(BaseModel):
    name: str
    tc_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    cari_kod: Optional[str] = None
    contact_type: ContactType = ContactType.CLIENT
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    specialty: Optional[str] = None
    il: Optional[str] = None
    sektor: Optional[str] = None
    yevmiye_no: Optional[str] = None
    noterlik: Optional[str] = None
    vekaletname_tarihi: Optional[date] = None
    vekil_avukatlar: Optional[str] = None
    gecerlilik_tarihi: Optional[date] = None
    vekalet_no: Optional[str] = None
    buro_vekalet_no: Optional[str] = None


class ClientRead(BaseModel):
    id: int
    name: str
    tc_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    cari_kod: Optional[str] = None
    contact_type: str = "Client"
    active: bool
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    specialty: Optional[str] = None
    il: Optional[str] = None
    sektor: Optional[str] = None
    yevmiye_no: Optional[str] = None
    noterlik: Optional[str] = None
    vekaletname_tarihi: Optional[date] = None
    vekil_avukatlar: Optional[str] = None
    gecerlilik_tarihi: Optional[date] = None
    vekalet_no: Optional[str] = None
    buro_vekalet_no: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    tc_no: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    client_type: Optional[str] = None
    category: Optional[str] = None
    cari_kod: Optional[str] = None
    contact_type: Optional[ContactType] = None
    active: Optional[bool] = None
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    specialty: Optional[str] = None
    il: Optional[str] = None
    sektor: Optional[str] = None
    yevmiye_no: Optional[str] = None
    noterlik: Optional[str] = None
    vekaletname_tarihi: Optional[date] = None
    vekil_avukatlar: Optional[str] = None
    gecerlilik_tarihi: Optional[date] = None
    vekalet_no: Optional[str] = None
    buro_vekalet_no: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CasePartyBase(BaseModel):
    """Taraf satırının ortak alanları — okuma yanıtları (liste/kart) ve yalnız-taraf
    ekleyen zenginleştirme isteği bu şekli taşır (hizmet alanı YOK)."""
    client_id: Optional[int] = None
    name: str
    role: str
    party_type: str  # "CLIENT", "COUNTER", "THIRD"
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    tc_no: Optional[str] = None


class CasePartyCreate(CasePartyBase):
    """Kart açma/düzenleme isteğindeki taraf (G250: müvekkil kendi hizmetleriyle gelir)."""
    # Bu müvekkile bu kartta verilen hizmet türleri — `service_types` ADLARI (G250).
    # Yalnız kart AÇILIRKEN okunur: `add_case` satırları `case_hizmetleri.elle_kumesini_yaz`
    # ile aynı transaction'da yazar; kullanıcı yollarında (POST /api/cases, intake commit)
    # hizmetsiz müvekkil 422'dir. Düzenlemede (PUT /api/cases/{id}) YOK SAYILIR — mevcut
    # kartın hizmetleri `PUT /api/cases/{id}/hizmetler/{case_party_id}` ucundan yazılır.
    hizmet_turleri: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _hizmet_yalniz_muvekkilde(self):
        # Hizmet kart × MÜVEKKİL çiftinin özelliğidir (G248) — karşı taraf/üçüncü kişide 422.
        if self.hizmet_turleri and self.party_type != "CLIENT":
            raise ValueError(
                f'Hizmet türü yalnız müvekkil tarafına yazılır: "{self.name}" müvekkil değil.'
            )
        return self


# ─── Tanıdık Sorgu / Çıkar Çatışması Kontrolü ────────────────────────────────

class PartyCheckItem(BaseModel):
    name: str
    tc_no: Optional[str] = None
    party_type: Optional[str] = None  # "CLIENT", "COUNTER", "THIRD"


class PartyCheckRequest(BaseModel):
    parties: List[PartyCheckItem] = Field(..., max_length=20)
    exclude_case_id: Optional[int] = None


class PartyMatch(BaseModel):
    source: str        # "client" | "case_party"
    strength: str      # "certain" | "probable" | "possible"
    matched_on: str    # "tc_no" | "name_exact" | "name_fuzzy"
    name: str
    # client kaynaklı alanlar
    client_id: Optional[int] = None
    cari_kod: Optional[str] = None
    category: Optional[str] = None
    contact_type: Optional[str] = None
    # case_party kaynaklı alanlar
    case_id: Optional[int] = None
    tracking_no: Optional[str] = None
    case_subject: Optional[str] = None
    case_status: Optional[str] = None
    role: Optional[str] = None
    party_type: Optional[str] = None
    # Eşleşen kaydın TC'si — ekranda karşılaştırma için gösterilir
    # (endpoint auth korumalı; cari seçim ekranı da TC'yi zaten açık gösteriyor)
    tc_no: Optional[str] = None


class PartyCheckResult(BaseModel):
    query: PartyCheckItem
    conflict: bool = False
    matches: List[PartyMatch] = []


class PartyCheckResponse(BaseModel):
    results: List[PartyCheckResult] = []


class CaseLawyerCreate(BaseModel):
    lawyer_id: Optional[int] = None
    name: str


class CaseCreate(BaseModel):
    # G236: numarayı SUNUCU verir (`services/ofis_no`). Alan eski istemciler için şemada
    # kalır ama yeni kayıtta yok sayılır, düzenlemede (PUT) yazılmaz.
    tracking_no: Optional[str] = None
    # Kayıt isteğinin kimliği (G236): aynı kimlikle tekrar gelen istek ikinci kart açmaz,
    # ilk kart `reused: true` ile döner. Opsiyonel (eski istemci/sekme); biçim UUID.
    istek_kimligi: Optional[UUID] = None
    esas_no: Optional[str] = None
    status: str = "DERDEST"
    # ESKİ 5'li hizmet maskesi (G250): geriye uyum için okunur ve olduğu gibi saklanır
    # (`cases.service_type`), ama hiçbir şeyi BESLEMEZ — ofis no kullanmıyor, zorunlu alan
    # değil, sunucu yeni kod üretmiyor. Hizmetin gerçek kaynağı taraf başına
    # `parties[i].hizmet_turleri` → `case_hizmetleri`.
    service_type: Optional[str] = None
    file_type: Optional[str] = None
    sub_type: Optional[str] = None
    subject: Optional[str] = None
    court: Optional[str] = None
    opening_date: Optional[str] = None
    responsible_lawyer_name: Optional[str] = None
    uyap_lawyer_name: Optional[str] = None
    maddi_tazminat: Optional[float] = 0
    manevi_tazminat: Optional[float] = 0
    acceptance_date: Optional[str] = None
    bureau_type: Optional[str] = None
    sub_type_extra: Optional[str] = None
    judicial_unit: Optional[str] = None
    # Excel import / ek alanlar
    atama_tarihi: Optional[str] = None
    hasar_dosya_no: Optional[str] = None
    hukuk_no: Optional[str] = None
    klasor_no_2: Optional[str] = None
    notes: Optional[str] = None
    parties: List[CasePartyCreate] = []
    lawyers: List[CaseLawyerCreate] = []


class CaseListRead(BaseModel):
    id: int
    tracking_no: str
    esas_no: Optional[str] = None
    status: str
    service_type: Optional[str] = None
    file_type: Optional[str] = None
    sub_type: Optional[str] = None
    subject: Optional[str] = None
    court: Optional[str] = None
    opening_date: Optional[str] = None
    responsible_lawyer_name: Optional[str] = None
    uyap_lawyer_name: Optional[str] = None
    maddi_tazminat: float = 0
    manevi_tazminat: float = 0
    acceptance_date: Optional[str] = None
    bureau_type: Optional[str] = None
    sub_type_extra: Optional[str] = None
    judicial_unit: Optional[str] = None
    atama_tarihi: Optional[date] = None
    hasar_dosya_no: Optional[str] = None
    hukuk_no: Optional[str] = None
    klasor_no_2: Optional[str] = None
    notes: Optional[str] = None
    dosya_son_durumu: Optional[str] = None
    # Aramayı eşleştiren esas tarihçesi satırları (G045). Yalnız q ile arama
    # yapıldığında dolar: dosya ESKİ esas numarasıyla bulunduğunda listede
    # "hangi aşamanın numarasıydı" görünsün diye (`stage`).
    esas_matches: List[Dict[str, Any]] = []
    missing_required_fields: List[dict] = []
    created_at: datetime
    updated_at: Optional[datetime] = None
    parties: List[CasePartyBase] = []
    lawyers: List[CaseLawyerCreate] = []

    model_config = ConfigDict(from_attributes=True)


class CaseRead(BaseModel):
    id: int
    tracking_no: str
    esas_no: Optional[str] = None
    # Esas numarası tarihçesi (G045, şartname §1.3): {esas_no, stage, court,
    # is_current, source}. `esas_no` bu listedeki is_current satırının
    # kopyasıdır — ikinci doğruluk kaynağı değil, türetilmiş değer.
    esas_numbers: List[Dict[str, Any]] = []
    status: str
    service_type: Optional[str] = None
    file_type: Optional[str] = None
    sub_type: Optional[str] = None
    subject: Optional[str] = None
    court: Optional[str] = None
    opening_date: Optional[str] = None
    responsible_lawyer_name: Optional[str] = None
    uyap_lawyer_name: Optional[str] = None
    maddi_tazminat: float = 0
    manevi_tazminat: float = 0
    acceptance_date: Optional[str] = None
    bureau_type: Optional[str] = None
    sub_type_extra: Optional[str] = None
    judicial_unit: Optional[str] = None
    # Excel import / ek alanlar
    atama_tarihi: Optional[date] = None
    hasar_dosya_no: Optional[str] = None
    hukuk_no: Optional[str] = None
    klasor_no_2: Optional[str] = None
    notes: Optional[str] = None
    # Takip alanları
    case_stage: Optional[str] = None
    dosya_son_durumu: Optional[str] = None
    # Yerel Karar
    karar_tarihi: Optional[date] = None
    karar_turu: Optional[str] = None
    karar_lehine: Optional[str] = None
    yerel_karar_durumu: Optional[str] = None   # kapalı liste (local_decisions, G060)
    karar_no: Optional[str] = None
    karar_teblig_tarihi: Optional[date] = None
    karar_aciklama: Optional[str] = None
    # İstinaf
    istinaf_basvuru_tarihi: Optional[date] = None
    istinaf_karar_durumu: Optional[str] = None
    istinaf_karar_tarihi: Optional[date] = None
    istinaf_mahkemesi: Optional[str] = None
    istinaf_esas_no: Optional[str] = None
    istinaf_karar_no: Optional[str] = None
    istinaf_karar_aciklama: Optional[str] = None
    istinaf_teblig_tarihi: Optional[date] = None
    # Temyiz
    temyiz_basvuru_tarihi: Optional[date] = None
    temyiz_karar_durumu: Optional[str] = None
    temyiz_karar_tarihi: Optional[date] = None
    temyiz_mahkemesi: Optional[str] = None
    temyiz_esas_no: Optional[str] = None
    temyiz_karar_no: Optional[str] = None
    temyiz_eden_durumu: Optional[str] = None
    temyiz_karar_aciklama: Optional[str] = None
    temyiz_teblig_tarihi: Optional[date] = None
    # Karar Düzeltme
    karar_duzeltme_durumu: Optional[str] = None
    karar_duzeltme_esas_no: Optional[str] = None
    karar_duzeltme_karar_no: Optional[str] = None
    karar_duzeltme_tarihi: Optional[date] = None
    karar_duzeltme_teblig_tarihi: Optional[date] = None
    karar_duzeltme_aciklama: Optional[str] = None
    yeni_esas_no: Optional[str] = None
    # Kesinleşme / İnfaz
    kesinlesme_tarihi: Optional[date] = None
    infaz_tarihi: Optional[date] = None
    # FAZ F aktarım alanları (G044) — hepsi opsiyonel: aktarım partiler hâlinde
    # geleceği için boş gelmek NORMAL durumdur, doğrulama hatası değil.
    # istinaf_basvuran_taraf ve iddia_edilen_kusur KAPALI referans listelerinden
    # gelir (appealing_parties / alleged_faults); tip serbest metindir çünkü değer
    # listenin ADIDIR — diğer 13 listede de (sub_type, bureau_type…) desen budur.
    islah_tutari: Optional[float] = None
    arsiv_tarihi: Optional[date] = None
    istinaf_basvuran_taraf: Optional[str] = None
    arabuluculuk_no: Optional[str] = None
    arabuluculuk_karar_tarihi: Optional[date] = None
    tibbi_surec: Optional[str] = None
    tibbi_olay: Optional[str] = None
    iddia_edilen_kusur: Optional[str] = None
    hastada_olusan_zarar: Optional[str] = None
    uygulanan_yontem: Optional[str] = None
    # Belgeleme olayı alanları (G103) — kapalı listeler (event_types /
    # judgment_roles); NULL = "karar okunmadı", hiçbir bağlamda zorunlu değil.
    olay_turu: Optional[str] = None
    hukumdeki_rol: Optional[str] = None
    # Müvekkil Tipi / Hizmet Türü (G119) — kapalı listeler (client_types /
    # service_types, DB-2026-002); NULL = "bilinmiyor", hiçbir bağlamda zorunlu
    # değil. `service_type` (ofis dosya no hizmet bloğu) ile İLGİSİZ.
    muvekkil_tipi: Optional[str] = None
    hizmet_turu: Optional[str] = None
    # Dava değeri ham hâli + para birimi (G123) — `maddi_tazminat` bundan
    # türetilir; NULL = bilinmiyor.
    dava_degeri: Optional[float] = None
    para_birimi: Optional[str] = None
    created_at: datetime
    parties: List[CasePartyBase] = []
    lawyers: List[CaseLawyerCreate] = []
    history: List[Dict[str, Any]] = []
    documents: List[Dict[str, Any]] = []
    # Kartın föyleri (`case_foys`, G063) + kapsam işareti (G113) + föy düzeyi
    # teslim alanları (G123): {id, sistem_no, tku_no, hasar_no, mko_id,
    # muvekkil_no, muvekkil_tipi, hizmet_turu, durum, source, case_party_id,
    # onceki_tracking_no, kapsam_durumu, kapsam_gerekcesi, kapsam_tarihi}.
    # `onceki_tracking_no`: TKU kart birleştirmesinde sönen kartın ofis
    # numarası (NULL = föy başka karttan taşınmadı). `kapsam_durumu` NULL =
    # kapsamda; SILINDI | KAPSAM_DISI işaretli föy kartın föy panelinde
    # "kapsam dışı" rozetiyle gösterilir (CaseFoyPanel, G123).
    foyler: List[Dict[str, Any]] = []
    # Kartın hizmet kayıtları (`case_hizmetleri`, G248): {id, case_party_id,
    # muvekkil_adi, hizmet_turu, kaynak ("foy" | "elle"), foy_id, sistem_no}.
    # `hizmet_turu` (yukarıda) bu listeden TÜRETİLEN özettir (" ; " birleşik).
    hizmetler: List[Dict[str, Any]] = []

    model_config = ConfigDict(from_attributes=True)


class CaseTrackingUpdate(BaseModel):
    case_stage: Optional[str] = None
    dosya_son_durumu: Optional[str] = None
    # Arabuluculuk — davanın ön aşaması (G073; kolonlar G044'te açılmıştı,
    # yazma yolu bu turda takip paneline verildi)
    arabuluculuk_no: Optional[str] = None
    arabuluculuk_karar_tarihi: Optional[date] = None
    # Yerel Karar
    karar_tarihi: Optional[date] = None
    karar_turu: Optional[str] = None
    karar_lehine: Optional[str] = None
    yerel_karar_durumu: Optional[str] = None   # kapalı liste (local_decisions, G060)
    karar_no: Optional[str] = None
    karar_teblig_tarihi: Optional[date] = None
    karar_aciklama: Optional[str] = None
    # Hükmedilen tutarlar — None gönderilen alan silinir (exclude_unset semantiği)
    hukmedilen_maddi: Optional[float] = None
    hukmedilen_manevi: Optional[float] = None
    hukmedilen_toplam: Optional[float] = None
    # İstinaf
    istinaf_basvuru_tarihi: Optional[date] = None
    istinaf_karar_durumu: Optional[str] = None
    istinaf_karar_tarihi: Optional[date] = None
    istinaf_mahkemesi: Optional[str] = None
    istinaf_esas_no: Optional[str] = None
    istinaf_karar_no: Optional[str] = None
    istinaf_karar_aciklama: Optional[str] = None
    istinaf_teblig_tarihi: Optional[date] = None
    # Temyiz
    temyiz_basvuru_tarihi: Optional[date] = None
    temyiz_karar_durumu: Optional[str] = None
    temyiz_karar_tarihi: Optional[date] = None
    temyiz_mahkemesi: Optional[str] = None
    temyiz_esas_no: Optional[str] = None
    temyiz_karar_no: Optional[str] = None
    temyiz_eden_durumu: Optional[str] = None
    temyiz_karar_aciklama: Optional[str] = None
    temyiz_teblig_tarihi: Optional[date] = None
    # Karar Düzeltme
    karar_duzeltme_durumu: Optional[str] = None
    karar_duzeltme_esas_no: Optional[str] = None
    karar_duzeltme_karar_no: Optional[str] = None
    karar_duzeltme_tarihi: Optional[date] = None
    karar_duzeltme_teblig_tarihi: Optional[date] = None
    karar_duzeltme_aciklama: Optional[str] = None
    yeni_esas_no: Optional[str] = None
    # Kesinleşme / İnfaz + kapanış (arşiv, G073)
    kesinlesme_tarihi: Optional[date] = None
    infaz_tarihi: Optional[date] = None
    arsiv_tarihi: Optional[date] = None
    # Belgeleme olayı alanları (G103) — kapalı listeler (event_types /
    # judgment_roles); yazma yolu takip paneli, doğrulama update_case_tracking
    # kapısında (G066 davranış eşi, case_manager._EVENT_LIST_COLUMNS)
    olay_turu: Optional[str] = None
    hukumdeki_rol: Optional[str] = None
    # Müvekkil Tipi (G119) — kapalı liste (client_types); yazma yolu takip paneli,
    # doğrulama aynı kapıda (case_manager._EVENT_LIST_COLUMNS, G066 davranış eşi).
    # `hizmet_turu` BURADA YOK (G250): kart alanı `case_hizmetleri`'nden TÜRETİLEN
    # özettir, takip ucundan yazılmaz — eski istemci gönderirse yok sayılır (Pydantic
    # tanımadığı alanı atar); hizmet `/api/cases/{id}/hizmetler` uçlarından yazılır.
    muvekkil_tipi: Optional[str] = None
    # G124 — dava değeri + para birimi (kapalı liste currencies) ve tıbbi
    # beşli (ÇOK DEĞERLİ, " ; " ayraçlı; her parça kendi listesine karşı
    # doğrulanır: case_manager._MULTI_LIST_COLUMNS). None = alan temizlenir.
    dava_degeri: Optional[float] = None
    para_birimi: Optional[str] = None
    tibbi_surec: Optional[str] = None
    tibbi_olay: Optional[str] = None
    iddia_edilen_kusur: Optional[str] = None
    hastada_olusan_zarar: Optional[str] = None
    uygulanan_yontem: Optional[str] = None
    note: Optional[str] = None


class CaseStageLogRead(BaseModel):
    id: int
    case_id: int
    stage: str
    changed_at: datetime
    changed_by: Optional[str] = None
    source: Optional[str] = None
    note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CaseStageDecisionRead(BaseModel):
    """Aşama/karar tarihçesi satırı (`case_stage_decisions`, G062).

    Sıralama sözleşmesi `sira_no`dur, tarih DEĞİL (tasarım paketi: 170 föyde
    karar tarihleri güvenilmez). `dogrulama_durumu` tahmin yasağının damgası
    (UYAP|BELGE|TURETILDI|BELIRSIZ). Okuma/yazma UÇLARI FAZ F + UI işidir;
    şema tabloyla birlikte doğar ki dış sözleşme tek yerden türesin.
    """
    id: int
    case_id: int
    stage: str
    sira_no: int
    mahkeme: Optional[str] = None
    esas_no: Optional[str] = None
    karar_no: Optional[str] = None
    karar_tarihi: Optional[date] = None
    karar_durumu: Optional[str] = None       # stage'in G060 kapalı listesinin adı
    teblig_tarihi: Optional[date] = None
    basvuru_tarihi: Optional[date] = None    # kanun yoluna başvuru tarihi (G155)
    basvuran_taraf: Optional[str] = None
    aciklama: Optional[str] = None
    dogrulama_durumu: str = "BELIRSIZ"
    kaynak_id: Optional[int] = None
    source: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CaseEsasNumberRead(BaseModel):
    """Esas numarası tarihçesi satırı (`case_esas_numbers`, G045).

    Aşama tarihçesi yanıtında yalnız GÜNCEL OLMAYAN satırlar için kullanılır
    (`CaseStageDecisionsResponse.onceki_esaslar`): güncel numara zaten
    `cases.esas_no`dur, onu ikinci kez döndürmek ikinci doğruluk kaynağı olurdu.
    """
    id: int
    case_id: int
    esas_no: str
    stage: str
    court: Optional[str] = None
    is_current: bool = False
    source: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CaseStageDecisionsResponse(BaseModel):
    """`GET /api/cases/{id}/stage-decisions` yanıtı (G072).

    İki liste BİLİNÇLİ AYRI: `decisions` kararların künyesi (hangi aşamada ne
    karar çıktı), `onceki_esaslar` ise NUMARANIN tarihçesi (görevsizlik/
    yetkisizlik sonrası değişen esas no). Aynı zaman çizgisinin parçalarıdır
    ama farklı şeylerdir; tek listede birleştirmek "önceki esas"ı karar sanan
    bir arayüz üretirdi.
    """
    case_id: int
    decisions: List[CaseStageDecisionRead] = []
    onceki_esaslar: List[CaseEsasNumberRead] = []


# ---- İlişkili Davalar ----

class CaseRelationCreate(BaseModel):
    target_case_id: int
    relation_type: str = "ILGILI"
    note: Optional[str] = None


class CaseRelationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_case_id: int
    target_case_id: int
    relation_type: str
    note: Optional[str]
    created_by: Optional[str]
    created_at: datetime


class RelatedCaseSummary(BaseModel):
    """Hem manuel hem otomatik için ortak şema — frontend bu yapıyı bekliyor."""
    id: int
    tracking_no: str
    esas_no: Optional[str] = None
    court: Optional[str] = None
    status: str
    file_type: Optional[str] = None
    parties: List[Dict[str, str]] = []
    relation_id: Optional[int] = None
    relation_type: str
    match_reason: str
    confidence_score: Optional[int] = None
    is_manual: bool
    note: Optional[str] = None


class RelatedCasesResponse(BaseModel):
    manual: List[RelatedCaseSummary]
    automatic: List[RelatedCaseSummary]
    # G128: aynı hasta + aynı doktor önerileri — onay bekler (Bağla / Reddet).
    suggested: List[RelatedCaseSummary] = []


class CaseRelationReject(BaseModel):
    """Öneriyi reddet (G128): `case_relations`a ONERI_RED satırı düşer, bir daha önerilmez."""
    target_case_id: int


# ─── DAVA NOTLARI (G214) ──────────────────────────────────────────────────────
# Sözleşme SABİT (G215 frontend paneli buna göre yazılır): routes/case_notes.py.

CASE_NOTE_MAX_LEN = 5000


class CaseNoteCreate(BaseModel):
    """`POST /api/cases/{id}/notes` gövdesi — trim SONRASI 1..5000 karakter, aksi 422."""
    body: str

    @field_validator("body")
    @classmethod
    def _body_trim_ve_uzunluk(cls, value: str) -> str:
        temiz = value.strip()
        if not temiz:
            raise ValueError("Not boş olamaz.")
        if len(temiz) > CASE_NOTE_MAX_LEN:
            raise ValueError(f"Not en fazla {CASE_NOTE_MAX_LEN} karakter olabilir.")
        return temiz


class CaseNoteRead(BaseModel):
    """Tek not. `created_at` UTC ve ofsetli ISO8601 (`...+00:00`)."""
    id: int
    body: str
    author_name: Optional[str] = None
    author_email: str
    created_at: str
    can_delete: bool


# ─── HİZMET KAYDI (G248) ─────────────────────────────────────────────────────
# Sözleşme: routes/case_hizmetleri.py — kart × müvekkil × hizmet satırları.

class CaseHizmetRead(BaseModel):
    """Tek hizmet satırı. `kaynak`: "foy" (aktarım yazdı, salt okunur) | "elle"."""
    id: int
    case_party_id: int
    muvekkil_adi: Optional[str] = None
    hizmet_turu: str
    kaynak: Literal["foy", "elle"]
    foy_id: Optional[int] = None
    sistem_no: Optional[str] = None     # yalnız föy kaynaklı satırda


class CaseHizmetCreate(BaseModel):
    """`POST /api/cases/{id}/hizmetler` gövdesi — tek elle satır."""
    case_party_id: int
    hizmet_turu: str


class CaseHizmetKumesi(BaseModel):
    """`PUT /api/cases/{id}/hizmetler/{case_party_id}` gövdesi — müvekkilin elle
    hizmet KÜMESİ (çoklu seçim); boş liste = elle satırların tamamı silinir."""
    hizmet_turleri: List[str]


# ─── HATA BİLDİRİMİ (02.10.2026) ──────────────────────────────────────────────
# Sözleşme: routes/hata_bildirimleri.py (frontend `lib/hataBildirimleri.ts` ile ORTAK).

HATA_ALAN_MAX_LEN = 80
HATA_ETIKET_MAX_LEN = 120
HATA_DEGER_MAX_LEN = 1000
HATA_ACIKLAMA_MAX_LEN = 2000
HATA_ALICI_AZAMI = 30
# Doğrudan düzeltmede karta yazılacak değerin tavanı (kimlik/numara alanları kısa metindir).
HATA_DOGRUDAN_DEGER_MAX_LEN = 200

HATA_DURUM_ACIK = "ACIK"
HATA_KAPANIS_SONUCLARI = ("COZULDU", "REDDEDILDI")


def _hata_metni(value: Optional[str], azami: int, ad: str) -> Optional[str]:
    """Trim + boş → None + uzunluk tavanı (aşım 422)."""
    temiz = (value or "").strip()
    if not temiz:
        return None
    if len(temiz) > azami:
        raise ValueError(f"{ad} en fazla {azami} karakter olabilir.")
    return temiz


class HataBildirimiCreate(BaseModel):
    """`POST /api/hata-bildirimleri` gövdesi.

    Hedef TEK: `case_id` ya da `client_id`. `dogru_deger` ile `aciklama`dan en az
    biri dolu olmalı — "yanlış" demek yetmez, düzeltecek kişi neyin yanlış olduğunu
    bilmeli. `mevcut_deger` bildirim anındaki ekran değeridir (istemci gönderir).
    """
    case_id: Optional[int] = None
    client_id: Optional[int] = None
    alan: str
    alan_etiketi: str
    mevcut_deger: Optional[str] = None
    dogru_deger: Optional[str] = None
    aciklama: Optional[str] = None
    # Bildirimin gideceği kişilerin e-postaları — `GET /api/hata-bildirimleri/alicilar`
    # listesinden seçilir (route listeye karşı doğrular). Boş/yok = varsayılan alıcılar.
    alicilar: Optional[List[str]] = None
    # Doğrudan düzeltme: bildiren (davanın sorumlu avukatı / yönetici) `dogru_deger`i
    # kimseye bildirmeden karta kendisi yazar. Yalnız dava hedefinde ve route'un izin
    # verdiği alanlarda; `mevcut_deger` ekranda gördüğü değerdir (bayat ekran → 409).
    dogrudan_duzelt: bool = False

    @field_validator("alicilar")
    @classmethod
    def _alicilar(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if not value:
            return None
        temiz: List[str] = []
        for ham in value:
            email = (ham or "").strip().lower()
            if email and email not in temiz:
                temiz.append(email)
        if len(temiz) > HATA_ALICI_AZAMI:
            raise ValueError(f"En fazla {HATA_ALICI_AZAMI} alıcı seçilebilir.")
        return temiz or None

    @field_validator("alan")
    @classmethod
    def _alan(cls, value: str) -> str:
        temiz = _hata_metni(value, HATA_ALAN_MAX_LEN, "Alan")
        if not temiz:
            raise ValueError("Alan boş olamaz.")
        return temiz

    @field_validator("alan_etiketi")
    @classmethod
    def _alan_etiketi(cls, value: str) -> str:
        temiz = _hata_metni(value, HATA_ETIKET_MAX_LEN, "Alan etiketi")
        if not temiz:
            raise ValueError("Alan etiketi boş olamaz.")
        return temiz

    @field_validator("mevcut_deger", "dogru_deger")
    @classmethod
    def _deger(cls, value: Optional[str]) -> Optional[str]:
        return _hata_metni(value, HATA_DEGER_MAX_LEN, "Değer")

    @field_validator("aciklama")
    @classmethod
    def _aciklama(cls, value: Optional[str]) -> Optional[str]:
        return _hata_metni(value, HATA_ACIKLAMA_MAX_LEN, "Açıklama")

    @model_validator(mode="after")
    def _tek_hedef_ve_icerik(self):
        if (self.case_id is None) == (self.client_id is None):
            raise ValueError("Hedef olarak dava ya da müvekkilden yalnız biri verilmelidir.")
        if not self.dogru_deger and not self.aciklama:
            raise ValueError("Doğru değer ya da açıklamadan en az biri yazılmalıdır.")
        if self.dogrudan_duzelt:
            if self.case_id is None:
                raise ValueError("Doğrudan düzeltme yalnız dava kartında yapılabilir.")
            if not self.dogru_deger:
                raise ValueError("Doğrudan düzeltme için doğru değer yazılmalıdır.")
            if len(self.dogru_deger) > HATA_DOGRUDAN_DEGER_MAX_LEN:
                raise ValueError(f"Doğru değer en fazla {HATA_DOGRUDAN_DEGER_MAX_LEN} karakter olabilir.")
        return self


class HataBildirimiKapat(BaseModel):
    """`POST /api/hata-bildirimleri/{id}/kapat` gövdesi."""
    sonuc: str
    kapatma_notu: Optional[str] = None

    @field_validator("sonuc")
    @classmethod
    def _sonuc(cls, value: str) -> str:
        temiz = (value or "").strip().upper()
        if temiz not in HATA_KAPANIS_SONUCLARI:
            raise ValueError("Sonuç COZULDU ya da REDDEDILDI olmalıdır.")
        return temiz

    @field_validator("kapatma_notu")
    @classmethod
    def _not(cls, value: Optional[str]) -> Optional[str]:
        return _hata_metni(value, HATA_ACIKLAMA_MAX_LEN, "Not")


class HataAlicisi(BaseModel):
    """Bildirimin gönderildiği kişi (gönderim anındaki ad)."""
    email: str
    ad: str


class HataAliciAdayi(HataAlicisi):
    """Alıcı seçicisinin satırı (`GET /api/hata-bildirimleri/alicilar`)."""
    grup: str            # IDARI | AVUKAT | YONETICI
    varsayilan: bool     # pencerede ön-seçili gelir


class HataBildirimiRead(BaseModel):
    """Tek hata bildirimi. Zaman damgaları UTC ve ofsetli ISO8601."""
    id: int
    case_id: Optional[int] = None
    client_id: Optional[int] = None
    # Hedefin okunur adı: dava künyesi (ofis no · esas no) ya da müvekkil adı.
    hedef_etiketi: Optional[str] = None
    # Uygulama içi yol — bildirim ve pano satırı buraya gider.
    link: str
    alan: str
    alan_etiketi: str
    mevcut_deger: Optional[str] = None
    dogru_deger: Optional[str] = None
    aciklama: Optional[str] = None
    durum: str
    alicilar: List[HataAlicisi] = []
    bildiren_ad: Optional[str] = None
    bildiren_email: str
    created_at: str
    kapatan_ad: Optional[str] = None
    kapatan_email: Optional[str] = None
    kapatma_notu: Optional[str] = None
    kapatildi_at: Optional[str] = None
