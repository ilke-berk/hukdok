"""G235 — ofis no üreticisi, kod listeleri, admin uçları (karar 023).

Şartname `docs/kararlar/023-ofis-no-formati.md`. Bu dosya saf fonksiyonları ve
sqlite üzerindeki DB yollarını (sayaç, önizleme, kod listesi, admin uçları, seed)
kilitler; gerçek Postgres gerektiren eşzamanlılık ve migrasyon testleri
`test_g235_ofis_no_postgres.py`'dedir.

Eski kodda kırmızıdır: `services/ofis_no.py`, `ofis_no_sayaclari`,
`sigorta_kisa_kodlari`, `client_categories.ofis_no_kodu` ve admin uçları yoktu.
"""
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

import models
from dependencies import get_current_user
from managers import seed_data
from routes import admin as admin_routes
from services import ofis_no

ADMIN = "yonetici@example.com"


# ─── ortak altyapı ───────────────────────────────────────────────────────────

@pytest.fixture()
def fabrika(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    Fabrika = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(seed_data, "SessionLocal", Fabrika)
    monkeypatch.setattr(admin_routes, "SessionLocal", Fabrika)
    yield Fabrika
    engine.dispose()


@pytest.fixture()
def tohumlu(fabrika):
    seed_data._seed_client_categories()
    seed_data._seed_sigorta_kisa_kodlari()
    return fabrika


def _istemci(monkeypatch, email):
    monkeypatch.setenv("ADMIN_EMAILS", ADMIN)
    app = FastAPI()
    app.include_router(admin_routes.router)
    app.dependency_overrides[get_current_user] = lambda: {"preferred_username": email}
    return TestClient(app)


def _m(ad, kategori=None):
    return {"name": ad, "category": kategori}


def _numara(muvekkiller, sira, tur, *, foys=(), parties=()):
    """Girdi: müvekkil listesi (+kategori) + tür + sigortalı kaynakları → tam numara."""
    kod, secilen = ofis_no.musteri_kodu(muvekkiller)
    sigortali = None
    if ofis_no.sigortaci_mi(secilen["name"], secilen.get("category")):
        sigortali = ofis_no.sigortali_sec(None, foys, parties, muvekkiller=muvekkiller)
    return ofis_no.numara_kur(kod, sira, sigortali, ofis_no.tur_kodu(tur))


def _foy(sigortali):
    return {"ham_veri": {"Sigortalı": sigortali}}


# ─── karar 023 §2: kategori tablosundaki HER örnek ───────────────────────────

@pytest.mark.parametrize("ad, kategori, sira, tur, beklenen", [
    ("Mehmet Öztürk", "Doktor", 3, "Hukuk", "DR.M.OZTURK-0003-HUK"),
    ("Aysel Koca Hem.", "Sağlık Çalışanı", 1, "Hukuk", "SC.A.KOCA-0001-HUK"),
    ("Ayşe Kaya", "Hasta", 1, "İdare", "HS.A.KAYA-0001-IDR"),
    ("Özel Safa Hastanesi", "Özel Hastane", 1, "Hukuk", "OH.SAFA-0001-HUK"),
    ("Enthone Kimya San. ve Tic. A.Ş.", "Kurum", 15, "Ceza", "KR.ENTHONE-0015-CEZ"),
    ("Tahsin Koç", "Bireysel", 9, "İcra", "BR.T.KOC-0009-ICR"),
    ("Sümutu", "Diğer", 1, "Hukuk", "DG.SUMUTU-0001-HUK"),
])
def test_kategori_tablosu_ornekleri(ad, kategori, sira, tur, beklenen):
    assert _numara([_m(ad, kategori)], sira, tur) == beklenen


# ─── karar 023 §3: sigorta tablosundaki HER örnek ────────────────────────────

@pytest.mark.parametrize("sirket, sigortali, sira, tur, beklenen", [
    ("AK SİGORTA A.Ş.", "Dr. Esra Altunç", 1189, "Hukuk", "AK-1189-DR.E.ALTUNC-HUK"),
    ("ANADOLU ANONİM TÜRK SİGORTA ŞİRKETİ", "Dr. Şenol Özay", 1317, "İdari Yargı", "ANADOLU-1317-DR.S.OZAY-IDR"),
    ("AXA SİGORTA A.Ş.", "Dr. Esra Altunç", 3297, "Hukuk", "AXA-3297-DR.E.ALTUNC-HUK"),
    ("CORPUS SİGORTA ANONİM ŞİRKETİ", "Dr. Ayşe Kaya", 3, "Hukuk", "CORPUS-0003-DR.A.KAYA-HUK"),
    ("QUICK SİGORTA A.Ş", "Dr. Yıldırım Tüylü", 588, "Hukuk", "QUICK-0588-DR.Y.TUYLU-HUK"),
    ("EUREKO SİGORTA A.Ş.", None, 409, "Hukuk", "EUREKO-0409-HUK"),
    ("TÜRK NİPPON SİGORTA AŞ", "Dr.Haktan Ergin Bağış", 178, "Hukuk", "NIPPON-0178-DR.H.BAGIS-HUK"),
    ("SOMPO SİGORTA A.Ş.", None, 206, "Hukuk", "SOMPO-0206-HUK"),
    ("S.S. KORU SİGORTA KOOPERATİFİ", "Dr.Teoman Toni Sevinç", 3172, "İdare", "KORU-3172-DR.T.SEVINC-IDR"),
    ("HDI SİGORTA A.Ş", None, 4, "Hukuk", "HDI-0004-HUK"),
    ("ZİRAAT SİGORTA A.Ş.", None, 1, "Hukuk", "ZIRAAT-0001-HUK"),
    ("BAŞAK SİGORTA A.Ş", None, 1, "Hukuk", "SG-0001-HUK"),
    ("AXA SİGORTA A.Ş.", None, 3297, "Hukuk", "AXA-3297-HUK"),
])
def test_sigorta_tablosu_ornekleri(sirket, sigortali, sira, tur, beklenen):
    foys = [_foy(sigortali)] if sigortali else []
    assert _numara([_m(sirket, "Sigorta Şirketi")], sira, tur, foys=foys) == beklenen


@pytest.mark.parametrize("ad, beklenen", [
    ("Anadolu Anonim Türk Sigorta Şirketi", "ANADOLU"),
    ("Koru Sigorta", "KORU"),
    ("Quick Sigorta", "QUICK"),
    ("Corpus Sigorta", "CORPUS"),
    ("Aksigorta A.Ş.", "AK"),
    ("Türkiye Sigorta A.Ş.", "SG"),
])
def test_sigortaci_kodu_kategorisiz_addan(ad, beklenen):
    """Kategori yazılmamış olsa da adında "sigorta" geçen müvekkil sigortacıdır."""
    kod, secilen = ofis_no.musteri_kodu([_m(ad)])
    assert kod == beklenen
    assert secilen["name"] == ad


def test_sigorta_eslesmesi_kelime_bazli():
    """"AK" anahtarı "AKTİF" ya da "BANKA" içinde eşleşmez — listede olmayan SG alır."""
    assert ofis_no.musteri_kodu([_m("Aktif Sigorta A.Ş.")])[0] == "SG"
    assert ofis_no.sigorta_kodu("Quick Sigorta") == "QUICK"      # küçük harf + i
    assert ofis_no.sigorta_kodu("nippon sigorta") == "NIPPON"


# ─── kişi / kurum blokları ───────────────────────────────────────────────────

@pytest.mark.parametrize("kod, ad, beklenen", [
    ("DR", "Dr.Teoman Toni Sevinç", "DR.T.SEVINC"),
    ("SC", "Aysel Koca Hem.", "SC.A.KOCA"),
    ("DR", "Mehmet Cüneyt Uğuzbalaban Dr.", "DR.M.UGUZBALABAN"),
    ("DR", "SÜLEYMAN TAŞ (DR. ÖZEL)", "DR.S.TAS"),
    ("DR", "DENİZ ÇAKIR DR.ÖZEL", "DR.D.CAKIR"),
    ("DR", "Prof. Dr. İsmail Işık Çağlar", "DR.I.CAGLAR"),
    ("HS", "Şükrü Ğüöç", "HS.S.GUOC"),
    ("BR", "Av. Ali Uz", "BR.A.UZ"),                 # noktasız "Uz" soyaddır, unvan değil
    ("DR", "Dr. Özgür Özel", "DR.O.OZEL"),           # "Özel" soyad olarak korunur
    ("HS", "Madonna", "HS.MADONNA"),                 # tek kelime: baş harfsiz
    ("BR", "M. Öztürk", "BR.M.OZTURK"),
    ("BR", "Şeyma O'Brien", "BR.S.OBRIEN"),
])
def test_kisi_blogu(kod, ad, beklenen):
    assert ofis_no.kisi_blogu(kod, ad) == beklenen


@pytest.mark.parametrize("kod, ad, beklenen", [
    ("KR", "Enthone Kimya San. ve Tic. A.Ş.", "KR.ENTHONE"),
    ("KR", "İnka Yapı Bağlantı Elemanları San. ve Tic. A.Ş.", "KR.INKA"),
    ("OH", "Özel Safa Hastanesi", "OH.SAFA"),
    ("OH", "DOĞSAN ÖZEL SAĞLIK HİZMETLERİ", "OH.DOGSAN"),
    ("KR", "Uluslararası Çokuzunbirkurumadı Derneği", "KR.ULUSLARARASI"),   # ad KESİLMEZ
    ("KR", "Sağlık Hizmetleri A.Ş.", "KR.SAGLIK"),   # hepsi jenerik → ham ilk kelime
])
def test_kurum_blogu(kod, ad, beklenen):
    assert ofis_no.kurum_blogu(kod, ad) == beklenen


@pytest.mark.parametrize("ad", ["", "   ", None, "Dr.", "( )", "123"])
def test_bos_ad_valueerror_yer_tutucu_uretilmez(ad):
    with pytest.raises(ValueError):
        ofis_no.kisi_blogu("DR", ad)
    with pytest.raises(ValueError):
        ofis_no.kurum_blogu("KR", "" if ad == "Dr." else ad)


def test_muvekkilsiz_numara_uretilmez():
    with pytest.raises(ValueError):
        ofis_no.musteri_kodu([])
    with pytest.raises(ValueError):
        ofis_no.musteri_kodu([_m("  ", "Doktor")])
    with pytest.raises(ValueError):
        ofis_no.musteri_kodu([_m("Dr.", "Doktor")])


# ─── kategori kodu ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("kategori, ad, beklenen", [
    ("Doktor", "x", "DR"),
    ("Sağlık Çalışanı", "x", "SC"),
    ("Diğer Sağlık Çalışanı", "x", "SC"),     # föy müvekkil tipi
    ("Hasta", "x", "HS"),
    ("Özel Hastane", "x", "OH"),              # "Hasta" parçasına DÜŞMEZ
    ("Kurum", "x", "KR"),
    ("Bireysel", "x", "BR"),
    ("Diğer", "x", "DG"),
    ("Klinik", "x", "OH"),
    ("Acente", "x", "KR"),
    ("Dernek", "x", "KR"),
    ("DOKTOR", "x", "DR"),
    ("SAGLIK-CALISANI", "x", "SC"),           # kategori KODU da tanınır
    ("OZEL-HASTANE", "x", "OH"),
    (None, "İnka Yapı Bağlantı Elemanları San. ve Tic. A.Ş.", "KR"),
    ("", "Tahsin Koç", "BR"),
    (None, "Ali San", "BR"),                  # noktasız "San" şirket işareti değil
    (None, "Medikal Ltd. Şti.", "KR"),
    (None, "Acme GmbH", "KR"),
    (None, "Delta AŞ", "KR"),
    (None, "Omega Inc.", "KR"),
])
def test_kategori_kodu(kategori, ad, beklenen):
    assert ofis_no.kategori_kodu(kategori, ad) == beklenen


def test_kategorisiz_muvekkil_tam_blok():
    assert ofis_no.musteri_kodu([_m("İnka Yapı Bağlantı Elemanları San. ve Tic. A.Ş.")])[0] == "KR.INKA"
    assert ofis_no.musteri_kodu([_m("Tahsin Koç")])[0] == "BR.T.KOC"
    assert ofis_no.musteri_kodu([_m("Gülüm Klinik", "Klinik")])[0] == "OH.GULUM"
    assert ofis_no.musteri_kodu([_m("Marmara Acentelik", "Acente")])[0] == "KR.MARMARA"
    assert ofis_no.musteri_kodu([_m("Hekimler Derneği", "Dernek")])[0] == "KR.HEKIMLER"


def test_acik_kategori_addaki_sigortadan_ustun():
    """Karar 023 §2 uçtan uca: adında "sigorta" geçen Acente sigortacı değil kurumdur."""
    assert ofis_no.musteri_kodu([_m("KAYNAK SİGORTA", "Acente")])[0] == "KR.KAYNAK"
    assert ofis_no.musteri_kodu([_m("YKM SİGORTA", "Acente")])[0] == "KR.YKM"
    assert not ofis_no.sigortaci_mi("Kaynak Sigorta", "Acente")
    # Kategori boşken ya da "Diğer"ken ad taraması sürer; sigorta kategorisi her zaman sigortacıdır.
    assert ofis_no.musteri_kodu([_m("Koru Sigorta A.Ş.")])[0] == "KORU"
    assert ofis_no.musteri_kodu([_m("Bilinmeyen Sigorta A.Ş.", "Diğer")])[0] == "SG"
    assert ofis_no.musteri_kodu([_m("Axa", "Sigorta Şirketi")])[0] == "AXA"


# ─── çok müvekkil ────────────────────────────────────────────────────────────

def test_cok_muvekkilde_ad_onceligi():
    """Doktor > Sağlık Çalışanı > Hasta > Bireysel > Diğer/kategorisiz > Özel Hastane > Kurum."""
    hepsi = [
        _m("Beta Kurum A.Ş.", "Kurum"),
        _m("Özel Safa Hastanesi", "Özel Hastane"),
        _m("Kategorisiz Kişi"),
        _m("Tahsin Koç", "Bireysel"),
        _m("Ayşe Kaya", "Hasta"),
        _m("Aysel Koca", "Sağlık Çalışanı"),
        _m("Mehmet Öztürk", "Doktor"),
    ]
    beklenen = ["DR.M.OZTURK", "SC.A.KOCA", "HS.A.KAYA", "BR.T.KOC", "BR.K.KISI", "OH.SAFA", "KR.BETA"]
    for i, kod in enumerate(beklenen):
        assert ofis_no.musteri_kodu(hepsi[: len(hepsi) - i])[0] == kod


def test_sigortaci_ve_doktor_birlikte_muvekkil():
    """Kod sigortacının; doktor sigortalı bloğunda (karar 023 §5)."""
    muvekkiller = [_m("Mehmet Öztürk", "Doktor"), _m("AXA SİGORTA A.Ş.", "Sigorta Şirketi")]
    kod, secilen = ofis_no.musteri_kodu(muvekkiller)
    assert kod == "AXA"
    assert secilen["name"] == "AXA SİGORTA A.Ş."
    assert ofis_no.sigortali_sec(None, [], [], muvekkiller=muvekkiller) == "DR.M.OZTURK"
    assert _numara(muvekkiller, 3298, "Hukuk") == "AXA-3298-DR.M.OZTURK-HUK"


def test_iki_sigortacida_listede_olan_kazanir():
    muvekkiller = [_m("Başak Sigorta A.Ş.", "Sigorta Şirketi"), _m("Sompo Sigorta A.Ş.", "Sigorta Şirketi")]
    kod, secilen = ofis_no.musteri_kodu(muvekkiller)
    assert (kod, secilen["name"]) == ("SOMPO", "Sompo Sigorta A.Ş.")


def test_muvekkil_nesne_olarak_da_okunur():
    client = models.Client(name="Mehmet Öztürk", category="Doktor")
    kod, secilen = ofis_no.musteri_kodu([client])
    assert kod == "DR.M.OZTURK" and secilen is client


# ─── sigortalı bloğu ─────────────────────────────────────────────────────────

def test_sigortali_kaynak_onceligi():
    foy = _foy("Dr. Esra Altunç")
    sigortali_taraf = {"role": "Sigortalı", "name": "Dr.Ali Demir", "party_type": "THIRD"}
    diger_davali = {"role": "Diğer Davalı", "name": "Akin Karaca Dr.", "party_type": "THIRD"}
    bakanlik = {"role": "Diğer Davalı", "name": "Sağlik Bakanliği", "party_type": "THIRD"}
    ortak = [_m("AXA Sigorta", "Sigorta Şirketi"), _m("Mehmet Öztürk", "Doktor")]

    # 1. föy → 2. Sigortalı tarafı → 3. birlikte müvekkil → 4. Diğer Davalı içindeki ilk hekim
    assert ofis_no.sigortali_sec(None, [foy], [sigortali_taraf, diger_davali], muvekkiller=ortak) == "DR.E.ALTUNC"
    assert ofis_no.sigortali_sec(None, [], [diger_davali, sigortali_taraf], muvekkiller=ortak) == "DR.A.DEMIR"
    assert ofis_no.sigortali_sec(None, [], [diger_davali], muvekkiller=ortak) == "DR.M.OZTURK"
    assert ofis_no.sigortali_sec(None, [], [bakanlik, diger_davali], muvekkiller=ortak[:1]) == "DR.A.KARACA"
    # Hekim olmayan "Diğer Davalı" sigortalı SAYILMAZ → blok yok ("sigortalı eksik")
    assert ofis_no.sigortali_sec(None, [], [bakanlik], muvekkiller=ortak[:1]) is None
    assert ofis_no.sigortali_sec(None, [], []) is None


def test_sigortali_kendi_kategori_koduyla():
    assert ofis_no.sigortali_sec(None, [_foy("Aysel Koca Hem.")], []) == "SC.A.KOCA"
    assert ofis_no.sigortali_sec(None, [_foy("Özel Safa Hastanesi")], []) == "OH.SAFA"
    assert ofis_no.sigortali_sec(None, [_foy("Medikal Ltd. Şti.")], []) == "KR.MEDIKAL"
    assert ofis_no.sigortali_sec(None, [_foy("Esra Altunç")], []) == "DR.E.ALTUNC"   # unvansız → hekim


@pytest.mark.parametrize("ham, beklenen", [
    # Gerçek veriden: `;` ayraçlı çok adlı "Sigortalı" — adlar kaynaştırılmaz, TEK kişi (karar 023 §7).
    ("Ufuk Tekbaş Dr.; Tam-Med Özel Hastane Teşhis ve Tedavi Hizmetleri A.Ş", "DR.U.TEKBAS"),
    ("Gökhan Pekcan Dr.; İstanbul Özel Kartal Hastanesi", "DR.G.PEKCAN"),
    ("Halil Kahveci Dr.; Ramazan Danışman Dr.; Servet Yavuz Dr.; İsmail Yıldız Dr", "DR.H.KAHVECI"),
    ("Özel Kartal Hastanesi; Gökhan Pekcan Dr", "DR.G.PEKCAN"),          # kurum önde: hekim seçilir
    ("Dilşat Çamlı Dr.; Özel Kent Sağlık Hiz. ve Mal. San. ve Tic. .AŞ", "DR.D.CAMLI"),
    ("Clinimed Medikal Estetik Hizmetleri ve Ticaret; Zübeyde Kuru Dr", "DR.Z.KURU"),
    ("Özel Safa Hastanesi; Esra Altunç", "DR.E.ALTUNC"),                 # unvansız kişi kurumdan önce
    ("Özel Safa Hastanesi; Medikal Ltd. Şti.", "OH.SAFA"),               # yalnız kurumlar: ilki
    ("Özel Safa Hastanesi; Aysel Koca Hem.", "SC.A.KOCA"),
    (" ; Dr. Şenol Özay ; ", "DR.S.OZAY"),                               # boş parçalar atılır
    ("Dr.Faysal Dane\nDr.Davut Şahin", "DR.F.DANE"),                     # unvanla başlayan satır = yeni ad
    ("Ferda Korkmaz \nÖzkanoğlu", "DR.F.OZKANOGLU"),                     # sarılmış TEK ad bölünmez
    ("Ömer Lütfi Aksoy ve Diğerleri", "DR.O.AKSOY"),
])
def test_sigortali_cok_adli_degerde_tek_kisi(ham, beklenen):
    assert ofis_no.sigortali_sec(None, [_foy(ham)], []) == beklenen
    taraf = {"name": ham, "role": "Sigortalı", "party_type": "THIRD"}
    assert ofis_no.sigortali_sec(None, [], [taraf]) == beklenen


def test_sigortali_kapsam_disi_foy_atlanir_bos_deger_gecilir():
    foys = [
        {"ham_veri": {"Sigortalı": "Dr. Eski Kayıt"}, "kapsam_durumu": "SILINDI"},
        {"ham_veri": {"Sigortalı": "  "}},
        {"ham_veri": None},
        {"ham_veri": {"Sigortalı": "Dr. Şenol Özay"}},
    ]
    assert ofis_no.sigortali_sec(None, foys, []) == "DR.S.OZAY"


def test_sigortali_case_nesnesinden_okunur():
    case = models.Case(tracking_no="G235.X")
    case.foys = [models.CaseFoy(sistem_no="SSTMN-1", ham_veri={"Sigortalı": "Dr. Yıldırım Tüylü"})]
    assert ofis_no.sigortali_sec(case) == "DR.Y.TUYLU"
    bos = models.Case(tracking_no="G235.Y")
    bos.parties = [models.CaseParty(name="Dr.Faysal Dane", role="Sigortalı", party_type="THIRD")]
    assert ofis_no.sigortali_sec(bos) == "DR.F.DANE"


# ─── tür kodu + numara ───────────────────────────────────────────────────────

@pytest.mark.parametrize("tur, kod", [
    ("Hukuk", "HUK"), ("Ceza", "CEZ"), ("İcra", "ICR"), ("Arabuluculuk", "ARB"),
    ("Savcılık", "SAV"), ("İdare", "IDR"), ("İdari Yargı", "IDR"), ("Tahkim", "THK"),
    ("Vergi", "VRG"), ("Danışmanlık", "DAN"),
    ("", "HUK"), (None, "HUK"), ("Hukuk Dava", "HUK"), ("Bilinmeyen", "HUK"),
])
def test_tur_kodu(tur, kod):
    assert ofis_no.tur_kodu(tur) == kod


def test_numara_kur():
    assert ofis_no.numara_kur("DR.M.OZTURK", 3, None, "HUK") == "DR.M.OZTURK-0003-HUK"
    assert ofis_no.numara_kur("AXA", 3297, "DR.E.ALTUNC", "HUK") == "AXA-3297-DR.E.ALTUNC-HUK"
    assert ofis_no.numara_kur("AXA", 9999, None, "HUK") == "AXA-9999-HUK"
    assert ofis_no.numara_kur("AXA", 10000, None, "HUK") == "AXA-10000-HUK"     # doğal uzar
    assert ofis_no.numara_kur("AXA", 12, "", "IDR") == "AXA-0012-IDR"
    for kod, sira, tur in [("", 1, "HUK"), ("  ", 1, "HUK"), ("AXA", 0, "HUK"), ("AXA", -1, "HUK"),
                           ("AXA", True, "HUK"), ("AXA", 1, "")]:
        with pytest.raises(ValueError):
            ofis_no.numara_kur(kod, sira, None, tur)


# ─── sayaç + önizleme (sqlite; eşzamanlılık Postgres dosyasında) ─────────────

def test_sira_tahsis_kod_basina_ardisik(fabrika):
    db = fabrika()
    assert [ofis_no.sira_tahsis_et(db, "AXA") for _ in range(3)] == [1, 2, 3]
    assert ofis_no.sira_tahsis_et(db, "DR.M.OZTURK") == 1          # kod başına ayrı sayaç
    assert ofis_no.sira_tahsis_et(db, "AXA") == 4
    db.commit()
    assert db.get(models.OfisNoSayaci, "AXA").son_sira == 4
    with pytest.raises(ValueError):
        ofis_no.sira_tahsis_et(db, " ")
    db.close()


def test_sira_tahsisi_commit_etmez_rollback_sirayi_geri_verir(fabrika):
    db = fabrika()
    assert ofis_no.sira_tahsis_et(db, "AXA") == 1
    db.commit()
    assert ofis_no.sira_tahsis_et(db, "AXA") == 2
    db.rollback()                                   # kart kaydı geri alındı
    assert ofis_no.sira_tahsis_et(db, "AXA") == 2   # numara boşa yanmadı
    db.close()


def test_onizle_sayaci_artirmaz(tohumlu):
    db = tohumlu()
    muvekkiller = [_m("AXA SİGORTA A.Ş.", "Sigorta Şirketi")]
    foys = [_foy("Dr. Esra Altunç")]
    for _ in range(3):
        sonuc = ofis_no.onizle(db, muvekkiller, "Hukuk", foys=foys)
        assert sonuc == {"numara": "AXA-0001-DR.E.ALTUNC-HUK", "kod": "AXA", "sira": 1,
                         "sigortali": "DR.E.ALTUNC", "tur": "HUK"}
    assert db.query(models.OfisNoSayaci).count() == 0              # satır bile doğmadı

    assert ofis_no.sira_tahsis_et(db, "AXA") == 1
    db.commit()
    assert ofis_no.onizle(db, muvekkiller, "Hukuk", foys=foys)["numara"] == "AXA-0002-DR.E.ALTUNC-HUK"
    assert ofis_no.onizle(db, muvekkiller, "Hukuk", foys=foys)["numara"] == "AXA-0002-DR.E.ALTUNC-HUK"
    assert db.get(models.OfisNoSayaci, "AXA").son_sira == 1
    # Sigortacı olmayan müvekkilde sigortalı kaynağı olsa da blok yazılmaz
    kisi = ofis_no.onizle(db, [_m("Mehmet Öztürk", "Doktor")], "Ceza", foys=foys)
    assert kisi["numara"] == "DR.M.OZTURK-0001-CEZ" and kisi["sigortali"] is None
    db.close()


# ─── seed + kod listeleri ────────────────────────────────────────────────────

def test_seed_kategori_ve_sigorta_kodlari(tohumlu):
    db = tohumlu()
    kodlar = {c.code: c.ofis_no_kodu for c in db.query(models.ClientCategory).all()}
    assert kodlar == {"DOKTOR": "DR", "SAGLIK-CALISANI": "SC", "HASTA": "HS", "OZEL-HASTANE": "OH",
                      "KURUM": "KR", "BIREYSEL": "BR", "DIGER": "DG", "SIGORTA": None}
    sigorta = [s.kod for s in db.query(models.SigortaKisaKodu).order_by(models.SigortaKisaKodu.id)]
    assert sigorta == ["AK", "ANADOLU", "AXA", "CORPUS", "QUICK", "EUREKO", "NIPPON", "SOMPO",
                       "KORU", "HDI", "ZIRAAT"]
    assert "SG" not in sigorta                                     # SG satır değil, sabit geri dönüş
    assert not set(sigorta) & {k for k in kodlar.values() if k}    # iki liste çakışmaz
    db.close()


def test_seed_mevcut_kategoriye_kodu_doldurur_yonetici_degisikligini_ezmez(fabrika):
    db = fabrika()
    db.add_all([
        models.ClientCategory(code="DOKTOR", name="Doktor", active=True),                       # eski satır
        models.ClientCategory(code="HASTA", name="Hasta", ofis_no_kodu="HT", active=True),      # yönetici değiştirdi
    ])
    db.commit()
    db.close()
    seed_data._seed_client_categories()
    seed_data._seed_client_categories()
    db = fabrika()
    kodlar = {c.code: c.ofis_no_kodu for c in db.query(models.ClientCategory).all()}
    assert kodlar["DOKTOR"] == "DR" and kodlar["HASTA"] == "HT" and kodlar["KURUM"] == "KR"
    assert db.query(models.ClientCategory).count() == 8
    db.close()


def test_seed_sigorta_listesi_yalniz_bos_tabloya(tohumlu):
    db = tohumlu()
    axa = db.query(models.SigortaKisaKodu).filter_by(kod="AXA").one()
    axa.kod = "AXAS"
    db.query(models.SigortaKisaKodu).filter_by(kod="HDI").one().aktif = False
    db.commit()
    db.close()
    seed_data._seed_sigorta_kisa_kodlari()
    db = tohumlu()
    assert db.query(models.SigortaKisaKodu).count() == 11          # AXA geri GELMEDİ
    assert db.query(models.SigortaKisaKodu).filter_by(kod="AXA").count() == 0
    assert db.query(models.SigortaKisaKodu).filter_by(kod="HDI").one().aktif is False
    db.close()


def test_kod_listeleri_dbden_pasif_kod_eslesmede_kullanilmaz(tohumlu):
    db = tohumlu()
    kl = ofis_no.kod_listelerini_yukle(db)
    assert ofis_no.musteri_kodu([_m("HDI SİGORTA A.Ş")], kl)[0] == "HDI"
    assert ofis_no.musteri_kodu([_m("Mehmet Öztürk", "Doktor")], kl)[0] == "DR.M.OZTURK"

    db.query(models.SigortaKisaKodu).filter_by(kod="HDI").one().aktif = False
    db.query(models.ClientCategory).filter_by(code="DOKTOR").one().ofis_no_kodu = "DK"
    db.add(models.ClientCategory(code="VAKIF", name="Vakıf", ofis_no_kodu="VK", active=True))
    db.commit()
    kl = ofis_no.kod_listelerini_yukle(db)
    assert ofis_no.musteri_kodu([_m("HDI SİGORTA A.Ş")], kl)[0] == "SG"          # pasif → SG
    assert ofis_no.musteri_kodu([_m("Mehmet Öztürk", "Doktor")], kl)[0] == "DK.M.OZTURK"
    assert ofis_no.musteri_kodu([_m("Şifa Vakfı", "Vakıf")], kl)[0] == "VK.SIFA"  # yönetimin eklediği kategori
    assert ofis_no.onizle(db, [_m("HDI SİGORTA A.Ş")], "Hukuk")["numara"] == "SG-0001-HUK"
    db.close()


# ─── admin uçları ────────────────────────────────────────────────────────────

def test_admin_uclari_yetkisiz_403(tohumlu, monkeypatch):
    istemci = _istemci(monkeypatch, "kullanici@example.com")
    sid = _sigorta_id(tohumlu, "AXA")
    assert istemci.get("/api/admin/sigorta-kodlari").status_code == 403
    assert istemci.post("/api/admin/sigorta-kodlari", json={"kod": "RAY", "ad": "Ray Sigorta"}).status_code == 403
    assert istemci.patch(f"/api/admin/sigorta-kodlari/{sid}", json={"aktif": False}).status_code == 403
    assert istemci.get("/api/admin/kategori-kodlari").status_code == 403
    assert istemci.patch("/api/admin/kategori-kodlari/DOKTOR", json={"ofis_no_kodu": "DK"}).status_code == 403
    db = tohumlu()
    assert db.query(models.SigortaKisaKodu).filter_by(kod="AXA").one().aktif is True
    assert db.query(models.SigortaKisaKodu).filter_by(kod="RAY").count() == 0
    assert db.query(models.ClientCategory).filter_by(code="DOKTOR").one().ofis_no_kodu == "DR"
    db.close()


def _sigorta_id(fabrika, kod):
    db = fabrika()
    try:
        return db.query(models.SigortaKisaKodu).filter_by(kod=kod).one().id
    finally:
        db.close()


def test_admin_sigorta_kodu_listele_ekle_guncelle(tohumlu, monkeypatch):
    istemci = _istemci(monkeypatch, ADMIN)
    liste = istemci.get("/api/admin/sigorta-kodlari").json()
    assert [k["kod"] for k in liste["kodlar"]][:3] == ["AK", "ANADOLU", "AXA"]
    assert liste["varsayilan_kod"] == "SG"
    assert liste["kodlar"][0] == {"id": liste["kodlar"][0]["id"], "kod": "AK", "ad": "AK Sigorta",
                                  "eslesme_anahtarlari": ["AK", "AKSIGORTA"], "aktif": True}

    yanit = istemci.post("/api/admin/sigorta-kodlari",
                         json={"kod": "RAY", "ad": " Ray Sigorta ", "eslesme_anahtarlari": ["ray", "Vienna İnsurance"]})
    assert yanit.status_code == 201
    yeni = yanit.json()
    assert yeni["kod"] == "RAY" and yeni["ad"] == "Ray Sigorta" and yeni["aktif"] is True
    assert yeni["eslesme_anahtarlari"] == ["RAY", "VIENNA INSURANCE"]

    db = tohumlu()
    kl = ofis_no.kod_listelerini_yukle(db)
    assert ofis_no.musteri_kodu([_m("Ray Sigorta A.Ş.")], kl)[0] == "RAY"
    assert ofis_no.musteri_kodu([_m("Vienna Insurance Group Sigorta")], kl)[0] == "RAY"
    db.close()

    # Boş anahtar listesi → kodun kendisi
    bos = istemci.post("/api/admin/sigorta-kodlari", json={"kod": "ALLIANZ", "ad": "Allianz Sigorta"})
    assert bos.status_code == 201 and bos.json()["eslesme_anahtarlari"] == ["ALLIANZ"]

    # PATCH: yalnız gönderilen alan değişir; pasife alma silme DEĞİL
    guncel = istemci.patch(f"/api/admin/sigorta-kodlari/{yeni['id']}", json={"aktif": False})
    assert guncel.status_code == 200
    assert guncel.json() == {**yeni, "aktif": False}
    db = tohumlu()
    assert ofis_no.musteri_kodu([_m("Ray Sigorta A.Ş.")], ofis_no.kod_listelerini_yukle(db))[0] == "SG"
    assert db.query(models.SigortaKisaKodu).filter_by(kod="RAY").count() == 1
    db.close()

    yeniden = istemci.patch(f"/api/admin/sigorta-kodlari/{yeni['id']}",
                            json={"kod": "RAYS", "ad": "Ray Sigorta A.Ş.", "aktif": True})
    assert yeniden.status_code == 200 and yeniden.json()["kod"] == "RAYS"
    assert istemci.patch("/api/admin/sigorta-kodlari/999999", json={"aktif": False}).status_code == 404
    # Silme ucu yok
    assert istemci.delete(f"/api/admin/sigorta-kodlari/{yeni['id']}").status_code == 405


@pytest.mark.parametrize("kod", ["a", "A", "axa", "AX1", "ABCDEFGHIJK", "ÇŞ", "AX A", ""])
def test_admin_kod_bicimi_2_10_buyuk_ascii(tohumlu, monkeypatch, kod):
    istemci = _istemci(monkeypatch, ADMIN)
    assert istemci.post("/api/admin/sigorta-kodlari", json={"kod": kod, "ad": "X Sigorta"}).status_code == 422
    assert istemci.patch("/api/admin/kategori-kodlari/DOKTOR", json={"ofis_no_kodu": kod}).status_code == 422
    sid = _sigorta_id(tohumlu, "AXA")
    assert istemci.patch(f"/api/admin/sigorta-kodlari/{sid}", json={"kod": kod}).status_code == 422


def test_kategori_kodu_ile_sigorta_kodu_cakisamaz(tohumlu, monkeypatch):
    istemci = _istemci(monkeypatch, ADMIN)
    sid = _sigorta_id(tohumlu, "AXA")
    # sigorta tarafı: kategori kodu, SG ve mevcut sigorta kodu reddedilir
    for kod in ("DR", "KR", "SG", "AXA"):
        assert istemci.post("/api/admin/sigorta-kodlari", json={"kod": kod, "ad": "X"}).status_code == 409, kod
    for kod in ("HS", "SG", "KORU"):
        assert istemci.patch(f"/api/admin/sigorta-kodlari/{sid}", json={"kod": kod}).status_code == 409, kod
    # kategori tarafı: sigorta kodu (pasif olsa da) ve SG reddedilir
    hdi = _sigorta_id(tohumlu, "HDI")
    assert istemci.patch(f"/api/admin/sigorta-kodlari/{hdi}", json={"aktif": False}).status_code == 200
    for kod in ("AXA", "HDI", "SG"):
        yanit = istemci.patch("/api/admin/kategori-kodlari/DOKTOR", json={"ofis_no_kodu": kod})
        assert yanit.status_code == 409, kod
    # yönetimin kategoriye verdiği YENİ kod da sigorta tarafında yasaklanır
    assert istemci.patch("/api/admin/kategori-kodlari/DOKTOR", json={"ofis_no_kodu": "HEKIM"}).status_code == 200
    assert istemci.post("/api/admin/sigorta-kodlari", json={"kod": "HEKIM", "ad": "X"}).status_code == 409

    db = tohumlu()
    assert db.query(models.SigortaKisaKodu).count() == 11
    assert db.query(models.SigortaKisaKodu).filter_by(id=sid).one().kod == "AXA"
    assert db.query(models.ClientCategory).filter_by(code="DOKTOR").one().ofis_no_kodu == "HEKIM"
    db.close()


def test_servis_cakisma_kurallari(tohumlu):
    db = tohumlu()
    with pytest.raises(ofis_no.KodCakismasi):
        ofis_no.sigorta_kodu_kullanilabilir(db, "OH")
    with pytest.raises(ofis_no.KodCakismasi):
        ofis_no.kategori_kodu_kullanilabilir(db, "QUICK")
    with pytest.raises(ValueError):
        ofis_no.kategori_kodu_kullanilabilir(db, "q")
    assert ofis_no.sigorta_kodu_kullanilabilir(db, "RAY") == "RAY"
    assert ofis_no.kategori_kodu_kullanilabilir(db, "OH") == "OH"      # kategoriler kodu paylaşabilir (Klinik → OH)
    axa = db.query(models.SigortaKisaKodu).filter_by(kod="AXA").one()
    assert ofis_no.sigorta_kodu_kullanilabilir(db, "AXA", haric_id=axa.id) == "AXA"
    db.close()


def test_admin_kategori_kodu_listele_guncelle_mevcut_numara_degismez(tohumlu, monkeypatch):
    db = tohumlu()
    db.add(models.Case(tracking_no="DR.M.OZTURK-0003-HUK", status="DERDEST",
                       ofis_no_kodu="DR.M.OZTURK", ofis_no_sira=3))
    db.commit()
    db.close()
    istemci = _istemci(monkeypatch, ADMIN)
    liste = istemci.get("/api/admin/kategori-kodlari").json()["kategoriler"]
    assert {k["code"]: k["ofis_no_kodu"] for k in liste}["DOKTOR"] == "DR"
    assert {k["code"]: k["ofis_no_kodu"] for k in liste}["SIGORTA"] is None

    yanit = istemci.patch("/api/admin/kategori-kodlari/DOKTOR", json={"ofis_no_kodu": "DK"})
    assert yanit.status_code == 200
    assert yanit.json() == {"code": "DOKTOR", "name": "Doktor", "ofis_no_kodu": "DK", "active": True}
    assert istemci.patch("/api/admin/kategori-kodlari/YOK", json={"ofis_no_kodu": "DK"}).status_code == 404

    db = tohumlu()
    kart = db.query(models.Case).one()
    assert (kart.tracking_no, kart.ofis_no_kodu, kart.ofis_no_sira) == ("DR.M.OZTURK-0003-HUK", "DR.M.OZTURK", 3)
    # yeni kart yeni kodu alır
    assert ofis_no.onizle(db, [_m("Mehmet Öztürk", "Doktor")], "Hukuk")["numara"] == "DK.M.OZTURK-0001-HUK"
    db.close()
