"""Kart alanı için hata bildirimi (02.10.2026) — `hata_bildirimleri`.

Kilitlenen davranışlar (sözleşme frontend `lib/hataBildirimleri.ts` ile ORTAK):
  1. POST: dava ve müvekkil hedefi, 201 + satır şekli, bildiren kimliği token'dan,
     trim; doğrulama (hedef tek, içerik zorunlu, uzunluk) 422,
  2. alıcılar: bildiren pencerede seçer (aday listesi: idari personel + iç avukatlar +
     yönetici; listede olmayan adres 422); seçim yoksa varsayılan = `notify_error_reports`
     işaretli alıcılar − bildiren, işaretli yoksa `notify_copy` alıcıları; allowlist dışı
     adres almaz (yönetici hesabı muaf); bildirim `link` taşır,
  3. liste: kayda göre / pano (tümü), `durum=acik|hepsi`, en yeni üstte,
  4. kapat: COZULDU/REDDEDILDI, kapatan kimliği, bildirene `hata_sonucu`, diğer
     alıcıların açılış bildirimi okundu olur; ikinci kapatma 409,
  5. görünürlük: soft-silinmiş / tenant dışı hedef → 404; pano listesinde görünmez,
  6. oturumsuz 401, router kayıtlı,
  7. migrasyon: ("table", ...) + `alicilar` kolon op'u + AYRI koşulsuz ("index", ...) op'u,
     iki FK de index'li,
     `email_recipients.notify_error_reports` ve `notifications.link` kolon op'ları.

DB'siz katman süreç içi sqlite (StaticPool) üzerinde GERÇEK sorgu koşar.
"""
import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database

DOMAIN = "hanyaloglu-acar.av.tr"
T1 = "tenant-hanyaloglu"
T2 = "tenant-baska"
MAIL_AVUKAT = f"avukat@{DOMAIN}"
MAIL_NURTEN = f"nurten@{DOMAIN}"
MAIL_IKINCI = f"ikinci@{DOMAIN}"
MAIL_KOPYA = f"kopya@{DOMAIN}"
USER_AVUKAT = {"tid": T1, "preferred_username": "Avukat@Hanyaloglu-Acar.av.tr", "name": "Av. Ayşe Kaya"}
USER_NURTEN = {"tid": T1, "upn": MAIL_NURTEN, "name": "Nurten Meral"}
USER_T2 = {"tid": T2, "preferred_username": "diger@baska.com"}
MAIL_YONETICI = "ilkekutluk@lexisbio.onmicrosoft.com"
MAIL_IC_AVUKAT = f"serap@{DOMAIN}"

UC = "/api/hata-bildirimleri"


@pytest.fixture()
def env(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from database import Base, get_db
    from dependencies import get_current_user
    import models
    from routes import hata_bildirimleri as route_mod

    monkeypatch.setenv("NOTIFICATION_DOMAINS", DOMAIN)
    monkeypatch.setenv("ADMIN_EMAILS", "")
    monkeypatch.delenv("ADMIN_ADLARI", raising=False)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_ac(dbapi_conn, _rec):  # sqlite'ta FK eylemleri varsayılan KAPALI
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    # Doğrudan düzeltme `enrich_case`ten geçer; o kendi oturumunu açar → aynı sqlite'a bağlanır.
    from managers import case_manager
    monkeypatch.setattr(case_manager, "SessionLocal", maker)

    def _client(user=USER_AVUKAT):
        app = FastAPI()
        app.include_router(route_mod.router)
        if user is not None:
            app.dependency_overrides[get_current_user] = lambda: user

        def _db_override():
            db = maker()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _db_override
        return TestClient(app, raise_server_exceptions=False)

    def _run(fn):
        db = maker()
        try:
            return fn(db)
        finally:
            db.close()

    def _case(tracking_no="DR.A.KAYA-0001-HUK", tenant_id=None, deleted=False, esas_no="2024/55", **alanlar):
        def op(db):
            row = models.Case(
                tracking_no=tracking_no, esas_no=esas_no, status="DERDEST", tenant_id=tenant_id, **alanlar,
                deleted_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc) if deleted else None,
            )
            db.add(row)
            db.commit()
            return int(row.id)
        return _run(op)

    def _muvekkil(name="Dr. Ali Kaya", tenant_id=None, deleted=False):
        def op(db):
            row = models.Client(
                name=name, tenant_id=tenant_id,
                deleted_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc) if deleted else None,
            )
            db.add(row)
            db.commit()
            return int(row.id)
        return _run(op)

    def _alici(name, email, hata=False, kopya=False, active=True, sequence=0):
        def op(db):
            db.add(models.EmailRecipient(
                name=name, email=email, notify_error_reports=hata, notify_copy=kopya,
                active=active, sequence=sequence,
            ))
            db.commit()
        _run(op)

    def _avukat(name, email, gorev="AVUKAT", code=None):
        def op(db):
            db.add(models.Lawyer(code=code or name[:3].upper(), name=name, email=email, gorev=gorev, active=True))
            db.commit()
        _run(op)

    def _bildirimler(tur=None):
        def op(db):
            q = db.query(models.Notification)
            if tur:
                q = q.filter(models.Notification.type == tur)
            return q.order_by(models.Notification.id.asc()).all()
        return _run(op)

    def _satir(bildirim_id):
        return _run(lambda db: db.get(models.HataBildirimi, bildirim_id))

    yield SimpleNamespace(
        client=_client, case=_case, muvekkil=_muvekkil, alici=_alici, avukat=_avukat,
        bildirimler=_bildirimler, satir=_satir, models=models, run=_run,
    )
    engine.dispose()


def _govde(**kw):
    govde = {"alan": "esas_no", "alan_etiketi": "Esas No", "mevcut_deger": "2024/55",
             "dogru_deger": "2024/65", "aciklama": "Esas no yanlış girilmiş."}
    govde.update(kw)
    return govde


# ─── 1. POST ─────────────────────────────────────────────────────────────────

def test_post_dava_201_satir_sekli_ve_bildiren_kimligi(env):
    cid = env.case()

    r = env.client().post(UC, json=_govde(case_id=cid, aciklama="  Esas no yanlış.  "))

    assert r.status_code == 201
    b = r.json()
    assert set(b) == {
        "id", "case_id", "client_id", "hedef_etiketi", "link", "alan", "alan_etiketi",
        "mevcut_deger", "dogru_deger", "aciklama", "durum", "alicilar", "bildiren_ad",
        "bildiren_email", "created_at", "kapatan_ad", "kapatan_email", "kapatma_notu", "kapatildi_at",
    }
    assert b["alicilar"] == [], "alıcı tanımlı değilken liste boş olmalı"
    assert b["case_id"] == cid and b["client_id"] is None
    assert b["durum"] == "ACIK"
    assert b["aciklama"] == "Esas no yanlış."
    assert b["bildiren_email"] == MAIL_AVUKAT, "bildiren e-postası küçük harfe indirgenmedi"
    assert b["bildiren_ad"] == "Av. Ayşe Kaya"
    assert b["hedef_etiketi"] == "DR.A.KAYA-0001-HUK · 2024/55"
    assert b["link"] == f"/cases/{cid}?hata={b['id']}"
    assert dt.datetime.fromisoformat(b["created_at"]).utcoffset() == dt.timedelta(0)
    assert b["kapatildi_at"] is None


def test_post_muvekkil_hedefi(env):
    mid = env.muvekkil("Dr. Ali Kaya")

    r = env.client().post(UC, json=_govde(client_id=mid, alan="phone", alan_etiketi="Telefon"))

    assert r.status_code == 201
    b = r.json()
    assert b["client_id"] == mid and b["case_id"] is None
    assert b["hedef_etiketi"] == "Dr. Ali Kaya"
    assert b["link"] == f"/clients?client={mid}&hata={b['id']}"


@pytest.mark.parametrize("degisen", [
    {"case_id": None},                                   # hedef yok
    {"client_id": 1},                                    # iki hedef birden
    {"dogru_deger": " ", "aciklama": ""},                # içerik yok
    {"alan": "  "},
    {"alan_etiketi": ""},
    {"aciklama": "x" * 2001},
    {"dogru_deger": "x" * 1001},
])
def test_post_gecersiz_govde_422(env, degisen):
    cid = env.case()
    govde = _govde(case_id=cid)
    govde.update(degisen)

    assert env.client().post(UC, json=govde).status_code == 422
    assert env.client().get(UC, params={"case_id": cid}).json() == []


def test_post_yalniz_dogru_deger_ya_da_yalniz_aciklama_yeter(env):
    cid = env.case()
    c = env.client()

    assert c.post(UC, json=_govde(case_id=cid, aciklama=None)).status_code == 201
    assert c.post(UC, json=_govde(case_id=cid, dogru_deger=None, mevcut_deger=None)).status_code == 201


# ─── 2. Alıcılar ─────────────────────────────────────────────────────────────

def test_isaretli_alicilara_bildirim_duser_bildiren_haric(env):
    cid = env.case()
    env.alici("Nurten Meral", MAIL_NURTEN, hata=True)
    env.alici("İkinci Personel", MAIL_IKINCI, hata=True, sequence=1)
    env.alici("Avukatın Kendisi", MAIL_AVUKAT, hata=True, sequence=2)
    env.alici("Kopya Alıcı", MAIL_KOPYA, kopya=True, sequence=3)       # hata bayrağı yok
    env.alici("Dış Adres", "biri@gmail.com", hata=True, sequence=4)    # allowlist dışı
    env.alici("Pasif", f"pasif@{DOMAIN}", hata=True, active=False, sequence=5)

    b = env.client().post(UC, json=_govde(case_id=cid)).json()

    satirlar = env.bildirimler("hata_bildirimi")
    assert [n.recipient_email for n in satirlar] == [MAIL_NURTEN, MAIL_IKINCI]
    n = satirlar[0]
    assert n.title == "Hata bildirimi: Esas No"
    assert n.severity == "warning"
    assert n.case_id == cid
    assert n.link == f"/cases/{cid}?hata={b['id']}"
    assert n.dedupe_key == f"hata:{b['id']}:{MAIL_NURTEN}"
    assert "Av. Ayşe Kaya" in n.body
    assert "2024/55 → Doğrusu: 2024/65" in n.body
    assert "Esas no yanlış girilmiş." in n.body


def test_isaretli_alici_yoksa_kopya_alicilara_duser(env):
    mid = env.muvekkil()
    env.alici("Kopya Alıcı", MAIL_KOPYA, kopya=True)

    b = env.client().post(UC, json=_govde(client_id=mid, alan="phone", alan_etiketi="Telefon")).json()

    satirlar = env.bildirimler("hata_bildirimi")
    assert [n.recipient_email for n in satirlar] == [MAIL_KOPYA]
    assert satirlar[0].case_id is None
    assert satirlar[0].link == f"/clients?client={mid}&hata={b['id']}"
    assert "Müvekkil: Dr. Ali Kaya" in satirlar[0].body


def test_alici_yokken_kayit_yine_acilir(env):
    cid = env.case()

    r = env.client().post(UC, json=_govde(case_id=cid))

    assert r.status_code == 201
    assert env.bildirimler() == []
    assert len(env.client().get(UC, params={"case_id": cid}).json()) == 1


def _havuz(env, monkeypatch):
    """Gerçek havuzun küçüğü: 2 idari, 2 iç avukat (biri yalnız alıcı listesinde), dış avukat, yönetici."""
    monkeypatch.setenv("ADMIN_EMAILS", f"{MAIL_YONETICI}, {MAIL_IC_AVUKAT}")
    env.avukat("Serap Turgal", MAIL_IC_AVUKAT)
    env.avukat("Rana Betül Gümüş Soydeğer", None, code="RBG")          # e-postası yalnız alıcı listesinde
    env.avukat("Dış Avukat", f"dis@{DOMAIN}", gorev="DIŞ AVUKAT", code="DIS")
    env.alici("Nurten Meral", MAIL_NURTEN, hata=True)
    env.alici("Murat Arslan", MAIL_IKINCI, sequence=1)
    env.alici("Av. Rana Betül Gümüş", f"rana@{DOMAIN}", sequence=2)
    env.alici("Av. Serap Turgal", MAIL_IC_AVUKAT, sequence=3)           # avukatla aynı adres → tek satır
    env.alici("İLKE BERK KUTLUK", "ilke@hotmail.com", sequence=4)       # allowlist dışı
    env.alici("Avukatın Kendisi", MAIL_AVUKAT, sequence=5)


def test_aday_listesi_gruplar_sira_ve_istek_sahibi_haric(env, monkeypatch):
    _havuz(env, monkeypatch)

    r = env.client(USER_AVUKAT).get(f"{UC}/alicilar")

    assert r.status_code == 200
    assert [(a["grup"], a["ad"], a["email"], a["varsayilan"]) for a in r.json()] == [
        ("IDARI", "Nurten Meral", MAIL_NURTEN, True),
        ("IDARI", "Murat Arslan", MAIL_IKINCI, False),
        ("AVUKAT", "Serap Turgal", MAIL_IC_AVUKAT, False),
        ("AVUKAT", "Av. Rana Betül Gümüş", f"rana@{DOMAIN}", False),
        ("YONETICI", "Yönetici", MAIL_YONETICI, False),
    ], "dış avukat, allowlist dışı adres ve istek sahibi listede olmamalı; yönetici allowlist'ten muaf"


def test_yonetici_adi_env_den_ve_kendi_listesinde_gorunmez(env, monkeypatch):
    _havuz(env, monkeypatch)
    monkeypatch.setenv("ADMIN_ADLARI", f"{MAIL_YONETICI.upper()} = İlke ; bozuk-parca")

    adaylar = env.client(USER_AVUKAT).get(f"{UC}/alicilar").json()
    assert [a["ad"] for a in adaylar if a["grup"] == "YONETICI"] == ["İlke"]

    yonetici = {"tid": T2, "preferred_username": MAIL_YONETICI, "name": "İlke"}
    kendi = env.client(yonetici).get(f"{UC}/alicilar").json()
    assert MAIL_YONETICI not in [a["email"] for a in kendi]
    assert MAIL_AVUKAT in [a["email"] for a in kendi]


def test_secilen_alicilara_gider_satira_yazilir(env, monkeypatch):
    _havuz(env, monkeypatch)
    monkeypatch.setenv("ADMIN_ADLARI", f"{MAIL_YONETICI}=İlke")
    cid = env.case()

    r = env.client(USER_AVUKAT).post(UC, json=_govde(
        case_id=cid, alicilar=[MAIL_YONETICI.upper(), f" {MAIL_IC_AVUKAT} ", MAIL_YONETICI, MAIL_AVUKAT],
    ))

    assert r.status_code == 201
    assert r.json()["alicilar"] == [
        {"email": MAIL_YONETICI, "ad": "İlke"},
        {"email": MAIL_IC_AVUKAT, "ad": "Serap Turgal"},
    ], "seçim sırası korunur, tekrar ve bildirenin kendisi düşer"
    alanlar = [n.recipient_email for n in env.bildirimler("hata_bildirimi")]
    assert alanlar == [MAIL_YONETICI, MAIL_IC_AVUKAT], "varsayılan (işaretli) alıcı seçilmediyse bildirim ALMAZ"
    liste = env.client(USER_AVUKAT).get(UC, params={"case_id": cid}).json()
    assert [a["ad"] for a in liste[0]["alicilar"]] == ["İlke", "Serap Turgal"]


def test_secim_yoksa_varsayilan_alicilar_satira_yazilir(env, monkeypatch):
    _havuz(env, monkeypatch)
    cid = env.case()

    b = env.client(USER_AVUKAT).post(UC, json=_govde(case_id=cid, alicilar=[])).json()

    assert b["alicilar"] == [{"email": MAIL_NURTEN, "ad": "Nurten Meral"}]
    assert [n.recipient_email for n in env.bildirimler("hata_bildirimi")] == [MAIL_NURTEN]


@pytest.mark.parametrize("secim", [
    ["yabanci@gmail.com"],                      # listede yok
    [f"dis@{DOMAIN}"],                          # dış avukat
    ["ilke@hotmail.com"],                       # allowlist dışı alıcı satırı
    [MAIL_NURTEN, "olmayan@" + DOMAIN],         # biri geçerli olsa da tümü reddedilir
    [MAIL_AVUKAT],                              # yalnız kendisi
    [f"kisi{i}@{DOMAIN}" for i in range(31)],   # tavan
])
def test_gecersiz_alici_secimi_422_kayit_acilmaz(env, monkeypatch, secim):
    _havuz(env, monkeypatch)
    cid = env.case()

    r = env.client(USER_AVUKAT).post(UC, json=_govde(case_id=cid, alicilar=secim))

    assert r.status_code == 422
    assert env.bildirimler() == []
    assert env.client(USER_AVUKAT).get(UC, params={"case_id": cid}).json() == []


def test_bildirim_ucu_link_alanini_yayinlar(env):
    """Zil `link`e gider — routes/notifications._serialize alanı taşımalı."""
    from routes.notifications import _serialize

    cid = env.case()
    env.alici("Nurten Meral", MAIL_NURTEN, hata=True)
    b = env.client().post(UC, json=_govde(case_id=cid)).json()

    assert _serialize(env.bildirimler()[0])["link"] == b["link"]


# ─── 2b. Doğrudan düzeltme (sorumlu avukat / yönetici) ───────────────────────

def _sorumlu_dava(env, **alanlar):
    """USER_AVUKAT'ın sorumlu olduğu dava (ad → ofis e-postası eşleşmesi `lawyers`tan)."""
    env.avukat("Ayşe Kaya", MAIL_AVUKAT)
    return env.case(responsible_lawyer_name="Av. Ayşe Kaya", **alanlar)


def _dogrudan(**kw):
    govde = _govde(dogrudan_duzelt=True, aciklama=None)
    govde.update(kw)
    return govde


def test_dogrudan_alanlar_ucu_sorumluya_ve_yoneticiye_acik(env, monkeypatch):
    from routes.hata_bildirimleri import DOGRUDAN_DUZELTME_ALANLARI

    monkeypatch.setenv("ADMIN_EMAILS", MAIL_YONETICI)
    cid = _sorumlu_dava(env)
    yonetici = {"tid": T1, "preferred_username": MAIL_YONETICI, "name": "İlke"}
    yol = f"{UC}/dogrudan"

    assert env.client(USER_AVUKAT).get(yol, params={"case_id": cid}).json() == {
        "alanlar": list(DOGRUDAN_DUZELTME_ALANLARI)}
    assert env.client(yonetici).get(yol, params={"case_id": cid}).json()["alanlar"] != []
    assert env.client(USER_NURTEN).get(yol, params={"case_id": cid}).json() == {"alanlar": []}
    assert env.client(USER_AVUKAT).get(yol, params={"case_id": 424242}).status_code == 404
    assert env.client(USER_AVUKAT).get(yol).status_code == 422
    assert env.client(user=None).get(yol, params={"case_id": cid}).status_code == 401


def test_dogrudan_alanlar_enrich_yazim_yolunda():
    """Beyaz liste `enrich_case`in yazabildiği alanların alt kümesi olmalı — yoksa
    "düzeltildi" denir ama karta hiçbir şey yazılmaz."""
    from managers.case_manager import ENRICH_FIELDS
    from routes.hata_bildirimleri import DOGRUDAN_DUZELTME_ALANLARI

    assert set(DOGRUDAN_DUZELTME_ALANLARI) <= set(ENRICH_FIELDS)
    # Liste / tarih / tutar / avukat / durum alanları serbest metinle YAZILMAZ.
    assert not set(DOGRUDAN_DUZELTME_ALANLARI) & {
        "court", "subject", "status", "responsible_lawyer_name", "uyap_lawyer_name",
        "opening_date", "maddi_tazminat", "manevi_tazminat", "tracking_no",
    }


def test_dogrudan_duzeltme_karta_yazar_tarihce_dusurur_bildirim_gitmez(env):
    cid = _sorumlu_dava(env)
    env.alici("Nurten Meral", MAIL_NURTEN, hata=True)

    r = env.client(USER_AVUKAT).post(UC, json=_dogrudan(case_id=cid))

    assert r.status_code == 201
    b = r.json()
    assert b["durum"] == "COZULDU"
    assert b["kapatan_email"] == MAIL_AVUKAT and b["bildiren_email"] == MAIL_AVUKAT
    assert b["kapatma_notu"] == "Bildiren tarafından doğrudan düzeltildi."
    assert b["alicilar"] == []
    assert b["hedef_etiketi"] == "DR.A.KAYA-0001-HUK · 2024/65", "künye güncel esas no'yu taşımalı"
    assert env.bildirimler() == [], "doğrudan düzeltmede kimseye bildirim gitmez"

    def kontrol(db):
        case = db.get(env.models.Case, cid)
        tarihce = db.query(env.models.CaseHistory).filter(env.models.CaseHistory.case_id == cid).all()
        esaslar = db.query(env.models.CaseEsasNumber).filter(env.models.CaseEsasNumber.case_id == cid).all()
        return case.esas_no, [(h.field_name, h.old_value, h.new_value, h.changed_by, h.source) for h in tarihce], \
            [(e.esas_no, e.is_current) for e in esaslar]
    esas, tarihce, esaslar = env.run(kontrol)
    assert esas == "2024/65"
    assert tarihce == [("esas_no", "2024/55", "2024/65", "Av. Ayşe Kaya", "HATA_DUZELTME")]
    assert ("2024/65", True) in esaslar, "esas no tek yazma yolundan (sync_current_esas) geçmeli"

    # Açık listede görünmez (kapalı doğdu), "hepsi"nde denetim izi olarak durur.
    c = env.client(USER_AVUKAT)
    assert c.get(UC, params={"case_id": cid}).json() == []
    assert [x["id"] for x in c.get(UC, params={"case_id": cid, "durum": "hepsi"}).json()] == [b["id"]]


def test_dogrudan_duzeltme_bos_alani_doldurur(env):
    cid = _sorumlu_dava(env)

    r = env.client(USER_AVUKAT).post(UC, json=_dogrudan(
        case_id=cid, alan="hukuk_no", alan_etiketi="Hukuk No", mevcut_deger=None, dogru_deger="174491",
    ))

    assert r.status_code == 201
    assert env.run(lambda db: db.get(env.models.Case, cid).hukuk_no) == "174491"


def test_dogrudan_duzeltme_yetkisiz_403_kart_degismez(env):
    cid = _sorumlu_dava(env)

    r = env.client(USER_NURTEN).post(UC, json=_dogrudan(case_id=cid))

    assert r.status_code == 403
    assert env.run(lambda db: db.get(env.models.Case, cid).esas_no) == "2024/55"
    assert env.client(USER_NURTEN).get(UC, params={"case_id": cid, "durum": "hepsi"}).json() == []


@pytest.mark.parametrize("degisen,kod", [
    ({"alan": "court", "alan_etiketi": "Mahkeme"}, 422),          # beyaz liste dışı alan
    ({"alan": "status", "alan_etiketi": "Durum"}, 422),
    ({"mevcut_deger": "2024/50"}, 409),                           # ekran bayat
    ({"dogru_deger": "2024/55"}, 422),                            # değişiklik yok
    ({"dogru_deger": None, "aciklama": "yanlış"}, 422),           # doğru değer yok
    ({"dogru_deger": "x" * 201}, 422),                            # tavan
])
def test_dogrudan_duzeltme_kapilar_hicbir_sey_yazmadan_reddeder(env, degisen, kod):
    cid = _sorumlu_dava(env)

    r = env.client(USER_AVUKAT).post(UC, json=_dogrudan(case_id=cid, **degisen))

    assert r.status_code == kod
    assert env.run(lambda db: db.get(env.models.Case, cid).esas_no) == "2024/55"
    assert env.run(lambda db: db.query(env.models.CaseHistory).count()) == 0
    assert env.client(USER_AVUKAT).get(UC, params={"case_id": cid, "durum": "hepsi"}).json() == []


def test_dogrudan_duzeltme_muvekkilde_yok_422(env, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", MAIL_AVUKAT)
    mid = env.muvekkil()

    r = env.client(USER_AVUKAT).post(UC, json=_dogrudan(
        client_id=mid, alan="phone", alan_etiketi="Telefon", mevcut_deger="1", dogru_deger="2",
    ))

    assert r.status_code == 422


# ─── 3. Liste ────────────────────────────────────────────────────────────────

def test_liste_kayda_gore_ve_pano(env):
    c1, c2 = env.case("DR.A-0001-HUK"), env.case("DR.B-0001-HUK")
    mid = env.muvekkil()
    c = env.client()
    b1 = c.post(UC, json=_govde(case_id=c1)).json()["id"]
    b2 = c.post(UC, json=_govde(case_id=c2, alan="court", alan_etiketi="Mahkeme")).json()["id"]
    b3 = c.post(UC, json=_govde(client_id=mid, alan="phone", alan_etiketi="Telefon")).json()["id"]

    assert [b["id"] for b in c.get(UC, params={"case_id": c1}).json()] == [b1]
    assert [b["id"] for b in c.get(UC, params={"client_id": mid}).json()] == [b3]
    assert [b["id"] for b in c.get(UC).json()] == [b3, b2, b1], "pano: en yeni üstte, tüm hedefler"
    assert c.get(UC, params={"case_id": c1, "client_id": mid}).status_code == 422
    assert c.get(UC, params={"durum": "bozuk"}).status_code == 422


def test_liste_varsayilan_acik_hepsi_kapalilari_da_verir(env):
    cid = env.case()
    c = env.client()
    acik = c.post(UC, json=_govde(case_id=cid)).json()["id"]
    kapali = c.post(UC, json=_govde(case_id=cid, alan="court", alan_etiketi="Mahkeme")).json()["id"]
    assert c.post(f"{UC}/{kapali}/kapat", json={"sonuc": "COZULDU"}).status_code == 200

    assert [b["id"] for b in c.get(UC, params={"case_id": cid}).json()] == [acik]
    assert {b["id"] for b in c.get(UC, params={"case_id": cid, "durum": "hepsi"}).json()} == {acik, kapali}
    assert [b["id"] for b in c.get(UC).json()] == [acik]


# ─── 4. Kapat ────────────────────────────────────────────────────────────────

def test_kapat_cozuldu_bildirene_sonuc_ve_acilis_bildirimleri_okunur(env):
    cid = env.case()
    env.alici("Nurten Meral", MAIL_NURTEN, hata=True)
    env.alici("İkinci Personel", MAIL_IKINCI, hata=True, sequence=1)
    bid = env.client(USER_AVUKAT).post(UC, json=_govde(case_id=cid)).json()["id"]

    r = env.client(USER_NURTEN).post(
        f"{UC}/{bid}/kapat", json={"sonuc": "cozuldu", "kapatma_notu": "  Düzeltildi.  "},
    )

    assert r.status_code == 200
    b = r.json()
    assert b["durum"] == "COZULDU"
    assert b["kapatan_email"] == MAIL_NURTEN and b["kapatan_ad"] == "Nurten Meral"
    assert b["kapatma_notu"] == "Düzeltildi."
    assert dt.datetime.fromisoformat(b["kapatildi_at"]).utcoffset() == dt.timedelta(0)

    acilis = env.bildirimler("hata_bildirimi")
    assert len(acilis) == 2 and all(n.read_at is not None for n in acilis), \
        "çözülen bildirimin açılış satırları okundu işaretlenmeli"
    sonuc = env.bildirimler("hata_sonucu")
    assert [n.recipient_email for n in sonuc] == [MAIL_AVUKAT]
    assert sonuc[0].title == "Hata bildiriminiz düzeltildi"
    assert sonuc[0].link == f"/cases/{cid}?hata={bid}"
    assert "Nurten Meral" in sonuc[0].body and "Düzeltildi." in sonuc[0].body
    assert sonuc[0].read_at is None


def test_kapat_reddedildi_ve_kendi_bildirimini_kapatana_sonuc_yazilmaz(env):
    cid = env.case()
    c = env.client(USER_AVUKAT)
    bid = c.post(UC, json=_govde(case_id=cid)).json()["id"]

    r = c.post(f"{UC}/{bid}/kapat", json={"sonuc": "REDDEDILDI"})

    assert r.status_code == 200 and r.json()["durum"] == "REDDEDILDI"
    assert env.bildirimler("hata_sonucu") == []


def test_ikinci_kapatma_409_ilk_sonuc_korunur(env):
    cid = env.case()
    bid = env.client(USER_AVUKAT).post(UC, json=_govde(case_id=cid)).json()["id"]
    assert env.client(USER_NURTEN).post(f"{UC}/{bid}/kapat", json={"sonuc": "COZULDU"}).status_code == 200

    r = env.client(USER_AVUKAT).post(f"{UC}/{bid}/kapat", json={"sonuc": "REDDEDILDI"})

    assert r.status_code == 409
    satir = env.satir(bid)
    assert satir.durum == "COZULDU" and satir.kapatan_email == MAIL_NURTEN
    assert len(env.bildirimler("hata_sonucu")) == 1


def test_kapat_gecersiz_sonuc_422_olmayan_404(env):
    cid = env.case()
    c = env.client()
    bid = c.post(UC, json=_govde(case_id=cid)).json()["id"]

    assert c.post(f"{UC}/{bid}/kapat", json={"sonuc": "ACIK"}).status_code == 422
    assert c.post(f"{UC}/{bid}/kapat", json={}).status_code == 422
    assert c.post(f"{UC}/999999/kapat", json={"sonuc": "COZULDU"}).status_code == 404
    assert env.satir(bid).durum == "ACIK"


# ─── 5. Görünürlük ───────────────────────────────────────────────────────────

def test_silinmis_ve_olmayan_hedef_404(env):
    silik_dava = env.case("DR.S-0001-HUK", deleted=True)
    silik_muvekkil = env.muvekkil("Silik", deleted=True)
    c = env.client()

    assert c.post(UC, json=_govde(case_id=silik_dava)).status_code == 404
    assert c.post(UC, json=_govde(client_id=silik_muvekkil)).status_code == 404
    assert c.post(UC, json=_govde(case_id=424242)).status_code == 404
    assert c.get(UC, params={"case_id": silik_dava}).status_code == 404
    assert c.get(UC, params={"client_id": 424242}).status_code == 404


def test_tenant_disi_hedef_gorunmez_paylasimli_havuz_gorunur(env):
    kendi = env.case("DR.K-0001-HUK", tenant_id=T1)
    havuz = env.case("DR.H-0001-HUK", tenant_id=None)
    b_kendi = env.client(USER_AVUKAT).post(UC, json=_govde(case_id=kendi)).json()["id"]
    b_havuz = env.client(USER_AVUKAT).post(UC, json=_govde(case_id=havuz)).json()["id"]
    diger = env.client(USER_T2)

    assert diger.post(UC, json=_govde(case_id=kendi)).status_code == 404
    assert diger.get(UC, params={"case_id": kendi}).status_code == 404
    assert diger.post(f"{UC}/{b_kendi}/kapat", json={"sonuc": "COZULDU"}).status_code == 404
    assert [b["id"] for b in diger.get(UC).json()] == [b_havuz], "pano tenant dışı bildirimi sızdırdı"
    assert env.satir(b_kendi).durum == "ACIK"


def test_hedef_sonradan_silinirse_panodan_duser_kapatilamaz(env):
    cid = env.case()
    bid = env.client().post(UC, json=_govde(case_id=cid)).json()["id"]

    def soft_sil(db):
        db.query(env.models.Case).filter(env.models.Case.id == cid).update(
            {"deleted_at": dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)})
        db.commit()
    env.run(soft_sil)
    c = env.client()

    assert c.get(UC).json() == []
    assert c.post(f"{UC}/{bid}/kapat", json={"sonuc": "COZULDU"}).status_code == 404


# ─── 6. Oturum + kayıt ───────────────────────────────────────────────────────

def test_oturumsuz_401(env):
    cid = env.case()
    c = env.client(user=None)

    assert c.get(UC).status_code == 401
    assert c.get(f"{UC}/alicilar").status_code == 401
    assert c.post(UC, json=_govde(case_id=cid)).status_code == 401
    assert c.post(f"{UC}/1/kapat", json={"sonuc": "COZULDU"}).status_code == 401


def _duz_yollar(routes):
    """FastAPI `include_router`ı sarmalar (`_IncludedRouter`) — düzleştir (G081 deseni)."""
    for r in routes:
        ic = getattr(r, "original_router", None)
        if ic is not None:
            yield from _duz_yollar(ic.routes)
            continue
        for method in getattr(r, "methods", []) or []:
            yield (r.path, method)


def test_router_uygulamaya_kayitli():
    from api import app

    yollar = set(_duz_yollar(app.routes))
    assert ("/api/hata-bildirimleri", "GET") in yollar
    assert ("/api/hata-bildirimleri", "POST") in yollar
    assert ("/api/hata-bildirimleri/alicilar", "GET") in yollar
    assert ("/api/hata-bildirimleri/{bildirim_id}/kapat", "POST") in yollar


# ─── 7. Migrasyon + model ────────────────────────────────────────────────────

def test_migrasyon_table_op_ve_ayri_kosulsuz_index_op():
    ops = [op for op in database._MIGRATIONS if op[1] == "hata_bildirimleri"]
    assert [op[0] for op in ops] == ["table", "columns", "index"]

    table_op, columns_op, index_op = ops
    # `alicilar` hem tablo DDL'inde hem (tablosu önceki hâliyle kurulmuş DB için) kolon op'unda.
    assert "alicilar JSON" in table_op[2] and columns_op[2] == {"alicilar": "JSON"}
    assert table_op[2].count("ON DELETE CASCADE") == 2
    assert table_op[3] == [], "index table op'una gömülmemeli (koşullu op tuzağı)"
    ddls = index_op[2]
    # İki FK kolonu da bir index'in İLK kolonu (G043 bekçisi: index'siz FK yok).
    assert any("idx_hata_bildirimleri_case ON hata_bildirimleri (case_id, durum)" in d for d in ddls)
    assert any("idx_hata_bildirimleri_client ON hata_bildirimleri (client_id, durum)" in d for d in ddls)
    assert any("idx_hata_bildirimleri_acik" in d and "WHERE durum = 'ACIK'" in d for d in ddls)
    assert all("IF NOT EXISTS" in d for d in ddls), "index/CHECK op'u idempotent değil"
    assert any("ck_hata_bildirimleri_tek_hedef" in d and "ck_hata_bildirimleri_durum" in d for d in ddls)


def test_migrasyon_kolon_oplari():
    def kolon_op(tablo, kolon):
        return next(
            (op for op in database._MIGRATIONS
             if op[0] == "columns" and op[1] == tablo and kolon in op[2]),
            None,
        )

    alici = kolon_op("email_recipients", "notify_error_reports")
    assert alici is not None and "BOOLEAN" in alici[2]["notify_error_reports"].upper()
    assert kolon_op("notifications", "link") is not None


def test_model_kolonlari_ve_fk_eylemleri():
    import models

    tablo = models.HataBildirimi.__table__
    assert {c.name for c in tablo.columns} == {
        "id", "tenant_id", "case_id", "client_id", "alan", "alan_etiketi", "mevcut_deger",
        "dogru_deger", "aciklama", "durum", "alicilar", "bildiren_email", "bildiren_ad", "created_at",
        "kapatan_email", "kapatan_ad", "kapatma_notu", "kapatildi_at",
    }
    assert {fk.parent.name: (fk.column.table.name, fk.ondelete) for fk in tablo.foreign_keys} == {
        "case_id": ("cases", "CASCADE"),
        "client_id": ("clients", "CASCADE"),
    }
    assert tablo.c.created_at.type.timezone is True and tablo.c.kapatildi_at.type.timezone is True
    assert models.Notification.__table__.c.link.nullable is True


def test_liste_spec_hata_bayragi_duzenlenebilir():
    from managers import reference_lists

    spec = reference_lists._spec("emails")
    assert "notify_error_reports" in spec.fields and "notify_error_reports" in spec.editable
