"""Otonom dava açma — merge servisi (Faz 3).

Aynı oturumda analiz edilen N belgenin çıkarımlarını tek dava kartı taslağında
birleştirir. Bu modül SAF fonksiyonlardan oluşur: DB ve Gemini erişimi YOK —
satırlar (client_rows, kayıtlı poliçeler, bilinen mahkeme adları) route
katmanından dict/list olarak gelir, böylece DB'siz conftest ile unit test edilir
(plan: docs/arsiv/otonom-dava-acma-gelistirme-plani-2026-07-24.md, İş Kalemi 1).

Girdi biçimi — /analyze'in terminal olayındaki data, frontend'den geri gelir:
    documents = [{"process_id": "...", "filename": "...", "extraction": {...}}]
extraction: skaler alanlar + taraflar + agreement{alan:skor} + verification +
regex_check + belge_turu_kodu_tahmini + ozet.

Birleştirme kuralları (plan "Merge" bölümü + Kararlar):
- Alan bazlı çoğunluk oyu; payda = alanı DOLU olan belge sayısı (poliçe
  belgesinin esas_no'suz olması esas_no güvenini düşürmez).
- confidence = belge-arası uyum × katkı veren belgelerin ensemble uyumu
  ortalaması; doğrulayıcı/regex sonucu ayrı bayrak olarak taşınır (rozet UI'ı).
- esas_no beraberliği en yeni belge_tarihi ile çözülür.
- Poliçe alanları oya GİRMEZ — hekim başına poliçe LİSTESİ olarak taşınır;
  açılış/olay tarihi hangi döneme düşüyorsa o poliçe relevant işaretlenir.
- esas_no/mahkeme çelişkisi hakem LLM'e gider (Katman 3, route tetikler);
  çelişki yoksa hakem çağrılmaz.
"""
import re
import unicodedata
from collections import Counter
from datetime import date
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Tuple

from party_check import _match_name, normalize_party_key, normalize_person_name, normalize_tc

# Çıkış alanı → çıkarım alanı eşlemesi (düz çoğunluk oyu alanları)
PLAIN_VOTE_FIELDS = {
    "esas_no": "esas_no",
    "court": "mahkeme",
    "file_type": "yargi_turu",
    "teblig_tarihi": "teblig_tarihi",
    "sub_type_extra": "uzmanlik_tahmini",
    # Sigorta atama/görevlendirme yazısından (2026-08-01 — karar 8 geri alındı,
    # atama yazısı da sihirbaza yüklenebilir)
    "hasar_dosya_no": "hasar_dosya_no",
    "hukuk_no": "hukuk_no",
}
# Dava dilekçesi öncelikli alanlar: dilekçede dolu ise yalnız dilekçe(ler) oylar
DILEKCE_PRIORITY_FIELDS = {
    "subject": "dava_konusu",
    "maddi_tazminat": "maddi_tazminat",
    "manevi_tazminat": "manevi_tazminat",
}
# Hakeme gidebilen alanlar (Katman 3)
ARBITER_FIELDS = ("esas_no", "court")

# Taraf rolleri: dava rolü belge-özel rolden (poliçe/vekaletname) daha bilgilidir
LITIGATION_ROLES = ("DAVACI", "DAVALI", "MUDAHIL", "IHBAR_OLUNAN")

POLICY_FIELDS = (
    "police_no", "police_turu", "sigorta_sirketi", "police_baslangic_tarihi",
    "police_bitis_tarihi", "retroaktif_tarihi", "sigortali_kurum", "teminat_limiti",
)

_DATE_TR_RE = re.compile(r"^(\d{1,2})[./](\d{1,2})[./]((?:19|20)\d{2})$")


# =====================================================================
# Temel yardımcılar
# =====================================================================


def _norm(value: Any) -> str:
    """Oylama anahtarı: aksan-duyarsız, boşluk-normalize, büyük harf.

    (case_intake_analyzer.norm_key ile aynı semantik; analyzer import zinciri
    Gemini istemcisini çektiğinden burada bağımsız tutulur.)
    """
    s = str(value).strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s)


def _vote_key(value: Any) -> str:
    """Oy sepeti anahtarı; sayısal değerlerde 50000 ↔ 50000.0 aynı sepete düşer."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{float(value):g}"
    return _norm(value)


def parse_iso_date(value: Any) -> Optional[date]:
    """ISO (YYYY-MM-DD) öncelikli, dd.mm.yyyy toleranslı tarih ayrıştırma."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    m = _DATE_TR_RE.match(s)
    if m:
        d, mo, y = m.groups()
        try:
            return date(int(y), int(mo), int(d))
        except ValueError:
            return None
    return None


def _ens_agreement(doc: Dict, field: str) -> float:
    """Belgenin o alandaki ensemble uyumu (analyze çıktısındaki agreement)."""
    agreement = (doc.get("extraction") or {}).get("agreement") or {}
    try:
        return float(agreement.get(field, 1.0))
    except (TypeError, ValueError):
        return 1.0


def _is_dilekce(doc: Dict) -> bool:
    tur = (doc.get("extraction") or {}).get("belge_turu_tahmini") or ""
    return "DILEKCE" in _norm(tur)


def _belge_tarihi(doc: Dict) -> Optional[date]:
    return parse_iso_date((doc.get("extraction") or {}).get("belge_tarihi"))


# =====================================================================
# Alan birleştirme (çoğunluk oyu)
# =====================================================================


def _field_vote(
    docs: List[Dict],
    extraction_key: str,
    tie_break_newest: bool = False,
) -> Dict[str, Any]:
    """Alan bazlı belge-arası çoğunluk oyu.

    agreement = kazanan_oy / alanı dolu belge sayısı.
    confidence = agreement × kazanan belgelerin ensemble uyumu ortalaması.
    Beraberlik: tie_break_newest ise en yeni belge_tarihi'li aday kazanır
    (yeni esas no eski tensipten daha günceldir); değilse ensemble ağırlığı.
    """
    votes: Dict[str, Dict[str, Any]] = {}
    docs_with_value = 0
    for doc in docs:
        v = (doc.get("extraction") or {}).get(extraction_key)
        if v is None or v == "":
            continue
        docs_with_value += 1
        k = _vote_key(v)
        entry = votes.setdefault(
            k, {"raw": v, "count": 0, "weight": 0.0, "sources": [], "newest": date.min}
        )
        entry["count"] += 1
        entry["weight"] += _ens_agreement(doc, extraction_key)
        entry["sources"].append(doc.get("filename") or doc.get("process_id") or "?")
        bt = _belge_tarihi(doc)
        if bt and bt > entry["newest"]:
            entry["newest"] = bt

    if not votes:
        return {"value": None, "agreement": None, "confidence": None, "candidates": [], "sources": []}

    def sort_key(item: Tuple[str, Dict]) -> Tuple:
        k, e = item
        if tie_break_newest:
            return (e["count"], e["newest"], e["weight"], k)
        return (e["count"], e["weight"], e["newest"], k)

    winner_key, winner = max(votes.items(), key=sort_key)
    agreement = round(winner["count"] / docs_with_value, 2)
    ens_avg = winner["weight"] / winner["count"]
    candidates = [
        {"value": e["raw"], "count": e["count"], "sources": e["sources"]}
        for _, e in sorted(votes.items(), key=sort_key, reverse=True)
    ]
    return {
        "value": winner["raw"],
        "agreement": agreement,
        "confidence": round(agreement * ens_avg, 2),
        "candidates": candidates,
        "sources": winner["sources"],
        "_winner_key": winner_key,
    }


def _aggregate_verification(docs: List[Dict], claim_key_prefix: str, winner_norm: Optional[str]) -> Optional[bool]:
    """Kazanan değer için doğrulayıcı (Katman 2) sonuçlarını birleştirir.

    Herhangi bir belge kazanan değeri kanıtla doğruladıysa True; en az bir
    belge açıkça yalanlıyor ve hiçbiri doğrulamıyorsa False; aksi halde None.
    """
    if winner_norm is None:
        return None
    saw_false = False
    for doc in docs:
        verification = (doc.get("extraction") or {}).get("verification") or {}
        for alan, k in verification.items():
            if not str(alan).startswith(claim_key_prefix):
                continue
            if _norm(k.get("deger") or "") != winner_norm:
                continue
            if k.get("belgede_geciyor") is True:
                return True
            if k.get("belgede_geciyor") is False:
                saw_false = True
    return False if saw_false else None


def _aggregate_regex_check(docs: List[Dict], winner_norm: Optional[str]) -> Optional[bool]:
    """Kazanan esas_no için regex çapraz kontrolü: kazananı üreten belgelerden
    herhangi birinde regex de aynı değeri bulduysa True."""
    if winner_norm is None:
        return None
    result = None
    for doc in docs:
        ext = doc.get("extraction") or {}
        if _vote_key(ext.get("esas_no") or "") != winner_norm:
            continue
        check = (ext.get("regex_check") or {}).get("esas_no")
        if check is True:
            return True
        if check is False:
            result = False
    return result


def merge_fields(docs: List[Dict]) -> Dict[str, Dict]:
    """Dava kartı alanlarını belge-arası çoğunluk oyuyla birleştirir."""
    fields: Dict[str, Dict] = {}

    for out_key, ext_key in PLAIN_VOTE_FIELDS.items():
        fields[out_key] = _field_vote(docs, ext_key, tie_break_newest=(out_key == "esas_no"))

    # Dilekçe öncelikli alanlar: dava dilekçesinde dolu ise yalnız dilekçeler oylar
    for out_key, ext_key in DILEKCE_PRIORITY_FIELDS.items():
        dilekce_docs = [
            d for d in docs
            if _is_dilekce(d) and (d.get("extraction") or {}).get(ext_key) not in (None, "")
        ]
        fields[out_key] = _field_vote(dilekce_docs or docs, ext_key)

    # Açılış tarihi: açık dava_acilis_tarihi varsa oyla; yoksa dilekçe sınıfı
    # belgelerin en erken belge_tarihi'nden türet (plan: merge_dates).
    opening = _field_vote(docs, "dava_acilis_tarihi")
    if opening["value"] is None:
        candidates = [(d, _belge_tarihi(d)) for d in docs if _is_dilekce(d) and _belge_tarihi(d)]
        if candidates:
            doc, earliest = min(candidates, key=lambda t: t[1])
            opening = {
                "value": earliest.isoformat(),
                "agreement": None,
                "confidence": 0.4,  # türetilmiş değer — düşük güvenli ön-dolgu
                "candidates": [],
                "sources": [doc.get("filename") or "?"],
                "derived_from": "belge_tarihi",
            }
    fields["opening_date"] = opening

    # Doğrulayıcı + regex bayrakları (yalnız esas_no kritik alan — karar 2)
    esas = fields["esas_no"]
    winner_norm = esas.pop("_winner_key", None)
    esas["verified"] = _aggregate_verification(docs, "esas_no", winner_norm)
    esas["regex_check"] = _aggregate_regex_check(docs, winner_norm)

    for f in fields.values():
        f.pop("_winner_key", None)
    return fields


# =====================================================================
# Çelişki tespiti + hakem kararlarının uygulanması (Katman 3)
# =====================================================================


def detect_conflicts(fields: Dict[str, Dict]) -> List[Dict]:
    """esas_no/mahkeme'de birden fazla belge-destekli aday → hakem tetiklenir."""
    conflicts = []
    for key in ARBITER_FIELDS:
        candidates = (fields.get(key) or {}).get("candidates") or []
        if len(candidates) >= 2:
            conflicts.append({
                "alan": key,
                "adaylar": [
                    {"deger": str(c["value"]), "belgeler": c["sources"]} for c in candidates
                ],
            })
    return conflicts


def build_doc_summaries(docs: List[Dict]) -> List[Dict]:
    """Hakem LLM'e giden belge özeti — tüm çıkarımlar değil, karar için gerekli çekirdek."""
    out = []
    for d in docs:
        ext = d.get("extraction") or {}
        out.append({
            "dosya": d.get("filename"),
            "belge_turu": ext.get("belge_turu_tahmini"),
            "belge_tarihi": ext.get("belge_tarihi"),
            "esas_no": ext.get("esas_no"),
            "mahkeme": ext.get("mahkeme"),
            "ozet": ext.get("ozet"),
        })
    return out


def apply_arbitration(fields: Dict[str, Dict], kararlar: List[Dict]) -> List[Dict]:
    """Hakem kararlarını alanlara uygular; gerekçe sihirbazda gösterilir.

    Karar yalnızca mevcut adaylardan biriyle eşleşiyorsa uygulanır — hakemin
    aday dışı bir değer uydurması (halüsinasyon) sessizce yok sayılmaz,
    uygulanmayan kararlar döndürülür (route bunu warning'e çevirir).
    """
    unapplied = []
    for karar in kararlar or []:
        alan = karar.get("alan")
        field = fields.get(alan) if alan in ARBITER_FIELDS else None
        if field is None:
            unapplied.append(karar)
            continue
        secilen = _vote_key(karar.get("secilen_deger") or "")
        match = next(
            (c for c in field.get("candidates") or [] if _vote_key(c["value"]) == secilen),
            None,
        )
        if match is None:
            unapplied.append(karar)
            continue
        field["value"] = match["value"]
        field["sources"] = match["sources"]
        field["arbiter"] = {
            "secilen_deger": str(match["value"]),
            "gerekce": karar.get("gerekce"),
        }
    return unapplied


# =====================================================================
# Taraf birleştirme
# =====================================================================


def match_client(name: str, tc_no: Optional[str], client_rows: List[Dict]) -> Optional[Dict]:
    """Tarafı kayıtlı carilerle eşler; en güçlü eşleşmeyi döndürür.

    Skorlar: tc_no 1.0 · isim tam 0.95 · isim fuzzy 0.8 (party_check kademeleri).
    Dönen name, DB'deki kanonik addır (zenginleştirme 3: tek tıkla kabul rozeti).
    """
    q_norm = normalize_person_name(name or "")
    q_tc = normalize_tc(tc_no)
    best: Optional[Dict] = None
    for c in client_rows:
        c_tc = normalize_tc(c.get("tc_no"))
        if q_tc and c_tc and q_tc == c_tc:
            matched_on, score = "tc_no", 1.0
        else:
            m = _match_name(q_norm, normalize_person_name(c.get("name") or ""))
            if m is None:
                continue
            matched_on, score = m, (0.95 if m == "name_exact" else 0.8)
        if best is None or score > best["score"]:
            best = {
                "client_id": c.get("id"),
                "name": c.get("name"),
                "category": c.get("category"),
                "contact_type": c.get("contact_type"),
                "matched_on": matched_on,
                "score": score,
            }
        if best["score"] >= 1.0:
            break
    return best


def _party_type_for(roller: Counter, match: Optional[Dict]) -> str:
    """party_type kararı (plan: merge_parties).

    Öncelik: kayıtlı müvekkil eşleşmesi → CLIENT; SIGORTALI görülmüş hekim →
    CLIENT (büro hekim savunması yapar, poliçedeki sigortalı müvekkil adayıdır);
    MUDAHIL/IHBAR_OLUNAN/DIGER → THIRD; kalan (davacı/davalı/sigorta şirketi) → COUNTER.
    """
    if match and (match.get("contact_type") or "Client") == "Client":
        return "CLIENT"
    if roller.get("SIGORTALI"):
        return "CLIENT"
    top_rol = roller.most_common(1)[0][0] if roller else "DIGER"
    if top_rol in ("MUDAHIL", "IHBAR_OLUNAN", "DIGER"):
        return "THIRD"
    return "COUNTER"


def merge_parties(docs: List[Dict], client_rows: List[Dict]) -> List[Dict]:
    """Belgelerin taraf listelerini normalize ada göre birleştirir.

    - Rol oyu dava rollerine (DAVACI/DAVALI/MUDAHIL/IHBAR_OLUNAN) öncelik verir:
      hekim dilekçede DAVALI, üç poliçede SIGORTALI görünse de rolü DAVALI'dır.
    - VEKIL satırları taraf listesine girmez (plan: vekilleri taraf listeleme).
    - TC herhangi bir belgede varsa korunur; kayıtlı cari eşleşmesi match olarak döner.
    """
    parties: Dict[str, Dict] = {}
    for doc in docs:
        ext = doc.get("extraction") or {}
        seen_in_doc = set()
        for p in ext.get("taraflar") or []:
            ad = p.get("ad") or ""
            rol = p.get("rol") or "DIGER"
            if rol == "VEKIL":
                continue
            key = normalize_party_key(ad)
            if not key:
                continue
            entry = parties.setdefault(key, {
                "ad": ad, "roller": Counter(), "tc_no": None,
                "doc_count": 0, "sources": [],
            })
            if key not in seen_in_doc:
                entry["doc_count"] += 1
                entry["sources"].append(doc.get("filename") or "?")
                seen_in_doc.add(key)
            entry["roller"][rol] += 1
            # Sansürsüz TC sansürlüye tercih edilir; ilk dolu değer korunur
            tc = p.get("tc_no")
            if tc and (entry["tc_no"] is None or ("*" in str(entry["tc_no"]) and "*" not in str(tc))):
                entry["tc_no"] = tc

    n = len(docs)
    merged = []
    for e in parties.values():
        litigation = Counter({r: c for r, c in e["roller"].items() if r in LITIGATION_ROLES})
        rol_votes = litigation or e["roller"]
        rol = rol_votes.most_common(1)[0][0]
        m = match_client(e["ad"], e["tc_no"], client_rows)
        merged.append({
            "name": e["ad"],
            "rol": rol,
            "party_type": _party_type_for(e["roller"], m),
            "tc_no": e["tc_no"],
            "doc_count": e["doc_count"],
            "agreement": round(e["doc_count"] / n, 2) if n else None,
            "sources": e["sources"],
            "match": m,
        })
    # Müvekkil adayları önce, sonra görülme sıklığı — sihirbaz listesi için stabil sıra
    merged.sort(key=lambda p: (p["party_type"] != "CLIENT", -p["doc_count"], p["name"]))
    return merged


# =====================================================================
# Poliçe birleştirme (oy YOK — hekim başına liste)
# =====================================================================


def _policy_key(policy: Dict) -> Tuple:
    """Poliçe kimliği: no + dönem başı. Aynı poliçenin iki kopyası tekilleşir,
    aynı numaralı yenileme (farklı dönem) ayrı kayıt kalır."""
    return (
        _norm(policy.get("police_no") or ""),
        str(policy.get("baslangic") or ""),
    )


def _period_covers(policy: Dict, target: Optional[date]) -> bool:
    if target is None:
        return False
    start = parse_iso_date(policy.get("retroaktif")) or parse_iso_date(policy.get("baslangic"))
    end = parse_iso_date(policy.get("bitis"))
    if start is None or end is None:
        return False
    return start <= target <= end


def policy_overlap_warnings(policies: List[Dict]) -> List[Dict]:
    """Aynı tip (şirket + tür) poliçelerde dönem çakışması uyarısı üretir."""
    warnings = []
    seen_pairs = set()
    for i, a in enumerate(policies):
        for b in policies[i + 1:]:
            if _policy_key(a) == _policy_key(b):
                continue
            if _norm(a.get("sigorta_sirketi") or "") != _norm(b.get("sigorta_sirketi") or ""):
                continue
            if (a.get("police_turu") or "") != (b.get("police_turu") or ""):
                continue
            a_start, a_end = parse_iso_date(a.get("baslangic")), parse_iso_date(a.get("bitis"))
            b_start, b_end = parse_iso_date(b.get("baslangic")), parse_iso_date(b.get("bitis"))
            if None in (a_start, a_end, b_start, b_end):
                continue
            # Uç uca dönemler (eski bitiş == yeni başlangıç) yenileme desenidir,
            # çakışma DEĞİLDİR — sınırda kesişme uyarı üretmez.
            if a_start < b_end and b_start < a_end:
                pair = tuple(sorted([_policy_key(a), _policy_key(b)]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                warnings.append({
                    "code": "POLICY_PERIOD_OVERLAP",
                    "message": (
                        "Aynı tip iki poliçenin dönemleri çakışıyor: "
                        f"{a.get('police_no') or '?'} ({a.get('baslangic')} – {a.get('bitis')}) / "
                        f"{b.get('police_no') or '?'} ({b.get('baslangic')} – {b.get('bitis')})"
                    ),
                })
    return warnings


def merge_policies(
    docs: List[Dict],
    opening_date: Optional[str],
    parties: List[Dict],
    known_policies: Optional[List[Dict]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """Poliçe alanlarını belge başına toplar (çoğunluk oyu YOK) ve kayıtlı
    poliçelerle harmanlar.

    - sigortali: belgenin taraflarındaki rol=SIGORTALI kişi; client_id o kişinin
      cari eşleşmesinden gelir (client_policies beslemesinin hedefi).
    - relevant: açılış/olay tarihi retroaktif(varsa)–bitiş aralığına düşen poliçe.
    - known_policies (client_policies satırları) 'kayıtlı' kaynaklı ve saved=True
      olarak listeye girer; belge kopyaları saved bayrağıyla işaretlenir.
    - Hiçbir poliçe açılış tarihini kapsamıyorsa POLICY_PERIOD_MISMATCH uyarısı
      (Faz 2 notu: çok poliçeli belgede koşular farklı yılın poliçesini seçebiliyor).
    """
    target = parse_iso_date(opening_date)
    match_by_name = {
        normalize_party_key(p["name"]): p.get("match") for p in parties if p.get("match")
    }

    policies: List[Dict] = []
    seen = set()

    for doc in docs:
        ext = doc.get("extraction") or {}
        if not ext.get("police_no") and not (
            ext.get("sigorta_sirketi") and ext.get("police_baslangic_tarihi")
        ):
            continue
        sigortali = next(
            (p.get("ad") for p in ext.get("taraflar") or [] if p.get("rol") == "SIGORTALI"),
            None,
        )
        m = match_by_name.get(normalize_party_key(sigortali or ""))
        policy = {
            "police_no": ext.get("police_no"),
            "police_turu": ext.get("police_turu"),
            "sigorta_sirketi": ext.get("sigorta_sirketi"),
            "baslangic": ext.get("police_baslangic_tarihi"),
            "bitis": ext.get("police_bitis_tarihi"),
            "retroaktif": ext.get("retroaktif_tarihi"),
            "sigortali": sigortali,
            "sigortali_kurum": ext.get("sigortali_kurum"),
            "teminat_limiti": ext.get("teminat_limiti"),
            "client_id": m.get("client_id") if m else None,
            "source": doc.get("filename"),
            "process_id": doc.get("process_id"),
            "saved": False,
        }
        key = _policy_key(policy)
        if key in seen:
            continue
        seen.add(key)
        policies.append(policy)

    for row in known_policies or []:
        policy = {
            "police_no": row.get("police_no"),
            "police_turu": row.get("police_turu"),
            "sigorta_sirketi": row.get("sigorta_sirketi"),
            "baslangic": str(row["baslangic_tarihi"]) if row.get("baslangic_tarihi") else None,
            "bitis": str(row["bitis_tarihi"]) if row.get("bitis_tarihi") else None,
            "retroaktif": str(row["retroaktif_tarihi"]) if row.get("retroaktif_tarihi") else None,
            "sigortali": row.get("client_name"),
            "sigortali_kurum": row.get("sigortali_kurum"),
            "teminat_limiti": float(row["teminat_limiti"]) if row.get("teminat_limiti") is not None else None,
            "client_id": row.get("client_id"),
            "source": "kayıtlı poliçe",
            "process_id": None,
            "saved": True,
        }
        key = _policy_key(policy)
        if key in seen:
            # Belgeden gelen kopya zaten kayıtlı → saved işaretle
            for p in policies:
                if _policy_key(p) == key:
                    p["saved"] = True
            continue
        seen.add(key)
        policies.append(policy)

    for p in policies:
        p["relevant"] = _period_covers(p, target)

    warnings = policy_overlap_warnings(policies)
    if policies and target and not any(p["relevant"] for p in policies):
        warnings.append({
            "code": "POLICY_PERIOD_MISMATCH",
            "message": (
                "Hiçbir poliçenin dönemi dava açılış/olay tarihini "
                f"({target.isoformat()}) kapsamıyor — belgede birden fazla poliçe "
                "dönemi olabilir, poliçe bilgilerini kontrol edin."
            ),
        })
    return policies, warnings


# =====================================================================
# DB destekli zenginleştirme yardımcıları (satırlar route'tan gelir)
# =====================================================================


def suggest_known_court(value: Optional[str], known_courts: List[str]) -> Optional[str]:
    """Mahkeme adını mevcut davalardaki bilinen yazımla eşler (zenginleştirme 5).

    Normalize eşitlik → doğrudan öneri; değilse yüksek benzerlik (≥0.90) en iyi
    aday. Birebir aynı yazımsa öneri üretmez (kirlilik yok)."""
    if not value:
        return None
    v_norm = _norm(value)
    best, best_ratio = None, 0.0
    for kc in known_courts:
        if kc == value:
            return None
        kc_norm = _norm(kc)
        if kc_norm == v_norm:
            return kc
        ratio = SequenceMatcher(None, v_norm, kc_norm).ratio()
        if ratio > best_ratio:
            best, best_ratio = kc, ratio
    return best if best_ratio >= 0.90 else None


def normalize_known_value(value: Optional[str], known_names: Optional[List[str]]) -> Optional[str]:
    """Serbest değeri kanonik liste adına eşler (dava konusu / uzmanlık bekçisi).

    Normalize eşitlik → kanonik ad; değilse en yüksek benzerlik ≥0.90 → kanonik
    ad; eşleşme yoksa None. Kural kesin: değer YA yönetici panelindeki dinamik
    listeden birebir gelir YA boş kalır — liste dışı serbest metin taslağa
    sızmaz, kullanıcı boş alanı combobox'tan doldurur (2026-08-01 kararı)."""
    if not value or not known_names:
        return None
    v_norm = _norm(value)
    best, best_ratio = None, 0.0
    for name in known_names:
        n_norm = _norm(name)
        if n_norm == v_norm:
            return name
        ratio = SequenceMatcher(None, v_norm, n_norm).ratio()
        if ratio > best_ratio:
            best, best_ratio = name, ratio
    return best if best_ratio >= 0.90 else None


def client_priors(case_rows: List[Dict]) -> Dict[str, Any]:
    """Müvekkilin geçmiş davalarından örüntüler (zenginleştirme 4).

    case_rows: [{"file_type", "sub_type", "responsible_lawyer_name", "subject"}]
    En sık dolu değerler düşük-güvenli ön-dolgu önerisi olarak döner."""
    priors: Dict[str, Any] = {}
    for key in ("file_type", "sub_type", "responsible_lawyer_name", "subject"):
        values = [r.get(key) for r in case_rows if r.get(key)]
        if values:
            value, count = Counter(values).most_common(1)[0]
            priors[key] = {"value": value, "count": count, "total": len(values)}
    return priors


# =====================================================================
# Taslak kurucu
# =====================================================================


def build_draft(
    docs: List[Dict],
    client_rows: List[Dict],
    known_policies: Optional[List[Dict]] = None,
    known_courts: Optional[List[str]] = None,
    known_subjects: Optional[List[str]] = None,
    known_specialties: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], List[Dict]]:
    """Saf birleştirme: alanlar + taraflar + poliçeler + uyarılar + belge özeti.

    Döner: (draft, conflicts) — conflicts doluysa route hakem LLM'i çağırıp
    apply_arbitration ile taslağı günceller. Duplicate/tanıdık sorgu/priors
    DB gerektirdiğinden route katmanında eklenir.
    """
    fields = merge_fields(docs)
    parties = merge_parties(docs, client_rows)
    policies, warnings = merge_policies(
        docs, fields["opening_date"]["value"], parties, known_policies
    )

    court_suggestion = suggest_known_court(fields["court"]["value"], known_courts or [])
    if court_suggestion:
        fields["court"]["known_court_suggestion"] = court_suggestion

    # Dava konusu + uzmanlık kanonik bekçisi: liste yüklüyse değer YA listeden
    # YA boş. Küçük model sapmaları (≥0.90 benzerlik) kanonik ada toparlanır;
    # eşleşmeyen değer boşaltılır (alan tiksiz gelir, kullanıcı seçer).
    # Adaylar da aynı süzgeçten geçer — popover liste dışı değer önermesin.
    for f_key, known in (("subject", known_subjects), ("sub_type_extra", known_specialties)):
        if not known:
            continue
        f = fields[f_key]
        if f["value"]:
            f["value"] = normalize_known_value(f["value"], known)
        if f.get("candidates"):
            canon_cands: Dict[str, Dict] = {}
            for c in f["candidates"]:
                canon = normalize_known_value(c.get("value"), known)
                if not canon:
                    continue
                if canon in canon_cands:
                    canon_cands[canon]["count"] += c.get("count", 0)
                    canon_cands[canon]["sources"] = sorted(
                        set(canon_cands[canon]["sources"]) | set(c.get("sources") or [])
                    )
                else:
                    canon_cands[canon] = {**c, "value": canon,
                                          "sources": list(c.get("sources") or [])}
            f["candidates"] = list(canon_cands.values())

    documents = []
    for d in docs:
        ext = d.get("extraction") or {}
        documents.append({
            "process_id": d.get("process_id"),
            "filename": d.get("filename"),
            "belge_turu_kodu": ext.get("belge_turu_kodu_tahmini"),
            "belge_turu_tahmini": ext.get("belge_turu_tahmini"),
            "ozet": ext.get("ozet"),
            "status": "ok",
        })

    draft = {
        "fields": fields,
        "parties": parties,
        "policies": policies,
        "warnings": warnings,
        "documents": documents,
        "duplicate_case": None,
        "priors": {},
    }
    return draft, detect_conflicts(fields)


# =====================================================================
# Zenginleştirme modu (Faz 7 / İş Kalemi 5) — kayıtlı dava bağlamı
# =====================================================================

# Taslak alan anahtarı → get_case sözlüğündeki dava alanı. teblig_tarihi
# dava kartında yok (takip paneli alanı) — bağlama girmez. judicial_unit
# route 4b'de türetildiğinden inject sırasında henüz yoktur (fields.get
# toleranslı), annotate hakem+türetme SONRASI koştuğu için onu da kapsar.
ENRICH_CASE_FIELD_MAP = {
    "esas_no": "esas_no",
    "court": "court",
    "file_type": "file_type",
    "subject": "subject",
    "sub_type_extra": "sub_type_extra",
    "opening_date": "opening_date",
    "maddi_tazminat": "maddi_tazminat",
    "manevi_tazminat": "manevi_tazminat",
    "judicial_unit": "judicial_unit",
    "hasar_dosya_no": "hasar_dosya_no",
    "hukuk_no": "hukuk_no",
}

SAVED_CASE_SOURCE = "kayıtlı dava"


def _case_value_empty(field_key: str, value: Any) -> bool:
    """Dava alanı 'boş' sayılır mı? Tazminatta 0 boş demektir (add_case
    varsayılanı 0 yazar — 0'ı dolu saymak her davayı 'çelişkili' yapardı)."""
    if value is None or value == "":
        return True
    if field_key in ("maddi_tazminat", "manevi_tazminat"):
        try:
            return float(value) == 0.0
        except (TypeError, ValueError):
            return False
    return False


def inject_case_candidates(fields: Dict[str, Dict], case_row: Dict[str, Any]) -> None:
    """Kayıtlı dava değerlerini alan adaylarına katar (hakem ÖNCESİ çağrılır).

    Belge adayıyla aynı (normalize) değer yeni aday üretmez — o adayın
    kaynaklarına "kayıtlı dava" eklenir; farklı değer count=0 ile yeni aday
    olur, böylece esas_no/mahkeme çelişkisi detect_conflicts'e (→ Katman 3
    hakem) görünür. Alanın value'su DEĞİŞMEZ: belge önerisi taslakta kalır,
    doldur/teyit kararı kullanıcının.
    """
    for f_key, case_key in ENRICH_CASE_FIELD_MAP.items():
        field = fields.get(f_key)
        current = case_row.get(case_key)
        if field is None or _case_value_empty(f_key, current):
            continue
        k = _vote_key(current)
        match = next(
            (c for c in field.get("candidates") or [] if _vote_key(c["value"]) == k),
            None,
        )
        if match is not None:
            if SAVED_CASE_SOURCE not in match["sources"]:
                match["sources"].append(SAVED_CASE_SOURCE)
        else:
            field.setdefault("candidates", []).append({
                "value": current, "count": 0, "sources": [SAVED_CASE_SOURCE],
            })


def annotate_enrich_status(fields: Dict[str, Dict], case_row: Dict[str, Any]) -> None:
    """Alan başına doldur/teyit/çelişki durumu (hakem + türetmeler SONRASI).

    fill: dava alanı boş + belgede değer var → doldur önerisi;
    confirm: dolu + belge aynı → teyit; conflict: dolu + belge farklı → uyarı;
    keep: dolu + belge önerisi yok → kayıtlı değer korunur. İkisi de boşsa
    enrich bilgisi yazılmaz (alan sihirbazda elle doldurulabilir kalır).
    """
    for f_key, case_key in ENRICH_CASE_FIELD_MAP.items():
        field = fields.get(f_key)
        if field is None:
            continue
        current = case_row.get(case_key)
        cur_empty = _case_value_empty(f_key, current)
        value = field.get("value")
        val_empty = value is None or value == ""
        if cur_empty and val_empty:
            continue
        if cur_empty:
            status = "fill"
        elif val_empty:
            status = "keep"
        elif _vote_key(value) == _vote_key(current):
            status = "confirm"
        else:
            status = "conflict"
        field["enrich"] = {"status": status, "current": current}


def mark_existing_parties(parties: List[Dict], case_parties: List[Dict]) -> None:
    """Birleşen taraf satırlarını davadaki kayıtlı taraflarla eşler.

    Eşleşen satır existing={case_party_id, name, role} alır — sihirbaz bu
    satırları "zaten kayıtlı" gösterir, apply'a göndermez (taraflarda yalnız
    EKLEME). Eşleşme anahtarı diff_case_parties ile aynı: önce normalize TC,
    sonra normalize_party_key (kurumsal ünvan eşitlemeli).
    """
    by_tc: Dict[str, Dict] = {}
    by_name: Dict[str, Dict] = {}
    for cp in case_parties:
        tc = normalize_tc(cp.get("tc_no"))
        if tc:
            by_tc.setdefault(tc, cp)
        key = normalize_party_key(cp.get("name") or "")
        if key:
            by_name.setdefault(key, cp)
    for p in parties:
        tc = normalize_tc(p.get("tc_no"))
        hit = by_tc.get(tc) if tc else None
        if hit is None:
            key = normalize_party_key(p.get("name") or "")
            hit = by_name.get(key) if key else None
        p["existing"] = (
            {"case_party_id": hit.get("id"), "name": hit.get("name"), "role": hit.get("role")}
            if hit else None
        )


# Hakem çağrısı imzası (route enjekte eder; testte sahte hakemle doğrulanır)
ArbiterFn = Callable[[List[Dict], List[Dict]], List[Dict]]
