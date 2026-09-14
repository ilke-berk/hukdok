# Gece Kuyruğu (workflow) · 2026-09-14-5

## Özet

2 görev alındı · 2 işaretlendi · 0 bloke · 0 atlandı

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G196 — Dava durumu yazma yollarında üçlü kapısı | backend | `ca13686` | geçti · test temiz · kırmızı-yeşil kanıtlandı · ihlal yok | GEÇTİ (4 bulgu) | 1 tur. Tam pytest 3567 passed / 3 skipped, ruff + mypy temiz. Kabul maddesi karşılanmadı: takip ucu HTTP 400 (bkz. Karar bekleyenler). Merge yapılmadı (ana repoda çalıştı), worktree yok. |
| G197 — Bayat metin ve atıflar | backend | `c863259` | geçti · test temiz · kırmızı-yeşil uygulanamaz · ihlal yok | GEÇTİ (3 bulgu) | 1 tur. pytest 3567 passed / 3 skipped; vitest 88 dosya / 1005 test passed; ruff + mypy temiz. Kapsam dışı iki bayat kod yorumu atfı düzeltilmedi (aşağıda). Merge yapılmadı, worktree yok. |

### G196 ayrıntı

- Kırmızı kanıt: yeni test dosyası eski kodda 26 failed / 5 passed (POST serbest ve TEMYIZ → 500, PUT → 500; takip → 200, çünkü şema `status` taşımıyor).
- Uygulama: `constants.validated_case_status` + `InvalidCaseStatusError`, `api.py` 400 handler; `add_case` oturum açmadan önce, `update_case` ve `update_case_tracking` yazımdan önce kapıyı uygular, rollback + raise.
- Takip dbtest'i HTTP düzeyinden yönetici düzeyine çevrildi. Bu son hâli eski kodda ayrıca koşulmadı; kırmızı kanıtı HTTP varyantından geliyor.
- Küçük davranış değişiklikleri: `add_case` boş string status'u DERDEST yapıyor (eskiden Postgres'te 500); `add_case` `data['case_stage']`'i yazıyor ama API bu alanı göndermiyor; `is_consult` normalize edilmiş değere bakıyor.
- Tarama temiz: `kartsiz_foy_kart_ac:156/199`, `birlesik_kart_ayir:191`, `import_excel_cases:113/246`, `mukerrer_kart_birlestir:222`, `hukdok_aktarim:633/849`, `case_intake:1095` hepsi üçlü yazıyor.

### G197 ayrıntı

- İlk deneme (yorumu 4 satıra, perf_olcum metnini 2 satıra yaymak) sonraki ~30 geçerli `nginx.conf:N` atfını ve `perf_olcum.py:413` atfını yeniden bayatlatacaktı; geri alındı. Değişen her metin orijinal satır sayısında tutuldu.
- Düzeltilen atıflar: `CLAUDE.md:247` `:75 → :114-115`; karar 010:14 `:75-76 → :114-115`; `raporlama.md:74` `:77 → :116`; karar 013:151 `:7,91 → :7,130`. `deploy-ve-altyapi.md:458-460` şerhi güncel script metnine göre yeniden yazıldı.
- `docs/arsiv` ve `gorevler` (G197.md dışında) diff'i boş.
- **Kapsam dışı, düzeltilmedi:** `backend/routes/processing.py:378` → `nginx.conf:109` atfı (`/refresh` artık :161); `backend/routes/notifications.py:28` → `nginx.conf:62` atfı (`location /api` artık :116). İkisi de kod yorumu; ayrı küçük görev adayı.
- Plan uyarısı karşılandı: G197, G196'ya bağımlıydı (backend seri) ve G196 sonrası koşuldu; test sayıları için hem pytest hem vitest koşuldu.

## Bloke

Yok.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok. Karşılanmayan kabul maddesinden doğan soru:

1. **G196 — takip ucu HTTP 400:** `schemas.CaseTrackingUpdate` (`schemas.py:487-557`) `status` alanı taşımıyor; Pydantic onu sessizce düşürüyor, `PATCH /api/cases/{id}/tracking` bugün 200 dönüyor ve status yok sayılıyor. Yönetici düzeyi kapı uygulandı ve Postgres dbtest'iyle doğrulandı; HTTP 400 ise görevin dosya kapsamı dışındaki bir API genişlemesi gerektiriyor.
   **SORU:** `CaseTrackingUpdate`'e `status` eklensin mi (eklenirse takip ucu 400'ü kendiliğinden verir), yoksa `TRACKING_FIELDS`'tan `status` çıkarılsın mı? (Not: frontend `lib/trackingDraft.ts` status göndermiyor.)

## İzin engelleri

yok

## Atlananlar

Yok. Tavan nedeniyle atlanan: yok.
