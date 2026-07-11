"""format_converter testleri.

Görüntü → PDF dönüşümü saf Pillow ile test edilir (harici bağımlılık yok).
Office → PDF testleri konteynerde koşar; soffice yoksa atlanır.
convert_to_pdfa2b dispatch testleri alt dönüştürücüleri mock'lar.
"""
import os
import shutil
import zipfile

import fitz  # pymupdf
import pytest
from PIL import Image

from pdf.format_converter import (
    CONVERTIBLE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    OFFICE_EXTENSIONS,
    ensure_pdf,
    image_to_pdf,
    office_to_pdf,
)


def _make_tiff(path, pages=3, size=(120, 80)):
    frames = [Image.new("RGB", size, color=(i * 40, 100, 200)) for i in range(pages)]
    frames[0].save(path, "TIFF", save_all=True, append_images=frames[1:])


def _pdf_page_count(pdf_path):
    with fitz.open(pdf_path) as doc:
        return doc.page_count


# ── image_to_pdf ─────────────────────────────────────────────────────────────

class TestImageToPdf:
    def test_multipage_tiff_roundtrip(self, tmp_path):
        src = tmp_path / "tarama.tif"
        _make_tiff(str(src), pages=3)
        out = image_to_pdf(str(src), str(tmp_path / "out.pdf"))
        assert _pdf_page_count(out) == 3

    def test_single_page_jpg(self, tmp_path):
        src = tmp_path / "foto.jpg"
        Image.new("RGB", (100, 100), "red").save(str(src), "JPEG")
        out = image_to_pdf(str(src), str(tmp_path / "out.pdf"))
        assert _pdf_page_count(out) == 1

    def test_rgba_png_normalized(self, tmp_path):
        # RGBA doğrudan PDF'e gömülemez — RGB'ye çevrilmeli
        src = tmp_path / "ekran.png"
        Image.new("RGBA", (100, 100), (255, 0, 0, 128)).save(str(src), "PNG")
        out = image_to_pdf(str(src), str(tmp_path / "out.pdf"))
        assert _pdf_page_count(out) == 1

    def test_temp_output_when_no_path_given(self, tmp_path):
        src = tmp_path / "foto.png"
        Image.new("RGB", (50, 50), "blue").save(str(src), "PNG")
        out = image_to_pdf(str(src))
        try:
            assert out.endswith(".pdf")
            assert _pdf_page_count(out) == 1
        finally:
            os.remove(out)

    def test_corrupt_image_raises(self, tmp_path):
        src = tmp_path / "bozuk.tif"
        src.write_bytes(b"II*\x00" + b"\xff" * 32)
        with pytest.raises(RuntimeError):
            image_to_pdf(str(src), str(tmp_path / "out.pdf"))


# ── ensure_pdf dispatch ──────────────────────────────────────────────────────

class TestEnsurePdf:
    def test_image_dispatch(self, tmp_path, monkeypatch):
        import pdf.format_converter as fc
        called = {}
        monkeypatch.setattr(fc, "image_to_pdf", lambda s, o=None: called.update(img=s) or "x.pdf")
        assert fc.ensure_pdf("belge.tiff") == "x.pdf"
        assert called["img"] == "belge.tiff"

    def test_office_dispatch(self, tmp_path, monkeypatch):
        import pdf.format_converter as fc
        called = {}
        monkeypatch.setattr(fc, "office_to_pdf", lambda s, o=None: called.update(office=s) or "x.pdf")
        assert fc.ensure_pdf("belge.xlsx") == "x.pdf"
        assert called["office"] == "belge.xlsx"

    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError):
            ensure_pdf("belge.txt")

    def test_extension_sets_consistent(self):
        assert CONVERTIBLE_EXTENSIONS == IMAGE_EXTENSIONS | OFFICE_EXTENSIONS
        assert ".pdf" not in CONVERTIBLE_EXTENSIONS
        assert ".udf" not in CONVERTIBLE_EXTENSIONS


# ── office_to_pdf (LibreOffice gerektirir — konteynerde koşar) ───────────────

_soffice_missing = shutil.which("soffice") is None


@pytest.mark.skipif(_soffice_missing, reason="LibreOffice (soffice) kurulu değil")
class TestOfficeToPdf:
    def test_xlsx_to_pdf(self, tmp_path):
        from openpyxl import Workbook
        src = tmp_path / "tablo.xlsx"
        wb = Workbook()
        ws = wb.active
        ws["A1"] = "Dava No"
        ws["B1"] = "2024/123 Esas"
        wb.save(str(src))

        out = office_to_pdf(str(src), str(tmp_path / "out.pdf"))
        assert _pdf_page_count(out) >= 1

    def test_docx_to_pdf(self, tmp_path):
        # Minimal geçerli OOXML docx (python-docx bağımlılığı olmadan)
        src = tmp_path / "belge.docx"
        with zipfile.ZipFile(src, "w") as z:
            z.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>",
            )
            z.writestr(
                "_rels/.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                "</Relationships>",
            )
            z.writestr(
                "word/document.xml",
                '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Gerekçeli karar örneği — Türkçe ğüşiöç</w:t></w:r></w:p></w:body></w:document>",
            )

        out = office_to_pdf(str(src), str(tmp_path / "out.pdf"))
        assert _pdf_page_count(out) >= 1

    def test_corrupt_docx_raises(self, tmp_path):
        src = tmp_path / "bozuk.docx"
        src.write_bytes(b"PK\x03\x04 bozuk arsiv")
        with pytest.raises(RuntimeError):
            office_to_pdf(str(src), str(tmp_path / "out.pdf"))


# ── convert_to_pdfa2b dispatch ───────────────────────────────────────────────

class TestConvertToPdfa2bDispatch:
    def test_image_goes_through_image_branch(self, tmp_path, monkeypatch):
        import pdf.pdf_converter as pc
        src = tmp_path / "tarama.tif"
        _make_tiff(str(src), pages=2)

        # GhostScript adımını kopyalamayla taklit et — ara PDF çıktıya taşınır
        def _fake_gs(s, o):
            shutil.copy(s, o)
            return o

        monkeypatch.setattr(pc, "_pdf_to_pdfa2b", _fake_gs)
        result = pc.convert_to_pdfa2b(str(src))
        try:
            assert result != str(src)
            assert _pdf_page_count(result) == 2
        finally:
            os.remove(result)

    def test_office_failure_raises_not_fallback(self, tmp_path, monkeypatch):
        import pdf.pdf_converter as pc
        src = tmp_path / "bozuk.xlsx"
        src.write_bytes(b"PK\x03\x04 bozuk")

        def _boom(s, o=None):
            raise RuntimeError("LibreOffice dönüşüm hatası")

        monkeypatch.setattr(pc, "office_to_pdf", _boom)
        with pytest.raises(RuntimeError):
            pc.convert_to_pdfa2b(str(src))

    def test_image_failure_raises_not_fallback(self, tmp_path, monkeypatch):
        import pdf.pdf_converter as pc
        src = tmp_path / "bozuk.tif"
        src.write_bytes(b"II*\x00 bozuk")

        def _boom(s, o=None):
            raise RuntimeError("Görüntü dönüşüm hatası")

        monkeypatch.setattr(pc, "image_to_pdf", _boom)
        with pytest.raises(RuntimeError):
            pc.convert_to_pdfa2b(str(src))

    def test_unsupported_extension_raises_valueerror(self, tmp_path):
        import pdf.pdf_converter as pc
        src = tmp_path / "belge.txt"
        src.write_bytes(b"metin")
        with pytest.raises(ValueError):
            pc.convert_to_pdfa2b(str(src))
