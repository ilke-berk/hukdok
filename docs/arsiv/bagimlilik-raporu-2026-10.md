# Bağımlılık denetimi raporu — 2026-10

> TARİHSEL rapor (`docs/arsiv/`). Yazıldığı günün fotoğrafıdır; güncel sürümler `backend/requirements.txt`
> ve `frontend/package-lock.json`'dadır.

## 1. Özet

- **Tarih:** 2026-10-01 (zamanlanmış görev `hukdok-aylik-bagimlilik-denetimi`, skill `bagimlilik-denetle`)
- **main SHA:** `2fa503b` · **dal:** `bagimlilik/2026-10`
- **Uygulanan:** 8 paket (Python 5 + npm 3), bölmede elenen yok
- **Kapılar (hepsi yeşil):**
  - Backend (konteyner): pip-audit `No known vulnerabilities found` · ruff `All checks passed!` ·
    mypy `Success: no issues found in 65 source files` · pytest `4082 passed, 15 skipped` (taban 4082; kapsam %80,54 ≥ 58)
  - Frontend: npm audit prod + dev temiz · lint 0 · `tsc -b --force` 0 · vitest `123 dosya, 1320 passed` (taban 1320) · build 0

SONUC: GUNCELLENDI 8 paket — dal bagimlilik/2026-10

## 2. Güvenlik açıkları

Açık YOK. pip-audit (doğrudan + dolaylı + dev) temiz, `backend/audit-ignore.txt` boş; npm prod + dev zinciri 0 açık,
aktif ignore yok.

## 3. Uygulananlar

### Python (`backend/requirements.txt`)

| Paket | Eski | Yeni | Sürüm notu | Kod etkisi |
| --- | --- | --- | --- | --- |
| fastapi | 0.141.1 | 0.142.2 | fastapi.tiangolo.com/release-notes | 0.142.0 yerleşik OpenTelemetry desteği; yalnız `OTEL_*` env + `fastapi[opentelemetry]` extra ile devreye girer — repoda `OTEL_`/`opentelemetry` kullanımı YOK. 0.142.1 (included router'da endpoint'in tekrar sarılması) ve 0.142.2 (OTel yapılandırması başarısızsa açılışın düşmesi) 0.142.0 hatalarının yamaları; ikisi de hedefte var. **Yeni dolaylı bağımlılık:** `opentelemetry-api 1.45.0` imaja giriyor (pip-audit temiz). starlette 1.7.0 değişmedi |
| python-dotenv | 1.2.3 | 1.2.4 | github.com/theskumar/python-dotenv CHANGELOG | Ayrıştırma düzeltmesi: `KEY= # yorum` artık boş değer (önceden yorum metni değer olurdu). `.env.example`'da bu kalıp yok; `load_dotenv` çağrıları `api.py:89`, `analyzer.py:47`, `vault.py:134`, `sharepoint/auth_graph.py:90` vb. **Prod `.env`'inde boş değer + satır içi yorum varsa** davranış düzelir (deploy öncesi `grep -nE '^[A-Z_]+= *#' .env` önerilir) |
| google-genai | 2.25.0 | 2.26.0 | github.com/googleapis/python-genai CHANGELOG.md | BREAKING yok; yeni özellikler (labels, TTS modelleri, environments), Vertex/aiohttp düzeltmeleri. Developer API + `generate_content` yolumuz etkilenmez |
| PyJWT | 2.15.0 | 2.15.1 | github.com/jpadilla/pyjwt CHANGELOG.rst | Tek düzeltme: JWS segmentlerinde sondaki Base64URL `=` dolgusu kabul ediliyor (önceden `DecodeError`). Yalnız gevşeme yönünde; geçersiz alfabe hâlâ red. `auth_verifier.py` imza/aud/iss doğrulaması değişmez |
| cryptography | 50.0.1 | 50.0.2 | cryptography.io/en/latest/changelog | Yok (wheel OpenSSL 4.0.3, PyO3 0.29.2) |

pip adımının gerçekten koştuğu `--progress=plain` ile doğrulandı (`Successfully installed ... fastapi-0.142.2 ...`);
beş paket `pip show` ile konteynerde teyitli. Dolaylı paketler pin'siz olduğundan rebuild'de güncel geldi
(charset-normalizer 3.5.2, google-auth 2.59.1, wrapt 2.5.0) — prod'un bir sonraki build'i de aynısını alır.

### npm (`frontend/package-lock.json`; `package.json` aralıkları hedefi kapsadığından değişmedi)

| Paket | Eski | Yeni | Sürüm notu | Kod etkisi |
| --- | --- | --- | --- | --- |
| @tanstack/react-query | 5.103.2 | 5.104.0 | github.com/TanStack/query/releases | Yalnız paketin kendi build'i Vite 8'e geçti; API değişikliği yok |
| typescript-eslint | 8.70.1 | 8.71.0 | github.com/typescript-eslint/typescript-eslint/releases | Yeni kural `no-unsafe-enum-assignment` recommended'a girmedi; 4 kural düzeltmesi; TS aralığı aynı (TS 5.9.3) — lint temiz |
| lovable-tagger | 1.3.4 | 1.3.5 | unpkg package.json | Yalnız dev modda (`vite.config.ts`); yama |

## 4. Bölmede elenenler

Yok — ilk koşuda tüm kapılar yeşil.

## 5. Ayrı görev önerileri

Eylül raporundaki (`bagimlilik-raporu-2026-09.md` §5) açık kalemler hâlâ geçerli; aradan kapananlar: apscheduler
3.11.3 + pytz/zoneinfo, requests 2.34.2, PyJWT 2.15.x, pytest 9.1.1, ruff 0.16.8, mypy 2.3.1. Önerilen sıra:

1. **MSAL frontend: @azure/msal-browser 5.1.0 → 5.23.0 + @azure/msal-react 5.0.3 → 5.7.1** (aralık içinde ama
   kimlik yolu; gerekçe Eylül §5.4 — 5.6.2 redirect yanıtı sessionStorage'a, 5.8.0 önbellek şema sürümü, msal-react 5.0.3
   peer'i `react ^19` istiyor ve `.npmrc legacy-peer-deps` örtüyor). Lokalde giriş / sessiz yenileme / çıkış dumanı şart. Risk: orta-yüksek.
2. **Radix grubu (13 paket, aralık içinde).** Eylül §5.3: popover 1.1.23 `ReportsPage.test.tsx` filtre testini
   deterministik kırıyordu; kök neden bulunmadan grup bölünemez (lock'ta çift kopya primitif). TEST GEVŞETİLMEZ. Risk: orta.
3. **pydantic 2.12.5 → 2.13.5 + pydantic-settings 2.11.0 → 2.15.0** (tek birim; Eylül §5.6 — Gemini `response_schema`
   ÖNCE/SONRA karşılaştırması, settings `case_sensitive` init kaynakları `config/settings.py`). Risk: orta.
4. **uvicorn 0.38.0 → 0.54.0** (16 minor; Eylül §5.7 — 0.50 açılış hatasında çıkış kodu 3 + supervisor durur;
   `docker-entrypoint.sh` `--workers`, 2 worker + lider kilidi dumanı). Risk: orta.
5. **SQLAlchemy 2.0.54 → 2.1.1.** Minor numaralı ama 2.1 serisi davranış değişiklikleri taşır (asgari Python,
   typing, bazı ORM varsayılanları); şüphe kuralıyla AYRI GÖREV. Kullanım `managers/case_manager.py` (`union`/`intersect`
   arama ağacı), `services/rapor/registry.py`, `database.py` migrasyonları. Kapsam: 2.1 migration notlarını kalem kalem
   okuma + E8 arama testleri + EXPLAIN karşılaştırması + `deploy.sh --gate-only` şema kapısı. Risk: orta.
6. **reportlab 4.2.5 → son 4.x** (Eylül §5.9; `udf_converter.py` `LongTable(splitByRow=1, splitInRow=1)` + `_splitCell`
   workaround'u; UDF görselli tablo regresyon seti). Risk: orta.
7. **Frontend majorları** (her biri ayrı iş, Eylül §5.11 ile aynı): eslint 10 + @eslint/js 10 + react-hooks 7 +
   react-refresh 0.5 + globals 17 (ESLint 9 destek dışı → öncelikli) · vitest 5 · vite 8 + plugin-react-swc 4 ·
   react/react-dom/@types 19 · lucide-react 1.x · sonner 2 · next-themes 0.4 (ya da kaldırma, Eylül yan bulgusu) ·
   tailwindcss 4 + tailwind-merge 3 · typescript 7 (typescript-eslint desteğine bağlı, ENGELLİ) · @types/node 26 önerilmez
   (Node 24 hattı).
8. **Dev aracı:** ruff 0.16.8 → 0.16.9 (`requirements-dev.txt`; yama, bu skill'in kapsamı `requirements.txt` olduğundan
   uygulanmadı — bir sonraki dev araç turunda). Risk: düşük.

## 6. İnsan kararı bekleyenler

| Kalem | Gerekçe | Önerilen yol |
| --- | --- | --- |
| ~~Office365-REST-Python-Client 2.6.2 → 3.2.0~~ | **KARAR VERİLDİ (2026-10-01, kullanıcı): paket kaldırıldı** — ayrı commit, bkz. §6.1 | — |
| reportlab 5.0.1 | Major; 5.0 uzak görsel `trustedHosts` varsayılanı, `_renderPM`/pyRXP kaldırıldı | Önce §5.6 (son 4.x), sonra ayrı karar |
| postgres:15-alpine → 17/18 (Docker Hub: 18.6 güncel) | Major; dump/restore ister | Planlı bakım penceresi + pre-deploy dump; ayrı plan |
| python:3.12-slim → 3.13/3.14 | İmaj major; reportlab `ast.NameConstant` 3.14'te kalkıyor | reportlab ve bağımlılık güncellemelerinden sonra |
| node:24 → 26 | Docker Hub'da `26` (26.10) yayında; Node 26 Ekim 2026 sonunda LTS olur | LTS'e geçtikten sonra ayrı iş; vite/vitest majorlarıyla birlikte düşünülmeli |
| nginx:alpine | Kayan etiket; yama rebuild'de gelir | Değişiklik yok |

### 6.1 Office365-REST-Python-Client kaldırıldı (aynı gün, kullanıcı kararı)

- Backend'de hiçbir import yoktu; SharePoint erişimi msal + Microsoft Graph (`sharepoint/auth_graph.py`,
  `services/upload_queue.py`). Word Online'da açma Graph `webUrl` ile zaten mümkün; sunucuda Word üretimi
  gerekirse doğru araç `python-docx`'tir — bu paket ikisini de yapmaz.
- Paketle birlikte imajdan düşen dolaylı bağımlılık: `pytz` (kodda kullanım yok — G198 `zoneinfo`'ya geçti;
  bekçi `tests/test_g198_zamanlayici_zoneinfo.py`). msal/requests/typing-extensions doğrudan ya da başka yoldan kalır.
- Doğrulama: `--progress=plain` rebuild (Successfully installed listesinde office365/pytz YOK), konteynerde
  `find_spec('pytz')` ve `find_spec('office365')` → None, `ZoneInfo('Europe/Istanbul')` çalışıyor;
  pip-audit temiz · ruff · mypy (65 dosya) · pytest `4082 passed, 15 skipped`.
- Kalan majorların uygulama planı: `docs/plan/bagimlilik-majorlar-plani-2026-10-01.md`.

**Geçilmez:** apscheduler 4.x (API baştan değişti) — 3.11.3'te kalınır.

## 7. Sonraki adım (kullanıcı)

1. Dalı incele: `git log main..bagimlilik/2026-10`, `git diff main bagimlilik/2026-10 -- backend/requirements.txt`.
2. `/ci-kontrol` (push öncesi lokal CI eşdeğeri) → birleştirme kararı → push → CI yeşil → deploy kararı
   (deploy'da backend imajı yeni pinlerle kurulur; prod `.env`'de `KEY= # yorum` kalıbı kontrolü + giriş ve Gemini analizi dumanı önerilir).
3. §5 listesinden görev açmak için `/plan-hazirla` — önerilen ilk iş §5.1 (MSAL) ya da ESLint 9 destek dışı olduğu için §5.7 eslint grubu.
