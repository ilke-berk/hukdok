# 009 — `/confirm` idempotency anahtarı `process_id`; kayıt DB'de

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul
- **Bağlam:** nginx 504'ünden (ya da ağ kopmasından) sonra kullanıcı "onayla"ya tekrar
  basıyor; frontend aynı `process_id` + dosya fallback'iyle `/confirm`'i yeniden çağırıyor
  ve pipeline ikinci kez koşuyordu → **mükerrer belge kaydı, mükerrer arşiv yüklemesi,
  mükerrer e-posta**. (Aynı 504 kaynağı `nginx.conf`'ta da belgelidir — bkz.
  `nginx.conf:10-12`.)
- **Karar:** `/confirm` bir idempotency kapısıyla başlar
  (`backend/services/confirm_idempotency.py`). Anahtar **`process_id`**'dir. Kayıt
  **DB'dedir** (`models.ConfirmReceipt`). Verdiktler: `replay` (saklanan yanıt aynen döner),
  `in_progress` (409), `proceed`, `bypass` (DB arızası).
- **Gerekçe (modül docstring'inden, `confirm_idempotency.py:9-30`):**
  - `process_id` `/confirm` formunda **zaten taşınıyor** (`Index.tsx` her zaman ekler,
    retry'da da aynı kalır) → frontend değişikliği gerektirmez; header yaklaşımı Faz 4'ün
    frontend paketini beklerdi.
  - Kapsam tam istenen genişlikte: "bir sihirbaz oturumu = bir belge kaydı". Kullanıcı
    sihirbazı baştan koşturursa yeni `process_id` üretilir ve bu **bilinçli yeni bir
    işlemdir**.
  - Kayıt yeri DB seçildi, süreç içi dict değil: "uvicorn restart'ında kayıt yaşar ve Faz
    3-E'nin `--workers 2` geçişinde worker'lar arasında tutarlı kalır (süreç içi sözlük iki
    durumda da kaçırırdı)".
- **Reddedilenler:**
  - *`Idempotency-Key` header'ı* — frontend değişikliği gerektirirdi, `process_id` zaten
    mevcut ve yeterli.
  - *`file_hash`* — iki nedenle: `/confirm`'e ulaşmıyor (form alanı yok, PROCESS_CACHE
    girdisinde saklanmıyor) ve **anlamsal olarak yanlış anahtar**: "aynı dosya bilerek iki
    kez yüklenebilir (örn. aynı dilekçe iki ayrı davaya) — hash dedup meşru tekrarları da
    yutar".
  - *Süreç içi sözlük* — restart'ta ve iki worker'da kaçırırdı.
- **Sonuçları:** Bayat `in_progress` kayıtları için eşik `PROCESS_CACHE` TTL'siyle
  hizalıdır (önceki süreç pipeline ortasında ölmüş olabilir — deploy/OOM). Pipeline istisna
  atarsa ve belge yaratılmamışsa kayıt `release` edilir, tekrar denemek serbest kalır.
  İlişkili bir idempotency kararı intake tarafında da vardır: `/commit`'in 409'u nihai
  değildir, muhafazakâr eşleşmeyle çözümlenir (`routes/case_intake.py:1096-1107`).
- **Test:** `backend/tests/test_faz3_confirm_idempotency.py`
- **İlgili:** [`docs/mimari/belge-isleme-hatti.md`](../mimari/belge-isleme-hatti.md),
  [`003-process-cache-disk.md`](003-process-cache-disk.md)
