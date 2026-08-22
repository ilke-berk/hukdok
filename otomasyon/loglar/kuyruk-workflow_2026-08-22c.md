# Gece Kuyrugu (workflow) · 2026-08-22c

## Ozet

2 görev alındı · 2 işaretlendi · 0 bloke · 0 atlandı

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G100 — Yazdırma popup'larında inline script/handler kaldırılır (CSP enforce ön koşulu) | frontend | `8fd1dbc` | GEÇTİ (test temiz, kırmızı-yeşil kanıtlandı) | GECTI (3 bulgu) | 3 tur; merge yapıldı, entegrasyon yeşil, worktree temizlendi. Son parmak izi: vitest 43 dosya / 550 passed; eslint 0 error 22 warning (hepsi mevcut); tsc -b --force exit 0. Tur 1: vi.mock hoisting hatası; Tur 2: çift avukat adı nedeniyle 4 test kırmızı; Tur 3: cmdItem(value, liste) ile 8/8 yeşil, eski kodla 6/8 kırmızı doğrulandı. 6 kabul kriteri karşılandı. Gerçek yazdırma diyaloğu insan turuna kalır (G101 sonrası). Ana repoda eski stash@{0} (38c0038, bu oturuma ait değil) duruyor, dokunulmadı. |
| G101 — CSP zorlayıcıya geçer: -Report-Only eki düşer | docs | `1b87448` | GEÇTİ (test temiz, kırmızı-yeşil uygulanamaz) | GECTI (3 bulgu) | 1 tur; merge yapıldı, entegrasyon uygulanamaz, worktree temizlendi. Doğrulama: `nginx -t` syntax ok / test successful (tek seferlik `docker run nginx:alpine`, compose çağrılmadı). Kabul parantezi "git diff nginx.conf tek satır" harfiyen karşılanmadı: add_header satırı tek, ancak nginx.conf:43-48 yorum bloğu da güncellendi (eski yorum zorlayıcı başlıkla çelişirdi; ALTIN KURAL gereği düzeltildi). Başlık hâlâ satır 54; proxy blokları, timeout'lar ve /export yokluğu değişmedi. Başlığın canlıda görünmesi için frontend imajı rebuild gerekir (kullanıcı adımı). |

## Bloke

Bloke görev yok.

## Karar bekleyenler

- `gorevTanimiHatali=true` olan görev yok; `kabulKarsilanmayan` listeleri boş.
- Not (G101): "git diff nginx.conf tek satır" kabul parantezi harfiyen karşılanmadı (ek yorum satırları değişti, içerik satırı tek). Denetim GECTI verdi; bu sapma kabul ediliyor mu?
- Plan uyarısı (G101): nginx.conf değişikliği DEPLOY gerektirir ve deploy sonrası insan turu ister (yazdır popup'ları, PDF aç, belge yükle); gece oturumu tarayıcı turunu yapamaz. Lokal çalışma direktifi (2026-08-19) gereği deploy kararı kullanıcıya aittir.

## Izin engelleri

yok

## Atlananlar

yok (tavan nedeniyle atlanan da yok)
