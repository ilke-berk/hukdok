"""Sihirbaz .eml genişletme testleri — POST /api/case-intake/expand-eml.

Sentetik multipart .eml fixture'ı: Türkçe karakterli HTML gövde + PDF ek +
inline PNG logo + .zip ek + .udf.zip ek + iç içe .eml. Gövde → PDF dönüşümü
soffice gerektirir; soffice'siz ortamda (host) gövde testleri atlanır, ek
ayrıştırma testleri _render_body_pdf monkeypatch'iyle koşar.
"""
import base64
import io
import os
import time
import zipfile
from email.message import EmailMessage
from types import SimpleNamespace

import pytest
from PIL import Image

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

SUBJECT = "[Kayseri 3. Tüketici Mahkemesi-5002940510859-0-2026/371]"
BODY_HTML = (
    "<html><body><p>Sayın yetkili,</p>"
    "<p>Tebliğ bilgisi — T.T: 23/07/2026</p>"
    "<img src=\"cid:logo123\"><script>alert('x')</script>"
    "<p>Saygılarımızla, Quick Sigorta</p></body></html>"
)
BODY_PLAIN = "Sayın yetkili,\nTebliğ bilgisi — T.T: 23/07/2026\nSaygılarımızla, Quick Sigorta"


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, "PNG")
    return buf.getvalue()


def _zip_bytes(marker="icerik.txt"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(marker, "test")
    return buf.getvalue()


def _base_msg(html_body=True):
    msg = EmailMessage()
    msg["From"] = "hukuk@quicksigorta.com.tr"
    msg["To"] = "info@ornek.av.tr"
    msg["Subject"] = SUBJECT
    msg["Date"] = "Thu, 30 Jul 2026 10:00:00 +0300"
    msg.set_content(BODY_PLAIN)
    if html_body:
        msg.add_alternative(BODY_HTML, subtype="html")
    return msg


def _html_eml_bytes(html):
    """Verilen HTML gövdeyi taşıyan eksiz .eml (temizlik testleri için)."""
    msg = EmailMessage()
    msg["From"] = "saldirgan@ornek.test"
    msg["To"] = "info@ornek.av.tr"
    msg["Subject"] = SUBJECT
    msg["Date"] = "Thu, 30 Jul 2026 10:00:00 +0300"
    msg.set_content(BODY_PLAIN)
    msg.add_alternative(html, subtype="html")
    return bytes(msg)


def _full_eml_bytes():
    """Plan test fixture'ı: HTML gövde + PDF ek + inline logo + zip + udf.zip + nested eml."""
    msg = _base_msg()
    msg.add_attachment(
        b"%PDF-1.4 ustyazi", maintype="application", subtype="pdf",
        filename="ustyazi_77.pdf",
    )
    msg.add_attachment(
        _png_bytes(), maintype="image", subtype="png",
        filename="image001.png", cid="<logo123>",
    )
    msg.add_attachment(
        _zip_bytes(), maintype="application", subtype="zip",
        filename="belgeler.zip",
    )
    msg.add_attachment(
        _zip_bytes("content.xml"), maintype="application", subtype="zip",
        filename="dava_dilekcesi.udf.zip",
    )
    nested = EmailMessage()
    nested["From"] = "a@b.c"
    nested["Subject"] = "ic mail"
    nested.set_content("nested")
    msg.add_attachment(nested)
    return bytes(msg)


@pytest.fixture()
def env():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_user
    from routes import case_intake

    app = FastAPI()
    app.include_router(case_intake.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "name": "Test Kullanıcı", "preferred_username": "test@example.com",
    }
    return SimpleNamespace(client=TestClient(app), module=case_intake)


@pytest.fixture()
def fake_render(env, monkeypatch):
    """Gövde PDF dönüşümünü soffice'siz sahte PDF ile geçer (ek testleri için)."""
    calls = []

    def _fake(body_html):
        calls.append(body_html)
        return b"%PDF-1.4 fake-body"

    monkeypatch.setattr(env.module, "_render_body_pdf", _fake)
    return calls


def _post(env, content, filename="atama.eml"):
    return env.client.post(
        "/api/case-intake/expand-eml",
        files={"file": (filename, content, "message/rfc822")},
    )


def _soffice_missing():
    from pdf.format_converter import find_libreoffice

    return find_libreoffice() is None


requires_soffice = pytest.mark.skipif(
    _soffice_missing(), reason="LibreOffice (soffice) bulunamadı"
)


# ── ek ayrıştırma (soffice gerektirmez) ─────────────────────────────────────

def test_attachments_split_and_skipped(env, fake_render):
    r = _post(env, _full_eml_bytes())
    assert r.status_code == 200
    body = r.json()

    # Gövde sanal belgesi üretildi
    assert body["body"]["filename"] == "E-posta_govdesi.pdf"
    assert base64.b64decode(body["body"]["data_b64"]).startswith(b"%PDF")

    # PDF ek attachments'ta, .udf.zip → .udf normalize edilmiş
    names = [a["filename"] for a in body["attachments"]]
    assert "ustyazi_77.pdf" in names
    assert "dava_dilekcesi.udf" in names
    assert len(names) == 2
    pdf_entry = next(a for a in body["attachments"] if a["filename"] == "ustyazi_77.pdf")
    assert base64.b64decode(pdf_entry["data_b64"]) == b"%PDF-1.4 ustyazi"

    # Logo + zip + nested eml skipped'da
    skipped = {s["filename"]: s["reason"] for s in body["skipped"]}
    assert skipped["image001.png"] == "inline görsel"
    assert "uzantı desteklenmiyor" in skipped["belgeler.zip"]
    assert any("iç içe e-posta" in s["reason"] for s in body["skipped"])


def test_body_html_contains_subject_and_headers(env, fake_render):
    r = _post(env, _full_eml_bytes())
    assert r.status_code == 200
    # _render_body_pdf'e giden HTML: başlık tablosu + temizlenmiş gövde
    html = fake_render[0]
    assert SUBJECT in html
    assert "hukuk@quicksigorta.com.tr" in html
    assert "T.T: 23/07/2026" in html
    assert "<script" not in html.lower()
    assert "cid:logo123" not in html


def test_plain_text_only_mail(env, fake_render):
    r = _post(env, bytes(_base_msg(html_body=False)))
    assert r.status_code == 200
    body = r.json()
    assert body["body"]["filename"] == "E-posta_govdesi.pdf"
    assert body["attachments"] == []
    html = fake_render[0]
    assert SUBJECT in html
    assert "T.T: 23/07/2026" in html


def test_invalid_file_rejected_400(env, fake_render):
    r = _post(env, b"Bu bir e-posta degildir, rastgele metin.\n" * 10)
    assert r.status_code == 400
    assert "RFC822" in r.json()["detail"]


def test_pdf_content_rejected_400(env, fake_render):
    r = _post(env, b"%PDF-1.4 sahte icerik")
    assert r.status_code == 400


def test_oversize_rejected_413(env, fake_render, monkeypatch):
    monkeypatch.setattr(env.module, "MAX_UPLOAD_BYTES", 1024)
    r = _post(env, _full_eml_bytes())
    assert r.status_code == 413


def test_unnamed_part_gets_generated_name(env, fake_render):
    msg = _base_msg(html_body=False)
    msg.add_attachment(b"%PDF-1.4 adsiz", maintype="application", subtype="pdf")
    r = _post(env, bytes(msg))
    assert r.status_code == 200
    names = [a["filename"] for a in r.json()["attachments"]]
    assert any(n.startswith("ek_") and n.endswith(".pdf") for n in names)


# ── gövde HTML temizliği / SSRF regresyonu ──────────────────────────────────
#
# Gövde soffice ile PDF'e çevrilirken LibreOffice uzak kaynakları GERÇEKTEN
# çekiyordu (probe ile kanıtlandı: <table background="http://..."> için sunucu
# kaydında GET). Aşağıdaki testler taşıyıcıyı tek tek değil, "uzak şema taşıyan
# attribute" genel kuralını kanıtlar.

SSRF_HTML = (
    "<html><head>"
    "<style>@import url('http://evil.test/import.css');"
    " body { background: url(http://evil.test/css_bg.png); }</style>"
    '<meta http-equiv="refresh" content="0;url=http://evil.test/refresh">'
    "</head><body>"
    '<table background="http://evil.test/TABLE_PROBE.png"><tr>'
    '<td background="&#104;ttp://evil.test/entity.png">hücre</td></tr></table>'
    "<div style=\"background-image:url('http://evil.test/inline.png')\">stil</div>"
    '<img srcset="http://evil.test/srcset.png 2x" src="yerel.png">'
    '<video poster="//evil.test/poster.jpg"></video>'
    '<object data="http://evil.test/object.bin"></object>'
    '<a href="http://evil.test/link">Dava metni burada</a>'
    "</body></html>"
)


def test_remote_resource_attributes_stripped(env, fake_render):
    """Kabul kriteri: temizlik sonrası gövdede HİÇBİR uzak URL kalmaz."""
    r = _post(env, _html_eml_bytes(SSRF_HTML))
    assert r.status_code == 200
    html = fake_render[0]

    assert "evil.test" not in html          # hiçbir taşıyıcı sızmadı
    assert "http://" not in html
    assert "@import" not in html
    assert "url(" not in html.lower()       # style bloğu + inline style url()
    # Aşırı temizlik değil: gövde metni korunur
    assert "Dava metni burada" in html
    assert "hücre" in html


def test_table_background_probe_removed(env, fake_render):
    """Kanıtlanmış SSRF taşıyıcısının kendisi — img'e özel kural bunu kaçırıyordu."""
    html = '<html><body><table background="http://127.0.0.1:8765/TABLE_PROBE.png">' \
           "<tr><td>satır</td></tr></table></body></html>"
    r = _post(env, _html_eml_bytes(html))
    assert r.status_code == 200
    cleaned = fake_render[0]
    assert "TABLE_PROBE" not in cleaned
    assert "background" not in cleaned.lower()
    assert "satır" in cleaned               # tablo içeriği duruyor


def test_link_tag_removed(env, fake_render):
    """`_LINK_TAG_RE` kapsaması: yerel href'li <link> de sökülür."""
    r = _post(env, _html_eml_bytes(
        '<html><head><link rel="stylesheet" href="/yerel/stil.css"></head>'
        "<body><p>Gövde</p></body></html>"
    ))
    assert r.status_code == 200
    cleaned = fake_render[0]
    assert "<link" not in cleaned.lower()
    assert "stil.css" not in cleaned
    assert "Gövde" in cleaned


def test_cid_image_still_removed(env, fake_render):
    """Mevcut davranış korunur: cid: gömülü görsel etiketi komple silinir."""
    r = _post(env, _html_eml_bytes(
        '<html><body><img src="cid:logo123"><p>İmza</p></body></html>'
    ))
    assert r.status_code == 200
    cleaned = fake_render[0]
    assert "cid:logo123" not in cleaned
    assert "<img" not in cleaned.lower()
    assert "İmza" in cleaned


def test_local_attributes_preserved(env, fake_render):
    """Genel kural yalnız UZAK şemaları söker — yerel/göreli değerler kalır."""
    r = _post(env, _html_eml_bytes(
        '<html><body><p class="govde"><a href="/yerel/sayfa">bak</a>'
        '<span style="color:#ff0000">kırmızı</span></p></body></html>'
    ))
    assert r.status_code == 200
    cleaned = fake_render[0]
    assert 'class="govde"' in cleaned
    assert 'href="/yerel/sayfa"' in cleaned
    assert "color:#ff0000" in cleaned


# ── fail-closed: temizlik yapılamazsa ham HTML soffice'e GİTMEZ (G023) ──────

def test_sanitizer_failure_falls_back_to_plaintext(env, fake_render, monkeypatch):
    """Sanitizer istisna atarsa ya da boyut tavanı aşılırsa gövde düz-metin
    yoluna düşer; ham HTML hiçbir koşulda dönüştürücüye verilmez."""
    from services.html_sanitizer import SanitizerError

    payload = '<table background="http://failclosed.test/probe.png"><tr><td>Dava metni</td></tr></table>'

    def _boom(raw, **kwargs):
        raise SanitizerError("sentetik arıza")

    monkeypatch.setattr(env.module, "sanitize_email_html", _boom)
    r = _post(env, _html_eml_bytes(payload))
    assert r.status_code == 200
    html = fake_render[0]
    assert "failclosed.test" not in html          # ham HTML geçmedi
    assert "background" not in html.lower()        # gövde markup'ı düz metne indirildi
    assert "<pre" in html.lower()                 # düz-metin yolu
    assert "Dava metni" in html                   # metin kaybı yok
    assert SUBJECT in html                        # başlık tablosu duruyor


def test_size_cap_falls_back_to_plaintext(env, fake_render, monkeypatch):
    """Boyut tavanı da aynı fail-closed yoluna çıkar (istisna ile aynı kapı)."""
    from services import html_sanitizer

    monkeypatch.setattr(html_sanitizer, "MAX_HTML_CHARS", 50)
    payload = (
        '<table background="http://toobig.test/probe.png"><tr><td>'
        + "Dava metni uzun gövde " * 20
        + "</td></tr></table>"
    )
    r = _post(env, _html_eml_bytes(payload))
    assert r.status_code == 200
    html = fake_render[0]
    assert "toobig.test" not in html
    assert "<pre" in html.lower()
    assert "Dava metni uzun gövde" in html


# ── gerçek soffice ile gövde PDF'i (konteyner) ──────────────────────────────

@requires_soffice
def test_body_pdf_rendered_with_soffice(env):
    import fitz

    r = _post(env, _full_eml_bytes())
    assert r.status_code == 200
    pdf_bytes = base64.b64decode(r.json()["body"]["data_b64"])
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        text = "".join(page.get_text() for page in doc)
    assert "5002940510859" in text        # konu satırındaki hasar dosya no
    assert "2026/371" in text             # konu satırındaki esas no
    assert "T.T: 23/07/2026" in text      # tebliğ tarihi gövdede
    assert "Quick Sigorta" in text        # Türkçe içerik/imza bloğu


@requires_soffice
def test_plain_body_pdf_rendered_with_soffice(env):
    import fitz

    r = _post(env, bytes(_base_msg(html_body=False)))
    assert r.status_code == 200
    pdf_bytes = base64.b64decode(r.json()["body"]["data_b64"])
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        text = "".join(page.get_text() for page in doc)
    assert "T.T: 23/07/2026" in text
    assert "Sayın yetkili" in text


# ── AC6 canlı kanıt: gerçek soffice + gerçek dinleyici (G023) ───────────────
#
# "Çıktıda uzak URL yok" iddiası ancak dinleyicinin GERÇEKTEN kayıt tuttuğu
# kanıtlanırsa bir şey söyler. Bu yüzden İKİ test birlikte durur: pozitif
# kontrol ham yükün istek DOĞURDUĞUNU, asıl test temizlenmiş yükün
# doğurmadığını gösterir. Pozitif kontrol düşerse asıl test anlamsızdır.

class _ProbeListener:
    """Konteyner içi 127.0.0.1 dinleyicisi — soffice'in çektiği yolları kaydeder."""

    def __init__(self):
        import http.server
        import threading

        hits = self.hits = []

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_HEAD = do_GET
            do_POST = do_GET

            def log_message(self, *args):
                pass

        self._srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self._srv.server_address[1]
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._thread.start()

    def close(self):
        self._srv.shutdown()
        self._srv.server_close()
        self._thread.join(timeout=5)


def _probe_document(port):
    """13 vakalık korpus + allowlist taşıyıcı taraması tek belgede — sanitizer
    birim testleriyle ORTAK kaynak (iki yerde ayrışan korpus tutmamak için)."""
    from test_sanitizer_html import allowlisted_attr_probe, probe_payloads

    host = f"127.0.0.1:{port}"
    payloads = probe_payloads(host)
    html = (
        "<html><body>"
        + allowlisted_attr_probe(host)
        + "".join(payloads.values())   # dengesiz tırnak + EOF vakaları en sonda
        + "</body></html>"
    )
    return html, payloads


@requires_soffice
def test_probe_listener_records_raw_payload_positive_control(env, monkeypatch):
    """Pozitif kontrol: TEMİZLENMEMİŞ yük soffice'e verilince dinleyici kayıt tutar.

    G024 soffice profiline ikinci bir kat koydu (uzak kaynak çekme kapalı) — bu
    kat AÇIKKEN hiçbir yük istek üretemez, dolayısıyla bu pozitif kontrol HTML
    temizliğinin katmanını ölçemez hâle gelirdi. Burada BİLEREK devre dışı
    bırakılıyor: ölçülen şey G023'ün sanitizer katmanının tek başına gerekliliği.
    G024 katmanının kendi kanıtı test_format_converter.py'dedir.
    """
    import pdf.format_converter as fc
    monkeypatch.setattr(fc, "_seed_lo_profile", lambda profile_dir: None)
    listener = _ProbeListener()
    try:
        raw_html, _ = _probe_document(listener.port)
        pdf_bytes = env.module._render_body_pdf(raw_html)
        assert pdf_bytes.startswith(b"%PDF")
        time.sleep(1.0)  # soffice isteği dönüşüm sırasında atar; kaydın oturması için
        assert listener.hits, (
            "dinleyici hiç istek görmedi — kanıt düzeneği çalışmıyor, "
            "negatif testin 'boş kayıt' sonucu anlamsız"
        )
    finally:
        listener.close()


@requires_soffice
def test_no_outbound_request_after_sanitize(env):
    """AC6 asıl kanıt: aynı korpus uçtan uca /expand-eml'den geçince giden istek YOK."""
    listener = _ProbeListener()
    try:
        raw_html, payloads = _probe_document(listener.port)
        r = _post(env, _html_eml_bytes(raw_html))
        assert r.status_code == 200
        pdf_bytes = base64.b64decode(r.json()["body"]["data_b64"])
        assert pdf_bytes.startswith(b"%PDF")
        assert len(payloads) == 13
        time.sleep(1.0)
        assert listener.hits == [], f"soffice uzak kaynak çekti: {listener.hits}"
    finally:
        listener.close()
