"""G250 — kart AÇILIRKEN müvekkil başına hizmet + zorunluluk + liste filtresi + PATCH kapanışı.

Kilitlenen davranışlar:
  1. şema: `CasePartyCreate.hizmet_turleri` (müvekkil dışı tarafta 422); okuma şemaları ve
     zenginleştirme (apply) isteği hizmet alanı TAŞIMAZ; `Case.hizmet_turu` bildirimi `Text`,
  2. `add_case`: tarafı yarattıktan sonra hizmet satırlarını `case_hizmetleri.elle_kumesini_yaz`
     yolundan AYNI transaction'da yazar (müvekkil başına ayrı küme, kart özeti yenilenir),
  3. KULLANICI yolları (`ofis_no_sunucudan` bayrağı: POST /api/cases, intake commit): hizmeti
     olmayan müvekkil → 422, mesaj müvekkili adıyla sayar, kart açılmaz, sayaç artmaz; listede
     olmayan hizmet → 422. Script/aktarım yolu (bayraksız) zorunlu tutulmaz. `service_types`
     listesi BOŞSA zorunluluk atlanır (WARNING),
  4. kural `required_fields`'e GİRMEZ: mevcut/hizmetsiz kart "eksik" sayılmaz; eski
     `service_type` maddesi listeden ve SQL ikizinden kalktı (maske yine saklanır),
  5. `get_cases(hizmet_turu=X)`: eşitlik değil `EXISTS case_hizmetleri` — çok hizmetli kart her
     hizmetinin filtresinde bulunur, kapsam dışı föyün satırı sayılmaz, arama (tek koşu) ile
     birlikte çalışır,
  6. `PATCH /api/cases/{id}/tracking` `hizmet_turu` YAZMAZ (yok sayılır, öteki alanlar yazılır).

Süreç içi sqlite (StaticPool, FK açık, `case_hizmetleri` index SQL'leri migrasyondan aynen)
üzerinde GERÇEK `add_case` / `get_cases` / route koşar. Son katman (dbtest) aynı kapıyı
gerçek Postgres scratch DB'sinde sınar: sıra tahsisinin geri dönmesi, SAVEPOINT'li hizmet
yazımının kart transaction'ında yaşaması ve kolonun TEXT doğması sqlite'ta kanıtlanamaz.
"""
import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import Text, create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import models
import test_migration_path as mig
from managers import case_hizmetleri as ch
from managers import case_manager
from required_fields import (
    MISSING_FLAG_INPUT_FIELDS,
    REQUIRED_CASE_FIELDS,
    compute_missing_fields,
    missing_required_sql,
)
from schemas import (
    CaseCreate,
    CaseListRead,
    CasePartyBase,
    CasePartyCreate,
    CaseRead,
    CaseTrackingUpdate,
)
from schemas_intake import CaseIntakeApplyRequest, CaseIntakeCommitRequest

BAYRAK = case_manager.SUNUCU_NUMARASI_BAYRAGI

# Scratch DB fixture'ı `test_migration_path`'ten yeniden kullanılır (test_g196 deseni).
admin_engine = mig.admin_engine

HIZMETLER = [
    ("DANISMANLIK", "Danışmanlık"),
    ("LEXIS-RAPOR", "Lexis Rapor"),
    ("VEKALETLI-TAKIP", "Vekaletli Takip"),
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Şema — DB'siz
# ═══════════════════════════════════════════════════════════════════════════

def test_parti_semasi_hizmet_turleri_muvekkilde_gecerli_baska_tarafta_422():
    alan = CasePartyCreate.model_fields["hizmet_turleri"]
    assert alan.is_required() is False
    assert CasePartyCreate(name="Ali", role="Davalı", party_type="CLIENT").hizmet_turleri == []

    muvekkil = CasePartyCreate(
        name="Ali", role="Davalı", party_type="CLIENT", hizmet_turleri=["Lexis Rapor", "Danışmanlık"],
    )
    assert muvekkil.hizmet_turleri == ["Lexis Rapor", "Danışmanlık"]

    for tur in ("COUNTER", "THIRD"):
        with pytest.raises(ValidationError) as exc:
            CasePartyCreate(name="Karşı Kurum", role="Davacı", party_type=tur, hizmet_turleri=["Lexis Rapor"])
        assert "Karşı Kurum" in str(exc.value) and "müvekkil" in str(exc.value)
        # Boş liste "verilmedi" demektir — karşı tarafta hata değil
        assert CasePartyCreate(name="K", role="Davacı", party_type=tur, hizmet_turleri=[]).hizmet_turleri == []


def test_parti_semasi_hizmet_girdisi_tavanli():
    """Kart açma isteğinde de ad başına doğrulama sorgusu koşar — liste ve ad tavanlıdır."""
    from schemas import HIZMET_ADI_MAX_LEN, HIZMET_KUMESI_AZAMI

    def parti(adlar):
        return CasePartyCreate(name="Ali", role="Davalı", party_type="CLIENT", hizmet_turleri=adlar)

    assert len(parti(["Lexis Rapor"] * HIZMET_KUMESI_AZAMI).hizmet_turleri) == HIZMET_KUMESI_AZAMI
    assert parti(["x" * HIZMET_ADI_MAX_LEN]).hizmet_turleri == ["x" * HIZMET_ADI_MAX_LEN]
    for asan in (["Lexis Rapor"] * (HIZMET_KUMESI_AZAMI + 1), ["x" * (HIZMET_ADI_MAX_LEN + 1)]):
        with pytest.raises(ValidationError):
            parti(asan)


def test_hizmet_alani_yalniz_kart_acma_isteginde():
    """Okuma yanıtları ve zenginleştirme (apply) isteği hizmet alanı taşımaz: listede her
    tarafta boş bir `hizmet_turleri` görünmesi "hizmeti yok" diye okunurdu."""
    assert "hizmet_turleri" not in CasePartyBase.model_fields
    assert issubclass(CasePartyCreate, CasePartyBase)
    assert CaseCreate.model_fields["parties"].annotation.__args__[0] is CasePartyCreate
    for okuma in (CaseListRead, CaseRead):
        assert okuma.model_fields["parties"].annotation.__args__[0] is CasePartyBase, okuma.__name__
    assert CaseIntakeApplyRequest.model_fields["parties"].annotation.__args__[0] is CasePartyBase
    # Commit (yeni kart) CaseCreate taşır → taraf başına hizmet_turleri
    commit = CaseIntakeCommitRequest.model_validate({"case": {"parties": [
        {"name": "Ali", "role": "Davalı", "party_type": "CLIENT", "hizmet_turleri": ["Lexis Rapor"]},
    ]}})
    assert commit.case.parties[0].hizmet_turleri == ["Lexis Rapor"]


def test_model_ozet_kolonu_text():
    """G248 SAPMA 2 kapanışı: bildirim `Text` — yalnız `create_all` koşan kurulumda da TEXT."""
    kolon = models.Case.__table__.c.hizmet_turu
    assert isinstance(kolon.type, Text)
    assert getattr(kolon.type, "length", None) is None
    assert kolon.nullable is True and kolon.default is None


def test_takip_ucu_hizmet_turunu_tanimiyor():
    assert "hizmet_turu" not in case_manager.TRACKING_FIELDS
    assert "hizmet_turu" not in CaseTrackingUpdate.model_fields
    # Gönderilirse yok sayılır (422 değil): formu olduğu gibi geri gönderen eski istemci kırılmaz
    dump = CaseTrackingUpdate.model_validate(
        {"hizmet_turu": "Lexis Rapor", "muvekkil_tipi": "Doktor"}
    ).model_dump(exclude_unset=True)
    assert dump == {"muvekkil_tipi": "Doktor"}
    assert case_manager.tracking_changes({"hizmet_turu": "Lexis Rapor", "muvekkil_tipi": "Doktor"}) == [
        ("muvekkil_tipi", "Doktor"),
    ]
    # Hizmet SATIRININ adı aynı kapalı liste kapısından doğrulanmaya devam eder
    assert case_manager._EVENT_LIST_COLUMNS["hizmet_turu"] == (models.ServiceType, "service_types")


def test_zorunlu_alanlarda_service_type_ve_hizmet_yok():
    alanlar = {f["field"] for f in REQUIRED_CASE_FIELDS}
    assert "service_type" not in alanlar
    assert "service_type" not in MISSING_FLAG_INPUT_FIELDS
    assert "service_type" not in missing_required_sql("cases")
    # Hizmet kuralı OLUŞTURMA kapısıdır — eksik-alan kuralına hiçbir adla girmez
    for ad in ("hizmet_turu", "hizmet_turleri", "hizmetler"):
        assert ad not in alanlar and ad not in MISSING_FLAG_INPUT_FIELDS, ad
        assert ad not in missing_required_sql("cases"), ad

    tam = {f["field"]: "dolu" for f in REQUIRED_CASE_FIELDS}
    assert compute_missing_fields({**tam, "service_type": None}, []) == []
    assert compute_missing_fields({**tam, "service_type": "  "}, []) == []


def test_hata_tipi_route_422_sozlesmesine_bagli():
    """İki kullanıcı route'u `OfisNoVerilemez`'i 422 + detail=str(e)'ye çevirir; hizmet
    kapısının hatası o sınıftandır (route'lara ikinci `except` gerekmez)."""
    assert issubclass(case_manager.HizmetKaydiGecersiz, case_manager.OfisNoVerilemez)
    assert issubclass(case_manager.HizmetKaydiGecersiz, ValueError)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Davranış — sqlite
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def ortam(monkeypatch):
    """Paylaşılan in-memory sqlite; `case_manager` oturumları buraya yönlenir. SAVEPOINT
    (`begin_nested`) gerçek çalışsın diye pysqlite'ın örtük BEGIN'i kapatılır (test_g179 deseni)."""
    from routes import cases as cases_route

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_ac(dbapi_conn, _rec):
        dbapi_conn.isolation_level = None
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    database.Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for op in database._MIGRATIONS:
            if op[0] == "index" and op[1] == "case_hizmetleri":
                for sql in op[2]:
                    conn.execute(text(sql))
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", maker)
    monkeypatch.setattr(cases_route, "SessionLocal", maker)

    statements: list = []

    @event.listens_for(engine, "before_cursor_execute")
    def _kaydet(conn, cursor, stmt, params, ctx, many):
        statements.append(stmt)

    yield SimpleNamespace(maker=maker, statements=statements)
    engine.dispose()


@pytest.fixture()
def listeli(ortam):
    """`service_types` seed'li ortam (prod'daki olağan durum)."""
    db = ortam.maker()
    for sira, (kod, ad) in enumerate(HIZMETLER):
        db.add(models.ServiceType(code=kod, name=ad, active=True, sequence=sira))
    db.commit()
    db.close()
    return ortam


def _muvekkil(ad, *hizmetler, **ek):
    taraf = {"name": ad, "role": "Davalı", "party_type": "CLIENT", **ek}
    if hizmetler:
        taraf["hizmet_turleri"] = list(hizmetler)
    return taraf


def _karsi(ad, **ek):
    return {"name": ad, "role": "Davacı", "party_type": "COUNTER", **ek}


def _say(ortam, model) -> int:
    db = ortam.maker()
    try:
        return db.query(model).count()
    finally:
        db.close()


def _satirlar(ortam, case_id):
    """[(müvekkil adı, hizmet, föy kaynaklı mı)] — sıralı."""
    db = ortam.maker()
    try:
        adlar = {p.id: p.name for p in db.query(models.CaseParty).filter_by(case_id=case_id).all()}
        return sorted(
            (adlar[r.case_party_id], r.hizmet_turu, r.foy_id is not None)
            for r in db.query(models.CaseHizmeti).filter_by(case_id=case_id).all()
        )
    finally:
        db.close()


def _kart(ortam, case_id):
    db = ortam.maker()
    try:
        return db.get(models.Case, case_id)
    finally:
        db.close()


def _hizmet_tarihcesi(ortam, case_id):
    db = ortam.maker()
    try:
        return [
            (h.old_value, h.new_value, h.changed_by, h.source)
            for h in db.query(models.CaseHistory)
            .filter_by(case_id=case_id, field_name="hizmet").order_by(models.CaseHistory.id).all()
        ]
    finally:
        db.close()


# ─── add_case: satır yazımı ──────────────────────────────────────────────────

def test_add_case_muvekkil_basina_hizmet_kumesi_ayni_transactionda(listeli):
    sonuc = case_manager.add_case({
        BAYRAK: True, case_manager.KAYDEDEN_ANAHTARI: "Av. Kaydeden",
        "parties": [
            _muvekkil("Dr. Ali Veli", "Vekaletli Takip", "Danışmanlık"),
            _muvekkil("Ayşe Kaya", "Lexis Rapor"),
            _karsi("Karşı Kurum"),
        ],
    })
    assert sonuc and "error" not in sonuc
    cid = sonuc["id"]

    # Her müvekkil KENDİ kümesini taşır (muhasebe ayrımı); karşı tarafa satır yok
    assert _satirlar(listeli, cid) == [
        ("Ayşe Kaya", "Lexis Rapor", False),
        ("Dr. Ali Veli", "Danışmanlık", False),
        ("Dr. Ali Veli", "Vekaletli Takip", False),
    ]
    # Türetilmiş özet tek yazıcıdan (`ozeti_yenile`): DISTINCT, Türkçe alfabetik, " ; "
    assert _kart(listeli, cid).hizmet_turu == "Danışmanlık ; Lexis Rapor ; Vekaletli Takip"
    # Müvekkil başına TEK tarihçe kaydı; imza kaydı açan kullanıcı + panel
    assert _hizmet_tarihcesi(listeli, cid) == [
        ("", "Dr. Ali Veli — Danışmanlık ; Vekaletli Takip", "Av. Kaydeden", case_manager.PANEL_SOURCE),
        ("", "Ayşe Kaya — Lexis Rapor", "Av. Kaydeden", case_manager.PANEL_SOURCE),
    ]
    # Okuma yolu: kartın `hizmetler` listesi elle satırları gösterir
    kart = case_manager.get_case(cid)
    assert [(h["muvekkil_adi"], h["hizmet_turu"], h["kaynak"]) for h in kart["hizmetler"]] == [
        ("Ayşe Kaya", "Lexis Rapor", "elle"),
        ("Dr. Ali Veli", "Danışmanlık", "elle"),
        ("Dr. Ali Veli", "Vekaletli Takip", "elle"),
    ]


def test_add_case_hizmet_adi_kanonik_ve_tekrarsiz(listeli):
    sonuc = case_manager.add_case({
        BAYRAK: True,
        "parties": [_muvekkil("Ali Veli", "  Lexis   Rapor ", "Lexis Rapor")],
    })
    assert _satirlar(listeli, sonuc["id"]) == [("Ali Veli", "Lexis Rapor", False)]
    # Route kaydedeni vermezse imza PANEL_SOURCE (update_case ile aynı varsayılan)
    assert _hizmet_tarihcesi(listeli, sonuc["id"]) == [
        ("", "Ali Veli — Lexis Rapor", case_manager.PANEL_SOURCE, case_manager.PANEL_SOURCE),
    ]


# ─── add_case: zorunluluk kapısı ─────────────────────────────────────────────

def test_kullanici_yolunda_hizmetsiz_muvekkil_reddedilir_hicbir_sey_yazilmaz(listeli, caplog):
    with caplog.at_level(logging.WARNING):
        with pytest.raises(case_manager.HizmetKaydiGecersiz) as exc:
            case_manager.add_case({
                BAYRAK: True,
                "parties": [
                    _muvekkil("Dr. Ali Veli", "Lexis Rapor"),
                    _muvekkil("Ayşe Kaya"),
                    _muvekkil("Mehmet Öz", hizmet_turleri=[]),
                    _karsi("Karşı Kurum"),
                ],
            })
    mesaj = str(exc.value)
    # Türkçe mesaj hizmetsiz müvekkilleri ADIYLA sayar; hizmeti olanı ve karşı tarafı saymaz
    assert '"Ayşe Kaya"' in mesaj and '"Mehmet Öz"' in mesaj
    assert "Dr. Ali Veli" not in mesaj and "Karşı Kurum" not in mesaj
    assert "hizmet türü" in mesaj.lower()

    assert _say(listeli, models.Case) == 0
    assert _say(listeli, models.CaseParty) == 0
    assert _say(listeli, models.CaseHizmeti) == 0
    assert _say(listeli, models.OfisNoSayaci) == 0, "sıra tahsis edilmeden reddedilmeli"
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == [], "istemci hatası ERROR basmaz"


def test_kullanici_yolunda_listede_olmayan_hizmet_reddedilir(listeli):
    with pytest.raises(case_manager.HizmetKaydiGecersiz) as exc:
        case_manager.add_case({
            BAYRAK: True,
            "parties": [_muvekkil("Ali Veli", "Lexis Rapor", "Serbest Hizmet")],
        })
    assert "Serbest Hizmet" in str(exc.value) and "Ali Veli" in str(exc.value)
    assert _say(listeli, models.Case) == 0 and _say(listeli, models.CaseHizmeti) == 0
    assert _say(listeli, models.OfisNoSayaci) == 0


def test_muvekkil_olmayan_tarafta_hizmet_dogrudan_cagrida_da_reddedilir(listeli):
    """Şema kullanıcı yolunda bunu zaten 422'ler; `add_case`'i doğrudan çağıran (script)
    için ikinci kilit."""
    for bayrak in (True, False):
        with pytest.raises(case_manager.HizmetKaydiGecersiz) as exc:
            case_manager.add_case({
                BAYRAK: bayrak, "tracking_no": "G250-KARSI",
                "parties": [_muvekkil("Ali Veli", "Lexis Rapor"),
                            _karsi("Karşı Kurum", hizmet_turleri=["Lexis Rapor"])],
            })
        assert "Karşı Kurum" in str(exc.value)
    assert _say(listeli, models.Case) == 0


def test_muvekkilsiz_istek_hizmet_kapisindan_gecer_ofis_no_hatasi_alir(listeli):
    """Hizmet kapısı müvekkilsiz isteğin G236 hatasını gölgelemez."""
    with pytest.raises(case_manager.OfisNoVerilemez) as exc:
        case_manager.add_case({BAYRAK: True, "parties": [_karsi("Karşı Kurum")]})
    assert not isinstance(exc.value, case_manager.HizmetKaydiGecersiz)
    assert "Müvekkil olmadan" in str(exc.value)


def test_script_yolu_zorunlu_tutulmaz_verilen_hizmeti_yazar(listeli):
    """Bayraksız çağrı (aktarım/script — kendi numarasını getirir): hizmetsiz müvekkil serbest."""
    hizmetsiz = case_manager.add_case({
        "tracking_no": "G250-SCRIPT-1", "parties": [_muvekkil("Ali Veli"), _karsi("Karşı Kurum")],
    })
    assert hizmetsiz and "error" not in hizmetsiz
    assert _satirlar(listeli, hizmetsiz["id"]) == []
    assert _kart(listeli, hizmetsiz["id"]).hizmet_turu is None

    hizmetli = case_manager.add_case({
        "tracking_no": "G250-SCRIPT-2", "parties": [_muvekkil("Ayşe Kaya", "Danışmanlık")],
    })
    assert _satirlar(listeli, hizmetli["id"]) == [("Ayşe Kaya", "Danışmanlık", False)]
    assert _kart(listeli, hizmetli["id"]).hizmet_turu == "Danışmanlık"

    # Verilen ad script yolunda da kapalı listeden doğrulanır
    with pytest.raises(case_manager.HizmetKaydiGecersiz):
        case_manager.add_case({
            "tracking_no": "G250-SCRIPT-3", "parties": [_muvekkil("Can Er", "Serbest Hizmet")],
        })
    assert _say(listeli, models.Case) == 2


def test_bos_listede_zorunluluk_atlanir_warning(ortam, caplog):
    """`service_types` BOŞ (seed koşmamış kurulum): seçilecek hizmet yok → kapı kart açmayı
    kilitlemez; avukat yazım koruması ve kapalı liste kapılarıyla aynı kural."""
    with caplog.at_level(logging.WARNING):
        sonuc = case_manager.add_case({BAYRAK: True, "parties": [_muvekkil("Ali Veli")]})
    assert sonuc and "error" not in sonuc
    assert _say(ortam, models.Case) == 1 and _say(ortam, models.CaseHizmeti) == 0
    assert any("service_types" in r.message and "BOŞ" in r.message for r in caplog.records)
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_hizmetsiz_kart_eksik_sayilmaz(listeli):
    """Kural yalnız OLUŞTURMA kapısıdır: hizmetsiz (script/eski) kartın eksik listesinde
    hizmetle ilgili madde çıkmaz; `service_type` de artık eksik üretmez."""
    sonuc = case_manager.add_case({
        "tracking_no": "G250-EKSIK", "service_type": None, "parties": [_muvekkil("Ali Veli")],
    })
    kart = case_manager.get_case(sonuc["id"])
    eksikler = {m["field"] for m in kart["missing_required_fields"]}
    assert eksikler, "öteki zorunlu alanlar boş — kontrol: eksik listesi gerçekten hesaplanıyor"
    assert not eksikler & {"service_type", "hizmet_turu", "hizmet_turleri", "hizmetler"}


def test_service_type_geriye_uyum_icin_saklanir(listeli):
    """Eski 5'li maske okunur ve olduğu gibi saklanır (kolon silinmedi); sunucu kod üretmez."""
    sonuc = case_manager.add_case({
        BAYRAK: True, "service_type": "00100", "parties": [_muvekkil("Ali Veli", "Lexis Rapor")],
    })
    cid = sonuc["id"]
    assert _kart(listeli, cid).service_type == "00100"
    maskesiz = case_manager.add_case({BAYRAK: True, "parties": [_muvekkil("Ayşe Kaya", "Lexis Rapor")]})
    assert _kart(listeli, maskesiz["id"]).service_type is None, "sunucu maske ÜRETMEZ"

    assert case_manager.update_case(cid, {
        "service_type": "01000",
        "parties": [_muvekkil("Ali Veli", "Danışmanlık")], "lawyers": [],
    }) is True
    assert _kart(listeli, cid).service_type == "01000"
    # Düzenleme (PUT yolu) taraftaki hizmet_turleri'ni YOK SAYAR — hizmet ayrı uçtan yazılır
    assert _satirlar(listeli, cid) == [("Ali Veli", "Lexis Rapor", False)]


# ─── liste filtresi ──────────────────────────────────────────────────────────

def _dava(db, tracking_no, **alanlar):
    case = models.Case(tracking_no=tracking_no, status="DERDEST", active=True,
                       maddi_tazminat=0, manevi_tazminat=0, **alanlar)
    db.add(case)
    db.flush()
    return case


def _taraf(db, case, ad, tur="CLIENT"):
    party = models.CaseParty(case_id=case.id, name=ad, role="Davalı", party_type=tur)
    db.add(party)
    db.flush()
    return party


def _idler(sonuc):
    return {c["id"] for c in sonuc}


def test_filtre_exists_cok_hizmetli_kart_her_filtrede(listeli):
    db = listeli.maker()
    cok = _dava(db, "G250-F-1", subject="Tazminat davası")
    ali = _taraf(db, cok, "Ali Veli")
    ayse = _taraf(db, cok, "Ayşe Kaya")
    ch.elle_kumesini_yaz(db, cok, ali.id, ["Lexis Rapor"])
    ch.elle_kumesini_yaz(db, cok, ayse.id, ["Vekaletli Takip", "Danışmanlık"])

    tek = _dava(db, "G250-F-2", subject="Tazminat davası")
    ch.elle_kumesini_yaz(db, tek, _taraf(db, tek, "Can Er").id, ["Lexis Rapor"])

    # Satırı OLMAYAN kart: özet kolonunda eski tek değer dursa da filtre satıra bakar
    eski = _dava(db, "G250-F-3", hizmet_turu="Lexis Rapor")
    bos = _dava(db, "G250-F-4")
    baska_tenant = _dava(db, "G250-F-5", tenant_id="baska-tenant")
    ch.elle_kumesini_yaz(db, baska_tenant, _taraf(db, baska_tenant, "Ece Ak").id, ["Lexis Rapor"])
    db.commit()
    cok_id, tek_id, eski_id, bos_id = cok.id, tek.id, eski.id, bos.id
    assert cok.hizmet_turu == "Danışmanlık ; Lexis Rapor ; Vekaletli Takip"
    db.close()

    kartlar, toplam = case_manager.get_cases(hizmet_turu="Lexis Rapor", tenant_id="tenant-1")
    assert _idler(kartlar) == {cok_id, tek_id} and toplam == 2
    # Çok hizmetli kart HER hizmetinin filtresinde (eski eşitlik "A ; B" özetini bulamıyordu)
    for hizmet in ("Vekaletli Takip", "Danışmanlık"):
        kartlar, toplam = case_manager.get_cases(hizmet_turu=hizmet, tenant_id="tenant-1")
        assert _idler(kartlar) == {cok_id} and toplam == 1, hizmet
    # Özet metninin kendisi filtre değeri DEĞİL
    kartlar, toplam = case_manager.get_cases(
        hizmet_turu="Danışmanlık ; Lexis Rapor ; Vekaletli Takip", tenant_id="tenant-1")
    assert kartlar == [] and toplam == 0

    kartlar, toplam = case_manager.get_cases(tenant_id="tenant-1")
    assert _idler(kartlar) == {cok_id, tek_id, eski_id, bos_id} and toplam == 4
    kartlar, toplam = case_manager.get_cases(hizmet_turu="ALL", tenant_id="tenant-1")
    assert toplam == 4


def test_filtre_kapsam_disi_foyun_satirini_saymaz(listeli):
    db = listeli.maker()
    case = _dava(db, "G250-K-1")
    ali = _taraf(db, case, "Ali Veli")
    foy = models.CaseFoy(sistem_no="SSTMN-250", case_id=case.id, case_party_id=ali.id,
                         hizmet_turu="Lexis Rapor", source="HUKDOK_TESLIM_TEST")
    db.add(foy)
    db.flush()
    assert ch.foydan_yaz(db, foy).durum == ch.FOY_EKLENDI
    db.commit()
    case_id, foy_id = case.id, foy.id
    db.close()

    kartlar, toplam = case_manager.get_cases(hizmet_turu="Lexis Rapor")
    assert _idler(kartlar) == {case_id} and toplam == 1, "kapsamdaki föy satırı filtrede sayılır"

    # Föy kapsam dışına işaretlendi ama satırı henüz silinmedi (aktarımın bir sonraki adımı):
    # liste o satırı SAYMAZ.
    db = listeli.maker()
    db.get(models.CaseFoy, foy_id).kapsam_durumu = "KAPSAM_DISI"
    db.commit()
    db.close()
    assert _say(listeli, models.CaseHizmeti) == 1
    kartlar, toplam = case_manager.get_cases(hizmet_turu="Lexis Rapor")
    assert kartlar == [] and toplam == 0

    # Aynı müvekkile aynı hizmet ELLE de yazılıysa kart kapsamdaki o satırla bulunur
    db = listeli.maker()
    db.add(models.CaseHizmeti(case_id=case_id, case_party_id=db.query(models.CaseParty).first().id,
                              hizmet_turu="Lexis Rapor", foy_id=None))
    db.commit()
    db.close()
    kartlar, toplam = case_manager.get_cases(hizmet_turu="Lexis Rapor")
    assert _idler(kartlar) == {case_id} and toplam == 1


def test_filtre_arama_tek_kosu_yoluyla_birlikte(listeli):
    """`_search_term_ids` yolu bozulmadı: arama + hizmet filtresi + toplam TEK id sorgusunda
    (COUNT yok), filtre o sorguda `EXISTS case_hizmetleri` olarak koşar."""
    db = listeli.maker()
    a = _dava(db, "G250-A-1", subject="Tazminat davası")
    ch.elle_kumesini_yaz(db, a, _taraf(db, a, "Ali Veli").id, ["Lexis Rapor", "Danışmanlık"])
    b = _dava(db, "G250-A-2", subject="Tazminat davası")
    ch.elle_kumesini_yaz(db, b, _taraf(db, b, "Ayşe Kaya").id, ["Vekaletli Takip"])
    c = _dava(db, "G250-A-3", subject="Kira davası")
    ch.elle_kumesini_yaz(db, c, _taraf(db, c, "Can Er").id, ["Lexis Rapor"])
    db.commit()
    a_id = a.id
    db.close()

    listeli.statements.clear()
    kartlar, toplam = case_manager.get_cases(q="tazminat", hizmet_turu="Lexis Rapor", with_total=True)
    assert _idler(kartlar) == {a_id} and toplam == 1

    sorgular = [s.upper() for s in listeli.statements]
    union_sorgulari = [s for s in sorgular if " UNION " in s]
    assert len(union_sorgulari) == 1, "arama ağacı tek kez koşmalı (D4, G190)"
    assert "EXISTS" in union_sorgulari[0] and "CASE_HIZMETLERI" in union_sorgulari[0]
    assert not [s for s in sorgular if "COUNT(" in s], "aramada COUNT koşmaz"

    # Tuş vuruşu yolu (with_total=False) aynı filtreyle çalışır
    kartlar, toplam = case_manager.get_cases(q="tazminat", hizmet_turu="Danışmanlık", with_total=False)
    assert _idler(kartlar) == {a_id} and toplam == -1


# ═══════════════════════════════════════════════════════════════════════════
# 3. Route — gerçek uygulama, sqlite
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def client(listeli, monkeypatch):
    from starlette.testclient import TestClient

    # `with` bilinçli YOK: lifespan (scheduler, thread'ler) çalışmasın (test_g196 deseni).
    from api import app
    from dependencies import get_current_tenant, get_current_user
    from rate_limiting import limiter
    from services import document_pipeline

    monkeypatch.setattr(document_pipeline, "validate_tenant_and_resolve_lawyer", lambda case_id, user: None)
    user = {"name": "Av. Test Kullanıcı", "preferred_username": "admin@example.com", "tid": "tenant-1"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def test_post_cases_hizmetsiz_muvekkil_422_adiyla(client, listeli, caplog):
    with caplog.at_level(logging.WARNING):
        r = client.post("/api/cases", json={
            "court": "X Mahkemesi",
            "parties": [_muvekkil("Dr. Ali Veli", "Lexis Rapor"), _muvekkil("Ayşe Kaya"), _karsi("Karşı Kurum")],
        })
    assert r.status_code == 422, r.text
    detay = r.json()["detail"]
    assert '"Ayşe Kaya"' in detay and "Dr. Ali Veli" not in detay and "Karşı Kurum" not in detay
    assert "hizmet türü" in detay.lower()
    assert _say(listeli, models.Case) == 0 and _say(listeli, models.OfisNoSayaci) == 0
    assert [rec for rec in caplog.records if rec.levelno >= logging.ERROR] == []


def test_post_cases_hizmetli_kayit_satirlari_yazar(client, listeli):
    r = client.post("/api/cases", json={
        "court": "X Mahkemesi",
        "parties": [
            _muvekkil("Dr. Ali Veli", "Vekaletli Takip"),
            _muvekkil("Ayşe Kaya", "Lexis Rapor", "Danışmanlık"),
            _karsi("Karşı Kurum"),
        ],
    })
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert _satirlar(listeli, cid) == [
        ("Ayşe Kaya", "Danışmanlık", False),
        ("Ayşe Kaya", "Lexis Rapor", False),
        ("Dr. Ali Veli", "Vekaletli Takip", False),
    ]
    kart = client.get(f"/api/cases/{cid}").json()
    assert kart["hizmet_turu"] == "Danışmanlık ; Lexis Rapor ; Vekaletli Takip"
    assert len(kart["hizmetler"]) == 3 and {h["kaynak"] for h in kart["hizmetler"]} == {"elle"}

    # Liste ucu: çok hizmetli kart her hizmet filtresinde; yanıt tarafları hizmet alanı taşımaz
    for hizmet in ("Vekaletli Takip", "Lexis Rapor", "Danışmanlık"):
        liste = client.get("/api/cases", params={"hizmet_turu": hizmet})
        assert [c["id"] for c in liste.json()] == [cid], hizmet
        assert liste.headers["X-Total-Count"] == "1"
        assert all("hizmet_turleri" not in p for p in liste.json()[0]["parties"])


def test_post_cases_gecersiz_hizmet_ve_karsi_tarafta_hizmet_422(client, listeli):
    r = client.post("/api/cases", json={"parties": [_muvekkil("Ali Veli", "Serbest Hizmet")]})
    assert r.status_code == 422, r.text
    assert "Serbest Hizmet" in r.json()["detail"]

    r = client.post("/api/cases", json={"parties": [
        _muvekkil("Ali Veli", "Lexis Rapor"), _karsi("Karşı Kurum", hizmet_turleri=["Lexis Rapor"]),
    ]})
    assert r.status_code == 422, r.text
    assert "Karşı Kurum" in str(r.json()["detail"])
    assert _say(listeli, models.Case) == 0 and _say(listeli, models.CaseHizmeti) == 0


def test_intake_commit_ayni_kapidan_gecer_ve_kaydedeni_imzalar(client, listeli):
    r = client.post("/api/case-intake/commit", json={"case": {
        "court": "X Mahkemesi", "parties": [_muvekkil("Dr. İntake Kişi"), _karsi("Karşı Kurum")],
    }})
    assert r.status_code == 422, r.text
    assert '"Dr. İntake Kişi"' in r.json()["detail"]
    assert _say(listeli, models.Case) == 0

    r = client.post("/api/case-intake/commit", json={"case": {
        "court": "X Mahkemesi",
        "parties": [_muvekkil("Dr. İntake Kişi", "Vekaletli Takip", "Lexis Rapor"), _karsi("Karşı Kurum")],
    }})
    assert r.status_code == 200, r.text
    cid = r.json()["case"]["id"]
    assert _satirlar(listeli, cid) == [
        ("Dr. İntake Kişi", "Lexis Rapor", False),
        ("Dr. İntake Kişi", "Vekaletli Takip", False),
    ]
    assert _hizmet_tarihcesi(listeli, cid) == [
        ("", "Dr. İntake Kişi — Lexis Rapor ; Vekaletli Takip", "Av. Test Kullanıcı", case_manager.PANEL_SOURCE),
    ]


def test_patch_takip_hizmet_turunu_yazmaz_oteki_alanlari_yazar(client, listeli):
    r = client.post("/api/cases", json={"parties": [_muvekkil("Ali Veli", "Lexis Rapor")]})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]

    # Listedeki bir ad da, liste dışı bir ad da yok sayılır — 200, özet türetilmiş hâliyle kalır
    for gonderilen in ("Danışmanlık", "Serbest Hizmet", None):
        r = client.patch(f"/api/cases/{cid}/tracking",
                         json={"hizmet_turu": gonderilen, "dosya_son_durumu": f"durum {gonderilen}"})
        assert r.status_code == 200, (gonderilen, r.text)
        kart = _kart(listeli, cid)
        assert kart.hizmet_turu == "Lexis Rapor", gonderilen
        assert kart.dosya_son_durumu == f"durum {gonderilen}", "öteki alan yazılmalı"
    assert _satirlar(listeli, cid) == [("Ali Veli", "Lexis Rapor", False)]


# ═══════════════════════════════════════════════════════════════════════════
# 4. Gerçek Postgres — scratch DB (yoksa SKIP)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def pg_engine(admin_engine):
    with mig._scratch_database(admin_engine, "g250") as engine:
        mig._run_init_db(engine)
        yield engine


@pytest.fixture()
def pg(pg_engine, monkeypatch):
    from starlette.testclient import TestClient

    # `with` bilinçli YOK: lifespan (scheduler, thread'ler) çalışmasın (test_g196 deseni).
    from api import app
    from dependencies import get_current_tenant, get_current_user
    from rate_limiting import limiter
    from routes import cases as cases_route

    Fabrika = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    monkeypatch.setattr(cases_route, "SessionLocal", Fabrika)
    user = {"name": "Av. Test Kullanıcı", "preferred_username": "admin@example.com", "tid": "tenant-1"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    limiter.reset()
    try:
        yield SimpleNamespace(client=TestClient(app), engine=pg_engine, Fabrika=Fabrika)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def _pg_say(pg, tablo) -> int:
    with pg.engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {tablo}")).scalar()


@pytest.mark.dbtest
def test_pg_kapi_liste_bosken_acik_seedliyken_kapali_ve_satirlar_kartla_yazilir(pg, caplog):
    """Tek akış (scratch DB modül ömürlü — sıra bağımlılığı olmasın diye tek test):
    boş listede kapı açık → liste dolunca hizmetsiz müvekkil 422 (kart yok, sıra geri döner)
    → hizmetli kayıt satırları kartla aynı transaction'da yazar."""
    with pg.engine.connect() as conn:
        tip = conn.execute(text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'cases' AND column_name = 'hizmet_turu'"
        )).scalar()
    assert tip == "text"

    # 1) `service_types` boş (init_db seed koşturmaz): zorunluluk atlanır
    assert _pg_say(pg, "service_types") == 0
    r = pg.client.post("/api/cases", json={"parties": [_muvekkil("G250 Bos Liste")]})
    assert r.status_code == 200, r.text
    assert _pg_say(pg, "cases") == 1 and _pg_say(pg, "case_hizmetleri") == 0

    # 2) Liste doldu (prod'un olağan durumu): hizmetsiz müvekkil 422
    db = pg.Fabrika()
    for sira, (kod, ad) in enumerate(HIZMETLER):
        db.add(models.ServiceType(code=kod, name=ad, active=True, sequence=sira))
    db.commit()
    db.close()
    sayac_once = _pg_say(pg, "ofis_no_sayaclari")
    with caplog.at_level(logging.WARNING):
        r = pg.client.post("/api/cases", json={
            "parties": [_muvekkil("G250 Hizmetli", "Lexis Rapor"), _muvekkil("G250 Hizmetsiz")],
        })
    assert r.status_code == 422, r.text
    assert '"G250 Hizmetsiz"' in r.json()["detail"] and "G250 Hizmetli" not in r.json()["detail"]
    assert _pg_say(pg, "cases") == 1 and _pg_say(pg, "case_parties") == 1
    assert _pg_say(pg, "ofis_no_sayaclari") == sayac_once, "reddedilen istek sıra yakmaz"
    assert [k for k in caplog.records if k.levelno >= logging.ERROR] == []

    # 3) Hizmetli kayıt: iki müvekkil, ayrı kümeler, özet birleşim
    r = pg.client.post("/api/cases", json={
        "parties": [
            _muvekkil("G250 Hizmetli", "Vekaletli Takip", "Lexis Rapor"),
            _muvekkil("G250 Ikinci", "Danışmanlık"),
            _karsi("G250 Karşı"),
        ],
    })
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    with pg.engine.connect() as conn:
        satirlar = conn.execute(text(
            "SELECT p.name, h.hizmet_turu, h.foy_id FROM case_hizmetleri h "
            "JOIN case_parties p ON p.id = h.case_party_id WHERE h.case_id = :c ORDER BY 1, 2"
        ), {"c": cid}).all()
        ozet = conn.execute(text("SELECT hizmet_turu FROM cases WHERE id = :c"), {"c": cid}).scalar()
    assert [tuple(s) for s in satirlar] == [
        ("G250 Hizmetli", "Lexis Rapor", None),
        ("G250 Hizmetli", "Vekaletli Takip", None),
        ("G250 Ikinci", "Danışmanlık", None),
    ]
    assert ozet == "Danışmanlık ; Lexis Rapor ; Vekaletli Takip"

    # Liste filtresi gerçek Postgres'te: çok hizmetli kart her hizmetinde
    for hizmet in ("Lexis Rapor", "Vekaletli Takip", "Danışmanlık"):
        liste = pg.client.get("/api/cases", params={"hizmet_turu": hizmet})
        assert [c["id"] for c in liste.json()] == [cid], hizmet
