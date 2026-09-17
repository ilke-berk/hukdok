#!/usr/bin/env python3
""""İdari Yargı" dava türünü "İdare"ye birleştirir — veri ekibine 17.09.2026 cevabında verilen söz.

**Neden:** dava açma sihirbazı (`frontend/src/lib/caseIntake.ts::normalizeFileType`) Gemini'nin
"İdari" etiketini "İdari Yargı" türüne çeviriyordu; ofis dosya numarasının tür bloğu da buradan
`IDARI` çıkıyordu. Paket ve elle açılan kartların türü ise "İdare" (`IDARE`). İki ad aynı şeyi
anlatır — ölçüm 17.09 (lokal = prod kopyası): "İdari Yargı" hiçbir yerde yargı BİRİMİ değildir;
`services/judicial_unit.PATTERNS` üçüncü sütunu ve `court_types.parent_code` da dava türüdür.
Kod tarafı aynı commit'te: sihirbaz "İdare" üretir, seed "İdari Yargı"yı artık kurmaz.

Adımlar (tek transaction; `--apply` yoksa sonunda geri alınır, rapor yine basılır):

1. **Kartlar:** `cases.file_type == "İdari Yargı"` olan HER kart (silinmişler dahil) "İdare" olur,
   tarihçe satırı yazılır. **Ofis dosya numarasına (`tracking_no`) DOKUNULMAZ** — mevcut
   `…IDARI…` numaraları arşiv klasör/dosya adlarında yaşar.
2. **Mahkeme türleri:** `court_types.parent_code == "İdari Yargı"` satırı, "İdare" altında aynı
   adlı satır varsa silinir (kopya; `cases.sub_type` adı taşır, kod değil — kopan bağ yok),
   yoksa üst türü "İdare"ye taşınır.
3. **Dava türü listesi:** `file_types` "İdari Yargı" satırı silinir (bağımlıları 1-2'de taşındı).

Serbest metinlere (`karar_aciklama`, belge AI özeti vb.) dokunulmaz. İkinci koşu 0 değişiklik:
eski adı taşıyan satır kalmaz.

    docker compose exec -T backend python scripts/idari_yargi_birlestir.py                # kuru koşu
    docker compose exec -T backend python scripts/idari_yargi_birlestir.py --apply --kim ilke
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from scripts.ekip_cevabi_1209 import Sonuc
from services.judicial_unit import normalize_court

logger = logging.getLogger("IdariYargiBirlestir")
DEGISTIREN = "idari_yargi_birlestir"
KAYNAK = "İdari Yargı → İdare birleştirmesi (ekibe söz 17.09.2026)"
ESKI = "İdari Yargı"
YENI = "İdare"

ADIM_ADLARI = {"kart": "1. Kart dava türü", "mahkeme": "2. Mahkeme türü", "tur": "3. Dava türü listesi"}


def kartlari_tasi(db, *, kim: str, sonuc: Sonuc) -> None:
    for kart in db.query(models.Case).filter(models.Case.file_type == ESKI).order_by(models.Case.id):
        kart.file_type = YENI
        db.add(models.CaseHistory(
            case_id=kart.id, field_name="file_type", old_value=ESKI, new_value=YENI,
            changed_by=DEGISTIREN, source=f"{KAYNAK} ({kim})"[:300],
        ))
        durum = "silinmiş kart" if kart.deleted_at is not None else "aktif kart"
        sonuc.ekle("kart", f"#{kart.id} {kart.tracking_no}", "YAPILDI", f"{ESKI} → {YENI} ({durum}, ofis no aynı)")
    db.flush()


def mahkeme_turlerini_tasi(db, *, sonuc: Sonuc) -> None:
    yenide = {
        normalize_court(r.name)
        for r in db.query(models.CourtType).filter(models.CourtType.parent_code == YENI)
    }
    for satir in db.query(models.CourtType).filter(models.CourtType.parent_code == ESKI).order_by(models.CourtType.id):
        if normalize_court(satir.name) in yenide:
            sonuc.ekle("mahkeme", f"{satir.code} {satir.name}", "YAPILDI", f"silindi ({YENI} altında aynısı var)")
            db.delete(satir)
        else:
            satir.parent_code = YENI
            yenide.add(normalize_court(satir.name))
            sonuc.ekle("mahkeme", f"{satir.code} {satir.name}", "YAPILDI", f"üst tür {ESKI} → {YENI}")
    db.flush()


def tur_satirini_sil(db, *, sonuc: Sonuc) -> None:
    for satir in db.query(models.FileType).filter((models.FileType.code == ESKI) | (models.FileType.name == ESKI)):
        if db.query(models.FileType).filter(models.FileType.name == YENI).first() is None:
            sonuc.ekle("tur", satir.code, "RET", f"{YENI} satırı yok — silinmedi")
            continue
        sonuc.ekle("tur", satir.code, "YAPILDI", "silindi")
        db.delete(satir)
    db.flush()


def kos(session_factory, *, apply: bool = False, kim: str = DEGISTIREN) -> Sonuc:
    sonuc = Sonuc()
    db = session_factory()
    try:
        kartlari_tasi(db, kim=kim, sonuc=sonuc)
        mahkeme_turlerini_tasi(db, sonuc=sonuc)
        tur_satirini_sil(db, sonuc=sonuc)
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
    satirlar = ["=" * 78, f"{ESKI} → {YENI} birleştirmesi — {'UYGULANDI' if apply else 'KURU KOŞU'}", "=" * 78]
    for adim, ad in ADIM_ADLARI.items():
        y, r = sonuc.sayim(adim, "YAPILDI"), sonuc.sayim(adim, "RET")
        satirlar.append(f"  {ad:26} {y:4} yapıldı · {r:3} ret")
    if sonuc.kalemler:
        satirlar.append("  " + "-" * 74)
        satirlar.extend(f"  {k.sonuc:7} [{k.adim}] {k.hedef}: {k.aciklama}" for k in sonuc.kalemler)
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description=f"{ESKI} → {YENI} dava türü birleştirmesi")
    ayristirici.add_argument("--apply", action="store_true", help="yazar (yoksa kuru koşu)")
    ayristirici.add_argument("--kim", default=DEGISTIREN, help="tarihçe imzası")
    args = ayristirici.parse_args(argv)

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    sonuc = kos(SessionLocal, apply=args.apply, kim=args.kim)
    print(ozet_metni(sonuc, apply=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
