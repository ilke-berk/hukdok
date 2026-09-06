# Raporlama modülü planı — kullanıcı tanımlı listeler, favori şablonlar, indirme logu, AI asistan

**Tarih:** 06.09.2026 · **Karar:** kullanıcı (06.09 sohbeti) · **Durum:** kuyruğa yazıldı (G130-G136), onay bekliyor.
**Kapsam kararları (kullanıcı):** test aşamasında yalnız yöneticiler (`require_admin`); çıktı Excel + CSV;
her indirme "kim, ne zaman, ne" ile loglanır ve çıktının kendisi sistemde saklanır; aynı ekranda AI sohbet
asistanı doğal dille rapor tanımı üretir (manuel yol her zaman açık kalır).

> **Bu dosya sözleşme kaynağıdır.** G130-G136 görevleri aşağıdaki JSON şemalarına ve uç adlarına birebir
> uyar; bir görev sözleşmeyi değiştirmek zorunda kalırsa ÖNCE burayı günceller ve raporunda yazar.
> Sayılar/yollar koddan doğrulanır (ALTIN KURAL, `CLAUDE.md`).

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

### 2.7 Env (`.env.example`'a eklenir)

```
# Raporlama modülü (G131/G132)
# RAPOR_MAX_SATIR=50000            # export satır tavanı; aşınca 413
# RAPOR_CIKTI_DIZINI=/app/data/rapor_ciktilari
# RAPOR_CIKTI_SAKLAMA_GUN=30
# GEMINI_RAPOR_MODEL=models/gemini-3.6-flash   # yoksa GEMINI_INTAKE_MODEL
```

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
