#!/usr/bin/env python3
"""Ofis no göçü — tüm kartları karar 023 formatına numaralar (G238).

Format ve kurallar `docs/kararlar/023-ofis-no-formati.md`; numaranın HER parçası
`services/ofis_no`'dan gelir (bu script üretici DEĞİL, yalnız göç sırasını ve kategori
kaynağı zincirini kurar).

**Kuru koşu (varsayılan):** DB'ye HİÇBİR ŞEY yazılmaz; plan bellekte hesaplanır ve rapor
dizinine üç dosya düşer:

* `ofis_no_esleme_<tarih>.csv`  — `case_id, eski, yeni, silinmis, kategori_kaynagi, sigortali_kaynagi`
* `ofis_no_sigortali_eksik_<tarih>.csv` — sigortacı müvekkilli, sigortalısı bulunamayan kartlar
* `ofis_no_ozet_<tarih>.txt`    — kod başına kart sayısı, kaynak dağılımları, `SG` ve müvekkilsiz listeleri

**Kategori kaynağı zinciri** (karar 023 §6), müvekkil başına; ilk dolu basamak kazanır:

1. `clients.category` — tarafın bağlı müvekkil kaydı (`muvekkil_kaydi`); bağ yoksa aynı adlı
   müvekkil kayıtlarının TEK kategorisi (`muvekkil_kaydi_ad` — canlı tahsisin
   `_mevcut_muvekkili_bul` yoluyla aynı mantık)
2. tarafa bağlı, kapsamdaki föyün `muvekkil_tipi` (`foy`)
3. eski numaranın ilk bloğu (`eski_numara`): D1→Doktor, D2→Sağlık Çalışanı, H1→Hasta,
   H2→Özel Hastane, S0-S7→Sigorta (şirket kodu addan; addan çıkmazsa S1/S2/S3/S5/S6/S7 sabit
   koduna, S0/S4 `SG`'ye düşer), X1→ad kuralıyla Kurum/Bireysel
4. hiçbiri yoksa üreticinin ad kuralı (`ad_kurali`)

**Sıra:** müvekkil kodu içinde `opening_date` artan, tarihsizler sonda; eşitlikte `created_at`,
sonra `id`. Zaten yeni formatta olan kart (G236'nın verdiği numara ya da önceki göç) ATLANIR —
numara verildikten sonra değişmez; göçün sırası o kodun en yüksek sırasından devam eder.

**`--apply`:** tek transaction. Müvekkilsiz kart ATLANIR: eski numarasıyla kalır, özet raporda
listelenir (kullanıcı kararı 30.09: lokalde 265 kartın 264'ü birleştirmede sönmüş silinmiş kart,
içleri boş; eski noktalı format yeni tireli formatla çakışamaz). Unique çakışmasın diye iki aşama (`__GOC__<id>` → yeni numara);
`ofis_no_kodu`/`ofis_no_sira` yazılır; her karta `case_history` (`tracking_no`, eski → yeni,
`source='OFIS_NO_GOCU'`); `case_foys.onceki_tracking_no` aynı eşlemeyle çevrilir (eşlemede
olmayan değer kalır, sayısı raporlanır) ve föyün BUGÜNKÜ kartına eski değeri taşıyan bir
`onceki_tracking_no` tarihçe satırı yazılır (eski numarayla arama `case_history.old_value`
kolundan çalışmaya devam etsin); `ofis_no_sayaclari` kod başına en yüksek sıraya çekilir.
Envanter kapısı (kart / silinmiş / föy sayısı önce = sonra, mükerrer yok, her numara desene
uyuyor) tutmazsa ROLLBACK + çıkış 2. İkinci koşu 0 değişiklik.

    docker compose exec -T backend python -m scripts.ofis_no_gocu                      # kuru koşu
    docker compose exec -T backend python -m scripts.ofis_no_gocu --apply --kim ilke   # YALNIZ kullanıcı kararıyla
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import insert, select, text

import models
from services import ofis_no

logger = logging.getLogger("OfisNoGocu")

KAYNAK = "OFIS_NO_GOCU"
DEGISTIREN = "ofis_no_gocu"
GECICI_ONEK = "__GOC__"

#: Karar 023 numara deseni: `<KOD>-<SIRA>[-<SİGORTALI>]-<TÜR>`.
YENI_DESEN = re.compile(
    r"^[A-Z]{2,10}(?:\.[A-Z]+){0,2}-\d{4,}(?:-[A-Z]{2,10}(?:\.[A-Z]+){1,2})?-[A-Z]{3}$"
)
_ESKI_KOD = re.compile(r"^([A-Z][0-9A-Z])\.")

#: Eski ilk blok → kategori adı (karar 023 §6.3). X1 ve S kodları ayrı ele alınır.
ESKI_KOD_KATEGORISI: dict[str, str] = {
    "D1": "Doktor",
    "D2": "Sağlık Çalışanı",
    "H1": "Hasta",
    "H2": "Özel Hastane",
}
_KISI_ESKI_KODLARI = frozenset({"D1", "D2", "H1"})
#: Tek şirkete giden eski sigorta kodları. S4 (Corpus + Quick) ve S0 (torba) addan çözülür.
ESKI_SIGORTA_KODLARI: dict[str, str] = {
    "S1": "AK", "S2": "ANADOLU", "S3": "AXA", "S5": "EUREKO", "S6": "NIPPON", "S7": "SOMPO",
}
SIGORTA_KATEGORISI = "Sigorta"

K_KAYIT, K_KAYIT_AD, K_FOY, K_ESKI, K_AD = "muvekkil_kaydi", "muvekkil_kaydi_ad", "foy", "eski_numara", "ad_kurali"
S_FOY, S_TARAF, S_ORTAK, S_DAVALI, S_EKSIK = "foy", "taraf", "ortak_muvekkil", "diger_davali", "eksik"


class GocDurdu(RuntimeError):
    """`--apply` yazmadan durdu (müvekkilsiz kart / plan çakışması / envanter kapısı)."""


# ─── Veri yapıları ───────────────────────────────────────────────────────────

@dataclass
class KartGirdisi:
    """Bir kartın göç için gereken alanları (DB'siz sınanabilir).

    `taraflar`: `{id, name, role, party_type, client_category}` sözlükleri (id sırası);
    `foyler`: `{case_party_id, muvekkil_tipi, ham_veri, kapsam_durumu}` sözlükleri (id sırası).
    """
    case_id: int
    tracking_no: str
    file_type: Optional[str] = None
    opening_date: Optional[date] = None
    created_at: Optional[datetime] = None
    silinmis: bool = False
    ofis_no_kodu: Optional[str] = None
    ofis_no_sira: Optional[int] = None
    taraflar: list[dict[str, Any]] = field(default_factory=list)
    foyler: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class KartPlani:
    case_id: int
    eski: str
    silinmis: bool
    durum: str                      # GOC | ZATEN_YENI | MUVEKKILSIZ
    kod: Optional[str] = None
    sigortali: Optional[str] = None
    tur: Optional[str] = None
    sira: Optional[int] = None
    yeni: Optional[str] = None
    sigortaci: bool = False
    kategori_kaynagi: str = ""
    sigortali_kaynagi: str = ""
    muvekkil_adi: str = ""
    aciklama: str = ""
    opening_date: Optional[date] = None
    created_at: Optional[datetime] = None


@dataclass
class GocSonucu:
    planlar: list[KartPlani] = field(default_factory=list)
    uygulandi: bool = False
    envanter: tuple[int, int, int] = (0, 0, 0)       # kart, silinmiş, föy
    foy_cevrilen: int = 0
    foy_eslesmeyen: int = 0
    sayaclar: dict[str, int] = field(default_factory=dict)
    plan_hatalari: list[str] = field(default_factory=list)
    raporlar: list[Path] = field(default_factory=list)

    def durumdakiler(self, durum: str) -> list[KartPlani]:
        return [p for p in self.planlar if p.durum == durum]

    @property
    def degisen(self) -> int:
        return len(self.durumdakiler("GOC"))


# ─── Plan (saf) ──────────────────────────────────────────────────────────────

def yeni_formatta(tracking_no: Optional[str]) -> bool:
    return bool(YENI_DESEN.match(tracking_no or ""))


def eski_kod(tracking_no: Optional[str]) -> Optional[str]:
    """Eski numaranın ilk bloğu (`D1`, `S3` …); eski formatta değilse None."""
    m = _ESKI_KOD.match(tracking_no or "")
    return m.group(1) if m else None


def ad_anahtari(ad: Optional[str]) -> str:
    return " ".join(ofis_no.ascii_buyuk(ad).split())


def _muvekkilleri_coz(
    kart: KartGirdisi, ad_kategorileri: Mapping[str, str]
) -> list[dict[str, Any]]:
    """Kartın adı dolu CLIENT tarafları + zincirle çözülen kategorileri (`category`, `kaynak`)."""
    muvekkiller: list[dict[str, Any]] = []
    for t in kart.taraflar:
        ad = str(t.get("name") or "").strip()
        if t.get("party_type") != "CLIENT" or not ad:
            continue
        kategori, kaynak = None, K_AD
        kayit = str(t.get("client_category") or "").strip()
        if kayit:
            kategori, kaynak = kayit, K_KAYIT
        elif ad_kategorileri.get(ad_anahtari(ad)):
            kategori, kaynak = ad_kategorileri[ad_anahtari(ad)], K_KAYIT_AD
        else:
            for f in kart.foyler:
                tip = str(f.get("muvekkil_tipi") or "").strip()
                if tip and not f.get("kapsam_durumu") and f.get("case_party_id") == t.get("id"):
                    kategori, kaynak = tip, K_FOY
                    break
        muvekkiller.append({"name": ad, "category": kategori, "kaynak": kaynak})

    # Basamak 3: eski numaranın ilk bloğu — yalnız hâlâ kategorisiz müvekkillere.
    kod2 = eski_kod(kart.tracking_no)
    bos = [m for m in muvekkiller if not m["category"]]
    if not kod2 or not bos:
        return muvekkiller
    if kod2 in ESKI_KOD_KATEGORISI:
        for m in bos:
            # Kişi kodu (D1/D2/H1) şirket ya da sigortacı adına yazılmaz — o ad kuralına kalır.
            sirket = ofis_no.sirket_isareti_var(m["name"]) or ofis_no.sigortaci_mi(m["name"])
            if kod2 in _KISI_ESKI_KODLARI and sirket:
                continue
            m["category"], m["kaynak"] = ESKI_KOD_KATEGORISI[kod2], K_ESKI
    elif kod2.startswith("S") and kod2[1].isdigit():
        for m in bos:
            if ofis_no.sigortaci_mi(m["name"]):
                m["category"], m["kaynak"] = SIGORTA_KATEGORISI, K_ESKI
        if not any(ofis_no.sigortaci_mi(m["name"], m["category"]) for m in muvekkiller):
            for m in bos:
                m["category"], m["kaynak"] = SIGORTA_KATEGORISI, K_ESKI
    elif kod2 == "X1":
        for m in bos:
            m["category"] = "Kurum" if ofis_no.sirket_isareti_var(m["name"]) else "Bireysel"
            m["kaynak"] = K_ESKI
    return muvekkiller


def _sigortali_coz(
    kart: KartGirdisi, muvekkiller: Sequence[Mapping[str, Any]], kl: ofis_no.KodListeleri
) -> tuple[Optional[str], str]:
    """(sigortalı bloğu, kaynağı). Blok `ofis_no.sigortali_sec`'in TAM çağrısından gelir;
    kaynak, aynı fonksiyonun tek kaynakla çağrılmasıyla (öncelik sırasıyla) bulunur."""
    taraflar = kart.taraflar
    blok = ofis_no.sigortali_sec(
        None, foys=kart.foyler, parties=taraflar, muvekkiller=muvekkiller, kod_listeleri=kl
    )
    if not blok:
        return None, S_EKSIK
    asamalar: tuple[tuple[str, Callable[[], Optional[str]]], ...] = (
        (S_FOY, lambda: ofis_no.sigortali_sec(None, foys=kart.foyler, parties=[], muvekkiller=[], kod_listeleri=kl)),
        (S_TARAF, lambda: ofis_no.sigortali_sec(
            None, foys=[], parties=[t for t in taraflar if t.get("role") == "Sigortalı"],
            muvekkiller=[], kod_listeleri=kl)),
        (S_ORTAK, lambda: ofis_no.sigortali_sec(
            None, foys=[], parties=[], muvekkiller=muvekkiller, kod_listeleri=kl)),
    )
    for ad, dene in asamalar:
        if dene() == blok:
            return blok, ad
    return blok, S_DAVALI


def kart_planla(
    kart: KartGirdisi,
    kl: Optional[ofis_no.KodListeleri] = None,
    ad_kategorileri: Optional[Mapping[str, str]] = None,
) -> KartPlani:
    """Tek kartın SIRASIZ planı (kod + sigortalı + tür + kaynaklar)."""
    kl = kl or ofis_no.varsayilan_kod_listeleri()
    plan = KartPlani(
        case_id=kart.case_id, eski=kart.tracking_no, silinmis=kart.silinmis, durum="GOC",
        opening_date=kart.opening_date, created_at=kart.created_at,
    )
    if kart.ofis_no_kodu and kart.ofis_no_sira and yeni_formatta(kart.tracking_no):
        plan.durum, plan.kod, plan.sira, plan.yeni = "ZATEN_YENI", kart.ofis_no_kodu, kart.ofis_no_sira, kart.tracking_no
        return plan

    muvekkiller = _muvekkilleri_coz(kart, ad_kategorileri or {})
    try:
        kod, secilen = ofis_no.musteri_kodu(muvekkiller, kl)
    except ValueError as e:
        plan.durum, plan.aciklama = "MUVEKKILSIZ", str(e)
        return plan

    plan.muvekkil_adi = secilen["name"]
    plan.kategori_kaynagi = secilen["kaynak"]
    plan.sigortaci = ofis_no.sigortaci_mi(secilen["name"], secilen["category"])
    if plan.sigortaci:
        sabit = ESKI_SIGORTA_KODLARI.get(eski_kod(kart.tracking_no) or "")
        if kod == ofis_no.SG_KODU and sabit and sabit in {s.kod for s in kl.sigorta}:
            kod, plan.kategori_kaynagi = sabit, K_ESKI
        plan.sigortali, plan.sigortali_kaynagi = _sigortali_coz(kart, muvekkiller, kl)
    plan.kod = kod
    plan.tur = ofis_no.tur_kodu(kart.file_type)
    return plan


def _sira_anahtari(p: KartPlani) -> tuple:
    return (
        p.opening_date is None, p.opening_date or date.min,
        p.created_at is None, p.created_at.timestamp() if p.created_at else 0.0,
        p.case_id,
    )


def siralari_ver(planlar: Sequence[KartPlani], sayaclar: Optional[Mapping[str, int]] = None) -> dict[str, int]:
    """GOC planlarına sıra + numara verir; kod başına en yüksek sırayı döndürür.

    Başlangıç = o kodun sayacı ile zaten yeni formattaki kartların en yüksek sırasının büyüğü.
    """
    tepe: dict[str, int] = defaultdict(int)
    for kod, son in (sayaclar or {}).items():
        tepe[kod] = max(tepe[kod], int(son))
    gruplar: dict[str, list[KartPlani]] = defaultdict(list)
    for p in planlar:
        if p.durum == "ZATEN_YENI" and p.kod and p.sira:
            tepe[p.kod] = max(tepe[p.kod], int(p.sira))
        elif p.durum == "GOC" and p.kod:
            gruplar[p.kod].append(p)
    for kod, grup in gruplar.items():
        for p in sorted(grup, key=_sira_anahtari):
            tepe[kod] += 1
            p.sira = tepe[kod]
            p.yeni = ofis_no.numara_kur(kod, p.sira, p.sigortali, p.tur or ofis_no.VARSAYILAN_TUR_KODU)
    return {kod: tepe[kod] for kod in gruplar}


def plan_hatalari(planlar: Sequence[KartPlani]) -> list[str]:
    """Planın kendi kapısı: yeni numaralar desene uyuyor ve hiçbir numarayla çakışmıyor mu?"""
    hatalar: list[str] = []
    gorulen: dict[str, int] = {}
    for p in planlar:
        numara = p.yeni if p.durum == "GOC" else p.eski
        if p.durum == "GOC" and not yeni_formatta(numara):
            hatalar.append(f"#{p.case_id}: desen dışı numara {numara!r}")
        if numara in gorulen:
            hatalar.append(f"#{p.case_id}: {numara!r} mükerrer (#{gorulen[numara]} ile)")
        elif numara:
            gorulen[numara] = p.case_id
    return hatalar


# ─── DB okuma ────────────────────────────────────────────────────────────────

def kartlari_oku(db) -> tuple[list[KartGirdisi], dict[str, str]]:
    """Tüm kartlar (silinmişler dahil) + ad → TEK kategori haritası (müvekkil kayıtlarından)."""
    C, P, F, M = models.Case, models.CaseParty, models.CaseFoy, models.Client

    kategoriler: dict[int, str] = {}
    ad_kumeleri: dict[str, set[str]] = defaultdict(set)
    for mid, ad, kategori, silindi in db.execute(select(M.id, M.name, M.category, M.deleted_at)):
        temiz = str(kategori or "").strip()
        if not temiz:
            continue
        kategoriler[mid] = temiz
        if silindi is None and ad_anahtari(ad):
            ad_kumeleri[ad_anahtari(ad)].add(temiz)
    ad_kategorileri = {ad: next(iter(k)) for ad, k in ad_kumeleri.items() if len(k) == 1}

    taraflar: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for pid, case_id, client_id, ad, rol, tip in db.execute(
        select(P.id, P.case_id, P.client_id, P.name, P.role, P.party_type).order_by(P.case_id, P.id)
    ):
        taraflar[case_id].append({
            "id": pid, "name": ad, "role": rol, "party_type": tip,
            "client_category": kategoriler.get(client_id) if client_id else None,
        })

    foyler: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for case_id, party_id, tip, ham, kapsam in db.execute(
        select(F.case_id, F.case_party_id, F.muvekkil_tipi, F.ham_veri, F.kapsam_durumu).order_by(F.case_id, F.id)
    ):
        foyler[case_id].append({
            "case_party_id": party_id, "muvekkil_tipi": tip, "ham_veri": ham, "kapsam_durumu": kapsam,
        })

    kartlar = [
        KartGirdisi(
            case_id=cid, tracking_no=no, file_type=tur, opening_date=acilis, created_at=olusturma,
            silinmis=silindi is not None, ofis_no_kodu=kod, ofis_no_sira=sira,
            taraflar=taraflar.get(cid, []), foyler=foyler.get(cid, []),
        )
        for cid, no, tur, acilis, olusturma, silindi, kod, sira in db.execute(
            select(C.id, C.tracking_no, C.file_type, C.opening_date, C.created_at, C.deleted_at,
                   C.ofis_no_kodu, C.ofis_no_sira).order_by(C.id)
        )
    ]
    return kartlar, ad_kategorileri


def envanter(db) -> tuple[int, int, int]:
    """(kart sayısı, silinmiş kart sayısı, föy sayısı)."""
    kart, silinmis = db.execute(text("SELECT count(*), count(deleted_at) FROM cases")).one()
    foy = db.execute(text("SELECT count(*) FROM case_foys")).scalar_one()
    return int(kart), int(silinmis), int(foy)


def plani_kur(db) -> GocSonucu:
    kartlar, ad_kategorileri = kartlari_oku(db)
    kl = ofis_no.kod_listelerini_yukle(db)
    sonuc = GocSonucu(planlar=[kart_planla(k, kl, ad_kategorileri) for k in kartlar])
    sayaclar = {str(kod): int(son) for kod, son in db.execute(text("SELECT kod, son_sira FROM ofis_no_sayaclari"))}
    sonuc.sayaclar = siralari_ver(sonuc.planlar, sayaclar)
    sonuc.plan_hatalari = plan_hatalari(sonuc.planlar)
    sonuc.envanter = envanter(db)
    return sonuc


# ─── Uygulama ────────────────────────────────────────────────────────────────

_SAYAC_SQL = text(
    "INSERT INTO ofis_no_sayaclari (kod, son_sira, updated_at) VALUES (:kod, :sira, CURRENT_TIMESTAMP) "
    "ON CONFLICT (kod) DO UPDATE SET "
    "son_sira = GREATEST(ofis_no_sayaclari.son_sira, EXCLUDED.son_sira), updated_at = CURRENT_TIMESTAMP"
)


def kapi_kontrolu(db, onceki: tuple[int, int, int], muaf: frozenset[str] = frozenset()) -> list[str]:
    """Envanter kapısı — boş liste = geçti. `muaf`: eski numarasıyla bırakılan (müvekkilsiz) kartlar."""
    hatalar: list[str] = []
    sonraki = envanter(db)
    if sonraki != onceki:
        hatalar.append(f"envanter değişti: önce {onceki}, sonra {sonraki} (kart, silinmiş, föy)")
    numaralar = [str(n) for (n,) in db.execute(text("SELECT tracking_no FROM cases"))]
    if len(set(numaralar)) != len(numaralar):
        hatalar.append(f"mükerrer numara: {len(numaralar) - len(set(numaralar))}")
    disi = [n for n in numaralar if n not in muaf and not yeni_formatta(n)]
    if disi:
        hatalar.append(f"desen dışı {len(disi)} numara (ilk: {disi[0]!r})")
    return hatalar


def uygula(db, sonuc: GocSonucu, *, kim: str) -> None:
    """Planı AÇIK transaction'a yazar (commit ÇAĞIRANDA). Kapı tutmazsa `GocDurdu`."""
    # Müvekkilsiz kartlar atlanır, eski numarasıyla kalır (kullanıcı kararı 30.09).
    muaf = frozenset(p.eski for p in sonuc.durumdakiler("MUVEKKILSIZ"))
    if sonuc.plan_hatalari:
        raise GocDurdu(f"plan kapısı: {sonuc.plan_hatalari[0]} (+{len(sonuc.plan_hatalari) - 1})")
    degisen = sonuc.durumdakiler("GOC")
    if not degisen:
        return

    onceki = envanter(db)
    # Aşama 1: geçici numara — yeni numara, henüz taşınmamış bir kartın ESKİ numarasıyla çakışmasın.
    db.execute(
        text("UPDATE cases SET tracking_no = :gecici WHERE id = :id"),
        [{"gecici": f"{GECICI_ONEK}{p.case_id}", "id": p.case_id} for p in degisen],
    )
    # Aşama 2: yeni numara + kod + sıra.
    db.execute(
        text("UPDATE cases SET tracking_no = :yeni, ofis_no_kodu = :kod, ofis_no_sira = :sira WHERE id = :id"),
        [{"yeni": p.yeni, "kod": p.kod, "sira": p.sira, "id": p.case_id} for p in degisen],
    )
    tarihce = [
        {"case_id": p.case_id, "field_name": "tracking_no", "old_value": p.eski, "new_value": p.yeni,
         "changed_by": kim[:200], "source": KAYNAK}
        for p in degisen
    ]

    # Föylerde kalan eski numaralar (sönen kartın numarası) aynı eşlemeyle çevrilir.
    esleme = {p.eski: p.yeni for p in degisen}
    foy_guncelle: list[dict[str, Any]] = []
    for foy_id, case_id, onceki_no in db.execute(text(
        "SELECT id, case_id, onceki_tracking_no FROM case_foys WHERE onceki_tracking_no IS NOT NULL ORDER BY id"
    )):
        yeni = esleme.get(str(onceki_no))
        if yeni is None:
            sonuc.foy_eslesmeyen += 1
            continue
        foy_guncelle.append({"yeni": yeni, "id": foy_id})
        # Föyün bugünkü kartı eski numarayla aranınca bulunmaya devam etsin (history.old_value kolu).
        tarihce.append({
            "case_id": case_id, "field_name": "onceki_tracking_no", "old_value": str(onceki_no),
            "new_value": yeni, "changed_by": kim[:200], "source": KAYNAK,
        })
    if foy_guncelle:
        db.execute(text("UPDATE case_foys SET onceki_tracking_no = :yeni WHERE id = :id"), foy_guncelle)
    sonuc.foy_cevrilen = len(foy_guncelle)

    db.execute(insert(models.CaseHistory.__table__), tarihce)
    db.execute(_SAYAC_SQL, [{"kod": kod, "sira": sira} for kod, sira in sorted(sonuc.sayaclar.items())])

    hatalar = kapi_kontrolu(db, onceki, muaf)
    if hatalar:
        raise GocDurdu("envanter kapısı: " + "; ".join(hatalar))


def kos(session_factory, *, apply: bool = False, kim: str = DEGISTIREN,
        rapor_dizini: Optional[Path] = None) -> GocSonucu:
    """Planı kurar; `apply` ise tek transaction'da yazar. Kuru koşu DB'ye hiçbir şey yazmaz."""
    db = session_factory()
    try:
        sonuc = plani_kur(db)
        if apply:
            uygula(db, sonuc, kim=kim)
            db.commit()
            sonuc.uygulandi = True
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    if rapor_dizini is not None:
        sonuc.raporlar = raporlari_yaz(sonuc, rapor_dizini)
    return sonuc


# ─── Raporlar ────────────────────────────────────────────────────────────────

def ozet_metni(sonuc: GocSonucu) -> str:
    goc = sonuc.durumdakiler("GOC")
    zaten = sonuc.durumdakiler("ZATEN_YENI")
    muvekkilsiz = sonuc.durumdakiler("MUVEKKILSIZ")
    eksik = [p for p in goc if p.sigortaci and not p.sigortali]
    kart, silinmis, foy = sonuc.envanter
    cizgi = "=" * 78
    s = [cizgi, f"Ofis no göçü (karar 023) — {'UYGULANDI' if sonuc.uygulandi else 'KURU KOŞU'}", cizgi,
         f"  Kart {kart} (silinmiş {silinmis}) · föy {foy}",
         f"  Numaralanan {len(goc)} · zaten yeni formatta {len(zaten)} · müvekkilsiz {len(muvekkilsiz)}",
         f"  Sigortacı müvekkilli {sum(1 for p in goc if p.sigortaci)} · sigortalı eksik {len(eksik)}"]
    if sonuc.uygulandi:
        s.append(f"  Föy onceki_tracking_no: çevrilen {sonuc.foy_cevrilen} · eşlemede olmayan {sonuc.foy_eslesmeyen}")
    if sonuc.plan_hatalari:
        s.append(f"  PLAN KAPISI: {len(sonuc.plan_hatalari)} hata")
        s.extend(f"    {h}" for h in sonuc.plan_hatalari[:20])

    s.append("\n  Kategori kodu dağılımı (müvekkil kodunun ilk parçası):")
    for kod, n in Counter((p.kod or "").split(".")[0] for p in goc).most_common():
        s.append(f"    {kod:12} {n:6}")
    s.append("\n  Kategori kaynağı dağılımı:")
    for ad, n in Counter(p.kategori_kaynagi for p in goc).most_common():
        s.append(f"    {ad:20} {n:6}")
    s.append("\n  Sigortalı kaynağı dağılımı (sigortacı müvekkilli kartlar):")
    for ad, n in Counter(p.sigortali_kaynagi for p in goc if p.sigortaci).most_common():
        s.append(f"    {ad:20} {n:6}")

    sg = [p for p in goc if p.kod == ofis_no.SG_KODU]
    s.append(f"\n  SG'ye düşen kart: {len(sg)} — müvekkil adları:")
    for ad, n in Counter(p.muvekkil_adi for p in sg).most_common():
        s.append(f"    {n:5}  {ad}")

    s.append(f"\n  Müvekkilsiz kart: {len(muvekkilsiz)} — eski ilk blok dağılımı: "
             + ", ".join(f"{k or '?'}={n}" for k, n in Counter(eski_kod(p.eski) for p in muvekkilsiz).most_common()))
    for p in muvekkilsiz:
        s.append(f"    #{p.case_id:<6} {p.eski}{' (silinmiş)' if p.silinmis else ''}")

    s.append(f"\n  Müvekkil kodu başına kart sayısı ({len(sonuc.sayaclar)} kod, en yüksek sıra):")
    for kod, n in sorted(Counter(p.kod for p in goc).items(), key=lambda kv: (-kv[1], kv[0] or "")):
        s.append(f"    {kod:40} {n:6}  (son sıra {sonuc.sayaclar.get(kod or '', 0)})")
    s.append(cizgi)
    return "\n".join(s)


def raporlari_yaz(sonuc: GocSonucu, dizin: Path, damga: Optional[str] = None) -> list[Path]:
    dizin.mkdir(parents=True, exist_ok=True)
    damga = damga or f"{datetime.now():%Y%m%d-%H%M%S}"
    esleme = dizin / f"ofis_no_esleme_{damga}.csv"
    eksik = dizin / f"ofis_no_sigortali_eksik_{damga}.csv"
    ozet = dizin / f"ofis_no_ozet_{damga}.txt"
    with esleme.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "eski", "yeni", "silinmis", "kategori_kaynagi", "sigortali_kaynagi"])
        for p in sonuc.planlar:
            if p.durum == "GOC":
                w.writerow([p.case_id, p.eski, p.yeni, int(p.silinmis), p.kategori_kaynagi, p.sigortali_kaynagi])
    with eksik.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "eski", "yeni", "silinmis", "muvekkil"])
        for p in sonuc.planlar:
            if p.durum == "GOC" and p.sigortaci and not p.sigortali:
                w.writerow([p.case_id, p.eski, p.yeni, int(p.silinmis), p.muvekkil_adi])
    ozet.write_text(ozet_metni(sonuc) + "\n", encoding="utf-8")
    return [esleme, eksik, ozet]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Ofis no göçü (karar 023)")
    ayristirici.add_argument("--apply", action="store_true", help="yazar (yoksa kuru koşu)")
    ayristirici.add_argument("--kim", default=DEGISTIREN, help="tarihçe imzası")
    ayristirici.add_argument("--rapor-dizini", default=str(Path(tempfile.gettempdir()) / "ofis-no-gocu"),
                             help="CSV + özet dosyalarının yazılacağı dizin")
    ayristirici.add_argument("--ayrinti", action="store_true", help="özeti ekrana kod başına dökümle basar")
    args = ayristirici.parse_args(argv)

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    try:
        sonuc = kos(SessionLocal, apply=args.apply, kim=args.kim, rapor_dizini=Path(args.rapor_dizini))
    except GocDurdu as e:
        print(f"DURDU — hiçbir şey yazılmadı: {e}")
        return 2
    metin = ozet_metni(sonuc)
    if not args.ayrinti:
        metin = metin.split("\n  Müvekkil kodu başına kart sayısı")[0]
    print(metin)
    for yol in sonuc.raporlar:
        print(f"  rapor: {yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
