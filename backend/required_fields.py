"""Dava kartı zorunlu alan tanımı — tek kaynak (anket kararı, 2026-07-31 rev.2).

Kural: zorunlu alan eksikliği kaydı ENGELLEMEZ — dosya DERDEST olarak açılır;
eksikler dava kartında/listesinde uyarı olarak görünür ve panelden
filtrelenebilir (DANIŞ'a düşürme denendi, dönüşüm kaybı riski nedeniyle
vazgeçildi: DANIŞ yolunda müvekkil kaydı oluşturulmuyor).

Frontend bu listeyi GET /api/config/required_case_fields üzerinden okur;
ikinci bir liste tutulmaz. Liste değişirse case_manager._missing_required_clause
otomatik uyum sağlar (alan adından kolona bakar).
"""

REQUIRED_CASE_FIELDS = [
    {"field": "esas_no", "label": "Esas No"},
    {"field": "court", "label": "Mahkeme"},
    {"field": "file_type", "label": "Yargı Türü"},
    {"field": "judicial_unit", "label": "Yargı Birimi"},
    {"field": "sub_type", "label": "Dosya Alt Türü"},
    {"field": "sub_type_extra", "label": "Uzmanlık / Tıbbi İşlem"},
    {"field": "opening_date", "label": "Dava Açılış Tarihi"},
    {"field": "subject", "label": "Dava Konusu"},
    {"field": "responsible_lawyer_name", "label": "Sorumlu Avukat"},
    {"field": "uyap_lawyer_name", "label": "UYAP Avukatı"},
    {"field": "service_type", "label": "Hizmet Türü"},
    {"field": "acceptance_date", "label": "Kabul Tarihi"},
    {"field": "bureau_type", "label": "Büro Özel Türü"},
    {"field": "atama_tarihi", "label": "Atama Tarihi"},
]

# Müvekkil TC'si Client kaydında yaşar (CaseParty'de toplanmıyor); form yalnız
# karşı taraf TC'si girebildiği için denetim COUNTER taraflarla sınırlı —
# aksi halde her yeni dosya yanlış "eksik" işaretlenir.
PARTY_TC_FIELD = {"field": "counter_party_tc_no", "label": "Karşı Taraf TC Kimlik No"}


def _is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _party_field(party, name):
    if isinstance(party, dict):
        return party.get(name)
    return getattr(party, name, None)


def compute_missing_fields(case_data: dict, parties=None) -> list:
    """Eksik zorunlu alanları [{field, label}] listesi olarak döndürür."""
    missing = [dict(f) for f in REQUIRED_CASE_FIELDS if _is_empty(case_data.get(f["field"]))]

    if parties is None:
        parties = case_data.get("parties") or []
    counters = [p for p in parties if (_party_field(p, "party_type") or "COUNTER") == "COUNTER"]
    has_counter_tc = any(not _is_empty(_party_field(p, "tc_no")) for p in counters)
    if counters and not has_counter_tc:
        missing.append(dict(PARTY_TC_FIELD))

    return missing
