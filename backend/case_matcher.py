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

        for case in case_snapshots:
            score = 0
            reasons = []

            # 1. ESAS NO (En güçlü sinyal)
            if esas_no and case["esas_no"]:
                es = _esas_no_similarity(esas_no, case["esas_no"])
                if es > 0:
                    score += es
                    reasons.append(f"Esas No eşleşmesi ({case['esas_no']}): +{es}")

            # 2. MÜVEKKİL ADLARI (Tüm taraflarla karşılaştır — CLIENT + COUNTER + THIRD)
            if muvekkiller:
                all_party_names_norm = [
                    _normalize(p["name"])
                    for p in case["parties"]
                    if p["name"]
                ]
                muvekkil_score = 0
                for muv in muvekkiller:
                    muv_norm = _normalize(muv)
                    if not muv_norm:
                        continue
                    for party_norm in all_party_names_norm:
                        if muv_norm == party_norm:
                            muvekkil_score += 25
                            reasons.append(f"Taraf tam eşleşme ({muv}): +25")
                            break
                        elif muv_norm in party_norm or party_norm in muv_norm:
                            muvekkil_score += 12
                            reasons.append(f"Taraf kısmi eşleşme ({muv}): +12")
                            break
                score += min(muvekkil_score, 50)

            # 3. AVUKAT KODU
            if avukat_kodu:
                lawyer_norm = _normalize(avukat_kodu)
                case_lawyer_norm = _normalize(case["responsible_lawyer_name"])
                if lawyer_norm and (
                    lawyer_norm == case_lawyer_norm
                    or lawyer_norm in case_lawyer_norm
                    or case_lawyer_norm.startswith(lawyer_norm)
                ):
                    score += 15
                    reasons.append(f"Avukat eşleşmesi ({case['responsible_lawyer_name']}): +15")

            if score >= min_score:
                # Karşı taraf adını çıkar (QuickCaseModal için)
                counter_parties = [
                    p["name"] for p in case["parties"]
                    if p["party_type"] == "COUNTER" and p["name"]
                ]
                client_parties = [
                    p["name"] for p in case["parties"]
                    if p["party_type"] == "CLIENT" and p["name"]
                ]

                candidates.append({
                    "case_id": case["id"],
                    "tracking_no": case["tracking_no"],
                    "esas_no": case["esas_no"],
                    "court": case["court"],
                    "responsible_lawyer_name": case["responsible_lawyer_name"],
                    "status": case["status"],
                    "score": score,
                    "match_reasons": reasons,
                    # Taraf bilgileri — QuickCaseModal ve UI için
                    "counter_parties": counter_parties,
                    "client_parties": client_parties,
                    "karsi_taraf": counter_parties[0] if counter_parties else "",
                })

        if not candidates:
            logger.info(f"CaseMatcher: Eşleşme bulunamadı (min_score={min_score})")
            return None

        candidates.sort(key=lambda x: x["score"], reverse=True)

        # best = candidates[0] ile aynı nesne — all_candidates'a dahil etme!
        # Circular reference → JSON serialize hatası
        best = dict(candidates[0])  # Shallow copy — orijinal nesneyi koru

        if best["score"] >= 80:
            confidence = "HIGH"
        elif best["score"] >= 50:
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

