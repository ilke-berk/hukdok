# Belge işleme hattı — `/process` → `/confirm` → arşiv → hukukbot

> **Son doğrulama: 2026-08-11 · 2eade56**
> Her iddia koddan doğrulanmıştır. Kod ile çelişirse kod haklıdır — bu dosyayı düzelt.

## 1. `/process` — analiz akışı

`backend/routes/processing.py` altındaki `/process` bir dosya (`file`) ve isteğe bağlı
`belge_turu_kodu` alır, `application/x-ndjson` **stream** döndürür. Analiz
`analyzer.analyze_file_generator` içinde yürür; her adım bir JSON satırı yayınlar.

İstek başına yapılan tek yan iş:

- Her `/process` çağrısında bayat PROCESS_CACHE girdileri süpürülür — disk taraması +
  payload silme olduğu için executor'a atılır (`processing.py::analyze_file_endpoint`).

`/process` analiz sırasında SharePoint'e (Graph) **çıkmaz** (aşağıda §6).

### Dizin kaydı eksik UDF (30.09.2026 olayı)

UYAP bazen ZIP dizin kaydı (central directory) yazılmamış `.udf` verir: `content.xml` ve
`sign.sgn` tamdır, dosya son girişin bitiminde biter. `zipfile` dizini sondan okuduğu için
`BadZipFile` verir; eskiden bu dosya `/process`'te 400 ile reddediliyordu. Yedek yol
`backend/udf_zip.py::read_entry_sequential` yerel giriş başlıklarını baştan sırayla okur ve
girişi CRC'siyle doğrular; yalnız `zipfile` başarısız olunca ve yalnız `.udf` için çağrılır
(`file_utils._validate_zip_marker` → kabul + WARNING; `udf_converter._parse_xml` → PDF dönüşümü).
Dosya **onarılmaz**: ham `.udf` arşive UYAP'tan geldiği baytlarla gider. Akışı yarıda kesilmiş
ya da CRC'si tutmayan dosya yine 400 alır. Bekçi `backend/tests/test_udf_zip.py`.

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
`<dir>/<key>.json` meta dosyasıdır, her işlem diski okur (`managers/ttl_cache.py:97-98`).

Gerekçe docstring'de: uvicorn `--workers N`'de worker'lar arası paylaşım ve restart
kalıcılığı gerekiyordu; süreç-içi indeks + sidecar deseni "worker A evict etti, worker B
hâlâ biliyor" tipi bayatlama sorunları doğururdu. `pop()` süreçler arası atomiktir — meta
dosyası önce rastgele adlı bir claim dosyasına `os.replace` ile taşınır, yarışan iki
pop'tan yalnız biri kazanır (`managers/ttl_cache.py:106-109`).

TTL 1800 sn'dir (`config/settings.py:86`). Boot'ta bir süpürme koşar: bayat girdiler ve
payload dosyaları temizlenir, taze girdiler restart'ı **atlatır** — özelliğin amacı budur
(`api.py:210-218`).

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
   sahibi doğrulanır ve belgenin avukatı davanın sorumlu avukatından **`lawyers.id`** olarak
   çözülür (G226, 27.09): `validate_tenant_and_resolve_lawyer(linked_case_id, user)` →
   `resolve_case_lawyer_id` → `lawyer_id_for_text` (`document_pipeline.py:141-202`).
   Eşleme `managers/lawyer_resolver` ile TOLERANSLIDIR ("TUGCE UNGOR" ↔ "Tuğçe Ungör Yanık",
   ünvan, Türkçe harf katlama, kod metni; çoklu değerde ilk çözülen parça; pasif avukat da
   çözülür); eski yol config'teki ada birebir eşleyip farklı yazımda belgeyi avukatsız
   bırakıyordu. Çözülemezse `lawyer_id=NULL`, akış sürer. Davasız belge avukatsızdır —
   `/confirm`'ün `avukat_kodu` Form alanı kalktı (hiçbir istemci göndermiyordu). Belge kaydı
   `case_documents.lawyer_id`'yi yazar (FK `lawyers.id` **ON DELETE RESTRICT**, migrasyon
   madde 55 + koşulsuz `idx_case_documents_lawyer_id`); `avukat_kodu` salt okunur geçiş
   kolonudur, yeni kayıtta yazılmaz, G231 kaldırır. Aynı `lawyer_id` dönüşüm kuyruğuna
   (`convert_pdfa_and_queue_uploads` / conversion_pending kaydı), avukat e-postasına ve
   intake arşivine (`case_intake._archive_intake_documents`, commit + apply) taşınır;
   e-postadaki avukat adı ve müvekkil bilgilendirmesinin alıcı adresi `lawyers` satırından
   okunur (`document_pipeline.lawyer_contact`). Eski belgeler
   `scripts/belge_avukat_bagi.py` ile bağlanır: kuru koşu varsayılan, `--apply`; yalnız
   `lawyer_id` boş + `avukat_kodu` dolu satırlar, kod `lawyers.code`'a birebir, listeden
   çıkmış eski kodlar sabit haritayla (`TUY→TUGCEUNG`, `BYU→BBA`, `AGH→AYSEGULH`);
   eşleşmeyen raporlanır, `avukat_kodu`'ya dokunulmaz, idempotent; aynı transaction'da avukat
   envanteri (G224) önce/sonra ölçülür, İHLAL varsa commit edilmez.
3. **Dosya kabulü**: PROCESS_CACHE'ten (analiz PDF'i + orijinal ham dosya) ya da yeniden
   yüklenen dosyadan.
4. **PDF/A dönüşümü + arşiv upload kuyruğu** — executor'da, bütçeli (§5). Semafor dolarsa
   `ConversionBusyError` → **503** ("sistem meşgul"), 504'e kadar bekleyip nginx'e
   çarpmak yerine hızlı ve dürüst sinyal (`config/settings.py:76-78`).
5. **E-posta** (avukat bildirimi; isteğe bağlı müvekkil bildirimi). Müvekkil
   bilgilendirmesi ("[Müvekkil Bilgilendirme]" konulu, sorumlu avukata giden ayrı mail)
   üç şarta bağlıdır: ana avukat maili gönderiliyor (`send_email`) + kullanıcı istedi
   (`send_client_notice`) + **yönetici ana anahtarı açık**
   (`email_sender.should_notify_client` → `services/app_settings.client_notice_enabled`,
   varsayılan KAPALI, yönetim paneli > Özellikler'den açılır). Asıl kapı sunucudadır:
   arayüz kutuyu göstermese de bayat/elle `send_client_notice=true` isteği anahtarı
   aşamaz; kapalıyken sonuç `client_notice: "Atlandı (özellik yönetici panelinden
   kapalı)"` olur (`routes/processing.py` confirm bloğu). Ek dosyalar
   (`extra_attachment_files`) YALNIZ `send_email` doğruyken doğrulanıp temp'e alınır
   (`document_pipeline.save_extra_attachments`); e-posta ön-kontrolü düşerse orada
   temizlenir — temizlik eskiden yalnız `send_email_sync` finally'sindeydi, `send_email=false`
   ile gelen ek temp dosyası sızdırıyordu (20.09.2026).
6. **Dava zenginleştirme**: belge bir davaya bağlıysa `_auto_update_case_status`
   (`processing.py:246`) ve `_auto_enrich_case_data(case_id, karsi_taraf, uploaded_by)`
   (`processing.py:300`; yalnız karşı taraf — avukat dalı G226'da kalktı, belgenin avukatı
   zaten davanın sorumlusundan çözüldüğü için hiç tetiklenemeyen bir no-op'tu; "A; B" metni
   kişi başına satıra bölünür, kartta başka türde duran kişi yeniden yazılmaz — 03.10) çalışır;
   duruşma tarihi varsa kaydedilir.
7. **İdempotency kaydının kapatılması**: `confirm_idempotency.complete(process_id, payload)`.
   Pipeline istisna atarsa ve belge **yaratılmamışsa** kayıt `release` edilir → tekrar
   denemek serbest kalır.

### Toplu yüklemede ek bağlama (tebligat dilekçesi + mazbata, 20.09.2026)

Tebligat pratikte iki dosya gelir: karşı tarafın dilekçesi + tebliğ mazbatası. Avukat
dilekçeyi sorumlu avukata mail atarken mazbatanın AYNI mailin eki olmasını ister (süre
hesabı mazbatadaki tebliğ tarihine dayanır). Kullanıcı kararı: ek satır hem kendi belgesi
olarak arşivlenir hem ana satırın mailine ek olur; toplu akışta e-postası açık tebligat
satırında ve bağlı eki olan satırda e-posta penceresi otomatik açılır.

- **Tezgâh** (`frontend/src/components/BulkUploadWorkbench.tsx`, "Eki olduğu belge"
  sütunu): satır `attachTo` ile başka satırın eki olur. Görsel düzen ağaç gibidir: ek satır
  ana belgenin hemen altında girintili ("↳", `data-attach-to`), numara yalnız ana belgelerde,
  ek satırda seçici yerine "Ayır" düğmesi (kullanıcı kararı 20.09: "ek dosyanın altında ek
  gibi görünsün"). Kurallar: kendisi ve e-postası
  kapalı satırlar aday değil; ek olan satır ana olamaz, ek taşıyan satır ek olamaz (zincir
  yok); bağlanınca satırın e-posta anahtarı kapanır ve kilitlenir; ana satırın e-postası
  kapanınca ya da satır silinince bağ çözülür; toplu e-posta anahtarı kapatılınca tüm
  bağlar çözülür. "Onaya Geç" payload'ında (`BulkPrepResult.attachments`) ana satır bağlı
  satırların `File`'larını taşır, ek satır `email:false` + boş `attachments` ile gider.
- **Kuyruk** (`frontend/src/pages/Index.tsx`): dosya başına meta `Map<File, BatchFileMeta>`
  (`docType`, `email`, `extraAttachments`) — **File referansı anahtarlı**; eski dizin hizalı
  `docTypes[]`/`emailFlags[]` kuyruktan çıkarma (`handleRemoveFromQueue`) sonrası bir
  kayıyordu, bu tasarımla kapandı. `handleConfirmClick`: "her dosyada ayrıca onayla" KAPALI
  (`batchEmailConfig` dolu) iken modal atlanır, İKİ istisna dışında — `email` açık ve
  (`lib/tebligatDoctype.isTebligatDoctype(onaylanan belge_turu_kodu || tezgâh türü)` ya da
  bağlı ek var) → `EmailModal` `defaultExtraAttachments` ile önceden dolu açılır. Sessiz
  yolda ekler yalnız `send_email` doğruyken `handleFinalProcess`'e geçer.
- **Backend sözleşmesi değişmedi:** ana satırın `/confirm`'ü ekleri `extra_attachment_files`
  ile taşır (tek ana bildirim mailine `extra_temp_paths`), ek satırın `/confirm`'ü
  `send_email=false` ile ayrı `process_id`'yle gider (arşiv + SharePoint, mail yok);
  idempotency çakışması yok. Ek satır ana satırdan önce ya da sonra işlense de `File`
  bellekte olduğundan sıra önemsizdir.
- **Sınırlar:** ekler PDF/A'ya çevrilmez, yüklendiği gibi gider; e-posta boyut sınırı
  `EMAIL_MAX_SINGLE_MB`/`EMAIL_MAX_TOTAL_MB` (varsayılan 3 MB, `email_sender.py`) —
  sığmayan ek gövde notuyla SESSİZ atlanır; `extra_attachments_warning` yalnız doğrulama
  retleri (uzantı/boyut/magic-byte) içindir ve artık arayüzde toast olarak görünür. Ek
  satır kuyruktan çıkarılırsa yine mail eki olur ama arşivlenmez.
- Bekçiler: `BulkUploadWorkbench.test.tsx`, `Index.batch.test.tsx`,
  `EmailModal.defaultAttachments.test.tsx`, `lib/tebligatDoctype.test.ts`;
  backend `test_faz3_confirm_idempotency.py` (ek + `send_email` iki yön),
  `test_faz0_hardening.py` (ön-kontrol temizliği).

### Arşiv adı tekliği (2026-09-01 arızası)

Hedef ad frontend'in ürettiği `TARİH_TÜR_ESAS_KarşıTaraf.pdf` kalıbıdır ve teklik
bileşeni taşımaz; Graph yüklemeleri ise `conflictBehavior=replace` ile gider
(`sharepoint/sharepoint_uploader_graph.py`). Bu ikili, aynı davada aynı türden ve aynı
belge tarihli iki belgede (toplu yüklemede yaygın) ikinci yüklemenin birincinin dosyasını
**sessizce değiştirmesine** yol açıyordu — 2026-09-01 tespiti: 102 mükerrer ad grubu /
240 kayıt; ezilen içerik SharePoint sürüm geçmişinde kaldığı için kurtarılabilir durumda.

Koruma `services/archive_names.py`'dedir ve `convert_pdfa_and_queue_uploads` hedef adları
**kuyruğa girmeden** benzersizleştirir (tek boğaz noktası: `/confirm` + intake commit):

- **İşlenmiş arşiv** tekliği **stem** (uzantısız gövde) düzeyindedir: pending belge
  `X.udf` saklanır, gece job'ı `X.pdf`'e döner — tam-ad tekliği bu geçişte yine ezerdi.
  Ad uzayı `case_documents.stored_filename` + `upload_outbox(kind='islenmis')`'tir;
  çakışmada `_2`, `_3`... soneki üretilir.
- **HAM arşiv** adı (`yükleme-tarihi_orijinal-ad`) DB kolonu olmadığından teklik
  `upload_outbox(kind='ham')` tarihçesine karşı tam-ad eşitliğiyle denetlenir (tarih
  öneki gereği çakışma zaten aynı gün içindedir).
- **Yarış**: eşzamanlı iki `/confirm` aynı adı seçebilir; `resolve_stored_name_race`
  INSERT **sonrası** aynı stem'de en küçük id'ye adı bırakır, kaybeden satır
  deterministik `_<doc_id>` sonekini alıp DB'de yeniden adlanır — kuyruklama bu addan
  sonra yapılır.
- Nihai ad `results["stored_filename"]` ile çağırana döner; e-posta eki, indirme ve
  frontend gösterimi arşivdeki gerçek adı kullanır. Adlandırma katmanındaki her arıza
  WARNING + adayın aynen kullanılması demektir (bugünkü davranışa geri düşüş) —
  arşivlemeyi eskisinden kötü yapamaz.

Fix öncesi ezilen dosyalar `scripts/repair_overwritten_documents.py` ile sürüm
geçmişinden kurtarılır (varsayılan dry-run; `--apply` DB satırlarını yeni ada/URL'e
çevirir, `--notify-hukukbot` export edilmişleri yeniden bildirir).

## 4. Dönüşüm, `conversion_status` ve gece retry'ı

`/confirm`'de dönüşüm **tüm** yollara rağmen başarısızsa belge kaybolmaz: orijinal kendi
uzantısıyla arşive gider, kayıt `conversion_status='pending'` ile açılır ve gece job'ı
yeniden dener (`backend/models.py:616-618`).

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
(`api.py:178-185`). En fazla `MAX_CONVERSION_ATTEMPTS = 5` deneme yapar
(`conversion_retry.py:53`); deneme sayacı dönüşümden **önce** commit edilir, böylece
zehirli bir dosya sonsuz döngü kurmaz (`upload_queue.py:233-234` ile aynı desen). Başarıda
PDF/A üretilir, arşive **senkron** yüklenir (outbox'a verilmez — gerekçe ADR 008'de),
statü `NULL`'lanır ve hukukbot hook'u yeniden çağrılır. Yüklemeden önce `.pdf` adı
`archive_names.unique_islenmis_name(..., exclude_doc_id=doc)` ile denetlenir: teklik
korumasından önce açılmış eski kayıtlarla stem çakışması varsa başka belgenin dosyası
ezilmez; kendi önceki gece denemeleri çakışma sayılmaz (aynı ada yeniden yükleme kendi
dosyası için idempotenttir).

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
| `process_cache_ttl_seconds` | 1800 | `PROCESS_CACHE_TTL_SECONDS` | `:86` |
| `download_cache_ttl_seconds` | 3600 | `DOWNLOAD_CACHE_TTL_SECONDS` | `:87` |
| `rate_limit_default` | `"100/minute"` | `RATE_LIMIT_DEFAULT` | `:90` |
| `gemini_retry_deadline_seconds` | 170.0 | `GEMINI_RETRY_DEADLINE_SECONDS` | `:94` |
| `gemini_http_timeout_ms` | 120000 | `GEMINI_HTTP_TIMEOUT_MS` | `:95` |

### 300 saniye hizası

`request_time_budget_seconds = 300` bir çıpadır: **nginx'in (host + konteyner)
`proxy_read_timeout` penceresi** (`settings.py:70-71`, `nginx.conf:13`). İki bütçe bu
pencereye sığmak zorundadır ve ikisi de kodda yorumla kilitlenmiştir:

- `/confirm` dönüşüm zinciri **270** sn — LO + GS + semafor beklemeleri bu bütçeden pay
  alır, kalan ~30 sn DB/kuyruk/e-posta/yanıta bırakılır. Bekçi testi: `bütçe + 30 ≤
  request_time_budget` (`settings.py:72-75`).
- Gemini retry penceresi **170** sn; tek deneme HTTP tavanı 120 sn → 170 + 120 = 290 < 300
  (`settings.py:93-94`).

`settings.py`'ye bilinçli **taşınmayanlar** da docstring'de listelidir: görüntü boyut
korumaları (`MAX_IMAGE_*`, 2026-07-29 OOM kararı), dönüşüm semafor sayıları, retry/backoff
sabitleri, DB timeout env'leri, cache dizin env'leri, confirm idempotency eşikleri ve
upload_queue backoff merdiveni — bunlar "limit değil, başka paketlerin politika sabitleri"
(`settings.py:25-32`).

## 6. Belge sayacı — kaldırıldı (G242)

`/process` eskiden her analizde SharePoint'teki bir liste öğesinden 9 haneli bir belge
numarası tahsis ediyordu. Numara dosya adında, veritabanında, `/confirm` isteğinde ve
ekranda kullanılmadığı için sayaç bütünüyle kaldırıldı: `/process` analiz sırasında Graph'a
çıkmaz, `complete` olayı bu alanı taşımaz, benchmark sözlüklerinde sayaç anahtarı yoktur
(bekçi `backend/tests/test_g242_sayac_kalkti.py`). Stream sözleşmesi değişmedi.

Dava kartının ofis numarası (`cases.tracking_no`) bununla **ilgisizdir**: o numara
veritabanında üretilir — [`dava-acma-akisi.md`](dava-acma-akisi.md).

## 7. SharePoint upload outbox

Arşiv yüklemeleri `services/upload_queue.py`'deki kalıcı outbox üzerinden gider. Tek worker
thread satırları sırayla işler; geçici hatada üstel backoff ile yeniden dener, denemeler
tükenince satır nihai `failed` olur. Açılıştaki ilk tarama **startup reconcile**'dır —
önceki süreçten kalan pending satırları toparlar (`upload_queue.py:1-20`).

- Backoff merdiveni: `(60, 300, 900, 3600, 3h, 6h, 12h)` saniye (`upload_queue.py:57`)
- `MAX_ATTEMPTS = 8` (`:58`), poll aralığı 60 sn (`:62`)

Worker **yalnız lider worker'da** başlar (`api.py:201-204`) — her worker kendi thread'ini
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

## 9. PDF araçları tezgâhı (07.10.2026, G267-G273)

Plan ve API sözleşmesi: [`docs/plan/pdf-araclari-plani-2026-10-07.md`](../plan/pdf-araclari-plani-2026-10-07.md) §3
(uç/parametre tablosu TEK kaynaktır; değişiklik önce orada). Amaç: Acrobat yerine PDF işlerinin (birleştir, böl, sayfa
düzenle, sıkıştır, karart, damga, not) HUKDOK'ta yapılması ve sonucun tek adımda kartın belgesi olması. `/process` →
`/confirm` hattından (§1-§3) AYRI bir yoldur: analiz koşmaz, e-posta gitmez, belge türünü kullanıcı seçer.

### 9.1 Akış

```
tarayıcı /belge-tezgahi (herkese; App.tsx:126, Sidebar.tsx:51)
   ├─ yükle (multipart, tek dosya) ─▶ POST /api/pdf-araclari/yukle ──pdf_ye_cevir──▶ PDF_ARACLARI_DIR/<uuid>.pdf
   │                                   DOWNLOAD_CACHE[file_id] = {path, filename, owner, kaynak:"pdf_araclari", sayfa, sayfalar}
   ├─ işlem (JSON) ──────────────────▶ POST /api/pdf-araclari/islem  ──pdf_araclari.<islem>──▶ yeni file_id(ler) (böl: birden çok)
   ├─ önizleme ◀─PNG──────────────── GET  /api/pdf-araclari/onizleme/{file_id}/{sayfa}?genislik=64..1600 (Bearer → blob URL)
   ├─ indir ◀─dosya───────────────── GET  /api/download/{file_id}   (mevcut uç, routes/processing)
   ├─ karta bağla ───────────────────▶ POST /api/pdf-araclari/karta-bagla ─▶ KESIN: convert_pdfa_and_queue_uploads
   │                                                                        TASLAK: save_case_document + 03_TASLAKLAR/<ofis_no>/
   └─ karttan al ────────────────────▶ POST /api/pdf-araclari/karttan-al ──SharePoint indir──▶ yeni file_id
```

Katmanlar: `backend/pdf/pdf_araclari.py` (saf fonksiyonlar; HTTP bilmez, `deadline` alır, girdi dosyasını değiştirmez,
çıktı geçici ada yazılıp `os.replace`) → `backend/routes/pdf_araclari.py` (doğrulama, sahiplik, cache, semafor, hata
eşlemesi) → `services/document_pipeline` (yalnız karta bağla). Frontend: `pages/BelgeTezgahiPage.tsx` üç bölge (sol
`DosyaListesi` + yükleyici · orta `SayfaIzgarasi` ↔ `SayfaGorunumu` · sağ `IslemPaneli`), `components/pdf/**`,
istemci `lib/pdfAraclariApi.ts`, tipler `types/pdfAraclari.ts` (§3 ile birebir). nginx DEĞİŞMEDİ: her yol
`location /api` altında (`nginx.conf:119`), `proxy_read_timeout 300s` yeter (K10). `api.py:552` router kaydı.

### 9.2 Çalışma dosyası (K2)

- Her yükleme ve her işlem çıktısı sahibine bağlı bir `file_id` alır; kayıt `DOWNLOAD_CACHE`'tedir (`/process`
  indirmeleriyle aynı cache, `kaynak:"pdf_araclari"` ile ayrılır). Başkasının id'si her uçta 404 (varlık maskelenir,
  `_sahipli_kayit`, `routes/pdf_araclari.py`).
- Dosyalar `PDF_ARACLARI_DIR` (varsayılan `<backend>/data/pdf_araclari`, konteynerde backend-data volume'ü) altında
  `<uuid>.pdf`. TTL (1 saat, `download_cache_ttl_seconds`) dolunca **payload da silinir** — `processing._download_evict`
  yalnız bu kaynağın dosyasını siler (`routes/processing.py:96-101`); `/confirm` kayıtları eskisi gibi `schedule_cleanup`'a
  bırakılır. Ekranda bilgi satırı: "Dosyalar 1 saat sonra silinir".
- Zincir: bir işlemin çıktısı sonraki işlemin girdisidir; girdiler SİLİNMEZ (TTL siler), kullanıcı sol listeden kaldırınca
  istemci yalnız kendi listesinden düşürür. Sayfa yenilenince istemci listesi gider (sunucu dosyaları TTL'e dek durur).
- Yüklenen her şey hemen PDF olur (K3: `pdf_ye_cevir` — `.pdf` kopya, `.udf` → `_udf_to_pdfa2b`, resim/Office →
  `format_converter`); işlemler yalnız PDF üstünde çalışır. Çıktılar düz PDF'tir, PDF/A karta bağlanınca (K4).

### 9.3 İşlemler ve koordinat sözleşmesi

İşlem parametreleri plan §3 tablosundadır (`birlestir`, `bol` aralık/`her_n`, `sayfa_duzenle` sıra+döndür+sil, `sikistir`
Ghostscript `/screen|/ebook|/printer`, `karart`, `damga`, `not`, `donustur`). Üç kural koddan:

- **Görünür düzlem:** karartma, not ve damga koordinatları döndürme uygulanmış GÖRÜNÜR sayfa düzlemindedir (sol-üst
  orijin, PDF puanı; `Dosya.sayfalar[].genislik/yukseklik` görünür boyut). Çekirdek `page.derotation_matrix` ile açıklama
  düzlemine kendisi çevirir (`pdf_araclari.py::_gorunur_rect`); tarayıcı yalnız ölçekler — ölçek = `sayfa.genislik /
  görüntü genişliği`, ek dönüşüm yok (`components/pdf/pdfKoordinat.ts`, testi döndürülmüş 842×595 ile belgeler).
- **Karartma gerçek silmedir** (K6): `add_redact_annot` + `apply_redactions` metin VE görüntü piksellerini siler; alan
  sayfa sınırına kırpılır, boş/sayfa dışı alan 422. Ekranda alanlar dosya başına birden çok sayfada birikir, "Karart" tek
  istek atar ve onay kutusu ("Karartma geri alınamaz; metin ve görüntü kalıcı silinir") işaretlenmeden istek GİTMEZ
  (`components/pdf/KarartmaKatmani.tsx`); en küçük alan 4×4 pt.
- **Türkçe glif:** damga ve not `DejaVuSans.ttf` (`fonts-dejavu-core`, `DEJAVU_FONTFILE`) ile gömülür (K7); damga ≤ 120,
  not ≤ 2.000 karakter.

### 9.4 Karta bağlama ve karttan alma (K4, K5, K17)

- `POST /karta-bagla` gövdesi `{id, case_id, belge_turu_kodu, dosya_adi, case_party_id?, istek_kimligi, yon, durum}`;
  sıra: idempotency kapısı → sahiplik 404 → kart 404 (tenant + soft-delete) → tür 422 (`doctypes` listesi,
  `_normalize_doctype_code`, DB'ye kanonik pad'li kod) → ad 422 → taraf 422 → kayıt.
- `durum=KESIN`: MEVCUT `document_pipeline.convert_pdfa_and_queue_uploads(...)` hattı (§3-§4 ile aynı: PDF/A + ham/işlenmiş
  arşiv kuyruğu + URL commit'inde `belge_islendi` bildirimi ve Hukukbot allowlist kuralı — yeni kural YOK;
  `kaynak="PDF_ARACLARI"`, `conversion_budget_seconds=pdf_araclari_butce_saniye`). Çalışma dosyası silinmez (zincir sürer).
- `durum=TASLAK` (K12): PDF/A YOK; `save_case_document(durum="TASLAK")` + TEK `islenmis` kuyruğu
  `SHAREPOINT_FOLDER_TASLAK_NAME/<ofis_no>/` (varsayılan `03_TASLAKLAR`; ofis no'daki `/` → `-`, ayrıştırma yok). G282
  kapıları taslağı Hukukbot export'undan (`export_publisher.py:66`) ve bildirimden (`upload_queue.py:223`, `_belge_kesin_mi`) eler.
- İdempotent: `istek_kimligi` (UUID; ekranda diyalog açılışında üretilir, tekrar denemede sabit) `confirm_idempotency`
  deseniyle, anahtar `pdf_araclari:<uuid>` (`ConfirmReceipt.process_id`, şema değişmedi) → tekrar `{"document_id": aynı,
  "reused": true}`; belge yaratılmadan düşen her yol (4xx, 503, 409) kaydı bırakır.
- **Kilitli kart → 409:** `save_case_document` lock_timeout'ta (SQLSTATE 55P03) artık `KayitMesgulError` yükseltir
  (`document_pipeline.py:151-155`); bu `/confirm` ve intake'i de etkiler — eskiden belge kaydı sessizce açılmıyordu
  (G269 raporu).
- `POST /karttan-al {document_id}`: kartın arşivdeki belgesi (`sharepoint_url` + `stored_filename` dolu; taslak
  `03_TASLAKLAR/<ofis_no>/`den, kesin işlenmiş arşivden) `download_file_from_sharepoint` ile indirilir → `pdf_ye_cevir` →
  `Dosya`. 404 belge/URL yok, 502 SharePoint (TEK ERROR), 413 boyut.
- Ekran: "Karta bağla" diyaloğu (dava arama `/api/cases/search`, belge türü `/api/config/doctypes`, müvekkil tarafı, yön,
  Kesinleştir/Taslak), "Karttan al" diyaloğu (kart belgeleri, çoklu seçim, sıralı alma, "Al ve birleştir"); dava kartı
  belge satırında "PDF araçlarında aç" ve çoklu seçim şeridi `navigate("/belge-tezgahi", { state: { document_ids, case } })`
  (`pages/CaseDetails.tsx`). Diyaloglar `theme-classic` taşır.

### 9.5 Sınırlar ve hata eşlemesi (K8)

| Sınır | Değer | Kaynak |
| --- | --- | --- |
| İşlem başına girdi | 20 (422) | `settings.pdf_araclari_max_girdi` (`config/settings.py:84`) |
| Çıktı sayfa tavanı | 1.000 (413) | `settings.pdf_araclari_max_sayfa` (`:83`) |
| Zaman bütçesi | 270 sn (504; nginx 300 sn) | `settings.pdf_araclari_butce_saniye` (`:85`) |
| Eşzamanlı işlem | 2 (dolu → 503) | `_pdf_arac_semaphore` (`routes/pdf_araclari.py:85`) |
| Hız sınırı | `30/minute` (uca özel) | `HIZ_SINIRI` (`:76`) |
| Yükleme | 50 MB, `ALLOWED_EXTENSIONS` + magic-byte | mevcut `file_utils` |
| Önizleme genişliği | 64-1600 px (aksi 422), `Cache-Control: private, max-age=3600` | `ONIZLEME_GENISLIK_ARALIGI` |

Hata eşlemesi (`routes/pdf_araclari.py` docstring): `ParametreHatasi`/`PdfArcHatasi` → 422, `SayfaSinirAsildi` → 413,
`AracYok` → 503, `ZamanAsimi` → 504, `ConversionBusyError` → 503; gövde `{"detail": {"mesaj", "error_kod"}}`. Log
sözleşmesi: 4xx WARNING, 5xx TEK ERROR. İstemci: 4xx'te sunucu metni, 5xx'te sabit metin (`lib/pdfAraclariApi.ts`);
`islem` JSON gövdeli olduğundan `lib/api.ts:78` uzun zaman aşımı (300 sn) önekindedir.

### 9.6 Belge modeli eki (G282, migrasyon 61) ve testler

`case_documents.yon` (GELEN|GIDEN), `kaynak` (BELGE_HATTI|PDF_ARACLARI|WORD|ARSIV_AKTARIM|TESLIM), `durum` (TASLAK|KESIN),
`word_url`, `kesinlesme_*`, `onceki_document_id` (`models.py:1318-1324`); sürüm defteri `belge_surumleri`
(`models.py:1332`; `database.py` madde 61 — kolon/tablo KOŞULLU, kalıcı kısıt/index ve backfill AYRI `("index", ...)`
op'unda, CLAUDE.md tuzağı). Mevcut kayıtlar GELEN/KESIN, `uploaded_by LIKE 'ARSIV_AKTARIM:%'` → kaynak ARSIV_AKTARIM.
Word yaşam döngüsü (yeni/sürüm/kesinleştir) G284-G287'nin işidir; bu bölüm yalnız PDF yolunu anlatır.

Bekçiler: backend `tests/test_pdf_araclari_{cekirdek,uclari,cache,kart}.py` (çekirdek 81 · uçlar+cache 57 · kart 61;
nginx'te `/pdf-araclari` location'ı OLMADIĞI bekçisi `test_pdf_araclari_uclari.py`, konteynerde skip); frontend
`components/pdf/*.test.tsx`, `lib/pdfAraclariApi.test.ts`, `pages/BelgeTezgahiPage.test.tsx`,
`pages/CaseDetails.pdfAraclari.test.tsx`. Gerçek girişle tarayıcı zinciri (yükle → işlem → karart → karta bağla → kartta
görünür → karttan al) ve deploy İNSAN ADIMIdır (plan "DURAK"). OCR kapsam DIŞI (ayrı karar).
