# Raporlama modülü planı — kullanıcı tanımlı listeler, favori şablonlar, indirme logu, AI asistan

**Tarih:** 06.09.2026 · **Karar:** kullanıcı (06.09 sohbeti) · **Durum:** **uygulandı — G130-G135**
(2026-09-06 gece koşusu, main'de; deploy edilmedi), dokümante G136 (`docs/mimari/raporlama.md`).
**İkinci tur (§4, 07.09 kullanıcı kararı): uygulandı — G137-G139** (2026-09-07 gece, main'de; deploy
edilmedi), dokümante G140 (`raporlama.md` ikinci tur; durum/kanıt §4.5).
**Kapsam kararları (kullanıcı):** test aşamasında yalnız yöneticiler (`require_admin`); çıktı Excel + CSV;
her indirme "kim, ne zaman, ne" ile loglanır ve çıktının kendisi sistemde saklanır; aynı ekranda AI sohbet
asistanı doğal dille rapor tanımı üretir (manuel yol her zaman açık kalır).

> **Bu dosya sözleşme kaynağıdır.** G130-G136 görevleri aşağıdaki JSON şemalarına ve uç adlarına birebir
> uyar; bir görev sözleşmeyi değiştirmek zorunda kalırsa ÖNCE burayı günceller ve raporunda yazar.
> Sayılar/yollar koddan doğrulanır (ALTIN KURAL, `CLAUDE.md`).

## 0. Durum ve kanıt (G136 şerhi, 2026-09-06)

Altı görev de TAMAM ve main'de; yaşayan doküman `docs/mimari/raporlama.md` (koddan doğrulanmış uç/env/
tablo/limit referansları). Kod ile bu sözleşme arasındaki farklar aşağıda §2'nin ilgili yerlerine
"**Uygulamada değişti**" şerhiyle işlenmiştir; dış sözleşme (uç adları, gövdeler, olaylar) değişmedi,
farklar ek alan/ek sınır/ek index türündedir.

| Kabul kriteri (plan) | Nasıl kanıtlandı (test dosyası; işçi raporları G130-G135) |
| --- | --- |
| K1 serbest SQL yok; bilinmeyen anahtar/op/tip 422 | `backend/tests/test_g130_rapor_temeli.py` (422 yolları, `contains` kaçışı, istemci string'i derlenmiş SQL'e girmez — bağlı parametre) |
| K2 tenant + soft-delete dört kaynakta | `test_g130_rapor_temeli.py` (başka tenant / `deleted_at` dolu satır listelenmez, 4 kaynak); `test_g131_rapor_export_ve_log.py` (export + `/runs` + download tenant kısıtı) |
| K3 akışlı export, bellek | `test_g131_rapor_export_ve_log.py` (export `satirlari_akit` iteratörünü tüketir; `write_only`); G131 raporu ölçümü: 50.000 satır xlsx tepe 8,4 MB / csv 2,1 MB (tracemalloc) |
| K4 yalnız export loglanır; sha256 = indirilen = saklanan; 410 | `test_g131_rapor_export_ve_log.py` (önizleme koşu yazmaz; koşu satırının tüm alanları; sha256 eşitliği; temizlik + 410 + `dosya_mevcut=false`; hata yolunda satır kalır) |
| K5 şablonlar DB'de, sahiplik 403, paylaşım | `test_g131_rapor_export_ve_log.py` (CRUD + 403 + paylaşımlı görünürlük); `frontend/src/pages/ReportsPage.sablon.test.tsx`, `frontend/src/lib/reports.export.test.ts` |
| K6 asistan tanımı aynı doğrulamadan geçer; geçersiz tanım istemciye gitmez; DB'ye dokunmaz | `backend/tests/test_g132_rapor_asistani.py` (katalog dışı kolon → `warning` + `tanim=null`; 8 doğrulama yolu; `SessionLocal`/`client.aio` yok bekçileri) |
| K7 indirme yalnız `/export`, `kaynak:"asistan"` | `frontend/src/pages/ReportsPage.asistan.test.tsx` (`indir_xlsx` → export gövdesi `kaynak:"asistan"`); `test_g131_rapor_export_ve_log.py` (`kaynak=asistan` koşu satırı) |
| K8 anahtar varsayılan kapalı; 409; panel gizli | `test_g132_rapor_asistani.py` (varsayılan, admin settings listesi, 409 gövde ayrıştırılmadan); `ReportsPage.asistan.test.tsx` (anahtar kapalı → düğme/panel yok, manuel akış çalışır) |
| K9 model env'i + intake fallback | `test_g132_rapor_asistani.py` (`get_rapor_model` üç kademe) |
| K10 index ölçülmeden yazılmaz; kısıt `("index",...)` op'unda | `test_g131_rapor_export_ve_log.py` (migrasyon kuralı bekçisi: modelde index yok, FK op'u `IF NOT EXISTS`, `("table",...)` yok); FK istisnası `test_g043_index_ve_avukat_filtresi.py::test_index_siz_fk_kolonu_kalmadi` |
| §2.6 akış sözleşmesi; `complete`/`failed` son olay; log sözleşmesi | `test_g132_rapor_asistani.py` (5 Gemini hatası → doğru `error_kod` + TEK ERROR `caplog`); `frontend/src/lib/reportsChat.test.ts` (NDJSON okuyucu, son olay, tanınmayan etiket → `analysis_error`) |
| §2.4 gövdeler birebir (frontend) | `frontend/src/pages/ReportsPage.test.tsx`, `frontend/src/lib/reports.test.ts` (önizleme gövdesi, tip↔op tablosu, `between`/`in` biçimi) |

Koşu sonuçları (işçi raporları): backend `pytest` 2637 passed / 3 skipped (G132 sonrası), ruff + mypy temiz;
frontend `vitest` 728 passed / 60 dosya (G135 sonrası), eslint 0 uyarı, `tsc -b --force` exit 0.
Gerçek Gemini duman testi 07.09'da lokalde YAPILDI (`models/gemini-3.6-flash`, servis katmanından, 8 istem):
3 örnek istem + takip mesajları + belirsizlik + katalog dışı alan + para/eşanlam senaryoları beklendiği gibi;
tek bulgu "davaları listele" için `tanim=null` + `eylem=onizle` + yanıltıcı mesaj → sunucu koruması (tanım
yoksa eylem düşer) + prompt kuralı daraltıldı (kaynak belliyse varsayılan tanım, soru yalnız zorunlu bilgi
eksikse); ayrıntı G132.md raporu "Duman testi" bölümü. Üretilen tanımlar lokal DB'de koşuldu (358 dava, 206
müvekkil). G134'ün nginx arkasında HTTP duman testi hâlâ insan adımı (giriş gerekir).

---

## 1. Tasarım kararları (planlayıcı, keşfe dayalı)

| # | Karar | Gerekçe |
| --- | --- | --- |
| K1 | **Serbest SQL YOK.** İstemci (ve LLM) yalnız *kayıt defterinde* (registry) tanımlı veri kaynağı + kolon + filtre anahtarları gönderir; sorgu sunucuda SQLAlchemy Core ile kurulur. | `SETTINGS_REGISTRY` / `LIST_REGISTRY` deseni (`services/app_settings.py`, `managers/reference_list_export.py`); SQL enjeksiyonu ve tenant/soft-delete sızıntısı sınıfı kapanır. |
| K2 | Tenant + soft-delete filtresi tek yerden: `auth_helpers.tenant_filter_clause` + `deleted_at IS NULL`; `cases` dışı tablolar `cases` JOIN'iyle. Silinmiş kayıtlar rapora GİRMEZ. | `case_manager._apply_tenant_filter` (`managers/case_manager.py:264`) ile aynı kural. |
| K3 | Excel/CSV **backend'de** üretilir (openpyxl 3.1.5 mevcut; frontend'de xlsx kütüphanesi yok, eklenmez). Excel `write_only` modda, sorgu `yield_per` ile akar. CSV: `utf-8-sig` + `;` (mevcut desen `services/teslim_cevap.py::_csv_yaz`). | Bellek disiplini (backend 2g limit, OOM dersleri); Türkçe Excel doğrudan açar. |
| K4 | **Yalnız export loglanır**, önizleme loglanmaz. Log satırı = tanım anlık görüntüsü + kullanıcı + zaman + satır sayısı + dosya adı/boyut/sha256 + kaynak (`manuel`/`asistan`). Dosya `RAPOR_CIKTI_DIZINI` altında saklanır, `RAPOR_CIKTI_SAKLAMA_GUN` (varsayılan 30) sonra her export'ta tembel temizlik. | Kullanıcı isteği "alınan çıktı + kim/ne zaman"; önizleme logu tabloyu şişirir. |
| K5 | Favori şablonlar DB'de (`report_templates`), sahibi + `paylasimli` bayrağı; test aşamasında tüm yöneticiler birbirinin paylaşımlı şablonunu görür. localStorage KULLANILMAZ. | Kullanıcılar arası paylaşım; çıkışta `clearAppStorage()` silerdi. |
| K6 | AI asistan **DB'ye dokunmaz**: Gemini'den JSON şemalı tek-atış cevap (`RaporAsistanCevabi`), içindeki `tanim` sunucuda aynı Pydantic + registry doğrulamasından geçer; geçmezse `tanim=null` + uyarı. Sohbet geçmişi sunucuda SAKLANMAZ (istemci `mesajlar` listesini taşır, son 20). | Tek factory `gemini_client.get_client` + `analyzer._gemini_call_with_retry`; repo'da multi-turn yok, yeni desen minimal tutuldu. |
| K7 | Asistan çıktı almak istediğinde `eylem` döner (`onizle` / `indir_xlsx` / `indir_csv`); **indirme yine frontend'in `/export` çağrısıyla** olur (`kaynak: "asistan"`). | Tek indirme yolu → tek log yolu. |
| K8 | Admin anahtarı `rapor_asistani` (`SETTINGS_REGISTRY`, varsayılan **KAPALI**). Kapalıyken `/chat` 409 döner, panel gizlenir; manuel rapor anahtardan bağımsız çalışır. | Repo kültürü: Gemini maliyetli özellikler varsayılan kapalı (`client_notice_enabled`, `veri_teslim_otomasyonu`). **Kullanıcı isterse varsayılan AÇIK yapılır — tek satır.** |
| K9 | Ayrı model env'i `GEMINI_RAPOR_MODEL` (varsayılan `GEMINI_INTAKE_MODEL` ile aynı) — devre kesici model-başına. | `case_intake_analyzer.get_intake_model` deseni. |
| K10 | Yeni index'ler ölçülmeden yazılmaz (G042 kuralı). `report_runs(requested_at)` ve `report_templates(owner_email)` için de: tablo sıfır dolulukla doğuyor, **index YOK**; ihtiyaç ölçülünce eklenir. Kısıtlar `("index", ...)` op'unda (G041). | `database.py:126-141` şerhi. |

Kapsam DIŞI (bilinçli): PDF çıktı, grafik/dashboard, zamanlanmış rapor e-postası, yönetici olmayan roller,
sohbet geçmişinin DB'de saklanması, LLM'in SQL üretmesi. Bunlar ölçülen kullanım sonrası ayrı plan.

---

## 2. Dondurulmuş sözleşme

### 2.1 Rapor tanımı (`RaporTanimi`, Pydantic — `backend/schemas_rapor.py`)

```json
{
  "veri_kaynagi": "davalar",
  "kolonlar": ["tracking_no", "subject", "responsible_lawyer_name", "opening_date"],
  "filtreler": [
    {"alan": "status", "op": "in", "deger": ["Derdest", "Karar"]},
    {"alan": "opening_date", "op": "between", "deger": ["2025-01-01", "2025-12-31"]},
    {"alan": "karar_tarihi", "op": "is_null"}
  ],
  "siralama": [{"alan": "opening_date", "yon": "desc"}]
}
```

Kurallar: `kolonlar` sıralıdır, en az 1, en fazla 60, tekrarsız; her anahtar veri kaynağının kataloğunda olmalı.
`filtreler` en fazla 20; `op` alan tipine göre izinli listeden (aşağıda); `in` en fazla 200 değer;
`contains` ILIKE, `%`/`_` kaçışlı. `siralama` en fazla 3. Bilinmeyen anahtar/op/tip → **422** (`detail` içinde
`alan`, `sebep`). Bu aynı doğrulama asistanın ürettiği tanıma da uygulanır (K6).

### 2.2 Kolon tipleri ve izinli operatörler

| tip | op'lar | `deger` biçimi |
| --- | --- | --- |
| `metin` | eq, ne, contains, in, is_null, not_null | str / list[str] |
| `liste` (kapalı liste, `secenekler` dolu) | eq, ne, in, is_null, not_null | str / list[str] |
| `tarih` | eq, gte, lte, between, is_null, not_null | ISO `YYYY-MM-DD` / [başlangıç, bitiş] |
| `sayi`, `para` | eq, gte, lte, between, is_null, not_null | number / [min, max] |
| `mantik` | eq, is_null | bool |

Türetilmiş kolonlar (`turetilmis: true`) filtrelenemez ve sıralanamaz (v1); katalog bunu `filtrelenebilir=false` ile bildirir.

> **Uygulamada değişti / netleşti (G136):** `ne` operatörü NULL satırı da döndürür
> (`services/rapor/motor.py:198-201` — "durum ≠ X"te boş da farklıdır). DateTime kolonlarda tarih
> filtresi gün aralığıdır (`eq` = `[gün, gün+1)`, `motor.py:164-185`; gün sınırı DB saat dilimi, prod UTC).

### 2.3 Veri kaynakları (registry — `backend/services/rapor/registry.py`)

| anahtar | etiket | çekirdek tablo | JOIN / türetilmiş kolonlar (en az) |
| --- | --- | --- | --- |
| `davalar` | Davalar | `cases` (deleted_at IS NULL, tenant) | `muvekkil_adlari` (case_parties CLIENT, ` ; ` ile), `karsi_taraf_adlari` (COUNTER), `foy_sayisi`, `belge_sayisi` |
| `muvekkiller` | Müvekkiller | `clients` (deleted_at IS NULL, tenant) | `dava_sayisi` (case_parties.client_id → silinmemiş cases) |
| `belgeler` | Belgeler | `case_documents` (deleted_at IS NULL) JOIN `cases` (tenant) | `dava_tracking_no`, `dava_subject` |
| `foyler` | Föyler | `case_foys` JOIN `cases` (tenant, deleted_at IS NULL) | `dava_tracking_no`, `dava_subject`; `ham_veri` HARİÇ |

`davalar` için asgari kolon kümesi: `id, tracking_no, esas_no, status, file_type, sub_type, service_type, subject,
court, judicial_unit, opening_date, acceptance_date, responsible_lawyer_name, uyap_lawyer_name, bureau_type,
klasor_no_2, hasar_dosya_no, tku_no, sistem_no, case_stage, dosya_son_durumu, karar_tarihi, karar_turu,
karar_lehine, karar_no, kesinlesme_tarihi, maddi_tazminat, manevi_tazminat, hukmedilen_toplam, dava_degeri,
para_birimi, olay_turu, hukumdeki_rol, muvekkil_tipi, hizmet_turu, tibbi_surec, tibbi_olay, iddia_edilen_kusur,
active, missing_required_bucket, created_at, updated_at` + 4 türetilmiş. Kalan `cases` kolonları eklenebilir;
`tenant_id`, `deleted_*`, `notes` (serbest metin, PII) ve `ham_veri` **eklenmez**. Etiketler Türkçe, mevcut
UI etiketleriyle aynı (`CaseList`/`CaseDetails` başlıkları). Kapalı listeli kolonlar (`status`, `file_type`,
`olay_turu`, `hizmet_turu`, `muvekkil_tipi`, `para_birimi`, `karar_lehine`, `missing_required_bucket`,
`link_mode`, `stage`...) `liste` tipinde ve `secenekler` katalogda dolu (seed sabitleri/DISTINCT).
Türetilmiş metin birleştirmeleri **`func.aggregate_strings`** ile (SQLAlchemy 2.0.25; testler sqlite koşar).

> **Uygulamada değişti (G136):** (a) katalog dışı liste genişledi — `clients.tc_no`, `source_ids`, belge
> `email_error` / `conversion_spool_path` da dışarıda (`services/rapor/registry.py:17-19`, `:453`);
> (b) `belgeler`/`foyler` JOIN kolonları `dava_tracking_no`/`dava_subject` türetilmiş sayılır → filtrelenemez
> ve sıralanamaz (`registry.py:371-372`, `:416-417`); (c) davasız (`case_id IS NULL`) belge INNER JOIN
> nedeniyle rapora girmez; (d) koddan sayılan kolon adedi davalar 86 / müvekkiller 25 / belgeler 20 / föyler 18.

### 2.4 HTTP uçları (`backend/routes/reports.py`, hepsi `Depends(require_admin)` + `get_current_tenant`)

| Uç | Gövde / parametre | Cevap |
| --- | --- | --- |
| `GET /api/reports/catalog` | – | `{"veri_kaynaklari":[{"anahtar","etiket","aciklama","varsayilan_kolonlar":[...],"kolonlar":[{"anahtar","etiket","tip","filtrelenebilir","siralanabilir","turetilmis","secenekler":[...]∣null}]}], "limitler":{"onizleme_sayfa_boyu_max":200,"export_max_satir":<env>}}` |
| `POST /api/reports/preview` | `{"tanim": RaporTanimi, "sayfa": 1, "sayfa_boyu": 50}` (sayfa_boyu ≤ 200) | `{"kolonlar":[{"anahtar","etiket","tip"}], "satirlar":[{anahtar: değer}], "toplam": n, "sayfa", "sayfa_boyu"}` — tarih ISO, para/sayı JSON number, `null` boş |
| `POST /api/reports/export` | `{"tanim", "format":"xlsx"∣"csv", "sablon_id": int∣null, "kaynak":"manuel"∣"asistan"}` | dosya (`Content-Disposition: attachment; filename="hukdok-rapor-<kaynak>-<YYYYMMDD-HHMM>.xlsx"`), başlık `X-Rapor-Kosu-Id: <run id>`; satır > `RAPOR_MAX_SATIR` → 413 `{"detail":{"sebep":"satir_limiti","toplam":n,"limit":m}}` |
| `GET /api/reports/templates` | – | `[RaporSablonu]` (kendi + paylaşımlılar; silinmişler hariç) |
| `POST /api/reports/templates` | `{"ad","aciklama","tanim","paylasimli"}` | `RaporSablonu` (201) |
| `PUT /api/reports/templates/{id}` | aynı gövde (kısmi değil, tam) | `RaporSablonu`; başkasının şablonu → 403 |
| `DELETE /api/reports/templates/{id}` | – | 204 (soft: `deleted_at`); başkasının → 403 |
| `GET /api/reports/runs?limit=50&offset=0` | – | `{"toplam": n, "kosular":[RaporKosusu]}` (tüm yöneticilerin koşuları, yeni→eski) |
| `GET /api/reports/runs/{id}/download` | – | saklanan dosya (`FileResponse`, path-traversal savunmalı — `routes/admin.py:277-308` deseni); dosya temizlenmişse 410 |
| `POST /api/reports/chat` | `{"mesajlar":[{"rol":"user"∣"assistant","icerik":str}], "mevcut_tanim": RaporTanimi∣null}` | NDJSON akışı (§2.6); anahtar kapalıysa **409** `{"detail":"rapor_asistani kapalı"}` |

`RaporSablonu`: `{"id","ad","aciklama","tanim","olusturan","paylasimli","created_at","updated_at"}`.
`RaporKosusu`: `{"id","sablon_id","sablon_adi","format","kaynak","veri_kaynagi","kolon_sayisi","satir_sayisi",
"kullanici","baslangic","sure_ms","dosya_adi","dosya_boyutu","sha256","dosya_mevcut","tanim"}`.

> **Uygulamada değişti (G136):** (a) `RaporKosusu`ya ek alan `hata: str|null` (`schemas_rapor.py:179`; üretim
> hatası özeti, istemci yok sayabilir); (b) `/runs` `limit` tavanı 200 (`routes/reports.py:61`, `:322`);
> (c) `/export`: `sablon_id` bulunamazsa 404 (`:255-256`), üretim hatası 500 `"Rapor üretilemedi"` + koşu satırı
> `hata` ile kalır (`:275-285`), 413'te koşu satırı YAZILMAZ; (d) `/chat` gövde sınırları: mesaj ≤20, içerik
> ≤4000 karakter, son mesaj `user` → 422 (`schemas_rapor.py:206-233`); (e) 422 gövdesi HER zaman
> `{"detail": {"alan", "sebep"}}` (yapısal Pydantic hataları dahil — route gövdeyi elle doğrular).

### 2.5 Tablolar (`models.py` + `database.py::_MIGRATIONS`)

```sql
CREATE TABLE report_templates (
  id SERIAL PRIMARY KEY, ad VARCHAR(120) NOT NULL, aciklama VARCHAR(500),
  tanim JSON NOT NULL, olusturan VARCHAR(255) NOT NULL, paylasimli BOOLEAN NOT NULL DEFAULT FALSE,
  tenant_id VARCHAR(64), created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),
  deleted_at TIMESTAMPTZ, deleted_by VARCHAR(255));
CREATE TABLE report_runs (
  id SERIAL PRIMARY KEY, sablon_id INTEGER REFERENCES report_templates(id) ON DELETE SET NULL,
  tanim JSON NOT NULL, format VARCHAR(8) NOT NULL, kaynak VARCHAR(16) NOT NULL DEFAULT 'manuel',
  veri_kaynagi VARCHAR(32) NOT NULL, kolon_sayisi INTEGER NOT NULL, satir_sayisi INTEGER NOT NULL,
  kullanici VARCHAR(255) NOT NULL, tenant_id VARCHAR(64), baslangic TIMESTAMPTZ NOT NULL DEFAULT now(),
  sure_ms INTEGER, dosya_adi VARCHAR(255) NOT NULL, dosya_yolu VARCHAR(500), dosya_boyutu INTEGER,
  sha256 VARCHAR(64), hata VARCHAR(500));
```

Modelde tanımlı olacakları için `("table", ...)` op'u ölü koddur (G041): migrasyona **yalnız** gerekirse
`("index", ...)` op'u yazılır; K10 gereği v1'de index yok → migrasyon kaydı sadece `create_all` + docstring şerhi.
`tenant_id` yazılır (gelecek ayrım için), okuma `tenant_filter_clause` ile.

> **Uygulamada değişti (G136):** K10'un TEK istisnası `idx_report_runs_sablon ON report_runs (sablon_id)`
> (`database.py:1062-1064`, koşulsuz `("index", ...)` op'u, `IF NOT EXISTS`): G043 bekçisi
> `test_index_siz_fk_kolonu_kalmadi` index'siz FK'yı yapısal olarak yasaklar — ölçüm sorusu değil, FK kuralı.
> `baslangic`/`olusturan` için index yok (K10 korunur). `format` CHECK'i DB'de değil Pydantic `Literal`'da.

### 2.6 Asistan akış sözleşmesi (`/api/reports/chat`, NDJSON — `analyzer._failed_event` ile uyumlu)

```
{"status":"info","message":"Rapor tanımı hazırlanıyor"}
{"status":"warning","message":"..."}                       # ör. tanım doğrulanamadı, tanım=null ile devam
{"status":"complete","cevap":"<asistanın Türkçe metni>","tanim":RaporTanimi|null,"eylem":"onizle"|"indir_xlsx"|"indir_csv"|null}
{"status":"failed","error_ozet":"...","error_kod":"gemini_saturated|gemini_blocked|gemini_truncated|schema_invalid|analysis_error"}
```

`complete` ve `failed` SON olaydır. Gemini yanıt şeması `RaporAsistanCevabi {cevap: str, tanim: RaporTanimi|None,
eylem: Literal[...]|None}`. Sistem talimatı (`prompts.py::get_rapor_asistani_instruction`) kataloğu kompakt
biçimde (anahtar · etiket · tip · seçenekler) gömer; kurallar: yalnız katalog anahtarları, belirsizse SORU sor
(`tanim=null`), `mevcut_tanim` verildiyse onu değiştirerek üret, veri döndürme (asistan satır görmez).
Log sözleşmesi: denemeler WARNING, nihai TEK ERROR.

> **Uygulamada değişti (G136):** Gemini `response_schema`'sındaki `tanim` `RaporTanimi` DEĞİL, ayrı
> `AsistanTanimi`dir (`schemas_rapor.py:188-204`, `:236-264`): `RaporTanimi`nin `extra="forbid"`i
> `additionalProperties:false` üretir (google-genai 2.11.0 Developer API modunda desteklenmez) ve
> `Filtre.deger: Any` tipsiz özellik olur. Asistan filtre değeri metin (`deger`) ya da metin listesi
> (`degerler`, `in`/`between`) taşır; sunucu kolon tipine göre çevirir ve **aynı** `RaporTanimi` +
> `motor.tanimi_dogrula` yolundan geçirir (K6). İstemciye giden `complete.tanim` yine `RaporTanimi`
> (`SohbetTamamlandi`, `:267-273`) — dış sözleşme değişmedi. Geçersiz tanımda `eylem` de `null`a düşer.
> Ek olay: route'un beklenmedik istisnası `{"status":"error","message"}` (sözleşme dışı, `/process` deseni).
> Baştaki asistan mesajları `contents`'e alınmaz (Gemini dizisi kullanıcıyla başlar).

### 2.7 Env (`.env.example`'a eklenir)

```
# Raporlama modülü (G131/G132)
# RAPOR_MAX_SATIR=50000            # export satır tavanı; aşınca 413
# RAPOR_CIKTI_DIZINI=/app/data/rapor_ciktilari
# RAPOR_CIKTI_SAKLAMA_GUN=30
# GEMINI_RAPOR_MODEL=models/gemini-3.6-flash   # yoksa GEMINI_INTAKE_MODEL
```

> **Teyit (G136):** dördü de `.env.example`'da şerhli ve yorumlu (`:55`, `:59`, `:62`, `:66`; blok `:49-66`);
> `config/settings.py:100-112` varsayılanları aynı. Bilinen sınır: `RAPOR_MAX_SATIR`ı iki okuyucu okur —
> export tavanı `settings.rapor_max_satir` (boot'ta donar), katalogdaki `export_max_satir` `motor.limitler()`
> `os.getenv` (her çağrı); prod'da aynı değer, fark test zamanı. Tek kaynağa indirmek bekleyen tek satır.

---

## 3. Görev grafiği

```
backend (seri, ana dizin):   G130 ──► G131 ──► G132
                              │                    │
frontend (worktree):         G133 ──► G134 ──► G135
                              (G130 ile PARALEL;      │
                               sözleşme burada dondu)  ▼
docs (worktree):                                     G136 (G132 + G135 sonrası)
```

| Görev | Bant | Bağımlı | İçerik |
| --- | --- | --- | --- |
| G130 | backend | – | Registry + RaporTanimi şeması + sorgu motoru + `/catalog` + `/preview` + route kaydı |
| G131 | backend | G130 | İki tablo + şablon CRUD + `/export` (xlsx/csv, akışlı) + koşu logu + saklama/temizlik + `/runs` |
| G132 | backend | G131 | Asistan: prompt + Gemini JSON şema + `/chat` NDJSON + `rapor_asistani` anahtarı + env |
| G133 | frontend | – | İskelet: route + Sidebar + `api.ts` timeout + `lib/reports.ts` tipleri + Rapor Oluşturucu (kaynak/kolon/filtre/sıralama) + önizleme tablosu |
| G134 | frontend | G133 | Şablonlar (kaydet/yükle/sil/paylaş) + Excel/CSV indirme + "İndirme geçmişi" sekmesi + eski çıktıyı indir |
| G135 | frontend | G134 | Asistan paneli: NDJSON okuyucu, mesaj listesi, tanımı oluşturucuya uygula, `eylem` yürütme, anahtar kapalıyken gizle |
| G136 | docs | G132,G135 | `docs/mimari/raporlama.md`, CLAUDE.md paragrafı, admin anahtar dokümanı, `.env.example` teyidi |

Tahmin: backend zinciri 3 oturum, frontend zinciri 3 oturum paralel → **2 gece** (1. gece G130-G131 ∥ G133-G134;
2. gece G132 ∥ G135, ardından G136). Riskler: (r1) G133 sözleşmeye göre yazılır, G130 sözleşmeyi bozarsa G134
öncesi uyum düzeltmesi gerekir; (r2) `App.tsx`/`Sidebar.tsx`/`api.ts` hub dosyalarına yalnız G133 dokunur;
(r3) asistan kalitesi ancak gerçek Gemini ile ölçülür — gece testleri sahte istemciyle geçer, gündüz duman testi şart.

---

## 4. İkinci tur — kullanılabilirlik yeniden tasarımı (2026-09-07, kullanıcı kararı; G137-G140)

> **Durum (G140 şerhi, 2026-09-07): uygulandı — G137 (backend), G138 + G139 (frontend), main'de; deploy
> edilmedi.** Aşağıdaki maddelerde kod ile plan arasındaki farklar "**Uygulamada değişti**" şerhiyle
> yerinde işaretlidir; aynı farklar `docs/mimari/raporlama.md` §12 tablosunda F11-F22 olarak, kabul
> kriteri → test dosyası kanıtı §4.5'te. Sunucu sözleşmesi (§2) DEĞİŞMEDİ — §4.2 katalog eki, §4.3 sunum katmanıdır.

**Kullanıcı bulgusu (07.09 gece, lokal kullanım + ekran görüntüsü):** "filtre seçilebiliyorsa bile nasıl
yapılacağını anlamadım; çok yazı var; çok sütun olduğu için karışık; kategorilerin içinden filtreleme yapılmıyor;
tarih filtresini göremedim." Ekranda: kaynak Müvekkiller seçiliyken tablo hâlâ dava satırlarını gösteriyor
(bayat önizleme), Filtreler bölümü ekranın altında görünmüyor, kolon listesi tip rozetleriyle dolu, filtre
üç adım (alan → operatör → değer) ve alan listesi 80+ öğeli düz `<select>`. Planlayıcı teşhisi: v1 bir
"sorgu kurucu"ydu; hedef kitle (yönetici/avukat) için **"süz ve gör"** arayüzü gerekir.

### 4.1 Hedef ekran (Rapor sekmesi)

1. **Kaynak seçimi** üstte dört kart (Davalar · Müvekkiller · Belgeler · Föyler, tek satır açıklama). Kaynak
   değişince taslak o kaynağın varsayılan kolonlarına döner ve önizleme HEMEN yenilenir — ekranda hiçbir zaman
   başka kaynağın satırı kalmaz.
2. **Filtre şeridi** önizlemenin üstünde, kaynağa özel ve katalogdan gelir (`hizli_filtreler`). Kontroller
   tipe göre hazır: tarih aralığı (alan değiştirici + "bu yıl / geçen yıl / son 30 gün / son 12 ay" kısayolları),
   çoklu seçim (kapalı listeler: Durum, Kategori, Hizmet Türü… — checkbox'lı açılır, seçilenler çip),
   metin "içerir", sayı/para "en az – en çok", "boş olanlar" anahtarı. **Operatör açılır listesi YOK**: operatör
   kontrolden türetilir (§4.3). "+ Başka alan" → aranabilir ve GRUPLU alan seçici (cmdk `Command`, kurulu);
   seçilen alan şeride aynı türde bir kontrol olarak eklenir. Etkin filtreler çip olarak görünür, tek tıkla
   kalkar, "Temizle" hepsini siler.
   **Uygulamada değişti (G138):** etiket "Filtreleri temizle" (kolon panelindeki "Temizle" ile çakışmasın;
   `QuickFilters.tsx:103`); hızlı yuva × ile silinmez, boşa döner — yalnız "+ Başka alan" ile eklenen şeritten
   kalkar; cmdk bulanık skoru yerine düz alt-dize filtresi (`FieldPicker.tsx:11-15`).
3. **Kolonlar** ana ekranda liste olarak DURMAZ: "Kolonlar (8)" düğmesi bir yan panel (shadcn `Sheet`) açar —
   gruplu checkbox listesi (`grup`), üstte hazır setler (`kolon_setleri`: "Temel", "İletişim", "Karar takibi",
   "Tazminat"…), seçilenlerin sırası aynı panelde (mevcut dnd + ↑↓). Tip rozetleri (`abc/123/liste`) kalkar.
   **Uygulamada değişti (G139):** `Sheet` yeni npm paketi değil, `@radix-ui/react-dialog` üzerine yerel
   `components/ui/sheet.tsx`; kolon değişikliği panel AÇIKKEN anında önizlenir (kapanışta toplu değil);
   sayfa `max-w-[1600px]` tavanı kaldırıldı (tam genişlik kuralı). Tip yalnız satır `title` ipucunda — ipucu
   türetilmiş kolonda hâlâ "filtrelenemez" der (`ColumnPicker.tsx:285`, taraf kolonlarında yanlış; açık NOT).
4. **Sıralama** ayrı bölüm değil: tablo başlığına tık (artan/azalan/kaldır, en fazla 3, `siralanabilir` olanlar).
5. **Önizleme otomatik**: yapısal değişiklikte hemen, metin/sayı/tarih yazarken 600 ms gecikme ya da odak
   çıkışı; yalnız geçerli tanımda; yarış koruması mevcut (`reqIdRef`). "Önizleme bayat" rozeti KALKAR; yerine
   başlıkta "güncelleniyor…" durumu. Önizle düğmesi yalnız hata durumunda "Tekrar dene".
   **Uygulamada değişti (G138):** `useDebounce` kancası kullanılmadı — efekt + `gecikmeliRef`/`zamanlayiciRef`
   (`ReportsPage.tsx:271-298`), aynı sözleşme (600 ms, tek istek); geçersiz taslakta SON GEÇERLİ önizleme
   ekranda kalır + "taslak eksik" ipucu (boşa düşürülmez); şablon/asistan tanımı yüklenince dolu filtreler
   şeridin BAŞINA gelir (tanım sırası korunur — şablon eşitliği kapısı için şart).
6. **Açılış**: sayfa Davalar + varsayılan kolonlar + filtresiz listeyle DOLU açılır.
7. **Metin azaltma**: açıklamalar tooltip'e, Eyebrow başlıklar kısa, kaynak açıklaması kartta tek satır.
8. Şablon çubuğu, Excel/CSV düğmeleri, sekmeler, asistan paneli ve `eylem` yürütme davranışı korunur; asistanın
   uyguladığı tanım artık otomatik önizlenir.

### 4.2 Katalog sözleşmesi genişlemesi (G137 — DONDU; G138 buna göre PARALEL yazılır)

`KatalogKolon`'a ek alanlar: `"grup": str` (kaynağa göre sabit küme: Davalar → `Kimlik · Taraflar · Mahkeme ve
konu · Tarihler · Tutarlar · Karar ve aşama · Tıbbi · Aktarım · Sistem`; Müvekkiller → `Kimlik · İletişim ·
Vekalet · Sınıflandırma · Sistem`; Belgeler → `Belge · Dava · Yükleme · Sistem`; Föyler → `Kimlik · Sınıflandırma ·
Kapsam · Sistem`), `"kontrol": "tarih_araligi" | "coklu_secim" | "metin_icerir" | "sayi_araligi" | "mantik"`
(tipten türetilir: tarih→tarih_araligi, liste→coklu_secim, metin→metin_icerir, sayi/para→sayi_araligi,
mantik→mantik; filtrelenemeyen kolonda `null`).
`VeriKaynagi`'na ek: `"hizli_filtreler": [{"alan": str, "alternatifler": [str, ...]}]` (sıralı; `alternatifler`
yalnız tarih aralığı kontrolünde alan değiştirici — ör. Davalar: `opening_date` ↔ `karar_tarihi` ↔
`kesinlesme_tarihi` ↔ `created_at`), `"kolon_setleri": [{"ad": str, "kolonlar": [str, ...]}]`.
Hızlı filtre listeleri (planlayıcı; işçi etiketleri koddan alır):
- Davalar: `opening_date` (alternatifler yukarıda) · `status` · `responsible_lawyer_name` · `court` ·
  `muvekkil_adlari` · `muvekkil_kategorisi` · `hizmet_turu` · `maddi_tazminat`
- Müvekkiller: `category` · `il` · `client_type` · `dava_sayisi`
- Belgeler: `uploaded_at` · `belge_turu_adi` · `uploaded_by` · `link_mode`
- Föyler: `durum` · `hizmet_turu` · `muvekkil_tipi` · `kapsam_durumu`
Kolon setleri (Davalar): "Temel" (= varsayılan), "Karar takibi" (`tracking_no, esas_no, court, status, case_stage,
karar_tarihi, karar_turu, karar_lehine, kesinlesme_tarihi`), "Tazminat" (`tracking_no, muvekkil_adlari, court,
maddi_tazminat, manevi_tazminat, hukmedilen_toplam, dava_degeri, para_birimi`), "Taraflar" (`tracking_no,
muvekkil_adlari, karsi_taraf_adlari, sigortali_adlari, muvekkil_kategorisi, responsible_lawyer_name`);
Müvekkiller: "Temel", "İletişim" (`name, category, phone, mobile_phone, email, address, il`), "Vekalet"
(`name, vekalet_no, buro_vekalet_no, vekaletname_tarihi, gecerlilik_tarihi, noterlik`).

**Taraf bağlantılı filtreler (Davalar, K1/K2 korunarak):** türetilmiş kolon kuralı gevşer — `filtrelenebilir`
artık kolon bazında; bu kolonlar `siralanabilir=False` kalır, filtre EXISTS alt sorgusuyla (`case_parties`
→ `clients`), silinmiş müvekkil kartı ve tenant kuralı `cases` üzerinden:
| anahtar | etiket | tip | kaynak | op'lar |
| --- | --- | --- | --- | --- |
| `muvekkil_adlari` | Müvekkiller | metin | `case_parties.party_type='CLIENT'` adları | contains, is_null, not_null |
| `karsi_taraf_adlari` | Karşı Taraflar | metin | `party_type='COUNTER'` | contains, is_null, not_null |
| `sigortali_adlari` (YENİ) | Sigortalılar | metin | `role='Sigortalı'` (her party_type) | contains, is_null, not_null |
| `muvekkil_kategorisi` (YENİ) | Müvekkil Kategorisi | liste | CLIENT tarafların `clients.category` (DISTINCT + seed) | eq, in, is_null |
`contains` bu kolonlarda "herhangi bir taraf adı içerir" anlamındadır (EXISTS), birleştirilmiş metin üzerinde değil.
**Uygulamada değişti (G137):** Müvekkiller `dava_sayisi` de filtrelenebilir türetilmiş oldu (hızlı filtre listesinde;
COUNT alt sorgusu doğrudan karşılaştırılır, `_skaler_filtre`; `is_null` boş küme döner ama 422 yemez) —
`foy_sayisi`/`belge_sayisi` filtrelenemez kaldı. `muvekkil_kategorisi` seçim ifadesi DISTINCT değil ("Doktor ; Doktor"
görünebilir; sqlite `group_concat(DISTINCT x, ayraç)` yok; filtre EXISTS olduğundan doğruluk etkilenmez).
`gruplar` kaynağa ayrıca yazılmadı — grup sırası kolon sırasından okunur. Migrasyon yok.
**Metin alanlarında öneri listesi (kullanıcı bulgusu 07.09: "manuel elle girilirse çok sorun yaşanır"):**
`KatalogKolon.oneriler: [str, ...] | null` — kayıt defterinde `onerili=True` işaretli metin kolonlarının
DISTINCT değerleri (silinmemiş + tenant kuralı, boş hariç, en fazla 300, alfabetik; aşarsa ilk 300 ve
`oneri_kesik: true`). İşaretlenecekler: Davalar `responsible_lawyer_name, uyap_lawyer_name, court,
judicial_unit, sub_type, muvekkil_adlari, karsi_taraf_adlari, sigortali_adlari` (taraf adları için
`case_parties.name` DISTINCT, ilgili party_type/role); Müvekkiller `il, sektor, specialty, noterlik`;
Belgeler `uploaded_by, belge_turu_adi`; Föyler `hizmet_turu` zaten liste. Frontend `metin_icerir` kontrolü
öneri varsa combobox (yazdıkça daralan liste, seçince `contains` yerine `eq`; serbest yazım yine `contains`)
olur. Katalog cevabı süreç içi 60 sn önbelleklenir (DISTINCT sorguları her açılışta koşmasın).
Asistan prompt'u kataloğu otomatik gömdüğü için `kontrol`/`grup`/`hizli_filtreler`/`oneriler` prompt'a
GİRMEZ (gürültü; öneriler 300'e kadar değer); yalnız yeni kolonlar girer.
**Uygulamada değişti (G137):** "alfabetik" = `ORDER BY kolon` (DB collation, Türkçe locale değil); önbellek
worker BAŞINA (`UVICORN_WORKERS=2` → 60 sn içinde iki worker farklı fotoğraf verebilir), anahtar
`(SessionLocal, tenant_id)`, `time.monotonic` (`routes/reports.py:81-109`); env yok, sabit `KATALOG_ONBELLEK_SN`.
Combobox seçimi taraf kolonlarında `eq` ÜRETMEZ (`oplar`da yok) — §4.3 şerhi.

### 4.3 Kontrol → operatör eşlemesi (frontend, G138)

| kontrol | kullanıcı girdisi | üretilen filtre |
| --- | --- | --- |
| tarih_araligi | başlangıç + bitiş / yalnız biri / kısayol | `between` / `gte` / `lte` |
| coklu_secim | 1 seçim / n seçim | `eq` / `in` |
| metin_icerir | metin | `contains` |
| sayi_araligi | en az + en çok / yalnız biri | `between` / `gte` / `lte` |
| mantik | Evet/Hayır | `eq true/false` |
| (her kontrolde) "boş olanlar" anahtarı | — | `is_null` (değer girdisi kilitlenir) |
Gelişmiş op'lar (`ne`, `not_null`, tam `eq` metinde) çipin "…" menüsünden; §2.1 sözleşmesi ve sunucu doğrulaması
DEĞİŞMEZ — bu yalnız sunum katmanıdır.
**Uygulamada eklendi (07.09, G137 sonrası):** `KatalogKolon.oplar: [str]` — kolon başına izinli op listesi
(filtrelenemeyen kolonda `[]`). Taraf kolonlarında (`muvekkil_adlari`, `karsi_taraf_adlari`, `sigortali_adlari`)
`eq` YOK (yalnız `contains`/`is_null`/`not_null`; EXISTS "herhangi bir taraf içerir"). Frontend kuralı: combobox
seçimi `eq` kolonun `oplar`ında varsa `eq`, yoksa `contains` gönderir; "…" menüsü yalnız `oplar`daki op'ları
listeler. Kontrol türü yine `kontrol` alanından gelir. Şablon/asistan tanımı yüklenince filtreler aynı kontrollere geri
çözülür (op → kontrol; çözülemeyen op "gelişmiş" çipi olarak gösterilir, kaybolmaz).
**Uygulamada değişti (G138, G140 doğruladı):** tablo `lib/reports.ts:373-408` `kontroldenFiltre` ile birebir; gidiş-dönüş
`filtredenKontrol` (`:415-451`) — tek istisna tek değerli `in` → `eq` (eş anlamlı). "…" menüsü = kolonun `oplar`ı ∖
kontrolün doğal op'ları (`KONTROL_DOGAL_OPLARI`, `:454-466`); gelişmiş çip hızlı yuvayı ezmez (yuva boş kalır).

### 4.4 Görevler

| Görev | Bant | Bağımlı | İçerik |
| --- | --- | --- | --- |
| G137 | backend | – | Katalog genişlemesi (grup, kontrol, hizli_filtreler, kolon_setleri) + taraf bağlantılı 4 filtre (EXISTS) + testler |
| G138 | frontend | – (sözleşme §4.2'den) | Filtre şeridi + operatörsüz kontroller + gruplu alan seçici + otomatik önizleme + başlıktan sıralama + kaynak değişiminde anında yenileme |
| G139 | frontend | G138 | Kaynak kartları + Kolonlar yan paneli (gruplar, setler, sıra) + açılışta dolu liste + metin sadeleştirme + responsive + asistan/şablon uyumu |
| G140 | docs | G137,G139 | `docs/mimari/raporlama.md` + bu plan durum şerhi; koddan doğrulanmış |
Zincir: backend G137 tek; frontend G138→G139 (ikisi de `ReportsPage.tsx`); G140 en son. Hub dosyalara
(App.tsx/Sidebar.tsx/api.ts) DOKUNULMAZ. Tahmin: 1 gece.

### 4.5 Durum ve kanıt (G140 şerhi, 2026-09-07)

Dört görev de TAMAM ve main'de (G137 · G138 · G139 · G140). Kabul kriteri → kanıt (test dosyası; işçi
raporları G137-G139, koddan G140 doğruladı):

| Kabul kriteri (plan §4) | Nasıl kanıtlandı |
| --- | --- |
| §4.2 katalog her kolonda `grup` + `kontrol` + `oneriler` (+ `oplar`), her kaynakta `hizli_filtreler` + `kolon_setleri` | `backend/tests/test_g137_rapor_katalog_genisleme.py` (şekil; grup kapalı kümede, boş grup yok; kontrol↔tip eşlemesi; hızlı filtre + set listeleri plan §4.2 ile birebir); `test_g130_rapor_temeli.py::test_katalog_sekli` (anahtar kümeleri güncellendi) |
| §4.2 taraf filtreleri: `muvekkil_adlari contains` yalnız CLIENT tarafı, aynı adlı karşı taraf bulunmaz; `sigortali_adlari` rol bazlı; `muvekkil_kategorisi in` silinmiş müvekkil kartını saymaz | `test_g137_rapor_katalog_genisleme.py` (taraf filtreleri; `is_null`/`not_null`; ILIKE kaçışı + zehir string bağlı parametrede; `dava_sayisi` karşılaştırma) |
| §4.2 türetilmişte yalnız izinli op'lar, diğerleri 422 `{"alan","sebep"}`; sıralama 422 | `test_g137_rapor_katalog_genisleme.py` (izinsiz op 7 varyant; sıralama 422); `test_g130_rapor_temeli.py::test_422_turetilmis_filtrelenemez_siralanamaz` (`foy_sayisi` hâlâ filtrelenemez); `test_g132_rapor_asistani.py` (asistanın `muvekkil_adlari eq` tanımı → `warning` + `tanim=null`) |
| §4.2 öneriler tenant + soft-delete kurallı, ≤300, `oneri_kesik` | `test_g137_rapor_katalog_genisleme.py` (DISTINCT, boş hariç, tenant/soft-delete, 300 kesme + bayrak, `db=None`) |
| §4.2 katalog önbelleği 60 sn — ikinci çağrı DISTINCT sorgusu koşturmaz | `test_g137_rapor_katalog_genisleme.py` (monotonic monkeypatch + sorgu sayacı; veri değişimi 60 sn gizlenir) |
| §4.2 asistan katalog metni öneri/hızlı filtre alanlarını içermez | `test_g137_rapor_katalog_genisleme.py` (300+ değerle metin uzunluğu sabit, `hizli_filtreler` kelimesi yok) |
| §4.2 migrasyon yok; ruff + mypy temiz | G137 raporu: `pytest` 2670 passed / 3 skipped, ruff + mypy temiz; `models.py`/`database.py` diff'te yok |
| §4.3 kontrol → op tablosu; "boş olanlar" → `is_null`; gelişmiş op'lar "…" menüsünden; yüklemede geri çözme | `frontend/src/lib/reports.test.ts` (kontrol başına op, 22 örnekli gidiş-dönüş, `gelismisOplar`, kısayollar, `tanimGecerliMi` taraf kolonu kapısı); `components/reports/builderState.test.ts` (tanımdan çözme, sıra korunur, gelişmiş çip yuvayı ezmez); `QuickFilters.test.tsx` |
| §4.1 madde 1 kaynak kartları; kaynak değişince eski satırlar ANINDA düşer | `components/reports/SourceCards.test.tsx`; `pages/ReportsPage.test.tsx` (kart tıklaması, aynı kart istek üretmez, cevap gelmeden eski satırlar kaybolur, şerit yeni kaynağın hızlı filtreleri) |
| §4.1 madde 2 filtre şeridi (kontroller, çipler, "+ Başka alan", temizle) | `QuickFilters.test.tsx`, `ReportsPage.test.tsx` (şerit → §2.1 gövdesi birebir: `between` dizi, `in` liste, number) |
| §4.1 madde 3 "Kolonlar (N)" yan paneli (setler, gruplar, tümünü seç, sıra, tavan, "Temel" üretimi) | `components/reports/ColumnSheet.test.tsx`; `ReportsPage.test.tsx` (set → önizleme, grup tümünü seç, kapanışta ek istek yok) |
| §4.1 madde 4 başlıktan sıralama (döngü, tavan 3) | `components/reports/PreviewTable.test.tsx`; `builderState.test.ts::siralamaDongusu`; `ReportsPage.sablon.test.tsx` (sıralama tanım gövdesinden) |
| §4.1 madde 5 otomatik önizleme (yapısal hemen / 600 ms / odak çıkışı / yalnız geçerli tanım / yarış) | `ReportsPage.test.tsx` (sahte zamanlayıcı; "taslak eksik"te istek gitmez; bayat rozeti DOM'da yok) |
| §4.1 madde 6 dolu açılış | `ReportsPage.test.tsx` (açılışta tek istek, varsayılan tanım) |
| §4.1 madde 7 metin azaltma (açıklama tek yer, tip rozeti yok, "Rapor Oluşturucu" yok) | `ReportsPage.test.tsx` sadeleştirme senaryosu |
| §4.1 madde 8 şablon/asistan uyumu; asistan tanımı otomatik önizlenir | `ReportsPage.sablon.test.tsx`, `ReportsPage.asistan.test.tsx` (`eylem=null` → otomatik önizleme; `onizle` → yeniden istek; `indir_xlsx` → `kaynak:"asistan"`) |
| Hub dosyalar (`App.tsx`/`Sidebar.tsx`/`api.ts`) ve `package.json` değişmedi | G138/G139 raporları; `Sidebar.tsx` yalnız G133 satırı (`:67`) |

Koşu sonuçları (işçi raporları): backend `pytest` 2670 passed / 3 skipped (G137), ruff + mypy temiz;
frontend `vitest` 798 passed / 65 dosya (G139), eslint 0 uyarı, `tsc -b --force` 0. Tarayıcıda görsel duman
testi YAPILMADI (backend/MSAL gerektirir) — sabah gerçek ekranda kart satırının `lg` altı kaydırması, Sheet
genişliği, araç çubuğu sarması göz kontrolü ister (G139 raporu). Açık NOT: `ColumnPicker.tsx:285` ipucu
(yukarıda), `lib/api.test.ts` "tek logout" testinin yük altında bir kez düşmesi (hub, kapsam dışı).

---

## 5. Üçüncü tur — arama/filtre kuralı: "veriden kapalı liste" + müvekkil şeridi (2026-09-07 gündüz, kullanıcı kararı; G141-G142)

**Kullanıcı bulgusu (07.09 sabah, lokal):** "birden fazla şehir seçilemiyor; Müvekkil Türü ayrı ve anlamsız;
filtrelemede hâlâ sorun var, önce müvekkil için düşünelim." Planlayıcı ölçümü (lokal DB, 1.998 kart): İl 79
farklı değer (temiz yazım), Kategori 11, Uzmanlık 44 (1.214 doktorda dolu), Müvekkil Türü ham İngilizce kod
(Individual 1.898 / Corporate 99 / "Gerçek Kişi" 1 — kategoriyle aynı bilgi), Kayıt Türü tek değer ("Client"),
vekalet geçerlilik hiç dolu değil, e-posta 1.187 / cep 1.392 dolu, Sektör 597 farklı yazım (gerçek serbest metin).
Teşhis: §4.2 "tipten kontrol" kuralı yetersiz — teknik olarak metin ama fiilen kapalı liste olan alanlar
(il, uzmanlık, mahkeme, avukat, yükleyen…) çoklu seçim olmalı; "içerir" yalnız gerçekten serbest metinde.

### 5.1 Hedef (müvekkil şeridi; kalıp diğer kaynaklara sonraki adımda)

1. **Tek arama kutusu** en üstte: ad · cari kod · e-posta · telefon · cep üzerinde birden "içerir".
2. **Kategori çipleri** doğrudan görünür (açılır liste değil), çoklu seçim.
3. **İl** aranabilir çoklu seçim; en sık kullanılan 8 değer üstte, gerisi yazdıkça.
4. **Uzmanlık** aranabilir çoklu seçim.
5. **Dava durumu**: "davası var / yok" anahtarı (isteyen "+ Başka alan"dan sayı aralığı).
6. **İletişim**: "e-postası yok" / "telefonu yok" anahtarları.
7. **Gizlenenler** (hızlı şeritte yok, "+ Başka alan"dan ulaşılır): Müvekkil Türü (etiketleri "Gerçek kişi /
   Tüzel kişi"), Kayıt Türü, vekalet alanları.
8. **"boş olanlar" kutucukları KALKAR**; çoklu seçim listelerinde "(boş)" seçeneği; tarih/sayı aralıklarında
   boş için çipin "…" menüsü (`is_null`) yeter.

### 5.2 Sözleşme genişlemesi (G141 — DONDU; G142 buna göre PARALEL)

- **Veriden kapalı liste:** metin kolonda `secenek_esigi` (kayıt defterinde kolon bazında `veriden_liste=True`
  işareti; varsayılan eşik `RAPOR_SECENEK_ESIGI=100` env) — DISTINCT değer sayısı eşiğin altındaysa katalogda
  `kontrol="coklu_secim"`, `secenekler` = DISTINCT (tenant + soft-delete kurallı, boş hariç, **sıklığa göre**
  azalan, en fazla eşik kadar), `secenek_kaynagi="veri"`; eşik aşılırsa `kontrol="metin_icerir"` + `oneriler`
  (G137 davranışı). `tip` **"metin" kalır** (op tablosu değişmez: `in`/`eq`/`contains` hepsi izinli).
  İşaretlenecekler: Müvekkiller `il, specialty, client_type(sabit etiketli)`; Davalar `court, judicial_unit,
  responsible_lawyer_name, uyap_lawyer_name, sub_type`; Belgeler `uploaded_by, belge_turu_adi`. Zaten `liste`
  tipli olanlar işaretlenmez, sabit kalır (`secenek_kaynagi="sabit"`, kontrol zaten `coklu_secim`): Davalar
  `karar_turu, case_stage, dosya_son_durumu`; Föyler `muvekkil_tipi`; Müvekkiller `client_type`. (G141 uygulama
  notu, 07.09 gece: "veriden liste" yalnız düz+önerili METİN kolonda tanımlıdır — liste kolonda anlamsız.)
  Eşik karşılaştırması `≤` (DISTINCT sayısı = eşik → yine `coklu_secim`). Veriden liste eşik ALTINDA öneri
  katmanı KOŞMAZ (`oneriler=null`, `oneri_kesik=false`) — `secenekler` ve `oneriler` birbirinin yerine geçer,
  frontend `kontrol`e bakar. `secilebilir=false` kolon `siralama`da da 422.
- **Seçenek etiketleri:** `KatalogKolon.secenek_etiketleri: {deger: etiket} | null` — ham kod saklanan
  alanlarda (client_type: `Individual→"Gerçek kişi"`, `Corporate→"Tüzel kişi"`, `Gerçek Kişi→"Gerçek kişi (eski
  yazım)"`); filtre değeri HAM kod olarak gider, yalnız gösterim etiketli.
- **`in` listesinde boş:** §2.1 `Filtre.deger` `in` için `list[str|number|null]`; `null` öğesi "(boş)"
  demektir → motor `IN (...) OR IS NULL` (tek başına `[null]` = `is_null`). Asistan çevirisi (`AsistanFiltre`)
  `degerler` metin listesinde `"(boş)"` sabitini `null`'a çevirir. Diğer op'larda `null` reddedilir (422).
- **Sanal arama kolonu:** her kaynağa `arama` (etiket "Ara", tip metin, `secilebilir=False`, `siralanabilir=False`,
  `turetilmis=True`, yalnız `contains`): Müvekkiller `name|cari_kod|email|phone|mobile_phone`; Davalar
  `tracking_no|esas_no|subject|court|muvekkil_adlari(EXISTS)|karsi_taraf_adlari(EXISTS)`; Belgeler
  `original_filename|dava_tracking_no|ai_summary`; Föyler `sistem_no|tku_no|hasar_no|dava_tracking_no`.
  Katalog kolonuna `secilebilir: bool` alanı (varsayılan true); `secilebilir=false` kolon `kolonlar`
  listesinde 422, kolon setlerinde yok, `katalog_metni`'ne "yalnız filtre" şerhiyle girer.
- **Hızlı filtre sunumu:** `HizliFiltre.sunum: "varsayilan" | "arama" | "cipler" | "var_yok" | "bos_anahtari"`
  + `etiket: str|null` (anahtar metni, ör. "Davası var", "E-postası yok"). Eşleme (frontend §5.3):
  `arama` → arama kutusu (`contains`); `cipler` → görünür çip satırı (çoklu, `in`); `var_yok` → sayı kolonunda
  anahtar: açık = `gte 1`, kapalı = filtre yok, "yok" = `eq 0`; `bos_anahtari` → açık = `is_null`.
  Müvekkiller hızlı filtreleri (sıra): `arama(arama)` · `category(cipler)` · `il` · `specialty` ·
  `dava_sayisi(var_yok,"Davası var")` · `email(bos_anahtari,"E-postası yok")` · `mobile_phone(bos_anahtari,
  "Cep telefonu yok")`. Davalar listesi değişmez (+ `arama` başa). Belgeler/Föyler: `arama` başa.
- **Sık kullanılanlar üstte:** `secenekler` sıklığa göre geldiği için ek alan gerekmez; frontend ilk 8'i
  "sık" bölümü olarak gösterir.
- Sunucu sözleşmesi dışında değişiklik yok: `/preview`/`/export` gövdesi aynı; DB/migrasyon yok.

### 5.3 Frontend (G142) kontrol kuralları

| kontrol / sunum | görünüm | üretilen filtre |
| --- | --- | --- |
| arama | tek kutu, 600 ms gecikme, temizle × | `arama contains "…"` |
| cipler | görünür çip satırı (≤ 12 seçenek; fazlası "+N" açılır) | `in [...]` (1 seçim → `eq`) |
| coklu_secim (veriden) | aranabilir açılır: "Sık" (ilk 8) + "Tümü" + "(boş)" seçeneği | `in [..., null]` |
| var_yok | üçlü anahtar: hepsi / var / yok | — / `gte 1` / `eq 0` |
| bos_anahtari | tek kutucuk "X yok" | `is_null` |
| (kaldırıldı) "boş olanlar" yan kutucuğu | — | tarih/sayı için çip "…" menüsünde `is_null` |

Şablon/asistan tanımı gidiş-dönüşü korunur: `in` içindeki `null` "(boş)" çipi olarak görünür; `arama`
kolonu şeridin arama kutusuna çözülür; `secilebilir=false` kolon Kolonlar panelinde listelenmez.

### 5.4 Görevler

| Görev | Bant | Bağımlı | İçerik |
| --- | --- | --- | --- |
| G141 | backend | – | Veriden kapalı liste (eşik + sıklık sırası), `secenek_etiketleri`, `in` içinde `null`, sanal `arama` kolonu + `secilebilir`, `HizliFiltre.sunum/etiket`, müvekkil hızlı filtre listesi; asistan çevirisi "(boş)" |
| G142 | frontend | – (sözleşme §5.2'den) | Arama kutusu, kategori çipleri, veriden çoklu seçim ("Sık"/"Tümü"/"(boş)"), var/yok ve "X yok" anahtarları, "boş olanlar" kutucuklarının kaldırılması, `secilebilir=false` gizleme, şablon/asistan gidiş-dönüş |
Test-değiştirme izni iki görevde de BAŞTAN yazılı (G138/G139 dersi). Docs: `raporlama.md` güncellemesi
bir sonraki docs turuna (G143) bırakılır — bu turda kod + test.

**Durum (07.09 gündüz koşusu, `2026-09-07d`): uygulandı — G141 `e1beb64`, G142 `52c04b3`; 0 BLOKE, 39 dk;
backend 2712 passed, frontend 836 passed.** Koşu sonrası kararlar (planlayıcı, aynı gün, `5a3f2e0`):
- **Eşik DEĞİŞMEDİ (100):** lokal veride `court` 2.306 farklı değer — çoklu seçim listesi anlamsız; mahkeme
  "içerir" + öneri (G137) olarak kalır. Eşik 150'ye çekilse de kapanmazdı; ileride il → mahkeme türü gibi
  kademeli filtre ayrı iş.
- **`KatalogKolon.aciklama` eklendi** (sözleşmeye ek alan; `arama` kolonlarında yer tutucu metin, diğerlerinde
  `null`) — G142 zaten isteğe bağlı okuyordu; plan §5.2'de yazılı değildi, uygulamada eklendi.
- **Deploy sırası:** G141 ve G142 birlikte deploy edilir; frontend `in` içinde `null` gönderiyor, eski backend
  422 verir.
- `prompts.py` "türetilmiş filtrelenemez" cümlesi G137'den beri bayattı → düzeltildi (aynı commit).
- Kalan docs işi G145: `raporlama.md` §2.1 katalog sözleşmesi (yeni alanlar), §8 kullanıcı akışı (arama kutusu,
  çipler, var/yok, "(boş)"), veriden liste kuralı ve eşik env'i, asistan-önde düzen ve favori önerisi (§6).

---

## 6. Dördüncü tur — asistan ön planda + favori önerisi (2026-09-07 gündüz, kullanıcı kararı; G143-G144)

**Kullanıcı isteği:** "AI asistan daha ön planda olsun; buton yerine göze çarpan, kullanıcıyı işini onunla
yapmaya teşvik eden bir format. Kullanıcı seçince favori format tipini '…' adıyla ekleyeyim mi diye sorsun,
evet derse kaydetsin." Gündüz ayrıca uygulandı (kuyruksuz): kaynak kartları minimal (`25403e7`), "Filtreler"
etiketi/sayaç, "Örnek" etiketi, "ilk N satır" notu, kolon paneli alt açıklaması kaldırıldı (`86e2df4`).
Backend değişikliği YOK (asistan `/chat` ve şablon CRUD uçları yeter).

### 6.1 Asistan-önde düzen (G143)

1. Rapor sekmesinin EN ÜSTÜNE (kaynak kartlarının üstü) **AssistantBar**: tam genişlik, göze çarpan kart
   (marka rengi vurgulu kenar), tek satır girdi "Ne listelemek istiyorsunuz? Yazın, asistan raporu hazırlasın…",
   gönder düğmesi (Enter gönderir), altında örnek istem çipleri (`ORNEK_ISTEMLER`, seçili kaynağa göre 3-4).
   Sağ altta küçük "veya aşağıdan seçin ↓" notu. Anahtar kapalıysa (`rapor_asistani=false` ya da 409) satır
   HİÇ görünmez; araç çubuğundaki eski "Asistan" düğmesi ve yan panel KALKAR.
2. Gönderince **konuşma alanı satırın altında açılır** (inline, kapatılabilir; `AssistantPanel`in mesaj listesi/
   NDJSON akışı/uyarı şeritleri buraya taşınır — mantık `reportsChat.ts` ve mevcut olay işleme aynen).
3. **Otomatik uygulama:** asistan geçerli `tanim` döndürdüğünde (eylem olsun olmasın) tanım oluşturucuya uygulanır
   ve önizleme yenilenir; kullanıcıya kısa toast ("Rapor hazırlandı · N kayıt"). `eylem=indir_*` mevcut yolla
   (`/export`, `kaynak:"asistan"`). Asistanın soru sorduğu (`tanim=null`) cevaplar konuşma alanında kalır.
   Uygulamadan önceki tanım "Geri al" bağlantısıyla bir adım geri alınabilir (kullanıcı beklemediği bir
   değişiklik görürse).
4. Konuşma geçmişi sayfa ömrü boyunca (K6 aynı); "Sohbeti temizle" korunur.

### 6.2 Favori (şablon) önerisi (G144)

1. **Tetik:** başarılı Excel/CSV indirme sonrası (manuel ya da asistan kaynaklı) mevcut tanım hiçbir kayıtlı
   şablonla birebir eşleşmiyorsa (`ayniTanim`) araç çubuğunun altında **FavoriOnerisi** kartı çıkar:
   "Bu formatı favorilere **'<önerilen ad>'** adıyla ekleyeyim mi?" — ad düzenlenebilir girdi, "Ekle" ve
   "Şimdi değil". Ekle → `createTemplate({ad, aciklama:"", tanim, paylasimli:false})` → toast + şablon
   çubuğunda seçili olur. "Şimdi değil" → o tanım için (sayfa ömründe) bir daha sorulmaz.
2. **Ad önerisi** `sablonAdiOner(tanim, katalog)` (saf, `lib/reports.ts`): "<Kaynak etiketi> · <en fazla iki
   filtre özeti>" (`kontrolOzeti` ile: "Doktor", "Ankara", "2025"), 60 karakter tavanı; aynı ad varsa " (2)".
3. Öneri kartı asistan konuşma alanıyla ve toast'larla çakışmaz: tek satır, kapatılabilir; "İndirme geçmişi"
   sekmesinde çıkmaz.
4. Ek: şablon çubuğunda mevcut tanım kayıtlı değilken kalıcı küçük "☆ Favorilere ekle" bağlantısı (aynı kartı
   açar) — indirme yapmadan da eklenebilsin.

### 6.3 Görevler

| Görev | Bant | Bağımlı | İçerik |
| --- | --- | --- | --- |
| G143 | frontend | – | AssistantBar en üstte + inline konuşma + otomatik uygulama + geri al; araç çubuğu düğmesi ve yan panel kalkar |
| G144 | frontend | G143 (ReportsPage ortak) | Favori önerisi kartı + ad önerisi + "☆ Favorilere ekle" |
Test-değiştirme izinleri baştan (ReportsPage*.test, AssistantPanel/AssistantMessage testleri, TemplateBar testi).

**Durum (07.09 gündüz koşusu `2026-09-07e`): uygulandı — G143 `eefdf81`, G144 `fd96c78`; 0 BLOKE, 45 dk;
frontend 873 passed.**

---

## 7. Beşinci tur — seçenek sayıları, veriye göre sıralama, "Boş" birinci sınıf seçenek (2026-09-07 gündüz, kullanıcı kararı; G145-G146)

**Kullanıcı bulgusu (kategori çipleri ekran görüntüsü):** "(boş) neden parantez içinde; sıralama iyi değil;
olmayanlar seçilebilsin, ileride veriler doldurulabilir; boş olanları seçme seçeneği çok hoşuma gitti ama
yetersiz." Ayrıca "E-postası yok" ve "Cep telefonu yok" anahtarları ayrı hücrelerde, biri tek başına satıra
düşüyor.

### 7.1 Hedef

1. **Her seçenekte kayıt sayısı** rozeti (Doktor 1.443 · Bireysel 423 · …), çipler ve açılır listeler kayıt
   sayısına göre azalan sırada; **sıfır kayıtlı seçenekler en sonda, soluk ama seçilebilir** (ileride veri
   dolunca kendiliğinden öne geçer). Sabit listeler (Durum, Kategori…) de sayılır.
2. **"Boş" birinci sınıf seçenek:** parantezsiz "Boş" etiketi, kendi stili (italik + ayırıcı çizgi), yanında o
   alanda boş olan kayıt sayısı; her çoklu seçimde ve çip satırında.
3. **Boş seçimi her kontrolde:** tarih aralığı, tutar aralığı ve metin/arama kontrollerinde de "Boş olanlar"
   küçük bir çip olarak (yan kutucuk değil, kontrolün içinde/yanında tek tık) — `is_null`; seçiliyken aralık
   girdileri kilitli.
4. **"X yok" anahtarları tek hücrede:** `bos_anahtari` sunumlu hızlı filtreler "Eksik bilgi" başlığı altında
   yan yana kutucuklar (e-postası yok · cep telefonu yok · …), her biri sayı rozetli.

### 7.2 Sözleşme genişlemesi (G145 — DONDU; G146 paralel)

- `KatalogKolon.secenek_sayilari: {deger: n} | null` — `secenekler` dolu her kolonda (sabit ya da veriden),
  kaynağın `kisitlar(tenant_id)` ile GROUP BY; sabit listede veride hiç geçmeyen değer `0`. Veriden listede
  zaten hesaplanan sayı kullanılır (ek sorgu yok). `secenekler` sırası: **sayıya göre azalan**, eşitlikte sabit
  listenin kendi sırası / alfabetik; sıfırlılar sonda.
- `KatalogKolon.bos_sayisi: int | null` — filtrelenebilir, `is_null` izinli her kolonda o alanda NULL/boş kayıt
  sayısı; kaynak başına TEK sorgu (`SELECT COUNT(*) FILTER (WHERE col IS NULL) …` — sqlite'ta `SUM(CASE …)`;
  metin kolonda boş string de boş sayılır). Türetilmiş kolonlarda `null` (hesaplanmaz).
- Katalog önbelleği (60 sn, tenant) hepsini kapsar; G145 raporu lokalde katalog süresini ölçer (hedef < 300 ms).
  > **G145 şerhi (07.09):** türetilmiş `liste` kolonda (`muvekkil_kategorisi` — EXISTS başına GROUP BY pahalı)
  > `secenek_sayilari = null`, sıra sabit listenin kendi sırası; `bos_sayisi` de `null` (türetilmiş). Sabit listede
  > veride görülen ek değerler artık tenant + soft-delete kurallı (K2; veriden liste ile aynı). Boş sayısında
  > `COUNT(*) FILTER` iki motorda da (sqlite ≥3.30) kullanıldı. Ölçüm lokal (14.5k dava): önbelleksiz medyan 242 ms
  > (taban 185 ms; kaynak başına tek UNION ALL GROUP BY + tek FILTER sorgusu).
- Asistan katalog metnine sayılar GİRMEZ.
- Sözleşme dışı değişiklik yok; `/preview`/`/export` aynı.

### 7.3 Frontend kuralları (G146)

| yer | kural |
| --- | --- |
| ChipSelect / çoklu seçim listesi | seçenek etiketi + küçük sayı rozeti; sıra katalogdan (değiştirilmez); sayı 0 → soluk (`opacity-60`), yine tıklanır, rozet "0" |
| "Boş" seçeneği | ayrı çip/satır: etiket **Boş**, italik, önünde ince ayırıcı; rozet `bos_sayisi`; `bos_sayisi=0` iken de görünür (soluk) |
| tarih/sayı/metin kontrolü | girdinin sağında "Boş" çipi (toggle) → `is_null`; seçiliyken girdiler kilitli; çip özeti "boş" |
| `bos_anahtari` yuvaları | tek "Eksik bilgi" hücresinde yan yana; her kutucuk "<etiket> · N" |
| Sık/Tümü bölümü | "Sık" = katalog ilk 8 (zaten sıklık sıralı); 0'lılar yalnız "Tümü"de |

### 7.4 Görevler

| Görev | Bant | Bağımlı | İçerik |
| --- | --- | --- | --- |
| G145 | backend | – | `secenek_sayilari` + sıklık sırası (sabit listeler dahil) + `bos_sayisi` (kaynak başına tek sorgu) + önbellek + ölçüm |
| G146 | frontend | – (sözleşme §7.2'den) | Sayı rozetleri, sıfırlılar soluk sonda, "Boş" birinci sınıf seçenek (parantezsiz), her kontrolde boş çipi, "Eksik bilgi" hücresi |
Docs turu G147: `raporlama.md` §2.1/§8 (§5, §6, §7 birlikte).
