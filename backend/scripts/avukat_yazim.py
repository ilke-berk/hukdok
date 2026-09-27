#!/usr/bin/env python3
"""Avukat adlarının yazım birliği + kart–avukat bağı (kullanıcı kararı 27.09.2026).

**Ölçüm (27.09, lokal = prod kopyası):** `lawyers` listesi BÜYÜK HARF ve çoğu aksansız
("TUGCE UNGOR"), kartlar teslimden gelen yazımı taşıyor ("Tuğçe Üngör Yanık"); aynı kişinin
2-3 yazımı yan yana (ör. "TUGCE UNGOR" 79 kart, "Av. Tuğçe Ungor Yanık" 1). Teslim paketi
avukatı yalnız AD olarak getirir (kimlik/kod yok, `SOZLESME.md` "Sorumlu Avukatlar"); aktarım
`case_lawyers.lawyer_id`'yi yalnız `upper(lawyers.name) == tr_upper(ad)` tutarsa bağlar →
listenin aksansız yazımı yüzünden ~15 bin satır bağsız. Dava listesi filtresi (toleranslı
eşleme) bundan ETKİLENMEZ (ölçüldü: 7 avukatta kaçan kart 0) — bu iş yazım + bağdır.

Kararlar (kullanıcı, 27.09):
* Listedeki 7 avukat NORMAL yazıma geçer ("Tuğçe Ungör Yanık" — "Ungör", Ü DEĞİL: kullanıcı
  düzeltmesi 27.09; kartlardaki "Üngör" yazımı da buna iner); `code` değişmez.
* Selda Şener, Reyhan Duygun, Asu Barış Karamık = DIŞ AVUKAT → listeye eklenir.
* Murat Arslan, Çiğdem Tel, Nurten Meral = idari personel (ofis) → listeye EKLENMEZ, kart
  satırları KALIR (paketteki 12 kişilik 1.031 föy listesinden geliyor); yalnız yazım düzelir.

Adımlar (tek transaction):
  1. `lawyers.name` yeniden adlandırma (eşleme: katlanmış ad anahtarı; beklenen eski ad yoksa ATLANDI).
  2. Yeni dış avukatlar (anahtarı listede varsa ATLANDI).
  3. Kart yazımı: `cases.responsible_lawyer_name` / `uyap_lawyer_name` (tarihçeli) ve
     `case_lawyers.name` (tarihçe alanı "avukat"); yalnız anahtarı tabloda olan adlar.
     "A;B" birleşik değerde her parça ayrı düzelir, `;` yapısı ve sıra korunur (kart kutusunu
     tek ada indirmek kullanıcı kararıdır). Silinmiş kartlar kapsam dışı.
     Yeniden adlandırma sonrası aynı kartta aynı adlı ikinci `case_lawyers` satırı birleşir
     (bağlı olan / küçük id kalır).
  4. Duruşma: `hearing_dates.lawyer_name` (aktif kart; tarihçe kartta `durusma_avukati`).
  5. Müvekkil: `clients.vekil_avukatlar` parçaları (listedeki/idari kişiler; diğer vekiller aynen).
  6. Bağ: `case_lawyers.lawyer_id` boş ve adı listedeki bir avukatla aynı → bağlanır.
  BEKÇİ: koşu sonunda "bilinen kişinin farklı yazımı" beş alanda sayılır — hepsi 0 olmalı.
  Kalıcı koruma (aynı gün): yeni kayıt yolları `lawyer_resolver.kanonik_avukat_metni`'nden geçer,
  kullanıcı uçları listede olmayan YENİ adı 422 ile reddeder, liste aynı kişiyi ikinci kez almaz.

Tarihçe `changed_by=--kim`, `source="avukat_yazim"`. Not: kesim-sonrası kullanıcı koruması
(`hukdok_aktarim.kesim_sonrasi_kullanici_kaydi`) bu kaynağı kullanıcı imzası sayar — yalnız
kesim tarihi BU koşudan önceki paketleri etkiler; aynı kişinin başka yazımı zaten eşlenir.
Koşu sonrası çalışan backend'in avukat önbelleği için `docker compose restart backend`.

    docker compose exec -T backend python scripts/avukat_yazim.py                 # kuru koşu
    docker compose exec -T backend python scripts/avukat_yazim.py --apply --kim ilke
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import unicodedata
from typing import Dict, Optional, Sequence, Tuple

from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from scripts.ekip_cevabi_1209 import Sonuc

logger = logging.getLogger("AvukatYazim")
SOURCE = "avukat_yazim"

#: (listedeki eski ad, yeni ad) — eşleşme `anahtar(eski)` ile; `code` değişmez.
#: 27.09 kullanıcı onayı: listenin TAMAMI normal yazım. Türkçe karaktersiz girilmiş adlar
#: (Karagül, Postalcıoğlu, Ertürk, Saygıner, Dilek Yıldırım, Başyurt, Fevzi, Kerim, Keziban,
#: Sakın, Oğuz … Çağlar, Özlem Deniz Türel, Hüseyin) kullanıcıya tek tek onaylatıldı.
#: "DUGCEM AYDIYE BALIKCI" BİLEREK YOK — doğru yazımı kullanıcı teyit edecek.
LISTE_YENIDEN_ADLANDIR: Tuple[Tuple[str, str], ...] = (
    ("TUGCE UNGOR", "Tuğçe Ungör Yanık"),
    ("BERNA BURCU BASYURT", "Berna Burcu Başyurt"),
    ("SERAP TURGAL", "Serap Turgal"),
    ("RANA BETUL GUMUS", "Rana Betül Gümüş"),
    ("BARIS YUCEL", "Barış Yücel"),
    ("AYSE GUL HANYALOGLU", "Ayşe Gül Hanyaloğlu"),
    ("AYSE ACAR YUCEL", "Ayşe Acar Yücel"),
    ("ABDULLAH BİRKAN ÖLMEZ", "Abdullah Birkan Ölmez"),
    ("AHMET ALPEREN KARAGUL", "Ahmet Alperen Karagül"),
    ("ASENA YILMAZ", "Asena Yılmaz"),
    ("AYSEL DİDEM KIVANÇ", "Aysel Didem Kıvanç"),
    ("AYSENUR POSTALCIOGLU", "Ayşenur Postalcıoğlu"),
    ("AYŞE AYAN", "Ayşe Ayan"),
    ("AYŞE NUR BAKİ", "Ayşe Nur Baki"),
    ("BATUHAN ŞAHİN", "Batuhan Şahin"),
    ("BURAK KAAN KOÇAK", "Burak Kaan Koçak"),
    ("BURCU ERTURK", "Burcu Ertürk"),
    ("BURCU SAYGINER SOYLU", "Burcu Saygıner Soylu"),
    ("BUSENUR TİRYAKİ", "Busenur Tiryaki"),
    ("BÜŞRA ATA", "Büşra Ata"),
    ("BÜŞRA KÜLLÜ", "Büşra Küllü"),
    ("CANAN FINDIK", "Canan Fındık"),
    ("CAVİDE IŞIL BOZDAĞ", "Cavide Işıl Bozdağ"),
    ("CEREN ÇAKIR ÇELİK", "Ceren Çakır Çelik"),
    ("ÇAĞRI ÜNAL", "Çağrı Ünal"),
    ("DILEK YILDIRIM", "Dilek Yıldırım"),
    ("EBRU ÇELİKKALELİ", "Ebru Çelikkaleli"),
    ("EGE CANSU BASYURT", "Ege Cansu Başyurt"),
    ("ELMAS SÜLEV", "Elmas Sülev"),
    ("EMİNE GÜZEL", "Emine Güzel"),
    ("EMİNE KESGİN", "Emine Kesgin"),
    ("EMRE ARSLAN", "Emre Arslan"),
    ("ENES KAYA", "Enes Kaya"),
    ("ERSİN KAZANCIGİL", "Ersin Kazancıgil"),
    ("FERHAT KÜÇÜK", "Ferhat Küçük"),
    ("FEVZI RANDA", "Fevzi Randa"),
    ("FEVZİ HERDEM", "Fevzi Herdem"),
    ("HANİFE GAMZE BİRGEÇ", "Hanife Gamze Birgeç"),
    ("HASAN KOÇAK", "Hasan Koçak"),
    ("İBRAHİM BAHADIR DOĞRU", "İbrahim Bahadır Doğru"),
    ("İLKEM ÖYKÜ KARADUT", "İlkem Öykü Karadut"),
    ("JİYAN ÖZKAPLAN", "Jiyan Özkaplan"),
    ("KERIM UYSAL", "Kerim Uysal"),
    ("KEZIBAN DOĞAN", "Keziban Doğan"),
    ("MEHTAP SAKIN", "Mehtap Sakın"),
    ("MELDA KÖYMEN", "Melda Köymen"),
    ("MENEKŞE KAÇAR", "Menekşe Kaçar"),
    ("MERVE NUR YILMAZ", "Merve Nur Yılmaz"),
    ("METEHAN TEMİZ", "Metehan Temiz"),
    ("MUHAMMED BULUTGÖÇER", "Muhammed Bulutgöçer"),
    ("MUHAMMED BURAK HAYRAN", "Muhammed Burak Hayran"),
    ("MUHAMMET BATUHAN YILMAZ", "Muhammet Batuhan Yılmaz"),
    ("MUHAMMET KAÇAR", "Muhammet Kaçar"),
    ("MUSTAFA ERKAL", "Mustafa Erkal"),
    ("NURSEDA SEZGİN", "Nurseda Sezgin"),
    ("OGUZ ALPEREN CAGLAR", "Oğuz Alperen Çağlar"),
    ("OĞUZHAN ERGÜL", "Oğuzhan Ergül"),
    ("OZLEM DENIZ TUREL", "Özlem Deniz Türel"),
    ("ÖMER BURUKAN", "Ömer Burukan"),
    ("ÖMER SELÇUK", "Ömer Selçuk"),
    ("ÖZDE SEYMEN SUNAR", "Özde Seymen Sunar"),
    ("RABİA DURGUT", "Rabia Durgut"),
    ("RAFET YAVAŞ", "Rafet Yavaş"),
    ("RIZA ALBAY", "Rıza Albay"),
    ("SACİDE ÖZATLI KÖPRÜLÜ", "Sacide Özatlı Köprülü"),
    ("SALİHA DİLER", "Saliha Diler"),
    ("SELMAN AYGÜN", "Selman Aygün"),
    ("SEZGİN KARMA", "Sezgin Karma"),
    ("TAHA HUSEYIN SOYLU", "Taha Hüseyin Soylu"),
    ("TAHİR KÜRŞAT ARPACIOĞLU", "Tahir Kürşat Arpacıoğlu"),
    ("UĞURAY SARIOĞLU", "Uğuray Sarıoğlu"),
    ("YAĞMUR GÜÇLÜ", "Yağmur Güçlü"),
    ("YUNUS EMRE BULUTGÖÇER", "Yunus Emre Bulutgöçer"),
    ("ZAFER KURTER", "Zafer Kurter"),
    ("ZEYNEP AYAN", "Zeynep Ayan"),
)

#: (ad, kod) — görev DIŞ AVUKAT.
YENI_DIS_AVUKATLAR: Tuple[Tuple[str, str], ...] = (
    ("Selda Şener", "SELDASEN"),
    ("Reyhan Duygun", "REYHANDU"),
    ("Asu Barış Karamık", "ASUBARIS"),
)

#: İdari personel — listeye girmez, kartta yalnız yazımı düzelir.
IDARI_PERSONEL: Tuple[str, ...] = ("Murat Arslan", "Çiğdem Tel", "Nurten Meral")

#: Aynı kişinin kısa/eski ad anahtarı → doğru yazım (soyadı eksik liste kaydı).
EK_ANAHTARLAR: Dict[str, str] = {"TUGCE UNGOR": "Tuğçe Ungör Yanık"}

_TR = str.maketrans("çğıöşüÇĞİÖŞÜâîûÂÎÛ", "cgiosuCGIOSUaiuAIU")

ADIM_ADLARI = {
    "liste": "1. Liste yazımı",
    "ekle": "2. Yeni dış avukat",
    "kart": "3. Kart yazımı",
    "durusma": "4. Duruşma avukatı",
    "vekil": "5. Müvekkil vekil listesi",
    "bag": "6. Kart–avukat bağı",
}


def anahtar(ad: Optional[str]) -> str:
    """Katlanmış ad anahtarı: Türkçe harf → ASCII, BÜYÜK, "Av."/"Avukat" öneki ve noktalama atılır."""
    s = unicodedata.normalize("NFKD", (ad or "").translate(_TR))
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    s = re.sub(r"^\s*(AV\.?|AVUKAT)\s+", "", s)
    s = re.sub(r"[^A-Z ]", " ", s)
    return " ".join(s.split())


def dogru_yazim_haritasi(db=None) -> Dict[str, str]:
    """{anahtar: doğru yazım}. Taban: listedeki (düzeltme SONRASI) adlar — tabloda olmayan liste
    kaydı da kendi yazımına iner; üstüne tablo, yeni dış avukatlar, idari personel, ek anahtarlar."""
    harita: Dict[str, str] = {}
    if db is not None:
        for av in db.query(models.Lawyer).all():
            if av.name and av.name.strip():
                harita.setdefault(anahtar(av.name), av.name)
    harita.update({anahtar(yeni): yeni for _, yeni in LISTE_YENIDEN_ADLANDIR})
    harita.update({anahtar(ad): ad for ad, _ in YENI_DIS_AVUKATLAR})
    harita.update({anahtar(ad): ad for ad in IDARI_PERSONEL})
    harita.update(EK_ANAHTARLAR)
    return harita


def _tarihce(db, case_id: int, alan: str, eski, yeni, kim: str) -> None:
    db.add(models.CaseHistory(
        case_id=case_id, field_name=alan, old_value=eski, new_value=yeni,
        changed_by=kim, source=SOURCE,
    ))


def listeyi_duzelt(db, *, sonuc: Sonuc) -> None:
    avukatlar = db.query(models.Lawyer).all()
    for eski_ad, yeni in LISTE_YENIDEN_ADLANDIR:
        eski_anahtar = anahtar(eski_ad)
        hedef = f"liste {yeni!r}"
        if any(av.name == yeni for av in avukatlar):
            sonuc.ekle("liste", hedef, "ATLANDI", "zaten düzeltilmiş")
            continue
        adaylar = [av for av in avukatlar if anahtar(av.name) in (eski_anahtar, anahtar(yeni))]
        if not adaylar:
            sonuc.ekle("liste", hedef, "ATLANDI", "bu ortamın listesinde yok")
            continue
        if len(adaylar) > 1:
            sonuc.ekle("liste", hedef, "RET", f"{len(adaylar)} aday satır — elle bakılmalı")
            continue
        eski = adaylar[0].name
        adaylar[0].name = yeni
        sonuc.ekle("liste", hedef, "YAPILDI", f"{eski!r} → {yeni!r} (kod {adaylar[0].code})")
    db.flush()


def dis_avukatlari_ekle(db, *, sonuc: Sonuc) -> None:
    avukatlar = db.query(models.Lawyer).all()
    mevcut_anahtarlar = {anahtar(av.name) for av in avukatlar}
    mevcut_kodlar = {av.code for av in avukatlar}
    sira = max((av.sequence or 0 for av in avukatlar), default=0)
    for ad, kod in YENI_DIS_AVUKATLAR:
        hedef = f"liste {ad!r}"
        if anahtar(ad) in mevcut_anahtarlar:
            sonuc.ekle("ekle", hedef, "ATLANDI", "listede zaten var")
            continue
        if kod in mevcut_kodlar:
            sonuc.ekle("ekle", hedef, "RET", f"kod {kod} başka avukatta — elle bakılmalı")
            continue
        sira += 1
        db.add(models.Lawyer(code=kod, name=ad, gorev="DIŞ AVUKAT", active=True, sequence=sira))
        mevcut_anahtarlar.add(anahtar(ad))
        mevcut_kodlar.add(kod)
        sonuc.ekle("ekle", hedef, "YAPILDI", f"kod {kod} · DIŞ AVUKAT")
    db.flush()


def kartlari_duzelt(db, harita: Dict[str, str], *, kim: str, sonuc: Sonuc) -> Dict[str, int]:
    """Kart yazımını tek biçime indirir; {'birlesik_duzelen': n, 'birlesen_satir': n} döner."""
    sayac = {"birlesik_duzelen": 0, "birlesen_satir": 0}
    aktif = db.query(models.Case).filter(models.Case.deleted_at.is_(None))
    for alan in ("responsible_lawyer_name", "uyap_lawyer_name"):
        kolon = getattr(models.Case, alan)
        degisen: Dict[Tuple[str, str], int] = {}
        for kart in aktif.filter(kolon.isnot(None), kolon != ""):
            deger = getattr(kart, alan)
            if ";" in deger:
                # "A;B": her parça ayrı düzelir, yapı ve sıra korunur.
                parcalar = [p.strip() for p in deger.split(";")]
                yeni = ";".join(harita.get(anahtar(p), p) for p in parcalar)
                if yeni != deger:
                    sayac["birlesik_duzelen"] += 1
            else:
                yeni = harita.get(anahtar(deger))
            if yeni is None or yeni == deger:
                continue
            setattr(kart, alan, yeni)
            _tarihce(db, kart.id, alan, deger, yeni, kim)
            degisen[(deger, yeni)] = degisen.get((deger, yeni), 0) + 1
        for (eski, yeni), n in sorted(degisen.items()):
            sonuc.ekle("kart", f"{alan}", "YAPILDI", f"{eski!r} → {yeni!r}: {n} kart")

    satirlar = (db.query(models.CaseLawyer)
                .join(models.Case, models.Case.id == models.CaseLawyer.case_id)
                .filter(models.Case.deleted_at.is_(None))
                .order_by(models.CaseLawyer.case_id, models.CaseLawyer.id).all())
    degisen = {}
    kart_adlari: Dict[Tuple[int, str], models.CaseLawyer] = {}
    for satir in satirlar:
        yeni = harita.get(anahtar(satir.name))
        if yeni is not None and yeni != satir.name:
            _tarihce(db, satir.case_id, "avukat", satir.name, yeni, kim)
            degisen[(satir.name, yeni)] = degisen.get((satir.name, yeni), 0) + 1
            satir.name = yeni
        anahtar_ = (satir.case_id, satir.name)
        onceki = kart_adlari.get(anahtar_)
        if onceki is None:
            kart_adlari[anahtar_] = satir
            continue
        # Aynı kartta aynı adlı ikinci satır: bağlı olan (yoksa küçük id) kalır.
        kalan, giden = (onceki, satir) if (onceki.lawyer_id or not satir.lawyer_id) else (satir, onceki)
        kart_adlari[anahtar_] = kalan
        db.delete(giden)
        sayac["birlesen_satir"] += 1
    for (eski, yeni), n in sorted(degisen.items()):
        sonuc.ekle("kart", "case_lawyers.name", "YAPILDI", f"{eski!r} → {yeni!r}: {n} satır")
    if sayac["birlesen_satir"]:
        sonuc.ekle("kart", "case_lawyers", "YAPILDI",
                   f"aynı kartta aynı adlı {sayac['birlesen_satir']} satır birleşti")
    db.flush()
    return sayac


def _parca_parca(deger: str, harita: Dict[str, str]) -> str:
    """"A;B" değerini parça parça doğru yazıma indirir; aynı kişi iki kez yazılmışsa bir kez kalır."""
    parcalar, gorulen = [], set()
    for parca in deger.split(";"):
        temiz = " ".join(parca.split())
        if not temiz:
            continue
        ad = harita.get(anahtar(temiz), temiz)
        if anahtar(ad) in gorulen:
            continue
        gorulen.add(anahtar(ad))
        parcalar.append(ad)
    return ";".join(parcalar)


def durusmalari_duzelt(db, harita: Dict[str, str], *, kim: str, sonuc: Sonuc) -> None:
    """`hearing_dates.lawyer_name` (aktif kartların duruşmaları) — tarihçe kartın kaydına
    `durusma_avukati` alanıyla düşer (duruşmanın kendi tarihçe tablosu yok)."""
    satirlar = (db.query(models.HearingDate)
                .join(models.Case, models.Case.id == models.HearingDate.case_id)
                .filter(models.Case.deleted_at.is_(None),
                        models.HearingDate.lawyer_name.isnot(None), models.HearingDate.lawyer_name != ""))
    degisen: Dict[Tuple[str, str], int] = {}
    for h in satirlar:
        yeni = _parca_parca(h.lawyer_name, harita)
        if yeni == h.lawyer_name:
            continue
        _tarihce(db, h.case_id, "durusma_avukati", f"{h.hearing_date} {h.lawyer_name}", f"{h.hearing_date} {yeni}", kim)
        degisen[(h.lawyer_name, yeni)] = degisen.get((h.lawyer_name, yeni), 0) + 1
        h.lawyer_name = yeni
    for (eski, yeni), n in sorted(degisen.items()):
        sonuc.ekle("durusma", "hearing_dates.lawyer_name", "YAPILDI", f"{eski!r} → {yeni!r}: {n} duruşma")
    db.flush()


def vekilleri_duzelt(db, harita: Dict[str, str], *, sonuc: Sonuc) -> None:
    """`clients.vekil_avukatlar` ("AD;AD"): listedeki/idari kişiler doğru yazıma iner, vekaletnamedeki
    diğer avukatlar olduğu gibi (yalnız boşluk sadeleşir) kalır. Müvekkil tarihçe tablosu yok →
    değişiklik yalnız bu raporda (koşu öncesi yedek şart)."""
    degisen_kayit, parca_sayim = 0, {}
    for mv in db.query(models.Client).filter(models.Client.deleted_at.is_(None),
                                             models.Client.vekil_avukatlar.isnot(None),
                                             models.Client.vekil_avukatlar != ""):
        yeni = _parca_parca(mv.vekil_avukatlar, harita)
        if yeni == mv.vekil_avukatlar:
            continue
        for parca in mv.vekil_avukatlar.split(";"):
            temiz = " ".join(parca.split())
            dogru = harita.get(anahtar(temiz))
            if dogru and dogru != temiz:
                parca_sayim[(temiz, dogru)] = parca_sayim.get((temiz, dogru), 0) + 1
        mv.vekil_avukatlar = yeni
        degisen_kayit += 1
    for (eski, yeni), n in sorted(parca_sayim.items()):
        sonuc.ekle("vekil", "clients.vekil_avukatlar", "YAPILDI", f"{eski!r} → {yeni!r}: {n} müvekkil")
    if degisen_kayit:
        sonuc.ekle("vekil", "clients.vekil_avukatlar", "YAPILDI", f"toplam {degisen_kayit} müvekkil kaydı güncellendi")
    db.flush()


def farkli_yazim(db, harita: Dict[str, str]) -> Dict[str, int]:
    """BEKÇİ ölçümü: bilinen bir kişinin doğru yazımından FARKLI yazıldığı parça sayısı (alan başına).
    Koşu sonrası hepsi 0 olmalı; yeni kayıt yolları `lawyer_resolver.kanonik_avukat_metni`'nden geçer."""
    def say(degerler) -> int:
        n = 0
        for deger in degerler:
            for parca in (deger or "").split(";"):
                temiz = " ".join(parca.split())
                dogru = harita.get(anahtar(temiz)) if temiz else None
                if dogru and dogru != temiz:
                    n += 1
        return n

    aktif = db.query(models.Case).filter(models.Case.deleted_at.is_(None))
    return {
        "responsible_lawyer_name": say(c.responsible_lawyer_name for c in aktif),
        "uyap_lawyer_name": say(c.uyap_lawyer_name for c in aktif),
        "case_lawyers": say(r.name for r in db.query(models.CaseLawyer)
                            .join(models.Case, models.Case.id == models.CaseLawyer.case_id)
                            .filter(models.Case.deleted_at.is_(None))),
        "hearing_dates": say(h.lawyer_name for h in db.query(models.HearingDate)
                             .join(models.Case, models.Case.id == models.HearingDate.case_id)
                             .filter(models.Case.deleted_at.is_(None))),
        "vekil_avukatlar": say(m.vekil_avukatlar for m in db.query(models.Client)
                               .filter(models.Client.deleted_at.is_(None))),
    }


def baglari_kur(db, *, sonuc: Sonuc) -> None:
    ad_id = {av.name: av.id for av in db.query(models.Lawyer).all()}
    sayim: Dict[str, int] = {}
    for satir in db.query(models.CaseLawyer).filter(models.CaseLawyer.lawyer_id.is_(None)):
        lawyer_id = ad_id.get(satir.name)
        if lawyer_id is None:
            continue
        satir.lawyer_id = lawyer_id
        sayim[satir.name] = sayim.get(satir.name, 0) + 1
    for ad, n in sorted(sayim.items()):
        sonuc.ekle("bag", ad, "YAPILDI", f"{n} satır bağlandı")
    db.flush()


def bagsiz_kalan(db) -> Dict[str, int]:
    """Bağsız kalan `case_lawyers` adları ve satır sayıları (bilgi)."""
    satirlar = (db.query(models.CaseLawyer.name, func.count(models.CaseLawyer.id))
                .filter(models.CaseLawyer.lawyer_id.is_(None))
                .group_by(models.CaseLawyer.name).all())
    return {ad: int(n) for ad, n in satirlar}


def kos(session_factory, *, apply: bool = False, kim: str = SOURCE):
    sonuc = Sonuc()
    db = session_factory()
    try:
        listeyi_duzelt(db, sonuc=sonuc)
        dis_avukatlari_ekle(db, sonuc=sonuc)
        harita = dogru_yazim_haritasi(db)
        sayac = kartlari_duzelt(db, harita, kim=kim, sonuc=sonuc)
        durusmalari_duzelt(db, harita, kim=kim, sonuc=sonuc)
        vekilleri_duzelt(db, harita, sonuc=sonuc)
        baglari_kur(db, sonuc=sonuc)
        kalan = bagsiz_kalan(db)
        sayac["farkli_yazim"] = farkli_yazim(db, harita)
        if apply:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return sonuc, sayac, kalan


def ozet_metni(sonuc: Sonuc, sayac: Dict[str, int], kalan: Dict[str, int], *, apply: bool) -> str:
    satirlar = ["=" * 78, f"Avukat yazım birliği — {'UYGULANDI' if apply else 'KURU KOŞU'}", "=" * 78]
    for adim, ad in ADIM_ADLARI.items():
        y, a, r = (sonuc.sayim(adim, s) for s in ("YAPILDI", "ATLANDI", "RET"))
        satirlar.append(f"  {ad:24} {y:4} yapıldı · {a:4} atlandı · {r:3} ret")
    satirlar.append("  " + "-" * 74)
    satirlar.extend(f"  {k.sonuc:7} [{k.adim}] {k.hedef}: {k.aciklama}" for k in sonuc.kalemler)
    satirlar.append("  " + "-" * 74)
    satirlar.append(f"  'A;B' birleşik değerde parça düzelen kart alanı: {sayac['birlesik_duzelen']}")
    satirlar.append("  BEKÇİ — bilinen kişinin farklı yazımı (koşu sonrası, hepsi 0 olmalı): "
                    + " · ".join(f"{k} {v}" for k, v in sayac["farkli_yazim"].items()))
    satirlar.append("  Bağsız kalan case_lawyers adları (sonrası):")
    satirlar.extend(f"    {n:6}  {ad}" for ad, n in sorted(kalan.items(), key=lambda x: -x[1]))
    satirlar.append("=" * 78)
    return "\n".join(satirlar)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Avukat adlarının yazım birliği + kart–avukat bağı")
    ayristirici.add_argument("--apply", action="store_true", help="yazar (yoksa kuru koşu)")
    ayristirici.add_argument("--kim", default=SOURCE, help="tarihçe imzası (changed_by)")
    args = ayristirici.parse_args(argv)

    from database import SessionLocal
    from logging_setup import configure_logging
    configure_logging()

    sonuc, sayac, kalan = kos(SessionLocal, apply=args.apply, kim=args.kim)
    print(ozet_metni(sonuc, sayac, kalan, apply=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
