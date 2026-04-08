# Refactor Planı — Kolaydan Zora

## Genel Durum

`@tanstack/react-query` v5 zaten `package.json`'da mevcut ama hiç kullanılmıyor.  
Tüm hook'lar elle `useState` + `useCallback` ile fetch yapıyor, duplicate logic var.

---

## ADIM 1 — `authenticatedRequest` duplicate'ini sil (Kolay)

**Dosyalar:** `useCases.ts`, `useClients.ts`, `useConfig.ts`

Her üç hook'ta aynı `authenticatedRequest` wrapper kopyalanmış.  
`useConfig.ts`'teki versiyon `accounts` kontrolü bile yapmıyor — tutarsız.

**Yapılacak:**
- `lib/api.ts`'e veya yeni `lib/useAuthRequest.ts`'e tek bir `useAuthRequest()` hook'u çıkar
- `useCases`, `useClients`, `useConfig` bu ortak hook'u import eder
- `accounts.length === 0` kontrolü tek yerde olur

**Etki:** Küçük, bağımsız, kırılma riski düşük.

---

## ADIM 2 — `useConfig`'i React Query'e taşı (Orta)

**Dosyalar:** `useConfig.ts`, `useConfig.ts`'i kullanan sayfalar

`useConfig` sadece okuma (GET) yapıyor ve uygulama genelinde paylaşılan veri.  
React Query'nin cache/dedup avantajı burada en çok işe yarar.

**Yapılacak:**
- `QueryClient` provider'ı `main.tsx`'e ekle (zaten `@tanstack/react-query` kurulu)
- `useQuery` ile şu endpoint'leri fetch et:
  - `/api/config/lawyers`
  - `/api/config/statuses`
  - `/api/config/doctypes`
  - `/api/config/email_recipients`
  - `/api/config/case_subjects`
- Mutasyon action'ları (`addLawyer`, `deleteStatus` vb.) `useMutation` + `invalidateQueries` ile yeniden yaz
- `isLoading` state'i React Query'nin `isLoading` flag'ına bırak

**Etki:** `useConfig` izole, sayfalarda interface değişmez.

---

## ADIM 3 — `useClients`'ı React Query'e taşı (Orta)

**Dosyalar:** `useClients.ts`, `ClientList.tsx`, `NewClient.tsx`, `QuickCaseModal.tsx`

`getClients` çağrısı birden fazla sayfada yapılıyor, her seferinde yeniden fetch ediliyor.

**Yapılacak:**
- `getClients` → `useQuery({ queryKey: ['clients'], queryFn: ... })`
- `saveClient`, `updateClient`, `deleteClient` → `useMutation` + `invalidateQueries(['clients'])`
- Sayfalarda `const { data: clients, isLoading } = useClients()` şeklinde kullanım

**Etki:** ClientList ve QuickCaseModal aynı cache'i paylaşır, duplicate fetch ortadan kalkar.

---

## ADIM 4 — `useCases`'i React Query'e taşı (Zor)

**Dosyalar:** `useCases.ts`, `CaseList.tsx`, `CaseDetails.tsx`, `NewCase.tsx`, `Home.tsx`

En karmaşık hook. `getCases` pagination + filtre parametreleri alıyor, `getCaseStats` ayrı endpoint.

**Yapılacak:**
- `getCases(options)` → `useQuery({ queryKey: ['cases', options], queryFn: ... })`  
  (options objesini queryKey'e dahil et — filtre değişince otomatik refetch)
- `getCaseStats` → `useQuery({ queryKey: ['caseStats'], queryFn: ... })`
- `getCase(id)` → `useQuery({ queryKey: ['case', id], queryFn: ... })`
- `saveCase`, `updateCase`, `deleteCase` → `useMutation` + `invalidateQueries`
- `searchCases` için ya ayrı query key ya da `getCases` ile `q` parametresi birleştir

**Dikkat edilecekler:**
- `CaseList.tsx`'teki lokal filtre state'leri (status, lawyer, q) queryKey'e doğru bağlanmalı
- `saveCaseAndReturn` pattern'i — mutation sonucu dönen data `onSuccess` callback'i ile ele alınmalı
- Optimistic update gerekebilir (DELETE anında listeden çıkarmak için)

---

## Sıra Özeti

| Adım | İş | Risk | Bağımlılık |
|------|-----|------|------------|
| 1 | `authenticatedRequest` → ortak hook | Çok düşük | Yok |
| 2 | `useConfig` → React Query | Düşük | Adım 1 |
| 3 | `useClients` → React Query | Orta | Adım 1 |
| 4 | `useCases` → React Query | Yüksek | Adım 1, 2, 3 |
