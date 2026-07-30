# Otonom Dava Açma — Faz 2 Başlangıç Planı (analyze endpoint)

*Tarih: 2026-07-30 · Yeni oturum için kendi kendine yeten kickoff dokümanı.*
*Eş dosyalar: [geliştirme planı](otonom-dava-acma-gelistirme-plani-2026-07-24.md) (ayrıntılı tasarım), [hazırlık raporu](otonom-dava-acma-hazirlik-raporu-2026-07-24.md), [alan-kaynak matrisi](otonom-dava-acma-alan-kaynak-matrisi-2026-07-24.md).*

## Bağlam (30 saniyede)

Hedef: belgeleri tek seferde yükle → sistem dava kartını doldurur → kullanıcı tik'lerle
onaylar → tek "Kaydet" ile dava + belge arşivi. **Faz 0 (kalibrasyon) bitti**, tüm
tasarım kararları kullanıcı onaylı (plan dokümanındaki "Kararlar" bölümü). Sıra
**Faz 2: `POST /api/case-intake/analyze` endpoint'i ve çıkarım motorunun backend'e
taşınması.** (Faz 1 — takip paneli tek-Kaydet — bağımsızdır, sonraya bırakıldı.)

## Faz 0'dan devralınanlar

`backend/calibration/` (gitignore'da, commit edilmez) altında ÇALIŞAN prototip:
- `schemas_intake.py` — kalibre edilmiş çıkarım şeması (poliçe alanları, retroaktif
  tarih, police_turu ZORUNLU/TAMAMLAYICI dahil). Faz 2'de `backend/schemas_intake.py`
  olarak taşınacak.
- `intake_prompt.py` — kalibre edilmiş prompt v2 (`get_case_intake_instruction`):
  taraf/vekil ayrımı, sigortalı-hekim zorunlu çıkarımı, sigorta ettiren ≠ sigortalı
  kuralı, sansürlü TC'yi yıldızlı aynen aktarma, belge türü odakları, regex ipucu
  enjeksiyonu. Faz 2'de `prompts.py`'a taşınacak.
- `run_calibration.py` — kalibrasyon/regresyon aracı; format dönüşümleri (UDF/".udf.zip",
  docx, odt, TIF, JPEG → PDF), ensemble + çoğunluk oyu + regex çapraz kontrol,
  ASCII-güvenli upload. Faz 2 sonrası da prompt regresyon testi olarak kalır.
- `demetler/` — gerçek test verisi: 16 poliçe, 15 tensip, 5 dilekçe.
  `results/` — ölçüm çıktıları (özellikle `policeler-e3` vs `policeler-e3-36flash`
  model kıyası).

**Ölçüm özeti:** tensip 14/14 (esas no + daireli mahkeme + açılış tarihi + taraflar),
dilekçe 5/5 (taraflar + konu + tazminat tutarları), poliçe 3.6-flash ile 16/16
(hekim, dönem, tür, şirket, kurum, limit). Regex çapraz kontrol esas_no'da 7/7 uyum.

## Kesinleşen kararlar (kullanıcı onaylı, tartışma bitti)

1. Model: **`models/gemini-3.6-flash`**, env **`GEMINI_INTAKE_MODEL`** ile (flash-lite
   sigortalı çıkarımında 9/15'te kalıyor, 3.6-flash 16/16 — plan dokümanında ölçüm var).
   Yavaşlık kabul edildi.
2. **Ensemble N=3** her belgeye; **doğrulayıcı geçiş yalnız kritik alanlara**
   (esas_no, tc_no, taraf rolleri).
3. **Sayfa kırpma YOK** — belge Gemini'ye tam gider (analyzer'ın "ilk 2 + son sayfa"
   kırpması intake'te uygulanmaz).
4. Tazminat alanları (maddi/manevi) sihirbaza **dahil**.
5. `hasar_dosya_no`/`hukuk_no` **şimdilik kapsam dışı** — kullanıcı atama yazısı
   örnekleri getirince eklenecek (şemada durabilirler, UI'ya bağlanmaz).
6. Sabit DERDEST; e-posta varsayılan kapalı toggle; max 15 belge — bunlar Faz 4-5 işi.
7. Faz 3'e **kalıcı poliçe tablosu** eklendi (`client_policies`, hekim client kaydına
   FK; migration + müvekkil kartı UI). Faz 2'yi etkilemez ama analyze çıktısındaki
   poliçe alanları bu tabloyu besleyecek şekilde eksiksiz kalmalı.
8. v2 notu: analiz-bitti bildirimi (kullanıcı beklemesin); UI'de ortalama süre
   beklentisi gösterimi Faz 5'te (ensemble=3 + 3.6-flash ile belge başına ~25-30 sn).

## Faz 2 kapsamı (plan dokümanı "İş Kalemi 1"den — efor 3–3.5 gün)

**Yeni dosyalar:**
- `backend/schemas_intake.py` — kalibrasyondaki şema (pydantic, response_schema olarak
  kullanılıyor; olduğu gibi taşı, `taraflar` rolleri Literal).
- `backend/case_intake_analyzer.py` — `analyze_intake_file_generator(...)`:
  analyzer'ın dönüşüm adımlarını (UDF/Office/görüntü→PDF, OCR kararı) yeniden
  kullanır + kendi AI adımı: `GenerateContentConfig(system_instruction=...,
  response_mime_type="application/json", response_schema=CaseIntakeExtraction)`,
  paylaşılan retry (`_gemini_call_with_retry` deseni), ensemble N=3 + alan bazlı
  çoğunluk oyu + kritik alan doğrulayıcı geçişi. PDF'i PROCESS_CACHE'e `/process`
  ile aynı hijyenle koyar.
- `backend/routes/case_intake.py` — `POST /api/case-intake/analyze`: multipart tek
  dosya, `/process` ile aynı şekilli NDJSON stream; terminal olay:
  `{"status":"complete","process_id":"<uuid>","data":{...CaseIntakeExtraction...,
  "belge_turu_kodu_tahmini":"...", "agreement":{alan:skor}}}`.
- `prompts.py`'a `get_case_intake_instruction()` (kalibrasyondan taşınır; DB bağlamı
  parametreleri: büro avukat listesi, FlashText müvekkil ipuçları, izinli yargı
  türü listesi — mevcut `get_system_instruction`'ın dynamic_lawyers deseni).

**Değişen:** `backend/api.py` (router kaydı), `backend/analyzer.py` (`_step_*`
yardımcılarının dışarıdan çağrılabilirliği — küçük imza ayarı, yarım gün bütçele).

**DB migration GEREKMİYOR** (Faz 2'de; poliçe tablosu Faz 3'te).

## Uygulama sırası önerisi

1. `schemas_intake.py` + `prompts.get_case_intake_instruction` taşı (kalibrasyon
   klasöründen kopyala, DB bağlam parametrelerini bağla).
2. `case_intake_analyzer.py`: önce tek koşu (ensemble'sız) uçtan uca; sonra ensemble
   + çoğunluk oyu (kalibrasyon script'indeki `majority_vote` saf fonksiyonu taşınabilir);
   en son kritik alan doğrulayıcı geçişi.
3. Route + NDJSON stream + PROCESS_CACHE kaydı.
4. Testler: `backend/tests/test_case_intake_analyze.py` — Gemini monkeypatch'li
   (conftest desenleri), çoğunluk oyu/doğrulayıcı saf fonksiyonları gerçek unit test.
5. Kalibrasyon script'iyle regresyon: aynı demetlerde eski/yeni çıktı kıyası.

## Test ve çalıştırma (bu repoya özgü)

- Backend pytest **KONTEYNERDE** (host py3.13 uyumsuz):
  `docker compose run --rm --entrypoint python backend -m pytest tests/ -x -q`
- Kalibrasyon/gerçek Gemini koşusu (lokal):
  `docker compose run --rm -e SSL_CERT_FILE=/app/calibration/ca_bundle.pem --entrypoint python backend calibration/run_calibration.py --model models/gemini-3.6-flash`
- Konteyner Python **3.10** — 3.12 sözdizimi (iç içe aynı-tırnak f-string) YOK.

## Tuzaklar (Faz 0'da yaşandı, tekrarlama)

- **AVG TLS araya girmesi (sadece bu PC):** konteynerden Gemini çağrısı
  `CERTIFICATE_VERIFY_FAILED` verir → `-e SSL_CERT_FILE=/app/calibration/ca_bundle.pem`.
  Prod'da (Google Cloud) yok. Üretim koduna bu bundle'ı GÖMME; api.py'daki mevcut
  `SSL_CERT_FILE` env deseni yeterli.
- **Gemini upload + Türkçe dosya adı:** SDK dosya adını HTTP başlığına taşıyor;
  ASCII dışı ad upload'ı düşürür. Üretim yolunda dosyalar zaten `tmp<uuid>` adıyla
  işleniyor (sorun yok) ama display_name'e kullanıcı dosya adı verilecekse
  ASCII'ye indirgemek şart (kalibrasyon script'indeki `ascii_safe_copy`/NFKD deseni).
- **UDF `.udf.zip` adıyla gelebilir** (UDF zaten zip'tir) — uzantı kontrolünde
  `name.endswith(".udf.zip")` istisnası (file_utils beyaz listesine eklenmeli mi →
  Faz 2'de karar).
- Model kaçak çıktı üretebilir (flash-lite'ta 237k karakterlik özet + kırpık JSON
  görüldü) — ensemble koşusunda tek bozuk koşu belgeyi öldürmemeli, kalanlarla oyla.
- `docker compose run` için `--entrypoint` şart, yoksa entrypoint script API server
  başlatır. PowerShell 5.1'de Türkçe içerikli dosya işlemleri için daima Edit/Write
  tool (Get/Set-Content çift kodlar).

## Faz 2 çıkış kriterleri

1. `/api/case-intake/analyze` gerçek bir tensip PDF'iyle NDJSON stream edip
   `complete` olayında dolu `CaseIntakeExtraction` + `agreement` skorları dönüyor.
2. UDF, docx, TIF, JPEG girişleri de aynı akıştan geçiyor.
3. Ensemble + doğrulayıcı saf fonksiyonları unit testli; route testi monkeypatch'li.
4. Kalibrasyon demetlerinde regresyon koşusu: Faz 0 ölçümlerinden sapma yok
   (tensip 14/14, poliçe 16/16 hekim).
5. `GEMINI_INTAKE_MODEL` env'i `.env.example`/dokümana eklendi (varsayılan
   `models/gemini-3.6-flash`).

## Faz 2 sonrası sıra

Faz 3: merge servisi + DB zenginleştirme + **kalıcı poliçe tablosu** (3.5–4.5 g) →
Faz 4: commit (1 g) → Faz 5: sihirbaz UI (4–5 g) → Faz 1 takip paneli araya her an
alınabilir → Faz 6: sertleştirme.

## Commit durumu uyarısı

Dört docs dosyası (bu dosya dahil) + `.gitignore` değişikliği henüz commit'lenmedi.
Faz 2 oturumunun ilk işi bunları commit'lemek olabilir (calibration/ klasörü
gitignore'da — commit'e girmez, girmemeli: gerçek müvekkil verisi içeriyor).
