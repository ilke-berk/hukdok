"""services/html_sanitizer.py — kanonik HTML temizliği (G023).

İddia YÜK LİSTESİ DEĞİL SINIF DÜZEYİNDEDİR: çıktı, tokenize edilecek belirsiz
bayt içermez. Bu yüzden her vaka ÇİFT İDDİA ile sınanır:

  (a) saldırgan host çıktının HİÇBİR yerinde yok,
  (b) çıktı `HTMLParser` ile YENİDEN ayrıştırıldığında uzak şema / `//`
      eşleşmesi ve allowlist ihlali yok.

`test_negative_control_legacy_chain_is_pierced` korpusun iş yaptığının kanıtıdır:
aynı vakalar G015'in (burada dondurulmuş) regex zincirini deliyor.
"""
import re
import time
from html.parser import HTMLParser

import pytest

from services import html_sanitizer
from services.html_sanitizer import (
    ALLOWED_ATTRS,
    DOC_PREFIX,
    DOC_SUFFIX,
    DROPPED_TAGS,
    GATED_ATTRS,
    MAX_HTML_CHARS,
    SanitizerError,
    html_to_text,
    sanitize_email_html,
)

EVIL = "evilhost-g023.test"
URL = f"http://{EVIL}/probe.png"

_TAG_NAME_OK = re.compile(r"^[a-z][a-z0-9]*$")
_SCHEME_RE = re.compile(r"(?:https?|ftps?|file|cid|data|javascript|vbscript)\s*:", re.IGNORECASE)
_WS_CTRL = re.compile(r"[\s\x00-\x20\x7f]")


# ── (b) iddiası: çıktının yeniden ayrıştırılması ────────────────────────────

class _OutputAuditor(HTMLParser):
    """Temizlenmiş çıktıyı BAĞIMSIZ olarak yeniden ayrıştırır ve politika
    ihlallerini toplar. Regex ile 'uzak URL ara' demek yerine çıktıyı gerçek
    bir tokenizer'a verir — G015'in kusuru tam da bu ikisinin ayrışmasıydı."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.violations = []

    def _check(self, tag, attrs):
        if not _TAG_NAME_OK.match(tag):
            self.violations.append(f"kanonik olmayan etiket adı: {tag!r}")
        if tag in DROPPED_TAGS:
            self.violations.append(f"düşürülmesi gereken etiket yayınlanmış: <{tag}>")
        for name, value in attrs:
            if name not in ALLOWED_ATTRS and name not in GATED_ATTRS:
                self.violations.append(f"allowlist dışı attribute: <{tag} {name}>")
            # Şema/protokol denetimi YALNIZ kapılı attribute'lar için: `title`,
            # `alt`, `class` gibi METİN değerli attribute'lar kaynak çekmez —
            # içlerindeki URL benzeri dizge gövde metnindeki adresle aynı
            # sınıftır (canlı dinleyiciyle doğrulandı, bkz. test_eml_expand.py).
            if name not in GATED_ATTRS:
                continue
            normalized = _WS_CTRL.sub("", value or "")
            if _SCHEME_RE.search(normalized):
                self.violations.append(f"uzak şema hayatta: <{tag} {name}={value!r}>")
            if normalized.startswith("//") or "\\" in normalized:
                self.violations.append(f"protokol-göreli/UNC hayatta: <{tag} {name}={value!r}>")

    def handle_starttag(self, tag, attrs):
        self._check(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._check(tag, attrs)


def _audit(out: str):
    """Sabit belge iskeleti (bizim ürettiğimiz `<meta charset>` dahil) denetim
    dışıdır — denetlenen, girdiden türeyen gövdedir."""
    assert out.startswith(DOC_PREFIX) and out.endswith(DOC_SUFFIX), f"iskelet bozulmuş: {out[:80]!r}"
    body = out[len(DOC_PREFIX):-len(DOC_SUFFIX)]
    auditor = _OutputAuditor()
    auditor.feed(body)
    auditor.close()
    return auditor.violations


def _assert_clean(out: str, host: str = EVIL):
    """Çift iddia — her vaka için ikisi birden."""
    assert host.lower() not in out.lower(), f"saldırgan host çıktıda: {out!r}"
    assert _audit(out) == [], f"yeniden ayrıştırmada ihlal: {_audit(out)} | çıktı: {out!r}"


# ── AC4 korpusu: 13 vaka ────────────────────────────────────────────────────
#
# İlk 8'i G015 sonrası zinciri DELEN, gerçek soffice GET'i üreten yüklerdir
# (görev dosyasındaki probe tablosu). Son 5'i regex yaklaşımının yapısal kör
# noktalarını (EOF, dengesiz tırnak) ve derinlik-savunması sınıflarını sınar.

def probe_payloads(host: str) -> dict:
    """Korpus, verilen host'a yönlendirilmiş hâliyle. Aynı kaynak hem birim
    testlerinde (sahte host) hem de canlı soffice kanıtında (127.0.0.1:port)
    kullanılır — iki yerde ayrışan iki korpus tutmamak için (bkz.
    test_eml_expand.py::test_no_outbound_request_after_sanitize).

    SIRA ÖNEMLİ: son iki vaka (dengesiz tırnak, EOF) tokenizer'da kendinden
    sonrasını yutar — tek belgede birleştirildiklerinde en sona konmalıdırlar.
    """
    url = f"http://{host}/probe.png"
    return {
        # tek tırnak içinde `>` — `[^>]*>` etiketi erken kesiyordu
        "P1_tek_tirnak_gt": f"<table dummy='a>b' background='{url}'><tr><td>hücre</td></tr></table>",
        # `_REMOTE_IMG_RE`'yi DE deliyordu
        "P6_img_alt_gt": f'<img alt="a>b" src="{url}">',
        # değer içinde newline + `>`
        "P7_deger_icinde_newline": f'<table dummy="a>\nb" background="{url}"><tr><td>x</td></tr></table>',
        # body background taşıyıcısı
        "P8_body_background": f'<body foo="a>b" background="{url}">gövde metni</body>',
        # art arda iki tırnaklı `>`
        "P9_iki_tuzakli_attr": f'<table a="x>y" b="p>q" background="{url}"><tr><td>x</td></tr></table>',
        # td background — hiçbir denylist'te yoktu
        "P11_td_background": f'<table><tr><td dummy="a>b" background="{url}">hücre</td></tr></table>',
        # ad öncesi `/` — `_ATTR_RE` `\s+` şart koşuyordu
        "P2_slash_ayirici": f'<table/background="{url}"><tr><td>x</td></tr></table>',
        # base href: TÜM göreli referansları uzak köke çözdürür
        "BASE_href": f'<base dummy="a>b" href="{url}"><img src="BIMG.png">',
        # CSS kaçışlı style (`u\72 l(` = `url(`)
        "CSS_KACISLI_STYLE": f'<div style="background:u\\72 l({url})">stil metni</div>',
        # meta refresh — URL değerin BAŞINDA değil
        "META_REFRESH": f'<meta http-equiv="refresh" content="0;url={url}">',
        # koşullu yorum içinde taşıyıcı
        "KOSULLU_YORUM": (
            f'<!--[if mso]><table background="{url}"><tr><td>Outlook metni</td>'
            "</tr></table><![endif]-->"
        ),
        # dengesiz tırnak — `_ATTR_RE` değeri hiç yakalamıyordu
        "DENGESIZ_TIRNAK": f'<table background="{url}><tr><td>x</td></tr></table>',
        # dosya sonunda kapanmamış etiket (`>` yok) — regex hiç eşleşmiyordu
        "EOF_kapanmamis_etiket": f'<p>metin</p><img src="{url}"',
    }


CORPUS = probe_payloads(EVIL)


def allowlisted_attr_probe(host: str) -> str:
    """Allowlist'teki METİN değerli attribute'lara uzak URL koyar.

    Bunlar kapılı DEĞİLDİR (title/alt/class… kaynak çekmez) — canlı dinleyici
    testinin bu iddiayı doğrulaması için üretilir."""
    url = f"http://{host}/attr.png"
    return (
        f'<p title="{url}" id="{url}" class="{url}" value="{url}" type="{url}" '
        f'lang="{url}" dir="{url}" bgcolor="{url}" color="{url}" face="{url}">'
        f'<img src="yerel.png" alt="{url}">allowlist taşıyıcı taraması</p>'
    )


@pytest.mark.parametrize("case_id", sorted(CORPUS))
def test_corpus_no_remote_url_survives(case_id):
    _assert_clean(sanitize_email_html(CORPUS[case_id]))


def test_corpus_size_is_thirteen():
    """Korpus daralırsa test sessizce zayıflamasın."""
    assert len(CORPUS) == 13


# ── AC4 taşıyıcı matrisi: ≥200 kombinasyon ──────────────────────────────────

_QUOTES = ['"', "'", ""]
_SEPARATORS = [" ", "/", "\n"]
_TRAPS = ["", 'dummy="a>b" ']
_CARRIERS = [
    "background", "src", "poster", "srcset", "data", "href",
    "xml:base", "longdesc", "usemap",
]
_SCHEMES = ["http://", "//", "HTTP://"]


def _matrix_cases():
    for quote in _QUOTES:
        for sep in _SEPARATORS:
            for trap in _TRAPS:
                for carrier in _CARRIERS:
                    for scheme in _SCHEMES:
                        value = f"{scheme}{EVIL}/x.png"
                        yield (
                            f"<table{sep}{trap}{carrier}={quote}{value}{quote}>"
                            "<tr><td>hücre</td></tr></table>"
                        )


def test_carrier_matrix_no_remote_url_survives():
    """{tırnak} × {ayırıcı} × {tuzak `>`} × {taşıyıcı} × {şema} kartezyeni."""
    cases = list(_matrix_cases())
    assert len(cases) >= 200, f"matris daralmış: {len(cases)}"
    failures = []
    for html in cases:
        out = sanitize_email_html(html)
        if EVIL.lower() in out.lower() or _audit(out):
            failures.append((html, out, _audit(out)))
    assert not failures, f"{len(failures)}/{len(cases)} kombinasyon delindi: {failures[:3]}"


def test_carrier_matrix_keeps_cell_text():
    """Matris aşırı temizlik yapmıyor: hücre metni her kombinasyonda duruyor."""
    for html in _matrix_cases():
        assert "hücre" in sanitize_email_html(html)


# ── AC5 negatif kontrol: G015'in dondurulmuş regex zinciri ──────────────────
#
# TARİHSEL KOPYA — üretim kodunda karşılığı YOKTUR (G023 sildi). Amacı tek:
# yukarıdaki korpusun gerçekten iş yaptığını kanıtlamak. Testin kendisi geçmiş
# bir kusuru sabitler, davranış sözleşmesi değildir; silinirse AC5 kanıtı gider.

_L_SCRIPT = re.compile(r"<script\b.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_L_STYLE_BLOCK = re.compile(r"<style\b.*?</style\s*>", re.IGNORECASE | re.DOTALL)
_L_LINK_TAG = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_L_REMOTE_IMG = re.compile(
    r"<img\b[^>]*\bsrc\s*=\s*[\"']?(?:cid:|https?:|//)[^>]*?>", re.IGNORECASE | re.DOTALL
)
_L_META_CHARSET = re.compile(r"<meta\b[^>]*charset[^>]*>", re.IGNORECASE)
_L_TAG = re.compile(r"<[A-Za-z!/][^>]*>", re.DOTALL)
_L_ATTR = re.compile(
    r"""\s+([A-Za-z_:][-.\w:]*)\s*=\s*("[^"]*"|'[^']*'|[^\s"'>`=]+)""", re.DOTALL
)
_L_REMOTE_SCHEME = re.compile(r"(?:https?|ftps?|file|cid)\s*:", re.IGNORECASE)
_L_PROTO_RELATIVE = re.compile(r"^(?://|\\\\)")
_L_ATTR_STRIP = re.compile(r"[\s\x00-\x20\x7f]")
_L_CSS_IMPORT = re.compile(r"@import\b[^;}]*;?", re.IGNORECASE)
_L_CSS_URL = re.compile(r"url\s*\([^)]*\)", re.IGNORECASE)


def _legacy_clean(content: str) -> str:
    """G015 sonrası zincirin birebir kopyası (routes/case_intake.py, bc35eb1)."""
    import html as html_lib

    def _normalize(raw: str) -> str:
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return _L_ATTR_STRIP.sub("", html_lib.unescape(value))

    def _attr(m):
        name, raw = m.group(1), m.group(2)
        value = _normalize(raw)
        if _L_REMOTE_SCHEME.search(value) or _L_PROTO_RELATIVE.match(value):
            return ""
        if name.lower() == "style":
            cleaned = _L_CSS_URL.sub("none", _L_CSS_IMPORT.sub("", raw))
            if cleaned != raw:
                return f" {name}={cleaned}"
        return m.group(0)

    out = _L_SCRIPT.sub("", content)
    out = _L_STYLE_BLOCK.sub("", out)
    out = _L_LINK_TAG.sub("", out)
    out = _L_REMOTE_IMG.sub("", out)
    out = _L_TAG.sub(lambda m: _L_ATTR.sub(_attr, m.group(0)), out)
    return _L_META_CHARSET.sub("", out)


def test_negative_control_legacy_chain_is_pierced():
    """AC5: korpus iş yapıyor mu? Eski zincir en az 8 vakada deliniyor."""
    pierced = [cid for cid, html in CORPUS.items() if EVIL.lower() in _legacy_clean(html).lower()]
    assert len(pierced) >= 8, f"korpus zayıf — eski zinciri yalnız {len(pierced)} vaka deliyor: {pierced}"


def test_negative_control_matrix_is_pierced():
    """Matris de körelmemiş: eski zincir kombinasyonların bir kısmını geçiriyor."""
    pierced = sum(1 for html in _matrix_cases() if EVIL.lower() in _legacy_clean(html).lower())
    assert pierced > 0, "matris eski zinciri hiç delmiyor — kombinasyonlar anlamsızlaşmış"


# ── AC2: politika tek sabitte ───────────────────────────────────────────────

def test_policy_constants_are_disjoint_and_gated_set_is_exact():
    assert GATED_ATTRS == {"src", "href", "style"}
    assert not (ALLOWED_ATTRS & GATED_ATTRS), "kapılı attribute allowlist'te de görünüyor"
    assert "base" in DROPPED_TAGS and "meta" in DROPPED_TAGS and "script" in DROPPED_TAGS


def test_unknown_attributes_are_dropped_without_denylist():
    """Allowlist dışı her attribute düşer — `on*` taşıyıcılarını saymaya gerek yok."""
    out = sanitize_email_html(
        '<div onclick="x()" onmouseover="y()" formaction="/z" data-track="1" class="k">metin</div>'
    )
    assert "onclick" not in out.lower()
    assert "onmouseover" not in out.lower()
    assert "formaction" not in out.lower()
    assert "data-track" not in out.lower()
    assert 'class="k"' in out and "metin" in out


def test_img_without_usable_src_is_dropped_whole():
    """Boş `<img>` iskeleti bırakmak soffice'te kırık görsel kutusu çizer."""
    assert "<img" not in sanitize_email_html('<img src="cid:logo1"><p>İmza</p>').lower()
    assert "<img" not in sanitize_email_html("<img><p>İmza</p>").lower()
    assert '<img src="yerel.png">' in sanitize_email_html('<img src="yerel.png" srcset="x">')


def test_style_attribute_dropped_whole_when_suspicious():
    out = sanitize_email_html('<div style="background:url(/yerel.png);color:red">x</div>')
    assert "style" not in out.lower()          # `none` ile ikame edilmez, komple düşer
    assert "<div>x</div>" in out
    assert 'style="color:#ff0000"' in sanitize_email_html('<div style="color:#ff0000">x</div>')


@pytest.mark.parametrize("value", [
    "background:u/**/rl(http://x.test/a.png)",   # CSS yorumu adı bölüyor (bypass avı bulgusu)
    "background:URL(http://x.test/a.png)",       # büyük harf
    "background:&#117;rl(http://x.test/a.png)",  # entity
    "background:u\\72 l(http://x.test/a.png)",   # CSS kaçışı
    "@import 'http://x.test/a.css'",
    "width:expression(alert(1))",
    "background-image:image-set('http://x.test/a.png')",
])
def test_style_gate_is_class_level_not_name_matching(value):
    """Style kapısı `url` adını aramaz; çağrı sözdizimi/kaçış/yorum sınıfını kapatır."""
    out = sanitize_email_html(f'<div style="{value}">metin</div>')
    assert "style" not in out.lower(), out
    assert "x.test" not in out
    assert "metin" in out


def test_declarations_and_comments_dropped():
    out = sanitize_email_html(
        "<!DOCTYPE html PUBLIC 'evil'><?php echo 1 ?><!--sıradan yorum--><![CDATA[x]]><p>kalan</p>"
    )
    assert out.count("<!DOCTYPE html>") == 1     # iskeletten gelen SABİT bildirim
    assert "PUBLIC" not in out and "php" not in out
    assert "sıradan yorum" not in out
    assert "<p>kalan</p>" in out


# ── AC3: fail-closed ────────────────────────────────────────────────────────

def test_size_cap_raises_sanitizer_error():
    with pytest.raises(SanitizerError):
        sanitize_email_html("<p>" + "a" * 100 + "</p>", max_chars=10)


def test_default_size_cap_is_documented_value():
    """Tavan ölçüme bağlıdır (1 MB = 237 ms); sessizce büyütülmesin."""
    assert MAX_HTML_CHARS == 2_000_000


def test_non_string_input_raises():
    with pytest.raises(SanitizerError):
        sanitize_email_html(None)  # type: ignore[arg-type]


# ── AC8: metin sadakati ─────────────────────────────────────────────────────

def test_turkish_entities_and_table_structure_preserved():
    out = sanitize_email_html(
        '<table border="1" cellpadding="4"><tr><td colspan="2">'
        "Tebli&#287; &amp; T&uuml;ketici &#304;&#351;lemi</td></tr></table>"
    )
    assert "Tebliğ &amp; Tüketici İşlemi" in out
    assert '<table border="1" cellpadding="4">' in out
    assert '<td colspan="2">' in out
    assert "</table>" in out


def test_broken_markup_keeps_all_text():
    out = sanitize_email_html("<td>a<td>b<p>c</div>")
    assert "a" in out and "b" in out and "c" in out


def test_conditional_comment_visible_text_preserved():
    out = sanitize_email_html(
        '<!--[if mso]><p style="color:red">Outlook metni</p><![endif]--><p>normal</p>'
    )
    assert "Outlook metni" in out
    assert "normal" in out


def test_plain_text_urls_in_body_text_are_kept():
    """Gövde METNİNDEKİ adres istek doğurmaz ve modele bilgi taşır — korunur."""
    out = sanitize_email_html("<p>Detay: http://ornek.test/dosya adresinde</p>")
    assert "http://ornek.test/dosya" in out


def test_lone_less_than_in_text_survives_as_entity():
    out = sanitize_email_html("<p>tutar &lt; 5 TL</p>")
    assert "tutar &lt; 5 TL" in out


def test_incomplete_tag_remnant_is_not_emitted_raw():
    out = sanitize_email_html('<p>metin</p><table background="http://kalinti.test/x')
    assert "kalinti.test" not in out
    assert "metin" in out


# ── G025: `&lt;` ile BAŞLAYAN metin kaybı ───────────────────────────────────
#
# G023 `handle_data`'da `<` ile başlayan koşuyu "kalıntı" sayıp atıyordu.
# `convert_charrefs=True` yüzünden `&lt;` buraya çözülmüş `<` olarak gelir →
# `<ad@firma.com>` ve `<<yer tutucu>>` ile BAŞLAYAN gövde metinleri sessizce
# siliniyordu. Yük tablosu bağımsız denetimin canlı çıktısından birebir alındı.

G025_LOSS_CASES = {
    "p_acili_hitap": (
        "<p>&lt;Sayin Ilgili&gt;, ekte bilirkişi raporu ve fatura yer almaktadir. "
        "Toplam tutar 145.000 TL'dir.</p>",
        "&lt;Sayin Ilgili&gt;, ekte bilirkişi raporu ve fatura yer almaktadir. "
        "Toplam tutar 145.000 TL'dir.",
    ),
    "td_eposta_adresi": (
        "<td>&lt;av.ilke@lexis.com.tr&gt; tarafindan 12.08.2026 tarihinde gonderildi</td>",
        "&lt;av.ilke@lexis.com.tr&gt; tarafindan 12.08.2026 tarihinde gonderildi",
    ),
    "div_cift_acili_yer_tutucu": (
        "<div>&lt;&lt;DOSYA NO&gt;&gt; 2026/1234 Esas - durusma 15.09.2026</div>",
        "&lt;&lt;DOSYA NO&gt;&gt; 2026/1234 Esas - durusma 15.09.2026",
    ),
    "sayisal_entity": (
        "<p>&#60;av.ilke@lexis.com.tr&#62; imzali dilekce ektedir</p>",
        "&lt;av.ilke@lexis.com.tr&gt; imzali dilekce ektedir",
    ),
}


@pytest.mark.parametrize("case_id", sorted(G025_LOSS_CASES))
def test_text_starting_with_escaped_lt_is_preserved(case_id):
    """Metnin TAMAMI çıktıda — eskiden yalnız `&lt;` kalıyordu."""
    payload, expected = G025_LOSS_CASES[case_id]
    out = sanitize_email_html(payload)
    assert expected in out, out
    _assert_clean(out)


@pytest.mark.parametrize("case_id", sorted(G025_LOSS_CASES))
def test_html_to_text_keeps_text_starting_with_escaped_lt(case_id):
    """Fail-closed düz-metin yolu da aynı metni kaybetmemeli (ikinci şans)."""
    payload, _ = G025_LOSS_CASES[case_id]
    text = html_to_text(payload)
    # Düz-metin yolunda entity ÇÖZÜLMÜŞ hâliyle durur (çağıran escape eder).
    assert "av.ilke@lexis.com.tr" in text or "Sayin Ilgili" in text or "DOSYA NO" in text
    assert text.lstrip().startswith("<"), text


def test_escaped_lt_run_is_lossless_for_text_extractor():
    """`_TextExtractor` koşunun BAŞINDAKİ `<` yüzünden koşuyu atmıyor."""
    text = html_to_text("<div>&lt;&lt;DOSYA NO&gt;&gt; 2026/1234 Esas</div>")
    assert "<<DOSYA NO>> 2026/1234 Esas" in text


def test_bare_less_than_still_emitted_as_entity():
    """Etiket açamayan tek `<` kaçışlanarak korunur (davranış değişmedi)."""
    out = sanitize_email_html("<p>x</p><")
    assert out.endswith("&lt;" + DOC_SUFFIX), out
    assert _audit(out) == []


@pytest.mark.parametrize("payload", [
    '<p>metin</p><img src="http://kalinti.test/x',              # EOF'ta kapanmamış etiket
    '<p>metin</p><img src="http://kalinti.test/a>b',            # kalıntı içinde `>`
    '<table background="http://kalinti.test/p.png><tr><td>x',   # dengesiz tırnak
    "<p>metin</p></di",                                         # kapanmamış kapanış etiketi
    "<p>metin</p><?php http://kalinti.test/y",                  # kapanmamış PI
])
def test_incomplete_markup_never_reaches_handle_data(payload):
    """ÖLÇÜM KİLİDİ (G025): kalıntı atma kuralı bu katmanda karşılıksızdı.

    `handle_data`'yı artık kaçışlıyoruz (atmıyoruz); bunun güvenli olmasının
    sebebi, HTMLParser'ın tamamlanmamış markup'ı `handle_data`'ya HİÇ
    vermemesidir (py3.10.20'de ölçüldü). Bir Python yükseltmesi bunu
    değiştirirse kalıntı metni kaçışlanmış hâlde görünür olur — inert kalır ama
    davranış değişir; bu test o günü SESSİZ geçmesin diye durur.
    """
    seen = []
    orig = html_sanitizer._CanonicalSerializer.handle_data

    class _Spy(html_sanitizer._CanonicalSerializer):
        def handle_data(self, data):
            seen.append(data)
            orig(self, data)

    out: list = []
    parser = _Spy(out)
    parser.feed(payload)
    parser.close()
    remnants = [d for d in seen if d.startswith("<") and len(d) > 1]
    assert remnants == [], f"kalıntı handle_data'ya düştü: {remnants}"
    assert "kalinti.test" not in "".join(out)


# ── html_to_text (fail-closed yolunun girdisi) ──────────────────────────────

def test_html_to_text_drops_markup_and_script():
    text = html_to_text("<p>Sayın yetkili</p><script>alert('x')</script><p>Tebliğ</p>")
    assert "Sayın yetkili" in text and "Tebliğ" in text
    assert "alert" not in text and "<p>" not in text


def test_html_to_text_never_raises():
    assert html_to_text(None) == ""
    assert "metin" in html_to_text('<p>metin</p><img src="http://x.test/a')


# ── AC9: performans ─────────────────────────────────────────────────────────

def _representative_body(target_chars: int) -> str:
    row = (
        '<tr><td style="color:#333" class="c">Tebliğ bilgisi — T.T: 23/07/2026</td>'
        '<td><a href="/yerel/dosya">bak</a></td></tr>'
    )
    return (
        '<html><body><table border="1">'
        + row * (target_chars // len(row) + 1)
        + "</table></body></html>"
    )


def test_one_megabyte_body_under_budget():
    html = _representative_body(1_000_000)
    assert len(html) >= 1_000_000
    start = time.perf_counter()
    out = sanitize_email_html(html)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert "Tebliğ bilgisi" in out
    # Ölçüm (G023, konteyner): ~250 ms. Eşik CI dalgalanmasına pay bırakır;
    # amaç mutlak hız değil, boyut tavanının makul kaldığını sabitlemek.
    assert elapsed_ms < 3000, f"1 MB gövde {elapsed_ms:.0f} ms sürdü"


def test_mechanism_is_tokenizer_and_legacy_patterns_are_gone():
    """AC1 mekanizma kilidi: temizlik tokenizer'a dayanır, etiket taramasına değil."""
    from routes import case_intake

    assert issubclass(html_sanitizer._CanonicalSerializer, HTMLParser)
    for name in (
        "_TAG_RE", "_ATTR_RE", "_SCRIPT_RE", "_LINK_TAG_RE",
        "_REMOTE_IMG_RE", "_STYLE_BLOCK_RE", "_META_CHARSET_RE",
        "_strip_remote_refs", "_clean_tag_attrs",
    ):
        assert not hasattr(case_intake, name), f"regex zincirinin kalıntısı: {name}"
