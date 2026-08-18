# CLAUDE.md — HukuDok çalışma rehberi

Hukuk bürosu belge otomasyonu: belge yükle → Gemini ile analiz → onayla → SharePoint
arşivi + veritabanı kaydı → hukukbot'a aktarım. FastAPI backend + React/Vite frontend +
PostgreSQL; kimlik Azure AD (MSAL). Bu dosya sıfır-context bir oturumun giriş noktasıdır.

> **ALTIN KURAL:** Buraya ve `docs/mimari/` altına yazılan her operasyonel iddia
> (komut, yol, port, sayı) **koddan okunarak ya da koşularak** doğrulanır.
> `docs/arsiv/` içinden veya ezberden KOPYALAMA. Doğrulayamadığını yazma.
> Kod ile doküman çelişirse kod haklıdır — dokümanı düzelt.

## Mimari özet

**Servisler** (`docker-compose.yml`): `postgres` (postgres:15-alpine, 127.0.0.1:5432),
`backend` (`hukdok_backend`, python:3.12-slim, 127.0.0.1:8001), `frontend` (nginx,
host 8080 → konteyner 80). Backend portu bilinçli localhost'a sabit: API-key'li
`/export` route'ları public'e açılmaz; hukukbot ortak `hukuk_shared` Docker ağından
`http://hukdok_backend:8001` ile konuşur.

**İki katmanlı nginx:** Repodaki `nginx.conf` **konteyner** nginx'idir: `listen 80`
(compose 8080:80 yayınlar), SPA'yı servis eder; `/api`, `/process`, `/confirm`,
`/preview-email-body`, `/preview-client-email-body`, `/refresh`, `/healthz` →
`backend:8001` proxy.
`proxy_read_timeout 300s` (GhostScript PDF/A dönüşümü 60s'yi aşabilir; 504 = mükerrer
kayıt kaynağıydı). Konteynerler düz HTTP konuşur; TLS prod'daki **host** nginx'inde
sonlanır (konfigi repo DIŞINDA, sunucuda; iki katmanın timeout'ları eşit tutulmalı —
bkz. `nginx.conf:10-14`). `/export` konteyner nginx'ine ASLA eklenmez (`nginx.conf:62`).

**Backend açılışı** (`backend/docker-entrypoint.sh`): önce `migrate.py` tek süreçte
koşar (hata = konteyner durur, bozuk şemayla kalkılmaz), sonra uvicorn
`--workers ${UVICORN_WORKERS:-2}`. **2 worker + lider kilidi:** süreç-tekil arkaplan
işleri kilit dosyası üzerinden (flock/msvcrt, `services/singleton_lock.py`) yalnız
lider worker'da başlar (`api.py` lifespan): APScheduler (günlük aktivite raporu 00:00 TR,
dönüşüm retry 02:30 TR) + SharePoint upload outbox worker'ı (`services/upload_queue.py`).
Refresh thread'i ise BİLEREK worker-başınadır (süreç-içi singleton cache'ler).

**Belge akışı:** `/process` → `analyzer.analyze_file_generator` NDJSON stream'i →
kullanıcı onayı → `/confirm` (idempotent: `process_id` anahtarlı `ConfirmReceipt` DB
kaydı, `services/confirm_idempotency.py`) → belge kaydı + SharePoint upload outbox →
upload başarılı olup `sharepoint_url` yazılınca `services/export_publisher.notify_hukukbot`:
filtrelerden geçen belge `export_outbox`'a "pending" düşer + hukukbot'a webhook atılır
(ulaşamazsa sorun değil — hukukbot'un periyodik reconcile'ı toparlar; doğruluk garantisi
outbox + reconcile'dadır, webhook yalnız gecikmeyi sıfırlar). Ofis dosya no `/process`
sırasında SharePoint sayacından ATOMİK tahsis edilir (ETag/If-Match; timeout'ta numara
atlanır — mükerrere tercih edilir).

**Stream sözleşmesi** (`analyzer.py::_failed_event`, frontend ile ORTAK referans):
olaylar `{"status": "info"/"warning"/"error"/"complete"/"failed", ...}`.
Nihai başarısızlık: `{"status":"failed", "error_ozet", "error_kod"}`; `error_kod`
etiketleri `gemini_saturated | gemini_blocked | gemini_truncated | schema_invalid |
pdf_page_limit | analysis_error` (uzay açık; tanınmayan etiket `analysis_error` gibi
ele alınır). `failed` SON olaydır, `process_id` taşımaz. Analyzer içinde akışı nihai
sonlandıran `status:"error"` yield'i YOKTUR; `{"status":"error","message"}` yalnız
route'un beklenmedik istisnasından gelir ve bu sözleşmenin dışındadır.

**Tenant modeli:** `cases`/`clients` tablolarında `tenant_id` kolonu VAR ama iki tenant
(Hanyaloğlu Acar + LexisBio) ortak çalışır: yeni kayıtlar bilinçli `tenant_id=NULL`
(paylaşımlı havuz — `routes/cases.py:55`, `routes/clients.py:35`); sorgular
"`tenant_id == X OR IS NULL`" deseniyle filtreler (`auth_helpers.py`). Girişte tenant
`ALLOWED_TENANTS` env listesine karşı doğrulanır (`auth_verifier.py`).

**Dava şeması (FAZ D+E, G044-G046):** `cases.esas_no` TÜRETİLMİŞTİR — gerçek kaynak
`case_esas_numbers` tablosu (esas numarası tarihçesi: aşama başına bir satır, dava
başına en fazla bir `is_current=True`); tek yazma yolu `case_manager.sync_current_esas`,
arama eski esas numarasıyla da bu tabloya JOIN'lenerek çalışır (E8, aşağıdaki arama
maddesi). Eksik zorunlu alan bayrağı `cases.missing_required_bucket` de
TÜRETİLMİŞTİR (NULL = eksik yok, `MANUAL`/`AKTARIM` kovaları); tek yazma yolu
`case_manager.refresh_missing_required`, kural `required_fields.py`'de D2/D8
bağlamına göre değişir.

**Dava arama (E8, G055):** `case_manager.get_cases` 13-14 kolon/ilişkiyi tek bir
OR/EXISTS ağacında DEĞİL, her terim için bağımsız `UNION`'lanan `SELECT`'lerle arar;
çok terimli sorguda AND semantiği `UNION`'ların `INTERSECT`'iyle kurulur
(`_search_term_ids`, `_term_case_id_selects`). `cases` üzerindeki altı GIN trigram
index'i (subject/tracking_no/court/klasor_no_2/esas_no/responsible_lawyer_name)
G042'de düşürüldü ve **geri eklenmedi** — UNION yeniden yazımı index'siz de ölçülebilir
kazanç veriyor (bkz. `docs/kararlar/018-index-temizligi-37-kalem.md`, `gorevler/gorev/G055.md`).

**Sürüm izi:** deploy git SHA'sını `APP_VERSION` build arg'ı ile imaja gömer →
`/healthz` "version" alanı + login rozeti. `/healthz` derindir (DB `SELECT 1`;
başarısızsa 503) — izleme ve deploy kapısı buradan bakar.

**Yedekleme:** prod'da systemd timer (`infra/systemd/db-backup.timer`, 00:30 UTC =
03:30 TR, `Persistent=true`; sunucuda cron YOK) `pg_dump -Fc` alır; deploy öncesi ayrıca
`deploy.sh` dump alır. Bellek düzeni: backend 2g / postgres 512m / frontend 128m limit,
`memswap=mem` (swap yasak), `MALLOC_ARENA_MAX=2` (2026-07-29 OOM dersleri).

## Komutlar

```bash
# Lokal stack (kod İMAJDAN çalışır — bkz. tuzaklar)
docker compose up -d

# Backend testleri KONTEYNERDE koşar (imaj python:3.12-slim)
docker compose exec -T backend python -m pytest            # 2026-08-13: 1285 passed, 3 skipped
# DİKKAT: komuta ekstra -q EKLEME — pyproject addopts zaten -q; -qq özet satırını yutar.

# Dev araçları (pytest/httpx/ruff/mypy) prod imajına GİRMEZ (requirements-dev.txt).
# Konteynerde yoksa kur (recreate'te uçar, yeniden kurulur):
docker compose exec -T backend pip install -r requirements-dev.txt
docker compose exec -T backend python -m ruff check .
docker compose exec -T backend python -m mypy

# Frontend testleri HOST'ta koşar (vitest)
npm --prefix frontend test                                 # 2026-08-13: 332 passed (26 dosya)
npm --prefix frontend run lint
npm --prefix frontend run build
```

**Deploy (yalnız kullanıcı kararıyla, sunucuda, mesai dışı):** `cd ~/hukdok && ./deploy.sh`
— akış ve güvenlik kapıları dosya başındaki yorumda (ff-only pull → pre-deploy pg_dump →
çalışan stack'i bozmadan build → SHA etiketi → `up -d` → 120 sn `/healthz` kapısı).
Geri dönüş: `./rollback.sh <SHA>` (imajı döndürür, DB'yi DÖNDÜRMEZ — DB için pre-deploy
dump). `.env` değişikliği `restart` ile GELMEZ: env yalnız konteyner create'te okunur →
`docker compose up -d` (recreate) gerekir.

## Kritik tuzaklar

- **PS5.1 UTF-8:** PowerShell 5.1 `Get-Content`/`Set-Content` Türkçe içeriği çift kodlar
  ve bozar. Dosya değişikliği DAİMA Edit/Write tool ile; shell'le dosya yazma
  (`otomasyon/gece-kosusu.ps1:14` bu yüzden bilerek ASCII).
- **Backend bind-mount YOK:** prod compose kaynak kodu mount ETMEZ — konteyner imajdaki
  kodu çalıştırır (`docker-compose.yml` backend/volumes yorumu). Kod değişikliğini görmek
  için rebuild şart: `docker compose build backend && docker compose up -d backend`.
  Lokal hot-reload isteniyorsa `docker-compose.override.yml.example` kopyalanır
  (gitignore'da, prod'a gitmez).
- **OneDrive + Docker build cache:** repo OneDrive altında; `requirements*.txt` değişse
  bile pip katmanı CACHED geçebilir. Şüphede `docker compose build --progress=plain` ile
  pip adımının gerçekten koştuğunu doğrula.
- **Migrasyon op türleri koşullu/koşulsuz karışımı:** `database.py::_MIGRATIONS`'ta
  `("table", ...)`/`("columns", ...)` KOŞULLUDUR — `init_db()` önce `create_all()`
  koşturur, ilgili tablo/kolon zaten oradaysa op atlanır ve gövdesine gömülü CREATE
  INDEX/UNIQUE kısıtları o kurulumda HİÇ çalışmaz. Kalıcı olması gereken kısıt/index
  DAİMA ayrı bir `("index", ...)` op'una yazılır (koşulsuz, `IF NOT EXISTS` ile
  idempotent) — G041 bu boşluğu 8 kalemde kapattı; `deploy.sh --gate-only` kendi
  Postgres'ini migrasyonlu kaldırıp bunu doğrular, CI ise ÇIPLAK postgres kullanır
  (tablo bile yok) — üç ortamın üçü de farklı bir DB durumu sunar (bkz. G050 raporu).
- **Doctype `_` padding:** belge türü kodları `_` ile pad'lidir (örn. `TEBLIGAT______`,
  `constants.py:10`). Karşılaştırmadan önce normalize et; ham `==`/`in` kısaltmaları
  sızdırır (export allowlist'i bu yüzden normalize eder, `services/export_publisher.py`).
- **AVG TLS araya girmesi (lokal):** konteynerden Gemini'ye SSL hatasında çözüm
  `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` env'i (`docker-compose.override.yml.example:15`,
  `api.py:88`; `.env.example:93`).
- **pytest çift -q:** `backend/pyproject.toml` `addopts = "-q"` içerir; komuta bir `-q`
  daha eklersen özet satırı ("N passed") hiç basılmaz.
- **Log sözleşmesi:** deneme-düzeyi hatalar WARNING, nihai başarısızlık TEK ERROR
  (`analyzer.py::_failed_event` docstring'i). Retry yollarına yeni ERROR ekleme.

## Doküman haritası

| Yol | Ne | Güvenilirlik |
| --- | --- | --- |
| `CLAUDE.md` | Bu dosya — giriş noktası | Güncel tutulur |
| `docs/mimari/` | Yaşayan mimari dokümanları: genel bakış, belge işleme hattı, dava açma akışı, dış bağımlılıklar, deploy ve altyapı | GÜNCEL — kodla çelişirse doküman düzeltilir |
| `docs/plan/` | Yürüyen planlar; sertleştirme uygulama takibi tek doğruluk kaynağı | Güncel |
| `docs/kararlar/` | Kalıcı mimari kararlar (karar + gerekçe + reddedilenler) | Güncel |
| `docs/arsiv/` | Tarihli plan/rapor/denetimler | **TARİHSEL — güncel bilgi kaynağı DEĞİL.** İçindeki "şu an şöyle" ifadeleri yazıldığı günün fotoğrafıdır; okumadan önce `docs/arsiv/README.md` şerhini oku |
| `docs/hukukbot-aktarim/` | Hukukbot export spesifikasyonu — koddan referanslı (`nginx.conf:62`, `models.py`, `routes/export.py`) | Yaşayan spec, arşiv DEĞİL |
| `gorevler/` | Gece kuyruğu: `KUYRUK.md` + `gorev/GNNN.md` görev dosyaları | Süreç dosyaları |
| `otomasyon/` | Gece koşucuları — güncel: Workflow v3 (`.claude/workflows/gece-kuyrugu.js`, başlatıcı `/gece-kuyrugu`); CLI koşucuları `gece-kosusu.ps1`/`kuyruk-kosusu.ps1` (org ayarı CLI'yi kapattı, 2026-08-18) + loglar | Süreç dosyaları |
| `infra/` | Sunucu birimleri: systemd timer'lar, watchdog scriptleri (`infra/README.md`) | Güncel |

## Kod konvansiyonları

- Yorum ve doküman dili Türkçe, tanımlayıcılar İngilizce; mevcut dosyanın üslubunu koru.
- Lint/type kapıları `backend/pyproject.toml`'da: ruff `E,F,B` (E501 kapalı,
  line-length 120), mypy kademeli — yalnız `managers/ routes/ config/ services/` taranır.
- Bir iş = TEK commit: kod + test + doküman birlikte; `git add -A` yerine dosya listesi.
  Push/deploy daima insan kararı — otomasyon oturumları push/ssh/deploy YAPMAZ.
- Hata işlemede stream sözleşmesine ve log sözleşmesine uy (yukarıda).
- Arşivden kod/iddia kopyalama; tarihli anlatı yazacaksan `docs/arsiv/`e yaz.
