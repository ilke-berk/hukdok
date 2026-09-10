#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Yazım birliği — tek seferlik büyük/küçük harf dönüşümü (G160, plan 08.09 §5.3-B).

Aynı değerin iki yazımı DB'de yan yana yaşıyor: kartta "Kadın Hastalıkları
**Ve** Doğum" (eski `tr_title`) ↔ teslimde "… ve …"; taraf adı "AK SİGORTA
A.Ş." ↔ "Ak Sigorta A.ş." ↔ "Ak Sigorta A.Ş."; mahkeme "İSTANBUL 6. TÜKETİCİ
MAHKEMESİ" ↔ "İstanbul 6. Tüketici Mahkemesi". Bu betik yazımı BİRLEŞTİRİR,
içeriğe dokunmaz: yalnız Türkçe büyük-harf anahtarı (`turkish_upper`, boşluk
normalize) AYNI olan değerler dönüşür; "Perinatoloji" ↔ "Kadın Hastalıkları"
gibi içerik farkı asla.

Adımlar (`--adim 1,2,…`; varsayılan hepsi):

| # | Hedef                  | Kaynak                                                          |
|---|------------------------|-----------------------------------------------------------------|
| 1 | `cases.sub_type`       | föy `ham_veri["Uzmanlık Alanı"]` yazımı; yoksa DB-içi ikiz → baskın |
| 2 | `case_parties.name`    | föy `ham_veri["Müvekkil"/"Karşı Taraf"]` yazımı; yoksa ikiz → baskın |
| 3 | `cases.court`          | DB-içi ikiz → baskın (teslim yazımı KULLANILMAZ: mahkeme adı kimliği bizim, G067-G070) |
| 4 | `cases.subject`        | DB-içi ikiz → baskın                                            |
| 5 | `case_parties.role`    | `party_roles` listesindeki yazım ("DAVALI" → "Davalı")          |
| 6 | `bureau_types` listesi | BÜYÜK liste adı → kart yazımı (`update_item` rename); "Hasta" listeye eklenir; "Tür Seçiniz" → boş |

**Baskın yazım kuralı:** gruptaki en çok satırlı yazım; eşitlikte teslim
yazımı, o da yoksa `tr_title`. Seçilen yazım tamamı BÜYÜK ise `tr_title`
(DB-008: kart Title yazar).

**DOKUNULMAZ:** rolü "Sigortalı" / "Davalı İdare" olan taraf satırları (teslim
BÜYÜK yazar, bizim yazım korunur — ne güncellenir ne baskınlık sayımına girer),
`istinaf_mahkemesi`/`temyiz_mahkemesi` + `appeal_courts`/`cassation_courts`
(paket kaynaklı, A sınıfı), avukat adları, `case_documents.muvekkil_adi`
(deprecated kopya), `deleted_at` dolu kartlar (ve tarafları), kapsam dışı
föylerin ham satırı (`kapsam_durumu` dolu — kardeş-föy uzlaşısıyla aynı kural).

Güvenlik:
  - VARSAYILAN KURU KOŞU: hiçbir şey yazmaz; adım başına özet (tekil değer,
    satır sayısı, ilk 20 örnek) + CSV (`<cikti-dizini>/<adim>.csv`).
  - `--apply --kim <kullanıcı>`: TEK transaction; kart alanları `case_history`
    (`source="yazim_birligi"`, `changed_by=--kim`); taraf satırı yerinde UPDATE
    (`id` sabit — belge bağı `case_party_id` FAZ F şartıyla korunur; satır
    silinmez/yeniden yaratılmaz). Belge envanteri (`services/belge_envanteri`)
    commit'ten önce ölçülür; DENK değilse koşu geri alınır, NONZERO çıkar.
  - İdempotent: ikinci `--apply` 0 değişiklik. `--limit` YOK (kısmi koşu
    ikizleri yarım bırakır).
  - Adım 6'nın liste işlemleri (`update_item`/`add_item`) kendi oturumlarında
    ve kart transaction'ı commit edildikten SONRA koşar; kart tarafı bu betiğin
    tarihçeli UPDATE'iyle önce hizalanır, `update_item`ın DEPENDENCIES yayılımı
    artık boş küme bulur (silinmiş kartlardaki eski yazım hariç — o yayılım
    tarihçesizdir, admin paneliyle aynı davranış).

Kullanım (konteynerde, prod'da paket uygulamasından SONRA ve yedekle):
  docker compose exec -T backend python scripts/yazim_birligi.py                 # kuru koşu, tüm adımlar
  docker compose exec -T backend python scripts/yazim_birligi.py --adim 1,3
  docker compose exec -T backend python scripts/yazim_birligi.py --apply --kim ilke
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ modülleri için

# E402 (import'tan önce sys.path kurulumu) scripts/* için pyproject'te bilinçli
# olarak kapalıdır — script tek başına da koşabilmeli (hukdok_aktarim deseni).
import models
from managers import reference_lists
from managers.reference_lists import normalize_list_name, tr_title
from scripts.hukdok_aktarim import TARAF_SUTUNLARI, _taraf_adlari
from services import belge_envanteri
from text_utils import turkish_upper

logger = logging.getLogger("yazim_birligi")

SOURCE = "yazim_birligi"
VARSAYILAN_CIKTI = "/tmp/yazim_birligi"
ORNEK_SAYISI = 20

CIKIS_TAMAM = 0
CIKIS_ENVANTER = 2

#: Dokunulmayan taraf rolleri — teslim bu sütunları BÜYÜK yazar (D1 şartname
#: §2 ve Davalı İdare); `TARAF_SUTUNLARI`ndan okunur ki aktarımla aynı ad kalsın.
KORUNAN_ROLLER = frozenset(
    rol for _, party_type, rol in TARAF_SUTUNLARI if party_type == "THIRD"
)

#: Adım 1-2'nin föy ham satırındaki başlıkları (G125 `ham_veri`, orijinal sütun adı).
HAM_UZMANLIK = "Uzmanlık Alanı"
HAM_TARAF_BASLIKLARI: Tuple[str, ...] = ("Müvekkil", "Karşı Taraf")

#: Adım 6 özel değerleri: kartta var, listede yok → listeye eklenir;
#: yer tutucu → kart alanı boşaltılır.
BURO_EKLENECEK = "Hasta"
BURO_BOSALTILACAK = "Tür Seçiniz"


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def anahtar(deger: str) -> str:
    """Yazım-duyarsız kimlik: boşluk normalize + Türkçe BÜYÜK (`turkish_upper`)."""
    return turkish_upper(" ".join(str(deger).split()))


def _duz(deger: str) -> str:
    return " ".join(str(deger).split())


def _tamami_buyuk(deger: str) -> bool:
    return any(ch.isalpha() for ch in deger) and deger == turkish_upper(deger)


def baskin_yazim(sayimlar: Dict[str, int], teslim: Optional[str] = None) -> str:
    """Bir anahtar grubunun hedef yazımı.

    Gruptaki en çok satırlı yazım; eşitlikte teslim yazımı, o da yoksa
    `tr_title`. Seçilen yazım tamamı BÜYÜK ise `tr_title` (kart Title yazar).
    `teslim` verilmişse o kazanır (adım 1-2: teslim yazımı hedeftir).
    """
    if teslim is not None:
        secilen = _duz(teslim)
    else:
        en_cok = max(sayimlar.values())
        adaylar = sorted({_duz(v) for v, n in sayimlar.items() if n == en_cok})
        secilen = adaylar[0] if len(adaylar) == 1 else tr_title(adaylar[0])
    if _tamami_buyuk(secilen):
        secilen = tr_title(secilen)
    return secilen


@dataclass(frozen=True)
class Degisiklik:
    tablo: str
    kayit_id: int
    case_id: Optional[int]
    tracking_no: Optional[str]
    alan: str
    eski: Optional[str]
    yeni: Optional[str]
    kaynak: str            # teslim | baskın | tr_title | liste | boşalt
    rol: Optional[str] = None   # taraf satırında tarihçe metni için


@dataclass
class ListeIslemi:
    """Adım 6'nın liste tarafı — kart transaction'ı commit edildikten SONRA koşar."""
    islem: str             # rename | add
    code: str
    eski: Optional[str]
    yeni: str


@dataclass
class AdimSonucu:
    adim: int
    ad: str
    degisiklikler: List[Degisiklik] = field(default_factory=list)
    liste_islemleri: List[ListeIslemi] = field(default_factory=list)
    notlar: List[str] = field(default_factory=list)

    @property
    def satir(self) -> int:
        return len(self.degisiklikler)

    @property
    def tekil(self) -> int:
        return len({(d.eski, d.yeni) for d in self.degisiklikler})


@dataclass
class KosuSonucu:
    adimlar: List[AdimSonucu]
    yazildi: bool
    envanter_farki: Dict[str, Tuple[Any, Any]]
    liste_sonuclari: List[str] = field(default_factory=list)

    @property
    def toplam_satir(self) -> int:
        return sum(a.satir for a in self.adimlar)

    @property
    def cikis_kodu(self) -> int:
        return CIKIS_ENVANTER if self.envanter_farki else CIKIS_TAMAM


# ─── Ortak okuma ─────────────────────────────────────────────────────────────

def _kapsamdaki_ham_satirlar(db) -> Iterable[Tuple[int, Dict[str, Any]]]:
    """(case_id, ham_veri) — silinmemiş kart, kapsamdaki föy, ham satırı olan."""
    sorgu = (
        db.query(models.CaseFoy.case_id, models.CaseFoy.ham_veri)
        .join(models.Case, models.Case.id == models.CaseFoy.case_id)
        .filter(
            models.Case.deleted_at.is_(None),
            models.CaseFoy.kapsam_durumu.is_(None),
            models.CaseFoy.ham_veri.isnot(None),
        )
    )
    for case_id, ham in sorgu:
        if isinstance(ham, dict):
            yield case_id, ham


def _teslim_yazimlari(db, basliklar: Sequence[str], parcala: bool) -> Dict[str, str]:
    """{anahtar: teslim yazımı} — her anahtar için en sık görülen yazım."""
    sayac: Dict[str, Counter] = defaultdict(Counter)
    for _case_id, ham in _kapsamdaki_ham_satirlar(db):
        for baslik in basliklar:
            deger = ham.get(baslik)
            if deger is None or not str(deger).strip():
                continue
            adlar = _taraf_adlari(deger) if parcala else [_duz(str(deger))]
            for ad in adlar:
                sayac[anahtar(ad)][ad] += 1
    return {k: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for k, c in sayac.items()}


def _tracking(db) -> Dict[int, str]:
    return dict(db.query(models.Case.id, models.Case.tracking_no))


def _kart_kolonu_donustur(db, adim: int, ad: str, kolon: str, teslim: Dict[str, str]) -> AdimSonucu:
    """`cases.<kolon>` için anahtar grupları: hedef teslim yazımı ya da baskın."""
    sonuc = AdimSonucu(adim, ad)
    kol = getattr(models.Case, kolon)
    satirlar = (
        db.query(models.Case.id, models.Case.tracking_no, kol)
        .filter(models.Case.deleted_at.is_(None), kol.isnot(None))
        .all()
    )
    gruplar: Dict[str, Dict[str, int]] = defaultdict(Counter)
    for _id, _tn, deger in satirlar:
        gruplar[anahtar(deger)][deger] += 1
    hedefler: Dict[str, Tuple[str, str]] = {}
    for k, sayimlar in gruplar.items():
        if k in teslim:
            hedef, kaynak = baskin_yazim(sayimlar, teslim[k]), "teslim"
            if _tamami_buyuk(teslim[k]):
                kaynak = "tr_title"
        elif len(sayimlar) > 1:
            hedef, kaynak = baskin_yazim(sayimlar), "baskın"
            if hedef not in sayimlar:
                kaynak = "tr_title"
        else:
            continue
        if any(v != hedef for v in sayimlar):
            hedefler[k] = (hedef, kaynak)
    for kart_id, tracking_no, deger in satirlar:
        h = hedefler.get(anahtar(deger))
        if h is None or deger == h[0]:
            continue
        sonuc.degisiklikler.append(Degisiklik(
            "cases", kart_id, kart_id, tracking_no, kolon, deger, h[0], h[1],
        ))
    return sonuc


# ─── Adımlar ─────────────────────────────────────────────────────────────────

def adim_1_uzmanlik(db) -> AdimSonucu:
    """`cases.sub_type`: föy teslim yazımı (Uzmanlık Alanı); yoksa DB-içi ikiz → baskın."""
    teslim = _teslim_yazimlari(db, (HAM_UZMANLIK,), parcala=False)
    return _kart_kolonu_donustur(db, 1, "uzmanlık alanı (cases.sub_type)", "sub_type", teslim)


def _taraf_satirlari(db):
    """Silinmemiş kartın, korunan rol DIŞI taraf satırları."""
    return (
        db.query(models.CaseParty.id, models.CaseParty.case_id, models.CaseParty.name, models.CaseParty.role)
        .join(models.Case, models.Case.id == models.CaseParty.case_id)
        .filter(models.Case.deleted_at.is_(None), models.CaseParty.role.notin_(sorted(KORUNAN_ROLLER)))
        .all()
    )


def adim_2_taraf_adi(db) -> AdimSonucu:
    """`case_parties.name`: föy teslim yazımı (Müvekkil/Karşı Taraf); yoksa DB-içi ikiz → baskın.

    Rolü `KORUNAN_ROLLER`de olan satırlar ne güncellenir ne sayıma girer.
    """
    sonuc = AdimSonucu(2, "taraf adı (case_parties.name)")
    teslim = _teslim_yazimlari(db, HAM_TARAF_BASLIKLARI, parcala=True)
    satirlar = _taraf_satirlari(db)
    tracking = _tracking(db)
    gruplar: Dict[str, Dict[str, int]] = defaultdict(Counter)
    for _id, _cid, ad, _rol in satirlar:
        gruplar[anahtar(ad)][ad] += 1
    hedefler: Dict[str, Tuple[str, str]] = {}
    for k, sayimlar in gruplar.items():
        if k in teslim:
            hedef, kaynak = baskin_yazim(sayimlar, teslim[k]), "teslim"
            if _tamami_buyuk(teslim[k]):
                kaynak = "tr_title"
        elif len(sayimlar) > 1:
            hedef, kaynak = baskin_yazim(sayimlar), "baskın"
            if hedef not in sayimlar:
                kaynak = "tr_title"
        else:
            continue
        if any(v != hedef for v in sayimlar):
            hedefler[k] = (hedef, kaynak)
    for taraf_id, case_id, ad, rol in satirlar:
        h = hedefler.get(anahtar(ad))
        if h is None or ad == h[0]:
            continue
        sonuc.degisiklikler.append(Degisiklik(
            "case_parties", taraf_id, case_id, tracking.get(case_id), "name", ad, h[0], h[1], rol=rol,
        ))
    return sonuc


def adim_3_mahkeme(db) -> AdimSonucu:
    """`cases.court`: DB-içi ikiz → baskın. Teslim yazımı KULLANILMAZ (BÜYÜK; kimlik bizim)."""
    return _kart_kolonu_donustur(db, 3, "yerel mahkeme (cases.court)", "court", {})


def adim_4_konu(db) -> AdimSonucu:
    """`cases.subject`: DB-içi ikiz → baskın."""
    return _kart_kolonu_donustur(db, 4, "dava konusu (cases.subject)", "subject", {})


def adim_5_rol(db) -> AdimSonucu:
    """`case_parties.role`: `party_roles` listesindeki yazım ("DAVALI" → "Davalı")."""
    sonuc = AdimSonucu(5, "taraf rolü (case_parties.role)")
    liste = {
        anahtar(ad): ad
        for (ad,) in db.query(models.PartyRole.name).filter(models.PartyRole.active.is_(True))
        if ad
    }
    tracking = _tracking(db)
    for taraf_id, case_id, ad, rol in _taraf_satirlari(db):
        if not rol:
            continue
        hedef = liste.get(anahtar(rol))
        if hedef is None or hedef == rol:
            continue
        sonuc.degisiklikler.append(Degisiklik(
            "case_parties", taraf_id, case_id, tracking.get(case_id), "role", rol, hedef, "liste", rol=ad,
        ))
    return sonuc


def adim_6_buro_turu(db) -> AdimSonucu:
    """`bureau_types` listesi ↔ `cases.bureau_type`.

    Liste adı BÜYÜKse hedef = kart yazımı (kartlardaki baskın; yoksa `tr_title`),
    `normalize_list_name`den geçirilir ki `update_item`ın saklayacağı adla aynı
    olsun. Kartlar bu betikte tarihçeli hizalanır, liste `update_item` ile.
    `BURO_EKLENECEK` listede yoksa eklenir; `BURO_BOSALTILACAK` kart alanı boşaltılır.
    """
    sonuc = AdimSonucu(6, "büro türü (bureau_types + cases.bureau_type)")
    satirlar = (
        db.query(models.Case.id, models.Case.tracking_no, models.Case.bureau_type)
        .filter(models.Case.deleted_at.is_(None), models.Case.bureau_type.isnot(None))
        .all()
    )
    kart_gruplari: Dict[str, Dict[str, int]] = defaultdict(Counter)
    for _id, _tn, deger in satirlar:
        kart_gruplari[anahtar(deger)][deger] += 1

    hedefler: Dict[str, Optional[str]] = {}
    liste_anahtarlari = set()
    for code, ad in db.query(models.BureauType.code, models.BureauType.name):
        if not ad:
            continue
        k = anahtar(ad)
        liste_anahtarlari.add(k)
        sayimlar = kart_gruplari.get(k)
        hedef = normalize_list_name(baskin_yazim(sayimlar) if sayimlar else tr_title(ad))
        if hedef != ad:
            sonuc.liste_islemleri.append(ListeIslemi("rename", code, ad, hedef))
        hedefler[k] = hedef

    if anahtar(BURO_EKLENECEK) not in liste_anahtarlari:
        sonuc.liste_islemleri.append(ListeIslemi(
            "add", turkish_upper(BURO_EKLENECEK).replace(" ", "-"), None, BURO_EKLENECEK,
        ))
        sayimlar = kart_gruplari.get(anahtar(BURO_EKLENECEK))
        sonuc.notlar.append(
            f"{BURO_EKLENECEK!r} listeye eklenir (kartta {sum(sayimlar.values()) if sayimlar else 0} satır)"
        )
    hedefler[anahtar(BURO_BOSALTILACAK)] = None

    for kart_id, tracking_no, deger in satirlar:
        k = anahtar(deger)
        if k not in hedefler:
            continue
        hedef = hedefler[k]
        if deger == hedef:
            continue
        sonuc.degisiklikler.append(Degisiklik(
            "cases", kart_id, kart_id, tracking_no, "bureau_type", deger, hedef,
            "boşalt" if hedef is None else "liste",
        ))
    return sonuc


ADIMLAR: Dict[int, Callable[[Any], AdimSonucu]] = {
    1: adim_1_uzmanlik,
    2: adim_2_taraf_adi,
    3: adim_3_mahkeme,
    4: adim_4_konu,
    5: adim_5_rol,
    6: adim_6_buro_turu,
}


# ─── Uygulama ────────────────────────────────────────────────────────────────

def _uygula(db, sonuc: AdimSonucu, kim: str) -> None:
    """Değişiklikleri AYNI oturumda yazar (commit çağıranın); her kart alanı tarihçeli."""
    for d in sonuc.degisiklikler:
        model = models.Case if d.tablo == "cases" else models.CaseParty
        db.query(model).filter(model.id == d.kayit_id).update(
            {d.alan: d.yeni}, synchronize_session=False,
        )
        if d.tablo == "cases":
            field_name, eski, yeni = d.alan, d.eski, d.yeni
        elif d.alan == "name":
            field_name, eski, yeni = "taraf", f"{d.eski} ({d.rol})", f"{d.yeni} ({d.rol})"
        else:
            field_name, eski, yeni = "taraf", f"{d.rol} ({d.eski})", f"{d.rol} ({d.yeni})"
        db.add(models.CaseHistory(
            case_id=d.case_id, field_name=field_name, old_value=eski, new_value=yeni,
            changed_by=kim, source=SOURCE,
        ))
    db.flush()


def _liste_islemlerini_uygula(islemler: Iterable[ListeIslemi]) -> List[str]:
    """Adım 6 liste tarafı — `reference_lists` kendi oturumunu açar (commit sonrası)."""
    mesajlar: List[str] = []
    for islem in islemler:
        if islem.islem == "rename":
            try:
                r = reference_lists.update_item("bureau_types", islem.code, {"name": islem.yeni})
            except reference_lists.DuplicateItemError as e:
                mesajlar.append(f"ATLANDI {islem.code}: {e}")
                logger.warning(f"bureau_types {islem.code!r} yeniden adlandırılamadı: {e}")
                continue
            mesajlar.append(
                f"{islem.code}: {islem.eski!r} → {islem.yeni!r}"
                + (f" (yayılan {r['updated']})" if r else " HATA")
            )
            if not r:
                logger.warning(f"bureau_types {islem.code!r} update_item başarısız")
        else:
            try:
                ok = reference_lists.add_item("bureau_types", code=islem.code, name=islem.yeni)
            except reference_lists.DuplicateItemError as e:
                mesajlar.append(f"ATLANDI {islem.code}: {e}")
                continue
            mesajlar.append(f"{islem.code}: {islem.yeni!r} eklendi" if ok else f"{islem.code}: eklenemedi")
    return mesajlar


def _csv_yaz(dizin: Path, sonuc: AdimSonucu) -> Path:
    dizin.mkdir(parents=True, exist_ok=True)
    yol = dizin / f"{sonuc.adim}.csv"
    with open(yol, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["tablo", "kayit_id", "case_id", "tracking_no", "alan", "eski", "yeni", "kaynak"])
        for d in sonuc.degisiklikler:
            w.writerow([d.tablo, d.kayit_id, d.case_id, d.tracking_no, d.alan, d.eski, d.yeni, d.kaynak])
        for li in sonuc.liste_islemleri:
            w.writerow(["bureau_types", li.code, "", "", f"liste:{li.islem}", li.eski, li.yeni, "liste"])
    return yol


def _ozet_yaz(sonuc: AdimSonucu, csv_yolu: Path) -> None:
    print(f"\n=== Adım {sonuc.adim} — {sonuc.ad} ===")
    print(f"  satır: {sonuc.satir}  |  tekil (eski→yeni): {sonuc.tekil}  |  csv: {csv_yolu}")
    kaynaklar = Counter(d.kaynak for d in sonuc.degisiklikler)
    if kaynaklar:
        print("  kaynak: " + ", ".join(f"{k} {n}" for k, n in sorted(kaynaklar.items())))
    gorulen = set()
    for d in sonuc.degisiklikler:
        if (d.eski, d.yeni) in gorulen:
            continue
        gorulen.add((d.eski, d.yeni))
        print(f"    {d.tablo}.{d.alan}: {d.eski!r} → {d.yeni!r}")
        if len(gorulen) >= ORNEK_SAYISI:
            break
    for li in sonuc.liste_islemleri:
        print(f"    liste {li.islem} {li.code}: {li.eski!r} → {li.yeni!r}")
    for n in sonuc.notlar:
        print(f"  NOT: {n}")


def kos(fabrika, *, adimlar: Sequence[int] = tuple(ADIMLAR), apply: bool = False,
        kim: Optional[str] = None, cikti_dizini: Optional[Path] = None) -> KosuSonucu:
    """Seçili adımları hesaplar, raporlar; `apply` ise tek transaction'da yazar.

    Belge envanteri kapısı commit'ten ÖNCE aynı oturumda ölçülür: fark varsa
    rollback + `envanter_farki` dolu (çıkış kodu 2). Liste işlemleri (adım 6)
    yalnız commit başarılıysa ve ondan sonra koşar.
    """
    if apply and not kim:
        raise ValueError("--apply için --kim zorunlu (case_history.changed_by)")
    dizin = Path(cikti_dizini or VARSAYILAN_CIKTI)
    sonuclar: List[AdimSonucu] = []
    envanter_farki: Dict[str, Tuple[Any, Any]] = {}
    yazildi = False
    db = fabrika()
    try:
        once = belge_envanteri.snapshot(db)
        for adim in adimlar:
            sonuc = ADIMLAR[adim](db)
            sonuclar.append(sonuc)
            _ozet_yaz(sonuc, _csv_yaz(dizin, sonuc))
            if apply and sonuc.degisiklikler:
                _uygula(db, sonuc, kim or SOURCE)
        if apply:
            sonra = belge_envanteri.snapshot(db)
            envanter_farki = belge_envanteri.diff(once, sonra)
            if envanter_farki:
                db.rollback()
                logger.error("Yazım birliği GERİ ALINDI — " + belge_envanteri.bicimle(envanter_farki))
            else:
                db.commit()
                yazildi = True
        else:
            db.rollback()
    finally:
        db.close()

    liste_sonuclari: List[str] = []
    if yazildi:
        islemler = [li for s in sonuclar for li in s.liste_islemleri]
        liste_sonuclari = _liste_islemlerini_uygula(islemler)
    return KosuSonucu(sonuclar, yazildi, envanter_farki, liste_sonuclari)


def _adim_listesi(metin: Optional[str]) -> List[int]:
    if not metin:
        return list(ADIMLAR)
    secilen = []
    for parca in metin.split(","):
        parca = parca.strip()
        if not parca:
            continue
        if not parca.isdigit() or int(parca) not in ADIMLAR:
            raise argparse.ArgumentTypeError(f"bilinmeyen adım: {parca!r} (geçerli: {', '.join(map(str, ADIMLAR))})")
        if int(parca) not in secilen:
            secilen.append(int(parca))
    return secilen


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Yazım birliği — tek seferlik büyük/küçük harf dönüşümü (G160)")
    parser.add_argument("--apply", action="store_true", help="Değişiklikleri veritabanına yaz (varsayılan kuru koşu)")
    parser.add_argument("--kim", help="case_history.changed_by (--apply ile zorunlu)")
    parser.add_argument("--adim", type=_adim_listesi, default=None,
                        help="Virgüllü adım listesi, örn. 1,3 (varsayılan hepsi)")
    parser.add_argument("--cikti-dizini", default=VARSAYILAN_CIKTI, help=f"CSV dizini (varsayılan {VARSAYILAN_CIKTI})")
    args = parser.parse_args(argv)
    if args.apply and not args.kim:
        parser.error("--apply için --kim zorunlu")

    from database import SessionLocal
    from logging_setup import configure_logging   # Faz 2-B bekçisi: basicConfig YOK

    configure_logging()

    sonuc = kos(SessionLocal, adimlar=args.adim or list(ADIMLAR), apply=args.apply,
                kim=args.kim, cikti_dizini=Path(args.cikti_dizini))

    print("\n" + "=" * 60)
    print("Toplam satır: " + ", ".join(f"adım {a.adim}={a.satir}" for a in sonuc.adimlar)
          + f"  → {sonuc.toplam_satir}")
    if sonuc.envanter_farki:
        print(belge_envanteri.bicimle(sonuc.envanter_farki) + " — GERİ ALINDI")
    elif sonuc.yazildi:
        print(f"YAZILDI (changed_by={args.kim!r}, source={SOURCE!r}); belge envanteri DENK")
        for m in sonuc.liste_sonuclari:
            print(f"  liste: {m}")
    else:
        print("KURU KOŞU — hiçbir şey yazılmadı. Uygulamak için: --apply --kim <kullanıcı>")
    return sonuc.cikis_kodu


if __name__ == "__main__":
    sys.exit(main())
