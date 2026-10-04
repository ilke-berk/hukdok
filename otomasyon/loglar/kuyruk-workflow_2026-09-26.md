# Gece Kuyruğu (workflow) · 2026-09-26

## Özet

9 görev alındı · 3 işaretlendi · 2 bloke · 4 atlandı

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G198 · Zamanlayıcı pytz'den kurtulur (zoneinfo + APScheduler 3.11.3) | backend | 9e0deb9 | geçti (kırmızı-yeşil kanıtlandı) | GEÇTİ (4 düşük önemli bulgu) | 3 tur; 3637 passed / 11 skipped, ruff+mypy yeşil. Liderde işler 00:00/02:30/06:00 TR. "Sabit tek yerde" hedefi literal uygulanmadı (G085 AST bekçisi literal ZoneInfo istiyor, 4 literal çağrı). pytz imaja Office365-REST-Python-Client üzerinden hâlâ giriyor (Faz 3). tzdata pin'lenmedi. Repo kökünde çalışıldı, merge yok. |
| G204 · lib/hukukbotApi.ts (oturum CRUD + /ask NDJSON + PDF indirme) | frontend | 99960a3 | geçti (kırmızı-yeşil kanıtlandı) | GEÇTİ (4 bulgu) | 1 tur; `apiClient.fetch` üzerinden (reportsChat deseni), api.ts'e dokunulmadı. Başlık `session-id` (tireli). Hukbot'un yenilemeden sonra 401 dönmesi HUKDOK logout'unu tetikler — canlı dumanda doğrulanmalı. Worktree merge edildi, entegrasyon yeşil, worktree temizlendi. |
| G199 · requests 2.34.2 + activity_manager Graph payload tipi | backend | 1d62a64 | geçti (kırmızı-yeşil uygulanamaz) | GEÇTİ (2 bulgu) | Yalnız tip açıklaması; kırmızı kanıtı `mypy --shadow-file` ile (açıklamasız kopyada activity_manager.py:257 arg-type). 3637 passed / 11 skipped. Sürüm notu ayrıntısı dışarıdan okunmadı. |

## Bloke

### G205 · /hukukbot sayfası HUKDOK tasarımıyla; testler (frontend)

- **Durma sebebi:** `kapsam-disi-gerekti` — kapsam dışı dosya gerekti (commit yok).
- **Son parmak izi:** `App.lazy.test.tsx > geri kalan her sayfa React.lazy + importWithReload ile yüklenir: AssertionError expected length 12 got 13`
- **Denenen yaklaşımlar:**
  1. Tur 1: sayfa + bileşenler + 26 test yazıldı; tam pakette App.lazy.test.tsx kırmızı, lint'te `require-yield` hatası.
  2. Tur 2: `require-yield` düzeltildi (429 mock'u async-iterator nesnesi); lint/tsc/build temiz; kalan tek kırmızı G182 bekçisi — düzeltmesi App.tsx (Dokunma) + mevcut testin sabit sayısı, ikisi de yasak → DUR.
  3. Reddedilen: sayfayı `components/hukukbot` altına taşıyıp bekçiyi atlatmak (görev kapsamını ve G206'nın beklediği yolu bozar, bekçinin amacını deler).
- **Kök neden (plan hatası):** G205 sayfayı `pages/`e koyup rotayı G206'ya bırakıyor; ara durumda App.lazy.test.tsx bekçisi kırmızı kalıyor. G206'nın dosya kapsamında da App.lazy.test.tsx yok (12 → 13 olmalı), yani G206 da takılırdı.
- **Worktree:** `C:/dev/hukudok-wt/G205` (dal `gorev/G205`, commit'siz, korunuyor). Görev dosyasına Rapor + DURUM: BLOKE yazıldı (commit'siz).
- **Karşılanmayan kabul maddeleri:** tam paket 1100 geçti / 1 kırmızı; 375 px davranışı tarayıcıda gözle doğrulanmadı (rota bağlı değil).
- **Önerilen sonraki adım:** G205 ile G206'yı birleştirmek ya da G206 kapsamına `App.lazy.test.tsx` eklemek; sayfa dosyası rota ile aynı commit'te bağlanmalı. Worktree'deki iş (26 yeşil test) bu birleşik göreve taşınabilir.

### G200 · PyJWT 2.15.0 (backend)

- **Durma sebebi:** KAPI — kırmızı-yeşil kanıtlanamadı (eklenen test eski kodda da geçiyor). Commit `d7d57b3` var ama işaretlenmedi.
- **Son parmak izi:** yeşil: 3641 passed, 11 skipped; ruff ok; mypy ok.
- **Denenen yaklaşımlar:** PyJWT 2.13.0 → 2.15.0 bump, imaj `--progress=plain` ile yeniden kuruldu; auth_verifier.py değişikliği gerekmedi, ilk turda yeşil.
- **Kök neden:** Eklenen 4 test kilit (regresyon) testidir; PyJWT 2.13 da aynı sayısal olmayan değerleri reddettiği için eski kodda kırmızıya dönmezler. Sürümü kod değil imaj belirliyor — kapının kırmızı-yeşil şartı bu tür bump görevine doğal olarak uymuyor.
- **Worktree:** yok (repo kökünde çalışıldı).
- **Önerilen sonraki adım:** İnsan kararı — bump görevleri için "kırmızı-yeşil uygulanamaz" kabul edilip (G199 gibi) işaretlensin mi? Deploy öncesi insan adımı: gerçek Azure girişi, sessiz token yenileme ve çıkış dumanı. Not: 2.15'te PyJWKClient bilinmeyen kid'de 30 sn yenileme beklemesi (cooldown) var — Azure anahtar rotasyonunda bu sürede ERROR log + None döner; ayar değiştirilmedi.

## Karar bekleyenler

(`teshis.gorevTanimiHatali=true` olan görev yok.)

- **G205:** Tam paket kırmızısız geçmiyor (App.lazy.test.tsx 12 sabiti) — G205+G206 birleştirilsin mi, yoksa G206 kapsamına App.lazy.test.tsx mi eklensin?
- **G205:** 375 px davranışı rota bağlanmadan tarayıcıda doğrulanamıyor — doğrulama birleşik göreve mi bırakılsın?
- **G200:** Kırmızı-yeşil kanıtı gerektirmeyen bağımlılık bump'ında kapı gevşetilsin mi?

## İzin engelleri

yok

## Atlananlar

- **G206** (Rota + menü) — bağımlılık bu koşuda tamamlanmadı: G205. (Worktree `C:/dev/hukudok-wt/G206` temizlenmedi.)
- **G201** (SQLAlchemy 2.0.54) — bağımlılık bu koşuda tamamlanmadı: G200.
- **G202** (Dev araçları pytest/ruff/mypy + ci-kontrol) — bağımlılık bu koşuda tamamlanmadı: G201. Plan uyarısı: dosya kapsamı `.claude/skills/ci-kontrol/SKILL.md` içeriyor.
- **G207** (Doküman + infra, karar 021) — bağımlılık bu koşuda tamamlanmadı: G202, G206. (Worktree `C:/dev/hukudok-wt/G207` temizlenmedi.)

Tavan nedeniyle atlanan: yok.
