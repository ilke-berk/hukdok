# Bağımlılık denetimi raporu — 2026-09

> TARİHSEL rapor (`docs/arsiv/`). Yazıldığı günün fotoğrafıdır; güncel sürümler `backend/requirements.txt`
> ve `frontend/package-lock.json`'dadır.

## 1. Özet

- **Tarih:** 2026-09-24 (zamanlanmış görev `hukdok-aylik-bagimlilik-denetimi`, skill `bagimlilik-denetle`)
- **main SHA:** `ac619f7` · **dal:** `bagimlilik/2026-09`
- **Uygulanan:** 24 paket (Python 9 + npm 15), bölmede elenen 2 birim (requests, Radix grubu)
- **Kapılar (hepsi yeşil):**
  - Backend (konteyner): pip-audit `No known vulnerabilities found, 2 ignored` · ruff `All checks passed!` ·
    mypy `Success: no issues found in 62 source files` · pytest `3603 passed, 3 skipped` (kapsam %77,51 ≥ 58)
  - Frontend: npm audit prod + dev temiz · lint 0 · `tsc -b --force` 0 · vitest `94 dosya, 1052 passed` · build 0
  - Not: koşu sırasında çalışma ağacında commit'e girmeyen, kullanıcıya ait koyu tema çalışması vardı
    (`frontend/src/index.css`, `styles/tokens.css` değişik; izlenmeyen `styles/tokens.contrast.test.ts`,
    `public/_koyu-tema.html`). vitest sayısı bu izlenmeyen test dosyasını da içerir; dokunulmadı.

SONUC: GUNCELLENDI 24 paket — dal bagimlilik/2026-09

## 2. Güvenlik açıkları

Yeni açık YOK.

| Paket | Kayıt | Kapatan sürüm | Durum |
| --- | --- | --- | --- |
| pytest 8.3.5 (yalnız dev) | PYSEC-2026-1845 | 9.0.3 | Mevcut, `backend/audit-ignore.txt`'te gerekçeli (gözden geçirme 2027-02-14); major → §5 |

npm prod + dev zinciri: 0 açık, aktif ignore yok.

## 3. Uygulananlar

### Python (`backend/requirements.txt`)

| Paket | Eski | Yeni | Sürüm notu | Kod etkisi |
| --- | --- | --- | --- | --- |
| python-dotenv | 1.2.2 | 1.2.3 | github.com/theskumar/python-dotenv CHANGELOG | Yok (yalnız bugfix; `load_dotenv` kullanımı `api.py:54` vb.) |
| google-genai | 2.11.0 | 2.25.0 | github.com/googleapis/python-genai/blob/main/CHANGELOG.md | Aralıkta BREAKING yok. `FinishReason.TOO_MANY_TOOL_CALLS` (2.17) `analyzer.py:884-923` bilinmeyen yoluna düşer, zararsız. AFC/Imagen kullanmıyoruz |
| pymupdf | 1.26.7 | 1.28.2 | pymupdf.readthedocs.io/en/latest/changes.html | `import fitz` artık FutureWarning basabilir (`pdf/pdf_utils.py:3`, `pdf/format_converter.py:22`, `routes/debug.py:56`); testlerde görülmedi. `import pymupdf as fitz` küçük temizlik işi |
| msal | 1.37.0 | 1.39.0 | github.com/AzureAD/microsoft-authentication-library-for-python/releases | `decode_id_token` kullanmıyoruz; yalnız `acquire_token_for_client` (`sharepoint/auth_graph.py:133,168`). `cryptography<51` ile uyumlu |
| python-multipart | 0.0.31 | 0.0.32 | Kludex/python-multipart CHANGELOG | Yok (performans) |
| slowapi | 0.1.9 | 0.1.10 | laurentS/slowapi | Yok |
| keyrings.alt | 5.0.0 | 5.0.2 | jaraco/keyrings.alt | Yok |
| psycopg2-binary | 2.9.9 | 2.9.13 | psycopg.org NEWS | Yok (API aynı; PG17/18 hata kodları) |
| cryptography | 50.0.0 | 50.0.1 | cryptography.io/en/latest/changelog | Yok (wheel OpenSSL 4.0.2) |

pip adımının gerçekten koştuğu `--progress=plain` ile doğrulandı; her paket `pip show`/`pip list` ile konteynerde teyitli.
Dolaylı paketler (starlette 1.7.0, urllib3 2.8.0, anyio 4.15.1 vb.) pin'siz oldukları için her rebuild'de zaten
güncel gelir — bu dal onları değiştirmez, prod'un bir sonraki build'i de aynısını alır.

### npm (`frontend/package-lock.json`; `package.json` aralıkları hedefi kapsadığından değişmedi)

| Paket | Eski | Yeni | Sürüm notu | Kod etkisi |
| --- | --- | --- | --- | --- |
| @tanstack/react-query | 5.83.0 | 5.103.2 | TanStack/query packages/react-query/CHANGELOG.md | 5.102'de kaldırılan deneysel API'ler (`experimental_prefetchInRender`, `promise` alanı, `experimental_before/afterQuery`) kullanılmıyor; 26 dosya |
| typescript | 5.8.3 | 5.9.3 | TS 5.9 release notes | `ArrayBuffer`/TypedArray tip değişikliği; tek aday `lib/caseIntake.ts:188`, `tsc -b --force` temiz |
| typescript-eslint | 8.38.0 | 8.70.1 | typescript-eslint.io/users/dependency-versions | TS `<6.1.0` destekli; TS ile tek birim |
| eslint + @eslint/js | 9.32.0 | 9.39.5 | eslint.org blog | Yeni kurallar recommended'a girmedi; lint temiz. **ESLint 9 desteği 2026-08-06'da bitti** (§5) |
| react-router | 7.18.2 | 7.18.4 | remix-run/react-router CHANGELOG | Yalnız RSC/SSR düzeltmeleri; declarative mod etkilenmez |
| tailwindcss | 3.4.17 | 3.4.19 | tailwindlabs/tailwindcss v3 CHANGELOG | Yok |
| autoprefixer | 10.4.21 | 10.6.1 | postcss/autoprefixer CHANGELOG | `-webkit-fill-available` sırası (10.5.2); build temiz |
| postcss | 8.5.26 | 8.5.28 | — | Yama |
| @tailwindcss/typography | 0.5.16 | 0.5.20 | — | Yama |
| tailwind-merge | 2.6.0 | 2.6.1 | — | Yama (`lib/utils.ts:2`) |
| @types/react | 18.3.23 | 18.3.31 | — | Tip yaması |
| @types/node | 22.16.5 | 22.20.4 | — | Tip yaması |
| eslint-plugin-react-refresh | 0.4.20 | 0.4.26 | ArnaudBarre/eslint-plugin-react-refresh CHANGELOG | 0.4.25 sıkılaştırması 0.4.26'da geri alındı; `eslint.config.js:22` |
| lovable-tagger | 1.1.11 | 1.3.4 | unpkg package.json | Yalnız dev modda (`vite.config.ts:5,66-67`); peer `vite >=5 <9` |

## 4. Bölmede elenenler

| Birim | Hata özeti | Taşındığı sınıf |
| --- | --- | --- |
| requests 2.33.0 → 2.34.2 | mypy: `managers/activity_manager.py:256: error: Argument "json" to "post" has incompatible type "dict[str, Collection[str]]"; expected "JsonType \| None"` — 2.34 typeshed yerine satır içi tip getirdi | AYRI GÖREV |
| Radix grubu (13 paket; alert-dialog 1.1.23, checkbox 1.3.11, collapsible 1.1.20, dialog 1.1.23, dropdown-menu 2.1.24, label 2.1.15, popover 1.1.23, select 2.3.7, slot 1.3.3, switch 1.3.7, tabs 1.1.21, toast 1.2.23, tooltip 1.2.16) | `ReportsPage.test.tsx` "kaynak değişince eski kaynağın satırları ANINDA kaybolur…" deterministik kırmızı: `expected [ …(3) ] to have a length of 2 but got 3` (satır 693 — bekleyen "x" filtresi kaynak değişiminde ek bir önizleme isteği doğuruyor). Bölme suçluyu `@radix-ui/react-popover` 1.1.23'e daralttı; ama popover'ı eski tutmak ortak primitifleri (dismissable-layer, focus-scope, presence…) çift kopyaya böldü (lock +3053 satır) → iç içe katman (dialog içinde popover) riski testlerde görünmez. Grup TEK birim sayıldı, tamamı geri alındı | AYRI GÖREV |

## 5. Ayrı görev önerileri

Önerilen sıra riske ve bağımlılığa göredir. `gorevler/`'e yazılmadı — kullanıcı `/plan-hazirla` ile açar.

1. **APScheduler 3.10.4 → 3.11.3 + pytz temizliği (ÖNCE bu).** 3.11 `pytz`'yi bağımlılıktan çıkardı (yalnız `test` extra).
   `backend/api.py:192` `import pytz`, `:194,197,210,224` `pytz.timezone("Europe/Istanbul")`; pytz requirements'ta
   YOK, bugün apscheduler 3.10.4 ve (kullanılmayan) Office365 üzerinden dolaylı geliyor. İkisi de bırakırsa
   `ImportError` `api.py:252-253`'te "apscheduler yüklü değil" uyarısıyla YUTULUR → 00:00 rapor, 02:30 retry,
   06:00 süre taraması SESSİZCE kapanır. Kapsam: `zoneinfo.ZoneInfo`'ya geçiş (python:3.12-slim'de tzdata
   varlığı doğrulanmalı — yoksa `tzdata` pin) + import hatasının yutulmaması + apscheduler bump. Risk: orta (zamanlayıcı).
2. **requests 2.34.2.** `activity_manager.py:256` payload tipini (`dict[str, Any]`) düzelt, bump et. Risk: düşük.
3. **Radix grubu.** Popover 1.1.23 ile `pages/ReportsPage` filtre düzenleyicisinin kapanma/odak akışı değişti
   (dropdown 2.1.18 "pencere odağı kaybında kapanır", select 2.3.1 `value=""` = temizle, select 2.3.3 Space/Enter
   yutulmuyor). Kapsam: `components/ui/{select,switch,button,popover}.tsx`, `ReportsPage`'in `TanimSeridi`
   filtre popover'ı; testin yakaladığı davranışın kök nedeni bulunup kod düzeltilir (TEST GEVŞETİLMEZ), grup
   birlikte güncellenir, tarayıcıda select/dropdown/popover dumanı. Risk: orta.
4. **MSAL frontend: @azure/msal-browser 5.1.0 → 5.23.0 + @azure/msal-react 5.0.3 → 5.7.1** (aynı major, ama
   kimlik yolu). 5.6.2 redirect yanıtı sessionStorage'a, 5.8.0 önbellek şema sürümü, 5.15.0 idToken'da
   `signin_state`/`login_hint`. Kullanım: `config/msalConfig.ts:16`, `App.tsx:171-196`, `lib/api.ts:40,144`,
   `Login.tsx:43`, `Sidebar.tsx:92`, `useIdleTimeout.ts:36`, 16 dosyada `useMsal`. Artı: kilitli msal-react 5.0.3
   peer'i `react ^19.2.1` istiyor ve `frontend/.npmrc` `legacy-peer-deps=true` bunu örtüyor; 5.2.0+ React 16.8+
   destekler → güncelleme uyuşmazlığı gerçekten çözer, `.npmrc` gerekçesi gözden geçirilebilir. Birim testleri
   akışı yakalamaz: lokalde giriş, sessiz token yenileme, çıkış elle denenmeli. Risk: orta-yüksek (giriş).
5. **PyJWT 2.13.0 → 2.15.0.** 2.14 güvenlik sertleştirmesi: `PyJWKClient` redirect izlemiyor, bilinmeyen `kid`
   için yenileme sınırlı, boş HMAC anahtarı reddi; 2.15 sayısal olmayan exp/nbf/iat hata. Kullanım
   `auth_verifier.py:69,98-100,117-128`. Kimlik doğrulama yolu olduğu için şüphe kuralıyla GÜVENLİ'den çıkarıldı;
   bump + auth testleri + lokalde gerçek girişle duman. Risk: düşük-orta.
6. **pydantic 2.12.5 → 2.13.5 + pydantic-settings 2.11.0 → 2.15.0** (tek birim; fastapi 0.141.1 `>=2.9` ile uyumlu).
   2.13'te JSON schema düzeltmeleri + discriminated union serileştirme davranışı; Gemini `response_schema`'ya
   giden şemalar (`schemas_intake.py`, `schemas_rapor.py`) ÖNCE/SONRA karşılaştırılmalı. settings 2.15
   `case_sensitive` init kaynaklarına da uygulanıyor (`config/settings.py:37-43`). Risk: orta.
7. **uvicorn 0.38.0 → 0.53.0** (15 minor). 0.50 açılış hatasında çıkış kodu 3 + supervisor durur (worker sonsuz
   yeniden başlatma yerine konteyner düşer), 0.51 SIGHUP'ta sıralı yeniden başlatma, ProxyHeaders değişiklikleri.
   `docker-entrypoint.sh:17` (`--workers`). 2 worker + lider kilidi ile duman şart. Risk: orta.
8. **SQLAlchemy 2.0.25 → 2.0.54** (29 yama). Compound select davranış değişikliği görülmedi ama 26-45 arası kalem
   kalem okunamadı. Kullanım `managers/case_manager.py:11,810,933` (`union`/`intersect`), `services/rapor/registry.py:99,1368`.
   Arama (E8) testleri + EXPLAIN karşılaştırması. Risk: düşük-orta.
9. **reportlab 4.2.5 → 4.5.1** (son 4.x). Tablo satır bölme düzeltmeleri bizim `LongTable(splitByRow=1, splitInRow=1)`
   + `_splitCell` workaround'una dokunur (`udf_converter.py:67,334,439`; 28.08 prod arızası). UDF görselli tablo
   regresyon seti şart. Risk: orta.
10. **Dev araçları** (`requirements-dev.txt`): pytest 8.3.5 → 9.1.1 (PYSEC-2026-1845'i kapatır; `PytestRemovedIn9Warning`
    hata olur, None dışı dönen test fail, pytest-cov 7.1.0 uyumu doğrulanmalı) · ruff 0.15.21 → 0.16.8 (varsayılan
    kural seti değişti; bizde `select=E,F,B` açık, etki sınırlı) · mypy 2.2.0 → 2.3.1 (düşük risk).
11. **Frontend majorları** (her biri ayrı iş):
    - eslint 10 + @eslint/js 10 + eslint-plugin-react-hooks 7 + react-refresh 0.5 + globals 17 — birlikte; hooks 7'nin
      React Compiler kuralları muhtemelen çok ihlal çıkarır. **ESLint 9 destek dışı** olduğundan öncelikli.
    - vitest 5 (Vite 6.4+ ile çalışır, vite 8'den bağımsız; `clearMocks` varsayılan açık → 88+ test dosyası etkilenebilir).
    - vite 8 + @vitejs/plugin-react-swc 4.3+ (lovable-tagger 1.3 uyumlu) — Rolldown tabanı.
    - react/react-dom 19 + @types 19 — tüm uygulama (shadcn `ui/*` forwardRef).
    - lucide-react 1.x (70 dosya, marka ikonu yok → düşük risk) · sonner 2 · next-themes 0.4.
    - tailwindcss 4 + tailwind-merge 3 — tek birim, büyük iş.
    - typescript 7 — ENGELLİ (typescript-eslint yalnız `<6.1.0`).
    - @types/node 26 — önerilmez; çalışma ortamı Node 24, 22/24 tip hattında kalınmalı.

Yan bulgular (bağımlılık dışı, ayrı küçük iş):
- `components/ui/sonner.tsx:1` `useTheme`'i next-themes'ten alıyor ama uygulamada next-themes sağlayıcısı yok
  (`App.tsx:247` kendi `ThemeProvider`'ımız) → toast'lar koyu/açık temayı izlemiyor olabilir (kod okumasıyla; tarayıcıda denenmedi).
  next-themes paketi kaldırılabilir.
- lovable-tagger yalnız Lovable editörü için; editör kullanılmıyorsa paketi kaldırmak daha temiz.

## 6. İnsan kararı bekleyenler

| Kalem | Gerekçe | Önerilen yol |
| --- | --- | --- |
| Office365-REST-Python-Client 2.6.2 → 3.1.0 | Major (arşiv kütüphanesi kuralı). Ancak backend'de `office365`/`ClientContext` importu YOK; SharePoint erişimi msal + Graph (`sharepoint/auth_graph.py`) | Güncelleme yerine requirements'tan ÇIKARMA — ama pytz'nin son dolaylı kaynağıdır: önce §5.1 (zoneinfo) |
| reportlab 5.x | Major; 5.0 uzak görsel `trustedHosts` varsayılanı "hiçbiri", `_renderPM`/pyRXP kaldırıldı — bizde görseller BytesIO/yerel (`udf_converter.py:324,572,583`) | Önce §5.9 (4.5.1), sonra ayrı karar |
| postgres:15-alpine → 17/18 | Major; dump/restore ister | Planlı bakım penceresi + pre-deploy dump; ayrı plan |
| python:3.12-slim → 3.13/3.14 | İmaj major; reportlab `ast.NameConstant` 3.14'te kalkıyor (pytest uyarısı) | reportlab ve bağımlılık güncellemelerinden sonra |
| node:24 | Güncel LTS hattı; Node 26 Ekim 2026'da LTS olur | Şimdilik kal |
| nginx:alpine | Kayan etiket; yama rebuild'de gelir | Değişiklik yok |

**Geçilmez:** apscheduler 4.x (API baştan değişti) — yalnız 3.x yamaları (§5.1).

## 7. Sonraki adım (kullanıcı)

1. Dalı incele: `git log main..bagimlilik/2026-09`, `git diff main bagimlilik/2026-09 -- backend/requirements.txt`.
2. `/ci-kontrol` (push öncesi lokal CI eşdeğeri) → birleştirme kararı → push → CI yeşil → deploy kararı
   (deploy'da backend imajı yeni pinlerle kurulur; Gemini analizi + SharePoint yüklemesi + PDF/A dönüşümü dumanı önerilir).
3. §5 listesinden görev açmak için `/plan-hazirla` — önerilen ilk iş §5.1 (pytz/zoneinfo), çünkü sessiz arıza riski taşıyor.
