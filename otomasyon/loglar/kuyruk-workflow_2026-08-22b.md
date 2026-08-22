# Gece Kuyrugu (workflow) · 2026-08-22b

## Ozet

3 gorev alindi · 3 isaretlendi · 0 bloke · 0 atlandi

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G096 — Token doğrulama faz 2: scp zorunlu + audience yalnız api:// | backend | `d63a1d0` | gecti (test temiz, kirmizi-yesil kanitlandi) | GECTI (2 bulgu) | 1 tur; 1996 passed / 3 skipped, ruff+mypy temiz. Yeni test dosyasi yok, test_auth_verifier.py icinde 8 yeni/ters cevrilmis test (stash ile eski kodda 6 failed). **Kullanici adimi:** rebuild + gercek Microsoft girisiyle pano acilisi dogrulanmali. `docs/mimari/kimlik-ve-token.md` §2/§6 guncellendi (satir ref. 38/112/131). Ana repoda calisti (worktree yok, merge alani yok). |
| G097 — Bildirim tarayıcısı: boot telafisi + retention + tz/duruşma sınırı testleri | backend | `80f2e17` | gecti (test temiz, kirmizi-yesil kanitlandi) | GECTI (2 bulgu) | 2 tur: tur 1'de G085 `test_durusmada_yedi_gun_esigi_yoktur` kirmizi (atlanan 0 != 1); tur 2'de sinir disi durusmalar COUNT ile atlanan sayacina eklendi, G085 testine dokunulmadi. 2014 passed / 3 skipped, ruff+mypy (49 dosya) temiz, 18 yeni test. Kararlar: `NOTIFICATION_RETENTION_DAYS` settings.py yerine notifications.py'de; lider-disi worker kriteri AST kapi testiyle. **Insan adimi:** `.env.example`'a `NOTIFICATION_RETENTION_DAYS` satiri eklenmedi (.env* kirmizi hat). Ana repoda calisti. |
| G098 — Zil paneli hijyeni: updater yan etkisi + markRead geri bildirimi + 401 testi | frontend | `6780fb8` | gecti (test temiz, kirmizi-yesil kanitlandi) | GECTI (2 bulgu) | 1 tur; vitest 542/542, lint 0 error, `tsc -b --force` exit 0; stash ile eski kodda 14 test kirmizi. Karar: `markError/clearMarkError` OPSIYONEL (mevcut NotificationBell.test.tsx hookState literali). Gorevdeki `hooks/useNotifications.test.tsx` yolu repoda yok; testler `components/notifications` altina kondu. Worktree `C:/dev/hukudok-wt/G098`, dal gorev/G098; merge yapildi, entegrasyon yesil, worktree temizlendi. |

Notlar:
- G096/G097 `mergeYapildi=false` / `entegrasyon=null`: ana repoda dogrudan calistilar, ayri merge adimi uygulanmadi (veri alani boyle; basari iddiasi degil, mekanik durum).
- Denetim "bulgu: 2" her uc gorevde de GECTI sonucuyla birlikte geldi; bulgu metinleri veride yok, sabah `gorev-denetle` ciktilarindan okunabilir.
- Calisma agacindaki `.claude/settings.local.json` (M) ve `.claude/launch.json` (??) hicbir gorevde commit'e girmedi.

## Bloke

yok.

## Karar bekleyenler

- `teshis.gorevTanimiHatali=true` olan gorev yok; `kabulKarsilanmayan` tum gorevlerde bos.
- Soru (G097): `.env.example`'a `NOTIFICATION_RETENTION_DAYS` satiri eklensin mi? (Gece koşusu .env* dosyalarina dokunmaz.)
- Soru (G096): rebuild sonrasi gercek Microsoft girisiyle pano acilisi kim/ne zaman dogrulayacak? Prod'a cikmadan once bu adim sart (lokal calisma direktifi yururlukte).
- Soru (G098): `hooks/useNotifications.test.tsx` yolu gorev tanimindaydi ama repoda yok; gorev sablonundaki yol sabitleri gozden gecirilsin mi?

## Izin engelleri

yok (G096, G097, G098 `izinEngelleri` listeleri bos).

## Atlananlar

yok (atlandi / zincirHatasi / teslimHatasi alanlari uc gorevde de bos; tavan nedeniyle atlanan yok).

## Plan uyarilari (koşu oncesi)

- G096 ve G097 ayni bant (backend): seri kostu, dosya kesisimi yok.
- G098 frontend: paralel kosabildi (worktree).
- G096 `docs/mimari/kimlik-ve-token.md` dosyasina da dokundu (docs bandi degil, backend gorevi icinde).
