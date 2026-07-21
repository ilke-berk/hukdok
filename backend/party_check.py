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

conflict=True koşulları:
  a) CLIENT olmayan sorgu, contact_type="Client" bir cari kaydıyla eşleşirse
     (karşı taraf ofisin müvekkili → çıkar çatışması riski)
  b) CLIENT sorgusu geçmiş bir dosyada COUNTER/THIRD taraf olarak geçmişse
  c) TC eşleşip isim eşleşmiyorsa (aynı TC farklı isim → veri hatası / kesin kişi)
"""

import re
import unicodedata

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


def normalize_person_name(name: str) -> str:
    """Karşılaştırma anahtarı üretir: birleşik işaret temizliği → Türkçe upper
    → diakritik katlama → unvan temizliği → boşluk sadeleştirme.

    NFD + combining-strip önemli: bazı kayıtlarda 'i̇' (i + U+0307 birleşik
    nokta) gibi görünmez karakterler var; bunlar temizlenmezse birebir aynı
    isim exact yerine fuzzy'ye düşer ya da hiç eşleşmez."""
    if not name:
        return ""
    cleaned = unicodedata.normalize("NFD", name)
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    cleaned = turkish_upper(cleaned)
    cleaned = _fold_diacritics(cleaned)
    cleaned = _TITLE_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"[;:.]+", " ", cleaned)
    return " ".join(cleaned.split())


def normalize_tc(tc: str | None) -> str | None:
    """TC'yi 11 haneye normalize eder; geçersizse None (yok sayılır)."""
    if not tc:
        return None
    digits = re.sub(r"\D", "", str(tc))
    return digits if len(digits) == 11 else None




def _levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i]
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[n]


def _token_threshold(length: int) -> int:
    """Kelime başına yazım hatası toleransı: kısa kelimede 1, uzun kelimede 2."""
    return 1 if length <= 7 else 2


def _is_corporate(normalized_name: str) -> bool:
    tokens = set(normalized_name.split())
    if tokens & _CORPORATE_WORDS:
        return True
    # "A.Ş." normalize sonrası "A S" olur → iki tek harfli token birlikte
    return "A" in tokens and "S" in tokens


def _match_name(query_norm: str, candidate_norm: str) -> str | None:
    """None | "name_exact" | "name_fuzzy"

    Kelime bazlı: kelime sayısı eşit olmalı ve her kelime karşılığıyla ayrı
    ayrı eşleşmeli. Böylece "ALI VELI" ↔ "ALI BEKI" eşleşmez (ilk isim aynı
    diye soyisim farkı tolere edilmez), ama "AHMET YILMAS" ↔ "AHMET YILMAZ"
    (soyisimde 1 harflik yazım hatası) yakalanır.
    """
    if not query_norm or not candidate_norm:
        return None
    if query_norm == candidate_norm:
        return "name_exact"
    if len(query_norm) < _FUZZY_MIN_LEN:
        return None

    q_tokens = query_norm.split()
    c_tokens = candidate_norm.split()

    # Kelime sırası farklı ama küme aynı ("SOYSAL AHMET" ↔ "AHMET SOYSAL") → exact
    if len(q_tokens) > 1 and sorted(q_tokens) == sorted(c_tokens):
        return "name_exact"

    if _is_corporate(query_norm) or _is_corporate(candidate_norm):
        return None
    if len(q_tokens) != len(c_tokens):
        return None

    used_fuzzy = False
    for qt, ct in zip(q_tokens, c_tokens):
        if qt == ct:
            continue
        # Çok kısa kelimede toleranslı eşleşme güvenilmez
        if len(qt) < 3 or _levenshtein(qt, ct) > _token_threshold(len(qt)):
            return None
        used_fuzzy = True
    return "name_fuzzy" if used_fuzzy else "name_exact"


_STRENGTH = {"tc_no": "certain", "name_exact": "probable", "name_fuzzy": "possible"}


def check_parties(queries, client_rows, party_rows, exclude_case_id=None):
    """
    queries:     [{name, tc_no?, party_type?}]
    client_rows: [{id, name, tc_no, cari_kod, category, contact_type}]
    party_rows:  [{id, name, tc_no, role, party_type, client_id,
                   case_id, tracking_no, case_subject, case_status}]
    → [{query, conflict, matches}]  (schemas.PartyCheckResult şekli)
    """
    results = []
    for q in queries:
        q_name = (q.get("name") or "").strip()
        q_norm = normalize_person_name(q_name)
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
            c_tc = normalize_tc(c.get("tc_no"))
            c_norm = normalize_person_name(c.get("name") or "")

            matched_on = None
            if q_tc and c_tc and q_tc == c_tc:
                matched_on = "tc_no"
            else:
                matched_on = _match_name(q_norm, c_norm)

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
            })

        # ── Geçmiş dosya tarafları ──────────────────────────────────────
        for p in party_rows:
            if exclude_case_id and p.get("case_id") == exclude_case_id:
                continue

            p_tc = normalize_tc(p.get("tc_no"))
            p_norm = normalize_person_name(p.get("name") or "")

            matched_on = None
            if q_tc and p_tc and q_tc == p_tc:
                matched_on = "tc_no"
            else:
                matched_on = _match_name(q_norm, p_norm)

            if not matched_on:
                continue

            p_type = p.get("party_type") or ""
            # CLIENT sorgusunun geçmiş CLIENT görünümleri beklenen durum —
            # yalnızca COUNTER/THIRD geçmişi ilginç (taraf değişimi = çatışma).
            if q_type == "CLIENT" and p_type == "CLIENT" and matched_on != "tc_no":
                continue
            if q_type == "CLIENT" and p_type in ("COUNTER", "THIRD"):
                conflict = True

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
                    row_tc = normalize_tc(row.get("tc_no")) if row else None
                else:
                    row = next((p for p in party_rows if p.get("case_id") == m["case_id"]
                                and (p.get("name") or "") == m["name"]), None)
                    row_tc = normalize_tc(row.get("tc_no")) if row else None
                if row_tc and row_tc != q_tc:
                    continue
                cleaned.append(m)
            matches = cleaned
            conflict = any(
                (m["source"] == "client" and q_type != "CLIENT"
                 and (m.get("contact_type") or "Client") == "Client")
                or (m["source"] == "case_party" and q_type == "CLIENT"
                    and m.get("party_type") in ("COUNTER", "THIRD"))
                for m in cleaned
            )

        # ── Dedupe: cari olarak zaten eşleşen kişinin case_party satırları
        # tekrar cari bilgisi taşımasın (tek kayıt görünümü) ──
        seen = set()
        deduped = []
        for m in matches:
            if m["source"] == "case_party" and m.get("client_id") in matched_client_ids:
                key = ("cp", m.get("case_id"), normalize_person_name(m["name"]))
            elif m["source"] == "client":
                key = ("cl", m.get("client_id"))
            else:
                key = ("cp", m.get("case_id"), normalize_person_name(m["name"]), m.get("role"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(m)

        results.append({"query": q, "conflict": conflict, "matches": deduped})

    return results
