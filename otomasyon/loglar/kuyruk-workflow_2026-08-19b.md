# Gece Kuyrugu (workflow) · 2026-08-19b

## Ozet

2 gorev alindi · 2 isaretlendi · 0 bloke · 0 atlandi.

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G069 — judicial_unit ust mahkeme boslugu (Yargitay daireleri Bolge Adliye'ye yaziliyor) | backend | `6ce04e9` | GECTI (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI (5 bulgu) | 2 tur; cift kanonik deger (YARGITAY HUKUK DAIRESI / YARGITAY CEZA DAIRESI) secildi; kapi: 1575 passed / 3 skipped, ruff+mypy temiz |
| G070 — Yargi yeri sozlugunu kendi verimizden kapat (166 KISMI deger) | backend | `8151d13` | GECTI (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI (4 bulgu) | 1 tur; 22 gercek yargi yeri eklendi; kapi: 1601 passed / 3 skipped, ruff temiz, mypy Success (43 dosya) |

Merge/entegrasyon alanlari her iki gorevde de bos (`mergeYapildi=false`, worktree yok) —
gorevler ana agacta seri kosuldu.

## Bloke

Bu kosuda bloke gorev yok.

## Karar bekleyenler

Hicbir gorevde `gorevTanimiHatali` isaretlenmedi; insana yoneltilmis dogrudan soru yok.
Karsilanmayan tek kabul maddesi asagida SORU olarak duruyor.

**SORU (G069):** Kanonik ad birebir `YARGITAY` yapilsin mi?
Uygulanan cozum `YARGITAY HUKUK DAIRESI` / `YARGITAY CEZA DAIRESI` cift degeri.
Gerekce: `judicial_unit` her degeri TEK `parent_code` tasir, Yargitay hem hukuk hem ceza
dairesi barindirir — kardes kurum Bolge Adliye de bu yuzden iki degerlidir. Ayrica birebir
`YARGITAY` degeri, Dokunma listesindeki
`test_g067_court_name.py::test_ikinci_kopya_yok` kilidini kirar (olculdu: kesisim
`{DANISTAY, YARGITAY}` olurdu). Tek `YARGITAY` isteniyorsa o testin izin kumesi
`{DANISTAY, YARGITAY}` yapilmali ve `court_name.py:76` yorumu duzeltilmeli — bu ayri bir
karar/gorev.

**SORU (G070, bilgi):** Gorev dosyasindaki ONERI olan "tekil degerlerin >=%95'i TAM"
hedefi gercek veride %94,27'de kaldi ve bir yer sozluguyle kapanamaz (kalan 110 tekilin
105'i yer eksigi degil). Esik bu yuzden olculebilir olanin — yer adi kapsaminin — uzerine
kuruldu (232 adlik temsili kume, ESIK=0.95, olculen %100). En buyuk kaldirac B sinifi
(68 tekil: yer ile tur arasinda "Cumhuriyet/Nobetci/Il" dolgu kelimesi); ayri gorev
onerildi. Onay/red gerekiyorsa insan karari.

## Izin engelleri

yok (her iki gorevde de `izinEngelleri` bos).

## Atlananlar

Atlanan, zincir hatasi veya teslim hatasi olan gorev yok. Tavan nedeniyle atlanan da yok.

## Ek notlar (kapsam disi bulgular, duzeltilmedi)

G069:
- `court_types` seed'i 2 worker'da MUKERRER satir uretiyor — yeni iki deger DB'ye IKISER
  kez dustu (ayni code: `HUK-YARGIT-44` / `CEZ-YARGIT-43`, her iki worker da
  "Seeded 2 new court_types" basti). Kok neden: `court_types.code` UNIQUE DEGIL
  (`models.py:545`, `database.py:866`'da yalniz `ix_court_types_id`), bu yuzden
  `_ekle_yarissiz`'in dayandigi `IntegrityError` hic olusmuyor. Pre-existing:
  seed'e her yeni deger eklenisinde ayni sey olmus olmali — **PROD'da mukerrer satir var mi
  olculmeli**; duzeltme `database.py`'de index/kisit op'u gerektirir. Lokal restore DB'de
  mukerrer satirlar kanit olarak birakildi.
- `derive_judicial_unit` BAM'da HD/CD kisaltmasini acmiyor ("Istanbul BAM 43. HD" -> None);
  Yargitay icin kisaltma eklendi, cunku orada daire tarafini gosteren tek isaret o.
- `docs/mimari`'de `judicial_unit` turetmesini anlatan bir yer YOK
  (`dava-acma-akisi.md:20` yalniz zorunlu alan listesinde aniyor) — guncellenecek satir
  bulunamadi.
- DANISTAY seed'de "Vergi", PATTERNS'te "Idari Yargi" parent'i altinda; ad eslesmesi
  yapildigi icin pratik etkisi yok ama iki kaynak celisiyor.

G070:
- Kisaltma ("Istanbul And.", "Eregli Kdz", "Afyon") ve yazim bozulmasi ("Bakirkoy",
  "Diyarbakir"...) bilincle sozluge ALINMADI: eslesen yuzey ayni zamanda kimliktir, ikinci
  yazim ayni yere ikinci kimlik acar; varyant->kanonik eslemesi mantik isi ve Dokunma
  listesinde. "OF" (Trabzon) 2 harfli oldugu icin alinmadi.

Her iki gorevde de calisma agacinda kapsam disi `.claude/settings.local.json` (M) ve
`.claude/launch.json` (??) vardi; harness dosyalari oldugu icin DOKUNULMADI ve commit'e
girmedi.

## Plan uyarilari

- G070 G069'a bagimli: ikisi de backend bandi, seri kosar; gercek paralellik yok.
- Calisma agaci temiz (yalniz `.claude/` altinda degisiklik var).
