# 018 — 37 index düşürülüyor: yapısal ikizler koşulsuz, altı trigram bilinçli bir bahisle

> Son doğrulama: 2026-08-13 · prod'da salt-okunur sorgulandı (`d0d806b`)

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

- **Test:** `backend/tests/test_index_envanteri.py` — envanter script'inin
  unique/primary'yi dışladığı ve `ix_cases_tracking_no`'nun listeye girmediği ayrı
  assertion'larla kilitli.
- **İlgili:** [`017-elasticsearch-ve-redis-kapsam-disi.md`](017-elasticsearch-ve-redis-kapsam-disi.md)
  (aynı trigram index'lerini "kullanılmayan arama altyapısı" olarak sayar),
  [`docs/plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md`](../plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md) §6.2,
  `gorevler/gorev/G042.md`, `gorevler/gorev/G055.md`
