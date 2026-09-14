# Performans denetimi — 2026-09-14

> **Şerh — uygulamada değişti (2026-09-14, G193).** Aşağıdaki gövde denetim gününün
> fotoğrafıdır ve DEĞİŞTİRİLMEDİ; satır numaraları o günün kodudur. Bulguların sonraki
> durumu main `e3ba26d` koduna göre aşağıdadır. Bu şerh kodun prod'a çıkıp çıkmadığını
> söylemez. Güncel anlatım: `CLAUDE.md` ("İki katmanlı nginx", "Dava arama"),
> `docs/mimari/genel-bakis.md` §2 ve §7, `docs/mimari/deploy-ve-altyapi.md` §11-§13,
> `docs/kararlar/018-index-temizligi-37-kalem.md` "Nihai index durumu".
>
> | Bulgu | Durum | Görev | Kodda (main `e3ba26d`) |
> | --- | --- | --- | --- |
> | F1, F2 | kapandı | G182 | `frontend/src/App.tsx:30-41` 12 sayfa `lazy`, Login/NotFound statik; `:105-149` tek `Suspense` |
> | F3 | kapandı (ağır sayfalar) | G184, G185 | `hooks/useConfig.ts:159` `useConfigList`; `App.tsx:47` `refetchOnWindowFocus:false`; 32 sorguluk `useConfig()` bilinçli kalanlar: AdminPage, NewCase, IntakeReviewStep, AnalysisResults, BulkUploadWorkbench, CaseTrackingPanel, YetkiBelgesiModal |
> | F4 | kapandı | G187 | `pages/AdminPage.tsx:366` yalnız sürükleme geçici sırası state'te (`pendingOrders`) |
> | F5 | kapandı | G186 | `pages/CaseDetails.tsx:195` modül düzeyi `DocCard` |
> | F6 | kapandı (KVKK maddesi) | G188 | `components/YetkiBelgesiModal.tsx:32-33` TC önbelleklenmez, `sessionStorage` `:v1`, eski kalıcı anahtar modal açılınca silinir |
> | F7 | kapandı | G188 | `components/theme-provider.tsx:14` try/catch'li okuma; `App.tsx:244-250` sağlayıcı `ErrorBoundary` içinde |
> | F8, F9 | kapandı | G186 | `pages/Index.tsx:120` tek okumalı lazy initializer (sayaç = liste uzunluğu); bildirim effect'i `:747` primitif `noticeBelgeTuruKodu`'na bağlı |
> | F10 | kapandı | G186 | `pages/NewCase.tsx:1728` `key`'li `NewCaseForm` + lazy initializer'lar |
> | F11 | **AÇIK** (görev açılmadı) | — | `pages/CaseList.tsx:169,222` elle `fetchCases` + `useEffect` |
> | F12 | kapandı | G182 | `src/` kodunda `import("sonner")` yok |
> | F13 | **bilinçli açık** | — | `frontend/index.html:55` Google Fonts stylesheet |
> | F14 | konteyner katmanında kapandı; **host nginx prod'da doğrulanacak** | G182 | `nginx.conf:77-99` |
> | D1 | kısmen kapandı | G190 | dört `cases` trigram'ı `database.py:1395-1398`; `klasor_no_2`, ham `responsible_lawyer_name`, `notes`, `case_history.old_value` index'siz; `notes`/`old_value` çıkarma **kullanıcı kararı açık** |
> | D2 | kapandı | G189 | `database.py:1404-1406` (eklenen) + `:1333-1335` (düşen); `uq_cases_sistem_no` dokunulmadı |
> | D3 | **bilinçli açık — prod ölçümüne bağlı** | ölçüm aracı G183 | `scripts/perf_olcum.py` bölüm 1 (şişme); VACUUM FULL / pg_repack kararı prod çıktısıyla |
> | D4 | kapandı | G190 | `managers/case_manager.py:956-964` tek id listesi, COUNT yok |
> | D5 | kapandı | G191 (önkoşul G194) | `database.py:65-96` idle/lock timeout; `migrate.py:25-30` muafiyet |
> | D6 | kapandı | G191 | `docker-compose.yml:22` `postgres.command:`; `database.py:1620` `_ensure_pg_stat_statements` |
> | D7 | **bilinçli açık — prod sayacına bağlı** | ölçüm aracı G183 | `scripts/perf_olcum.py` bölüm 4; düşürme kodu yok |
> | D8 | kapandı (tavan; keyset kapsam dışı) | G192 | `routes/cases.py:92` `offset le=10000` |
> | D9 | kısmen: CHECK `NOT VALID` eklendi, **VALIDATE açık** | G195 | `database.py:1229` madde 52; VALIDATE prod `perf_olcum` durum bölümünde üçlü dışı = 0 olunca |
> | D10 | kapandı (DROP yarısı; `models.py` değişmedi) | G192 | `database.py:1295-1314` |
> | D11 | kapandı | G192 | `routes/cases.py:413`, `routes/clients.py:164` tek `in_()` |
> | D12 | **bilinçli açık** (aciliyet yok) | — | `models.py` `Column(JSON)` kolonları aynı |
> | D13 | **bilinçli açık** (gece, tek transaction) | — | değişiklik yok |
> | D14 | **bilinçli açık** (tek konteyner) | — | `backend/` kodunda `skip_locked` yok |
> | D15 | kapandı | G192 | `services/upload_queue.py:506-507` vade koşulu SQL'de |
>
> §4'teki prod doğrulama listesi hâlâ geçerlidir (hiçbiri prod'da koşulmadı); sırası
> `docs/mimari/deploy-ve-altyapi.md` §12 "Deploy sonrası prod doğrulama sırası"nda.

> Tarihli fotoğraf (bkz. `docs/arsiv/README.md`). Kod ve veritabanı DEĞİŞTİRİLMEDİ; yalnız
> ölçüm + salt okunur sorgu. Kural setleri: Vercel `react-best-practices` (Vite SPA'ya
> uygulanabilir olanlar; Next.js kuralları atlandı) ve Supabase `postgres-best-practices`
> (RLS kuralları atlandı; tenant filtresi uygulama katmanında). Grafik: graphify c587ff6.

## 0. Ortam ve yöntem

- Kod: main `c587ff6`. Lokal Docker stack (backend 47 saat, postgres 2 gün ayakta).
- Frontend: `npm run build` (host) + tarayıcıda `/login` yükleme ölçümü + sourcemap'li
  ayrı build (scratchpad) ile bundle'ın modüllere dağılımı.
- DB: prod'un restore kopyası; **yazma trafiği yok, süreler prod'u temsil etmez**, sorgu
  planları (seq scan / index seçimi / join biçimi) anlamlıdır. `pg_stat_*` sayaçları
  11.09'dan beri. Tam EXPLAIN çıktısı oturum scratchpad'inde (`explain_out.txt`, 1.067 satır).

## 1. Ölçülen gerçekler

| Ölçü | Değer |
| --- | --- |
| JS bundle (tek chunk) | 1.529 kB minified · 422 kB gzip |
| CSS | 85 kB · 16 kB gzip |
| `/login` DOMContentLoaded (lokal, sıcak) | 1.296 ms — JS aktarımı 50 ms, kalan çözümleme/çalıştırma |
| Google Fonts stylesheet (3 aile / 8 ağırlık) | 279 ms, render-blocking |
| Hash'li asset `Cache-Control` | YOK (konteyner nginx; gzip açık, ETag zayıf) |
| Bundle dağılımı | npm 732 kB / src 758 kB; `@azure/msal-*` 220 kB, react-dom 141 kB, rapor katmanı 128 kB, admin 74 kB, `@dnd-kit` 45 kB |
| DB | PostgreSQL 15.15, 178 index / 47 MB; cases 14.578 (89 kolon, ~2,9 KB/satır), case_parties 50.648, case_foys 9.749, case_history 9.520 |
| FK index eksiği | 0 |
| `timestamptz` | 73/73 kolon |
| Arama `q=Bora` sayfa sorgusu | 27.154 buffer hit + 1.358 read · 332 ms soğuk / 55 ms sıcak; 17 UNION kolundan 12'si seq scan |
| Şişme (heap / canlı veri) | case_history 21 MB / 1 MB · case_foys 36 MB / 11 MB · cases 11 MB / 5 MB |

Sağlıklı bulunanlar: liste sayfa 1 (`idx_cases_updated_at_id`) 1,5 ms; status filtreli liste
0,3 ms; deadline_scanner 1,1 ms; upload_outbox taraması 0,04 ms; rapor motoru tipik sorgu
4,7-5,6 ms; lucide-react tree-shake doğru (115 ikon, 43 kB); hook'larda seri `await` yok;
sanallaştırma gerektiren uzun liste yok (sayfa boyları 10-50).

## 2. Frontend bulguları (etkiye göre)

| # | Kural | Yer | Sorun | Etki | Öneri |
| --- | --- | --- | --- | --- | --- |
| F1 | bundle-dynamic-imports | `frontend/src/App.tsx:18-33`, `vite.config.ts` | 14 sayfa statik import, `React.lazy` / `manualChunks` yok → tek chunk | Yüksek | Route `element`'lerini `React.lazy` + `Suspense` ile sar |
| F2 | bundle-conditional | `App.tsx:98-113`, `pages/AdminPage.tsx:143` | Yalnız admin'in açtığı `/admin` + `/reports` (247 kB min, ~70 kB gzip) herkese iniyor | Yüksek | Önce bu iki route'u lazy yap; dnd-kit + rapor katmanı kendiliğinden ayrılır |
| F3 | rerender-split-combined-hooks / client-swr-dedup | `hooks/useConfig.ts:147-188`, `App.tsx:34` | Tek hook 32 `useQuery`; 14 tüketici 1-2 liste için 32 observer'a abone; `refetchOnWindowFocus` varsayılan → odakta 32 istek | Yüksek | Liste başına hook ya da `useQueries`+`select`; QueryClient'ta `refetchOnWindowFocus:false` |
| F4 | rerender-derived-state-no-effect | `pages/AdminPage.tsx:222-243` | 13 `useEffect` query verisini local state'e kopyalıyor (64 useState'li bileşen, çift render) | Orta | Render sırasında türet; yalnız sürükleme geçici sırasını state'te tut |
| F5 | rerender-no-inline-components | `pages/CaseDetails.tsx:881` | `DocCard` render içinde IIFE'de tanımlı → her tuşta tüm kartlar unmount/mount | Orta | Modül düzeyine çıkar, prop geçir |
| F6 | client-localstorage-schema | `components/YetkiBelgesiModal.tsx:27,43-45,201-204` | TC + sicil no sürümsüz anahtarla kalıcı localStorage'da, `setItem` try/catch'siz; `lib/formDraft.ts:10-11` kuralıyla çelişir | Orta | try/catch + `:v1`; TC'yi sessionStorage'a al ya da önbellekleme |
| F7 | client-localstorage-schema | `components/theme-provider.tsx:18,42`, `App.tsx:213-225` | Storage okuması try/catch'siz ve ErrorBoundary DIŞINDA → storage kapalıysa beyaz ekran | Orta (nadir) | `DashboardViewProvider.tsx:7-14` deseni gibi sar |
| F8 | rerender-lazy-state-init | `pages/Index.tsx:117-118`, `lib/todayUploads.ts:36-47` | Her render'da iki localStorage okuma + JSON.parse | Orta/düşük | `useState(() => …)`, tek okumadan türet |
| F9 | rerender-dependencies | `pages/Index.tsx:697-742` | Effect nesne kimliğine bağlı, yalnız `belge_turu_kodu` kullanıyor → gereksiz fetch | Düşük | Bağımlılığı primitif değere indir |
| F10 | rerender-derived-state-no-effect | `pages/NewCase.tsx:346-357` | `editModeCase` effect ile 7 state'e kopyalanıyor (boş → dolu çift render) | Düşük | Lazy initializer ya da `key={editModeCase?.id}` |
| F11 | client-swr-dedup | `pages/CaseList.tsx:166-180` | Elle fetch, cache yok; detaydan dönüşte tam refetch | Düşük | `useQuery(["cases", filtreler])` |
| F12 | bundle-conditional | `App.tsx:182`, `lib/api.ts:134` | `import("sonner")` dinamik ama 24 dosyada statik → bölme olmuyor (Vite uyarısı) | Düşük | Statik import'a çevir |
| F13 | rendering-resource-hints | `frontend/index.html:55` | Google Fonts stylesheet render-blocking, dış ağ bağımlılığı | Düşük | Self-host ya da `media="print" onload` erteleme |
| F14 | (nginx) | `nginx.conf` | Hash'li asset'lere `Cache-Control: public, max-age=31536000, immutable` yok | Düşük | `location /assets/` bloğu; prod host nginx'i ekliyorsa gereksiz — DOĞRULA |

**Kazanç tahmini (sourcemap dağılımı, importer'lar grep ile doğrulandı):** route'a özgü kod
≈ 588 kB minified (%39) → ilk yüklemeden ~130-165 kB gzip çıkar; dashboard kullanıcısı için
ilk chunk 420 → ~260-290 kB gzip. Yalnız F2 (iki admin route'u) admin olmayan herkesten
~70 kB gzip düşürür. Kalan çekirdek (msal ~60 kB gzip + react-dom) ertelenemez.

## 3. Veritabanı bulguları (etkiye göre)

| # | Kural | Yer | Sorun | Kanıt | Etki | Öneri |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | query-missing-indexes | `backend/managers/case_manager.py:740-796` `_term_case_id_selects` | 17 UNION kolundan 12'si seq scan (cases ×7, case_foys ×3, case_history, case_esas_numbers) | `Rows Removed by Filter: 14578` her kolda; 27 k buffer | Yüksek | G042 kararını bu kanıtla yeniden aç: gerçekten aranan kolonlara `gin_trgm_ops`; az kullanılan kolları (notes, old_value) aramadan çıkar |
| D2 | query-index-types | `idx_cases_tku_no_trgm`, `idx_cases_sistem_no_trgm`, `idx_cases_tku_no`, `uq_cases_sistem_no` | Index'ler BOŞ legacy kolonlarda (`cases.tku_no`/`sistem_no` 0 dolu); asıl aranan `case_foys.tku_no` (8.140) / `sistem_no` (8.395) / `onceki_tracking_no` index'siz | 3 seq scan × 4.635 sayfa, kol başına 5-176 ms | Yüksek | Üç case_foys kolonuna trgm GIN; cases'teki dört boş-kolon index'ini düşür |
| D3 | monitor-vacuum-analyze | `case_history`, `case_foys`, `cases` | 11.09 tarihçe temizliği sonrası şişme; seq scan'ler ölü sayfa okuyor | case_history 2.750 sayfa, 91 ms soğuk | Yüksek (D1/D2'yi katlar) | Bakım penceresinde `VACUUM (FULL, ANALYZE)` ya da pg_repack; ÖNCE prod'da aynı ölçüm (temizlik Deploy #26 ile prod'da) |
| D4 | query · çift koşu | `case_manager.py:914` (`count()`) + `:940` | UNION ağacı istek başına İKİ kez koşuyor; sayfa sorgusunda dış `cases` Hash Join ile tam taranıyor | 2 × 27 k buffer | Orta-yüksek | id kümesini bir kez al (CTE MATERIALIZED / Python listesi), `total=len(ids)`, sayfa `id IN (...)` |
| D5 | conn-idle-timeout | `backend/database.py:54-59` | Yalnız `statement_timeout=30000`; `idle_in_transaction_session_timeout=0`, `lock_timeout=0`; autocommit kapalı → SELECT sonrası "idle in transaction" | sunucu ayarı | Orta | options'a `-c idle_in_transaction_session_timeout=60000 -c lock_timeout=5000` (migrate.py hariç) |
| D6 | conn-limits | `docker-compose.yml:3-34` | Postgres için conf yok → `shared_buffers=128MB`, `effective_cache_size=4GB` (mem_limit 512m ile tutarsız), `random_page_cost=4`, pg_stat_statements yok | `SHOW` çıktıları | Orta | compose `command:` ile `effective_cache_size=384MB random_page_cost=1.1 shared_preload_libraries=pg_stat_statements`; `max_connections=100` yeterli (havuz 60) |
| D7 | schema · yazma maliyeti | `cases` 16 index (HOT %15), `case_parties` 8 index (`name` üç kez) | idx_scan=0 adayları: `ix_cases_esas_no`, `idx_cases_tenant`, `idx_cases_tracking_name_block`, `ix_case_lawyers_name`, `idx_case_lawyers_lawyer`, `idx_case_parties_tc_no`, `ix_clients_name` | lokal sayaç — karar DEĞİL | Orta | Prod `pg_stat_user_indexes`'te 30 gün doğrula, `("index", ...)` op'uyla düşür |
| D8 | data-pagination | `case_manager.py:940-942`, `routes/cases.py:90` | OFFSET/LIMIT, `offset` tavansız | offset 10000 → 65 ms / 8.023 buffer (sayfa 1: 1,5 ms / 71) | Orta-düşük | Aramasız listede keyset `(updated_at, id)`; arama modunda tavan |
| D9 | schema-constraints | şema | Hiç CHECK yok; `cases.status` üçlüsü yalnız uygulama ile korunuyor | `contype='c'` 0 | Orta-düşük | Idempotent `CHECK (status IN (...))`; önce prod'da ihlal taraması |
| D10 | schema-primary-keys | 20 tablo | PK'yı tekrar eden `ix_<tablo>_id` (SQLAlchemy `index=True`) + `idx_case_docs_conversion_pending (id)` | — | Düşük | Modelde `index=True` kaldır + DROP |
| D11 | data-n-plus-one | `routes/cases.py:391-405`, `routes/clients.py:158-168`, `case_manager.py:1857-1858` | Döngü içinde sorgu (ilişki başına, poliçe başına — `original_filename` index'siz) | 229 satır bugün | Düşük | `in_()` ile tek sorgu |
| D12 | schema-data-types | `case_foys.ham_veri`, `report_runs.tanim`, `report_templates.tanim`, `aktarim_teslimleri.yapi/durum_gecmisi` | `json` (jsonb değil); varchar sınırlı/sınırsız karışık | ham_veri ort. 1.231 B | Düşük | Yeni kolonlarda `jsonb`/`text`; mevcutler için aciliyet yok |
| D13 | lock-short-transactions | `scripts/hukdok_aktarim.py:3297-3480` | Tüm paket tek transaction (8.409 satır / 93 sn) → 04:00 TR'de ~1,5 dk satır kilidi | ölçüm 20.08 | Düşük (gece) | Bilinçli; gündüz elle `--apply` koşulmamalı |
| D14 | lock-skip-locked | `services/singleton_lock.py:86-106`, outbox tüketicileri | Dosya kilidi tek konteynerde doğru; `FOR UPDATE SKIP LOCKED` yok → 2. konteynerde çift işleme | — | Düşük | `with_for_update(skip_locked=True)` ya da advisory lock |
| D15 | query-partial-indexes | `services/upload_queue.py:494-500` | Tüm `pending` çekilip vade Python'da eleniyor; parçalı index'in `next_attempt_at` koşulu sorguda yok | 0 satır | Düşük | Vade koşulunu SQL'e taşı |

## 4. Prod'da doğrulanmadan karar verilmeyecekler

1. Şişme oranı: `pg_relation_size('case_history')` vs `sum(pg_column_size(h.*))` — aynı oran
   çıkarsa VACUUM FULL / pg_repack penceresi.
2. Arama süresi: bir avukat soyadı + bir esas no ile `EXPLAIN (ANALYZE, BUFFERS)` (D1/D2/D4).
3. `SHOW shared_buffers; SHOW effective_cache_size; SHOW idle_in_transaction_session_timeout;
   SHOW max_connections;` (D5/D6).
4. Mesai içinde `pg_stat_activity` "idle in transaction" sayısı; `pg_stat_user_indexes` 30 gün
   `idx_scan` (D7/D10) — düşürme yalnız prod sayacıyla.
5. `SELECT status, count(*) FROM cases GROUP BY 1` (D9).
6. Host nginx'in `/assets/` için `Cache-Control` gönderip göndermediği (F14).

## 5. Önerilen sıra (karar kullanıcının)

1. **F1+F2** route lazy (tek PR, düşük risk, ölçülebilir: ilk chunk gzip 420 → ~280 kB).
2. **D3** prod şişme ölçümü → bakım penceresi; **D2** case_foys trgm index + boş index'leri
   düşürme (`("index", ...)` op'u, G041 kuralı).
3. **D1+D4** aramayı tek koşuya indir + kanıtlı index'ler (G042 kararına ek not).
4. **F3** useConfig bölme + `refetchOnWindowFocus:false`.
5. **D5+D6** bağlantı/sunucu ayarları (compose `command:` + engine options; `.env` gibi
   `up -d` recreate ister).
6. Geri kalanı fırsat buldukça; F6 (TC localStorage) performans değil KVKK maddesi, ayrı ele al.
