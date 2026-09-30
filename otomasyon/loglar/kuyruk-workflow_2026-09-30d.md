# Gece Kuyrugu (workflow) · 2026-09-30d

## Özet

6 görev alındı · 3 işaretlendi · 2 bloke · 1 atlandı

Tavan nedeniyle atlanan: yok. Push/deploy yapılmadı.

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G236 — Yeni kartta numarayı sunucu verir + `GET /api/cases/ofis-no-onizleme` + `istek_kimligi` tekrar koruması (migrasyon 57) | backend | `72a657d` | geçti (test temiz; kırmızı-yeşil uygulanamaz; ihlal yok) | GEÇTİ (6 bulgu) | 2 tur. Bağımsız koşuda pytest 4004 passed / 15 skipped, ruff + mypy temiz. Verideki `mergeYapildi=false`, worktree yok. Lokal DB'ye migrasyon 57 uygulandı. |
| G238 — `scripts/ofis_no_gocu.py`: kuru koşu + `--apply` (işçi yalnız lokal kuru koşu) | backend | `436e7a2` | geçti (test temiz; kırmızı-yeşil kanıtlandı; ihlal yok) | GEÇTİ (5 bulgu) | 2 tur. Yeni test dosyası 54/54 yeşil. Verideki `mergeYapildi=false`, worktree yok. `--apply` koşulmadı; üç kullanıcı kararı bekliyor (aşağıda). |
| G237 — NewCase/QuickCase/Intake numarayı önizler, üretmez; `caseNumberUtils` üreticisi kalkar; kayıt isteği `istek_kimligi` taşır | frontend | `7025a7f` | geçti (test temiz; kırmızı-yeşil kanıtlandı; ihlal yok) | GEÇTİ (6 bulgu) | 1 tur. vitest 1302 passed / 121 dosya, eslint temiz, `tsc -b --force` çıkış 0. Merge yapıldı, entegrasyon yeşil, worktree `C:/dev/hukudok-wt/G237` temizlendi. |

### İşaretlenen görevlerden sabah incelemesine kalan notlar

**G236**
- Taşınan testler: `test_g196_status_kapisi.py`, `test_faz3_confirm_idempotency.py` (bölüm 3: 8 test, bölüm 4: 4 test), `test_case_intake_commit.py`. Silinen test yok, assert sayısı azalmadı, skip/xfail eklenmedi.
- Kimlik intake'te `case.istek_kimligi` olarak gelir (`schemas_intake.py` kapsam dışıydı, dokunulmadı).
- `add_case` imzası değişmedi; sunucu tahsisi `ofis_no_sunucudan` bayrağıyla açılır. Doğrudan çağrılar (`scripts/kartsiz_foy_kart_ac.py`, mevcut testler) eski yolda.
- Önizleme ucuna görev tanımında OLMAYAN opsiyonel `sigortali` parametresi eklendi; yanıtta ek açıklama alanı var.
- Sunucunun verdiği numarada `ix_cases_tracking_no` çakışması 409 değil 500 + ERROR (sayaç tutarsızlığı) — G238 göçü sayaçları mevcut numaralarla hizalamalı.
- PUT'ta `tracking_no` sessizce yok sayılır.
- Kapsam dışı, düzeltilmedi: `docs/mimari/dava-acma-akisi.md` satır 101-112 hâlâ eski `find_idempotent_commit_match` / `TRACKING_NO_COLLISION` akışını anlatıyor; CLAUDE.md test sayıları eski. Önizleme "Diğer Davalı" hekimini görmez (kayıt numarası önizlemeden farklı çıkabilir).
- İşçi, "kapsam dışı kirli dosya → BLOKE" kuralını izlenmeyen `.claude/launch.json` için uygulamadı (dokunmadı, commit'e girmedi).

**G238**
- Sapmalar: görev Doğrulama'sındaki `docker compose build backend && up -d backend` KOŞULMADI (lokal override bind-mount, yalnız backend recreate lokal nginx'te bayat upstream 502'si üretiyor). `avukat_envanteri --karsilastir` koşulmadı (DB'ye yazan adım yok). İki küçük düzeltme bir kez shell içinden Python (açık utf-8) ile dosyaya yazıldı — Edit aracı yerine; Türkçe içerik doğrulandı.
- Tasarım: kategori zinciri basamak 1'e "aynı adlı müvekkil kaydının TEK kategorisi" eklendi (13.343 kart), çünkü CLIENT taraflarının yalnız 107/16.177'si müvekkil kaydına bağlı.
- Exact aramada `case_history.old_value` kolu yok — eski numara yalnız normal aramada bulunur (`case_manager` kapsam dışı).
- Rapor dizini varsayılanı konteynerde `/tmp/ofis-no-gocu` (CSV müşteri adı taşır).

**G237**
- KAPSAM: `frontend/src/lib/caseIntake.ts` görevin dosya kapsamında YOK ("Dokunma"da da yok) ama dokunuldu — yalnız tip + yorum (`tracking_no` çıktı, `istek_kimligi` ve `CommitResult.case.reused` eklendi). Denetim kapsam ihlali saymadı; karar insanın.
- ARAÇ SAPMASI: `NewCase.tsx`'te tek satır Edit ile eşleşmedi, Git Bash `sed` ile silindi (ASCII satır; dosya UTF-8 doğrulandı).
- `caseNumberUtils.ts` silinmedi (`YARGI_TURLERI`, `ofisNoOnizlemeSorgusu`, `yeniIstekKimligi` orada).
- Bayat yorumlar kapsam dışı dosyalarda kaldı: `hooks/useCaseIntake.ts:326-328`, `lib/caseIntakeFields.ts:86`. `IntakeResultStep` `reused` durumunda hâlâ "Dava oluşturuldu" başlığı gösteriyor.
- Backend `GET /api/cases/client-sequence` ucu artık istemcisiz (kaldırması G239'un işi — bloke).
- Tarayıcıda elle doğrulama YAPILMADI.

## Bloke

### G241 — Admin panelinde ofis no kod listeleri (frontend)

- **Durma sebebi:** `ana dizin kirli - merge ertelendi`. İş bitti ve denetimden geçti, ama teslim (merge) yapılamadı; bu yüzden görev İŞARETLENMEDİ (`isaretlendi=false`, `mergeYapildi=false`, entegrasyon `uygulanamaz`).
- **Son parmak izi:** yok (işçi doğrulaması yeşil: `durmaSebebi=yesil`, 1 tur).
- **Denenen yaklaşımlar:** Tur 1 — yeni panel + api yardımcısı + AdminPage sekme bağlantısı + testler; test/lint/tsc ilk koşuda yeşil.
- **Kapı / denetim:** kapı geçti (test temiz, kırmızı-yeşil kanıtlandı, ihlal yok); denetim GEÇTİ (5 bulgu) — vitest 123 dosya / 1321 test yeşil, lint temiz, `tsc -b --force` çıkış 0.
- **Kök neden:** veride teşhis kaydı yok (`teshis=[]`). Blokenin sebebi koda değil ana çalışma dizininin durumuna ait. Koşu verisinden görülen kirli dosyalar: G239'un bıraktığı commit'lenmemiş `gorevler/gorev/G239.md` (DURUM satırı) ve izlenmeyen `.claude/launch.json`.
- **Worktree (korunuyor):** `C:/dev/hukudok-wt/G241`, dal `gorev/G241`.
- **DİKKAT — iki commit:** kod+test `4952be3`, görev raporu ayrı commit `c12d8ba` (dal ucu). Teslim dal ucunu (`c12d8ba`) birleştirmeli.
- **Önerilen sonraki adım:** ana dizini temizle (`gorevler/gorev/G239.md` değişikliğini commit'le ya da geri al; `.claude/launch.json` için karar ver), sonra `gorev/G241` dal ucunu merge et, entegrasyon testini koş, KUYRUK'ta işaretle. Kodun yeniden yazılması gerekmiyor.
- **İşçi notları:** mevcut Kategoriler sekmesine dokunulmadı; kodlu yeni kategori iki adımla eklenir (POST `/api/config/client_categories`, sonra PATCH `/api/admin/kategori-kodlari/{code}`) — ikinci adım reddedilirse kategori kodsuz kalır, panel bunu açıkça söyler (atomik uç backend işi, kapsam dışı). Kişi/kurum örnek ayrımı backend `KISI_KATEGORILERI` kümesinin frontend kopyasıyla. Canlı tarayıcıda denenmedi.

### Testi değiştirmeden geçilemedi — görev tanımı gözden geçirilmeli

Bu başlık bir başarısızlık değildir: işçi, izin listesi dışındaki testleri değiştirmek yerine durdu. Hattın doğru çalıştığının kanıtıdır.

#### G239 — Eski formatı ayrıştıran kod uyarlanır; client-sequence + `idx_cases_tracking_name_block` kalkar (backend)

- **Durma sebebi:** `test-degistirmek-gerekti` — testi değiştirmeden geçilemedi, görev tanımı gözden geçirilmeli.
- **Son parmak izi:** yok (kod yazılmadı, doğrulama koşulmadı; `turSayisi=0`, `verify=calistirilmadi`).
- **Denenen yaklaşımlar:** kod yazmadan önce kapsamdaki sembollerin test bağımlılıkları tarandı; izin listesi dışı iki dosyanın eski davranışı sabitlediği görüldü, uygulamaya geçilmedi.
- **Kök neden:** veride teşhis kaydı yok (`teshis=[]`). İşçinin tespiti — görevin kabul kriterleri, taşıma izni verilmemiş iki test dosyasının beklentisiyle doğrudan çelişiyor:
  1. `backend/tests/test_g043_index_ve_avukat_filtresi.py` — `YENI_INDEXLER` listesi `idx_cases_tracking_name_block`'u içeriyor; index'in var olmasını ve `_DUSURULECEK_INDEXLER`'de OLMAMASINI şart koşan testler: index op'unda tam 1 kez bulunma testi, `test_tracking_no_index_i_route_ile_ayni_ifadeyi_kullanir`, `test_yeni_indexler_dusurulecekler_listesiyle_catismiyor`, `test_yeni_indexler_sifirdan_kurulumda_semada_var`, `test_fonksiyonel_index_tracking_no_sorgusunda_kullaniliyor`.
  2. `backend/tests/test_g236_ofis_no_kayit.py::test_client_sequence_ucu_hala_calisir` — uçtan 200 + `{sequence: 1}` bekliyor; kabul kriteri 404 istiyor.
- **Worktree:** yok. Ana çalışma ağacında commit'lenmemiş tek değişiklik `gorevler/gorev/G239.md` (DURUM satırı) — G241 merge'ünü erteleten kirlilikle ilişkili.
- **Ön tarama bulguları:** frontend'de `client-sequence` çağıranı yok; `max_tracking_sequence`'ın kalan tek üretim çağıranı `scripts/kartsiz_foy_kart_ac.py` (kapsam içi). Ortam hazırdı (konteyner sağlıklı).
- **Önerilen sonraki adım:** iki test dosyasını G239 taşıma iznine ekleyip görevi yeniden koşmak (insan kararı).

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok (tüm görevlerde `teshis` boş). Aşağıdakiler karşılanmayan kabul maddeleri ve işçi notlarından çıkan sorulardır.

**G239 — karşılanmayan kabul maddeleri (hiçbiri uygulanmadı):**
1. `rg` substr/split kalıntısı boş olacak — izin verilmeden uygulanamadı; taşıma izni genişletilsin mi?
2. `cevapli_kart_eslemesi` iki formatı da tanıyacak — aynı soruya bağlı.
3. Mükerrer kart raporu göç öncesi/sonrası aynı grupları verecek — aynı soruya bağlı.
4. `kartsiz_foy_kart_ac` yeni format + sayaç — aynı soruya bağlı.
5. `/api/cases/client-sequence` 404 dönecek — G236'nın eklediği `test_client_sequence_ucu_hala_calisir` testi taşınabilir mi (200 → 404)?
6. Index düşürme migrasyonu idempotent — `test_g043_index_ve_avukat_filtresi.py` içindeki `idx_cases_tracking_name_block` beklentileri taşınabilir mi (var olmalı → düşürülmüş olmalı)?

**G238 — `--apply` öncesi kullanıcı kararı gerekenler:**
1. 265 müvekkilsiz kart (eski kod: D1 73, S4 49, S1 47, S2 35, S3 23, X1 17, S6 12, S7 7, S0 2) varken `--apply` DURUR. Müvekkil mi eklenecek, yoksa eski koddan numara verme kuralı mı isteniyor (script değişikliği)?
2. SG'ye düşen 26 kart doğru mu? 10'u S0 kodlu, tek müvekkili KİŞİ olan kart (şartname gereği SG); Ergo 11, Pramit Sigorta Aracılık 3, Allianz 1, Yapıkredi 1.
3. Sigortacı müvekkilli 11.280 kartın 6.315'inde sigortalı bulunamadı (bloksuz numaralanır) — kabul mü?

**G237:**
- `frontend/src/lib/caseIntake.ts` kapsam listesinde yokken dokunuldu (yalnız tip + yorum). Kabul mü?

**G241:**
- Kodlu kategori ekleme iki adımlı ve atomik değil; atomik bir backend ucu ayrı görev olarak açılsın mı?

**G236:**
- Önizleme ucuna görev tanımında olmayan `sigortali` parametresi eklendi. Kabul mü?
- Sunucu numarasında `ix_cases_tracking_no` çakışmasının 409 yerine 500 + ERROR dönmesi istenen davranış mı?

**Plan uyarıları (koşu öncesi):**
- G236: Rapor bölümünde önceki koşudan "DURUM: BLOKE" kaydı var (test taşıma izni eksikti); görev dosyasındaki "İnsan kararı 30.09" bölümü ile çözüldü, KUYRUK satırında BLOKE yok — seçilebilir.
- G241: dosya kapsamında adı belirsiz kalemler var (yeni hook/api yardımcısı, mevcut müvekkil kategorisi yönetim bileşeni, testler) — `dosya[]` yalnız adı verilen yolları içerir.
- G237/G239: dosya kapsamında "ilgili testler" adsız; `dosya[]` yalnız adı verilen yolları içerir.

## İzin engelleri

yok (altı görevin tamamında `izinEngelleri` boş).

## Atlananlar

- **G240** — CLAUDE.md + dava-acma-akisi + veri-teslim-hatti güncellenir; veri ekibine not taslağı (docs). Sebep: `bagimlilik bu kosuda tamamlanmadi: G239, G241`. Uygulanmadı, commit yok. Veride worktree `C:/dev/hukudok-wt/G240` kayıtlı ve `worktreeTemizlendi=false` — dizin duruyorsa elle temizlenmeli.

Zincir hatası: yok. Teslim hatası: yok (G241'in merge'ü `teslimHatasi` olarak değil, bloke olarak kaydedildi).
