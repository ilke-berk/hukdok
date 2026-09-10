# Veri kalitesi düzenleme planı — kontrol listesi

**Tarih:** 06.09.2026 · **Veri:** lokal DB = 30.07 prod kopyası + `HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx`
üç koşu (aktarım → G126 kart açma → G127 birleştirme), bkz. `HUKDOK_VERI_EKIBI_RAPORU_2026-09-06.md`.
**Kapsam:** yalnız kontrol listesi ve sıra. Kod yazılmadı; sayılar 06.09 lokal ölçümüdür (salt okunur SQL).

> **Yaşayan plan.** Her kalem "ne kontrol edilir · nasıl · kim düzeltir" üçlüsüyle yazıldı.
> Kalemler görev kuyruğuna alınırken bu dosyadan referans verilir; sayılar prod'da yeniden ölçülür.

---

## 0. Temel kural: düzeltmenin kaynağı kim?

`scripts/hukdok_aktarim.py` docstring'i (koddan okundu): kart alanlarının çoğu "varsayılan sınıf"tır —
**dolu hücre üzerine yazar, tarihçeli**. Yani DB'de elle düzelttiğimiz TKU, esas no, tarih, tutar
bir sonraki teslimde paketten **geri gelir**. Aktarımın dokunmadığı yerler ise şunlardır:

- `court` / `sub_type`: yalnız İÇERİK farkında yazılır, yazım farkına dokunmaz.
- Taraf satırları (`case_parties`): yalnız EKLER, silmez, güncellemez.
- Aşama kararları (`case_stage_decisions`): dolu aşamaya dokunmaz.
- `cases.tku_no`, `cases.sistem_no`, karar künyesi (`karar_no`/`karar_tarihi`): hiç yazılmaz.
- Kapalı listelerin kendisi (havuz seed yalnız ekler).
- Kart yapısı: bağ (`case_relations`), birleştirme, kart açma.

Bundan üç düzeltme sınıfı çıkar. Her kontrol kalemi birine düşer:

| Sınıf | Kim düzeltir | Nerede kalıcı olur |
| --- | --- | --- |
| **A — Master** | Veri ekibi, kendi master'ında | Sonraki paket `Düzeltme_Logu` ile getirir; bizde otomatik uygulanır |
| **B — Bizde** | Biz (panel ya da dry-run'lı script) | Aktarımın dokunmadığı alanlar; paket ezmez |
| **C — Kural** | Biz, aktarım kodunda | Aynı hata her pakette aynı biçimde çözülür (normalize/doğrulama) |

**Kural:** A sınıfı bir hatayı DB'de düzeltmek boşa iştir; liste ekibe gider. B ve C bizde kalır.

**Kullanıcı kararı (06.09): "Bu aşamada en doğru bilgi son paketten gelendir, elle
düzeltmeden bile daha doğru olabilir."** Sonuçları:
- "Elle düzeltilen alan paketle ezilmez" kuralı YAZILMAZ. Kart alanlarında paket zaten kazanıyor
  (varsayılan sınıf), bu davranış korunur; tarihçe eski değeri saklar.
- Aşama katmanındaki **"dolu aşamaya dokunulmaz"** kuralı bu kararla çelişiyor: 18.08 paketinin
  yazdığı 4.971 satır 04.09'un düzeltmelerini engelledi (12 satır bayat). Kural şöyle değişmeli
  (C sınıfı): kaynağı `HUKDOK_TESLIM_*` olan aşama satırını yeni paket günceller (tarihçeli);
  elle girilmiş satır da paket geldiğinde güncellenir — kullanıcı kararı. Prod'da bugün paket
  kaynaklı aşama satırı YOK (aktarım hiç koşmadı), lokalde elle girilmiş satır 0; ilk prod
  uygulaması temiz yazar, kural sonraki paketler içindir.
  **→ G150 ile uygulandı (08.09):** yerinde güncelleme + `BELGE`/`UYAP` satırı korunur + çok tur
  `sira_no+1`; lokalde 12 bayat satır 0'a indi, ikinci koşu 0. Güncel kural
  `docs/mimari/veri-teslim-hatti.md` §7.1; bu paragraf tarihsel bağlamdır.
- Sistem içi (elle) düzeltme yalnız paketin taşımadığı alanlarda anlamlıdır: bağ/birleştirme,
  listeler, mahkeme adı yazımı, taraf satırları, esas tarihçesi. İçerik hatası ekibe gider.
Prod sırası değişmez: deploy → havuz seed → paket → kart aç → birleştir → aktarım. Temizlik önce
LOKALDE prova edilir, prod'a paket uygulamasından SONRA girer.

---

## 1. Ölçüm fotoğrafı (06.09 lokal)

**Kapsam kararı (kullanıcı, 06.09):** temizlik hedefi **föylü kartlar** — paketin kapsadığı
6.641 kart / 8.386 föy. Föysüz 7.906 kart (KORU 3.172, AXA 2.338, EUREKO 389, HANYALOĞLU 416;
İcra 2.246, Tahkim 2.191; 7.536'sı MAHZEN, 20'sinde belge) sigorta rücu/icra/tahkim ve özel
müvekkil dosyalarıdır, ekibin master'ında yoktur; **bu planın dışındadır** (§2.6 #31).

| Ölçüm | Föylü kart | Tüm aktif | Not |
| --- | --- | --- | --- |
| Kart | 6.641 | 14.547 | föy 8.386 |
| TKU boş föy | 255 | — | 20'sinde hasar no var |
| TKU biçim dışı (`TKU-NNN` değil) | **0** | — | biçim TEMİZ; sorun anlamsal |
| TKU grubu / tek föylü / çok kartlı | 5.658 / 4.131 / 624 | — | |
| Aynı TKU, birden çok hasar no | 218 grup | — | ilişki anahtarı mı, hata mı? (§2.1) |
| Aynı hasar no, birden çok TKU | 20 grup | — | en güçlü TKU hatası sinyali |
| Hasar no boş föy / çok değerli-biçim dışı | 3.329 / 233 | — | `;` ayraçlı, `11/7323674`, `11232258-1` |
| Kart hasar no boş / föyle çelişen | 2.711 / 5 | — | |
| Esas boş | **12** | 127 | Hukuk 5, Arabuluculuk 4, İdare 2, Danışmanlık 1 |
| Esas `YYYY/` (numarasız) | **409** | 409 | tamamı föylü kartta |
| Esas `2014/???` | **3** | 294 | 291'i föysüz karttaydı |
| Esas biçim dışı (diğer) | **22** | — | `2016/389;2026/89`, `2014/ 1700`, `2017367`, `yok` |
| Kartta esas var, `case_esas_numbers` güncel satırı yok | **5.825** | 13.616 | türetilmiş kolon borcu (§2.2) |
| Mahkeme adı tekil / büyük-küçük harf ikizi | 1.436 / **57** | 2.306 / 60 | ikizlerin hemen hepsi föylü kartta |
| Mahkeme boş | **271** | 726 | Hukuk 119, Arabuluculuk 74, İdare 37, Savcılık 23, Ceza 15 |
| Dava tarihi boş / iş kabul tarihi boş | 293 / 845 | — | |
| Dava tarihi > karar tarihi | **153** | 153 | tamamı föylü kartta |
| Karar > istinaf / istinaf > temyiz / gelecek tarih | **34 / 21 / 4** | aynı | tamamı föylü kartta |
| Aşama kararı / BELIRSIZ | 5.026 / 1.377 | aynı | tamamı föylü kartta |
| Yerel karar durumu tekil / boş | 23 / 3.873 | — | |
| Müvekkil tipi boş / hizmet türü boş | 891 / 976 | — | kardeş föy çelişkisi (föyde dolu) |
| Uzmanlık alanı boş / konu boş | 96 / 3 | — | |
| Sorumlu avukat boş kart / hiç avukatı olmayan | 102 / **0** | 7.257 | 102'si çok avukatlı, `case_lawyers`'ta |
| Müvekkil tarafı olmayan / karşı tarafı olmayan | 0 / 1 | — | |
| Taraf rolü tekil | **18** | 24 | büyük harf sapmaları (`DAVALI`, `SIGORTALI`) föysüz kartta |
| Kart içi taraf adı büyük-küçük ikizi / birebir çift | 0 / **18** | — | aynı ad + aynı tür iki satır |
| Föy `case_party_id` boş | 8.386 (hepsi) | — | E-8 föy kimliği kurulmadı |
| `file_type` sapması | **0** | "Hukuk Dava" 2, boş 3 | sapmalar föysüz kartta |
| Test artığı ofis no (`SMOKE-`, `HK-`) | **0** | 6 | föysüz kartta |
| Kapsam işaretli föy | 0 | — | 04.09 paketinin kapsam sayfaları işlendi mi? (§2.6) |

**Okuma:** biçim/yazım sapmalarının çoğu (rol büyük harf, `Hukuk Dava`, `2014/???`, test artığı)
föysüz eski kartlarda; **föylü kartların sorunu içerik ve tutarlılık** — numarasız esas (409),
tarih sırası (212), esas tarihçesi (5.825), mahkeme adı ikizi (57), TKU/hasar anlamı.

---

## 1.5 Aktarım eksiksizlik denetimi (06.09, bağımsız, salt okunur)

Paket (`HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx`, sha256 `50196ab5…`, konteynerdeki `/tmp/paket.xlsx`
ile birebir) lokal DB'ye karşı sütun sütun karşılaştırıldı; aktarımın kendi dönüştürücüleri
kullanıldı, yazma yolu çağrılmadı. Sonuç: **aktarım eksiksiz; fark yalnız bilinçli kurallardan.**

| Katman | Sonuç |
| --- | --- |
| Satır | 8.409 SistemNo → 8.386 föy; 23 eksik = 20 müvekkil-ayrımı belirsizi + 3 boş DosyaNo (ekip cevabı bekliyor) |
| `ham_veri` | 8.386 föyde 54 sütun **birebir**, 0 farklı hücre |
| Kart alanları (40 tanınan sütun) | 0 açıklanamayan fark; tüm farklar "kardeş föy çelişkisi → yazılmadı" (islah 10 dahil: kardeş föyün `(boş)` talimatı) |
| Föy alanları (mko_id, muvekkil_no, tipi, hizmet, durum, tku, hasar) | 8.386/8.386 birebir; DosyaNo ↔ `klasor_no_2` 0 uyumsuz |
| Taraflar | 27.860 ad / 0 eksik; 921 "Sigortalı" adı kartta CLIENT türüyle duruyor (mevcut satır güncellenmez, bilinçli) |
| Avukatlar / Eski Dosya No | 19.798/19.798 · 617/617 |
| Karar_Asamalari (8.362 satır) | 6.273 var + 664 ONCEKI var; **1.398 yok = tamamı kardeş föy çelişkisi (532 kart)**, açıklanamayan 0 |
| 18.08'den kalan aşama satırları | 4.971 satır (04.09 yalnız 55 yazdı, "dolu aşamaya dokunulmaz"); 04.09 künyesiyle **12 satır farklı** (7 YEREL, 5 TEMYIZ) → bayat |
| Kapsam sayfaları (61 föy) | Hiçbiri DB'de föy değil → işaretlenecek satır yok (kapsam 0 doğru) |

**Bilinçli boşluklar (B/C sınıfı, plan kalemi):** (a) 532 kart×aşama grubunun zinciri kartta yok,
Sheet satırı `ham_veri`de duruyor. **Dokusu ölçüldü (06.09, denetim 4), üç sınıf:**

| Sınıf | Grup | Ne | Kim çözer |
| --- | --- | --- | --- |
| Yalnız boşluk | **302** (%57) | Bir föyde karar no/tarih dolu, kardeşinde boş; dolu değerler çelişmiyor (örn. kart 13210: H-1737 karar 2021/856, H-1738 boş, tarih ve durum aynı) | **Biz, C sınıfı**: aşama imzasında boş hücre çelişki sayılmasın, dolu olanlar birleşsin (kart alanlarında bu kural zaten böyle, `kart_degerleri` None'ı düşürür; aşama imzası düşürmüyor) |
| Gerçek künye çelişkisi | **148** (%28) | İki farklı dolu değer: karar no 51 (2021/963 ↔ 2021/693), tarih 79 (2017 ↔ 2020), mahkeme 32, esas 22. Alt sınıflar 20b-1/2/3: 37 yazım hatası, 61 aynı dava başka karar (yıl uyumsuzluğu dedektörü), 50 mahkeme/esas farkı = 44 yazım/bayat föy/kayma + 6 çok tur; **farklı dava sıfır** | **Ekibe, A sınıfı** (142) + 6 çok tur model kararı |
| Yalnız karar durumu | **81** (%15) | Künye aynı, durum farklı: "Kabul/Kısmen" ↔ "Kabul", "Red/Esastan" ↔ "Kabul" (doktor föyü red, sigorta föyü kabul) | Karışık: E-8 kuralına göre müvekkil yönünden farklı sonuç MEŞRU olabilir → föy düzeyinde saklanmalı (muvekkil_tipi gibi), kart tek slotu boş kalır; gerçekten çelişenler ekibe |

Sonuç: 532'nin 302'si ekibe gitmeden bizde çözülür; 148'i ekibe; 81'i föy düzeyi alan kararı.

**Ekibe rapor (06.09 akşam, masaüstünde):** `HUKDOK_ASAMA_CELISKILERI_2026-09-06.pdf` (31 sayfa: yöntem,
özet, sınıf başına iki tam-kanıt örneği, Ek A tüm liste) + `HUKDOK_ASAMA_CELISKILERI_2026-09-06.xlsx`
(sınıf başına sayfa, 532 satır, sarı CEVABINIZ = HATA / SEBEBİ VAR / BELİRSİZ + AÇIKLAMANIZ). Tüm 532
grup gönderildi (302 boşluk dahil: 140'ında ana sayfa dolu, aşama sayfası boş → "artık mı?" sorusu).
Gönderim ve cevap sonrası ortak plan kullanıcı adımı. Üretici script scratchpad'de, repoya girmedi.
(b) 12 bayat aşama satırı → "dolu aşamaya dokunulmaz" kuralı değişince (§0) yeniden koşuda düzelir
**(→ G150, 08.09: düzeldi, 12 → 0)**; (c) yerel/istinaf aşama satırlarında
`karar_durumu` NULL 362/322 (havuz dışı değerler: "Derdest", "Kapalı", "Karar" — sözlük tuzağı;
**→ G151: Derdest/Kapalı artık "karar yok", havuz 27/8/4/2; "Karar" ekibe soru**);
(d) 921 sigortalı-tür etiketi (→ G153 "müvekkil değişti" raporu; eski satır elle temizlenir).

## 2. Kontrol listesi — katman katman

### 2.1 Kimlik anahtarları (TKU · Hasar No · SistemNo · DosyaNo)

| # | Kontrol | Nasıl | Sınıf |
| --- | --- | --- | --- |
| 1 | TKU biçimi | Ölçüldü: 0 bozuk. Kapalı. | — |
| 2 | TKU boş 255 föy | 20'si için hasar no üzerinden TKU önerisi üret (aynı hasar no'lu föyün TKU'su); kalan 235 için G128 öneri katmanı (aynı hasta + doktor) ile aday TKU. Liste ekibe. | A |
| 3 | Aynı hasar no, farklı TKU (20 grup) | Hasar no olayın doğal dış anahtarı (sözlük). Grup listesi + iki TKU'nun föyleri yan yana → ekip hangisinin doğru olduğunu söyler. | A |
| 4 | Aynı TKU, farklı hasar no (218 grup) | Ayrıştır: (a) aynı hasta + aynı olay tarihi → TKU doğru, hasar no ikinci sigorta dosyası (meşru); (b) hasta farklı → TKU yanlış. Sınıflı liste ekibe. TKU'nun "ilişki anahtarı" olarak bilinçli kullanımı (mahkeme değişikliği, 400 grup) bu sınıfa girmez, ayrı sütunda işaretlenir. | A |
| 5 | Hasar no biçimi (233 föy) | `;` ile çoklu değer (aynı föyde iki sigorta dosyası) meşru mu? 8 haneli ve 13 haneli iki sigorta biçimi, `11/…` ve `…-1` ekleri. Ekibe "biçim sözlüğü" sorusu; bizde `hasar_parcalari` zaten `;` böler, ek/önek kuralı yok. | A + C |
| 6 | SistemNo / mko_id / MüvekkilNo | SistemNo çift 0 (kapalı). mko_id boş 1, MüvekkilNo boş 7 → ekibe. | A |
| 7 | Kalan 20 müvekkil-ayrımı föyü + 3 boş DosyaNo | Zaten `HUKDOK_MUKERRER_VE_YENI_KARTLAR` ekinde; cevap gelince aktarım bağlar. | A |
| 8 | TKU çok-kartlı 624 grup | Mükerrer DEĞİL (bağ). Yalnız "aynı müvekkil + aynı mahkeme + aynı esas" çiftleri ikiz adayı; `mukerrer_kart_raporu.py` tazelenir, 747/748 ve 791/792 üçlüleri ekip cevabından sonra `mukerrer_kart_birlestir.py`. | B |

### 2.2 Esas numarası ve mahkeme

| # | Kontrol | Nasıl | Sınıf |
| --- | --- | --- | --- |
| 9 | Esas boş 12 | Hukuk 5 + İdare 2 ekibe; Arabuluculuk 4 + Danışmanlık 1 normal olabilir. Küçük, ilk listeye girer. | A |
| 10 | `YYYY/` numarasız 409 (+ `???` 3) | Föylü kartların en büyük esas sorunu. Ekibe liste (belgeden tamamlanır); sözlük "gerçek yıl Esas'ta" dediğine göre ekip yılı biliyor, numarayı bilmiyor → belge taraması. Bizde karar: numarasız değer kartta kalsın mı (bugün kimlik sayılmıyor, ama ekranda/aramada görünüyor)? Kullanıcı kararı. | A + C |
| 11 | Biçim dışı 22 (diğer) | Üç alt sınıf ölçüldü: (a) tek hücrede iki esas `2016/389;2026/89` (4 kart) → ikincisi esas tarihçesine ONCEKI/güncel olarak ayrışmalı, ekibe "Eski Dosya No" sütununa taşısın; (b) yazım `2014/ 1700`, `2017367`, `20197360` → C normalize (boşluk sil, 4+N haneyi `YYYY/N`e böl); (c) `yok`, `5274`, `9.1801`, `2024/0423.2645` (arabuluculuk büro no?) → ekibe. | A + C |
| 12 | `cases.esas_no` türetilmiş ama `case_esas_numbers` güncel satırı yok: **5.825 / 6.641 föylü kart** | CLAUDE.md: tek yazma yolu `case_manager.sync_current_esas`. Tarihçe tablosu (1.330 satır) yalnız tablo sonrası kayıtları ve aktarımın ONCEKI yazdıklarını taşıyor. Backfill script (dry-run) şart; eski esasla arama (E8) bu kartlarda çalışmıyor demektir. **B sınıfının ilk işi.** | B |
| 13 | Mahkeme adı 57 büyük-küçük ikizi (föylü) | `court` içerik farkında olduğundan bizde düzeltme KALICI, paket ezmez. G067-G070 mahkeme adı kimliği ile normalize (dry-run). Ayrıca "yer tanınmayan" 110 kalem. | B |
| 14 | Mahkeme boş 271 | Savcılık 23 + Arabuluculuk 74'te boş normal olabilir; **Hukuk 119 + İdare 37 + Ceza 15** ekibe. Esas dolu ama mahkeme boş olanlar önce. | A |
| 15 | İstinaf mahkemesi 204, temyiz 33 tekil | Kullanıcı kuralı (05.09): önce geçir, sonra panelden temizle. Büyük-küçük/nokta ikizlerini birleştir; ekibe de yazım birliği (raporda var). Not: seed yalnız EKLER, sonraki paket bozuk yazımı geri getirebilir → yazım birliği ekipte de şart. | B + A |

### 2.3 Tarihler ve yargı zinciri

| # | Kontrol | Nasıl | Sınıf |
| --- | --- | --- | --- |
| 16 | Dava tarihi > karar tarihi 153 | Sözlük: "Dava Tarihi güvenilmez, gerçek yıl Esas'ta". Liste ekibe; bizde esas yılı ile çapraz kontrol sütunu. | A |
| 17 | Karar > istinaf 34, istinaf > temyiz 21, gelecek tarih 4 | Liste ekibe. | A |
| 18 | E-9 bayat hüküm kapısı | Eski Dosya No (ONCEKI esas 523) dolu VE yerel sonuç dolu VE dosya yargılamada → yerel sonuç `Derdest` olmalı. Sayı ölç, ihlal listesi ekibe. | A |
| 19 | Aşama kararı BELIRSIZ 1.377 / 5.026 | Bunlar aktarımdan gelen, belgeyle doğrulanmamış satırlar. Doğrulama akışı takip panelinde var; kim, hangi sırayla? Öneri: önce DERDEST kartlar, sonra karar tarihine göre yeni→eski. İnsan işi, plan dışı takvim. | B (insan) |
| 20 | 5 kapsam satırında tarih hücresine metin | Raporda ekibe yazıldı; bekleniyor. | A |
| 20a | Aşama imzasında boş hücre çelişki sayılıyor (302 grup) | `_asama_imzasi` boş alanı imzaya katıyor; kural kart alanlarındaki gibi olmalı: boş hücre uzlaşıya katılmaz, dolu değerler çelişmiyorsa birleşik satır yazılır. Test: kart 13210 YEREL tek satır, karar no 2021/856. **→ G150 ile (08.09) kapandı:** imza yalnız dolu alanlar, `_asama_uzlasisi` alan bazında; çelişki grubu 532 → 227 (lokal). | C ✔ |
| 20b | Gerçek künye çelişkisi (148 grup) — **dokusu ölçüldü (denetim 6-7)**, üç alt sınıf: | | |
| 20b-1 | Yazım hatası adayı **37**: aynı mahkeme + esas (+ çoğunlukla aynı tarih), karar no'da ≤1 rakam / yer değişimi / yıl farkı (2021/963 ↔ 2021/693; 2019/2034 ↔ 2019/1034; tarih 2021-04-15 ↔ 2020-04-15). Ana sayfada da farklı → sayfa artığı değil, master hatası. 9'unda çoğunluk aynı, tek föy sapıyor. | Liste ekibe, sapan föy işaretli. | A |
| 20b-2 | Aynı dava, başka karar **61**: aynı mahkeme + esas, karar no ve/veya tarih bambaşka (5042: 2025/4243 ↔ 2023/183 aynı tarih 29.03.2023; 372: 2024/173 ↔ 2022/226 aynı tarih). Dedektör: karar no yılı ≠ karar tarihi yılı → büyük ihtimal hata; kalanı ek karar/tavzih olabilir. 17'sinde tek föy sapıyor. | Liste ekibe, "yıl uyumsuz" bayrağıyla. | A |
| 20b-3 | Mahkeme ya da esas farklı **50** — **"farklı dava" HİPOTEZİ ÇÜRÜDÜ (denetim 8-9, tam zincir okundu):** sıfır grup farklı dava. Dağılım: mahkeme adı yazımı/eksik 24 ("Mahkemeleri"↔"Mahkemesi", "İSTANBUL BİM"↔"İSTANBUL BİM 7. İDD", "BAM 6. HD"↔"BİM 6. İDD", Anadolu "5."↔"12."); **bayat föy** 14 (yenileme sonrası bir föy eski esasta kalmış: 13440 2022/79↔2025/250, 14132 2019/56↔2023/640; eski esas kardeşin "Eski Dosya No"sunda); sütun kayması 1 (13037: esas mahkeme hücresinde); aşama yanlış dosyalanmış 1 (13107: istinaf satırında yerel mahkeme); esas eksik yazılmış 1 ("2025/"); **çok tur adayı 6** (13261: BİM 7 2021/1479 → temyiz 2022 bozma → 2025/1812 ikinci istinaf; 12955, 128, 14132, 13467): aynı davanın iki turu farklı föylere yazılmış. | 44'ü ekibe (yazım/bayat/kayma); 6 çok tur için model kararı: `case_stage_decisions.sira_no` iki turu taşıyabilir, kural "farklı tarih + farklı esas = ikinci tur, ikisini de yaz" | A + karar |
| 20c | Yalnız karar durumu farkı (81 grup) | Önce E-8 sorusu ekibe: "aynı kararın iki föyde farklı sonucu müvekkil yönünden mi?" Evetse karar durumu föy düzeyi alan olur (`case_foys`, muvekkil_tipi deseni); hayırsa çelişki listesine eklenir. **→ Karar 08.09 (plan 08.09 A3): föy düzeyi alan AÇILMADI**; G157 çelişki raporunda E-8 grubu "müvekkil yönü farkı" etiketiyle (hata değil), föyün değeri `ham_veri`de; SOZLESME 1.3 §6 ekibe anlatır. | karar ✔ |

### 2.4 Kapalı listeler ve yazım birliği

| # | Kontrol | Nasıl | Sınıf |
| --- | --- | --- | --- |
| 21 | Yerel karar durumu 23 değer | Sözlük tuzağı: "Kapalı"/"Derdest" sonuç değil işlem durumu. Bizde liste değerleri makul görünüyor (Red/Esastan 1.473, Kabul/Kısmen 485…); işlem durumu değerleri geliyorsa ayrı alana mı? Ekiple kavram teyidi. **→ G151 ile (08.09):** `Kapalı`/`Derdest` yerel havuzdan çıktı, aktarım ikisini "karar yok" sayar (künyeli satır durumsuz + şerh, künyesiz satır yazılmaz); ekibe "yazmayın, boş bırakın" (SOZLESME 1.3 §6). Ayrı alan açılmadı — büro durumu `cases.status`. | A + C ✔ |
| 22 | İstinaf/temyiz karar durumu | Kartlarda 3'er değer (temiz). Ama havuz seed +22 bozuk yazımı LİSTEYE ekledi → listeden panelle sil (kartta kullanılmıyorsa). **→ G151 ile (08.09):** seed istinaf 8 / temyiz 4 (HMK 353/1-b-2 ailesi, `Kısmen Onama/Kısmen Bozma`); `deger_havuzu_seed.py --kaldir` kullanılmayan satırı siler (kuru koşu varsayılan). Lokalde 2 istinaf değeri paket yazımıyla duruyor (ad düzeltmesi panelden); **bozuk 22 yazımın panel temizliği hâlâ insan adımı.** | B (kısmen) |
| 23 | `file_type` sapması | Föylü kartta 0; "Hukuk Dava" 2 + boş 3 föysüz eski kartlarda. Kapsam dışı, yalnız kayıt. | — |
| 24 | Tıbbi beşli havuzu (tıbbi olay 667, yöntem 260, zarar 258, süreç 97) | Büyük-küçük harf / ayraç / boşluk ikizlerini ölç, panelden birleştir. Kartlardaki ` ; ` ayraçlı değerler listeyle uyuşuyor mu (multiselect doğrulaması)? | B |
| 25 | Taraf rolü | Föylü kartta 18 değer, büyük harf sapması YOK (`DAVALI`/`SIGORTALI` föysüz kartlarda). `party_roles` kapalı listesiyle çapraz kontrol yeter; C normalize düşük öncelik. | B (düşük) |
| 26 | Sorumlu avukat | Föylü kartta hiç avukatı olmayan kart **0**; 102 kartın kutusu boş ama `case_lawyers`'ta çok avukat var. Kapalı. | — |

### 2.5 Taraflar ve kişiler

| # | Kontrol | Nasıl | Sınıf |
| --- | --- | --- | --- |
| 27 | Taraf adı | Föylü kartta kart içi büyük-küçük ikizi **0**; birebir çift (aynı ad + aynı tür, iki satır) **18** → dry-run script ile tekle (belge bağı `case_party_id` SET NULL tuzağına dikkat, FAZ F şartı). Kartlar arası 87 yazım ikizi (`AHMET ALP`/`Ahmet Alp`) kişi eşleştirmesini (G128 `normalize_party_key`) etkilemiyor; yazım standardı kararı kullanıcıya. | B |
| 28 | Föy ↔ müvekkil bağı (`case_party_id` 8.386 boş) | Sözlük E-8: föy kimliği Müvekkil+Sigortalı çifti; bizde kurulmadı. Karar: aktarımda "Müvekkil" hücresini `case_parties` ile eşleyip föye bağlansın mı? Kurulursa müvekkil-ayrımı belirsizliği (20 föy sınıfı) yapısal çözülür. Kullanıcı kararı. **→ Karar EVET (08.09), G153 ile kuruldu:** `_foy_muvekkilini_bagla` (Müvekkil ilk parçası → CLIENT satırı), Dosya No kökü eşleştirme adımı; lokal kuru koşu 8.385/8.386 föy bağlı, belirsiz 20 → 10 (8 hekim köklü + 2 gerçek mükerrer → G154 cevaplı harita). Prod'a uygulanmadı. | C ✔ |
| 29 | `client_id` boş 51.247 | Cari bağı bilinçli kurulmadı (G128 notu). Bu planın DIŞI; kayıt olarak durur. | — |
| 30 | Müvekkil tipi / hizmet türü kardeş çelişkisi (973 / 891 kart) | Çelişki gerçek mi, yazım farkı mı ("Doktor"/"DOKTOR")? Normalize edilmiş karşılaştırmayla çelişki sayısını yeniden ölç; düşüyorsa C (aktarım karşılaştırmayı normalize etsin), kalan gerçek çelişki ekibe. | C + A |

### 2.6 Kapsam mutabakatı (büyük resim)

| # | Kontrol | Nasıl | Sınıf |
| --- | --- | --- | --- |
| 31 | Föysüz 7.906 aktif kart | Ölçüldü (06.09): KORU 3.172 / AXA 2.338 / EUREKO 389 / HANYALOĞLU 416 isim blokları; İcra 2.246, Tahkim 2.191, Hukuk 3.031; 7.536 MAHZEN, 370 DERDEST (İcra 195, Hukuk 139); 7.878'inde DosyaNo dolu (MKO kökenli), 20'sinde belge. Sigorta rücu/icra/tahkim + özel müvekkil dosyaları; ekibin malpraktis master'ında yok. **Karar (kullanıcı, 06.09): bu plan föylü kartlara odaklanır**; föysüz kartlar olduğu gibi kalır, 6 test artığı ofis no (`SMOKE-`, `HK-`) ayrı küçük temizlik. | kapsam dışı |
| 32 | Kapsam işaretli föy 0 | 04.09 paketinde `Silinen_Föyler`/`Kapsam_Dışı` sayfaları var mıydı, boş muydu, işlendi mi? Aktarım raporundan doğrula. | ölçüm |
| 33 | Master 17.07 sonrası ~40-60 yeni dosya | Sözlük notu; sonraki paketle gelir. G126 210 kart + G127 8 birleştirme ekibe bildirildi; paket bunları yansıtmalı. | A |

---

## 3. Yürütme sırası

1. **Ölçüm paketi (tek salt-okunur script, sonra görev):** yukarıdaki 33 kalemi tek xlsx'e döker
   (kalem başına sayfa; her satırda sınıf, kart/föy kimliği, öneri). Prod'da da aynı script koşar;
   sayılar oradan alınır. Çıktı: `HUKDOK_VERI_KALITE_RAPORU_<tarih>.xlsx`.
2. **A sınıfı → ekibe:** 06.09 raporuna ek ya da ikinci rapor. Beklenen dönüş: `Düzeltme_Logu`
   `[Sütun]` önekli, "Önceki teslim" satırı doğru. Biz beklerken B'ye geçeriz.
3. **B sınıfı, bizde, sırayla** (her biri dry-run → yedek → `--apply` → tek commit):
   1. esas tarihçesi backfill (#12) — arama doğruluğu, en yüksek etki;
   2. mahkeme adı normalize (#13);
   3. taraf rolü + taraf adı tekleme (#25, #27);
   4. liste temizliği panelden (#15, #22, #24) — kullanıcı elle, "kolay işler";
   5. föy-müvekkil bağı (#28) — yalnız karar verilirse.
4. **C sınıfı, aktarım kuralları:** rol normalize, `Hukuk Dava`, `???` esas kararı, çelişki
   karşılaştırmasında normalize, hasar no ek/önek. Her biri test + ikinci koşu 0 değişiklik kanıtı.
5. **Prod:** deploy → havuz seed → paket → kart aç → birleştir → aktarım → ölçüm paketi tekrar.

**Kabul kriterleri (her adımda):** aynı paketle ikinci koşu 0 değişiklik; belge envanteri denk;
her düzeltme `case_history`'de kaynak imzalı; A sınıfı hiçbir alan DB'de elle değiştirilmedi.

---

## 4. Kullanıcı kararı bekleyen sorular

1. Numarasız `YYYY/` esas değerleri (409 kart) kartta kalsın mı, aktarım bunları boş mu yazsın? (#10)
2. ~~Föy ↔ müvekkil bağı (E-8 kimliği) kurulsun mu?~~ → karar verildi 08.09: evet, G153 ile kuruldu. (#28)
3. ~~Föysüz 7.906 kartın sahibi~~ → karar verildi 06.09: plan dışı, olduğu gibi kalır. (#31)
4. Taraf adı yazım standardı: büyük harf mi, başlık biçimi mi? Belge çıktılarını etkiler. (#27)
5. BELIRSIZ 1.377 aşama kararını kim, hangi sırayla doğrulayacak? (#19)
