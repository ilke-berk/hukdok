# Gece Kuyrugu (workflow) · 2026-08-22

## Ozet

4 gorev alindi · 4 isaretlendi · 0 bloke · 0 atlandi

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G092 — Token doğrulama: issuer kontrolü + scp/aud gözlem modu | backend | `19aa5c1` | gecti (kirmizi-yesil kanitlandi; 1967 passed/3 skipped, ruff+mypy temiz) | GECTI (2 bulgu) | 1 tur. Merge YAPILMADI, worktree yok (ana repoda calisildi). Insan adimi: rebuild + gercek Microsoft girisi; 401 gelirse gercek `iss` bicimi farklidir. Gozlem WARNING'leri toplanip scp/aud faz 2 ayri gorev olarak acilmali. |
| G093 — Konfigürasyon uyarıları: DEV_MODE prod guard + SharePoint secret expiry | backend | `f6eb466` | gecti (kirmizi-yesil kanitlandi; 1990 passed/3 skipped, ruff+mypy temiz) | GECTI (3 bulgu) | 2 tur (tur 1: 2 kirmizi — kok handler/configure_logging sirasi + .env.example konteynerde yok). `.env.example` kabulu kod testiyle DEGIL goz denetimiyle kapatildi (repo koku mount edilmiyor). Merge YAPILMADI. Insan adimi: prod `.env`'e `SHAREPOINT_CLIENT_SECRET_EXPIRES_AT` gercek tarih. |
| G095 — Oturum kapanış yolu: #/login artığı + boşa giden 401 turu | frontend | `7c97004` | gecti (kirmizi-yesil kanitlandi: stash ile eski kodda 5 failed/22 passed; 520 passed, lint 0 error, tsc exit 0, `#/login` grep 0) | GECTI (2 bulgu) | 1 tur. Merge yapildi, entegrasyon yesil, worktree temizlendi. DIKKAT: `api.test.ts:67` testi gorev dosyasinin ACIK talimatiyla yeniden yazildi (silinmedi; gerekce test dosyasinda yorum). Denetci gecti; insan ayrica goz atmali. |
| G094 — Kimlik ve token mimarisi dokümanı | docs | `754c871` | gecti (test-yok; kirmizi-yesil uygulanamaz) | GECTI (2 bulgu; satir atiflari tek tek dogrulandi) | 1 tur. Merge yapildi, worktree temizlendi. Kapsam disi bulgu (duzeltilmedi): `docs/mimari/dis-bagimliliklar.md:88,168,175` surumler bayat (msal 1.34.0/PyJWT 2.8.0/cryptography 42.0.5 yaziyor; requirements.txt 1.37.0/2.13.0/50.0.0). Entra token omru §3.2'de "TEYIT EDILMEDI" — kullanici teyidi bekliyor. |

Not: G092 ve G093 icin `mergeYapildi=false`, `worktree=null` — ana repoda dogrudan commit'lendi; G095/G094 worktree dalindan merge edildi ve temizlendi.

## Bloke

Bloke gorev yok.

## Karar bekleyenler

- `teshis.gorevTanimiHatali=true` olan gorev yok; `kabulKarsilanmayan` listeleri bos.
- SORU (G093): `.env.example` kabulu konteynerde test edilemiyor (repo koku mount edilmiyor). Goz denetimi + rapor serhi yeterli sayilsin mi, yoksa host tarafinda ayri bir kontrol mu istenir?
- SORU (G095): isci sozlesmesindeki "mevcut testi degistirme" kurali ile gorev dosyasinin "api.test.ts:67'yi yeniden yaz" talimati catisti; gorev tanimi ustun tutuldu. Bu tercih onaylaniyor mu?
- SORU (G092, plan uyarisi): gercek Azure AD token'ina karsi `iss` zorlamasi denenmedi — deploy oncesi insan turu (rebuild + gercek giris) sart.
- SORU (G094): `dis-bagimliliklar.md` bayat surumler icin ayri kucuk gorev acilsin mi?

## Izin engelleri

yok

## Atlananlar

yok (atlandi / zincirHatasi / teslimHatasi olan gorev yok; tavan nedeniyle atlanan yok)

## Plan uyarilari (kosucudan)

- G092 deploy oncesi insan turu ister (gercek Azure AD token'ina karsi iss zorlamasi denenmemis olacak).
- G095 frontend bandi backend bandiyla paralel kosabilir; G094 uc gorevi de bekler.
- Calisma agacindaki kapsam disi kirli dosyalar (`.claude/settings.local.json` M, `.claude/launch.json` ??) kosucu altyapisi oldugu icin dokunulmadi, commit'lere alinmadi.
