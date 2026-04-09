# 📘 HukuDok v2 Yayına Alım Rehberi

Bu doküman, mevcut sistemin v2'ye yükseltilmesi sırasında izlenen adımları ve mimariyi özetler.

## 🛠️ Neler Değişti?
- **Veritabanı Şeması:** Mevcut PostgreSQL yapısı v2 özellikleri için yeni tablolar ve sütunlar (cari_kod, birth_year, service_type vb.) ile güncellendi. 🐘✅
![alt text](image.png)- **Migrasyon:** Yeni sütunlar (cari_kod, birth_year, service_type vb.) ilk başlatmada otomatik yüklenir.
- **Otomasyon:** `deploy.sh` ile tek komutla güncelleme imkanı eklendi.
- **Frontend Hijyeni:** Console logları prodüksiyonda otomatik olarak gizlendi.

## 🚀 Yayına Alma Adımları
1. Proje ana dizininde `./deploy.sh` komutunu çalıştırın.
2. Çıkan tablodan konteynerlerin "Up" durumda olduğunu kontrol edin.
3. Uygulamayı tarayıcıda açıp login testi yapın.

## ⚡ Sorun Giderme
- **Veritabanı Bağlantı Hatası:** `.env` içindeki `POSTGRES_PASSWORD` değerini ve Docker ağ ayarlarını kontrol edin.
- **Frontend Açılmıyor:** `VITE_API_URL` değişkeninin canlı domain (https) olduğundan emin olun.
- **Redirect URI Hatası:** Azure Portal > Authentication > Redirect URIs kısmında canlı adresiniz ekli olmalıdır.

## 🏆 Sonuç
HukuDok v2 artık daha stabil, daha hızlı ve kurumsal veritabanı yapısıyla yayında!
