# infra/ — host-seviyesi konfigürasyonun repo kopyası (Faz 1-B)

Amaç: VM kaybolsa bile bilinen-iyi host konfigürasyonu `git clone` +
`sudo bash infra/install.sh` ile geri gelsin. Dosyalar 2026-08-08'de sunucudan
(`ssh hukukoid`) birebir çekildi ve diff ile doğrulandı. Bundan sonra değişiklik
ÖNCE repo'da yapılır, sunucuya install.sh ile işlenir — sunucuda elle düzenleme
= izlenemeyen sapma.

## Envanter

| Repo | Sunucu hedefi | Ne işe yarar |
|---|---|---|
| `nginx/sites-available/default` | `/etc/nginx/sites-available/default` + `sites-enabled` symlink | hukukoid.com TLS ucu (Let's Encrypt), 50M upload limiti, **300 sn proxy timeout** (uzun /confirm–Ghostscript akışı; container nginx'teki eşi f72f13e); tüm trafik → frontend konteyneri :8080 |
| `nginx/sites-available/hukbot` | `/etc/nginx/sites-available/hukbot` + symlink | hukbot.tragic.tr → :3000. Sahibi hukukbot-ui stack'i; VM yeniden kurulumunda eksik kalmasın diye kopyası burada tutulur |
| `systemd/net-watchdog.{service,timer}` | `/etc/systemd/system/` | Ağ nöbetçisi, dakikada bir (2026-07-29 ens4/DHCP arızası sonrası); yerel ağ bozuksa kademeli müdahale, log `/var/log/net-watchdog.log` |
| `systemd/mem-watch.{service,timer}` | `/etc/systemd/system/` | 5 dk'da bir sistem+konteyner bellek kaydı; backend anon ≥1500 MB'de KRITIK satırı (OOM eğilim verisi), log `/var/log/mem-watch.log` |
| `systemd/db-backup.{service,timer}` | `/etc/systemd/system/` | Gecelik Postgres yedeği 00:30 UTC = 03:30 TR, `Persistent=true` (sunucuda cron YOK, tek desen systemd timer) |
| `scripts/net-watchdog.sh` | `/usr/local/sbin/net-watchdog.sh` | net-watchdog.service'in ExecStart'ı |
| `scripts/mem-watch.sh` | `/usr/local/sbin/mem-watch.sh` | mem-watch.service'in ExecStart'ı |
| `scripts/backup_db.sh` | `/home/luciferandlucius/backup_db.sh` (sahip: luciferandlucius — db-backup.service `User=` ve `ExecStart=` bu yolu bekler) | pg_dump -Fc → boyut kontrolü (<1 MB hata; dolu dump ~1.7 MB) → SharePoint `02_YEDEK_ARSIV`'e `db_backup_YYYY-MM-DD.dump` (backend konteynerindeki `scripts/upload_db_backup.py` ile) → yerelde 14 gün saklama; log `~/backups/backup.log` |
| `docker/daemon.json` | `/etc/docker/daemon.json` | json-file log rotasyonu (50m×3) daemon default'u. docker-compose.yml aynı ayarı servis bazında da taşır (Faz 1-A); daemon.json compose dışı konteynerler için emniyet |

## Kurulum / güncelleme (sunucuda)

```bash
ssh hukukoid
cd ~/hukdok && git pull --ff-only
sudo bash infra/install.sh
```

install.sh idempotenttir: içerik aynıysa dokunmaz; nginx'i yalnızca config
değiştiyse ve `nginx -t` geçerse reload eder; üç timer'ı `enable --now` yapar;
docker daemon'ı yeniden BAŞLATMAZ (daemon.json değiştiyse mesai dışı elle
`sudo systemctl restart docker`).

Yeni VM önkoşulları (install.sh bunları kurmaz): `luciferandlucius` kullanıcısı,
docker + compose eklentisi, nginx + certbot (sertifikalar
`/etc/letsencrypt/live/hukukoid.com/` ve `.../hukbot.tragic.tr/` — certbot ile
yeniden üretilir), `docker network create hukuk_shared`, `~/hukdok` repo
klonu + `.env`.

## Bilinen sunucu sapmaları (2026-08-08 envanteri)

- `sites-available/hukukoid.com`: ESKİ mimarinin kalıntısı (enable değil,
  /api → :8000 süren sürüm). install.sh dokunmaz; 1-C provasında elle silinebilir.
- `~/hukdok/docker-compose.override.yml`: bellek limitleri artık repo
  docker-compose.yml'inde (Faz 1-A) — Deploy #2 sonrası override gereksiz,
  kaldırılması 1-C provasında.
- Dump kişisel veri içerir; SharePoint klasörü app-only erişimlidir, dump'ı
  başka yere kopyalamayın.

## Yedekten geri dönüş (backup_db.sh çıktısı)

```bash
# Seçmeli veya tam restore (boş DB'ye):
pg_restore --list hukudok_YYYY-MM-DD.dump            # içeriği gör
createdb -U hukudok_user hukudok_restore
pg_restore -U hukudok_user -d hukudok_restore hukudok_YYYY-MM-DD.dump
psql -U hukudok_user -d hukudok_restore -c "SELECT count(*) FROM cases;"
```

SharePoint kopyaları `02_YEDEK_ARSIV` kökünde `db_backup_*.dump` desenindedir
(teknik loglarla aynı klasör; arama endpoint'i geride kalabilir, children ile
listeleyin). 2026-08-05 geri dönüş tatbikatında restore denendi, sayımlar
birebir çıktı (bkz. 345eda3).

## Doğrulama

```bash
ssh hukukoid 'systemctl list-timers --no-pager | grep -E "db-backup|mem-watch|net-watchdog"'
ssh hukukoid 'tail -3 ~/backups/backup.log; sudo tail -3 /var/log/net-watchdog.log /var/log/mem-watch.log'
```
