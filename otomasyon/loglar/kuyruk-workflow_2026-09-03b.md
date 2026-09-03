# Gece Kuyrugu (workflow) · 2026-09-03b

## Ozet

2 gorev alindi · 2 isaretlendi · 0 bloke · 0 atlandi

Tavan nedeniyle atlanan: yok. Plan uyarilari (koşu oncesi): G113 icin gorev dosyasinin Rapor bolumunde onceki geceden "DURUM: BLOKE" kaydi vardi; 03.09 sabahi kullanici karariyla cozuldu (HEAD c4971b2, test_g063 kolon kilidi guncellendi) ve koşuda test degistirilmeden yesile dondu. G114 G113'e bagimli oldugu icin G113 sonrasinda koştu.

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G113 — Silinen_Föyler / Kapsam_Dışı → case_foys kapsam işareti | backend | `75b1c30` | gecti (test temiz, kirmizi-yesil kanitlandi) | GECTI (3 bulgu, denetim2 yok) | 1 tur; pytest 2325 passed / 3 skipped, ruff + mypy temiz. Migration idempotency lokal Postgres'te iki koşuyla kanitlandi. mergeYapildi=false, worktree yok (ana repoda kosuldu). Frontend rozeti sonraki tur. |
| G114 — veri-teslim-hatti.md + SOZLESME.md + genel-bakis/README/CLAUDE.md düzeltmeleri | docs | `5ba94a4` (+ onarim `29a0054`) | gecti (kirmizi-yesil uygulanamaz, docs) | 1. denetim RET → onar 4/4 → 2. denetim GECTI | 2 tur; 248 dosya:satir referansi tarandi, 0 hata. mergeYapildi=true, entegrasyon uygulanamaz, worktree `C:/dev/hukudok-wt/G114` temizlendi. |

### G114 denetim RET → onarim ayrintisi

Ilk denetim SOZLESME.md:30'daki iddiayi reddetti: `DEGISIKLIK_OZETI` sayfasi "Zorunlu" ve "sayfa yoksa otomatik uygulanmaz" diye yazilmisti; kod (`teslim_kutusu.py:784-786` zincir_tamam=None, `:846` kapi yalniz `is False`) sayfasiz paketi 04:00'te otomatik uygulayabiliyor — veri ekibine verilen sozlesmede koddan dogrulanmamis, guvenlik acisindan yaniltici iddia. Onarim commit'i (`29a0054`) sayfayi "istege bagli", zincir_tamam=NULL "kapiyi durdurmaz" olarak duzeltti; ikinci denetim kod satirlarina karsi dogruladi ve GECTI.

### G113 yorum kararlari (raporda)

1. `case_relations_auto` "Dokunma" listesindeydi; "yalniz filtre ekle" izniyle iki sorguya `kapsam_durumu IS NULL` eklendi, algoritmaya dokunulmadi.
2. Ayni pakette hem Sheet'te hem kapsam sayfasinda olan foy: kapsam sayfasi kazanir, Sheet satiri yalniz foy kimligi yazar — kabul kriterindeki "celiski 0" ancak bu yorumla anlamli.
3. `get_case`'e `foyler[]` eklenirken selectinload yerine joinedload: G051 kilidi (kart 6 sorgu) korunuyor.
4. `foy_map.py` dosya kapsami disinda oldugu icin kapsam kolonlari script icinde ORM satirina dogrudan yaziliyor; ileride `foy_map.set_kapsam` cikarilabilir (NOT).
5. Migration idempotency testi sqlite'ta yazilmadi (runner `CREATE EXTENSION pg_trgm` ERROR logu uretir); kanit lokal Postgres'te iki koşu.

## Bloke

Bloke gorev yok.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan gorev yok; `kabulKarsilanmayan` iki gorevde de bos. Yine de raporlardan cikan, insan karari gerektiren maddeler:

- **G113 / kapsam suzgeci disinda kalan okuyucular:** `mukerrer_kart_raporu.py` ve `teslim_cevap.py` kapsam suzgecsiz okuyor (kapsam disi NOT). Bunlar ayri bir gorev olarak acilsin mi?
- **G113 / frontend rozeti:** kapsam disi foy rozeti frontend'de yok — sonraki tur icin gorev acilsin mi?
- **G114 / plan kapatilmadi:** veri-teslim plani §7 kabul kriterleri prod'da gozlenmedi. Acik kalanlar (§8): `POST /api/admin/aktarim/tara` hala yer tutucu (G109 NOT'u, kucuk ayri gorev); prod kurulumu insan adimi (SharePoint klasorleri + `.env SHAREPOINT_FOLDER_TESLIM_NAME` + recreate + admin anahtari); ilk teslim elle uygulanir. Bunlar ne zaman ele alinacak?
- **G114 / SOZLESME §7:** "HukuDok tarafi size haber verir" cumleleri kod degil ekip taahhudu — veri ekibine iletmeden once insan gozu gerekiyor. Iletilsin mi, degistirilsin mi?
- **G114 / CLAUDE.md dokuman haritasi:** yeni `docs/veri-teslim/` klasoru dokuman haritasi tablosuna eklenmedi (kapsam yalnizca mimari ozet paragrafi). Tabloya satir eklensin mi?
- **G114 / kaymis referanslar:** genel-bakis/belge-isleme-hatti'nin dokunulmayan bolumlerindeki bazi `api.py` referanslari (PROCESS_CACHE api.py:210-218, healthz api.py:444) G085/G109 sonrasi kaymis olabilir — ayri dokuman turu gorevi acilsin mi?

## Izin engelleri

yok

## Atlananlar

Atlanan / zincir hatasi / teslim hatasi olan gorev yok.
