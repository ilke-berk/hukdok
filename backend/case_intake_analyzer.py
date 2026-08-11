"""Otonom dava açma — intake çıkarım motoru (Faz 2).

`/api/case-intake/analyze` için belge analiz generator'ı. `/process`'in
analyzer'ından bağımsız bir hattır ama dönüşüm adımlarını (UDF/Office/görüntü
→ PDF), OCR kararını ve Gemini retry mantığını analyzer'dan yeniden kullanır.

Kalibrasyon kararları (docs/otonom-dava-acma-gelistirme-plani-2026-07-24.md):
- Model: GEMINI_INTAKE_MODEL env (varsayılan models/gemini-3.6-flash) —
  /process'in flash-lite'ı DEĞİL; sigortalı çıkarımı flash-lite'ta 9/15,
  3.6-flash'ta 16/16.
- Sayfa kırpma YOK — belge Gemini'ye tam gider.
- Katman 1: ensemble N=3 + alan bazında çoğunluk oyu (tek seferlik
  halüsinasyon elenir; tek bozuk koşu belgeyi öldürmez).
- Katman 2: kritik alanlar (esas_no, tc_no, taraf rolleri) için doğrulayıcı
  geçiş — "değer belgede geçiyor mu, kanıt cümlesi ne?".
- Regex birincil çıkarıcı değil, çapraz kontrol.
"""
import asyncio
import json
import os
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from google.genai import types as genai_types

import analyzer
import gemini_client
from config.settings import settings
from managers.log_manager import TechnicalLogger
from party_check import normalize_party_key
from prompts import (
    get_case_intake_arbiter_instruction,
    get_case_intake_instruction,
    get_case_intake_verifier_instruction,
)
from schemas_intake import CaseIntakeArbitration, CaseIntakeExtraction, CaseIntakeVerification

DEFAULT_INTAKE_MODEL = "models/gemini-3.6-flash"
DEFAULT_ENSEMBLE_N = 3

# Çoğunluk oyuna giren skaler alanlar (taraflar ayrı birleştirilir, ozet oya girmez)
SCALAR_FIELDS = [
    "belge_turu_tahmini", "belge_tarihi", "mahkeme", "esas_no", "yargi_turu",
    "dava_konusu", "dava_acilis_tarihi", "teblig_tarihi", "uzmanlik_tahmini",
    "maddi_tazminat", "manevi_tazminat", "police_no", "police_turu", "sigorta_sirketi",
    "police_baslangic_tarihi", "police_bitis_tarihi", "retroaktif_tarihi", "sigortali_kurum",
    "teminat_limiti", "hasar_dosya_no", "hukuk_no",
]

ESAS_NO_RE = re.compile(
    r"(?:ESAS|E\s*\.)\s*(?:NO)?\s*[:.]?\s*((?:19|20)\d{2}\s*/\s*\d{1,6})", re.IGNORECASE
)
DATE_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./]((?:19|20)\d{2})\b")


def get_intake_model() -> str:
    return os.getenv("GEMINI_INTAKE_MODEL") or DEFAULT_INTAKE_MODEL


# =====================================================================
# Saf yardımcılar (unit test hedefi)
# =====================================================================


def norm_key(value: Any) -> str:
    """Oylama anahtarı: aksan-duyarsız, boşluk-normalize, büyük harf."""
    s = str(value).strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s)


def regex_prehints(text: Optional[str]) -> Dict[str, str]:
    """Dijital metinden prompt'a enjekte edilecek ipuçları (esas_no adayları, tarihler)."""
    if not text:
        return {}
    hints = {}
    esas = [re.sub(r"\s", "", m) for m in ESAS_NO_RE.findall(text)]
    if esas:
        hints["esas_no adayları"] = ", ".join(dict.fromkeys(esas))
    dates = [f"{y}-{int(mo):02d}-{int(d):02d}" for d, mo, y in DATE_RE.findall(text)[:10]]
    if dates:
        hints["belgede geçen tarihler"] = ", ".join(dict.fromkeys(dates))
    return hints


def majority_vote(runs: List[Dict]) -> Tuple[Dict, List[Dict]]:
    """Alan bazında çoğunluk oyu. agreement = kazanan_oy / koşu_sayısı (null'lar dahil).

    Döner: (merged, parties)
    - merged: {alan: {"value", "agreement", "candidates"}}
    - parties: [{"ad", "rol", "tc_no", "agreement"}] — normalize ada göre birleşim,
      rol için oy çokluğu.
    """
    merged = {}
    n = len(runs)
    for field in SCALAR_FIELDS:
        votes = Counter()
        originals = {}
        for r in runs:
            v = r.get(field)
            if v is None or v == "":
                votes["__null__"] += 1
            else:
                k = norm_key(v)
                votes[k] += 1
                originals.setdefault(k, v)  # ilk görülen ham hali göster
        top_key, top_count = votes.most_common(1)[0]
        merged[field] = {
            "value": None if top_key == "__null__" else originals[top_key],
            "agreement": round(top_count / n, 2),
            "candidates": {
                (k if k == "__null__" else str(originals[k])): c for k, c in votes.items()
            },
        }
    # Taraflar: normalize ada göre birleşim. Unvan sökümü party_check ile —
    # "Av. FATİH BEYAZIT" ve "FATİH BEYAZIT" aynı kişidir, oyu bölmesin
    # (duman testinde görüldü). Aynı koşuda çift varyant agreement'ı şişirmesin
    # diye koşu başına tekil sayılır.
    parties = {}
    for r in runs:
        seen_in_run = set()
        for p in r.get("taraflar") or []:
            key = normalize_party_key(p.get("ad", ""))
            if not key:
                continue
            entry = parties.setdefault(
                key, {"ad": p["ad"], "roller": Counter(), "tc_no": None, "count": 0}
            )
            if key not in seen_in_run:
                entry["count"] += 1
                seen_in_run.add(key)
            entry["roller"][p.get("rol", "DIGER")] += 1
            if p.get("tc_no"):
                entry["tc_no"] = p["tc_no"]
    merged_parties = [
        {
            "ad": e["ad"],
            "rol": e["roller"].most_common(1)[0][0],
            "tc_no": e["tc_no"],
            "agreement": round(e["count"] / n, 2),
        }
        for e in parties.values()
    ]
    return merged, merged_parties


def pick_ozet(runs: List[Dict]) -> Optional[str]:
    """Ozet oya girmez (serbest metin hiç anlaşmaz) — en bilgilendirici (en uzun) alınır."""
    candidates = [r.get("ozet") for r in runs if r.get("ozet")]
    if not candidates:
        return None
    return max(candidates, key=len)


def regex_crosscheck(merged: Dict, text: Optional[str]) -> Dict[str, Optional[bool]]:
    """Regex ↔ AI çapraz kontrolü: aynı değeri bulurlarsa güven yükselir."""
    if not text:
        return {"esas_no": None}
    ai_esas = merged["esas_no"]["value"]
    found = [re.sub(r"\s", "", m) for m in ESAS_NO_RE.findall(text)]
    return {
        "esas_no": (norm_key(ai_esas) in {norm_key(x) for x in found})
        if (ai_esas and found)
        else None
    }


def build_critical_claims(merged: Dict, parties: List[Dict]) -> List[Dict[str, str]]:
    """Katman 2'ye gidecek iddia listesi — yalnız kritik alanlar (karar 2)."""
    claims = []
    esas = merged.get("esas_no", {}).get("value")
    if esas:
        claims.append({"alan": "esas_no", "deger": str(esas)})
    for p in parties:
        if p.get("tc_no"):
            claims.append({"alan": f"tc_no:{p['ad']}", "deger": str(p["tc_no"])})
        claims.append({"alan": f"rol:{p['ad']}", "deger": p["rol"]})
    return claims


def apply_verification(claims: List[Dict], kontroller: List[Dict]) -> Dict[str, Dict]:
    """Doğrulayıcı yanıtını iddialara eşler.

    Dönen sözlük iddia anahtarıyla (alan) indekslidir; doğrulayıcının
    yanıtlamadığı iddialar belgede_geciyor=None (bilinmiyor) kalır — kanıtsız
    değer sihirbazda düşük güvenli rozetle gösterilir.
    """
    by_alan: Dict[str, Dict] = {}
    for k in kontroller or []:
        by_alan.setdefault(str(k.get("alan")), k)
    out = {}
    for c in claims:
        k = by_alan.get(c["alan"])
        if k is None:
            out[c["alan"]] = {"deger": c["deger"], "belgede_geciyor": None, "kanit": None}
        else:
            out[c["alan"]] = {
                "deger": c["deger"],
                "belgede_geciyor": bool(k.get("belgede_geciyor")),
                "kanit": k.get("kanit"),
            }
    return out


def guess_doctype_code(belge_turu_tahmini: Optional[str], doctypes: List[Dict]) -> Optional[str]:
    """Serbest metin belge türü tahminini kayıtlı belge türü koduna eşler.

    Kesin eşleme merge adımının işidir (Faz 3); burada UI ön-seçimi için
    hafif bir sözlük eşlemesi yapılır. Kodlar '_' ile pad'lidir — pad'li kod
    olduğu gibi döndürülür (karşılaştırma etikete göre yapılır).
    Önce tam etiket eşleşmesi, sonra içerme (en uzun etiket kazanır).
    """
    if not belge_turu_tahmini or not doctypes:
        return None
    guess = norm_key(belge_turu_tahmini)
    exact, partial = None, []
    for dt in doctypes:
        label = dt.get("name") or dt.get("label") or ""
        code = dt.get("code")
        if not label or not code:
            continue
        label_n = norm_key(label)
        if label_n == guess:
            exact = code
            break
        if label_n and (label_n in guess or guess in label_n):
            partial.append((len(label_n), code))
    if exact:
        return exact
    if partial:
        return max(partial)[1]
    return None


# =====================================================================
# Katman 3 — belgeler-arası hakem (Faz 3; merge route'undan çağrılır)
# =====================================================================


async def arbitrate_conflicts(conflicts: List[Dict], doc_summaries: List[Dict]) -> List[Dict]:
    """Merge'in bulduğu esas_no/mahkeme çelişkileri için hakem LLM kararı alır.

    conflicts: services.case_intake.detect_conflicts çıktısı.
    doc_summaries: services.case_intake.build_doc_summaries çıktısı.
    Döner: [{alan, secilen_deger, gerekce}] — apply_arbitration'a gider.
    Çelişki yoksa ÇAĞRILMAMALIDIR (plan: hakem yalnız çelişkide koşar).
    Hata fırlatır — çağıran taraf hakemsiz (çoğunluk oyu) sonuca düşer.
    """
    config = genai_types.GenerateContentConfig(
        system_instruction=get_case_intake_arbiter_instruction(),
        response_mime_type="application/json",
        response_schema=CaseIntakeArbitration,
    )
    payload_text = json.dumps(
        {"celisen_alanlar": conflicts, "belgeler": doc_summaries},
        ensure_ascii=False, indent=2, default=str,
    )
    stats: Dict[str, Any] = {"retry_count": 0, "retry_wait_ms": 0}
    response = await analyzer._gemini_call_with_retry(
        config, [payload_text], stats=stats, model=get_intake_model()
    )
    # Faz 3-C: boş/kesik yanıt finish_reason kanıtıyla tipli hataya çevrilir
    text = analyzer._ensure_response_text(response, context="Hakem")
    return CaseIntakeArbitration.model_validate_json(text).model_dump()["kararlar"]


# =====================================================================
# Generator
# =====================================================================


def _extract_digital_text(file_path: str) -> Optional[str]:
    """Dijital metni çeker (regex ipuçları + çapraz kontrol için); OCR gerekiyorsa None."""
    needs_ocr, text = analyzer.is_scanned_pdf(file_path)
    return None if needs_ocr else text


def _fetch_prompt_context(extracted_text: Optional[str]) -> Dict[str, Optional[List[str]]]:
    """DB bağlamı: büro avukatları, FlashText müvekkil ipuçları, izinli yargı
    türleri, dava konuları ve uzmanlıklar.

    Her kaynak bağımsız try/except'lidir — bağlam eksikliği analizi durdurmaz
    (prompt varsayılanlarına düşülür).
    """
    lawyer_names = None
    client_hints = None
    yargi_turleri = None
    dava_konulari = None
    uzmanliklar = None
    doctypes: List[Dict] = []

    try:
        from managers.config_manager import DynamicConfig

        config = DynamicConfig.get_instance()
        lawyer_names = [
            lw.get("name") for lw in (config.get_lawyers() or []) if lw.get("name")
        ] or None
        doctypes = config.get_doctypes() or []
    except Exception as e:
        TechnicalLogger.log("WARNING", f"[INTAKE] Avukat/doctype listesi alınamadı: {e}")

    if extracted_text:
        try:
            from list_searcher import get_list_searcher

            client_hints = get_list_searcher().search(extracted_text) or None
        except Exception as e:
            TechnicalLogger.log("WARNING", f"[INTAKE] Müvekkil ipucu araması hatası: {e}")

    try:
        from managers.reference_lists import get_file_types

        yargi_turleri = [
            ft.get("name") or ft.get("code") for ft in (get_file_types() or [])
            if ft.get("name") or ft.get("code")
        ] or None
    except Exception as e:
        TechnicalLogger.log("WARNING", f"[INTAKE] Yargı türü listesi alınamadı: {e}")

    # Dava konusu + uzmanlık: kanonik listeler prompt'a enjekte edilir — model
    # YA listeden birebir seçer YA null bırakır (serbest metin istenmez).
    try:
        from managers.reference_lists import get_case_subjects, get_specialties

        dava_konulari = [
            s.get("name") for s in (get_case_subjects() or []) if s.get("name")
        ] or None
        uzmanliklar = [
            s.get("name") for s in (get_specialties() or []) if s.get("name")
        ] or None
    except Exception as e:
        TechnicalLogger.log("WARNING", f"[INTAKE] Konu/uzmanlık listesi alınamadı: {e}")

    return {
        "lawyer_names": lawyer_names,
        "client_hints": client_hints,
        "yargi_turleri": yargi_turleri,
        "dava_konulari": dava_konulari,
        "uzmanliklar": uzmanliklar,
        "doctypes": doctypes,
    }


async def analyze_intake_file_generator(
    file_path: str,
    file_hash: Optional[str] = None,
    process_id: Optional[str] = None,
    ensemble_n: Optional[int] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Dava açılış belgesini analiz eden generator.

    Yields: {"status": "info"/"warning"/"error"/"complete", ...}
    Terminal olay: {"status": "complete", "data": {...}, "full_pdf_path": "..."}
    (route full_pdf_path'i PROCESS_CACHE'e koyar ve olaya process_id ekler).

    process_id: verilirse dönüştürülmüş PDF silinmez (cache sahipliği route'a geçer).
    """
    benchmark: Dict[str, Any] = {}
    total_start = time.perf_counter()
    loop = asyncio.get_running_loop()
    n = ensemble_n or DEFAULT_ENSEMBLE_N
    intake_model = get_intake_model()

    if file_hash is None:
        file_hash = await loop.run_in_executor(None, analyzer.calculate_file_hash, file_path)

    if not analyzer.GOOGLE_API_KEY:
        yield {"status": "error", "message": "GEMINI_API_KEY tanımlı değil — analiz yapılamıyor."}
        return
    if not os.path.exists(file_path):
        yield {"status": "error", "message": "Dosya bulunamadı (işlem sırasında silinmiş olabilir)."}
        return

    # 1. PDF olmayan formatlar önce PDF'e çevrilir (analyzer adımları yeniden kullanılır).
    #    Adımlar hata halinde analyzer'ın default-data'lı "complete" olayını üretir —
    #    intake akışında bu olay hata olayına çevrilir.
    from pdf.format_converter import CONVERTIBLE_EXTENSIONS

    temp_converted_pdf = None
    file_ext = Path(file_path).suffix.lower()

    if file_ext == ".udf":
        state = {"file_path": file_path, "temp_pdf_from_udf": None, "failed": False}
        async for event in analyzer._step_udf_conversion(state, file_hash, benchmark, loop):
            if event.get("status") == "complete":
                msg = (event.get("data") or {}).get("ozet") or "UDF dönüşüm hatası"
                yield {"status": "error", "message": msg}
            else:
                yield event
        if state["failed"]:
            return
        file_path = state["file_path"]
        temp_converted_pdf = state["temp_pdf_from_udf"]
    elif file_ext in CONVERTIBLE_EXTENSIONS:
        state = {"file_path": file_path, "temp_converted_pdf": None, "failed": False}
        async for event in analyzer._step_format_conversion(state, file_hash, benchmark, loop):
            if event.get("status") == "complete":
                msg = (event.get("data") or {}).get("ozet") or "Dosya dönüşüm hatası"
                yield {"status": "error", "message": msg}
            else:
                yield event
        if state["failed"]:
            return
        file_path = state["file_path"]
        temp_converted_pdf = state["temp_converted_pdf"]

    # Sayfa kırpma YOK (karar 3) — belge tam gider; tam PDF cache'e de bu gider.
    full_pdf_path = file_path

    uploaded_file = None
    try:
        # 2. Dijital metin (regex ipuçları + çapraz kontrol için; OCR'lıysa atlanır).
        #    Metin çıkarılamaması analizi durdurmaz — belge Gemini'ye görsel gider.
        extracted_text = None
        t_text = time.perf_counter()
        try:
            # Tavanın evi config/settings.py (env: PDF_PARSE_TIMEOUT_SECONDS, Faz 5-A)
            extracted_text = await asyncio.wait_for(
                loop.run_in_executor(None, _extract_digital_text, file_path),
                timeout=settings.pdf_parse_timeout_seconds,
            )
        except asyncio.TimeoutError:
            TechnicalLogger.log(
                "WARNING",
                f"[INTAKE] PDF metin çıkarma timeout "
                f"({settings.pdf_parse_timeout_seconds:.0f}s): {file_path}",
            )
        except ValueError as e:
            # pdf_utils dosyayı reddetti (bozuk/şifreli) — /process ile tutarlı: fatal
            TechnicalLogger.log("ERROR", f"[INTAKE] PDF reddedildi: {e}")
            yield {"status": "error", "message": str(e)}
            return
        except Exception as e:
            TechnicalLogger.log("WARNING", f"[INTAKE] Metin çıkarma hatası (ipuçları atlanıyor): {e}")
        benchmark["text_extract_ms"] = round((time.perf_counter() - t_text) * 1000, 2)

        # 3. Prompt bağlamı (DB) + talimat
        t_ctx = time.perf_counter()
        ctx = await loop.run_in_executor(None, _fetch_prompt_context, extracted_text)
        hints = regex_prehints(extracted_text)
        instruction = get_case_intake_instruction(
            regex_hints=hints or None,
            lawyer_names=ctx["lawyer_names"],
            client_hints=ctx["client_hints"],
            yargi_turleri=ctx["yargi_turleri"],
            dava_konulari=ctx["dava_konulari"],
            uzmanliklar=ctx["uzmanliklar"],
        )
        benchmark["prompt_build_ms"] = round((time.perf_counter() - t_ctx) * 1000, 2)

        gen_config = genai_types.GenerateContentConfig(
            system_instruction=instruction,
            response_mime_type="application/json",
            response_schema=CaseIntakeExtraction,
        )

        # 4. Upload (tek sefer; N koşu aynı dosyayı kullanır)
        yield {"status": "info", "message": "📤 Belge yapay zekaya yükleniyor..."}
        t_up = time.perf_counter()
        uploaded_file = await loop.run_in_executor(None, analyzer.upload_to_gemini, full_pdf_path)
        await analyzer.wait_for_files_active([uploaded_file])
        benchmark["upload_ms"] = round((time.perf_counter() - t_up) * 1000, 2)

        # 5. Katman 1 — ensemble N koşu + çoğunluk oyu
        yield {
            "status": "info",
            "message": f"🧠 Belge çıkarımı başlıyor ({n} bağımsız koşu, ~25-30 sn)...",
        }
        ai_stats: Dict[str, Any] = {"retry_count": 0, "retry_wait_ms": 0}
        runs: List[Dict] = []
        durations: List[float] = []
        last_run_error: Optional[Exception] = None
        payload = [uploaded_file, "Bu belgeyi analiz et ve şemayı doldur."]
        for i in range(n):
            t_run = time.perf_counter()
            try:
                response = await analyzer._gemini_call_with_retry(
                    gen_config, payload, stats=ai_stats, model=intake_model
                )
                # Faz 3-C: boş/kesik yanıt finish_reason kanıtıyla tipli hata olur
                text = analyzer._ensure_response_text(response)
                runs.append(CaseIntakeExtraction.model_validate_json(text).model_dump())
                durations.append(round(time.perf_counter() - t_run, 1))
                yield {
                    "status": "info",
                    "message": f"✅ Çıkarım koşusu {i + 1}/{n} tamamlandı ({durations[-1]}s)",
                }
            except Exception as e:
                # Tek bozuk koşu (kaçak/kırpık JSON, filtre engeli) belgeyi öldürmesin —
                # atla, kalan koşularla oyla (Faz 0'da flash-lite'ta görüldü).
                last_run_error = e
                TechnicalLogger.log(
                    "WARNING",
                    f"[INTAKE] Koşu {i + 1}/{n} geçersiz ({e.__class__.__name__}): {e}",
                )
                yield {
                    "status": "warning",
                    "message": f"⚠️ Çıkarım koşusu {i + 1}/{n} geçersiz, kalan koşularla devam ediliyor...",
                }
        benchmark["ensemble_run_sec"] = durations
        benchmark["retry_count"] = ai_stats["retry_count"]
        benchmark["retry_wait_ms"] = round(ai_stats["retry_wait_ms"], 2)

        if not runs:
            # Nihai başarısızlık → log sözleşmesi gereği tek ERROR (koşu
            # başına WARNING'ler yukarıda düştü). Devre kesici hızlı-fail'i
            # kullanıcıya gerçek nedeniyle yansıtılır.
            TechnicalLogger.log(
                "ERROR",
                "[INTAKE] Tüm çıkarım koşuları geçersiz — analiz başarısız",
                {"file": file_path, "runs_requested": n},
            )
            if isinstance(last_run_error, gemini_client.GeminiCircuitOpenError):
                message = (
                    "⚠️ Yapay zeka servisi art arda hata verdiği için kısa "
                    "süreliğine devre dışı bırakıldı (koruma devrede). "
                    "Lütfen 1 dakika sonra tekrar deneyin."
                )
            else:
                message = "Belge analizi başarısız: tüm çıkarım koşuları geçersiz sonuç döndürdü."
            yield {"status": "error", "message": message}
            return

        merged, parties = majority_vote(runs)

        # 6. Katman 2 — kritik alan doğrulayıcı geçişi (esas_no, tc_no, taraf rolleri)
        claims = build_critical_claims(merged, parties)
        verification: Dict[str, Dict] = {}
        if claims:
            yield {"status": "info", "message": "🛡️ Kritik alanlar belgeye karşı doğrulanıyor..."}
            t_ver = time.perf_counter()
            try:
                verify_config = genai_types.GenerateContentConfig(
                    system_instruction=get_case_intake_verifier_instruction(),
                    response_mime_type="application/json",
                    response_schema=CaseIntakeVerification,
                )
                claims_text = (
                    "Doğrulanacak iddialar:\n"
                    + json.dumps(claims, ensure_ascii=False, indent=2)
                )
                v_response = await analyzer._gemini_call_with_retry(
                    verify_config, [uploaded_file, claims_text],
                    stats=ai_stats, model=intake_model,
                )
                v_text = analyzer._ensure_response_text(v_response, context="Doğrulayıcı")
                kontroller = CaseIntakeVerification.model_validate_json(
                    v_text
                ).model_dump()["kontroller"]
                verification = apply_verification(claims, kontroller)
            except Exception as e:
                # Doğrulayıcı hatası analizi düşürmez — iddialar "bilinmiyor" kalır
                TechnicalLogger.log("WARNING", f"[INTAKE] Doğrulayıcı geçişi hatası: {e}")
                verification = apply_verification(claims, [])
            benchmark["verify_ms"] = round((time.perf_counter() - t_ver) * 1000, 2)

        # 7. Sonuç birleştirme
        data: Dict[str, Any] = {f: merged[f]["value"] for f in SCALAR_FIELDS}
        data["ozet"] = pick_ozet(runs)
        data["taraflar"] = parties
        data["belge_turu_kodu_tahmini"] = guess_doctype_code(
            merged["belge_turu_tahmini"]["value"], ctx["doctypes"]
        )
        data["agreement"] = {f: merged[f]["agreement"] for f in SCALAR_FIELDS}
        # Anlaşmasız alanların oy dağılımı — sihirbaz rozet/tooltip'i için
        data["vote_candidates"] = {
            f: merged[f]["candidates"] for f in SCALAR_FIELDS if merged[f]["agreement"] < 1.0
        }
        data["verification"] = verification
        data["regex_check"] = regex_crosscheck(merged, extracted_text)
        data["ensemble"] = {"runs_requested": n, "runs_valid": len(runs)}
        data["hash"] = file_hash
        benchmark["model"] = intake_model
        benchmark["total_ms"] = round((time.perf_counter() - total_start) * 1000, 2)
        data["_benchmark"] = benchmark

        TechnicalLogger.log(
            "INFO",
            "[INTAKE] Analiz tamamlandı",
            {
                "file": file_path,
                "runs_valid": len(runs),
                "belge_turu": data.get("belge_turu_tahmini"),
                "esas_no": data.get("esas_no"),
            },
        )
        yield {"status": "complete", "data": data, "full_pdf_path": full_pdf_path}

    except Exception as e:
        import uuid as _uuid

        error_id = str(_uuid.uuid4())[:8]
        TechnicalLogger.log(
            "ERROR", f"[INTAKE] Analiz hatası [ErrorID: {error_id}]: {e}", {"file": file_path}
        )
        yield {"status": "error", "message": analyzer._api_error_ozet(e, error_id)}
    finally:
        # Gemini'deki dosya her durumda silinir
        if uploaded_file is not None:
            try:
                client = analyzer.get_gemini_client(analyzer.GOOGLE_API_KEY)
                if client:
                    client.files.delete(name=uploaded_file.name)
            except Exception as e:
                TechnicalLogger.log("WARNING", f"[INTAKE] Gemini dosyası silinemedi: {e}")
        # Dönüştürülmüş PDF: process_id verildiyse PROCESS_CACHE sahipliğinde —
        # TTL temizliği siler; verilmediyse burada silinir.
        if temp_converted_pdf and os.path.exists(temp_converted_pdf):
            if process_id:
                TechnicalLogger.log(
                    "INFO",
                    f"[INTAKE] Dönüştürülmüş PDF cache'te bırakıldı (process_id={process_id}): {temp_converted_pdf}",
                )
            else:
                try:
                    os.remove(temp_converted_pdf)
                except Exception as e:
                    TechnicalLogger.log("WARNING", f"[INTAKE] Geçici PDF silinemedi: {e}")
