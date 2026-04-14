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
"""

import logging
from typing import Optional

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
    import re
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
        import models
        from sqlalchemy.orm import joinedload

        db = SessionLocal()
        try:
            # joinedload: session kapanmadan önce parties eager yükleniyor
            # (Lazy load → DetachedInstanceError riskini ortadan kaldırır)
            all_cases = (
                db.query(models.Case)
                .options(joinedload(models.Case.parties))
                .filter(models.Case.active == True)
                .all()
            )

            # Session kapanmadan önce ihtiyaç duyulacak tüm verileri al
            case_snapshots = []
            for case in all_cases:
                case_snapshots.append({
                    "id": case.id,
                    "tracking_no": case.tracking_no,
                    "esas_no": case.esas_no or "",
                    "court": case.court or "",
                    "responsible_lawyer_name": case.responsible_lawyer_name or "",
                    "status": case.status or "",
                    "parties": [
                        {
                            "name": p.name or "",
                            "role": p.role or "",
                            "party_type": p.party_type or "",
                        }
                        for p in case.parties
                    ],
                })
        finally:
            db.close()

        if not case_snapshots:
            logger.info("CaseMatcher: Veritabanında aktif dava bulunamadı.")
            return None

        candidates = []
        
        # Doc names normalization (all names combined: muvekkiller + other names)
        all_names_in_doc = []
        if muvekkiller:
            all_names_in_doc.extend(muvekkiller)
        if belgede_gecen_isimler:
            all_names_in_doc.extend(belgede_gecen_isimler)
            
        doc_names_norm = list(set(_normalize(n) for n in all_names_in_doc if n and len(n) >= 4))

        for case in case_snapshots:
            score = 0
            reasons = []
            matched_parties = set()
            matched_doc_names = set() # Track matched original names from document
            
            # Party names in this specific case
            case_parties_norm = []
            for p in case["parties"]:
                if p["name"]:
                    case_parties_norm.append((_normalize(p["name"]), p["name"]))

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
                
                for cp_norm, cp_orig in case_parties_norm:
                    if cp_norm in matched_parties:
                        continue
                    
                    if doc_name_norm == cp_norm:
                        score += 30
                        match_count += 1
                        reasons.append(f"İsim tam eşleşme ({cp_orig}): +30")
                        matched_parties.add(cp_norm)
                        matched_doc_names.add(doc_name_orig)
                        break
                    elif doc_name_norm in cp_norm or cp_norm in doc_name_norm:
                        if len(doc_name_norm) >= 6 and len(cp_norm) >= 6:
                            score += 15
                            match_count += 0.5
                            reasons.append(f"İsim kısmi eşleşme ({doc_name_orig} ↔ {cp_orig}): +15")
                            matched_parties.add(cp_norm)
                            matched_doc_names.add(doc_name_orig)
                            break

            # Mahkeme eşleştirmesi
            court_score, court_reason = _court_similarity(mahkeme, case["court"])
            if court_score:
                score += court_score
                reasons.append(court_reason)

            if score >= min_score:
                counter_parties = [p["name"] for p in case["parties"] if p["party_type"] == "COUNTER" and p["name"]]
                client_parties = [p["name"] for p in case["parties"] if p["party_type"] == "CLIENT" and p["name"]]

                candidates.append({
                    "case_id": case["id"],
                    "tracking_no": case["tracking_no"],
                    "esas_no": case["esas_no"],
                    "court": case["court"],
                    "responsible_lawyer_name": case["responsible_lawyer_name"],
                    "status": case["status"],
                    "score": score,
                    "match_count": match_count,
                    "match_reasons": reasons,
                    "matched_doc_names": list(matched_doc_names), # New field
                    "counter_parties": counter_parties,
                    "client_parties": client_parties,
                    "karsi_taraf": counter_parties[0] if counter_parties else "",
                    "parties": case["parties"] # Pass full parties for the UI
                })

        if not candidates:
            logger.info(f"CaseMatcher: Eşleşme bulunamadı (min_score={min_score})")
            return None

        candidates.sort(key=lambda x: x["score"], reverse=True)

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

