"""G080 — Bildirim hedefleme: dava → sorumlu avukatın ofis e-postası.

`services/notification_targeting.py` serbest metin `cases.responsible_lawyer_name`
değerini giriş yapabilen kişinin ofis adresine çevirir. Buradaki testler dört şeyi
kilitler:

1. **Allowlist yapısal kapıdır** — 69 dış avukatın kişisel adresi (gmail/hotmail)
   hiçbir eşleşme yolundan dönemez; ofis alan adlı ama `gorev='DIŞ AVUKAT'` olan
   kayıt da dönmez (iki koşul birlikte aranır).
2. **İsim varyantları** — "Av." öneki, TR karakter katlaması, tümü büyük harf,
   avukat kodu ve ";" ile ayrılmış çoklu sorumlu.
3. **İkinci kaynak** — `lawyers`ta olmayan ama ofis adresli idari personel
   (`email_recipients`) çözülür; öncelik yine avukat tablosundadır.
4. **Servis DB'ye YAZMAZ** — çağrı boyunca çalışan SQL'lerde INSERT/UPDATE/DELETE
   olmadığı cursor seviyesinde doğrulanır (sözleşme: yalnız okuma).

DB katmanı in-memory sqlite (StaticPool) — modülün sorguları ORM üzerinden kurulur,
Postgres'e özgü hiçbir yapı kullanılmaz.
"""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from services import notification_targeting as nt

OFIS = "hanyaloglu-acar.av.tr"


@pytest.fixture()
def db(monkeypatch):
    """Boş şema + G080 senaryosunun referans kayıtları."""
    monkeypatch.delenv("NOTIFICATION_DOMAINS", raising=False)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    session.add_all([
        # Giriş yapabilen avukatlar (ölçümde 7 kayıt, hepsi ofis alan adlı)
        models.Lawyer(code="AGH", name="Ayşe Gül Hanyaloğlu", gorev="AVUKAT",
                      email=f"aysegul@{OFIS}", active=True, sequence=0),
        models.Lawyer(code="ST", name="Serap Turgal", gorev="AVUKAT",
                      email=f"Serap.Turgal@{OFIS}".upper(), active=True, sequence=1),
        models.Lawyer(code="TUY", name="Tuğçe Üngör Yanık", gorev="AVUKAT",
                      email=f"tugce@{OFIS}", active=True, sequence=2),
        # Dış avukat: kişisel adres — allowlist dışı
        models.Lawyer(code="DA1", name="Mehmet Dışavukat", gorev="DIŞ AVUKAT",
                      email="mehmet.disavukat@gmail.com", active=True, sequence=3),
        # Dış avukat AMA ofis alan adlı: görev kapısı yine de kapatır
        models.Lawyer(code="DA2", name="Kemal Dışkatip", gorev="DIŞ AVUKAT",
                      email=f"kemal@{OFIS}", active=True, sequence=4),
        # İdari personel: lawyers'ta YOK, e-posta alıcılarında var
        models.EmailRecipient(name="Murat Arslan", email=f"murat.arslan@{OFIS}",
                              active=True, sequence=0),
        models.EmailRecipient(name="Nurten Meral", email=f"nurten@{OFIS}",
                              active=True, sequence=1),
        # Alıcı listesinde duran dış adres — allowlist dışı
        models.EmailRecipient(name="Dış Danışman", email="dis.danisman@hotmail.com",
                              active=True, sequence=2),
    ])
    session.commit()
    yield session
    session.close()


def _case(responsible):
    """Session'a EKLENMEYEN dava nesnesi — çözümleyici yalnız alanı okur."""
    return models.Case(tracking_no="T-1", responsible_lawyer_name=responsible)


# ─── Allowlist ────────────────────────────────────────────────────────────────

def test_allowlist_disi_adres_asla_donmez(db):
    """Kişisel adresli dış avukat adıyla birebir arandığında bile hedef yok."""
    assert nt.resolve_case_recipients(db, _case("Mehmet Dışavukat")) == []
    assert nt.resolve_case_recipients(db, _case("Dış Danışman")) == []


def test_ofis_adresli_dis_avukat_gorev_kapisinda_elenir(db):
    """Alan adı doğru ama gorev='DIŞ AVUKAT' → giriş yapamaz, hedef değildir."""
    assert nt.resolve_case_recipients(db, _case("Kemal Dışkatip")) == []


def test_allowlist_env_ile_genisletilir(db, monkeypatch):
    monkeypatch.setenv("NOTIFICATION_DOMAINS", f"{OFIS}, lexisbio.com.tr")
    assert nt.notification_domains() == (OFIS, "lexisbio.com.tr")
    db.add(models.Lawyer(code="LX", name="Lexis Avukat", gorev="AVUKAT",
                         email="lexis@lexisbio.com.tr", active=True, sequence=9))
    db.commit()
    assert nt.resolve_case_recipients(db, _case("Lexis Avukat")) == ["lexis@lexisbio.com.tr"]


def test_env_bos_ise_varsayilan_ofis_alan_adi(db, monkeypatch):
    monkeypatch.setenv("NOTIFICATION_DOMAINS", "   ")
    assert nt.notification_domains() == nt.DEFAULT_NOTIFICATION_DOMAINS == (OFIS,)


def test_is_allowed_email_bozuk_bicimi_reddeder():
    assert nt.is_allowed_email(f"kimse@{OFIS}") is True
    assert nt.is_allowed_email(f"KIMSE@{OFIS.upper()}") is True
    assert nt.is_allowed_email(None) is False
    assert nt.is_allowed_email("bosluksuz-adres") is False
    assert nt.is_allowed_email(f"a@b@{OFIS}") is False
    # Alt alan adı ofis alan adı DEĞİLDİR (son ek eşleşmesi yok)
    assert nt.is_allowed_email(f"kimse@sahte-{OFIS}") is False


# ─── İsim varyantları ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("yazim", [
    "Serap Turgal",
    "Av. Serap Turgal",
    "SERAP TURGAL",
    "  serap   turgal  ",
    "ST",
])
def test_isim_varyantlari_ayni_hedefe_cozulur(db, yazim):
    assert nt.resolve_case_recipients(db, _case(yazim)) == [f"serap.turgal@{OFIS}"]


def test_tr_karakter_katlamasi(db):
    """'TUGCE UNGOR' (ASCII, büyük harf) ↔ 'Tuğçe Üngör Yanık'."""
    assert nt.resolve_case_recipients(db, _case("TUGCE UNGOR")) == [f"tugce@{OFIS}"]


def test_avukat_kodu_ile_cozulur(db):
    assert nt.resolve_case_recipients(db, _case("AGH")) == [f"aysegul@{OFIS}"]


def test_tek_token_benzersiz_soyad(db):
    assert nt.resolve_case_recipients(db, _case("Hanyaloğlu")) == [f"aysegul@{OFIS}"]


def test_noktali_virgul_iki_alici_dondurur(db):
    assert nt.resolve_case_recipients(db, _case("Tuğçe Üngör Yanık;Serap Turgal")) == [
        f"tugce@{OFIS}", f"serap.turgal@{OFIS}",
    ]


def test_ayni_kisi_iki_kez_yazilmissa_tekillesir(db):
    assert nt.resolve_case_recipients(db, _case("Av. Serap Turgal, SERAP TURGAL")) == [
        f"serap.turgal@{OFIS}",
    ]


def test_cozulen_ve_cozulmeyen_karisik(db):
    """Karışık listede çözülen döner, çözülemeyen sessizce düşer."""
    assert nt.resolve_case_recipients(db, _case("Arşiv Dosya Yöneticisi;Serap Turgal")) == [
        f"serap.turgal@{OFIS}",
    ]


# ─── İkinci kaynak: e-posta alıcıları ─────────────────────────────────────────

def test_idari_personel_email_recipients_uzerinden_cozulur(db):
    """Murat Arslan `lawyers` tablosunda YOK — 294 davası ikinci kaynaktan çözülür."""
    assert nt.resolve_case_recipients(db, _case("Murat Arslan")) == [f"murat.arslan@{OFIS}"]


def test_avukat_tablosu_alici_tablosundan_once_gelir(db):
    """Aynı ad iki tabloda varsa avukat kaydının adresi kazanır."""
    db.add(models.EmailRecipient(name="Serap Turgal", email=f"sekreterlik@{OFIS}",
                                 active=True, sequence=9))
    db.commit()
    assert nt.resolve_case_recipients(db, _case("Serap Turgal")) == [f"serap.turgal@{OFIS}"]


def test_pasif_kayit_hedef_olmaz(db):
    db.query(models.Lawyer).filter(models.Lawyer.code == "TUY").one().active = False
    db.commit()
    assert nt.resolve_case_recipients(db, _case("Tuğçe Üngör Yanık")) == []


# ─── Boş / hedefsiz ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("bos", [None, "", "   ", ";", " ; "])
def test_bos_sorumlu_bos_liste(db, bos):
    assert nt.resolve_recipients(db, bos) == []
    assert nt.resolve_case_recipients(db, _case(bos)) == []


def test_case_none_ise_bos_liste(db):
    assert nt.resolve_case_recipients(db, None) == []


def test_unresolved_targets_ad_ve_dava_sayisi(db):
    for i in range(3):
        db.add(models.Case(tracking_no=f"A-{i}", responsible_lawyer_name="Arşiv Dosya Yöneticisi"))
    db.add(models.Case(tracking_no="A-x", responsible_lawyer_name="ARSIV DOSYA YONETICISI"))
    db.add(models.Case(tracking_no="B-1", responsible_lawyer_name="Asu Barış Karamık"))
    db.add(models.Case(tracking_no="C-1", responsible_lawyer_name="Serap Turgal"))
    db.add(models.Case(tracking_no="D-1", responsible_lawyer_name="Serap Turgal;Asu Barış Karamık"))
    db.commit()

    hedefsiz = nt.unresolved_targets(db)
    assert [h["name"] for h in hedefsiz] == ["ARSIV DOSYA YONETICISI", "Asu Barış Karamık"]
    assert [h["case_count"] for h in hedefsiz] == [4, 2]
    # Çözülen sorumlu listede YOKTUR
    assert all("Turgal" not in h["name"] for h in hedefsiz)


def test_unresolved_targets_silinmis_davayi_saymaz(db):
    from datetime import datetime, timezone

    db.add(models.Case(tracking_no="S-1", responsible_lawyer_name="Arşiv Dosya Yöneticisi"))
    db.add(models.Case(tracking_no="S-2", responsible_lawyer_name="Arşiv Dosya Yöneticisi",
                       deleted_at=datetime.now(timezone.utc)))
    db.commit()
    assert nt.unresolved_targets(db) == [{"name": "Arşiv Dosya Yöneticisi", "case_count": 1}]


# ─── Yazma yasağı ─────────────────────────────────────────────────────────────

def test_servis_dbye_yazmaz(db):
    db.add(models.Case(tracking_no="W-1", responsible_lawyer_name="Arşiv Dosya Yöneticisi"))
    db.commit()

    yazan = []

    def _kaydet(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().split(" ", 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            yazan.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", _kaydet)
    try:
        nt.resolve_case_recipients(db, _case("Serap Turgal"))
        nt.unresolved_targets(db)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _kaydet)

    assert yazan == []
    assert (list(db.new), list(db.dirty), list(db.deleted)) == ([], [], [])
