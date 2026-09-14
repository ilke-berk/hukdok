"""Modüller arası paylaşılan sabitler.

Duruşma tarihi zinciri (analyzer → prompts → document_pipeline → frontend)
aynı belge türü filtresini kullanır; liste tek yerden yönetilir ki yeni bir
tür eklenince üç kopyadan biri unutulmasın.
"""
from typing import Optional

# Sonraki duruşma tarihi taşıyabilen belge türü kod parçaları.
# Kodlar '_' ile pad'li gelebilir (örn. "TEBLIGAT______"); contains kontrolü
# yapıldığı için padding sorun olmaz. "TEBLIG" hem TEBLIGAT hem TEBLIG'i kapsar.
HEARING_DOCTYPE_KEYWORDS = ("DURUSMA", "ZABIT", "TUTANAK", "TENSIP", "TEBLIG")


def is_hearing_doctype(code: Optional[str]) -> bool:
    """Belge türü kodu duruşma tarihi çıkarımı yapılacak türlerden mi?"""
    c = (code or "").upper()
    return any(kw in c for kw in HEARING_DOCTYPE_KEYWORDS)


# ─── Dava durumu üçlüsü (kullanıcı kararı 12.09.2026) ────────────────────────
# `cases.status` yalnız üç değer alır: DERDEST (aktif dava), DANIŞ (danışma
# dosyası), MAHZEN (arşiv). Temyizdeki/istinaftaki dava da DERDEST'tir — yargı
# aşaması `cases.case_stage`'in işidir (DERDEST | KARAR | ISTINAF | TEMYIZ |
# KARAR_DUZELTME | KESINLESME | INFAZ | KAPALI). Eski kod belge türünden status'a
# TEMYIZ/KARAR/INFAZ/KAPALI yazıyordu; panel ve rapor kataloğu da bu değerleri
# listeliyordu. Migrasyon 50 mevcut kayıtları üçlüye çeker (aşamayı korur), bu
# modül yazma yollarının (panel, takip, belge işleme) ortak kapısıdır.
CASE_STATUSES: tuple = ("DERDEST", "DANIŞ", "MAHZEN")

# Eski durum değeri → (üçlü durum, korunacak aşama). KAPALI arşive, kalanlar
# derdeste gider; aşama kolonu boşsa eski değer oraya taşınır (bilgi kaybolmaz).
LEGACY_CASE_STATUS: dict = {
    "KARAR": ("DERDEST", "KARAR"),
    "ISTINAF": ("DERDEST", "ISTINAF"),
    "TEMYIZ": ("DERDEST", "TEMYIZ"),
    "KARAR_DUZELTME": ("DERDEST", "KARAR_DUZELTME"),
    "KESINLESME": ("DERDEST", "KESINLESME"),
    "INFAZ": ("DERDEST", "INFAZ"),
    "KAPALI": ("MAHZEN", "KAPALI"),
}

_STATUS_ALIASES = {"DANIS": "DANIŞ", "DANİŞ": "DANIŞ", "AKTIF": "DERDEST", "ARSIV": "MAHZEN", "ARŞIV": "MAHZEN"}


def normalize_case_status(value: Optional[str]) -> "tuple[Optional[str], Optional[str]]":
    """Gelen durum değerini üçlüye indirger: (status, aşama | None).

    Boş → (None, None) (çağıran dokunmaz). Üçlüdeki değer (büyük/küçük harf,
    ASCII DANIS) olduğu gibi; eski değer (TEMYIZ, KAPALI, ...) `LEGACY_CASE_STATUS`
    ile üçlüye çevrilir ve korunacak aşama ikinci elemanda döner. Tanınmayan
    metin DERDEST sayılmaz — olduğu gibi döner ki panel serbest yazımı kaybetmesin;
    kapalı liste kapısı (`CASE_STATUSES`) çağıranda uygulanır.
    """
    if value is None:
        return None, None
    ham = str(value).strip()
    if not ham:
        return None, None
    key = ham.upper().replace("İ", "I").replace("ı", "I")
    key = _STATUS_ALIASES.get(key, key)
    if key == "DANIS":
        key = "DANIŞ"
    if key in CASE_STATUSES:
        return key, None
    if key in LEGACY_CASE_STATUS:
        return LEGACY_CASE_STATUS[key]
    return ham, None


class InvalidCaseStatusError(ValueError):
    """Dava durumu üçlü (`CASE_STATUSES`) dışında — istemci hatası (G196).

    `ValueError` ALT SINIFI (`stage_decisions.InvalidDecisionStatusError` deseni):
    ayrı tip olmasının tek nedeni HTTP eşlemesi — `api.py` bunu 400'e çevirir;
    yazma yollarının genel `except Exception` dalı hatayı ERROR + 500/404'e
    yutmaz (log sözleşmesi: istemci hatası nihai sistem başarısızlığı değil).
    """


def validated_case_status(value: Optional[str]) -> "tuple[Optional[str], Optional[str]]":
    """Yazma yollarının üçlü kapısı (G196): `normalize_case_status` + kapalı liste.

    Dönüş `normalize_case_status` ile aynıdır — boş → (None, None), eski değer
    (TEMYIZ, KAPALI, ...) → (üçlü, korunacak aşama). Normalize sonrası değer
    `CASE_STATUSES` dışındaysa `InvalidCaseStatusError` yükselir; çağıran bunu
    veritabanına dokunmadan ÖNCE çağırır ki G195 CHECK kısıtına (`ck_cases_status_uclu`)
    hiç ulaşılmasın. `normalize_case_status`'ın "tanınmayanı olduğu gibi döndür"
    sözleşmesi bilinçli korunur (okuma/rapor tarafı kullanır).
    """
    status, stage = normalize_case_status(value)
    if status is not None and status not in CASE_STATUSES:
        raise InvalidCaseStatusError(
            f"Geçersiz dava durumu: {status!r} — durum yalnız {', '.join(CASE_STATUSES)} "
            f"olabilir (temyiz, istinaf, karar gibi yargı aşamaları durum değil aşamadır)"
        )
    return status, stage
