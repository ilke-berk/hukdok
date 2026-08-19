# Gece Kuyrugu (workflow) · 2026-08-19

## Ozet
2 gorev alindi · 2 isaretlendi · 0 bloke · 0 atlandi

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G063 — case_foys: SistemNo → kart+müvekkil föy eşleme tablosu | backend | `bfffcfa` | GECTI (test temiz, kirmizi→yesil kanitlandi, ihlal yok) | GECTI (2 bulgu) | 2 tur; son parmak izi: pytest 1368 passed / 3 skipped, ruff temiz, mypy Success (41 dosya). Lokal DB'de migrasyon canli kosturuldu (tablo + 4 index dogdu, acilis 0 ERROR). Push/deploy YAPILMADI. |
| G064 — Aktarim yazma yolu cekirdegi: idempotent iskelet + kuru kosu + belge envanter denkligi | backend | `f0bf06e` | GECTI (test temiz, kirmizi→yesil kanitlandi, ihlal yok) | GECTI (6 bulgu) | 3 tur; son parmak izi: pytest 1432 passed / 3 skipped, ruff temiz, mypy Success (42 dosya). CLI duman testi gercek lokal DB'ye karsi YALNIZ `--dry-run`; kosu sonrasi sayimlar degismedi (14345/229/6/0). Push/deploy YAPILMADI. |

Her iki gorevde de `mergeYapildi=false`, `entegrasyon=uygulanamaz`, worktree kullanilmadi
(ikisi de ana dizinde, seri backend zinciri).

### G063 — teknik notlar
Uc isci keskinlestirmesi taslaga eklendi ve gorev dosyasinda gerekcelendirildi:
1. `sistem_no` KIRPILMAZ, reddedilir — kirpma iki farkli foyu UNIQUE altinda tek satira cokertirdi.
2. `Case.foys` iliskisi `passive_deletes="all"` — yoksa ORM, kart silinirken cocugun NOT NULL
   FK'sini NULL'lamaya kalkardi; karar tamamen DB'de.
3. `None` = "bu teslimde yok" (bosalt degil). Tek istisna: kart degisiminde eski taraf baginin
   dusurulmesi (WARNING'li).

`idx_case_foys_case` ve `idx_case_foys_case_party` G043 bekcisi (index'siz FK kolonu kalmaz)
geregi zorunluydu.

Kapsam disi kirli dosyalar (`.claude/settings.local.json` modified, `.claude/launch.json`
untracked) OTURUM BASINDAN beri vardi — harness'in kendi konfig dosyalari, dokunulmadi,
commit'e girmedi.

### G064 — teknik notlar
Kapsam disi TEK dokunus: `backend/scripts/README.md`'ye yeni scriptin envanter satiri
(script envanteri o dosyada yasiyor; CLAUDE.md "is = kod + test + dokuman").
`import_excel_cases.py` DEGISTIRILMEDI — README satirinda yalniz "kullanilmaz" serhi var,
diff'te dosya yok.

Gercek teslim paketi repoya girmedi; testler openpyxl ile sentetik mini paket uretiyor.
dbtest yazimlari dis transaction'la geri alindi.

Yesil sonrasi ek olcum: gercek DB'ye karsi CLI duman testi `klasor_no_2`'nin cok degerli
oldugunu gosterdi (14.317 dolu kaydin 1.267'si `;` ile birlesik = birlesik kartlar).
Kopru iki tarafta da parcalanacak sekilde duzeltildi + 6 yeni test.

## Bloke
Bloke gorev yok. Iki gorev de `bloke=false`, `durmaSebebi="yesil"`.

Yine de tanilama degeri olan ara duraklar (hepsi ayni kosuda cozuldu, hicbiri gorevi durdurmadi):

- **G063 / sistem_no uretimi (tur 1):** f-string ile uretilen `sistem_no`'lar yanlisti
  (`SSTMN-71810`). Kok neden: uretim ifadesi beklenen numaralari birlestiriyordu. Cozum: acik
  liste (7189, 7190, 7191, 7192) + `zip`.
- **G063 / ruff B905:** `zip()` `strict=` olmadan cagriliyordu → `zip(..., strict=True)`,
  tur 2 temiz.
- **G063 / dbtest SKIP:** ilk kosuda testler "sema gocmemis" diye atlandi. Kok neden:
  migrasyon lokal DB'de henuz kosmamisti. Cozum: `docker compose restart backend` ile
  `migrate.py` kosturuldu (bind-mount), tablo + 4 index dogdu, 5 dbtest gercekten KOSTU.
- **G063 / kart hard-delete testi yanlis sebeple yesil:** test `_kart_ve_taraf` kullaniyordu;
  `case_parties` FK'si de 23503 verdigi icin test dogru sebebi olcmuyordu. Cozum: yalniz kart
  yazan `_kart` yardimcisina cevrildi + hata mesajinda `case_foys` arandi.
- **G064 / pysqlite SAVEPOINT (tur 1, 3 kirmizi):** parmak izi
  `test_dry_run_hicbir_tabloya_yazmaz`, `test_belge_bagi_koparsa` (AssertionError: rollback
  yazilanlari geri almadi), `test_alan_degisikligi` (MultipleResultsFound). Kok neden: pysqlite
  SAVEPOINT'ten once bekleyen transaction'i ortuk COMMIT ediyor. Cozum: SQLAlchemy'nin
  belgeledigi pysqlite recetesi (`isolation_level=None` + elle BEGIN) fixture'a eklendi.
- **G064 / test_no_basicconfig_left_in_backend (tur 2):** `scripts/hukdok_aktarim.py` icinde
  `logging.basicConfig`. Cozum: merkezi `logging_setup.configure_logging` cagrildi — **test
  degistirilmedi**.

## Testi degistirmeden gecilemedi
Bu kosuda boyle bir kalem YOK. G064 tur 2'de tek bir test (`test_alan_degisikligi` /
tarihce beklentisi) duzeltildi, ancak bu testin kendi hatasiydi (ilk kosu da tarihce
yaziyordu, test tek satir bekliyordu) — uretim davranisi degismedi. G064 tur 3'teki
`basicConfig` bulgusunda kapi dogru calisti: test korundu, uretim kodu duzeltildi.

## Karar bekleyenler
Yok. Hicbir gorevde `teshis.gorevTanimiHatali=true` yok; `kabulKarsilanmayan` her iki
gorevde de bos.

Insan karari bekleyen tek konu operasyoneldir, teshis degil: **her iki commit de yalniz
lokalde** (`bfffcfa`, `f0bf06e`). Push ve deploy YAPILMADI — sabah insan karari.

## Izin engelleri
Yok. (G063 ve G064'un `izinEngelleri` listeleri bos.) `.claude/settings` izin listesi bu
kosudan olculen bir genisletme gerektirmiyor.

## Atlananlar
Yok. Tavan nedeniyle atlanan gorev yok; `atlandi`, `zincirHatasi`, `teslimHatasi` alanlari
her iki gorevde de bos.

## Plan uyarilari
- G063 ve G064 seri zincirdi (ikisi de backend bandi); G064 G063'u bekledi — gercek
  paralellik yoktu.
- Kosu baslangicinda HEAD: `d6a01bb` (chore: gece kuyrugu raporu 2026-08-18).
