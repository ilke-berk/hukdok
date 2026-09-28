# Gece Kuyruğu (workflow) · 2026-09-28

## Özet

2 görev alındı · 2 işaretlendi · 0 bloke · 0 atlandı

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G233 · Duruşma listesi `GET /api/hearing-dates?lawyer=` kimliği tanır (G228 denetim bulgusu) | backend | c661435 | geçti (test temiz, kırmızı→yeşil kanıtlandı) | GEÇTİ (2 bulgu) | 2 tur: tur 1'de ruff F401 (kullanılmayan `kanonik_avukat_adi` importu), tur 2'de temizlendi; pytest 3829 passed / 13 skipped, ruff + mypy temiz. `case_manager.py` değişmedi (yalnız `_kimligi_ada_cevir` import edildi). G231'de eski kod kaldırılırken `test_eski_kod_geriye_uyumlu` bilinçli güncellenmeli. Merge: veride `mergeYapildi=false`, worktree yok. |
| G232 · Karar 022: kurumsal avukat kimliği AVK-00001, avukat silinmez, envanter kapısı + CLAUDE.md maddesi | docs | 7a944bc | geçti (test temiz, kırmızı→yeşil uygulanamaz) | GEÇTİ (3 bulgu) | ADR iddiaları kod okunarak doğrulandı. `docs/kararlar/README.md` dizinine 022 satırı eklendi (kapsam dışıydı, ADR'den ayrılmaz). Hukukbot tarafı iddiası (`app/metadata.py sanitize_metadata`) dış repoda, G227/G230 keşfine dayanıyor. Merge yapıldı, worktree `C:/dev/hukudok-wt/G232` temizlendi. Push/deploy yok. |

## Bloke

Yok.

## Karar bekleyenler

Yok. (`gorevTanimiHatali` teşhisi ya da karşılanmayan kabul maddesi yok.)

## İzin engelleri

Yok.

## Atlananlar

Yok. (Tavan nedeniyle atlanan yok; plan uyarısı yok.)
