"""/process (belge analizi) LLM çıktısının şeması (Faz 5-B, plan 5.4).

intake yolu (`schemas_intake.CaseIntakeExtraction`) çıktısını Pydantic ile
doğruluyordu; /process yolu doğrulamıyordu → yapısı bozuk bir yanıt
(`muvekkiller: {...}`, `court: [...]`, kök seviyede liste) post-processing'de
patlıyor ya da sessizce yutuluyordu. Artık bozuk yapı G001'in terminal
`failed` olayına (`error_kod="schema_invalid"`) çevrilir.

TASARIM: şema BİLEREK toleranslıdır. Amaç meşru ama gevşek çıktıyı reddetmek
DEĞİL, yapısal olarak bozuk çıktıyı yakalamaktır — yanlış pozitif kullanıcıya
"analiz başarısız" der ve gerçek veriyi çöpe atar. Bu yüzden:

  * tüm alanlar Optional / varsayılanlı (LLM alan atlayabilir),
  * skaler alanda sayı gelirse metne çevrilir ("2024" ↔ 2024),
  * liste alanında tek metin gelirse tek elemanlı listeye sarılır, null gelirse
    boş listeye düşer, boş/None öğeler elenir,
  * bilinmeyen alanlar KORUNUR (`extra="allow"`) — prompt yeni alan isteyince
    şema onu yutmamalı.

Reddedilen tek şey yapısal karışıklıktır: kök seviyede sözlük olmayan çıktı,
skaler beklenen yerde sözlük/liste, liste beklenen yerde sözlük.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


class ProcessSchemaError(Exception):
    """LLM çıktısı /process şemasına uymuyor (nihai başarısızlık → schema_invalid).

    BİLEREK `ValueError` alt sınıfı DEĞİL: `analyze_file_generator`'ın handler
    zincirinde `json.JSONDecodeError`/`ValueError` yakalayıcıları var; şema
    reddi onlara düşerse yanlış etiketle (`analysis_error`) raporlanır.
    """


# Şemanın kapsadığı alanlar prompts.py'deki <output_schema> ile aynı hizada
# tutulur; oraya alan eklenince buraya da eklenmeli (aksi halde alan `extra`
# olarak korunur ama tip normalizasyonu almaz).
def _as_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    # bool hariç sayılar metne çevrilir (LLM "2024" yerine 2024 yazabiliyor)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise ValueError("metin bekleniyordu")


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, (list, tuple)):
        raise ValueError("liste bekleniyordu")
    items: List[str] = []
    for item in value:
        if item is None:
            continue
        if isinstance(item, str):
            if item.strip():
                items.append(item)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            items.append(str(item))
        else:
            raise ValueError("liste öğeleri metin olmalı")
    return items


class ProcessAnalysisOutput(BaseModel):
    """Belge analizi LLM çıktısı — toleranslı doğrulama + tip normalizasyonu."""

    model_config = ConfigDict(extra="allow")

    tarih: Optional[str] = None
    muvekkil_adi: Optional[str] = None
    muvekkiller: List[str] = []
    belgede_gecen_isimler: List[str] = []
    esas_no: Optional[str] = None
    court: Optional[str] = None
    durum: Optional[str] = None
    ozet: Optional[str] = None
    karsi_taraf: Optional[str] = None
    avukat_kodu: Optional[str] = None
    belge_kaynagi: Optional[str] = None
    belge_turu_kodu: Optional[str] = None
    sonraki_durusma_tarihi: Optional[str] = None
    sonraki_durusma_saati: Optional[str] = None

    @field_validator(
        "tarih", "muvekkil_adi", "esas_no", "court", "durum", "ozet",
        "karsi_taraf", "avukat_kodu", "belge_kaynagi", "belge_turu_kodu",
        "sonraki_durusma_tarihi", "sonraki_durusma_saati",
        mode="before",
    )
    @classmethod
    def _normalize_scalar(cls, value: Any) -> Optional[str]:
        return _as_optional_str(value)

    @field_validator("muvekkiller", "belgede_gecen_isimler", mode="before")
    @classmethod
    def _normalize_list(cls, value: Any) -> List[str]:
        return _as_str_list(value)


def _summarize(exc: ValidationError) -> str:
    """Log için kısa alan listesi — ham LLM çıktısı loga sızmasın (KVKK)."""
    parts = []
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err.get("loc", ())) or "(kök)"
        parts.append(f"{field}: {err.get('msg', '')}")
    return "; ".join(parts[:5]) or "bilinmeyen şema hatası"


def validate_process_output(raw: Any) -> Dict[str, Any]:
    """LLM çıktısını doğrular ve normalize edilmiş sözlüğü döner.

    ALAN HARİTASI KORUNUR: dönen sözlükte YALNIZCA `raw` içindeki anahtarlar
    bulunur (aynı sırayla). Şemadaki ama çıktıda olmayan alanlar `None`/`[]`
    olarak EKLENMEZ — post-processing ve frontend bugünkü sözlüğün aynısını
    görür, yalnız değerler tip-normalize edilmiştir.

    Raises:
        ProcessSchemaError: kök sözlük değilse ya da doğrulama başarısızsa.
    """
    if not isinstance(raw, dict):
        raise ProcessSchemaError(
            f"kök seviyede JSON nesnesi bekleniyordu, {type(raw).__name__} geldi"
        )
    try:
        model = ProcessAnalysisOutput.model_validate(raw)
    except ValidationError as e:
        raise ProcessSchemaError(_summarize(e)) from e
    normalized = model.model_dump()
    return {key: normalized.get(key, value) for key, value in raw.items()}
