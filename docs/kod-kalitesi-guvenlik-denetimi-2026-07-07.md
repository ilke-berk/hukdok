# Kod Kalitesi & Güvenlik Denetimi — 2026-07-07

Bu rapor, `feature/dava-baglanti-gelistirmeleri` dalı üzerinde yapılan bağımsız iki denetimin (güvenlik + kod kalitesi) birleştirilmiş sonucudur. Mevcut `KALITE_DENETIM_RAPORU.md` (3 Temmuz 2026) ve `docs/guvenlik-incelemesi-2026-05-10.md` ile örtüşen bazı yapısal borçların hâlâ açık olduğunu teyit eder.

**Özet durum:** Kod kalitesi **6/10** — sağlam mimari/refactor, ancak test ve tip/lint ağı yok. Güvenlikte **1 kritik, 3 yüksek** öncelikli bulgu var; enjeksiyon ve dosya-yükleme savunması ise iyi durumda.

> **Güncelleme (2026-07-07, aynı gün):** İlk düzeltme turu uygulandı ve Docker ortamında
> doğrulandı. Çözülenler: **G4** (rate limit etkin), **G3** (zayıf anahtar fail-closed),
> **G6** (non-root konteyner), **K1, K2, K8** (kısmen), **K9, K17, K18** (kısmen).
> Her bulgunun altındaki **Durum** satırına bakın. Kalanlar için yol haritası:
> [`docs/gelistirme-plani-2026-07-07.md`](gelistirme-plani-2026-07-07.md).
>
> **Güncelleme 2 (2026-07-07, Faz 1):** Kalan güvenlik yüzeyi kapatıldı ve Docker'da
> doğrulandı. Çözülenler: **G2** (CORS beyaz listesi), **G5** (dev bypass'a DEV_MODE
> şartı + startup CRITICAL), **G6** (kaynak mount prod compose'dan kaldırıldı),
> **G8** (frontend access token). Açık kalan tek güvenlik bulgusu: **G1** (manuel
> sır rotasyonu, Faz 0) + **G10** (dev/prod env dosyası ayrımı — operatör hijyeni).

---

## 1. Güvenlik Bulguları

### KRİTİK

#### G1. Gerçek üretim sırları düz metin `.env` dosyasında
- **Dosya:** `.env:14,15,21,60,65,68,73`
- **Önem:** Kritik
- `.env` çalışma dizininde canlı görünen sırlar içeriyor: `GEMINI_API_KEY` (14), `SHAREPOINT_CLIENT_SECRET` + `UPLOAD_SHAREPOINT_CLIENT_SECRET` (15, 21), `POSTGRES_PASSWORD`/`DATABASE_URL` içinde DB şifresi (60, 65), zayıf `HUKDOK_EXPORT_API_KEY=dev-export-key-12345` ve `HUKUKBOT_INGEST_API_KEY=dev-ingest-key-67890` (68, 73).
- Dosya git'e **commit edilmemiş** (`.gitignore`'da doğru şekilde var — iyi), ancak diskte düz metin ve `docker-compose.yml`'de hem `env_file` hem `./backend:/app` mount ile konteynere aynen giriyor.
- **İstismar:** Dosya-okuma erişimi (log sızıntısı, hatalı yedek, ele geçirilmiş bağımlılık) SharePoint secret'ları + Gemini anahtarıyla kiracı arşivine ve LLM faturasına erişim verir.
- **Aksiyon:** Gemini anahtarı ve SharePoint secret'ları **derhal rotate edilmeli**; export/ingest anahtarları güçlü rastgele değerlerle değiştirilmeli; fallback yerine Vault'a taşınmalı.
- **Durum: 🔴 AÇIK — manuel aksiyon gerekiyor.** Kod tarafında destek geldi: zayıf export anahtarı prod'da artık reddediliyor (bkz. G3). Rotasyon adımları geliştirme planında (Faz 0).

### YÜKSEK

#### G2. CORS her origin'e açık + credentials açık
- **Dosya:** `backend/api.py:181-187`
- `allow_origin_regex=".*"` gelen her origin'i yansıtıyor; `allow_credentials=True` ile birlikte spec dışı. Auth Bearer header ile yapıldığından pratik etki sınırlı, yine de CSRF/veri-sızdırma yüzeyini gereksiz açıyor.
- **Aksiyon:** `allow_origins` bilinen origin'lere (localhost + prod domain) kısıtlanmalı.
- **Durum: ✅ ÇÖZÜLDÜ (2026-07-07, Faz 1).** `allow_origin_regex=".*"` kaldırıldı; origin beyaz listesi `ALLOWED_ORIGINS` env'inden okunuyor, tanımsızsa güvenli default (hukukoid.com + www + localhost:8080/8000/5173). Docker'da doğrulandı: `Origin: https://evil.example` ile yanıtta `access-control-allow-origin` yok (preflight 400), `https://hukukoid.com` ve `http://localhost:8080` doğru yansıtılıyor.

#### G3. `/export` uçları tenant izolasyonu olmadan herhangi bir belgeye erişiyor
- **Dosya:** `backend/routes/export.py:146-223` (`get_export_document`, `download_export_document`)
- Azure AD auth dışında, yalnızca `X-API-Key` ile korunuyor ve **hiç `tenant_id` filtresi yok** — `document_id` ile herhangi bir kiracının belgesi indirilebilir. Anahtar `.env`'de zayıf (`dev-export-key-12345`). Backend `hukuk_shared` external network'ünde olduğundan bu uçlar paylaşılan Docker ağından erişilebilir.
- **İstismar:** Ağdaki başka bir konteyner (veya anahtar sızarsa herhangi biri) ardışık id enumerasyonu ile tüm firmaların PDF'lerini çeker.
- **İyi taraf:** Karşılaştırma `hmac.compare_digest` (sabit-zamanlı) ve env yoksa fail-closed (503).
- **Aksiyon:** Güçlü prod anahtarı zorunlu kılınmalı; mümkünse tenant filtresi eklenmeli.
- **Durum: ✅ ÇÖZÜLDÜ (2026-07-07, kod tarafı).** `require_export_api_key` artık zayıf anahtarları (32 karakterden kısa veya `dev-` önekli) `DEV_MODE=true` değilse **503 ile reddediyor** (fail-closed) + CRITICAL log. Docker'da doğrulandı: dev modda dev anahtar 200/yanlış anahtar 401; `DEV_MODE=false` ile zayıf anahtar 503. Tenant filtresi **uygulanmadı**: iki tenant tasarım gereği ortak havuz kullanıyor (bkz. G7), filtreleyecek sınır yok. ⚠️ Prod deploy öncesi güçlü anahtar tanımlanmalı, yoksa export API 503 döner (G1/Faz 0).

#### G4. Rate limiting yapılandırılmış ama etkin değil
- **Dosya:** `backend/api.py:189-191`
- `Limiter(default_limits=["100/minute"])` tanımlı ve exception handler var, ancak `SlowAPIMiddleware` **eklenmemiş** ve hiçbir uçta `@limiter.limit` yok. slowapi'de `default_limits` yalnızca middleware kayıtlıysa uygulanır → fiilen hiç hız sınırı yok.
- **İstismar:** `/process` (dosya + Gemini) veya `/api/download/{file_id}` uçlarına sınırsız istek → LLM maliyet tırmanışı, DoS, id brute-force.
- **Aksiyon:** `app.add_middleware(SlowAPIMiddleware)` eklenmeli.
- **Durum: ✅ ÇÖZÜLDÜ (2026-07-07).** Middleware eklendi. Ek iyileştirme: limit anahtarı `X-Forwarded-For`'daki gerçek istemci IP'sini kullanıyor — aksi halde nginx arkasında tüm kullanıcılar tek 100/dk kovasını paylaşırdı (backend portu yalnızca localhost + iç Docker ağına açık olduğundan header spoof dış istemciler için mümkün değil). Docker'da doğrulandı: 110 istekte ilk 100 işlendi, kalan 10 → **429**.

### ORTA

#### G5. Auth "dev bypass" — imza doğrulaması olmadan token kabulü
- **Dosya:** `backend/auth_verifier.py:38-41`
- `ENV=development` + `ALLOW_DEV_TENANT=true` + `tid=dev-tenant` koşullarında imzasız JWT tam yetkiyle kabul ediliyor. `.env`'de bu değişkenler set edilmediğinden şu an pasif, ancak prod imajında bu kod yolunun bulunması riskli.
- **Aksiyon:** Prod build'lerden kaldırılması/derleme-zamanı çıkarılması.
- **Durum: ✅ ÇÖZÜLDÜ (2026-07-07, Faz 1).** Bypass'a üçüncü koşul eklendi: `DEV_MODE=true` da şart (prod'da false/tanımsız). Kombinasyon `DEV_MODE` olmadan görülürse `api.py` başlangıçta CRITICAL log basıyor; bypass kullanıldığında WARNING loglanıyor. Konteynerde doğrulandı: `ENV=development + ALLOW_DEV_TENANT=true` iken imzasız `dev-tenant` token `DEV_MODE=false` ile **reddedildi**, yalnızca üç koşul birlikteyken kabul edildi.

#### G6. Backend konteyneri root çalışıyor + prod'da kaynak & `.env` mount
- **Dosya:** `backend/Dockerfile` (USER yok), `docker-compose.yml:37-48`
- `USER` direktifi yok → root. Compose prod'da bile `./backend:/app` ve `env_file: .env` bağlıyor.
- **Aksiyon:** `USER appuser` eklenmeli; prod override'ında kaynak mount kaldırılmalı.
- **Durum: ✅ ÇÖZÜLDÜ (2026-07-07, kod tarafı).** Dockerfile'a `USER appuser` (uid 1000) eklendi; Docker'da doğrulandı (`whoami` → appuser, DB migration + cache yazımı sorunsuz). Faz 1'de `./backend:/app` kaynak mount'u base compose'dan **kaldırıldı** — prod imajdaki kodu çalıştırır; dev hot-reload mount'u gitignore'lu `docker-compose.override.yml`'e taşındı (şablon: `docker-compose.override.yml.example`). ⚠️ Kalan manuel adımlar (Faz 0): prod'da tek seferlik `docker compose exec -u root backend chown -R appuser /app/data`; prod sunucuda override dosyası bulunmadığı doğrulanmalı; backend değişiklikleri artık deploy'da `--build` gerektirir. `env_file: .env` bağlanmaya devam ediyor (prod sunucudaki `.env` zaten prod değerleri — bkz. G10).

#### G7. Kiracı izolasyonu fiilen paylaşımlı (tasarım gereği)
- **Dosya:** `backend/auth_helpers.py:14-16`, `backend/routes/cases.py:47-48`
- Tüm filtreler `tenant_id == X OR tenant_id IS NULL`; yeni davalar bilinçli olarak `tenant_id=NULL` (paylaşımlı) damgalanıyor. İki firma (Hanyaloğlu + LexisBio) birbirinin verisini görüyor.
- **Not:** Ortak çalışma nedeniyle kabul edilmiş tasarım; "izolasyon" beklentisi varsa net belgelenmeli. IDOR koruması (`get_tenant_owned_*`) tutarlı uygulanmış — iyi.

### DÜŞÜK

- **G8.** `frontend/src/lib/api.ts:32-33` — API'ye access token yerine `idToken` gönderiliyor; ideali API scope'lu access token. Token `sessionStorage`'da (`localStorage`'dan iyi). — **✅ ÇÖZÜLDÜ (2026-07-07, Faz 1):** `acquireTokenSilent` yanıtından artık `accessToken` gönderiliyor (scope zaten `api://<client_id>/access_as_user` idi); backend `aud` kontrolü iki formatı da kabul ediyor. Frontend imajı build edildi. ⚠️ Gerçek Azure AD login akışı tarayıcıdan bir kez elle doğrulanmalı.
- **G9.** `frontend/src/components/ui/chart.tsx:70` `dangerouslySetInnerHTML` — içerik tema renk değişkeni, kullanıcı girdisi değil; gerçek XSS riski görünmüyor. `YetkiBelgesiModal.tsx:201` `innerHTML`'i yalnızca okuyor.
- **G10.** `.env:32,34` — `DEV_MODE=true`, `SHAREPOINT_TEST_MODE=true` gerçek sırlarla aynı dosyada; prod/dev env dosyaları ayrılmalı.

### Güvenlikte İyi Yapılanlar
1. Sağlam JWT doğrulaması: RS256 imza (JWKS public key) + `aud` + `exp` + `ALLOWED_TENANTS` beyaz listesi (`auth_verifier.py`). İmzasız decode yalnızca `tid` okumak için.
2. Enjeksiyon yüzeyi kapalı: SQL tamamen ORM/parametreli; `subprocess` çağrıları liste-argümanlı, `shell=True` yok; dosya adları `basename` + `sanitize_filename` ile temizleniyor (path traversal kapalı).
3. Güçlü dosya-yükleme savunması: uzantı beyaz listesi (`.pdf/.udf`), magic-byte/MIME doğrulaması (UDF için ZIP/XML iç yapı kontrolü), 50MB boyut limiti, indirmede sahiplik kontrolü. nginx güvenlik başlıkları + export'ta sabit-zamanlı karşılaştırma.

---

## 2. Kod Kalitesi Değerlendirmesi — 6/10

Bilinçli ve özenle kurgulanmış, çalışan bir uygulama. Modülerleşme refactor'u büyük ölçüde gerçek: 1779 satırlık `admin_manager` 40 satırlık uyumluluk katmanına inmiş, mantık `managers/`, `services/`, `extractors/`, `pdf/`, `sharepoint/`, `routes/` katmanlarına dağılmış. Kaliteyi tavana çeken üç boşluk: **sıfır otomatik test**, **TS strict kapalı + backend lint yok**, **yaygın hata yutma + yapılandırılmamış loglama**.

### Mimari & Modülerlik
- **K1 (Orta):** `backend/related_cases_finder.py` (127 satır) **ölü kod** — hiçbir yerde import edilmiyor. Silinmeli. — **✅ ÇÖZÜLDÜ (2026-07-07):** dosya silindi (import edilmediği grep ile teyit edildi).
- **K2 (Orta):** `backend/routes/processing.py:61` — refactor sızıntısı: hâlâ `from managers.admin_manager import ...` (uyumluluk katmanı) kullanıyor; doğrudan `managers.reference_lists`'ten import edilmeli. — **✅ ÇÖZÜLDÜ (2026-07-07):** import doğrudan `managers.reference_lists`'e çevrildi.
- **K3 (Orta):** Kalan god-dosyalar: `analyzer.py` 1179, `routes/processing.py` 706, `routes/cases.py` 692, `email_sender.py` 627, `services/document_pipeline.py` 584. Router'lar hâlâ iş mantığı taşıyor.
- **K4 (Düşük):** `case_matcher.py` + `muvekkil_matcher_v2.py` yan yana ("v2" isimlendirme borcu); 21 kök-seviye modül paketlere taşınmamış (bilinçli ama görsel olarak yarım).

### Tekrar
- **K5 (Orta):** İsim normalize/benzerlik mantığı `lawyer_resolver.py`, `client_normalizer.py`, `muvekkil_matcher_v2.py`, `case_matcher.py`, `list_searcher.py`'de dağınık — tek `text_normalization` yardımcısına toplanmalı.
- **K6 (Orta):** Frontend'de 15+ component `lib/api.ts` yerine doğrudan `axios`/`fetch` çağırıyor — hata yönetimi/başlıklar tekrar yazılıyor.
- **K7 (Düşük):** `frontend/src/lib/nameSimilarity.ts` Levenshtein'i backend'de de var; `email_sender.py:244,371` aynı model-default satırını iki kez içeriyor.

### Hata Yönetimi
- **K8 (Yüksek):** ~20 `except … pass` + ~10 çıplak `except:`. Örnek: `managers/case_manager.py:338,343,348` (üç ardışık `except: pass`), `case_manager.py:472,480`, `extractors/date_extractor.py:173,284`, `managers/cache_manager.py:74`, `counter_manager.py:202`, `log_manager.py:61`. Toplam 173 `except Exception` — sahte-başarı riski. — **🟢 KISMEN ÇÖZÜLDÜ (2026-07-07):** backend'de **çıplak `except:` kalmadı** (grep ile teyit). Tarih parse'ları `case_manager._parse_date_field` yardımcısına toplandı (loglu); `date_extractor`, `cache_manager` loglu/daraltılmış except'e geçti; `os.getlogin()` fallback'leri `except OSError:` oldu. **Kalan:** geniş `except Exception` blokları tek tek gözden geçirilmeli — test ağı kuruldukça yürüyen sürekli görev (plan Faz 2.4; öncelik `services/document_pipeline.py`, `analyzer.py`, `sharepoint/`).
- **K9 (Yüksek):** Kod tabanında **`logging.basicConfig` yok** → kök logger WARNING, 106 `logging.info/warning` çağrısının INFO olanları sessizce düşüyor (başlangıç logları görünmez). — **✅ ÇÖZÜLDÜ (2026-07-07):** `api.py` başına timestamp'li `logging.basicConfig(level=INFO)` eklendi; Docker'da başlangıç loglarının aktığı doğrulandı.
- **K10 (Orta):** İki paralel loglama sistemi: `TechnicalLogger` (178) + standart `logging` (106) yan yana, tutarsız.
- **İyi:** `print()` neredeyse yok (yalnızca kritik import fallback).

### Test Durumu
- **K11 (Yüksek):** **Sıfır test.** `test_*.py`/`*.test.ts` yok, `conftest.py`/`pytest.ini` yok, CI (`.github/workflows`) yok, frontend'de vitest/jest yok. Tip güvenliği de kapalı olduğundan regresyon ağı tamamen elle. — **✅ ÇÖZÜLDÜ (2026-07-10, Faz 2):** Backend: pytest altyapısı (`backend/pyproject.toml` + `tests/conftest.py`, DB/ağ/keyring'e dokunmayan saf birim testleri) ile **164 test** — `file_utils` (doctype pad tuzağı dahil), `lawyer_resolver`, `case_matcher`, `date_extractor` (LLM mock), `routes/export` guard'ları. Frontend: vitest ile **43 test** — `nameSimilarity`, `validation` (TC checksum), `caseNumberUtils`, `api.ts` (token enjeksiyonu + 401 logout, MSAL mock). CI: `.github/workflows/ci.yml` (backend: pytest + Postgres service; frontend: tsc + vitest + build; eslint Faz 3'e kadar bilgilendirici). **Kalan manuel adım:** GitHub branch protection ile `backend`/`frontend` check'lerinin main'e merge şartı yapılması. Bonus: testler `sanitize_filename`'de uzantı yutan `[_.]{2,}` regresyonunu yakaladı, düzeltildi (`file_utils.py`).

### Tip Güvenliği & Lint
- **K12 (Yüksek):** Frontend TS **strict KAPALI** (`tsconfig.app.json: strict:false`, `strictNullChecks:false`, `noImplicitAny:false`) — pratikte "tipli JavaScript".
- **K13 (Orta):** ESLint `@typescript-eslint/no-unused-vars: "off"`; backend'de `mypy`/`ruff`/`pyproject.toml` config yok. Type hint kullanımı iyi ama zorlayıcı kapı yok.

### Frontend Kalitesi
- **K14 (Yüksek):** God component'ler: `NewCase.tsx` 1679, `Index.tsx` 1473 (47 hook), `AdminPage.tsx` 1319 (**67 useState/useEffect**), `CaseDetails.tsx` 857, `NewClient.tsx` 789, `QuickCaseModal.tsx` 748.
- **K15 (Orta):** `react-query` mevcut (iyi) ama dev sayfalarda onlarca lokal `useState` ile karışık.
- **K16 (Düşük):** `components/ui/` altında ~50 shadcn component; birçoğu (carousel, input-otp, menubar…) muhtemelen kullanılmıyor — scaffold artığı.

### Konfigürasyon & Bağımlılıklar
- **K17 (Orta):** Tutarsız model default'u: `extractors/date_extractor.py:20` → `gemini-1.5-flash`, `email_sender.py:244,371` → `gemini-2.5-flash-lite`. Aynı env değişkeninin farklı fallback'leri. — **✅ ÇÖZÜLDÜ (2026-07-07):** `date_extractor` fallback'i `gemini-2.5-flash-lite`'a eşitlendi.
- **K18 (Düşük):** Hardcoded limitler (`api.py:189,215` — 50MB, "100/minute") config'e alınabilir; `requirements.txt`'te `python-multipart` sürümsüz — pinlenmeli; `lovable-tagger` scaffold artığı. — **🟢 KISMEN ÇÖZÜLDÜ (2026-07-07):** `python-multipart==0.0.20` pinlendi. Kalan: limitlerin config'e alınması, `lovable-tagger` temizliği.

### Kod Kalitesinde İyi Yapılanlar
- Refactor gerçekten çalışmış: tanrı-modül temiz uyumluluk katmanına inmiş, mantık odaklı modüllere bölünmüş.
- `analyzer.py`'deki dev generator sözleşmesi korunarak adım fonksiyonlarına ayrıştırılmış.
- `vault` soyutlaması, `TechnicalLogger` maskeleme, `database.py`'de bildirimsel `_MIGRATIONS` + fail-fast.
- Backend bağımlılıkları neredeyse tümüyle pinlenmiş; frontend'de `react-query` + temiz `hooks/`–`lib/` ayrımı.

---

## 3. Öncelikli Aksiyonlar

> Güncel durum ve kalan işlerin ayrıntılı yol haritası: [`docs/gelistirme-plani-2026-07-07.md`](gelistirme-plani-2026-07-07.md)

**Hemen (güvenlik):**
1. 🔴 `.env`'deki sızan sırları rotate et (Gemini + SharePoint secret'ları), export/ingest anahtarlarını güçlendir. *(G1 — manuel, plan Faz 0)*
2. ~~`SlowAPIMiddleware` ekle (rate limit); `/export` için güçlü anahtar; CORS kısıtlaması; dev bypass sertleştirme; prod kaynak mount kaldırma; frontend access token~~ ✅ *(G2, G3, G4, G5, G6, G8 — 2026-07-07, Faz 1 tamam)*.

**Kısa vade (kalite):**
3. ~~`logging.basicConfig(level=INFO)` ekle; en tehlikeli `except: pass` bloklarını logla~~ ✅ *(K8 kısmen, K9 — 2026-07-07)*
4. ~~Test + CI altyapısı kur (pytest, vitest, GitHub Actions)~~ ✅ *(K11 — 2026-07-10, Faz 2 tamam; branch protection manuel adımı kaldı)*
5. 🔴 Tip/lint kapılarını kademeli aç (frontend `strict`/`strictNullChecks`, ESLint `no-unused-vars`; backend `ruff`+`mypy`). *(K12, K13 — plan Faz 3)*

**Orta vade:**
6. 🔴 God-dosyaları böl (`AdminPage.tsx`, `NewCase.tsx`, `Index.tsx`; `routes/processing.py`/`cases.py` iş mantığını `services/`'e taşı). *(K3, K14 — plan Faz 4)*
7. ~~Refactor kalıntılarını kapat: `related_cases_finder.py` sil, `processing.py:61` importunu düzelt.~~ ✅ *(K1, K2 — 2026-07-07)*
