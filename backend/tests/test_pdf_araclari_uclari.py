"""G268 — PDF araçları uçları (`/api/pdf-araclari/{yukle,islem,onizleme}` + mevcut `/api/download`).

Kalıp: `test_g078_son_belgeler_ucu.py` (bare FastAPI + `dependency_overrides[get_current_user]` +
`TestClient(raise_server_exceptions=False)`). DB yok. Cache dizini ve PDF_ARACLARI_DIR geçici dizine yönlendirilir
(conftest DOWNLOAD_CACHE_DIR'i zaten tmp'ye alır; PDF_ARACLARI_DIR çağrı anında çözülür → monkeypatch env).

Kilitlenen davranışlar: yükle → işlem → önizleme → indir zinciri; başkasının id'si 404; 21 girdi 422; yanlış islem /
parametre 422; semafor dolu 503; ZamanAsimi 504; SayfaSinirAsildi 413; magic-byte sahte .pdf 415; uzantı 415; boyut 413;
rate limit sabiti; Cache-Control; nginx bekçisi (yollar `/api/` altında, `nginx.conf`'ta `pdf-araclari` yok).
"""
import io
import os
import threading
from pathlib import Path

import fitz
import pytest
from PIL import Image

USER_A = {"preferred_username": "a@hanyaloglu.com"}
USER_B = {"preferred_username": "b@hanyaloglu.com"}
BACKEND_DIR = Path(__file__).resolve().parent.parent
NGINX = BACKEND_DIR.parent / "nginx.conf"


def _pdf_bytes(metinler=("BIR", "IKI", "UC"), rotation=0) -> bytes:
    with fitz.open() as doc:
        for m in metinler:
            page = doc.new_page(width=600, height=800)
            page.insert_text((50, 100), m, fontsize=20)
            if rotation:
                page.set_rotation(rotation)
        return doc.tobytes()


@pytest.fixture(autouse=True)
def _limiter_sifirla():
    from rate_limiting import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def client_factory(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import pdf_araclari as route_mod
    from routes import processing

    monkeypatch.setenv("PDF_ARACLARI_DIR", str(tmp_path / "pdf_araclari"))

    def _make(user: dict = USER_A):
        app = FastAPI()
        app.include_router(route_mod.router)
        app.include_router(processing.router)  # /api/download mevcut uç
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    _make.route = route_mod  # type: ignore[attr-defined]
    _make.processing = processing  # type: ignore[attr-defined]
    _make.dir = tmp_path / "pdf_araclari"  # type: ignore[attr-defined]
    return _make


def _yukle(client, icerik: bytes, ad="dilekce.pdf", tur="application/pdf"):
    return client.post("/api/pdf-araclari/yukle", files={"file": (ad, icerik, tur)})


def _islem(client, islem, girdiler, parametreler=None, **ek):
    govde = {"islem": islem, "girdiler": girdiler, "parametreler": parametreler or {}}
    govde.update(ek)
    return client.post("/api/pdf-araclari/islem", json=govde)


# ── yükle ────────────────────────────────────────────────────────────────────

class TestYukle:
    def test_pdf_yukle_dosya_nesnesi(self, client_factory):
        client = client_factory()
        r = _yukle(client, _pdf_bytes())
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(d) == {"id", "ad", "sayfa", "boyut", "sayfalar"}
        assert d["ad"] == "dilekce.pdf" and d["sayfa"] == 3 and d["boyut"] > 0
        assert d["sayfalar"][0] == {"no": 1, "genislik": 600.0, "yukseklik": 800.0}
        kayit = client_factory.processing.DOWNLOAD_CACHE.get(d["id"])
        assert kayit["kaynak"] == "pdf_araclari" and kayit["owner"] == "a@hanyaloglu.com"
        assert kayit["sayfa"] == 3 and Path(kayit["path"]).parent == client_factory.dir
        assert Path(kayit["path"]).name == f"{d['id']}.pdf"

    def test_png_yukle_pdf_olur(self, client_factory):
        buf = io.BytesIO()
        Image.new("RGB", (80, 60), (0, 128, 0)).save(buf, "PNG")
        r = _yukle(client_factory(), buf.getvalue(), ad="foto.png", tur="image/png")
        assert r.status_code == 200, r.text
        assert r.json()["ad"] == "foto.pdf" and r.json()["sayfa"] == 1

    def test_uzanti_415(self, client_factory):
        r = _yukle(client_factory(), b"x", ad="zararli.exe", tur="application/octet-stream")
        assert r.status_code == 415
        assert r.json()["detail"]["error_kod"] == "uzanti"

    def test_sahte_pdf_magic_byte_415(self, client_factory):
        r = _yukle(client_factory(), b"bu pdf degil ama uzantisi pdf")
        assert r.status_code == 415
        assert r.json()["detail"]["error_kod"] == "dosya_turu"

    def test_boyut_413(self, client_factory, monkeypatch):
        monkeypatch.setattr(client_factory.route, "MAX_UPLOAD_BYTES", 100)
        r = _yukle(client_factory(), _pdf_bytes())
        assert r.status_code == 413

    def test_bos_dosya_422(self, client_factory):
        r = _yukle(client_factory(), b"")
        assert r.status_code == 422

    def test_donusum_kuyrugu_dolu_503(self, client_factory, monkeypatch):
        from pdf.format_converter import ConversionBusyError

        def _dolu(*a, **k):
            raise ConversionBusyError("PDF aracı")

        monkeypatch.setattr(client_factory.route, "acquire_conversion_slot", _dolu)
        r = _yukle(client_factory(), _pdf_bytes())
        assert r.status_code == 503
        assert r.json()["detail"]["error_kod"] == "sistem_mesgul"

    def test_donusum_basarisiz_422(self, client_factory, monkeypatch):
        def _patla(*a, **k):
            raise RuntimeError("LibreOffice öldü")

        monkeypatch.setattr(client_factory.route.cekirdek, "pdf_ye_cevir", _patla)
        r = _yukle(client_factory(), _pdf_bytes())
        assert r.status_code == 422
        assert r.json()["detail"]["error_kod"] == "donusum_basarisiz"

    def test_ham_dosya_silinir(self, client_factory, monkeypatch):
        import tempfile

        olusanlar = []
        orijinal = tempfile.mkdtemp

        def _izle(*a, **k):
            d = orijinal(*a, **k)
            olusanlar.append(d)
            return d

        monkeypatch.setattr(client_factory.route.tempfile, "mkdtemp", _izle)
        assert _yukle(client_factory(), _pdf_bytes()).status_code == 200
        assert olusanlar and not os.path.exists(olusanlar[0])


# ── işlem zinciri ────────────────────────────────────────────────────────────

class TestIslemZinciri:
    def test_yukle_birlestir_bol_onizleme_indir(self, client_factory):
        client = client_factory()
        a = _yukle(client, _pdf_bytes(("A1", "A2"))).json()
        b = _yukle(client, _pdf_bytes(("B1",)), ad="ek.pdf").json()

        r = _islem(client, "birlestir", [b["id"], a["id"]])
        assert r.status_code == 200, r.text
        [birlesik] = r.json()["ciktilar"]
        assert birlesik["sayfa"] == 3 and birlesik["ad"] == "birlestirilmis.pdf"

        r = _islem(client, "bol", [birlesik["id"]], {"araliklar": [[1, 1], [2, 3]]})
        assert r.status_code == 200, r.text
        parcalar = r.json()["ciktilar"]
        assert [p["ad"] for p in parcalar] == ["birlestirilmis_1-1.pdf", "birlestirilmis_2-3.pdf"]
        assert [p["sayfa"] for p in parcalar] == [1, 2]

        r = client.get(f"/api/pdf-araclari/onizleme/{parcalar[1]['id']}/2?genislik=120")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert r.headers["cache-control"] == "private, max-age=3600"
        assert Image.open(io.BytesIO(r.content)).size == (120, 160)

        r = client.get(f"/api/download/{parcalar[1]['id']}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert 'filename="birlestirilmis_2-3.pdf"' in r.headers["content-disposition"]
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            assert [p.get_text().strip() for p in doc] == ["A1", "A2"]

    def test_cikti_adi_sanitize(self, client_factory):
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()
        r = _islem(client, "damga", [a["id"]], {"metin": "ASLI GİBİDİR", "konum": "sag-ust"}, cikti_adi="../gizli/<x>.pdf")
        assert r.status_code == 200, r.text
        ad = r.json()["ciktilar"][0]["ad"]
        assert "/" not in ad and "<" not in ad and ad.endswith(".pdf")

    @pytest.mark.parametrize(
        "islem,parametreler",
        [
            ("sayfa_duzenle", {"sayfalar": [{"no": 3, "dondur": 90}, {"no": 1}]}),
            ("karart", {"alanlar": [{"sayfa": 1, "x0": 40, "y0": 70, "x1": 200, "y1": 120}]}),
            ("damga", {"metin": "ÖRNEK", "konum": "orta", "sayfalar": [1], "punto": 18, "renk": "#0000ff"}),
            ("not", {"sayfa": 2, "x": 100, "y": 100, "metin": "Dikkat"}),
            ("donustur", {}),
        ],
    )
    def test_tek_girdili_islemler(self, client_factory, islem, parametreler):
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()
        r = _islem(client, islem, [a["id"]], parametreler)
        assert r.status_code == 200, r.text
        [c] = r.json()["ciktilar"]
        assert c["id"] != a["id"] and c["sayfa"] >= 1
        assert client_factory.processing.DOWNLOAD_CACHE.get(c["id"])["kaynak"] == "pdf_araclari"
        if islem == "karart":
            with fitz.open(client_factory.processing.DOWNLOAD_CACHE.get(c["id"])["path"]) as doc:
                assert "BIR" not in doc[0].get_text()
        if islem == "sayfa_duzenle":
            assert c["sayfa"] == 2 and c["sayfalar"][0] == {"no": 1, "genislik": 800.0, "yukseklik": 600.0}

    def test_sikistir_kucultme_alani(self, client_factory, monkeypatch):
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()
        yol = client_factory.processing.DOWNLOAD_CACHE.get(a["id"])["path"]
        monkeypatch.setattr(client_factory.route.cekirdek, "sikistir", lambda *args, **kw: (yol, 0))
        # çekirdek sahte: aynı dosyayı "kucultme 0" ile döndürür → route cache'e yazar
        r = _islem(client, "sikistir", [a["id"]], {"seviye": "ekran"})
        assert r.status_code == 200, r.text
        assert r.json()["ciktilar"][0]["kucultme"] == 0

    def test_girdiler_tekrar_kullanilabilir(self, client_factory):
        """Zincirde girdiler silinmez (TTL siler)."""
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()
        assert _islem(client, "bol", [a["id"]], {"her_n": 1}).status_code == 200
        assert _islem(client, "bol", [a["id"]], {"her_n": 2}).status_code == 200


# ── sahiplik / sınırlar / hata eşlemesi ──────────────────────────────────────

class TestSahiplikVeSinirlar:
    def test_baska_kullanicinin_idsi_404(self, client_factory):
        a = _yukle(client_factory(USER_A), _pdf_bytes()).json()
        b = client_factory(USER_B)
        assert _islem(b, "bol", [a["id"]], {"her_n": 1}).status_code == 404
        assert b.get(f"/api/pdf-araclari/onizleme/{a['id']}/1").status_code == 404
        assert b.get(f"/api/download/{a['id']}").status_code == 404

    def test_process_kaydi_pdf_araclarinda_404(self, client_factory, tmp_path):
        """`kaynak` pdf_araclari olmayan DOWNLOAD_CACHE kaydı (örn. /confirm çıktısı) bu uçlarda görünmez."""
        client = client_factory()
        yol = tmp_path / "confirm.pdf"
        yol.write_bytes(_pdf_bytes())
        client_factory.processing.DOWNLOAD_CACHE.set("confirm-1", {"path": str(yol), "filename": "x.pdf", "owner": "a@hanyaloglu.com"})
        assert _islem(client, "bol", ["confirm-1"], {"her_n": 1}).status_code == 404
        assert client.get("/api/pdf-araclari/onizleme/confirm-1/1").status_code == 404
        assert client.get("/api/download/confirm-1").status_code == 200  # mevcut uç değişmedi

    def test_bilinmeyen_id_404(self, client_factory):
        client = client_factory()
        assert _islem(client, "bol", ["yok"], {"her_n": 1}).status_code == 404
        assert client.get("/api/pdf-araclari/onizleme/yok/1").status_code == 404

    def test_diskten_silinmis_404(self, client_factory):
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()
        os.remove(client_factory.processing.DOWNLOAD_CACHE.get(a["id"])["path"])
        assert client.get(f"/api/pdf-araclari/onizleme/{a['id']}/1").status_code == 404
        assert client_factory.processing.DOWNLOAD_CACHE.get(a["id"]) is None

    def test_21_girdi_422(self, client_factory):
        r = _islem(client_factory(), "birlestir", [f"id-{i}" for i in range(21)])
        assert r.status_code == 422
        assert r.json()["detail"]["error_kod"] == "girdi_siniri"

    def test_tek_girdili_isleme_iki_girdi_422(self, client_factory):
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()
        r = _islem(client, "bol", [a["id"], a["id"]], {"her_n": 1})
        assert r.status_code == 422 and r.json()["detail"]["error_kod"] == "girdi_sayisi"

    def test_yanlis_islem_422(self, client_factory):
        assert _islem(client_factory(), "ocr", ["x"]).status_code == 422

    def test_bos_girdi_listesi_422(self, client_factory):
        assert _islem(client_factory(), "birlestir", []).status_code == 422

    @pytest.mark.parametrize(
        "islem,parametreler",
        [
            ("bol", {}),
            ("bol", {"araliklar": [[1, 2]], "her_n": 1}),
            ("bol", {"her_n": 0}),
            ("bol", {"araliklar": [[1, 5]]}),  # aşım: çekirdek yakalar
            ("bol", {"araliklar": [[1]]}),
            ("sayfa_duzenle", {"sayfalar": []}),
            ("sayfa_duzenle", {"sayfalar": [{"no": 1, "dondur": 45}]}),
            ("sayfa_duzenle", {"sayfalar": [{"no": 1}], "fazla": 1}),
            ("sikistir", {"seviye": "maksimum"}),
            ("karart", {"alanlar": []}),
            ("karart", {"alanlar": [{"sayfa": 9, "x0": 0, "y0": 0, "x1": 10, "y1": 10}]}),
            ("damga", {"metin": "x" * 121, "konum": "orta"}),
            ("damga", {"metin": "x", "konum": "ust"}),
            ("damga", {"metin": "x", "konum": "orta", "renk": "kirmizi"}),
            ("not", {"sayfa": 1, "x": 1, "y": 1, "metin": "x" * 2001}),
            ("not", {"sayfa": 1, "x": 1, "y": 1}),
            ("birlestir", {"seviye": "ekran"}),
        ],
    )
    def test_parametre_422(self, client_factory, islem, parametreler):
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()
        r = _islem(client, islem, [a["id"]], parametreler)
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["error_kod"] == "parametre_hatasi"

    def test_sayfa_siniri_413(self, client_factory, monkeypatch):
        monkeypatch.setattr(client_factory.route.settings, "pdf_araclari_max_sayfa", 5)
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()
        r = _islem(client, "birlestir", [a["id"], a["id"]])
        assert r.status_code == 413 and r.json()["detail"]["error_kod"] == "sayfa_siniri"

    def test_semafor_dolu_503(self, client_factory, monkeypatch):
        monkeypatch.setattr(client_factory.route, "_pdf_arac_semaphore", threading.Semaphore(0))
        monkeypatch.setattr(client_factory.route.settings, "conversion_acquire_timeout_seconds", 0.05)
        client = client_factory()
        r = _yukle(client, _pdf_bytes())  # yükleme de aynı semafora takılır
        assert r.status_code == 503 and r.json()["detail"]["error_kod"] == "sistem_mesgul"
        assert _islem(client, "birlestir", ["yok"]).status_code == 404  # sahiplik semafordan önce

    def test_zaman_asimi_504(self, client_factory, monkeypatch):
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()

        def _asim(*args, **kw):
            raise client_factory.route.cekirdek.ZamanAsimi("bütçe doldu")

        monkeypatch.setattr(client_factory.route.cekirdek, "bol", _asim)
        r = _islem(client, "bol", [a["id"]], {"her_n": 1})
        assert r.status_code == 504 and r.json()["detail"]["error_kod"] == "zaman_asimi"

    def test_arac_yok_503(self, client_factory, monkeypatch):
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()

        def _yok(*args, **kw):
            raise client_factory.route.cekirdek.AracYok("gs yok")

        monkeypatch.setattr(client_factory.route.cekirdek, "sikistir", _yok)
        r = _islem(client, "sikistir", [a["id"]], {"seviye": "ekran"})
        assert r.status_code == 503 and r.json()["detail"]["error_kod"] == "arac_yok"

    def test_beklenmedik_hata_500_tek_error(self, client_factory, monkeypatch, caplog):
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()

        def _patla(*args, **kw):
            raise RuntimeError("beklenmedik")

        monkeypatch.setattr(client_factory.route.cekirdek, "bol", _patla)
        with caplog.at_level("ERROR", logger="routes.pdf_araclari"):
            r = _islem(client, "bol", [a["id"]], {"her_n": 1})
        assert r.status_code == 500 and r.json()["detail"]["error_kod"] == "islem_hatasi"
        assert sum(1 for rec in caplog.records if rec.levelname == "ERROR") == 1

    def test_onizleme_sinirlari(self, client_factory):
        client = client_factory()
        a = _yukle(client, _pdf_bytes()).json()
        assert client.get(f"/api/pdf-araclari/onizleme/{a['id']}/4").status_code == 404
        assert client.get(f"/api/pdf-araclari/onizleme/{a['id']}/0").status_code == 404
        assert client.get(f"/api/pdf-araclari/onizleme/{a['id']}/1?genislik=63").status_code == 422
        assert client.get(f"/api/pdf-araclari/onizleme/{a['id']}/1?genislik=1601").status_code == 422
        r = client.get(f"/api/pdf-araclari/onizleme/{a['id']}/1")
        assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).size[0] == 240

    def test_onizleme_donmus_sayfa(self, client_factory):
        client = client_factory()
        a = _yukle(client, _pdf_bytes(("A",), rotation=90)).json()
        r = client.get(f"/api/pdf-araclari/onizleme/{a['id']}/1?genislik=400")
        assert Image.open(io.BytesIO(r.content)).size == (400, 300)


# ── bekçiler ─────────────────────────────────────────────────────────────────

class TestBekci:
    def test_rate_limit_sabiti(self):
        from routes import pdf_araclari as route_mod

        from rate_limiting import limiter

        assert route_mod.HIZ_SINIRI == "30/minute"
        for ad in ("yukle", "islem", "karta_bagla", "karttan_al"):  # G269 iki ucu da sınırlı
            assert f"routes.pdf_araclari.{ad}" in limiter._route_limits, ad

    def test_yollar_api_altinda(self):
        from routes import pdf_araclari as route_mod

        yollar = sorted(r.path for r in route_mod.router.routes)
        assert yollar == [
            "/api/pdf-araclari/islem",
            "/api/pdf-araclari/karta-bagla",  # G269
            "/api/pdf-araclari/karttan-al",  # G269
            "/api/pdf-araclari/onizleme/{file_id}/{sayfa}",
            "/api/pdf-araclari/yukle",
        ]

    @pytest.mark.skipif(not NGINX.exists(), reason="repo kökü görünmüyor (konteynerde yalnız backend/)")
    def test_nginx_dokunulmadi(self):
        metin = NGINX.read_text(encoding="utf-8")
        assert "pdf-araclari" not in metin and "pdf_araclari" not in metin
        assert "location /api" in metin

    def test_api_kaydi(self):
        api_metin = (BACKEND_DIR / "api.py").read_text(encoding="utf-8")
        assert "app.include_router(pdf_araclari.router)" in api_metin

    def test_ayarlar(self):
        from config.settings import settings

        assert settings.pdf_araclari_max_sayfa == 1000
        assert settings.pdf_araclari_max_girdi == 20
        assert settings.pdf_araclari_butce_saniye + 30 <= settings.request_time_budget_seconds
