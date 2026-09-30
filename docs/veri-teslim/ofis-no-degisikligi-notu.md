# Ofis dosya numarası değişiyor — veri ekibi için not

> **TASLAK — GÖNDERİLMEDİ.** Gönderim insan kararıdır. Bu metin 30.09.2026'da koddan
> (`backend/services/ofis_no.py`, `backend/scripts/ofis_no_gocu.py`,
> `backend/scripts/cevapli_kart_eslemesi.py`; main `c40e10c`) okunarak hazırlandı.
> Gönderilmeden önce doldurulacak yerler `[…]` ile işaretlidir: göç tarihi ve eşleme
> dosyasının adı. **Göç henüz hiçbir veritabanında uygulanmadı** — not, göç tarihi
> kesinleştikten sonra gider.
>
> Bu not gönderildiğinde `ofis-no-formati.md` (26.09.2026) **geçersiz kalır**: o belge eski
> beş bloklu düzeni anlatır. `SOZLESME.md`'deki `ofis-no-formati.md` atıfı da bu nota
çevrilmelidir (açık iş — iki dosya G240 kapsamında değildi).

**Tarih:** `[gönderim tarihi]` · **Muhatap:** veri ekibi · **Karşı taraf:** HukuDok

Merhaba,

HukuDok'ta dava kartlarına verdiğimiz **ofis dosya numarasının** (cevap dosyalarımızdaki
`tracking_no` sütunu) biçimini değiştiriyoruz. Numarayı siz üretmiyorsunuz ve teslim paketi
ona dokunmuyor (sözleşme §10); sizin tarafınızda **paket biçiminde hiçbir değişiklik
gerekmiyor**. Bu not, cevap dosyalarımızda göreceğiniz yeni numarayı okuyabilmeniz ve
elinizdeki eski numaralı listeleri yenisiyle eşleyebilmeniz içindir.

## 1. Ne değişti

| | Eski | Yeni |
| --- | --- | --- |
| Biçim | noktayla ayrılmış beş blok, 30 karakter, `.` dolgulu | tireyle ayrılmış üç ya da dört blok, dolgu yok |
| Müvekkil kodu | iki haneli kod (`D1`, `S3`, `X1` …) | okunur kod: kategori (`DR`, `KR` …) ya da sigorta şirketinin adı (`AXA`, `ANADOLU` …) |
| Ad | 10 karaktere kesilir | kesilmez |
| Sigortalı hekim | numarada yok | sigorta dosyasında ayrı blok |
| Tür | beş harf (`HUKUK`, `IDARE`) | üç harf (`HUK`, `IDR`) |
| Hizmet bloğu (son beş hane) | var | **yok** |

```
<MÜVEKKİL KODU>-<SIRA>[-<SİGORTALI>]-<TÜR>
```

Bloklar arasında `-`, blok içinde `.` bulunur. Yalnız ASCII büyük harf kullanılır
(Ö→O, Ü→U, Ş→S, Ç→C, Ğ→G, İ/ı→I).

## 2. Örnekler

Eski biçimin görünüşü (hatırlatma): `S3.AXA........2915.IDARE.00000`,
`D1.A_VARAN....0002.IDARE.00000`.

Yeni biçim:

| Durum | Yeni numara |
| --- | --- |
| Doktor müvekkil | `DR.M.OZTURK-0003-HUK` |
| Kurum müvekkil | `KR.ENTHONE-0015-CEZ` |
| Sigortacı müvekkil + sigortalı hekim | `AXA-3297-DR.E.ALTUNC-HUK` |
| Sigortacı müvekkil, sigortalı bilinmiyor | `AXA-3297-HUK` |
| Listemizde olmayan sigortacı | `SG-0001-HUK` |

> Örnekler biçimi göstermek içindir, gerçek kart numarası değildir. Bir kartın eski ↔ yeni
> karşılığı yalnız eşleme dosyasındadır (§4).

**Müvekkil kodu.** Müvekkil sigorta şirketi değilse kategori kodu + ad: kişide
`<KOD>.<ilk adın baş harfi>.<SOYAD>`, kurumda `<KOD>.<ilk anlamlı kelime>`.

| Kategori | Kod |
| --- | --- |
| Doktor | `DR` |
| Sağlık Çalışanı | `SC` |
| Hasta | `HS` |
| Özel Hastane (Klinik dahil) | `OH` |
| Kurum (Acente, Dernek dahil) | `KR` |
| Bireysel | `BR` |
| Diğer | `DG` |

Müvekkil sigorta şirketiyse numara şirket koduyla başlar: `AK`, `ANADOLU`, `AXA`, `CORPUS`,
`QUICK`, `EUREKO`, `NIPPON`, `SOMPO`, `KORU`, `HDI`, `ZIRAAT`; listede olmayan sigortacı `SG`.
Bu listeler bizde yönetim panelinden düzenlenebilir; kod değişikliği yalnız **sonradan
açılan** kartları etkiler.

**Sigortalı bloğu** yalnız sigorta müvekkilli kartta bulunur ve TEK kişidir; kaynağı
öncelikle sizin paketinizdeki `Sigortalı` sütunudur. Bulunamazsa blok yazılmaz.

**Tür kodları:** Hukuk `HUK` · Ceza `CEZ` · İcra `ICR` · Arabuluculuk `ARB` · Savcılık `SAV` ·
İdare `IDR` · Tahkim `THK` · Vergi `VRG` · Danışmanlık `DAN`.

## 3. Sıra numarası hakkında

Sıra artık **müvekkil kodu başına** sayılır ("AXA'nın 3297. dosyası", "Dr. M. Öztürk'ün 3.
dosyası"). Geçişte tüm kartlar — silinmiş olanlar dahil — açılış tarihi sırasıyla yeniden
numaralanır; bu yüzden **yeni sıra eski sırayla aynı olmayabilir**. Eski numaradan yenisini
kuralla türetmeye çalışmayın; eşleme dosyasını kullanın.

Bir kartın numarası verildikten sonra **değişmez** — müvekkil, tür ya da sigortalı sonradan
düzeltilse de.

## 4. Eski → yeni eşleme dosyası

Geçişle birlikte size `[ofis_no_esleme_<tarih>.csv]` dosyasını ileteceğiz (UTF-8, virgülle
ayrılmış). Sütunlar:

| Sütun | Anlamı |
| --- | --- |
| `case_id` | bizim kart numaramız (cevap dosyalarındaki `case_id` ile aynı) |
| `eski` | kartın geçişten önceki ofis numarası |
| `yeni` | kartın yeni ofis numarası |
| `silinmis` | `1` = kart bizde silinmiş kayıt; `0` = yaşayan kart |
| `kategori_kaynagi` | müvekkil kodunun nereden çıktığı (iç bilgi) |
| `sigortali_kaynagi` | sigortalı bloğunun nereden çıktığı (iç bilgi) |

Nasıl kullanılır:

- Elinizdeki listelerde, notlarda ya da önceki cevap dosyalarımızda eski numara geçiyorsa
  `eski` sütununda arayıp `yeni` karşılığını alın. En güvenli anahtar `case_id`'dir —
  `eslesme_<teslim>.csv` dosyalarımızda numarayla yan yana durur ve geçişte değişmez.
- `kategori_kaynagi` ve `sigortali_kaynagi` sütunlarını işlemenize gerek yok.
- Dosya bir kez üretilir; geçişten sonra açılan kartlar doğrudan yeni numarayla doğar ve
  bu dosyada yer almaz.

## 5. Bekleyen cevaplı dosyalar — eski numara hâlâ tanınıyor

Sizde bekleyen cevaplı dosyalarda (örn. mükerrer kart listesinin `CEVABINIZ` sütunu) kart
numarasını **eski biçimde yazmış olmanız sorun değil**: cevabı okuyan aracımız iki biçimi de
tanır ve eski numarayı kartın bugünkü numarasına kendisi çevirir. Dosyaları yeniden
düzenlemenize gerek yok.

Geçişten sonra hazırlayacağınız yeni cevaplarda hangi biçimi kullanacağınız size kalmış;
ikisi de kabul edilir. Tanıyamadığımız (eşlemede bulunmayan) bir numara tahmin edilmez —
o satırı size geri sorarız.

## 6. Sizin tarafınızda değişmeyenler

- Teslim paketinin yapısı, sütunları ve sözleşme kuralları aynı.
- Eşleşme köprüsü aynı: `SistemNo`, `DosyaNo` ↔ klasör no, `TKU`.
- Cevap dosyalarımızın sütunları aynı; yalnız `tracking_no` sütunundaki değerin biçimi
  geçişten sonra yenidir.
- HukuDok'ta eski numarayla arama çalışmaya devam eder.

Geçiş tarihi: `[tarih]`. Sorularınız için bize yazabilirsiniz.
