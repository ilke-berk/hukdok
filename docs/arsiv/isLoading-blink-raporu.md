# `isLoading` Blink Sorunları Raporu

## Sorunun Özeti

`useCases()` ve `useClients()` hook'larında tek bir global `isLoading` state var.
Bu hook'ların herhangi bir metodu çağrıldığında `isLoading=true` oluyor.
Eğer bir sayfa bu flag'i **tam sayfa render koşulunda** kullanıyorsa, her arka plan işleminde sayfa yanıp sönüyor.

---

## Kritik (CaseDetails ile aynı bug)

### `CaseGroup.tsx` — Satır 133
```tsx
if (loadingLocal || isLoading) {   // ← isLoading buradan geliyor: useCases()
    return <skeleton...>
}
```
CaseGroup sayfasında herhangi bir dava işlemi yapıldığında (refresh, güncelleme vb.) tüm sayfa skeleton'a dönebilir.

**Düzeltme:** `if (loadingLocal)` — aynı CaseDetails'te yaptığımız gibi.

---

## Orta Risk (Tam sayfa değil, içerik alanı)

### `CaseList.tsx` — Satır 297
```tsx
{isLoading ? <spinner> : <tablo>}
```
Buradaki `isLoading` hook'tan değil, **lokal state**'ten geliyor (`useState(true)`).
Sorunsuz — sadece tablo alanı spinner gösteriyor, sayfa kaybolmuyor.

### `ClientList.tsx` — Satır 346
```tsx
{isLoading ? <spinner> : <liste>}
```
`useClients()` hook'undan geliyor. Sayfa tamamen kaybolmuyor, sadece liste alanı değişiyor.
Ancak herhangi bir client işleminden sonra liste alanı anlık spinner'a dönebilir.

---

## Düşük Risk (Buton disable/guard amaçlı, blink yok)

### `AdminPage.tsx` — Satır 396
```tsx
if (isLoading) { return <spinner> }
```
`useConfig()` hook'undan geliyor. Config sadece uygulama açılışında yükleniyor, sonradan tetiklenmez. Pratikte sorun yaratmıyor.

### `NewClient.tsx` — Satır 725-726
```tsx
<Button disabled={isLoading}>
    {isLoading ? "Kaydediliyor..." : "Kaydet"}
</Button>
```
Sadece buton disable/label için kullanılıyor. Sayfa kaybolmuyor, sorun yok.

### `NewCase.tsx` — Satır 1453-1454
```tsx
<Button disabled={isSaving || isLoading}>
```
Buton disable için kullanılıyor. `isLoading` lokal state, `isSaving` hook'tan geliyor. Sayfa blinki yok.

---

## Özet Tablo

| Dosya | Satır | Kaynak | Risk | Sorun |
|-------|-------|--------|------|-------|
| `CaseGroup.tsx` | 133 | `useCases().isLoading` | **KRİTİK** | Tam sayfa blink |
| `ClientList.tsx` | 346 | `useClients().isLoading` | Orta | Liste alanı blink |
| `AdminPage.tsx` | 396 | `useConfig().isLoading` | Düşük | Sadece ilk yükleme |
| `NewClient.tsx` | 725 | `useClients().isLoading` | Düşük | Buton disable |
| `NewCase.tsx` | 1453 | `useCases().isLoading` | Düşük | Buton disable |
| `CaseList.tsx` | 297 | Lokal state | Sorunsuz | — |
