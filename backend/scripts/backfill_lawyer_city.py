#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Avukatların şehrini mevcut adres metninden çıkarır (lawyers.city backfill).

Yönetim panelindeki Şehir alanı yeni eklendi ve boş; ama bilgi zaten adreste
duruyor ("... MERKEZ KİLİS", "... Karatay/Konya"). Bu script adresi Şehirler
referans listesiyle eşleştirip city kolonunu doldurur.

Eşleştirme:
  - Adres ve şehir adları diakritik/büyük-küçük duyarsız normalize edilir
    (party_check ile aynı yardımcılar) — "KILIS" ↔ "Kilis" eşleşir.
  - Kelime sınırı aranır, böylece "İZMİR" içinde geçen "MİR" gibi parçalar eşleşmez.
  - Adreste birden fazla şehir geçiyorsa EN SONDAKİ seçilir: il adı adresin
    sonunda yazılır, "İzmir Caddesi ... ANKARA" gibi durumlarda doğru olan Ankara'dır.
  - Şehri zaten dolu olan avukata dokunulmaz.

Güvenlik:
  - VARSAYILAN DRY-RUN: hiçbir şey yazmaz.
  - Yazmak için `--apply`.
  - Idempotent; eşleşmeyenler raporlanır, elle doldurulur.

Kullanım:
  docker compose exec -T backend python scripts/backfill_lawyer_city.py
  docker compose exec -T backend python scripts/backfill_lawyer_city.py --apply
"""
import argparse
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ modulleri icin

import models  # noqa: E402
from case_matcher import _normalize as _fold_diacritics  # noqa: E402
from database import SessionLocal  # noqa: E402
from managers.reference_lists import refresh_cache  # noqa: E402
from text_utils import turkish_upper  # noqa: E402


def _key(text: str) -> str:
    """Karşılaştırma anahtarı: birleşik işaret temizliği → Türkçe upper → diakritik katlama."""
    if not text:
        return ""
    cleaned = unicodedata.normalize("NFD", text)
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    return _fold_diacritics(turkish_upper(cleaned))


def find_city(address: str, cities: list) -> str:
    """Adreste geçen şehri döner (en sondaki eşleşme kazanır); yoksa None."""
    haystack = _key(address)
    best_name, best_pos = None, -1
    for name in cities:
        needle = _key(name)
        if not needle:
            continue
        for m in re.finditer(rf"(?<![A-Z0-9]){re.escape(needle)}(?![A-Z0-9])", haystack):
            if m.start() > best_pos:
                best_name, best_pos = name, m.start()
    return best_name


def run(apply_changes: bool):
    db = SessionLocal()
    matched, skipped_filled, unmatched = [], 0, []
    try:
        cities = [c.name for c in db.query(models.City).filter(models.City.active.is_(True)).all()]
        lawyers = db.query(models.Lawyer).all()
        print(f"Şehir listesi: {len(cities)} kayıt | Avukat: {len(lawyers)}\n")

        for lw in lawyers:
            if lw.city:
                skipped_filled += 1
                continue
            city = find_city(lw.address or "", cities)
            if city:
                matched.append((lw, city))
            else:
                unmatched.append(lw)

        for lw, city in matched:
            print(f"  {lw.name:32} → {city}")
            if apply_changes:
                lw.city = city

        if apply_changes and matched:
            db.commit()
            refresh_cache("lawyers")

        print("\n" + "=" * 60)
        print(f"Eşleşen: {len(matched)} | Zaten dolu: {skipped_filled} | Eşleşmeyen: {len(unmatched)}")
        if unmatched:
            print("\nAdresten şehir çıkarılamayanlar (panelden elle seçin):")
            for lw in unmatched:
                adres = (lw.address or "").strip()
                print(f"  {lw.name:32} adres: {adres[:55] or '(boş)'}")
        if apply_changes:
            print(f"\n{len(matched)} avukatın şehri yazıldı.")
        else:
            print("\nDRY-RUN — hiçbir şey yazılmadı. Uygulamak için: --apply")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Avukat şehrini adresten çıkarır")
    parser.add_argument("--apply", action="store_true", help="Değişiklikleri veritabanına yaz")
    args = parser.parse_args()
    run(args.apply)
