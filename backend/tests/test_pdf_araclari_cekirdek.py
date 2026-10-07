"""G267 — `pdf/pdf_araclari.py` çekirdek testleri.

Gerçek PDF'ler fitz ile üretilir (`tmp_path`). Her işlem için en az bir başarı + bir ParametreHatasi;
karartma metnin `get_text`'ten kaybolduğunu VE görüntü pikselinin değiştiğini kanıtlar; 90° döndürülmüş
sayfada karartma/damga/not doğru yere düşer; sıkıştırma Ghostscript yoksa skip; `os.replace` yarım dosya testi.
"""
import hashlib
import io
import os
import subprocess
import warnings

import fitz
import pytest
from PIL import Image

from pdf import pdf_araclari as pa
from pdf.pdf_araclari import (
    AracYok,
    ParametreHatasi,
    PdfArcHatasi,
    SayfaSinirAsildi,
    ZamanAsimi,
    birlestir,
    bol,
    damga,
    karart,
    not_ekle,
    onizleme_png,
    pdf_ye_cevir,
    sayfa_duzenle,
    sayfa_meta,
    sikistir,
)

warnings.filterwarnings("ignore", message="The `fitz` API is deprecated")

W, H = 600.0, 800.0


def _pdf(path, metinler=("SAYFA 1",), rotation=0, boyut=(W, H)):
    """Her sayfada tek metin; metin (50, 100) döndürülmemiş noktasına yazılır."""
    with fitz.open() as doc:
        for metin in metinler:
            page = doc.new_page(width=boyut[0], height=boyut[1])
            page.insert_text((50, 100), metin, fontsize=20)
            if rotation:
                page.set_rotation(rotation)
        doc.save(str(path))
    return str(path)


def _sayfa_metinleri(pdf):
    with fitz.open(pdf) as doc:
        return [page.get_text().strip() for page in doc]


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _gorunur_bbox(page, metin):
    """Metnin görünür düzlemdeki bbox'ı (açıklama düzlemi × rotation_matrix)."""
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            for span in line["spans"]:
                if metin in span["text"]:
                    return fitz.Rect(span["bbox"]) * page.rotation_matrix
    raise AssertionError(f"metin bulunamadı: {metin}")


@pytest.fixture
def cikti(tmp_path):
    d = tmp_path / "cikti"
    d.mkdir()
    return str(d)


@pytest.fixture
def uc_sayfa(tmp_path):
    return _pdf(tmp_path / "uc.pdf", ("BIR", "IKI", "UC"))


# ── sayfa_meta ───────────────────────────────────────────────────────────────

class TestSayfaMeta:
    def test_boyutlar_ve_sayfa_sayisi(self, uc_sayfa):
        meta = sayfa_meta(uc_sayfa)
        assert meta["sayfa"] == 3
        assert meta["boyut"] == os.path.getsize(uc_sayfa)
        assert meta["sayfalar"][0] == {"no": 1, "genislik": W, "yukseklik": H}
        assert [s["no"] for s in meta["sayfalar"]] == [1, 2, 3]

    def test_donmus_sayfa_gorunur_boyut(self, tmp_path):
        pdf = _pdf(tmp_path / "d.pdf", ("A",), rotation=90)
        meta = sayfa_meta(pdf)
        assert meta["sayfalar"][0]["genislik"] == H
        assert meta["sayfalar"][0]["yukseklik"] == W

    def test_sifreli_pdf_hata(self, tmp_path):
        yol = tmp_path / "sifreli.pdf"
        with fitz.open() as doc:
            doc.new_page()
            doc.save(str(yol), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="gizli", owner_pw="gizli")
        with pytest.raises(PdfArcHatasi):
            sayfa_meta(str(yol))

    def test_acilamayan_dosya_hata(self, tmp_path):
        yol = tmp_path / "bozuk.pdf"
        yol.write_bytes(b"bu bir pdf degil")
        with pytest.raises(PdfArcHatasi):
            sayfa_meta(str(yol))


# ── birlestir ────────────────────────────────────────────────────────────────

class TestBirlestir:
    def test_sira_korunur(self, tmp_path, cikti):
        a = _pdf(tmp_path / "a.pdf", ("A1", "A2"))
        b = _pdf(tmp_path / "b.pdf", ("B1",))
        out = birlestir([b, a], cikti)
        assert os.path.basename(out) == "birlestirilmis.pdf"
        assert _sayfa_metinleri(out) == ["B1", "A1", "A2"]

    def test_bos_girdi_parametre_hatasi(self, cikti):
        with pytest.raises(ParametreHatasi):
            birlestir([], cikti)

    def test_sayfa_siniri_cikti_yazilmadan(self, tmp_path, cikti, uc_sayfa):
        with pytest.raises(SayfaSinirAsildi):
            birlestir([uc_sayfa, uc_sayfa], cikti, max_sayfa=5)
        assert os.listdir(cikti) == []

    def test_sayfa_siniri_tam_esit_gecer(self, cikti, uc_sayfa):
        out = birlestir([uc_sayfa, uc_sayfa], cikti, max_sayfa=6)
        assert sayfa_meta(out)["sayfa"] == 6

    def test_ayni_ad_cakismaz(self, cikti, uc_sayfa):
        birlestir([uc_sayfa], cikti)
        out2 = birlestir([uc_sayfa], cikti)
        assert os.path.basename(out2) == "birlestirilmis-2.pdf"


# ── bol ──────────────────────────────────────────────────────────────────────

class TestBol:
    def test_araliklar(self, cikti, uc_sayfa):
        outs = bol(uc_sayfa, cikti, araliklar=[[1, 2], [3, 3]])
        assert [os.path.basename(o) for o in outs] == ["uc_1-2.pdf", "uc_3-3.pdf"]
        assert _sayfa_metinleri(outs[0]) == ["BIR", "IKI"]
        assert _sayfa_metinleri(outs[1]) == ["UC"]

    def test_her_n_bir_her_sayfa_ayri(self, cikti, uc_sayfa):
        outs = bol(uc_sayfa, cikti, her_n=1)
        assert len(outs) == 3
        assert [os.path.basename(o) for o in outs] == ["uc_1-1.pdf", "uc_2-2.pdf", "uc_3-3.pdf"]

    def test_her_n_son_parca_kisa(self, cikti, uc_sayfa):
        outs = bol(uc_sayfa, cikti, her_n=2)
        assert [os.path.basename(o) for o in outs] == ["uc_1-2.pdf", "uc_3-3.pdf"]

    @pytest.mark.parametrize("araliklar", [[[1, 2], [2, 3]], [[1, 4]], [[2, 1]], [[0, 1]], [], [[1]]])
    def test_gecersiz_aralik(self, cikti, uc_sayfa, araliklar):
        with pytest.raises(ParametreHatasi):
            bol(uc_sayfa, cikti, araliklar=araliklar)
        assert os.listdir(cikti) == []

    def test_ikisi_birden_ya_da_hicbiri(self, cikti, uc_sayfa):
        with pytest.raises(ParametreHatasi):
            bol(uc_sayfa, cikti, araliklar=[[1, 1]], her_n=1)
        with pytest.raises(ParametreHatasi):
            bol(uc_sayfa, cikti)
        with pytest.raises(ParametreHatasi):
            bol(uc_sayfa, cikti, her_n=0)


# ── sayfa_duzenle ────────────────────────────────────────────────────────────

class TestSayfaDuzenle:
    def test_sira_silme_dondurme(self, cikti, uc_sayfa):
        out = sayfa_duzenle(uc_sayfa, [{"no": 3, "dondur": 90}, {"no": 1}], cikti)
        assert _sayfa_metinleri(out) == ["UC", "BIR"]
        with fitz.open(out) as doc:
            assert doc[0].rotation == 90
            assert doc[1].rotation == 0

    def test_dondurme_mevcuda_eklenir(self, tmp_path, cikti):
        pdf = _pdf(tmp_path / "d.pdf", ("A",), rotation=270)
        out = sayfa_duzenle(pdf, [{"no": 1, "dondur": 180}], cikti)
        with fitz.open(out) as doc:
            assert doc[0].rotation == 90

    @pytest.mark.parametrize("sayfalar", [[], [{"no": 1, "dondur": 45}], [{"no": 4}], [{"no": 1}, {"no": 1}], [{"x": 1}]])
    def test_gecersiz_liste(self, cikti, uc_sayfa, sayfalar):
        with pytest.raises(ParametreHatasi):
            sayfa_duzenle(uc_sayfa, sayfalar, cikti)


# ── sikistir ─────────────────────────────────────────────────────────────────

def _gurultulu_pdf(path):
    """Büyük, gürültülü görüntü içeren tek sayfa — /screen seviyesinde örnekleme küçültür."""
    import random

    rnd = random.Random(7)
    img = Image.new("RGB", (1400, 1400))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(1400 * 1400)])
    png = str(path.parent / "gurultu.png")
    img.save(png, "PNG")
    with fitz.open() as doc:
        page = doc.new_page(width=W, height=H)
        page.insert_image(fitz.Rect(50, 50, 250, 250), filename=png)
        doc.save(str(path))
    return str(path)


class TestSikistir:
    def test_gecersiz_seviye(self, cikti, uc_sayfa):
        with pytest.raises(ParametreHatasi):
            sikistir(uc_sayfa, "maksimum", cikti)

    @pytest.mark.skipif(pa._find_ghostscript() is None, reason="Ghostscript yok")
    def test_boyut_kuculur(self, tmp_path, cikti):
        pdf = _gurultulu_pdf(tmp_path / "buyuk.pdf")
        out, kucultme = sikistir(pdf, "ekran", cikti)
        assert os.path.basename(out) == "buyuk_sikistirilmis.pdf"
        assert kucultme > 0
        assert os.path.getsize(out) == os.path.getsize(pdf) - kucultme
        assert sayfa_meta(out)["sayfa"] == 1

    def test_ghostscript_yoksa_arac_yok(self, monkeypatch, cikti, uc_sayfa):
        monkeypatch.setattr(pa, "_find_ghostscript", lambda: None)
        with pytest.raises(AracYok):
            sikistir(uc_sayfa, "ebook", cikti)

    def test_zaman_asimi_gecici_dosya_kalmaz(self, monkeypatch, cikti, uc_sayfa):
        monkeypatch.setattr(pa, "_find_ghostscript", lambda: "gs")

        def _timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="gs", timeout=kwargs.get("timeout"))

        monkeypatch.setattr(pa.subprocess, "run", _timeout)
        with pytest.raises(ZamanAsimi):
            sikistir(uc_sayfa, "yazici", cikti)
        assert os.listdir(cikti) == []

    def test_cikti_buyukse_girdi_kopyasi(self, monkeypatch, cikti, uc_sayfa):
        monkeypatch.setattr(pa, "_find_ghostscript", lambda: "gs")

        def _sahte_gs(komut, **kwargs):
            hedef = next(a for a in komut if a.startswith("-sOutputFile=")).split("=", 1)[1]
            with open(hedef, "wb") as f:
                f.write(b"%PDF-1.4\n" + b"0" * (os.path.getsize(uc_sayfa) + 1000))
            return subprocess.CompletedProcess(komut, 0, "", "")

        monkeypatch.setattr(pa.subprocess, "run", _sahte_gs)
        out, kucultme = sikistir(uc_sayfa, "ebook", cikti)
        assert kucultme == 0
        assert _sha(out) == _sha(uc_sayfa)
        assert os.listdir(cikti) == ["uc_sikistirilmis.pdf"]

    def test_gs_hatasi_pdf_arc_hatasi(self, monkeypatch, cikti, uc_sayfa):
        monkeypatch.setattr(pa, "_find_ghostscript", lambda: "gs")
        monkeypatch.setattr(
            pa.subprocess, "run", lambda komut, **kw: subprocess.CompletedProcess(komut, 1, "", "bozuk")
        )
        with pytest.raises(PdfArcHatasi):
            sikistir(uc_sayfa, "ebook", cikti)
        assert os.listdir(cikti) == []


# ── karart ───────────────────────────────────────────────────────────────────

class TestKarart:
    def test_metin_kaybolur_digeri_kalir(self, tmp_path, cikti):
        pdf = _pdf(tmp_path / "k.pdf", ("GIZLI",))
        with fitz.open(pdf) as doc:
            doc[0].insert_text((50, 300), "ACIK", fontsize=20)
            doc.save(str(tmp_path / "k2.pdf"))
        pdf = str(tmp_path / "k2.pdf")
        with fitz.open(pdf) as doc:
            alan = _gorunur_bbox(doc[0], "GIZLI")
        out = karart(pdf, [{"sayfa": 1, "x0": alan.x0, "y0": alan.y0, "x1": alan.x1, "y1": alan.y1}], cikti)
        with fitz.open(out) as doc:
            metin = doc[0].get_text()
        assert "GIZLI" not in metin
        assert "ACIK" in metin

    def test_goruntu_pikseli_degisir(self, tmp_path, cikti):
        png = str(tmp_path / "kirmizi.png")
        Image.new("RGB", (100, 100), (255, 0, 0)).save(png, "PNG")
        pdf = str(tmp_path / "g.pdf")
        with fitz.open() as doc:
            page = doc.new_page(width=W, height=H)
            page.insert_image(fitz.Rect(100, 100, 300, 300), filename=png)
            doc.save(pdf)
        with fitz.open(pdf) as doc:
            onceki = doc[0].get_pixmap().pixel(200, 200)
        assert onceki == (255, 0, 0)
        out = karart(pdf, [{"sayfa": 1, "x0": 150, "y0": 150, "x1": 250, "y1": 250}], cikti)
        with fitz.open(out) as doc:
            pix = doc[0].get_pixmap()
            assert pix.pixel(200, 200) == (0, 0, 0)  # karartılan alan siyah
            assert pix.pixel(120, 120) == (255, 0, 0)  # alan dışı görüntü yerinde

    def test_donmus_sayfada_gorunur_koordinat(self, tmp_path, cikti):
        pdf = _pdf(tmp_path / "r.pdf", ("GIZLI",), rotation=90)
        with fitz.open(pdf) as doc:
            page = doc[0]
            page.insert_text((50, 500), "ACIK", fontsize=20)  # döndürülmemiş düzlem
            doc.save(str(tmp_path / "r2.pdf"))
        pdf = str(tmp_path / "r2.pdf")
        with fitz.open(pdf) as doc:
            alan = _gorunur_bbox(doc[0], "GIZLI")
            # görünür düzlem: 90° dönmüş sayfada metin sağ üstte (x > W/2)
            assert alan.x0 > doc[0].rect.width / 2
        out = karart(pdf, [{"sayfa": 1, "x0": alan.x0, "y0": alan.y0, "x1": alan.x1, "y1": alan.y1}], cikti)
        with fitz.open(out) as doc:
            metin = doc[0].get_text()
            pix = doc[0].get_pixmap()
            orta = alan.top_left + (alan.bottom_right - alan.top_left) * 0.5
            assert pix.pixel(int(orta.x), int(orta.y)) == (0, 0, 0)
        assert "GIZLI" not in metin
        assert "ACIK" in metin

    def test_tasan_alan_kirpilir(self, tmp_path, cikti):
        pdf = _pdf(tmp_path / "t.pdf", ("GIZLI",))
        out = karart(pdf, [{"sayfa": 1, "x0": -100, "y0": -100, "x1": 200, "y1": 150}], cikti)
        assert "GIZLI" not in _sayfa_metinleri(out)[0]

    @pytest.mark.parametrize(
        "alanlar",
        [
            [],
            [{"sayfa": 2, "x0": 0, "y0": 0, "x1": 10, "y1": 10}],
            [{"sayfa": 1, "x0": -50, "y0": -50, "x1": -10, "y1": -10}],
            [{"sayfa": 1, "x0": 10, "y0": 10, "x1": 10, "y1": 50}],
            [{"sayfa": 1, "x0": "a", "y0": 0, "x1": 10, "y1": 10}],
        ],
    )
    def test_gecersiz_alan(self, tmp_path, cikti, alanlar):
        pdf = _pdf(tmp_path / "p.pdf", ("GIZLI",))
        with pytest.raises(ParametreHatasi):
            karart(pdf, alanlar, cikti)


# ── damga ────────────────────────────────────────────────────────────────────

class TestDamga:
    def test_turkce_glif_geri_okunur(self, tmp_path, cikti):
        pdf = _pdf(tmp_path / "s.pdf", ("A", "B"))
        out = damga(pdf, "ASLI GİBİDİR ĞÜŞİÖÇ ğüşıöç", "sag-ust", cikti)
        assert os.path.basename(out) == "s_damgali.pdf"
        for metin in _sayfa_metinleri(out):
            assert "ASLI GİBİDİR ĞÜŞİÖÇ ğüşıöç" in metin
        with fitz.open(out) as doc:
            bbox = _gorunur_bbox(doc[0], "ASLI")
            assert bbox.x1 <= W and bbox.x0 > W / 2 and bbox.y1 < 80

    @pytest.mark.parametrize(
        "konum,kontrol",
        [
            ("sol-ust", lambda r: r.x0 < W / 2 and r.y1 < H / 2),
            ("sag-alt", lambda r: r.x0 > W / 2 and r.y0 > H / 2),
            ("sol-alt", lambda r: r.x0 < W / 2 and r.y0 > H / 2),
            ("orta", lambda r: r.x0 < W / 2 < r.x1 and r.y0 < H / 2 < r.y1),
        ],
    )
    def test_konumlar(self, tmp_path, cikti, konum, kontrol):
        pdf = _pdf(tmp_path / "k.pdf", ("A",))
        out = damga(pdf, "DAMGA", konum, cikti)
        with fitz.open(out) as doc:
            assert kontrol(_gorunur_bbox(doc[0], "DAMGA")), konum

    def test_donmus_sayfada_sag_ust(self, tmp_path, cikti):
        pdf = _pdf(tmp_path / "r.pdf", ("A",), rotation=90)
        out = damga(pdf, "DAMGA", "sag-ust", cikti, punto=14, renk="#0000ff")
        with fitz.open(out) as doc:
            page = doc[0]
            bbox = _gorunur_bbox(page, "DAMGA")
            assert bbox.x0 > page.rect.width / 2 and bbox.x1 <= page.rect.width and bbox.y1 < 80
            # metin görünür düzlemde yatay okunur: dönmüş sayfada satır yönü (0,-1)
            yon = page.get_text("dict")["blocks"][-1]["lines"][0]["dir"]
            assert tuple(round(v) for v in yon) == (0, -1)

    def test_sayfa_listesi(self, tmp_path, cikti):
        pdf = _pdf(tmp_path / "l.pdf", ("A", "B", "C"))
        out = damga(pdf, "X", "orta", cikti, sayfalar=[3])
        metinler = _sayfa_metinleri(out)
        assert "X" not in metinler[0] and "X" in metinler[2]

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"metin": "a" * 121, "konum": "orta"},
            {"metin": "", "konum": "orta"},
            {"metin": "x", "konum": "ust"},
            {"metin": "x", "konum": "orta", "renk": "kirmizi"},
            {"metin": "x", "konum": "orta", "renk": "#zz0000"},
            {"metin": "x", "konum": "orta", "punto": 0},
            {"metin": "x", "konum": "orta", "sayfalar": [5]},
            {"metin": "x", "konum": "orta", "sayfalar": "bazi"},
        ],
    )
    def test_gecersiz_parametre(self, tmp_path, cikti, kwargs):
        pdf = _pdf(tmp_path / "p.pdf", ("A",))
        with pytest.raises(ParametreHatasi):
            damga(pdf, kwargs.pop("metin"), kwargs.pop("konum"), cikti, **kwargs)

    def test_font_yoksa_arac_yok(self, monkeypatch, tmp_path, cikti):
        monkeypatch.setattr(pa, "DEJAVU_FONTFILE", str(tmp_path / "yok.ttf"))
        pdf = _pdf(tmp_path / "p.pdf", ("A",))
        with pytest.raises(AracYok):
            damga(pdf, "x", "orta", cikti)


# ── not_ekle ─────────────────────────────────────────────────────────────────

class TestNotEkle:
    def test_not_icerigi(self, tmp_path, cikti):
        pdf = _pdf(tmp_path / "n.pdf", ("A",))
        out = not_ekle(pdf, 1, 120, 240, "Dikkat: ĞÜŞ", cikti)
        with fitz.open(out) as doc:
            page = doc[0]  # referans tutulmazsa açıklama nesneleri sayfaya bağını kaybeder
            annots = list(page.annots())
            assert len(annots) == 1
            assert annots[0].type[1] == "Text"
            assert annots[0].info["content"] == "Dikkat: ĞÜŞ"
            assert annots[0].rect.top_left == fitz.Point(120, 240)

    def test_donmus_sayfada_gorunur_nokta(self, tmp_path, cikti):
        pdf = _pdf(tmp_path / "r.pdf", ("A",), rotation=90)
        out = not_ekle(pdf, 1, 700, 50, "not", cikti)
        with fitz.open(out) as doc:
            page = doc[0]
            annot = next(page.annots())
            assert (annot.rect * page.rotation_matrix).top_left == fitz.Point(700, 50)

    @pytest.mark.parametrize(
        "args",
        [
            (1, 10, 10, "a" * 2001),
            (1, 10, 10, ""),
            (2, 10, 10, "x"),
            (1, 9999, 10, "x"),
            (1, "a", 10, "x"),
        ],
    )
    def test_gecersiz(self, tmp_path, cikti, args):
        pdf = _pdf(tmp_path / "p.pdf", ("A",))
        with pytest.raises(ParametreHatasi):
            not_ekle(pdf, *args, cikti)


# ── pdf_ye_cevir ─────────────────────────────────────────────────────────────

class TestPdfYeCevir:
    def test_pdf_kopya(self, cikti, uc_sayfa):
        out = pdf_ye_cevir(uc_sayfa, cikti)
        assert os.path.basename(out) == "uc.pdf"
        assert _sha(out) == _sha(uc_sayfa)

    def test_png_donusur(self, tmp_path, cikti):
        png = tmp_path / "foto.png"
        Image.new("RGB", (80, 60), (0, 128, 0)).save(str(png), "PNG")
        out = pdf_ye_cevir(str(png), cikti)
        assert os.path.basename(out) == "foto.pdf"
        assert sayfa_meta(out)["sayfa"] == 1

    def test_udf_sarmalayici(self, monkeypatch, tmp_path, cikti):
        def _sahte_udf(kaynak, hedef, deadline=None):
            with fitz.open() as doc:
                doc.new_page()
                doc.save(hedef)
            return hedef

        monkeypatch.setattr(pa, "_udf_to_pdfa2b", _sahte_udf)
        udf = tmp_path / "dilekce.udf"
        udf.write_bytes(b"udf")
        out = pdf_ye_cevir(str(udf), cikti)
        assert os.path.basename(out) == "dilekce.pdf"
        assert sayfa_meta(out)["sayfa"] == 1

    def test_desteklenmeyen_uzanti(self, tmp_path, cikti):
        dosya = tmp_path / "x.exe"
        dosya.write_bytes(b"x")
        with pytest.raises(ParametreHatasi):
            pdf_ye_cevir(str(dosya), cikti)
        assert os.listdir(cikti) == []

    def test_bozuk_pdf(self, tmp_path, cikti):
        dosya = tmp_path / "x.pdf"
        dosya.write_bytes(b"pdf degil")
        with pytest.raises(PdfArcHatasi):
            pdf_ye_cevir(str(dosya), cikti)


# ── onizleme_png ─────────────────────────────────────────────────────────────

class TestOnizleme:
    def test_png_ve_genislik(self, uc_sayfa):
        veri = onizleme_png(uc_sayfa, 2, genislik=240)
        assert veri[:8] == b"\x89PNG\r\n\x1a\n"
        img = Image.open(io.BytesIO(veri))
        assert img.size == (240, round(240 * H / W))

    def test_donmus_sayfa_pixmapta_gorunur(self, tmp_path):
        pdf = _pdf(tmp_path / "r.pdf", ("A",), rotation=90)
        veri = onizleme_png(pdf, 1, genislik=400)
        assert Image.open(io.BytesIO(veri)).size == (400, 300)  # 800x600 görünür → 400x300

    @pytest.mark.parametrize("genislik", [63, 1601, 0, "240", 240.0])
    def test_gecersiz_genislik(self, uc_sayfa, genislik):
        with pytest.raises(ParametreHatasi):
            onizleme_png(uc_sayfa, 1, genislik=genislik)

    def test_sayfa_disi(self, uc_sayfa):
        with pytest.raises(ParametreHatasi):
            onizleme_png(uc_sayfa, 4)


# ── Ortak güvenceler ─────────────────────────────────────────────────────────

class TestOrtak:
    def test_girdi_degismez(self, tmp_path, cikti):
        pdf = _pdf(tmp_path / "g.pdf", ("GIZLI", "B", "C"))
        onceki = _sha(pdf)
        birlestir([pdf, pdf], cikti)
        bol(pdf, cikti, her_n=2)
        sayfa_duzenle(pdf, [{"no": 2, "dondur": 90}], cikti)
        karart(pdf, [{"sayfa": 1, "x0": 0, "y0": 0, "x1": 300, "y1": 200}], cikti)
        damga(pdf, "ASLI GİBİDİR", "sag-ust", cikti)
        not_ekle(pdf, 1, 10, 10, "not", cikti)
        pdf_ye_cevir(pdf, cikti)
        onizleme_png(pdf, 1)
        sayfa_meta(pdf)
        assert _sha(pdf) == onceki

    def test_os_replace_hatasinda_yarim_dosya_kalmaz(self, monkeypatch, cikti, uc_sayfa):
        def _patla(src, dst):
            raise RuntimeError("disk dolu")

        monkeypatch.setattr(pa.os, "replace", _patla)
        with pytest.raises(RuntimeError):
            birlestir([uc_sayfa], cikti)
        assert os.listdir(cikti) == []  # ne hedef ne .tmp

    def test_deadline_gecmisse_zaman_asimi(self, cikti, uc_sayfa):
        gecmis = pa.time.monotonic() - 1
        with pytest.raises(ZamanAsimi):
            birlestir([uc_sayfa], cikti, deadline=gecmis)
        with pytest.raises(ZamanAsimi):
            karart(uc_sayfa, [{"sayfa": 1, "x0": 0, "y0": 0, "x1": 10, "y1": 10}], cikti, deadline=gecmis)
        assert os.listdir(cikti) == []

    def test_hata_siniflari_tek_tabandan(self):
        for sinif in (ParametreHatasi, SayfaSinirAsildi, AracYok, ZamanAsimi):
            assert issubclass(sinif, PdfArcHatasi)
