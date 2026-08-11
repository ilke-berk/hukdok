# Yetki Belgesi Özelliği — Uygulama Planı

## Özet

Müvekkil listesi sayfasındaki **Hızlı Bakış (Quick Look)** paneline "Yetki Belgesi Oluştur" butonu eklenecek. Bu butona basıldığında bir modal açılacak; kullanıcı vekalet veren avukatı ve yetkilendirilen avukatları seçecek, gerekli bilgileri tamamlayacak ve fotokopiye/baskıya hazır, yasal formatlı bir belge üretilecek.

---

## Mevcut Durum Analizi

### İlgili Dosyalar
- **`frontend/src/pages/ClientList.tsx`** — Quick Look paneli burada (satır 452–672). Aksiyon butonları satır 477–491'de.
- **`frontend/src/pages/NewClient.tsx`** — Müvekkil kayıt formu; `vekil_avukatlar` alanı noktalı virgülle ayrılmış isimler olarak saklanıyor (örn: `AYSE GUL HANYALOGLU;SERAP TURGAL`).
- **`frontend/src/pages/ClientList.tsx` L24-47** — `Client` arayüzü; `vekil_avukatlar?: string` var ama avukat başına TC/sicil no alanı **yok**.

### Veri Boşluğu (Kritik)

Mevcut `vekil_avukatlar` alanı yalnızca **ad-soyad** tutuyor. Yetki belgesi için her avukat için şunlar lazım:
- T.C. Kimlik No
- Baro Sicil No
- Büro Adresi (genellikle aynı adres)

Bu bilgiler şu an sistemde **saklanmıyor**. Planın en kritik kararı bu boşluğun nasıl doldurulacağıdır.

---

## Veri Boşluğu Çözümü: İki Seçenek

### Seçenek A — Modal'da Manuel Giriş (Hızlı, Basit)
- Her kullanıcı belge oluştururken TC/sicil no alanlarını modal içinde manuel doldurur.
- Girilen veriler **kaydedilmez**, sadece o anki belge için kullanılır.
- Avantaj: Backend değişikliği yok, çok hızlı implemente edilir.
- Dezavantaj: Her seferinde yeniden girilmeli.

### Seçenek B — Avukat Profillerine TC/Sicil No Ekleme (Önerilen)
- `vekil_avukatlar` string formatı şu an: `AYSE GUL;SERAP TURGAL`
- Yeni format: `AYSE GUL|37561611246|18670;SERAP TURGAL|29723258840|24174` (isim|TC|sicil_no)
- Ya da `NewClient.tsx`'teki vekalet bilgileri kartına avukat başına TC/sicil no alanları eklenir.
- Avantaj: Bir kez girilir, hep kullanılır.
- Dezavantaj: Mevcut veri formatı değişir, migration gerekebilir.

**Önerilen Yaklaşım:** Seçenek A ile başla (MVP), Seçenek B sonraya bırak. Modal'da girilen bilgileri `localStorage`'a cache'le (aynı avukat tekrar seçilince otomatik doldurulsun).

---

## Uygulama Adımları

### Adım 1 — `YetkiBelgesiModal` Bileşeni Oluştur
**Dosya:** `frontend/src/components/YetkiBelgesiModal.tsx`

Modal 3 adımlı bir wizard olacak:

#### Adım 1/3 — Tarafları Seç
- Müvekkile ait `vekil_avukatlar` listesi (noktalı virgülle parse edilmiş) gösterilir.
- **"Yetki Veren Avukat"**: Radyo butonu ile tek seçim.
- **"Yetkili Kılınan Avukatlar"**: Checkbox ile çoklu seçim (veren avukat otomatik çıkarılır).
- Yetki veren olarak seçilen avukat, yetkili kılınan listesinde görünmez.

#### Adım 2/3 — Avukat Detaylarını Doldur
- Büro adresi (tüm avukatlar için ortak — müvekkil adresinden ya da manuel giriş).
- Yetki veren avukat için:
  - TC Kimlik No (input)
  - Baro Sicil No (input)
- Her yetkili kılınan avukat için:
  - TC Kimlik No (input)
  - Baro Sicil No (input, opsiyonel)
- `localStorage` cache: Girilen TC/sicil değerleri `avukat_cache_<isim>` key'i altında saklanır, bir sonraki açılışta otomatik doldurulur.

#### Adım 3/3 — Önizleme ve Yazdır
- Belge tam formatıyla önizlenir.
- "Yazdır / PDF'e Aktar" butonu: `window.print()` tetiklenir.
- Yazdırma stilleri için `@media print` CSS kuralı kullanılır (modal dışı her şey gizlenir).

---

### Adım 2 — Belge Şablonu

Örnek belgeden çıkarılan format:

```
YETKİ BELGESİ

YETKİ BELGESİ VEREN AVUKAT:

1. Av. [AD SOYAD]
   ([Büro Adresi] adresinde mukim,
   T.C. Kimlik No: [TC],
   [Sicil No] sicil no'lu,
   Vergi Daire ve No: [TC])

YETKİLİ KILINAN AVUKATLAR:

1. Av. [AD SOYAD]
   (Aynı adreste mukim,
   T.C. Kimlik No: [TC],
   [Sicil No] sicil no'lu)

2. Av. [AD SOYAD]
   (Aynı adreste mukim,
   T.C. Kimlik No: [TC],
   [Sicil No] sicil no'lu)

[... diğer avukatlar]

1136 sayılı Avukatlık Kanunu'nu değiştiren 4667 Sayılı Kanunun
36. maddesi ile 56. maddesine eklenen hüküm uyarınca
vekaletname yerine geçmek üzere işbu yetki belgesi
tarafımdan düzenlenmiştir.

Av. [YETKİ VEREN AVUKAT AD SOYAD]
```

**Not:** Yetki veren avukatın adresi tam adres, yetkili kılınanlar için "Aynı adreste mukim" yazısı kullanılır.

---

### Adım 3 — Quick Look Paneline Buton Ekle

**Dosya:** `frontend/src/pages/ClientList.tsx`

Mevcut aksiyon butonları (satır 477–491):
```tsx
<div className="flex gap-4 w-full">
  <Button ...>Düzenle</Button>
  <Button ...><Gavel /> Davalar</Button>
</div>
```

Değişiklik: Butonların altına yeni bir satır ekle (veya mevcut satırı genişlet):
```tsx
<div className="flex gap-4 w-full">
  <Button ...>Düzenle</Button>
  <Button ...><Gavel /> Davalar</Button>
</div>
{/* Yeni satır */}
{selectedClient.vekil_avukatlar && (
  <Button
    variant="outline"
    className="w-full h-11 ..."
    onClick={() => setYetkiBelgesiOpen(true)}
  >
    <FileText className="w-4 h-4 mr-2" /> Yetki Belgesi
  </Button>
)}
```

Buton sadece `vekil_avukatlar` dolu olan müvekkillerde görünür.

---

### Adım 4 — Yazdırma CSS'i

`frontend/src/index.css`'e eklenecek:

```css
@media print {
  body > * { display: none !important; }
  #yetki-belgesi-print-area { display: block !important; }
}
```

Belge alanı için `id="yetki-belgesi-print-area"` kullanılacak. Alternatif olarak yeni bir tarayıcı sekmesinde `document.write()` ile print tetiklenebilir — bu daha temiz bir çözüm.

---

## Bileşen Yapısı

```
frontend/src/components/
  YetkiBelgesiModal.tsx      ← Yeni bileşen (wizard + belge şablonu + print)

frontend/src/pages/
  ClientList.tsx             ← Buton + modal state eklenir
```

Backend değişikliği **yoktur** — tamamen frontend işlemi.

---

## Kapsam Dışı (Bu Versiyon)

- Avukat TC/sicil bilgilerinin veritabanına kaydedilmesi (Seçenek B)
- PDF dosyası indirme (sadece tarayıcı print dialog'u kullanılır)
- Dijital imza
- Farklı belge dili seçenekleri

---

## Uygulama Sırası

1. `YetkiBelgesiModal.tsx` bileşeni oluştur (wizard UI + belge önizleme + localStorage cache)
2. `ClientList.tsx`'e modal state ve butonu ekle
3. Print CSS'ini `index.css`'e ekle
4. Test: Farklı `vekil_avukatlar` kombinasyonları ile dene
