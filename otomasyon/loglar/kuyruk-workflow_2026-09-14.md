# Gece Kuyruğu (workflow) · 2026-09-14

## Özet

6 görev alındı · 6 işaretlendi · 0 bloke · 6 atlandı (tavan)

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G183 · `scripts/perf_olcum.py` salt okunur performans ölçüm raporu | backend | `600a90f` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (4 bulgu) | 2 tur. pytest 3472 passed / 3 skipped, mypy temiz. Çıplak `ruff check .` konteynerde 6 hata veriyor; hepsi git dışı `calibration-data/_g179/ek3_cevapla.py` (bind-mount). Veride mergeYapildi=false, entegrasyon alanı yok, worktree yok. |
| G182 · Route düzeyinde kod bölme + sonner statik + nginx asset önbelleği | frontend | `5b79f61` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (5 bulgu) | 2 tur. vitest 953 test, 58 JS parçası, giriş 203 kB gzip. Merge yapıldı, entegrasyon yeşil, worktree temizlendi. Karşılanmayan kabul maddesi var (aşağıda). |
| G189 · Trigram index'ler gerçek kolonlara | backend | `56afafb` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (3 bulgu) | 3 tur. pytest 3479 passed / 3 skipped. Bedel: `idx_cases_tku_no` düşünce `case_relations_auto.py:240` seq scan'e döndü (lokal 0,1 → 3,8 ms). Veride mergeYapildi=false, worktree yok. |
| G184 · `useConfigList(key)` + `refetchOnWindowFocus:false` | frontend | `37abb7c` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (3 bulgu) | 1 tur. 963 test. Global varsayılan config dışı 3 sorguyu da etkiler (useClients, ClientList policies, usePartyCheck odakta tazelenmez). Merge yapıldı, entegrasyon yeşil, worktree temizlendi. |
| G187 · AdminPage: 13 effect yerine render'da türetme | frontend | `374083b` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (5 bulgu) | 2 tur. 970 test. Bilinçli davranış değişikliği: sıralama kaydı hata verirse sunucu sırasına dönülüyor. Merge yapıldı, entegrasyon yeşil, worktree temizlendi. |
| G185 · Ağır useConfig tüketicileri useConfigList'e | frontend | `4ee7550` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (4 bulgu) | 3 tur. 984 test. NewCase ve IntakeReviewStep useConfig()'te kaldı (yorum notu aşağıda). Merge yapıldı, entegrasyon yeşil, worktree temizlendi. |

### Sabah bakılacak izlenecekler (işçi notlarından)

- **Konteyner içi ruff kapısı kırmızı** (G183, G189): `backend/calibration-data/_g179/ek3_cevapla.py` bind-mount'lu veri dizini, git'te 0 dosya. `ruff check . --extend-exclude calibration-data` temiz. Bu dizin bağlıyken çıplak `ruff check .` kırmızı döner; ruff exclude ayarına ya da dizin konumuna ayrıca bakılmalı.
- **G182:** prod'da host nginx'in `Cache-Control`'u ezip ezmediği ölçülmeli (`curl -sI https://<alan>/assets/<parça>.js` ve `/`). MSAL oturumlu tarayıcı dumanı yapılmadı: admin olmayan kullanıcıda AdminPage/ReportsPage parçası inmemeli, eski açık sekmede tek yenileme olmalı. `docs/mimari`'de nginx önbellek anlatımı yok.
- **G187:** `invalidateType` `emails` tipini tanımıyor (typeToKey'de yalnız `email_recipients`), e-posta alıcısı düzenleme/silme/sıralama sonrası liste önbelleği yenilenmiyor; ayrı görev önerildi. Tarayıcıda sürükle-bırak dumanı yapılmadı.
- **G185:** önerilen takip görevi: `useConfig.ts`'e `useRequiredCaseFields` eklenip QuickCaseModal'daki kopya kaldırılsın, NewCase ve IntakeReviewStep 32 → 8 uca taşınsın. Index sayfası analiz tamamlanınca AnalysisResults üzerinden hâlâ 32 listeyi yüklüyor.
- **G189:** `ix_cases_tku_no` düşürülmedi (kaynağı `models.py index=True`, Dokunma listesinde); yalnız sıfırdan kurulumda oluşur.
- **G183, G189 merge durumu:** veride `mergeYapildi=false`, `entegrasyon=null`. Bu iki backend görevinin commit'lerinin main'e nasıl girdiği sabah git log ile teyit edilmeli.

## Bloke

Bloke görev yok.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok. Karşılanmayan kabul maddeleri:

- **G182 — SORU:** Kabuldeki `docker compose build frontend && docker compose up -d frontend` + `localhost:8080` curl adımı koşulmadı (frontend bandında compose yasak). Eşdeğeri koşuldu: tek seferlik `docker run nginx:alpine` 127.0.0.1:18182 üzerinde worktree `nginx.conf` + `dist` salt okunur bağlı, `curl -sI` çıktıları rapora yazıldı. Bu eşdeğer ölçüm kabul sayılacak mı, yoksa compose'lu 8080 ölçümü deploy öncesi insan adımı olarak mı yapılacak?
- **G185 — SORU:** NewCase ve IntakeReviewStep "8+" istisnasıyla useConfig()'te bırakıldı: 7 liste + `required_case_fields` = 8 uç. Bu, liste sayısıyla değil uç sayısıyla 8+. Bu yorum kabul ediliyor mu, yoksa önerilen `useRequiredCaseFields` takip görevi açılsın mı?
- **G185 — SORU:** Kriter testlerin "mevcut test dosyasına ek" olmasını söylüyordu; 8 bileşenin hiçbirinde mount testi olmadığından her taşınan bileşenin yanına yeni `*.config.test.tsx` açıldı. Bu yorum kabul ediliyor mu?

## İzin engelleri

yok

## Atlananlar

Tavan nedeniyle atlanan (bu koşuda alınmadı, kuyrukta bekliyor):

- G190 — tavan
- G191 — tavan
- G186 — tavan
- G188 — tavan
- G192 — tavan
- G193 — tavan

`zincirHatasi` ya da `teslimHatasi` olan görev yok. Plan uyarısı yok.
