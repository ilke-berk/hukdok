"""E-posta gövdesi HTML temizliği — tokenizer + yeniden serileştirme (G023).

NEDEN REGEX DEĞİL: regex tabanlı temizlik (G015) saldırganın BAYTLARINI çıktıya
aynen geçiriyordu. `<[^>]*>` etiketi tırnak içindeki `>` karakterinde kesiyor,
attribute deseni ad öncesinde boşluk şart koşuyor, kapanmamış etiket ve dengesiz
tırnak hiç eşleşmiyordu; LibreOffice'in tokenizer'ı her farklı düşündüğü noktada
uzak kaynak isteği yeniden doğuyordu (13 ajanlı bypass avında 8 taşıyıcı ayakta
kaldı).

BURADAKİ İDDİA SINIF DÜZEYİNDEDİR: çıktı, tokenize edilecek belirsiz bayt
içermez. Girdi `html.parser` ile ayrıştırılır ve çıktı SIFIRDAN yeniden yazılır:

* etiket adı yalnız `[a-z][a-z0-9]*` kalıbına uyuyorsa yayınlanır,
* attribute adı sabit bir allowlist'ten gelir (allowlist dışı her şey — `on*`
  dahil — düşer; taşıyıcı uzayını tek tek saymaya gerek kalmaz),
* attribute değeri DAİMA çift tırnaklı ve `html.escape` edilmiş yazılır,
* metin `html.escape` edilir — ATILMAZ (G025: kaçışlama hem güvenli hem
  kayıpsız; `&lt;` ile başlayan gövde metni artık yok olmuyor).

Belge iskeleti (DOCTYPE + html/head/meta/body) sabittir ve BİZİM üretimimizdir;
girdideki iskelet etiketleri ile bildirimler (DOCTYPE/PI/bogus decl) yayınlanmaz.

Fail-closed: temizlik yapılamazsa `SanitizerError` atılır — çağıran ham HTML'i
soffice'e ASLA vermez, düz-metin yoluna düşer (bkz. routes/case_intake.py).
"""
import html as html_lib
import re
from html.parser import HTMLParser
from typing import List, Optional, Tuple

# Boyut tavanı (karakter). Ölçüm (G023, konteyner): 1 MB temsili gövde 237 ms.
# Temizlik istek işleyicisinde SATIR İÇİ koştuğu için tavan 2 MB'a konuldu —
# en kötü durum ~0,5 sn. Aşan gövde istisna alır ve düz-metin yoluna düşer.
MAX_HTML_CHARS = 2_000_000

# Koşullu yorum içeriği aynı temizlikten geçirilir; iç içe yorumda özyineleme
# bu derinlikte durur.
_MAX_COND_DEPTH = 3


# Belge iskeleti SABİTTİR ve girdiden bağımsızdır — DOCTYPE dahil tek kaynak.
DOC_PREFIX = '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
DOC_SUFFIX = "</body></html>"


class SanitizerError(Exception):
    """Temizlik başarısız — çağıran ham HTML'i soffice'e GÖNDERMEZ."""


# ── POLİTİKA: iki sabit ─────────────────────────────────────────────────────
#
# Komple düşürülen etiketler (void olmayanların ALT AĞACI da düşer). `base`
# attribute soymakla kapanmaz — tek başına `<base href>` tüm göreli referansları
# uzak bir köke çözdürür; bu yüzden etiket komple gider.
DROPPED_TAGS = frozenset({
    "applet", "audio", "base", "canvas", "embed", "frame", "frameset",
    "iframe", "image", "input", "link", "math", "meta", "noframes",
    "object", "param", "script", "source", "style", "svg", "template",
    "track", "video",
})

# İzin verilen attribute adları. Değer kapısı YALNIZ `src`/`href`/`style` için
# çalışır (aşağıdaki GATED_ATTRS); bu üçü dışındaki her ad ya bu listededir ya
# da düşer.
ALLOWED_ATTRS = frozenset({
    # yapı
    "colspan", "rowspan", "border", "cellpadding", "cellspacing", "align",
    "valign", "width", "height", "nowrap", "span",
    # anlam
    "lang", "dir", "class", "id", "title", "alt", "start", "value", "type",
    # biçim
    "bgcolor", "color", "face", "size",
})

GATED_ATTRS = frozenset({"src", "href", "style"})

# ── HTML olguları (politika değil) ──────────────────────────────────────────
#
# Kapanış etiketi olmayan öğeler: düşürülenlerinde alt ağaç bastırması
# BAŞLATILMAZ (aksi hâlde `<meta>` sonrası belgenin tamamı yutulurdu).
_VOID_TAGS = frozenset({
    "area", "base", "basefont", "br", "col", "embed", "frame", "hr", "image",
    "img", "input", "link", "meta", "param", "source", "track", "wbr",
})

# Belge iskeletini biz yazdığımız için girdideki karşılıkları yayınlanmaz —
# İÇERİKLERİ korunur (alt ağaç bastırması yok: `</head>` sıklıkla eksiktir ve
# bastırma gövdeyi yutardı).
_SKELETON_TAGS = frozenset({"html", "head", "body", "title"})

_SUBTREE_DROP = DROPPED_TAGS - _VOID_TAGS

_TAG_NAME_RE = re.compile(r"^[a-z][a-z0-9]*$")
_ATTR_NAME_RE = re.compile(r"^[a-z_:][-.\w:]*$", re.ASCII)
# Karar için normalizasyon: boşluk + kontrol karakterleri atılır
# (`h&#9;ttp://…` gibi kaçışlar kapıya takılsın).
_WS_CTRL_RE = re.compile(r"[\s\x00-\x20\x7f]")
# `style` değerinde bunlardan biri varsa attribute KOMPLE düşer — `url(`
# literalini arayıp `none` ile ikame etmek CSS kaçışlarına kördür.
#
# Kural sınıf düzeyindedir: satır içi stilde FONKSİYON ÇAĞRISI SÖZDİZİMİ (`(`),
# CSS kaçışı (`\`) ve CSS YORUMU (`/*`) yasak. Ad listesi (`url`, `@import`,
# `expression`, `image-set`) bunun üstüne durur. Yorum yasağı olmadan
# `background:u/**/rl(…)` gibi ad-bölen varyantlar kapıyı deliyordu (G023 bypass
# avı bulgusu); `(` yasağı ise adı hiç okumadan tüm çağrı sınıfını kapatır.
# Görsel sadakat hedef olmadığı için kaybedilen `calc()` vb. önemsizdir.
_STYLE_BAD_RE = re.compile(r"url|@import|expression|image-set|\\|\(|/\*", re.IGNORECASE)
# `<!--[if mso]>…<![endif]-->` — içindeki görünür metin kaybolmasın diye
# içerik aynı temizlikten geçirilip yayınlanır.
_COND_COMMENT_RE = re.compile(r"^\s*\[if\b[^\]]*\]\s*>(.*)<!\s*\[\s*endif\s*\]\s*$", re.IGNORECASE | re.DOTALL)

# Metin çıkarımında satır sonu üreten öğeler.
_BLOCK_TAGS = frozenset({
    "br", "p", "div", "tr", "table", "li", "ul", "ol", "hr", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "pre",
})


def _normalize_value(raw: str) -> str:
    """Değeri KARAR için normalize eder: entity çöz, boşluk/kontrol karakterlerini
    at. HTMLParser attribute değerlerini zaten bir kez unescape eder; buradaki
    ikinci çözüm kapıyı yalnız DAHA agresif yapar (fail-closed yön)."""
    return _WS_CTRL_RE.sub("", html_lib.unescape(raw))


class _CanonicalSerializer(HTMLParser):
    """Girdiyi ayrıştırır, çıktıyı `out` listesine kanonik HTML olarak yazar."""

    def __init__(self, out: List[str], depth: int = 0) -> None:
        super().__init__(convert_charrefs=True)
        self._out = out
        self._depth = depth
        self._suppress: List[str] = []

    # ── etiketler ───────────────────────────────────────────────────────
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if self._suppress:
            if tag in _SUBTREE_DROP:
                self._suppress.append(tag)
            return
        if tag in DROPPED_TAGS:
            if tag in _SUBTREE_DROP:
                self._suppress.append(tag)
            return
        if tag in _SKELETON_TAGS or not _TAG_NAME_RE.match(tag):
            return
        rendered = self._render_attrs(tag, attrs)
        if rendered is None:
            # `<img>`: src kapıdan geçemedi → etiket komple düşer. Yalnız
            # attribute soymak boş iskelet bırakır, soffice kırık görsel
            # kutusu çizer (G015'in doğru kararı).
            return
        self._out.append(f"<{tag}{rendered}>")

    def handle_endtag(self, tag: str) -> None:
        if self._suppress:
            if tag in self._suppress:
                # En İÇTEKİ eşleşmeye kadar kapat (iç içe aynı adlı düşük etiket).
                idx = len(self._suppress) - 1 - self._suppress[::-1].index(tag)
                del self._suppress[idx:]
            return
        if tag in DROPPED_TAGS or tag in _SKELETON_TAGS or tag in _VOID_TAGS:
            return
        if not _TAG_NAME_RE.match(tag):
            return
        self._out.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    # ── attribute süzgeci ───────────────────────────────────────────────
    def _render_attrs(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> Optional[str]:
        parts: List[str] = []
        src_kept = False
        for raw_name, value in attrs:
            name = (raw_name or "").lower()
            if not _ATTR_NAME_RE.match(name):
                continue
            if name in GATED_ATTRS:
                value = _gate_value(name, value)
                if value is None:
                    continue
            elif name not in ALLOWED_ATTRS:
                continue
            if name == "src":
                src_kept = True
            if value is None:
                parts.append(f" {name}")
            else:
                parts.append(f' {name}="{html_lib.escape(value, quote=True)}"')
        if tag == "img" and not src_kept:
            return None
        return "".join(parts)

    # ── metin ───────────────────────────────────────────────────────────
    def handle_data(self, data: str) -> None:
        """Metin DAİMA kaçışlanarak yayınlanır — atılmaz (G025).

        G023 burada `<` ile BAŞLAYAN veriyi "tamamlanmamış markup kalıntısı"
        sayıp atıyordu. `convert_charrefs=True` olduğu için `&lt;` / `&#60;`
        buraya çözülmüş `<` olarak gelir; yani kural, `&lt;` ile başlayan her
        gövde metnini (`<ad@firma.com>`, `<<yer tutucu>>`) sessizce siliyordu.

        ÖLÇÜM (G025, konteyner py3.10.20): kalıntı korkusu bu katmanda
        karşılıksız — HTMLParser kapanmamış etiketi (`<img src="…` EOF'ta) ve
        dengesiz tırnaklı etiketi `handle_data`'ya HİÇ vermiyor, sessizce
        yutuyor. `<` ile başlayıp buraya ulaşan tek veri, etiket açamayan TEK
        karakterlik `"<"`tır; onun kaçışlanmışı da zaten `&lt;`. Kalıntı ileride
        (Python sürümü değişirse) buraya düşerse kaçışlanmış hâli inert kalır —
        canlı soffice dinleyicisiyle 0 istek ölçüldü — ve
        `test_incomplete_tag_remnant_is_not_emitted_raw` bunu haber verir.
        """
        if self._suppress or not data:
            return
        self._out.append(html_lib.escape(data, quote=False))

    # ── yorum / bildirim ────────────────────────────────────────────────
    def handle_comment(self, data: str) -> None:
        if self._suppress or self._depth >= _MAX_COND_DEPTH:
            return
        match = _COND_COMMENT_RE.match(data or "")
        if not match:
            return
        inner = _CanonicalSerializer(self._out, self._depth + 1)
        inner.feed(match.group(1))
        inner.close()

    def handle_decl(self, decl: str) -> None:
        """DOCTYPE yayınlanmaz — belge iskeleti sabit `<!DOCTYPE html>` ile
        BİR KEZ, girdiden bağımsız yazılır (bkz. sanitize_email_html)."""

    def unknown_decl(self, data: str) -> None:
        """CDATA / bogus bildirim düşer."""

    def handle_pi(self, data: str) -> None:
        """Processing instruction düşer."""


def _gate_value(name: str, value: Optional[str]) -> Optional[str]:
    """Korunan attribute'ların değer kapısı. Geçemezse None döner (attribute düşer)."""
    if value is None:
        return None
    normalized = _normalize_value(value)
    if name == "style":
        return None if _STYLE_BAD_RE.search(normalized) else value
    # `src`/`href`: yalnız SAF GÖRELİ yol geçer. `:` şema taşıyabilir
    # (http, cid, data, file, javascript…), `//` protokol-göreli, `\` UNC.
    if ":" in normalized or normalized.startswith("//") or "\\" in normalized:
        return None
    return value


def sanitize_email_html(
    raw: str,
    *,
    body_prefix: str = "",
    max_chars: Optional[int] = None,
) -> str:
    """Ham e-posta HTML'ini kanonik, uzak-kaynaksız bir belgeye çevirir.

    `body_prefix` BİZİM ürettiğimiz (zaten kaçışlanmış) başlık tablosudur —
    temizlikten geçmez, gövdenin başına konur.

    Raises:
        SanitizerError: boyut tavanı aşıldığında ya da ayrıştırma patladığında.
            Çağıran bu durumda ham HTML'i soffice'e VERMEZ (fail-closed).
    """
    if not isinstance(raw, str):
        raise SanitizerError("gövde metin değil")
    limit = MAX_HTML_CHARS if max_chars is None else max_chars
    if len(raw) > limit:
        raise SanitizerError(f"gövde boyut tavanını aştı ({len(raw)} > {limit} karakter)")

    out: List[str] = []
    try:
        parser = _CanonicalSerializer(out)
        parser.feed(raw)
        parser.close()
    except Exception as e:  # pragma: no cover - HTMLParser pratikte atmaz
        raise SanitizerError(f"HTML ayrıştırılamadı: {e}") from e

    return DOC_PREFIX + body_prefix + "".join(out) + DOC_SUFFIX


class _TextExtractor(HTMLParser):
    """Görünür metin çıkarımı — fail-closed düz-metin yolunun girdisi."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._suppress: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if self._suppress:
            if tag in _SUBTREE_DROP:
                self._suppress.append(tag)
            return
        if tag in _SUBTREE_DROP:
            self._suppress.append(tag)
            return
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._suppress:
            if tag in self._suppress:
                idx = len(self._suppress) - 1 - self._suppress[::-1].index(tag)
                del self._suppress[idx:]
            return
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        """Fail-closed yol metin KAYBETMEZ (G025) — `<` ile başlayan koşu da
        aynen alınır. Çıktı çağıranda `html.escape` ile inert'lenip `<pre>`
        içine konur (routes/case_intake.py::_plain_body_document), bu yüzden
        burada kaçışlama yapılmaz; ikinci kaçışlama metni bozardı."""
        if self._suppress or not data:
            return
        self.parts.append(data)


def html_to_text(raw: str) -> str:
    """HTML'den görünür metin. ASLA istisna atmaz — çağıran sonucu
    `html.escape` ile inert'leyip `<pre>` içine koyar."""
    extractor = _TextExtractor()
    try:
        extractor.feed(raw or "")
        extractor.close()
    except Exception:
        return raw or ""
    return re.sub(r"\n{3,}", "\n\n", "".join(extractor.parts)).strip()
