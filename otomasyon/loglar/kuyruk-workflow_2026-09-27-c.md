# Gece Kuyruğu (workflow) · 2026-09-27-c

## Özet

2 görev alındı · 0 işaretlendi · 1 bloke · 1 atlandı

## İşaretlenenler

İşaretlenen görev yok.

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — |

## Bloke

### G229 · Arayüzden avukat kodu kalkar (frontend)

**Testi değiştirmeden geçilemedi, görev tanımı gözden geçirilmeli.** Bu bir başarısızlık değil: hat, izin verilmeyen bir testi değiştirmek yerine doğru biçimde durdu.

- **Durma sebebi:** `test-degistirmek-gerekti`. Doğrulama yeşil (2 tur), ama bir kabul maddesi karşılanamadı.
- **Son parmak izi:** yeşil, 113 dosya, 1217 passed.
- **Commit (iş dalı `gorev/G229`, merge YOK, push YOK):** `d4a7a64`
- **Denenen yaklaşımlar:**
  - Tur 1: Avukat tablosu ve formu koddan arındırıldı, satır kimliği `kimlik` oldu, Pasife al işlemi `DELETE /api/config/lawyers/{kimlik}` çağırıyor, CaseList değeri `kimlik`. Yeni test, düzenleme diyaloğunda `editing.id` (AVK-) basıldığını yakaladı.
  - Tur 2: Düzenleme diyaloğunda avukat için ad basıldı. Tam paket 1217 passed, lint ve `tsc -b --force` temiz.
  - Kırmızı-yeşil kontrolü: Yeni testler eski kodda (stash ile) 7 testten 6'sında kırmızı verdi. Kalan 1 test, "diğer listeler değişmez" bekçisidir.
  - QuickCaseModal'daki ölü prefill kaldırılmadı. `QuickCaseModal.lawyer.test.tsx:154-157` bu davranışı kilitliyor ve dosya test taşıma izin listesinde yok.
- **Kök neden:** Görev tanımı, QuickCaseModal'daki ölü `prefill.avukat_kodu` kalemini kaldırmayı istiyor. Ancak test taşıma izni yalnız `AdminPage.listeler.test.tsx` için verilmiş. Tanımdaki bu çelişki çözülmeden kalem kapanamaz.
- **Notlar:**
  - Taşınan testlerde (`AdminPage.listeler.test.tsx`) expect sayısı değişmedi (24→24). Kimlikler AVK-0000n oldu, id yerine kimlik, kod dizisi yerine ad dizisi kullanıldı.
  - CaseList filtresi `l.kimlik || l.code || l.name` değerini kullanıyor. Bu yedek, izin listesi dışındaki `CaseList.config.test.tsx` testini korumak için eklendi; **G231'de silinmeli**.
  - Pasif avukatlar tablodan düşmeye devam ediyor (backend yalnız aktifleri döndürüyor), backend'e dokunulmadı.
- **Worktree (korunuyor):** `C:/dev/hukudok-wt/G229`
- **Önerilen sonraki adım:** `QuickCaseModal.lawyer.test.tsx` için test taşıma izni hakkında karar verilmeli.
  - İzin verilirse: `QuickCaseModal.tsx:66,143,202-208` küçük bir ek görevle temizlenir. Ardından `d4a7a64` denetlenip merge edilir.
  - İzin verilmezse: Kalem görev tanımından çıkarılır ve `d4a7a64` o hâliyle denetlenip merge edilir.

## Karar bekleyenler

- **SORU (G229):** QuickCaseModal'daki ölü `prefill.avukat_kodu` kaldırılsın mı? Üretimde bu alanı kullanan kod yok, ama `QuickCaseModal.lawyer.test.tsx:154-157` davranışı kilitliyor. Bu test dosyasının taşınmasına (değiştirilmesine) izin veriliyor mu, yoksa kalem görevden mi çıkarılsın?

## İzin engelleri

yok

## Atlananlar

- **G232** (docs): Bağımlılığı olan G229 bu koşuda tamamlanmadığı için atlandı. Worktree `C:/dev/hukudok-wt/G232` temizlenmedi. G229 kapanınca yeniden kuyruğa girer.
