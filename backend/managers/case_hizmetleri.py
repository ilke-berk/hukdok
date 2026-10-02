"""Hizmet kaydının (`case_hizmetleri`) TEK yazma yolu (G248).

Kullanıcı kararı (01.10.2026): hizmet türü kartın değil **kart × müvekkil
tarafı** çiftinin özelliğidir — "bu kartta bu müvekkile bu hizmet verildi"
(muhasebe); aynı müvekkile birden çok hizmet mümkündür. Desen `managers/foy_map`
(G063) ve `managers/stage_decisions` (G062) ile aynıdır: satırlar + tek yazma
yolu + karttaki türetilmiş tek kolon.

Sözleşme (G249-G253 buna yazar):

* **İki satır türü.** `foy_id` DOLU = föy kaynaklı satır: yalnız aktarım yazar
  (`foydan_yaz`), API'den silinemez/değiştirilemez (`FoyKaynakliSatir` → 409).
  `foy_id` NULL = elle satır: `elle_ekle` / `elle_sil` / `elle_kumesini_yaz`.
* **Taraf kendi kartının MÜVEKKİLİDİR.** `case_party_id` aynı karta ait ve
  `party_type='CLIENT'` olmalı (`GecersizHizmetTarafi`).
* **Hizmet adı kapalı listedendir** (`service_types`): doğrulama
  `case_manager.validated_event_list_value` ile ORTAK (boşluk normalize, tam ad
  eşleşmesi, `active` filtresi yok, liste BOŞSA doğrulama atlanır) — listede
  olmayan ad `GecersizHizmetTuru`.
* **Föyün verdiği hizmet elle tekrar yazılmaz.** Aynı (müvekkil, hizmet) föy
  satırında zaten varsa `elle_ekle` yeni satır açmaz (mevcut föy satırını
  döner), `elle_kumesini_yaz` o adı "var" sayar. Tersi serbest: `foydan_yaz`
  mevcut elle satıra DOKUNMAZ (kullanıcının girdiği kayıt silinmez; özet
  DISTINCT olduğu için kart özetinde tekrar görünmez).
* **Türetilmiş özet.** `cases.hizmet_turu` = kartın satırlarındaki DISTINCT
  adlar, Türkçe alfabetik, `" ; "` ile; satır yoksa NULL. Tek yazıcı
  `ozeti_yenile`; satır ekleyen/silen/taşıyan her fonksiyon çağırır. Hizmet
  satırı HİÇ yazılmamış kartta özet yenilenmez (aktarımın eski tek değeri
  durur) — özet yalnız satıra dokunan yolda tazelenir.
* **Tarihçe.** Elle ekleme/silme ve föy satırının yerinde değişmesi/silinmesi
  `case_history`'ye `field_name='hizmet'` ile düşer ("Müvekkil — Hizmet").
  Föy satırının İLK yazımı tarihçesizdir (geriye dönük doldurma 8.400 satır;
  kaynak föyün kendisidir).
* Fonksiyonlar COMMIT ETMEZ (flush eder) — işlem sınırı çağıranındır.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from db_errors import is_unique_violation

logger = logging.getLogger("CaseManager")

#: Özetin ayracı — çok değerli hücre sözleşmesiyle aynı (`services.multi_value.SEPARATOR`).
AYRAC = " ; "
#: `case_history.field_name` — hizmet satırı değişikliklerinin tek etiketi.
TARIHCE_ALANI = "hizmet"
MUVEKKIL_TARAF_TURU = "CLIENT"
KAYNAK_FOY = "foy"
KAYNAK_ELLE = "elle"

# Kolon sınırları modelden okunur, elle tekrarlanmaz (foy_map._LIMITS gerekçesi).
_SINIRLAR: Dict[str, int] = {
    _kolon.name: _uzunluk
    for _kolon in models.CaseHizmeti.__table__.columns
    if (_uzunluk := getattr(_kolon.type, "length", None))
}
_AD_SINIRI: int = _SINIRLAR["hizmet_turu"]
_KAYNAK_SINIRI: int = _SINIRLAR["source"]
_YAZAN_SINIRI: int = _SINIRLAR["created_by"]
_CHUNK = 1000

# `foydan_yaz` sonuç durumları ve atlama/silme sebepleri (G249 satır raporu bunları okur).
FOY_EKLENDI = "EKLENDI"
FOY_GUNCELLENDI = "GUNCELLENDI"
FOY_DEGISMEDI = "DEGISMEDI"
FOY_SILINDI = "SILINDI"
FOY_ATLANDI = "ATLANDI"
SEBEP_KAPSAM_DISI = "KAPSAM_DISI"
SEBEP_TARAF_YOK = "TARAF_YOK"
SEBEP_MUVEKKIL_DEGIL = "MUVEKKIL_DEGIL"
SEBEP_HIZMET_BOS = "HIZMET_BOS"
SEBEP_LISTEDE_YOK = "LISTEDE_YOK"


class HizmetHatasi(ValueError):
    """Hizmet kaydı yazımında istemci hatası (route 4xx'e çevirir; ERROR basılmaz)."""


class GecersizHizmetTarafi(HizmetHatasi):
    """Taraf bu kartın tarafı değil ya da müvekkil (CLIENT) değil."""


class GecersizHizmetTuru(HizmetHatasi):
    """Hizmet adı boş ya da `service_types` kapalı listesinde yok."""


class FoyKaynakliSatir(HizmetHatasi):
    """Föy kaynaklı satır API'den silinemez/değiştirilemez (yalnız aktarım yazar)."""


@dataclass
class FoySonucu:
    """`foydan_yaz` dönüşü: ne oldu (`durum`), neden (`sebep`), satır (varsa)."""
    durum: str
    sebep: Optional[str] = None
    satir: Any = None


# ─── yardımcılar ─────────────────────────────────────────────────────────────

_TR_ALFABE = {harf: sira for sira, harf in enumerate("abcçdefgğhıijklmnoöprsştuüvyz")}


def _tr_sira_anahtari(ad: str) -> Tuple[Tuple[Tuple[int, int], ...], str]:
    """Türkçe alfabetik sıra (ç/ğ/ı/ö/ş/ü yerinde; harf dışı karakter harften önce)."""
    kucuk = ad.replace("I", "ı").replace("İ", "i").lower()
    return tuple((1, _TR_ALFABE[h]) if h in _TR_ALFABE else (0, ord(h)) for h in kucuk), ad


def ozet_metni(adlar: Iterable[str]) -> Optional[str]:
    """Ad kümesinden kart özeti: DISTINCT, Türkçe alfabetik, `" ; "` birleşik; boş → None."""
    tekil = sorted({a for a in adlar if a}, key=_tr_sira_anahtari)
    return AYRAC.join(tekil) if tekil else None


def _kirp(deger: Optional[str], sinir: int) -> Optional[str]:
    if deger is None:
        return None
    metin = " ".join(str(deger).split())
    return metin[:sinir] if metin else None


def _cakisma_mi(exc: IntegrityError) -> bool:
    """UNIQUE ihlali mi? (`foy_map._is_duplicate_violation` ile aynı kural: SQLSTATE
    taşımayan diyalektte — sqlite — çakışma varsayılır, çağıran satırı okumayı dener.)"""
    if is_unique_violation(exc):
        return True
    orig = getattr(exc, "orig", None)
    return (getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)) is None


def _kart_id(db: Session, case: Any) -> int:
    if case.id is None:
        db.flush()          # FK için kart id'si şart (foy_map.upsert_foy deseni)
    return int(case.id)


def _dogrulanmis_taraf(db: Session, case_id: int, case_party_id: Any) -> Any:
    """Taraf AYNI kartın müvekkili olmalı (`foy_map._validated_party` + CLIENT şartı)."""
    party: Any = db.get(models.CaseParty, case_party_id) if case_party_id is not None else None
    if party is None or party.case_id != case_id:
        raise GecersizHizmetTarafi(
            f"Taraf bu dava kartına ait değil (taraf {case_party_id}, dava {case_id})."
        )
    if party.party_type != MUVEKKIL_TARAF_TURU:
        raise GecersizHizmetTarafi(
            f"Hizmet yalnız müvekkil tarafına yazılır: \"{party.name}\" müvekkil değil."
        )
    return party


def dogrulanmis_hizmet_adi(db: Session, ad: Any) -> str:
    """Hizmet adını `service_types` kapalı listesine karşı doğrular (kanonik ad döner).

    Kapı `case_manager.validated_event_list_value` ile ORTAK — kart alanı ile
    hizmet satırı aynı listeyi aynı normalizasyonla denetler. Boş ad ya da
    listede olmayan ad `GecersizHizmetTuru`.
    """
    # Döngüsel import: case_manager bu modülü modül düzeyinde import eder.
    from managers import case_manager, stage_decisions

    try:
        temiz = case_manager.validated_event_list_value(db, "hizmet_turu", ad)
    except stage_decisions.InvalidDecisionStatusError as exc:
        raise GecersizHizmetTuru(
            f"Hizmet türü listede yok: \"{' '.join(str(ad).split())}\"."
        ) from exc
    if not temiz:
        raise GecersizHizmetTuru("Hizmet türü boş olamaz.")
    if len(temiz) > _AD_SINIRI:
        raise GecersizHizmetTuru(f"Hizmet türü en fazla {_AD_SINIRI} karakter olabilir.")
    return str(temiz)


def _tarihce(db: Session, case_id: int, eski: str, yeni: str, *,
             changed_by: Optional[str], source: Optional[str]) -> None:
    db.add(models.CaseHistory(
        case_id=case_id, field_name=TARIHCE_ALANI, old_value=eski, new_value=yeni,
        changed_by=_kirp(changed_by, 200), source=_kirp(source, 300),
    ))


def _etiket(taraf_adi: Optional[str], adlar: Iterable[str]) -> str:
    """Tarihçe değeri: "Müvekkil — Hizmet [; Hizmet…]"; hizmet yoksa boş metin."""
    ozet = ozet_metni(adlar)
    return f"{taraf_adi or '?'} — {ozet}" if ozet else ""


def _taraf_adi(db: Session, case_party_id: Any) -> Optional[str]:
    party: Any = db.get(models.CaseParty, case_party_id) if case_party_id is not None else None
    return party.name if party is not None else None


# ─── okuma ───────────────────────────────────────────────────────────────────

def kart_satirlari(db: Session, case_id: int) -> List[Any]:
    """Kartın hizmet satırları (ORM), yazılma sırasıyla."""
    return (
        db.query(models.CaseHizmeti)
        .filter(models.CaseHizmeti.case_id == case_id)
        .order_by(models.CaseHizmeti.id)
        .all()
    )


def satir_dict(row: Any, taraf_adlari: Dict[int, str], foy_sistem_nolari: Dict[int, str]) -> dict:
    """Hizmet satırının API gösterimi (kart `hizmetler` listesi ve uçlar AYNI sözleşme)."""
    return {
        "id": row.id,
        "case_party_id": row.case_party_id,
        "muvekkil_adi": taraf_adlari.get(row.case_party_id),
        "hizmet_turu": row.hizmet_turu,
        "kaynak": KAYNAK_FOY if row.foy_id is not None else KAYNAK_ELLE,
        "foy_id": row.foy_id,
        "sistem_no": foy_sistem_nolari.get(row.foy_id) if row.foy_id is not None else None,
    }


def satirlari_sirala(satirlar: Iterable[dict]) -> List[dict]:
    """Gösterim sırası: müvekkil adı → hizmet adı (Türkçe) → föy satırı önce → id."""
    return sorted(satirlar, key=lambda s: (
        _tr_sira_anahtari(s.get("muvekkil_adi") or ""),
        _tr_sira_anahtari(s["hizmet_turu"]),
        s["kaynak"] != KAYNAK_FOY,
        s["id"],
    ))


def kart_hizmet_listesi(db: Session, case_id: int) -> List[dict]:
    """Kartın `hizmetler` listesi — müvekkil adı ve (föy satırında) SistemNo ile."""
    satirlar = kart_satirlari(db, case_id)
    if not satirlar:
        return []
    taraf_adlari = {
        pid: ad for pid, ad in
        db.query(models.CaseParty.id, models.CaseParty.name)
        .filter(models.CaseParty.case_id == case_id).all()
    }
    foy_idleri = {s.foy_id for s in satirlar if s.foy_id is not None}
    foy_nolari: Dict[int, str] = {}
    if foy_idleri:
        foy_nolari = {
            fid: no for fid, no in
            db.query(models.CaseFoy.id, models.CaseFoy.sistem_no)
            .filter(models.CaseFoy.id.in_(foy_idleri)).all()
        }
    return satirlari_sirala(satir_dict(s, taraf_adlari, foy_nolari) for s in satirlar)


# ─── türetilmiş özet ─────────────────────────────────────────────────────────

def ozeti_yenile(db: Session, case_id: int) -> Optional[str]:
    """`cases.hizmet_turu` özetini satırlardan yeniden kurar — TEK yazıcı.

    Bekleyen satır değişiklikleri önce flush edilir (oturumlar autoflush'sız).
    Değer aynıysa kolona dokunulmaz (`updated_at` oynamaz).
    """
    db.flush()
    adlar = [
        ad for (ad,) in
        db.query(models.CaseHizmeti.hizmet_turu)
        .filter(models.CaseHizmeti.case_id == case_id).distinct().all()
    ]
    ozet = ozet_metni(adlar)
    case: Any = db.get(models.Case, case_id)
    if case is not None and case.hizmet_turu != ozet:
        case.hizmet_turu = ozet
        db.flush()
    return ozet


def ozetleri_yenile(db: Session, case_idleri: Iterable[int]) -> int:
    """Toplu özet yenileme (liste adı değişimi binlerce kartı etkileyebilir).

    Kart satırlarını ORM'e YÜKLEMEZ: parça başına iki SELECT + yalnız özeti
    değişen kart için tek UPDATE. Değişen kart sayısını döner.
    """
    db.flush()
    idler = sorted({int(c) for c in case_idleri if c is not None})
    degisen = 0
    for i in range(0, len(idler), _CHUNK):
        parca = idler[i:i + _CHUNK]
        adlar: Dict[int, Set[str]] = {cid: set() for cid in parca}
        for cid, ad in (
            db.query(models.CaseHizmeti.case_id, models.CaseHizmeti.hizmet_turu)
            .filter(models.CaseHizmeti.case_id.in_(parca)).distinct().all()
        ):
            adlar[cid].add(ad)
        mevcut: Dict[int, Optional[str]] = {
            cid: ozet for cid, ozet in
            db.query(models.Case.id, models.Case.hizmet_turu)
            .filter(models.Case.id.in_(parca)).all()
        }
        for cid in parca:
            ozet = ozet_metni(adlar[cid])
            if cid in mevcut and mevcut[cid] != ozet:
                db.query(models.Case).filter(models.Case.id == cid).update(
                    {models.Case.hizmet_turu: ozet}, synchronize_session="fetch"
                )
                degisen += 1
    return degisen


# ─── elle satırlar ───────────────────────────────────────────────────────────

def _muvekkil_satirlari(db: Session, case_id: int, case_party_id: int) -> List[Any]:
    return (
        db.query(models.CaseHizmeti)
        .filter(
            models.CaseHizmeti.case_id == case_id,
            models.CaseHizmeti.case_party_id == case_party_id,
        )
        .order_by(models.CaseHizmeti.id)
        .all()
    )


def _elle_satir_yaz(db: Session, case_id: int, case_party_id: int, ad: str, *,
                    changed_by: Optional[str], source: Optional[str]) -> Tuple[Any, bool]:
    """Elle satırı SAVEPOINT içinde yazar; yarışta (kısmi UNIQUE) mevcut satırı döner."""
    row = models.CaseHizmeti(
        case_id=case_id, case_party_id=case_party_id, hizmet_turu=ad, foy_id=None,
        source=_kirp(source, _KAYNAK_SINIRI), created_by=_kirp(changed_by, _YAZAN_SINIRI),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row, True
    except IntegrityError as exc:
        if not _cakisma_mi(exc):
            raise
        mevcut = (
            db.query(models.CaseHizmeti)
            .filter(
                models.CaseHizmeti.case_id == case_id,
                models.CaseHizmeti.case_party_id == case_party_id,
                models.CaseHizmeti.hizmet_turu == ad,
                models.CaseHizmeti.foy_id.is_(None),
            )
            .first()
        )
        if mevcut is None:
            raise           # çakışma değilmiş (FK/NOT NULL) — gerçek hatayı gizleme
        return mevcut, False


def elle_ekle(db: Session, case: Any, case_party_id: int, hizmet_turu: Any, *,
              changed_by: Optional[str] = None, source: Optional[str] = None) -> Tuple[Any, bool]:
    """Müvekkile elle hizmet satırı ekler — İDEMPOTENT.

    Dönüş `(satır, yeni_mi)`. Aynı (müvekkil, hizmet) zaten varsa — elle ya da
    föy kaynaklı — yeni satır açılmaz, mevcut satır `False` ile döner.
    """
    case_id = _kart_id(db, case)
    party = _dogrulanmis_taraf(db, case_id, case_party_id)
    ad = dogrulanmis_hizmet_adi(db, hizmet_turu)
    db.flush()
    ayni = [s for s in _muvekkil_satirlari(db, case_id, party.id) if s.hizmet_turu == ad]
    if ayni:
        elle = [s for s in ayni if s.foy_id is None]
        return (elle[0] if elle else ayni[0]), False
    row, yeni = _elle_satir_yaz(db, case_id, party.id, ad, changed_by=changed_by, source=source)
    if yeni:
        _tarihce(db, case_id, "", _etiket(party.name, [ad]), changed_by=changed_by, source=source)
        ozeti_yenile(db, case_id)
    return row, yeni


def elle_sil(db: Session, case: Any, hizmet_id: int, *,
             changed_by: Optional[str] = None, source: Optional[str] = None) -> bool:
    """Elle satırı siler (hard-delete + tarihçe). Satır bu kartta yoksa `False`;
    föy kaynaklı satır `FoyKaynakliSatir`."""
    case_id = _kart_id(db, case)
    row: Any = db.get(models.CaseHizmeti, hizmet_id)
    if row is None or row.case_id != case_id:
        return False
    if row.foy_id is not None:
        raise FoyKaynakliSatir(
            "Bu hizmet kaydı veri paketindeki föyden geliyor; panelden silinemez. "
            "Düzeltme veri teslimiyle yapılır."
        )
    eski = _etiket(_taraf_adi(db, row.case_party_id), [row.hizmet_turu])
    db.delete(row)
    _tarihce(db, case_id, eski, "", changed_by=changed_by, source=source)
    ozeti_yenile(db, case_id)
    return True


def elle_kumesini_yaz(db: Session, case: Any, case_party_id: int, adlar: Iterable[Any], *,
                      changed_by: Optional[str] = None, source: Optional[str] = None) -> bool:
    """Bir müvekkilin ELLE hizmet kümesini verilen kümeye getirir (çoklu seçim, 02.10).

    * Her ad listeye karşı ÖNCE doğrulanır — biri bile geçersizse hiçbir şey yazılmaz.
    * Kümede olup müvekkilde (elle ya da föyden) bulunmayan ad eklenir.
    * Kümede olmayan ELLE satır silinir; föy kaynaklı satıra DOKUNULMAZ (föyün adı
      kümede olsa da olmasa da).
    * Değişiklik `case_history`'ye TEK kayıtla düşer (eski/yeni: müvekkilin elle
      hizmetleri `" ; "` birleşik); aynı küme ikinci kez → kayıt yok, `False`.
    """
    case_id = _kart_id(db, case)
    party = _dogrulanmis_taraf(db, case_id, case_party_id)
    istenen: List[str] = []
    for ham in adlar or []:
        ad = dogrulanmis_hizmet_adi(db, ham)
        if ad not in istenen:
            istenen.append(ad)

    db.flush()
    mevcut = _muvekkil_satirlari(db, case_id, party.id)
    foyden = {s.hizmet_turu for s in mevcut if s.foy_id is not None}
    elle = {s.hizmet_turu: s for s in mevcut if s.foy_id is None}

    silinecek = [s for ad, s in elle.items() if ad not in istenen]
    eklenecek = [ad for ad in istenen if ad not in elle and ad not in foyden]
    if not silinecek and not eklenecek:
        return False

    eski = _etiket(party.name, elle.keys())
    for s in silinecek:
        db.delete(s)
    db.flush()
    for ad in eklenecek:
        _elle_satir_yaz(db, case_id, party.id, ad, changed_by=changed_by, source=source)
    kalan = (set(elle) - {s.hizmet_turu for s in silinecek}) | set(eklenecek)
    _tarihce(db, case_id, eski, _etiket(party.name, kalan), changed_by=changed_by, source=source)
    ozeti_yenile(db, case_id)
    return True


def taraflarin_elle_satirlarini_sil(db: Session, case: Any, party_idleri: Sequence[int], *,
                                    changed_by: Optional[str] = None,
                                    source: Optional[str] = None) -> int:
    """Karttan düşürülen müvekkil taraflarının ELLE hizmet satırlarını siler (tarihçeli).

    `update_case` taraf satırını silmeden ÖNCE çağırır (FK RESTRICT). Föy kaynaklı
    satıra dokunulmaz — o taraf zaten silinemez (`case_foys` + bu tablo RESTRICT).
    Silinen satır sayısını döner; satır silindiyse özet yenilenir.
    """
    if not party_idleri:
        return 0
    case_id = _kart_id(db, case)
    satirlar: List[Any] = (
        db.query(models.CaseHizmeti)
        .filter(
            models.CaseHizmeti.case_id == case_id,
            models.CaseHizmeti.case_party_id.in_(list(party_idleri)),
            models.CaseHizmeti.foy_id.is_(None),
        )
        .order_by(models.CaseHizmeti.id)
        .all()
    )
    if not satirlar:
        return 0
    taraf_bazli: Dict[int, List[Any]] = {}
    for s in satirlar:
        taraf_bazli.setdefault(s.case_party_id, []).append(s)
    for pid, grup in taraf_bazli.items():
        eski = _etiket(_taraf_adi(db, pid), [s.hizmet_turu for s in grup])
        for s in grup:
            db.delete(s)
        _tarihce(db, case_id, eski, "", changed_by=changed_by, source=source)
    ozeti_yenile(db, case_id)
    return len(satirlar)


# ─── föy kaynaklı satır (aktarım) ────────────────────────────────────────────

def _foy_satiri(db: Session, foy_id: int) -> Any:
    return (
        db.query(models.CaseHizmeti)
        .filter(models.CaseHizmeti.foy_id == foy_id)
        .first()
    )


def _foy_satirini_sil(db: Session, row: Any, *, source: Optional[str]) -> None:
    case_id = row.case_id
    eski = _etiket(_taraf_adi(db, row.case_party_id), [row.hizmet_turu])
    db.delete(row)
    _tarihce(db, case_id, eski, "", changed_by=source, source=source)
    ozeti_yenile(db, case_id)


def foydan_yaz(db: Session, foy: Any, *, source: Optional[str] = None) -> FoySonucu:
    """Föyün hizmet satırını yazar — upsert, anahtar `foy_id` (aktarımın yolu, G249).

    * Föy kapsam dışı (`kapsam_durumu` dolu) → satırı varsa silinir (tarihçeli);
      işaret kalkınca bir sonraki çağrı satırı geri yazar.
    * Föyün müvekkili yok / kartının müvekkili değil ya da hizmeti boş / listede
      yok → satır YAZILMAZ (`ATLANDI` + sebep; çağıran satır raporuna UYARI
      düşer). Mevcut satır yerinde kalır (yeniden adlandırılmış hizmet: paket
      eski adı taşıdıkça bu yola düşer, satır yeni adıyla durur) — TEK istisna
      föy başka karta taşınmışsa: eski kartta kalan satır silinir.
    * Föyün kartı, müvekkili ya da hizmeti değiştiyse satır YERİNDE güncellenir
      (tarihçeli); hiçbiri değişmediyse `DEGISMEDI`.

    `source` verilmezse föyün kendi `source`'u (teslim imzası) yazılır.
    """
    if foy.id is None:
        db.flush()
    imza = _kirp(source or foy.source, _KAYNAK_SINIRI)
    mevcut = _foy_satiri(db, foy.id)

    def _atla(sebep: str) -> FoySonucu:
        if mevcut is not None and mevcut.case_id != foy.case_id:
            _foy_satirini_sil(db, mevcut, source=imza)
            return FoySonucu(FOY_SILINDI, sebep)
        return FoySonucu(FOY_ATLANDI, sebep, mevcut)

    if foy.kapsam_durumu:
        if mevcut is not None:
            _foy_satirini_sil(db, mevcut, source=imza)
            return FoySonucu(FOY_SILINDI, SEBEP_KAPSAM_DISI)
        return FoySonucu(FOY_ATLANDI, SEBEP_KAPSAM_DISI)

    party: Any = db.get(models.CaseParty, foy.case_party_id) if foy.case_party_id is not None else None
    if party is None or party.case_id != foy.case_id:
        return _atla(SEBEP_TARAF_YOK)
    if party.party_type != MUVEKKIL_TARAF_TURU:
        return _atla(SEBEP_MUVEKKIL_DEGIL)
    if not _kirp(foy.hizmet_turu, _AD_SINIRI):
        return _atla(SEBEP_HIZMET_BOS)
    try:
        ad = dogrulanmis_hizmet_adi(db, foy.hizmet_turu)
    except GecersizHizmetTuru:
        return _atla(SEBEP_LISTEDE_YOK)

    if mevcut is None:
        row = models.CaseHizmeti(
            case_id=foy.case_id, case_party_id=party.id, hizmet_turu=ad,
            foy_id=foy.id, source=imza, created_by=imza,
        )
        db.add(row)
        ozeti_yenile(db, foy.case_id)
        return FoySonucu(FOY_EKLENDI, None, row)

    if (mevcut.case_id, mevcut.case_party_id, mevcut.hizmet_turu) == (foy.case_id, party.id, ad):
        return FoySonucu(FOY_DEGISMEDI, None, mevcut)

    eski_kart = mevcut.case_id
    eski = _etiket(_taraf_adi(db, mevcut.case_party_id), [mevcut.hizmet_turu])
    mevcut.case_id = foy.case_id
    mevcut.case_party_id = party.id
    mevcut.hizmet_turu = ad
    mevcut.source = imza
    yeni = _etiket(party.name, [ad])
    if eski_kart != foy.case_id:
        _tarihce(db, eski_kart, eski, "", changed_by=imza, source=imza)
        _tarihce(db, foy.case_id, "", yeni, changed_by=imza, source=imza)
        ozeti_yenile(db, eski_kart)
    else:
        _tarihce(db, foy.case_id, eski, yeni, changed_by=imza, source=imza)
    ozeti_yenile(db, foy.case_id)
    return FoySonucu(FOY_GUNCELLENDI, None, mevcut)


# ─── kart birleştirme / ayırma (script yolları, G249) ────────────────────────

def tarafi_tasi(db: Session, *, eski_party_id: int, yeni_party_id: int,
                yeni_case_id: int) -> Dict[str, int]:
    """Bir tarafın TÜM hizmet satırlarını başka tarafa/karta taşır.

    Kart birleştirmede iki yol da buradan geçer: taraf satırı karta taşındıysa
    `eski_party_id == yeni_party_id` (yalnız kart değişir); taraf hedef kartın
    mevcut tarafına eşlendiyse satırlar o tarafa geçer. Hedefte aynı (müvekkil,
    hizmet) ELLE satırı zaten varsa taşınan elle satır birleşir (silinir) —
    kısmi UNIQUE çakışmaz. Föy satırı her zaman taşınır. Etkilenen kartların
    özeti yenilenir. Dönüş: `{"tasinan": n, "birlesen": m}`.
    """
    db.flush()
    satirlar: List[Any] = (
        db.query(models.CaseHizmeti)
        .filter(models.CaseHizmeti.case_party_id == eski_party_id)
        .order_by(models.CaseHizmeti.id)
        .all()
    )
    sonuc = {"tasinan": 0, "birlesen": 0}
    if not satirlar:
        return sonuc
    hedef_elle = {
        s.hizmet_turu for s in
        db.query(models.CaseHizmeti)
        .filter(
            models.CaseHizmeti.case_id == yeni_case_id,
            models.CaseHizmeti.case_party_id == yeni_party_id,
            models.CaseHizmeti.foy_id.is_(None),
        ).all()
        if s not in satirlar
    }
    etkilenen = {yeni_case_id}
    for s in satirlar:
        etkilenen.add(s.case_id)
        if s.foy_id is None and s.hizmet_turu in hedef_elle:
            db.delete(s)
            sonuc["birlesen"] += 1
            continue
        s.case_id = yeni_case_id
        s.case_party_id = yeni_party_id
        if s.foy_id is None:
            hedef_elle.add(s.hizmet_turu)
        sonuc["tasinan"] += 1
    db.flush()
    for cid in sorted(etkilenen):
        ozeti_yenile(db, cid)
    return sonuc


# ─── liste adı değişimi (reference_lists yayılımı) ───────────────────────────

def liste_adi_degisti(db: Session, eski_adlar: Sequence[str], yeni_ad: str) -> int:
    """`service_types` öğesi yeniden adlandırıldı / başka öğeye taşındı.

    Eski adı (yazım varyantlarıyla) taşıyan satırlar yeni ada çevrilir. Çevirme
    kısmi UNIQUE'i çiğneyecekse — aynı (kart, müvekkil) için yeni adlı ELLE satır
    zaten var ya da iki varyant tek ada iniyor — fazlalık elle satır BİRLEŞİR
    (silinir; bilgi kaybı yok, aynı kayıt tek satıra iner). Föy satırı hep
    çevrilir. Sonra etkilenen kartların özeti toplu yenilenir. Etkilenen satır
    sayısını döner (çevrilen + birleşen). Tarihçe yazılmaz — liste yayılımı
    hiçbir kolonda tarihçe yazmıyor (`reference_lists._apply_to_dependents`).
    """
    eskiler = [a for a in dict.fromkeys(eski_adlar or []) if a and a != yeni_ad]
    if not eskiler or not yeni_ad:
        return 0
    db.flush()
    kartlar = {
        cid for (cid,) in
        db.query(models.CaseHizmeti.case_id)
        .filter(models.CaseHizmeti.hizmet_turu.in_(eskiler)).distinct().all()
    }
    if not kartlar:
        return 0

    # Birleşme: (kart, müvekkil) başına yeni ada inecek elle satırlardan yalnız biri kalır.
    elle: List[Any] = (
        db.query(models.CaseHizmeti)
        .filter(
            models.CaseHizmeti.foy_id.is_(None),
            models.CaseHizmeti.hizmet_turu.in_([*eskiler, yeni_ad]),
            models.CaseHizmeti.case_id.in_(
                db.query(models.CaseHizmeti.case_id)
                .filter(models.CaseHizmeti.hizmet_turu.in_(eskiler))
            ),
        )
        .order_by(models.CaseHizmeti.id)
        .all()
    )
    gruplar: Dict[Tuple[int, int], List[Any]] = {}
    for s in elle:
        gruplar.setdefault((s.case_id, s.case_party_id), []).append(s)
    birlesen = 0
    for grup in gruplar.values():
        if len(grup) < 2:
            continue
        kalan = next((s for s in grup if s.hizmet_turu == yeni_ad), grup[0])
        for s in grup:
            if s is not kalan:
                db.delete(s)
                birlesen += 1
    db.flush()

    cevrilen = (
        db.query(models.CaseHizmeti)
        .filter(models.CaseHizmeti.hizmet_turu.in_(eskiler))
        .update({models.CaseHizmeti.hizmet_turu: yeni_ad}, synchronize_session="fetch")
    )
    ozetleri_yenile(db, kartlar)
    if birlesen:
        logger.info(
            f"case_hizmetleri: {eskiler[0]!r} → {yeni_ad!r} taşımasında {birlesen} elle satır birleşti"
        )
    return int(cevrilen) + birlesen
