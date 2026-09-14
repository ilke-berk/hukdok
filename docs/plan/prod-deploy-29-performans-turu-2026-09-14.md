# Prod deploy #29 — performans turu (G182–G197) + VACUUM FULL + önce/sonra ölçümü (14.09.2026)

**Amaç:** prod `c184c9a` (Deploy #28) ile main arasındaki işi canlıya almak — 13.09 bildirim kopya alıcıları
(G178-G181 script'leri yalnız kod olarak), 14.09 performans turu G182–G197, CI protokolü — ve kazancı prod'da
**ölçerek** göstermek. Deploy'dan hemen sonra şişik üç tabloya `VACUUM FULL` uygulanır (kullanıcı kararı 14.09).
Bu doküman **koşu günü işaretlenerek** ilerletilir; bitince `docs/arsiv/`e taşınır.

> **KOŞU KAYDI — 14.09.2026 (pazartesi, MESAİ İÇİ — kullanıcı açık isteğiyle), §1–§7 TAMAMLANDI.** Prod = main
> **906cda2** (Deploy #29); rollback `./rollback.sh c184c9a`; DB dump
> `~/backups/predeploy_906cda2_20260914-111620.dump` (damga UTC = 14:16 TR). §1 CI `success`, aktivite 0,
> 64 commit. §2 test kapısı 3562 passed / 8 skipped (1010 sn), postgres recreate, üç konteyner healthy.
> §3 healthz `906cda2`, ERROR 0, trgm + pg_stat_statements logu, SHOW 384MB / 1.1 / pg_stat_statements / on,
> `ck_cases_status_uclu` `f`, 7 yeni trgm index var, düşmesi gerekenler yok. §8'in host nginx kısmı da koşuldu:
> `https://hukukoid.com/` `no-cache`, `/assets/index-*.js` `public, max-age=31536000, immutable`, eksik parça 404
> (host nginx başlıkları EZMİYOR — G182/F14 kapandı). §5 `VACUUM (FULL, ANALYZE)` ssh dahil 3,3 sn, ERROR 0.
>
> | Ölçüm (tek UNION çalışma süresi, sıcak) | Turgal | 2024/12 | Sulh | TKU-788 | Bora | Seq Scan kol | Buffer (Turgal) |
> | --- | --- | --- | --- | --- | --- | --- | --- |
> | A · önce (c184c9a, 13:25) | 194,4 ms | 131,4 | 127,6 | 126,4 | 135,7 | 12/17 | 24.698 |
> | B · sonra-kod (906cda2) | 47,9 | 40,8 | 46,7 | 40,5 | 38,7 | 5/15 | 9.097 |
> | C · sonra-vacuum | **46,4** | **35,6** | **32,6** | **36,9** | **32,3** | 5-6/15 | 3.238 |
>
> Eski kod UNION'ı istek başına iki kez koşuyordu (G190 D4) → istek başına DB süresi yaklaşık Turgal ~389 → 46 ms.
> Şişme (heap / satır verisi): case_history 15,67 → **1,09** (heap 19 MB → 1,3 MB; toplam 25 MB → 1,8 MB), cases
> 2,67 → **1,06** (toplam 28 → 11 MB), case_foys 2,08 → **1,11** (28 → 14 MB). C'de Turgal'ın kalan seq scan kolları:
> `case_lawyers.name` 9,7 ms (önce Merge Join 50,4), `responsible_lawyer_name` 9,2, `notes` 4,0, `old_value` 1,6
> (önce 4,3), `case_esas_numbers` 0,8, `klasor_no_2`. Raporlar `C:\hukdok-veri\perf\2026-09-14-{once-c184c9a,
> sonra-kod-906cda2,sonra-vacuum-906cda2}`. **Açık:** §8 tarayıcı dumanı (insan), §9 ertesi gün.

> Kod blokları bilerek `text` etiketli: komutlar **sunucuda** (`ssh hukukoid`, `~/hukdok`) koşar; "lokal" yazanlar
> hariç. Deploy ve `VACUUM FULL` yalnız kullanıcı kararıyla, **mesai dışı**.

## 0. Sabit bilgiler

| Ne | Değer | Kaynak |
| --- | --- | --- |
| Prod şu an | **c184c9a** (Deploy #28, 12.09) — rollback hedefi | `/healthz` 14.09 13:24 TR |
| Hedef | koşu günü `origin/main` HEAD'i; CI `success` olmalı (§1) | `ci-kontrol` skill §4 |
| Konteynerler | backend `hukdok_backend`, db `hukudok-postgres` | `deploy.sh:296` |
| Yedek | deploy kendi alır: `~/backups/predeploy_<SHA>_<damga>.dump` | `deploy.sh:52,291-298` |
| Önce ölçümü | `C:\hukdok-veri\perf\2026-09-14-once-c184c9a\perf_prod_<terim>.md` (5 terim) | 14.09 13:25 TR koşusu |
| Doğrulama sırası | `docs/mimari/deploy-ve-altyapi.md` §12 "Deploy sonrası prod doğrulama sırası", §13 | G193, G191 |

**Önce ölçümünün özeti (14.09, c184c9a):** üçlü dışı `cases.status` **0**; arama tek UNION çalışma süresi
Turgal 194,4 · 2024/12 131,4 · Sulh 127,6 · TKU-788 126,4 · Bora 135,7 ms (12/17 kol seq scan; eski kod
UNION'ı istek başına iki kez koşuyor); şişme (heap / satır verisi) case_history **15,68** · cases 2,67 ·
case_foys 2,08; `shared_buffers` 128MB, `effective_cache_size` 4GB, `pg_stat_statements` yok.

## 1. Ön kontroller

**Lokal — CI kapısı** (`deploy-prosedur` §1): `completed/success` değilse deploy YOK.

```text
git fetch origin main
gh run list --commit "$(git rev-parse origin/main)" --json status,conclusion,workflowName
```

**Sunucu — pencere ve aktif kullanım** (0 beklenir):

```text
TZ=Europe/Istanbul date
docker logs hukdok_backend --since 3m 2>&1 | grep -cE 'POST /(process|confirm)'
cd ~/hukdok && git fetch origin && git log --oneline HEAD..origin/main | wc -l
```

## 2. Deploy

`deploy-prosedur` §2 deseni (nohup + ayrı ssh ile izleme):

```text
cd ~/hukdok && nohup ./deploy.sh > /tmp/deploy.log 2>&1 &
tail -30 /tmp/deploy.log
```

Son satır: `✅ Deploy tamam: <SHA> · rollback: ./rollback.sh c184c9a · DB dump: <yol>` (`deploy.sh:401`) — üçü not edilir.

**Deploy'un kendiliğinden yaptıkları:**
- `docker-compose.yml` postgres `command:` değişti (G191) → `up -d --remove-orphans` (`deploy.sh:331`) postgres'i
  **recreate eder**: birkaç saniyelik DB kesintisi; backend havuzu yeniden bağlanır (§13 "Prod'a geçiş").
- `migrate.py` açılışta: `email_recipients.notify_copy` kolonu (13.09), `cases` üzerinde 4 + `case_foys` üzerinde
  3 GIN trigram index (G189/G190, `CONCURRENTLY` DEĞİL — lokalde index başına 24-106 ms), 23 index düşürme
  (G189 3 + G192 20), madde 52 `ck_cases_status_uclu CHECK ... NOT VALID` (G195), `pg_stat_statements` uzantısı (G191).
- Yeni env'ler (`DB_IDLE_TX_TIMEOUT_MS` 60000, `DB_LOCK_TIMEOUT_MS` 5000) varsayılanla gelir; `.env` değişikliği GEREKMEZ.

## 3. Doğrulama A — kod canlıda mı

```text
curl -fsS http://localhost:8001/healthz                                               # "version": "<SHA>"
docker logs --since 10m hukdok_backend 2>&1 | grep -c '"severity": "ERROR"'            # 0
docker compose logs --since 10m backend | grep -i "trgm\|pg_stat_statements"          # "... index'leri hazır", "pg_stat_statements hazır"
docker compose exec -T postgres psql -U hukudok_user -d hukudok -c "SHOW effective_cache_size; SHOW random_page_cost; SHOW shared_preload_libraries;"   # 384MB / 1.1 / pg_stat_statements
docker exec hukudok-postgres psql -U hukudok_user -d hukudok -c "SELECT conname, convalidated FROM pg_constraint WHERE conname = 'ck_cases_status_uclu';"   # tek satır, f
```

- [ ] healthz sürümü · [ ] ERROR 0 · [ ] trgm + pg_stat_statements logu · [ ] SHOW değerleri · [ ] CHECK kısıtı `f`

## 4. Ölçüm B — "sonra (kod)"

Script artık imajda. Aynı 5 terim, önce ölçümüyle aynı yöntem (lokalden ssh ile, çıktı lokale):

```text
# lokal (Git Bash), terim başına:
ssh hukukoid "cd ~/hukdok && docker compose exec -T backend python -m scripts.perf_olcum --term '<terim>'" > "C:/hukdok-veri/perf/2026-09-14-sonra-kod-<SHA>/perf_prod_<terim>.md"
```

Terimler: `Turgal`, `2024/12` (dosya adında `2024_12`), `Sulh`, `TKU-788`, `Bora`.
- [ ] 5 rapor alındı · bölüm 6 "Seq Scan'li kol" 12/17 → beklenen ≤ 6/15 (G190 lokal: 5-6/15)

## 5. VACUUM FULL (kullanıcı kararı 14.09)

`VACUUM FULL` tabloyu ve index'lerini sıkışık yeniden yazar; çalışırken tabloda **ACCESS EXCLUSIVE** kilit tutar
(okuma/yazma bekler). Tablolar küçük (canlı veri 1.2 / 4.9 / 11.3 MB) → saniyeler mertebesi (tahmin, prod'da
ölçülecek). Veri değişmez; geri alınacak bir şey yok, deploy dump'ı yine de yerinde. `pg_repack` prod'da kurulu değil.

```text
docker exec hukudok-postgres psql -U hukudok_user -d hukudok -c "SELECT relname, pg_size_pretty(pg_relation_size(oid)) AS heap, pg_size_pretty(pg_total_relation_size(oid)) AS toplam FROM pg_class WHERE relname IN ('case_history','cases','case_foys') ORDER BY relname;"
docker logs hukdok_backend --since 3m 2>&1 | grep -cE 'POST /(process|confirm)'     # 0 değilse bekle
time docker exec hukudok-postgres psql -U hukudok_user -d hukudok -c "VACUUM (FULL, ANALYZE) case_history, cases, case_foys;"
docker exec hukudok-postgres psql -U hukudok_user -d hukudok -c "SELECT relname, pg_size_pretty(pg_relation_size(oid)) AS heap, pg_size_pretty(pg_total_relation_size(oid)) AS toplam FROM pg_class WHERE relname IN ('case_history','cases','case_foys') ORDER BY relname;"
```

- [ ] önce boyutlar (beklenen heap: case_history 18.9 MB · cases 12.9 MB · case_foys 23.5 MB — 14.09 önce ölçümü; deploy'un index değişiklikleri `toplam`ı oynatır)
- [ ] süre (`time`) · [ ] sonra boyutlar · [ ] `docker logs --since 5m hukdok_backend 2>&1 | grep -c '"severity": "ERROR"'` 0

## 6. Ölçüm C — "sonra (vacuum)"

§4'ün aynısı, dizin `C:/hukdok-veri/perf/2026-09-14-sonra-vacuum-<SHA>/`. Böylece kodun ve VACUUM'un katkısı ayrı görünür.
- [ ] 5 rapor · bölüm 1 şişme oranları · bölüm 6 çalışma süreleri

## 7. Karşılaştırma (lokal, ajan)

Üç ölçümden tek tablo: terim başına bölüm 6 **Çalışma (ms)** ve **Seq Scan'li kol**; bölüm 1 üç tablonun **Oran**'ı;
bölüm 2 ayarlar. Not: eski kod UNION'ı istek başına iki kez, yeni kod bir kez koşar (G190 D4) — istek başına
DB süresi karşılaştırmasında önce değeri ×2 alınır. Sonuç `docs/kararlar/018-...` G190 ekine ve hafızaya yazılır.

## 8. Önbellek + tarayıcı dumanı (insan)

```text
curl -sI https://hukukoid.com/                                  # Cache-Control: no-cache
curl -sI https://hukukoid.com/assets/<index-*.js>              # public, max-age=31536000, immutable (parça adı / sayfa kaynağından)
```

- [ ] host nginx başlığı ezmiyor (`deploy-ve-altyapi.md` §11-§12)
- [ ] **G182:** admin olmayan kullanıcıda ağ sekmesinde `AdminPage-*` / `ReportsPage-*` parçası inmez; deploy öncesinden açık kalmış sekmede bir sayfaya geçince tek yenileme olur
- [ ] **G186** (`gorevler/gorev/G186.md` "El testi notu" 4 madde): Evraklar Select'i, Belge Yükleme "Bugün N" sayacı, e-posta modalı titremesi, "Davayı Güncelle" formu ilk anda dolu / "Yeni Dava Aç"ta boş (kabul edildi)

## 9. Ertesi gün

```text
docker compose logs --since 12h backend | grep -ci "lock timeout"                     # 0 beklenir (G191 yeni hata modu)
docker logs --since 12h hukdok_backend 2>&1 | grep -c '"severity": "ERROR"'
```

- [ ] lock timeout 0 · [ ] ERROR incelemesi · [ ] trafik birikince §13 `pg_stat_statements` en pahalı 10 sorgu
- [ ] 13.09 bildirim sistemi insan adımı (hafıza `bildirim_sistemi_canli_2026-09-13`): meral@ / tel@ kopya alıcı bayrağı yönetim panelinden

## 10. Geri dönüş

`./rollback.sh c184c9a` yalnız İMAJLARI döndürür; git checkout'a ve DB'ye DOKUNMAZ (`rollback.sh:7`, `:43`
`up -d --no-build`). Eski kod yeni şemayla çalışır: yeni index'ler zararsız; CHECK kısıtı yalnız üçlü dışı yazımı
reddeder (eski `add_case` o durumda 500 verir — G196 öncesi hâl); düşen boş-kolon trigram'ları eski aramayı yalnız
yavaşlatır. Postgres parametreleri compose'dan gelir, rollback değiştirmez. DB'yi döndürmek gerekirse tek yol
deploy dump'ıdır (`pg_restore`, ayrı karar). `VACUUM FULL` veri değiştirmediği için geri dönüş gerektirmez.

## 11. Deploy sonrası görev adayları (açılmadı)

- `ALTER TABLE cases VALIDATE CONSTRAINT ck_cases_status_uclu` — önce ölçümünde üçlü dışı 0; §3 sonrası tekrar 0 ise.
- `idx_cases_resp_lawyer_fold_trgm` 4.6 MB, `idx_scan = 0`; arama `cases.responsible_lawyer_name` kolunu seq scan'le
  arıyor (ifade index'le eşleşmiyor) → aramayı index ifadesine hizala ya da index'i düşür (EXPLAIN kanıtıyla).
- `case_lawyers.name` kolu yaygın soyadında en pahalı tek kol (Turgal 50,4 ms, 2.004 eşleşme).
- Bayat kod yorumu atıfları: `backend/routes/processing.py:378` (`nginx.conf:109` → `/refresh` :161),
  `backend/routes/notifications.py:28` (`nginx.conf:62` → `location /api` :116).
