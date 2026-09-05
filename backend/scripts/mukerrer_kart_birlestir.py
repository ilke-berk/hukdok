#!/usr/bin/env python3
"""Mükerrer dava kartlarını birleştirir (G127) — kalan karta taşı, mükerreri SOFT sil.

Kullanıcı kararı (05.09.2026): 04.09 paketinin 29 "belirsiz eşleşme" föyünden
9'u, eski aktarımımızın AYNI dava için iki kart açmasından kaynaklanıyordu
(aynı esas + mahkeme + müvekkil + karşı taraf; 8 çift). Aktarım bu föyleri
hiçbir karta yazmıyordu. Bu script çifti birleştirir: mükerrer kartın her şeyi
kalan karta taşınır, mükerrer soft-delete olur (`deleted_at`, `delete_reason`;
routes/cases.py api_delete_case deseni) — böylece DosyaNo köprüsü tek karta
çözülür ve sonraki aktarım koşusu föyü bağlar.

Kurallar (belge koruma şartı, G063/G045/G062 tek yazıcı desenleri):
* Kart HARD silinmez; `deleted_at` + `active=False`. Ofis numarası mükerrerde
  kalır (unique kısıt silinenleri kapsar, yeniden verilmez).
* Belgeler `case_id` ile taşınır; `case_party_id` kalan karttaki aynı adlı
  tarafa yeniden bağlanır (yoksa taraf taşınır) — SET NULL tuzağına düşmez.
* Taraflar/avukatlar AD bazlı tekilleştirilerek taşınır (kalan kartta zaten
  varsa mükerrerdeki satır silinir — belge bağı önce yeniden yazılır).
* Föyler, aşama satırları, esas tarihçesi, ilişkiler, duruşmalar, bildirimler,
  aşama günlükleri kalan karta yeniden işaretlenir; tarihçe (`case_history`)
  mükerrerde KALIR (o kartın geçmişidir), kalan karta tek birleştirme notu düşer.
* `klasor_no_2` birleşimi (";" ayraçlı, mükerrersiz) kalan karta yazılır.
* Ön koşul: iki kart da silinmemiş; esas no ve mahkeme anahtarı aynı; müvekkil
  ad kümeleri aynı — değilse çift REDDEDİLİR (mükerrer değil, müvekkil ayrımı).

    docker compose exec -T backend python scripts/mukerrer_kart_birlestir.py \\
        --cift 719:718 --cift 721:720            # kalan:mükerrer, kuru koşu
    docker compose exec -T backend python scripts/mukerrer_kart_birlestir.py \\
        --cift 719:718 --apply --kim "ilke"      # yazar
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from managers import case_manager
from managers.reference_lists import tr_upper
from party_check import normalize_party_key
from scripts.hukdok_aktarim import _baslik_anahtari

logger = logging.getLogger("MukerrerBirlestir")
DEGISTIREN = "mukerrer_kart_birlestir"


@dataclass
class BirlestirmeSonucu:
    kalan_id: int
    mukerrer_id: int
    ret: Optional[str] = None
    tasinan: Dict[str, int] = field(default_factory=dict)
    kalan_tracking_no: str = ""
    mukerrer_tracking_no: str = ""


def _taraf_anahtari(p: models.CaseParty) -> Tuple[str, str]:
    return (p.party_type or "", normalize_party_key(p.name or ""))


def _muvekkil_kumesi(case: models.Case) -> set:
    return {normalize_party_key(p.name or "") for p in case.parties if p.party_type == "CLIENT"}


def on_kosul(kalan: models.Case, mukerrer: models.Case) -> Optional[str]:
    """Çift gerçekten mükerrer mi? Değilse sebep döner (birleştirme YAPILMAZ)."""
    if kalan.id == mukerrer.id:
        return "aynı kart"
    if kalan.deleted_at is not None or mukerrer.deleted_at is not None:
        return "kartlardan biri zaten silinmiş"
    if (kalan.esas_no or "") != (mukerrer.esas_no or ""):
        return f"esas no farklı ({kalan.esas_no!r} ≠ {mukerrer.esas_no!r})"
    # Mahkeme: ikisi de doluysa aynı olmalı; biri boşsa (eski aktarım mahkemesiz
    # kart açmış — #14315 örneği) esas + müvekkil eşleşmesi yeter.
    if (kalan.court and mukerrer.court
            and _baslik_anahtari(kalan.court) != _baslik_anahtari(mukerrer.court)):
        return f"mahkeme farklı ({kalan.court!r} ≠ {mukerrer.court!r})"
    if _muvekkil_kumesi(kalan) != _muvekkil_kumesi(mukerrer):
        return "müvekkil kümeleri farklı (müvekkil ayrımı — birleştirme değil)"
    return None


def _klasor_birlesimi(kalan: Optional[str], mukerrer: Optional[str]) -> Optional[str]:
    parcalar: List[str] = []
    for ham in ((kalan or "") + ";" + (mukerrer or "")).split(";"):
        p = " ".join(ham.split())
        if p and tr_upper(p) not in {tr_upper(x) for x in parcalar}:
            parcalar.append(p)
    return ";".join(parcalar) or None


def birlestir(db, kalan: models.Case, mukerrer: models.Case, *, kim: str) -> BirlestirmeSonucu:
    """Tek çifti birleştirir (flush eder, COMMIT ETMEZ — çağıranın işi)."""
    sonuc = BirlestirmeSonucu(kalan.id, mukerrer.id, kalan_tracking_no=kalan.tracking_no,
                              mukerrer_tracking_no=mukerrer.tracking_no)
    sonuc.ret = on_kosul(kalan, mukerrer)
    if sonuc.ret:
        return sonuc
    t = sonuc.tasinan

    # 1) Taraflar: kalan karttaki (tür, ad) → satır; mükerrerdeki taraf id → kalan taraf id
    # Taraf/avukat/belge ilişkileri `cascade="all, delete-orphan"` — taşıma
    # koleksiyon üzerinden yapılır (remove + append); yalnız FK kolonunu yazmak
    # ORM koleksiyonuyla çelişir ve flush'ta geri alınabilirdi.
    kalan_taraf = {_taraf_anahtari(p): p for p in kalan.parties}
    taraf_esleme: Dict[int, int] = {}
    silinecek_taraflar: List[models.CaseParty] = []
    for p in list(mukerrer.parties):
        hedef = kalan_taraf.get(_taraf_anahtari(p))
        if hedef is None:
            mukerrer.parties.remove(p)
            kalan.parties.append(p)               # kalanda yok → taşı
            kalan_taraf[_taraf_anahtari(p)] = p
            t["taraf_tasinan"] = t.get("taraf_tasinan", 0) + 1
        else:
            taraf_esleme[p.id] = hedef.id          # kalanda var → belge bağı yeniden yazılır, satır silinir
            silinecek_taraflar.append(p)
    db.flush()

    # 2) Belgeler: kart + taraf bağı (SET NULL tuzağı: taraf silinmeden ÖNCE yeniden bağla)
    for d in list(mukerrer.documents):
        mukerrer.documents.remove(d)
        kalan.documents.append(d)
        if d.case_party_id in taraf_esleme:
            d.case_party_id = taraf_esleme[d.case_party_id]
        t["belge"] = t.get("belge", 0) + 1
    # Föyler (cascade'siz ilişki): kart + taraf bağı
    for f in db.query(models.CaseFoy).filter(models.CaseFoy.case_id == mukerrer.id).all():
        f.case_id = kalan.id
        if f.case_party_id in taraf_esleme:
            f.case_party_id = taraf_esleme[f.case_party_id]
        t["foy"] = t.get("foy", 0) + 1
    db.flush()
    for p in silinecek_taraflar:
        mukerrer.parties.remove(p)                 # delete-orphan: yetim → silinir
        t["taraf_tekil"] = t.get("taraf_tekil", 0) + 1

    # 3) Avukatlar (ad bazlı tekil)
    kalan_avukat = {normalize_party_key(lw.name or "") for lw in kalan.lawyers}
    for lw in list(mukerrer.lawyers):
        mukerrer.lawyers.remove(lw)
        if normalize_party_key(lw.name or "") not in kalan_avukat:
            kalan.lawyers.append(lw)
            kalan_avukat.add(normalize_party_key(lw.name or ""))
            t["avukat"] = t.get("avukat", 0) + 1
    if not kalan.responsible_lawyer_name and mukerrer.responsible_lawyer_name:
        kalan.responsible_lawyer_name = mukerrer.responsible_lawyer_name

    # 4) Aşama satırları: kalanda o aşama boşsa taşı (dolu aşamaya dokunma, G062)
    kalan_asamalar = {s.stage for s in db.query(models.CaseStageDecision.stage)
                      .filter(models.CaseStageDecision.case_id == kalan.id)}
    for s in db.query(models.CaseStageDecision).filter(models.CaseStageDecision.case_id == mukerrer.id).all():
        if s.stage in kalan_asamalar:
            db.delete(s)
        else:
            s.case_id = kalan.id
            t["asama"] = t.get("asama", 0) + 1
    # 5) Esas tarihçesi: güncel olmayanlar kalana eklenir (aynı satır varsa atlanır)
    for e in db.query(models.CaseEsasNumber).filter(models.CaseEsasNumber.case_id == mukerrer.id).all():
        if not e.is_current and case_manager.add_historical_esas(
                db, kalan, e.esas_no, stage=e.stage, court=e.court, source=e.source) is not None:
            t["esas"] = t.get("esas", 0) + 1
        db.delete(e)
    # 6) İlişkiler / duruşmalar / bildirimler / aşama günlükleri: yeniden işaretle
    for r in db.query(models.CaseRelation).filter(
            (models.CaseRelation.source_case_id == mukerrer.id) | (models.CaseRelation.target_case_id == mukerrer.id)).all():
        if r.source_case_id == mukerrer.id:
            r.source_case_id = kalan.id
        if r.target_case_id == mukerrer.id:
            r.target_case_id = kalan.id
        if r.source_case_id == r.target_case_id:
            db.delete(r)                           # kendine ilişki anlamsız
        else:
            t["iliski"] = t.get("iliski", 0) + 1
    for model, ad in ((models.HearingDate, "durusma"), (models.Notification, "bildirim"),
                      (models.CaseStageLog, "asama_gunlugu")):
        n = db.query(model).filter(model.case_id == mukerrer.id).update(
            {model.case_id: kalan.id}, synchronize_session=False)
        if n:
            t[ad] = n

    # 7) Kart alanları: klasör no birleşimi, boş alanları mükerrerden tamamla, notlar
    kalan.klasor_no_2 = _klasor_birlesimi(kalan.klasor_no_2, mukerrer.klasor_no_2)
    for alan in ("subject", "court", "opening_date", "acceptance_date", "hasar_dosya_no", "hukuk_no",
                 "sub_type", "bureau_type", "muvekkil_tipi", "hizmet_turu"):
        if getattr(kalan, alan) in (None, "") and getattr(mukerrer, alan) not in (None, ""):
            setattr(kalan, alan, getattr(mukerrer, alan))
            t["alan_tamamlanan"] = t.get("alan_tamamlanan", 0) + 1
    if kalan.status != "DERDEST" and mukerrer.status == "DERDEST":
        kalan.status = "DERDEST"                   # aktif dava mahzene düşmesin
    if mukerrer.notes:
        kalan.notes = ((kalan.notes or "") + f"\n[Birleştirme #{mukerrer.id}] {mukerrer.notes}").strip()

    # 8) Tarihçe notu + soft delete
    db.add(models.CaseHistory(
        case_id=kalan.id, field_name="mukerrer_birlestirme",
        old_value=mukerrer.tracking_no, new_value=kalan.tracking_no,
        changed_by=DEGISTIREN, source=f"mukerrer #{mukerrer.id} → #{kalan.id} ({kim})",
    ))
    mukerrer.deleted_at = func.now()
    mukerrer.deleted_by = kim
    mukerrer.delete_reason = f"Mükerrer kart: #{kalan.id} {kalan.tracking_no} ile birleştirildi"
    mukerrer.active = False
    db.flush()
    return sonuc


def ciftleri_birlestir(session_factory, ciftler: Sequence[Tuple[int, int]], *,
                       apply: bool = False, kim: str = DEGISTIREN) -> List[BirlestirmeSonucu]:
    sonuclar = []
    db = session_factory()
    try:
        for kalan_id, mukerrer_id in ciftler:
            kalan = db.get(models.Case, kalan_id)
            mukerrer = db.get(models.Case, mukerrer_id)
            if kalan is None or mukerrer is None:
                sonuclar.append(BirlestirmeSonucu(kalan_id, mukerrer_id, ret="kart bulunamadı"))
                continue
            with db.begin_nested():
                sonuc = birlestir(db, kalan, mukerrer, kim=kim)
            sonuclar.append(sonuc)
        if apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    return sonuclar


def ozet_metni(sonuclar: Sequence[BirlestirmeSonucu], *, apply: bool) -> str:
    satirlar = []
    for s in sonuclar:
        if s.ret:
            satirlar.append(f"RET   #{s.mukerrer_id} → #{s.kalan_id}: {s.ret}")
        else:
            tasinan = ", ".join(f"{k} {v}" for k, v in sorted(s.tasinan.items())) or "taşınacak bir şey yok"
            satirlar.append(f"{'BİRLEŞTİ' if apply else 'PLAN    '} #{s.mukerrer_id} {s.mukerrer_tracking_no} → "
                            f"#{s.kalan_id} {s.kalan_tracking_no}: {tasinan}")
    ok = sum(1 for s in sonuclar if not s.ret)
    satirlar.append(f"{ok}/{len(sonuclar)} çift {'birleştirildi' if apply else 'birleştirilebilir (kuru koşu)'}")
    return "\n".join(satirlar)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Mükerrer kartları birleştirir (G127)")
    parser.add_argument("--cift", action="append", required=True,
                        help="kalan_id:mukerrer_id (tekrarlanabilir)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--kim", default=DEGISTIREN, help="deleted_by / tarihçe imzası")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from logging_setup import configure_logging

    configure_logging()
    import database

    ciftler = []
    for c in args.cift:
        kalan, mukerrer = c.split(":")
        ciftler.append((int(kalan), int(mukerrer)))
    sonuclar = ciftleri_birlestir(database.SessionLocal, ciftler, apply=args.apply, kim=args.kim)
    print(ozet_metni(sonuclar, apply=args.apply))
    return 1 if any(s.ret for s in sonuclar) else 0


if __name__ == "__main__":
    sys.exit(main())
