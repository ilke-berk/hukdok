# 007 — Form taslakları sessionStorage'da; çıkışta yazım bastırılır (KVKK)

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul
- **Bağlam:** Dava formu ve intake sihirbazı yarım kalan girdiyi taslak olarak saklar.
  Taslaklar TC kimlik numarası ve isim içerir. Ayrıca çıkış akışında bir yarış vardı:
  `clearAppStorage()` taslakları siliyor, hemen ardından `logoutRedirect` navigasyonu
  `pagehide` + `beforeunload` tetikliyor ve bu flush'lar taslağı geri yazıyordu.
  sessionStorage aynı sekmedeki AAD gidiş-dönüşünde hayatta kaldığı için **sonraki
  kullanıcı, önceki kullanıcının TC içeren taslağını "geri yükle" şeridiyle görüyordu**
  (`frontend/src/lib/formDraft.ts:49-53`).
- **Karar:** İki katman:
  1. Taslaklar **sessionStorage**'da tutulur, `localStorage`'da değil
     (`formDraft.ts:10-11`, `:14-19`). Sürümlü zarf + `maxAgeMs` bayatlama denetimi ile
     (seçenek `:32`, kontrol `:168-172`).
  2. Çıkış akışı, temizlikten **önce** `suppressAllDrafts()` çağırır (`formDraft.ts:71-73`).
     Bayrak kuruluyken hiçbir `DraftStore.save` diske yazmaz ve `attachUnloadGuard` ne uyarı
     diyaloğu ne flush üretir. Bayrak modül-içi bellektedir — redirect/reload sayfayı
     tazeleyince kendiliğinden sıfırlanır.
- **Gerekçe:** Kodda birebir: "KVKK: taslaklar sessionStorage'da tutulur — sekme kapanınca
  ölür. TC/isim içeren form verisi kalıcı localStorage'a YAZILMAZ" (`formDraft.ts:10-11`).
  Susturma bayrağı için: tarayıcının "ayrılmak istiyor musunuz?" sorusu da logout'un
  ortasına düşmemeli (`:56-58`).
- **Bilinçli istisna (kodda büyük harfle):** "Oturum düşmesi (401 →
  `SESSION_EXPIRED_EVENT`) bu bayrağı KURMAZ — orada flush bilinçli bir özelliktir (aynı
  kullanıcı tekrar girince emeği geri gelir; depo da temizlenmez)" (`formDraft.ts:61-64`).
  Yani ayrım "kim gidiyor" sorusudur: **çıkış** = başka kullanıcı gelebilir → sustur;
  **oturum düşmesi** = aynı kullanıcı dönecek → koru.
- **Reddedilenler:**
  - *localStorage* — kalıcıdır, TC içeren veriyi sekme/oturum ötesine taşır.
  - *Yalnız `clearAppStorage()` ile yetinmek* — unload flush'ları veriyi geri yazdığı için
    yetersizdi; hatanın kendisi buydu.
- **Test:** `frontend/src/lib/formDraft.test.ts`, `frontend/src/hooks/useFormDraft.test.tsx`
- **İlgili:** [`docs/mimari/dava-acma-akisi.md`](../mimari/dava-acma-akisi.md)
