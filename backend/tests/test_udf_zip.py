"""Dizin kaydı eksik UDF arşivi — sıralı okuma yedek yolu.

2026-09-30 prod olayı: UYAP'tan gelen bir .udf'te content.xml ve sign.sgn tamdı
ama arşivin sonundaki dizin kaydı (central directory) yoktu; zipfile BadZipFile
verdiği için /process aynı dosyayı 14 kez 400 ile reddetti. Bu testler yedek
okuyucuyu (udf_zip), doğrulama kapısını (file_utils) ve dönüştürücüyü
(udf_converter) aynı dosya biçimiyle kilitler.
"""
import io
import struct
import zipfile
import zlib

import fitz  # pymupdf
import pytest
from fastapi import HTTPException

from file_utils import validate_file_type
from udf_converter import convert_udf_to_pdf
from udf_zip import read_entry_sequential

_CONTENT_TEXT = "İSTANBUL 3. TÜKETİCİ MAHKEMESİNE adli yardım talebi"
_CONTENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" ?>\n'
    '<template format_id="1.8">\n'
    f"<content><![CDATA[{_CONTENT_TEXT}]]></content>\n"
    '<properties><pageFormat leftMargin="70" rightMargin="70" '
    'topMargin="70" bottomMargin="70" /></properties>\n'
    '<elements resolver="hvl-default">\n'
    f'<paragraph><content startOffset="0" length="{len(_CONTENT_TEXT)}" /></paragraph>\n'
    "</elements>\n"
    "</template>\n"
).encode("utf-8")
_SIGN = b"\x30\x82" + b"imza" * 200


def _descriptor_entry(name: str, payload: bytes, *, bad_crc: bool = False) -> bytes:
    """UYAP'ın yazdığı biçim: başlıkta boyut/CRC sıfır, gerçek değerler girişten sonra."""
    deflater = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = deflater.compress(payload) + deflater.flush()
    crc = zlib.crc32(payload) ^ (1 if bad_crc else 0)
    header = struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0x808, 8, 0, 0, 0, 0, 0, len(name), 0)
    descriptor = b"PK\x07\x08" + struct.pack("<III", crc, len(body), len(payload))
    return header + name.encode() + body + descriptor


def _write_dizinsiz_udf(path, *, bad_crc: bool = False, truncate: int = 0, first: str = "content.xml"):
    data = _descriptor_entry(first, _CONTENT_XML, bad_crc=bad_crc) + _descriptor_entry("sign.sgn", _SIGN)
    if truncate:
        data = data[:truncate]
    path.write_bytes(data)
    return str(path)


class TestReadEntrySequential:
    def test_dizinsiz_arsivden_content_okunur(self, tmp_path):
        p = _write_dizinsiz_udf(tmp_path / "belge.udf")
        with pytest.raises(zipfile.BadZipFile):
            zipfile.ZipFile(p)
        assert read_entry_sequential(p) == _CONTENT_XML

    def test_sonraki_giris_de_okunur(self, tmp_path):
        p = _write_dizinsiz_udf(tmp_path / "belge.udf")
        assert read_entry_sequential(p, "sign.sgn") == _SIGN

    def test_descriptorsiz_giris_okunur(self, tmp_path):
        # zipfile'ın yazdığı biçim (boyut/CRC başlıkta), dizin kaydı kesilmiş.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("content.xml", _CONTENT_XML)
            z.writestr("not.txt", b"duz", compress_type=zipfile.ZIP_STORED)
            start_dir = z.fp.tell()
        p = tmp_path / "belge.udf"
        p.write_bytes(buf.getvalue()[:start_dir])
        assert read_entry_sequential(str(p)) == _CONTENT_XML
        assert read_entry_sequential(str(p), "not.txt") == b"duz"

    def test_yarida_kesilmis_akis_none(self, tmp_path):
        p = _write_dizinsiz_udf(tmp_path / "belge.udf", truncate=120)
        assert read_entry_sequential(p) is None

    def test_crc_tutmazsa_none(self, tmp_path):
        p = _write_dizinsiz_udf(tmp_path / "belge.udf", bad_crc=True)
        assert read_entry_sequential(p) is None

    def test_giris_yoksa_none(self, tmp_path):
        p = _write_dizinsiz_udf(tmp_path / "belge.udf", first="word/document.xml")
        assert read_entry_sequential(p) is None

    def test_zip_olmayan_dosya_none(self, tmp_path):
        p = tmp_path / "belge.udf"
        p.write_bytes(b"PK\x03\x04" + b"\x00" * 10)
        assert read_entry_sequential(str(p)) is None


class TestValidateFileTypeDizinsizUdf:
    def test_dizinsiz_udf_kabul_edilir(self, tmp_path):
        assert validate_file_type(_write_dizinsiz_udf(tmp_path / "belge.udf")) is True

    def test_yarida_kesilmis_udf_reddedilir(self, tmp_path):
        p = _write_dizinsiz_udf(tmp_path / "belge.udf", truncate=120)
        with pytest.raises(HTTPException) as exc:
            validate_file_type(p)
        assert exc.value.status_code == 400

    def test_content_xml_olmayan_dizinsiz_udf_reddedilir(self, tmp_path):
        p = _write_dizinsiz_udf(tmp_path / "sahte.udf", first="word/document.xml")
        with pytest.raises(HTTPException) as exc:
            validate_file_type(p)
        assert exc.value.status_code == 400

    def test_yedek_yol_yalniz_udf_icin(self, tmp_path):
        # docx/xlsx dönüştürücüleri gerçek ZIP ister; dizinsiz arşiv onlarda reddedilir.
        p = tmp_path / "belge.docx"
        p.write_bytes(_descriptor_entry("word/document.xml", b"<document/>"))
        with pytest.raises(HTTPException) as exc:
            validate_file_type(str(p))
        assert exc.value.status_code == 400


class TestConverterDizinsizUdf:
    def test_dizinsiz_udf_pdfe_donusur(self, tmp_path):
        udf = _write_dizinsiz_udf(tmp_path / "belge.udf")
        pdf, _warnings = convert_udf_to_pdf(udf, str(tmp_path / "belge.pdf"))
        with fitz.open(pdf) as doc:
            text = "".join(page.get_text() for page in doc)
        assert "adli yardım talebi" in text

    def test_bozuk_udf_value_error(self, tmp_path):
        udf = _write_dizinsiz_udf(tmp_path / "belge.udf", truncate=120)
        with pytest.raises(ValueError):
            convert_udf_to_pdf(udf, str(tmp_path / "belge.pdf"))
