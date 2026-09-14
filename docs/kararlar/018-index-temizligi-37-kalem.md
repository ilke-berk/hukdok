# 018 — 37 index düşürülüyor: yapısal ikizler koşulsuz, altı trigram bilinçli bir bahisle

> Son doğrulama: 2026-08-13 · prod'da salt-okunur sorgulandı (`d0d806b`)
> "Nihai index durumu" tablosu: 2026-09-14 · G193 — `backend/database.py` (main `e3ba26d`) + lokal
> restore kopyasında `pg_indexes` sorgusu; prod'da doğrulanmadı.

- **Durum:** kabul
- **Bağlam:** FAZ D 6.2 (G042) `cases` ve 23 başka tabloda 37 index düşürüyor. Karar
  kullanıcıya deploy öncesi sunuldu; itiraz **"sistem bitmedi, veri gelecek, dava takibi
  henüz yapılmıyor — bunlar ileride kullanılmaz mı?"** oldu. İtiraz yerindeydi ve iki
  kümeye farklı çarptığı için gerekçe ayrı ayrı yazılıyor. Aksi hâlde altı ay sonra
  "bu trigram index'leri neden yok" sorusu E8 bağlantısı görülmeden cevaplanır.
- **Karar:** **37'si de düşürülür.** Küme 1 koşulsuz güvenlidir; Küme 2 ölçülmüş bir
  bahistir ve geri alma yolu yazılıdır.

## Ölçüm — prod'da doğrulandı (2026-08-13, salt okunur)

| Ölçüm | Değer |
| --- | --- |
| Listedeki index'ten prod'da var olan | **37 / 37** |
| Listede **UNIQUE** olan | **0** |
| Listede **PRIMARY** olan | **0** |
| Toplam boyut (prod) | **29 MB** |
| Bunun altı GIN trigram'dan geleni | **26.896 kB ≈ 26,3 MB** |
| Altı GIN trigram'ın prod'daki toplam taraması | **0** |
| Altı GIN trigram'ı yeniden kurma süresi (lokal, 11 MB heap / 14.345 satır) | **292 ms** (altısı birden) |

`ix_cases_tracking_no` listede **YOKTUR** — ofis no tekilliğini tutan tek yapıdır ve
`idx_scan = 0` göründüğü için körlemesine silinme riski taşıyordu (bkz. G042'nin
pazarlıksız kuralı: kısıt doğrulaması `idx_scan`'i artırmaz).

## Küme 1 — 31 yapısal ikiz (~2,7 MB): koşulsuz güvenli

Her birinin **birebir aynı imzalı** (aynı `indkey`, aynı erişim yöntemi) hayatta kalan bir
ikizi prod'da adıyla doğrulandı. Kaynağı masum bir kaza: `models.py`'de birincil anahtar
kolonuna ayrıca `index=True` yazılmış, SQLAlchemy ikinci bir index kurmuş.

Taraması sıfır olmayanlar da dahil — tarama ikize geçer, planlayıcı için hiçbir şey değişmez:

| Düşecek | Prod taraması | Hayatta kalan ikiz |
| --- | --- | --- |
| `ix_cases_id` | 42.699 | `cases_pkey` |
| `ix_case_documents_id` | 4.593 | `case_documents_pkey` |
| `ix_export_outbox_id` | 1.879 | `export_outbox_pkey` |
| `ix_case_parties_id` | 430 | `case_parties_pkey` |
| `ix_upload_outbox_id` | 112 | `upload_outbox_pkey` |
| `ix_clients_id` | 90 | `clients_pkey` |

**"Veri büyüyünce lazım olur" itirazı bu kümeye uygulanmaz.** İkinci bir özdeş index,
birincinin yapamadığı bir şeyi hiçbir veri hacminde yapamaz; büyüme onları faydalı değil
**pahalı** yapar (her yazma iki kez).

**Dava takibi özellikle soruldu:** listedeki `ix_hearing_dates_id`,
`ix_case_stage_logs_id`, `ix_case_history_id`, `ix_case_history_case_id` yalnız
ikizlerdir; dava takibinin dayandığı gerçek yapılar (`hearing_dates_pkey`,
`case_stage_logs_pkey`, `idx_case_history_case`) **yerinde kalır**.

## Küme 2 — altı GIN trigram (~26,3 MB): bilinçli bahis

`idx_cases_subject_trgm`, `idx_cases_tracking_no_trgm`, `idx_cases_court_trgm`,
`idx_cases_klasor_no_2_trgm`, `idx_cases_esas_no_trgm`, `idx_cases_resp_lawyer_trgm`.
Bunların **ikizi yoktur**; tek dayanak prod'da 0 tarama.

**Kritik ayrım — bu index'ler "kullanılmıyor" değil, KULLANILAMIYOR.** Sebep veri azlığı
değil, sorgunun biçimi: arama 13 kolonu tek `OR` ağacında birleştiriyor
(`managers/case_manager.py`, arama dalı) ve planlayıcı o ağaçta index seçemiyor.
`EXPLAIN` ile gösterildi (2026-08-13, lokal, index geçici olarak geri kurularak):

```
A) SELECT id FROM cases WHERE subject ILIKE '%tazminat%'
   -> Bitmap Index Scan on idx_cases_subject_trgm        (index KULLANILIYOR)

B) ... WHERE subject ILIKE %..% OR court ILIKE %..% OR ... (13 kol)
   -> Seq Scan on cases                                   (aynı index KULLANILMIYOR)
```

Bunun sonucu: **arama trafiği ya da veri hacmi ne kadar artarsa artsın bu index'ler
devreye girmez.** Devreye sokan tek şey kodun değişmesidir — yani E8 (G055, UNION
yeniden yazımı).

**Bahis nedir:** bugün sıfır fayda veren, ölçülü maliyeti olan (26 MB + her yazmada
altı kez güncelleme) bir yapıyı, projenin **en büyük yazma dalgasından önce** kaldırmak.
FAZ F 8.409 föy yükleyecek; toplu yüklemeden önce ölü index düşürmek standart pratiktir.

**Bahsin diğer yüzü dürüstçe yazılıyor:** veri büyüdükçe `Seq Scan`'in maliyeti doğrusal
artar, yani büyüme E8'i "opsiyonel"den "zorunlu"ya taşır. O gün geldiğinde index'ler
geri gelir — **292 ms**. `rollback.sh` imajı döndürür, DB'yi döndürmez; ama bu geri alma
tek bir SQL dosyasıdır ve saniyenin üçte biri sürer, tek yönlü bir kapı değildir.

**G055 ile bağ (görev dosyasına yazıldı):** E8 çalışırsa `EXPLAIN`'inin istediği index'i
— yalnız onu, körlemesine altısını değil — `("index", …)` op'una geri ekler ve ölçülen
kazancını rapora yazar.

## Yeni kolonlara peşin index KONULMADI

G044 on yeni kolon açtı ve FAZ F onları dolduracak. Hiçbirine index konulmadı: index
bir sorgu onu isteyince, **ölçülerek** eklenir. Peşin index koymak tam da bu kararın
temizlediği durumu yeniden üretir.

Tek istisna bilinçli: `case_esas_numbers.esas_no` (G045) — eski esas numarasıyla arama
bilinen ve talep edilmiş bir ihtiyaçtır.

## Reddedilenler

- **"Altı trigram'ı bu deploy'da atlayalım, yalnız ikizleri temizleyelim."** Savunulabilir
  bir muhafazakârlıktı ve kullanıcıya sunuldu; **reddedildi** (2026-08-13, kullanıcı
  kararı: "muhafazakârlığa gerek yok, temizle, gerekirse sonra düşünürüz"). Kazancın
  26,3 MB'ı ve yazma amplifikasyonunun tamamı o altısındaydı — atlamak deploy'u
  2,7 MB'lık bir işe indirirdi.
- **"İleride lazım olur, dursun."** Küme 1 için yanlış (özdeş kopya hiçbir koşulda
  gerekmez); Küme 2 için sorgu biçimi engeli yüzünden **bekleyerek** çözülmez — kod
  değişmeden kullanılamazlar.
- **`idx_scan = 0` olan her index'i düşürmek.** Prod'da kullanılmayan görünen 96
  index'in 44'ü unique/primary'dir; kısıt doğrulaması sayacı artırmaz. G042 bu yüzden
  isim kalıbıyla değil `indkey` karşılaştırmasıyla eledi ve 52 aday yerine yalnız
  **37** düşürdü.

## Ek — 2026-09-14: legacy kolon index'leri boş kolondaydı, `case_foys`'a taşındı (G189)

14.09 performans denetimi (D2) şunu gösterdi: `cases.tku_no` / `cases.sistem_no` 14.578
kartta **0 dolu**, çünkü aktarım bu kimlikleri G123'ten beri föy tablosuna (`case_foys`)
yazıyor. Bu yüzden `idx_cases_tku_no_trgm`, `idx_cases_sistem_no_trgm` ve btree
`idx_cases_tku_no` boş kolonu tutuyordu. Aramanın (`_term_case_id_selects`) gerçekten
kullandığı üç `case_foys` kolu ise index'sizdi: her arama 3 seq scan × 4.635 sayfa.

- **Eklendi** (`_TRGM_INDEXES`, G043 deseni): `idx_case_foys_tku_no_trgm`,
  `idx_case_foys_sistem_no_trgm`, `idx_case_foys_onceki_tracking_no_trgm`
  (lokal boyut 336 / 344 / 96 kB).
- **Düşürüldü** (`_DUSURULECEK_INDEXLER["cases"]`, G042 deseni): yukarıdaki üç legacy
  index. İkisi sözlükten, btree'nin kaynağı madde 22'nin post-SQL'inden çıkarıldı.
  `uq_cases_sistem_no` tekillik kısıtıdır ve **dokunulmadı**.
- **Ölçüm** (lokal restore kopyası, `TKU-788`, sıcak önbellek):

  | Kol | Önce | Sonra |
  | --- | --- | --- |
  | `case_foys.tku_no` | Seq Scan, 4.668 buffer, 2,81 ms | Bitmap Index Scan, 60 buffer, 0,35 ms |
  | `case_foys.sistem_no` | Seq Scan, 4.635 buffer, 3,26 ms | Bitmap Index Scan, 11 buffer, 0,05 ms |
  | `case_foys.onceki_tracking_no` | Seq Scan, 4.635 buffer, 1,72 ms | Bitmap Index Scan, 11 buffer, 0,04 ms |
  | Tek terim UNION'ın tamamı | 26.917 buffer, 51,8 ms | 15.911 buffer, 47,8 ms |

  UNION süresinin kalanı `cases` üzerindeki index'siz kollardan geliyor.
- **Bilinen bedel:** `services/case_relations_auto.py`'deki `Case.tku_no IN (...)`
  sorgusu btree'yi kaybetti; lokalde 0,1 ms → 3,8 ms (1.440 sayfalık seq scan, kart
  ilişkileri görünümü başına bir kez). Kolon boş olduğu için sonuç değişmez.
  Sıfırdan kurulumda `models.py`'deki `index=True` ayrıca `ix_cases_tku_no`'yu yaratır.
  `models.py` bu görevin kapsamı dışında kaldı.
- **`cases` üzerindeki altı trgm index'i hâlâ geri eklenmedi.** Geri ekleme kararı
  G190'ın EXPLAIN kanıtına bağlı.

## Ek — 2026-09-14: altı trigram'dan dördü EXPLAIN kanıtıyla geri geldi (G190)

Bu kararın "Küme 2" bahsi E8'e bağlanmıştı: UNION yeniden yazımı index'i
*kullanılabilir* kıldıysa, EXPLAIN'in istediği — yalnız o — geri eklenecekti. G190 aynı
turda iki şeyi daha yaptı: boş legacy kolları (`cases.tku_no`/`sistem_no`) aramadan
çıkardı (17 → 15 kol) ve `with_total=True` aramada COUNT + sayfa sorgusunun iki kez
koştuğu UNION ağacını tek koşuya indirdi (D4).

**Yöntem:** lokal restore kopyası (14.578 kart), `scripts/perf_olcum --term` ile sıcak
önbellekte `EXPLAIN (ANALYZE, BUFFERS)`. Üç terim: `Turgal` (avukat soyadı), `2024/12`
(esas parçası), `Sulh` (mahkeme parçası); ek olarak `20` (2 harfli, gerileme sınaması).
Altı aday index geçici kuruldu, kol kol ölçüldü, reddedilenler düşürüldü.

**Tek terim UNION'ın tamamı** (çalışma · buffer · seq scan'li kol):

| Terim | G189 hâli (17 kol) | Kollar çıktı (15 kol) | + dört trigram |
| --- | --- | --- | --- |
| `Turgal` | 48,5 ms · 19.329 · 12/17 | 43,8 ms · 16.449 · 10/15 | 26,9 ms · 8.759 · 6/15 |
| `2024/12` | 39,5 ms · 15.867 · 11/17 | 32,5 ms · 12.987 · 9/15 | 16,2 ms · 7.295 · 5/15 |
| `Sulh` | 35,8 ms · 15.832 · 11/17 | 30,3 ms · 12.952 · 9/15 | 16,6 ms · 7.298 · 5/15 |
| `20` | — | 82,7 ms · 33.559 · 14/15 | 78,9 ms · 33.559 · 14/15 (plan birebir aynı) |

- **Eklendi** (`_TRGM_INDEXES`, G043 deseni) ve **`_DUSURULECEK_INDEXLER["cases"]`dan
  çıkarıldı** (ikisinde birden kalsa her açılışta düşürülüp yeniden kurulurdu):

  | Index | Kol önce (üç terim) | Kol sonra | Lokal boyut · kurulum |
  | --- | --- | --- | --- |
  | `idx_cases_court_trgm` | Seq Scan, 1.440 buffer, 5,3-5,9 ms | Bitmap Index Scan, 9-91 buffer, 0,0-0,5 ms | 1.048 kB · 106 ms |
  | `idx_cases_subject_trgm` | Seq Scan, 1.440 buffer, 4,0-5,2 ms | Bitmap Index Scan, 5-11 buffer, 0,0 ms | 616 kB · 71 ms |
  | `idx_cases_esas_no_trgm` | Seq Scan, 1.440 buffer, 4,0-4,4 ms | Bitmap Index Scan, 5-33 buffer, 0,0-0,3 ms | 464 kB · 24 ms |
  | `idx_cases_tracking_no_trgm` | Seq Scan, 1.440 buffer, 4,7-5,6 ms | Bitmap Index Scan, 5-12 buffer, 0,0-0,1 ms | 1.144 kB · 57 ms |

- **Ölçüldü, EKLENMEDİ:**
  - `case_esas_numbers.esas_no` trigram — seq scan zaten 19 buffer / 0,3 ms (1.280
    satır); index'le 5-11 buffer / 0,0 ms. Kazanç ≤ 0,3 ms, bu kararın "peşin index"
    ölçütüne takılır. Btree `idx_case_esas_numbers_esas_no` yerinde.
  - `case_history.old_value` trigram — seq scan 2.750 buffer / 1,3-1,5 ms; index'le
    5-13 buffer / 0,0-0,1 ms (152 kB). Kazanç ~1,4 ms. Kolonun (ve `cases.notes`un)
    normal modda aramadan ÇIKARILMASI ayrı bir seçenek ve davranış değişikliği →
    **kullanıcı kararı açık**. Karar "çıkar" olursa index ölü doğardı; "kalsın" olursa
    bu ölçümle eklenir.
- **İstenmedi, düşmüş kalır:** `idx_cases_klasor_no_2_trgm`, `idx_cases_resp_lawyer_trgm`.
  Not: `cases.klasor_no_2` artık kalan en pahalı `cases` kolu (1.440 buffer, 5,6-6,8 ms)
  ve ham `responsible_lawyer_name` kolu da seq scan (katlanmış ifade index'i
  `idx_cases_resp_lawyer_fold_trgm` ham `ILIKE`'la eşleşmez) — ayrı ölçüm konusu.
- **2 harfli terim:** trigram index'i 2 karakterlik deseni daraltamaz; planlayıcı dört
  index varken de seq scan seçti (plan ve buffer birebir aynı). Tuş vuruşu yolunda gerileme yok.
- **Bilinen bedel:** `cases` üzerinde dört GIN daha — aktarımın toplu UPDATE'inde yazma
  amplifikasyonu. Lokal tam kurulum süreleri 24-106 ms; aktarım süresi (2026-08-20
  ölçümü: 8.409 satır / 93 sn) sonraki koşuda izlenecek. Prod boyutları bu kararın
  2026-08-13 tablosundaki gibi lokalin ~5 katı olabilir (şişme, D3).
- **Test:** `backend/tests/test_g190_arama_tek_kosu.py` — sözlük/düşürme listesi
  ayrıklığı, reddedilenlerin yokluğu ve `dbtest`'te ikinci `init_db`de index oid'inin
  değişmediği + arama kolunun index'e düşebildiği.

## Ek — 2026-09-14: prod doğrulaması (Deploy #29, 906cda2)

G189 + G190 prod'da ölçüldü (`scripts/perf_olcum.py --term`, tek UNION `EXPLAIN (ANALYZE, BUFFERS)`, sıcak).
Önce c184c9a (13:25 TR), sonra 906cda2 deploy'u; ardından `VACUUM (FULL, ANALYZE) case_history, cases, case_foys`
(D3, kullanıcı kararı). Koşu kaydı ve komutlar: `docs/plan/prod-deploy-29-performans-turu-2026-09-14.md`.

| Terim | Önce (17 kol) | Sonra — kod (15 kol) | Sonra — VACUUM FULL |
| --- | --- | --- | --- |
| `Turgal` | 194,4 ms · 24.698 buffer · 12 seq | 47,9 ms · 9.097 · 5 seq | 46,4 ms · 3.238 · 6 seq |
| `2024/12` | 131,4 ms · 23.350 · 12 seq | 40,8 ms · 7.776 · 5 seq | 35,6 ms · 2.509 · 5 seq |
| `Sulh` | 127,6 ms · 23.322 · 12 seq | 46,7 ms · 7.886 · 5 seq | 32,6 ms · 2.540 · 5 seq |

- Prod işlemcisi lokalden ~3-4× yavaş (aynı kolda `cases` seq scan prod 12-18 ms / lokal 4-5 ms); kazanç
  milisaniye olarak prod'da büyüdü. Eski kod UNION'ı istek başına iki kez koşuyordu (G190 D4).
- Dört `cases` trigram'ı + üç `case_foys` trigram'ı kuruldu, düşürülecekler yok — açılış logu temiz, ERROR 0.
- Şişme (heap / satır verisi) VACUUM FULL ile case_history 15,67 → 1,09, cases 2,67 → 1,06, case_foys 2,08 → 1,11.
- VACUUM sonrası planlayıcı Turgal'da `case_lawyers.name`'i Merge Join (50,4 ms) yerine seq scan'le (9,7 ms) koştu.
  Kalan seq scan kolları `responsible_lawyer_name`, `case_lawyers.name`, `klasor_no_2`, `notes`, `old_value`,
  `case_esas_numbers`; `idx_cases_resp_lawyer_fold_trgm` (4.6 MB) `idx_scan = 0` — ifade eşleşmesi ayrı görev adayı.

## Nihai index durumu — 2026-09-14 (14.09 denetimi · G189 · G190 · G192)

14.09 performans denetiminin (`docs/arsiv/performans-denetimi-2026-09-14.md` D1, D2, D7,
D10) ve G189/G190/G192'nin ortak sonucu tek tabloda. "Kod" sütunu `backend/database.py`
satırıdır (main `e3ba26d`); "Lokal" sütunu lokal restore kopyasında `pg_indexes` sorgusudur
(2026-09-14, backend imajı bu kodla kurulu) — **prod'da DOĞRULANMADI**, prod'a ilk açılışta
aynı op'lar koşar. Yukarıdaki G189/G190 eklerindeki ölçüm sayıları lokaldir.

| Index | Kolon | Durum | Görev · kanıt | Kod | Lokal |
| --- | --- | --- | --- | --- | --- |
| `idx_case_foys_tku_no_trgm` | `case_foys.tku_no` | **EKLENDİ** | G189 · D2 (arama kolu seq scan'di) | `_TRGM_INDEXES` `:1404` | var |
| `idx_case_foys_sistem_no_trgm` | `case_foys.sistem_no` | **EKLENDİ** | G189 · D2 | `:1405` | var |
| `idx_case_foys_onceki_tracking_no_trgm` | `case_foys.onceki_tracking_no` | **EKLENDİ** | G189 · D2 | `:1406` | var |
| `idx_cases_court_trgm` | `cases.court` | **GERİ EKLENDİ** (G042'de düşmüştü) | G190 · D1, EXPLAIN eki yukarıda | `:1395` | var |
| `idx_cases_subject_trgm` | `cases.subject` | **GERİ EKLENDİ** | G190 · D1 | `:1396` | var |
| `idx_cases_esas_no_trgm` | `cases.esas_no` | **GERİ EKLENDİ** | G190 · D1 | `:1397` | var |
| `idx_cases_tracking_no_trgm` | `cases.tracking_no` | **GERİ EKLENDİ** | G190 · D1 | `:1398` | var |
| `idx_cases_tku_no` (btree) | `cases.tku_no` (yazıcısız, boş) | **DÜŞÜRÜLDÜ** | G189 · D2; kaynağı madde 22 post-SQL'i kaldırıldı | `_DUSURULECEK_INDEXLER["cases"]` `:1333` | yok |
| `idx_cases_tku_no_trgm` | `cases.tku_no` | **DÜŞÜRÜLDÜ** | G189 · D2 | `:1334` | yok |
| `idx_cases_sistem_no_trgm` | `cases.sistem_no` | **DÜŞÜRÜLDÜ** | G189 · D2 | `:1335` | yok |
| 20 × `ix_<tablo>_id` (`alleged_faults` … `service_types`) | PK ikizi | **DÜŞÜRÜLDÜ** | G192 · D10 seçenek B: `models.py` değişmez, `create_all` yaratır, op her `init_db`'de siler; kapsam bekçisi `tests/test_g192_dusuk_etkili.py::test_model_pk_ikizlerinin_tamami_dusurme_listesinde_dogru_tabloda` | `:1295-1314` | yok (adı `ix_*_id` olan kalan 7 index'in hiçbiri PK değil) |
| `idx_cases_klasor_no_2_trgm` | `cases.klasor_no_2` | **DÜŞMÜŞ KALIR** | G042; G190'da aday değildi | `:1326` | yok |
| `idx_cases_resp_lawyer_trgm` | ham `cases.responsible_lawyer_name` | **DÜŞMÜŞ KALIR** | G042; avukat filtresi katlanmış `idx_cases_resp_lawyer_fold_trgm` (G043, `:1415`) kullanır — ham `ILIKE` kolu onu kullanamaz | `:1327` | yok |
| `case_esas_numbers.esas_no` trigram | `case_esas_numbers.esas_no` | **ÖLÇÜLDÜ, EKLENMEDİ** | G190: kazanç ≤ 0,3 ms (peşin index ölçütü); btree `idx_case_esas_numbers_esas_no` yerinde | — | btree var |
| `case_history.old_value` trigram | `case_history.old_value` | **ÖLÇÜLDÜ, EKLENMEDİ — kullanıcı kararı AÇIK** | G190: A (normal modda `notes`+`old_value` aramadan çıkar) / B (index ekle) / C (bugünkü gibi) | — | — |
| `ix_cases_esas_no`, `idx_cases_tenant`, `idx_cases_tracking_name_block`, `ix_case_lawyers_name`, `idx_case_lawyers_lawyer`, `idx_case_parties_tc_no`, `ix_clients_name` | çeşitli | **BEKLİYOR — prod sayacına bağlı** | D7: yalnız lokal `idx_scan = 0` (restore'da sayaç anlamsız); karar prod `pg_stat_user_indexes` ~30 gün (`scripts/perf_olcum.py` bölüm 4), düşürme G042 deseniyle | düşürme kodu yok | 7/7 var |
| `uq_cases_sistem_no` | `cases.sistem_no` | **DOKUNULMAZ** | tekillik kısıtı, kullanıcı kararı (G189) | — | var |
| `idx_case_docs_conversion_pending` | `case_documents (id) WHERE pending` | **DOKUNULMAZ** | G192: parçalı, PK ikizi DEĞİL; müşterisi `services/conversion_retry.py` gece taraması | — | var |
| `idx_upload_outbox_pending` | `upload_outbox (next_attempt_at) WHERE pending` | **DOKUNULMAZ** | G192 · D15: tarama vade koşulunu artık SQL'de taşır (`services/upload_queue.py:506-507`) | — | var |
| `ix_cases_tku_no`, `ix_cases_sistem_no` | legacy `cases` kolonları | **YALNIZ SIFIRDAN KURULUMDA** | `models.py:61-62` `index=True`; büyümüş kurulumda yok; `models.py` değişikliği ayrı karar (G189 NOT) | — | yok |

Aynı turda şemaya giren tek kısıt index değildir: `ck_cases_status_uclu` (G195, D9) madde 52
(`database.py:1229`) ile `NOT VALID` eklendi, lokal `convalidated = false`; `VALIDATE` prod
ölçümüne bağlı — ayrıntı [`docs/mimari/dava-acma-akisi.md` §4](../mimari/dava-acma-akisi.md).

- **Test:** `backend/tests/test_index_envanteri.py` — envanter script'inin
  unique/primary'yi dışladığı ve `ix_cases_tracking_no`'nun listeye girmediği ayrı
  assertion'larla kilitli.
- **İlgili:** [`017-elasticsearch-ve-redis-kapsam-disi.md`](017-elasticsearch-ve-redis-kapsam-disi.md)
  (aynı trigram index'lerini "kullanılmayan arama altyapısı" olarak sayar),
  [`docs/plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md`](../plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md) §6.2,
  `gorevler/gorev/G042.md`, `gorevler/gorev/G055.md`
