# E-Posta Sistemi İyileştirme Planı

## Mevcut Durum (07.05.2026 itibarıyla)

- Mail gönderimi **senkron** hale getirildi — sonuç anında toast olarak gösteriliyor
- Toplu yüklemede **her dosya** için mail modalı açılıyor (önceden ara dosyalar sessizce atlanıyordu)
- `email_sent` / `email_error` DB'ye kaydediliyor

---

## Yapılacaklar

### A) Otomatik Retry
**Dosya:** `backend/email_sender.py` → `send_document_email()`

Mail başarısız olursa 30 saniye bekleyip 1 kez otomatik tekrar dener.
Geçici ağ hatalarını ve Graph API 429 (rate limit) hatalarını çözer.

```python
# send_document_email() içinde response kontrolünden sonra:
if response.status_code != 202:
    time.sleep(30)
    response = requests.post(url, headers=headers, json=email_payload, timeout=60)
```

---

### B) Mail Durumu Göstergesi (UI)

**Dosya:** `backend/routes/documents.py` → `get_case_documents()`

`email_sent` ve `email_error` alanlarını API response'a ekle:

```python
"email_sent": d.email_sent,       # True / False / None
"email_error": d.email_error,     # Hata mesajı (sadece False ise dolu)
```

**Dosya:** `frontend/src/pages/CaseDetails.tsx` → Belge listesi

Her belgede durum ikonu göster:
- ✅ `email_sent = true` → Mail gönderildi
- ❌ `email_sent = false` → Mail başarısız (hover'da hata mesajı)
- ⏸ `email_sent = null` → Mail gönderilmedi / atlandı

---

### C) "Tekrar Gönder" Butonu

**Yeni endpoint:** `POST /api/documents/{doc_id}/resend-email`

```
Body: { "to": ["avukat@ornek.com"], "cc": [] }
```

Belgeniyi yeniden yüklemek gerekmeden mail gönderir.
`email_sent` ve `email_error` DB'de güncellenir.

**Dosya:** `frontend/src/pages/CaseDetails.tsx`

`email_sent = false` olan belgeler için "Tekrar Gönder" butonu göster.
Tıklandığında mevcut mail modal'ını açar, gönderim yapar.

---

## Öncelik Sırası

| Öncelik | Madde | Efor | Etki |
|---------|-------|------|------|
| 1 | B — Mail durumu göstergesi | Orta | Yüksek |
| 2 | C — Tekrar Gönder butonu | Yüksek | Yüksek |
| 3 | A — Otomatik retry | Düşük | Orta |

B + C birlikte yapılırsa en pratik çözüm olur.
