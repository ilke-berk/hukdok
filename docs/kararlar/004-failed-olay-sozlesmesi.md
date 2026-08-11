# 004 — `failed` olay sözleşmesi: terminal olay, etiket uzayı AÇIK

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul
- **Bağlam:** `/process` NDJSON stream'iyle çalışır. Nihai başarısızlık eskiden varsayılan
  verilerle dolu bir `complete` olayı ya da serbest biçimli bir hata mesajı olarak
  dönüyordu; frontend formu boş/uydurma veriyle doldurabiliyor, hata türüne göre davranmak
  mümkün olmuyordu.
- **Karar:** Ayrı bir terminal olay tipi:
  `{"status": "failed", "error_ozet": "<Türkçe mesaj>", "error_kod": "<etiket>"}`.
  Sözleşmenin tek kaynağı `backend/analyzer.py::_failed_event` docstring'idir (`:368-393`)
  ve **frontend ile ortak referanstır**. Etiketler: `gemini_saturated`, `gemini_blocked`,
  `gemini_truncated`, `schema_invalid`, `analysis_error`.
- **Gerekçe (üç kural, docstring'den):**
  - **Etiket uzayı KAPALI değildir** — "ileride yeni etiket eklenebilir; tüketiciler
    tanımadıkları etiketi `analysis_error` gibi ele almalıdır". Böylece backend yeni bir
    hata sınıfı ekleyince frontend'i kırmaz. Frontend bunu `msg.error_kod ||
    "analysis_error"` ile uygular (`frontend/src/lib/analyzeDocument.ts`).
  - **`failed` SON olaydır**: ardından `complete` gelmez ve olay `process_id` **taşımaz** —
    confirm adımı yoktur, PROCESS_CACHE yazılmaz. Kullanıcı yarım bir oturumla kalmaz.
  - **Yeni ERROR log satırı EKLEMEZ**: nihai ERROR'lar çağıran handler'da yazılır,
    deneme-düzeyi hatalar WARNING kalır (log sözleşmesi).
- **Reddedilenler:**
  - *Kapalı enum* — her yeni hata sınıfı frontend sürümüyle eşzamanlı deploy gerektirirdi.
  - *Varsayılan veriyle `complete` döndürmek* — kullanıcıya uydurma alan gösteriyordu;
    frontend artık `AnalysisFailedError` fırlatıp formu doldurmuyor.
  - Route'un beklenmedik istisnada ürettiği `{"status": "error", "message"}` olayı bu
    sözleşmenin **dışında** bırakılmıştır ve aynen korunur (`analyzer.py:390-391`).
- **Test:** `backend/tests/test_faz4_failed_event.py`,
  `frontend/src/lib/analyzeDocument.test.ts`
- **İlgili:** [`docs/mimari/belge-isleme-hatti.md`](../mimari/belge-isleme-hatti.md)
