#!/usr/bin/env python3
"""Ekibin 26.09 + 01.10.2026 iletilerinde paketin YAPMADIĞI kart işleri.

Kaynak: 26.09 iletisi (12–14. maddeler) + 01.10 iletisi (16–17. maddeler). Teslim paketi
(`hukdok_aktarim`) föy alanlarını yazar ama kart birleştirmez/kapatmaz, aşama satırı silmez,
mevcut taraf satırını yeniden adlandırmaz (belge koruma şartı) ve paket hücresi boş gelen
mahkemeyi dolduramaz. Bu script o boşlukları ekibin yazdığı kanıtla kapatır.

Adımlar (tek transaction; `--apply` yoksa geri alınır):

1. **Birleştirme (26.09 §14):** #665 (id-841, İstanbul 5. İdare 2017/849 → 2021/1921) ile #13363
   aynı dava; #665 #13363'e birleştirilir (`mukerrer_kart_birlestir.birlestir`, müvekkil ayrımı
   izinli — kartlar müvekkil başına açılmıştı). 2017/849 esas tarihçesinde zaten var.
2. **Föy taşıma + kapatma (26.09 §13):** id-5126'nın davası (İstanbul 13. İdare 2021/1880) #13360'ta;
   föy oraya taşınır (`ekip_cevabi_2309._foy_gecir` deseni), föysüz ve belgesiz kalan #3146 kapatılır.
3. **Yabancı künye (26.09 §12, #29):** Beykoz 1. Asliye Hukuk 2013/376 kartında yıllardır başka
   davanın (Yozgat İdare 2013/1052) temyiz (Danıştay 15. Daire 2016/1086 · 16.05.2016 onama) ve
   karar düzeltme satırları duruyordu; ekip bizde temizledi, pakette boş geliyor. Satırlar
   `stage_decisions.delete_stage_decision` ile silinir (BELGE/UYAP damgalı satır RET).
4. **Mahkeme (01.10 §17, #2909):** iletide "Antalya 2. Tüketici Mahkemesi 2025/252" yazıyor ama
   paketin föy satırında (H-4922) "Yerel Mahkeme" boş geldi; kart ve güncel YEREL aşama satırı
   boşsa doldurulur (dolu ve farklıysa RET — elle bakılır).
5. **Sigortalı (01.10 §16):** H-6677'de "DR.YUNUS ARAZ" sigortalı satırı "Yusuf Araz Dr." olur
   (kararlardaki ad); H-10298'e sigortalı satırı eklenir (önceden boştu). Aktarım taraf satırını
   yalnız ekler, bu yüzden burada.
6. **Dava konusu kısaltması (26.09 §14):** "… (Tıbbi Kötü Uygulama Sigorta Poliçesinden Kaynaklanan)"
   → "… (Tıbbi Kötü Uygulama)" — kısa ad `case_subjects`te olmalı (yoksa RET); kullanıcı imzalı
   `subject` tarihçesi olan kart KORUNDU.

Kartlar id ile değil FÖY anahtarıyla (SistemNo) bulunur — prod/lokal kart id'leri farklı olabilir.

    docker compose exec -T backend python scripts/ekip_cevabi_2609.py              # kuru koşu
    docker compose exec -T backend python scripts/ekip_cevabi_2609.py --apply --kim ilke

İkinci koşu 0 değişiklik: birleşen kart silinmiş (ATLANDI), föy hedefte (ATLANDI), satır yok
(ATLANDI), mahkeme dolu (ATLANDI), ad doğru (ATLANDI), uzun konu kalmadı (ATLANDI).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

import models
from managers import case_manager, stage_decisions
from scripts import mukerrer_kart_birlestir as mb
from scripts.ekip_cevabi_1209 import Sonuc
from scripts.ekip_cevabi_2309 import _canli_kart, _foy, _foy_gecir, taraflari_temizle

logger = logging.getLogger("EkipCevabi2609")
DEGISTIREN = "ekip_cevabi_2609"
KAYNAK = "ekip iletisi 26.09 + 01.10.2026"

# (kalan kartın föyü, sönecek kartın föyü, kanıt)
BIRLESTIRMELER: Tuple[Tuple[str, str, str], ...] = (
    ("id-842", "id-841",
     "26.09 §14: İstanbul 5. İdare 2017/849 kararı kaldırıldıktan sonra dava 2021/1921 esasıyla "
     "yeniden görülüyor — id-841 aynı davanın föyü"),
)
# (taşınacak föy, hedef kartın föyü, kanıt) — kaynak kart föysüz+belgesiz kalırsa kapatılır.
TASIMALAR: Tuple[Tuple[str, str, str], ...] = (
    ("id-5126", "id-8855",
     "26.09 §13: id-5126 esas düzeltmesi '2021/' → 2021/1880; dava İstanbul 13. İdare 2021/1880 "
     "kartında görülüyor, eski kart kapatılabilir"),
)
# (kartın föyü, aşama, eşleşme alanları {alan: beklenen | None=boş}, kanıt)
ASAMA_SILMELERI: Tuple[Tuple[str, str, Dict[str, Optional[str]], str], ...] = (
    ("H-5614", "TEMYIZ", {"mahkeme": "Danıştay 15. Daire", "esas_no": "2016/1086"},
     "26.09 §12: Yozgat İdare 2013/1052 davasının Danıştay onaması — Beykoz davasına ait değil"),
    ("H-5614", "KARAR_DUZELTME", {"mahkeme": None, "esas_no": None, "karar_no": None},
     "26.09 §12: aynı yabancı davanın karar düzeltme reddi — Beykoz davasında bilinen karar yok"),
)
# (kartın föyü, mahkeme, kanıt) — kart ve güncel YEREL aşama satırı BOŞSA yazılır.
MAHKEME_DUZELTMELERI: Tuple[Tuple[str, str, str], ...] = (
    ("H-4922", "Antalya 2. Tüketici Mahkemesi",
     "01.10 §17: Yargıtay bozması sonrası dava Antalya 2. Tüketici 2025/252 — paketin föy satırında "
     "Yerel Mahkeme boş geldi"),
)
# (kartın föyü, mevcut sigortalı adı | None=yok, doğru ad, kanıt)
SIGORTALI_DUZELTMELERI: Tuple[Tuple[str, Optional[str], str, str], ...] = (
    ("H-6677", "DR.YUNUS ARAZ", "Yusuf Araz Dr.", "01.10 §16: kararlardaki ad Yusuf Araz"),
    ("H-10298", None, "Mustafa Kavurmacı Dr.", "01.10 §16: önceden boştu; kararda Ak Sigorta'nın sigortalısı"),
)
# (uzun yazım, kısa yazım) — bütün canlı kartlar.
DAVA_KONUSU_KISALTMALARI: Tuple[Tuple[str, str], ...] = (
    ("Tazminat (Tıbbi Kötü Uygulama Sigorta Poliçesinden Kaynaklanan)", "Tazminat (Tıbbi Kötü Uygulama)"),
    ("Rücuen Alacak (Tıbbi Kötü Uygulama Sigorta Poliçesinden Kaynaklanan)", "Rücuen Alacak (Tıbbi Kötü Uygulama)"),
)
SIGORTALI_ROLU = "Sigortalı"
# `subject` tarihçesinde kullanıcı SAYILMAYAN imzalar (aktarım, migrasyon, ekip script'leri).
SCRIPT_IMZALARI = frozenset({"hukdok_aktarim", "sistem", "birlesik_kart_ayir", "kartsiz_foy_kart_ac"})

ADIM_ADLARI = {"cift": "Birleştirme", "tasima": "Föy taşıma", "kapatma": "Kart kapatma",
               "taraf": "Taraf temizliği", "asama": "Yabancı künye silme", "mahkeme": "Mahkeme",
               "sigortali": "Sigortalı adı", "konu": "Dava konusu kısaltma"}


def _tarihce(db, case_id: int, alan: str, eski, yeni, kim: str, kanit: str) -> None:
    db.add(models.CaseHistory(
        case_id=case_id, field_name=alan,
        old_value=None if eski is None else str(eski), new_value=None if yeni is None else str(yeni),
        changed_by=DEGISTIREN, source=f"{KAYNAK} ({kim}): {kanit}"[:300],
    ))


def _kullanici_kaydi_var(db, case_id: int, alan: str) -> bool:
    """Alanda script/aktarım dışı imzalı tarihçe var mı (kullanıcı düzeltmesi korunur)."""
    for h in db.query(models.CaseHistory).filter(models.CaseHistory.case_id == case_id,
                                                 models.CaseHistory.field_name == alan).all():
        kaynak = (h.source or "")
        if kaynak.startswith("HUKDOK_TESLIM") or kaynak.startswith("ekip ") or kaynak.startswith("ekip_"):
            continue
        if (h.changed_by or "") in SCRIPT_IMZALARI or (h.changed_by or "").startswith("ekip_cevabi"):
            continue
        return True
    return False


# ─── Adım 1: birleştirme ─────────────────────────────────────────────────────

def ciftleri_birlestir(db, kalemler: Sequence[Tuple[str, str, str]], *, kim: str, sonuc: Sonuc) -> None:
    for kalan_sn, sonen_sn, kanit in kalemler:
        hedef = f"{sonen_sn}'in kartı → {kalan_sn}'in kartı"
        kalan_foy, sonen_foy = _foy(db, kalan_sn), _foy(db, sonen_sn)
        if kalan_foy is None or sonen_foy is None:
            sonuc.ekle("cift", hedef, "RET", "föy bizde yok")
            continue
        kalan = db.get(models.Case, kalan_foy.case_id)
        sonen = db.get(models.Case, sonen_foy.case_id)
        if kalan is None or kalan.deleted_at is not None:
            sonuc.ekle("cift", hedef, "RET", "kalan kart silinmiş")
            continue
        if sonen.id == kalan.id:
            sonuc.ekle("cift", hedef, "ATLANDI", f"zaten birleştirilmiş (#{kalan.id})")
            continue
        with db.begin_nested():
            b = mb.birlestir(db, kalan, sonen, kim=kim, muvekkil_ayrimi=True,
                             tarihce_alani="ekip_cevabi_2609_birlestirme",
                             sebep_etiketi=f"{KAYNAK} ›14 aynı dava")
        if b.ret:
            sonuc.ekle("cift", hedef, "RET", f"{b.ret} ({kanit})")
        else:
            sonuc.ekle("cift", f"#{sonen.id} {sonen.tracking_no} → #{kalan.id} {kalan.tracking_no}",
                       "YAPILDI", f"{b.tasinan} — {kanit}")


# ─── Adım 2: föy taşıma + kaynak kartı kapatma ───────────────────────────────

def _kapat(db, kart: models.Case, sebep: str, kim: str, sonuc: Sonuc) -> None:
    hedef = f"#{kart.id} {kart.tracking_no}"
    if kart.deleted_at is not None:
        sonuc.ekle("kapatma", hedef, "ATLANDI", "zaten kapalı")
        return
    foy = db.query(models.CaseFoy).filter(models.CaseFoy.case_id == kart.id).count()
    belge = db.query(models.CaseDocument).filter(models.CaseDocument.case_id == kart.id).count()
    if foy or belge:
        sonuc.ekle("kapatma", hedef, "RET", f"{foy} föy / {belge} belge var — insan kararı")
        return
    kart.deleted_at = func.now()
    kart.deleted_by = kim
    kart.delete_reason = f"{KAYNAK}: {sebep}"[:500]
    kart.active = False
    _tarihce(db, kart.id, "kapatma", kart.tracking_no, None, kim, sebep)
    db.flush()
    case_manager.refresh_missing_required(db, kart)
    sonuc.ekle("kapatma", hedef, "YAPILDI", sebep)


def foyleri_tasi(db, kalemler: Sequence[Tuple[str, str, str]], *, kim: str, sonuc: Sonuc) -> None:
    for giden_sn, hedef_sn, kanit in kalemler:
        hedef_ad = f"{giden_sn} → {hedef_sn}'in kartı"
        giden_foy = _foy(db, giden_sn)
        kaynak, hedef = _canli_kart(db, giden_foy), _canli_kart(db, _foy(db, hedef_sn))
        if giden_foy is None or kaynak is None or hedef is None:
            sonuc.ekle("tasima", hedef_ad, "RET", "föy bizde yok ya da kartı silinmiş")
            continue
        if kaynak.id == hedef.id:
            sonuc.ekle("tasima", hedef_ad, "ATLANDI", f"zaten #{hedef.id}'de")
            continue
        _foy_gecir(db, giden_foy, hedef, kim=kim, kanit=kanit)
        case_manager.refresh_missing_required(db, kaynak)
        case_manager.refresh_missing_required(db, hedef)
        sonuc.ekle("tasima", hedef_ad, "YAPILDI", f"#{kaynak.id} → #{hedef.id} {hedef.tracking_no} — {kanit}")
        taraflari_temizle(db, kaynak, [giden_sn], kim=kim, sonuc=sonuc)
        _kapat(db, kaynak, f"föyü {giden_sn} #{hedef.id}'e taşındı, kart föysüz kaldı", kim, sonuc)


# ─── Adım 3: yabancı künye silme ─────────────────────────────────────────────

def _eslesen_satirlar(db, kart: models.Case, stage: str,
                      alanlar: Dict[str, Optional[str]]) -> List[models.CaseStageDecision]:
    satirlar = db.query(models.CaseStageDecision).filter(
        models.CaseStageDecision.case_id == kart.id, models.CaseStageDecision.stage == stage).all()
    return [s for s in satirlar
            if all((getattr(s, alan) or None) == (beklenen or None) for alan, beklenen in alanlar.items())]


def asamalari_sil(db, kalemler: Sequence[Tuple[str, str, Dict[str, Optional[str]], str]], *,
                  kim: str, sonuc: Sonuc) -> None:
    for foy_sn, stage, alanlar, kanit in kalemler:
        tanim = ", ".join(f"{a}={b or '∅'}" for a, b in alanlar.items())
        kart = _canli_kart(db, _foy(db, foy_sn))
        if kart is None:
            sonuc.ekle("asama", f"{foy_sn} {stage}", "RET", "föy bizde yok ya da kartı silinmiş")
            continue
        hedef = f"#{kart.id} {stage} [{tanim}]"
        satirlar = _eslesen_satirlar(db, kart, stage, alanlar)
        if not satirlar:
            sonuc.ekle("asama", hedef, "ATLANDI", "eşleşen satır yok (zaten silinmiş)")
            continue
        for satir in satirlar:
            if stage_decisions.is_protected(satir):
                sonuc.ekle("asama", hedef, "RET", f"satır {satir.dogrulama_durumu} damgalı — belgeye dayanıyor")
                continue
            ozet = (f"sira={satir.sira_no} {satir.mahkeme or '∅'} {satir.esas_no or '∅'} "
                    f"K:{satir.karar_no or '∅'} {satir.karar_tarihi or '∅'} {satir.karar_durumu or '∅'}")
            if stage_decisions.delete_stage_decision(db, kart, satir.id):
                _tarihce(db, kart.id, f"asama_{stage.lower()}", ozet, None, kim, kanit)
                sonuc.ekle("asama", hedef, "YAPILDI", f"{ozet} — {kanit}")
        db.flush()
        case_manager.refresh_missing_required(db, kart)


# ─── Adım 4: mahkeme ─────────────────────────────────────────────────────────

def mahkemeleri_doldur(db, kalemler: Sequence[Tuple[str, str, str]], *, kim: str, sonuc: Sonuc) -> None:
    for foy_sn, mahkeme, kanit in kalemler:
        kart = _canli_kart(db, _foy(db, foy_sn))
        if kart is None:
            sonuc.ekle("mahkeme", foy_sn, "RET", "föy bizde yok ya da kartı silinmiş")
            continue
        hedef = f"#{kart.id} {kart.tracking_no}"
        if (kart.court or "").strip() == mahkeme:
            sonuc.ekle("mahkeme", hedef, "ATLANDI", "zaten dolu")
        elif kart.court:
            sonuc.ekle("mahkeme", hedef, "RET", f"kartta farklı mahkeme {kart.court!r} — elle bakılmalı")
            continue
        else:
            _tarihce(db, kart.id, "court", kart.court, mahkeme, kim, kanit)
            kart.court = mahkeme
            sonuc.ekle("mahkeme", hedef, "YAPILDI", f"∅ → {mahkeme!r} — {kanit}")
        yerel = stage_decisions.latest_stage_decision(db, kart.id, "YEREL")
        if yerel is not None and not yerel.mahkeme and not stage_decisions.is_protected(yerel):
            # update_stage_decision içeriğin TAMAMINI yazar (verilmeyen alan = boş):
            # mevcut alanlar aynen taşınır, yalnız mahkeme değişir; damga korunur.
            icerik = {alan: getattr(yerel, alan) for alan in stage_decisions.CONTENT_FIELDS}
            icerik["mahkeme"] = mahkeme
            stage_decisions.update_stage_decision(db, kart, yerel, **icerik,
                                                  dogrulama_durumu=yerel.dogrulama_durumu,
                                                  source=f"{DEGISTIREN} ({kim})")
            _tarihce(db, kart.id, "asama_yerel", f"sira={yerel.sira_no} mahkeme=∅",
                     f"sira={yerel.sira_no} mahkeme={mahkeme}", kim, kanit)
            sonuc.ekle("mahkeme", f"{hedef} YEREL#{yerel.sira_no}", "YAPILDI", f"aşama satırı mahkeme ∅ → {mahkeme!r}")
        db.flush()
        case_manager.refresh_missing_required(db, kart)


# ─── Adım 5: sigortalı ───────────────────────────────────────────────────────

def sigortalilari_duzelt(db, kalemler: Sequence[Tuple[str, Optional[str], str, str]], *,
                         kim: str, sonuc: Sonuc) -> None:
    for foy_sn, mevcut_ad, dogru_ad, kanit in kalemler:
        kart = _canli_kart(db, _foy(db, foy_sn))
        if kart is None:
            sonuc.ekle("sigortali", foy_sn, "RET", "föy bizde yok ya da kartı silinmiş")
            continue
        hedef = f"#{kart.id} {kart.tracking_no}"
        sigortalilar = (db.query(models.CaseParty)
                        .filter(models.CaseParty.case_id == kart.id, models.CaseParty.role == SIGORTALI_ROLU)
                        .order_by(models.CaseParty.id).all())
        if any((p.name or "").strip() == dogru_ad for p in sigortalilar):
            sonuc.ekle("sigortali", hedef, "ATLANDI", f"{dogru_ad!r} zaten sigortalı")
            continue
        if mevcut_ad is not None:
            eski = [p for p in sigortalilar if (p.name or "").strip() == mevcut_ad]
            if not eski:
                sonuc.ekle("sigortali", hedef, "RET", f"{mevcut_ad!r} sigortalı satırı yok — elle bakılmalı")
                continue
            for p in eski:
                _tarihce(db, kart.id, "taraf", f"{p.name} ({p.role})", f"{dogru_ad} ({p.role})", kim, kanit)
                p.name = dogru_ad
            sonuc.ekle("sigortali", hedef, "YAPILDI", f"{mevcut_ad!r} → {dogru_ad!r} — {kanit}")
        else:
            if sigortalilar:
                sonuc.ekle("sigortali", hedef, "RET",
                           f"başka sigortalı var: {[p.name for p in sigortalilar]} — elle bakılmalı")
                continue
            db.add(models.CaseParty(case_id=kart.id, name=dogru_ad, role=SIGORTALI_ROLU, party_type="THIRD",
                                    client_id=None))
            _tarihce(db, kart.id, "taraf", None, f"{dogru_ad} ({SIGORTALI_ROLU})", kim, kanit)
            sonuc.ekle("sigortali", hedef, "YAPILDI", f"∅ → {dogru_ad!r} — {kanit}")
        db.flush()


# ─── Adım 6: dava konusu kısaltması ──────────────────────────────────────────

def konulari_kisalt(db, kalemler: Sequence[Tuple[str, str]], *, kim: str, sonuc: Sonuc) -> None:
    for uzun, kisa in kalemler:
        if db.query(models.CaseSubject).filter(models.CaseSubject.name == kisa).count() == 0:
            sonuc.ekle("konu", kisa, "RET", "kısa ad dava konusu listesinde yok — önce listeye eklenmeli")
            continue
        kartlar = (db.query(models.Case)
                   .filter(models.Case.deleted_at.is_(None), models.Case.subject == uzun)
                   .order_by(models.Case.id).all())
        if not kartlar:
            sonuc.ekle("konu", uzun, "ATLANDI", "bu yazımda canlı kart yok")
            continue
        for kart in kartlar:
            hedef = f"#{kart.id} {kart.tracking_no}"
            if _kullanici_kaydi_var(db, kart.id, "subject"):
                sonuc.ekle("konu", hedef, "KORUNDU", "kullanıcı imzalı dava konusu tarihçesi var")
                continue
            _tarihce(db, kart.id, "subject", uzun, kisa, kim, "26.09 §14 dava konusu kısaltması")
            kart.subject = kisa
            sonuc.ekle("konu", hedef, "YAPILDI", f"{uzun!r} → {kisa!r}")
        db.flush()


# ─── Koşu ────────────────────────────────────────────────────────────────────

def kos(session_factory, *, apply: bool = False, kim: str = DEGISTIREN) -> Sonuc:
    sonuc = Sonuc()
    db = session_factory()
    try:
        ciftleri_birlestir(db, BIRLESTIRMELER, kim=kim, sonuc=sonuc)
        foyleri_tasi(db, TASIMALAR, kim=kim, sonuc=sonuc)
        asamalari_sil(db, ASAMA_SILMELERI, kim=kim, sonuc=sonuc)
        mahkemeleri_doldur(db, MAHKEME_DUZELTMELERI, kim=kim, sonuc=sonuc)
        sigortalilari_duzelt(db, SIGORTALI_DUZELTMELERI, kim=kim, sonuc=sonuc)
        konulari_kisalt(db, DAVA_KONUSU_KISALTMALARI, kim=kim, sonuc=sonuc)
        if apply:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return sonuc


def ozet_metni(sonuc: Sonuc, *, apply: bool) -> str:
    satirlar = ["=" * 78, f"Ekip iletileri 26.09 + 01.10 — kart işleri — {'UYGULANDI' if apply else 'KURU KOŞU'}",
                "=" * 78]
    for adim, ad in ADIM_ADLARI.items():
        y, a, r, k = (sonuc.sayim(adim, s) for s in ("YAPILDI", "ATLANDI", "RET", "KORUNDU"))
        satirlar.append(f"  {ad:22} {y:3} yapıldı · {a:3} atlandı · {r:3} ret · {k:3} korundu")
    satirlar.append("  " + "-" * 74)
    satirlar.extend(f"  {k.sonuc:7} [{k.adim}] {k.hedef}: {k.aciklama}" for k in sonuc.kalemler
                    if k.adim != "konu" or k.sonuc != "YAPILDI")
    konu = sonuc.sayim("konu", "YAPILDI")
    if konu:
        satirlar.append(f"  YAPILDI [konu] {konu} kart kısa ada çekildi (tek tek tarihçede)")
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Ekip iletileri 26.09 + 01.10: paketin yapmadığı kart işleri")
    ayristirici.add_argument("--apply", action="store_true", help="yazar (yoksa kuru koşu)")
    ayristirici.add_argument("--kim", default=DEGISTIREN, help="tarihçe imzası")
    args = ayristirici.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    sonuc = kos(SessionLocal, apply=args.apply, kim=args.kim)
    print(ozet_metni(sonuc, apply=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
