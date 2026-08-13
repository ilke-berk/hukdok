# 003 — PROCESS_CACHE disk destekli, bellekte state yok ("diskten lazy okuma")

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul
- **Bağlam:** `/process` ile `/confirm` arasında dosya ve analiz sonucu bir cache'te tutulur.
  Cache süreç içi bir sözlük olduğu sürece iki sorun vardı: uvicorn `--workers 2`'ye
  geçişte `/process`'i işleyen worker ile `/confirm`'i işleyen worker farklı olabiliyordu,
  ve konteyner restart'ı bekleyen tüm oturumları düşürüyordu.
- **Karar:** `managers/ttl_cache.py::DiskTTLCache` — `TTLCache` ile aynı arayüz, disk
  destekli. **Bellekte state yoktur**: her girdi bir `<dir>/<key>.json` meta dosyasıdır ve
  her işlem diski okur (`managers/ttl_cache.py:97-98`). `PROCESS_CACHE` bunun üzerine
  `adopt_file_fields=("path", "original_path")` ile kurulur (`routes/processing.py:76-80`)
  — girdideki yollar dosyanın taşınma **sonrasını** gösterir, `/confirm` onları kalıcı
  volume'den okur.
- **Gerekçe:** Docstring'den birebir: "İşlem hacmi kullanıcı-eylemi mertebesinde (dakikada
  onlarca) ve meta dosyaları birkaç yüz bayt — süreç içi indeks + sidecar senkronunun
  bayatlama problemleri (worker A evict etti, worker B hâlâ biliyor) hiç doğmaz."
  Yani ölçek küçük olduğu için en basit tutarlı model seçilmiştir.
  Yarış güvenliği ayrıca sağlanmıştır: `pop()` süreçler arası atomiktir — meta dosyası önce
  rastgele adlı bir claim dosyasına `os.replace`/rename ile taşınır, yarışan iki `pop`'tan
  yalnız biri kazanır (`managers/ttl_cache.py:106-109`).
- **Reddedilenler:** *Süreç içi indeks + disk sidecar* — iki worker arasında bayatlama
  (evict görünürlüğü) sorunları doğururdu, docstring'de açıkça reddedilmiştir.
  *Redis/harici cache* — üç konteynerlik bir kuruluma yeni bir servis eklerdi; bu ölçekte
  karşılığı yok.
- **Sonuçları:** Boot'ta TTL süpürmesi koşar; bayat girdiler ve payload'lar silinir, **taze
  girdiler restart'ı atlatır** — özelliğin amacı budur (`api.py:215-218`). Süpürme
  claim-atomik olduğu için iki worker'ın eşzamanlı süpürmesi güvenlidir.
- **İlgili:** [`docs/mimari/belge-isleme-hatti.md`](../mimari/belge-isleme-hatti.md),
  [`009-confirm-idempotency-anahtari.md`](009-confirm-idempotency-anahtari.md)
