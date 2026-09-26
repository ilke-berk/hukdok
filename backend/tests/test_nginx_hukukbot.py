"""Hukukbot proxy bekçisi (karar 021, G203).

Tarayıcının Hukukbot API'sine tek yolu konteyner nginx'indeki `/hukukbot-api/`
önekidir. Bekçi üç şeyi sessizce bozulmaktan korur:

1. ALLOWLIST: yalnız kullanıcı uçları (ask, sessions, download) proxy'lenir;
   Hukukbot'un API-key'li `/ingest` webhook'u ve `/health` asla açılmaz, geri
   kalan her `/hukukbot-api` yolu 404'tür.
2. GECİKMELİ DNS: upstream değişkenle + `resolver` ile verilir. Düz adla yazılırsa
   Hukukbot kapalıyken HukuDok'un nginx'i açılışta upstream'i çözemez ve HİÇ kalkmaz.
3. `/export` konteyner nginx'ine eklenmez (nginx.conf kuralı) ve frontend
   `hukuk_shared` ağındadır (yoksa proxy hiçbir yere ulaşmaz).

Konteynerde repo kökü görünmediği için atlanır; CI'da (repo checkout'u) koşar.
"""
import re
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
NGINX = REPO_ROOT / "nginx.conf"
COMPOSE = REPO_ROOT / "docker-compose.yml"

pytestmark = pytest.mark.skipif(
    not (NGINX.exists() and COMPOSE.exists()),
    reason="repo kökü görünmüyor (konteynerde yalnız backend/ mount'lu)",
)


def _yorumsuz(metin: str) -> str:
    return "\n".join(s.split("#", 1)[0] for s in metin.splitlines())


def _location_bloklari(metin: str) -> dict[str, str]:
    """`location <eşleşme> { ... }` → {eşleşme: gövde}; iç içe blok yok varsayımı."""
    bloklar: dict[str, str] = {}
    for m in re.finditer(r"location\s+([^{]+?)\s*\{(.*?)\n\s*\}", metin, re.S):
        bloklar[m.group(1).strip()] = m.group(2)
    return bloklar


def _hukukbot_bloklari() -> list[tuple[str, str]]:
    bloklar = _location_bloklari(_yorumsuz(NGINX.read_text(encoding="utf-8")))
    return [(k, v) for k, v in bloklar.items() if "hukukbot-api" in k]


# Tam metin: alternatif eklemek, (/|$) çapasını silmek ya da ~ → ~* (büyük/küçük harf
# duyarsız) yapmak allowlist'i genişletir; parça kontrolü bunları kaçırıyordu (G203 denetimi).
ALLOWLIST_ESLESMESI = "~ ^/hukukbot-api/(ask|sessions|download)(/|$)"


def test_hukukbot_allowlist_yalniz_kullanici_uclari():
    bloklar = _hukukbot_bloklari()
    proxy = [(k, v) for k, v in bloklar if "proxy_pass" in v]
    assert len(proxy) == 1, f"tek bir proxy'leyen /hukukbot-api location'ı olmalı: {[k for k, _ in proxy]}"
    eslesme = proxy[0][0]
    assert eslesme == ALLOWLIST_ESLESMESI, (
        f"allowlist location'ı değişti: {eslesme!r}. Yeni uç açmak bilinçli karar olmalı; "
        "Hukukbot'un /ingest'i ve /health'i tarayıcıya ASLA açılmaz."
    )


def test_hukukbot_onek_atilir():
    _, govde = next((k, v) for k, v in _hukukbot_bloklari() if "proxy_pass" in v)
    assert re.search(r"rewrite\s+\^/hukukbot-api/\(\.\*\)\$\s+/\$1\s+break;", govde), (
        "önek rewrite...break ile atılmalı (değişkenli proxy_pass URI eklemez; "
        "yoksa Hukukbot /hukukbot-api/... alır ve her istek 404 olur)"
    )


def test_hukukbot_geri_kalani_404():
    bloklar = _hukukbot_bloklari()
    kapanis = [v for k, v in bloklar if "proxy_pass" not in v]
    assert any(re.search(r"return\s+404", v) for v in kapanis), (
        "allowlist dışı /hukukbot-api yolları açıkça 404 dönmeli (SPA'ya düşmemeli)"
    )
    # nginx regex location'ları dosya sırasıyla dener: allowlist 404 bloğundan ÖNCE olmalı.
    metin = _yorumsuz(NGINX.read_text(encoding="utf-8"))
    assert metin.index("(ask|sessions|download)") < metin.index("location ~ ^/hukukbot-api(/|$)")


def test_hukukbot_upstream_gecikmeli_cozulur():
    _, govde = next((k, v) for k, v in _hukukbot_bloklari() if "proxy_pass" in v)
    assert re.search(r"resolver\s+127\.0\.0\.11", govde), "Docker iç DNS resolver'ı şart"
    pp = re.search(r"proxy_pass\s+([^;]+);", govde).group(1).strip()
    assert pp.startswith("$"), f"proxy_pass değişkenle verilmeli (açılışta çözülmesin): {pp}"
    assert re.search(r"set\s+\$\w+\s+http://hukukbot_api:8010", govde)


def test_hukukbot_proxy_ayarlari():
    _, govde = next((k, v) for k, v in _hukukbot_bloklari() if "proxy_pass" in v)
    assert re.search(r'proxy_set_header\s+X-User-OID\s+""', govde), "X-User-OID silinmeli"
    assert re.search(r"proxy_buffering\s+off", govde), "/ask NDJSON akışı tamponlanmamalı"
    assert "add_header" not in govde, (
        "add_header server düzeyi güvenlik başlıklarını düşürür (nginx.conf kalıtım tuzağı)"
    )


def test_export_konteyner_nginxinde_yok():
    bloklar = _location_bloklari(_yorumsuz(NGINX.read_text(encoding="utf-8")))
    assert not any("export" in k for k in bloklar), "/export konteyner nginx'ine ASLA eklenmez"


def test_frontend_hukuk_shared_aginda():
    metin = COMPOSE.read_text(encoding="utf-8")
    frontend = re.search(r"\n  frontend:\n(.*?)(?=\n\S|\n  \w[\w-]*:\n)", metin, re.S)
    assert frontend, "compose'da frontend servisi bulunamadı"
    aglar = re.search(r"\n    networks:\n((?:\s+-\s+\S+\n?|\s+#.*\n)+)", frontend.group(1))
    assert aglar and "hukuk_shared" in aglar.group(1), "frontend hukuk_shared ağında olmalı"
