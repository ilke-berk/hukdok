# Genel bakış — bileşen haritası ve istek yaşam döngüsü

> **Son doğrulama: 2026-08-11 · 2eade56**
> §1 compose satır atıfları + Postgres parametreleri, §2 (önbellek başlıkları ve `nginx.conf`
> satırları), §3'teki `migrate.py` cümlesi ve §7 alt başlıkları: **2026-09-14 · G193**
> (G182-G191 sonrası, main `e3ba26d` koduna karşı yeniden okundu). §3'ün diğer
> `database.py`/`api.py` satır atıfları bu turda yeniden doğrulanmadı.
> Bu dosyadaki her iddia koddan okunarak doğrulanmıştır. Kod ile çelişirse kod haklıdır —
> bu dosyayı düzelt. Ayrıntı için bkz. [`docs/mimari/README.md`](README.md).

HukuDok bir hukuk bürosu belge otomasyonudur: belge yüklenir, Gemini analiz eder, kullanıcı
onaylar, belge SharePoint arşivine + veritabanına yazılır ve hukukbot'a aktarılır.

## 1. Bileşenler

Üç konteyner, `docker-compose.yml` ile tanımlı:

| Servis | İmaj / kaynak | Yayınlanan port | Bellek | Sağlık kontrolü |
| --- | --- | --- | --- | --- |
| `postgres` | `postgres:15-alpine` (`docker-compose.yml:4`) | `127.0.0.1:5432` (`:26`) | 512m, `memswap=mem` (`:32-33`) | `pg_isready`, 10s (`:39-43`) |
| `backend` (`hukdok_backend`) | `./backend/Dockerfile` (`:48-50`) | `127.0.0.1:8001` (`:65`) | 2g, `memswap=mem` (`:103-104`) | `/healthz`, 30s, start_period 60s (`:110-121`) |
| `frontend` | `./frontend/Dockerfile` (`:130-132`) | `8080:80` (`:137`) | 128m, `memswap=mem` (`:139-140`) | yok; `depends_on: backend healthy` (`:146-148`) |

Üç kural bu tabloda gizli, üçü de bilinçli:

- **`memswap_limit == mem_limit` — swap yasak.** Gerekçe konfigde yazılı: "swap'a taşma,
  2026-07-29 kesintilerindeki I/O fırtınasının mekanizmasıydı" (`docker-compose.yml:30-31`).
- **Backend portu localhost'a sabit.** API-key'li `/export` route'ları public porttan
  erişilememeli (`docker-compose.yml:62-64`). Hukukbot public port yerine ortak
  `hukuk_shared` Docker ağından `http://hukdok_backend:8001` ile konuşur (`:54-55`);
  bu ağ **external**'dır ve önceden `docker network create hukuk_shared` ile kurulur (`:163-166`).
- **Backend'de kaynak kodu bind-mount'u YOK** (`docker-compose.yml:69-71`) — konteyner
  imajdaki kodu çalıştırır. Kod değişikliği ancak rebuild ile görünür. Lokal hot-reload
  isteniyorsa `docker-compose.override.yml.example` kopyalanır (gitignore'da).

Bellek ayarına eşlik eden `MALLOC_ARENA_MAX=2` de aynı OOM incelemesinden gelir: glibc
thread başına arena açıyor, PDF/görüntü dönüşümünün geçici tahsisleri arena'larda kalıp
RSS'i kalıcı yükseltiyordu (`docker-compose.yml:85-88`).

Postgres sunucu parametreleri compose'daki `command:` satırındadır (`docker-compose.yml:22`,
G191): `effective_cache_size=384MB`, `random_page_cost=1.1`,
`shared_preload_libraries=pg_stat_statements`, `track_io_timing=on`. Gerekçeler ve
"`restart` ile gelmez, `up -d` recreate şart" kuralı
[`deploy-ve-altyapi.md` §13](deploy-ve-altyapi.md).

## 2. İki katmanlı nginx

Repodaki `nginx.conf` **konteyner** nginx'idir (`listen 80`, `nginx.conf:8`; compose bunu
8080'de yayınlar). SPA'yı `/usr/share/nginx/html` kökünden servis eder ve `try_files` ile
`/index.html`'e düşer (`nginx.conf:88-91`).

**Önbellek başlıkları (G182, `nginx.conf:38-51` gerekçe yorumu):**

| Location | `Cache-Control` | Eksik dosyada |
| --- | --- | --- |
| `~* ^/assets/` (`nginx.conf:77-86`) | `public, max-age=31536000, immutable` — Vite parça adları içerik hash'lidir | `=404`; index.html'e DÜŞMEZ (aksi hâlde HTML, JS adresi altında 1 yıl önbelleğe girerdi). Başlık bilerek `always` değil: 404'e immutable yazılmaz |
| `/` (`nginx.conf:88-99`) | `no-cache` — index.html ve SPA fallback her açılışta ETag ile yeniden doğrulanır, deploy sonrası yeni parça adları hemen gelir | SPA fallback (index.html) |

`add_header` kalıtım kuralı: bir location içinde tek `add_header` bile varsa server düzeyindeki
`add_header`'lar o blokta düşer. Bu yüzden beş güvenlik başlığı (`nginx.conf:53-56`, CSP `:70`)
iki location'da AYNEN tekrar yazılıdır; birini değiştiren üç yeri değiştirir (`nginx.conf:48-51`).
Eski sekmede bayat parçanın 404'ü frontend'in tek yenileme dalını tetikler (§7). Host nginx'in
bu başlıkları geçirdiği prod'da doğrulanacak ([`deploy-ve-altyapi.md` §11](deploy-ve-altyapi.md)).

Backend'e proxy'lenen location'ların listesi:

| Location | Not |
| --- | --- |
| `= /healthz` | **Exact match şart** — `location /` (SPA try_files) yutarsa backend ölüyken bile 200 index.html döner ve izleme kör kalır (`nginx.conf:101-111`) |
| `/api` | genel API (`nginx.conf:116`) |
| `/process` | belge analizi; `client_max_body_size 50M` (`nginx.conf:124-131`) |
| `/confirm` | onay + arşivleme (`nginx.conf:133`) |
| `/preview-email-body` | (`nginx.conf:141`) |
| `/preview-client-email-body` | müşteri/müvekkil bilgilendirme gövdesi (`routes/processing.py:347`); prefix eşleşmesi olduğu için üstteki `/preview-email-body` bunu YAKALAMAZ (`nginx.conf:149-159`) |
| `/refresh` | liste tazeleme (`nginx.conf:161`) |

**`/export` bu listede YOKTUR ve asla eklenmez** — konfigin kendi uyarısı: "DIKKAT: /export
buraya ASLA eklenmez — yalnizca ic Docker network'unden erisilir, public'e proxy'lenmez"
(`nginx.conf:114-115`). Karar kaydı: [`docs/kararlar/010-export-nginxe-acilmaz.md`](../kararlar/010-export-nginxe-acilmaz.md).

`proxy_read_timeout`/`proxy_send_timeout` 300s'tir (`nginx.conf:13-14`). Gerekçe konfigde:
GhostScript PDF/A dönüşümü 60s'yi aşabiliyor, default 60s ile `/confirm` 504 dönüyor ama
backend işlemi tamamlıyordu — **mükerrer kayıt kaynağı** (`nginx.conf:10-12`).

TLS bu katmanda **sonlanmaz**: konteynerler düz HTTP konuşur, TLS prod'daki **host**
nginx'indedir. Host konfigi `infra/nginx/sites-available/default` olarak repoda tutulur ve
timeout'ları bu katmanla eşit olmalıdır (`nginx.conf:12`). Bkz.
[`deploy-ve-altyapi.md`](deploy-ve-altyapi.md).

## 3. Backend açılış sırası

`backend/docker-entrypoint.sh` iki adımdır:

1. `python migrate.py` — şema migrasyonları **uvicorn'dan önce, tek süreçte**. Gerekçe
   modül docstring'inde: "her worker kendi migrasyonunu koşarsa DDL yarışı olur"; çıkış
   kodu 1 ise entrypoint `set -e` ile durur, "sessiz şema sapması yerine fail-fast"
   (`backend/migrate.py:1-10`). Migrasyonlar `backend/database.py:142` `_MIGRATIONS`
   listesinden idempotent uygulanır (`database.py:939` `check_and_migrate_tables`).
   `migrate.py` ayrı süreç olduğu için `DB_STATEMENT_TIMEOUT_MS`, `DB_IDLE_TX_TIMEOUT_MS`
   ve `DB_LOCK_TIMEOUT_MS`'i `0`'lar — uygulama engine'inin sınırları (30 sn sorgu, 60 sn
   boşta transaction, 5 sn kilit bekleme; `backend/database.py:65-67`) backfill
   UPDATE'lerini kesmesin (`backend/migrate.py:19-30`; ayrıntı
   [`deploy-ve-altyapi.md` §13](deploy-ve-altyapi.md)).
2. `uvicorn api:app --workers ${UVICORN_WORKERS:-2}`.

### Migrasyon op türleri ve `create_all` tuzağı

`init_db()` önce `Base.metadata.create_all()` koşturur, `check_and_migrate_tables()` tablo/kolon
listesini **sonra** okur (`database.py:113-117`). Sonuç: `("table", …)` ve `("columns", …)`
op'ları **koşulludur** — modelde tanımlı bir tablo/kolon create_all tarafından zaten
yaratılmışsa op atlanır (`database.py:1016-1017`, `database.py:993-994`) ve **gövdesine iliştirilmiş** `CREATE INDEX` /
`CONSTRAINT … UNIQUE` ifadeleri o kurulumda hiç çalışmaz. `("index", …)` op'u ise koşulsuz
koşar; `IF NOT EXISTS` onu idempotent kılar. Kural: kalıcı olması istenen kısıt/index **daima**
`("index", …)` op'una yazılır (`database.py:136-141` şerhi).

FAZ D 6.1 (G041) bu boşluğu kapattı: tablo op'larına gömülü olduğu için hiç oluşmamış kısıt ve
index'ler 28. maddeye taşındı — `uq_case_relation`, `uq_daily_report`, `idx_case_relations_*`,
`idx_daily_reports_user` ve `ix_clients_name`. UNIQUE'ler `ALTER TABLE ADD CONSTRAINT` ile
değil `CREATE UNIQUE INDEX IF NOT EXISTS` ile eklenir (ADD CONSTRAINT idempotent değildir).
Mükerrer veride migrasyon **bilinçli durur** (sessiz atlama şemayı sessizce saptırırdı), ama
önce `_unique_index_duplicate_report` (`database.py:880`) hangi tabloda kaç mükerrer grup
olduğunu örnek anahtarlarla raporlar. Kalan bilinen boşluk: `("columns", …)` op'larının
post-SQL index'leri sıfırdan kurulumda hâlâ oluşmuyor (en kritiği `uq_cases_sistem_no`) —
mevcut kurulumlarda kolon migrasyonla eklendiği için varlar. Mekanizmanın tamamı
`backend/tests/test_migration_path.py`'de gerçek Postgres'e karşı kilitli.

### Lider kilidi: hangi iş kaç kere koşar

uvicorn her worker sürecinde lifespan'i ayrı koşar. Süreç-tekil olması gereken işler
`backend/services/singleton_lock.py`'deki dosya kilidiyle (flock/msvcrt, `LOCK_EX | LOCK_NB`)
korunur; kilidi alan worker "lider"dir. Kilit süreç yaşadıkça tutulur, süreç ölünce çekirdek
bırakır → yeni worker devralır, **liderlik sabit bir worker'a bağlı değildir**
(`singleton_lock.py:1-12`).

Kilit dosyası tek yola bağlı değildir (G012): aday zinciri `tempfile.gettempdir()` →
`/dev/shm` → `/var/tmp` sırayla denenir (`singleton_lock.py::_lock_path_candidates`).
Ayrım kritik: yol AÇILAMAZSA (OSError) sıradaki adaya geçilir; dosya açılıp kilit BAŞKA
süreçte çıkarsa zincir durur ve worker lider OLMAZ (yoksa iki lider doğardı). Hiçbir aday
açılamazsa fail-open korunur — her worker kendini lider sayar (arıza günü arkaplan işleri
tamamen durmasın; en kötü durum tekli davranışın N kopyası) ama sessiz değil: süreç başına
TEK `CRITICAL` log satırı atılır (`singleton_lock.py:139`), log tabanlı alarm bunu yakalar.

| İş | Kapsam | Kod |
| --- | --- | --- |
| APScheduler: günlük aktivite raporu, `CronTrigger(hour=0, minute=0, Europe/Istanbul)`, `id="daily_activity_report"` | yalnız lider | `api.py:195-201` |
| APScheduler: dönüşüm retry (`conversion_retry.retry_pending_conversions`), `CronTrigger(hour=2, minute=30, Europe/Istanbul)`, `id="conversion_retry"` | yalnız lider | `api.py:208-214` |
| APScheduler: süre/duruşma taraması (`deadline_scanner.scan_deadlines`), `CronTrigger(hour=6, minute=0, Europe/Istanbul)`, `id="deadline_scan"` | yalnız lider | `api.py:222-228` |
| Kaçırılan gün raporlarını tamamlama (catch-up thread) | yalnız lider | `api.py:237` |
| Süre taraması boot telafisi (`deadline_scanner.boot_catch_up_scan`) | yalnız lider | `api.py:243-244` |
| Veri teslim açılış toparlaması (`teslim_kutusu.boot_toparla`; yalnız kesilmiş elle uygulama → `inceleme_bekliyor`, uygulama/tarama YOK) | yalnız lider | `api.py:249-250` |
| SharePoint upload outbox worker'ı | yalnız lider | `api.py:262-263` |
| Liste tazeleme (refresh) thread'i | **worker başına — bilinçli** | `api.py:171-181` |

Üç cron job'ı da tek `BackgroundScheduler` üzerindedir (`api.py:194`; 04:00 veri teslim turu
17.09.2026'da SharePoint teslim klasörü yoluyla kalktı) — yeni thread/scheduler
açılmaz (3-E devri); `misfire_grace_time=3600` ile lider bir saat içinde ayağa kalkarsa
kaçan tetik yine koşar.

Refresh thread'inin istisna olmasının gerekçesi kodda yazılı: DynamicConfig, matcher ve
searcher **süreç içi singleton**'lardır; yalnız liderde koşsaydı diğer worker'lar boş
listelerle kalırdı. Bilinen sınır da orada kabul edilmiş: `/refresh` yalnız isteği işleyen
worker'ı tazeler, diğeri kendi refresh'ine kadar bayat kalır — "liste değişiklikleri nadir,
kabul edilen takas" (`api.py:176-178`).

Saatlerin seçimi tesadüf değil, gerekçeler kodda: 02:30 dönüşüm retry'ı gece yarısı raporu
(00:00) ve host pg_dump'ı (03:30) ile çakışmasın diye; 06:00 süre
taraması gece işleri bitmiş ve uyarı mesai başlangıcında hazır olsun diye (`api.py:216-218`).

## 4. Kimlik ve tenant

Kimlik Azure AD'dir. `backend/auth_verifier.py` token'ın imzasız decode edilen
claim'lerinden `tid` okur, `ALLOWED_TENANTS` env listesine karşı kontrol eder, ilgili
tenant'ın JWKS'inden imza anahtarını alır ve RS256 imza + `aud` + `iss` + `exp`
doğrulaması yapar; sunucu tarafı oturum tutulmaz. Tarayıcı akışı (MSAL, sessionStorage,
401 yenilemesi, çıkış yolları), süre tablosu, Graph app-only akışı ve açık kalemler
[`kimlik-ve-token.md`](kimlik-ve-token.md)'dedir — burada tekrarlanmaz.

Tenant modeli **paylaşımlı havuzdur**: `cases`/`clients` tablolarında `tenant_id` kolonu
vardır ama yeni kayıtlar bilinçli `NULL` yazılır, çünkü Hanyaloğlu Acar + LexisBio ortak
çalışır. Sorgular `tenant_id == X OR tenant_id IS NULL` deseniyle filtreler
(`backend/auth_helpers.py:14-16`). Karar kaydı:
[`docs/kararlar/001-tenant-ortak-havuz.md`](../kararlar/001-tenant-ortak-havuz.md).

## 5. Bir `/process` isteğinin yaşam döngüsü

```
tarayıcı (MSAL access token)
  → host nginx (TLS:443, repo dışı konfig — infra/nginx/sites-available/default)
    → konteyner nginx :80  [location /process, proxy_read_timeout 300s]
      → uvicorn :8001 (2 worker'dan biri)
        → middleware: RequestId → RequestSizeLimit → SlowAPI (rate limit) → CORS
          → routes/processing.py  /process
            → Azure AD token doğrulama (auth_verifier)
            → dosya kabul + PROCESS_CACHE bakımı
            → paralel: SharePoint sayacından ofis no ATOMİK tahsis
            → analyzer.analyze_file_generator → Gemini
            ← NDJSON stream: info… → complete | failed
```

Yanıt `application/x-ndjson` akışıdır; olay sözleşmesi frontend ile ortak referanstır ve
[`belge-isleme-hatti.md`](belge-isleme-hatti.md)'de birebir yazılıdır.

## 6. `/healthz` — derin sağlık ucu

`backend/api.py` içindeki route DB'ye `SELECT 1` atar ve `backend/health.py`'nin süreç-içi
sinyalleriyle birleştirir:

| Durum | HTTP | Koşul |
| --- | --- | --- |
| `unhealthy` | 503 | DB erişilemiyor |
| `degraded` | 200 | DB tamam, ama son 1 saatte Gemini nihai hatası var ya da Graph token son denemesi başarısız |
| `ok` | 200 | hepsi temiz |

Yanıt gövdesi `status`, `version` (imaja gömülü git SHA) ve `checks` alanlarını taşır.
Sonuç 10 saniyelik TTL cache'te tutulur (`api.py:444` `_HEALTHZ_CACHE_TTL_SECONDS = 10.0`) —
compose healthcheck'i (30s), GCP uptime check ve deploy kapısı aynı anda yokladığında DB'ye
yığılmasın diye.

`degraded`'in 200 dönmesi bilinçlidir: Docker restart'ı ve uptime alarmını tetiklemez,
yalnız görünürlük sağlar; ERROR tabanlı alarmlar log yolundan gelir (bkz.
[`deploy-ve-altyapi.md`](deploy-ve-altyapi.md)).

## 7. Frontend

React + Vite SPA. Kimlik `@azure/msal-react` ile kurulur; token `acquireTokenSilent` ile
alınıp `Authorization: Bearer` olarak eklenir (`frontend/src/lib/api.ts`; 401'de tek
yenileme + tekrar, ayrıntı [`kimlik-ve-token.md`](kimlik-ve-token.md)). API katmanının
iki zaman aşımı kademesi vardır — etkileşimli çağrılar için kısa, uzun süren uçlar
(`/process`, `/confirm`, `/api/case-intake/*`, indirme) için nginx'in 300s penceresiyle
hizalı uzun kademe. GET'ler 502/503/504'te sınırlı sayıda yeniden denenir; POST'lar
**hiçbir zaman** otomatik tekrarlanmaz (idempotency kuralı).

### Route düzeyinde kod bölme (G182)

`frontend/src/App.tsx:25-41`: `Login` ve `NotFound` statik import edilir (oturumsuz ilk
açılış ve 404 ek ağ turu beklemesin); diğer 12 sayfa
`lazy(() => importWithReload(() => import("./pages/X")))` ile route başına ayrı parçadır.
`<Routes>` tek bir `<Suspense fallback={<PageLoading />}>` ile sarılıdır (`App.tsx:105-149`).
Parça ancak route'un elemanı çizilince iner: `/reports` ve `/admin` `ProtectedAdminRoute`
altındadır (`App.tsx:128-143`) ve bu bekçi admin olmayana çocuğu hiç çizmeden `/`'e
yönlendirir (`components/ProtectedAdminRoute.tsx`) — rapor katmanı ve `@dnd-kit` o
kullanıcıya inmez. Kodun yorumuna göre BrowserRouter gezinmeleri `startTransition` içinde
yaptığından sayfalar arası geçişte eski sayfa yerinde kalır; gösterge pratikte yalnız ilk
açılışta görünür (`App.tsx:49-51`). Yeni sayfa eklenirse aynı desenle eklenir;
`frontend/src/App.lazy.test.tsx`'teki kaynak bekçisi `pages/` dizininden türeyerek bunu
denetler.

### Bayat parça: tek yenileme (G182)

Her deploy yeni hash'li parça adları üretir, eskileri yeni imajda yoktur. Açık kalmış
sekme eski `index.html`'in adıyla bir sayfaya geçerse konteyner nginx `/assets/` altında
`404` döner (§2) ve dinamik import düşer. `frontend/src/lib/chunkReload.ts`:

- `isChunkLoadError` yalnız ağdan yüklenememe hatalarını tanır (Chromium/Firefox/Safari
  dinamik import mesajları, Vite "Unable to preload CSS", `ChunkLoadError` adı); modül
  içi çalışma hatası yenileme tetiklemez.
- `importWithReload` ilk parça hatasında `sessionStorage` bayrağı `hukudok:chunk-reload`
  yazar ve `location.reload()`'u **bir kez** çağırır; dönen söz hiç çözülmez, ekran
  Suspense göstergesinde kalır (hata ekranı yanıp sönmez).
- Bayrak zaten varsa ya da storage okunamıyor/yazılamıyorsa yenilemez, hata
  `ErrorBoundary`'ye düşer (döngü engellenemiyorsa yenileme yok).
- Başarılı parça yüklemesi bayrağı siler; sonraki deploy yine bir kez yenileyebilir.

### Config listeleri: `useConfigList` (G184, G185)

`frontend/src/hooks/useConfig.ts`'te `useConfig()` 32 `useQuery`'ye birden abone olur.
`useConfigList(key)` (`useConfig.ts:159-172`) yalnız tek listeye abone olur. İkisi sorguyu
aynı kurucudan alır (`configListQueryOptions`, `:128-134`: aynı `queryKey`,
`staleTime` 5 dk, `retry: false`, `enabled`); önbellek ortaktır, iki hook aynı listeyi çift
çekmez. `useConfigList().error` bir mesaj dizgesidir (`useConfig().configError` ile aynı
G019 sözleşmesi: hata ≠ boş liste). Türetilmiş yardımcılar saf fonksiyon olarak dışa
verilir: `groupCourtTypesByParent`, `splitPartyRoles`.

| Hook | Tüketiciler |
| --- | --- |
| `useConfigList` | `pages/Index`, `pages/CaseList`, `pages/CaseDetails`, `pages/NewClient`, `components/email/EmailModal`, `components/QuickCaseModal` (zorunlu alan sorgusunu `useConfig()`'teki ile aynı anahtarla kendisi kurar, `QuickCaseModal.tsx:85`) |
| `useConfig()` | `pages/AdminPage` (13 liste + ekleme/sıralama/güncelleme/silme mutasyonları, `AdminPage.tsx:331-340`), `pages/NewCase` ve `components/intake/IntakeReviewStep` (7 liste + `required_case_fields`; `NewCase.tsx:89-94`, `IntakeReviewStep.tsx:131`), `components/AnalysisResults`, `components/BulkUploadWorkbench`, `components/CaseTrackingPanel`, `components/YetkiBelgesiModal` |

Kural: yeni bir tüketici yalnız okuduğu listelere `useConfigList` ile abone olur; 32
sorguluk `useConfig()` birçok listeyi ve zorunlu alan ucunu birlikte kullanan yere kalır.

### Odakta yeniden çekme kapalı (G184)

`App.tsx:43-47`: `new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } })`.
Gerekçe: açıkken 5 dk `staleTime` dolunca her pencere odağı `useConfig`'in 32 sorgusunu
topluca yeniden çekiyordu. Karar global olduğu için config dışındaki sorgular da odakta
tazelenmez: `hooks/useClients.ts:47`, `pages/ClientList.tsx:132` (poliçeler),
`hooks/usePartyCheck.ts:112`; bunlar mount, mutasyon sonrası invalidate ve `staleTime`
ile tazelenir. Tek bir sorgu odakta tazelenmeliyse kendi seçeneğinde
`refetchOnWindowFocus: true` verilir. `frontend/src` altında `refetchInterval` kullanımı yoktur.
Bildirim sayacı react-query değildir: `hooks/useNotifications.ts` kendi `setInterval`'ı
(`NOTIFICATION_POLL_MS = 60_000`, `:36`) ve `visibilitychange` dinleyicisiyle (`:155-187`)
çalışır, bu karardan etkilenmez.

### Tema sağlayıcısı ve tarayıcı deposu (G188)

`ThemeProvider` `ErrorBoundary`'nin İÇİNDEdir (`App.tsx:244-250`) ve kayıtlı temayı
try/catch'li okur (`components/theme-provider.tsx:14` `readStoredTheme`): depo kapalıyken
(özel pencere, kurumsal politika) uygulama beyaz ekran yerine varsayılan temayla açılır.
Yetki belgesi önbelleği TC taşımaz; ad + sicil `sessionStorage`'da `yetki_belgesi_avukat_cache:v1`
anahtarındadır, eski kalıcı anahtar modal açılınca silinir
(`components/YetkiBelgesiModal.tsx:32-33`; kural kaynağı `lib/formDraft.ts`).

## 8. Nereye bakmalı

| Konu | Dosya |
| --- | --- |
| `/process` → `/confirm` zinciri, olay sözleşmesi, zaman bütçeleri | [`belge-isleme-hatti.md`](belge-isleme-hatti.md) |
| Manuel form + intake sihirbazı, ofis no, taslak kalıcılığı | [`dava-acma-akisi.md`](dava-acma-akisi.md) |
| Veri teslim hattı: panelden yükleme, defter, kapı, elle uygulama, cevap dosyaları | [`veri-teslim-hatti.md`](veri-teslim-hatti.md) |
| Raporlama: kayıt defteri (serbest SQL yok), önizleme, Excel/CSV export + koşu logu, şablonlar, AI asistan + `rapor_asistani` anahtarı | [`raporlama.md`](raporlama.md) |
| Gemini, Graph/SharePoint, e-posta, ayar tablosu | [`dis-bagimliliklar.md`](dis-bagimliliklar.md) |
| Kullanıcı oturumu, token doğrulama zinciri, süreler, Graph app-only kimlik | [`kimlik-ve-token.md`](kimlik-ve-token.md) |
| deploy/rollback, systemd birimleri, izleme, yedekleme | [`deploy-ve-altyapi.md`](deploy-ve-altyapi.md) |
| Kalıcı mimari kararlar ve gerekçeleri | [`docs/kararlar/`](../kararlar/) |
