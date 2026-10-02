"""Rapor `davalar.taraf_sifati` (02.10 kullanıcı bulgusu): "Müdahil" seçip o sıfatta tarafı olan
davaları arayacak kolon yoktu — listesinde "Feri Müdahil" geçen tek kolon `istinaf_basvuran_taraf`
(ayrı alan) olduğundan rapor 0 satır dönüyordu. Filtre EXISTS `case_parties.role`, gösterim
"Ad (Sıfat)". Düzen `test_g137_rapor_katalog_genisleme.env` (sqlite, gerçek route)."""
import models
from tests import test_g137_rapor_katalog_genisleme as g137
from tests.test_g137_rapor_katalog_genisleme import _kolonlar, _katalog, _onizle, _takip, _tanim

env = g137.env      # fixture'ı bu modülde de görünür kıl


def _taraf_ekle(env, takip_no, ad, rol, tur="THIRD"):
    db = env.db()
    try:
        dava = db.query(models.Case).filter_by(tracking_no=takip_no).one()
        db.add(models.CaseParty(case_id=dava.id, name=ad, role=rol, party_type=tur))
        db.commit()
    finally:
        db.close()


def test_katalogda_taraf_sifati_liste_kolonu(env):
    """Taraflar grubunda türetilmiş liste kolon; seçenekler veriden (`case_parties.role`) gelir."""
    _taraf_ekle(env, "HA.G137.1", "Müdahil Kurum", "Müdahil")
    k = _kolonlar(_katalog(env.client())["davalar"])["taraf_sifati"]
    assert k["tip"] == "liste" and k["etiket"] == "Taraf Sıfatı" and k["grup"] == "Taraflar"
    assert k["turetilmis"] and k["filtrelenebilir"] and not k["siralanabilir"]
    assert k["oplar"] == ["eq", "in", "is_null"]
    assert {"Müdahil", "Davalı", "Davacı", "Sigortalı"} <= set(k["secenekler"])


def test_mudahil_secimi_mudahili_olan_davalari_getirir(env):
    _taraf_ekle(env, "HA.G137.1", "Müdahil Kurum", "Müdahil")
    _taraf_ekle(env, "HA.G137.2", "Fer'i Kurum", "Feri Müdahil")
    _taraf_ekle(env, "HA.G137.4", "Yabanci Mudahil", "Müdahil")      # başka tenant: sızmaz
    _taraf_ekle(env, "HA.G137.5", "Silinmis Mudahil", "Müdahil")     # silinmiş dava: gelmez
    client = env.client()

    r = _onizle(client, _tanim(filtreler=[{"alan": "taraf_sifati", "op": "in", "deger": ["Müdahil"]}]))
    assert _takip(r) == {"HA.G137.1"}
    r = _onizle(client, _tanim(filtreler=[{"alan": "taraf_sifati", "op": "eq", "deger": "Feri Müdahil"}]))
    assert _takip(r) == {"HA.G137.2"}
    r = _onizle(client, _tanim(filtreler=[{"alan": "taraf_sifati", "op": "in",
                                           "deger": ["Müdahil", "Feri Müdahil"]}]))
    assert _takip(r) == {"HA.G137.1", "HA.G137.2"}
    # Tarafsız dava (c6) "sıfatı dolu taraf yok"
    r = _onizle(client, _tanim(filtreler=[{"alan": "taraf_sifati", "op": "is_null"}]))
    assert _takip(r) == {"HA.G137.6"}


def test_gosterim_ad_ve_sifat(env):
    _taraf_ekle(env, "HA.G137.1", "Müdahil Kurum", "Müdahil")
    r = _onizle(env.client(), _tanim(kolonlar=("tracking_no", "taraf_sifati"),
                                     filtreler=[{"alan": "taraf_sifati", "op": "eq", "deger": "Müdahil"}]))
    assert r.status_code == 200, r.text
    hucre = r.json()["satirlar"][0]["taraf_sifati"]
    assert "Müdahil Kurum (Müdahil)" in hucre and "Hasta B (Davacı)" in hucre
