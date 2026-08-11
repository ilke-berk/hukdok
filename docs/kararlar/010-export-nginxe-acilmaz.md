# 010 — `/export` public'e proxy'lenmez: iç ağ + API anahtarı, fail-closed

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul
- **Bağlam:** Hukukbot, HukuDok'tan aktarılacak belgeleri `/export/*` uçlarından okur ve
  acknowledge/nack eder. Bu uçlar kullanıcı kimliğiyle değil, servis-servis bir API
  anahtarıyla korunur — public internete açılırsa tek sızan anahtar tüm arşiv metadata'sını
  verir.
- **Karar:** İki bağımsız katman:
  1. **`/export` konteyner nginx'ine hiç eklenmez.** Yalnız iç Docker ağından
     (`hukuk_shared`, `http://hukdok_backend:8001`) erişilir. Konfigdeki uyarı birebir:
     `# DIKKAT: /export buraya ASLA eklenmez — yalnizca ic Docker network'unden erisilir,
     public'e proxy'lenmez` (`nginx.conf:40-41`). Backend portu da bu yüzden
     `127.0.0.1:8001`'e sabittir (`docker-compose.yml:47-49`).
  2. **API anahtarı, fail-closed.** Router'ın tamamı `require_export_api_key` bağımlılığıyla
     korunur (`backend/routes/export.py:67`).
- **Gerekçe (docstring'den, `export.py:44-49`):** "Env tanımlı değilse export API kapalıdır
  (fail-closed): her istek 503 alır. Anahtar zayıfsa (kısa veya 'dev-' önekli) yalnızca
  `DEV_MODE=true` iken kabul edilir; prod'da yine 503 (fail-closed). Karşılaştırma sabit
  zamanlıdır (timing attack'a karşı)."
  Zayıflık ölçütü açıktır: 32 karakterden kısa **veya** `dev-` önekli (`export.py:38-40`).
  Zayıf anahtar durumunda bir kez `CRITICAL` loglanır ve çözüm önerilir
  (`openssl rand -hex 32`).
- **Reddedilenler:**
  - *`/export`'u nginx'e ekleyip yalnız API anahtarına güvenmek* — tek katman; anahtar
    sızıntısı doğrudan internete açık bir uç bırakırdı.
  - *Anahtar yokken uçları açık bırakmak (fail-open)* — yanlış yapılandırma sessizce
    korumasız bir sistem üretirdi. Tercih: yapılandırılmamışsa **çalışmasın**.
  - *`==` ile karşılaştırma* — timing attack yüzeyi; `hmac.compare_digest` kullanılır
    (`export.py:63`).
- **Sonuçları:** Bu karar, aktarım hattının doğruluk garantisiyle birlikte okunmalıdır:
  webhook'un ulaşamaması sorun değildir, `export_outbox` + hukukbot'un periyodik reconcile'ı
  toparlar (`services/export_publisher.py:12-15`).
- **Test:** `backend/tests/test_export_filters.py`
- **İlgili:** [`docs/mimari/belge-isleme-hatti.md`](../mimari/belge-isleme-hatti.md),
  [`docs/hukukbot-aktarim/`](../hukukbot-aktarim/)
