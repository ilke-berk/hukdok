"""Sihirbaz .eml genişletme testleri — POST /api/case-intake/expand-eml.

Sentetik multipart .eml fixture'ı: Türkçe karakterli HTML gövde + PDF ek +
inline PNG logo + .zip ek + .udf.zip ek + iç içe .eml. Gövde → PDF dönüşümü
soffice gerektirir; soffice'siz ortamda (host) gövde testleri atlanır, ek
ayrıştırma testleri _render_body_pdf monkeypatch'iyle koşar.
"""
import base64
import io
import os
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
