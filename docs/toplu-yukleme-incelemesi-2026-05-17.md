# Toplu Yükleme İşleyişi — İnceleme Raporu

**Tarih:** 2026-05-17
**İnceleyen:** Claude (Opus 4.7)
**İncelenen dosyalar:**
- [frontend/src/pages/Index.tsx](../frontend/src/pages/Index.tsx)
- [frontend/src/components/FileUpload.tsx](../frontend/src/components/FileUpload.tsx)
- [frontend/src/components/QueueStatus.tsx](../frontend/src/components/QueueStatus.tsx)
- [frontend/src/components/email/EmailModal.tsx](../frontend/src/components/email/EmailModal.tsx)
- [backend/routes/processing.py](../backend/routes/processing.py)

---

## 🔴 KRİTİK — Veri Kaybı / Yanlış Bağlama Riski

### 1. `linkedCase` dosyalar arasında resetlenmiyor — yanlış davaya bağlanma riski
[Index.tsx:728-755](../frontend/src/pages/Index.tsx#L728-L755) — kuyrukta bir sonraki dosyaya geçerken `setIsValidated`, `setFinalData`, `setSelectedDocType` resetleniyor ama **`linkedCase`, `caseSearch`, `selectedPartyId`** resetlenmiyor.

**Sonuç:**
- 1. dosya Esas No `2024/123` davasına bağlandıysa, 2. dosya başka bir davaya ait olsa bile **sessizce aynı davaya bağlanıyor**.
- AI eşleşme önerisi de devre dışı kalıyor: [Index.tsx:368](../frontend/src/pages/Index.tsx#L368) — `if (suggested && !linkedCase && !isTestMode)` koşulu `linkedCase` dolu olduğu için tetiklenmiyor.
- Yalnızca tüm batch bittiğinde [Index.tsx:773-774](../frontend/src/pages/Index.tsx#L773-L774) resetleniyor.

**Çözüm:** [Index.tsx:734](../frontend/src/pages/Index.tsx#L734) civarında dosyalar arası geçişte aşağıdaki satırlar eklenmeli:
```tsx
setLinkedCase(null);
setCaseSearch("");
setSelectedPartyId(null);
```

---

### 2. Pre-load edilen dosyada AI alanları kayboluyor
[Index.tsx:492-506](../frontend/src/pages/Index.tsx#L492-L506) — `preloadNextFile` içinde kurulan `nextAnalysisData`, `handleAnalyze`'in kurduğu yapıya kıyasla şu alanları **eksik bırakıyor**:

- `suggested_case` → AI dava eşleşmesi kayboluyor
- `court` → Mahkeme bilgisi
- `karsi_taraf`, `suggested_karsi_taraf`
- `muvekkil_adi`
- `sonraki_durusma_tarihi`, `sonraki_durusma_saati` → **duruşma ajandaya yazılamıyor**

**Sonuç:** Pipeline çalıştığında (hızlı senaryo), 2. dosyadan itibaren AI dava önerisi, mahkeme adı ve sonraki duruşma tarihi UI'da görünmüyor; otomatik dava bağlama da çalışmıyor.

**Çözüm:** `preloadNextFile` içindeki `setNextAnalysisData(...)` blokunu [Index.tsx:342-363](../frontend/src/pages/Index.tsx#L342-L363) içindeki `analysisResult` yapısıyla bire bir aynı yapmak.

---

### 3. `belge_turu_kodu` pre-load'da gönderilmiyor
[Index.tsx:451-452](../frontend/src/pages/Index.tsx#L451-L452) — `preloadNextFile` FormData'ya `belge_turu_kodu` koymuyor. Backend'de bu alan analiz kalitesini ve auto-status-update tetiklemesini etkiliyor. Pipeline'da kullanıcı seçimi tamamen yok sayılıyor.

> **Not:** Her dosya için `selectedDocType` resetlendiğinden ([Index.tsx:736](../frontend/src/pages/Index.tsx#L736)) pre-load anında kullanıcının seçimi zaten yok. Yine de modelin ürettiği `belge_turu_kodu` ile pipeline arası geçişlerin tutarsız sonuç vermesi mümkün.

---

## 🟡 ORTA — UX ve Tutarlılık

### 4. EmailModal her dosyada sıfırlanıyor
[EmailModal.tsx:70-82](../frontend/src/components/email/EmailModal.tsx#L70-L82) — modal her açılışta alıcılar, CC, tebliğ tarihi, ekler ve `sendEmail` flag'i tamamen resetleniyor.

**Sonuç:** 10 dosyalık batch'te kullanıcı **10 kez aynı alıcıları seçmek zorunda**. Toplu yükleme amacına ters.

**Öneri:** "Tüm dosyalar için aynı alıcılar" toggle'ı veya batch-level email config.

---

### 5. `processedBatch` closure race — `setState` fonksiyonel olarak kullanılmamış
[Index.tsx:693-696](../frontend/src/pages/Index.tsx#L693-L696):
```tsx
const updatedBatch = [...processedBatch];
updatedBatch.push({ path: "", name: newFilename });
setProcessedBatch(updatedBatch);
```

Eski state üzerinden hesaplanıyor. EmailModal'a geçilen `batchCount={processedBatch.length + 1}` ([Index.tsx:1105](../frontend/src/pages/Index.tsx#L1105)) — hızlı ardışık tıklamalarda yanlış sayı gösterebilir.

**Çözüm:** `setProcessedBatch(prev => [...prev, { path: "", name: newFilename }])`

---

### 6. Son dosyada `processedCount` artırılmıyor
[Index.tsx:732](../frontend/src/pages/Index.tsx#L732) yalnızca "henüz son değilse" dalında çalışıyor. QueueStatus'ta tamamlanma anında "9 tamamlandı / 10 toplam" gözüküp anında "10/10" toast'ı atılıyor — küçük tutarsızlık.

---

### 7. `outputDirHandle` batch sonrası temizleniyor
[Index.tsx:776-778](../frontend/src/pages/Index.tsx#L776-L778) — kullanıcı arka arkaya batch yüklerse her seferde klasör seçmek zorunda.

> Yorumda "User wants to re-select" yazıyor; kasıtlıysa OK, ama toplu yükleme akışında zahmetli.

---

### 8. `durum` varsayılanı tutarsız
- [Index.tsx:352](../frontend/src/pages/Index.tsx#L352) `handleAnalyze`'da `"G"`
- [Index.tsx:499](../frontend/src/pages/Index.tsx#L499) `preloadNextFile`'da `"X"`

Pre-load yolu kullanılan dosyada UI farklı durum kodu gösteriyor.

---

### 9. Otomatik dava bağlama mantığı yalnızca `handleAnalyze` içinde
[Index.tsx:366-407](../frontend/src/pages/Index.tsx#L366-L407) — auto-suggest toast ve `setAnalysisData` zenginleştirme bloku **pre-loaded path'te çalışmıyor**.

**Sonuç:** Kullanıcı pipeline'dan gelen 2. dosyada hiç öneri toastı görmüyor, `client_parties`/`counter_parties` ile zenginleştirme de yapılmıyor.

---

## 🟢 KÜÇÜK — UX İyileştirme Fırsatları

### 10. Kuyruktan dosya çıkarma yok
`fileQueue`'da bir dosya hata verirse veya kullanıcı atlamak isterse "skip" / "remove from queue" butonu yok. Sadece toplu `handleClearFile` var ([Index.tsx:217](../frontend/src/pages/Index.tsx#L217)).

---

### 11. Toast spam
Her dosyada ~5-8 toast atılıyor (info/success/warning karışık). 10 dosyalık batch'te 50+ toast.

**Öneri:** Batch mode'da toplu özet toast'ı (örn. "10/10 tamamlandı, 9 e-posta gönderildi, 1 hata") daha temiz olur.

---

### 12. `handleConfirmClick` "tek/toplu fark etmez" yorumu yanıltıcı
[Index.tsx:543](../frontend/src/pages/Index.tsx#L543) yorumu doğru ama EmailModal her seferinde reset olduğu için kullanıcı için "her dosya için ayrı mail" gibi davranıyor — batch için tek seferlik kurulum opsiyonu olmalı.

---

### 13. Geçersiz dosya uzantısı sessizce yutuluyor
[FileUpload.tsx:42-61](../frontend/src/components/FileUpload.tsx#L42-L61) — drag-drop'ta geçersiz dosyalar filtreleniyor ama kullanıcıya uyarı verilmiyor (`return; // No valid files`). Kullanıcı 5 dosya sürüklediğinde 2'si filtrelendiyse haberi olmaz.

---

### 14. Pipeline tek-dosya derinlikli
`nextAnalysisData` ve `nextProcessId` tek slot. Kullanıcı çok yavaş ilerlerse 3. dosya hazırlanmıyor.

**Öneri:** Küçük FIFO ile 2-3 dosya buffer'lansa toplam akış belirgin hızlanır.

---

## 🚨 En Acil Düzeltme Önerisi

**Bug #1 (`linkedCase` reset)** ile **Bug #2 (pre-load eksik alanlar)** veri bütünlüğü riski taşıyor — kullanıcı farkında olmadan belgeyi yanlış davaya kaydedebilir veya AI önerisi göremeyip eski davayı onaylamış olarak devam edebilir.

### Hızlı Fix #1

[Index.tsx:734](../frontend/src/pages/Index.tsx#L734) civarına ekle:

```tsx
setLinkedCase(null);
setCaseSearch("");
setSelectedPartyId(null);
```

### Hızlı Fix #2

[Index.tsx:492-506](../frontend/src/pages/Index.tsx#L492-L506) blokunu [Index.tsx:342-363](../frontend/src/pages/Index.tsx#L342-L363) ile aynı alanları içerecek şekilde genişlet:

```tsx
setNextAnalysisData({
  tarih: resultData.tarih || "",
  belge_turu_kodu: resultData.belge_turu_kodu || "",
  muvekkil_kodu: resultData.muvekkil_adi || "",
  muvekkil_adi: resultData.muvekkil_adi || "",
  muvekkiller: resultData.muvekkiller || [],
  karsi_taraf: resultData.karsi_taraf || "",
  suggested_karsi_taraf: resultData.suggested_karsi_taraf || "",
  belgede_gecen_isimler: resultData.belgede_gecen_isimler || [],
  esas_no: resultData.esas_no || "",
  durum: resultData.durum || "G",
  ofis_dosya_no: resultData.ofis_dosya_no || "000000000",
  yedek1: "X",
  yedek2: "XX",
  ozet: resultData.ozet || "",
  generated_filename: "",
  hash: resultData.hash || "",
  court: resultData.court || undefined,
  suggested_case: resultData.suggested_case || null,
  sonraki_durusma_tarihi: resultData.sonraki_durusma_tarihi || undefined,
  sonraki_durusma_saati: resultData.sonraki_durusma_saati || undefined,
});
```

Ayrıca pre-loaded dosya gösterilirken (Index.tsx:738-745) otomatik dava bağlama bloku ([Index.tsx:366-407](../frontend/src/pages/Index.tsx#L366-L407)) yeniden çalıştırılmalı — aksi halde kullanıcı pre-load avantajı uğruna AI öneri toast'ını kaybediyor.

---

## Özet Tablo

| # | Bulgu | Önem | Risk |
|---|------|------|------|
| 1 | `linkedCase` dosyalar arası reset edilmiyor | 🔴 Kritik | Yanlış davaya bağlama |
| 2 | Pre-load'da AI alanları eksik | 🔴 Kritik | Veri kaybı, eksik özellikler |
| 3 | `belge_turu_kodu` pre-load'da gönderilmiyor | 🔴 Kritik | Analiz kalitesi düşüşü |
| 4 | EmailModal her dosyada sıfırlanıyor | 🟡 Orta | UX zahmeti |
| 5 | `processedBatch` closure race | 🟡 Orta | Yanlış batch count |
| 6 | Son dosyada `processedCount` artmıyor | 🟡 Orta | UI tutarsızlık |
| 7 | `outputDirHandle` her batch sonrası temizleniyor | 🟡 Orta | UX zahmeti |
| 8 | `durum` varsayılanı tutarsız (G vs X) | 🟡 Orta | UI tutarsızlık |
| 9 | Auto-dava-bağlama pre-load'da çalışmıyor | 🟡 Orta | Özellik kaybı |
| 10 | Kuyruktan dosya çıkarma yok | 🟢 Küçük | UX eksikliği |
| 11 | Toast spam | 🟢 Küçük | Görsel gürültü |
| 12 | "Tek/toplu fark etmez" varsayımı yanıltıcı | 🟢 Küçük | Bug #4 ile bağlantılı |
| 13 | Geçersiz uzantı sessizce filtreleniyor | 🟢 Küçük | Sessiz hata |
| 14 | Pipeline tek-dosya derinlikli | 🟢 Küçük | Performans fırsatı |
