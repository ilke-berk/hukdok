"""Permissions-Policy bekçisi (28.09).

Sesli giriş (G217, `MicButton`) tarayıcıda `getUserMedia` ister. Konteyner nginx'i
`microphone=()` gönderirse tarayıcı kullanıcıya HİÇ SORMADAN reddeder ve ekranda
"Mikrofon izni verilmedi" çıkar. Bekçi: başlık (add_header kalıtımı yüzünden üç
yerde tekrar yazılır) üç yerde de AYNI, mikrofon yalnız kendi origin'imize açık
(`microphone=(self)`), kamera ve konum kapalı.

Konteynerde repo kökü görünmediği için atlanır; CI'da (repo checkout'u) koşar.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NGINX = REPO_ROOT / "nginx.conf"

pytestmark = pytest.mark.skipif(not NGINX.exists(), reason="repo kökü görünmüyor (konteynerde yalnız backend/ mount'lu)")


def _politikalar() -> list[str]:
    yorumsuz = "\n".join(s.split("#", 1)[0] for s in NGINX.read_text(encoding="utf-8").splitlines())
    return re.findall(r'add_header\s+Permissions-Policy\s+"([^"]*)"\s+always;', yorumsuz)


def test_uc_yerde_ayni_politika():
    politikalar = _politikalar()
    assert len(politikalar) == 3, politikalar
    assert len(set(politikalar)) == 1, politikalar


def test_mikrofon_yalniz_kendi_originimize_acik():
    ozellikler = dict(p.strip().split("=", 1) for p in _politikalar()[0].split(","))
    assert ozellikler["microphone"] == "(self)"
    assert ozellikler["camera"] == "()"
    assert ozellikler["geolocation"] == "()"
