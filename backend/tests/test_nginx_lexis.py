"""Lexis proxy bekçisi (04.10.2026).

Tarayıcının Lexis rapor servisine (`../lexis-rapor`, ayrı stack) tek yolu konteyner
nginx'indeki `/lexis-api/` önekidir — Hukukbot proxy'sinin aynı deseni
(`test_nginx_hukukbot.py`). Bekçi şunları sessizce bozulmaktan korur:

1. ALLOWLIST: yalnız kullanıcı uçları proxy'lenir (`word`, `davalar`, `dosya`,
   `emsal-oner`, `iskelet`, `muallak-oner`, `karar-bankasi`, `kutuphane`, `rapor`,
   `emsal-puanla`); servisin `/health`'i ve geri kalan her `/lexis-api` yolu 404'tür.
2. GECİKMELİ DNS: upstream değişkenle + `resolver` ile verilir. Düz adla yazılırsa
   Lexis stack'i kapalıyken HUKDOK'un nginx'i açılışta upstream'i çözemez ve HİÇ kalkmaz.
3. Vite dev proxy'si aynı allowlist'i taşır.

Konteynerde repo kökü görünmediği için atlanır; CI'da (repo checkout'u) koşar.
"""
import re
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
NGINX = REPO_ROOT / "nginx.conf"
VITE_CONFIG = REPO_ROOT / "frontend" / "vite.config.ts"

pytestmark = pytest.mark.skipif(
    not NGINX.exists(),
    reason="repo kökü görünmüyor (konteynerde yalnız backend/ mount'lu)",
)


def _yorumsuz(metin: str) -> str:
    return "\n".join(s.split("#", 1)[0] for s in metin.splitlines())


def _lexis_bloklari() -> list[tuple[str, str]]:
    """`location <eşleşme> { ... }` → (eşleşme, gövde); iç içe blok yok varsayımı."""
    metin = _yorumsuz(NGINX.read_text(encoding="utf-8"))
    bloklar = [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"location\s+([^{]+?)\s*\{(.*?)\n\s*\}", metin, re.S)]
    return [(k, v) for k, v in bloklar if "lexis-api" in k]


def _proxy_govdesi() -> str:
    return next(v for k, v in _lexis_bloklari() if "proxy_pass" in v)


# Tam metin: alternatif eklemek, (/|$) çapasını silmek ya da ~ → ~* yapmak allowlist'i genişletir.
ALLOWLIST = "(word|davalar|dosya|emsal-oner|iskelet|muallak-oner|karar-bankasi|kutuphane|rapor|emsal-puanla)"
ALLOWLIST_ESLESMESI = f"~ ^/lexis-api/{ALLOWLIST}(/|$)"


def test_lexis_allowlist_yalniz_kullanici_uclari():
    proxy = [k for k, v in _lexis_bloklari() if "proxy_pass" in v]
    assert proxy == [ALLOWLIST_ESLESMESI], (
        f"allowlist location'ı değişti: {proxy!r}. Yeni uç açmak bilinçli karar olmalı; "
        "servisin /health'i tarayıcıya AÇILMAZ."
    )


def test_lexis_onek_atilir():
    assert re.search(r"rewrite\s+\^/lexis-api/\(\.\*\)\$\s+/\$1\s+break;", _proxy_govdesi()), (
        "önek rewrite...break ile atılmalı (değişkenli proxy_pass URI eklemez; "
        "yoksa servis /lexis-api/... alır ve her istek 404 olur)"
    )


def test_lexis_geri_kalani_404():
    kapanis = [v for k, v in _lexis_bloklari() if "proxy_pass" not in v]
    assert any(re.search(r"return\s+404", v) for v in kapanis), (
        "allowlist dışı /lexis-api yolları açıkça 404 dönmeli (SPA'ya düşmemeli)"
    )
    # nginx regex location'ları dosya sırasıyla dener: allowlist 404 bloğundan ÖNCE olmalı.
    metin = _yorumsuz(NGINX.read_text(encoding="utf-8"))
    assert metin.index(f"^/lexis-api/{ALLOWLIST}") < metin.index("location ~ ^/lexis-api(/|$)")


def test_lexis_upstream_gecikmeli_cozulur():
    govde = _proxy_govdesi()
    assert re.search(r"resolver\s+127\.0\.0\.11", govde), "Docker iç DNS resolver'ı şart"
    pp = re.search(r"proxy_pass\s+([^;]+);", govde).group(1).strip()
    assert pp.startswith("$"), f"proxy_pass değişkenle verilmeli (açılışta çözülmesin): {pp}"
    assert re.search(r"set\s+\$\w+\s+http://lexis_api:8020", govde)


def test_lexis_proxy_guvenlik_basliklarini_dusurmez():
    assert "add_header" not in _proxy_govdesi(), (
        "add_header server düzeyi güvenlik başlıklarını düşürür (nginx.conf kalıtım tuzağı)"
    )


@pytest.mark.skipif(not VITE_CONFIG.exists(), reason="frontend/vite.config.ts görünmüyor")
def test_vite_dev_proxy_ayni_allowlist():
    """`npm run dev` (5173) nginx'i atlar: aynı allowlist Vite proxy'sinde de olmalı."""
    metin = VITE_CONFIG.read_text(encoding="utf-8")
    assert f"'^/lexis-api/{ALLOWLIST}(/|$)'" in metin, "Vite allowlist anahtarı nginx ile aynı olmalı"
    lexis_404 = re.search(r"'\^/lexis-api\(/\|\$\)':\s*\{(.*?)\}", metin, re.S)
    assert lexis_404 and re.search(r"bypass:\s*\(\)\s*=>\s*false", lexis_404.group(1)), (
        "allowlist dışı /lexis-api Vite'ta da 404 olmalı"
    )
