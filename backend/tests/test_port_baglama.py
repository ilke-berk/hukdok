"""docker-compose.yml port bağlama bekçisi.

Dışarıya açık TEK kapı host nginx'tir (prod 443, TLS). Compose'un yayınladığı her
port (postgres 5432, backend 8001, frontend 8080) yalnız 127.0.0.1'e bağlanır:
backend'in API-key'li /export route'ları ve DB public porttan erişilemez, frontend'e
host nginx loopback'ten proxy'ler. Yeni bir dış kapı açmak bilinçli bir mimari karar
olmalı — bu test onu sessizce olmaktan çıkarır.

Konteynerde repo kökü görünmediği için atlanır; CI'da (repo checkout'u) koşar.
"""
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
COMPOSE = REPO_ROOT / "docker-compose.yml"


def _port_girdileri(metin: str) -> list[str]:
    """`ports:` bloklarındaki liste girdilerini (yorumlar hariç) döndürür."""
    girdiler: list[str] = []
    blok_girintisi: int | None = None
    for satir in metin.splitlines():
        yalin = satir.strip()
        if not yalin or yalin.startswith("#"):
            continue
        girinti = len(satir) - len(satir.lstrip())
        if yalin == "ports:":
            blok_girintisi = girinti
            continue
        if blok_girintisi is not None:
            if girinti > blok_girintisi and yalin.startswith("- "):
                girdiler.append(yalin[2:].strip().strip("\"'"))
                continue
            blok_girintisi = None
    return girdiler


@pytest.mark.skipif(
    not COMPOSE.exists(),
    reason="repo kökü görünmüyor (konteynerde yalnız backend/ mount'lu)",
)
def test_compose_portlari_yalniz_loopbacke_baglanir():
    girdiler = _port_girdileri(COMPOSE.read_text(encoding="utf-8"))
    assert girdiler, "docker-compose.yml'de ports girdisi bulunamadı — ayrıştırıcı bozuk olabilir"
    acik = [g for g in girdiler if not g.startswith("127.0.0.1:")]
    assert not acik, (
        f"127.0.0.1'e bağlanmamış port(lar): {acik}. Yeni dış kapı açma; public "
        "trafik host nginx'ten (443) girer, konteyner portları loopback'e bağlanır."
    )


def test_ayristirici_acik_portu_yakalar():
    ornek = (
        "services:\n"
        "  db:\n"
        "    ports:\n"
        "      # yorum\n"
        '      - "127.0.0.1:5432:5432"\n'
        "  web:\n"
        "    ports:\n"
        '      - "8080:80"\n'
        "    restart: always\n"
    )
    assert _port_girdileri(ornek) == ["127.0.0.1:5432:5432", "8080:80"]
