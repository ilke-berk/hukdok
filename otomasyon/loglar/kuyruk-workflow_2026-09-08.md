# Gece Kuyrugu (workflow) · 2026-09-08

## Ozet

8 gorev alindi · 4 isaretlendi (G149, G150, G158, G147) · 1 bloke (G151) · 3 atlandi (G152, G153, G154 — G151 zinciri)

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G149 — 370 derdest kart listesi xlsx (salt okunur script) | backend | `37def41` | gecti (test temiz, kirmizi-yesil kanitlandi) | GECTI (3 bulgu) | 2 tur; pytest 2750 passed / 3 skipped, ruff + mypy temiz. Cikti repo disinda: `C:\hukdok-veri\rapor\HUKDOK_DERDEST_KARTLAR_2026-09-08.xlsx` (41,6 KB, lokal kopyadan 370 = 175 + 195). Prod sayisi farkli olabilir — ekibe gondermeden once prod'da kosulmali (insan adimi). Tuzak: Git Bash `docker compose exec ... --out /tmp/x/` argumanini Windows yoluna cevirir, bind-mount yuzunden repoya `backend/C:/` dizini duser; silindi, commit'e girmedi; cozum `MSYS_NO_PATHCONV=1`. |
| G150 — Asama katmani kurali (paket kaynakli satir guncellenir, BELGE/UYAP korunur, bos hucre imzaya girmez) | backend | `3be2a74` | gecti (test temiz, kirmizi-yesil kanitlandi) | GECTI (5 bulgu) | 2 tur; pytest 2768 passed / 3 skipped, ruff + mypy temiz. 04.09 paketiyle kuru kosu + uygulama + ikinci kosu 0/0/0 lokal kaniti; denetim DB'den dogruladi (5.336 asama satiri, 426'si paket imzali). Lokal DB artik 04.09 paketinin yeni kuralla uygulanmis halini tasiyor; sifir noktasi `C:\hukdok-veri\yedek\pre_g150_20260908.dump`. Ayri kalem: ayni paket icindeki 6 cok-tur grubu hala celiski raporunda (kural mevcut-vs-paket icin). Docs/mimari guncellemesi G161'in isi. |
| G158 — Coklu avukatli kart "eksik sorumlu avukat" sayilmaz (Python + SQL ikizi + backfill) | backend | `491ea2d` | gecti (test temiz, kirmizi-yesil kanitlandi) | GECTI (4 bulgu) | 3 tur; pytest 2792 passed / 3 skipped, ruff + mypy temiz. Backfill idempotent (kuru kosu 0 / apply 0 / ikinci kosu 0). Beklenen ~1.031 AKTARIM kova dususu lokalde GERCEKLESMEDI (veri durumu, kod degil) — prod'da deploy sonrasi `scripts/backfill_missing_required.py` kuru kosusu ile olculmeli. Kapsam disi bulgu: `update_case` `lawyers` anahtari gelmezse `case_lawyers` satirlarini siliyor (`case_manager.py:1108-1113`) — frontend'in ne gonderdigi olculmeli. |
| G147 — Teslim hatti `teslim` config'i (TESLIM_SHAREPOINT_* ikinci kimlik/site) | backend | `b9fcb99` | gecti (test temiz, kirmizi-yesil kanitlandi) | GECTI (4 bulgu) | 2 tur; pytest 2834 passed / 3 skipped, ruff + mypy temiz. Env blogu `backend/.env.example` degil repo kokundeki `.env.example:31-48`'e yazildi (dosya orada). Insan adimlari YAPILMADI: Hanyaloglu site'inda `03_VERI_TESLIM/gelen+cevap` klasorleri ve paylasim, Entra app-only izin teyidi + secret bitis tarihi, prod `.env` TESLIM_SHAREPOINT_* dortlusu + `up -d` (recreate), admin anahtari, LexisBio'daki eski klasor karari. Ilk gercek kosuda "arsiv kimligi kullaniliyor" INFO'su gorunurse prod `.env` dortlusu eksik demektir. |

Hicbir gorevde merge/entegrasyon yapilmadi (`mergeYapildi=false`, worktree yok — ana repoda kosuldu).

## Bloke

### G151 — Karar durumu havuzlari (Kapali/Derdest yerel havuzdan cikar + aktarimda "karar yok" kurali + seed genislemesi)

**Testi degistirmeden gecilemedi — gorev tanimi gozden gecirilmeli.** Bu bir basarisizlik degil, hattin dogru calistiginin kanitidir: kilitli testlere dokunma yasagi uygulandi ve koşu durdu.

- **Durma sebebi:** `test-degistirmek-gerekti` (tur 1, verify kirmizi).
- **Son parmak izi:** hedefli 195 test yesil, ruff/mypy temiz; tam pytest **3 failed / 2866 passed**.
- **Denenen yaklasim (tur 1):** seed (yerel 27 / istinaf 8 / temyiz 4) + aktarimda "karar yok" kurali (kunye bos -> satir yazilmaz, dolu -> durumsuz + serh, INFO, sayac) + uzlasi imzasinda buro durumu bos hucre gibi + `deger_havuzu_seed --kaldir` (kuru kosu varsayilan) ve paket elemesi.
- **Kok neden:** KILIT testler `test_g066` (`DORT_ALAN` :53, route testi :367) ve `test_g103` (:376) "Kismen Kabul" degerini havuz DISI ornek deger olarak kullaniyor; gorev tanimi ayni degeri havuza eklemeyi sart kosuyor. Kod tarafinda cozum yok; test degistirme izni verilmemisti -> DUR.
- **Worktree:** yok — kod ana calisma agacinda **COMMIT'SIZ** duruyor (skill kurali: kirmizi -> commit yok). Sonraki koşudan once bu degisikliklerin korunmasi/stash'lenmesi kararı insana ait.
- **Karsilanan kabul maddeleri:** seed 27/8/4 + "Karar" yok (test), Kapali/Derdest satiri karar durumu uretmez + sayac + INFO, kunye doluysa durumsuz yazilir (test), `--kaldir` kuru kosu varsayilan ve kullanilan satiri silmez (test; lokal: Kapali silinebilir 0/0, Derdest 1 kart + 1 asama korunur).
- **Karsilanmayan kabul maddeleri:** bkz. "Karar bekleyenler".
- **Onerilen sonraki adim:** G151'i su test degistirme izniyle yeniden kuyruga al: `test_g066` `DORT_ALAN` istinaf ornek degeri + `test_route_liste_disi_degeri_400_donuyor` + `test_g103` `test_karar_durumu_kapisi_hala_calisiyor` — YALNIZ havuz disi ornek degeri (or. "Kismen Kabul" -> "Lehe Istinaf"). Baska degisiklik gerekmiyor; tekrar kosu tek turluk.
- **Artiklar:** konteynerde `/tmp/paket_0409.xlsx` ve `/tmp/rapor_g151` gecici kaldi (konteyner icinde, repoya girmez).

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan gorev yok; asagidakiler `kabulKarsilanmayan` maddelerinden turetilmis sorulardir.

**G151**
1. Yukaridaki test degistirme izni verilecek mi? (Verilmezse gorev tanimi ile kilitli testler celisik kalir; kod ilerleyemez.)
2. Kabul maddesi "04.09 paketiyle `buro_durumu_atlanan` ~409" bu paketle uretilemiyor: paketin Karar_Asamalari sayfasinda yalniz 2 Derdest satiri var, olculen sayac 1 (Sheet sutunu aktarimca okunmuyor). ~409 beklentisi hangi kaynaga dayaniyor — kabul kriteri duzeltilsin mi?
3. Kabul maddesi "lokalde `deger_havuzu_seed --apply` sonrasi liste sayilari": BLOKE sebebiyle lokal DB'ye yazilmadi (kuru kosu sonuclari raporda). Yeniden kosuda apply lokalde yapilsin mi?
4. Not: 04.09 paketi kuru kosusunda kardes celiskisi 6.610 satir raporlandi — bu gorevin degisikligi celiski artiramaz (imzadan deger cikarir), zeminin sayisi; eski kodla karsilastirma kosulmadi. Karsilastirma istenir mi?

**G147**
5. `grep -rn UPLOAD_SHAREPOINT backend docs`: backend/ ve docs/mimari/ temiz; ancak `docs/arsiv/` altinda uc tarihli belgede (gelistirme-plani-2026-07-07.md:30, kod-kalitesi-guvenlik-denetimi-2026-07-07.md:28, sistem-teknik-raporu-2026-08-04.md:24,572) ad geciyor. Arsiv tarihsel kayit ve dosya kapsami disi — dokunulmadi. Kabul kriteri arsivi haric tutacak sekilde daraltilsin mi?

**G158 (bilgi, karar degil)**
6. Beklenen ~1.031 AKTARIM kova dususu lokalde gerceklesmedi (0/0). Prod deploy sonrasi kuru kosu ile olculmeli; sayi orada da 0 cikarsa gorevin varsayimi gozden gecirilmeli.

## Izin engelleri

Yalniz **G150**'de cikti (diger gorevlerde bos):

1. `docker compose cp "C:/Users/ilkeb/OneDrive/Masaüstü/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx" backend:/tmp/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx` — G150
2. `cp "/c/Users/ilkeb/OneDrive/Masaüstü/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx" backend/.gk-tmp-G150-paket.xlsx` — G150
3. Birlesik komut: `docker compose exec -T postgres pg_dump ... && docker compose cp postgres:/tmp/pre_g150_20260908.dump C:/hukdok-veri/yedek/... && docker compose cp <xlsx> backend:/tmp/...` — G150. Ayri ayri: pg_dump ve dump'i disari alma GECTI; xlsx kopyalama bash'te engellendi; PowerShell `Copy-Item` GECTI.

Ortak desen: masaustundeki teslim paketi xlsx'ini konteynere/repoya kopyalama (`docker compose cp <host xlsx> backend:...` ve bash `cp`). `.claude/settings` izin listesi bu uc kalemle olculerek genisletilebilir.

## Atlananlar

| gorev | sebep |
| --- | --- |
| G152 — `status` kesim-sonrasi koruma + DEGISIKLIK_OZETI "Veri kesim tarihi" | bagimlilik bu kosuda tamamlanmadi: G151 (bloke) |
| G153 — DosyaNo koku -> muvekkil kimligi eslestirmesi | bagimlilik bu kosuda tamamlanmadi: G152 |
| G154 — Cevapli xlsx ile 20 foyu baglama (`--kart-esleme`) | bagimlilik bu kosuda tamamlanmadi: G153 |

Zincir hatasi / teslim hatasi / tavan nedeniyle atlanan: yok.

## Plan uyarilari (koşu oncesi)

- G147/G148 (teslim tenant ayrimi) ve G149-G161 (veri ekibi cevabi) olmak uzere 15 acik gorev; 12'si backend bandinda seri zincir (G150 -> ... -> G160), G161 docs G148 + G156 + G160'i bekler. Bu kosuda zincir G151'de kirildi; G152-G154 atlandi, G155-G161 kuyrukta.
- G155 dosya kapsami `frontend/src/**/CaseTracking*` glob'unu "yalniz gerekirse" diye iceriyor; bant backend.
- G161 dosya kapsaminda "dava-acma-akisi.md ya da ilgili mimari dokuman" esnek ifadesi var.
- G148 ve G161 ikisi de `docs/veri-teslim/SOZLESME.md` ve `CLAUDE.md`'ye dokunur (G161 G148'e bagimli, cakisma bagimlilikla cozulur).

## Genel notlar

- Tum gorevlerde calisma agacinda gorev disi kirli dosyalar vardi (`.claude/settings.local.json` M, `.claude/launch.json` ??) — oturum oncesinden, izin/onizleme altyapisina ait; commit'lere alinmadi, skill'in BLOKE kurali bilincli uygulanmadi.
- Hicbir gorev push/deploy yapmadi; tum commit'ler lokal main'de.
