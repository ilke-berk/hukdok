"""Belge envanteri — aktarım yazma yolunun BELGE KORUMA kanıtı (G064).

**Kullanıcı şartı (18.08):** mevcut kartlarda işlenmiş belgeler (`case_documents`)
vardır; HUKDOK aktarımı onlara DOKUNMAZ. Şartın tehlikesi teoride değil şemada:
`CaseDocument.case_party_id` FK'sı `ondelete="SET NULL"` (models.py:770) — bir
kartın taraflarını toptan silip yeniden yazan bir aktarım, belge-taraf bağını
HATA VERMEDEN koparır. Sessiz kayıp, gürültülü kayıptan pahalıdır.

Bu modül o sessizliği ölçülebilir kılar: koşu öncesi ve sonrası aynı işlem
içinde anlık görüntü alınır, fark ≠ 0 ise aktarım kendini geri alır (kapı
`scripts/hukdok_aktarim.py`da; burası ölçüm, karar değil).

Neden **imza** (sha256) — satır listesi değil: prod'da on binlerce belge var,
soru ise tek cümlelik ("bir bağ kımıldadı mı?"). İmza sabit bellekle cevap
verir; SAYIMLAR ise hangi boyutun kımıldadığını söyler. İkisi birlikte
sayımların yakalayamadığı sınıfı da yakalar: iki belgenin taraf bağı
BİRBİRİYLE yer değiştirirse sayımlar aynı kalır, imza değişir.

Salt okunurdur — hiçbir tabloya yazmaz, commit etmez.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import models

# `case_ids` verildiğinde IN listesi parça boyu (foy_map._CHUNK gerekçesi:
# tek dev IN listesi hem sürücünün parametre sınırını hem planlayıcıyı zorlar).
_PARCA = 1000

# Karşılaştırmaya giren alanlar; `bag_imzasi` ayrı ele alınır (aşağıda).
SAYIM_ALANLARI: Tuple[str, ...] = (
    "toplam", "karta_bagli", "tarafa_bagli", "arsivli", "silinmis",
)


@dataclass(frozen=True)
class BelgeEnvanteri:
    """Belge bağlarının anlık görüntüsü.

    `toplam` belge sayısı; `karta_bagli`/`tarafa_bagli` FK'ların dolu olduğu
    satır sayısı (SET NULL tuzağının doğrudan göstergesi); `arsivli`
    SharePoint URL'i yazılmış belgeler; `silinmis` soft-delete edilmişler
    (aktarım bir belgeyi soft-delete ederse de fark verir); `bag_imzasi` dört
    kolonun satır satır özeti.
    """
    toplam: int
    karta_bagli: int
    tarafa_bagli: int
    arsivli: int
    silinmis: int
    bag_imzasi: str


def snapshot(db, case_ids: Optional[Iterable[int]] = None) -> BelgeEnvanteri:
    """`case_documents` anlık görüntüsü — `case_ids` verilirse yalnız o kartlar.

    Aynı OTURUMDAN çağrılmalıdır: aktarım henüz commit etmemişken ölçüm
    yapılabilsin diye (kapı, hasarın kalıcı olmasından ÖNCE ölçer). İmza
    sırası `id` iledir; sıra değişirse imza da değişirdi.
    """
    ozet = hashlib.sha256()
    toplam = karta_bagli = tarafa_bagli = arsivli = silinmis = 0

    for belge_id, case_id, party_id, url, deleted_at in _satirlar(db, case_ids):
        toplam += 1
        if case_id is not None:
            karta_bagli += 1
        if party_id is not None:
            tarafa_bagli += 1
        if url:
            arsivli += 1
        if deleted_at is not None:
            silinmis += 1
        ozet.update(
            "{}|{}|{}|{}|{}\n".format(
                belge_id,
                "" if case_id is None else case_id,
                "" if party_id is None else party_id,
                url or "",
                0 if deleted_at is None else 1,
            ).encode("utf-8")
        )

    return BelgeEnvanteri(
        toplam=toplam,
        karta_bagli=karta_bagli,
        tarafa_bagli=tarafa_bagli,
        arsivli=arsivli,
        silinmis=silinmis,
        bag_imzasi=ozet.hexdigest(),
    )


def diff(once: BelgeEnvanteri, sonra: BelgeEnvanteri) -> Dict[str, Tuple[Any, Any]]:
    """Değişen alanlar: {alan: (önce, sonra)} — BOŞ SÖZLÜK = envanter denk."""
    alanlar = (*SAYIM_ALANLARI, "bag_imzasi")
    return {
        ad: (getattr(once, ad), getattr(sonra, ad))
        for ad in alanlar
        if getattr(once, ad) != getattr(sonra, ad)
    }


def denk(once: BelgeEnvanteri, sonra: BelgeEnvanteri) -> bool:
    """İki anlık görüntü birebir aynı mı? (kapının tek soruşu)"""
    return not diff(once, sonra)


def bicimle(fark: Dict[str, Tuple[Any, Any]]) -> str:
    """Farkı insana okunur tek metne çevirir (rapor + log için)."""
    if not fark:
        return "belge envanteri DENK"
    satirlar = ["belge envanteri DENK DEĞİL:"]
    for ad, (once, sonra) in fark.items():
        if ad == "bag_imzasi":
            satirlar.append(f"  bag_imzasi: {str(once)[:12]}… → {str(sonra)[:12]}…")
        else:
            satirlar.append(f"  {ad}: {once} → {sonra} ({sonra - once:+d})")
    return "\n".join(satirlar)


def _satirlar(db, case_ids: Optional[Iterable[int]]) -> Iterable[Any]:
    """(id, case_id, case_party_id, sharepoint_url, deleted_at) satırları.

    Filtresiz çağrıda akış hâlinde okunur (`yield_per`) — tüm tabloyu ORM
    nesnesi olarak hydrate etmenin anlamı yok. Filtreli çağrıda parçalar
    birleştikten SONRA id'ye göre sıralanır: imza sırası parçalanmaya
    dayanmamalı.
    """
    sorgu = db.query(
        models.CaseDocument.id,
        models.CaseDocument.case_id,
        models.CaseDocument.case_party_id,
        models.CaseDocument.sharepoint_url,
        models.CaseDocument.deleted_at,
    )
    if case_ids is None:
        return sorgu.order_by(models.CaseDocument.id).yield_per(_PARCA)

    kimlikler = sorted({int(c) for c in case_ids})
    toplanan: List[Any] = []
    for i in range(0, len(kimlikler), _PARCA):
        toplanan.extend(
            sorgu.filter(models.CaseDocument.case_id.in_(kimlikler[i:i + _PARCA])).all()
        )
    toplanan.sort(key=lambda satir: satir[0])
    return toplanan
