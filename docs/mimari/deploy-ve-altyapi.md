# Deploy ve altyapı — deploy.sh, rollback, systemd birimleri, izleme

> **Son doğrulama: 2026-08-12 · G050** (§1 test kapısı artık kendi Postgres'ini kaldırır);
> §1 `.env` anahtar listesi 2026-09-08 · G148 ile G147 sonrası koda göre yeniden doğrulandı;
> 17.09.2026'da `TESLIM_SHAREPOINT_*` maddesi kaldırıldı (teslim klasörü yolu kod dışı).
> §13 2026-09-14 · G191: lokal stack recreate sonrası `SHOW` çıktıları ve pg_stat_statements sorgusu koşularak doğrulandı.
> 2026-09-14 · G193: §3/§4/§8/§11 `docker-compose.yml` ve `nginx.conf` satır atıfları G182/G191 sonrası koda göre
> yeniden okundu; §11 önbellek başlıkları ve §12 D9/doğrulama sırası koddan; §13 `SHOW` ve en pahalı 10 sorgu
> komutları lokal `hukudok-postgres`'te yeniden koşuldu.
> 2026-09-26: §1 test kapısı varsayılanda ŞEMA KAPISI'na indi (kullanıcı kararı; tam paket `--with-tests`) —
> lokal `--gate-only` provası (şema yolu) 8 sn ölçüldü.
> Her iddia koddan doğrulanmıştır. Kod ile çelişirse kod haklıdır — bu dosyayı düzelt.

> **Push ve deploy daima insan kararıdır.** Otomasyon oturumları `git push`, `ssh`,
> `gcloud`, deploy/rollback koşmaz.

## 1. `deploy.sh`

Kullanım: sunucuda, mesai dışı — `cd ~/hukdok && ./deploy.sh`. Akış dosyanın başındaki
yorumda yazılıdır (`deploy.sh:7-10`): önkoşullar → `git pull --ff-only` → pre-deploy
`pg_dump` → build (eski stack ÇALIŞIRKEN) → imajlara git-SHA etiketi → **şema kapısı**
(`--with-tests` ile tam test kapısı) → `up -d` → `/healthz` kapısı (120 sn) → etiket bakımı
(son 3) + dangling temizliği.

**Varsayılan kapı = şema kapısı (26.09.2026 kullanıcı kararı).** Tam test paketi sunucuda
(2 çekirdek / 3 GB) ~3.600 testte ~13 dk sürüyordu; aynı paket her push'ta GitHub CI'da koşar
ve CI `success` olmadan deploy yapılmaz (`deploy-prosedur` §1) — sunucuda tekrarı yalnız süre
ekliyordu. Kalan, sunucuya özgü ucuz kısım: yeni imajdan tek seferlik konteyner, kapının
geçici Postgres'inde `python migrate.py` (lokal prova 8 sn). Bozuk migrasyon prod'da
entrypoint'te konteyneri kaldırmaz; bunu `up`'tan önce yakalamak kesintiyi önler. Tam kapı için
`./deploy.sh --with-tests` (ya da `FULL_TESTS=1`); `--gate-only` daima tam paketi koşar.
Bedel: imaja/sunucuya özgü bir test kırılması (ör. CI ile imaj arasında paket farkı) artık
deploy'da yakalanmaz.

Altı tasarım tercihi, gerekçeleriyle (`deploy.sh:12-35`):

| Tercih | Gerekçe (kodda yazılı) |
| --- | --- |
| `down` YOK | build çalışan stack'i etkilemez; kesinti yalnız `up`'taki konteyner değişimi ("dakikalar → saniyeler") |
| `git pull --ff-only` başarısızsa **DURUR** | eskiden hata yutulup ESKİ kodla sessizce devam ediliyordu |
| Sağlık kapısı gerçek | `/healthz` 120 sn poll, başarısızsa `exit 1` + rollback komutu basılır (eskiden `sleep 5` + `docker ps`) |
| İmajlar SHA ile etiketlenir | `docker image prune -f` artık rollback hedeflerini silemez (etiketli imaj dangling olmaz) |
| Test kapısı (G038) | build'den SONRA, `up`'tan ÖNCE koşar — kalırsa deploy DURUR, çalışan stack'e hiç dokunulmaz. 26.09.2026'dan beri varsayılanda yalnız şema (`migrate.py`), tam paket `--with-tests` |
| Kapının kendi Postgres'i (G050) | temiz ortamın bedeli DB testlerinin SKIP olmasıydı; kapı artık kendi tek kullanımlık Postgres'ini kaldırır — prod DB'ye yine hiç dokunmaz |

### Güvenlik kapıları

- **`.env` zorunlu anahtar denetimi** (`deploy.sh:259-267`): `POSTGRES_PASSWORD`,
  `DATABASE_URL`, `GEMINI_API_KEY`, `AZURE_CLIENT_ID`, `ALLOWED_TENANTS`,
  `SHAREPOINT_TENANT_ID`, `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_CLIENT_SECRET` — biri boşsa
  deploy iptal (`REQUIRED_KEYS`, `:260-262`).
- **`TESLIM_SHAREPOINT_*` / `SHAREPOINT_FOLDER_TESLIM_NAME` artık okunmaz** (17.09.2026: veri
  teslim klasörü yolu ve G147 ikinci kimliği koddan çıktı). Prod `.env`'de kalmışlarsa zararsızdır;
  silmek insan adımıdır. Mevcut kural aynen geçerli: **`.env` değişikliği `restart` ile GELMEZ** —
  env yalnız konteyner create'te okunur, `docker compose up -d` (recreate) gerekir; yalnız backend'i
  recreate etmek frontend nginx'i bayat upstream IP'de bırakabildiği için stack'in tamamı
  `up -d` edilir (kurulum sırası [`veri-teslim-hatti.md` §9](veri-teslim-hatti.md)).
- **`hukuk_shared` ağı** yoksa oluşturulur (`:269-272`).
- **Pre-deploy dump** (`:287-301`): `docker exec hukudok-postgres pg_dump -U hukudok_user -Fc
  hukudok > ~/backups/predeploy_<SHA>_<zaman>.dump`. Dump `MIN_DUMP_BYTES` (varsayılan 1 MiB)
  altındaysa **deploy iptal**. Gerekçe: "Migration'lar açılışta otomatik koşar; kötü bir
  migration'ın tek geri yolu bu dump'tır (rollback.sh imaj döndürür, DB'yi DÖNDÜRMEZ)"
  (`:288-289`). `hukudok-postgres` çalışmıyorsa adım atlanır (ilk kurulum senaryosu).
- **Rollback hedefini koruma** (`:303-312`): build `:latest`'i yeni imaja taşıyacağı için eski
  imaj SHA etiketi taşımıyorsa önce etiketlenir — rollback hedefi dangling'e düşmesin.
- **Test kapısı** (`:195-239` tanım, `:325-326` çağrı) — aşağıda ayrı başlık.
- **Sürüm doğrulaması** (`:346-354`): `/healthz`'in `version` alanı yeni SHA'yı göstermeli.
  Bu bir **uyarıdır, fail değil** — lokal mount/elle build senaryolarında meşru sapma
  olabilir; prod'da bayat imaj işaretidir.
- **Frontend poll'u** (`:355-367`): konteyner "Started" ile nginx'in porta geçmesi arasında
  1-2 sn yarış var; tek atımlık `curl` buna yakalanmıştı → 30 sn poll.

Ortam düğmeleri (`deploy.sh:37-40`): `MIN_DUMP_BYTES` (lokal prova: 1), `PRUNE` (lokal
prova: 0), `FULL_TESTS` (1 = `--with-tests`), `SKIP_TESTS` (aşağıda). Saklanan etiket sayısı `KEEP_TAGS=3` (`:53`).

### Test kapısı (G038 · G050)

`test_gate()` (`deploy.sh:195-239`) build'den **sonra**, `up -d`'den **önce** koşar
(`:327`). Testler kalırsa deploy `exit 1` ile durur ve çalışan stack'e hiç dokunulmaz —
kırık kod prod'a çıkamaz. Ölçülen süre: **~59-61 sn** (geçici Postgres kalkışı ~5 sn +
pip install ~7 sn + `migrate.py` ~1 sn + 1190 test ~45 sn). G050 öncesi 44 sn'ydi; 15 sn'lik
artış DB gerektiren 29 testin artık **gerçekten koşmasının** bedelidir. 120 sn'lik
`/healthz` kapısıyla birlikte deploy'un toplam kapı bütçesi bu iki sayıdır.
`gate_db_up`/`gate_db_down`/`gate_sweep_orphan_networks` tanımları `:68-182`.

Kapı, YENİ imajdan tek seferlik bir konteyner kaldırır (`docker run --rm`), çalışan
konteynerlere dokunmaz. Üç tasarım kısıtı kodda yazılı:

- **`docker compose run` BİLEREK kullanılmaz.** Compose servisi olarak koşmak `.env`'i
  (gerçek `DATABASE_URL`) beraberinde getirirdi; `tests/conftest.py` `DATABASE_URL`'i
  `setdefault` ile koyduğu için gerçek URL korunur ve `tests/test_migration_path.py`
  ulaştığı Postgres'te scratch veritabanı yaratıp düşürür — yani kapı **prod postgres'e
  DDL koşturabilirdi**. Temiz ortamlı `docker run` bu yüzden şart.
- **Test kodu imajda YOKTUR** (`backend/.dockerignore:35` `tests/` dışlar), bu yüzden
  çalışma ağacındaki `backend/` **salt-okunur** mount edilir: kütüphane ortamı yeni imajdan,
  test kodu `git pull`'un getirdiği ağaçtan gelir — ikisi de aynı commit'tir. Salt-okunur
  mount yüzünden `-p no:cacheprovider` ve `PYTHONDONTWRITEBYTECODE=1` şarttır.
- **Kapının kendi Postgres'i vardır** (G050, `:68-182`) — aşağıda.

#### Kapının kendi Postgres'i (G050)

Temiz ortamın bedeli, DB gerektiren testlerin **SKIP** olmasıydı; SKIP yeşil sayıldığı için
kapı **29 testi koşmadan** "geçti" diyordu (2026-08-12 ölçümü: kapıda 1158 passed/32
skipped, çalışan konteynerde 1187 passed/3 skipped). FAZ D'nin migrasyon-yolu,
index-envanteri ve esas-tarihçesi testleri de aynı deliğe düşmüştü.

Çözüm prod DB'ye bağlanmak **değil** (o yol tam olarak yukarıdaki birinci kısıtın
reddettiği yoldur): kapı `gate_db_up()` ile **kendi tek kullanımlık Postgres'ini** kaldırır.

| Kısıt | Nasıl |
| --- | --- |
| Prod verisine temas yok | Boş `postgres:15-alpine`, `gate/gate@gatedb`; prod `.env` bu konteynere hiç girmez |
| Ağ yalıtımı | Kendi ağı (`hukdok_gate_net_<pid>_<rnd>`); `hukuk_shared` / compose ağına **bağlanmaz** |
| Port yayınlanmaz | `-p` yok, `--network host` yok — yalnız kapı ağından erişilebilir |
| Çakışmaya dayanıklı | Ad PID+`$RANDOM`'dan türer, üstelik `docker container/network inspect` ile boşta olduğu doğrulanır (5 deneme) |
| Her yolda silinir | `gate_db_down()` hem doğrudan çağrılır hem `trap ... EXIT INT TERM` ile yedeklenir; sıra: test konteyneri → postgres → ağ (ağ 5×1 sn yeniden dener), silinemeyen kalem **uyarı basar** |
| Kendi kendini toparlar | `gate_sweep_orphan_networks()` her koşuda artık kalmış kapı ağlarını siler; `docker network rm` kullanımdaki ağı reddettiği için eşzamanlı bir deploy'un ağına dokunamaz |

Konteyner içinde testlerden **önce `python migrate.py`** koşar: şema boş DB'de kurulur.
Bu hem prod entrypoint'inin yolunun provasıdır (bozuk migrasyon artık kapıda yakalanır,
konteyner prod'da kalkmadan önce) hem de "kolon yok → SKIP" diyen testlerin (`test_g046_*`)
önkoşuludur.

**Sonuç (2026-08-12 ölçümü):** kapıda **1185 passed / 5 skipped**, referans koşuda
(`docker compose exec -T backend python -m pytest`) **1187 passed / 3 skipped** — toplam
ikisinde de 1190. Kalan fark iki testtir (`test_g046_missing_required.py:574,598`): gerçek
kayıt sayısı yetersiz diyerek atlarlar, çünkü kapının veritabanı **bilinçli olarak boştur**
(prod verisi oraya kopyalanmaz). Pytest artık `-rs` ile koşar: hangi testin neden
atlandığı deploy çıktısında görünür, sessiz SKIP kalmaz.

Beş çıkış yolu:

| Durum | Davranış |
| --- | --- |
| Testler geçti | `✅ Test kapısı GEÇTİ (N sn)`, deploy devam eder |
| Testler kaldı | `❌ Test kapısı KALDI` + `exit 1` — `up -d` hiç çalışmaz |
| Şema migrasyonu boş DB'de kaldı | Konteyner **92** döner → `❌ ... şema migrasyonu BOŞ veritabanında koşmadı` + `exit 1` (bu kod prod'da entrypoint'te de düşerdi) |
| Geçici Postgres kalkmadı | `❌ Test kapısı KURULAMADI` + `exit 1` — sessizce DB'siz koşmak G050'nin kapattığı deliği geri açardı |
| Dev bağımlılıkları kurulamadı (pip ağ erişimi yok) | Konteyner **91** döner → **gürültülü uyarı** basılır ama deploy **DURMAZ** (sessiz atlama yasak) |

`SKIP_TESTS=1 ./deploy.sh` kaçış kapısıdır: şema kapısı dahil kapıyı atlar ve çerçeveli bir uyarı basar
("Prod'a TEST EDİLMEMİŞ kod çıkıyor").

**`./deploy.sh --gate-only`** (`:241-252`): yalnız test kapısını koşar ve çıkar. Dal
`git pull`'dan **önce** döndüğü için pull / dump / build / `up -d` hiç çalışmaz; henüz build
olmadığından mevcut `:latest` imajı üzerinden koşar. Kapının davranışını prod'a dokunmadan
kanıtlamanın yoludur. `MSYS_NO_PATHCONV=1` (`:55-59`) yalnız Git Bash içindir — Linux'ta
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
| Docker healthcheck (`docker-compose.yml:110-121`) | 30 sn, 3 retry, 60 sn start_period | konteyner "unhealthy" **işaretlenir**; Docker restart ETMEZ (`:115-116`) |
| Konteyner nginx `location = /healthz` | — | exact match şart; backend down → 502, DB down → 503 (`nginx.conf:101-111`) |
| GCP uptime check | — | alarm |

Healthcheck komutu `curl` değil stdlib `urllib` kullanır — `python:slim` imajında `curl`
yoktur (`docker-compose.yml:111-112`).

## 4. Sürüm izi

```
deploy.sh: export APP_VERSION="$NEW_SHA"   (deploy.sh:317)
  → docker-compose.yml build args: APP_VERSION: ${APP_VERSION:-dev}   (:51-53, :133-135)
    → backend Dockerfile ARG/ENV  → /healthz "version"
    → frontend Dockerfile ARG     → VITE_APP_VERSION → login rozeti tooltip'i ("Build: <SHA>")

frontend/package.json "version" (3.2.0)
  → vite.config.ts define → VITE_APP_RELEASE → login rozeti görünür metni ("v3.2.0")
```

Elle build'de SHA yerine `dev` düşer (`docker-compose.yml:52`); okunur sürüm build'den bağımsız,
her zaman package.json'dan gelir. İki kanal bilinçli ayrıdır: deploy kapısı SHA'yı karşılaştırır
(`deploy.sh:350-354`), kullanıcı ise okunur numarayı görür. Sürüm atlatma = `package.json` +
`package-lock.json` kökündeki iki `version` alanı (`npm ci` tutarlılık ister); bekçi
`frontend/src/pages/Login.badge.test.tsx`.

## 5. `infra/` envanteri

Tümü sunucuya `sudo bash infra/install.sh` ile konuşlandırılır (idempotent: içerik aynıysa
dosyaya dokunmaz; nginx yalnız config değiştiyse ve `nginx -t` geçerse reload edilir).

| Yol | Hedef | İş |
| --- | --- | --- |
| `infra/nginx/sites-available/default` | host nginx | hukukoid.com HTTPS (Let's Encrypt) → frontend `127.0.0.1:8080` (konteyner yalnız loopback'te dinler; `localhost` yazma — ::1 denemesi hata loglar); **timeout'ları konteyner nginx ile eşit tutulmalı** |
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
Backend'in `LOG_FORMAT=json` ayarı (`docker-compose.yml:92`) tam da bu zincir içindir.

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
PostgreSQL servis konteyneriyle) ve **frontend** (`npm ci` → lint → `npx tsc -b --force` →
vitest → build). Python ve Node sürümleri prod imajlarıyla hizalıdır.

**Çıplak `tsc --noEmit` DEĞİL, `tsc -b --force`:** kök `tsconfig.json` solution-style'dır
(`"files": []` + `references`), yani çıplak `tsc --noEmit` hiçbir dosya bulamaz ve tip
hatası dururken bile **exit 0** döner — sahte bir kapı (G026 bulgusu, G037'de gerçeğe
çevrildi). `-b` referansları gerçekten izler (`tsconfig.app.json` + `tsconfig.node.json`);
`--force` inkremental önbelleği atlar (`ci.yml:91-98`).

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

## 11. Konteyner nginx güvenlik başlıkları (G091)

Konteyner nginx beş güvenlik başlığı gönderir (`nginx.conf:53-56`): `X-Frame-Options`,
`X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` ve **zorlayıcı
`Content-Security-Policy`** (`nginx.conf:70`, G101). Beşi de `always` ile biter, yani hata
yanıtlarında (413/429/5xx) da gider. `Content-Security-Policy-Report-Only` başlığı artık
yoktur. G182'den beri beşi `/assets/` ve `/` location'larında AYNEN tekrar yazılıdır
(`nginx.conf:81-85`, `:94-98`): `add_header` kalıtım kuralı gereği `Cache-Control` ekleyen
location server düzeyindeki başlıkları devralmaz (`nginx.conf:48-51`).

**Tarihçe — neden önce Report-Only kondu (G091):** bilinen bir XSS yolu yok (React
varsayılan kaçışı var, `dangerouslySetInnerHTML` hiç kullanılmıyor), yani bu bir açık
kapatma değil derinlemesine savunmadır; ve `frontend/index.html:38`'deki inline
`<script type="application/ld+json">` bloğunun `script-src`e tabi olup olmadığı tarayıcı
sürümüne göre değiştiği için ölçmeden zorlayıcı politika yazmak sayfayı kırabilirdi.
Enforce'a geçişin ön koşulu (imaj yeniden kurulup gerçek bir turla ihlal listesinin
toplanması) **geçildi (G101)**; politika metni G091'dekiyle birebir aynı kaldı, yalnız
başlık adı değişti.

**2026-08-22 ihlal turu (lokal 8080, Report-Only başlıkla):**

- Gezilen: login (SSO), pano, `/upload`, `/cases`, `/clients`, `/activity-history`,
  `/admin`, tema geçişi, zil paneli.
- `script-src`, `style-src`, `font-src`, `img-src`, `frame-src`: **0 ihlal**. Google Fonts
  yüklendi, `index.html`'deki inline `ld+json` bloğu raporlanmadı, MSAL yönlendirmesi sorunsuz.
- `connect-src`: 32 ihlal, hepsi `http://localhost:8001` — yalnız lokal `.env`'deki
  `VITE_API_URL` artefaktı. `.env.example`/compose/`deploy.sh`'de bu değişken yok; prod API'yi
  aynı origin'den konteyner nginx proxy'siyle çağırır, dolayısıyla prod'da oluşmaz.
- Kod okumasıyla bulunan iki inline-script yazdırma popup'ı (Takvim "Yazdır", Yetki Belgesi
  "Yazdır") turun tetiklemediği enforce kırıcılardı; **G100** ön koşul olarak bunları
  kapattı (tetik popup'ın içinden değil açandan verilir).

**Deploy sonrası insan turu (zorunlu):** login → pano → Takvim "Yazdır" → Yetki Belgesi
"Yazdır" (G100) → dava kartından PDF açma → belge yükleme. Tarayıcı konsolunda "Refused to"
satırı **olmamalı**. İhlal görülürse geri dönüş: CSP başlık adına `-Report-Only` ekini geri
koymak — G182'den beri ÜÇ satırda birlikte (`nginx.conf:70`, `:85`, `:98`), ama başlık
imajdan geldiği için frontend imajı rebuild ister (`docker compose build frontend && docker compose up -d frontend`; prod'da
`deploy.sh`). Lokal `.env`'de `VITE_API_URL` doluysa `connect-src` ihlali görülür — lokal
artefakttır, prod'u temsil etmez.

Politikanın izin verdiği dış kaynaklar ve gerekçeleri koddan doğrulanmıştır:

| Direktif | Kaynak | Neden |
| --- | --- | --- |
| `style-src` | `https://fonts.googleapis.com` + `'unsafe-inline'` | Google Fonts stil dosyası (`frontend/index.html:53-55`); `'unsafe-inline'` Radix/Tailwind'in çalışma zamanında enjekte ettiği inline stiller için — daraltması ayrı iş |
| `font-src` | `https://fonts.gstatic.com` | aynı `<link>` zincirinin çektiği font dosyaları |
| `connect-src` / `frame-src` | `https://login.microsoftonline.com` | MSAL sessiz token yenilemesi bu origin'e iframe açar (`frontend/src/config/msalConfig.ts:12`) |
| `img-src` | `data:` `blob:` | `URL.createObjectURL` ile üretilen indirme/önizleme bağlantıları |

Sözdizimi denetimi çalışan stack'e dokunmadan, tek kullanımlık konteynerle koşar
(`backend` upstream'i çözülebilsin diye compose ağına bağlanır):

```
docker run --rm --network hukudok-automator-main_hukudok-network \
  -v "//c/Users/ilkeb/OneDrive/Masaüstü/hukudok-automator-main/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
  nginx:alpine nginx -t
```

### Önbellek başlıkları (G182)

Kural ve gerekçe [`genel-bakis.md` §2](genel-bakis.md): `/assets/` (hash'li parçalar)
`Cache-Control: public, max-age=31536000, immutable`, eksik parça `404` (index.html'e
düşmez); `/` ve SPA fallback `no-cache` (`nginx.conf:77-99`). Kontrol:

```
curl -sI http://localhost:8080/ | grep -i cache-control                          # no-cache
curl -s  http://localhost:8080/ | grep -o 'assets/index-[^"]*\.js'               # giriş parçası adı
curl -sI http://localhost:8080/assets/<parça>.js | grep -i cache-control         # public, max-age=31536000, immutable
curl -sI http://localhost:8080/assets/YOK.js | head -1                           # 404
```

- **Başlık imajdan gelir:** `nginx.conf` frontend imajına kopyalanır; değişiklik
  `docker compose build frontend && docker compose up -d frontend` (prod'da `deploy.sh`)
  ister. 2026-09-14'te lokal 8080'de `Cache-Control` YOKTU ve `/assets/YOK.js` 200 döndü:
  çalışan frontend imajı bu `nginx.conf`'u taşımıyordu (G182 sonrası rebuild edilmemiş).
  Beklenen çıktılar G182'nin tek kullanımlık `nginx:alpine` ölçümündedir
  (`gorevler/gorev/G182.md`).
- **Host nginx — PROD'DA DOĞRULANACAK:** repodaki kopyası (`infra/nginx/sites-available/default`)
  `add_header`/`proxy_hide_header` içermez ve her şeyi `proxy_pass http://127.0.0.1:8080`
  ile konteynere geçirir. Sunucudaki konfigin bununla aynı olduğu ve başlığın tarayıcıya
  ulaştığı yukarıdaki komutların `https://hukukoid.com` karşılığıyla deploy sonrası kontrol
  edilir (§12 doğrulama sırası).
- **Bayat parça davranışı:** açık eski sekme bir sayfaya geçince tek yenileme olmalı
  (`frontend/src/lib/chunkReload.ts`, [`genel-bakis.md` §7](genel-bakis.md)); admin olmayan
  kullanıcıda ağ sekmesinde `AdminPage-*`/`ReportsPage-*` parçası inmemeli. Bu tarayıcı
  dumanı MSAL'lı gerçek oturum ister; `gorevler/gorev/G182.md` raporunda yapılmadığı yazılıdır.

## 12. Performans ölçümü (G183)

`backend/scripts/perf_olcum.py` veritabanı performans kararlarından (VACUUM FULL / pg_repack,
index düşürme, `ck_cases_status_uclu` kısıtının `VALIDATE`'i — kısıt G195'te `NOT VALID` ile
eklendi —, bağlantı ve sunucu ayarları) ÖNCE koşulan salt okunur ölçüm raporudur. Hiçbir şeyi değiştirmez, çıktısı Markdown'dır:

```
docker compose exec -T backend python -m scripts.perf_olcum                  # EXPLAIN'siz
docker compose exec -T backend python -m scripts.perf_olcum --term <soyad>   # + arama planı
docker compose exec -T backend python -m scripts.perf_olcum --term <soyad> --out /tmp/perf_olcum.md
docker compose cp backend:/tmp/perf_olcum.md ./perf_olcum.md
```

Rapor stdout'a basılır; `--out` ayrıca konteyner içindeki dosyaya UTF-8 yazar. Bir bölüm
ölçülemezse (yetki, zaman aşımı) rapor durmaz: bölüme "Ölçülemedi" satırı düşer ve WARNING
loglanır. Log handler'ı stdout'a yazdığı için bu durumda stdout yönlendirmesine log satırı
karışabilir; temiz dosya için `--out` kullanın.

Başlıkta sürüm (`APP_VERSION`, `/healthz` "version" alanıyla aynı kaynak) ve TR saatiyle
zaman damgası vardır. Bölümler:

| # | Bölüm | Kaynak |
| --- | --- | --- |
| 1 | Şişme: en büyük 12 tablo için heap / Σ `pg_column_size` oranı, `n_dead_tup`, son (auto)vacuum | `pg_stat_user_tables` + tablo başına tam tarama |
| 2 | Sunucu ayarları: `shared_buffers`, `effective_cache_size`, `work_mem`, `random_page_cost`, `max_connections`, `idle_in_transaction_session_timeout`, `lock_timeout`, `shared_preload_libraries` | `SHOW` + `pg_settings.source` |
| 3 | Bağlantılar: durum dağılımı, "idle in transaction" sayısı ve en uzun süre | `pg_stat_activity` (ölçümün kendi bağlantısı hariç) |
| 4 | Index kullanımı: `idx_scan = 0` listesi, boyut, envanter kararı, sayaç sıfırlama tarihi | `scripts/index_envanteri.collect_indexes` + `pg_stat_get_db_stat_reset_time` |
| 5 | Veri dağılımı: `cases.status` (üçlü dışı bayraklı), `cases`/`case_foys` kimlik kolonlarının doluluğu | `cases`, `case_foys` |
| 6 | Arama planı (yalnız `--term` ile): `case_manager._search_term_ids(term, exact=False)` için `EXPLAIN (ANALYZE, BUFFERS)`, UNION kolu başına düğüm türü, satır, buffer, süre | uygulamanın gerçek arama sorgusu |

**Salt okunur güvencesi:** script'in koştuğu her SQL `salt_okunur_dogrula` süzgecinden geçer
(yalnız `SELECT`/`SHOW`/`EXPLAIN`, yazma sözcüğü yok); CLI bağlantısı ayrıca
`default_transaction_read_only=on` ile açılır. Ölçüm bağlantısının `statement_timeout`'u
120 sn'dir (uygulamanınki 30 sn). `EXPLAIN ANALYZE` sorguyu gerçekten çalıştırır, ama sorgu
yalnız bir `SELECT` UNION'udur.

**Şerh — lokal süreler prod'u TEMSİL ETMEZ.** Lokal veritabanı bir restore kopyasıdır
(yazma trafiği yok): index sayaçları restore'da sıfırlanır, tablo istatistikleri ve önbellek
durumu prod'dan farklıdır. Bölüm 1, 4 ve 6'daki sayılarla karar ancak prod çıktısı alınınca
verilir. `idx_scan = 0` bir index'i düşürmek için tek başına yetmez: unique/primary index'ler
tekillik kontrolünde bu sayacı artırmaz (bkz. `scripts/index_envanteri.py` docstring'i).

### Deploy sonrası prod doğrulama sırası (14.09 performans turu)

14.09 performans turu (G182-G195) lokal restore kopyasında ölçüldü; aşağıdakiler prod'da
deploy'dan SONRA insan tarafından koşulur (otomasyon `ssh`/deploy yapmaz). Komutların
kendisi bu dokümanın ilgili bölümündedir, burada yalnız sıra ve neye bakılacağı var:

1. **Açılış logu:** `docker compose logs --since 10m backend | grep -i "trgm\|pg_stat_statements"`
   → "Trigram (pg_trgm) arama index'leri hazır" ve "pg_stat_statements hazır"
   (`backend/database.py:1611`, `:1643`). İlk açılış `cases` üzerinde dört, `case_foys`
   üzerinde üç GIN index kurar ve 23 index düşürür (karar 018 "Nihai index durumu"); kurulum
   `CONCURRENTLY` değildir, mesai dışı deploy kuralı bunu karşılar.
2. **Postgres parametreleri:** §13 `SHOW` komutu → `384MB` / `pg_stat_statements`. Görünmüyorsa
   postgres recreate olmamıştır (`up -d` şart, §13).
3. **Önbellek başlıkları:** §11 `curl -sI` komutlarının `https://hukukoid.com` karşılığı (host nginx).
4. **`perf_olcum`:** `--term <avukat soyadı> --out` ile tam rapor. Bölüm 1 şişme → VACUUM FULL /
   pg_repack kararı (D3); bölüm 3 "idle in transaction" mesai içinde birkaç kez; bölüm 4
   `idx_scan = 0` → D7 index kararı, sayaç sıfırlama tarihinden bu yana ~30 gün birikince;
   bölüm 5 `cases.status` üçlü dışı = 0 ise `ALTER TABLE cases VALIDATE CONSTRAINT ck_cases_status_uclu`
   ayrı görevle (D9, [`dava-acma-akisi.md` §4](dava-acma-akisi.md)); bölüm 6 arama kollarının
   index'e düştüğü. Script'in bölüm 5 metni (`scripts/perf_olcum.py:413`) de bunu söyler:
   "`VALIDATE CONSTRAINT ck_cases_status_uclu` (D9) ancak 0 iken koşulabilir" (kısıt G195'te
   `NOT VALID` ile eklendi; G197 metni düzeltti).
5. **İlk gece turları:** `lock_timeout` 5 sn yeni bir hata modudur (§13); gece job'larından
   (00:00 rapor, 02:30 dönüşüm retry) sonra `docker compose logs --since 12h backend | grep -i "lock timeout"`.
6. **`pg_stat_statements`:** trafik birikince §13'teki en pahalı 10 sorgu.

## 13. Bağlantı sınırları ve Postgres sunucu ayarları (G191)

Kaynak: performans denetimi D5 (bağlantı sınırları) ve D6 (sunucu parametreleri).

### Uygulama bağlantısı sınırları (`backend/database.py`)

Motorun her bağlantısına libpq `options` ile gider (`_build_connect_args`). Değer
milisaniyedir; `0` = kapalı, seçenek bağlantıya hiç gönderilmez.

| Env | Varsayılan | Etki |
| --- | --- | --- |
| `DB_STATEMENT_TIMEOUT_MS` | 30000 | Tek sorgu bu süreyi aşarsa sunucu iptal eder (Faz 3-E) |
| `DB_IDLE_TX_TIMEOUT_MS` | 60000 | `idle_in_transaction_session_timeout`: transaction açıkken ifade koşmadan bu süre geçerse sunucu oturumu keser |
| `DB_LOCK_TIMEOUT_MS` | 5000 | `lock_timeout`: kilit bekleyen ifade bu sürede `LockNotAvailable` (SQLSTATE 55P03) alır |

- **`migrate.py` muafiyeti:** import'tan önce üç env'i de `0`'lar. Şema migrasyonu ve backfill
  UPDATE'leri sınırsız koşar, uygulama trafiğinin tuttuğu kilidi bekleyebilir.
- **Uzun süren TEK ifade idle sayılmaz.** Aktarım gibi uzun ama sürekli ifade koşturan iş bu
  sınırdan etkilenmez. Etkilenen, transaction açıkken DB dışı iş yapan yoldur: 60 sn aşılırsa
  sonraki ifade/commit `OperationalError` alır. Bu yüzden teslim cevap yüklemesi yüklemeden
  önce transaction'ı kapatır (G194). Kanıt dbtest'leri: `tests/test_g191_baglanti_ayarlari.py`
  (1 sn'lik `pg_sleep` 300 ms sınırda kesilmez, 1,5 sn boşta bekleme kesilir; `lock_timeout=200`
  ile kilitli satıra `UPDATE` 1 sn içinde düşer ve tek yuvalı havuz rehin kalmaz).
- **Elle koşulan script'ler** (`docker compose exec backend python -m scripts.…`) `database`
  modülünü import ettiği için aynı sınırlarla bağlanır. Bilinçli uzun kilit beklemesi gereken
  tek seferlik bir iş için env o komutta verilir:
  `docker compose exec -e DB_LOCK_TIMEOUT_MS=0 -T backend python -m scripts.<ad>`.

### Postgres sunucu parametreleri (`docker-compose.yml` → `postgres.command:`)

```
postgres -c effective_cache_size=384MB -c random_page_cost=1.1 -c shared_preload_libraries=pg_stat_statements -c track_io_timing=on
```

| Parametre | Değer (önceki) | Gerekçe |
| --- | --- | --- |
| `effective_cache_size` | 384MB (4GB) | Planlayıcı ipucu; 512m limitli konteynerle tutarlı hâle geldi |
| `random_page_cost` | 1.1 (4) | SSD sınıfı disk değeri; varsayılan döner disk içindir |
| `shared_preload_libraries` | `pg_stat_statements` (boş) | Sorgu istatistikleri (aşağıda) |
| `track_io_timing` | on (off) | `EXPLAIN (ANALYZE, BUFFERS)` ve `pg_stat_statements` I/O süreleri |

`shared_buffers` (128MB), `work_mem` ve `max_connections` (100) bilinçli olarak varsayılanda kalır:
havuz worker başına `pool_size=10 + max_overflow=20` = 30, iki worker ile 60 < 100.

**Bellek ve 512m limit (2026-07-29 OOM dersleri).** `effective_cache_size` hiçbir bellek
**ayırmaz**: yalnız planlayıcıya "işletim sistemi önbelleği + shared_buffers ne kadar veri
tutabilir" tahminini verir ve index taraması ile sıralı tarama arasındaki maliyet seçimini
etkiler. RSS'i artırmaz. Önceki 4GB, 512m'lik konteynerde (`mem_limit: 512m`, `memswap=mem`,
swap yok) gerçekte olmayan bir önbellek varsayıyordu. 384MB ≈ limitin %75'i. Konteynerin gerçek
bellek tavanını `shared_buffers`, bağlantı sayısı ve `work_mem` belirler; üçü de değişmedi.
Lokal ölçüm (2026-09-14, recreate sonrası): `hukudok-postgres` 53 MiB / 512 MiB.
`pg_stat_statements` sabit boyutlu bir paylaşımlı hash tablosu kullanır
(`pg_stat_statements.max` = 5000 kayıt, varsayılan).

**Uzantı kurulumu:** `database.py::_ensure_pg_stat_statements`, migrasyonun sonunda `pg_trgm`
adımının hemen ardından `CREATE EXTENSION IF NOT EXISTS pg_stat_statements` koşar ve görünümü
bir kez okuyarak yoklar. Uzantı preload olmadan da yaratılabildiği için yoklama şarttır.
Preload yoksa (recreate edilmemiş sunucu, CI'ın çıplak Postgres'i) TEK WARNING loglanır,
uygulama ayakta kalır.

### Prod'a geçiş: `up -d` recreate şart

`postgres.command:` ve `.env` değişikliği `restart` ile **gelmez**: komut ve env yalnız
konteyner create'te okunur. `deploy.sh` zaten `up -d` koşar (§1) ve değişen postgres
tanımını recreate eder. Elle geçişte stack'in tamamı `docker compose up -d` edilir; yalnız
backend recreate'inin frontend nginx'ini bayat upstream'de bırakma tuzağı §1'de. Postgres
recreate'i birkaç saniyelik DB kesintisidir; backend havuzu `pool_pre_ping` ile yeniden bağlanır.
Uzantı, recreate'ten SONRAKİ ilk migrasyonda (backend açılışı) kurulur. Kontrol:

```
docker compose exec -T postgres psql -U hukudok_user -d hukudok -c "SHOW effective_cache_size; SHOW shared_preload_libraries;"
```

### `pg_stat_statements`: en pahalı 10 sorgu

```
docker compose exec -T postgres psql -U hukudok_user -d hukudok -c "SELECT round(total_exec_time) AS toplam_ms, calls, round(mean_exec_time::numeric, 1) AS ort_ms, rows, left(query, 120) AS sorgu FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;"
```

`total_exec_time` sıralaması en çok toplam süre yiyen sorguları getirir: sık çağrılan ucuz
sorgu, seyrek çağrılan pahalı sorgunun önüne geçebilir. Tek tek yavaş olanlar için
`ORDER BY mean_exec_time DESC` kullanılır. Sayaçlar `SELECT pg_stat_statements_reset();` ile
sıfırlanır; bir değişikliğin etkisini ölçmeden önce sıfırla, trafik birikince yeniden oku.
Lokal sayılar prod'u temsil etmez (§12 şerhi).
