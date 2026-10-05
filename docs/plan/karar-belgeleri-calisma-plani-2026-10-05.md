# Karar belgeleri çalışma planı — HUKDOK → Hukukbot → Lexis

**Tarih:** 05.10.2026 · **Kaynak:** 05.10 sohbeti (karar veritabanı oturumu) ·
**Durum:** **ONAY BEKLİYOR** — sıra kullanıcının önerisidir (önce HUKDOK, sonra Hukukbot, en son Lexis);
yalnız 1. adımın ölçümleri yapıldı (§5.2 ve §5.3, yazma yok), diğer adımlar başlamadı. Görsel anlatım: `karar-belgeleri-uc-sistem-2026-10-05.pdf` (aynı klasör; 8 sayfa —
7. sayfa veri ekibine danışma çizelgesi, 8. sayfa takip tablosu).

> **Sayıların kaynağı.** Aksi yazmıyorsa sayılar 05.10.2026'da **lokal** veritabanı kopyalarından
> ölçüldü (HUKDOK lokal Postgres'i ve `lexis_db`); prod'u temsil etmez. Hukukbot sayıları (≈ 4.847 belge,
> ≈ 504 künyeli, ≈ 4.340 eski yük) Hukukbot deposunun 28.09 tarihli `rapor/06-rag-sistem-analizi.md`
> dosyasındandır, bugün yeniden sayılmadı. Karar veritabanının ayrıntısı: `..\lexis-rapor\PLAN.md` Aşama 11.

## 1. Amaç ve gerekçe

Büro arşivindeki kararlar (4.078 PDF: karar, bilirkişi ve ATK raporu) üç sistemde üç ayrı iş görecek:

| Sistem | Görevi | Saklanan birim |
| --- | --- | --- |
| HUKDOK | Asıl dosya ve dava kartı | Dosya (arşivde PDF, veritabanında belge kaydı ve aşama künyesi) |
| Hukukbot | Soru sorulabilir arşiv | Metin parçası |
| Lexis | Ayrıştırılmış karar verisi (sonuç, tutar, gerekçe) | Alan ve parça |

**Neden önce HUKDOK** (kullanıcı, 05.10: "kararları HUKDOK'ta doğru dava kartlarının altına koyabilirsek
büyük bir yükten kurtuluruz"): asıl tek yerde toplanır; Hukukbot'un bugün çalışan aktarım hattı
(`export_outbox` → Hukukbot `ingest`) kararları kendiliğinden taşır; Lexis künyeyi tahmin etmek yerine
HUKDOK'tan okur. İlke: bir bilgi kaynağında düzeltilir, türevler yeniden üretilir.

## 2. Sıra — kolaydan zora

| # | Adım | Sistem | Zorluk | Yazma | Karar / onay |
| --- | --- | --- | --- | --- | --- |
| 1 | Eşleştirme listesi | HUKDOK (yalnız okuma) | Kolay | Yok | — |
| 2 | Lokalde toplu ekleme (kuru koşu → uygulama) | HUKDOK | Orta | Lokal DB | Şema eki onayı |
| 3 | Prod'a uygulama | HUKDOK | Orta | Prod | Kullanıcı kararı, mesai dışı |
| 4 | Hukukbot, kolay yol: künye belgenin aşamasından + arşiv kararları mevcut kuyruktan | Hukukbot + HUKDOK | Orta | Gemini deposu | Her yükleme ayrı onay; maske kararı |
| 5 | Eski künyesiz yükün kaldırılması | Hukukbot | Orta | Gemini deposu | Kullanıcı kararı (geri alınamaz) |
| 6 | Lexis'in kalanı: tutar hatası, kalan kararlar, ekran | Lexis | Zor | `lexis_db` | Model adımı ayrı onay |
| 7 | Hukukbot, zor yol: kararı parça rolüyle yüklemek | Hukukbot + Lexis | En zor | Gemini deposu | Yalnız 4. adımın ölçümü yetersizse |

### Adım 1 — Eşleştirme listesi (yazma yok)

- Hangi PDF → hangi dava kartı → kartın hangi aşama kaydı. Eşleşmenin çoğu hazır
  (`..\lexis-rapor` `karar.py`, `araclar/karar_yukle.py`): 4.058 büro belgesinin **3.065**'i tek karta
  (1.825 kart), bunların **2.493**'ü aşama kaydına oturuyor.
- **Ölçüldü (05.10, sonuç §5.2):** arşivdeki PDF'lerin ne kadarı HUKDOK'ta zaten belge kaydı. Lokal kopyada
  2.480 belge kaydı var, ≈ 1.000'i karar ya da rapor türünde; `case_documents`'ta dosya özeti (parmak izi)
  tutulmadığı için doğrudan eşlenemiyor — yöntem bu adımda seçilir (arşivdeki dosyaların özetini almak ya da
  kart + tür + tarih ile yaklaşık eşleme).
- Belge türü eşlemesi: dosya adındaki mahkeme / dereceden HUKDOK belge türü koduna (gerekçeli karar,
  istinaf, Yargıtay, Danıştay, bilirkişi, ATK) — kural yazılır, uymayanlar listelenir.
- Çıktı: sayılarla rapor + inceleme listeleri (depo dışı; kişi verisi repoya girmez).

### Adım 2 — Lokalde toplu ekleme

- Kararlar karta bağlı **arşiv belgesi** olarak eklenir; analiz ve onay hattından (`/process` → `/confirm`)
  GEÇMEZ, kaynağı işaretlidir.
- Belge kaydına iki ek (migrasyon; kalıcı index ayrı `("index", ...)` op'u — CLAUDE.md tuzağı):
  dosyanın **parmak izi** (mükerrer yüklemeyi görmek için) ve **aşama bağı** (belge → `case_stage_decisions`
  satırı; bugün yok).
- Script varsayılan kuru koşu, `--apply` ayrı; önce lokal kopyada.
- **Kapalı tutulacak iki yan etki:**
  - *Otomatik Hukukbot aktarımı.* Bugün arşive giren her karar `notify_hukukbot` ile kuyruğa, oradan Gemini
    deposuna gidiyor. Toplu eklemede kapalı kalır; aktarım 4. adımın ayrı ve onaylı işidir.
  - *Bildirim.* Normal akışta her belge için avukatların ziline `belge_islendi` düşer; toplu eklemede üretilmez.

### Adım 3 — Prod'a uygulama

- Yalnız kullanıcı kararıyla; mesai (09:00–18:00 TR) dışında; öncesinde dump. Kuru koşu prod'da değil, prod
  dump'ının kopyasında (CLAUDE.md "Prod'da mesai içinde toplu yazma yok").
- ≈ 3.000 PDF arşive (SharePoint) yüklenir: süre, PDF/A dönüşümü gerekip gerekmediği ve yükleme kuyruğunun
  (`upload_outbox`) bu hacimde davranışı 2. adımda lokalde ölçülür.

### Adım 4 — Hukukbot, kolay yol

- **Künye düzeltmesi:** bugün Hukukbot'a giden künye belgenin değil, bağlı olduğu **davanın** künyesi (28.09'da
  canlıda bir üst mahkeme kararı davanın kayıtlı merciinin adıyla etiketlendi). 2. adımdaki aşama bağıyla
  `/export` yanıtına belgenin kendi aşama künyesi eklenir; Hukukbot `hukdok_map` onu kullanır.
- Arşiv kararları mevcut kuyruktan geçer: önce **100 kararlık deneme**, 27 soruluk sınama setiyle ölçüm,
  sonra toplu.
- Her yükleme Gemini'ye gönderimdir → onaysız yapılmaz. **Ad maskesi kararı** burada verilir (bugün Hukukbot'a
  PDF maskesiz gidiyor; kodda maskeleme yok).

### Adım 5 — Eski künyesiz yükün kaldırılması

- Depodaki ≈ 4.340 eski belge (ilk toplu yükleme; mahkemesi, esası, tarihi kayıtlı değil) kaldırılır.
- 4. adımla **birlikte** planlanır: eski yük dururken arşiv kararları yüklenirse aynı karar depoda iki kez
  durur ve cevaplar ikisine de atıf yapar.
- Geri alınamaz; kullanıcının 28.09 kararıyla uyumlu ("bütün belgeler künyeleri yazılarak yeniden yüklenecek").
  Depo türü (yönetilen depoda kalmak / kendi vektör veritabanı) bu adımdan önce kesinleşir.

### Adım 6 — Lexis'in kalanı

- Fiilsiz kabul çıkarımı hatası: 35 adayın 31'i doğrulandı (`..\lexis-rapor\PLAN.md` §7).
- Kodun yetmediği 489 karar: model mi (ad maskesinden sonra, ayrı onay) elle mi.
- Pakette olmayan 479 PDF; ekrana karar rafı.
- **Bağımsız, her an yapılabilir:** kullanıcının 20 kararlık elle denetimi
  (`C:\hukdok-veri\lexis\kararlar\rapor\elle_bakilacak_20.csv`).
- HUKDOK'ta belge → aşama bağı kayıtlı olunca Lexis künyeyi oradan okur; kendi eşleme hesabı yedek kalır.

### Adım 7 — Hukukbot, zor yol (koşullu)

- Kararı hüküm / gerekçe / iddia / savunma parçalarına bölüp her parçayı künyesi ve rolüyle yüklemek; büro
  kararları ile dış kararlar ayrı raf. Parçalar Lexis'te üretilir.
- **Yalnız** 4. adımın ölçümü yetersiz çıkarsa açılır.

## 3. Veri ekibine danışma noktaları

Kartın, föyün ve aşama kaydının sahibi veri ekibidir. Bir belgeyi karta bağlayamıyorsak ya da iki kaynak
çelişiyorsa doğrusu tahmin edilmez: liste hazırlanır, sorulur. Düzeltme HUKDOK'ta (teslim paketiyle) yapılır,
Lexis ve Hukukbot yeniden üretilir. **Bekletir** = cevap gelmeden gösterilen adım başlamaz; **paralel** = iş
sürer, cevap gelince sonraki turda eklenir.

| No | Ne zaman | Ne sorulur / ne istenir | Bekletir mi |
| --- | --- | --- | --- |
| V1 | 1. adımdan sonra | Karta bağlanamayan belgeler: 985 föysüz, 8 iki kartlı, 30 adı kalıp dışı ya da öneki bilinmeyen dosya (`C-`/`ARB-`/`DN-`/`SSTMN-` 21 + kalıp dışı 9) — hangi dosyaya ait? | Paralel: bağlananlarla devam edilir |
| V2 | 1. adımdan sonra | Aşaması bulunamayan 572 karar: 282'sinde aynı mahkemenin başka künyeli kaydı var, 217'sinde o mahkemenin kaydı yok, 66 kartta hiç aşama yok (kalan 7: çok aday / ayrışan anahtar). Eksik aşama kayıtları teslim paketine girsin | Paralel: belge karta girer, aşama bağı boş kalır |
| V3 | 1. adımdan sonra | Künye çelişkileri: 198 yerde karar tarihi (171) ya da esas no (27) veritabanında ve dosya adında farklı; 129'unda kararın metni dosya adını doğruluyor | Paralel; 4. adımdan (Hukukbot yüklemesi) önce kapanmalı |
| V4 | 1. adımdan sonra | Sonuç etiketinin anlamı: `karar_durumu` ve dosya adındaki sonuç kimin yönünden yazıldı; değer listesi ve anlamları | Paralel; 6. adım için gerekli |
| V5 | 2. adımdan sonra | Aşama satırının kalıcı kimliği: teslim paketi aşama satırını güncelleyince (yerinde güncelleme, tur sırası değişimi) belge → aşama bağı doğru satırı göstermeye devam eder mi? Sözleşmeye (`docs/veri-teslim/SOZLESME.md`) "arşiv belgeleri" notu | **Bekletir → 3** |
| V6 | 3. adımdan önce | Takvim: toplu ekleme, teslim paketinin uygulandığı geceyle çakışmasın (ikisi de kartları kilitler) | **Bekletir → 3** |
| V7 | 5. adımdan önce | Eski yükün kaynağı: Hukukbot deposundaki ≈ 4.340 eski belge büro arşiviyle aynı mı; arşivde olmayan belge var mı? (ilk yüklemeyi yapan / veri ekibi; ilk yükleme başka makineden yapılmış) | **Bekletir → 5** (silme geri alınamaz) |
| V8 | 6. adımda | Eksik bilgi: taranmış 121 kararın metinli aslı var mı; kesinleşme tarihleri sağlanabilir mi (zincire bağlı kartların hiçbirinde dolu değil) | Paralel |
| V9 | 6. adımdan sonra | Etiketi hatalı görünen kararlar: bizim incelememizden sonra etiketi yanlış çıkanlar düzeltme için gönderilir (en çok 232 aday: ayrışık 185 + talep karması 47) | Paralel |

V5'in gerekçesi doğrulanmış bir arıza değil, sorulacak bir risktir: aktarım aşama satırını yerinde günceller ve
tur sırasını değiştirebilir (`docs/mimari/veri-teslim-hatti.md` §7.1); belge bağı eklendiğinde bunun bağı
bozup bozmayacağı 2. adımda lokalde sınanır, veri ekibinden satır kimliğinin nasıl korunduğu teyit edilir.

## 4. Takip tablosu

Sırayla işlenir. Durum: `☐` başlamadı · `◐` sürüyor · `☑` bitti. Görsel hâli PDF'in 7. ve 8. sayfasında.

| No | İş | Kim | Bekletir mi | Durum | Tarih |
| --- | --- | --- | --- | --- | --- |
| **HUKDOK** | | | | | |
| 1 | Eşleştirme listesi (yazma yok) | Biz | — | ◐ | 05.10: mevcut belge kaydı ölçümü (§5.2); kalan: tür eşleme kuralı, V1-V4 listeleri |
| V1 | Karta bağlanamayan belgeler | Veri ekibi | Paralel | ☐ | |
| V2 | Aşaması bulunamayan kararlar | Veri ekibi | Paralel | ☐ | |
| V3 | Künye çelişkileri | Veri ekibi | Paralel; 4'ten önce | ☐ | |
| V4 | Sonuç etiketinin anlamı | Veri ekibi | Paralel; 6 için | ☐ | |
| 2 | Lokalde toplu ekleme | Biz | Kullanıcı: şema eki onayı | ◐ | 05.10: şema eki onaylandı; ilk aşama (3.333 belge, 1.903 kart) lokalde eklendi ve PDF'leri gerçek arşive yüklendi (§5.4); kalan: olası 150, aynı kararın kopya taramaları |
| V5 | Aşama satırının kimliği, paket kuralı | Veri ekibi | **Bekletir → 3** | ☐ | |
| V6 | Takvim | Veri ekibi | **Bekletir → 3** | ☐ | |
| 3 | Prod'a uygulama | Kullanıcı + biz | Kullanıcı: karar | ☐ | |
| **HUKUKBOT** | | | | | |
| 4 | Kolay yol: 100 kararlık deneme, sonra toplu | Biz | Kullanıcı: maske, her yükleme | ☐ | |
| V7 | Eski yükün kaynağı | İlk yükleyen / veri ekibi | **Bekletir → 5** | ☐ | |
| 5 | Eski künyesiz yükün kaldırılması | Kullanıcı + biz | Kullanıcı: karar | ☐ | |
| **LEXIS** | | | | | |
| V8 | Eksik bilgi (taranmış asıllar, kesinleşme) | Veri ekibi | Paralel | ☐ | |
| 6 | Lexis'in kalanı | Biz | Kullanıcı: model onayı | ☐ | |
| V9 | Etiketi hatalı görünen kararlar | Veri ekibi | Paralel | ☐ | |
| 7 | Zor yol: parça rolüyle yükleme | Biz | Koşullu | ☐ | |

## 5. Eşleştirmenin bugünkü sonucu (Lexis tarafındaki hesap; 1. adımın başlangıç noktası)

Kaynak: `C:\hukdok-veri\lexis\kararlar\rapor\adim1_rapor.json` ve lokal `lexis_db` (05.10.2026). Bu hesap
"PDF → kart → aşama" bağını verir; **HUKDOK'ta zaten belge kaydı olanlar ölçülmedi** (1. adımın işi).

**Karta bağlama (4.058 büro belgesi):**

| Sonuç | Belge | Nasıl / neden |
| --- | --- | --- |
| Tek karta bağlandı | 3.065 | PDF adındaki föy numarası (yoksa paketin föy bağı) → `case_foys.sistem_no` → kart. 1.825 kart; 3.047'sinin PDF'i klasörde, 18'inin PDF'i yok |
| Föy numarası yok | 985 | 531'inin PDF adı `YOKSIS` taşıyor (arşivi hazırlayan föy bulamamış); 454'ünün PDF'i klasörde hiç yok (yalnız pakette metni var, föy bağı da yok) |
| İki karta gidiyor | 8 | Dosya adının föyü ile paketin föy bağı farklı karta gidiyor; kart seçilmedi |

Türe göre: 3.756 kararın 3.058'i bağlandı (%81); 302 bilirkişi / ATK raporunun yalnız 7'si bağlandı (295'i föysüz).
Kart başına belge: 998 kartta 1 · 563 kartta 2 · 252 kartta 3-5 · 12 kartta 6 ve üzeri.

**Aşama kaydına oturtma (karta bağlı 3.065 belge):**

| Sonuç | Belge | Nasıl / neden |
| --- | --- | --- |
| Esas no + karar tarihi tuttu | 2.084 | En güçlü eşleşme |
| Yalnız esas no tuttu | 206 | Kayıtta tarih boş ya da farklı (farklıysa künye çelişkisi listesinde) |
| Yalnız karar tarihi tuttu | 76 | Mahkeme aykırı değilse |
| Yalnız mahkeme tuttu | 127 | Kayıt künyesiz açılmış (esas ve tarih boş) |
| **Oturdu, toplam** | **2.493** | |
| Kayıt yok / tutmuyor | 499 | 282'sinde aynı mahkemenin başka künyeli kaydı var; 217'sinde kartta o mahkemenin kaydı hiç yok |
| Kartta hiç aşama kaydı yok | 66 | |
| Birden çok aday | 4 | Aynı güçte iki kayıt; seçilmedi |
| İki anahtar ayrışıyor | 3 | Esas no bir kayda, tarih başka kayda gidiyor; bağ kurulmadı |

**Pakette olmayan 479 PDF** ayrıca duruyor (bu tabloların dışında): 407'sinin föyü kartta, 63'ü föysüz, 9'unun adı
kalıba uymuyor; kart düzeyinde sayımı yapılmadı.

## 5.1 Sınırlar — yükün ne kadarı kalkar

| | Belge | Ne olur |
| --- | --- | --- |
| Tek karta bağlanan | 3.065 | Kendiliğinden yerine oturur |
| Föy numarası olmayan | 985 | Karta otomatik bağlanamaz: elle bağlanır ya da "kartsız arşiv" olarak durur |
| İki karta giden | 8 | Kart seçilmez (kullanıcı kararı K8), listelenir |
| Karta bağlı ama aşaması bulunamayan | 572 | Karta girer, aşama bağı boş kalır |
| Künye çelişkisi | 129 yer | HUKDOK'taki tarih / esas no kararın metninde geçmiyor, dosya adındaki geçiyor → düzeltme listesi veri ekibine; düzeltme HUKDOK'ta yapılır |

## 5.2 HUKDOK'ta zaten belge kaydı olanlar (1. adımın ilk ölçümü, 05.10.2026)

Yazma yok; iki lokal kopyadan (HUKDOK Postgres'i, `lexis_db`) okunarak ölçüldü. Lokal HUKDOK kopyasının son belge
kaydı 15.09.2026 tarihlidir; prod'da daha yenisi olabilir. Sonuç dosyaları depo dışında:
`C:\hukdok-veri\lexis\kararlar\rapor\hukdok_esleme_*.csv` ve `hukdok_esleme_rapor.json`.

**Yöntem.** `case_documents`'ta parmak izi yok; eşleme yaklaşıktır. Anahtarlar: aynı kart + esas no
(`case_documents.esas_no`, `;` çok değerli) + belge tarihi (`stored_filename` başındaki tarih) + derece (belge türü
kodu, `_`/`-` atılarak). Dosya adı kademesi **boş döndü** (0 eşleşme): HUKDOK'taki özgün adlar UYAP adlarıdır, arşiv
adlandırmasıyla ortak yanı yok. Kademelerden rastgele ≈ 35 örneğe bakılarak sınıflar düzeltildi (aşağıdaki iki not).

**HUKDOK tarafı.** Silinmemiş 2.480 belge kaydı, 884 kartta. Nihai karar türünde 500 (gerekçeli, istinaf, Yargıtay,
Danıştay, karar düzeltme, ek, görev, AYM), bilirkişi / ATK raporu türünde 320; ara karar, tebligat, dilekçe ve
diğerleri 1.660.

**Karta bağlı arşiv belgeleri (3.472 = paketteki 3.065 + pakette olmayan PDF'lerden föyü kartta olan 407):**

| Sınıf | Paket (3.065) | Pakette olmayan PDF (407) | Toplam |
| --- | --- | --- | --- |
| Güçlü eşleşme: aynı kart + aynı tarih + (aynı esas ya da aynı derece) | 26 | 239 | **265** |
| Olası: aynı kart + aynı esas + aynı derece, tarih farklı (ya da tarih tutuyor, derece tutmuyor) | 24 | 14 | **38** |
| Kartta aynı esasla **başka derecenin** kararı var, bu belge yok | 121 | 3 | 124 |
| Kartta başka karar belgesi var, bu belge yok | 157 | 35 | 192 |
| Kartta belge var, karar / rapor türünde yok | 171 | 8 | 179 |
| Kartta hiç belge kaydı yok | 2.566 | 108 | 2.674 |

- **HUKDOK'ta zaten var: 265 güçlü + 38 olası = 303 belge** (≈ %9); **yeni: 3.169** (≈ %91).
- Örtüşme pakette değil, pakette olmayan PDF'lerde: paketin %1,6'sı (50 / 3.065), pakette olmayanların %62'si
  (253 / 407). Neden: pakette olmayan 479 PDF'in 320'si 2026 tarihli; HUKDOK'a karar yüklemesi 04.2026'da başlıyor.
- Not 1 — *aynı esas, başka derece*: HUKDOK'taki istinaf / temyiz kararı çoğu kez ilk derece esas numarasıyla
  kayıtlı; yalnız esas numarası tutan eşleşme aynı belge sayılmadı (örneklerde hepsi farklı karardı).
- Not 2 — *tarih tutuyor, esas tutmuyor*: aynı nedenle üst derece kararlarında esas no ayrışıyor; aynı kart + aynı
  gün + aynı derece güçlü sayıldı.
- Güçlü eşleşenlerin 9'unda derece çelişiyor (arşiv adı ilk derece mahkemesini, HUKDOK türü üst dereceyi gösteriyor).
- Olası sınıfın tarih farkı çoğunlukla 90 günden büyük: HUKDOK'taki belge tarihi karar tarihi olmayabiliyor.

**Karta bağlı olmayan arşiv belgeleri (1.065 = 985 föysüz + 8 iki kartlı + pakette olmayan föysüz 72):** kart
olmadığı için ölçülemez. HUKDOK belgelerinde esas no + tarih ile arandı: 12'si tek karta işaret ediyor (hepsi pakette
olmayan PDF); yalnız esas no ile 81'i tek karta, 4'ü birden çok karta gidiyor (zayıf; esas no mahkemeler arasında
tekil değil); 968'inde isabet yok. Adaylar V1 listesine "aday kart" sütunu olarak eklenir, kendiliğinden bağlanmaz.

**Ters yön — HUKDOK'ta olup arşivde karşılığı bulunmayan:** 500 karar kaydının 280'inin (258 güçlü + 22 olası)
arşivde karşılığı var, 220'sinin yok (143'ünün kartına bağlı hiç arşiv belgesi yok; 139'u 2026 tarihli). 320 rapor
kaydının hiçbirinin karşılığı yok: arşivdeki 302 raporun 295'i föysüz, karta bağlanamıyor. Arşiv HUKDOK'un üst kümesi
değil; 2026 için HUKDOK daha güncel.

**2. adıma etkisi.** Mükerrer riski ≈ 300 belgeyle sınırlı; parmak izini geriye dönük almak gerekirse yalnız HUKDOK'taki
500 karar kaydının asıl dosyası yeterli (2.480'in tamamı değil). 1. adımın kalanı: belge türü eşleme kuralı
(arşiv adındaki mahkeme / derece → HUKDOK tür kodu) ve V1-V4 listelerinin son hâli.

## 5.3 Karar → föy eşleştirmesi (teslim paketine karşı, 05.10.2026 akşam)

Kullanıcı düzeltmesi (05.10): föyler bu kararlardan üretildi; her karar teslim paketindeki bir föyle eşleşmelidir.
§5'teki hesap föyü yalnız dosya adındaki numaradan alıyordu (`YOKSIS` = föysüz). Bu ölçüm föyü **paketin kendi
künyesinden** arar. Yazma yok. Kaynak: `Masaüstü\hukdok_kararlar` (4.078 dosya) ↔ 01.10.2026 paketi (`Sheet` 8.408 föy +
`Karar_Asamalari` 8.923 satır + `Kapsam_Dışı` 58 + `Silinen_Föyler` 12). Betik ve çıktılar depo dışında:
`C:\hukdok-veri\lexis\kararlar\foy_esle.py`, `rapor\foy_esleme_2026-10-05.xlsx` (sınıf başına sayfa, satırda neden).
§5'teki 985 "föysüz"ün 454'ü PDF'i olmayan paket belgesidir; bu ölçümün kapsamı dışındadır (yalnız klasördeki dosyalar).

**Adında föy numarası olan 3.472 dosya** — numaraların tamamı pakette var (eksik föy 0):

| Sonuç | Dosya | Açıklama |
| --- | --- | --- |
| Föy + föyün aşama satırı tuttu | 3.198 | 2.731 esas + tarih · 313 esas + mahkeme · 34 tarih + mahkeme · 102 yalnız esas · 18 yalnız tarih / künyesiz satır |
| Künye aynı dosyanın başka föyünde | 24 | Föy doğru; aşama yalnız kardeş föyde yazılı |
| Föy var, aşaması pakette tutmuyor | 243 | 98 istinaf aşaması hiç yok · 24 temyiz aşaması hiç yok · 96 aynı mahkeme başka esas / tarihle · 25 aynı derecede başka mahkeme |
| Föy numarası şüpheli | 7 | Künye bu föyde yok, başka bir föyde tam tutuyor |

**Föy numarası olmayan 606 dosya** (594 `YOKSIS` + 3 `_EMSAL` + 8 kalıp dışı PDF + 1 `.udf`):

| Sonuç | Dosya | Nasıl / neden |
| --- | --- | --- |
| Föy bulundu — künyeyle | 32 | 26 esas + tarih · 5 esas + mahkeme · 1 tarih + mahkeme |
| Föy bulundu — karar metniyle | 300 | 143 föyün esas nosu + taraf adı metinde · 24 iki tarafın adı · 133 taraf adı + aynı mahkeme |
| Aday var, bağlanmadı | 163 | 151 yalnız taraf adı tutuyor (29 üst derece, 122 yerel) · 9 yalnız esas · 3 tarih + mahkeme |
| İlişkili föy | 7 | Aynı tarafların başka yargı kolundaki davasının föyü var; bu davanın föyü pakette yok |
| Föy bulunamadı | 103 | 61 metinde büro avukatı yok (dış / emsal karar olabilir; 3'ü `_EMSAL`) · 33 büro avukatı var, föyü pakette yok · 9 taranmış PDF |
| Karar değil | 1 | UYAP kaydı (`.udf`) |

- **Föye bağlanan: 3.797 / 4.078 (%93)**; `YOKSIS` dosyaların 332'si (%55) föyünü buldu. Belgesi olan föy 2.269, kart 2.054.
  Föyü bulunan 332 dosyanın 10'u birden çok karta gidiyor (kart seçilmedi).
- **Yöntemin sınaması** (föyü bilinen 3.472 dosyada föy numarası gizlenerek): künye kademeleri 3.090 / 3.101 doğru;
  esas + taraf 325 / 328; esas da gizlenince taraf + aynı mahkeme 2.457 / 2.476, iki taraf 484 / 511. Yalnız taraf adı:
  üst derecede 92 / 107, yerelde 48 / 93 — bu yüzden bağ değil **aday** sayıldı.
- Metinle bulunan 300 dosyanın 182'sinde föy aynı mahkemeyi başka esasla taşıyor (çoğu usulden ret / bozma sonrası yeni
  esas alan dosyanın önceki turu), 89'unda bu mahkemenin aşaması föyde hiç yok, 29'unda aşama satırı künyesiz açılmış.
- Ters yön: pakette karar tarihi yazılı 4.041 föyün 2.184'ünün (kendisinin ya da aynı dosyadaki föyün) PDF'i klasörde var.
- V1 / V2 listeleri bu ölçümle yeniden kurulur: V1 = aday 163 + ilişkili 7 + bulunamayan 103 + şüpheli 7; V2 = aşaması
  tutmayan 243 + metinle bulunup aşaması olmayan 271.

## 5.4 İlk aşama: eşleşenlerin lokalde eklenmesi (2. adımın ilk dilimi, 05.10.2026 gece)

Kullanıcı kararı (05.10): "ilk aşamada eşleşenler üzerinden gidelim"; şema eki (parmak izi + aşama bağı) onaylandı.

- **Şema:** migrasyon 60 — `case_documents.dosya_sha256`, `case_documents.asama_karari_id`
  (→ `case_stage_decisions`, `ON DELETE SET NULL`); kart başına aynı dosya tek kayıt (`uq_case_docs_kart_sha`, kısmi,
  koşulsuz op'ta). Mevcut belgelerde iki kolon boş.
- **Script:** `backend/scripts/arsiv_karar_ekle.py` (varsayılan kuru koşu; girdi depo dışındaki eşleştirme listesi,
  kart föy numarasından çözülür — liste lokal kart numarasına bağlı değil). Test: `tests/test_arsiv_karar_ekle.py`.
- **İlk aşama kümesi:** tek karta giden ve HUKDOK'ta kaydı olmayan **3.333 dosya, 1.903 kart** — 2.929 föy + aşama,
  232 föy var / aşaması pakette yok, 31 künyeyle bulunan, 141 metinde esas + taraf adıyla bulunan. Dışarıda: HUKDOK'ta
  zaten olan 303, birden çok karta giden 3, olası eşleşen 150 (taraf + mahkeme / iki taraf; ikinci tur).
- **Lokalde uygulandı** (öncesi yedek `C:\hukdok-veri\yedek\pre_arsiv_karar_20261005.dump`): 3.333 belge kaydı —
  2.042 gerekçeli karar, 894 istinaf, 301 Danıştay, 96 Yargıtay. İkinci koşu 3.333 `ZATEN_VAR` (yeniden koşulabilir).
  Hukukbot kuyruğuna ve bildirimlere satır düşmedi.
- **Aşama bağı:** 2.452 belge kartın aşama kararına bağlandı; 881'i boş: 355'inde pakette aşama künyesi yoktu, 433'ünde
  künye yalnız paketin ana sayfasında (kartın alanlarında) — `case_stage_decisions`'ta satırı yok, 92 kartta hiç aşama
  kaydı yok, 1'inde iki satır aynı künyeyi taşıyor.
- **Arşive yükleme (05.10 gece, kullanıcı kararı: "hepsini yükle"):** `arsiv_karar_ekle.py --yukle` 3.333 PDF'i
  gerçek SharePoint arşivine (`02_YEDEK_ARSIV`) yükledi ve `sharepoint_url`'i yazdı — 3.332 yeni yükleme, 1 dosya
  arşivde zaten vardı (aynı boyut; yeniden yüklenmedi). Süre ≈ 20 dk (4 iş parçacığı), 1,1 GB. Yüklemeden önce her ad
  arşivde arandı: **ad çakışması 0** (küçük dosya yüklemesi aynı adı sormadan ezer; script önce bakar, boyutu farklı
  dosyaya dokunmaz). Rastgele 25 + ilk 6 belge arşivden geri indirildi, parmak izleri kayıtla aynı. Yükleme
  `upload_queue`'dan geçmedi: bildirim ve Hukukbot kuyruğu yine boş (`export_outbox` 420 → 420). **Dosyalar artık gerçek
  arşivde durduğu için prod'a geçişte yeniden yüklenmez; prod'da yalnız belge kayıtları açılır ve URL'ler bağlanır**
  (`--yukle` aynı boyutlu dosyayı `ARSIVDE_VARDI` sayıp URL'ini alır).
- **İkinci tur ve ayıklama (05.10 gece; kullanıcı açık kalemlerde kararı bize bıraktı):**
  - *Olası eşleşenler:* taraf adı + aynı mahkeme ile bulunan 127 karar EKLENDİ (sınamada 2.457 / 2.476 doğru); belge
    özetinde "olası eşleşme" notu taşır. İki tarafın adıyla bulunan 23 karar (mahkeme tutmuyor; sınamada 484 / 511)
    EKLENMEDİ.
  - *Föy numarası şüpheli 7 karar:* karar metnindeki taraf adları tek föyü destekliyorsa o föye, ikisini de destekliyorsa
    dosyanın yargı koluyla aynı olana bağlandı → 6'sı eklendi (4'ü adındaki föye, 2'si künyesi tutan föye); 1'inde adlar
    bir föyü, yargı kolu ötekini gösteriyor, eklenmedi.
  - *Kopya taramalar:* aynı kart + aynı tarih / mahkeme / esas grubunda metni aynı (212) ya da çok yakın (143) olan
    **355 belge** kopya sayılıp kayıttan çıkarıldı (soft-delete, yönetim panelinden geri alınır; gerekçede kalan belgenin
    numarası). Kalan: metin katmanı olan, nüsha eki olmayan. Metni farklı 11 ve taranmış olduğu için karşılaştırılamayan
    4 belge DURUYOR. Arşivdeki dosyalara dokunulmadı.
  - *Bağlanamayan 273 karar* (aday 163 + föyü bulunamayan 103 + başka yargı kolu 7) ve yukarıdaki 23 + 1 EKLENMEDİ:
    tahmin edilmez, veri ekibine listelenir (V1).
  - **Lokal son durum: 3.111 arşiv belgesi, 1.924 kart**; ikinci turun 133 PDF'i de arşive yüklendi (çakışma 0).
    Prod için tek girdi listesi: `C:\hukdok-veri\lexis\kararlar\rapor\arsiv_karar_liste_prod.csv` (3.111 satır; lokale
    karşı kuru koşu 3.111 `ZATEN_VAR`). Arşivde kayda bağlı olmayan 355 kopya dosya duruyor (silinmedi).
- **Bilinen sınırlar:** (1) Belge kayıtları yalnız LOKAL veritabanında; prod kartlarında görünmez (dosyalar arşivde
  kayıtsız duruyor). (2) `uploaded_at` karar tarihidir (yükleme anı değil) — "son
  belgeler" ve günlük aktivite raporu dolmasın diye; iz `uploaded_by = ARSIV_AKTARIM:<kim>`. (3) Kopya ayıklama
  depo dışındaki betikle (`C:\hukdok-veri\lexis\kararlar\kopya_ayikla.py`) yapıldı; prod'da ayıklama gerekmez — prod
  listesi kopyaları içermez. (4) Gerçek girişle ekrandan tıklanmadı (ajan Microsoft girişini yapamaz). HTTP düzeyinde
  doğrulandı: uygulamanın kendi uçlarıyla bir kartta `GET /api/cases/{id}` kararları URL'leriyle döndü,
  `/api/documents/{id}/download?inline=true` dört kararı arşivden PDF olarak verdi; aynı yanıt Lexis servisinin
  `dosya_getir` koduna verildiğinde kararlar "KARAR" türüyle listelendi.

## 6. Kullanıcıdan beklenen kararlar

1. Büro arşivi HUKDOK'a girsin mi (bu planın ön koşulu) ve 985 föysüz belge nasıl dursun?
2. Belge kaydına parmak izi ve aşama bağı eklensin mi (şema değişikliği)?
3. Hukukbot'a adlar açık mı gitsin, maskeli mi?
4. Depo türü: yönetilen depoda kalmak mı, kendi vektör veritabanı mı?
5. Dış kararlar (21.602; Lexis'te metin olarak hazır, ince ayrım yok) Hukukbot'a ne zaman, hangi rafla?

## 7. Değişmeyen kurallar

- Gemini'ye onaysız gönderim yok; kişi verisi repoya, dokümana ve sohbete girmez.
- Prod'a yazma, push ve deploy yalnız kullanıcı kararıyla; toplu yazma mesai dışında.
- Lexis servisi HUKDOK veritabanına bağlanmaz (K9); HUKDOK'a yazan iş HUKDOK deposunda, HUKDOK'un kendi
  script'iyle yapılır.
- Adım başına tek commit: kod + test + doküman birlikte.
