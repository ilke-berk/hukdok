# Aktarım Allowlist'i — Belge Türü Kodları

> Kaynak: hukdok referans verisi (DB `doctypes` tablosunun lokal cache kopyası,
> 2026-07-06). Kodlar DB'de `_` ile 14 karaktere pad'lidir; karşılaştırma her zaman
> normalize edilerek yapılır (BULGULAR #7). Aşağıda okunabilirlik için kısa halleri.
>
> **Durum: ONAYLANDI (2026-07-06).** v1 allowlist'i yalnızca aşağıdaki
> **"kesin dahil" 12 koddur**. "Karar bekleyen" iki bölümdeki kalemlerin tümü
> (TAKIPSIZLK-KRR dahil) v1'de HARİÇ tutulacak — ileride eklenirse geçmiş
> belgeler backfill modu (`after_id=0`, belge tablosu taraması) ile toplanır.

## Kesin dahil — Kararlar

| Kod | Ad |
|---|---|
| `GEREKCELI-KRR` | Gerekçeli Karar |
| `ARA-KRR` | Ara Karar |
| `EK-KRR` | Ek Karar |
| `ISTINAF-KRR` | İstinaf Kararı |
| `YARGITAY-KRR` | Yargıtay Kararı |
| `DANISTAY-KRR` | Danıştay Kararı |
| `AYM-KRR` | Anayasa Mahkemesi Kararı |
| `KRR_DZLTM-KRR` | Karar Düzeltme Kararı |
| `EMSAL-KRR` | Emsal Karar |

## Kesin dahil — Bilirkişi raporları

| Kod | Ad |
|---|---|
| `BILIRKISI-RPR` | Bilirkişi Raporu |
| `BLRKSI-RPR-EK` | Bilirkişi Ek Raporu |
| `ATK-RPR` | Adli Tıp Kurumu (ATK) Raporu |

## Karar verildi: HARİÇ — (eski "muhtemelen dahil")

RAG'de karar/rapor araması yapan birinin bulmayı bekleyeceği ama "karar" ve
"bilirkişi raporu" tanımının kenarında kalan türler. **v1'de hariç tutulmasına
karar verildi (2026-07-06):**

| Kod | Ad | Not |
|---|---|---|
| `MALULYT-RPR` | Maluliyet Raporu | Bilirkişi niteliğinde uzman raporu |
| `MALULYT-RPR-EK` | Maluliyet Raporu Eki | |
| `TAZMNT-RPR` | Tazminat Hesap Raporu (Aktüerya) | |
| `TAZMNT-EK-RPR` | Tazminat Ek Raporu (Aktüerya) | |
| `MUTALAA` | Mütalaa (Bilirkişi veya Savcılık) | Karışık nitelik — içinde savcılık mütalaası da var |
| `MSK-KRR` | Mesleki Sorumluluk Kurulu Kararı | Kurul kararı, mahkeme değil |
| `YD-KRR` | Yürütmeyi Durdurma (YD) Kararı | |
| `IHT-TED-KRR` | İhtiyati Tedbir Kararı | |
| `IHTYT-HCZ-KRR` | İhtiyati Haciz Kararı | |
| `TEHIR-ICR-KRR` | Tehir-i İcra Kararı | |

## Karar verildi: HARİÇ — (eski "muhtemelen hariç")

Adında "KRR" geçen ama içerik olarak usul/idari nitelikte, RAG değeri düşük türler.
**v1'de hariç (2026-07-06); TAKIPSIZLK-KRR için de "hariç" kararı verildi:**

| Kod | Ad | Not |
|---|---|---|
| `GOREV-KRR` | Görevsizlik / Yetkisizlik Kararı | Usul kararı |
| `ACILMAMIS-KRR` | Davanın Açılmamış Sayılmasına Karar | Usul |
| `ARA-KRR-RUCU` | Ara Karardan Rücu | Usul |
| `AYIRMA-KRR` | Davaların Ayrılması (Tefrik) | Usul |
| `BIRLESTRM-KRR` | Davaların Birleştirilmesi | Usul |
| `BEKLETICI-MSL` | Bekletici Mesele Kararı | Usul |
| `DEG-IS-KRR` | Değişik İş Kararı | Usul |
| `DILEKCE-RED` | Dilekçenin Reddi Kararı | Usul |
| `FERI-M-KRR` | Feri Müdahillik Kararı | Usul |
| `HAKM-KRR` | Hakim Kararı / Havalesi | Usul |
| `IHBR-KRR` | İhbar Kararı | Usul |
| `IDDIANME-KABL` | İddianamenin Kabulü Kararı | Usul (ceza) |
| `SURE-UZT-KRR` | Süre Uzatım Kararı | Usul |
| `TAKIPSIZLK-KRR` | Takipsizlik Kararı (KYOK) | Ceza — istenirse dahil edilebilir |
| `YETKI-KRR` | Yetki Belgesi / Yetki Kararı | Belge, karar değil |
| `KESINLESME` | Kesinleşme Şerhi | Şerh |
| `ATAMA` | Atama Kararı / Yazısı | İdari |
| `BLRKSI-TUTNK` | Bilirkişi Tutanağı | Tutanak, rapor değil |
| `ATK-EKSIK-EVR` | ATK Eksik Evrak Yazısı | Yazışma |
| `RPR-ITIRZ` | Rapora İtiraz Dilekçesi | Taraf dilekçesi, rapor değil |
| `KRR_DZLTM-TLB` / `KRR_DZLTM-CVB` | Karar Düzeltme Talebi / Cevabı | Taraf dilekçesi |

## Uygulama notu

Allowlist env/config'de **kısa (normalize) kodlarla** tutulur; karşılaştırma
`file_utils.py:264-272`'deki normalize mantığıyla yapılır (pad'li `ARA-KRR_______`,
kısa `ARA-KRR` ve `ARAKRR` hepsi eşleşir). Doctype listesi admin panelinden
değiştirilebilir olduğundan allowlist de koda gömülmez — env değişikliğiyle
güncellenir (prod'da `.env` değişimi `up -d` ile recreate gerektirir).
