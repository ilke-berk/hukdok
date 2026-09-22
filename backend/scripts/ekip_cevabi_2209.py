#!/usr/bin/env python3
"""Ekibin 22.09.2026 cevabı (20.09 son durum mailimize) — Ek-1 › A2: iki kartın ayrılması.

Kaynak: `HUKDOK_CELISKI_CEVABI_2026-09-20.xlsx` (48 çelişkili kartın sınıflaması). A2
sınıfı "Ayrı dava — kart BÖLÜNMELİ" iki karttır; ikisinde de bizim DosyaNo köprümüz
birbiriyle ilgisiz iki föyü tek karta bağlamış:

* **D1.D_OZTURK...0001.IDARE.00000** (id-10880 + id-2635): aynı müvekkil ve mahkeme
  (Ankara 8. İdare) ama karşı taraf farklı (Ramazan/Sefa Gündüz ↔ Bilge Gümüş) ve dava
  tarihleri ayrı (17.01.2023 ↔ 30.06.2022); esaslar 2022/2536 ↔ 2022/1453.
* **S4.QUICK......0032.HUKUK.00000** (H-10589 + ARB-16909): farklı müvekkil, farklı karşı
  taraf, farklı şehir — Quick Sigorta · İstanbul 3. Tüketici · 2020/269 ile Dr. Cemal Ünlü ·
  Kayseri Arabuluculuk · 2026/720 ekipte iki ayrı klasördür.

Kartlar id ile DEĞİL föy çiftiyle tanınır (`AYIRMALAR`): kart id'leri prod ile lokalde
farklı olabilir (16.09 ölçümü: 234 kart), föy `sistem_no`su iki ortamda da aynıdır. Çiftin
iki föyü aynı canlı kartta değilse RET.

Adımlar (tek transaction; `--apply` yoksa geri alınır):

1. **Ayırma** — `scripts/birlesik_kart_ayir.karti_ayir` (grup anahtarı tür + esas; kartın
   kendi grubu kalır, öteki grup yeni karta taşınır, `AYRISTIRILAN` ilişkisi, tarihçe).
   Belgeler KALAN kartta kalır (belge koruma şartı).
2. **Taraf temizliği** — ayırma yardımcısı yalnız-ekleme çalışır (`_taraflari_yaz`), kalan
   kartta taşınan föyün tarafları kalırdı (Quick Sigorta kartında Dr. Cemal Ünlü). Bu adım
   YALNIZ bu kartlarda: taşınan föylerin ham satırından gelen ve kalan föylerin ham
   satırında geçmeyen taraf satırları silinir; belge (`case_documents.case_party_id`) ya da
   föy (`case_foys.case_party_id`) bağı olan satıra DOKUNULMAZ (ATLANDI). Tarihçe `taraf`.

    docker compose exec -T backend python scripts/ekip_cevabi_2209.py            # kuru koşu
    docker compose exec -T backend python scripts/ekip_cevabi_2209.py --apply --kim ilke

İkinci koşu 0 değişiklik: föy çifti artık aynı kartta olmadığından RET döner, yazmaz.
Son durum tazelemesi (Ek-2 master) ayrı script'tir: `scripts/kolayofis_son_durum.py`.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from party_check import normalize_party_key
from scripts import birlesik_kart_ayir as bka
from scripts import hukdok_aktarim as ha
from scripts.ekip_cevabi_1209 import Sonuc

logger = logging.getLogger("EkipCevabi2209")
DEGISTIREN = "ekip_cevabi_2209"
KAYNAK = "ekip cevabı 22.09.2026 Ek-1 › A2 (ayrı dava, kart bölünmeli)"

# (kartta kalan föy, yeni karta gidecek föy, kanıt) — kart iki föyün ortak canlı kartıdır.
AYIRMALAR: Tuple[Tuple[str, str, str], ...] = (
    ("id-10880", "id-2635",
     "aynı müvekkil/mahkeme, karşı taraf ve dava tarihi farklı: 2022/2536 (Gündüz) ↔ 2022/1453 (Gümüş)"),
    ("H-10589", "ARB-16909",
     "farklı müvekkil/karşı taraf/şehir: Quick Sigorta İstanbul 3. Tüketici 2020/269 ↔ Dr. Cemal Ünlü Kayseri Arb. 2026/720"),
)

ADIM_ADLARI = {"ayirma": "Ayırma", "taraf": "Taraf temizliği"}


def _tarihce(db, case_id: int, alan: str, eski, yeni, kim: str, kanit: str) -> None:
    db.add(models.CaseHistory(
        case_id=case_id, field_name=alan,
        old_value=None if eski is None else str(eski), new_value=None if yeni is None else str(yeni),
        changed_by=DEGISTIREN, source=f"{KAYNAK} ({kim}): {kanit}"[:300],
    ))


def _ortak_kart(db, kalan_foy: str, giden_foy: str) -> Tuple[Optional[models.Case], str]:
    foyler = {f.sistem_no: f for f in db.query(models.CaseFoy)
              .filter(models.CaseFoy.sistem_no.in_([kalan_foy, giden_foy])).all()}
    eksik = [s for s in (kalan_foy, giden_foy) if s not in foyler]
    if eksik:
        return None, f"föy bizde yok: {', '.join(eksik)}"
    if foyler[kalan_foy].case_id != foyler[giden_foy].case_id:
        return None, (f"föyler zaten ayrı kartlarda: {kalan_foy} #{foyler[kalan_foy].case_id}, "
                      f"{giden_foy} #{foyler[giden_foy].case_id}")
    kart = db.get(models.Case, foyler[kalan_foy].case_id)
    if kart is None or kart.deleted_at is not None:
        return None, "kart yok ya da silinmiş"
    return kart, ""


def _foy_taraf_anahtarlari(foyler: Sequence[models.CaseFoy]) -> Set[str]:
    """Föylerin ham satırlarındaki bütün taraf adlarının normalize anahtarları."""
    anahtarlar: Set[str] = set()
    for foy in foyler:
        satir = bka.foy_satiri(foy)
        if satir is None:
            continue
        for kaynak, _tip, _rol in ha.TARAF_SUTUNLARI:
            for ad in ha._taraf_adlari(satir.degerler.get(kaynak)):
                anahtar = normalize_party_key(ad)
                if anahtar:
                    anahtarlar.add(anahtar)
    return anahtarlar


def taraflari_temizle(db, kart: models.Case, giden_sistem_nolar: Sequence[str], *, kim: str, sonuc: Sonuc) -> None:
    kalan_foyler = db.query(models.CaseFoy).filter(models.CaseFoy.case_id == kart.id).all()
    giden_foyler = db.query(models.CaseFoy).filter(models.CaseFoy.sistem_no.in_(list(giden_sistem_nolar))).all()
    gidenler = _foy_taraf_anahtarlari(giden_foyler) - _foy_taraf_anahtarlari(kalan_foyler)
    if not gidenler:
        sonuc.ekle("taraf", f"#{kart.id}", "ATLANDI", "taşınan föye özgü taraf yok")
        return
    for taraf in db.query(models.CaseParty).filter(models.CaseParty.case_id == kart.id).all():
        if normalize_party_key(taraf.name) not in gidenler:
            continue
        hedef = f"#{kart.id} {taraf.name} ({taraf.role})"
        belge_bagi = db.query(models.CaseDocument).filter(models.CaseDocument.case_party_id == taraf.id).count()
        foy_bagi = db.query(models.CaseFoy).filter(models.CaseFoy.case_party_id == taraf.id).count()
        if belge_bagi or foy_bagi:
            sonuc.ekle("taraf", hedef, "ATLANDI", f"bağlı: {belge_bagi} belge, {foy_bagi} föy — dokunulmadı")
            continue
        _tarihce(db, kart.id, "taraf", f"{taraf.name} ({taraf.role})", None, kim,
                 f"taşınan föyün tarafı: {', '.join(giden_sistem_nolar)}")
        db.delete(taraf)
        sonuc.ekle("taraf", hedef, "YAPILDI", "kalan karttan silindi (yeni kartta yazılı)")
    db.flush()


def kartlari_ayir(db, kalemler: Sequence[Tuple[str, str, str]], *, kim: str, sonuc: Sonuc) -> None:
    kullanilan: Dict[str, int] = {}
    for kalan_foy, giden_foy, kanit in kalemler:
        hedef = f"{kalan_foy} | {giden_foy}"
        kart, hata = _ortak_kart(db, kalan_foy, giden_foy)
        if kart is None:
            sonuc.ekle("ayirma", hedef, "RET", hata)
            continue
        kalem = bka.karti_ayir(db, kart.id, kullanilan, kim=kim)
        if kalem.sonuc != "YAPILDI":
            sonuc.ekle("ayirma", f"#{kart.id} {hedef}", kalem.sonuc, f"{kalem.aciklama} — {kanit}")
            continue
        giden: List[str] = [s for _id, _t, sistem_nolar in kalem.yeni_kartlar for s in sistem_nolar]
        if giden_foy not in giden or kalan_foy in giden:
            # Gruplama beklenenin tersine düştüyse yazma: yardımcı zaten savepoint'te,
            # dış transaction sonunda geri alınır.
            raise ValueError(f"#{kart.id}: beklenen ayrım {hedef} değil {giden} — hiçbir şey yazılmadı")
        aciklama = "; ".join(f"→ #{i} {t} ({', '.join(s)})" for i, t, s in kalem.yeni_kartlar)
        sonuc.ekle("ayirma", f"#{kart.id} {kart.tracking_no}", "YAPILDI", f"{aciklama} — {kanit}")
        taraflari_temizle(db, kart, giden, kim=kim, sonuc=sonuc)


def kos(session_factory, *, apply: bool = False, kim: str = DEGISTIREN) -> Sonuc:
    sonuc = Sonuc()
    db = session_factory()
    try:
        kartlari_ayir(db, AYIRMALAR, kim=kim, sonuc=sonuc)
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
    satirlar = ["=" * 78,
                f"Ekip cevabı 22.09 › A2 kart ayırma — {'UYGULANDI' if apply else 'KURU KOŞU'}",
                "=" * 78]
    for adim, ad in ADIM_ADLARI.items():
        y, a, r = (sonuc.sayim(adim, s) for s in ("YAPILDI", "ATLANDI", "RET"))
        satirlar.append(f"  {ad:18} {y:3} yapıldı · {a:3} atlandı · {r:3} ret")
    satirlar.append("  " + "-" * 74)
    satirlar.extend(f"  {k.sonuc:7} [{k.adim}] {k.hedef}: {k.aciklama}" for k in sonuc.kalemler)
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Ekip cevabı 22.09 › A2: iki kartın ayrılması")
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
