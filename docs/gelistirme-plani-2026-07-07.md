# Geliştirme Planı — Denetim Kalanları (2026-07-07)

Bu plan, [`kod-kalitesi-guvenlik-denetimi-2026-07-07.md`](kod-kalitesi-guvenlik-denetimi-2026-07-07.md)
raporundaki **açık kalan** bulguların yol haritasıdır. Çözülenler (G3, G4, G6 kısmen,
K1, K2, K8 kısmen, K9, K17, K18 kısmen) raporun kendisinde işaretlidir.

Fazlar bağımsız oturumlar olarak tasarlandı; her faz kendi başına deploy edilebilir.
Sıralama risk önceliğine göredir: önce sır rotasyonu (deploy engeli), sonra kalan
güvenlik yüzeyi, sonra regresyon ağı (test/CI), en son yapısal refactor — çünkü
god-dosya bölme işine test ağı olmadan girmek risklidir.

---

## Faz 0 — Deploy Öncesi Manuel Adımlar (G1) 🔴 KRİTİK — 🟡 KISMEN TAMAMLANDI (2026-07-10)

**Kim:** İnsan operatör (kod değişikliği yok). **Süre:** ~1 saat + mesai dışı deploy penceresi.

Bu faz tamamlanmadan mevcut branch prod'a çıkarılmamalı — zayıf anahtar guard'ı
nedeniyle export API bilinçli olarak 503'e düşer.

> **Durum (2026-07-10):**
> - ✅ Adım 1-3: Export/ingest anahtarları güçlü değerlerle değiştirildi;
>   hukukbot tarafı (`~/hukukbot-ui/.env` → `HUKDOK_API_KEY` + `INGEST_API_KEY`)
>   aynı pencerede güncellendi, iki taraf da recreate edildi.
> - ✅ Adım 4: Gemini rotasyonu + **anahtar ayrımı**: artık üç ayrı anahtar var
>   (hukdok-prod, hukukbot-prod, hukdok-dev — eskiden tek ortak anahtardı).
>   Eski ortak anahtar AI Studio'dan silindi.
> - ⬜ Adım 5: SharePoint secret'ları **bekliyor** (bilinçli erteleme). İki iş:
>   (a) aktif `SHAREPOINT_CLIENT_SECRET` rotasyonu; (b) kodun artık KULLANMADIĞI
>   `UPLOAD_SHAREPOINT_*` uygulamasının secret'ını Azure'da iptal et (rotate
>   değil — app başka yerde kullanılmıyorsa kaydı komple sil) ve 4 `UPLOAD_*`
>   satırını prod + lokal `.env`'lerden temizle. Bu kapanmadan G1 kapanmış
>   sayılmaz — ifşa edilmiş secret hâlâ arşive erişebilir.
> - ⬜ Adım 6-7: Volume chown non-root imajın ilk deploy'unda; reconcile ack
>   doğrulaması da o pencerede.
> - 📝 Yan bulgu: sunucu home dizininde düz metin DB yedekleri birikmiş
>   (`prod_backup.sql`, `hukudok_canli.dump` vb.) — müvekkil verisi içeriyor;
>   temizlenmeli/şifreli arşive taşınmalı.

1. **Yeni export/ingest anahtarları üret:**
   ```bash
   openssl rand -hex 32   # HUKDOK_EXPORT_API_KEY
   openssl rand -hex 32   # HUKUKBOT_INGEST_API_KEY
   ```
2. **Prod `.env`'i güncelle** (sunucuda; `.env` değişikliği `restart` ile gelmez,
   `docker compose up -d` ile recreate gerekir).
3. **Hukukbot tarafını koordine et:** aynı export anahtarı hukukbot'un config'ine
   girilmeli; iki taraf aynı pencerede güncellenmeli yoksa aktarım durur.
4. **Gemini API anahtarını rotate et** (Google AI Studio → yeni anahtar → prod `.env`
   → eskisini iptal et).
5. **SharePoint client secret'larını rotate et** (Azure Portal → App registrations →
   ilgili iki uygulama → yeni secret → prod `.env` → eskilerini sil).
6. **Volume sahipliği (G6 kalıntısı):** non-root imajın ilk deploy'unda bir kez:
   ```bash
   docker compose exec -u root backend chown -R appuser /app/data
   ```
7. **Doğrulama:** `docker logs hukdok_backend` → CRITICAL "anahtar zayıf" logu
   OLMAMALI; hukukbot reconcile akışı bir tur çalıştırılıp ack görülmeli.

**Kabul kriteri:** Prod'da hiçbir `dev-*` anahtar yok, export API 200 dönüyor,
eski Gemini/SharePoint anahtarları iptal edilmiş.

---

## Faz 1 — Kalan Güvenlik Yüzeyi (G2, G5, G6-kalan, G8, G10) ✅ TAMAMLANDI (2026-07-07)

**Süre:** ~yarım gün kod + 1 deploy.

> **Durum:** Kod tarafı tamamlandı ve lokal Docker'da doğrulandı (CORS curl testleri,
> konteyner içinde bypass testi, frontend imaj build'i). Deploy notları:
> 1. Prod deploy'da backend değişiklikleri artık `--build` gerektirir (kaynak mount yok).
> 2. Prod sunucuda `docker-compose.override.yml` **bulunmamalı** (varsa kaynak mount geri gelir).
> 3. Frontend access-token geçişi tarayıcıdan gerçek Azure AD login ile bir kez doğrulanmalı.
> 4. `.env.prod` ayrımı yerine mevcut yaklaşım korundu: prod sunucudaki `.env` zaten
>    yalnızca prod değerleri içerir; `.env.example`'a DEV_MODE uyarısı eklendi (G10 operatör hijyeni).

### 1.1 CORS kısıtlaması (G2) ✅
- `backend/api.py`: `allow_origin_regex=".*"` yerine env'den okunan liste:
  ```
  ALLOWED_ORIGINS=https://hukukoid.com,http://localhost:8080,http://localhost:5173
  ```
- Boş/tanımsızsa güvenli default (yalnızca prod domain + localhost) kullanılmalı.
- **Test:** tarayıcıdan normal akış + `curl -H "Origin: https://evil.example"` ile
  yanıtta `Access-Control-Allow-Origin` dönmediğini doğrula.
- **Risk:** yanlış origin listesi frontend'i kırar → önce lokalde, sonra prod'da
  mesai dışı doğrula.

### 1.2 Dev bypass'ın prod'dan çıkarılması (G5) ✅ — "en az maliyetli çözüm" uygulandı
- `auth_verifier.py:38-41`'deki imzasız kabul yolu ayrı modüle (`auth_dev.py`)
  taşınsın; prod imajında bulunmasın **veya** en az maliyetli çözüm: bypass'a
  `DEV_MODE=true` üçüncü koşulu eklenip başlangıçta `ENV=development` +
  `ALLOW_DEV_TENANT=true` kombinasyonu prod'da tespit edilirse CRITICAL log +
  bypass devre dışı bırakılsın.
- **Kabul kriteri:** prod ortam değişkenleriyle imzasız token hiçbir koşulda
  kabul edilmiyor.

### 1.3 Prod compose sertleştirme (G6 kalan, G10) ✅ — ayrı prod dosyası yerine base sertleştirildi
- `docker-compose.prod.yml` override dosyası oluştur:
  - `./backend:/app` kaynak mount'u **yok** (imajdaki kod çalışır),
  - yalnızca `backend-data` volume,
  - prod'a özel `.env.prod` (`DEV_MODE`/`SHAREPOINT_TEST_MODE` içermez).
- Dev tarafı mevcut `docker-compose.yml` + `docker-compose.override.yml`
  (hot-reload mount burada kalır).
- **Not:** prod deploy komutu değişir → `deploy_method` hafıza notu ve varsa
  deploy dokümanı güncellenmeli.

### 1.4 Frontend token türü (G8 — düşük) ✅
- MSAL'dan API scope'lu **access token** istenip (`api://<client_id>/.default`)
  `lib/api.ts`'te `idToken` yerine o gönderilmeli. Backend `aud` kontrolü zaten
  iki formatı da kabul ediyor; yalnızca frontend değişikliği.

**Faz kabul kriteri:** prod'da kaynak mount yok, CORS beyaz listeli, dev bypass
prod'da imkânsız, login + belge işleme akışı uçtan uca çalışıyor.

---

## Faz 2 — Regresyon Ağı: Test + CI (K11, K8-kalan) ✅ TAMAMLANDI (2026-07-10)

**Süre:** ~2-3 gün. Yapısal refactor'ün (Faz 4) ön koşulu.

> **Durum:** 2.1–2.3 tamamlandı; 2.4 tanımı gereği sürekli görev, açık.
> - **Backend:** 164 test yeşil (`docker compose exec backend pytest`).
>   Altyapı: `backend/pyproject.toml` + `tests/conftest.py` — testler DB'ye/ağa/
>   keyring'e dokunmaz (vault stub, TechnicalLogger cloud-sync no-op, dummy
>   `DATABASE_URL`). Test DB'si/testcontainers ihtiyacı doğduğunda CI'daki
>   Postgres service hazır.
> - **Frontend:** 43 test yeşil (`npm test`). `vitest.config.ts` ayrı (vite
>   config'i lovable-tagger yüklüyor); `.npmrc` ile `legacy-peer-deps` kalıcı.
>   `@testing-library/react` ilk component testiyle birlikte eklenecek.
> - **CI:** `.github/workflows/ci.yml` — backend (py3.10, pytest, Postgres
>   service) + frontend (node20, tsc, vitest, build). ESLint mevcut 18 hata
>   nedeniyle `continue-on-error` (Faz 3.2'de zorunlu olacak).
> - **Bonus bulgu:** testler `sanitize_filename`'de `[_.]{2,}` regex'inin
>   uzantı yuttuğunu yakaladı ("KARARI_.pdf" → "KARARI_pdf") — düzeltildi,
>   regresyon testi eklendi.
> - **Kalan manuel adım (operatör):** GitHub → Settings → Branches → `main`
>   → branch protection → "Require status checks": `backend`, `frontend`.
>   Bu yapılmadan "PR'lar test olmadan merge edilemiyor" kriteri kapanmaz.

### 2.1 Backend pytest altyapısı ✅
- `backend/pyproject.toml` + `pytest` + `conftest.py` (test DB olarak
  `postgresql://…/hukudok_test` veya testcontainers).
- İlk hedef saf/pure modüller (DB ve Gemini mock'u gerektirmez):
  1. `file_utils._normalize_doctype_code` — pad'li/kısa kod karşılaştırmaları
     (bilinen tuzak: `ARA-KRR_______` vs `ARA-KRR`),
  2. `lawyer_resolver` — isim normalize/alias çözümleme,
  3. `case_matcher` / `muvekkil_matcher_v2` — eşleştirme skorları,
  4. `extractors/date_extractor` — tarih adayı skorlama (LLM çağrısı mock),
  5. `routes/export.py` — `_key_is_weak`, `_doc_passes_filters` (bu turda
     yazılan guard'ların kilitlenmesi).
- Hedef: ilk PR'da ~40-60 test, kritik yolların %70+'ı.

### 2.2 Frontend vitest ✅
- `vitest` + `@testing-library/react`; ilk hedefler: `lib/nameSimilarity.ts`,
  `lib/api.ts` interceptor'ları, form doğrulama yardımcıları.

### 2.3 GitHub Actions CI ✅ — branch protection manuel adımı açık
- `.github/workflows/ci.yml`: iki job —
  `backend` (ruff + pytest, Postgres service container),
  `frontend` (eslint + tsc --noEmit + vitest + build).
- PR'larda zorunlu; `main`'e merge kapısı.

### 2.4 `except Exception` taraması (K8 kalan) 🔄 SÜREKLİ GÖREV
- Test ağı oluştukça 173 `except Exception` bloğu dosya dosya gözden geçirilir:
  ya daraltılır, ya `logging.exception` eklenir, ya da bilinçli yutma ise
  gerekçe yorumu yazılır. Öncelik: `services/document_pipeline.py`,
  `analyzer.py`, `sharepoint/` (sahte-başarı riski en yüksek yerler).

**Faz kabul kriteri:** CI yeşil, PR'lar test olmadan merge edilemiyor.

---

## Faz 3 — Tip/Lint Kapıları (K12, K13, K10) ✅ TAMAMLANDI (2026-07-10)

**Süre:** ~2 gün, kademeli. Faz 2'deki CI'a eklenir.

> **Durum:** Üç alt başlık da tamamlandı; lokalde ruff + mypy + pytest (282) ve
> tsc strict + eslint + vitest (58) + build yeşil. CI'a `ruff check` + `mypy`
> adımları eklendi, ESLint'in `continue-on-error`'ı kaldırıldı (artık zorunlu).
> Uygulama notları:
> - **Ruff:** E, F, B seçili; `E501` (satır boyu) kapsam dışı bırakıldı.
>   `B008` için FastAPI `Depends/Query/...` deyimi `extend-immutable-calls` ile
>   muaf. `E402` yalnızca bilinçli "önce env yükle sonra import" yapan dosyalarda
>   (`analyzer.py`, `api.py`, `vault.py`, `scripts/*` vb.) per-file-ignore.
>   301 bulgu sıfırlandı; E722 (bare except) hiç yoktu.
> - **Mypy:** `managers/` + `routes/` taranıyor; `implicit_optional=true`
>   (mevcut `param: str = None` stili) ve `disable_error_code=["assignment"]`
>   (eski stil SQLAlchemy `Column()` false-positive'i — modeller `Mapped[]`'e
>   geçince açılacak, Faz 4). Kalan 29 gerçek hata elle düzeltildi.
> - **Yan kazanım:** `validate_file_size` fonksiyon-attribute limitleri
>   `file_utils.MAX_UPLOAD_MB/BYTES` modül sabitlerine çevrildi (4.4'ün env
>   işine zemin). `dependencies.py`'de `HTTPBearer` modül singleton'ı oldu.
> - **Frontend:** `noImplicitAny` (23 hata) → `strictNullChecks` (23) →
>   `strict: true` (2) sırasıyla açıldı; ESLint 18 hata temizlendi;
>   `no-unused-vars` `_`-öneki muafiyetiyle "error" yapıldı (38 ihlal temizlendi,
>   bu sırada ölü kod `parseToHtmlDate` ve `handleSearch` silindi).
>   `ClientData` tipi backend'in döndürdüğü alanlarla tamamlandı;
>   `ClientList.Client` artık `ClientData`'dan extend ediyor (tekilleşme).
> - Kalan 25 ESLint uyarısı (exhaustive-deps, react-refresh) bilinçli olarak
>   warning seviyesinde — Faz 4.3 component bölmelerinde doğal olarak azalacak.

### 3.1 Backend: ruff + mypy ✅
- `pyproject.toml`'a `ruff` (E, F, B, bare-except yasağı `E722`) — mevcut kod
  temiz başlasın diye ilk geçişte `--fix` + kalanlara satır bazlı `noqa`.
- `mypy` kademeli: önce `managers/`, `routes/` (`ignore_missing_imports=true`,
  `check_untyped_defs=true`), tam `strict` hedeflenmez.

### 3.2 Frontend: strict'e kademeli geçiş ✅
- 1. adım: `noImplicitAny: true` → hataları düzelt (tahmini en büyük yığın).
- 2. adım: `strictNullChecks: true` → null guard'ları ekle.
- 3. adım: `strict: true` + ESLint `no-unused-vars` açılır.
- Her adım ayrı PR; god-component'lere dokunmadan yalnızca tip düzeltmesi.

### 3.3 Loglama tekleştirme (K10) ✅
- Karar: `TechnicalLogger` API yüzeyi korunur ama içi standart `logging`'e
  delege eder (handler/format tek yerden). 106 standart çağrı olduğu gibi kalır.
- Uygulandı: `TechnicalLogger.log` artık `logging.getLogger("TechnicalLogger")`
  üzerinden de yazar; RAM buffer + SharePoint sync davranışı değişmedi.

**Faz kabul kriteri:** CI'da ruff + mypy + tsc strict + eslint zorunlu ve yeşil. ✅

---

## Faz 4 — Yapısal Refactor (K3, K14, K5, K6, K7, K15)

**Süre:** ~1 hafta, parça parça. Faz 2 (test ağı) olmadan başlanmamalı.

### 4.1 Backend god-dosyalar (K3)
- `routes/processing.py` (706) ve `routes/cases.py` (692): route'lar yalnızca
  parse + yetki + `services/` çağrısı yapacak şekilde iş mantığı
  `services/case_service.py` / `services/processing_service.py`'ye taşınır.
- `analyzer.py` (1179): generator sözleşmesi korunur; adım fonksiyonları zaten
  ayrık — yalnızca prompt şablonları `prompts/` modülüne çıkarılır.
- `email_sender.py` (627): şablon üretimi / SMTP gönderimi / Gemini metin
  üretimi üç modüle ayrılır (K7'deki mükerrer model-default satırı da burada ölür).

### 4.2 İsim normalize tekleştirme (K5, K7)
- `backend/text_normalization.py`: `_norm_name`, Levenshtein, Türkçe karakter
  katlama tek modülde; `lawyer_resolver`, `client_normalizer`,
  `muvekkil_matcher_v2`, `case_matcher`, `list_searcher` buradan import eder.
- Frontend `nameSimilarity.ts` kalır (ayrı runtime) ama algoritma davranışı
  backend testleriyle aynı fixture'lar üzerinden hizalanır.

### 4.3 Frontend god-component'ler (K14, K15, K6)
- Sıra (kazanç/risk oranına göre): `AdminPage.tsx` (1319, 67 hook) →
  `NewCase.tsx` (1679) → `Index.tsx` (1473) → `QuickCaseModal.tsx` (748).
- Kalıp: her sayfa `hooks/useXxx.ts` (react-query + mutasyonlar) + sunum
  bileşenlerine bölünür; lokal `useState` yığınları query cache'ine taşınır (K15).
- Aynı geçişte doğrudan `axios/fetch` çağrıları `lib/api.ts`'e toplanır (K6).
- Hatırlatma: redesign sayfaları tam genişlik kuralına uyar (max-w cap yok).

### 4.4 Küçük temizlikler (K4, K16, K18-kalan)
- `muvekkil_matcher_v2.py` → `muvekkil_matcher.py` rename (v1 yoksa).
- Kullanılmayan shadcn bileşenleri tespit edilip silinir (`npx knip` veya
  import grep'i), `lovable-tagger` kaldırılır.
- 50MB / "100/minute" limitleri env'e alınır (`MAX_UPLOAD_MB`, `RATE_LIMIT`).

**Faz kabul kriteri:** hiçbir dosya ~500 satır üstünde iş mantığı taşımıyor,
testler yeşil, davranış değişikliği yok.

---

## Kapsam Dışı / Kabul Edilenler

- **G7 (ortak tenant havuzu):** Hanyaloğlu Acar + LexisBio bilinçli olarak tüm
  kayıtları `tenant_id=NULL` ile paylaşıyor — bulgu değil, tasarım. Bu plan
  kapsamında yalnızca belgelenmiş sayılır; izolasyon istenirse ayrı proje.
- **G9 (`dangerouslySetInnerHTML`):** içerik kullanıcı girdisi değil, tema
  değişkeni — aksiyon yok, izlemede.

## Önerilen Oturum Sırası

| # | Faz | Ön koşul | Tahmini süre |
|---|-----|----------|--------------|
| 1 | Faz 0 (manuel rotasyon) | — | 1 saat + deploy penceresi |
| 2 | Faz 1 (güvenlik kalanları) ✅ 2026-07-07 | Faz 0 | yarım gün |
| 3 | Faz 2 (test + CI) ✅ 2026-07-10 | — (Faz 1'e paralel olabilir) | 2-3 gün |
| 4 | Faz 3 (tip/lint) ✅ 2026-07-10 | Faz 2 (CI) | 2 gün |
| 5 | Faz 4 (refactor) | Faz 2 (test ağı) | ~1 hafta, parça parça |
