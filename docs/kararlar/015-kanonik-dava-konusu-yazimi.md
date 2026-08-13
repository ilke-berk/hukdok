# 015 — Kanonik dava konusu yazımı; asıl düzeltme veri değil kural

> Son doğrulama: 2026-08-12 · 74bb425 (G039)

- **Durum:** kabul — kullanıcı yetkisiyle verildi (12.08.2026)
- **Bağlam:** HUKDOK teslim paketinde en yaygın dava konusu iki farklı yazımla duruyor.
  Aktarım öncesi hangisinin kanonik olduğuna karar verilmezse 7.710 kayıt iki ayrı
  değere bölünerek gelir; `cases.subject` (`backend/models.py:27`) serbest metin bir
  kolondur ve arama, raporlama, dış yazışma hepsi bu metne bakar.
- **Karar:** Kanonik yazım —

  ```
  Tazminat (Tıbbi Kötü Uygulama Sigorta Poliçesinden Kaynaklanan)
  ```

  18 satırlık sapma varyantı bu değere çekilir.

## Gerekçe

1. **427:1 çoğunluk.** Kanonik yazım 7.692 satırda, varyant 18 satırda (karşı taraf ekibinin
   master üzerinde aldığı ölçüm, 12.08.2026). Azınlığı kazandırmak için 7.692 satır
   dokunmak, hiçbir şey kazanmadan risk almaktır.
2. **"Sigorta" kelimesi anlam taşıyor** — poliçe türünü belirtiyor, süs değil. Kısaltılmış
   varyant bilgi kaybıdır.
3. **Sapma bizde.** 18 satırlık varyant **bizim sistemimizde** açılmış; karşı tarafın
   raporlarında ve dış yazışmalarda geçen yazım kanonik olandır. Dışarısı zaten bu değeri
   biliyor.

## Reddedilenler

- **Kısaltılmış varyantı kanonik yapmak** — 7.692 satır dokunulurdu, "Sigorta" bilgisi
  kaybolurdu, dış yazışmalarla ayrışırdı.
- **İki yazımı da bırakıp arama tarafında birleştirmek** — her tüketicinin (liste,
  panel, export, hukukbot) aynı eşleme kuralını ayrı ayrı bilmesi gerekirdi. Aynı hata
  sınıfı doctype `_` padding'inde yaşandı: normalize etmeyi unutan tüketici sessizce sızdırır
  (`backend/services/export_publisher.py`).
- **Sadece veriyi düzeltmek** — aşağıdaki asıl mesele.

## Asıl düzeltme kural, veri değil

Bugünkü ayrışmanın sebebi **sondaki boşluk**. Veriyi tek seferlik düzeltip yazma yolunu
olduğu gibi bırakırsak aynı sapma tekrar doğar. Bu yüzden karar veriyi değil **yazma
kuralını** kapsar: kayıt anında `trim` + iç boşluk sadeleştirme. Bu FAZ F'nin **D7** maddesidir.

**Kod okumasının çıkardığı iki ayrı gerçek — uygulamadan önce bilinmesi gereken:**

1. **Referans listesi yolu boşluğu ZATEN sadeleştiriyor.** `add_item`
   (`backend/managers/reference_lists.py:228`) ve `update_item` (`:407`) adı
   `normalize_list_name` → `tr_title`'dan geçiriyor; `tr_title` (`:49-56`)
   `tr_lower(s).split()` + `" ".join(...)` yaptığı için baş/son boşluk ve tekrar eden iç
   boşluk kayboluyor. Mükerrer denetimi de `tr_upper` (`:41`) ile aynı sadeleştirmeyi
   yapıyor. Yani sondaki boşluk **bu yoldan** bugün geçemez.
2. **Ama `tr_title` kanonik yazımı BOZAR.** Her kelimenin ilk harfini kendisi belirlediği
   ve parantezi kelimenin ilk karakteri saydığı için:

   | Girdi | `tr_title` çıktısı |
   | --- | --- |
   | `Tazminat (Tıbbi Kötü Uygulama Sigorta Poliçesinden Kaynaklanan)` | `Tazminat (tıbbi Kötü Uygulama Sigorta Poliçesinden Kaynaklanan)` |

   `"(tıbbi"` kelimesinin ilk karakteri `"("` → `"(".upper()` yine `"("`, kalan harfler
   küçük kalıyor (`:54-55`). **Bu ADR'nin seçtiği kanonik değer bugünkü referans listesi
   yazma yolundan geçemiyor.**
3. **Dava kaydının kendi yolunda hiç normalizasyon YOK.** `Case.subject` hem yeni kayıtta
   (`backend/managers/case_manager.py:1278`) hem güncellemede (`:919`) forma ne yazıldıysa
   ham hâliyle yazılıyor — `trim` bile yok. Sondaki boşluğun girebileceği yer burasıdır.

**Sonuç — D7'nin hedefi kaynak belgede eksik yazılmış.** FAZ F tablosu D7'nin dokunduğu
yeri "Referans listesi yazma yolu" diye gösteriyor; ölçüm bunun **iki noktaya birden**
dokunması gerektiğini söylüyor:

- `Case.subject` yazma yoluna `trim` + iç boşluk sadeleştirme eklenir (bugün hiç yok);
- `tr_title`'ın parantezli sözcüğü küçülten davranışı, kanonik değer listeye alınmadan
  önce çözülür — aksi hâlde dropdown'daki değer ile `cases.subject`'teki değer birbirini
  tutmaz ve **bu ADR ilk günden ihlal edilmiş olur**.

- **Test:** bu kayıt için yeni test yok (karar belgesi). D7 uygulanırken kabul kriteri:
  kanonik dizgenin yazma yolundan **değişmeden** çıktığını gösteren bir test
  (`backend/tests/` altında; `tr_title` regresyonunu da kilitler).
- **İlgili:** [`docs/plan/faz-f-aktarim-gereksinimleri-2026-08-12.md`](../plan/faz-f-aktarim-gereksinimleri-2026-08-12.md) §4 K2 + §2 (D7),
  [`016-ofis-no-kategori-rejimi.md`](016-ofis-no-kategori-rejimi.md) (aynı ilke: kimliği
  değiştirme, kuralı düzelt)
