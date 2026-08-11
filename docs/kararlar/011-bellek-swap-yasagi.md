# 011 — Swap yasak, bellek limitleri repoda, `MALLOC_ARENA_MAX=2`

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul
- **Bağlam:** 2026-07-29/30'da üç prod kesintisi yaşandı. İnceleme kök nedeni backend'in
  anon bellek büyümesine bağladı; swap'a taşma I/O fırtınasını, o da VM'in ağ/SSH
  kaybetmesini üretiyordu. Bellek limitleri o sırada yalnız sunucudaki gitignore'lu bir
  compose override'ında ve `daemon.json`'daydı — VM kaybında konfig geri gelmezdi.
- **Karar:** Üç ayar, üçü de `docker-compose.yml`'de (repoda):
  1. Her serviste `mem_limit` **ve** `memswap_limit` **eşit** — swap tamamen kapalı.
     backend 2g (`:79-80`), postgres 512m (`:21-22`), frontend 128m (`:115-116`).
  2. Backend'de `MALLOC_ARENA_MAX=2` (`:64`).
  3. Log rotasyonu servis bazında (json-file, 50m×3) — `daemon.json`'a bağımlı değil.
- **Gerekçe (kodda birebir):**
  - Swap için: "memswap=mem → swap yok: swap'a taşma, 2026-07-29 kesintilerindeki I/O
    fırtınasının mekanizmasıydı (tüm servislerde aynı kural)" (`docker-compose.yml:19-20`).
  - Limitlerin repoda olması için: "önceden yalnız sunucudaki gitignore'lu override'da /
    daemon.json'daydı — VM kaybında konfig repo'dan geri gelsin" (`:17-18`).
  - Arena için: "glibc thread başına ayrı malloc arena açar; PDF/görüntü dönüşümünün dev
    geçici tahsisleri arena'larda kalıp RSS'i kalıcı yükseltiyordu (2026-07-29 OOM
    incelemesi). 2 arena, 2 vCPU için yeterli" (`:61-63`).
  - Backend limitinin kabul edilen sonucu: "Limit aşımında konteyner OOM-kill edilir ve
    restart olur — **tüm VM'in ağ/SSH kaybetmesinden iyidir**" (`:76-78`).
- **Reddedilenler:** *Swap'ı açık bırakıp limiti yükseltmek* — arıza mekanizması swap'ın
  kendisiydi. *Limitleri yalnız sunucuda tutmak* — VM yeniden kurulumunda kaybolurdu.
- **Tamamlayıcı:** `infra/scripts/mem-watch.sh` 5 dakikada bir anon/file bellek yazar ve
  eşiği aşınca `KRITIK` satırı üretir; amacı incelemede yazılı — tekrarında kök nedeni
  "tahminle değil veriyle" yakalamak. Görüntü boyut korumaları ve dönüşüm semafor sayıları
  aynı kararın parçasıdır ve bilinçle `settings.py`'ye taşınmamıştır
  (`backend/config/settings.py:25-27`).
- **Test:** `backend/tests/test_faz1_infra.py`
- **İlgili:** [`docs/mimari/deploy-ve-altyapi.md`](../mimari/deploy-ve-altyapi.md)
