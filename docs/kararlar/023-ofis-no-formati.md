# 023 — Ofis no yeni formatı: `<MÜVEKKİL KODU>-<SIRA>[-<SİGORTALI>]-<TÜR>`, tüm kartlar yeniden numaralanır

> Son doğrulama: 2026-09-30 · 9b07017 (G234). Bu doküman yazıldığında **kod henüz değişmedi**:
> aşağıdaki "bugünkü durum" atıfları eski formatın kodunu gösterir; yeni formatı uygulayacak
> dosyalar G235-G240 ile gelir ve metinde **(planlanan)** diye işaretlidir.

- **Durum:** kabul — kullanıcı kararı (28.09.2026). [016](016-ofis-no-kategori-rejimi.md)'nın
  "geçmiş dokunulmaz / geriye dönük retag yapılmaz" parçasını ve iki haneli kod rejimini
  (`D1`/`S3`/`K1`) **değiştirir**; [002](002-ofis-no-isim-blogu-onceligi.md)'nin müvekkil
  önceliği korunur, kod önceliği (`bestCategoryCode`) yeni kurala göre yeniden yazılır.
  Bu doküman G235-G240 görevlerinin **tek şartnamesidir**.
- **Bağlam:** Bugünkü numara `<KOD>.<AD 10 karakter, '.' dolgulu>.<SIRA>.<TÜR>.<HİZMET>`
  biçimindedir (üretici `frontend/src/lib/caseNumberUtils.ts`, kanonik ikizi
  `backend/scripts/retag_tracking_nos.py`). Sorunları:
  - İki haneli kod bilinmeden okunmuyor (`D1`, `H2`, `S3`).
  - `S0` 3.204 kartta onlarca sigorta şirketini tek koda topluyor; `S4` iki ayrı şirkete
    (Corpus, Quick) gidiyor (28.09 ölçümü).
  - Ad bloğu 10 karaktere kesiliyor ve `.` ile dolduruluyor (`caseNumberUtils.ts:73-88`);
    uzun soyad kırpılıyor, kısa ad noktalarla şişiyor.
  - Sigorta dosyasında asıl özne olan sigortalı hekim numarada yalnız sigortacının yerine
    geçerek görünüyor; "kaçıncı AXA dosyası" ile "hangi hekim" aynı numarada birlikte okunamıyor.
  - Sıra numarasını frontend hesaplıyor; sunucu yalnız ad bloğuna göre öneri veriyor
    (`backend/routes/cases.py:151`, `substr(tracking_no, 4, 10)`).

## Karar

### 1. Format

```
<MÜVEKKİL KODU>-<SIRA>[-<SİGORTALI>]-<TÜR>
```

- Bloklar arası ayraç `-`, blok içinde `.`.
- Doldurma karakteri (`.` / `X` padding) **YOK**; ad **kesilmez**.
- Hizmet bloğu **YOK**.
- Yalnız ASCII büyük harf: Türkçe harfler ASCII'ye indirilir (Ö→O, Ü→U, Ş→S, Ç→C, Ğ→G, İ/ı→I).

### 2. Kişi/kurum kategorileri

Müvekkil sigorta şirketi değilse numara `KOD.<ad>` ile başlar.

- **Kişide** `<ilk adın baş harfi>.<SOYAD>`: çok adlı kişide ilk ad alınır, son kelime
  soyaddır; `Dr.` / `Hem.` gibi unvanlar atılır.
- **Kurumda** genel kelimeler atılır, ilk anlamlı kelime alınır — bugünkü `CORP_STOP`
  mantığı (`frontend/src/lib/caseNumberUtils.ts:41`, ikizi
  `backend/scripts/retag_tracking_nos.py:71`).

| Kategori | Eski kod | Yeni kod | Örnek |
| --- | --- | --- | --- |
| Doktor | D1 | `DR` | `DR.M.OZTURK-0003-HUK` |
| Sağlık Çalışanı | D2 | `SC` | `SC.A.KOCA-0001-HUK` |
| Hasta | H1 | `HS` | `HS.A.KAYA-0001-IDR` |
| Özel Hastane | H2 | `OH` | `OH.SAFA-0001-HUK` |
| Kurum | X1 | `KR` | `KR.ENTHONE-0015-CEZ` |
| Bireysel | X1 | `BR` | `BR.T.KOC-0009-ICR` |
| Diğer | X1 | `DG` | `DG.SUMUTU-0001-HUK` |

- Eski serbest kategori adları: Klinik → `OH`; Acente, Dernek → `KR`.
- **Kategorisiz** müvekkil: adında şirket işareti (A.Ş., AŞ, Ltd., Şti., San., Tic., Inc.,
  GmbH…) varsa `KR`, yoksa `BR`.

### 3. Sigorta şirketleri

Müvekkil sigorta şirketiyse numara **şirket koduyla** başlar; sigortalı hekim ayrı blokta durur.

| Şirket | Eski kod | Yeni kod | Örnek |
| --- | --- | --- | --- |
| AK Sigorta | S1 | `AK` | `AK-1189-DR.E.ALTUNC-HUK` |
| Anadolu Sigorta | S2 | `ANADOLU` | `ANADOLU-1317-DR.S.OZAY-IDR` |
| AXA Sigorta | S3 | `AXA` | `AXA-3297-DR.E.ALTUNC-HUK` |
| Corpus Sigorta | S4 | `CORPUS` | `CORPUS-0003-DR.A.KAYA-HUK` |
| Quick Sigorta | S4 | `QUICK` | `QUICK-0588-DR.Y.TUYLU-HUK` |
| Eureko Sigorta | S5 | `EUREKO` | `EUREKO-0409-HUK` |
| Nippon Sigorta | S6 | `NIPPON` | `NIPPON-0178-DR.H.BAGIS-HUK` |
| Sompo Sigorta | S7 | `SOMPO` | `SOMPO-0206-HUK` |
| Koru Sigorta | S0 | `KORU` | `KORU-3172-DR.T.SEVINC-IDR` |
| HDI Sigorta | S0 | `HDI` | `HDI-0004-HUK` |
| Ziraat Sigorta | S0 | `ZIRAAT` | `ZIRAAT-0001-HUK` |
| Listede olmayan sigortacı | S0 | `SG` | `SG-0001-HUK` |

Sigortalı yoksa blok yazılmaz: `AXA-3297-HUK`.

### 4. Kod listeleri düzenlenebilir

Kategori→kod ve sigorta şirketi→kod eşlemeleri (+ müvekkil adında aranan eşleşme kelimeleri)
admin panelinden yönetilir **(planlanan)**. Kod değişikliği yalnız **YENİ** kartları etkiler;
verilmiş numara değişmez. Kodlar birbirinden farklıdır — kategori kodu ile sigorta kodu da
çakışamaz.

### 5. Birden çok müvekkil

- Sigortacı varsa numara **sigortacınındır**.
- Sigortacı yoksa öncelik: Doktor > Sağlık Çalışanı > Hasta > Bireysel > Diğer/kategorisiz >
  Özel Hastane > Kurum — bugünkü `pickNameClient` sırası
  (`frontend/src/lib/caseNumberUtils.ts:164`, karar [002](002-ofis-no-isim-blogu-onceligi.md)).
- Sigortacı + doktor birlikte müvekkilse doktor **sigortalı bloğuna** yazılır.

### 6. Kategori kaynağı

Çoğu kartın taraf kaydı kategorili müvekkil kaydına BAĞLI DEĞİL (28.09 ölçümü); bu yüzden
kategori şu sırayla aranır:

1. `clients.category`
2. föy `muvekkil_tipi` (Sigorta / Doktor / Kurum / Hasta / Diğer Sağlık Çalışanı) —
   `case_foys.muvekkil_tipi`, `backend/models.py:375`
3. eski numaranın ilk bloğu: D1→`DR`, D2→`SC`, H1→`HS`, H2→`OH`, S1-S7→şirket kodu,
   S0→adından şirket ya da `SG`, X1→ad kuralıyla `KR`/`BR`.

### 7. Sigortalı bloğu

Yalnız sigorta müvekkilli kartta yazılır. Kişinin **kendi kategori koduyla**
(`DR.<baş harf>.<SOYAD>`; hemşirede `SC.`, kurumda `OH.`/`KR.`) ve **TEK kişi**.

Kaynak önceliği:

1. föy `ham_veri->>'Sigortalı'` (`case_foys.ham_veri`, `backend/models.py:383`)
2. `case_parties.role='Sigortalı'` (aktarımın yazdığı `THIRD` taraf,
   `backend/scripts/hukdok_aktarim.py:2269`)
3. "Diğer Davalı" içindeki ilk hekim.

Bulunamazsa blok yazılmaz, kart **"sigortalı eksik"** listesine düşer.

### 8. Sıra

- **Müvekkil kodu başına** sayılır; 4 haneden kısa ise sola sıfır (`0003`), 9999'u aşarsa
  doğal uzar.
- Kayıt anında **sunucu** verir (DB sayacı, atomik) **(planlanan)**; frontend yalnız önizler.
- Numara verildikten sonra **DEĞİŞMEZ** — müvekkil / tür / sigortalı sonradan düzeltilse de.

### 9. Tür kodu

`cases.file_type`'tan (`backend/models.py:23`):

| Dosya türü | Kod |
| --- | --- |
| Hukuk | `HUK` |
| Ceza | `CEZ` |
| İcra | `ICR` |
| Arabuluculuk | `ARB` |
| Savcılık | `SAV` |
| İdare / İdari Yargı | `IDR` |
| Tahkim | `THK` |
| Vergi | `VRG` |
| Danışmanlık | `DAN` |
| boş | `HUK` |

## Göç kuralları

- **Tüm kartlar** yeniden numaralanır — soft-delete edilenler **dahil** (unique index onları
  da kapsar).
- Sıra, müvekkil kodu içinde `cases.opening_date` sırasıyla verilir; tarihsizler sonda,
  `created_at` sırasıyla.
- Her karta eski numarayı taşıyan bir `case_history` satırı yazılır.
- `case_foys.onceki_tracking_no` (`backend/models.py:389`) aynı eski→yeni eşlemesiyle çevrilir.
- **Eski numarayla arama çalışmaya devam eder.**
- Eski→yeni CSV veri ekibine verilir.
- **Prod göçü yalnız kullanıcı kararıyla**, kuru koşu raporu görüldükten sonra yapılır.
- Sigortalısı bulunamayan kart göçü BEKLETMEZ: bloksuz numaralanır, "sigortalı eksik"
  listesine düşer (§7).

## Bağımlılık haritası (28.09 taraması)

| Tüketici | Numaraya bağlılık | Yer |
| --- | --- | --- |
| SharePoint arşivi | **Bağlı DEĞİL** — dosya/klasör adında numara yok | — |
| Veri ekibi G154 döngüsü — cevaplı kart eşlemesi | Numarayı regex'le tanır (`TRACKING_NO_DESENI`, eski format) | `backend/scripts/cevapli_kart_eslemesi.py:71` |
| Veri ekibi G154 döngüsü — aktarım kart eşlemesi | `{SistemNo: tracking_no}` CSV haritası, numarayla kart arar | `backend/scripts/hukdok_aktarim.py:216`, `:1698` |
| Veri ekibi G154 döngüsü — cevap CSV'si | `tracking_no` kolonu taşır | `backend/services/teslim_cevap.py:57` |
| Hukukbot export'u | Yalnız bilgi alanı (anahtar değil) | `backend/routes/export.py:143`, `:237` |
| `ix_cases_tracking_no` | UNIQUE; silinmiş kartları da kapsar (kısmi değil) | `backend/managers/case_manager.py:48` |
| `idx_cases_tracking_name_block` | `substr(tracking_no, 4, 10)` — yeni formatta **anlamsız** (ad bloğu sabit konumda değil) | `backend/database.py:690`, kullanan `backend/routes/cases.py:151` |

Not: karar [016](016-ofis-no-kategori-rejimi.md) numaranın SharePoint klasör adlarında
yaşadığını retag'ı reddetme gerekçesi saymıştı; 28.09 taraması dosya/klasör adında numaranın
**olmadığını** gösterdi. 016'nın "yeniden açma tetikleyicisi"ne gerek kalmadan göç mümkündür.
Gönderilmiş dış yazışmalardaki eski numaralar ise değişmez — bunu "eski numarayla arama"
ve eski→yeni CSV karşılar.

## Gerekçe

- **Okunurluk:** kod kendini anlatır (`DR`, `AXA`); numara tabloya bakmadan okunur.
- **Sigorta dosyasında iki bilgi birlikte:** "kaçıncı AXA dosyası" (müvekkil kodu başına sıra)
  ve "hangi hekim" (sigortalı bloğu) aynı numarada.
- **Şirket başına ayrı kod:** `S0` torbası ve `S4` çakışması kalkar.
- **Kesme/dolgu yok:** ad tam yazılır, numara gereksiz uzamaz.
- **Sunucu sayacı:** sıra tek yerde ve atomik verilir; frontend'in hesapladığı sırayla
  çakışma yarışı biter.
- **Değişmezlik ilkesi korunur** (016'nın çekirdeği): numara kimliktir; göç tek seferlik ve
  izlidir (`case_history` + `onceki_tracking_no` + CSV), göçten sonra verilmiş numara bir daha
  değişmez. Raporlama yine `clients.category`'den okur, numaradan değil.

## Reddedilenler

- **Büro geneli yıllık sıra (`2026-0451`)** — "kaçıncı AXA dosyası" bilgisi kaybolur.
- **Çok hekimde "VD" eki** — sigortalı bloğu TEK kişidir.
- **Sigortalısız kartta göçü bekletmek** — kart bloksuz numaralanır, eksik listesine düşer.
- **Eski iki haneli kodları (D1/S3) korumak** — `S0` 3.204 kartta onlarca şirketi tek koda
  topluyordu, `S4` iki şirkete gidiyordu, kod bilinmeden okunmuyordu.
- **Kategorisiz grubu `HS`/`DR`'ye katmak** — 1.686 kartlık tıp dışı grup hasta/doktor
  görünürdü; bu yüzden ad kuralıyla `KR`/`BR`.

## Sonuçları ve sınırları

- Kod bu kararla DEĞİŞMEDİ. Üretici, sunucu sayacı, admin kod listeleri, göç script'i ve
  G154 zincirinin yeni formata uyumu G235-G240'ta gelir **(planlanan)**; `CLAUDE.md` ve
  `docs/mimari/` o görevlerin sonunda (G240) güncellenir.
- `idx_cases_tracking_name_block` ve onu kullanan sıra önerisi yeni formatta işlevsizdir;
  kaldırılması/yerine geçecek yol uygulama görevlerinin işidir.
- `TRACKING_NO_DESENI` yalnız eski formatı tanır; veri ekibinin cevaplarında yeni numara
  dolaşmaya başlamadan önce güncellenmelidir.
- `backend/scripts/retag_tracking_nos.py` eski formatın üreticisidir; göçten sonra elle
  çalıştırılması bu kararı ihlal eder.
- **İlgili:** [002](002-ofis-no-isim-blogu-onceligi.md), [016](016-ofis-no-kategori-rejimi.md),
  görev dosyaları `gorevler/gorev/G234.md` – `G242.md`.
