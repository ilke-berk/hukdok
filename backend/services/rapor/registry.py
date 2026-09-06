"""Raporlama kayıt defteri — hangi veri kaynağı, hangi kolon, hangi tip (G130).

**Beyaz liste ilkesi (plan K1):** istemciden (ve asistandan, K6) gelen hiçbir
string SQL'e ham girmez. Motor yalnız buradaki `Kolon.ifade` SQLAlchemy
ifadelerini kullanır; istemcinin gönderdiği anahtar bu sözlükte yoksa 422.
`SETTINGS_REGISTRY` / `LIST_REGISTRY` deseninin (services/app_settings.py,
managers/reference_lists.py) rapor ikizi.

Dört veri kaynağı (plan §2.3): `davalar` (cases), `muvekkiller` (clients),
`belgeler` (case_documents JOIN cases), `foyler` (case_foys JOIN cases).
Tenant + soft-delete kuralı `VeriKaynagi.kisitlar(tenant_id)` ile TEK yerden
gelir (K2, `case_manager._apply_tenant_filter` ile aynı kural):
`tenant_filter_clause` + `deleted_at IS NULL`; `belgeler`/`foyler` bunu `cases`
JOIN'iyle (INNER — davasız/silinmiş davalı satır rapora girmez), `muvekkiller`
`Client` üzerinden alır.

Kataloga GİRMEYENLER (plan §2.3): `tenant_id`, `deleted_*`, `notes` (serbest
metin, PII), `ham_veri` (föy ham satırı); ayrıca `clients.tc_no` / `source_ids`
ve belge `email_error` / `conversion_spool_path` (teknik/PII, rapor değeri yok).

Kolon tipi kolonun SQLAlchemy tipinden türetilir (`_tip_bul`); kapalı listeli
alanlar `liste` tipine `secenekler` ile ZORLANIR — seçeneksiz `liste` kolon YOK
(`test_g130_rapor_temeli` bunu mekanik doğrular). Seçenek kaynağı üç katman:
sabit çekirdek (seed sabitleri / kod sözlükleri) + referans tablosu adları
(`secenek_tablosu`, aktif satırlar) + kolondaki DISTINCT değerler; hepsi
`secenekleri_getir(kolon, db)` ile birleşir (sıra korunur, tekrar yok).
Türetilmiş metin birleştirmeleri `func.aggregate_strings(..., " ; ")` —
Postgres'te string_agg, sqlite'ta group_concat (testler sqlite koşar).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, and_, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

import models
from auth_helpers import tenant_filter_clause
from managers.seed_data import (
    APPEAL_DECISIONS, APPEALING_PARTIES, CASSATION_DECISIONS, CLIENT_TYPES, CURRENCIES, EVENT_TYPES,
    JUDGMENT_ROLES, LOCAL_DECISIONS, REVISION_DECISIONS, SERVICE_TYPES,
)
from required_fields import MISSING_BUCKETS

AYRAC = " ; "

# ─── Tipler ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Kolon:
    anahtar: str
    etiket: str
    tip: str                      # metin | liste | tarih | sayi | para | mantik
    ifade: Any                    # SQLAlchemy ColumnElement (kolon ya da scalar alt sorgu)
    filtrelenebilir: bool = True
    siralanabilir: bool = True
    turetilmis: bool = False
    secenekler: tuple[str, ...] = ()          # sabit çekirdek (liste tipinde zorunlu)
    # Referans listesi ORM modeli (`name`/`active`/`sequence`/`id` kolonlu); eski stil
    # Column() modelleri mypy'de öznitelik taşımadığı için `Any`.
    secenek_tablosu: Any = None
    zaman_damgali: bool = False               # tarih tipinde DateTime kolon (gün aralığı karşılaştırması)


@dataclass(frozen=True)
class VeriKaynagi:
    anahtar: str
    etiket: str
    aciklama: str
    from_clause: Any                          # Table ya da Join
    kisitlar: Callable[[str], list[ColumnElement]]
    kolonlar: dict[str, Kolon]
    varsayilan_kolonlar: tuple[str, ...]
    birincil_anahtar: Any = field(default=None)   # deterministik sıralama için son kırıcı


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def _tip_bul(kolon) -> tuple[str, bool]:
    """SQLAlchemy kolon tipinden rapor tipi; ikinci değer DateTime mi."""
    t = kolon.type
    if isinstance(t, Boolean):
        return "mantik", False
    if isinstance(t, DateTime):
        return "tarih", True
    if isinstance(t, Date):
        return "tarih", False
    if isinstance(t, Numeric):
        return "para", False
    if isinstance(t, Integer):
        return "sayi", False
    return "metin", False


def _adlar(cift_listesi) -> tuple[str, ...]:
    """Seed sabiti `[(kod, ad), ...]` → adlar (denormalize ad saklanan alanlar için)."""
    return tuple(ad for _kod, ad in cift_listesi)


def _kolon(model, anahtar: str, etiket: str, *, liste: tuple[str, ...] | None = None,
           secenek_tablosu: Any = None, tip: Optional[str] = None) -> Kolon:
    """Düz tablo kolonu → Kolon. `liste` verilirse tip `liste` ve seçenekler dolu."""
    col = getattr(model, anahtar)
    bulunan, zaman = _tip_bul(col)
    if liste is not None or secenek_tablosu is not None:
        return Kolon(anahtar, etiket, "liste", col, secenekler=tuple(liste or ()),
                     secenek_tablosu=secenek_tablosu)
    return Kolon(anahtar, etiket, tip or bulunan, col, zaman_damgali=zaman)


def _turetilmis(anahtar: str, etiket: str, tip: str, ifade) -> Kolon:
    """Türetilmiş kolon: v1'de filtrelenemez ve sıralanamaz (plan §2.2)."""
    return Kolon(anahtar, etiket, tip, ifade, filtrelenebilir=False, siralanabilir=False, turetilmis=True)


def _sozluk(kolonlar: list[Kolon]) -> dict[str, Kolon]:
    sozluk: dict[str, Kolon] = {}
    for k in kolonlar:
        if k.anahtar in sozluk:
            raise ValueError(f"kayıt defterinde kolon tekrarı: {k.anahtar}")
        sozluk[k.anahtar] = k
    return sozluk


# ─── Kapalı liste çekirdekleri ───────────────────────────────────────────────
# cases.status: model şerhi (DERDEST | DANIŞ | MAHZEN) + CaseList.STATUS_ORDER.
DAVA_DURUMLARI = ("DANIŞ", "DERDEST", "KARAR", "ISTINAF", "TEMYIZ", "KAPALI", "MAHZEN")
# cases.case_stage: models.py şerhi + frontend trackingDraft.STAGES anahtarları.
DAVA_ASAMALARI = ("DERDEST", "KARAR", "ISTINAF", "TEMYIZ", "KARAR_DUZELTME", "KESINLESME", "INFAZ", "KAPALI")
KARAR_TURLERI = ("KABUL", "RED", "KISMI_KABUL", "FERAGAT", "UZLASMA", "DUSME")   # trackingDraft.STAGE_FIELDS
KARAR_LEHINE = ("LEHINE", "ALEYHINE", "KISMI")
# file_types seed'i fonksiyon-yerel (seed_data._seed_file_types); çekirdek burada,
# tablo + DISTINCT katmanı panelden eklenenleri getirir.
DAVA_TURLERI = ("Ceza", "Hukuk", "İcra", "İdare", "İdari Yargı", "Arabuluculuk", "Savcılık", "Tahkim", "Vergi",
                "Danışmanlık")
BELGE_LINK_MODLARI = ("LINKED", "TEST", "UNLINKED")
BELGE_UPLOAD_DURUMLARI = ("pending", "uploaded", "failed")
BELGE_DONUSUM_DURUMLARI = ("pending", "failed")
FOY_DURUMLARI = ("DERDEST", "MAHZEN")
FOY_KAPSAM_DURUMLARI = ("SILINDI", "KAPSAM_DISI")
MUVEKKIL_ILETISIM_TURLERI = ("Client", "Other")
MUVEKKIL_TIPLERI_CARI = ("Individual", "Corporate")
CINSIYETLER = ("Erkek", "Kadın")                       # NewClient.tsx seçenekleri ("Belirtilmemiş" = NULL)
# file_statuses seed'i fonksiyon-yerel 38 ad (seed_data._seed_file_statuses); çekirdek
# sık kullanılanlar, kalanı tablo + DISTINCT katmanından gelir.
DOSYA_SON_DURUMLARI = ("Bilirkişide", "İstinafta", "Temyizde", "Karar Düzeltmede", "Kesin Lehe", "Kesin Aleyhe")


# ─── davalar ─────────────────────────────────────────────────────────────────

def _dava_kisitlari(tenant_id: str) -> list[ColumnElement]:
    return [models.Case.deleted_at.is_(None), tenant_filter_clause(models.Case, tenant_id)]


def _taraf_adlari(party_type: str):
    P = models.CaseParty
    return (
        select(func.aggregate_strings(P.name, AYRAC))
        .where(and_(P.case_id == models.Case.id, P.party_type == party_type))
        .correlate(models.Case)
        .scalar_subquery()
    )


def _foy_sayisi():
    F = models.CaseFoy
    return select(func.count(F.id)).where(F.case_id == models.Case.id).correlate(models.Case).scalar_subquery()


def _belge_sayisi():
    D = models.CaseDocument
    return (
        select(func.count(D.id))
        .where(and_(D.case_id == models.Case.id, D.deleted_at.is_(None)))
        .correlate(models.Case)
        .scalar_subquery()
    )


_C = models.Case
_DAVA_KOLONLARI: list[Kolon] = [
    _kolon(_C, "id", "ID"),
    _kolon(_C, "tracking_no", "Ofis Dosya No"),
    _kolon(_C, "esas_no", "Esas No"),
    _kolon(_C, "status", "Durum", liste=DAVA_DURUMLARI),
    _kolon(_C, "file_type", "Dava Türü", liste=DAVA_TURLERI, secenek_tablosu=models.FileType),
    _kolon(_C, "sub_type", "Uzmanlık Alanı"),
    _kolon(_C, "service_type", "Hizmet Tipi"),
    _kolon(_C, "subject", "Dava Konusu"),
    _kolon(_C, "court", "Mahkeme"),
    _kolon(_C, "judicial_unit", "Yargı Birimi"),
    _kolon(_C, "opening_date", "Açılış Tarihi"),
    _kolon(_C, "acceptance_date", "İş Kabul Tarihi"),
    _kolon(_C, "atama_tarihi", "Atama Tarihi"),
    _kolon(_C, "responsible_lawyer_name", "Sorumlu Avukat"),
    _kolon(_C, "uyap_lawyer_name", "UYAP Avukatı"),
    _kolon(_C, "bureau_type", "Büro Özel Türü", secenek_tablosu=models.BureauType,
           liste=("ALEYHE", "DR ÖZEL", "HASTANE ÖZEL MÜVEKKİL", "LEXİS", "RÜCU", "VEKALETLİ TAKİP",
                  "VEKALETSİZ TAKİP", "ÖZEL")),
    _kolon(_C, "sub_type_extra", "Ek Alt Kırılım"),
    _kolon(_C, "klasor_no_2", "Eski Sistem No"),
    _kolon(_C, "hasar_dosya_no", "Hasar Dosya No"),
    _kolon(_C, "hukuk_no", "Hukuk No"),
    _kolon(_C, "tku_no", "TKU No"),
    _kolon(_C, "sistem_no", "Sistem No"),
    _kolon(_C, "case_stage", "Aşama", liste=DAVA_ASAMALARI),
    _kolon(_C, "dosya_son_durumu", "Dosya Son Durumu", secenek_tablosu=models.FileStatus, liste=DOSYA_SON_DURUMLARI),
    # Yerel karar
    _kolon(_C, "karar_tarihi", "Karar Tarihi"),
    _kolon(_C, "karar_turu", "Karar Türü", liste=KARAR_TURLERI),
    _kolon(_C, "karar_lehine", "Karar Lehine", liste=KARAR_LEHINE),
    _kolon(_C, "yerel_karar_durumu", "Karar Durumu", secenek_tablosu=models.LocalDecision,
           liste=_adlar(LOCAL_DECISIONS)),
    _kolon(_C, "karar_no", "Karar No"),
    _kolon(_C, "karar_teblig_tarihi", "Karar Tebliğ Tarihi"),
    _kolon(_C, "karar_aciklama", "Karar Açıklaması"),
    _kolon(_C, "hukmedilen_maddi", "Hükmedilen Maddi"),
    _kolon(_C, "hukmedilen_manevi", "Hükmedilen Manevi"),
    _kolon(_C, "hukmedilen_toplam", "Hükmedilen Toplam"),
    # İstinaf
    _kolon(_C, "istinaf_basvuru_tarihi", "İstinaf Başvuru Tarihi"),
    _kolon(_C, "istinaf_basvuran_taraf", "İstinaf Başvuran Taraf", liste=_adlar(APPEALING_PARTIES),
           secenek_tablosu=models.AppealingParty),
    _kolon(_C, "istinaf_karar_durumu", "İstinaf Karar Durumu", secenek_tablosu=models.AppealDecision,
           liste=_adlar(APPEAL_DECISIONS)),
    _kolon(_C, "istinaf_karar_tarihi", "İstinaf Karar Tarihi"),
    _kolon(_C, "istinaf_mahkemesi", "İstinaf Mahkemesi"),
    _kolon(_C, "istinaf_esas_no", "İstinaf Esas No"),
    _kolon(_C, "istinaf_karar_no", "İstinaf Karar No"),
    _kolon(_C, "istinaf_karar_aciklama", "İstinaf Açıklaması"),
    _kolon(_C, "istinaf_teblig_tarihi", "İstinaf Tebliğ Tarihi"),
    # Temyiz
    _kolon(_C, "temyiz_basvuru_tarihi", "Temyiz Başvuru Tarihi"),
    _kolon(_C, "temyiz_karar_durumu", "Temyiz Karar Durumu", secenek_tablosu=models.CassationDecision,
           liste=_adlar(CASSATION_DECISIONS)),
    _kolon(_C, "temyiz_karar_tarihi", "Temyiz Karar Tarihi"),
    _kolon(_C, "temyiz_mahkemesi", "Temyiz Mahkemesi"),
    _kolon(_C, "temyiz_esas_no", "Temyiz Esas No"),
    _kolon(_C, "temyiz_karar_no", "Temyiz Karar No"),
    _kolon(_C, "temyiz_eden_durumu", "Temyiz Eden"),
    _kolon(_C, "temyiz_karar_aciklama", "Temyiz Açıklaması"),
    _kolon(_C, "temyiz_teblig_tarihi", "Temyiz Tebliğ Tarihi"),
    # Karar düzeltme
    _kolon(_C, "karar_duzeltme_durumu", "Karar Düzeltme Durumu", secenek_tablosu=models.RevisionDecision,
           liste=_adlar(REVISION_DECISIONS)),
    _kolon(_C, "karar_duzeltme_esas_no", "Karar Düzeltme Esas No"),
    _kolon(_C, "karar_duzeltme_karar_no", "Karar Düzeltme Karar No"),
    _kolon(_C, "karar_duzeltme_tarihi", "Karar Düzeltme Tarihi"),
    _kolon(_C, "karar_duzeltme_teblig_tarihi", "Karar Düzeltme Tebliğ Tarihi"),
    _kolon(_C, "karar_duzeltme_aciklama", "Karar Düzeltme Açıklaması"),
    _kolon(_C, "yeni_esas_no", "Yeni Esas No"),
    # Kesinleşme / infaz / arşiv
    _kolon(_C, "kesinlesme_tarihi", "Kesinleşme Tarihi"),
    _kolon(_C, "infaz_tarihi", "İnfaz Tarihi"),
    _kolon(_C, "arsiv_tarihi", "Arşiv Tarihi"),
    # Tutarlar
    _kolon(_C, "maddi_tazminat", "Maddi Tazminat"),
    _kolon(_C, "manevi_tazminat", "Manevi Tazminat"),
    _kolon(_C, "islah_tutari", "Islah Tutarı"),
    _kolon(_C, "dava_degeri", "Dava Değeri"),
    _kolon(_C, "para_birimi", "Para Birimi", liste=_adlar(CURRENCIES), secenek_tablosu=models.Currency),
    # Arabuluculuk
    _kolon(_C, "arabuluculuk_no", "Arabuluculuk No"),
    _kolon(_C, "arabuluculuk_karar_tarihi", "Arabuluculuk Karar Tarihi"),
    # Olay / müvekkil / hizmet (kapalı listeler, ad denormalize)
    _kolon(_C, "olay_turu", "Olay Türü", liste=_adlar(EVENT_TYPES), secenek_tablosu=models.EventType),
    _kolon(_C, "hukumdeki_rol", "Hükümdeki Rol", liste=_adlar(JUDGMENT_ROLES), secenek_tablosu=models.JudgmentRole),
    _kolon(_C, "muvekkil_tipi", "Müvekkil Tipi", liste=_adlar(CLIENT_TYPES), secenek_tablosu=models.ClientType),
    _kolon(_C, "hizmet_turu", "Hizmet Türü", liste=_adlar(SERVICE_TYPES), secenek_tablosu=models.ServiceType),
    # Tıbbi beşli: ÇOK DEĞERLİ metin (" ; " ayraçlı, G124) → liste DEĞİL, `contains` ile aranır.
    _kolon(_C, "tibbi_surec", "Tıbbi Süreç"),
    _kolon(_C, "tibbi_olay", "Tıbbi Olay"),
    _kolon(_C, "iddia_edilen_kusur", "İddia Edilen Kusur"),
    _kolon(_C, "hastada_olusan_zarar", "Hastada Oluşan Zarar"),
    _kolon(_C, "uygulanan_yontem", "Uygulanan Yöntem"),
    _kolon(_C, "active", "Aktif"),
    _kolon(_C, "missing_required_bucket", "Eksik Zorunlu Alan Kovası", liste=tuple(MISSING_BUCKETS)),
    _kolon(_C, "created_at", "Oluşturulma"),
    _kolon(_C, "updated_at", "Güncellenme"),
    # Türetilmiş (plan §2.3)
    _turetilmis("muvekkil_adlari", "Müvekkiller", "metin", _taraf_adlari("CLIENT")),
    _turetilmis("karsi_taraf_adlari", "Karşı Taraflar", "metin", _taraf_adlari("COUNTER")),
    _turetilmis("foy_sayisi", "Föy Sayısı", "sayi", _foy_sayisi()),
    _turetilmis("belge_sayisi", "Belge Sayısı", "sayi", _belge_sayisi()),
]

DAVALAR = VeriKaynagi(
    anahtar="davalar",
    etiket="Davalar",
    aciklama="Dava kartları (silinmişler hariç); müvekkil/karşı taraf adları ve föy/belge sayıları türetilmiş.",
    from_clause=models.Case.__table__,
    kisitlar=_dava_kisitlari,
    kolonlar=_sozluk(_DAVA_KOLONLARI),
    varsayilan_kolonlar=("tracking_no", "esas_no", "muvekkil_adlari", "court", "subject", "status",
                         "responsible_lawyer_name", "opening_date"),
    birincil_anahtar=models.Case.id,
)

# ─── muvekkiller ─────────────────────────────────────────────────────────────

def _muvekkil_kisitlari(tenant_id: str) -> list[ColumnElement]:
    return [models.Client.deleted_at.is_(None), tenant_filter_clause(models.Client, tenant_id)]


def _dava_sayisi():
    P = models.CaseParty
    return (
        select(func.count(func.distinct(P.case_id)))
        .select_from(P.__table__.join(models.Case.__table__, P.case_id == models.Case.id))
        .where(and_(P.client_id == models.Client.id, models.Case.deleted_at.is_(None)))
        .correlate(models.Client)
        .scalar_subquery()
    )


_M = models.Client
_MUVEKKIL_KOLONLARI: list[Kolon] = [
    _kolon(_M, "id", "ID"),
    _kolon(_M, "name", "Müvekkil Adı"),
    _kolon(_M, "cari_kod", "Cari Kod"),
    _kolon(_M, "contact_type", "Kayıt Türü", liste=MUVEKKIL_ILETISIM_TURLERI),
    _kolon(_M, "client_type", "Müvekkil Türü", liste=MUVEKKIL_TIPLERI_CARI),
    _kolon(_M, "category", "Kategori", secenek_tablosu=models.ClientCategory,
           liste=("Doktor", "Sağlık Çalışanı", "Hasta", "Kurum", "Özel Hastane", "Bireysel", "Sigorta Şirketi",
                  "Diğer")),
    _kolon(_M, "specialty", "Uzmanlık"),
    _kolon(_M, "il", "İl"),
    _kolon(_M, "sektor", "Sektör"),
    _kolon(_M, "email", "E-posta"),
    _kolon(_M, "phone", "Telefon"),
    _kolon(_M, "mobile_phone", "Cep Telefonu"),
    _kolon(_M, "address", "Adres"),
    _kolon(_M, "birth_year", "Doğum Yılı"),
    _kolon(_M, "gender", "Cinsiyet", liste=CINSIYETLER),
    _kolon(_M, "yevmiye_no", "Yevmiye No"),
    _kolon(_M, "noterlik", "Noterlik"),
    _kolon(_M, "vekaletname_tarihi", "Vekaletname Tarihi"),
    _kolon(_M, "vekil_avukatlar", "Vekil Avukatlar"),
    _kolon(_M, "gecerlilik_tarihi", "Geçerlilik Tarihi"),
    _kolon(_M, "vekalet_no", "Vekalet No"),
    _kolon(_M, "buro_vekalet_no", "Büro Vekalet No"),
    _kolon(_M, "active", "Aktif"),
    _kolon(_M, "updated_at", "Güncellenme"),
    _turetilmis("dava_sayisi", "Dava Sayısı", "sayi", _dava_sayisi()),
]

MUVEKKILLER = VeriKaynagi(
    anahtar="muvekkiller",
    etiket="Müvekkiller",
    aciklama="Cari kartlar (silinmişler hariç); dava sayısı silinmemiş davalardan türetilir.",
    from_clause=models.Client.__table__,
    kisitlar=_muvekkil_kisitlari,
    kolonlar=_sozluk(_MUVEKKIL_KOLONLARI),
    varsayilan_kolonlar=("name", "cari_kod", "category", "il", "phone", "email", "dava_sayisi"),
    birincil_anahtar=models.Client.id,
)


# ─── belgeler ────────────────────────────────────────────────────────────────

def _belge_kisitlari(tenant_id: str) -> list[ColumnElement]:
    return [models.CaseDocument.deleted_at.is_(None), *_dava_kisitlari(tenant_id)]


_D = models.CaseDocument
_BELGE_KOLONLARI: list[Kolon] = [
    _kolon(_D, "id", "ID"),
    _kolon(_D, "case_id", "Dava ID"),
    _turetilmis("dava_tracking_no", "Dava Ofis No", "metin", models.Case.tracking_no),
    _turetilmis("dava_subject", "Dava Konusu", "metin", models.Case.subject),
    _kolon(_D, "original_filename", "Orijinal Dosya Adı"),
    _kolon(_D, "stored_filename", "Arşiv Dosya Adı"),
    _kolon(_D, "belge_turu_kodu", "Belge Türü Kodu"),
    _kolon(_D, "belge_turu_adi", "Belge Türü"),
    _kolon(_D, "muvekkil_adi", "Müvekkil"),
    _kolon(_D, "avukat_kodu", "Avukat Kodu"),
    _kolon(_D, "esas_no", "Esas No"),
    _kolon(_D, "ai_summary", "Özet"),
    _kolon(_D, "link_mode", "Bağlantı Modu", liste=BELGE_LINK_MODLARI),
    _kolon(_D, "upload_status", "Yükleme Durumu", liste=BELGE_UPLOAD_DURUMLARI),
    _kolon(_D, "conversion_status", "Dönüşüm Durumu", liste=BELGE_DONUSUM_DURUMLARI),
    _kolon(_D, "sharepoint_url", "SharePoint Bağlantısı"),
    _kolon(_D, "email_sent", "E-posta Gönderildi"),
    _kolon(_D, "uploaded_by", "Yükleyen"),
    _kolon(_D, "uploaded_by_email", "Yükleyen E-posta"),
    _kolon(_D, "uploaded_at", "Yükleme Tarihi"),
]

BELGELER = VeriKaynagi(
    anahtar="belgeler",
    etiket="Belgeler",
    aciklama="Davaya bağlı belgeler (silinmiş belge ve silinmiş dava hariç).",
    from_clause=models.CaseDocument.__table__.join(
        models.Case.__table__, models.CaseDocument.case_id == models.Case.id
    ),
    kisitlar=_belge_kisitlari,
    kolonlar=_sozluk(_BELGE_KOLONLARI),
    varsayilan_kolonlar=("dava_tracking_no", "belge_turu_adi", "original_filename", "muvekkil_adi",
                         "uploaded_by", "uploaded_at"),
    birincil_anahtar=models.CaseDocument.id,
)


# ─── foyler ──────────────────────────────────────────────────────────────────

def _foy_kisitlari(tenant_id: str) -> list[ColumnElement]:
    return list(_dava_kisitlari(tenant_id))


_F = models.CaseFoy
_FOY_KOLONLARI: list[Kolon] = [
    _kolon(_F, "id", "ID"),
    _kolon(_F, "case_id", "Dava ID"),
    _turetilmis("dava_tracking_no", "Dava Ofis No", "metin", models.Case.tracking_no),
    _turetilmis("dava_subject", "Dava Konusu", "metin", models.Case.subject),
    _kolon(_F, "sistem_no", "SistemNo"),
    _kolon(_F, "tku_no", "TKU"),
    _kolon(_F, "hasar_no", "Hasar No"),
    _kolon(_F, "mko_id", "MKO Föy"),
    _kolon(_F, "muvekkil_no", "Müvekkil No"),
    _kolon(_F, "muvekkil_tipi", "Müvekkil Tipi", liste=_adlar(CLIENT_TYPES), secenek_tablosu=models.ClientType),
    _kolon(_F, "hizmet_turu", "Hizmet Türü", liste=_adlar(SERVICE_TYPES), secenek_tablosu=models.ServiceType),
    _kolon(_F, "durum", "Durum", liste=FOY_DURUMLARI),
    _kolon(_F, "kapsam_durumu", "Kapsam Durumu", liste=FOY_KAPSAM_DURUMLARI),
    _kolon(_F, "kapsam_gerekcesi", "Kapsam Gerekçesi"),
    _kolon(_F, "kapsam_tarihi", "Kapsam Tarihi"),
    _kolon(_F, "source", "Kaynak Teslim"),
    _kolon(_F, "created_at", "Oluşturulma"),
    _kolon(_F, "updated_at", "Güncellenme"),
]

FOYLER = VeriKaynagi(
    anahtar="foyler",
    etiket="Föyler",
    aciklama="Teslim föyleri (SistemNo) kart bağıyla; silinmiş davanın föyleri hariç, ham satır katalog dışı.",
    from_clause=models.CaseFoy.__table__.join(models.Case.__table__, models.CaseFoy.case_id == models.Case.id),
    kisitlar=_foy_kisitlari,
    kolonlar=_sozluk(_FOY_KOLONLARI),
    varsayilan_kolonlar=("sistem_no", "tku_no", "dava_tracking_no", "muvekkil_tipi", "hizmet_turu", "durum"),
    birincil_anahtar=models.CaseFoy.id,
)


# ─── Kayıt defteri ───────────────────────────────────────────────────────────

KAYNAKLAR: dict[str, VeriKaynagi] = {
    k.anahtar: k for k in (DAVALAR, MUVEKKILLER, BELGELER, FOYLER)
}

# Kataloga girmesi YASAK kolon adları — kayıt defteri kendi kendini denetler.
YASAK_KOLONLAR = frozenset({"tenant_id", "deleted_at", "deleted_by", "delete_reason", "notes", "ham_veri", "tc_no"})


def _kendini_denetle() -> None:
    for kaynak in KAYNAKLAR.values():
        for kolon in kaynak.kolonlar.values():
            if kolon.anahtar in YASAK_KOLONLAR:
                raise ValueError(f"{kaynak.anahtar}.{kolon.anahtar} kataloga giremez")
            if kolon.tip == "liste" and not kolon.secenekler and kolon.secenek_tablosu is None:
                raise ValueError(f"{kaynak.anahtar}.{kolon.anahtar}: seçeneksiz liste kolon")
            if kolon.turetilmis and (kolon.filtrelenebilir or kolon.siralanabilir):
                raise ValueError(f"{kaynak.anahtar}.{kolon.anahtar}: türetilmiş kolon filtrelenemez")
        for anahtar in kaynak.varsayilan_kolonlar:
            if anahtar not in kaynak.kolonlar:
                raise ValueError(f"{kaynak.anahtar}: varsayılan kolon katalogda yok: {anahtar}")


_kendini_denetle()


def kaynak_bul(anahtar: str) -> Optional[VeriKaynagi]:
    return KAYNAKLAR.get(anahtar)


def secenekleri_getir(kolon: Kolon, db: Optional[Session]) -> list[str]:
    """`liste` kolonun seçenekleri: sabit çekirdek + referans tablosu (aktif) +
    kolondaki DISTINCT değerler; sıra korunur, tekrar yok, boş/None atlanır.
    `db` yoksa yalnız sabit çekirdek döner (asistan prompt'u için yeterli)."""
    if kolon.tip != "liste":
        return []
    gorulen: dict[str, None] = dict.fromkeys(kolon.secenekler)
    if db is not None:
        if kolon.secenek_tablosu is not None:
            T = kolon.secenek_tablosu
            satirlar = db.execute(
                select(T.name).where(T.active.is_(True)).order_by(T.sequence, T.id)
            ).scalars()
            for ad in satirlar:
                if ad:
                    gorulen.setdefault(str(ad))
        if not kolon.turetilmis:
            mevcut = db.execute(
                select(func.distinct(kolon.ifade)).where(kolon.ifade.isnot(None)).order_by(kolon.ifade)
            ).scalars()
            for deger in mevcut:
                if deger not in (None, ""):
                    gorulen.setdefault(str(deger))
    return list(gorulen)


def katalog(db: Optional[Session], limitler: dict[str, int]) -> dict[str, Any]:
    """`GET /api/reports/catalog` gövdesi (plan §2.4)."""
    return {
        "veri_kaynaklari": [
            {
                "anahtar": kaynak.anahtar,
                "etiket": kaynak.etiket,
                "aciklama": kaynak.aciklama,
                "varsayilan_kolonlar": list(kaynak.varsayilan_kolonlar),
                "kolonlar": [
                    {
                        "anahtar": kolon.anahtar,
                        "etiket": kolon.etiket,
                        "tip": kolon.tip,
                        "filtrelenebilir": kolon.filtrelenebilir,
                        "siralanabilir": kolon.siralanabilir,
                        "turetilmis": kolon.turetilmis,
                        "secenekler": secenekleri_getir(kolon, db) if kolon.tip == "liste" else None,
                    }
                    for kolon in kaynak.kolonlar.values()
                ],
            }
            for kaynak in KAYNAKLAR.values()
        ],
        "limitler": dict(limitler),
    }
