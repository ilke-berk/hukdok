# Deploy ve altyapı — deploy.sh, rollback, systemd birimleri, izleme

> **Son doğrulama: 2026-08-12 · 2de8d20** (§1 test kapısı G038 ile eklendi)
> Her iddia koddan doğrulanmıştır. Kod ile çelişirse kod haklıdır — bu dosyayı düzelt.

> **Push ve deploy daima insan kararıdır.** Otomasyon oturumları `git push`, `ssh`,
> `gcloud`, deploy/rollback koşmaz.

## 1. `deploy.sh`

Kullanım: sunucuda, mesai dışı — `cd ~/hukdok && ./deploy.sh`. Akış dosyanın başındaki
yorumda yazılıdır (`deploy.sh:7-10`): önkoşullar → `git pull --ff-only` → pre-deploy
`pg_dump` → build (eski stack ÇALIŞIRKEN) → imajlara git-SHA etiketi → **test kapısı** →
`up -d` → `/healthz` kapısı (120 sn) → etiket bakımı (son 3) + dangling temizliği.

Beş tasarım tercihi, gerekçeleriyle (`deploy.sh:12-30`):

| Tercih | Gerekçe (kodda yazılı) |
| --- | --- |
| `down` YOK | build çalışan stack'i etkilemez; kesinti yalnız `up`'taki konteyner değişimi ("dakikalar → saniyeler") |
| `git pull --ff-only` başarısızsa **DURUR** | eskiden hata yutulup ESKİ kodla sessizce devam ediliyordu |
| Sağlık kapısı gerçek | `/healthz` 120 sn poll, başarısızsa `exit 1` + rollback komutu basılır (eskiden `sleep 5` + `docker ps`) |
| İmajlar SHA ile etiketlenir | `docker image prune -f` artık rollback hedeflerini silemez (etiketli imaj dangling olmaz) |
| Test kapısı (G038) | build'den SONRA, `up`'tan ÖNCE koşar — testler kalırsa deploy DURUR, çalışan stack'e hiç dokunulmaz (kırık kod prod'a çıkamaz) |

### Güvenlik kapıları

- **`.env` zorunlu anahtar denetimi** (`deploy.sh:118-125`): `POSTGRES_PASSWORD`,
  `DATABASE_URL`, `GEMINI_API_KEY`, `AZURE_CLIENT_ID`, `ALLOWED_TENANTS`,
  `SHAREPOINT_TENANT_ID`, `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_CLIENT_SECRET` — biri boşsa
  deploy iptal.
- **`hukuk_shared` ağı** yoksa oluşturulur (`:128-131`).
- **Pre-deploy dump** (`:146-157`): `docker exec hukudok-postgres pg_dump -U hukudok_user -Fc
  hukudok > ~/backups/predeploy_<SHA>_<zaman>.dump`. Dump `MIN_DUMP_BYTES` (varsayılan 1 MiB)
  altındaysa **deploy iptal**. Gerekçe: "Migration'lar açılışta otomatik koşar; kötü bir
  migration'ın tek geri yolu bu dump'tır (rollback.sh imaj döndürür, DB'yi DÖNDÜRMEZ)"
  (`:147-148`). `hukudok-postgres` çalışmıyorsa adım atlanır (ilk kurulum senaryosu).
- **Rollback hedefini koruma** (`:162-171`): build `:latest`'i yeni imaja taşıyacağı için eski
  imaj SHA etiketi taşımıyorsa önce etiketlenir — rollback hedefi dangling'e düşmesin.
- **Test kapısı** (`:67-98` tanım, `:184-185` çağrı) — aşağıda ayrı başlık.
- **Sürüm doğrulaması** (`:205-213`): `/healthz`'in `version` alanı yeni SHA'yı göstermeli.
  Bu bir **uyarıdır, fail değil** — lokal mount/elle build senaryolarında meşru sapma
  olabilir; prod'da bayat imaj işaretidir.
- **Frontend poll'u** (`:214-225`): konteyner "Started" ile nginx'in porta geçmesi arasında
  1-2 sn yarış var; tek atımlık `curl` buna yakalanmıştı → 30 sn poll.

Ortam düğmeleri (`deploy.sh:32-35`): `MIN_DUMP_BYTES` (lokal prova: 1), `PRUNE` (lokal
prova: 0), `SKIP_TESTS` (aşağıda). Saklanan etiket sayısı `KEEP_TAGS=3` (`:47`).

### Test kapısı (G038)

`test_gate()` (`deploy.sh:67-98`) build'den **sonra**, `up -d`'den **önce** koşar
(`:184-185`). Testler kalırsa deploy `exit 1` ile durur ve çalışan stack'e hiç dokunulmaz —
kırık kod prod'a çıkamaz. Ölçülen süre: **~45-47 sn** (pip install ~9 sn + 1035 test ~37 sn);
120 sn'lik `/healthz` kapısıyla birlikte deploy'un toplam kapı bütçesi bu iki sayıdır.

Kapı, YENİ imajdan tek seferlik bir konteyner kaldırır (`docker run --rm`), çalışan
konteynerlere dokunmaz. İki tasarım kısıtı kodda yazılı:

- **`docker compose run` BİLEREK kullanılmaz.** Compose servisi olarak koşmak `.env`'i
  (gerçek `DATABASE_URL`) beraberinde getirirdi; `tests/conftest.py` `DATABASE_URL`'i
  `setdefault` ile koyduğu için gerçek URL korunur ve `tests/test_migration_path.py`
  ulaştığı Postgres'te scratch veritabanı yaratıp düşürür — yani kapı **prod postgres'e
  DDL koşturabilirdi**. Temiz ortamlı `docker run` bu yüzden şart.
- **Test kodu imajda YOKTUR** (`backend/.dockerignore:35` `tests/` dışlar), bu yüzden
  çalışma ağacındaki `backend/` **salt-okunur** mount edilir: kütüphane ortamı yeni imajdan,
  test kodu `git pull`'un getirdiği ağaçtan gelir — ikisi de aynı commit'tir. Salt-okunur
  mount yüzünden `-p no:cacheprovider` ve `PYTHONDONTWRITEBYTECODE=1` şarttır.

**Kapının bilinçli sınırı — migration testleri KOŞMAZ.** Kapı temiz ortamda (`.env` yok,
dolayısıyla `DATABASE_URL` yok) koştuğu için DB gerektiren testler atlanır: kapıda
**1035 passed / 8 skipped**, çalışan konteynerde (`docker compose exec -T backend python -m
pytest`) **1041 passed / 2 skipped** — aradaki 6 test `tests/test_migration_path.py`'nin
`dbtest`'leridir (scratch veritabanı yaratıp düşürürler). Bu, kapının prod postgres'e
dokunmamasının bedelidir: **bozuk bir migration kapıdan geçer.** Onu yakalayan iki savunma
başka yerde — CI (`.github/workflows/ci.yml`, postgres servisi + `DATABASE_URL` ile
`dbtest`'leri koşar) ve pre-deploy `pg_dump`.

Üç çıkış yolu:

| Durum | Davranış |
| --- | --- |
| Testler geçti | `✅ Test kapısı GEÇTİ (N sn)`, deploy devam eder |
| Testler kaldı | `❌ Test kapısı KALDI` + `exit 1` — `up -d` hiç çalışmaz |
| Dev bağımlılıkları kurulamadı (pip ağ erişimi yok) | Konteyner **91** döner → **gürültülü uyarı** basılır ama deploy **DURMAZ** (sessiz atlama yasak) |

`SKIP_TESTS=1 ./deploy.sh` kaçış kapısıdır: kapıyı atlar ve çerçeveli bir uyarı basar
("Prod'a TEST EDİLMEMİŞ kod çıkıyor").

**`./deploy.sh --gate-only`** (`:103-111`): yalnız test kapısını koşar ve çıkar. Dal
`git pull`'dan **önce** döndüğü için pull / dump / build / `up -d` hiç çalışmaz; henüz build
olmadığından mevcut `:latest` imajı üzerinden koşar. Kapının davranışını prod'a dokunmadan
kanıtlamanın yoludur. `MSYS_NO_PATHCONV=1` (`:50-54`) yalnız Git Bash içindir — Linux'ta
hiçbir şey yapmaz; onsuz lokal prova docker'ın `-w /app` argümanı bozulduğu için çıkış 125
verir.

## 2. `rollback.sh`

`./rollback.sh <git-kısa-sha>` — argümansız çağrıldığında mevcut geri dönüş etiketlerini
listeler. deploy.sh'ın SHA-etiketli imajlarına döner: `:${SHA}` → `:latest` etiketlenir ve
`docker compose up -d --no-build` koşar; ardından aynı sağlık kapısı işler.

Dosyanın kendi notu (`rollback.sh:7-12`):

> Yalnız İMAJLARI döndürür; git checkout'a ve DB'ye DOKUNMAZ.
> - Kötü migration durumunda `~/backups/predeploy_*.dump`'tan restore gerekir.
> - Rollback sonrası `:latest` etiketi git HEAD'den farklı imajı gösterir; sonraki
>   `./deploy.sh` bunu yeniden hizalar.

## 3. `/healthz` kapısı

Derin sağlık ucu; ok/degraded/unhealthy kuralları ve 10 sn TTL cache için bkz.
[`genel-bakis.md` §6](genel-bakis.md#6-healthz--derin-sağlık-ucu).

Aynı uç dört yerden yoklanır ve dördü de farklı şey yapar:

| Yoklayan | Aralık | Başarısızlıkta |
| --- | --- | --- |
| `deploy.sh` kapısı | 3 sn, 120 sn tavan | deploy `exit 1` + rollback komutu |
| Docker healthcheck (`docker-compose.yml:86-97`) | 30 sn, 3 retry, 60 sn start_period | konteyner "unhealthy" **işaretlenir**; Docker restart ETMEZ (`:90-92`) |
| Konteyner nginx `location = /healthz` | — | exact match şart; backend down → 502, DB down → 503 (`nginx.conf:27-31`) |
| GCP uptime check | — | alarm |

Healthcheck komutu `curl` değil stdlib `urllib` kullanır — `python:slim` imajında `curl`
yoktur (`docker-compose.yml:87-88`).

## 4. Sürüm izi

```
deploy.sh: export APP_VERSION="$NEW_SHA"   (deploy.sh:175)
  → docker-compose.yml build args: APP_VERSION: ${APP_VERSION:-dev}   (:40-42, :109-111)
    → backend Dockerfile ARG/ENV  → /healthz "version"
    → frontend Dockerfile ARG     → VITE_APP_VERSION → login rozeti
```

Elle build'de `dev` düşer (`docker-compose.yml:41`).

## 5. `infra/` envanteri

Tümü sunucuya `sudo bash infra/install.sh` ile konuşlandırılır (idempotent: içerik aynıysa
dosyaya dokunmaz; nginx yalnız config değiştiyse ve `nginx -t` geçerse reload edilir).

| Yol | Hedef | İş |
| --- | --- | --- |
| `infra/nginx/sites-available/default` | host nginx | hukukoid.com HTTPS (Let's Encrypt) → frontend :8080; **timeout'ları konteyner nginx ile eşit tutulmalı** |
| `infra/nginx/sites-available/hukbot` | host nginx | hukbot.tragic.tr → :3000 (hukukbot-ui stack'i) |
| `infra/systemd/db-backup.{service,timer}` | systemd | gecelik pg_dump — `OnCalendar=*-*-* 00:30:00` (UTC) = 03:30 TR, `Persistent=true` |
| `infra/systemd/net-watchdog.{service,timer}` | systemd | ağ nöbetçisi — `OnBootSec=2min`, `OnUnitActiveSec=1min` |
| `infra/systemd/mem-watch.{service,timer}` | systemd | bellek kaydı — `OnBootSec=3min`, `OnUnitActiveSec=5min` |
| `infra/scripts/backup_db.sh` | `~/backup_db.sh` | dump + SharePoint kopyası + 14 gün rotasyon |
| `infra/scripts/net-watchdog.sh` | `/usr/local/bin` | metadata + yerel ağ probu, kademeli müdahale |
| `infra/scripts/mem-watch.sh` | `/usr/local/bin` | sistem + konteyner bellek satırı |
| `infra/docker/daemon.json` | `/etc/docker/daemon.json` | json-file log rotasyonu 50m×3 |
| `infra/gcp/ops-agent-config.yaml` | Ops Agent | konteyner + watchdog loglarını Cloud Logging'e taşır |
| `infra/gcp/policy-*.json`, `apply_monitoring.sh` | GCP projesi | log tabanlı metrik + 3 alarm politikası |

`Persistent=true` önemlidir: **sunucuda cron yoktur**, systemd timer tek desendir; makine
tetikleme anında kapalıysa açılışta telafi eder.

## 6. Yedekleme

İki ayrı yedek var, ikisi de `pg_dump -Fc` (custom format, sıkıştırılı):

- **Pre-deploy** — `deploy.sh` alır, `~/backups/predeploy_<SHA>_<zaman>.dump`.
- **Gecelik** — `infra/scripts/backup_db.sh`, `db-backup.timer` ile 00:30 UTC (03:30 TR).
  Akış script'in başında yazılı: `pg_dump` → boyut kontrolü → SharePoint `02_YEDEK_ARSIV`'e
  kopya (backend konteynerinin app-only Graph kimliğiyle) → 14 günden eski yerel dump'ların
  temizliği.

Script'in kendi uyarısı: **"Dump kişisel veri içerir; SharePoint klasörü app-only
erişimlidir, dump'ı başka yere kopyalamayın."**

Boyut kontrolü küçük dump'ı SharePoint'e yüklemez — sessizce boş yedek biriktirmeye karşı.
Geri dönüş adımları `infra/README.md`'nin "Yedekten geri dönüş" bölümündedir.

## 7. Nöbetçiler

### Ağ nöbetçisi (`infra/scripts/net-watchdog.sh`)

2026-07-29'da ens4 "Failed" durumunda kalıp sunucu ~7 saat ağsız kaldıktan sonra kuruldu.
Tasarım notları script'in başında (`net-watchdog.sh:4-13`):

- Kutuda `ping` **kurulu değil**; erişilebilirlik üç yapısal sinyalle ölçülür: global IPv4
  adresi, default route, networkd'nin `routable` görüşü. 2026-07-29 arızasında üçü de
  başarısız olurdu.
- **Metadata erişilemez ama yerel ağ sağlıklıysa MÜDAHALE EDİLMEZ.** Aksi halde Google
  tarafındaki bir metadata kesintisinde çalışan siteyi dakikada bir `networkd` restart'ıyla
  sarsardık.
- Uzun arızada müdahale backoff'a girer: ilk turlarda her tur, sonra 10 turda bir.

Kritik durumda log'a `KRITIK` satırı yazılır — GCP alarmı bunu yakalar.

### Bellek nöbetçisi (`infra/scripts/mem-watch.sh`)

Amaç script'te yazılı (`mem-watch.sh:4-7`): 2026-07-29'daki OOM'un (backend anon 3.57 GB)
tekrarında kök nedeni "tahminle değil veriyle" yakalamak — o gece eğilim verisi olmadığı
için sızıntının yeri kod okuyarak bulunamamıştı.

Her 5 dakikada sistem ve konteyner belleğini yazar. `anon` = gerçek bellek (sızıntı buradan
görülür), `file` = sayfa önbelleği (baskı altında kendiliğinden bırakılır, zararsız)
(`mem-watch.sh:8-10`). Backend anon değeri eşiği aşınca `KRITIK` satırı yazılır.

## 8. GCP izleme

`infra/gcp/ops-agent-config.yaml` üç kaynağı Cloud Logging'e taşır: Docker json-file
logları (iki katmanlı JSON parse + `severity` yükseltme), `net-watchdog.log`, `mem-watch.log`.
Backend'in `LOG_FORMAT=json` ayarı (`docker-compose.yml:65-68`) tam da bu zincir içindir.

`infra/gcp/apply_monitoring.sh` **lokal makineden** koşar (gcloud auth'lu) ve idempotenttir:
log tabanlı metrik + `infra/gcp/policy-*.json`'daki üç alarm politikasını uygular:

| Politika | Neyi yakalar |
| --- | --- |
| `policy-backend-error-rate.json` | backend ERROR satırı oranı |
| `policy-oom-kill.json` | kernel OOM kill (syslog) |
| `policy-watchdog-kritik.json` | net-watchdog / mem-watch `KRITIK` satırları |

Bu üçü `/healthz`'in `degraded` durumunu **tamamlar**: `degraded` 200 döndüğü için uptime
alarmı tetiklemez, gerçek alarm log yolundan gelir.

## 9. CI

`.github/workflows/ci.yml` iki bağımsız job koşar: **backend** (`ruff` → `mypy` → `pytest`,
PostgreSQL servis konteyneriyle) ve **frontend** (`npm ci` → lint → `tsc --noEmit` → vitest
→ build). Python ve Node sürümleri prod imajlarıyla hizalıdır.

Dosyanın notu: merge kapısı için GitHub'da branch protection **manuel** ayarlanır
(Settings → Branches → main → Require status checks: backend, frontend).

## 10. Gece otomasyonu

`otomasyon/` altında iki koşucu var; ikisi de sıfır-context Claude oturumları açar ve her
işi **ayrı, temiz bir oturumla denetletir**:

- **`gece-kosusu.ps1`** — sertleştirme paketlerini `docs/plan/guvenilirlik-sertlestirme-uygulama-takibi.md`
  (tek doğruluk kaynağı) üzerinden yürütür: `faz-devam` (kod+test+doküman+commit) →
  `faz-denetle` (temiz context). Denetim `RET` verirse koşu durur, commit geri alınmaz.
- **`kuyruk-kosusu.ps1`** — `gorevler/KUYRUK.md`'deki işleri **şerit** bazlı paralel yürütür:
  `gorev-devam` → `gorev-denetle` → (GECTI ise) worktree dalını ana dala birleştirme.

### Şerit modeli

| Şerit | Nerede koşar | Test |
| --- | --- | --- |
| `backend` | **ANA dizin, seri** | `docker compose exec -T backend python -m pytest` |
| `frontend` | ayrı git worktree | `npm --prefix frontend test` (host'ta) |
| `docs` | ayrı git worktree | test yok |

Backend'in şerit olmasının gerekçesi script'te yazılı: konteyner ana dizini bind-mount eder,
pytest yalnız ana dizindeki kodu doğru test eder. Bu yüzden `bant:frontend` görevlerinde
`docker compose` komutları **yasaktır** — konteyner worktree kodunu test etmez, sonuç
yanıltıcı olur (`.claude/skills/gorev-devam/SKILL.md:34-36`).

Karar kaydı: [`006-gece-otomasyonu-serit-modeli.md`](../kararlar/006-gece-otomasyonu-serit-modeli.md).

Her iki koşucu da koşulsuz yasaklarla kilitlidir: `git push`, `ssh`, `gcloud`,
deploy/rollback scriptleri, `docker compose down -v`, `git reset --hard`.
