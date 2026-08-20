# Gece Kuyrugu (workflow) · 2026-08-20

## Ozet
6 gorev alindi · 6 isaretlendi · 0 bloke · 0 atlandi

## Isaretlenenler

| Gorev | Bant | Commit | Kapi | Denetim | Not |
| --- | --- | --- | --- | --- | --- |
| G078 | backend | `0db1653` | GECTI (test temiz, kirmizi-yesil kanitlandi) | GECTI (3 bulgu) | GET /api/documents/recent; uc henuz frontend'de tuketilmiyor. 2 tur. |
| G080 | backend | `1f1a015` | GECTI (test temiz, kirmizi-yesil kanitlandi) | GECTI (5 bulgu) | Bildirim hedef cozumleyicisi; servis henuz hicbir yerden CAGRILMIYOR. 3 tur. |
| G081 | backend | `b306e60` | GECTI (test temiz, kirmizi-yesil kanitlandi) | GECTI (4 bulgu) | notifications tablosu + /api/notifications; entegrasyon: uygulanamaz. 3 tur. |
| G084 | backend | `26a8f4e` | GECTI (test temiz, kirmizi-yesil kanitlandi) | GECTI (4 bulgu) | legal_deadlines saf modul; ilk turda yesil. |
| G082 | backend | `216095a` | GECTI (test temiz, kirmizi-yesil kanitlandi) | GECTI (4 bulgu) | "Belge islendi" bildirimi; 1 kabul kriteri birebir karsilanmadi (asagida SORU). |
| G079 | frontend | `75d05fb` | GECTI (test temiz, kirmizi-yesil kanitlandi) | GECTI (2 bulgu) | Pano paneli + mail rozeti; merge yapildi, entegrasyon yesil, worktree temizlendi. 2 tur. |

Son parmak izleri (koşu ciktilarindan):
- G078: yesil, basarisiz test yok.
- G080: 1755 passed, 3 skipped; ruff temiz; mypy Success (45 dosya).
- G081: 1795 passed, 3 skipped; ruff 0 bulgu; mypy 0 hata.
- G084: 1822 passed, 3 skipped; ruff temiz; mypy Success (48 dosya).
- G082: 1844 passed, 3 skipped; ruff temiz; mypy 48 dosya temiz.
- G079: vitest 396 passed / 29 dosya; eslint 0 error 22 warning (baseline); `tsc -b --force` exit 0.

## Bloke
Yok — bu kosuda bloke kalan gorev olmadi.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` isaretli gorev YOK; dolayisiyla insana yoneltilmis
otomatik soru bulunmuyor. Karsilanmayan tek kabul maddesi asagida SORU olarak duruyor.

**SORU (G082) — dedupe_key formati:** Gorev tanimi `doc-processed:{doc_id}` diyordu;
uygulanan anahtar `doc-processed:{doc_id}:{email}`. Gerekce: `dedupe_key` G081'de
GLOBAL tekil (`uq_notifications_dedupe`) ve bir bildirim satiri tek `recipient_email`
tasiyor; ciplak anahtar iki sorumlulu davada ("Tugce Ungor Yanik;Serap Turgal" —
G080 bu ayraci bilincli destekliyor) ikinci avukatin bildirimini sessizce yutardi.
Onek korundu ve tek alicili davada davranis birebir ayni (iki test kilitliyor).
Karar: sapma kabul mu edilsin, yoksa tanimdaki format mi geri getirilsin?

## Izin engelleri
Yok. (Alti gorevin de `izinEngelleri` listesi bos — `.claude/settings` izin listesi
icin bu kosudan olculmus bir genisletme gerekcesi CIKMADI.)

## Atlananlar
Yok — `atlandi`, `zincirHatasi`, `teslimHatasi` alanlari alti gorevde de bos.
Tavan nedeniyle atlanan gorev de yok.

## Ek notlar ve izlenecekler

- **Push/deploy YAPILMADI.** 19.08 lokal calisma direktifi geregi paket (G078-G086)
  yalniz lokalde dogrulandi; deploy gerektiren degisiklikler icin ayri insan karari sart.
- G080 ve G081 uretilen yapilar henuz uctan uca bagli degil: G080 cozumleyicisi
  cagrilmiyor, G081'de `dismissed_at` yazan "kapatma" ucu yok. G085 dedupe_key'i
  "ayni olayin ayni gun tekrari" kapsaminda secmeli.
- G079 panosu acilis sirasinda 3 paralel istek yapiyor; olcum yapilmadan
  birlestirme/onbellek eklenmemeli. "02 · Sure / Vade" bolumu hala yer tutucu.
- G078: `documents.uploaded_at` uzerinde tekil index yok; ADR-018 geregi olcum
  yapilmadan index eklenmemeli.
- G084: dini bayram takvimi 2024-2027 icin elle girildi, yillik insan dogrulamasi
  gerekiyor (kodda BAKIM NOTU olarak yazili).
- Kapsam disi kirli dosyalar (`.claude/settings.local.json` M, `.claude/launch.json` ??)
  tum gorevlerde harness urunu olarak DURUYOR; hicbir commit'e girmedi.
