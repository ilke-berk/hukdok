# FAZ F — HUKDOK aktarımı: gereksinim belgesi

**Kaynak:** `HUKDOK_SORU_RAPORU_2026-08-11_CEVAPLI.xlsx` (karşı taraf ekibinin cevabı,
12.08.2026) — 68 eşleme teyidi, 15 soru, 13 taşınma kararı, 20 alan işaretlemesi,
2 ek tablo. Cevaplar master üzerinde ölçülerek verilmiş.

> **Bu belge yaşayan bir spec'tir, arşiv değildir.** İçindeki her "sistemde var/yok"
> iddiası `backend/models.py` ve `backend/database.py` okunarak doğrulandı (12.08.2026).
> Ana plan: [`temizlik-ve-yapisal-saglik-plani-2026-08-11.md`](temizlik-ve-yapisal-saglik-plani-2026-08-11.md) §8.

---

## 0. Aktarımın karakteri değişti

Taslakta "8.409 föylük tek seferlik aktarım" varsayılıyordu. Cevaplar bunu çürüttü:

- **Göz hastalıkları dilimi için tarih taahhüdü YOK** (çalışma 08.08.2026'da başladı,
  534 dosya, ~290'ı kararlı). Teslim **partiler hâlinde** gelecek.
- Karşı taraf ayrıca dört ayrı düzeltme listesi göndereceğini yazdı: 16 satırlık ıslah
  hatası, 98 satırlık manevi>toplam, arşiv tarihi tutarsızlıkları, istinaf başvuran
  taraf normalizasyonu, Müvekkil Tipi hataları.

**Sonuç: aktarım bir olay değil, tekrar eden bir süreçtir.** İdempotency artık
"iyi olurdu" değil, işletim modelinin kendisi. Ana plan §8'deki yazma-yolu tasarımı
(stabil dış anahtar + `ON CONFLICT DO UPDATE` + SAVEPOINT + imleç) bu yüzden pazarlıksız.

---

## 1. Yeni şema

### 1.1 Yeni kolonlar (11) — modelde YOK, doğrulandı

| Alan | Kaynak sütun | Dolu satır | Not |
| --- | --- | --- | --- |
| `islah_tutari` | Islah Tutarı | 8.402 | S1: ıslahla **EKLENEN** miktar. Güncel talep = Dava Değeri. Ayrı alan olarak kalır (zamanaşımı + harç açısından ayrıca sorulan bilgi) |
| `arsiv_tarihi` | Arşiv Tarihi | 4.702 | S4: dosya kapanış süresi analizi + ön muhasebe buna dayanıyor |
| `istinaf_basvuran_taraf` | İstinaf Mah. Başvuran Taraf | 406 | S5: temyizle simetri. **Kapalı liste:** Davacı / Davalı / Her İki Taraf |
| `arabuluculuk_no` | Arabuluculuk Numarası | 1 | Taşınmama önerimiz **reddedildi**. 435 arabuluculuk föyünde esas numarasının yerini tutuyor; alan açılırsa tamamlayacaklar |
| `arabuluculuk_karar_tarihi` | Arabuluculuk Karar Tarihi | 1 | Numara alanı açılınca birlikte |
| `tibbi_surec` | Tıbbi Süreç | 1.339 | Branş bazlı büyüyen sözlük. Boş = "o branşın analizi henüz yapılmadı" |
| `tibbi_olay` | Tıbbi Olay | 1.341 | Büyüyen sözlük (bugün 214 değer) |
| `iddia_edilen_kusur` | İddia Edilen Kusur | 1.330 | **KAPALI 7 değerli referans listesi** — hiçbir branşta değişmez |
| `hastada_olusan_zarar` | Hastada Oluşan Zarar | 1.318 | Büyüyen sözlük (bugün 89 değer) |
| `uygulanan_yontem` | Uygulanan Yöntem | 436 | Branşa göre kapalı liste (kadın doğum: Vajinal / Sezaryen) |
| *(esas tarihçesi)* | Eski Dosya No | 616 | Kolon değil **tablo** — bkz. §1.3 |

### 1.2 Zaten var — ek iş YOK (koddan doğrulandı)

Karşı tarafın "alanları açın" dediği iki küme mevcut:

- **Karar düzeltme detayları:** `karar_duzeltme_esas_no`, `karar_duzeltme_karar_no`,
  `karar_duzeltme_tarihi`, `karar_duzeltme_teblig_tarihi`, `karar_duzeltme_aciklama` ✅
- **Temyiz künyesi:** `temyiz_basvuru_tarihi`, `temyiz_karar_no`, `temyiz_teblig_tarihi`,
  `temyiz_eden_durumu`, `temyiz_karar_aciklama` ✅
- Ayrıca: `istinaf_teblig_tarihi`, `kesinlesme_tarihi`, `infaz_tarihi`, `yeni_esas_no` ✅

Bunlar **boş duruyor**; aktarım dolduracak.

### 1.3 Esas numarası tarihçesi — yeni tablo

**Sorun:** tek kavram bugün beş kolona dağılmış (`esas_no`, `yeni_esas_no`,
`istinaf_esas_no`, `temyiz_esas_no`, `karar_duzeltme_esas_no`) ve altıncısı geliyor.
"Eski Dosya No" sütununun içeriği aslında **önceki esas numaralarıdır** (S7 düzeltmesi),
üstelik çok değerli: `"2017/325 - 2024/145"`. Görevsizlik/yetkisizlik/bozma sonrası
değişen esasların tarihçesi. Eski esasla **arama yapılıyor**.

```sql
CREATE TABLE case_esas_numbers (
    id          SERIAL PRIMARY KEY,
    case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    esas_no     VARCHAR(50) NOT NULL,
    stage       VARCHAR(20) NOT NULL,   -- YEREL|ISTINAF|TEMYIZ|KARAR_DUZELTME|ONCEKI
    court       VARCHAR(200),
    is_current  BOOLEAN NOT NULL DEFAULT false,
    source      VARCHAR(100),           -- provenance
    created_at  TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_case_esas UNIQUE (case_id, esas_no, stage)
);
```

**`cases.esas_no` KALIR** — ama artık türetilmiş değer: `is_current = true` satırının
kopyası. Tek yazma yolu, tek türetme kuralı, **ikinci doğruluk kaynağı yok**. Sıcak yollar
(liste, kart) tek kolondan okumaya devam eder; arama `esas_no` index'li tabloya vurur.

> **DİKKAT — FAZ D 6.1 bağı:** `uq_case_esas` ve tablonun index'leri `("index", …)`
> op türüyle yazılmalı, `("table", …)` op'unun içine GÖMÜLMEMELİ. `table` op'larının
> taşıdığı kısıt/index SQL'leri bugün **hiç çalışmıyor** (§FAZ D 6.1). Bu tablo o
> tuzağa düşmemeli.

### 1.4 Yeniden adlandırma

`Dava Türü Alt Kırılımı` → **`Uzmanlık Alanı`** (S15). **Bu aktarımla birlikte** yapılacak:
export sütun sabitliği taahhüdü verildikten sonra ad değiştirmek taahhüt ihlali olur.
Aynı gerekçeyle §1.1'deki beş tıbbi alanın adları da bu turda kesinleşir.

---

## 2. Davranış değişiklikleri (kolon değil, kod)

| # | Kural | Dokunduğu yer |
| --- | --- | --- |
| **D1** | **Sigortalı** taraf kaydı olur, `party_type = THIRD`, rol adı `Sigortalı`. **Karşı taraf DEĞİL.** Çıkar çatışması kontrolünden **hariç**, aramaya **dahil** | `party_check.py` (çıkar çatışması kuralı) |
| **D2** | Ana Tür ∈ {ARABULUCULUK, SAVCILIK, DANIŞMANLIK, TAHKİM} ise **esas beklenmez** — "eksik esas" işaretlenmez | `required_fields.py` + `case_manager._missing_required_clause` |
| **D8** | Aktarım kaynaklı kayıtlar eksik-alan filtresinde **ayrı kovada** (K1 kararı; UYAP Avukatı 8.409 kayıtta boş gelecek). Kaynak: `case_history.source = HUKDOK_TESLIM_*` | Aynı yer — D2 ile tek işte |
| **D3** | `Vekalet Ücreti Alacağı` → hizmet türü **İCRA** (Dava değil). 83 satırın tamamında Ana Tür=İCRA, mahkeme=icra müdürlüğü | `service_type` eşlemesi |
| **D4** | `maddi = Dava Değeri − Manevi`; sonuç **negatifse hesaplama yapılmaz, maddi NULL kalır** (98 satır). `Manevi = Dava Değeri` olan 142 satırda maddi = 0 doğrudur | Aktarım scripti |
| **D5** | Yer tutucu tarihler **NULL**: `01.01.1900` (217), metin biçimli (40), gelecek tarihler (4: `01.01.2030`×3, `01.01.2027`) | Aktarım scripti |
| **D6** | Mükerrer gruplar **otomatik BİRLEŞTİRİLMEZ**. Sigortalı farklı → ayrı föy (160 grup); hizmet türü farklı → ayrı föy (14 grup) | Aktarım scripti |
| **D7** | Kanonik dava konusu yazımına kapanma + kayıt anında `trim` / iç boşluk sadeleştirme | Referans listesi yazma yolu |

> **D1 uyarısı:** çıkar çatışması motoru G017'de (A.4) yeni optimize edildi. Sigortalı
> istisnası oraya eklenirken 1.324.050 isim çifti üzerinde kanıtlanmış davranış
> eşdeğerliğinin bozulmadığı yeniden ölçülmeli.

---

## 3. Karşı tarafa borçlu olduğumuz çıktılar

Aktarım scriptinin **kabul kriteridir** — üretmiyorsa iş bitmemiştir.

1. **98 satırlık liste** — Manevi > Dava Değeri olan, maddi'si NULL bırakılan kayıtlar
2. **33 + 24 grup** — gerçek mükerrer şüphesi (hizmet+sigortalı+karşı taraf+Hasar No aynı)
   ve Hasar No'su iki tarafta da boş olanlar. Kendi mükerrer föy prosedürleriyle inceleyecekler
3. **SistemNo → Kayıt No / Takip No** — kayıt kayıt eşleme (9 no'lu talepleri)
4. **TKU grup raporu** — çok üyeli TKU gruplarının `case_relations`'ta nasıl karşılandığı

---

## 4. Kararlar (12.08.2026, kullanıcı yetkisiyle verildi)

### K1 — UYAP Avukatı: **ön-doldurulmayacak**, filtre bağlam-duyarlı yapılacak

**Karşı tarafın önerisi ("Sorumlu Avukatlar'ın ilk ismiyle ön-doldurup 'teyit bekliyor'
işaretlemek mümkün mü?") REDDEDİLDİ.**

**Gerekçe:** UYAP avukatı ile büronun sorumlu avukatı **aynı kişi değildir**. UYAP'ta
dosyaya kayıtlı vekil, büro içi iş dağılımından bağımsızdır — dosya devri, vekaletname
kapsamı ve UYAP yetkilendirmesi ayrı ayrı değişir. İlk sorumlu avukat ismiyle doldurmak
8.409 kayda **uydurma veri** yazar; provenance imzası bunu "uydurma" olmaktan çıkarmaz,
yalnız izlenebilir kılar. Yanlış veri, boş veriden pahalıdır: birisi ona güvenip UYAP
işlemi yapar.

**Çözüm veri tarafında değil filtre tarafında.** UYAP Avukatı **boş kalır**; eksik-alan
filtresi aktarım kaynaklı kayıtları ayrı kovada tutar (`case_history.source =
HUKDOK_TESLIM_*` üzerinden). Böylece:

- filtre "her zaman ateşleyen" hâle gelmez, kullanılabilir kalır;
- 8.409 dosyanın tamamlanması gereken alanı **görünür** olur, gizlenmez;
- alan elle doldurulunca kayıt normal kovaya geçer.

> **Bu, D2 ile birebir aynı desendir** (S9: arabuluculuk/savcılık/danışmanlık/tahkim
> föylerinde esas beklenmez). Zorunluluk mutlak değil **bağlamsaldır**; kural
> `required_fields.py`'de zaten kapılı zorunlu alan deseni mevcut.

Karşı tarafa dönülecek cevap: *ön-doldurma yapmıyoruz, alan boş gelecek; eksik filtresinde
ayrı kovada duracak, dolduruldukça normale geçecek.*

### K2 — Kanonik dava konusu: 7.692 satırlık yazım

`Tazminat (Tıbbi Kötü Uygulama Sigorta Poliçesinden Kaynaklanan)`

**Gerekçe:** 427:1 çoğunluk; "Sigorta" kelimesi poliçe türünü belirtiyor (anlam taşıyor);
18 satırlık varyant **bizim sistemimizde** açılmış — sapma bizde. Dış yazışmalarda ve
karşı tarafın raporlarında bu yazım geçiyor.

**Asıl düzeltme veri değil kural** (D7): yazım normalizasyonu kayıt anında uygulanmazsa
aynı sapma tekrar doğar — bugünkü ayrışmanın sebebi sondaki boşluk.

### K3 — Kurum kategorisi: `K1` ileriye dönük, raporlama kimlikten ayrılır

Üç parça:

1. **`K1` kodu açılır**, yalnız bundan sonra açılan Kurum kayıtlarında kullanılır.
2. **Mevcut 1.658 X1 kaydı ve 73 Kurum föyü DOKUNULMAZ.** Ofis numaraları SharePoint
   klasör adlarına ve gönderilmiş dış yazışmalara bağlı; geriye dönük retag DB'yi
   dosya sisteminden ve dış dünyadan ayrıştırır. → Ana plan **0.5 = seçenek (a)**.
3. **Kategori raporlaması `clients.category` alanına taşınır.** Alan zaten var ve
   aktarımla 8.409 satırın tamamında dolu geliyor (Müvekkil Tipi eşlemesi).

**Gerekçe:** karşı tarafın endişesi ("diğer içinde kaybolursa müvekkil tipi raporlaması
bozulur") haklı, ama çözümü kod değiştirmek değil. **Ofis numarası bir kimliktir;**
içine gömülü semantiği sonradan sorgu boyutu olarak kullanmak yanlış katman. Kimlik
değişmez, sorgu boyutu değişebilir olmalı. Bu çözümle 1.658 X1 kaydı da doğru raporlanır —
kodları X1 kalsa bile.

> Bu üç karar `docs/kararlar/` altına ADR olarak da yazılacak (0.5'in ADR borcu K3 ile kapanır).

---

## 5. Açık kalanlar

| Konu | Durum |
| --- | --- |
| **TC Kimlik No** | Pakette hiç yok, toplu kaynak da yok. Kişi eşleştirme + çıkar çatışması için iki tarafın da ihtiyacı. UYAP'tan dosya bazında çekilebilir → **aktarım sonrası ayrı çalışma** |
| **Poliçe kayıtları** | Sigorta şirketlerinden gelen yıllık listeler var (AXA/Anadolu/AK/Quick/Sompo/Nippon, 20+ dosya, 2014-2026). **Poliçe modülünün alan yapısını göndermemiz gerekiyor** — sonra eşleyip ayrı teslim verecekler |
| **Belgeler / SharePoint eşleşmesi** | Bu aktarımın kapsamı dışında; klasör–dosya eşleme tablosunu hazır olduğunda verecekler |
| **Kapsam eki eksik 11 satır** | Yalnız `id-13537` kanıtlı → `(Malpraktis Kaynaklı)`. Kalan 10 satır belge incelemesi gerektiriyor — **eksiz aktarılacak**, sonraki turda işlenecek |
| **MüvekkilNo** | Sisteme aktarılmayacak (mutabık). 1.515 numaradan 61'i birden çok isme bağlı. Temizlik bitince ayrı turda temiz eşleme tablosu gelecek. O zamana kadar cari kartlar **isim + vergi/TC** üzerinden kurulur |
| **Uzmanlık alanı ad eşleme tablosu** | Ayrı turda onaya gelecek |
| **Göz hastalıkları dilimi** | Tarih taahhüdü yok; partiler hâlinde |

---

## 6. Sıra

```
FAZ B (emniyet ağı)
   └─> FAZ D  6.1 migrasyon mekanizması + 6.2 index
         └─> ŞEMA: 11 kolon + case_esas_numbers + Uzmanlık Alanı rename
               └─> FAZ F  yazma yolu + 7 davranış kuralı + 4 rapor
```

`case_esas_numbers` ve yeni kolonlar **D'nin arkasında** durur: `("table", …)` op'unun
kısıt/index SQL'i çalışmadığı sürece yeni tablo da korumasız doğar.

**FAZ E tamamen koşacak** (kullanıcı kararı, 2026-08-12) ve D ile **aynı deploy'a** biner —
bkz. ana plan §7 + §12 madde envanteri. Bu belgede FAZ E'yi *zorunlu kılan* bir madde yok;
ama F, E'nin iki maddesinin girdisini büyütüyor:

- **E5 `find_matching_case`** — tüm aktif davaları tarafları ile belleğe çekiyor
  (tepe 244 MB, `/process` sıcak yolu). F, `case_parties`'i büyütüyor: Sigortalı 4.294
  satırda taraf kaydına dönüşüyor (D1) ve çoklu Karşı Taraf 3.240 satırda ayrı satırlara
  açılıyor. Bugünkü 50.032 taraf ~%20 artıyor → E5 **F'den önce** kapanmalı.
- **E6 `missing_required`** — D8 ile birlikte düşünülmeli: aktarım kaynaklı kayıtların
  ayrı kovada tutulması bu sorgunun içindedir.
