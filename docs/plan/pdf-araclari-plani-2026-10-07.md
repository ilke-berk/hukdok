# Belge tezgâhı planı: PDF araçları + Word yaşam döngüsü + eklenti (07.10.2026)

> **Durum: ONAYLANDI (07.10.2026).** Kullanıcı 07.10'da Acrobat aboneliğini yenilemeden PDF işlerini HUKDOK'tan yapmak
> istedi; "Acrobat yerine HUKDOK ile PDF işleri" belgesi (Claude Docs + masaüstü, 07.10) önerinin gerekçesidir. Bu
> dosya uygulama planı ve **frontend ile backend'in paralel koşabilmesi için sabitlenen API sözleşmesidir** (§3).
> Her iddia 07.10'da koddan okunarak doğrulandı; kaynağı yanında yazar. Görevler G267-G274 (PDF yolu) +
> G282-G288 (§6: yön/kaynak/durum modeli, Word yaşam döngüsü, eklenti — 07.10 ikinci onay, "birlikte geliştirelim").
>
> **PDF yolu TAMAM (07.10.2026 gece, sohbette elle koşu — `docs/plan/belge-tezgahi-elle-kosu-2026-10-07.md`; hepsi
> main, push'suz, deploy YOK):** G267 çekirdek **35cebfb** (81 test) → G268 uçlar + cache **0539ad4** (57) → G282
> migrasyon 61 **4ef2621** (31) → G269 karta bağla / karttan al **66f0483** (61; tam backend paketi 4566 passed, 25 skipped)
> ∥ G270 sayfa iskeleti **fa0479b** → G271 sayfa ızgarası **94948c1** → G272 karartma + not **d7c799e** → G273 kart
> diyalogları + `CaseDetails` **e2876ad** (frontend tam paket 1764 passed) → G274 doküman **134b169** (bu not + CLAUDE.md paragrafı +
> `belge-isleme-hatti.md` §9). §3 sözleşmesi hiçbir görevde değişmedi (G273 hizalama tablosu: fark
> yok). Sapmalar: sayfa yolu `/pdf-araclari` yerine **`/belge-tezgahi`** (K1, tek menü girişi); `lib/api.ts` uzun zaman
> aşımı öneki (G271); `save_case_document` kilitli kartta `KayitMesgulError` → `/confirm` 409 (G269, bilinçli).
> **Açık kalanlar (insan adımı, DURAK):** gerçek girişle tarayıcıda zincir (yükle → birleştir → karart → indir → karta
> bağla kesin + taslak → kartta görünür → "PDF araçlarında aç" → karttan al; dokunmatik cihazda kaydırma/çizim ayrımı;
> `03_TASLAKLAR/<ofis_no>` klasörünün Graph'ta ilk yüklemede oluşması), sonra deploy kararı (CI yeşil şartı, mesai dışı).
> **OCR kararı:** kapsam dışı kaldı (K9; Tesseract imaja girmedi) — tarama PDF'lerinde karartma yalnız görüntü piksellerini
> siler, metin katmanı yoktur; ayrı karar. **Görsel karşılaştırma** (Acrobat çıktısı ↔ HUKDOK çıktısı, özellikle sıkıştırma
> seviyeleri ve damga yerleşimi) yapılmadı — DURAK'ta kullanıcıyla. Word yolu G283'ten sürer (§6.4).

## 0. Doğrulanan zemin

| Konu | Bulgu | Kaynak |
| --- | --- | --- |
| Araçlar imajda | Ghostscript, LibreOffice writer/calc, `fonts-dejavu-core`, `fonts-liberation` apt ile; `pymupdf==1.28.2`, `Pillow` pip ile. Yeni bağımlılık GEREKMEZ. | `backend/Dockerfile:11-18`, `requirements.txt` |
| Dönüştürücüler | `format_converter.ensure_pdf(source, output=None)` (:171) resim/Office → PDF; `image_to_pdf` (:243), `office_to_pdf` (:324) `deadline` alır; semaforlar `_office_semaphore=2` (:51), `_image_semaphore=1` (:55); `acquire_conversion_slot` dolu kuyrukta `ConversionBusyError` (:126, çağıran 503 üretir); `_clip_timeout` (:159). `convert_to_pdfa2b(source, time_budget_seconds)` (`pdf_converter.py:39`), bütçe varsayılanı 270 sn (`settings.confirm_conversion_budget_seconds`). | okundu |
| Geçici dosya + indirme | `DOWNLOAD_CACHE = DiskTTLCache(..., ttl=settings.download_cache_ttl_seconds=3600)` (`routes/processing.py:68`); kayıt `{"path","filename","owner"}` (:899); `GET /api/download/{file_id}` sahibi uyuşmazsa 404 (:622-632). TTL yalnız indeksi siler, payload dosyasını `on_evict` SİLMİYOR (yalnız log). `case_intake.py:63` aynı cache'i kullanıyor. | okundu |
| Doğrulama | `file_utils.ALLOWED_EXTENSIONS` (:15: pdf udf tif tiff jpg jpeg png docx doc xlsx xls), `validate_file_type` magic-byte (:145), `validate_file_size` (:218, `max_upload_mb=50`); gövde sınırı `RequestSizeLimitMiddleware` 50 MB (`api.py:519`); akışta 413 örneği `processing.py:486-504`. Rate limit varsayılan 100/dk, uca özel örnek `client_errors.py:56` (`@limiter.limit`, `request: Request` zorunlu). | okundu |
| Karta belge kaydı | `/confirm` dışında HTTP ucu YOK. Orkestratör `document_pipeline.convert_pdfa_and_queue_uploads(...)` (:507): PDF/A + `save_case_document` (:40) + iki `enqueue_upload` (`upload_queue.py:94`). `case_intake.py:931` aynı yolu kullanır; klasör adları `SHAREPOINT_FOLDER_HAM_NAME`/`..._ISLENMIS_NAME` env'inden (:889-890). | okundu |
| Hukukbot aktarımı | `upload_queue._attempt_upload` URL yazılınca `notify_hukukbot(doc_id)` (:337-340); filtre `export_publisher.enqueue_document` (:36): TEST/URL'siz, `conversion_status` dolu, silinmiş dava, tür allowlist dışı belgeler GİRMEZ. Kartta kaydedilen PDF aracı çıktısı tür allowlist'teyse Hukukbot'a da akar — MEVCUT kural, bilinçli korunur. | okundu |
| Kart belge listesi | `pages/CaseDetails.tsx` içinde (satır bileşeni ≈ :203-345, sekme :1125-1230); veri `GET /api/cases/{id}` yanıtındaki `documents`; karta belge ekleme yalnız `/upload`'a yönlendirme (:533, :1207). Belgeyi aç: `GET /api/documents/{id}/download?inline=` (`routes/documents.py:286`, SharePoint proxy). | okundu |
| Sayfa/menü deseni | `App.tsx:42` lazy import + `:103-141` `ProtectedRoute > ShellLayout`; `/reports` herkese (:123), `/lexis` `ProtectedAdminRoute` (:125). Menü `components/shell/Sidebar.tsx:46-51` `ARACLAR` (`yalnizYonetici?`). Sayfa kabuğu `LexisPage.tsx:44` `useSetPageTitle`, `:94-104` başlık. `apiClient.fetch` FormData'da Content-Type'ı bırakır, 300 sn (`lib/api.ts:59,81,181`); blob indirme örneği `DashboardCalendar.tsx:134-149`. | okundu |
| Sürükle-bırak | `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities` zaten `frontend/package.json:17-19`'da. Yeni npm paketi GEREKMEZ. | okundu |
| Test kalıpları | Route: in-memory SQLite + `app.dependency_overrides[get_current_user]` (`tests/test_g078_son_belgeler_ucu.py:38-63`). PDF: fitz/PIL ile gerçek dosya, `tmp_path` (`tests/test_format_converter.py`). Frontend sayfa: `pages/LexisPage.test.tsx` (`vi.mock` + `createRoot` + `MemoryRouter`). | okundu |

## 1. Kararlar (öneri; onayla ya da değiştir)

- **K1 — Sayfa herkese açık.** Araçlar menüsünde tek giriş "Belge tezgâhı" (`/belge-tezgahi`; içinde "Düzenle (PDF)" ve
  "Yaz (Word)" yolları — §6), giriş yapan her kullanıcıya (Raporlar gibi);
  yönetici kısıtı yok. Gerekçe: Acrobat'ı kullanan idari personel ve avukatlar.
- **K2 — Çalışma dosyası = `DOWNLOAD_CACHE` kaydı.** Her yükleme ve her işlem çıktısı sahibine bağlı bir `file_id`
  alır (mevcut `/api/download/{file_id}` ile iner); bir işlemin çıktısı sonraki işlemin girdisi olur (zincir). Dosyalar
  `PDF_ARACLARI_DIR` (cache dizini altı, volume) içinde; TTL dolunca **payload da silinir** (`on_evict`, bugünkü boşluk
  kapanır — yalnız `kaynak == "pdf_araclari"` kayıtları için, mevcut `/process` kayıtlarına dokunulmaz).
- **K3 — Yüklenen her şey PDF'e çevrilir.** Yükleme ucu Office/resim/UDF'yi `ensure_pdf`/`_udf_to_pdfa2b` ile hemen
  PDF yapar; işlemler yalnız PDF üstünde çalışır. Tek giriş kapısı: `ALLOWED_EXTENSIONS` + magic-byte.
- **K4 — Çıktı PDF/A DEĞİL, karta bağlanınca olur.** Çalışma dosyaları düz PDF (Ghostscript sıkıştırması PDF/A
  uygunluğunu bozabilir). "Karta bağla" mevcut `convert_pdfa_and_queue_uploads` hattından geçer: PDF/A + ham/işlenmiş
  arşiv + bildirim + (tür allowlist'teyse) Hukukbot. `/process` analizi KOŞMAZ, e-posta GİTMEZ; belge türünü kullanıcı seçer.
- **K5 — Kart belgesi girdi olabilir.** "Karttan al": mevcut belge SharePoint'ten (`documents.py:286` proxy'sinin
  yardımcısıyla) çalışma dosyasına indirilir → duruşma dosyası = kart belgelerini seç → birleştir → indir/karta bağla.
- **K6 — Karartma gerçek silmedir.** PyMuPDF `add_redact_annot` + `apply_redactions` (metin VE görüntü pikselleri);
  test, karartılan alandaki metnin `get_text`'te kalmadığını ve görüntünün değiştiğini kanıtlar. Koordinat PDF puanı,
  sayfa sol-üst orijin (PyMuPDF düzeni); tarayıcı küçük resim pikselini ölçekle çevirir.
- **K7 — Damga/not Türkçe karakter.** Yerleşik Helvetica Türkçe glif taşımaz → `DejaVuSans.ttf` (imajda,
  `fonts-dejavu-core`) `fontfile` ile gömülür.
- **K8 — Sınırlar.** İşlem başına ≤ 20 girdi, çıktı ≤ 1.000 sayfa (`pdf_araclari_max_sayfa`), zaman bütçesi 270 sn
  (confirm ile aynı; nginx 300 sn), işlem semaforu 2 (`_pdf_arac_semaphore`; dolu → 503 "sistem meşgul"), uca özel
  rate limit `30/minute`. Yükleme dosya başına 50 MB (mevcut); birleştirmede dosyalar AYRI isteklerle yüklenir (gövde
  sınırı 50 MB).
- **K9 — Yeni bağımlılık yok.** Backend: pymupdf + Ghostscript + LibreOffice (kurulu). Frontend: `@dnd-kit` (kurulu).
  OCR katmanı (Tesseract) bu planın DIŞINDA — ayrı karar.
- **K10 — nginx değişmez.** Tüm uçlar `/api/pdf-araclari/...` altında; `location /api` zaten `backend:8001`'e gider,
  `proxy_read_timeout 300s` yeter. Önizleme PNG'leri `/api` altından gelir, `assets` önbellek kuralına GİRMEZ.

## 2. Mimari

```
tarayıcı  ──yükle (multipart)──▶  POST /api/pdf-araclari/yukle  ──ensure_pdf──▶  PDF_ARACLARI_DIR/<uuid>.pdf
                                                                                   │ DOWNLOAD_CACHE[file_id] = {path, filename, owner, kaynak:"pdf_araclari", sayfalar}
tarayıcı  ──islem (JSON)──▶      POST /api/pdf-araclari/islem   ──pdf_araclari.<islem>──▶ yeni file_id(ler)
tarayıcı  ◀─PNG──               GET  /api/pdf-araclari/onizleme/{file_id}/{sayfa}
tarayıcı  ◀─dosya──             GET  /api/download/{file_id}             (mevcut uç)
tarayıcı  ──karta-bagla──▶       POST /api/pdf-araclari/karta-bagla  ──convert_pdfa_and_queue_uploads──▶ case_documents + outbox
tarayıcı  ──karttan-al──▶        POST /api/pdf-araclari/karttan-al   ──SharePoint indir──▶ yeni file_id
```

Backend katmanları: `pdf/pdf_araclari.py` (saf fonksiyonlar, HTTP bilmez, `deadline` alır) → `routes/pdf_araclari.py`
(doğrulama, sahiplik, cache, semafor, 503/413/422) → `document_pipeline` (yalnız karta bağla). Frontend:
`pages/PdfAraclariPage.tsx` tek tezgâh (sol: dosyalar · orta: sayfa ızgarası · sağ: işlem paneli), `components/pdf/**`,
`lib/pdfAraclariApi.ts`.

## 3. API sözleşmesi (G267-G273 bu tabloya göre yazılır; değişiklik bu dosyadan geçer)

Ortak dosya nesnesi (`Dosya`):

```json
{"id": "uuid", "ad": "dilekce.pdf", "sayfa": 12, "boyut": 348211,
 "sayfalar": [{"no": 1, "genislik": 595.3, "yukseklik": 841.9}]}
```
`genislik/yukseklik` PDF puanı (döndürme uygulanmış görünür boyut). `id` sahibine bağlıdır; başkasının id'si her uçta 404.

| Uç | Gövde | Yanıt | Hata |
| --- | --- | --- | --- |
| `POST /api/pdf-araclari/yukle` | multipart `file` (TEK dosya; `ALLOWED_EXTENSIONS`) | `Dosya` | 413 boyut, 415 tür, 503 dönüşüm kuyruğu dolu, 422 dönüşüm başarısız |
| `POST /api/pdf-araclari/islem` | `{"islem": str, "girdiler": [id], "parametreler": {}, "cikti_adi"?: str}` | `{"ciktilar": [Dosya]}` (böl: birden çok) | 404 id, 422 parametre, 413 sayfa sınırı, 503 meşgul, 504 bütçe |
| `GET /api/pdf-araclari/onizleme/{id}/{sayfa}?genislik=240` | — | `image/png` (`Cache-Control: private, max-age=3600`) | 404 |
| `GET /api/download/{id}` | — | dosya (mevcut uç; `filename` cache'ten) | 404 |
| `POST /api/pdf-araclari/karta-bagla` | `{"id", "case_id", "belge_turu_kodu", "dosya_adi", "case_party_id"?: int, "istek_kimligi": uuid}` | `{"document_id": int, "reused": bool}` | 404 id/kart, 422 tür kodu/ad, 409 kilitli kart |
| `POST /api/pdf-araclari/karttan-al` | `{"document_id": int}` | `Dosya` | 404 belge/URL yok, 502 SharePoint |

`islem` değerleri ve `parametreler`:

| islem | parametreler | Davranış |
| --- | --- | --- |
| `birlestir` | — | `girdiler` sırasıyla tek PDF; çıktı adı `cikti_adi` ya da `birlestirilmis.pdf` |
| `bol` | `{"araliklar": [[1,3],[4,7]]}` YA DA `{"her_n": 1}` | her aralık ayrı çıktı; 1 tabanlı, kapalı aralık; çakışma/aşım 422 |
| `sayfa_duzenle` | `{"sayfalar": [{"no": 3, "dondur": 90}, {"no": 1}]}` | listedeki sıra = yeni sıra; listede olmayan sayfa SİLİNİR; `dondur` ∈ {0,90,180,270} mevcut döndürmeye EKLENİR; boş liste 422 |
| `sikistir` | `{"seviye": "ekran" \| "ebook" \| "yazici"}` | Ghostscript `-dPDFSETTINGS=/screen|/ebook|/printer`; çıktı girdiden büyükse girdi kopyası döner (`kucultme: 0`) |
| `karart` | `{"alanlar": [{"sayfa": 1, "x0", "y0", "x1", "y1"}]}` | PDF puanı, sol-üst orijin; metin + görüntü pikselleri silinir; alan sayfa dışına taşarsa kırpılır |
| `damga` | `{"metin": "ASLI GİBİDİR", "konum": "sag-ust" \| "sol-ust" \| "sag-alt" \| "sol-alt" \| "orta", "sayfalar": "hepsi" \| [no], "punto": 12, "renk": "#b00020"}` | DejaVuSans gömülü; metin ≤ 120 karakter |
| `not` | `{"sayfa": 1, "x", "y", "metin"}` | yapışkan not açıklaması (`add_text_annot`), ≤ 2.000 karakter |
| `donustur` | — | girdi zaten PDF (K3) → kopyası; uç yalnız sözleşme bütünlüğü için (yükleme dönüştürür) |

Yanıt üstbilgisi: her çıktı `Dosya.ad` sunucuda `sanitize_filename`'den geçer. Zincirde girdiler SİLİNMEZ (TTL siler);
kullanıcı sol listeden kaldırınca istemci yalnız kendi listesinden düşürür.

## 4. Görevler ve sıra

| Görev | Bant | Bağımlı | Kapsam |
| --- | --- | --- | --- |
| G267 | backend | - | `pdf/pdf_araclari.py` çekirdek (8 işlem + sayfa meta + önizleme render) + testler |
| G268 | backend | G267 | `routes/pdf_araclari.py` (`yukle`, `islem`, `onizleme`), cache `kaynak` + `on_evict` silme, ayarlar, `api.py` kaydı, testler |
| G269 | backend | G268, G282 | `karta-bagla` (+ `istek_kimligi` idempotent, `yon`/`durum`, taslak yolu) ve `karttan-al`, testler |
| G270 | frontend | - (sözleşme §3) | rota + menü + `lib/pdfAraclariApi.ts` + sayfa iskeleti: yükleme, dosya listesi, işlem paneli (birleştir/böl/sıkıştır/damga), indirme |
| G271 | frontend | G270 | sayfa ızgarası: önizleme, sürükle-sırala, döndür, sil, aralık seçimi → `sayfa_duzenle`/`bol` |
| G272 | frontend | G271 | karartma + not çizim katmanı (canvas overlay, piksel → PDF puanı) |
| G273 | frontend | G269, G271 | "Karta bağla" diyaloğu (dava arama, belge türü, taraf, yön, kesinleştir/taslak) + "Karttan al" + `CaseDetails` belge satırında "PDF araçlarında aç" / çoklu seç → birleştir |
| G274 | docs | G272, G273 | CLAUDE.md paragrafı, `docs/mimari/belge-isleme-hatti.md` yeni bölüm, bu planın durum notu |

Bağımlılık grafiği (PDF yolu): `G267 → G268 → G269` (backend seri; G269 ayrıca G282'e bağlı) ∥ `G270 → G271 → G272`;
`G273` iki zincirin birleşimi; `G274` PDF yolunun dokümanı. Word yolu ve toplam tahmin §6.4.

## 5. Riskler

- **Sözleşme sapması:** G270-G272 sahte API ile yazılır; gerçek backend'le ilk buluşma G273'tedir. Alan adı/şekil
  farkı bulunursa G273 **bu dosyayı** düzeltip iki tarafı hizalar (sözleşme tek kaynak).
- **Karartma koordinatı:** döndürülmüş sayfada PyMuPDF `page.rect` görünür boyutu verir, `rect` koordinatları
  döndürülmemiş sayfaya göredir; G267 `page.rotation_matrix` ile çevirir ve 90°/270° testleri yazar.
- **Ghostscript sıkıştırma süresi:** 200+ sayfalık taramada `/ebook` dakikalar sürebilir; `deadline` ile kesilir, 504
  döner, çalışma dosyası bozulmaz (çıktı geçici ada yazılır, sonda `os.replace`).
- **Payload temizliği:** K2'nin `on_evict` silmesi yalnız `kaynak == "pdf_araclari"` için; `_cleanup_process_cache`
  `/process` ve açılışta koşar (`api.py:301`, `processing.py:515`) — PDF aracı ucu da kendi başında çağırır.
- **CaseDetails hub dosyası:** yalnız G273 dokunur; aynı gece başka görev `CaseDetails.tsx`'e yazmaz (kuyrukta
  kontrol edildi: açık görevlerden G264 `components/lexis/**`'te).
- **Gece koşusu sonrası gerçek deneme:** yükleme/indirme/karta bağla zinciri gerçek girişle tarayıcıda denenir — İNSAN
  ADIMI, G274'ün ön koşulu değil ama deploy'un ön koşulu.


## 6. Birleşik belge tezgâhı: yön/kaynak/durum, Word yaşam döngüsü, eklenti (07.10 ikinci onay)

Kullanıcı 07.10'da üç isteği ekledi: (a) avukat **kendi yazdığı** belgeyi HUKDOK'a kaydetsin, "giden belgelere hâkim
olalım", ileride üstüne araç gelsin; (b) belge bir günde bitmez, **taslak + sürüm** şart; (c) PDF aracıyla **birlikte,
aynı amaca, aynı biçimde** gelişsin. Çözüm: iki aracın arka yarısı ortaktır (kart, tür, PDF/A, arşiv, bildirim, Hukukbot);
ön yarıları farklıdır (bitmiş sayfa işleri · yazma). Tek menü girişi "Belge tezgâhı", iki yol: **Düzenle (PDF)** ·
**Yaz (Word)**. Kartta tek "Belgeler" alanı: **Gelen · Taslak · Giden**.

### 6.1 Doğrulanan zemin (ek)

| Konu | Bulgu | Kaynak |
| --- | --- | --- |
| Yön/kaynak alanı | `case_documents`'ta belgenin yönü (gelen/giden), kaynağı ve taslak/kesin durumu YOK; `uploaded_by` `ARSIV_AKTARIM:<kim>` öneki tek kaynak izi (`models.py:1262`, `arsiv_karar_ekle.py`). | okundu |
| Son migrasyon | Madde 60 (arşiv belgesi parmak izi, `database.py:1488`). Yeni kolon/tablo **madde 61**; `("columns", ...)` koşullu, kalıcı index/kısıt ayrı `("index", ...)` op'unda (CLAUDE.md tuzağı). | okundu |
| SharePoint | Tek sürücü (`SHAREPOINT_SITE_URL` + `SHAREPOINT_DRIVE_NAME`), klasörler env ile (`01_HAM_ARSIV`, `02_YEDEK_ARSIV`; `.env.example:16-24`). `upload_file_to_sharepoint` (`sharepoint/sharepoint_uploader_graph.py:382`), `download_file_from_sharepoint` (:439), `get_file_meta_from_sharepoint` (:462). Küçük dosya `PUT .../content` aynı adı sormadan EZER (CLAUDE.md "ad çakışması"). | okundu |
| Export/bildirim filtresi | `export_publisher.enqueue_document` (:36-72): TEST, URL'siz, `conversion_status` dolu, silinmiş dava, allowlist dışı tür → GİRMEZ. `upload_queue._notify_document_processed` (:195) URL commit'inde koşar. İkisine `durum == KESIN` şartı eklenir. | okundu |
| Rapor kataloğu | `belgeler` kaynağı `services/rapor/registry.py` (elle kolon listesi yazılmaz; kolon eklemek = registry tanımı). | CLAUDE.md |
| Word belgesi üretimi | Repoda python-docx YOK; UDF üretimi var (`/api/yetki-belgesi/udf`). Boş/şablon `.docx` = repo içinde statik varlık (`backend/sablonlar/bos.docx`), yeni bağımlılık gerekmez. | okundu |
| Eklenti kimliği | HUKDOK token kuralı `aud=api://<client>`, `scp=access_as_user` (CLAUDE.md). Office eklentisi MSAL.js **NAA** (nested app auth) ile AYNI uygulama kaydından aynı scope'u alabilir → backend doğrulaması değişmeyebilir; alınamazsa ikinci audience (`ALLOWED_AUDIENCES`) gerekir — G286 ölçer. CSP başlıkları konteyner nginx'inde üç yerde (`nginx.conf:48-51`); Office.js `appsforoffice.microsoft.com` izni ister. | okundu |

### 6.2 Kararlar (K11-K18)

- **K11 — Üç yeni belge alanı.** `case_documents.yon` (`GELEN` | `GIDEN`, varsayılan GELEN), `kaynak` (`BELGE_HATTI` |
  `PDF_ARACLARI` | `WORD` | `ARSIV_AKTARIM` | `TESLIM`, varsayılan BELGE_HATTI), `durum` (`TASLAK` | `KESIN`, varsayılan
  KESIN). Mevcut kayıtlar GELEN/KESIN; `uploaded_by LIKE 'ARSIV_AKTARIM:%'` → kaynak ARSIV_AKTARIM. Tür bu alanların
  yerine GEÇMEZ (dilekçe iki yönde de olur).
- **K12 — Taslak = kesinleşmemiş belge.** TASLAK: Hukukbot'a GİTMEZ, bildirim ÜRETMEZ, raporda "giden" SAYILMAZ, PDF/A
  yapılmaz; dosyası `SHAREPOINT_FOLDER_TASLAK_NAME` (varsayılan `03_TASLAKLAR`) `/<ofis_no>/` altında (aynı sürücü, ayrı
  üst klasör; ayrı kütüphane ikinci sürücü kimliği isterdi, ilk sürümde değil). Word taslağı `.docx` olarak orada
  durur: Word'ün otomatik kaydetme, birlikte düzenleme ve sürüm geçmişi SharePoint'ten gelir, HUKDOK bunu YENİDEN YAZMAZ.
- **K13 — Sürüm defteri HUKDOK'ta.** `belge_surumleri` (document_id, surum_no, sha256, sharepoint_etag, not,
  olusturan_email, olusturulma; UNIQUE (document_id, surum_no)). Satır yalnız bilinçli "Sürüm kaydet"te ve
  kesinleşmede açılır (SharePoint'in her otomatik kaydı DEĞİL).
- **K14 — Kesinleşme tek yönlüdür.** `kesinlestir`: SharePoint'teki `.docx` indirilir → PDF/A → işlenmiş arşiv (yeni dosya) +
  `.docx` ham arşive, AYNI belge satırı `durum=KESIN`, `kesinlesme_tarihi/kesinlestiren_email`, son sürüm satırı; URL
  commit'inde bildirim + Hukukbot (allowlist) tetiklenir. Kesinleşmiş belge düzenlenemez; düzeltme = yeni taslak
  (`onceki_document_id` bağı), eskisi "gönderildi" kalır: "mahkemeye ne gitti" değişmez.
- **K15 — İki başlangıç yolu.** HUKDOK'tan: kartta "Yeni belge" (tür + ad + şablon) → `03_TASLAKLAR/<ofis_no>/<ad>.docx`
  (`bos.docx` kopyası; ad çakışmasında `get_file_meta` ile bakılır, varsa `-2` eki) → `word_url` + `ms-word:ofe|u|<url>`
  bağlantısı. Word'den (eklenti): açık belge `getFileAsync` ile yüklenir → aynı uç.
- **K16 — Eklenti HUKDOK'un bir sayfasıdır.** `/eklenti` rotası (SPA içinde, Office.js CDN'den), manifest
  `frontend/public/eklenti/manifest.xml`, aynı origin → CORS yok. Kimlik NAA ile aynı scope hedeflenir (G286 ölçer).
  **Dağıtım Microsoft 365 yönetici merkezinden — İNSAN ADIMI**, kuyruk yapmaz.
- **K17 — PDF tezgâhı da taslak kaydedebilir.** "Karta bağla" diyaloğunda "Taslak olarak kaydet": PDF kartın
  Taslaklar'ına düşer (1 saat sınırı yalnız karta bağlanmamış dosyalar için kalır). Aynı defter, aynı kesinleştirme.
- **K18 — İleriki araçlar yön alanına dayanır** (şablon kütüphanesi, gönderim kanalı kaydı: UYAP/e-posta/elden, giden
  evrak defteri raporu, süre hesabını giden belgeyle başlatma). Bu planın DIŞINDA; alanlar onlar için hazırlanır.

### 6.3 API sözleşmesi (ek; G282-G287 bu tabloya göre)

| Uç | Gövde | Yanıt | Not |
| --- | --- | --- | --- |
| `GET /api/cases/{id}` `documents[]` | — | her belgede `yon`, `kaynak`, `durum`, `word_url?`, `kesinlesme_tarihi?`, `surum_sayisi` | mevcut yanıt genişler |
| `GET /api/cases/{id}/documents?yon=&durum=` | — | süzülmüş liste | mevcut uç, iki filtre |
| `POST /api/cases/{id}/belgeler/yeni` | `{"belge_turu_kodu", "ad", "sablon"?: "bos", "case_party_id"?}` | `{"document_id", "word_url", "word_ac"}` (`word_ac` = `ms-word:ofe` protokol bağlantısı) | TASLAK/GIDEN/WORD; 409 ad çakışması çözülemezse |
| `POST /api/documents/{id}/surum` | `{"not"?: str}` | `{"surum_no", "sha256", "degisti": bool}` | SharePoint meta + indirme ile sha; aynı sha → `degisti:false`, satır yine açılır (not için) |
| `GET /api/documents/{id}/surumler` | — | `[{"surum_no","sha256","not","olusturan_email","olusturulma","kesin": bool}]` | |
| `POST /api/documents/{id}/kesinlestir` | `{"istek_kimligi"}` | `{"document_id", "reused"}` | K14; zaten KESIN → 409; dönüşüm meşgul 503 |
| `POST /api/documents/{id}/yeni-surum-taslagi` | `{"istek_kimligi"}` | `{"document_id": yeni}` | KESIN belgeden yeni TASLAK (`.docx` ham arşivden kopyalanır, `onceki_document_id`) |
| `POST /api/pdf-araclari/karta-bagla` | + `"yon"`, `"durum"` | — | §3 ile aynı; K17 |

### 6.4 Görevler (ek), sıra ve tahmin

| Görev | Bant | Bağımlı | Kapsam |
| --- | --- | --- | --- |
| G282 | backend | - | Migrasyon 61: `yon`/`kaynak`/`durum`/`word_url`/`kesinlesme_*`/`onceki_document_id` + `belge_surumleri`; backfill; export/bildirim filtresi `durum==KESIN`; kart yanıtı + liste filtresi; rapor `belgeler` kolonları; `SHAREPOINT_FOLDER_TASLAK_NAME` |
| G283 | frontend | G273, G282 | Kart "Belgeler": Gelen · Taslak · Giden sekmeleri/rozetleri, yön-kaynak çipleri, tipler |
| G284 | backend | G282, G269 | Word yaşam döngüsü uçları: `yeni` (bos.docx + ad çakışması), `surum`, `surumler`, `kesinlestir`, `yeni-surum-taslagi`; sahte Graph testleri |
| G285 | frontend | G284, G283 | "Yeni belge" diyaloğu, "Word'de aç", "Sürüm kaydet" + sürüm listesi, "Kesinleştir" onayı, "Yeni sürüm taslağı"; tezgâhta "Yaz (Word)" yolu |
| G286 | backend | G284 | Eklenti altyapısı: nginx CSP'ye Office.js kaynakları (üç yerde), `/eklenti/manifest.xml` servis + bekçi, token audience ölçümü (NAA aynı scope mu?) + gerekiyorsa `ALLOWED_AUDIENCES` |
| G287 | frontend | G286, G285 | `/eklenti` görev bölmesi: Office.js + MSAL NAA giriş, kart ara, "Taslak kaydet" (`getFileAsync` → yeni/sürüm), "Kesinleştir"; manifest; yönetici dağıtımı İNSAN ADIMI |
| G288 | docs | G287, G274 | CLAUDE.md "Belge tezgâhı" paragrafı (PDF + Word + eklenti), `belge-isleme-hatti.md`, `docs/mimari/genel-bakis.md`, plan durumu |

Zincirler: backend seri `G267 → G268 → G282 → G269 → G284 → G286`; frontend `G270 → G271 → G272 → G273 → G283 → G285 → G287`
(G273 G269'u, G283 G282'i, G285 G284'yi, G287 G286'u bekler); docs `G274` (PDF) → `G288` (bütün).
**Tahmin 7-8 gece:** gece 1 `G267 → G268` ∥ `G270 → G271`; gece 2 `G282 → G269` ∥ `G272`; gece 3 `G284` ∥ `G273 → G283`;
gece 4 `G286` ∥ `G285` → `G274`; gece 5 `G287`; gece 6 `G288` + takılanlar. Eklentinin yönetici dağıtımı ve gerçek
girişle deneme kuyruk dışı insan adımı.

### 6.5 Riskler (ek)

- **Migrasyon + hub dosyalar:** G282 `models.py`, `database.py`, `registry.py`, `routes/documents.py`, `routes/cases.py`
  yanıtına dokunur; backend seri olduğu için çakışma yok, ama G269 bunun ÜSTÜNE yazar: sıra `G282 → G269`.
- **SharePoint ad çakışması:** küçük dosya yüklemesi aynı adı EZER; `yeni` ucu önce `get_file_meta` ile bakar (CLAUDE.md
  arşiv kuralıyla aynı), çakışmada `-2`, `-3` eki.
- **Kesinleştirme sırasında Word açık:** SharePoint son kaydedilmiş hali verir; Word'de kaydedilmemiş değişiklik PDF/A'ya
  girmez. Diyalog uyarır ("Word'de kaydettiğinizden emin olun"); K13 sha ile kullanıcı sürüm kaydında farkı görür.
- **Eklenti kimliği:** NAA ile aynı scope alınamazsa `ALLOWED_AUDIENCES` + token doğrulayıcı değişir (kimlik-ve-token
  dokümanı); G286 bunu test eder, gerekirse BLOKE bırakır ve kullanıcı kararı ister (Azure uygulama kaydı değişikliği
  İNSAN ADIMI). **G286 sonucu (08.10, belge ölçümü):** NAA token'ı aynı kayıt + aynı scope → `aud` aynı; doğrulayıcı
  DEĞİŞMEDİ. İNSAN ADIMI: uygulama kaydına SPA yönlendirmesi `brk-multihub://hukukoid.com` + `https://hukukoid.com/eklenti`
  (`kimlik-ve-token.md` §2.5). Canlı claim teyidi G287 sonrası.
- **CSP:** Office.js için `script-src`/`connect-src`/`frame-ancestors` genişler; `add_header` kopyaları birlikte değişir,
  bekçi testi eşitliği doğrular. **G286 (08.10):** Office.js CDN'i değişmiş — `officeapis.public.onecdn.static.microsoft`
  (eski `appsforoffice`; Ajax artık yüklenmez → `ajax.aspnetcdn` gereksiz); `connect-src` değişmedi (MSAL zaten vardı);
  `frame-ancestors` yalnız `/eklenti` location'ında açık.
- **Word Online mı masaüstü mü:** `ms-word:ofe|u|` bağlantısı masaüstü Word'ü açar, yoksa `word_url` Word Online'ı; iki
  yol da SharePoint oturumu ister (kullanıcı HUKDOK'a Microsoft hesabıyla girdiği için genelde açık).
