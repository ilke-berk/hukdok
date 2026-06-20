# Toplu Yükleme — Fazlı Düzeltme Planı

**Tarih:** 2026-05-17
**Kaynak rapor:** [toplu-yukleme-incelemesi-2026-05-17.md](./toplu-yukleme-incelemesi-2026-05-17.md)
**Hedef:** 14 bulgunun risk-öncelikli, bağımsız PR'lara bölünmüş şekilde çözülmesi.

---

## Fazlama Mantığı

| Faz | Odak | Risk | PR Boyutu | Test Yükü |
|-----|------|------|-----------|-----------|
| **1** | Veri bütünlüğü (kritik bug fix) | 🔴 → ✅ | Küçük | Manuel + regresyon |
| **2** | State tutarlılığı / teknik borç | 🟡 → ✅ | Küçük | Manuel |
| **3** | Batch-aware UX (EmailModal + klasör) | 🟡 → ✅ | Orta | Manuel |
| **4** | Queue yönetimi (skip, geçersiz dosya uyarısı) | 🟢 → ✅ | Orta | Manuel |
| **5** | Pipeline derinleştirme (opsiyonel performans) | 🟢 | Büyük | Performans testi |

Her faz **bağımsız deploy edilebilir** olacak şekilde ayrıldı. Faz 1 production'a en kısa sürede gitmeli — bug #1 ve #2 veri bütünlüğü riski taşıyor.

---

## 🔴 FAZ 1 — Kritik Veri Bütünlüğü (Acil)

**Hedef:** Yanlış davaya bağlama ve pre-load alan kaybını ortadan kaldır.
**Kapsam:** Bug #1, #2, #3, #9
**Tahmin:** 0.5 gün
**Deploy önceliği:** En yüksek — bir sonraki mesai dışı deploy penceresinde.

### 1.1 — `linkedCase` dosyalar arası reset (Bug #1)

**Dosya:** [Index.tsx:728-755](../frontend/src/pages/Index.tsx#L728-L755)

**Değişiklik:** Sıradaki dosyaya geçerken aşağıdaki satırlar eklenir:

```tsx
setLinkedCase(null);
setCaseSearch("");
setSelectedPartyId(null);
// isTestMode korunmalı — kullanıcı batch boyunca test modunu açık tutabilir
```

**Kabul kriteri:**
- 2 farklı davaya ait 2 dosya yüklendiğinde, 1. dosya bağlandıktan sonra 2. dosyada `linkedCase` boş gelir.
- 2. dosyada AI önerisi varsa öneri toast'ı tetiklenir.

### 1.2 — Pre-load veri yapısı eşitleme (Bug #2)

**Dosya:** [Index.tsx:492-506](../frontend/src/pages/Index.tsx#L492-L506)

**Değişiklik:** `preloadNextFile` içindeki `setNextAnalysisData(...)` bloku, [Index.tsx:342-363](../frontend/src/pages/Index.tsx#L342-L363) yapısıyla birebir eşitlenir. Eklenen alanlar: `muvekkil_adi`, `karsi_taraf`, `suggested_karsi_taraf`, `court`, `suggested_case`, `sonraki_durusma_tarihi`, `sonraki_durusma_saati`.

**Refaktör fırsatı:** Bu mapping iki yerde tekrar ediyor — `mapResultToAnalysisData(resultData, selectedDocType?)` helper'ı çıkarılabilir. Faz 2'ye bırakılabilir; Faz 1'de minimum invaziv değişiklikle eşitlenir.

**Kabul kriteri:**
- Pre-load edilen 2. dosyada `suggested_case` UI'da görünür.
- `court`, `karsi_taraf` AnalysisResults'ta dolu.
- Duruşma tarihi varsa backend'e gönderilir.

### 1.3 — Pre-load'da `belge_turu_kodu` gönderimi (Bug #3)

**Dosya:** [Index.tsx:451-452](../frontend/src/pages/Index.tsx#L451-L452)

**Değişiklik:** Pre-load anında kullanıcı seçimi yok ama bu pipeline'ın yapısal bir kısıtı. Karar gerekiyor:

- **Seçenek A (önerilen):** Pre-load yalnızca AI'ın bulduğu `belge_turu_kodu`'na güvensin (mevcut davranış). Kullanıcı dosyaya geçtiğinde manuel seçim için `selectedDocType` resetlenir. **Değişiklik yok, dokümante et.**
- **Seçenek B:** Pre-load'u kullanıcı sırasıyla doctype seçtikten sonra başlat. Daha güvenli ama pipeline hızını kaybettirir.

**Öneri:** Seçenek A + bug #2 fix'i ile birlikte pre-load'da AI'ın seçtiği doctype UI'a yansır. Kullanıcı yanlışsa düzeltir.

### 1.4 — Pre-loaded dosyada auto-dava-bağlama tetikleme (Bug #9)

**Dosya:** [Index.tsx:738-755](../frontend/src/pages/Index.tsx#L738-L755)

**Değişiklik:** `setAnalysisData(nextAnalysisData)` çağrısından sonra, [Index.tsx:366-407](../frontend/src/pages/Index.tsx#L366-L407) içindeki "FAZ 1: Otomatik Dava Bağlantısı" bloku yardımcı bir fonksiyona çıkarılır:

```tsx
const applyAutoSuggestionFlow = (data: AnalysisData) => {
  // mevcut 366-407 satırları
};
```

Hem `handleAnalyze` hem de pre-loaded geçiş bu helper'ı çağırır.

**Kabul kriteri:**
- Pre-loaded 2. dosyada AI öneri toast'ı görünür.
- `client_parties`/`counter_parties` zenginleştirmesi pre-loaded dosyada da çalışır.

### Faz 1 Test Senaryosu

1. **Farklı dava senaryosu:** Aynı tenant'tan 2 farklı davaya ait 2 PDF yükle. İlkini onayla → ikinci dosyada `linkedCase` boş ve AI önerisi görünür.
2. **Aynı dava senaryosu:** Aynı davaya ait 3 PDF yükle. Hepsi doğru davaya bağlanır (kullanıcı manuel seçer).
3. **Pre-load tetikleme:** 5 dosyalık batch, ilkini yavaş onayla — 2. dosyada `suggested_case` UI'da görünür.
4. **Duruşma tarihi:** Pre-loaded duruşma zaptında `sonraki_durusma_tarihi` ajandaya kaydedilir.

---

## 🟡 FAZ 2 — State Tutarlılığı & Teknik Borç

**Hedef:** Closure race, varsayılan değer tutarsızlıkları, UI sayım hataları.
**Kapsam:** Bug #5, #6, #8
**Tahmin:** 0.5 gün
**Bağımlılık:** Faz 1 merge edildikten sonra başlatılabilir.

### 2.1 — `processedBatch` fonksiyonel setter (Bug #5)

**Dosya:** [Index.tsx:693-696](../frontend/src/pages/Index.tsx#L693-L696)

```tsx
// Önce:
const updatedBatch = [...processedBatch];
updatedBatch.push({ path: "", name: newFilename });
setProcessedBatch(updatedBatch);

// Sonra:
setProcessedBatch(prev => [...prev, { path: "", name: newFilename }]);
```

**Not:** `path` alanı her zaman boş — bu alanın kaldırılması düşünülmeli (sadece `name` tutulabilir). Faz 4'te queue yönetimiyle birlikte ele alınabilir.

### 2.2 — Son dosyada `processedCount` artırma (Bug #6)

**Dosya:** [Index.tsx:756-779](../frontend/src/pages/Index.tsx#L756-L779) ("All files processed!" dalı)

**Değişiklik:** Reset bloğundan ÖNCE bir kez daha `setProcessedCount(prev => prev + 1)` çağır. Reset sonrası `setProcessedCount(0)` zaten var; ama UI son dosya tamamlanırken `10/10` görmeli, sıfırlanmadan önce kısa bir tamamlanma animasyonu için.

**Alternatif:** Reset'i 500ms timeout'a alıp QueueStatus'un "tüm rozetler yeşil" durumunu kullanıcı görür.

### 2.3 — `durum` varsayılan tutarsızlığı (Bug #8)

**Dosya:** [Index.tsx:499](../frontend/src/pages/Index.tsx#L499) ve [Index.tsx:352](../frontend/src/pages/Index.tsx#L352)

**Değişiklik:** Pre-load'da `"X"` yerine `"G"` kullan (handleAnalyze ile aynı). Faz 1.2'deki mapping helper'ı bu sorunu zaten çözer.

### Faz 2 Test Senaryosu

1. 10 dosyalık batch yükle — son dosyada toast "10/10" gösterir.
2. Hızlı ardışık tıklama ile EmailModal'daki `batchCount` doğru gözükür.
3. Pre-loaded dosyada AnalysisResults'taki "Durum" alanı `G` olarak başlar.

---

## 🟡 FAZ 3 — Batch-Aware UX

**Hedef:** Toplu yüklemede tekrarlayan kullanıcı eylemlerini ortadan kaldır.
**Kapsam:** Bug #4, #7, #11, #12
**Tahmin:** 1.5-2 gün
**Bağımlılık:** Faz 1.

### 3.1 — EmailModal batch-level config (Bug #4, #12)

**Dosya:** [EmailModal.tsx](../frontend/src/components/email/EmailModal.tsx), [Index.tsx](../frontend/src/pages/Index.tsx)

**Tasarım:**
- Batch mode tespiti: `fileQueue.length > 1`.
- İlk dosyada EmailModal'ın altında **"Bu ayarları tüm batch için kullan"** toggle'ı.
- Toggle açıksa: `batchEmailConfig` state'i Index'te tutulur, sonraki dosyaların `handleConfirmClick`'i EmailModal'ı atlar ve doğrudan `handleFinalProcess(batchEmailConfig)` çağırır.
- Toggle kapalıysa: mevcut davranış (her dosyada modal açılır).

**State değişikliği:**
```tsx
const [batchEmailConfig, setBatchEmailConfig] = useState<{
  to: string[];
  cc: string[];
  shouldSend: boolean;
  tebligTarihi?: string;
} | null>(null);
```

**Yorumun düzeltilmesi:** [Index.tsx:543](../frontend/src/pages/Index.tsx#L543) yorumu güncellenir: "Batch modda config varsa modal atlanır; yoksa açılır."

**UI:** EmailModal başlığına "Dosya 3/10 — Tüm batch için ayarlar" göstergesi.

**Kabul kriteri:**
- Toggle açıkken 10 dosya tek modal açılışıyla işlenir.
- Toggle kapalıyken her dosyada modal açılır (mevcut davranış).
- Per-recipient mesajlar ve ekler batch-level değil — sadece alıcı listesi ve `shouldSend` paylaşılır. (Tartışılabilir: ekler de paylaşılsın mı? **Öneri: hayır**, ekler genellikle dosyaya özgü.)

### 3.2 — `outputDirHandle` kalıcılığı (Bug #7)

**Dosya:** [Index.tsx:776-778](../frontend/src/pages/Index.tsx#L776-L778)

**Karar gerekiyor:** Mevcut yorum "User wants to re-select for every process" diyor. Bu kasıtlıysa ve kullanıcı tercihi geçerliyse:

- **Seçenek A (önerilen):** Klasör seçimi `directoryStorage`'da kalıcı (zaten öyle). Batch sonrası reset'i KALDIR. Kullanıcı manuel olarak değiştirebilir.
- **Seçenek B:** Settings'e bir "Her batch sonrası klasör seçimini sıfırla" tercih ekle, varsayılan kapalı.

**Öneri:** Seçenek A — kullanıcıya sor. Mevcut davranış memory'de [tenant_model.md] gibi bir notla doğrulanmadıysa yorumdaki niyet anlaşılmış olabilir ama gerçek tercih olmayabilir.

> **Aksiyon:** Kullanıcıya sor — "her batch sonrası klasör seçimini sıfırlamayı kasıtlı olarak mı istiyorsunuz?"

### 3.3 — Toast özetleme (Bug #11)

**Dosya:** [Index.tsx](../frontend/src/pages/Index.tsx) — `handleFinalProcess` içindeki toast çağrıları

**Değişiklik:** Batch mode'da (`isBatchMode === true`) ara toast'ları susturup batch sonunda toplu özet at:

```tsx
// State'e ekle:
const [batchResults, setBatchResults] = useState<{
  successCount: number;
  emailSuccessCount: number;
  errors: string[];
}>({ successCount: 0, emailSuccessCount: 0, errors: [] });
```

- Her dosyada `batchResults` güncellenir, toast atılmaz.
- Son dosyada tek özet:
  > 🎉 10/10 tamamlandı · 📧 9 e-posta gönderildi · ⚠️ 1 hata: dosya_x.pdf

**Korunan toast'lar (batch içinde de gösterilmeli):**
- ❌ Kritik hatalar (SharePoint upload fail, vs.)
- 📅 Duruşma tarihi kaydedildi (önemli kullanıcı bilgisi)

**Filtrelenen toast'lar (batch sonu özetine taşınır):**
- ✅ "Dosya işlendi" (her dosya için)
- 💾 "Dosya kaydedildi"
- 📄 "İşlenmiş PDF indirildi"
- 📂 "Sıradaki dosya hazırlanıyor"

### Faz 3 Test Senaryosu

1. **Batch email config:** 5 dosya, toggle açık → tek modal, 5 farklı alıcı seçilmez. 5 dosya başarıyla işlenir.
2. **Toggle kapalı:** 5 dosya → 5 modal açılır, her birinde alıcı seçilir.
3. **Toast özet:** 10 dosyalık batch → toast sayısı < 15 (kritikler + özet).

---

## 🟢 FAZ 4 — Queue Yönetimi & Kullanıcı Bildirimleri ✅ (2026-05-17)

**Hedef:** Hata durumlarını kullanıcıya açıkça bildir, kuyruktan dosya çıkarma ekle.
**Kapsam:** Bug #10, #13
**Tahmin:** 1 gün
**Bağımlılık:** Faz 1, 2.
**Durum:** Tamamlandı — `mevcut dosyayı atlama (skip)` ileride ele alınacak; minimum viable kapsam uygulandı.

### 4.1 — Geçersiz dosya uyarısı (Bug #13)

**Dosya:** [FileUpload.tsx:42-70](../frontend/src/components/FileUpload.tsx#L42-L70)

**Değişiklik:**
```tsx
const handleDrop = useCallback((e: React.DragEvent) => {
  e.preventDefault();
  setIsDragging(false);

  const files = Array.from(e.dataTransfer.files);
  const validFiles = files.filter(file => isValidFile(file));
  const invalidCount = files.length - validFiles.length;

  if (invalidCount > 0) {
    const invalidNames = files
      .filter(f => !isValidFile(f))
      .map(f => f.name)
      .join(", ");
    toast.warning(
      `${invalidCount} dosya desteklenmeyen formatta atlandı: ${invalidNames}`,
      { duration: 6000 }
    );
  }

  if (validFiles.length === 0) return;

  if (validFiles.length === 1) {
    onFileSelect(validFiles[0]);
  } else {
    onFileSelect(validFiles);
  }
}, [onFileSelect]);
```

Aynı mantık `handleFileInput` için de uygulanır.

**Kabul kriteri:** Drag-drop'a `.exe` ve `.pdf` karışık atıldığında, `.exe` için uyarı gösterilir.

### 4.2 — Kuyruktan dosya çıkarma (Bug #10)

**Dosya:** [QueueStatus.tsx](../frontend/src/components/QueueStatus.tsx), [Index.tsx](../frontend/src/pages/Index.tsx)

**Tasarım:**
- QueueStatus'taki rozet listesi tıklanabilir hale gelir (gelecek dosyalar için, geçmiş için değil).
- Her bekleyen rozetin yanında küçük `X` ikonu.
- Tıklanınca dosya `fileQueue`'dan çıkarılır.

**State değişikliği:**
```tsx
const handleRemoveFromQueue = (index: number) => {
  if (index <= currentFileIndex) return; // geçmişi ve mevcudu silme
  setFileQueue(prev => prev.filter((_, i) => i !== index));
};
```

**QueueStatus prop ekle:**
```tsx
onRemoveFile?: (index: number) => void;
```

**Mevcut dosyayı atlama (skip):**
- Ayrı bir buton: "Bu dosyayı atla → sıradakine geç"
- `handleClearCurrentFileOnly()` fonksiyonu — sadece current'i atlar, queue'yu korur.

**Bu son özellik daha karmaşık; minimum viable olarak sadece "bekleyen dosyaları kaldırma" yeterli.**

### Faz 4 Test Senaryosu

1. 5 dosya yükle, 3. dosyaya geç, 4. ve 5. dosyaları kuyruktan kaldır → toast "2 dosya kuyruktan çıkarıldı".
2. PDF + EXE + DOCX sürükle-bırak → EXE için uyarı, diğerleri kuyruğa alınır.

---

## 🟢 FAZ 5 — Pipeline Derinleştirme ✅ (2026-05-17)

**Hedef:** Pre-load slot'unu artırarak yavaş kullanıcılarda akış hızını koru.
**Kapsam:** Bug #14
**Tahmin:** 1-2 gün
**Bağımlılık:** Faz 1-2-3. Performans testi gerekli.
**Durum:** Uygulandı. FIFO buffer (`MAX_PRELOAD_DEPTH = 2`), sıralı doldurma (concurrent değil — backend AI API rate limit'i için aynı anda en fazla 1 preload + 1 aktif analiz), file-reference ile entry eşleştirme ve queue mutation race koruması. Üretim verisi ile gözlemlenip MAX_PRELOAD_DEPTH ileride ayarlanabilir.

### 5.1 — FIFO buffer ile çoklu pre-load

**State değişikliği:**
```tsx
// Önceki:
const [nextAnalysisData, setNextAnalysisData] = useState<AnalysisData | null>(null);
const [nextProcessId, setNextProcessId] = useState<string | null>(null);

// Sonrası:
type PreloadEntry = { analysisData: AnalysisData; processId: string };
const [preloadBuffer, setPreloadBuffer] = useState<PreloadEntry[]>([]);
const MAX_PRELOAD_DEPTH = 2; // 2 dosya ileriye kadar buffer
```

**Akış:**
- `handleAnalyze` finally'de buffer doluysa daha fazla pre-load tetiklenmez.
- Dosyaya geçince buffer'dan çekilir, yeni pre-load başlar.

**Trade-off:**
- ✅ Yavaş kullanıcıda daha pürüzsüz akış.
- ⚠️ Backend tarafında 2-3 paralel `/process` çağrısı → AI API rate limit riski.
- ⚠️ PROCESS_CACHE TTL 30 dakika → eski entry'ler birikebilir, mevcut [processing.py:34](../backend/routes/processing.py#L34) cleanup mekanizması yeterli olmalı.

**Karar kriteri:** Production logs'tan ortalama batch boyutu ve dosya başına bekleme süresine bakılır. Eğer kullanıcı 1 dosyada >2 dakika harcıyorsa Faz 5 değerli.

---

## Genel Strateji

### Sıralama özeti

```
Bugün ───► FAZ 1 (kritik fix, deploy)
+1 gün ──► FAZ 2 (teknik borç, deploy)
+1 hafta ► FAZ 3 (UX iyileştirme, kullanıcı feedback'iyle)
+2 hafta ► FAZ 4 (queue yönetimi)
İhtiyaca ► FAZ 5 (opsiyonel performans)
```

### Her faz için PR şablonu

- **Branch:** `feat/bulk-upload-faz-{n}-{kısa-konu}`
- **Test:** Yukarıdaki "Faz N Test Senaryosu" başlıkları manuel test edilir.
- **Deploy:** [deploy_method.md] uyarınca mesai dışı SSH + `docker compose up -d --build`.
- **Doc:** Bu plandaki ilgili kutu işaretlenir ([toplu-yukleme-incelemesi-2026-05-17.md](./toplu-yukleme-incelemesi-2026-05-17.md) referansla).

### Regresyon riski yüksek alanlar

1. **`linkedCase` state akışı** — Faz 1.1 ile değişiyor, QuickCaseModal flow'unu da etkileyebilir ([Index.tsx:1115-1143](../frontend/src/pages/Index.tsx#L1115-L1143)). Test: yeni dava açma akışı batch içinde tetiklendiğinde sıradaki dosya hâlâ doğru bağlanıyor mu?
2. **EmailModal reset davranışı** — Faz 3.1 ile değişiyor. Tek dosya akışı bozulmamalı.
3. **PROCESS_CACHE TTL** — Faz 5'te artarsa backend bellek/disk kullanımı izlenmeli.

### Karar bekleyen sorular

1. **Faz 1.3:** Pre-load'da `belge_turu_kodu` davranışı — Seçenek A (mevcut) yeterli mi?
2. **Faz 3.2:** `outputDirHandle` her batch sonrası sıfırlansın mı? (Memory'de doğrulanmadı, kullanıcı tercihi belirsiz.)
3. **Faz 3.1:** EmailModal batch config'de ekler de paylaşılsın mı? (Öneri: hayır.)
4. **Faz 5:** Yapılsın mı? (Production verisine göre karar.)

Bu sorular Faz 1 başlamadan önce kısaca cevaplanmalı; gerisi geliştirme sırasında netleşir.
