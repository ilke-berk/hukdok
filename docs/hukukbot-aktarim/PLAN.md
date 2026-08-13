# Hukdok → Hukukbot Otomatik Karar Aktarım Planı

> Durum: Taslak — kod incelemesiyle doğrulandı, bulgular ve düzeltmeler işlendi (2026-07-06).
> İlgili dosya: [BULGULAR.md](BULGULAR.md) — plana karşı yapılan kod incelemesinin bulguları ve düzeltme önerileri.

## Mimari özet

İkisi aynı sunucuda çalışacağı için akış şöyle: webhook tetikler, veriyi hukukbot çeker.
Bu hibrit model push'un hızını verir ama veri transferini tek yönlü ve tekrarlanabilir
(retry edilebilir) tutar:

```
Hukdok (belge arşivlendi, tür uygun)
  │  1. outbox'a kayıt + POST http://hukukbot:<port>/ingest/hukdok  {document_id}
  │     (aynı Docker Compose network'ü — localhost DEĞİL, bkz. BULGULAR #2)
  ▼
Hukukbot ingest servisi
  │  2. GET hukdok/export/documents/{id}        → metadata
  │  3. GET hukdok/export/documents/{id}/file   → PDF (hukdok Graph'tan indirir)
  │  4. sha256 dedup → PDF_FOLDER'a kaydet → File Search store'a yükle
  │     → metadata'yı dönüştürüp metadata_db'ye yaz (LLM çıkarımı YOK)
  ▼
  5. ACK → hukdok outbox kaydını "delivered" yapar
  + Emniyet: hukukbot periyodik reconcile (kaçan webhook'ları cursor'la toparlar)
```

MCP'ye gerek yok — amaç otomasyon olduğu için düz API + webhook hem daha basit hem daha
sağlam. İleride Claude'un "hukdok'ta şunu ara, aktar" demesi istenirse aynı export
API'sinin üstüne ince bir MCP server eklenebilir.

## Hukdok tarafında yapılacaklar

### 1. Outbox tablosu — `export_outbox`

**Aktarımın kaynağı outbox'tır, `case_documents` değil** (gerekçe: BULGULAR #1 —
async upload yarışı). Satır yalnızca "SharePoint upload başarılı + `sharepoint_url`
DB'ye yazıldı" anında oluşturulur; böylece outbox `id` sırası = aktarılabilirlik sırası.

```
export_outbox
├── id            (autoincrement — reconcile cursor'ı bu)
├── document_id   (FK case_documents.id, unique)
├── status        ("pending" | "delivered" | "failed")
├── created_at
├── delivered_at  (nullable)
└── attempts      (int, webhook deneme sayısı)
```

Hook noktası: `services/document_pipeline.py` → `async_islenmis_upload` içinde,
`doc_rec.sharepoint_url = response_data["webUrl"]` commit'inin hemen ardından
(`document_pipeline.py:318-325`). Tür allowlist'ine uyan **ve** `link_mode != "TEST"` olan
belgeler için outbox satırı aç + webhook POST'u dene.

### 2. Export router — `backend/routes/export.py`

Mevcut modüler yapıya yeni router:

- `GET /export/documents?status=&after_id=&types=` — **outbox üzerinden** liste.
  Normal reconcile `status=pending` ile sorgular (cursor YOK — gerekçe: BULGULAR #9,
  cursor ya sessiz kayıp ya kuyruk kilidi üretir); `after_id` yalnızca backfill
  modu içindir. Dönen her kayıt: `{outbox_id, document_id, status}` + özet metadata.
- `GET /export/documents/{id}` — metadata JSON (`belge_turu_kodu/adi`, `ai_summary`,
  `esas_no`, `muvekkil_adi`, `avukat_kodu`, dava bilgileri, `tracking_no`,
  `sharepoint_url`, `stored_filename`, `uploaded_at`).
- `GET /export/documents/{id}/file` — SharePoint'ten PDF'i indirip döner.
  **Yeni Graph kodu gerekmez**: `sharepoint/sharepoint_uploader_graph.py:421-439`'daki
  `download_file_from_sharepoint(folder, stored_filename)` ve
  `routes/documents.py:319-346`'daki mevcut indirme akışı aynen yeniden kullanılır
  (klasör `SHAREPOINT_FOLDER_ISLENMIS_NAME` env'inden). Graph kimlik bilgileri
  sadece hukdok'ta kalır. Not: fonksiyon dosyayı belleğe alır (stream değil);
  upload boyut limiti olduğu için kabul edilebilir.
- `POST /export/outbox/{outbox_id}/ack` — hukukbot işleyince çağırır, satır "delivered" olur.
- `POST /export/outbox/{outbox_id}/nack` — hukukbot N denemeden sonra çağırır
  (`{reason}` ile), satır "failed" olur ve manuel incelemeye düşer; `status=pending`
  sorgusundan çıkar, sonsuz retry biter (BULGULAR #9).

**Kimlik doğrulama:** `X-API-Key` header'ı, paylaşılan secret env'den. Router Azure AD
auth dependency'sinin DIŞINDA tutulur. **Ek katman:** `/export` host nginx'e hiç
bağlanmaz — yalnızca iç Docker network'ünden erişilir (BULGULAR #5).

**Tür filtresi:** karar + bilirkişi raporu `belge_turu` kodlarının allowlist'i
(env/config). DB'de hem pad'li (`ARA-KRR_______`) hem kısa (`ARA-KRR`) kod karışık
durumda olduğundan filtre SQL `IN` ile YAPILMAZ; `file_utils.py:264-272`'deki normalize
mantığıyla Python'da karşılaştırılır (veya allowlist'in her iki varyantı SQL'e verilir).
Liste onaylandı: [KOD_LISTESI.md](KOD_LISTESI.md) — v1 allowlist'i yalnızca "kesin dahil"
12 kod (9 karar + 3 bilirkişi); "karar bekleyen" kalemlerin tümü hariç (2026-07-06).

**Kayıt filtresi (BULGULAR #3):**
- `link_mode != "TEST"` — test yüklemeleri RAG'e gitmez.
- `sharepoint_url IS NOT NULL` — outbox tabanlı listede bu zaten garanti, `/file`
  endpoint'i yine de NULL durumda 404 döner.
- `UNLINKED` belgeler AKTARILIR (karar: içerik değerli, müvekkil eşleşmesi boş kalır).

### 3. Webhook publisher

Outbox satırı açıldığında background task ile
`POST http://hukukbot_api:8010/ingest/hukdok {document_id, outbox_id}`.
Backoff'lu birkaç retry; kalıcı başarısızlıkta satır "pending" kalır — reconcile toparlar.
(FastAPI BackgroundTasks restart'ta kaybolur; bu bilinçli olarak kabul edilir çünkü
emniyet ağı reconcile'dır.)

### 4. Compose değişiklikleri (BULGULAR #10, #11)

- `backend` servisine `container_name: hukdok_backend` (veya network alias) —
  paylaşılan network'te `backend` adı fazla genel, `hukdok-backend` ise hiç çözünmez.
- İki compose projesinin de katılacağı external network: `hukuk_shared`
  (`docker network create hukuk_shared`). Hukukbot tarafı servis `api`,
  container `hukukbot_api`, port 8010 ile aynı network'e katılır.
- `ports: "8001:8001"` → `"127.0.0.1:8001:8001"` — backend portu host'ta
  public kalmasın; host nginx localhost'tan proxy'lemeye devam eder,
  hukukbot iç network'ten konuşur.

## Hukukbot tarafında yapılacaklar

- **Ingest endpoint** (`POST /ingest/hukdok`, API-key korumalı): `document_id` alır,
  hukdok'tan metadata + dosyayı çeker, işler, ACK gönderir.
- **Uploader refactor:** `uploader_async.py`'deki `upload_single_file` mantığı
  "hazır metadata ile yükle" biçiminde yeniden kullanılabilir hale getirilir —
  hukdok'tan gelen belgelerde `extract_metadata_for_pdf` (LLM) adımı tamamen atlanır.
- **Metadata dönüşüm katmanı** (`app/hukdok_map.py`) — şemalar birebir değil:
  - `belge_turu` `ARA-KRR_______` → pad temizle → `dosya_turu_kodu`
  - `tarih` `YYYY-MM-DD` → `YYMMDD`
  - `ozet` → `topic`, `court` → `court`, `esas_no` → `YY/NNNNN` normalizasyonu
  - `muvekkil_adi` → `muvekkil_kodu` (7 sessiz harf kuralı, deterministik fonksiyon)
  - Provenans alanları korunur: `hukdok_id`, `sharepoint_url`, `tracking_no`
- **Dosya yerleşimi:** PDF `PDF_FOLDER`'a kaydedilir ki mevcut `/download/{filename}`
  kaynak-indirme akışı hukdok belgeleri için de çalışsın.
- **Reconcile job:** açılışta + periyodik (örn. 30 dk)
  `GET /export/documents?status=pending` — cursor ve lokal `ingest_state` YOK
  (BULGULAR #9): teslim durumu tek yerde (hukdok outbox) tutulur. Kayıt başına
  try/except; N başarısız denemeden sonra `nack`. Webhook ile reconcile aynı
  ingest işlevinden geçer (iki ayrı kod yolu olmaz).
- **Dedup sırası (BULGULAR #12):** sha256 hash'i File Search store upload'ından
  ÖNCE `metadata_db`'ye "pending" olarak yazılır, başarıda finalize edilir —
  yoksa upload ile metadata yazımı arasındaki crash, retry'da store'a çift
  yükleme üretir.
- **Dikkat:** `metadata_db.json` şu an CLI uploader ile paylaşılıyor; API'den
  eşzamanlı yazma için yazımlar tek bir lock arkasına alınmalı.

## Kapsam dışı (bilinçli kararlar — BULGULAR #4)

- **Güncelleme/silme yayılımı v1'de YOK.** Belgenin `belge_turu`'su sonradan
  düzeltilirse, UNLINKED → LINKED olursa veya belge silinirse hukukbot'a yansımaz.
- Ucuz sigorta: arada bir `after_id=0` ile tam reconcile + hukukbot tarafında
  "sha256 zaten var mı, metadata değişmiş mi" kontrolü. İlk sürümde sadece
  dedup (atla) davranışı yeterli; metadata güncelleme ileriye bırakıldı.
- Başta yanlış sınıflanmış (allowlist dışı) bir karar outbox'a hiç girmediği için
  sonradan düzeltilse bile aktarılmaz — kabul edilen sınırlama; tam reconcile
  koşusu (`after_id=0`) düzeltilmiş kayıtları da taramak istenirse outbox yerine
  belge tablosunu tarayan ayrı bir "backfill" modu ile çözülür.

## Uygulama sırası

| Faz | İş | Sonuç |
|-----|----|----|
| 1 | Hukdok: outbox tablosu + export router + API key ✅ (2026-07-06) | Hukukbot veri çekebilir hale gelir |
| 2 | Hukukbot: ingest + dönüşüm + reconcile ✅ (2026-07-06, bkz. hukukbot `rapor/07` §7.2 notu) | Sistem çalışır (periyodik/manuel aktarım) |
| 3 | Hukdok: outbox hook + webhook publisher ✅ (2026-07-06) | Anında aktarım devreye girer |
| 4 | Hukukbot'u aynı **Docker Compose network'üne** deploy ✅ (2026-07-06, lokal; prod'da gerçek secret + recreate gerekir) | Container-to-container push kurulur |
| 5 | Uçtan uca test: hukdok'a karar yükle → hukukbot RAG'inde sorgula | Doğrulama |

Faz 1–2 kendi başına da değerli: webhook olmadan bile sistem 30 dakikada bir senkron
olur; Faz 3 sadece gecikmeyi sıfırlar. Backfill mimariden bedavaya çıkar — reconcile'ı
`after_id=0` ile bir kez çalıştırmak (backfill modunda) tüm arşivi aktarır.

## Başlamadan eksikler — ÇÖZÜLDÜ

1. ~~Belge türü kod listesi~~ → çıkarıldı ve ONAYLANDI: [KOD_LISTESI.md](KOD_LISTESI.md) —
   v1 allowlist'i "kesin dahil" 12 kod; "karar bekleyen" kalemlerin tümü hariç.
2. ~~Hukukbot servis adı / port~~ → servis `api`, container `hukukbot_api`, port 8010,
   external network `hukuk_shared`. Hukdok tarafı `container_name: hukdok_backend`
   ekler (yukarıda §4).
