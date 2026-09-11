# Gece Kuyrugu (workflow) · 2026-09-11

## Ozet

6 gorev alindi · 4 isaretlendi (G165, G176, G173, G174) · 1 bloke (G175) · 1 atlandi (G177)

Tavan nedeniyle atlanan: yok.

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G165 | backend | `0fa910f` | gecti (test temiz, kirmizi/yesil kanitlandi) | GECTI (3 bulgu) | Ana dizinde, 2 tur. 42 passed hedef dosya; tam pytest 3290 passed / 3 skipped; ruff + mypy temiz. `--apply` KOSULMADI (kullanici karari), yalniz kuru kosu. 11.09 olcumu 6.351/4.398 (gorevdeki 6.423/4.404'ten fark: TKU birlestirmesi 7beafc6'nin sildigi 184 kart). Tasarim: kuru kosu her adimi ayni transaction'da uygulayip sonda rollback yapiyor (psql ile DB'nin dokunulmadigi dogrulandi). Mevcut `test_adim_listesi_ayristirma` beklentisi gorev izniyle [0..6] yapildi. Gecici CSV dizini (`backend/C:/...`, Git Bash /tmp donusumu) silindi. Merge yok (ana dizin). |
| G176 | backend | `de2b72f` | gecti (test temiz, kirmizi/yesil kanitlandi) | GECTI (2 bulgu) | Ana dizinde, 1 tur. prompts.py'de TEYIT DONGUSU → hemen uygulanir; YAKLASIK AD (contains) + LISTE SORUSU maddeleri; test_g132'ye 2 yeni test. Hedef 65 passed; tam paket 3292 passed / 3 skipped; ruff + mypy temiz. Mevcut test beklentisi degistirme izni KULLANILMADI. Insan adimi: Gemini duman testi 3 istem (gorev raporunda). NOT: `docs/mimari/raporlama.md` satir 43 ve 411 hala G167 teyit dongusunu anlatiyor — kapsam disi, G174/G177 ile guncellenmeli. |
| G173 | frontend | `acfd215` | gecti (test temiz, kirmizi/yesil kanitlandi) | GECTI (4 bulgu) | Worktree `C:/dev/hukudok-wt/G173`, 2 tur. TanimSeridi + 14 test; tam paket 922 passed (72 dosya), lint 0, tsc -b --force 0. Merge YAPILDI, entegrasyon yesil, worktree temizlendi. Sayfaya baglanmadi (tasarim geregi; G175 isi). Git uyarisi: yeni dosyalar LF, autocrlf CRLF'ye cevirebilir. |
| G174 | frontend | `09c89c9` | gecti (test temiz, kirmizi/yesil kanitlandi) | GECTI (3 bulgu) | Worktree `C:/dev/hukudok-wt/G174`, 2 tur. Asistan otomatik uygulama + degerEsle + DegerListesi + onFiltreEkle; 945/945 yesil, lint + tsc temiz. Merge YAPILDI, entegrasyon yesil, worktree temizlendi. Test degisiklikleri (denetci onayli): AssistantBar.test.tsx'te G167 "UYGULANMAZ" beklentisi tasiyan 3 test yeni akisa gore yeniden yazildi (+8 yeni test); kapsam DISI `ReportsPage.favori.test.tsx`'te G167 onay adimini kodlayan 4 satir kaldirildi (planlayici kapsam listesinde eksik). ornekIstemler ucuncu ornek DEGISTIRILDI (test uclu sayiyi kilitliyor). |

## Bloke

### G175 — Sohbet oncelikli rapor ekrani yerlesimi (frontend)

- **Durma sebebi:** KAPI — test butunlugu ihlali. Kod ve testler yesil (verify: yesil, 3 tur), fakat kapi `gecti=false`.
- **Son parmak izi:** 916 passed (69 dosya), eslint temiz, tsc -b --force temiz. Commit `c7db935` dal `gorev/G175`.
- **Kapi ihlalleri (mekanik):**
  - Silinen test dosyasi: `frontend/src/components/reports/ColumnSheet.test.tsx` (286 satir)
  - Silinen test dosyasi: `frontend/src/components/reports/QuickFilters.test.tsx` (864 satir)
  - Silinen test dosyasi: `frontend/src/components/reports/SourceCards.test.tsx` (77 satir)
  - Net azalan `expect(` sayisi: diff'te silinen 407 > eklenen 134 (`git diff e79bb6b..gorev/G175`, frontend/ altinda)
- **Denenen yaklasimlar:**
  - Tur 1: ReportsPage yerlesimi + TemplateBar kompakt + dosya silme; tsc/lint yesil; ReportsPage.test yeniden yazildi → 16/18 (2 kirmizi: Durum listbox toggle ikinci tikta kapaniyor; cip govdesine tik acik popover'i kapatiyor).
  - Tur 2: test yardimcilarina aria-expanded/duzenleyici-acik kontrolu eklendi → ReportsPage.test 18/18.
  - Tur 3: asistan/sablon/favori testleri serit kimliklerine tasindi → 2 kirmizi (Guncelle/Sil menude; Sehir icerir girdisi popover'da) → beklentiler yeni yerlesime gore duzeltildi → 916/916.
- **Kok neden (teshis):** Kural mekanik: test dosyasi silme + net expect azalmasi otomatik ihlal. Ancak gorev dosyasi `gorevler/gorev/G175.md` (satir 8, 49, 88, 93) bu bilesenlerin (SourceCards/QuickFilters/ColumnSheet) ve testlerinin kaldirilmasini ve sayfa testlerinde beklenti degisikligini ACIKCA istiyor. `.skip/.only/.todo`, `@ts-ignore/eslint-disable`, gevsetilmis beklenti, vitest.config/package.json degisikligi YOK. Yani bu, hattin dogru calistiginin kanitidir: **testi degistirmeden/silmeden gecilemedi; gorev tanimi ile kapi kurali celisiyor, nihai karar insanin.** Basarisizlik degil.
- **Denetim:** yapilmadi (kapi gecmedigi icin). Merge yapilmadi, entegrasyon uygulanamaz.
- **Worktree:** `C:/dev/hukudok-wt/G175` KORUNUYOR (dal `gorev/G175`, commit `c7db935`).
- **Kapsam disi notlar (gorev raporunda):** `docs/mimari/raporlama.md` §8.1-8.3 ve kaynak tablosu hala eski bilesenleri anlatiyor (docs gorevi = G177); `FilterControl.tsx:65` yorumu bayat; PreviewTable basligindaki "N kayit · M kolon" rozeti (dokunma listesinde) sayac satiriyla iki kez gorunuyor (kucuk temizlik gorevi). Tarayici dumani yapilmadi. Plan uyarisi: `sheet.tsx` silinmeden once baska kullanici grep ile dogrulanmali (gorev sarti) — raporda bu dogrulamanin yapilip yapilmadigi acikca yazilmamis, insan denetiminde bakilmali.
- **Onerilen sonraki adim:** Insan `git diff e79bb6b..gorev/G175 --stat` ile silinen 3 test dosyasinin gorev tanimindaki kaldirma istegiyle birebir ortustugunu ve `sheet.tsx` grep sartini dogrular; uygunsa kapiyi elle gecerek `/gorev-denetle G175` koşturur, sonra merge + worktree temizligi. Ardindan G177 (docs) serbest kalir.

### Testi degistirmeden gecilemedi, gorev tanimi gozden gecirilmeli

- **G175:** yukaridaki gibi — test dosyasi silme gorev taniminin kendisi; kapi kurali gorev tanimiyla catisiyor. Gelecekte bu tur "bilesen kaldirma" gorevlerine bastan "test dosyasi silme izni" / kapi muafiyeti yazilmali (bkz. raporlama modulu dersi: test-kilidi kaldiran gorevlere bastan izin yaz).
- **G174 (isaretlendi, bilgi):** kapsam disi `ReportsPage.favori.test.tsx` beklentisi minimal degistirildi; planlayici kapsam listesinde eksikti. Denetim GECTI, ama ayni ders gecerli.

## Karar bekleyenler

- `teshis.gorevTanimiHatali=true` olan gorev: yok.
- `kabulKarsilanmayan` maddesi: yok.
- Insan karari gerektiren:
  - **G175:** Silinen 3 test dosyasi (ColumnSheet/QuickFilters/SourceCards, toplam 1.227 satir) ve net expect azalmasi (407 → 134) gorev taniminin istedigi bilesen kaldirmasi olarak KABUL EDILIYOR MU? Kabulse kapi elle gecilip denetim + merge yapilacak.
  - **G175:** `sheet.tsx` silinmeden once "baska kullanici yok" grep dogrulamasi (gorev sarti) yapildi mi? Rapor bunu acikca belirtmiyor.
  - **G174:** Kapsam disi `ReportsPage.favori.test.tsx` degisikligi (G167 onay adimi 4 satir) onaylaniyor mu? (Denetim GECTI; bilgi amacli.)
  - **G176 insan adimi:** Gemini duman testi 3 istem (gorev raporunda) koşulacak mi?
  - **G165:** `--apply` kosulmadi (10.09 karari). Adim 0 sonrasi adim 2'de 57 satir / 32 tekil G164 nokta ikizi aciga cikiyor — apply karari verilecek mi?
  - **G177:** G175 bloke oldugu icin atlandi; G175 karari sonrasi yeniden kuyruga alinacak mi? (docs/mimari/raporlama.md hem G175 yerlesimi hem G176 teyit dongusu acisindan bayat.)

## Izin engelleri

yok (G165, G176, G173, G174, G175, G177 — hicbirinde izinEngelleri listesi dolu degil).

## Atlananlar

- **G177** (docs): atlandi — "bagimlilik bu kosuda tamamlanmadi: G175". Uygulanmadi, commit yok, tur 0. Worktree `C:/dev/hukudok-wt/G177` olusturulmus ve temizlenmemis (`worktreeTemizlendi=false`); is yapilmadigi icin silinebilir. Kapsaminda G169-G172 dosyalarinin `git mv` ile arsive tasinmasi var; BLOKE'li satirlar KUYRUK'ta kalir.
- zincirHatasi: yok. teslimHatasi: yok.

## Koşu notlari

- `.claude/settings.local.json` (M) ve `.claude/launch.json` (??) kosu basinda kirliydi; harness dosyalari, hicbir commit'e alinmadi.
- Push/deploy yapilmadi. Prod hala main 700a806 (Deploy #23); bu kosunun 4 commit'i (0fa910f, de2b72f, acfd215, 09c89c9) yalniz lokal main'de.
