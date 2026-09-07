# Raporlama modülü — kayıt defteri → önizleme → Excel/CSV export + koşu logu → AI asistan

> **Son doğrulama: 2026-09-06 · e31457e** (G136)
> Her uç adı, env, tablo adı ve limit koddan okunarak yazılmıştır; satır numaraları bu
> commit'e aittir. Kod ile çelişirse kod haklıdır — bu dosyayı düzelt. Plan/sözleşme dosyası
> [`docs/plan/raporlama-plani-2026-09-06.md`](../plan/raporlama-plani-2026-09-06.md);
> planla kod arasındaki farklar §11'de ve planın kendisinde "uygulamada değişti" şerhiyle.

Yönetici, DB'den kolon/filtre/sıralama seçerek liste üretir, önizler, Excel ya da CSV indirir;
her indirme "kim, ne zaman, hangi tanım, kaç satır, hangi dosya" olarak loglanır ve çıktının
kendisi diskte saklanır. Aynı ekranda AI asistan doğal dil isteğini rapor tanımına çevirir —
veriyi görmez, sorgu çalıştırmaz. **Test aşamasında yalnız yöneticiler** kullanır: bütün uçlar
`Depends(require_admin)` (`backend/routes/config.py:66-70`, `ADMIN_EMAILS`) +
`Depends(get_current_tenant)` (`backend/dependencies.py:71`) ile korunur.

```
Rapor sekmesi (frontend/src/pages/ReportsPage.tsx — G139: kaynak kartları SourceCards.tsx → filtre şeridi
QuickFilters.tsx → araç çubuğu: "Kolonlar (N)" yan paneli ColumnSheet.tsx + şablon çubuğu + Excel/CSV + Asistan
→ tam genişlik PreviewTable.tsx; ReportBuilder.tsx KALDIRILDI)
   │ GET /api/reports/catalog ──▶ registry.katalog()  (kaynaklar · kolonlar · tipler · seçenekler · limitler)
   │ POST /api/reports/preview ─▶ motor.onizle()      (sayfalı, LOGLANMAZ)
   │ POST /api/reports/export ──▶ COUNT → 413? → report_runs satırı → dosya <RAPOR_CIKTI_DIZINI>/<run_id>-<slug>.<ext>
   │                               → sha256/boyut → tembel temizlik → aynı dosya FileResponse (X-Rapor-Kosu-Id)
   │ GET  /api/reports/runs ────▶ tüm yöneticilerin koşuları;  /runs/{id}/download → saklanan dosya (410 = temizlendi)
   │ /api/reports/templates ────▶ favori şablonlar (kendi + paylaşımlı; soft delete)
   │
Asistan paneli (AssistantPanel.tsx) — yalnız admin anahtarı `rapor_asistani` AÇIKKEN görünür
   │ POST /api/reports/chat ────▶ NDJSON: info → [warning] → complete{cevap, tanim, eylem} | failed{error_ozet, error_kod}
   │                               Gemini JSON şemalı tek atış; `tanim` sunucuda AYNI doğrulamadan geçer (K6)
   └─ eylem: onizle → /preview · indir_xlsx|indir_csv → /export (kaynak:"asistan")  ← tek indirme = tek log yolu (K7)
```

## 1. Bileşenler

| Katman | Dosya | Rol |
| --- | --- | --- |
| Sözleşme | `backend/schemas_rapor.py` | `RaporTanimi`/`Filtre`/`Siralama`, sınırlar (`:19-23`), tip↔op tablosu `TIP_OPLARI` (`:29-36`), istek/cevap şemaları, asistan şema ailesi (`:188-273`) |
| Kayıt defteri | `backend/services/rapor/registry.py` | Dört veri kaynağı, kolon tanımları (SQLAlchemy ifadesi + tip + seçenekler), tenant/soft-delete kısıtları, katalog gövdesi |
| Motor | `backend/services/rapor/motor.py` | Tanım doğrulama, Core `select` kurma, önizleme, `yield_per` satır akışı |
| Çıktı | `backend/services/rapor/cikti.py` | xlsx (openpyxl write-only) / csv üretimi, sha256 |
| Koşu logu | `backend/services/rapor/kosu_logu.py` | `report_runs` yazma yolu, saklama dizini, path denetimi, temizlik |
| Asistan | `backend/services/rapor/asistan.py` + `backend/prompts.py:449` | Gemini çağrısı, katalog metni, asistan tanımı → `RaporTanimi` çevirisi |
| Uçlar | `backend/routes/reports.py` | `/api/reports/*` (prefix `:59`); `api.py:507-509` ile kayıtlı — `/api` altında olduğu için `nginx.conf:77` `location /api` yeter, nginx istisnası YOK |
| Tablolar | `backend/models.py:1350-1432`, `backend/database.py:1049-1064` | `ReportTemplate`, `ReportRun`, migrasyon madde 46 |
| Anahtar / env | `backend/services/app_settings.py:66-75`, `backend/config/settings.py:100-112` | `rapor_asistani` anahtarı; dört env |
| Frontend | `frontend/src/pages/ReportsPage.tsx`, `frontend/src/components/reports/*`, `frontend/src/lib/reports.ts`, `frontend/src/lib/reportsChat.ts` | Route `/reports` (`App.tsx:101-104`, `ProtectedAdminRoute`), Sidebar "Raporlar" (`Sidebar.tsx:67`, yalnız yönetici), `/api/reports/` uzun zaman aşımı listesinde (`api.ts:74`, 300 sn `:58`) |

## 2. Kayıt defteri (registry) — beyaz liste

İstemciden (ve asistandan) gelen hiçbir string SQL'e ham girmez: motor yalnız
`Kolon.ifade` SQLAlchemy ifadelerini kullanır; anahtar sözlükte yoksa 422
(`registry.py:1-7`, `motor.py:9-12`). Kolon tipi kolonun SQLAlchemy tipinden türetilir
(`_tip_bul`, `registry.py:81-94`: Boolean→`mantik`, DateTime/Date→`tarih`, Numeric→`para`,
Integer→`sayi`, kalan `metin`); kapalı listeli alanlar `liste` tipine seçeneklerle zorlanır.

| Kaynak | Çekirdek tablo + kısıt | Kolon (koddan sayıldı) | Türetilmiş kolonlar | Kod |
| --- | --- | --- | --- | --- |
| `davalar` | `cases`; `deleted_at IS NULL` + `tenant_filter_clause` | 86 | `muvekkil_adlari` (CLIENT), `karsi_taraf_adlari` (COUNTER) — `func.aggregate_strings(..., " ; ")`; `foy_sayisi`; `belge_sayisi` (silinmemiş belgeler) | `registry.py:153-299` |
| `muvekkiller` | `clients`; aynı kural `Client` üzerinden | 25 | `dava_sayisi` (case_parties.client_id → silinmemiş cases, DISTINCT) | `:303-358` |
| `belgeler` | `case_documents` INNER JOIN `cases`; belge `deleted_at IS NULL` + dava kısıtları | 20 | `dava_tracking_no`, `dava_subject` (JOIN kolonu, türetilmiş sayılır) | `:363-403` |
| `foyler` | `case_foys` INNER JOIN `cases`; dava kısıtları | 18 | `dava_tracking_no`, `dava_subject`; `ham_veri` katalog DIŞI | `:408-443` |

Kurallar (kayıt defteri import anında kendini denetler, `_kendini_denetle`, `registry.py:456-470`):

- **Kataloga girmeyenler:** `YASAK_KOLONLAR = {tenant_id, deleted_at, deleted_by, delete_reason,
  notes, ham_veri, tc_no}` (`:453`); ayrıca `clients.source_ids`, belge `email_error` /
  `conversion_spool_path` listeye alınmamıştır (`:17-19`).
- **Seçeneksiz `liste` kolon yok.** Seçenek üç katman: sabit çekirdek (seed sabitleri
  `EVENT_TYPES`/`CLIENT_TYPES`/`SERVICE_TYPES`/`CURRENCIES`/... + kod sözlükleri `:128-148`) +
  referans tablosunun aktif adları (`secenek_tablosu`) + kolondaki DISTINCT değerler;
  `secenekleri_getir(kolon, db)` birleştirir, `db=None` ise yalnız çekirdek (asistan prompt'u)
  (`:477-500`). Katalog her çağrıda DB'den okur → seçenek listesi statik değildir, büyür.
- **Türetilmiş kolon filtrelenemez ve sıralanamaz** (`_turetilmis`, `:113-115`; katalog
  `filtrelenebilir=false`, `siralanabilir=false`, `turetilmis=true`).
- **Tıbbi beşli** (`tibbi_surec`, `tibbi_olay`, `iddia_edilen_kusur`, `hastada_olusan_zarar`,
  `uygulanan_yontem`) `" ; "` ayraçlı ÇOK DEĞERLİ metindir → `liste` DEĞİL, `contains` ile
  aranır (`:281-286`).
- INNER JOIN sonucu: davasız (`case_id IS NULL`, TEST/UNLINKED) belge rapora GİRMEZ — tenant'a
  bağlanamadığı için bilinçli (`:11-15`).

## 3. Rapor tanımı ve doğrulama

`RaporTanimi = {veri_kaynagi, kolonlar[], filtreler[{alan, op, deger}], siralama[{alan, yon}]}`
(`schemas_rapor.py:75-93`; `extra="forbid"`). Sınırlar (`:19-23`): kolon 1-60 tekrarsız, filtre ≤20,
`in` ≤200 değer, sıralama ≤3, önizleme `sayfa_boyu` ≤200. İki doğrulama katmanı, tek hata tipi:

1. **Yapısal** (Pydantic) — adet/tekrar/op sözlüğü; route gövdeyi `dict` alıp elle doğrular ki
   FastAPI'nin `[{loc,msg,type}]` listesi yerine sözleşmedeki tek `{"alan","sebep"}` dönsün
   (`pydantic_hatasini_cevir`, `:276-288`; `routes/reports.py:22-23`, `:69-73`).
2. **Kayıt defterine karşı** (`motor.tanimi_dogrula`, `motor.py:123-143`) — kaynak/kolon var mı,
   kolon filtrelenebilir/sıralanabilir mi, op kolon tipinde izinli mi, değer biçimi doğru mu
   (`_deger_cevir`, `:93-120`: tarih ISO `YYYY-AA-GG`, sayı/para → `Decimal`, mantık `bool`,
   `between` tam iki öğe, `in` boş olmayan liste).

Her iki katman `RaporDogrulamaHatasi(alan, sebep)` yükseltir → **422** `{"detail": {"alan", "sebep"}}`
(`schemas_rapor.py:40-49`). Aynı yol asistanın ürettiği tanıma da uygulanır (§7).

Tip ↔ izinli op tablosu (`TIP_OPLARI`, `schemas_rapor.py:29-36`; frontend ikizi
`lib/reports.ts` `OP_BY_TIP`):

| tip | op'lar | `deger` |
| --- | --- | --- |
| `metin` | eq, ne, contains, in, is_null, not_null | str / list[str] |
| `liste` | eq, ne, in, is_null, not_null | str / list[str] (seçeneklerden) |
| `tarih` | eq, gte, lte, between, is_null, not_null | ISO tarih / [başlangıç, bitiş] |
| `sayi`, `para` | eq, gte, lte, between, is_null, not_null | number / [min, max] |
| `mantik` | eq, is_null | bool |

Motor semantiği (`motor.py:188-212`): `contains` = ILIKE, `\`/`%`/`_` kaçışlı (`ESCAPE '\'`,
`:148-153`, `:202-203`); **`ne` NULL satırı da döndürür** (`or_(ifade != deger, ifade.is_(None))`,
`:198-201` — "durum ≠ X" sorusunda boş da farklıdır); DateTime kolonda tarih filtresi gün aralığı
(`eq` = `[gün, gün+1)`, `:164-185`; gün sınırı DB oturumunun saat dilimine göre, prod UTC).
Sıralama `desc → NULLS LAST`, `asc → NULLS FIRST`, sonda daima birincil anahtar (`:224-230`).
Serileştirme: tarih ISO, `Decimal → float`, NULL → `null` (`:235-242`).

## 4. HTTP uçları — `backend/routes/reports.py`

Hepsi `require_admin` + `get_current_tenant`; yönetici değilse 403 `"Yönetici yetkisi gerekli"`.

| Uç | Kod | Davranış |
| --- | --- | --- |
| `GET /api/reports/catalog` | `:78-88` | `{"veri_kaynaklari":[...], "limitler":{"onizleme_sayfa_boyu_max":200, "export_max_satir":<RAPOR_MAX_SATIR>}}` (`registry.katalog`, `motor.limitler` `motor.py:37-44`) |
| `POST /api/reports/preview` | `:91-108` | `{"tanim", "sayfa"≥1, "sayfa_boyu"≤200}` → `{"kolonlar":[{anahtar,etiket,tip}], "satirlar", "toplam", "sayfa", "sayfa_boyu"}`; **loglanmaz** (K4) |
| `GET /api/reports/templates` | `:143-161` | kendi (`olusturan` = kullanıcı e-postası, küçük harf) + `paylasimli=true`; silinmişler hariç; ad sırası |
| `POST /api/reports/templates` | `:164-183` | `{"ad"≤120, "aciklama"≤500, "tanim", "paylasimli"}` → 201 `RaporSablonu`; tanım kayıt anında motor doğrulamasından geçer (422) |
| `PUT /api/reports/templates/{id}` | `:186-209` | tam gövde (kısmi değil); sahibi değilse 403 (`_sahibi_dogrula`, `:131-133`); yoksa 404 |
| `DELETE /api/reports/templates/{id}` | `:212-229` | 204, soft delete (`deleted_at` + `deleted_by`); sahibi değilse 403 |
| `POST /api/reports/export` | `:239-297` | `{"tanim", "format":"xlsx"∣"csv", "sablon_id"∣null, "kaynak":"manuel"∣"asistan"}` → dosya; §5 |
| `GET /api/reports/runs?limit=50&offset=0` | `:320-338` | `limit` 1-200 (`RUNS_LIMIT_MAX`, `:61`); `{"toplam", "kosular":[RaporKosusu]}`, tüm yöneticilerin koşuları, `baslangic desc, id desc`, tenant filtreli |
| `GET /api/reports/runs/{id}/download` | `:341-368` | saklanan dosya; yol NULL ya da dosya yok → **410**; yol dizin dışında / izinsiz uzantı → **404**; başka tenant → 404 |
| `POST /api/reports/chat` | `:373-397` | NDJSON (§7); anahtar kapalıysa gövde ayrıştırılmadan **409** `{"detail":"rapor_asistani kapalı"}` (`:381-382`) |

Kullanıcı kimliği `preferred_username | upn | email` üçlüsü, küçük harf (`_kullanici_epostasi`,
`:64-66`) — `require_admin` ile aynı okuma; frontend sahiplik karşılaştırması da küçük harf
(`lib/reports.ts:464` `sablonSahibiMi`).

## 5. Export — tek indirme yolu, tek log yolu

Sıra (`routes/reports.py:246-297`): gövde 422 → `sablon_id` verildiyse var mı (404, `:255-256`)
→ `COUNT` (`:258`) → tavan `settings.rapor_max_satir` aşımı **413**
`{"detail":{"sebep":"satir_limiti","toplam":n,"limit":m}}` (`:259-261`; koşu satırı YAZILMAZ)
→ `kosu_baslat` (satır COMMIT edilir, `id` dosya adına girer; `kosu_logu.py:77-90`)
→ `cikti.ciktiyi_yaz(format, kolonlar, motor.satirlari_akit(...), hedef)` (`:274`)
→ `kosu_bitir` (yol, boyut, sha256, satır sayısı, süre; `kosu_logu.py:93-107`)
→ `temizle_sessiz` (`:291`) → aynı dosya `FileResponse`, başlıklar `Content-Disposition:
attachment; filename="hukdok-rapor-<kaynak>-<YYYYMMDD-HHMM>.<ext>"` (`_indirme_adi`, `:234-236`;
`<kaynak>` = gövdedeki `manuel`/`asistan`) ve `X-Rapor-Kosu-Id: <run id>` (`:294-297`).

- **Dosya-önce kuralı:** çıktı önce `<RAPOR_CIKTI_DIZINI>/<run_id>-<slug>.<ext>` yoluna yazılır
  (`cikti_yolu`, `kosu_logu.py:45-51`; slug yalnız `[A-Za-z0-9-_]`, `Path.name` ile dizin bileşeni
  atılır), boyut + sha256 dosyadan parça parça hesaplanır (`cikti.dosya_ozeti`, `cikti.py:198-206`);
  indirilen dosya ile saklanan dosya AYNI bayttır, `report_runs.sha256` bunu kanıtlar.
- **Bellek disiplini (K3):** motor `yield_per=500` (`AKIS_PARCA`, `motor.py:33`, `:270-277`),
  xlsx `Workbook(write_only=True)` (`cikti.py:106`), csv doğrudan dosya akışı; tüm satır listesi
  hiçbir yerde tutulmaz.
- **Hücre kuralları** (`cikti.py:12-21`): xlsx'te `tarih` gerçek tarih hücresi (`DD.MM.YYYY` /
  `DD.MM.YYYY HH:MM`), `para` `#,##0.00`, `mantik` Evet/Hayır, başlık bordo `4A1530` + beyaz
  kalın, A2 dondurma, otomatik filtre; csv `utf-8-sig` + `;` (`:39-40`), tarih `GG.AA.YYYY`.
- **CSV formül enjeksiyonu:** `= + - @` ile başlayan METİN hücreye `'` öneki, sayılar (negatif
  dahil) dokunulmaz (`csv_hucresi_koru`, `cikti.py:88-93`).
- **Hata yolu** (`:275-285`): yarım dosya silinir, `db.rollback()`, koşu satırı `hata` (≤500 karakter)
  ile KALIR, TEK ERROR log, istemciye 500 `"Rapor üretilemedi"`.

## 6. Tablolar ve migrasyon

`report_templates` (`models.py:1350-1384`): `id, ad(120), aciklama(500), tanim JSON, olusturan(255),
paylasimli bool, tenant_id(64), created_at, updated_at, deleted_at, deleted_by(255)`.
`report_runs` (`:1387-1432`): `id, sablon_id FK → report_templates ON DELETE SET NULL, tanim JSON
(anlık görüntü), format(8), kaynak(16) default 'manuel', veri_kaynagi(32), kolon_sayisi, satir_sayisi,
kullanici(255), tenant_id(64), baslangic timestamptz, sure_ms, dosya_adi(255), dosya_yolu(500),
dosya_boyutu, sha256(64), hata(500)`. `tenant_id` yazılır (gelecek ayrım), okuma
`tenant_filter_clause` ile (`auth_helpers.py:14`; `routes/reports.py:117-121`, `:316-317`).

Migrasyon madde 46 (`database.py:1049-1064`): iki tablo `create_all` ile doğar, `("table", ...)`
op'u YAZILMADI (G041 kuralı — ölü kod olurdu). Performans index'i YOK (K10: sıfır dolulukla doğan
tablo ölçülmeden index almaz). **Tek istisna** `idx_report_runs_sablon ON report_runs (sablon_id)`
(`:1062-1064`, koşulsuz `("index", ...)` op'u, `IF NOT EXISTS`) — G043 bekçisi
`test_index_siz_fk_kolonu_kalmadi` index'siz FK'yı yapısal olarak yasaklar; ölçüm sorusu değil.
`format IN ('xlsx','csv')` CHECK'i DB'de değil Pydantic `Literal`'da (`schemas_rapor.py:121-122`).

Neden DB'de, localStorage değil (model docstring'i, `models.py:1355-1358`): paylaşımlı şablonu
diğer yöneticiler görür; çıkıştaki `clearAppStorage()` tarayıcı deposunu siler; `report_runs.sablon_id`
denetim izi. `tanim` JSON şablon sonradan değişse/silinse de "o gün ne indirildi"yi cevaplar.

## 7. Asistan — `POST /api/reports/chat`

Gövde `SohbetIstegi` (`schemas_rapor.py:220-233`): `mesajlar[{rol:"user"|"assistant", icerik}]`
1-20 adet, içerik 1-4000 karakter, **son mesaj `user`** olmalı; `mevcut_tanim: RaporTanimi|null`.
Kapı sırası: 403 (yönetici) → 409 (anahtar, gövde ayrıştırılmadan) → 422 (gövde).

Akış (`services/rapor/asistan.py:232-276`):

```
{"status":"info","message":"Rapor tanımı hazırlanıyor"}
{"status":"warning","message":"Asistanın ürettiği tanım doğrulanamadı (<alan>: <sebep>); tanım olmadan devam ediliyor."}   # isteğe bağlı
{"status":"complete","cevap":"<Türkçe metin>","tanim":RaporTanimi|null,"eylem":"onizle"|"indir_xlsx"|"indir_csv"|null}
{"status":"failed","error_ozet":"... (Kod: xxxxxxxx)","error_kod":"gemini_saturated|gemini_blocked|gemini_truncated|schema_invalid|analysis_error"}
```

`complete`/`failed` SON olaydır; `failed` `analyzer._failed_event` ile üretilir (`analyzer.py:368`),
etiket sınıflandırması `_hata_esle` (`asistan.py:212-229`; 429/5xx/devre kesici → `gemini_saturated`
`analyzer._api_error_kod` ile). Route'un beklenmedik istisnası `{"status":"error","message":"Beklenmedik
hata (Kod: ...)"}` verir ve sözleşme dışıdır (`routes/reports.py:389-395`, `/process` ile aynı desen).

- **Gemini çağrısı YALNIZ `analyzer._gemini_call_with_retry`** (`analyzer.py:82`; devre kesici +
  retry + health sayacı tek yerde) — `asistan.py:251`; `analyzer` tembel import edilir çünkü modül
  import'u `GEMINI_MODEL_NAME` ister ve CI/lokal testler bu env olmadan `routes.reports`'u yükler
  (`:24-29`, `:76-81`). `config`: `system_instruction` + `response_mime_type="application/json"` +
  `response_schema=RaporAsistanCevabi` (`:245-249`).
- **Model (K9):** `get_rapor_model()` (`:64-73`) → `GEMINI_RAPOR_MODEL` boşsa
  `case_intake_analyzer.get_intake_model()` (`case_intake_analyzer.py:60`, `GEMINI_INTAKE_MODEL`).
- **Sistem talimatı** (`prompts.py:449`): katalog `katalog_metni()` ile registry'den üretilir
  (`asistan.py:97-108`: `## kaynak — etiket: açıklama`, varsayılan kolonlar, `anahtar · etiket · tip[ ·
  seçenek|seçenek][ · türetilmiş]`; seçenekler yalnız sabit çekirdek, DB'siz), elle kolon listesi YOK;
  bugünün tarihi göreli ifadeler için; `mevcut_tanim` JSON olarak gömülür ("sıfırdan üretme, değiştir").
- **Gemini şeması `RaporTanimi` DEĞİL** (`schemas_rapor.py:188-204`): `extra="forbid"`
  `additionalProperties:false` üretir (google-genai 2.11.0 Developer API modunda desteklenmez) ve
  `Filtre.deger: Any` tipsiz özellik olur. Bu yüzden `AsistanTanimi` filtre değerini METİN (`deger`)
  ya da metin listesi (`degerler`, `in`/`between`) taşır; sunucu kolon tipine göre çevirir
  (`asistan_tanimini_cevir`, `asistan.py:158-175`: mantık `true/false/evet/hayır`, sayı/para `Decimal`,
  tarih strip) ve sonucu **aynı** `RaporTanimi` + `motor.tanimi_dogrula` yolundan geçirir
  (`tanimi_dogrula`, `:178-187` — K6 tek doğrulama). Geçmezse `warning` + `tanim=null` + `eylem=null`
  ile yine `complete` (`:264-276`); geçersiz tanım istemciye hiçbir zaman `tanim` olarak gitmez.
- **Sohbet geçmişi sunucuda saklanmaz** (K6): istemci `mesajlar`ı taşır; `icerikleri_kur` son 20
  mesajı `user`/`model` rolüne eşler, baştaki asistan mesajlarını atar (Gemini dizisi kullanıcıyla
  başlar; `:192-202`). Frontend geçmişi bileşen state'inde tutar, sayfa yenilenince sıfırlanır
  (`lib/reportsChat.ts:86` `gecmisiKirp` en yeni 20).
- **Asistan DB'ye dokunmaz:** `asistan.py` oturum fabrikası import etmez, satır görmez; `tenant_id`
  yalnız ERROR log bağlamıdır — tanım tenant filtresini `/preview`/`/export`'ta alır (`:237-238`).
- **Eylem (K7):** `eylem` yalnız öneridir; indirme frontend'in `/export` çağrısıyla `kaynak:"asistan"`
  olarak yapılır → koşu logunda "Asistan" rozeti (`ReportsPage.tsx`, `lib/reports.ts:518`).

## 8. Admin anahtarı — `rapor_asistani`

`SETTINGS_REGISTRY["rapor_asistani"]` (`services/app_settings.py:66-75`): label "Rapor asistanı (AI)",
**varsayılan KAPALI** (`default: False` — Gemini maliyetli özellikler repo kültüründe kapalı doğar;
`client_notice_enabled`, `veri_teslim_otomasyonu` gibi). Okuma `rapor_asistani_etkin()` (`:178-180`);
`GET/PUT /api/admin/settings` (`routes/admin.py:50`, `:56`) ile panelden açılır — Yönetim →
Özellikler kartı registry'den otomatik listeler. Kapalıyken `/chat` 409, panel düğmesi HİÇ render
edilmez (frontend `raporAsistaniAcikMi()` `GET /api/admin/settings`'i okur, hata/kayıt yok → false,
sessiz; `lib/reportsChat.ts:196`). **Manuel rapor anahtardan bağımsızdır**: katalog, önizleme,
export, şablonlar açık/kapalı fark etmez. Varsayılanı AÇIK yapmak tek satırdır (`app_settings.py:46-47`).

## 9. Env'ler (`config/settings.py:100-112`, `.env.example:49-66`)

| Env | Varsayılan | Ne | Okuyan |
| --- | --- | --- | --- |
| `RAPOR_MAX_SATIR` | `50000` | export satır tavanı; COUNT aşarsa 413 | `settings.rapor_max_satir` (`routes/reports.py:259`); katalogdaki `export_max_satir` ise `motor.limitler()` `os.getenv` ile okur (`motor.py:41`) — §12 |
| `RAPOR_CIKTI_DIZINI` | `""` → `<backend>/data/rapor_ciktilari` | saklanan çıktı dizini; konteynerde `/app/data` = `backend-data` volume'u (`docker-compose.yml:57`) → recreate'i atlatır | `kosu_logu.cikti_dizini` (`:34-42`) |
| `RAPOR_CIKTI_SAKLAMA_GUN` | `30` | dosya bu kadar günden eskiyse silinir, koşu satırı kalır, indirme 410 | `kosu_logu.temizle` (`:112-138`) |
| `GEMINI_RAPOR_MODEL` | `""` → `GEMINI_INTAKE_MODEL` | asistan modeli; devre kesici model-başına olduğundan intake'ten ayrılabilir | `asistan.get_rapor_model` (`:64-73`) |

Dördü de `.env.example`'da şerhli ve yorumlu (`:55`, `:59`, `:62`, `:66`); prod'da varsayılanlar
yeter. `.env` değişikliği `restart` ile gelmez, `docker compose up -d` (recreate) ister.

## 10. Güvenlik modeli

| Tehdit | Savunma | Kod |
| --- | --- | --- |
| SQL enjeksiyonu / rastgele kolon | serbest SQL yok; anahtar registry'de yoksa 422; `contains` ILIKE bağlı parametre + kaçış; `in` bağlı parametre | `registry.py:1-7`, `motor.py:9-12`, `:148-153`, `:202-205` |
| Tenant / soft-delete sızıntısı | her kaynağın `kisitlar(tenant_id)` = `deleted_at IS NULL` + `tenant_filter_clause`; `belgeler`/`foyler` `cases` INNER JOIN'i; şablon/koşu sorguları da tenant filtreli | `registry.py:153-154`, `:303-304`, `:363-364`, `:408-409`; `routes/reports.py:117-121`, `:316-317` |
| PII / teknik alan sızması | `YASAK_KOLONLAR` + import anı öz-denetim | `registry.py:453-470` |
| LLM'in ürettiği tanım | manuel tanımla AYNI Pydantic + registry doğrulaması; geçmezse `tanim=null` | `asistan.py:178-187`, `:264-276` |
| Path traversal (indirme) | `yol_guvenli_mi`: `resolve()` sonrası çıktı dizini altında VE `.xlsx/.csv`; aksi 404 | `kosu_logu.py:54-66`, `routes/reports.py:360-361` |
| Dosya adı enjeksiyonu | `cikti_yolu` slug'ı yalnız `[A-Za-z0-9-_]`, `Path.name` | `kosu_logu.py:45-51` |
| CSV formül enjeksiyonu | `= + - @` öneki `'` (metin hücre) | `cikti.py:88-93` |
| Kaynak tüketimi | kolon ≤60 / filtre ≤20 / `in` ≤200 / sayfa ≤200 / export tavanı 413 / `yield_per` + write-only; sohbet ≤20×4000 | `schemas_rapor.py:19-23`, `:206-207`; `routes/reports.py:259-261` |
| Yetki | tüm uçlar `require_admin` (`ADMIN_EMAILS`); şablon yazma yalnız sahibi (403) | `routes/config.py:66-70`, `routes/reports.py:131-133` |

## 11. Plan §2 ile kod arasındaki farklar (uygulamada değişti)

Sözleşme (`docs/plan/raporlama-plani-2026-09-06.md` §2) büyük ölçüde birebir uygulandı; aşağıdakiler
kodda plandan farklı ya da plana ek — plan dosyasında da aynı şerhle işaretlidir.

| # | Plan | Kod | Sonuç |
| --- | --- | --- | --- |
| F1 | §2.4 `RaporKosusu` alan listesi | `hata: str|null` alanı eklendi (`schemas_rapor.py:179`) | ek alan; istemci yok sayabilir |
| F2 | §2.5 / K10 "v1'de index yok" | `idx_report_runs_sablon` FK index'i (`database.py:1062-1064`) | G043 "index'siz FK yok" bekçisi; K10'un tek istisnası |
| F3 | §2.6 Gemini şeması `RaporAsistanCevabi{tanim: RaporTanimi}` | `tanim: AsistanTanimi` (metin değerli filtre; `schemas_rapor.py:236-264`) | dış sözleşme değişmedi: `complete.tanim` yine `RaporTanimi` (`SohbetTamamlandi`, `:267-273`) |
| F4 | §2.4 `/chat` gövdesi | ek sınırlar: mesaj ≤20, içerik ≤4000, son mesaj `user` → 422 (`:206-233`) | plana ek |
| F5 | §2.4 `/runs` `limit` | tavan 200 (`routes/reports.py:61`, `:322`) | plana ek |
| F6 | §2.4 `/export` | `sablon_id` yoksa 404 (`:255-256`); üretim hatası 500 + satır `hata` ile kalır (`:275-285`); 413'te satır yazılmaz | plana ek |
| F7 | §2.2 `ne` | NULL satırı dahil (`motor.py:198-201`) | semantik netleştirme |
| F8 | §2.3 katalog dışı liste | `tc_no`, `source_ids`, `email_error`, `conversion_spool_path` de dışarıda (`registry.py:17-19`, `:453`) | plana ek (PII/teknik) |
| F9 | §2.3 JOIN kolonları | `dava_tracking_no`/`dava_subject` türetilmiş sayılır → filtrelenemez/sıralanamaz (`registry.py:371-372`, `:416-417`) | v2'de açılabilir, tek satır |
| F10 | §2.6 olay listesi | route'un beklenmedik istisnası `{"status":"error","message"}` (`routes/reports.py:389-395`) | sözleşme dışı, `/process` deseni |

## 12. Bilinen sınırlar, işletme notları

- **Kapsam dışı (plan §1, bilinçli):** PDF çıktı, grafik/dashboard, zamanlanmış rapor e-postası,
  yönetici olmayan roller, sohbet geçmişinin DB'de saklanması, LLM'in SQL üretmesi. Ölçülen kullanım
  sonrası ayrı plan.
- **`RAPOR_MAX_SATIR` iki okuyucu:** export tavanı `settings.rapor_max_satir` (boot'ta donar),
  katalogdaki `export_max_satir` `motor.limitler()` `os.getenv` (her çağrı). Prod'da aynı env'i okurlar,
  fark yalnız test zamanı; `motor.limitler()`ın `settings`'ten okuması bekleyen tek satır (G131/G132
  raporları) — docs bandı kod değiştirmediği için açık.
- **Saklama dizini volume'da:** `/app/data/rapor_ciktilari` `backend-data` volume'unda doğar, recreate'i
  atlatır; disk büyümesi ≈ 30 gün × günlük export × ~3 MB, ilk ay ölçülür. Temizlik **tembel**: yalnız
  export sonunda koşar (`temizle_sessiz`), zamanlayıcı yok; export yapılmayan dönemde eski dosya
  diskte kalır. Temizlik hatası export'u düşürmez (WARNING, `kosu_logu.py:141-151`).
- **Bellek/süre ölçümü (G131 raporu, konteyner, 50.000 sentetik dava × 10 kolon, sqlite):** xlsx 2,6 MB /
  32,6 sn / tracemalloc tepe 8,4 MB; csv 7,3 MB / 2,3 sn / tepe 2,1 MB; `ru_maxrss` 75 → 89 MB.
  xlsx 50k satırda ~33 sn (openpyxl hücre maliyeti) — nginx 300 sn ve frontend 300 sn penceresi içinde.
- **Önizleme maliyeti:** `davalar` tüm kolonlarla 4 korele alt sorgu taşır; `toplam` COUNT'u büyük
  filtrelerde ölçülmedi (K10: index ölçülmeden yazılmaz).
- **`/chat` NDJSON'u konteyner nginx'inden geçer** (`location /api`); `proxy_buffering` ayarı yok —
  `info` olayının canlı gelip gelmediği gündüz duman testinde gözle doğrulanır (G135 raporu adım 7).
- **Asistan kalitesi gerçek Gemini ile ölçülmedi:** gece testleri sahte istemciyle geçti; gündüz duman
  testi istemleri G132 raporunda (3 örnek), adım listesi G135 raporunda. Şema kabulü (nullable object +
  enum) sorun çıkarırsa `AsistanTanimi.filtreler` düz metin `deger`e indirgenebilir (çevirici hazır).
- **Anahtar yeniden açılınca sayfa yenilemesi gerekir:** frontend `asistan409` sayfa ömrü boyunca
  kalır (G135, bilinçli).
- **Gün sınırı saat dilimi:** DateTime kolonlarda tarih filtresi DB oturumunun saat dilimine göredir
  (prod UTC; Türkiye günü 03:00'te başlar).
- **CSV ondalık `.`:** `Decimal→float` olduğu gibi yazılır; Türkçe Excel `;` ayraçlı CSV'de `,` ondalık
  bekleyebilir — xlsx ana yol, CSV ham veri yolu; kullanıcı geri bildirimiyle karar.

## 13. Log sözleşmesi

- Export üretim hatası: TEK ERROR (`routes/reports.py:277`), satır `hata` ile kalır.
- Temizlik: dosya silinemedi / temizlik atlandı → WARNING (`kosu_logu.py:132`, `:146`).
- Asistan: Gemini denemeleri `_gemini_call_with_retry` içinde WARNING; nihai başarısızlık TEK ERROR
  (`asistan.py:257-260`, `Kod:` kimliği ile); doğrulanamayan tanım WARNING (`:270`).
- `/chat` beklenmedik istisna: ERROR + `status:"error"` olayı (`routes/reports.py:393`).

## 14. Testler (kanıt)

| Dosya | Kapsam |
| --- | --- |
| `backend/tests/test_g130_rapor_temeli.py` | katalog şekli, yasak kolonlar, 403 (gerçek `require_admin`), 422 yolları, op×tip kombinasyonları, `contains` kaçışı, bağlı parametre, tenant + soft-delete dört kaynakta, türetilmiş kolonlar, sayfalama |
| `backend/tests/test_g131_rapor_export_ve_log.py` | şablon CRUD + sahiplik 403 + paylaşım, xlsx geri okuma + koşu satırı + sha256 = indirilen = saklanan, csv BOM/`;`/önek, 413, download traversal reddi, temizlik + 410, hata yolu, migrasyon kuralı bekçisi, akış (liste değil) |
| `backend/tests/test_g132_rapor_asistani.py` | anahtar varsayılan/409, 403, gövde sınırları, geçerli/geçersiz tanım akışı, 5 Gemini hatası → `error_kod` + TEK ERROR, yanıt hataları, prompt içeriği, kod incelemesi bekçileri (SessionLocal/`client.aio` yok), Developer API uyumlu şema |
| `frontend/src/lib/reports.test.ts`, `reports.export.test.ts`, `reportsChat.test.ts` | tip↔op tablosu, gövde biçimleri, hata çevirisi, `Content-Disposition`, NDJSON okuyucu, anahtar okuyucu |
| `frontend/src/pages/ReportsPage.test.tsx`, `ReportsPage.sablon.test.tsx`, `ReportsPage.asistan.test.tsx` | oluşturucu → önizleme gövdesi, yönetici kapısı, şablon/indirme/geçmiş, asistan paneli + eylem + 409/anahtar |

Backend testleri konteynerde (`docker compose exec -T backend python -m pytest tests/test_g13*.py`),
frontend host'ta (`npm --prefix frontend test`) koşar.

## 15. Nereye bakmalı

| Konu | Dosya |
| --- | --- |
| Sözleşme (plan, dondurulmuş §2 + şerhler) | [`docs/plan/raporlama-plani-2026-09-06.md`](../plan/raporlama-plani-2026-09-06.md) |
| Uçlar | `backend/routes/reports.py` |
| Şemalar, sınırlar, tip↔op | `backend/schemas_rapor.py` |
| Kayıt defteri / motor / çıktı / koşu logu / asistan | `backend/services/rapor/{registry,motor,cikti,kosu_logu,asistan}.py` |
| Sistem talimatı | `backend/prompts.py:449` |
| Tablolar + madde 46 | `backend/models.py:1350-1432`, `backend/database.py:1049-1064` |
| Anahtar / env | `backend/services/app_settings.py:41-79`, `backend/config/settings.py:100-112`, `.env.example:49-66` |
| Frontend tipler + API | `frontend/src/lib/reports.ts`, `frontend/src/lib/reportsChat.ts` |
| Frontend sayfa + bileşenler | `frontend/src/pages/ReportsPage.tsx`, `frontend/src/components/reports/` |
| Gemini devre kesici / retry / `_failed_event` | [`dis-bagimliliklar.md`](dis-bagimliliklar.md), `backend/analyzer.py:82`, `:368` |
| Görev raporları (G130-G136) | `gorevler/gorev/G130.md` … `G136.md` |
