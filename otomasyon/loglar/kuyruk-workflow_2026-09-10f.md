# Gece Kuyruğu (workflow) · 2026-09-10f

## Özet

1 görev alındı · 1 işaretlendi · 0 bloke · 0 atlandı

Tavan nedeniyle atlanan: yok.

Plan uyarıları: kuyrukta yalnız 1 açık görev vardı (G164); G164 `--apply` KOŞULMAZ, yalnız kuru koşu (kullanıcı kararı 10.09); G164 dosya kapsamındaki test dosyası için test değiştirme izni VAR (görev dosyasında yazılı).

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G164 — `yazim_birligi.py` anahtarı son noktayı yutar ("A.Ş"↔"A.Ş." nokta ikizleri birleşir; kuru koşu ilk 15, `--apply` koşulmaz) | backend | `9d6ac3a` | GEÇTİ (test temiz, kırmızı-yeşil kanıtlandı, ihlal yok) | GEÇTİ (3 bulgu) | 1 tur, verify yeşil. Son parmak izi: `tests/test_g160_yazim_birligi.py` 26 passed; tam paket 3226 passed / 3 skipped; ruff temiz; mypy 62 dosya Success. Merge yapılmadı (`mergeYapildi=false`), entegrasyon/worktree alanı boş. |

**G164 ayrıntı (denenen yaklaşım, tur 1):** anahtar = boşluk normalize + `turkish_upper` + `rstrip('.')` + yeniden normalize; adım 2/2b kodu değişmedi. 4 yeni test önce eski kodla koşuldu (4 failed — kırmızı kanıtı), sonra yeni kodla 26/26 yeşil.

**Görev notları (koşucudan):**
- Kirli dosyalar `.claude/settings.local.json` (M) ve `.claude/launch.json` (??) iş öncesinden vardı; kapsam dışı IDE/koşucu ayarları, dokunulmadı, commit'e girmedi.
- İlk kuru koşuda Git Bash MSYS yol çevirimi `/tmp/yb_once`'ı `C:/Users/...` yapıp konteynerde `/app/C:/` altında klasör açtı (`backend/C:` untracked); iş sonunda silindi, çalışma ağacı temiz. Sonraki komutlarda `MSYS_NO_PATHCONV=1` kullanıldı.
- Görevde Ak / Sağlık Bakanlığı için "baskın" öngörülmüştü; lokalde teslim anahtarı bulundu (teslim kazanır, sonuç aynı yazım).
- Combining-dot bozuk adlar (Mlp Sağlık Hi̇zmetleri̇, Türki̇ye Si̇gorta) G163 kararı gereği olduğu gibi kalıyor; yalnız son nokta hizalanıyor.
- İzlenecek: kullanıcı ilk 15'i onaylayınca lokalde `--apply --kim` (adım 2 = 844 beklenir, ikinci koşu 0), prod §6e aynı koşu.

## Bloke

Bloke görev yok.

## Karar bekleyenler

`gorevTanimiHatali=true` teşhisi olan görev yok.

Kabul kriteri karşılanmayan madde (G164) — SORU:

- **G164 / adım 2 sayısı:** Görev dosyası adım 2 kuru koşusunda "≈ 4.000" satır tahmin ediyordu; gerçek çıktı **844 satır / 161 tekil**. Konteynerde ayrı mutabakat: yeni anahtarla çok-yazımlı grup 134 / 4.166 satır (görevdeki ölçümle birebir), eski anahtarla 0 — yani 4.166 gruplardaki TOPLAM satırdır; değişen yalnız hedef dışı azınlık yazımı (Ak 1.383 kalır / 7 değişir; Quick teslim noktalı → 578 değişir / 81 kalır). Kural görevdeki gibi işliyor, 844 doğru sayı; görev dosyasında kriter bu gerekçeyle işaretlendi. **Soru:** 844 sayısı ve bu gerekçe kabul ediliyor mu; kabul ediliyorsa ilk 15 satırlık kuru koşu çıktısı onaylanıp lokalde `--apply --kim` koşulsun mu?

## İzin engelleri

yok

## Atlananlar

Atlanan / zincir hatalı / teslim hatalı görev yok.
