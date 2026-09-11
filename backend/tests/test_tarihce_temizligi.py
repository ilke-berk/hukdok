"""Tarihçe temizliği (11.09.2026 kullanıcı kararı) — hangi satır gürültü, hangisi olay.

Kural: otomatik imzalı (HUKDOK_TESLIM* / yazim_birligi) satırlar silinir; istisna
föy bağlama (provenance imzası), birleştirme izi ve mahkeme/esas/status GERÇEK
değişimi. Kullanıcı imzalı satıra dokunulmaz.
"""
from datetime import datetime

import pytest

import models
from scripts import tarihce_temizligi as tt


def _h(field, old, new, source="HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx", changed_by="hukdok_aktarim"):
    return models.CaseHistory(case_id=1, field_name=field, old_value=old, new_value=new,
                              changed_by=changed_by, source=source, changed_at=datetime(2026, 9, 5))


@pytest.mark.parametrize("satir, beklenen", [
    (_h("avukat", None, "Serap Turgal"), "dolgu izi"),
    (_h("taraf", "Axa Sigorta A.ş.", "Axa Sigorta A.Ş.", source="yazim_birligi", changed_by="ilke"), "dolgu izi"),
    (_h("case_foys.case_party_id", None, "Axa Sigorta A.Ş."), "dolgu izi"),
    (_h("court", None, "Tarsus 3. Asliye Hukuk Mahkemesi"), "ilk dolum"),
    (_h("court", "Kocaeli 2. İdare Mahkemesi", "Kocaeli 2. İdare Mahkemeleri"), "yalnız biçim"),
    (_h("court", "ISTANBUL 4. IDARE MAHKEMESI", "İstanbul 4. İdare Mahkemesi"), "yalnız biçim"),
    (_h("court", "İzmir 4. İdare Mahkemesi", "İzmir 15. Asliye Hukuk Mahkemesi"), None),   # gerçek
    (_h("esas_no", "2022/???;2022/", "2022/"), "yer tutucu esas"),
    (_h("esas_no", "2020 / 1777", "2020/1777"), "yalnız biçim"),
    (_h("esas_no", "2019/382", "2025/837"), None),                                        # gerçek
    (_h("status", "DERDEST", "derdest"), "yalnız biçim"),
    (_h("status", "DERDEST", "MAHZEN"), None),                                            # gerçek
    (_h("case_foys.sistem_no", None, "H-12028"), None),                                   # provenance imzası
    (_h("tku_birlestirme", "D1.X", "S3.Y", source="tku_birlestirme #2 → #1", changed_by="mukerrer_kart_birlestir"), None),
    (_h("avukat", None, "Serap Turgal", source=None, changed_by="ilke"), None),           # kullanıcı
    (_h("court", "A", "B", source="intake-enrich: x.pdf", changed_by="Ilke Kutluk"), None),
])
def test_karar(satir, beklenen):
    assert tt.karar(satir) == beklenen


def test_otomatik_imza_joker_sizdirmaz():
    assert tt.otomatik_imza("HUKDOK_TESLIM_paket.xlsx")
    assert tt.otomatik_imza("yazim_birligi")
    assert not tt.otomatik_imza(None)
    assert not tt.otomatik_imza("intake-enrich: a.pdf")
    assert not tt.otomatik_imza("HUKDOKxTESLIM")
