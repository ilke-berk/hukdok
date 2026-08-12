"""G045 — `case_esas_numbers`: esas numarası tarihçesi tablosu.

Kaynak: docs/plan/faz-f-aktarim-gereksinimleri-2026-08-12.md §1.3.
G044 şartnamenin on kolonunu açtı; on birinci kalem kolon DEĞİL tablodur.

Kilitlenen üç şey:

1. **Şema** — tablo modelde, kısıt/index `("index", ...)` op'unda. G041'in tamir
   ettiği hata tam olarak bunları `("table", ...)` op'una gömmekti; oradan HİÇ
   koşmazlar. Test bu tuzağın tekrarını ada bakarak değil OP TÜRÜNE bakarak
   yakalar.
2. **Türetme kuralı** — `cases.esas_no` = `is_current` satırının kopyası. Üç
   yazma yolunun (add/update/enrich) üçü de aynı fonksiyondan geçmeli; biri
   kaçarsa ikinci doğruluk kaynağı doğar ve tablo yalanlanabilir hâle gelir.
   Bu yüzden testler `sync_current_esas`i doğrudan DEĞİL, gerçek yazma
   yollarından çağırır (sqlite + StaticPool, deseni G044 ile aynı).
3. **Arama** — eski esasla arandığında dosya bulunuyor VE hangi aşamanın
   numarası olduğu söyleniyor. "Bulunuyor" tek başına yetersizdir: listede
   görünen `esas_no` artık başka bir numaradır, sonuç açıklanamaz olur.

Veri dolumu (616 satırlık "Eski Dosya No" sütunu) BU GÖREVDE YOK — ayrıştırma
KURALI burada ve testli, uygulaması FAZ F'nin aktarım scriptinin işi.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import _MIGRATIONS

TABLO = "case_esas_numbers"

# Şartname §1.3: tablo bunların ÜSTÜNE kurulur, yerine değil. Göç FAZ F'nin
# veri işidir; bu görevde kolonların hiçbiri silinmez.
BES_ESKI_KOLON = [
    "esas_no", "yeni_esas_no", "istinaf_esas_no",
    "temyiz_esas_no", "karar_duzeltme_esas_no",
]


def _index_ops(table):
    """`("index", table, [...])` op'larındaki SQL'lerin düz listesi."""
    return [sql for op in _MIGRATIONS if op[0] == "index" and op[1] == table for sql in op[2]]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Şema
# ═══════════════════════════════════════════════════════════════════════════

def test_model_ve_kolonlar_sartnameye_uygun():
    row = models.CaseEsasNumber
    assert row.__tablename__ == TABLO
    columns = row.__table__.columns
    assert set(columns.keys()) == {
        "id", "case_id", "esas_no", "stage", "court", "is_current", "source", "created_at",
    }
    assert columns["esas_no"].type.length == 50
    assert columns["stage"].type.length == 20
    assert columns["court"].type.length == 200
    assert columns["source"].type.length == 100
    # Zorunlular: numarasız/aşamasız satır tarihçeyi anlamsızlaştırır
    assert not columns["case_id"].nullable
    assert not columns["esas_no"].nullable
    assert not columns["stage"].nullable
    assert not columns["is_current"].nullable
    assert columns["is_current"].default.arg is False


def test_case_silinince_tarihce_de_dusuyor():
    """Dava kaydı gidince öksüz esas satırı kalmamalı (ORM + DB, iki taraflı)."""
    fk = list(models.CaseEsasNumber.__table__.c.case_id.foreign_keys)[0]
    assert fk.ondelete == "CASCADE"
    assert models.Case.esas_numbers.property.cascade.delete_orphan


def test_id_ve_case_id_uzerinde_index_true_yok():
    """G042 dersi: `id` index'i PK ikizi olurdu, `case_id`yi uq_case_esas karşılar.

    `index=True` yazmak `ix_case_esas_numbers_id` / `..._case_id` üretir; ilki
    doğrudan G042'nin düşürdüğü sınıftır, ikincisi (case_id, esas_no, stage)
    unique index'inin ÖNEK kolonuyla zaten kapsanır (G043'te
    `case_relations.source_case_id` için verilen kararın aynısı).
    """
    columns = models.CaseEsasNumber.__table__.columns
    assert not columns["id"].index
    assert not columns["case_id"].index
    assert not columns["esas_no"].index, "index migrasyonda tanımlı, modelde değil"


def test_kisit_ve_indexler_index_opunda():
    """G041 tuzağı: kısıt/index tablo op'una gömülürse HİÇ koşmaz."""
    sqls = _index_ops(TABLO)
    assert sqls, f"{TABLO} için ('index', ...) op'u yok"
    birlesik = " | ".join(sqls)
    assert "uq_case_esas " in birlesik and "(case_id, esas_no, stage)" in birlesik
    assert "uq_case_esas_current" in birlesik
    assert "idx_case_esas_numbers_esas_no" in birlesik
    # Hepsi idempotent olmalı: ikinci açılışta migrasyon patlamamalı
    for sql in sqls:
        assert "IF NOT EXISTS" in sql, sql


def test_tablo_op_u_bilincli_yok_create_all_yaratiyor():
    """Tablo modelde tanımlı → create_all yaratır; ('table', ...) op'u ölü kod olurdu.

    init_db önce create_all koşturur, migrasyon tablo listesini SONRA okur:
    modelde tanımlı bir tablo için tablo op'u HER kurulumda atlanır. G044'ün iki
    referans listesi (alleged_faults/appealing_parties) de aynı yoldan doğdu.
    """
    assert not [op for op in _MIGRATIONS if op[0] == "table" and op[1] == TABLO]
    from database import Base
    assert TABLO in Base.metadata.tables


def test_guncel_satir_kisiti_kismi_unique():
    """Dava başına en fazla bir `is_current` — kural yorumda değil şemada.

    Türetme kuralının ("cases.esas_no = is_current satırının kopyası") tek
    yazma yoluna bırakılması yetmez: yarın bir aktarım scripti doğrudan INSERT
    ederse kısıt son savunmadır.

    G049: bu test METNE bakar ve BİLEREK KALIR — migrasyonun kısıtı tanımlamayı
    bırakmasını (silinmesini/daraltılmasını) yakalayan tek kontrol budur; kısıt
    şemadan çıkarsa davranış testi de sessizce yeşile döner. Metin testinin
    YALNIZ BAŞINA yeterli sanılması G045'in RET sebebiydi, o yüzden yanına iki
    davranış testi eklendi: `test_guncel_satir_kisiti_davranista_zorlaniyor`
    (sqlite, fixture artık migrasyon index'lerini kuruyor) ve gerçek Postgres'e
    karşı `test_migration_path.py::test_esas_geri_donusu_kismi_unique_*`.
    """
    sql = next(s for s in _index_ops(TABLO) if "uq_case_esas_current" in s)
    assert "UNIQUE" in sql.upper()
    assert "(case_id)" in sql
    assert "WHERE is_current" in sql


def test_bes_eski_kolon_silinmedi():
    """Bu görev taşıma değil, üstüne kurma (kabul kriteri)."""
    for column in BES_ESKI_KOLON:
        assert hasattr(models.Case, column), f"cases.{column} kaybolmuş"
    droplar = [c for op in _MIGRATIONS if op[0] == "drop" and op[1] == "cases" for c in op[2]]
    assert not set(droplar) & set(BES_ESKI_KOLON)


def test_semalar_tarihceyi_tasiyor():
    from schemas import CaseListRead, CaseRead

    assert "esas_numbers" in CaseRead.model_fields
    assert CaseRead(id=1, tracking_no="HA.X.0001.2026", status="DERDEST",
                    created_at="2026-08-12T00:00:00").esas_numbers == []
    # Liste yanıtı response_model'den geçer: eklenmezse esas_matches sessizce düşerdi
    assert "esas_matches" in CaseListRead.model_fields


# ═══════════════════════════════════════════════════════════════════════════
# 2. Ayrıştırma kuralı — "2017/325 - 2024/145"
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("raw, beklenen", [
    ("2017/325 - 2024/145", ["2017/325", "2024/145"]),          # şartname örneği
    ("2021/588", ["2021/588"]),
    ("2017/325-2024/145", ["2017/325", "2024/145"]),            # boşluksuz ayırıcı
    ("2017/325, 2024/145; 2025/9", ["2017/325", "2024/145", "2025/9"]),
    ("E. 2019/12 K. 2019/12", ["2019/12"]),                     # tekilleşme
    ("2024 / 0123", ["2024/0123"]),                             # sıfır dolgusu KORUNUR
    ("", []),
    (None, []),
    ("BİLİNMİYOR", []),
    ("Yok - -", []),
])
def test_parse_esas_history(raw, beklenen):
    from managers.case_manager import parse_esas_history

    assert parse_esas_history(raw) == beklenen


def test_parse_esas_history_uzun_rakam_dizisini_yutmuyor():
    """Hasar dosya numarası gibi uzun sayılar esas sanılmamalı."""
    from managers.case_manager import parse_esas_history

    assert parse_esas_history("12020/1234567890") == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. Türetme kuralı — gerçek yazma yolları (sqlite)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db_env(monkeypatch):
    """Paylaşılan in-memory sqlite + case_manager.SessionLocal yönlendirmesi.

    G049 — HARNESS KÖRLÜĞÜ KAPATILDI: `create_all` yalnız MODELDEKİ kısıtları
    kurar; `uq_case_esas_current` gibi yalnız migrasyonda tanımlı kısmi unique
    index'ler sqlite'ta hiç oluşmuyordu. Sonuç: G045'in "geri dönüş" testi
    burada yeşil, gerçek Postgres'te `duplicate key ... uq_case_esas_current`
    ile 500'dü. Migrasyonun `("index", TABLO, ...)` SQL'leri fixture'a OLDUĞU
    GİBİ uygulanır — sqlite de kısmi unique index destekler, dolayısıyla kısıt
    artık birim koşuda da gerçekten zorlanır. SQL'ler elle tekrarlanmaz:
    migrasyon değişirse fixture kendiliğinden uyar.
    """
    from database import Base
    from managers import case_manager

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for sql in _index_ops(TABLO):
            conn.execute(text(sql))
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", maker)
    yield SimpleNamespace(sessions=maker, manager=case_manager)
    engine.dispose()


def _satirlar(db_env, case_id):
    """(esas_no, stage, is_current) üçlüleri — yazılma sırasıyla."""
    db = db_env.sessions()
    try:
        rows = (
            db.query(models.CaseEsasNumber)
            .filter(models.CaseEsasNumber.case_id == case_id)
            .order_by(models.CaseEsasNumber.id)
            .all()
        )
        return [(r.esas_no, r.stage, bool(r.is_current)) for r in rows]
    finally:
        db.close()


def _kolon(db_env, case_id):
    db = db_env.sessions()
    try:
        return db.get(models.Case, case_id).esas_no
    finally:
        db.close()


def _invariant(db_env, case_id):
    """`cases.esas_no` gerçekten is_current satırının kopyası mı?"""
    guncel = [r for r in _satirlar(db_env, case_id) if r[2]]
    assert len(guncel) <= 1, f"birden çok güncel satır: {guncel}"
    kolon = _kolon(db_env, case_id)
    assert [r[0] for r in guncel] == ([kolon] if kolon else []), (
        f"kolon={kolon!r} ile güncel satır {guncel} ayrıştı"
    )


def _dava(db_env, esas_no="2017/325", **extra):
    created = db_env.manager.add_case({
        "tracking_no": extra.pop("tracking_no", "HA.X.0001.2026"),
        "esas_no": esas_no,
        "court": extra.pop("court", "Ankara 5. Asliye Hukuk Mahkemesi"),
        **extra,
    })
    assert created and "id" in created, created
    return created["id"]


def test_add_case_ilk_tarihce_satirini_aciyor(db_env):
    case_id = _dava(db_env)

    assert _satirlar(db_env, case_id) == [("2017/325", "YEREL", True)]
    db = db_env.sessions()
    try:
        row = db.query(models.CaseEsasNumber).first()
        assert row.court == "Ankara 5. Asliye Hukuk Mahkemesi"
        assert row.source == "add_case"
    finally:
        db.close()
    _invariant(db_env, case_id)


def test_add_case_esassiz_dava_tarihce_acmiyor(db_env):
    """Esas henüz yokken (DANIŞ / dava açılmadan) boş satır üretilmemeli."""
    case_id = _dava(db_env, esas_no=None)

    assert _satirlar(db_env, case_id) == []
    assert _kolon(db_env, case_id) is None


def test_update_case_esas_degisince_eskisi_tarihcede_kaliyor(db_env):
    """Görevsizlik sonrası: numara değişir, eskisi KAYITTA kalır."""
    case_id = _dava(db_env)

    assert db_env.manager.update_case(case_id, {"esas_no": "2024/145"}) is True

    assert _satirlar(db_env, case_id) == [
        ("2017/325", "YEREL", False),
        ("2024/145", "YEREL", True),
    ]
    assert _kolon(db_env, case_id) == "2024/145"
    _invariant(db_env, case_id)


def test_ayni_numara_ikinci_kez_yazilinca_yeni_satir_acilmiyor(db_env):
    """Aktarım tekrar tekrar koşacak (§0) — idempotency pazarlıksız."""
    case_id = _dava(db_env)

    db_env.manager.update_case(case_id, {"esas_no": "2024/145"})
    db_env.manager.update_case(case_id, {"esas_no": "2017/325"})   # geri dönüş
    db_env.manager.update_case(case_id, {"esas_no": "2017/325"})   # tekrar

    assert _satirlar(db_env, case_id) == [
        ("2017/325", "YEREL", True),
        ("2024/145", "YEREL", False),
    ]
    _invariant(db_env, case_id)


def test_guncel_satir_kisiti_davranista_zorlaniyor(db_env):
    """Kısıt METİNDE değil ŞEMADA var mı — ikinci güncel satır gerçekten reddediliyor mu?

    G049: `test_guncel_satir_kisiti_kismi_unique` yalnız migrasyon SQL'inin
    metnine bakıyordu; fixture ise kısıtı hiç kurmuyordu. İki kör nokta üst
    üste gelince "kısıt var" iddiası test edilmemiş bir inanç hâline gelmişti.
    Burada doğrudan INSERT edilir — kısıt son savunma olarak deneniyor.
    """
    case_id = _dava(db_env)

    db = db_env.sessions()
    try:
        db.add(models.CaseEsasNumber(
            case_id=case_id, esas_no="2024/145", stage="YEREL", is_current=True,
        ))
        with pytest.raises(IntegrityError):
            db.flush()
    finally:
        db.rollback()
        db.close()

    # Kısıt tutunca tarihçe bozulmadan kaldı
    assert _satirlar(db_env, case_id) == [("2017/325", "YEREL", True)]


def test_esas_gecis_siralari_ileri_geri_tekrar(db_env):
    """G049 kabul kriteri: üç geçiş sırası da kısıtı ihlal etmeden yürüyor.

    G045 denetiminde patlayan sıra GERİ dönüştü: hedef satırın id'si eski
    güncel satırınkinden KÜÇÜK olduğu için SQLAlchemy tek flush'ta önce ona
    True yazıyor ve o an iki güncel satır oluyordu. `sync_current_esas` artık
    düşürmeyi ayrı bir flush'ta önden yazıyor ("önce boşalt, sonra işaretle").

    İnvariant her adımdan SONRA doğrulanır: bir dava başına en fazla bir güncel
    satır ve `cases.esas_no` tam olarak o satırın kopyası.
    """
    case_id = _dava(db_env)                                   # 1. ileri: ilk satır
    _invariant(db_env, case_id)
    assert _satirlar(db_env, case_id) == [("2017/325", "YEREL", True)]

    assert db_env.manager.update_case(case_id, {"esas_no": "2024/145"}) is True
    _invariant(db_env, case_id)                               # 2. ileri: yeni numara
    assert _kolon(db_env, case_id) == "2024/145"

    # 3. GERİ: tarihçedeki DAHA ESKİ (küçük id'li) satıra dönüş — patlayan yol
    assert db_env.manager.update_case(case_id, {"esas_no": "2017/325"}) is True
    _invariant(db_env, case_id)
    assert _satirlar(db_env, case_id) == [
        ("2017/325", "YEREL", True),
        ("2024/145", "YEREL", False),
    ]

    # 4. TEKRAR: aynı numara yeniden yazılıyor (aktarım tekrar koşacak, §0)
    assert db_env.manager.update_case(case_id, {"esas_no": "2017/325"}) is True
    _invariant(db_env, case_id)
    assert _satirlar(db_env, case_id) == [
        ("2017/325", "YEREL", True),
        ("2024/145", "YEREL", False),
    ]


def test_enrich_case_de_ayni_yoldan_geciyor(db_env):
    """Belgeden zenginleştirme (Faz 7) tarihçeyi ATLAMAMALI."""
    case_id = _dava(db_env)

    result = db_env.manager.enrich_case(
        case_id, {"esas_no": "2024/145"}, [],
        changed_by="ilke@lexis.com.tr", source="intake-enrich: tensip.pdf",
    )
    assert result and not result.get("error"), result

    assert _satirlar(db_env, case_id) == [
        ("2017/325", "YEREL", False),
        ("2024/145", "YEREL", True),
    ]
    _invariant(db_env, case_id)


def test_enrich_case_uzun_source_kolona_sigacak_sekilde_kirpiliyor(db_env):
    """`source` VARCHAR(100); belge adı uzun olabilir — kayıt 500 olmamalı."""
    case_id = _dava(db_env, esas_no=None)
    uzun = "intake-enrich: " + ("t" * 300) + ".pdf"

    db_env.manager.enrich_case(case_id, {"esas_no": "2024/145"}, [],
                               changed_by="x@y.z", source=uzun)

    db = db_env.sessions()
    try:
        row = db.query(models.CaseEsasNumber).one()
        assert len(row.source) == 100
        assert row.source.startswith("intake-enrich: ")
    finally:
        db.close()


def test_esas_silinince_tarihce_korunuyor_guncel_isaret_dusuyor(db_env):
    """Alan temizlense bile geçmiş numaralar kayıt değeridir — SİLİNMEZ."""
    case_id = _dava(db_env)

    db_env.manager.enrich_case(case_id, {"esas_no": None}, [],
                               changed_by="x@y.z", source="auto-enrich")

    assert _satirlar(db_env, case_id) == [("2017/325", "YEREL", False)]
    assert _kolon(db_env, case_id) is None
    _invariant(db_env, case_id)


def test_kolona_sigmayan_esas_kaydi_500e_cevirmiyor(db_env):
    """`cases.esas_no` sınırsız TEXT, tarihçe VARCHAR(50).

    Çöp uzunlukta bir değer bugüne kadar sorunsuz kaydediliyordu; tarihçe
    uğruna kaydı düşürmek davranış regresyonu olurdu.

    BİLİNÇLİ TAVİZ: bu tek durumda kolonun tarihçede karşılığı yoktur. Yine de
    ESKİ güncel işaret düşürülür — "güncel" diye eski numarayı göstermek,
    hiçbir şey göstermemekten kötüdür (tam da kaçınılan ikinci kaynak).
    """
    case_id = _dava(db_env)
    cop = "2017/" + "9" * 80

    assert db_env.manager.update_case(case_id, {"esas_no": cop}) is True

    assert _kolon(db_env, case_id) == cop
    assert _satirlar(db_env, case_id) == [("2017/325", "YEREL", False)]
    # Yalancı "güncel" satır kalmadı (invariantın koruduğu asıl şey)
    assert not [r for r in _satirlar(db_env, case_id) if r[2]]


def test_bilinmeyen_asama_reddediliyor():
    """Aşama kapalı kümedir; yazım hatası sessizce yeni bir "aşama" yaratmasın."""
    from managers.case_manager import ESAS_STAGES, sync_current_esas

    assert ESAS_STAGES == ("YEREL", "ISTINAF", "TEMYIZ", "KARAR_DUZELTME", "ONCEKI")
    with pytest.raises(ValueError):
        sync_current_esas(None, models.Case(), "2024/1", stage="ISTINAAF")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Okuma yolu + arama
# ═══════════════════════════════════════════════════════════════════════════

def test_dava_karti_tarihceyi_donduruyor(db_env):
    case_id = _dava(db_env)
    db_env.manager.update_case(case_id, {"esas_no": "2024/145"})

    result = db_env.manager.get_case(case_id)

    assert result["esas_no"] == "2024/145"
    # Güncel satır önce — kart "bugünkü numara" ile açılır
    assert [(e["esas_no"], e["stage"], e["is_current"]) for e in result["esas_numbers"]] == [
        ("2024/145", "YEREL", True),
        ("2017/325", "YEREL", False),
    ]
    assert result["esas_numbers"][0]["court"] == "Ankara 5. Asliye Hukuk Mahkemesi"


def test_eski_esasla_arama_dosyayi_buluyor_ve_asamayi_soyluyor(db_env):
    """Kabul kriteri: "2021/588" gibi ÖNCEKİ bir esasla arama dosyayı döndürür."""
    case_id = _dava(db_env, esas_no="2021/588")
    db_env.manager.update_case(case_id, {"esas_no": "2024/145"})

    items, total = db_env.manager.get_cases(q="2021/588")

    assert total == 1 and [i["id"] for i in items] == [case_id]
    bulunan = items[0]
    # Listede görünen numara ARTIK BAŞKA — sonuç ancak eşleşen satırla açıklanır
    assert bulunan["esas_no"] == "2024/145"
    assert bulunan["esas_matches"] == [{
        "esas_no": "2021/588", "stage": "YEREL",
        "court": "Ankara 5. Asliye Hukuk Mahkemesi",
        "is_current": False, "source": "add_case",
    }]


def test_guncel_esasla_arama_bozulmadi(db_env):
    case_id = _dava(db_env, esas_no="2021/588")

    items, total = db_env.manager.get_cases(q="2021/588", exact=True)

    assert total == 1 and items[0]["id"] == case_id
    assert items[0]["esas_matches"][0]["is_current"] is True


def test_eslesmeyen_aramada_esas_matches_bos(db_env):
    """Sözleşme sabit: alan her zaman var, eşleşme yoksa boş liste."""
    _dava(db_env, esas_no="2021/588")

    items, _ = db_env.manager.get_cases(q="Ankara")

    assert items and items[0]["esas_matches"] == []


def test_arama_yokken_de_alan_var(db_env):
    _dava(db_env)

    items, _ = db_env.manager.get_cases()

    assert items[0]["esas_matches"] == []


def test_baska_davanin_tarihcesi_sonuca_karismiyor(db_env):
    """Toplu sorgu case_id'ye göre dağıtılmalı — çapraz sızıntı olmamalı."""
    ilk = _dava(db_env, esas_no="2021/588")
    ikinci = _dava(db_env, esas_no="2021/588", tracking_no="HA.X.0002.2026")
    db_env.manager.update_case(ikinci, {"esas_no": "2024/145"})

    items, total = db_env.manager.get_cases(q="2021/588")

    assert total == 2
    esaslar = {i["id"]: [m["esas_no"] for m in i["esas_matches"]] for i in items}
    assert esaslar == {ilk: ["2021/588"], ikinci: ["2021/588"]}
