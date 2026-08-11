# Müvekkil Veritabanı Güncelleme Planı

**Kaynak:** `cari_mikro_guncellendi.xlsx` — 1994 kayıt, 20 kolon  
**Tarih:** 2026-04-16  
**Durum:** Kararlar netleşti — uygulamaya hazır

---

## 1. Excel Kolon Analizi

| # | Excel Başlık | Doluluk | Model Alanı | Durum |
|---|---|---|---|---|
| 1 | Vergi No *(sayısal ID, ör. 11196)* | 1994/1994 | `cari_kod` | Mevcut |
| 2 | Vergi No *(isim, ör. ABDULHAMİT SOYSAL)* | 1994/1994 | `name` | Mevcut |
| 3 | Tür *(Şahıs / Kurum)* | 1994/1994 | `client_type` | Mevcut |
| 4 | e-Posta Adresi | 1186/1994 | `email` | Mevcut |
| 5 | Cep Telefonu | 1392/1994 | `mobile_phone` | Mevcut |
| 6 | Telefon | 192/1994 | `phone` | Mevcut |
| 7 | Adres | 1514/1994 | `address` | Mevcut |
| 8 | İl | 1864/1994 | `il` | **Eklenecek** |
| 9 | TC / Vergi No | 1216/1994 | `tc_no` | Mevcut |
| 10 | Sektörü | 1190/1994 | `sektor` | **Eklenecek** |
| 11 | Grup *(tıp branşı vb.)* | 1214/1994 | `specialty` | Mevcut |
| 12 | Özel Kod/Ortaklık No *(Doktor, Bireysel…)* | 1976/1994 | `category` | Mevcut |
| 13 | YEVMİYE NO | 1666/1994 | `yevmiye_no` | **Eklenecek** |
| 14 | NOTERLİK | 1666/1994 | `noterlik` | **Eklenecek** |
| 15 | VERİLİŞ TARİHİ (VEKALET) | 1666/1994 | `vekaletname_tarihi` | **Eklenecek** |
| 16 | VEKİL AVUKATLAR | 1666/1994 | `vekil_avukatlar` | **Eklenecek** |
| 17 | GEÇERLİLİK TAR. | 147/1994 | `gecerlilik_tarihi` | **Eklenecek** |
| 18 | VEKALET NO | 0/1994 | `vekalet_no` | **Eklenecek** |
| 19 | BÜRO VEKALET NO | 1581/1994 | `buro_vekalet_no` | **Eklenecek** |
| 20 | VEKALET AÇIKLAMALAR | 1400/1994 | ~~`vekalet_aciklamasi`~~ | **Kapsam dışı — import edilmeyecek** |

> **Not:** Col 16 (VEKİL AVUKATLAR) iki farklı format içeriyor:
> - Uzun format: `Ayse Acar Yucel ( T.C. Kimlik No: 18188289308)\nAyse Gul Hanyaloglu ( T.C. Kimlik No: ...)`
> - Kısa format: `AYŞE GÜL HANYALOĞLU;TUGÇE ÜNGÖR YANIK`
>
> **Karar:** Her zaman **kısa format** saklanacak — `AD SOYAD;AD SOYAD`.
> Import scripti uzun formatı normalize eder: her satırdan parantez öncesini alır, TC numarasını atar, noktalı virgülle birleştirir.
>
> ```python
> # Örnek normalize fonksiyonu:
> import re
> def normalize_vekil(raw: str) -> str:
>     if not raw:
>         return None
>     # Zaten kısa format ise (satır başına göre ayırt et)
>     if "\n" not in raw and "T.C." not in raw:
>         return raw.strip()
>     # Uzun format: her satır "Ad Soyad ( T.C. Kimlik No: 12345678901)"
>     names = []
>     for line in raw.split("\n"):
>         line = line.strip()
>         if not line:
>             continue
>         name = re.sub(r"\s*\(.*?\)\s*", "", line).strip()
>         if name:
>             names.append(name.upper())
>     return ";".join(names)
> ```
>
> **Not:** Avukat TC numaraları ilerleyen aşamada ayrıca sisteme girilecek, şimdilik sadece isimler saklanıyor.

---

## 2. Yeni Client Model Şeması

```python
class Client(Base):
    __tablename__ = "clients"

    # --- Mevcut alanlar (değişmez) ---
    id              = Column(Integer, primary_key=True)
    name            = Column(String, unique=True, index=True, nullable=False)  # Col 2
    cari_kod        = Column(String, nullable=True)                            # Col 1
    client_type     = Column(String, nullable=True)   # "Individual" | "Corporate"  # Col 3
    email           = Column(String, nullable=True)                            # Col 4
    mobile_phone    = Column(String, nullable=True)                            # Col 5
    phone           = Column(String, nullable=True)                            # Col 6
    address         = Column(String, nullable=True)                            # Col 7
    tc_no           = Column(String, nullable=True)                            # Col 9
    specialty       = Column(String, nullable=True)   # Grup                  # Col 11
    category        = Column(String, nullable=True)   # Özel Kod              # Col 12
    active          = Column(Boolean, default=True)
    notes           = Column(String, nullable=True)
    source_ids      = Column(String, nullable=True)
    contact_type    = Column(String, default="Client")
    birth_year      = Column(Integer, nullable=True)
    gender          = Column(String, nullable=True)
    updated_at      = Column(DateTime(timezone=True), ...)

    # --- YENİ ALANLAR ---
    il                  = Column(String, nullable=True)   # Col 8  - İl / Şehir
    sektor              = Column(String, nullable=True)   # Col 10 - Sektörü
    yevmiye_no          = Column(String, nullable=True)   # Col 13 - Yevmiye No
    noterlik            = Column(String, nullable=True)   # Col 14 - Noterlik adı
    vekaletname_tarihi  = Column(Date,   nullable=True)   # Col 15 - Veriliş tarihi
    vekil_avukatlar     = Column(Text,   nullable=True)   # Col 16 - Vekil avukatlar (ham metin)
    gecerlilik_tarihi   = Column(Date,   nullable=True)   # Col 17 - Geçerlilik tarihi
    vekalet_no          = Column(String, nullable=True)   # Col 18 - Vekalet No
    buro_vekalet_no     = Column(String, nullable=True)   # Col 19 - Büro Vekalet No
    # Col 20 (VEKALET AÇIKLAMALAR) — kapsam dışı bırakıldı
```

---

## 3. Uygulama Adımları

### Adım 1 — `backend/models.py`
- `Client` modeline 10 yeni alan ekle (yukarıdaki şema)

### Adım 2 — `backend/schemas.py`
- `ClientBase`, `ClientCreate`, `ClientUpdate`, `ClientOut` şemalarına yeni alanlar ekle

### Adım 3 — Alembic Migration
```bash
alembic revision --autogenerate -m "add_client_fields_from_excel"
alembic upgrade head
```

### Adım 4 — `backend/import_clients.py` (yeni script)
Görevler:
- Mevcut tüm `clients` tablosunu sil (truncate), ardından taze import yap
- Excel'i oku (openpyxl), 1994 satırı INSERT et
- Tarih alanlarını `DD.MM.YYYY` formatından `Date`'e çevir
- `client_type` dönüşümü: `"Şahıs"` → `"Individual"`, `"Kurum"` → `"Corporate"`
- `vekil_avukatlar` ham metin olarak saklanır, `lawyers` tablosuyla ilişkilendirilmez
- Log: toplam kayıt sayısı, hata varsa satır numarasıyla birlikte

Çalıştırma:
```bash
python backend/import_clients.py --file "cari_mikro_guncellendi.xlsx"
```

### Adım 5 — Backend Route (`backend/routes/admin.py` veya `clients.py`)

| Method | Endpoint | Açıklama |
|---|---|---|
| GET | `/clients` | Liste + arama + filtre |
| GET | `/clients/{id}` | Tek müvekkil detayı |
| POST | `/clients` | Yeni müvekkil |
| PUT | `/clients/{id}` | Güncelle |
| DELETE | `/clients/{id}` | Sil (soft delete) |
| POST | `/clients/import` | Excel import (multipart) |

**Filtre parametreleri:** `q` (isim arama), `client_type`, `il`, `category`, `active`

### Adım 6 — Frontend

**Yeni sayfa:** `frontend/src/pages/Clients.tsx`

Bileşenler:
- `ClientList` — tablo görünümü, sütunlar: Ad, Tür, İl, Kategori, Büro Vekalet No, Veriliş Tarihi
- `ClientDetailModal` — tüm alanları gösteren detay/düzenleme modalı, 3 sekme:
  - **Genel:** Ad, Tür, TC/VN, e-posta, telefon, adres, il
  - **Sektör:** Sektörü, Grup/Uzmanlık, Özel Kod
  - **Vekalet:** Yevmiye No, Noterlik, Veriliş Tarihi, Geçerlilik, Vekalet No, Büro Vekalet No, Vekil Avukatlar, Açıklamalar
- `ClientImportButton` — Excel yükleme + ilerleme göstergesi

**Rota:** `/clients` → App.tsx'e eklenir

---

## 4. Veri Notları

| Konu | Detay |
|---|---|
| Toplam kayıt | 1994 |
| Tür dağılımı | Şahıs + Kurum |
| Vekalet No | Tüm satırlar boş (Col 18) — alan açık kalacak |
| Büro Vekalet No | 1581/1994 dolu |
| Geçerlilik Tarihi | Sadece 147/1994 dolu |
| Import stratejisi | Truncate + fresh insert (upsert değil, tablo önce temizlenir) |

---

## 5. Dosya Etki Listesi

```
backend/
  models.py               ← Client modeline 10 alan ekle
  schemas.py              ← Client şemalarını güncelle
  import_clients.py       ← YENİ: Excel import scripti
  routes/
    clients.py            ← YENİ (veya admin.py güncelle)
  alembic/versions/
    xxxx_add_client_fields.py  ← YENİ migration

frontend/src/
  pages/
    Clients.tsx           ← YENİ sayfa
  components/
    ClientDetailModal.tsx ← YENİ modal
    ClientImportButton.tsx← YENİ buton
  App.tsx                 ← Route ekle
```

---

## 6. Kararlar

| Soru | Karar |
|---|---|
| `client_type` dili | **İngilizce** — `"Individual"` / `"Corporate"` |
| Import stratejisi | **Truncate + fresh insert** — mevcut tüm müvekkiller silinir, Excel'den yeniden yazılır |
| Vekil avukatlar | **Ham metin** — `lawyers` tablosuyla ilişkilendirilmez |
| Navigasyon | **Zaten mevcut** — Header'da "Müvekkiller" butonu var, `/clients` rotası çalışıyor |

---

## 7. Mevcut Frontend Durumu

`frontend/src/pages/ClientList.tsx` **tam işlevsel** bir sayfa:

- Sol panel: filtreleme (kayıt türü, kategori, şehir, tıbbi branş)
- Orta: sayfalanmış liste (ad, iletişim, adres)
- Sağ: "Hızlı Bakış" slide-over paneli

**Şu an gösterilen alanlar (Quick View):**
TC No, Cari Hesap Kodu, Sabit Telefon, Cep Telefonu, E-posta, Adres, Notlar

**Şehir filtresi şu an:** `address` alanının tamamını kullanıyor — `il` alanı gelince bu düzeltilecek.

**Eksikler (yeni alanlar eklendikten sonra yapılacaklar):**

| Bileşen | Değişiklik |
|---|---|
| `Client` arayüzü (satır 24-37) | 10 yeni alan eklenecek |
| Şehir filtresi | `address` → `il` alanına çekilecek |
| Quick View paneli | Vekalet bilgileri bölümü eklenecek (noterlik, tarih, büro vekalet no, vekil avukatlar) |
| `NewClient.tsx` | Yeni alanlar için form alanları eklenecek |
| `useClients` hook | API response'da yeni alanlar otomatik gelecek |

---

## 8. Açık Soru — YOK

Tüm kararlar netleşti. Uygulamaya başlanabilir.
