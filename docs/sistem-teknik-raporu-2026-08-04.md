# HukuDok — Kapsamlı Sistem Teknik Raporu

**Tarih:** 2026-08-04
**Hedef okur:** Ekip üyeleri ve onların AI asistanları. Bu rapor bir insan-özeti değil, makine-okur referans belgesidir: dosya:satır referansları, gerçek kod listeleri ve kesin davranış tanımları içerir.
**Kapsam:** Deponun `main` dalındaki güncel durum (lokal main, Faz 7 dahil). Prod'da o an hangi commit'in koştuğu için `docs/` altındaki deploy kayıtlarına bakın.
**Temel amaç:** Ekip eski arşiv sisteminin zihinsel modeliyle düşünmeye devam ediyor. Bu rapor, **eski sistemden kalan hiçbir zorunluluğun (TKU numarası, klasörleme, elle numaralandırma, klasör-bazlı arşivleme) yeni sistemde var olmadığını** kod kanıtlarıyla ortaya koyar ve yeni sistemin gerçekte nasıl çalıştığını uçtan uca tanımlar.

---

## 0. EN ÖNEMLİ BÖLÜM — Eski sistem varsayımları vs. yeni sistem gerçeği

AI asistanları için talimat niteliğinde: kullanıcı (ekip üyesi) aşağıdaki eski-sistem kavramlarından bahsederse, yeni sistemdeki karşılığını bu tabloya göre düzeltin.

| Eski sistem varsayımı | Yeni sistem gerçeği | Kanıt |
|---|---|---|
| "Belgeye TKU numarası verilir" | **TKU artık HukuDok'ta yalnız TARİHSEL/GRUP alanı olarak yaşar.** 2026-08-05 mutabakatıyla `cases.tku_no` (olay grup anahtarı, unique değil) ve `cases.sistem_no` (eski sistem kayıt kimliği, unique) kolonları eklendi — yalnız DB + arama, UI'da gösterilmez, `Full_Rapor_TKU.xlsx` aktarımında dolacak. Numara ÜRETİMİNDE hiçbir rolü yoktur: kimlik `cases.id`, ofis no 5 bloklu `tracking_no`, belge sayacı 9 haneli `ofis_dosya_no`. Değerlendirme §6.4, mutabakat §6.6. | §5, §6, §6.4, §6.6 |
| "Belge, müvekkil/dava klasörüne konur; klasör yapısı kurulmalı" | **HukuDok ARŞİVİ için klasörleme tamamen kalktı.** SharePoint'te yalnız İKİ düz kök klasör var: `01_HAM_ARSIV` (dokunulmamış orijinal) ve `02_YEDEK_ARSIV` (işlenmiş PDF/A-2b). Müvekkil/dava/yıl alt klasörü YOK; belgenin "hangi davaya ait olduğu" bilgisi **Postgres `case_documents` tablosunda** tutulur. ÖNEMLİ NÜANS: bu yalnız HukuDok arşivi içindir — büronun ortak dosya sunucusundaki ÇALIŞMA ALANI (taslaklar, UDF çalışma dosyaları, masraf evrakı, arşive girmemiş yaşayan belgeler) HukuDok kapsamı dışındadır ve kendi klasör düzeniyle yaşamaya devam eder; büronun klasör adlandırma çalışmaları o alan için geçerliliğini korur. | §3.3 |
| "Belgeyi bulmak için SharePoint'te klasörlerde/aramada gezilir" | **Arama SharePoint'te YAPILMAZ.** Graph search endpoint'i kodda hiç kullanılmıyor; `children` listeleme de yok. Tüm arama/filtreleme Postgres üzerinden (ILIKE + trigram index). SharePoint'ten dosya, DB'deki `stored_filename` ile **doğrudan yol** üzerinden çekilir. Kullanıcı belgeye web uygulamasından erişir (backend proxy indirme). | §7 |
| "Dosya adı elle, büro kuralına göre yazılır" | Dosya adını **AI analizi + otomatik format** üretir: `YYYY-MM-DD_TÜR_YY-ESASNO_A.Soyad.pdf`. Kullanıcı onay ekranında düzeltebilir ama kural sistemseldir. | §5.1 |
| "Numara atlamasın diye sayaç defteri/Excel tutulur" | Belge sayacı SharePoint `Counter` listesinde tek merkezi kayıttır, ETag tabanlı optimistic concurrency ile atomik artar; dava sırası (`tracking_no` 3. blok) DB'den `max+1` ile önerilir. Elle sayaç takibi gereksiz ve yanlıştır. | §6 |
| "Arşive girmeden önce evrak fiziksel/elle sınıflandırılır" | Sınıflandırma (belge türü, taraflar, tarih, esas no, mahkeme) **Gemini AI** ile otomatik çıkarılır; kullanıcı yalnız onaylar/düzeltir. 127 kayıtlı doctype kod listesi vardır (§5.3). | §4 |
| "Eski dosya numarasıyla arama yapamam" | Eski sistem numaraları `cases.klasor_no_2` alanına taşındı ("Eski sistem no — gizli, aranabilir", `backend/models.py:36`); trigram index'li ve arama motoruna dahil (`case_manager.py:305`). Eski numarayla arama ÇALIŞIR ama yeni kayıt üretiminde hiçbir rol oynamaz. | §8.2 |
| "SharePoint listelerine (log, metadata) kayıt düşülür" | SharePoint list kullanımı tek canlı öğeye indi: `Counter` (sayaç). `log` listesi ölü koddur (LogManager instance ediliyor ama hiçbir yerden çağrılmıyor); belge kütüphanesi metadata kolonlarına da hiçbir şey yazılmıyor (`_update_list_item_fields` ölü yol). Tüm metadata Postgres'tedir. | §3.4 |
| "İki SharePoint sitesi var (eski arşiv + yükleme)" | Tek site modu. `config_type="upload"` / `UPLOAD_SHAREPOINT_*` env ailesi eski iki-site mimarisinin kalıntısıdır ve kod tarafından KULLANILMAZ (yalnız log satırı kalmış). | §14 |

**Özet paradigma:** Eski sistem "klasör + numara + liste" üçlüsüyle SharePoint-merkezliydi. Yeni sistem **veritabanı-merkezli**dir: SharePoint yalnızca *binary depo* (2 düz klasör) + *tek sayaç*tır; kimlik, ilişki, metadata ve arama tamamen Postgres'tedir.

---

## 1. Sistem kimliği ve bileşenler

**HukuDok Automator** — hukuk bürosu (Hanyaloğlu-Acar + LexisBio ortak havuzu) belge otomasyon ve dava takip sistemi.

| Bileşen | Teknoloji | Konum |
|---|---|---|
| Backend | Python 3.10, FastAPI, uvicorn | `backend/`, container `hukdok_backend`, port 127.0.0.1:8001 |
| Frontend | React 18 + TypeScript + Vite + shadcn/ui + Tailwind + react-query + MSAL | `frontend/`, nginx container, port 8080 |
| Veritabanı | PostgreSQL 15 (zorunlu; SQLite desteği kaldırıldı, `database.py:23-30`) | container `hukudok-postgres`, 127.0.0.1:5432 |
| Belge deposu | SharePoint (Microsoft Graph API, app-only) | tek site, tek drive ("Belgeler"), 2 düz klasör |
| AI | Google Gemini (`google-genai` SDK 2.11.0) | analiz: `GEMINI_MODEL_NAME` (flash-lite); intake: `GEMINI_INTAKE_MODEL` (models/gemini-3.6-flash) |
| PDF motorları | Ghostscript (PDF/A-2b), LibreOffice (Office/HTML→PDF), ReportLab (UDF render), Pillow | backend imajı içinde |
| E-posta | Microsoft Graph `sendMail` (aynı app-only credential) | `backend/email_sender.py` |
| Dış tüketici | **hukukbot** (ikinci stack, `~/hukukbot-ui`) — `/export` API + webhook | Docker `hukuk_shared` network üzerinden |

**Prod:** Google Cloud VM (Frankfurt, 35.234.119.194), domain `hukukoid.com` (Namecheap). İki katmanlı nginx: host nginx (TLS :443) → container nginx (HTTP :8080) → backend :8001. Deploy: SSH + `docker compose up -d --build` (frontend için `--build` şart; VITE_* değerleri build-time gömülür, `frontend/Dockerfile:14-16`).

---

## 2. Uçtan uca ana akış (belge arşivleme)

```
Kullanıcı (web UI /upload)
  │ dosya (pdf/udf/tif/jpg/png/docx/doc/xlsx/xls, max 50 MB)
  ▼
POST /process  ──────────────── routes/processing.py:328-474
  ├─ magic-byte doğrulama (file_utils.validate_file_type)
  ├─ paralel: SharePoint Counter oku (10s timeout → "TIMEOUT___")
  ├─ analyze_file_generator (analyzer.py):
  │    UDF→PDF, Office/Görüntü→PDF, sayfa kırpma (ilk 2 + son anlamlı),
  │    OCR/TEXT kararı, regex ön-çıkarım (tarih/esas no/mahkeme/müvekkil),
  │    Gemini çağrısı → {tarih, muvekkil, esas_no, court, ozet, ...}
  ├─ find_matching_case → suggested_case (dava önerisi)
  └─ NDJSON stream yanıt; dönüştürülmüş PDF → PROCESS_CACHE (TTL 30 dk)
  ▼
Kullanıcı onay ekranı: alanları düzeltir, dosya adı otomatik üretilir
  ▼
POST /confirm ──────────────── routes/processing.py:504-724
  ├─ tenant/dava sahipliği doğrulaması
  ├─ counter +1 (background, ETag optimistic concurrency)
  ├─ Ghostscript PDF/A-2b dönüşümü  ← BAŞARISIZSA HİÇBİR ARŞİVE YAZILMAZ (500)
  ├─ case_documents satırı (DB) → doc_id
  ├─ background upload 1: ham orijinal → SharePoint 01_HAM_ARSIV
  │    ad: YYYY-MM-DD_<sanitize(orijinal_ad)>
  ├─ background upload 2: PDF/A → SharePoint 02_YEDEK_ARSIV
  │    ad: YYYY-MM-DD_TÜR_YY-ESASNO_A.Soyad.pdf
  │    upload sonrası webUrl → case_documents.sharepoint_url
  │    URL commit başarılıysa → export_outbox satırı + hukukbot webhook
  ├─ opsiyonel: avukata bildirim e-postası (Graph sendMail)
  └─ dava bağlıysa: otomatik durum güncelleme + zenginleştirme + duruşma tarihi
```

Kritik garanti (`services/document_pipeline.py:279,314-316`): "ham upload, PDF/A başarılı olduktan SONRA kuyruklanır — iki arşiv tutarlı kalır". Aynı isimli dosya SharePoint'te `@microsoft.graph.conflictBehavior: replace` ile **üzerine yazılır** (`sharepoint_uploader_graph.py:107`); versiyonlama SharePoint'in kendi version history'sine bırakılmıştır.

---

## 3. Depolama ve arşivleme mimarisi (SharePoint)

### 3.1 Kimlik doğrulama
- **App-only / client credentials** (`backend/sharepoint/auth_graph.py:51-72`): `msal.ConfidentialClientApplication`, scope `https://graph.microsoft.com/.default`. Son kullanıcının Microsoft hesabının SharePoint erişimi olması GEREKMEZ — tüm erişim uygulamanın kimliğiyle yapılır.
- Env: `SHAREPOINT_TENANT_ID`, `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_CLIENT_SECRET`.
- Aynı credential üç Graph yüzeyini kullanır: Sites/Drives (dosya), Lists (sayaç), Mail.Send (e-posta). Gerekli app izinleri: `Sites.ReadWrite.All`, `Mail.Send` (+ scriptler için `Mail.Read`).

### 3.2 Site/drive çözümleme
`sharepoint_uploader_graph.py:37-93`: `SHAREPOINT_SITE_URL`'den hostname+path → `GET /sites/{hostname}:{path}` → site_id → `GET /sites/{id}/drives` → adı `SP_DRIVE_NAME` (default **"Belgeler"**, fallback "Documents") olan drive. Site/drive ID'leri env'de tutulmaz, runtime'da çözülür ve `lru_cache` ile saklanır.
⚠️ `.env.example`'daki `SHAREPOINT_DRIVE_NAME` ve `SHAREPOINT_TARGET_FOLDER` **hiçbir yerde okunmayan ölü env'lerdir**; kod `SP_DRIVE_NAME` okur.

### 3.3 Klasör yapısı — düz, iki klasör, hepsi bu

| Klasör (env ile değişir, default) | İçerik | Kim yazar | Kim okur |
|---|---|---|---|
| `01_HAM_ARSIV` (`SHAREPOINT_FOLDER_HAM_NAME`) | Dokunulmamış orijinal dosya (UDF, Office, görüntü dahil), adı `YYYY-MM-DD_<orijinal>` | `/confirm` ve intake commit/apply | **HİÇ KİMSE** — koddan hiç okunmuyor; salt felaket yedeği |
| `02_YEDEK_ARSIV` (`SHAREPOINT_FOLDER_ISLENMIS_NAME`) | (1) İşlenmiş PDF/A-2b belgeler, (2) `technical_log_*.json` teknik log dökümleri | `/confirm`, intake, TechnicalLogger | belge indirme proxy'si, e-posta yeniden gönderimi, hukukbot export |

- Adına rağmen `02_YEDEK_ARSIV` **birincil işlenmiş belge deposudur** — tüm indirme/servis buradan yapılır.
- Alt klasör YOK. Tenant ayrımı klasör düzeyinde YOK (bilinçli: iki büro ortak havuz çalışıyor; tüm kayıtlar `tenant_id=NULL` paylaşımlı).
- Klasörler kod tarafından OLUŞTURULMAZ — kütüphanede önceden var olmalıdır.
- Upload mekaniği: ≤4 MB tek PUT; >4 MB upload session + 5 MB chunk'lar (`sharepoint_uploader_graph.py:118-224`).

### 3.4 SharePoint listeleri — tek canlı liste
| Liste | Durum | Detay |
|---|---|---|
| `Counter` (`SHAREPOINT_COUNTER_LIST_NAME`) | **CANLI — tek merkezi SharePoint bağımlılığı** | Tek item; kolonlar `Current_Count`/`Last_Updated`/`Updated_By` (internal adlar runtime tespit, `counter_manager.py:55-92`). 9 haneye zfill'li belge sayacı. ETag `If-Match` + 412'de 3 retry ile atomik artırım. SharePoint erişilemezse fallback YOK (exception). |
| `log` (`SHAREPOINT_LOG_LIST_NAME`) | **ÖLÜ** | `LogManager` `api.py:86-89`'da instance ediliyor ama `init_log/complete_log/fail_log` hiçbir yerden çağrılmıyor. Listeye artık yazılmıyor. |
| Belge kütüphanesi metadata kolonları | **ÖLÜ** | `_update_list_item_fields` mevcut ama hiçbir upload çağrısı `metadata=` geçmiyor. Kolonlara hiçbir şey yazılmıyor. |

### 3.5 Teknik loglar
`TechnicalLogger` (`managers/log_manager.py:207-319`): RAM buffer (deque maxlen 2000, mesaj 4000 karakter; 2026-07-29 OOM sonrası tavanlar). TCKN/kart/e-posta maskelenir. ERROR/CRITICAL'da ayrı thread'de SharePoint'e senkron: dosya `technical_log_{YYYYMMDD_HHMMSS}_{hostname}.json` → **`02_YEDEK_ARSIV`**. Hata teşhisi için ERROR kayıtları `docker logs`'ta DEĞİL, SharePoint `02_YEDEK_ARSIV` içindeki bu JSON'lardadır (SharePoint search endpoint'i geride kalabilir; `children` ile listelemek daha güvenilir — operasyon notu).

---

## 4. AI analizi (belge)

- Client: thread-safe singleton `genai.Client` (`gemini_client.py:13-39`); anahtar `vault.get_secret("GEMINI_API_KEY")` (Docker'da keyring null-backend → fiilen `.env`).
- Model: `GEMINI_MODEL_NAME` env **zorunlu** (yoksa import hatası, `analyzer.py:54-60`). Örnek: `gemini-2.5-flash-lite` ailesi. Intake ayrı model: `GEMINI_INTAKE_MODEL` default `models/gemini-3.6-flash` (kalibrasyonla seçildi: sigortalı çıkarımı flash-lite 9/15 vs 3.6-flash 16/16, `case_intake_analyzer.py:9-11`).
- Retry: 429 base 5s / 503 base 1s, exponential+jitter, max 5 (`analyzer.py:69-115`).
- Hat adımları (`analyzer.py:1084+`): UDF→PDF → format dönüşümü → sayfa kırpma (`extract_key_pages`: >3 sayfada ilk 2 + son anlamlı sayfa; `MAX_PDF_PAGES=500` üstü ret) → OCR/TEXT kararı (`load_and_analyze_pdf`: metin <50 char → OCR; mojibake tespiti; hibrit içerik) → regex ön-çıkarım (tarih/esas no/mahkeme extractors + FlashText müvekkil arama) → dinamik prompt (VERIFICATION modu: aday listesinden seç / DISCOVERY modu) → Gemini (OCR modunda `files.upload`) → JSON parse + alan çözümü → Gemini dosyası silinir.
- LLM çıktı şeması (`prompts.py:201-212`): `tarih, muvekkil_adi, muvekkiller[], belgede_gecen_isimler[], esas_no, court, durum, ozet` (+ duruşma belgelerinde `sonraki_durusma_tarihi/saati`).
- OCR modunda subprocess/Gemini hataları ve `UnicodeDecodeError` (ValueError alt sınıfı!) için geniş except kullanılır — dar `except ValueError` bu hatayı DELMİŞTİ (2026-07-13 arızası); yeni kod geniş yakalar (`routes/case_intake.py:798-801` gerekçe yorumu).

---

## 5. Adlandırma ve belge türü sistemi

### 5.1 İşlenmiş dosya adı formatı (stored_filename)
**`YYYY-MM-DD_TÜR_YY-ESASNO_A.Soyad[.pdf]`** — üretim FRONTEND'dedir: `frontend/src/components/AnalysisResults.tsx:394-419` (`generateFilename`); backend eşdeğeri müvekkil için `analyzer.py:987-1008`.

| Blok | Kural | Boş fallback |
|---|---|---|
| Tarih | belge tarihi ISO | `XXXX-XX-XX` |
| TÜR | doctype kodu, trailing `_` padding kırpılır (`AYM-KRR______`→`AYM-KRR`) | `XXX` |
| Esas no | `/(\d{2,4})[/\-\s](\d+)/` → yıl son 2 hane: `2021/413`→`21-413` | `XX-XX` |
| Ad | **karşı taraf** adı; kişi → `İ.Soyad` (unvanlar temizlenir), çoklu taraf → `_vd`, şirket → sektör kelimesi mantığı (A.Ş/LTD/SİGORTA/BANKA... tespiti) | `XXXXX` |

- HAM arşiv adı: `YYYY-MM-DD_<sanitize_filename(orijinal)>` (`processing.py:583-585`).
- `sanitize_filename` (`file_utils.py:51-90`): `.udf.zip`→`.udf`, uzantı whitelist, 200 char sınır, boşluk→`_`, `[_.]{2,}` gövdede tekilleştirilir.
- 9 haneli `ofis_dosya_no` sayacı `/process` yanıtında döner ama **dosya adına girmez**.

### 5.2 Doctype kod normalizasyonu — KRİTİK TUZAK
Kodlar DB'de `_` ile **14 karaktere pad'lidir** (`ARA-KRR_______`). Karşılaştırma yapmadan önce daima normalize edin:
```python
# backend/file_utils.py:261-269
def _normalize_doctype_code(code): return re.sub(r"[^A-Z0-9]", "", (code or "").upper())
# "ARA-KRR" == "ARA-KRR_______" == "ARAKRR"
```
Normalize edilmeden yapılan prefix/eşitlik karşılaştırmaları kısaltma sızmasına yol açar (geçmişte yaşanmış bug sınıfı).

### 5.3 Doctype kod listesi — TAM (127 kayıt)
Kaynak: `doctypes` tablosu; runtime `DynamicConfig.get_doctypes()`. Admin panelinden düzenlenebilir (liste sabit değildir; aşağıdaki döküm 2026-08-04 anlık görüntüsüdür).

| Kod (pad'li) | Ad |
|---|---|
| `ACILMAMIS-KRR_` | Davanın Açılmamış Sayılmasına Karar |
| `AYM-KRR_______` | Anayasa Mahkemesi Kararı |
| `ARA-KRR_______` | Ara Karar |
| `ARA-KRR-RUCU__` | Ara Karardan Rücu |
| `ARB-DAVET_____` | Arabuluculuk Davet Mektubu |
| `ARB-TUTNK-ILK_` | Arabuluculuk İlk Oturum Tutanağı |
| `ARB-TUTNK-SON_` | Arabuluculuk Son Oturum Tutanağı |
| `ATAMA_________` | Atama Kararı / Yazısı |
| `ATK-EKSIK-EVR_` | Adli Tıp Kurumu (ATK) Eksik Evrak Yazısı |
| `ATK-RPR_______` | Adli Tıp Kurumu (ATK) Raporu |
| `AYIRMA-KRR____` | Davaların Ayrılması Kararı (Tefrik) |
| `AZIL__________` | Azilname |
| `BEKLETICI-MSL_` | Bekletici Mesele Kararı |
| `BEYAN_________` | Beyan Dilekçesi |
| `BLRKSI-RPR-EK_` | Bilirkişi Ek Raporu |
| `BILIRKISI-RPR_` | Bilirkişi Raporu |
| `BLRKSI-TUTNK__` | Bilirkişi Tutanağı |
| `BIRLESTRM-KRR_` | Davaların Birleştirilmesi Kararı |
| `CEVAP-CVP_____` | Cevaba Cevap Dilekçesi (Replik) |
| `CEVAP_________` | Cevap Dilekçesi |
| `DANISMA_______` | Danışma / Görüş Yazısı |
| `DANISTAY-KRR__` | Danıştay Kararı |
| `DAVA-DLK______` | Dava Dilekçesi |
| `DEG-IS-KRR____` | Değişik İş Kararı |
| `DELIL-LST_____` | Delil Listesi |
| `DELIL-EK______` | Delil Eki / Sunumu |
| `DILEKCE_______` | Genel Dilekçe |
| `DILEKCE-RED___` | Dilekçenin Reddi Kararı |
| `EK-KRR________` | Ek Karar |
| `EMSAL-KRR_____` | Emsal Karar |
| `EPIKRIZ_______` | Epikriz Raporu (Hasta Çıkış Özeti) |
| `FERAGAT_______` | Feragat Dilekçesi |
| `FERI-M-KRR____` | Feri Müdahillik Kararı |
| `FERI-M-TLB____` | Feri Müdahillik Talebi |
| `GEREKCELI-KRR_` | Gerekçeli Karar |
| `GOREV-KRR_____` | Görevsizlik / Yetkisizlik Kararı |
| `HACZ-TLB______` | Haciz Talebi |
| `HACZ-TUTNK____` | Haciz Tutanağı |
| `HAKM-KRR______` | Hakim Kararı / Havalesi |
| `HASAR-IHB_____` | Hasar İhbarı |
| `HASTA-BSVR____` | Hasta Başvuru Formu |
| `HASTA-KY______` | Hasta Kayıtları |
| `HEKIM-BYN_____` | Hekim Beyanı |
| `ISLAH_________` | Islah Dilekçesi |
| `ISLAHA-BYN____` | Islaha Karşı Beyan |
| `IBRANAME______` | İbraname |
| `ICRA-DIGR_____` | Diğer İcra Evrakları |
| `ICRA-EMR______` | İcra Emri |
| `IDARI-BASVR___` | İdari Başvuru |
| `IDDIANME______` | İddianame |
| `IDDIANME-KABL_` | İddianamenin Kabulü Kararı |
| `IFADE_________` | İfade Tutanağı |
| `IHBR-KRR______` | İhbar Kararı |
| `IHTAR_________` | İhtarname |
| `IHTAR-CVB_____` | İhtarnamenin Cevabı |
| `IHTYT-HCZ-KRR_` | İhtiyati Haciz Kararı |
| `IHTYT-HCZ-TALB` | İhtiyati Haciz Talebi |
| `IHT-HCZ-ITRZ__` | İhtiyati Hacize İtiraz |
| `IHT-TED-KRR___` | İhtiyati Tedbir Kararı |
| `IHT-TED-TALB__` | İhtiyati Tedbir Talebi |
| `IHT-TED-ITRZ__` | İhtiyati Tedbire İtiraz |
| `ISTINAF-BSVR__` | İstinaf Başvuru Dilekçesi |
| `ISTINAF-CVB___` | İstinafa Cevap Dilekçesi |
| `ISTINAF-KRR___` | İstinaf Kararı |
| `KAPAK-HESB____` | Dosya Kapak Hesabı |
| `KRR_DZLTM-TLB_` | Karar Düzeltme Talebi |
| `KRR_DZLTM-CVB_` | Karar Düzeltmeye Cevap |
| `KRR_DZLTM-KRR_` | Karar Düzeltme Kararı |
| `KESINLESME____` | Kesinleşme Şerhi |
| `KESIF-TUTNK___` | Keşif Tutanağı |
| `KRONOLOJI_____` | Kronoloji Raporu |
| `LEXIS-RPR_____` | Lexis Raporu (Otomasyon Raporu) |
| `MAAS-HCZ-CVB__` | Maaş Haczi Cevabı |
| `MAIL-GEL______` | Gelen E-Posta |
| `MAIL-GID______` | Giden E-Posta |
| `MALULYT-RPR-EK` | Maluliyet Raporu Eki |
| `MALULYT-RPR___` | Maluliyet Raporu |
| `MAZERET_______` | Mazeret Dilekçesi |
| `MEHIL-VESK____` | Mehil Vesikası |
| `MEVZUAT_______` | Mevzuat / Kanun Maddesi |
| `MSK-KRR_______` | Mesleki Sorumluluk Kurulu Kararı (veya Yüksek Sağlık Şurası) |
| `MUHTIRA_______` | Muhtıra |
| `MUTALAA_______` | Mütalaa (Bilirkişi veya Savcılık) |
| `MUTALAA-SUNM__` | Mütalaa Sunumu / Beyanı |
| `MUTALAA-TLB___` | Mütalaa Talebi |
| `MUVEKKIL-YZS__` | Müvekkil ile Yazışma |
| `MUZEKKERE_____` | Müzekkere |
| `MUZEKKERE-CVB_` | Müzekkere Cevabı |
| `ONAM__________` | Onam Formu (Aydınlatılmış Onam) |
| `ODME-DEKNT____` | Ödeme Dekontu |
| `ODME-EMR______` | Ödeme Emri |
| `POLICE________` | Sigorta Poliçesi |
| `RPR-ITIRZ_____` | Rapora İtiraz Dilekçesi |
| `SAVUNMA_______` | Savunma Dilekçesi |
| `SIGRT-YZSMA___` | Sigorta Şirketi Yazışması |
| `SON-SAVNM_____` | Esasa İlişkin Son Savunma |
| `SOZLS_________` | Sözleşme |
| `SOZL-INCLM____` | Sözlü İnceleme / Duruşma |
| `SULH-PROTKL___` | Sulh Protokolü |
| `SURE-TUTM_____` | Süre Tutum Dilekçesi |
| `SURE-UZTM_____` | Süre Uzatım Talebi |
| `SURE-UZT-KRR__` | Süre Uzatım Kararı |
| `SIKAYET_______` | Şikayet Dilekçesi |
| `TAKIP-TLB_____` | Takip Talebi (İcra) |
| `TAKIPSIZLK-KRR` | Takipsizlik Kararı (KYOK) |
| `TANIK-IFD_____` | Tanık İfadesi |
| `TANIK-LST_____` | Tanık Listesi |
| `TANIK-BYN_____` | Tanığa Karşı Beyan |
| `TAPU__________` | Tapu Kaydı / Senedi |
| `TAZMNT-EK-RPR_` | Tazminat Ek Raporu (Aktüerya) |
| `TAZMNT-RPR____` | Tazminat Hesap Raporu (Aktüerya) |
| `TEBLIGAT______` | Tebligat Parçası / Mazbata |
| `TEHIR-ICR-KRR_` | Tehir-i İcra Kararı |
| `TEHIR-ICR-TLB_` | Tehir-i İcra Talebi |
| `TEMINAT_______` | Teminat Mektubu / Makbuzu |
| `TEMYIZ-BSVR___` | Temyiz Başvuru Dilekçesi |
| `TENSIP________` | Tensip Zaptı |
| `UYAP-KAYD_____` | UYAP Kaydı / Ekran Görüntüsü |
| `VEK-SZLS______` | Vekalet Sözleşmesi (Ücret Sözleşmesi) |
| `VU-TEKLF______` | Vaka Üstlenme Teklifi / Vekalet Ücreti Teklifi |
| `VEKALET_______` | Vekaletname |
| `YARGITAY-KRR__` | Yargıtay Kararı |
| `YENILEME______` | Yenileme Dilekçesi |
| `YETKI-KRR_____` | Yetki Belgesi / Yetki Kararı |
| `YD-KRR________` | Yürütmeyi Durdurma (YD) Kararı |
| `ZABIT_________` | Duruşma Zaptı / Tutanak |
| `DIGER_________` | Diğer / Tasnif Dışı |

Alt kümeler:
- **Duruşma tarihi taşıyabilenler** (`constants.py:12`): kod içinde `DURUSMA|ZABIT|TUTANAK|TENSIP|TEBLIG` geçenler (contains kontrolü — padding sorun olmaz).
- **Hukukbot export allowlist** (`HUKDOK_EXPORT_TYPES`, 12 kod): `GEREKCELI-KRR, ARA-KRR, EK-KRR, ISTINAF-KRR, YARGITAY-KRR, DANISTAY-KRR, AYM-KRR, KRR_DZLTM-KRR, EMSAL-KRR, BILIRKISI-RPR, BLRKSI-RPR-EK, ATK-RPR` (gerekçeler: `docs/hukukbot-aktarim/KOD_LISTESI.md`).
- **Otomatik dava durumu haritası** (`processing.py:49-55`, prefix eşleşmesi): `KARAR→KARAR, TEMYIZ→TEMYIZ, INFAZ→INFAZ, FERAGAT→KAPALI, ISLAH→DERDEST`.

---

## 6. Numaralandırma sistemleri

Yeni sistemde İKİ bağımsız numara vardır; ikisi de otomatiktir:

### 6.1 Belge sayacı — `ofis_dosya_no` (9 hane)
SharePoint `Counter` listesindeki tek global sayaç. `/process` sırasında okunur (`"000000042"` formatı), `/confirm`'de background task ile +1. Detay §3.4. Dosya adına girmez; UI'da bilgi olarak gösterilir.

### 6.2 Dava/ofis numarası — `tracking_no` (5 blok)
`cases.tracking_no` — unique, NOT NULL. Format: **`B1.B2.B3.B4.B5`**, doğrulama regex'i (`caseNumberUtils.ts:200`):
`^[A-Z0-9]{2}\.[A-Z0-9_.]{10}\.[A-Z0-9]{4}\.[A-Z0-9]{5}\.[A-Z0-9]{5}$`

| Blok | İçerik | Değerler |
|---|---|---|
| B1 (2) | Müvekkil kategori kodu | `Doktor→D1, Sağlık Çalışanı→D2, Özel Hastane→H2, Sigorta→S0, Hasta→H1, Diğer→X1`; sigorta şirketine özgü: `AK→S1, ANADOLU→S2, AXA→S3, CORPUS/QUICK→S4, EUREKO→S5, NIPPON→S6, SOMPO→S7` |
| B2 (10) | İsim bloğu, `.` ile pad | Kişi: `{İlkİsimBaşHarfi}_{SOYAD}` (örn. `I_KUTLUK..`); kurum: jenerik kelimeler (SIGORTA/ANONIM/LTD/...) atılıp ilk anlamlı kelime (örn. `ANADOLU...`) |
| B3 (4) | Müvekkil-içi sıra no, zfill(4) | `GET /api/cases/client-sequence` → **max+1** (COUNT değil! §6.3) |
| B4 (5) | Yargı süreci | `Hukuk→HUKUK, İdari Yargı→IDARI, Ceza→CEZAA, İcra→ICRAA, Arabuluculuk→ARABU, Savcılık→SAVCI`; script'te ek: `IDARE, TAHKM, VERGI, DANIS`; bilinmeyen→`HUKUK` |
| B5 (5) | Hizmet türü bitmask | bit 0=Rapor, 1=Danışmanlık, 2=Dava, 3=İcra, 4=Yazışma; default `00000`; `Case.service_type` olarak da saklanır |

**İsim bloğu müvekkil seçimi kategori önceliğiyle yapılır** (İLK müvekkil değil; kullanıcı bilinçli onayladı, değiştirmeyin): `Doktor(0) > Sağlık Çalışanı(1) > Hasta(2) > Bireysel(3) > kategorisiz(4) > diğer(6) > sigorta(10)` — en düşük değer kazanır (`pickNameClient`, `caseNumberUtils.ts:143-160`). B1 için `bestCategoryCode`: S1-S7 > S0 > D1 > D2 > H2 > H1 > X1.

⚠️ Üretim mantığı YALNIZ frontend'dedir (`frontend/src/lib/caseNumberUtils.ts`); backend yalnız sıra önerir ve `unique` kısıtıyla çakışmayı 409 olarak reddeder. `scripts/retag_tracking_nos.py` geriye dönük yeniden etiketleme için ayrı bir kopya taşır.

### 6.3 Sıra üretimi ve çakışma tarihi
- `GET /api/cases/client-sequence` (`routes/cases.py:107-153`): tercihen `name_block` (B2) ile `substr(tracking_no,4,10)` eşleşen kayıtların **max sırası + 1**; fallback müvekkil adı ILIKE prefix.
- Tarihçe: eski COUNT-tabanlı öneri, silinen/eşleşmeyen kayıtlarda dolu numara önerip UniqueViolation/500 üretiyordu (2026-07-16 arızası); Faz 6.3'te max+1'e geçildi. Regex'e uymayan eski/serbest numaralar sayımda YOK SAYILIR.
- Çakışmada: DB unique ihlali → `[TRACKING_NO_COLLISION]` teknik logu + HTTP 409 "Bu ofis numarası zaten kayıtlı".
- Eski sistem numarası `klasor_no_2`'dedir ve tracking_no üretiminde HİÇBİR rol oynamaz.

### 6.4 Büro "Numaralandırma Yeniden Tasarımı" bilgi notunun değerlendirmesi (2026-08-03)

Kaynak: `HUKDOK_Bilgi_Notu_Numaralandirma_2026-08-03.docx` (Hanyaloğlu-Acar, "tartışmaya açık taslak"). Önerinin özü: üç katmanlı kimlik — MüvekkilNo (5 hane), TKU (olay/vaka numarası), D-No (`D-01843-2` = sabit önek + 5 haneli opak sıra + Luhn kontrol hanesi) — artı merkezi "Numarator" sayaç + numara defteri, mahkeme aşamaları alt tablosu, "Klasör Yolu" alanı ve 8.410 föye geriye dönük D-No yazımı.

**Genel sonuç:** Önerinin *teşhisi* doğrudur — eski manuel sistemin sorunları (elle numara → mükerrer/atlama, sayısal görünüm → Excel bozulması, numaraya gömülü değişken veri → toplu yeniden numaralama, çok köklü müvekkil, tek değerli mahkeme/esas alanı) gerçektir. Önerinin *ilkesi* de doğrudur: "numara kimliktir, veri deposu değildir." Ancak önerilen mekanizmaların büyük bölümü, **HukuDok'un zaten başka (ve daha köklü) biçimde çözdüğü problemleri, eski dünyanın (Excel + klasör sunucusu + elle giriş) araçlarıyla yeniden çözmektedir.** Ayrı bir D-No serisi HukuDok içinde ikinci bir paralel numaralandırma sistemi yaratır; bu, önerinin kendi "tek ve değişmez kimlik" ilkesiyle çelişir ve operasyonel karışıklığı artırır.

Madde madde karşılıklar:

| Önerinin çözdüğü sorun | Önerdiği mekanizma | HukuDok'ta durum |
|---|---|---|
| Elle numara → mükerrer, atlanan, yanlış yazılmış numara | D-No + Luhn kontrol hanesi + Numarator defteri | **Sorun sınıfı yok.** Numara elle yazılmaz: `tracking_no` UI'da otomatik üretilir, DB `unique` kısıtı çakışmayı 409 ile reddeder; belge sayacı ETag'li atomiktir. Luhn'un yakaladığı hata türü (elle daktilo hatası) sistemde oluşmaz — kullanıcı numarayı hiçbir alana elle girmez, kayda tıklayarak ulaşır. |
| "Numara veriden türetilmesin; veri değişince numara yanlış olur" | Opak, hiçbir şeyden türetilmeyen D-No | **İlke zaten sağlanıyor — gerçek kimlik `cases.id`'dir**: opak, kalıcı, düzenlemede asla değişmeyen PK; tüm ilişkiler (belgeler, taraflar, duruşmalar, ilişkili dosyalar) buna FK ile bağlıdır. `tracking_no` insan-yüzlü bir ETİKETtir: hiçbir join/eşleştirme ona dayanmaz ve veri düzeltildiğinde YENİDEN ÜRETİLMEZ (enrich modu tracking üretimini atlar; `ENRICH_FIELDS` bilinçli hariç tutar). Önerinin korktuğu "veri düzeltmesi 158 föyün numarasını değiştirir" senaryosu HukuDok'ta oluşmaz: alan düzeltilir, etiket durur, arama alanlardan çalışır. |
| Sayısal görünümlü numara Excel'de bozuluyor | `D-` metin öneki | `tracking_no` harf + nokta içerir (`D1.I_KUTLUK..0001.HUKUK.00000`), sayıya dönüşmez; birincil veri alışverişi zaten Excel değil API/DB'dir. |
| Aynı olayın dosyaları bağlanamıyor | TKU olay numarası katmanı | `case_relations` tablosu tipli bağ kurar (`ICRA_CEZA, ICRA_HUKUK, ASIL_TEMYIZ, BIRLESEN, AYRISTIRILAN, ILGILI...`) + `/case-groups/:id` görünümü. Fark: TKU tek grup anahtarı, relations ikili bağdır. Grup anahtarına gerçek ihtiyaç doğarsa bu **küçük bir ek alan/tablo işidir** — yeni bir numaralandırma sistemi gerektirmez. |
| Müvekkilin birden çok kökü var, kimliği tek değil | MüvekkilNo (5 hane) | `clients.id` + `cari_kod` (6 haneli sicil) zaten tek müvekkil kimliğidir; davalar FK ile bağlanır. |
| Mahkeme/esas değişince geçmiş kayboluyor veya ikinci föy açılıyor | Mahkeme Aşamaları alt tablosu | **Teşhis HukuDok için yanlış:** `court`/`esas_no` değişimi `CaseHistory`'ye old/new olarak yazılır ve `history.old_value` ARAMAYA DAHİLDİR (`case_manager.py:313`) — eski esas numarasıyla arama dosyayı bulur. İstinaf/temyiz/karar düzeltme blokları kendi mahkeme+esas alanlarını taşır; `yeni_esas_no` bozma sonrası içindir. Yapısal çok-satırlı aşama tablosu raporlama için değerlendirilebilir bir GELECEK geliştirmesidir; numaralandırmayla ilgisi yoktur. |
| Klasörler kayıtlardan kopuyor | "Klasör Yolu" alanı + hedef klasör düzeni | **Problem HukuDok'ta ortadan kalktı:** klasör yok; belge-dava bağı DB'dedir (`case_documents.case_id`), depo düz iki SharePoint klasörüdür. Önerinin 8. bölümü, büronun KENDİ dosya sunucusu için anlamlı olabilir ama HukuDok'a taşınacak bir gereksinim değildir. |
| Eski numaralar kaybolmasın | "Eski DosyaNo" sütunu | Zaten var: `klasor_no_2` — saklanır ve aranabilir. |
| Numara kayıttan önce alınmalı, iptal edilen defterde kalmalı | Numarator + numara defteri | HukuDok'ta numara kayıtla ATOMİK doğar; ayrı rezervasyon/iptal defteri, numara ile kaydın ayrı sistemlerde yaşadığı dünyanın ihtiyacıdır. |

Bilgi notunun 9. bölümündeki sorulara doğrudan cevaplar (görüşme gündemi için):

- **9.1 (D-No alanı):** Teknik olarak kolay, ama HukuDok içinde ikinci paralel numara sistemi açar; önerilmez. Eşleştirme ihtiyacı için kalıcı anahtar zaten var: `cases.id`. Büro D-No'yu kendi tarafında tutup HukuDok id'sini dış anahtar olarak saklayabilir (notun 9.8 ilkesiyle uyumlu — isim benzerliğine dönülmez, HukuDok'a alan basmak şart olmaz).
- **9.2 (Luhn doğrulama):** Elle giriş olmadığı için çözdüğü problem yok.
- **9.3 (aşamalar alt tablosu):** Kısmen mevcut (CaseHistory + istinaf/temyiz/KD blokları); tam alt tablo makul bir geliştirme adayı olarak not edildi.
- **9.4 (8.410 föye toplu yazım):** Toplu içe aktarma deseni mevcut (`scripts/import_excel_cases.py`, batch commit); eşleştirme anahtarı olarak `cases.id` kullanılabilir ve **kalıcıdır** (düzenlemede/taşımada değişmez).
- **9.5 (export/senkron):** `/export` API'si ve Excel exportları mevcut; "sütun adları/sırası sürümler arasında sabit kalsın" talebi makuldür ve ayrıca taahhüt edilmelidir.
- **9.6 (kayıt yaşam döngüsü):** `cases.id` kalıcıdır. Föy birleştirme özelliği yok (ilişki kurulur, kayıtlar yaşar). Silme, yazıldığı tarihte HARD delete'ti; **2026-08-05'te soft-delete'e çevrildi** (gerekçeli, admin panelinden geri alınabilir — §6.6). Büronun "silinen föy gerekçesiyle saklansın" beklentisi artık karşılanıyor.
- **9.7 (ön muhasebe):** HukuDok'ta yok. Kurulursa/dışarıda tutulursa bağlantı anahtarı D-No değil `cases.id`/`tracking_no` olmalıdır.

Dürüst öz-eleştiri: önerinin "numaraya veri gömme" eleştirisi, HukuDok'un `tracking_no`'suna da dokunur — 5 blok gerçekten veri taşır (kategori, isim, yargı türü, hizmet). Fark şudur: `tracking_no` sistemde *kimlik* değil *okunabilir etikettir*; kimlik yükünü `cases.id` taşıdığı için etiketteki bilginin eskimesi hiçbir bağı bozmaz ve yeniden numaralama zorunluluğu doğurmaz. Bu tasarım tercihi bilinçlidir (isim bloğu kategori önceliği dahil, kullanıcı onaylı).

**Özet tavsiye:** Öneri, HukuDok'suz (klasör + Excel + elle numara) bir dünya için doğru reçetedir; o dünya artık yok. D-No / Luhn / Numarator / Klasör Yolu benimsenmemeli. Öneriden alınmaya değer üç şey vardır ve üçü de numaralandırma değişikliği değil ek özelliktir: (1) ihtiyaç doğrulanırsa vaka/olay grup anahtarı (case_relations'ın üstüne küçük ek), (2) mahkeme aşamaları alt tablosu (raporlama geliştirmesi), (3) soft-delete (gerçek boşluk). Export sütun sabitliği ise entegrasyon taahhüdü olarak ayrıca verilmelidir.

### 6.5 Ekip veri güncelleme çalışması — `Full_Rapor_TKU.xlsx` değerlendirmesi (2026-08-04 anlık görüntü, ÇALIŞMA DEVAM EDİYOR)

Büro ekibi, sistemdeki verilerden "daha doğru" olacak şekilde arşiv verisini Excel üzerinde elden geçiriyor; nihai hali HukuDok'a aktarılmak üzere teslim edilecek. Aşağıdaki analiz 2026-08-04 tarihli ara sürüme aittir; sayılar teslimde değişebilir ama yapısal bulgular ve aktarım kuralları geçerli kalır.

**Dosya yapısı:** 4 sayfa —
- `Sheet` (ana): **8.409 föy × 63 kolon** (bilgi notundaki "8.410 föy" ile tutarlı).
- `Düzeltme_Logu`: **8.234 düzeltme kaydı** — kolonlar: Excel Satırı, SistemNo, DosyaNo, Eski Değer, Yeni Değer, Gerekçe, Tarih (18.07–02.08.2026 arası).
- `Silinen_Föyler` (10) ve `Kapsam_Dışı` (51): ana sayfayla aynı şemada, ayrılmış kayıtlar.

**Güçlü yönler (bunlar örnek nitelikte, aynen sürdürülmeli):**
1. **Düzeltme log disiplini** — her düzeltme eski değer + yeni değer + gerekçe + tarihle kayıtlı. Bu, HukuDok'un `CaseHistory` felsefesinin birebir Excel karşılığıdır ve aktarımda provenance olarak taşınabilir (aşağıda).
2. **Silinen föyler yok edilmemiş**, ayrı sayfada gerekçeli duruyor (bilgi notundaki soft-delete beklentisinin pratiği).
3. **TKU verisi temiz**: 8.151/8.409 dolu (%96,9) ve dolu değerlerin **%100'ü** `TKU-\d+` desenine uyuyor. 5.692 ayrı TKU grubu var; 1.515'i çok üyeli (en büyüğü 16 föy). Not: grupların 4.177'si tek üyeli — TKU'nun gerçek bilgi değeri çok-üyeli ~1.515 grupta (~4.000 föy).
4. **`SistemNo` %100 dolu ve %100 benzersiz** (8.409/8.409) — Micro Kolay Ofis kayıt kimliği. **Toplu aktarımın eşleştirme anahtarı BU olmalıdır** (aşağıda neden DosyaNo olamayacağı kanıtlı).

**Ara sürüm tespitleri** — bunlar eleştiri değil, 2026-08-04 anlık görüntüsünün durum fotoğrafıdır. Çalışma devam ettiği için bir kısmı ekibin zaten planında olabilir veya bilinçli bir ara durumdur; buradaki amaç, aktarım script'ini yazacak kişinin/AI'ın bu durumları önceden bilmesi ve script'in bunları tolere edecek şekilde tasarlanmasıdır:
1. **`DosyaNo` benzersiz değil** (bu ara sürümde): 142 değer mükerrer (284 satır) — örn. `1541.004`, `329.001`, `9.639.00`. Bilgi notunun kendi teşhisiyle (§2.2 "elle numara → mükerrer riski") tutarlı bir eski-veri gerçeği. Aktarım açısından sonuç: DosyaNo `klasor_no_2`'ye aranabilir etiket olarak yazılabilir; eşleştirme anahtarı olarak SistemNo tercih edilmeli.
2. **`DosyaNo` formatı en az 10 farklı şekilde**: `9.999.99` (2.597), `9.99999.99` (1.466), `9999.999.99` (1.337), `9.9999.99` (1.216), `999.999.99` (868), hizmet segmentsiz `9999.999` (507), `9.9999` (262)... Eski sistemin doğal mirası; karşılaştırma yapılacaksa önce normalizasyon gerekir.
3. **`MüvekkilNo` tekilleştirmesi bu ara sürümde henüz tamamlanmamış görünüyor**: 1.515 numaradan 61'i birden fazla isim taşıyor (örn. no 9 → AXA SİGORTA + ANADOLU SİGORTA + MEHMET NALBANT DR.; no 1 → AXA + KEMAL AYENGİN DR.), 9 isim birden fazla numara taşıyor (AXA → 1, 3, 9; QUICK → 2, 1464). Yoğunlaşma sigorta şirketlerinde — eski "çok kök" düzeninin izi; ekibin temizlik sırası gereği bu kolona henüz gelinmemiş olması muhtemel. Aktarım açısından sonuç: müvekkil eşleştirmesi bu kolonla tek başına otomatikleştirilmemeli; nihai teslimde durum yeniden değerlendirilip gerekirse isim-normalizasyonlu + insan onaylı eşleştirme kullanılmalı.
4. **Yer tutucu / sentinel değerler mevcut**: `Dava Tarihi`nde 217 satır `1900-01-01`, 40 satır metin tipinde, 122 boş; `Son Durum`da 97 satır `"Lütfen Seçiniz"`. Kaynak sistemin zorunlu-alan davranışından gelen bilinen desenler. Aktarım script'i bunları NULL'a çevirmeli ki HukuDok'ta "dolu ama anlamsız" alan oluşmasın ve `missing_required` filtresi doğru çalışsın.
5. **Çoklu-değer ve boşluk desenleri**: `Karşı Taraf` 7.398 satırda baş/son boşluklu, 3.198 satırda `;` ayraçlı çoklu taraf (aktarımda split edilip her biri ayrı `CaseParty(COUNTER)` satırına açılmalı). `Sorumlu Avukatlar` 8.398 satırda sonda virgül, 1.085 satırda çoklu avukat (ilki `responsible_lawyer_name`, tamamı `case_lawyers`'a). Kaynak yazılımın export biçiminden gelen desenler; script tarafında trim/split yeterli.
6. **`Esas` alanında 429 satır `YYYY/` ile bitiyor** (yıl var, sıra yok), 6 satır yalnız yıl. Kaynakta gerçekten eksik mi, export sırasında mı kesildi — ekip en iyisini bilir; aktarımda "eksik esas no" olarak işaretlenmesi yeterli.
7. **TKU boş 258 satır** (Ceza 153, İdare 70, Savcılık 13, Hukuk 13...): tekil-olay dosyası mı, henüz atanmamış mı — çalışma bittiğinde kendiliğinden netleşecek bir ayrım; şimdilik yalnız not.

**HukuDok alan eşlemesi (aktarım script'i için):** Excel kolonları HukuDok şemasıyla büyük oranda birebir örtüşüyor — bu, verinin zaten HukuDok modeline göre düşünüldüğünü gösteriyor:

| Excel | HukuDok | Not |
|---|---|---|
| SistemNo | eşleştirme anahtarı (kalıcı saklama için önerilen yer: `klasor_no_2` içinde `DosyaNo \| SistemNo \| TKU-xxx` birleşik, VEYA küçük migration ile ayrı kolonlar) | %100 unique |
| DosyaNo | `klasor_no_2` (aranabilir eski no) | unique değil, normalize et |
| Klasör No (=TKU) | çok-üyeli gruplar → `case_relations` (ILGILI) veya ileride grup anahtarı alanı | §6.4 tavsiyesiyle uyumlu |
| Müvekkil / Müvekkil Tipi | `clients` + `CaseParty(CLIENT)`; kategori: `Doktor→Doktor`, `Diğer Sağlık Çalışanı→Sağlık Çalışanı`, `Sigorta→Sigorta`, `Hasta→Hasta`, `Kurum→Kurum` | "Kurum" `CATEGORY_MAP`'te yok → B1 `X1` olur (bilinçli mi teyit et) |
| Karşı Taraf | `;` split → `CaseParty(COUNTER)` | trim şart |
| Yerel Mahkeme / Esas | `court` / `esas_no` (+ `judicial_unit` türetimi `derive_judicial_unit` ile) | |
| Dava Tarihi / İş Kabul Tarihi | `opening_date` / `acceptance_date` | 1900 sentinel → NULL |
| Ana Tür | `file_type` — değer kümesi HukuDok `file_types` seed'iyle 8/10 birebir (`İDARE`↔`İdare`, `TAHKİM`↔`Tahkim` normalize) | |
| Durum (Aktif/Arşiv) | `status` (`DERDEST`/`MAHZEN`) | |
| Dava Konusu / Alt Kırılım / Ek Alt Kırılım* | `subject` / `sub_type_extra` (kanonik listeye `normalize_known_value` süzgeciyle) | |
| İstinaf bloğu (6 kolon) / Temyiz bloğu | `istinaf_*` / `temyiz_*` alanları — neredeyse birebir | |
| Son Durum (35 değer) | `dosya_son_durumu` — HukuDok `file_statuses` (38 kayıt) ile kesişim eşlemesi çıkarılmalı; `"Lütfen Seçiniz"` atılmalı | |
| Sorumlu Avukatlar | ilki `responsible_lawyer_name`, hepsi `case_lawyers` (toleranslı `lawyer_resolver` ile) | |
| Hizmet Türü (9 değer) | `service_type` bitmask'e eşleme tablosu gerekir (örn. `Lexis Rapor→bit0 Rapor`, `Danışmanlık→bit1`, `Takip/Vekaletli→bit2 Dava`...) | ekiple birlikte kararlaştırılmalı |
| Taraf Sıfatı (11 değer) | `CaseParty.role` — `Aleyhine Başvurulan`, `Alacaklı`, `Katılan` HukuDok `party_roles` seed'inde YOK → listeye eklenmeli veya eşlenmeli | |
| Sigortalı / Hasar No / Hukuk No | `SIGORTALI` taraf veya poliçe `sigortali_kurum` / `hasar_dosya_no` / `hukuk_no` | |
| Hükmedilen Maddi/Manevi/Toplam | **HukuDok'ta karşılığı YOK** (karar blokları tutar alanı taşımıyor) — ya `karar_aciklama`/notes'a, ya küçük migration ile yeni alanlara | gerçek şema boşluğu |
| Islah Tutarı / Dava Değeri / Manevi Dava Değeri | `maddi_tazminat`/`manevi_tazminat` (ıslah sonrası mı ilk mi — ekip teyidi gerekli) | |

**Süreç notu — çift gerçek kaynak:** HukuDok DB'sinde davalar zaten yaşıyor (daha önceki aktarım; DB ~11 bin dava) ve çalışma süresince iki taraf paralel güncelleniyor. Bu, devam eden bir temizlik çalışmasının doğal ara durumudur — sorun değil; yalnızca teslim anında planlı yönetilmesi gereken bir geçiştir. Önerilen aktarım stratejisi:
1. **Cutoff tarihi ilan edilmeli**: Excel çalışması teslimle dondurulur; sonrasındaki tüm düzeltmeler yalnız HukuDok'ta yapılır (Excel'e dönüş yok).
2. **Toptan overwrite DEĞİL, alan bazlı delta**: SistemNo ↔ `cases.id` eşleme tablosu kurulur (ilk eşleştirme DosyaNo+esas_no+müvekkil karması ve insan onayıyla); sonra `enrich_case` deseni uygulanır — yalnız değişen alan yazılır, her değişiklik `CaseHistory`'ye `source="excel-cleanup-2026-08: <gerekçe>"` imzasıyla girer. `Düzeltme_Logu` sayfasındaki gerekçeler bu imzalara taşınarak provenance HukuDok'ta da yaşamaya devam eder.
3. **Çakışma raporu**: aynı alanda hem Excel'de hem HukuDok'ta (aktarım sonrası tarihli) farklı değer varsa otomatik yazılmaz, insan kararına listelenir.
4. `Silinen_Föyler` HukuDok'ta karşılığı olan kayıtlarsa: hard-delete YAPILMAMALI (bkz. §6.4 soft-delete boşluğu); çözülene kadar `status=MAHZEN` + notes'a silme gerekçesi önerilir.
5. `Kapsam_Dışı` sayfası aktarım kapsamına hiç girmemeli.

**Genel yorum:** Çalışma ciddi, yöntemli ve doğru yönde — özellikle düzeltme logu disiplini ve silinen föylerin gerekçeli saklanması, HukuDok'un veri felsefesiyle tam uyumlu ve örnek nitelikte. Excel'in kolon seti fiilen "HukuDok şemasının eski sistemden görünüşü" olduğundan aktarım teknik olarak düşük riskli. Yukarıdaki tespitlerin çoğu, çalışma tamamlandığında ekip tarafından zaten kapatılmış olabilir; nihai teslimde bu profilleme yeniden koşulup güncel durum doğrulanmalıdır. Teslim öncesi ekiple konuşulması *yararlı* iki başlık: MüvekkilNo eşleşmelerinin nihai durumu ve `Hükmedilen` tutar alanları için HukuDok tarafında yer açılıp açılmayacağı (şema boşluğu bizim tarafımızda).

**Aktarım günü notu (2026-08-05):** aktarım gününde admin panelinden `party_roles` listesine `Aleyhine Başvurulan / Alacaklı / Katılan` eklenecek; "Kurum" kategorisinin B1 eşlemesi ve Hizmet Türü bitmask tablosu ekiple birlikte kararlaştırılacak (açık karar).

### 6.6 Mutabakat ve uygulanan işler (2026-08-05)

Büro, teknik rapora verdiği cevapta **D-No / Luhn / Numarator önerisini geri çekti** (gerekçe: ilkenin — "numara kimliktir, veri deposu değildir" — `cases.id` ile zaten sağlandığını kabul). Karşılığında aşağıdaki maddeler kabul edilip **uygulandı**:

| İş | Durum | Uygulama |
|---|---|---|
| `cases.tku_no` (olay grup anahtarı, index'li, unique DEĞİL) + `cases.sistem_no` (eski sistem kayıt kimliği, unique) | ✅ Uygulandı | Migration #22; arama (normal+exact+relevance) ve trigram index'ler dahil; UI'da gösterilmez (kullanıcı kararı); `Full_Rapor_TKU.xlsx` aktarımında dolacak |
| Soft-delete (dava + müvekkil) | ✅ Uygulandı | Migration #21: `deleted_at/deleted_by/delete_reason`; silme artık kayıt korur, gerekçe zorunlu (`DELETE ...?reason=`), listelerden gizlenir; **admin paneli "Silinenler" sekmesinden geri alınır** (`GET /api/admin/deleted-records`, `POST /api/admin/restore/{case\|client}/{id}`). Davada silme `active=False` da yazar (restore'da True). Müvekkil silmede `CaseParty.client_id` artık NULL'lanmaz (restore temiz). BİLİNÇLİ İSTİSNA: `client-sequence` silinen davaların numara aralığını saymaya devam eder |
| Hükmedilen tutarlar | ✅ Uygulandı | Migration #23: `hukmedilen_maddi/manevi/toplam NUMERIC(20,2)`, NULL = girilmedi; takip paneli Yerel Mahkeme bloğunda düzenlenir (`normalizeMoney` ile TR biçimi kabul), CaseDetails Tazminat kartında gösterilir |
| PROCESS_MAP düzeltmesi | ✅ Uygulandı | `caseNumberUtils.ts`'e `İdare→IDARE, Tahkim→TAHKM, Vergi→VERGI, Danışmanlık→DANIS` eklendi — bu türler artık sessizce HUKUK bloğu üretmez; intake sihirbazı dropdown'ı da genişledi. MEVCUT yanlış-bloklu davalara otomatik retag YAPILMADI (gerekirse `scripts/retag_tracking_nos.py`) |
| Kayıt No gösterimi | ✅ Uygulandı | `cases.id` dava detayı "Dosya Bilgileri" kartında kısa, dikte edilebilir "Kayıt No" olarak gösterilir |

Büro cevabındaki "dört taahhüt" çerçevesi (kalıcılık, görünürlük, export sabitliği, çıkış garantisi) satıcı–müşteri kurgusuydu; uygulama Hanyaloğlu-Acar bünyesinde geliştirildiği için bunlar taahhüt değil **iç standarttır**: `cases.id` PK olarak kalıcıdır, export sütun sabitliği geliştirme pratiği olarak gözetilir, veri kendi Postgres'imizdedir (`pg_dump` her an alınabilir).

**İkinci tur kararlar (2026-08-05):**

- **Export soft-delete filtresi + cari silme uyarısı uygulandı:** `/export` hattı (liste + tekil + dosya + outbox enqueue) soft-delete edilmiş davanın belgelerini artık eler; UNLINKED (davasız) belgeler bilinçli dahil kalır, dava restore edilirse belgeleri tekrar akar (filtre dinamik — istenen davranış). Aktif (DERDEST/DANIŞ) davası olan cari silinirken silme dialogu kırmızı bilgilendirme gösterir (`GET /api/clients/{id}/case-summary`) — sistem geneli kural gereği ENGELLEME YOK.
- **tku_no/sistem_no aktarım doğrulama kararı:** ayrı doğrulama ucu AÇILMAYACAK; doğrulama = aktarım script'inin dry-run raporu + doğrudan psql sorguları + `GET /api/cases/{id}` ham dict'inde iki alanın dönmesi.
- **Retag kuru-çalışma sonucu:** lokal DB'de İdare/Tahkim/Vergi/Danışmanlık türündeki 4.414 dosyanın SIFIRINDA `B4=HUKUK` yanlış bloğu bulundu (bu türler Excel import script'iyle gelmişti, script'in haritası tamdı; UI'dan bu türlerde yeni-format numara hiç üretilmemiş). Toplu retag GEREKSİZ; PROCESS_MAP düzeltmesi ileriye dönük korumadır. Prod'da teyit sorgusu: `SELECT count(*) FROM cases WHERE file_type IN ('İdare','Tahkim','Vergi','Danışmanlık') AND tracking_no LIKE '%.HUKUK.%';`
- **calendar_events maddesi düştü:** tablo davaya bağlı değildir (`case_id` yok; `models.py` docstring: "Bir davaya bağlı değildir"). Davaya bağlı takvim öğesi `HearingDate`'tir ve onun soft-delete filtresi uygulanmıştır.

**Kanonik kimlik:** `cases.id` sistemin kanonik kimliğidir; hiçbir işlemde değişmez. Export sütun adları/sırası sürümlenir; değişiklikler duyurulmadan yapılmaz.

---

## 7. Arama ve belgeye erişim

### 7.1 Nerede aranır: SADECE Postgres
- Dava arama: `GET /api/cases/search?q=` ve `GET /api/cases?q=...` → `case_manager.get_cases` (`case_manager.py:230-343`). Sorgu boşluktan bölünür; terimler arası AND, alanlar arası OR. Aranan alanlar: `tracking_no, esas_no, klasor_no_2 (ESKİ SİSTEM NO), court, subject, notes, responsible_lawyer_name, uyap_lawyer_name, parties.name, lawyers.name, history.old_value` — hepsi `ILIKE %term%`, trigram index destekli. Relevance: exact > prefix > partial, sonra `updated_at DESC`.
- `exact=true` modu: numara alanlarında tam eşleşme.
- Filtreler: `status, file_type, lawyer, urgent_days, missing_required, limit/offset`; toplam `X-Total-Count` header'ında. Tarih ve doctype filtresi dava listesinde YOK.
- Global arama barı (⌘K): davalar sunucudan, müvekkiller client-side filtre. UI'daki "AI Anlamsal Arama" rozeti kozmetiktir — arama saf SQL'dir, semantik arama YOKTUR.
- Belge listeleme: `GET /api/documents?link_mode=UNLINKED` ve `GET /api/cases/{id}/documents?party_id=` — yine DB.

### 7.2 Belge indirme: backend proxy, SharePoint linki değil
`GET /api/documents/{id}/download?inline=true` (`routes/documents.py:238-284`): tenant/sahiplik doğrulaması → Graph ile `02_YEDEK_ARSIV/{stored_filename}` içeriği çekilir → doğru MIME ile stream edilir. Kullanıcının SharePoint erişimine ihtiyaç yoktur. (İstisna/teknik borç: `CaseGroup.tsx:491-492` hâlâ ham `sharepoint_url` açar.)

### 7.3 Bağlantısız belgeler
`link_mode` ∈ `LINKED | UNLINKED | TEST`. Davasız arşivlenen belge `UNLINKED` kalır ve `/unlinked-documents` sayfasından sonradan davaya bağlanır (`PATCH /api/documents/{id}/link`). UNLINKED belgelere yalnız YÜKLEYEN erişebilir (`auth_helpers.py:44-81`).

---

## 8. Veri modeli (Postgres)

### 8.1 Tablolar (`backend/models.py`)
`cases, case_stage_logs, case_relations, case_history, case_parties, case_lawyers, lawyers, clients, client_policies, doctypes, statuses, sync_logs, email_recipients, case_subjects, file_types, court_types, party_roles, bureau_types, cities, specialties, client_categories, file_statuses, analysis_cache, hearing_dates, calendar_events, case_documents, daily_activity_reports, export_outbox`.
Migrasyon: Alembic YOK; elle yazılmış deklaratif `_MIGRATIONS` listesi (`database.py:90+`), startup'ta koşar.

### 8.2 `Case` — dava kartı (öne çıkan alanlar)
Tam liste `models.py:6-97`. Çekirdek: `tracking_no(unique), esas_no, status(DERDEST/DANIŞ/MAHZEN), file_type, sub_type, sub_type_extra, service_type, subject, court, judicial_unit, opening_date, acceptance_date, atama_tarihi, bureau_type, responsible_lawyer_name, uyap_lawyer_name, maddi/manevi_tazminat, hasar_dosya_no, hukuk_no, notes, tenant_id, klasor_no_2(ESKİ SİSTEM NO — gizli, aranabilir)`. Takip alanları: `case_stage(DERDEST|KARAR|ISTINAF|TEMYIZ|KARAR_DUZELTME|KESINLESME|INFAZ|KAPALI)`, `dosya_son_durumu` + yerel karar/istinaf/temyiz/karar düzeltme blokları (~30 alan) + `kesinlesme_tarihi, infaz_tarihi`.
- Takip paneli TEK taslak + tek Kaydet: `PATCH /api/cases/{id}/tracking`, **exclude_unset semantiği** — gönderilmeyen alan dokunulmaz, açık `null` SİLER.
- `check-duplicate`: `GET /api/cases/check-duplicate?esas_no=&court=` — esas no benzerliği (tam/sıfır-dolgu toleransı) + mahkeme benzerliği, ilk 10 aday.

### 8.3 Tenant modeli — ortak havuz
`tenant_id` yalnız 4 tabloda (`cases, clients, calendar_events, daily_activity_reports`), hepsi nullable. Filtre kuralı (`auth_helpers.py:15`): `tenant_id == <kullanıcının tid'i> OR tenant_id IS NULL`. **Hanyaloğlu-Acar + LexisBio ortak iş yaptığı için yeni kayıtlar BİLİNÇLİ olarak `tenant_id=NULL` (paylaşımlı) açılır** (`routes/cases.py:48-50`, `clients.py:28-29`). NULL = "legacy/paylaşılan" değil "ortak havuz" olarak okuyun. `case_documents`'ta tenant_id yok; belge tenant'ı davası üzerinden türetilir.

### 8.4 Zorunlu alanlar — kayıt ENGELLENMEZ
`backend/required_fields.py` tek kaynak (frontend `GET /api/config/required_case_fields` ile okur). 13 alan: `esas_no, court, file_type, judicial_unit, sub_type, opening_date, subject, responsible_lawyer_name, uyap_lawyer_name, service_type, acceptance_date, bureau_type, atama_tarihi` + karşı taraf TC kuralı (`counter_party_tc_no`). **Eksik alan kaydı ENGELLEMEZ** — dosya DERDEST açılır, eksikler uyarı olur ve `missing_required=true` filtresiyle listelenir. (DANIŞ'a düşürme denendi, dönüşüm kaybı riskiyle vazgeçildi.)

---

## 9. Otonom dava açma (Case Intake) — Faz 6+1 prod'da, Faz 7 lokal main'de

### 9.1 Akış
`/new-case/auto` sihirbazı: **upload → analyze → review → save**. Max 15 dosya. `.eml` desteklenir: `POST /api/case-intake/expand-eml` gövdeyi PDF'e çevirir + ekleri çıkarır (orijinal .eml arşivlenmez).

1. **Analyze** (`POST /api/case-intake/analyze`, belge başına): Gemini **ensemble N=3** koşu + alan bazlı çoğunluk oyu → kritik alan doğrulayıcı geçişi (esas_no, TC, roller; "şüphede false") → regex çapraz kontrol. Sayfa kırpma YOK (tam belge gider). Model `GEMINI_INTAKE_MODEL`.
2. **Merge** (`POST /api/case-intake/merge`): belgeler arası oy (payda = alanı DOLU belge sayısı), dilekçe-öncelikli alanlar (subject/tazminatlar), esas_no/court çelişkisinde **hakem LLM** (belge hiyerarşisi: tensip > dava dilekçesi > tebligat > diğer; hakem kararı yalnız mevcut adaylardan biriyse uygulanır), `judicial_unit` mahkeme adından 31 regex kalıbıyla türetilir, taraf birleştirme (VEKIL satırları taraf listesine girmez), poliçe birleştirme + dönem uyarıları, tanıdık sorgu her tarafa iliştirilir, mükerrer dava kontrolü.
3. **Commit** (`POST /api/case-intake/commit`): dava atomik açılır (`status` sunucuda DERDEST'e zorlanır); **409'da (duplicate tracking_no) HİÇBİR belge tüketilmez** → frontend tek otomatik retry yapar; belgeler belge-başına best-effort arşivlenir (`expired`/`failed` durumları yanıtla döner); poliçeler best-effort `client_policies`'e yazılır.

### 9.2 Faz 7 — Zenginleştirme modu (enrich)
Mevcut davaya belgeden doldur/teyit. Tetik: merge gövdesinde `case_id` (UI: dava detayından `?enrichCase=<id>` veya duplicate uyarısından köprü).
- Kayıtlı dava değerleri aday havuzuna enjekte edilir (`inject_case_candidates`); alan başına `enrich.status` ∈ `fill` (dava boş, belge dolu) / `confirm` (aynı) / `conflict` (farklı) / `keep`.
- UI'da tik = **"UYGULA"** demektir (onay değil); tiklenmeyen alana dokunulmaz. Ofis no/hizmet türü/avukat blokları enrich'te gizlenir; tracking_no yeniden ÜRETİLMEZ.
- Uygulama: `POST /api/case-intake/apply` → `case_manager.enrich_case` (19 alanlık `ENRICH_FIELDS`; `status/tracking_no/service_type` bilinçli hariç). Her değişiklik `CaseHistory`'ye **imzalı** yazılır: `source="intake-enrich: <belge adları>"`. Taraflarda YALNIZ EKLEME yapılır (mevcut satır güncellenmez/silinmez), idempotent.
- Belge arşivleme commit ile aynı yardımcıları kullanır (aynı SharePoint klasörleri).

---

## 10. Müvekkil / taraf yönetimi ve Tanıdık Sorgu

### 10.1 Tanıdık Sorgu — `POST /api/parties/check` (2026-07-22'den beri prod'da)
Saf motor `backend/party_check.py` (DB erişimi route'ta). Amaç: dava kartına yazılan tarafın büro geçmişinde görünüp görünmediğini ve **çıkar çatışmasını** göstermek. Kayıt asla ENGELLENMEZ; UI'da gri/sarı/kırmızı nokta (`PartyMatchIndicator`).
- Normalizasyon KRİTİK: **NFD + combining-mark strip şart** (bazı kayıtlarda `i̇` = i + U+0307 var) → turkish_upper → diacritic fold → unvan temizliği (`DR|AV|UZM|DOÇ|PROF|OP|DT|AVUKAT|STJ`).
- Eşleşme kademeleri: `tc_no` → certain; isim tam/kelime-sırası-bağımsız → probable; **kelime bazlı Levenshtein** (kelime sayıları eşit + her kelime kendi karşılığıyla; ≤7 harf tolerans 1, uzun 2) → possible. Kurumsal isimlerde fuzzy KAPALI.
- `conflict=True` TEK koşul: CLIENT OLMAYAN taraf, `contact_type=="Client"` bir cariyle eşleşirse (çıkar çatışması yalnız karşı tarafa bakılır — 2026-08-01 kullanıcı kararı). TC'ler biliniyor ve farklıysa eşleşme düşürülür ("aynı isim farklı kişi").
- Frontend: 600 ms debounce, max 20 taraf, TC girilerek kesinleştirilebilir.

### 10.2 Diğer eşleştiriciler
- `muvekkil_matcher_v2.HibridMatcher`: belge analizinde müvekkil hook doğrulama (cache_hit 100 / liste_düzeltmesi 95 / fallback 0).
- `list_searcher.ListSearcher`: FlashText tabanlı in-memory müvekkil arama — **adına rağmen SharePoint listesiyle ilgisi yoktur**; veriyi Postgres'ten yükler (isim eski SharePoint-list döneminden kalmadır).
- Intake `match_client`: tc 1.0 / isim tam 0.95 / fuzzy 0.8 skorları; DB'deki kanonik adı döndürür.
- `CaseParty.party_type` ekseni: `CLIENT | COUNTER | THIRD`; rol ekseni ayrı (`party_roles` listesi, MAIN 11 + THIRD 5). DANIŞ statüsünde yeni davada kalıcı Client kaydı AÇILMAZ (yalnız CaseParty).

---

## 11. E-posta, yetki belgesi, UDF

- **E-posta**: Graph `POST /users/{EMAIL_SENDER}/sendMail` (app-only). Belge arşivlendiğinde sorumlu avukata bildirim; "müvekkil bilgilendirme" metni de **müvekkile değil avukata** gider (`[Müvekkil Bilgilendirme]` öneki). Gövde metnini Gemini üretir; önizleme endpoint'leri var. Sonuç `case_documents.email_sent/email_error`'a yazılır; `/api/documents/{id}/resend-email` ile tekrar denenir. Gecelik "Mailsiz Arşiv Özeti" raporu APScheduler ile.
- **UDF okuma** (`udf_converter.py`): UYAP UDF (ZIP veya düz XML) → ReportLab ile PDF; bozuk görseller akışı durdurmaz, uyarı üretir.
- **UDF üretme** (`yetki_belgesi_generator.py` + `POST /api/yetki-belgesi/udf`): gerçek UYAP `format_id="1.8"` ZIP/XML formatında yetki belgesi üretir.
- **PDF/A-2b**: Ghostscript `-dPDFA=2 -sColorConversionStrategy=RGB` (`pdf/pdf_converter.py:138-148`), timeout `GS_TIMEOUT_SECONDS` default 240s; subprocess çıktısı `encoding="utf-8", errors="replace"` (UnicodeDecodeError arızasının düzeltmesi). PDF olmayan format dönüşemezse fallback YOK (ham dosya `.pdf` kılığında arşive sızamaz).

---

## 12. Hukukbot entegrasyonu (export)

- İkinci stack (`~/hukukbot-ui`, ayrı repo) belge tüketicisidir. Auth: Azure AD DEĞİL — `X-API-Key` (`HUKDOK_EXPORT_API_KEY`, ≥32 karakter zorunlu, fail-closed 503). `/export` prefix'i nginx'e BİLİNÇLİ bağlanmamıştır; yalnız Docker iç ağı `hukuk_shared` üzerinden `http://hukdok_backend:8001` ile erişilir.
- Akış: SharePoint upload bitip `sharepoint_url` DB'ye yazıldıktan SONRA `export_outbox` satırı açılır (`pending`) + `HUKUKBOT_WEBHOOK_URL`'e webhook (retry 3). Webhook yalnız gecikmeyi azaltır; doğruluk garantisi outbox + hukukbot reconcile'dadır.
- Uçlar: `GET /export/documents?status=pending`, `GET /export/documents/{id}`, `GET /export/documents/{id}/file` (SharePoint'ten proxy — Graph kimlikleri hukdok'ta kalır), `POST /export/outbox/{id}/ack|nack`.
- Filtreler: `link_mode != TEST` (UNLINKED dahil), `sharepoint_url` dolu, tür allowlist'i (§5.3, 12 karar/rapor kodu).

---

## 13. Kimlik doğrulama ve yetkilendirme

- **Frontend**: MSAL redirect flow, cache sessionStorage, scope `api://{AZURE_CLIENT_ID}/access_as_user`; access token her istekte `Authorization: Bearer`. 30 dk idle timeout. 401'de bir kez sessiz yenileme + retry, sonra logout.
- **Backend** (`auth_verifier.py`): `tid` → `ALLOWED_TENANTS` whitelist → tenant'a özgü JWKS ile RS256 imza + audience doğrulaması.
- **Kimlik/e-posta çözümü — KRİTİK**: her yerde üçlü fallback şart: `preferred_username → upn → email` (`auth_verifier.py:101`, `config.py:42`). Azure token'ları her zaman `upn` taşımaz; tek claim'e güvenmek admin kontrolünü bozmuştu.
- **Admin**: binary model — `ADMIN_EMAILS` env listesi; `GET /api/config/is_admin`. RBAC yok.
- **Tenant izolasyonu**: §8.3 kuralı + UNLINKED belgede yükleyen-kilidi.
- Dev bypass yalnız `ENV=development + ALLOW_DEV_TENANT=true + DEV_MODE=true + tid=="dev-tenant"` dördü birdense çalışır. ⚠️ `DEV_MODE=true` prod'a taşınırsa CORS `.*` açılır ve zayıf export anahtarı kabul edilir — prod `.env`'inde asla bırakmayın.

---

## 14. Konfigürasyon, referans listeleri, ortamlar

### 14.1 Referans listeleri (13 liste, admin panelden yönetilir)
`LIST_REGISTRY` (`managers/reference_lists.py:74-92`): `lawyers, statuses, doctypes, case_subjects, emails, file_types (Dava/Yargı Türleri), court_types (Mahkemeler, parent_code hiyerarşili), party_roles, bureau_types, cities, specialties, client_categories, file_statuses`. Ad değişiklikleri bağımlı dava/müvekkil/belge kayıtlarına YAYILIR (`POST /api/config/update`); silme modları `block|clear|reassign|keep` (`party_roles`, `lawyers`(CaseLawyer), `file_types`(CourtType.parent) clearable=False). Excel export: `GET /api/config/export/{list_type}`. Seed: `seed_data.py` (10 yargı türü, ~45 mahkeme, 16 rol, 8 büro türü, 84 şehir, 45 uzmanlık, 8 kategori, 38 dosya durumu).

### 14.2 Kritik env değişkenleri (canlı okunanlar)
```
DATABASE_URL (postgresql zorunlu)         GEMINI_API_KEY, GEMINI_MODEL_NAME, GEMINI_INTAKE_MODEL
SHAREPOINT_TENANT_ID / CLIENT_ID / CLIENT_SECRET / SITE_URL
SP_DRIVE_NAME (default Belgeler)          SHAREPOINT_COUNTER_LIST_NAME (Counter)
SHAREPOINT_FOLDER_HAM_NAME (01_HAM_ARSIV) SHAREPOINT_FOLDER_ISLENMIS_NAME (02_YEDEK_ARSIV)
AZURE_CLIENT_ID, ALLOWED_TENANTS, ADMIN_EMAILS
EMAIL_ENABLED, EMAIL_SENDER, EMAIL_TEST_MODE
HUKDOK_EXPORT_API_KEY, HUKDOK_EXPORT_TYPES, HUKUKBOT_WEBHOOK_URL, HUKUKBOT_INGEST_API_KEY
VITE_AZURE_CLIENT_ID, VITE_AZURE_TENANT_ID, VITE_API_URL   (build-time gömülür!)
GS_TIMEOUT_SECONDS, MALLOC_ARENA_MAX=2, SSL_CERT_FILE (AVG TLS için lokal)
```
**Ölü env'ler (kod okumaz, kafa karıştırmasın):** `SHAREPOINT_DRIVE_NAME`, `SHAREPOINT_TARGET_FOLDER`, `SHAREPOINT_TEST_MODE`, `SHAREPOINT_SCOPE`, `UPLOAD_SHAREPOINT_*` ailesi (eski iki-site mimarisi kalıntısı; Azure'daki upload app secret'ının iptali önerilmiş durumda), `VITE_AZURE_REDIRECT_URI`.
`.env` değişikliği prod'da `docker compose restart` ile GELMEZ; `up -d` (recreate) gerekir.

### 14.3 Deployment zinciri
`docker-compose.yml`: postgres + backend (`hukdok_backend`) + frontend; network `hukudok-network` + external `hukuk_shared`. Backend imajı: python:3.10-slim + ghostscript + libreoffice. Frontend: node build (`--legacy-peer-deps`) → nginx:alpine. Container nginx: 50M body, **300s proxy timeout** (GS dönüşümü 60s'i aşınca 504 üretiyordu — f72f13e), `/api|/process|/confirm|/preview-email-body|/refresh` proxy'lenir, `/export` bilinçli proxy'lenmez. CI: ruff+mypy+pytest (backend, konteyner python 3.10 ile aynı) / lint+tsc+vitest+build (frontend). Lokal test: backend pytest KONTEYNERDE koşulmalı (host py3.13 uyumsuz), frontend vitest host'ta.

---

## 15. Legacy kalıntıları ve ölü kod haritası (AI asistanları için "buna kanma" listesi)

| Kalıntı | Gerçek | Konum |
|---|---|---|
| `klasor_no_2` | Eski sistem dosya numarasının taşındığı SALT-ARAMA alanı; hiçbir üretim/doğrulama mantığına girmez | `models.py:36`, arama `case_manager.py:305` |
| `config_type="upload"` parametreleri | Ölü — daima default credential/site kullanılır ("Single-Tenant/Single-Site Mode") | `auth_graph.py:33-35`, `sharepoint_uploader_graph.py:41-45` |
| `LogManager` / SharePoint `log` listesi | Instance ediliyor ama hiç çağrılmıyor; listeye yazım durmuş | `log_manager.py:19-170`, `api.py:86-89` |
| `_update_list_item_fields` (belge metadata) | Hiçbir çağıran metadata geçmiyor — SharePoint kolonlarına yazım yok | `sharepoint_uploader_graph.py:250-265` |
| `use_date_subfolder=True` yolu | Kod var, tüm çağıranlar False — tarih alt klasörü açılmıyor | `sharepoint_uploader_graph.py:147-151` |
| `tracking_no` yorumundaki `"2024/1234"` örneği | ESKİMİŞ — gerçek format 5 bloklu (§6.2) | `models.py:10` |
| `admin_manager.py` | Salt geriye-uyumluluk re-export shim'i; gerçek kod `reference_lists/lawyer_resolver/case_manager/client_manager/seed_data`'da | `managers/admin_manager.py:1-39` |
| `ListSearcher` adı | SharePoint listesi DEĞİL — Postgres'ten beslenen FlashText motoru | `list_searcher.py:18-39` |
| Masaüstü (PyInstaller/Electron) izleri | `sys.frozen` .env yolları, `os.getlogin()`, `~/AppData/Local/HukuDok/*` yolları — Linux konteynerde `/home/appuser/AppData/...` olarak oluşur, recreate'te kaybolur | `auth_graph.py:25-28`, `config_manager.py:21-35`, `vault.py` |
| `muvekkil_adi` (case_documents) | deprecated — taraf bağı `case_party_id` üzerinden | `models.py:461` |
| "AI Anlamsal Arama" UI rozeti | Kozmetik; arama SQL ILIKE | `GlobalSearchDropdown.tsx:182-185` |

---

## 16. Bilinen tuzaklar ve operasyon notları (çapraz doğrulanmış)

1. **Doctype padding**: karşılaştırmadan önce `_normalize_doctype_code` (§5.2). En sık AI hatası kaynağı.
2. **PATCH tracking exclude_unset**: alan güncellerken göndermediğiniz alan korunur, `null` gönderirseniz SİLİNİR.
3. **tracking_no üretimi yalnız frontend'de**; backend'e "numara üret" diye API aramayın — yoktur. PROCESS_MAP artık üç kopyada da 10 anahtarlıdır (2026-08-05'te frontend'e `İdare/Tahkim/Vergi/Danışmanlık` eklendi — önceden bu türler B4'te sessizce `HUKUK` üretiyordu; DÜZELTİLDİ, §6.6). Düzeltme öncesi açılan bu türlerdeki davaların blokları yanlış kalmış olabilir; gerekirse `scripts/retag_tracking_nos.py`.
4. **Counter SharePoint'e bağımlı**: SharePoint kesintisinde `/process` sayacı `TIMEOUT___`/`XXXXXXXXX` döner ama akış devam eder; `increment` başarısızlığı CRITICAL loglanır.
5. **PDF/A başarısızsa hiçbir arşive yazılmaz** (500 + hata ID) — "belge yarım yüklendi" durumu tasarımsal olarak imkânsızdır; `sharepoint_url` NULL olan `case_documents` satırı "upload henüz bitmedi/başarısız" demektir.
6. **Teknik ERROR logları** docker logs'ta değil, SharePoint `02_YEDEK_ARSIV/technical_log_*.json` içindedir.
7. **OOM geçmişi**: 1-bit G4 TIFF'lerin RGB'ye açılıp listede tutulması + glibc arena büyümesi üç prod kesintisinin kök nedeniydi; düzeltmeler + `MALLOC_ARENA_MAX=2` 2026-07-30'dan beri canlı. Prod'da `docker logs`/`journalctl`'i `--since`'siz çalıştırmayın.
8. **Kimlik claim'i**: `preferred_username → upn → email` üçlü fallback olmadan kimlik okumayın (§13).
9. **DANIŞ**: yeni DANIŞ dosyasında kalıcı Client açılmaz; ama `update_case` yolu DANIŞ kontrolü yapmadan cari açabilir (bilinen tutarsızlık, `case_manager.py:426-447`).
10. **`/api/incomplete-tasks`** `required_fields.py`'den bağımsız İKİNCİ bir eksik-alan mantığı taşır (legacy; çelişki bilinçli kabul edilmiş durumda).
11. **PowerShell 5.1 + Türkçe dosyalar**: Get/Set-Content çift kodlama yapar; dosya değişikliklerini daima editör/Edit aracıyla yapın.
12. **OneDrive + Docker build cache**: requirements değişse bile pip katmanı CACHED geçebilir; `--progress=plain` ile doğrulayın.
13. E-posta "müvekkil bilgilendirme" çıktısı müvekkile GİTMEZ; sorumlu avukata gider (bilinçli tasarım).
14. Frontend `VITE_*` değerleri build-time gömülür; env değişince frontend rebuild şarttır (`--build`).
15. **Soft-delete imha değildir.** KVKK imha yükümlülüğü kapsamında, saklama süresi dolan kayıtlar için kalıcı imha (purge) yolu İLERİKİ FAZ olarak planlanmalıdır (belge binary'lerinin SharePoint'ten silinmesi dahil).

---

## 17. Endpoint hızlı referansı

**Belge işleme:** `POST /process` (NDJSON stream analiz) · `POST /confirm` (arşivle) · `POST /preview-email-body` · `POST /preview-client-email-body` · `GET /api/download/{file_id}` · `POST /refresh`
**Belgeler:** `GET /api/documents` · `GET /api/cases/{id}/documents` · `PATCH /api/documents/{id}/link` · `PATCH /api/documents/{id}/party` · `GET /api/documents/{id}/download` · `GET /api/documents/{id}/email-status` · `POST /api/documents/{id}/resend-email` · `POST /api/yetki-belgesi/udf`
**Davalar:** `POST/GET /api/cases` · `GET /api/cases/stats` · `GET /api/cases/search` · `GET /api/cases/client-sequence` · `GET /api/cases/check-duplicate` · `GET/PUT /api/cases/{id}` · `DELETE /api/cases/{id}?reason=` (soft-delete, gerekçe zorunlu) · `PATCH /api/cases/{id}/tracking` · `GET /api/cases/{id}/stage-log` · relations CRUD · hearing-dates CRUD · calendar-events CRUD · `GET /api/calendar-report`
**Admin (soft-delete):** `GET /api/admin/deleted-records` · `POST /api/admin/restore/{case|client}/{id}` — silinenleri gören TEK yol; require_admin
**Intake:** `POST /api/case-intake/expand-eml | analyze | merge | commit | apply | keepalive`
**Müvekkil/taraf:** `POST/GET /api/clients` · `PUT /api/clients/{id}` · `GET /api/clients/{id}/case-summary` (silme uyarısı sayıları) · `DELETE /api/clients/{id}?reason=` (soft-delete, gerekçe zorunlu) · policies CRUD · `POST /api/parties/check`
**Config:** 13 liste CRUD (`/api/config/{liste}`) · `update/delete/usage/fields/export/reorder/seed/rename` · `GET /api/config/is_admin` · `GET /api/config/required_case_fields`
**Aktivite:** `GET /api/activity/daily-report|history` · acknowledge · send-emails · admin uçları
**Export (API-key, iç ağ):** `GET /export/documents[/{id}[/file]]` · `POST /export/outbox/{id}/ack|nack`

---

*Bu rapor 4 paralel kod keşif taramasının (belge hattı, SharePoint/arşivleme, dava takip/intake, frontend/auth/altyapı) çapraz doğrulanmış birleşimidir. Satır numaraları 2026-08-04 itibarıyla `main` dalına aittir; kod değiştikçe kayabilir, dosya adları daha kalıcıdır.*
