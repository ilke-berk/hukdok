# Gece Kuyruğu (workflow) · 2026-09-27

## Özet

7 görev alındı · 4 işaretlendi · 2 bloke · 1 atlandı

Push/deploy yapılmadı. Hiçbir görevde merge yapılmadı (mergeYapildi=false). Tüm işaretlenen commit'ler main üzerinde, push'suz.

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G224 · Avukat envanteri + `--karsilastir` | backend | 2324cd3 | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (4 bulgu) | 2 tur (tur 1 mypy). "Düştüyse VE azaldıysa" iki ayrı İHLAL koşulu (VEYA) okundu; bağlı satır düşüşü de İHLAL. Lokalde 71/81 avukatın filtresi 0 dava buluyor. Fotoğraf konteyner /tmp'de (recreate'te silinir). |
| G225 · `lawyers.kimlik` AVK-00001 + silme→pasif + FK RESTRICT | backend | bb24b81 | geçti | GEÇTİ (5 bulgu) | 2 tur (tur 1 mypy). Lokal DB'de migrasyon 54: 81/81 AVK-00001..00081, envanter 0 İHLAL. İzlenecek: numara ortamın id sırasından doğar, prod'a gitmeden prod/lokal liste karşılaştırması (G231). |
| G226 · Belge hattı `lawyer_id` + ölü `avukat_kodu` artıkları + `belge_avukat_bagi.py` | backend | 894ef79 | geçti | GEÇTİ (3 bulgu) | **Sabah incelemesi:** kabul kriteri açıkça istediği için 8 mevcut test dosyası değişti (yalnız ad göçü, assert sayısı aynı, skip yok; liste G226.md Rapor'da). Envanter 0 İHLAL, 3 BİLGİ. **RİSK:** G226 ile G227 prod'a birlikte gitmeli. Yedek konteyner /tmp'de. Kapsam dışı: `docs/mimari/dava-acma-akisi.md:213,:233` eski imza. |
| G227 · Export `avukat_kimlik` + `avukat_adi` + `GET /export/lawyers` | backend | 31eb8dd | geçti | GEÇTİ (2 bulgu) | 2 tur (tur 1 ruff B905). nginx bekçisi konteynerde skip, host'ta 8 passed. Kimliği NULL avukat listelenmez. |

## Bloke

Aşağıdaki iki görev başarısızlık DEĞİL: **testi değiştirmeden geçilemedi, görev tanımı gözden geçirilmeli.** Hattın doğru çalıştığının kanıtıdır — işçi, görev metni ("kodu sabitleyen mevcut testler taşınır") ile işçi sözleşmesi ("mevcut testleri değiştirme") çelişince durdu.

Not: G226 aynı gerilimle karşılaşıp görev tanımındaki açık kriteri izin sayarak ilerledi; G228/G229 durdu. Bu tutarsızlık da sabah kararına dahil edilmeli.

### G228 · Avukat listesi kimlik ile yönetilir; kod eşlemesi kalkar (backend)

- **Durma sebebi:** test-değiştirmek-gerekti (tur 0, kod değişmedi, commit yok)
- **Son parmak izi:** yok (verify çalıştırılmadı)
- **Denenen yaklaşımlar:**
  - Ön ölçüm: lokal DB'de kart/duruşma/case_lawyers alanlarında kod biçimli değer 0 (veri engeli yok); envanter önce-fotoğrafı `/tmp/avukat_envanteri_once_G228.json`
  - Kabul kriterleri mevcut testlerle karşılaştırıldı: kod token eşlemesinin kaldırılması ve POST'ta kodun yok sayılması 9 mevcut testi kırıyor; geriye uyumlu tanımlayıcı yalnız bir kısmını kurtarır
- **Kök neden:** görev tanımı test taşımayı öngörüyor, işçi sözleşmesi yasaklıyor. Engelleyen testler:
  - `test_lawyer_resolver.py`: test_code_match, test_code_match_lowercase, test_duplicates_deduped, test_resolve_by_code, test_value_matches[AGH-True], test_free_text_fallback, test_duplicate_canonical_names_collapse
  - `test_g080_bildirim_hedefleme.py::test_avukat_kodu_ile_cozulur`
  - `test_g225_avukat_kimligi.py::test_route_post_yeni_avukata_kimlik_verir`
- **Worktree:** yok (ana repoda; `gorevler/gorev/G228.md` Rapor + DURUM: BLOKE yazıldı, commit'lenmedi)
- **Önerilen sonraki adım:** test taşıma izniyle yeniden aç ya da ikiye böl: (a) test kırmayan kimlik/filtre/rapor kısmı, (b) kod eşlemesinin kaldırılması + test taşıma.

### G229 · Arayüzden avukat kodu kalkar; Sil → Pasife al; CaseList filtresi kimlik (frontend)

- **Durma sebebi:** test-değiştirmek-gerekti (tur 0, commit yok)
- **Son parmak izi:** yok (verify çalıştırılmadı)
- **Denenen yaklaşımlar:**
  - Kod sütununu gizli tutup testi korumak: kabul "kod ekrana basılmaz" ile çelişir, reddedildi
  - `kimlik||code` yedeğiyle sıralama kimliği: sıralama testlerini korur ama sütun testlerini (column(1)=kod) kurtarmaz
- **Kök neden:** `AdminPage.listeler.test.tsx` kodu 1. sütunda sabitliyor; görev dosyası test değişikliğini öngörüyor, gece koşucu kuralı yasaklıyor.
- **Ek bulgular:**
  1. G225 sonrası genel `/api/config/delete` lawyers için clear/keep'i 422 ile reddeder; Pasife al için özel `DELETE /api/config/lawyers/{kimlik}` çağıran useConfig fonksiyonu gerekir.
  2. `get_items` yalnız active=True döndürür (`reference_lists.py:388`) → pasif avukat bugün tablodan düşer.
  3. Plan uyarısı: G229 G228 sözleşmesine dayanıyor; G228 bloke olduğundan sözleşme henüz yok.
- **Worktree:** `C:/dev/hukudok-wt/G229` (dal `gorev/G229`) korunuyor; G229.md Rapor değişikliği commit'lenmemiş.
- **Önerilen sonraki adım:** önce G228'i çöz; sonra gündüz onayıyla `AdminPage.listeler.test.tsx` beklentilerini ad sütununa ve `ordered_ids` kimlik dizisine taşıyarak yeniden koş.

## Karar bekleyenler

(teshis.gorevTanimiHatali=true olan görev yok; aşağıdakiler kabulKarsilanmayan maddelerinden.)

- **G228:** Test taşıma izni verilecek mi, yoksa görev ikiye mi bölünecek?
  - Sözleşme (kimlik ile CRUD, POST'ta kod yok sayılır) ne zaman uygulanacak?
  - Filtre `lawyer=<kimlik>` + ad eşlemesi güvencesi hangi görevde?
  - Resolver/bildirim kod token eşlemesinin kaldırılması (mevcut testler kodu sabitliyor) onaylanıyor mu?
  - Rapor kataloğu `avukat_kodu` → ad kolonu?
  - Envanter `--karsilastir` sonrası ölçümü değişiklikten sonra yapılacak.
- **G229:** "Avukat tablosunda kod ve kimlik sütunu YOK" maddesi mevcut testi değiştirmeden karşılanamaz — `AdminPage.listeler.test.tsx` taşınsın mı? Diğer kabul maddeleri uygulanmadı.
- **G226 (bilgi):** 8 test dosyası değişikliği sabah onayı bekliyor; işçi sözleşmesi ile görev kriteri çelişkisinin genel kuralı belirlenmeli.

## İzin engelleri

yok

## Atlananlar

- **G232** · Karar 022: kurumsal avukat kimliği AVK-00001 + CLAUDE.md maddesi (docs) — atlandı: bağımlılık bu koşuda tamamlanmadı (G228, G229). Worktree `C:/dev/hukudok-wt/G232` duruyor (temizlenmedi).

Tavan nedeniyle atlanan: yok. zincirHatasi / teslimHatasi: yok.
