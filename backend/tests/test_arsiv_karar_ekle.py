"""Büro karar arşivinin kartlara arşiv belgesi olarak eklenmesi (05.10.2026).

Kapsam: `scripts/arsiv_karar_ekle` — föy → kart, künye → aşama kararı (tahmin yok),
belge türü kuralı, mükerrer koruması, kuru koşu; migrasyon 60'ın kolon + koşulsuz
index op'u.
"""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS, Base
from scripts import arsiv_karar_ekle as ak

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _index_ops(table):
    return [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == table
            for sql in op[2] if not sql.lstrip().upper().startswith(("UPDATE", "ALTER", "DO"))]


@pytest.fixture()
def fabrika():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for sql in _index_ops("case_documents"):
            if "uq_case_docs_kart_sha" in sql or "idx_case_docs_asama_karari" in sql:
                conn.execute(text(sql))
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


def _kart(db, tno, foyler, asamalar=()):
    """asamalar: [(stage, sira, mahkeme, esas, tarih)] → kart"""
    kart = models.Case(tracking_no=tno, status="DERDEST", court="Bolu 2. Asliye Hukuk Mahkemesi", file_type="Hukuk")
    db.add(kart)
    db.flush()
    for no in foyler:
        db.add(models.CaseFoy(sistem_no=no, case_id=kart.id))
    for stage, sira, mahkeme, esas, tarih in asamalar:
        db.add(models.CaseStageDecision(case_id=kart.id, stage=stage, sira_no=sira, mahkeme=mahkeme,
                                        esas_no=esas, karar_tarihi=tarih, dogrulama_durumu="TURETILDI"))
    db.flush()
    return kart


def _satir(dosya, sha, foyler, **ek):
    temel = {"dosya": dosya, "sha256": sha, "foyler": foyler, "belge_tarihi": "", "mahkeme_etiketi": "",
             "esas_no": "", "asama_mahkeme": "", "asama_esas": "", "asama_tarih": ""}
    temel.update(ek)
    return temel


def _belgeler(fabrika):
    db = fabrika()
    try:
        return db.query(models.CaseDocument).order_by(models.CaseDocument.id).all()
    finally:
        db.close()


@pytest.fixture()
def kartli(fabrika):
    db = fabrika()
    kart = _kart(db, "DR.T.TEST-0001-HUK", ["H-1", "H-2"], [
        ("YEREL", 1, "Bolu 2. Asliye Hukuk Mahkemesi", "2021/124", date(2022, 3, 10)),
        ("ISTINAF", 1, "Ankara BAM 3. HD", "2022/900", date(2023, 5, 4)),
        ("TEMYIZ", 1, "Yargıtay 4. HD", None, None),
    ])
    baska = _kart(db, "DR.T.TEST-0002-HUK", ["H-9"])
    idler = (kart.id, baska.id)
    db.commit()
    db.close()
    return fabrika, idler


def test_belge_turu_mahkeme_etiketinden():
    assert ak.belge_turu("DANISTAY_10_DAIRE") == ak.TUR_DANISTAY
    assert ak.belge_turu("YARGITAY_4_HD") == ak.TUR_YARGITAY
    assert ak.belge_turu("ISTANBUL_BAM_14_HD") == ak.TUR_ISTINAF
    assert ak.belge_turu("IZMIR_BIM_6_IDD") == ak.TUR_ISTINAF
    assert ak.belge_turu("ANAYASA_MAHKEMESI") == ak.TUR_AYM
    assert ak.belge_turu("BOLU_2_ASLIYE_HUKUK") == ak.TUR_GEREKCELI
    # "BAMBU" gibi bir yer adı istinaf sayılmaz: BAM / BİM ayrı sözcük olmalı
    assert ak.belge_turu("BAMBU_1_ASLIYE_HUKUK") == ak.TUR_GEREKCELI
    assert ak.belge_turu(None) == ak.TUR_GEREKCELI


def test_kuru_kosu_yazmaz_apply_yazar(kartli):
    fabrika, (kart_id, _) = kartli
    liste = [_satir("2022-03-10__BOLU_2_ASLIYE_HUKUK__21-124__X__RED__H-1.pdf", SHA_A, "H-1;H-2",
                    belge_tarihi="2022-03-10", mahkeme_etiketi="BOLU_2_ASLIYE_HUKUK", esas_no="2021/124")]
    kuru = ak.kos(fabrika, liste)
    assert kuru.say()[ak.EKLENDI] == 1 and not kuru.yazildi
    assert _belgeler(fabrika) == []

    with pytest.raises(ValueError):
        ak.kos(fabrika, liste, apply=True)

    sonuc = ak.kos(fabrika, liste, apply=True, kim="test")
    assert sonuc.yazildi and sonuc.asamali == 1 and sonuc.kart_sayisi == 1
    (b,) = _belgeler(fabrika)
    assert b.case_id == kart_id and b.dosya_sha256 == SHA_A
    assert b.belge_turu_kodu == "GEREKCELIKRR" and b.link_mode == "LINKED"
    assert b.sharepoint_url is None and b.uploaded_by == "ARSIV_AKTARIM:test"
    assert b.uploaded_at.date() == date(2022, 3, 10)        # yükleme anı değil, karar tarihi
    assert b.uploaded_by_email is None and b.email_sent is None


def test_asama_bagi_tahmin_edilmez(kartli):
    fabrika, _ = kartli
    liste = [
        # esas + tarih → yerel aşama
        _satir("a.pdf", SHA_A, "H-1", belge_tarihi="2022-03-10", esas_no="2021/124"),
        # dosya adı ilk derece esasını taşıyor, paketin aşama künyesi istinafı gösteriyor → istinaf
        _satir("b.pdf", SHA_B, "H-1", belge_tarihi="2023-05-04", esas_no="2021/124", mahkeme_etiketi="ANKARA_BAM_3_HD",
               asama_mahkeme="Ankara BAM 3. HD", asama_esas="2022/900", asama_tarih="2023-05-04"),
        # künyesi hiçbir satırla tutmuyor → karta girer, bağ boş
        _satir("c.pdf", SHA_C, "H-1", belge_tarihi="2019-01-01", esas_no="2018/7"),
    ]
    ak.kos(fabrika, liste, apply=True, kim="test")
    db = fabrika()
    try:
        asama = {a.id: a.stage for a in db.query(models.CaseStageDecision).all()}
        bag = {b.original_filename: asama.get(b.asama_karari_id) for b in db.query(models.CaseDocument).all()}
    finally:
        db.close()
    assert bag == {"a.pdf": "YEREL", "b.pdf": "ISTINAF", "c.pdf": None}


def test_ayni_esasli_iki_asama_mahkemeyle_ayrilir_ayrilmazsa_bag_yok(fabrika):
    db = fabrika()
    _kart(db, "DR.T.TEST-0003-HUK", ["H-5"], [
        ("YEREL", 1, "Bolu 2. Asliye Hukuk Mahkemesi", "2021/124", None),
        ("ISTINAF", 1, "Ankara BAM 3. HD", "2021/124", None),
    ])
    db.commit()
    asamalar = db.query(models.CaseStageDecision).all()
    assert ak.asama_bul(asamalar, "2021/124", None, None) is None
    assert ak.asama_bul(asamalar, "2021/124", None, "ANKARA BAM 3.HD").stage == "ISTINAF"
    assert ak.asama_bul(asamalar, "2021/0124 E.", None, "Bolu 2. Asliye Hukuk Mahkemesi").stage == "YEREL"
    db.close()


def test_mukerrer_ve_baglanamayanlar(kartli):
    fabrika, (kart_id, baska_id) = kartli
    liste = [
        _satir("a.pdf", SHA_A, "H-1"),
        _satir("a_kopya.pdf", SHA_A, "H-2"),            # aynı kart, aynı parmak izi
        _satir("b.pdf", SHA_B, "H-1;H-9"),              # iki karta gidiyor: kart seçilmez
        _satir("c.pdf", SHA_C, "H-404"),                # föy yok
        _satir("d.pdf", "kisa", "H-1"),                 # bozuk parmak izi
        _satir("e.pdf", SHA_A, "H-9"),                  # aynı dosya BAŞKA kartta: eklenir
    ]
    ilk = ak.kos(fabrika, liste, apply=True, kim="test")
    assert ilk.say() == {ak.EKLENDI: 2, ak.ZATEN_VAR: 1, ak.COK_KART: 1, ak.FOY_YOK: 1, ak.GIRDI_HATALI: 1}
    assert sorted(b.case_id for b in _belgeler(fabrika)) == sorted([kart_id, baska_id])

    ikinci = ak.kos(fabrika, liste, apply=True, kim="test")       # yeniden koşulabilir
    assert ikinci.say()[ak.EKLENDI] == 0 and ikinci.say()[ak.ZATEN_VAR] == 3
    assert len(_belgeler(fabrika)) == 2


def test_aciklama_sutunu_ozete_eklenir(kartli):
    fabrika, _ = kartli
    ak.kos(fabrika, [_satir("a.pdf", SHA_A, "H-1"),
                     _satir("b.pdf", SHA_B, "H-1", aciklama="Olası eşleşme: taraf adı + mahkeme.")], apply=True, kim="test")
    ozet = {b.original_filename: b.ai_summary for b in _belgeler(fabrika)}
    assert ozet["a.pdf"] == "Büro karar arşivinden aktarıldı."
    assert ozet["b.pdf"] == "Büro karar arşivinden aktarıldı. Olası eşleşme: taraf adı + mahkeme."


def test_silinmis_karta_eklenmez(kartli):
    fabrika, (kart_id, _) = kartli
    db = fabrika()
    db.get(models.Case, kart_id).deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.close()
    sonuc = ak.kos(fabrika, [_satir("a.pdf", SHA_A, "H-1")], apply=True, kim="test")
    assert sonuc.say() == {ak.KART_SILINMIS: 1}
    assert _belgeler(fabrika) == []


def _yuklemeye_hazir(fabrika, tmp_path):
    """İki kartta üç belge kaydı (a.pdf iki kartta), yerelde a.pdf + b.pdf; c.pdf yerelde yok."""
    import hashlib
    icerik = {"a.pdf": b"A" * 10, "b.pdf": b"B" * 20}
    for ad, veri in icerik.items():
        (tmp_path / ad).write_bytes(veri)
    sha = {ad: hashlib.sha256(veri).hexdigest() for ad, veri in icerik.items()}
    ak.kos(fabrika, [_satir("a.pdf", sha["a.pdf"], "H-1"), _satir("a.pdf", sha["a.pdf"], "H-9"),
                     _satir("b.pdf", sha["b.pdf"], "H-1"), _satir("c.pdf", SHA_C, "H-1")], apply=True, kim="test")


def test_yukle_kuru_kosu_yuklemez_apply_url_yazar(kartli, tmp_path):
    fabrika, _ = kartli
    _yuklemeye_hazir(fabrika, tmp_path)
    yuklenen = []

    def yukleyici(yol, ad, klasor):
        yuklenen.append((ad, klasor))
        return {"webUrl": f"https://arsiv/{klasor}/{ad}"}

    kuru = ak.yukle(fabrika, tmp_path, mevcut=lambda klasor, ad: None, yukleyici=yukleyici)
    assert kuru.say() == {ak.YUKLENECEK: 2, ak.DOSYA_YOK: 1} and yuklenen == []
    assert all(b.sharepoint_url is None for b in _belgeler(fabrika))

    sonuc = ak.yukle(fabrika, tmp_path, apply=True, mevcut=lambda klasor, ad: None, yukleyici=yukleyici)
    assert sonuc.say() == {ak.YUKLENDI: 2, ak.DOSYA_YOK: 1}
    assert sorted(ad for ad, _ in yuklenen) == ["a.pdf", "b.pdf"]      # iki karttaki a.pdf BİR KEZ yüklendi
    url = {(b.original_filename, b.case_id): (b.sharepoint_url, b.upload_status) for b in _belgeler(fabrika)}
    assert sum(1 for (ad, _), (u, d) in url.items() if ad == "a.pdf" and u and d == "uploaded") == 2
    assert [u for (ad, _), (u, _) in url.items() if ad == "c.pdf"] == [None]

    # yeniden koşu: URL'i yazılmış kayıt kapsam dışı, yalnız dosyası olmayan kalır
    tekrar = ak.yukle(fabrika, tmp_path, apply=True, mevcut=lambda klasor, ad: None, yukleyici=yukleyici)
    assert tekrar.say() == {ak.DOSYA_YOK: 1} and len(yuklenen) == 2


def test_yukle_arsivdeki_dosyayi_ezmez(kartli, tmp_path):
    fabrika, _ = kartli
    _yuklemeye_hazir(fabrika, tmp_path)
    yuklenen = []
    arsiv = {"a.pdf": {"size": 10, "webUrl": "https://arsiv/a-onceki"},      # aynı boyut: önceki koşumuz
             "b.pdf": {"size": 999, "webUrl": "https://arsiv/b-baskasi"}}    # başka dosya: dokunma
    sonuc = ak.yukle(fabrika, tmp_path, apply=True, mevcut=lambda klasor, ad: arsiv.get(ad),
                     yukleyici=lambda yol, ad, klasor: yuklenen.append(ad) or {"webUrl": "x"})
    assert sonuc.say() == {ak.ARSIVDE_VARDI: 1, ak.AD_CAKISMASI: 1, ak.DOSYA_YOK: 1}
    assert yuklenen == []
    url = {b.original_filename: b.sharepoint_url for b in _belgeler(fabrika)}
    assert url["a.pdf"] == "https://arsiv/a-onceki" and url["b.pdf"] is None


def test_yukle_bozuk_dosya_ve_ardisik_hata(kartli, tmp_path, monkeypatch):
    fabrika, _ = kartli
    _yuklemeye_hazir(fabrika, tmp_path)
    (tmp_path / "b.pdf").write_bytes(b"degisti")                # parmak izi artık tutmuyor

    def patlayan(yol, ad, klasor):
        raise RuntimeError("ağ yok")

    monkeypatch.setattr(ak, "ARDISIK_HATA_SINIRI", 1)
    sonuc = ak.yukle(fabrika, tmp_path, apply=True, mevcut=lambda klasor, ad: None, yukleyici=patlayan, is_parcacigi=1)
    assert sonuc.durduruldu and sonuc.satirlar[0].sonuc == ak.YUKLEME_HATASI
    assert all(b.sharepoint_url is None for b in _belgeler(fabrika))

    monkeypatch.setattr(ak, "ARDISIK_HATA_SINIRI", 15)
    sonuc = ak.yukle(fabrika, tmp_path, apply=True, mevcut=lambda klasor, ad: None,
                     yukleyici=lambda yol, ad, klasor: {"webUrl": "u"})
    assert sonuc.say() == {ak.YUKLENDI: 1, ak.SHA_FARKLI: 1, ak.DOSYA_YOK: 1}


def test_migrasyon_60_kolon_ve_kosulsuz_index():
    kolonlar = [op for op in _MIGRATIONS if op[0] == "columns" and op[1] == "case_documents"
                and "dosya_sha256" in op[2]]
    assert len(kolonlar) == 1 and "asama_karari_id" in kolonlar[0][2]
    assert "ON DELETE SET NULL" in kolonlar[0][2]["asama_karari_id"]
    indexler = " ".join(_index_ops("case_documents"))
    # kalıcı kısıt "columns" op'una gömülmez (koşullu op tuzağı): ayrı, koşulsuz op'ta
    assert "uq_case_docs_kart_sha" in indexler and "idx_case_docs_asama_karari" in indexler
    assert "deleted_at IS NULL" in indexler
