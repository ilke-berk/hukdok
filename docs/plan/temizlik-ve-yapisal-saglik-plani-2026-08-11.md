# Temizlik, Bölme ve Yapısal Sağlık Planı — 2026-08-11

Kullanıcının sorusundan doğdu: *"Eklenen her özellik, düzeltilen her hata bize kod satırı
olarak dönüyor; kontrolden çıktık mı, bir planla temizlemeli miyiz?"*

## Hüküm

**Hayır — kod kontrolden çıkmadı.** Ölçüldü: kopyala-yapıştır oranı backend %0,13 / frontend
%0,58 (jscpd), lint 0 hata, test dışı frontend kaynağında sıfır `any`, 2.000 satırı aşan tek
bir üretim dosyası yok. Büyüme gerçek ama en büyük kalemi testler.

**Borç dört dar noktada toplanmış** ve hepsi FAZ 0–E ile kapanıyor: (1) hata yutan kapılar,
(2) Python tarafında O(N) tarama yapan üç sıcak yol, (3) sessizce hiç çalışmamış migrasyon
op'ları, (4) yamalanmamış bağımlılıklar. **Büyük yeniden yapılandırma (dosya bölme) bu planda
kapsam dışıdır** — gerekçesi ölçülmedi, tetikleyiciye bağlandı (bkz. §9).

---

## Kanıt düzeyi — bu planı okurken bilmen gereken

> **UYARI.** Aşağıdaki ölçümler **lokal restore kopyası** üzerinde alındı, **prod'dan tek bir
> okuma yapılmadı.** Kanıt: `confirm_receipts` 0 satır, `export_outbox` 0 satır,
> `cases.n_tup_ins` = 3, en yeni dava 2026-07-30. Bu veritabanı prod iş yükünü hiç görmedi.
>
> Sonuç: **index kullanım istatistikleri, autovacuum teşhisi ve süre ölçümleri prod'u temsil
> etmez.** FAZ D ve FAZ E'nin ön koşulu prod'da tek seferlik salt-okunur ölçüm setidir (§6.0).
> Kod okumasına, şema yapısına ve davranış kanıtlarına dayanan bulgular bu uyarının dışında —
> onlar ortamdan bağımsız.

Plan iki turlu üretildi: 14 ajanlı keşif (7 alan + 7 adversarial doğrulayıcı) → taslak →
11 ajanlı denetim paneli (5 lens + doğrulayıcıları + eksiklik eleştirmeni). Panel taslağın
**dört iddiasını çürüttü**; hepsi bu sürümde düzeltildi (§10).

---

## 1. Ölçüm: büyüme gerçekte ne?

| Ay | Eklenen | Silinen | Net | Silme oranı |
| --- | --- | --- | --- | --- |
| 2026-04 | 6.335 | 5.214 | +1.121 | %82 |
| 2026-05 | 13.751 | 1.382 | +12.369 | %10 |
| 2026-06 | 13.982 | 5.453 | +8.529 | %39 |
| 2026-07 | ~23.000–27.000 | ~5.100–5.500 | — | ~%20 |
| 2026-08 (11 gün) | 27.464 | 2.221 | +25.243 | **%8** |

*(Temmuz satırı iki bağımsız ölçümde farklı çıktı — muhtemelen lock dosyası/merge sayımı;
eğilim değişmiyor, kesin rakam için tek bir sayım yöntemi sabitlenmeli.)*

Tüm tarih: 121.456 eklendi / 23.486 silindi → **%19**. Ağustos'un +25.243 net satırı:

| Alan | Net | Pay |
| --- | --- | --- |
| test | +10.291 | **%41** |
| backend kod | +5.724 | %23 |
| süreç/otomasyon | +2.900 | %11 |
| docs | +2.625 | %10 |
| frontend kod | +2.605 | %10 |
| diğer | +1.098 | %4 |

**Üretim kodu tüm büyümenin %33'ü.** Teşhis: model ekleyici (silme oranı düşüyor), ama
biriken şey ağırlıkla emniyet ağı ve doküman — şişkinlik değil.

---

## 2. FAZ 0 — Canlı arızalar (temizlik değil; en yüksek öncelik)

| # | Arıza | Kanıt | Etki |
| --- | --- | --- | --- |
| **0.1** | **SSRF: .eml gövdesi LibreOffice'e giderken uzak kaynak çekiyor** | Bağımsız iki probe ile üretildi: `<table background="http://…/PROBE.png">` → sunucu kaydında `GET /TABLE_PROBE.png`. `routes/case_intake.py:96-101` yalnız `<script>`, `<link>`, `<img src=…>` siliyor; `pdf/format_converter.py:305-325` soffice'te ağ kapatan bayrak yok | Avukat kötü niyetli bir .eml'i sihirbaza sürükleyince prod VM saldırganın seçtiği adrese istek atıyor (kör SSRF + izleme pikseli). Kimlik doğrulamalı uç → uzaktan-kimliksiz değil, "confused deputy" |
| **0.2** | Mükerrer dava kapısı **iki katmanda birden** hata yutuyor | Frontend `useCases.ts:200-210` → `[]`; **backend** `case_manager.py:805-807` `except: return []`; `routes/cases.py:185` 200 + boş matches döndürüyor | DB hatasında mükerrer kapısı sessizce açılıyor. **Yalnız frontend'i düzeltmek yetmez** — backend ayağı da düzelmeli |
| **0.3** | `useConfig` hatayı boş listeye çeviriyor | `useConfig.ts:66` ve `:112` | Konfig ucu düşünce zorunlu alan kapısı sessizce açılıyor |
| **0.4** | Ofis dosya no sıra tahsisi hatada `1`e düşüyor | `routes/cases.py:168-170` `except: return {"sequence": 1}` | Sıra çakışması riski |
| **0.5** | Ofis no kategori kodu çatallanması | `caseNumberUtils.ts:111-118` kategori **adı** bekliyor; `NewCase.tsx:341` ve `IntakeReviewStep.tsx:242` **kod** ("D1") geçiyor → `block1` sessizce `"X1"`e düşüyor. `QuickCaseModal.tsx` doğru | Canlı veride **X1 = 1.658 kayıt (%11,6)**. Bkz. aşağıdaki karar kutusu |
| **0.6** | Prod export/hukukbot sağlık denetimi | Lokal `export_outbox` 0 satır → keşif bu yüzeyi **görmüş olamaz** | Prod'da birikmiş `failed` satır olabilir; salt-okunur bakılmalı, çıkan arıza bu listeye eklenmeli |
| **0.7** | `/preview-client-email-body` nginx'te proxy'lenmiyor | `nginx.conf` location listesi: `/`, `= /healthz`, `/api`, `/process`, `/confirm`, `/preview-email-body`, `/refresh` — müvekkil olanı **yok**. `frontend/vite.config.ts` dev proxy'sinde **ikisi de yok** | Müvekkil bilgilendirme AI metni sessizce yanlış tonlu frontend fallback'ine düşüyor. Aynı allowlist üç yerde elle tutuluyor ve üçü de sapmış |
| **0.8** | `/api/documents` bağlantısız belgelerde tenant izolasyonu **yok** | `routes/documents.py:169` `or_(Case.tenant_id==tid, Case.tenant_id.is_(None), CaseDocument.case_id.is_(None))` — üçüncü şart tenant kısıtını devre dışı bırakıyor; uçta `get_current_user` bağımlılığı bile yok | Her tenant tüm bağlantısız belgeleri görüyor (`uploaded_by`, `stored_filename`, `muvekkil_adi` dahil). Tekil belge yolları `get_tenant_owned_document` ile "case_id yoksa yalnız yükleyen" kuralını uyguluyor — **liste ucu bu korumanın dışında** |

> **KARAR GEREKTİRİR (0.5).** Düzeltme deploy edilince aynı müvekkil kategorisi dün X1, bugün
> D1/H1 üretir — arşivde iki rejim oluşur. Üç seçenek: **(a)** dokunma, iki rejimi kabul et;
> **(b)** `backend/scripts/retag_tracking_nos.py` ile 1.658 kaydı geriye dönük düzelt (SharePoint
> klasör adları ve dış yazışmalardaki referanslar DB'den ayrışır — kapsam ve geri dönüş yazılı
> olmalı); **(c)** yalnız yeni kayıtlar + eskiler için eşleme tablosu. Bu **operasyonel** bir
> karar, teknik değil. Seçim `docs/kararlar/` altına ADR olarak yazılmalı.

> **`service_type` ayrı bir iş olarak ayrıldı.** Canlı: `count(*)/count(service_type)` =
> **14.345 / 0**. Yazma yolunu düzeltmek (kayıt yüküne alanı ekle) FAZ 0'a girer. **Backfill
> girmez:** taslaktaki `split_part(tracking_no,'.',5)` reçetesi canlı veride çürüdü —
> 12.013 satırda boş, 1.032'sinde `"00000"`; 4. parça da kurtarmıyor (12.689 boş). Sabit-pozisyon
> hiçbir reçete bu korpusta doğru değil. Backfill ayrı bir keşif işi olarak sıraya alınır.

---

## 3. FAZ A — Davranışsız hızlı kazanımlar (emniyet ağını beklemez)

Bunlar davranış değiştirmez ve karakterizasyon testleriyle ilgisi yoktur; L bir fazın arkasına
kilitlenmemeliler.

**A.1 nginx gzip'i aç.** Konteyner nginx'inde gzip kapalı; JS chunk'ı **1.324.033 bayt** ham,
gzip'li karşılığı **361.003 bayt**. Tek config satırı. *(S)*
*Not: ~10 kullanıcı ölçeğinde bu tek seferlik bir kazanç — büyük ama dar.*

**A.2 Gerçek müvekkil verisini geliştirme makinesinden kaldır.** *(Taslakta yanlış çerçevelenmişti
— bkz. §10.)* `backend/data/hukudok.db` **140 MB** legacy SQLite (kodda sıfır referans) ve
`backend/calibration/` **139 MB** gerçek müvekkil PDF'i, `C:\Users\...\OneDrive\Masaüstü\...`
altında — yani **üçüncü taraf buluta senkronlanıyor**. İçerik: 1.998 müvekkil, 14.345 dava,
49.857 taraf. Gerçek eylem: (1) legacy SQLite'ı sil, (2) calibration'ı OneDrive senkronu
dışına taşı, (3) eski lokal imaj etiketlerini temizle, (4) `backend/.dockerignore` yaz.
**Bu bir KVKK/veri envanteri maddesidir, prod sızıntısı değil** — prod build context'i git
klonu olduğu için bu dosyalar prod imajında yok. *(S)*

**A.3 `init: true`.** Her soffice dönüşümü 5 zombie süreç bırakıyor (ölçüldü: 212 → 230);
konteynerde reaper yok. *(S)*

**A.4 Tanıdık sorgu aday indeksini önbelleğe al.** Planın kaçırdığı en ucuz gerçek kazanç:
`party_check` her istekte aynı **51.855** adayı yeniden çekiyor (427 ms DB) ve yeniden
normalize ediyor (`normalize_person_name` istek başına 51.859 çağrı; 20 isimlik istekte
~1,04 M çağrı). Repoda `managers/ttl_cache.py` **zaten var**. TTL cache + `lru_cache`,
**sıfır davranış değişikliğiyle** DB maliyetini sıfırlar ve CPU'nun kayda değer kısmını alır.
Kabul kriteri: mevcut `party_check` testleri değişmeden yeşil + 1 ve 20 isim için önce/sonra
ölçüm. **Bu yapıldıktan sonra FAZ E'nin party_check maddesi yeniden değerlendirilmeli —
muhtemelen L'lik SQL göçüne hiç gerek kalmaz.** *(S)*

**A.5 Bağımlılık yamalama.** *(Taslakta tamamen eksikti.)* `pip-audit`: 7 pakette 57 kayıt
(~43 distinct) — **PyJWT 2.8.0** (token doğrulamasının kendisi), **python-multipart** (tüm
dosya yüklemelerinin ayrıştırıcısı), **Pillow** (kullanıcı görüntülerini decode eder),
cryptography, starlette, requests. `npm audit`: 22 (15 high) — axios, postcss, vite,
react-router-dom.
> **Tuzak:** "pip-audit'i CI kapısı yap" olduğu gibi uygulanırsa **CI kalıcı kırmızı kalır** —
> PyJWT PYSEC-2025-183'ün fix sürümü yok. Kapı bir **ignore listesiyle** kurulmalı, liste
> gerekçeli ve tarihli olmalı.
> **Bonus:** `@xmldom/xmldom` ve `underscore` (high) `mammoth`'tan, `jszip` `docx`'ten geliyor —
> FAZ C'deki ölü paket silmesi bu advisory'leri zaten kaldırır.

**A.6 Çalışma zamanı yaşlanması.** `node:20` bugün EOL; `python:3.10` iki ay sonra. Yükseltme
planı bu fazda **karara** bağlanmalı (uygulama ayrı iş). *(S — karar)*

> **ÖLÇÜM ŞERHİ (G022, 2026-08-11) — A.5 ve A.6 karara bağlandı.**
> Yukarıdaki iki madde bu tarihte yeniden ölçüldü ve
> [`docs/kararlar/013-bagimlilik-yamalama-ve-calisma-zamani.md`](../kararlar/013-bagimlilik-yamalama-ve-calisma-zamani.md)
> ile kapatıldı. **Yukarıdaki metin bilinçli olarak silinmedi**; aşağıdaki düzeltmelerle
> birlikte okunmalıdır:
>
> - **`npm audit` 22/15 doğrulandı**, ama sayı tek başına yanıltıcı: `--omit=dev` ile
>   **10 açık (4 moderate / 6 high)** kalıyor — 12'si yalnız derleme zincirinde (vite,
>   esbuild, rollup, eslint), tarayıcı bundle'ında değil.
> - **`jszip` iddiası çürüdü:** `jszip@3.10.1`'in bugün advisory'si yok. `docx`'i silmenin
>   getirisi `docx/node_modules/nanoid`. `@xmldom/xmldom` + `underscore` ↔ `mammoth` bağı doğru.
>   G021 sonrası beklenen: prod **7 paket (4 moderate / 3 high)**, tümü **20 paket (13 high)**.
> - **Python tarafı "7 pakette 57 kayıt (~43 distinct)" yerine ölçülen: 73 ham / 39 distinct,
>   7 paket** (Pillow 17, cryptography 7, python-multipart 6, PyJWT 6, requests 1,
>   python-dotenv 1, pytest 1-dev). Fix sürümü olmayan **tek** kayıt PyJWT `PYSEC-2025-183`
>   — planın uyardığı tuzak doğrulandı.
> - **Plan `starlette`'i doğrudan pin sanıyordu; değil.** `requirements.txt` transitif
>   bağımlılıkları sabitlemiyor (lock yok) → imajdaki sürüm repodan okunamıyor. Yine de kesin:
>   `fastapi==0.121.3` → `starlette<0.51.0` ve bu aralıktaki **her** sürüm ≥10 kayıt taşıyor;
>   ilk temiz starlette **1.5.0**, ona ulaşmak **fastapi yükseltmesi** gerektiriyor. Gerçek
>   prod tabanı bu yüzden 39 değil **en az 49**.
> - **`node:20` "bugün EOL" değil — 2026-04-30'da EOL oldu**, yani 3,5 ay gecikmedeyiz
>   (kaynak: nodejs/Release `schedule.json`). `python:3.10` EOL **2026-10-31** (doğrulandı).
>   Karar: **`node:24`** (Aktif LTS, EOL 2028-04-30) ve **`python:3.12`** (EOL 2028-10-31;
>   3.13 reddedildi — `psycopg2-binary==2.9.9`'un cp313 tekerleği yok).
> - **A.5 artık *(S)* değil.** PyJWT'nin tek tüketicisi `auth_verifier.py` ve **sıfır testi
>   var**; yükseltmesi FAZ B.3 karakterizasyon testinin arkasına kilitlendi. `npm` tarafı ve
>   python-multipart/Pillow/cryptography/requests/python-dotenv *(S)* olarak kalıyor.
> - **Kapı tasarımı ADR'de:** `pip-audit` kurulu ortamı denetler (transitif körlüğü lock'suz
>   kapatır); ignore listesi `backend/audit-ignore.txt`'te gerekçeli ve **tarihli** yaşar,
>   tarihi geçen satır kapıyı kırmızıya çevirir. Frontend kapısının ön koşulu:
>   `frontend/Dockerfile:8-9` lock'u kullanmıyor (`npm install`, `package-lock.json`
>   kurulum anında yok) → CI'ın denetlediği ağaç ile prod'un yayınladığı ağaç aynı değil.

---

## 4. FAZ B — Emniyet ağı

| Ölçüm | Değer |
| --- | --- |
| Backend pytest | 868 passed / 2 skipped, 17,45 sn |
| Backend uygulama kapsamı | **%58,5** |
| `case_manager.py` / `routes/cases.py` / `routes/clients.py` / `routes/config.py` | %28,8 / %27,4 / %21,4 / %34 |
| Gerçek Postgres'e dokunan test | **0** |
| Açılış migrasyonu (39 adım) | Hiçbir testte çalışmıyor |
| Frontend `src/pages` (10.882 satır) | **0 test dosyası** |
| Sıfır kapsamlı modüller | `report_builder.py`, `yetki_belgesi_generator.py`, `vault.py`, `managers/reference_list_export.py` |
| CI | 5/5 yeşil, ~1 dk — ama **main korumasız**, `deploy.sh`'ta test kapısı yok |
| `pytest-cov` | `requirements-dev.txt`'te **yok** — kapsam klondan tekrarlanamaz |

**B.1** `pytest-cov`'u `requirements-dev.txt`'e ekle; CI'ya `--cov` + mütevazı `--cov-fail-under`. *(S)*
**B.2** Main'e branch protection, `deploy.sh`'a test kapısı. Bugün CI kapı değil bildirim. *(S)*
**B.3** Route/ORM karakterizasyon testleri. **Önce ucuz reçete:** `TestClient` + manager katmanı
monkeypatch'i — `tests/test_case_intake_commit.py` bunu yapıyor ve `routes/case_intake.py`'yi
DB'siz %82 kapsama taşıyor. sqlite yalnız ORM sorgu semantiği (tenant / soft-delete) gerektiğinde.
Zorunlu vaka: **"DB hatası → kapı KAPALI kalıyor mu"** (0.2/0.3'ün regresyon koruması). *(L)*
**B.4** Migrasyon yolu testi — FAZ D'nin ön koşulu. *(M)*
**B.5** `CaseList` sayfalama karakterizasyon testi — `X-Total-Count` gerçek toplamı veriyor mu
(FAZ E'nin ön koşulu, bkz. §10). *(S)*
**B.6** mypy kapsamı kademeli. Geniş kapsamda bugün **128 hata** var; hepsini birden açmak
temizliği bloke eder. *(M)*
> **Frontend sayfa testleri kapsam dışına alındı** — bkz. §9. Gerekçe: tek müşterisi olan
> FAZ 6 (frontend bölme) kapsam dışı.
> **Tuzak:** `vitest.config.ts:16` `include: ['src/**/*.test.{ts,tsx}']` — `src` dışına konan
> test **sessizce toplanmaz**, hata vermez, "geçmiş" görünür.

---

## 5. FAZ C — Ölü kod ve tekrar temizliği

> **PAZARLIKSIZ KURAL (denetim dersi):** `getattr`/string-dispatch taraması yapılmadan hiçbir
> sembol ölü sayılmaz. Taslak bu yüzden **canlı kod silmeye** kalkıyordu.

| Hedef | Satır | Durum |
| --- | --- | --- |
| `components/ui/sidebar.tsx` | 637 | Silinir. En büyük ölü dosya; 5 dosyayı yapay canlı gösteren düğüm. Gerçek kenar çubuğu ayrı: `components/shell/Sidebar.tsx`. **Sıra: önce sidebar, sonra kaskad** |
| `CaseGroup` sayfası | 666 | Silinir. Hiç var olmamış bir backend ucuna bağlı |
| Diğer kullanılmayan `ui/` bileşenleri | ~1.900 | Silinir |
| `class LogManager` (`log_manager.py:26-192`) | 187 | Silinir — **ama dosya SİLİNMEZ.** Aynı dosyadaki `TechnicalLogger` (`:214-329`) 20+ modülde canlı |
| `DatabaseManager` + `SyncLog` + `AnalysisCache` | ~170 | Silinir |
| Ölü route alias'ları (5× `/config/*`, `/api/refresh`, `/api/config/refresh`) | ~45 | Silinir |
| `udf_converter.py` ölü async yol | 3 fonksiyon | Silinir |
| ~~`config_manager` setter'ları~~ | ~~45~~ | **ÇIKARILDI — CANLI.** 14 setter'ın 8'i yalnızca `reference_lists.py:532` `getattr(config, spec.setter)` üzerinden çağrılıyor; adlar `LIST_REGISTRY`'de string. Silinseydi arıza modeli sinsi olurdu: `refresh_cache` çağrıları DB commit'inden **sonra** ve dış `except` içinde → satır DB'ye yazılır, kullanıcıya "başarısız" denir |
| Ölü npm paketleri | — | **Silinir** — taslakta "getiri yok" denmişti, ama `mammoth`/`docx` iki high advisory taşıyor (A.5) |

Toplam ≈ **3.600 satır**. Test kaybı: **sıfır** (tarandı — hiçbir test bu sembollere dokunmuyor).

**C.2 `tenant_filter_clause` benimsetme.** Helper var ama **11 yerde** (taslakta 9 denmişti)
elle kopyalanmış. Güvenlik yüzeyi taşıyan tekrar, önceliklidir. Denetim ayrıca bir kopyanın
fiilen delik olduğunu buldu: **`/api/documents` bağlantısız belgeleri sahip/tenant kontrolü
olmadan listeliyor** — bu C değil **FAZ 0** maddesidir, doğrulanıp oraya taşınmalı.

> **NFD/diakritik katlama birleştirmesi FAZ C'den çıkarıldı.** 4 modüldeki katlama
> implementasyonları **birebir aynı değil**; birleştirmek davranış değiştirir ve tanıdık sorgu
> eşleşmelerini etkiler. Ayrı bir iş, altın küme testiyle (bkz. FAZ E).

---

## 6. FAZ D — Veritabanı sağlığı

### 6.0 Ön koşul: prod ölçümü *(pazarlıksız)*

Prod'da tek seferlik **salt-okunur** set koşulmadan hiçbir index kalemi kuyruğa girmez:
`pg_stat_user_indexes`, `pg_stat_user_tables`, ilgili sorgular için `EXPLAIN (ANALYZE)`,
gerçek gzip durumu. §6.2 ve §6.3'ün rakamları o çıktıyla **değiştirilir**.

### 6.1 Kök neden: migrasyon op'ları sessizce hiç çalışmıyor *(kritik, ortamdan bağımsız)*

`database.py:110` `create_all()` **önce** koşuyor; `:543` tablo listesini **sonra** okuyor;
`:589-590` `if table in tables: continue` → `("table", …)` op'ları **hiç çalışmıyor**.
Canlı doğrulama: `uq_case_relation`, `uq_daily_report` UNIQUE kısıtları yok;
`idx_case_relations_source/target`, `idx_daily_reports_user` yok. Ters yön: `create_all` mevcut
tabloya index eklemez → `models.py:212` `index=True` karşılığı `ix_clients_name` yok.

Kök neden tek noktada: `models.py`'de `__table_args__` / `UniqueConstraint` / `Index(` →
**sıfır eşleşme**. ORM bileşik kısıtı ifade edemiyor, her kısıt `database.py`'ye düşüyor ve
orada da çalışmıyor.

**Çözüm ucuz:** yeni mekanizma ya da Alembic gerekmiyor. `database.py:106`'daki
`("index", tablo, [...])` op türü zaten tanımlı, idempotent ve **çalışıyor** (canlı kanıt:
`idx_case_docs_conversion_pending`). Eksik kısıtlar bu mevcut op türüne taşınır. *(S/M)*

> **Prod riski + geri dönüş.** `migrate.py` fail-fast: UNIQUE index prod'da patlarsa **konteyner
> kalkmaz**. Önce `GROUP BY … HAVING count(*)>1` ile doğrula. Migrasyon adım adım commit'lediği
> için **kısmi arıza `rollback.sh`'ın geri getiremeyeceği bir şema bırakır** (rollback imajı
> döndürür, DB'yi döndürmez) → pre-deploy `pg_dump` ve geri dönüş adımı yazılı olmalı.

### 6.2 Index temizliği — mayınlı alan

> **TUZAK:** "Kullanılmayan index'i düşür" körlemesine uygulanırsa **ofis dosya numarası
> tekilliği silinir.** `ix_cases_tracking_no` `indisunique = true` ve `pg_constraint`'te
> karşılığı **yok** — tekilliği tutan tek yapı o, ve `idx_scan = 0` görünüyor (kısıt doğrulaması
> `idx_scan`'i artırmaz). Kullanılmayan görünen index'lerin **8'i UNIQUE/PRIMARY**.
> **Kural: liste `indisunique`/`indisprimary` olanları zorunlu dışlar ve isim kalıbıyla değil
> `pg_index.indkey` karşılaştırmasıyla üretilir.**

29 PK-ikizi index'i düşür; 4 index'siz FK kolonuna index ekle; `cases.status` için kısmi index;
`substr(tracking_no,4,10)` için fonksiyonel index (`routes/cases.py:139`, her dava açma formunda).
Net etki ≈ **−23 index** → toplu yazmayı ucuzlatır, pahalılaştırmaz. *(M, §6.0'a bağlı)*

### 6.3 İstatistik ve autovacuum

Lokalde 29/30 tabloda `last_autoanalyze` NULL — **ama bu lokal kopyanın yazma trafiği sıfır
olmasının doğal sonucu olabilir; prod'da doğrulanmadan teşhis konmaz** (§6.0). Kesin olan:
toplu import öncesi/sonrası `ANALYZE` ve dalga sonrası `VACUUM (ANALYZE)` FAZ F'nin kabul
kriteridir. *(S)*

---

## 7. FAZ E — Sorgu algoritmaları

Sorgu türü ↔ erişim yolu eşleşmesi (**düzeltilmiş rakamlarla**, lokal ölçüm):

| Sıcak yol | Sorgu türü | Bugünkü erişim | Ölçüm | Doğru yol |
| --- | --- | --- | --- | --- |
| Tanıdık sorgu | eşitlik + bulanık isim | Tüm tablo Python'a (51.855 satır) | 1 isim ~600 ms CPU + ~430 ms DB; **20 isimde 10,5 sn CPU** | **Önce A.4 (cache)**, sonra yeniden değerlendir |
| `find_matching_case` | bulanık eşleştirme | Tüm aktif dava + tarafları belleğe | 2.953 ms; **tepe bellek 244 MB (gerçek RSS deltası ~290 MB)** | SQL'de aday daraltma + yalnız gerekli kolonlar |
| Avukat filtresi | eşitlik | İki `.all()` + Python | 116 ms, doğrusal büyür | index + SQL filtre |
| Dava araması | 13 kollu OR × terim sayısı | 11 trgm index'inin hiçbiri kullanılamıyor | 83 ms → UNION **20 ms = 4,0×** (tek terim, ≥3 karakter). 2 karakterde 97 → 77 ms = **1,27×** | UNION — ama bkz. uyarı |
| Arama `count()` | aggregate | `search_cases:816`'da `_total` **atılıyor** | Her tuşta ikinci tam tarama | `with_total=False` **yalnız o çağrıya** |
| `missing_required` | korele EXISTS | Satır başına alt sorgu | 81 ms vs 19 ms | denormalize bayrak |
| Intake merge mahkeme sözlüğü | DISTINCT | Her çağrıda tam tarama | 17,8 ms | TTL cache |
| Dava kartı | ilişki yükleme | Lazy → N+1 | 5 sorgu / 58 ms | `selectinload` |

> **UNION uyarısı.** Taslaktaki "123 ms → 6,9 ms (18×)" **hiçbir kurulumda tekrar üretilemedi.**
> Gerçek: tek terim ve ≥3 karakterde 4,0×; tipik 2 karakterlik aramada 1,27×. Sebep: `cases.notes`
> aranan tek trgm'siz kolon, UNION planında Seq Scan hayatta kalıyor. Ayrıca sorgu tek OR değil —
> `case_manager.py:302-347` her terim için OR üretip AND'liyor, yani **çok terimli sorgu
> INTERSECT-of-UNION gerektirir**. Kabul kriteri: en az 20 gerçek sorguda eski/yeni id kümesi
> **ve ilk 25'in sırası** birebir aynı. Çok terimli hal kapsam dışıysa yazılsın; kapsamdaysa
> emek **L**.

> **`count()` uyarısı.** Taslak "sonuç atılıyor, kaldır" diyordu — **liste yolunda atılmıyor.**
> `routes/cases.py:97-103` `total`'ı `X-Total-Count` başlığına yazıyor;
> `CaseList.tsx:270` sayfalamayı ondan hesaplıyor. `with_total=False` genel uygulanırsa
> **sayfalama sessizce bozulur.** Yalnız `search_cases:816` yolunda uygulanır.

> **party_check → SQL göçü için sert kural.** `similarity('ALI VELI','ALI BEKI')` = **0,307** >
> pg varsayılan eşik 0,3 → `%` operatörü bu çifti **eşleştirir**; oysa `party_check.py:19-20`
> docstring'i bunu **açıkça reddediyor**. Ayrıca DB collation'ı `en_US.utf8`,
> `upper('ilker')` = `ILKER` (İ değil) — Türkçe upper'ın SQL karşılığı bu DB'de **yok**.
> Kural: **SQL yalnız geri-çağırma güvenli ön filtre olabilir**; kademe kararı
> (certain/probable/possible) ve conflict hesabı Python'da kalır. Ön koşul: üretim verisinden
> üretilmiş **altın küme testi** (≥200 isim çifti, 4 sınıf) yeşil olmadan birleşmez.
> *(Kullanıcının bilinçli onayladığı bir özellik — davranış korunacak.)*

---

## 8. FAZ F — HUKDOK aktarımı (8.409 föy)

Taslakta 10 satırlık bir başlıktı; denetim haklı olarak "plan değil" dedi.

**Düzeltme:** "cases'i %59 büyütür" iddiası muhtemelen yanlış — bu ağırlıkla bir **UPDATE
dalgası**, INSERT değil (eşleştirme köprüsü DosyaNo↔klasor_no_2 %97,4).

**Yazma yolu tasarımı gerekiyor.** Mevcut tek toplu-yazma scripti (`scripts/import_excel_cases.py`)
**idempotent değil ve hata yolunda sessizce veri kaybediyor**: `:328-331` her 500 satırda
commit, `:333-337` satır hatasında `db.rollback()` → o partideki 499 satıra kadar veri gider
ama `added` sayacı geri alınmaz (rapor "Eklendi: N" derken N satır DB'de yoktur);
`:237-244` "mükerrer koruması" skip değil — mevcut `tracking_no`'ya `-2` ekleyip **ikinci dava
yaratıyor**, yani yarım kalan koşunun tekrarı mükerrer üretir. Doğal anahtar da yok:
`klasor_no_2` 14.317 dolu / 14.204 distinct → **112 mükerrer grup**.

Gerekenler: (1) kaynak satır başına stabil dış anahtar + UNIQUE index, (2) `ON CONFLICT DO UPDATE`,
(3) satır hatasında `rollback` yerine **SAVEPOINT**, (4) işlenmiş-satır imleci (kaldığı yerden
devam), (5) kabul kriteri: *"aynı girdiyle iki kez koşulduğunda satır sayısı değişmez"*,
(6) `statement_timeout` (30 sn) miras alınıyor — batch ortasında kesilir, açıkça yükseltilmeli,
(7) dalga sonrası `VACUUM (ANALYZE)`, (8) hukukbot export tarafına etkisi.

Ayrıca `sistem_no` UNIQUE ile 1.211 birleşik kart çatışması (bilinen açık konu). *(L)*

---

## 9. Kapsam dışı — ve nedeni

> Bir planı kısaltmak da bir katkıdır. Aşağıdakiler **bilinçli olarak yapılmayacak**.

| Kalem | Neden kapsam dışı | Yeniden açma tetikleyicisi |
| --- | --- | --- |
| **Backend dosya bölme** (9.745 satır) | Ölçülmüş bir soruna karşılık gelmiyor. Dosyalar zaten sorumluluk kümelerine ayrılmış; en büyüğü 1.600 satır | Aynı dosyada bir ay içinde 3+ regresyon, **veya** bir ajanın dosyayı tam okuyamadığı kanıtlanmış bir görev |
| **Frontend dosya bölme** (9.118 satır) | Aynı gerekçe; 2.000 satırı aşan üretim dosyası yok. Ayrıca ön koşulu L bir test fazı — planın en pahalı kalemi | Aynı |
| **Frontend sayfa karakterizasyon testleri** | Tek müşterisi yukarıdaki iki kalem | Bölme yeniden açılırsa |
| **Tip/kısıt hijyeni** (CHECK, enum, TEXT→JSONB) | 14.345 satırlık, ~38 belge/ay kullanılan sistemde canlı veri üzerinde yüksek riskli, kullanıcı değeri ~0 | Veri bütünlüğü arızası görülürse |
| **Alembic'e geçiş** | §6.1 mevcut `("index", …)` op türünün yettiğini kanıtladı | Şema değişim hızı artarsa |

**FAZ 6'dan kurtarılan iki madde** (FAZ 0/A'ya taşındı): dava açma mantığının üç kopyasının
tekilleştirilmesi (0.5'in kök nedeni) ve rota bazlı lazy-loading (A.1'in yanında).

---

## 10. Denetim düzeltmeleri — taslakta neyi yanlış yazmıştım

| # | Taslak iddiası | Gerçek |
| --- | --- | --- |
| 1 | "Her sayı canlı sistemden ölçüldü" | **Lokal restore kopyası.** Prod'a tek okuma yapılmadı |
| 2 | "UNION → 6,9 ms, 18× kazanç" | Tekrar üretilemedi. **4,0×** (tek terim ≥3 karakter), **1,27×** (2 karakter) |
| 3 | "`count()` sonucu atılıyor, kaldır" | Liste yolunda **atılmıyor** — `X-Total-Count` sayfalamayı besliyor. Genel uygulanırsa sayfalama bozulur |
| 4 | "`config_manager` setter'ları ölü" | **Canlı** — 8'i `getattr` ile çağrılıyor |
| 5 | "`.dockerignore` → imaj %92 küçülür, sızıntı kapanır" | Prod imajında bu dosyalar **zaten yok** (build context git klonu). Gerçek sorun: veri **geliştirme makinesinde OneDrive senkronunda** |
| 6 | "`split_part(tracking_no,'.',5)` ile backfill" | Çürüdü — 12.013 satırda boş |
| 7 | "FAZ 2 ve FAZ 3 paralel yürüyebilir" | **İkisi de backend bandı**; runner bant başına tek slot verir |
| 8 | "LogManager'ı sil" | Yalnız `class LogManager`; aynı dosyadaki `TechnicalLogger` 20+ modülde canlı |
| 9 | "Bölme gerekçesi: parçalı okuma = kaçırılan bağlam" | 2.000 satırı aşan üretim dosyası yok → gerekçe ölçülmedi (§9) |
| 10 | SSRF, bağımlılık açıkları, hukukbot, süreç belleği, aktarım yazma yolu | Taslakta **hiç yoktu** |

**Çürütülen denetim iddiaları (plana girmedi):** *(a)* "Önce toplu yaz, sonra index kur" —
FAZ D net **−23** index, yani yazmayı ucuzlatıyor; ayrıca UNIQUE düşürme tuzağını geri açardı.
*(b)* "Negatif satır deltası kuralı oyunlanabilir/uygulanamaz" — kural yalnız **silme görevi**
tipine bağlı, her faza değil.

---

## 11. Yürütme yöntemi: "insan gibi değil, AI gibi"

| İnsan çağı varsayımı | AI çağı gerçeği |
| --- | --- |
| PR küçük olsun, review kapasitesi sınırlı | Sınır insan **onay noktası**, kod hacmi değil |
| Refactoring pahalı (insan zamanı pahalı) | Mekanik dönüşüm ucuz; pahalı olan **doğrulama** |
| Denetim örnekleme ile yapılır | Denetim **tam kapsam** olabilir — bu planın kendisi öyle üretildi ve kendi 10 hatasını buldu |
| Ölçüm zahmetli, tahmin edilir | Ölçüm ucuz → **tahmin yasak** |

**İlkeler:**

1. **Silme birinci sınıf iş tipi.** Kullanıcının teşhisi doğru: model ekleyici. Bunu model
   değiştirerek değil **süreçle** düzeltiriz. Silme görevlerinde net satır deltası negatif
   olmak zorunda; denetçi ölçer.
   **Ön koşul (davranışsız, FAZ B.0):** `gorev/<id>.md` şablonuna zorunlu **"Beklenen silme"**
   alanı (silinecek dosya + test sayısı, önceden beyan) ve `gorev-denetle` skill'inde
   "test sayısı düştü" kuralının **"beyan edilmeyen test kaybı"** olarak daraltılması.
2. **Doğrulama = derleyici.** Doğrulanmamış bulgu plana girmez. Taşıma görevleri için ucuz
   mekanizma: `git show -M --find-renames` altında ≥%90 rename + `--color-moved`.
3. **Ölçüm panosu — sahibi belli.** `otomasyon/` altında koşan bir script; her kuyruk koşusunun
   sonunda `docs/` altındaki tek bir dosyaya yazar: toplam satır, en büyük 10 dosya, ölü kod
   adayı, kapsam, silme oranı, `idx_scan=0` index sayısı. Bayatlarsa koşu logunda uyarı.
   Kullanıcının endişesi böylece kalıcı olarak **görünür** olur.
4. **Karakterizasyon testi = AI'ın en verimli işi.** Ama yalnız **müşterisi olan** yerde
   (bkz. §9 — sahipsiz test fazı yazmıyoruz).
5. **Sınır kararı insana, mekanik dönüşüm ajana.**

**Bant gerçeği (düzeltildi):** `gorevler/README.md` kuralı 4 — backend bandında paralellik yok.
FAZ A/C/D/E'nin ağırlığı backend. Gerçek paralellik yalnız frontend dilimlerinden gelir
(ölü `ui/` bileşenleri, `sidebar.tsx` kaskadı, `CaseGroup.tsx`). Altyapı dosyaları
(`nginx.conf`, `docker-compose*.yml`, `Dockerfile`) **backend bandı sayılır** — doğrulaması
ayakta stack gerektirir; bu kural `gorevler/README.md`'ye eklenmeli.

---

## 12. Program

**Bağımlılık grafiği** (genel "pazarlıksız sıra" yerine):

```
FAZ 0 (arızalar) ─┬─> FAZ A (davranışsız kazanımlar)  [paralel, birbirini beklemez]
                  └─> FAZ B (emniyet ağı)
FAZ B.3/B.4 ──> FAZ D (DB)          FAZ B.5 ──> FAZ E (sorgu)
FAZ D + FAZ E ──> FAZ F (aktarım)
FAZ C (ölü kod) — bağımsız, herhangi bir noktada
```

**Kapasite:** gözlenen gece verimi 5–6 küçük görev (2026-08-11: üç koşuda 13 görev).
Görev tavanı 180 dk. Dükkân aynı sürede ~8 commit/gün üretmeye devam ediyor.

| Faz | Kalem | Tahmini gece | Deploy | İnsan onay noktası |
| --- | --- | --- | --- | --- |
| 0 | 6 arıza + service_type yazma | 2 | **Evet (öncelikli)** | 0.5 kategori kararı (ADR) |
| A | 6 hızlı kazanım | 1–2 | Evet *(0 ile aynı deploy)* | A.2 veri taşıma, A.6 sürüm kararı |
| B | Kapılar + karakterizasyon | 3–4 | Hayır (CI hariç) | — |
| C | ~3.600 satır ölü kod | 1–2 | Evet | — |
| D | Migrasyon + index | 2 | **Evet (dikkatli)** | Prod ölçümü (6.0) + UNIQUE mükerrer kontrolü |
| E | Sorgu algoritmaları | 2–3 | Evet *(D ile aynı deploy)* | party_check altın küme onayı |
| F | Aktarım yazma yolu | 3+ | Evet | Aktarım kararı |

**Toplam ≈ 14–18 gece, 4 prod deploy'u** (7 değil — 0+A ve D+E paketlendi).

**Durma kriteri.** Her fazın sonunda: *hedeflenen ölçüm sağlandıysa kalan maddeler düşer.*
Örnek: FAZ A sonrası party_check 1 isim < 200 ms ise, FAZ E'nin party_check maddesi **silinir**.

**Kod dondurma.** FAZ D/E/F gecelerinde o gecenin dosyalarına gündüz özellik commit'i girmez.
Son 30 günün en sıcak dosyaları: `case_intake.py` (14), `case_manager.py` (14), `analyzer.py` (10).

**Doküman borcu.** Yaşayan dokümanlarda **156 satır-numaralı kod çıpası** var; FAZ D/E bunları
geçersizleştirir. Ayrıca `CLAUDE.md:77` bugün bayat (859 diyor; gerçek 868). Her fazın kabul
kriterine "dokunduğu dokümanı güncelle" maddesi girer.

**Deploy gerektiren her faz** için kabul kriteri: **export duman testi** (bir belge → outbox
pending → webhook/reconcile). Hukukbot bu backend'e bağlı ikinci canlı sistemdir ve taslakta
sıfır kez geçiyordu.

---

## 13. Kaynak

İki turlu çok ajanlı üretim (2026-08-11): keşif 14 ajan / 1,84 M token / 25 dk / 70 bulgu
(1 çürütüldü, 22 düzeltildi); denetim paneli 11 ajan / 1,32 M token / 42 dk / 48 bulgu
(2 çürütüldü, 18 düzeltildi). Toplam 25 ajan, ~3,2 M token.
