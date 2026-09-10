"""G155 — Karar_Asamalari `Başvuru Tarihi` (plan 08.09 §1.2 A6, ekip 06.09 §7).

Ekip aşama sayfasına 22. sütun olarak "Başvuru Tarihi"ni ekliyor: istinaf/
temyiz başvuru tarihi tek kaynaktan gelsin. Bu dosya kilitler:

  (1) okuyucu sütunu tanır → `case_stage_decisions.basvuru_tarihi`;
  (2) fotoğraf: ISTINAF → `cases.istinaf_basvuru_tarihi`, TEMYIZ →
      `cases.temyiz_basvuru_tarihi`;
  (3) sütun YOK paketle (21 sütun, eski format) geriye uyumlu;
  (4) Sheet'in "İstinaf Mahkeme Başvuru Tar." sütunu YEDEK kaynaktır: yalnız
      aşama değeri boşken yazar; aşama sayfası önceliklidir ve iki yazıcı
      salınmaz (ikinci koşu 0);
  (5) imza: kardeş föyler farklı başvuru tarihi söylüyorsa çelişki;
  (6) yönetici: içerik alanı (fark/güncelleme/silme fotoğrafı);
  (7) migrasyon op'u var ve idempotent (çift koşu).

Fixture'lar G064'ten (pysqlite SAVEPOINT reçetesi tek kaynakta durmalı).
"""
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

import database
import models
from managers import stage_decisions
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import CIKIS_TAMAM, HamSatir, aktarimi_kos

# Aktarım koşusunun fixture'ları TEK KAYNAKTAN; ruff fixture parametresini
# yeniden tanımlama sanar (F811), kullanım yerinde susturulur.
from tests.test_g064_aktarim_cekirdek import (  # noqa: F401
    _satir,
    db_env,
    uc_kart,
)

SHEET_BASLIKLARI = ["SistemNo", "TKU", "Dosya No", "İstinaf Mahkeme Başvuru Tar."]
# Ekibin 22 sütunlu sayfası (bizim okuduğumuz alt küme) ve 21 sütunlu eski hâli.
ASAMA_22 = ["SistemNo", "AsamaNo", "Aşama", "Mahkeme", "Esas No", "Karar No",
            "Karar Tarihi", "Karar Durumu", "Tebliğ Tarihi", "Başvuru Tarihi",
            "Başvuran Taraf", "Güven"]
ASAMA_21 = [b for b in ASAMA_22 if b != "Başvuru Tarihi"]


def _paket(yol, foyler, asamalar, *, asama_basliklari=ASAMA_22):
    """İki sayfalı sentetik paket: Sheet (+ istinaf başvuru sütunu) + Karar_Asamalari."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Föyler"
    ws.append(SHEET_BASLIKLARI)
    for satir in foyler:
        ws.append([satir.get(b) for b in SHEET_BASLIKLARI])
    wa = wb.create_sheet("Karar_Asamalari")
    wa.append(asama_basliklari)
    for satir in asamalar:
        wa.append([satir.get(b) for b in asama_basliklari])
    wb.save(yol)
    wb.close()
    return Path(yol)


def _istinaf(sistem_no, **alanlar):
    temel = {"SistemNo": sistem_no, "AsamaNo": 2, "Aşama": "İstinaf",
             "Mahkeme": "İSTANBUL BİM 7. HD", "Esas No": "2021/1479",
             "Karar Tarihi": "01.03.2022", "Karar Durumu": "Başvuru Ret",
             "Başvuru Tarihi": "10.01.2024", "Güven": "KESİN"}
    temel.update(alanlar)
    return temel


def _temyiz(sistem_no, **alanlar):
    temel = {"SistemNo": sistem_no, "AsamaNo": 3, "Aşama": "Temyiz",
             "Mahkeme": "Yargıtay 3. HD", "Esas No": "2023/500",
             "Karar Tarihi": "01.09.2024", "Karar Durumu": "Onama",
             "Başvuru Tarihi": "15.06.2025", "Güven": "KESİN"}
    temel.update(alanlar)
    return temel


@pytest.fixture()
def zemin(uc_kart):  # noqa: F811
    """Üç kart + G060 kapalı havuzları (boş listede tarihçe yolu hiçbir değeri
    geçirmez)."""
    db = uc_kart()
    try:
        db.add(models.LocalDecision(code="KABUL", name="Kabul"))
        db.add(models.AppealDecision(code="BASVURU-RET", name="Başvuru Ret"))
        db.add(models.CassationDecision(code="ONAMA", name="Onama"))
        db.commit()
    finally:
        db.close()
    return uc_kart


def _satirlar(fabrika, klasor="D-1"):
    db = fabrika()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2=klasor).one()
        satirlar = stage_decisions.get_stage_decisions(db, kart.id)
        for s in satirlar:
            db.expunge(s)
        return {(s.stage, s.sira_no): s for s in satirlar}
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


def _tarihce(fabrika):
    db = fabrika()
    try:
        return [
            (h.field_name, h.old_value, h.new_value)
            for h in db.query(models.CaseHistory).order_by(models.CaseHistory.id)
        ]
    finally:
        db.close()


# ─── Kayıt kilitleri (DB yok) ────────────────────────────────────────────────

def test_kayit_kilitleri():
    assert hukdok_aktarim.ASAMA_SUTUNLARI["basvuru_tarihi"] == ("Başvuru Tarihi",)
    assert "basvuru_tarihi" in hukdok_aktarim._IMZA_ALANLARI
    assert "basvuru_tarihi" in stage_decisions.CONTENT_FIELDS
    assert stage_decisions._PHOTO_COLUMNS["ISTINAF"]["basvuru_tarihi"] == "istinaf_basvuru_tarihi"
    assert stage_decisions._PHOTO_COLUMNS["TEMYIZ"]["basvuru_tarihi"] == "temyiz_basvuru_tarihi"
    # Yerel/karar düzeltme için kart slot kolonu yok → fotoğraf da yok.
    assert "basvuru_tarihi" not in stage_decisions._PHOTO_COLUMNS["YEREL"]
    assert "basvuru_tarihi" not in stage_decisions._PHOTO_COLUMNS["KARAR_DUZELTME"]
    # Sheet kart yolu KALDI (G123 kilidi) — yalnız aşama satırı taşıyorsa atlanır.
    assert hukdok_aktarim.KART_ALANLARI["istinaf_basvuru_tarihi"] == (
        "istinaf_basvuru_tarihi", hukdok_aktarim._tarih)


def test_imza_bos_basvuru_tarihi_katilmaz_dolu_katilir():
    dolu = HamSatir(satir_no=2, degerler={"basvuru_tarihi": "10.01.2024"})
    bos = HamSatir(satir_no=3, degerler={"basvuru_tarihi": None})
    assert hukdok_aktarim._asama_imzasi(dolu) == {"basvuru_tarihi": "2024-01-10"}
    assert hukdok_aktarim._asama_imzasi(bos) == {}
    # Başvuru tarihi tek başına künyeyi "dolu" sayar (G151 ayracı): istinaf
    # başvurusu yapılmış ama karar yok — satır anlatacak bir şey taşıyor.
    assert hukdok_aktarim._kunye_dolu(dolu) and not hukdok_aktarim._kunye_dolu(bos)


def test_asama_kaynakli_kart_alanlari_yalniz_dolu_istinaf():
    satirlar = [
        HamSatir(satir_no=2, degerler={"sistem_no": "H-1", "asama": "İstinaf", "basvuru_tarihi": "10.01.2024"}),
        HamSatir(satir_no=3, degerler={"sistem_no": "H-2", "asama": "İstinaf", "basvuru_tarihi": None}),
        HamSatir(satir_no=4, degerler={"sistem_no": "H-3", "asama": "Temyiz", "basvuru_tarihi": "10.01.2024"}),
        HamSatir(satir_no=5, degerler={"sistem_no": "H-4", "asama": "İstinaf"}),   # sütun yok
    ]
    assert hukdok_aktarim.asama_kaynakli_kart_alanlari(satirlar) == {
        "H-1": frozenset({"istinaf_basvuru_tarihi"}),
    }


# ─── (1)+(2) okuyucu + fotoğraf ──────────────────────────────────────────────

def test_basvuru_tarihi_okunur_ve_fotograflanir(zemin, tmp_path):
    paket = _paket(tmp_path / "t.xlsx", [_satir("H-1", "D-1")],
                   [_istinaf("H-1"), _temyiz("H-1")])

    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM and sonuc.asama_eklenen == 2
    satirlar = _satirlar(zemin)
    assert satirlar[("ISTINAF", 1)].basvuru_tarihi == date(2024, 1, 10)
    assert satirlar[("TEMYIZ", 1)].basvuru_tarihi == date(2025, 6, 15)
    kart = _kart(zemin)
    assert kart.istinaf_basvuru_tarihi == date(2024, 1, 10)
    assert kart.temyiz_basvuru_tarihi == date(2025, 6, 15)
    # Kart yolu Sheet'ten yazmadı (hücre boş) — tarihçede kart alanı satırı yok
    assert [t for t in _tarihce(zemin) if t[0] == "istinaf_basvuru_tarihi"] == []


def test_yerel_satirda_basvuru_tarihi_saklanir_kart_slotu_yok(zemin, tmp_path):
    """YEREL satırı da alanı taşır (tarihçe kayıpsız) ama kartta fotoğrafı yok."""
    paket = _paket(tmp_path / "t.xlsx", [_satir("H-1", "D-1")], [
        {"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel", "Mahkeme": "İstanbul 8. Tüketici",
         "Esas No": "2020/143", "Karar Tarihi": "05.05.2021", "Karar Durumu": "Kabul",
         "Başvuru Tarihi": "01.02.2020", "Güven": "KESİN"},
    ])
    aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert _satirlar(zemin)[("YEREL", 1)].basvuru_tarihi == date(2020, 2, 1)
    kart = _kart(zemin)
    assert kart.istinaf_basvuru_tarihi is None and kart.temyiz_basvuru_tarihi is None


# ─── (3) sütun yok — geriye uyumlu ───────────────────────────────────────────

def test_sutun_yok_eski_paket_ayni_calisir(zemin, tmp_path):
    """21 sütunlu (eski) sayfa: alan okunmaz, satır yine yazılır, hata yok."""
    paket = _paket(tmp_path / "t.xlsx", [_satir("H-1", "D-1")],
                   [_istinaf("H-1")], asama_basliklari=ASAMA_21)

    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM and sonuc.asama_eklenen == 1
    satir = _satirlar(zemin)[("ISTINAF", 1)]
    assert satir.basvuru_tarihi is None and satir.esas_no == "2021/1479"
    assert _kart(zemin).istinaf_basvuru_tarihi is None


def test_sutun_yok_sheet_yedegi_asama_satirini_ve_karti_besler(zemin, tmp_path):
    """Eski sayfa + Sheet'te başvuru tarihi: yedek kaynak aşama satırına
    girer, fotoğraf ve kart yolu AYNI değeri yazar — ikinci koşu 0."""
    paket = _paket(
        tmp_path / "t.xlsx",
        [_satir("H-1", "D-1", **{"İstinaf Mahkeme Başvuru Tar.": datetime(2025, 11, 24)})],
        [_istinaf("H-1")], asama_basliklari=ASAMA_21,
    )
    ilk = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.asama_eklenen == 1
    assert _satirlar(zemin)[("ISTINAF", 1)].basvuru_tarihi == date(2025, 11, 24)
    assert _kart(zemin).istinaf_basvuru_tarihi == date(2025, 11, 24)
    tarihce = _tarihce(zemin)
    assert ("istinaf_basvuru_tarihi", None, "2025-11-24") in tarihce   # kart yolu yazdı

    ikinci = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert (ikinci.asama_eklenen, ikinci.asama_guncellenen) == (0, 0)
    assert _tarihce(zemin) == tarihce


# ─── (4) öncelik: aşama sayfası; Sheet yalnız boşken ────────────────────────

def test_asama_sayfasi_onceliklidir_sheet_yazmaz_ikinci_kosu_sifir(zemin, tmp_path):
    """Sheet 24.11.2025, aşama 10.01.2024 → kart 10.01.2024; kart yolu Sheet
    değerini YAZMAZ (tarihçe yok); ikinci koşu hiçbir şey değiştirmez."""
    paket = _paket(
        tmp_path / "t.xlsx",
        [_satir("H-1", "D-1", **{"İstinaf Mahkeme Başvuru Tar.": datetime(2025, 11, 24)})],
        [_istinaf("H-1")],
    )
    ilk = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert ilk.cikis_kodu == CIKIS_TAMAM
    assert _satirlar(zemin)[("ISTINAF", 1)].basvuru_tarihi == date(2024, 1, 10)
    assert _kart(zemin).istinaf_basvuru_tarihi == date(2024, 1, 10)
    tarihce = _tarihce(zemin)
    assert [t for t in tarihce if t[0] == "istinaf_basvuru_tarihi"] == []

    ikinci = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert (ikinci.asama_eklenen, ikinci.asama_guncellenen) == (0, 0)
    assert _tarihce(zemin) == tarihce
    assert _kart(zemin).istinaf_basvuru_tarihi == date(2024, 1, 10)


def test_asama_hucresi_bosken_sheet_yedegi_yazar(zemin, tmp_path):
    """22 sütunlu sayfa ama hücre boş → Sheet değeri satıra ve karta."""
    paket = _paket(
        tmp_path / "t.xlsx",
        [_satir("H-1", "D-1", **{"İstinaf Mahkeme Başvuru Tar.": datetime(2025, 11, 24)})],
        [_istinaf("H-1", **{"Başvuru Tarihi": None})],
    )
    aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert _satirlar(zemin)[("ISTINAF", 1)].basvuru_tarihi == date(2025, 11, 24)
    assert _kart(zemin).istinaf_basvuru_tarihi == date(2025, 11, 24)


def test_temyizin_sheet_yedegi_yok(zemin, tmp_path):
    """Sheet'teki sütun İSTİNAF başvurusudur; temyiz satırı ondan beslenmez."""
    paket = _paket(
        tmp_path / "t.xlsx",
        [_satir("H-1", "D-1", **{"İstinaf Mahkeme Başvuru Tar.": datetime(2025, 11, 24)})],
        [_temyiz("H-1", **{"Başvuru Tarihi": None})],
    )
    aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert _satirlar(zemin)[("TEMYIZ", 1)].basvuru_tarihi is None
    kart = _kart(zemin)
    assert kart.temyiz_basvuru_tarihi is None
    assert kart.istinaf_basvuru_tarihi == date(2025, 11, 24)   # kart yolu (aşama satırı yok)


def test_yeni_paket_basvuru_tarihini_yerinde_gunceller_tarihceli(zemin, tmp_path):
    eski = _paket(tmp_path / "p1.xlsx", [_satir("H-1", "D-1")], [_istinaf("H-1")])
    aktarimi_kos(zemin, girdi=eski, rapor_dizini=tmp_path / "rapor")
    yeni = _paket(tmp_path / "p2.xlsx", [_satir("H-1", "D-1")],
                  [_istinaf("H-1", **{"Başvuru Tarihi": "12.01.2024"})])

    sonuc = aktarimi_kos(zemin, girdi=yeni, rapor_dizini=tmp_path / "rapor")

    assert (sonuc.asama_eklenen, sonuc.asama_guncellenen) == (0, 1)
    assert _satirlar(zemin)[("ISTINAF", 1)].basvuru_tarihi == date(2024, 1, 12)
    assert _kart(zemin).istinaf_basvuru_tarihi == date(2024, 1, 12)
    assert ("case_stage_decisions.ISTINAF.1.basvuru_tarihi", "2024-01-10", "2024-01-12") in _tarihce(zemin)


# ─── (5) imza ────────────────────────────────────────────────────────────────

def test_kardes_foyler_farkli_basvuru_tarihi_celiski(zemin, tmp_path):
    paket = _paket(
        tmp_path / "t.xlsx",
        [_satir("H-1", "D-1"), _satir("H-2", "D-1")],
        [_istinaf("H-1"), _istinaf("H-2", **{"Başvuru Tarihi": "11.01.2024"})],
    )
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert sonuc.asama_eklenen == 0 and _satirlar(zemin) == {}
    assert [c.alan for c in sonuc.celiskiler] == ["asama:ISTINAF"]


def test_kardes_foyde_bos_basvuru_tarihi_celiski_degil(zemin, tmp_path):
    paket = _paket(
        tmp_path / "t.xlsx",
        [_satir("H-1", "D-1"), _satir("H-2", "D-1")],
        [_istinaf("H-1"), _istinaf("H-2", **{"Başvuru Tarihi": None})],
    )
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert sonuc.asama_eklenen == 1 and sonuc.celiskiler == []
    assert _satirlar(zemin)[("ISTINAF", 1)].basvuru_tarihi == date(2024, 1, 10)


# ─── (6) yönetici: içerik alanı ──────────────────────────────────────────────

def test_yonetici_basvuru_tarihi_icerik_alani_fotograf_ve_silme(zemin):
    db = zemin()
    try:
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        satir = stage_decisions.add_stage_decision(
            db, kart, stage="ISTINAF", karar_durumu="Başvuru Ret",
            basvuru_tarihi=date(2024, 1, 10), dogrulama_durumu="TURETILDI")
        assert kart.istinaf_basvuru_tarihi == date(2024, 1, 10)

        fark = stage_decisions.update_stage_decision(
            db, kart, satir, karar_durumu="Başvuru Ret", basvuru_tarihi=date(2024, 1, 12))
        assert fark == {"basvuru_tarihi": (date(2024, 1, 10), date(2024, 1, 12))}
        assert kart.istinaf_basvuru_tarihi == date(2024, 1, 12)
        assert stage_decisions.stage_decision_diff(
            db, satir, karar_durumu="Başvuru Ret", basvuru_tarihi=date(2024, 1, 12)) == {}

        temyiz = stage_decisions.add_stage_decision(
            db, kart, stage="TEMYIZ", karar_durumu="Onama", basvuru_tarihi=date(2025, 6, 15))
        assert kart.temyiz_basvuru_tarihi == date(2025, 6, 15)
        assert kart.istinaf_basvuru_tarihi == date(2024, 1, 12)     # başka aşamaya dokunulmadı

        assert stage_decisions.delete_stage_decision(db, kart, temyiz.id)
        assert kart.temyiz_basvuru_tarihi is None                  # fotoğraf temizlendi
    finally:
        db.close()


# ─── (7) migrasyon ───────────────────────────────────────────────────────────

def test_migrasyon_opu_var_kisit_index_yok():
    ops = [
        op for op in database._MIGRATIONS
        if op[0] == "columns" and op[1] == "case_stage_decisions" and "basvuru_tarihi" in op[2]
    ]
    assert len(ops) == 1, "case_stage_decisions.basvuru_tarihi op'u tam bir kez olmalı"
    assert ops[0][2]["basvuru_tarihi"] == "DATE"                     # post-SQL yok
    assert not any(
        op[0] == "index" and op[1] == "case_stage_decisions"
        and any("basvuru_tarihi" in sql for sql in op[2])
        for op in database._MIGRATIONS
    )


def test_migrasyon_idempotent_cift_kosu(monkeypatch):
    """Eski kurulum (kolonsuz tablo) → ilk koşu ADD COLUMN, ikinci koşu no-op.

    Liste `case_stage_decisions` op'larına süzülür (test_migration_path
    deseni): op'lar GERÇEK listeden, elle kopya değil; öteki tabloların
    Postgres'e özgü ("table", ...) DDL'leri sqlite'ta koşmaz.
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE case_stage_decisions ("
            " id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL, stage VARCHAR(20) NOT NULL,"
            " sira_no INTEGER NOT NULL, kaynak_id INTEGER)"
        ))
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "_MIGRATIONS", [
        op for op in database._MIGRATIONS if op[1] == "case_stage_decisions"
    ])

    database.check_and_migrate_tables()
    kolonlar = {c["name"] for c in inspect(engine).get_columns("case_stage_decisions")}
    assert "basvuru_tarihi" in kolonlar

    database.check_and_migrate_tables()                              # ikinci koşu: hata yok
    kolonlar = [c["name"] for c in inspect(engine).get_columns("case_stage_decisions")]
    assert kolonlar.count("basvuru_tarihi") == 1
    engine.dispose()
