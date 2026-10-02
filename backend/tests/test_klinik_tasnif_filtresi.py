"""Dava listesi klinik tasnif filtreleri (02.10): `tibbi_surec` + `tibbi_olay`.

Kolonlar çok değerlidir (`multi_value.SEPARATOR` = " ; "); filtre değeri hücrede TAM
ÖĞE olarak eşleşir — "Cerrahi" süzgeci "Cerrahi Uygulama" hücresini yakalamaz, ama
"Doğum Yönetimi ; Cerrahi" hücresini yakalar. Kalıp ve fixture'lar G119 testinden
(`seedli_fabrika` sqlite StaticPool, `client` bağımlılık override'lı).
"""
from managers import case_manager
from tests.test_g119_muvekkil_tipi_hizmet_turu import (  # noqa: F401 — fixture'lar
    _dava_ekle, client, oturum_fabrikasi, seedli_fabrika,
)


def test_tibbi_surec_tam_oge_eslesmesi(seedli_fabrika):  # noqa: F811
    tek = _dava_ekle(seedli_fabrika, tracking_no="HA.X.9401.2026", tibbi_surec="Cerrahi")
    coklu = _dava_ekle(seedli_fabrika, tracking_no="HA.X.9402.2026",
                       tibbi_surec="Doğum Yönetimi ; Cerrahi")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9403.2026", tibbi_surec="Cerrahi Uygulama")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9404.2026")                 # NULL

    items, total = case_manager.get_cases(tibbi_surec="Cerrahi")
    assert {c["id"] for c in items} == {tek, coklu}
    assert total == 2

    items, total = case_manager.get_cases(tibbi_surec="ALL")
    assert total == 4


def test_tibbi_olay_joker_karakterleri_kacisli(seedli_fabrika):  # noqa: F811
    """`%`/`_` değer içinde joker değil, harf olarak aranır."""
    hedef = _dava_ekle(seedli_fabrika, tracking_no="HA.X.9411.2026", tibbi_olay="Yanık_%2")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9412.2026", tibbi_olay="YanıkX12")

    items, total = case_manager.get_cases(tibbi_olay="Yanık_%2")
    assert [c["id"] for c in items] == [hedef]
    assert total == 1


def test_iki_filtre_and_ile_birlesir(seedli_fabrika):  # noqa: F811
    c1 = _dava_ekle(seedli_fabrika, tracking_no="HA.X.9421.2026",
                    tibbi_surec="Doğum Yönetimi", tibbi_olay="Omuz Distosisi")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9422.2026",
               tibbi_surec="Doğum Yönetimi", tibbi_olay="Asfiksik Doğum")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9423.2026",
               tibbi_surec="Cerrahi", tibbi_olay="Omuz Distosisi")

    items, total = case_manager.get_cases(tibbi_surec="Doğum Yönetimi", tibbi_olay="Omuz Distosisi")
    assert [c["id"] for c in items] == [c1]
    assert total == 1


def test_route_liste_ucu_klinik_tasnif_parametreleri(client, seedli_fabrika):  # noqa: F811
    c1 = _dava_ekle(seedli_fabrika, tracking_no="HA.X.9431.2026",
                    tibbi_surec="Cerrahi ; Gebelik Takibi", tibbi_olay="Cisim Unutma (Gazlı Bez)")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9432.2026", tibbi_surec="Gebelik Takibi")

    resp = client.get("/api/cases", params={"tibbi_surec": "Cerrahi"})
    assert resp.status_code == 200
    assert [c["id"] for c in resp.json()] == [c1]
    assert resp.headers["X-Total-Count"] == "1"

    resp = client.get("/api/cases", params={"tibbi_olay": "Cisim Unutma (Gazlı Bez)"})
    assert resp.headers["X-Total-Count"] == "1"

    resp = client.get("/api/cases", params={"tibbi_surec": "Gebelik Takibi"})
    assert resp.headers["X-Total-Count"] == "2"


# ── Tıbbi Olay seçenekleri: süreç seçimine göre daralan, sayılı liste ─────────

def test_olay_secenekleri_veriden_sayili_ve_surece_gore_daralir(seedli_fabrika):  # noqa: F811
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9441.2026",
               tibbi_surec="Doğum Yönetimi", tibbi_olay="Omuz Distosisi ; Asfiksik Doğum")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9442.2026",
               tibbi_surec="Doğum Yönetimi ; Cerrahi", tibbi_olay="omuz distosisi")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9443.2026",
               tibbi_surec="Cerrahi Uygulama", tibbi_olay="Cisim Unutma (Gazlı Bez)")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9444.2026", tibbi_surec="Doğum Yönetimi")   # olaysız

    tum = case_manager.tibbi_olay_secenekleri()
    # Büyük/küçük harf farkı tek seçenek; sayı azalan, eşitlikte ad
    assert [(s["name"].casefold(), s["count"]) for s in tum] == [
        ("omuz distosisi", 2), ("asfiksik doğum", 1), ("cisim unutma (gazlı bez)", 1),
    ]

    dogum = case_manager.tibbi_olay_secenekleri(tibbi_surec="Doğum Yönetimi")
    assert [(s["name"].casefold(), s["count"]) for s in dogum] == [
        ("omuz distosisi", 2), ("asfiksik doğum", 1),
    ]
    # Tam öğe: "Cerrahi" süreci "Cerrahi Uygulama"lı davanın olayını getirmez
    cerrahi = case_manager.tibbi_olay_secenekleri(tibbi_surec="Cerrahi")
    assert [(s["name"].casefold(), s["count"]) for s in cerrahi] == [("omuz distosisi", 1)]

    assert case_manager.tibbi_olay_secenekleri(tibbi_surec="ALL") == tum


def test_route_olay_secenekleri(client, seedli_fabrika):  # noqa: F811
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9451.2026",
               tibbi_surec="Gebelik Takibi", tibbi_olay="Down Sendromu")
    _dava_ekle(seedli_fabrika, tracking_no="HA.X.9452.2026",
               tibbi_surec="Cerrahi", tibbi_olay="Septorinoplasti")

    resp = client.get("/api/cases/tibbi-olay-secenekleri", params={"tibbi_surec": "Gebelik Takibi"})
    assert resp.status_code == 200
    assert resp.json() == [{"name": "Down Sendromu", "count": 1}]

    resp = client.get("/api/cases/tibbi-olay-secenekleri")
    assert {s["name"] for s in resp.json()} == {"Down Sendromu", "Septorinoplasti"}
