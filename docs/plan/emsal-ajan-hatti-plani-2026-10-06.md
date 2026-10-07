# Emsal ajan hattı planı — Lexis B kolu (06.10.2026)

> **Durum: ONAYLANDI (07.10.2026).** Kullanıcı 06.10'da A'yı değiştirdi (kalıcı SharePoint arşivi), E4 ve H'yi
> istedi; 07.10'da F ve G'yi önerildiği gibi onayladı ve işin gece kuyruğunda koşmasına karar verdi (koşucuya
> `lexis` bandı eklendi, görevler G258-G266). Bu belge "Emsal arama — Lexis, Lexpera ve ajan hattı"
> karşılaştırmasının (masaüstü, 06.10) "Ajan hattı" ve "Test süreci" bölümlerinin uygulama planıdır. Her sayı
> 06.10'da koddan ya da lokal `lexis_db`'den okunarak doğrulandı; kaynağı yanında yazar. Kararlar
> `..\lexis-rapor\PLAN.md` **Aşama 12 / K23-K29**'da; bu dosya HUKDOK tarafının izidir.

## 0. Doğrulanan zemin

| Konu | Bulgu | Kaynak |
| --- | --- | --- |
| Karar veritabanı | `lexis_db.karar_belgeleri` 25.660 belge: büro 4.058 (karar 3.756 · bilirkişi 152 · ATK 150), Yargıtay 8.618, Danıştay 6.738, UYAP Emsal 5.479, AYM 767. Büro belgesinde `kart_id` dolu 3.335, `esas_no` 4.041, `karar_no` 3.654, `karar_tarihi` 3.643. | `psql` sayımı |
| Büro metni | Uzunluk: ortanca 14.013, ortalama 18.246, en çok 358.711 karakter; toplam 74,0 M karakter. | `psql` |
| Kod alanları | `karar_alanlari` (`kaynak=kod`): `hukum_sinifi` 3.665, `sonuc_muvekkil` 3.440, `olay` 1.924, `hukmedilen_*` 363-595; gerekçe konuları `konu:kusur` 17.533, `tazminat` 10.957, `bilirkisi` 10.345, `onam` 5.308, `illiyet` 2.778, `usul` 2.281 paragraf. | `psql` |
| Raf araması bugün | `karar_depo.raf_listesi`: beş kolonda (`mahkeme`, `esas_no`, `karar_no`, `uzmanlik`, `metin`) `ILIKE '%…%'`, Türkçe büyük/küçük üç biçimle; operatör yok. Index yok: `karar_belgeleri` üzerinde yalnız `kaynak`, `kart_id`, `vaka_id`, `dosya_sha256`, `uyusmazlik_no`, `paket_id` btree'leri. | `servis/karar_depo.py:356-424`, `pg_indexes` |
| Servis | `lexis_api:8020`, FastAPI, tek uvicorn worker, `uid 10001`, yazılabilir birim YOK (yalnız geçici dizin). İmajda pymupdf YOK (`servis/requirements.txt`: "ucu gelince eklenir"). `google-genai==2.26.0` kurulu; `cikarim.gemini_uretici` senkron, `temperature=0`, `response_schema` ile JSON. | `Dockerfile`, `docker-compose.yml`, `cikarim.py:250` |
| Kimlik | `kimlik.yonetici`: HUKDOK token'ı + `ADMIN_EMAILS`. | `servis/kimlik.py` |
| Proxy | HUKDOK `nginx.conf:216-235` allowlist (20 uç), `proxy_buffering` kapatılmamış (Hukukbot bloğunda NDJSON için kapalı); bekçi `backend/tests/test_nginx_lexis.py`, Vite `vite.config.ts:80`. | okundu |
| Maske | `maske.metin_maskele(metin, bilinen_adlar)`: bilinen adlar (kart tarafları) → kalıplar → öğrenilen adlar; karar başlığı satırları; TC. Kalıp geçişi kusursuz değil (modül notu). | `lexis_rapor/maske.py` |
| Alıntı denetimi | Python: `yazici._alinti_parcalari` + `metin.katla` (dayanak alıntısı hedef metinde aranır). TS: `lexisMetin.kaynaktaOlmayanlar`, `alintiGeciyor`. | okundu |
| Kararlardan yazım kuralı | `yazim.yaz` yalnız **o karta bağlı** büro belgesini girdi alır (`karar_depo.kart_metinleri` `kart_id` süzer); "başka dosyanın kararını girdi yapan yol açma" (lexis-rapor `CLAUDE.md`). Emsal karar tanım gereği başka dosyanın kararıdır → **F kararı**. | `servis/yazim.py:150`, `karar_depo.py:463` |
| Belge kaynağı kuralı | K2/K10: dosyanın belgeleri dava kartından gelir, kullanıcı yeniden yüklemez; HUKDOK'ta `GET /api/documents/{id}/download` var (`routes/documents.py:286`), servis adaptörü (`servis/hukdok.py`) bugün yalnız kart + belge LİSTESİ okur, indirme yok. | okundu |
| Test altyapısı | lexis-rapor testleri SQLite'ta koşar (`tests/conftest.py` `LEXIS_DB_URL`'i siler; `test_depo.veritabani` SQLite verir, `LEXIS_TEST_DB_URL` ile Postgres'e çevrilebilir). SQLite'ta `tsvector` yok. | `tests/conftest.py`, `tests/test_depo.py:22` |
| Eski rapor külliyatı | Lokalde yalnız pilot paket: 28 rapor (`HUKDOK_LEXIS_EGITIM_2026-10-03\RAPORLAR`, 55 dosya) + envanter (3.065 satır `vaka_raporlari`'nda, 26'sı kütüphanede). Tam külliyat (~3.260 rapor, Aşama 7) lokalde YOK. | `ls`, `psql` |

## 1. Altın küme sayımı (06.10, model çağrısı yok)

**Kaynak 1 — rapor atıfları** (`okuma_maskeli.jsonl`, 28 pilot rapor; eşleme `kutuphane.karar_bul` ile aynı
anahtar: boşluksuz esas + karar no, `lexis_db`'nin bütün kaynaklarına karşı):

| Sayım | Değer |
| --- | --- |
| Rapor | 28 (17'sinde en az bir emsal atfı) |
| Karar atfı | 31 (27'si `emsal=True`, 2'si belirsiz, 2'si raporun kendi dosyası) |
| `lexis_db`'de bulunan | 24 / 31 |
| … büro kararına düşen | **6 atıf → 4 (vaka → büro kararı) çifti**: klasör 31471 → belge 24533 (kart 229); 91820 → 23963 (kart 13190); 08251 + 08252 (aynı vaka) → 23590 (kart 927); 21469 → 23599/23951 (kart 3881; raporun kartı 13966 — emsal bayrağı belirsiz, ayrı kart olduğu için emsal sayıldı) |
| … dış karara düşen | 18 (Yargıtay 15 · Danıştay 2 · mercisiz 1) — veritabanında VAR, "yalnız büro arşivi" kuralıyla kapsam DIŞI (bkz. G kararı) |
| Bulunamayan | 7 (BAM 3 · idare mahkemesi 2 · tüketici 1 · Danıştay 1 · Yargıtay 1) |

Sonuç: **rapor atıfı altın kümesi bugün 4 çifttir, 100'ün çok altında.** Oran (4/28) tam külliyata (~3.260 rapor)
taşınırsa ~450 çift beklenir, ama külliyat lokalde yok (Aşama 7 adım 1: SharePoint'ten dışa aktarım, insan adımı).
Belgedeki "100'ün üstündeyse ana test budur" koşulu külliyat gelmeden sınanamaz.

**Kaynak 2 — aynı dava zinciri** (bedava, sağlama): büro kararlarında `kart_id` ortak olan 909 kart (2.364 karar;
575 ikili, 205 üçlü, 86 dörtlü, 25 beşli, 18 daha fazla); vaka bazında 931; paketin kendi zincirleri 466 (395 ikili,
62 üçlü, 8 dörtlü, 1 beşli). **Bu küme bugün hazır** — sistemin bozuk olmadığını ölçer, emsal isabetini ölçmez
(aynı dosyanın kararları ad ve numarayla trivial bulunur; sorgu belgesinden esas/karar no ve kart adları
maskelenerek koşulur, yine kolay testtir).

**Kaynak 3 — kör avukat işaretlemesi** (30 dosya × 3-5 emsal): kullanıcıda; planın 7. adımı bunu bekler.

**Öneri:** 2. adımdan itibaren ölçüm aracı üç kümeyi de okur; bugün zincir kümesi (sağlama) + 4 atıf çifti (duman)
koşar; asıl Recall@5 sayısı külliyat ya da kör işaretleme gelince alınır. Onay istenen şey: **külliyat dışa aktarımı
(Aşama 7 adım 1) bu işin önüne alınsın mı?** Alınmazsa kabul ölçütü kör işaretlemeye dayanır.

## 2. Mimari şema

```
HUKDOK frontend (/lexis, yalnız yönetici, theme-classic)
  Karar rafı ─"Bu dosyaya emsal bul"─► EmsalBulDiyalogu
     kaynak seç: kart belgesi (HUKDOK belge listesi)  |  dosya yükle (PDF/DOCX/UDF)
          │                                                 │
          ▼  POST /lexis-api/emsal-belge  (multipart ya da {belge_id, case_id})
  ┌────── Lexis servisi (lexis_api) ─────────────────────────────────────────────────┐
  │ 1 metin çıkar   docx_okuyucu | pdf_okuyucu (pymupdf) | udf_okuyucu (YENİ)       │
  │ 2 maskele       maske.metin_maskele(+ kart taraf adları)   → emsal_dosyalari    │
  │ 3 künye         sorgu üretici (model, 1 çağrı; sahte üretici seçilebilir)        │
  │                  → uzmanlık · işlem · iddia · taraf türü · 3-5 sorgu (operatörlü) │
  │ 4 aday          arama.py: sorgu → tsquery → karar_arama (GIN)  ≤ 30-50 aday     │
  │ 5 oku           okuyucu × N (asyncio, eşzamanlılık 6; önbellek emsal_okumalar)   │
  │ 6 denetle       kod: alıntı kaynak kararda birebir mi (katlanmış metin)          │
  │ 7 sırala        okuma puanı ▸ FTS sırası; denetimden düşen ÇIKMAZ                │
  │   NDJSON akışı: info (aşama/ilerleme) · warning · complete (liste) · failed      │
  └──────────────────────────────────────────────────────────────────────────────────┘
          │ sonuç listesi (puan · gerekçe · doğrulanmış alıntı · künye)
          ▼
  Avukat onaylar ─► taslak.emsal_kararlar (F kararı) ─► KararOkuyucu'da açılır
```

Model çağrıları (3 ve 5) yalnız `LEXIS_EMSAL_MODEL=gemini` iken Google'a gider; varsayılan `sahte` (belirlenimci:
künye kart/dosya başlığından, puan FTS sırasından, alıntı ilk eşleşen cümleden). Sahte kip uçtan uca aynı yolu yürür.

## 3. Tasarım kararları — öneri ve gerekçe (kararı kullanıcı verir)

### A. Yüklenen belgenin saklanması (K23) — **06.10 kullanıcı kararı: kalıcı arşiv, şimdilik yeni SharePoint arşivi**

- **A1 İki kaynak, bir kayıt.** Birinci yol **kart belgesi**: diyalog kartın belge listesini gösterir (zaten
  `/dosya/{case_id}`'de var), servis dosyayı HUKDOK `GET /api/documents/{id}/download`'dan **kullanıcının token'ıyla**
  indirir (`servis/hukdok.py`'ye `belge_indir`; K9 ile uyumlu, HUKDOK backend'ine dokunulmaz) ve **kopyasını
  almaz** — asıl zaten HUKDOK arşivindedir. İkinci yol **disk yükleme** (kartta olmayan belge; `client_max_body_size`
  20 MB): orijinal **kalıcıdır**, yeni bir SharePoint arşivine gider (A4). Her iki yolda dosya adı saklanmaz (ad kişi adı
  taşıyabilir); arşivde ad `<sha256>.<uzantı>`.
- **A2 Tablo `emsal_dosyalari`** (`lexis_db`, `depo.py` deseni): `sha256` PK, `kaynak` (`kart` | `yukleme`),
  `case_id` (boş olabilir), `hukdok_belge_id`, `bicim`, `boyut`, `metin`, `maskeli_metin`, `bolumler` (JSON), `kunye`
  (JSON, 3. adım), `maske_dokumu` (sayılar), `yukleyen`, `yukleme`, `sharepoint_url`, `sharepoint_hata` (son deneme).
  Metin ve maskeli metin kişi/sağlık verisidir: loglanmaz, hata iletisine taşınmaz (depo kuralı aynen).
- **A3 Modele yalnız `maskeli_metin` gider.** Orijinal dosya ve ham metin hiçbir modele gitmez; okuyucuya giden karar
  metni de `metin_maskele`'den geçer (`yazim.kaynaklari_kur` ile aynı yol). Yükleme yolu kart seçmeden yapılırsa
  bilinen ad listesi boş kalır → yalnız kalıp maskesi; ekran "maske dökümü"nü (bilinen/kalıp/öğrenilen sayıları) canlı
  çağrı onayından önce gösterir.
- **A4 Kalıcı arşiv — yeni SharePoint klasörü (kullanıcı kararı 06.10).** Yüklenen belge ve inceleme paketi (E4),
  HUKDOK'un arşiv kimliğiyle (aynı `SHAREPOINT_TENANT_ID / CLIENT_ID / CLIENT_SECRET / SITE_URL / DRIVE_NAME`
  değerleri Lexis `.env`'ine kopyalanır; `.env.example`'a girer) **yeni** bir üst klasöre yazılır:
  `LEXIS_SHAREPOINT_KLASORU` (öneri `03_LEXIS_EMSAL`) → `<yıl>/<sha256>/` altında `belge.<uzantı>` +
  `inceleme.docx` + `sonuc.json`. HUKDOK'un `01_HAM_ARSIV` / `02_YEDEK_ARSIV` klasörlerine ve eski "SharePoint Lexis
  klasörüne" (K10: araç onu okumaz) DOKUNULMAZ. Servis kendi küçük Graph istemcisini taşır (`servis/sharepoint.py`,
  ~120 satır: token, klasör oluşturma, `PUT …/content` küçük dosya; HUKDOK `sharepoint_uploader_graph.py` desenindedir
  ama oradan import EDİLEMEZ — ayrı stack). Yükleme şöyle sıralanır: önce servisin yazılabilir birimi
  `lexis_yukleme:/veri/yukleme`'ye spool (compose'a birim, `uid 10001`), sonra SharePoint; başarısızsa kayıt
  `sharepoint_url` boş kalır, bir sonraki istekte ve `araclar/emsal_arsiv_toparla.py` ile yeniden denenir (HUKDOK outbox
  desenindeki gibi: "SharePoint'e çıkmadan silinmez"). Yüklendikten sonra spool kopyası silinir. **İleride** belgeler
  dava kartlarıyla eşlenince ortak Lexis arşivine taşınır: `emsal_dosyalari.case_id` + `sha256` taşımanın anahtarıdır
  (sha256 HUKDOK `case_documents.dosya_sha256` ile aynı özet — migrasyon 60), taşıma ayrı iştir.
- **A5 Erişim:** servis zaten yalnız `ADMIN_EMAILS`; kayıt `yukleyen`'i taşır. Öneri: her yönetici her kaydı görür
  (bugünkü taslak/geçmiş kuralıyla aynı); "yalnız yükleyen" isteniyorsa `yukleyen == eposta(claims)` süzgeci tek satırdır.
  Log satırı: kullanıcı, `case_id`, sha256'nın ilk 12 hanesi, sayılar — ad, metin, dosya adı yok. SharePoint
  yükleme hatası türüyle loglanır, yol/ad ile değil.
- **A6 Silme kuralı yok:** kalıcı arşiv olduğu için otomatik silme kurulmaz; spool kopyası yükleme sonrası kalkar.
  Ham `metin` kolonu da kalır (önbellek anahtarı değil ama yeniden maske/yeniden künye için gerekir); isterseniz
  env ile süreli boşaltma eklenir.

### B. Biçim (K24)

- PDF: `pdf_okuyucu` (pymupdf) — **`servis/requirements.txt`'e `pymupdf` girer** (imaj ~+25 MB; bugün "ucu gelince
  eklenir" notu bu uçtur). Metin katmanı yoksa 422 "taranmış belge; OCR bu hatta yok" (hat OCR kurmaz).
- DOCX: `docx_okuyucu` (bağımlılıksız).
- UDF: yeni `lexis_rapor/udf_okuyucu.py` (~50 satır): zip içindeki `content.xml`'in `<content>` metni + `<paragraph>`
  ofsetleri. HUKDOK `udf_converter.py` (reportlab, PDF üretir) KOPYALANMAZ; yalnız biçim bilgisi (content.xml, CDATA)
  oradan alınır. XML `defusedxml` ile (HUKDOK'taki gerekçe: billion-laughs) → requirements'a girer. Şifreli zip 422.
- Çıktı: UTF-8 düz metin + `bolumler` JSON `[{tip, baslik, bas, son}]` (karar bölümleriyle aynı aralık sözleşmesi).
  Bölüm tanıma başlık anahtarıyla (`metin.anahtar`), dilekçe/beyan/bilirkişi için küçük liste (OLAY, İDDİA/DAVA,
  CEVAP/SAVUNMA, TALEP, SONUÇ, DEĞERLENDİRME); tanınmazsa tek bölüm. Künye çıkarımı 3. adımın işidir, okuyucunun değil.

### C. Hız (K25)

- **C1 Tam metin arama — ayrı tablo.** Ölçüm (06.10, `BEGIN … ROLLBACK` içinde, 4.058 büro belgesi, Postgres 15.15,
  `turkish` sözlüğü yerleşik):

  | Yaklaşım | "üreter yaralanması komplikasyon" (AND, 23 sonuç) | 3 terim + `ts_rank_cd` sıralı, 684 sonuç | tek terim "kusur", 3.462 sonuç sıralı |
  | --- | --- | --- | --- |
  | Bugün: `to_tsvector` anında, index yok | 12.030 ms | — | — |
  | `karar_belgeleri.arama` kolonu + kısmi GIN (`WHERE kaynak='buro'`) | 104 ms — **planlayıcı GIN'i KULLANMADI** (`kaynak` btree + süzgeç) | 200 ms | — |
  | **Ayrı tablo `karar_arama(belge_id PK, arama tsvector)` + GIN** | **0,16 ms** | **103 ms** | 290 ms |

  Ayrı tablo seçilir: GIN 21 MB, tsvector 55 MB, tablo toplam 79 MB. Sıralama maliyeti eşleşme sayısıyla büyür
  (tsvector okunur); kural: eşleşme > 1.500 ise sıralama atlanır, tarih sırası + "sorguyu daraltın" uyarısı. Ajan
  sorguları 2-4 terimli AND olduğundan tipik koşu < 10 ms. Hedef "< 200 ms" ölçümle tutuyor; tek genel terim 290 ms
  (bilinen istisna, raporda yazılır).
- **C2 Türkçe kök bulma kusurlu:** snowball `turkish` "yaralanması → yaralanmas", "yaralanmasında → yaralanma",
  "hekimin → hek", "doğumda → dok" veriyor. Bu yüzden sorgu kurucu (`lexis_rapor/arama.py`) **kendi ayrıştırıcısını**
  taşır: `AND / OR / NOT / "ibare" / ( )` → `to_tsquery('turkish')`; terimler `:*` ön-ek eşleşmesiyle (ölçüm: `üreter:* &
  (yaralan:* | kesi:*) & sezaryen:*` 3,7 ms, 12 sonuç); ibare `<->` ile. `websearch_to_tsquery` ön-ek desteklemediği
  için kullanılmaz. Raf araması aynı kurucudan geçer: metin kutusu operatörlü olur, `ILIKE` yalnız künye kolonlarında
  (mahkeme, esas, karar no; kısa kolon, ucuz) kalır. `karar_arama` tablosu `araclar/karar_arama_kur.py` ile doldurulur
  (büro, `--apply`); `belgeleri_yaz` büro satırında tsvector'ü günceller; dış karar `kaynak` kolonu ile kapalı durur (G).
- **C3 Okuma paralel:** `asyncio.Semaphore(LEXIS_EMSAL_ESZAMANLI=6)`, `google-genai` async istemcisi (`client.aio`);
  `cikarim.gemini_uretici` dokunulmaz, yanına `gemini_uretici_async` eklenir. Aday tavanı `LEXIS_EMSAL_ADAY=30` (ölçüm
  için 50'ye çıkarılabilir). Uçtan uca hedef < 60 sn: 30 aday / 6 eşzamanlı = 5 tur × ~6-8 sn.
- **C4 Önbellek:** tablo `emsal_okumalar` PK (`dosya_sha256`, `belge_id`, `model`, `istem_surumu`) → puan, gerekçe,
  alıntı, denetim sonucu, token, süre. Aynı belge + aynı aday için model yeniden çağrılmaz; önbellekten gelen satır
  akışta `info` ile "önbellekten" işaretlenir. Sorgu üretici çıktısı `emsal_dosyalari.kunye`'de durur (aynı belge
  ikinci koşuda yeniden üretilmez; "yeniden üret" düğmesi ayrı).
- **C5 NDJSON akışı:** `POST /emsal-ara` `application/x-ndjson`, HUKDOK stream sözleşmesi: `{"status":"info","asama":
  "metin|maske|sorgu|aday|okuma|denetim","ilerleme":[i,n],...}`, `warning` (ör. okuyucu hatası: aday düşer, akış
  sürmez değil sürer), `complete` (sonuç listesi + sayılar), `failed` (`error_ozet`, `error_kod`: `gemini_saturated |
  gemini_blocked | schema_invalid | metin_yok | aday_yok | analysis_error`; `failed` SON olaydır). İş istek içindeki
  asyncio görevidir; istemci koparsa görev tamamlanır, sonuç önbelleğe düşer, `GET /emsal-sonuc/{sha256}` ile geri
  açılır (böylece "arka planda koşar, kullanıcı ilerlemeyi görür" sağlanır; ayrı iş kuyruğu süreci kurulmaz).
  nginx: Lexis location'ına `proxy_buffering off` (Hukukbot bloğuyla aynı), yeni uçlar allowlist'e, bekçi testi ve
  Vite proxy güncellenir.

### D. Paralel ajanlar (K26)

- **Roller:** `sorgu_uretici` (1 çağrı, şema `EmsalKunyesi`: uzmanlık, tıbbi işlem, iddia, taraf türü, yargı yolu,
  3-5 `sorgu` satırı — her satır operatörlü metin + "tıbbi / hukuki / eş anlam" etiketi), `okuyucu` (aday başına 1
  çağrı, şema `OkumaPuani`: `puan` 0-100, `uygun` bool, `gerekce` tek cümle, `alinti` karardan 15-40 sözcük birebir,
  `fark` tek cümle — "aynı olay, kusur yönü ters" gibi), `denetci` (kod, model değil): alıntı katlanmış karar metninde
  birebir aranır (`yazici._alinti_parcalari` kuralı: ≥ 12 harf, ardışık parçalar); bulunamazsa aday düşer ve `warning`
  yazılır; gerekçedeki tutar/tarih/numara `_olgu_uyarilari` ile kararla karşılaştırılır.
- **Sıralama:** `uygun=true` ve denetimden geçenler, `puan` azalan; eşitlikte FTS sırası. Etiket puanı (A kolu) bu
  dilimde girmez (etiketler yok) — C kolu için `bilesenler` alanı boş liste olarak sözleşmede durur.
- **Eşzamanlılık ve tavan:** kullanıcı başına 1 açık iş (ikinci istek 409 "koşu sürüyor"), süreç genelinde
  `LEXIS_EMSAL_ESZAMANLI`; gün tavanı `LEXIS_EMSAL_GUNLUK_TOKEN` (aşımda 429, akış `failed: kota`). Dosya başı tavan
  `LEXIS_EMSAL_DOSYA_TOKEN` (aday metni `karar_yazici.kirp` ile 20.000 karaktere kırpılır — ortanca karar 14.013
  karakter; 30 aday ≈ 150-200 bin giriş token'ı; gerçek sayı ilk canlı koşuda raporlanır).
- **Model çağrı logu:** tablo `model_cagrilari`: zaman, kullanıcı, rol, model, `dosya_sha256`, `belge_id`, giriş/çıkış
  token, süre ms, sonuç (`ok | hata:<tür>`), istem sürümü. **Metin yok.** Geçmiş sekmesinde "Emsal koşuları" alt
  listesi buradan okunur.
- **Sahte üretici:** `LEXIS_EMSAL_MODEL=sahte` (varsayılan) belirlenimci çıktı üretir (künye: belge başlığından;
  sorgu: en sık 5 tıbbi/hukuki terim; puan: FTS sırası; alıntı: ilk eşleşen cümle). Testler ve ilk uçtan uca koşu
  bununla. `gemini` değeri + `GEMINI_API_KEY` → canlı; her canlı koşu ayrıca ekranda onay kutusu ister (yazım
  ucuyla aynı K4 pratiği).

### E. Ekran (K27)

- Karar rafı başlığına **"Bu dosyaya emsal bul"**; tezgâhta belge listesine satır düğmesi (kart belgesiyle doğrudan).
- `components/lexis/EmsalBulDiyalogu.tsx` (`theme-classic`, portal): kaynak seçimi (kart belgesi listesi | dosya seç),
  maske dökümü + model kipi rozeti ("sahte" / "Gemini — onay gerekir"), ilerleme çubuğu (NDJSON `info`), sonuç listesi
  `EmsalKararListesi.tsx` (puan rozeti, gerekçe, alıntı + "kaynakta doğrulandı" rozeti, künye, `KararOkuyucu`'da aç),
  onay kutuları → "Taslağa ekle". Akış okuyucusu `lib/lexisAkis.ts` (`hukukbotApi.ask` okuyucusunun aynı deseni:
  satır tamponu, iptal). Örnek kipte `lexisOrnekVeri` sentetik sonuç verir; servis kipinde `lexisServis.emsalAra`.
- Yalnız yönetici (mevcut rota koruması); menüde yeni madde yok, rafın içinde yaşar.
- **E4 İnceleme paketi (kullanıcı isteği 06.10: önerilen emsaller incelenecek, uygun yere indirilecek).**
  `GET /emsal-sonuc/{sha256}/indir` → `inceleme_<sha256 ilk 12>.zip`: `inceleme.docx` (sıralı liste: puan, gerekçe,
  doğrulanmış alıntı, künye, kart no, "uygun / kısmen / değil" işaret sütunu — kör kıyas ve avukat işaretlemesi bu
  dosyada yapılır), aday başına `kararlar/<sıra>_<esas>_<karar>.txt` (büro kararının birebir metni, veritabanından) ve
  varsa PDF'i (`karar_dosyalari.ad` → host'taki `hukdok_kararlar` dizini compose'a **salt okunur** bağlanırsa; yoksa
  yalnız metin — bu bağlama kullanıcı kararıdır), `sonuc.json` (ölçüm aracının okuduğu biçim). Aynı paket A4 arşivine
  belgenin yanına yazılır; ekranda "İndir" ve "Arşivde aç" bağlantısı. Paket kişi verisi taşır (karar metinleri
  maskesiz, büronun kendi kararı): yalnız yönetici indirir, loglanmaz. İşaretlenmiş `inceleme.docx`'in geri yüklenip
  altın kümeye yazılması 7. adımın aracıdır (`araclar/emsal_isaret_oku.py`).

### H. Hangi model ne için (kullanıcı sorusu 06.10)

| Adım | Model | Neden |
| --- | --- | --- |
| Metin çıkarma (PDF/DOCX/UDF), bölümleme | yok (kod) | belirlenimci okuyucular |
| Maske | yok (kod, `maske.py`) | modele gitmeden önce koşar |
| Künye + sorgu üretimi (3. adım) | `gemini-3.8-flash` (`cikarim.VARSAYILAN_MODEL`, 03.10 kullanıcı kararı; env `LEXIS_EMSAL_SORGU_MODEL`) | dosya başına 1 çağrı, kısa çıktı (JSON şema) |
| Aday toplama (FTS) | yok (Postgres) | model çağrısı yok |
| Okuyup puanlama (5. adım) | `gemini-3.8-flash` varsayılan (env `LEXIS_EMSAL_OKUYUCU_MODEL`) | dosya başına 30 çağrı: hacim ve hız; kalite belirleyici adım olduğu için 7. adımdaki ölçüm **flash ↔ pro** karşılaştırmasını içerir, kazanan env'e yazılır |
| Alıntı denetimi, sıralama | yok (kod) | halüsinasyon kapısı modelsizdir |
| İnceleme paketi (DOCX) | yok (python-docx) | — |
| Sahte kip (`LEXIS_EMSAL_MODEL=sahte`) | yok | testler ve ilk uçtan uca koşu |

Bugün serviste zaten `gemini-3.8-flash` kullanan uçlar: etiket çıkarımı (`cikar`, 28 pilot), kararlardan yazım (`/yaz`,
`LEXIS_YAZIM` kapalı). Hat aynı anahtarı (`GEMINI_API_KEY`) ve aynı `temperature=0` + JSON şema kuralını kullanır. Her
canlı çağrı `model_cagrilari`'na model adıyla düşer; Geçmiş sekmesi "hangi model, kaç token" sütunlarını gösterir.

### F. Onaylanan kararın taslağa binişi (K28) — **KARAR (07.10): öneri gibi**

Kararlardan yazım yalnız **o karta bağlı** kararı girdi alır (kullanıcı kuralı). Emsal karar başka kartındır.
Karar: `LexisTaslak.emsal_kararlar: number[]` **ayrı alan** (bugünkü `kararlar` yazım girdisi olarak kalır);
taslakta "Emsal kararlar" listesi + Word'de künye satırı (bugün emsal dipnotu yazılmıyor — bu dilimde künye satırı
olarak eklenir); **yazıma gitmez.** Emsal kararın metninin de değerlendirmeye girmesi (emsal dayanaklı madde)
ayrı kullanıcı kararıdır ve yazım kuralını değiştirir.

### G. Arama evreni (K29) — **KARAR (07.10): yalnız büro**

Görev "yalnız büro arşivi" der; `lexis_db`'de 21.602 dış karar da var ve 28 raporun atıflarının 18'i dış karara.
Karar: `karar_arama` tablosu `kaynak` kolonu taşır, **bu dilimde yalnız büro doldurulur**; dış kararın açılması
ayrı karar (lisans `cc0_kamu`, metin anonim — maske yükü yok). Ölçüm büro üzerinde.

## 4. Teslim sırası ve dosya kapsamı (her adım tek commit: kod + test + doküman)

| # | İş | Dosyalar (lexis-rapor `..\lexis-rapor`; HUKDOK bu depo) | Test / ölçüm |
| --- | --- | --- | --- |
| 1 | **Plan onayı** (bu belge) + PLAN.md Aşama 12 / K23-K29 | `PLAN.md`, bu dosya | — |
| 2 | **FTS**: `karar_arama` tablosu, `lexis_rapor/arama.py` (ayrıştırıcı → tsquery), `araclar/karar_arama_kur.py`, raf araması değişimi (`karar_depo.raf_listesi`), `README` "Karar rafı" | `servis/karar_depo.py`, `lexis_rapor/arama.py`, `araclar/`, `tests/test_arama.py` (saf), `tests/test_karar_raf.py` (Postgres kipi `LEXIS_TEST_DB_URL`, SQLite'ta FTS testleri `skip`) | 4.058 belgede 20 sorguluk ölçüm tablosu (ms), README'ye |
| 3 | **Yükleme + metin + maske + kalıcı arşiv**: `udf_okuyucu.py`, `emsal_dosyalari`, `POST /emsal-belge`, `hukdok.belge_indir`, spool birimi, **`servis/sharepoint.py` + `03_LEXIS_EMSAL` klasörü**, `araclar/emsal_arsiv_toparla.py`, pymupdf/defusedxml/requests | `lexis_rapor/udf_okuyucu.py`, `servis/emsal_dosya.py`, `servis/sharepoint.py`, `servis/depo.py` (tablo), `servis/hukdok.py`, `docker-compose.yml`, `servis/requirements.txt`, `.env.example` | sentetik PDF/DOCX/UDF testleri; maske dökümü testi; "dosya adı saklanmaz" kilidi; SharePoint sahte Graph ile yükleme/yeniden deneme testi; gerçek klasöre tek dosya yükleme denemesi (lokal, kullanıcı .env'i) |
| 4 | **Ajanlar sahte modelle uçtan uca**: `servis/emsal_ajan.py` (sorgu üretici, okuyucu, denetçi, sıralama), `emsal_okumalar`, `model_cagrilari`, `POST /emsal-ara` NDJSON, `GET /emsal-sonuc/{sha}`; nginx allowlist + `proxy_buffering off` + bekçi + Vite | lexis-rapor `servis/`, HUKDOK `nginx.conf`, `backend/tests/test_nginx_lexis.py`, `frontend/vite.config.ts` | akış sözleşmesi testi; denetçi düşürme testi; önbellek testi; eşzamanlılık/409/429 testi |
| 5 | **Ekran + inceleme paketi**: diyalog, sonuç listesi, akış okuyucusu, taslağa biniş (F), "İndir" / "Arşivde aç" (E4: `GET /emsal-sonuc/{sha}/indir`, DOCX + metinler + JSON, arşive de yazılır), örnek kip verisi | `frontend/src/components/lexis/EmsalBulDiyalogu.tsx`, `EmsalKararListesi.tsx`, `lib/lexisAkis.ts`, `lib/lexisApi.ts`, `lib/lexisServis.ts`, `lib/lexisOrnekVeri.ts`, `types/lexis.ts`, `KararRafi.tsx`, `Tezgah.tsx`, `useTezgah.ts`; lexis-rapor `servis/inceleme_paketi.py` | vitest: diyalog akışı, onay → taslak, örnek kip; pytest: paket içeriği sentetik kararla, ad/kişi verisi kilidi |
| 6 | **Canlı Gemini, tek dosya** — ayrı onay; `.env`'de `LEXIS_EMSAL_MODEL=gemini` | — | token ve saniye raporu; maske dökümü |
| 7 | **Altın küme ölçümü**: `araclar/emsal_ajan_olcum.py` (zincir kümesi + atıf çiftleri + kör işaretleme girdisi); aday ve okuma aşaması AYRI | `araclar/`, README ölçüm tablosu | Recall@5/@10, MRR, aday kapsaması, gerekçe doğruluğu, token/sn |

Adım 2-5 sahte modelle, Gemini'siz yürür. Push/deploy yok (prod'da Lexis servisi kurulu değil).

## 5. Kabul ölçütleri (test süreci belgesiyle aynı)

- Aday aşaması: altın karar 30 adayda mı (zincir kümesinde ≥ %95 beklenir — aksi FTS/maske bozuk demektir).
- Okuma aşaması: aday listesindeyken ilk 5'e çekebildi mi (Recall@5, @10, MRR); iki aşama ayrı raporlanır.
- Gerekçe doğruluğu: denetçiden geçen öneri oranı; denetimden düşen hiçbir öneri ekrana çıkmaz (test kilidi).
- Maliyet: dosya başına token ve saniye (`model_cagrilari`'ndan), uçtan uca < 60 sn / 30 aday.
- Arama: 4.058 belgede ajan sorgusu < 200 ms (tek genel terimli sıralı sorgu için 290 ms istisnası raporda).
- Etiket hatası bilinen 31 karar (fiilsiz kabul) altın kümede işaretli tutulur.

## 6. Riskler ve açık sorular

- **Altın küme küçük** (4 çift). Külliyat dışa aktarımı (Aşama 7 adım 1) ya da kör işaretleme olmadan Recall sayısı
  anlamlı değildir; plan bunu gizlemez, 7. adım kümeyi aldığı gün koşar.
- **Kök bulma:** snowball Türkçe için ön-ek eşleşmesi şart; eş anlam (üreter / idrar kanalı) sorgu üreticisinin işidir,
  arama motorunun değil. Sahte üreticide eş anlam yok → sahte kipte aday aşaması canlıdan zayıf çıkar; ölçüm tablosu
  kipi yazar.
- **Maske kaçağı:** kartsız yüklemede bilinen ad listesi boştur; kalıp geçişi kusursuz değildir (README ölçümü).
  Canlı gönderim onayı maske dökümüyle birlikte sorulur.
- **Servis belleği 512 MB:** pymupdf + 30 adayın metni + asyncio kuyruğu; aday metni kırpılır, orijinal dosya 20 MB
  tavanlı. İlk koşuda `docker stats` ile ölçülür.
- **Tek uvicorn worker:** NDJSON akışı uzun bağlantı tutar; async uç olduğu için diğer istekler bloklanmaz, ama
  senkron parçalar (pymupdf, maske) `run_in_executor` ile koşar.
- **F ve G kararları** verilmeden 5. adımın "taslağa ekle" ve 2. adımın `kaynak` kapsamı kodlanmaz.
- **SharePoint kimliği:** HUKDOK'un arşiv kimliği Lexis `.env`'ine kopyalanır; secret'ın süresi
  (`SHAREPOINT_CLIENT_SECRET_EXPIRES_AT`) iki yerde takip edilir. Lokalde AVG TLS araya girmesi Graph çağrısında da
  görülebilir (`docker-compose.override.yml.example` CA paketi yolu çözer).
- **Karar PDF'lerinin pakete girmesi** host dizini bağlamaya bağlıdır (E4); bağlanmazsa paket yalnız metin taşır.
