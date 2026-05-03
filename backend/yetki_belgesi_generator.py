"""
Yetki Belgesi UDF Üretici
-------------------------
Gerçek UYAP UDF formatına göre yetki belgesi üretir.

Format: <template format_id="1.8"> köklü ZIP/XML.
Content: <![CDATA[...]]> içinde düz metin.
Paragraflar startOffset/length ile CDATA metnini referanslar.
"""
import io
import zipfile
from typing import List, Tuple


# ── Yardımcılar ───────────────────────────────────────────────────────────────

def uc(s: str) -> str:
    return (s or "").upper()


# ── Ana üretici ───────────────────────────────────────────────────────────────

def generate_yetki_belgesi_udf(data: dict) -> bytes:
    """
    data keys:
        veren       : {"ad": str, "tc": str, "sicil": str}
        yetkililar  : [{"ad": str, "tc": str, "sicil": str}, ...]
        buro_adres  : str
        muvekkil    : {"ad": str, "adres": str, "il": str,
                       "tc_vergi": str, "client_type": str}
        dayanak     : {"noterlik": str, "tarih": str, "yevmiye": str}
        kapsam      : str
    """
    veren      = data.get("veren", {})
    yetkililar = data.get("yetkililar", [])
    buro_adres = data.get("buro_adres", "")
    muvekkil   = data.get("muvekkil", {})
    dayanak    = data.get("dayanak", {})
    kapsam     = data.get("kapsam", "İlgili Vekaletnamedeki yetkilerin tamamı")

    ad_v    = uc(veren.get("ad", ""))
    tc_v    = veren.get("tc", "")
    sicil_v = veren.get("sicil", "")

    mv_ad    = uc(muvekkil.get("ad", ""))
    mv_adres = uc(muvekkil.get("adres", ""))
    mv_il    = uc(muvekkil.get("il", ""))
    mv_no    = muvekkil.get("tc_vergi", "")
    mv_type  = muvekkil.get("client_type", "Individual")
    mv_tam   = " ".join(filter(None, [mv_adres, mv_il]))

    day_not  = uc(dayanak.get("noterlik", ""))
    day_tar  = dayanak.get("tarih", "")
    day_yev  = dayanak.get("yevmiye", "")

    # ── 1. CDATA metnini satır satır oluştur ──────────────────────────────────
    # Her satır (line, bold, size, alignment) demeti
    # alignment: "0"=left "1"=center
    # bold: True/False
    # size: int (None = style default = 12)
    # family: "Times New Roman" | "Arial"

    Line = Tuple[str, bool, int, str, str]  # text, bold, size, alignment, family

    lines: List[Line] = []

    def add(text="", bold=False, size=12, align="0", family="Times New Roman"):
        lines.append((text, bold, size, align, family))

    # Başlık
    add()
    add("YETKİ BELGESİ", bold=True, size=13, align="1", family="Arial")
    add()

    # Yetki veren
    add("YETKİ BELGESİ VEREN AVUKAT :", bold=True, family="Arial")
    add()
    add(f"1. Av. {ad_v}", bold=False, family="Arial")
    veren_parts = [f"{uc(buro_adres)} adresinde mukim"]
    if tc_v:
        veren_parts.append(f"T.C. Kimlik No: {tc_v}")
    if sicil_v:
        veren_parts.append(f"{sicil_v} sicil no'lu")
    if tc_v:
        veren_parts.append(f"Vergi Daire ve No: {tc_v}")
    add(f"    ({', '.join(veren_parts)})", family="Arial")
    add()

    # Yetkili kılınanlar
    add("YETKİLİ KILINAN AVUKATLAR :", bold=True, family="Arial")
    add()
    for idx, av in enumerate(yetkililar, 1):
        ad_y    = uc(av.get("ad", ""))
        tc_y    = av.get("tc", "")
        sicil_y = av.get("sicil", "")
        add(f"{idx}. Av. {ad_y}", family="Arial")
        parts = ["Aynı adreste mukim"]
        if tc_y:
            parts.append(f"T.C. Kimlik No: {tc_y}")
        if sicil_y:
            parts.append(f"{sicil_y} sicil no'lu")
        add(f"    ({', '.join(parts)})", family="Arial")
        add()

    # Vekil eden
    add("VEKİL EDEN :", bold=True, family="Arial")
    add()
    add(f"1. {mv_ad}", family="Arial")
    mv_parts = []
    if mv_tam:
        mv_parts.append(f"{mv_tam} adresinde mukim")
    if mv_no:
        label = "Vergi No" if mv_type == "Corporate" else "T.C. Kimlik No"
        mv_parts.append(f"{label}: {mv_no}")
    add(f"    ({', '.join(mv_parts)})", family="Arial")
    add()

    # Dayanak vekaletname
    day_parts = []
    if day_not:  day_parts.append(day_not)
    if day_tar:  day_parts.append(f"{day_tar} tarihli")
    if day_yev:  day_parts.append(f"Yevmiye No: {day_yev}")
    if day_parts:
        add("DAYANAK VEKALETNAME :", bold=True, family="Arial")
        add()
        add(", ".join(day_parts), family="Arial")
        add()

    # Kapsam
    if kapsam:
        add("YETKİ BELGESİNİN KAPSAMI :", bold=True, family="Arial")
        add()
        add(kapsam, family="Arial")
        add()

    # Kanun maddesi
    add()
    add(
        "1136 sayılı Avukatlık Kanunu'nu değiştiren 4667 Sayılı Kanunun 36. maddesi "
        "ile 56. maddesine eklenen hüküm uyarınca vekaletname yerine geçmek üzere "
        "işbu yetki belgesi tarafımdan düzenlenmiştir.",
        family="Arial",
    )
    add()
    add()

    # İmza
    add(f"Av. {ad_v}", bold=True, align="1", family="Arial")
    add()

    # ── 2. CDATA metnini ve offset tablosunu hesapla ───────────────────────────
    # Her satır CDATA'ya \n ile eklenir; offset satırın başındaki konumdur.
    cdata_text = ""
    offsets: List[Tuple[int, int]] = []  # (start, length) her satır için

    for (text, *_) in lines:
        start = len(cdata_text)
        cdata_text += text + "\n"
        offsets.append((start, len(text)))

    # ── 3. XML'i string olarak oluştur ────────────────────────────────────────
    # ElementTree CDATA'yı desteklemediği için string birleştirme kullanıyoruz.

    para_xmls = []
    for i, (text, bold, size, align, family) in enumerate(lines):
        start, length = offsets[i]
        # Boş satır
        if length == 0:
            length_real = 1  # \n karakterini al
        else:
            length_real = length

        bold_attr   = ' bold="true"' if bold else ""
        align_attr  = f' Alignment="{align}"' if align != "0" else ""
        size_attr   = f' size="{size}"' if size != 12 else ""
        left_attr   = ' LeftIndent="2.0"' if text and not text.startswith("    ") else ""
        right_attr  = ' RightIndent="2.0"'

        para_xmls.append(
            f'<paragraph resolver="hvl-default"{align_attr}{left_attr}{right_attr}>'
            f'<content{bold_attr}{size_attr} family="{family}" '
            f'startOffset="{start}" length="{length_real}" />'
            f'</paragraph>'
        )

    paragraphs_xml = "\n".join(para_xmls)

    xml_str = (
        '<?xml version="1.0" encoding="UTF-8" ?>\n\n'
        '<template format_id="1.8" >\n'
        f'<content><![CDATA[{cdata_text}]]></content>'
        '<properties>'
        '<pageFormat mediaSizeName="1" '
        'leftMargin="42.51968" rightMargin="28.346449999999997" '
        'topMargin="42.51968" bottomMargin="42.51967999999999" '
        'paperOrientation="1" headerFOffset="20.0" footerFOffset="20.0" />'
        '</properties>\n'
        f'<elements >\n{paragraphs_xml}\n</elements>\n'
        '<styles>'
        '<style name="default" description="Geçerli" size="15" bold="false" '
        'family="Segoe UI" italic="false" foreground="-14012874" '
        'FONT_ATTRIBUTE_KEY="javax.swing.plaf.FontUIResource[family=Segoe UI,'
        'name=Segoe UI,style=plain,size=15]" />'
        '<style name="hvl-default" description="Gövde" size="12" '
        'family="Times New Roman" />'
        '</styles>\n'
        '</template>'
    )

    # ── 4. ZIP olarak paketle ─────────────────────────────────────────────────
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.xml", xml_str.encode("utf-8"))
    return buf.getvalue()
