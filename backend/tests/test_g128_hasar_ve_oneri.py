"""G128 — Hasar numarası dedektörü + aynı hasta/doktor öneri katmanı (06.09.2026).

Lokal ölçüm (05.09): hasar numarası 237 çift, 61'i TKU'da yok; hasta + doktor (kişi)
1.176 çift, 648'i TKU'suz. Kurallar: hasar kesin (otomatik listede, gerekçeli);
hasta + doktor ÖNERİ (ayrı liste, otomatik bağlanmaz, Bağla/Reddet); sigorta/kurum
adı doktor sayılmaz; reddedilen (ONERI_RED) ve zaten bağlı kartlar önerilmez.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from services import case_relations_auto as ilis

TENANT = "tenant-hanyaloglu"


@pytest.fixture
def oturum():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()
    engine.dispose()


def _kart(db, tracking_no, *, muvekkil=(), karsi=(), ucuncu=(), **alanlar):
    case = models.Case(tracking_no=tracking_no, status="DERDEST", **alanlar)
    db.add(case)
    db.flush()
    for ad in muvekkil:
        case.parties.append(models.CaseParty(name=ad, role="Müvekkil", party_type="CLIENT"))
    for ad in karsi:
        case.parties.append(models.CaseParty(name=ad, role="Davacı", party_type="COUNTER"))
    for ad in ucuncu:
        case.parties.append(models.CaseParty(name=ad, role="Sigortalı", party_type="THIRD"))
    db.commit()
    return case


# ── Hasar numarası ────────────────────────────────────────────────────────

def test_hasar_parcalari_cok_degerli_ve_yer_tutucusuz():
    assert ilis.hasar_parcalari("3509162150001; 20144520004 ;0;-") == {"3509162150001", "20144520004"}
    assert ilis.hasar_parcalari(None) == set() and ilis.hasar_parcalari("0") == set()


def test_hasar_dedektoru_tkusuz_kartlari_bagliyor(oturum):
    a = _kart(oturum, "S1.AK.........0001.HUKUK.00000", file_type="Hukuk", hasar_dosya_no="3509162150001")
    b = _kart(oturum, "S1.AK.........0002.ICRAA.00000", file_type="İcra")
    oturum.add(models.CaseFoy(sistem_no="H-1", case_id=b.id, hasar_no="20144520004;3509162150001"))
    c = _kart(oturum, "S1.AK.........0003.HUKUK.00000", file_type="Hukuk", hasar_dosya_no="9162150")  # alt dizi, EŞLEŞMEZ
    oturum.commit()

    sonuc = ilis.iliskileri_bul(oturum, a, TENANT)

    assert [(k.id, tur) for k, tur, _, _ in sonuc] == [(b.id, ilis.ICRA_PARALEL)]
    assert "aynı hasar dosya no (3509162150001)" in sonuc[0][2]
    assert c.id not in {k.id for k, *_ in sonuc}


def test_kapsam_disi_foyun_hasari_baglamaz(oturum):
    a = _kart(oturum, "A.1", file_type="Hukuk", hasar_dosya_no="1234567")
    b = _kart(oturum, "B.1", file_type="Hukuk")
    oturum.add(models.CaseFoy(sistem_no="H-2", case_id=b.id, hasar_no="1234567", kapsam_durumu="SILINDI"))
    oturum.commit()
    assert ilis.iliskileri_bul(oturum, a, TENANT) == []


# ── Öneri: aynı hasta + aynı doktor ───────────────────────────────────────

def test_kisi_anahtari_kurum_ve_sigortayi_eler():
    assert ilis.kisi_anahtari("Oktay Erdener Dr.") == ilis.kisi_anahtari("OKTAY ERDENER")
    assert ilis.kisi_anahtari("Axa Sigorta A.Ş.") == ""
    assert ilis.kisi_anahtari("Sağlık Bakanlığı") == ""
    assert ilis.kisi_anahtari("İstanbul Valiliği") == ""
    assert ilis.kisi_anahtari("Ali") == ""                         # çok kısa


def test_oneri_ayni_hasta_ve_doktor_bulur_sigorta_uzerinden_bulmaz(oturum):
    kaynak = _kart(oturum, "D1.O_ERDENER..0003.HUKUK.00000", file_type="Hukuk",
                   muvekkil=("Oktay Erdener Dr.", "Axa Sigorta A.Ş."), karsi=("Semra Kurt", "Murat Kurt"))
    ayni_vaka = _kart(oturum, "D1.O_ERDENER..0007.ICRAA.00000", file_type="İcra",
                      muvekkil=("OKTAY ERDENER",), karsi=("SEMRA KURT",))
    ayni_hasta_baska_doktor = _kart(oturum, "S3.AXA........0001.HUKUK.00000", file_type="Hukuk",
                                    muvekkil=("Axa Sigorta A.Ş.",), karsi=("Semra Kurt",))   # yalnız sigorta ortak
    sigortali_doktor = _kart(oturum, "S3.AXA........0002.IDARE.00000", file_type="İdare",
                             muvekkil=("Axa Sigorta A.Ş.",), ucuncu=("Oktay Erdener",), karsi=("Semra Kurt",))
    _kart(oturum, "D1.X_Y........0001.HUKUK.00000", file_type="Hukuk",
          muvekkil=("Oktay Erdener",), karsi=("Ayşe Yılmaz",))                              # başka hasta

    sonuc = ilis.onerileri_bul(oturum, kaynak, TENANT)

    idler = {k.id for k, *_ in sonuc}
    assert idler == {ayni_vaka.id, sigortali_doktor.id}
    assert ayni_hasta_baska_doktor.id not in idler
    turler = {k.id: tur for k, tur, _, _ in sonuc}
    assert turler[ayni_vaka.id] == ilis.ICRA_PARALEL and turler[sigortali_doktor.id] == ilis.ADLI_IDARI_PARALEL
    gerekce = next(g for k, _, g, _ in sonuc if k.id == ayni_vaka.id)
    assert "Semra Kurt" in gerekce and "Oktay Erdener" in gerekce and "onay bekler" in gerekce
    # kaynak karşı tarafında Semra + Murat Kurt: aile soyadı sinyali (+10) her adayda
    assert all(p == ilis.ONERI_PUANI + ilis.SOYADI_PUANI for _, _, _, p in sonuc)


def test_oneri_haric_tutulanlari_ve_reddedileni_atlar(oturum):
    kaynak = _kart(oturum, "A.1", file_type="Hukuk", muvekkil=("Oktay Erdener",), karsi=("Semra Kurt",))
    b = _kart(oturum, "B.1", file_type="İcra", muvekkil=("Oktay Erdener",), karsi=("Semra Kurt",))
    c = _kart(oturum, "C.1", file_type="Ceza", muvekkil=("Oktay Erdener",), karsi=("Semra Kurt",))
    oturum.add(models.CaseRelation(source_case_id=kaynak.id, target_case_id=c.id, relation_type=ilis.ONERI_RED))
    oturum.commit()

    assert {k.id for k, *_ in ilis.onerileri_bul(oturum, kaynak, TENANT)} == {b.id, c.id}   # servis ham
    # route reddedileni ve elle bağlıyı `haric_idler` ile düşürür
    assert {k.id for k, *_ in ilis.onerileri_bul(oturum, kaynak, TENANT, {c.id})} == {b.id}


def test_oneri_hasta_ya_da_doktor_yoksa_bos(oturum):
    yalniz_sigorta = _kart(oturum, "S3.AXA........0009.HUKUK.00000", file_type="Hukuk",
                           muvekkil=("Axa Sigorta A.Ş.",), karsi=("Semra Kurt",))
    _kart(oturum, "S3.AXA........0010.HUKUK.00000", file_type="Hukuk",
          muvekkil=("Axa Sigorta A.Ş.",), karsi=("Semra Kurt",))
    assert ilis.onerileri_bul(oturum, yalniz_sigorta, TENANT) == []


# ── Üçüncü kademe (G129): tıbbi olay + aile soyadı puanı ──────────────────

def _ozet_kart(**alanlar):
    class K:
        pass
    k = K()
    k.tibbi_olay = alanlar.get("tibbi_olay")
    k.parties = [type("P", (), {"party_type": t, "name": n})() for t, n in alanlar.get("parties", [])]
    return k


def test_destekleyici_sinyaller_tibbi_olay_ve_aile_soyadi():
    kaynak = _ozet_kart(tibbi_olay="Omuz Distosisi ; Asfiksik Doğum",
                        parties=[("COUNTER", "Semra Kurt"), ("COUNTER", "Murat Kurt")])
    aday = _ozet_kart(tibbi_olay="asfiksik doğum", parties=[("COUNTER", "Semra Kurt")])
    puan, ekler = ilis.destekleyici_sinyaller(kaynak, aday)
    assert puan == ilis.TIBBI_OLAY_PUANI + ilis.SOYADI_PUANI
    assert ekler == ["aynı tıbbi olay (Asfiksik Doğum)", "ortak aile soyadı (Kurt)"]


def test_tek_kisinin_soyadi_aile_sinyali_degildir():
    """Hasta eşleşmesinin kendisi soyadı sinyali sayılmaz: iki kartta da yalnız
    'Semra Kurt' varsa aile kümesi yok, puan 0."""
    kaynak = _ozet_kart(parties=[("COUNTER", "Semra Kurt")])
    aday = _ozet_kart(parties=[("COUNTER", "Semra Kurt")])
    assert ilis.destekleyici_sinyaller(kaynak, aday) == (0, [])
    # kurum karşı taraf soyadı üretmez
    kurum = _ozet_kart(parties=[("COUNTER", "Sağlık Bakanlığı")])
    assert ilis.destekleyici_sinyaller(kurum, kurum) == (0, [])


def test_ucuncu_kademe_puani_artirir_ve_siralar_ama_tek_basina_oneri_uretmez(oturum):
    kaynak = _kart(oturum, "A.1", file_type="Hukuk", tibbi_olay="Omuz Distosisi",
                   muvekkil=("Oktay Erdener",), karsi=("Semra Kurt",))
    zayif = _kart(oturum, "B.1", file_type="İcra", muvekkil=("Oktay Erdener",), karsi=("Semra Kurt",))
    guclu = _kart(oturum, "C.1", file_type="Ceza", tibbi_olay="omuz distosisi ; Kırık",
                  muvekkil=("Oktay Erdener",), karsi=("Semra Kurt", "Ayşe Kurt"))
    _kart(oturum, "D.1", file_type="Hukuk", tibbi_olay="Omuz Distosisi",
          muvekkil=("Oktay Erdener",), karsi=("Ali Veli",))           # olay aynı ama hasta yok → öneri YOK

    sonuc = ilis.onerileri_bul(oturum, kaynak, TENANT)

    assert [(k.id, p) for k, _, _, p in sonuc] == [(guclu.id, 75), (zayif.id, 50)]   # puana göre sıralı
    gerekce = sonuc[0][2]
    assert "+ aynı tıbbi olay (Omuz Distosisi)" in gerekce and "+ ortak aile soyadı (Kurt)" in gerekce
    assert "+" not in sonuc[1][2].split("—")[0].replace("Aynı hasta (Semra Kurt) + aynı doktor (Oktay Erdener)", "")


# ── Route: reddet + suggested ─────────────────────────────────────────────

def test_route_reddet_oneri_red_yazar_ve_listeden_dusurur(oturum, monkeypatch):
    from fastapi import HTTPException

    from routes import cases as rc
    from schemas import CaseRelationReject

    monkeypatch.setattr(rc, "SessionLocal", lambda: oturum)
    kaynak = _kart(oturum, "A.1", file_type="Hukuk", muvekkil=("Oktay Erdener",), karsi=("Semra Kurt",),
                   tenant_id=TENANT)
    b = _kart(oturum, "B.1", file_type="İcra", muvekkil=("Oktay Erdener",), karsi=("Semra Kurt",),
              tenant_id=TENANT)
    user = {"name": "Test Avukat"}

    once = rc.get_case_relations(kaynak.id, TENANT)
    assert [s.id for s in once.suggested] == [b.id] and once.automatic == [] and once.manual == []

    cevap = rc.reject_case_relation(kaynak.id, CaseRelationReject(target_case_id=b.id), user, TENANT)
    assert cevap["status"] == "rejected"
    satir = oturum.query(models.CaseRelation).one()
    assert satir.relation_type == ilis.ONERI_RED and satir.created_by == "Test Avukat"

    sonra = rc.get_case_relations(kaynak.id, TENANT)
    assert sonra.suggested == [] and sonra.manual == []                # ret ne öneri ne elle bağ

    with pytest.raises(HTTPException) as exc:                          # ikinci ret 409
        rc.reject_case_relation(kaynak.id, CaseRelationReject(target_case_id=b.id), user, TENANT)
    assert exc.value.status_code == 409
