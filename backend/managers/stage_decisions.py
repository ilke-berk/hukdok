"""Aşama/karar tarihçesinin TEK yazma yolu (G062).

`case_stage_decisions`, `cases` üzerindeki aşama başına TEK SLOT'luk karar
künyesinin (yerel karar_no/karar_tarihi, istinaf_*, temyiz_*, karar_duzeltme_*)
tarihçe ikizidir — aynı aşamanın ikinci kararı artık eskisini ezmez (kanıt
vakası id-2271: Danıştay 2023 Bozma + 2026 Onama). Desen
`case_manager.sync_current_esas`ın karar ikizidir; o fonksiyonun ve
`case_esas_numbers`ın DAVRANIŞI DEĞİŞMEZ (G062 "dokunma" listesi) — bu modül
onları çağırmaz, `cases.esas_no`/`court` kolonlarına ASLA yazmaz.

Kurallar:

* SIRALAMA `sira_no` İLEDİR, tarihle DEĞİL — tasarım paketinin ölçümü: 170
  föyde karar tarihleri güvenilmez. `sira_no` verilmezse aşamanın bir
  sonrakisi atanır (1'den başlar); aktarım/düzeltme yolları açıkça verebilir.
* Her yazım/silmeden sonra SENKRON: aşamanın EN YÜKSEK sira_no'lu satırı
  `cases`teki o aşamanın tek-slot kolonlarına "son aşama fotoğrafı" olarak
  yazılır (`_PHOTO_COLUMNS`). Satır kalmazsa fotoğraf temizlenir — silinmiş
  bir kararın izini "güncel" diye göstermek ikinci doğruluk kaynağı olurdu.
  Tarihçesi hiç yazılmamış aşamaların slot kolonlarına dokunulmaz (takip
  paneli o kolonları elle yazmaya devam ediyor; birleşik yol G065'in işi).
* `karar_turu`/`karar_lehine` türetmesi BİLİNÇLİ KAPSAM DIŞI (kaba alanlar,
  ayrı karar); YEREL fotoğrafı görev tanımı gereği karar_no + karar_tarihi +
  yerel_karar_durumu üçlüsüyle sınırlıdır.
* `karar_durumu` stage'in G060 resmi listesine karşı doğrulanır (kapalı
  havuz). Karşılaştırma liste ADI iledir ve tablonun İÇERİĞİNE bakılır —
  `active` filtresi BİLİNÇLİ YOK: tarihçe "ne olduğunu" kaydeder; bir değerin
  dropdown'dan kaldırılmış olması tarihsel gerçeği geçersizleştirmez.
  Aynı kapı G066'dan beri takip panelinin yazma yoluna da açık:
  `validated_status_for_column` (`case_manager.update_case_tracking` çağırır) —
  böylece `cases`teki dört karar durumu kolonuna yazan İKİ yol da aynı havuzu
  aynı normalizasyonla denetler.
* `dogrulama_durumu` tahmin yasağının taşıyıcısıdır: verilmezse BELIRSIZ,
  UYAP|BELGE|TURETILDI|BELIRSIZ dışı değer reddedilir.
* Fonksiyonlar COMMIT ETMEZ (flush eder) — işlem sınırı çağıranındır
  (`sync_current_esas` ile aynı sözleşme).
"""
import logging
from datetime import date
from typing import Any, Dict, Optional, cast

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from db_errors import is_unique_violation

logger = logging.getLogger("CaseManager")

# Etiket seti case_esas_numbers ile AYNI, ONCEKI HARİÇ: ONCEKI yalnız esas
# numarası kavramıdır (görevsizlik öncesi numara), bir kararın aşaması olamaz.
DECISION_STAGES = ("YEREL", "ISTINAF", "TEMYIZ", "KARAR_DUZELTME")

# Tahmin yasağının taşıyıcısı — satır hangi kaynakla doğrulandı?
DOGRULAMA_UYAP = "UYAP"            # UYAP kaydından okundu
DOGRULAMA_BELGE = "BELGE"          # elimizdeki belgeden okundu
DOGRULAMA_TURETILDI = "TURETILDI"  # başka alandan kurallıca türetildi
DOGRULAMA_BELIRSIZ = "BELIRSIZ"    # kaynağı bilinmiyor — varsayılan damga
DOGRULAMA_DURUMLARI = (
    DOGRULAMA_UYAP, DOGRULAMA_BELGE, DOGRULAMA_TURETILDI, DOGRULAMA_BELIRSIZ,
)

# stage → G060 resmi listesi (kapalı havuz). reference_lists.LIST_REGISTRY'deki
# local/appeal/cassation/revision_decisions tablolarının modelleri.
STAGE_DECISION_LISTS: Dict[str, Any] = {   # değer: G060 liste modeli (sınıf)
    "YEREL": models.LocalDecision,
    "ISTINAF": models.AppealDecision,
    "TEMYIZ": models.CassationDecision,
    "KARAR_DUZELTME": models.RevisionDecision,
}

# stage → {tarihçe kolonu: cases fotoğraf kolonu}. Satır alanı olmayan slot
# kolonlarına (istinaf_basvuru_tarihi gibi) dokunulmaz. Bilinçli boşluklar:
#   * YEREL üçlüyle sınırlı (görev tanımı); karar_teblig_tarihi/karar_aciklama
#     elle yönetilen slot olarak kalır, karar_turu/karar_lehine kapsam dışı,
#     esas_no/court'un tek yazma yolu sync_current_esas.
#   * TEMYIZ'de "başvuran taraf"ın şemadaki asimetrik adı `temyiz_eden_durumu`
#     (istinaf_basvuran_taraf'ın temyiz ikizi; alan prod'da 0 dolu).
#   * KARAR_DUZELTME'nin mahkeme/başvuran slot kolonu şemada yok.
_PHOTO_COLUMNS = {
    "YEREL": {
        "karar_no": "karar_no",
        "karar_tarihi": "karar_tarihi",
        "karar_durumu": "yerel_karar_durumu",
    },
    "ISTINAF": {
        "mahkeme": "istinaf_mahkemesi",
        "esas_no": "istinaf_esas_no",
        "karar_no": "istinaf_karar_no",
        "karar_tarihi": "istinaf_karar_tarihi",
        "karar_durumu": "istinaf_karar_durumu",
        "teblig_tarihi": "istinaf_teblig_tarihi",
        "basvuran_taraf": "istinaf_basvuran_taraf",
        "aciklama": "istinaf_karar_aciklama",
    },
    "TEMYIZ": {
        "mahkeme": "temyiz_mahkemesi",
        "esas_no": "temyiz_esas_no",
        "karar_no": "temyiz_karar_no",
        "karar_tarihi": "temyiz_karar_tarihi",
        "karar_durumu": "temyiz_karar_durumu",
        "teblig_tarihi": "temyiz_teblig_tarihi",
        "basvuran_taraf": "temyiz_eden_durumu",
        "aciklama": "temyiz_karar_aciklama",
    },
    "KARAR_DUZELTME": {
        "esas_no": "karar_duzeltme_esas_no",
        "karar_no": "karar_duzeltme_karar_no",
        "karar_tarihi": "karar_duzeltme_tarihi",
        "karar_durumu": "karar_duzeltme_durumu",
        "teblig_tarihi": "karar_duzeltme_teblig_tarihi",
        "aciklama": "karar_duzeltme_aciklama",
    },
}

# Kolon sınırları modelden okunur, elle tekrarlanmaz (case_manager._ESAS_NO_MAX
# gerekçesi: şema büyürse kod kendiliğinden uyar).
_LIMITS: Dict[str, int] = {}
for _column in models.CaseStageDecision.__table__.columns:
    _limit = getattr(_column.type, "length", None)
    if _limit:
        _LIMITS[_column.name] = _limit


class DuplicateStageDecisionError(Exception):
    """Aynı (case_id, stage, sira_no) ikinci kez yazılmak istendi.

    `uq_case_stage_decision` kısıtının alan hatası karşılığı; route katmanı
    (FAZ F/UI işi) bunu 409'a çevirir. G049 dersi: bu yol GERÇEK kısıt
    kırmızısıyla test edilir, ön kontrolle değil.
    """


class InvalidDecisionStatusError(ValueError):
    """Karar durumu değeri aşamanın G060 kapalı havuzunda yok (G066).

    `ValueError` ALT SINIFI: bu modülün tarihçe yolunu `pytest.raises(ValueError)`
    ile kilitleyen G062 testleri ve `ValueError` yakalayan çağıranlar aynen
    çalışmaya devam eder. Ayrı tip olmasının tek nedeni HTTP eşlemesi —
    `api.py` bunu 400'e çevirir; genel `except Exception` yollarının hatayı
    500'e/False'a yutması (G003 durum kodu disiplini) böyle önlenir.
    """


def _clamped(value: Optional[str], column: str) -> Optional[str]:
    """Kısa metin alanını boşluk-normalize edip kolon sınırına kırpar.

    Taşan bir mahkeme adı yüzünden kaydın tamamını 500'e çevirmek orantısız
    olurdu (sync_current_esas'taki gerekçe); kırpma sessiz de değildir —
    deneme-düzeyi durum WARNING'dir (log sözleşmesi).
    """
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    limit = _LIMITS.get(column)
    if limit and len(text) > limit:
        logger.warning(
            f"case_stage_decisions.{column} kolon sınırına kırpıldı (>{limit}): {text[:60]!r}…"
        )
        text = text[:limit]
    return text


def _validated_stage(stage: str) -> str:
    if stage not in DECISION_STAGES:
        raise ValueError(f"Bilinmeyen karar aşaması: {stage!r} (izinli: {', '.join(DECISION_STAGES)})")
    return stage


def _validated_dogrulama(value: Optional[str]) -> str:
    """Verilmezse BELIRSIZ; kapalı küme dışı damga reddedilir (tahmin yasağı)."""
    if value is None or not str(value).strip():
        return DOGRULAMA_BELIRSIZ
    damga = str(value).strip()
    if damga not in DOGRULAMA_DURUMLARI:
        raise ValueError(
            f"Bilinmeyen doğrulama durumu: {damga!r} (izinli: {', '.join(DOGRULAMA_DURUMLARI)})"
        )
    return damga


def _validated_karar_durumu(db: Session, stage: str, value: Optional[str]) -> Optional[str]:
    """Kararın resmi sonucu stage'in G060 kapalı havuzunda olmalı (adıyla).

    None/boş serbesttir: karar satırı sonucu henüz bilinmeden de doğabilir
    (dogrulama_durumu=BELIRSIZ bunun damgasıdır).
    """
    if value is None or not str(value).strip():
        return None
    ad = " ".join(str(value).split())
    liste = STAGE_DECISION_LISTS[stage]
    if db.query(liste.id).filter(liste.name == ad).first() is None:
        raise InvalidDecisionStatusError(
            f"{stage} için geçersiz karar durumu: {ad!r} — değer "
            f"{liste.__tablename__} resmi listesinde yok (kapalı havuz, G060)"
        )
    return ad


# ─── Takip yazma yolunun kapısı (G066) ───────────────────────────────────────
# `cases` üzerindeki dört karar durumu kolonu → aşama etiketi. ÜÇÜNCÜ BİR KOPYA
# DEĞİL: eşleme `_PHOTO_COLUMNS`tan TÜRETİLİR (görev kuralı). Kaynak olarak
# `reference_lists.LIST_REGISTRY` yerine burası seçildi, çünkü aynı kolonlara
# yazan iki yol (tarihçe fotoğrafı + takip paneli) artık TEK haritayı okuyor;
# yeni bir aşama `_PHOTO_COLUMNS`a eklendiği anda doğrulama da onu kapsar.
DECISION_STATUS_COLUMNS: Dict[str, str] = {
    kolonlar["karar_durumu"]: stage
    for stage, kolonlar in _PHOTO_COLUMNS.items()
    if "karar_durumu" in kolonlar
}


def validated_status_for_column(db: Session, column: str, value: Any) -> Any:
    """`cases.<column>` karar durumu ise kapalı havuza karşı doğrular (G066).

    Karar durumu OLMAYAN kolon dokunulmadan geri döner — çağıran (takip
    panelinin whitelist döngüsü) alanları tek tek ayıklamak zorunda kalmasın.

    İki bilinçli sözleşme (görev dosyasının 2. ve 3. karar noktaları):

    * `active` filtresi YOK — tarihçe yoluyla SİMETRİ. İki yol aynı kolona
      yazıyor ve fotoğraf senkronu ikisini birbirine bağlıyor; dropdown'dan
      kaldırılmış (pasif) bir değeri takip panelinde reddetmek, tarihçeden
      gelen aynı değeri kabul etmekle çelişirdi.
    * Liste BOŞSA doğrulama devre dışıdır (uyarıyla) — tarihçe yolundan
      BİLİNÇLİ AYRIŞMA. `case_stage_decisions` yepyeni bir tablodur, tek
      yazıcısı bu modüldür; orada "boş liste = hiçbir şey geçmez" bedelsizdir.
      Takip paneli ise 14.403 kartın CANLI ana yoludur: seed'i koşmamış ya da
      listesi boşaltılmış bir kurulumda aynı sertlik, yapılandırma boşluğunu
      kullanıcının veri girememesine çevirirdi. Boş liste = "havuz henüz
      kurulmamış" sayılır; deneme-düzeyi durum olduğu için WARNING (log
      sözleşmesi), sessiz değil.
    """
    stage = DECISION_STATUS_COLUMNS.get(column)
    if stage is None:
        return value
    if value is None or not str(value).strip():
        return None
    liste = STAGE_DECISION_LISTS[stage]
    if db.query(liste.id).first() is None:
        logger.warning(
            f"{liste.__tablename__} resmi listesi BOŞ — {column} kapalı havuz "
            f"doğrulaması atlandı (seed koşmamış olabilir)"
        )
        return " ".join(str(value).split())
    return _validated_karar_durumu(db, stage, value)


def _next_sira_no(db: Session, case_id: int, stage: str) -> int:
    en_yuksek = (
        db.query(func.max(models.CaseStageDecision.sira_no))
        .filter(
            models.CaseStageDecision.case_id == case_id,
            models.CaseStageDecision.stage == stage,
        )
        .scalar()
    )
    return int(en_yuksek or 0) + 1


def _is_duplicate_violation(exc: IntegrityError) -> bool:
    """UNIQUE ihlali mi? PG'de SQLSTATE 23505 ile; SQLSTATE taşımayan diyalekt
    (sqlite birim koşusu) için: bu INSERT'in girdileri ön-doğrulandığından tek
    gerçekçi kısıt `uq_case_stage_decision`dır (confirm_idempotency'deki akıl
    yürütme). SQLSTATE VARSA ama 23505 DEĞİLSE (örn. FK 23503) çakışma
    SAYILMAZ — yanlış sınıflandırma gerçek hatayı 409'a gizlerdi."""
    if is_unique_violation(exc):
        return True
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    return code is None


def _insert_decision(db: Session, values: dict) -> models.CaseStageDecision:
    """Satırı SAVEPOINT içinde yazar; çakışmada oturumu bozmadan alan hatası verir."""
    row = models.CaseStageDecision(**values)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        if _is_duplicate_violation(exc):
            raise DuplicateStageDecisionError(
                f"Bu karar sırası dolu: dava {values['case_id']} {values['stage']} "
                f"sira_no={values['sira_no']} (uq_case_stage_decision)"
            ) from exc
        raise
    return row


def _resync_stage_photo(db: Session, case: models.Case, stage: str) -> None:
    """`cases`teki aşama slot kolonlarını EN YÜKSEK sira_no'lu satırla eşitler.

    `sync_current_esas` deseninin karar ikizi: slot kolonları TÜRETİLMİŞ
    fotoğraftır, doğruluk kaynağı tarihçe tablosudur. Satır kalmadıysa
    fotoğraf temizlenir. Diğer aşamaların kolonlarına dokunulmaz.
    """
    son = (
        db.query(models.CaseStageDecision)
        .filter(
            models.CaseStageDecision.case_id == case.id,
            models.CaseStageDecision.stage == stage,
        )
        .order_by(models.CaseStageDecision.sira_no.desc())
        .first()
    )
    for row_field, case_column in _PHOTO_COLUMNS[stage].items():
        setattr(case, case_column, getattr(son, row_field) if son is not None else None)


def add_stage_decision(
    db: Session,
    case: models.Case,
    *,
    stage: str,
    sira_no: Optional[int] = None,
    mahkeme: Optional[str] = None,
    esas_no: Optional[str] = None,
    karar_no: Optional[str] = None,
    karar_tarihi: Optional[date] = None,
    karar_durumu: Optional[str] = None,
    teblig_tarihi: Optional[date] = None,
    basvuran_taraf: Optional[str] = None,
    aciklama: Optional[str] = None,
    dogrulama_durumu: Optional[str] = None,
    kaynak_id: Optional[int] = None,
    source: Optional[str] = None,
) -> models.CaseStageDecision:
    """Aşamaya YENİ karar satırı ekler ve tek-slot fotoğrafı tazeler.

    * `sira_no` verilmezse aşamanın bir sonrakisi atanır; verilmişse (aktarım/
      düzeltme yolu) aynen kullanılır ve doluysa DuplicateStageDecisionError
      yükselir (kısıt kırmızısından, ön kontrolden değil — G049).
    * `kaynak_id` verilirse AYNI davanın mevcut bir kararını göstermek zorunda
      (bozma → yeni yerel zinciri; çapraz dava bağı veri çöpü olurdu).
    * Dönen satır flush edilmiştir (id dolu); commit çağıranın işi.
    """
    stage = _validated_stage(stage)
    damga = _validated_dogrulama(dogrulama_durumu)

    if case.id is None:
        db.flush()          # FK için dava id'si şart (sync_current_esas deseni)
    case_id = cast(int, case.id)

    sonuc = _validated_karar_durumu(db, stage, karar_durumu)

    if kaynak_id is not None:
        kaynak = db.get(models.CaseStageDecision, kaynak_id)
        if kaynak is None or kaynak.case_id != case_id:
            raise ValueError(
                f"kaynak_id={kaynak_id} bu davanın mevcut bir kararı değil (dava {case_id})"
            )

    values = {
        "case_id": case_id,
        "stage": stage,
        "mahkeme": _clamped(mahkeme, "mahkeme"),
        "esas_no": _clamped(esas_no, "esas_no"),
        "karar_no": _clamped(karar_no, "karar_no"),
        "karar_tarihi": karar_tarihi,
        "karar_durumu": sonuc,
        "teblig_tarihi": teblig_tarihi,
        "basvuran_taraf": _clamped(basvuran_taraf, "basvuran_taraf"),
        # Serbest metin: satır sonları anlamlı olabilir, boşluk katlaması yok
        "aciklama": (str(aciklama).strip() or None) if aciklama is not None else None,
        "dogrulama_durumu": damga,
        "kaynak_id": kaynak_id,
        "source": _clamped(source, "source"),
    }

    if sira_no is not None:
        if sira_no < 1:
            raise ValueError(f"sira_no 1'den başlar: {sira_no!r}")
        row = _insert_decision(db, {**values, "sira_no": sira_no})
    else:
        try:
            row = _insert_decision(db, {**values, "sira_no": _next_sira_no(db, case_id, stage)})
        except DuplicateStageDecisionError:
            # Otomatik atamada yarış kaybedildi (iki worker aynı max'ı gördü):
            # sıra BİR kez yeniden hesaplanır; yine çakışırsa hata çağırana.
            row = _insert_decision(db, {**values, "sira_no": _next_sira_no(db, case_id, stage)})

    _resync_stage_photo(db, case, stage)
    return row


def delete_stage_decision(db: Session, case: models.Case, decision_id: int) -> bool:
    """Tarihçe satırını siler (admin düzeltme yolu) ve fotoğrafı tazeler.

    Satır yoksa ya da BU davaya ait değilse False döner, hiçbir şey değişmez.
    Silinen satırı `kaynak_id` ile gösteren kayıtlar öksüz kalır ama SİLİNMEZ
    (kaynak_id → NULL; şemadaki ON DELETE SET NULL'un ORM ikizi — sqlite birim
    koşusu FK aksiyonlarını çalıştırmadığı için elle yazılır). Fotoğraf bir
    önceki sira_no'ya geri düşer; aşamada satır kalmazsa temizlenir.
    """
    row = db.get(models.CaseStageDecision, decision_id)
    if row is None or row.case_id != case.id:
        return False
    stage = cast(str, row.stage)
    db.query(models.CaseStageDecision).filter(
        models.CaseStageDecision.kaynak_id == row.id
    ).update({models.CaseStageDecision.kaynak_id: None}, synchronize_session=False)
    db.delete(row)
    db.flush()
    _resync_stage_photo(db, case, stage)
    return True


def get_stage_decisions(db: Session, case_id: int) -> list:
    """Davanın karar tarihçesi — (stage, sira_no) sırasıyla ORM satırları.

    Sıra SÖZLEŞMEDİR: karar sırası `sira_no`dan okunur, tarihten değil.
    Okuma/yazma UÇLARI bu görevin kapsamı dışında (FAZ F + UI ayrı işler);
    testler ve gelecekteki route katmanı bu tek noktadan okur.
    """
    return (
        db.query(models.CaseStageDecision)
        .filter(models.CaseStageDecision.case_id == case_id)
        .order_by(models.CaseStageDecision.stage, models.CaseStageDecision.sira_no)
        .all()
    )
