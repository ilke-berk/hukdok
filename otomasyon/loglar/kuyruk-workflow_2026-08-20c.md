# Gece Kuyrugu (workflow) · 2026-08-20c

## Ozet

2 gorev alindi · 2 isaretlendi · 0 bloke · 0 atlandi (tavan nedeniyle atlanan: yok)

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G087 — İdari bildirim görünümü uçları (dağılım + hedefsiz sayacı) | backend | `d2114b6` | GECTI (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI (4 bulgu) | 2 tur; pytest 1913 passed / 3 skipped, ruff temiz, mypy 49 dosya temiz. Merge/entegrasyon alani bos (mergeYapildi=false), worktree kullanilmadi. |
| G086 — KALAN: "Süreli İşler" (idari) paneli | frontend | `3be06cabd6e4f124bcd86618d1ba889383f418a8` | GECTI (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI (4 bulgu) | 1 tur; vitest 510, lint 0 error / 22 warning, `tsc -b --force` exit 0. mergeYapildi=true, entegrasyon yesil, worktree `C:/dev/hukudok-wt/G086` temizlendi. |

### G087 notlari (veriden)

- Kapi `get_current_user` + `get_current_tenant`: kimliksiz 401, `tid` claim'i yoksa 403.
- Tenant filtresi overview'de paylasilan havuz deseni (`tenant_id == X OR IS NULL`).
  `unresolved-targets`'ta tenant daraltmasi **bilincli yok**: sayac `cases` uzerinden
  hesaplanir, dava havuzu paylasimli (tenant_id NULL) ve daraltmak Dokunma listesindeki
  `services/notification_targeting.py`'yi degistirmeyi gerektirirdi.
- Pencere `due_date` degil `created_at` uzerinde (suresi gecmis ama okunmamis uyari
  listeden dusmesin). Tur etiketleri (`SURE_TYPE`/`DURUSMA_TYPE`) `deadline_scanner`'dan
  import edildi, kopyalanmadi. Siralama `coalesce(due_date, 9999-12-31) ASC, id ASC`
  (sqlite/Postgres NULL sirasi farkini kapatir). `total`/`unread` limit uygulanmadan
  hesaplanir.
- G081 kisisel uclari degismedi; regresyon bekcisi uc test yesil (kisisel liste yalniz
  kendi satirlari, baskasinin id'si 404, read-all baskasina dokunmaz).
- Kapsam disi kirli dosyalar (`.claude/settings.local.json` M, `.claude/launch.json` ??)
  oturum basinda vardi, dokunulmadi ve commit'e alinmadi. Push/deploy yapilmadi.

### G086 notlari (veriden)

- Kabul kriterlerinin tamami karsilandi; gorev dosyasindaki DURUM satiri TAMAM'a cevrildi,
  eski BLOKE raporu tarihsel kayit serhiyle korundu.
- Dokunma listesindeki `frontend/src/components/PlaceholderBadge.tsx` **silinmedi** (artik
  hicbir yerde kullanilmiyor — takip icin rapora yazildi).
- `docker compose` hic calistirilmadi; tum dogrulama host'ta worktree icinde kosuldu.
  Push/deploy/ssh yapilmadi.
- Commit trailer'i skill'deki bicimle atildi (G086'nin avukat yarisi commit'i `a74909b`
  ile ayni); amend kirmizi hat oldugu icin degistirilmedi.

## Bloke

Bu kosuda bloke gorev yok.

## Karar bekleyenler

Teshis kaydi bos (`gorevTanimiHatali=true` olan gorev yok) ve iki gorevde de
`kabulKarsilanmayan` listesi bos — insana yoneltilecek acik soru yok.

Bilgi olarak tasinan iki takip maddesi (soru degil, karar gerektirmiyor ama kaybolmasin):

- G087: `unresolved-targets` ucunda tenant daraltmasi bilincli olarak yapilmadi; ileride
  daraltma istenirse `services/notification_targeting.py` dokunma listesinden cikarilmali.
- G086: kullanilmayan `PlaceholderBadge.tsx` duruyor; silinmesi ayri bir temizlik kalemi.

## Izin engelleri

Yok — iki gorevin de `izinEngelleri` listesi bos.

## Atlananlar

Yok — `atlandi`, `zincirHatasi`, `teslimHatasi` alanlarinin hepsi bos.

## Plan uyarilari (kosucudan)

- G086 acik ama `bagimli:G087` — G087 bitmeden secilmemeli; ayni gece secilirse G087 once
  kosmali. Bu kosuda sira dogru isledi (G087 once, G086 sonra).
- G086 gorev dosyasinin Rapor bolumunde "DURUM: BLOKE" yaziliydi (avukat yarisi main'de,
  idari yari G087'nin ucunu bekliyordu); KUYRUK satirinda BLOKE kelimesi gecmiyordu.
- Kosu baslangicinda HEAD: `4566b33` (docs: G087 yetki kapisi karari — admin ayrimi yok).

## Testi degistirmeden gecilemedi mi?

Hayir. G087'nin ilk turunda tek kirmizi vardi ve **beklenti** duzeltildi: hedefsiz sayaci
etiketi collation'a bagli oldugu icin (servis "ada gore sirali sorgunun ilk ham yazimi"ni
doner, sqlite ASCII siralamasinda "ARSIV DOSYA YONETICISI" one geciyor) test, servisin
belgelenmis davranisina gore kabul edilen yazim KUMESI + kesin sayimlar seklinde yeniden
yazildi. Uretim davranisi gevsetilmedi; sayimlar ve toplamlar aynen kesin dogrulaniyor.
Hattin dogru calistiginin kanitidir.
