# Gece Kuyrugu (workflow) · 2026-09-10d

## Ozet

1 görev alındı · 1 işaretlendi · 0 bloke · 0 atlandı

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G163 · yazim_birligi.py adım 2b: tek yazımlı taraf adlarında yalnız biçim farkı tr_title'a çekilir; kuru koşu ilk 15 tekil, --apply KOŞULMAZ | backend | 1be2d23 | GEÇTİ (test temiz, kırmızı-yeşil kanıtlandı, ihlal yok) | GECTI (4 bulgu) | 2 tur; 22/22 adım testi, tam paket 3222 passed 3 skipped, ruff+mypy temiz. Merge YAPILMADI (mergeYapildi=false), worktree yok. Kabul kriterlerinden biri karşılanmadı — bkz. "Karar bekleyenler". |

Tur ayrıntısı (G163):
- Tur 1: `_adim_2_hesapla` + `adim_2b_taraf_adi_bicim` (anahtar_genis eşitliği, tr_title) + `_adimi_hesapla` ile `--adim 2 = [2, 2b]`; 6 yeni test → 1 test kırmızı (test yazım hatası: "Toplam satır" satırını `main()` basıyor, `kos()` değil; ikiz çift adım 2'de 2 satır değiştiriyor).
- Tur 2: test beklentileri `kos()` çıktısına ve gerçek sayımlara ({2: 2, '2b': 5}, tarihçe 7) düzeltildi → yeşil. Kırmızı-yeşil kanıtı HEAD script'iyle 5 failed / 1 passed (geçici kopyayla, git checkout/stash kullanılmadı, geçici dosyalar silindi).

## Bloke

Bloke görev yok.

## Karar bekleyenler

Görev tanımı hatalı işaretlenen (gorevTanimiHatali=true) görev yok. Kabul kriteri karşılanmayan maddeler SORU olarak:

- **G163 — "İlk 15 tekilde Türk Nippon görünür" kriteri karşılanmadı.** "Turk Nippon Sigorta As" (204 satır) grubunun TESLİM ANAHTARI VAR; paketin kendi Müvekkil/Karşı Taraf yazımı da "As". Adım 2 teslim yazımını hedef alır (0 değişiklik), görev tanımı 2b'yi "teslim anahtarı yok" gruplarla sınırlar → tasarım gereği 2b'ye girmez. Yalnız 1 satırlık "Turk Nippon Sigorta A.s." 2b'de (sıra 1650). İlk 3: Quick / Koru / Ankara. SORU: Bu kriter görevin kendi §1 tanımıyla çelişiyor — kriter mi düşürülsün, yoksa adım 2'ye "teslim yazımı yalnız biçimse tr_title" kuralı ayrı görev olarak mı açılsın? (Paketin "Aş"/"Aş." yazdığı gruplarda teslim yazımı DB-008'e aykırı kalıyor.)
- **G163 — İlk 15 tekil onayı.** Onaylanırsa lokalde `--apply --kim <ad>`; prod §6e öncesi kuru koşu şart. --apply gece koşulmadı (tanım gereği).
- **G163 — Combining-dot U+0307** 806 tekil adda; 2b yalnız Ve→ve / A.ş→A.Ş gibi biçim farkını değiştirir, bozukluğa dokunmaz → ayrı NFC temizlik görevi açılsın mı?
- **G163 — tr_title "Aş." → "AŞ."** üretir (KISALTMALAR), "A.Ş." ile birleştirmez; kurala dokunulmadı. Birleştirme istenirse ayrı karar.

## Izin engelleri

yok

## Atlananlar

Atlanan / zincir hatalı / teslim hatalı görev yok. Tavan nedeniyle atlanan: yok.

Plan uyarıları (koşu öncesi, bilgi):
- G163: kabul kriterleri lokal kuru koşu için konteynerde canlı DB ister; --apply KOŞULMAZ; test-değiştirme izni yalnız adım 2/2b testleri için.
- G162: docs bandı; §3.8 sayıları konteynerde seed'den koşularak alınmalı (docker gerekir), docs/arsiv/ değişmemeli. (Bu koşuda alınmadı.)

Not: çalışma ağacında `.claude/settings.local.json` (M) ve `.claude/launch.json` (??) koşucu ortamı dosyaları; kapsam dışı, commit'e girmedi.
