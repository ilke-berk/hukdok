"""G228 — avukat listesi kurumsal KİMLİKLE yönetilir; kod gizli ve sunucu üretimi; filtre AD eşlemesini korur.

Sözleşme (G229 buna göre yazılır):
- `GET /api/config/lawyers` her kayıtta `kimlik` (`AVK-…`) döner.
- `POST /api/config/lawyers`: `code` opsiyonel ve YOK SAYILIR; sunucu iç kodu ve kimliği üretir; yanıt yeni kaydı döner.
- `PUT|DELETE /api/config/lawyers/{kimlik}` + genel uçlar (`update`, `delete`, `reorder`, `usage`, `rename`)
  `type="lawyers"` için tanımlayıcı olarak kimlik alır; eski kod 1 sürüm geriye uyumlu.
- `GET /api/cases?lawyer=<kimlik>` → kimlik avukat KAYDINI bulur, eşleşme toleranslı AD kurallarıyla koşar.
- Diğer referans listeler (kod anahtarlı) DEĞİŞMEZ.
- Kod artık ad metninde eşleşme token'ı değil (resolver + bildirim + filtre).
- Rapor kataloğu: `belgeler.avukat_kodu` yerine `avukat_adi` (lawyer_id → lawyers.name).

Eski kodda kırmızıdır: `kimlik` yanıtta yoktu, POST `code`'suz 422'ydi, kimlikle PUT/DELETE/genel uçlar 404,
filtre kimliği tanımıyordu, kod token'ı eşleşiyordu, katalogda `avukat_adi` yoktu.
"""
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

import models
from managers import case_manager, lawyer_resolver, reference_lists
from managers.config_manager import DynamicConfig


def _translate(deger, kaynak, hedef):
    if deger is None:
        return None
    return deger.translate(str.maketrans(kaynak, hedef))


@pytest.fixture()
def fabrika(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _baglan(dbapi_connection, _record):
        dbapi_connection.create_function("translate", 3, _translate)
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(reference_lists, "SessionLocal", Fabrika)
    config = DynamicConfig.get_instance()
    onceki = config.get_lawyers()
    yield Fabrika
    config.set_lawyers(onceki)
    engine.dispose()


@pytest.fixture()
def veri(fabrika):
    """Serap (AVK-00001, kod SERAPTUR) · Tuğçe (AVK-00002) · Pasif Kemal (AVK-00003).

    k1: sorumlu metni "Av. Serap Turgal" — YALNIZ adla (case_lawyers yok)
    k2: sorumlu "SERAP TURGAL; Tuğçe Ungör Yanık" (çoklu, yalnız adla)
    k3: sorumlu yalnız "SERAPTUR" (kod biçimli değer — G228'de artık eşleşmez)
    k4: sorumlu "Kemal Pasif" (pasif avukatın kartı)
    """
    db = fabrika()
    serap = models.Lawyer(kimlik="AVK-00001", code="SERAPTUR", name="Serap Turgal", active=True, sequence=1)
    tugce = models.Lawyer(kimlik="AVK-00002", code="TUGCEUNG", name="Tuğçe Ungör Yanık", active=True, sequence=2)
    kemal = models.Lawyer(kimlik="AVK-00003", code="KEMALPAS", name="Kemal Pasif", active=False, sequence=3)
    db.add_all([serap, tugce, kemal])
    db.flush()
    kartlar = [
        models.Case(tracking_no="G228.1", status="DERDEST", responsible_lawyer_name="Av. Serap Turgal"),
        models.Case(tracking_no="G228.2", status="DERDEST",
                    responsible_lawyer_name="SERAP TURGAL; Tuğçe Ungör Yanık"),
        models.Case(tracking_no="G228.3", status="DERDEST", responsible_lawyer_name="SERAPTUR"),
        models.Case(tracking_no="G228.4", status="DERDEST", responsible_lawyer_name="Kemal Pasif"),
    ]
    db.add_all(kartlar)
    db.commit()
    ids = {c.tracking_no: c.id for c in kartlar}
    ids.update({"serap": serap.id, "tugce": tugce.id, "kemal": kemal.id})
    db.close()
    reference_lists.refresh_cache("lawyers")
    return ids


def _avukat(fabrika, kimlik):
    db = fabrika()
    try:
        av = db.query(models.Lawyer).filter_by(kimlik=kimlik).one_or_none()
        return None if av is None else {"code": av.code, "active": av.active, "name": av.name,
                                        "sequence": av.sequence, "email": av.email}
    finally:
        db.close()


@pytest.fixture()
def istemci(fabrika):
    from dependencies import get_current_user
    from routes import config as config_routes

    app = FastAPI()
    app.include_router(config_routes.router)
    kullanici = {"preferred_username": "admin@example.com"}
    app.dependency_overrides[get_current_user] = lambda: kullanici
    app.dependency_overrides[config_routes.require_admin] = lambda: kullanici
    return TestClient(app)


# ── liste tanımı ─────────────────────────────────────────────────────────────

def test_avukat_listesinin_anahtari_kimlik_diger_listeler_kod():
    kayit = reference_lists.LIST_REGISTRY
    assert kayit["lawyers"].key == "kimlik"
    assert "kimlik" in kayit["lawyers"].fields
    assert "kimlik" not in kayit["lawyers"].editable and "code" not in kayit["lawyers"].editable
    for anahtar, spec in kayit.items():
        if anahtar in ("lawyers", "emails"):
            continue
        assert spec.key == "code", anahtar
    assert kayit["emails"].key == "email"


# ── uçlar ────────────────────────────────────────────────────────────────────

def test_get_her_kayitta_kimlik_doner(istemci, veri):
    yanit = istemci.get("/api/config/lawyers")
    assert yanit.status_code == 200
    assert [(lw["kimlik"], lw["name"]) for lw in yanit.json()] == [
        ("AVK-00001", "Serap Turgal"), ("AVK-00002", "Tuğçe Ungör Yanık"),
    ]


def test_post_codesuz_kabul_edilir_sunucu_kod_ve_kimlik_uretir(istemci, fabrika, veri):
    yanit = istemci.post("/api/config/lawyers", json={"name": "Yeni Avukat", "email": "y@x.tr"})
    assert yanit.status_code == 200
    yeni = yanit.json()["lawyer"]
    assert yeni["kimlik"] == "AVK-00004" and yeni["name"] == "Yeni Avukat"
    assert _avukat(fabrika, "AVK-00004")["code"] == "AVK-00004"      # iç kod sunucunun


def test_post_verilen_code_yok_sayilir(istemci, fabrika, veri):
    yanit = istemci.post("/api/config/lawyers", json={"code": "SERAPTUR", "name": "Başka Avukat"})
    assert yanit.status_code == 200                                   # istemci kodu çakışsa da 409 değil
    assert yanit.json()["lawyer"]["kimlik"] == "AVK-00004"
    assert _avukat(fabrika, "AVK-00004")["code"] == "AVK-00004"
    assert _avukat(fabrika, "AVK-00001")["code"] == "SERAPTUR"        # mevcut kayıt etkilenmedi


def test_post_pasif_avukati_yeniden_acinca_ayni_kaydi_doner(istemci, fabrika, veri):
    yanit = istemci.post("/api/config/lawyers", json={"name": "KEMAL PASİF"})
    assert yanit.status_code == 200
    assert yanit.json()["lawyer"]["kimlik"] == "AVK-00003"
    assert _avukat(fabrika, "AVK-00003")["active"] is True


def test_put_ve_delete_kimlikle(istemci, fabrika, veri):
    assert istemci.put("/api/config/lawyers/AVK-00001", json={"email": "s@x.tr"}).status_code == 200
    assert _avukat(fabrika, "AVK-00001")["email"] == "s@x.tr"
    assert istemci.put("/api/config/lawyers/avk-00002", json={"email": "t@x.tr"}).status_code == 200
    assert _avukat(fabrika, "AVK-00002")["email"] == "t@x.tr"          # harf duyarsız
    assert istemci.delete("/api/config/lawyers/AVK-00002").status_code == 200
    assert _avukat(fabrika, "AVK-00002")["active"] is False            # pasif (G225), silinmedi
    assert istemci.delete("/api/config/lawyers/AVK-09999").status_code == 404


def test_genel_uclar_kimlik_alir(istemci, fabrika, veri):
    usage = istemci.get("/api/config/usage", params={"type": "lawyers", "code": "AVK-00001"})
    assert usage.status_code == 200 and usage.json()["name"] == "Serap Turgal"

    yanit = istemci.post("/api/config/update", json={"type": "lawyers", "code": "AVK-00001",
                                                    "fields": {"phone": "555"}})
    assert yanit.status_code == 200

    yanit = istemci.post("/api/config/rename", json={"type": "lawyers", "code": "AVK-00002",
                                                    "name": "Tuğçe Ungör Yanık Demir"})
    assert yanit.status_code == 200
    assert _avukat(fabrika, "AVK-00002")["name"] == "Tuğçe Ungör Yanık Demir"

    yanit = istemci.post("/api/config/reorder", json={"type": "lawyers", "ordered_ids": ["AVK-00002", "AVK-00001"]})
    assert yanit.status_code == 200
    assert _avukat(fabrika, "AVK-00002")["sequence"] == 0 and _avukat(fabrika, "AVK-00001")["sequence"] == 1

    yanit = istemci.post("/api/config/delete", json={"type": "lawyers", "code": "AVK-00001", "mode": "reassign",
                                                    "target_code": "AVK-00002"})
    assert yanit.status_code == 200
    assert _avukat(fabrika, "AVK-00001")["active"] is False


def test_ad_duzeltmesi_kendisiyle_cakismaz(fabrika, veri):
    """Kendisi-hariç kontrolü birincil anahtarla: yalnız harf/diakritik düzeltmesi 409 vermez."""
    assert reference_lists.update_item("lawyers", "AVK-00001", {"name": "SERAP TURGAL"}) is not False
    sonuc = reference_lists.update_item("lawyers", "AVK-00002", {"name": "Tugce Ungor Yanik"})
    assert sonuc and "updated" in sonuc


def test_diger_listeler_degismedi(istemci, fabrika):
    assert istemci.post("/api/config/statuses", json={"name": "Kodsuz"}).status_code == 422
    assert istemci.post("/api/config/statuses", json={"code": "GELEN", "name": "Gelen Belge"}).status_code == 200
    assert istemci.delete("/api/config/statuses/GELEN").status_code == 200
    db = fabrika()
    try:
        assert db.query(models.Status).filter_by(code="GELEN").count() == 0
    finally:
        db.close()


# ── dava listesi filtresi ────────────────────────────────────────────────────

def _filtre(fabrika, secim):
    db = fabrika()
    try:
        return case_manager._lawyer_filter_case_ids(db, secim, None)
    finally:
        db.close()


def test_kimlikle_filtre_yalniz_adla_yazilmis_kartlari_bulur(fabrika, veri):
    beklenen = {veri["G228.1"], veri["G228.2"]}
    assert _filtre(fabrika, "AVK-00001") == beklenen
    assert _filtre(fabrika, "avk-00001") == beklenen
    # Güvence: kimlik yalnız kaydı bulur; sonuç ad seçimi ve (geriye uyum) eski kod seçimiyle AYNI
    assert _filtre(fabrika, "Serap Turgal") == beklenen
    assert _filtre(fabrika, "SERAPTUR") == beklenen


def test_kod_biçimli_kart_metni_artik_eslesmez(fabrika, veri):
    assert veri["G228.3"] not in _filtre(fabrika, "AVK-00001")


def test_pasif_avukatin_kimligi_kartlarini_bulur(fabrika, veri):
    assert "AVK-00003" not in [lw["kimlik"] for lw in DynamicConfig.get_instance().get_lawyers()]
    assert _filtre(fabrika, "AVK-00003") == {veri["G228.4"]}


def test_bilinmeyen_kimlik_bos(fabrika, veri):
    assert _filtre(fabrika, "AVK-09999") == set()


# ── çözümleyici ──────────────────────────────────────────────────────────────

def test_canonicalize_bagi_kimlik_uzerinden_kurar(fabrika, veri, monkeypatch):
    """Önbellekteki kod DB'dekinden farklı olsa da bağ `lawyers.id`'ye kimlikle kurulur."""
    DynamicConfig.get_instance().set_lawyers([
        {"kimlik": "AVK-00001", "code": "ESKIKOD", "name": "Serap Turgal"},
    ])
    db = fabrika()
    try:
        rows, canonical, unresolved = lawyer_resolver.canonicalize_lawyers(db, None, "SERAP TURGAL")
    finally:
        db.close()
    assert rows == [{"name": "Serap Turgal", "lawyer_id": veri["serap"]}]
    assert canonical == "Serap Turgal" and unresolved == []


def test_resolver_kodu_cozmez_kimligi_secimde_tanir(veri):
    assert lawyer_resolver.resolve_lawyer("SERAPTUR") is None
    assert lawyer_resolver.resolve_lawyer("Serap Turgal")["kimlik"] == "AVK-00001"
    core, kod, soyad, tekil = lawyer_resolver._resolve_lawyer_aliases("AVK-00002")
    assert kod == "" and soyad == "yanik" and tekil is True
    assert core == {"tugce", "ungor", "yanik"}


# ── rapor kataloğu ───────────────────────────────────────────────────────────

def test_rapor_belgeler_avukat_adi_kolonu(fabrika, veri):
    from schemas_rapor import RaporTanimi
    from services.rapor import motor, registry

    kolonlar = registry.kaynak_bul("belgeler").kolonlar
    assert "avukat_kodu" not in kolonlar
    assert kolonlar["avukat_adi"].etiket == "Avukat"

    db = fabrika()
    try:
        db.add_all([
            models.CaseDocument(case_id=veri["G228.1"], original_filename="a.pdf", stored_filename="a.pdf", lawyer_id=veri["serap"]),
            models.CaseDocument(case_id=veri["G228.2"], original_filename="b.pdf", stored_filename="b.pdf", lawyer_id=veri["kemal"]),
            models.CaseDocument(case_id=veri["G228.3"], original_filename="c.pdf", stored_filename="c.pdf"),
        ])
        db.commit()
        tanim = RaporTanimi(veri_kaynagi="belgeler", kolonlar=["original_filename", "avukat_adi"],
                            siralama=[{"alan": "original_filename", "yon": "asc"}])
        _, satirlar, toplam = motor.onizle(db, tanim, "t1")
        assert toplam == 3
        assert [(s["original_filename"], s["avukat_adi"]) for s in satirlar] == [
            ("a.pdf", "Serap Turgal"), ("b.pdf", "Kemal Pasif"), ("c.pdf", None),
        ]
        suzulu = RaporTanimi(veri_kaynagi="belgeler", kolonlar=["original_filename"],
                             filtreler=[{"alan": "avukat_adi", "op": "contains", "deger": "serap"}])
        _, satirlar, _ = motor.onizle(db, suzulu, "t1")
        assert [s["original_filename"] for s in satirlar] == ["a.pdf"]
    finally:
        db.close()
