"""Raporlama ÖZET MODU (2026-09-12, kullanıcı kararı "2. madde: gruplama ve özet satırları").

Sözleşme: `RaporTanimi.gruplama` (≤3, `{alan, kirilim?}`) + `olcumler` (≤5, `{islem, alan?}`); `olcumler`
doluysa özet modu — satırlar gruplama alanlarına göre `GROUP BY`, çıktı kolonları = gruplama alanları +
ölçümler (`olcum_anahtari`: `sayi`, `toplam:maddi_tazminat`), `kolonlar` kullanılmaz ama şemada kalır.
Tarih kolonunda kırılım gün/ay/yıl (Türkiye günü — `tr_gun`, Postgres `AT TIME ZONE`). Filtreler WHERE'de
(gruplamadan önce). Sıralama verilmezse ilk ölçüm azalan. K1 korunur: anahtarlar registry'den, Core select.

Düzen: G130 `env` reçetesi (sqlite StaticPool, gerçek `require_admin`).
"""
import csv
import datetime as dt
import io
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from prompts import get_rapor_asistani_instruction
from schemas_rapor import GRUPLAMA_MAX, OLCUM_MAX, AsistanTanimi, RaporDogrulamaHatasi, RaporTanimi, olcum_anahtari
from services.rapor import asistan, cikti, motor, registry

ADMIN = "yonetici@hanyaloglu-acar.av.tr"
T1 = "tenant-hanyaloglu"
T2 = "tenant-baska"
PREVIEW = "/api/reports/preview"
CATALOG = "/api/reports/catalog"


def _veri_yukle(db):
    db.add_all([
        models.Case(tracking_no="OZ.1", tenant_id=T1, status="DERDEST", subject="a", responsible_lawyer_name="Av. Ali",
                    opening_date=dt.date(2025, 3, 1), maddi_tazminat=Decimal("1000.50"),
                    created_at=dt.datetime(2026, 1, 5, 10, 0)),
        models.Case(tracking_no="OZ.2", tenant_id=None, status="KARAR", subject="b", responsible_lawyer_name="Av. Veli",
                    opening_date=dt.date(2024, 6, 15), maddi_tazminat=Decimal("250"),
                    created_at=dt.datetime(2026, 1, 6, 9, 0)),
        models.Case(tracking_no="OZ.3", tenant_id=None, status="DERDEST", subject="c", responsible_lawyer_name="Av. Ali",
                    opening_date=dt.date(2025, 3, 20), maddi_tazminat=Decimal("100"),
                    created_at=dt.datetime(2026, 1, 5, 23, 30)),
        models.Case(tracking_no="OZ.4", tenant_id=T2, status="DERDEST", subject="baska tenant",
                    responsible_lawyer_name="Av. Ali", opening_date=dt.date(2025, 3, 2)),
        models.Case(tracking_no="OZ.5", tenant_id=T1, status="DERDEST", subject="silinmis", responsible_lawyer_name="Av. Ali",
                    deleted_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)),
    ])
    db.commit()


@pytest.fixture()
def env(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import reports as route_mod

    monkeypatch.setenv("ADMIN_EMAILS", ADMIN)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(route_mod, "SessionLocal", maker)
    db = maker()
    try:
        _veri_yukle(db)
    finally:
        db.close()

    def _client(email=ADMIN, tid=T1):
        app = FastAPI()
        app.include_router(route_mod.router)
        app.dependency_overrides[get_current_user] = lambda: {"preferred_username": email, "tid": tid}
        return TestClient(app, raise_server_exceptions=False)

    yield SimpleNamespace(db=maker, client=_client)
    engine.dispose()


def _tanim(gruplama=(), olcumler=({"islem": "sayi"},), filtreler=(), siralama=(), kolonlar=("tracking_no",)):
    return {"veri_kaynagi": "davalar", "kolonlar": list(kolonlar), "filtreler": list(filtreler),
            "siralama": list(siralama), "gruplama": list(gruplama), "olcumler": list(olcumler)}


def _onizle(client, tanim, **ek):
    return client.post(PREVIEW, json={"tanim": tanim, "sayfa": 1, "sayfa_boyu": 50, **ek})


def _422(r, alan_parcasi: str, sebep_parcasi: str):
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert alan_parcasi in d["alan"] and sebep_parcasi in d["sebep"], d


# ─── Özet sorguları ──────────────────────────────────────────────────────────

def test_avukat_basina_dava_sayisi(env):
    """Kabul: gruplama avukat + sayı → avukat başına satır; varsayılan sıra sayı azalan, eşitlikte ad artan;
    tenant + soft-delete kısıtı gruplamadan önce (OZ.4 başka tenant, OZ.5 silinmiş sayılmaz); `toplam` grup sayısı."""
    r = _onizle(env.client(), _tanim(gruplama=[{"alan": "responsible_lawyer_name"}]))
    assert r.status_code == 200, r.text
    g = r.json()
    assert [k["anahtar"] for k in g["kolonlar"]] == ["responsible_lawyer_name", "sayi"]
    assert [(k["etiket"], k["tip"]) for k in g["kolonlar"]] == [("Sorumlu Avukat", "metin"), ("Kayıt sayısı", "sayi")]
    assert g["satirlar"] == [{"responsible_lawyer_name": "Av. Ali", "sayi": 2}, {"responsible_lawyer_name": "Av. Veli", "sayi": 1}]
    assert g["toplam"] == 2


def test_aylara_gore_acilis_ve_toplam_tazminat(env):
    """Kabul: tarih kolonunda ay kırılımı 'YYYY-AA' metni; toplam para; etiketler '(ay)' ve 'Toplam …'."""
    r = _onizle(env.client(), _tanim(gruplama=[{"alan": "opening_date", "kirilim": "ay"}],
                                     olcumler=[{"islem": "sayi"}, {"islem": "toplam", "alan": "maddi_tazminat"}]))
    assert r.status_code == 200, r.text
    g = r.json()
    assert [(k["anahtar"], k["etiket"], k["tip"]) for k in g["kolonlar"]] == [
        ("opening_date", "Açılış Tarihi (ay)", "metin"), ("sayi", "Kayıt sayısı", "sayi"),
        ("toplam:maddi_tazminat", "Toplam Maddi Tazminat", "para"),
    ]
    assert g["satirlar"] == [
        {"opening_date": "2025-03", "sayi": 2, "toplam:maddi_tazminat": 1100.5},
        {"opening_date": "2024-06", "sayi": 1, "toplam:maddi_tazminat": 250.0},
    ]


def test_yil_ve_gun_kirilimi(env):
    r = _onizle(env.client(), _tanim(gruplama=[{"alan": "opening_date", "kirilim": "yil"}],
                                     siralama=[{"alan": "opening_date", "yon": "asc"}]))
    assert [s["opening_date"] for s in r.json()["satirlar"]] == ["2024", "2025"]
    # Zaman damgalı kolonda gün kırılımı: `tr_gun` (sqlite `date()`), tip tarih, ISO gün
    r = _onizle(env.client(), _tanim(gruplama=[{"alan": "created_at", "kirilim": "gun"}],
                                     siralama=[{"alan": "created_at", "yon": "asc"}]))
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["kolonlar"][0]["tip"] == "tarih" and g["kolonlar"][0]["etiket"] == "Oluşturulma"
    assert g["satirlar"] == [{"created_at": "2026-01-05", "sayi": 2}, {"created_at": "2026-01-06", "sayi": 1}]


def test_gruplamasiz_tek_toplam_satiri(env):
    """Kabul: gruplama yok, ölçümler var → tek satır (sayı, ortalama, min/max tarih)."""
    r = _onizle(env.client(), _tanim(olcumler=[{"islem": "sayi"}, {"islem": "ortalama", "alan": "maddi_tazminat"},
                                               {"islem": "min", "alan": "opening_date"},
                                               {"islem": "max", "alan": "opening_date"},
                                               {"islem": "sayi", "alan": "karar_tarihi"}]))
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["toplam"] == 1 and len(g["satirlar"]) == 1
    s = g["satirlar"][0]
    assert s["sayi"] == 3 and s["ortalama:maddi_tazminat"] == pytest.approx(450.1666, abs=0.001)
    assert s["min:opening_date"] == "2024-06-15" and s["max:opening_date"] == "2025-03-20"
    assert s["sayi:karar_tarihi"] == 0                          # dolu değer sayısı
    etiketler = {k["anahtar"]: k["etiket"] for k in g["kolonlar"]}
    assert etiketler["ortalama:maddi_tazminat"] == "Ortalama Maddi Tazminat"
    assert etiketler["min:opening_date"] == "En küçük Açılış Tarihi" and etiketler["sayi:karar_tarihi"] == "Karar Tarihi sayısı"


def test_filtre_gruplamadan_once_ve_olcum_siralamasi(env):
    """Kabul: WHERE gruplamadan önce (status=KARAR → yalnız Veli); ölçüm anahtarıyla artan sıralama."""
    r = _onizle(env.client(), _tanim(gruplama=[{"alan": "responsible_lawyer_name"}],
                                     filtreler=[{"alan": "status", "op": "eq", "deger": "KARAR"}]))
    assert r.json()["satirlar"] == [{"responsible_lawyer_name": "Av. Veli", "sayi": 1}]
    r = _onizle(env.client(), _tanim(gruplama=[{"alan": "responsible_lawyer_name"}],
                                     siralama=[{"alan": "sayi", "yon": "asc"}]))
    assert [s["responsible_lawyer_name"] for s in r.json()["satirlar"]] == ["Av. Veli", "Av. Ali"]


def test_ozet_export_csv_ve_kolon_sayisi(env):
    """Kabul: export yolu özet kolonlarını yazar (`kolon_basliklari` + `satirlari_akit` aynı anahtarlar)."""
    tanim = RaporTanimi.model_validate(_tanim(gruplama=[{"alan": "responsible_lawyer_name"}],
                                              olcumler=[{"islem": "sayi"}, {"islem": "toplam", "alan": "maddi_tazminat"}]))
    db = env.db()
    try:
        import tempfile
        from pathlib import Path

        hedef = Path(tempfile.mkdtemp()) / "ozet.csv"
        kolonlar = motor.kolon_basliklari(tanim)
        ozet = cikti.ciktiyi_yaz("csv", kolonlar, motor.satirlari_akit(db, tanim, T1), hedef)
        satirlar = list(csv.reader(io.StringIO(hedef.read_bytes().decode("utf-8-sig")), delimiter=";"))
    finally:
        db.close()
    assert ozet.satir_sayisi == 2
    assert satirlar == [["Sorumlu Avukat", "Kayıt sayısı", "Toplam Maddi Tazminat"],
                        ["Av. Ali", "2", "1100,50"], ["Av. Veli", "1", "250,00"]]


# ─── 422 kuralları ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("tanim,alan,sebep", [
    (_tanim(gruplama=[{"alan": "muvekkil_adlari"}]), "gruplama[0]", "gruplanamaz"),
    (_tanim(gruplama=[{"alan": "status", "kirilim": "ay"}]), "gruplama[0]", "kırılım yalnız tarih"),
    (_tanim(gruplama=[{"alan": "yok_boyle"}]), "gruplama[0]", "katalogda olmayan"),
    (_tanim(olcumler=[{"islem": "toplam", "alan": "subject"}]), "olcumler[0]", "yapılamaz"),
    (_tanim(olcumler=[{"islem": "toplam"}]), "olcumler", "alan ister"),
    (_tanim(olcumler=[{"islem": "sayi"}, {"islem": "sayi"}]), "olcumler", "tekrar"),
    (_tanim(gruplama=[{"alan": "status"}], olcumler=[]), "olcumler", "ölçüm ister"),
    (_tanim(gruplama=[{"alan": "status"}], siralama=[{"alan": "tracking_no", "yon": "asc"}]), "siralama[0]",
     "özet modunda"),
    (_tanim(gruplama=[{"alan": "status", "kirilim": "hafta"}]), "gruplama", ""),
    (_tanim(gruplama=[{"alan": a} for a in ("status", "court", "sub_type", "responsible_lawyer_name")]), "gruplama", ""),
    (_tanim(olcumler=[{"islem": "sayi", "alan": a} for a in ("status", "court", "sub_type", "subject", "esas_no", "il")]),
     "olcumler", ""),
    (_tanim(gruplama=[{"alan": "arama"}]), "gruplama[0]", "gruplanamaz"),
])
def test_ozet_422(env, tanim, alan, sebep):
    _422(_onizle(env.client(), tanim), alan, sebep)


def test_sinirlar_sabit():
    assert GRUPLAMA_MAX == 3 and OLCUM_MAX == 5
    assert olcum_anahtari("sayi", None) == "sayi" and olcum_anahtari("toplam", "x") == "toplam:x"


def test_liste_gorunumu_degismedi(env):
    """Kabul: `olcumler` boş → eski davranış (kolonlar seçilir, `gruplama` yok sayılmaz — ölçümsüz gruplama 422)."""
    r = _onizle(env.client(), {"veri_kaynagi": "davalar", "kolonlar": ["tracking_no"], "filtreler": [], "siralama": []})
    assert r.status_code == 200 and [k["anahtar"] for k in r.json()["kolonlar"]] == ["tracking_no"]


# ─── Katalog, Postgres derlemesi, asistan ────────────────────────────────────

def test_katalog_gruplanabilir_ve_limitler(env):
    r = env.client().get(CATALOG)
    assert r.status_code == 200
    g = r.json()
    assert g["limitler"]["gruplama_max"] == 3 and g["limitler"]["olcum_max"] == 5
    davalar = {k["anahtar"]: k for k in next(v for v in g["veri_kaynaklari"] if v["anahtar"] == "davalar")["kolonlar"]}
    assert davalar["tracking_no"]["gruplanabilir"] is True and davalar["opening_date"]["gruplanabilir"] is True
    assert davalar["muvekkil_adlari"]["gruplanabilir"] is False and davalar["arama"]["gruplanabilir"] is False
    assert davalar["muvekkil.phone"]["gruplanabilir"] is False          # çoklu bağ — sıralanamaz


def test_tr_gun_postgres_derlemesi_turkiye_gunu():
    """Kabul: Postgres'te gün kırılımı `AT TIME ZONE 'Europe/Istanbul'` ile (UTC gün değil); varsayılan `date()`."""
    ifade = motor.tr_gun(models.Case.created_at)
    pg = str(ifade.compile(dialect=postgresql.dialect()))
    assert pg == "(cases.created_at AT TIME ZONE 'Europe/Istanbul')::date"
    assert str(ifade.compile()) == "date(cases.created_at)"
    tanim = RaporTanimi.model_validate(_tanim(gruplama=[{"alan": "created_at", "kirilim": "ay"}]))
    sql = str(motor.sorgu_kur(tanim, T1).compile(dialect=postgresql.dialect()))
    assert "GROUP BY substr(CAST((cases.created_at AT TIME ZONE 'Europe/Istanbul')::date AS VARCHAR)" in sql
    assert "count(*)" in sql and "ORDER BY count(*) DESC NULLS LAST" in sql


def test_asistan_ozet_tanimi_cevrilir_ve_dogrulanir():
    """Kabul: Gemini şemasındaki gruplama/olcumler `RaporTanimi`ye geçer, aynı doğrulama yolundan geçer;
    boş listeler gövdeye YAZILMAZ (eski istemci/şablon uyumu)."""
    at = AsistanTanimi(veri_kaynagi="davalar", kolonlar=["tracking_no"],
                       gruplama=[{"alan": "opening_date", "kirilim": "ay"}],
                       olcumler=[{"islem": "sayi"}, {"islem": "toplam", "alan": "maddi_tazminat"}],
                       siralama=[{"alan": "sayi", "yon": "desc"}])
    govde = asistan.asistan_tanimini_cevir(at)
    assert govde["gruplama"] == [{"alan": "opening_date", "kirilim": "ay"}]
    assert govde["olcumler"] == [{"islem": "sayi"}, {"islem": "toplam", "alan": "maddi_tazminat"}]
    tanim = asistan.tanimi_dogrula(at)
    assert tanim.ozet_modu and tanim.olcumler[1].anahtar == "toplam:maddi_tazminat"
    duz = asistan.asistan_tanimini_cevir(AsistanTanimi(veri_kaynagi="davalar", kolonlar=["tracking_no"]))
    assert "gruplama" not in duz and "olcumler" not in duz
    with pytest.raises(RaporDogrulamaHatasi, match="gruplanamaz"):
        asistan.tanimi_dogrula(AsistanTanimi(veri_kaynagi="davalar", kolonlar=["tracking_no"],
                                             gruplama=[{"alan": "muvekkil_adlari"}], olcumler=[{"islem": "sayi"}]))


def test_prompt_ozet_rapor_kurali():
    metin = get_rapor_asistani_instruction(asistan.katalog_metni(), "2026-09-12")
    assert "ÖZET RAPOR" in metin and "tanim.gruplama" in metin and "tanim.olcumler" in metin
    assert "kirilim gun|ay|yil" in metin and "GRUPLANAMAZ" in metin and "'sayi', 'toplam:maddi_tazminat'" in metin
    assert "isteğe bağlı gruplama/olcumler" in metin
    assert registry is not None
