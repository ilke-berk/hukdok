"""G151 — Karar durumu havuzları: `Kapalı`/`Derdest` yerel havuzdan çıkar,
aktarımda "karar yok" kuralı, istinaf/temyiz/yerel seed genişlemesi.

Kullanıcı kararı 08.09 (plan §1.2 A4 + A5): `Kapalı` ve `Derdest` mahkeme
kararı değil büro dosya durumudur; ekip 409 hücreye bu değerleri "bizim
havuzumuzda var diye" yazmıştı. İstinaf/temyiz havuzları HMK 353/1-b-2
düzelterek karar ailesini taşımıyordu (193+15+3 föy "tanınmayan").

Katmanlar:
1. Seed sabitleri — yerel 27 (28 − 2 + 1), istinaf 8, temyiz 4; `Karar` YOK.
2. Kapalı havuz doğrulaması (`_validated_karar_durumu`) yeni değerleri geçirir,
   çıkarılan değerleri reddeder (mekanizma DEĞİŞMEDİ — yalnız liste içeriği).
3. Aktarım "karar yok" kuralı: künye boş → satır yazılmaz; künye dolu → durum
   boş + şerh; sayaç + INFO; toleranslı yazım; kardeş uzlaşısında imza dışı;
   ikinci koşu 0; havuz dışı davranış (G076) değişmedi.
4. `deger_havuzu_seed`: paketten büro durumu havuza girmez; `--kaldir` kuru
   koşu varsayılan, kullanılan satır silinmez.

Fixture'lar G064/G076'dan (pysqlite SAVEPOINT reçetesi tek kaynakta durmalı).
Gerçek paket repoya GİRMEZ (A.2) — sentetik paket.
"""
import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from managers import seed_data, stage_decisions
from managers.stage_decisions import InvalidDecisionStatusError
from scripts import deger_havuzu_seed as seed
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import (
    BURO_DURUMLARI,
    BURO_DURUMU_SERHI,
    CIKIS_TAMAM,
    AktarimSonucu,
    HamSatir,
    aktarimi_kos,
    ozet_metni,
)

# Aktarım koşusunun fixture'ları TEK KAYNAKTAN; ruff fixture parametresini
# yeniden tanımlama sanar (F811), kullanım yerinde susturulur.
from tests.test_g064_aktarim_cekirdek import (  # noqa: F401
    _asama_paketi_yaz,
    _satir,
    db_env,
    uc_kart,
)
from tests.test_g076_havuz_disi_serhi import _asama_paketi

YENI_ISTINAF = [
    "Düzeltilerek Karar Verildi", "Düzeltilerek Kabul Edildi", "Düzeltilerek Reddine",
    "Kısmen Kabul", "Davacı İstinaf Talebinin Kabulü",
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Seed sabitleri
# ═══════════════════════════════════════════════════════════════════════════

def test_seed_sayilari_27_8_4():
    assert len(seed_data.LOCAL_DECISIONS) == 27
    assert len(seed_data.APPEAL_DECISIONS) == 8
    assert len(seed_data.CASSATION_DECISIONS) == 4
    assert len(seed_data.REVISION_DECISIONS) == 2           # dokunulmadı


def test_yerel_havuzda_kapali_derdest_yok_red_usulden_var():
    yerel = [ad for _, ad in seed_data.LOCAL_DECISIONS]
    assert "Kapalı" not in yerel and "Derdest" not in yerel
    assert "Red/Usulden" in yerel
    # büro durumu anahtarları seed'in hiçbir listesinde yok (toleranslı karşılaştırma)
    for sabit in (seed_data.LOCAL_DECISIONS, seed_data.APPEAL_DECISIONS,
                  seed_data.CASSATION_DECISIONS, seed_data.REVISION_DECISIONS):
        assert not any(hukdok_aktarim._baslik_anahtari(ad) in BURO_DURUMLARI for _, ad in sabit)


def test_istinaf_ve_temyiz_genislemesi_birebir_yazim():
    istinaf = [ad for _, ad in seed_data.APPEAL_DECISIONS]
    for ad in YENI_ISTINAF:
        assert ad in istinaf, ad
    assert istinaf[:3] == ["Kaldırma", "Kaldırma/Yeniden Hüküm", "Başvuru Ret"]   # eski sıra korunur
    temyiz = [ad for _, ad in seed_data.CASSATION_DECISIONS]
    assert temyiz == ["Bozma", "Onama", "Düzelterek Onama", "Kısmen Onama/Kısmen Bozma"]


def test_karar_degeri_hicbir_havuzda_yok():
    """`Karar` (74 föy) BİLEREK eklenmedi — anlamı belirsiz, ekibe soruldu (plan §4-6)."""
    for sabit in (seed_data.LOCAL_DECISIONS, seed_data.APPEAL_DECISIONS,
                  seed_data.CASSATION_DECISIONS, seed_data.REVISION_DECISIONS):
        assert "Karar" not in [ad for _, ad in sabit]
        assert "KARAR" not in [kod for kod, _ in sabit]


def test_kodlar_tekil_ve_ascii():
    for sabit in (seed_data.LOCAL_DECISIONS, seed_data.APPEAL_DECISIONS, seed_data.CASSATION_DECISIONS):
        kodlar = [kod for kod, _ in sabit]
        assert len(set(kodlar)) == len(kodlar)
        assert all(kod.isascii() and kod == kod.upper() for kod in kodlar)
    assert dict(seed_data.LOCAL_DECISIONS)["RED_USULDEN"] == "Red/Usulden"
    assert dict(seed_data.CASSATION_DECISIONS)["KISMEN_ONAMA_KISMEN_BOZMA"] == "Kısmen Onama/Kısmen Bozma"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Kapalı havuz doğrulaması — mekanizma aynı, içerik yeni
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def seedli_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    fabrika = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = fabrika()
    try:
        for model, sabit in ((models.LocalDecision, seed_data.LOCAL_DECISIONS),
                             (models.AppealDecision, seed_data.APPEAL_DECISIONS),
                             (models.CassationDecision, seed_data.CASSATION_DECISIONS)):
            for i, (kod, ad) in enumerate(sabit):
                db.add(model(code=kod, name=ad, active=True, sequence=i))
        db.commit()
        yield db
    finally:
        db.close()
        engine.dispose()


def test_yeni_degerler_dogrulamadan_gecer(seedli_db):
    assert stage_decisions._validated_karar_durumu(seedli_db, "YEREL", "Red/Usulden") == "Red/Usulden"
    for ad in YENI_ISTINAF:
        assert stage_decisions._validated_karar_durumu(seedli_db, "ISTINAF", ad) == ad
    assert stage_decisions._validated_karar_durumu(
        seedli_db, "TEMYIZ", "Kısmen Onama/Kısmen Bozma") == "Kısmen Onama/Kısmen Bozma"


def test_cikarilan_degerler_artik_havuz_disi(seedli_db):
    """Eski kodda `Kapalı`/`Derdest` YEREL havuzundan geçiyordu — artık reddedilir."""
    for ad in ("Kapalı", "Derdest"):
        with pytest.raises(InvalidDecisionStatusError):
            stage_decisions._validated_karar_durumu(seedli_db, "YEREL", ad)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Aktarım "karar yok" kuralı
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def zemin(uc_kart):  # noqa: F811
    """Üç kart + G060 kapalı havuzları (Kapalı/Derdest artık YOK)."""
    db = uc_kart()
    try:
        db.add(models.LocalDecision(code="RED-ESAS", name="Red/Esastan"))
        db.add(models.LocalDecision(code="KABUL", name="Kabul"))
        db.commit()
    finally:
        db.close()
    return uc_kart


def _asama_satirlari(fabrika):
    db = fabrika()
    try:
        satirlar = db.query(models.CaseStageDecision).order_by(models.CaseStageDecision.id).all()
        for s in satirlar:
            db.expunge(s)
        return satirlar
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


def _tarihce_sayisi(fabrika):
    db = fabrika()
    try:
        return db.query(models.CaseHistory).filter(
            models.CaseHistory.field_name.like("case_stage_decisions%")).count()
    finally:
        db.close()


@pytest.mark.parametrize("ham", ["Kapalı", "Derdest", "KAPALI", " derdest ", "DERDEST", "kapali"])
def test_buro_durumu_anahtari_toleransli(ham):
    assert hukdok_aktarim._buro_durumu_mu(ham)


@pytest.mark.parametrize("ham", [None, "", "Kabul", "Red/Esastan", "Karar", "Kapalı Dosya"])
def test_buro_durumu_anahtari_baskasini_yakalamaz(ham):
    assert not hukdok_aktarim._buro_durumu_mu(ham)


def test_kunye_bos_buro_durumu_satir_yazilmaz_sayac_info(zemin, tmp_path, caplog):
    """Künye boş + `Derdest` → aşama satırı HİÇ yazılmaz; sayaç 1; INFO (WARNING değil).
    Eski kodda bu satır "havuz dışı durum: Derdest" şerhiyle yazılırdı."""
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel",
          "Karar Durumu": "Derdest", "Güven": "KESİN"}],
    )
    with caplog.at_level(logging.INFO):
        sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM
    assert sonuc.buro_durumu_atlanan == 1
    assert sonuc.asama_eklenen == 0 and sonuc.havuz_disi_durum == 0
    assert _asama_satirlari(zemin) == []
    assert _kart(zemin).yerel_karar_durumu is None
    buro_kayitlari = [r for r in caplog.records if "büro durumu" in r.getMessage()]
    assert buro_kayitlari and all(r.levelno == logging.INFO for r in buro_kayitlari)
    assert not any(r.levelno >= logging.WARNING and "havuz dışı" in r.getMessage() for r in caplog.records)


def test_kunye_dolu_buro_durumu_durumsuz_serhli_yazilir_ikinci_kosu_sifir(zemin, tmp_path):
    """Künye dolu + `Kapalı` → satır durumsuz + "büro durumu, karar değil: Kapalı"
    şerhiyle yazılır; fotoğraf boş; aynı paketle ikinci koşu 0 yazma."""
    paket = _asama_paketi(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel", "Mahkeme": "İstanbul 8. Tüketici",
          "Esas No": "2023/1", "Karar No": "2024/5", "Karar Tarihi": "05.05.2024",
          "Karar Durumu": "Kapalı", "Açıklama": "dosya işlemde", "Güven": "KESİN"}],
    )
    ilk = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert ilk.buro_durumu_atlanan == 1 and ilk.asama_eklenen == 1 and ilk.havuz_disi_durum == 0
    satirlar = _asama_satirlari(zemin)
    assert len(satirlar) == 1
    satir = satirlar[0]
    assert satir.karar_durumu is None
    assert satir.karar_no == "2024/5"
    assert satir.aciklama == f"dosya işlemde · {BURO_DURUMU_SERHI}: Kapalı"
    kart = _kart(zemin)
    assert kart.yerel_karar_durumu is None and kart.karar_no == "2024/5"

    ikinci = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor2")
    assert (ikinci.asama_eklenen, ikinci.asama_guncellenen, ikinci.asama_ikinci_tur) == (0, 0, 0)
    assert ikinci.buro_durumu_atlanan == 1                 # her koşuda yeniden sayılır, yazma 0
    assert len(_asama_satirlari(zemin)) == 1
    assert _tarihce_sayisi(zemin) == 0


def test_yazim_toleransi_buyuk_harf_ve_bosluk(zemin, tmp_path):
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1"), _satir("H-2", "D-2")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel", "Karar Durumu": "KAPALI", "Güven": "KESİN"},
         {"SistemNo": "H-2", "AsamaNo": 1, "Aşama": "Yerel", "Karar Durumu": "  derdest ", "Güven": "KESİN"}],
    )
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert sonuc.buro_durumu_atlanan == 2 and sonuc.asama_eklenen == 0 and sonuc.havuz_disi_durum == 0
    assert _asama_satirlari(zemin) == []


def test_atlanan_satir_sira_tuketmez(zemin, tmp_path):
    """Künyesiz Derdest satırı 1. sırada, gerçek karar 2. sırada → yazılan satır sira_no 1."""
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel", "Karar Durumu": "Derdest", "Güven": "KESİN"},
         {"SistemNo": "H-1", "AsamaNo": 2, "Aşama": "Yerel", "Esas No": "2023/1",
          "Karar Durumu": "Kabul", "Güven": "KESİN"}],
    )
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert sonuc.buro_durumu_atlanan == 1 and sonuc.asama_eklenen == 1
    satirlar = _asama_satirlari(zemin)
    assert [(s.sira_no, s.karar_durumu) for s in satirlar] == [(1, "Kabul")]


def test_kardes_foyde_buro_durumu_imzaya_girmez_gercek_sonuc_kazanir(zemin, tmp_path):
    """H-1 `Derdest`, H-2 `Kabul` (aynı kart, aynı aşama) → çelişki DEĞİL, tek satır `Kabul`."""
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1"), _satir("H-2", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel", "Esas No": "2023/1",
          "Karar Durumu": "Derdest", "Güven": "KESİN"},
         {"SistemNo": "H-2", "AsamaNo": 1, "Aşama": "Yerel", "Esas No": "2023/1",
          "Karar Durumu": "Kabul", "Güven": "KESİN"}],
    )
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert [c for c in sonuc.celiskiler if c.alan.startswith("asama:")] == []
    assert sonuc.asama_eklenen == 1 and sonuc.buro_durumu_atlanan == 0
    satirlar = _asama_satirlari(zemin)
    assert [(s.karar_durumu, s.aciklama) for s in satirlar] == [("Kabul", None)]


def test_kardeslerin_ikisi_de_buro_durumu_ise_kural_uygulanir(zemin, tmp_path):
    """İki kardeş de `Derdest` (künye dolu) → tek satır durumsuz + şerh, sayaç 1."""
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1"), _satir("H-2", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel", "Esas No": "2023/1",
          "Karar Durumu": "Derdest", "Güven": "KESİN"},
         {"SistemNo": "H-2", "AsamaNo": 1, "Aşama": "Yerel", "Esas No": "2023/1",
          "Karar Durumu": "DERDEST", "Güven": "KESİN"}],
    )
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert sonuc.asama_eklenen == 1 and sonuc.buro_durumu_atlanan == 1
    satir = _asama_satirlari(zemin)[0]
    assert satir.karar_durumu is None and satir.esas_no == "2023/1"
    assert satir.aciklama == f"{BURO_DURUMU_SERHI}: Derdest"


def test_eski_kurulumdaki_derdest_satiri_paketle_durumsuz_olur(zemin, tmp_path):
    """Eski havuzla yazılmış `Derdest` satırı (künyeli) yeni paketle yerinde
    güncellenir: durum NULL + şerh, tarihçeli (G150 güncelleme yolu)."""
    db = zemin()
    try:
        db.add(models.LocalDecision(code="DERDEST", name="Derdest"))   # eski kurulum kalıntısı
        db.commit()
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        stage_decisions.add_stage_decision(
            db, kart, stage="YEREL", dogrulama_durumu="TURETILDI", source="HUKDOK_TESLIM_eski",
            esas_no="2023/1", karar_durumu="Derdest")
        db.commit()
    finally:
        db.close()
    assert _kart(zemin).yerel_karar_durumu == "Derdest"

    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel", "Esas No": "2023/1",
          "Karar Durumu": "Derdest", "Güven": "KESİN"}],
    )
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert sonuc.asama_guncellenen == 1 and sonuc.buro_durumu_atlanan == 1
    satir = _asama_satirlari(zemin)[0]
    assert satir.karar_durumu is None and satir.aciklama == f"{BURO_DURUMU_SERHI}: Derdest"
    assert _kart(zemin).yerel_karar_durumu is None            # fotoğraf izledi
    assert _tarihce_sayisi(zemin) == 2                         # karar_durumu + aciklama


def test_havuz_disi_davranisi_degismedi(zemin, tmp_path):
    """Gerileme nöbetçisi (G076): gerçek havuz dışı değer yine durum boş + şerh + WARNING sayacı."""
    paket = _asama_paketi_yaz(
        tmp_path / "teslim.xlsx",
        [_satir("H-1", "D-1")],
        [{"SistemNo": "H-1", "AsamaNo": 1, "Aşama": "Yerel",
          "Karar Durumu": "Lexis Rapor Gönderildi", "Güven": "KESİN"}],
    )
    sonuc = aktarimi_kos(zemin, girdi=paket, rapor_dizini=tmp_path / "rapor")
    assert sonuc.havuz_disi_durum == 1 and sonuc.buro_durumu_atlanan == 0 and sonuc.asama_eklenen == 1
    satir = _asama_satirlari(zemin)[0]
    assert satir.karar_durumu is None
    assert satir.aciklama == "havuz dışı durum: Lexis Rapor Gönderildi"


def test_kunye_dolu_ayraci():
    bos = HamSatir(satir_no=2, degerler={"karar_durumu": "Derdest", "aciklama": "not"})
    assert not hukdok_aktarim._kunye_dolu(bos)
    for alan, deger in (("mahkeme", "İstanbul 8. Tüketici"), ("esas_no", "2023/1"),
                        ("karar_no", "2024/1"), ("karar_tarihi", "05.05.2024"),
                        ("teblig_tarihi", "06.06.2024")):
        dolu = HamSatir(satir_no=2, degerler={"karar_durumu": "Derdest", alan: deger})
        assert hukdok_aktarim._kunye_dolu(dolu), alan
    # yer tutucu tarih künye sayılmaz
    assert not hukdok_aktarim._kunye_dolu(
        HamSatir(satir_no=2, degerler={"karar_durumu": "Kapalı", "karar_tarihi": "01.01.1900"}))


def test_ozet_metninde_sayac_gorunur():
    sonuc = AktarimSonucu(kaynak_imzasi="HUKDOK_TESLIM_test", buro_durumu_atlanan=3)
    assert "büro durumu atlanan: 3" in ozet_metni(sonuc)
    assert "büro durumu atlanan" not in ozet_metni(AktarimSonucu(kaynak_imzasi="x"))


# ═══════════════════════════════════════════════════════════════════════════
# 4. deger_havuzu_seed — paket elemesi + --kaldir
# ═══════════════════════════════════════════════════════════════════════════

def _sheet_paketi(yol, satirlar, basliklar):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet"
    ws.append(basliklar)
    for satir in satirlar:
        ws.append([satir.get(b) for b in basliklar])
    wb.save(yol)
    wb.close()
    return Path(yol)


def test_karar_listeleri_stage_haritasindan_turetildi():
    assert seed.KARAR_LISTELERI == {
        "local_decisions", "appeal_decisions", "cassation_decisions", "revision_decisions"}


def test_paket_seedi_buro_durumunu_havuza_sokmaz(db_env, tmp_path):  # noqa: F811
    basliklar = ["SistemNo", "Yerel Mahkeme Karar Durumu", "İstinaf Karar Durumu", "Davalı İdare"]
    paket = _sheet_paketi(tmp_path / "p.xlsx", [
        {"SistemNo": "H-1", "Yerel Mahkeme Karar Durumu": "Kapalı", "İstinaf Karar Durumu": "DERDEST",
         "Davalı İdare": "Derdest"},
        {"SistemNo": "H-2", "Yerel Mahkeme Karar Durumu": "Derdest", "İstinaf Karar Durumu": "Karar Aaleyhe"},
        {"SistemNo": "H-3", "Yerel Mahkeme Karar Durumu": "Red/Usulden"},
    ], basliklar)
    sonuclar = seed.havuzlari_kur(db_env, girdi=paket, apply=True)
    yeni = {s.liste_adi: s.yeni for s in sonuclar}
    assert yeni["local_decisions"] == 1                      # yalnız Red/Usulden
    assert yeni["appeal_decisions"] == 1                      # bozuk yazım GEÇER, Derdest geçmez
    assert yeni["defendant_administrations"] == 1             # karar listesi değil: eleme yok
    db = db_env()
    try:
        assert [r.name for r in db.query(models.LocalDecision)] == ["Red/Usulden"]
        assert [r.name for r in db.query(models.AppealDecision)] == ["Karar Aaleyhe"]
    finally:
        db.close()


@pytest.fixture()
def kaldirma_zemini(uc_kart):  # noqa: F811
    """Yerel havuzda Kapalı (kullanılmıyor) + Derdest (1 kart kolonu + 1 aşama satırı) + Kabul."""
    db = uc_kart()
    try:
        db.add(models.LocalDecision(code="KAPALI", name="Kapalı"))
        db.add(models.LocalDecision(code="DERDEST", name="Derdest"))
        db.add(models.LocalDecision(code="KABUL", name="Kabul"))
        db.commit()
        kart = db.query(models.Case).filter_by(klasor_no_2="D-1").one()
        stage_decisions.add_stage_decision(
            db, kart, stage="YEREL", dogrulama_durumu="BELIRSIZ", source="takip-paneli",
            esas_no="2023/1", karar_durumu="Derdest")
        db.commit()
    finally:
        db.close()
    return uc_kart


def _liste(fabrika):
    db = fabrika()
    try:
        return sorted(r.name for r in db.query(models.LocalDecision))
    finally:
        db.close()


def test_kaldir_kuru_kosu_varsayilan_hicbir_sey_silmez(kaldirma_zemini):
    sonuclar = seed.havuz_satirlarini_kaldir(
        kaldirma_zemini, liste_adi="local_decisions", adlar=["Kapalı", "derdest", "Yok Böyle"])
    kapali, derdest, yok = sonuclar
    assert kapali.bulunan == "Kapalı" and not kapali.kullaniliyor and not kapali.silindi
    assert derdest.bulunan == "Derdest" and (derdest.kart_kullanimi, derdest.asama_kullanimi) == (1, 1)
    assert yok.bulunan is None and not yok.silindi
    assert _liste(kaldirma_zemini) == ["Derdest", "Kabul", "Kapalı"]      # kuru koşu: dokunulmadı
    ozet = seed.kaldirma_ozeti(sonuclar, apply=False)
    assert "silinebilir (kuru koşu)" in ozet and "KULLANILIYOR" in ozet and "listede yok" in ozet


def test_kaldir_apply_kullanilmayani_siler_kullanilani_korur(kaldirma_zemini):
    sonuclar = seed.havuz_satirlarini_kaldir(
        kaldirma_zemini, liste_adi="local_decisions", adlar=["Kapalı", "Derdest"], apply=True)
    kapali, derdest = sonuclar
    assert kapali.silindi and not derdest.silindi
    assert _liste(kaldirma_zemini) == ["Derdest", "Kabul"]
    # ikinci koşu: Kapalı artık yok, Derdest yine korunur
    tekrar = seed.havuz_satirlarini_kaldir(
        kaldirma_zemini, liste_adi="local_decisions", adlar=["Kapalı", "Derdest"], apply=True)
    assert tekrar[0].bulunan is None and not tekrar[1].silindi
    assert _liste(kaldirma_zemini) == ["Derdest", "Kabul"]
    assert "SİLİNDİ" in seed.kaldirma_ozeti(sonuclar, apply=True)


def test_kaldir_bilinmeyen_liste_reddedilir(kaldirma_zemini):
    with pytest.raises(ValueError, match="bilinmeyen liste"):
        seed.havuz_satirlarini_kaldir(kaldirma_zemini, liste_adi="olmayan", adlar=["x"])


def test_cli_kaldir_kuru_kosu_ve_input_zorunlulugu(kaldirma_zemini, monkeypatch, capsys):
    import database

    monkeypatch.setattr(database, "SessionLocal", kaldirma_zemini)
    assert seed.main(["--kaldir", "Kapalı", "--kaldir", "Derdest"]) == 0
    cikti = capsys.readouterr().out
    assert "kuru koşu, yazılmadı" in cikti and "KULLANILIYOR" in cikti
    assert _liste(kaldirma_zemini) == ["Derdest", "Kabul", "Kapalı"]
    with pytest.raises(SystemExit):
        seed.main([])                                        # ne --input ne --kaldir
