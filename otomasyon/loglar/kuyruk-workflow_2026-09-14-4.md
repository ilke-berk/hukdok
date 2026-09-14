# Gece Kuyruğu (workflow) · 2026-09-14-4

## Özet

3 görev alındı · 3 işaretlendi · 0 bloke · 0 atlandı

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G192 — Düşük etkili: offset tavanı 422; cases ilişki + clients poliçe N+1 → in_(); upload_queue._scan_once vade filtresi SQL'de; PK ikizi ix_<tablo>_id → _DUSURULECEK_INDEXLER (D8, D10, D11, D15) | backend | 9851939 | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (2 bulgu) | 1 tur; 3531 passed / 3 skipped; ruff dokunulan dosyalar temiz, mypy 62 dosya temiz. mergeYapildi=false, worktree yok (ana repoda). Prod'da ilk açılışta 20 `DROP INDEX IF EXISTS` koşar; rollback bu index'leri geri getirmez (PK ikizi, plan etkisi yok). `ruff check .` 6 hata yalnız `calibration-data/_g179/ek3_cevapla.py` (repo dışı volume, görevle ilgisiz). |
| G195 — cases.status CHECK NOT VALID idempotent op (değer listesi CASE_STATUSES'ten; VALIDATE ayrı görev) | backend | 1e2ce6a | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (3 bulgu) | 1 tur; 3536 passed / 3 skipped, hedefli 37 passed; ruff/mypy temiz. Madde 52 `case_status_check_ddl()`. mergeYapildi=false, worktree yok. Kapsam dışı notlar aşağıda (Karar bekleyenler). Lokalde nginx bayat upstream için `docker compose restart frontend` koşuldu. |
| G193 — Performans turu dokümantasyonu: CLAUDE.md arama + nginx, deploy-ve-altyapi, genel-bakis, karar 018 nihai index tablosu, denetim raporu şerhi | docs | c8db049 | geçti (test temiz, kırmızı-yeşil uygulanamaz) | GEÇTİ (5 bulgu) | 1 tur; verify=test-yok. Merge yapıldı (902efac), entegrasyon uygulanamaz; worktree `C:/dev/hukudok-wt/G193` temizlendi. Bağıl link/atıf kontrolü 6 dosyada kırık 0. |

Push/deploy yapılmadı. Görev dışı kirli dosyalar (`.claude/settings.local.json`, `.claude/launch.json`) commit'lere girmedi.

## Bloke

Bloke görev yok.

Plan uyarıları (koşu öncesi):
- **G192:** görev dosyası Rapor bölümünde önceki gecenin `DURUM: BLOKE` kaydı (D9 test çelişkisi) duruyor; KUYRUK satırında BLOKE yoktu, 14.09 kullanıcı kararıyla D9 G195'e ayrıldığı için seçilebilir kabul edildi. Bu gece G192 ilk turda yeşil kapandı; eski BLOKE kaydı görev dosyasında tarihsel olarak kalıyor — gündüz temizlenmesi düşünülebilir.
- **G193:** görev dosyasındaki "Bağımlı" satırı G195'i içermiyor (KUYRUK'ta var); KUYRUK esas alındı.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok; `kabulKarsilanmayan` listelerinin hepsi boş. İşçi notlarından çıkan, insan kararı gerektiren açık sorular:

- **G195 → ayrı görev?** `add_case` status'u normalize etmeden yazıyor, `update_case` tanımadığı metni geçiriyor (`case_manager.py:1512`, `:1120`). Üçlü dışı değer artık 23514 CheckViolation: `add_case` ERROR loglayıp None döner, route 500 verir. Bunu 400'e çeviren görev açılsın mı?
- **G195 → VALIDATE görevi:** prod'da `perf_olcum` üçlü dışı sayısı 0 olunca `VALIDATE CONSTRAINT` ayrı görevi ne zaman açılacak?
- **G195 kenar durumu:** kısıt elle düşürülüp eski değer (ör. TEMYIZ, `case_stage` boş) yazılır ve kısıt geri eklenirse sonraki açılışta madde 50'nin aşama UPDATE'i kısıta takılır. Normal akışta oluşmaz — kabul mü?
- **`scripts/perf_olcum.py:413`** metni "CHECK kısıtı ancak 0 iken eklenebilir" diyor, doğrusu "VALIDATE ancak 0 iken" (G195 ve G193 ikisi de işaretledi, kapsam dışıydı). Düzeltme görevi?
- **G193 → `nginx.conf:44` yorumu** host nginx konfiginin repo dışında olduğunu söylüyor; `infra/nginx/sites-available/default` repoda. Düzeltilsin mi?
- **G193 → CLAUDE.md bayatlıkları:** Komutlar bölümündeki test sayıları (backend artık 3536 passed) ve doküman haritasındaki `nginx.conf:75` atfı bayat. Güncelleme görevi?
- **G193 → genel-bakis §3** diğer `database.py`/`api.py` satır atıfları yeniden doğrulanmadı.
- **Lokal frontend imajı** G182 öncesi (Cache-Control yok, eksik parça 200): `docker compose build frontend && docker compose up -d frontend` koşulsun mu?
- **Açık kararlar (G193 notu):** notes/old_value araması (G190 A/B/C seçenekleri); F11 CaseList için görev yok.
- **G192 izlenecek:** ileride `id = Column(..., index=True)` ile yeni model tablosu eklenirse metadata taramalı test kırmızı olur; ad `_DUSURULECEK_INDEXLER`'e eklenmeli (bilgi, karar değil).

## İzin engelleri

yok

## Atlananlar

Atlanan, zincir hatası veya teslim hatası olan görev yok. Tavan nedeniyle atlanan: yok.
