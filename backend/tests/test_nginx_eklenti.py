"""Word eklentisi nginx bekçisi (G286, plan §6.2 K16, §6.5 "CSP").

`add_header` kalıtım tuzağı yüzünden CSP beş yerde yazılıdır: server, `/assets/`, `/`, `= /eklenti/manifest.xml`
(dördü BİREBİR aynı) ve `/eklenti` görev bölmesi — bu kopya YALNIZ `frame-ancestors`'ta farklıdır (Word web bölmeyi
Office alan adlarından çerçeveler; ana sayfa `'self'` kalır). Office.js CDN'i `script-src`'de
(`officeapis.public.onecdn.static.microsoft` — Microsoft Learn, 23.09.2026; eski `appsforoffice` ucu gerekmez).
`/eklenti`'de X-Frame-Options BİLEREK yok (SAMEORIGIN Office çerçevelemesiyle çelişir); diğer dört başlık tam.
Manifest `application/xml` + `no-cache`; yer tutucu dosya geçerli XML, `<Id>` GUID, `SourceLocation` `/eklenti`.

Konteynerde repo kökü görünmediği için atlanır; CI'da (repo checkout'u) koşar.
"""
import re
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NGINX = REPO_ROOT / "nginx.conf"
MANIFEST = REPO_ROOT / "frontend" / "public" / "eklenti" / "manifest.xml"

pytestmark = pytest.mark.skipif(not NGINX.exists(), reason="repo kökü görünmüyor (konteynerde yalnız backend/ mount'lu)")

OFFICE_JS = "https://officeapis.public.onecdn.static.microsoft"
ANA_ATALAR = "frame-ancestors 'self'"
EKLENTI_ATALAR = "frame-ancestors 'self' https://*.officeapps.live.com https://*.office.com https://word.cloud.microsoft"
NS = {"o": "http://schemas.microsoft.com/office/appforoffice/1.1"}


def _yorumsuz() -> str:
    return "\n".join(s.split("#", 1)[0] for s in NGINX.read_text(encoding="utf-8").splitlines())


def _blok(baslangic: str) -> str:
    """`location ...` satırından eşleşen kapanış süslüsüne kadar (iç içe `types { }` dahil)."""
    metin = _yorumsuz()
    i = metin.index(baslangic)
    derinlik, j = 0, metin.index("{", i)
    for k in range(j, len(metin)):
        if metin[k] == "{":
            derinlik += 1
        elif metin[k] == "}":
            derinlik -= 1
            if derinlik == 0:
                return metin[i : k + 1]
    raise AssertionError(baslangic)


def _csp(metin: str) -> list[str]:
    return re.findall(r'add_header\s+Content-Security-Policy\s+"([^"]*)"\s+always;', metin)


def _yonergeler(csp: str) -> dict[str, str]:
    return {p.strip().split(" ", 1)[0]: p.strip() for p in csp.split(";") if p.strip()}


def test_bes_kopya_ve_yalniz_frame_ancestors_farki():
    tumu = _csp(_yorumsuz())
    assert len(tumu) == 5, tumu
    eklenti = _csp(_blok("location ~ ^/eklenti(/|$)"))
    assert len(eklenti) == 1
    digerleri = [c for c in tumu if c != eklenti[0]]
    assert len(digerleri) == 4 and len(set(digerleri)) == 1, "server, /assets/, /, manifest kopyaları AYNI olmalı"
    ana, ek = _yonergeler(digerleri[0]), _yonergeler(eklenti[0])
    assert ana["frame-ancestors"] == ANA_ATALAR
    assert ek["frame-ancestors"] == EKLENTI_ATALAR
    assert {k: v for k, v in ana.items() if k != "frame-ancestors"} == {k: v for k, v in ek.items() if k != "frame-ancestors"}


def test_office_js_script_src_ve_msal_connect_src():
    for csp in _csp(_yorumsuz()):
        y = _yonergeler(csp)
        assert y["script-src"] == f"script-src 'self' {OFFICE_JS}"
        assert "https://login.microsoftonline.com" in y["connect-src"]
        assert "appsforoffice.microsoft.com" not in csp and "ajax.aspnetcdn.com" not in csp


def test_eklenti_locationi_guvenlik_basliklari():
    blok = _blok("location ~ ^/eklenti(/|$)")
    for baslik in ("X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy", "Content-Security-Policy"):
        assert re.search(rf"add_header\s+{baslik}\s", blok), baslik
    assert "X-Frame-Options" not in blok, "Office çerçevelemesiyle çelişir; tek kaynak CSP frame-ancestors"
    assert 'add_header Cache-Control "no-cache"' in blok
    # /index.html dosya olarak BU location'da servis edilir (son argüman değil) → başlıklar location / 'a düşmez.
    assert "try_files $uri /index.html =404;" in blok


def test_manifest_locationi():
    blok = _blok("location = /eklenti/manifest.xml")
    assert "default_type application/xml;" in blok and "types { }" in blok
    assert 'add_header Cache-Control "no-cache"' in blok
    for baslik in ("X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy", "Content-Security-Policy"):
        assert re.search(rf"add_header\s+{baslik}\s", blok), baslik


def test_ana_sayfa_frame_ancestors_daraltilmis_kalir():
    for bas in ("location / {", "location ~* ^/assets/ {"):
        assert _yonergeler(_csp(_blok(bas))[0])["frame-ancestors"] == ANA_ATALAR


def test_yer_tutucu_manifest_gecerli():
    kok = ET.parse(MANIFEST).getroot()
    assert kok.tag == f"{{{NS['o']}}}OfficeApp"
    uuid.UUID(kok.findtext("o:Id", namespaces=NS))
    kaynak = kok.find("o:DefaultSettings/o:SourceLocation", NS).get("DefaultValue")
    assert kaynak.startswith("https://") and kaynak.endswith("/eklenti")
    assert kok.find("o:Hosts/o:Host", NS).get("Name") == "Document"
