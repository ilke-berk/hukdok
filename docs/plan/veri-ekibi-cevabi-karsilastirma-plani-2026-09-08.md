# Veri ekibi yazışmaları ↔ HukuDok karşılaştırması ve düzeltme planı

**Tarih:** 08.09.2026 · **Girdi:** ekibin dört e-postası (04.09 bildirim REV-2, 04.09 takip, 04.09 "paket
güncellendi", 06.09 cevap + 4 ek) ve bizim iki metnimiz (`HUKDOK_CEVAP_20260904.md`,
`HUKDOK_VERI_EKIBI_RAPORU_2026-09-06.md`). Ekler: `~/Masaüstü/veri-ekibi-cevap-2026-09-06/`.
**Yöntem:** her kalem koda karşı okundu (satır referansları 08.09 `main`), sonra hüküm verildi.
**Bu dosya `veri-kalitesi-duzenleme-plani-2026-09-06.md`'nin devamıdır**; oradaki #-numaraları korunur.

> **Şerh (10.09.2026, G161):** §3 tablosuna "Durum" sütunu ve §4 kararlara sonuç eklendi; §1 tablolarındaki
> kod satır referansları 08.09 `main`e aittir ve G150–G160 sonrası kaymıştır — güncel satırlar ve kuralların
> kod karşılığı `docs/mimari/veri-teslim-hatti.md` §7.1'de, ekibe giden metin `docs/veri-teslim/SOZLESME.md`
> 1.3'te. §0-3'teki "dolu aşama" kuralı G150 ile değişti (yerinde güncelleme, BELGE/UYAP korunur).

> **İlke (kullanıcı, 08.09):** ekip HukuDok'un iç işleyişine hâkim değil. Onlara makul gelen bir istek
> bizde ya zaten karşılanıyor ya gereksiz ya da verimsiz olabilir. Bu yüzden her kalem dört hükümden
> birini alır: **ZATEN VAR** (iş yok, ekibe anlatılır) · **YAP** (bizde gerçek boşluk) · **GEREKMEZ**
> (istek bizim modelde anlamsız; gerekçesiyle geri yazılır) · **KARAR** (kullanıcı karar verir).

---

## 0. Beş cümlede

1. Ekibin göremediği klasörün sebebi tenant ayrımı; **G147/G148** kuyrukta, kod değişmeden çözülmez.
2. Ekibin isteklerinin yaklaşık yarısı bizde **zaten karşılanıyor** (Sütun başlığı, delta yazma yolu, bilinmeyen
   sayfa, avukat satırlarına dokunmama, H-6589'un bağlanmamış olması). Bunları kod değiştirmeden cevaplayacağız.
3. Gerçek boşluklar **aşama katmanında**: "dolu aşamaya dokunulmaz" kuralı (delta paketleri ve düzeltmeleri
   kilitliyor), boş hücrenin çelişki sayılması (302 grup), `Başvuru Tarihi` okunmaması, havuzlarda "Kapalı/Derdest".
4. 04.09 cevabımızda iki iddia yanlıştı: "33.441 hücre bizde değişmiş görünmez" (sayım hücre bazlı, görünür) ve
   "Müvekkil Tipi/Hizmet Türü okunmuyor" (G119-G122 ile okunuyor). Düzeltilerek bildirilecek.
5. Ekibin "karar durumu föy düzeyinde saklansın" ve "15 föyün taraf kaydını dondurun" istekleri bizim modelde
   ya verimsiz ya anlamsız; **KARAR** ve **GEREKMEZ** olarak işaretlendi.

---

## 1. Karşılaştırma tablosu

### 1.1 Teslim kanalı ve kapı

| # | Ekibin dediği | Bizde gerçek durum | Hüküm |
| --- | --- | --- | --- |
| K1 | `03_VERI_TESLIM/gelen` görünmüyor, davet gelmedi; hangi hesaba paylaşıldı + bağlantı | Prod arşiv LexisBio tenant'ında; ekip hesabı Hanyaloğlu tenant'ında → 03.09 paylaşımı misafir daveti oldu. Kod tek-site (`sharepoint_uploader_graph.py:131-142`) | **YAP → G147/G148** (kuyrukta). Bağlantı Hanyaloğlu site'ında verilecek |
| K2 | Kapı sayımı ham dizgi mi anlam mı? DB-008 33.441, DB-009 46.491 hücre | Sayım **kart hücresi** bazında (`teslim_kutusu.py:390`, `hukdok_aktarim.py:1900`). Tarih/tutar tip düzeyinde normalize (`:416-450`, `:464-490`) → DB-009 **değişiklik üretmez**. Metin ham karşılaştırılır (`:1614-1622`) → DB-008 casing farkı **değişiklik sayılır**, paket yazımı üzerine yazar (istenen: "paket kazanır"). Yalnız `court`/`sub_type` yazım farkında dokunulmaz (`:821`). Eşik 10.000 aşılır → `inceleme_bekliyor`; ilk teslim zaten inceleme (`teslim_kutusu.py:1055`) | **ZATEN VAR.** Cevap: "DB-009 sıfır, DB-008 ~33 bin sayılır, ilk teslim insan onaylı; ek işlem yok". 04.09'daki "görünmez" ifadesi düzeltilir. Sözleşmeye "eşik = kart hücresi" notu (G148'e ek) |
| K3 | 31.08 paketi uygulandı mı? Zincir nereden başlasın? | 31.08 hiç ulaşmadı. 04.09 paketi lokalde script ile uygulandı, **defterde yok** (defter 1 satır = 18.08); prod'da hiç. `_uygulandi_var` birebir dosya adı arar (`teslim_kutusu.py:373-382`) | **YAP (süreç):** prod'da 04.09 paketi **teslim hattından** (defter üzerinden) uygulanır ki zincir oradan başlasın. Ekibe: "Önceki teslim: HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx" |
| K4 | "Önceki teslim" için `—` yazalım mı? | `—` yer tutucu olarak tanınır ama `zincir_tamam=False` → `zincir_eksik` ihlali (`:856-857`, `:995-1003`) | **YAP (küçük C):** defter boşken `—`/`İLK` ihlal üretmesin (zincir başlangıcı). Test + sözleşme §3.3 |
| K5 | Ek sayfalar (Kaldirilan_Sutunlar, S37_Kanonik, Yazim_Standardi) pakete girsin mi | Yapı doğrulaması yalnız `Sheet` + izlenen sayfalara bakar (`:862-899`, `:763-765`); bilinmeyen sayfa ne uyarı ne ret | **ZATEN VAR.** Cevap doğruydu |
| K6 | Partili (delta) teslim: 3 soru | Yazma yolu delta'yı destekler (eksik sütun/föy = dokunma, `hukdok_aktarim.py:1279-1280`, `:2327`). Ama (a) kapı eksik sütunu `kaybolan_basliklar` → `yapi_degisti` ihlali sayar (`teslim_kutusu.py:760-761`, `:1073-1075`) → her delta `inceleme`; (b) aşama katmanı "dolu aşamaya dokunulmaz" (`hukdok_aktarim.py:2114-2119`) → delta aşama düzeltmesi **ulaşmaz**; (c) Düzeltme_Logu değer yazmaz, yalnız `(boş)` + provenance (`:1236-1251`) → yalnız ilgili föyler yeter | **YAP (orta):** `DEGISIKLIK_OZETI`'ne "Teslim türü: delta" satırı; delta'da kaybolan başlık **bilgi**, ihlal değil. Aşama tarafı A1 ile çözülür. Cevap: (1) evet yalnız ilgili föyler, (2) zincir delta'da da kesintisiz, (3) tam paket aylık mutabakat |

### 1.2 Aşama katmanı (Karar_Asamalari)

| # | Ekibin dediği | Bizde gerçek durum | Hüküm |
| --- | --- | --- | --- |
| A1 | 270 HATA cevabı: "aşama sayfası uzlaştırıldı, tüm kardeş föyler aynı değerde" → sonraki paket düzeltir | "Dolu aşamaya dokunulmaz" (`:2114-2119`): o aşamada bir satır varsa paket **hiçbir düzeltmeyi yazmaz** (18.08'in 4.971 satırı 04.09'u engelledi, 12 bayat). Silme yolu yok (delta güvenli) | **YAP (C, en öncelikli):** plan §0 kararı uygulanır: kaynağı `HUKDOK_TESLIM_*` olan aşama satırını yeni paket günceller (tarihçeli); `dogrulama_durumu ∈ {BELGE, UYAP}` satıra **dokunulmaz** (ekibin "künyede belgeye dayanan taraf kazanır" kuralıyla aynı); çok tur (6 grup) `sira_no` ile ikinci satır. Kabul: 04.09 paketiyle 12 bayat satır düzelir, ikinci koşu 0 |
| A2 | 160 grup: "boşluk — dolu değerle birleştirin, size iş çıkmaz" | `_asama_imzasi` boş alanı imzaya katıyor (`:2012-2020`) → 302 grup çelişki sayıldı, aşama yazılmadı | **YAP (C):** plan #20a: boş hücre uzlaşıya katılmaz, dolu değerler çelişmiyorsa birleşik satır. Kabul: kart 13210 YEREL tek satır |
| A3 | 29 grup E-8: "karar_durumu föy düzeyinde saklanmalı; kartta tek değerse hangi müvekkil yönünden olduğu belirtilmeli" | `case_foys`'ta karar alanı yok; `case_stage_decisions` karta bağlı, `foy_id` yok (`models.py:284`); föyün kendi değeri `ham_veri`'de zaten duruyor (`models.py:371-376`) | **KARAR.** Öneri: **büyük model değişikliği YAPILMASIN** (29 grup için yön ekseni + föy bağlı aşama tablosu verimsiz). Ucuz karşılık: föy panelinde `ham_veri`'den "bu föyün karar durumu" satırı; kart slotu çelişkide boş kalır (bugünkü davranış); çelişki raporunda E-8 grubu ayrı etiket ("müvekkil yönü farkı", hata değil) |
| A4 | 409 hücreye "Kapalı/Derdest" yazdık çünkü sizin yerel havuzunuzda var; iç kuralımız "sonuç değil" der | Yerel havuzda `Kapalı` (`seed_data.py:431`) ve `Derdest` (`:423`) **var** — sözlük tuzağı bizden kaynaklandı (plan #21). Lokalde yerel/istinaf `karar_durumu` NULL 362/322 | **YAP (C + havuz):** `Kapalı`/`Derdest` yerel havuzdan çıkar; aktarımda bu iki değer "karar yok" sayılır (aşama satırı yazılmaz, `dosya_son_durumu`/`status` zaten Sheet'ten geliyor). Ekibe: "karar durumu sütununa büro durumu yazmayın, boş bırakın" |
| A5 | Havuz genişletmesi: istinaf +6 (193 föy), yerel `Red/Usulden` (15), temyiz `Kısmen Onama/Kısmen Bozma` (3) | Kod seed'i istinaf 3 / temyiz 3 / yerel 28 (`seed_data.py:446-448`); lokalde `deger_havuzu_seed` 25 istinaf satırı (bozuk yazımlar dahil, plan #22). Tanınmayan değer satırı düşürmez, durum boş + şerh (`hukdok_aktarim.py:2132-2157`) | **YAP (küçük, seçici):** HMK 353/1-b-2 meşru; seed'e `Düzeltilerek Karar Verildi`, `Düzeltilerek Kabul`, `Kısmen Kabul`, `Düzeltilerek Ret`, yerel `Red/Usulden`, temyiz `Kısmen Onama/Kısmen Bozma`. **"Karar" (74 föy) tek başına anlamsız** → ekibe sor. Bozuk 22 yazım panelden silinir (#22). `add_item` normalize tuzağı (`reference_lists.py:59-63`) → seed'den ekle, panelden değil |
| A6 | Karar_Asamalari'na `Başvuru Tarihi` (22. sütun) ekleyeceğiz | `ASAMA_SUTUNLARI` tanımıyor (`:1687-1700`); `istinaf_basvuru_tarihi` Sheet'ten karta (`:238-240`, `:807`); `case_stage_decisions`'ta `basvuru_tarihi` kolonu yok | **YAP (orta):** kolon + okuyucu + fotoğraf (`istinaf_basvuru_tarihi`, `temyiz_basvuru_tarihi`); Sheet sütunu yedek kaynak kalır |
| A7 | S5 satır 82 (id-10285/10286) boş geldi | Üretici scratchpad'de (`rapor_uret.py`), repoda değil; normalize eşitliği yer tutucu değerleri (`DANIŞTAY . DAİRE` ≈ `DANIŞTAY DAİRE`) eşit sayıp "farklı alan" boş bıraktı | **YAP (düşük):** üreticiyi `services/` altına al, yer tutucu değerleri ayrı sınıf ("daire no eksik"), test |
| A8 | BELİRSİZ 210 grup belge kuyruğunda; 5.539 föyde karar belgesi yok | Aşama satırı `dogrulama_durumu=BELIRSIZ` 1.377 (plan #19) | **ZATEN VAR** (insan takvimi). Ekibin belge turu bizim BELIRSIZ doğrulamasını da besler; sonuç `Düzeltme_Logu` ile gelir |

### 1.3 Kimlik ve müvekkil

| # | Ekibin dediği | Bizde gerçek durum | Hüküm |
| --- | --- | --- | --- |
| M1 | 29 grup cevaplandı: 27 onay, H-6589 bağlamayın, id-1012 → Quick | 20 föy bağlanmamış bekliyor (rapor §2.1). Eşleştirme: SistemNo → DosyaNo↔`klasor_no_2` → esas/tür/müvekkil adı (`:1548-1582`, `:1462-1545`) | **YAP (küçük script):** `HUKDOK_MUKERRER_VE_YENI_KARTLAR_20260905_CEVAPLI.xlsx` → CEVABINIZ'daki kart no ile föyü bağla (dry-run → apply); H-6589 atlanır; id-1012 → #786 |
| M2 | Müvekkil kimliği DosyaNo kökünde (1 AXA, 2 Quick, 3 Ak, 5 Koru, 6 Sompo, 7 Eureko, 8 HDI, 9 Anadolu, 8000 Nippon, 13 hizmetsiz, ≥500 hekim); sabit hane yok | Belirsiz eşleşmede üçüncü anahtar müvekkil adı (`normalize_party_key`); kök bilgisi kullanılmıyor | **YAP (C):** `_ikinci_anahtarla_coz`'a "kök → sigorta müvekkili" adımı (yalnız sigorta kökleri deterministik; ≥500 hekim kökü ad gerektirir). 20-föy sınıfı yapısal biter. Plan #28 (föy↔müvekkil bağı `case_party_id`) bununla birlikte kurulur |
| M3 | H-6589 bağlanmasın | Bağlanmadı; #745 önerisi uygulanmamıştı | **ZATEN VAR.** İş yok |
| M4 | 15 föyde hekim adı Müvekkil sütununda → `case_parties`'te CLIENT olabilir; "taraf kaydını dondurun" | `_taraflari_yaz` **yalnız ekler**, hiç güncellemez/silmez (`:1729-1765`, belge bağı `SET NULL` tuzağı). Hekim CLIENT satırı zaten yazıldı; "dondurma" diye bir işlem yok ve gerekmiyor — sonraki paket düzeltince eski satır **silinmez, yeni satır eklenir** | **GEREKMEZ (dondurma)** + **YAP (küçük):** aktarım "Müvekkil hücresi değişti" olayını rapora düşürsün (eski CLIENT satırı elle düzeltilir, 15 + 921 sigortalı-tür sınıfı plan 1.5-d). Ekibe: "dondurmaya gerek yok, düzeltince bize liste verin" |
| M5 | 1.031 föyde 12 avukat = ayrıştırılamamış eski dosya; silmeyin/boşaltmayın; `case_lawyers`'a işaret koyun | Çoklu isimde kart kutusu **NULL**, 12 satır `case_lawyers` (`:605-613`, `:1768-1801`); silme yolu yok. Ayrı işaret alanı yok; kutu boş olduğu için `missing_required_bucket=AKTARIM` kovasına düşüyor (`required_fields.py:57`) | **GEREKMEZ (işaret alanı)** + **KARAR:** 1.031 kart "eksik sorumlu avukat" sayılmalı mı? Öneri: `case_lawyers` ≥ 2 iken kutu boşluğu eksik sayılmasın (gürültü). Ekibe: "12 satır yalnız ilişki, sorumlu boş; raporlarda 12 avukat sorumlu görünmez" |
| M6 | DB-008 ad yazımı; eşleştirme anahtarı mı? | Anahtar değil (doğru). Ama `sub_type` yazım farkında **bizimki kalır** (`:821`) → "ORTOPEDİ VE TRAVMATOLOJİ" bizde BÜYÜK kalır, paket "Ortopedi ve Travmatoloji" yazmaz. `court` için mahkeme adı kimliği bizim (G067-G070), doğru | **KARAR:** `sub_type` yazım farkında paket yazsın mı ("paket kazanır")? Öneri: evet, `sub_type` `ICERIK_KARSILASTIRMALI`'dan çıkar, `specialties` listesiyle `tr_title`; `court` kalır |

### 1.4 Sütun ve sayfa değişiklikleri

| # | Ekibin dediği | Bizde gerçek durum | Hüküm |
| --- | --- | --- | --- |
| S1 | Düzeltme_Logu'na `Sütun` başlığı; geçmişin %43'ü doldurulacak, kalan boş | `sutun_adi()` önce açık başlığa bakar, adaylar `Sütun, Sütun Adı, Alan, …` (`:1006`, `:1154-1160`); `Eski Değer` okunur ama kullanılmaz (`:1052-1061`) | **ZATEN VAR.** Opsiyonel C: `Eski Değer` bizimkiyle uyuşmuyorsa uyarı (kalite sinyali) — düşük |
| S2 | DB-002 Müvekkil Tipi / Hizmet Türü: "alan açılınca haber verin" | G119-G122 ile okunuyor (`:224-225`, `:800-801`, föy `:1312-1313`); 04.09 paketi işlendi. ` ; ` çok değer → `AlanHatasi`, föyde ham | **ZATEN VAR.** 04.09 cevabındaki "okunmuyor" düzeltilir |
| S3 | Lexis Rapor 2.218 föy dava değil; istatistikte ayırın | `hizmet_turu` liste filtresi (`case_manager.py:810`) + rapor kataloğu hızlı filtre (`registry.py:622`); istatistik/rozet yok | **ZATEN VAR (filtre).** Küçük: rapor kataloğuna "Dava takibi (Lexis Rapor hariç)" hazır filtre önerisi; dashboard sayıları ayırmıyor — istenirse ayrı iş |
| S4 | Kapsam sayfaları hâlâ 68 sütun; 5 tarih hücresi düzeltilecek | Kapsam sayfalarından yalnız SistemNo + gerekçe + tarih okunur | **ZATEN VAR.** Bizde etki yok |
| S5 | DEGER_HAVUZLARI +321 klinik değer sonraki pakette | `deger_havuzu_seed.py` yalnız ekler, kuru koşu varsayılan | **YAP (süreç):** prod sırasında paket sonrası `--apply`; kural "önce geçir, sonra panelden temizle" (05.09) |
| S6 | `appealing_parties` 3 değere hizalayacaklar; "Her İkisi" | Seed: `Davacı · Davalı · Her İki Taraf` (`seed_data.py:376-380`); listede olmayan sessizce boş (`:544-550`) | **ZATEN VAR.** Cevapta birebir yazım verilir |
| S7 | İstinaf Karar Durumu yön hücreleri (~50) ayrı alana taşınacak; `appeal_decisions` 25 satır bekliyorlar | Bizde istinaf için yön alanı yok (yerel `karar_lehine` var, `models.py`); seed 3 satır (25 lokal seed artığı) | **GEREKMEZ (25 satır):** ekibe kanonik 3 + A5 genişlemesi gönderilir; yön alanı ekip üretince değerlendirilir (ertelendi) |
| S8 | "İlgili Diğer Uzmanlık Alanları" çok değerli ek alan önerisi | `cases.sub_type_extra` şemada var, `;` ayraçlı, UI kapalı (`caseIntakeFields.ts:50 enabled:false`), aktarım yazmıyor | **KARAR (ertele):** ekip sütunu üretirse aktarım `sub_type_extra`'ya yazar + UI açılır. Şimdi iş yok |
| S9 | DB-006 Olay Türü / Hükümdeki Rol bizde henüz yok | Alanlar prod'da (Deploy #18), kapalı liste; gelmezse boş | **ZATEN VAR.** İş yok |

### 1.5 Kapsam ve senkron kuralları

| # | Ekibin dediği | Bizde gerçek durum | Hüküm |
| --- | --- | --- | --- |
| P1 | 370 derdest kartın listesi (en öncelikli); icra/tahkim/vergi hariç kalanın malpraktis olanlarını alacaklar | Sayı 06.09 ad-hoc ölçüm (plan #31), üreten script yok; `file_type` kolonu var, kategori sayımı kodda yok | **YAP (küçük, öncelikli):** salt-okunur script → xlsx: föysüz + DERDEST kartlar; sayfa 1 Hukuk/İdare/Ceza/Arabuluculuk (~175), sayfa 2 İcra/Tahkim/Vergi (bilgi); kolonlar DosyaNo(`klasor_no_2`), ofis no, müvekkil, tür, esas, mahkeme, açılış. 06.09 "föysüz kartlar plan dışı" kararıyla çelişmez: liste vermek maliyetsiz, kapsam kararı ekibin |
| P2 | Alan bazında öncelik: `Durum`/yeni dosya/arşiv **bizde** kazanır (kesim 30.07); klinik tasnif/yazım/biçim ekipte; künye belgeye dayanan tarafta | Aktarım `status`'u üzerine yazar (`DURUM_ESLEMESI`, `:542`, `:755`) → **30.07'den sonra bizde MAHZEN'e alınan kart paketle DERDEST'e geri döner** (gerçek risk). `case_history` `status` için tutuluyor ama elle yolda `changed_by/source` NULL (`case_manager.py:1010-1027`); aktarım imzalı (`AKTARIM_SOURCE_PREFIX`) | **KARAR → YAP (C):** "paket kazanır"ın tek istisnası: `status` için kesim tarihinden sonra aktarım-dışı `case_history` kaydı varsa paket yazmaz, rapora düşer. Kesim tarihi `DEGISIKLIK_OZETI`'ne "Veri kesim tarihi:" satırı (ekipten istenir; yoksa paket adındaki tarih). Klinik/yazım: zaten paket kazanır. Künye: A1 istisnası |
| P3 | 4.437 icra/tahkim + vergi hiç gelmeyecek; "Kapsam dışı işaretlemeyin" | Kapsam işareti yalnız sayfadan (`:2218-2275`); pakette olmayan föye dokunulmaz | **ZATEN VAR.** Plan #31 ile uyumlu |
| P4 | 210 yeni karta itiraz yok; `Durum`da bizim kayıt esas | G126 kartları lokalde; prod'da henüz yok | **ZATEN VAR.** P2 kuralı bunları da korur |
| P5 | Sütun sahipliği tablosu (klinik/kimlik ekip, kart/iş akışı biz, yargı zinciri ekip yazar biz fotoğraflarız) | Bizim modelle örtüşüyor; tek fark A3 (karar durumu yönü) ve A1 (belgeli künye) | **ZATEN VAR.** Sözleşmeye tablo olarak girer (G148 ya da ayrı docs) |

---

## 2. 04.09 cevabımızdaki düzeltilecek ifadeler

| Cevap §, iddia | Gerçek | Nasıl düzeltilir |
| --- | --- | --- |
| §2 "33.441 hücre bizde değişmiş görünmez" | Eşleştirme etkilenmez (doğru) ama kapı sayımı hücre bazlı, casing farkı sayılır ve üzerine yazılır (K2) | Cevapta açıkça: "sayılır, ilk teslim zaten insan onaylı, sorun değil" |
| §1 DB-002 "sütunlar bugün okunmuyor" | G119-G122 ile okunuyor, 04.09 paketinde işlendi (S2) | "Alan açıldı, 04.09'dan itibaren işlendi" |
| §3 istinaf havuzu 3 değer | Kod seed'i 3; lokal seed 25 (bozuk yazımlar). Ekip 25'i "kanonik liste" sandı (S7) | Kanonik = 3 + A5 genişlemesi; 25 artık |
| §5 "yazma izniniz tanımlı" | Tenant ayrımı (K1) | G147 sonrası bağlantı |

---

## 3. Görev adayları (öncelik sırası, bant, büyüklük)

| Sıra | İş | Kalem | Bant | Büyüklük | Bağımlı | Durum (10.09) · kanıt |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Teslim hattı Hanyaloğlu site'ı | K1 | backend → docs | G147, G148 (kuyrukta) | — | **G147 + G148 tamam** (08.09) · `services/teslim_kutusu.TESLIM_SP_CONFIG`, `sharepoint/auth_graph.py`; prod `.env`/klasör/anahtar insan adımı bekliyor |
| 2 | 370 derdest kart listesi script + xlsx | P1 | backend (salt okunur) | küçük | — | **G149 tamam** (08.09) · `scripts/foysuz_derdest_kartlar.py` |
| 3 | Aşama katmanı kuralı: paket kaynaklı satır güncellenir, BELGE/UYAP dokunulmaz, boş hücre imzaya girmez, çok tur `sira_no` | A1, A2 | backend | **büyük** (aktarım + test + ikinci koşu 0 kanıtı) | — | **G150 tamam** (08.09) · `stage_decisions.update_stage_decision`/`is_protected`, `hukdok_aktarim._asama_uzlasisi`/`_asama_satirini_uygula`; lokal 04.09 paketi 310 eklendi / 116 güncellendi, 12 bayat → 0, ikinci koşu 0; çelişki grubu 532 → 227 |
| 4 | Yerel havuzdan `Kapalı/Derdest` çıkar + aktarım "karar yok" kuralı; seed genişlemesi (A5); bozuk 22 yazım temizliği | A4, A5 | backend + panel | küçük | 3 ile aynı dosya → zincir | **G151 tamam** (08.09) · seed 27/8/4/2, `BURO_DURUMLARI`, `deger_havuzu_seed.py --kaldir`; lokalde Kapalı/Derdest silindi; **bozuk yazım panel temizliği insan adımı**, `Karar` ekibe soru |
| 5 | `status` kesim-sonrası koruma (`case_history` aktarım-dışı imza) + `DEGISIKLIK_OZETI` "Veri kesim tarihi" | P2 | backend | orta | 3 | **G152 tamam** (08.09) · `kesim_sonrasi_kullanici_kaydi`, `KORUNDU` türü, `teslim_kutusu.kesim_tarihi_bul`, `case_manager.PANEL_SOURCE` |
| 6 | DosyaNo kökü → müvekkil adımı + föy↔müvekkil bağı (`case_party_id`) + "Müvekkil değişti" raporu | M2, M4 | backend | orta | 3 | **G153 tamam** (08.09) · `DOSYANO_KOK_MUVEKKILI`, `_kokun_karti_mi`, `_foy_muvekkilini_bagla`, `MUVEKKIL_DEGISTI`; lokal 8.385 föy bağlı, belirsiz 20 → 10, kök çelişkisi 7 (Corpus ×4, Ergo, DN-11927, H-6589 — ekibe soru) |
| 7 | 20 föyü cevaplı xlsx ile bağlayan script | M1 | backend (script) | küçük | 6 (kök kuralı yoksa elle kart no ile de olur) | **G154 tamam** (08.09) · `scripts/cevapli_kart_eslemesi.py` → `--kart-esleme` |
| 8 | `Başvuru Tarihi` aşama kolonu + okuyucu + fotoğraf | A6 | backend (migration) | orta | 3 | **G155 tamam** (10.09, ikinci koşu; test_g062/g073 kilit izni) · `case_stage_decisions.basvuru_tarihi`, migrasyon 47, `_basvuru_tarihi_uzlasi`, `asama_kaynakli_kart_alanlari` |
| 9 | Delta paket: "Teslim türü" satırı, kaybolan başlık bilgi; `—` zincir başlangıcı | K6, K4 | backend | küçük | — | **G156 tamam** (10.09) · `teslim_turu_oku`, `_DELTA_IHLAL_KATEGORILERI`, `teslim_dogrula` zincir başlangıcı |
| 10 | Çelişki raporu üreticisini repoya al, yer tutucu sınıfı | A7 | backend | düşük | 3 | **G157 tamam** (10.09) · `services/asama_celiski_raporu.py` + CLI, S6 yer tutucu sınıfı, E-8 etiketi |
| 11 | `sub_type` yazım farkında paket yazsın (karar) | M6 | backend | küçük | 3 | **G159 tamam** (10.09, 14 ile birlikte) · `ICERIK_KARSILASTIRMALI_ALANLAR = {"court"}`; lokal 4.521 → 196 |
| 12 | Çoklu avukatlı kartı eksik sayma (karar) | M5 | backend | küçük | — | **G158 tamam** (08.09) · `required_fields.COKLU_AVUKAT_ESIGI`, `scripts/backfill_missing_required.py`; lokalde kova düşüşü 0 (102 kartın öteki alanları da boş) |
| 13 | Sözleşme/dokümanlar: eşik = hücre, sütun sahipliği tablosu, delta kuralları, kesim tarihi satırı | K2, P5, K6 | docs | küçük | 9 | **G161 tamam** (10.09) · `SOZLESME.md` 1.3, `veri-teslim-hatti.md` §7.1, `dava-acma-akisi.md` §9/§10/§13, CLAUDE.md; ekibe cevap (§6) insan adımı |
| 14 | `tr_title` DB-008 kuralı + `yazim_birligi.py` | §5.3-C/B | backend | orta | 3, 11 | **G159 + G160 tamam** (10.09) · `reference_lists.tr_title`, `scripts/yazim_birligi.py` (dry-run varsayılan; prod'da paket uygulamasından SONRA `--apply`) |
| 15 | `bureau_types` liste düzeltmesi | §5.2 | panel/insan | küçük | — | **bekliyor** (insan, panel) |

**Prod sırası (değişmedi, iki ek):** deploy → havuz seed → **G147 env + klasör** → 04.09 paketi
**teslim hattından** (defter, zincir başlangıcı) → kart aç → birleştir → 20 föy bağla → ölçüm paketi.

---

## 4. Kullanıcı kararları — verildi (08.09), uygulandı (08–10.09)

1. **A3 — karar durumu föy düzeyi:** **hayır** (verildi 08.09); föy düzeyi alan açılmadı, G157 çelişki raporunda
   E-8 "müvekkil yönü farkı" etiketi (föy panelinde `ham_veri` gösterimi ayrı küçük iş, yapılmadı).
2. **P2 — `status` kesim-sonrası koruma:** **evet** (verildi 08.09) → G152.
3. **M6 — `sub_type` yazım farkında paket yazsın:** **evet** (verildi 08.09) → G159; `court` bizde kalır.
4. **A4 — `Kapalı/Derdest` yerel havuzdan çıksın:** **evet** (verildi 08.09) → G151.
5. **M5 — çoklu avukatlı kart eksik sayılmasın:** **evet** (verildi 08.09) → G158.
6. **A5 — "Karar" (74 föy) değeri:** ekibe sorulacak, havuza girmedi (G151 bilerek eklemedi; SOZLESME 1.3 §6 soruyor).
7. **S8 — ek uzmanlık alanı:** ertelendi (verildi 08.09).

## 5. Yazım birliği — yalnız büyük/küçük harf farkları (ölçüm 08.09, lokal, salt okunur)

**Soru (kullanıcı):** DB'de teslimden yalnız büyük/küçük harf yazımıyla ayrılan değerler var mı; varsa
föylerin (teslimin) biçimine çevrilsin. **Yöntem:** her föyün `case_foys.ham_veri` ham satırındaki değer,
bağlı kartın/tarafın DB değeriyle Türkçe büyük-harf anahtarında karşılaştırıldı (`turkish_upper`); anahtar
aynı, dizgi farklıysa **YALNIZ_HARF**. Betik: scratchpad `yazim_farki_olc.py`; ayrıntı 12.340 satır
`veri-ekibi-cevap-2026-09-06/yalniz_harf_detay.csv` (alan · kart · SistemNo · bizde · teslimde).

### 6.1 Önce nüans: teslimin kendisi her sütunda "İlk Harf Büyük" DEĞİL

DB-008 yalnız dört sütunu standartlaştırdı. Paketin 8.386 föyünde sütun bazında tamamı-BÜYÜK-HARF hücre oranı:

| Sütun | BÜYÜK oranı | Hedef yazım |
| --- | --- | --- |
| Müvekkil · Karşı Taraf · Uzmanlık Alanı · Buro Özel Türü · Dava Konusu · Taraf Sıfatı · Sorumlu Avukatlar · karar durumları · tıbbi beşli | **%0** | **teslim** (İlk Harf Büyük) |
| Yerel Mahkeme | %7 (610/8.085) | karışık → **bizim** başlık biçimi (mahkeme adı kimliği G067-G070 bizde) |
| Sigortalı | **%99** | teslim standartlaşmamış → **bizim** (Title) korunur; ekibe DB-008 genişletme sorusu |
| Davalı İdare · İstinaf Mahkemesi · Temyiz Mahkemesi | **%100** | aynı; kart `istinaf_mahkemesi`/`temyiz_mahkemesi` 1.241/436 BÜYÜK ve `appeal_courts` 217 / `cassation_courts` 38 listeleri tamamen BÜYÜK — **paket kaynaklı (A sınıfı)**, bizde dönüştürmek boşa iş: sonraki paket geri yazar |
| Sorumlu Avukatlar | %0 ama soyad BÜYÜK ("Rana Betül GÜMÜŞ") | **bizim** kart yazımı (aktarım zaten bizimkini seçiyor, `avukat_haritasi_kur`) |

Yani "föylerin formatına çevir" kuralı **yalnız DB-008 sütunlarında** uygulanır; öteki sütunlarda teslim biçimi
BÜYÜK HARF olduğundan bizimki korunur ve ekibe "DB-008'i Sigortalı, Davalı İdare, üç mahkeme sütununa
genişletin" denir.

### 6.2 Ölçüm: nerede, kaç, neden

| Alan | YALNIZ_HARF çift | Tekil dönüşüm | Yön | Kök neden | Sınıf |
| --- | ---: | ---: | --- | --- | --- |
| `cases.sub_type` (Uzmanlık) | **4.521 kart** | 17 | "Kadın Hastalıkları **Ve** Doğum" → "… **ve** Doğum" | `tr_title` bağlacı büyütüyor (`reference_lists.py:49-56`); `sub_type` içerik-karşılaştırmalı olduğundan paket düzeltemedi. `specialties` listesi zaten doğru yazımda (`Ve` içeren 0) → kart ↔ liste uyumsuz | **C + B** |
| `case_parties` Müvekkil | **3.209 satır** | 68 | "Axa Sigorta **A.ş.**" → "**A.Ş.**" (1.485), Ak 1.444, Sompo 168, Eureko 22; 63 satır tamamen BÜYÜK (Nisan aktarımı) | `tr_title` kısaltmayı bozuyor ("A.Ş." → "A.ş."); taraf satırı yalnız-ekleme, paket düzeltemez | **C + B** |
| `case_parties` Karşı Taraf | 237 | 170 | 131 bizde BÜYÜK ("SAĞLIK BAKANLIĞI" 30), 102 `tr_title` artığı ("(adına", "Ve"), 4 teslim BÜYÜK | Nisan aktarımı + `tr_title` | **B** |
| `case_parties` Sigortalı / Davalı İdare | 800 / 111 | 697 / 7 | bizde Title, **teslim BÜYÜK** | teslim standartlaşmamış | **korunur** (A: ekibe) |
| `cases.court` | 407 | 233 | 388 bizde Title, teslim BÜYÜK (icra müdürlükleri, başsavcılıklar) | teslim %7 karışık | **korunur**; DB-içi ikiz ayrı (aşağıda) |
| `cases.subject` | 10 | 4 | "(**t**ıbbi" → "(**T**ıbbi", "(tck 89)" → "(TCK 89)" | `tr_title` parantez sonrasını büyütmüyor | **C + B** (föysüz kartlar) |
| `case_lawyers.name` / `responsible_lawyer_name` | 2.569 / 476 | 2 / 1 | "Gümüş" ↔ "GÜMÜŞ" | teslim soyadı BÜYÜK | **korunur** |
| `cases.bureau_type` | 0 harf farkı | — | 1.227 fark **içerik** (kardeş föy çelişkisi: Vekaletsiz ↔ Dr Özel) | — | plan #30 |

**DB içi ikizler (teslimden bağımsız, aynı anahtar farklı yazım):**

| Tablo.kolon | İkiz grubu | Etkilenen satır | Örnek | Çözüm |
| --- | ---: | ---: | --- | --- |
| `case_parties.name` | 111 | 7.666 | "Axa Sigorta A.ş." 3.783 · "AXA SİGORTA A.Ş." 5 · "Axa Sigorta A.Ş." 1 | teslim yazımına (DB-008 sütunlarından gelenler), yoksa baskın Title |
| `cases.court` | 64 | 1.115 | "İSTANBUL 6. TÜKETİCİ MAHKEMESİ" 1 · "İstanbul 6. Tüketici Mahkemesi" 55 | baskın (Title) yazıma; G067-G070 kimliğiyle |
| `cases.subject` | 6 | 6.454 | "Tazminat (Tıbbi …)" 5.988 · "(tıbbi …)" 103 | baskın yazıma |
| `case_parties.role` | 2 | 781 | "DAVALI" 6 · "Davalı" 634 | `party_roles` listesindeki yazıma (9 satır) |
| `cases.bureau_type` | 1 | 14 | "HASTANE ÖZEL MÜVEKKİL" 1 | liste yazımına |
| **`bureau_types` listesi** | — | 8 | listenin 8 değeri BÜYÜK ("DR ÖZEL"), kartlar Title ("Dr Özel" 1.520) — liste ↔ kart uyumsuz; ayrıca kartta listede olmayan "Hasta" 42, "Sağlık Personeli" 1, "Tür Seçiniz" 1 | listeyi kart/teslim yazımına çevir (rename `DEPENDENCIES` ile yayılır), "Hasta" listeye, "Tür Seçiniz" → boş |
| `specialties`, `party_roles`, `case_subjects`, `case_lawyers`, `responsible_lawyer_name` | 0 | 0 | — | temiz |

### 6.3 Dönüşüm planı (üç katman)

**C — kod (bir kez, kalıcı):** `tr_title` DB-008 kuralına getirilir: bağlaç küçük (ve, ile, veya, adına),
kısaltma korunur (A.Ş., Ltd., Şti., T.C., Dr., K.H., TCK, HD, İDD), parantez/tire sonrası büyük, yabancı
adlarda I/ı kuralı yok (Quick, HDI). `normalize_list_name` ve `_baslik_bicimli` aynı fonksiyonu kullanır → liste
ve aktarım aynı yazımı üretir. Kilit test: `test_g064_aktarim_cekirdek.py:896` "Çocuk Sağlığı **Ve**
Hastalıkları" beklentisi **değişir** (izin baştan). Ek: `sub_type` yazım farkında paket yazsın (§1.3 M6) →
sonraki paketler bu sınıfı kendiliğinden kapatır.

**B — tek seferlik dönüşüm scripti (`scripts/yazim_birligi.py`, dry-run varsayılan, `--apply`, tarihçeli):**

| Adım | Kaynak harita | Hedef | Satır (lokal) |
| --- | --- | --- | --- |
| 1 | `ham_veri` YALNIZ_HARF çiftleri (Uzmanlık Alanı) | `cases.sub_type` | 4.521 |
| 2 | `ham_veri` çiftleri (Müvekkil, Karşı Taraf) + DB-içi ikizler → teslim yazımı, yoksa baskın Title | `case_parties.name` | ~3.450 + ikiz kalanı |
| 3 | DB-içi ikiz → baskın yazım (Title), G067-G070 kimliği | `cases.court` | 1.115 |
| 4 | DB-içi ikiz → baskın | `cases.subject` | ~110 |
| 5 | `party_roles` yazımı | `case_parties.role` | 9 |
| 6 | liste rename (`update_item`, DEPENDENCIES yayar) | `bureau_types` 8 satır + "Hasta" ekle + "Tür Seçiniz" boşalt | 8 + 42 + 1 |
| — | DOKUNMA | Sigortalı, Davalı İdare, istinaf/temyiz mahkemesi + listeleri, avukat adları | — |

Kurallar: `case_history` "yazim_birligi" imzalı; taraf satırı **güncellenir, silinmez** (belge bağı
`case_party_id` korunur; `case_documents.muvekkil_adi` 228 satır deprecated kopya, dokunulmaz);
ikinci koşu 0; belge envanteri denk; önce lokalde, prod'da paket uygulamasından SONRA (sıra §3).

**A — ekibe:** DB-008 kapsamı Sigortalı · Davalı İdare · Yerel/İstinaf/Temyiz Mahkemesi sütunlarına
genişletilsin (bizdeki 217+38 mahkeme listesi ve 1.677 kart alanı paketten BÜYÜK geldi); **`Yazim_Standardi`
tablosunu artık istiyoruz** (04.09'daki "gerek yok" düzeltilir: föysüz/eski kart değerleri için eski→yeni
haritası; Karşı Taraf 131 BÜYÜK satırın çoğu oradan çözülür).

**Görev adayı (§3 tablosuna ek):** 14 · `tr_title` DB-008 kuralı + `yazim_birligi.py` (backend, orta,
bağımlı: 3 ve 11) · 15 · bureau_types liste düzeltmesi (panel/insan, küçük).

## 6. Ekibe cevapta yer alacaklar (plan onaylanınca yazılır)

> 10.09: aşağıdaki kalemlerin metni `docs/veri-teslim/SOZLESME.md` 1.3'te hazır (§3 üç satır, §4 delta +
> dondurma gerekmez + kök, §6 havuzlar + Kapalı/Derdest + "Karar" sorusu, §7 eşik/K2 düzeltmesi, §10 sahiplik,
> §11 DB-008 + `Yazim_Standardi`). Bağlantı (G147 sonrası), 370 liste eki (G149 çıktısı), `specialties` 45
> listesi ve S5 satır 82 açıklaması cevap e-postasında ayrıca verilir — insan adımı.

Bağlantı (G147 sonrası) · kapı/zincir cevabı (K2, K3, K4) · delta 3 soru (K6) · havuz kanonik listesi (A5) ·
"Kapalı/Derdest yazmayın" (A4) · dondurma gerekmez (M4) · avukat satırları (M5) · 370 liste eki (P1) ·
`specialties` 45 listesi (ek) · S5 satır 82 açıklaması (A7) · 04.09 düzeltmeleri (§2) · "Karar" sorusu ·
DB-008'in Sigortalı/Davalı İdare/mahkeme sütunlarına genişletilmesi + `Yazim_Standardi` isteği (§5.3-A).
