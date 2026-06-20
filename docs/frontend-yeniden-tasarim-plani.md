# Frontend Yeniden Tasarım — Aşamalı Migration Planı

**Tarih:** 2026-05-20
**Kaynak:** `design_handoff_hukdok/` — Yeni UI/UX tasarım paketi
**Hedef:** Mevcut React + Vite + Tailwind frontend'inin tasarım dilini, yeni "klasik avukatlık vakarı" kimliğine aşamalı olarak taşımak.
**Strateji:** Tek seferde değil, faz-faz. Her faz kendi commit'i, mümkünse PR'ı olur. Eski kod **en son** silinir.
**Kurtarma noktası:** `frontend-pre-redesign-2026-05-20` git tag'i (Faz 0'dan önceki son hal).

---

## Genel Strateji

### Neden aşamalı?
- Tek seferlik değişim 22 ekranı, font sistemini, navigasyon paradigmasını, default temayı, marka rengini aynı anda etkiler — kullanıcı için şok edici, geliştirici için debug imkansız hale gelir.
- Aşamalı geçişte her PR kendi başına gözle test edilebilir, sorun çıkarsa o faz geri alınır.
- Production canlı kullanımdayken yan yana iki tasarımı taşımak yerine, **alttan üste** önce token'lar, sonra shell, sonra sayfalar değişir.

### Coğrafi kapsam
- **Dahil:** `frontend/` klasörü (React + Vite + Tailwind production kodu) — sadece **görsel/tasarım katmanı**
- **Hariç:** `test_env/` (ayrı test ortamı, dokunulmaz)
- **Hariç:** Backend (FastAPI), veritabanı, API endpoint'leri, auth (MSAL) — **hiçbiri değişmiyor**
- **Hariç:** Yeni özellik / iş mantığı — sadece mevcut özelliklerin görünümü yenileniyor

### Dashboard yaklaşımı (rol sistemsiz)
Yeni tasarımda iki ayrı dashboard var (Avukat / İdari), ama backend'de rol kolonu açılmıyor. Bunun yerine:
- Kullanıcı **frontend'de bir toggle** ile "Avukat görünümü" veya "İdari görünümü" seçer
- Tercih `localStorage`'da saklanır (`hukdok.dashboard.view = 'avukat' | 'idari'`)
- Default değer: `'avukat'` (büronun ana kullanıcı tipi)
- Toggle nereye konacak: User card (sidebar alt) veya Topbar'da görünüm seçici
- API çağrıları aynı endpoint'lere gider — frontend hangi widget'ları göstereceğini kendisi karar verir

### Eski kod silme politikası
Her faz yeni komponenti **mevcut komponentin yanında** oluşturur (örneğin `Header.tsx` dururken `Shell.tsx` eklenir). Sayfa migrate edildikçe eski referanslar düşer. **Faz 12'de** kullanılmayan eski dosyalar topluca silinir. Bu sayede:
- Her aşamada uygulama çalışır halde kalır
- Eski/yeni karşılaştırılabilir
- Bir faz başarısızsa o faz revert edilir, gerisi etkilenmez

### Commit / branch politikası
- Her faz `main`'e direkt commit edilir (mevcut iş akışı bu — feature branch yok)
- Her commit anlamlı, geri alınabilir bir bütündür
- Migrasyon sırasında çalışmayan ara durumlar **commit edilmez**
- Major faz başlarında bir tag atılır (`frontend-redesign-faz-N-baslangic`)

### Test stratejisi
- Her faz sonunda **gözle test** (Chrome + Edge, light + dark, sidebar açık/kapalı)
- Yeni rol sisteminden sonra her iki rolün UI'ı ayrı test edilir
- Otomatik test yok (mevcut projede frontend test altyapısı yok), regression manuel

---

## Tasarım Dilinin Özeti

| Konu | Mevcut | Yeni |
|---|---|---|
| Marka rengi | Lacivert `#1a2942` | Burgundy `#6D2434` (dark'ta `#b8404c`) |
| Default tema | Light | **Dark** (light alternatif kalır) |
| Navigasyon | Üst header'da nav butonları | **248px sol sidebar** (collapsible, 240ms anim) |
| Topbar | Yok (Header.tsx top-nav rolü görüyor) | **64px sabit topbar** (page title, kısayollar) |
| Dashboard | Tek genel dashboard | **İki ayrı dashboard** (Avukat / İdari) |
| Fontlar | Inter | **Fraunces serif** (display) + Inter (body) + **JetBrains Mono** (eyebrow, metadata, kbd) |
| Border radius | Genel olarak 4-8px | **2-4px** (hairline-friendly, klasik) |
| Karakter | Modern minimal | **Klasik avukatlık vakarı** — Fraunces başlıklar, ALLCAPS Mono eyebrow'lar, hairline ayraçlar |

---

## Faz 0 — Hazırlık ✅ TAMAMLANDI

- [x] Mevcut state GitHub'a push edildi (commit `0512bc5`)
- [x] `frontend-pre-redesign-2026-05-20` tag'i atıldı (rollback noktası)
- [x] `design_handoff_hukdok/` paketi yerel diskte, README okundu
- [x] Bu plan dokümanı oluşturuldu

**Çıktı:** Her şey yedekli, başlamaya hazır.

---

## Faz 1 — Foundation: Design Tokens + Fontlar

**Süre tahmini:** 0.5 gün
**Risk:** Düşük (yeni dosyalar, mevcut bozulmaz)

### Hedef
Tasarım sisteminin temel taşlarını projeye enjekte etmek. Bu fazda **hiçbir görsel değişiklik olmaz** — sadece altyapı kurulur.

### Yapılacaklar

1. **`tokens.css`'i taşı**
   - `design_handoff_hukdok/tokens.css` içeriğini `frontend/src/styles/tokens.css` olarak kopyala
   - `frontend/src/index.css` üstüne `@import './styles/tokens.css';` ekle
   - **Mevcut Tailwind tema'sını henüz override etme** — token'lar yan yana var olur

2. **Fontları yükle**
   - `frontend/index.html` `<head>` içine Google Fonts link'i ekle:
     ```html
     <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
     ```
   - **Inter zaten yüklü** — sadece Fraunces ve JetBrains Mono yeni

3. **Tailwind tema'sını genişlet**
   - `frontend/tailwind.config.ts` içine yeni font-family token'ları ekle:
     ```ts
     theme: {
       extend: {
         fontFamily: {
           display: ['Fraunces', 'Georgia', 'serif'],
           sans: ['Inter', 'ui-sans-serif', 'system-ui'],
           mono: ['JetBrains Mono', 'ui-monospace'],
         },
         colors: {
           burgundy: { 50: '#faf3f4', ..., 950: '#260d14' }, // 11 ton
         },
       },
     }
     ```
   - **Mevcut renkleri silme**, yenilerini ekle

4. **Theme provider'ı genişlet**
   - `frontend/src/components/theme-provider.tsx` mevcut light/dark mantığını kullanıyor
   - Yeni token'lardaki light/dark CSS variable'larını `body[data-theme]` attribute'una göre uygula
   - **Default temayı şimdilik light bırak** (Faz 2'de dark'a çevrilecek)

### Dokunulacak dosyalar
- `frontend/src/styles/tokens.css` (YENİ)
- `frontend/src/index.css` (1 satır @import eklenir)
- `frontend/index.html` (1 satır font link eklenir)
- `frontend/tailwind.config.ts` (font ve renk genişletmesi)

### Test
- `npm run dev` — derleme hatasız geçmeli
- Sayfa görsel olarak **eskisiyle aynı** olmalı (henüz hiçbir komponent yeni token'ları kullanmıyor)
- DevTools'ta yeni CSS variable'lar tanımlı olmalı (`getComputedStyle(document.documentElement).getPropertyValue('--burgundy-700')` → `#6d2434` dönmeli)
- Network sekmesinde Fraunces ve JetBrains Mono fontları yüklenmeli

### Çıktı / commit
`feat(redesign-faz-1): design tokens ve yeni fontları projeye ekle`

---

## Faz 2 — Brand Renk Geçişi (Lacivert → Burgundy)

**Süre tahmini:** 0.5 gün
**Risk:** Orta (görsel değişim ilk kez görünür, ama geri alınabilir)

### Hedef
Tüm primary/brand renklerini lacivert'ten burgundy'ye geçirmek. Bu fazda **navigasyon hâlâ eski**, sadece renkler değişir.

### Yapılacaklar

1. **Mevcut `#1a2942` referanslarını bul ve değiştir**
   - Global grep: `#1a2942`, `#1A2942`, `bg-blue-`, `text-blue-` (varsa)
   - Her referansı `var(--brand)` veya Tailwind `bg-burgundy-700` ile değiştir
   - `index.html` `theme-color` meta tag'ini güncelle: `#1a2942` → `#6d2434`
   - `site.webmanifest` `theme_color`'u güncelle

2. **Default temayı dark'a çevir** (opsiyonel — kullanıcı tercihine bağlı)
   - `theme-provider.tsx` defaultTheme'i `light` → `dark` yap
   - Test: ilk açılışta dark olarak gelmeli, kullanıcının localStorage tercihi varsa onu korumalı

### Dokunulacak dosyalar
- `frontend/index.html` (theme-color)
- `frontend/public/site.webmanifest` (theme_color)
- `frontend/src/components/theme-provider.tsx`
- Mevcut `#1a2942` ile boyanmış tüm komponentler (grep ile bulunacak — muhtemelen Login, Header, butonlar)

### Test
- Buton hover'ları, focus ring'ler burgundy
- Light → dark geçişinde brand rengi `#6d2434` → `#b8404c` (dark variant) olmalı
- Logo ve favicon hâlâ eski lacivert — bu sonraki fazda güncellenecek (uyarı: bunu commit notuna ekle)

### Çıktı / commit
`feat(redesign-faz-2): brand rengini lacivert'ten burgundy'ye geçir`

---

## Faz 3 — App Shell (Sidebar + Topbar)

**Süre tahmini:** 2 gün
**Risk:** Yüksek (navigasyon paradigması değişiyor — tüm sayfaları etkiler)

### Hedef
Üst-nav'ı sol-sidebar + sabit topbar ile değiştirmek. Bu, kullanıcının en çok hissedeceği değişiklik.

### Yapılacaklar

1. **Yeni komponentler oluştur**
   - `frontend/src/components/shell/Shell.tsx` (ana wrapper)
   - `frontend/src/components/shell/Sidebar.tsx`
   - `frontend/src/components/shell/Topbar.tsx`
   - `frontend/src/components/shell/SidebarOpener.tsx` (kapalı durumda topbar'da)
   - `frontend/src/components/shell/NavItem.tsx`
   - `frontend/src/components/shell/UserCard.tsx` (sidebar alt)
   - `design_handoff_hukdok/shell.jsx`'ten görsel referans, mantık yeniden yaz

2. **Routing'i Shell ile sar**
   - `frontend/src/App.tsx`'te her `<Route>`'u `<Shell>` ile sar
   - Veya layout route pattern: `<Route element={<Shell />}>` altına nested route'lar
   - Sidebar state (open/collapsed) Shell içinde tutulur, localStorage'a kaydedilir

3. **Mevcut Header'ı sakla ama kullanma**
   - `Header.tsx` ve `NavLink.tsx` dosyaları **silinmez**, sadece App.tsx'ten import edilmemeleri yeterli
   - Faz 12'de silinecek

4. **Sayfa başlığını topbar'a taşı**
   - Her sayfa kendi başlığını ya prop ile geçer ya da context'ten okur
   - Önerilen: `usePageTitle('Davalar')` hook'u, Topbar tüketir

### Dokunulacak dosyalar
- `frontend/src/components/shell/*` (YENİ klasör)
- `frontend/src/App.tsx` (Routes etrafı Shell ile sarılır)
- `frontend/src/hooks/usePageTitle.ts` (YENİ)
- 12 sayfa (`pages/*.tsx`) — her birine `usePageTitle` çağrısı eklenir

### Test
- Sidebar açık/kapalı animasyonu yumuşak
- Her sayfada doğru nav item active görünüyor
- Topbar'da doğru sayfa başlığı var
- Mobile (1024px altı) için davranış belirsiz — README'de "mobile yok" diyor, **tablet/mobil için en azından sidebar overlay açılış mantığı eklenebilir**, ama bu opsiyonel

### Çıktı / commit
`feat(redesign-faz-3): yeni App Shell — Sidebar + Topbar`
**Tag:** `frontend-redesign-faz-3-tamam` (büyük milestone)

---

## Faz 4 — Dashboard'lar (Avukat + İdari, frontend-only görünüm seçici)

**Süre tahmini:** 3-4 gün
**Risk:** Orta (yoğun komponent + grafik + tablo)

### Hedef
İki dashboard'u (Avukat ve İdari) görsel olarak birebir yeniden inşa etmek. Backend rol sistemi YOK — kullanıcı frontend'de hangi görünümü göreceğini seçer.

### Yapılacaklar

1. **Görünüm seçici (View Switcher)**
   - `frontend/src/hooks/useDashboardView.ts` (YENİ)
     - localStorage'dan `hukdok.dashboard.view` okur, default `'avukat'`
     - `{ view, setView }` döner
   - Sidebar'ın user card'ında veya Topbar'da küçük toggle:
     ```
     Görünüm: [ Avukat ] [ İdari ]
     ```
   - Seçim anında dashboard yenilenmeden değişir
   - **Backend'e hiçbir şey gönderilmez** — tamamen UI tercihi

2. **Ortak komponentler**
   - `MetricCard.tsx` (4'lü metrik kartları — Süre uyarısı, Yeni belge vb.)
   - `SectionHeader.tsx` (eyebrow + title + meta — `FlowSectionH` karşılığı)
   - `HairlineCard.tsx` (1px border kart — `FlowCard` karşılığı)
   - `Eyebrow.tsx` (ALLCAPS Mono başlık)

3. **Avukat Dashboard**
   - `frontend/src/pages/dashboards/AvukatDashboard.tsx`
   - Bileşenler: 4 metrik üst sıra → büyük takvim widget (hafta görünümü, duruşma dot'ları) + sağ kolon (Son açılan, Sabitlenmişler) → Süresi yaklaşan işler tablo
   - **API:** Mevcut endpoint'lerden veri çeker (yeni endpoint AÇILMAZ). Hangi widget'ın hangi mevcut API'dan beslendiği port sırasında netleşir; veri yoksa o widget şimdilik boş/skeleton kalır.

4. **İdari Dashboard**
   - `frontend/src/pages/dashboards/IdariDashboard.tsx`
   - 3'lü hızlı eylem (Belge Yükle / Yeni Dava / Müvekkil Ekle) → günün özeti → Süreli işler panel (sorumlu avukat + bildirildi/bildirilecek) → inceleme bekleyen belgeler → avukat istekleri + son aktivite
   - **API:** Aynı şekilde mevcut endpoint'lerden besleme

5. **Dashboard route'u**
   - `/dashboard` veya `/` — `useDashboardView()` ile hangisi seçiliyse onu render eder
   - Tek route, koşullu render

6. **Takvim widget**
   - Mevcut `react-day-picker` paketi var, hafta görünümü için custom grid yapılabilir
   - Hearing dot'ları için backend'den (mevcut API) duruşma tarihlerini çek

7. **Eksik veri durumu**
   - Yeni tasarımda bazı widget'lar mevcut backend'de karşılığı olmayan veriyi gösterebilir (örn. "sabitlenmişler" listesi)
   - Bunlar için iki opsiyon:
     - **a) localStorage:** Kullanıcı kendi sabitlenmişlerini frontend'de tutar (örn. son ziyaret edilenler)
     - **b) Widget'ı gizle:** Backend desteklemiyorsa o widget gösterilmez
   - Port sırasında her widget için karar verilir

### Dokunulacak dosyalar
- `frontend/src/pages/dashboards/AvukatDashboard.tsx` (YENİ)
- `frontend/src/pages/dashboards/IdariDashboard.tsx` (YENİ)
- `frontend/src/hooks/useDashboardView.ts` (YENİ)
- `frontend/src/components/shell/ViewSwitcher.tsx` (YENİ)
- `frontend/src/pages/Home.tsx` / `Index.tsx` — route yeni dashboard'a yönlenir, eski içerikleri Faz 12'de silinir
- `frontend/src/components/dashboard/*` (yeni ortak komponentler)

### Test
- Default `/` → Avukat Dashboard
- Görünüm seçici "İdari" → İdari Dashboard'a anında geçiş
- Tarayıcı kapat-aç → tercih korunmuş (localStorage)
- Light/dark her ikisinde de düzgün
- Metrikler doğru veri gösteriyor (mevcut API'lardan)
- Takvim navigasyonu (önceki/sonraki hafta) çalışıyor

### Çıktı / commit
`feat(redesign-faz-4): avukat + idari dashboard'lar, görünüm seçici`

---

## Faz 5 — Belge Yükleme Akışı (Full Flow)

**Süre tahmini:** 4-5 gün
**Risk:** Yüksek (akışın tamamı bağımlı, bir kısmı yarıda kalırsa kullanıcı sıkışır)

### Hedef
Belge yükleme akışının tüm ekranlarını birlikte port etmek — yarım bırakılmamalı.

### Yapılacaklar

1. **Ortak primitives**
   - `FlowStageStrip` (4 aşama göstericisi: Yükleme → Analiz → Onay → Tamam)
   - `FlowButton` (primary/secondary/ghost varyantları)
   - `FlowField`, `FlowInput`, `FlowSelect`
   - `AiPill` (AI önerisi rozeti, confidence skoru)

2. **Drop Zone — 4 state**
   - `frontend/src/components/upload/DropZone.tsx`
   - `data-state` attribute ile state geçişi: `idle | dragover | dropped | rejected`
   - CSS transition'lar README'deki spec'lere uygun

3. **Belge Yükleme Boş Ekran**
   - `frontend/src/components/upload/UploadEmptyScreen.tsx`
   - Mevcut `FileUpload.tsx` yerine geçer (eski silinmez, route değiştirilir)

4. **Analiz Bekleme Animasyonu**
   - `frontend/src/components/upload/AnalysisPending.tsx`
   - Mevcut `AnalysisPending.tsx` üzerine yazılabilir veya v2 olarak yan yana

5. **Analiz Sonrası Onay Ekranı**
   - `frontend/src/components/upload/AnalysisConfirm.tsx`
   - Mevcut `AnalysisResults.tsx` yerine geçer
   - 2 kolon: sol özet + sağ form (her field'da AiPill, override edilince AiPill kaybolur)

6. **Modallar**
   - `QuickCaseModal` (mevcut var — yeniden tasarla)
   - `QuickCaseModalWithNewClient` (yeni)
   - `BulkUploadModal` (mevcut `BatchPrepScreen.tsx` ile birleştirilebilir)

7. **İşlem Kuyruğu**
   - `frontend/src/components/upload/QueueStatus.tsx`
   - Mevcut `QueueStatus.tsx`'i yenisiyle değiştir

### Dokunulacak dosyalar
- `frontend/src/components/upload/*` (yeni klasör)
- Mevcut `FileUpload.tsx`, `AnalysisPending.tsx`, `AnalysisResults.tsx`, `QuickCaseModal.tsx`, `QueueStatus.tsx`, `BatchPrepScreen.tsx` — sayfa bağlantıları yenilere kaydırılır, eski dosyalar Faz 12'de silinir

### Test
- Boş ekran → dosya sürükle → drop zone animasyonları
- Dosya bırakıldı → analiz beklemede animasyonu
- Analiz bitti → onay ekranı → AI pill'ler doğru
- Form alanı değiştirildi → AiPill kaybolur
- Onayla → kaydedildi
- Toplu yükleme → QueueStatus → her dosya işleniyor

### Çıktı / commit
`feat(redesign-faz-5): belge yükleme akışı yeni tasarımla`

---

## Faz 6 — Listeler (Davalar, Müvekkiller, Aktivite)

**Süre tahmini:** 2-3 gün
**Risk:** Düşük (mevcut liste mantığı çoğunlukla korunur, sadece görsel)

### Hedef
3 liste sayfasını yeni tasarıma çekmek: Davalar, Müvekkiller, Aktivite.

### Yapılacaklar

1. **Davalar Liste**
   - `frontend/src/pages/CaseList.tsx` yeniden tasarlanır
   - 4 metrik (Toplam / Derdest / İstinaf / Karar)
   - Sol filtre rail (durum, mahkeme, konu, sorumlu avukat)
   - Tablo (Dosya No · Taraflar · Mahkeme · Durum · Son işlem)
   - İdari rolünde sağ-alt sticky "+ Yeni Dava Aç"

2. **Müvekkiller Liste**
   - `frontend/src/pages/ClientList.tsx` yeniden tasarlanır
   - 4 metrik (Toplam / Doktorlar / Kurumlar / Bireysel)
   - Sol filtre (Kayıt Türü, Kategori, Şehir, Tıbbi Branş)
   - Tablo + tıklayınca **sağdan kayan Quick View paneli** (320-360px)

3. **Aktivite Geçmişi**
   - `frontend/src/pages/ActivityHistory.tsx` yeniden tasarlanır
   - 4 metrik (Toplam / E-posta ile / E-postasız / Hatalı)
   - Günlük gruplanmış tablo

### Dokunulacak dosyalar
- `frontend/src/pages/CaseList.tsx`
- `frontend/src/pages/ClientList.tsx`
- `frontend/src/pages/ActivityHistory.tsx`
- `frontend/src/components/QuickViewPanel.tsx` (YENİ, Müvekkil listesinde)

### Test
- Her listede arama, filtre, sıralama çalışıyor
- Quick View paneli yumuşak açılıyor/kapanıyor
- Mobile'da liste responsive (en azından scroll)

### Çıktı / commit
`feat(redesign-faz-6): davalar, müvekkiller ve aktivite listeleri`

---

## Faz 7 — Formlar (Dava, Müvekkil)

**Süre tahmini:** 1.5 gün
**Risk:** Düşük

### Hedef
Yeni dava ve müvekkil formlarını yeni tasarıma çekmek.

### Yapılacaklar

1. **Dava Formu**
   - `frontend/src/pages/NewCase.tsx`
   - Sol ana kolon: Taraf Bilgileri + Dava Bilgileri + (varsa) Hasar Bilgileri
   - Sağ sticky rail (320px): Ofis No (otomatik), Sorumlu, Büro Türü, Tazminat, [Kaydet] [Vazgeç]

2. **Müvekkil Formu**
   - `frontend/src/pages/NewClient.tsx`
   - 4 bölüm: Kişisel / İletişim / Ek Bilgiler / Vekalet
   - Sağda "İşlemi Tamamla" aksiyon kartı: Güncelle / İptal / **Kaydı Sil** (destructive — Confirm Dialog'a bağlanır, ama Confirm Dialog Faz 10'da geliyor)

### Dokunulacak dosyalar
- `frontend/src/pages/NewCase.tsx`
- `frontend/src/pages/NewClient.tsx`

### Test
- Form validation çalışıyor (Zod schema'lar dokunulmadı)
- Sticky rail scroll'a göre sabit kalıyor

### Çıktı / commit
`feat(redesign-faz-7): dava ve müvekkil formları`

---

## Faz 8 — Detay Sayfaları (Dava Detay 4-tab, Case Group)

**Süre tahmini:** 2-3 gün
**Risk:** Orta (4 sekmenin tamamı + grup görünümü)

### Hedef
Dava detay sayfasını ve grup görünümünü yeni tasarıma çekmek.

### Yapılacaklar

1. **Dava Detay**
   - `frontend/src/pages/CaseDetails.tsx`
   - Üst hero: brand sol şeritli kart (dosya no Mono büyük + durum chip + konu + meta)
   - Linked case chip'leri
   - 4 sekme:
     1. Genel Bilgiler — taraf grid, dava bilgisi, sorumlu, ofis no
     2. Takip — vertical timeline
     3. Taraflar — 5 rol kartı
     4. Belgeler — gruplanmış evrak listesi

2. **Dava Grup Görünümü**
   - `frontend/src/pages/CaseGroup.tsx`
   - Üst grup kartı (gradient şerit)
   - Alt: dava türü kartları, tıklayınca detay

### Dokunulacak dosyalar
- `frontend/src/pages/CaseDetails.tsx`
- `frontend/src/pages/CaseGroup.tsx`
- `frontend/src/components/CaseTrackingPanel.tsx` (timeline yeniden tasarımı)

### Test
- Her sekme arası geçiş yumuşak
- URL'de aktif sekme yansıyor (`/cases/:id?tab=takip`)
- Linked case chip'lerine tıklayınca o davaya navigasyon

### Çıktı / commit
`feat(redesign-faz-8): dava detay ve grup görünümü`

---

## Faz 9 — Sistem Komponentleri

**Süre tahmini:** 2 gün
**Risk:** Düşük (izole komponentler)

### Hedef
Toast, ConfirmDialog, ⌘K palette ve diğer sistem-wide komponentleri eklemek.

### Yapılacaklar

1. **Toast Sistemi**
   - Mevcut `sonner` kütüphanesi var — onun üzerine custom render
   - 4 tone: success / info / warning / error
   - Stack max 3, hover pause, auto-dismiss
   - `frontend/src/components/system/Toast.tsx`
   - `frontend/src/lib/toast.ts` (API: `toast.success({...})`)

2. **ConfirmDialog**
   - 3 tone: destructive / warning / info
   - Opsiyonel: irreversible warning, check-required input ("SİL yaz")
   - `frontend/src/components/system/ConfirmDialog.tsx`
   - `frontend/src/lib/confirm.ts` (Promise-based API: `await confirm({...})`)
   - Mevcut `AlertDialog` (Radix UI) yerine bunu kullan

3. **⌘K Komut Paleti**
   - Mevcut `cmdk` kütüphanesi paket.json'da var ama kullanılmıyor — şimdi kullanılacak
   - Global keyboard listener (Cmd+K / Ctrl+K)
   - 3 mode: idle (recents + quick actions) / search (gruplanmış sonuçlar) / empty (öneri chip'leri)
   - Recents localStorage'da
   - `frontend/src/components/system/CommandPalette.tsx`

4. **Mevcut destructive aksiyonları ConfirmDialog'a bağla**
   - Müvekkil sil, dava sil, kullanıcı sil vb. — eski `confirm()` veya AlertDialog çağrıları ConfirmDialog'a geçirilir

### Dokunulacak dosyalar
- `frontend/src/components/system/*` (YENİ klasör)
- `frontend/src/lib/toast.ts`, `confirm.ts`
- Mevcut destructive aksiyon noktaları — confirm dialog kullanıma geçirilir

### Test
- Cmd+K her sayfada açılıyor, arama çalışıyor
- Toast'lar sağ-alt stack halinde geliyor, otomatik kapanıyor
- ConfirmDialog'da check-required input'lu silme ("SİL yaz") test edilir

### Çıktı / commit
`feat(redesign-faz-9): sistem komponentleri (toast, confirm, cmd palette)`

---

## Faz 10 — Admin Paneli + Yetki Belgesi

**Süre tahmini:** 3 gün
**Risk:** Orta (admin paneli geniş kapsam)

### Hedef
Admin panelini (14 sekme) ve yetki belgesi modal'ını yeni tasarıma çekmek.

### Yapılacaklar

1. **Admin Paneli**
   - `frontend/src/pages/AdminPage.tsx`
   - 14 sekme (Avukatlar default, Durumlar, Belge Türleri, Dava Konuları, E-posta Alıcıları, vd.)
   - Her sekme: sol tablo + sağ düzenle/ekle form paneli
   - URL'de aktif sekme yansır
   - **Yeni:** Avukatlar sekmesinde rol değiştirme (Faz 4 backend'i hazırsa)

2. **Yetki Belgesi Modal**
   - `frontend/src/components/YetkiBelgesiModal.tsx` yeniden yazılır
   - 3 adım:
     1. Avukatlar — Veren (single) + Yetkilendirilen (multi chip)
     2. Detaylar — TC, sicil no, vekaletname, kapsam (radio)
     3. Önizleme — krem letterhead, Times New Roman 12pt, basılacak hali
   - Footer: [UDF İndir] [Yazdır]

### Dokunulacak dosyalar
- `frontend/src/pages/AdminPage.tsx`
- `frontend/src/components/YetkiBelgesiModal.tsx`

### Test
- 14 sekmenin tümü çalışıyor
- Yetki belgesi 3 adımı arası geçiş, önizleme, UDF/print

### Çıktı / commit
`feat(redesign-faz-10): admin paneli ve yetki belgesi`

---

## Faz 11 — Temizlik

**Süre tahmini:** 1 gün
**Risk:** Düşük (sadece silme)

### Hedef
Artık kullanılmayan eski komponentleri silmek, kod tabanını sadeleştirmek.

### Yapılacaklar

1. **Eski komponentler**
   - `frontend/src/components/Header.tsx`
   - `frontend/src/components/NavLink.tsx`
   - `frontend/src/components/HukdokLogo.tsx` (yeni Shell'de yeni logo komponenti varsa)
   - Eski sürümleri Faz 6'da geçici kalmış olabilir — onlar da

2. **Eski stiller**
   - `frontend/src/index.css`'te artık kullanılmayan custom class'lar
   - Tailwind config'inde artık kullanılmayan renkler (lacivert, eski blue token'lar)

3. **Eski mock data**
   - Eğer geçici constants kullandıysak (Faz 5'te) — gerçek API'a bağlanmış olmalı

4. **Bağımlılık temizliği**
   - `package.json`'da artık kullanılmayan paketler varsa kaldır (örneğin Header tarafında kullanılan bir lib)

5. **Final QA**
   - Tüm sayfaları light + dark tema, sidebar açık + kapalı kombinasyonlarında gözden geçir
   - Console'da error/warning olmamalı
   - Network'te 404 olmamalı (eski asset referansları kalmamalı)

### Çıktı / commit
`refactor(redesign-faz-11): eski komponentleri ve kullanılmayan stilleri sil`
**Tag:** `frontend-redesign-tamam-2026-XX-XX`

---

## Bağımlılık Grafiği

```
Faz 0 (TAMAM)
  ↓
Faz 1 — Tokens & Fontlar  [hiçbir UI değişikliği yok, altyapı]
  ↓
Faz 2 — Brand renk burgundy
  ↓
Faz 3 — App Shell ────────────── (bu noktadan sonra her sayfa Shell içinde)
  ↓
Faz 4 — Dashboard'lar (Avukat + İdari, frontend toggle ile)
  ↓
Faz 5 — Belge yükleme akışı (TÜM AKIŞ TEK PR'DA, yarıda bırakma)
  ↓
Faz 6 — Listeler (Faz 5 ile paralel olabilir, bağımsız)
  ↓
Faz 7 — Formlar
  ↓
Faz 8 — Detay sayfaları
  ↓
Faz 9 — Sistem komponentleri ── (ConfirmDialog'u erkene de alabiliriz, Faz 7'nin destructive butonu için)
  ↓
Faz 10 — Admin paneli + Yetki belgesi
  ↓
Faz 11 — Temizlik (eski kod silme)
```

---

## Toplam Tahmini Efor

| Faz | Tahmin (gün) |
|---|---|
| 0 | ✅ Tamam |
| 1 | 0.5 |
| 2 | 0.5 |
| 3 | 2 |
| 4 | 3-4 |
| 5 | 4-5 |
| 6 | 2-3 |
| 7 | 1.5 |
| 8 | 2-3 |
| 9 | 2 |
| 10 | 3 |
| 11 | 1 |
| **Toplam** | **~22-25 gün** (kabaca 4.5-5 hafta tek geliştirici full-time) |

---

## Riskler ve Kontrol

### Risk 1 — Yarıda kalmış faz
Bir faz başlanır ama bitirilmezse görsel olarak tutarsızlık olur. **Önlem:** Her fazın "bitti" tanımı net (test maddeleri). Yarım kalan faz commit edilmez, branch'te bekler.

### Risk 2 — Production canlı ve kullanıcılar kullanırken
Her faz canlıya çıktıkça kullanıcıyı şaşırtabilir. **Önlem:** Her faz sonrası kısa bir kullanıcı bildirimi (örn. "Tasarımı yeniliyoruz, geri bildiriminiz değerli").

### Risk 3 — Mevcut bug'lar yeni komponenste tekrarlanır
Eski koddaki mantık bug'ları (örn. AnalysisResults.tsx'teki state bug'ları) yeni komponente "kopya" çekilirse aynı bug devam eder. **Önlem:** Her sayfa migrate edilirken o sayfanın bilinen bug'ları açılmış mı kontrol edilir (`docs/` altındaki inceleme dosyalarına bak).

---

## Rollback Stratejisi

Herhangi bir faz başarısızsa:

```bash
# Sadece o faz'ın commit'ini revert et
git revert <faz-commit-sha>

# Veya tüm redesign'ı geri al, tag'e dön
git checkout frontend-pre-redesign-2026-05-20 -- frontend/
git commit -m "revert: frontend redesign geri alındı, eski hale dönüldü"
```

---

## Bağlantılı Dokümanlar

- `design_handoff_hukdok/README.md` — Tasarım paketinin orijinal readme'si
- `design_handoff_hukdok/tokens.css` — Design token'lar
- `frontend/README_FRONTEND.md` — Mevcut frontend dokümantasyonu

---

## Süreç Takibi

Bu planın sonuna her faz bitiminde:
- [ ] Faz adı, commit SHA, tamamlanma tarihi
- Karşılaşılan sorunlar, alınan kararlar

eklenecek.

### Faz Tamamlanma Logu

| Faz | Commit SHA | Tarih | Not |
|---|---|---|---|
| 0 | `0512bc5` | 2026-05-20 | README + tag oluşturuldu |
| 1 | — | — | — |
| 2 | — | — | — |
| ... | | | |
