# 002 — Ofis numarası isim bloğu: kategori önceliği, "ilk müvekkil" değil

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul — **kullanıcı tarafından bilinçle onaylandı, değiştirme**
- **Bağlam:** Ofis dosya numarasının ikinci bloğu bir müvekkil adından türetilir. Bir davada
  birden çok müvekkil olabilir (örn. bir doktor + çalıştığı hastane + sigorta şirketi);
  hangisinin numaraya gireceği belirlenmelidir.
- **Karar:** İsim bloğuna giren müvekkil, **kategori önceliğiyle** seçilir; listedeki ilk
  müvekkil değil. `pickNameClient` öncelik fonksiyonu
  (`frontend/src/lib/caseNumberUtils.ts:150-167`):

  | Kategori | Öncelik (küçük = güçlü) |
  | --- | --- |
  | `Doktor` | 0 |
  | `Sağlık Çalışanı` | 1 |
  | `Hasta` | 2 |
  | `Bireysel` | 3 |
  | kategori yok | 4 |
  | diğer (kurum) | 6 |
  | adında/kategorisinde "sigorta" geçen | 10 |

  Kategori **kodu** ayrı seçilir (`bestCategoryCode`, `:173-203`): özgül sigorta (S1–S7) >
  S0 > D1 > D2 > H2 > H1 > X1.
- **Gerekçe:** Numara insan tarafından okunacak bir arşiv anahtarıdır; dosyanın **asıl
  öznesi** (hekim/hasta) numarada görünmelidir. Sigorta şirketi gibi tekrar eden kurumsal
  adlar bloğu doldurursa numara ayırt ediciliğini kaybeder — bu yüzden "sigorta" en zayıf
  önceliktedir. Fonksiyonun docstring'i kuralı özetler:
  `Kişi (Doktor/Sağlık Çalışanı/Hasta/Bireysel) > Kurum > Sigorta Şirketi`
  (`caseNumberUtils.ts:147-148`).
- **Reddedilenler:**
  - *Listedeki ilk müvekkili almak* — müvekkil sırası kullanıcı giriş sırasına bağlı,
    kararsız bir anahtar üretirdi.
  - *"İlk X1 olmayan kodu" seçmek* — kategori kodu için önceki davranıştı ve açık öncelikle
    değiştirildi; kodda not düşülmüş:
    `// Docstring'deki açık öncelik: D1 > D2 > H2 > H1 (önceden "ilk X1 olmayan" idi)`
    (`caseNumberUtils.ts:197`).
- **Test:** `frontend/src/lib/caseNumberUtils.test.ts`
- **İlgili:** [`docs/mimari/dava-acma-akisi.md`](../mimari/dava-acma-akisi.md)
