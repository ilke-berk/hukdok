# Gece Kuyrugu (workflow) · 2026-09-02

## Ozet
3 gorev alindi · 3 isaretlendi · 0 bloke · 0 atlandi

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G103 — Belgeleme olayı alanları (iki kolon + iki kapalı liste + yazma/okuma yolu + olay_turu filtresi) | backend | `e6d44ed` | GECTI (test temiz, kirmizi-yesil kanitli) | GECTI (0 bulgu) | 4 tur; yazma yolu olarak takip paneli secildi (G066 mekanizmasi kurulu); yeni exception acilmadi, `InvalidDecisionStatusError` yeniden kullanildi; canli lokal DB'de migrasyon+seed psql ile dogrulandi, acilis 0 ERROR. Son parmak izi: pytest 2096 passed 3 skipped, ruff/mypy temiz. |
| G105 — Kart UI: iki kapalı liste alanı + "belgeleme olayı olabilir" rozeti (NULL≠0) + liste filtresi | frontend | `a6e13eb` | GECTI (test temiz, kirmizi-yesil kanitli) | GECTI (3 bulgu) | Tek turda yesil; merge yapildi, entegrasyon yesil, worktree (C:/dev/hukudok-wt/G105) temizlendi. G103 backend'i gelene dek yeni config uclari 404 doner (G019 hata seridi) — iki gorev birlikte merge edilecegi icin deploy durumunda sorun yok. Rozet saf predikat olarak test edildi. |
| G104 — Aktarım eşlemesi: Olay Türü + Hükümdeki Rol sütunları teslimden kartlara (toleranslı başlık) | backend | `8e71bcf` | GECTI (test temiz, kirmizi-yesil kanitli) | GECTI (2 bulgu) | Tek turda yesil; kirmizi-yesil kaniti: yeni test dosyasi HEAD'de import asamasinda kirmizi. Kapsam ici duzeltme: docstring YAZILAN bolumu kodla esitlendi. Dokunma listesi korundu (models.py ve managers/** degismedi). |

Not: G103 ve G104 icin mergeYapildi=false — commit'ler var, entegrasyon/merge adimi veride yesil olarak isaretlenmemis (yalniz G105'te merge + entegrasyon yesil).

## Bloke
Yok — hicbir gorev bloke olmadi.

## Karar bekleyenler
Yok — hicbir goreve gorevTanimiHatali teshisi konmadi, kabulKarsilanmayan madde yok.

## Izin engelleri
Yok.

## Atlananlar
Yok (tavan nedeniyle atlanan da yok; plan uyarisi yok).

## Dikkat notlari
- G103 turlarindan biri altyapi kaynakliydi (canli lokal DB'de migrasyon eksikti, `docker compose restart backend` ile cozuldu) — kod hatasi degil.
- G103/G104 oturumlarinda calisma agacinda kapsam disi harness kirliligi gozlendi (`.claude/settings.local.json` degisik, `.claude/launch.json` izsiz); bilinçli olarak dokunulmadi ve commit'e alinmadi.
- G103 notu: G105 ayni dondurulmus sozlesmeyle paralel kostu; iki gorev birlikte deploy edilmeli.
