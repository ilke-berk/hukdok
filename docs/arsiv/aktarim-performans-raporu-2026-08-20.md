# Föy aktarımı performans raporu — 2026-08-20

> Tarihli koşu raporu (arşiv). Buradaki sayılar **2026-08-20 sabahı lokal stack'te
> fiilen koşularak** ölçüldü; ileride kod değişirse bu dosya düzeltilmez, yeni rapor
> yazılır. Ölçüm HEAD = `dea787e` (G076), girdi = `HUKDOK_TESLIM_PAKETI_2026-08-18.xlsx`
> (4,2 MB, 8.409 veri satırı).

## Nasıl ölçüldü

Çalışan lokal veritabanına (`hukudok`) **yazılmadı**. Ölçüm için prova öncesi dump
(`C:\hukdok-veri\yedek\lokal_prova_oncesi_20260819.dump`) ayrı bir şemaya
(`hukdok_perf`) geri yüklendi, migrasyonlar koşturuldu ve aktarım orada **iki kez**
gerçek yazımla koşuldu. Ayrıca çalışan DB üzerinde bir kuru koşu alındı.

| Koşu | Veritabanı | Başlangıç durumu | Yazım |
| --- | --- | --- | --- |
| Kuru koşu | `hukudok` (çalışan) | aktarım uygulanmış | yok (geri alındı) |
| Koşu 1 (soğuk) | `hukdok_perf` | 14.345 kart · 0 föy | EVET |
| Koşu 2 (tekrar) | `hukdok_perf` | koşu 1 sonrası | EVET |

Koşu 2 sonrası `hukdok_perf` satır sayımları, çalışan DB'nin sayımlarıyla **birebir
aynı** çıktı (14345 / 8156 / 229 / 66435 / 16562 / 50661 / 4971 / 1112) — aktarım
tekrarlanabilir.

## 1. Hız

| Koşu | Süre | Satır/sn | Yazılan satır |
| --- | --- | --- | --- |
| Koşu 1 (soğuk, tam yazım) | **93,2 sn** | 90 | ~71.900 |
| Koşu 2 (değişiklik yok) | **35,2 sn** | 239 | 0 |
| Kuru koşu (çalışan DB) | 40,9 sn | 206 | 0 |

Okuma + normalize + kart eşleştirme tabanı ≈ **35 sn**; yazımın maliyeti ≈ **58 sn**.
8.409 satırlık tam paket tek transaction'da sorunsuz aktı; parti başına commit'e
ihtiyaç duyulmadı (G064'ün açık bıraktığı soru bu koşuyla kapandı).

Pratik sonuç: **tam aktarım bir buçuk dakika sürüyor.** Mesai dışı koşma şartı
performanstan değil, belge envanteri kapısının eşzamanlı yüklemeye karşı
muhafazakâr olmasından geliyor.

## 2. Kapsam ve eşleşme

| | Satır | Oran |
| --- | --- | --- |
| Okunan | 8.409 | %100 |
| İşlenen (kart eşleşti) | **8.156** | **%97,0** |
| Atlandı (kart bulunamadı) | 217 | %2,58 |
| Satır hatası | 36 | %0,43 |

Hataların dağılımı: **33** belirsiz eşleşme (aynı Dosya No 2+ kartla eşleşiyor, esas
no + tür ikinci anahtarı da ayırmadı), **3** Dosya No boş.

Dokunulan kart: **6.425 / 14.345** (%44,8). Föy dağılımı: 5.220 kart tek föylü,
1.205 kart çok föylü (en kalabalığı 12 föy).

Atlanan 217 satırın Dosya No'ları ağırlıkla `2*` (87), `8000*` (25), `9*` (18)
öneklerinde toplanıyor — bunlar bizim `klasor_no_2` havuzunda karşılığı olmayan
numaralar; karşı tarafa borçlu düzeltme listesinin somut girdisi.

## 3. Yazılan alanlar

Toplam **40.908 alan değişikliği** (6.425 kart) + 16.561 avukat satırı + 804 taraf
satırı + 8.156 föy kimliği = 66.429 provenance kaydı.

| Alan | Değişiklik | Boştan doldu | Mevcut değerin üzerine |
| --- | --- | --- | --- |
| avukat (`case_lawyers`) | 16.561 | 16.561 | 0 |
| `case_foys.sistem_no` | 8.156 | 8.156 | 0 |
| `islah_tutari` | 6.409 | 6.409 | 0 |
| `subject` | 6.246 | 323 | **5.923** |
| `bureau_type` | 5.364 | 299 | **5.065** |
| `maddi_tazminat` | 4.675 | 0 | **4.675** |
| `arsiv_tarihi` | 3.346 | 3.346 | 0 |
| `acceptance_date` | 3.174 | 3.166 | 8 |
| `hasar_dosya_no` | 1.958 | 1.958 | 0 |
| `manevi_tazminat` | 1.150 | 0 | **1.150** |
| `hukuk_no` | 975 | 968 | 7 |
| tıbbi beşli (G044) | 3.846 | 3.846 | 0 |
| `dosya_son_durumu` | 817 | 19 | 798 |
| taraf (`case_parties`) | 804 | 804 | 0 |
| `responsible_lawyer_name` | 720 | 224 | 496 |
| `esas_no` | 595 | 0 | **595** |
| `sub_type` | 385 | 371 | 14 |
| hükmedilen üçlü | 951 | 951 | 0 |
| `status` | 149 | 0 | **149** |
| `court` | 71 | 27 | 44 |
| `opening_date` | 65 | 57 | 8 |
| `file_type` | 10 | 0 | 10 |

Aşama tarihçesi: **4.971 aşama satırı**, 517 önceki esas numarası, 8 havuz dışı
karar durumu.

**Dikkat çeken:** 40.908 değişikliğin **18.942'si mevcut bir değerin üzerine
yazıyor** (%46). En büyük kalemler `subject` (5.923), `bureau_type` (5.065),
`maddi_tazminat` (4.675), `manevi_tazminat` (1.150), `esas_no` (595), `status` (149).
Bu tasarım gereğidir (içerik farkında teslim kazanır, yazım farkında biz —
`ICERIK_KARSILASTIRMALI_ALANLAR`), ama **para alanlarında %100 üzerine yazma**
(maddi/manevi tazminatta boştan dolan satır YOK) tek başına gözden geçirmeye değer:
demek ki bu iki kolon zaten doluydu ve teslim paketinin değeri farklıydı.

## 4. İdempotentlik — DÜZELDİ

19.08 provasında bulunan kusur (çok föylü kartta `arsiv_tarihi` salınıyor, ikinci
koşu sıfır değişiklik vermiyor) **kapanmış.** Koşu 2 çıktısı:

```
  yeni föy          : 0
  güncellenen föy   : 8156
  alan değişikliği  : 0 (0 kart)
  avukat satırı     : 0
  taraf satırı      : 0
  aşama satırı      : 0 (önceki esas: 0)
```

Aynı girdiyle ikinci koşu **hiçbir tabloya tek satır eklemiyor, tek alan
değiştirmiyor**; `case_history` şişmiyor. İşletim modelinin (partili teslim +
dört düzeltme listesi) dayandığı şart sağlanmış durumda.

Belge envanteri her üç koşuda da **DENK** — `case_documents` bağları korundu.

Çıkış kodu üç koşuda da **1** (satır hatası var); bu beklenen sonuçtur, kart
bulunamayan satır koşuyu kırmızıya çekmiyor.

## 5. Kardeş föy çelişkileri — 5.008 satır

Aynı kart altındaki föyler arasında **5.008 künye uyuşmazlığı**, **1.180 kartta**.
Çok föylü kart sayısı 1.205 — yani **çok föylü kartların %97,9'unda en az bir
çelişki var.** En sık çelişen alanlar:

| Alan | Çelişki |
| --- | --- |
| `acceptance_date` | 984 |
| `bureau_type` | 971 |
| `opening_date` | 400 |
| `dosya_son_durumu` | 395 |
| `maddi_tazminat` | 363 |
| aşama:YEREL | 354 |
| `arsiv_tarihi` | 348 |
| `sub_type` | 246 |
| `status` | 181 |
| `responsible_lawyer_name` | 149 |
| `esas_no` | 48 · `karar_no` 35 · `court` 34 |

Bu oran, "kart = föylerin birleşimi" varsayımının çok föylü kartlarda **kural olarak
tutmadığını** gösteriyor. Çelişki raporu üretiliyor ama satırlar hâlâ
`dogrulama_durumu = BELIRSIZ` ile işaretlenmiyor (G064'ün opsiyonel bıraktığı
kalem) — 1.180 kart panelde "temiz" görünüyor.

## 6. TKU bulgusu — grup anahtarı aynı zamanda İLİŞKİ anahtarı

Kullanıcının 20.08'de işaret ettiği ayrıntı ölçüldü ve **doğrulandı**: ekip TKU
numarasını yalnız "aynı davanın föyleri" için değil, **farklı davaları
ilişkilendirmek** için de kullanmış.

Toplam **5.488 TKU grubu** (254 föy TKU'suz):

| Ölçüt | Grup |
| --- | --- |
| Birden çok **karta** yayılan | **593** |
| Birden çok **mahkemeye** yayılan | **400** |
| Birden çok **esas yılına** yayılan | **291** |
| Açılış tarihleri arası > 1 yıl | 242 |
| Açılış tarihleri arası > 3 yıl | **132** |
| Birden çok **dosya türüne** yayılan | **369** (347×2 tür, 21×3, 1×4) |

Karışık tür desenleri: **Arabuluculuk+Hukuk 139**, Hukuk+İcra 72, Hukuk+İdare 61,
Ceza+Hukuk 30, Ceza+İdare 27, Hukuk+Savcılık 5.

İki kanıt vakası:

* **TKU-402** — üç ayrı kart: `Şanlıurfa 1. Tüketici` 2017/162 ve `Şanlıurfa
  Tüketici` 2017/190 (2017 açılışlı), artı `Şanlıurfa 1. Tüketici` 2024/216
  (2024-02-02 açılışlı). Mahkeme değişmiş, dava yıllar sonra yeniden açılmış;
  ekip üçünü TKU ile bağlamış.
* **TKU-4724** — `ARB-15021` (Arabuluculuk, 2023/33233, 22.05.2023) ile `H-15030`
  (İzmir 2. Tüketici, 2023/416, 13.08.2023): arabuluculuk ve ardından açılan
  hukuk davası aynı TKU altında.

**İyi haber:** aktarım bunları BİRLEŞTİRMEDİ — eşleştirme `klasor_no_2` üzerinden
gittiği için üç kart üç kart olarak kaldı, çelişki raporu da KART bazlı çalışıyor
(5.008 çelişkinin tamamı `kume=KART`), yani TKU yayılması sahte çelişki üretmiyor.

**Kötü haber:** bu ilişki bilgisi şu an **hiçbir yere yazılmıyor.** `case_foys.tku_no`
dolu ama `cases.tku_no` yazılmıyor ve `case_relations` tablosunda **1 satır** var.
Yani 593 çok kartlı TKU grubunun taşıdığı "bu davalar aynı olayın parçası" bilgisi
veritabanında var, arayüzde yok.

Bu, FAZ F gereksinim belgesinin §4 maddesinde ("TKU grup raporu — çok üyeli TKU
gruplarının `case_relations`'ta nasıl karşılandığı") **soru olarak** duruyordu;
artık soru değil, ölçülmüş bir gereksinim: TKU → `case_relations` yazımı
tasarlanmalı ve ilişki türü ayrıştırılmalı (aynı davanın föyü / yeniden açılan dava
/ arabuluculuk öncülü / icra takibi / ceza-idare paraleli).

## 7. Hüküm

* **Hız sorun değil** — tam paket 93 sn, tekrar koşusu 35 sn. Ölçeklendirme,
  parti bölme, ilerleme imleci gerekmiyor.
* **Eşleşme %97,0** — köprü sağlam, kalan %3 karşı tarafın düzeltme listesine ait.
* **İdempotentlik kanıtlandı** — 19.08 kusuru kapandı, tekrarlı işletim modeli
  güvenli.
* **Asıl açık kalem hız değil anlam:** 18.942 üzerine-yazma, 1.180 kartta çelişki,
  593 çok kartlı TKU grubu. Üçü de veri modeli kararı bekliyor, kod performansı
  değil.

## 8. Ek ölçüm (aynı gün, TKU bulgusu üzerine) — aynı dava / mükerrer kart

§6'nın açık bıraktığı "peki ne yapacağız" sorusu aynı gün koda döküldü:
`services/case_relations_auto.py` (panelin otomatik ilişki katmanı) +
`scripts/mukerrer_kart_raporu.py` (onay listesi). Kartlar **birleştirilmiyor**,
bağlanıyor — `tracking_no` müvekkil bazlı ofis dosya numarasıdır.

İki dedektör kullanılıyor: TKU ortaklığı **ve** esas + mahkeme + tür ikizliği.
İkinci dedektörde kritik bir eleme var: **numarası girilmemiş esas kimlik
sayılmaz.** Canlı veride 397 kart `YYYY/`, 208 kart `2014/???` taşıyor; bunlar
kimlik sayılsaydı aynı mahkemedeki bütün `2019/` kartları birbirinin ikizi ilan
edilirdi (eleme öncesi 508 çift → sonrası 223).

| Ölçüt | Değer |
| --- | --- |
| Aday çift | TKU 807 · esas ikizi 223 |
| "Aynı dava" çifti | 223 |
| **Aynı dava grubu** | **149 grup / 327 kart** |
| Mükerrer kart şüphesi (aynı dava + AYNI müvekkil) | **55 çift** |
| — karşı tarafı da ortak (gerçek mükerrer adayı) | **52** |
| — karşı tarafı farklı (esas no yanlış girilmiş olabilir) | 3 |

Son satır raporun karar verdirici kolonu: aynı mahkeme + aynı esas ama davalılar
bambaşkaysa bu mükerrer kayıt değil, veri hatasıdır. Kanıt vakası: Gaziantep 2.
Tüketici **2017/1210** — kartlardan biri "Çeliksoy", diğeri "Oğul" davalı.

## Ekler — koşuyu tekrarlamak

```bash
docker cp "C:/hukdok-veri/yedek/lokal_prova_oncesi_20260819.dump" hukudok-postgres:/tmp/prova.dump
docker compose exec -T postgres psql -U hukudok_user -d postgres -c "CREATE DATABASE hukdok_perf OWNER hukudok_user;"
docker compose exec -T postgres pg_restore -U hukudok_user -d hukdok_perf --no-owner --no-privileges /tmp/prova.dump
docker compose exec -T -e DATABASE_URL="postgresql://hukudok_user:<PW>@postgres:5432/hukdok_perf" backend python -c "import database; database.init_db()"
docker compose exec -T -e DATABASE_URL="postgresql://hukudok_user:<PW>@postgres:5432/hukdok_perf" backend python scripts/hukdok_aktarim.py --input /tmp/teslim.xlsx --rapor-dizini /tmp/rapor
```

Ölçüm sonunda `hukdok_perf` düşürüldü; çalışan `hukudok` veritabanına dokunulmadı.
