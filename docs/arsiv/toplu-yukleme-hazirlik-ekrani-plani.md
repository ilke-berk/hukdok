# Toplu Yükleme — Hazırlık Ekranı Planı (Faz 6)

**Tarih:** 2026-05-18
**Kaynak:** Üretim testinde tespit edilen UX sorunları
**Hedef:** Toplu yüklemede belge türü ve e-posta yapılandırmasının analiz başlamadan önce toplu olarak alınması.

---

## Sorun Tespiti

Üretim testinde gözlemlenen iki UX sorunu:

### Sorun 1 — "Bu ayarları tüm batch için kullan" toggle metni kullanıcı için karmaşık
- **Yer:** [EmailModal.tsx:387-401](../frontend/src/components/email/EmailModal.tsx#L387-L401)
- **Sorun:** Toggle açıklaması teknik dil içeriyor ("batch", "sıradaki N dosyada", "mesaj metinleri her dosya için ayrıca üretilir"). Avukat kullanıcısının zihninde net karşılığı yok.
- **Ek sorun:** Toggle her dosyada görünüyor — sadece ilk dosyada sorulması daha mantıklı (2. dosyadan itibaren karar zaten verildi).

### Sorun 2 — Belge türü seçimi pipeline'a geç giriyor
- **Mevcut akış:** `selectedDocType` her dosya için kullanıcı arayüze geldikten sonra (analiz tamamlandığında) seçiliyor.
- **Sorun:** Bazı belge türlerinin **özel AI prompt'ları** var. Pre-load anında AI bu özel prompt'u kullanamıyor — sadece "genel" promptla çalışıyor → analiz kalitesi düşüyor.
- **İlgili bug:** [toplu-yukleme-incelemesi-2026-05-17.md — Bug #3](./toplu-yukleme-incelemesi-2026-05-17.md) (`belge_turu_kodu` pre-load'da gönderilmiyor).

---

## Tasarım Önerisi: Toplu Yükleme Hazırlık Ekranı

`fileQueue.length > 1` olduğunda, **ilk analiz başlamadan önce** bir hazırlık ekranı (modal veya tam ekran adım) gösterilir. Kullanıcı tüm dosyaların:

1. Belge türünü (her dosya için ayrı, varsayılan "otomatik")
2. E-posta alıcılarını (tüm batch için ortak)
3. Genel ayarları (e-posta gönderilsin mi, tebliğ tarihi vb.)

önceden belirler. Sonra "Analize Başla" tıklanır → pipeline mevcut haliyle çalışır, ama önceden belirlenmiş parametrelerle.

### UI Taslağı

```
┌──────────────────────────────────────────────────────┐
│ 📚 Toplu Yükleme Hazırlığı  ·  5 dosya               │
├──────────────────────────────────────────────────────┤
│                                                       │
│ BELGE TÜRLERİ                                         │
│ ┌─────────────────────────────────────────────┐     │
│ │ Tümüne uygula: [— Otomatik (AI) —      ▼]    │     │
│ └─────────────────────────────────────────────┘     │
│                                                       │
│ ┌─────────────────────────────────────────────┐     │
│ │ 1. dosya_a.pdf       [Otomatik          ▼]   │     │
│ │ 2. tebligat_b.pdf    [Tebligat          ▼]   │     │
│ │ 3. muzekkere_c.udf   [Müzekkere         ▼]   │     │
│ │ 4. dosya_d.pdf       [Otomatik          ▼]   │     │
│ │ 5. karar_e.pdf       [Mahkeme Kararı    ▼]   │     │
│ └─────────────────────────────────────────────┘     │
│                                                       │
│ ───────────────────────────────────────────────────  │
│                                                       │
│ E-POSTA AYARLARI         [✓ E-posta gönder]          │
│ ┌─────────────────────────────────────────────┐     │
│ │ Kime:  [Av. Ahmet ×] [Av. Ayşe ×] [+ Ekle]   │     │
│ │ CC:    [+ Ekle]                              │     │
│ │ Tebliğ Tarihi: [____________]                │     │
│ └─────────────────────────────────────────────┘     │
│                                                       │
│ ☐ Her dosyada e-posta ayarlarını ayrıca onayla       │
│   (kapalıysa modal hiç açılmaz)                      │
│                                                       │
├──────────────────────────────────────────────────────┤
│                       [İptal]   [Analize Başla →]    │
└──────────────────────────────────────────────────────┘
```

### Akış

1. Kullanıcı 2+ dosya seçer → hazırlık ekranı açılır (analiz **henüz başlamaz**).
2. Kullanıcı belge türlerini ve e-posta ayarlarını girer.
3. "Analize Başla" → Index'te `batchDocTypes: Record<fileIndex, docTypeCode>` ve `batchEmailConfig` state'e yazılır.
4. Pipeline aynı şekilde çalışır:
   - `handleAnalyze` ve `preloadNextFile` FormData'ya `batchDocTypes[currentIndex]` ekler.
   - Her dosyaya geçişte `setSelectedDocType(batchDocTypes[i])` çağrılır → AnalysisResults önceden dolu gelir.
   - EmailModal "her dosyada ayrıca onayla" kapalıysa hiç açılmaz; `handleFinalProcess` doğrudan `batchEmailConfig` ile çağrılır.

### Tek Dosya Davranışı (Korunur)

`fileQueue.length === 1` ise hazırlık ekranı **atlanır** — mevcut akış aynen devam eder. Basit kullanım yavaşlatılmaz.

---

## Pipeline Değişiklikleri (Minimum İnvaziv)

### Yeni state

```tsx
type BatchDocType = string; // "" = otomatik
interface BatchPrep {
  docTypes: BatchDocType[];           // fileQueue ile aynı index
  emailConfig: {
    to: Array<{name: string; email: string}>;
    cc: Array<{name: string; email: string}>;
    sendEmail: boolean;
    tebligTarihi?: string;
    confirmPerFile: boolean;          // true = her dosyada modal açılsın
  } | null;
}

const [batchPrep, setBatchPrep] = useState<BatchPrep | null>(null);
const [showBatchPrepScreen, setShowBatchPrepScreen] = useState(false);
```

### Akış noktaları

| Yer | Mevcut | Yeni |
|-----|--------|------|
| Dosya seçimi sonrası | `handleAnalyze` direkt çağrılır | `fileQueue.length > 1` ise `setShowBatchPrepScreen(true)`, değilse mevcut akış |
| `handleAnalyze` FormData | `selectedDocType` | `batchPrep?.docTypes[currentFileIndex] ?? selectedDocType` |
| `preloadNextFile` FormData | (boş) | `batchPrep?.docTypes[nextIndex]` (Bug #3 çözümü) |
| Dosyalar arası geçiş | `setSelectedDocType("")` | `setSelectedDocType(batchPrep?.docTypes[nextIndex] ?? "")` |
| `handleConfirmClick` | EmailModal aç | `batchPrep?.emailConfig && !confirmPerFile` ise modal'ı atla, doğrudan `handleFinalProcess(batchEmailConfig)` |
| Batch sonu reset | `setOutputDirHandle(null)` vb. | + `setBatchPrep(null)` |

### EmailModal değişiklikleri

- "Bu ayarları tüm batch için kullan" toggle'ı **kaldırılabilir** (hazırlık ekranı bu görevi devraldı).
- VEYA: "Her dosyada ayrıca onayla" kapalıyken modal hiç açılmadığı için toggle gerçekten gereksiz hale gelir. Korunacaksa metin sadeleştirilir:
  - Başlık: **"Aynı alıcıları tüm dosyalar için kullan"**
  - Açıklama: *"Sıradaki dosyalarda bu pencere açılmaz."*

---

## Kabul Kriterleri

1. **Tek dosya:** Hazırlık ekranı açılmaz, mevcut akış aynen çalışır.
2. **Çoklu dosya + tümü otomatik:** Hazırlık ekranı açılır, kullanıcı hiçbir şey değiştirmeden "Analize Başla"ya basabilir → mevcut davranış.
3. **Çoklu dosya + özel doctype:** 3. dosyaya "Müzekkere" seçildiyse, o dosya analiz edilirken backend'de Müzekkere prompt'u kullanılır. Pre-load anında da aynı kod gönderilir.
4. **Çoklu dosya + ortak email:** Hazırlık ekranında alıcı seçilirse, EmailModal hiç açılmadan 5 dosya da işlenir.
5. **"Her dosyada ayrıca onayla" açık:** EmailModal her dosyada açılır ama alıcı listesi prefill olur.
6. **Pre-load kalitesi:** Hazırlık ekranında "Tebligat" seçilen dosya için backend log'unda `belge_turu_kodu=TEB` görülür (Bug #3 regresyon testi).

---

## Tahmin & Faz Sıralaması

| Adım | Tahmin |
|------|--------|
| Yeni `BatchPrepScreen.tsx` component | 0.5 gün |
| Index.tsx state + pipeline entegrasyonu | 0.5 gün |
| EmailModal sadeleştirme/toggle kaldırma | 0.25 gün |
| Manuel test (4 senaryo) | 0.25 gün |
| **Toplam** | **~1.5 gün** |

**Bağımlılık:** Faz 1-3 merge edilmiş olmalı (bu plan onların üzerine ekleniyor).
**Deploy önceliği:** Faz 3 sonrası mantıklı — Faz 3'teki batch toggle'ı bu çalışma ile birlikte kaldırılabilir.

---

## Açık Sorular

1. **Belge türü listesi:** Hazırlık ekranındaki dropdown'da hangi türler görünecek? `useConfig` içinde `docTypes` zaten var mı, yoksa AnalysisResults'taki listeden mi türeyecek?
2. **"Tümüne uygula" davranışı:** Sadece "Otomatik" olanları mı override eder, yoksa hepsini mi? (Öneri: hepsini override etsin, kullanıcı sonra tek tek değiştirebilir.)
3. **Ek belgeler (extraAttachments):** Hazırlık ekranında "tüm batch için ortak ek" olur mu, yoksa per-file mı? (Öneri: per-file, hazırlık ekranında yok.)
4. **İptal sonrası:** Hazırlık ekranında "İptal" → `fileQueue` boşaltılır mı, yoksa tek dosya akışına mı düşer? (Öneri: `fileQueue` boşaltılır, kullanıcı baştan başlar.)

Bu sorular implementasyon başlamadan kısaca cevaplanmalı.
