"""Bildirim hedefleme: dava → sorumlu avukatın ofis e-postası (G080).

Bildirimler "davanın sorumlu avukatına" gidecek, ama `cases.responsible_lawyer_name`
serbest metindir: aynı kişi "Av. Serap Turgal", "SERAP TURGAL", "Serap Turgal;Tuğçe
Üngör Yanık" ya da avukat kodu ("AGH") olarak yazılmış olabilir. Bu modül o metni
**HukuDok'a giriş yapabilen kişinin ofis e-postasına** çeviren tek çözümleyicidir.

Neden yeni kolon yok
--------------------
Lokal prod-restore kopyasından ölçüm (2026-08-20): `lawyers.gorev='AVUKAT'` olan 7
kaydın 7'sinde de ofis alan adlı e-posta zaten dolu; 69 "DIŞ AVUKAT" ve 2 "DİĞER"
kaydında ise adresler kişisel (gmail/hotmail). Yani giriş yapabilen kişilerin
kimliği hâlihazırda `Lawyer.email`de duruyor — şema değişikliği gereksiz.
`email_recipients` tablosunda ayrıca ofis adresli idari personel var (Murat Arslan
294 davada sorumlu görünüyor ama `lawyers` tablosunda YOK) → ikinci kaynak şart.

Çözümleme sırası
----------------
1. `lawyers` → `gorev='AVUKAT'` **ve** e-posta alan adı allowlist'te
2. `email_recipients` → alan adı allowlist'te
3. Çözülemedi → hedefsiz sayacına düşer (`unresolved_targets`)

Allowlist (`NOTIFICATION_DOMAINS`, varsayılan `hanyaloglu-acar.av.tr`) yapısal bir
kapıdır: dış avukatların kişisel adresleri hiçbir eşleşme yolundan dönemez. Kural
alan adı üzerinedir — tek tek adres kara listesi tutulmaz.

Sözleşme: bu modül DB'ye **YAZMAZ**, yalnız okur; boş liste geçerli bir sonuçtur
(hedef yok). İsim eşleştirme kuralları `managers.lawyer_resolver` ile ORTAKTIR —
normalize ediciler oradan alınır, kopyalanmaz (TR katlama + ünvan atma + çoklu
kişi ayracı tek yerde tanımlı kalsın).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional, cast

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
# Bilinçli olarak lawyer_resolver'ın normalize edicileri kullanılır: "Av." öneki,
# TR karakter katlaması ve ";"/","/"ve" ayracı davranışı iki modülde AYNI kalmalı.
from managers.lawyer_resolver import _name_tokens, _norm_name, _split_persons

# `lawyers.gorev` değeri — yalnız bu görevdekiler HukuDok'a giriş yapar
GOREV_AVUKAT = "AVUKAT"

# Allowlist varsayılanı: ofis alan adı. Env ile genişletilir (bkz. .env.example).
DEFAULT_NOTIFICATION_DOMAINS: tuple[str, ...] = ("hanyaloglu-acar.av.tr",)

KAYNAK_AVUKAT = "lawyers"
KAYNAK_ALICI = "email_recipients"


def notification_domains() -> tuple[str, ...]:
    """Bildirim gönderilebilecek e-posta alan adları (küçük harf).

    `NOTIFICATION_DOMAINS` env'i virgül/noktalı virgülle ayrılır; boş ya da
    tanımsızsa varsayılan ofis alan adına düşülür. Her çağrıda okunur —
    ayar süreç ömrüne dondurulmaz (testler ve env değişikliği kolay olsun).
    """
    raw = os.getenv("NOTIFICATION_DOMAINS", "") or ""
    parcalar = [p.strip().lower().lstrip("@") for p in raw.replace(";", ",").split(",")]
    domains = tuple(p for p in parcalar if p)
    return domains or DEFAULT_NOTIFICATION_DOMAINS


def normalize_email(raw: Optional[str]) -> Optional[str]:
    """E-postayı küçük harfe indirger; biçimi bozuksa None döner."""
    if not raw:
        return None
    value = str(raw).strip().lower()
    if value.count("@") != 1:
        return None
    local, _, domain = value.partition("@")
    if not local or not domain or "." not in domain:
        return None
    return value


def is_allowed_email(email: Optional[str], domains: Optional[tuple[str, ...]] = None) -> bool:
    """Adres allowlist'teki bir alan adına mı ait? (alt alan adı sayılmaz)"""
    normalized = normalize_email(email)
    if not normalized:
        return False
    domain = normalized.split("@", 1)[1]
    return domain in (domains if domains is not None else notification_domains())


@dataclass(frozen=True)
class _Aday:
    """Eşleştirme havuzundaki tek hedef (avukat ya da e-posta alıcısı)."""
    email: str
    tokens: frozenset
    code: str          # normalize edilmiş avukat kodu ("agh"), yoksa ""
    surname: str       # normalize edilmiş soyad (tek-token eşleşme için)
    source: str


def _aday(name: Optional[str], email: str, code: Optional[str], source: str) -> Optional[_Aday]:
    tokens = _name_tokens(name or "")
    code_norm = _norm_name(code or "")
    if not tokens and not code_norm:
        return None
    ad_tokens = _norm_name(name or "").split()
    return _Aday(
        email=email,
        tokens=frozenset(tokens),
        code=code_norm,
        surname=ad_tokens[-1] if ad_tokens else "",
        source=source,
    )


def _build_pool(db: Session, domains: tuple[str, ...]) -> tuple[list[_Aday], dict[str, int]]:
    """Allowlist'ten geçen hedef havuzu + soyad sayaçları.

    Sıra çözümleme sırasıdır: önce avukatlar, sonra e-posta alıcıları.
    Sayaçlar tek-token ("Hanyaloğlu") kayıtların yalnız benzersiz soyadla
    eşleşmesi için kullanılır.
    """
    adaylar: list[_Aday] = []

    lawyers = (
        db.query(models.Lawyer)
        .filter(models.Lawyer.active.isnot(False))
        .order_by(models.Lawyer.sequence.asc(), models.Lawyer.id.asc())
        .all()
    )
    for lw in lawyers:
        # Görev karşılaştırması ham metin üzerinde: _norm_name "avukat"ı ünvan
        # sayıp atardı ("AVUKAT" → ""), bu alanda ünvan değil ROL bilgisi var.
        if (lw.gorev or "").strip().upper() != GOREV_AVUKAT:
            continue
        # cast: eski stil Column() modellerinde mypy instance alanını Column[str]
        # görür (Mapped[] geçişine kadar; upload_queue/conversion_retry ile aynı köprü).
        email = normalize_email(cast(Optional[str], lw.email))
        if not email or not is_allowed_email(email, domains):
            continue
        aday = _aday(cast(Optional[str], lw.name), email, cast(Optional[str], lw.code), KAYNAK_AVUKAT)
        if aday:
            adaylar.append(aday)

    recipients = (
        db.query(models.EmailRecipient)
        .filter(models.EmailRecipient.active.isnot(False))
        .order_by(models.EmailRecipient.sequence.asc(), models.EmailRecipient.id.asc())
        .all()
    )
    for rec in recipients:
        email = normalize_email(cast(Optional[str], rec.email))
        if not email or not is_allowed_email(email, domains):
            continue
        aday = _aday(cast(Optional[str], rec.name), email, None, KAYNAK_ALICI)
        if aday:
            adaylar.append(aday)

    surname_counts: dict[str, int] = {}
    for aday in adaylar:
        if aday.surname:
            surname_counts[aday.surname] = surname_counts.get(aday.surname, 0) + 1
    return adaylar, surname_counts


def _match_person(part: str, adaylar: list[_Aday], surname_counts: dict[str, int]) -> Optional[_Aday]:
    """Tek kişilik ham metni havuzdaki bir adaya çözer (yoksa None).

    Üç geçiş, güçlüden zayıfa — havuz sırası (avukatlar önce) her geçişte korunur:
      1. avukat kodu birebir ("AGH")
      2. en az iki ortak ad token'ı ("Tuğçe Üngör Yanık" ↔ "TUGCE UNGOR")
      3. yalnız soyad yazılmışsa ve o soyad havuzda benzersizse
    Geçişleri ayırmak, zayıf bir eşleşmenin (soyad) listede önce duruyor diye
    güçlü bir eşleşmeyi (kod/iki token) gölgelemesini engeller.
    """
    ptoks = _name_tokens(part)
    if not ptoks:
        return None
    for aday in adaylar:
        if aday.code and aday.code in ptoks:
            return aday
    for aday in adaylar:
        if len(ptoks & aday.tokens) >= 2:
            return aday
    for aday in adaylar:
        if aday.surname and surname_counts.get(aday.surname) == 1 and ptoks == {aday.surname}:
            return aday
    return None


def resolve_recipients(db: Session, raw_value: Optional[str]) -> list[str]:
    """Serbest sorumlu-avukat metnini e-posta listesine çevirir.

    Çoklu sorumlu (";", ",", "/", "&", " ve ") ayrı alıcılara açılır; sıra ve
    tekillik korunur. Çözülemeyen parça sessizce atlanır — boş liste geçerli
    sonuçtur (hedef yok).
    """
    if not raw_value or not str(raw_value).strip():
        return []
    domains = notification_domains()
    adaylar, surname_counts = _build_pool(db, domains)
    if not adaylar:
        return []
    return _resolve_with_pool(raw_value, adaylar, surname_counts)


def _resolve_with_pool(raw_value: str, adaylar: list[_Aday], surname_counts: dict[str, int]) -> list[str]:
    out: list[str] = []
    for part in _split_persons(raw_value):
        aday = _match_person(part, adaylar, surname_counts)
        if aday and aday.email not in out:
            out.append(aday.email)
    return out


def resolve_case_recipients(db: Session, case: Any) -> list[str]:
    """Davanın bildirim alıcıları: sorumlu avukat(lar)ın ofis e-postaları.

    Küçük harfe normalize edilmiş, tekilleştirilmiş liste döner. Allowlist dışı
    hiçbir adres dönmez. Boş liste = hedef yok (`unresolved_targets` bunları sayar).
    """
    if case is None:
        return []
    return resolve_recipients(db, getattr(case, "responsible_lawyer_name", None))


def unresolved_targets(db: Session) -> list[dict[str, Any]]:
    """Hedefe çözülemeyen sorumlu adları ve dava sayıları.

    İdari panelin "hedefsiz" göstergesi bunu tüketir. Aynı kişinin farklı
    yazımları ("ARSIV DOSYA YONETICISI" / "Arşiv Dosya Yöneticisi") tek satırda
    toplanır; etiket olarak ada göre sıralı sorgunun ilk ham yazımı gösterilir
    (deterministik olsun diye — hangi yazımın "doğru" olduğunu servis bilemez).

    Dönen: `[{"name": str, "case_count": int}, …]` — dava sayısına göre azalan.
    """
    domains = notification_domains()
    adaylar, surname_counts = _build_pool(db, domains)

    rows = (
        db.query(
            models.Case.responsible_lawyer_name.label("ad"),
            func.count(models.Case.id).label("adet"),
        )
        .filter(models.Case.responsible_lawyer_name.isnot(None))
        .filter(models.Case.deleted_at.is_(None))
        .group_by(models.Case.responsible_lawyer_name)
        .order_by(models.Case.responsible_lawyer_name.asc())
        .all()
    )

    gruplar: dict[str, dict[str, Any]] = {}
    for ad, adet in rows:
        for part in _split_persons(ad or ""):
            etiket = part.strip()
            anahtar = _norm_name(etiket)
            if not anahtar:
                continue
            if _match_person(etiket, adaylar, surname_counts):
                continue
            grup = gruplar.setdefault(anahtar, {"name": etiket, "case_count": 0})
            grup["case_count"] += int(adet or 0)

    return sorted(gruplar.values(), key=lambda g: (-g["case_count"], g["name"]))
