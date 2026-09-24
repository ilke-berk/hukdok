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
kayıt kaynağıydı). **Önbellek (G182, `nginx.conf:77-99`):** hash'li Vite parçaları
`location ~* ^/assets/` → `Cache-Control: public, max-age=31536000, immutable`; eksik parça
`=404` döner, index.html'e DÜŞMEZ (açık eski sekmede `frontend/src/lib/chunkReload.ts` sayfayı
bir kez yeniler). `location /` (index.html + SPA fallback) → `no-cache`. `add_header` kalıtım
tuzağı: location'da tek `add_header` bile server düzeyindekileri düşürür → beş güvenlik başlığı
iki location'da AYNEN tekrar yazılıdır, birini değiştiren üç yeri değiştirir (`nginx.conf:48-51`).
Konteynerler düz HTTP konuşur; TLS prod'daki **host** nginx'inde sonlanır (konfigin repodaki
kopyası `infra/nginx/sites-available/default`, sunucuya `infra/install.sh` kurar; iki katmanın
timeout'ları eşit tutulmalı — bkz. `nginx.conf:10-14`). Repodaki host konfiginde `add_header`
/ `proxy_hide_header` yok; sunucudaki konfigin bununla aynı olduğu ve `Cache-Control`'un
tarayıcıya ulaştığı **prod'da doğrulanacak** (`curl -sI https://<alan>/assets/<parça>.js`,
`curl -sI https://<alan>/`). `/export` konteyner nginx'ine ASLA eklenmez (`nginx.conf:114`).

**Backend açılışı** (`backend/docker-entrypoint.sh`): önce `migrate.py` tek süreçte
koşar (hata = konteyner durur, bozuk şemayla kalkılmaz), sonra uvicorn
`--workers ${UVICORN_WORKERS:-2}`. **2 worker + lider kilidi:** süreç-tekil arkaplan
işleri kilit dosyası üzerinden (flock/msvcrt, `services/singleton_lock.py`) yalnız
lider worker'da başlar (`api.py` lifespan): APScheduler (günlük aktivite raporu 00:00 TR,
dönüşüm retry 02:30 TR, süre/duruşma taraması 06:00 TR) + SharePoint upload outbox worker'ı
(`services/upload_queue.py`) + veri teslim açılış toparlaması (`teslim_kutusu.boot_toparla`).
Refresh thread'i ise BİLEREK worker-başınadır (süreç-içi singleton cache'ler).

**Veri teslim hattı:** veri ekibi `HUKDOK_TESLIM_*.xlsx` paketini bize iletir; yönetici admin
panelinden yükler (`services/teslim_kutusu.py`, sha256) → `aktarim_teslimleri` defteri + spool →
doğrula → kuru koş (`scripts/hukdok_aktarim.aktarimi_kos`, yalnız import edilir) → kapı
(env eşikleri `TESLIM_KAPI_*`; ilk teslim ve envanter farkı daima `inceleme_bekliyor`) →
**uygulamayı daima yönetici "Uygula" başlatır** → eşleşme/havuz farkı CSV'leri rapor dizinine
(`services/teslim_cevap.py`, panelden indirilir). Panelsiz yol CLI: `hukdok_aktarim.py` kuru koşu →
`--apply`. **SharePoint teslim klasörü yolu 17.09.2026'da KALDIRILDI** (gözcü, 04:00 gece turu,
`cevap/` yüklemesi, `TESLIM_SHAREPOINT_*` ikinci kimliği, `/aktarim/tara`,
`veri_teslim_otomasyonu` anahtarı — bekçi `tests/test_teslim_klasoru_kaldirildi.py`).
`DEGISIKLIK_OZETI` üç satır taşır: "Önceki teslim" (zincir; `—` yalnız defter boşken
başlangıçtır), "Teslim türü: tam | delta" (delta'da kaybolan sütun ihlal değil bilgi; eksik
sütun/föy = dokunma) ve "Veri kesim tarihi" (yoksa paket adındaki tarih). Kapı eşiği
`alan_degisikligi` KART HÜCRESİ sayar (tarih/tutar biçimi üretmez, ad yazımı üretir).
"Paket kazanır" kuralının tek istisnası kesim-sonrası kullanıcı korumasıdır (G152; 12.09'da
`status`'tan HER kart alanına genellendi): bizde DOLU bir alan için kesim gününden itibaren o alanda
kullanıcı imzalı (`source` NULL ya da `HUKDOK_TESLIM` dışı) `case_history` kaydı varsa paket o alanı
yazmaz/boşaltmaz, satır raporuna `KORUNDU` düşer (hata değil; bizde BOŞ alanı paket doldurur —
`scripts/hukdok_aktarim.py::_kart_alanlarini_yaz` + `kesim_sonrasi_kullanici_kaydi`).
Tek SharePoint kimliği arşivindir (LexisBio: arşiv/sayaç/export). Ayrıntı
`docs/mimari/veri-teslim-hatti.md`; veri ekibine verilen sözleşme `docs/veri-teslim/SOZLESME.md`.

**Belge akışı:** `/process` → `analyzer.analyze_file_generator` NDJSON stream'i →
kullanıcı onayı → `/confirm` (idempotent: `process_id` anahtarlı `ConfirmReceipt` DB
kaydı, `services/confirm_idempotency.py`) → belge kaydı + SharePoint upload outbox →
upload başarılı olup `sharepoint_url` yazılınca `services/export_publisher.notify_hukukbot`:
filtrelerden geçen belge `export_outbox`'a "pending" düşer + hukukbot'a webhook atılır
(ulaşamazsa sorun değil — hukukbot'un periyodik reconcile'ı toparlar; doğruluk garantisi
outbox + reconcile'dadır, webhook yalnız gecikmeyi sıfırlar). Ofis dosya no `/process`
sırasında SharePoint sayacından ATOMİK tahsis edilir (ETag/If-Match; timeout'ta numara
atlanır — mükerrere tercih edilir). **Toplu yüklemede ek bağlama (20.09):** tezgâhta bir satır
başka satırın e-posta EKİ olabilir (tebligat dilekçesi + mazbata): ek satır kendi başına
arşivlenir (`send_email=false`), dosyası ana satırın `/confirm`'üne `extra_attachment_files` ile
biner; toplu akışta e-postası açık tebligat ya da ekli satırda EmailModal ZORLA açılır
(`lib/tebligatDoctype.ts`); dosya başına meta `File` anahtarlıdır (`Index.tsx` `BatchFileMeta`).
Ayrıntı `docs/mimari/belge-isleme-hatti.md` §3.

**Uygulama içi bildirim** (`docs/mimari/bildirimler.md`): kanal yalnız zil, e-posta
değil. Üreticiler `belge_islendi` (URL commit sonrası; gündüz `upload_queue` ve gece
`conversion_retry`), `sure_yaklasti`/`durusma_yaklasti` (06:00 TR lider taraması,
`services/deadline_scanner.py`). Alıcı = sorumlu avukat(lar) + `email_recipients.notify_copy`
kopya alıcıları − belgeyi yükleyen (`notification_targeting.resolve_notification_recipients`);
allowlist `NOTIFICATION_DOMAINS`. Süre uyarısının TEK kaynağı `case_stage_decisions.teblig_tarihi`;
`/confirm`'de karar belgesiyle girilen tebliğ tarihi oraya yazılır
(`processing.KARAR_DOCTYPE_TO_DECISION_STAGE`, boş alan dolar dolu alan ezilmez).

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
bağlamına göre değişir (2+ avukatlı kartta boş sorumlu avukat kutusu eksik sayılmaz, G158).
Aşama kararları `case_stage_decisions` (tek yazma yolu `managers/stage_decisions.py`, kart
slotları türetilmiş fotoğraf): aktarım mevcut satırı YERİNDE günceller (paket kaynaklı ve elle
girilmiş fark etmez, tarihçeli), yalnız `dogrulama_durumu ∈ {BELGE, UYAP}` satır korunur, esas
VE karar tarihi farklı ise ikinci tur `sira_no+1` ile eklenir, silme yolu yok (G150; ayrıntı
`docs/mimari/veri-teslim-hatti.md` §7.1). **Dava durumu ÜÇLÜDÜR** (`constants.CASE_STATUSES`,
karar 020): `cases.status` yalnız DERDEST | DANIŞ | MAHZEN; temyiz/istinaf/karar/kapalı DURUM
değil AŞAMADIR (`cases.case_stage`). Yazma yolları `normalize_case_status`'tan geçer, belge işleme
belge türünden aşamaya yazar (`DOCTYPE_TO_STAGE_MAP`), migrasyon 50 eski değerleri üçlüye çekti.

**Dava arama (E8, G055, G189, G190):** `case_manager.get_cases` 15 kolon/ilişkiyi (exact modda
13: `notes`/`case_history.old_value` yok) tek bir OR/EXISTS ağacında DEĞİL, her terim için
bağımsız `UNION`'lanan `SELECT`'lerle arar; çok terimli sorguda AND semantiği `UNION`'ların
`INTERSECT`'iyle kurulur (`_search_term_ids`, `_term_case_id_selects`). Boş legacy
`cases.tku_no`/`sistem_no` kolları G190'da çıktı (TKU/SistemNo `case_foys` kollarından).
**Tek koşu (D4):** `with_total=True` aramada süzülmüş+sıralı id listesi TEK sorguda gelir →
toplam = uzunluk, sayfa = dilim (`_load_cases_in_order`); COUNT yok. `with_total=False`
(`search_cases`, tuş vuruşu yolu) COUNT'suz tek koşudur; aramasız liste COUNT + sayfa koşar.
Liste ucunda `offset ≤ 10000` (`routes/cases.py:92`, aşım 422). **Trigram index'leri**
`database.py::_TRGM_INDEXES` sözlüğündedir — `("index", ...)` op'unda DEĞİL, `pg_trgm`
uzantısından sonra koşan hata-toleranslı blokta (G043 notu); düşürmeler `_DUSURULECEK_INDEXLER`
(`("index", ...)` DROP op'ları). Sözlükteki arama kolları: `case_foys.tku_no/sistem_no/
onceki_tracking_no` (G189), `cases.court/subject/esas_no/tracking_no` (G190 — G042'nin
düşürdüğü altıdan EXPLAIN kanıtıyla dönen dördü), `cases.uyap_lawyer_name`, `case_parties.name`,
`case_lawyers.name`; avukat filtresinin katlanmış ifade index'i ayrıca. Düşmüş kalanlar:
`idx_cases_klasor_no_2_trgm`, ham `idx_cases_resp_lawyer_trgm`, boş legacy
`idx_cases_tku_no`/`idx_cases_tku_no_trgm`/`idx_cases_sistem_no_trgm` (G189). Trigram index'i
olmayan kollar: `klasor_no_2`, ham `responsible_lawyer_name`, `notes`, `case_history.old_value`,
`case_esas_numbers.esas_no` (btree var, küçük tablo); `notes`/`old_value`'yu aramadan çıkarma
kullanıcı kararı AÇIK. Nihai tablo: `docs/kararlar/018-index-temizligi-37-kalem.md` "Nihai index durumu".

**Raporlama (G130-G177 + 12.09 özet modu):** yönetici `/reports`'ta isteğini sohbete yazar — sohbet öncelikli ekran (G173-G176):
`AssistantBar` → `TanimSeridi` (uygulanan tanımın düzenlenebilir çip şeridi: kaynak · kolonlar · filtreler ·
sıralama; operatör seçici yok, kontrol türü/grup/öneri katalogda, 60 sn önbellekli) → tablo; manuel kurucu
(kaynak kartı/filtre şeridi/kolon paneli) KALKTI, şerit yedek kurucudur →
`GET /api/reports/catalog` · `POST /preview` (loglanmaz) · `POST /export` (xlsx/csv; `report_runs`
satırı + dosya `RAPOR_CIKTI_DIZINI`'de saklanır, sha256 = indirilen) · `/templates` · `/runs`. Serbest
SQL YOK (K1: istemci yalnız `services/rapor/registry.py` anahtarlarını gönderir, sorgu Core ile kurulur,
tenant+soft-delete `kisitlar`dan). AI asistan `POST /chat` (NDJSON) admin anahtarı `rapor_asistani`
(varsayılan KAPALI; kapalıyken sayfa boş kalmaz — bilgi kartı + şerit) ister; tanımı şeritle AYNI doğrulamadan
geçer (K6) ve DÜĞME BEKLEMEDEN uygulanır (G174; kart yalnız metin filtre değeri katalog önerilerine uymayınca
bekler — `degerEsle`, aday çipleri; "hangi X'ler var" listesi Gemini'siz katalogdan, `listeNiyeti`); prompt
G176: onay sorma, yaklaşık ad → `contains`, liste sorusunda ekrana yönlendir. **Kaynaklar arası birleştirme
(G166):** kaynak `iliskiler` bildirir, bağlı kaynağın kolonları `<iliski>.<kolon>` anahtarıyla TÜRETİLİR
(`muvekkil.phone` davalar'da; `dava.tracking_no` müvekkiller'de) — çoklu bağda değerler `" ; "` birleşik +
EXISTS filtre, sıralama yok; belgeler/föyler → `dava.*` tekil (düz kolon gibi). Elle kolon listesi yazma;
`kart_eslesmesi` ad anahtarı için ifade index'i migrasyon 48'de (`_ad_anahtari` ile birebir, test bekçili).
Ayrıntı `docs/mimari/raporlama.md` §2.4. **Özet modu (12.09):** tanım `olcumler` taşıyorsa satırlar `gruplama`
alanlarına göre `GROUP BY` (≤3; tarihte `kirilim` gün/ay/yıl, Türkiye günü) + ölçümler (≤5; `sayi|toplam|ortalama|
min|max`, anahtar `toplam:maddi_tazminat`); `kolonlar` özet modunda kullanılmaz ama zorunlu kalır; boş
`gruplama`/`olcumler` JSON'a girmez (eski sözleşme birebir). Türetilmiş/çoklu bağ kolonu GRUPLANAMAZ. Şeritte
"Σ Özet" satırı; asistan prompt'u "ÖZET RAPOR". Ayrıntı §3.1. **Saat dilimi (12.09):** rapor sözleşmesinin
dilimi `schemas_rapor.SAAT_DILIMI` (Europe/Istanbul) — DB UTC; zaman damgalı filtre bind'ı, serileştirme ve
Excel hücresi TR saati (openpyxl tz'li datetime'ı reddeder).

**Sürüm izi:** deploy git SHA'sını `APP_VERSION` build arg'ı ile imaja gömer →
`/healthz` "version" alanı + login rozetinin tooltip'i ("Build: <SHA>"). Rozetin görünür
metni okunur sürümdür (`v3.2.0`): tek kaynak `frontend/package.json` "version"
(`vite.config.ts` `define` → `VITE_APP_RELEASE`); sürüm atlatmak = o alanı + `package-lock.json`
kökünü değiştirmek. `/healthz` derindir (DB `SELECT 1`;
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
docker compose exec -T backend python -m pytest            # 2026-09-17: 3527 passed, 3 skipped
# DİKKAT: komuta ekstra -q EKLEME — pyproject addopts zaten -q; -qq özet satırını yutar.

# Dev araçları (pytest/httpx/ruff/mypy) prod imajına GİRMEZ (requirements-dev.txt).
# Konteynerde yoksa kur (recreate'te uçar, yeniden kurulur):
docker compose exec -T backend pip install -r requirements-dev.txt
docker compose exec -T backend python -m ruff check .
docker compose exec -T backend python -m mypy

# Frontend testleri HOST'ta koşar (vitest)
npm --prefix frontend test                                 # 2026-09-17: 1002 passed (88 dosya)
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
- **Rapor asistanı tanımı doğrulanmadan kullanılmaz:** Gemini'nin döndürdüğü tanım
  `services/rapor/asistan.tanimi_dogrula` → `RaporTanimi` + `motor.tanimi_dogrula` yolundan
  geçmeden istemciye `tanim` olarak GİTMEZ (geçmezse `warning` + `tanim=null`); Gemini
  `response_schema`'sına `RaporTanimi` verilmez (`extra="forbid"` → `additionalProperties`,
  SDK Developer API'de desteklenmez — `schemas_rapor.py:188-204`).

## Doküman haritası

| Yol | Ne | Güvenilirlik |
| --- | --- | --- |
| `CLAUDE.md` | Bu dosya — giriş noktası | Güncel tutulur |
| `docs/mimari/` | Yaşayan mimari dokümanları: genel bakış, belge işleme hattı, dava açma akışı, veri teslim hattı, raporlama (`raporlama.md`), bildirimler (`bildirimler.md`), dış bağımlılıklar, deploy ve altyapı, kimlik ve token (`kimlik-ve-token.md`) | GÜNCEL — kodla çelişirse doküman düzeltilir |
| `docs/plan/` | Yürüyen planlar; sertleştirme uygulama takibi tek doğruluk kaynağı | Güncel |
| `docs/kararlar/` | Kalıcı mimari kararlar (karar + gerekçe + reddedilenler) | Güncel |
| `docs/arsiv/` | Tarihli plan/rapor/denetimler | **TARİHSEL — güncel bilgi kaynağı DEĞİL.** İçindeki "şu an şöyle" ifadeleri yazıldığı günün fotoğrafıdır; okumadan önce `docs/arsiv/README.md` şerhini oku |
| `docs/hukukbot-aktarim/` | Hukukbot export spesifikasyonu — koddan referanslı (`nginx.conf:114-115`, `models.py`, `routes/export.py`) | Yaşayan spec, arşiv DEĞİL |
| `gorevler/` | Gece kuyruğu: `KUYRUK.md` + `gorev/GNNN.md` görev dosyaları | Süreç dosyaları |
| `otomasyon/` | Gece koşucuları — güncel: Workflow v3 (`.claude/workflows/gece-kuyrugu.js`, başlatıcı `/gece-kuyrugu`); CLI koşucuları `gece-kosusu.ps1`/`kuyruk-kosusu.ps1` (org ayarı CLI'yi kapattı, 2026-08-18) + loglar | Süreç dosyaları |
| `infra/` | Sunucu birimleri: systemd timer'lar, watchdog scriptleri (`infra/README.md`) | Güncel |

## Kod konvansiyonları

- Yorum ve doküman dili Türkçe, tanımlayıcılar İngilizce; mevcut dosyanın üslubunu koru.
- Lint/type kapıları `backend/pyproject.toml`'da: ruff `E,F,B` (E501 kapalı,
  line-length 120), mypy kademeli — yalnız `managers/ routes/ config/ services/` taranır.
- Bir iş = TEK commit: kod + test + doküman birlikte; `git add -A` yerine dosya listesi.
  Push/deploy daima insan kararı — otomasyon oturumları push/ssh/deploy YAPMAZ.
- **CI protokolü** (`.claude/skills/ci-kontrol`, `/ci-kontrol`): push ÖNCESİ `ci.yml` adımlarının lokal
  eşdeğeri, push SONRASI `gh run watch`; **kırmızıdayken yeni iş push'lanmaz** (sıradaki push düzeltmedir);
  deploy edilecek SHA'nın CI'ı `success` değilse deploy YOK (`deploy-prosedur` §1).
- **Bağımlılık denetimi** (`.claude/skills/bagimlilik-denetle`, `/bagimlilik-denetle`; her ayın 1'i zamanlanmış
  yerel görev): yeni sürümleri sürüm notu + kod etkisiyle sınıflar, yalnız aynı-major güncellemeleri
  `bagimlilik/YYYY-MM` dalında uygulayıp CI kapılarından geçirir; major/altyapı atlamaları rapor
  (`docs/arsiv/bagimlilik-raporu-YYYY-MM.md`) önerisidir. Push/deploy YAPMAZ.
- Hata işlemede stream sözleşmesine ve log sözleşmesine uy (yukarıda).
- Arşivden kod/iddia kopyalama; tarihli anlatı yazacaksan `docs/arsiv/`e yaz.
