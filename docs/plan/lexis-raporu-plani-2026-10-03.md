# Lexis raporu modülü planı — emsal külliyatı + medikolegal rapor taslağı

**Tarih:** 03.10.2026 · **Kaynak:** 03.10 sohbeti (pilot paket incelemesi + kart doluluk ölçümü) ·
**Durum:** **ONAY BEKLİYOR** — kuyruk görevleri (`gorevler/`) henüz yazılmadı; §2'deki kararlar
verilince §7'deki bölümleme görev dosyalarına dönüşür.

> **Yön değişikliği (03.10, kullanıcı kararı):** araç önce **HukuDok'tan ayrı** geliştirilecek, sonra
> entegre edilecek. Bu yüzden K1 ("modül HukuDok backend'inde") ve §7'deki görev bölümlemesi (HukuDok
> dosyalarına göre yazılmıştı) GEÇERSİZ; §1 ölçümleri, §3 istenecekler, §4 veri modeli, §5 emsal hattı ve
> §6 üretim akışı geçerliliğini korur. Ayrı aracın yeri ve entegrasyon biçimi kararlaşınca §2 ve §7
> yeniden yazılır.
>
> **Ayrı araç (03.10):** kardeş klasör `..\lexis-rapor` (ayrı depo). Okuyucu, maskeleme ve çıkarım modülü
> orada; durum ve pilot ölçümü o deponun `README.md`'sinde. **Güncel uygulama planı `..\lexis-rapor\PLAN.md`'dir**
> (rapor yazıcı + benzer eski rapor bulucu + Word çıktısı + HukuDok entegrasyonu); bu dosyanın §6-§7'si
> onun yerini tutmaz. Belge uçları HukuDok'ta VAR (04.10 düzeltmesi; önceki "yeni bir uç gerekir" cümlesi
> yanlıştı): `GET /api/cases/{case_id}/documents` (`backend/routes/documents.py:93`) ve
> `GET /api/documents/{doc_id}/download` (`:286`), ikisi de kullanıcı token'ıyla. HukuDok tarafında açık kalan
> tek soru kart yanıtının uzmanlığı verip vermediğidir (`lexis-rapor/PLAN.md` S5).
>
> **Arayüz önizlemesi (04.10, kullanıcı kararı):** ekran, çekirdeğin API'si beklenmeden HukuDok frontend'inde
> **sentetik örnek veriyle** kuruldu — **§10**. Backend'e dokunulmadı.

> **Bu dosya sözleşme kaynağıdır.** Görevler aşağıdaki tablo/uç/alan adlarına uyar; bir görev sözleşmeyi
> değiştirmek zorunda kalırsa ÖNCE burayı günceller. Sayılar/yollar koddan doğrulanır (ALTIN KURAL,
> `CLAUDE.md`). Buradaki ölçümler **lokal DB** ölçümüdür; prod'da yeniden ölçülmeden prod iddiası sayılmaz.

## 0. Amaç ve kapsam

Sigorta şirketlerine yazılan **Lexis medikolegal raporunun taslağını** HukuDok içinde üretmek:
dava kartı + dosyanın belgeleri (dilekçe, hekim beyanı, bilirkişi raporu, uzman görüşü) girer; şirketin
iskeletine uygun, emsal raporlardan beslenen, **insanın düzeltip imzaladığı** bir Word taslağı çıkar.

İki parça:

1. **Emsal külliyatı** — SharePoint Lexis sitesindeki eski raporlar okunur, alanları çıkarılır, dava
   kartına bağlanır, sisteme yüklenir.
2. **Rapor üretimi** — "Araçlar › Lexis Raporu" sayfası: dava seç → belge ver → taslak akar → bölüm bölüm
   düzelt → Word indir.

**Kapsam dışı (v1):** raporun şirkete gönderimi; nihai raporun otomatik arşivlenmesi; muallak tutarının
insansız kesinleşmesi (öneri + dayanak gösterilir, karar insanındır); eski raporlardan dava kartına toplu
geri yazım (§8).

## 1. Ölçümler — planın dayanağı

### 1.1 Pilot paket (`E:\HUKDOK_LEXIS_EGITIM_2026-10-03`, repo dışı, karartmasız)

| Ölçüm | Değer |
| --- | --- |
| Envanterdeki dosya klasörü | **3.607** (AK 1.424 · AXA 839 · Anadolu 668 · Quick 418 · Nippon 257 · Eureko 1) |
| Rapor dosyası olan klasör | **3.260**; Word'ü olan 3.154, yalnız PDF 106 |
| AXA rapor türleri | 212 ana rapor · 358 birinci revize · 250 ikinci revize |
| Pakette örnek rapor | 28 Word (26 klasör); PDF'lerin tamamında metin katmanı var (OCR gerekmedi) |
| Rapor uzunluğu | 2.100–15.200 karakter, 4–10 sayfa |
| Word yapısı | Adlandırılmış stiller (`Balk1/2/3`, `ListeParagraf`), üstbilgi/altbilgi + logo |

**İskeletler** (tek şablon yok; aynı şirkette karışık kullanılıyor):

| Kod | Bölümler | Görüldüğü yer |
| --- | --- | --- |
| `ANADOLU` | Hasar bilgileri (taraflar · poliçeler · talep/dava) · hastane · sulh ve muallak · iddia · yargı süreci · tıbbi görüş · poliçe incelemesi · değerlendirme ve sonuç | Anadolu |
| `ALTILI` | Mahkeme ve tazminat · iddia · sigortalı hekim beyanı · poliçe tespiti · uzman görüşü · değerlendirme | AK, Nippon (güncel), AXA (bir örnek) |
| `KISA` | Hasar bilgileri · inceleme konusu iddia · uzman görüşü · değerlendirme | Quick, AXA ana rapor, Nippon şablonu |
| `EK` | Ek inceleme · değerlendirme | AXA ek/revize rapor |

**Paketin eksikleri:** içerik etiketi yok (envanter yalnız kimlik); şablon dosyalarında gerçek kişi verisi
duruyor; Anadolu muallak tablosu 2021'de, pilot tutarlar 2022'de bitiyor; AXA kriterlerinde ölüm kalemleri
boş ve atıf yapılan emsal Excel'i yok; AK/Quick/Nippon kriteri yok; girdi belgeleri (dilekçe vb.) yok;
çok dosyalı klasörde "nihai rapor" kuralı yok; envanterin oluşturma tarihi taşıma tarihidir (2.688 klasör
2022), rapor tarihi metnin içindedir.

### 1.2 Dava kartı bağı ve doluluk (lokal DB, 03.10)

- Envanterin 3.362 tekil `DosyaNo`'su, **yazım normalize edilince** `cases.klasor_no_2`'nin bir öğesiyle
  **3.362/3.362** eşleşir. Ham eşleşme 306'dır: envanter `3.966`, bizde `3.966.00` ve alan `;` ile çok
  değerli. Normalizasyon: `;` ile böl → ilk iki blok → ikinci bloğun baştaki sıfırları at.
- Raporu olan 3.171 satır → **2.994 kart**.

| Alan (2.994 kart) | Doluluk | Not |
| --- | --- | --- |
| Esas no, dava konusu, karşı taraf adı | %99-100 | |
| Uzmanlık alanı | %99 | **Kart kolonu değil**, `case_foys.ham_veri` → `Uzmanlık Alanı` |
| Mahkeme / yargı birimi / dava tarihi | %98 / %94 / %95 | |
| Dava değeri / maddi tazminat | %84 / %77 | |
| Hasar no / hukuk no | %70 / %46 | Hukuk no Anadolu'da %4 |
| Manevi tazminat | %28 | AK %8 · AXA %8 · Nippon %6 · Anadolu %71 · Quick %83 |
| Aşama kararı / yerel karar durumu | %41 / %34 | AXA %71, Nippon %12 |
| Tıbbi süreç-olay-kusur-zarar | %22 | Beşi de dolu 320 kart; hiçbiri yok 2.305 kart |
| Hükmedilen manevi | %7 | ~200 kart |
| HukuDok'ta işlenmiş belge | %8 | Girdi belgeleri SharePoint klasöründe |
| Müvekkil kartı bağı, poliçe kaydı, karşı taraf doğum yılı | %0 | |

**Sonuç:** kimlik/mahkeme/uzmanlık karttan gelir; tıbbi içerik, manevi talep, poliçe, muallak, kusur, risk
ve emsal kararlar **rapor metninden çıkarılmak zorundadır**.

Değer havuzları (lokal DB satır sayısı): `specialties` 45 · `medical_processes` 150 · `medical_events` 859 ·
`alleged_faults` 10 · `patient_harms` 349 · `applied_methods` 343.

## 2. Kararlar (onayda kesinleşir)

| # | Konu | Öneri | Gerekçe |
| --- | --- | --- | --- |
| K1 | Modülün yeri | HukuDok backend'i (`services/lexis/`, `routes/lexis.py`) | Dava verisi, belge ve kimlik burada; karar 019 (monolit) |
| K2 | Emsal araması | **Postgres + etiket**; File Search/vektör deposu YOK | Külliyat küçük (~3.200 rapor, ~30 MB metin) ve etiketleri güçlü; uzmanlık %99 dolu. Yeni altyapı, kalıcı dış depo ve karar 017 tartışması gerekmez. Yetmezse ölçümle yeniden açılır (§8) |
| K3 | Etiket sözlüğü | Mevcut değer havuzları (tıbbi beşli + `specialties`); yeni sözlük açılmaz | Yeni dosyanın kartıyla aynı dil → doğrudan eşleşir; ileride karta geri yazım mümkün kalır |
| K4 | Çıkarım nerede koşar | Lokalde/ayrı makinede `JSONL` üretir; sunucuya yalnız `JSONL` yüklenir | Uzun Gemini koşusu prod web sürecine ve DB'sine binmez; yükleme yalnız yeni tablolara yazar (kart kilidi yok) |
| K5 | Çıktı biçimi | Word (`.docx`), şirket şablonundan | Büro Word'de düzeltiyor; raporlar stil tabanlı |
| K6 | Atıf kuralı | Taslakta emsal karar yalnız **karar bankasından** ya da dosyanın kendi belgelerinden gelir; kaynağı olmayan atıf basılmaz | Uydurma karar riski; Hukukbot'taki atıf doğrulama dersi |
| K7 | Muallak | Öneri + dayanak (kriter maddesi ve benzer rapor tutarları) gösterilir; kesin tutar insanındır | Kriter tabloları eski/eksik; tutarlar yıla bağlı |
| K8 | Erişim | Admin anahtarı `lexis_raporu`, varsayılan KAPALI; açıkken giriş yapmış her kullanıcı | `rapor_asistani` deseni (`services/app_settings.py`) |

**Sizin vermeniz gereken kararlar** (kod bunlara göre değişir):

- **G1 — Gizlilik.** Rapor metni çıkarım ve üretim sırasında Gemini'ye gider (belge analizinde bugün de
  böyle). Ek olarak külliyatın **tam metni Postgres'te** saklanır. Uygun mu, yoksa metin kimliksizleştirilip
  mi saklansın (ad, TC, poliçe no maskeli)?
- **G2 — Kullanıcı kitlesi.** Sayfayı kim görecek: herkes mi, yalnız Lexis ekibi mi?
- **G3 — Model.** Varsayılan mevcut analiz modeli; pilotta kalite yetmezse daha güçlü modele geçiş.

## 3. Bürodan / veri sağlayıcıdan istenecekler (insan adımı)

1. **Tam dışa aktarım:** rapor dosyası olan 3.260 klasörün **nihai rapor Word'ü** (yoksa PDF) + güncel
   envanter. Pilot paketle aynı düzen (`RAPORLAR\<ŞİRKET>\<klasör>\`).
2. **Nihai dosya kuralı:** bir klasörde birden çok rapor dosyası varken hangisi gönderilen sürüm.
3. **Güncel kriterler:** Anadolu muallak tablosu (2022 sonrası), AXA emsal listesi (Excel) ve ölüm
   kalemleri; AK, Quick, Nippon için yazılı kriter var mı.
4. **Temiz şablonlar:** her iskelet için kişi verisi içermeyen boş Word (logo/üstbilgi korunmuş).
5. **Uçtan uca deneme için 3-5 tam klasör:** girdi belgeleri + gönderilen rapor.

## 4. Veri modeli (yeni tablolar; `cases`'e dokunulmaz)

**`lexis_emsal_raporlar`** — bir satır = bir eski rapor.

| Grup | Alanlar |
| --- | --- |
| Kimlik | `sha256` (UNIQUE), `sirket`, `rapor_turu` (`ANA`/`EK`/`REVIZE_1`/`REVIZE_2`), `iskelet`, `rapor_no`, `rapor_tarihi`, `kaynak_yolu` |
| Bağ | `case_id` (FK, NULL olabilir), `dosya_no`, `hasar_no`, `hukuk_no` |
| Etiket | `uzmanlik`, `tibbi_surec`, `tibbi_olay`, `iddia_edilen_kusur`, `hastada_olusan_zarar`, `uygulanan_yontem` (havuz değerleri, çok değerli `;`), `zarar_kisi` (`BEBEK`/`COCUK`/`YETISKIN`), `yargi_yolu`, `kurum_turu` (`KAMU`/`OZEL`) |
| Talep ve sonuç | `talep_maddi`, `talep_manevi`, `muallak_maddi`, `muallak_manevi`, `kusur_tespiti` (`HATA_YOK`/`KOMPLIKASYON`/`KOMPLIKASYON_YONETIMI`/`HATA_VAR`), `risk_duzeyi`, `kazanma_ihtimali`, `rucu`, `teminat`, `muallak_dayanagi` (`KARAR`/`BILIRKISI`/`UZMAN`/`EMSAL`) |
| Metin | `iddia_ozeti`, `bolumler` (JSON: bölüm kodu → metin), `metin` |
| Çıkarım izi | `cikarim_modeli`, `cikarim_tarihi`, `dogrulama_durumu` (`OTOMATIK`/`INSAN`) |

**`lexis_emsal_kararlar`** — karar bankası: `rapor_id` (FK), `merci`, `esas_no`, `karar_no`, `karar_tarihi`,
`konu`, `hukmedilen_tutar`, `alinti`. Aynı karar birden çok raporda geçer; tekilleştirme anahtarı
`(merci, esas_no, karar_no)` normalize.

**`lexis_sirket_profilleri`** — `sirket_kodu`, `ad`, `iskelet_ana`, `iskelet_ek`, `sabit_metinler` (JSON),
`kriter_metni`, `muallak_tablosu` (JSON), `guncelleme`. Admin panelinden düzenlenir.

**`lexis_rapor_kosulari`** — üretim logu (`report_runs` deseni): kim, ne zaman, `case_id`, şirket, iskelet,
girdi belgelerinin sha256'ları, kullanılan emsal id'leri, çıktı sha256.

Migrasyon kuralı: tablolar `("table", ...)`, kalıcı UNIQUE/index'ler **ayrı `("index", ...)` op'u**
(`CLAUDE.md` "Migrasyon op türleri" tuzağı).

## 5. Emsal hattı

```
dizin + envanter.xlsx ──► lexis_emsal_cikar.py ──► emsal.jsonl ──► lexis_emsal_yukle.py ──► DB
                          (okuyucu + Gemini)        (taşınır)      (kuru koşu / --apply)
```

1. **Okuyucu (Gemini'siz, belirlenimci):** Word'ü stillerden bölümlere ayırır, iskeleti tanır; kapak
   alanlarını (tarih, rapor no, hasar/hukuk no), talep ve muallak tutarlarını düzenli ifadeyle çeker.
   Yalnız PDF'i olan 106 klasör için metin katmanından aynı çıkarım.
2. **Çıkarım (Gemini):** etiketleri havuz değerlerine eşler (havuz dışı değer üretmez; uymayan `NULL` +
   ham ifade raporda), `iddia_ozeti`, kusur/risk/rücu sınıfları ve emsal kararlar. Şema doğrulamasından
   geçmeyen kayıt JSONL'e `hata` olarak düşer, DB'ye girmez.
3. **Çapraz doğrulama:** Gemini'nin tutarları okuyucunun düzenli ifade sonucuyla, rapor no envanterle
   karşılaştırılır; uyuşmayan satır `UYARI`.
4. **Yükleme:** `sha256` ile idempotent; dosya no normalizasyonuyla karta bağlar; varsayılan kuru koşu,
   `--apply` insan kararı. Yalnız yeni tablolara yazar.

**Ölçüm kapısı (Faz 1 çıkışı):** pilot 28 raporda alan isabeti elle denetlenir. Eşik önerisi: tutar ve
kimlik alanları %95, etiket alanları %85. Eşik altı alan düzeltilmeden tam paket koşulmaz.

## 6. Rapor üretimi

**Akış** (`POST /api/lexis/taslak`, NDJSON; `analyzer` stream sözleşmesinin olay biçimi):

1. **Girdi:** `case_id`, rapor türü (ana/ek), yüklenen ya da karttaki belgelerden seçilen dosyalar.
2. **Şirket ve iskelet:** kartın müvekkil sigorta şirketinden → `lexis_sirket_profilleri`.
   (`cases.ofis_no_kodu` lokalde şirketi veriyor; ofis no göçü prod'da koşulmadığı için tek kaynak
   yapılmaz — işçi görev doğrular.)
3. **Olgular:** karttan gelenler belirlenimci doldurulur (mahkeme, esas, talep, hasar no); eksikler
   belgelerden çıkarılır ve "belgeden" işaretiyle gösterilir.
4. **Emsal seçimi** (`services/lexis/emsal_secici.py`, Gemini'siz): uzmanlık süzgeci → etiket örtüşmesi
   puanı (işlem, kusur, zarar, yargı yolu, kurum türü) → aynı şirket ve yakın tarih önceliği → ilk 3-5 rapor.
5. **Yazım:** bölümler sırayla akar; iddia ve beyan özetleri belgelerden, uzman görüşü bölümü belgelerden +
   karar bankasından (K6), değerlendirme emsal raporların kalıplarından.
6. **Muallak önerisi:** şirket kriteri + benzer raporlardaki talep→muallak ilişkisi; dayanağıyla birlikte.
7. **Çıktı:** ekranda bölüm bölüm düzenlenir; `POST /api/lexis/word` şablonu doldurur, koşu loglanır.

**Ek rapor:** aynı akış, `EK` iskeleti; girdiye dosyanın önceki raporu (`lexis_emsal_raporlar`, aynı
`case_id`) eklenir.

**Uçlar:** `GET /api/lexis/durum` · `GET /api/lexis/emsaller?case_id=` · `POST /api/lexis/taslak` ·
`POST /api/lexis/word` · `GET|PUT /api/admin/lexis-profilleri`. Konteyner nginx'inde `/api` zaten
proxy'li; yeni location gerekmez.

## 7. Görev bölümlemesi (onay sonrası `gorevler/`'e yazılır; id'ler G258'den)

| Görev | Bant | Bağımlı | İş |
| --- | --- | --- | --- |
| G258 | backend | - | Şema: dört tablo + modeller + migrasyon + index op'ları; bekçi testi |
| G259 | backend | G258 | Okuyucu: Word/PDF → bölümler + iskelet + kapak/tutar alanları; **sentetik** örneklerle test |
| G260 | backend | G259 | Çıkarım: Gemini etiket + karar çıkarımı, havuz eşlemesi, şema ve çapraz doğrulama; `scripts/lexis_emsal_cikar.py` → JSONL |
| G261 | backend | G260 | Yükleme: `scripts/lexis_emsal_yukle.py` (dosya no normalizasyonu, idempotent, kuru koşu, satır raporu) |
| — | insan | G261 | **Pilot koşu + ölçüm kapısı** (28 rapor) → tam paket çıkarımı |
| G262 | backend | G261 | Bağımlılık: Word yazma kütüphanesi (`requirements.txt`, imaj yeniden kurulur); duman testi |
| G263 | backend | G262 | Şirket profilleri: tohum + admin uçları + `lexis_raporu` anahtarı |
| G264 | backend | G263 | Emsal seçici + `GET /api/lexis/emsaller`; puanlama testleri |
| G265 | backend | G264 | Taslak üretimi: `POST /api/lexis/taslak` (olgu, bölümler, atıf kuralı, muallak önerisi) + koşu logu |
| G266 | backend | G265 | Word çıktısı: `POST /api/lexis/word`, şablon doldurma |
| G267 | frontend | - | `lib/lexisApi.ts` + tipler + NDJSON okuyucu (bu plandaki sözleşmeden) |
| G268 | frontend | G267, G265 | `/lexis-raporu` sayfası + rota + "Araçlar" menüsü |
| G269 | frontend | G263, G268 | Admin "Lexis Şirket Profilleri" sekmesi |
| G270 | docs | G266, G269 | `docs/mimari/lexis-raporu.md` + `CLAUDE.md` + karar kaydı |

**Paralellik:** backend zinciri seri (aynı stack; hub dosyalar `models.py`, `database.py`, `api.py`).
G267, backend'le paralel koşar. **Tahmin:** Faz 1 (G258-G261) 1-2 gece + pilot gündüzü; Faz 2-3
(G262-G270) 3-4 gece. Faz 2 görevlerinin kabul kriterleri pilot kapısından sonra kesinleşir; o yüzden
ilk onayda yalnız **G258-G261** kuyruğa yazılır.

**Test verisi kuralı:** repo'ya gerçek rapor girmez. Test örnekleri sentetik üretilir; pilot paket repo
dışında kalır.

## 8. Sonraya bırakılanlar (ölçümle açılır)

- **Anlam araması (embedding):** etiketle seçilen emsaller pilotta isabetsiz çıkarsa.
- **Karta geri yazım:** rapordan çıkan tıbbi beşli, boş olan 2.305 karta yazılabilir. Toplu kart yazımıdır
  → ayrı karar, mesai dışı kuralı.
- **Öneri–gerçekleşen kıyası:** hükmedilen tutar yalnız ~200 kartta dolu; örnek büyüyünce.
- **Nihai raporun arşive bağlanması:** gönderilen raporun dava belgesi olarak kaydı ve külliyata dönmesi.

## 9. Riskler

- **Havuz eşlemesi:** `medical_events` 859, `patient_harms` 349 değer; modelin doğru öğeyi seçmesi pilotta
  ölçülmeden bilinmez. Kötü çıkarsa önce uzmanlığa göre daraltılmış aday listesi verilir.
- **Nihai dosya belirsizliği:** kural gelmezse aynı dosyanın taslağı ve gönderileni birlikte yüklenir;
  `sha256` bunu ayıramaz.
- **Şablon doldurma:** Word'lerde içindekiler tablosu ve üstbilgi var; doldurma sonrası içindekilerin
  güncellenmesi Word açılışına kalabilir. G262 dumanında denenir.
- **Kriter eskiliği:** güncel tablolar gelmezse muallak önerisi yalnız benzer rapor tutarlarına dayanır ve
  bu açıkça gösterilir.
- **Şirket eşlemesi prod'da:** ofis no göçü prod'da koşulmadı; müvekkil adından profil eşlemesi gerekir.

## 10. Arayüz önizlemesi — `/lexis` (04.10.2026)

Kullanıcı kararları (04.10): sayfa **gerçek kodda, örnek veriyle** kurulur; düzen **üç bölgeli tezgâh**; giriş
**yalnız Araçlar menüsü** (dava kartına düğme yok); ilk sürümde dört ek ekran (taslak geçmişi, emsal
kütüphanesi tarayıcısı, kart bağı inceleme listesi, şirket profilleri + muallak kriterleri).

**Kapı:** menü öğesi yalnız yöneticide (`components/shell/Sidebar.tsx` `yalnizYonetici`), rota
`ProtectedAdminRoute` ile sarılı (`App.tsx`). Sayfa ağ isteği atmaz; üstte kalıcı "Örnek veri" şeridi durur.
Kullanıcı kitlesi (`lexis-rapor/PLAN.md` S4) entegrasyonda kararlaştırılır.

**Dosyalar** (`frontend/src/`):

| Dosya | Ne |
| --- | --- |
| `types/lexis.ts` | Sözleşme. Çekirdek tipleri `lexis_rapor/*.py`'den birebir (alan adları Python adlarıyla aynı); çekirdekte olmayan arayüz tipleri "çekirdekte yok" notuyla: `LexisUyari` (kodlu, yer bilgili uyarı), `MuallakOnerisi`, `ISKELET_BOLUMLERI` (iskelet başına sıralı bölüm + başlık), `DosyaGirdisi`, `LexisTaslak`, akış olayı, `SirketProfili`, `TaslakKosusu`, `RaporBagi` |
| `lib/lexisApi.ts` | `LexisApi` arayüzü + bellekte çalışan örnek adaptör; `ORNEK_VERI` bayrağı. Entegrasyonda aynı arayüz `apiClient.fetch` ile uygulanır |
| `lib/lexisOrnekVeri.ts` | Sentetik veri: 4 dava (her yazılabilir iskeletten biri), 8 emsal rapor, kart bağları, şirket profilleri, geçmiş. **Uydurmadır; pilot paketten metin kopyalanmadı** |
| `lib/lexisDenetim.ts` | Örnek adaptörün denetimi (dayanak kuralı K13, muallak sınırları, boş alan/bölüm) — çekirdekteki `yazici.dogrula`'nın ekranı sürecek kadar taklidi; entegrasyonda kalkar |
| `lib/lexisMetin.ts` | Alıntıyı kaynak metinde bulma (vurgu aralıkları; çekirdeğin toleransıyla), tutar/tarih yazımı — entegrasyonda kalır |
| `pages/LexisPage.tsx` | Odak modunda sayfa; sekme `?sekme=` ile URL'de; "Rapor yaz" sekme değişince bağlı kalır |
| `components/lexis/` | Bileşenler (aşağıda) + `useTezgah.ts` (tezgâh durumu) + `useVeri.ts` (sekme verisi) + `yardimcilar.ts` |

**Sekmeler ve bileşenleri:**

| Sekme (`?sekme=`) | Bileşenler |
| --- | --- |
| Rapor yaz (varsayılan) | `Tezgah` — **sol** `DavaSecici`, `KunyeKarti`, `BelgeListesi`, `EmsalListesi` (+ `EmsalOkuyucu`, `EmsalEkleDiyalogu`); **orta** `UretimSeridi`, `BolumGezgini`, `EtiketliBolum`, `OzetBolum`, `DegerlendirmeBolumu` → `MaddeKarti`; **sağ** `UyariListesi`, `MuallakKarti`, `DayanakGoruntuleyici`, `CiktiCubugu`. Dar ekranda sol bölge `lg`, sağ bölge `xl` altında çekmece |
| Geçmiş (`gecmis`) | `GecmisTablosu` — koşu logu |
| Kütüphane (`kutuphane`) | `KutuphaneTarayici` (filtre + tablo + okuyucu), `KararBankasiTablosu` |
| Kart bağı (`kart-bagi`) | `KartBagiListesi`, `KartSecimDiyalogu` (K8: kartı insan seçer, geri alınabilir) |
| Şirketler (`sirketler`) | `SirketProfilleri`, `MuallakKriterTablosu`. Önizlemede Lexis sayfasının sekmesi; entegrasyonda Yönetim paneline taşınabilir (`AdminPage.tsx`'e dokunulmadı — örnek veri gerçek Yönetim sekmeleriyle karışmasın diye) |

**Tezgâh davranışı:** taslağı silen her eylem (dava ya da künye değişimi, yeniden yazım) onay ister; yazımdan
önce modele gidecek belgeler ve emsal sayısı gösterilir (K4). Metin düzenlemesi denetimi bayatlatır (madde
"denetlenmedi" görünür), alandan çıkınca ya da yapısal değişiklikte (madde ekle/sil/taşı, tür değişimi, kesin
muallak tutarı) yeniden denetlenir. Uyarıya tıklanınca ilgili madde / alan / bölüme gidilir; "Kaynakta göster"
alıntıyı kaynak paragrafta vurgular. Muallakta kesin tutar insanındır; boş bırakılan alanda öneri geçerlidir (K11).

**Entegrasyonun arayüzden beklediği** (çekirdek bugün vermiyor): uyarıların düz metin yerine kodlu ve yer
bilgili gelmesi (`bolum`, `madde`, `alan`); iskelet başına bölüm sırası ve görünen başlık; etiketli satırların
etiketiyle birlikte gelmesi; özet paragrafının kaynak belgesi; `Emsal.gerekce()` metninin telde gelmesi.

**Önizlemede olmayanlar:** Word çıktısı (düğme bilgi verir), kalıcılık (sayfa yenilenince durum sıfırlanır),
gerçek dava araması, belgelerin modele gönderimi.
