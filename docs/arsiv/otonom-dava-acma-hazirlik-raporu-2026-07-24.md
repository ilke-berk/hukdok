# Otonom Dava Açma — Hazırlık Raporu (Mevcut Durum Değerlendirmesi)

*Tarih: 2026-07-24 · Eş dosya: [otonom-dava-acma-gelistirme-plani-2026-07-24.md](otonom-dava-acma-gelistirme-plani-2026-07-24.md)*

## Amaç ve kapsam

Dava dosyası açma özelliği elden geçirilip otonom hale getirilecek: kullanıcı davayla ilgili tüm belgeleri **tek seferde** yükleyecek, sistem belgelerden dava kartı bilgilerini (taraflar + rolleri, mahkeme, esas no, tarihler, konu) otomatik çıkaracak, kullanıcıya yalnızca **onaylamak (tik atmak)** ve **tek "Kaydet"** kalacak. Ara kayıt olmayacak — kayıt yalnızca en sonda yapılacak. Açılışta alınan bazı bilgiler formdan çıkarılacak.

**Netleşen kararlar:**
- Yeni sihirbaz mevcut manuel formun **yanında** durur (NewCase kalır; "Yeni Dava Aç" → "Belgelerden Otomatik Aç" / "Manuel Aç").
- Belge akıbeti **tam entegre**: kaydette belgeler davaya bağlanır + PDF/A + SharePoint arşivi (mevcut pipeline yeniden kullanılır).
- Çıkarılacak alan adayları: eski sistem numaraları (Klasör No, Hasar Dosya No, Hukuk No), tazminat alanları, Atama Tarihi + İş Kabul Tarihi, Hizmet Türü + Büro Özel Türü. Kesin liste gerçek belgelerle test edilince donacak → alan seti **tek config dosyasında** tutulacak (çıkarma = config düzenlemesi).
- "Her bilgi yazıldığında kaydetme" şikayeti **dava detayındaki takip panelinde** (CaseTrackingPanel) yaşanıyor → ayrı iş kalemi olarak tek-Kaydet'e çevrilecek.
- Intake çıkarım motoru belge yükleme hattından **bağımsız** olacak (kendi prompt/şema/ayarları); maliyet kısıtı yok, çok geçişli (ensemble + doğrulayıcı) çalışacak.
- Alanlar doldurulurken **veritabanı desteği** kullanılacak (müvekkil adı, uzmanlık alanı vb. — destek rolünde, belge kanıtı birincil).

## 1. Yeniden kullanılabilir varlıklar (yeniden yazma yok)

| Varlık | Konum | Kullanım |
|---|---|---|
| Tek-belge analiz motoru (UDF/görsel→PDF, sayfa kırpma, taranmış/metin tespiti, regex ön-çıkarım, retry'lı Gemini çağrısı) | `backend/analyzer.py` — adımlar zaten fonksiyon: `_step_udf_conversion` (297), `_step_format_conversion` (344), `_step_decide_mode` (409), `_step_ai_call` (619) | Sihirbazın belge-başı çıkarımı dönüşüm/mod adımlarını aynen kullanır; prompt+schema+post-process farklı |
| NDJSON streaming deseni | `backend/routes/processing.py` `/process` (319) + Index.tsx tüketimi | Sihirbaz ilerleme akışı için aynı sözleşme |
| Analiz↔kayıt arası PDF tutma | `PROCESS_CACHE` (TTL 30dk, processing.py:32), `accept_incoming_file` (document_pipeline.py:141) | N PDF, dosya başına bir process_id |
| Arşiv hattı (PDF/A-2b + DB satırı + SharePoint) | `document_pipeline.convert_pdfa_and_queue_uploads` (254) → `save_case_document` (29) — GS Unicode fix'i dahil, savaş görmüş kod | Commit endpoint'i belge başına çağırır; **yeniden yazma yasak** |
| Dava oluşturma | `case_manager.add_case` (462-607): 7 formatlı tarih parse, taraf auto-link/create, avukat kanonikleştirme, duplicate tracking_no → 409 | Commit aynen çağırır |
| Mevcut dava tespiti | `case_matcher.find_matching_case` | "Bu dava zaten kayıtlı olabilir" uyarısı |
| Taraf normalize/çakışma | `party_check.normalize_person_name` + `check_parties`; frontend `PartyMatchIndicator` + `useInlinePartyCheck` | Belgeler arası taraf dedupe + tanıdık sorgu noktası |
| Müvekkil tespiti | `muvekkil_matcher_v2` hibrit matcher | CLIENT vs COUNTER ayrımı |
| DB müvekkil taraması | `backend/list_searcher.py` (FlashText, DB'den yüklenir, reload destekli) | Belge metninde kayıtlı müvekkil tespiti → prompt ipucu + çapraz kontrol |
| Ofis No üretimi | `frontend/src/lib/caseNumberUtils.ts` + `GET /api/cases/client-sequence` | Sihirbaz aynen kullanır; **isim bloğu kategori önceliğine dokunulmaz** (bilinçli karar) |
| Mahkeme parse, tür listeleri | `QuickCaseModal.tsx` (court→base+daire, DOSYA_TURLERI/ALT_TURLER) | Review adımı widget'ları |
| Gemini client | `backend/gemini_client.py` (google-genai 2.11.0) | `response_mime_type="application/json"` + `response_schema=<Pydantic>` destekli — yapılandırılmış çıktı sadece config değişikliği |

## 2. Sorunlar / Riskler (bu yenilemeyle ilgili)

1. **AI çıktısında rol yok.** Mevcut çıkarım düz `muvekkiller[]` / `belgede_gecen_isimler[]` / tek `karsi_taraf` döner — davacı/davalı ayrımı, TC, alan bazlı kaynak yok. Dava kartı bundan kurulamaz → yeni yapılandırılmış prompt + response_schema **zorunlu**.
2. **Elle JSON parse** (`_extract_first_json` brace-counting). 15 alanlı iç içe schema için kırılgan; yeni akışta response_schema bunu ortadan kaldırır.
3. **Backend'de batch kavramı yok.** Batch = frontend döngüsü (Index.tsx fileQueue). Sunucu tarafı birleştirme/uzlaştırma katmanı sıfırdan yazılacak.
4. **PROCESS_CACHE TTL = 30 dk.** Sihirbaz oturumu (10 belge yükle → incele → kaydet) 30 dk'yı aşabilir; PDF'ler uçar, commit belge-başı patlar. → keepalive + commit'te "süresi doldu, yeniden yükle" zarif yolu şart.
5. **`update_case` tarafları sil-yeniden-oluştur yapıyor** (case_manager.py:336-451) → parti id'leri her düzenlemede değişir, `case_documents.case_party_id` (FK SET NULL) **öksüz kalır**. Sihirbaz belge-taraf bağı kurduğu için bu gizli bug görünür hale gelecek — hardening'de düzeltilmeli.
6. **`service_type` sessizce düşüyor** — CaseCreate kabul ediyor, `add_case` hiç persist etmiyor (mevcut bug). Hizmet Türü zaten çıkarma adayı: sihirbaz alan setine alınmaz; manuel form kararı ayrı.
7. **client-sequence yarışı** (cases.py:89-133; legacy count fallback hâlâ çakışmaya açık). Sihirbaz 409 `duplicate_tracking_no` alırsa **otomatik yeniden üret + 1 kez tekrar dene** (NewCase şu an sadece hata basıyor).
8. **`update_case_tracking` alan sıfırlayamıyor** (`field in data and data[field] is not None`, 610-668). Takip paneli toplu kayda geçince tarih silme çalışmalı → `exclude_unset` semantiğine geçilecek.
9. **CaseTrackingPanel parçalı kayıt (kodda doğrulandı):** debounce YOK; üç ayrı kayıt noktası var — `saveDosyaSonDurumu` (112), `saveFields` (159), `confirmStage` (177) — ve `handleStageClick` (142-151) aşama değişiminde kirli formu **uyarısız sıfırlıyor** (veri kaybı). İş: tek panel-geneli taslak + tek Kaydet.
10. **DANIŞ modu:** sihirbaz gerçek dava açar → sabit DERDEST önerilir (durum yine görünür/onaylanır).
11. **İş kuyruğu yok, gerekmez de.** Frontend döngüsü + NDJSON v1 için yeterli; kuyruk eklenmeyecek.

Not: Dava açma formunun kendisinde (NewCase.tsx) alan-bazlı otomatik kayıt YOK — kayıt zaten tek butonla yapılıyor. Şikayetin kaynağı takip paneli (madde 9).

## 3. Geliştirme öncesi hazırlıklar

1. **Gerçek örnek belge demetleri (prompt işi için BLOKER).** 5–10 gerçek dava açılışı (dilekçe + tensip + tebligat + vekaletname vb.). Alan seti ve çıkarım doğruluğu bunlarla kalibre edilecek.
2. **Kalibrasyon script'i:** UI'sız prompt iterasyonu için — yeni prompt'u örnek PDF'lere koşturup JSON döker (commit edilmez, scratchpad'de).
3. **Schema kararı:** tüm belge türleri için **tek** çıkarım şeması (önerilen; birleştirme adımı belge türüne göre ağırlıklandırır).
4. **Alan seti dondurma:** `caseIntakeFields.ts` config'i sayesinde ertelenebilir; Faz 5 (UI cilası) öncesi kesinleşmeli.
5. **Onaylanacak kararlar:** commit'te e-posta bildirimi (öneri: varsayılan kapalı, tek toggle); oturum başına max dosya (öneri: 15); sihirbaz durumu (öneri: sabit DERDEST).
