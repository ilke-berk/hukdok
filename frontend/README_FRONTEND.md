# HUKDOK Frontend — Hanyaloğlu & Acar Hukuk Bürosu

Hukuki belge analiz, dava takip ve doküman yönetim platformunun frontend uygulaması.

## Teknoloji Stack'i

- **React 18** + **TypeScript** + **Vite**
- **TailwindCSS** + **shadcn/ui** (Radix UI tabanlı, 49 hazır komponent `src/components/ui/` altında)
- **React Router v6** — sayfa yönetimi
- **TanStack Query (React Query) v5** — server state / API cache
- **React Hook Form + Zod** — form validation
- **Azure MSAL** (`@azure/msal-react` v5) — Microsoft Entra ID (Azure AD) authentication
- **Axios** — HTTP istemcisi
- **Recharts** — grafikler
- **DnD Kit** — sürükle-bırak
- **next-themes** — light/dark mode
- **Lucide React** — ikonlar
- **mammoth, docx, file-saver** — DOCX dosya işleme

## Klasör Yapısı

```
frontend/
├── public/                      # Statik dosyalar (favicon, og-image, logolar)
├── src/
│   ├── App.tsx                  # Ana router, AuthProvider, ThemeProvider
│   ├── main.tsx                 # Entry point
│   ├── index.css                # Tailwind + global stiller
│   ├── pages/                   # Sayfa bileşenleri (12 sayfa)
│   │   ├── Home.tsx             # Ana sayfa
│   │   ├── Login.tsx            # Giriş ekranı (Azure AD)
│   │   ├── CaseList.tsx         # Dava listesi
│   │   ├── CaseDetails.tsx      # Dava detay
│   │   ├── CaseGroup.tsx        # Grup dava görünümü
│   │   ├── NewCase.tsx          # Yeni dava oluştur
│   │   ├── ClientList.tsx       # Müvekkil listesi
│   │   ├── NewClient.tsx        # Yeni müvekkil
│   │   ├── ActivityHistory.tsx  # Aktivite geçmişi
│   │   ├── AdminPage.tsx        # Admin paneli
│   │   ├── Index.tsx            # Dashboard
│   │   └── NotFound.tsx         # 404
│   ├── components/
│   │   ├── ui/                  # shadcn/ui komponentleri (DOKUNMAYIN)
│   │   ├── email/               # Email şablonları
│   │   ├── Header.tsx           # Üst bar
│   │   ├── HukdokLogo.tsx       # Logo komponenti
│   │   ├── FileUpload.tsx       # Dosya yükleme
│   │   ├── AnalysisResults.tsx  # Belge analiz sonuçları
│   │   ├── BatchPrepScreen.tsx  # Toplu yükleme hazırlık ekranı
│   │   ├── CaseTrackingPanel.tsx
│   │   ├── QuickCaseModal.tsx
│   │   ├── YetkiBelgesiModal.tsx
│   │   └── ... (ProtectedRoute, NavLink, theme-toggle vb.)
│   ├── hooks/                   # Custom React hook'ları
│   │   ├── useCases.ts          # Dava CRUD
│   │   ├── useClients.ts        # Müvekkil CRUD
│   │   ├── useConfig.ts         # Uygulama config
│   │   ├── useAuthRequest.ts    # Auth akışı
│   │   ├── useIdleTimeout.ts    # Boş kalma zamanaşımı
│   │   └── useDebounce.ts, use-mobile, use-toast
│   ├── lib/                     # Yardımcı modüller
│   │   ├── api.ts               # Axios instance + endpoint sarmalayıcıları
│   │   ├── caseNumberUtils.ts   # Dava no validasyon/format
│   │   ├── documentUtils.ts     # Belge işlemleri
│   │   ├── directoryStorage.ts  # File System Access API
│   │   ├── validation.ts        # Zod şemaları
│   │   └── utils.ts             # Tailwind clsx birleştirici
│   ├── config/
│   │   └── msalConfig.ts        # Azure AD MSAL konfigürasyonu
│   └── assets/                  # İmaj/svg
├── index.html                   # Vite entry HTML (SEO meta + favicon link'leri)
├── vite.config.ts               # Build config, dev proxy ayarları
├── tailwind.config.ts           # Tema renkleri, fontlar
├── components.json              # shadcn/ui konfigürasyonu
├── tsconfig*.json               # TypeScript
├── eslint.config.js
├── postcss.config.js
├── Dockerfile                   # Multi-stage Nginx build
└── package.json
```

## Kurulum

```bash
# 1. Bağımlılıkları yükle
#    React 18 + MSAL v5 arasındaki peer dep çakışması için --legacy-peer-deps şart
npm install --legacy-peer-deps

# 2. Root dizinde .env oluştur (.env.example'a bak)
#    Vite envDir=".." olarak ayarlı, .env'i proje köküne koy

# 3. Dev sunucusunu başlat
npm run dev
# → http://localhost:8000 (8000 portu strictPort, başka port'a fallback yok)

# 4. Production build
npm run build
# → dist/ klasörü üretilir, nginx ile servis edilir
```

### Backend Bağımlılığı

Frontend dev modda backend'i `http://localhost:8001` üzerinden bekliyor. Vite proxy ayarı `vite.config.ts` içinde:

```ts
proxy: {
  '/api':     'http://localhost:8001',
  '/process': 'http://localhost:8001',
  '/confirm': 'http://localhost:8001',
  '/refresh': 'http://localhost:8001',
}
```

Backend ayrı bir Python/FastAPI projesi. Tasarım çalışması için backend'i çalıştırmana gerek YOK — sayfalar API çağrıları olmadan da render olur (loading state'ler veya boş veri görünür). Auth flow için mock veya sahte token ile test edebilirsin.

## Authentication

Microsoft Entra ID (Azure AD) ile SSO. `Login.tsx` MSAL `loginPopup` çağırıyor. Korumalı sayfalar `ProtectedRoute.tsx` ile sarılı, admin sayfalar `ProtectedAdminRoute.tsx` ile.

Tasarım çalışmasında bu akışa dokunman gerekmez — sadece görsel iyileştirmeye odaklan.

## Tasarım Sistemi

- **shadcn/ui** kullanılıyor — yeni komponent eklemek için:
  ```bash
  npx shadcn@latest add <component-name>
  ```
- Tema renkleri ve CSS değişkenleri [tailwind.config.ts](tailwind.config.ts) ve [src/index.css](src/index.css) içinde
- Dark mode `next-themes` üzerinden, `ThemeProvider` `App.tsx` içinde sarılı
- Logo komponenti [src/components/HukdokLogo.tsx](src/components/HukdokLogo.tsx)

## Kurumsal Kimlik (mevcut)

- Birincil renk: **lacivert #1a2942**
- Font: **Inter** (Google Fonts, `index.html` üzerinden yükleniyor)
- Marka: **Hanyaloğlu & Acar Hukuk Bürosu** (resmi ad) — **HUKDOK** (ürün adı)
- Favicon seti: `public/favicon*.png`, `public/android-chrome-*.png`, `public/apple-touch-icon.png`
- OG image: `public/og-image.png` (1731x909, bordo arkaplan)

## Sayfalar ve Özellikler (mevcut)

### Ana Akış
1. **Login** → Azure AD ile giriş
2. **Home / Index** → Dashboard, hızlı erişim
3. **CaseList** → Dava listesi (filtreleme, arama, sayfalama)
4. **NewCase** → Yeni dava oluştur (form, validation)
5. **CaseDetails** → Dava detay, ilişkili belgeler, takip paneli
6. **CaseGroup** → Birden fazla davayı grup olarak görüntüleme
7. **ClientList / NewClient** → Müvekkil yönetimi

### Belge İşleme
- **FileUpload.tsx** — drag&drop dosya yükleme
- **AnalysisPending.tsx** — analiz beklemede durumu
- **AnalysisResults.tsx** — Gemini AI analiz sonuçları
- **BatchPrepScreen.tsx** — toplu yükleme öncesi hazırlık ekranı
- **YetkiBelgesiModal.tsx** — yetki belgesi yükleme modal'ı

### Aktivite & Admin
- **ActivityHistory.tsx** — kullanıcı geçmişi
- **ActivityReportModal.tsx** — aktivite raporu detay
- **AdminPage.tsx** — kullanıcı/tenant yönetimi

## Bilinen UX Sorunları / İyileştirme Alanları

- Login sayfası sade, kurumsal kimlikten uzak
- Dashboard'da KPI/widget'lar yetersiz
- Mobil responsive iyileştirmeye açık
- Light/dark theme'da bazı kontrast sorunları olabilir
- Toplu yükleme akışında stepper/progress göstergesi geliştirilebilir

## Build ve Deploy

- Production'da Docker (Nginx) ile servis ediliyor (`frontend/Dockerfile`)
- Build sırasında root `.env` `/app` dışına kopyalanıyor (envDir konfigürasyonu)
- Prod'da Vite **çalıştırılmıyor**, statik dosyalar Nginx ile servis ediliyor

## İletişim

Mevcut tasarım/akış hakkında soru olursa proje sahibine ulaş.

---

**Not:** Bu paket node_modules ve dist hariç tüm frontend kaynak kodunu içerir. `npm install --legacy-peer-deps` ile başla.
