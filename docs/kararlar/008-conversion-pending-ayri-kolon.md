# 008 — Dönüşüm durumu ayrı kolonda; gece retry'ı senkron yükler

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul
- **Bağlam:** `/confirm` sırasında PDF/A dönüşümü tüm fallback yollarına rağmen
  başarısız olabilir (bozuk kaynak, GhostScript/LibreOffice timeout'u, sistem meşgul).
  Belgenin kaybolmaması ve daha sonra yeniden denenebilmesi gerekir. Belgenin ayrıca bir
  `upload_status` alanı vardır (işlenmiş kopyanın SharePoint yükleme durumu).
- **Karar:** `CaseDocument` üzerinde **üç yeni kolon**: `conversion_status`,
  `conversion_attempts`, `conversion_spool_path` (`backend/models.py:508-521`).
  Dönüşüm başarısızsa orijinal **kendi uzantısıyla** arşive gider ve kayıt
  `conversion_status='pending'` ile açılır; 02:30 TR'deki gece job'ı
  (`services/conversion_retry.py`) spool'daki orijinalden yeniden dener.

  | Değer | Anlam |
  | --- | --- |
  | `NULL` | normal (dönüşüm gerekmedi ya da tamamlandı) |
  | `'pending'` | gece yeniden denenecek |
  | `'failed'` | denemeler tükendi (`MAX_CONVERSION_ATTEMPTS = 5`); tek nihai ERROR, spool elle kurtarma için saklanır |

- **Gerekçe (kodda "KARAR NOTU" başlığıyla, `models.py:518-521`):** "`upload_status`'a yeni
  değer DEĞİL, ayrı alan — `upload_status` işlenmiş kopyanın SharePoint yükleme durumudur
  ve pending belgede orijinalin yüklemesini izlemeye devam eder (dik boyutlar; belge kartı
  göstergesi ve `idx_case_docs_upload_status` partial index'i bozulmaz)."
  Yani iki durum **ortogonaldir**: "dönüşüm oldu mu" ile "arşive yüklendi mi" aynı eksende
  değildir; tek alana sıkıştırmak ikisini de bozardı.
- **İkinci karar — gece job'ı outbox kullanmaz** (`conversion_retry.py:11-23`): "gece job'ı
  PDF/A'yı `upload_outbox`'a DEĞİL, senkron yükler — outbox'a verilse statü düşürme +
  `stored_filename` güncelleme + hukukbot açılışı outbox worker'ının başarı yoluna sızmak
  zorunda kalırdı (sıkı bağlaşım); SharePoint hıçkırığında bir sonraki gece yeniden denemek
  (dönüşüm dahil) ucuz ve idempotenttir. Uploader'ın kendi 3-B retry'ı zaten kısa
  hıçkırıkları kapatır."
- **Reddedilenler:** *`upload_status`'a `conversion_pending` değeri eklemek* (yukarıdaki
  gerekçe). *Ayrı bir dönüşüm kuyruğu tablosu* — durum belgenin kendi özelliğidir ve
  partial index (`idx_case_docs_conversion_pending`) gece taramasını zaten ucuzlatır.
  *PDF/A'yı upload outbox'a vermek* — sıkı bağlaşım.
- **Sonuçları:** `conversion_status is not None` olan belge hukukbot'a **açılmaz**
  (`services/export_publisher.py:60-61`) — arşivde PDF değil orijinal durduğu için
  hukukbot'un ingest'i düşerdi. Deneme sayacı dönüşümden **önce** commit edilir; zehirli
  dosya sonsuz döngü kurmaz.
- **Test:** `backend/tests/test_faz3_f_conversion_pending.py`
- **İlgili:** [`docs/mimari/belge-isleme-hatti.md`](../mimari/belge-isleme-hatti.md)
