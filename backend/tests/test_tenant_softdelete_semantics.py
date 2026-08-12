"""G034 — tenant izolasyonu + soft-delete ORM semantiği (KARAKTERİZASYON).

Neden var: `tenant_id == X OR tenant_id IS NULL` deseni merkezî bir helper'da
(`auth_helpers.tenant_filter_clause`) durmasına rağmen kod tabanına **elle
kopyalanmış** hâlleriyle de yaşıyor, ve soft-delete (`deleted_at`) filtresi bu
desenden BAĞIMSIZ olarak her sorguya ayrı ayrı ekleniyor. İkisi tek tek doğru
olup birleşimde kaçan bir kopya, başka tenant'ın ya da silinmiş bir kaydın
kullanıcıya dönmesi demek. FAZ 0.8 tam bu sınıftan bir delik buldu
(`/api/documents` bağlantısız belgeler, bkz. `test_g016_documents_tenant_isolation.py`).

Bu dosya bugünkü davranışı kilitler; FAZ E sorgu yollarını yeniden yazdığında
ağ ısırır. **Kaynak kod DEĞİŞTİRİLMEDİ** — aşağıda bulunan sapmalar da
düzeltilmeden karakterize edildi (bkz. `KNOWN_UNPAIRED_SITES`).

Üç katman:

1. **DB'siz (monkeypatch)** — yeni kaydın `tenant_id` damgası. Route'un
   manager'a ne geçtiği sorusu ORM gerektirmez; sahte manager yeter.
2. **DB'siz (AST)** — elle kopyaların BİÇİM denetimi: her kopyada iki kolun da
   (eşitlik + IS NULL) bulunduğu ve hangi kopyaların `deleted_at` ile
   eşleşmediği statik olarak sayılır.
3. **sqlite (StaticPool)** — üç durumlu görünürlük ve soft-delete DAVRANIŞI.
   Burada sqlite bilinçli: kilitlenen şey Python değil, SQLAlchemy'nin ürettiği
   WHERE'in sonucu. Sahte bir session bu soruyu yanıtlayamaz — sahteyi test
   etmiş olurduk. Desen `test_g016_documents_tenant_isolation.py` ile aynı.
"""
import ast
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND = Path(__file__).resolve().parents[1]

T1 = "tenant-hanyaloglu"
T2 = "tenant-lexisbio"
USER = {"tid": T1, "preferred_username": "a@hanyaloglu.com"}


# ═══════════════════════════════════════════════════════════════════════════
# 1. DB'siz — yeni kayıtlar bilinçli olarak paylaşımlı havuza (tenant_id=NULL)
# ═══════════════════════════════════════════════════════════════════════════

def test_api_add_case_does_not_stamp_tenant(monkeypatch):
    """`POST /api/cases` tenant'ı DAMGALAMAZ (routes/cases.py:53-57).

    Hanyaloğlu Acar + LexisBio ortak çalıştığı için yeni davalar paylaşımlıdır.
    Bu bir HATA DEĞİL, korunacak karardır: `tenant_id` Depends'i yalnız token
    doğrulaması için durur. Damgalayan bir "düzeltme" iki bürodan birini kendi
    yeni dosyalarına kör bırakmaz ama karşı büroyu kör bırakır.
    """
    from routes import cases as cases_route

    seen = {}

    def _fake_add_case(data, *args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return {"id": 1}

    monkeypatch.setattr(cases_route, "add_case", _fake_add_case)
    payload = SimpleNamespace(model_dump=lambda: {"tracking_no": "HA.X.0001.2026"})
    cases_route.api_add_case(payload, tenant_id=T1)

    assert seen["args"] == (), "add_case'e konumsal tenant geçilmiş"
    assert "tenant_id" not in seen["kwargs"], "add_case'e tenant_id geçilmiş"


def test_api_add_client_does_not_stamp_tenant(monkeypatch):
    """`POST /api/clients` da damgalamaz (routes/clients.py:29-37) — aynı karar."""
    from routes import clients as clients_route

    seen = {}

    def _fake_add_client(data, *args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return True

    monkeypatch.setattr(clients_route, "add_client", _fake_add_client)
    payload = SimpleNamespace(model_dump=lambda: {"name": "TEST MÜVEKKİL"})
    clients_route.api_add_client(payload, tenant_id=T1, user=USER)

    assert seen["args"] == (), "add_client'a konumsal tenant geçilmiş"
    assert "tenant_id" not in seen["kwargs"], "add_client'a tenant_id geçilmiş"


# ═══════════════════════════════════════════════════════════════════════════
# 2. DB'siz — elle yazılmış `or_(...)` kopyalarının biçim denetimi
# ═══════════════════════════════════════════════════════════════════════════
#
# Taranan iki "tenant süzme noktası" türü:
#   (a) elle yazılmış  or_(M.tenant_id == tenant_id, M.tenant_id.is_(None))
#   (b) tenant_filter_clause(models.Case, ...) çağrısı
# `_apply_tenant_filter(...)` ÇAĞRILARI bilinçli olarak taranmaz: o helper
# soft-delete'i kendi içinde uygular, çağıranı yükümlü değildir.

SKIP_DIRS = {"tests", "__pycache__", "data", "fonts", "calibration"}

# 3 kollu kopyalar: CaseDocument'ta tenant_id kolonu YOK, bağlantısız (case_id
# NULL) belge outerjoin'de Case tarafını NULL bıraktığı için üçüncü kol şart.
# Bu iki nokta bilinçlidir; sahiplik kontrolü Python tarafında sürer
# (auth_helpers.get_tenant_owned_document + G016 ağı).
KNOWN_EXTRA_ARM_SITES = {
    ("auth_helpers.py", "get_tenant_owned_document"),
    ("routes/admin.py", "api_deleted_records"),
    ("routes/admin.py", "api_restore_record"),
}

# `models.Case` süzülen ama AYNI İFADEDE `Case.deleted_at.is_(None)` bulunmayan
# noktalar. routes/admin.py taranmaz (silinenleri sorgulamak onun İŞİ).
KNOWN_UNPAIRED_SITES = {
    # Merkezî helper: deleted_at'i bir önceki satırda, aynı fonksiyonda uygular
    # (case_manager.py:51). Fonksiyon düzeyindeki eşleşme
    # test_soft_delete.py::test_central_filters_contain_deleted_at ile kilitli.
    ("managers/case_manager.py", "_apply_tenant_filter"),
    # BİLİNÇLİ AÇIK (routes/cases.py:132-135): silinen davaların ofis numarası
    # aralığı sayılmaya devam eder ki aynı numara yeniden önerilip UNIQUE
    # kısıtına çarpmasın. test_soft_delete.py bunu kaynak düzeyinde de kilitler.
    ("routes/cases.py", "get_client_case_sequence"),
    # G034 BULGUSU (düzeltilmedi — karakterize edildi, C.2 girdisi):
    # bu iki nokta `deleted_at` yerine YALNIZ `active.is_(True)` filtresine
    # dayanıyor. Silme yolu `active=False` da yazdığı için (routes/cases.py:319)
    # bugün sızıntı YOK — ama koruma tek katmanlı: `deleted_at` "tek gerçek
    # kaynak" olarak tanımlanmışken (models.py:42) bu noktalar ona bakmıyor.
    ("routes/cases.py", "get_incomplete_tasks"),
    # G052'de TAŞINDI (sapma aynı, adres değişti): intake mahkeme sözlüğü
    # sorgusu `_load_merge_context`ten `_known_courts` TTL cache yardımcısına
    # çıktı. Sorgunun kendisi harfiyen aynı — `active.is_(True)` var,
    # `deleted_at` yok. `_load_merge_context` listeden düştü: içinde kalan
    # tek Case süzgeci (party_rows) `deleted_at`i zaten uyguluyor.
    ("routes/case_intake.py", "_known_courts"),
}


def _source_files():
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(BACKEND)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        yield path, rel.as_posix()


def _is_tenant_eq(node):
    """`M.tenant_id == tenant_id` kolu."""
    return (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.Eq)
        and isinstance(node.left, ast.Attribute)
        and node.left.attr == "tenant_id"
    )


def _is_tenant_isnull(node):
    """`M.tenant_id.is_(None)` kolu."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "is_"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "tenant_id"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value is None
    )


def _enclosing(tree, node, kinds):
    """`node`'u içeren EN İÇTEKİ `kinds` düğümü (fonksiyon ya da deyim)."""
    best = None
    for cand in ast.walk(tree):
        if not isinstance(cand, kinds):
            continue
        start = getattr(cand, "lineno", None)
        end = getattr(cand, "end_lineno", None)
        if start is None or end is None:
            continue
        if start <= node.lineno and node.end_lineno <= end:
            if best is None or start > best.lineno:
                best = cand
    return best


def _collect_sites():
    """(inline kopyalar, Case süzme noktaları) envanteri."""
    inline_copies = []   # elle yazılmış or_(...) kopyaları
    case_sites = []      # models.Case üzerinde tenant süzen her nokta
    for path, rel in _source_files():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            is_copy = (
                isinstance(node.func, ast.Name)
                and node.func.id == "or_"
                and any(_is_tenant_eq(a) or _is_tenant_isnull(a) for a in node.args)
            )
            is_helper_call = (
                isinstance(node.func, ast.Name)
                and node.func.id == "tenant_filter_clause"
                and node.args
            )
            if not (is_copy or is_helper_call):
                continue

            fn = _enclosing(tree, node, (ast.FunctionDef, ast.AsyncFunctionDef))
            stmt = _enclosing(tree, node, (ast.stmt,))
            site = SimpleNamespace(
                file=rel,
                func=fn.name if fn else "<module>",
                lineno=node.lineno,
                node=node,
                stmt=stmt,
                inline=is_copy,
            )
            if is_copy:
                inline_copies.append(site)

            model = None
            if is_copy:
                for arg in node.args:
                    if _is_tenant_eq(arg):
                        model = ast.unparse(arg.left.value)
            else:
                model = ast.unparse(node.args[0])
            if model == "models.Case":
                case_sites.append(site)
    return inline_copies, case_sites


def test_inline_tenant_copies_exist_and_are_found():
    """Envanter boş çıkarsa tarayıcı bozulmuştur — testin geri kalanı yalan söyler."""
    inline_copies, case_sites = _collect_sites()
    assert len(inline_copies) >= 5, f"elle kopya bulunamadı: {len(inline_copies)}"
    assert len(case_sites) >= 5, f"Case süzme noktası bulunamadı: {len(case_sites)}"


def test_every_inline_copy_keeps_both_arms():
    """Her elle kopyada iki kol da, AYNI model üzerinde bulunmalı.

    Eksik `is_(None)` kolu → tenant paylaşımlı havuzu (legacy NULL kayıtlar)
    kaybeder; eksik eşitlik kolu → tenant HER ŞEYİ görür. İkisi de sessizdir.
    """
    inline_copies, _ = _collect_sites()
    for site in inline_copies:
        eq_models = [
            ast.unparse(a.left.value) for a in site.node.args if _is_tenant_eq(a)
        ]
        null_models = [
            ast.unparse(a.func.value.value) for a in site.node.args if _is_tenant_isnull(a)
        ]
        where = f"{site.file}:{site.lineno} ({site.func})"
        assert len(eq_models) == 1, f"{where}: eşitlik kolu {len(eq_models)} adet"
        assert len(null_models) == 1, f"{where}: IS NULL kolu {len(null_models)} adet"
        assert eq_models[0] == null_models[0], f"{where}: kollar farklı modelde"
        rhs = [
            ast.unparse(a.comparators[0]) for a in site.node.args if _is_tenant_eq(a)
        ]
        assert rhs[0] == "tenant_id", f"{where}: eşitlik sağ tarafı {rhs[0]!r}"


def test_extra_arm_copies_are_the_known_two():
    """İki koldan FAZLA kollu kopyalar yalnız belgelenmiş CaseDocument yollarında."""
    inline_copies, _ = _collect_sites()
    extra = {
        (s.file, s.func) for s in inline_copies if len(s.node.args) > 2
    }
    assert extra == KNOWN_EXTRA_ARM_SITES, (
        f"3+ kollu kopya kümesi değişti: {extra}\n"
        "Yeni bir kol tenant kısıtını genişletir — bilinçliyse listeyi güncelle."
    )


def test_case_tenant_sites_without_soft_delete_are_the_known_set():
    """`models.Case` süzen ama aynı ifadede `deleted_at` filtresi OLMAYAN noktalar.

    Bu kümenin BÜYÜMESİ = yeni bir kopya soft-delete'i unuttu demektir.
    Küçülmesi = bir sapma düzeltildi demektir; ikisinde de bu liste bilinçli
    güncellenmeli (G034 kapsamında düzeltme YAPILMADI, karakterize edildi).
    """
    _, case_sites = _collect_sites()
    unpaired = set()
    for site in case_sites:
        if site.file == "routes/admin.py":
            continue  # silinenleri sorgulamak bu modülün işi
        stmt_src = ast.unparse(site.stmt) if site.stmt else ""
        if "Case.deleted_at.is_(None)" not in stmt_src:
            unpaired.add((site.file, site.func))
    assert unpaired == KNOWN_UNPAIRED_SITES, (
        f"tenant/soft-delete eşleşmeyen nokta kümesi değişti: {unpaired}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. sqlite — üç durumlu görünürlük + soft-delete davranışı
# ═══════════════════════════════════════════════════════════════════════════

DELETED_AT = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)

# (etiket, tenant, silinmiş mi, ofis no sıra numarası)
MATRIX = [
    ("t1-canli", T1, False, 1),
    ("t1-silinmis", T1, True, 2),
    ("t2-canli", T2, False, 3),
    ("t2-silinmis", T2, True, 99),   # T2'nin EN YÜKSEK numarası — tenant sızıntısı belirteci
    ("ortak-canli", None, False, 5),
    ("ortak-silinmis", None, True, 9),
]
NAME_BLOCK = "KUTLUKILKE"  # tam 10 karakter (tracking_no blok2)

# T1'in canlı ve görmesi gereken kayıtları
T1_VISIBLE = {"t1-canli", "ortak-canli"}


@pytest.fixture()
def db_env(monkeypatch):
    """Süreç içi sqlite + tenant/soft-delete matrisi.

    `SessionLocal` dört modülde birden yönlendirilir: manager'lar ve route'lar
    onu import zamanında modül düzeyine bağlar.
    """
    from database import Base
    import models  # noqa: F401 — Base.metadata dolsun
    from managers import case_manager, client_manager
    from routes import cases as cases_route
    from routes import clients as clients_route

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    for module in (case_manager, client_manager, cases_route, clients_route):
        monkeypatch.setattr(module, "SessionLocal", maker)

    db = maker()
    try:
        for label, tenant, deleted, seq in MATRIX:
            # BİLİNÇLİ: silinmiş satırlarda active=True bırakılıyor. Gerçek silme
            # yolu (routes/cases.py:314-321) deleted_at İLE BİRLİKTE active=False
            # da yazar; ikisini ayırmak, bir sorgunun korumasını hangi filtreden
            # aldığını görünür kılar. active=False'lu üretim hâli ayrıca test
            # edilir (test_incomplete_tasks_*).
            db.add(models.Case(
                tracking_no=f"HA.{NAME_BLOCK}.{seq:04d}.2026",
                esas_no=f"2026/{seq}",
                status="DERDEST",
                tenant_id=tenant,
                active=True,
                deleted_at=DELETED_AT if deleted else None,
            ))
            db.add(models.Client(
                name=f"MÜVEKKİL {label.upper()}",
                tenant_id=tenant,
                active=True,
                deleted_at=DELETED_AT if deleted else None,
            ))
        db.commit()
    finally:
        db.close()

    yield SimpleNamespace(
        sessions=maker,
        models=models,
        case_manager=case_manager,
        client_manager=client_manager,
        cases_route=cases_route,
        clients_route=clients_route,
    )
    engine.dispose()


def _label_of_case(tracking_no):
    for label, _tenant, _deleted, seq in MATRIX:
        if tracking_no == f"HA.{NAME_BLOCK}.{seq:04d}.2026":
            return label
    return tracking_no


def _case_id(db_env, label):
    _l, _t, _d, seq = next(row for row in MATRIX if row[0] == label)
    db = db_env.sessions()
    try:
        row = db.query(db_env.models.Case).filter(
            db_env.models.Case.tracking_no == f"HA.{NAME_BLOCK}.{seq:04d}.2026"
        ).one()
        return row.id
    finally:
        db.close()


def _client_id(db_env, label):
    db = db_env.sessions()
    try:
        row = db.query(db_env.models.Client).filter(
            db_env.models.Client.name == f"MÜVEKKİL {label.upper()}"
        ).one()
        return row.id
    finally:
        db.close()


# ─── Üç durum ayrı ayrı: kendi / paylaşımlı / başkasının ─────────────────────

def test_case_list_sees_own_tenant(db_env):
    items, total = db_env.case_manager.get_cases(tenant_id=T1)
    labels = {_label_of_case(i["tracking_no"]) for i in items}
    assert "t1-canli" in labels, "tenant kendi kaydını GÖRMÜYOR"
    assert total == len(labels)


def test_case_list_sees_shared_null_pool(db_env):
    items, _ = db_env.case_manager.get_cases(tenant_id=T1)
    labels = {_label_of_case(i["tracking_no"]) for i in items}
    assert "ortak-canli" in labels, "paylaşımlı havuz (tenant_id=NULL) GÖRÜNMÜYOR"


def test_case_list_hides_other_tenant(db_env):
    items, _ = db_env.case_manager.get_cases(tenant_id=T1)
    labels = {_label_of_case(i["tracking_no"]) for i in items}
    assert "t2-canli" not in labels, "BAŞKA TENANT'IN kaydı sızıyor"


def test_client_list_three_states(db_env):
    rows = db_env.clients_route.get_clients_api(tenant_id=T1)
    names = {r.name for r in rows}
    assert "MÜVEKKİL T1-CANLI" in names, "tenant kendi cari kaydını görmüyor"
    assert "MÜVEKKİL ORTAK-CANLI" in names, "paylaşımlı cari görünmüyor"
    assert "MÜVEKKİL T2-CANLI" not in names, "başka tenant'ın carisi sızıyor"


# ─── Tenant + soft-delete BİRLİKTE (C.2 risk modeli) ─────────────────────────

def test_case_list_applies_tenant_and_soft_delete_together(db_env):
    """Tam küme eşitliği: tek tek doğru olup birleşimde kaçıran kopyayı yakalar.

    Yalnız tenant filtresi olsaydı silinmişler; yalnız soft-delete olsaydı
    T2'nin kaydı listeye girerdi. Küme eşitliği ikisini de reddeder.
    """
    items, total = db_env.case_manager.get_cases(tenant_id=T1)
    labels = {_label_of_case(i["tracking_no"]) for i in items}
    assert labels == T1_VISIBLE
    assert total == len(T1_VISIBLE), "X-Total-Count aynı filtreden geçmiyor"


def test_client_list_applies_tenant_and_soft_delete_together(db_env):
    rows = db_env.clients_route.get_clients_api(tenant_id=T1)
    names = {r.name for r in rows}
    assert names == {f"MÜVEKKİL {label.upper()}" for label in T1_VISIBLE}


def test_case_stats_applies_tenant_and_soft_delete_together(db_env):
    """Özet sayaç ile listenin AYNI kümeden beslendiği kilitlenir."""
    stats = db_env.case_manager.get_case_stats(tenant_id=T1)
    assert stats["total"] == len(T1_VISIBLE)
    assert stats["statuses"] == {"DERDEST": len(T1_VISIBLE)}


# ─── Tekil erişim (id ile) — bugünkü davranış ────────────────────────────────

@pytest.mark.parametrize("label,visible", [
    ("t1-canli", True),
    ("ortak-canli", True),
    ("t1-silinmis", False),      # kendi kaydı ama silinmiş
    ("ortak-silinmis", False),
    ("t2-canli", False),         # canlı ama başka tenant
    ("t2-silinmis", False),      # ikisi de kapalı
])
def test_get_case_single_access(db_env, label, visible):
    """`get_case` (dava kartı) — altı hücrenin hepsi ayrı ayrı.

    Bulunamayan kayıt None döner; route bunu 404'e çevirir. Yani "başka
    tenant'ın kaydı" ile "olmayan kayıt" çağıran taraftan ayırt EDİLEMEZ —
    id enumeration'a karşı bilinçli (ve korunacak) davranış.
    """
    got = db_env.case_manager.get_case(_case_id(db_env, label), tenant_id=T1)
    assert (got is not None) is visible, f"{label}: beklenen görünürlük {visible}"


@pytest.mark.parametrize("label,visible", [
    ("t1-canli", True),
    ("ortak-canli", True),
    ("t1-silinmis", False),
    ("ortak-silinmis", False),
    ("t2-canli", False),
    ("t2-silinmis", False),
])
def test_auth_helper_single_access(db_env, label, visible):
    """`auth_helpers.get_tenant_owned_case/_client` — merkezî tekil erişim kapısı."""
    import auth_helpers

    db = db_env.sessions()
    try:
        case = auth_helpers.get_tenant_owned_case(db, _case_id(db_env, label), T1)
        client = auth_helpers.get_tenant_owned_client(db, _client_id(db_env, label), T1)
    finally:
        db.close()
    assert (case is not None) is visible, f"case/{label}"
    assert (client is not None) is visible, f"client/{label}"


def test_tenant_none_disables_case_manager_tenant_filter(db_env):
    """`tenant_id=None` (dahilî çağrılar) tenant filtresini KAPATIR, soft-delete'i DEĞİL.

    `_apply_tenant_filter` yalnız `if tenant_id:` ise tenant kolunu ekler.
    Bu, arkaplan işleri için bilinçli bir kapıdır; kullanıcı yollarında
    tenant_id daima `Depends(get_current_tenant)`'tan gelir.
    """
    items, _ = db_env.case_manager.get_cases(tenant_id=None)
    labels = {_label_of_case(i["tracking_no"]) for i in items}
    assert labels == {"t1-canli", "t2-canli", "ortak-canli"}


# ─── Bilinçli sapma: ofis no sırası silinenleri SAYAR ────────────────────────

def test_client_sequence_counts_deleted_but_still_isolates_tenant(db_env):
    """Tek çağrıda iki kural: soft-delete bilinçli KAPALI, tenant filtresi AÇIK.

    T1+ortak havuzun en yükseği silinmiş `ortak-silinmis` (0009) → 10 beklenir.
    Soft-delete filtresi eklenmiş olsaydı 6 (0005+1), tenant filtresi düşmüş
    olsaydı 100 (T2'nin 0099'u) dönerdi.
    """
    got = db_env.cases_route.get_client_case_sequence(
        client_name="", name_block=NAME_BLOCK, tenant_id=T1
    )
    assert got == {"sequence": 10}


# ─── G034 bulgusu: `deleted_at` yerine `active`'e dayanan yol ────────────────

def test_incomplete_tasks_isolates_tenant(db_env):
    """`/api/incomplete-tasks` tenant filtresini uygular (dava + cari)."""
    got = db_env.cases_route.get_incomplete_tasks(tenant_id=T1)
    esas = {c["esas_no"] for c in got["incomplete_cases"]}
    names = {c["name"] for c in got["incomplete_clients"]}
    assert "2026/1" in esas, "kendi eksik davası listelenmiyor"
    assert "2026/3" not in esas, "başka tenant'ın davası sızıyor"
    assert "MÜVEKKİL T2-CANLI" not in names, "başka tenant'ın carisi sızıyor"


def test_incomplete_tasks_case_side_relies_on_active_not_deleted_at(db_env):
    """BULGU (karakterizasyon, düzeltilmedi): dava tarafında `deleted_at` filtresi YOK.

    `deleted_at` dolu ama `active=True` bırakılmış bir dava bu listede görünür;
    aynı durumdaki CARİ görünmez (cari sorgusu `deleted_at`'i elle filtreler,
    routes/cases.py:772). Bugün üretimde sızıntı yoktur çünkü silme yolu
    `active=False` da yazar — bir sonraki test bunu gösterir. Yine de koruma
    tek katmanlıdır ve `deleted_at`'in "tek gerçek kaynak" tanımıyla (models.py:42)
    çelişir → FAZ C / C.2 girdisi.
    """
    got = db_env.cases_route.get_incomplete_tasks(tenant_id=T1)
    esas = {c["esas_no"] for c in got["incomplete_cases"]}
    names = {c["name"] for c in got["incomplete_clients"]}
    assert "2026/2" in esas, "bugünkü davranış değişti — bulgu düzeltilmişse testi güncelle"
    assert "MÜVEKKİL T1-SILINMIS" not in names, "cari tarafı deleted_at'i filtreliyordu"


def test_incomplete_tasks_hides_production_deleted_case(db_env):
    """Üretim silme yolu `active=False` de yazar → liste temizlenir (maskeleme kanıtı)."""
    models = db_env.models
    db = db_env.sessions()
    try:
        row = db.query(models.Case).filter(
            models.Case.tracking_no == f"HA.{NAME_BLOCK}.0002.2026"
        ).one()
        row.active = False  # routes/cases.py:321 ile aynı
        db.commit()
    finally:
        db.close()

    got = db_env.cases_route.get_incomplete_tasks(tenant_id=T1)
    assert "2026/2" not in {c["esas_no"] for c in got["incomplete_cases"]}


# ─── Manager'ların damgalama davranışı (sqlite, gerçek INSERT) ───────────────

def test_add_case_never_stamps_tenant_even_when_given(db_env):
    """`case_manager.add_case` `tenant_id` parametresini ALIR ama KULLANMAZ.

    `models.Case(...)` ctor'unda tenant_id hiç geçilmez → kolon NULL kalır.
    Yani dava tarafında paylaşımlı havuz iki katmanlı korunuyor (route da
    geçmiyor, manager da yazmıyor). Bu bir tuzak da olabilir: parametre
    imzada durduğu için "damgalanıyor" sanılabilir.
    """
    models = db_env.models
    db_env.case_manager.add_case(
        {"tracking_no": "HA.YENIKAYIT_.0001.2026", "status": "DERDEST"}, tenant_id=T1
    )
    db = db_env.sessions()
    try:
        row = db.query(models.Case).filter(
            models.Case.tracking_no == "HA.YENIKAYIT_.0001.2026"
        ).one()
        assert row.tenant_id is None
    finally:
        db.close()


def test_add_client_would_stamp_tenant_if_given(db_env):
    """`client_manager.add_client` cari tarafında tenant'ı YAZAR — route geçmediği için NULL kalır.

    Dava tarafıyla asimetri bilinçli değil, sadece bugünkü hâl: koruma tek
    katmanda (`routes/clients.py:37`) duruyor. Route bir gün `tenant_id=`
    geçirirse yeni cariler damgalanır ve paylaşımlı havuz kararı sessizce
    delinir — bu test o değişikliği görünür kılar.
    """
    models = db_env.models
    db_env.client_manager.add_client({"name": "DAMGALI MÜVEKKİL"}, tenant_id=T1)
    db_env.client_manager.add_client({"name": "DAMGASIZ MÜVEKKİL"})
    db = db_env.sessions()
    try:
        stamped = db.query(models.Client).filter(
            models.Client.name == "DAMGALI MÜVEKKİL"
        ).one()
        plain = db.query(models.Client).filter(
            models.Client.name == "DAMGASIZ MÜVEKKİL"
        ).one()
        assert stamped.tenant_id == T1
        assert plain.tenant_id is None
    finally:
        db.close()


def test_add_client_upsert_skips_soft_deleted_namesake(db_env):
    """Silinmiş aynı adlı cari UPSERT hedefi OLMAZ — yeni satır açılır.

    Silinen kayıt sessizce dirilmesin (geri alma yalnız admin panelinden).
    """
    models = db_env.models
    db_env.client_manager.add_client({"name": "MÜVEKKİL T1-SILINMIS", "phone": "555"})
    db = db_env.sessions()
    try:
        rows = db.query(models.Client).filter(
            models.Client.name == "MÜVEKKİL T1-SILINMIS"
        ).all()
        assert len(rows) == 2, "silinmiş kayıt üzerine yazılmış (diriltme)"
        assert {r.deleted_at is None for r in rows} == {True, False}
    finally:
        db.close()
