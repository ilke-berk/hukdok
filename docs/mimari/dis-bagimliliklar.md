# Dış bağımlılıklar — Gemini, Microsoft Graph/SharePoint, e-posta, sistem araçları

> **Son doğrulama: 2026-08-11 · 2eade56** — §2 (Graph/SharePoint) 2026-09-08 · G148 ile
> G147 sonrası koda (`11150b4`) göre yeniden doğrulandı; satır numaraları o ağaca aittir.
> Her iddia koddan doğrulanmıştır. Kod ile çelişirse kod haklıdır — bu dosyayı düzelt.

HukuDok dört dış sisteme bağlıdır: **Gemini** (analiz), **Microsoft Graph** (SharePoint
arşivi + e-posta), **PostgreSQL** ve konteyner içindeki **GhostScript / LibreOffice**.
Ortak tasarım kuralı: her dış çağrının bir zaman tavanı, bir retry politikası ve bir
başarısızlık sözleşmesi vardır — hiçbiri sonsuza dek asılmaz.

## 1. Gemini

**SDK:** `google-genai==2.11.0` (`backend/requirements.txt:4`). Ortak istemci
`backend/gemini_client.py`'dedir; eski SDK'daki `genai.configure(...)` global durumunun
yerini alır ve tüm modüller (analyzer, email_sender, date_extractor) Client'ı buradan alır
(`gemini_client.py:1-8`).

Anahtar `vault.get_secret("GEMINI_API_KEY")` üzerinden okunur; bulunamazsa `None` döner ve
çağıran akışı keser (`gemini_client.py:40-53`). İstemci anahtar değişmediği sürece bir kez
kurulur.

**HTTP timeout** zorunludur: "Hiçbir Gemini çağrısı sonsuza dek asılmamalı: SDK'da
varsayılan timeout yok, takılı bir istek `/process` akışını süresiz bloke ediyordu"
(`gemini_client.py:29-33`). Değer `gemini_http_timeout_ms` = 120000 ms.

**SDK'nın kendi retry'ı bilinçli KAPALI** bırakılmıştır: verilmediğinde SDK "never retry"
kullanır, retry politikasının tek sahibi bizim katmanımızdır — çifte-retry çarpanı olmaz
(`gemini_client.py:10-14`).

### Retry sınıflandırması — kod bazlı, string eşleme yok

| Küme | Değerler | Kod |
| --- | --- | --- |
| `RETRYABLE_API_CODES` | 429, 500, 502, 503, 504 | `gemini_client.py:72` |
| `SATURATION_API_CODES` (devre kesiciyi besleyen) | 429, 503 | `gemini_client.py:75` |

`classify_transient` üç değer döndürür: `"429"` (kota — uzun backoff), `"server"`
(500/502/503/504 — kısa backoff), `"transport"` (httpx ağ/timeout) ya da `None` (kalıcı,
retry anlamsız) (`gemini_client.py:78-88`). `httpx` google-genai'nin zorunlu transport
bağımlılığıdır ve requirements'a ayrıca yazılmamıştır (`gemini_client.py:21-22`).

**Backoff** (`analyzer.py:82-149`): en çok 5 retry; 429 için taban 5 sn (5, 10, 20…),
sunucu/ağ için taban 1 sn (1, 2, 4, 8, 16…); her ikisine jitter eklenir, tavan 30 sn.

**Deadline:** retry'lar dahil toplam süre `gemini_retry_deadline_seconds` (170 sn) ile
sınırlıdır. Bütçe "yeni bekleme/deneme BAŞLATMA" kapısıdır: bekleme deadline'ı aşacaksa
yeni deneme başlatılmaz. Aritmetik `170 + 120 = 290 < 300` (nginx penceresi) ve bekçi
testiyle kilitlidir (`analyzer.py:75-79`, `config/settings.py:96-97`).

### Devre kesici — model başına

`CIRCUIT_FAILURE_THRESHOLD = 5`, `CIRCUIT_OPEN_SECONDS = 60.0` (`gemini_client.py:105-106`).
Art arda 5 doygunluk hatası (429/503) kesiciyi 60 sn açar; açıkken çağrı Gemini'ye gitmeden
`GeminiCircuitOpenError` ile hızlı-fail eder ve kullanıcıya `error_kod: gemini_saturated`
olarak yansır.

Üç tasarım notu kodda yazılıdır (`gemini_client.py:91-104`):

- **Model başına** tutulur, çünkü Gemini'de rate-limit/overload model bazlıdır: tek global
  kesici, intake modelinin fırtınasında ana analiz modelini de keserdi (yanlış pozitif).
- **State süreç içidir.** `--workers 2`'de her worker kendi kesicisini işletir — "koruma
  amaçlı sinyal için yeterli", `health.py`'nin süreç-içi sayaçlarıyla aynı gerekçe.
- **Yarı-açık davranış:** açık süre dolunca çağrılara izin verilir ama sayaç sıfırlanmaz —
  ilk 429/503 kesiciyi anında yeniden açar; yalnız **başarılı** bir çağrı sayacı sıfırlayıp
  kesiciyi tam kapatır.

Kesici kontrolü yalnız **girişte** yapılır: çağrı başladıktan sonra kesici açılsa da eldeki
retry döngüsü kendi bütçesiyle sürer; kesicinin amacı yeni çağrıların yığılmasını önlemektir
(`analyzer.py:106-108`).

### Sağlık sözleşmesi

`health.record_gemini_error()` **yalnız nihai başarısızlıkta** çağrılır; atlatılan geçici
hatalar sayılmaz (`analyzer.py:97-98`). Bu sayaç `/healthz`'in `degraded` kararını besler.
Log sözleşmesiyle uyumlu: nihai ERROR'u çağıranın handler'ı üretir, retry katmanı WARNING
bırakır (`analyzer.py:93-95`).

### Model adları

| Kullanım | Env | Not |
| --- | --- | --- |
| Ana belge analizi | `GEMINI_MODEL_NAME` | `analyzer.py` |
| Otonom dava açma (intake) | `GEMINI_INTAKE_MODEL` | `case_intake_analyzer.py`; `_gemini_call_with_retry(model=...)` ile geçirilir (`analyzer.py:101`) |

## 2. Microsoft Graph / SharePoint

İki modül: `backend/sharepoint/auth_graph.py` (app-only token) ve
`backend/sharepoint/sharepoint_uploader_graph.py` (drive işlemleri). Kimlik `msal==1.37.0`
ile client-credentials akışıdır. **İki config, iki kimlik, iki site** vardır (G147, 2026-09-08);
önceki anlatım (bir site, bir kimlik seti) artık geçerli değildir — aşağıda.

### İki config: `default` (arşiv) ve `teslim` (veri teslim hattı) — G147

`config_type` uzayı `"default" | "teslim"` (`auth_graph.py:25-27`; tanınmayan ad `ValueError`,
`:130-131`). Her config'in kendi env seti, kendi MSAL uygulaması (ayrı token cache:
`_MSAL_APPS[config_type]`, `:16`, `:158`) ve kendi site/drive çözümü vardır:

| | `default` — arşiv (LexisBio tenant'ı) | `teslim` — veri teslim hattı (Hanyaloğlu tenant'ı) |
| --- | --- | --- |
| Kimlik env'leri | `SHAREPOINT_TENANT_ID` / `SHAREPOINT_CLIENT_ID` / `SHAREPOINT_CLIENT_SECRET` | `TESLIM_SHAREPOINT_TENANT_ID` / `TESLIM_SHAREPOINT_CLIENT_ID` / `TESLIM_SHAREPOINT_CLIENT_SECRET` (önek tablosu `_ENV_PREFIX`, `auth_graph.py:29`) |
| Secret okuma sırası | önce `vault.get_secret`, sonra env (`_read_credentials`, `:101-115`) | aynı; tenant ya da client boşsa secret HİÇ aranmaz — vault'un sahte "Secret not found" uyarısı olmasın (`:104-105`, `:111`) |
| Site | `SHAREPOINT_SITE_URL` | `TESLIM_SHAREPOINT_SITE_URL`, boşsa `SHAREPOINT_SITE_URL` (`_site_url_for`, `sharepoint_uploader_graph.py:27-32`) |
| Drive (belge kütüphanesi) adı | `SP_DRIVE_NAME`, boşsa `Belgeler` | `TESLIM_SP_DRIVE_NAME` > `SP_DRIVE_NAME` > `Belgeler` (`_drive_name_for`, `:35-40`; boş dize tanımsız sayılır) |
| Secret bitiş izleme | `SHAREPOINT_CLIENT_SECRET_EXPIRES_AT` | `TESLIM_SHAREPOINT_CLIENT_SECRET_EXPIRES_AT` (`auth_graph.py:39`; lifespan ikinci çağrı `api.py:133`) |
| `.env` şablonu | `.env.example:9-17` | `.env.example:31-48` (tamamı yorumlu — isteğe bağlı) |

**Düşüş kuralı:** `teslim` üçlüsünden (tenant / client / secret) biri bile boşsa `teslim`
config'i **default kimlik setiyle** kurulur ve süreç başına BİR KEZ INFO basılır ("Veri teslim
SharePoint kimliği tanımsız … arşiv kimliği kullanılıyor", `auth_graph.py:136-143`); site için
aynı kural `TESLIM_SHAREPOINT_SITE_URL` boşken işler. Yani `TESLIM_*` tanımsız bir `.env`'de
davranış G147 öncesiyle aynıdır, hiçbir yerde istisna yoktur. Düşüşte bile `_MSAL_APPS["teslim"]`
ayrı bir app nesnesidir (ayrı token cache) — `force_refresh` yolu config'e sadık kalsın diye
(`:121-125`).

**Site/drive cache'i:** `_get_site_and_drive_id(token, config_type)` `@lru_cache(maxsize=4)`,
anahtar `(token, config_type)` (`sharepoint_uploader_graph.py:145-146`). Token'ın anahtarda
olması bilinçli: token ~saatte bir döndüğünde kayıt kendiliğinden tazelenir (bedava TTL) ve 401
sonrası zorla yenilenen token yeni anahtar üretir; `maxsize=1` iki config art arda koşunca
(outbox upload + gece gözcüsü) her geçişte site+drive'ı yeniden çözerdi (2 Graph GET)
(`:150-156`). `_with_fresh_token_on_401(fn, config_type)` token'ı verilen config'le alır ve ilk
401'de **aynı** config'i zorla yeniler (`:125-142`).

**Hangi çağrı hangi config'le gider** — imzalarda varsayılan her yerde `"default"`
(`list_folder_children` / `download_file_from_sharepoint` / `upload_file_to_sharepoint`
keyword-only `config_type`, `:395-403`, `:453-455`, `:483`); `teslim` tarafı tek sabitten
beslenir (`teslim_kutusu.TESLIM_SP_CONFIG = _spu.CONFIG_TESLIM`, `services/teslim_kutusu.py:174-178`):

| Çağrı | Config | Kod |
| --- | --- | --- |
| Outbox upload (belge arşivi) | `default` | `services/upload_queue.py:275-276` (`config_type` verilmez) |
| Belge indirme (UI / hukukbot export), dönüşüm retry, pipeline ham/işlenmiş upload, DB yedeği | `default` | `routes/documents.py:312,415`, `routes/export.py:252`, `services/conversion_retry.py:210`, `services/document_pipeline.py:243,308`, `scripts/upload_db_backup.py:32` |
| E-posta (`/sendMail`), günlük aktivite raporu | `default` | `email_sender.py:147`, `managers/activity_manager.py:244` (`get_graph_token()` parametresiz) |
| Ofis-no sayacı (SharePoint liste öğesi) | `default` | `managers/counter_manager.py:189-190`, `:239-240` (`_get_site_and_drive_id(token)` konumsal) |
| Onarım scripti | `default` (açık) | `scripts/repair_overwritten_documents.py:68-77` |
| Gözcü: teslim klasörü listeleme + indirme | `teslim` | `services/teslim_kutusu.py:1274`, `:1287` |
| Cevap paketi yükleme | `teslim` | `services/teslim_cevap.py:529-532` |

Tenant GUID'leri kodda değil `.env`'dedir; hangi tenant'ın hangisi olduğu ve giriş tenant
listesiyle (`ALLOWED_TENANTS`) ilişkisi [`kimlik-ve-token.md` §4](kimlik-ve-token.md)'te.
Tüketici tarafı (gözcü, cevap paketi, prod kurulum sırası)
[`veri-teslim-hatti.md`](veri-teslim-hatti.md) §1 "Site/kimlik" ve §9'da.

### İki katmanlı retry

Mimari uploader'ın başında yazılıdır (`sharepoint_uploader_graph.py:42-48`):

- **İç katman** (bu modül, saniyeler): `urllib3.Retry` — 429/5xx ve bağlantı hatalarında
  aynı yükleme denemesi içinde kısa tekrarlar. `total=3`, `backoff_factor=1` (1-2-4 sn),
  `status_forcelist = (429, 500, 502, 503, 504)` (`:55`, `:86-96`).
- **Dış katman** (`services/upload_queue.py`, dakika–saat): outbox backoff, `MAX_ATTEMPTS = 8`.

İç bütçenin küçük tutulması bilinçli: outbox worker'ı tek thread ve satırları seri işliyor;
uzun kesintiyi dış katman karşılar.

`allowed_methods` açıkça `{GET, HEAD, PUT, POST, PATCH}` verilir — urllib3 2.x varsayılanı
idempotent-güvenli küçük kümedir (PUT/POST/PATCH yok) ve açıkça izin verilmezse upload'lar
hiç retry görmezdi (`:91-93`). 429/503'te Graph'ın `Retry-After` başlığına uyulur
(`:94-95`).

> **DİKKAT** (`sharepoint_uploader_graph.py:50-54`): Retry PUT/POST/PATCH'i de kapsar; bu
> modüldeki çağrılar idempotent olduğu için güvenlidir (içerik PUT'u,
> `createUploadSession` `conflictBehavior=replace`, metadata PATCH alan set'i).
> **`sendMail` / SharePoint liste-item POST'u gibi idempotent OLMAYAN Graph çağrıları bu
> session'ı KULLANMAMALIDIR** (çift e-posta / çift kayıt riski) — onlar kendi modüllerinde
> düz `requests` ile kalır.

### Büyük dosya yükleme

| Sabit | Değer | Satır |
| --- | --- | --- |
| `_SMALL_FILE_LIMIT` | 4 MiB — altında tek PUT, üstünde chunk'lı upload session | `:56` |
| `_CHUNK_SIZE` | 5 MiB = 16 × 320 KiB (Graph parça hizalama kuralı) | `:57` |
| `_CHUNK_RESUME_BUDGET` | 3 — yükleme başına `nextExpectedRanges` ile devam hakkı | `:58` |

`SSL_CERT_FILE` env'i tanımlıysa ve dosya varsa doğrulama sertifikası olarak kullanılır
(`:78-83`) — lokal geliştirmede AVG gibi TLS araya giren yazılımların çözümü budur.

### Klasörler

Arşiv klasör adları env'den gelir: ham belgeler `SHAREPOINT_FOLDER_HAM_NAME`
(`01_HAM_ARSIV`), işlenmiş kopyalar ve teknik/veritabanı yedekleri
`SHAREPOINT_FOLDER_ISLENMIS_NAME` (`02_YEDEK_ARSIV`), veri ekibinin teslim paketleri
`SHAREPOINT_FOLDER_TESLIM_NAME` (`03_VERI_TESLIM`; `gelen/` okunur, `cevap/<teslim>/`
yazılır — `.env.example:27-29`). **Teslim klasörü arşivle aynı site'ta DEĞİLDİR** (G147):
`03_VERI_TESLIM` `teslim` config'inin site'ında (Hanyaloğlu tenant'ı, `TESLIM_SHAREPOINT_SITE_URL`)
yaşar; klasör adı ve `gelen`/`cevap` yolu site'tan bağımsızdır, `TESLIM_*` tanımsızsa aynı ad
arşiv site'ında aranır (düşüş kuralı, yukarıda). Ofis numarası sayacı arşiv site'ındaki bir
SharePoint liste öğesinde tutulur ve `managers/counter_manager.py` üzerinden ETag'li güncellenir
(`default` config; teslim site'ında sayaç/`log` listesi YOKTUR ve gerekmez).

### Klasör listeleme — `list_folder_children`

Uploader'daki tek listeleme çağrısı, G109 teslim gözcüsü için (`sharepoint_uploader_graph.py:483-518`):
`GET /drives/{drive}/root:/{folder}:/children` — `$select=id,name,size,eTag,file,lastModifiedDateTime`,
`$top=200` (Graph tavanı, `:477-480`), `@odata.nextLink` sonuna kadar izlenir (nextLink'te
`params=None` — bağlantı parametreleri kendi taşır), yalnız `file` anahtarlı öğeler döner
(alt klasörler elenir). **404 → boş liste + WARNING**: "klasör henüz açılmadı" kurulum
eksiğidir, gece job'ı ERROR basmasın; diğer HTTP hataları yükselir. Ortak session (transport
retry) + `_with_fresh_token_on_401` kullanır; gözcü `config_type="teslim"` ile çağırır
(`services/teslim_kutusu.py:1274`). Tüketicisi ve eTag'li ucuz eleme
[`veri-teslim-hatti.md`](veri-teslim-hatti.md) §2'de.

## 3. E-posta

`backend/email_sender.py` Microsoft Graph `/sendMail` kullanır (SMTP değil). Gönderen
`EMAIL_SENDER` env'inden gelir; `EMAIL_ENABLED` bir kill-switch'tir.

Ek boyut limitleri `settings.email_max_single_mb` / `email_max_total_mb` = 3 MB'dır; sınırın
gerekçesi ayar dosyasında yazılı: Graph `/sendMail` gövdesinin ~4 MB tavanı ve base64
şişmesi (`config/settings.py:80-83`). Limiti aşan ek yerine arşiv referansı gönderilir.

## 4. Sistem araçları (konteyner içi)

`backend/Dockerfile` (`python:3.12-slim` üzerine, `:11-17`):

| Paket | Ne için |
| --- | --- |
| `ghostscript` | PDF → PDF/A-2b dönüşümü |
| `libreoffice-writer`, `libreoffice-calc` | Word/Excel → PDF (headless `soffice`) |
| `fonts-liberation` | Office belgelerinde Calibri/Times metrik uyumu (`Dockerfile:10`) |
| `fonts-dejavu-core` | genel font desteği |

Dönüşüm eşzamanlılığı semaforlarla sınırlıdır ve zaman tavanları
`gs_timeout_seconds` (240) / `libreoffice_timeout_seconds` (120) ile verilir; ikisi de
istek yolunda **kalan bütçeyle kırpılır** (`config/settings.py:57-59`). Semafor sayıları
`settings.py`'ye bilinçli taşınmamıştır — 2026-07-29 OOM kararının politika sabitleridir
(`settings.py:25-27`).

## 5. Python bağımlılıkları

Tümü **tam sürüme sabitlenmiştir** (`backend/requirements.txt`). Ana kalemler:

| Paket | Sürüm | Rol |
| --- | --- | --- |
| `fastapi` / `uvicorn` | 0.141.1 / 0.38.0 | web çerçevesi + ASGI sunucu |
| `google-genai` | 2.11.0 | Gemini |
| `msal` | 1.37.0 | Graph app-only kimlik |
| `sqlalchemy` / `psycopg2-binary` | 2.0.25 / 2.9.9 | ORM + PostgreSQL sürücüsü |
| `pydantic` / `pydantic-settings` | 2.12.5 / 2.11.0 | şema + ayar yükleme |
| `pymupdf` | 1.26.7 | PDF metin çıkarma |
| `Pillow` | 12.3.0 | görüntü işleme |
| `slowapi` | 0.1.9 | hız sınırı |
| `apscheduler` | 3.10.4 | zamanlanmış işler |
| `PyJWT` / `cryptography` | 2.13.0 / 50.0.0 | Azure AD token doğrulama |
| `keyring` / `keyrings.alt` | 25.7.0 / 5.0.0 | vault (Windows Credential Manager) |
| `defusedxml` | 0.7.1 | güvenli XML ayrıştırma |
| `reportlab` / `openpyxl` / `flashtext` | 4.2.5 / 3.1.5 / 2.7 | PDF üretimi, Excel, hızlı anahtar kelime araması |

Geliştirme araçları (`pytest`, `httpx`, `ruff`, `mypy`) `backend/requirements-dev.txt`'tedir
ve **prod imajına girmez**.

## 6. Belge türü kodları — normalize etmeden karşılaştırma yapma

Belge türü kodları `_` ile pad'lidir (örn. `TEBLIGAT______`, `backend/constants.py`).
Karşılaştırmadan önce `file_utils._normalize_doctype_code` ile normalize edilmelidir; ham
`==`/`in` kısaltma sızdırır. Hukukbot export allowlist'i bu yüzden normalize eder
(`services/export_publisher.py:67-69`).

## 7. Ayarların tek evi

Tüm limit ve zaman tavanları `backend/config/settings.py`'dedir; tam tablo
[`belge-isleme-hatti.md` §5](belge-isleme-hatti.md#5-zaman-bütçeleri)'te.

İki kural: pydantic-settings'in **kendi `.env` okuması bilinçli KAPALI** — host'ta koşan
testler geliştiricinin `.env`'inden değer kapmasın (konteynerde compose enjekte ettiği için
fark yaratmaz, `settings.py:14-16`). Ve **toleranslı ayrıştırma**: bozuk env değeri
uygulamayı düşürmez, WARNING loglanıp alan varsayılanına düşülür — "settings import'u asla
patlamamalı" (`settings.py:17-20`, `:100-117`).
