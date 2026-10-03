#!/usr/bin/env python3
"""Kart içi taraf tekilleştirme — aynı kişi bir kartta TEK satır (03.10.2026).

Kullanıcı kararı (03.10.2026): "3. şahıs eski TKU mantığından kalan bir kavram;
müvekkil ya da karşı taraf olan kişi ayrıca 3. şahıs olarak da görünüyorsa 3. şahıs
satırı hatalıdır." Ünvan (Dr vb.) farkı ve tek hücrede çok isim de aynı temizliğin
konusudur. Tarama (lokal, 03.10): 14.395 kartın 952'sinde aynı kişi birden çok satırda.

Nedenler (ölçüm + kod):
* eski import (`import_excel_cases`, staging kopyası) müvekkili ayrıca "Diğer Davalı"
  (THIRD) yazmış, ad karşılaştırması yoktu (965 satır);
* kart birleştirme anahtarı `(tür, ad)` idi → bir kartta müvekkil, öbüründe sigortalı
  olan aynı hekim iki satır kaldı (`mukerrer_kart_birlestir`, 03.10'da düzeltildi);
* paketin "Karşı Taraf" sütunu müvekkil hekimi de sayıyor;
* `;` / `,` ile birleşik ad tek satır yazılmış, parçaları sonradan ayrıca eklenmiş.

Kart içinde sırayla:
1. **Çok adlı satır** (`party_check.split_party_names`, virgül açık): eksik parça aynı
   tür/rolle eklenir; birleşik satırın bağları (belge, föy, hizmet) İLK parçanın
   satırına taşınır; birleşik satır silinir. Sonu virgüllü tek ad yalnız temizlenir.
2. **Aynı kişi** (`normalize_party_key` eşit — ünvan, şirket eki, harf katlama):
   kalan = öncelikli tür (`party_check.TARAF_TUR_ONCELIGI`: müvekkil > karşı taraf >
   3. şahıs), eşitse bağı olan, sonra küçük id. Gidenin bağları kalana taşınır, kalanın
   boş kimlik alanları gidenden dolar; kalanın adı ve rolü DEĞİŞMEZ.
3. **Koruma:** kartın ofis no girdileri (müvekkil kodu + sigortalı bloğu,
   `services.ofis_no`) değişecekse kart ATLANIR — prod'da ofis no göçü koşmadı, göç
   sigortalıyı "Sigortalı"/"Diğer Davalı" satırlarından da okuyor. Belge–taraf bağ
   sayısı değişirse de kart atlanır (SET NULL tuzağı).
4. **Bulanık** (anahtar farklı, yazım yakın ya da biri ötekinin sözcük alt kümesi):
   OTOMATİK DEĞİL — `taraf_inceleme.csv`'ye düşer, insan karar verir.

Her kart KENDİ transaction'ında (02.10 kilit dersi: tek uzun transaction panel
yazmalarını düşürür). Yine de prod'da `--apply` mesai DIŞINDA; kuru koşu prod'da değil,
prod dump'ının kopyasında koşulur (CLAUDE.md "Prod'da mesai içinde toplu yazma yok").

    docker compose exec -T backend python scripts/taraf_tekillestir.py            # kuru koşu
    docker compose exec -T backend python scripts/taraf_tekillestir.py --kart 14579
    docker compose exec -T backend python scripts/taraf_tekillestir.py --apply --kim "ilke"
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ modülleri için

import models
from managers import case_hizmetleri, case_manager
from party_check import (
    _match_name_keys,
    _name_key,
    kurum_mu,
    normalize_party_key,
    normalize_person_name,
    split_party_names,
    taraf_tur_sirasi,
)
from services import belge_envanteri, ofis_no

logger = logging.getLogger("taraf_tekillestir")

SOURCE = "TARAF_TEKILLESTIRME"
VARSAYILAN_CIKTI = "/tmp/taraf_tekillestir"
#: Kurum adlarında bulanık eşleşme eşiği (difflib oranı, anahtar üzerinde). Yalnız
#: İNCELEME listesi; kişi adlarında eşik yok — `party_check` kelime bazlı kuralı geçerli.
KURUM_ESIK = 0.90
#: Kimlik alanları: kalan satırda boşsa giden satırdan dolar.
KIMLIK_ALANLARI: Tuple[str, ...] = ("client_id", "tc_no", "birth_year", "gender")

CIKIS_TAMAM = 0
CIKIS_ENVANTER = 2


@dataclass
class Islem:
    case_id: int
    tracking_no: str
    kural: str               # cok_adli | ad_temizligi | ayni_kisi:CLIENT+THIRD | ...
    islem: str               # SIL | EKLE | AD | YUKSELT
    taraf_id: Optional[int]
    ad: str
    tur: str
    rol: str
    kalan_id: Optional[int] = None
    kalan_ad: str = ""
    kalan_tur: str = ""
    kalan_rol: str = ""
    tasinan: str = ""        # "belge=1 foy=1 hizmet=2"


@dataclass
class Inceleme:
    case_id: int
    tracking_no: str
    sebep: str               # benzer_yazim | alt_kume | ofis_no_degisir | belge_bagi
    a_id: Optional[int] = None
    a_ad: str = ""
    a_tur_rol: str = ""
    b_id: Optional[int] = None
    b_ad: str = ""
    b_tur_rol: str = ""
    benzerlik: str = ""
    oneri: str = ""


@dataclass
class KosuSonucu:
    islemler: List[Islem] = field(default_factory=list)
    incelemeler: List[Inceleme] = field(default_factory=list)
    aday_kart: int = 0
    degisen_kart: int = 0
    atlanan_kart: int = 0
    yazildi: bool = False
    envanter_farki: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)

    @property
    def cikis_kodu(self) -> int:
        return CIKIS_ENVANTER if self.envanter_farki else CIKIS_TAMAM


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def _tur_rol(p: Any) -> str:
    return f"{p.party_type or ''}/{p.role or ''}"


def _duz(ad: Optional[str]) -> str:
    return " ".join((ad or "").split())


def _bulanik_ciftler(satirlar: Sequence[Any]) -> List[Tuple[Any, Any, str, float]]:
    """Anahtarı FARKLI ama yazımı yakın çiftler: (a, b, sebep, oran). Salt hesap.

    `satirlar`: `.id .name .party_type .role` taşıyan nesneler (ORM satırı ya da Row).
    """
    hazir = []
    for s in satirlar:
        anahtar = normalize_party_key(s.name or "")
        if anahtar:
            norm = normalize_person_name(s.name or "")
            hazir.append((s, anahtar, _name_key(norm), set(anahtar.split()), kurum_mu(s.name or "")))
    ciftler: List[Tuple[Any, Any, str, float]] = []
    for i, (a, ka, nka, ta, kurum_a) in enumerate(hazir):
        for b, kb, nkb, tb, kurum_b in hazir[i + 1:]:
            if ka == kb:
                continue
            kucuk, buyuk = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
            if len(kucuk) >= 2 and kucuk < buyuk:
                ciftler.append((a, b, "alt_kume", 1.0))
                continue
            oran = SequenceMatcher(None, ka, kb).ratio()
            if kurum_a and kurum_b:
                # Kurum adı: sözcük sayısı oynar ("Hiz." / "Hizmetleri") → dize oranı.
                # Sigorta şirketleri birbirine benzer ("Axa Sigorta" ↔ "Ak Sigorta") — gürültü.
                if "SIGORTA" in ta and "SIGORTA" in tb:
                    continue
                if oran >= KURUM_ESIK:
                    ciftler.append((a, b, "benzer_yazim", oran))
            elif not kurum_a and not kurum_b and _match_name_keys(nka, nkb) == "name_fuzzy":
                # Kişi adı: tanıdık sorguyla AYNI kelime bazlı kural — sözcük sayısı eşit ve
                # her sözcük kendi içinde 1-2 harf toleransla eşleşmeli. Yalnız soyadı ortak
                # iki kişi ("Erdal Şengel" ↔ "Erol Şengel") listeye girmez.
                ciftler.append((a, b, "benzer_yazim", oran))
    return ciftler


def _oneri(a: Any, b: Any) -> str:
    """İnceleme satırına yön: aynı listede iki benzer ad kardeş/eş olabilir."""
    if (a.party_type, a.role) != (b.party_type, b.role):
        return "muhtemelen aynı kişi (farklı tür/rol)"
    return "aynı tür ve rolde — iki ayrı kişi olabilir, belgeye bak"


def _yapilacak_var(satirlar: Sequence[Any]) -> bool:
    """Kartta kural 1 ya da 2'nin işi var mı? (ön eleme — ORM yüklemeden)"""
    gorulen = set()
    for s in satirlar:
        adlar = split_party_names(s.name, virgul=True)
        if len(adlar) > 1 or (adlar and adlar[0] != _duz(s.name)):
            return True
        anahtar = normalize_party_key(s.name or "")
        if anahtar and anahtar in gorulen:
            return True
        gorulen.add(anahtar)
    return False


def _aday_kartlar(db, kart_idleri: Optional[Iterable[int]]) -> List[int]:
    """İşi ya da inceleme çifti olan canlı kartlar — tek hafif sorgu, hesap Python'da."""
    sorgu = (
        db.query(models.CaseParty.id, models.CaseParty.case_id, models.CaseParty.name,
                 models.CaseParty.party_type, models.CaseParty.role)
        .join(models.Case, models.Case.id == models.CaseParty.case_id)
        .filter(models.Case.deleted_at.is_(None))
    )
    if kart_idleri is not None:
        sorgu = sorgu.filter(models.CaseParty.case_id.in_(sorted({int(k) for k in kart_idleri})))
    kartlar: Dict[int, List[Any]] = defaultdict(list)
    for satir in sorgu.order_by(models.CaseParty.id).all():
        kartlar[satir.case_id].append(satir)
    return sorted(cid for cid, satirlar in kartlar.items()
                  if _yapilacak_var(satirlar) or _bulanik_ciftler(satirlar))


def _ofis_no_imzasi(case: models.Case, kl: ofis_no.KodListeleri) -> Optional[Tuple[str, Optional[str]]]:
    """Kartın ofis no girdileri: (müvekkil kodu, sigortalı bloğu). Müvekkilsiz kart → None."""
    muvekkiller = [
        {"name": p.name, "category": p.client.category if p.client is not None else None}
        for p in case.parties if p.party_type == "CLIENT"
    ]
    try:
        kod, secilen = ofis_no.musteri_kodu(muvekkiller, kl)
    except ValueError:
        return None
    sigortali = None
    if ofis_no.sigortaci_mi(secilen.get("name"), secilen.get("category")):
        sigortali = ofis_no.sigortali_sec(case, kod_listeleri=kl)
    return kod, sigortali


def _belge_bagi_sayisi(db, case_id: int) -> int:
    return int(
        db.query(models.CaseDocument.id)
        .filter(models.CaseDocument.case_id == case_id, models.CaseDocument.case_party_id.isnot(None))
        .count()
    )


def _bagli_mi(db, party_id: int) -> bool:
    for model in (models.CaseFoy, models.CaseHizmeti, models.CaseDocument):
        if db.query(model.id).filter(model.case_party_id == party_id).first() is not None:
            return True
    return False


def _baglari_tasi(db, case: models.Case, eski: models.CaseParty, yeni: models.CaseParty) -> str:
    """Belge, föy ve hizmet bağlarını `eski` → `yeni` tarafa taşır; özet metni döner.

    Taraf satırı silinmeden ÖNCE çağrılır: belge FK'sı SET NULL (bağ sessizce kopardı),
    föy ve hizmet FK'ları RESTRICT (silme hata verirdi). Hizmet satırları tek yazma
    yolundan (`case_hizmetleri.tarafi_tasi`) geçer — kart özeti orada yenilenir.
    """
    belge = foy = 0
    for d in db.query(models.CaseDocument).filter(models.CaseDocument.case_party_id == eski.id).all():
        d.case_party_id = yeni.id
        belge += 1
    for f in db.query(models.CaseFoy).filter(models.CaseFoy.case_party_id == eski.id).all():
        f.case_party_id = yeni.id
        foy += 1
    hizmet = case_hizmetleri.tarafi_tasi(
        db, eski_party_id=eski.id, yeni_party_id=yeni.id, yeni_case_id=case.id)
    parcalar = [f"{ad}={n}" for ad, n in (("belge", belge), ("foy", foy),
                                           ("hizmet", hizmet["tasinan"]),
                                           ("hizmet_birlesen", hizmet["birlesen"])) if n]
    return " ".join(parcalar)


def _tarihce(db, case_id: int, eski: Optional[str], yeni: Optional[str], kim: str) -> None:
    db.add(models.CaseHistory(
        case_id=case_id, field_name="taraf", old_value=eski, new_value=yeni,
        changed_by=kim, source=SOURCE,
    ))


def _kisi_haritasi(case: models.Case) -> Dict[str, models.CaseParty]:
    """anahtar → kartın o kişiye ait satırı (öncelikli tür, sonra küçük id)."""
    harita: Dict[str, models.CaseParty] = {}
    for p in sorted(case.parties, key=lambda x: (taraf_tur_sirasi(x.party_type), x.id or 0)):
        anahtar = normalize_party_key(p.name or "")
        if anahtar:
            harita.setdefault(anahtar, p)
    return harita


def _sil(db, case: models.Case, giden: models.CaseParty, kalan: models.CaseParty, *,
         kural: str, kim: str) -> Islem:
    """`giden` satırı `kalan`a devreder ve siler (bağlar + boş kimlik alanları taşınır)."""
    tasinan = _baglari_tasi(db, case, giden, kalan)
    for alan in KIMLIK_ALANLARI:
        if getattr(kalan, alan) in (None, "") and getattr(giden, alan) not in (None, ""):
            setattr(kalan, alan, getattr(giden, alan))
    islem = Islem(case.id, case.tracking_no or "", kural, "SIL", giden.id, giden.name or "",
                  giden.party_type or "", giden.role or "", kalan.id, kalan.name or "",
                  kalan.party_type or "", kalan.role or "", tasinan)
    _tarihce(db, case.id, f"{giden.name} ({giden.role})", f"{kalan.name} ({kalan.role})", kim)
    db.flush()
    case.parties.remove(giden)                 # delete-orphan: yetim → silinir
    db.flush()
    return islem


# ─── Kart kuralları ──────────────────────────────────────────────────────────

def _cok_adlilari_bol(db, case: models.Case, kim: str) -> List[Islem]:
    """Kural 1: `;`/`,` ile çok kişi taşıyan satır kişi başına satıra çevrilir."""
    islemler: List[Islem] = []
    tno = case.tracking_no or ""
    for p in sorted(case.parties, key=lambda x: x.id or 0):
        adlar = split_party_names(p.name, virgul=True)
        if len(adlar) == 1 and adlar[0] != _duz(p.name):
            # Tek kişi, yalnız sondaki ayraç artığı ("Atilla Kurtay Dr.,")
            islemler.append(Islem(case.id, tno, "ad_temizligi", "AD", p.id, p.name or "",
                                  p.party_type or "", p.role or "", p.id, adlar[0],
                                  p.party_type or "", p.role or ""))
            _tarihce(db, case.id, f"{p.name} ({p.role})", f"{adlar[0]} ({p.role})", kim)
            p.name = adlar[0]
            continue
        if len(adlar) < 2:
            continue
        harita = _kisi_haritasi(case)
        ilk: Optional[models.CaseParty] = None
        for sira, ad in enumerate(adlar):
            satir = harita.get(normalize_party_key(ad))
            if satir is None or satir is p:
                satir = models.CaseParty(name=ad, role=p.role, party_type=p.party_type, client_id=None)
                case.parties.append(satir)
                db.flush()
                _tarihce(db, case.id, None, f"{ad} ({p.role})", kim)
                islemler.append(Islem(case.id, tno, "cok_adli", "EKLE", satir.id, ad,
                                      p.party_type or "", p.role or ""))
            elif taraf_tur_sirasi(p.party_type) < taraf_tur_sirasi(satir.party_type):
                # Parça kartta daha zayıf türde duruyor (ör. 3. şahıs), birleşik satır
                # müvekkil/karşı taraf → mevcut satır yerinde yükseltilir (bağları kopmaz).
                islemler.append(Islem(case.id, tno, "cok_adli", "YUKSELT", satir.id, satir.name or "",
                                      satir.party_type or "", satir.role or "", satir.id,
                                      satir.name or "", p.party_type or "", p.role or ""))
                _tarihce(db, case.id, f"{satir.name} ({satir.role})", f"{satir.name} ({p.role})", kim)
                satir.party_type, satir.role = p.party_type, p.role
            if sira == 0:
                ilk = satir
        assert ilk is not None
        islemler.append(_sil(db, case, p, ilk, kural="cok_adli", kim=kim))
    db.flush()
    return islemler


def _ayni_kisileri_birlestir(db, case: models.Case, kim: str) -> List[Islem]:
    """Kural 2: anahtarı eşit satırlar tek satıra iner (tür önceliği → bağ → küçük id)."""
    gruplar: Dict[str, List[models.CaseParty]] = defaultdict(list)
    for p in case.parties:
        anahtar = normalize_party_key(p.name or "")
        if anahtar:
            gruplar[anahtar].append(p)
    islemler: List[Islem] = []
    for anahtar in sorted(gruplar):
        grup = gruplar[anahtar]
        if len(grup) < 2:
            continue
        sirali = sorted(grup, key=lambda x: (taraf_tur_sirasi(x.party_type),
                                             0 if _bagli_mi(db, x.id) else 1, x.id or 0))
        kalan = sirali[0]
        for giden in sirali[1:]:
            kural = f"ayni_kisi:{kalan.party_type}+{giden.party_type}"
            islemler.append(_sil(db, case, giden, kalan, kural=kural, kim=kim))
    return islemler


def kart_tekillestir(db, case: models.Case, kim: str) -> List[Islem]:
    """Tek kartın kesin kurallarını AYNI oturumda uygular (flush eder, COMMIT ETMEZ)."""
    islemler = _cok_adlilari_bol(db, case, kim)
    islemler += _ayni_kisileri_birlestir(db, case, kim)
    if islemler:
        case_manager.refresh_missing_required(db, case)
        db.flush()
    return islemler


# ─── Koşu ────────────────────────────────────────────────────────────────────

def kos(fabrika, *, apply: bool = False, kim: Optional[str] = None,
        kart_idleri: Optional[Iterable[int]] = None,
        cikti_dizini: Optional[Path] = None) -> KosuSonucu:
    """Aday kartları tek tek işler; `apply` ise kart başına commit, değilse rollback.

    Kuru koşu da değişikliği oturumda UYGULAR ve geri alır — rapor, apply'ın yapacağının
    birebir ön izlemesidir (korumalar gerçek sonuca karşı ölçülür).
    """
    if apply and not kim:
        raise ValueError("--apply için --kim zorunlu (case_history.changed_by)")
    sonuc = KosuSonucu()
    db = fabrika()
    try:
        once = belge_envanteri.snapshot(db)
        kl = ofis_no.kod_listelerini_yukle(db)
        adaylar = _aday_kartlar(db, kart_idleri)
        sonuc.aday_kart = len(adaylar)
        for case_id in adaylar:
            case = db.get(models.Case, case_id)
            if case is None or case.deleted_at is not None:
                continue
            tno = case.tracking_no or ""
            imza_once = _ofis_no_imzasi(case, kl)
            belge_once = _belge_bagi_sayisi(db, case_id)
            islemler = kart_tekillestir(db, case, kim or SOURCE)
            engel: Optional[Inceleme] = None
            if islemler:
                imza_sonra = _ofis_no_imzasi(case, kl)
                if imza_sonra != imza_once:
                    engel = Inceleme(case_id, tno, "ofis_no_degisir",
                                     a_ad=str(imza_once), b_ad=str(imza_sonra),
                                     oneri="kart atlandı: sigortalı bloğunun kaynağı silinecek satır")
                elif _belge_bagi_sayisi(db, case_id) != belge_once:
                    engel = Inceleme(case_id, tno, "belge_bagi")
            if engel is not None:
                db.rollback()
                sonuc.atlanan_kart += 1
                sonuc.incelemeler.append(engel)
                logger.warning(f"Kart #{case_id} {tno} ATLANDI: {engel.sebep} "
                               f"({engel.a_ad} → {engel.b_ad})")
                case = db.get(models.Case, case_id)
                islemler = []
            for a, b, sebep, oran in _bulanik_ciftler(sorted(case.parties, key=lambda x: x.id or 0)):
                sonuc.incelemeler.append(Inceleme(
                    case_id, tno, sebep, a.id, a.name or "", _tur_rol(a),
                    b.id, b.name or "", _tur_rol(b), f"{oran:.2f}", _oneri(a, b)))
            if islemler:
                sonuc.islemler.extend(islemler)
                sonuc.degisen_kart += 1
            if apply:
                db.commit()
            else:
                db.rollback()
        if apply:
            sonuc.yazildi = True
            fark = belge_envanteri.diff(once, belge_envanteri.snapshot(db))
            # Bağ imzası BİLEREK kapsam dışı: belge aynı kartta bir taraf satırından
            # ötekine taşınır (imza değişir); kapı sayımlardır — hiçbir bağ kopmamalı.
            sonuc.envanter_farki = {k: v for k, v in fark.items() if k != "bag_imzasi"}
            if sonuc.envanter_farki:
                logger.error("Taraf tekilleştirme sonrası " + belge_envanteri.bicimle(sonuc.envanter_farki))
    finally:
        db.close()
    if cikti_dizini is not None:
        _csv_yaz(Path(cikti_dizini), sonuc)
    return sonuc


def _csv_yaz(dizin: Path, sonuc: KosuSonucu) -> None:
    dizin.mkdir(parents=True, exist_ok=True)
    with open(dizin / "taraf_tekillestir_islemler.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "tracking_no", "kural", "islem", "taraf_id", "ad", "tur", "rol",
                    "kalan_id", "kalan_ad", "kalan_tur", "kalan_rol", "tasinan"])
        for i in sonuc.islemler:
            w.writerow([i.case_id, i.tracking_no, i.kural, i.islem, i.taraf_id, i.ad, i.tur, i.rol,
                        i.kalan_id, i.kalan_ad, i.kalan_tur, i.kalan_rol, i.tasinan])
    with open(dizin / "taraf_inceleme.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "tracking_no", "sebep", "a_id", "a_ad", "a_tur_rol",
                    "b_id", "b_ad", "b_tur_rol", "benzerlik", "oneri"])
        for n in sonuc.incelemeler:
            w.writerow([n.case_id, n.tracking_no, n.sebep, n.a_id, n.a_ad, n.a_tur_rol,
                        n.b_id, n.b_ad, n.b_tur_rol, n.benzerlik, n.oneri])


def _ozet_yaz(sonuc: KosuSonucu, dizin: Path) -> None:
    print(f"Aday kart: {sonuc.aday_kart}  |  değişen kart: {sonuc.degisen_kart}  |  "
          f"atlanan (koruma): {sonuc.atlanan_kart}")
    sayim = Counter((i.kural, i.islem) for i in sonuc.islemler)
    for (kural, islem), n in sorted(sayim.items(), key=lambda kv: -kv[1]):
        print(f"  {kural:<28} {islem:<8} {n}")
    bagli = sum(1 for i in sonuc.islemler if i.islem == "SIL" and i.tasinan)
    print(f"  bağ taşınan silme: {bagli}")
    inceleme = Counter(n.sebep for n in sonuc.incelemeler)
    print("İnceleme listesi: " + (", ".join(f"{k} {n}" for k, n in sorted(inceleme.items())) or "boş"))
    print(f"CSV: {dizin / 'taraf_tekillestir_islemler.csv'}  |  {dizin / 'taraf_inceleme.csv'}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Kart içi taraf tekilleştirme (03.10.2026)")
    parser.add_argument("--apply", action="store_true", help="Değişiklikleri veritabanına yaz (varsayılan kuru koşu)")
    parser.add_argument("--kim", help="case_history.changed_by (--apply ile zorunlu)")
    parser.add_argument("--kart", type=int, action="append", help="Yalnız bu kart id'si (tekrarlanabilir)")
    parser.add_argument("--cikti-dizini", default=VARSAYILAN_CIKTI, help=f"CSV dizini (varsayılan {VARSAYILAN_CIKTI})")
    args = parser.parse_args(argv)
    if args.apply and not args.kim:
        parser.error("--apply için --kim zorunlu")

    from database import SessionLocal
    from logging_setup import configure_logging   # Faz 2-B bekçisi: basicConfig YOK

    configure_logging()

    dizin = Path(args.cikti_dizini)
    sonuc = kos(SessionLocal, apply=args.apply, kim=args.kim, kart_idleri=args.kart, cikti_dizini=dizin)
    print("=" * 60)
    _ozet_yaz(sonuc, dizin)
    if sonuc.envanter_farki:
        print(belge_envanteri.bicimle(sonuc.envanter_farki) + " — İNCELE (kart başına commit edildi)")
    elif sonuc.yazildi:
        print(f"YAZILDI (changed_by={args.kim!r}, source={SOURCE!r}); belge sayımları DENK")
    else:
        print("KURU KOŞU — hiçbir şey yazılmadı. Uygulamak için: --apply --kim <kullanıcı>")
    return sonuc.cikis_kodu


if __name__ == "__main__":
    sys.exit(main())
