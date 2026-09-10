# Gece Kuyrugu (workflow) · 2026-09-10e

## Ozet

1 gorev alindi · 1 isaretlendi · 0 bloke · 0 atlandi

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G162 — BİLGİLENDİRME 1.3: §3.3/§3.4/§3.5/§3.8/§9 SÖZLEŞME 1.3'e aynalanır, SÖZLEŞME giriş şerhi güncellenir | docs | `e228e49` | GEÇTİ (test: temiz, kırmızı-yeşil: uygulanamaz, ihlal yok) | GEÇTİ (4 bulgu; üç kabul kriteri bağımsız doğrulandı: §3.8 sayıları host'ta AST ile yeniden sayıldı 27/8/4/2 ve 47/66, sızıntı grep boş, diff yalnız iki .md + görev dosyası) | Tek tur, verify: test-yok. Merge yapıldı, entegrasyon: uygulanamaz, worktree (`C:/dev/hukudok-wt/G162`) temizlendi. Listelenen bölümler dışında aynı dosyada küçük tutarlılık dokunuşları yapıldı (kapı tablosu satırı, 3.1 sayfa tablosu, 3.2 ad alanları, 4 satır raporu tür/sebep, 5 DB-008 + 3 SERBEST satır, 8 kontrol listesi 10 madde) — gerekçe: §3.8'de Yazım_Standardı isterken §5'te "gerek yok" bırakmak belgeyi kendi içinde çelişik yapardı. SÖZLEŞME'den aynalanan ölçüm sayıları (1.677 / 217 / 38 / 131 / 74) yeniden ölçülmedi. Push/deploy yapılmadı. |

## Bloke

Bloke görev yok.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok; `kabulKarsilanmayan` boş. Yine de G162 çalışmasında ortaya çıkan ve karar isteyen iki kod-doküman uyuşmazlığı var:

- SORU (G162): SÖZLEŞME §7'deki DB-008 örneği ("AXA SIGORTA → Axa Sigorta değişiklik sayılır") taraf sütunları için kodla uyuşmuyor — `_taraflari_yaz` yalnız ekler ve harf duyarsız anahtar kullanır. BİLGİLENDİRME koda göre yazıldı, SÖZLEŞME §7 görev kapsamı dışında bırakıldı. SÖZLEŞME §7 kodla hizalansın mı, yoksa kod SÖZLEŞME'ye mi uydurulsun?
- SORU (G162): `BOSALTMA_DISI_ALANLAR` içinde "İstinaf Mahkemesi Başvuran Taraf" da var; SÖZLEŞME §4 bunu saymıyor. BİLGİLENDİRME'ye koddan eklendi. SÖZLEŞME §4 güncellensin mi?

## Izin engelleri

yok

## Atlananlar

Atlanan / zincir hatası / teslim hatası olan görev yok. Tavan nedeniyle atlanan: yok.

## Plan uyarıları

- G162 §3.8 adımı konteynerde seed sayımı ister (`docker compose exec backend`) — docs bandı worktree'de koşarsa ana stack'in ayakta olması gerekir. Bu koşuda sayım konteynerde yapıldı ve denetim host'ta AST ile yeniden saydı; sonuçlar birebir.
