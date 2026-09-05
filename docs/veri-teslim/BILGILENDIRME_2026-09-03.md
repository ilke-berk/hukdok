# HUKDOK Veri Teslim Hattı — Veri Ekibi Bilgilendirmesi

**Tarih:** 03.09.2026 (ilk sürüm) · **Gönderen:** HukuDok ekibi (Hanyaloğlu Acar + LexisBio) ·
**Muhatap:** MicroKolayOfis master'ını hazırlayan veri ekibi · **Sürüm:** 1.2 (05.09.2026)

> Bu belge yapılandırılmış yazıldı: tablolar, birebir yazımlar ve sondaki makine-okur özet
> (§9), kendi yapay zekâ asistanınıza "teslim öncesi kontrol" ve "cevap paketi yorumlama"
> görevi olarak doğrudan verilebilir. Buradaki her kural çalışan sistemden okunarak yazıldı;
> tahmin ya da niyet değil, bugün geçerli davranıştır.

**Değişiklik geçmişi**

| Sürüm | Tarih | Ne değişti |
| --- | --- | --- |
| 1.0 | 03.09.2026 | İlk sürüm |
| 1.1 | 04.09.2026 | Format Değişiklik Bildirimi REV-2 (DB-2026-001…010) ve aynı gün verdiğimiz cevap işlendi: `Müvekkil Tipi` + `Hizmet Türü` artık **okunuyor** (§3.2; "bekleyen alan" değil); okunan başlık listesi sistemden yeniden sayıldı (42 alan / 54 kabul edilen yazım); kapalı listelerimizin tam envanteri (§3.8 — `İddia Edilen Kusur` 9 değerle doldu); `Karar_Asamalari`'nda `Önceki` etiketi (§3.5); DB-2026 kalemlerinin bizdeki karşılığı ilgili bölümlere tarihli şerh olarak girdi; §5 tablosu, §6 örnek bildirim numarası, §9 özet |
| 1.2 | 05.09.2026 | 04.09 paketinin **54 sütununun tamamı** okunur hâle geldi: `Dosya - Föy Bilgileri`, `Para Birimi TL`, `MüvekkilNo`, `Eski Dosya No`, `İstinaf Mahkeme Başvuru Tar.` artık **okunuyor** (§3.2; okunan liste 47 alan / 66 yazım); `Yerel Mahkeme Tebliğ Tarihi` ve `Yerel Mahkeme Kararı Açıklaması` `Karar_Asamalari`'ndan karta da yansıyor; `Müvekkil Tipi` / `Hizmet Türü` / `Durum` föy düzeyinde de saklanır — kardeş föy çelişkisinde kart alanı boş kalır ama föy değeri kaybolmaz (§3.2 şerhi). Dosyanızda değişiklik gerekmez |

---

## 0. Beş cümlede özet

1. Teslim paketi artık WhatsApp/e-posta ile değil, size paylaşılan SharePoint klasörüne
   (`03_VERI_TESLIM/gelen`) bırakılır; WhatsApp yalnız "bıraktım" haberi için kalır.
2. Sistem klasörü her gece 04:00'te tarar, paketi önce hiçbir şey yazmadan prova eder, ölçüm
   eşiklerin içindeyse aynı gece uygular; değilse HukuDok yöneticisinin onayına düşer.
3. Ertesi sabah `03_VERI_TESLIM/cevap/<paket adı>/` klasöründe cevap paketi bulursunuz:
   hangi satır hangi karta eşleşti, hangileri eşleşmedi, hangi değerler tanınmadı.
4. Gelen dosyanın biçimini bu belge belirler. Sütun adı, sayfa adı, kimlik alanı ya da değer
   havuzu değişikliği **teslimden önce yazılı bildirilir** (§6 şablonu); bildirilmemiş
   değişiklik ya paketi reddettirir ya da güncellemenin sessizce kaybolmasına yol açar.
5. Sistem yeni dava kartı **açmaz** ve tahmin **yazmaz**: bizde karşılığı olmayan satır ve
   değerler raporda kalır, veriye dokunulmaz.

---

## 1. Yeni sistem nasıl çalışıyor

```
siz ──xlsx──▶ 03_VERI_TESLIM/gelen/
                    │  her gece 04:00 (Türkiye saati)
                    ▼
            (1) alındı        dosya indirilir, içerik parmak izi alınır, deftere yazılır
            (2) doğrulandı    sayfa/başlık kontrolü + "önceki teslim" zincir kontrolü
            (3) kuru koşu     hiçbir şey yazmadan prova: eşleşme, değişiklik, hata sayımı
            (4) kapı          ölçümler eşik içindeyse → otomatik uygulama
                              eşik dışıysa → "inceleme bekliyor" (HukuDok yöneticisi karar verir)
            (5) uygulandı     kartlar güncellenir (idempotent: aynı paket ikinci kez sıfır değişiklik)
            (6) cevap         raporlar cevap/<paket adı>/ altına yüklenir
```

**Kapı eşikleri (bugünkü değerler):**

| Kural | Eşik | Aşılırsa |
| --- | --- | --- |
| Hatalı satır oranı | en çok %2 | inceleme bekler |
| Eşleşmeyen satır oranı (bizde kart bulunamayan) | en çok %5 | inceleme bekler |
| Toplam alan değişikliği | en çok 10.000 hücre | inceleme bekler |
| "Önceki teslim" zinciri | önceki paket bizde uygulanmış olmalı | inceleme bekler |
| Belge sayımı | koşu öncesi/sonrası birebir | değilse koşu kendini geri alır |
| İlk teslim | daima | insan onayı |

"İnceleme bekliyor" bir hata değildir; büyük ya da olağandışı paketlerde beklenen yoldur.
Bu durumda cevap klasörü açılmaz, sonucu size HukuDok tarafı iletir.

**Ne yapmaz:** yeni kart açmaz; bizde olmayan kapalı liste değerini listeye eklemez; boş
hücreyi "sil" olarak yorumlamaz (§3.4); aynı gece birden çok paketten yalnız ilkini uygular.

---

## 2. Nasıl göndereceksiniz

| Konu | Kural |
| --- | --- |
| Klasör | `03_VERI_TESLIM/gelen/` (size "düzenleyebilir" olarak paylaşıldı) |
| Dosya adı | `HUKDOK_TESLIM_` ile başlar, `.xlsx` ile biter. Öneri: `HUKDOK_TESLIM_PAKETI_YYYY-AA-GG.xlsx`. Kalıba uymayan dosya **sessizce yok sayılır** |
| Biçim | Yalnız `.xlsx`. `.xlsm`, `.xls`, `.csv` kabul edilmez |
| Boyut | 50 MB'a kadar (bugünkü paket 4,2 MB) |
| Sıklık | Günde en çok bir paket. Aynı gece iki paket bırakılırsa ikincisi insan onayına düşer |
| Tekrar | Aynı dosya iki kez bırakılırsa ikincisi "yinelenen" sayılır, işlenmez. İçerik değişip ad aynı kalırsa **yeni teslim** sayılır |
| Haber | Bıraktıktan sonra WhatsApp'tan kısa bir "bırakıldı: <dosya adı>" mesajı; zorunlu değil, faydalı |
| Eski dosyalar | Silmenize gerek yok; sistem içerik parmak iziyle tanır |

---

## 3. Dosya biçimi — sistemin okuduğu ve beklediği

### 3.1 Sayfalar

| Sayfa adı (birebir) | Zorunlu | Sistem ne yapar |
| --- | --- | --- |
| `Sheet` | **Evet** | Ana veri. Föy başına bir satır. `SistemNo` ve `Dosya No` sütunları yoksa paket **reddedilir** |
| `DEGISIKLIK_OZETI` | Hayır, ama **her pakete koyun** | "Önceki teslim" satırından zincir kontrolü (§3.3). Sayfa yoksa zincir denetlenmez |
| `Karar_Asamalari` | Hayır | Föy başına yargı aşamaları (§3.5). Yoksa aşama yazılmaz |
| `Düzeltme_Logu` | Hayır | Değişiklik gerekçeleri tarihçeye işlenir; `(boş)` talimatı buradan okunur (§3.4) |
| `DEGER_HAVUZLARI` | Hayır | Kapalı liste değerleriniz bizimkilerle karşılaştırılır, fark raporlanır (§4) |
| `Silinen_Föyler`, `Kapsam_Dışı` | Hayır | Föy "kapsam dışı" işaretlenir, silinmez (§3.6) |
| `SUTUN_SOZLUGU`, `SINIFLANDIRMA_MODELI`, `HUKDOK_TALEPLERI` | Hayır | Okunmaz; insan için. Kalabilir |

Sayfa adları yukarıdaki yazımla **birebir** olmalıdır. Yalnız kapsam sayfalarında aksan ve
alt çizgi farkı tolere edilir. Tanınmayan adlı sayfa **sessizce atlanır**; bu yüzden
`Karar_Asamalari` yerine `Karar Asamalari` yazılırsa hata görmezsiniz ama aşama bilgisi
işlenmez.

### 3.2 `Sheet` — ana sayfa

**Sütun adı esastır, sütun sırası değil.** Sistem sütunları ada göre bulur; sıra değişse
çalışır, ad değişse **o alan "bu teslimde yok" sayılır** ve hata vermez. Bu, en tehlikeli
sessiz kayıp yoludur: adı değişen sütundaki güncellemeler bize hiç ulaşmaz (§5).

Ad karşılaştırması büyük/küçük harf, aksan ve boşluk farkını yutar: `Arşiv Tarihi`,
`ARSIV TARIHI`, `arsiv_tarihi` aynı sütundur. Kelime değişikliği yutulmaz:
`Arşiv Tarihi` → `Arşive Kaldırma Tarihi` farklı sütundur.

**Sistemin bugün okuduğu başlıklar** — **47 alan, 66 kabul edilen yazım** (05.09.2026'da
çalışan sistemden sayıldı; bazı alanlar için birden çok yazım tanınır, `/` ile ayrılanlar
aynı alandır):

| Alan grubu | Kabul edilen başlıklar |
| --- | --- |
| Kimlik (zorunlu) | `SistemNo` / `Sistem No` · `Dosya No` / `DosyaNo` / `Klasör No.2` |
| Kimlik (isteğe bağlı) | `Klasör No` / `TKU` / `TKU No` / `TKU No.` · `Hasar No` / `Hasar Numarası` · `Hukuk No` · `Arabuluculuk Numarası` · `Dosya - Föy Bilgileri` / `Föy Id` / `MKO Id` (föy kimliği, föyde saklanır) · `MüvekkilNo` / `Müvekkil No` (föyde saklanır, cari kart kurmaz) |
| Sınıflandırma | `Ana Tür` · `Durum` · `Dava Konusu` · `Dava Türü Alt Kırılımı` / `Uzmanlık Alanı` · `Buro Özel Türü` · `Son Durum` |
| Künye | `Yerel Mahkeme` · `Esas` · `Karar No` · `Karar Tarihi` · `İstinaf Mahkemesi Başvuran Taraf` · `Eski Dosya No` / `Eski Esas No` (esas tarihçesine "önceki" olarak) · `İstinaf Mahkeme Başvuru Tar.` / `İstinaf Mahkeme Başvuru Tarihi` / `İstinaf Başvuru Tarihi` |
| Tarihler | `Dava Tarihi` · `İş Kabul Tarihi` · `Arşiv Tarihi` · `Arabuluculuk Karar Tarihi` |
| Para | `Dava Değeri TL` / `Dava Değeri` · `Manevi Dava Değeri TL` / `Manevi Dava Değeri` · `Islah Tutarı` / `İslah Tutarı` · `Hükmedilen Maddi` · `Hükmedilen Manevi` · `Hükmedilen Toplam` · `Para Birimi TL` / `Para Birimi` |
| Taraflar | `Müvekkil` · `Karşı Taraf` · `Sigortalı` · `Davalı İdare` · `Taraf Sıfatı` · `Sorumlu Avukatlar` / `Sorumlu Avukat` |
| Klinik kodlama | `Tıbbi Süreç` · `Tıbbi Olay` · `İddia Edilen Kusur` · `Hastada Oluşan Zarar` · `Uygulanan Yöntem` |
| Belgeleme olayı | `Olay Türü` · `Hükümdeki Rol` |
| Föy düzeyi kapalı listeler (yeni, 04.09) | `Müvekkil Tipi` · `Hizmet Türü` |

**04.09.2026 bildiriminin bu listeye etkisi (DB-2026 şerhleri):**

- **DB-2026-002 — `Müvekkil Tipi` + `Hizmet Türü`:** 1.0'daki "bekleyen alan" durumu
  kapandı; iki sütun artık **okunur** ve föy düzeyinde kartın iki ayrı alanına yazılır.
  İkisi de kapalı listedir (değerler §3.8); tek değer beklenir, ` ; ` ile çok değerli hücre
  bu iki alanda **yazılmaz** ve satır raporuna düşer. Aynı davanın föyleri farklı müvekkil
  tipi söylerse bu **beklenen** bir kardeş föy çelişkisidir: alan karta yazılmaz, çelişki
  raporunda görünür (§4) — hata saymayın.
- **DB-2026-003 — artık gelmeyecek sütunlar:** on dört sütunun bir sonraki paketten
  itibaren gelmeyeceğini (on birinin kaynaktan silindiğini) bildirdiniz; bizde iş
  çıkarmadı. Kural §3.4'tekidir: gelmeyen sütun = "bu teslimde bu bilgi yok", bizdeki
  değer korunur, hata üretmez. Hangi başlıkların kalktığının kaynağı bildiriminizin kendi
  listesidir (`Kaldirilan_Sutunlar` sayfası); bu belge o listeyi tekrar etmez. Not:
  `Arabuluculuk Numarası` bizde **kimlik alanı değildir** — eşleşme köprüsü yalnız
  `Dosya No`dur; bu sütunun gelmemesi eşleşmeyi etkilemez.
- **DB-2026-006 — `Olay Türü` / `Hükümdeki Rol`:** bu iki sütun sizde henüz
  üretilmiyor (04.09). Alanlar bizde açık; sütun gelmeyince ya da boş gelince alan boş
  kalır, bu meşru bir durumdur ("karar okunmadı"), hata değildir.
- **DB-2026-007 — `Dava Türü Alt Kırılımı` → `Uzmanlık Alanı`:** iki başlık da aynı
  alana bağlıdır (yukarıdaki tabloda `/` ile); adı değiştirmeniz bizde iş çıkarmadı,
  ikisinden hangisi gelirse gelsin okunur.
- **05.09.2026 (sürüm 1.2) — 54 sütunun tamamı:** 04.09 paketinin her sütunu artık bir
  yere düşer. `Dosya - Föy Bilgileri` ve `MüvekkilNo` föy düzeyinde saklanır (kimlik;
  `MüvekkilNo` cari kart KURMAZ, 12.08 mutabakatının o kısmı geçerli). `Para Birimi TL`
  ve `Dava Değeri TL` ham hâliyle karta yazılır (maddi tazminat türetmesi sürer: dava
  değeri − manevi). `Eski Dosya No` bir esas numarasıdır ve `Karar_Asamalari`'nın
  `Önceki` satırlarıyla aynı tarihçeye düşer (kartın güncel esası değişmez; aynı numara
  iki kaynaktan gelirse tek satır). `İstinaf Mahkeme Başvuru Tar.` `Karar_Asamalari`'nda
  karşılığı olmayan tek zincir alanıdır, `Sheet`'ten doğrudan karta yazılır.
  **Föy düzeyi kopya:** `Müvekkil Tipi`, `Hizmet Türü`, `Durum` kart alanına ek olarak
  föyün kendisine de yazılır; aynı kartın föyleri farklı değer söylediğinde (04.09
  paketinde hizmet türü 973, müvekkil tipi 891, durum 181 kart) kart alanı §4 gereği boş
  kalır ama her föyün değeri kartta "Föyler" panelinde görünür — kayıp yok, bu satırlar
  çelişki raporunda yine listelenir.

**Okunmayan sütunlar** (18.08 paketindeki 68 sütunun kalan 24'ü; 04.09 paketindeki 54
sütunun **hepsi okunur**. Paketten çıkarmanız gerekmez, olduğu gibi kalabilir —
DB-2026-003 ile kaldırdıklarınız için de aynı kural):

| Sütunlar | Neden okunmuyor |
| --- | --- |
| `Yerel Mahkeme Karar Tarihi`, `Yerel Mahkeme Tebliğ Tarihi`, `Yerel Mahkeme Karar Durumu`, `Yerel Mahkeme Kararı Açıklaması`, `İstinaf Mahkemesi`, `İstinaf Mahkeme Esas`, `İstinaf Mahkeme Karar No`, `İstinaf Mahkeme Karar Tar.`, `İstinaf Karar Durumu`, `İstinaf Karar Açıklamalar`, `Temyiz Mahkemesi`, `Temyiz_Esas_No`, `Temyiz Karar Tarihi`, `Yargıtay Onama Durumu`, `Karar Düzeltme Kararı Durumu` (15) | **Yargı zinciri `Karar_Asamalari` sayfasından okunur** ve oradan karta yansır (05.09'dan beri yerel tebliğ tarihi ve karar açıklaması dahil). `Sheet` yalnız güncel aşamayı yatay taşıyor; bizde karar künyesinin tek yazma yolu aşama tarihçesidir, aynı bilgiyi iki kaynaktan yazmak çelişki üretirdi. Bu sütunları `Sheet`'te tutmaya devam edin; kardeş föy çelişki raporu bunlardan yararlanır |
| `Bilirkişi Rapor Sonuç`, `Poliçe Başlangıç Tarihi`, `Ek Alt Kırılım 1`–`4`, `Arabuluculuk Merkezi`, `Soruşturma İtiraz Mahkemesi` (8) | **Sizin sözlüğünüzün "ölü sütun" listesi** (24.08 veri sözlüğü §10: doluluk 0, "modelinize taşımayın"); 04.09 paketinde zaten yok |
| `Ek Alt Kırılım` (1) | Sizin uyarınız: dosya açılış etiketi, karardan okunmamış, kanıt değil; 04.09 paketinde zaten yok |

Yeni bir sütun eklediğinizde de aynı kural geçerlidir: **tanınmayan başlık sessizce
atlanır**, paket hata vermeden işlenir, ama o sütundaki bilgi bize ulaşmaz. Sütunun
işlenmesi için önce §6 bildirimi, sonra bizim tarafta alan + eşleme açılması gerekir.
Bildirimle gönderdiğiniz ek sayfalar (`Kaldirilan_Sutunlar`, `S37_Kanonik`,
`Yazim_Standardi`) da bu sınıftadır: okunmaz, paketi bozmaz, arşiv olarak kalabilir.

**Hücre değerleri:**

| Tür | Beklenen | Notlar |
| --- | --- | --- |
| Tarih | Excel tarih hücresi ya da `GG.AA.YYYY` metni | `01.01.1900`, 1900 ve öncesi, gelecek tarihler **yer tutucu** sayılır ve boş yazılır (uyarı düşer, satır düşmez). DB-2026-009 ile teyit: Excel tarih hücresi tam istediğimiz biçim, değişiklik yok |
| Sayı | Excel sayı hücresi ya da Türkçe yazım (`12.500,00`) | `NULL ≠ 0` kuralı korunur: boş = bilinmiyor, `0` = hükmedilmedi. DB-2026-009 ile teyit: Excel sayı hücresi tam istediğimiz biçim |
| Ad alanları (`Müvekkil`, `Karşı Taraf`, `Sigortalı`, `Davalı İdare`, `Sorumlu Avukatlar`) | Serbest metin | DB-2026-008 (İlk Harf Büyük yazımı) bizde **değişiklik sayılmaz**: taraf ve müvekkil karşılaştırması büyük/küçük harf, aksan ve I/ı-İ/i farkından bağımsız anahtarla yapılır (`AK SİGORTA A.Ş.` = `Ak Sigorta A.Ş.` = `Ak Sigorta Anonim Şirketi`); kartta zaten olan taraf yeniden yazılmaz, yalnız kartta hiç olmayan ad eklenir. Avukat adı bizim kayıtlı yazımımızla yazılır. Ad alanları **eşleşme anahtarı değildir** (köprü `Dosya No`); müvekkil adı yalnız aynı `Dosya No`ya birden çok kart düştüğünde üçüncü ayırt edici olarak kullanılır (§4) |
| `Müvekkil Tipi`, `Hizmet Türü` | Tek değer, bizdeki kapalı listeden (§3.8) | ` ; ` ile çok değer **yazılmaz**, rapora düşer; tanınmayan değer yazılmaz. Boş = bilinmiyor (bildiriminiz "tamamı dolu" diyor — ilk cevap paketinde `yazılmadı` satırı beklemiyoruz) |
| Yer tutucu metin | `-`, `--`, `—`, `?`, `YOK`, `BELİRSİZ`, `BOŞ`, `N/A`, `NA` | Hepsi "boş" sayılır |
| Çok değerli hücre | ` ; ` (noktalı virgül) ile ayrılır | Satır sonu da ayraç sayılır. Virgül ayraç **değildir** |
| Kapalı liste değeri | Bizde de olan yazım | Aksan/büyük-küçük farkı yutulur; kelime farkı yutulmaz. Tanınmayan değer **yazılmaz**, satır raporunda görünür |
| `Olay Türü` çok değer | Yalnız `Tıbbi Olay ; Belgeleme Olayı` ikilisi → "Tıbbi + Belgeleme" | Başka kombinasyon yazılmaz |
| `Hükümdeki Rol` | Tek değer | Çok değer yazılmaz, rapora düşer |
| `Sorumlu Avukatlar` | `;` ile çoklu | Yalnız ekleme yapılır, mevcut avukat silinmez |

### 3.3 `DEGISIKLIK_OZETI` — "Önceki teslim" satırı

Sistem sayfanın ilk satırlarında **"Önceki teslim"** etiketli hücreyi arar; yanındaki (ya da
aynı hücredeki iki nokta sonrası) değeri bir önceki paketin **dosya adı** olarak okur.
`·` işaretinden sonrası dikkate alınmaz. Bugünkü paketinizdeki yazım tam olarak uygundur:

```
Önceki teslim | HUKDOK_TESLIM_PAKETI_2026-08-10.xlsx · 10.08.2026
```

Ad, bıraktığınız dosyanın adıyla **birebir** olmalı. Yanlış ad ya da atlanmış paket zinciri
koparır; paket insan incelemesine düşer. İlk teslimde `—` ya da `yok` yazın.

### 3.4 Partili teslim ve boşaltma

- Ana sayfada **olmayan sütun** ya da **boş hücre** = "bu teslimde bu bilgi yok". Bizdeki
  değer korunur. Bu yüzden yalnız değişen föyleri içeren küçük paketler gönderebilirsiniz;
  68 sütunu taşımak şart değildir (yalnız `SistemNo` ve `Dosya No` şarttır).
- **Bir alanı bilerek silmek** için `Düzeltme_Logu`'nda ilgili satırın `Yeni Değer` hücresine
  `(boş)` (parantezli) yazın ve `Gerekçe`'yi **`[Sütun Adı]`** önekiyle başlatın:
  `[Hükmedilen Manevi] belge yeniden okundu, tutar yok`. Sistem üç şartı birlikte arar: log
  `(boş)` diyor + ana sayfada o hücre boş + bizde dolu. Öneksiz `(boş)` satırı uygulanamaz.
- Bugünkü paketinizdeki 229 `(boş)` satırının hiçbiri sütun adı taşımıyor; bunlar
  uygulanmadı. Sonraki pakette öneki eklerseniz işlenir. Alternatif olarak
  `Düzeltme_Logu`'na ayrı bir `Sütun` başlığı açabilirsiniz; ayrı başlık gelirse önek yerine
  o okunur.
- Boşaltılamayan alanlar: `Karar No`, `Karar Tarihi` (aşama sayfasından beslenir), `Yerel
  Mahkeme`, `Dava Türü Alt Kırılımı` (yazım bizde). Bunlar için `(boş)` raporda
  "boşaltılmadı" olarak görünür.

### 3.5 `Karar_Asamalari`

Beklenen başlıklar: `SistemNo`, `AsamaNo` / `Aşama No`, `Aşama`, `Mahkeme`, `Esas No`,
`Karar No`, `Karar Tarihi`, `Karar Durumu`, `Tebliğ Tarihi`, `Başvuran Taraf`, `Güven`,
`Açıklama`. Bugünkü 21 sütunlu sayfanız uyumludur; fazladan sütun sorun değildir.

**`Aşama` sütununun değer havuzu:**

| Değer | Sistem ne yapar |
| --- | --- |
| `Yerel`, `İstinaf`, `Temyiz`, `Karar Düzeltme` | Karar aşaması: kartın aşama tarihçesine künye olarak yazılır |
| `Önceki` | **Kabul edilir ama karar aşaması değildir** (DB-2026-004, 04.09): satırın `Esas No`su kartın **esas numarası tarihçesine** önceki esas olarak yazılır (görevsizlik/yenileme öncesi numara); kartın güncel esası değişmez, "tanınmayan aşama" raporu üretilmez. Bu satırları **filtrelemeyin, gönderin** — `Sheet`'teki `Eski Dosya No` tek slottur, `Önceki` satırları birden çok eski esası taşıyabildiği için bizim için daha zengindir (04.09 ricamız: filtrelenmiş 664 satır) |
| Başka değer | Satır sessizce atlanır (aşama yazılmaz) |

`Karar Durumu` bizde aşama başına kapalı havuzdur (§3.8). Havuz dışı bir değer satırı
**düşürmez**: durum boş kalır, gelen değer aşamanın açıklama alanına taşınır ve cevap
raporuna yazılır (DB-2026-005 cevabı). Havuzumuzda **lehe/aleyhe ekseni yoktur**, usul
sonucu tutulur — "Kesin Lehe", "Karar Aleyhe" gibi yön taşıyan yazımların karşılığı
olmayacaktır; yön bilgisini ayrı bir sütunda tutuyorsanız §6 ile bildirin.

Aynı davaya bağlı iki föy aynı aşama için farklı künye söylerse o aşama yazılmaz, çelişki
raporuna düşer.

### 3.6 `Silinen_Föyler` ve `Kapsam_Dışı`

Beklenen: `SistemNo` + gerekçe sütunu (`Silinme Gerekçesi` / `Kapsam Dışı Gerekçesi` /
`Gerekçe`) + `Tarih`. Föy bizde silinmez; kart ve belgeler yerinde kalır, föy "kapsam dışı"
işaretlenir, kart bilgilerini beslemekten çıkar. Föy sonraki pakette ana sayfaya dönerse
işaret kaldırılır. Bizde olmayan SistemNo raporda "atlandı" olur.

### 3.7 `DEGER_HAVUZLARI`

Bugünkü düzen uygundur: 3. satırda `Havuz / Sütun` ve `Değer` başlıkları, havuz başına bir
satır bir değer. Karşılaştırılan havuzlar: `İddia Edilen Kusur`, `Yerel Mahkeme Karar
Durumu`, `İstinaf Karar Durumu`, `Yargıtay Onama Durumu` (ya da `Temyiz Onama Durumu`),
`Olay Türü`, `Hükümdeki Rol`. Diğer havuzlar atlanır — `Müvekkil Tipi` ve `Hizmet Türü`
havuzları da (04.09): bu ikisi için fark raporu üretilmez; tanınmayan bir değer `Sheet`
işlenirken satır raporunda görünür (§4).

### 3.8 Kapalı listelerimiz — bizde geçerli değer havuzları (04.09.2026)

Aşağıdaki listeler çalışan sistemin referans listelerinden birebir alınmıştır. Listeye
ekleme yalnız §6 bildirimi + bizim tarafta insan kararıyla olur; paketle gelen yeni değer
listeye **eklenmez**. Listenin alana nasıl uygulandığı alandan alana değişir, "Uygulama"
sütununu okuyun (aksan/büyük-küçük farkı her yerde yutulur, kelime farkı yutulmaz — §3.2):

| Alan (sütun) | Değer sayısı | Değerler (bizim yazımımız) | Uygulama | Kaynak |
| --- | --- | --- | --- | --- |
| `İddia Edilen Kusur` | 9 | Uygulama Hatası · Komplikasyon Yönetimi · Aydınlatma · Tanı Hatası · Organizasyon Hatası · Takip Eksikliği · Endikasyon Hatası · Uzmanlık Dışı Girişim · İddia Belgeden Belirlenemiyor | `Sheet`'ten **metin olarak olduğu gibi yazılır** (aktarımda liste doğrulaması yok); liste kart ekranındaki seçimi ve `DEGER_HAVUZLARI` fark raporunu (§3.7) besler. Bu yüzden listedışı yazım karta girer ve kart ekranında liste dışı görünür — yazımı bu tabloya uydurun | DB-2026-001 (04.09): liste bu bildirimle doldu; 1.0'da bilinçli boştu. "İddia Belgeden Belirlenemiyor" ≠ boş (belge okundu, iddia katmanı yok) |
| `Müvekkil Tipi` | 5 | Sigorta · Doktor · Kurum · Hasta · Diğer Sağlık Çalışanı | Liste doğrulamalı: tanınmayan değer **yazılmaz**, satır raporuna `HATA` düşer; ` ; ` ile çok değer yazılmaz | DB-2026-002 (04.09) |
| `Hizmet Türü` | 9 | Takip (doktor müvekkil) · Lexis Rapor · Vekaletsiz Takip · Vekaletli Takip · Vekalet Ücreti Alacağı · Takip (hasta vekilliği) · Takip (kurum vekilliği) · Danışmanlık · Takip (sağlık personeli) | aynı | DB-2026-002 (04.09) |
| `Olay Türü` | 3 | Tıbbi Olay · Belgeleme Olayı · Tıbbi + Belgeleme | Liste doğrulamalı; `Tıbbi Olay ; Belgeleme Olayı` ikilisi üçüncü değere çözülür, başka kombinasyon yazılmaz (§3.2) | 25.08 belgeniz + 02.09 kararımız |
| `Hükümdeki Rol` | 4 | Tek Gerekçe · Yan Gerekçe · Yalnız Saptama · Reddedilmiş İddia | Liste doğrulamalı; tek değer | 25.08 belgeniz + 02.09 kararımız |
| `Karar Durumu` — `Yerel` aşaması | 28 | Açılmamış Sayılması (HMK 150. Md) · Adli Para Cezası · Anlaşma · Anlaşmama · Beraat · Birleştirme · Derdest · Düşme Kararı · Hapis Cezası · Hapis Cezasının Paraya Çevrilmesi · Hükmün Açıklanmasının Geri Bırakılması (HAGB) · İflas · Kabul · Kabul/Kısmen · Kapalı · Karar Verilmesine Yer Olmadığına (HMK 331 Md.) · Kovuşturmaya Yer Olmadığına (KYOK) · Red/Arabuluculuk Ön Şart · Red/Dilekçenin Reddi · Red/Esastan · Red/Feragat · Red/Görev · Red/Husumet · Red/İdari Merciye Tevdi · Red/MSK Kararı Gereği · Red/Yargı Yolu · Red/Yetkisizlik · Red/Zamanaşımı | `Karar_Asamalari`'ndan; havuz dışı değer satırı düşürmez: durum boş kalır, değer açıklamaya taşınır, rapora yazılır (§3.5) | 10.08 `DEGER_HAVUZLARI`nız; DB-2026-005 cevabımızla gönderilen kanonik liste |
| `Karar Durumu` — `İstinaf` | 3 | Kaldırma · Kaldırma/Yeniden Hüküm · Başvuru Ret | aynı | aynı |
| `Karar Durumu` — `Temyiz` | 3 | Bozma · Onama · Düzelterek Onama | aynı | aynı |
| `Karar Durumu` — `Karar Düzeltme` | 2 | Karar Düzeltme Kabul · Karar Düzeltme Ret | aynı | aynı |
| `Başvuran Taraf` / `İstinaf Mahkemesi Başvuran Taraf` | 3 | Davacı · Davalı · Her İki Taraf | `Davalı/Davacı` ve `Davacı/Davalı` yazımları "Her İki Taraf"a çözülür; başka yazım **boş bırakılır** (rapora düşmez) | bizim listemiz |

DB-2026-010'daki dört açık havuz (kanonik yazım standardı getirdiğiniz serbest metin
alanları) bizde **sözlüksüz metin alanıdır**: değer olduğu gibi yazılır, yazım
standardınız bizde iş çıkarmaz.

---

## 4. Cevap paketini nasıl yorumlayacaksınız

Uygulanan her paket için `03_VERI_TESLIM/cevap/<paket adı uzantısız>/` klasörü açılır.
CSV'ler noktalı virgül ayraçlı ve UTF-8'dir; Türkçe Excel'de doğrudan açılır.

| Dosya | Ne söyler | Nasıl kullanılır |
| --- | --- | --- |
| `eslesme_<paket>.csv` | Ana sayfadaki **her** satır için: `sistem_no; dosya_no; case_id; tracking_no; klasor_no_2; tku_no; case_party_id; durum; sebep` | `durum = ESLESTI` → bizde kart numarası `case_id`, ofis numarası `tracking_no`. `durum = ESLESMEDI` → `sebep` sütununa bakın (aşağıda). Talep #9'un cevabıdır; kendi eşleme tablonuzu buradan kurun |
| `ozet_<paket>.txt` | Tek ekranlık koşu özeti + son satırda kapı kararı | Sayılar sizin `DEGISIKLIK_OZETI`'nizle tutuyor mu diye bakın |
| `satir-raporu_<zaman>.csv` | Yalnız sorunlu satırlar: `satir_no; sistem_no; dosya_no; tur; sebep` | `tur = ATLANDI` beklenen sebep (kart yok). `tur = HATA` insan işi (aşağıda) |
| `kardes-foy-celiskileri_<zaman>.csv` | Aynı davanın föyleri aynı alan için farklı değer söylüyor: `kume; kume_anahtari; alan; degerler` | O alan karta **yazılmadı**. Föylerden birini düzeltip sonraki pakette gönderin |
| `deger-havuzu-farki_<paket>.csv` | Yalnız fark varsa: `havuz; liste; yon; deger` | `yon = teslimde var / bizde yok` → o değer karta yazılmamıştır; listeye eklenmesini isterseniz §6 ile bildirin |
| `kuru-kosu-ozeti.txt`, `uygulama-ozeti.txt` | Provanın ve gerçek uygulamanın ayrı özetleri | Normalde aynı sayılar; farklıysa bize haber verin |

**`sebep` sütununda göreceğiniz başlıca metinler ve anlamları:**

| Sebep | Anlamı | Sizden beklenen |
| --- | --- | --- |
| `kart bulunamadı` (ATLANDI) | `Dosya No` bizim klasör numaralarımızla eşleşmedi | Dosya No'yu kontrol edin; bizde kart yoksa bu satır her pakette atlanır, sorun değil |
| `belirsiz eşleşme` (HATA) | Aynı Dosya No bizde 2+ kartla eşleşiyor; `Esas`, `Ana Tür` ve `Müvekkil` adı (üçüncü anahtar, tam anahtar eşitliği — bulanık eşleşme yok) da ayırmadı | Satırda `Esas`, `Ana Tür` ve `Müvekkil` dolu olsun; hâlâ ayrılmıyorsa bize bildirin |
| `Dosya No boş` (HATA) | Kimlik eksik | Doldurun |
| `<alan> yazılmadı: tanınmayan değer …` (HATA) | Kapalı listede karşılığı yok | Ya yazımı bizimkine uydurun ya da yeni değer bildirin (§6) |
| `<alan> yazılmadı: çok değerli hücre tanımsız …` | `Olay Türü`/`Hükümdeki Rol` için izin verilmeyen kombinasyon | Tek değere indirin |
| `boşaltılmadı — …` | `(boş)` talimatı bu alanda geçersiz ya da öneksiz | §3.4 |

**Cevap klasörü yoksa:** paket ya "inceleme bekliyor"dur ya reddedilmiştir; iki durumda da
HukuDok tarafı size yazar. İki iş günü haber almazsanız sorun.

**Ölçek beklentisi:** 18.08 paketi 8.409 satırdı; 8.156 eşleşti, 217 atlandı (bizde kart
yok), 36 hata (33 belirsiz eşleşme + 3 boş Dosya No). Bu oranlar eşik içindedir; benzer bir
paket gece kendiliğinden uygulanır.

---

## 5. Neler sistemi bozar — bildirim gerektiren değişiklikler

Aşağıdaki tablo "bunu değiştirirseniz ne olur" sorusunun cevabıdır. **KIRICI** satırlar
bildirilmeden yapılırsa paket ya reddedilir ya da veri sessizce kaybolur; sistemin bizim
tarafta yeniden düzenlenmesi gerekir. **BİLDİRİLMELİ** satırlar paketi bozmaz ama bilgiyi
kullanabilmemiz için önceden anlaşma ister. **SERBEST** satırlar için bildirim gerekmez.

| Değişiklik | Sınıf | Sistemde ne olur |
| --- | --- | --- |
| `SistemNo` değerlerinin değişmesi, birleşmesi, yeniden numaralanması | **KIRICI** | `SistemNo` föyün kimliğidir. Yeni numara = yeni föy; eski föy yetim kalır, tarihçe kopar, mükerrer doğar |
| `Dosya No` biçiminin değişmesi (ör. `13.021.00` → `13-021`) | **KIRICI** | Eşleşme köprüsü kopar; tüm satırlar "kart bulunamadı" olur |
| `SistemNo` / `Dosya No` başlığının değişmesi | **KIRICI** | Paket reddedilir |
| `Sheet` sayfasının adının değişmesi | **KIRICI** | Paket reddedilir |
| §3.2'deki okunan 47 alandan birinin başlığında **kelime** değişikliği | **KIRICI (sessiz)** | Hata yok; alan "bu teslimde yok" sayılır, o sütundaki güncellemeler hiç işlenmez. (DB-2026-007 bu sınıfa girmedi: `Uzmanlık Alanı` zaten tanınan ikinci yazımdı) |
| Sayfa adlarının değişmesi (`Karar_Asamalari`, `Düzeltme_Logu`, `DEGER_HAVUZLARI`) | **KIRICI (sessiz)** | Sayfa atlanır, içeriği işlenmez |
| Çok değer ayracının değişmesi (`;` yerine `,` / `/`) | **KIRICI** | Hücre tek değer sanılır; kapalı listede tanınmaz, yazılmaz |
| Tarih yazımının değişmesi (`2026-08-18`, `18/08/26`) | **KIRICI** | Çözülemeyen tarih boş yazılır. Excel tarih hücresi (DB-2026-009) tam istediğimiz biçimdir |
| Sayı yazımının değişmesi (`12,500.00` İngiliz biçimi) | **KIRICI** | Yanlış tutar okunabilir. Excel sayı hücresi (DB-2026-009) tam istediğimiz biçimdir |
| Dosya biçimi `.xlsm` / `.csv`, ad kalıbı dışı | **KIRICI** | Dosya yok sayılır ya da reddedilir |
| Kapalı listeye **yeni değer** (`Müvekkil Tipi`, `Hizmet Türü`, `Olay Türü`, `Hükümdeki Rol`, karar durumları) | **BİLDİRİLMELİ** | Değer yazılmaz, rapora düşer (karar durumunda: durum boş, değer açıklamaya); biz listeye ekleyince sonraki pakette işlenir |
| `İddia Edilen Kusur`'a yeni değer | **BİLDİRİLMELİ** | Değer karta **metin olarak yazılır** (§3.8) ama listemizde olmadığı için kart ekranında liste dışı görünür ve `DEGER_HAVUZLARI` fark raporuna düşer; DB-2026-001'in dokuz değeri bugün listemizdedir |
| `Ana Tür` / `Durum` / `Son Durum`'a yeni değer | **BİLDİRİLMELİ** | Eşleme sözlüğümüzde yoksa satır hata verir ya da alan yazılmaz |
| **Yeni sütun** eklenmesi | **BİLDİRİLMELİ** | Sütun sessizce yok sayılır. Yeni bilgi taşıyorsa bizim tarafta alan + eşleme açılır; bildirimden sonra genelde bir teslim döngüsü sürer |
| Bir sütunun **kalıcı** kaldırılması | **BİLDİRİLMELİ** | Paket bozulmaz (alan korunur), ama "artık gelmiyor" bilgisini belgeleyelim |
| `Düzeltme_Logu`'na ayrı `Sütun` başlığı açılması | **BİLDİRİLMELİ (olumlu)** | Önek yerine başlık okunur; önceden haber verin ki doğrulayalım |
| Yeni sayfa eklenmesi | **BİLDİRİLMELİ** | Yok sayılır; işlenmesini istiyorsanız tanımlanmalı |
| Aşama adlarına yeni değer (`Yerel`/`İstinaf`/`Temyiz`/`Karar Düzeltme` dışında) | **BİLDİRİLMELİ** | Aşama yazılmaz |
| Sütun sırasının değişmesi | SERBEST | Ada göre okunur |
| Satır sayısı, satır sırası, yalnız değişen föylerin gönderilmesi | SERBEST | Partili teslim desteklenir |
| Boş hücreler | SERBEST | "Bu teslimde yok" sayılır, silmez |
| Okunmayan sayfaların içeriği (`SUTUN_SOZLUGU` vb.) | SERBEST | |
| Büyük/küçük harf, aksan, boşluk farkı — başlıkta, kapalı liste değerinde **ve ad alanlarında** (`Müvekkil`, `Karşı Taraf`, `Sigortalı`, `Davalı İdare`, `Sorumlu Avukatlar`) | SERBEST | Yutulur. DB-2026-008 (İlk Harf Büyük) bu sınıftadır: 33.441 hücre bizde "değişmiş" görünmez, `Yazim_Standardi` tablosuna ihtiyacımız yok |
| Bildirimle gelen ek sayfalar (`Kaldirilan_Sutunlar`, `S37_Kanonik`, `Yazim_Standardi`) | SERBEST | Okunmaz, arşiv olarak kalabilir |

**Genel kural:** "Sistem hata vermedi" demek "işlendi" demek değildir. Sessiz kayıp yolları
(sütun adı, sayfa adı, ayraç) ancak cevap paketindeki sayılarla yakalanır. Her cevapta
`ozet` dosyasındaki "alan değişikliği" sayısını beklediğinizle karşılaştırın; beklediğinizden
çok düşükse bir sütun tanınmamış olabilir.

---

## 6. Bildirim formatı — "Format Değişiklik Bildirimi"

Bildirim **teslimden önce**, tercihen bir teslim döngüsü önce gelir (sistem tarafında
değişiklik + test + yayına alma gerekir). Bildirilmemiş bir değişiklikle gelen paket
"inceleme bekliyor"da durur ve düzeltilmiş paket istenir.

Kanal: e-posta (tercih) ya da WhatsApp; ekli `.md` ya da `.xlsx` dosyası olabilir. Sistem bu
bildirimi otomatik okumaz; HukuDok ekibi okuyup uygular ve size "hazır" der.

Her değişiklik için bir kayıt; alanların tamamı doldurulur. Numara dizisi sizde devam
eder: `DB-2026-001`…`010` REV-2 (04.09.2026) ile kullanıldı, sonraki bildirim `DB-2026-011`
ile başlar; aşağıdaki `DB-2026-0NN` yer tutucudur:

```
DEĞİŞİKLİK BİLDİRİMİ
Bildirim no        : DB-2026-0NN
Tarih              : 15.09.2026
Tür                : yeni sütun | sütun adı değişikliği | sütun kaldırma | yeni sayfa |
                     sayfa adı değişikliği | yeni kapalı liste değeri | kimlik biçimi |
                     ayraç/tarih/sayı biçimi | diğer
Etkilenen sayfa    : Sheet
Eski başlık/değer  : (yoksa "—")
Yeni başlık/değer  : Bilirkişi Rapor Tarihi
Anlamı             : Son bilirkişi raporunun mahkemeye sunulduğu tarih; GG.AA.YYYY
Değer havuzu       : (kapalı listeyse tüm izinli değerler; serbestse "serbest metin")
Boş ne demek       : bilinmiyor / rapor yok (NULL ≠ 0 kuralı geçerli mi?)
Föy mü dava mı     : föy düzeyi | dava düzeyi (aynı davanın föylerinde aynı olmak zorunda mı?)
İlk geçerli paket  : HUKDOK_TESLIM_PAKETI_2026-09-22.xlsx
Örnek satır        : SistemNo=H-12345, yeni değer=03.07.2026
Geri uyumluluk     : eski başlık bir süre birlikte gelecek mi? (evet/hayır)
```

Makine-okur eşdeğeri (asistanınız üretebilir; biz her ikisini de kabul ederiz):

```json
{
  "bildirim_no": "DB-2026-0NN",
  "tarih": "2026-09-15",
  "tur": "yeni_sutun",
  "sayfa": "Sheet",
  "eski": null,
  "yeni": "Bilirkişi Rapor Tarihi",
  "anlam": "Son bilirkişi raporunun mahkemeye sunulduğu tarih",
  "deger_tipi": "tarih",
  "deger_havuzu": null,
  "bos_anlami": "rapor yok / bilinmiyor",
  "duzey": "foy",
  "ilk_paket": "HUKDOK_TESLIM_PAKETI_2026-09-22.xlsx",
  "ornek": {"SistemNo": "H-12345", "deger": "03.07.2026"},
  "geri_uyumlu": false
}
```

Bizden dönecek cevap: "kabul + hangi paketten itibaren işlenir" ya da "soru". Cevap gelmeden
yeni biçimi göndermeyin.

---

## 7. Özel durumlar

| Durum | Ne yapılmalı |
| --- | --- |
| Tek bir föyde acil düzeltme | Yalnız o satırı içeren küçük bir paket (`SistemNo` + `Dosya No` + değişen sütunlar) bırakın; gece işlenir. Gerçekten acilse WhatsApp'tan haber verin, HukuDok yöneticisi panelden gündüz uygular |
| Düzeltme listeleri (ıslah hatası, manevi > toplam vb.) | Ayrı dosya değil, normal paket biçiminde; `Düzeltme_Logu` gerekçeyi taşısın |
| Föy birleştirme / bölme | **Önce bildirin** (§6, tür "kimlik biçimi"). `SistemNo` değişimi kimlik değişimidir |
| Föyün kapsamdan çıkması | `Silinen_Föyler` ya da `Kapsam_Dışı` sayfası; ana sayfadan da çıkarın |
| Yeni branş dilimi (göz, ortopedi…) | Partili paket olarak gelir; yeni klinik kodlama değerleri varsa `DEGER_HAVUZLARI`'na koyun, fark raporunu okuyun, yeni değerleri §6 ile bildirin |
| Paketi yanlışlıkla bıraktınız | Bize hemen yazın. Gece 04:00'ten önce silerseniz işlenmez; sonra silmenin etkisi yoktur (içerik zaten alınmıştır) |
| Bir gecede iki paket | Yalnız ilki otomatik; ikincisi için HukuDok yöneticisi onay verir. Kaçının |
| Sütun adını yanlışlıkla değiştirdiniz ve paket işlendi | Bize yazın; sütunu eski adıyla içeren küçük bir paket gönderirseniz güncellemeler o gece işlenir (sistem idempotent, ikinci geçiş zarar vermez) |

---

## 8. Teslim öncesi kontrol listesi

1. Dosya adı `HUKDOK_TESLIM_…xlsx`; klasör `03_VERI_TESLIM/gelen/`.
2. `Sheet` var; `SistemNo` ve `Dosya No` dolu; sütun adları önceki paketle aynı.
3. `DEGISIKLIK_OZETI`'nde "Önceki teslim" satırı, bir önceki dosyanın tam adıyla.
4. Çok değerli hücrelerde ayraç `;`; tarihler `GG.AA.YYYY`; sayılar Türkçe biçim.
5. Kapalı listelerde (§3.8: `Müvekkil Tipi`, `Hizmet Türü`, `Olay Türü`, `Hükümdeki Rol`,
   `Karar Durumu`, `İddia Edilen Kusur`) yalnız bizde de olan değerler; yeni değer için
   önce §6 bildirimi.
6. `(boş)` talimatları `Düzeltme_Logu`'nda `[Sütun Adı]` önekli.
7. Yapısal bir değişiklik varsa §6 bildirimi gönderildi ve "hazır" cevabı alındı.
8. Bir önceki paketin cevap klasörü okundu; `ESLESMEDI` ve `HATA` satırları ele alındı.

---

## 9. Makine-okur özet (asistanınız için)

```yaml
hukdok_teslim_spec:
  surum: "1.1"
  surum_tarihi: "2026-09-04"
  degisiklik_gecmisi:
    - {surum: "1.0", tarih: "2026-09-03", not: "ilk sürüm"}
    - {surum: "1.1", tarih: "2026-09-04", not: "DB-2026-001…010 (REV-2) + cevabımız işlendi; Müvekkil Tipi/Hizmet Türü okunuyor; kapalı liste envanteri"}
  islenen_bildirimler: ["DB-2026-001", "DB-2026-002", "DB-2026-003", "DB-2026-004", "DB-2026-005",
                        "DB-2026-006", "DB-2026-007", "DB-2026-008", "DB-2026-009", "DB-2026-010"]
  sonraki_bildirim_no: "DB-2026-011"
  klasor: "03_VERI_TESLIM/gelen"
  cevap_klasoru: "03_VERI_TESLIM/cevap/<paket_adi_uzantisiz>/"
  dosya_adi_kalibi: "^HUKDOK_TESLIM_.*\\.xlsx$"   # büyük/küçük harf duyarsız
  bicim: xlsx
  azami_boyut_mb: 50
  gunde_azami_paket: 1
  isleme_saati: "04:00 Europe/Istanbul"
  zorunlu_sayfa: ["Sheet"]
  istege_bagli_sayfa: ["DEGISIKLIK_OZETI", "Karar_Asamalari", "Düzeltme_Logu",
                       "DEGER_HAVUZLARI", "Silinen_Föyler", "Kapsam_Dışı"]
  okunmayan_sayfa: ["SUTUN_SOZLUGU", "SINIFLANDIRMA_MODELI", "HUKDOK_TALEPLERI"]
  sheet:
    zorunlu_sutun: ["SistemNo", "Dosya No"]
    kimlik: "SistemNo (değişmez)"
    eslesme_koprusu: "Dosya No ↔ HukuDok klasör numarası"
    sutun_eslesme: "ada göre; sıra serbest; aksan/boşluk/büyük-küçük yutulur; kelime farkı yutulmaz"
    okunan_alan_sayisi: 42
    okunan_baslik_yazim_sayisi: 54
    okunan_baslik:            # aynı satırdaki yazımlar aynı alandır
      - ["SistemNo", "Sistem No"]
      - ["Dosya No", "DosyaNo", "Klasör No.2"]
      - ["Klasör No", "TKU", "TKU No", "TKU No."]
      - ["Hasar No", "Hasar Numarası"]
      - ["Hukuk No"]
      - ["Arabuluculuk Numarası"]
      - ["Ana Tür"]
      - ["Durum"]
      - ["Dava Konusu"]
      - ["Dava Türü Alt Kırılımı", "Uzmanlık Alanı"]
      - ["Buro Özel Türü"]
      - ["Son Durum"]
      - ["Yerel Mahkeme"]
      - ["Esas"]
      - ["Karar No"]
      - ["Karar Tarihi"]
      - ["İstinaf Mahkemesi Başvuran Taraf"]
      - ["Dava Tarihi"]
      - ["İş Kabul Tarihi"]
      - ["Arşiv Tarihi"]
      - ["Arabuluculuk Karar Tarihi"]
      - ["Dava Değeri TL", "Dava Değeri"]
      - ["Manevi Dava Değeri TL", "Manevi Dava Değeri"]
      - ["Islah Tutarı", "İslah Tutarı"]
      - ["Hükmedilen Maddi"]
      - ["Hükmedilen Manevi"]
      - ["Hükmedilen Toplam"]
      - ["Müvekkil"]
      - ["Karşı Taraf"]
      - ["Sigortalı"]
      - ["Davalı İdare"]
      - ["Taraf Sıfatı"]
      - ["Sorumlu Avukatlar", "Sorumlu Avukat"]
      - ["Tıbbi Süreç"]
      - ["Tıbbi Olay"]
      - ["İddia Edilen Kusur"]
      - ["Hastada Oluşan Zarar"]
      - ["Uygulanan Yöntem"]
      - ["Olay Türü"]
      - ["Hükümdeki Rol"]
      - ["Müvekkil Tipi"]
      - ["Hizmet Türü"]
    kimlik_olmayan_alan: ["Arabuluculuk Numarası", "Müvekkil"]   # köprü yalnız Dosya No
    gelmeyen_sutun: "DB-2026-003: bu teslimde yok sayılır, mevcut değer korunur, hata yok"
    tanimayan_sutun: "sessizce yok sayılır"
    bos_hucre: "bu teslimde yok; mevcut değer korunur"
    cok_deger_ayraci: ";"
    tarih: "Excel tarihi veya GG.AA.YYYY; 1900 ve öncesi + gelecek = yer tutucu → boş"
    sayi: "Excel sayısı veya Türkçe biçim (12.500,00)"
    yer_tutucu_metin: ["-", "--", "—", "?", "YOK", "BELİRSİZ", "BOŞ", "N/A", "NA"]
    null_sifir_farki: true
    ad_alanlari_harf_duyarsiz: true   # DB-2026-008: İlk Harf Büyük değişiklik sayılmaz
  kapali_listeler:                    # §3.8 — bizdeki değer havuzları (04.09.2026)
    iddia_edilen_kusur:
      uygulama: "metin olarak yazılır; liste kart seçimini + DEGER_HAVUZLARI farkını besler"
      degerler: ["Uygulama Hatası", "Komplikasyon Yönetimi", "Aydınlatma", "Tanı Hatası",
                 "Organizasyon Hatası", "Takip Eksikliği", "Endikasyon Hatası",
                 "Uzmanlık Dışı Girişim", "İddia Belgeden Belirlenemiyor"]
    muvekkil_tipi:
      uygulama: "doğrulamalı; tanınmayan/çok değer yazılmaz + satır raporu"
      degerler: ["Sigorta", "Doktor", "Kurum", "Hasta", "Diğer Sağlık Çalışanı"]
    hizmet_turu:
      uygulama: "doğrulamalı; tanınmayan/çok değer yazılmaz + satır raporu"
      degerler: ["Takip (doktor müvekkil)", "Lexis Rapor", "Vekaletsiz Takip", "Vekaletli Takip",
                 "Vekalet Ücreti Alacağı", "Takip (hasta vekilliği)", "Takip (kurum vekilliği)",
                 "Danışmanlık", "Takip (sağlık personeli)"]
    olay_turu:
      uygulama: "doğrulamalı; 'Tıbbi Olay ; Belgeleme Olayı' → 'Tıbbi + Belgeleme'"
      degerler: ["Tıbbi Olay", "Belgeleme Olayı", "Tıbbi + Belgeleme"]
    hukumdeki_rol:
      uygulama: "doğrulamalı; tek değer"
      degerler: ["Tek Gerekçe", "Yan Gerekçe", "Yalnız Saptama", "Reddedilmiş İddia"]
    karar_durumu:
      uygulama: "Karar_Asamalari; havuz dışı → durum boş, değer açıklamaya, rapora; lehe/aleyhe ekseni yok"
      yerel: ["Açılmamış Sayılması (HMK 150. Md)", "Adli Para Cezası", "Anlaşma", "Anlaşmama", "Beraat",
              "Birleştirme", "Derdest", "Düşme Kararı", "Hapis Cezası", "Hapis Cezasının Paraya Çevrilmesi",
              "Hükmün Açıklanmasının Geri Bırakılması (HAGB)", "İflas", "Kabul", "Kabul/Kısmen", "Kapalı",
              "Karar Verilmesine Yer Olmadığına (HMK 331 Md.)", "Kovuşturmaya Yer Olmadığına (KYOK)",
              "Red/Arabuluculuk Ön Şart", "Red/Dilekçenin Reddi", "Red/Esastan", "Red/Feragat", "Red/Görev",
              "Red/Husumet", "Red/İdari Merciye Tevdi", "Red/MSK Kararı Gereği", "Red/Yargı Yolu",
              "Red/Yetkisizlik", "Red/Zamanaşımı"]
      istinaf: ["Kaldırma", "Kaldırma/Yeniden Hüküm", "Başvuru Ret"]
      temyiz: ["Bozma", "Onama", "Düzelterek Onama"]
      karar_duzeltme: ["Karar Düzeltme Kabul", "Karar Düzeltme Ret"]
    basvuran_taraf:
      uygulama: "tanınmayan yazım boş bırakılır"
      degerler: ["Davacı", "Davalı", "Her İki Taraf"]
  degisiklik_ozeti:
    etiket: "Önceki teslim"
    deger: "önceki dosya adı; '·' sonrası yok sayılır; ilk teslimde '—' veya 'yok'"
  duzeltme_logu:
    sutunlar: ["SistemNo", "Eski Değer", "Yeni Değer", "Gerekçe", "Tarih"]
    bosaltma_isareti: "(boş)"
    sutun_adi: "Gerekçe başında [Sütun Adı] öneki; ya da ayrı 'Sütun' başlığı"
    bosaltilamayan: ["Karar No", "Karar Tarihi", "Yerel Mahkeme", "Dava Türü Alt Kırılımı"]
  karar_asamalari:
    sutunlar: ["SistemNo", "AsamaNo", "Aşama", "Mahkeme", "Esas No", "Karar No",
               "Karar Tarihi", "Karar Durumu", "Tebliğ Tarihi", "Başvuran Taraf", "Güven", "Açıklama"]
    asama_degerleri: ["Yerel", "İstinaf", "Temyiz", "Karar Düzeltme"]
    asama_onceki: "'Önceki' kabul edilir: karar aşaması değil, Esas No kartın esas tarihçesine önceki esas olarak yazılır — bu satırları GÖNDERİN (DB-2026-004)"
    taninmayan_asama: "satır sessizce atlanır"
  kapsam_sayfalari:
    sutunlar: ["SistemNo", "Silinme Gerekçesi | Kapsam Dışı Gerekçesi | Gerekçe", "Tarih"]
    etki: "föy işaretlenir, silinmez"
  deger_havuzlari:
    baslik: ["Havuz / Sütun", "Değer"]
    karsilastirilan: ["İddia Edilen Kusur", "Yerel Mahkeme Karar Durumu", "İstinaf Karar Durumu",
                      "Yargıtay Onama Durumu", "Olay Türü", "Hükümdeki Rol"]
    taninmayan_deger: "yazılmaz; rapora düşer; listeye otomatik eklenmez"
    karsilastirilmayan: ["Müvekkil Tipi", "Hizmet Türü"]   # fark raporu yok; satır raporu var
  kapi:
    hata_orani_azami: 0.02
    eslesmeyen_orani_azami: 0.05
    alan_degisikligi_azami: 10000
    ilk_teslim: "daima insan onayı"
    zincir: "önceki teslim uygulanmış olmalı"
  cevap_dosyalari:
    eslesme_csv: ["sistem_no", "dosya_no", "case_id", "tracking_no", "klasor_no_2",
                  "tku_no", "case_party_id", "durum", "sebep"]
    satir_raporu_csv: ["satir_no", "sistem_no", "dosya_no", "tur", "sebep"]
    celiski_csv: ["kume", "kume_anahtari", "alan", "degerler"]
    havuz_farki_csv: ["havuz", "liste", "yon", "deger"]
    ozet_txt: "sayılar + kapı kararı"
    csv_bicimi: "UTF-8 BOM, ';' ayraç"
  bildirim_gerektiren:
    kirici: ["SistemNo değişimi", "Dosya No biçimi", "Sheet adı", "SistemNo/Dosya No başlığı",
             "okunan 47 alandan birinin başlığında kelime değişimi", "sayfa adı değişimi",
             "ayraç/tarih/sayı biçimi", "dosya biçimi"]
    bildirilmeli: ["yeni kapalı liste değeri (Müvekkil Tipi, Hizmet Türü, Olay Türü, Hükümdeki Rol, karar durumları)",
                   "İddia Edilen Kusur yeni değer (metin yazılır, liste dışı görünür)",
                   "Ana Tür/Durum/Son Durum yeni değer",
                   "yeni sütun", "kalıcı sütun kaldırma", "yeni sayfa", "yeni aşama adı"]
    serbest: ["sütun sırası", "satır sayısı/sırası", "boş hücre", "okunmayan sayfa içeriği",
              "aksan/boşluk/büyük-küçük (başlık, kapalı liste değeri, ad alanları)",
              "bildirim ek sayfaları (Kaldirilan_Sutunlar, S37_Kanonik, Yazim_Standardi)"]
  bildirim_kanali: "e-posta veya WhatsApp, §6 şablonu, teslimden bir döngü önce; numara dizisi DB-2026-011'den devam eder; cevabımız gelmeden yeni biçimi göndermeyin"
```

---

*Sorular için HukuDok ekibine yazın. Bu belgenin güncel sürümü her yapısal değişiklikte
yeniden gönderilir; sürüm numarası başlıktadır.*
