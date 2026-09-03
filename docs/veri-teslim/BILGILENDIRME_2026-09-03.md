# HUKDOK Veri Teslim Hattı — Veri Ekibi Bilgilendirmesi

**Tarih:** 03.09.2026 · **Gönderen:** HukuDok ekibi (Hanyaloğlu Acar + LexisBio) ·
**Muhatap:** MicroKolayOfis master'ını hazırlayan veri ekibi · **Sürüm:** 1.0

> Bu belge yapılandırılmış yazıldı: tablolar, birebir yazımlar ve sondaki makine-okur özet
> (§9), kendi yapay zekâ asistanınıza "teslim öncesi kontrol" ve "cevap paketi yorumlama"
> görevi olarak doğrudan verilebilir. Buradaki her kural çalışan sistemden okunarak yazıldı;
> tahmin ya da niyet değil, bugün geçerli davranıştır.

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

**Sistemin bugün okuduğu başlıklar** (18.08 paketindeki 68 sütunun 37'si; aşağıda kabul
edilen yazımlarıyla, bazı alanlar için birden çok yazım tanınır):

| Alan grubu | Kabul edilen başlıklar |
| --- | --- |
| Kimlik (zorunlu) | `SistemNo` / `Sistem No` · `Dosya No` / `DosyaNo` / `Klasör No.2` |
| Kimlik (isteğe bağlı) | `Klasör No` / `TKU` / `TKU No` · `Hasar No` / `Hasar Numarası` · `Hukuk No` · `Arabuluculuk Numarası` |
| Sınıflandırma | `Ana Tür` · `Durum` · `Dava Konusu` · `Dava Türü Alt Kırılımı` / `Uzmanlık Alanı` · `Buro Özel Türü` · `Son Durum` |
| Künye | `Yerel Mahkeme` · `Esas` · `Karar No` · `Karar Tarihi` · `İstinaf Mahkemesi Başvuran Taraf` |
| Tarihler | `Dava Tarihi` · `İş Kabul Tarihi` · `Arşiv Tarihi` · `Arabuluculuk Karar Tarihi` |
| Para | `Dava Değeri TL` / `Dava Değeri` · `Manevi Dava Değeri TL` / `Manevi Dava Değeri` · `Islah Tutarı` / `İslah Tutarı` · `Hükmedilen Maddi` · `Hükmedilen Manevi` · `Hükmedilen Toplam` |
| Taraflar | `Müvekkil` · `Karşı Taraf` · `Sigortalı` · `Davalı İdare` · `Taraf Sıfatı` · `Sorumlu Avukatlar` / `Sorumlu Avukat` |
| Klinik kodlama | `Tıbbi Süreç` · `Tıbbi Olay` · `İddia Edilen Kusur` · `Hastada Oluşan Zarar` · `Uygulanan Yöntem` |
| Belgeleme olayı | `Olay Türü` · `Hükümdeki Rol` |

**Okunmayan 31 sütun ve nedeni** (paketten çıkarmanız gerekmez; olduğu gibi kalabilir):

| Sütunlar | Neden okunmuyor |
| --- | --- |
| `Yerel Mahkeme Karar Tarihi`, `Yerel Mahkeme Tebliğ Tarihi`, `Yerel Mahkeme Karar Durumu`, `Yerel Mahkeme Kararı Açıklaması`, `İstinaf Mahkemesi`, `İstinaf Mahkeme Esas`, `İstinaf Mahkeme Başvuru Tar.`, `İstinaf Mahkeme Karar No`, `İstinaf Mahkeme Karar Tar.`, `İstinaf Karar Durumu`, `İstinaf Karar Açıklamalar`, `Temyiz Mahkemesi`, `Temyiz_Esas_No`, `Temyiz Karar Tarihi`, `Yargıtay Onama Durumu`, `Karar Düzeltme Kararı Durumu`, `Eski Dosya No` (17) | **Yargı zinciri `Karar_Asamalari` sayfasından okunur.** `Sheet` yalnız güncel aşamayı yatay taşıyor; bizde karar künyesinin tek yazma yolu aşama tarihçesidir, aynı bilgiyi iki kaynaktan yazmak çelişki üretirdi. `Eski Dosya No` da aşama sayfasındaki önceki esas satırlarından gelir. Bu sütunları `Sheet`'te tutmaya devam edin; kardeş föy çelişki raporu bunlardan yararlanır |
| `Dosya - Föy Bilgileri`, `Para Birimi TL`, `Bilirkişi Rapor Sonuç`, `Poliçe Başlangıç Tarihi`, `Ek Alt Kırılım 1`–`4`, `Arabuluculuk Merkezi`, `Soruşturma İtiraz Mahkemesi` (10) | **Sizin sözlüğünüzün "ölü sütun" listesi** (24.08 veri sözlüğü §10: doluluk 0 ya da tek değer, "modelinize taşımayın") |
| `Ek Alt Kırılım` (1) | Sizin uyarınız: dosya açılış etiketi, karardan okunmamış, kanıt değil |
| `MüvekkilNo` (1) | 12.08 mutabakatı: sisteme aktarılmayacak; cari kartlar isim + vergi/TC ile kurulur |
| `Müvekkil Tipi`, `Hizmet Türü` (2) | **Bekleyen alanlar.** Föy (müvekkil) düzeyi bilgi; bizde kartın tek kutusuna sığmıyor (aynı davada doktor föyü "Takip", sigorta föyü "Lexis Rapor"). Taraf düzeyine taşınma kararı verildi, henüz uygulanmadı. Uygulanınca bildireceğiz; o zamana kadar bu iki sütun okunmaz |

Yeni bir sütun eklediğinizde de aynı kural geçerlidir: **tanınmayan başlık sessizce
atlanır**, paket hata vermeden işlenir, ama o sütundaki bilgi bize ulaşmaz. Sütunun
işlenmesi için önce §6 bildirimi, sonra bizim tarafta alan + eşleme açılması gerekir.

**Hücre değerleri:**

| Tür | Beklenen | Notlar |
| --- | --- | --- |
| Tarih | Excel tarih hücresi ya da `GG.AA.YYYY` metni | `01.01.1900`, 1900 ve öncesi, gelecek tarihler **yer tutucu** sayılır ve boş yazılır (uyarı düşer, satır düşmez) |
| Sayı | Excel sayı hücresi ya da Türkçe yazım (`12.500,00`) | `NULL ≠ 0` kuralı korunur: boş = bilinmiyor, `0` = hükmedilmedi |
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

Beklenen başlıklar: `SistemNo`, `AsamaNo` / `Aşama No`, `Aşama` (`Yerel`, `İstinaf`,
`Temyiz`, `Karar Düzeltme`), `Mahkeme`, `Esas No`, `Karar No`, `Karar Tarihi`,
`Karar Durumu`, `Tebliğ Tarihi`, `Başvuran Taraf`, `Güven`, `Açıklama`. Bugünkü 21 sütunlu
sayfanız uyumludur; fazladan sütun sorun değildir.

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
`Olay Türü`, `Hükümdeki Rol`. Diğer havuzlar atlanır.

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
| `belirsiz eşleşme` (HATA) | Aynı Dosya No bizde 2+ kartla eşleşiyor, esas no da ayırmadı | Satıra `Esas` ve `Ana Tür` ekleyin; hâlâ ayrılmıyorsa bize bildirin |
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
| §3.2'deki 40 başlıktan birinin **kelime** değişikliği | **KIRICI (sessiz)** | Hata yok; alan "bu teslimde yok" sayılır, o sütundaki güncellemeler hiç işlenmez |
| Sayfa adlarının değişmesi (`Karar_Asamalari`, `Düzeltme_Logu`, `DEGER_HAVUZLARI`) | **KIRICI (sessiz)** | Sayfa atlanır, içeriği işlenmez |
| Çok değer ayracının değişmesi (`;` yerine `,` / `/`) | **KIRICI** | Hücre tek değer sanılır; kapalı listede tanınmaz, yazılmaz |
| Tarih yazımının değişmesi (`2026-08-18`, `18/08/26`) | **KIRICI** | Çözülemeyen tarih boş yazılır |
| Sayı yazımının değişmesi (`12,500.00` İngiliz biçimi) | **KIRICI** | Yanlış tutar okunabilir |
| Dosya biçimi `.xlsm` / `.csv`, ad kalıbı dışı | **KIRICI** | Dosya yok sayılır ya da reddedilir |
| Kapalı listeye **yeni değer** (`İddia Edilen Kusur`, karar durumları, `Olay Türü`, `Hükümdeki Rol`) | **BİLDİRİLMELİ** | Değer yazılmaz, rapora düşer; biz listeye ekleyince sonraki pakette işlenir |
| `Ana Tür` / `Durum` / `Son Durum` / `Hizmet Türü`'ne yeni değer | **BİLDİRİLMELİ** | Eşleme sözlüğümüzde yoksa satır hata verir ya da alan yazılmaz |
| **Yeni sütun** eklenmesi | **BİLDİRİLMELİ** | Sütun sessizce yok sayılır. Yeni bilgi taşıyorsa bizim tarafta alan + eşleme açılır; bildirimden sonra genelde bir teslim döngüsü sürer |
| Bir sütunun **kalıcı** kaldırılması | **BİLDİRİLMELİ** | Paket bozulmaz (alan korunur), ama "artık gelmiyor" bilgisini belgeleyelim |
| `Düzeltme_Logu`'na ayrı `Sütun` başlığı açılması | **BİLDİRİLMELİ (olumlu)** | Önek yerine başlık okunur; önceden haber verin ki doğrulayalım |
| Yeni sayfa eklenmesi | **BİLDİRİLMELİ** | Yok sayılır; işlenmesini istiyorsanız tanımlanmalı |
| Aşama adlarına yeni değer (`Yerel`/`İstinaf`/`Temyiz`/`Karar Düzeltme` dışında) | **BİLDİRİLMELİ** | Aşama yazılmaz |
| Sütun sırasının değişmesi | SERBEST | Ada göre okunur |
| Satır sayısı, satır sırası, yalnız değişen föylerin gönderilmesi | SERBEST | Partili teslim desteklenir |
| Boş hücreler | SERBEST | "Bu teslimde yok" sayılır, silmez |
| Okunmayan sayfaların içeriği (`SUTUN_SOZLUGU` vb.) | SERBEST | |
| Büyük/küçük harf, aksan, boşluk farkı (başlıkta ve kapalı liste değerinde) | SERBEST | Yutulur |

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

Her değişiklik için bir kayıt; alanların tamamı doldurulur:

```
DEĞİŞİKLİK BİLDİRİMİ
Bildirim no        : DB-2026-001
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
  "bildirim_no": "DB-2026-001",
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
5. Kapalı listelerde yalnız bizde de olan değerler; yeni değer için önce §6 bildirimi.
6. `(boş)` talimatları `Düzeltme_Logu`'nda `[Sütun Adı]` önekli.
7. Yapısal bir değişiklik varsa §6 bildirimi gönderildi ve "hazır" cevabı alındı.
8. Bir önceki paketin cevap klasörü okundu; `ESLESMEDI` ve `HATA` satırları ele alındı.

---

## 9. Makine-okur özet (asistanınız için)

```yaml
hukdok_teslim_spec:
  surum: "2026-09-03"
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
    tanimayan_sutun: "sessizce yok sayılır"
    bos_hucre: "bu teslimde yok; mevcut değer korunur"
    cok_deger_ayraci: ";"
    tarih: "Excel tarihi veya GG.AA.YYYY; 1900 ve öncesi + gelecek = yer tutucu → boş"
    sayi: "Excel sayısı veya Türkçe biçim (12.500,00)"
    yer_tutucu_metin: ["-", "--", "—", "?", "YOK", "BELİRSİZ", "BOŞ", "N/A", "NA"]
    null_sifir_farki: true
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
  kapsam_sayfalari:
    sutunlar: ["SistemNo", "Silinme Gerekçesi | Kapsam Dışı Gerekçesi | Gerekçe", "Tarih"]
    etki: "föy işaretlenir, silinmez"
  deger_havuzlari:
    baslik: ["Havuz / Sütun", "Değer"]
    karsilastirilan: ["İddia Edilen Kusur", "Yerel Mahkeme Karar Durumu", "İstinaf Karar Durumu",
                      "Yargıtay Onama Durumu", "Olay Türü", "Hükümdeki Rol"]
    taninmayan_deger: "yazılmaz; rapora düşer; listeye otomatik eklenmez"
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
             "okunan 40 başlıktan birinin kelime değişimi", "sayfa adı değişimi",
             "ayraç/tarih/sayı biçimi", "dosya biçimi"]
    bildirilmeli: ["yeni kapalı liste değeri", "Ana Tür/Durum/Son Durum yeni değer",
                   "yeni sütun", "kalıcı sütun kaldırma", "yeni sayfa", "yeni aşama adı"]
    serbest: ["sütun sırası", "satır sayısı/sırası", "boş hücre", "okunmayan sayfa içeriği",
              "aksan/boşluk/büyük-küçük"]
  bildirim_kanali: "e-posta veya WhatsApp, §6 şablonu, teslimden bir döngü önce"
```

---

*Sorular için HukuDok ekibine yazın. Bu belgenin güncel sürümü her yapısal değişiklikte
yeniden gönderilir; sürüm numarası başlıktadır.*
