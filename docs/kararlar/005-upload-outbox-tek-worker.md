# 005 — Süreç-tekil arkaplan işleri dosya kilidiyle; refresh thread'i bilinçli istisna

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul
- **Bağlam:** Backend `uvicorn --workers 2` ile koşar ve uvicorn lifespan'i **her worker
  sürecinde ayrı** çalıştırır. Süreç-tekil olması gereken işler (SharePoint upload outbox
  worker'ı, günlük rapor zamanlayıcısı, dönüşüm retry job'ı) her worker'da başlarsa aynı
  outbox satırı N kez yüklenir ve günlük rapor N kez üretilir.
- **Karar:** `backend/services/singleton_lock.py` — dosya kilidi (`flock LOCK_EX | LOCK_NB`,
  Windows'ta `msvcrt`). Kilidi alan worker "lider"dir; süreç-tekil işler yalnız onda başlar
  (`api.py:158`, `:201`). **Liste tazeleme thread'i bilinçli istisnadır** ve her worker'da
  koşar (`api.py:144-154`).
- **Gerekçe:**
  - Lider seçimi için: "Kilit süreç yaşadıkça tutulur; süreç ölünce çekirdek kilidi bırakır
    → uvicorn'un yeniden doğurduğu worker kendi lifespan'inde kilidi devralır (kendi
    kendini onarır — liderlik sabit bir worker'a bağlı değildir)" (`singleton_lock.py:8-12`).
    Kilit lifespan sırasında, yani **fork sonrası** açılır; import anında değil.
  - Refresh thread'inin istisna olması için (`api.py:144-148`): "DynamicConfig, matcher ve
    searcher süreç İÇİ singleton'lardır — yalnız liderde koşsaydı diğer worker'lar taze
    cache dosyası yokken boş listelerle kalırdı. Duplikasyonun tek gerçek zararı cache
    dosyası yazma yarışıydı → `cache_manager.save_cache` tekil temp adla atomik yazacak
    şekilde düzeltildi."
- **Kabul edilen sınır (kodda açıkça):** "`/refresh` endpoint'i yalnız isteği işleyen
  worker'ı tazeler; diğeri kendi refresh'ine (boot ya da kendi `/refresh`'i) kadar bayat
  kalır — liste değişiklikleri nadir, kabul edilen takas" (`api.py:149-151`).
  Aynı biçimde Gemini devre kesicisi ve `health.py` sayaçları da süreç içidir
  (`gemini_client.py:98-100`).
- **Reddedilenler:** *Her worker'da outbox worker'ı çalıştırmak* — aynı satır N kez
  yüklenirdi (overwrite zararsız ama gereksiz), `upload_queue.py:1-35` bunu önkoşul olarak
  işaretlemişti. *Lideri sabit bir worker'a atamak* — o worker ölürse iş kalıcı olarak
  durur; dosya kilidi kendi kendini onarır.
- **Test:** `backend/tests/test_faz3_upload_outbox.py`,
  `backend/tests/test_faz3_e_hardening.py`
- **İlgili:** [`docs/mimari/genel-bakis.md`](../mimari/genel-bakis.md),
  [`006-gece-otomasyonu-serit-modeli.md`](006-gece-otomasyonu-serit-modeli.md)
