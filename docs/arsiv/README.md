# docs/arsiv — TARİHSEL KAYIT

> **Bu klasör tarihsel kayıttır.** Buradaki plan/rapor/bulgu dosyaları yazıldıkları günün
> fotoğrafıdır ve **GÜNCEL DURUMU YANSITMAZ**. İçlerindeki "şu an şöyle çalışıyor",
> "şu bug açık", "şu dosyada şu satır var" türü ifadeler o tarihte doğruydu; bugün
> yanlış olabilir.
>
> **Güncel mimari: [`docs/mimari/`](../mimari/README.md).**
> **Bu klasörü güncel bilgi kaynağı olarak KULLANMA.**

## Ne zaman buraya bakılır

- "Bu karar neden böyle verilmiş?" — tarihsel gerekçe aramak için.
- Bir bulgunun/regresyonun geçmişte görülüp görülmediğini araştırmak için.

Bir iddiayı buradan alıp güncel kabul etme: **koddan doğrula**. Kod ile arşiv çelişirse
kod haklıdır.

## Aktif (arşiv olmayan) dokümanlar

| Yol | İçerik |
| --- | --- |
| [`docs/plan/`](../plan/) | Yürüyen planlar ve uygulama takibi |
| [`docs/mimari/`](../mimari/README.md) | Yaşayan mimari dokümanları |
| [`docs/kararlar/`](../kararlar/README.md) | Kalıcı mimari kararlar |
| `docs/hukukbot-aktarim/` | Hukukbot export spesifikasyonu — koddan referanslı, arşiv DEĞİL |

## Kod yorumlarından hâlâ eski yolla atıf alan arşiv dosyaları

Aşağıdaki `backend/**` yorumları taşınma öncesi `docs/<ad>.md` yollarını kullanmaya
devam eder (G006'da bilinçli DEĞİŞTİRİLMEDİ — dokunma listesi; düzeltilmeleri G007
kapsamındadır). O yolları `docs/arsiv/<ad>.md` olarak oku:

| Koddaki eski yol | Gerçek yer | Atıf veren |
| --- | --- | --- |
| `docs/otonom-dava-acma-gelistirme-plani-2026-07-24.md` | `docs/arsiv/otonom-dava-acma-gelistirme-plani-2026-07-24.md` | `backend/case_intake_analyzer.py`, `backend/services/case_intake.py` |
| `docs/eml-intake-gelistirme-plani` (kısaltma) | `docs/arsiv/eml-intake-gelistirme-plani-2026-08-01.md` | `backend/routes/case_intake.py` |

Diğer kod/altyapı atıfları (`.github/workflows/ci.yml`, `infra/scripts/net-watchdog.sh`,
`infra/scripts/mem-watch.sh`) G006'da `docs/arsiv/...` olarak güncellendi.

Not: **arşiv dosyalarının kendi içindeki** `docs/<ad>.md` yazımları da taşınma öncesi
yollardır — bu klasördeki komşularını kastederler (`docs/arsiv/<ad>.md` diye oku);
tarihsel içerik bilerek yeniden yazılmadı. (Yalnızca koda giden `](../...)` biçimli
göreli linkler taşınmayla kırıldığı için `](../../...)` yapıldı.)
