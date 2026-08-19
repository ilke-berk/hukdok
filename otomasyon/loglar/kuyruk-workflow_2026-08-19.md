# Gece Kuyrugu (workflow) · 2026-08-19

## Ozet
2 gorev alindi · 2 isaretlendi · 0 bloke · 0 atlandi (tavan nedeniyle atlanan: yok)

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G067 — Mahkeme adi icin yapisal kimlik kapisi (`services/court_name.py`) | backend | `cffc130` | GECTI (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI — 4 bulgu | `CourtName`'e iki yuzey alani eklendi (`tur_yuzey`, `daire_yuzey`); ust mahkeme damgasi gorev tanimina uyularak KISMI birakildi; `find_court_name` sozlesmesi permissive kaldi, siki kapi yeni `find_court_identity` |
| G068 — Analiz hattinda mahkeme adi: guven kilidi + LLM capraz kontrolu + BELIRSIZ | backend | `a31cea6` | GECTI (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI — 5 bulgu | TAM guvende capraz kontrol yapilmaz (kilitli deger bagimsiz okuma degil); regex `GUVEN_YOK` yuzeyi dogrulanmis okuma yoksa korunur; JSON semasi genislemedi |

Son parmak izi (G068): `1538 passed, 3 skipped (88.9 s) | ruff All checks passed | mypy Success (43 dosya)`.

Iki gorevde de `mergeYapildi=false`, worktree kullanilmadi (ana repoda calisildi), `worktreeTemizlendi=false`.

## Bloke
Yok — bu kosuda hicbir gorev blokede durmadi.

## Testi degistirmeden gecilemedi (hattin dogru calistiginin kaniti)
Bu kosuda boyle bir durum olusmadi. Bununla birlikte G068'de mevcut testin kapiyi tuttugu bir an yasandi ve **test degistirilmeden** cozuldu:

- On cikarimda `find_court_name` yerine `find_court_identity` cagirmak
  `test_g067_court_name.py::TestGeriUyum::test_analyzer_cagrisi_degismedi` testini kirmiziya dondurdu
  (test analyzer'in cagri satirini kilitliyor).
- Cozum: cagri korundu; kimlik, uretilen duz adin ayni kapidan (`_court_ayristir` / `parse_court_name`)
  yeniden ayristirilmasiyla alindi. Kayipsizlik 8 ornekle (TAM/KISMI/YOK, daireli/dairesiz, bilesik yer)
  olculdu; tam suite yesil.

## Karar bekleyenler
`teshis.gorevTanimiHatali=true` isaretli gorev yok; `kabulKarsilanmayan` her iki gorevde de bos.
Rapor edilen bulgular tasarim sonucu ve raporlama duzeyinde. Insan karari icin acik kalan izleme maddeleri:

- SORU (G067, kapsam disi birakildi): `judicial_unit.PATTERNS` icinde `YARGITAY` kanonik degeri yok ve
  `HUKUK DAIRESI` alternatifi Yargitay dairelerini `BOLGE ADLIYE MAH. HUKUK DAIRESI`'ne yaziyor. Yeni kapi
  bunu ust mahkeme daliyla asiyor ama `cases.judicial_unit` turetmesi hala eski yoldan geciyor.
  Ayri gorev acilsin mi?
- SORU (G067): Yargi yeri sozlugu bilincli olarak modulde sabit. Panele tasima ayri gorev olarak
  kuyruga girsin mi?
- SORU (G068): TAM guvende capraz kontrol yapilmadigi icin "yer celiskisi" dali uretimde bugun
  erisilemez durumda; yalniz birim testiyle kilitli. Bu tasarim kalici kabul edilsin mi?
- SORU (G068): Guven damgasinin UI'da gosterimi kapsam disi birakildi — ayri frontend gorevi acilsin mi?

## Izin engelleri
Yok — her iki gorevin de `izinEngelleri` listesi bos. (`.claude/settings` izin listesi bu kosudan
olculecek bir genisletme gerektirmiyor.)

## Atlananlar
Yok — `atlandi`, `zincirHatasi`, `teslimHatasi` alanlari her iki gorevde de bos.

## Plan uyarilari
- HEAD: `12dd7b4` (chore: kuyruk - G067+G068 yazildi)
- G067 ve G068 seri backend bandinda: G068 G067'ye bagimli, gercek paralellik yok.
- Calisma agacinda gorev oncesinden kirli olan `.claude/settings.local.json` (M) ve
  `.claude/launch.json` (??) kapsam disi birakildi, dokunulmadi ve commit'lere girmedi.
