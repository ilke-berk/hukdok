# UDF → PDF Dönüşüm Altyapısı Araştırması

## Nasıl Çalışıyor?

Dönüşüm `backend/udf_converter.py` tarafından yapılıyor (704 satır). Ana kütüphane **ReportLab** ile PDF üretiliyor.

### Desteklenen UDF Formatları

- **ZIP tabanlı** → içinde `content.xml` aranıyor (en yaygın)
- **Düz XML** → `<udf>` root elementi

### Desteklenen XML Elementleri

`<paragraph>`, `<table>`, `<image>`, `<header>`, `<footer>`, `<page-break>`, `<field>`, `<space>`

---

## Dönüşüm Pipeline'ı

```
Input (UDF)
    ↓
[Magic byte doğrulama] → ZIP mi? Düz XML mi?
    ↓
[content.xml parse] → defusedxml ile güvenli XML okuma
    ↓
[ReportLab PDF üretimi] → Element handler'lar çalışır
    ↓
[GhostScript] → PDF/A-2b arşiv formatına dönüştürme
    ↓
[Veritabanı + SharePoint] → Arka plan görevi
```

**Çalışma modları:**
- Senkron: `convert_udf_to_pdf(udf_path, output_path)`
- Asenkron: `convert_udf_to_pdf_async()` — ProcessPoolExecutor (max 2 worker)

---

## Format Koruması

| Alan | Durum |
|---|---|
| Font (Türkçe karakter) | DejaVuSerif birincil, Times-Roman fallback |
| Hizalama (sol/sağ/orta/justify) | Tam destekleniyor |
| Bold / italic / underline | HTML inline tag ile |
| Metin rengi | BGR→RGB dönüşüm ile koruluyor |
| Tablo çerçeveleri | 3 mod: grid / box / yok |
| Sayfa boyutu | A4 hardcoded |
| Başlık/alt bilgi offseti | Parametre ile konumlandırılıyor |
| Şekil rengi / highlight | **Desteklenmiyor** |
| Vektörel grafik | **Desteklenmiyor** |
| Gömülü özel font | **Yok** — sadece Times-Roman fallback |

---

## Sorun Yaşanacak Senaryolar

### 1. Font / Türkçe Karakter Kayıpları
`backend/fonts/` klasörü projede mevcut, Dockerfile'da `COPY . .` ile image'a dahil ediliyor — **mevcut deploy'da sorun yok.** Tek risk: `fonts/` klasörü yanlışlıkla `.dockerignore`'a eklenirse veya başka bir ortama manuel deploy yapılırsa DejaVuSerif yüklenemez. Bu durumda Times-Roman'a sessiz fallback yapılır (DEV_MODE dışında hata loglanmaz), Türkçe ğ/ş/ı/ö/ü karakterleri bozulur.

### 2. Karmaşık Tablolar
Hücre başına maksimum 3 paragraf destekleniyor. Bunun üzerinde satır bölmesi yapıyor. Uzun hücreli UYAP tabloları bozulabilir.

### 3. Bozuk Base64 Görseller
Bozuk veya eksik base64 görsel varsa PDF'e `[GÖRSEL]` placeholder yazılıyor, kullanıcıya bildirilmiyor — sessiz geçiliyor.

### 4. Standart Dışı ZIP Yapısı
`content.xml` haricinde farklı entry adı kullanan veya nested ZIP olan UDF'ler şu an hiç işlenemiyor → HTTP 400. Bazı eski UYAP UDF'leri bu kategoriye girebilir.

### 5. Async Zaman Aşımı
- GhostScript: 60 saniye
- LibreOffice: 120 saniye

Büyük belgeler veya yavaş sunucularda arka plan görevi sessizce başarısız olabilir.

### 6. Büyük / Şüpheli Görseller
89M piksel veya 10.000×10.000 üzeri görseller decompression bomb koruması nedeniyle reddediliyor. Büyük taranmış sayfalar içeren belgeler sorun yaşayabilir.

---

## Kritik Gözlem

UYAP'tan indirilen UDF'lerin iç yapısı her zaman standart olmayabiliyor. Şu an yalnızca `content.xml` entry'si olan ZIP'ler destekleniyor. Farklı entry adı, nested ZIP veya şifreli ZIP kullanan UYAP belgeleri **hiç işlenemiyor**.

---

## İlgili Dosyalar

| Dosya | Rol |
|---|---|
| `backend/udf_converter.py` | Ana UDF→PDF dönüşüm motoru |
| `backend/pdf/pdf_converter.py` | PDF/A-2b arşivleme (GhostScript) |
| `backend/file_utils.py` | Magic byte doğrulama, dosya güvenliği |
| `backend/routes/processing.py` | Upload pipeline |
| `backend/routes/documents.py` | Belge yönetimi endpoint'leri |
| `backend/yetki_belgesi_generator.py` | UYAP uyumlu UDF üretimi |
| `backend/test_yetki.udf` | Test UDF dosyası |
