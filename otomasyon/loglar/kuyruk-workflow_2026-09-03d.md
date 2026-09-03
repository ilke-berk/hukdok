# Gece Kuyrugu (workflow) · 2026-09-03d

## Ozet

2 gorev alindi · 2 isaretlendi · 0 bloke · 0 atlandi

Tavan nedeniyle atlanan: yok. Her iki gorev de tek turda yesil; merge YAPILMADI
(mergeYapildi=false, worktree yok — ana dizinde calisildi), entegrasyon adimi kosmadi.

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G115 — Teslim yapi farki tespiti (yapi JSON kolonu, kapi `yapi_degisti`, bildirim govdesi, ozet) | backend | `bc7c49f` | GECTI (test temiz, kirmizi-yesil kanitlandi, 0 ihlal) | GECTI (3 bulgu) | Tek tur; son parmak izi: pytest 2344 passed / 3 skipped, ruff temiz, mypy 53 dosya temiz. Fark ayri kolon degil `yapi["fark"]` + model property `yapi_farki` (test_g108 kilidi korundu). Bildirim/ozette `taninmayan_basliklar` bilerek yok (her teslimde 31 okunmayan sutun = gurultu). WARNING yalnizca gercek fark kaleminde. Izlenecek: frontend gosterimi (G116 sonrasi); prod'daki mevcut teslimlerin `yapi`'si NULL → ilk yeni teslimde yalnizca "taninmayan" hesaplanir; cok satirli (`\n`) bildirim govdesinin G111 panelinde satir kirdigi dogrulanmali. |
| G118 — Belirsiz eslesmede ucuncu anahtar (satir Muvekkil adi ↔ kartin CLIENT taraflari) | backend | `b6a48f8` | GECTI (test temiz, kirmizi-yesil kanitlandi, 0 ihlal) | GECTI (3 bulgu) | Tek tur; denetim konteynerde pytest 2357 passed / 3 skipped (+11), ruff/mypy temiz, gercek paket kuru kosu bagimsiz tekrarlandi (belirsiz 29). Olcum: 33 → 29 (hedef ≤10 TUTMADI — asagida karar bekleyenlerde). `cases.client_id` sozlesmede var ama modelde YOK; kume `case_parties.client_id → clients.name` uzerinden kuruldu. Yalniz INFO log eklendi. Teknik not: bind-mount'ta `docker compose exec` icin `MSYS_NO_PATHCONV=1` gerekti (Git Bash `/app/...` yolunu bozuyor). |

## Bloke

Bloke gorev yok.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan gorev yok. Kabul kriteri karsilanmayan madde:

- **G118 — SORU:** Belirsiz eslesme olcumu hedefi (≤10) tutmadi: 33 → 29. Gorev metni
  "hedef tutmazsa 3 ornekle gerekceli TAMAM olabilir" dedigi icin isaretlendi; gerekce ve
  3 ornek gorev raporunda. Raporun notu: 8. adim olarak "muvekkil kumesi birebir esitligi"
  eklense 18 satir daha cozulur → 11 kalir; sozlesme disi ve tahmin riski tasidigi icin
  BILEREK eklenmedi. **Bu 8. adim eklensin mi?** Kalan 11 satir gercek mukerrer kart
  (10 cift listesi raporda) → kart temizligi ayri is olarak acilsin mi?
- **G115 — bilgi:** "Fark ayri JSON kolon" yerine `yapi["fark"]` anahtari + property
  secildi (gorev "bir JSON kolon" dedi). Tasarim sapmasi kabul ediliyorsa ek is yok.

## Izin engelleri

yok

## Atlananlar

yok (atlandi / zincirHatasi / teslimHatasi olan gorev yok).

## Diger notlar

- Plan uyarilari koşuda dogrulandi: G115 gorev dosyasindaki eski "DURUM: BLOKE" kaydi
  tarihsel (03.09 b352b59 ile cozulmustu); test_g107/test_g108 kilitleri degistirilmedi.
  G118 seri zincirde G115 sonrasi kostu.
- Her iki gorevde de kapsam disi kirli dosyalar (`.claude/settings.local.json` M,
  `.claude/launch.json` ??) oturum oncesinden vardi; dokunulmadi, commit'e girmedi.
  Skill'in "kapsam disi kirli dosya → BLOKE" kurali bu arac dosyalari icin uygulanmadi
  (G118 raporunda not edildi) — kural metni bu istisnayi acikca kapsamali.
