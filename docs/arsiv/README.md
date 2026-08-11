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

## Alt dizinler

| Yol | İçerik |
| --- | --- |
| [`gorevler/`](gorevler/README.md) | Kapanmış gece kuyruğu görev dosyaları (G001–G025) — tanım + oturum raporu. Aynı şerh geçerli: tarihseldir. |

## Aktif (arşiv olmayan) dokümanlar

| Yol | İçerik |
| --- | --- |
| [`docs/plan/`](../plan/) | Yürüyen planlar ve uygulama takibi |
| [`docs/mimari/`](../mimari/README.md) | Yaşayan mimari dokümanları |
| [`docs/kararlar/`](../kararlar/README.md) | Kalıcı mimari kararlar |
| `docs/hukukbot-aktarim/` | Hukukbot export spesifikasyonu — koddan referanslı, arşiv DEĞİL |

## Koddan bu klasöre atıflar

Kod ve altyapı dosyalarındaki arşiv atıfları `docs/arsiv/<ad>.md` biçimindedir:
`.github/workflows/ci.yml`, `infra/scripts/net-watchdog.sh`, `infra/scripts/mem-watch.sh`
G006'da; kalan üç `backend/**` yorumu (`case_intake_analyzer.py`, `services/case_intake.py`,
`routes/case_intake.py`) G009'da güncellendi. Taşınma öncesi düz `docs/<ad>.md` yazımı
kod tarafında kalmadı.

Not: **arşiv dosyalarının kendi içindeki** `docs/<ad>.md` yazımları taşınma öncesi
yollardır — bu klasördeki komşularını kastederler (`docs/arsiv/<ad>.md` diye oku);
tarihsel içerik bilerek yeniden yazılmadı. (Yalnızca koda giden `](../...)` biçimli
göreli linkler taşınmayla kırıldığı için `](../../...)` yapıldı.)
