#!/usr/bin/env python3
"""Veri ekibinin 12.09.2026 cevabındaki kart düzeltmeleri (G179) — tek koşu, dört adım.

Kaynak: Av. Ayşe Gül Hanyaloğlu, 12.09 16:30 — "09.09 yazınıza, 11.09 'girmeyen 18
satır' dosyanıza ve 11.09 dava kartları listenize cevabımız" + Ek-3
(`HUKDOK_CEVAP_EKI_3_2026-09-12.xlsx`) + Ek-2 › 06. Kullanıcı kararı 13.09:
"ekibin önerisi gibi olsun" (kart modeli) + "devam". Ekler repoya GİRMEZ; Ek-3
yolu `--ek3` ile verilir, kalan düzeltmeler bu dosyada tablo hâlinde (kaynak
satırı her kalemin yanında) — prod'da aynı script + aynı xlsx koşar.

Adımlar (hepsi tek transaction; `--apply` yoksa sonunda geri alınır, rapor yine basılır):

1. **Çift kart birleştirme** — Ek-3 › 01 (37 föy: eski 30.07 kartı föysüz, 05.09'da
   `.00` eki yüzünden ikinci kart açılmış) + §3/Ek-2 › 03'teki özdeş çiftler. KALAN =
   30.07 kartı / çiftin ilki (ekibin master köprüsü o numarayı tanır), mükerrer =
   05.09 kartı / ikincisi. Taşıma yolu `scripts/mukerrer_kart_birlestir.birlestir`
   (belge koruma, taraf tekilleştirme, soft delete). Ön koşul reddederse (müvekkil
   kümeleri farklı — H-15496: 13565 iki müvekkilli Anadolu kartı) Ek-3 › 01 çiftinde
   yalnız o FÖY 30.07 kartına taşınır, kart birleştirilmez; sabit çiftte ret kalır.
2. **Föy taşıma** — Ek-3 › 02'de "Önerdiğimiz kart" dolu satırlar (8 föy): föy, esas +
   mahkeme + türü tutan karta geçer (`case_foys.case_id`; taraf bağı sıfırlanır — hedef
   kartta aynı adlı CLIENT varsa ona bağlanır). İki kartta da `case_history` notu.
3. **Kart düzeltmeleri** — Ek-2 › 06 (12 kart; 9635 ve 13002 lokalde zaten doğru → 0
   değişiklik) + §3 konu/hizmet türü (6 kart; 28 "Rücu" kartı LİSTE OLMADAN
   uygulanmaz — `bureau_type=Rücu` olan föysüz AXA/Sompo kartlarının çoğu hukuken
   "İtirazın İptali", ekibe sorulacak). 14393 "kontrol" (MİCRO teyidi) uygulanmaz.
   Değer zaten eşitse dokunulmaz (ikinci koşu 0). Konu adı `case_subjects`, hizmet
   türü `service_types` listesinde OLMALI — yoksa satır atlanır (rapor).
4. **Hatalı kopya / test kartlarını kapat** — üst mahkeme aşamasının hatalı kopyası
   olan 4 HK kartı (§3): belgeleri ekibin gösterdiği GERÇEK dosyanın kartına taşınır
   (belge koruma şartı — belge silinmez, `case_party_id` sıfırlanır), sonra kart
   soft-delete (routes/cases.py `api_delete_case` deseni). SMOKE-… + "Test İçin"
   kartları (4) hedefsiz soft-delete (belgeler kartla birlikte gizlenir).

İkinci koşu 0 değişiklik: birleşmiş çift `deleted_at` + `delete_reason` ile tanınır,
taşınmış föy hedefte, eşit alan atlanır, silinmiş kart atlanır.

    docker compose exec -T backend python scripts/ekip_cevabi_1209.py \\
        --ek3 /app/calibration-data/_g179/HUKDOK_CEVAP_EKI_3_2026-09-12.xlsx        # kuru koşu
    docker compose exec -T backend python scripts/ekip_cevabi_1209.py \\
        --ek3 … --apply --kim ilke                                                 # yazar
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from managers import case_manager
from managers.reference_lists import tr_upper
from party_check import normalize_party_key
from scripts import mukerrer_kart_birlestir as mb

logger = logging.getLogger("EkipCevabi1209")
DEGISTIREN = "ekip_cevabi_1209"
KAYNAK = "ekip cevabı 12.09.2026"

EK3_CIFT_SAYFASI = "01_AYNI_DAVA_IKI_KART"
EK3_TASIMA_SAYFASI = "02_BASKA_ASAMA_KARTI"

# ─── Sabit tablolar (kaynak: mail §3 / Ek-2 › 03 / Ek-2 › 06) ────────────────
# (kalan_id, mükerrer_id, kaynak) — "her çiftin ikincisini kapatmanızı öneririz".
SABIT_CIFTLER: Tuple[Tuple[int, int, str], ...] = (
    (5338, 5570, "§3 mükerrer: S3.AXA…2653 / …2654"),
    (5340, 5571, "§3 mükerrer: S3.AXA…0059 / …0060"),
    (5295, 5567, "§3 mükerrer: S7.SOMPO…0045 / …0046"),
    (5307, 5066, "§3 mükerrer: X1.SEDADKENT…0030 / …0029 (ikincisi klasörsüz)"),
    (5057, 5568, "Ek-2 › 03: H-16294 tek föy, iki özdeş kart (5568 lokalde zaten kapalı)"),
    (14321, 14322, "Ek-2 › 03: H-16336 tek föy, iki özdeş kart (esas/mahkeme farklıysa ret beklenir)"),
)

# (kart_id, alan, yeni değer, kanıt). Alanlar:
#   klasor_ekle — `klasor_no_2` listesine parça ekler (varsa dokunmaz)
#   klasor      — `klasor_no_2` değerini değiştirir
#   court/esas_no/subject/hizmet_turu — düz kart alanı (subject/hizmet_turu listede olmalı)
#   muvekkil    — CLIENT tarafının adı (+ `clients` bağı adla bulunursa)
SABIT_DUZELTMELER: Tuple[Tuple[int, str, Optional[str], str], ...] = (
    (745, "muvekkil", "Ak Sigorta A.Ş.",
     "Ek-2 › 06: H-6589 (3.1400.00) Ak 2022 listesi ↔ Ak hukuk no 123065; kart 745 müvekkili AXA yazılmış"),
    (1154, "muvekkil", "Anadolu Anonim Türk Sigorta Şirketi",
     "Ek-2 › 06: DN-11927 (9.032.00) büronun Anadolu listesi; kart 1154 müvekkili AXA yazılmış"),
    (13002, "klasor_ekle", "2.554.00", "Ek-2 › 06: kök 27 → 2 (20.07.2026), 27.001.00 → 2.554.00 (H-5441)"),
    (3946, "klasor_ekle", "2.555.00", "Ek-2 › 06: 27.002.00 → 2.555.00 (H-5628)"),
    (2850, "klasor_ekle", "2.556.00", "Ek-2 › 06: 27.003.00 → 2.556.00 (H-2954)"),
    (1763, "klasor_ekle", "2.557.00", "Ek-2 › 06: 27.004.00 → 2.557.00 (H-1557)"),
    (3021, "klasor_ekle", "2.558.00", "Ek-2 › 06: 27.005.00 → 2.558.00 (id-13744)"),
    (9635, "esas_no", "2015/11027", "Ek-2 › 06: İstanbul 2. İdare E.2015/11027 K.2016/1368 karar künyesi"),
    (4181, "klasor", "1735.002", "Ek-2 › 06: ARB-15159 işçi alacağı arabuluculuğu (03.08.2023); 1735.001.00 dava dosyasının (H-15052, kart 4094)"),
    (4181, "court", None, "Ek-2 › 06: arabuluculuk — mahkeme yok (İstanbul 1. Tüketici 2023/202 = H-15052'nin)"),
    (4181, "esas_no", None, "Ek-2 › 06: arabuluculuk — esas yok (2023/202 = H-15052'nin)"),
    (2223, "klasor", "2.051.00", "Ek-2 › 06: id-10225 Quick · Batman İdare 2018/740; 1464.001.00 Dr. Mehmet Emrah Çıplak'ın (H-10329)"),
    (5297, "subject", "Hakem Kararına İtiraz", "§3: S3.AXA…2484 → Hakem Kararına İtiraz"),
    (4949, "subject", "İdari İşlemin İptali", "§3: D1.B_TAYMUR…0002 → İdari İşlemin İptali (olumsuz kanaat notu)"),
    (5282, "subject", "Rücuen Alacak (Tıbbi Kötü Uygulama)", "§3: S2.ANADOLU…0901 → Rücuen Alacak (Tıbbi Kötü Uygulama Sigorta Poliçesinden Kaynaklanan)"),
    (4953, "subject", "Tazminat (Tıbbi Kötü Uygulama)", "§3: S3.AXA…3205 → Tazminat (Tıbbi Kötü Uygulama …) (kartta Delil Tespiti)"),
    (5279, "subject", "Tazminat (Tıbbi Kötü Uygulama)", "§3: H1.K_OZDEMIR…0002 hasta dosyası → Tazminat (Tıbbi Kötü Uygulama …)"),
    (4504, "hizmet_turu", "Vekaletsiz Takip", "§3: S2.ANADOLU…1094 → Vekaletsiz Takip (Anadolu dosyalarında Lexis hizmeti yok)"),
)

# (kopya_id, hedef_id | None, sebep). Hedef doluysa belgeler oraya taşınır.
SABIT_KAPATMALAR: Tuple[Tuple[int, Optional[int], str], ...] = (
    (14337, 939, "§3 hatalı kopya: HK-837834 = H-6000/H-6001'in İstanbul BAM 18. HD istinaf esası (2020/1759); kart S3.L_ARSLAN…0001"),
    (14338, 698, "§3 hatalı kopya: HK-110273 = id-13750'nin Ankara BİM 10. İDD istinaf esası (2021/3718); kart D1.G_USTUN…0002"),
    (14339, 2797, "§3 hatalı kopya: HK-915104 = id-6265'in İstanbul BİM 7. İDD istinaf esası (2022/1863); 'karşı taraf' Selçuk Gülen daire başkanı; kart D1.K_COKTU…0004"),
    (14340, 291, "§3 hatalı kopya: X1.IBRAHIM_SERHAT…0001 = id-11025'in Danıştay 10. Daire temyiz esası (2022/6162); kart S1.I_KAYIRAN…0001"),
    (14362, None, "§3 deneme verisi: SMOKE-1785412361 (30.07 dışa aktarımında yok)"),
    (14363, None, "§3 deneme verisi: SMOKE-1785412573"),
    (14364, None, "§3 deneme verisi: SMOKE-1785412573-2"),
    (14335, None, "§3 deneme verisi: X1.I_KUTLUK…0001.CEZAA.00000-2 ('Test İçin' · 9/9)"),
)


@dataclass
class Kalem:
    adim: str
    hedef: str
    sonuc: str            # YAPILDI | ATLANDI | RET
    aciklama: str = ""


@dataclass
class Sonuc:
    kalemler: List[Kalem] = field(default_factory=list)

    def ekle(self, adim: str, hedef: str, sonuc: str, aciklama: str = "") -> None:
        self.kalemler.append(Kalem(adim, hedef, sonuc, aciklama))
        (logger.info if sonuc == "YAPILDI" else logger.warning)(f"[{adim}] {hedef}: {sonuc} {aciklama}".rstrip())

    def sayim(self, adim: str, sonuc: str) -> int:
        return sum(1 for k in self.kalemler if k.adim == adim and k.sonuc == sonuc)


# ─── Ek-3 okuma ──────────────────────────────────────────────────────────────

def _sayfa(wb, ad: str):
    for ws in wb.worksheets:
        if ws.title.strip() == ad:
            return ws
    raise ValueError(f"Ek-3'te {ad!r} sayfası yok — sayfalar: {[w.title for w in wb.worksheets]}")


def _kolon(basliklar: Sequence, *adaylar: str) -> int:
    normal = [" ".join(str(b or "").split()).casefold() for b in basliklar]
    for aday in adaylar:
        aday_n = " ".join(aday.split()).casefold()
        for i, b in enumerate(normal):
            if b == aday_n:
                return i
    raise ValueError(f"Ek-3 başlığı bulunamadı: {adaylar} — başlıklar: {basliklar}")


def _tam_sayi(deger) -> Optional[int]:
    if deger in (None, ""):
        return None
    try:
        return int(str(deger).strip())
    except ValueError:
        return None


def ek3_oku(yol: Path) -> Tuple[List[Tuple[str, int, int]], List[Tuple[str, int]]]:
    """(çiftler [(SistemNo, kalan=30.07 kartı, mükerrer=föyün kartı)], taşımalar [(SistemNo, hedef)])."""
    import openpyxl
    wb = openpyxl.load_workbook(yol, data_only=True, read_only=True)
    ws = _sayfa(wb, EK3_CIFT_SAYFASI)
    satirlar = list(ws.iter_rows(values_only=True))
    basliklar = satirlar[0]
    i_sn = _kolon(basliklar, "SistemNo")
    i_kalan = _kolon(basliklar, "30.07'deki kart")
    i_mukerrer = _kolon(basliklar, "Föyün bağlı olduğu kart")
    ciftler: List[Tuple[str, int, int]] = []
    for satir in satirlar[1:]:
        sn, kalan, mukerrer = satir[i_sn], _tam_sayi(satir[i_kalan]), _tam_sayi(satir[i_mukerrer])
        if sn and kalan and mukerrer:
            ciftler.append((str(sn).strip(), kalan, mukerrer))
    ws = _sayfa(wb, EK3_TASIMA_SAYFASI)
    satirlar = list(ws.iter_rows(values_only=True))
    basliklar = satirlar[0]
    i_sn = _kolon(basliklar, "SistemNo")
    i_hedef = _kolon(basliklar, "Önerdiğimiz kart")
    tasimalar: List[Tuple[str, int]] = []
    for satir in satirlar[1:]:
        sn, hedef = satir[i_sn], _tam_sayi(satir[i_hedef])
        if sn and hedef:
            tasimalar.append((str(sn).strip(), hedef))
    wb.close()
    return ciftler, tasimalar


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def _tarihce(db, case_id: int, alan: str, eski, yeni, kim: str, kanit: str) -> None:
    db.add(models.CaseHistory(
        case_id=case_id, field_name=alan,
        old_value=None if eski is None else str(eski), new_value=None if yeni is None else str(yeni),
        changed_by=DEGISTIREN, source=f"{KAYNAK} ({kim}): {kanit}"[:300],
    ))


def _canli_kart(db, case_id: int) -> Optional[models.Case]:
    kart = db.get(models.Case, case_id)
    return kart if kart is not None and kart.deleted_at is None else None


def _client_taraf(db, case_id: int, ad: str) -> Optional[models.CaseParty]:
    anahtar = normalize_party_key(ad)
    for p in db.query(models.CaseParty).filter(models.CaseParty.case_id == case_id,
                                              models.CaseParty.party_type == "CLIENT").all():
        if normalize_party_key(p.name or "") == anahtar:
            return p
    return None


def _foy_tasi(db, foy: models.CaseFoy, hedef: models.Case, kim: str, kanit: str) -> None:
    """Föyü hedef karta geçirir; taraf bağı hedefte aynı adlı CLIENT'a, yoksa sıfır."""
    eski_id = foy.case_id
    yeni_taraf: Optional[int] = None
    if foy.case_party_id:
        eski_taraf = db.get(models.CaseParty, foy.case_party_id)
        if eski_taraf is not None and eski_taraf.name:
            hedef_taraf = _client_taraf(db, hedef.id, eski_taraf.name)
            yeni_taraf = hedef_taraf.id if hedef_taraf is not None else None
    foy.case_id = hedef.id
    foy.case_party_id = yeni_taraf
    db.flush()
    _tarihce(db, eski_id, "foy_tasima", foy.sistem_no, f"→ #{hedef.id} {hedef.tracking_no}", kim, kanit)
    _tarihce(db, hedef.id, "foy_tasima", f"#{eski_id}", foy.sistem_no, kim, kanit)
    eski = db.get(models.Case, eski_id)
    if eski is not None:
        case_manager.refresh_missing_required(db, eski)
    case_manager.refresh_missing_required(db, hedef)


# ─── Adım 1: çift kart birleştirme ───────────────────────────────────────────

def _birlesmis_mi(mukerrer: models.Case, kalan_id: int) -> bool:
    return mukerrer.deleted_at is not None and f"#{kalan_id} " in (mukerrer.delete_reason or "")


def ciftleri_birlestir(db, ciftler: Sequence[Tuple[str, int, int]], sabit: Sequence[Tuple[int, int, str]],
                       *, kim: str, sonuc: Sonuc) -> None:
    for sn, kalan_id, mukerrer_id in ciftler:
        hedef = f"{sn}: #{kalan_id} ← #{mukerrer_id}"
        kalan, mukerrer = db.get(models.Case, kalan_id), db.get(models.Case, mukerrer_id)
        if kalan is None or mukerrer is None:
            sonuc.ekle("cift", hedef, "RET", "kart bulunamadı")
            continue
        if _birlesmis_mi(mukerrer, kalan_id):
            sonuc.ekle("cift", hedef, "ATLANDI", "zaten birleşmiş")
            continue
        with db.begin_nested():
            b = mb.birlestir(db, kalan, mukerrer, kim=kim, sebep_etiketi="Ek-3 › 01 aynı dava için iki kart (.00)")
        if not b.ret:
            sonuc.ekle("cift", hedef, "YAPILDI", f"taşınan={b.tasinan}")
            continue
        # Ret: kart birleşmez (müvekkil kümeleri farklı vb.) — yalnız föy 30.07 kartına
        foy = db.query(models.CaseFoy).filter(models.CaseFoy.sistem_no == sn).one_or_none()
        if foy is None:
            sonuc.ekle("cift", hedef, "RET", f"{b.ret}; föy {sn} yok")
        elif foy.case_id == kalan_id:
            sonuc.ekle("cift", hedef, "ATLANDI", f"{b.ret}; föy zaten #{kalan_id}'de")
        elif kalan.deleted_at is not None:
            sonuc.ekle("cift", hedef, "RET", f"{b.ret}; 30.07 kartı silinmiş")
        else:
            _foy_tasi(db, foy, kalan, kim, f"Ek-3 › 01 {sn}: kart birleşmedi ({b.ret}); föy 30.07 kartına")
            sonuc.ekle("cift", hedef, "YAPILDI", f"kart birleşmedi ({b.ret}) → yalnız föy taşındı")
    for kalan_id, mukerrer_id, kanit in sabit:
        hedef = f"#{kalan_id} ← #{mukerrer_id}"
        kalan, mukerrer = db.get(models.Case, kalan_id), db.get(models.Case, mukerrer_id)
        if kalan is None or mukerrer is None:
            sonuc.ekle("cift", hedef, "RET", "kart bulunamadı")
            continue
        if mukerrer.deleted_at is not None:
            sonuc.ekle("cift", hedef, "ATLANDI", f"mükerrer zaten kapalı ({mukerrer.delete_reason!r})")
            continue
        with db.begin_nested():
            b = mb.birlestir(db, kalan, mukerrer, kim=kim, sebep_etiketi=f"Mükerrer kart ({kanit})")
        sonuc.ekle("cift", hedef, "RET" if b.ret else "YAPILDI", b.ret or f"{kanit}; taşınan={b.tasinan}")


# ─── Adım 2: föy taşıma ──────────────────────────────────────────────────────

def foyleri_tasi(db, tasimalar: Sequence[Tuple[str, int]], *, kim: str, sonuc: Sonuc) -> None:
    for sn, hedef_id in tasimalar:
        hedef_metin = f"{sn} → #{hedef_id}"
        foy = db.query(models.CaseFoy).filter(models.CaseFoy.sistem_no == sn).one_or_none()
        hedef = _canli_kart(db, hedef_id)
        if foy is None or hedef is None:
            sonuc.ekle("foy", hedef_metin, "RET", "föy yok" if foy is None else "hedef kart yok/silinmiş")
            continue
        if foy.case_id == hedef_id:
            sonuc.ekle("foy", hedef_metin, "ATLANDI", "zaten hedefte")
            continue
        _foy_tasi(db, foy, hedef, kim, "Ek-3 › 02: föyün esas + mahkeme + türüyle tutan kart")
        sonuc.ekle("foy", hedef_metin, "YAPILDI", f"#{foy.case_id} ← eski kart")


# ─── Adım 3: kart düzeltmeleri ───────────────────────────────────────────────

def _liste_adi(db, model, ad: str) -> Optional[str]:
    """Liste tablosunda adı (harf duyarsız) bulur, kanonik yazımı döner."""
    for satir in db.query(model.name).all():
        if tr_upper(satir[0] or "") == tr_upper(ad):
            return satir[0]
    return None


def kartlari_duzelt(db, duzeltmeler: Sequence[Tuple[int, str, Optional[str], str]], *, kim: str, sonuc: Sonuc) -> None:
    for case_id, alan, yeni, kanit in duzeltmeler:
        hedef = f"#{case_id} {alan}"
        kart = _canli_kart(db, case_id)
        if kart is None:
            sonuc.ekle("duzeltme", hedef, "RET", "kart yok/silinmiş")
            continue
        if alan == "muvekkil":
            assert yeni is not None
            taraf = _client_taraf(db, case_id, yeni)
            if taraf is not None:
                sonuc.ekle("duzeltme", hedef, "ATLANDI", f"müvekkil zaten {yeni!r}")
                continue
            adaylar = [p for p in kart.parties if p.party_type == "CLIENT"]
            if len(adaylar) != 1:
                sonuc.ekle("duzeltme", hedef, "RET", f"CLIENT sayısı {len(adaylar)} — tek olmalı")
                continue
            taraf = adaylar[0]
            eski = taraf.name
            taraf.name = yeni
            client = (db.query(models.Client).filter(models.Client.deleted_at.is_(None))
                      .filter(func.lower(models.Client.name) == yeni.lower()).first())
            if client is None:
                for c in db.query(models.Client).filter(models.Client.deleted_at.is_(None)).all():
                    if normalize_party_key(c.name or "") == normalize_party_key(yeni):
                        client = c
                        break
            taraf.client_id = client.id if client is not None else None
            _tarihce(db, case_id, "muvekkil", eski, yeni, kim, kanit)
            case_manager.refresh_missing_required(db, kart)
            sonuc.ekle("duzeltme", hedef, "YAPILDI", f"{eski!r} → {yeni!r}" + (f" (client #{client.id})" if client else ""))
            continue
        if alan == "klasor_ekle":
            assert yeni is not None
            parcalar = [" ".join(p.split()) for p in (kart.klasor_no_2 or "").split(";") if p.strip()]
            if tr_upper(yeni) in {tr_upper(p) for p in parcalar}:
                sonuc.ekle("duzeltme", hedef, "ATLANDI", f"{yeni!r} zaten listede")
                continue
            eski = kart.klasor_no_2
            kart.klasor_no_2 = ";".join(parcalar + [yeni])
            _tarihce(db, case_id, "klasor_no_2", eski, kart.klasor_no_2, kim, kanit)
            sonuc.ekle("duzeltme", hedef, "YAPILDI", f"{eski!r} → {kart.klasor_no_2!r}")
            continue
        kolon = "klasor_no_2" if alan == "klasor" else alan
        if kolon not in {"klasor_no_2", "court", "esas_no", "subject", "hizmet_turu"}:
            sonuc.ekle("duzeltme", hedef, "RET", f"bilinmeyen alan {alan!r}")
            continue
        if yeni is not None and kolon in ("subject", "hizmet_turu"):
            model = models.CaseSubject if kolon == "subject" else models.ServiceType
            kanonik = _liste_adi(db, model, yeni)
            if kanonik is None:
                sonuc.ekle("duzeltme", hedef, "RET", f"{yeni!r} listede yok ({model.__tablename__})")
                continue
            yeni = kanonik
        eski = getattr(kart, kolon)
        if (eski or None) == (yeni or None):
            sonuc.ekle("duzeltme", hedef, "ATLANDI", f"zaten {yeni!r}")
            continue
        if kolon == "esas_no":
            # Türetilmiş kolon: tek yazma yolu esas tarihçesi (E8) — boşaltma dahil
            # (değer boşsa kolon temizlenir, tarihçe satırları silinmez). Aşama
            # varsayılan YEREL: iki kalem de yerel esas (9635 karar künyesi, 4181 boşaltma).
            case_manager.sync_current_esas(db, kart, yeni, court=kart.court,
                                           source=f"{DEGISTIREN} ({kim})")
        else:
            setattr(kart, kolon, yeni)
        _tarihce(db, case_id, kolon, eski, yeni, kim, kanit)
        case_manager.refresh_missing_required(db, kart)
        sonuc.ekle("duzeltme", hedef, "YAPILDI", f"{eski!r} → {yeni!r}")


# ─── Adım 4: kopya / test kartlarını kapat ───────────────────────────────────

def kartlari_kapat(db, kapatmalar: Sequence[Tuple[int, Optional[int], str]], *, kim: str, sonuc: Sonuc) -> None:
    for kopya_id, hedef_id, sebep in kapatmalar:
        hedef_metin = f"#{kopya_id}" + (f" → belgeler #{hedef_id}" if hedef_id else "")
        kopya = db.get(models.Case, kopya_id)
        if kopya is None:
            sonuc.ekle("kapatma", hedef_metin, "RET", "kart yok")
            continue
        if kopya.deleted_at is not None:
            sonuc.ekle("kapatma", hedef_metin, "ATLANDI", f"zaten kapalı ({kopya.delete_reason!r})")
            continue
        tasinan = 0
        if hedef_id is not None:
            hedef = _canli_kart(db, hedef_id)
            if hedef is None:
                sonuc.ekle("kapatma", hedef_metin, "RET", "hedef kart yok/silinmiş")
                continue
            for d in list(kopya.documents):
                kopya.documents.remove(d)
                hedef.documents.append(d)
                d.case_party_id = None            # kopyanın tarafı — hedefte karşılığı yok
                tasinan += 1
            if tasinan:
                _tarihce(db, hedef.id, "belge_tasima", f"#{kopya_id} {kopya.tracking_no}", f"{tasinan} belge", kim, sebep)
                case_manager.refresh_missing_required(db, hedef)
        kopya.deleted_at = func.now()
        kopya.deleted_by = kim
        kopya.delete_reason = f"{KAYNAK}: {sebep}"[:500]
        kopya.active = False
        _tarihce(db, kopya_id, "kapatma", kopya.tracking_no, f"belge→#{hedef_id}" if hedef_id else "soft delete", kim, sebep)
        db.flush()
        sonuc.ekle("kapatma", hedef_metin, "YAPILDI", f"{tasinan} belge taşındı; {sebep}")


# ─── Koşu ────────────────────────────────────────────────────────────────────

def kos(session_factory, *, ek3: Optional[Path], apply: bool = False, kim: str = DEGISTIREN,
        ciftler: Optional[Sequence[Tuple[str, int, int]]] = None,
        tasimalar: Optional[Sequence[Tuple[str, int]]] = None,
        sabit_ciftler: Sequence[Tuple[int, int, str]] = SABIT_CIFTLER,
        duzeltmeler: Sequence[Tuple[int, str, Optional[str], str]] = SABIT_DUZELTMELER,
        kapatmalar: Sequence[Tuple[int, Optional[int], str]] = SABIT_KAPATMALAR) -> Sonuc:
    """Dört adımı tek transaction'da koşar; `apply=False` sonunda geri alır."""
    if ek3 is not None:
        ek3_ciftler, ek3_tasimalar = ek3_oku(ek3)
        ciftler = list(ek3_ciftler) if ciftler is None else list(ciftler)
        tasimalar = list(ek3_tasimalar) if tasimalar is None else list(tasimalar)
    sonuc = Sonuc()
    db = session_factory()
    try:
        ciftleri_birlestir(db, ciftler or [], sabit_ciftler, kim=kim, sonuc=sonuc)
        foyleri_tasi(db, tasimalar or [], kim=kim, sonuc=sonuc)
        kartlari_duzelt(db, duzeltmeler, kim=kim, sonuc=sonuc)
        kartlari_kapat(db, kapatmalar, kim=kim, sonuc=sonuc)
        if apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    return sonuc


def ozet_metni(sonuc: Sonuc, *, apply: bool) -> str:
    satirlar = ["Ekip cevabı 12.09 düzeltmeleri — " + ("YAZILDI" if apply else "KURU KOŞU (geri alındı)")]
    for adim, ad in (("cift", "çift kart"), ("foy", "föy taşıma"), ("duzeltme", "kart düzeltme"), ("kapatma", "kapatma")):
        satirlar.append(f"  {ad:14}: {sonuc.sayim(adim, 'YAPILDI')} yapıldı · {sonuc.sayim(adim, 'ATLANDI')} atlandı · "
                        f"{sonuc.sayim(adim, 'RET')} ret")
    for k in sonuc.kalemler:
        if k.sonuc != "YAPILDI" or k.adim != "cift":
            satirlar.append(f"    [{k.adim}] {k.hedef}: {k.sonuc} {k.aciklama}".rstrip())
    return "\n".join(satirlar)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ek3", required=True, help="HUKDOK_CEVAP_EKI_3_2026-09-12.xlsx yolu")
    parser.add_argument("--apply", action="store_true", help="yaz (varsayılan kuru koşu)")
    parser.add_argument("--kim", default=DEGISTIREN, help="tarihçe imzası")
    args = parser.parse_args(argv)
    from database import SessionLocal
    from logging_setup import configure_logging    # log sözleşmesi: yapılandırma tek yerde
    configure_logging()
    sonuc = kos(SessionLocal, ek3=Path(args.ek3), apply=args.apply, kim=args.kim)
    print(ozet_metni(sonuc, apply=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
