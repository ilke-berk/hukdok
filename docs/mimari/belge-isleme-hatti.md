# Belge işleme hattı — `/process` → `/confirm` → arşiv → hukukbot

> **Son doğrulama: 2026-08-11 · 2eade56**
> Her iddia koddan doğrulanmıştır. Kod ile çelişirse kod haklıdır — bu dosyayı düzelt.

## 1. `/process` — analiz akışı

`backend/routes/processing.py` altındaki `/process` bir dosya (`file`) ve isteğe bağlı
`belge_turu_kodu` alır, `application/x-ndjson` **stream** döndürür. Analiz
`analyzer.analyze_file_generator` içinde yürür; her adım bir JSON satırı yayınlar.

İstek başına yapılan iki yan iş:

- Her `/process` çağrısında bayat PROCESS_CACHE girdileri süpürülür — disk taraması +
  payload silme olduğu için executor'a atılır (`processing.py:431-433`).
- Ofis dosya numarası **paralel bir task** olarak SharePoint sayacından tahsis edilir
  (aşağıda §6).

### Olay sözleşmesi (frontend ile ORTAK referans)

Olaylar `{"status": ...}` taşır: `info`, `warning`, `error`, `complete`, `failed`.

Nihai başarısızlık sözleşmesi `analyzer.py::_failed_event` docstring'inde tanımlıdır ve
**birebir** uyulur (`backend/analyzer.py:368-399`):

```
{"status": "failed",
 "error_ozet": "<kullanıcıya gösterilecek Türkçe mesaj>",
 "error_kod": "<etiket>"}
```

`error_kod` etiketleri:

| Etiket | Anlamı |
| --- | --- |
| `gemini_saturated` | devre kesici açık / 429 / 5xx (servis doygun) |
| `gemini_blocked` | güvenlik/gizlilik filtresi |
| `gemini_truncated` | uzunluk sınırı (MAX_TOKENS) nedeniyle kesik yanıt |
| `schema_invalid` | çıktı ayrıştırıldı ama YAPISI şemaya uymuyor (bkz. `schemas_process`) |
| `pdf_page_limit` | belge `MAX_PDF_PAGES` sınırını aşıyor (`_step_decide_mode`, `pdf_utils.PdfPageLimitError`) |
| `analysis_error` | diğer tüm nihai başarısızlıklar |

Sözleşmenin üç kuralı, docstring'den:

- **Etiket uzayı KAPALI değildir** — ileride yeni etiket eklenebilir; tüketiciler
  tanımadıkları etiketi `analysis_error` gibi ele almalıdır. Frontend bunu
  `msg.error_kod || "analysis_error"` ile uygular (`frontend/src/lib/analyzeDocument.ts`).
- **`failed` SON olaydır**: ardından `complete` GELMEZ ve olay `process_id` TAŞIMAZ —
  confirm adımı yoktur, PROCESS_CACHE yazılmaz.
- Bu olayın üretilmesi **yeni bir ERROR log satırı EKLEMEZ**; nihai ERROR'lar çağıran
  handler'da yazılır, deneme-düzeyi hatalar WARNING kalır (log sözleşmesi). İki ön-koşul
  yolu (API anahtarı yok / dosya kaybolmuş) nihai başarısızlıkta **bilerek WARNING**
  loglar — operatör ya da kullanıcı kaynaklı, alarm hijyeni için ERROR'a yükseltilmez.

Başarılı akışın terminal olayı `complete`'tir ve `process_id` **taşır** — `/confirm` bu
kimlikle çağrılır.

Route'un **beklenmedik** istisnasında üretilen `{"status": "error", "message": ...}` olayı
bu sözleşmenin dışındadır ve aynen korunur (`analyzer.py:396-397`). `analyzer.py` içinde
akışı nihai sonlandıran `status:"error"` yield'i **kalmadı** — mod kararının üç hata yolu
(zaman aşımı, sayfa limiti, diğer `ValueError`) da `failed` üretir.

Karar kaydı: [`004-failed-olay-sozlesmesi.md`](../kararlar/004-failed-olay-sozlesmesi.md).

## 2. PROCESS_CACHE — disk destekli, diskten lazy okuma

`/process`'te kabul edilen dosya `/confirm`'e kadar PROCESS_CACHE'te yaşar. Cache
`managers/ttl_cache.py`'deki `DiskTTLCache`'tir ve **bellekte state tutmaz**: her girdi bir
`<dir>/<key>.json` meta dosyasıdır, her işlem diski okur (`ttl_cache.py:82-93`).

Gerekçe docstring'de: uvicorn `--workers N`'de worker'lar arası paylaşım ve restart
kalıcılığı gerekiyordu; süreç-içi indeks + sidecar deseni "worker A evict etti, worker B
hâlâ biliyor" tipi bayatlama sorunları doğururdu. `pop()` süreçler arası atomiktir — meta
dosyası önce rastgele adlı bir claim dosyasına `os.replace` ile taşınır, yarışan iki
pop'tan yalnız biri kazanır (`ttl_cache.py:99-108`).

TTL 1800 sn'dir (`config/settings.py:89`). Boot'ta bir süpürme koşar: bayat girdiler ve
payload dosyaları temizlenir, taze girdiler restart'ı **atlatır** — özelliğin amacı budur
(`api.py:215-223`).

Karar kaydı: [`003-process-cache-disk.md`](../kararlar/003-process-cache-disk.md).

## 3. `/confirm` — onay zinciri

`/confirm` idempotent bir kapıyla başlar, sonra ağır işi yapar:

1. **İdempotency kapısı.** `services/confirm_idempotency.begin(process_id, owner)` bir
   verdikt döner: `replay` (tamamlanmış yanıt aynen döner, pipeline hiç koşmaz),
   `in_progress` (409 — "işlem sürüyor"), `proceed` (normal akış), `bypass` (DB arızası;
   pipeline korumasız koşar). Anahtar **`process_id`**'dir; gerekçesi modül docstring'inde
   yazılıdır ve [`009-confirm-idempotency-anahtari.md`](../kararlar/009-confirm-idempotency-anahtari.md)
   olarak kayıtlıdır. Kayıt DB'de yaşar (`models.ConfirmReceipt`) — süreç içi sözlük
   restart'ta ve iki worker'da kaçırırdı.
2. **Tenant + avukat doğrulaması** (`services/document_pipeline`): `linked_case_id`'nin
   sahibi doğrulanır.
3. **Dosya kabulü**: PROCESS_CACHE'ten (analiz PDF'i + orijinal ham dosya) ya da yeniden
   yüklenen dosyadan.
4. **PDF/A dönüşümü + arşiv upload kuyruğu** — executor'da, bütçeli (§5). Semafor dolarsa
   `ConversionBusyError` → **503** ("sistem meşgul"), 504'e kadar bekleyip nginx'e
   çarpmak yerine hızlı ve dürüst sinyal (`config/settings.py:76-78`).
5. **E-posta** (avukat bildirimi; isteğe bağlı müvekkil bildirimi).
6. **Dava zenginleştirme**: belge bir davaya bağlıysa `_auto_update_case_status`
   (`processing.py:152`) ve `_auto_enrich_case_data` (`processing.py:205`) çalışır;
   duruşma tarihi varsa kaydedilir.
7. **İdempotency kaydının kapatılması**: `confirm_idempotency.complete(process_id, payload)`.
   Pipeline istisna atarsa ve belge **yaratılmamışsa** kayıt `release` edilir → tekrar
   denemek serbest kalır.

## 4. Dönüşüm, `conversion_status` ve gece retry'ı

`/confirm`'de dönüşüm **tüm** yollara rağmen başarısızsa belge kaybolmaz: orijinal kendi
uzantısıyla arşive gider, kayıt `conversion_status='pending'` ile açılır ve gece job'ı
yeniden dener (`backend/models.py:508-521`).

| `conversion_status` | Anlamı |
| --- | --- |
| `NULL` | normal (dönüşüm gerekmedi ya da tamamlandı) |
| `'pending'` | gece yeniden denenecek (spool'daki orijinalden) |
| `'failed'` | denemeler tükendi; tek nihai ERROR loglanır, spool dosyası elle kurtarma için saklanır |

Kolon üçlüsü `conversion_status` / `conversion_attempts` / `conversion_spool_path`'tir.
`upload_status`'a yeni bir değer eklenmemesi bilinçli bir karardır — gerekçesi modelde
"KARAR NOTU" başlığıyla yazılıdır ve
[`008-conversion-pending-ayri-kolon.md`](../kararlar/008-conversion-pending-ayri-kolon.md)
olarak kayıtlıdır.

Gece job'ı `services/conversion_retry.py`'dir, 02:30 TR'de lider worker'da koşar
(`api.py:184-190`). En fazla `MAX_CONVERSION_ATTEMPTS = 5` deneme yapar
(`conversion_retry.py:53`); deneme sayacı dönüşümden **önce** commit edilir, böylece
zehirli bir dosya sonsuz döngü kurmaz (`upload_queue.py:206` ile aynı desen). Başarıda
PDF/A üretilir, arşive **senkron** yüklenir (outbox'a verilmez — gerekçe ADR 008'de),
statü `NULL`'lanır ve hukukbot hook'u yeniden çağrılır.

## 5. Zaman bütçeleri

Tüm limitlerin tek evi `backend/config/settings.py`'dir (pydantic-settings). İki tasarım
kuralı docstring'de: değerler **boot'ta bir kez** okunur, ve bozuk env değeri uygulamayı
düşürmez — WARNING loglanıp alan varsayılanına düşülür ("settings import'u asla
patlamamalı", `settings.py:17-20`).

| Ayar | Varsayılan | Env | Satır |
| --- | --- | --- | --- |
| `max_upload_mb` | 50 | `MAX_UPLOAD_MB` | `settings.py:47` |
| `request_size_limit_mb` | 50 | `REQUEST_SIZE_LIMIT_MB` | `:50` |
| `max_pdf_pages` | 500 | `MAX_PDF_PAGES` | `:53` |
| `pdf_parse_timeout_seconds` | 60.0 | `PDF_PARSE_TIMEOUT_SECONDS` | `:55` |
| `gs_timeout_seconds` | 240 | `GS_TIMEOUT_SECONDS` | `:59` |
| `libreoffice_timeout_seconds` | 120 | `LIBREOFFICE_TIMEOUT` \| `LIBREOFFICE_TIMEOUT_SECONDS` | `:62-67` |
| `request_time_budget_seconds` | 300.0 | `REQUEST_TIME_BUDGET_SECONDS` | `:71` |
| `confirm_conversion_budget_seconds` | 270.0 | `CONFIRM_CONVERSION_BUDGET_SECONDS` | `:75` |
| `conversion_acquire_timeout_seconds` | 30.0 | `CONVERSION_ACQUIRE_TIMEOUT_SECONDS` | `:78` |
| `email_max_single_mb` | 3 | `EMAIL_MAX_SINGLE_MB` | `:82` |
| `email_max_total_mb` | 3 | `EMAIL_MAX_TOTAL_MB` | `:83` |
| `counter_fetch_timeout_seconds` | 10.0 | `COUNTER_FETCH_TIMEOUT_SECONDS` | `:86` |
| `process_cache_ttl_seconds` | 1800 | `PROCESS_CACHE_TTL_SECONDS` | `:89` |
| `download_cache_ttl_seconds` | 3600 | `DOWNLOAD_CACHE_TTL_SECONDS` | `:90` |
| `rate_limit_default` | `"100/minute"` | `RATE_LIMIT_DEFAULT` | `:93` |
| `gemini_retry_deadline_seconds` | 170.0 | `GEMINI_RETRY_DEADLINE_SECONDS` | `:97` |
| `gemini_http_timeout_ms` | 120000 | `GEMINI_HTTP_TIMEOUT_MS` | `:98` |

### 300 saniye hizası

`request_time_budget_seconds = 300` bir çıpadır: **nginx'in (host + konteyner)
`proxy_read_timeout` penceresi** (`settings.py:70-71`, `nginx.conf:13`). İki bütçe bu
pencereye sığmak zorundadır ve ikisi de kodda yorumla kilitlenmiştir:

- `/confirm` dönüşüm zinciri **270** sn — LO + GS + semafor beklemeleri bu bütçeden pay
  alır, kalan ~30 sn DB/kuyruk/e-posta/yanıta bırakılır. Bekçi testi: `bütçe + 30 ≤
  request_time_budget` (`settings.py:72-75`).
- Gemini retry penceresi **170** sn; tek deneme HTTP tavanı 120 sn → 170 + 120 = 290 < 300
  (`settings.py:96-97`).

`settings.py`'ye bilinçli **taşınmayanlar** da docstring'de listelidir: görüntü boyut
korumaları (`MAX_IMAGE_*`, 2026-07-29 OOM kararı), dönüşüm semafor sayıları, retry/backoff
sabitleri, DB timeout env'leri, cache dizin env'leri, confirm idempotency eşikleri ve
upload_queue backoff merdiveni — bunlar "limit değil, başka paketlerin politika sabitleri"
(`settings.py:25-32`).

## 6. Ofis dosya numarası — atomik tahsis

Numara `/process` sırasında `managers/counter_manager.py::reserve_next_counter` ile
SharePoint sayacından **atomik** tahsis edilir: oku + artır + döndür tek işlemde,
ETag/`If-Match` ile optimistic concurrency. 412 (başka kullanıcı önce davrandı) alınırsa
yeni değer okunup jitter'lı backoff ile tekrar denenir. "Dönen numara BU çağrıya aittir —
eşzamanlı iki çağrı asla aynı numarayı alamaz" (`counter_manager.py:216-231`).

Sabitler: `RESERVE_MAX_ATTEMPTS = 4`, backoff tabanı 0.3 sn, tavan 2.0 sn, jitter 0.2 sn
(`counter_manager.py:46-49`). Tüm denemeler 412 ile tükenirse **tek** ERROR loglanır — ara
çakışmalar WARNING'dir (log sözleşmesi, `counter_manager.py:304-312`).

İstek yolunda tahsis `counter_fetch_timeout_seconds` (10 sn) ile sınırlıdır. Timeout'ta
`"TIMEOUT___"` sentinel'i döner; arkadaki thread tahsisi bitirebileceği için **numara
atlanır**. Bu bilinçli bir takastır: "mükerrere tercih edilir"
(`processing.py:440-461`).

## 7. SharePoint upload outbox

Arşiv yüklemeleri `services/upload_queue.py`'deki kalıcı outbox üzerinden gider. Tek worker
thread satırları sırayla işler; geçici hatada üstel backoff ile yeniden dener, denemeler
tükenince satır nihai `failed` olur. Açılıştaki ilk tarama **startup reconcile**'dır —
önceki süreçten kalan pending satırları toparlar (`upload_queue.py:1-20`).

- Backoff merdiveni: `(60, 300, 900, 3600, 3h, 6h, 12h)` saniye (`upload_queue.py:53`)
- `MAX_ATTEMPTS = 8` (`:54`), poll aralığı 60 sn (`:58`)

Worker **yalnız lider worker'da** başlar (`api.py:206-213`) — her worker kendi thread'ini
açarsa aynı satır N kez yüklenir. Karar kaydı:
[`005-upload-outbox-tek-worker.md`](../kararlar/005-upload-outbox-tek-worker.md).

Başarıda `sharepoint_url` DB'ye yazılır ve hukukbot hook'u tetiklenir.

## 8. Hukukbot'a aktarım

`services/export_publisher.notify_hukukbot` iki adımdır (`export_publisher.py:1-23`):

1. **`enqueue_document`** — belge filtrelerden geçiyorsa `export_outbox`'a `pending` satır
   açar. Satırın yalnız bu anda açılması bilinçlidir: "outbox id sırası = aktarılabilirlik
   sırası, async upload yarışı yok".
2. **`publish_webhook`** — hukukbot'a POST atar (`WEBHOOK_RETRIES = 3`, backoff `(2, 4)` sn,
   timeout 60 sn — `export_publisher.py:31-33`).

Webhook'un ulaşamaması **sorun değildir**: satır pending kalır, hukukbot'un periyodik
reconcile'ı toparlar. Docstring'in kendi cümlesi: "Webhook yalnızca gecikmeyi sıfırlar,
doğruluk garantisi outbox + reconcile'dadır" (`export_publisher.py:12-15`).

Filtreler (`export_publisher.py:54-70`), hepsi `and` ile:

| Filtre | Gerekçe |
| --- | --- |
| `link_mode != "TEST"` | test belgeleri aktarılmaz |
| `sharepoint_url` dolu | arşivlenmemiş belge aktarılmaz |
| `conversion_status is None` | dönüşüm bekleyen/başarısız belgede arşivde PDF değil orijinal (ör. `.udf`) durur; hukukbot'un PDF ingest'i düşer — "140+ belgelik failed birikimi vakasının önlemi" (`:56-59`) |
| dava silinmemiş | silinmiş davanın belgesi outbox'a hiç girmez; dava restore edilirse belgeleri tekrar akabilir (filtre dinamik) (`:62-64`) |
| tür allowlist'te | `_normalize_doctype_code` ile **normalize edilerek** karşılaştırılır (`:67-69`) |

Son satır kritiktir: belge türü kodları `_` ile pad'lidir (örn. `TEBLIGAT______`,
`backend/constants.py`); ham `==`/`in` karşılaştırması kısaltma sızdırır. Bkz.
[`dis-bagimliliklar.md`](dis-bagimliliklar.md).

Buradaki hiçbir hata yukarı fırlatılmaz — "arşivleme hattı hukukbot entegrasyonu yüzünden
ASLA devrilmemeli" (`export_publisher.py:21-22`).

Hukukbot'un okuduğu `/export` uçları public'e açılmaz; bkz.
[`010-export-nginxe-acilmaz.md`](../kararlar/010-export-nginxe-acilmaz.md) ve yaşayan spec
[`docs/hukukbot-aktarim/`](../hukukbot-aktarim/).
