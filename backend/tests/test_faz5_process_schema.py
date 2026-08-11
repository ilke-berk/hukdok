"""Faz 5-B (G003, plan 5.4): /process LLM çıktısına Pydantic şeması.

Kilitlenen davranışlar:
  1. Toleranslı normalizasyon — meşru ama gevşek çıktı REDDEDİLMEZ (yanlış
     pozitif = kullanıcı verisinin çöpe gitmesi).
  2. Yapısal bozukluk reddedilir ve G001'in terminal olayına `schema_invalid`
     etiketiyle döner.
  3. Alan haritası korunur: doğrulama çıktıya YENİ anahtar eklemez, mevcut
     anahtarları düşürmez (post-processing ve frontend aynı sözlüğü görür).
  4. Log sözleşmesi: şema reddi TEK ERROR üretir (deneme-düzeyi log yok).
"""
import asyncio
import logging
import os
from typing import Any, Dict, List

import pytest

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

import analyzer  # noqa: E402
from schemas_process import (  # noqa: E402
    ProcessAnalysisOutput,
    ProcessSchemaError,
    validate_process_output,
)


# ── Toleranslı normalizasyon: meşru çıktı geçmeli ───────────────────────────


def test_typical_llm_output_passes_unchanged():
    raw = {
        "tarih": "2026-08-11",
        "muvekkil_adi": "Ahmet Yılmaz",
        "muvekkiller": ["Ahmet Yılmaz"],
        "belgede_gecen_isimler": ["Mehmet Demir"],
        "esas_no": "2026/123",
        "court": "İstanbul 5. Asliye Hukuk Mahkemesi",
        "durum": "G",
        "ozet": "Kısa özet.",
    }
    assert validate_process_output(raw) == raw


def test_missing_fields_are_not_added():
    """Alan haritası: şemada olan ama çıktıda olmayan alan EKLENMEZ."""
    out = validate_process_output({"ozet": "sadece özet"})
    assert out == {"ozet": "sadece özet"}
    assert "sonraki_durusma_tarihi" not in out


def test_key_order_and_extra_fields_preserved():
    raw = {"ozet": "x", "yeni_alan": {"derin": 1}, "tarih": None}
    out = validate_process_output(raw)
    assert list(out) == ["ozet", "yeni_alan", "tarih"]
    # Bilinmeyen alan aynen korunur (prompt yeni alan isteyince şema yutmasın)
    assert out["yeni_alan"] == {"derin": 1}


def test_nulls_are_tolerated():
    raw = {"tarih": None, "esas_no": None, "court": None, "muvekkil_adi": None}
    assert validate_process_output(raw) == raw


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"esas_no": 2024}, {"esas_no": "2024"}),                    # sayı → metin
        ({"muvekkiller": None}, {"muvekkiller": []}),                # null liste → []
        ({"muvekkiller": "Ahmet Yılmaz"}, {"muvekkiller": ["Ahmet Yılmaz"]}),  # tekil → liste
        ({"belgede_gecen_isimler": ["A", None, "  "]}, {"belgede_gecen_isimler": ["A"]}),
        ({"muvekkiller": []}, {"muvekkiller": []}),
    ],
)
def test_loose_but_legitimate_shapes_are_normalized(raw, expected):
    assert validate_process_output(raw) == expected


# ── Yapısal bozukluk: reddedilmeli ──────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        [{"ozet": "liste kök"}],            # kökte JSON nesnesi değil
        "düz metin",
        42,
        {"muvekkiller": {"ad": "Ahmet"}},   # liste beklenen yerde sözlük
        {"belgede_gecen_isimler": [{"ad": "Ahmet"}]},   # liste öğesi nesne
        {"court": {"ad": "Mahkeme"}},       # skaler beklenen yerde sözlük
        {"ozet": ["a", "b"]},               # skaler beklenen yerde liste
    ],
)
def test_structurally_broken_output_is_rejected(raw):
    with pytest.raises(ProcessSchemaError):
        validate_process_output(raw)


def test_rejection_message_has_no_raw_content():
    """Log'a giden mesaj alan adı + sebep taşır, ham LLM metnini DEĞİL (KVKK)."""
    with pytest.raises(ProcessSchemaError) as exc:
        validate_process_output({"court": {"gizli": "Ahmet Yılmaz TC 12345678901"}})
    assert "court" in str(exc.value)
    assert "12345678901" not in str(exc.value)


def test_schema_error_is_not_a_valueerror():
    """analyze_file_generator'ın JSONDecodeError/ValueError handler'larına
    düşerse yanlış etiketle (analysis_error) raporlanırdı."""
    assert not issubclass(ProcessSchemaError, ValueError)


def test_model_declares_prompt_contract_fields():
    """prompts.py <output_schema> alanları şemada tanımlı olmalı."""
    for field in ("tarih", "muvekkil_adi", "muvekkiller", "belgede_gecen_isimler",
                  "esas_no", "court", "durum", "ozet",
                  "sonraki_durusma_tarihi", "sonraki_durusma_saati"):
        assert field in ProcessAnalysisOutput.model_fields


# ── analyze_file_generator entegrasyonu ─────────────────────────────────────


@pytest.fixture()
def gemini_text(monkeypatch, tmp_path):
    """Akışı Gemini'nin HAM METNİNİ seçebileceğimiz noktaya kadar kurar."""
    monkeypatch.setattr(analyzer, "GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(analyzer, "is_scanned_pdf", lambda path: (False, "kisa"))
    monkeypatch.setattr(analyzer.pdf_utils, "extract_key_pages", lambda path: path)
    monkeypatch.setattr(analyzer, "_build_prompt_and_config", lambda *a, **kw: (None, []))
    monkeypatch.setattr(analyzer, "_record_token_usage", lambda *a, **kw: None)

    pdf = tmp_path / "belge.pdf"
    pdf.write_bytes(b"%PDF-1.4\ntest\n")

    def _drive(raw_text: str) -> List[Dict[str, Any]]:
        async def fake_ai_call(ai_state, *args, **kwargs):
            ai_state["response"] = object()
            if False:      # pragma: no cover — async generator olmalı
                yield {}

        monkeypatch.setattr(analyzer, "_step_ai_call", fake_ai_call)
        monkeypatch.setattr(analyzer, "_ensure_response_text", lambda response: raw_text)

        async def _run():
            return [e async for e in analyzer.analyze_file_generator(str(pdf))]

        return asyncio.run(_run())

    return _drive


def test_broken_structure_yields_failed_schema_invalid(gemini_text):
    events = gemini_text('{"muvekkiller": {"ad": "Ahmet"}, "ozet": "x"}')
    assert [e for e in events if e["status"] == "complete"] == []
    final = events[-1]
    # G001 sözleşmesi birebir: üç alan, process_id/data YOK
    assert set(final) == {"status", "error_ozet", "error_kod"}
    assert final["status"] == "failed"
    assert final["error_kod"] == "schema_invalid"
    assert "beklenen yapıda değil" in final["error_ozet"]


def test_root_level_list_yields_failed_schema_invalid(gemini_text):
    # Kökte dizi: ayrıştırılabilir, ama sözlük değil → post-processing'de
    # `data["hash"] = ...` üzerinde patlardı (etiketi analysis_error olurdu).
    events = gemini_text('["Ahmet Yılmaz", "Mehmet Demir"]')
    assert events[-1]["error_kod"] == "schema_invalid"


def test_valid_output_still_completes_with_field_map(gemini_text):
    events = gemini_text(
        '{"tarih": "2026-08-11", "esas_no": "2026/123", "court": "İstanbul 5. AHM", '
        '"muvekkiller": [], "belgede_gecen_isimler": [], "durum": "G", "ozet": "özet"}'
    )
    final = events[-1]
    assert final["status"] == "complete"
    data = final["data"]
    # Mevcut alan haritası korundu (şema hiçbir alanı düşürmedi)
    for field in ("tarih", "esas_no", "court", "durum", "ozet", "hash",
                  "belge_turu_kodu", "suggested_karsi_taraf", "karsi_taraf", "_benchmark"):
        assert field in data
    assert data["esas_no"] == "2026/123"


def test_loose_output_completes_after_normalization(gemini_text):
    """Tekil metin gelen liste alanı reddedilmez, normalize edilip akar."""
    events = gemini_text('{"muvekkiller": "Ahmet Yılmaz", "ozet": "özet", "esas_no": 2026}')
    final = events[-1]
    assert final["status"] == "complete"
    assert final["data"]["esas_no"] == "2026"


def test_schema_rejection_logs_exactly_one_error(gemini_text, caplog):
    with caplog.at_level(logging.ERROR):
        events = gemini_text('{"court": {"ad": "x"}}')
    assert events[-1]["error_kod"] == "schema_invalid"
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert "şema doğrulaması" in errors[0].getMessage()


def test_failed_event_docstring_lists_schema_invalid():
    """Sözleşme docstring'i (frontend'le ortak referans) yeni etiketi içerir."""
    assert "schema_invalid" in (analyzer._failed_event.__doc__ or "")
