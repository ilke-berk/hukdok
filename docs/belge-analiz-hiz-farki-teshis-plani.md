# Belge Analizi Hız Farkı — Teşhis Planı

**Tarih:** 2026-06-23
**Sorun:** Aynı uygulama lokal makinede, prod sunucusundaki halinden belirgin şekilde daha hızlı belge analizi yapıyor. Bu farkın kaynağını bulmamız gerekiyor.

---

## 0. Elenen Şüpheliler

İlk iki büyük olası sebep teyit edildi ve **elendi**:

- ✅ **Çalışma ortamı aynı:** Hem lokal hem prod `docker compose` ile aynı imajı çalıştırıyor. → Native vs Docker CPU farkı, kütüphane sürüm farkı yok.
- ✅ **Model aynı:** İki ortamda `GEMINI_MODEL_NAME` birebir aynı. → Model katmanı (flash vs pro) fark yaratmıyor.

Aynı imaj + aynı model ⇒ aynı belge teorik olarak **aynı kod yolundan** (TEXT vs OCR) geçer. Dolayısıyla fark koddan değil, **donanım veya ağdan** geliyor olmalı.

---

## 1. Kilit Avantaj: Kod Zaten Ölçüm Yapıyor

`backend/analyzer.py` her analizde bir `_benchmark` sözlüğü dolduruyor ve sonuca ekliyor (`analyzer.py:863`). Frontend'e de geliyor; loglarda `⏱️ BENCHMARK:` satırı olarak görünür (`analyzer.py:860`).

```python
benchmark = {
  "hash_calculation": ...,   # dosya hash'i (disk okuma)
  "pdf_analysis": ...,        # is_scanned_pdf — fitz ile TEXT/OCR kararı (CPU)
  "pre_extraction": ...,      # regex + FlashText (CPU)
  "ai_call": ...,             # Gemini çağrısı (+OCR modunda upload & bekleme)
  "total": ...,
}
```

> **"Neresi yavaş?" sorusunun cevabı zaten her yanıtın içinde dönüyor.** Strateji bu ölçümü iki ortamda yan yana koymaya dayanıyor.

---

## 2. Daraltılmış Şüpheli Tablosu

| Kova | Benchmark alanı | Olası sebep |
|------|-----------------|-------------|
| **CPU** | `pdf_analysis`, `pre_extraction` (+ ölçülmeyen UDF & `extract_key_pages`) | Prod VPS'in çekirdeği lokal makineden zayıf. Bu işler `run_in_executor` ile koşan, fitz/regex ağırlıklı CPU-bound işler. |
| **Ağ** | `ai_call` | Prod'un Google API'ye gecikmesi / egress bant genişliği. Özellikle OCR modunda tüm dosya yükleniyor (`analyzer.py:531-533`). |
| **Ölçülmeyen boşluk** | `total` − (alanların toplamı) | Config/prompt kurulumu (`analyzer.py:504-523`) ve UDF dönüşümü hiç ölçülmüyor. `DynamicConfig` prod'da DB/SharePoint'e gidiyorsa burada şişer. |

---

## 3. Belirleyici Deney

**Aynı dosyayı** lokalde ve prod'da analiz edip dönen `_benchmark`'ı yan yana koy. Hangi alan prod'da şişmişse kova belli olur.

### Adımlar
1. **3 belge tipi seç** (her biri farklı kod yolundan geçer):
   - (a) temiz metinli PDF → TEXT modu
   - (b) taranmış / görsel PDF → OCR moduna düşer
   - (c) UDF dosyası → önce PDF'e dönüşür
2. Her belgeyi **hem lokalde hem prod'da** analiz et.
3. Her çalıştırmada `_benchmark` değerlerini kaydet (frontend yanıtı veya `⏱️ BENCHMARK:` log satırı).
4. Loglardaki `MODE: TEXT` / `MODE: OCR` satırını kontrol et: **iki ortamda aynı mı?**
   - Aynı olmalı. Değilse asıl mesele budur (aynı belge prod'da neden OCR'a düşüyor?).

### Karşılaştırma tablosu (her belge için doldur)

| Alan | Lokal (ms) | Prod (ms) | Oran (prod/lokal) |
|------|-----------|-----------|-------------------|
| hash_calculation | | | |
| pdf_analysis | | | |
| pre_extraction | | | |
| ai_call | | | |
| **total** | | | |
| Mode (TEXT/OCR) | | | |

### Yorumlama
- **`ai_call` şişti** → **ağ** sorunu (CPU değil). Prod'dan Google'a gecikmeyi ölç:
  `curl -w "%{time_total}\n" -o /dev/null -s https://generativelanguage.googleapis.com`
- **`pdf_analysis` / `pre_extraction` şişti** → **CPU** sorunu. Prod'da çekirdek ve yük bak:
  `nproc` ve analiz anında `docker stats`.
- **Alanlar normal ama `total` çok büyük** → **ölçülmeyen boşluk** (config/UDF). Bkz. Bölüm 4.

---

## 4. Mevcut Benchmark'ın Kör Noktaları

Kalan şüphelilerin tam da **ölçülmeyen** yerlerde olması talihsiz. Tablo bu haliyle CPU vs ağ ayrımını yapar ama "boşluk" kovasının içini gösteremez. Kesin teşhis için şu timer'lar eklenmeli:

1. **UDF dönüşümü** — `convert_udf_to_pdf` (`analyzer.py:313`)
2. **Sayfa kırpma** — `extract_key_pages` (`analyzer.py:345`)
3. **Config + prompt kurulumu** — `get_lawyers` / `get_system_instruction` arası boşluk (`analyzer.py:504-523`)
4. **OCR upload vs generate ayrımı** — `_gemini_call_with_retry` içinde upload ile generate'i ayır; OCR'daki ağ payını net gösterir.

---

## 5. Kanıtlama

Şüphe izole edilince doğrula:
- **Ağ ise:** prod sunucu lokasyonu / egress'i sorgula; OCR yükleme süresini ölç.
- **CPU ise:** prod konteynerine çekirdek ekle veya CPU limitini kaldır, tek belgeyle yeniden ölç.
- **Boşluk ise:** Bölüm 4'teki timer'ları ekle, `DynamicConfig`'in prod'da her çağrıda DB/SharePoint'e gidip gitmediğini kontrol et.

---

## 6. Prod Forensiği — Bulgular (2026-06-23)

Tarayıcı SSH konsolundan prod sunucusu (`europe-west3-a`, Frankfurt) incelendi.

### Sunucu parmak izi
- **CPU:** 2 vCPU Intel Xeon @ 2.20GHz (paylaşımlı, zayıf — muhtemelen `e2-medium`).
- **RAM:** 3.8 GiB (1.4 kullanımda, swap'ta 377Mi → geçmiş bellek baskısı).
- **Yük:** ölçüm anında 0.19 (boşta).
- **Google Gemini API gecikmesi:** ~60–106 ms toplam, TLS ~50 ms. **Ağ sağlıklı.**

### Gerçek `_benchmark` logları (33 analiz)
| Alan | Tipik | Sonuç |
|------|-------|-------|
| hash_calculation | ~0 ms | ihmal edilebilir |
| pdf_analysis | 8–57 ms | **ihmal edilebilir** |
| pre_extraction | çoğu <30 ms, ara sıra 1.000–6.500 ms sıçrama | genelde küçük, ara sıra baskın |
| **ai_call** | **2.300–8.000 ms (aykırı: 15.900, 39.463)** | **sürenin ~%95'i** |

### Çürütülen / doğrulanan hipotezler
- ❌ **CPU darboğazı ÇÜRÜTÜLDÜ:** PDF + regex işleri prod'un zayıf 2 çekirdeğinde bile ms'ler sürüyor. Ana maliyet değil.
- ❌ **Ağ gecikmesi ÇÜRÜTÜLDÜ:** temel bağlantı ~60 ms.
- ✅ **Darboğaz `ai_call` (Gemini çağrısı).** Yüksek varyans + 15–39 sn aykırı değerler.

### Kritik çerçeveleme
Aynı model + aynı belge için Gemini inference süresi **istemcinin konumundan bağımsızdır**. O hâlde "lokal çok daha hızlı" gerçekse sebep:
1. Lokalde farklı/küçük belgelerle test,
2. Aynı belge prod'da **OCR**, lokalde **TEXT** moduna düşüyor (OCR = upload + Google'ın işlemesini bekleme),
3. Prod **toplu yükleme** sırasında Gemini **429 rate-limit'ine** takılıp retry backoff (10/30/60 sn) ile bekliyor.

15.9 sn ≈ 1 retry (10s + çağrı), 39.5 sn ≈ 2 retry (10s+30s) — (2) veya (3)'e güçlü işaret.

### Log görünürlüğü tuzağı
`TechnicalLogger` (MODE ve retry uyarıları) **docker stdout'a yazmıyor** — RAM buffer'da tutup yalnızca ERROR/CRITICAL'de SharePoint'e yüklüyor (`log_manager.py:216`). Bu yüzden `MODE: TEXT/OCR` ve `geçici hata` satırları `docker compose logs`'ta görünmez. Çözüm: `ai_call` zaten `_benchmark` ile (root logger üzerinden stdout'a) loglanıyor; alt-metrikleri de oraya ekledik (aşağı bkz).

## 7. Eklenen Instrumentation (2026-06-23)

`analyzer.py` `_benchmark`'ına şu alanlar eklendi — `ai_call`'ın içini açar:
- `mode`: `TEXT` / `OCR` / `TEXT->OCR_FALLBACK`
- `upload_ms`: Gemini'ye dosya yükleme (yalnız OCR)
- `wait_active_ms`: `wait_for_files_active` — Google'ın dosyayı işlemesini bekleme
- `generate_ms`: saf inference süresi
- `retry_count` + `retry_wait_ms`: 429/503 retry sayısı ve toplam backoff uykusu
- `udf_conversion`: UDF→PDF dönüşümü (yalnız UDF)
- `page_trim`: `extract_key_pages`
- `prompt_build`: config yükleme + system instruction kurulumu

Bu alanlar stdout'a `⏱️ BENCHMARK:` satırında gelir → `docker compose logs backend | grep BENCHMARK` ile okunur.

### Yorumlama kılavuzu
- `generate_ms` büyük + `retry_count`=0 → saf Gemini inference (lokalde de aynı olmalı; fark belge farkıdır).
- `retry_count`>0, `retry_wait_ms` büyük → **rate-limit** sorunu (toplu yükleme kotayı yiyor).
- `mode`=OCR + büyük `upload_ms`/`wait_active_ms` → belge OCR'a düşüyor; lokalde TEXT'e düşüyorsa fark budur.

## Sonraki Aksiyon

- [ ] **Instrumented `analyzer.py`'ı prod'a deploy et** (mesai dışı: SSH + `docker compose up -d --build backend`).
- [ ] Prod'da 3 belge tipi (temiz PDF / taranmış / UDF) çalıştır, `grep BENCHMARK` ile yeni alanları oku.
- [ ] **Aynı belgeleri lokalde** çalıştır, `generate_ms` ve `mode`'u karşılaştır (Bölüm 3 tablosu).
- [ ] `retry_count`>0 çıkarsa → toplu yükleme eşzamanlılığını / kota tier'ını incele.
- [ ] `mode` ayrışıyorsa → aynı belgenin neden farklı moda düştüğünü araştır.
