"""
party_check.py — Tanıdık Sorgu / Çıkar Çatışması Kontrolü

Dosya açılırken girilen taraf isimlerini (davacı/davalı/başvuran) mevcut
kayıtlarla karşılaştırır: cari kayıtları (clients) ve geçmiş dosya tarafları
(case_parties). Saf modül — DB erişimi yok; satırlar route katmanından dict
olarak gelir, böylece DB'siz conftest ile birim test edilebilir.

Eşleşme kademeleri (güçlüden zayıfa):
  1. tc_no      → "certain"  (11 haneli TC tam eşleşme)
  2. name_exact → "probable" (normalize edilmiş isim eşitliği; kelime sırası
                              farklı olsa da tüm kelimeler aynıysa exact sayılır)
  3. name_fuzzy → "possible" (KELİME BAZLI Levenshtein: kelime sayısı eşit
                              olmalı ve HER kelime kendi içinde eşleşmeli
                              [≤7 harf→1, daha uzun→2 harf tolerans].
                              "Ali Veli" ↔ "Ali Beki" eşleşmez — yalnızca ilk
                              ismin aynı olması yetmez, soyisim de eşleşmeli.)

conflict=True koşulu (TEK):
  CLIENT olmayan sorgu, contact_type="Client" bir cari kaydıyla eşleşirse
  (karşı taraf ofisin müvekkili → çıkar çatışması riski).
  Müvekkil satırı çatışma ÜRETMEZ — müvekkilin geçmiş dosyalarda karşı taraf
  olarak görünmesi bilgi olarak listelenir (matches), conflict sayılmaz
  (2026-08-01 kullanıcı kararı: çıkar çatışması yalnız karşı tarafa bakılır).
  TC eşleşip isim eşleşmeyen kayıtlar da yalnız matches'ta raporlanır.

Hazırlanmış aday satırları (G017): `prepare_candidate_rows` satıra `_key`
(normalize ad türevleri) ve `_tc` (normalize TC) alanlarını ekler; check_parties
bunları VARSA kullanır, yoksa satır başına hesaplar. Sonuç her iki durumda
birebir aynıdır — hazırlık yalnız CPU tasarrufudur (aday cache'i:
`routes/parties.py`). Bu alanlar yanıta çıkmaz.
"""

import re
import unicodedata
from functools import lru_cache

from text_utils import turkish_upper
from case_matcher import _normalize as _fold_diacritics

# Unvanlar: sondaki nokta veya kelime sınırı zorunlu — "AVNİ" gibi isimlerin
# başındaki "AV"nin yanlışlıkla silinmemesi için client_normalizer'daki
# kalıplardan daha sıkı.
_TITLE_PATTERN = re.compile(
    r"\b(DR|AV|UZM|DOC|DOÇ|PROF|OP|DT|AVUKAT|STJ)\b\.?\s*", re.IGNORECASE
)

# Kurumsal isimlerde fuzzy gürültü üretir (sigorta şirketleri birbirine benzer).
# Normalize edilmiş isimde KELİME olarak aranır ("HASAN"daki "AS" gibi
# substring yanlış pozitifleri önlemek için).
_CORPORATE_WORDS = frozenset({
    "SIGORTA", "HOLDING", "ANONIM", "LTD", "STI", "LIMITED",
    "SIRKETI", "TIC", "TICARET", "SAN", "SANAYI", "AS",
})

_FUZZY_MIN_LEN = 5
_NAME_MIN_LEN = 4


@lru_cache(maxsize=8192)
def normalize_person_name(name: str) -> str:
    """Karşılaştırma anahtarı üretir: birleşik işaret temizliği → Türkçe upper
    → diakritik katlama → unvan temizliği → boşluk sadeleştirme.

    NFD + combining-strip önemli: bazı kayıtlarda 'i̇' (i + U+0307 birleşik
    nokta) gibi görünmez karakterler var; bunlar temizlenmezse birebir aynı
    isim exact yerine fuzzy'ye düşer ya da hiç eşleşmez.

    Saf fonksiyon (str → str) → memoize edilebilir. lru_cache aynı ismin
    tekrar tekrar normalize edilmesini keser (bir dava açma oturumunda aynı
    taraflar birden çok kez sorgulanır); maxsize sınırlı, süresiz büyüme yok."""
    if not name:
        return ""
    cleaned = unicodedata.normalize("NFD", name)
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    cleaned = turkish_upper(cleaned)
    cleaned = _fold_diacritics(cleaned)
    cleaned = _TITLE_PATTERN.sub(" ", cleaned)
    # Virgül de noktalama sayılır (03.10): vekalet ücreti föylerinden gelen
    # "Atilla Kurtay Dr.," yazımı anahtarda artık "," token'ı bırakmaz.
    cleaned = re.sub(r"[;:.,]+", " ", cleaned)
    return " ".join(cleaned.split())


_CORP_PAIR_MAP = {
    ("ANONIM", "SIRKETI"): "AS",
    ("A", "S"): "AS",  # "A.Ş." normalize sonrası iki tek harfli token
    ("LIMITED", "SIRKETI"): "LTD",
    ("LTD", "STI"): "LTD",
}
_CORP_TOKEN_MAP = {"TIC": "TICARET", "SAN": "SANAYI", "LIMITED": "LTD", "STI": "LTD"}


def normalize_party_key(name: str) -> str:
    """Taraf BİRLEŞTİRME anahtarı: normalize_person_name + şirket eki eşitleme.

    "X A.Ş." ↔ "X Anonim Şirketi" aynı anahtara düşer; kelime sırası önemsiz
    (_match_name'in sorted-exact semantiğiyle uyumlu). Yalnız dedup anahtarıdır,
    görüntülenecek ad değildir.
    """
    norm = normalize_person_name(name)
    tokens = norm.split()
    out = []
    i = 0
    while i < len(tokens):
        pair = tuple(tokens[i:i + 2])
        if pair in _CORP_PAIR_MAP:
            out.append(_CORP_PAIR_MAP[pair])
            i += 2
            continue
        out.append(_CORP_TOKEN_MAP.get(tokens[i], tokens[i]))
        i += 1
    # Kurum adında "VE" bağlacı anahtara girmez: şirketlerde baştan beri; hastane,
    # üniversite, bakanlık için 03.10'dan beri ("Eğitim ve Araştırma Hastanesi" ↔
    # "Eğitim Araştırma Hastanesi" aynı kurumdur).
    if _is_corporate(norm) or set(tokens) & KURUM_SOZCUKLERI:
        out = [t for t in out if t != "VE"]
    return " ".join(sorted(out))


# ─── Taraf tekilliği (03.10.2026 kullanıcı kararı) ───────────────────────────
#
# Bir kartta aynı kişi TEK satırdır. "3. şahıs" eski TKU mantığından kalan bir
# kavram: müvekkil ya da karşı taraf olan kişi ayrıca 3. şahıs olarak da
# görünüyorsa 3. şahıs satırı hatalıdır → öncelik CLIENT > COUNTER > THIRD.
# Tek tanım burada; kart birleştirme (`scripts/mukerrer_kart_birlestir`), temizlik
# (`scripts/taraf_tekillestir`) ve kart açma (`case_manager.add_case`) bunu okur.
TARAF_TUR_ONCELIGI = {"CLIENT": 0, "COUNTER": 1, "THIRD": 2}


def taraf_tur_sirasi(party_type: str | None) -> int:
    """Küçük = öncelikli. Tanınmayan tür en sona düşer."""
    return TARAF_TUR_ONCELIGI.get(party_type or "", len(TARAF_TUR_ONCELIGI))


# Kurum adlarında geçen sözcükler. `_is_corporate` YETMEZ: o yalnız ticari şirketi
# tanır (SİGORTA/A.Ş./LTD); hastane, üniversite ve bakanlık ondan geçer.
KURUM_SOZCUKLERI = frozenset({
    "HASTANE", "HASTANESI", "UNIVERSITE", "UNIVERSITESI", "FAKULTE", "FAKULTESI",
    "BAKANLIGI", "BAKANLIK", "MUDURLUGU", "BELEDIYE", "BELEDIYESI", "KURUMU",
    "MERKEZI", "VAKIF", "VAKFI", "DERNEGI", "POLIKLINIK", "POLIKLINIGI",
    "VALILIGI", "REKTORLUGU", "ARASTIRMA",
})


def kurum_mu(ad: str) -> bool:
    """Ad bir şirket/kurum mu (kişi değil)? Normalize ad üzerinden sözcük bazlı."""
    norm = normalize_person_name(ad or "")
    return _is_corporate(norm) or bool(set(norm.split()) & KURUM_SOZCUKLERI)


_AD_AYRACI = re.compile(r"[;\r\n]+")
_SONDAKI_AYRAC = re.compile(r"[\s,;]+$")


def split_party_names(metin: str | None, *, virgul: bool = False) -> list[str]:
    """Tek hücreye/alana yazılmış çok adlı taraf metnini adlara böler.

    * `;` ve satır sonu HER ZAMAN ayraçtır (frontend `splitPartyNames` ile aynı).
    * Sondaki virgül/noktalı virgül atılır ("Atilla Kurtay Dr.," → "Atilla Kurtay Dr.").
    * `virgul=True` (teslim paketi ve temizlik script'i — kullanıcı yollarında KAPALI):
      virgül de ayraç sayılır, ama yalnız parçaların HEPSİ en az iki sözcüklü kişi
      adıysa. Şirket/kurum adı içeren metin bölünmez ("X San., Tic. Ltd. Şti.");
      tek sözcüklü parça da bölmeyi iptal eder ("Yılmaz, Ahmet").
    * Aynı kişi (`normalize_party_key` eşit) listede bir kez kalır; sıra korunur.
    """
    if not metin:
        return []
    adlar: list[str] = []
    gorulen: set[str] = set()

    def _ekle(ham: str) -> None:
        ad = _SONDAKI_AYRAC.sub("", " ".join(ham.split())).strip()
        anahtar = normalize_party_key(ad)
        if ad and anahtar and anahtar not in gorulen:
            gorulen.add(anahtar)
            adlar.append(ad)

    for parca in _AD_AYRACI.split(str(metin)):
        govde = _SONDAKI_AYRAC.sub("", parca)
        alt = [a for a in govde.split(",") if a.strip()] if virgul and "," in govde else []
        if len(alt) > 1 and all(
            len(normalize_person_name(a).split()) >= 2 and not kurum_mu(a) for a in alt
        ):
            for a in alt:
                _ekle(a)
        else:
            _ekle(parca)
    return adlar


def taraf_listesini_tekillestir(parties: list[dict] | None) -> list[dict]:
    """Kart AÇILIRKEN gelen taraf listesini böler ve tekilleştirir (yeni liste döner).

    * Adı `;`/satır sonuyla çok kişi taşıyan öğe kişi başına bir öğeye bölünür; bölünen
      öğenin kişiye özgü alanları (`tc_no`, `birth_year`, `gender`, `client_id`) hangi
      kişiye ait olduğu bilinemediği için BOŞ bırakılır, `hizmet_turleri` her parçaya geçer.
    * Aynı kişi (`normalize_party_key`) iki kez gelirse TEK öğe kalır: türü öncelikli
      olan (`TARAF_TUR_ONCELIGI`); kalanın boş kişi alanları ötekinden dolar, iki
      müvekkil öğesinin `hizmet_turleri` birleşir.
    * Anahtarı boş (adsız) öğeye dokunulmaz.
    """
    kisiye_ozgu = ("tc_no", "birth_year", "gender", "client_id")
    sonuc: list[dict] = []
    konum: dict[str, int] = {}
    for p in parties or []:
        adlar = split_party_names(p.get("name"))
        if len(adlar) > 1:
            parcalar = [{**p, "name": ad, **dict.fromkeys(kisiye_ozgu)} for ad in adlar]
        elif adlar:
            parcalar = [{**p, "name": adlar[0]}]
        else:
            parcalar = [dict(p)]
        for oge in parcalar:
            anahtar = normalize_party_key(oge.get("name") or "")
            if not anahtar or anahtar not in konum:
                if anahtar:
                    konum[anahtar] = len(sonuc)
                sonuc.append(oge)
                continue
            mevcut = sonuc[konum[anahtar]]
            kalan, giden = mevcut, oge
            if taraf_tur_sirasi(oge.get("party_type")) < taraf_tur_sirasi(mevcut.get("party_type")):
                kalan, giden = oge, mevcut
            birlesik = dict(kalan)
            for alan in kisiye_ozgu:
                if birlesik.get(alan) in (None, ""):
                    birlesik[alan] = giden.get(alan)
            if kalan.get("party_type") == giden.get("party_type") == "CLIENT":
                hizmetler = list(kalan.get("hizmet_turleri") or [])
                hizmetler += [h for h in (giden.get("hizmet_turleri") or []) if h not in hizmetler]
                if hizmetler:
                    birlesik["hizmet_turleri"] = hizmetler
            sonuc[konum[anahtar]] = birlesik
    return sonuc


def normalize_tc(tc: str | None) -> str | None:
    """TC'yi 11 haneye normalize eder; geçersizse None (yok sayılır)."""
    if not tc:
        return None
    digits = re.sub(r"\D", "", str(tc))
    return digits if len(digits) == 11 else None




def _levenshtein_within(a: str, b: str, threshold: int) -> bool:
    """`a` ile `b` arasındaki düzenleme mesafesi `threshold`u AŞMIYORSA True.

    TAM MESAFE DÖNDÜRMEZ (sözleşme bilinçli daraltıldı): tek çağrı yeri
    `_match_name_keys` zaten yalnız `> threshold` karşılaştırması yapıyordu,
    mesafenin kendisi hiçbir yerde kullanılmıyor. Eşik-aşımı sorusuna
    indirgeyince iki kısayol serbest kalır ve İKİSİ DE SONUCU DEĞİŞTİRMEZ:

    * **Bant:** mesafe indis farkının altına inemez → `|i-j| > threshold`
      hücrelerinin gerçek değeri zaten eşiği aşar; hesaplanmaz, `threshold+1`
      sayılır. Satır başına en fazla `2*threshold+1` hücre işlenir (eşik 1 ya
      da 2 olduğu için 3-5 hücre), tüm satır değil.
    * **Erken çıkış:** DP'de satır minimumu azalamaz (her hücre bir önceki
      satır/sütun hücrelerinin minimumundan küçük olamaz) → bir satırın
      tamamı eşiği aşmışsa sonuç da aşar; kalan satırlar hiç kurulmaz.

    Değerler `threshold+1`de doyurulur. Doyurma özyinelemeyle değişmelidir
    (min/+1 monoton) → eşiğin ALTINDA kalan hücreler birebir doğru hesaplanır,
    yalnız "zaten elenmiş" hücreler tek bir üst değere toplanır.
    """
    m, n = len(a), len(b)
    if a == b:
        return True
    if abs(m - n) > threshold:
        return False
    if m == 0 or n == 0:
        # Diğeri boş: mesafe = dolu dizenin uzunluğu (üstteki fark kapısı geçti)
        return max(m, n) <= threshold

    if threshold == 1 and m == n:
        # EŞİT UZUNLUK + EŞİK 1 → matris hiç kurulmaz. Ekleme/silme uzunluğu
        # değiştirir; eşit uzunlukta 1 düzenleme yalnız DEĞİŞTİRME olabilir →
        # "mesafe ≤ 1" ile "en fazla bir konumda harf farkı" DENKTİR. Kelime
        # eşiği ≤7 harfte 1 olduğu için çağrıların çoğu buradan döner.
        seen_diff = False
        for x, y in zip(a, b, strict=True):  # m == n (üstteki kapı)
            if x != y:
                if seen_diff:
                    return False
                seen_diff = True
        return True

    cap = threshold + 1  # "eşiği aştı" için tek temsilci değer
    prev = [j if j <= threshold else cap for j in range(n + 1)]
    for i in range(1, m + 1):
        lo = max(1, i - threshold)
        hi = min(n, i + threshold)
        curr = [cap] * (n + 1)
        curr[0] = i if i <= threshold else cap
        row_min = curr[0]
        ai = a[i - 1]
        for j in range(lo, hi + 1):
            cost = 0 if ai == b[j - 1] else 1
            val = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            if val > threshold:
                val = cap
            elif val < row_min:
                row_min = val
            curr[j] = val
        if row_min > threshold:
            return False
        prev = curr
    return prev[n] <= threshold


def _token_threshold(length: int) -> int:
    """Kelime başına yazım hatası toleransı: kısa kelimede 1, uzun kelimede 2."""
    return 1 if length <= 7 else 2


def _is_corporate(normalized_name: str) -> bool:
    tokens = set(normalized_name.split())
    if tokens & _CORPORATE_WORDS:
        return True
    # "A.Ş." normalize sonrası "A S" olur → iki tek harfli token birlikte
    return "A" in tokens and "S" in tokens


def _name_key(normalized_name: str) -> tuple:
    """Eşleştirmenin satır başına yeniden hesapladığı türevleri bir kez üretir:
    `(norm, kelimeler, sıralı-kelime anahtarı, kurumsal mı)`.

    Sıralı anahtar dize olarak tutulur; kelimeler split()'ten geldiği için
    boşluk içermez → `" ".join(sorted(a)) == " ".join(sorted(b))` ile
    `sorted(a) == sorted(b)` denktir (davranış korunur, karşılaştırma ucuzlar).
    """
    tokens = tuple(normalized_name.split())
    return (normalized_name, tokens, " ".join(sorted(tokens)), _is_corporate(normalized_name))


def _match_name_keys(q_key: tuple, c_key: tuple) -> str | None:
    """`_match_name`in hazırlanmış anahtarlar üzerinde çalışan biçimi."""
    query_norm, q_tokens, q_sorted, q_corp = q_key
    candidate_norm, c_tokens, c_sorted, c_corp = c_key

    if not query_norm or not candidate_norm:
        return None
    if query_norm == candidate_norm:
        return "name_exact"
    if len(query_norm) < _FUZZY_MIN_LEN:
        return None

    # Kelime sırası farklı ama küme aynı ("SOYSAL AHMET" ↔ "AHMET SOYSAL") → exact
    if len(q_tokens) > 1 and q_sorted == c_sorted:
        return "name_exact"

    if q_corp or c_corp:
        return None
    if len(q_tokens) != len(c_tokens):
        return None

    used_fuzzy = False
    for qt, ct in zip(q_tokens, c_tokens, strict=True):
        if qt == ct:
            continue
        threshold = _token_threshold(len(qt))
        # Çok kısa kelimede toleranslı eşleşme güvenilmez. Uzunluk farkı
        # düzenleme mesafesinin ALT sınırıdır → eşiği aşıyorsa Levenshtein'ı
        # hiç kurmadan eleriz (aynı sonuç, ölçülen maliyetin büyük kısmı gider;
        # kapı `_levenshtein_within` içinde de var — burada çağrıyı bile kesiyor).
        if (
            len(qt) < 3
            or abs(len(qt) - len(ct)) > threshold
            or not _levenshtein_within(qt, ct, threshold)
        ):
            return None
        used_fuzzy = True
    return "name_fuzzy" if used_fuzzy else "name_exact"


def _match_name(query_norm: str, candidate_norm: str) -> str | None:
    """None | "name_exact" | "name_fuzzy"

    Kelime bazlı: kelime sayısı eşit olmalı ve her kelime karşılığıyla ayrı
    ayrı eşleşmeli. Böylece "ALI VELI" ↔ "ALI BEKI" eşleşmez (ilk isim aynı
    diye soyisim farkı tolere edilmez), ama "AHMET YILMAS" ↔ "AHMET YILMAZ"
    (soyisimde 1 harflik yazım hatası) yakalanır.

    Ucuz erken çıkışlar burada kalır: anahtar kurmaya yalnız gerçekten kelime
    karşılaştırması gerekince girilir (`services/case_intake.py` bu yolu satır
    başına çağırıyor).
    """
    if not query_norm or not candidate_norm:
        return None
    if query_norm == candidate_norm:
        return "name_exact"
    if len(query_norm) < _FUZZY_MIN_LEN:
        return None
    return _match_name_keys(_name_key(query_norm), _name_key(candidate_norm))


_STRENGTH = {"tc_no": "certain", "name_exact": "probable", "name_fuzzy": "possible"}

_UNSET = object()


def prepare_candidate_rows(rows: list[dict]) -> list[dict]:
    """Aday satırlarını karşılaştırmaya hazırlar (yeni liste döner, girdi bozulmaz).

    Her satıra `_key` (bkz. `_name_key`) ve `_tc` (normalize TC) iliştirilir.
    Aynı isim onlarca dosyada tekrar ettiği için anahtar İSİM BAŞINA bir kez
    üretilip paylaşılır; dize alanları da yerel havuzda tekilleştirilir —
    satırlar cache'te KALICI olduğundan (route TTL cache'i) tekrar eden
    "DERDEST"/"Davalı"/aynı ad kopyaları bellekte tek nesneye iner.

    Hazırlık davranışı değiştirmez: check_parties bu alanlar yoksa aynı işi
    satır başına yapar (`_row_key`/`_row_tc`).
    """
    text_pool: dict[str, str] = {}
    key_pool: dict[str, tuple] = {}
    prepared: list[dict] = []
    for row in rows:
        item = {}
        for field, value in row.items():
            item[field] = text_pool.setdefault(value, value) if isinstance(value, str) else value
        name = item.get("name") or ""
        key = key_pool.get(name)
        if key is None:
            key = key_pool[name] = _name_key(normalize_person_name(name))
        item["_key"] = key
        item["_tc"] = normalize_tc(item.get("tc_no"))
        prepared.append(item)
    return prepared


def _row_key(row: dict) -> tuple:
    """Satırın ad anahtarı — hazırlanmışsa cache'ten, değilse anında."""
    key = row.get("_key")
    if key is None:
        return _name_key(normalize_person_name(row.get("name") or ""))
    return key


def _row_tc(row: dict) -> str | None:
    """Satırın normalize TC'si — hazırlanmışsa cache'ten, değilse anında.
    (`None` geçerli bir değer olduğu için varlık kontrolü sentinel ile.)"""
    tc = row.get("_tc", _UNSET)
    if tc is _UNSET:
        return normalize_tc(row.get("tc_no"))
    return tc


def check_parties(queries, client_rows, party_rows, exclude_case_id=None):
    """
    queries:     [{name, tc_no?, party_type?}]
    client_rows: [{id, name, tc_no, cari_kod, category, contact_type}]
    party_rows:  [{id, name, tc_no, role, party_type, client_id,
                   case_id, tracking_no, case_subject, case_status}]
    → [{query, conflict, matches}]  (schemas.PartyCheckResult şekli)

    Aday satırları `prepare_candidate_rows`ten geçmişse `_key`/`_tc` alanları
    kullanılır (hazırlanmamış satırlarla sonuç aynı, yalnız daha yavaş).
    """
    results = []
    for q in queries:
        q_name = (q.get("name") or "").strip()
        q_norm = normalize_person_name(q_name)
        q_key = _name_key(q_norm)
        q_tc = normalize_tc(q.get("tc_no"))
        q_type = q.get("party_type") or ""

        matches = []
        conflict = False
        matched_client_ids = set()

        if len(q_norm) < _NAME_MIN_LEN and not q_tc:
            results.append({"query": q, "conflict": False, "matches": []})
            continue

        # ── Cari kayıtları ──────────────────────────────────────────────
        for c in client_rows:
            c_tc = _row_tc(c)
            c_key = _row_key(c)
            c_norm = c_key[0]

            matched_on = None
            if q_tc and c_tc and q_tc == c_tc:
                matched_on = "tc_no"
            else:
                matched_on = _match_name_keys(q_key, c_key)

            if not matched_on:
                continue

            is_client_query = q_type == "CLIENT"
            matched_client_ids.add(c["id"])
            # CLIENT sorgusunun beklenen cari eşleşmesini bastır (combobox
            # zaten garanti ediyor). İstisna: TC eşleşip isim farklıysa
            # raporla — aynı TC farklı isim = veri hatası.
            if is_client_query and (matched_on != "tc_no" or q_norm == c_norm):
                continue

            if not is_client_query and (c.get("contact_type") or "Client") == "Client":
                conflict = True

            matches.append({
                "source": "client",
                "strength": _STRENGTH[matched_on],
                "matched_on": matched_on,
                "name": c.get("name") or "",
                "client_id": c["id"],
                "cari_kod": c.get("cari_kod"),
                "category": c.get("category"),
                "contact_type": c.get("contact_type"),
                # Eşleşen kaydın TC'si ekranda gösterilir (kullanıcı talebi;
                # endpoint auth korumalı, cari seçiminde de TC zaten açık)
                "tc_no": c.get("tc_no"),
                # Dedupe anahtarı için taşınan geçici alan — aşağıda pop'lanır,
                # yanıta çıkmaz (adı yeniden normalize etmemek için).
                "_norm": c_norm,
            })

        # ── Geçmiş dosya tarafları ──────────────────────────────────────
        for p in party_rows:
            if exclude_case_id and p.get("case_id") == exclude_case_id:
                continue

            p_tc = _row_tc(p)
            p_key = _row_key(p)
            p_norm = p_key[0]

            matched_on = None
            if q_tc and p_tc and q_tc == p_tc:
                matched_on = "tc_no"
            else:
                matched_on = _match_name_keys(q_key, p_key)

            if not matched_on:
                continue

            p_type = p.get("party_type") or ""
            # CLIENT sorgusunun geçmiş CLIENT görünümleri beklenen durum —
            # yalnızca COUNTER/THIRD geçmişi ilginç. Taraf-değişimi geçmişi
            # bilgi olarak listelenir, çatışma SAYILMAZ (müvekkil ile çıkar
            # çatışması olmaz; çatışma yalnız karşı tarafın kayıtlı müvekkil
            # çıkmasıdır — cari döngüsündeki koşul).
            if q_type == "CLIENT" and p_type == "CLIENT" and matched_on != "tc_no":
                continue

            matches.append({
                "source": "case_party",
                "strength": _STRENGTH[matched_on],
                "matched_on": matched_on,
                "name": p.get("name") or "",
                "client_id": p.get("client_id"),
                "case_id": p.get("case_id"),
                "tracking_no": p.get("tracking_no"),
                "case_subject": p.get("case_subject"),
                "case_status": p.get("case_status"),
                "role": p.get("role"),
                "party_type": p_type,
                "tc_no": p.get("tc_no"),
                "_norm": p_norm,  # geçici — dedupe anahtarı, aşağıda pop'lanır
            })

        # ── TC verilmiş ve TC'li kayıtla isim eşleşti ama TC eşleşmedi →
        # "aynı isim, farklı kişi": bu eşleşmeleri düşür (yanlış alarm temizliği)
        if q_tc:
            cleaned = []
            for m in matches:
                if m["matched_on"] == "tc_no":
                    cleaned.append(m)
                    continue
                # Eşleşen kaydın TC'si biliniyor ve sorgu TC'sinden farklıysa ele
                row_tc = None
                if m["source"] == "client":
                    row = next((c for c in client_rows if c["id"] == m["client_id"]), None)
                    row_tc = _row_tc(row) if row else None
                else:
                    row = next((p for p in party_rows if p.get("case_id") == m["case_id"]
                                and (p.get("name") or "") == m["name"]), None)
                    row_tc = _row_tc(row) if row else None
                if row_tc and row_tc != q_tc:
                    continue
                cleaned.append(m)
            matches = cleaned
            conflict = any(
                m["source"] == "client" and q_type != "CLIENT"
                and (m.get("contact_type") or "Client") == "Client"
                for m in cleaned
            )

        # ── Dedupe: cari olarak zaten eşleşen kişinin case_party satırları
        # tekrar cari bilgisi taşımasın (tek kayıt görünümü) ──
        seen = set()
        deduped = []
        for m in matches:
            m_norm = m.pop("_norm")  # geçici alan burada tükenir → yanıt şekli aynı
            if m["source"] == "case_party" and m.get("client_id") in matched_client_ids:
                key = ("cp", m.get("case_id"), m_norm)
            elif m["source"] == "client":
                key = ("cl", m.get("client_id"))
            else:
                key = ("cp", m.get("case_id"), m_norm, m.get("role"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(m)

        results.append({"query": q, "conflict": conflict, "matches": deduped})

    return results
