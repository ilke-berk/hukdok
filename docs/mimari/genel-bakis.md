# Genel bakış — bileşen haritası ve istek yaşam döngüsü

> **Son doğrulama: 2026-08-11 · 2eade56**
> Bu dosyadaki her iddia koddan okunarak doğrulanmıştır. Kod ile çelişirse kod haklıdır —
> bu dosyayı düzelt. Ayrıntı için bkz. [`docs/mimari/README.md`](README.md).

HukuDok bir hukuk bürosu belge otomasyonudur: belge yüklenir, Gemini analiz eder, kullanıcı
onaylar, belge SharePoint arşivine + veritabanına yazılır ve hukukbot'a aktarılır.

## 1. Bileşenler

Üç konteyner, `docker-compose.yml` ile tanımlı:

| Servis | İmaj / kaynak | Yayınlanan port | Bellek | Sağlık kontrolü |
| --- | --- | --- | --- | --- |
| `postgres` | `postgres:15-alpine` (`docker-compose.yml:4`) | `127.0.0.1:5432` (`:15`) | 512m, `memswap=mem` (`:21-22`) | `pg_isready`, 10s (`:28-32`) |
| `backend` (`hukdok_backend`) | `./backend/Dockerfile` (`:37-39`) | `127.0.0.1:8001` (`:50`) | 2g, `memswap=mem` (`:79-80`) | `/healthz`, 30s, start_period 60s (`:86-97`) |
| `frontend` | `./frontend/Dockerfile` (`:106-108`) | `8080:80` (`:113`) | 128m, `memswap=mem` (`:115-116`) | yok; `depends_on: backend healthy` (`:122-124`) |

Üç kural bu tabloda gizli, üçü de bilinçli:

- **`memswap_limit == mem_limit` — swap yasak.** Gerekçe konfigde yazılı: "swap'a taşma,
  2026-07-29 kesintilerindeki I/O fırtınasının mekanizmasıydı" (`docker-compose.yml:19-20`).
- **Backend portu localhost'a sabit.** API-key'li `/export` route'ları public porttan
  erişilememeli (`docker-compose.yml:47-49`). Hukukbot public port yerine ortak
  `hukuk_shared` Docker ağından `http://hukdok_backend:8001` ile konuşur (`:43-44`);
  bu ağ **external**'dır ve önceden `docker network create hukuk_shared` ile kurulur (`:139-142`).
- **Backend'de kaynak kodu bind-mount'u YOK** (`docker-compose.yml:54-56`) — konteyner
  imajdaki kodu çalıştırır. Kod değişikliği ancak rebuild ile görünür. Lokal hot-reload
  isteniyorsa `docker-compose.override.yml.example` kopyalanır (gitignore'da).

Bellek ayarına eşlik eden `MALLOC_ARENA_MAX=2` de aynı OOM incelemesinden gelir: glibc
thread başına arena açıyor, PDF/görüntü dönüşümünün geçici tahsisleri arena'larda kalıp
RSS'i kalıcı yükseltiyordu (`docker-compose.yml:61-64`).

## 2. İki katmanlı nginx

Repodaki `nginx.conf` **konteyner** nginx'idir (`listen 80`, `nginx.conf:8`; compose bunu
8080'de yayınlar). SPA'yı `/usr/share/nginx/html` kökünden servis eder ve `try_files` ile
`/index.html`'e düşer (`nginx.conf:21-25`).

Backend'e proxy'lenen location'ların **tam** listesi:

| Location | Not |
| --- | --- |
| `= /healthz` | **Exact match şart** — `location /` (SPA try_files) yutarsa backend ölüyken bile 200 index.html döner ve izleme kör kalır (`nginx.conf:27-31`) |
| `/api` | genel API (`nginx.conf:42`) |
| `/process` | belge analizi; `client_max_body_size 50M` (`nginx.conf:50-57`) |
| `/confirm` | onay + arşivleme (`nginx.conf:59`) |
| `/preview-email-body` | (`nginx.conf:67`) |
| `/refresh` | liste tazeleme (`nginx.conf:75`) |

**`/export` bu listede YOKTUR ve asla eklenmez** — konfigin kendi uyarısı: "DIKKAT: /export
buraya ASLA eklenmez — yalnizca ic Docker network'unden erisilir, public'e proxy'lenmez"
(`nginx.conf:40-41`). Karar kaydı: [`docs/kararlar/010-export-nginxe-acilmaz.md`](../kararlar/010-export-nginxe-acilmaz.md).

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
   (`backend/migrate.py:1-10`). Migrasyonlar `backend/database.py:131` `_MIGRATIONS`
   listesinden idempotent uygulanır (`database.py:529` `check_and_migrate_tables`).
   `migrate.py` ayrı süreç olduğu için `DB_STATEMENT_TIMEOUT_MS=0` atar — uygulama
   engine'inin 30 sn'lik sınırı backfill UPDATE'lerini kesmesin (`backend/migrate.py:20-26`).
2. `uvicorn api:app --workers ${UVICORN_WORKERS:-2}`.

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
TEK `CRITICAL` log satırı atılır (`singleton_lock.py:132-142`), log tabanlı alarm bunu yakalar.

| İş | Kapsam | Kod |
| --- | --- | --- |
| APScheduler: günlük aktivite raporu, `CronTrigger(hour=0, minute=0, Europe/Istanbul)` | yalnız lider | `api.py:163-177` |
| APScheduler: dönüşüm retry, `CronTrigger(hour=2, minute=30, Europe/Istanbul)` | yalnız lider | `api.py:184-190` |
| Kaçırılan gün raporlarını tamamlama (catch-up thread) | yalnız lider | `api.py:195-197` |
| SharePoint upload outbox worker'ı | yalnız lider | `api.py:206-213` |
| Liste tazeleme (refresh) thread'i | **worker başına — bilinçli** | `api.py:149-159` |

Refresh thread'inin istisna olmasının gerekçesi kodda yazılı: DynamicConfig, matcher ve
searcher **süreç içi singleton**'lardır; yalnız liderde koşsaydı diğer worker'lar boş
listelerle kalırdı. Bilinen sınır da orada kabul edilmiş: `/refresh` yalnız isteği işleyen
worker'ı tazeler, diğeri kendi refresh'ine kadar bayat kalır — "liste değişiklikleri nadir,
kabul edilen takas" (`api.py:149-156`).

02:30 saatinin seçimi de tesadüf değil: gece yarısı raporu (00:00) ve host pg_dump'ı
(03:30) ile çakışmasın diye (`api.py:181-182`).

## 4. Kimlik ve tenant

Kimlik Azure AD'dir. `backend/auth_verifier.py` token'ın doğrulanmamış header'ından `tid`
okur, `ALLOWED_TENANTS` env listesine karşı kontrol eder, ilgili tenant'ın JWKS'inden imza
anahtarını alır ve RS256 + audience doğrulaması yapar.

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
Sonuç 10 saniyelik TTL cache'te tutulur (`api.py:449` `_HEALTHZ_CACHE_TTL_SECONDS = 10.0`) —
compose healthcheck'i (30s), GCP uptime check ve deploy kapısı aynı anda yokladığında DB'ye
yığılmasın diye.

`degraded`'in 200 dönmesi bilinçlidir: Docker restart'ı ve uptime alarmını tetiklemez,
yalnız görünürlük sağlar; ERROR tabanlı alarmlar log yolundan gelir (bkz.
[`deploy-ve-altyapi.md`](deploy-ve-altyapi.md)).

## 7. Frontend

React + Vite SPA. Kimlik `@azure/msal-react` ile kurulur; token `acquireTokenSilent` ile
alınıp `Authorization: Bearer` olarak eklenir (`frontend/src/lib/api.ts`). API katmanının
iki zaman aşımı kademesi vardır — etkileşimli çağrılar için kısa, uzun süren uçlar
(`/process`, `/confirm`, `/api/case-intake/*`, indirme) için nginx'in 300s penceresiyle
hizalı uzun kademe. GET'ler 502/503/504'te sınırlı sayıda yeniden denenir; POST'lar
**hiçbir zaman** otomatik tekrarlanmaz (idempotency kuralı).

## 8. Nereye bakmalı

| Konu | Dosya |
| --- | --- |
| `/process` → `/confirm` zinciri, olay sözleşmesi, zaman bütçeleri | [`belge-isleme-hatti.md`](belge-isleme-hatti.md) |
| Manuel form + intake sihirbazı, ofis no, taslak kalıcılığı | [`dava-acma-akisi.md`](dava-acma-akisi.md) |
| Gemini, Graph/SharePoint, e-posta, ayar tablosu | [`dis-bagimliliklar.md`](dis-bagimliliklar.md) |
| deploy/rollback, systemd birimleri, izleme, yedekleme | [`deploy-ve-altyapi.md`](deploy-ve-altyapi.md) |
| Kalıcı mimari kararlar ve gerekçeleri | [`docs/kararlar/`](../kararlar/) |
