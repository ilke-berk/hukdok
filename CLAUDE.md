# CLAUDE.md — HUKDOK çalışma rehberi

Hukuk bürosu belge otomasyonu: belge yükle → Gemini ile analiz → onayla → SharePoint
arşivi + veritabanı kaydı → hukukbot'a aktarım. FastAPI backend + React/Vite frontend +
PostgreSQL; kimlik Azure AD (MSAL). Bu dosya sıfır-context bir oturumun giriş noktasıdır.

> **ALTIN KURAL:** Buraya ve `docs/mimari/` altına yazılan her operasyonel iddia
> (komut, yol, port, sayı) **koddan okunarak ya da koşularak** doğrulanır.
> `docs/arsiv/` içinden veya ezberden KOPYALAMA. Doğrulayamadığını yazma.
> Kod ile doküman çelişirse kod haklıdır — dokümanı düzelt.

## Mimari özet

**Servisler** (`docker-compose.yml`): `postgres` (postgres:15-alpine, 127.0.0.1:5432),
`backend` (`hukdok_backend`, python:3.13-slim, 127.0.0.1:8001), `frontend` (nginx,
127.0.0.1:8080 → konteyner 80). **Üç port da loopback'e sabit** — dışarıya açık tek kapı
host nginx'tir (prod 443); bekçi `backend/tests/test_port_baglama.py`. API-key'li
`/export` route'ları public'e açılmaz; hukukbot ortak `hukuk_shared` Docker ağından
`http://hukdok_backend:8001` ile konuşur. **Hukukbot'a kullanıcı erişimi yalnız HUKDOK'tan**
(karar 021): kendi sitesi/girişi/arayüzü yok; `/hukukbot` sayfası (`pages/HukukbotPage.tsx`) HUKDOK'un access
token'ıyla aynı origin'den `/hukukbot-api/` önekine konuşur (`lib/hukukbotApi.ts`), Hukukbot token'ı
HUKDOK kuralıyla (`ALLOWED_TENANTS`, `aud=api://<client>`, `scp=access_as_user`) kendisi doğrular; frontend
konteyneri bu yüzden `hukuk_shared` ağındadır. Vite dev sunucusu 127.0.0.1:5173 (strictPort).
Port haritası: `docs/mimari/genel-bakis.md` §1.

**İki katmanlı nginx:** Repodaki `nginx.conf` **konteyner** nginx'idir: `listen 80`
(compose 127.0.0.1:8080:80 yayınlar), SPA'yı servis eder; `/api`, `/process`, `/confirm`,
`/preview-email-body`, `/preview-client-email-body`, `/refresh`, `/healthz` →
`backend:8001` proxy.
`proxy_read_timeout 300s` (GhostScript PDF/A dönüşümü 60s'yi aşabilir; 504 = mükerrer
kayıt kaynağıydı). **Önbellek (G182, `nginx.conf:80-102`):** hash'li Vite parçaları
`location ~* ^/assets/` → `Cache-Control: public, max-age=31536000, immutable`; eksik parça
`=404` döner, index.html'e DÜŞMEZ (açık eski sekmede `frontend/src/lib/chunkReload.ts` sayfayı
bir kez yeniler). `location /` (index.html + SPA fallback) → `no-cache`. `add_header` kalıtım
tuzağı: location'da tek `add_header` bile server düzeyindekileri düşürür → beş güvenlik başlığı
iki location'da AYNEN tekrar yazılıdır, birini değiştiren üç yeri değiştirir (`nginx.conf:48-51`).
Konteynerler düz HTTP konuşur; TLS prod'daki **host** nginx'inde sonlanır (konfigin repodaki
kopyası `infra/nginx/sites-available/default`, sunucuya `infra/install.sh` kurar; iki katmanın
timeout'ları eşit tutulmalı — bkz. `nginx.conf:10-14`). Repodaki host konfiginde `add_header`
/ `proxy_hide_header` yok; sunucudaki konfigin bununla aynı olduğu ve `Cache-Control`'un
tarayıcıya ulaştığı **prod'da doğrulanacak** (`curl -sI https://<alan>/assets/<parça>.js`,
`curl -sI https://<alan>/`). `/export` konteyner nginx'ine ASLA eklenmez (`nginx.conf:117`).
**Hukukbot proxy'si (karar 021, G203, `nginx.conf:172-207`):** `location ~ ^/hukukbot-api/(ask|sessions|download)(/|$)`
önek atılarak (`rewrite ... break`) `hukuk_shared` üzerinden `hukukbot_api:8010`'a gider; allowlist dışı her
`/hukukbot-api` yolu (`/ingest`, `/health` dahil) `return 404`. **Gecikmeli DNS:** upstream değişkenle
(`set $hukukbot_upstream`) + `resolver 127.0.0.11 valid=30s` — düz `proxy_pass` Hukukbot kapalıyken HUKDOK
nginx'ini AÇILMAZ yapardı; böyle yalnız o istekler 502. `X-User-OID` silinir, `proxy_buffering off` (NDJSON
akışı), location'da `add_header` yok. Bekçi `backend/tests/test_nginx_hukukbot.py`.

**Backend açılışı** (`backend/docker-entrypoint.sh`): önce `migrate.py` tek süreçte
koşar (hata = konteyner durur, bozuk şemayla kalkılmaz), sonra uvicorn
`--workers ${UVICORN_WORKERS:-2}`. **2 worker + lider kilidi:** süreç-tekil arkaplan
işleri kilit dosyası üzerinden (flock/msvcrt, `services/singleton_lock.py`) yalnız
lider worker'da başlar (`api.py` lifespan): APScheduler (günlük aktivite raporu 00:00 TR,
dönüşüm retry 02:30 TR, süre/duruşma taraması 06:00 TR) + SharePoint upload outbox worker'ı
(`services/upload_queue.py`) + veri teslim açılış toparlaması (`teslim_kutusu.boot_toparla`).
Refresh thread'i ise BİLEREK worker-başınadır (süreç-içi singleton cache'ler).

**Veri teslim hattı:** veri ekibi `HUKDOK_TESLIM_*.xlsx` paketini bize iletir; yönetici admin
panelinden yükler (`services/teslim_kutusu.py`, sha256) → `aktarim_teslimleri` defteri + spool →
doğrula → kuru koş (`scripts/hukdok_aktarim.aktarimi_kos`, yalnız import edilir) → kapı
(env eşikleri `TESLIM_KAPI_*`; ilk teslim ve envanter farkı daima `inceleme_bekliyor`) →
**uygulamayı daima yönetici "Uygula" başlatır** → eşleşme/havuz farkı CSV'leri rapor dizinine
(`services/teslim_cevap.py`, panelden indirilir). Panelsiz yol CLI: `hukdok_aktarim.py` kuru koşu →
`--apply`. **SharePoint teslim klasörü yolu 17.09.2026'da KALDIRILDI** (gözcü, 04:00 gece turu,
`cevap/` yüklemesi, `TESLIM_SHAREPOINT_*` ikinci kimliği, `/aktarim/tara`,
`veri_teslim_otomasyonu` anahtarı — bekçi `tests/test_teslim_klasoru_kaldirildi.py`).
`DEGISIKLIK_OZETI` üç satır taşır: "Önceki teslim" (zincir; `—` yalnız defter boşken
başlangıçtır), "Teslim türü: tam | delta" (delta'da kaybolan sütun ihlal değil bilgi; eksik
sütun/föy = dokunma) ve "Veri kesim tarihi" (yoksa paket adındaki tarih). Kapı eşiği
`alan_degisikligi` KART HÜCRESİ sayar (tarih/tutar biçimi üretmez, ad yazımı üretir).
"Paket kazanır" kuralının tek istisnası kesim-sonrası kullanıcı korumasıdır (G152; 12.09'da
`status`'tan HER kart alanına genellendi): bizde DOLU bir alan için kesim gününden itibaren o alanda
kullanıcı imzalı (`source` NULL ya da `HUKDOK_TESLIM` dışı) `case_history` kaydı varsa paket o alanı
yazmaz/boşaltmaz, satır raporuna `KORUNDU` düşer (hata değil; bizde BOŞ alanı paket doldurur —
`scripts/hukdok_aktarim.py::_kart_alanlarini_yaz` + `kesim_sonrasi_kullanici_kaydi`).
Tek SharePoint kimliği arşivindir (LexisBio: arşiv/export). Ayrıntı
`docs/mimari/veri-teslim-hatti.md`; veri ekibine verilen sözleşme `docs/veri-teslim/SOZLESME.md`.

**Belge akışı:** `/process` → `analyzer.analyze_file_generator` NDJSON stream'i →
kullanıcı onayı → `/confirm` (idempotent: `process_id` anahtarlı `ConfirmReceipt` DB
kaydı, `services/confirm_idempotency.py`) → belge kaydı + SharePoint upload outbox →
upload başarılı olup `sharepoint_url` yazılınca `services/export_publisher.notify_hukukbot`:
filtrelerden geçen belge `export_outbox`'a "pending" düşer + hukukbot'a webhook atılır
(ulaşamazsa sorun değil — hukukbot'un periyodik reconcile'ı toparlar; doğruluk garantisi
outbox + reconcile'dadır, webhook yalnız gecikmeyi sıfırlar). `/process` analiz sırasında
SharePoint'e çıkmaz: eski belge sayacı kaldırıldı (G242; dava kartının ofis numarası
`cases.tracking_no` ayrı konudur, DB'de üretilir — aşağıdaki "Ofis no" maddesi). **Toplu yüklemede ek bağlama (20.09):** tezgâhta bir satır
başka satırın e-posta EKİ olabilir (tebligat dilekçesi + mazbata): ek satır kendi başına
arşivlenir (`send_email=false`), dosyası ana satırın `/confirm`'üne `extra_attachment_files` ile
biner; toplu akışta e-postası açık tebligat ya da ekli satırda EmailModal ZORLA açılır
(`lib/tebligatDoctype.ts`); dosya başına meta `File` anahtarlıdır (`Index.tsx` `BatchFileMeta`).
Ayrıntı `docs/mimari/belge-isleme-hatti.md` §3.

**Belge tezgâhı — PDF araçları (07.10, G267-G273; plan `docs/plan/pdf-araclari-plani-2026-10-07.md`):** Acrobat yerine
PDF işleri HUKDOK'ta. Sayfa `/belge-tezgahi` (Araçlar menüsü, giriş yapan HERKESE — `App.tsx:126`, `Sidebar.tsx:51`;
"Yaz (Word)" yolu G285'e dek kapalı). Uçlar `routes/pdf_araclari.py` (`/api/pdf-araclari/{yukle,islem,onizleme/{id}/{sayfa},
karta-bagla,karttan-al}`; indirme mevcut `/api/download/{id}`), çekirdek `pdf/pdf_araclari.py` (HTTP bilmez, `deadline` alır;
sekiz işlem: birleştir · böl · sayfa_duzenle · sıkıştır (Ghostscript) · karart · damga · not · donustur). **Çalışma dosyası =
`DOWNLOAD_CACHE` kaydı** `{path, filename, owner, kaynak:"pdf_araclari", sayfa, sayfalar}`; başkasının id'si her uçta 404;
dosya `PDF_ARACLARI_DIR` altında, TTL 1 saat dolunca payload da silinir (`processing._download_evict`, yalnız bu kaynak);
her işlem çıktısı yeni id'dir, girdiler listede kalır (zincir). Yükleme Office/resim/UDF'yi hemen PDF yapar (K3); çıktılar düz
PDF, PDF/A karta bağlanınca. **Koordinat sözleşmesi:** karartma/not/damga alanları GÖRÜNÜR sayfa düzleminde, sol-üst orijin,
PDF puanı (`Dosya.sayfalar[].genislik/yukseklik` döndürme uygulanmış) — çekirdek `derotation_matrix` ile çevirir, tarayıcı
yalnız ölçekler (`components/pdf/pdfKoordinat.ts`). **Karartma gerçek silmedir** (`apply_redactions`, metin + görüntü
pikselleri; ekranda onay kutusu olmadan istek gitmez). **Karta bağla** (`durum=KESIN`): MEVCUT
`document_pipeline.convert_pdfa_and_queue_uploads` hattı (PDF/A + iki arşiv + URL commit'inde bildirim ve Hukukbot allowlist
kuralı AYNEN; `/process` analizi ve e-posta YOK); `durum=TASLAK` (K12/K17): PDF/A yok, tek `islenmis` kuyruğu
`03_TASLAKLAR/<ofis_no>/` (`SHAREPOINT_FOLDER_TASLAK_NAME`), G282 kapıları taslağı export'tan ve bildirimden eler
(`export_publisher.py:66`, `upload_queue.py:223`). `istek_kimligi` (UUID) ile idempotent (`confirm_idempotency`, anahtar
`pdf_araclari:<uuid>`, tekrar → `reused: true`); kilitli kart 409 — `save_case_document` artık `KayitMesgulError` yükseltir
(`/confirm`'ü de etkiler, G269). **Karttan al:** arşivdeki belge (`sharepoint_url` dolu) SharePoint'ten çalışma dosyasına.
**Sınırlar (K8, `config/settings.py:83-85`):** işlem başına 20 girdi, çıktı ≤ 1.000 sayfa (413), bütçe 270 sn (504),
semafor 2 (`_pdf_arac_semaphore`, dolu → 503), uca özel `30/minute`; yükleme 50 MB; `islem` JSON olduğu için
`lib/api.ts:78` uzun zaman aşımı önekinde. **Belge modeli (G282, migrasyon 61):** `case_documents.yon` (GELEN|GIDEN) /
`kaynak` (BELGE_HATTI|PDF_ARACLARI|WORD|ARSIV_AKTARIM|TESLIM) / `durum` (TASLAK|KESIN) + `word_url`, `onceki_document_id`
(`models.py:1318-1324`), sürüm defteri `belge_surumleri` (`models.py:1332`). nginx DEĞİŞMEDİ (her yol `location /api` altında,
`nginx.conf:119`); yeni bağımlılık yok (pymupdf + Ghostscript imajda, `@dnd-kit` kurulu); OCR kapsam DIŞI (ayrı karar).
Gerçek girişle tarayıcı denemesi ve deploy İNSAN ADIMI (plan DURAK). Ayrıntı `docs/mimari/belge-isleme-hatti.md` §9.

**Arşiv belgesi (05.10, migrasyon 60):** büro karar arşivi kartlara `/process` → `/confirm` hattından GEÇMEDEN,
`backend/scripts/arsiv_karar_ekle.py` ile eklenir (İNSAN ADIMI; varsayılan kuru koşu, girdi depo dışındaki eşleştirme
listesi: karar → föy). Kayıt `uploaded_by = ARSIV_AKTARIM:<kim>`, `uploaded_at` = KARAR TARİHİ (yükleme anı değil),
bildirim ve `notify_hukukbot` yok. İki adım: `--liste` belge kaydını açar (`sharepoint_url` boş: kartta listelenir,
açılamaz), `--yukle --pdf-dizini` PDF'i arşive yükleyip URL'i yazar — `upload_queue`'dan GEÇMEZ (o yol bildirim +
Hukukbot aktarımı üretir; `export_outbox`'a satır düşmediği için export'a da girmez). **Arşivde ad çakışması:** küçük
dosya yüklemesi (`PUT .../content`) aynı addaki dosyayı sormadan EZER → toplu yükleme her dosyadan önce
`sharepoint_uploader_graph.get_file_meta_from_sharepoint` ile bakar (aynı boyut = önceki koşu, URL alınır; farklı boyut =
`AD_CAKISMASI`, dokunulmaz).
İki yeni kolon: `case_documents.dosya_sha256` (kart başına aynı dosya tek kayıt — kısmi unique `uq_case_docs_kart_sha`)
ve `case_documents.asama_karari_id` (belge → `case_stage_decisions`; künye tek satırla tutmuyorsa BOŞ, tahmin edilmez).
Belge hattından gelen kayıtlarda iki kolon bugün yazılmaz. **05.10: belge kayıtları yalnız LOKAL veritabanında
(3.111 belge, 1.924 kart; 355 kopya tarama soft-delete), prod'da KOŞULMADI; PDF'ler ise GERÇEK arşive yüklendi
(`02_YEDEK_ARSIV`, 3.466 dosya) — prod'da `--liste` sonrası `--yukle` yeniden yüklemez, URL'leri bağlar. Prod girdisi
depo dışında: `C:\hukdok-veri\lexis\kararlar\rapor\arsiv_karar_liste_prod.csv`.** Ayrıntı `docs/plan/karar-belgeleri-calisma-plani-2026-10-05.md` §5.3-§5.4.

**Uygulama içi bildirim** (`docs/mimari/bildirimler.md`): kanal yalnız zil, e-posta
değil. Üreticiler `belge_islendi` (URL commit sonrası; gündüz `upload_queue` ve gece
`conversion_retry`), `sure_yaklasti`/`durusma_yaklasti` (06:00 TR lider taraması,
`services/deadline_scanner.py`). Alıcı = sorumlu avukat(lar) + `email_recipients.notify_copy`
kopya alıcıları − belgeyi yükleyen (`notification_targeting.resolve_notification_recipients`);
allowlist `NOTIFICATION_DOMAINS`. Süre uyarısının TEK kaynağı `case_stage_decisions.teblig_tarihi`;
`/confirm`'de karar belgesiyle girilen tebliğ tarihi oraya yazılır
(`processing.KARAR_DOCTYPE_TO_DECISION_STAGE`, boş alan dolar dolu alan ezilmez).

**Hata bildirimi (02.10, `docs/mimari/bildirimler.md` §7):** kart alanlarının yanındaki kırmızı zil
(`components/hata/HataBildirimi.tsx`; dava kartı + müvekkil hızlı bakışı) → `POST /api/hata-bildirimleri`
(`routes/hata_bildirimleri.py`, tablo `hata_bildirimleri`, hedef dava YA DA müvekkil) → alıcıların ziline
`hata_bildirimi`. **Alıcıyı bildiren seçer** (`GET /alicilar`: idari personel + iç avukatlar + `ADMIN_EMAILS`
yöneticisi, adı `ADMIN_ADLARI` env'inden; sunucu seçimi bu havuza karşı doğrular, serbest adres 422); ön-seçim
son seçim, yoksa `email_recipients.notify_error_reports`, o da yoksa `notify_copy`. Alıcı kartın üstündeki
şeritten düzeltip kapatır (`/kapat`: COZULDU | REDDEDILDI, tek yönlü) → bildirene `hata_sonucu`. Zil hedefi
`notifications.link` (sunucu üretir). Açık bildirimler idari panoda da listelenir. Rol yok: herkes bildirir/kapatır.
**Doğrudan düzeltme:** davanın sorumlu avukatı ya da yönetici, `DOGRUDAN_DUZELTME_ALANLARI`ndaki serbest metinli
alanı (esas no, hasar/hukuk/klasör no, yargı birimi) "Emin misiniz?" onayıyla kendisi yazar (`dogrudan_duzelt=true`
→ `enrich_case`, tarihçe `source=HATA_DUZELTME`; bayat ekran 409) — listeye yeni alan eklemeden önce o alanın
serbest metinle yazılabildiğini doğrula (kapalı liste / tarih / tutar / avukat alanı EKLENMEZ).

**Ofis no (karar 023, G235-G242):** `<MÜVEKKİL KODU>-<SIRA>[-<SİGORTALI>]-<TÜR>` — `DR.M.OZTURK-0003-HUK`,
`KR.ENTHONE-0015-CEZ`, `AXA-3297-DR.E.ALTUNC-HUK`, `SG-0001-HUK` (listede olmayan sigortacı). Tek kanonik
üretici `backend/services/ofis_no.py`; **numarayı SUNUCU verir**: kullanıcı route'ları (`POST /api/cases`,
intake commit) `add_case`'e `ofis_no_sunucudan` bayrağını koyar, istemcinin `tracking_no`'su okunmaz, sıra
müvekkil kodu başına `ofis_no_sayaclari`ndan kayıtla AYNI transaction'da tahsis edilir
(`sira_tahsis_et`, tek yazma yolu); müvekkilsiz kayıt 422. Frontend yalnız önizler
(`GET /api/cases/ofis-no-onizleme`, sayacı artırmaz). Tekrar eden istek `cases.istek_kimligi` (UUID, kısmi
UNIQUE) ile tanınır → yeni kart açılmaz, yanıt `reused: true`. **Numara verildikten sonra DEĞİŞMEZ**
(PUT'ta `tracking_no` yok sayılır). Kategori kodları (`client_categories.ofis_no_kodu`: DR/SC/HS/OH/KR/BR/DG)
ve sigorta şirketi kodları (`sigorta_kisa_kodlari`) admin panelinde ("Ofis No Kodları" sekmesi,
`/api/admin/sigorta-kodlari`, `/api/admin/kategori-kodlari`); kod değişikliği yalnız YENİ numarayı etkiler.
Eski numaraların göçü `scripts/ofis_no_gocu.py` (varsayılan kuru koşu; `--apply` **yalnız kullanıcı
kararıyla** — 30.09 itibarıyla hiçbir DB'de koşulmadı, mevcut kartlar eski numarasını taşır); eski numarayla
arama `case_history.old_value` kolundan sürer. Ayrıntı `docs/mimari/dava-acma-akisi.md` §4-§5.

**Dava notu, sesli giriş, takvim (26.09 toplantısı, G210-G222):** tarihli, yazanı belli notlar `case_notes`'ta
(`routes/case_notes.py`: `GET|POST /api/cases/{id}/notes`, `DELETE .../notes/{note_id}` soft-delete, yazan ya da
admin; panel `CaseNotesPanel.tsx`); `cases.notes` kartta "Genel not" olarak AYRI kalır (`docs/mimari/dava-acma-akisi.md` §14).
Sesli giriş `POST /api/transcribe` (≤2 MB, webm/ogg/mp4/mpeg/wav) → Gemini Türkçe metin, ses diske/loga düşmez;
`MicButton` (≤60 sn) yalnız iki sohbette (Hukukbot `SoruKutusu`, rapor `AssistantBar` — ikisi de ortak yazı kutusu
`components/SohbetGirdisi.tsx`; geçmiş kutunun ÜSTÜNDE, 28.09), metin kutuya düşer, gönderim
otomatik DEĞİL. Takvim raporunda duruşma Açıklama'sı = davanın `dosya_son_durumu` (boşsa not / "Duruşma";
`report_builder._hearing_title`). Avukat seçimi `LawyerCombobox` (NewCase, intake, QuickCaseModal); `CaseList`
filtresi ile `YetkiBelgesiModal` "Veren Avukat" bilinçli dönüştürülmedi (G213).

**Lexis rapor aracı önizlemesi (04.10):** `/lexis` (`pages/LexisPage.tsx`, Araçlar › Lexis) çekirdeği AYRI depoda
(`..\lexis-rapor`) gelişen medikolegal rapor aracının arayüzüdür ve bugün **sentetik örnek veriyle** çalışır: HUKDOK
backend'inde ucu YOK, tek kapısı `lib/lexisApi.ts`'teki örnek adaptördür (`ORNEK_VERI`; veri
`lib/lexisOrnekVeri.ts` — uydurma, repoya gerçek rapor/kişi verisi girmez). **Örnek kipte tek ağ isteği "Word indir"dir**
(`lib/lexisWord.ts`, dinamik yüklenir): örnek taslak aynı origin'den `/lexis-api/word`'e gider, konteyner nginx'i
(`nginx.conf:209-242`, Hukukbot proxy'sinin aynı deseni: allowlist `word|davalar|dosya|emsal-oner|iskelet|muallak-oner|karar-bankasi|kutuphane|rapor|emsal-puanla|taslak|gecmis|kart-baglari|kart-sec|profiller|profil|karar-rafi|kararlar|karar|yaz|emsal-belge|emsal-ara|emsal-sonuc|emsal-durum|kunye-oneri|kunye-karar`, gecikmeli DNS, gerisi 404; bekçi
`backend/tests/test_nginx_lexis.py`) `hukuk_shared` üzerinden **ayrı stack'teki** `lexis_api:8020`'ye iletir
(`..\lexis-rapor\servis`; yerleşim kararı 04.10: ayrı servis). Servis token'ı HUKDOK kuralıyla kendisi doğrular,
yalnız `ADMIN_EMAILS`'i kabul eder, gerçek şirket şablonunu doldurup dosyayı döndürür (dört biçim: Anadolu şablonu
yerinde doldurulur; ALTILI/KISA/EK şirket kabuğundan kurulur, kabuğu olmayan şirkette 503 — 04.10; şablon ve kabuklar
repo ve imaj DIŞINDA). **"Gerçek dava" kipi (04.10, şeritteki düğme, `?veri=gercek`; `lexisApi.veriKipi()`):** "Rapor yaz"
sekmesinin dosya bölgesi (dava arama, künye, belge listesi, emsal önerisi) servisten gelir (`lib/lexisServis.ts` →
`/lexis-api/{davalar,dosya,emsal-oner,karar-bankasi}`); servis kartı ve belge listesini HUKDOK'un MEVCUT uçlarından kullanıcının
token'ıyla okur (`..\lexis-rapor\servis\hukdok.py` — HUKDOK backend'ine yine dokunulmadı), emsal metni maskelidir. Bu
kipte "Taslağı yaz" **iskelet** üretir (`/lexis-api/iskelet`: künye karttan, özet boş — modele hiçbir şey gitmez), muallak
sınıflarını insan seçer (`/lexis-api/muallak-oner`), denetim ekrandaki `lexisDenetim.ts` ile koşar, Word gerçek künyeyle
iner. Kütüphane sekmesi (tarama, rapor okuyucu, karar bankası) ve kütüphaneden elle emsal ekleme de servisten gelir
(`/lexis-api/{kutuphane,rapor,emsal-puanla}`). **Saklama (04.10 gece, kullanıcı kararı: servisin KENDİ veritabanı —
`lexis_db` Postgres'i, `..\lexis-rapor\servis\depo.py`; HUKDOK veritabanına tablo eklenmedi):** gerçek kipte taslak
yazdıkça kaydedilir ve dava yeniden seçilince geri açılır (`/lexis-api/taslak/{case_id}`, sürüm kilitli — başka oturum
yazmışsa 409 ve o oturum artık yazmaz; `components/lexis/useTezgah.ts` "KALICILIK"), Geçmiş koşu logunu
(`/gecmis`), Kart bağı inceleme listesini ve insan seçimini (`/kart-baglari`, `/kart-sec`), Şirketler profilleri
(`/profiller`, `/profil/{şirket}`; kriter tablosu muallak önerisinin ilk basamağıdır) servisten alır. Örnek kipte
hiçbir şey kaydedilmez (`lexisApi.kalici`). **Karar rafı ve kararlardan yazım (05.10 gece, LOKAL — prod'da Lexis servisi
kurulu değil):** servisin karar veritabanındaki büro kararları iki yerde görünür — Kütüphane › "Karar rafı"
(`components/lexis/KararRafi.tsx`: süzgeç + karar metninde arama, sayfalı; `/lexis-api/karar-rafi`) ve tezgâhın sol
bölgesinde davanın kendi kararları (`KararListesi.tsx`, `/lexis-api/kararlar/{case_id}`); tek karar `KararOkuyucu.tsx`
(`/lexis-api/karar/{id}`). **Sonuç iki ayrı alandır** (kararın bütünü koddan · müvekkil yönünden HUKDOK etiketinden) —
tek sütuna indirme. Karar seçiliyse VE servis yazımı açmışsa (`yazim.acik`; servis tarafında `LEXIS_YAZIM`,
**varsayılan KAPALI — açmak kullanıcı kararı**) "Taslağı yaz" iskeletin ardından `/lexis-api/yaz`'ı çağırır: iddia /
yargı süreci özeti ve değerlendirme kararlardan yazılır (servis kararları maskeleyip modele gönderir; tarayıcıdan
yalnız karar KİMLİKLERİ gider, onay kutusu kararları künyeleriyle listeler). Yazım yapılamazsa akış kesilmez
(`warning` olayı, taslak iskelet kalır). Taslak yazıldığı kararları taşır (`LexisTaslak.kararlar`); denetim
(`lexisDenetim.ts`) dayanak alıntısını o kararların metninde de arar ve karardan yazılan özet paragrafındaki tutar /
tarih / numarayı kaynak kararla karşılaştırır (`lexisMetin.kaynaktaOlmayanlar` — çekirdekteki kuralla AYNI tutulur).
Dilekçe / hekim beyanı / poliçeden yazım hâlâ bağlı DEĞİL. **Belgeden künye önerisi (08.10, Aşama 13, LOKAL):** künye kartında "Belgelerden doldur" (gerçek kip; `components/lexis/KunyeOneriCipi.tsx`, `useKunyeOnerileri.ts`) kart belgelerinden alan başına öneri çipi getirir (`/lexis-api/{kunye-oneri,kunye-karar}`; değer + birebir alıntı, kabul / ret); kabul edilen değeri iskelete servis koyar, karta YAZILMAZ. Servis üreticisi varsayılan SAHTE; gerçek kip belgeyi MASKESİZ gönderir, her koşuda ekranda onay ister — canlı çağrı YAPILMADI (S1 + K4 kullanıcı kararı). **Emsal ajan hattı (07.10 gece kuyruğu G258-G265, LOKAL —
prod'da Lexis servisi kurulu değil; plan ve durum `docs/plan/emsal-ajan-hatti-plani-2026-10-06.md`, kararlar lexis-rapor
`PLAN.md` Aşama 12 / K23-K30):** karar rafı başlığındaki ve tezgâhtaki belge satırındaki "Bu dosyaya emsal bul"
(`components/lexis/EmsalBulDiyalogu.tsx`, liste `EmsalKararListesi.tsx`, NDJSON okuyucu `lib/lexisAkis.ts`) büro karar
arşivinde emsal arar — akış: belge (kart belgesini servis HUKDOK'tan kullanıcının token'ıyla indirir, kopyasını almaz; ya da
diskten PDF/DOCX/UDF ≤ 20 MB) → metin + bölümler → maske (`maske.metin_maskele`; kartlıysa kartın tarafları bilinen ad) →
künye + operatörlü sorgular → tam metin arama (`karar_arama` tsvector+GIN, YALNIZ büro kararları — K29) → paralel
okuyucular (aday başına 1 çağrı; `LEXIS_EMSAL_ADAY`=30, `LEXIS_EMSAL_ESZAMANLI`=6; önbellek `emsal_okumalar`, çağrı logu
`model_cagrilari` metinsiz) → KOD denetçisi (alıntı kaynak kararda birebir değilse öneri DÜŞER, ekrana çıkmaz) → gerekçeli
liste → onaylanan karar taslağa `LexisTaslak.emsal_kararlar` ile biner (K28: `kararlar`dan AYRI, yazıma GİTMEZ, Word'de
"Emsal kararlar" künye satırı). Uçlar `/lexis-api/{emsal-belge,emsal-ara,emsal-sonuc,emsal-durum}` (allowlist'te, G262;
`POST /emsal-ara` NDJSON akışı HUKDOK stream sözleşmesiyle — bu yüzden Lexis location'ında `proxy_buffering off`, gövde
tavanı `client_max_body_size 20M`; `GET /emsal-sonuc/{sha}/indir` inceleme paketi zip'i: işaret sütunlu DOCX + birebir
karar metinleri + `sonuc.json`; servis kodu `..\lexis-rapor\servis\{emsal_dosya,emsal_ajan,inceleme_paketi,sharepoint}.py`).
**Üretici varsayılan SAHTE** (`LEXIS_EMSAL_MODEL=sahte`: Gemini'ye hiçbir şey gitmez; künye, puan ve alıntı belirlenimci);
`gemini` kipi env + `GEMINI_API_KEY` + ekranda her koşuda onay kutusu ister (K4; onaysız "Ara" pasif) ve **canlı Gemini
çağrısı henüz YAPILMADI** (plan adım 6, ayrı kullanıcı onayı). Yüklenen belge kalıcıdır: `lexis_db.emsal_dosyalari`
(sha256 anahtar, dosya adı SAKLANMAZ) + SharePoint `03_LEXIS_EMSAL/<yıl>/<sha256>/` (HUKDOK arşiv kimliğiyle,
`LEXIS_SHAREPOINT_KLASORU`; yüklenemezse spool'da bekler, `araclar/emsal_arsiv_toparla.py`). İnsan adımları:
`karar_arama`'yı gerçek `lexis_db`'de kurmak (`araclar/karar_arama_kur.py --apply`, KOŞULMADI — kurulana dek Postgres'te
raf araması yalnız künye bulur), ölçüm (`araclar/emsal_ajan_olcum.py`, gerçek veride KOŞULMADI), gerçek SharePoint'e ilk
yükleme.
Servis kapalıyken HUKDOK açılır, yalnız `/lexis-api` istekleri 502 olur. Entegrasyona dek **yalnız yönetici**
görür (menüde `yalnizYonetici`, rota `ProtectedAdminRoute`). Sözleşme `types/lexis.ts` (çekirdek sınıflarıyla birebir +
"çekirdekte yok" notlu arayüz tipleri). Beş sekme (`?sekme=`): "Rapor yaz" üç bölgeli tezgâh (`components/lexis/Tezgah.tsx`,
durum `useTezgah.ts`: dosya · taslak · denetim), Geçmiş, Kütüphane, Kart bağı, Şirketler. Lexis diyalogları `theme-classic`
taşır (portal kabuğun dışında). Ayrıntı ve entegrasyonun beklediği `docs/plan/lexis-raporu-plani-2026-10-03.md` §10.

**Stream sözleşmesi** (`analyzer.py::_failed_event`, frontend ile ORTAK referans):
olaylar `{"status": "info"/"warning"/"error"/"complete"/"failed", ...}`.
Nihai başarısızlık: `{"status":"failed", "error_ozet", "error_kod"}`; `error_kod`
etiketleri `gemini_saturated | gemini_blocked | gemini_truncated | schema_invalid |
pdf_page_limit | analysis_error` (uzay açık; tanınmayan etiket `analysis_error` gibi
ele alınır). `failed` SON olaydır, `process_id` taşımaz. Analyzer içinde akışı nihai
sonlandıran `status:"error"` yield'i YOKTUR; `{"status":"error","message"}` yalnız
route'un beklenmedik istisnasından gelir ve bu sözleşmenin dışındadır.

**Tenant modeli:** `cases`/`clients` tablolarında `tenant_id` kolonu VAR ama iki tenant
(Hanyaloğlu Acar + LexisBio) ortak çalışır: yeni kayıtlar bilinçli `tenant_id=NULL`
(paylaşımlı havuz — `routes/cases.py:55`, `routes/clients.py:35`); sorgular
"`tenant_id == X OR IS NULL`" deseniyle filtreler (`auth_helpers.py`). Girişte tenant
`ALLOWED_TENANTS` env listesine karşı doğrulanır (`auth_verifier.py`).

**Dava şeması (FAZ D+E, G044-G046):** `cases.esas_no` TÜRETİLMİŞTİR — gerçek kaynak
`case_esas_numbers` tablosu (esas numarası tarihçesi: aşama başına bir satır, dava
başına en fazla bir `is_current=True`); tek yazma yolu `case_manager.sync_current_esas`,
arama eski esas numarasıyla da bu tabloya JOIN'lenerek çalışır (E8, aşağıdaki arama
maddesi). Eksik zorunlu alan bayrağı `cases.missing_required_bucket` de
TÜRETİLMİŞTİR (NULL = eksik yok, `MANUAL`/`AKTARIM` kovaları); tek yazma yolu
`case_manager.refresh_missing_required`, kural `required_fields.py`'de D2/D8
bağlamına göre değişir (2+ avukatlı kartta boş sorumlu avukat kutusu eksik sayılmaz, G158).
Aşama kararları `case_stage_decisions` (tek yazma yolu `managers/stage_decisions.py`, kart
slotları türetilmiş fotoğraf): aktarım mevcut satırı YERİNDE günceller (paket kaynaklı ve elle
girilmiş fark etmez, tarihçeli), yalnız `dogrulama_durumu ∈ {BELGE, UYAP}` satır korunur, esas
VE karar tarihi farklı ise ikinci tur `sira_no+1` ile eklenir, silme yolu yok (G150; ayrıntı
`docs/mimari/veri-teslim-hatti.md` §7.1). Tur sırası `AsamaNo` DEĞİL: paketin "Güncel?" = EVET
satırı sona, sonra karar tarihi; aktarım `sira_no`ları bu sıraya çeker (fotoğraf = güncel tur, 02.10). **Dava durumu ÜÇLÜDÜR** (`constants.CASE_STATUSES`,
karar 020): `cases.status` yalnız DERDEST | DANIŞ | MAHZEN; temyiz/istinaf/karar/kapalı DURUM
değil AŞAMADIR (`cases.case_stage`). Yazma yolları `normalize_case_status`'tan geçer, belge işleme
belge türünden aşamaya yazar (`DOCTYPE_TO_STAGE_MAP`), migrasyon 50 eski değerleri üçlüye çekti.

**Hizmet kaydı (G248-G257, 01-02.10 kullanıcı kararı):** hizmet türü kartın değil **kart × müvekkil tarafı**
çiftinin özelliğidir — `case_hizmetleri` (`models.py:424`, migrasyon 59 `database.py:1437-1486`) her satırda "bu
kartta bu müvekkile bu hizmet verildi" der. **Tek yazma yolu** `managers/case_hizmetleri.py`; `cases.hizmet_turu`
TÜRETİLMİŞ özettir (satırların DISTINCT adları, Türkçe alfabetik, `" ; "` birleşik; tek yazıcı `ozeti_yenile`, `:257`)
— takip ucundan yazılmaz (`TRACKING_FIELDS`'te yok, gönderilirse yok sayılır), aktarımın kart alanı da değildir.
**Föy kaynaklı satır** (`foy_id` dolu) yalnız aktarımla yazılır (`foydan_yaz`, `:532`), kartta salt okunur (çipte yalnız
kilit simgesi — 03.10: "paket · föy no" yazısı kullanıcıya gösterilmez), API'den silme 409. **Elle satır** müvekkil başına ÇOKLU seçimdir: `PUT /api/cases/{id}/hizmetler/{case_party_id}`
gövde `{"hizmet_turleri": [...]}` müvekkilin elle kümesini verilen kümeye getirir (`routes/case_hizmetleri.py:97` →
`elle_kumesini_yaz`, `:395`; föy satırına dokunmaz, listede olmayan ad 422). **Oluşturma kapısı:** kullanıcı yollarında
(`POST /api/cases`, intake commit — `ofis_no_sunucudan` bayraklı istek) her müvekkil ≥1 hizmet taşır, yoksa 422
(`case_manager._taraf_hizmetlerini_dogrula`, `:1852`; `service_types` boşsa kapı açık); kural `required_fields.py`'ye
GİRMEZ (`:75-79`) — mevcut kartlar hizmetsiz diye "eksik" sayılmaz, script/aktarım yolu zorunlu tutulmaz. Dava listesi
`hizmet_turu` filtresi eşitlik değil `EXISTS case_hizmetleri` (`_hizmet_kosulu`, `:1001`). Eski 5'li maske
`cases.service_type` kolonu durur ama hiçbir şeyi beslemez (zorunlu alan listesinden çıktı; yeni dava formu ve
sihirbazdaki 5'li kutular kalktı, yerine müvekkil başına `HizmetSecici`).
**Listenin kaynağı** (`service_types`) veri ekibinin paketidir: `scripts/deger_havuzu_seed.py` "Hizmet Türü" sütununu
listeye ekler (`HAVUZLAR`, `:100`) — İNSAN ADIMI, sıra ÖNCE seed `--apply` SONRA aktarım (aktarım eşlemeyi koşu başında
DB listesinden kurar, `hukdok_aktarim.hizmet_eslemesini_yukle`; listede olmayan ad satır raporunda `UYARI`, hata değil).
Yazım düzeltme/sıralama/paket dışı ek/silme admin "Hizmet Türleri" sekmesinden (`AdminPage.tsx`, `?tab=service_types`);
kullanılan ad boşaltılamaz, yalnız taşınır. Geriye dönük doldurma `scripts/hizmet_kayitlari_doldur.py` İNSAN ADIMIdır
(dump → kopyada kuru koşu → `--apply`, prod'da mesai dışı). Ayrıntı `docs/mimari/dava-acma-akisi.md` §18,
`docs/mimari/veri-teslim-hatti.md` §7.7.

**Dava arama (E8, G055, G189, G190):** `case_manager.get_cases` 15 kolon/ilişkiyi (exact modda
13: `notes`/`case_history.old_value` yok) tek bir OR/EXISTS ağacında DEĞİL, her terim için
bağımsız `UNION`'lanan `SELECT`'lerle arar; çok terimli sorguda AND semantiği `UNION`'ların
`INTERSECT`'iyle kurulur (`_search_term_ids`, `_term_case_id_selects`). Boş legacy
`cases.tku_no`/`sistem_no` kolları G190'da çıktı (TKU/SistemNo `case_foys` kollarından).
**Tek koşu (D4):** `with_total=True` aramada süzülmüş+sıralı id listesi TEK sorguda gelir →
toplam = uzunluk, sayfa = dilim (`_load_cases_in_order`); COUNT yok. `with_total=False`
(`search_cases`, tuş vuruşu yolu) COUNT'suz tek koşudur; aramasız liste COUNT + sayfa koşar.
Liste ucunda `offset ≤ 10000` (`routes/cases.py:92`, aşım 422). **Trigram index'leri**
`database.py::_TRGM_INDEXES` sözlüğündedir — `("index", ...)` op'unda DEĞİL, `pg_trgm`
uzantısından sonra koşan hata-toleranslı blokta (G043 notu); düşürmeler `_DUSURULECEK_INDEXLER`
(`("index", ...)` DROP op'ları). Sözlükteki arama kolları: `case_foys.tku_no/sistem_no/
onceki_tracking_no` (G189), `cases.court/subject/esas_no/tracking_no` (G190 — G042'nin
düşürdüğü altıdan EXPLAIN kanıtıyla dönen dördü), `cases.uyap_lawyer_name`, `case_parties.name`,
`case_lawyers.name`; avukat filtresinin katlanmış ifade index'i ayrıca. Düşmüş kalanlar:
`idx_cases_klasor_no_2_trgm`, ham `idx_cases_resp_lawyer_trgm`, boş legacy
`idx_cases_tku_no`/`idx_cases_tku_no_trgm`/`idx_cases_sistem_no_trgm` (G189). Trigram index'i
olmayan kollar: `klasor_no_2`, ham `responsible_lawyer_name`, `notes`, `case_history.old_value`,
`case_esas_numbers.esas_no` (btree var, küçük tablo); `notes`/`old_value`'yu aramadan çıkarma
kullanıcı kararı AÇIK. Nihai tablo: `docs/kararlar/018-index-temizligi-37-kalem.md` "Nihai index durumu".

**Raporlama (G130-G177 + 12.09 özet modu):** `/reports` giriş yapmış HER kullanıcıya açık (30.09; uçlar
`get_current_user`, menüde Araçlar; koşu geçmişinde yönetici herkesi, diğeri yalnız kendini görür —
`routes/reports.py::_kosu_sorgusu`). Kullanıcı isteğini sohbete yazar — sohbet öncelikli ekran (G173-G176):
`AssistantBar` → `TanimSeridi` (uygulanan tanımın düzenlenebilir çip şeridi: kaynak · kolonlar · filtreler ·
sıralama; operatör seçici yok, kontrol türü/grup/öneri katalogda; katalog önbellekli — bayatken arkaplanda yenilenir, worker açılışında ısıtılır) → tablo; manuel kurucu
(kaynak kartı/filtre şeridi/kolon paneli) KALKTI, şerit yedek kurucudur →
`GET /api/reports/catalog` · `POST /preview` (loglanmaz) · `POST /export` (xlsx/csv; `report_runs`
satırı + dosya `RAPOR_CIKTI_DIZINI`'de saklanır, sha256 = indirilen) · `/templates` · `/runs`. Serbest
SQL YOK (K1: istemci yalnız `services/rapor/registry.py` anahtarlarını gönderir, sorgu Core ile kurulur,
tenant+soft-delete `kisitlar`dan). AI asistan `POST /chat` (NDJSON) admin anahtarı `rapor_asistani`
(durumu sayfa `GET /api/reports/assistant`'tan okur; varsayılan KAPALI; kapalıyken sayfa boş kalmaz — bilgi kartı + şerit) ister; tanımı şeritle AYNI doğrulamadan
geçer (K6) ve DÜĞME BEKLEMEDEN uygulanır (G174; kart yalnız metin filtre değeri katalog önerilerine uymayınca
bekler — `degerEsle`, aday çipleri; "hangi X'ler var" listesi Gemini'siz katalogdan, `listeNiyeti`); prompt
G176: onay sorma, yaklaşık ad → `contains`, liste sorusunda ekrana yönlendir. **Kaynaklar arası birleştirme
(G166):** kaynak `iliskiler` bildirir, bağlı kaynağın kolonları `<iliski>.<kolon>` anahtarıyla TÜRETİLİR
(`muvekkil.phone` davalar'da; `dava.tracking_no` müvekkiller'de) — çoklu bağda değerler `" ; "` birleşik +
EXISTS filtre, sıralama yok; belgeler/föyler → `dava.*` tekil (düz kolon gibi). Elle kolon listesi yazma;
`kart_eslesmesi` ad anahtarı için ifade index'i migrasyon 48'de (`_ad_anahtari` ile birebir, test bekçili).
Ayrıntı `docs/mimari/raporlama.md` §2.4. **"Hizmetler" kaynağı (G251, 02.10):** beşinci kaynak `hizmetler`
(`registry.py:1298`) — satır = bir `case_hizmetleri` kaydı (müvekkil × hizmet × dava); `hizmet_turu`, `kaynak` (`föy`/`elle`),
`muvekkil_adi` düz kolon (gruplanır: "müvekkil başına hizmet sayısı"), `dava.*` tekil, `muvekkil.*` çoklu bağ (yalnız
hizmetin kendi tarafının kartı); föyü kapsam dışı satır görünmez. `davalar.hizmet_turu` aynı görevde ÇOK DEĞERLİ oldu
(`coklu_deger`, `eq`/`in` tam öğe). Doldurma script'i koşulana dek kaynak boş döner. Ayrıntı §2.5. **Özet modu (12.09):** tanım `olcumler` taşıyorsa satırlar `gruplama`
alanlarına göre `GROUP BY` (≤3; tarihte `kirilim` gün/ay/yıl, Türkiye günü) + ölçümler (≤5; `sayi|toplam|ortalama|
min|max`, anahtar `toplam:maddi_tazminat`); `kolonlar` özet modunda kullanılmaz ama zorunlu kalır; boş
`gruplama`/`olcumler` JSON'a girmez (eski sözleşme birebir). Türetilmiş/çoklu bağ kolonu GRUPLANAMAZ. Şeritte
"Σ Özet" satırı; asistan prompt'u "ÖZET RAPOR". Ayrıntı §3.1. **Tıbbi beşli çok değerli (28.09):** `Kolon.coklu_deger` — seçenek havuz ∪ verideki öğeler (sayılı), `eq`/`in` TAM ÖĞE eşler (`motor._coklu_kosulu`), `contains` parça; asistana en sık 40 öğe. Ayrıntı §2. **Saat dilimi (12.09):** rapor sözleşmesinin
dilimi `schemas_rapor.SAAT_DILIMI` (Europe/Istanbul) — DB UTC; zaman damgalı filtre bind'ı, serileştirme ve
Excel hücresi TR saati (openpyxl tz'li datetime'ı reddeder).

**Sürüm izi:** deploy git SHA'sını `APP_VERSION` build arg'ı ile imaja gömer →
`/healthz` "version" alanı + login rozetinin tooltip'i ("Build: <SHA>"). Rozetin görünür
metni okunur sürümdür (`v3.2.0`): tek kaynak `frontend/package.json` "version"
(`vite.config.ts` `define` → `VITE_APP_RELEASE`); sürüm atlatmak = o alanı + `package-lock.json`
kökünü değiştirmek. `/healthz` derindir (DB `SELECT 1`;
başarısızsa 503) — izleme ve deploy kapısı buradan bakar.

**Yedekleme:** prod'da systemd timer (`infra/systemd/db-backup.timer`, 00:30 UTC =
03:30 TR, `Persistent=true`; sunucuda cron YOK) `pg_dump -Fc` alır; deploy öncesi ayrıca
`deploy.sh` dump alır. Bellek düzeni: backend 2g / postgres 512m / frontend 128m limit,
`memswap=mem` (swap yasak), `MALLOC_ARENA_MAX=2` (2026-07-29 OOM dersleri).

## Komutlar

```bash
# Lokal stack (kod İMAJDAN çalışır — bkz. tuzaklar)
docker compose up -d

# Backend testleri KONTEYNERDE koşar (imaj python:3.13-slim)
docker compose exec -T backend python -m pytest            # 2026-09-30 (pytest 9.1.1): 4082 passed, 15 skipped
# DİKKAT: komuta ekstra -q EKLEME — pyproject addopts zaten -q; -qq özet satırını yutar.

# Dev araçları (pytest/httpx/ruff/mypy) prod imajına GİRMEZ (requirements-dev.txt).
# Konteynerde yoksa kur (recreate'te uçar, yeniden kurulur):
docker compose exec -T backend pip install -r requirements-dev.txt
docker compose exec -T backend python -m ruff check .
docker compose exec -T backend python -m mypy

# Frontend testleri HOST'ta koşar (vitest)
npm --prefix frontend test                                 # 2026-10-06: 1636 passed (148 dosya)
npm --prefix frontend run lint
npm --prefix frontend run build
```

**Deploy (yalnız kullanıcı kararıyla, sunucuda, mesai dışı):** `cd ~/hukdok && ./deploy.sh`
— akış ve güvenlik kapıları dosya başındaki yorumda (ff-only pull → pre-deploy pg_dump →
çalışan stack'i bozmadan build → SHA etiketi → şema kapısı (geçici Postgres'te `migrate.py`) →
`up -d` → 120 sn `/healthz` kapısı). Tam test paketi sunucuda VARSAYILAN koşmaz (26.09 kararı:
CI'da koşuyor, sunucuda ~13 dk ekliyordu; CI `success` kapısı bu yüzden şart) — gerekirse
`./deploy.sh --with-tests`.
Geri dönüş: `./rollback.sh <SHA>` (imajı döndürür, DB'yi DÖNDÜRMEZ — DB için pre-deploy
dump). `.env` değişikliği `restart` ile GELMEZ: env yalnız konteyner create'te okunur →
`docker compose up -d` (recreate) gerekir.

## Kritik tuzaklar

- **PS5.1 UTF-8:** PowerShell 5.1 `Get-Content`/`Set-Content` Türkçe içeriği çift kodlar
  ve bozar. Dosya değişikliği DAİMA Edit/Write tool ile; shell'le dosya yazma
  (`otomasyon/gece-kosusu.ps1:14` bu yüzden bilerek ASCII).
- **Backend bind-mount YOK:** prod compose kaynak kodu mount ETMEZ — konteyner imajdaki
  kodu çalıştırır (`docker-compose.yml` backend/volumes yorumu). Kod değişikliğini görmek
  için rebuild şart: `docker compose build backend && docker compose up -d backend`.
  Lokal hot-reload isteniyorsa `docker-compose.override.yml.example` kopyalanır
  (gitignore'da, prod'a gitmez).
- **OneDrive + Docker build cache:** repo OneDrive altında; `requirements*.txt` değişse
  bile pip katmanı CACHED geçebilir. Şüphede `docker compose build --progress=plain` ile
  pip adımının gerçekten koştuğunu doğrula.
- **Migrasyon op türleri koşullu/koşulsuz karışımı:** `database.py::_MIGRATIONS`'ta
  `("table", ...)`/`("columns", ...)` KOŞULLUDUR — `init_db()` önce `create_all()`
  koşturur, ilgili tablo/kolon zaten oradaysa op atlanır ve gövdesine gömülü CREATE
  INDEX/UNIQUE kısıtları o kurulumda HİÇ çalışmaz. Kalıcı olması gereken kısıt/index
  DAİMA ayrı bir `("index", ...)` op'una yazılır (koşulsuz, `IF NOT EXISTS` ile
  idempotent) — G041 bu boşluğu 8 kalemde kapattı; `deploy.sh --gate-only` kendi
  Postgres'ini migrasyonlu kaldırıp bunu doğrular, CI ise ÇIPLAK postgres kullanır
  (tablo bile yok) — üç ortamın üçü de farklı bir DB durumu sunar (bkz. G050 raporu).
- **Doctype `_` padding:** belge türü kodları `_` ile pad'lidir (örn. `TEBLIGAT______`,
  `constants.py:10`). Karşılaştırmadan önce normalize et; ham `==`/`in` kısaltmaları
  sızdırır (export allowlist'i bu yüzden normalize eder, `services/export_publisher.py`).
- **AVG TLS araya girmesi (lokal):** konteynerden Gemini'ye SSL hatasında çözüm
  `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` env'i (`docker-compose.override.yml.example:15`,
  `api.py:88`; `.env.example:93`).
- **pytest çift -q:** `backend/pyproject.toml` `addopts = "-q"` içerir; komuta bir `-q`
  daha eklersen özet satırı ("N passed") hiç basılmaz.
- **Log sözleşmesi:** deneme-düzeyi hatalar WARNING, nihai başarısızlık TEK ERROR
  (`analyzer.py::_failed_event` docstring'i). Retry yollarına yeni ERROR ekleme.
- **Prod'da mesai içinde toplu yazma yok (02.10 kullanıcı kararı):** `hukdok_aktarim` ve tek transaction'lı veri
  script'leri dokundukları binlerce kartı koşu boyunca (dakikalar) kilitler — **kuru koşu dahil** (yazar, sonda
  rollback). Panelden o karta yazan kullanıcı 5 sn `lock_timeout` ile düşer (01.10 avukat adı, 02.10 #3469 aşama
  geçişi). Kural: kuru koşu prod'da DEĞİL, prod dump'ının kopyasında; `--apply`, panel "Uygula"/"Kuru koş" ve veri
  script'leri prod'da mesai (09:00–18:00 TR) dışında. Kilitli kayda yazma 409 "birkaç dakika sonra tekrar deneyin"
  döner (`db_errors.KayitMesgulError`). Kalıcı çözüm G255. Ayrıntı `docs/mimari/veri-teslim-hatti.md` §5
  "Toplu işlem prensibi".
- **Avukat adı serbest yazılmaz (27.09):** avukat adı yazan YENİ kod `lawyer_resolver.kanonik_avukat_metni`'nden
  geçer (listedeki yazım; doğru yazım "Tuğçe Ungör Yanık", Ü değil); kullanıcı yolları listede olmayan
  yeni adı `AvukatListedeYok` → 422 ile reddeder. Ayrıntı `docs/mimari/veri-teslim-hatti.md` "Avukat yazım koruması".
- **Bir kartta aynı kişi TEK taraf satırıdır (03.10 kullanıcı kararı):** taraf yazan/taşıyan YENİ kod kişiyi
  `party_check.normalize_party_key` ile tanır (tür ve rol anahtarda YOK), çok adlı metni `split_party_names` ile
  böler, aynı kişi iki türde karşılaşırsa `TARAF_TUR_ONCELIGI` (müvekkil > karşı taraf > 3. şahıs) kazanır —
  `(tür, ad)` anahtarı ve ham `name ==` karşılaştırması YAZILMAZ. Mevcut mükerrerlerin temizliği
  `scripts/taraf_tekillestir.py` İNSAN ADIMIdır (03.10: LOKALDE uygulandı — 952 kart, 1.216 satır; prod'da KOŞULMADI).
  Ayrıntı `docs/mimari/dava-acma-akisi.md` §7.1.
- **Ofis no ayrıştırılmaz, elle kurulmaz (karar 023):** numara üreten/okuyan YENİ kod `services/ofis_no`'yu
  çağırır; müvekkil kodu gerekiyorsa `cases.ofis_no_kodu` okunur (boşsa `kartsiz_foy_kart_ac.kart_kodu`) —
  `split`/`substr` ile blok çıkarma ve eski formatı (nokta ayraçlı beş blok) ayrıştıran kod YAZILMAZ; sayaç
  tablosu doğrudan yazılmaz. `retag_tracking_nos.py`/`import_excel_cases.py` EMEKLİ (çalıştırılınca hata verir).
- **Avukat kimliği kod değil `lawyers.kimlik` (karar 022, G224-G229):** `AVK-00001`, sistem üretir
  (`models.sonraki_avukat_kimligi`), değişmez, ekrana basılmaz; `lawyers.id` dışarı verilmez. Avukat SİLİNMEZ
  (DELETE = `active=false`, `clear`/`keep` 422), bağlar `ON DELETE RESTRICT`. Avukat verisine dokunan her adım
  önce/sonra `scripts/avukat_envanteri.py --kaydet` / `--karsilastir` (İHLAL = geri al).
- **Rapor asistanı tanımı doğrulanmadan kullanılmaz:** Gemini'nin döndürdüğü tanım
  `services/rapor/asistan.tanimi_dogrula` → `RaporTanimi` + `motor.tanimi_dogrula` yolundan
  geçmeden istemciye `tanim` olarak GİTMEZ (geçmezse `warning` + `tanim=null`); Gemini
  `response_schema`'sına `RaporTanimi` verilmez (`extra="forbid"` → `additionalProperties`,
  SDK Developer API'de desteklenmez — `schemas_rapor.py:188-204`).

## Doküman haritası

| Yol | Ne | Güvenilirlik |
| --- | --- | --- |
| `CLAUDE.md` | Bu dosya — giriş noktası | Güncel tutulur |
| `docs/mimari/` | Yaşayan mimari dokümanları: genel bakış, belge işleme hattı, dava açma akışı, veri teslim hattı, raporlama (`raporlama.md`), bildirimler (`bildirimler.md`), dış bağımlılıklar, deploy ve altyapı, kimlik ve token (`kimlik-ve-token.md`) | GÜNCEL — kodla çelişirse doküman düzeltilir |
| `docs/plan/` | Yürüyen planlar; sertleştirme uygulama takibi tek doğruluk kaynağı | Güncel |
| `docs/kararlar/` | Kalıcı mimari kararlar (karar + gerekçe + reddedilenler) | Güncel |
| `docs/arsiv/` | Tarihli plan/rapor/denetimler | **TARİHSEL — güncel bilgi kaynağı DEĞİL.** İçindeki "şu an şöyle" ifadeleri yazıldığı günün fotoğrafıdır; okumadan önce `docs/arsiv/README.md` şerhini oku |
| `docs/hukukbot-aktarim/` | Hukukbot export spesifikasyonu — koddan referanslı (`nginx.conf:117-118`, `models.py`, `routes/export.py`) | Yaşayan spec, arşiv DEĞİL |
| `gorevler/` | Gece kuyruğu: `KUYRUK.md` + `gorev/GNNN.md` görev dosyaları; dört bant backend / frontend / docs / **lexis** (lexis = dış depo `..\lexis-rapor`, worktree'siz; `gorevler/README.md`) | Süreç dosyaları |
| `otomasyon/` | Gece koşucuları — güncel: Workflow v3 (`.claude/workflows/gece-kuyrugu.js`, başlatıcı `/gece-kuyrugu`); CLI koşucuları `gece-kosusu.ps1`/`kuyruk-kosusu.ps1` (org ayarı CLI'yi kapattı, 2026-08-18) + loglar | Süreç dosyaları |
| `infra/` | Sunucu birimleri: systemd timer'lar, watchdog scriptleri (`infra/README.md`) | Güncel |

## Kod konvansiyonları

- Yorum ve doküman dili Türkçe, tanımlayıcılar İngilizce; mevcut dosyanın üslubunu koru.
- Lint/type kapıları `backend/pyproject.toml`'da: ruff `E,F,B` (E501 kapalı,
  line-length 120), mypy kademeli — yalnız `managers/ routes/ config/ services/` taranır.
- Bir iş = TEK commit: kod + test + doküman birlikte; `git add -A` yerine dosya listesi.
  Push/deploy daima insan kararı — otomasyon oturumları push/ssh/deploy YAPMAZ.
- **CI protokolü** (`.claude/skills/ci-kontrol`, `/ci-kontrol`): push ÖNCESİ `ci.yml` adımlarının lokal
  eşdeğeri, push SONRASI `gh run watch`; **kırmızıdayken yeni iş push'lanmaz** (sıradaki push düzeltmedir);
  deploy edilecek SHA'nın CI'ı `success` değilse deploy YOK (`deploy-prosedur` §1).
- **Bağımlılık denetimi** (`.claude/skills/bagimlilik-denetle`, `/bagimlilik-denetle`; her ayın 1'i zamanlanmış
  yerel görev): yeni sürümleri sürüm notu + kod etkisiyle sınıflar, yalnız aynı-major güncellemeleri
  `bagimlilik/YYYY-MM` dalında uygulayıp CI kapılarından geçirir; major/altyapı atlamaları rapor
  (`docs/arsiv/bagimlilik-raporu-YYYY-MM.md`) önerisidir. Push/deploy YAPMAZ.
- Hata işlemede stream sözleşmesine ve log sözleşmesine uy (yukarıda).
- Arşivden kod/iddia kopyalama; tarihli anlatı yazacaksan `docs/arsiv/`e yaz.
