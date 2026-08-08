# Güvenilirlik, Bakım ve İzlenebilirlik Sertleştirme Planı — 2026-08-04

Üç paralel denetim taramasının (dış bağımlılıklar, işlem hattı, frontend + altyapı) birleştirilmiş sonucu ve fazlı uygulama planı.

**Öncelik sırası (kullanıcı kararı):** Güvenilirlik > Bakım kolaylığı + AI-dostu repo + Monitoring > Ölçeklenebilirlik (şimdilik ertelendi, ~10 kullanıcı).

**Kısıt:** Uygulama aktif kullanımda. Her faz kendi başına deploy edilebilir, küçük ve geri alınabilir olmalı. Deploy'lar mesai dışı yapılır.

**Uygulama takibi:** Oturum paketleri ve güncel durum [guvenilirlik-sertlestirme-uygulama-takibi.md](guvenilirlik-sertlestirme-uygulama-takibi.md) dosyasında — çalışmaya oradan başla, bu dosyadan yalnız ilgili faz bölümünü oku.

---

## Özet teşhis

Geçmiş arızaların (OOM, 504, mükerrer kayıt, sessiz e-posta arızası) kök nedenleri taramada tek tek doğrulandı. Sistemin üç yapısal zafiyeti var:

1. **Hata tek noktadan tüm sistemi durduruyor.** Tek uvicorn worker + `/confirm` içinde event loop'u 240 sn'ye kadar bloke eden senkron Ghostscript çağrısı → bir kullanıcının büyük PDF'i herkesin isteğini durduruyor (504 kümelerinin asıl mekanizması bu).
2. **Hatalar sessizce yutuluyor.** SharePoint arşiv yüklemeleri fire-and-forget (başarısızlık ne kullanıcıya ne DB'ye yansıyor), e-posta kill-switch'i ölü kod (`cfg["enabled"]` KeyError yutularak), frontend hata durumunda boş liste/varsayılan veri gösteriyor. Kullanıcı "sistem çalışıyor" sanırken veri kayboluyor.
3. **Kritik yapılandırma repo dışında.** Bellek limitleri, host nginx config'i (300 sn timeout fix'i dahil), watchdog scriptleri, log rotasyonu — hepsi sadece sunucuda. VM yeniden kurulumu, OOM öncesi konfigürasyonu aynen geri getirir.

---

## FAZ 0 — Acil tekil düzeltmeler (en yüksek getiri / en düşük risk)

Her biri küçük, bağımsız test edilebilir, tek deploy'da çıkabilir.

| # | Düzeltme | Konum | Neden |
|---|---|---|---|
| 0.1 | `/confirm` içindeki `convert_pdfa_and_queue_uploads` çağrısını `run_in_threadpool`'a al | `routes/processing.py:588` | Event loop 240 sn bloke oluyor → tüm kullanıcılar duruyor. Tek satır, en büyük tekil kazanç. `case_intake.py:845-871` zaten doğru deseni kullanıyor. |
| 0.2 | DB session sızıntılarını kapat (`finally: db.close()`) | `document_pipeline.py:45,106-108`, `:581,615`; `routes/processing.py:116,149-151` | Hata yolunda session kapanmıyor → pool (10+20) tükenince TÜM endpoint'ler asılıp 500 veriyor. "Sistem hata veriyor" şikayetinin en olası nedeni. |
| 0.3 | `json.JSONDecodeError`'ı `ValueError`'dan önce ayrı yakala | `analyzer.py:1277` | Bozuk LLM JSON'u kullanıcıya "Güvenlik Filtresi engelledi" olarak yansıyor (yanlış teşhis). Confirm-500 arızasındaki UnicodeDecodeError sınıfıyla aynı tuzak. |
| 0.4 | Gemini client'a timeout ver + `wait_for_files_active`'e deadline ekle | `gemini_client.py:37` (`http_options=HttpOptions(timeout=120_000)`), `analyzer.py:239-254` (max 120 sn) | Hiçbir Gemini çağrısında timeout yok; PROCESSING'de takılı dosya isteği sonsuza dek asıyor. |
| 0.5 | E-posta kill-switch'ini onar: `_get_email_config`'a `enabled`/`test_mode` ekle | `email_sender.py:33-43`; `document_pipeline.py:434-439`; `activity_manager.py:208` | `cfg["enabled"]` KeyError atıp yutuluyor → EMAIL_ENABLED bayrağı hiç çalışmıyor, günlük özet maili HİÇ gönderilmiyor. |
| 0.6 | E-posta eki sınırını 3 MB'a indir, aşınca SharePoint linki ile gönder | `email_sender.py:127-128` | 50 MB izin veriliyor ama Graph `/sendMail` ~4 MB'ta kesiyor → garantili 413. "Kısıtlamalar hata veriyor" şikayetinin somut örneği. |
| 0.7 | `MAX_PDF_PAGES` `ValueError`'ını genel handler'dan önce yeniden fırlat | `pdf/pdf_utils.py:99-101` | 500 sayfa limiti ölü kod: kendi hatasını kendisi yutup bozuk/şifreli PDF'i OCR yoluna sokuyor. |
| 0.8 | `counter_task`'ı stream'in `finally`'sinde iptal et | `routes/processing.py:393,418-425` | Analiz hata verirse task hiç await edilmiyor → sarkan task sızıntısı. |
| 0.9 | `PROCESS_CACHE`'e `owner` alanı ekle ve pop/touch'ta doğrula | `routes/processing.py:411-415`; `document_pipeline.py:154-166` | Kimlik doğrulamalı herhangi bir kullanıcı başkasının `process_id`'sini tüketebiliyor. `DOWNLOAD_CACHE` zaten owner kontrolü yapıyor — aynı desen. |
| 0.10 | `extra_attachment_files`'a uzantı + boyut + magic-byte doğrulaması | `routes/processing.py:531`; `document_pipeline.py:334-349` | Ek dosyalar tüm doğrulamayı atlıyor ve dışarı e-postalanıyor. |

**Test:** Backend pytest konteynerde (host py3.13 uyumsuz). 0.1–0.2 için eşzamanlı istek dumanı testi.

---

## FAZ 1 — Altyapı ve deploy sertleştirme (konfigürasyonu repo'ya al)

Amaç: VM kaybolsa bile bilinen-iyi durum tek `git clone` + `deploy.sh` ile geri gelsin.

1. **`docker-compose.yml`'e taşı:** `mem_limit: 2g` + `memswap_limit: 2g` (backend), `512m` (postgres), `128m` (frontend); her servise `logging: {driver: json-file, options: {max-size: 50m, max-file: "3"}}`. Şu an bunlar yalnızca sunucudaki gitignore'lu override'da / daemon.json'da — kaybolursa OOM öncesi konfig geri gelir.
2. **Healthcheck'ler:** backend'e `GET /healthz` healthcheck (start_period 60s), frontend `depends_on: backend: condition: service_healthy`.
3. **`infra/` dizini oluştur, repo'ya al:** host nginx config'i (300 sn timeout fix'i dahil — şu an SADECE sunucuda!), `net-watchdog.sh` + systemd unit'leri, `mem-watch`, daemon.json, kurulum scripti. `deploy.sh` timer'ın `active` olduğunu doğrulasın.
4. **`deploy.sh` yeniden yaz:**
   - `down` YOK → önce `docker compose build`, sonra `up -d` (kesinti dakikalardan saniyelere iner)
   - `git pull --ff-only || exit 1` (şu an pull hatası yutulup ESKİ kod deploy ediliyor)
   - İmajları `hukudok-backend:$(git rev-parse --short HEAD)` olarak etiketle, son 3'ü tut, `rollback.sh` ekle (şu an `image prune -f` geri dönüş hedefini siliyor)
   - Deploy öncesi otomatik `pg_dump` (migration'lar otomatik koşuyor, kötü migration şu an geri alınamaz)
   - Gerçek sağlık kapısı: 120 sn'ye kadar `curl -fsS /healthz` poll, başarısızsa non-zero exit (şu an `sleep 5 && docker ps`)
   - `hukuk_shared` network'ünü ve `.env` zorunlu anahtarlarını kontrol et
5. **Gece yedeği:** `pg_dump` → GCS bucket (lifecycle retention). Şu an SIFIR otomatik yedek var; tek VM, tek disk.
6. **Uvicorn:** `--workers 2` (bellek limiti I1 sonrası uygun; migration'ları entrypoint'ten tek seferlik ayrı adıma taşı — iki worker'da DDL yarışı olur). `api.py:331-332`'deki import-time `check_and_migrate_tables()` çağrısını kaldır (zaten lifespan'da koşuyor).

---

## FAZ 2 — Monitoring ve alarm (aniden fark et, müdahale et)

Kullanıcının açık talebi. Şu an tek izleme: `/`'a bakan uptime check — SPA `try_files` yüzünden backend ölüyken bile 200 dönüyor.

1. **Derin `/healthz` endpoint'i:** `SELECT 1` + Graph token yaşı + son Gemini hata sayısı (cache'li, <1 sn). Container healthcheck, deploy kapısı ve uptime check hep bunu kullansın.
2. **Container nginx'e `location = /healthz`** ekle; GCP uptime check'i buna çevir.
3. **Log tabanlı alarm (GCP Ops Agent):**
   - Backend `ERROR`/`CRITICAL` satır oranı eşiği → e-posta
   - Container `OOMKilled` / restart olayları → e-posta
   - `net-watchdog` `KRITIK` satırları → e-posta
4. **Yapısal loglama:** 11 modüldeki dağınık `logging.basicConfig`'i tek `dictConfig`'e topla (sonraki çağrılar zaten no-op — çoğu modülün format ayarı hiç uygulanmıyor), JSON formatter + request-id middleware. Bir kullanıcının `/confirm` yolculuğu uçtan uca izlenebilsin.
5. **Frontend hata sinyali:** `window.addEventListener('unhandledrejection'/'error')` → `/api/client-error` beacon endpoint'i. Şu an "ekran boş" şikayeti sunucudan görünmez.
6. **Arşiv durumu görünürlüğü:** `CaseDocument`'a `upload_status` kolonu (pending/uploaded/failed + attempts) — hem retry kuyruğunun temeli (Faz 3) hem belge kartında kullanıcıya "arşivleme başarısız" göstergesi.

TechnicalLogger zaten var (SharePoint'e ERROR senkronu) ama sadece kayıt tutuyor, alarm üretmiyor; bu faz onu tamamlıyor.

---

## FAZ 3 — Fallback ve dayanıklılık (dış bağımlılıklar)

1. **SharePoint yükleme retry kuyruğu:** Fire-and-forget `BackgroundTasks` yerine `ExportOutbox` desenini (zaten repoda var: `services/export_publisher.py`) belge yüklemelerine uygula: DB'ye job satırı yaz → arka plan işleyici + startup reconcile. Süreç ölse bile yükleme kaybolmaz; başarısızlık `upload_status=failed` olarak görünür ve yeniden denenir. **En büyük sessiz veri kaybı yolu bu.**
2. **Graph çağrılarına retry:** Paylaşılan `requests.Session` + `urllib3.Retry(total=3, backoff_factor=1, status_forcelist=[429,500,502,503,504], respect_retry_after_header=True)`. Şu an tek 429 tüm belgeyi kalıcı düşürüyor. 401'de bir kez token yenile + tekrar dene. Chunk yüklemede `nextExpectedRanges` ile devam (45 MB dosya tek blip'te sıfırlanmasın).
3. **Gemini retry sınıflandırıcısını düzelt:** String eşleme yerine `APIError.code in {429,500,502,503,504}` + `httpx.TransportError`. `finish_reason` oku: `MAX_TOKENS` kesilmesi "güvenlik filtresi" olarak raporlanmasın. Toplam deadline bütçesi (nginx 300 sn'yi aşmasın). Basit devre kesici: art arda N 429/503 → 60 sn açık.
4. **Ofis numarası atomik rezervasyonu:** `get_next_counter` şu an sadece okuyor, artırma `/confirm`'de arka planda → iki eşzamanlı kullanıcı AYNI numarayı alıyor. ETag döngüsünü tahsis anında "oku+artır+döndür" tek işlemine çevir; çakışma retry'ına backoff ekle.
5. **`/confirm` idempotency:** Client tarafı `Idempotency-Key` (veya `file_hash`) → mevcut kayıt varsa onu döndür. 504 sonrası retry şu an mükerrer belge + mükerrer e-posta üretiyor (nginx.conf'ta "mukerrer kayit kaynagi" diye belgelenmiş). `/commit` 409'unda mevcut davayı bulup idempotent sonuç döndür — şu anki "sıra numarasını artırıp tekrar deneyin" mesajı mükerrer dava yaratmaya davetiye.
6. **DB dayanıklılığı:** `pool_timeout=10`, `connect_timeout=5`, `statement_timeout=30s`; `get_db`'ye rollback; pipeline commit handler'larına `db.rollback()`.
7. **PROCESS_CACHE kalıcılığı:** Cache'lenen PDF'leri `backend-data` volume'üne yaz, boot'ta TTL indeksini yeniden kur. Şu an her deploy/restart tüm açık sihirbaz oturumlarını "expired" yapıyor (OOM geçmişiyle birleşince en olası kullanıcı veri kaybı yolu).
8. **Dönüşüm hatasında "orijinali sakla, sonra çevir" (Katman 2 — 2026-08-05 UDF arızası):** PDF dönüşümü her yol denendikten sonra da başarısızsa `/confirm` 500 atmasın: (a) orijinal dosya **kendi uzantısıyla** (ör. `.udf`) işlenmiş arşive yüklensin — ".pdf adıyla sızma" kuralı korunur, belge kaybolmaz; (b) `CaseDocument` kaydı `conversion_pending` statüsüyle oluşsun, kullanıcıya "belge kaydedildi, PDF dönüşümü sonra tamamlanacak" uyarısı dönsün, akış devam etsin; (c) gece koşan retry job bekleyenleri yeniden denesin, başaramadıklarını TechnicalLogger ERROR'a düşsün; (d) hukukbot export'u `conversion_pending` kayıtları ingest'e ALMASIN (140+ belgelik failed birikimi vakasının tekrarını önlemek için şart). Not: Katman 1 (converter içi tablo-düzleştirme fallback'i + gerçek nedene göre hata mesajları) 2026-08-05'te kodlandı; bu madde onun üstündeki yapısal katman.

---

## FAZ 4 — Frontend dayanıklılığı

1. **`apiClient.fetch`'e varsayılan timeout** (`AbortSignal.timeout`: okuma 30 sn, upload/analiz 300 sn) + idempotent GET'lere 2× backoff'lu retry. POST `/confirm`/`commit` ASLA otomatik retry edilmez.
2. **Hata ≠ boş veri:** `useCases`/`useClients` hook'ları hata durumunda boş liste döndürmesin; "Sunucuya ulaşılamadı — tekrar dene" banner'ı. Şu an kesinti sırasında kullanıcı "dosya bulunamadı" görüyor (veri kaybı sanıyor). **Özellikle:** `getClientCaseSequence` hata durumunda `1` döndürüyor → sessizce yanlış ofis numarası; hata fırlatıp kaydetmeyi bloke etmeli.
3. **`/confirm` yanıt işleme:** `response.ok`'u JSON parse'tan ÖNCE kontrol et (504 HTML gövdesi şu an ham `SyntaxError` toast'ı üretiyor); 502/503/504'te "işlem sunucuda sürüyor olabilir, tekrar YÜKLEMEYİN" mesajı + Faz 3.5 idempotency anahtarı.
4. **ErrorBoundary:** `<AppContent/>` etrafına, yeniden yükleme butonuyla. Şu an herhangi bir render hatası tüm SPA'yı boş ekrana çeviriyor.
5. **Taslak kalıcılığı:** `NewCase.tsx` (1700 satırlık form!) ve `Index.tsx` analiz akışına `intakeDraft` desenini uygula + `beforeunload` koruması. Sidebar logout'taki `sessionStorage.clear()`/`localStorage.clear()` yalnızca uygulama anahtarlarını silsin.
6. **Analiz stream'inde `"failed"` terminal olayı:** Başarısız analiz şu an `status:"complete"` + varsayılan veri olarak dönüyor — sessiz, tam veri kaybı "başarı" gibi görünüyor. Backend'de ayrı terminal olay + frontend'de işleme.

---

## FAZ 5 — Kısıtlamaların merkezileştirilmesi ve hizalanması

"Kısıtlamalar hata veriyor" şikayetinin sistemik çözümü. `backend/config/` klasörü boş; tüm limitler koda saçılmış.

1. **`config/settings.py` (pydantic-settings):** Tüm limitleri tek yerden, env-tunable yap: `MAX_UPLOAD_MB`, e-posta ek limitleri, `MAX_PDF_PAGES`, `LIBREOFFICE_TIMEOUT` (şu an hardcoded 120), `GS_TIMEOUT_SECONDS`, PDF parse timeout (60), counter fetch timeout (10), cache TTL'leri, rate limit.
2. **Zaman bütçesi hizalaması:** LO(120) + GS(240) = 360 sn > nginx 300 sn — garanti 504 penceresi. Toplam istek bütçesi tanımla, alt bileşenler ondan pay alsın; semaphore acquire'lara timeout → dolunca 503 "sistem meşgul" (sonsuz bekleme yerine).
3. **HTTP durum kodu disiplini:** 500'e mahkûm edilmiş 4xx'leri düzelt: GS timeout → 503, mükerrer config kaydı → 409 (`DuplicateItemError` handler'ı zaten var, route'lar kullanmıyor), not-found → 404, doğrulama → 400. `tracking_no` 409 tespitini string eşlemeden `pgcode == '23505'` + constraint adına çevir.
4. **`/process` LLM çıktısına Pydantic şeması:** Intake yolu zaten `model_validate_json` kullanıyor; `/process` kullanmıyor → bozuk çıktı varsayılan veriyle "başarılı" dönüyor.

---

## FAZ 6 — AI-dostu repo ve bakım kolaylığı

Kullanıcının talebi: "AI'ın işini kolaylaştıracak klasörler + memory". Şu an repoda hiç `CLAUDE.md` yok; `docs/` 37 tarih-bazlı plan/rapor dosyasıyla dolu ama güncel mimari doküman yok — AI her oturumda mimariyi sıfırdan keşfediyor.

1. **`CLAUDE.md` (repo kökü):** Mimari özet (iki katmanlı nginx, tek VM, tenant modeli), komutlar (test koşusu: backend pytest konteynerde / frontend vitest host'ta; deploy prosedürü), kritik tuzaklar (PS5.1 UTF-8, OneDrive docker cache, doctype `_` padding, AVG TLS), kod konvansiyonları.
2. **`docs/` reorganizasyonu:**
   - `docs/mimari/` — yaşayan dokümanlar: `genel-bakis.md`, `belge-isleme-hatti.md`, `dava-acma-akisi.md`, `dis-bagimliliklar.md` (Gemini/Graph/GS sözleşmeleri, limitler), `deploy-ve-altyapi.md`
   - `docs/plan/` — aktif planlar; `docs/arsiv/` — biten 30+ tarihli plan/rapor buraya
   - `docs/kararlar/` — ADR tarzı kısa karar kayıtları (ör. "tenant_id=NULL ortak havuz", "ofis no isim önceliği") — şu an bu kararlar yalnız AI hafızasında, repo'da değil
3. **`.claude/` genişletmesi:** Sık işler için proje skill'leri (ör. deploy prosedürü, test koşusu), gerekirse `rules` dosyaları.
4. **Modül üstü docstring standardı:** Her `managers/`, `services/`, `routes/` modülünün başına 3-5 satır "ne yapar, kimden çağrılır, dış bağımlılığı ne" bloğu.

---

## Uygulama stratejisi

- **Sıra:** Faz 0 → 1 → 2 önce (arıza yüzeyini ve körlüğü kapatır), sonra 3 → 4 paralel gidebilir, 5 → 6 arkadan.
- **Her faz ayrı commit dizisi + ayrı deploy;** mesai dışı, deploy öncesi `pg_dump`, `--build` ile (frontend memory kuralı).
- **Faz 0 tek deploy'da çıkabilir** (10 küçük, bağımsız düzeltme); Faz 1'in deploy.sh değişikliği kendisi deploy edilmeden önce sunucuda elle prova edilir.
- **Bekleyen iş:** Faz 7 zenginleştirme modu (f4ff9ff) hâlâ deploy bekliyor — bu planın Faz 0'ı ile birlikte veya öncesinde çıkarılmalı, karışmasın diye ayrı deploy önerilir.
- Ölçeklenebilirlik bilinçli olarak kapsam dışı (tek VM + 2 worker ~10 kullanıcıya fazlasıyla yeter); Faz 1-3 zaten ileride yatay büyümenin ön koşullarını (durum dışılaştırma, idempotency, kuyruk) döşüyor.

## Denetim bulgularının tam listesi

Bu plan üç tarama raporunun sentezidir. Tarama raporlarındaki tam bulgu listeleri (90+ madde, dosya:satır referanslı) gerektiğinde yeniden üretilebilir; en kritik 10'ar madde her fazın gerekçesine gömülüdür.
