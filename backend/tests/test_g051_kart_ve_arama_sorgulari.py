"""G051 — FAZ E1 + E3: dava kartının sorgu sayısı + aramanın atılan COUNT'u.

İki iddia kilitlenir, ikisi de SQL SAYARAK (assert'ler ölçüme dayanır,
"öyle olması gerekir"e değil — sayaç `before_cursor_execute` olayından gelir):

1. **E3 (uygulandı).** `search_cases` toplamı zaten ATIYOR
   (`items, _total = get_cases(...)`), ama `get_cases` onu her çağrıda
   sayıyordu: her tuş vuruşunda ikinci bir tam tarama. `with_total=False`
   bayrağı COUNT'u kapatır ve toplam yerine `-1` döner. Bayrak YALNIZ
   `search_cases`'te verilir — liste yolu (`routes/cases.py` → `X-Total-Count`)
   asla vermez; o sözleşmenin ağı `test_cases_pagination.py`dir ve bu görevde
   dokunulmamıştır.

2. **E1 (UYGULANMADI — gerekçe ölçüm).** Plan kartta "N+1" görüyordu; ölçüm
   teşhisi doğrulamadı. Kart TEK satırdır: `selectinload` bir ilişki sorgusunu
   yine bir ilişki sorgusuna indirir. Lokal prod kopyasında (14.345 aktif dava,
   14 kart × 10 tekrar, 2026-08-12) lazy 6 sorgu / 2,90 ms; selectinload×5
   6 sorgu / 3,70 ms; zincirli `documents.case_party` ile 6-7 sorgu / 3,88 ms.
   Yani eager varyant sorgu SAYMIYOR, yalnız yavaşlatıyordu — bu yüzden
   `get_case` lazy bırakıldı. Buradaki testler kararı bir sabite bağlar:
   kart sorgu sayısı SABİTTİR (satır sayısıyla büyümez). Gerçek bir N+1
   (örn. belge başına `case_party` sorgusu) doğarsa test kırmızıya döner —
   yani "eager gerekmiyor" iddiası sürekli sınanır.

sqlite + StaticPool deseni G045/G046 ile aynı.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models


@pytest.fixture()
def db_env(monkeypatch):
    """In-memory sqlite + `case_manager.SessionLocal` yönlendirmesi + SQL sayacı."""
    from database import Base
    from managers import case_manager

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(case_manager, "SessionLocal", maker)

    statements: list = []

    @event.listens_for(engine, "before_cursor_execute")
    def _kaydet(conn, cursor, stmt, params, ctx, many):
        statements.append(stmt)

    yield SimpleNamespace(sessions=maker, manager=case_manager, statements=statements)
    engine.dispose()


_SIRA = [0]


def _dava_yaz(db_env, *, belge_sayisi: int, taraf_sayisi: int = 2) -> int:
    """Kartın okuduğu BEŞ ilişkiyi de dolduran kayıt üretir.

    Belgelerin `case_party_id`si DOLU verilir: kartta `d.case_party.name`
    okunuyor ve gerçek N+1 riski tam olarak burada.
    """
    db = db_env.sessions()
    _SIRA[0] += 1
    try:
        case = models.Case(tracking_no=f"HA.TEST.{_SIRA[0]:04d}.2026",
                           esas_no="2026/1", court="Ankara 1. Asliye Hukuk",
                           status="DERDEST", active=True)
        db.add(case)
        db.flush()
        parties = []
        for i in range(taraf_sayisi):
            p = models.CaseParty(case_id=case.id, name=f"Taraf {i}", role="Davacı",
                                 party_type="CLIENT")
            db.add(p)
            parties.append(p)
        db.add(models.CaseLawyer(case_id=case.id, name="Av. Deneme"))
        db.add(models.CaseEsasNumber(case_id=case.id, esas_no="2026/1", stage="ILK_DERECE",
                                     is_current=True))
        db.add(models.CaseHistory(case_id=case.id, field_name="status", old_value="",
                                  new_value="DERDEST", changed_by="test"))
        db.flush()
        for i in range(belge_sayisi):
            db.add(models.CaseDocument(
                case_id=case.id, original_filename=f"belge{i}.pdf",
                stored_filename=f"s{i}.pdf", belge_turu_kodu="TEBLIGAT______",
                case_party_id=parties[i % len(parties)].id,
            ))
        db.commit()
        return case.id
    finally:
        db.close()


def _sorgular(db_env, fn, *args, **kwargs):
    """Çağrı sırasında koşan SQL ifadelerini ve dönüşü verir."""
    db_env.statements.clear()
    sonuc = fn(*args, **kwargs)
    return sonuc, list(db_env.statements)


# ═══════════════════════════════════════════════════════════════════════════
# 1. E1 — kart sorgu sayısı sabittir (belge/taraf sayısıyla büyümez)
# ═══════════════════════════════════════════════════════════════════════════

def test_kart_sorgu_sayisi_belge_sayisiyla_buyumuyor(db_env):
    """1 belgeli ve 20 belgeli kart AYNI sayıda sorgu koşmalı.

    Büyüyorsa gerçek bir N+1 vardır (en olası aday: belge başına
    `case_party` yüklemesi) ve o zaman eager yükleme tartışılır. Sabit
    kaldığı sürece `get_case`'e `selectinload` eklemek yalnız maliyettir.
    """
    kucuk = _dava_yaz(db_env, belge_sayisi=1)
    buyuk = _dava_yaz(db_env, belge_sayisi=20)

    _, az = _sorgular(db_env, db_env.manager.get_case, kucuk)
    _, cok = _sorgular(db_env, db_env.manager.get_case, buyuk)

    assert len(az) == len(cok), (
        "kart sorgu sayısı belge sayısıyla büyüyor (N+1): "
        f"1 belge={len(az)}, 20 belge={len(cok)}\n" + "\n".join(cok)
    )


def test_kart_iliski_basina_tek_sorgu_kosuyor(db_env):
    """Dava satırı + beş ilişki = 6 SQL. Sayı değişirse gerekçesi olmalı.

    Bu sabit, "kart 5 sorgu koşuyor, selectinload'la azalır" varsayımının
    ölçülmüş hâlidir: azalmıyor — lazy de eager de ilişki başına tek sorgu.
    """
    case_id = _dava_yaz(db_env, belge_sayisi=3)

    kart, sqls = _sorgular(db_env, db_env.manager.get_case, case_id)

    assert kart is not None
    assert len(sqls) == 6, (
        "kartın sorgu sayısı 6 (dava + parties/lawyers/esas_numbers/history/documents) "
        f"değil {len(sqls)}:\n" + "\n".join(sqls)
    )
    assert len(kart["documents"]) == 3
    assert all(d["case_party_name"] for d in kart["documents"]), (
        "taraf adı kartta boş — testin N+1 riskini gerçekten sürdüğü varsayımı düşer"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. E3 — arama COUNT koşmaz, liste yolu koşar
# ═══════════════════════════════════════════════════════════════════════════

def _count_sqls(sqls):
    return [s for s in sqls if "count(" in s.lower()]


def test_arama_count_kosmuyor(db_env):
    _dava_yaz(db_env, belge_sayisi=1)

    items, sqls = _sorgular(db_env, db_env.manager.search_cases, "2026")

    assert isinstance(items, list)
    assert _count_sqls(sqls) == [], (
        "arama hâlâ COUNT koşuyor — her tuş vuruşunda ikinci tam tarama:\n"
        + "\n".join(_count_sqls(sqls))
    )


def test_liste_yolu_count_kosmaya_devam_ediyor(db_env):
    """Varsayılan `with_total=True`: X-Total-Count'un beslendiği yer."""
    _dava_yaz(db_env, belge_sayisi=1)

    (items, total), sqls = _sorgular(db_env, db_env.manager.get_cases, limit=10)

    assert total == len(items) == 1
    assert _count_sqls(sqls), "liste yolunda COUNT kayboldu — X-Total-Count yalan söyler"


def test_with_total_false_toplam_yerine_eksi_bir_donuyor(db_env):
    """`len(items)` DÖNMEZ: gerçek toplam sanılıp sayfalamayı sessizce bozardı."""
    _dava_yaz(db_env, belge_sayisi=1)
    _dava_yaz(db_env, belge_sayisi=1)

    items, total = db_env.manager.get_cases(limit=1, with_total=False)

    assert len(items) == 1
    assert total == -1, f"with_total=False toplam yerine {total!r} döndü"


def test_with_total_sonuc_kumesini_degistirmiyor(db_env):
    """COUNT'u kapatmak yalnız toplamı etkiler; dönen satırlar birebir aynı."""
    _dava_yaz(db_env, belge_sayisi=1)
    _dava_yaz(db_env, belge_sayisi=2)

    sayili, _ = db_env.manager.get_cases(limit=10, with_total=True)
    sayisiz, _ = db_env.manager.get_cases(limit=10, with_total=False)

    assert [c["id"] for c in sayili] == [c["id"] for c in sayisiz]
    assert sayili == sayisiz


def test_with_total_false_yalniz_search_cases_te_kullaniliyor():
    """Denetçinin grep'i test olarak: bayrak liste yoluna sızmamalı.

    Sızdığı gün `X-Total-Count` sayfa uzunluğuna iner ve sayfa çubuğu tek
    sayfaya düşer (bkz. test_cases_pagination.py). Metin taraması değil AST:
    yorum/docstring içinde geçen "with_total=False" çağrı sayılmaz.
    """
    import ast
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    cagrilar = []
    for py in sorted(backend.rglob("*.py")):
        if "tests" in py.parts or "__pycache__" in py.parts:
            continue
        agac = ast.parse(py.read_text(encoding="utf-8"))
        # Her fonksiyonun içindeki çağrıları o fonksiyonun adıyla etiketle
        for kap in ast.walk(agac):
            if not isinstance(kap, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(kap):
                if not isinstance(node, ast.Call):
                    continue
                for kw in node.keywords:
                    if kw.arg != "with_total":
                        continue
                    if isinstance(kw.value, ast.Constant) and kw.value.value is False:
                        cagrilar.append(f"{py.relative_to(backend)}::{kap.name}")

    assert cagrilar == ["managers/case_manager.py::search_cases"], (
        f"with_total=False yalnız search_cases'te olmalı, bulundu: {cagrilar}"
    )
