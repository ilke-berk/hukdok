# Bağımlılık majorları planı — 2026-10-01

Kaynak: `docs/arsiv/bagimlilik-raporu-2026-10.md` §6 (İnsan kararı bekleyenler). 2026-10-01 kullanıcı kararı:
Office365-REST-Python-Client kaldırıldı (dal `bagimlilik/2026-10`, `0bc902c`); kalan dört major bu plana göre
yürür. Görevler: `gorevler/KUYRUK.md` "Bağımlılık majorları" bölümü, G243-G247.

## Sıra ve gerekçe

| # | İş | Görev | Ne zaman | Neden bu sırada |
| --- | --- | --- | --- | --- |
| 1 | reportlab 4.2.5 → 4.5.1 (son 4.x) | G243 | Gece 1 | PDF üretiminin iki yolu da (UDF→PDF `udf_converter.py`, rapor PDF'i `report_builder.py`) reportlab'da. 28.08 prod arızası (görselli tablo bölme) bu kodda çıktı → önce aynı major içinde, küçük adımla |
| 2 | reportlab 4.5.1 → 5.0.x | G244 | Gece 1 | 5.0 kaldırmaları (`_renderPM`, pyRXP, uzak görsel `trustedHosts` varsayılanı) ayrı commit'te ölçülür; geri almak tek satır |
| 3 | python:3.12-slim → 3.13-slim | G245 | Gece 1 | 3.14 DEĞİL: reportlab 4.x'in kullandığı `ast.NameConstant` 3.14'te kalkıyor; 3.13 tüm pinlerin wheel'iyle güvenli ara durak. 3.12 güvenlik desteği 2028-10'a dek sürer — acele yok, ama imaj/CI/mypy hedefi tek seferde hizalanır |
| 4 | postgres:15 → 17 PROVASI | G246 | Gece 1 | 18 DEĞİL: 17 olgun (17.11), 18 genç. PG15 desteği 2027-11'e dek. Gece işi yalnız PROVA + runbook; gerçek geçiş insan adımı (aşağıda) |
| 5 | node:24 → 26 | G247 | Node 26 LTS'e geçince (≈2026-10-28) | Node yalnız frontend build aşamasında; çalışan uygulama nginx → risk düşük. LTS öncesi BLOKE |

Tahmin: G243-G246 tek gece (hepsi `bant:backend`, seri). G247 Kasım başı ayrı koşu.

## Sınırlar (bütün görevler)

- Push / deploy / ssh YOK. Prod'a hiçbir şey çıkmaz; her görev tek commit.
- Test silme / gevşetme / skip YASAK. Kırmızıda görev BLOKE bırakılır, sürüm geri alınır.
- Gerçek müvekkil verisi (DB dump'ı) repo ve OneDrive altına yazılmaz → `C:\hukdok-veri\yedek\`.
- `docker-compose.yml` postgres imajı, `deploy.sh` `GATE_PG_IMAGE`, `.github/workflows/ci.yml` postgres servisi
  gece DEĞİŞMEZ: lokal veri hacmi PG15 biçiminde, imaj değişirse lokal stack açılmaz.

## Postgres 17 — gerçek geçiş (İNSAN ADIMI, G246 provasından sonra)

Önce lokalde sonra prod'da, mesai dışı. Komutlar ve süreler G246 provasında (2026-10-01, lokal restore kopyası:
15.15 → 17.11, `postgres:17-alpine`) ÖLÇÜLDÜ; ayrıntılı kanıt `gorevler/gorev/G246.md` Rapor bölümünde.

### Prova sonucu (özet)

| Adım | Ölçülen (lokal) | Sonuç |
| --- | --- | --- |
| `pg_dump -Fc` (PG15 sunucusu içinde) | 1,2 sn · 5,2 MB (DB 139 MB, şişkin) | — |
| `pg_restore` (PG17 istemcisi, boş PG17 DB) | 3,0 sn · 549 TOC kalemi | 0 hata, 0 uyarı |
| `ANALYZE` (restore istatistik taşımaz) | 1,3 sn | — |
| `migrate.py` (backend konteyneri, `DATABASE_URL` override) | 1,9 sn | yeni op YOK — şema dump'ı PG15 ile birebir (sürüm biçim farkları ayıklanınca `diff` boş) |
| Şema sayımı 15 ↔ 17 | 60 tablo · 173 index (11 `gin_trgm_ops`) · 86 kısıt | aynı; index adlarının md5'i aynı |
| Uzantılar | `pg_trgm` 1.6 = 1.6 · `pg_stat_statements` 1.10 → 1.11 | restore 17'nin sürümünü kurar |
| Tam pytest (`DATABASE_URL` = PG17; `dbtest` scratch DB'leri PG17'de açıldı) | 4 dk 58 sn | **4082 passed, 15 skipped** = PG15 tabanı |
| Arama planı `perf_olcum --term "Bora"` / `"Bora Ankara"` | çalışma 23,9 → 22,1 / 27,1 → 22,8 ms | 15 kolun kök düğümü + index'i BİREBİR aynı; Seq Scan'li kol 4/15 = 4/15 |
| Sıralama/harf katlama (musl, `en_US.utf8`, sağlayıcı `c`) | `ORDER BY`, `lower/upper` Türkçe örnek | aynı |

Buffer sayısındaki düşüş (6.931 → 3.193) sürümden DEĞİL, dump/restore'un şişmeyi atmasından: lokal `cases` heap'i
14,7 MB → 5,2 MB (oran 2,98 → 1,07). Prod'da VACUUM FULL yapıldığı için (Deploy #29) bu fark orada küçük olur.

### Runbook (prod; lokal aynı adımlar, proje dizini farklı)

Hazırlık (pencereden ÖNCE): bu adımı içeren commit CI'da `success`; sunucuda `docker pull postgres:17-alpine`
(pencere içinde indirme olmasın). Geçiş başka bir deploy ile BİRLEŞTİRİLMEZ — `deploy.sh` olduğu gibi koşulursa
backend `migrate.py` BOŞ PG17 hacmine şema kurar ve ardından gelen `pg_restore` çakışır.

1. **Commit (insan, önceden):** imaj üç yerde aynı commit'te `postgres:17-alpine`: `docker-compose.yml:4`,
   `deploy.sh:86` (`GATE_PG_IMAGE`), `ci.yml:28`. Aynı commit'te `docker-compose.yml`'de hacim anahtarı yeni ada
   taşınır (`postgres-data` → örn. `postgres17-data`, `:24` ve `:164`) — eski PG15 hacmi böylece HİÇ dokunulmadan
   yerinde kalır (Docker'da hacim yeniden adlandırma yok; geri dönüş yolu budur). PG17 imajında veri yolu
   `/var/lib/postgresql/data` aynı kalır (yol değişikliği 18'de). Dokümanlar: `CLAUDE.md:14`,
   `docs/mimari/genel-bakis.md:22`, `docs/mimari/deploy-ve-altyapi.md:112`.
2. **Yazmayı durdur + dump:** `docker compose stop backend frontend` →
   `docker exec hukudok-postgres pg_dump -U hukudok_user -Fc hukudok > ~/yedek/pre_pg17_<tarih>.dump`
   (deploy.sh'ın yöntemi; lokal ölçüm 1,2 sn). Dump'ı `pg_restore -l` ile açılabilir doğrula; SharePoint
   yedeğinin o geceki dosyasının da varlığını kontrol et.
3. **Kodu al, yalnız postgres'i kaldır:** `git pull --ff-only` → `docker compose up -d postgres` (yeni boş hacimde
   PG17 initdb, kimlik `.env`'den) → `docker exec hukudok-postgres pg_isready -U hukudok_user -d hukudok` bekle;
   `docker exec hukudok-postgres postgres --version` = 17.x.
4. **Restore + istatistik:** `docker cp ~/yedek/pre_pg17_<tarih>.dump hukudok-postgres:/tmp/pg17.dump` →
   `docker exec hukudok-postgres pg_restore -U hukudok_user -d hukudok --exit-on-error /tmp/pg17.dump`
   (lokal 3,0 sn, çıktı boş olmalı) → `docker exec hukudok-postgres psql -U hukudok_user -d hukudok -c "ANALYZE;"`
   (1,3 sn) → `docker exec hukudok-postgres rm /tmp/pg17.dump`. Sayım kontrolü: `pg_indexes` public = 173,
   `gin_trgm_ops` = 11 (o günün şemasıyla; prod sayısı geçiş öncesi aynı sorguyla alınır ve karşılaştırılır).
   Git Bash'te koşuluyorsa `MSYS_NO_PATHCONV=1` (yoksa `/tmp/...` Windows yoluna çevrilir — provada yaşandı).
5. **Uygulamayı kaldır:** `docker compose up -d` (TÜM stack — yalnız backend recreate nginx'te bayat upstream
   502'si bırakır) → entrypoint `migrate.py` koşar (yeni op çıkmamalı) → `curl -s http://127.0.0.1:8001/healthz`
   `"db":"ok"` → `docker compose exec -T backend python -m scripts.perf_olcum --term "<terim>"`: §6 kök düğümleri
   geçiş öncesi aynı komutun çıktısıyla aynı olmalı (provada aynıydı).
6. **Geri dönüş:** commit'i geri al (imaj 15 + hacim anahtarı `postgres-data`) → `docker compose up -d` → eski
   PG15 hacmi olduğu gibi döner. Geçişten SONRA yazılan veri kaybolur; o veri gerekiyorsa PG17'den alınan dump
   PG15'e DOĞRUDAN dönmez (pg_dump 17 `SET transaction_timeout` yazar, 15 tanımaz) → elle `psql` ile o satır
   atlanarak ya da `--data-only` ile taşınır. `rollback.sh` DB'yi döndürmez.
7. **Temizlik (birkaç gün sorunsuz çalıştıktan sonra, insan kararı):** eski PG15 hacmi `docker volume rm`.

**Tahmini prod kesintisi:** DB adımları (dump + initdb + restore + ANALYZE + migrate) lokalde ~10 sn; prod verisi
lokalle aynı mertebede (lokal, prod kopyası). Durdurma, kaldırma, 120 sn `/healthz` beklemesi ve elle kontrollerle
**~5 dk yazma kesintisi**; kontrol ve ölçüm dahil **30 dk'lık pencere** yeterli. Uptime alarmı ALERT/RESOLVED çifti
beklenir.

### 15 → 17 arası bizi ilgilendiren davranış farkları (sürüm notlarından, koda karşı kontrol edildi)

- **pg_stat_statements 1.11 (17):** `blk_read_time`/`blk_write_time` → `shared_blk_*`/`local_blk_*` adlandı.
  Kodda bu kolonlar YOK (grep); `perf_olcum` 17'de hatasız koştu.
- **`pg_stat_bgwriter` checkpoint kolonları `pg_stat_checkpointer`'a taşındı (17):** kullanılmıyor.
- **Bakım işlemlerinde güvenli `search_path` (17):** ANALYZE/VACUUM/CREATE INDEX/REINDEX, ifade index'lerindeki
  fonksiyonları `pg_catalog, pg_temp` ile çözer. Tek ifade index'imiz (`idx_cases_resp_lawyer_fold_trgm`)
  yalnız `lower/translate/coalesce` (pg_catalog) kullanır; restore + ANALYZE provada hatasız.
- **Kaldırılan ayarlar** (`old_snapshot_threshold`, `db_user_namespace`, `vacuum_defer_cleanup_age`,
  `promote_trigger_file`, `adminpack`): hiçbirini kullanmıyoruz; compose `command:` bayrakları
  (`effective_cache_size`, `random_page_cost`, `shared_preload_libraries=pg_stat_statements`, `track_io_timing`)
  17'de geçerli — prova konteyneri aynı bayraklarla açıldı.
- **`transaction_timeout` (17, yeni):** varsayılan 0; pg_dump 17 çıktısı onu yazdığından 17 dump'ı 15'e dönmez
  (yukarıda adım 6).
- **`pg_trgm` 1.6 değişmedi;** psycopg2'nin paketlediği libpq 17 sunucusuyla tam pytest'i geçti.
- **Kapsam dışı:** Hukukbot'un kendi `hukukbot_db` konteyneri (`postgres:15`, ayrı repo) bu geçişe dahil değil.

## Python 3.14 ve sonrası

reportlab 5 (G244) yeşil kalırsa 3.14 engeli kalkar; 3.14'e geçiş ayrı bir sonraki adım olarak bir sonraki aylık
denetimde değerlendirilir.

## Node 26 sonrası (bu planın dışında, sıradaki frontend majorları)

vite 8 + `@vitejs/plugin-react-swc` 4 + vitest 5 (Eylül raporu §5.11). Node 26'ya geçtikten sonra ayrı plan.
Not: host'ta Node v22.16.0 kurulu (vitest host'ta koşar); CI ve imaj Node 24. Host sürümünün yükseltilmesi
kullanıcı adımıdır (gece koşucusu sistem kurulumu yapmaz).
