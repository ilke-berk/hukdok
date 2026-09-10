# HUKDOK veri teslim sözleşmesi — veri ekibi için

**Sürüm:** 10.09.2026 (1.3 — 06.09 cevabınıza karşılık: eşik sayımı, `DEGISIKLIK_OZETI`'nin
üç satırı, delta teslim, karar durumu havuzları, sütun sahipliği, yazım standardı; 1.2:
08.09.2026 §1 klasörün yeri; 1.1: 04.09.2026; ilk sürüm 03.09.2026) ·
**Muhatap:** MicroKolayOfis master'ını temizleyen veri ekibi · **Karşı taraf:** HukuDok
(Hanyaloğlu Acar + LexisBio ortak sistemi)

Bu metin kısa sözleşmedir; sütun/sayfa/değer ayrıntıları ve makine-okur özet ayrı
bilgilendirme belgesindedir (`BILGILENDIRME_2026-09-03.md`, sürüm 1.2 — karar durumu
havuzları için bu metnin §6'sı günceldir, bilgilendirme belgesinin §3.8'i 04.09
fotoğrafıdır). 04.09.2026'daki Format Değişiklik Bildirimi REV-2 (DB-2026-001…010) ve
cevabımız her iki belgeye işlendi: `Müvekkil Tipi` ve `Hizmet Türü` sütunları artık okunur,
`İddia Edilen Kusur` listemiz dokuz değerle doludur. 05.09.2026 (bilgilendirme sürüm 1.2):
04.09 paketinin 54 sütununun **tamamı** okunur; dosyanızda değişiklik gerekmez.

**1.3'te değişenler (kısa):** §3 artık üç satır (Önceki teslim · Teslim türü · Veri kesim
tarihi); §4 delta teslim kuralları; §6 karar durumu havuzları yenilendi ve "Kapalı/Derdest
yazılmaz"; §7 eşik sayımı hücre bazında + `Durum` istisnası; §10 sütun sahipliği; §11 yazım
standardı (DB-008 genişletme + `Yazim_Standardi` isteği); `Karar_Asamalari`'nda `Başvuru
Tarihi` okunur; Dosya No kökü müvekkil kimliği olarak kullanılır.

Bu metin, teslim paketinin **nasıl bırakılacağını** ve karşılığında **ne alınacağını**
anlatır. Teslim artık WhatsApp/e-posta ile değil, paylaşılan SharePoint klasörüne bırakılarak
yapılır; sistem paketi geceleri kendiliğinden işler. WhatsApp yalnız "dosyayı bıraktım"
haberi için kalır.

---

## 1. Nereye, hangi adla

- **Klasör:** Hanyaloğlu Acar SharePoint'indeki **`hukdok_arsiv`** site'ı → **Belgeler**
  kütüphanesi → `03_VERI_TESLIM` klasörünün `gelen` alt klasörü (`03_VERI_TESLIM/gelen/`).
  Klasör size kuruluş hesabınızla (`@hanyaloglu-acar.av.tr`) paylaşılır; SharePoint /
  OneDrive'da **"Benimle paylaşılanlar"** altında görünür, ayrı bir davet ya da misafir hesabı
  gerekmez. Doğrudan bağlantıyı HukuDok tarafı cevap e-postasında iletir. (Cevap klasörü
  `03_VERI_TESLIM/cevap/` de aynı yerdedir — §8.)
- **Dosya adı:** `HUKDOK_TESLIM_` ile başlayan ve `.xlsx` ile biten bir ad; örneğin
  `HUKDOK_TESLIM_PAKETI_2026-09-15.xlsx`. Büyük/küçük harf fark etmez. Bu kalıba uymayan
  dosyalar **görmezden gelinir** (hata da vermez). Ad içindeki `YYYY-AA-GG` tarihi §3.3'teki
  yedek kuralda kullanılır — teslim gününü yazın.
- **Aynı dosyayı iki kez bırakırsanız** sorun olmaz: içerik aynıysa ikinci kopya "yinelenen"
  olarak kaydedilir ve işlenmez. İçeriği değiştirip aynı adla yeniden yüklerseniz **yeni bir
  teslim** sayılır.
- Her teslim ayrı bir dosyadır; önceki teslimin dosyasını silmenize gerek yok.

## 2. Dosyanın içinde ne olmalı

| Sayfa adı | Zorunlu mu | Ne olmalı |
| --- | --- | --- |
| `Sheet` | **Zorunlu** | Ana veri sayfası: föy başına bir satır. Sütunlar **ada göre** okunur, sıra serbesttir; sütun adları önceki teslimlerdeki ve bildirdiğiniz (DB-2026) yazımlarla aynı kalır — adı değişen sütun hata vermez, "bu teslimde yok" sayılır. `SistemNo` ve `Dosya No` sütunları **mutlaka** bulunmalı — ikisi olmadan dosya reddedilir. Okunan başlıkların tam listesi bilgilendirme belgesi §3.2'dedir. |
| `DEGISIKLIK_OZETI` | İsteğe bağlı — **her teslime ekleyin** | Üç etiketli satır: **"Önceki teslim"**, **"Teslim türü"**, **"Veri kesim tarihi"** (§3). Sayfa yoksa dosya reddedilmez; ama zincir kontrolü **yapılamaz** ("zincir bilinmiyor" notu düşer, paket öteki eşiklerin içindeyse yine otomatik uygulanabilir), teslim türü **tam** sayılır ve kesim tarihi paket adından alınır. Atlanan teslimin yakalanmasını istiyorsanız bu sayfayı hiç eksik bırakmayın. |
| `Karar_Asamalari` | İsteğe bağlı | Föy başına yargı aşamaları (Yerel → İstinaf → Temyiz → Karar Düzeltme). Yoksa aşama bilgisi yazılmaz, hata değildir. 06.09'da eklediğiniz **`Başvuru Tarihi`** sütunu okunur (kanun yoluna başvuru tarihi; İstinaf satırında boşsa ana sayfadaki "İstinaf Mahkeme Başvuru Tar." yedek kaynaktır). `Aşama = Önceki` satırları eski esas numarası olarak işlenir. Karar durumu hücresine büro dosya durumu (`Kapalı`, `Derdest`) **yazmayın** — §6. |
| `Düzeltme_Logu` | İsteğe bağlı | Hücre düzeltme günlüğü: `SistemNo`, `Sütun`, `Eski Değer`, `Yeni Değer`, `Gerekçe`, `Tarih`. Gerekçe bizde o alanın değişiklik tarihçesine işlenir. Değişen sütunun adı ya ayrı bir `Sütun` başlığında (06.09'da önerdiğiniz biçim — kabul) ya da gerekçenin başında köşeli parantezle (`[Hükmedilen Manevi] Outlook otomasyonu parti-2`) verilir; ikisi de yoksa satır işlenmez. |
| `DEGER_HAVUZLARI` | İsteğe bağlı | Kapalı liste değerleri: "Havuz / Sütun" ve "Değer" sütunları (bugünkü paketteki düzen). Bizim listelerimizle karşılaştırılır; fark varsa cevap klasörüne rapor düşer (§6). |
| `Silinen_Föyler`, `Kapsam_Dışı` | İsteğe bağlı | Kapsamdan çıkardığınız föyler: `SistemNo` + gerekçe (`Silinme Gerekçesi` / `Kapsam Dışı Gerekçesi`) + `Tarih`. Bkz. §5. |
| `SUTUN_SOZLUGU`, `SINIFLANDIRMA_MODELI`, `HUKDOK_TALEPLERI`, `Kaldirilan_Sutunlar`, `S37_Kanonik`, `Yazim_Standardi` | İsteğe bağlı | Okunmaz; paketle gelmesi sorun değildir. (`Yazim_Standardi`'nı artık **istiyoruz** — §11; okunmaması "gelmesin" demek değildir, insan okur.) |

Sayfa adları yukarıdaki yazımla birebir olmalıdır (`Sheet`, `DEGISIKLIK_OZETI`,
`Karar_Asamalari`, `Düzeltme_Logu`, `DEGER_HAVUZLARI`). Kapsam sayfalarında aksan/alt çizgi
farkı tolere edilir (`Silinen_Föyler` = `Silinen Foyler`), diğerlerinde edilmez.

## 3. `DEGISIKLIK_OZETI` — üç satır

Sistem bu sayfada üç etiketi arar. Hepsi için aynı yazım kuralı geçerlidir: etiket ile değer
**aynı hücrede** iki noktayla (`Önceki teslim: …`) ya da etiket bir hücrede, değer sağındaki
ilk dolu hücrede. Etiketlerde büyük/küçük harf, aksan ve boşluk farkı yutulur. Satırlar
sayfanın ilk 200 satırında olmalıdır.

### 3.1 "Önceki teslim" — zincir

- Değer bir önceki paketin **dosya adıdır**: `Önceki teslim: HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx`.
- Dosya adından sonra ` · 8.409 satır × 68 sütun` gibi bir ek yazılabilir; nokta işaretinden
  (`·`) sonrası dikkate alınmaz.
- **Yalnız ilk teslimde** `—` ya da `yok` yazın (boş bırakmak da olur). Bizde uygulanmış
  hiçbir teslim yokken bu değer "zincir başlangıcı" sayılır ve ihlal üretmez (ilk teslim
  zaten insan onayıyla uygulanır, §7). Bizde uygulanmış bir teslim **varken** `—` yazarsanız
  paket "zincir eksik" ile insan incelemesine düşer — ikinci teslimden itibaren daima ad yazın.
- Zincirin başlangıcı: prod'da ilk uygulanacak paket `HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx`'tir;
  sonraki teslimde "Önceki teslim" olarak bu adı yazın. 31.08 paketi bize hiç ulaşmadı,
  zincirde yer almaz.

Neden önemli: sistem, "önceki teslim" dediğiniz dosyanın gerçekten bizde uygulanmış olduğunu
kontrol eder (**zincir kontrolü**). Bir teslim atlanmışsa ya da ad yanlış yazılmışsa paket
otomatik uygulanmaz, insan incelemesine düşer. Ad, bıraktığınız dosyanın adıyla birebir
olmalıdır. Bu kontrol yalnız sayfa **varsa** çalışır: sayfa hiç yoksa sistem zinciri
denetleyemez ve paketi bu açıdan durdurmaz (§2 tablosu) — sayfayı eksik bırakmak zincir
güvencesinden vazgeçmek demektir.

### 3.2 "Teslim türü" — tam | delta

- `Teslim türü: tam` (varsayılan) ya da `Teslim türü: delta`. Satır yoksa, boşsa ya da `—`
  ise **tam** sayılır; tanınmayan bir değer de tam sayılır (uyarı düşer, paket reddedilmez).
- **Delta** = yalnız değişen föyler (ve gerekirse yalnız değişen sütunlar). Kuralları §4'tedir.
- Neden önemli: tam pakette bir sütunun **kaybolması** yapı değişikliği sayılır ve paketi
  incelemeye düşürür; delta pakette kaybolan sütun yalnız **bilgi** olarak raporlanır. Yeni
  bir sütunun belirmesi ve bir sayfanın kaybolması her iki türde de incelemeye düşürür.

### 3.3 "Veri kesim tarihi" — `Durum` istisnasının eşiği

- `Veri kesim tarihi: 30.07.2026` (gün.ay.yıl ya da `2026-07-30`). Master'ınızın bu paketteki
  fotoğrafının **hangi güne** ait olduğunu yazın — 06.09 cevabınızdaki "kesim tarihimiz
  30.07.2026" bilgisinin paket içindeki yeridir.
- Satır **zorunludur**: yoksa sistem dosya adındaki tarihi (`…_2026-09-04.xlsx` → 04.09.2026)
  kesim günü sayar ve uyarı düşer. Bu, gerçek kesimden **geç** bir eşiktir: aradaki günlerde
  bizde yapılan `Durum` değişiklikleri korunmaz (aşağıda). Satırı yazmak sizin lehinizedir.
- Ne işe yarar (§7 ve §10): `Durum` (derdest/arşiv) sütununda **bizim kaydımız esastır**
  (06.09 §1.2'de siz de öyle dediniz). Kesim gününden itibaren bizde bir kullanıcının
  değiştirdiği `Durum`, paketin eski değeriyle **geri yazılmaz**; rapora "korundu" olarak düşer.
  Kesim tarihi hatalı ileri yazılırsa koruma gereksiz yere devreye girer, geri yazılırsa
  bizdeki değişiklik ezilir — gerçek fotoğraf tarihini yazın.

## 4. Partili (delta) teslim ve alan boşaltma

- **Paket parça parça gelebilir** (06.09 §11.4'teki isteğiniz — kabul). Ana sayfada bir sütun
  hiç yoksa ya da bir hücre boşsa bu "bu teslimde bu bilgi yok" demektir; bizdeki mevcut değer
  **silinmez**, olduğu gibi kalır.
- **Delta paket kuralları** (§11.4'teki üç sorunun cevabı):
  1. Ana sayfada **yalnız değişen föyler** (`SistemNo` + `Dosya No` her satırda şart);
     `Karar_Asamalari` ve `Düzeltme_Logu` da **yalnız ilgili föylerin** satırlarını taşır —
     gelmeyen föye/aşamaya dokunulmaz.
  2. Zincir (`Önceki teslim`) delta paketlerde de **kesintisizdir**: her delta bir öncekinin
     adını yazar, tam paket de kendinden önceki delta'nın adını.
  3. **Tam paket aylık** gelir (mutabakat); aylık tam paket `Teslim türü: tam` ile gelir ve
     envanterin tamamını taşır. Delta'da eksik föy "silindi" anlamına gelmez.
  4. `DEGISIKLIK_OZETI`'nde `Teslim türü: delta` satırı **şart** (§3.2); yoksa paket tam
     sayılır ve kaybolan sütunlar yüzünden incelemeye düşer.
  5. Belge sayımı denkliği, zincir ve öteki eşikler (§7) delta'da da aynen geçerlidir.
- **Bir alanı bilerek boşaltmak** istiyorsanız bunu açıkça `Düzeltme_Logu`'nda söylersiniz:
  ilgili satırın `Yeni Değer` hücresine parantezli olarak **`(boş)`** yazın ve gerekçeyi
  belirtin. Sistem üç şartı birlikte arar: log `(boş)` diyor **ve** ana sayfada o hücre
  gerçekten boş **ve** bizde o alan dolu. Üçü de sağlanınca alan boşaltılır ve gerekçe
  tarihçeye işlenir. Parantezsiz `boş` bir metin değeridir, boşaltma talimatı değildir.
- Boşaltılamayan alanlar: karar numarası ve karar tarihi (aşama fotoğrafından beslenir),
  mahkeme adı (yazım bizim, §10) ve uzmanlık alanı (paket yazar ama silmez). Bunlar için gelen
  `(boş)` talimatı uygulanmaz, raporda "boşaltılmadı" olarak görünür.
- Aynı davaya bağlı iki föy aynı alan için farklı değer söylerse (biri değer, biri `(boş)`
  dahil) o alan **yazılmaz**, "kardeş föy çelişkisi" raporuna düşer. Boş hücre çelişki
  **değildir** — aşama satırlarında da kart alanlarında da dolu değerler birleştirilir (06.09
  raporundaki 302 "yalnız boşluk" grubu bizde kapandı).
- **Taraf kaydı "dondurma" diye bir işlem yoktur ve gerekmez** (06.09 §3/§12-5 isteğiniz):
  taraf satırları bizde yalnız eklenir, hiç silinmez ve üzerine yazılmaz. `Müvekkil` hücresini
  düzelttiğinizde (15 föydeki hekim adı gibi) sistem föyü yeni müvekkile bağlar, eski satırı
  yerinde bırakır ve satır raporuna "müvekkil değişti: eski → yeni" düşer; eski satırı biz
  elle temizleriz. Yani düzeltmeyi bekletmeyin, `Düzeltme_Logu` ile gönderin.
- **Müvekkil kimliği Dosya No kökünden okunur** (06.09 §2'de verdiğiniz kural: 1 Axa · 2 Quick ·
  3 Ak · 5 Koru · 6 Sompo · 7 Eureko · 8 HDI · 9 Anadolu · 8000 Nippon; 13 hizmetsiz; 500 ve
  üstü hekim/kurum). Dosya No birden çok kartımıza düşünce sistem esas ve dosya türünden sonra
  bu kökle ayırır; kök bir sigortayı gösterirken `Müvekkil` hücresinde **başka bir sigorta**
  yazıyorsa (H-6589, DN-11927 deseni) satır hiçbir karta yazılmaz, raporda "kök/müvekkil
  çelişkisi" olarak görünür. Corpus (kök 2) ve Ergo (kök 8) yazan föyler de bu sınıfa düştü —
  grup şirketi/devir ise bize bildirin, haritayı genişletelim. Kök 5 (Koru) 04.09 paketinde hiç
  yok; kök listenizin tam olduğunu teyit edin.

## 5. Kapsamdan çıkarılan föyler

`Silinen_Föyler` (mükerrer / hatalı açılış) ve `Kapsam_Dışı` (malpraktis dışı) sayfalarına
yazdığınız föyler bizde **silinmez**; kart ve belgeleri yerinde kalır, föy yalnız
"kapsam dışı" olarak işaretlenir ve gerekçeniz + tarihiniz kaydedilir. İşaretli föy kart
bilgilerini beslemez. Föy sonraki bir teslimde ana sayfada yeniden görünür ve kapsam
sayfalarında yoksa işaret kaldırılır. Bizde olmayan bir SistemNo bu sayfalarda gelirse
raporda "atlandı" olarak görünür, hata değildir. Pakette hiç olmayan föye (icra/tahkim/vergi
gibi, 06.09 §1.3) dokunulmaz — "kapsam dışı işaretlemeyin" isteğiniz zaten böyle çalışır.

## 6. Kapalı liste değerleri — "bizde olmayan değer yazılmaz"

Kapalı listeli alanlar (Müvekkil Tipi, Hizmet Türü, Olay Türü, Hükümdeki Rol, Yerel
Mahkeme Karar Durumu, İstinaf Karar Durumu, Temyiz/Yargıtay Onama Durumu, İddia Edilen
Kusur) için kural — Müvekkil Tipi / Hizmet Türü / Olay Türü / Hükümdeki Rol / İddia Edilen
Kusur havuzları bilgilendirme belgesi §3.8'dedir, karar durumu havuzlarının güncel hâli aşağıda:

- Müvekkil Tipi, Hizmet Türü, Olay Türü, Hükümdeki Rol: bizim listemizde **karşılığı
  olmayan** bir değer karta **yazılmaz**, satır raporunda "tanınmayan değer" olarak görünür.
  Karar durumları: havuz dışı değer satırı düşürmez, durum boş kalır, değer açıklamaya
  taşınır ve rapora yazılır. Listeye kendiliğinden ekleme yapılmaz — tahmin yasağı.
- İddia Edilen Kusur: değer karta **metin olarak olduğu gibi yazılır**; listemiz (04.09'dan
  beri dokuz değer) kart ekranındaki seçimi ve aşağıdaki havuz farkı raporunu besler.
  Liste dışı yazım karta girer ama ekranda liste dışı görünür — yazımı listeye uydurun.
- `DEGER_HAVUZLARI` sayfası paketle geliyorsa altı havuz için (İddia Edilen Kusur, üç
  karar durumu, Olay Türü, Hükümdeki Rol) iki yönlü fark çıkarılır: sizde olup bizde
  olmayanlar ve bizde olup sizde olmayanlar. Fark varsa cevap klasörüne
  `deger-havuzu-farki_<teslim>.csv` düşer; fark yoksa dosya üretilmez. Müvekkil Tipi ve
  Hizmet Türü havuzları karşılaştırılmaz; bu ikisinde tanınmayan değer yalnız satır
  raporunda görünür.
- Yeni bir değer eklenmesi gerekiyorsa bunu yazılı bildirin; listeye ekleme insan kararıyla
  yapılır, sonraki teslimde değer yazılır.

**Karar durumu havuzları (kanonik, 10.09.2026 — 06.09 §12-2 genişletme isteğiniz işlendi):**

| Aşama | Değer sayısı | Değerler (bizim yazımımız, birebir) |
| --- | --- | --- |
| Yerel | 27 | Açılmamış Sayılması (HMK 150. Md) · Adli Para Cezası · Anlaşma · Anlaşmama · Beraat · Birleştirme · Düşme Kararı · Hapis Cezası · Hapis Cezasının Paraya Çevrilmesi · Hükmün Açıklanmasının Geri Bırakılması (HAGB) · İflas · Kabul · Kabul/Kısmen · Karar Verilmesine Yer Olmadığına (HMK 331 Md.) · Kovuşturmaya Yer Olmadığına (KYOK) · Red/Arabuluculuk Ön Şart · Red/Dilekçenin Reddi · Red/Esastan · Red/Feragat · Red/Görev · Red/Husumet · Red/İdari Merciye Tevdi · Red/MSK Kararı Gereği · **Red/Usulden** (yeni) · Red/Yargı Yolu · Red/Yetkisizlik · Red/Zamanaşımı |
| İstinaf | 8 | Kaldırma · Kaldırma/Yeniden Hüküm · Başvuru Ret · **Düzeltilerek Karar Verildi** · **Düzeltilerek Kabul Edildi** · **Düzeltilerek Reddine** · **Kısmen Kabul** · **Davacı İstinaf Talebinin Kabulü** (beşi yeni, HMK 353/1-b-2) |
| Temyiz | 4 | Bozma · Onama · Düzelterek Onama · **Kısmen Onama/Kısmen Bozma** (yeni) |
| Karar Düzeltme | 2 | Karar Düzeltme Kabul · Karar Düzeltme Ret |

- **`Kapalı` ve `Derdest` yerel havuzdan çıktı.** İkisi mahkeme kararı değil büro dosya
  durumudur; 04.09 cevabımızdaki havuz onları taşıdığı için sözlük tuzağı bizden kaynaklandı.
  Karar durumu sütununa büro durumu **yazmayın, boş bırakın** — dosyanın derdest/arşiv bilgisi
  ana sayfadaki `Durum`dan gelir. Yine de gelirse satır düşmez: künyesi (mahkeme/esas/karar
  no/karar tarihi/tebliğ) dolu satır durumsuz yazılır ve "büro durumu, karar değil" şerhi
  düşer; künyesiz satır hiç yazılmaz.
- **`Karar` (istinaf, 74 föy) havuza girmedi:** tek başına anlamı belirsiz — hangi sonucu
  kastettiğinizi yazılı bildirin, ona göre eklenir ya da mevcut bir değere eşlenir.
- İstinaf yön hücreleri (~50, 06.09 §8) için bizde ayrı alan yoktur; siz ayrı alana taşıyınca
  değerlendiririz. 25 satırlık `appeal_decisions` listesi lokal bir seed artığıydı, kanonik
  liste yukarıdaki 8'dir.
- Karar durumunun **müvekkil yönü** (E-8: aynı kararın doktor föyünde red, sigorta föyünde
  kabul) kart düzeyinde tek slotta tutulur; kardeş föyler farklı söylüyorsa kart slotu boş kalır,
  föyün kendi değeri ham satırında saklanır ve çelişki raporunda "müvekkil yönü farkı" etiketiyle
  (hata değil) görünür. Föy düzeyinde ayrı karar alanı açılmadı — 29 grup için model değişikliği
  yapmıyoruz.

## 7. Ne zaman işlenir, ne olur

- Klasör her gece **04:00**'te taranır. Yeni paket önce **kuru koşulur** (hiçbir şey
  yazılmadan sonuç ölçülür), ölçümler eşiklerin içindeyse aynı gece uygulanır.
- Eşik dışı bir durum varsa (ör. satırların %5'inden fazlası eşleşmiyor, hata oranı %2'yi
  aşıyor, alan değişikliği 10.000 hücreden büyük, önceki teslim zinciri tutmuyor, belge sayımı
  denk çıkmıyor, tam pakette sütun kaybolmuş) paket **uygulanmaz**, "inceleme bekliyor"
  durumuna alınır ve HukuDok yöneticisi karar verir. Bu bir hata değildir; büyük teslimlerde
  beklenen yoldur.
- **Eşik nasıl sayılır (06.09 §K2 sorunuz):** "alan değişikliği" **kart hücresi** bazında
  sayılır — föy satırı değil, bizdeki kartın değeri değişen her alanı bir sayar. Tarih ve tutar
  hücreleri tip düzeyinde karşılaştırılır: `30.07.2026` ↔ `2026-07-30` ya da `1.500,00` ↔
  `1500` **değişiklik üretmez** (DB-009 sıfır). Metin alanları ham karşılaştırılır: ad yazımının
  değişmesi (`AXA SİGORTA` → `Axa Sigorta`, DB-008) **değişiklik sayılır** ve paketin yazımı
  bizdekinin üzerine yazılır ("paket kazanır"). Bu yüzden DB-008 gibi toplu yazım turları
  eşiği aşar ve insan onayına düşer — sorun değil, beklenen yol; 04.09 cevabımızdaki "bizde
  değişmiş görünmez" ifadesi yanlıştı, düzeltiyoruz. Tek istisna mahkeme adı: yalnız yazımı
  farklıysa bizimki kalır (§10).
- **`Durum` istisnası (§3.3):** paket `Durum`u yazar ama kesim tarihinden sonra bizde
  kullanıcı tarafından değiştirilmiş `Durum` üzerine **yazmaz**; satır raporunda `KORUNDU`
  türüyle görünür, hata sayılmaz, eşiği etkilemez.
- **İlk teslim her zaman insan onayıyla uygulanır.**
- Aynı gece birden çok paket bırakılırsa yalnız ilki otomatik uygulanır; diğerleri insan
  kararına bırakılır. Günde bir paket bırakın.
- Yapısı bozuk dosya (ana sayfa yok, `SistemNo`/`Dosya No` sütunu yok, dosya açılmıyor)
  **reddedilir**; cevap klasörüne bir şey düşmez, HukuDok tarafı size haber verir.
- Sistemde **yeni kart açılmaz**: bizde karşılığı olmayan (Dosya No ile eşleşmeyen) satırlar
  raporda "eşleşmedi" olarak kalır. Eşleşme köprüsü sizin "Dosya No" sütununuz ile bizim
  klasör numaramızdır; Dosya No birden çok karta düşünce sıra esas → dosya türü → Dosya No
  kökü (§4) → müvekkil adıdır.
- **Aşama satırları (`Karar_Asamalari`) nasıl güncellenir:** bizdeki aşama satırı paketten
  geldiyse ya da elle girildiyse yeni paket onu **yerinde günceller** (tarihçeli); yalnız
  **belgeye/UYAP kaydına dayanan** satırlara dokunulmaz — fark raporda "belgeli aşama satırı
  korundu" olarak görünür (06.09 §11.3'teki "künyede belgeye dayanan taraf kazanır" kuralıyla
  aynı). Aynı aşamanın **ikinci yargılama turu** (bozma sonrası ikinci istinaf gibi: esas
  numarası **ve** karar tarihi farklı) yeni satır olarak eklenir, eskisi kalır. Silme yoktur:
  paket bir aşamayı artık taşımıyorsa bizdeki satır kalır. 04.09 cevabımızdaki "270 HATA"
  sınıfı bu kuralla kapanır: uzlaştırdığınız aşama sayfası sonraki pakette bizdekini düzeltir.

## 8. Ne geri alırsınız — cevap klasörü

Her **uygulanan** teslim için `03_VERI_TESLIM/cevap/<teslim dosya adı, uzantısız>/` altına
(ör. `03_VERI_TESLIM/cevap/HUKDOK_TESLIM_PAKETI_2026-09-15/`) şu dosyalar bırakılır:

| Dosya | İçerik |
| --- | --- |
| `eslesme_<teslim>.csv` | **Talep #9.** Ana sayfadaki her satır için eşleşme sonucu. Sütunlar: `sistem_no`, `dosya_no`, `case_id` (bizim kart numaramız), `tracking_no` (ofis dosya no), `klasor_no_2`, `tku_no`, `case_party_id` (föyün bağlandığı müvekkil kaydı — 1.3'ten itibaren dolu gelir), `durum` (`ESLESTI` / `ESLESMEDI`), `sebep` (eşleşmediyse ya da alan düzeyinde bir uyarı varsa açıklaması). Düzeltme listenizi buradan kurabilirsiniz. |
| `ozet_<teslim>.txt` | Koşunun tek ekranlık özeti (okunan/işlenen/atlanan satır, alan değişikliği, boşaltılan alan, kapsam işaretleri, aşama satırı eklenen/güncellenen/ikinci tur/belgeli korunan, büro durumu atlanan, `Durum` korunan, föy↔müvekkil bağı, kök/müvekkil çelişkisi, hata ve çelişki sayısı) + son satırda kapı kararı ve gerekçesi. |
| `deger-havuzu-farki_<teslim>.csv` | Yalnız fark varsa (§6). Sütunlar: `havuz`, `liste`, `yon`, `deger`. |
| `satir-raporu_<tarih-saat>.csv` | Yalnız sorunlu ya da bilgi satırı varsa: `satir_no`, `sistem_no`, `dosya_no`, `tur`, `sebep`. `tur` değerleri: `ATLANDI` (eşleşmedi / bizde olmayan SistemNo / belgeli aşama satırı korundu), `HATA` (tanınmayan değer, çok değer, kök/müvekkil çelişkisi — satır ya da alan yazılmadı), `KORUNDU` (`Durum` istisnası, §7 — hata değil), `MUVEKKIL_DEGISTI` (föy başka müvekkile bağlandı, §4 — hata değil; eski taraf satırı bizde elle temizlenir). |
| `kardes-foy-celiskileri_<tarih-saat>.csv` | Yalnız çelişki varsa: aynı davanın föyleri aynı alan için farklı **dolu** değer söylüyor (`kume`, `kume_anahtari`, `alan`, `degerler`). Boşluk çelişki değildir. |
| `kuru-kosu-ozeti.txt`, `uygulama-ozeti.txt` | Kuru koşunun ve gerçek uygulamanın ayrı özetleri. |

CSV dosyaları Türkçe Excel'de doğrudan açılır (noktalı virgül ayraçlı, UTF-8).

"İnceleme bekliyor"da kalan ya da reddedilen teslim için cevap klasörü **açılmaz**; sonuç
size HukuDok tarafından iletilir. Cevap dosyaları uygulamadan hemen sonra yüklenir; SharePoint
o an ulaşılamazsa ertesi gece yeniden denenir.

## 9. Kısa kontrol listesi

1. Dosya adı `HUKDOK_TESLIM_…YYYY-AA-GG.xlsx`, klasör `03_VERI_TESLIM/gelen/`.
2. `Sheet` sayfası var; `SistemNo` ve `Dosya No` sütunları var; sütun adları önceki teslim ve
   bildirimlerle aynı (sıra serbest).
3. `DEGISIKLIK_OZETI`'nde üç satır: "Önceki teslim: <bir önceki dosyanın tam adı>" (ilk
   teslimde `—`), "Teslim türü: tam | delta", "Veri kesim tarihi: gg.aa.yyyy".
4. Delta paketse yalnız değişen föyler; `Karar_Asamalari` ve `Düzeltme_Logu` yalnız o föyler.
5. Boşaltmak istediğiniz alanlar `Düzeltme_Logu`'nda `(boş)` + gerekçe + `Sütun` başlığı (ya
   da `[Sütun Adı]` öneki).
6. Kapalı listeli alanlarda (Müvekkil Tipi, Hizmet Türü, Olay Türü, Hükümdeki Rol, karar
   durumları, İddia Edilen Kusur) yalnız bizde de olan değerler; karar durumu sütununa
   `Kapalı`/`Derdest` yazılmaz; yeni değer için önce yazılı bildirim (sıradaki numara
   DB-2026-011).
7. `Karar_Asamalari`'nda `Aşama = Önceki` satırlarını filtrelemeyin, gönderin (eski esas
   numarası olarak işlenir); `Başvuru Tarihi` sütunu doluysa okunur.
8. Günde bir paket; ertesi sabah `cevap/<teslim>/` klasörüne bakın.

## 10. Sütun sahipliği — kim yazar, kim korur

06.09 §11.3 tablonuz bizim modelle örtüşüyor; aşağıdaki tablo onun bizim taraftaki
karşılığıdır (farklar kalın):

| Bölge | Sütunlar | Yazan / kalıcı olduğu yer | Bizde nasıl işlenir |
| --- | --- | --- | --- |
| Klinik tasnif | Tıbbi Süreç · Tıbbi Olay · İddia Edilen Kusur · Hastada Oluşan Zarar · Uygulanan Yöntem | **yalnız siz** (master) | Paket kazanır, tarihçeli; bizde elle düzeltilmez |
| Kimlik / kapsam | SistemNo · Dosya No · Klasör No · Müvekkil · MüvekkilNo · Müvekkil Tipi · Hizmet Türü · Buro Özel Türü · Sigortalı | **yalnız siz** | Föy düzeyinde kayıpsız saklanır; kart alanına kardeş föyler çelişmiyorsa yazılır. Müvekkil kimliği Dosya No kökünden (§4). Taraf satırı bizde yalnız eklenir |
| Uzmanlık Alanı | — | **değeri siz; yazımı da artık siz** (DB-008 kuralı: bağlaç küçük, kısaltma korunur) | 1.3'ten itibaren paket yalnız yazım farkında da yazar; bizdeki 45'lik `specialties` listesi aynı kuralla yazılıdır (06.09 §11.2'deki 72→45 eşlemesini bekliyoruz). 04.09'daki "yazım bizim" ifadesi geçersiz |
| Mahkeme adı (Yerel/İstinaf/Temyiz) | — | değeri siz, **yazımı biz** (mahkeme adı kimliği bizde) | Yalnız yazım farkı varsa bizimki kalır; içerik farkı paket kazanır. `(boş)` uygulanmaz |
| `Durum` / arşiv-derdest | — | **biz** (06.09 §1.2) | Paket yazar; kesim tarihinden sonra bizde kullanıcı değiştirdiyse **yazmaz** (§3.3, §7) |
| Yargı zinciri | mahkeme · esas · karar no · karar tarihi · tebliğ · başvuru tarihi · karar durumu · tutarlar | **siz** (`Karar_Asamalari`), biz fotoğraflarız | Aşama satırı yerinde güncellenir; **belgeye/UYAP'a dayanan satır korunur** (§7); ikinci tur yeni satır; silme yok. Karar durumu kapalı havuz (§6), büro durumu yazılmaz |
| Sorumlu avukat | Sorumlu Avukatlar | siz (isim listesi), **kart kutusu biz** | 12 avukatlı 1.031 föy: hepsi ilişki olarak saklanır, kutu boş kalır; **kutu boşluğu artık "eksik alan" sayılmaz** (2+ avukatlı kartta). Silme/boşaltma yok — 06.09 §9 isteğiniz karşılandı |
| Kart / iş akışı | kart no · ofis dosya no · taraf satırları · belge · ajanda · bildirim · eksik-alan kovası | **yalnız biz** | Paket dokunmaz. Kart açma, birleştirme, bağ bizde |
| Esas numarası | Esas · Eski Dosya No | siz | Tarihçeli: eski esas `Önceki` aşama satırından, arama eski esasla da çalışır |

## 11. Yazım standardı — DB-008 genişletme ricası ve `Yazim_Standardi`

04.09 cevabımızda `Yazim_Standardi` tablosuna "gerek yok" demiştik; **düzeltiyoruz.**

- **DB-008 kapsamını genişletin:** İlk-Harf-Büyük standardını `Sigortalı`, `Davalı İdare`,
  `Yerel Mahkeme`, `İstinaf Mahkemesi` ve `Temyiz Mahkemesi` sütunlarına da uygulayın. 04.09
  paketinde bu beş sütun %99-100 BÜYÜK HARF geldi; bizdeki 217 istinaf + 38 temyiz mahkeme
  listesi ve 1.677 kart alanı paketten bu yazımla doldu. Biz dönüştürsek sonraki paket geri
  yazar — kaynak sizsiniz.
- **`Yazim_Standardi` sayfasını pakete ekleyin** (eski → yeni yazım haritası): paketle gelmeyen
  eski kartlarımızın (föysüz kartlar, Karşı Taraf'taki 131 BÜYÜK HARF satır) yazımını bu
  haritayla düzelteceğiz. Sayfa sistemce okunmaz, insan işler; adı ve düzeni serbest, eski
  değer / yeni değer / sütun üçlüsü yeter.
- Bizim tarafta kural: bağlaçlar küçük (ve, ile, veya, adına), kısaltmalar korunur (A.Ş., Ltd.,
  T.C., Dr., TCK, HD, İDD), parantez/tire sonrası büyük, yabancı adlarda I/ı çevrimi yok (Quick,
  HDI). Uzmanlık alanı ve liste adlarımız bu kurala çekildi; taraf adları (Müvekkil / Karşı
  Taraf "A.ş." artıkları) tek seferlik bir dönüşümle düzeltilecek, sizden `Yazim_Standardi`
  haritası geldikten sonra.
- Sorumlu avukat adlarında soyadı BÜYÜK yazımınız ("Rana Betül GÜMÜŞ") bizde dönüştürülmez;
  kart kutusundaki yazım bizimkidir, isim listesi olduğu gibi saklanır.
