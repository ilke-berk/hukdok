"""Gece tarayıcısı: yaklaşan kanuni süreler ve duruşmalar (G085).

Her gece 06:00 TR'de (APScheduler, `api.py` lifespan — **yalnız lider worker**,
Faz 3-E kararı) iki kaynağı tarar ve sorumlu avukata uygulama içi bildirim yazar:

* `case_stage_decisions.teblig_tarihi` → kanuni son gün G084 motoruyla hesaplanır
  (`services.legal_deadlines.deadline_for`), eşikler **T-15 / T-7 / T-3 / T-1**;
* `hearing_dates.hearing_date` → eşikler **T-3 / T-1**.

Kaynak seçimi ÖLÇÜMLEDİR, tahmin değil (lokal prod-restore, 2026-08-20):
`cases.karar_teblig_tarihi` 0 dolu — oradan tarama yapılsa hiçbir şey bulunmazdı.
Gerçek kaynak `case_stage_decisions.teblig_tarihi`: 4.971 satırın 750'si dolu ve
hepsi YEREL aşamada. Bu yüzden panel ilk gün onlarca değil **bir avuç** uyarı
gösterir; bu bir kusur değil, veri durumudur.

İdempotency (`dedupe_key`)
--------------------------
Anahtar deseni `deadline:{stage_decision_id}:{esik}` ve `hearing:{hearing_id}:{esik}`
— sonuna **alıcı e-postası eklenir**. Sebep G082'de ödenmiş bir derstir: `dedupe_key`
GLOBAL tekildir (`uq_notifications_dedupe`) ve bir bildirim satırı TEK
`recipient_email` taşır; çıplak anahtar, iki sorumlusu olan davada ikinci avukatın
bildirimini sessizce yutardı. Tek alıcılı davada (ölçülen normal hâl) davranış
tanımdakiyle aynıdır: ertesi gece aynı satır için İKİNCİ bildirim üretilmez.

Eşik seçimi: kalan güne **uyan EN DAR eşik** kullanılır (kalan 10 gün → T-15
anahtarı, kalan 5 gün → T-7). Böylece tarayıcı ilk gördüğü satır için dört
bildirimi birden açmaz; süre yaklaştıkça yeni anahtar (T-7 → T-3 → T-1) devreye
girer ve okunmuş uyarı yeniden okunmamışa DÖNMEZ (dedupe mevcut satırı güncellemez).

Geçmiş tarih: son günü/duruşması geçmiş kayıt için bildirim ÜRETİLMEZ — sistem
geçmiş bir süreyi "yaklaşıyor" diye duyuramaz.

Log sözleşmesi
--------------
Satır düzeyi başarısızlık **WARNING** (tur devam eder), turun tamamı için en fazla
**TEK ERROR**: ya tarama sorgusu düştü ya da tur sonunda işlenemeyen satır kaldı.
Tur her hâlükârda biter, ertesi gece kaldığı yerden devam eder — bildirim üretimi
idempotent olduğu için kaçırılan gece veri kaybı değildir.

Boot telafisi (G097)
--------------------
Cron job'ının `misfire_grace_time` penceresi bir saattir: lider 06:00-07:00 TR
arasında kapalıysa o gün tarama HİÇ koşmaz. Bu yüzden lider worker boot'unda
(`api.py` lifespan, `is_leader` bloğu) `boot_catch_up_scan` arka plan thread'inde
**bir kez** `scan_deadlines` çağırır — günlük raporun `catch_up_missed_reports`
deseni. Dedupe anahtarı eşik+alıcı bazlı olduğundan aynı gün cron + telafi
birlikte koşsa da satır ikilenmez. Telafi kaçırılan günün eşiğini değil,
**bugünün kalan gününe uyan en dar eşiği** üretir (T-7 günü kaçtıysa T-5'te
yine `:7:` anahtarı). **Kaçan T-1 telafi EDİLMEZ**: son gün geçtiyse kalan<0 →
`esik_sec` None — sistem geçmiş bir süreyi "yaklaşıyor" diye duyuramaz; bu
bilinçli kabuldür. Telafi hatası yutulur ve TEK WARNING loglanır (deneme
düzeyi — nihai iş gece cron'undur).

Retention (G097)
----------------
Tur sonunda aynı job içinde (yeni job/scheduler YOK, 3-E devri)
`services.notifications.purge_old_notifications` koşar: okunmuş ve
`NOTIFICATION_RETENTION_DAYS` (varsayılan 90) günden eski satırlar silinir,
okunmamış satır ASLA silinmez; okunmamış-eski sayısı `okunmamis_eski` sayacı
olarak loglanır. Silinen sayı dönüş sözlüğünde `purged` anahtarıdır.

Kapsam dışı (bilinçli): e-posta gönderimi YOK (kanal yalnız uygulama içi, kullanıcı
kararı 2026-08-20); `cases` üzerindeki tek-slot karar alanları taranmaz (tarihçe
tablosu tek gerçek kaynaktır, G062).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional, Sequence, cast
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from database import SessionLocal
import models
from services.legal_deadlines import Deadline, deadline_for
from services.notification_targeting import resolve_case_recipients, resolve_recipients
# Dava künyesi ("ofis no · esas no · mahkeme") G082 ile AYNI biçimde yazılır;
# ikinci bir kopya tutulmaz (notification_targeting'in lawyer_resolver'dan
# normalize edici alması ile aynı gerekçe: biçim iki yerde ayrışmasın).
from services.notifications import (
    _case_label,
    count_unread_stale,
    create_notification,
    purge_old_notifications,
)

logger = logging.getLogger(__name__)

#: Zamanlayıcı Türkiye saatiyle koşar; "bugün" de TR gününe göre belirlenir
#: (sunucu UTC'de olduğunda 06:00 TR = 03:00 UTC — aynı takvim günü, ama
#: elle/erken çağrıda gün kaymasın diye açıkça dönüştürülür).
TR_TZ = "Europe/Istanbul"

#: Bildirim tür etiketleri (frontend filtresi bunları tüketir — G086).
SURE_TYPE = "sure_yaklasti"
DURUSMA_TYPE = "durusma_yaklasti"

#: Eşikler — görev tanımı: süreler T-15/7/3/1, duruşmalar T-3/1.
SURE_ESIKLERI: tuple[int, ...] = (15, 7, 3, 1)
DURUSMA_ESIKLERI: tuple[int, ...] = (3, 1)

#: Sorgu penceresi: tebliğ tarihi bundan daha eski satırın son günü çoktan
#: geçmiştir. En uzun zincir 2 hafta + adli tatil uzaması (20 Temmuz tebliğ →
#: 7 Eylül son gün ≈ 50 gün) + tatil kaydırmaları; 120 gün rahat bir tavandır.
GERIYE_TARAMA_GUN = 120

#: Kullanıcı şartı: her uyarı bu şerhi taşır.
SERH = "Bu bilgilendirmedir, süre takibi yerine geçmez."

#: G084 takvimi doğrulanmamış yıla düşen son günü kaydırmaz; uyarı bunu SÖYLER.
TAKVIM_UYARISI = (
    "DİKKAT: son günün yılı için resmî tatil takvimi doğrulanmadı — "
    "hafta sonu/resmî tatil kaydırması UYGULANMADI, son gün elle teyit edilmeli."
)

#: Aşama kodunun okunur karşılığı. Kodun kendisi de gövdeye yazılır (etiket
#: değişse bile kayıt hangi satırdan doğduğunu söylesin).
_ASAMA_ETIKET: dict[str, str] = {
    "YEREL": "Yerel mahkeme",
    "ISTINAF": "İstinaf",
    "TEMYIZ": "Temyiz",
    "KARAR_DUZELTME": "Karar düzeltme",
}

#: Sayaç anahtarları — çağıran (smoke/test) tek sözlükten okur.
_SAYAC_ANAHTARLARI = (
    "sure_bildirim",
    "durusma_bildirim",
    "hedefsiz",
    "kuralsiz",
    "atlanan",
    "hata",
    "purged",          # retention ile silinen okunmuş-eski satır (G097)
    "okunmamis_eski",  # okunmamış ama retention sınırını aşmış satır — SİLİNMEZ, ölçülür
)


def bugun_tr() -> date:
    """Türkiye saatiyle bugünün tarihi."""
    return datetime.now(ZoneInfo(TR_TZ)).date()


def esik_sec(kalan_gun: int, esikler: Sequence[int]) -> Optional[int]:
    """Kalan güne uyan EN DAR eşik (yoksa None).

    `None` iki durumda döner: gün geçmişte (kalan < 0 → bildirim yok) ya da en
    geniş eşikten daha uzak (henüz erken).
    """
    if kalan_gun < 0:
        return None
    uygun = [e for e in esikler if kalan_gun <= e]
    return min(uygun) if uygun else None


def deadline_dedupe_key(stage_decision_id: int, esik: int, recipient_email: str) -> str:
    """Süre bildiriminin idempotency anahtarı (alıcı dâhil — modül şerhi)."""
    return f"deadline:{stage_decision_id}:{esik}:{_norm_mail(recipient_email)}"


def hearing_dedupe_key(hearing_id: int, esik: int, recipient_email: str) -> str:
    """Duruşma bildiriminin idempotency anahtarı (alıcı dâhil — modül şerhi)."""
    return f"hearing:{hearing_id}:{esik}:{_norm_mail(recipient_email)}"


def _norm_mail(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _tarih(gun: Optional[date]) -> str:
    """Gövdede kullanılan tarih biçimi (gg.aa.yyyy)."""
    return gun.strftime("%d.%m.%Y") if gun else "-"


def _kalan_metni(kalan: int) -> str:
    return "son gün bugün" if kalan == 0 else f"{kalan} gün kaldı"


def _severity(kalan: int) -> str:
    """Üç günden yakını uyarıdır; uzağı bilgidir."""
    return "warning" if kalan <= 3 else "info"


@dataclass(frozen=True)
class _Aday:
    """Bildirime dönüşmeye hazır tek kayıt (okuma fazının çıktısı)."""

    type: str
    dedupe_key: str
    recipient_email: str
    title: str
    body: str
    severity: str
    due_date: date
    case_id: Optional[int]
    tenant_id: Optional[str]
    sayac: str  # hangi sayacı artıracağı ("sure_bildirim" | "durusma_bildirim")


# ─── okuma fazı: süreler ─────────────────────────────────────────────────────

def _sure_govdesi(case: Any, karar: Any, dl: Deadline, kalan: int) -> str:
    """Süre bildiriminin gövdesi — dayanağı taşımayan uyarı YAZILMAZ."""
    stage = str(cast(Optional[str], karar.stage) or "")
    etiket = _ASAMA_ETIKET.get(stage, stage or "Aşama bilinmiyor")
    satirlar = []
    kunye = _case_label(case)
    if kunye:
        satirlar.append(f"Dava: {kunye}")
    satirlar.append(f"Aşama: {etiket} ({stage}, {cast(Optional[int], karar.sira_no) or 1}. karar)")
    satirlar.append(f"Tebliğ tarihi: {_tarih(dl.teblig_tarihi)}")
    satirlar.append(f"Kural: {dl.kural_adi} — {dl.dayanak}")
    satirlar.append(f"Son gün: {_tarih(dl.son_gun)} ({_kalan_metni(kalan)})")
    for kaydirma in dl.kaydirmalar:
        satirlar.append(f"Kaydırma: {kaydirma}")
    if not dl.takvim_dogrulandi:
        satirlar.append(TAKVIM_UYARISI)
    satirlar.append(SERH)
    return "\n".join(satirlar)


def _sure_adaylari(db: Session, gun: date, sayaclar: dict[str, int]) -> list[_Aday]:
    """Tebliğ tarihi olan aşama kararlarından yaklaşan süreleri çıkarır."""
    rows = (
        db.query(models.CaseStageDecision, models.Case)
        .join(models.Case, models.Case.id == models.CaseStageDecision.case_id)
        .filter(models.CaseStageDecision.teblig_tarihi.isnot(None))
        .filter(models.CaseStageDecision.teblig_tarihi >= gun - timedelta(days=GERIYE_TARAMA_GUN))
        .filter(models.Case.deleted_at.is_(None))
        .order_by(models.CaseStageDecision.id)
        .all()
    )

    adaylar: list[_Aday] = []
    for karar, case in rows:
        karar_id = cast(int, karar.id)
        try:
            dl = deadline_for(
                cast(Optional[str], karar.stage),
                cast(Optional[date], karar.teblig_tarihi),
            )
            if dl is None:
                # TEMYIZ / KARAR_DUZELTME: tebliğden işleyen kanuni süre YOK.
                sayaclar["kuralsiz"] += 1
                continue

            kalan = (dl.son_gun - gun).days
            esik = esik_sec(kalan, SURE_ESIKLERI)
            if esik is None:
                sayaclar["atlanan"] += 1
                continue

            alicilar = resolve_case_recipients(db, case)
            if not alicilar:
                sayaclar["hedefsiz"] += 1
                logger.warning(
                    "Süre bildirimi hedefsiz: sorumlu avukat çözülemedi "
                    "(stage_decision=%s, case=%s, sorumlu=%r)",
                    karar_id,
                    cast(Optional[int], case.id),
                    cast(Optional[str], case.responsible_lawyer_name),
                )
                continue

            govde = _sure_govdesi(case, karar, dl, kalan)
            baslik = f"Süre yaklaşıyor: {dl.kural_adi} — {_kalan_metni(kalan)}"
            for email in alicilar:
                adaylar.append(
                    _Aday(
                        type=SURE_TYPE,
                        dedupe_key=deadline_dedupe_key(karar_id, esik, email),
                        recipient_email=email,
                        title=baslik,
                        body=govde,
                        severity=_severity(kalan),
                        due_date=dl.son_gun,
                        case_id=cast(Optional[int], case.id),
                        tenant_id=cast(Optional[str], case.tenant_id),
                        sayac="sure_bildirim",
                    )
                )
        except Exception as e:
            sayaclar["hata"] += 1
            logger.warning("Süre adayı hesaplanamadı (stage_decision=%s): %s", karar_id, e)
    return adaylar


# ─── okuma fazı: duruşmalar ──────────────────────────────────────────────────

def _durusma_govdesi(case: Any, durusma: Any, kalan: int) -> str:
    satirlar = []
    kunye = _case_label(case)
    if kunye:
        satirlar.append(f"Dava: {kunye}")
    saat = (cast(Optional[str], durusma.hearing_time) or "").strip()
    gun_metni = _tarih(cast(Optional[date], durusma.hearing_date))
    satirlar.append(
        f"Duruşma: {gun_metni}{(' ' + saat) if saat else ''} ({_kalan_metni(kalan)})"
    )
    kaynak = (cast(Optional[str], durusma.extracted_from_doc) or "").strip()
    if kaynak:
        satirlar.append(f"Kaynak belge: {kaynak}")
    not_metni = (cast(Optional[str], durusma.note) or "").strip()
    if not_metni:
        satirlar.append(f"Not: {not_metni}")
    satirlar.append(SERH)
    return "\n".join(satirlar)


def _durusma_adaylari(db: Session, gun: date, sayaclar: dict[str, int]) -> list[_Aday]:
    """Gelecek duruşmalardan yaklaşanları çıkarır.

    Üst sınır SQL'de (G097): en geniş eşik 3 gün → daha uzak duruşma zaten
    `esik_sec` ile elenirdi; tüm gelecek takvimi çekip Python'da elemek tablo
    büyüdükçe boşuna I/O olurdu. `atlanan` sayacının anlamı korunur ("eşik
    dışı gelecek duruşma"): sınır dışı kalanlar satır çekilmeden COUNT ile
    sayılır — sayaç sözleşmesi (G085 testleri) değişmez, veri transferi düşer.
    """
    ust_sinir = gun + timedelta(days=max(DURUSMA_ESIKLERI))
    temel = (
        db.query(models.HearingDate, models.Case)
        .join(models.Case, models.Case.id == models.HearingDate.case_id)
        .filter(models.HearingDate.hearing_date >= gun)
        .filter(models.Case.deleted_at.is_(None))
    )
    sayaclar["atlanan"] += int(
        temel.filter(models.HearingDate.hearing_date > ust_sinir).count()
    )
    rows = (
        temel.filter(models.HearingDate.hearing_date <= ust_sinir)
        .order_by(models.HearingDate.id)
        .all()
    )

    adaylar: list[_Aday] = []
    for durusma, case in rows:
        durusma_id = cast(int, durusma.id)
        try:
            hearing_date = cast(Optional[date], durusma.hearing_date)
            if hearing_date is None:
                sayaclar["atlanan"] += 1
                continue
            kalan = (hearing_date - gun).days
            esik = esik_sec(kalan, DURUSMA_ESIKLERI)
            if esik is None:
                sayaclar["atlanan"] += 1
                continue

            # Alıcı sırası: davanın sorumlusu (diğer tüm bildirimlerle aynı
            # kural), o çözülemezse zaptan çıkarılan duruşma avukatı. İkisi de
            # G080 çözümleyicisinden geçer — allowlist dışı adres dönemez.
            alicilar = resolve_case_recipients(db, case)
            if not alicilar:
                alicilar = resolve_recipients(db, cast(Optional[str], durusma.lawyer_name))
            if not alicilar:
                sayaclar["hedefsiz"] += 1
                logger.warning(
                    "Duruşma bildirimi hedefsiz: sorumlu avukat çözülemedi "
                    "(hearing=%s, case=%s, sorumlu=%r, zapt=%r)",
                    durusma_id,
                    cast(Optional[int], case.id),
                    cast(Optional[str], case.responsible_lawyer_name),
                    cast(Optional[str], durusma.lawyer_name),
                )
                continue

            govde = _durusma_govdesi(case, durusma, kalan)
            baslik = f"Duruşma yaklaşıyor: {_tarih(hearing_date)} — {_kalan_metni(kalan)}"
            for email in alicilar:
                adaylar.append(
                    _Aday(
                        type=DURUSMA_TYPE,
                        dedupe_key=hearing_dedupe_key(durusma_id, esik, email),
                        recipient_email=email,
                        title=baslik,
                        body=govde,
                        severity=_severity(kalan),
                        due_date=hearing_date,
                        case_id=cast(Optional[int], case.id),
                        tenant_id=cast(Optional[str], case.tenant_id),
                        sayac="durusma_bildirim",
                    )
                )
        except Exception as e:
            sayaclar["hata"] += 1
            logger.warning("Duruşma adayı hesaplanamadı (hearing=%s): %s", durusma_id, e)
    return adaylar


# ─── yazma fazı + gece job'ı ─────────────────────────────────────────────────

def _yaz(db: Session, adaylar: list[_Aday], sayaclar: dict[str, int]) -> None:
    """Adayları bildirime çevirir; satır düzeyi hata turu DURDURMAZ."""
    for aday in adaylar:
        try:
            create_notification(
                db,
                recipient_email=aday.recipient_email,
                type=aday.type,
                title=aday.title,
                body=aday.body,
                severity=aday.severity,
                tenant_id=aday.tenant_id,
                case_id=aday.case_id,
                due_date=aday.due_date,
                dedupe_key=aday.dedupe_key,
            )
            sayaclar[aday.sayac] += 1
        except Exception as e:
            sayaclar["hata"] += 1
            logger.warning("Bildirim yazılamadı (dedupe_key=%s): %s", aday.dedupe_key, e)


def scan_deadlines(bugun: Optional[date] = None, db: Optional[Session] = None) -> dict[str, int]:
    """Gece taraması: yaklaşan süre ve duruşmalar için bildirim üretir.

    APScheduler bunu argümansız çağırır (06:00 TR, yalnız lider worker). `bugun`
    ve `db` yalnız test/elle koşu içindir. Dönüş sayaçlarıdır; **hiçbir istisna
    yukarı taşmaz** — scheduler'ı öldürmemeli.

    Aynı gece iki kez koşturmak satır İKİLEMEZ (dedupe); ertesi gece de aynı
    kayıt için ikinci bildirim yazılmaz — eşik değişene kadar anahtar aynıdır.
    """
    sayaclar: dict[str, int] = {anahtar: 0 for anahtar in _SAYAC_ANAHTARLARI}
    session = db if db is not None else SessionLocal()
    try:
        gun = bugun or bugun_tr()
        try:
            adaylar = _sure_adaylari(session, gun, sayaclar)
            adaylar.extend(_durusma_adaylari(session, gun, sayaclar))
            _yaz(session, adaylar, sayaclar)
        except Exception as e:
            # Tarama sorgusu düştü: tur yarıda kaldı → NİHAİ başarısızlık, TEK ERROR.
            logger.error("Süre tarayıcısı turu yarıda kaldı: %s", e)
            return sayaclar

        if sayaclar["hata"]:
            # Satır düzeyi başarısızlıklar zaten WARNING'e düştü; tur sonunda
            # tek ERROR özet: alarm sayacı görsün ama ERROR satırı çoğalmasın.
            logger.error(
                "Süre tarayıcısı turunda %s kayıt işlenemedi (ayrıntı WARNING satırlarında); "
                "tur tamamlandı, ertesi gece yeniden denenecek.",
                sayaclar["hata"],
            )

        # Retention (G097): aynı job, tur sonunda. Başarısızlığı turu
        # başarısız yapmaz — bildirimler yazıldı; temizlik ertesi gece
        # yeniden denenir (WARNING, deneme düzeyi).
        try:
            sayaclar["purged"] = purge_old_notifications(bugun=gun, db=session)
            sayaclar["okunmamis_eski"] = count_unread_stale(bugun=gun, db=session)
        except Exception as e:
            logger.warning("Bildirim retention temizliği yapılamadı: %s", e)
        if sayaclar["okunmamis_eski"]:
            logger.info(
                "Okunmamış ve retention sınırını aşmış bildirim: %s (silinmedi)",
                sayaclar["okunmamis_eski"],
            )
        logger.info("Süre taraması bitti (%s): %s", gun.isoformat(), sayaclar)
        return sayaclar
    finally:
        if db is None:
            session.close()


def boot_catch_up_scan() -> Optional[dict[str, int]]:
    """Lider boot'unda bir kerelik telafi taraması (modül şerhi: Boot telafisi).

    `api.py` bunu daemon thread'de çağırır; lifespan'i bloklamaz. Her istisna
    burada yutulur ve TEK WARNING loglanır — thread'den taşan istisna kimseye
    ulaşmaz, gece cron'u asıl iştir. Başarıda sayaçları döner (test/elle koşu).
    """
    try:
        sayaclar = scan_deadlines()
        logger.info("Boot telafi taraması bitti: %s", sayaclar)
        return sayaclar
    except Exception as e:
        logger.warning("Boot telafi taraması yapılamadı (gece cron'u yeniden dener): %s", e)
        return None
