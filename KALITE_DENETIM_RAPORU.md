# HukuDok Automator — Kalite, Performans ve Güvenlik Denetim Raporu

**Tarih:** 3 Temmuz 2026
**Kapsam:** Backend (FastAPI, ~14.600 satır), Frontend (React/TypeScript), Docker/nginx deploy
**Yöntem:** Üç paralel denetim (güvenlik, performans, kod kalitesi) — tüm bulgular ilgili dosyalar okunarak doğrulandı, tahmine dayalı bulgu yok.

## Genel Değerlendirme

Sistemin savunma katmanları (Azure AD JWT doğrulama, tenant izolasyonu, magic-byte dosya doğrulama, log maskeleme) ve iş mantığı (toleranslı avukat eşleştirme, TTL cache, benchmark altyapısı) **bilinçli ve özenli kurgulanmış**. Kritik bir auth-bypass veya SQL injection **bulunamadı**.

Ana risk alanları üç başlıkta toplanıyor:

1. **Güvenlik konfigürasyonu:** CORS herkese açık, rate limiting fiilen çalışmıyor.
2. **Performans:** `async` endpoint'lerde event loop'u kilitleyen senkron çağrılar ("sistem ara ara donuyor" hissinin muhtemel kaynağı) ve veri büyüdükçe lineer kötüleşen DB desenleri.
3. **Yapısal borç:** Tanrı-dosyalar, hataların sahte-başarıyla yutulması, sıfır test, TS strict kapalı.

---

# 🔴 P0 — ACİL (bu hafta)

Küçük değişiklikler, yüksek etki. Hepsi birkaç saatlik iş.

## P0-1. CORS tüm origin'lere `allow_credentials=True` ile açık — GÜVENLİK

**Dosya:** `backend/api.py:181-187`

```python
app.add_middleware(CORSMiddleware, allow_origin_regex=".*",
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
```

`allow_origin_regex=".*"` gelen her `Origin`'i yansıtıp `Access-Control-Allow-Credentials: true` dönüyor — spec'in yasakladığı `*` + credentials kombinasyonunun regex ile baypası. Kötü niyetli bir site, kurbanın tarayıcısından API'ye credentialed istek atıp yanıtı okuyabilir. (Token sessionStorage + Bearer header'da olduğu için etki sınırlı, ama yüzey gereksiz geniş.)

**Düzeltme:** `allow_origins=["https://<prod-domain>", "http://localhost:5173"]` gibi sabit liste; `allow_origin_regex`'i kaldırın.

## P0-2. Rate limiting fiilen devre dışı — GÜVENLİK / MALİYET

**Dosya:** `backend/api.py:189-191`

`Limiter(default_limits=["100/minute"])` tanımlı ama slowapi'de `default_limits` yalnızca `SlowAPIMiddleware` eklenince çalışır; middleware eklenmemiş, per-route `@limiter.limit` dekoratörü de hiçbir yerde yok. **Hiçbir istek gerçekte sınırlanmıyor.** `/process` ve `/confirm` her istekte Gemini + SharePoint + e-posta tetiklediği için tek bir authenticated kullanıcı bile maliyet patlaması / e-posta spam'i yaratabilir.

**Düzeltme:**
```python
from slowapi.middleware import SlowAPIMiddleware
app.add_middleware(SlowAPIMiddleware)
```
Ek olarak `/process`, `/confirm`, `/api/documents/*/resend-email` için daha sıkı `@limiter.limit`.

## P0-3. Event loop'u kilitleyen senkron çağrılar — PERFORMANS

`async def` endpoint içinde senkron blocking çağrı = o işlem bitene kadar **tüm sistem donar** (diğer kullanıcıların analiz stream'leri dahil). Üç yer:

| Yer | Blocking çağrı | Kilit süresi |
|---|---|---|
| `backend/routes/processing.py:343, 394` → `email_sender.py:267, 401` | Senkron `model.generate_content` (e-posta önizleme) | 2-10 sn |
| `backend/routes/processing.py:733` → `pdf/pdf_converter.py:113` | Senkron Ghostscript `subprocess.run` (PDF/A dönüşüm, her `/confirm`'de) | 1-15 sn |
| `backend/analyzer.py:558, 582, 228-230, 982` | Senkron `genai.upload_file` / `genai.get_file` / `delete` (OCR modu) | birkaç sn |

Prod'daki "ara ara donma" şikayetlerinin ve lokal/prod hız farkı araştırmasının en güçlü adayı bu — kilitler `_benchmark` metriklerinde görünmez, başka isteklerin gecikmesi olarak yansır.

**Düzeltme:** Hepsini `await loop.run_in_executor(None, fn, ...)` ile sarın (veya endpoint'i `def` yapıp threadpool'a bırakın).

## P0-4. Exception yolunda DB session sızıntısı — GÜVENİLİRLİK

**Dosya:** `backend/routes/processing.py:124-188` (`_save_case_document`) ve `191-227` (`_auto_update_case_status`)

`db.close()` yalnızca başarı dallarında elle çağrılıyor, `finally` yok; hata durumunda session havada kalır → zamanla connection pool (10+20) tükenir → tüm sistem 500 döner. Aynı dosyadaki `_auto_enrich_case_data:288` doğru deseni zaten kullanıyor.

**Düzeltme:** `try/finally: db.close()` (5 dakikalık iş).

## P0-5. Ham exception mesajı kullanıcıya sızıyor — GÜVENLİK

**Dosya:** `backend/routes/processing.py:526-529`

`/process` stream'inde `f"Beklenmedik hata: {str(e)}"` doğrudan istemciye dönüyor — iç yol adları, kütüphane/DB hata metinleri sızabilir. Diğer endpoint'lerdeki jenerik mesaj + `error_id` deseni burada uygulanmamış.

**Düzeltme:** Jenerik mesaj + `error_id` dönün, `str(e)` yalnızca sunucu loguna.

---

# 🟠 P1 — YÜKSEK (bu sprint)

## P1-1. Eksik FK indeksleri — PERFORMANS

**Dosya:** `backend/models.py:132, 144, 160`

`case_parties.case_id`, `case_lawyers.case_id`, `case_history.case_id` üzerinde indeks yok (PostgreSQL FK'ye otomatik indeks koymaz). `get_cases` her çağrıda `selectinload` ile bu tablolara `WHERE case_id IN (...)` atıyor → her liste açılışında full-table scan. Liste hep `ORDER BY updated_at DESC` olduğu için `cases.updated_at`'e de indeks gerekli.

**Düzeltme:** Mevcut migration desenine 4 `CREATE INDEX` ekleyin. Veri büyüdükçe etkisi katlanır; şimdi ucuz.

## P1-2. Avukat filtresi iki tabloyu Python'da tarıyor — PERFORMANS

**Dosya:** `backend/managers/admin_manager.py:575-605` (çağrı: `get_cases:717`)

Avukat filtresi seçilince `cases` + `case_lawyers` tablolarının **tamamı** çekilip her satır Python'da normalize edilip eşleştiriliyor; her sayfa geçişinde tekrar. 10-50 bin davada saniyeler sürer.

**Düzeltme:** `case_lawyers.lawyer_id` FK'si zaten dolduruluyor — filtreyi `CaseLawyer.lawyer_id == X` JOIN'ine çevirin; legacy kayıtlar için eşleşme kümesini TTL cache'leyin.

## P1-3. Hataların sahte-başarıyla yutulması — GÜVENİLİRLİK / VERİ KAYBI

- **10 çıplak `except:`** — en tehlikelileri tarih parse'ları (`admin_manager.py:862, 867, 872, 994, 1002`): kullanıcı bozuk tarih girer, kayıt "başarılı" döner, **tarih sessizce kaybolur**.
- **217 `except Exception`** — çoğu hatayı loglayıp sahte-başarı dönüyor: `get_cases:812-814` hata → `[]` (UI "kayıt yok" gösterir), `get_case:441-443` hata → `None` (route 404 sanır). DB çökse kullanıcı fark edemez.
- `processing.py:186-188`: belge DB'ye yazılamazsa dosya SharePoint'e yüklenir ama sistemde kaydı olmaz (sessiz tutarsızlık).

**Düzeltme:** `add_case:958-963`'teki çoklu-format tarih döngüsünü ortak `parse_date_or_warn()` yapıp her yerde kullanın. Manager katmanı hatayı fırlatsın, route katmanı tek exception-handler'da 500 + `error_id`'ye çevirsin.

## P1-4. "Dosya Türü" filtresi çalışmıyor (canlı UI, işlevsiz) — KALİTE

**Dosya:** `frontend/src/pages/CaseList.tsx:148, 183, 208, 255`

Filtre UI'da var, kullanıcı seçiyor, ama `getCases`'e hiç gönderilmiyor (`useCases.ts:106-112` parametreyi almıyor, backend de desteklemiyor). **Hiçbir şey filtrelenmiyor.**

**Düzeltme:** Parametreyi uçtan uca bağlayın ya da kontrolü kaldırın.

## P1-5. Ekstra e-posta ekleri doğrulamasız — GÜVENLİK

**Dosya:** `backend/routes/processing.py:808-818`

Ana dosya uzantı + magic-byte ile denetleniyor, ama `extra_attachment_files` için hiçbir tip/uzantı/boyut doğrulaması yok; suffix doğrudan `filename`'den alınıyor. Authenticated kullanıcı `.exe`/`.html` gibi keyfi dosyayı sistem üzerinden dış alıcılara e-posta eki olarak yollayabilir.

**Düzeltme:** Ekstra ekleri de `sanitize_filename` + uzantı whitelist'inden geçirin.

## P1-6. Tracking-no üretim mantığı iki dilde çift tutuluyor — KALİTE

**Dosya:** `backend/retag_tracking_nos.py:29` ↔ `frontend/.../caseNumberUtils.ts`

`CATEGORY_MAP` / `INSURANCE_CODES` / `PROCESS_MAP` backend ve frontend'de elle senkron tutuluyor (kodda "frontend ile eşleşmeli" yorumu var) — sapma garantili, doctype-padding bug'ının kökündeki aynı desen.

**Düzeltme:** Üretimi tek yere (backend endpoint) alın, frontend sadece göstersin.

## P1-7. Sıfır test — KALİTE

Backend'de ve frontend'de tek bir test dosyası yok (`pytest` requirements'ta bile değil). En riskli mantıklar — `case_matcher.find_matching_case`, `admin_manager._norm_name/resolve_lawyer`, `file_utils._normalize_doctype_code`, tracking-no üretimi — saf fonksiyonlar, yani **test etmesi çok kolay** ama tamamen korumasız. Doctype-padding bug'ı prod'a sızıp `backfill_belge_turu_adi.py` ile onarılmak zorunda kaldı; tek bir birim testi yakalardı.

**Düzeltme:** pytest + önce normalize/eşleştirme fonksiyonlarından başlayın (1 gün, yüksek getiri).

---

# 🟡 P2 — ORTA (önümüzdeki ay)

## Güvenlik sağlamlaştırma

- **ID token → access token** (`frontend/src/lib/api.ts:32-33`): API'ye `idToken` gönderiliyor; `response.accessToken` olmalı. Çalışıyor ama OAuth2 modeline aykırı, scope tabanlı yetki eklenirse kırılır.
- **JWT `iss` doğrulanmıyor** (`backend/auth_verifier.py:69-78`): `verify_aud`/`verify_exp` var, issuer sabitlemesi yok. `jwt.decode`'a `issuer=...` ekleyin.
- **Avukat PII'si tüm kullanıcılara açık** (`backend/routes/config.py:54-61`): `tc_no`, `sicil_no`, adres dahil liste sadece `get_current_user` ile dönüyor. Hassas alanları genel yanıttan çıkarın.

## Performans

- **AnalysisCache devre dışı** (`backend/analyzer.py:298`): SHA-256 hash hesaplanıyor, `analysis_cache` tablosu ve `get_cache`/`save_cache` hazır, ama kullanılmıyor. Aynı belge ikinci yüklemede tam Gemini turu (5-30 sn + token) tekrar döner. Cache anahtarına `preset_belge_turu_kodu`'nu dahil ederek açın.
- **Gemini çağrısında timeout yok** (`backend/analyzer.py:79-81`): retry/backoff iyi ama tek çağrıya üst sınır yok — takılan istek analizi dakikalarca askıda bırakır. `asyncio.wait_for(..., timeout=90)` + timeout'u transient sayıp retry.
- **N+1: belge listelerinde `case_party`** (`backend/routes/documents.py:119-121, 177`; `admin_manager.py:403`): her belge için ayrı SELECT. `selectinload(CaseDocument.case_party)` ekleyin.
- **BackgroundTasks'ta 30 sn `sleep`** (`processing.py:1006-1021`): her `/confirm` iki background thread'i 30'ar sn işgal ediyor; yük altında anyio threadpool'u (~40) tükenir. Temizliği TTL eviction'a bırakın.
- **`case_matcher` tüm aktif davaları belleğe çekiyor** (`case_matcher.py:163-190`): executor'da çalıştığı için loop'u kilitlemiyor ama dava sayısıyla lineer büyür. Büyüme görülürse esas_no/isim ön filtresiyle aday kümesini SQL'de daraltın.
- **Route code-splitting yok** (`frontend/src/App.tsx:16-30`): Index (1473), NewCase (1679), AdminPage (1319) dahil her sayfa statik import. En az bu üçüne `React.lazy` + `Suspense`.
- **`DocCard` render içinde tanımlı** (`frontend/src/pages/CaseDetails.tsx:668-784`): her render'da yeni bileşen tipi → tüm belge kartları unmount/remount (açık Select'in kapanması dahil). Bileşen dışına taşıyın.
- **`case_history.old_value` üzerinde indekssiz `%…%` araması** (`admin_manager.py:758`): ya arama koşulundan çıkarın ya trigram indeksi ekleyin.

## Kod kalitesi / mimari

- **Tanrı-dosyalar:** `admin_manager.py` 1778 satır / 8+ sorumluluk; `processing.py` `/confirm` ~500 satır, 27 form parametresi, 6 iç fonksiyon; `analyzer.py` `analyze_file_generator` ~730 satır. Bölme planı: `managers/reference_lists.py` (generic CRUD), `managers/case_manager.py`, `services/document_pipeline.py`.
- **13 varlık için kopyala-yapıştır CRUD** (`admin_manager.py:81-1364`): ~600 satır, tek `LIST_REGISTRY` sözlüğü + generic fabrika ile ~60 satıra iner; `reorder_list:319` ve `refresh_cache:1750`'deki 13 dallı if-elif zincirleri de aynı anda çözülür.
- **Tekrarlanan yardımcılar:** avukat kodu→ad lookup'u 4 kopya (`processing.py:641, 868, 954`; `_auto_enrich_case_data:246`) → `config_manager.get_lawyer_by_code()`; Türkçe→ASCII dönüşümü 5+ implementasyon → tek `text_utils.fold_tr()`; `format_date_tr` aynı dosyada iki kez (`processing.py:324, 366`).
- **Frontend doctype `_` temizliği 5 ayrı yerde** (`predictDocType.ts:34`, `BulkUploadWorkbench.tsx:76`, `AnalysisResults.tsx`, `Index.tsx`): backend'deki tek merkez (`file_utils.py:209`) gibi frontend'de de `lib/doctype.ts`'e toplayın — geçmişteki "kısaltma sızması" bug'ının kökü bu dağınıklık.
- **TS strict tamamen kapalı** (`frontend/tsconfig.app.json`): `strict`, `noImplicitAny`, `strictNullChecks` hepsi false. Önce `strictNullChecks: true`, sonra kademeli `strict`.
- **`Case` tipi 5 ayrı yerde tutarsız tanımlı** (`CaseList.tsx:24`, `CaseDetails.tsx:30`, `CaseGroup.tsx:50`, `Index.tsx:32`, `useCases.ts:18`) → tek `types/case.ts`.
- **Elle yazılmış migrasyon** (`database.py:77-513`): ~30 "kolon var mı → ALTER" bloğu, her biri hatayı yutuyor — migrasyon başarısız olsa uygulama ayağa kalkıyor (sessiz şema sapması). Alembic'e geçin; en azından migrasyon hatasında startup'ı durdurun.
- **Sentinel string'ler DB'ye sızabiliyor:** sayaç hatasında `"XXXXXXXXX"` / `"TIMEOUT___"` (`processing.py:457-460`) tracking_no olarak kaydedilebilir. Named constant + üretimde reddetme.
- **Statü literal'leri dağınık:** `"DERDEST"/"KAPALI"/...` backend + frontend'de serbest string → tek sabit modülü.
- **Sahte toplam sayı** (`CaseList.tsx:171`): backend toplam dönmediği için "Sayfa X/Y" uyduruluyor; backend `{cases, total}` dönmeli (frontend'de o dal zaten hazır bekliyor).
- **Dev bileşenler:** `AdminPage.tsx` tek bileşende 54 useState / 14 useEffect; `Index.tsx` 38 useState. Sekme/adım başına alt-bileşen + `useReducer`.
- **Tek-seferlik scriptler uygulama koduyla iç içe:** backend kökünde 11 import/migrate/backfill scripti Docker imajına giriyor → `backend/scripts/` altına taşıyın, bitenler silinsin.

---

# 🟢 P3 — DÜŞÜK / ÖNERİLEN (fırsat buldukça)

- **Dev-mode auth bypass kodda** (`auth_verifier.py:38-41`): 3 env koşuluna bağlı, prod'da kapalı; yine de prod build'de erişilmez olduğundan emin olun.
- **50MB limiti `Content-Length` header'ına güveniyor** (`api.py:194-212`): chunked istekte atlanır; `/process`'teki streaming sayaç deseni genelleştirilebilir. Malformed header'da `int()` ValueError → 500.
- **SharePoint indirmesi streaming değil** (`documents.py:265, 282, 360`): 50MB'a kadar dosya tam bellekte → `StreamingResponse`.
- **Ham Gemini yanıtı INFO seviyesinde tam loglanıyor** (`analyzer.py:607`): log hacmi + KVKK — DEBUG'a çekin.
- **`/api/hearing-dates` sınırsız** (`CaseList.tsx:195`, `cases.py:421-455`): 7 günlük pencere parametresi yeterli.
- **Küçük N+1'ler:** `get_case_relations` döngüde sorgu (`cases.py:255-262`); liste sorgusu 60+ kolonun hepsini çekiyor (`load_only` ile daraltın).
- **Ölü kod / başıboş dosyalar:** `backend/test_yetki.udf`, kökteki `test_env/`, `admin_manager.py:1523` kullanılmayan `import locale`, `:355` mükerrer import, 36 adet `console.log` prod'a sızıyor.
- **Hardcoded kişisel yol** (`import_excel_cases.py:27`): `C:\Users\ilkeb\...` — CLI argümanı yapın.
- **Bağımlılık taraması:** sürümler makul güncel (FastAPI 0.121, PyJWT 2.8, React 18); `python-multipart` pinlenmemiş — CI'a `pip-audit` / `npm audit` ekleyin.

---

# ✅ İyi Durumda Olanlar (doğrulandı, sorun yok)

- **SQL injection yok** — ORM + parametreli sorgular; f-string SQL'ler yalnızca sabit kolon adları kullanıyor.
- **Secret yönetimi temiz** — hardcoded secret yok, `.env`/DB gitignore'da, git geçmişinde `.env` commit'i yok.
- **IDOR/tenant izolasyonu tutarlı** — `get_tenant_owned_*` zincirleri, `/confirm`'de `linked_case_id` ownership kontrolü, admin endpoint'leri `require_admin` korumalı.
- **Path traversal / XXE korumalı** — `sanitize_filename` (basename + null-byte + whitelist), `defusedxml`.
- **Ana dosya yükleme doğrulaması sağlam** — uzantı + magic-byte + streaming boyut sayacı + inkremental hash.
- **Connection pooling doğru** (pool 10 + overflow 20 + pre_ping); trigram indeksler aramalar için isabetli.
- **AI maliyet optimizasyonları bilinçli** — sayfa kırpma, regex/FlashText pre-extraction, PROCESS_CACHE.
- **Yeni frontend kodu kaliteli** — CaseList'te debounce, race koruması (`reqIdRef`), memoization.
- **Benchmark altyapısı iyi** — eksik tek şey `/confirm` DB adımları ve event-loop lag ölçümü.

---

# Önerilen Yol Haritası

| Aşama | İçerik | Tahmini efor |
|---|---|---|
| **Hafta 1** | P0'ın tamamı: CORS daralt, SlowAPIMiddleware ekle, 3 blocking çağrıyı executor'a al, `finally: db.close()`, exception sızıntısını kapat | 1-2 gün |
| **Sprint** | P1: 4 indeks + avukat filtresi JOIN'i, tarih-parse yardımcısı, Dosya Türü filtresi, ekstra ek doğrulaması, ilk pytest'ler (normalize/eşleştirme fonksiyonları) | 3-5 gün |
| **Ay** | P2: access token geçişi, AnalysisCache, code-splitting + DocCard, `LIST_REGISTRY` refactor'u, `strictNullChecks`, tek `types/case.ts` | kademeli |
| **Sürekli** | P3 hijyen maddeleri + CI'a `pip-audit`/`npm audit` | fırsat buldukça |
