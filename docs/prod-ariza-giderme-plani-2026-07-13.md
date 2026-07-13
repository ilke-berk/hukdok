# Prod Arıza Giderme Planı — 2026-07-13

## Arıza Özeti

Kullanıcı, belge onaylama adımında **"SharePoint arşiv yüklemesi başarısız. (Hata: bd039f4b)"** hatası aldı.
Teşhis sonucu üç bağımsız sorun tespit edildi (detaylı log kanıtları SharePoint `02_YEDEK_ARSIV/technical_log_20260713_*.json` dosyalarında):

| # | Sorun | Etki | Durum |
|---|-------|------|-------|
| 1 | Ghostscript/LibreOffice subprocess çıktısı `text=True` ile UTF-8 decode edilirken taramalı PDF'lerde `UnicodeDecodeError` fırlıyor; `UnicodeDecodeError` ⊂ `ValueError` olduğu için `except ValueError: raise` dalı PDF fallback'ini atlıyor → `/confirm` 500 | Taramalı (metin katmansız) PDF'ler onaylanamıyor | Kod düzeltmesi bu planla geliyor |
| 2 | `GEMINI_API_KEY` yeni format (`AQ.` prefix); metin PDF'lerde REST `generateContent` çalışıyor ama taramalı PDF'lerde `genai.upload_file` → legacy discovery endpoint'i anahtarı reddediyor (`API_KEY_INVALID`) | Taramalı PDF'lerin AI analizi başarısız (13 Temmuz'da 15+ belge) | Kullanıcı aksiyonu gerekli |
| 3 | Prod imajı 23 Haziran build'i; container 10 Temmuz'da `--build`'siz yeniden başlatılmış | Son 3 haftanın düzeltmeleri prod'da yok; hata logları docker logs'a düşmüyor | Deploy ile çözülür |

> Not: Hata mesajı yanıltıcıdır — SharePoint erişimi, Graph token, Ghostscript kurulumu, disk ve DB sağlıklı doğrulandı.

---

## Faz 1 — Kod Düzeltmesi: subprocess decode güvenliği

**Dosyalar:** `backend/pdf/pdf_converter.py`, `backend/pdf/format_converter.py`

1. `subprocess.run(..., text=True)` çağrılarına `encoding="utf-8", errors="replace"` eklenir
   (GS/LO çıktısındaki ham baytlar artık istisna değil `�` üretir; hata mesajı yine okunur kalır):
   - `pdf_converter.py` → `_pdf_to_pdfa2b` (Ghostscript)
   - `format_converter.py` → `office_to_pdf` (LibreOffice)
2. Derinlemesine savunma: `convert_to_pdfa2b` içine, bilinçli `except ValueError: raise` dalından **önce**
   `except UnicodeDecodeError` dalı eklenir — decode hatası "desteklenmeyen format" muamelesi görmez,
   PDF'ler için orijinal dosyaya fallback çalışır.
3. Doğrulama: mevcut backend testleri konteynerde koşulur (`pytest`), ayrıca 0xae içeren sahte GS çıktısı
   senaryosu manuel doğrulanır.

**Risk:** Düşük — yalnızca hata yolu davranışı değişir; başarılı dönüşüm yolu aynen kalır.

## Faz 2 — Gemini API Anahtarı (kullanıcı aksiyonu)

1. [Google AI Studio](https://aistudio.google.com/apikey) üzerinden **klasik `AIza...` formatlı** yeni anahtar üretilir
   (yeni `AQ.` formatı, eski `google-generativeai` kütüphanesinin discovery tabanlı upload yoluyla uyumsuz).
2. Prod sunucuda `~/hukdok/.env` içinde `GEMINI_API_KEY` güncellenir.
3. `.env` değişikliği `restart` ile YÜKLENMEZ — `docker compose up -d` (recreate) gerekir.
   (Faz 3 deploy'u zaten recreate içerdiği için deploy ile birleştirilebilir.)
4. Doğrulama: taramalı bir PDF yüklenip AI analizinin özet üretmesi beklenir; ayrıca
   `docker logs hukdok_backend --since 10m 2>&1 | grep -i "API_KEY_INVALID"` boş dönmeli.

**Orta vadeli iyileştirme (ayrı iş):** `google-generativeai` → yeni `google-genai` SDK migrasyonu;
böylece yeni format anahtarlar ve Files API doğal desteklenir.

## Faz 3 — Prod Deploy (mesai dışı)

1. Faz 1 düzeltmesi `main`'e merge edilir.
2. Mesai dışında, prod sunucuda:
   ```bash
   cd ~/hukdok
   # (schema değişikliği yoksa pg_dump şart değil; yine de hızlı yedek önerilir)
   docker exec hukudok-postgres pg_dump -U postgres hukudok > ~/yedek_$(date +%Y%m%d_%H%M).sql
   git pull
   docker compose up -d --build
   ```
3. `docker-compose.override.yml` prod sunucuda BULUNMAMALI (dev kaynak mount'u geri getirir) — kontrol edilir.

## Faz 4 — Deploy Sonrası Doğrulama

1. `docker image inspect hukdok-backend --format '{{.Created}}'` → bugünün tarihi olmalı.
2. Uygulamada uçtan uca test: **taramalı bir PDF** yüklenir → analiz → dava bağlanır → **Onayla ve İşlemi Tamamla** → hata toast'ı çıkmamalı, belge SharePoint `02_YEDEK_ARSIV`'e düşmeli.
3. `docker logs hukdok_backend --since 15m 2>&1 | grep -E "500|ERROR"` temiz olmalı.
4. Yeni imajla `TechnicalLogger` kayıtları artık docker logs'ta da görünür (K10) — ileride teşhis için SharePoint'e gitmek gerekmez.

## Başarı Ölçütleri

- [ ] Taramalı PDF onaylama işlemi 200 dönüyor
- [ ] Taramalı PDF AI analizi özet üretiyor (API_KEY_INVALID yok)
- [ ] Prod imajı güncel (build tarihi = deploy günü)
- [ ] 24 saat içinde `/confirm` 500 tekrarı yok
