"""G160 — `scripts/yazim_birligi.py`: tek seferlik yazım dönüşümü (dry-run / --apply, tarihçeli).

Plan 08.09 §5.3-B: aynı değerin iki yazımı DB'de yan yana yaşıyor (uzmanlık
"… Ve …" ↔ "… ve …", taraf "A.ş." ↔ "A.Ş.", mahkeme BÜYÜK ↔ Title). Betik
yalnız Türkçe büyük-harf anahtarı AYNI olan çiftleri dönüştürür; içerik farkı
asla. Sigortalı/Davalı İdare tarafları, istinaf/temyiz mahkemesi, silinmiş
kartlar DOKUNULMAZ; belge envanteri (`case_party_id`) denk kalır; ikinci
`--apply` 0 değişiklik.
"""
from __future__ import annotations

import argparse
from typing import Dict, List

import pytest

import models
from managers import reference_lists
from managers.config_manager import DynamicConfig
from scripts import yazim_birligi as yb
from services import belge_envanteri
from tests import test_g064_aktarim_cekirdek as g064

db_env = g064.db_env


# ═══════════════════════════════════════════════════════════════════════════
# 1. Saf kurallar
# ═══════════════════════════════════════════════════════════════════════════

def test_anahtar_bosluk_ve_turkce_buyuk():
    assert yb.anahtar("  kadın   hastalıkları ") == "KADIN HASTALIKLARI"
    assert yb.anahtar("İstanbul 6. Tüketici") == yb.anahtar("İSTANBUL 6. TÜKETİCİ")
    assert yb.anahtar("Sigortalı") != yb.anahtar("SIGORTALI")       # ASCII I ≠ Türkçe İ: içerik farkı


@pytest.mark.parametrize("sayimlar,teslim,beklenen", [
    ({"Ortopedi Ve Travmatoloji": 21, "Ortopedi ve Travmatoloji": 500}, None, "Ortopedi ve Travmatoloji"),
    # eşitlikte teslim yazımı
    ({"Ak Sigorta A.ş.": 3, "AK SİGORTA A.Ş.": 3}, "Ak Sigorta A.Ş.", "Ak Sigorta A.Ş."),
    # eşitlikte teslim yoksa tr_title
    ({"Ak Sigorta A.ş.": 3, "AK SİGORTA A.Ş.": 3}, None, "Ak Sigorta A.Ş."),
    # baskın tamamı BÜYÜK → tr_title
    ({"ANKARA 2. ASLİYE HUKUK MAHKEMESİ": 9, "Ankara 2. asliye hukuk mahkemesi": 1}, None,
     "Ankara 2. Asliye Hukuk Mahkemesi"),
    # teslim verildiyse o kazanır (satır sayısına bakılmaz); teslim BÜYÜKse tr_title
    ({"Kadın Hastalıkları Ve Doğum": 100}, "Kadın Hastalıkları ve Doğum", "Kadın Hastalıkları ve Doğum"),
    ({"Çetin Refik Kayaoğlu": 1}, "ÇETİN REFİK KAYAOĞLU", "Çetin Refik Kayaoğlu"),
    # teslim yazımının boşluğu normalize edilir
    ({"İstanbul 6. Tüketici Mahkemesi": 5}, "İstanbul  6. Tüketici Mahkemesi ", "İstanbul 6. Tüketici Mahkemesi"),
])
def test_baskin_yazim_kurali(sayimlar, teslim, beklenen):
    assert yb.baskin_yazim(sayimlar, teslim) == beklenen


def test_korunan_roller_aktarimla_ayni():
    assert yb.KORUNAN_ROLLER == frozenset({"Sigortalı", "Davalı İdare"})


def test_adim_listesi_ayristirma():
    assert yb._adim_listesi(None) == [1, 2, 3, 4, 5, 6]
    assert yb._adim_listesi("3, 1,3") == [3, 1]
    with pytest.raises(argparse.ArgumentTypeError):
        yb._adim_listesi("1,9")


def test_apply_kim_zorunlu(db_env):
    with pytest.raises(ValueError, match="--kim"):
        yb.kos(db_env, apply=True)
    with pytest.raises(SystemExit):
        yb.main(["--apply"])


# ═══════════════════════════════════════════════════════════════════════════
# 2. sqlite fixture — çift + ikiz + dokunulmayacak alan, her adım için
# ═══════════════════════════════════════════════════════════════════════════

ISTINAF = "İSTANBUL BİM 7. İDD"


def _kart(db, tracking, **alanlar):
    case = models.Case(tracking_no=tracking, status="DERDEST", **alanlar)
    db.add(case)
    db.flush()
    return case


def _taraf(db, case, name, role, party_type="COUNTER"):
    p = models.CaseParty(case_id=case.id, name=name, role=role, party_type=party_type)
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def zemin(db_env, monkeypatch):
    """Yedi kart + föyler + taraflar + belgeler + iki liste.

    K1: her kolonda yazım farkı + föy ham satırı (teslim yazımı) + belge bağı.
    K2/K3: baskın yazımlar. K4: SİLİNMİŞ (aynı bozuk yazım, dokunulmaz).
    K5-K7: teslimsiz DB-içi ikizler (baskın Title / baskın BÜYÜK → tr_title).
    """
    monkeypatch.setattr(reference_lists, "SessionLocal", db_env)
    config = DynamicConfig.get_instance()
    config.set_bureau_types([])
    db = db_env()
    try:
        k1 = _kart(db, "K1", sub_type="Kadın Hastalıkları Ve Doğum", court="İSTANBUL 6. TÜKETİCİ MAHKEMESİ",
                   subject="Tazminat (tıbbi Kötü Uygulama)", bureau_type="Dr Özel", istinaf_mahkemesi=ISTINAF)
        k2 = _kart(db, "K2", sub_type="Kadın Hastalıkları ve Doğum", court="İstanbul 6. Tüketici Mahkemesi",
                   subject="Tazminat (Tıbbi Kötü Uygulama)", bureau_type="Dr Özel")
        k3 = _kart(db, "K3", sub_type="Perinatoloji", court="İstanbul 6. Tüketici Mahkemesi",
                   subject="Tazminat (Tıbbi Kötü Uygulama)", bureau_type="Dr Özel")
        k4 = _kart(db, "K4", sub_type="Kadın Hastalıkları Ve Doğum", court="İSTANBUL 6. TÜKETİCİ MAHKEMESİ",
                   subject="Tazminat (tıbbi Kötü Uygulama)", bureau_type="DR ÖZEL")
        k5 = _kart(db, "K5", sub_type="Ortopedi Ve Travmatoloji", court="ANKARA 2. ASLİYE HUKUK MAHKEMESİ",
                   subject="TAZMİNAT", bureau_type="DR ÖZEL")
        k6 = _kart(db, "K6", sub_type="Ortopedi ve Travmatoloji", court="ANKARA 2. ASLİYE HUKUK MAHKEMESİ",
                   subject="Tazminat", bureau_type="Hasta")
        k7 = _kart(db, "K7", sub_type="Ortopedi ve Travmatoloji", court="Ankara 2. asliye hukuk mahkemesi",
                   subject="Tazminat", bureau_type="Tür Seçiniz")
        db.flush()
        k4.deleted_at = models.func.now()
        k4.active = False

        # Föy ham satırları — teslim yazımı (K1: Uzmanlık/Müvekkil/Karşı Taraf; mahkeme
        # ve Sigortalı BÜYÜK gelir ve KULLANILMAMALI). K4 silinmiş, K7 kapsam dışı.
        db.add(models.CaseFoy(sistem_no="SSTMN-1", case_id=k1.id, ham_veri={
            "Uzmanlık Alanı": "Kadın Hastalıkları ve Doğum",
            "Müvekkil": "Ak Sigorta A.Ş.",
            "Karşı Taraf": "Selcan Ayar, Seçkin Ayar; ALİ VELİ",
            "Sigortalı": "GAMZE GÖKALP",
            "Yerel Mahkeme": "İSTANBUL 6. TÜKETİCİ MAHKEMESİ",
            "Dava Konusu": "TAZMİNAT (TIBBİ KÖTÜ UYGULAMA)",
        }))
        db.add(models.CaseFoy(sistem_no="SSTMN-4", case_id=k4.id, ham_veri={"Uzmanlık Alanı": "KADIN HASTALIKLARI VE DOĞUM"}))
        db.add(models.CaseFoy(sistem_no="SSTMN-7", case_id=k7.id, kapsam_durumu="SILINDI",
                              ham_veri={"Uzmanlık Alanı": "ORTOPEDİ VE TRAVMATOLOJİ"}))

        # Taraflar
        t1 = _taraf(db, k1, "AK SİGORTA A.Ş.", "Müvekkil", "CLIENT")
        t2 = _taraf(db, k2, "Ak Sigorta A.ş.", "Müvekkil", "CLIENT")
        t3 = _taraf(db, k1, "SELCAN AYAR, SEÇKİN AYAR", "Karşı Taraf")
        t4 = _taraf(db, k1, "Ali Veli", "DAVALI")                    # ad zaten Title (teslim BÜYÜK → tr_title aynı); rol listeye
        t5 = _taraf(db, k1, "GAMZE GÖKALP", "Sigortalı", "THIRD")     # KORUNUR
        t6 = _taraf(db, k2, "Gamze Gökalp", "Karşı Taraf")           # korunanla ikiz → tek varyant → dokunulmaz
        t7 = _taraf(db, k5, "ANADOLU ANONİM TÜRK SİGORTA ŞİRKETİ", "Karşı Taraf")
        t8 = _taraf(db, k6, "Anadolu Anonim Türk Sigorta Şirketi", "Karşı Taraf")
        t9 = _taraf(db, k7, "Anadolu Anonim Türk Sigorta Şirketi", "Karşı Taraf")
        t10 = _taraf(db, k5, "MEHMET YILMAZ", "Diğer Davalı")
        t11 = _taraf(db, k6, "MEHMET YILMAZ", "Diğer Davalı")
        t12 = _taraf(db, k7, "Mehmet yılmaz", "Diğer Davalı")
        t13 = _taraf(db, k4, "AK SİGORTA A.Ş.", "Müvekkil", "CLIENT")  # silinmiş kart
        t14 = _taraf(db, k2, "Ayşe Kaya", "SIGORTALI", "THIRD")       # rol anahtarı listeyle AYNI DEĞİL
        t15 = _taraf(db, k3, "Hakan Yılmaz", "DAVACI")

        # Belgeler — envanter kanıtı (taraf bağlı + kart bağlı)
        db.add(models.CaseDocument(case_id=k1.id, case_party_id=t1.id, original_filename="a.pdf",
                                   stored_filename="a.pdf", link_mode="LINKED"))
        db.add(models.CaseDocument(case_id=k1.id, case_party_id=t3.id, original_filename="b.pdf",
                                   stored_filename="b.pdf", link_mode="LINKED"))
        db.add(models.CaseDocument(case_id=k2.id, original_filename="c.pdf", stored_filename="c.pdf",
                                   link_mode="LINKED"))

        # Listeler
        db.add(models.PartyRole(code="DAVALI", name="Davalı", role_type="MAIN", active=True))
        db.add(models.PartyRole(code="DAVACI", name="Davacı", role_type="MAIN", active=True))
        db.add(models.BureauType(code="DR-ÖZEL", name="DR ÖZEL", active=True))
        db.add(models.BureauType(code="LEXİS", name="LEXİS", active=True))
        db.add(models.AppealCourt(code="IST-BIM-7", name=ISTINAF, active=True))
        db.commit()
        kimlikler = dict(k1=k1.id, k2=k2.id, k3=k3.id, k4=k4.id, k5=k5.id, k6=k6.id, k7=k7.id,
                         t1=t1.id, t2=t2.id, t3=t3.id, t4=t4.id, t5=t5.id, t6=t6.id, t7=t7.id, t8=t8.id,
                         t9=t9.id, t10=t10.id, t11=t11.id, t12=t12.id, t13=t13.id, t14=t14.id, t15=t15.id)
    finally:
        db.close()
    yield db_env, kimlikler
    config.set_bureau_types([])


def _kartlar(fabrika) -> Dict[str, models.Case]:
    db = fabrika()
    try:
        db.expire_on_commit = False
        return {c.tracking_no: c for c in db.query(models.Case).all()}
    finally:
        db.close()


def _taraflar(fabrika) -> Dict[int, tuple]:
    db = fabrika()
    try:
        return {p.id: (p.name, p.role, p.case_id) for p in db.query(models.CaseParty).all()}
    finally:
        db.close()


def _tarihce(fabrika) -> List[models.CaseHistory]:
    db = fabrika()
    try:
        db.expire_on_commit = False
        return db.query(models.CaseHistory).order_by(models.CaseHistory.id).all()
    finally:
        db.close()


def _envanter(fabrika) -> belge_envanteri.BelgeEnvanteri:
    db = fabrika()
    try:
        return belge_envanteri.snapshot(db)
    finally:
        db.close()


def _liste(fabrika, model) -> Dict[str, str]:
    db = fabrika()
    try:
        return {r.code: r.name for r in db.query(model).all()}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Kuru koşu — hiçbir şey yazmaz, CSV + özet üretir
# ═══════════════════════════════════════════════════════════════════════════

def test_kuru_kosu_varsayilan_hicbir_sey_yazmaz(zemin, tmp_path, capsys):
    fabrika, k = zemin
    kart_once, taraf_once, tarihce_once = _kartlar(fabrika), _taraflar(fabrika), _tarihce(fabrika)
    liste_once = _liste(fabrika, models.BureauType)

    sonuc = yb.kos(fabrika, cikti_dizini=tmp_path)
    assert not sonuc.yazildi and sonuc.cikis_kodu == yb.CIKIS_TAMAM
    assert sonuc.toplam_satir > 0

    # DB dokunulmadı
    assert {t: (c.sub_type, c.court, c.subject, c.bureau_type)
            for t, c in _kartlar(fabrika).items()} == {t: (c.sub_type, c.court, c.subject, c.bureau_type)
                                                        for t, c in kart_once.items()}
    assert _taraflar(fabrika) == taraf_once
    assert len(_tarihce(fabrika)) == len(tarihce_once) == 0
    assert _liste(fabrika, models.BureauType) == liste_once

    # Adım başına CSV + özet satırı
    for adim in yb.ADIMLAR:
        assert (tmp_path / f"{adim}.csv").exists()
    cikti = capsys.readouterr().out
    assert "=== Adım 1" in cikti and "=== Adım 6" in cikti
    assert "'Kadın Hastalıkları Ve Doğum' → 'Kadın Hastalıkları ve Doğum'" in cikti
    icerik = (tmp_path / "2.csv").read_text(encoding="utf-8-sig")
    assert "AK SİGORTA A.Ş.,Ak Sigorta A.Ş.,teslim" in icerik


# ═══════════════════════════════════════════════════════════════════════════
# 4. --apply — adım adım beklenen değerler + tarihçe + idempotency + envanter
# ═══════════════════════════════════════════════════════════════════════════

def test_apply_adimlarin_tamami(zemin, tmp_path):
    fabrika, k = zemin
    envanter_once = _envanter(fabrika)
    taraf_once = _taraflar(fabrika)

    sonuc = yb.kos(fabrika, apply=True, kim="test-kullanici", cikti_dizini=tmp_path)
    assert sonuc.yazildi and not sonuc.envanter_farki and sonuc.cikis_kodu == yb.CIKIS_TAMAM
    satirlar = {a.adim: a.satir for a in sonuc.adimlar}

    kart = _kartlar(fabrika)
    # Adım 1 — teslim yazımı (K1) + föysüz ikiz baskın (K5); içerik farklı K3 dokunulmaz; K4 silinmiş
    assert kart["K1"].sub_type == "Kadın Hastalıkları ve Doğum"
    assert kart["K5"].sub_type == "Ortopedi ve Travmatoloji"
    assert kart["K3"].sub_type == "Perinatoloji"
    assert kart["K4"].sub_type == "Kadın Hastalıkları Ve Doğum"
    assert satirlar[1] == 2

    # Adım 3 — ikiz baskın Title (K1); baskın BÜYÜK → tr_title (K5, K6, K7); teslim BÜYÜK KULLANILMADI
    assert kart["K1"].court == "İstanbul 6. Tüketici Mahkemesi"
    assert kart["K2"].court == "İstanbul 6. Tüketici Mahkemesi"
    assert {kart[t].court for t in ("K5", "K6", "K7")} == {"Ankara 2. Asliye Hukuk Mahkemesi"}
    assert kart["K4"].court == "İSTANBUL 6. TÜKETİCİ MAHKEMESİ"
    assert satirlar[3] == 4

    # Adım 4 — ikiz baskın (K1); eşitlik yok: TAZMİNAT 1 ↔ Tazminat 2 → baskın
    assert kart["K1"].subject == "Tazminat (Tıbbi Kötü Uygulama)"
    assert kart["K5"].subject == "Tazminat"
    assert satirlar[4] == 2

    # Adım 6 — kartlar: K5 BÜYÜK → kart yazımı; K7 yer tutucu → boş; K6 "Hasta" kalır
    assert kart["K5"].bureau_type == "Dr Özel"
    assert kart["K7"].bureau_type is None
    assert kart["K6"].bureau_type == "Hasta"
    assert satirlar[6] == 2
    liste = _liste(fabrika, models.BureauType)
    assert liste["DR-ÖZEL"] == "Dr Özel" and liste["LEXİS"] == "Lexis" and liste["HASTA"] == "Hasta"
    assert any("eklendi" in m for m in sonuc.liste_sonuclari)

    # Dokunulmayanlar
    assert kart["K1"].istinaf_mahkemesi == ISTINAF
    assert _liste(fabrika, models.AppealCourt) == {"IST-BIM-7": ISTINAF}

    taraf = _taraflar(fabrika)
    # Adım 2 — teslim yazımı; ikiz baskın; baskın BÜYÜK → tr_title; korunan/silinmiş/tekil dokunulmaz
    assert taraf[k["t1"]][0] == "Ak Sigorta A.Ş."
    assert taraf[k["t2"]][0] == "Ak Sigorta A.Ş."
    assert taraf[k["t3"]][0] == "Selcan Ayar, Seçkin Ayar"
    assert taraf[k["t4"]][0] == "Ali Veli"
    assert taraf[k["t7"]][0] == "Anadolu Anonim Türk Sigorta Şirketi"
    assert {taraf[k[t]][0] for t in ("t10", "t11", "t12")} == {"Mehmet Yılmaz"}
    assert taraf[k["t5"]][0] == "GAMZE GÖKALP"           # Sigortalı KORUNDU
    assert taraf[k["t6"]][0] == "Gamze Gökalp"
    assert taraf[k["t13"]][0] == "AK SİGORTA A.Ş."       # silinmiş kartın tarafı
    assert satirlar[2] == 7
    # Adım 5 — rol listeye; "SIGORTALI" (ASCII I) içerik farkı → dokunulmaz
    assert taraf[k["t4"]][1] == "Davalı"
    assert taraf[k["t15"]][1] == "Davacı"
    assert taraf[k["t14"]][1] == "SIGORTALI"
    assert satirlar[5] == 2
    # Taraf satırları yerinde güncellendi: id kümesi ve kart bağı aynı
    assert set(taraf) == set(taraf_once)
    assert {i: v[2] for i, v in taraf.items()} == {i: v[2] for i, v in taraf_once.items()}

    # Belge envanteri denk (case_party_id dahil)
    assert belge_envanteri.denk(envanter_once, _envanter(fabrika))
    assert _envanter(fabrika).tarafa_bagli == 2

    # Tarihçe: kart alanları + taraf satırları, imza doğru
    tarihce = _tarihce(fabrika)
    assert len(tarihce) == sonuc.toplam_satir == sum(satirlar.values())
    assert {h.source for h in tarihce} == {"yazim_birligi"}
    assert {h.changed_by for h in tarihce} == {"test-kullanici"}
    kayitlar = {(h.case_id, h.field_name, h.old_value, h.new_value) for h in tarihce}
    assert (k["k1"], "sub_type", "Kadın Hastalıkları Ve Doğum", "Kadın Hastalıkları ve Doğum") in kayitlar
    assert (k["k5"], "bureau_type", "DR ÖZEL", "Dr Özel") in kayitlar
    assert (k["k7"], "bureau_type", "Tür Seçiniz", None) in kayitlar
    assert (k["k1"], "taraf", "AK SİGORTA A.Ş. (Müvekkil)", "Ak Sigorta A.Ş. (Müvekkil)") in kayitlar
    assert (k["k1"], "taraf", "Ali Veli (DAVALI)", "Ali Veli (Davalı)") in kayitlar

    # İkinci --apply: 0 değişiklik, tarihçe büyümez, liste işlemi yok
    ikinci = yb.kos(fabrika, apply=True, kim="test-kullanici", cikti_dizini=tmp_path / "ikinci")
    assert ikinci.yazildi and ikinci.toplam_satir == 0
    assert all(not a.liste_islemleri for a in ikinci.adimlar)
    assert len(_tarihce(fabrika)) == len(tarihce)
    assert _taraflar(fabrika) == taraf


def test_adim_secimi_yalniz_secilen_kolona_dokunur(zemin, tmp_path):
    fabrika, k = zemin
    sonuc = yb.kos(fabrika, adimlar=[3], apply=True, kim="x", cikti_dizini=tmp_path)
    assert [a.adim for a in sonuc.adimlar] == [3]
    kart = _kartlar(fabrika)
    assert kart["K1"].court == "İstanbul 6. Tüketici Mahkemesi"
    assert kart["K1"].sub_type == "Kadın Hastalıkları Ve Doğum"      # adım 1 koşmadı
    assert _taraflar(fabrika)[k["t1"]][0] == "AK SİGORTA A.Ş."       # adım 2 koşmadı
    assert {h.field_name for h in _tarihce(fabrika)} == {"court"}
    assert not (tmp_path / "1.csv").exists() and (tmp_path / "3.csv").exists()


def test_envanter_farki_kosuyu_geri_alir(zemin, tmp_path, monkeypatch, caplog):
    """Kapı: commit'ten önce belge envanteri denk değilse rollback + NONZERO, tek ERROR."""
    fabrika, k = zemin
    gercek = belge_envanteri.snapshot
    sayac = {"n": 0}

    def sahte(db, case_ids=None):
        sayac["n"] += 1
        foto = gercek(db, case_ids)
        if sayac["n"] == 2:
            return belge_envanteri.BelgeEnvanteri(**{**foto.__dict__, "tarafa_bagli": foto.tarafa_bagli - 1})
        return foto

    monkeypatch.setattr(belge_envanteri, "snapshot", sahte)
    kart_once = {t: c.sub_type for t, c in _kartlar(fabrika).items()}
    with caplog.at_level("ERROR", logger="yazim_birligi"):
        sonuc = yb.kos(fabrika, apply=True, kim="x", cikti_dizini=tmp_path)
    assert not sonuc.yazildi and sonuc.cikis_kodu == yb.CIKIS_ENVANTER
    assert "tarafa_bagli" in sonuc.envanter_farki
    assert {t: c.sub_type for t, c in _kartlar(fabrika).items()} == kart_once
    assert len(_tarihce(fabrika)) == 0
    assert _liste(fabrika, models.BureauType)["DR-ÖZEL"] == "DR ÖZEL"      # liste işlemi de koşmadı
    assert sum(1 for r in caplog.records if r.levelname == "ERROR") == 1


def test_icerik_farkli_cift_donusmez(db_env, tmp_path):
    """Anahtar farklıysa (içerik) hiçbir kural devreye girmez — ikiz gibi görünse de."""
    db = db_env()
    try:
        _kart(db, "A", sub_type="Kadın Hastalıkları ve Doğum", court="İstanbul 6. Tüketici Mahkemesi")
        _kart(db, "B", sub_type="Kadın Hastalıkları Doğum", court="İstanbul 7. Tüketici Mahkemesi")
        _kart(db, "C", sub_type="Kadin Hastaliklari ve Dogum", court="İstanbul 6. Tüketici Mahkemesi ")
        db.commit()
    finally:
        db.close()
    sonuc = yb.kos(db_env, adimlar=[1, 3], apply=True, kim="x", cikti_dizini=tmp_path)
    assert sonuc.yazildi
    kart = _kartlar(db_env)
    assert kart["B"].sub_type == "Kadın Hastalıkları Doğum"
    assert kart["C"].sub_type == "Kadin Hastaliklari ve Dogum"
    assert kart["B"].court == "İstanbul 7. Tüketici Mahkemesi"
    # yalnız boşluk farkı (aynı anahtar) baskına hizalanır — yazım, içerik değil
    assert kart["C"].court == "İstanbul 6. Tüketici Mahkemesi"
    assert sonuc.toplam_satir == 1


# ═══════════════════════════════════════════════════════════════════════════
# 5. Adım 2b (G163) — tek yazımlı, teslimsiz taraf adında yalnız biçim farkı → tr_title
# ═══════════════════════════════════════════════════════════════════════════

def test_anahtar_genis_bicim_katlar_icerik_katlamaz():
    # ı/i/İ/I + son nokta + A.ş/A.Ş: aynı biçim kimliği
    assert yb.anahtar_genis("Quıck Sigorta A.ş") == yb.anahtar_genis("Quick Sigorta A.Ş") \
        == yb.anahtar_genis("QUİCK  SİGORTA A.Ş.")
    assert yb.anahtar_genis("Türk Nippon Sigorta Aş") == yb.anahtar_genis("Türk Nippon Sigorta AŞ")
    # kelime ekleme/çıkarma ve harf farkı: farklı
    assert yb.anahtar_genis("Koru Sigorta A.Ş.") != yb.anahtar_genis("Koru A.Ş.")
    assert yb.anahtar_genis("Ak Sigorta") != yb.anahtar_genis("Ag Sigorta")


@pytest.fixture()
def zemin_2b(db_env):
    """Adım 2b zemini: tek yazımlı (ikizsiz, teslimsiz) bozuk biçimler + sınır durumları.

    Q1..Q4: 2b'nin hedefi. Q5 korunan rol (Sigortalı). Q6/Q7 ikiz (adım 2'nin
    işi, 2b'ye girmez). Q8 teslim anahtarlı tek yazım (teslim kazanır, 2b
    dokunmaz). Q9 silinmiş kart. Q10 kelime düşüren sahte hedef için (test-e).
    """
    db = db_env()
    try:
        k1 = _kart(db, "Q1")
        k2 = _kart(db, "Q2")
        k9 = _kart(db, "Q9")
        db.flush()
        k9.deleted_at = models.func.now()
        k9.active = False
        db.add(models.CaseFoy(sistem_no="SSTMN-Q2", case_id=k2.id, ham_veri={"Müvekkil": "Yeni SİGORTA A.Ş."}))
        t = {}
        t["q1"] = _taraf(db, k1, "Quıck Sigorta A.ş", "Müvekkil", "CLIENT")
        t["q2"] = _taraf(db, k1, "Koru Sigorta A.ş.", "Karşı Taraf")
        t["q3"] = _taraf(db, k1, "Türk Nippon Sigorta Aş", "Karşı Taraf")
        t["q4"] = _taraf(db, k2, "Sağlık Bakanlığı (davalı)", "Karşı Taraf")
        t["q5"] = _taraf(db, k1, "Ankara Sigorta A.ş", "Sigortalı", "THIRD")          # KORUNUR
        t["q6"] = _taraf(db, k1, "Ak Sigorta A.ş.", "Karşı Taraf")                    # ikiz → adım 2
        t["q7"] = _taraf(db, k2, "AK SİGORTA A.Ş.", "Karşı Taraf")                    # ikiz → adım 2
        t["q8"] = _taraf(db, k2, "Yeni SİGORTA A.Ş.", "Müvekkil", "CLIENT")           # teslimle aynı → adım 2 görür
        t["q9"] = _taraf(db, k9, "Batı Sigorta A.ş", "Karşı Taraf")                   # silinmiş kart
        t["q10"] = _taraf(db, k2, "Deneme Sigorta A.ş", "Karşı Taraf")
        db.add(models.CaseDocument(case_id=k1.id, case_party_id=t["q1"].id, original_filename="q.pdf",
                                   stored_filename="q.pdf", link_mode="LINKED"))
        db.commit()
        kimlikler = {ad: p.id for ad, p in t.items()}
        kimlikler.update(k1=k1.id, k2=k2.id, k9=k9.id)
    finally:
        db.close()
    return db_env, kimlikler


def _degisim(sonuc: yb.AdimSonucu) -> Dict[int, tuple]:
    return {d.kayit_id: (d.eski, d.yeni, d.kaynak) for d in sonuc.degisiklikler}


def test_adim_2b_yalniz_bicim_farki_tr_title(zemin_2b):
    """(a)-(d): tek yazımlı grupta hedef tr_title, kaynak tr_title; (f) korunan rol, silinmiş kart dışarıda."""
    fabrika, k = zemin_2b
    db = fabrika()
    try:
        sonuc = yb.adim_2b_taraf_adi_bicim(db)
    finally:
        db.close()
    assert sonuc.adim == "2b" and sonuc.sayili_ornek == yb.ORNEK_SAYISI_2B
    degisim = _degisim(sonuc)
    assert degisim[k["q1"]] == ("Quıck Sigorta A.ş", "Quick Sigorta A.Ş", "tr_title")
    assert degisim[k["q2"]] == ("Koru Sigorta A.ş.", "Koru Sigorta A.Ş.", "tr_title")
    assert degisim[k["q3"]] == ("Türk Nippon Sigorta Aş", "Türk Nippon Sigorta AŞ", "tr_title")
    assert degisim[k["q4"]] == ("Sağlık Bakanlığı (davalı)", "Sağlık Bakanlığı (Davalı)", "tr_title")
    assert degisim[k["q10"]] == ("Deneme Sigorta A.ş", "Deneme Sigorta A.Ş", "tr_title")
    assert k["q5"] not in degisim                       # Sigortalı KORUNUR
    assert k["q9"] not in degisim                       # silinmiş kartın tarafı
    assert all(d.rol for d in sonuc.degisiklikler)      # tarihçe metni için rol taşınır


def test_adim_2b_adim_2nin_gordugu_gruplara_girmez(zemin_2b):
    """(g): ikiz grup ve teslim anahtarlı grup adım 2'nindir; 2b aynı satırı tekrar saymaz."""
    fabrika, k = zemin_2b
    db = fabrika()
    try:
        s2, anahtarlar = yb._adim_2_hesapla(db)
        s2b = yb.adim_2b_taraf_adi_bicim(db, anahtarlar)
        s2b_bagimsiz = yb.adim_2b_taraf_adi_bicim(db)   # anahtar verilmeden de aynı sonuç
    finally:
        db.close()
    d2, d2b = _degisim(s2), _degisim(s2b)
    assert d2[k["q6"]] == ("Ak Sigorta A.ş.", "Ak Sigorta A.Ş.", "tr_title")   # eşitlik → tr_title (adım 2)
    assert k["q6"] not in d2b and k["q7"] not in d2b
    # Q8: teslim yazımı DB'deki tek yazımla aynı → adım 2 değişiklik üretmez; tr_title farklı olsa da 2b dokunmaz
    assert k["q8"] not in d2 and k["q8"] not in d2b
    assert yb.anahtar("Yeni SİGORTA A.Ş.") in anahtarlar
    assert not set(d2) & set(d2b)
    assert _degisim(s2b_bagimsiz) == d2b


def test_adim_2b_kelime_farki_ureten_hedef_atlanir(zemin_2b, monkeypatch):
    """(e): tr_title kelime düşürmez; koruma yine de var — sahte hedefte anahtar_genis eşit değil → atlanır."""
    fabrika, k = zemin_2b
    gercek = yb.tr_title

    def sahte(s: str) -> str:
        return "Deneme A.Ş" if s == "Deneme Sigorta A.ş" else gercek(s)

    monkeypatch.setattr(yb, "tr_title", sahte)
    db = fabrika()
    try:
        sonuc = yb.adim_2b_taraf_adi_bicim(db)
    finally:
        db.close()
    degisim = _degisim(sonuc)
    assert k["q10"] not in degisim
    assert k["q1"] in degisim                           # diğerleri etkilenmez


def test_adim_2b_kos_apply_tarihce_envanter_idempotent(zemin_2b, tmp_path, capsys):
    """(h) + kabul: `--adim 2` → [2, 2b]; apply tarihçeli, satır id/bağ sabit, envanter denk, ikinci koşu 0."""
    fabrika, k = zemin_2b
    taraf_once, envanter_once = _taraflar(fabrika), _envanter(fabrika)

    kuru = yb.kos(fabrika, adimlar=[2], cikti_dizini=tmp_path / "kuru")
    assert [a.adim for a in kuru.adimlar] == [2, "2b"]
    assert not kuru.yazildi and _taraflar(fabrika) == taraf_once
    assert (tmp_path / "kuru" / "2b.csv").exists()
    cikti = capsys.readouterr().out
    assert "=== Adım 2b" in cikti and f"ilk {yb.ORNEK_SAYISI_2B} tekil" in cikti
    assert "'Quıck Sigorta A.ş' → 'Quick Sigorta A.Ş'  (1 satır)" in cikti
    assert "Quıck Sigorta A.ş,Quick Sigorta A.Ş,tr_title" in (tmp_path / "kuru" / "2b.csv").read_text(encoding="utf-8-sig")
    assert kuru.toplam_satir == 2 + 5                   # adım 2: ikiz çifti (eşitlik → tr_title, iki satır); 2b: Q1-Q4 + Q10

    sonuc = yb.kos(fabrika, adimlar=[2], apply=True, kim="test-kullanici", cikti_dizini=tmp_path)
    assert sonuc.yazildi and not sonuc.envanter_farki
    satirlar = {a.adim: a.satir for a in sonuc.adimlar}
    assert satirlar == {2: 2, "2b": 5}

    taraf = _taraflar(fabrika)
    assert taraf[k["q1"]][0] == "Quick Sigorta A.Ş"
    assert taraf[k["q2"]][0] == "Koru Sigorta A.Ş."
    assert taraf[k["q3"]][0] == "Türk Nippon Sigorta AŞ"
    assert taraf[k["q4"]][0] == "Sağlık Bakanlığı (Davalı)"
    assert taraf[k["q5"]][0] == "Ankara Sigorta A.ş"    # Sigortalı KORUNDU
    assert taraf[k["q6"]][0] == taraf[k["q7"]][0] == "Ak Sigorta A.Ş."
    assert taraf[k["q8"]][0] == "Yeni SİGORTA A.Ş."     # teslim yazımı kazandı
    assert taraf[k["q9"]][0] == "Batı Sigorta A.ş"      # silinmiş kart
    # satır sayısı, id kümesi ve kart bağı değişmedi; belge bağı (case_party_id) denk
    assert set(taraf) == set(taraf_once) and len(taraf) == len(taraf_once)
    assert {i: v[2] for i, v in taraf.items()} == {i: v[2] for i, v in taraf_once.items()}
    assert belge_envanteri.denk(envanter_once, _envanter(fabrika)) and _envanter(fabrika).tarafa_bagli == 1

    tarihce = _tarihce(fabrika)
    assert len(tarihce) == 7
    assert {h.source for h in tarihce} == {"yazim_birligi"} and {h.changed_by for h in tarihce} == {"test-kullanici"}
    kayitlar = {(h.case_id, h.field_name, h.old_value, h.new_value) for h in tarihce}
    assert (k["k1"], "taraf", "Quıck Sigorta A.ş (Müvekkil)", "Quick Sigorta A.Ş (Müvekkil)") in kayitlar
    assert (k["k2"], "taraf", "Sağlık Bakanlığı (davalı) (Karşı Taraf)", "Sağlık Bakanlığı (Davalı) (Karşı Taraf)") in kayitlar

    ikinci = yb.kos(fabrika, adimlar=[2], apply=True, kim="test-kullanici", cikti_dizini=tmp_path / "ikinci")
    assert ikinci.yazildi and ikinci.toplam_satir == 0
    assert len(_tarihce(fabrika)) == 7 and _taraflar(fabrika) == taraf


def test_adim_2b_yalniz_adim_2_ile_gelir(zemin_2b, tmp_path):
    sonuc = yb.kos(zemin_2b[0], adimlar=[3, 5], cikti_dizini=tmp_path)
    assert [a.adim for a in sonuc.adimlar] == [3, 5]
    assert not (tmp_path / "2b.csv").exists()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Nokta ikizleri (G164) — anahtar SON noktayı yutar: "A.Ş." ↔ "A.Ş" aynı grup
# ═══════════════════════════════════════════════════════════════════════════

def test_anahtar_son_noktayi_yutar_ic_noktayi_korur():
    """(a) Yalnız SONDAKİ nokta(lar) anahtara girmez; iç nokta içerik farkıdır; kelime farkı ayrı kalır."""
    assert yb.anahtar("Ak Sigorta A.Ş.") == yb.anahtar("Ak Sigorta A.Ş") == "AK SİGORTA A.Ş"
    assert yb.anahtar("Sağlık Bakanlığı.") == yb.anahtar("Sağlık Bakanlığı") == "SAĞLIK BAKANLIĞI"
    assert yb.anahtar("X.") == yb.anahtar("X") == yb.anahtar("X..") == yb.anahtar("X . ")
    # iç noktalar kalır: "A.Ş" ≠ "AŞ", "Sağ.Hiz." → "SAĞ.HİZ"
    assert yb.anahtar("Sağ.Hiz.") == "SAĞ.HİZ"
    assert yb.anahtar("Ak Sigorta A.Ş") != yb.anahtar("Ak Sigorta AŞ")
    assert yb.anahtar("İstanbul 6. Tüketici") == "İSTANBUL 6. TÜKETİCİ"
    # kelime ekleme/çıkarma farklı kalır
    assert yb.anahtar("Koru") != yb.anahtar("Koru Sigorta")
    assert yb.anahtar("X") != yb.anahtar("X Y")
    # anahtar_genis anahtar üzerinden kurulu → kendiliğinden uyar
    assert yb.anahtar_genis("Ak Sigorta A.Ş.") == yb.anahtar_genis("Ak Sigorta A.Ş")


@pytest.fixture()
def zemin_nokta(db_env):
    """Nokta ikizleri: teslimli (N1-N3), teslimsiz baskın noktalı (N4-N6) ve noktasız (N7-N9), ikiz-eşitlik (N10-N11).

    N1/N2 "Quick Sigorta A.Ş" ↔ N3 "Quick Sigorta A.Ş." + föy teslimi noktalı → hepsi teslim yazımına.
    N4/N5 "Ak Sigorta A.Ş." ↔ N6 "Ak Sigorta A.Ş" (teslim yok) → baskın noktalı.
    N7/N8 "Sağlık Bakanlığı" ↔ N9 "Sağlık Bakanlığı." (teslim yok) → baskın noktasız.
    N10 "Eureko Sigorta A.ş." ↔ N11 "Eureko Sigorta A.Ş" → adım 2 ikizi (eşitlik); 2b bu grubu GÖRMEZ.
    N12 "Koru" ↔ N13 "Koru Sigorta" → farklı anahtar, dokunulmaz.
    """
    db = db_env()
    try:
        k1 = _kart(db, "N-K1")
        k2 = _kart(db, "N-K2")
        db.flush()
        db.add(models.CaseFoy(sistem_no="SSTMN-N1", case_id=k1.id, ham_veri={"Müvekkil": "Quick Sigorta A.Ş."}))
        t = {}
        t["n1"] = _taraf(db, k1, "Quick Sigorta A.Ş", "Müvekkil", "CLIENT")
        t["n2"] = _taraf(db, k2, "Quick Sigorta A.Ş", "Müvekkil", "CLIENT")
        t["n3"] = _taraf(db, k2, "Quick Sigorta A.Ş.", "Karşı Taraf")
        t["n4"] = _taraf(db, k1, "Ak Sigorta A.Ş.", "Karşı Taraf")
        t["n5"] = _taraf(db, k2, "Ak Sigorta A.Ş.", "Karşı Taraf")
        t["n6"] = _taraf(db, k2, "Ak Sigorta A.Ş", "Diğer Davalı")
        t["n7"] = _taraf(db, k1, "Sağlık Bakanlığı", "Karşı Taraf")
        t["n8"] = _taraf(db, k2, "Sağlık Bakanlığı", "Karşı Taraf")
        t["n9"] = _taraf(db, k2, "Sağlık Bakanlığı.", "Diğer Davalı")
        t["n10"] = _taraf(db, k1, "Eureko Sigorta A.ş.", "Karşı Taraf")
        t["n11"] = _taraf(db, k2, "Eureko Sigorta A.Ş", "Karşı Taraf")
        t["n12"] = _taraf(db, k1, "Koru", "Karşı Taraf")
        t["n13"] = _taraf(db, k2, "Koru Sigorta", "Karşı Taraf")
        db.add(models.CaseDocument(case_id=k1.id, case_party_id=t["n1"].id, original_filename="n.pdf",
                                   stored_filename="n.pdf", link_mode="LINKED"))
        db.commit()
        kimlikler = {ad: p.id for ad, p in t.items()}
        kimlikler.update(k1=k1.id, k2=k2.id)
    finally:
        db.close()
    return db_env, kimlikler


def test_adim_2_nokta_ikizi_teslim_kazanir_yoksa_baskin(zemin_nokta):
    """(b) teslim yazımı noktalı → noktasızlar teslime; (c) teslimsiz ikizde baskın yazım (noktalı ya da noktasız)."""
    fabrika, k = zemin_nokta
    db = fabrika()
    try:
        sonuc, anahtarlar = yb._adim_2_hesapla(db)
    finally:
        db.close()
    degisim = _degisim(sonuc)
    assert degisim[k["n1"]] == ("Quick Sigorta A.Ş", "Quick Sigorta A.Ş.", "teslim")
    assert degisim[k["n2"]] == ("Quick Sigorta A.Ş", "Quick Sigorta A.Ş.", "teslim")
    assert k["n3"] not in degisim                                       # zaten teslim yazımı
    assert degisim[k["n6"]] == ("Ak Sigorta A.Ş", "Ak Sigorta A.Ş.", "baskın")
    assert k["n4"] not in degisim and k["n5"] not in degisim
    assert degisim[k["n9"]] == ("Sağlık Bakanlığı.", "Sağlık Bakanlığı", "baskın")
    assert k["n7"] not in degisim and k["n8"] not in degisim
    assert k["n12"] not in degisim and k["n13"] not in degisim          # "Koru" ↔ "Koru Sigorta" farklı
    # adım 2 nokta gruplarını GÖRDÜ (2b'ye kapalı)
    assert {yb.anahtar("Quick Sigorta A.Ş"), yb.anahtar("Ak Sigorta A.Ş"), yb.anahtar("Sağlık Bakanlığı"),
            yb.anahtar("Eureko Sigorta A.Ş")} <= anahtarlar


def test_adim_2b_nokta_ikizi_grubunu_gormez(zemin_nokta):
    """(d) Nokta ikizi adım 2'nin grubudur; 2b aynı satıra tekrar dokunmaz (çift değişiklik yok)."""
    fabrika, k = zemin_nokta
    db = fabrika()
    try:
        s2, anahtarlar = yb._adim_2_hesapla(db)
        s2b = yb.adim_2b_taraf_adi_bicim(db, anahtarlar)
    finally:
        db.close()
    d2, d2b = _degisim(s2), _degisim(s2b)
    # N10/N11 ikiz: eşitlikte sıralı ilk adayın tr_title'ı ("A.Ş" < "A.ş." → "Eureko Sigorta A.Ş"); 2b görmez
    assert d2[k["n10"]] == ("Eureko Sigorta A.ş.", "Eureko Sigorta A.Ş", "baskın")
    assert k["n11"] not in d2
    assert k["n10"] not in d2b and k["n11"] not in d2b
    assert not set(d2) & set(d2b)
    assert d2b == {}


def test_nokta_ikizi_apply_ikinci_kosu_sifir(zemin_nokta, tmp_path):
    """(e) --adim 2 apply: tarihçeli, satır id/bağ sabit, envanter denk; ikinci koşu 0."""
    fabrika, k = zemin_nokta
    taraf_once, envanter_once = _taraflar(fabrika), _envanter(fabrika)

    sonuc = yb.kos(fabrika, adimlar=[2], apply=True, kim="test-kullanici", cikti_dizini=tmp_path)
    assert sonuc.yazildi and not sonuc.envanter_farki
    assert {a.adim: a.satir for a in sonuc.adimlar} == {2: 5, "2b": 0}

    taraf = _taraflar(fabrika)
    assert {taraf[k[t]][0] for t in ("n1", "n2", "n3")} == {"Quick Sigorta A.Ş."}
    assert {taraf[k[t]][0] for t in ("n4", "n5", "n6")} == {"Ak Sigorta A.Ş."}
    assert {taraf[k[t]][0] for t in ("n7", "n8", "n9")} == {"Sağlık Bakanlığı"}
    assert {taraf[k[t]][0] for t in ("n10", "n11")} == {"Eureko Sigorta A.Ş"}
    assert taraf[k["n12"]][0] == "Koru" and taraf[k["n13"]][0] == "Koru Sigorta"
    assert set(taraf) == set(taraf_once) and {i: v[2] for i, v in taraf.items()} == {i: v[2] for i, v in taraf_once.items()}
    assert belge_envanteri.denk(envanter_once, _envanter(fabrika)) and _envanter(fabrika).tarafa_bagli == 1

    tarihce = _tarihce(fabrika)
    assert len(tarihce) == 5 and {h.source for h in tarihce} == {"yazim_birligi"}
    kayitlar = {(h.case_id, h.field_name, h.old_value, h.new_value) for h in tarihce}
    assert (k["k1"], "taraf", "Quick Sigorta A.Ş (Müvekkil)", "Quick Sigorta A.Ş. (Müvekkil)") in kayitlar
    assert (k["k2"], "taraf", "Sağlık Bakanlığı. (Diğer Davalı)", "Sağlık Bakanlığı (Diğer Davalı)") in kayitlar

    ikinci = yb.kos(fabrika, adimlar=[2], apply=True, kim="test-kullanici", cikti_dizini=tmp_path / "ikinci")
    assert ikinci.yazildi and ikinci.toplam_satir == 0
    assert len(_tarihce(fabrika)) == 5 and _taraflar(fabrika) == taraf
