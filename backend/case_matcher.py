"""
case_matcher.py — Otomatik Dava Eşleştirme Motoru (Faz 1)

Belge analizinden çıkan bilgileri (esas_no, muvekkiller, avukat_kodu)
kullanarak veritabanındaki davalarla eşleştirir ve bir güven skoru üretir.

Güven Skoru:
  esas_no tam eşleşmesi      → +60 puan (en güvenilir sinyal)
  esas_no kısmi eşleşmesi   → +30 puan
  müvekkil adı eşleşmesi    → +25 puan (her biri, max +50)
  avukat kodu eşleşmesi     → +15 puan

Karar eşiği:
  ≥ 80 puan → Otomatik öneri (güven: HIGH)
  50-79     → Öneri, kullanıcı onayı beklenir (güven: MEDIUM)
  < 50      → Bulunamadı / Manuel seçim gerekli

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
    "2024/1234" tam eşleşme → 60
    "2024/1234" ↔ "2024/001234" (sıfır dolgu farkı) → 60
    Sadece yıl veya sadece numara eşleşmesi → 15
    Hiç eşleşme → 0
    """
    if not doc_esas or not case_esas:
        return 0

    d = _normalize(doc_esas).replace(" ", "")
    c = _normalize(case_esas).replace(" ", "")

    # Tam eşleşme
    if d == c:
        return 60

    # Normalize: bölü veya tire ile parçala
    import re
    d_parts = re.split(r"[/\-]", d)
    c_parts = re.split(r"[/\-]", c)

    if len(d_parts) >= 2 and len(c_parts) >= 2:
        d_year = d_parts[0].lstrip("0") or "0"
        d_num = d_parts[1].lstrip("0") or "0"
        c_year = c_parts[0].lstrip("0") or "0"
        c_num = c_parts[1].lstrip("0") or "0"

        if d_year == c_year and d_num == c_num:
            return 60  # Sıfır dolgu farkı — aynı dava

        if d_year == c_year:
            return 20  # Aynı yıl, farklı numara

        if d_num == c_num:
            return 15  # Aynı numara, farklı yıl (çok nadir ama mümkün)

    # Substring kontrolü (bir kısım diğerini içeriyorsa)
    if d in c or c in d:
        return 25

    return 0


def find_matching_case(
    esas_no: Optional[str] = None,
    muvekkiller: Optional[list] = None,
    avukat_kodu: Optional[str] = None,
    belgede_gecen_isimler: Optional[list] = None,
    min_score: int = 40,
) -> Optional[dict]:
    """
    Analiz çıktısını kullanarak DB'deki davalar arasında en iyi eşleşmeyi bulur.

    Args:
        esas_no: Belgeden çıkarılan esas numarası
        muvekkiller: Belgeden çıkarılan müvekkil adları listesi
        avukat_kodu: Belgeden çıkarılan avukat kodu
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
            # all_names_in_doc contains (original_name, normalized_name) would be better
            # For now, let's just use doc_names_norm and try to map back or just return the normalized matched ones
            
            # Revised matching loop to track doc names
            for doc_name_orig in all_names_in_doc:
                if not doc_name_orig or len(doc_name_orig) < 4:
                    continue
                doc_name_norm = _normalize(doc_name_orig)
                
                for cp_norm, cp_orig in case_parties_norm:
                    if cp_norm in matched_parties:
                        continue
                    
                    if doc_name_norm == cp_norm:
                        score += 50
                        match_count += 1
                        reasons.append(f"İsim tam eşleşme ({cp_orig}): +50")
                        matched_parties.add(cp_norm)
                        matched_doc_names.add(doc_name_orig)
                        break
                    elif doc_name_norm in cp_norm or cp_norm in doc_name_norm:
                        if len(doc_name_norm) >= 6 and len(cp_norm) >= 6:
                            score += 20
                            match_count += 0.4
                            reasons.append(f"İsim kısmi eşleşme ({doc_name_orig} ↔ {cp_orig}): +20")
                            matched_parties.add(cp_norm)
                            matched_doc_names.add(doc_name_orig)
                            break

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

        if best["score"] >= 90 or best.get("match_count", 0) >= 1.8:
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

