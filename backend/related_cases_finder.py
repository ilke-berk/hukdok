"""
related_cases_finder.py
-----------------------
Verilen bir dava için algoritmik olarak ilişkili olası davaları tespit eder.
Veritabanına yazmaz, sadece okur.

Temel kural: "Aynı müvekkil + aynı karşı taraf, farklı dava türü"
→ Aynı hukuki uyuşmazlığın farklı ayaklarını bulur.
→ Sadece müvekkil eşleşmesi yeterli değil (müvekkilin tüm davaları gelir, bu yanlış).
"""
from __future__ import annotations
import logging
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _normalize(name: str) -> str:
    import re
    name = name.upper().strip()
    name = re.sub(r"[^\w\s]", "", name, flags=re.UNICODE)
    name = re.sub(r"\s+", " ", name)
    return name


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_automatic_relations(case_id: int, db: "Session") -> list[dict]:
    """
    Dönüş: [{"case": <Case ORM nesnesi>, "reason": str, "score": int}]

    Strateji:
    1. Aynı müvekkil (client_id) + aynı karşı taraf adı → güçlü eşleşme
       (aynı uyuşmazlığın Ceza/Hukuk/İcra ayakları)
    2. Aynı mahkeme + aynı yıl esas no → zayıf, ek bilgi
    """
    import models

    target = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not target:
        return []

    found: dict[int, dict] = {}

    # Hedef davanın taraflarını ayır
    target_client_ids = {
        p.client_id for p in target.parties
        if p.party_type == "CLIENT" and p.client_id is not None
    }
    target_counter_names = [
        _normalize(p.name) for p in target.parties
        if p.party_type in ("COUNTER", "THIRD")
    ]

    # ── 1. Aynı müvekkil + aynı karşı taraf ─────────────────────────────────
    # Önce aynı müvekkile sahip aday davaları bul
    if target_client_ids and target_counter_names:
        same_client_rows = (
            db.query(models.CaseParty)
            .filter(
                models.CaseParty.client_id.in_(target_client_ids),
                models.CaseParty.case_id != case_id,
            )
            .all()
        )
        candidate_case_ids = {r.case_id for r in same_client_rows}

        # Aday davalar içinde karşı taraf adı eşleşenlerini seç
        for cid in candidate_case_ids:
            candidate = db.query(models.Case).filter(models.Case.id == cid).first()
            if not candidate:
                continue

            counter_parties = [
                p for p in candidate.parties
                if p.party_type in ("COUNTER", "THIRD")
            ]
            if not counter_parties:
                continue

            best_sim = 0.0
            best_name = ""
            for cp in counter_parties:
                norm = _normalize(cp.name)
                for tname in target_counter_names:
                    sim = _similarity(norm, tname)
                    if sim > best_sim:
                        best_sim = sim
                        best_name = cp.name

            # Eşik: %80 — "AXA SİGORTA A.Ş." gibi kısa isimlerde toleranslı ol
            if best_sim >= 0.80:
                score = min(95, int(best_sim * 100) + 5)
                found[cid] = {
                    "case": candidate,
                    "reason": f"Aynı taraflar, farklı dava türü — Karşı taraf: {best_name}",
                    "score": score,
                }

    # ── 2. Aynı mahkeme + aynı yıl (zayıf sinyal, ek bilgi) ────────────────
    if target.court and target.esas_no and "/" in target.esas_no:
        target_year = target.esas_no.split("/")[0]
        same_court = (
            db.query(models.Case)
            .filter(
                models.Case.court == target.court,
                models.Case.esas_no.ilike(f"{target_year}/%"),
                models.Case.id != case_id,
            )
            .limit(3)
            .all()
        )
        for c in same_court:
            if c.id not in found:
                found[c.id] = {
                    "case": c,
                    "reason": f"Aynı mahkeme, aynı yıl: {target.court}",
                    "score": 50,
                }

    return list(found.values())
