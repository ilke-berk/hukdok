"""Raporlama doğruluk düzeltmeleri (2026-09-12, kullanıcı kararı "deploy sonrası 4. madde"):

1. Saat dilimi — `timestamptz` kolonlarda gün sınırı Türkiye günüdür: filtre bind'ı `+03:00`
   taşır (`registry.tarih_kosulu`), motor UTC değeri Türkiye saatine çevirip serileştirir
   (22:15 UTC → ertesi gün 01:15), Excel tz'siz Türkiye saati yazar (openpyxl tz'li datetime'ı
   reddediyordu — lokal Postgres'te `uploaded_at` kolonlu export 500 veriyordu).
2. CSV ondalık virgül — `para` iki basamak "1234,50", ondalıklı `sayi` virgüllü, tam sayı aynen.
3. Türkçe sıralama — öneri/seçenek listeleri Türk alfabesi sırasıyla (`tr_sira_anahtari`),
   büyük/küçük harf duyarsız; DB collation'ına bağımlılık yok (sqlite = Postgres).

Frontend eşi: `PreviewTable` başlığındaki ikinci "N kayıt" rozeti kaldırıldı (`PreviewTable.test.tsx`).
"""
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from schemas_rapor import SAAT_DILIMI, KolonBasligi
from services.rapor import cikti, motor, registry

TR = dt.timezone(dt.timedelta(hours=3))


# ─── 1. Saat dilimi ──────────────────────────────────────────────────────────

def _derle(kosul) -> str:
    return str(kosul.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_tarih_kosulu_zaman_damgali_bindlar_turkiye_saat_dilimli():
    """Kabul: DateTime kolonda eq/gte/lte/between bind'ları `+03:00` ofsetli — Postgres oturumu UTC olsa da
    gün 03:00 UTC'de değil TR gece yarısında başlar. Date kolonda (opening_date) bind düz tarih kalır."""
    sql = _derle(registry.tarih_kosulu(models.CaseDocument.uploaded_at, True, "eq", dt.date(2026, 5, 2)))
    assert "'2026-05-02 00:00:00+03:00'" in sql and "'2026-05-03 00:00:00+03:00'" in sql
    sql = _derle(registry.tarih_kosulu(models.CaseDocument.uploaded_at, True, "between",
                                       (dt.date(2026, 5, 1), dt.date(2026, 5, 31))))
    assert "'2026-05-01 00:00:00+03:00'" in sql and "'2026-06-01 00:00:00+03:00'" in sql
    assert registry._gun_basi(dt.date(2026, 1, 15)).tzinfo is SAAT_DILIMI
    sql = _derle(registry.tarih_kosulu(models.Case.opening_date, False, "eq", dt.date(2026, 5, 2)))
    assert "'2026-05-02'" in sql and "+03:00" not in sql


def test_serilestir_utc_zaman_turkiye_saatine_cevrilir():
    """Kabul: UTC 22:15 → `2026-05-03T01:15:28+03:00` (gün kayar); naive (sqlite) ve `date` olduğu gibi."""
    utc = dt.datetime(2026, 5, 2, 22, 15, 28, tzinfo=dt.timezone.utc)
    assert motor._serilestir(utc) == "2026-05-03T01:15:28+03:00"
    assert motor._serilestir(dt.datetime(2026, 5, 2, 22, 15, 28)) == "2026-05-02T22:15:28"
    assert motor._serilestir(dt.date(2026, 5, 2)) == "2026-05-02"


def test_xlsx_saat_dilimli_zaman_turkiye_saati_tzsiz(tmp_path):
    """Kabul: motorun `+03:00`'lü ISO'su (ve UTC'li ISO) Excel'de tz'siz Türkiye saati hücresi olur — openpyxl
    'Excel does not support timezones' fırlatmaz; CSV aynı satırı `03.05.2026 01:15:28` yazar."""
    from openpyxl import load_workbook

    kolonlar = [KolonBasligi(anahtar="t", etiket="Yükleme", tip="tarih")]
    satirlar = [{"t": "2026-05-03T01:15:28+03:00"}, {"t": "2026-05-02T22:15:28+00:00"}, {"t": "2026-05-02"}]
    cikti.ciktiyi_yaz("xlsx", kolonlar, iter(satirlar), tmp_path / "r.xlsx")
    ws = load_workbook(tmp_path / "r.xlsx").active
    assert ws["A2"].value == dt.datetime(2026, 5, 3, 1, 15, 28) and ws["A2"].value.tzinfo is None
    assert ws["A3"].value == dt.datetime(2026, 5, 3, 1, 15, 28)
    assert ws["A4"].value == dt.datetime(2026, 5, 2, 0, 0) or ws["A4"].value == dt.date(2026, 5, 2)
    cikti.ciktiyi_yaz("csv", kolonlar, iter(satirlar[:2]), tmp_path / "r.csv")
    metin = (tmp_path / "r.csv").read_bytes().decode("utf-8-sig")
    assert metin == "Yükleme\r\n03.05.2026 01:15:28\r\n03.05.2026 01:15:28\r\n"


# ─── 2. CSV ondalık virgül ───────────────────────────────────────────────────

@pytest.mark.parametrize("deger,tip,beklenen", [
    (1234.5, "para", "1234,50"),
    (-250.0, "para", "-250,00"),
    (1, "para", "1,00"),
    (2.5, "sayi", "2,5"),
    (7, "sayi", 7),
    (True, "sayi", True),           # bool sayı değildir
    ("metin", "para", "metin"),
])
def test_csv_sayi_hucresi_ondalik_virgul(deger, tip, beklenen):
    assert cikti._sayi_metni(deger, tip) == beklenen


def test_csv_satirinda_para_ve_sayi_virgullu_tarih_metin_dokunulmaz():
    kolonlar = [KolonBasligi(anahtar="p", etiket="Tutar", tip="para"),
                KolonBasligi(anahtar="n", etiket="Sayı", tip="sayi"),
                KolonBasligi(anahtar="a", etiket="Ad", tip="metin")]
    assert cikti._csv_degerleri(kolonlar, {"p": 10, "n": 3.25, "a": "x.y"}) == ["10,00", "3,25", "x.y"]
    assert cikti._csv_degerleri(kolonlar, {"p": None, "n": 4, "a": None}) == ["", 4, ""]


# ─── 3. Türkçe sıralama ──────────────────────────────────────────────────────

def test_tr_sira_anahtari_turk_alfabesi_ve_harf_duyarsiz():
    """Kabul: ç/ğ/ı/i/ö/ş/ü alfabe yerinde; İ→i, I→ı; boşluk/rakam harflerden önce; şapkalı taban ardında."""
    adlar = ["Şirket", "Sağlık", "İzmir", "Isparta", "Çankaya", "Ankara", "ankara", "Ömer", "Zeynep",
             "Birim 10", "Birim 2", "Cem", "Âdem", "Adana", "Üsküdar", "Uşak", "Giresun", "Ğ-test"]
    sirali = sorted(adlar, key=registry.tr_sira_anahtari)
    assert sirali == ["Adana", "Âdem", "Ankara", "ankara", "Birim 10", "Birim 2", "Cem", "Çankaya", "Giresun",
                      "Ğ-test", "Isparta", "İzmir", "Ömer", "Sağlık", "Şirket", "Uşak", "Üsküdar", "Zeynep"]


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    oturum = maker()
    try:
        yield oturum
    finally:
        oturum.close()
        engine.dispose()


def test_oneriler_ve_veriden_secenekler_turkce_sirali(db, monkeypatch):
    """Kabul: taraf adı önerileri ve veriden liste (eşit sıklıkta) Türk alfabesiyle döner — DB'nin
    C sırası ("Ankara" < "Zeynep" < "Çankaya" < "İzmir" < "Şirket") değil."""
    from config.settings import settings

    monkeypatch.setattr(settings, "rapor_secenek_esigi", 50)
    davalar = []
    for i, (taraf, il) in enumerate([("Şirket A", "Şanlıurfa"), ("Çankaya Hastanesi", "Çorum"),
                                      ("İzmir Kliniği", "İzmir"), ("Ankara Tıp", "Ankara"), ("zeynep", "Isparta")]):
        dava = models.Case(tracking_no=f"TR.{i}", tenant_id=None, status="DERDEST", subject="s", court=il)
        db.add(dava)
        db.flush()
        db.add(models.CaseParty(case_id=dava.id, name=taraf, role="Davacı", party_type="CLIENT"))
        davalar.append(dava)
    db.commit()
    kolon = registry.DAVALAR.kolonlar["muvekkil_adlari"]
    oneriler, kesik = registry.onerileri_getir(registry.DAVALAR, kolon, db, "t")
    assert oneriler == ["Ankara Tıp", "Çankaya Hastanesi", "İzmir Kliniği", "Şirket A", "zeynep"] and not kesik
    il_kolonu = registry.DAVALAR.kolonlar["court"]           # veriden liste (mahkeme adı yerine il adı yazıldı)
    assert il_kolonu.veriden_liste
    secenekler = registry.veriden_secenekleri_getir(registry.DAVALAR, il_kolonu, db, "t")
    assert secenekler == ["Ankara", "Çorum", "Isparta", "İzmir", "Şanlıurfa"]
    sayili = registry.veriden_secenekleri_getir(registry.DAVALAR, il_kolonu, db, "t", sayili=True)
    assert [d for d, _n in sayili] == secenekler and all(n == 1 for _d, n in sayili)


def test_secenekleri_getir_distinct_katmani_turkce_sirali(db):
    """Kabul: `liste` kolonun çekirdek + referans sırası korunur; kolondaki DISTINCT ek değerler Türk
    alfabesiyle sona eklenir."""
    kolon = registry.DAVALAR.kolonlar["status"]
    for i, durum in enumerate(["Şüpheli", "Çekildi", "Ara"]):
        db.add(models.Case(tracking_no=f"SG.{i}", tenant_id=None, status=durum, subject="s"))
    db.commit()
    secenekler = registry.secenekleri_getir(kolon, db)
    cekirdek = list(kolon.secenekler)
    assert secenekler[:len(cekirdek)] == cekirdek
    ek = [s for s in secenekler if s not in cekirdek]
    assert ek == ["Ara", "Çekildi", "Şüpheli"]
