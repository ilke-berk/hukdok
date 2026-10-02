"""Rapor ↔ panel/dava listesi kapsam eşitliği (02.10 incelemesi). Üç kolon, raporun başka ekranlardan
daha az bulduğu yerleri kapatır:

- `kanun_yolu`: `cases.case_stage` kartların çoğunda boş (aşama `case_stage_decisions`'ta) → "Aşama =
  İstinaf" 0 dönüyordu; panel kutularıyla aynı tanım (`case_manager.kanun_yolu_ifadesi`).
- `avukatlar`: "Sorumlu Avukat" tek alan; karta atanmış diğer avukatlar (`case_lawyers`) kaçıyordu —
  dava listesinin avukat filtresi ikisine de bakar.
- `diger_taraf_adlari` + arama: THIRD taraflar (Diğer Davalı, İhbar Olunan) raporda adla bulunamıyordu.

Düzen `test_g137_rapor_katalog_genisleme.env` (sqlite, gerçek route)."""
import models
from managers import case_manager
from tests import test_g137_rapor_katalog_genisleme as g137
from tests.test_g137_rapor_katalog_genisleme import _kolonlar, _katalog, _onizle, _takip, _tanim

env = g137.env      # fixture'ı bu modülde de görünür kıl


def _dava(db, takip_no):
    return db.query(models.Case).filter_by(tracking_no=takip_no).one()


def _ekle(env, kur):
    db = env.db()
    try:
        kur(db)
        db.commit()
    finally:
        db.close()


def _filtre(alan, op, deger=None):
    f = {"alan": alan, "op": op}
    if deger is not None:
        f["deger"] = deger
    return _tanim(filtreler=[f])


# ─── Ulaştığı kanun yolu ─────────────────────────────────────────────────────

def _asamalari_kur(db):
    D = models.CaseStageDecision
    c1, c2, c3 = _dava(db, "HA.G137.1"), _dava(db, "HA.G137.2"), _dava(db, "HA.G137.3")
    db.add_all([
        D(case_id=c1.id, stage="ISTINAF", sira_no=1),                    # yalnız istinaf
        D(case_id=c2.id, stage="ISTINAF", sira_no=1),                    # temyiz istinafı ezer
        D(case_id=c2.id, stage="TEMYIZ", sira_no=1),
        D(case_id=c3.id, stage="KARAR_DUZELTME", sira_no=1),             # karar düzeltme = temyiz
    ])
    c3.file_type = "İdare"                                               # → Danıştay
    _dava(db, "HA.G137.6").case_stage = "ISTINAF"                        # kart alanı da sayılır


def test_kanun_yolu_katalogda_ve_degerleri(env):
    k = _kolonlar(_katalog(env.client())["davalar"])["kanun_yolu"]
    assert k["tip"] == "liste" and k["etiket"] == "Ulaştığı Kanun Yolu" and k["grup"] == "Karar ve aşama"
    assert set(k["secenekler"]) == set(case_manager.KANUN_YOLLARI)
    assert k["filtrelenebilir"] and k["siralanabilir"]


def test_kanun_yolu_karar_tarihcesinden_okunur(env):
    _ekle(env, _asamalari_kur)
    client = env.client()
    assert _takip(_onizle(client, _filtre("kanun_yolu", "eq", "İstinaf"))) == {"HA.G137.1", "HA.G137.6"}
    assert _takip(_onizle(client, _filtre("kanun_yolu", "eq", "Temyiz – Yargıtay"))) == {"HA.G137.2"}
    assert _takip(_onizle(client, _filtre("kanun_yolu", "eq", "Temyiz – Danıştay"))) == {"HA.G137.3"}
    # Yerel: aşama kararı da kart alanı da yok (c4 başka tenant, c5 silinmiş → yok)
    assert _takip(_onizle(client, _filtre("kanun_yolu", "eq", "Yerel"))) == set()
    # Kart alanı (`case_stage`) bu kartlarda boş — eski "Aşama" filtresi istinafı bulamazdı
    assert _takip(_onizle(client, _filtre("case_stage", "eq", "ISTINAF"))) == {"HA.G137.6"}


def test_kanun_yolu_paneldeki_derdest_sayilariyla_ayni(env):
    """Rapor `Durum = DERDEST` + kanun yolu = panel kutusu (`derdest_asama_kosullari`)."""
    _ekle(env, _asamalari_kur)
    db = env.db()
    try:
        panel = {a: {c.tracking_no for c in db.query(models.Case).filter(
            models.Case.deleted_at.is_(None), *case_manager.derdest_asama_kosullari(a)).all()}
            for a in ("ISTINAF", "TEMYIZ_YARGITAY", "TEMYIZ_DANISTAY")}
    finally:
        db.close()
    panel = {a: s - {"HA.G137.4"} for a, s in panel.items()}          # başka tenant raporda görünmez
    client = env.client()
    for asama, deger in (("ISTINAF", "İstinaf"), ("TEMYIZ_YARGITAY", "Temyiz – Yargıtay"),
                         ("TEMYIZ_DANISTAY", "Temyiz – Danıştay")):
        tanim = _tanim(filtreler=[{"alan": "status", "op": "eq", "deger": "DERDEST"},
                                  {"alan": "kanun_yolu", "op": "eq", "deger": deger}])
        assert _takip(_onizle(client, tanim)) == panel[asama], asama


# ─── Avukatlar (tümü) ────────────────────────────────────────────────────────

def _avukatlari_kur(db):
    L = models.CaseLawyer
    c1, c2 = _dava(db, "HA.G137.1"), _dava(db, "HA.G137.2")
    db.add_all([
        L(case_id=c1.id, name="Av. Ali"),                                # sorumlu da atanmış
        L(case_id=c2.id, name="Av. Zeynep"),                             # sorumlu Av. Veli, ek atama
    ])


def test_avukatlar_atanmis_avukati_da_bulur(env):
    _ekle(env, _avukatlari_kur)
    client = env.client()
    assert _takip(_onizle(client, _filtre("avukatlar", "eq", "Av. Zeynep"))) == {"HA.G137.2"}
    assert _takip(_onizle(client, _filtre("avukatlar", "in", ["Av. Veli", "Av. Ali"]))) == {"HA.G137.1", "HA.G137.2"}
    # Eski "Sorumlu Avukat" kolonu ek atamayı görmez
    assert _takip(_onizle(client, _filtre("responsible_lawyer_name", "eq", "Av. Zeynep"))) == set()
    # Avukatsız: sorumlu boş VE atama yok
    assert _takip(_onizle(client, _filtre("avukatlar", "is_null"))) == {"HA.G137.3", "HA.G137.6"}
    assert _takip(_onizle(client, _filtre("avukatlar", "in", [None, "Av. Zeynep"]))) == {
        "HA.G137.2", "HA.G137.3", "HA.G137.6"}


def test_avukatlar_gosterimi_sorumlu_once_tekrarsiz(env):
    _ekle(env, _avukatlari_kur)
    r = _onizle(env.client(), _tanim(kolonlar=("tracking_no", "avukatlar"), siralama=[{"alan": "tracking_no",
                                                                                         "yon": "asc"}]))
    assert r.status_code == 200, r.text
    hucre = {s["tracking_no"]: s["avukatlar"] for s in r.json()["satirlar"]}
    assert hucre["HA.G137.1"] == "Av. Ali"
    assert hucre["HA.G137.2"] == "Av. Veli ; Av. Zeynep"
    assert hucre["HA.G137.6"] is None


# ─── Diğer taraflar (THIRD) ──────────────────────────────────────────────────

def _diger_taraf_kur(db):
    db.add(models.CaseParty(case_id=_dava(db, "HA.G137.6").id, name="Dr. Diğer Davalı", role="Diğer Davalı",
                            party_type="THIRD"))


def test_diger_taraflar_kolonu_ve_arama(env):
    _ekle(env, _diger_taraf_kur)
    client = env.client()
    assert _takip(_onizle(client, _filtre("diger_taraf_adlari", "contains", "diğer davalı"))) == {"HA.G137.6"}
    # Sigortalı THIRD kendi kolonunda kalır, "Diğer Taraflar"a girmez
    assert _takip(_onizle(client, _filtre("diger_taraf_adlari", "contains", "Sigortalı Klinik"))) == set()
    # Arama kutusu THIRD tarafları da bulur (dava listesi araması gibi)
    assert _takip(_onizle(client, _filtre("arama", "contains", "Dr. Diğer"))) == {"HA.G137.6"}
    assert _takip(_onizle(client, _filtre("arama", "contains", "Sigortalı Klinik"))) == {"HA.G137.1"}
