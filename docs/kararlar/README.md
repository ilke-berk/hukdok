# docs/kararlar — kalıcı mimari kararlar

Geri alınması pahalı olan ya da tekrar tekrar sorgulanan kararların gerekçesi burada
tutulur: **karar + bağlam + gerekçe + reddedilen alternatifler**.

## Kayıtlar

| # | Karar |
| --- | --- |
| [001](001-tenant-ortak-havuz.md) | Yeni kayıtlar `tenant_id=NULL`: iki tenant ortak havuzda çalışır |
| [002](002-ofis-no-isim-blogu-onceligi.md) | Ofis numarası isim bloğu: kategori önceliği, "ilk müvekkil" değil |
| [003](003-process-cache-disk.md) | PROCESS_CACHE disk destekli, bellekte state yok |
| [004](004-failed-olay-sozlesmesi.md) | `failed` olay sözleşmesi: terminal olay, etiket uzayı AÇIK |
| [005](005-upload-outbox-tek-worker.md) | Süreç-tekil arkaplan işleri dosya kilidiyle; refresh thread'i istisna |
| [006](006-gece-otomasyonu-serit-modeli.md) | Gece otomasyonunda şerit modeli: backend ana dizinde seri |
| [007](007-logout-taslak-susturmasi.md) | Form taslakları sessionStorage'da; çıkışta yazım bastırılır (KVKK) |
| [008](008-conversion-pending-ayri-kolon.md) | Dönüşüm durumu ayrı kolonda; gece retry'ı senkron yükler |
| [009](009-confirm-idempotency-anahtari.md) | `/confirm` idempotency anahtarı `process_id`; kayıt DB'de |
| [010](010-export-nginxe-acilmaz.md) | `/export` public'e proxy'lenmez: iç ağ + API anahtarı, fail-closed |
| [011](011-bellek-swap-yasagi.md) | Swap yasak, bellek limitleri repoda, `MALLOC_ARENA_MAX=2` |
| [012](012-soft-delete-baglar-korunur.md) | Soft-delete: bağlar koparılmaz, `active` alanına dokunulmaz |
| [013](013-bagimlilik-yamalama-ve-calisma-zamani.md) | Bağımlılık yamalama sırası, tarihli ignore listesiyle denetim kapısı, `node:24` + `python:3.12` |
| [014](014-uyap-avukati-on-doldurulmaz.md) | UYAP Avukatı ön-doldurulmaz; zorunluluk bağlamsallaşır |
| [015](015-kanonik-dava-konusu-yazimi.md) | Kanonik dava konusu yazımı; asıl düzeltme veri değil kural |
| [016](016-ofis-no-kategori-rejimi.md) | Ofis no kategori rejimi: `K1` ileriye dönük, geçmiş dokunulmaz |
| [017](017-elasticsearch-ve-redis-kapsam-disi.md) | Elasticsearch ve Redis kapsam dışı: bellek bütçesi + kullanılmayan index'ler |

## Dosya biçimi

`NNN-kisa-baslik.md`, içinde:

```
# NNN — <karar>
- **Durum:** kabul | değiştirildi (bkz. NNN) | geri alındı
- **Bağlam:** hangi problem
- **Karar:** ne yapıldı
- **Gerekçe:** neden bu
- **Reddedilenler:** hangi alternatif, neden değil
```

Karar bir plan adımı değil, **kalıcı bir tercih** olmalı; tek seferlik iş kalemleri
[`docs/plan/`](../plan/) altına ya da `gorevler/` kuyruğuna yazılır.
