# Ofis dosya numarası (ofis no) formatı — veri ekibi için

**Tarih:** 26.09.2026 · **Muhatap:** veri ekibi · **Karşı taraf:** HUKDOK

Bu belge, HUKDOK'ta her dava kartına verilen **ofis dosya numarasının** (içeride `tracking_no`)
nasıl kurulduğunu anlatır. Ofis numarasını **siz üretmezsiniz** ve teslim paketi ona dokunmaz
(`SOZLESME.md` §10, "Kart / iş akışı" satırı). Numarayı cevap dosyalarında görürsünüz
(`eslesme_<teslim>.csv` → `tracking_no` sütunu, sözleşme §8); bu belge onu okuyup
yorumlayabilmeniz içindir.

Anlatılan her kural sistemdeki koddan okunmuştur:

- `frontend/src/lib/caseNumberUtils.ts`: yeni kart açılırken numarayı üreten kod.
- `backend/scripts/retag_tracking_nos.py`: numara tablolarının kanonik (esas) kopyası. Paketten
  kart açan script (`backend/scripts/kartsiz_foy_kart_ac.py`) de numarayı bu kopyayla üretir.
- `backend/routes/cases.py`: sıra numarası (`max_tracking_sequence`, `/api/cases/client-sequence`).

---

## 1. Genel görünüm

Numara, noktayla ayrılmış beş bloktan oluşur ve toplam **30 karakterdir**:

```
B1 . B2         . B3   . B4    . B5
S2 . ANADOLU... . 0007 . HUKUK . 00100
```

| Blok | Uzunluk | Anlamı |
| --- | --- | --- |
| B1 | 2 | Müvekkil kategorisi (sigorta şirketinde şirket kodu) |
| B2 | 10 | Müvekkil ad bloğu (kısa ad, eksik kalan yer `.` ile dolar) |
| B3 | 4 | Aynı ad bloğu içindeki sıra numarası |
| B4 | 5 | Yargı süreci türü |
| B5 | 5 | Hizmet türü işaretleri (0/1) |

Dikkat: B2'nin içindeki dolgu noktaları, bloklar arasındaki ayırıcı noktayla yan yana gelir
(`ANADOLU...` + `.` → `ANADOLU....`). Numarayı bölerken noktaya göre değil, **konuma göre**
bölün: B1 = 1-2. karakter, B2 = 4-13, B3 = 15-18, B4 = 20-24, B5 = 26-30.

Bir kartta birden çok müvekkil varsa B1 ve B2 farklı müvekkillerden gelebilir (bkz. §2.3 ve §3.3).

---

## 2. B1 — kategori kodu

### 2.1 Kategori tablosu

Müvekkilin kategorisine göre:

| Müvekkil kategorisi | Kod |
| --- | --- |
| Doktor | `D1` |
| Sağlık Çalışanı | `D2` |
| Özel Hastane | `H2` |
| Sigorta | `S0` (şirket tanınırsa aşağıdaki kod) |
| Hasta | `H1` |
| Diğer / kategorisi bilinmeyen | `X1` |

Eşleştirme "kategori adı bu kelimeyi içeriyor mu" diye ve tablodaki sırayla yapılır; bu yüzden
"Özel Hastane", "Hasta"dan önce denenir (yoksa "Özel Hastane" de `H1` olurdu).

### 2.2 Sigorta şirketleri

Müvekkilin kategorisinde ya da adında "SİGORTA" geçiyorsa kod önce `S0` olur; ardından adında
aşağıdaki sözcüklerden biri geçiyorsa (tablodaki sırayla, ilk tutan kazanır) şirket kodu verilir:

| Adında geçen | Kod |
| --- | --- |
| AK | `S1` |
| ANADOLU | `S2` |
| AXA | `S3` |
| CORPUS | `S4` |
| QUICK | `S4` |
| EUREKO | `S5` |
| NIPPON | `S6` |
| SOMPO | `S7` |

Corpus ve Quick aynı kodu (`S4`) taşır. Tanınmayan sigorta şirketi `S0` kalır.

Bilmeniz gereken iki davranış:

- Arama "içeriyor mu" diye yapılır, kelime bazında değil. Adında "AK" harf dizisi geçen her
  sigorta şirketi `S1` alır (ör. "Başak ... Sigorta" → `S1`).
- Adlar aranmadan önce Türkçe karakterlerden arındırılır (ı→i, İ→I, ş→s ...), bu yüzden
  küçük harfle yazılmış "Quick Sigorta" `S4`, "Nippon Sigorta" `S6` alır; yeni kart ekranları ile
  kanonik kopya (`retag_tracking_nos.py`) aynı sonucu verir. **Eski numaralarda istisna:** bu
  düzeltme (G223) yayına alınmadan önce yeni kart ekranı adı Türkçe büyük harfe çeviriyordu
  ("QUİCK"/"NİPPON" tanınmıyordu); o dönemde açılmış Quick/Nippon kartlarında `S0` görebilirsiniz.
  Mevcut numaralar geriye dönük değiştirilmez.

### 2.3 Birden çok müvekkil

B1 için kartın **bütün** müvekkillerine bakılır ve en özgül kod seçilir:
tanınan sigorta şirketi (`S1`-`S7`) > `S0` > `D1` > `D2` > `H2` > `H1` > `X1`.

### 2.4 B1'i kategori kaynağı olarak kullanmayın

B1 numara açılırken bir kez yazılır ve sonradan müvekkilin kategorisi değişse de güncellenmez.
Ayrıca yeni kart ekranlarında (dava açma sihirbazı ve belge ile kart açma) sigorta dışı
müvekkillerde B1'in `X1` yazıldığı bir hata vardı; düzeltildi (G223) — düzeltme yayına
alındıktan sonra açılan numaralarda B1 yukarıdaki tabloya uyar. **Eski numaralarda** (düzeltme
öncesi açılmış kartlarda) kategorisi Doktor/Hasta vb. olan müvekkillerde `X1` görülebilir; mevcut
numaralar geriye dönük değiştirilmez. Müvekkil kategorisinin doğru kaynağı müvekkil kaydıdır,
numaranın ilk iki harfi değil.

---

## 3. B2 — ad bloğu

Her zaman **10 karakter**. Türkçe harfler önce Latin karşılığına çevrilir
(ı→I, ğ→G, ü→U, ş→S, ö→O, ç→C, İ→I), sonra her şey büyük harfe çevrilir ve harf ile boşluk
dışındaki her şey (rakam, nokta, tire, kesme) silinir.

### 3.1 Kişi müvekkil

Kategori Doktor, Sağlık Çalışanı, Hasta, Bireysel ya da **boş** ise kişi kuralı uygulanır:

- Ad tek kelimeyse: o kelime.
- Birden çok kelimeyse: **ilk kelimenin baş harfi + `_` + son kelime**. Göbek adı/ikinci ad
  atlanır.
- Sonuç 10 karakterden kısaysa sağa `.` eklenir, uzunsa 10. karakterden kesilir.

| Ad | Ad bloğu |
| --- | --- |
| Ayşe Gül Öztürk | `A_OZTURK..` |
| Mehmet Ali Er | `M_ER......` |
| Abdurrahman Karaosmanoğlu | `A_KARAOSMA` |
| Mehmet | `MEHMET....` |

Ad "Dr." gibi bir unvanla başlıyorsa unvan ilk kelime sayılır: "Dr. Ali Rıza Çelik" →
`D_CELIK...`.

### 3.2 Şirket / kurum müvekkil

Kategori yukarıdakilerden biri değilse (Özel Hastane, Sigorta, Diğer vb.) kurum kuralı
uygulanır: şirket türü ve genel sözcükler atılır, **kalan ilk anlamlı kelime** alınır (tek
harfli kelimeler de atılır). O kelime 10 karakterde kesilir, kısaysa sağa `.` eklenir.

Atılan genel sözcükler (Türkçe karakterden arındırılmış hâlleriyle):
SIGORTA, HAYAT, ANONIM, TURK, SIRKETI, KOOPERATIFI, TIC, TICARETI, SAN, SANAYI, SANAYII,
INS, INSAAT, TAAHHUT, LTD, STI, AS, HASTANE, HASTANESI, SAGLIK, HIZ, HIZMETLERI, HIZM, OZEL,
TIBBI, MALZ, SITE, SITESI, YONETICILIGI, YONETIM, KURULU, MERKEZ, VE, VEYA, PAZ, PAZARLAMA,
DAG, DAGITIM, ORG, ORGANIZASYON, YAPIM, TANITIM, URETIM, ISLETMECILIGI, DANISMANLIK, GLOBAL,
SISTEMLERI, HIZMETLER.

Adın bütün kelimeleri bu listedeyse ham ilk kelime alınır.

| Ad | Ad bloğu |
| --- | --- |
| Özel Yıldız Hastanesi A.Ş. | `YILDIZ....` |
| Anadolu Anonim Türk Sigorta Şirketi | `ANADOLU...` |
| XYZ Ltd. Şti. | `XYZ.......` |
| Özel Hastane A.Ş. | `OZEL......` (hepsi genel sözcük) |

"A.Ş." noktalar silinince "AS" olur ve atılır.

### 3.3 Birden çok müvekkil

Ad bloğu için tek bir müvekkil seçilir: Doktor > Sağlık Çalışanı > Hasta > Bireysel >
kategorisi boş > diğer kurumlar > sigorta. Yani doktor + sigorta şirketi müvekkilli bir kartta
B1 sigortadan (`S3` gibi), B2 doktordan (`A_OZTURK..` gibi) gelir.

---

## 4. B3 — sıra numarası

- **4 hane**, soldan sıfırla doldurulur (`0001`, `0012`).
- Değer: **aynı ad bloğunu (B2) taşıyan kartlardaki en büyük sıra numarası + 1**. Sayım yalnız
  B2'ye bakar; B1, B4, B5 farklı olsa da aynı ad bloğundaki kartlar tek sırayı paylaşır.
- **Silinmiş kartlar da sayılır**: silinen kartın numarası tekrar verilmez. Aynı numara iki
  karta verilemez (veritabanında tekillik kuralı var).
- Bu desene uymayan eski/serbest biçimli numaralar sayımda yok sayılır.

Sonuç: aynı B2'li kartlarda sıra numarası boşluklu olabilir (silinen kartlar) ve açılış
tarihine göre sıralı olmak zorunda değildir.

---

## 5. B4 — yargı süreci kodu

Kanonik tablo (`retag_tracking_nos.py`):

| Dava türü | Kod |
| --- | --- |
| Hukuk | `HUKUK` |
| İdari Yargı | `IDARE` |
| İdare | `IDARE` |
| Ceza | `CEZAA` |
| İcra | `ICRAA` |
| Arabuluculuk | `ARABU` |
| Savcılık | `SAVCI` |
| Tahkim | `TAHKM` |
| Vergi | `VERGI` |
| Danışmanlık | `DANIS` |

Tür boş ya da tabloda yoksa `HUKUK` yazılır. "İdari Yargı" türü 17.09.2026'da "İdare"ye
katıldı; o tarihten önce açılmış bazı kartlarda eski `IDARI` kodu görülebilir, bu numaralar
değiştirilmez.

---

## 6. B5 — hizmet türü işaretleri

5 haneli bir **işaret dizisidir**; her hane bir hizmete karşılık gelir, `1` = var, `0` = yok.
Birden çok hane `1` olabilir.

| Hane (soldan) | Hizmet |
| --- | --- |
| 1 | Rapor |
| 2 | Danışmanlık |
| 3 | Dava |
| 4 | İcra |
| 5 | Yazışma |

Örnek: `00100` = yalnız Dava; `11000` = Rapor + Danışmanlık; `00000` = işaretlenmemiş
(varsayılan; hızlı kart açma ve paketten açılan kartlar da `00000` yazar).

Bu blok kartın `service_type` alanından gelir ve paketinizdeki **"Hizmet Türü" sütunuyla ilgisi
yoktur** (o sütun kartta ayrı bir alana, `hizmet_turu`'na yazılır).

---

## 7. Biçim kontrolü (doğrulama kalıbı)

Kodda tanımlı kontrol kalıbı:

```
^[A-Z0-9]{2}\.[A-Z0-9_.]{10}\.[A-Z0-9]{4}\.[A-Z0-9]{5}\.[A-Z0-9]{5}$
```

Okunuşu:

1. 2 karakter büyük harf ya da rakam (B1), sonra nokta;
2. 10 karakter büyük harf, rakam, `_` ya da `.` (B2), sonra nokta;
3. 4 karakter büyük harf ya da rakam (B3), sonra nokta;
4. 5 karakter büyük harf ya da rakam (B4), sonra nokta;
5. 5 karakter büyük harf ya da rakam (B5), başka hiçbir şey yok.

Küçük harf, Türkçe karakter, boşluk ya da fazladan karakter olan numara bu kalıba uymaz.

Bu kalıp bir **referanstır**: sistem kart kaydederken numarayı bu kalıba göre reddetmez;
kaydı engelleyen tek kural numaranın tekil olmasıdır. Bu yüzden eski kartlarda kalıba uymayan
numaralar olabilir (ör. geçmişte yeniden numaralandırma sırasında çakışan numaraya eklenen
`-2`, `-3` sonekleri). Kalıba uymayan numarayı hata saymayın; sadece blok blok
yorumlanamayacağını bilin.

---

## 8. Örnekler

Aşağıdaki üç numara kurallarla elle türetildi ve §7'deki kalıba karşı denendi (üçü de uyuyor).

**Örnek 1 — kişi müvekkil.** Müvekkil "Ayşe Gül Öztürk" (Doktor), dava türü Hukuk, hizmet Dava,
bu ad bloğunda daha önce en büyük sıra 0002.

- B1: Doktor → `D1`
- B2: kişi kuralı → ilk harf A + `_` + son kelime OZTURK = `A_OZTURK` → `A_OZTURK..`
- B3: 0002 + 1 → `0003`
- B4: Hukuk → `HUKUK`
- B5: yalnız Dava → `00100`

```
D1.A_OZTURK...0003.HUKUK.00100
```

**Örnek 2 — şirket müvekkil.** Müvekkil "Özel Yıldız Hastanesi A.Ş." (Özel Hastane), dava türü
İcra, hizmet İcra, önceki en büyük sıra 0011.

- B1: Özel Hastane → `H2`
- B2: kurum kuralı → OZEL, HASTANESI, AS atılır, ilk anlamlı kelime YILDIZ → `YILDIZ....`
- B3: 0011 + 1 → `0012`
- B4: İcra → `ICRAA`
- B5: yalnız İcra → `00010`

```
H2.YILDIZ.....0012.ICRAA.00010
```

**Örnek 3 — sigorta şirketi.** Müvekkil "Anadolu Anonim Türk Sigorta Şirketi" (Sigorta), dava
türü Hukuk, hizmet Dava, önceki en büyük sıra 0006.

- B1: adında SİGORTA var → `S0`; adında ANADOLU geçiyor → `S2`
- B2: kurum kuralı → ANONIM, TURK, SIGORTA, SIRKETI atılır, ilk anlamlı kelime ANADOLU →
  `ANADOLU...`
- B3: 0006 + 1 → `0007`
- B4: Hukuk → `HUKUK`
- B5: yalnız Dava → `00100`

```
S2.ANADOLU....0007.HUKUK.00100
```

---

Sorunuz ya da bu kurallarla açıklanamayan bir numara görürseniz numarayı ve kart bilgisini
bize iletin.
