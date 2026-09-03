# HUKDOK veri teslim sözleşmesi — veri ekibi için

**Sürüm:** 03.09.2026 · **Muhatap:** MicroKolayOfis master'ını temizleyen veri ekibi ·
**Karşı taraf:** HukuDok (Hanyaloğlu Acar + LexisBio ortak sistemi)

Bu metin, teslim paketinin **nasıl bırakılacağını** ve karşılığında **ne alınacağını**
anlatır. Teslim artık WhatsApp/e-posta ile değil, paylaşılan SharePoint klasörüne bırakılarak
yapılır; sistem paketi geceleri kendiliğinden işler. WhatsApp yalnız "dosyayı bıraktım"
haberi için kalır.

---

## 1. Nereye, hangi adla

- **Klasör:** SharePoint'te size paylaşılan `03_VERI_TESLIM` klasörünün `gelen` alt klasörü
  (`03_VERI_TESLIM/gelen/`).
- **Dosya adı:** `HUKDOK_TESLIM_` ile başlayan ve `.xlsx` ile biten bir ad; örneğin
  `HUKDOK_TESLIM_PAKETI_2026-09-15.xlsx`. Büyük/küçük harf fark etmez. Bu kalıba uymayan
  dosyalar **görmezden gelinir** (hata da vermez).
- **Aynı dosyayı iki kez bırakırsanız** sorun olmaz: içerik aynıysa ikinci kopya "yinelenen"
  olarak kaydedilir ve işlenmez. İçeriği değiştirip aynı adla yeniden yüklerseniz **yeni bir
  teslim** sayılır.
- Her teslim ayrı bir dosyadır; önceki teslimin dosyasını silmenize gerek yok.

## 2. Dosyanın içinde ne olmalı

| Sayfa adı | Zorunlu mu | Ne olmalı |
| --- | --- | --- |
| `Sheet` | **Zorunlu** | Ana veri sayfası: föy başına bir satır, 68 sütun, sütun adları ve sırası önceki teslimlerdeki gibi sabit. `SistemNo` ve `Dosya No` sütunları **mutlaka** bulunmalı — ikisi olmadan dosya reddedilir. |
| `DEGISIKLIK_OZETI` | Zorunlu | "Önceki teslim" ve "Bu teslim" satırları (aşağıda §3). Sayfa yoksa dosya reddedilmez ama otomatik uygulanmaz, mutlaka insan incelemesine düşer. |
| `Karar_Asamalari` | İsteğe bağlı | Föy başına yargı aşamaları (Yerel → İstinaf → Temyiz → Karar Düzeltme). Yoksa aşama bilgisi yazılmaz, hata değildir. |
| `Düzeltme_Logu` | İsteğe bağlı | Hücre düzeltme günlüğü: `SistemNo`, `Eski Değer`, `Yeni Değer`, `Gerekçe`, `Tarih`. Gerekçe bizde o alanın değişiklik tarihçesine işlenir. Değişen sütunun adını gerekçenin başında köşeli parantezle yazın: `[Hükmedilen Manevi] Outlook otomasyonu parti-2`. Sütun adı yazılmayan satır işlenmez. |
| `DEGER_HAVUZLARI` | İsteğe bağlı | Kapalı liste değerleri: "Havuz / Sütun" ve "Değer" sütunları (bugünkü paketteki düzen). Bizim listelerimizle karşılaştırılır; fark varsa cevap klasörüne rapor düşer (§6). |
| `Silinen_Föyler`, `Kapsam_Dışı` | İsteğe bağlı | Kapsamdan çıkardığınız föyler: `SistemNo` + gerekçe (`Silinme Gerekçesi` / `Kapsam Dışı Gerekçesi`) + `Tarih`. Bkz. §5. |
| `SUTUN_SOZLUGU`, `SINIFLANDIRMA_MODELI`, `HUKDOK_TALEPLERI` | İsteğe bağlı | Okunmaz; paketle gelmesi sorun değildir. |

Sayfa adları yukarıdaki yazımla birebir olmalıdır (`Sheet`, `DEGISIKLIK_OZETI`,
`Karar_Asamalari`, `Düzeltme_Logu`, `DEGER_HAVUZLARI`). Kapsam sayfalarında aksan/alt çizgi
farkı tolere edilir (`Silinen_Föyler` = `Silinen Foyler`), diğerlerinde edilmez.

## 3. `DEGISIKLIK_OZETI` — "Önceki teslim" satırı

Sistem bu sayfada **"Önceki teslim"** etiketli hücreyi arar ve yanındaki değeri bir önceki
paketin **dosya adı** olarak okur. Kabul edilen yazımlar:

- Aynı hücrede: `Önceki teslim: HUKDOK_TESLIM_PAKETI_2026-08-18.xlsx`
- Etiket bir hücrede, dosya adı sağındaki ilk dolu hücrede.
- Dosya adından sonra ` · 8.409 satır × 68 sütun` gibi bir ek yazılabilir; nokta işaretinden
  (`·`) sonrası dikkate alınmaz.
- İlk teslimde `—` ya da `yok` yazın (boş bırakmak da olur).

Neden önemli: sistem, "önceki teslim" dediğiniz dosyanın gerçekten bizde uygulanmış olduğunu
kontrol eder (**zincir kontrolü**). Bir teslim atlanmışsa ya da ad yanlış yazılmışsa paket
otomatik uygulanmaz, insan incelemesine düşer. Ad, bıraktığınız dosyanın adıyla birebir
olmalıdır.

## 4. Partili teslim ve alan boşaltma

- **Paket parça parça gelebilir.** Ana sayfada bir sütun hiç yoksa ya da bir hücre boşsa bu
  "bu teslimde bu bilgi yok" demektir; bizdeki mevcut değer **silinmez**, olduğu gibi kalır.
- **Bir alanı bilerek boşaltmak** istiyorsanız bunu açıkça `Düzeltme_Logu`'nda söylersiniz:
  ilgili satırın `Yeni Değer` hücresine parantezli olarak **`(boş)`** yazın ve gerekçeyi
  belirtin. Sistem üç şartı birlikte arar: log `(boş)` diyor **ve** ana sayfada o hücre
  gerçekten boş **ve** bizde o alan dolu. Üçü de sağlanınca alan boşaltılır ve gerekçe
  tarihçeye işlenir. Parantezsiz `boş` bir metin değeridir, boşaltma talimatı değildir.
- Boşaltılamayan alanlar: karar numarası ve karar tarihi (aşama fotoğrafından beslenir),
  mahkeme adı ve alt tür (yazım bizim). Bunlar için gelen `(boş)` talimatı uygulanmaz,
  raporda "boşaltılmadı" olarak görünür.
- Aynı davaya bağlı iki föy aynı alan için farklı değer söylerse (biri değer, biri `(boş)`
  dahil) o alan **yazılmaz**, "kardeş föy çelişkisi" raporuna düşer.

## 5. Kapsamdan çıkarılan föyler

`Silinen_Föyler` (mükerrer / hatalı açılış) ve `Kapsam_Dışı` (malpraktis dışı) sayfalarına
yazdığınız föyler bizde **silinmez**; kart ve belgeleri yerinde kalır, föy yalnız
"kapsam dışı" olarak işaretlenir ve gerekçeniz + tarihiniz kaydedilir. İşaretli föy kart
bilgilerini beslemez. Föy sonraki bir teslimde ana sayfada yeniden görünür ve kapsam
sayfalarında yoksa işaret kaldırılır. Bizde olmayan bir SistemNo bu sayfalarda gelirse
raporda "atlandı" olarak görünür, hata değildir.

## 6. Kapalı liste değerleri — "bizde olmayan değer yazılmaz"

Kapalı listeli alanlar (İddia Edilen Kusur, Yerel Mahkeme Karar Durumu, İstinaf Karar
Durumu, Temyiz/Yargıtay Onama Durumu, Olay Türü, Hükümdeki Rol) için kural:

- Bizim listemizde **karşılığı olmayan** bir değer karta **yazılmaz**, satır raporunda
  "tanınmayan değer" olarak görünür. Listeye kendiliğinden ekleme yapılmaz — tahmin yasağı.
- `DEGER_HAVUZLARI` sayfası paketle geliyorsa iki yönlü fark çıkarılır: sizde olup bizde
  olmayanlar ve bizde olup sizde olmayanlar. Fark varsa cevap klasörüne
  `deger-havuzu-farki_<teslim>.csv` düşer; fark yoksa dosya üretilmez.
- Yeni bir değer eklenmesi gerekiyorsa bunu yazılı bildirin; listeye ekleme insan kararıyla
  yapılır, sonraki teslimde değer yazılır.

## 7. Ne zaman işlenir, ne olur

- Klasör her gece **04:00**'te taranır. Yeni paket önce **kuru koşulur** (hiçbir şey
  yazılmadan sonuç ölçülür), ölçümler eşiklerin içindeyse aynı gece uygulanır.
- Eşik dışı bir durum varsa (ör. satırların %5'inden fazlası eşleşmiyor, hata oranı %2'yi
  aşıyor, alan değişikliği çok büyük, önceki teslim zinciri tutmuyor, belge sayımı denk
  çıkmıyor) paket **uygulanmaz**, "inceleme bekliyor" durumuna alınır ve HukuDok yöneticisi
  karar verir. Bu bir hata değildir; büyük teslimlerde beklenen yoldur.
- **İlk teslim her zaman insan onayıyla uygulanır.**
- Aynı gece birden çok paket bırakılırsa yalnız ilki otomatik uygulanır; diğerleri insan
  kararına bırakılır. Günde bir paket bırakın.
- Yapısı bozuk dosya (ana sayfa yok, `SistemNo`/`Dosya No` sütunu yok, dosya açılmıyor)
  **reddedilir**; cevap klasörüne bir şey düşmez, HukuDok tarafı size haber verir.
- Sistemde **yeni kart açılmaz**: bizde karşılığı olmayan (Dosya No ile eşleşmeyen) satırlar
  raporda "eşleşmedi" olarak kalır. Eşleşme köprüsü sizin "Dosya No" sütununuz ile bizim
  klasör numaramızdır.

## 8. Ne geri alırsınız — cevap klasörü

Her **uygulanan** teslim için `03_VERI_TESLIM/cevap/<teslim dosya adı, uzantısız>/` altına
(ör. `03_VERI_TESLIM/cevap/HUKDOK_TESLIM_PAKETI_2026-09-15/`) şu dosyalar bırakılır:

| Dosya | İçerik |
| --- | --- |
| `eslesme_<teslim>.csv` | **Talep #9.** Ana sayfadaki her satır için eşleşme sonucu. Sütunlar: `sistem_no`, `dosya_no`, `case_id` (bizim kart numaramız), `tracking_no` (ofis dosya no), `klasor_no_2`, `tku_no`, `case_party_id`, `durum` (`ESLESTI` / `ESLESMEDI`), `sebep` (eşleşmediyse ya da alan düzeyinde bir uyarı varsa açıklaması). Düzeltme listenizi buradan kurabilirsiniz. |
| `ozet_<teslim>.txt` | Koşunun tek ekranlık özeti (okunan/işlenen/atlanan satır, alan değişikliği, boşaltılan alan, kapsam işaretleri, hata ve çelişki sayısı) + son satırda kapı kararı ve gerekçesi. |
| `deger-havuzu-farki_<teslim>.csv` | Yalnız fark varsa (§6). Sütunlar: `havuz`, `liste`, `yon`, `deger`. |
| `satir-raporu_<tarih-saat>.csv` | Yalnız sorunlu satır varsa: `satir_no`, `sistem_no`, `dosya_no`, `tur` (ATLANDI / HATA), `sebep`. |
| `kardes-foy-celiskileri_<tarih-saat>.csv` | Yalnız çelişki varsa: aynı davanın föyleri aynı alan için farklı değer söylüyor (`kume`, `kume_anahtari`, `alan`, `degerler`). |
| `kuru-kosu-ozeti.txt`, `uygulama-ozeti.txt` | Kuru koşunun ve gerçek uygulamanın ayrı özetleri. |

CSV dosyaları Türkçe Excel'de doğrudan açılır (noktalı virgül ayraçlı, UTF-8).

"İnceleme bekliyor"da kalan ya da reddedilen teslim için cevap klasörü **açılmaz**; sonuç
size HukuDok tarafından iletilir. Cevap dosyaları uygulamadan hemen sonra yüklenir; SharePoint
o an ulaşılamazsa ertesi gece yeniden denenir.

## 9. Kısa kontrol listesi

1. Dosya adı `HUKDOK_TESLIM_…xlsx`, klasör `03_VERI_TESLIM/gelen/`.
2. `Sheet` sayfası var; `SistemNo` ve `Dosya No` sütunları var; 68 sütun adı ve sırası sabit.
3. `DEGISIKLIK_OZETI`'nde "Önceki teslim: <bir önceki dosyanın tam adı>" satırı var.
4. Boşaltmak istediğiniz alanlar `Düzeltme_Logu`'nda `(boş)` + gerekçe + `[Sütun Adı]` önekiyle.
5. Kapalı listeli alanlarda yalnız bizde de olan değerler; yeni değer için önce yazılı bildirim.
6. Günde bir paket; ertesi sabah `cevap/<teslim>/` klasörüne bakın.
