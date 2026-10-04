# docs/plan — yürüyen planlar

Burada **hâlâ yürüyen** planlar ve uygulama takibi durur. Bir plan bittiğinde dosya
[`docs/arsiv/`](../arsiv/README.md) altına taşınır.

| Dosya | Ne işe yarar |
| --- | --- |
| [`lexis-raporu-plani-2026-10-03.md`](lexis-raporu-plani-2026-10-03.md) | **Onay bekliyor.** Lexis medikolegal rapor modülü: emsal külliyatı (3.260 rapor → okuyucu + Gemini çıkarımı → JSONL → yeni tablolar) + "Araçlar › Lexis Raporu" taslak üretimi (Word). Pilot paket ve kart doluluk ölçümü §1, kararlar §2, görev bölümlemesi §7 (G258-G270; kuyruğa henüz yazılmadı). **03.10 yön değişikliği:** araç ayrı depoda (`..\lexis-rapor`) gelişiyor, güncel uygulama planı oradaki `PLAN.md`. **04.10:** `/lexis` arayüz önizlemesi örnek veriyle HukuDok frontend'inde (§10; yalnız yönetici görür) |
| [`bagimlilik-majorlar-plani-2026-10-01.md`](bagimlilik-majorlar-plani-2026-10-01.md) | **Gece kuyruğunda (G243-G247).** reportlab 4.5.1 → 5, python 3.13, postgres 17 provası + insan adımı geçiş runbook'u, node 26 (LTS sonrası) |
| [`prod-deploy-29-performans-turu-2026-09-14.md`](prod-deploy-29-performans-turu-2026-09-14.md) | **Koşu bekliyor (mesai dışı, kullanıcı kararı).** Deploy #29: c184c9a → main (13.09 bildirim + G182–G197 performans turu + CI protokolü); CI kapısı, doğrulama, `VACUUM FULL` (case_history 15,7× şişik), önce/sonra `perf_olcum` ölçümü, geri dönüş |
| [`veri-teslim-otomasyonu-plani-2026-09-03.md`](veri-teslim-otomasyonu-plani-2026-09-03.md) | **Kod tamam (G107–G114 main'de), kapanış prod kurulumunu bekliyor.** Veri ekibinin teslim paketleri SharePoint klasöründen kendiliğinden alınır, kuru koşu + kapı + 04:00 gece uygulaması, cevap paketi geri yüklenir; ikinci faz sayfaları (Düzeltme_Logu, Silinen_Föyler/Kapsam_Dışı, DEGER_HAVUZLARI) okunuyor. Açık kalanlar §8 (tara ucu, kapsam rozeti, insan adımları). Yaşayan doküman: [`docs/mimari/veri-teslim-hatti.md`](../mimari/veri-teslim-hatti.md) |
| [`temizlik-ve-yapisal-saglik-plani-2026-08-11.md`](temizlik-ve-yapisal-saglik-plani-2026-08-11.md) | **Onay bekliyor.** Temizlik/DB/sorgu/ölçek planı — 25 ajanlı keşif + denetim panelinin ürünü. Kapsam dışı bırakılanlar §9'da, taslakta düzeltilen 10 hata §10'da |
| [`guvenilirlik-sertlestirme-uygulama-takibi.md`](guvenilirlik-sertlestirme-uygulama-takibi.md) | Sertleştirme paketlerinin tek doğruluk kaynağı (durum tablosu) |
| [`guvenilirlik-sertlestirme-plani-2026-08-04.md`](guvenilirlik-sertlestirme-plani-2026-08-04.md) | Ana plan — faz ve madde numaralarının tanımı (KAPANDI 2026-08-11) |

Gece koşusunun kuyruğu bu klasörde değil, [`gorevler/`](../../gorevler/) altındadır.
