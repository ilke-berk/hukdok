# Gemini SDK Migrasyon Planı — `google-generativeai` → `google-genai`

**Tarih:** 2026-07-13
**Durum:** Uygulandı (2026-07-13) — kod migre edildi (`google-genai==2.11.0`), konteynerde pytest/ruff/mypy temiz, canlı smoke test (`AQ.` anahtarla TEXT + upload/OCR yolu) başarılı. **Prod deploy bekliyor** (mesai dışı, arıza deploy'u stabilize olduktan sonra — bkz. `prod-ariza-giderme-plani-2026-07-13.md`)
**Tahmini efor:** ~½ gün kod + test, mesai dışı 1 deploy

---

## 1. Neden Gerekli?

### 1.1 Mevcut kütüphane kullanımdan kaldırıldı (EOL)

Uygulama, Gemini erişimi için `google-generativeai==0.8.5` kullanıyor. Google bu kütüphaneyi
**deprecated** ilan etti ve desteğini sonlandırdı; yerine resmi **`google-genai`** SDK'sı geçti.
Pratik sonuçları:

- Güvenlik yaması, hata düzeltmesi ve yeni özellik **gelmiyor**.
- Yeni Gemini modelleri ve API yetenekleri yalnızca yeni SDK'da garanti ediliyor;
  eski SDK herhangi bir tarihte sessizce çalışmaz hale gelebilir (aşağıdaki anahtar
  sorunu bunun ilk örneği).

### 1.2 Anahtar format uyuşmazlığı — 2026-07-13 arızasının kök nedeni

Google, yeni nesil API anahtarlarını `AQ.` önekiyle veriyor. Eski SDK'nın çoğu çağrısı modern
REST uçlarına gittiği için bu anahtarlarla çalışıyor; ancak **taramalı PDF'lerin yüklendiği
`upload_file` yolu**, eski "discovery" tabanlı istemciden geçiyor ve bu eski kanal `AQ.`
formatını tanımıyor → `API_KEY_INVALID`. Sonuç: 13 Temmuz'da 15+ belgenin AI analizi başarısız oldu.

Kısa vadeli çözüm klasik `AIza...` formatlı anahtar kullanmak; ama bu bir **köprü**, kalıcı çözüm
değil. Migrasyon sonrası tüm trafik modern uçlardan geçeceği için **her iki anahtar formatı da
çalışır** ve bu arıza sınıfı kökten kapanır.

## 2. Bize Ne Katacak?

| # | Kazanım | Somut karşılığı |
|---|---------|-----------------|
| 1 | **Anahtar format bağımsızlığı** | `AIza` da `AQ.` da çalışır; anahtar yenilerken "yanlış format" tuzağı biter, 2026-07-13 arızası tekrarlanamaz |
| 2 | **Desteklenen bağımlılık** | EOL kütüphane gider; güvenlik yamaları ve sürüm güncellemeleri yeniden alınabilir olur |
| 3 | **Yeni model erişimi** | Gelecek Gemini sürümlerine (ve mevcutların yeni yeteneklerine) SDK engeli olmadan geçilebilir; `GEMINI_MODEL_NAME` env değişkeni yeterli olur |
| 4 | **Yapılandırılmış JSON çıktı (sonraki adım)** | Yeni SDK `response_schema` ile şema zorunlu JSON destekler; bugün `_parse_gemini_json` ve `date_extractor`'daki elle ` ```json ` temizleme kırılganlığı ileride kaldırılabilir |
| 5 | **Tipli hata nesneleri** | `_gemini_call_with_retry` bugün hata **metnini** string arayarak sınıflandırıyor ("429", "overloaded"...); yeni SDK'nın `APIError.code` alanı ile retry kararı HTTP koduna bakarak verilir — daha sağlam, daha okunur |
| 6 | **Global durum yerine client nesnesi** | Eski SDK'daki `genai.configure(...)` global'i gider (bugün `email_sender` her çağrıda yeniden configure ediyor); tek `Client` nesnesi test edilebilirliği ve eşzamanlılık güvenliğini artırır |

## 3. Kapsam — Neye Dokunuyoruz?

Eski SDK yalnızca **3 dosya + requirements** içinde kullanılıyor (~12 çağrı noktası):

| Dosya | Kullanım | Zorluk |
|-------|----------|--------|
| `backend/analyzer.py` | `configure`, `upload_file`, `get_file`, `GenerativeModel(system_instruction=...)`, `generate_content_async`, retry sarmalayıcısı | **Asıl iş** — kritik analiz hattı (OCR/TEXT modları) |
| `backend/email_sender.py` | `configure` + 2 basit `generate_content(prompt)` | Kolay |
| `backend/extractors/date_extractor.py` | `configure` + 1 basit `generate_content(prompt)` | Kolay |
| `backend/requirements.txt` | `google-generativeai==0.8.5` → `google-genai==<güncel stabil>` | Tek satır |

### API eşleme tablosu (eski → yeni)

| Eski (`google.generativeai`) | Yeni (`google-genai`) |
|------------------------------|------------------------|
| `import google.generativeai as genai` + `genai.configure(api_key=K)` | `from google import genai` + `client = genai.Client(api_key=K)` (modül seviyesinde bir kez) |
| `genai.upload_file(path, mime_type=M)` | `client.files.upload(file=path, config=types.UploadFileConfig(mime_type=M))` |
| `genai.get_file(name)` | `client.files.get(name=name)` |
| `file.state.name == "PROCESSING"` | Aynı mantık; `file.state` yeni SDK'da enum — `.name` karşılaştırması implementasyonda doğrulanır |
| `genai.GenerativeModel(model_name=M, system_instruction=S)` + `model.generate_content_async(payload)` | `await client.aio.models.generate_content(model=M, contents=payload, config=types.GenerateContentConfig(system_instruction=S))` |
| `model.generate_content(prompt)` (sync) | `client.models.generate_content(model=M, contents=prompt)` |
| `response.text` | `response.text` (değişmez) |
| Hata: string içinde "429"/"503" arama | `google.genai.errors.APIError` → `e.code in (429, 503)` (string kontrolü fallback olarak kalır) |

**Değişmeyenler:** `GEMINI_API_KEY` / `GEMINI_MODEL_NAME` env değişkenleri, prompt üretimi
(`prompts.py`), `_parse_gemini_json` (şimdilik), frontend, veritabanı, SharePoint akışı.

## 4. Plan

### Faz 0 — Hazırlık

1. Bu iş **ayrı dalda** yapılır (örn. `feature/gemini-genai-sdk-migrasyonu`); 2026-07-13 arıza
   deploy'u (Faz 1-4) prod'a çıkmış ve 24 saat stabil kalmış olmalı.
2. `google-genai`'nin güncel stabil sürümü belirlenir ve pin'lenir; backend imajının Python
   sürümüyle uyumluluğu kontrol edilir.

### Faz 1 — Ortak client modülü + bağımlılık değişimi

1. `requirements.txt` güncellenir.
2. Tek noktadan `Client` üreten küçük bir modül eklenir (örn. `backend/gemini_client.py`) —
   üç dosyanın da `configure` tekrarları buraya toplanır.

### Faz 2 — `analyzer.py` migrasyonu (kritik yol)

1. `upload_to_gemini` → `client.files.upload`; `wait_for_files_active` → `client.files.get`
   (state enum karşılaştırması doğrulanır).
2. `_step_model_setup`: `GenerativeModel` kurulumu yerine model adı + `GenerateContentConfig`
   (system_instruction) hazırlanır.
3. `_gemini_call_with_retry`: `client.aio.models.generate_content` çağıracak şekilde imza
   güncellenir; hata sınıflandırması `APIError.code` üzerinden yapılır, mevcut string kontrolü
   fallback olarak korunur. Backoff/jitter mantığı **aynen kalır**.
4. OCR ve TEXT modlarının payload kurulumları (`[uploaded_file]` / metin) yeni `contents`
   parametresine uyarlanır.

### Faz 3 — Basit çağrılar

`email_sender.py` (2 çağrı) ve `date_extractor.py` (1 çağrı) ortak client'a geçirilir.

### Faz 4 — Test ve doğrulama

1. Backend pytest **konteynerde** koşulur (host Python 3.13 uyumsuz — bkz. lokal test notu);
   Gemini çağrıları mock'lanan mevcut testler geçmeli.
2. Manuel uçtan uca (lokal):
   - **Metin katmanlı PDF** → analiz özeti üretmeli (TEXT modu).
   - **Taramalı PDF** → upload + analiz çalışmalı (OCR modu) — kritik senaryo.
   - Tarih çıkarımı ve e-posta taslağı üretimi birer kez denenir.
3. Mümkünse `AQ.` formatlı anahtarla da taramalı PDF senaryosu denenir —
   migrasyonun asıl kazanımının kanıtı.

### Faz 5 — Deploy (mesai dışı)

1. PR `main`'e merge edilir.
2. Prod: `cd ~/hukdok && git pull && docker compose up -d --build`
   (`docker-compose.override.yml` sunucuda BULUNMAMALI — kontrol edilir).
3. Deploy sonrası: taramalı bir PDF ile uçtan uca onay akışı +
   `docker logs hukdok_backend --since 15m 2>&1 | grep -iE "API_KEY_INVALID|ERROR|500"` temiz olmalı.

## 5. Riskler ve Geri Dönüş

| Risk | Önlem |
|------|-------|
| Analiz hattı uygulamanın en kritik yolu — regresyon maliyeti yüksek | Arıza deploy'undan ayrı PR; Faz 4'te iki PDF tipiyle zorunlu manuel test; mesai dışı deploy |
| Yeni SDK'da dosya state/hata davranış farkları | Eşleme tablosundaki noktalar implementasyonda tek tek doğrulanır; retry fallback'i korunur |
| Geri dönüş ihtiyacı | Tek PR = tek revert; `git revert` + `docker compose up -d --build` ile eski SDK'ya dakikalar içinde dönülür (`AIza` anahtar iki SDK'da da çalıştığı için anahtar değişimi gerekmez) |

## 6. Başarı Ölçütleri

- [ ] Kod tabanında `google.generativeai` import'u kalmadı
- [ ] Taramalı PDF analizi (upload yolu) prod'da çalışıyor
- [ ] Metin PDF analizi, tarih çıkarımı ve e-posta taslağı regresyonsuz
- [ ] `AQ.` formatlı anahtarla taramalı PDF analizi başarılı (format bağımsızlığı kanıtlandı)
- [ ] Deploy sonrası 24 saat `API_KEY_INVALID` / analiz kaynaklı ERROR yok
