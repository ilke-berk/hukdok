"""SharePoint arşiv hedef adlarının benzersizleştirilmesi (2026-09-01 arızası).

Neden: /confirm hedef adı frontend'in ürettiği `TARİH_TÜR_ESAS_KarşıTaraf.pdf`
kalıbıdır ve teklik bileşeni taşımaz; Graph yüklemeleri conflictBehavior=replace
ile gider (sharepoint/sharepoint_uploader_graph.py). Aynı davada aynı türden ve
aynı belge tarihli iki belge (toplu yüklemede yaygın) birebir aynı adı üretir ve
ikinci yükleme birincinin dosyasını SESSİZCE değiştirirdi. 2026-09-01 tespiti:
prod'da 102 mükerrer ad grubu / 240 kayıt; 72 grupta orijinal adlar farklı, yani
gerçekten farklı belgeler ezilmiş. Ezilen içerik SharePoint sürüm geçmişinde
kalır; onarımı scripts/repair_overwritten_documents.py yapar.

Kurallar:
- İşlenmiş arşiv (02_YEDEK_ARSIV) tekliği GÖVDE (stem) düzeyindedir, tam ad
  düzeyinde değil: conversion_pending belgesi `X.udf` adıyla saklanır ve gece
  job'ı başarıda `X.pdf` adına döner (services/conversion_retry.py) — tam-ad
  tekliği `X.pdf`'i serbest sayar, gece dönüşümü başka belgenin dosyasını yine
  ezerdi. Stem tekilse her uzantı güvendedir.
- HAM arşiv adı `yükleme-tarihi_orijinal-ad`dır ve DB'de kolonu yoktur; teklik
  upload_outbox (kind='ham') tarihçesine karşı TAM AD eşitliğiyle denetlenir.
  Tarih öneki yüzünden çakışma zaten yalnız aynı gün içinde mümkündür; outbox
  satırları silinmediği için tarihçe yeterlidir. (enqueue None dönüp
  BackgroundTasks fallback'ine düşen nadir yükleme outbox'ta iz bırakmaz —
  kabul edilen boşluk, bugünkü davranıştan kötü değil.)
- SQL filtreleri yalnız ÖNFİLTREDİR; nihai karar her zaman Python'daki kesin
  karşılaştırmadadır (LIKE joker kaçışı ve fake'lenebilir testler için).
- Yarış: ad kontrolü ile INSERT ayrı transaction'larda — eşzamanlı iki /confirm
  aynı adı seçebilir. resolve_stored_name_race INSERT SONRASI çağrılır: aynı
  stem'i taşıyan en küçük id adı tutar, kaybeden satır deterministik
  `_<doc_id>` sonekini alır (doc_id tekil olduğundan ikinci tur yarış
  imkânsızdır) ve DB'de yeniden adlandırılır. SharePoint kuyruklaması bu addan
  SONRA yapıldığı için hedef de düzeltilmiş addır.
- Hata semantiği: buradaki her arıza WARNING + adayı olduğu gibi döndürür
  (bugünkü davranışa geri düşüş) — adlandırma katmanı arşivlemeyi eskisinden
  kötü yapamaz. Log sözleşmesi gereği ERROR üretmez.
"""
import logging
import uuid
from pathlib import Path
from typing import Optional

from database import SessionLocal
import models

logger = logging.getLogger(__name__)

# Önfiltre satır tavanı: aynı stem ailesinin makul üst sınırının çok üstü.
_PREFILTER_LIMIT = 200
# _2.._99 denenir; hepsi doluysa kısa rastgele sonek (sonsuz döngü sigortası).
_MAX_SUFFIX = 99


def _split_name(name: str) -> tuple[str, str]:
    p = Path(str(name or ""))
    return p.stem, p.suffix


def _norm_stem(name: str) -> str:
    """Karşılaştırma anahtarı: SON uzantı düşer, büyük/küçük harf katlanır
    (SharePoint adları büyük/küçük harf duyarsızdır)."""
    return Path(str(name or "")).stem.casefold()


def _like_escape(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def islenmis_stem_taken(db, stem: str, exclude_doc_id: Optional[int] = None) -> bool:
    """İşlenmiş arşivde stem kullanımda mı? case_documents + upload_outbox
    (kind='islenmis') birlikte bakılır: belge kaydı açılamadan kuyruklanmış
    nadir satırlar da ad uzayını işgal eder.

    exclude_doc_id: gece dönüşüm job'ı kendi belgesinin mevcut adını/satırlarını
    çakışma saymamalı (aynı ada yeniden yüklemek kendi dosyası için idempotent).
    """
    stem_cf = str(stem).casefold()
    like_pat = _like_escape(stem) + ".%"

    doc_rows = (
        db.query(models.CaseDocument.id, models.CaseDocument.stored_filename)
        .filter(models.CaseDocument.stored_filename.like(like_pat, escape="\\"))
        .limit(_PREFILTER_LIMIT)
        .all()
    )
    for rid, fname in doc_rows:
        if exclude_doc_id is not None and rid == exclude_doc_id:
            continue
        if _norm_stem(fname) == stem_cf:
            return True

    outbox_rows = (
        db.query(
            models.UploadOutbox.document_id,
            models.UploadOutbox.kind,
            models.UploadOutbox.target_filename,
        )
        .filter(
            models.UploadOutbox.kind == "islenmis",
            models.UploadOutbox.target_filename.like(like_pat, escape="\\"),
        )
        .limit(_PREFILTER_LIMIT)
        .all()
    )
    for did, kind, fname in outbox_rows:
        if kind != "islenmis":
            continue
        if exclude_doc_id is not None and did == exclude_doc_id:
            continue
        if _norm_stem(fname) == stem_cf:
            return True
    return False


def _ham_name_taken(db, candidate: str) -> bool:
    cand_cf = str(candidate).casefold()
    rows = (
        db.query(models.UploadOutbox.kind, models.UploadOutbox.target_filename)
        .filter(
            models.UploadOutbox.kind == "ham",
            models.UploadOutbox.target_filename == candidate,
        )
        .limit(_PREFILTER_LIMIT)
        .all()
    )
    for kind, fname in rows:
        if kind == "ham" and str(fname).casefold() == cand_cf:
            return True
    return False


def _suffixed(stem: str, ext: str, n: int) -> str:
    return f"{stem}_{n}{ext}"


def unique_islenmis_name(candidate: str, exclude_doc_id: Optional[int] = None) -> str:
    """İşlenmiş arşiv hedef adını stem düzeyinde benzersizleştirir.

    Çakışmada `_2`, `_3`... denenir; _MAX_SUFFIX de doluysa kısa rastgele
    sonekle döner. Her arızada aday olduğu gibi döner (bugünkü davranış)."""
    db = None
    try:
        db = SessionLocal()
        stem, ext = _split_name(candidate)
        if not stem:
            return candidate
        if not islenmis_stem_taken(db, stem, exclude_doc_id):
            return candidate
        for n in range(2, _MAX_SUFFIX + 1):
            if not islenmis_stem_taken(db, f"{stem}_{n}", exclude_doc_id):
                final = _suffixed(stem, ext, n)
                logger.info(f"Arşiv adı çakışması: '{candidate}' → '{final}'")
                return final
        final = f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
        logger.warning(f"Arşiv adı sonek uzayı doldu: '{candidate}' → '{final}'")
        return final
    except Exception as e:
        logger.warning(f"Arşiv adı teklik kontrolü yapılamadı ('{candidate}'): {e}")
        return candidate
    finally:
        if db is not None:
            db.close()


def unique_ham_name(candidate: str) -> str:
    """HAM arşiv hedef adını tam-ad düzeyinde benzersizleştirir (outbox
    tarihçesine karşı). Her arızada aday olduğu gibi döner."""
    db = None
    try:
        db = SessionLocal()
        if not _ham_name_taken(db, candidate):
            return candidate
        stem, ext = _split_name(candidate)
        for n in range(2, _MAX_SUFFIX + 1):
            cand = _suffixed(stem, ext, n)
            if not _ham_name_taken(db, cand):
                logger.info(f"HAM arşiv adı çakışması: '{candidate}' → '{cand}'")
                return cand
        final = f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
        logger.warning(f"HAM arşiv adı sonek uzayı doldu: '{candidate}' → '{final}'")
        return final
    except Exception as e:
        logger.warning(f"HAM arşiv adı teklik kontrolü yapılamadı ('{candidate}'): {e}")
        return candidate
    finally:
        if db is not None:
            db.close()


def resolve_stored_name_race(doc_id: Optional[int], name: str) -> str:
    """INSERT sonrası yarış çözümü: aynı stem'i taşıyan en küçük id ad sahibidir.

    Kaybeden satırın adı `_<doc_id>` sonekiyle deterministik benzersizleştirilir
    ve satır DB'de güncellenir; SharePoint kuyruklaması bu dönüşten SONRA
    yapılmalıdır. Her arızada ad olduğu gibi döner (yarış penceresi bugünkü
    davranışa düşer)."""
    if not doc_id:
        return name
    db = None
    try:
        db = SessionLocal()
        stem, ext = _split_name(name)
        stem_cf = str(stem).casefold()
        like_pat = _like_escape(stem) + ".%"
        rows = (
            db.query(models.CaseDocument.id, models.CaseDocument.stored_filename)
            .filter(models.CaseDocument.stored_filename.like(like_pat, escape="\\"))
            .limit(_PREFILTER_LIMIT)
            .all()
        )
        rival_ids = [
            rid for rid, fname in rows
            if rid != doc_id and _norm_stem(fname) == stem_cf
        ]
        if not rival_ids or min(rival_ids) > doc_id:
            return name

        new_name = f"{stem}_{doc_id}{ext}"
        doc = (
            db.query(models.CaseDocument)
            .filter(models.CaseDocument.id == doc_id)
            .first()
        )
        if doc is None:
            return name
        doc.stored_filename = new_name
        db.commit()
        logger.warning(
            f"Arşiv adı yarışı çözüldü: doc={doc_id} '{name}' → '{new_name}' "
            f"(rakip satırlar: {sorted(rival_ids)})"
        )
        return new_name
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        logger.warning(f"Arşiv adı yarış çözümü yapılamadı (doc={doc_id}, '{name}'): {e}")
        return name
    finally:
        if db is not None:
            db.close()
