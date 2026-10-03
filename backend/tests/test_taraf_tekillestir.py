"""Taraf tekilliği (03.10.2026 kullanıcı kararı): bir kartta aynı kişi TEK satır.

"3. şahıs eski TKU mantığından kalan bir kavram; müvekkil ya da karşı taraf olan kişi
ayrıca 3. şahıs olarak da görünüyorsa 3. şahıs satırı hatalıdır." Tarama (lokal, 03.10):
952 kartta aynı kişi birden çok satırda — eski import'un "Diğer Davalı" satırları, kart
birleştirmenin `(tür, ad)` anahtarı, `;`/`,` ile birleşik adlar.

Kapsam: ortak bölücü + tür önceliği (`party_check`), temizlik script'i
(`scripts/taraf_tekillestir`), kalıcı düzeltmeler (kart birleştirme anahtarı, belge
işleme, kart açma/zenginleştirme girişi).
"""
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from managers import case_manager
from party_check import (
    kurum_mu,
    normalize_party_key,
    split_party_names,
    taraf_listesini_tekillestir,
)
from scripts import mukerrer_kart_birlestir as mb
from scripts import taraf_tekillestir as tt
from scripts.hukdok_aktarim import _taraf_adlari


def _index_ops(table):
    return [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == table
            for sql in op[2] if not sql.lstrip().upper().startswith(("UPDATE", "ALTER"))]


@pytest.fixture()
def fabrika():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        dbapi_connection.isolation_level = None
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for sql in _index_ops("case_foys"):
            conn.execute(text(sql))
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


def _kart(db, tno, taraflar, *, esas="2026/305", court="Ankara 2. Tüketici Mahkemesi"):
    """taraflar: [(ad, party_type, rol)] → (kart, {ad: taraf})"""
    kart = models.Case(tracking_no=tno, status="DERDEST", court=court, file_type="Hukuk")
    db.add(kart)
    db.flush()
    case_manager.sync_current_esas(db, kart, esas, court=court, source="test")
    satirlar = {}
    for ad, tur, rol in taraflar:
        p = models.CaseParty(name=ad, party_type=tur, role=rol)
        kart.parties.append(p)
        satirlar[ad] = p
    db.flush()
    return kart, satirlar


def _taraflar(fabrika, kart_id):
    db = fabrika()
    try:
        return sorted(
            (p.name, p.party_type, p.role)
            for p in db.query(models.CaseParty).filter_by(case_id=kart_id).all()
        )
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Ortak bölücü ve anahtar — party_check
# ═══════════════════════════════════════════════════════════════════════════

def test_anahtar_virgul_artigini_ve_unvani_yok_sayar():
    assert normalize_party_key("Atilla Kurtay Dr.,") == normalize_party_key("Atilla Kurtay")
    assert normalize_party_key("AYTUN ÇANGA DR") == normalize_party_key("Aytun Çanga Dr")


def test_bolucu_noktali_virgul_ve_satir_sonunu_her_zaman_boler():
    assert split_party_names("Efsane Ballı; Funda Süreyya Cengiz;\nMert Cengiz") == [
        "Efsane Ballı", "Funda Süreyya Cengiz", "Mert Cengiz"]
    assert split_party_names("Mert Cengiz; MERT CENGİZ") == ["Mert Cengiz"]      # aynı kişi bir kez
    assert split_party_names(None) == [] and split_party_names(" ; ") == []


def test_bolucu_virgulu_yalniz_acikken_ve_kisi_adlarinda_boler():
    cok_adli = "Fuat Bora Dr.,Mehmet Can Keven Dr.,"
    assert split_party_names(cok_adli, virgul=True) == ["Fuat Bora Dr.", "Mehmet Can Keven Dr."]
    assert split_party_names(cok_adli) == ["Fuat Bora Dr.,Mehmet Can Keven Dr."]    # kullanıcı yolu: kapalı
    assert split_party_names("Atilla Kurtay Dr.,", virgul=True) == ["Atilla Kurtay Dr."]
    # Şirket/kurum adı ve tek sözcüklü parça virgülden BÖLÜNMEZ
    sirket = "Mirata Tekstil İnş. İth. ve İhr. San., Tic. Ltd. Şti."
    assert split_party_names(sirket, virgul=True) == [sirket]
    assert split_party_names("Yılmaz, Ahmet", virgul=True) == ["Yılmaz, Ahmet"]
    assert split_party_names("Ankara Şehir Hastanesi, Ali Veli", virgul=True) == [
        "Ankara Şehir Hastanesi, Ali Veli"]


def test_kurum_ayrimi_hastane_ve_bakanligi_da_tanir():
    assert kurum_mu("Bağcılar Eğitim ve Araştırma Hastanesi") and kurum_mu("Axa Sigorta A.Ş.")
    assert kurum_mu("Sağlık Bakanlığı") and not kurum_mu("Aytun Çanga Dr")


def test_aktarim_bolucusu_virgullu_muvekkil_hucresini_boler():
    assert _taraf_adlari("Ahmet Koç Dr.,Fatma Elif Gülek,") == ["Ahmet Koç Dr.", "Fatma Elif Gülek"]
    assert _taraf_adlari("Kadri Demirtuyi; Suna Demirtuyi") == ["Kadri Demirtuyi", "Suna Demirtuyi"]


def test_gelen_liste_bolunur_ve_tur_onceligiyle_tekillesir():
    sonuc = taraf_listesini_tekillestir([
        {"name": "AYTUN ÇANGA DR", "party_type": "THIRD", "role": "Sigortalı", "tc_no": "12345678901"},
        {"name": "Aytun Çanga Dr", "party_type": "CLIENT", "role": "Davalı", "hizmet_turleri": ["Takip"]},
        {"name": "Efsane Ballı; Mert Cengiz", "party_type": "COUNTER", "role": "Davacı", "tc_no": "1"},
        {"name": "Mert Cengiz", "party_type": "THIRD", "role": "Diğer"},
    ])
    assert [(p["name"], p["party_type"], p["role"]) for p in sonuc] == [
        ("Aytun Çanga Dr", "CLIENT", "Davalı"),          # müvekkil kazanır, 3. şahıs satırı düşer
        ("Efsane Ballı", "COUNTER", "Davacı"),
        ("Mert Cengiz", "COUNTER", "Davacı"),            # karşı taraf > 3. şahıs
    ]
    assert sonuc[0]["tc_no"] == "12345678901" and sonuc[0]["hizmet_turleri"] == ["Takip"]
    assert sonuc[1]["tc_no"] is None                     # bölünen öğenin TC'si kime ait bilinmez


# ═══════════════════════════════════════════════════════════════════════════
# 2. Temizlik script'i — scripts/taraf_tekillestir.py
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def ekran_karti(fabrika):
    """03.10 ekran görüntüsündeki kart (case 14579): üç kartın birleşimi."""
    db = fabrika()
    try:
        kart, t = _kart(db, "NIPPON-0187-DR.A.CANGA-HUK", [
            ("Efsane Ballı; Funda Süreyya Cengiz; Mert Cengiz", "COUNTER", "Davacı"),
            ("Aytun Çanga Dr", "CLIENT", "Davalı"),
            ("Efsane Ballı", "COUNTER", "Karşı Taraf"),
            ("Funda Süreyya Cengiz", "COUNTER", "Karşı Taraf"),
            ("Mert Cengiz", "COUNTER", "Karşı Taraf"),
            ("Türk Nippon Sigorta Aş", "CLIENT", "Davalı"),
            ("AYTUN ÇANGA DR", "THIRD", "Sigortalı"),
        ])
        hekim, sigortali = t["Aytun Çanga Dr"], t["AYTUN ÇANGA DR"]
        sigortali.tc_no = "12345678901"
        foy = models.CaseFoy(sistem_no="H-16890", case_id=kart.id, case_party_id=hekim.id)
        sigorta_foy = models.CaseFoy(sistem_no="H-16894", case_id=kart.id,
                                     case_party_id=t["Türk Nippon Sigorta Aş"].id,
                                     ham_veri={"Sigortalı": "Aytun Çanga Dr"})
        db.add_all([foy, sigorta_foy])
        kart.documents.append(models.CaseDocument(
            original_filename="d.pdf", stored_filename="d.pdf", belge_turu_kodu="DILEKCE_______",
            case_party_id=hekim.id))
        db.commit()
        return fabrika, kart.id, hekim.id
    finally:
        db.close()


def test_kuru_kosu_raporlar_ama_yazmaz(ekran_karti, tmp_path):
    fabrika, kart_id, _ = ekran_karti
    once = _taraflar(fabrika, kart_id)

    sonuc = tt.kos(fabrika, cikti_dizini=tmp_path)

    assert not sonuc.yazildi and sonuc.degisen_kart == 1
    assert sorted((i.kural, i.islem) for i in sonuc.islemler) == [
        ("ayni_kisi:CLIENT+THIRD", "SIL"), ("cok_adli", "SIL")]
    assert _taraflar(fabrika, kart_id) == once
    assert (tmp_path / "taraf_tekillestir_islemler.csv").exists()
    assert (tmp_path / "taraf_inceleme.csv").exists()


def test_apply_ekran_kartini_temizler_baglar_durur_ikinci_kosu_bos(ekran_karti):
    fabrika, kart_id, hekim_id = ekran_karti

    sonuc = tt.kos(fabrika, apply=True, kim="test")

    assert sonuc.yazildi and sonuc.envanter_farki == {} and sonuc.atlanan_kart == 0
    assert _taraflar(fabrika, kart_id) == [
        ("Aytun Çanga Dr", "CLIENT", "Davalı"),              # ad ve rol değişmedi
        ("Efsane Ballı", "COUNTER", "Karşı Taraf"),
        ("Funda Süreyya Cengiz", "COUNTER", "Karşı Taraf"),
        ("Mert Cengiz", "COUNTER", "Karşı Taraf"),
        ("Türk Nippon Sigorta Aş", "CLIENT", "Davalı"),
    ]
    db = fabrika()
    try:
        hekim = db.get(models.CaseParty, hekim_id)
        assert hekim.tc_no == "12345678901"                  # boş kimlik alanı gidenden doldu
        assert db.query(models.CaseDocument).one().case_party_id == hekim_id
        assert db.query(models.CaseFoy).filter_by(sistem_no="H-16890").one().case_party_id == hekim_id
        tarihce = db.query(models.CaseHistory).filter_by(case_id=kart_id, source=tt.SOURCE).all()
        assert len(tarihce) == 2 and {h.changed_by for h in tarihce} == {"test"}
    finally:
        db.close()

    ikinci = tt.kos(fabrika, apply=True, kim="test")
    assert ikinci.islemler == [] and ikinci.degisen_kart == 0


def test_karsi_taraf_ucuncu_sahistan_once_gelir_ve_eksik_parca_eklenir(fabrika):
    db = fabrika()
    try:
        kart, _ = _kart(db, "K.1", [
            ("Suat Hayri Küçük", "CLIENT", "Müvekkil"),
            ("Bağcılar Eğitim ve Araştırma Hastanesi", "COUNTER", "Karşı Taraf"),
            ("Bağcilar Eğitim Araştirma Hastanesi", "THIRD", "Diğer Davalı"),     # "ve" + ı/i farkı
            ("Suat Hayri Küçük Dr", "COUNTER", "Karşı Taraf"),                    # müvekkil ayrıca karşı taraf
            ("Kadri Demirtuyi; Suna Demirtuyi", "COUNTER", "Davacı"),
            ("Kadri Demirtuyi", "COUNTER", "Karşı Taraf"),
        ])
        db.commit()
        kart_id = kart.id
    finally:
        db.close()

    sonuc = tt.kos(fabrika, apply=True, kim="test")

    assert _taraflar(fabrika, kart_id) == [
        ("Bağcılar Eğitim ve Araştırma Hastanesi", "COUNTER", "Karşı Taraf"),
        ("Kadri Demirtuyi", "COUNTER", "Karşı Taraf"),
        ("Suat Hayri Küçük", "CLIENT", "Müvekkil"),
        ("Suna Demirtuyi", "COUNTER", "Davacı"),             # eksik parça birleşik satırın rolüyle eklendi
    ]
    assert ("cok_adli", "EKLE") in {(i.kural, i.islem) for i in sonuc.islemler}


def test_virgullu_foy_muvekkili_bagiyla_tek_satira_iner(fabrika):
    """Vekalet ücreti föyü: "Atilla Kurtay Dr.," (Alacaklı, föy+hizmet bağlı) + "Atilla Kurtay"."""
    db = fabrika()
    try:
        kart, t = _kart(db, "V.1", [
            ("Atilla Kurtay", "CLIENT", "Müvekkil"),
            ("Atilla Kurtay Dr.,", "CLIENT", "Alacaklı"),
        ])
        bagli = t["Atilla Kurtay Dr.,"]
        foy = models.CaseFoy(sistem_no="i-14910", case_id=kart.id, case_party_id=bagli.id)
        db.add(foy)
        db.flush()
        db.add(models.CaseHizmeti(case_id=kart.id, case_party_id=bagli.id,
                                  hizmet_turu="Vekalet Ücreti Alacağı", foy_id=foy.id))
        db.commit()
        kart_id, bagli_id = kart.id, bagli.id
    finally:
        db.close()

    sonuc = tt.kos(fabrika, apply=True, kim="test")

    assert [(i.kural, i.islem) for i in sonuc.islemler] == [
        ("ad_temizligi", "AD"), ("ayni_kisi:CLIENT+CLIENT", "SIL")]
    assert _taraflar(fabrika, kart_id) == [("Atilla Kurtay Dr.", "CLIENT", "Alacaklı")]   # bağı olan kaldı
    db = fabrika()
    try:
        assert db.query(models.CaseFoy).one().case_party_id == bagli_id
        assert db.query(models.CaseHizmeti).one().case_party_id == bagli_id
    finally:
        db.close()


def test_ofis_no_girdisi_degisecekse_kart_atlanir(fabrika):
    """Föysüz sigortacı kartında sigortalı "Diğer Davalı" hekim satırından okunur (ofis_no
    kaynak 4). O satır karşı tarafla aynı kişi diye silinirse blok kaybolurdu → kart atlanır."""
    db = fabrika()
    try:
        kart, _ = _kart(db, "S.1", [
            ("Axa Sigorta A.Ş.", "CLIENT", "Müvekkil"),
            ("Ali Veli", "COUNTER", "Karşı Taraf"),
            ("Ali Veli Dr.", "THIRD", "Diğer Davalı"),
        ])
        db.commit()
        kart_id = kart.id
    finally:
        db.close()
    once = _taraflar(fabrika, kart_id)

    sonuc = tt.kos(fabrika, apply=True, kim="test")

    assert sonuc.atlanan_kart == 1 and sonuc.islemler == []
    assert [n.sebep for n in sonuc.incelemeler] == ["ofis_no_degisir"]
    assert _taraflar(fabrika, kart_id) == once


def test_yazim_farki_otomatik_birlesmez_inceleme_listesine_duser(fabrika):
    db = fabrika()
    try:
        kart, _ = _kart(db, "B.1", [
            ("Deniz Çakır", "CLIENT", "Müvekkil"),
            ("Sebiha Sezer", "COUNTER", "Karşı Taraf"),
            ("Sebiha Ezer", "COUNTER", "Karşı Taraf"),
            ("Sağlık Bakanlığı", "THIRD", "Diğer Davalı"),
            ("TC Sağlık Bakanlığı Ankara İl Müdürlüğü", "COUNTER", "Karşı Taraf"),
        ])
        db.commit()
        kart_id = kart.id
    finally:
        db.close()
    once = _taraflar(fabrika, kart_id)

    sonuc = tt.kos(fabrika, apply=True, kim="test")

    assert sonuc.islemler == [] and _taraflar(fabrika, kart_id) == once
    assert sorted(n.sebep for n in sonuc.incelemeler) == ["alt_kume", "benzer_yazim"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. Kalıcı düzeltmeler
# ═══════════════════════════════════════════════════════════════════════════

def test_kart_birlestirme_ayni_kisiyi_turler_arasi_tek_satirda_tutar(fabrika):
    """TKU birleştirmesi: sigorta föyünün kartında hekim "Sigortalı" (3. şahıs), hekim
    föyünün kartında müvekkil → birleşen kartta TEK satır ve müvekkil olarak kalır."""
    db = fabrika()
    try:
        kalan, kt = _kart(db, "KALAN.1", [
            ("Türk Nippon Sigorta Aş", "CLIENT", "Davalı"),
            ("AYTUN ÇANGA DR", "THIRD", "Sigortalı"),
            ("Efsane Ballı", "COUNTER", "Karşı Taraf"),
        ])
        muk, mt = _kart(db, "MUK.1", [
            ("Aytun Çanga Dr", "CLIENT", "Davalı"),
            ("Efsane Ballı", "THIRD", "Diğer Davalı"),
        ])
        hekim = mt["Aytun Çanga Dr"]
        muk.documents.append(models.CaseDocument(
            original_filename="d.pdf", stored_filename="d.pdf", belge_turu_kodu="DILEKCE_______",
            case_party_id=hekim.id))
        db.add(models.CaseFoy(sistem_no="H-16890", case_id=muk.id, case_party_id=hekim.id))
        db.commit()
        kalan_id, muk_id, sigortali_id = kalan.id, muk.id, kt["AYTUN ÇANGA DR"].id
    finally:
        db.close()

    db = fabrika()
    try:
        sonuc = mb.birlestir(db, db.get(models.Case, kalan_id), db.get(models.Case, muk_id),
                             kim="test", muvekkil_ayrimi=True)       # tku_kart_birlestir çağrısı
        db.commit()
    finally:
        db.close()

    assert sonuc.ret is None
    assert sonuc.tasinan["taraf_tekil"] == 2 and sonuc.tasinan["taraf_yukseltilen"] == 1
    assert _taraflar(fabrika, kalan_id) == [
        ("Aytun Çanga Dr", "CLIENT", "Davalı"),              # 3. şahıs satırı yerinde yükseldi
        ("Efsane Ballı", "COUNTER", "Karşı Taraf"),          # gelen 3. şahıs satırı düştü
        ("Türk Nippon Sigorta Aş", "CLIENT", "Davalı"),
    ]
    db = fabrika()
    try:
        assert db.query(models.CaseDocument).one().case_party_id == sigortali_id   # bağ kopmadı
        assert db.query(models.CaseFoy).one().case_party_id == sigortali_id
    finally:
        db.close()


def test_belge_isleme_birlesik_karsi_tarafi_kisi_basina_yazar(fabrika, monkeypatch):
    from routes import processing

    db = fabrika()
    try:
        kart, _ = _kart(db, "P.1", [("Mert Cengiz", "CLIENT", "Müvekkil")])
        db.commit()
        kart_id = kart.id
    finally:
        db.close()
    monkeypatch.setattr(processing, "SessionLocal", fabrika)

    sonuc = processing._auto_enrich_case_data(kart_id, "Efsane Ballı; Funda Süreyya Cengiz; MERT CENGİZ", "t")

    assert sonuc == {"counter_party": "Efsane Ballı; Funda Süreyya Cengiz"}     # müvekkil yeniden yazılmaz
    assert _taraflar(fabrika, kart_id) == [
        ("Efsane Ballı", "COUNTER", "Karşı Taraf"),
        ("Funda Süreyya Cengiz", "COUNTER", "Karşı Taraf"),
        ("Mert Cengiz", "CLIENT", "Müvekkil"),
    ]


def test_kart_acma_gelen_taraflari_tekillestirir(fabrika, monkeypatch):
    monkeypatch.setattr(case_manager, "SessionLocal", fabrika)

    case_manager.add_case({
        "tracking_no": "ELLE.1", "status": "DERDEST",
        "parties": [
            {"name": "Deniz Çakır", "party_type": "CLIENT", "role": "Davacı"},
            {"name": "Ali Veli; Ayşe Veli", "party_type": "COUNTER", "role": "Davalı"},
            {"name": "DENİZ ÇAKIR", "party_type": "THIRD", "role": "Diğer"},
        ],
    })

    db = fabrika()
    try:
        kart_id = db.query(models.Case).filter_by(tracking_no="ELLE.1").one().id
    finally:
        db.close()
    assert _taraflar(fabrika, kart_id) == [
        ("Ali Veli", "COUNTER", "Davalı"),
        ("Ayşe Veli", "COUNTER", "Davalı"),
        ("Deniz Çakır", "CLIENT", "Davacı"),
    ]
