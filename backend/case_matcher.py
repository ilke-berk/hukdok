"""
case_matcher.py — Otomatik Dava Eşleştirme Motoru (Faz 1)

Belge analizinden çıkan bilgileri (esas_no, muvekkiller, mahkeme)
kullanarak veritabanındaki davalarla eşleştirir ve bir güven skoru üretir.

Güven Skoru:
  mahkeme tam eşleşmesi     → +50 puan  ┐ ikisi birden eşleşirse kesin (100 puan → HIGH)
  esas_no tam eşleşmesi     → +50 puan  ┘
  mahkeme şehir+tür eşleşme → +25 puan
  müvekkil adı tam eşleşme  → +30 puan (her biri)
  müvekkil adı kısmi eşleşme→ +15 puan (her biri)
  karşı taraf adı tam eşleşme → +12 puan (her biri — zayıf sinyal)
  karşı taraf adı kısmi eşleşme→ +6 puan  (her biri — zayıf sinyal)

  Not: Esas no tek başına yeterli değildir — aynı esas no farklı mahkemelerde olabilir.
       Sadece tam esas no eşleşmesi değerlendirilir, kısmi eşleşme yok.

Karar eşiği:
  ≥ 90 puan → Otomatik öneri (güven: HIGH)
  45-89     → Öneri, kullanıcı onayı beklenir (güven: MEDIUM)
  < 45      → Bulunamadı / Manuel seçim gerekli

Sonuç:
  {
    "case_id": int,
    "tracking_no": str,
    "esas_no": str,
    "court": str,
    "responsible_lawyer_name": str,
    "status": str,
    "score": int,
    "confidence": "HIGH" | "MEDIUM" | "LOW",
    "match_reasons": [str],
    "all_candidates": [...]   # birden fazla aday varsa
  }

Veri erişimi (G054) — üç dar sorgu, tam ORM nesnesi YOK:
  1. `_fetch_candidate_parties` — belgedeki adlarla eşleşme İHTİMALİ olan taraf
     satırları (eşleşmeyen taraf zaten puan üretmez).
  2. `_fetch_case_rows` — skorlama için gereken üç kolon (id, esas_no, court);
     aday daraltma SQL'de (taraf eşleşmesi VEYA esas VEYA mahkeme sinyali).
  3. `_fetch_display` — yalnız DÖNEN beş aday için görüntü alanları
     (tracking_no, sorumlu avukat, durum) ve tam taraf listesi.
Skorlama kararı Python'da kalır; SQL yalnız geri-çağırma güvenli ön filtredir.
"""

import logging
import re
from typing import Any, Optional

from sqlalchemy import text as sa_text

logger = logging.getLogger("CaseMatcher")


def _normalize(text: str) -> str:
    """Karşılaştırma için metni düzenler."""
    if not text:
        return ""
    return (
        text.upper()
        .replace("İ", "I")
        .replace("Ğ", "G")
        .replace("Ü", "U")
        .replace("Ş", "S")
        .replace("Ö", "O")
        .replace("Ç", "C")
        .strip()
    )


# ── SQL ön filtresi ──────────────────────────────────────────────────────────
#
# PAZARLIKSIZ KURAL: ön filtre yalnız KESİNLİKLE eşleşemeyecek satırı eleyebilir.
# Şüphede satır listede kalır — kaçırılan eşleşme mükerrer dosya demektir.
#
# `_normalize`ın SQL karşılığı: `btrim(translate(upper(x), 'İĞÜŞÖÇ', 'IGUSOC'))`.
# Bu eşitlik sınırsız değil, BELİRLİ bir alfabede geçerlidir:
#
#   * İzinli aralıklar — U+0020..U+017F (Latin + Türkçe) ve U+0300..U+036F
#     (birleşik işaretler; kayıtlarda "Ali̇" gibi i+U+0307 dizileri gerçekten var).
#   * İstisnalar — aralık içinde oldukları hâlde emüle EDİLEMEYEN dört karakter:
#     U+0085 / U+00A0 (Python `.strip()` kırpar, `btrim` kırpmaz) ile
#     U+00DF 'ß' ve U+0149 'ŉ' (Python `.upper()` iki karaktere açar,
#     Postgres `upper()` açmaz).
#
# Bu alfabenin dışına taşan satır ELENMEZ, koşulsuz listede tutulur
# (`_sql_unmodelled`). Böylece Türkçe upper'ın SQL'de olmaması (DB collation'ı
# en_US.utf8) sessiz eleme üretemez. Eşitlik `tests/test_case_matcher_sql.py`
# ile karakter karakter kilitlidir.
#
# DİKKAT: `_SQL_UNMODELLED_CHARS`in ilk iki karakteri GÖRÜNMEZDİR (U+0085,
# U+00A0). Kod noktaları `tests/test_case_matcher.py` içinde kilitli — kodlama
# kazası ya da düzenleyici "temizliği" sabiti sessizce bozarsa test kırılır.
_SQL_FOLD_FROM = "İĞÜŞÖÇ"
_SQL_FOLD_TO = "IGUSOC"
_SQL_ALPHABET_RE = "[^{}-{}{}-{}]".format(chr(0x20), chr(0x17F), chr(0x300), chr(0x36F))
_SQL_UNMODELLED_CHARS = " ßŉ"


def _sql_fold(col: str, params: dict) -> str:
    """`_normalize(col)`ın SQL karşılığı olan ifadeyi üretir."""
    params["fold_from"] = _SQL_FOLD_FROM
    params["fold_to"] = _SQL_FOLD_TO
    return f"btrim(translate(upper(coalesce({col}, '')), :fold_from, :fold_to))"


def _sql_unmodelled(col: str, params: dict) -> str:
    """Kolonda SQL'de emüle edilemeyen karakter var mı → varsa satır şüphededir."""
    params["alphabet_re"] = _SQL_ALPHABET_RE
    params["unmodelled"] = _SQL_UNMODELLED_CHARS
    return (
        f"(coalesce({col}, '') ~ :alphabet_re"
        f" OR translate(coalesce({col}, ''), :unmodelled, '') <> coalesce({col}, ''))"
    )


def _fetch_candidate_parties(db, doc_names_norm: list[str]) -> dict[int, list[dict]]:
    """Belgedeki adlarla eşleşme İHTİMALİ olan taraf satırları → {case_id: [satır]}.

    Eşleşmeyen taraf skorlamada ne puan üretir ne de `matched_parties`/`break`
    akışını değiştirir (döngü onu atlar) → hiç çekilmemesi sonucu DEĞİŞTİRMEZ,
    yalnız ~50 bin satırı belleğe almayı önler. Satır sırası `case_parties.id`
    üzerinden sabitlenir: aynı adı taşıyan iki taraftan hangisinin puanlandığı
    (`break`) sıraya bağlıdır.

    Filtre `_score_cases`teki eşiklerin aynısını kullanır: tam eşleşme her
    uzunlukta, içerme (kısmi) yalnız iki taraf da ≥6 karakterken puan üretir.
    """
    params: dict[str, Any] = {}
    conds = [_sql_unmodelled("name", params)]
    for i, doc_norm in enumerate(doc_names_norm):
        key = f"n{i}"
        params[key] = doc_norm
        if len(doc_norm) >= 6:
            conds.append(
                f"(cpn = :{key} OR (length(cpn) >= 6"
                f" AND (strpos(cpn, :{key}) > 0 OR strpos(:{key}, cpn) > 0)))"
            )
        else:
            conds.append(f"cpn = :{key}")

    sql = (
        "SELECT case_id, name, role, party_type FROM ("
        f" SELECT id, case_id, name, role, party_type, {_sql_fold('name', params)} AS cpn"
        " FROM case_parties"
        ") t WHERE " + " OR ".join(conds) + " ORDER BY id"
    )

    out: dict[int, list[dict]] = {}
    for case_id, name, role, party_type in db.execute(sa_text(sql), params):
        out.setdefault(case_id, []).append({
            "name": name or "",
            "role": role or "",
            "party_type": party_type or "",
        })
    return out


def _fetch_case_rows(
    db,
    party_case_ids,
    esas_no: Optional[str],
    mahkeme: Optional[str],
    narrow: bool,
) -> list[dict]:
    """Skorlanacak davaların üç kolonu (id, esas_no, court) — aday daraltma SQL'de.

    Puan üretebilecek TEK üç kaynak var: taraf adı, esas no, mahkeme. Bir dava
    bunlardan hiçbiri için sinyal taşımıyorsa skoru 0'dır → `min_score > 0` iken
    aday olamaz. `narrow=False` (min_score ≤ 0) ya da hiç sinyal yoksa daraltma
    yapılmaz; o zaman da yalnız üç kolon çekilir, tam ORM nesnesi değil.

    Esas/mahkeme koşulları bilinçli GENİŞTİR (mahkeme için yalnız şehir kelimesi
    aranır, tür kelimesi Python'a bırakılır): ön filtre geri-çağırma güvenli
    olmalı, kesinlik `_score_cases`in işidir.
    """
    params: dict[str, Any] = {}
    conds: list[str] = []

    pids = list(party_case_ids)
    if pids:
        params["pids"] = pids
        conds.append("id = ANY(CAST(:pids AS integer[]))")

    doc_esas = _normalize(esas_no or "").replace(" ", "")
    if doc_esas:
        sub = [_sql_unmodelled("esas_no", params), "ecn = :esas_d"]
        params["esas_d"] = doc_esas
        doc_parts = re.split(r"[/\-]", doc_esas)
        if len(doc_parts) >= 2:
            # `_esas_no_similarity`nin sıfır dolgu toleransı: yıl ve numara
            # baştaki sıfırlar atıldıktan sonra eşitse eşleşme sayılır.
            params["esas_year"] = doc_parts[0].lstrip("0") or "0"
            params["esas_num"] = doc_parts[1].lstrip("0") or "0"
            sub.append(
                "(coalesce(nullif(ltrim(split_part(replace(ecn, '-', '/'), '/', 1), '0'), ''), '0')"
                " = :esas_year AND"
                " coalesce(nullif(ltrim(split_part(replace(ecn, '-', '/'), '/', 2), '0'), ''), '0')"
                " = :esas_num)"
            )
        conds.append("(" + " OR ".join(sub) + ")")

    doc_court = _normalize(mahkeme or "")
    if doc_court:
        sub = [_sql_unmodelled("court", params), "ccn = :court_d"]
        params["court_d"] = doc_court
        doc_city = doc_court.split()[0] if doc_court.split() else ""
        if len(doc_city) >= 3:
            # `_court_similarity`de şehir = ilk kelime → "ccn, şehirle başlıyor
            # ve hemen ardından boşluk ya da dize sonu geliyor" ile denktir.
            params["city"] = doc_city
            params["city_len"] = len(doc_city)
            sub.append(
                "(left(ccn, :city_len) = :city AND (length(ccn) = :city_len"
                " OR substr(ccn, :city_len + 1, 1) = ' '))"
            )
        conds.append("(" + " OR ".join(sub) + ")")

    if not narrow or not conds:
        sql = "SELECT id, esas_no, court FROM cases WHERE active IS TRUE ORDER BY id"
        params = {}
    else:
        inner = (
            "SELECT id, esas_no, court,"
            " replace(translate(upper(coalesce(esas_no, '')), :fold_from, :fold_to), ' ', '') AS ecn,"
            f" {_sql_fold('court', params)} AS ccn"
            " FROM cases WHERE active IS TRUE"
        )
        sql = (
            f"SELECT id, esas_no, court FROM ({inner}) t"
            " WHERE " + " OR ".join(conds) + " ORDER BY id"
        )

    return [
        {"id": cid, "esas_no": esas or "", "court": court or ""}
        for cid, esas, court in db.execute(sa_text(sql), params)
    ]


def _fetch_display(db, case_ids: list[int]) -> tuple[dict[int, dict], dict[int, list[dict]]]:
    """DÖNEN adayların görüntü alanları + TAM taraf listesi ({id: ...}, {id: [...]}).

    En fazla beş dava için koşar (best + all_candidates) — skorlamaya girmeyen
    kolonlar ve eşleşmeyen taraflar buraya kadar hiç okunmaz.

    BEYAN — `parties` sırası artık TANIMLI. Eski yol `joinedload(Case.parties)`
    ile okuyordu ve `models.py:152`'deki ilişkide `order_by` YOK: sıra Postgres'in
    döndürdüğü fiziksel satır sırasıydı, yani bir sözleşme değil kazaydı (167
    gerçek girdilik eşdeğerlik koşusunda 2 davada id sırasından saptı — örn.
    case 6834'te ctid'si önde olan büyük id'li satır başa geliyordu). `ORDER BY id`
    bunu deterministik kılar. Etkisi `karsi_taraf` alanına kadar uzanır
    (`counter_parties[0]`): iki karşı taraflı davalarda hangisinin gösterileceği
    artık kayıt sırasına bağlıdır, plana değil.
    """
    info: dict[int, dict] = {}
    parties: dict[int, list[dict]] = {}
    if not case_ids:
        return info, parties

    params = {"ids": list(case_ids)}
    rows = db.execute(sa_text(
        "SELECT id, tracking_no, responsible_lawyer_name, status FROM cases"
        " WHERE id = ANY(CAST(:ids AS integer[]))"
    ), params)
    for cid, tracking_no, lawyer, status in rows:
        info[cid] = {
            "tracking_no": tracking_no,
            "responsible_lawyer_name": lawyer or "",
            "status": status or "",
        }

    rows = db.execute(sa_text(
        "SELECT case_id, name, role, party_type FROM case_parties"
        " WHERE case_id = ANY(CAST(:ids AS integer[])) ORDER BY id"
    ), params)
    for cid, name, role, party_type in rows:
        parties.setdefault(cid, []).append({
            "name": name or "",
            "role": role or "",
            "party_type": party_type or "",
        })
    return info, parties


def _esas_no_similarity(doc_esas: str, case_esas: str) -> int:
    """
    İki esas no arasındaki benzerliği puana çevirir.
    Tam eşleşme veya sıfır dolgu farkı → +50
    Diğer tüm durumlar → 0 (kısmi eşleşme yok)
    """
    if not doc_esas or not case_esas:
        return 0

    d = _normalize(doc_esas).replace(" ", "")
    c = _normalize(case_esas).replace(" ", "")

    if d == c:
        return 50

    # Sıfır dolgu farkı: "2024/1234" ↔ "2024/001234"
    d_parts = re.split(r"[/\-]", d)
    c_parts = re.split(r"[/\-]", c)

    if len(d_parts) >= 2 and len(c_parts) >= 2:
        d_year = d_parts[0].lstrip("0") or "0"
        d_num = d_parts[1].lstrip("0") or "0"
        c_year = c_parts[0].lstrip("0") or "0"
        c_num = c_parts[1].lstrip("0") or "0"

        if d_year == c_year and d_num == c_num:
            return 50

    return 0


def _court_similarity(doc_court: str, case_court: str) -> tuple[int, str]:
    """
    İki mahkeme adı arasındaki benzerliği puana çevirir.
    Döner: (puan, açıklama)

    Tam eşleşme (normalize)              → +50
    Şehir + mahkeme türü eşleşmesi      → +25  (numara farklı olsa bile)
    """
    if not doc_court or not case_court:
        return 0, ""

    d = _normalize(doc_court)
    c = _normalize(case_court)

    if d == c:
        return 50, f"Mahkeme tam eşleşme ({case_court}): +50"

    SKIP = {"MAHKEMESI", "MAHKEME", "DAIRESI", "DAIRE", "VE", "NO", "NUMARALI"}
    d_words = {w for w in d.split() if w not in SKIP and len(w) >= 2}
    c_words = {w for w in c.split() if w not in SKIP and len(w) >= 2}

    # Şehir: ilk kelime (en az 3 harf)
    d_city = d.split()[0] if d.split() else ""
    c_city = c.split()[0] if c.split() else ""
    city_match = len(d_city) >= 3 and d_city == c_city

    # Mahkeme türü: "TUKETICI", "HUKUK", "AGIR", "IDARE" gibi ayırt edici kelimeler
    TYPE_KEYWORDS = {
        "TUKETICI", "HUKUK", "AGIR", "CEZA", "IDARE", "IS", "SULH",
        "AILE", "ICRA", "TICARET", "KADASTRO", "BOLGE",
    }
    d_types = d_words & TYPE_KEYWORDS
    c_types = c_words & TYPE_KEYWORDS
    type_match = bool(d_types & c_types)

    if city_match and type_match:
        return 25, f"Mahkeme şehir+tür eşleşmesi ({case_court}): +25"

    return 0, ""


def _score_cases(
    case_rows: list[dict],
    party_map: dict[int, list[dict]],
    all_names_in_doc: list,
    esas_no: Optional[str],
    mahkeme: Optional[str],
    min_score: int,
) -> list[dict]:
    """Aday davaları skorlar (saf fonksiyon — DB'ye dokunmaz).

    Görüntü alanları (`tracking_no`, sorumlu avukat, durum, taraf listeleri)
    burada boş bırakılır; sıralama sonrası yalnız dönen beş aday için
    `_fetch_display` ile doldurulur.
    """
    candidates = []

    for case in case_rows:
        score = 0
        reasons = []
        matched_parties = set()
        matched_doc_names = set()  # Track matched original names from document

        # Party names in this specific case (taraf türü ile birlikte)
        # CLIENT (müvekkil) eşleşmesi güçlü sinyaldir; COUNTER/THIRD (karşı taraf)
        # eşleşmesi zayıftır çünkü aynı sigorta/banka onlarca davada karşı taraf olabilir.
        case_parties_norm = []
        for p in party_map.get(case["id"], ()):
            if p["name"]:
                is_client = (p.get("party_type") or "").upper() == "CLIENT"
                case_parties_norm.append((_normalize(p["name"]), p["name"], is_client))

        match_count = 0

        # Esas no eşleştirmesi
        esas_score = _esas_no_similarity(esas_no, case["esas_no"])
        if esas_score:
            score += esas_score
            reasons.append(f"Esas no tam eşleşme ({case['esas_no']}): +{esas_score}")

        # İsim eşleştirmesi
        for doc_name_orig in all_names_in_doc:
            if not doc_name_orig or len(doc_name_orig) < 4:
                continue
            doc_name_norm = _normalize(doc_name_orig)

            for cp_norm, cp_orig, is_client in case_parties_norm:
                if cp_norm in matched_parties:
                    continue

                # Taraf türüne göre ağırlık: müvekkil tam +30 / kısmi +15,
                # karşı taraf (veya diğer) tam +12 / kısmi +6.
                exact_pts = 30 if is_client else 12
                partial_pts = 15 if is_client else 6
                rol = "Müvekkil" if is_client else "Karşı taraf"

                if doc_name_norm == cp_norm:
                    score += exact_pts
                    match_count += 1 if is_client else 0.5
                    reasons.append(f"{rol} adı tam eşleşme ({cp_orig}): +{exact_pts}")
                    matched_parties.add(cp_norm)
                    matched_doc_names.add(doc_name_orig)
                    break
                elif doc_name_norm in cp_norm or cp_norm in doc_name_norm:
                    if len(doc_name_norm) >= 6 and len(cp_norm) >= 6:
                        score += partial_pts
                        match_count += 0.5 if is_client else 0.25
                        reasons.append(f"{rol} adı kısmi eşleşme ({doc_name_orig} ↔ {cp_orig}): +{partial_pts}")
                        matched_parties.add(cp_norm)
                        matched_doc_names.add(doc_name_orig)
                        break

        # Mahkeme eşleştirmesi
        court_score, court_reason = _court_similarity(mahkeme, case["court"])
        if court_score:
            score += court_score
            reasons.append(court_reason)

        if score >= min_score:
            candidates.append({
                "case_id": case["id"],
                "tracking_no": None,
                "esas_no": case["esas_no"],
                "court": case["court"],
                "responsible_lawyer_name": "",
                "status": "",
                "score": score,
                "match_count": match_count,
                "match_reasons": reasons,
                "matched_doc_names": list(matched_doc_names),  # New field
                "counter_parties": [],
                "client_parties": [],
                "karsi_taraf": "",
                "parties": [],  # Pass full parties for the UI
            })

    return candidates


def _apply_display(db, top_candidates: list[dict]) -> None:
    """Dönen adayların görüntü alanlarını yerinde doldurur (anahtar sırası korunur)."""
    info, parties = _fetch_display(db, [c["case_id"] for c in top_candidates])
    for cand in top_candidates:
        meta = info.get(cand["case_id"], {})
        cand["tracking_no"] = meta.get("tracking_no")
        cand["responsible_lawyer_name"] = meta.get("responsible_lawyer_name", "")
        cand["status"] = meta.get("status", "")

        case_parties = parties.get(cand["case_id"], [])
        counter_parties = [p["name"] for p in case_parties if p["party_type"] == "COUNTER" and p["name"]]
        client_parties = [p["name"] for p in case_parties if p["party_type"] == "CLIENT" and p["name"]]
        cand["counter_parties"] = counter_parties
        cand["client_parties"] = client_parties
        cand["karsi_taraf"] = counter_parties[0] if counter_parties else ""
        cand["parties"] = case_parties


def find_matching_case(
    esas_no: Optional[str] = None,
    muvekkiller: Optional[list] = None,
    belgede_gecen_isimler: Optional[list] = None,
    mahkeme: Optional[str] = None,
    min_score: int = 40,
) -> Optional[dict]:
    """
    Analiz çıktısını kullanarak DB'deki davalar arasında en iyi eşleşmeyi bulur.

    Args:
        esas_no: Belgeden çıkarılan esas numarası
        muvekkiller: Belgeden çıkarılan müvekkil adları listesi
        belgede_gecen_isimler: Belgede geçen diğer isimler
        mahkeme: Belgeden çıkarılan mahkeme adı
        min_score: Bu puanın altındaki eşleşmeler döndürülmez

    Returns:
        En iyi eşleşme dict'i veya None
    """
    try:
        from database import SessionLocal

        # Doc names normalization (all names combined: muvekkiller + other names)
        all_names_in_doc = []
        if muvekkiller:
            all_names_in_doc.extend(muvekkiller)
        if belgede_gecen_isimler:
            all_names_in_doc.extend(belgede_gecen_isimler)

        # Ön filtreye giren adlar: skorlamadaki 4 karakter kapısıyla AYNI eşik
        # (kapı ham ada bakar, karşılaştırma normalize hâle).
        doc_names_norm = sorted({
            _normalize(n) for n in all_names_in_doc if n and len(n) >= 4
        })

        db = SessionLocal()
        try:
            party_map = _fetch_candidate_parties(db, doc_names_norm)
            case_rows = _fetch_case_rows(
                db, party_map.keys(), esas_no, mahkeme, narrow=min_score > 0
            )
            if not case_rows:
                logger.info("CaseMatcher: Ön filtreden aday dava geçmedi.")
                return None

            candidates = _score_cases(
                case_rows, party_map, all_names_in_doc, esas_no, mahkeme, min_score
            )
            if not candidates:
                logger.info(f"CaseMatcher: Eşleşme bulunamadı (min_score={min_score})")
                return None

            candidates.sort(key=lambda x: x["score"], reverse=True)
            # Yanıta yalnız ilk beş aday çıkar → görüntü alanları da yalnız
            # onlar için okunur.
            _apply_display(db, candidates[:5])
        finally:
            db.close()

        # best = candidates[0] ile aynı nesne — all_candidates'a dahil etme!
        # Circular reference → JSON serialize hatası
        best = dict(candidates[0])  # Shallow copy — orijinal nesneyi koru

        if best["score"] >= 90:
            confidence = "HIGH"
        elif best["score"] >= 45:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        best["confidence"] = confidence
        # Diğer adayları ekle (best'in kendisi hariç — circular reference önlemi)
        best["all_candidates"] = [
            {k: v for k, v in c.items()}  # Her aday da shallow copy
            for c in candidates[1:5]       # Index 0 = best, onu atlıyoruz
        ]

        logger.info(
            f"✅ CaseMatcher: En iyi eşleşme = Dava#{best['case_id']} "
            f"({best['esas_no']}) — Skor: {best['score']}, Güven: {confidence}"
        )
        logger.info(f"   Nedenler: {best['match_reasons']}")

        return best

    except Exception as e:
        logger.error(f"❌ CaseMatcher hatası: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None
