# Otonom Dava Açma — Faz 4 Başlangıç Planı (commit endpoint)

*Tarih: 2026-07-30 · Yeni oturum için kendi kendine yeten kickoff dokümanı.*
*Eş dosyalar: [geliştirme planı](otonom-dava-acma-gelistirme-plani-2026-07-24.md) (ayrıntılı tasarım + "Faz 3 durumu" bloğu), [Faz 2 kickoff](otonom-dava-acma-faz2-baslangic-2026-07-30.md), [hazırlık raporu](otonom-dava-acma-hazirlik-raporu-2026-07-24.md).*

## Bağlam (30 saniyede)

Hedef akış: belgeleri tek seferde yükle → sistem dava kartını doldurur → kullanıcı
tik'lerle onaylar → **tek "Kaydet"** ile dava oluşur + belgeler bağlanır/arşivlenir.
Faz 0 (kalibrasyon), Faz 2 (`/api/case-intake/analyze`) ve Faz 3 (`/merge` +
`/keepalive` + `client_policies`) **bitti**. Sıra **Faz 4: `POST
/api/case-intake/commit`** — sihirbazın "Kaydet ve Arşivle" düğmesinin arkasındaki
TEK kayıt endpoint'i. Efor ~1 gün (+poliçe beslemesi eklendi, aşağıda).

## Faz 3'ten devralınanlar (bu oturumda hazır olan altyapı)

- **`/api/case-intake/analyze`** (Faz 2): belge başına çıkarım; tam PDF
  `PROCESS_CACHE`'te `process_id` ile duruyor (`routes/processing.py:32`,
  TTL 30 dk). Cache girdisi `{path, original_path, original_ext}` şeklinde —
  `/process` ile aynı hijyen; dönüştürülmüş formatlarda (UDF/TIF/DOCX) orijinal
  dosya da saklı, HAM arşive o gider.
- **`/api/case-intake/merge`** (Faz 3, durumsuz): dava kartı taslağı döner —
  `fields` (value/candidates/agreement/confidence/sources), `parties`
  (party_type + cari `match`), `policies` (client_id + `saved` bayraklı),
  `warnings`, `documents`, `duplicate_case`, `priors`. Frontend taslaktan
  kullanıcı onaylı halini commit'e gönderecek.
- **`/api/case-intake/keepalive`**: `TTLCache.touch` — sihirbaz review adımında
  10 dk'da bir çağırır; commit'e gelen process_id'lerin çoğu bu sayede canlı olur.
- **`client_policies`** tablosu + `managers/client_manager.save_client_policies(client_id,
  policies, created_by)` — **idempotent** besleme (dedupe = normalize police_no +
  dönem başı); `GET/POST/DELETE /api/clients/{id}/policies` endpoint'leri canlı.
  **Poliçe beslemesi bilinçli olarak commit adımına bırakıldı** (merge durumsuz,
  kullanıcı vazgeçebilir) — Faz 4 kapsamındadır.
- Testler: `tests/test_case_intake_analyze.py` (23), `tests/test_case_intake_merge.py`
  (31); suite 389 yeşil, ruff + mypy temiz.

## Kesinleşen kararlar (kullanıcı onaylı — yeniden tartışma yok)

1. Sihirbaz dava durumu: **sabit DERDEST**.
2. Müvekkile e-posta: **varsayılan KAPALI toggle** (`options.send_email=false`).
3. `duplicate_tracking_no` → **409**; frontend sequence yenileyip **1 kez**
   otomatik dener (tracking_no üretimi client-side kalır — `client-sequence` +
   `generateTrackingNumber`, kategori önceliği aynen).
4. **Dava oluşturma transactional; belge arşivleme belge-başı best-effort** —
   başarısız/TTL-dolmuş belge akışı öldürmez, yanıtta `failed`/`expired` döner,
   sonuç ekranı "davaya git, tekrar yükle" yönlendirir.
5. Poliçe kalıcı kaydı **commit'te** yapılır (karar 3'ün devamı; Faz 3 sapma notu).

## Faz 4 kapsamı — `POST /api/case-intake/commit`

**Yeni dosya yok** — `backend/routes/case_intake.py`'a eklenir; iş mantığı
mevcut yapıtaşlarının kompozisyonu (`services/document_pipeline.py` +
`managers/case_manager.py`). Test: `backend/tests/test_case_intake_commit.py`.

### İstek (JSON; multipart DEĞİL — dosyalar zaten PROCESS_CACHE'te)

```json
{
  "case": { "...schemas.CaseCreate (tracking_no dahil, parties/lawyers içinde)..." : "" },
  "documents": [
    {"process_id": "…", "new_filename": "…", "belge_turu_kodu": "…",
     "ai_ozet": "…", "esas_no": "…", "muvekkil_adi": "…"}
  ],
  "policies": [ {"client_id": 12, "police_no": "…", "police_turu": "…",
                 "sigorta_sirketi": "…", "baslangic_tarihi": "…",
                 "bitis_tarihi": "…", "retroaktif_tarihi": null,
                 "sigortali_kurum": null, "teminat_limiti": null,
                 "source_document": "police.pdf"} ],
  "options": {"send_email": false}
}
```

- `case.status` sunucuda **DERDEST'e zorlanır** (karar 1 — istemciye güvenme).
- `policies`: kullanıcının review'da ONAYLADIĞI, `client_id`'si dolu poliçeler
  (merge çıktısında `saved=true` olanları frontend hiç göndermez).
- Pydantic modelleri `schemas_intake.py`'a: `CommitDocumentIn`,
  `CommitPolicyIn` (veya `schemas.ClientPolicyCreate` + client_id sarmalayıcı),
  `CaseIntakeCommitRequest`, `options` için `CommitOptions`.

### Davranış (sıra önemli)

1. **Dava — atomik:** `case_manager.add_case(case_dict)` (cases route'u gibi
   tenant paslamadan — ortak havuz modeli). Dönüş `{"error":
   "duplicate_tracking_no"}` ise **409** fırlat (bkz. `routes/cases.py:47-53`
   birebir desen). `None` ise 500. Başarıda `case_id` alınır.
2. **Belge başına best-effort döngü** — her belge kendi try/except'inde:
   a. `document_pipeline.validate_tenant_and_resolve_lawyer(case_id, user,
      avukat_kodu=None)` → avukat kodu davanın sorumlusundan çözülür.
      (İlk belgede bir kez çağırıp sonucu döngüde yeniden kullanmak yeterli —
      dava az önce bizim oluşturduğumuz; her belgede tekrar tenant sorgusu israf.)
   b. `document_pipeline.accept_incoming_file(process_id, file=None,
      PROCESS_CACHE)` — **DİKKAT: cache girdisini POP eder (tüketir)**; girişte
      process_id yoksa/dosya diskten silinmişse `HTTPException(400)` fırlatır →
      bu belgeyi `{"status": "expired"}` olarak raporla, akışa devam et.
   c. `sanitize_filename(new_filename)`; `ham_filename = f"{date}_{sanitize(orijinal ad)}"`.
      Orijinal ad: merge `documents[].filename`'den commit isteğinde taşınabilir
      ya da `new_filename` kullanılır (confirm'deki fallback deseni).
   d. `document_pipeline.convert_pdfa_and_queue_uploads(..., linked_case_id=case_id,
      muvekkil_adi=doc.muvekkil_adi, esas_no=doc.esas_no, ai_ozet=doc.ai_ozet,
      belge_turu_kodu=doc.belge_turu_kodu, is_test_mode=False, ...)` — imza için
      `routes/processing.py:579-601`'e (confirm) birebir bak; `results`/`timings`
      dict'leri belge-başı ayrı tutulur.
   e. `document_pipeline.schedule_cleanup(...)` (confirm'deki gibi; ham orijinal
      farklıysa onu da temizler).
   f. Hata → `TechnicalLogger` + `{"status": "failed", "error_ozet": "..."}`;
      başarı → `{"status": "queued", "document_id": doc_id}`.
3. **Poliçe beslemesi — best-effort:** `policies`'i `client_id`'ye grupla, her
   grup için `save_client_policies(client_id, [...], created_by=kullanıcı)`.
   Hata dava kaydını GERİ ALMAZ; yanıtta `policy_result: {"saved": n,
   "skipped": n}` ya da `{"error": "..."}`.
4. **E-posta:** `options.send_email` true ise mevcut
   `document_pipeline.send_notification_email` (confirm'deki kullanım deseni);
   varsayılan kapalı — v1'de hiç çağrılmaması da kabul, toggle Faz 5 UI işi.
5. **Yanıt:**
```json
{
  "case": {"id": 123, "tracking_no": "2026/0456"},
  "documents": [{"process_id": "…", "status": "queued|failed|expired",
                 "document_id": 45, "error_ozet": null}],
  "policies": {"saved": 2, "skipped": 1}
}
```

### Bilinen tuzaklar (bu endpoint'e özgü)

- **`accept_incoming_file` POP eder:** aynı process_id ikinci kez commit'lenemez;
  409 sonrası frontend retry'ı YALNIZCA dava kaydını tekrarlar sanmasın —
  409 durumunda henüz hiçbir belge tüketilmemiştir (add_case adım 1'de patlar),
  bu yüzden retry güvenlidir. Belge döngüsü başladıktan sonra oluşan kısmi
  hatalarda retry YOK — sonuç ekranı yönlendirmesi var (karar 4).
- `convert_pdfa_and_queue_uploads` **senkron PDF/A dönüşümü** yapar (Ghostscript);
  N belge için commit yanıt süresi belge sayısıyla büyür. v1'de kabul (max 15);
  endpoint'i `async def` yapıp dönüşümü `run_in_executor`'da koşmak yeterli
  (confirm zaten `async def` + BackgroundTasks kullanıyor).
- `BackgroundTasks` FastAPI parametresi olarak alınmalı (confirm gibi) — upload
  kuyruğu yanıt döndükten sonra çalışır.
- Confirm yolunda yaşanmış GS `UnicodeDecodeError` arızası (2026-07-13;
  `UnicodeDecodeError`, `ValueError`'ın alt sınıfıdır ve dar except'leri deler)
  güncel main'de hâlâ mevcut — intake commit'in belge-başı sarmalayıcısı geniş
  `except Exception` kullansın ki tek belge hatası akışı öldürmesin.
- `case.parties[].client_id` → `CasePartyCreate` zaten destekliyor; merge
  `match.client_id`'sini frontend taşır. `case_party_id` bağlama (belge→taraf)
  v1'de YOK (belge davaya bağlanır, tarafa değil) — İş Kalemi 4/sertleştirmede.

## Uygulama sırası önerisi

1. `schemas_intake.py`'a commit istek/yanıt modelleri.
2. Route iskeleti: add_case + 409 yolu (belge yok senaryosu uçtan uca).
3. Belge döngüsü: accept → pdfa → queue → cleanup; expired/failed raporlama.
4. Poliçe beslemesi + options.send_email.
5. Testler: `tests/test_case_intake_commit.py` — conftest desenleri;
   `add_case`, `validate_tenant_and_resolve_lawyer`, `convert_pdfa_and_queue_uploads`,
   `schedule_cleanup`, `save_client_policies` **monkeypatch'li** (DB/ağ yok):
   - dava oluşur + tüm belgeler queued (mutlu yol),
   - `duplicate_tracking_no` → 409 ve HİÇBİR belgenin tüketilmediği,
   - cache-miss belge → `expired`, kalanlar `queued` (izolasyon),
   - pdfa hatası → o belge `failed`, akış sürer,
   - poliçe besleme hatası → dava/belgeler etkilenmez, yanıtta error,
   - `case.status` istemci ne gönderirse göndersin DERDEST.
6. Elle duman testi (lokal stack): analyze → merge → commit zinciri gerçek
   PDF'le; dava listesinde görünmeli, `case_documents` + `export_outbox`/upload
   kuyruğu dolmalı, poliçe müvekkil kartında görünmeli.

## Test ve çalıştırma (bu repoya özgü — değişmedi)

- Backend pytest **KONTEYNERDE** (host py3.13 uyumsuz). Stack ayaktaysa:
  `docker compose exec backend python -m pytest tests/ -q`
  (pytest imajda yoksa bir kez: `docker compose exec -u root backend pip install -r requirements-dev.txt`).
- Lint: `docker compose exec backend python -m ruff check --output-format=concise .`
  ve `docker compose exec backend python -m mypy` (routes/ + managers/ taranır —
  commit route'u mypy kapsamındadır, tip düşkünü yaz).
- Konteyner Python **3.10** — 3.12 sözdizimi yok.
- Lokal gerçek Gemini koşusu gerekirse (analyze/merge duman testi): AVG TLS
  araya girmesi — `-e SSL_CERT_FILE=/app/calibration/ca_bundle.pem` (yalnız bu
  PC; prod'da yok, üretim koduna gömme).
- PowerShell 5.1'de Türkçe içerikli dosyaya daima Edit/Write tool (Get/Set-Content çift kodlar).
- Migration gerekmiyor (client_policies Faz 3'te yaratıldı).

## Faz 4 çıkış kriterleri

1. `POST /api/case-intake/commit` tek çağrıda dava + N belge + poliçe kaydını
   yapıyor; yanıt belge-başı durum içeriyor.
2. 409 yolu: duplicate tracking_no'da hiçbir belge tüketilmeden 409 dönüyor
   (frontend'in tek retry varsayımı güvende).
3. Belge-başı hata izolasyonu testle kanıtlı (expired + failed senaryoları).
4. Poliçe beslemesi idempotent çalışıyor (ikinci commit aynı poliçeyi çoğaltmıyor)
   ve hatası dava kaydını düşürmüyor.
5. Konteynerde tam suite + ruff + mypy yeşil.
6. Elle duman testi: analyze → merge → commit zinciri lokalde uçtan uca çalıştı.

## Faz 4 sonrası sıra

Faz 5: sihirbaz UI (4 adım + CaseList girişi, 4–5 g — özellik burada çıkar) →
Faz 1 (takip paneli tek-Kaydet) araya her an alınabilir → Faz 6: sertleştirme
(`update_case` taraf öksüzleşmesi, client-sequence fallback, service_type kaderi).
