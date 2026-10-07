# PDF araçları sayfası planı (07.10.2026)

> **Durum: ONAYLANDI (07.10.2026).** Kullanıcı 07.10'da Acrobat aboneliğini yenilemeden PDF işlerini HUKDOK'tan yapmak
> istedi; "Acrobat yerine HUKDOK ile PDF işleri" belgesi (Claude Docs + masaüstü, 07.10) önerinin gerekçesidir. Bu
> dosya uygulama planı ve **frontend ile backend'in paralel koşabilmesi için sabitlenen API sözleşmesidir** (§3).
> Her iddia 07.10'da koddan okunarak doğrulandı; kaynağı yanında yazar. Görevler G267-G274.

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

- **K1 — Sayfa herkese açık.** `/pdf-araclari` Araçlar menüsünde, giriş yapan her kullanıcıya (Raporlar gibi);
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
| G269 | backend | G268 | `karta-bagla` (+ `istek_kimligi` idempotent) ve `karttan-al`, testler |
| G270 | frontend | - (sözleşme §3) | rota + menü + `lib/pdfAraclariApi.ts` + sayfa iskeleti: yükleme, dosya listesi, işlem paneli (birleştir/böl/sıkıştır/damga), indirme |
| G271 | frontend | G270 | sayfa ızgarası: önizleme, sürükle-sırala, döndür, sil, aralık seçimi → `sayfa_duzenle`/`bol` |
| G272 | frontend | G271 | karartma + not çizim katmanı (canvas overlay, piksel → PDF puanı) |
| G273 | frontend | G269, G271 | "Karta bağla" diyaloğu (dava arama, belge türü, taraf) + "Karttan al" + `CaseDetails` belge satırında "PDF araçlarında aç" / çoklu seç → birleştir |
| G274 | docs | G272, G273 | CLAUDE.md paragrafı, `docs/mimari/belge-isleme-hatti.md` yeni bölüm, bu planın durum notu |

Bağımlılık grafiği: `G267 → G268 → G269` (backend seri) ∥ `G270 → G271 → G272`; `G273` iki zincirin birleşimi; `G274` son.
**Tahmin 3 gece:** gece 1 `G267 → G268` ∥ `G270 → G271`; gece 2 `G269` ∥ `G272`; gece 3 `G273 → G274`.

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
