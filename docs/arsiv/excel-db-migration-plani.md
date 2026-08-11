# Excel → DB Migrasyon Planı: BIRLESIK_SONUC_v5_temiz.xlsx

**Kaynak dosya:** `C:\Users\ilkeb\OneDrive\Masaüstü\BIRLESIK_SONUC_v5_temiz.xlsx`  
**Sheet:** Son Liste (14.334 satır, 21 sütun)  
**Strateji:** DB tamamen temizlenir, sıfırdan import edilir  
**Tarih:** 2026-04-27

---

## 1. Kaynak Veriye Genel Bakış

| Sheet | Satır | Sütun |
|-------|-------|-------|
| Son Liste | 14.334 | 21 |

**Sütunlar:**
`Klasör No.2`, `Müvekkil`, `Karşı Taraf`, `Diğer Davalı`, `Tarafımız`, `Ana Tür`, `Dava Konusu`, `Alt Kırılım`, `Ek Alt Kırılım`, `Büro Özel Türü`, `Mahkemesi`, `Esas Numarası`, `Durum`, `Son Durum`, `Yerel Mahkeme Karar Durumu`, `Dava Tarihi`, `İş Kabul Tarihi`, `Atama Tarihi`, `Dosya İlgilisi`, `Hasar Dosya Numarası`, `Hukuk Numarası`

---

## 2. Alan Eşleşme Tablosu

### 2a. Doğrudan Eşleşen Alanlar

| Excel Kolonu | DB Tablosu / Alanı | Notlar |
|-------------|-------------------|--------|
| Esas Numarası | `cases.esas_no` | |
| Ana Tür | `cases.file_type` | Enum mapping gerekiyor (bkz. §3b) |
| Dava Konusu | `cases.subject` | |
| Alt Kırılım | `cases.sub_type` | |
| Ek Alt Kırılım | `cases.sub_type_extra` | |
| Büro Özel Türü | `cases.bureau_type` | |
| Mahkemesi | `cases.court` | |
| Son Durum | `cases.dosya_son_durumu` | |
| Dava Tarihi | `cases.opening_date` | |
| İş Kabul Tarihi | `cases.acceptance_date` | |
| Dosya İlgilisi | `cases.responsible_lawyer_name` | |
| Müvekkil | `case_parties` (party_type=CLIENT) | `;` ile ayrılmış birden fazla isim olabilir |
| Karşı Taraf | `case_parties` (party_type=COUNTER) | `;` ile ayrılmış birden fazla isim olabilir |
| Diğer Davalı | `case_parties` (party_type=THIRD) | `;` ile ayrılmış birden fazla isim olabilir |

### 2b. Dönüşüm Gereken Alanlar

| Excel Kolonu | DB Alanı | Dönüşüm |
|-------------|---------|---------|
| **Durum** | `cases.status` | `Aktif` → `DERDEST` / `Arşiv` → `MAHZEN` |
| **Tarafımız** | `case_parties.role` | Import sırasında CLIENT tarafın `role` alanına yazılır (bkz. §3d) |
| **Yerel Mahkeme Karar Durumu** | `cases.karar_turu` | Normalize edilir (bkz. §3c) |
| **Klasör No.2** | `cases.klasor_no_2` | Eski sistem numarası — DB'de saklanır, UI'da gizli, **sadece arama** için kullanılır |

### 2c. `tracking_no` — Yeni Sistem Numarası

Import sırasında her dava için mevcut ofis numaralama sistemi (`generateTrackingNumber`) ile **otomatik** yeni bir takip numarası atanır.  
Eski numara (`Klasör No.2`) `klasor_no_2` alanında tutulur — bu geçiş döneminde arama sonuçlarında görünür ama dava kartında gösterilmez.

### 2d. DB'de Olmayan Yeni Alanlar

| Excel Kolonu | Eklenecek DB Alanı | Tür | Örnek Değer |
|-------------|-------------------|-----|-------------|
| Klasör No.2 | `cases.klasor_no_2` | String | `514.002.00` |
| Atama Tarihi | `cases.atama_tarihi` | Date | `2024-03-15` |
| Hasar Dosya Numarası | `cases.hasar_dosya_no` | String | `2022452063233` |
| Hukuk Numarası | `cases.hukuk_no` | String | `AİH68784` |

---

## 3. Mapping Tabloları

### 3a. Durum Mapping

| Excel | Adet | DB `status` |
|-------|------|------------|
| Aktif | 3.010 | `DERDEST` |
| Arşiv | 11.324 | `MAHZEN` |

### 3b. Ana Tür → `file_types` Tablosu

Import öncesi eksik değerler `file_types` tablosuna eklenmelidir:

| Ana Tür | Adet | Mevcut mu? |
|---------|------|-----------|
| Hukuk | 6.748 | kontrol et |
| İcra | 2.329 | kontrol et |
| Tahkim | 2.199 | **ekle** |
| İdare | 2.034 | kontrol et |
| Arabuluculuk | 409 | **ekle** |
| Ceza | 378 | kontrol et |
| Vergi | 94 | **ekle** |
| Danışmanlık | 87 | **ekle** |
| Savcılık | 56 | **ekle** |

### 3c. Yerel Mahkeme Karar Durumu Mapping

| Excel Değeri | DB `karar_turu` |
|-------------|----------------|
| Kabul | `KABUL` |
| Kabul/kısmen | `KISMI_KABUL` |
| Red/esastan | `RED` |
| Red/görev | `RED` |
| Red/husumet | `RED` |
| Red/zamanaşımı | `RED` |
| Red/feragat | `FERAGAT` |
| Anlaşmama | `null` (serbest metin `dosya_son_durumu`'na yazılır) |
| Beraat | `null` (Ceza davası — serbest metin) |
| Derdest | `null` (henüz karar yok) |

### 3d. Tarafımız Değerleri

CLIENT tarafın `role` alanına yazılır:

| Excel Değeri | Adet |
|-------------|------|
| İhbar Olunan | 1.488 |
| Davalı | 509 |
| Müdahil | 368 |
| Davacı | 125 |
| Karşı Taraf | 123 |
| Sanık | 31 |
| Şüpheli | 27 |
| Diğerleri | ~20 |

---

## 4. Adım Adım Uygulama Planı

### Adım 1 — DB Şeması Güncelle (`models.py`)

`cases` tablosuna 4 yeni kolon ekle:

```python
klasor_no_2    = Column(String, nullable=True)  # Eski sistem no — gizli, aranabilir
atama_tarihi   = Column(Date,   nullable=True)  # Atama Tarihi
hasar_dosya_no = Column(String, nullable=True)  # Hasar Dosya Numarası
hukuk_no       = Column(String, nullable=True)  # Hukuk Numarası
```

Alembic migration oluştur ve uygula:

```bash
alembic revision --autogenerate -m "excel_uyum_alanlari"
alembic upgrade head
```

---

### Adım 2 — `file_types` Tablosunu Güncelle

Eksik Ana Tür değerlerini DB'ye ekle: **Tahkim, Arabuluculuk, Vergi, Danışmanlık, Savcılık**  
(Hukuk, İcra, Ceza, İdare yoksa onları da ekle)

---

### Adım 3 — DB'yi Temizle

Import öncesi mevcut dava verisi silinir:

```sql
TRUNCATE cases, case_parties, case_lawyers, case_history, case_documents
  RESTART IDENTITY CASCADE;
```

> ⚠️ Geri alınamaz. Önce yedeği al.

---

### Adım 4 — Import Scripti Yaz (`backend/import_excel_cases.py`)

Script şunları yapmalı:

1. `BIRLESIK_SONUC_v5_temiz.xlsx` → `Son Liste` sheet'ini oku
2. Her satır için:
   - `generateTrackingNumber()` ile yeni `tracking_no` oluştur
   - `Klasör No.2` → `klasor_no_2`
   - `Durum` → `status` mapping (Aktif→DERDEST, Arşiv→MAHZEN)
   - Tarih alanlarını `date` tipine dönüştür (`datetime` veya `string` olabilir)
   - `Müvekkil`, `Karşı Taraf`, `Diğer Davalı`'yı `;`'ye göre böl → `CaseParty` kayıtları
   - `Tarafımız` → CLIENT tarafın `role` alanına yaz
   - `Yerel Mahkeme Karar Durumu` → `karar_turu` mapping
3. Import sonunda özet rapor:
   ```
   ✓ Eklendi:  X kayıt
   ✗ Hatalı:   X kayıt
   ```

---

### Adım 5 — Test Import (100 Satır)

```bash
python backend/import_excel_cases.py --limit 100 --dry-run
```

`--dry-run` ile DB'ye yazmadan logları incele.

---

### Adım 6 — Tam Import

```bash
python backend/import_excel_cases.py
```

---

### Adım 7 — Arama Güncellemesi (Frontend)

`klasor_no_2` alanını arama kapsamına ekle (`get_cases` / `search_cases`), ancak dava kartında **gösterme**.  
Geçiş dönemi bittikten sonra bu alan gizlenmekten çıkarılabilir veya tamamen kaldırılabilir.

---

### Adım 8 — Frontend Yeni Alanlar (isteğe bağlı)

Dava kartında görünür yapılacak alanlar:

| Alan | Etiket |
|------|--------|
| `atama_tarihi` | Atama Tarihi |
| `hasar_dosya_no` | Hasar Dosya No. |
| `hukuk_no` | Hukuk No. |

---

## 5. Riskler & Dikkat Edilecekler

| Risk | Önlem |
|------|-------|
| DB temizleme geri alınamaz | Import öncesi mutlaka yedek al (`pg_dump`) |
| Müvekkil adları serbest metin — `clients` tablosuyla otomatik eşleşme zor | İlk importta `client_id` boş bırakılır, sonradan eşleştirilir |
| Tarih formatları karışık (`datetime` vs `string`) | Script her iki formatı da handle etmeli |
| `Dosya İlgilisi` (avukat adı) `lawyers` tablosundaki kayıtlarla eşleşmeyebilir | İlk importta `responsible_lawyer_name` serbest metin olarak yazılır, `case_lawyers` boş kalır |
| `Ana Tür` değeri `file_types` tablosunda yoksa kayıt eklenemez | Adım 2'de tüm değerler eklenmeli |
