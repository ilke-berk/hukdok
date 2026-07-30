# Otonom Dava Açma — Geliştirme Planı

*Tarih: 2026-07-24 · Eş dosya: [otonom-dava-acma-hazirlik-raporu-2026-07-24.md](otonom-dava-acma-hazirlik-raporu-2026-07-24.md)*

Hedef akış: belgeleri tek seferde yükle → sistem dava kartını doldurur → kullanıcı tik'lerle onaylar → **tek "Kaydet"** ile dava oluşur + belgeler bağlanır/arşivlenir. Ara kayıt yok.

## İş Kalemi 1 — Backend: analiz, birleştirme, commit

**Yeni dosyalar:** `backend/routes/case_intake.py`, `backend/services/case_intake.py`, `backend/case_intake_analyzer.py`, `backend/schemas_intake.py`, `backend/prompts.py`'a yeni fonksiyon.
**Değişen:** `backend/api.py` (router), `backend/analyzer.py` (`_step_*` yardımcılarının dışarıdan çağrılabilirliği — küçük imza ayarı gerekebilir, yarım gün bütçele).
**DB migration GEREKMİYOR** — Case/CaseParty/CaseDocument her şeyi karşılıyor.

### Endpoint'ler (dört ince sarmalayıcı)

**`POST /api/case-intake/analyze`** — multipart, tek dosya. `/process` ile aynı şekilli NDJSON stream döner. Frontend dosyaları sırayla döngüler (1 aktif + 1 preload — kanıtlanmış Index.tsx deseni). Tek-N-dosyalık endpoint yerine bu tercih edildi: belge-başı ilerleme ve hata izolasyonu bedava, sunucu-tarafı oturum durumu PROCESS_CACHE dışında yok, Gemini rate limit'ine uygun. Terminal olay:
```json
{"status":"complete","process_id":"<uuid>","data":{ "...CaseIntakeExtraction...": "", "belge_turu_kodu_tahmini":"..." }}
```
İçerde `case_intake_analyzer.analyze_intake_file_generator(...)`: analyzer'ın dönüşüm/mod adımları + kendi AI adımı: `GenerateContentConfig(system_instruction=..., response_mime_type="application/json", response_schema=CaseIntakeExtraction)`, paylaşılan retry. PDF'i PROCESS_CACHE'e `/process` ile aynı hijyenle koyar.

**`POST /api/case-intake/merge`** — durumsuz JSON; frontend aldıklarını geri yollar:
```json
{ "documents": [ { "process_id":"…", "filename":"…", "extraction":{} } ] }
```
Dönen taslak, **kaynak bilgisiyle (provenance)**:
```json
{
  "fields": {
    "esas_no": {"value":"2024/123","candidates":[{"value":"2024/123","count":3},{"value":"2023/98","count":1}],"agreement":0.75,"sources":["dilekce.pdf","tensip.pdf"]},
    "court": {"value":"ANKARA 3. ASLİYE HUKUK MAHKEMESİ","agreement":1.0,"sources":["..."]},
    "file_type": {}, "sub_type": {}, "opening_date": {}, "subject": {}
  },
  "parties": [
    {"name":"AHMET YILMAZ","role":"Davacı","party_type":"CLIENT","tc_no":"…","doc_count":3,"sources":["..."],"match":{"client_id":12,"score":0.94}},
    {"name":"XYZ SİGORTA A.Ş.","role":"Davalı","party_type":"COUNTER","doc_count":2}
  ],
  "duplicate_case": {"id":88,"tracking_no":"…","score":0.9},
  "policies": [
    {"police_no":"…","sigorta_sirketi":"…","baslangic":"2023-05-01","bitis":"2024-05-01","sigortali":"AHMET YILMAZ","source":"police1.pdf","relevant":true}
  ],
  "warnings": [ {"code":"POLICY_PERIOD_OVERLAP","message":"Aynı tip iki poliçenin dönemleri çakışıyor: … / …"} ],
  "documents": [ {"process_id":"…","filename":"…","belge_turu_kodu":"…","suggested_name":"…","ozet":"…","status":"ok"} ]
}
```
Birleştirme mantığı `services/case_intake.py`'de **saf fonksiyonlar** (Gemini'siz unit-test edilir):
- `merge_esas_no`: normalize → çoğunluk oyu; beraberlik → en yeni `belge_tarihi`; tüm adaylar döner.
- `merge_court`: normalize + çoğunluk (ham string; base+daire parse'ı frontend'de ortak yardımcıyla).
- `merge_parties`: `normalize_person_name` anahtarıyla birleşim; kişi başına en sık rol; party_type: müvekkil matcher / client DB eşleşmesi → CLIENT, karşı yaka → COUNTER, MÜDAHİL/İHBAR OLUNAN → THIRD; TC herhangi bir belgede varsa korunur.
- `merge_dates`: açık dava açılış tarihi varsa o; yoksa dilekçe sınıfı belgenin en erken tarihi.
- `merge_subject`: dava dilekçesi özeti öncelikli.
- `merge_policies`: poliçe alanları çoğunluk oyuna GİRMEZ — bir hekimin birden fazla poliçesi olabilir; poliçe/zeyilname belgelerinden hekim başına poliçe LİSTESİ toplanır (police_no, sigorta_sirketi, dönem başlangıç/bitiş, sigortalı). Açılış/olay tarihi hangi poliçe dönemine düşüyorsa o poliçe `relevant` işaretlenir. **Aynı tip (aynı şirket/branş) poliçelerde dönem çakışması varsa `warnings`'e POLICY_PERIOD_OVERLAP uyarısı eklenir** — sihirbazda amber banner olarak gösterilir.
- Duplicate: `case_matcher.find_matching_case`.
- Ayrıca listelenen tüm process_id'lerin PROCESS_CACHE TTL'ini tazeler (keepalive'ın parçası).

**`POST /api/case-intake/commit`** — TEK kayıt:
```json
{
  "case": { "...CaseCreate, tracking_no dahil...": "" },
  "documents": [ {"process_id":"…","new_filename":"…","belge_turu_kodu":"…","ai_ozet":"…","esas_no":"…","muvekkil_adi":"…"} ],
  "options": {"send_email": false}
}
```
Davranış:
1. `add_case` — atomik; `duplicate_tracking_no` → 409 (frontend sequence yenileyip 1 kez otomatik dener).
2. Belge başına: `accept_incoming_file` → `validate_tenant_and_resolve_lawyer` → `convert_pdfa_and_queue_uploads(linked_case_id=yeni_dava)` → `schedule_cleanup`. Her biri try/except: **dava oluşturma transactional, arşivleme belge-başı best-effort** — başarısız/TTL-dolmuş belge akışı öldürmez, yanıtta `{"status":"failed"|"expired"}` döner (sonuç ekranı "davaya git, tekrar yükle" yönlendirir).
3. E-posta: `options.send_email` açıksa mevcut `send_notification_email` (varsayılan kapalı).

**`POST /api/case-intake/keepalive`** `{process_ids:[…]}` — PROCESS_CACHE tazeler; sihirbaz review adımında 10 dk'da bir çağırır (hazırlık raporu Risk 4 sigortası).

### Çıkarım motoru: BAĞIMSIZ ve çok geçişli

Intake çıkarım motoru belge yükleme hattından **tamamen bağımsız** kurulur — kendi prompt'u, kendi şeması, kendi işlem ayarları. Maliyet kısıtı yok. Sonuçları:

- **Model (Faz 0 kalibrasyon kararı, 2026-07-30):** intake motoru `/process`'in flash-lite'ını DEĞİL, tam flash sınıfını kullanır (env `GEMINI_INTAKE_MODEL`, kalibrasyonda `models/gemini-3.6-flash`). Ölçüm: 16 poliçede sigortalı hekim çıkarımı flash-lite ensemble=3'te 9/15 (düşük anlaşma) iken 3.6-flash'ta **16/16 tam anlaşmayla** çıktı; uzmanlık 7/16→16/16. Koşu süresi ~2x, karar net.

- **Sayfa kırpma YOK:** `/process`'in "ilk 2 + son sayfa" kırpması intake'te uygulanmaz; belge tam gönderilir (dava belgelerinde kritik bilgi ortada olabiliyor — en büyük doğruluk kazanımı).
- **Katman 1 — Ensemble:** belge başına aynı çıkarım N=3 kez koşulur, alan bazında çoğunluk oyu. Tek seferlik halüsinasyon elenir.
- **Katman 2 — Doğrulayıcı geçiş:** kritik alanlar (esas_no, taraf rolleri, tc_no) için ikinci çağrı: "değer belgede geçiyor mu, kanıt cümlesi ne?" Kanıtsız değer düşük güvenli işaretlenir → sihirbazda rozet rengi.
- **Katman 3 — Belgeler-arası hakem:** merge çelişki bulduğunda (esas_no/mahkeme anlaşmazlığı) tüm çıkarımları+özetleri gören bir hakem LLM çağrısı meşru farkları ayırt eder (yeni esas, istinaf mahkemesi, birleşen dosya) ve gerekçeli karar döner; gerekçe sihirbazda gösterilir. Çelişki yoksa hakem çağrılmaz.
- **Regex'in rolü:** birincil çıkarıcı değil, çapraz kontrol — regex ile AI aynı değeri bulursa güven skoru yükselir.
- Tam araçlı otonom ajan (sayfa gezen, DB sorgulayan) v1'e alınmaz — kapalı uçlu çıkarımda ölçülebilir kazanım yok, belirsizlik ekler. Çok büyük demetlerde seçici okuma → v2 adayı.

Efor etkisi: analyze fazına +1–1.5 gün. Merge çıktısındaki `agreement` alanı artık belge-arası uyum + ensemble uyumu + regex çapraz kontrolünün bileşik güven skorudur.

### Veritabanı destekli zenginleştirme

Alanlar doldurulurken DB **hem çıkarımı yönlendirir hem sonucu düzeltir** — ama daima *destek* rolünde: belge kanıtı birincil, DB önerisi rozet/düzeltme olarak sunulur, sessizce üzerine yazmaz.

1. **Prompt'a DB bağlamı enjeksiyonu (çıkarım öncesi):** mevcut desen genişletilir — `get_system_instruction` nasıl dynamic_lawyers/doctypes alıyorsa, intake prompt'u da şunları alır:
   - Büro avukat listesi (vekil adı → ofis avukatı eşleşmesi → `responsible_lawyer` önerisi),
   - İzinli değer listeleri: yargı türü, alt tür/uzmanlık (`specialties`), dava konuları (`caseSubjects`) — AI serbest metin yerine bu listelerden seçer (schema'da enum ya da prompt kısıtı); listede yoksa serbest metin + "listede yok" bayrağı.
2. **FlashText müvekkil taraması (`list_searcher.py`, HAZIR):** DB'deki tüm müvekkil adları belge metninde taranır. Intake'te iki işlevi: (a) bulunan adlar prompt'a "bu kişiler büronun kayıtlı müvekkili olabilir" ipucu → CLIENT/COUNTER ayrımı isabetlenir; (b) AI'nin bulduğu adla çapraz kontrol → güven skoruna katkı.
3. **İsim kanonikleştirme (merge sonrası):** eşleşen müvekkilin DB'deki kanonik adı öneri olarak gösterilir ("AHMET YILMAZ → Ahmet YILMAZ (kayıtlı müvekkil #12)" rozeti, tek tıkla kabul). `muvekkil_matcher_v2` + `party_check.normalize_person_name`; TC varsa TC öncelikli eşleşme.
4. **Müvekkil geçmişinden alan öncelikleri (prior):** taraf kayıtlı müvekkille eşleşirse geçmiş davalarından örüntüler düşük-güvenli ön-dolgu olarak önerilir: en sık uzmanlık/alt tür, en sık sorumlu avukat, kategori kodu. Belgeyle çelişirse belge kazanır; DB önerisi popover'da "geçmiş davalarında genelde X" olarak durur.
5. **Mahkeme adı normalizasyonu:** merge'in mahkeme çıktısı mevcut davalardaki adlarla fuzzy eşlenir; bilinen yazım önerilir (serbest yazım kirliliğini önler).
6. **Tanıdık sorgu + duplicate:** `check_parties` çakışma kontrolü ve `find_matching_case` mükerrer dava uyarısı bu katmanın parçası.

Uygulama yeri: 1–2 analyze fazında (prompt/şema), 3–5 merge servisinde (saf fonksiyon + DB okuma; testlerde client_rows fixture'ı). Efor: +1 gün (çoğu mevcut bileşenin yeniden bağlanması).

### Yapılandırılmış çıkarım şeması (`backend/schemas_intake.py`)
```python
class IntakeParty(BaseModel):
    ad: str
    rol: Literal["DAVACI","DAVALI","MUDAHIL","IHBAR_OLUNAN","VEKIL","DIGER"]
    tc_no: Optional[str] = None

class CaseIntakeExtraction(BaseModel):
    belge_turu_tahmini: Optional[str] = None   # serbest metin; koda map backend'de
    mahkeme: Optional[str] = None              # daire dahil tam ad
    esas_no: Optional[str] = None              # "YYYY/N"
    yargi_turu: Optional[str] = None           # Hukuk/Ceza/İcra/İdari/Arabuluculuk/Savcılık
    dava_konusu: Optional[str] = None
    belge_tarihi: Optional[str] = None         # ISO
    dava_acilis_tarihi: Optional[str] = None
    taraflar: list[IntakeParty] = []
    ozet: Optional[str] = None
```
Prompt: `prompts.py`'a `get_case_intake_instruction()` — dava kartı odaklı, açık rol kuralları ("davacı/davalı yalnızca başlık bloğundan; vekilleri taraf listeleme, rol=VEKIL"), regex ön-çıkarım ipuçları (tarih/esas_no/mahkeme) enjekte edilir ve merge'e düşük ağırlıklı aday olarak da geçer.

## İş Kalemi 2 — Frontend: Sihirbaz

**Yeni:** `frontend/src/pages/CaseIntakeWizard.tsx`, `frontend/src/hooks/useCaseIntake.ts`, `frontend/src/lib/caseIntakeFields.ts`, `frontend/src/components/intake/` altında `IntakeUploadStep.tsx`, `IntakeProgressStep.tsx`, `IntakeReviewStep.tsx`, `IntakeFieldRow.tsx`, `IntakeResultStep.tsx`.
**Değişen:** `frontend/src/App.tsx` (route `/new-case/auto`), `frontend/src/pages/CaseList.tsx:270` ("Yeni Dava Aç" → DropdownMenu: "Belgelerden Otomatik Aç" / "Manuel Aç"), `caseNumberUtils.ts` (QuickCaseModal'daki mahkeme base+daire parser'ı ortak yardımcı olarak dışarı alınır).

### Akış (tek sayfa, adım state'i)
1. **Yükleme:** çoklu dosya dropzone (max ~15, `/process` uzantı beyaz listesi). "Analiz Et"e kadar işlem başlamaz.
2. **Çıkarım ilerlemesi:** dosyalar sırayla (`useCaseIntake.analyzeFile`, NDJSON reader). Adım başında ortalama süre beklentisi gösterilir ("N belge × ~X sn ≈ toplam ~Y dk" — X kalibrasyon ölçümünden sabitlenir, ensemble=3 ile belge başına ~25-30 sn). Satır başına: ad, canlı durum, sonuç çipleri (esas no / mahkeme / N taraf) veya kırmızı "başarısız" (akış devam eder, başarısız belge merge dışı ama listede). Hepsi bitince otomatik `/merge`. (v2: analiz bitince bildirim — kullanıcı sekmede beklemek zorunda kalmasın.)
3. **İnceleme ("Dava Kartı Onayı") — UX'in kalbi:**
   - Alanlar **`caseIntakeFields.ts`**'ten render edilir:
     ```ts
     export interface IntakeFieldDef { key: keyof CaseCreatePayload; label: string;
       widget: "text"|"date"|"court"|"select"; required?: boolean; enabled: boolean; }
     export const INTAKE_FIELDS: IntakeFieldDef[] = [ /* esas_no, court, file_type, sub_type, opening_date, subject, notes, lawyers, uyap_lawyer */ ];
     ```
     Alan çıkarma = `enabled:false`. Çıkarma adayları (klasör/hasar/hukuk no, tazminat, atama/iş kabul tarihi, hizmet türü, büro özel türü) bu listeye **hiç girmez**.
   - **`IntakeFieldRow`**: değer editörü (ön-dolu) + kaynak rozeti ("3/4 belge · dilekce.pdf"; adaylar anlaşmazsa popover'da tıkla-seç) + onay Checkbox'ı (tik).
   - **Onay semantiği:** boş olmayan her AI değeri kaydetten önce tiklenmeli; *alanı düzenlemek otomatik tikler*; kullanıcının boşalttığı alan boş kaydedilir; boş AI alanı tik istemez. "Kaydet" tüm boş-olmayan alanlar + en az 1 CLIENT taraf onaylanana dek pasif; "7/9 alan onaylandı" sayacı. (Halüsinasyonun incelenmeden kayda girmesini engeller.)
   - **Taraflar bloğu:** ad/rol/TC düzenlenebilir satırlar, party_type toggle (Müvekkil/Karşı/3. Kişi), satır-başı tik, `PartyMatchIndicator` noktası, merge müşteri eşleşmesi bulmuşsa bağlantı gösterimi. Manuel satır ekle/sil.
   - **Ofis No:** ilk CLIENT onaylanınca client-side üretilir (`client-sequence` + `generateTrackingNumber`; kategori önceliği aynen), salt-okunur + yeniden-üret ikonu.
   - **Duplicate uyarısı:** `duplicate_case` varsa amber banner "Bu dava zaten kayıtlı olabilir: [tracking_no] — Görüntüle / Yine de devam et".
   - **Poliçe bloğu:** merge'in `policies` listesi hekim başına gösterilir (birden fazla poliçe desteklenir); dava tarihine denk düşen poliçe "ilgili" rozetiyle vurgulanır; `POLICY_PERIOD_OVERLAP` uyarısı amber banner ("Aynı tip poliçelerde dönem çakışması var — kontrol edin"). Poliçe bilgisi dava kartına notes içinde yazılır (ayrı DB alanı yok; kalıcı poliçe kaydı → açık soru #6).
   - **Belge şeridi:** belge başına: ad (düzenlenebilir, öneriden ön-dolu), belge türü select (AI tahmini + `predictDocTypeFromName` fallback), özet.
   - Bu adım açıkken 10 dk'da bir keepalive.
4. **Kaydet:** tek **"Kaydet ve Arşivle"** → `/commit`. 409'da: sessizce sequence yenile, tracking_no yeniden üret, 1 kez dene. Sonuç ekranı: dava linki + belge-başı arşiv durumu (queued/failed/expired + yönlendirme).

## İş Kalemi 3 — CaseTrackingPanel tek-Kaydet dönüşümü (bağımsız, İLK çıkar)

**Değişen:** `frontend/src/components/CaseTrackingPanel.tsx`, `backend/managers/case_manager.py` (`update_case_tracking`), `backend/routes/cases.py:394`.
1. Üç kayıt yolu → tüm aşamaların STAGE_FIELDS'ı + `dosya_son_durumu`'nu kapsayan tek taslak nesne; panel-geneli tek "Kaydet" + "Kaydedilmemiş değişiklikler" rozeti. `handleStageClick` taslağı artık sıfırlamaz — sadece görünen dilimi değiştirir (mevcut veri kaybı bug'ı kapanır).
2. **Aşama geçişi (`confirmStage`) istisna kalır:** dialog onaylı, anlık — CaseStageLog'u süren semantik bir *olay*; UI metninde belirtilir.
3. Ayrılma koruması: `beforeunload` + panel içi sekme/aşama değişiminde confirm dialog (BrowserRouter kullanıldığından `useBlocker` yok; router migrasyonu kapsam dışı).
4. Backend: `update_case_tracking`'de `exclude_unset` semantiği (route `model_dump(exclude_unset=True)` geçer; manager mevcut her anahtarı `None` dahil uygular) — alan silme çalışır olur.

## İş Kalemi 4 — Sertleştirme (MVP sonrası)
1. `update_case` taraf sil-yeniden-oluştur → `case_party_id` öksüzleşmesi düzeltmesi (diff bazlı güncelleme veya yeniden-oluşturma sonrası normalize ada göre re-link). Sihirbaz belge-taraf bağı kurduğundan önemi artıyor.
2. client-sequence fallback düzeltmesi / 409 telemetrisi.
3. `service_type` kaderi (persist et ya da formdan da kaldır).

## Test
- **Backend (pytest KONTEYNERDE** — host py3.13 uyumsuz): `backend/tests/test_case_intake_merge.py` — saf merge fonksiyonları (esas_no çoğunluk/beraberlik, Türkçe aksanlı taraf dedupe, rol→party_type, tarih seçimi); `test_case_intake_commit.py` — conftest desenleriyle, pipeline fonksiyonları monkeypatch'li (dava oluşur, belge-başı hata izolasyonu, 409 yolu). Prompt kalibrasyonu CI'da değil, kalibrasyon script'iyle manuel.
- **Frontend (vitest host'ta):** `caseIntakeFields` bütünlüğü; review adımı onay/kirli mantığı saf reducer'a (`intakeReviewReducer.ts`) çekilip unit-test (tik kapısı, düzenlemede oto-tik, 409 retry kararı); `caseNumberUtils` testleri ortak mahkeme parser'ı için genişletilir.

## Fazlama

| Faz | İçerik | Efor | Bağımsız çıkar mı? |
|---|---|---|---|
| 0 | Örnek belge demetleri, kalibrasyon script'i, schema/prompt iterasyonu, alan seti taslağı | 1–2 g (çoğu dev-dışı) | — |
| 1 | İş Kalemi 3 (takip paneli tek-Kaydet + PATCH null düzeltmesi) | 1–1.5 g | **Evet — anında UX kazanımı** |
| 2 | Analyze endpoint + schema/prompt + ensemble/doğrulayıcı (`case_intake_analyzer`, `/analyze`) | 3–3.5 g | Kalibrasyon script'iyle test edilir |
| 3 | Merge servisi + DB zenginleştirme + **kalıcı poliçe tablosu (migration + müvekkil kartı UI)** + endpoint + testler; keepalive | 3.5–4.5 g | Evet (API-tamam) |
| 4 | Commit endpoint + testler | 1 g | Evet |
| 5 | Sihirbaz frontend (4 adım + CaseList girişi) | 4–5 g | **Özellik burada çıkar** |
| 6 | Sertleştirme | 1–2 g | Kalem kalem bağımsız |

## Kararlar (2026-07-30, kullanıcı onaylı — açık soru kalmadı)
1. **Model:** intake motoru `models/gemini-3.6-flash` (env `GEMINI_INTAKE_MODEL`); yavaşlık kabul edildi, doğruluk öncelikli.
2. **Ensemble N=3 kalıcı**; Katman 2 doğrulayıcı geçiş yalnız kritik alanlara (esas_no, TC, taraf rolleri).
3. **Kalıcı poliçe tablosu (seçenek b):** hekim (client) kaydına bağlı `client_policies` tablosu — poliçe bir kez kaydedilir, sonraki davalarda otomatik önerilir, dönem çakışması uyarısı kalıcı veriyle çalışır. DB migration + müvekkil kartı UI'ı Faz 3'e eklendi (+1.5–2 gün).
4. **Tazminat alanları sihirbaza DAHİL** (kalibrasyonda dilekçeden 5/5 güvenilir çıktı; plandaki "hariç" kararı geri alındı).
5. Sihirbaz durumu: **sabit DERDEST**.
6. Commit'te müvekkile e-posta: **varsayılan kapalı toggle**.
7. Oturum başına **max 15 belge**. Çıkarım adımında UI'de **ortalama süre beklentisi** gösterilir ("belge başına ~X sn sürer" — kalibrasyon ölçümünden).
8. `hasar_dosya_no`/`hukuk_no`: şimdilik kapsam dışı — kullanıcı sigorta atama yazısı örnekleri getirecek, alanlar o zaman kalibre edilip eklenecek.
9. Tiklenmemiş alan politikası: boş olmayan AI değeri zorunlu tik, düzenlemede oto-tik — kullanılırken kalibre edilir.
10. Çıkarılan alan kesin listesi: `caseIntakeFields.ts`'e ertelendi; Faz 5 cilası öncesi donmalı.

**v2 notları:** analiz bitince kullanıcıya push/uygulama içi bildirim ("analiz bitti, incelemeye dön" — kullanıcı sihirbazda beklemesin); vekaletnameden avukat/uyap_lawyer çıkarımı.

## Doğrulama (uçtan uca)
1. **Faz 1:** dava detayında takip panelinde birden çok aşamada alan değiştir → tek Kaydet ile hepsi yazılmalı; aşama sekmesi değiştir → veri kaybolmamalı; tarih sil + kaydet → DB'de null olmalı (konteynerde pytest + elle UI).
2. **Faz 2–4:** kalibrasyon script'i örnek PDF demetiyle koşulur, alan doğruluğu ölçülür; konteynerde `pytest tests/test_case_intake_*.py`.
3. **Faz 5:** lokalde docker compose ile: 3–5 gerçek belge yükle → çıkarım ilerlemesi izle → review'da alanları tikle/düzenle → Kaydet → dava listesinde görünmeli, belgeler davaya bağlı + SharePoint kuyruğunda olmalı; 409 senaryosu (aynı client'la ikinci dava) otomatik retry ile geçmeli; 30 dk bekletme senaryosunda keepalive sayesinde commit çalışmalı. Frontend vitest host'ta.
4. Prod'a mesai dışı, `--build` ile.
