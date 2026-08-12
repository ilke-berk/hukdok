"""G032 — `GET /api/cases` sayfalama sözleşmesi: `X-Total-Count` karakterizasyonu.

Neden var: liste yolunda `get_cases`'in döndürdüğü `total` ATILMIYOR —
`routes/cases.py` onu `X-Total-Count` başlığına yazıyor ve frontend
(`CaseList.tsx`) sayfa sayısını bu başlıktan hesaplıyor. Toplam sayıyı
"maliyetli COUNT" diye kapatan bir optimizasyon (örn. genel `with_total=False`)
sayfalamayı SESSİZCE bozar: liste dolu görünür, sayfa çubuğu tek sayfaya iner.
Bu dosya o ağı kurar; optimizasyon bu ağın üstünde yapılır.

DB/ağ yok: `routes.cases.get_cases` bellekte bir sahte veri kümesiyle
monkeypatch'lidir (desen: `tests/test_g014_error_gates.py` + `test_case_intake_commit.py`).
Sahte manager filtre/limit/offset semantiğini gerçeğiyle aynı sırada uygular
(önce filtre → sonra toplam → sonra dilim), böylece kilitlenen şey route'un
sözleşmesidir: **başlık, sayfa uzunluğu değil, filtrelenmiş toplam.**

Bu görev kaynak kodu DEĞİŞTİRMEZ; yalnız mevcut davranışı kayda geçirir.
"""
import ast
from pathlib import Path

import pytest


API_PY = Path(__file__).resolve().parents[1] / "api.py"


def _row(idx: int, *, status: str = "DERDEST", court: str = "ANKARA 1. ASLIYE HUKUK",
         missing: bool = False) -> dict:
    """CaseListRead'i doyuran asgari satır (route response_model ile doğrular)."""
    return {
        "id": idx,
        "tracking_no": f"HA.KUTLUKILKE.{idx:04d}.2026",
        "esas_no": f"2026/{idx}",
        "status": status,
        "court": court,
        "created_at": "2026-08-01T10:00:00",
        "updated_at": "2026-08-01T10:00:00",
        "missing_required_fields": [{"field": "court"}] if missing else [],
        "parties": [],
        "lawyers": [],
    }


# 25 satır: 5'i KARAR, 4'ü eksik alanlı, 3'ü "IZMIR" mahkemesi.
DATASET = (
    [_row(i) for i in range(1, 14)]
    + [_row(i, status="KARAR") for i in range(15, 20)]
    + [_row(i, missing=True) for i in range(20, 24)]
    + [_row(i, court="IZMIR 2. ASLIYE HUKUK") for i in range(24, 27)]
)
TOTAL = len(DATASET)  # 25


def _fake_query(rows, *, status=None, q=None, missing_required=False):
    """Gerçek manager'ın filtre sırasını taklit eder (basitleştirilmiş)."""
    out = rows
    if status and status != "ALL":
        out = [r for r in out if r["status"] == status]
    if missing_required:
        out = [r for r in out if r["missing_required_fields"]]
    if q and len(q) >= 2:
        needle = q.lower()
        out = [
            r for r in out
            if needle in r["tracking_no"].lower()
            or needle in r["court"].lower()
            or needle in (r["esas_no"] or "").lower()
        ]
    return out


@pytest.fixture()
def cases_app(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user
    from routes import cases as cases_routes

    calls = []

    def fake_get_cases(**kwargs):
        calls.append(kwargs)
        matched = _fake_query(
            DATASET,
            status=kwargs.get("status"),
            q=kwargs.get("q"),
            missing_required=kwargs.get("missing_required", False),
        )
        # Toplam OFFSET/LIMIT'ten ÖNCE hesaplanır (case_manager.get_cases:352 ile aynı sıra)
        total = len(matched)
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 50)
        return matched[offset:offset + limit], total

    monkeypatch.setattr(cases_routes, "get_cases", fake_get_cases)

    app = FastAPI()
    app.include_router(cases_routes.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "name": "Test", "preferred_username": "test@example.com", "tid": "tenant-1",
    }
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"
    client = TestClient(app, raise_server_exceptions=False)
    client.manager_calls = calls  # type: ignore[attr-defined]
    return client


# ── 1. Başlık sayfa uzunluğundan bağımsız ────────────────────────────────────

def test_total_count_is_full_total_not_page_length(cases_app):
    """limit=5 ile 5 kayıt döner ama başlık 25 der."""
    r = cases_app.get("/api/cases", params={"limit": 5})

    assert r.status_code == 200
    assert len(r.json()) == 5, "limit gövdeye uygulanmamış"
    assert r.headers["X-Total-Count"] == str(TOTAL), (
        "X-Total-Count sayfa uzunluğunu yansıtıyor — sayfalama tek sayfaya iner"
    )


def test_total_count_present_on_default_request(cases_app):
    """Başlık her yanıtta var ve tam sayı metni; frontend parseInt ile okuyor."""
    r = cases_app.get("/api/cases")

    assert "X-Total-Count" in r.headers, "başlık kaybolmuş → sayfa çubuğu ölür"
    assert r.headers["X-Total-Count"].isdigit()
    assert int(r.headers["X-Total-Count"]) == TOTAL


def test_list_path_does_not_request_total_suppression(cases_app):
    """FAZ E ağı: liste yoluna genel bir `with_total=False` sızarsa başlık bozulur.

    `search_cases` toplamı ATIYOR (`case_manager.py` — `items, _total = get_cases(...)`),
    bu yüzden orada COUNT'u kapatmak güvenli; ama AYNI anahtarın liste yoluna
    uygulanması sayfalamayı sessizce bozar. Bu test o farkı kilitler.
    """
    cases_app.get("/api/cases", params={"limit": 5})

    kwargs = cases_app.manager_calls[-1]  # type: ignore[attr-defined]
    assert kwargs.get("with_total", True), (
        "liste yolu get_cases'ten toplamı istemiyor — X-Total-Count anlamsızlaşır"
    )


def test_header_mirrors_manager_total_and_breaks_if_suppressed(monkeypatch):
    """Ağın kendi kanıtı: başlık manager'ın 2. dönüş değerinden geliyor.

    Toplamı bastıran bir manager (dönüş `(page, len(page))` — `with_total=False`
    sonrası tipik davranış) takılırsa başlık 25 yerine 5 der; yani yukarıdaki
    testler bu bozulmada gerçekten kırmızıya döner. Route toplamı kendi başına
    yeniden hesaplamıyor — koruma tamamen manager sözleşmesine bağlı.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dependencies import get_current_tenant, get_current_user
    from routes import cases as cases_routes

    def suppressed_get_cases(**kwargs):
        offset = kwargs.get("offset", 0)
        page = DATASET[offset:offset + kwargs.get("limit", 50)]
        return page, len(page)

    monkeypatch.setattr(cases_routes, "get_cases", suppressed_get_cases)

    app = FastAPI()
    app.include_router(cases_routes.router)
    app.dependency_overrides[get_current_user] = lambda: {"preferred_username": "t@e.com"}
    app.dependency_overrides[get_current_tenant] = lambda: "tenant-1"

    r = TestClient(app).get("/api/cases", params={"limit": 5})

    assert r.headers["X-Total-Count"] == "5" != str(TOTAL), (
        "route toplamı manager'dan almıyor — bu dosyadaki koruma ağı boşa çıkar"
    )


# ── 2. Filtreli toplam ───────────────────────────────────────────────────────

def test_total_count_reflects_status_filter(cases_app):
    r = cases_app.get("/api/cases", params={"status": "KARAR", "limit": 2})

    assert len(r.json()) == 2
    assert r.headers["X-Total-Count"] == "5", (
        "status filtresi başlığa yansımıyor — filtresiz toplam sızıyor"
    )


def test_total_count_reflects_missing_required_filter(cases_app):
    r = cases_app.get("/api/cases", params={"missing_required": "true", "limit": 1})

    assert len(r.json()) == 1
    assert r.headers["X-Total-Count"] == "4"


def test_total_count_reflects_search_term(cases_app):
    r = cases_app.get("/api/cases", params={"q": "IZMIR", "limit": 50})

    assert len(r.json()) == 3
    assert r.headers["X-Total-Count"] == "3", "arama teriminde de filtrelenmiş toplam beklenir"


def test_total_count_zero_when_filter_matches_nothing(cases_app):
    r = cases_app.get("/api/cases", params={"status": "TEMYIZ"})

    assert r.json() == []
    assert r.headers["X-Total-Count"] == "0", "eşleşme yokken başlık 0 olmalı"


# ── 3. Offset toplamı değiştirmez ────────────────────────────────────────────

def test_offset_does_not_change_total(cases_app):
    first = cases_app.get("/api/cases", params={"limit": 10, "offset": 0})
    third = cases_app.get("/api/cases", params={"limit": 10, "offset": 10})

    assert first.headers["X-Total-Count"] == third.headers["X-Total-Count"] == str(TOTAL)
    assert [c["id"] for c in first.json()] != [c["id"] for c in third.json()], (
        "offset gövdeye uygulanmamış — sayfalar aynı kayıtları veriyor"
    )


def test_offset_with_filter_keeps_filtered_total(cases_app):
    r = cases_app.get("/api/cases", params={"status": "KARAR", "limit": 2, "offset": 2})

    assert len(r.json()) == 2
    assert r.headers["X-Total-Count"] == "5"


# ── 4. Son sayfa ─────────────────────────────────────────────────────────────

def test_offset_past_end_returns_empty_list_with_real_total(cases_app):
    """Frontend son sayfayı toplam/limit ile hesaplar; taşan offset boş liste + doğru toplam."""
    r = cases_app.get("/api/cases", params={"limit": 10, "offset": TOTAL + 5})

    assert r.status_code == 200
    assert r.json() == []
    assert r.headers["X-Total-Count"] == str(TOTAL), (
        "son sayfanın ötesinde toplam sıfırlanıyor — sayfa çubuğu kayboluyor"
    )


def test_last_partial_page(cases_app):
    """25 kayıt, limit=10 → 3. sayfa 5 kayıt, başlık yine 25."""
    r = cases_app.get("/api/cases", params={"limit": 10, "offset": 20})

    assert len(r.json()) == 5
    assert r.headers["X-Total-Count"] == str(TOTAL)


# ── 5. Sınır doğrulaması route'ta kalıyor ────────────────────────────────────

def test_limit_upper_bound_is_enforced(cases_app):
    """limit sınırı (le=200) kalkarsa DB tarafında sayfalama koruması kaybolur."""
    r = cases_app.get("/api/cases", params={"limit": 201})

    assert r.status_code == 422


def test_negative_offset_rejected(cases_app):
    r = cases_app.get("/api/cases", params={"offset": -1})

    assert r.status_code == 422


# ── 6. CORS: başlık tarayıcıya açık mı ───────────────────────────────────────

def _cors_expose_headers() -> list[list[str]]:
    """api.py'deki her `add_middleware(CORSMiddleware, ...)` çağrısının expose_headers'ı.

    Kaynak AST'ten okunur (api import'u ağır: scheduler/lifespan zinciri).
    """
    tree = ast.parse(API_PY.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_middleware"):
            continue
        if not (node.args and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "CORSMiddleware"):
            continue
        exposed = []
        for kw in node.keywords:
            if kw.arg == "expose_headers" and isinstance(kw.value, ast.List):
                exposed = [
                    el.value for el in kw.value.elts
                    if isinstance(el, ast.Constant) and isinstance(el.value, str)
                ]
        found.append(exposed)
    return found


def test_both_cors_branches_expose_total_count():
    """DEV_MODE ve prod dallarının İKİSİ de X-Total-Count'u açığa çıkarmalı.

    Açığa çıkarılmazsa tarayıcı başlığı JS'e vermez (yanıt gövdesi normal gelir):
    sayfalama yine sessizce bozulur, ağ sekmesinde başlık görünür olduğu için
    teşhis de zorlaşır.
    """
    branches = _cors_expose_headers()

    assert len(branches) == 2, (
        f"api.py'de 2 CORS dalı (DEV_MODE + prod) bekleniyordu, {len(branches)} bulundu"
    )
    for exposed in branches:
        assert "X-Total-Count" in exposed, (
            "bir CORS dalında expose_headers X-Total-Count içermiyor"
        )
