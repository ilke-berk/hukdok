# HUKDOK Veri Teslim Hattı — Veri Ekibi Bilgilendirmesi

**Tarih:** 03.09.2026 (ilk sürüm) · **Gönderen:** HukuDok ekibi (Hanyaloğlu Acar + LexisBio) ·
**Muhatap:** MicroKolayOfis master'ını hazırlayan veri ekibi · **Sürüm:** 1.3 (10.09.2026)

> Bu belge yapılandırılmış yazıldı: tablolar, birebir yazımlar ve sondaki makine-okur özet
> (§9), kendi yapay zekâ asistanınıza "teslim öncesi kontrol" ve "cevap paketi yorumlama"
> görevi olarak doğrudan verilebilir. Buradaki her kural çalışan sistemden okunarak yazıldı;
> tahmin ya da niyet değil, bugün geçerli davranıştır.

**Değişiklik geçmişi**

| Sürüm | Tarih | Ne değişti |
| --- | --- | --- |
| 1.0 | 03.09.2026 | İlk sürüm |
| 1.1 | 04.09.2026 | Format Değişiklik Bildirimi REV-2 (DB-2026-001…010) ve aynı gün verdiğimiz cevap işlendi: `Müvekkil Tipi` + `Hizmet Türü` artık **okunuyor** (§3.2; "bekleyen alan" değil); okunan başlık listesi sistemden yeniden sayıldı (42 alan / 54 kabul edilen yazım); kapalı listelerimizin tam envanteri (§3.8 — `İddia Edilen Kusur` 9 değerle doldu); `Karar_Asamalari`'nda `Önceki` etiketi (§3.5); DB-2026 kalemlerinin bizdeki karşılığı ilgili bölümlere tarihli şerh olarak girdi; §5 tablosu, §6 örnek bildirim numarası, §9 özet |
| 1.2 | 05.09.2026 | 04.09 paketinin **54 sütununun tamamı** okunur hâle geldi: `Dosya - Föy Bilgileri`, `Para Birimi TL`, `MüvekkilNo`, `Eski Dosya No`, `İstinaf Mahkeme Başvuru Tar.` artık **okunuyor** (§3.2; okunan liste 47 alan / 66 yazım); `Yerel Mahkeme Tebliğ Tarihi` ve `Yerel Mahkeme Kararı Açıklaması` `Karar_Asamalari`'ndan karta da yansıyor; `Müvekkil Tipi` / `Hizmet Türü` / `Durum` föy düzeyinde de saklanır — kardeş föy çelişkisinde kart alanı boş kalır ama föy değeri kaybolmaz (§3.2 şerhi); kapalı listelerimiz paketinizin değer havuzlarıyla olduğu gibi dolduruldu, tıbbi beşli çok değerli hücreler kırpılmadan saklanır, üç taraf rolü listeye girdi. Dosyanızda değişiklik gerekmez |
| 1.3 | 10.09.2026 | 06.09 cevabınıza karşılık sözleşme 1.3 ile hizalandı: `DEGISIKLIK_OZETI` artık **üç satır** taşır ("Önceki teslim" zinciri + `—` yalnız ilk teslimde, "Teslim türü: tam \| delta", "Veri kesim tarihi" — §3.3); **delta (partili) teslim** kuralları (§3.4); `Karar_Asamalari`'nda `Başvuru Tarihi` sütunu okunur, aşama satırı **yerinde güncellenir / belgeli satır korunur / ikinci tur eklenir / silinmez**, `Kapalı`·`Derdest` karar durumu değildir (§3.5); `Durum` için kesim-sonrası kullanıcı kaydı korunur, satır raporunda `KORUNDU` (§3.3, §4); karar durumu havuzları çalışan sistemden yeniden sayıldı — Yerel 27 · İstinaf 8 · Temyiz 4 · Karar Düzeltme 2, `Kapalı`/`Derdest` listeden çıktı (§3.8); DB-2026-008 kapsamının `Sigortalı` · `Davalı İdare` · mahkeme sütunlarına genişletilmesi ricası ve `Yazim_Standardi` sayfası artık **isteniyor** (§3.8, §5 — 04.09'daki "gerek yok" geri alındı); §9 özet güncellendi (okunan başlık listesi §3.2 ile eşitlendi: 47 alan / 66 yazım). Sütun adı, sayfa adı ve kimlik biçimi değişmedi |

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
| Yapı farkı (bir önceki uygulanan pakete göre) | yeni sütun ya da kaybolan sayfa her türde; **kaybolan sütun yalnız tam pakette** (delta'da bilgi, §3.4) | inceleme bekler |
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
| `DEGISIKLIK_OZETI` | Hayır, ama **her pakete koyun** | Üç etiketli satır okunur: "Önceki teslim" (zincir kontrolü), "Teslim türü" (tam \| delta), "Veri kesim tarihi" (§3.3). Sayfa yoksa zincir denetlenmez, teslim **tam** sayılır, kesim tarihi paket adından alınır |
| `Karar_Asamalari` | Hayır | Föy başına yargı aşamaları (§3.5); 06.09'da eklediğiniz `Başvuru Tarihi` sütunu okunur. Yoksa aşama yazılmaz |
| `Düzeltme_Logu` | Hayır | Değişiklik gerekçeleri tarihçeye işlenir; `(boş)` talimatı buradan okunur, sütun adı ayrı `Sütun` başlığından ya da gerekçe önekinden (§3.4) |
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
  **Değer havuzları (aynı gün):** kapalı listelerimiz 04.09 paketinizin değerleriyle
  OLDUĞU GİBİ dolduruldu — dört karar durumu havuzu, `İddia Edilen Kusur`, tıbbi dört
  liste (`Tıbbi Süreç` 97 · `Tıbbi Olay` 667 · `Hastada Oluşan Zarar` 258 · `Uygulanan
  Yöntem` 260 atomik değer), `Temyiz Mahkemesi` (38), `İstinaf Mahkemesi` (217),
  `Davalı İdare` (10). Bozuk yazımlar ("Karar Aaleyhe", "YARGITAY .....HD") bizde de
  var; birlikte temizleyeceğiz, listeleri elden geçirince yeni kanonik yazımı size
  bildiririz. Bu paket için "tanınmayan değer" raporu boş kalır. Tıbbi beşlinin çok
  değerli hücreleri (` ; `) artık kırpılmadan tam saklanır. `Taraf Sıfatı`'ndaki
  `Aleyhine Başvurulan`, `Alacaklı`, `Katılan` rol listemize girdi.

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
| Ad alanları (`Müvekkil`, `Karşı Taraf`, `Sigortalı`, `Davalı İdare`, `Sorumlu Avukatlar`) | Serbest metin | Bu dört taraf sütunu karta **taraf satırı** olarak işlenir ve taraf satırları **yalnız eklenir** — mevcut satır silinmez, üzerine yazılmaz: karşılaştırma büyük/küçük harf, aksan ve I/ı-İ/i farkından bağımsız anahtarla yapılır (`AK SİGORTA A.Ş.` = `Ak Sigorta A.Ş.` = `Ak Sigorta Anonim Şirketi`), kartta zaten olan taraf yeniden yazılmaz, yalnız kartta hiç olmayan ad eklenir. Bu yüzden DB-2026-008 (İlk Harf Büyük) taraf satırlarında değişiklik üretmez **ve** bizdeki eski BÜYÜK HARF yazımlar kendiliğinden düzelmez — `Yazim_Standardi` haritasını bu yüzden istiyoruz (§3.8). Sözlük/metin alanlarında (`Dava Konusu`, `Son Durum`, `Uzmanlık Alanı`) yazım farkı **değişiklik sayılır** ve paketin yazımı bizdekinin üzerine yazılır ("paket kazanır"); tek istisna mahkeme adı (yazım bizde, §3.4). Avukat adı bizim kayıtlı yazımımızla yazılır. Ad alanları **eşleşme anahtarı değildir** (köprü `Dosya No`); müvekkil adı yalnız aynı `Dosya No`ya birden çok kart düştüğünde ayırt edici olarak kullanılır (§4) |
| `Müvekkil Tipi`, `Hizmet Türü` | Tek değer, bizdeki kapalı listeden (§3.8) | ` ; ` ile çok değer **yazılmaz**, rapora düşer; tanınmayan değer yazılmaz. Boş = bilinmiyor (bildiriminiz "tamamı dolu" diyor — ilk cevap paketinde `yazılmadı` satırı beklemiyoruz) |
| Yer tutucu metin | `-`, `--`, `—`, `?`, `YOK`, `BELİRSİZ`, `BOŞ`, `N/A`, `NA` | Hepsi "boş" sayılır |
| Çok değerli hücre | ` ; ` (noktalı virgül) ile ayrılır | Satır sonu da ayraç sayılır. Virgül ayraç **değildir** |
| Kapalı liste değeri | Bizde de olan yazım | Aksan/büyük-küçük farkı yutulur; kelime farkı yutulmaz. Tanınmayan değer **yazılmaz**, satır raporunda görünür |
| `Olay Türü` çok değer | Yalnız `Tıbbi Olay ; Belgeleme Olayı` ikilisi → "Tıbbi + Belgeleme" | Başka kombinasyon yazılmaz |
| `Hükümdeki Rol` | Tek değer | Çok değer yazılmaz, rapora düşer |
| `Sorumlu Avukatlar` | `;` ile çoklu | Yalnız ekleme yapılır, mevcut avukat silinmez |

### 3.3 `DEGISIKLIK_OZETI` — üç satır (1.3)

Sistem bu sayfanın **ilk 200 satırında** üç etiketi arar. Üçü için aynı yazım kuralı
geçerlidir: etiket ile değer aynı hücrede iki noktayla (`Önceki teslim: …`) ya da etiket bir
hücrede, değer sağındaki ilk dolu hücrede. Etiketlerde büyük/küçük harf, aksan ve boşluk farkı
yutulur. Bugünkü paketinizdeki yazım tam olarak uygundur; iki satır eklemeniz yeter:

```
Önceki teslim     | HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx · 8.409 satır × 54 sütun
Teslim türü       | tam
Veri kesim tarihi | 30.07.2026
```

| Satır | Değer | Yoksa ne olur |
| --- | --- | --- |
| **Önceki teslim** | Bir önceki paketin **dosya adı**, bıraktığınız adla birebir; `·` işaretinden sonrası (satır/sütun sayısı) dikkate alınmaz | Zincir kontrolü: ad bizde uygulanmış bir paket değilse ya da bir teslim atlanmışsa paket **insan incelemesine** düşer. Sayfa hiç yoksa zincir denetlenemez ("zincir bilinmiyor"), paket öteki eşiklerin içindeyse yine uygulanabilir |
| **Teslim türü** | `tam` (varsayılan) ya da `delta` (§3.4) | Satır yok, boş, `—` ya da tanınmayan bir değer → **tam** sayılır (tanınmayan değerde uyarı düşer, paket reddedilmez). Delta paketi `tam` sayılırsa kaybolan sütunlar yüzünden incelemeye düşer |
| **Veri kesim tarihi** | Master'ınızın bu paketteki fotoğrafının ait olduğu gün: `30.07.2026` ya da `2026-07-30` (Excel tarih hücresi de olur) | **Zorunlu sayın:** yoksa dosya adındaki tarih (`…_2026-09-04.xlsx` → 04.09.2026) kesim günü sayılır ve uyarı düşer — bu gerçek kesimden geç bir eşiktir, aradaki günlerde bizde yapılan `Durum` değişiklikleri korunmaz |

- **`—` yalnız ilk teslimde:** "Önceki teslim" için `—` ya da `yok` (boş bırakmak da olur)
  bizde uygulanmış hiçbir teslim yokken "zincir başlangıcı" sayılır ve ihlal üretmez (ilk
  teslim zaten insan onayıyla uygulanır, §1). Bizde uygulanmış bir teslim **varken** `—`
  yazarsanız paket "zincir eksik" ile incelemeye düşer — ikinci teslimden itibaren daima ad
  yazın. Zincirin başlangıcı: canlı sistemde ilk uygulanacak paket
  `HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx`'tir; sonraki teslimde bu adı yazın. 31.08 paketi bize
  hiç ulaşmadı, zincirde yer almaz.
- **Kesim tarihi ne işe yarar — `Durum` istisnası:** `Durum` (derdest/arşiv) sütununda bizim
  kaydımız esastır (06.09 §1.2'de siz de öyle dediniz). Paket `Durum`u yazar; ama kesim
  gününden itibaren bizde bir **kullanıcının** değiştirdiği `Durum` paketin eski değeriyle
  **geri yazılmaz** — satır raporuna `KORUNDU` türüyle düşer (`status korundu (kullanıcı
  gg.aa.yyyy)`), hata sayılmaz, kapı eşiğini etkilemez (§4). Kesim tarihini ileri yazarsanız
  koruma gereksiz devreye girer, geri yazarsanız bizdeki değişiklik ezilir — gerçek fotoğraf
  tarihini yazın. Bu koruma yalnız `Durum` içindir; öteki alanlarda "paket kazanır".

### 3.4 Partili (delta) teslim ve boşaltma

- Ana sayfada **olmayan sütun** ya da **boş hücre** = "bu teslimde bu bilgi yok". Bizdeki
  değer korunur, hata üretmez. Bu yüzden yalnız değişen föyleri içeren küçük paketler
  gönderebilirsiniz; tüm sütunları taşımak şart değildir (yalnız `SistemNo` ve `Dosya No`
  şarttır). Gelmeyen föye de dokunulmaz — delta'da eksik föy "silindi" anlamına gelmez.
- **Delta paket kuralları** (06.09 §11.4'teki isteğiniz — kabul):
  1. `DEGISIKLIK_OZETI`'nde `Teslim türü: delta` satırı **şart** (§3.3). Fark şudur: tam
     pakette bir sütunun **kaybolması** yapı değişikliği sayılır ve paketi incelemeye
     düşürür; delta pakette kaybolan sütun yalnız **bilgi** olarak raporlanır. Yeni sütun ve
     kaybolan sayfa her iki türde de incelemeye düşürür.
  2. Ana sayfada **yalnız değişen föyler**; `Karar_Asamalari` ve `Düzeltme_Logu` da yalnız
     **ilgili föylerin** satırlarını taşır — gelmeyen aşamaya/föye dokunulmaz.
  3. Zincir (`Önceki teslim`) delta'da da **kesintisizdir**: her delta bir öncekinin adını
     yazar, tam paket de kendinden önceki delta'nın adını.
  4. **Tam paket aylık** gelir (mutabakat): `Teslim türü: tam` ile ve envanterin tamamıyla.
  5. Belge sayımı denkliği, zincir ve öteki eşikler (§1) delta'da da aynen geçerlidir.
- **Bir alanı bilerek silmek** için `Düzeltme_Logu`'nda ilgili satırın `Yeni Değer` hücresine
  `(boş)` (parantezli) yazın ve sütunu belirtin: ya ayrı bir **`Sütun`** başlığında (06.09'da
  önerdiğiniz biçim — kabul; başlık varsa ve doluysa önce o okunur) ya da `Gerekçe`'nin
  başında **`[Sütun Adı]`** önekiyle: `[Hükmedilen Manevi] belge yeniden okundu, tutar yok`.
  Sistem üç şartı birlikte arar: log `(boş)` diyor + ana sayfada o hücre boş + bizde dolu.
  Sütunsuz `(boş)` satırı uygulanamaz (04.09 paketindeki 229 sütunsuz satır böyle
  uygulanmadı). Parantezsiz `boş` bir metin değeridir, boşaltma talimatı değildir.
- Boşaltılamayan alanlar: `Karar No`, `Karar Tarihi`, `İstinaf Mahkemesi Başvuran Taraf`
  (üçü aşama sayfasından beslenir), `Yerel Mahkeme` (yazım bizde), `Dava Türü Alt Kırılımı` /
  `Uzmanlık Alanı` (paket yazar ama silmez). Bunlar için `(boş)` raporda "boşaltılmadı"
  olarak görünür.
- Aynı davaya bağlı iki föy aynı alan için farklı **dolu** değer söylerse (biri değer, biri
  `(boş)` dahil) o alan yazılmaz, kardeş föy çelişki raporuna düşer (§4). Boş hücre çelişki
  **değildir**: aşama satırlarında da kart alanlarında da dolu değerler birleştirilir.

### 3.5 `Karar_Asamalari`

Beklenen başlıklar: `SistemNo`, `AsamaNo` / `Aşama No`, `Aşama`, `Mahkeme`, `Esas No`,
`Karar No`, `Karar Tarihi`, `Karar Durumu`, `Tebliğ Tarihi`, **`Başvuru Tarihi`** (06.09'da
eklediğiniz 22. sütun — 1.3'ten itibaren okunur), `Başvuran Taraf`, `Güven`, `Açıklama`.
Fazladan sütun sorun değildir; `Başvuru Tarihi` sütunu olmayan eski düzen de aynen çalışır
(alan boş kalır).

**`Başvuru Tarihi`:** kanun yoluna başvuru tarihi, aşama satırından okunur. İstinaf satırında
boşsa ana sayfadaki `İstinaf Mahkeme Başvuru Tar.` **yedek** kaynaktır; aşama satırı doluysa
ana sayfadaki değer o föy için atlanır (iki kaynak salınım üretmesin diye). Temyiz için yalnız
aşama sayfası okunur — ana sayfada karşılığı yoktur.

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

**`Kapalı` / `Derdest` karar durumu değildir — yazmayın (1.3):** ikisi mahkeme kararı değil
büro dosya durumudur ve yerel havuzdan çıktı (§3.8; 04.09 cevabımızdaki havuz onları
taşıdığı için sözlük tuzağı bizden kaynaklandı). Karar durumu hücresini boş bırakın —
dosyanın derdest/arşiv bilgisi ana sayfadaki `Durum`dan gelir. Yine de gelirse satır düşmez:
künyesi (mahkeme/esas/karar no/karar tarihi/tebliğ) dolu satır durumsuz yazılır ve
açıklamaya "büro durumu, karar değil: Kapalı" şerhi düşer; künyesiz satır hiç yazılmaz.
Kardeş föy uzlaşısında bu değer boş hücre gibi sayılır (kardeşi gerçek sonucu taşıyorsa o
kazanır). Beklenen bir durumdur, hata değildir; özette "büro durumu atlanan" sayacında görünür.

**Aşama satırları nasıl güncellenir (1.3):** paket satırı, kartta o aşamanın mevcut
satırlarıyla karşılaştırılır —

| Durum | Sistem ne yapar |
| --- | --- |
| İçeriği birebir aynı satır zaten var | Hiçbir şey yazılmaz (aynı paketle ikinci koşu sıfır değişiklik) |
| Konumda satır yok | Yeni satır eklenir |
| Konumdaki satır **belgeye ya da UYAP kaydına** dayanıyor | Satır **korunur**; fark satır raporuna `ATLANDI` / "belgeli aşama satırı korundu" olarak düşer (06.09 §11.3'teki "künyede belgeye dayanan taraf kazanır" kuralı) |
| Paket satırının `Esas No` **ve** `Karar Tarihi`si mevcut satırdan farklı (dördü de dolu, mevcut daha eski) | Aynı aşamanın **ikinci yargılama turu** (bozma sonrası ikinci istinaf gibi): mevcut satır kalır, paket satırı bir sonraki sıra numarasıyla **eklenir**. Yalnız biri farklıysa ya da biri boşsa bu bir düzeltmedir (alt satır) |
| Aksi hâlde | Satır **yerinde güncellenir** — bizdeki satır paketten gelmiş ya da elle girilmiş fark etmez (06.09 §0: son paket elle düzeltmeden daha doğru); değişen her alan tarihçeye eski/yeni değerle işlenir |

**Silme yoktur:** paket bir aşamayı artık taşımıyorsa bizdeki satır kalır. 04.09 cevabımızdaki
"270 HATA" sınıfı bu kuralla kapanır: uzlaştırdığınız aşama sayfası sonraki pakette bizdekini
düzeltir.

Aynı davaya bağlı iki föy aynı aşama için farklı **dolu** künye söylerse o aşama yazılmaz,
çelişki raporuna düşer; boş hücre çelişki değildir, dolu değerler birleştirilir.

**`Durum` ile karıştırmayın:** `Karar Durumu` aşama sonucudur; dosyanın derdest/arşiv
bilgisi ana sayfadaki `Durum` sütunudur ve onun tek istisnası vardır — kesim tarihinden
sonra bizde kullanıcı tarafından değiştirilmişse paket üzerine yazmaz, satır raporunda
`KORUNDU` türüyle görünür (§3.3, §4).

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

### 3.8 Kapalı listelerimiz — bizde geçerli değer havuzları (10.09.2026)

Aşağıdaki listeler çalışan sistemin referans listelerinden birebir alınmıştır (karar durumu
havuzları 10.09.2026'da yeniden sayıldı; 06.09 §12-2 genişletme isteğiniz işlendi). Listeye
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
| `Karar Durumu` — `Yerel` aşaması | 27 | Açılmamış Sayılması (HMK 150. Md) · Adli Para Cezası · Anlaşma · Anlaşmama · Beraat · Birleştirme · Düşme Kararı · Hapis Cezası · Hapis Cezasının Paraya Çevrilmesi · Hükmün Açıklanmasının Geri Bırakılması (HAGB) · İflas · Kabul · Kabul/Kısmen · Karar Verilmesine Yer Olmadığına (HMK 331 Md.) · Kovuşturmaya Yer Olmadığına (KYOK) · Red/Arabuluculuk Ön Şart · Red/Dilekçenin Reddi · Red/Esastan · Red/Feragat · Red/Görev · Red/Husumet · Red/İdari Merciye Tevdi · Red/MSK Kararı Gereği · **Red/Usulden** (yeni) · Red/Yargı Yolu · Red/Yetkisizlik · Red/Zamanaşımı | `Karar_Asamalari`'ndan; havuz dışı değer satırı düşürmez: durum boş kalır, değer açıklamaya taşınır, rapora yazılır (§3.5). `Kapalı` ve `Derdest` **listeden çıktı** — büro dosya durumudur, karar değil; yazmayın (§3.5) | 10.08 `DEGER_HAVUZLARI`nız + 06.09 §12-2 genişletme isteğiniz; 10.09.2026'da çalışan sistemden sayıldı |
| `Karar Durumu` — `İstinaf` | 8 | Kaldırma · Kaldırma/Yeniden Hüküm · Başvuru Ret · **Düzeltilerek Karar Verildi** · **Düzeltilerek Kabul Edildi** · **Düzeltilerek Reddine** · **Kısmen Kabul** · **Davacı İstinaf Talebinin Kabulü** (beşi yeni, HMK 353/1-b-2) | aynı. `Karar` (74 föy) havuza **girmedi**: tek başına anlamı belirsiz — hangi sonucu kastettiğinizi yazılı bildirin, ona göre eklenir ya da mevcut bir değere eşlenir. İstinaf yön hücreleri (~50) için bizde ayrı alan yoktur | aynı |
| `Karar Durumu` — `Temyiz` | 4 | Bozma · Onama · Düzelterek Onama · **Kısmen Onama/Kısmen Bozma** (yeni) | aynı | aynı |
| `Karar Durumu` — `Karar Düzeltme` | 2 | Karar Düzeltme Kabul · Karar Düzeltme Ret | aynı | aynı |
| `Başvuran Taraf` / `İstinaf Mahkemesi Başvuran Taraf` | 3 | Davacı · Davalı · Her İki Taraf | `Davalı/Davacı` ve `Davacı/Davalı` yazımları "Her İki Taraf"a çözülür; başka yazım **boş bırakılır** (rapora düşmez) | bizim listemiz |

Karar durumunun **müvekkil yönü** (aynı kararın doktor föyünde red, sigorta föyünde kabul
olması) kart düzeyinde tek slotta tutulur; kardeş föyler farklı söylüyorsa kart slotu boş
kalır, föyün kendi değeri ham satırında saklanır ve çelişki raporunda görünür (hata değil).

**Yazım standardı — DB-2026-008 genişletme ricası ve `Yazim_Standardi` (1.3):** 04.09
cevabımızda `Yazim_Standardi` tablosuna "gerek yok" demiştik; **düzeltiyoruz.**

- **DB-2026-008 kapsamını genişletin:** İlk-Harf-Büyük standardını `Sigortalı`, `Davalı
  İdare`, `Yerel Mahkeme`, `İstinaf Mahkemesi` ve `Temyiz Mahkemesi` sütunlarına da uygulayın.
  04.09 paketinde bu beş sütun %99-100 BÜYÜK HARF geldi; bizdeki 217 istinaf + 38 temyiz
  mahkeme listesi ve 1.677 kart alanı paketten bu yazımla doldu. Biz dönüştürsek sonraki paket
  geri yazar — kaynak sizsiniz.
- **`Yazim_Standardi` sayfasını pakete ekleyin** (eski → yeni yazım haritası): paketle
  gelmeyen eski kartlarımızın (föysüz kartlar, `Karşı Taraf`'taki 131 BÜYÜK HARF satır)
  yazımını bu haritayla düzelteceğiz — taraf satırları yalnız eklendiği için (§3.2) paket
  bunları kendiliğinden düzeltmez. Sayfa sistemce okunmaz, insan işler; adı ve düzeni serbest,
  eski değer / yeni değer / sütun üçlüsü yeter.
- Bizim tarafta kural: bağlaçlar küçük (ve, ile, veya, adına), kısaltmalar korunur (A.Ş.,
  Ltd., T.C., Dr., TCK, HD, İDD), parantez/tire sonrası büyük, yabancı adlarda I/ı çevrimi yok
  (Quick, HDI). `Uzmanlık Alanı` değerlerimiz bu kurala çekildi; 1.3'ten itibaren paket
  `Uzmanlık Alanı`'nı yazım farkında da yazar (04.09'daki "yazım bizim" ifadesi geçersiz).
  Mahkeme adında ise yazım bizde kalır (yalnız yazım farklıysa bizimki korunur, içerik farkı
  paket kazanır).
- Sorumlu avukat adlarında soyadı BÜYÜK yazımınız ("Rana Betül GÜMÜŞ") bizde dönüştürülmez;
  kart kutusundaki yazım bizimkidir, isim listesi olduğu gibi saklanır.

DB-2026-010'daki öteki açık havuzlar (kanonik yazım standardı getirdiğiniz serbest metin
alanları) bizde **sözlüksüz metin alanıdır**: değer olduğu gibi yazılır.

---

## 4. Cevap paketini nasıl yorumlayacaksınız

Uygulanan her paket için `03_VERI_TESLIM/cevap/<paket adı uzantısız>/` klasörü açılır.
CSV'ler noktalı virgül ayraçlı ve UTF-8'dir; Türkçe Excel'de doğrudan açılır.

| Dosya | Ne söyler | Nasıl kullanılır |
| --- | --- | --- |
| `eslesme_<paket>.csv` | Ana sayfadaki **her** satır için: `sistem_no; dosya_no; case_id; tracking_no; klasor_no_2; tku_no; case_party_id; durum; sebep` | `durum = ESLESTI` → bizde kart numarası `case_id`, ofis numarası `tracking_no`. `durum = ESLESMEDI` → `sebep` sütununa bakın (aşağıda). Talep #9'un cevabıdır; kendi eşleme tablonuzu buradan kurun |
| `ozet_<paket>.txt` | Tek ekranlık koşu özeti + son satırda kapı kararı | Sayılar sizin `DEGISIKLIK_OZETI`'nizle tutuyor mu diye bakın |
| `satir-raporu_<zaman>.csv` | Yalnız sorunlu ya da bilgi satırı varsa: `satir_no; sistem_no; dosya_no; tur; sebep` | `tur = ATLANDI` beklenen sebep (kart yok / bizde olmayan SistemNo / belgeli aşama satırı korundu). `tur = HATA` insan işi (aşağıda). `tur = KORUNDU` (1.3): `Durum` istisnası, §3.3 — hata değil. `tur = MUVEKKIL_DEGISTI` (1.3): föy başka müvekkile bağlandı, eski taraf satırı bizde elle temizlenir — hata değil |
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
| `boşaltılmadı — …` | `(boş)` talimatı bu alanda geçersiz ya da sütunsuz | §3.4 |
| `status korundu (kullanıcı gg.aa.yyyy)` (KORUNDU) | Kesim tarihinden sonra bizde kullanıcı `Durum`u değiştirmiş; paketin değeri yazılmadı | Bir şey yapmanız gerekmez; bir sonraki kesimde master'ınızı bizimkiyle hizalayın (§3.3) |
| `belgeli aşama satırı korundu (…)` (ATLANDI) | O aşama satırı bizde belgeye/UYAP kaydına dayanıyor; paket farkı yazılmadı | Farkı `sebep`ten okuyun; belge haklıysa master'ı düzeltin (§3.5) |
| `kök/müvekkil çelişkisi: …` (HATA) | `Dosya No` kökü bir sigortayı gösterirken `Müvekkil` hücresinde başka sigorta yazıyor; satır hiçbir karta yazılmadı | Kök ya da müvekkil hücresini düzeltin; grup şirketi/devir ise bize bildirin |
| `müvekkil değişti: eski → yeni` (MUVEKKIL_DEGISTI) | Föy yeni müvekkile bağlandı, eski taraf satırı yerinde | Bir şey yapmanız gerekmez |

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
| Büyük/küçük harf, aksan, boşluk farkı — başlıkta, kapalı liste değerinde **ve taraf sütunlarında** (`Müvekkil`, `Karşı Taraf`, `Sigortalı`, `Davalı İdare`) | SERBEST | Yutulur: taraf satırları yalnız eklenir, yazım farkı değişiklik üretmez (§3.2). DB-2026-008 (İlk Harf Büyük) taraf sütunlarında bu sınıftadır — ama bizdeki eski yazım da kendiliğinden düzelmez; bu yüzden `Yazim_Standardi` haritasını **istiyoruz** (§3.8). Sözlük/metin alanlarında (`Dava Konusu`, `Son Durum`, `Uzmanlık Alanı`) yazım farkı **değişiklik sayılır** ve paket kazanır; toplu bir yazım turu 10.000 hücre eşiğini aşarsa paket insan onayına düşer — sorun değil, beklenen yol (§1) |
| DB-2026-008 kapsamının `Sigortalı`, `Davalı İdare`, `Yerel Mahkeme`, `İstinaf Mahkemesi`, `Temyiz Mahkemesi` sütunlarına genişletilmesi | SERBEST (**ricamız**, 1.3) | Bildirim gerekmez; §3.8'deki yazım kuralıyla gelsin. Mahkeme adında yalnız yazım farkı varsa bizimki kalır |
| `DEGISIKLIK_OZETI`'ne "Teslim türü" ve "Veri kesim tarihi" satırlarının eklenmesi | SERBEST (**beklenen**, 1.3) | Bildirim gerekmez; §3.3. Delta paketi tür satırı olmadan gelirse tam sayılır ve kaybolan sütunlar yüzünden incelemeye düşer |
| `Karar_Asamalari`'na `Başvuru Tarihi` sütunu | SERBEST (06.09'da eklediniz) | 1.3'ten itibaren okunur (§3.5) |
| Bildirimle gelen ek sayfalar (`Kaldirilan_Sutunlar`, `S37_Kanonik`, `Yazim_Standardi`) | SERBEST | Okunmaz, arşiv olarak kalabilir. `Yazim_Standardi`'nı artık **istiyoruz** (§3.8) — sistem okumaz, insan işler |

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
3. `DEGISIKLIK_OZETI`'nde üç satır: "Önceki teslim: <bir önceki dosyanın tam adı>" (ilk
   teslimde `—`), "Teslim türü: tam | delta", "Veri kesim tarihi: gg.aa.yyyy" (§3.3).
4. Delta paketse yalnız değişen föyler; `Karar_Asamalari` ve `Düzeltme_Logu` yalnız o föyler
   (§3.4).
5. Çok değerli hücrelerde ayraç `;`; tarihler `GG.AA.YYYY`; sayılar Türkçe biçim.
6. Kapalı listelerde (§3.8: `Müvekkil Tipi`, `Hizmet Türü`, `Olay Türü`, `Hükümdeki Rol`,
   `Karar Durumu`, `İddia Edilen Kusur`) yalnız bizde de olan değerler; karar durumu
   sütununa `Kapalı`/`Derdest` yazılmaz (§3.5); yeni değer için önce §6 bildirimi.
7. `Karar_Asamalari`'nda `Aşama = Önceki` satırlarını filtrelemeyin; `Başvuru Tarihi`
   sütunu doluysa okunur (§3.5).
8. `(boş)` talimatları `Düzeltme_Logu`'nda `Sütun` başlığı ya da `[Sütun Adı]` önekiyle.
9. Yapısal bir değişiklik varsa §6 bildirimi gönderildi ve "hazır" cevabı alındı.
10. Bir önceki paketin cevap klasörü okundu; `ESLESMEDI` ve `HATA` satırları ele alındı
    (`KORUNDU` ve `MUVEKKIL_DEGISTI` bilgi satırıdır, §4).

---

## 9. Makine-okur özet (asistanınız için)

```yaml
hukdok_teslim_spec:
  surum: "1.3"
  surum_tarihi: "2026-09-10"
  degisiklik_gecmisi:
    - {surum: "1.0", tarih: "2026-09-03", not: "ilk sürüm"}
    - {surum: "1.1", tarih: "2026-09-04", not: "DB-2026-001…010 (REV-2) + cevabımız işlendi; Müvekkil Tipi/Hizmet Türü okunuyor; kapalı liste envanteri"}
    - {surum: "1.2", tarih: "2026-09-05", not: "04.09 paketinin 54 sütununun tamamı okunuyor (47 alan / 66 yazım); föy düzeyi kopya; değer havuzları paketten dolduruldu"}
    - {surum: "1.3", tarih: "2026-09-10", not: "DEGISIKLIK_OZETI üç satır (önceki teslim · teslim türü · veri kesim tarihi); delta teslim; Karar_Asamalari Başvuru Tarihi + aşama satırı güncelleme/koruma/ikinci tur; Kapalı/Derdest karar durumu değil; Durum kesim-sonrası koruma (KORUNDU); karar durumu havuzları 27/8/4/2; DB-008 genişletme + Yazim_Standardi isteği"}
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
    okunan_alan_sayisi: 47                # 10.09.2026'da çalışan sistemden sayıldı
    okunan_baslik_yazim_sayisi: 66
    okunan_baslik:            # aynı satırdaki yazımlar aynı alandır
      - ["SistemNo", "Sistem No"]
      - ["Dosya No", "DosyaNo", "Klasör No.2"]
      - ["Klasör No", "TKU", "TKU No", "TKU No."]
      - ["Hasar No", "Hasar Numarası"]
      - ["Hukuk No"]
      - ["Arabuluculuk Numarası"]
      - ["Dosya - Föy Bilgileri", "Föy Id", "MKO Id"]
      - ["MüvekkilNo", "Müvekkil No"]
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
      - ["Eski Dosya No", "Eski Esas No"]
      - ["İstinaf Mahkeme Başvuru Tar.", "İstinaf Mahkeme Başvuru Tarihi", "İstinaf Başvuru Tarihi"]
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
      - ["Para Birimi TL", "Para Birimi"]
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
    taraf_sutunlari_harf_duyarsiz: true   # Müvekkil/Karşı Taraf/Sigortalı/Davalı İdare: taraf satırı yalnız eklenir, yazım farkı değişiklik üretmez
    metin_alanlari_ham_karsilastirma: true   # Dava Konusu/Son Durum/Uzmanlık Alanı: yazım farkı değişiklik sayılır, paket kazanır; mahkeme adı istisna (yazım bizde)
    esik_sayimi: "kart hücresi bazında; tarih/tutar biçim farkı değişiklik üretmez"
  kapali_listeler:                    # §3.8 — bizdeki değer havuzları (10.09.2026, çalışan sistemden)
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
      buro_durumu_karar_degil: ["Kapalı", "Derdest"]   # yazmayın: künyeli satır durumsuz yazılır + şerh, künyesiz satır yazılmaz
      yerel: ["Açılmamış Sayılması (HMK 150. Md)", "Adli Para Cezası", "Anlaşma", "Anlaşmama", "Beraat",
              "Birleştirme", "Düşme Kararı", "Hapis Cezası", "Hapis Cezasının Paraya Çevrilmesi",
              "Hükmün Açıklanmasının Geri Bırakılması (HAGB)", "İflas", "Kabul", "Kabul/Kısmen",
              "Karar Verilmesine Yer Olmadığına (HMK 331 Md.)", "Kovuşturmaya Yer Olmadığına (KYOK)",
              "Red/Arabuluculuk Ön Şart", "Red/Dilekçenin Reddi", "Red/Esastan", "Red/Feragat", "Red/Görev",
              "Red/Husumet", "Red/İdari Merciye Tevdi", "Red/MSK Kararı Gereği", "Red/Usulden", "Red/Yargı Yolu",
              "Red/Yetkisizlik", "Red/Zamanaşımı"]                                                    # 27
      istinaf: ["Kaldırma", "Kaldırma/Yeniden Hüküm", "Başvuru Ret", "Düzeltilerek Karar Verildi",
                "Düzeltilerek Kabul Edildi", "Düzeltilerek Reddine", "Kısmen Kabul",
                "Davacı İstinaf Talebinin Kabulü"]                                                    # 8
      temyiz: ["Bozma", "Onama", "Düzelterek Onama", "Kısmen Onama/Kısmen Bozma"]                     # 4
      karar_duzeltme: ["Karar Düzeltme Kabul", "Karar Düzeltme Ret"]                                  # 2
      havuza_girmeyen: "İstinaf 'Karar' (74 föy) — anlamı belirsiz, yazılı bildirim bekleniyor"
    basvuran_taraf:
      uygulama: "tanınmayan yazım boş bırakılır"
      degerler: ["Davacı", "Davalı", "Her İki Taraf"]
  degisiklik_ozeti:                   # §3.3 — üç satır; etiket:değer aynı hücrede ya da sağdaki ilk dolu hücre; ilk 200 satır
    onceki_teslim:
      etiket: "Önceki teslim"
      deger: "önceki dosya adı, birebir; '·' sonrası yok sayılır"
      ilk_teslim: "'—' veya 'yok' YALNIZ bizde uygulanmış teslim yokken (zincir başlangıcı); sonra zincir eksik → inceleme"
      zincir_baslangici: "HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx"
      sayfa_yoksa: "zincir bilinmiyor; paket bu açıdan durdurulmaz"
    teslim_turu:
      etiket: "Teslim türü"
      degerler: ["tam", "delta"]
      varsayilan: "tam (satır yok/boş/—/tanınmayan → tam; tanınmayanda uyarı)"
      fark: "tam: kaybolan sütun = yapı değişikliği → inceleme; delta: kaybolan sütun = bilgi. Yeni sütun ve kaybolan sayfa her türde inceleme"
    veri_kesim_tarihi:
      etiket: "Veri kesim tarihi"
      deger: "gg.aa.yyyy | yyyy-aa-gg | Excel tarih hücresi"
      yoksa: "paket adındaki YYYY-AA-GG kesim günü sayılır + uyarı (gerçek kesimden geç eşik)"
      ne_ise_yarar: "Durum istisnası: kesim gününden itibaren bizde kullanıcı imzalı Durum değişikliği varsa paket Durum'u yazmaz → satır raporu tur=KORUNDU (hata değil, eşiği etkilemez)"
  delta_teslim:                       # §3.4
    - "yalnız değişen föyler; SistemNo + Dosya No her satırda"
    - "Karar_Asamalari ve Düzeltme_Logu yalnız ilgili föylerin satırları; gelmeyen föye/aşamaya dokunulmaz"
    - "zincir kesintisiz: delta bir öncekinin adını yazar, tam paket de kendinden önceki delta'nın"
    - "tam paket aylık (mutabakat), Teslim türü: tam + tam envanter"
    - "delta'da eksik föy silindi anlamına gelmez; belge sayımı/zincir/eşikler aynen geçerli"
  duzeltme_logu:
    sutunlar: ["SistemNo", "Sütun", "Eski Değer", "Yeni Değer", "Gerekçe", "Tarih"]
    bosaltma_isareti: "(boş)"
    sutun_adi: "ayrı 'Sütun' başlığı (doluysa önce o); yoksa Gerekçe başında [Sütun Adı] öneki; ikisi de yoksa satır işlenmez"
    bosaltilamayan: ["Karar No", "Karar Tarihi", "İstinaf Mahkemesi Başvuran Taraf", "Yerel Mahkeme", "Dava Türü Alt Kırılımı / Uzmanlık Alanı"]
  karar_asamalari:
    sutunlar: ["SistemNo", "AsamaNo", "Aşama", "Mahkeme", "Esas No", "Karar No",
               "Karar Tarihi", "Karar Durumu", "Tebliğ Tarihi", "Başvuru Tarihi", "Başvuran Taraf", "Güven", "Açıklama"]
    basvuru_tarihi: "aşama satırından; İstinaf'ta boşsa Sheet 'İstinaf Mahkeme Başvuru Tar.' yedek; Temyiz yalnız aşama sayfası; sütun yoksa alan boş"
    asama_degerleri: ["Yerel", "İstinaf", "Temyiz", "Karar Düzeltme"]
    asama_onceki: "'Önceki' kabul edilir: karar aşaması değil, Esas No kartın esas tarihçesine önceki esas olarak yazılır — bu satırları GÖNDERİN (DB-2026-004)"
    taninmayan_asama: "satır sessizce atlanır"
    buro_durumu: "Kapalı/Derdest karar durumu değil — yazmayın; künyeli satır durumsuz + şerh, künyesiz satır yazılmaz; kardeş uzlaşısında boş hücre gibi"
    mevcut_satir_kurali:            # 1.3 — aşama satırı güncelleme
      birebir_ayni: "hiçbir şey yazılmaz (idempotent)"
      konum_bos: "yeni satır eklenir"
      belgeli_uyap: "korunur; satır raporu ATLANDI 'belgeli aşama satırı korundu'"
      ikinci_tur: "Esas No VE Karar Tarihi farklı, dördü dolu, mevcut daha eski → yeni satır sira+1, mevcut kalır"
      aksi: "yerinde güncellenir (paket kaynaklı ya da elle girilmiş fark etmez), tarihçeli"
      silme: "yok — paket taşımasa da bizdeki satır kalır"
    kardes_foy: "aynı aşamada farklı DOLU künye → aşama yazılmaz + çelişki raporu; boş hücre çelişki değil"
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
    alan_degisikligi_azami: 10000       # kart hücresi bazında
    ilk_teslim: "daima insan onayı"
    zincir: "önceki teslim uygulanmış olmalı (ilk teslimde '—' başlangıçtır)"
    yapi_farki: "yeni sütun / kaybolan sayfa her türde inceleme; kaybolan sütun yalnız tam pakette"
    belge_sayimi: "koşu öncesi/sonrası denk değilse koşu geri alınır"
  cevap_dosyalari:
    eslesme_csv: ["sistem_no", "dosya_no", "case_id", "tracking_no", "klasor_no_2",
                  "tku_no", "case_party_id", "durum", "sebep"]
    satir_raporu_csv: ["satir_no", "sistem_no", "dosya_no", "tur", "sebep"]
    satir_raporu_tur:
      ATLANDI: "eşleşmedi / bizde olmayan SistemNo / belgeli aşama satırı korundu"
      HATA: "tanınmayan değer, çok değer, kök/müvekkil çelişkisi, boş Dosya No, belirsiz eşleşme"
      KORUNDU: "Durum istisnası (§3.3) — hata değil"
      MUVEKKIL_DEGISTI: "föy başka müvekkile bağlandı — hata değil; eski taraf satırı bizde elle temizlenir"
    celiski_csv: ["kume", "kume_anahtari", "alan", "degerler"]
    havuz_farki_csv: ["havuz", "liste", "yon", "deger"]
    ozet_txt: "sayılar (aşama eklenen/güncellenen/ikinci tur/belgeli korunan, büro durumu atlanan, status korunan …) + kapı kararı"
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
              "aksan/boşluk/büyük-küçük (başlık, kapalı liste değeri, taraf sütunları)",
              "bildirim ek sayfaları (Kaldirilan_Sutunlar, S37_Kanonik, Yazim_Standardi)",
              "DEGISIKLIK_OZETI'ne Teslim türü + Veri kesim tarihi satırları (beklenen)",
              "Karar_Asamalari'na Başvuru Tarihi sütunu (okunur)",
              "DB-2026-008'in Sigortalı/Davalı İdare/mahkeme sütunlarına genişletilmesi (ricamız)"]
  yazim_standardi:                    # §3.8, 1.3
    yazim_standardi_sayfasi: "İSTENİYOR (eski → yeni yazım / sütun); sistem okumaz, insan işler"
    db_008_genisletme: ["Sigortalı", "Davalı İdare", "Yerel Mahkeme", "İstinaf Mahkemesi", "Temyiz Mahkemesi"]
    uzmanlik_alani: "1.3'ten itibaren paket yazım farkında da yazar"
    mahkeme_adi: "yazım bizde — yalnız yazım farkıysa bizimki kalır, içerik farkı paket kazanır"
    avukat_soyadi: "dönüştürülmez; kart kutusu bizim yazımımız"
  bildirim_kanali: "e-posta veya WhatsApp, §6 şablonu, teslimden bir döngü önce; numara dizisi DB-2026-011'den devam eder; cevabımız gelmeden yeni biçimi göndermeyin"
```

---

*Sorular için HukuDok ekibine yazın. Bu belgenin güncel sürümü her yapısal değişiklikte
yeniden gönderilir; sürüm numarası başlıktadır.*
