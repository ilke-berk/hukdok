# Mail Gönderilmeme: Nedenler ve Çözümler

> **Bağlam:** Yaklaşık 20 mailden 1'i gönderilemiyor. Kalıcı yapılandırma hataları
> (yanlış kimlik bilgisi, eksik izin) tüm mailleri durdurur — buradaki nedenler yalnızca
> **aralıklı** (intermittent) hatalar için geçerlidir.

---

## 1. Ağ hatası / timeout sırasında retry yapılmıyor ⚠️ (En olası neden)

**Neden:** `email_sender.py:200-205`'teki retry mantığı yalnızca HTTP yanıt kodu `202`
dışında gelirse devreye girer. İlk `requests.post` çağrısı bir exception fırlatırsa
(bağlantı kesilmesi, 60 saniyelik timeout, Graph API uç noktasında geçici erişilemezlik)
doğrudan `except Exception` bloğuna düşülür ve **retry hiç yapılmaz**.

```python
# email_sender.py:200
response = requests.post(url, headers=headers, json=email_payload, timeout=60)

# Bu blok yalnızca yanıt gelirse çalışır; exception'da atlanır:
if response.status_code != 202:
    time.sleep(30)
    response = requests.post(...)  # ikinci deneme

# Exception düşerse buraya gelir, ikinci deneme yok:
except Exception as e:
    return {"success": False, "message": str(e)}
```

**Nasıl anlaşılır:** Logda `"E-posta gönderim hatası: ..."` + `requests.exceptions.Timeout`
veya `ConnectionError` yazar.

**Çözüm:**
```python
for attempt in range(2):
    try:
        response = requests.post(url, headers=headers, json=email_payload, timeout=60)
        if response.status_code == 202:
            break
        if attempt == 0:
            time.sleep(30)
    except requests.exceptions.RequestException as e:
        if attempt == 1:
            raise
        logger.warning(f"⚠️ Bağlantı hatası, 30sn sonra tekrar: {e}")
        time.sleep(30)
```

---

## 2. Graph API 4xx / 5xx — Retry sonrası da başarısız

**Neden:** Mail isteği geçerli bir HTTP yanıtı döner ama `202` dışında bir kod gelir.
Kod 30 saniye bekleyip otomatik tekrar dener (`email_sender.py:202`).
İkinci denemede de başarısız olursa hata döner.

**Sık karşılaşılan kodlar:**

| HTTP Kodu | Neden | Çözüm |
|---|---|---|
| `429 Too Many Requests` | Graph API rate limit | 30sn retry genellikle yeterli; toplu yüklemelerde gönderim aralığını artır |
| `500 / 503` | Microsoft tarafında geçici hata | Birkaç dakika bekle, tekrar dene |

**Nasıl anlaşılır:** Logda `"E-posta gönderilemedi: {status_code} - {hata_detayı}"` yazar.
`email_error` alanı DB'de dolu olur.

**Çözüm — UI tarafı:** ✅ Uygulandı.
- `email_sent=false` (başarısız) → kırmızı "Tekrar Gönder" butonu
- `email_sent=null` (ilk başta atlandı) → gri "E-posta Gönder" butonu

Her iki durumda da EmailModal açılır, `POST /api/documents/{id}/resend-email` çağrılır,
başarıda dava detayı sayfası otomatik yenilenir.

---

## 3. Token alımında geçici ağ hatası

**Neden:** `sharepoint/auth_graph.py`'daki `get_graph_token()` Azure'a OAuth isteği atar.
Bu istek de bir ağ çağrısıdır — geçici bir bağlantı sorunu olursa exception fırlatır ve
`send_document_email` içinde yukarıdaki aynı `except` bloğuna düşer.

Bu madde **kalıcı yapılandırma hatalarını kapsamaz** (yanlış secret / eksik izin →
tüm mailler durur, 1/20 senaryosuyla uyuşmaz).

**Nasıl anlaşılır:** Logda `"E-posta gönderim hatası: ..."` + token isteğine ait
`HTTPError` veya `ConnectionError` yazar.

**Çözüm:** ✅ Uygulandı. `get_graph_token()` içinde 2 deneme yapılıyor:
ilk hata alınırsa 5sn beklenir, ikinci denemede de başarısız olursa `RuntimeError` fırlatılır.

---

## 4. PDF dosyası 70 MB üzeri

**Neden:** Uygulama içi kontrol 70MB olarak ayarlıdır (`email_sender.py` — `MAX_SINGLE_MB = 70`).
Graph API `sendMail` uç noktasının fiziksel limiti 35MB'dır; 35–70MB arası dosyalar için
büyük dosya yükleme oturumu API'si kullanılmalıdır (bkz. kod tarafı çözüm).

**Nasıl anlaşılır:** Logda `"Ana dosya çok büyük: X.XXMB (max: 70MB)"` yazar;
kullanıcı arayüzünde hata bildirimi gösterilir.

**Çözüm — kısa vadeli:** Büyük PDF'leri göndermek yerine SharePoint linki mail gövdesine ekle.

**Çözüm — kod tarafı:** Ek için Graph API'nin
[büyük dosya yükleme oturumu](https://learn.microsoft.com/tr-tr/graph/api/attachment-createuploadsession)
kullanılabilir (100MB'a kadar destekler).

---

## 5. PDF/A dönüşüm hatası — mail kısmına hiç ulaşılamıyor

**Neden:** `processing.py`'daki `/confirm` endpoint'inde önce PDF/A-2b dönüşümü yapılıyor.
Bu adım başarısız olursa endpoint `500` döndürüyor ve email gönderimi hiç başlamıyor.

**Nasıl anlaşılır:** Frontend'de genel "yükleme başarısız" hatası görünür.
Backend logunda `"Processed Upload Error"` + `"PDF/A-2b dönüşümü başarısız"` yazar.

**Çözüm:** `backend/pdf/pdf_converter.py`'daki `convert_to_pdfa2b()` fonksiyonunu incele.
Ghostscript kurulumu eksikse veya dosya bozuksa dönüşüm başarısız olur.

---

## 6. Temp dosyası silinmiş — pre-check başarısız

**Neden:** Teorik bir timing sorunu: PDF/A temp dosyası `_async_cleanup` tarafından silinirse
ve bu silme `_email_pre_check()` çağrısından önce gerçekleşirse, `os.path.exists(email_file_path)`
kontrolü `False` döner.

**Nasıl anlaşılır:** `email_warning: "Dosya bulunamadı"` gelir.

**Neden pratikte yaşanmaz:** İki mimari güvence var:
1. `background_tasks.add_task(_async_cleanup, ...)` satırları kodda email gönderiminden
   **sonra** gelir; cleanup task'ı email tamamlanmadan kayıt bile edilmez.
2. FastAPI `BackgroundTasks` HTTP response döndükten sonra çalışır; email ise response
   dönmeden önce `await run_in_executor` ile senkron olarak tamamlanır.

Not: `_async_cleanup`'taki 30 saniyelik bekleme email'i korumak için değil, `download_id`
indirme linkinin response'tan sonra kullanılabilir kalması içindir.

**Gerçekten tekrarlanıyorsa:** Cleanup dışında başka bir şeyin dosyayı silip silmediğini
kontrol et (antivirus, OS temp cleaner, vb.).

---

## Hızlı Teşhis Rehberi

```
Mail gönderilmedi mi?
│
├─ Backend loguna bak
│   ├─ "Timeout" / "ConnectionError" → retry yok, ağ sorunu (#1)
│   ├─ "429" → Graph rate limit, retry yeterli (#2)
│   ├─ "500/503" → Microsoft geçici hata (#2)
│   ├─ "token" + bağlantı hatası → token alım sorunu (#3)
│   ├─ "35MB" → büyük dosya limiti (#4)
│   └─ "PDF/A-2b başarısız" → dönüşüm hatası (#5)
│
└─ DB'de email_sent = false ise
    → email_error alanına bak, hata mesajı orada
```

---

## Öncelik Sırası (Uygulanması Önerilen Sıra)

| Öncelik | Madde | Efor | Etki |
|---------|-------|------|------|
| 1 | Exception'larda retry eklenmesi (#1) | Düşük | Yüksek |
| 2 | Tekrar Gönder butonu (#2) | Orta | Yüksek |
| 3 | 35MB için büyük dosya desteği (#4) | Yüksek | Düşük |
