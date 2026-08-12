"""G046 — eksik zorunlu alan: bağlamsal zorunluluk + denormalize kova bayrağı.

Kaynaklar: docs/plan/faz-f-aktarim-gereksinimleri-2026-08-12.md §2 (D2/D8) +
docs/kararlar/014-uyap-avukati-on-doldurulmaz.md + ana planın E6 maddesi.

Üç iddia kilitlenir:

1. **Zorunluluk bağlamsaldır** (D2). Ana Tür ∈ {Arabuluculuk, Savcılık,
   Danışmanlık, Tahkim} ise esas beklenmez. Kural VERİ olarak yazılır
   (`skip_when`) — kod olarak yazılsaydı SQL ikizi ve frontend onu göremezdi.
2. **Aktarım kaydı ayrı kovada** (D8). Provenance `case_history.source`
   imzasından okunur; ikinci bir "aktarımdan geldi" bayrağı tutulmaz.
3. **Bayrak bayatlamaz** (E6). `cases.missing_required_bucket` türetilmiş
   kolondur; üç yazma yolunun (add/update/enrich) üçü de aynı fonksiyondan
   geçer. Testler `refresh_missing_required`i DOĞRUDAN çağırmaz — gerçek yazma
   yollarından geçer (G045 deseni), çünkü kaçan bir yol tam olarak bayatlamanın
   kendisidir.

Yazma yolu testleri sqlite + StaticPool ile koşar (G044/G045 ile aynı desen);
SQL ikizinin gerçek Postgres'e karşı doğrulaması `dbtest` işaretli son bölümde.
"""
import json
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS
from required_fields import (
    AKTARIM_SOURCE_PREFIX,
    ESAS_BEKLENMEYEN_TURLER,
    MISSING_BUCKET_AKTARIM,
    MISSING_BUCKET_MANUAL,
    MISSING_FLAG_INPUT_FIELDS,
    REQUIRED_CASE_FIELDS,
    compute_missing_bucket,
    compute_missing_fields,
    is_aktarim_source,
    missing_bucket_sql,
    missing_required_sql,
)

KOLON = "missing_required_bucket"


def _tam_kayit(**overrides) -> dict:
    """Hiçbir zorunlu alanı eksik olmayan dava verisi."""
    data = {
        "esas_no": "2024/145",
        "court": "Ankara 5. Asliye Hukuk Mahkemesi",
        "file_type": "Hukuk",
        "judicial_unit": "Asliye Hukuk",
        "sub_type": "Tıbbi Malpraktis",
        "opening_date": "2024-01-15",
        "subject": "Tazminat",
        "responsible_lawyer_name": "Av. Deneme Kişi",
        "uyap_lawyer_name": "Av. Deneme Kişi",
        "service_type": "DAVA",
        "acceptance_date": "2024-01-10",
        "bureau_type": "LEXİS",
        "atama_tarihi": "2024-01-12",
    }
    data.update(overrides)
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 1. D2 — bağlamsal zorunluluk (Python kuralı)
# ═══════════════════════════════════════════════════════════════════════════

def test_kapi_verisi_json_serilestirilebilir():
    """Liste GET /api/config/required_case_fields ile aynen frontend'e gider.

    Kapıyı callable olarak yazmak (en kolay çözüm) bu ucu sessizce kırardı.
    """
    assert json.loads(json.dumps(REQUIRED_CASE_FIELDS)) == REQUIRED_CASE_FIELDS


@pytest.mark.parametrize("file_type", ESAS_BEKLENMEYEN_TURLER)
def test_d2_esas_beklenmeyen_turlerde_eksik_isaretlenmiyor(file_type):
    eksik = compute_missing_fields(_tam_kayit(esas_no=None, file_type=file_type), [])
    assert eksik == [], f"{file_type}: esas beklenmemeli"


def test_d2_besinci_yargi_turunde_esas_hala_zorunlu():
    """Kapı yalnız dört türü açar; genişlemesi sessiz olmamalı."""
    eksik = compute_missing_fields(_tam_kayit(esas_no=None, file_type="Hukuk"), [])
    assert [e["field"] for e in eksik] == ["esas_no"]


def test_d2_kapisi_yalnizca_kendi_alanini_serbest_birakiyor():
    """Tahkim dosyasında esas beklenmez ama diğer 12 alan hâlâ zorunlu."""
    eksik = compute_missing_fields(
        _tam_kayit(esas_no=None, file_type="Tahkim", court=None), []
    )
    assert [e["field"] for e in eksik] == ["court"]


def test_d2_bos_yargi_turu_kapiyi_acmiyor():
    """file_type'ın kendisi boşsa esas zorunlu KALIR (ikisi de eksik sayılır)."""
    eksik = compute_missing_fields(_tam_kayit(esas_no=None, file_type=None), [])
    assert {e["field"] for e in eksik} == {"esas_no", "file_type"}


def test_eksik_listesi_yalnizca_field_ve_label_tasiyor():
    """`skip_when` API yanıtına sızmamalı — panel yalnız alan+etiket bekliyor."""
    eksik = compute_missing_fields({}, [])
    assert all(set(e) == {"field", "label"} for e in eksik)


def test_bayrak_girdi_alanlari_kapi_alanlarini_da_kapsiyor():
    """Kapı `file_type`a bakıyor; anlık görüntü onu okumazsa kural çalışmaz."""
    assert set(MISSING_FLAG_INPUT_FIELDS) >= {f["field"] for f in REQUIRED_CASE_FIELDS}
    assert "file_type" in MISSING_FLAG_INPUT_FIELDS


# ═══════════════════════════════════════════════════════════════════════════
# 2. D8 — kova adlandırması (saf kural)
# ═══════════════════════════════════════════════════════════════════════════

def test_kova_eksik_yoksa_none():
    assert compute_missing_bucket([], is_aktarim=False) is None
    assert compute_missing_bucket([], is_aktarim=True) is None


def test_kova_aktarim_imzasina_gore_ayriliyor():
    eksik = [{"field": "uyap_lawyer_name", "label": "UYAP Avukatı"}]
    assert compute_missing_bucket(eksik, is_aktarim=False) == MISSING_BUCKET_MANUAL
    assert compute_missing_bucket(eksik, is_aktarim=True) == MISSING_BUCKET_AKTARIM


@pytest.mark.parametrize("source, beklenen", [
    ("HUKDOK_TESLIM_2026-08-12", True),
    ("HUKDOK_TESLIM", True),
    ("add_case", False),
    ("auto-enrich", False),
    ("", False),
    (None, False),
])
def test_aktarim_imzasi(source, beklenen):
    assert is_aktarim_source(source) is beklenen


# ═══════════════════════════════════════════════════════════════════════════
# 3. SQL ikizi — aynı listeden türüyor mu?
# ═══════════════════════════════════════════════════════════════════════════

def test_sql_ikizi_her_zorunlu_alani_ve_taraf_kuralini_kapsiyor():
    sql = missing_required_sql()
    for f in REQUIRED_CASE_FIELDS:
        assert f"cases.{f['field']}" in sql, f"{f['field']} SQL ikizinde yok"
    assert "case_parties" in sql


def test_sql_ikizi_d2_kapisini_ceviriyor():
    sql = missing_required_sql()
    assert "NOT IN" in sql
    for tur in ESAS_BEKLENMEYEN_TURLER:
        assert f"'{tur}'" in sql, f"{tur} SQL kapısında yok"


def test_sql_ikizi_tarih_kolonunda_trim_hatasina_dusmuyor():
    """trim(date) Postgres'te patlar; ikiz `::text` cast'iyle geziyor."""
    sql = missing_required_sql()
    assert "cases.opening_date::text" in sql


def test_aktarim_sql_i_like_yerine_starts_with_kullaniyor():
    """LIKE 'HUKDOK_TESLIM%' tuzağı: '_' SQL'de tek karakter jokeridir."""
    sql = missing_bucket_sql()
    assert f"starts_with(h.source, '{AKTARIM_SOURCE_PREFIX}')" in sql
    assert "LIKE" not in sql.upper()
    assert f"'{MISSING_BUCKET_AKTARIM}'" in sql and f"'{MISSING_BUCKET_MANUAL}'" in sql


# ═══════════════════════════════════════════════════════════════════════════
# 4. Şema + migrasyon
# ═══════════════════════════════════════════════════════════════════════════

def test_kolon_modelde_ve_dogru_tipte():
    kolon = models.Case.__table__.columns[KOLON]
    assert kolon.type.length == 20
    assert kolon.nullable, "NULL = eksik yok"


def test_yeni_satir_varsayilani_manual():
    """case_manager'ı atlayan bir yazıcı satırı hesaplamasız bırakırsa kayıt
    GÖRÜNÜR kalmalı: görünmeyen borç hiç kapanmaz (ADR-014)."""
    kolon = models.Case.__table__.columns[KOLON]
    assert kolon.server_default is not None
    assert MISSING_BUCKET_MANUAL in str(kolon.server_default.arg)


def test_migrasyon_kolonu_ekliyor_ve_backfill_ediyor():
    spec = None
    for op in _MIGRATIONS:
        if op[0] == "columns" and op[1] == "cases" and KOLON in op[2]:
            spec = op[2][KOLON]
    assert spec is not None, f"cases.{KOLON} için migrasyon adımı yok"
    ddl, post_sql = spec
    assert "VARCHAR(20)" in ddl and MISSING_BUCKET_MANUAL in ddl
    assert len(post_sql) == 1
    # Backfill İKİNCİ BİR KURAL LİSTESİ DEĞİL: required_fields'tan türetiliyor
    assert missing_bucket_sql("cases") in post_sql[0]
    assert post_sql[0].startswith(f"UPDATE cases SET {KOLON} =")


def test_takip_formu_zorunlu_alan_yazmiyor():
    """Bayatlama nöbeti: `update_case_tracking` bayrağı tazelemez.

    Bugün doğru, çünkü TRACKING_FIELDS ile zorunlu alanların kesişimi BOŞ.
    Kesişim doğduğu gün bu test düşer ve o yola da bir tazeleme çağrısı
    gerektiğini söyler — sessiz bayatlama yerine kırmızı test.
    """
    from managers.case_manager import TRACKING_FIELDS

    kesisim = set(TRACKING_FIELDS) & {f["field"] for f in REQUIRED_CASE_FIELDS}
    assert kesisim == set(), f"takip formu artık zorunlu alan yazıyor: {kesisim}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Yazma yolları — bayrak bayatlamıyor (sqlite)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db_env(monkeypatch):
    """Paylaşılan in-memory sqlite + case_manager.SessionLocal yönlendirmesi."""
    from database import Base
    from managers import case_manager

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", maker)
    yield SimpleNamespace(sessions=maker, manager=case_manager, engine=engine)
    engine.dispose()


@pytest.fixture()
def kaydedilen_sql(db_env):
    """Motora giden ham SQL'i toplar — "hangi sorgu koştu" iddiası ölçülebilsin."""
    from sqlalchemy import event

    kayit: list = []

    def _dinle(conn, cursor, statement, parameters, context, executemany):
        kayit.append(statement)

    event.listen(db_env.engine, "before_cursor_execute", _dinle)
    yield kayit
    event.remove(db_env.engine, "before_cursor_execute", _dinle)


def _kova(db_env, case_id):
    db = db_env.sessions()
    try:
        return getattr(db.get(models.Case, case_id), KOLON)
    finally:
        db.close()


def _dava(db_env, tracking_no="HA.X.0001.2026", parties=None, **overrides):
    data = _tam_kayit(**overrides)
    data["tracking_no"] = tracking_no
    data["parties"] = parties if parties is not None else []
    created = db_env.manager.add_case(data)
    assert created and "id" in created, created
    return created["id"]


def _imza_at(db_env, case_id, source):
    """Kayda provenance imzası düşer (aktarımın yapacağı şey)."""
    db = db_env.sessions()
    try:
        db.add(models.CaseHistory(
            case_id=case_id, field_name="esas_no", old_value="", new_value="x",
            changed_by="aktarim", source=source,
        ))
        db.commit()
    finally:
        db.close()


def test_add_case_tam_kayitta_bayrak_bos(db_env):
    assert _kova(db_env, _dava(db_env)) is None


def test_add_case_eksik_alanda_manual_kovasi(db_env):
    assert _kova(db_env, _dava(db_env, uyap_lawyer_name=None)) == MISSING_BUCKET_MANUAL


def test_add_case_tcsiz_karsi_taraf_bayragi_yakiyor(db_env):
    """Taraf kuralı bayrağa yansımalı — taraflar davadan SONRA yazılıyor."""
    case_id = _dava(db_env, parties=[
        {"name": "Karşı Kurum", "role": "Davalı", "party_type": "COUNTER"},
    ])
    assert _kova(db_env, case_id) == MISSING_BUCKET_MANUAL


def test_add_case_tcli_karsi_taraf_bayragi_yakmiyor(db_env):
    case_id = _dava(db_env, parties=[
        {"name": "Karşı Kurum", "role": "Davalı", "party_type": "COUNTER",
         "tc_no": "12345678901"},
    ])
    assert _kova(db_env, case_id) is None


def test_update_case_son_eksigi_doldurunca_bayrak_dusuyor(db_env):
    case_id = _dava(db_env, uyap_lawyer_name=None)
    assert _kova(db_env, case_id) == MISSING_BUCKET_MANUAL

    assert db_env.manager.update_case(case_id, {"uyap_lawyer_name": "Av. Deneme Kişi"}) is True

    assert _kova(db_env, case_id) is None


def test_update_case_alani_bosaltinca_bayrak_geri_geliyor(db_env):
    case_id = _dava(db_env)

    assert db_env.manager.update_case(case_id, {"subject": "   "}) is True

    assert _kova(db_env, case_id) == MISSING_BUCKET_MANUAL


def test_update_case_tcsiz_karsi_taraf_eklenince_bayrak_yaniyor(db_env):
    case_id = _dava(db_env)

    db_env.manager.update_case(case_id, {"parties": [
        {"name": "Karşı Kurum", "role": "Davalı", "party_type": "COUNTER"},
    ]})

    assert _kova(db_env, case_id) == MISSING_BUCKET_MANUAL


def test_enrich_case_de_bayragi_tazeliyor(db_env):
    """Belgeden zenginleştirme (Faz 7) bayrağı ATLAMAMALI."""
    case_id = _dava(db_env, court=None)
    assert _kova(db_env, case_id) == MISSING_BUCKET_MANUAL

    sonuc = db_env.manager.enrich_case(
        case_id, {"court": "Ankara 5. Asliye Hukuk Mahkemesi"}, [],
        changed_by="ilke@lexis.com.tr", source="intake-enrich: tensip.pdf",
    )
    assert sonuc and not sonuc.get("error"), sonuc

    assert _kova(db_env, case_id) is None


def test_d2_uctan_uca_tahkim_dosyasi_eksik_sayilmiyor(db_env):
    """Kabul kriteri: dört türden birinde esas boşken kayıt eksik DEĞİL."""
    case_id = _dava(db_env, esas_no=None, file_type="Tahkim")
    assert _kova(db_env, case_id) is None

    # Beşinci bir yargı türüne çevrilince aynı kayıt eksiğe düşüyor
    assert db_env.manager.update_case(case_id, {"file_type": "Hukuk"}) is True
    assert _kova(db_env, case_id) == MISSING_BUCKET_MANUAL


def test_d8_aktarim_imzali_kayit_ayri_kovada(db_env):
    """Kabul kriteri: HUKDOK_TESLIM_* imzalı kayıt AKTARIM kovasında."""
    case_id = _dava(db_env, uyap_lawyer_name=None)
    assert _kova(db_env, case_id) == MISSING_BUCKET_MANUAL

    _imza_at(db_env, case_id, "HUKDOK_TESLIM_2026-08-12")
    db_env.manager.update_case(case_id, {})

    assert _kova(db_env, case_id) == MISSING_BUCKET_AKTARIM


def test_d8_imzasiz_kayit_normal_kovada(db_env):
    case_id = _dava(db_env, uyap_lawyer_name=None)
    _imza_at(db_env, case_id, "auto-enrich")
    db_env.manager.update_case(case_id, {})

    assert _kova(db_env, case_id) == MISSING_BUCKET_MANUAL


def test_d8_aktarim_kaydinin_eksigi_kapaninca_kova_bosaliyor(db_env):
    """"Alan elle doldurulunca kayıt normal kovaya geçer" (ADR-014)."""
    case_id = _dava(db_env, uyap_lawyer_name=None)
    _imza_at(db_env, case_id, "HUKDOK_TESLIM_2026-08-12")
    db_env.manager.update_case(case_id, {})
    assert _kova(db_env, case_id) == MISSING_BUCKET_AKTARIM

    db_env.manager.update_case(case_id, {"uyap_lawyer_name": "Av. Deneme Kişi"})

    assert _kova(db_env, case_id) is None


# ═══════════════════════════════════════════════════════════════════════════
# 6. Filtre — E6 sıcak yolu + kova seçimi
# ═══════════════════════════════════════════════════════════════════════════

def _kurulum_iki_kova(db_env):
    tam = _dava(db_env, tracking_no="HA.X.0001.2026")
    elle = _dava(db_env, tracking_no="HA.X.0002.2026", uyap_lawyer_name=None)
    aktarim = _dava(db_env, tracking_no="HA.X.0003.2026", uyap_lawyer_name=None)
    _imza_at(db_env, aktarim, "HUKDOK_TESLIM_2026-08-12")
    db_env.manager.update_case(aktarim, {})
    return tam, elle, aktarim


def test_filtre_kolonu_okuyor_korele_exists_kalkti(db_env, kaydedilen_sql):
    """E6: sıcak yolda korele alt sorgu yok — filtre tek kolonu okuyor.

    İddia gerçekten KOŞAN sorgu üzerinden ölçülür; elde derlenmiş bir ifadeyi
    denetlemek kendini onaylayan bir test olurdu.
    """
    _kurulum_iki_kova(db_env)
    kaydedilen_sql.clear()

    db_env.manager.get_cases(missing_required=True)

    filtreli = [s for s in kaydedilen_sql if KOLON in s]
    assert filtreli, "filtre kolonu hiç okunmadı"
    for sql in filtreli:
        assert "EXISTS" not in sql.upper(), sql


def test_filtre_kova_verilmezse_iki_kovayi_da_donduruyor(db_env):
    _, elle, aktarim = _kurulum_iki_kova(db_env)

    items, total = db_env.manager.get_cases(missing_required=True)

    assert total == 2
    assert {i["id"] for i in items} == {elle, aktarim}


def test_filtre_manual_kovasi_aktarimi_disliyor(db_env):
    _, elle, _ = _kurulum_iki_kova(db_env)

    items, total = db_env.manager.get_cases(
        missing_required=True, missing_bucket=MISSING_BUCKET_MANUAL
    )

    assert total == 1 and [i["id"] for i in items] == [elle]


def test_filtre_aktarim_kovasi_yalniz_aktarimi_donduruyor(db_env):
    _, _, aktarim = _kurulum_iki_kova(db_env)

    items, total = db_env.manager.get_cases(
        missing_required=True, missing_bucket=MISSING_BUCKET_AKTARIM
    )

    assert total == 1 and [i["id"] for i in items] == [aktarim]


def test_filtre_bilinmeyen_kovayi_yok_sayiyor(db_env):
    """Yazım hatası sessizce BOŞ liste döndürmemeli (yanlış "eksik yok" cevabı)."""
    _, elle, aktarim = _kurulum_iki_kova(db_env)

    items, total = db_env.manager.get_cases(missing_required=True, missing_bucket="MANUEL")

    assert total == 2 and {i["id"] for i in items} == {elle, aktarim}


def test_filtresiz_liste_tam_kaydi_da_donduruyor(db_env):
    tam, elle, aktarim = _kurulum_iki_kova(db_env)

    items, total = db_env.manager.get_cases()

    assert total == 3 and {i["id"] for i in items} == {tam, elle, aktarim}


def test_satir_uyarisi_d2_kapisina_uyuyor(db_env):
    """Listedeki satır uyarısı (canlı hesap) ile bayrak aynı kuralı söylemeli."""
    case_id = _dava(db_env, esas_no=None, file_type="Arabuluculuk")

    items, _ = db_env.manager.get_cases()
    kart = db_env.manager.get_case(case_id)

    assert items[0]["missing_required_fields"] == []
    assert kart["missing_required_fields"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 7. Gerçek Postgres — bayrak ile SQL/Python kurallarının sapması
# ═══════════════════════════════════════════════════════════════════════════

EN_AZ_KAYIT = 20


@pytest.fixture(scope="module")
def gercek_db():
    """Gerçek (dev/prod kopyası) veritabanına SALT OKUNUR oturum; yoksa SKIP."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import NullPool

    url = os.getenv("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        pytest.skip("DATABASE_URL postgresql:// değil")

    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as conn:
            var = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'cases' AND column_name = :k"
            ), {"k": KOLON}).first()
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"Gerçek Postgres'e ulaşılamadı ({type(exc).__name__})")
    if not var:
        engine.dispose()
        pytest.skip(f"cases.{KOLON} kolonu yok — migrasyon henüz koşmamış")

    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


def _sentetik_satir_sql(**overrides) -> str:
    """Tek satırlık sahte `cases` görünümü — SQL ikizini kontrollü girdiyle sınar.

    `id = -1`: karşı taraf/aktarım alt sorguları gerçek tablolara vurur ama
    hiçbir satır bulamaz. Sorgu SALT OKUNURDUR, veritabanına yazmaz.
    """
    data = _tam_kayit(**overrides)
    kolonlar = ["-1::int AS id"]
    for name in MISSING_FLAG_INPUT_FIELDS:
        value = data.get(name)
        literal = "NULL::text" if value is None else "'" + str(value).replace("'", "''") + "'::text"
        kolonlar.append(f"{literal} AS {name}")
    return "WITH v AS (SELECT " + ", ".join(kolonlar) + ")"


@pytest.mark.parametrize("overrides, beklenen", [
    ({}, None),                                              # tam kayıt
    ({"uyap_lawyer_name": None}, MISSING_BUCKET_MANUAL),     # NULL alan
    ({"subject": "   "}, MISSING_BUCKET_MANUAL),             # yalnız boşluk
    ({"esas_no": None, "file_type": "Tahkim"}, None),        # D2 kapısı açık
    ({"esas_no": None, "file_type": "Hukuk"}, MISSING_BUCKET_MANUAL),
    ({"opening_date": None}, MISSING_BUCKET_MANUAL),         # tarih kolonu
])
@pytest.mark.dbtest
def test_sql_ikizi_gercek_postgreste_python_ile_ayni_sonucu_veriyor(
    gercek_db, overrides, beklenen
):
    """İkizin Postgres'te GERÇEKTEN çalıştığı ve Python ile aynı dediği.

    Yalnız gerçek satırlara bakmak yetmez: lokal kopyada 14.345 kaydın hepsinde
    en az bir alan boş (service_type), yani "tam kayıt" dalı hiç denenmezdi.
    """
    from sqlalchemy import text

    sql = f"{_sentetik_satir_sql(**overrides)} SELECT {missing_bucket_sql('v')} FROM v"
    sonuc = gercek_db.execute(text(sql)).scalar()

    assert sonuc == beklenen
    # Python kuralı aynı girdide aynı şeyi söylemeli (ikizlik iddiasının kendisi)
    assert compute_missing_bucket(
        compute_missing_fields(_tam_kayit(**overrides), []), False
    ) == beklenen


@pytest.mark.dbtest
def test_gercek_kayitlarda_bayrak_sql_ikiziyle_ayni(gercek_db):
    """Kabul kriteri: bayrak ile kuralın SQL karşılığı 0 fark (bayatlama nöbeti)."""
    from managers.case_manager import audit_missing_required_flags

    rapor = audit_missing_required_flags(db=gercek_db)
    if rapor["toplam"] < EN_AZ_KAYIT:
        pytest.skip(f"gerçek kayıt sayısı yetersiz ({rapor['toplam']})")
    assert rapor["sapan"] == 0, f"bayat bayraklar: {rapor['ornekler']}"


@pytest.mark.dbtest
def test_gercek_kayitlarda_bayrak_python_kuraliyla_ayni(gercek_db):
    """SQL ikizinin değil, PYTHON kuralının kendisiyle karşılaştırma.

    İkisi ayrı yollardır: bayrağı Python yazar, backfill'i SQL yazdı. Yalnız
    SQL'e karşı doğrulamak, iki SQL'in aynı yanlışı yapması hâlinde sessiz
    kalırdı.
    """
    from sqlalchemy.orm import selectinload

    from managers.case_manager import _case_snapshot, _is_aktarim_kaydi

    rows = (
        gercek_db.query(models.Case)
        .options(selectinload(models.Case.parties))
        .order_by(models.Case.id)
        .limit(50)
        .all()
    )
    if len(rows) < EN_AZ_KAYIT:
        pytest.skip(f"gerçek kayıt sayısı yetersiz ({len(rows)})")

    farklar = []
    for case in rows:
        eksik = compute_missing_fields(_case_snapshot(case), list(case.parties))
        beklenen = compute_missing_bucket(
            eksik, bool(eksik) and _is_aktarim_kaydi(gercek_db, case.id)
        )
        if beklenen != getattr(case, KOLON):
            farklar.append((case.id, getattr(case, KOLON), beklenen))

    assert farklar == [], f"{len(farklar)} kayıtta bayrak Python kuralından ayrıştı"
