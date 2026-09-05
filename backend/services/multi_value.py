"""Çok değerli hücre sözleşmesi (G124) — TEK ayraç, TEK yazım.

Teslim paketinin beş tasnif sütunu (Tıbbi Süreç · Tıbbi Olay · İddia Edilen
Kusur · Hastada Oluşan Zarar · Uygulanan Yöntem) bir hücrede birden çok
değer taşır ("Komplikasyon Yönetimi ; Takip Eksikliği"). Kartta aynı metin
kolonunda saklanır; ayraç noktalı virgüldür — virgül ayraç DEĞİLDİR
(değerlerin kendisi virgül içerebilir: "Kaynamama / Yanlış Kaynama").

Bu modül ayırma/birleştirmenin tek yeridir: aktarım (`hukdok_aktarim`),
takip paneli yazma kapısı (`case_manager.validated_multi_list_value`) ve
havuz seed'i (`scripts/deger_havuzu_seed.py`) buradan okur; frontend
karşılığı `frontend/src/lib/multiValue.ts` (aynı ayraç).
"""
from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional

SEPARATOR = " ; "
_SPLIT = re.compile(r"[;\r\n]+")


def split_values(value: Any) -> List[str]:
    """Hücreyi parçalara ayırır: boşluk kırpılır, boş parça ve mükerrer düşer
    (ilk görülen sıra korunur). None/boş → []."""
    if value is None:
        return []
    gorulen: List[str] = []
    for parca in _SPLIT.split(str(value)):
        temiz = " ".join(parca.split())
        if temiz and temiz.casefold() not in {g.casefold() for g in gorulen}:
            gorulen.append(temiz)
    return gorulen


def join_values(values: Iterable[str]) -> Optional[str]:
    """Parçaları kanonik ayraçla birleştirir; boş → None (alan temizlenir)."""
    parcalar = [p for p in (" ".join(str(v).split()) for v in values) if p]
    return SEPARATOR.join(parcalar) if parcalar else None
