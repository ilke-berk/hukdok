"""udf_converter tablo dönüşümü testleri.

2026-08-05 prod arızası: UYAP cevap dilekçesindeki tablo hücresi tek dev
paragraf içeriyordu; splitByRow satır içinde bölemediği için ReportLab
"too large on page" fırlatıyordu. Ayrıca columnSpans yüzde değeri mutlak
punto sanılıp tablo 100pt'lik şeride sıkışıyordu.
"""
import fitz  # pymupdf
import pytest
from reportlab.lib.pagesizes import A4
from reportlab.platypus.doctemplate import LayoutError

from udf_converter import UDFConverter, convert_udf_to_pdf


def _make_udf_xml(path, content_text, elements_xml):
    # Magic PK olmayan dosya ham XML olarak parse edilir; zip'e gerek yok.
    xml = (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        '<template format_id="1.8">\n'
        f'<content><![CDATA[{content_text}]]></content>\n'
        '<properties><pageFormat leftMargin="70" rightMargin="70" '
        'topMargin="70" bottomMargin="70" /></properties>\n'
        f'<elements resolver="hvl-default">\n{elements_xml}\n</elements>\n'
        '</template>\n'
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)


def _single_cell_table_udf(path, content_text, column_spans="100"):
    elements = (
        f'<table tableName="Sabit" columnCount="1" columnSpans="{column_spans}" '
        'border="borderCell">\n'
        '<row rowName="row"><cell>'
        f'<paragraph><content startOffset="0" length="{len(content_text)}" /></paragraph>'
        "</cell></row>\n"
        "</table>"
    )
    _make_udf_xml(path, content_text, elements)


class TestTableConversion:
    def test_oversized_single_cell_splits_across_pages(self, tmp_path):
        """Sayfaya sığmayan tek hücre satır içinde bölünmeli, hata değil."""
        long_text = "Yargıtay kararı alıntısı deneme metni. " * 900
        src = tmp_path / "dev_hucre.udf"
        out = tmp_path / "dev_hucre.pdf"
        _single_cell_table_udf(str(src), long_text)

        result_path, _ = convert_udf_to_pdf(str(src), str(out))

        with fitz.open(result_path) as doc:
            assert doc.page_count > 1
            assert "deneme metni" in doc[0].get_text()

    def test_column_spans_percentage_scales_to_frame_width(self, tmp_path):
        """columnSpans="100" yüzdedir; tablo kullanılabilir genişliği kaplamalı."""
        text = "Kısa hücre içeriği."
        src = tmp_path / "genislik.udf"
        _single_cell_table_udf(str(src), text)

        conv = UDFConverter(str(src), str(tmp_path / "genislik.pdf"))
        conv.convert()

        # convert() sonrası margins dolu; frame genişliği = A4 - marjlar
        avail = A4[0] - conv.margins["left"] - conv.margins["right"]
        with fitz.open(str(tmp_path / "genislik.pdf")) as doc:
            words = doc[0].get_text("words")
            assert words, "PDF metin içermeli"
            # borderCell çizgileri tablo genişliğini gösterir
            drawings = doc[0].get_drawings()
            xs = [x for d in drawings for x in (d["rect"].x0, d["rect"].x1)]
            if xs:
                table_width = max(xs) - min(xs)
                assert table_width == pytest.approx(avail, abs=5)

    def test_two_columns_share_width_by_span_ratio(self, tmp_path):
        """"30,70" oranı iki kolona orantılı dağılmalı (toplam = frame)."""
        text = "Sol hücre. Sağ hücre."
        elements = (
            '<table tableName="Sabit" columnCount="2" columnSpans="30,70" '
            'border="borderCell">\n'
            '<row rowName="row">'
            '<cell><paragraph><content startOffset="0" length="9" /></paragraph></cell>'
            '<cell><paragraph><content startOffset="10" length="11" /></paragraph></cell>'
            "</row>\n</table>"
        )
        src = tmp_path / "iki_kolon.udf"
        out = tmp_path / "iki_kolon.pdf"
        _make_udf_xml(str(src), text, elements)

        result_path, _ = convert_udf_to_pdf(str(src), str(out))

        with fitz.open(result_path) as doc:
            page_text = doc[0].get_text()
            assert "Sol hücre" in page_text
            assert "Sağ hücre" in page_text


class TestDegradeFallback:
    """Katman 1: layout hatasında tablolar düzleştirilerek ikinci deneme."""

    def test_layout_error_triggers_degraded_retry(self, tmp_path, monkeypatch):
        text = "Fallback deneme içeriği."
        src = tmp_path / "fallback.udf"
        out = tmp_path / "fallback.pdf"
        _single_cell_table_udf(str(src), text)

        attempts = []
        orig_convert = UDFConverter.convert

        def fake_convert(self):
            attempts.append(self.degrade_tables)
            if not self.degrade_tables:
                raise LayoutError("tablo sayfaya sığmadı (simülasyon)")
            return orig_convert(self)

        monkeypatch.setattr(UDFConverter, "convert", fake_convert)
        result_path, warnings = convert_udf_to_pdf(str(src), str(out))

        assert attempts == [False, True], "önce normal, sonra degrade denenmeli"
        assert any("basitleştirilmiş" in w for w in warnings)
        with fitz.open(result_path) as doc:
            assert "Fallback deneme içeriği" in doc[0].get_text()

    def test_double_layout_error_raises_clear_message(self, tmp_path, monkeypatch):
        src = tmp_path / "umutsuz.udf"
        _single_cell_table_udf(str(src), "İçerik.")

        def always_fail(self):
            raise LayoutError("simülasyon")

        monkeypatch.setattr(UDFConverter, "convert", always_fail)
        with pytest.raises(ValueError, match="yerleştirilemedi"):
            convert_udf_to_pdf(str(src), str(tmp_path / "umutsuz.pdf"))

    def test_degraded_mode_flattens_tables_keeps_content(self, tmp_path):
        """Degrade modunda tablo çizgisi yok ama tüm hücre içerikleri korunur."""
        text = "Birinci hücre metni. İkinci hücre metni."
        elements = (
            '<table tableName="Sabit" columnCount="2" columnSpans="50,50" '
            'border="borderCell">\n'
            '<row rowName="row">'
            '<cell><paragraph><content startOffset="0" length="20" /></paragraph></cell>'
            '<cell><paragraph><content startOffset="21" length="19" /></paragraph></cell>'
            "</row>\n</table>"
        )
        src = tmp_path / "duz.udf"
        out = tmp_path / "duz.pdf"
        _make_udf_xml(str(src), text, elements)

        conv = UDFConverter(str(src), str(out), degrade_tables=True)
        conv.convert()

        with fitz.open(str(out)) as doc:
            page_text = doc[0].get_text()
            assert "Birinci hücre metni" in page_text
            assert "İkinci hücre metni" in page_text
            assert not doc[0].get_drawings(), "degrade modunda tablo çizgisi olmamalı"

    def test_broken_udf_raises_turkish_parse_error(self, tmp_path):
        src = tmp_path / "bozuk.udf"
        src.write_text("bu bir xml değil <<<", encoding="utf-8")

        with pytest.raises(ValueError, match="okunamadı"):
            convert_udf_to_pdf(str(src), str(tmp_path / "bozuk.pdf"))
