"""G066 — Dört karar durumu alanında kapalı liste doğrulaması (takip yazma yolu).

18.08 boşluk analizinin 3. maddesi: G060 resmi listeleri + G061 dropdown'ı +
G065 yazma yolu geldi ama kapalılık YALNIZ ARAYÜZDEYDİ — `update_case_tracking`
dört karar durumu alanına serbest metin yazıyordu (`case_manager.py` yalnız
yorum taşıyordu). API'yi doğrudan çağıran istediğini yazabiliyordu; tarihçe
yolu (`stage_decisions.add_stage_decision`) ise G062'den beri doğruluyordu —
asimetri bu yüzden doğdu ve iki yol AYNI kolonlara yazıyor.

Bu dosya dört şeyi kilitler:

1. Dördü de reddediyor (asimetri kalmasın): yerel/istinaf/temyiz/karar düzeltme.
2. Kabul + temizleme davranışı G065'teki gibi duruyor (gerileme yok).
3. Karar noktalarının seçimi: `active` filtresi YOK (tarihçeyle simetri),
   liste BOŞSA doğrulama atlanır (tarihçeden bilinçli ayrışma).
4. Ret istemciye 400 dönüyor (500 değil, G003 durum kodu disiplini) ve mesaj
   hangi aşama/liste olduğunu söylüyor.

Gerçek DB'ye bağlanan test YOK: in-memory sqlite + StaticPool (G060/G065
deseni) — üç ortam (lokal konteyner / deploy kapısı / CI çıplak postgres)
aynı davranır.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from managers import case_manager, stage_decisions
from managers.seed_data import (
    APPEAL_DECISIONS,
    CASSATION_DECISIONS,
    LOCAL_DECISIONS,
    REVISION_DECISIONS,
)
from managers.stage_decisions import (
    DECISION_STATUS_COLUMNS,
    InvalidDecisionStatusError,
    validated_status_for_column,
)
from schemas import CaseTrackingUpdate

_KARAR_LISTELERI = [
    (models.LocalDecision, LOCAL_DECISIONS),
    (models.AppealDecision, APPEAL_DECISIONS),
    (models.CassationDecision, CASSATION_DECISIONS),
    (models.RevisionDecision, REVISION_DECISIONS),
]

# (kolon, geçerli değer, liste dışı değer) — dört alan da AYRI test edilir.
DORT_ALAN = [
    ("yerel_karar_durumu", "Beraat", "Lexis Rapor Gönderildi"),
    ("istinaf_karar_durumu", "Başvuru Ret", "Kısmen Kabul"),
    ("temyiz_karar_durumu", "Onama", "usulden red"),
    ("karar_duzeltme_durumu", "Karar Düzeltme Ret", "Lehe"),
]


def _route_dump(payload: dict) -> dict:
    """Route'un yaptığı dönüşümün birebir kopyası (G065 deseni)."""
    return CaseTrackingUpdate.model_validate(payload).model_dump(exclude_unset=True)


# ═══════════════════════════════════════════════════════════════════════════
# 1. DB'siz — kolon→aşama haritası TÜRETİLMİŞ (üçüncü kopya yok)
# ═══════════════════════════════════════════════════════════════════════════

def test_harita_dort_alani_kapsiyor():
    assert DECISION_STATUS_COLUMNS == {
        "yerel_karar_durumu": "YEREL",
        "istinaf_karar_durumu": "ISTINAF",
        "temyiz_karar_durumu": "TEMYIZ",
        "karar_duzeltme_durumu": "KARAR_DUZELTME",
    }


def test_harita_photo_columnsdan_turetiliyor():
    """Görev kuralı: üçüncü bir eşleme kopyası çıkarılmayacak. Harita
    `_PHOTO_COLUMNS`ın karar_durumu satırlarından doğar — kaynak değişirse
    doğrulama kendiliğinden uyar (elle senkron borcu yok)."""
    beklenen = {
        kolonlar["karar_durumu"]: stage
        for stage, kolonlar in stage_decisions._PHOTO_COLUMNS.items()
        if "karar_durumu" in kolonlar
    }
    assert DECISION_STATUS_COLUMNS == beklenen
    # Her aşamanın bir de resmi listesi olmalı (G060 bağı kopmasın)
    for stage in DECISION_STATUS_COLUMNS.values():
        assert stage in stage_decisions.STAGE_DECISION_LISTS


def test_hata_tipi_valueerror_alt_sinifi():
    """G062'nin `pytest.raises(ValueError)` kilitleri kırılmasın diye alt sınıf."""
    assert issubclass(InvalidDecisionStatusError, ValueError)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Kolon kapısı — sqlite (seed'li listeler)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def oturum_fabrikasi(monkeypatch):
    """In-memory sqlite + G060 seed'leri; `case_manager.SessionLocal` bağlanır."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine)
    db = Fabrika()
    try:
        for model, degerler in _KARAR_LISTELERI:
            for idx, (code, name) in enumerate(degerler):
                db.add(model(code=code, name=name, active=True, sequence=idx))
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    yield Fabrika
    engine.dispose()


@pytest.fixture()
def bos_liste_fabrikasi(monkeypatch):
    """Aynı şema, HİÇBİR karar listesi seed'lenmemiş (seed koşmamış kurulum)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine)
    monkeypatch.setattr(case_manager, "SessionLocal", Fabrika)
    yield Fabrika
    engine.dispose()


def _dava_ekle(Fabrika, tracking_no="HA.X.9066.2026", **alanlar) -> int:
    db = Fabrika()
    try:
        case = models.Case(tracking_no=tracking_no, status="DERDEST",
                           maddi_tazminat=0, manevi_tazminat=0, **alanlar)
        db.add(case)
        db.commit()
        return case.id
    finally:
        db.close()


def _oku(Fabrika, case_id: int, alan: str):
    db = Fabrika()
    try:
        return getattr(db.get(models.Case, case_id), alan)
    finally:
        db.close()


def test_kolon_kapisi_karar_durumu_olmayani_gecirir(oturum_fabrikasi):
    """Whitelist döngüsü her alanı kapıdan geçirir; ilgisiz alan DEĞİŞMEDEN döner
    (boşluk normalizasyonu bile uygulanmaz — o alanların sözleşmesi bu değil)."""
    db = oturum_fabrikasi()
    try:
        assert validated_status_for_column(db, "istinaf_mahkemesi", "  BAM   3. HD ") == "  BAM   3. HD "
        assert validated_status_for_column(db, "karar_turu", "Kabul") == "Kabul"
        assert validated_status_for_column(db, "case_stage", None) is None
    finally:
        db.close()


def test_kolon_kapisi_bosluk_normalize_ediyor(oturum_fabrikasi):
    """Kabul kriteri: normalizasyon `_validated_karar_durumu` ile AYNI —
    baştaki/sondaki ve İÇTEKİ fazla boşluklar sadeleşir, sonra ada göre eşleşir."""
    db = oturum_fabrikasi()
    try:
        assert validated_status_for_column(
            db, "istinaf_karar_durumu", "  Kaldırma/Yeniden   Hüküm  "
        ) == "Kaldırma/Yeniden Hüküm"
        # Boş/boşluk-yalnızca değer alanı TEMİZLER (None)
        assert validated_status_for_column(db, "yerel_karar_durumu", "   ") is None
        assert validated_status_for_column(db, "yerel_karar_durumu", None) is None
    finally:
        db.close()


def test_kolon_kapisi_pasif_degeri_kabul_ediyor(oturum_fabrikasi):
    """Karar noktası 2 KİLİDİ: `active` filtresi YOK (tarihçeyle simetri).
    Dropdown'dan kaldırılmış bir değer, tarihçe yolundan kabul edilirken takip
    yolundan reddedilseydi aynı kolonda iki farklı kural olurdu."""
    db = oturum_fabrikasi()
    try:
        db.query(models.CassationDecision).filter_by(name="Bozma").update({"active": False})
        db.commit()
        assert validated_status_for_column(db, "temyiz_karar_durumu", "Bozma") == "Bozma"
    finally:
        db.close()


def test_kolon_kapisi_bos_listede_dogrulamayi_atliyor(bos_liste_fabrikasi, caplog):
    """Karar noktası 3 KİLİDİ: liste boşsa doğrulama devre dışı — ama SESSİZ
    değil (WARNING, log sözleşmesi). Tarihçe yolundan bilinçli ayrışma:
    seed'i koşmamış bir kurulumda takip paneli veri girilemez hâle gelmemeli."""
    db = bos_liste_fabrikasi()
    try:
        with caplog.at_level("WARNING"):
            assert validated_status_for_column(
                db, "yerel_karar_durumu", "  Ne Olduğu   Belirsiz "
            ) == "Ne Olduğu Belirsiz"
        assert any("local_decisions" in r.message and "BOŞ" in r.message
                   for r in caplog.records)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Uçtan uca — update_case_tracking (dört alan AYRI AYRI)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("alan,gecerli,liste_disi", DORT_ALAN)
def test_liste_disi_deger_reddediliyor(oturum_fabrikasi, alan, gecerli, liste_disi):
    """Kırmızı-yeşil kanıtı: eski kodda bu çağrı True dönüp değeri YAZIYORDU."""
    cid = _dava_ekle(oturum_fabrikasi)
    with pytest.raises(InvalidDecisionStatusError):
        case_manager.update_case_tracking(
            cid, _route_dump({alan: liste_disi}), changed_by="g066-test"
        )
    assert _oku(oturum_fabrikasi, cid, alan) is None


@pytest.mark.parametrize("alan,gecerli,liste_disi", DORT_ALAN)
def test_listedeki_deger_yazilabiliyor(oturum_fabrikasi, alan, gecerli, liste_disi):
    cid = _dava_ekle(oturum_fabrikasi)
    assert case_manager.update_case_tracking(
        cid, _route_dump({alan: gecerli}), changed_by="g066-test"
    ) is True
    assert _oku(oturum_fabrikasi, cid, alan) == gecerli


@pytest.mark.parametrize("alan,gecerli,liste_disi", DORT_ALAN)
def test_null_gonderimi_alani_temizliyor(oturum_fabrikasi, alan, gecerli, liste_disi):
    """G065'in kilitlediği davranış korunur: None GÖNDERİLEN alan silinir."""
    cid = _dava_ekle(oturum_fabrikasi, **{alan: gecerli})
    assert case_manager.update_case_tracking(
        cid, _route_dump({alan: None}), changed_by="g066-test"
    ) is True
    assert _oku(oturum_fabrikasi, cid, alan) is None


def test_ret_kismi_yazim_birakmiyor(oturum_fabrikasi):
    """Doğrulama YAZIMDAN ÖNCE toptan koşar: aynı gövdede bir geçerli + bir
    liste dışı değer varsa HİÇBİRİ yazılmaz (yarım kaydedilmiş takip formu
    kullanıcıya 'kaydedilmedi' der ama veriyi değiştirmiş olurdu)."""
    cid = _dava_ekle(oturum_fabrikasi)
    with pytest.raises(InvalidDecisionStatusError):
        case_manager.update_case_tracking(
            cid,
            _route_dump({"yerel_karar_durumu": "Beraat",
                         "temyiz_karar_durumu": "Kısmen Bozma"}),
            changed_by="g066-test",
        )
    assert _oku(oturum_fabrikasi, cid, "yerel_karar_durumu") is None
    assert _oku(oturum_fabrikasi, cid, "temyiz_karar_durumu") is None


def test_diger_takip_alanlari_ve_whitelist_disi_davranisi_degismedi(oturum_fabrikasi):
    """Korunum: (1) karar durumu OLMAYAN takip alanları eskisi gibi yazılır,
    (2) whitelist dışı `tracking_no` ham dict'le gelse de YAZILMAZ (G065 kilidi)."""
    cid = _dava_ekle(oturum_fabrikasi)
    assert case_manager.update_case_tracking(
        cid,
        {"tracking_no": "HACK", "istinaf_mahkemesi": "BAM 3. HD",
         "karar_turu": "Kabul", "yerel_karar_durumu": "Beraat"},
        changed_by="g066-test",
    ) is True
    db = oturum_fabrikasi()
    try:
        case = db.get(models.Case, cid)
        assert case.tracking_no == "HA.X.9066.2026"   # whitelist dışı — dokunulmadı
        assert case.istinaf_mahkemesi == "BAM 3. HD"
        assert case.karar_turu == "Kabul"             # kapalı listeye BAĞLI DEĞİL (G060)
        assert case.yerel_karar_durumu == "Beraat"
    finally:
        db.close()


def test_bos_listeli_kurulumda_yazim_engellenmiyor(bos_liste_fabrikasi):
    """Karar noktası 3'ün uçtan uca karşılığı — ve G065 testlerinin (seed'siz
    sqlite) neden yeşil kaldığının kanıtı."""
    cid = _dava_ekle(bos_liste_fabrikasi)
    assert case_manager.update_case_tracking(
        cid, _route_dump({"yerel_karar_durumu": "Red/Esastan"}), changed_by="g066-test"
    ) is True
    assert _oku(bos_liste_fabrikasi, cid, "yerel_karar_durumu") == "Red/Esastan"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Tarihçe yolu DEĞİŞMEDİ + fotoğraf senkronu yeni kapıya takılmıyor
# ═══════════════════════════════════════════════════════════════════════════

def test_tarihce_yolu_hala_reddediyor(oturum_fabrikasi):
    """G062 sözleşmesi aynen duruyor (mesaj metni dahil); tek fark hata TİPİ,
    o da ValueError alt sınıfı olduğu için mevcut kilitleri kırmıyor."""
    db = oturum_fabrikasi()
    try:
        case = models.Case(tracking_no="HA.X.9067.2026", status="DERDEST",
                           maddi_tazminat=0, manevi_tazminat=0)
        db.add(case)
        db.commit()
        with pytest.raises(ValueError, match="geçersiz karar durumu"):
            stage_decisions.add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Kısmen Bozma")
    finally:
        db.close()


def test_fotograf_senkronunun_yazdigi_deger_takip_kapisindan_geciyor(oturum_fabrikasi):
    """Aynı kolona yazan iki yol çelişmiyor: tarihçeden gelen "son aşama
    fotoğrafı" değeri, arkasından takip paneli aynı değeri gönderse de kabul
    edilir (fotoğraf senkronunun kendisi bu kapıdan geçmez — değeri zaten
    tarihçe yazımında doğrulanmıştır)."""
    db = oturum_fabrikasi()
    try:
        case = models.Case(tracking_no="HA.X.9068.2026", status="DERDEST",
                           maddi_tazminat=0, manevi_tazminat=0)
        db.add(case)
        db.commit()
        stage_decisions.add_stage_decision(db, case, stage="TEMYIZ", karar_durumu="Bozma")
        db.commit()
        cid = case.id
        assert case.temyiz_karar_durumu == "Bozma"   # fotoğraf yazıldı
    finally:
        db.close()

    assert case_manager.update_case_tracking(
        cid, _route_dump({"temyiz_karar_durumu": "Bozma"}), changed_by="g066-test"
    ) is True
    assert _oku(oturum_fabrikasi, cid, "temyiz_karar_durumu") == "Bozma"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Route katmanı — ret 400 (500 DEĞİL)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def client(oturum_fabrikasi):
    from starlette.testclient import TestClient

    # `with` bilinçli YOK: lifespan (scheduler, thread'ler) çalışmasın
    # (test_faz5_status_codes deseni).
    from api import app
    from dependencies import get_current_tenant, get_current_user
    from rate_limiting import limiter

    user = {"name": "Test", "preferred_username": "admin@example.com", "tid": "tenant-1"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def test_route_liste_disi_degeri_400_donuyor(client, oturum_fabrikasi):
    cid = _dava_ekle(oturum_fabrikasi)
    resp = client.patch(f"/api/cases/{cid}/tracking",
                        json={"istinaf_karar_durumu": "Kısmen Kabul"})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "ISTINAF" in detail                 # hangi aşama
    assert "appeal_decisions" in detail        # hangi liste
    assert "Kısmen Kabul" in detail            # hangi değer
    assert _oku(oturum_fabrikasi, cid, "istinaf_karar_durumu") is None


def test_route_gecerli_deger_200_donuyor(client, oturum_fabrikasi):
    cid = _dava_ekle(oturum_fabrikasi)
    resp = client.patch(f"/api/cases/{cid}/tracking",
                        json={"istinaf_karar_durumu": "Kaldırma"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert _oku(oturum_fabrikasi, cid, "istinaf_karar_durumu") == "Kaldırma"


def test_route_olmayan_dava_hala_404(client, oturum_fabrikasi):
    """Gerileme kapısı: yeni 400 yolu, "dava yok" 404'ünü yutmadı."""
    resp = client.patch("/api/cases/999999/tracking", json={"karar_turu": "Kabul"})
    assert resp.status_code == 404


def test_handler_kayitli():
    from api import app

    assert InvalidDecisionStatusError in app.exception_handlers
