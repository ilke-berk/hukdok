"""G150 — Aşama katmanı kuralı (plan 08.09 §1.2 A1 + A2, kullanıcı kararı 06.09 §0).

Eski kural "dolu aşamaya dokunulmaz"dı: o aşamada bir satır varsa paket hiçbir
düzeltmeyi yazmıyordu (18.08'in 4.971 satırı 04.09 paketini engelledi, 12 bayat)
ve `_asama_imzasi` boş hücreyi imzaya katıyordu (302 grup yalnız boşluk
yüzünden "çelişki" sayıldı, aşama yazılmadı).

Yeni kural:
  (a) boş hücre uzlaşıya girmez; dolu değerler çelişmiyorsa birleşik satır;
  (b) paket kaynaklı satır yeni paketle YERİNDE güncellenir (tarihçeli);
  (c) BELGE/UYAP satır korunur ve satır raporuna düşer;
  (d) elle girilmiş satır da güncellenir;
  (e) aynı içerikle ikinci koşu 0;
  (f) çok tur: esas VE karar tarihi farklı, mevcut daha eski → `sira_no+1`;
  (g) gerçek çelişki (iki farklı dolu değer) hâlâ yazılmaz.

Fixture'lar G064'ten (pysqlite SAVEPOINT reçetesi tek kaynakta durmalı).
"""
import re
from datetime import date
from pathlib import Path

import pytest

import models
from managers import stage_decisions
from scripts.hukdok_aktarim import CIKIS_TAMAM, aktarimi_kos

# Aktarım koşusunun fixture'ları TEK KAYNAKTAN; ruff fixture parametresini
# yeniden tanımlama sanar (F811), kullanım yerinde susturulur.
from tests.test_g064_aktarim_cekirdek import (  # noqa: F401
    _asama_paketi_yaz,
    _satir,
    db_env,
    uc_kart,
)


@pytest.fixture()
def zemin(uc_kart):  # noqa: F811
    """Üç kart + G060 kapalı havuzları (boş listede tarihçe yolu hiçbir değeri
    geçirmez)."""
    db = uc_kart()
    try:
        db.add(models.LocalDecision(code="RED-ESAS", name="Red/Esastan"))
        db.add(models.LocalDecision(code="KABUL", name="Kabul"))
        db.add(models.AppealDecision(code="KALDIRMA", name="Kaldırma"))
        db.add(models.AppealDecision(code="BASVURU-RET", name="Başvuru Ret"))
        db.commit()
    finally:
        db.close()
    return uc_kart


def _yerel(sistem_no, **alanlar):
    temel = {"SistemNo": sistem_no, "AsamaNo": 1, "Aşama": "Yerel",
             "Mahkeme": "İstanbul 8. Tüketici", "Esas No": "2020/143",
             "Karar Tarihi": "05.05.2021", "Karar Durumu": "Red/Esastan", "Güven": "KESİN"}
    temel.update(alanlar)
    return temel


def _satirlar(fabrika, klasor="D-1"):
    """Kartın aşama satırları: (stage, sira_no) → satır (oturum kapalı, alanlar yüklü)."""
    db = fabrika()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2=klasor).one()
        satirlar = stage_decisions.get_stage_decisions(db, kart.id)
        for s in satirlar:
            db.expunge(s)
        return {(s.stage, s.sira_no): s for s in satirlar}
    finally:
        db.close()


def _tarihce(fabrika, onek="case_stage_decisions"):
    db = fabrika()
    try:
        return [
            (h.field_name, h.old_value, h.new_value, h.source)
            for h in db.query(models.CaseHistory)
            .filter(models.CaseHistory.field_name.like(f"{onek}%"))
            .order_by(models.CaseHistory.id)
        ]
    finally:
        db.close()


def _kart(fabrika, klasor="D-1"):
    db = fabrika()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2=klasor).one()
        db.expunge(kart)
        return kart
    finally:
        db.close()


def _elle_satir(fabrika, *, stage="YEREL", damga="BELIRSIZ", source="takip-paneli", **alanlar):
    """Aktarım dışı yoldan yazılmış mevcut satır (elle / belgeli)."""
    db = fabrika()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        satir = stage_decisions.add_stage_decision(
            db, kart, stage=stage, dogrulama_durumu=damga, source=source, **alanlar)
        db.commit()
        return satir.id
    finally:
        db.close()


# ─── (a) boş hücre birleşimi ─────────────────────────────────────────────────

def test_a_kardes_foyde_bos_hucre_celiski_degil_birlesik_satir(zemin, tmp_path):
    """Kart 13210 deseni: H-1737 karar no 2021/856, H-1738 boş; tarih ve durum
    aynı → TEK satır, karar no dolu olandan. Eski kodda bu grup çelişkiydi."""
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx",
        [_satir("H-1737", "D-1"), _satir("H-1738", "D-1")],
        [_yerel("H-1737", **{"Karar No": "2021/856", "Tebliğ Tarihi": "01.06.2021"}),
         _yerel("H-1738", **{"Karar No": None, "Mahkeme": None})],
    )

    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM
    assert sonuc.asama_eklenen == 1
    assert [c for c in sonuc.celiskiler if c.alan.startswith("asama:")] == []
    satirlar = _satirlar(zemin)
    assert set(satirlar) == {("YEREL", 1)}
    satir = satirlar[("YEREL", 1)]
    assert satir.karar_no == "2021/856"
    assert satir.mahkeme == "İstanbul 8. Tüketici"          # boş kardeşten değil
    assert satir.karar_tarihi == date(2021, 5, 5)
    assert satir.karar_durumu == "Red/Esastan"
    assert satir.teblig_tarihi == date(2021, 6, 1)           # imza dışı alan: ilk dolu
    assert satir.dogrulama_durumu == "TURETILDI"             # ikisi de KESİN


def test_a_guven_zayif_damga_kazanir(zemin, tmp_path):
    """Kardeşlerden biri BELİRSİZ diyorsa birleşik satır BELİRSİZ (tahmin yasağı)."""
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1"), _satir("H-2", "D-1")],
        [_yerel("H-1", **{"Karar No": "2021/1"}),
         _yerel("H-2", **{"Karar No": None, "Güven": "BELİRSİZ"})],
    )
    aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert _satirlar(zemin)[("YEREL", 1)].dogrulama_durumu == "BELIRSIZ"


# ─── (g) gerçek çelişki ──────────────────────────────────────────────────────

def test_g_iki_farkli_dolu_deger_hala_celiski(zemin, tmp_path):
    """Boşluk toleransı gerçek çelişkiyi gizlemez: bir alan boş olsa bile başka
    alanda iki farklı dolu değer varsa aşama yazılmaz, rapora düşer."""
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1"), _satir("H-2", "D-1")],
        [_yerel("H-1", **{"Karar No": "2021/963", "Mahkeme": None}),
         _yerel("H-2", **{"Karar No": "2021/693"})],
    )

    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.asama_eklenen == 0 and _satirlar(zemin) == {}
    celiski = [c for c in sonuc.celiskiler if c.alan == "asama:YEREL"]
    assert len(celiski) == 1
    assert "H-1=2021/963" in celiski[0].degerler and "H-2=2021/693" in celiski[0].degerler


def test_g_farkli_tur_sayisi_celiski(zemin, tmp_path):
    """Föyler aynı aşamada farklı sayıda tur anlatıyorsa hizalanamaz → çelişki."""
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1"), _satir("H-2", "D-1")],
        [_yerel("H-1", **{"Karar No": "2021/1"}),
         _yerel("H-2", **{"Karar No": "2021/1"}),
         _yerel("H-2", AsamaNo=2, **{"Karar No": "2023/5", "Esas No": "2022/9",
                                     "Karar Tarihi": "01.02.2023"})],
    )
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert sonuc.asama_eklenen == 0
    assert [c.alan for c in sonuc.celiskiler] == ["asama:YEREL"]


# ─── (b) paket kaynaklı bayat satır güncellenir ──────────────────────────────

def test_b_paket_kaynakli_satir_yeni_paketle_guncellenir_tarihceli(zemin, tmp_path):
    """18.08 → 04.09 deseni: ilk paket 2021/856 yazdı, ekip düzeltti, ikinci
    paket 2021/865 getirdi → satır yerinde güncellenir, alan başına tarihçe
    eski/yeni + yeni paketin imzası, damga/imza tazelenir, fotoğraf eşitlenir."""
    eski = _asama_paketi_yaz(tmp_path / "p1.xlsx",
                             [_satir("H-1", "D-1")], [_yerel("H-1", **{"Karar No": "2021/856"})])
    ilk = aktarimi_kos(zemin, girdi=eski, rapor_dizini=tmp_path / "rapor",
                       source="HUKDOK_TESLIM_PAKETI_2026-08-18.xlsx")
    assert ilk.asama_eklenen == 1 and ilk.asama_guncellenen == 0
    assert _satirlar(zemin)[("YEREL", 1)].source == "HUKDOK_TESLIM_PAKETI_2026-08-18.xlsx"

    yeni = _asama_paketi_yaz(tmp_path / "p2.xlsx",
                             [_satir("H-1", "D-1")],
                             [_yerel("H-1", **{"Karar No": "2021/865", "Karar Durumu": "Kabul",
                                               "Güven": "BELİRSİZ"})])
    ikinci = aktarimi_kos(zemin, girdi=yeni, rapor_dizini=tmp_path / "rapor",
                          source="HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx")

    assert ikinci.cikis_kodu == CIKIS_TAMAM
    assert (ikinci.asama_eklenen, ikinci.asama_guncellenen, ikinci.asama_ikinci_tur,
            ikinci.asama_belgeli_korunan) == (0, 1, 0, 0)
    satirlar = _satirlar(zemin)
    assert set(satirlar) == {("YEREL", 1)}                    # satır İKİLENMEDİ
    satir = satirlar[("YEREL", 1)]
    assert satir.karar_no == "2021/865" and satir.karar_durumu == "Kabul"
    assert satir.esas_no == "2020/143"                        # değişmeyen alan durdu
    assert satir.dogrulama_durumu == "BELIRSIZ"               # damga tazelendi
    assert satir.source == "HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx"   # imza tazelendi
    tarihce = _tarihce(zemin)
    assert sorted(tarihce) == sorted([
        ("case_stage_decisions.YEREL.1.karar_no", "2021/856", "2021/865", satir.source),
        ("case_stage_decisions.YEREL.1.karar_durumu", "Red/Esastan", "Kabul", satir.source),
    ])
    kart = _kart(zemin)
    assert kart.karar_no == "2021/865" and kart.yerel_karar_durumu == "Kabul"   # fotoğraf


def test_b_bos_paket_alani_bizdeki_degeri_bosaltmaz(zemin, tmp_path):
    """Paket kaynaklı satırda bir alan yeni pakette BOŞ geliyorsa bu 'boşalt'
    demektir mi? Hayır — hücre boş = 'bu teslimde yok' (kart alanlarıyla aynı
    kural DEĞİL: aşama satırı bütün olarak paketin anlatımıdır, boş hücre de
    içeriğin parçasıdır ve yerinde güncelleme bunu yazar). Bu test kuralı
    KİLİTLER: karar no boş gelince satırın karar_no'su boşalır ve tarihçeye
    düşer — sessiz veri kaybı değil, izli değişiklik."""
    eski = _asama_paketi_yaz(tmp_path / "p1.xlsx", [_satir("H-1", "D-1")],
                             [_yerel("H-1", **{"Karar No": "2021/856"})])
    aktarimi_kos(zemin, girdi=eski, rapor_dizini=tmp_path / "rapor")
    yeni = _asama_paketi_yaz(tmp_path / "p2.xlsx", [_satir("H-1", "D-1")],
                             [_yerel("H-1", **{"Karar No": None})])
    sonuc = aktarimi_kos(zemin, girdi=yeni, rapor_dizini=tmp_path / "rapor")
    assert sonuc.asama_guncellenen == 1
    assert _satirlar(zemin)[("YEREL", 1)].karar_no is None
    assert [(t[0], t[1], t[2]) for t in _tarihce(zemin)] == [
        ("case_stage_decisions.YEREL.1.karar_no", "2021/856", None)]


# ─── (c) BELGE / UYAP satır korunur ──────────────────────────────────────────

@pytest.mark.parametrize("damga", ["BELGE", "UYAP"])
def test_c_belgeli_satir_korunur_ve_raporlanir(zemin, tmp_path, damga):
    """Künyede belgeye dayanan taraf kazanır: satır dokunulmaz, fark satır
    raporuna ATLANDI olarak düşer (koşu kırmızı olmaz), CSV'de görünür."""
    _elle_satir(zemin, damga=damga, mahkeme="İstanbul 8. Tüketici", esas_no="2020/143",
                karar_no="2021/856", karar_tarihi=date(2021, 5, 5), karar_durumu="Red/Esastan")
    paket = _asama_paketi_yaz(tmp_path / "teslim.xlsx", [_satir("H-1", "D-1")],
                              [_yerel("H-1", **{"Karar No": "2021/865", "Karar Durumu": "Kabul"})])

    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM
    assert (sonuc.asama_eklenen, sonuc.asama_guncellenen, sonuc.asama_belgeli_korunan) == (0, 0, 1)
    satirlar = _satirlar(zemin)
    assert set(satirlar) == {("YEREL", 1)}
    satir = satirlar[("YEREL", 1)]
    assert (satir.karar_no, satir.karar_durumu, satir.dogrulama_durumu, satir.source) == (
        "2021/856", "Red/Esastan", damga, "takip-paneli")
    assert _tarihce(zemin) == []                              # tarihçe de yok
    rapor = [r for r in sonuc.rapor_satirlari if "belgeli aşama satırı korundu" in r.sebep]
    assert len(rapor) == 1 and rapor[0].tur == "ATLANDI" and rapor[0].sistem_no == "H-1"
    assert f"YEREL #1, {damga}" in rapor[0].sebep
    assert "karar_no: 2021/856 → 2021/865" in rapor[0].sebep
    csv = [p for p in sonuc.raporlar if p.name.startswith("satir-raporu")]
    assert len(csv) == 1 and "belgeli aşama satırı korundu" in Path(csv[0]).read_text(encoding="utf-8-sig")
    assert _kart(zemin).karar_no == "2021/856"               # fotoğraf belgeli satırdan


def test_c_belgeli_satir_ayni_icerikle_sessiz(zemin, tmp_path):
    """Paket belgeli satırla aynı şeyi söylüyorsa çelişki yok — rapor da yok."""
    _elle_satir(zemin, damga="BELGE", mahkeme="İstanbul 8. Tüketici", esas_no="2020/143",
                karar_no="2021/856", karar_tarihi=date(2021, 5, 5), karar_durumu="Red/Esastan")
    paket = _asama_paketi_yaz(tmp_path / "teslim.xlsx", [_satir("H-1", "D-1")],
                              [_yerel("H-1", **{"Karar No": "2021/856"})])
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert sonuc.asama_belgeli_korunan == 0 and sonuc.rapor_satirlari == []


# ─── (d) elle satır güncellenir ──────────────────────────────────────────────

def test_d_elle_girilmis_satir_paketle_guncellenir(zemin, tmp_path):
    """Kullanıcı kararı 06.09: son paket elle düzeltmeden daha doğru sayılır —
    kaynağı paket olmayan BELIRSIZ/TURETILDI satır da güncellenir (tarihçeli)."""
    _elle_satir(zemin, damga="TURETILDI", source="takip-paneli",
                mahkeme="İstanbul 8. Tüketici", esas_no="2020/143", karar_no="2021/856",
                karar_tarihi=date(2021, 5, 5), karar_durumu="Red/Esastan")
    paket = _asama_paketi_yaz(tmp_path / "teslim.xlsx", [_satir("H-1", "D-1")],
                              [_yerel("H-1", **{"Karar No": "2021/865"})])

    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert (sonuc.asama_eklenen, sonuc.asama_guncellenen) == (0, 1)
    satir = _satirlar(zemin)[("YEREL", 1)]
    assert satir.karar_no == "2021/865" and satir.source != "takip-paneli"
    assert [(t[0], t[1], t[2]) for t in _tarihce(zemin)] == [
        ("case_stage_decisions.YEREL.1.karar_no", "2021/856", "2021/865")]


# ─── (e) ikinci koşu 0 ───────────────────────────────────────────────────────

def test_e_ayni_paketle_ikinci_kosu_sifir(zemin, tmp_path):
    """Güncelleme + çok tur + boşluk birleşimi bir arada; ikinci koşu hiçbir
    sayaç artırmaz, tarihçe büyümez, satır sayısı sabit."""
    _elle_satir(zemin, stage="ISTINAF", mahkeme="İSTANBUL BİM 7. HD", esas_no="2021/1479",
                karar_no="2022/100", karar_tarihi=date(2022, 3, 1), karar_durumu="Kaldırma")
    eski = _asama_paketi_yaz(tmp_path / "p1.xlsx", [_satir("H-1", "D-1")],
                             [_yerel("H-1", **{"Karar No": "2021/856"})])
    aktarimi_kos(zemin, girdi=eski, rapor_dizini=tmp_path / "rapor")
    paket = _asama_paketi_yaz(
        tmp_path / "p2.xlsx",
        [_satir("H-1", "D-1"), _satir("H-2", "D-1")],
        [_yerel("H-1", **{"Karar No": "2021/865"}),
         _yerel("H-2", **{"Karar No": None}),
         {"SistemNo": "H-1", "AsamaNo": 2, "Aşama": "İstinaf", "Mahkeme": "İSTANBUL BİM 7. HD",
          "Esas No": "2025/1812", "Karar No": "2025/50", "Karar Tarihi": "01.06.2025",
          "Karar Durumu": "Başvuru Ret", "Güven": "KESİN"}],
    )

    ilk = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert (ilk.asama_eklenen, ilk.asama_guncellenen, ilk.asama_ikinci_tur) == (0, 1, 1)
    tarihce_once = _tarihce(zemin, onek="")
    satirlar_once = {k: (s.karar_no, s.esas_no, s.source) for k, s in _satirlar(zemin).items()}
    assert set(satirlar_once) == {("YEREL", 1), ("ISTINAF", 1), ("ISTINAF", 2)}

    ikinci = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert (ikinci.asama_eklenen, ikinci.asama_guncellenen, ikinci.asama_ikinci_tur,
            ikinci.asama_belgeli_korunan) == (0, 0, 0, 0)
    assert ikinci.celiskiler == [] and ikinci.rapor_satirlari == []
    assert _tarihce(zemin, onek="") == tarihce_once
    assert {k: (s.karar_no, s.esas_no, s.source) for k, s in _satirlar(zemin).items()} == satirlar_once


# ─── (f) çok tur ─────────────────────────────────────────────────────────────

def test_f_cok_tur_ikinci_satir_ve_fotograf(zemin, tmp_path):
    """Kart 13261 deseni: BİM 7 2021/1479 (2022) mevcut, paket 2025/1812 (2025)
    getirdi — esas VE tarih farklı, mevcut daha eski → ikinci satır sira_no 2,
    mevcut korunur, fotoğraf en yüksek sira_no'dan."""
    _elle_satir(zemin, stage="ISTINAF", mahkeme="İSTANBUL BİM 7. HD", esas_no="2021/1479",
                karar_no="2022/100", karar_tarihi=date(2022, 3, 1), karar_durumu="Kaldırma",
                source="HUKDOK_TESLIM_tam_teslim.xlsx")
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx", [_satir("H-1", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "İstinaf", "Mahkeme": "İSTANBUL BİM 7. HD",
          "Esas No": "2025/1812", "Karar No": "2025/50", "Karar Tarihi": "01.06.2025",
          "Karar Durumu": "Başvuru Ret", "Güven": "KESİN"}],
    )

    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert (sonuc.asama_eklenen, sonuc.asama_guncellenen, sonuc.asama_ikinci_tur) == (0, 0, 1)
    satirlar = _satirlar(zemin)
    assert set(satirlar) == {("ISTINAF", 1), ("ISTINAF", 2)}
    assert satirlar[("ISTINAF", 1)].esas_no == "2021/1479"    # korundu
    assert satirlar[("ISTINAF", 1)].karar_no == "2022/100"
    assert satirlar[("ISTINAF", 2)].esas_no == "2025/1812"
    assert satirlar[("ISTINAF", 2)].karar_durumu == "Başvuru Ret"
    assert _tarihce(zemin) == []                              # güncelleme değil, ekleme
    kart = _kart(zemin)
    assert (kart.istinaf_esas_no, kart.istinaf_karar_no) == ("2025/1812", "2025/50")

    ikinci = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert (ikinci.asama_eklenen, ikinci.asama_ikinci_tur, ikinci.asama_guncellenen) == (0, 0, 0)
    assert set(_satirlar(zemin)) == {("ISTINAF", 1), ("ISTINAF", 2)}


def test_f_yalniz_esas_farkliysa_duzeltmedir(zemin, tmp_path):
    """Çok tur kuralı DAR: yalnız esas no değişmişse (tarih aynı) bu bir
    düzeltmedir — yerinde güncellenir, ikinci satır açılmaz."""
    _elle_satir(zemin, stage="ISTINAF", mahkeme="İSTANBUL BİM 7. HD", esas_no="2021/1479",
                karar_no="2022/100", karar_tarihi=date(2022, 3, 1), karar_durumu="Kaldırma")
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx", [_satir("H-1", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "İstinaf", "Mahkeme": "İSTANBUL BİM 7. HD",
          "Esas No": "2021/1497", "Karar No": "2022/100", "Karar Tarihi": "01.03.2022",
          "Karar Durumu": "Kaldırma", "Güven": "KESİN"}],
    )
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert (sonuc.asama_guncellenen, sonuc.asama_ikinci_tur) == (1, 0)
    assert set(_satirlar(zemin)) == {("ISTINAF", 1)}
    assert _satirlar(zemin)[("ISTINAF", 1)].esas_no == "2021/1497"


# ─── Yönetici (tek yazma yolu) ───────────────────────────────────────────────

def test_update_belgeli_satiri_reddeder_ve_dokunmaz(zemin):
    db = zemin()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        satir = stage_decisions.add_stage_decision(
            db, kart, stage="YEREL", karar_no="2021/1", dogrulama_durumu="UYAP")
        with pytest.raises(stage_decisions.ProtectedStageDecisionError):
            stage_decisions.update_stage_decision(db, kart, satir, karar_no="2021/2")
        assert satir.karar_no == "2021/1"
    finally:
        db.close()


def test_update_ayni_icerik_hicbir_seye_dokunmaz(zemin):
    """İçerik aynıyken damga/imza da tazelenmez — 'değişiklik' sayılmaz."""
    db = zemin()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        satir = stage_decisions.add_stage_decision(
            db, kart, stage="YEREL", karar_no=" 2021/1 ", karar_durumu="Kabul",
            dogrulama_durumu="TURETILDI", source="HUKDOK_TESLIM_a.xlsx")
        fark = stage_decisions.update_stage_decision(
            db, kart, satir, karar_no="2021/1", karar_durumu="Kabul",
            dogrulama_durumu="BELIRSIZ", source="HUKDOK_TESLIM_b.xlsx")
        assert fark == {}
        assert (satir.dogrulama_durumu, satir.source) == ("TURETILDI", "HUKDOK_TESLIM_a.xlsx")
    finally:
        db.close()


def test_update_farki_doner_damga_ve_fotografi_tazeler(zemin):
    db = zemin()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        satir = stage_decisions.add_stage_decision(
            db, kart, stage="YEREL", karar_no="2021/1", karar_durumu="Kabul",
            dogrulama_durumu="TURETILDI", source="HUKDOK_TESLIM_a.xlsx")
        fark = stage_decisions.update_stage_decision(
            db, kart, satir, karar_no="2021/2", karar_durumu="Red/Esastan",
            karar_tarihi=date(2021, 5, 5), dogrulama_durumu="BELIRSIZ", source="HUKDOK_TESLIM_b.xlsx")
        assert fark == {
            "karar_no": ("2021/1", "2021/2"),
            "karar_durumu": ("Kabul", "Red/Esastan"),
            "karar_tarihi": (None, date(2021, 5, 5)),
        }
        assert (satir.dogrulama_durumu, satir.source) == ("BELIRSIZ", "HUKDOK_TESLIM_b.xlsx")
        assert (kart.karar_no, kart.yerel_karar_durumu, kart.karar_tarihi) == (
            "2021/2", "Red/Esastan", date(2021, 5, 5))
        with pytest.raises(stage_decisions.InvalidDecisionStatusError):
            stage_decisions.update_stage_decision(db, kart, satir, karar_durumu="Uydurma")
    finally:
        db.close()


def test_update_baska_davanin_satirini_reddeder(zemin):
    db = zemin()
    try:
        kartlar = {c.klasor_no_2: c for c in db.query(models.Case).all()}
        satir = stage_decisions.add_stage_decision(db, kartlar["D-1"], stage="YEREL", karar_no="2021/1")
        with pytest.raises(ValueError):
            stage_decisions.update_stage_decision(db, kartlar["D-2"], satir, karar_no="2021/2")
    finally:
        db.close()


def test_silme_yolu_eklenmedi():
    """Kabul kriteri: `CaseStageDecision` için silme yalnız mevcut
    `delete_stage_decision` — aktarım tarafında hiç yok."""
    yonetici = Path(stage_decisions.__file__).read_text(encoding="utf-8")
    assert len(re.findall(r"db\.delete\(", yonetici)) == 1
    aktarim = Path(__file__).resolve().parents[1] / "scripts" / "hukdok_aktarim.py"
    govde = aktarim.read_text(encoding="utf-8")
    assert "delete_stage_decision" not in govde
    assert not re.search(r"CaseStageDecision\)[^\n]*\.delete\(", govde)
