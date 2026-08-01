"""file_utils saf fonksiyon testleri.

Denetim planı 2.1/1: _normalize_doctype_code bilinen tuzağı
("ARA-KRR_______" vs "ARA-KRR") ve dosya doğrulama guard'larını kilitler.
"""
import zipfile

import pytest
from fastapi import HTTPException

from file_utils import (
    _normalize_doctype_code,
    normalize_date_for_sharepoint,
    safe_remove,
    sanitize_filename,
    validate_file_size,
    validate_file_type,
)


# ── _normalize_doctype_code ──────────────────────────────────────────────────

class TestNormalizeDoctypeCode:
    def test_padded_equals_short(self):
        # Bilinen tuzak: config kodları "_" ile sabit genişliğe pad'lidir
        assert _normalize_doctype_code("ARA-KRR_______") == _normalize_doctype_code("ARA-KRR")

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("ARA-KRR_______", "ARAKRR"),
            ("ARA-KRR", "ARAKRR"),
            ("ara-krr", "ARAKRR"),
            ("ARA KRR", "ARAKRR"),
            ("ARA_KRR", "ARAKRR"),
            ("ARA.KRR", "ARAKRR"),
            ("GEREKCELI-KRR", "GEREKCELIKRR"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_variants(self, raw, expected):
        assert _normalize_doctype_code(raw) == expected

    def test_distinct_codes_stay_distinct(self):
        assert _normalize_doctype_code("ARA-KRR") != _normalize_doctype_code("ARA-KRR2")


# ── normalize_date_for_sharepoint ────────────────────────────────────────────

class TestNormalizeDateForSharepoint:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("240115", "2024-01-15"),        # %y%m%d
            ("15.01.2024", "2024-01-15"),
            ("2024-01-15", "2024-01-15"),
            ("20240115", "2024-01-15"),      # %Y%m%d
            ("15/01/2024", "2024-01-15"),
            ("15-01-2024", "2024-01-15"),
            ("  15.01.2024  ", "2024-01-15"),  # strip
        ],
    )
    def test_valid_formats(self, raw, expected):
        assert normalize_date_for_sharepoint(raw) == expected

    @pytest.mark.parametrize("raw", ["", None, "tarih değil", "15.01.24", "99.99.2024"])
    def test_invalid_returns_none(self, raw):
        assert normalize_date_for_sharepoint(raw) is None

    def test_pre_1900_rejected(self):
        assert normalize_date_for_sharepoint("01.01.1899") is None


# ── sanitize_filename ────────────────────────────────────────────────────────

class TestSanitizeFilename:
    def test_spaces_become_underscores(self):
        assert sanitize_filename("Gerekçeli Karar 2024.pdf") == "Gerekçeli_Karar_2024.pdf"

    def test_path_traversal_stripped(self):
        assert sanitize_filename("../../evil.pdf") == "evil.pdf"

    def test_null_bytes_removed(self):
        assert sanitize_filename("ev\x00il.pdf") == "evil.pdf"

    def test_unsafe_chars_replaced(self):
        # ':' ve '?' güvenli değil → '_'; ardışık '_' tekilleşir
        assert sanitize_filename("dava:no?1.pdf") == "dava_no_1.pdf"

    def test_trailing_underscore_keeps_extension(self):
        # Regresyon: '[_.]{2,}' regex'i '_.' ikilisini yutup uzantıyı
        # siliyordu ("KARARI_.pdf" → "KARARI_pdf"). Uzantı korunmalı.
        assert sanitize_filename("KARARI_.pdf").endswith(".pdf")

    def test_no_extension_rejected(self):
        with pytest.raises(HTTPException) as exc:
            sanitize_filename("uzantisiz")
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("name", ["zararli.exe", "script.js", "notlar.txt"])
    def test_disallowed_extension_rejected(self, name):
        with pytest.raises(HTTPException) as exc:
            sanitize_filename(name)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize(
        "name",
        ["belge.docx", "eski.doc", "tablo.xlsx", "eski.xls", "tarama.tif", "tarama.tiff", "foto.jpg", "foto.jpeg", "ekran.png"],
    )
    def test_new_formats_accepted(self, name):
        assert sanitize_filename(name) == name

    def test_udf_zip_normalized_to_udf(self):
        # UYAP'ın ".udf.zip" adlandırması ".udf"e normalize edilir; düz .zip reddedilir
        assert sanitize_filename("TENSIP_TUTANAGI.udf.zip") == "TENSIP_TUTANAGI.udf"
        with pytest.raises(HTTPException):
            sanitize_filename("arsiv.zip")

    def test_long_name_truncated(self):
        result = sanitize_filename("a" * 250 + ".pdf")
        assert result == "a" * 150 + ".pdf"

    def test_uppercase_extension_accepted(self):
        assert sanitize_filename("BELGE.PDF") == "BELGE.PDF"


# ── validate_file_type ───────────────────────────────────────────────────────

class TestValidateFileType:
    def test_valid_pdf(self, tmp_path):
        p = tmp_path / "belge.pdf"
        p.write_bytes(b"%PDF-1.7 fake content")
        assert validate_file_type(str(p)) is True

    def test_pdf_content_with_udf_extension_rejected(self, tmp_path):
        p = tmp_path / "belge.udf"
        p.write_bytes(b"%PDF-1.7 fake content")
        with pytest.raises(HTTPException) as exc:
            validate_file_type(str(p))
        assert exc.value.status_code == 400

    def test_valid_zip_udf(self, tmp_path):
        p = tmp_path / "belge.udf"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("content.xml", "<content/>")
        assert validate_file_type(str(p)) is True

    def test_zip_udf_without_content_xml_rejected(self, tmp_path):
        p = tmp_path / "belge.udf"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("baska.xml", "<x/>")
        with pytest.raises(HTTPException) as exc:
            validate_file_type(str(p))
        assert exc.value.status_code == 400

    def test_valid_xml_udf(self, tmp_path):
        p = tmp_path / "belge.udf"
        p.write_bytes(b'<?xml version="1.0"?><udf:template xmlns:udf="x">')
        assert validate_file_type(str(p)) is True

    def test_xml_without_udf_tag_rejected(self, tmp_path):
        p = tmp_path / "belge.udf"
        p.write_bytes(b'<?xml version="1.0"?><baska/>' + b" " * 600)
        with pytest.raises(HTTPException) as exc:
            validate_file_type(str(p))
        assert exc.value.status_code == 400

    def test_junk_bytes_rejected(self, tmp_path):
        p = tmp_path / "belge.pdf"
        p.write_bytes(b"\x4d\x5a\x90\x00\x03\x00\x00\x00")  # PE/exe imzası
        with pytest.raises(HTTPException) as exc:
            validate_file_type(str(p))
        assert exc.value.status_code == 400

    def test_disallowed_extension_rejected_before_read(self):
        # Uzantı kontrolü dosya açılmadan yapılır — dosya var olmasa bile 400
        with pytest.raises(HTTPException) as exc:
            validate_file_type("yok/boyle/bir/dosya.exe")
        assert exc.value.status_code == 400

    # ── Yeni formatlar: görüntüler ──
    @pytest.mark.parametrize(
        "name,header",
        [
            ("tarama.tif", b"II*\x00" + b"\x00" * 8),
            ("tarama.tiff", b"MM\x00*" + b"\x00" * 8),
            ("foto.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 8),
            ("foto.jpeg", b"\xff\xd8\xff\xe1" + b"\x00" * 8),
            ("ekran.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8),
        ],
    )
    def test_valid_image_magic_bytes(self, tmp_path, name, header):
        p = tmp_path / name
        p.write_bytes(header)
        assert validate_file_type(str(p)) is True

    def test_png_content_with_tif_extension_rejected(self, tmp_path):
        p = tmp_path / "sahte.tif"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
        with pytest.raises(HTTPException) as exc:
            validate_file_type(str(p))
        assert exc.value.status_code == 400

    def test_pdf_content_with_docx_extension_rejected(self, tmp_path):
        p = tmp_path / "sahte.docx"
        p.write_bytes(b"%PDF-1.7 fake content")
        with pytest.raises(HTTPException) as exc:
            validate_file_type(str(p))
        assert exc.value.status_code == 400

    # ── Yeni formatlar: legacy Office (OLE) ──
    @pytest.mark.parametrize("name", ["eski.doc", "eski.xls"])
    def test_valid_ole_office(self, tmp_path, name):
        p = tmp_path / name
        p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16)
        assert validate_file_type(str(p)) is True

    def test_junk_with_doc_extension_rejected(self, tmp_path):
        p = tmp_path / "sahte.doc"
        p.write_bytes(b"\x4d\x5a\x90\x00\x03\x00\x00\x00")
        with pytest.raises(HTTPException) as exc:
            validate_file_type(str(p))
        assert exc.value.status_code == 400

    # ── Yeni formatlar: OOXML (ZIP marker ayrıştırması) ──
    def test_valid_docx_zip_marker(self, tmp_path):
        p = tmp_path / "belge.docx"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr("word/document.xml", "<document/>")
        assert validate_file_type(str(p)) is True

    def test_valid_xlsx_zip_marker(self, tmp_path):
        p = tmp_path / "tablo.xlsx"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr("xl/workbook.xml", "<workbook/>")
        assert validate_file_type(str(p)) is True

    def test_udf_zip_with_docx_extension_rejected(self, tmp_path):
        # Uzantı-içerik uyuşmazlığı: UDF arşivi .docx adıyla gelemez
        p = tmp_path / "sahte.docx"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("content.xml", "<content/>")
        with pytest.raises(HTTPException) as exc:
            validate_file_type(str(p))
        assert exc.value.status_code == 400

    def test_docx_zip_with_udf_extension_rejected(self, tmp_path):
        p = tmp_path / "sahte.udf"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("word/document.xml", "<document/>")
        with pytest.raises(HTTPException) as exc:
            validate_file_type(str(p))
        assert exc.value.status_code == 400

    def test_xlsx_content_with_docx_extension_rejected(self, tmp_path):
        p = tmp_path / "sahte.docx"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("xl/workbook.xml", "<workbook/>")
        with pytest.raises(HTTPException) as exc:
            validate_file_type(str(p))
        assert exc.value.status_code == 400


# ── validate_file_size ───────────────────────────────────────────────────────

class TestValidateFileSize:
    def test_small_file_ok(self, tmp_path):
        p = tmp_path / "kucuk.pdf"
        p.write_bytes(b"x" * 1024)
        assert validate_file_size(str(p)) is True

    def test_oversized_rejected(self, tmp_path, monkeypatch):
        import file_utils
        monkeypatch.setattr(file_utils, "MAX_UPLOAD_BYTES", 10)
        p = tmp_path / "buyuk.pdf"
        p.write_bytes(b"x" * 100)
        with pytest.raises(HTTPException) as exc:
            validate_file_size(str(p))
        assert exc.value.status_code == 413

    def test_missing_file_500(self):
        with pytest.raises(HTTPException) as exc:
            validate_file_size("yok/dosya.pdf")
        assert exc.value.status_code == 500


# ── safe_remove ──────────────────────────────────────────────────────────────

class TestSafeRemove:
    def test_removes_existing_file(self, tmp_path):
        p = tmp_path / "sil.pdf"
        p.write_bytes(b"x")
        assert safe_remove(str(p)) is True
        assert not p.exists()

    def test_missing_file_is_success(self, tmp_path):
        assert safe_remove(str(tmp_path / "yok.pdf")) is True

    def test_empty_path_is_success(self):
        assert safe_remove("") is True
