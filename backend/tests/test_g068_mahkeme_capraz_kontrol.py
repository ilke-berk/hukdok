"""G068: analiz hattında mahkeme adı — güven kilidi + LLM çapraz kontrolü.

Kilitlenen davranışlar:
  1. Ön çıkarım kilidi (`ÖN ÇIKARIM BİLGİSİ (Zaten bulundu, DEĞİŞTİRME)`) YALNIZ
     `guven=TAM` okumada kurulur; KISMI/YOK'ta alan `missing_fields`te kalır ve
     prompt'a kilit değil İPUCU olarak girer.
  2. LLM'in mahkeme adı da G067 kapısından geçer: tür doğrulanamıyorsa değer
     sisteme YAZILMAZ.
  3. İki okuma varsa yapısal kimlikler (yer · sıra · tür · daire) karşılaştırılır;
     çelişen bileşen BOŞ bırakılır — sessizce biri seçilmez (basamak koruması).
  4. Uyuşmazlık WARNING'dir: `failed` olayı üretilmez, ERROR basılmaz.
  5. Analiz sonucu JSON şeması genişlemez (`mahkeme_guven` YOK) — damga iç
     sözleşme ve logda kalır.

conftest sözleşmesi gereği ağa/DB'ye çıkılmaz; Gemini adımı monkeypatch'lenir.
"""
import asyncio
import json
import os
from typing import Any, Dict, List

import pytest

os.environ.setdefault("GEMINI_MODEL_NAME", "models/test-flash")

import analyzer
from extractors.court_extractor import _config_listeleri
from prompts import get_system_instruction
from services.court_name import GUVEN_KISMI, GUVEN_TAM, GUVEN_YOK, parse_court_name

_YERLER, _TURLER = _config_listeleri()


def _kimlik(metin: str):
    """Test kolaylığı: G067 kapısını üretim listeleriyle çalıştırır."""
    return parse_court_name(metin, yerler=_YERLER, turler=_TURLER)


def _pre(metin: str | None = None, **kw: Any) -> Dict[str, Any]:
    """`analyze_file_generator`'ın kurduğu pre_extracted sözlüğünün eşleniği."""
    kimlik = _kimlik(metin) if metin else None
    pre: Dict[str, Any] = {
        "tarih": None,
        "esas_no": None,
        "muvekkil_candidates": [],
        "court": kimlik.duz_ad() if kimlik is not None else None,
        "court_identity": kimlik,
        "court_guven": kimlik.guven if kimlik is not None else None,
        "sonraki_durusma_tarihi": None,
        "sonraki_durusma_saati": None,
    }
    pre.update(kw)
    return pre


class _KayitliLogger:
    """TechnicalLogger ikizi — seviye/mesaj çiftlerini toplar."""

    def __init__(self) -> None:
        self.kayitlar: List[tuple] = []

    def log(self, level: str, message: str, *args: Any, **kwargs: Any) -> None:
        self.kayitlar.append((level, message))

    def seviyeler(self) -> List[str]:
        return [lv for lv, _ in self.kayitlar]


@pytest.fixture()
def kayitli_log(monkeypatch):
    sahte = _KayitliLogger()
    monkeypatch.setattr(analyzer, "TechnicalLogger", sahte)
    return sahte


# ── Ön koşul: kapının bu testlerdeki girdileri beklenen damgayı üretiyor ─────


def test_test_girdileri_beklenen_guven_damgasini_uretir():
    assert _kimlik("ANKARA 3. ASLİYE HUKUK MAHKEMESİ").guven == GUVEN_TAM
    assert _kimlik("YARGITAY 11. HUKUK DAİRESİ").guven == GUVEN_KISMI
    assert _kimlik("ZZZTEPE 1. ASLİYE HUKUK MAHKEMESİ").guven == GUVEN_KISMI
    assert _kimlik("ANKARA 1. BASIN MAHKEMESİ").guven == GUVEN_YOK


def test_on_cikarim_guven_damgasini_doldurur():
    """Ön çıkarım düz adın YANINDA yapısal kimliği + damgayı da yazar."""
    pre = _pre()
    pre.update({"court": None, "court_identity": None, "court_guven": None})
    metin = "T.C.\nANKARA 3. ASLİYE HUKUK MAHKEMESİ\nGEREKÇELİ KARAR\nESAS NO: 2026/123\n"
    analyzer._pre_extract_fields(pre, metin, None)
    assert pre["court"] == "ANKARA 3. ASLİYE HUKUK MAHKEMESİ"
    assert pre["court_guven"] == GUVEN_TAM
    assert pre["court_identity"] is not None
    assert pre["court_identity"].daire_no is None


# ── 1. Kilit güvene bağlandı (missing_fields) ───────────────────────────────


def test_tam_guvende_kilit_kurulur_alan_llme_sorulmaz():
    missing = analyzer._detect_missing_fields(_pre("ANKARA 3. ASLİYE HUKUK MAHKEMESİ"))
    assert "court" not in missing
    assert analyzer._court_kilitli(_pre("ANKARA 3. ASLİYE HUKUK MAHKEMESİ")) is True


def test_kismi_guvende_alan_missing_fieldste_kalir():
    pre = _pre("YARGITAY 11. HUKUK DAİRESİ")
    assert pre["court_guven"] == GUVEN_KISMI
    assert "court" in analyzer._detect_missing_fields(pre)
    assert analyzer._court_kilitli(pre) is False


def test_yok_guvende_alan_missing_fieldste_kalir():
    pre = _pre("ANKARA 1. BASIN MAHKEMESİ")
    assert pre["court_guven"] == GUVEN_YOK
    assert "court" in analyzer._detect_missing_fields(pre)


def test_okuma_yoksa_alan_missing_fieldste():
    assert "court" in analyzer._detect_missing_fields(_pre())


def test_diger_alanlarin_kilit_mantigi_degismedi():
    """Yalnız `court` farklılaştı: tarih/esas_no/müvekkil "bulundu = kilit"."""
    pre = _pre(
        "ANKARA 3. ASLİYE HUKUK MAHKEMESİ",
        tarih="2026-08-19",
        esas_no="2026/123",
        muvekkil_candidates=["AYŞE YILMAZ"],
    )
    assert analyzer._detect_missing_fields(pre) == []

    # Güven damgası KISMI olunca SADECE court listeye döner
    pre_kismi = _pre(
        "YARGITAY 11. HUKUK DAİRESİ",
        tarih="2026-08-19",
        esas_no="2026/123",
        muvekkil_candidates=["AYŞE YILMAZ"],
    )
    assert analyzer._detect_missing_fields(pre_kismi) == ["court"]

    # Diğer alanların yokluğu bugünkü sırayla listelenir
    assert analyzer._detect_missing_fields(_pre()) == ["tarih", "esas_no", "muvekkil", "court"]


# ── 2. Prompt: kilit vs ipucu ───────────────────────────────────────────────


def test_kilitli_mahkeme_degistirme_blogunda_verilir():
    pre = _pre("ANKARA 3. ASLİYE HUKUK MAHKEMESİ")
    sys_inst = get_system_instruction(missing_fields=["tarih"], pre_extracted=pre)
    assert "DEĞİŞTİRME" in sys_inst
    assert "Mahkeme: ANKARA 3. ASLİYE HUKUK MAHKEMESİ" in sys_inst


def test_kilitsiz_mahkemede_degistirme_ifadesi_yer_almaz():
    """KISMI okuma tek başına promptta hiçbir 'DEĞİŞTİRME' ifadesi doğurmaz."""
    pre = _pre("YARGITAY 11. HUKUK DAİRESİ")
    sys_inst = get_system_instruction(missing_fields=["court"], pre_extracted=pre)
    assert "DEĞİŞTİRME" not in sys_inst
    assert "ÖN OKUMA (regex, DOĞRULANMAMIŞ)" in sys_inst
    assert "YARGITAY 11. HUKUK DAİRESİ" in sys_inst
    assert "kilit DEĞİL" in sys_inst


def test_kilitsiz_mahkeme_degistirme_blogunun_disinda_kalir():
    """Başka alanlar kilitliyken bile mahkeme o bloğa GİRMEZ."""
    pre = _pre("YARGITAY 11. HUKUK DAİRESİ", tarih="2026-08-19")
    sys_inst = get_system_instruction(missing_fields=["court"], pre_extracted=pre)
    assert "DEĞİŞTİRME" in sys_inst  # tarih kilidi duruyor
    blok = sys_inst.split("ÖN ÇIKARIM BİLGİSİ", 1)[1].split("</critical_ops>", 1)[0]
    assert "Mahkeme:" not in blok
    assert "Tarih: 2026-08-19" in blok


def test_kilitli_mahkemede_ipucu_metni_kullanilmaz():
    pre = _pre("ANKARA 3. ASLİYE HUKUK MAHKEMESİ")
    sys_inst = get_system_instruction(missing_fields=["tarih"], pre_extracted=pre)
    assert "ÖN OKUMA (regex, DOĞRULANMAMIŞ)" not in sys_inst


# ── 3. Çözümleme: kapı + çapraz kontrol ─────────────────────────────────────


def test_kilitte_llm_ciktisi_regexi_ezmez(kayitli_log):
    """TAM güvende davranış bugünküyle aynı: regex yazılır, çapraz kontrol yok."""
    data = {"court": "İSTANBUL ANADOLU 17. ASLİYE TİCARET MAHKEMESİ"}
    uyarilar = analyzer._resolve_court(data, _pre("ANKARA 3. ASLİYE HUKUK MAHKEMESİ"), [])
    assert data["court"] == "ANKARA 3. ASLİYE HUKUK MAHKEMESİ"
    assert uyarilar == []
    assert kayitli_log.seviyeler() == []


def test_llm_taninmayan_tur_sisteme_yazilmaz(kayitli_log):
    data = {"court": "ANKARA 5. ŞURA MAHKEMESİ"}
    uyarilar = analyzer._resolve_court(data, _pre(), [])
    assert data["court"] == ""
    assert uyarilar == []
    assert "WARNING" in kayitli_log.seviyeler()
    assert "ERROR" not in kayitli_log.seviyeler()


def test_llm_tek_kaynaksa_kapidan_gecen_deger_yazilir():
    data = {"court": "Manavgat 1. Asliye Hukuk Mahkemesi"}
    uyarilar = analyzer._resolve_court(data, _pre(), [])
    assert data["court"] == "MANAVGAT 1. ASLİYE HUKUK MAHKEMESİ"
    assert uyarilar == []


def test_iki_okuma_uyusursa_deger_yazilir(kayitli_log):
    data = {"court": "ZZZTEPE 1. Asliye Hukuk Mahkemesi"}
    uyarilar = analyzer._resolve_court(data, _pre("ZZZTEPE 1. ASLİYE HUKUK MAHKEMESİ"), [])
    assert data["court"] == "1. ASLİYE HUKUK MAHKEMESİ"
    assert uyarilar == []
    assert kayitli_log.seviyeler() == []


def test_daire_no_catismasinda_sessizce_biri_secilmez(kayitli_log):
    """Ekibin E maddesi: 11 vs 1 — basamak koruması, ikisi de yazılmaz."""
    data = {"court": "YARGITAY 1. HUKUK DAİRESİ"}
    uyarilar = analyzer._resolve_court(data, _pre("YARGITAY 11. HUKUK DAİRESİ"), [])
    assert data["court"] == "YARGITAY"
    assert "11" not in data["court"] and "1." not in data["court"]
    assert len(uyarilar) == 1 and "daire no" in uyarilar[0]
    assert "WARNING" in kayitli_log.seviyeler()
    assert "ERROR" not in kayitli_log.seviyeler()


def test_yer_catismasinda_yer_bos_kalir_govde_yazilir():
    """Ekibin A maddesi: AĞRI vs IĞDIR — ortak bileşenler yazılır, yer düşer.

    NOT: bu dal bugün üretimde yalnız kilit devre dışıyken görünür (yer okunmuş
    bir regex sonucu tanımı gereği TAM'dır ve kilitlenir); karşılaştırıcı yine de
    bileşen bazında tekdüze çalışır — birim düzeyinde kilitlenir.
    """
    ad, catisma = analyzer._court_capraz_kontrol(
        _kimlik("AĞRI 1. ASLİYE HUKUK MAHKEMESİ"),
        _kimlik("IĞDIR 1. ASLİYE HUKUK MAHKEMESİ"),
    )
    assert ad == "1. ASLİYE HUKUK MAHKEMESİ"
    assert catisma == ["yer"]


def test_tur_catismasinda_hicbir_deger_yazilmaz():
    """Tür gövdedir: çelişince '1.' gibi yarım ad ÜRETİLMEZ."""
    data = {"court": "ZZZTEPE 1. ASLİYE TİCARET MAHKEMESİ"}
    uyarilar = analyzer._resolve_court(data, _pre("ZZZTEPE 1. ASLİYE HUKUK MAHKEMESİ"), [])
    assert data["court"] == ""
    assert len(uyarilar) == 1 and "tür" in uyarilar[0]


def test_bir_okumanin_susmasi_catisma_degildir(kayitli_log):
    """Yokluk karşıt iddia değildir: dairesiz okuma daireyi düşürmez."""
    data = {"court": "YARGITAY 11. HUKUK DAİRESİ"}
    uyarilar = analyzer._resolve_court(data, _pre("YARGITAY"), [])
    assert data["court"] == "YARGITAY 11. HUKUK DAİRESİ"
    assert uyarilar == []
    assert "WARNING" not in kayitli_log.seviyeler()


def test_iki_okuma_da_kapidan_gecmezse_regex_yuzeyi_kalir():
    """Regex yüzeyi belgeden KOPYALANMIŞTIR — LLM üretimi gibi atılmaz."""
    data = {"court": "ANKARA 5. ŞURA MAHKEMESİ"}
    uyarilar = analyzer._resolve_court(data, _pre("ANKARA 1. BASIN MAHKEMESİ"), [])
    assert data["court"] == "ANKARA 1. BASIN MAHKEMESİ"
    assert uyarilar == []


def test_hicbir_okuma_yoksa_alan_bos():
    data = {"court": None}
    assert analyzer._resolve_court(data, _pre(), []) == []
    assert data["court"] == ""


def test_tarih_ve_esas_no_cozumu_degismedi():
    data = {"tarih": "1999-01-01", "esas_no": "1999/1", "court": None}
    pre = _pre(tarih="2026-08-19", esas_no="2026/123")
    uyarilar = analyzer._resolve_tarih_esas_court(data, pre, [])
    assert data["tarih"] == "2026-08-19"
    assert data["esas_no"] == "2026/123"
    assert uyarilar == []

    # Regex susarsa LLM değeri korunur (bugünkü davranış)
    data2 = {"tarih": "2026-01-02", "esas_no": "2026/9", "court": None}
    analyzer._resolve_tarih_esas_court(data2, _pre(), [])
    assert data2["tarih"] == "2026-01-02"
    assert data2["esas_no"] == "2026/9"


# ── 4. Sonuç JSON şeması genişlemedi ────────────────────────────────────────


def test_sonuc_semasina_yeni_alan_eklenmedi():
    from schemas_process import ProcessAnalysisOutput

    assert "mahkeme_guven" not in ProcessAnalysisOutput.model_fields
    assert "court_guven" not in ProcessAnalysisOutput.model_fields
    assert "court_identity" not in ProcessAnalysisOutput.model_fields
    assert "court" in ProcessAnalysisOutput.model_fields


def test_cozumleme_data_sozlugune_yeni_anahtar_eklemez():
    data: Dict[str, Any] = {"court": "YARGITAY 1. HUKUK DAİRESİ", "ozet": "x"}
    once = set(data)
    analyzer._resolve_court(data, _pre("YARGITAY 11. HUKUK DAİRESİ"), [])
    assert set(data) == once


def test_prompt_cikti_semasi_genislemedi():
    sys_inst = get_system_instruction(
        missing_fields=["court"], pre_extracted=_pre("YARGITAY 11. HUKUK DAİRESİ")
    )
    assert "mahkeme_guven" not in sys_inst
    assert '"court": "String | null"' in sys_inst


# ── 5. Akış sözleşmesi: warning evet, failed hayır ──────────────────────────


def _drive(file_path: str, **kwargs: Any) -> List[Dict[str, Any]]:
    async def _run():
        return [event async for event in analyzer.analyze_file_generator(file_path, **kwargs)]

    return asyncio.run(_run())


@pytest.fixture()
def sahte_akis(monkeypatch, tmp_path):
    """Gemini'ye çıkmadan uçtan uca akış: LLM cevabı testten verilir."""
    monkeypatch.setattr(analyzer, "GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(analyzer, "is_scanned_pdf", lambda path: (False, "M" * 200))
    monkeypatch.setattr(analyzer.pdf_utils, "extract_key_pages", lambda path: path)
    monkeypatch.setattr(analyzer, "_record_token_usage", lambda response, benchmark: None)

    async def _sahte_ai(state, *args, **kwargs):
        state["response"] = {"sahte": True}
        for event in ():
            yield event

    monkeypatch.setattr(analyzer, "_step_ai_call", _sahte_ai)

    def _kur(regex_metin: str | None, ai_court: str | None) -> List[Dict[str, Any]]:
        def _sahte_pre(pre_extracted, extracted_text, preset_belge_turu_kodu):
            pre_extracted.update(
                {k: v for k, v in _pre(regex_metin).items() if k.startswith("court")}
            )

        monkeypatch.setattr(analyzer, "_pre_extract_fields", _sahte_pre)
        cevap = json.dumps(
            {
                "tarih": "2026-08-19",
                "muvekkil_adi": None,
                "muvekkiller": [],
                "belgede_gecen_isimler": [],
                "esas_no": "2026/123",
                "court": ai_court,
                "durum": "G",
                "ozet": "Test özeti",
            }
        )
        monkeypatch.setattr(analyzer, "_ensure_response_text", lambda response: cevap)
        pdf = tmp_path / "belge.pdf"
        pdf.write_bytes(b"%PDF-1.4\ntest\n")
        return _drive(str(pdf))

    return _kur


def test_uyusmazlik_warning_olayi_uretir_failed_uretmez(sahte_akis):
    events = sahte_akis("YARGITAY 11. HUKUK DAİRESİ", "YARGITAY 1. HUKUK DAİRESİ")
    durumlar = [e["status"] for e in events]
    assert "failed" not in durumlar and "error" not in durumlar
    assert durumlar[-1] == "complete"
    uyarilar = [e for e in events if e["status"] == "warning"]
    assert len(uyarilar) == 1 and "daire no" in uyarilar[0]["message"]
    assert events[-1]["data"]["court"] == "YARGITAY"


def test_uyusan_okumada_warning_olayi_yok(sahte_akis):
    events = sahte_akis("YARGITAY 11. HUKUK DAİRESİ", "Yargıtay 11. Hukuk Dairesi")
    assert [e for e in events if e["status"] == "warning"] == []
    assert events[-1]["status"] == "complete"
    assert events[-1]["data"]["court"] == "YARGITAY 11. HUKUK DAİRESİ"
