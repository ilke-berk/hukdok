# Gece Kuyruğu (workflow) · 2026-09-07f

## Özet

2 görev alındı · 2 işaretlendi · 0 bloke · 0 atlandı

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G145 — Katalog: secenek_sayilari + sıklık sırası + bos_sayisi (kaynak başına tek sorgu) + ölçüm | backend | `6343916` | geçti (test temiz, kırmızı-yeşil kanıtlandı, ihlal yok) | GEÇTİ (3 bulgu) | 3 tur, ana dizinde uygulandı (worktree yok, merge yok). Tur 2'de kolon başına GROUP BY yerine kaynak başına tek UNION ALL GROUP BY + COUNT(*) FILTER ile katalog medyanı 306-309 ms → 242 ms (hedef <300 ms). Son parmak izi: 2726 passed / 3 skipped, ruff temiz, mypy 61 dosya temiz. İzin kapsamında değiştirilen testler: test_g130 anahtar kümesi + sıra iddiası (sıklık sırası); assert sayısı azalmadı. Kapsam dışı ek: docs/plan §7.2 kısa şerh (görev madde 4 öngörüyordu). |
| G146 — Şerit: sayı rozetleri + sıfırlılar soluk/sonda + "Boş" birinci sınıf seçenek + boş çipi + "Eksik bilgi" hücresi | frontend | `6d4fef2` | geçti (test temiz, kırmızı-yeşil uygulanamaz, ihlal yok) | GEÇTİ (5 bulgu) | 3 tur, worktree `C:/dev/hukudok-wt/G146` dalı `gorev/G146`; merge yapıldı, entegrasyon yeşil, worktree temizlendi. Tur 1'de tek kırmızı kendi yeni builderState testinin JSON anahtar sırasıydı (test sahtesi RaporTanimi sırasına çekildi). Son koşu: vitest 887/887, tsc 0, lint 0. Yeni test dosyası açılmadı; mevcut izinli dosyalara +13 it eklendi, hiçbir test silinmedi/gevşetilmedi. Yan etki: HEAD'deki ChipSelect.tsx'te 1 NUL bayt vardı (git ikili sayıyordu), yeniden yazılınca kalktı — commit diff'inde "Bin" görünür. |

### Testi değiştirmeden geçilemeyen noktalar (hattın doğru çalıştığının kanıtı)

- **G145:** Mevcut G130 rapor testleri katalog şeklini ve seçenek sırasını sabitlemişti; görevin istediği `secenek_sayilari`/`bos_sayisi` anahtarları ve sıklık sırası bu iddiaları bilerek kırdı (görev tanımında izinli). Testler görev sözleşmesine göre güncellendi, assert sayısı korundu. Tur 3'te yeni test dosyasının ilk koşusundaki 3 kırmızı, test varsayımlarından kaynaklandı (FileType.code zorunlu, Case.active=None varsayılana düşüyor, sqlite qmark param) — üretim kodu değil, testler düzeltildi.
- **G146:** Tek kırmızı, görevin kendi yeni testindeki JSON.stringify anahtar sırası; üretim kodu değil, test sahtesi düzeltildi.

## Bloke

Bloke görev yok.

## Karar bekleyenler

- `gorevTanimiHatali=true` teşhisi olan görev yok; `kabulKarsilanmayan` listeleri her iki görevde de boş.
- Görev notlarından çıkan, karar isteyen adaylar (SORU olarak):
  - **G145 → boş semantiği farkı:** `bos_sayisi` TRIM'li boşları (boş string) sayarken `motor.py` `is_null` yalnız NULL süzüyor (motor dokunulmadı, filtre semantiği aynı). Frontend "Boş" çipiyle rozet sayısı arasında fark çıkabilir. Ayrı görev açılsın mı, yoksa `is_null` TRIM'li boşu da kapsayacak şekilde genişletilsin mi?
  - **G145 → DISTINCT katmanı artık tenant + soft-delete kurallı.** Prod'da tüm kayıtlar tenant NULL olduğundan pratik fark yok; bilinçli kabul mü?
  - **G146 → is_null tarih/sayı/metin "..." menüsünden kaldırıldı** (mantıkta duruyor, yalnız UI'dan çekildi, kapsam dışı sayıldı). Kabul mü, geri gelsin mi?
  - **G146 → görsel doğrulama yapılmadı:** worktree'de backend/katalog yoktu; G145 backend'i deploy edilmeden rozetler boş görünür. Deploy öncesi lokal stack'te tarayıcı dumanı istenir mi?
  - **G146 → "Boş" çipi +N sayımının dışında daima görünür** (13 kategoride +2 → +1). Tasarım kararı olarak kabul mü?

## İzin engelleri

yok (G145 ve G146 `izinEngelleri` listeleri boş).

## Atlananlar

Atlanan / zincir hatası / teslim hatası olan görev yok. Tavan nedeniyle atlanan: yok.

## Plan uyarıları (koşucudan)

- G145 ve G146 aynı plan (§7.2) sözleşmesine dayanır, farklı bantlarda PARALEL koştu; dosya kesişimi yok.
- G146 kapsamındaki bazı test dosyaları (FilterControl*.test.tsx, pages/ReportsPage*.test.tsx) glob olarak yazılmıştı; dosya[] listesine sabit adlar alındı.

## Çalışma ağacı notu

`.claude/settings.local.json` (M) ve `.claude/launch.json` (??) görev öncesinden kalma, iki görev de dokunmadı.
