"""Otomatik dava ilişkisi tespiti — `services/case_relations_auto.py`.

`GET /api/cases/{id}/relations` yıllardır `automatic=[]` döndürüyordu: şema slotu
vardı, üreticisi yoktu. Bu dosya iki dedektörü ve sınıflandırıcıyı kilitler.

Senaryolar canlı veriden alındı (2026-08-20 ölçümü, `docs/arsiv/aktarim-performans-
raporu-2026-08-20.md`), böylece test "uydurma bir dünya" değil ölçülmüş desenleri
korur:

* **TKU-1230** — üç kart, üçü de İstanbul 8. İdare 2020/2029, ofis no isim blokları
  farklı (B_GURER / E_CELIKOGL / J_HAZNECI): aynı dava, farklı müvekkiller.
* **TKU-402**  — Şanlıurfa 1. Tüketici 2017/162 ile 2024/216: aynı tür, farklı
  esas/mahkeme — dava yıllar sonra yeniden açılmış.
* **TKU-4724** — ARB-15021 (Arabuluculuk) → H-15030 (İzmir 2. Tüketici 2023/416).

Gerçek DB'ye bağlanan test YOK: in-memory sqlite + StaticPool (G060/G065 deseni).
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from services import case_relations_auto as ilis
from services.case_relations_auto import KartOzeti, esas_anahtari, siniflandir


def _ozet(kimlik: int, tur: str, mahkeme: str = "", esas: str = "") -> KartOzeti:
    return KartOzeti(id=kimlik, file_type=tur, court=mahkeme, esas_no=esas)


# ═══════════════════════════════════════════════════════════════════════════
# 1. DB'siz — saf sınıflandırıcı
# ═══════════════════════════════════════════════════════════════════════════

def test_ayni_tur_ayni_mahkeme_ayni_esas_ayni_davadir():
    """TKU-1230 deseni: üç ayrı kart ama tek dava (farklı müvekkiller)."""
    a = _ozet(1, "İdare", "İstanbul 8. İdare Mahkemesi", "2020/2029")
    b = _ozet(2, "İdare", "İstanbul 8. İdare Mahkemesi", "2020/2029")
    assert siniflandir(a, b) == ilis.AYNI_DAVA


def test_ayni_tur_farkli_esas_yeniden_acilandir():
    """TKU-402 deseni: 2017/162 → 2024/216, aynı tür, dava yeniden açılmış."""
    a = _ozet(1, "Hukuk", "Şanlıurfa 1. Tüketici Mahkemesi", "2017/162")
    b = _ozet(2, "Hukuk", "Şanlıurfa 1. Tüketici Mahkemesi", "2024/216")
    assert siniflandir(a, b) == ilis.YENIDEN_ACILAN


def test_ayni_tur_ayni_esas_farkli_mahkeme_ayni_dava_degildir():
    """Esas numaraları mahkemeler arasında serbestçe tekrar eder — mahkeme
    eşitliği olmadan 'aynı dava' demek rastlantıyı gerçek sanmaktır."""
    a = _ozet(1, "Hukuk", "Ankara 3. Tüketici Mahkemesi", "2020/100")
    b = _ozet(2, "Hukuk", "İzmir 1. Tüketici Mahkemesi", "2020/100")
    assert siniflandir(a, b) == ilis.YENIDEN_ACILAN


def test_bos_esas_ayni_dava_uretmez():
    """İki kartın da esası boşsa bu bir ikizlik KANITI değildir."""
    a = _ozet(1, "Hukuk", "Ankara 3. Tüketici Mahkemesi", "")
    b = _ozet(2, "Hukuk", "Ankara 3. Tüketici Mahkemesi", None)
    assert siniflandir(a, b) == ilis.YENIDEN_ACILAN


def test_esas_yazim_farki_ayni_davayi_bozmaz():
    a = _ozet(1, "İdare", "İstanbul 8. İdare Mahkemesi", " 2020 / 2029 ")
    b = _ozet(2, "İdare", "İstanbul 8. İdare Mahkemesi", "2020/2029")
    assert siniflandir(a, b) == ilis.AYNI_DAVA


def test_mahkeme_yazim_farki_ayni_davayi_bozmaz():
    """normalize_court aksan/büyük-küçük farkını yutar (G067 sözleşmesi)."""
    a = _ozet(1, "İdare", "İSTANBUL 8. IDARE MAHKEMESI", "2020/2029")
    b = _ozet(2, "İdare", "İstanbul 8. İdare Mahkemesi", "2020/2029")
    assert siniflandir(a, b) == ilis.AYNI_DAVA


@pytest.mark.parametrize("diger_tur,beklenen", [
    ("Arabuluculuk", ilis.ARABULUCULUK_ONCULU),
    ("İcra", ilis.ICRA_PARALEL),
    ("Ceza", ilis.CEZA_PARALEL),
    ("Savcılık", ilis.SAVCILIK_PARALEL),
    ("İdare", ilis.ADLI_IDARI_PARALEL),
])
def test_tur_farki_paralel_iliskilere_bolunur(diger_tur, beklenen):
    """TKU-4724 (Arabuluculuk→Hukuk) dahil, ölçülen dört karışık tür deseni."""
    a = _ozet(1, "Hukuk", "İzmir 2. Tüketici Mahkemesi", "2023/416")
    b = _ozet(2, diger_tur, "", "2023/33233")
    assert siniflandir(a, b) == beklenen


def test_arabuluculuk_icradan_once_gelir():
    """Sıra sözleşmesi: bir grup hem arabuluculuk hem icra taşıyorsa anlatılacak
    öncelikli hikâye arabuluculuk zinciridir."""
    a = _ozet(1, "Arabuluculuk", "", "2023/33233")
    b = _ozet(2, "İcra", "İzmir 5. İcra Dairesi", "2023/900")
    assert siniflandir(a, b) == ilis.ARABULUCULUK_ONCULU


def test_taninmayan_tur_ikilisi_ilgiliye_duser():
    a = _ozet(1, "Danışmanlık", "", "")
    b = _ozet(2, "Ticaret", "İstanbul 1. Asliye Ticaret Mahkemesi", "2024/5")
    assert siniflandir(a, b) == ilis.ILGILI


def test_ayni_dava_en_yuksek_guven_puanini_alir():
    """Panel sıralaması buna dayanır: 'bu aslında tek dava' uyarısı hep en üstte."""
    assert ilis.GUVEN_PUANI[ilis.AYNI_DAVA] == max(ilis.GUVEN_PUANI.values())


def test_esas_anahtari_bosu_bos_dondurur():
    assert esas_anahtari(None) == ""
    assert esas_anahtari("   ") == ""
    assert esas_anahtari("2020 / 1777") == "2020/1777"


@pytest.mark.parametrize("yer_tutucu", ["2021/", "2014/???", "2023", "/4954", "9.1801"])
def test_numarasiz_esas_kimlik_sayilmaz(yer_tutucu):
    """Canlı veride 397 kart 'YYYY/', 208 kart '2014/???' taşıyor. Bunlar kimlik
    sayılsaydı aynı mahkemedeki tüm '2019/' kartları birbirinin ikizi olurdu."""
    assert esas_anahtari(yer_tutucu) == ""


def test_yer_tutucu_esas_ayni_dava_uretmez():
    """Aynı mahkeme + aynı tür + iki tarafta da '2019/' → AYNI_DAVA DEĞİL."""
    a = _ozet(1, "İdare", "Ankara 17. İdare Mahkemesi", "2019/")
    b = _ozet(2, "İdare", "Ankara 17. İdare Mahkemesi", "2019/")
    assert siniflandir(a, b) == ilis.YENIDEN_ACILAN


# ═══════════════════════════════════════════════════════════════════════════
# 2. sqlite — iki dedektör uçtan uca
# ═══════════════════════════════════════════════════════════════════════════

TENANT = "tenant-hanyaloglu"


@pytest.fixture
def oturum():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine)
    db = Fabrika()
    yield db
    db.close()
    engine.dispose()


def _kart(db, tracking_no, **alanlar):
    case = models.Case(tracking_no=tracking_no, status="DERDEST", **alanlar)
    db.add(case)
    db.commit()
    return case


def _foy(db, sistem_no, case_id, tku_no=None):
    db.add(models.CaseFoy(sistem_no=sistem_no, case_id=case_id, tku_no=tku_no))
    db.commit()


def _tku_1230(db):
    """Üç kart, tek dava, üç müvekkil — canlı TKU-1230 grubunun birebir kopyası."""
    kartlar = []
    for tracking_no, sistem_no in (
        ("D1.B_GURER....0001.IDARE.00000", "id-7173"),
        ("D1.E_CELIKOGL.0001.IDARE.00000", "id-7174"),
        ("D1.J_HAZNECI..0001.IDARE.00000", "id-7175"),
    ):
        kart = _kart(db, tracking_no, file_type="İdare",
                     court="İstanbul 8. İdare Mahkemesi", esas_no="2020/2029")
        _foy(db, sistem_no, kart.id, "TKU-1230")
        kartlar.append(kart)
    return kartlar


def test_tku_dedektoru_kardes_kartlari_buluyor(oturum):
    a, b, c = _tku_1230(oturum)
    sonuc = ilis.iliskileri_bul(oturum, a, TENANT)
    assert {kart.id for kart, *_ in sonuc} == {b.id, c.id}
    assert {tur for _, tur, _, _ in sonuc} == {ilis.AYNI_DAVA}


def test_gerekce_hem_tku_hem_esas_kanitini_yaziyor(oturum):
    a, _, _ = _tku_1230(oturum)
    _, _, gerekce, _ = ilis.iliskileri_bul(oturum, a, TENANT)[0]
    assert "TKU-1230" in gerekce
    assert "2020/2029" in gerekce


def test_kart_kendisini_iliskilendirmiyor(oturum):
    a, _, _ = _tku_1230(oturum)
    assert a.id not in {kart.id for kart, *_ in ilis.iliskileri_bul(oturum, a, TENANT)}


def test_esas_dedektoru_tkusuz_ikizi_buluyor(oturum):
    """TKU'nun kör noktası: ölçümde 199 esas-ikizi grubunun 24'ünde hiçbir kartın
    TKU'su yok. İkinci dedektör olmasa bu kartlar hiç bağlanmazdı."""
    a = _kart(oturum, "D1.A....0001.HUKUK.00000", file_type="Hukuk",
              court="Ankara 3. Tüketici Mahkemesi", esas_no="2021/55")
    b = _kart(oturum, "D1.B....0001.HUKUK.00000", file_type="Hukuk",
              court="Ankara 3. Tüketici Mahkemesi", esas_no="2021/55")
    sonuc = ilis.iliskileri_bul(oturum, a, TENANT)
    assert [(kart.id, tur) for kart, tur, _, _ in sonuc] == [(b.id, ilis.AYNI_DAVA)]


def test_esas_dedektoru_farkli_mahkemeyi_baglamiyor(oturum):
    a = _kart(oturum, "D1.A....0001.HUKUK.00000", file_type="Hukuk",
              court="Ankara 3. Tüketici Mahkemesi", esas_no="2021/55")
    _kart(oturum, "D1.B....0001.HUKUK.00000", file_type="Hukuk",
          court="İzmir 1. Tüketici Mahkemesi", esas_no="2021/55")
    assert ilis.iliskileri_bul(oturum, a, TENANT) == []


def test_esas_dedektoru_farkli_turu_baglamiyor(oturum):
    a = _kart(oturum, "D1.A....0001.HUKUK.00000", file_type="Hukuk",
              court="Ankara 3. Tüketici Mahkemesi", esas_no="2021/55")
    _kart(oturum, "D1.B....0001.ICRA.00000", file_type="İcra",
          court="Ankara 3. Tüketici Mahkemesi", esas_no="2021/55")
    assert ilis.iliskileri_bul(oturum, a, TENANT) == []


@pytest.mark.parametrize("esas", ["", "2019/"])
def test_kimliksiz_esasli_kartlar_birbirine_baglanmiyor(oturum, esas):
    """Boş ya da yer tutucu esas SQL'de eşleşseydi bütün numarasız kartlar tek
    yumak olurdu (canlı veride 397 kart 'YYYY/' taşıyor)."""
    a = _kart(oturum, "D1.A....0001.HUKUK.00000", file_type="Hukuk",
              court="Ankara 3. Tüketici Mahkemesi", esas_no=esas)
    _kart(oturum, "D1.B....0001.HUKUK.00000", file_type="Hukuk",
          court="Ankara 3. Tüketici Mahkemesi", esas_no=esas)
    assert ilis.iliskileri_bul(oturum, a, TENANT) == []


def test_arabuluculuk_zinciri_tku_ile_baglaniyor(oturum):
    """TKU-4724: arabuluculuğun esası ve mahkemesi davanınkiyle tutmaz —
    bu bağı KURAN tek şey TKU'dur."""
    arb = _kart(oturum, "D1.M....0001.ARB.00000", file_type="Arabuluculuk",
                court=None, esas_no="2023/33233")
    hukuk = _kart(oturum, "D1.M....0001.HUKUK.00000", file_type="Hukuk",
                  court="İzmir 2. Tüketici Mahkemesi", esas_no="2023/416")
    _foy(oturum, "ARB-15021", arb.id, "TKU-4724")
    _foy(oturum, "H-15030", hukuk.id, "TKU-4724")
    sonuc = ilis.iliskileri_bul(oturum, hukuk, TENANT)
    assert [(kart.id, tur) for kart, tur, _, _ in sonuc] == [
        (arb.id, ilis.ARABULUCULUK_ONCULU)
    ]


def test_legacy_kart_tku_kolonu_da_okunuyor(oturum):
    """`cases.tku_no` eski Full_Rapor_TKU aktarımının kolonu; aktarım buraya
    yazmaz ama prod'da dolu olabilir — föy satırı olmayan kart da bağlanmalı."""
    a = _kart(oturum, "D1.A....0001.HUKUK.00000", file_type="Hukuk",
              court="Ankara 3. Tüketici Mahkemesi", esas_no="2021/55", tku_no="TKU-9")
    b = _kart(oturum, "D1.B....0001.CEZA.00000", file_type="Ceza",
              court="Ankara 1. Asliye Ceza Mahkemesi", esas_no="2021/900",
              tku_no="TKU-9")
    sonuc = ilis.iliskileri_bul(oturum, a, TENANT)
    assert [(kart.id, tur) for kart, tur, _, _ in sonuc] == [(b.id, ilis.CEZA_PARALEL)]


def test_silinmis_kart_iliski_listesine_girmiyor(oturum):
    """Manuel katmanın kuralıyla aynı: soft-delete edilmiş dava listede görünmez."""
    a, b, c = _tku_1230(oturum)
    b.deleted_at = datetime(2026, 8, 20, 10, 0, 0)
    oturum.commit()
    assert {kart.id for kart, *_ in ilis.iliskileri_bul(oturum, a, TENANT)} == {c.id}


def test_baska_tenantin_karti_sizmiyor(oturum):
    """tenant_id NULL paylaşımlı havuzdur; DOLU ve farklı olan sızmamalı."""
    a, b, c = _tku_1230(oturum)
    b.tenant_id = "baska-tenant"
    c.tenant_id = TENANT
    oturum.commit()
    assert {kart.id for kart, *_ in ilis.iliskileri_bul(oturum, a, TENANT)} == {c.id}


def test_siralama_guven_puanina_gore(oturum):
    """AYNI_DAVA (95) paralel türlerin (80) üstünde durur."""
    a = _kart(oturum, "D1.A....0001.HUKUK.00000", file_type="Hukuk",
              court="Ankara 3. Tüketici Mahkemesi", esas_no="2021/55", tku_no="TKU-7")
    icra = _kart(oturum, "D1.B....0001.ICRA.00000", file_type="İcra",
                 court="Ankara 5. İcra Dairesi", esas_no="2021/700", tku_no="TKU-7")
    ikiz = _kart(oturum, "D1.C....0001.HUKUK.00000", file_type="Hukuk",
                 court="Ankara 3. Tüketici Mahkemesi", esas_no="2021/55",
                 tku_no="TKU-7")
    sonuc = ilis.iliskileri_bul(oturum, a, TENANT)
    assert [kart.id for kart, *_ in sonuc] == [ikiz.id, icra.id]
    assert [puan for *_, puan in sonuc] == [95, 80]


def test_iliskisiz_kart_bos_liste_donuyor(oturum):
    a = _kart(oturum, "D1.A....0001.HUKUK.00000", file_type="Hukuk",
              court="Ankara 3. Tüketici Mahkemesi", esas_no="2021/55")
    assert ilis.iliskileri_bul(oturum, a, TENANT) == []


def test_azami_iliski_siniri_uygulaniyor(oturum):
    """Emniyet supabı: patolojik bir grup paneli boğmasın."""
    a = _kart(oturum, "D1.A....0001.HUKUK.00000", file_type="Hukuk",
              court="Ankara 3. Tüketici Mahkemesi", esas_no="2021/55", tku_no="TKU-8")
    for sira in range(ilis.AZAMI_ILISKI + 5):
        _kart(oturum, f"D1.X{sira:02d}..0001.HUKUK.00000", file_type="Hukuk",
              court="Ankara 3. Tüketici Mahkemesi", esas_no="2021/55", tku_no="TKU-8")
    assert len(ilis.iliskileri_bul(oturum, a, TENANT)) == ilis.AZAMI_ILISKI
