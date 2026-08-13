# 017 — Elasticsearch ve Redis kapsam dışı: bellek bütçesi ve elimizdeki kullanılmayan altyapı

> Son doğrulama: 2026-08-12 · 74bb425 (G039)

- **Durum:** kabul
- **Bağlam:** Temizlik planı hazırlanırken iki "ölçek" bileşeni gündeme geldi: arama için
  **Elasticsearch**, cache için **Redis**. İkisi de tanıdık ve savunulabilir seçimler; bu
  yüzden reddedilme gerekçesi ve **hangi koşulda yeniden açılacakları** yazılı olmalı.
  Aksi hâlde aynı öneri altı ayda bir sıfırdan tartışılır.
- **Karar:** Her ikisi de **kapsam dışıdır**. Aşağıdaki eşiklerden biri gerçekleşmeden
  yeniden ele alınmaz.

## Ölçüm — kararın dayanağı

| Ölçüm | Değer | Kaynak |
| --- | --- | --- |
| Prod DB boyutu | **67 MB** | temizlik planı §6.0 prod ölçümü (2026-08-12) |
| `cases` satır sayısı | **14.395** | aynı |
| Backend konteyner bellek limiti | **2 GB**, `memswap_limit` eşit → **swap YOK** | `docker-compose.yml:92-93` |
| 2026-07-29 OOM'unda ölçülen backend anon bellek | **3,57 GB** | `docs/mimari/deploy-ve-altyapi.md:224` |
| `cases` üzerindeki GIN trigram index'leri (ölçüm anında) | 6 adet, **26.896 kB ≈ 26 MB**, **hiçbiri hiç taranmamış** (`idx_scan = 0`) — **G042'de DÜŞÜRÜLDÜ, bkz. güncel not** | temizlik planı §6.0 madde 3 |
| Aday indeksi DB yüklemesi (tanıdık sorgu) | 1.998 + 49.857 satır, **~550 ms** | `backend/routes/parties.py:8-11` (docstring, G017 ölçümü) |
| Hazırlanmış aday indeksinin bellekteki boyutu | **~34 MB**, **worker başına** (2 worker) | `backend/routes/parties.py:41-45` |

> Trigram toplamı: `subject` 6.112 + `tracking_no` 5.472 + `court` 5.424 + `klasor_no_2`
> 3.528 + `esas_no` 3.328 + `resp_lawyer` 3.032 = **26.896 kB**. Kaynak plan bunu "~27 MB"
> diye yuvarlıyor; altı kalemin toplamı 26 MB'dir.

## Karar 1 — Elasticsearch: kapsam dışı

**Gerekçe.**

1. **Bellek aritmetiği tutmuyor.** ES'in gerçekçi asgari JVM heap'i ~1 GB — yani
   **veritabanının kendisinin ~15 katı**. Backend'e ayrılan bütçenin tamamı 2 GB, swap
   bilinçli olarak kapalı ([`011`](011-bellek-swap-yasagi.md)) ve bu kutu 2026-07-29'da
   3,57 GB'lık bir anon bellek büyümesiyle bir kez yenildi. Aynı VM'e 1 GB'lık bir JVM
   koymak, kök nedeni kapatılmış bir arızayı yeniden davet etmektir.
2. **Elimizdeki tam metin altyapısı zaten kullanılmıyordu.** Bu kayıt yazıldığında `cases`
   üzerinde 26 MB'lık altı GIN trigram index'i duruyordu ve **hiçbiri bir kez bile
   taranmamıştı** — sebep veri azlığı değil, aramanın 13 kolonu tek bir OR/EXISTS ağacında
   birleştirmesiydi; planlayıcı o ağaçta index seçemiyordu. Bu index'ler FAZ D 6.2'de
   (G042) **düşürüldü** (bkz. [`018-index-temizligi-37-kalem.md`](018-index-temizligi-37-kalem.md)).
   **Güncel not (G055, E8, 2026-08-13):** arama motoru UNION + çok terimli için
   INTERSECT-of-UNION'a yeniden yazıldı ve **index'ler geri eklenmedi** — ölçüm, kazancın
   trigram index'lerden değil sorgunun bağımsız SELECT'lere bölünmesinden geldiğini,
   çok terimli aramada index'siz bile ölçülebilir (5-9×) olduğunu gösterdi. Yani bu
   maddenin sonucu değişmedi (Elasticsearch hâlâ kapsam dışı) ama gerekçesi güncellendi:
   "kullanılmayan altyapı" artık yok, arama kendi kod değişikliğiyle hızlandı.
3. **Ölçek yok.** 14.395 satır ve 67 MB, Postgres için küçük veridir. Arama bugün yavaşsa
   sebebi motor değil, index seçimi ve sorgu şeklidir — FAZ D 6.2'nin konusu.

**Yeniden açma eşikleri** (biri yeterlidir):

- Arama **belge içeriğine** girmesi gerekirse (bugün yalnız dava kartı alanlarında);
- `cases` **~1M satırı** geçerse;
- **Düzgün index'le** ölçülen arama gecikmesi **>500 ms** olursa. ("Düzgün index'le"
  şartı kasıtlı: index'siz bir ölçüm ES lehine kanıt sayılmaz.)

**Postgres tam metin notu — doğrulanmadı, doğrulanmalı.** Kaynak tartışmada "Postgres'in
`turkish` tam metin konfigü mevcut imajda hazır ve gövdeleme doğrulandı" iddiası geçti.
Bu kayıt **o iddiayı devralmıyor:** repoda `to_tsvector`/`tsquery`/`turkish` için **sıfır
eşleşme** var (yani sistem bugün tam metin araması hiç kullanmıyor) ve bu görev `docs`
bandında koştuğu için konteyner erişimi yoktu — iddia koşularak **doğrulanamadı**. İmaj
`postgres:15-alpine` (`docker-compose.yml:4`). Yeniden açma tartışması başladığında ilk
adım şu iki komuttur:

```sql
\dF turkish
SELECT to_tsvector('turkish', 'davalar davası davacının');
```

Çıktı gövdelenmiş tek bir kök gösteriyorsa ES'e giden yolun ilk alternatifi **elimizde
zaten var** demektir ve ölçüm o karşılaştırmayla yapılır.

## Karar 2 — Redis: kapsam dışı

**Gerekçe.**

1. **Çözdüğü sorun süreç-içi cache ile zaten çözüldü.** Tanıdık sorgu aday indeksi
   G017'de süreç-içi TTL cache'e alındı: iki tam tablo sorgusu (1.998 + 49.857 satır,
   ~550 ms) ve satır başına isim normalizasyonu artık her istekte tekrarlanmıyor
   (`backend/routes/parties.py:8-11`). Redis bu yola bir **ağ atlaması**, bir konteyner ve
   yeni bir arıza modu ekler — hızlandırmaz, yavaşlatır.
2. **2 GB'lık kutuda yer yok.** Aynı bellek bütçesi ([`011`](011-bellek-swap-yasagi.md)).
3. **Tazelik gereksinimi zaten karşılanmış.** TTL 60 sn ve **invalidasyon bilinçli olarak
   yok** (`backend/routes/parties.py:30-39`): salt-okunur bir uyarı ucu için "yeni eklenen
   müvekkil en geç 60 sn içinde görünür" garantisi kabul edilmiş bir sözleşmedir. Redis'in
   getireceği tek gerçek yetenek — worker'lar arası anında invalidasyon — bugün **istenen
   bir şey değil**.

**Yeniden açma eşikleri** (biri yeterlidir):

- Tek VM'den çıkıp **yatay ölçeklersek** — süreç-içi cache orada çalışmaz;
- **Worker'lar arası cache invalidasyonu bir iş gereksinimi** hâline gelirse, yani 60 sn'lik
  gecikme kabul edilemez olursa.

> Bugünkü tasarımın kendi sınırı da yazılı: hazırlanmış indeks worker başına ~34 MB ve iki
> worker ayrı ayrı tutuyor; bu yüzden **tek girdi** politikası uygulanıyor, iki tenant
> dönüşümlü sorgularsa her istek soğuk oluyor (`backend/routes/parties.py:41-45`). Bu
> bilinen ve kabul edilmiş bir davranıştır — Redis tartışması yeniden açılırsa ölçülecek
> nokta da burasıdır.

## Reddedilenler (bu kararın kendisine yapılan itirazlar)

- **"Şimdiden kuralım, sonra ölçekleniriz"** — 67 MB'lık bir veritabanı ve ~10 kullanıcı
  için 1 GB heap ayırmak, bugünkü tek gerçek kısıtı (bellek) bugünkü tek gerçek arıza
  moduna (OOM) doğru harcamaktır.
- **"Ayrı bir B-tree/arama çalışması yapalım"** — Postgres'te varsayılan index zaten
  B-tree ve **FAZ D 6.2 tam olarak bu iştir**: 52 kullanılmayan index'in düşürülmesi,
  4 index'siz FK kolonuna index, `cases.status` kısmi index'i,
  `substr(tracking_no,4,10)` fonksiyonel index'i. Ayrı bir kalem gerekmiyor.
- **Cache'i tümden kaldırıp her istekte DB'ye gitmek** — ölçülen maliyet ~550 ms/istek;
  dava açma oturumunda üst üste gelen sorgular bunu tekrar tekrar öderdi.

- **Test:** bu kayıt için yeni test yok (karar belgesi). Süreç-içi cache'in davranışı
  `backend/tests/test_party_check.py` ile kilitli — testler cache'i
  `reset_candidate_cache_for_tests` üzerinden sıfırlıyor (`backend/routes/parties.py:132-140`).
- **İlgili:** [`011-bellek-swap-yasagi.md`](011-bellek-swap-yasagi.md),
  [`docs/plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md`](../plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md) §9 (kapsam dışı) + §6.0 (prod ölçümü) + §6.2 (index temizliği),
  [`docs/mimari/deploy-ve-altyapi.md`](../mimari/deploy-ve-altyapi.md)
