# Gece Kuyrugu (workflow) · 2026-10-07c

## Ozet

8 gorev alindi · 3 isaretlendi · 1 bloke · 4 atlandi (tavan nedeniyle atlanan: yok)

## Isaretlenenler

| gorev | bant | depo | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- | --- |
| G258 | lexis | lexis-rapor | — (zaten tamamdi: lexis-rapor 0200695 + 7d830af, bu kosuda yeni commit yok) | — (bu kosuda tur yok) | GECTI (5 bulgu) | Onceki kosuda yapilmis isin denetimi + isaretlemesi; 399 passed / 14 skipped (Postgres FTS skip), ruff temiz; HUKDOK'a sizma yok. Plan uyarisi: KUYRUK'ta [ ] kalmisti, HEAD ed1c98e "BLOKE kaldirildi, yeniden denetime" — bu kosuda kapandi. |
| G259 | lexis | lexis-rapor | 3a84ccd | GECTI (test temiz, kirmizi→yesil kanitlandi) | GECTI (7 bulgu) | 2 tur; 433 passed / 14 skipped, ruff temiz, compose config OK. Kararlar: 20 MB asimi 422 yerine 413 `{kod: boyut}` (README'de); bicim icerik imzasindan, uyusmazlik 422; `belge_indir` once kartin belge listesine bakar (baska kartin belgesi 404); uid 10001 icin compose'da tek seferlik `lexis_yukleme_hazirla` servisi (Dockerfile'da mkdir+chown alternatifi Rapor'da); requirements pinleri HUKDOK backend'iyle ayni (host testleri eski surumlerle kostu). Izlenecek: nginx `/lexis-api` govde tavani 20 MB (G262); pdf_okuyucu baslik yapistirma siniri (G265); `lexis_yukleme` birimi kisi verisi tasir, yedek insan adimi; gercek UDF / gercek token / birim sahipligi denenmedi. |
| G261 | lexis | lexis-rapor | 9767445 | GECTI (test temiz, kirmizi→yesil kanitlandi) | GECTI (5 bulgu) | 3 tur; 478 passed / 14 skipped, ruff temiz. Canli Gemini cagrisi YAPILMADI (K4, plan adim 6 ayri onay) — Field kisitlarinin response_schema donusumu ilk canli kosuda dogrulanmali. Postgres FTS aday yolu olculmedi (LEXIS_TEST_DB_URL yok). `LEXIS_EMSAL_DOSYA_TOKEN` kabul listesinde olmadigi icin yazilmadi; aday metni karakterle kirpiliyor. 409 yarisi dongu duzeyinde sinandi (TestClient akisi gercek akis degil). Kapsam disi: lexis-rapor CLAUDE.md hala "351 test" diyor. HUKDOK tarafi bekliyor: G262 (nginx allowlist + proxy_buffering off + Vite proxy), G264, G263. |

Not: lexis bandinin commit'leri `../lexis-rapor` deposundadir (push'suz) — sabah incelemesi ve push orada ayrica yapilir. Hicbir gorevde merge yapilmadi (`mergeYapildi=false`), entegrasyon "uygulanamaz".

## Bloke

### G260 — Kalici arsiv (`servis/sharepoint.py`, Graph, `03_LEXIS_EMSAL/<yil>/<sha>/`)

- **Durum:** is uygulandi, `verify=yesil`, commit **cd90f33** (lexis-rapor, push'suz); `isaretlendi=false`, `bloke=true`.
- **Durma sebebi:** KAPI — test butunlugu ihlali: yeni `# noqa` `tests/test_emsal_dosya.py:22` (`import emsal_arsiv_toparla  # noqa: E402`, `sys.path.insert` sonrasi `araclar/` betigi importu). Karar sabaha.
- **Son parmak izi:** yesil — 451 passed, 14 skipped (G258'in Postgres FTS testleri, LEXIS_TEST_DB_URL yok); ruff temiz.
- **Denenen yaklasimlar:** Tur 1: sharepoint.py + `arsivle_kayit` + tembel toparlama + arac + sahte Graph oturumlu testler yazildi; ilk turda yesil. Tek tur, kod degisikligi gerekmedi.
- **Teshisin kok nedeni:** kapi kurali "yeni noqa yok" mekanik uygulandi. Baglam: dosya bir TEST dosyasi; `lexis_rapor/ servis/ araclar/` altinda yeni noqa / type: ignore YOK; ayni desen eski commit'te `tests/test_profil_yukle.py:10`'da birebir var; E402 yalniz import sirasi uyarisi, test gucunu etkilemez. G258 emsalinde ayni kural BLOKE kaydettigi icin tutarlilik geregi burada da kaydedildi. Denetim kosulmadi (`denetim=null`).
- **Worktree:** yok (lexis bandi, calisma `../lexis-rapor` deposunda).
- **Onerilen sonraki adim:** sabah insan karari — (a) noqa'yi test dosyasinda kabul edip `/gorev-denetle G260` kosturarak isaretle, ya da (b) `araclar/` importunu `conftest`/paket yoluyla cozup noqa'siz hale getir (G258'de nasil kapatildigi emsal). Isaretlenince G263 → G264 → G265 → G266 zinciri acilir.
- **Ek notlar:** cd90f33 commit mesajinda baslik ile govde arasinda bos satir yok (heredoc hatasi; `git log --oneline` govdeyi basliga ekler) — amend kirmizi hat oldugundan dokunulmadi, sabah `--amend` kullanici karari. HUKDOK yukleyicisi surucu adini `SP_DRIVE_NAME`'den okurken `.env.example` `SHAREPOINT_DRIVE_NAME` yazar; Lexis gorev metnindeki `SHAREPOINT_DRIVE_NAME`'i kullanir (varsayilan Belgeler, Documents toleransi). Kapsam disi birakilan: pyproject servis ekstrasina `requests`, lexis-rapor CLAUDE.md komut listesi/test sayisi. Gercek SharePoint'e tek dosya denemesi insan adimi (Lexis `.env`'ine dort `SHAREPOINT_*` degeri + `docker compose up -d`). HUKDOK agacinda kosu sirasinda izlenmeyen `docs/plan/pdf-araclari-plani-2026-10-07.md` belirdi, dokunulmadi.

### Testi degistirmeden gecilemedi, gorev tanimi gozden gecirilmeli

Bu kosuda `durmaSebebi=test-degistirmek-gerekti` olan gorev yok. (G259 tur 1'deki 4 kirmizinin hepsi test tarafiydi — caplog suzgeci, sentetik PDF, sha sabiti, monkeypatch sirasi — kod degismedi; G261 tur 1-2'de de yalniz test beklentileri duzeltildi. Bunlar hattin dogru calistiginin kanitidir, basarisizlik degildir.)

## Karar bekleyenler

- `teshis.gorevTanimiHatali=true` olan gorev: yok.
- `kabulKarsilanmayan` madde: yok.
- Kosudan dogan sorular:
  1. G260: test dosyasindaki `# noqa: E402` kabul edilsin mi, yoksa import yolu noqa'siz cozulsun mu? (Kapi kurali test dosyalarini da kapsiyor mu — G258 emsaliyle tutarli karar gerekli.)
  2. G260: cd90f33 commit mesaji `--amend` ile duzeltilsin mi (push'suz, guvenli)?
  3. G259: 20 MB asiminda gorev metnindeki 422 yerine 413 `{kod: boyut}` kabul mu? (README'ye yazildi.)
  4. G261: Gemini canli cagrisi (plan adim 6) icin onay ne zaman?

## Izin engelleri

yok (G258, G259, G260, G261 hicbir izin engeli bildirmedi; G263-G266 kosmadi).

## Atlananlar

| gorev | bant | depo | sebep |
| --- | --- | --- | --- |
| G263 | lexis | lexis-rapor | bagimlilik bu kosuda tamamlanmadi: G260 (bloke) |
| G264 | frontend | hukdok | bagimlilik bu kosuda tamamlanmadi: G263 — worktree `C:/dev/hukudok-wt/G264` acildi, temizlenmedi (`worktreeTemizlendi=false`) |
| G265 | lexis | lexis-rapor | bagimlilik bu kosuda tamamlanmadi: G263 |
| G266 | docs | hukdok | bagimlilik bu kosuda tamamlanmadi: G264 — worktree `C:/dev/hukudok-wt/G266` acildi, temizlenmedi (`worktreeTemizlendi=false`) |

Zincir hatasi / teslim hatasi: yok. Tavan nedeniyle atlanan: yok.

Plan uyarilari (koşucudan): Lexis bandi gorevlerinin (G258-G265) dosya yollari `../lexis-rapor` deposuna goreli; G263 kapsaminda glob `tests/test_word*.py` var.
