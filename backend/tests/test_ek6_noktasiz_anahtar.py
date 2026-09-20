"""Ek-6 › 02 sınıf A (17.09.2026) — DosyaNo köprüsünün noktasız ikincil anahtarı.

Ekip: aynı numaranın iki yazımı ("1976.001" ↔ "1.976.001") köprüde farklı anahtar
sayıldığı için paket kartı bulamadı ve ikinci kart açıldı (4 dava: 4966/14482,
4903/14478, 13995/14495, 14330/14511). Kural: birincil anahtar HİÇ tutmazsa
noktasız biçimle ikinci tur; yalnız TEK aday varsa eşleşir — iki kart aynı noktasız
biçime düşüyorsa (temizlik öncesi hâl) eşleşme yapılmaz, satır rapora düşer.

**TEST VERİSİ KURALI (A.2 dersi):** paketler openpyxl ile SENTETİK üretilir.
"""
import models
from scripts import hukdok_aktarim
from scripts.hukdok_aktarim import CIKIS_TAMAM, aktarimi_kos
from tests.test_g064_aktarim_cekirdek import _kart, _paket_yaz, _satir
from tests.test_g153_dosyano_koku import BASLIKLAR_G153, _foy_karti
from tests.test_g178_dosyano_sifir_eki import db_env  # noqa: F401  (fixture)


# ─── Birim ───────────────────────────────────────────────────────────────────

def test_noktasiz_anahtar_yalnizca_noktalari_atar():
    assert hukdok_aktarim._noktasiz_anahtar("1.976.001") == "1976001"
    assert hukdok_aktarim._noktasiz_anahtar("1976.001") == "1976001"
    assert hukdok_aktarim._noktasiz_anahtar("2433.01") == hukdok_aktarim._noktasiz_anahtar("2.433.01")


def test_birincil_anahtar_tutuyorsa_ikincil_tura_gecilmez():
    harita = {"1976.001": [14482], "1.976.001": [4966]}
    assert hukdok_aktarim._dosya_no_adaylari(harita, ["1976.001"]) == [14482]
    assert hukdok_aktarim._dosya_no_adaylari(harita, ["1.976.001"]) == [4966]


def test_tek_aday_varsa_noktasiz_bicimle_eslesir():
    """A sınıfı temizlendikten sonraki hâl: kartta tek yazım kaldı, paket ötekini yolluyor."""
    harita = hukdok_aktarim.DosyaNoKoprusu({"1976.001": [14482], "2.187.00": [4262]})
    assert hukdok_aktarim._dosya_no_adaylari(harita, ["1.976.001"]) == [14482]
    assert hukdok_aktarim._dosya_no_adaylari(harita, ["2433.01"]) == []      # hiçbir biçimde yok


def test_iki_kart_ayni_noktasiz_bicime_dusuyorsa_eslesme_yapilmaz():
    """Temizlik öncesi hâl: belirsizlik korunur — yanlış karta yazmaktansa."""
    harita = {"1976.001": [14482], "1.976.001": [4966]}
    assert hukdok_aktarim._dosya_no_adaylari(harita, ["19.76.001"]) == []


def test_sifir_eki_ayrimi_bozulmaz():
    """".01 AYRI dosyadır" kuralı (G178) ikincil turda da korunur.

    Fonksiyon NORMALİZE parça alır (çağıranlar `_dosya_no_parcalari`den geçirir)."""
    harita = hukdok_aktarim.DosyaNoKoprusu({"2.531.01": [1], "2.531": [2]})
    parca = hukdok_aktarim._dosya_no_parcalari
    assert hukdok_aktarim._dosya_no_adaylari(harita, parca("2.531.00")) == [2]   # birincil: ".00" atılır
    assert hukdok_aktarim._dosya_no_adaylari(harita, parca("2531.01")) == [1]    # ikincil: noktasız
    assert hukdok_aktarim._dosya_no_adaylari(harita, parca("25.31.02")) == []    # başka dosya


# ─── sqlite: uçtan uca ───────────────────────────────────────────────────────

def test_farkli_nokta_yazimi_ikinci_kart_actirmaz(db_env, tmp_path):  # noqa: F811
    """Sınıf A çekirdek vakası: kart `1976.001`, paket `1.976.001` → föy o karta
    bağlanır (bugünkü davranışta "Kart bulunamadı" olur, ikinci kart açılırdı)."""
    db = db_env()
    try:
        kart = _kart(db, "D1.C_HARMANCI.0002.IDARE.00000", "1976.001",
                     file_type="İdare", esas_no="2023/907")
        db.commit()
        kart_id = kart.id
    finally:
        db.close()
    paket = _paket_yaz(tmp_path / "teslim.xlsx", [
        _satir("id-16645", "1.976.001", **{"Ana Tür": "IDARE", "Esas": "2023/907"}),
    ], basliklar=BASLIKLAR_G153)

    sonuc = aktarimi_kos(db_env, girdi=paket, rapor_dizini=tmp_path / "rapor")

    assert sonuc.cikis_kodu == CIKIS_TAMAM and not sonuc.hatalar
    assert _foy_karti(db_env, "id-16645") == kart_id
    db = db_env()
    try:
        assert db.query(models.Case).count() == 1
    finally:
        db.close()
