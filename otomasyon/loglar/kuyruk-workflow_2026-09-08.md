# Gece Kuyruğu (workflow) · 2026-09-08

## Özet

6 görev alındı · 5 işaretlendi · 1 bloke · 0 atlandı

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G151 | backend | 8d355d2 | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (3 bulgu) | stash@{0} çakışmasız pop edildi; izinli örnek-değer değişikliği g066/g103 (Kısmen Kabul → Lehe İstinaf, 5 dizgi); 2869 passed / 3 skipped, ruff+mypy temiz, 1 tur. Lokal DB'de `appeal_decisions` 'Karar' satırı 05.09 paket seed'inden duruyor (0/0, silinmedi — insan kararı). Yedek `C:\hukdok-veri\yedek\pre_g151_20260908.dump`. Merge/entegrasyon alanı boş (ana repoda koşuldu). |
| G148 | docs | 10f2d9f | geçti (kırmızı-yeşil uygulanamaz — docs) | GEÇTİ (3 bulgu) | 5 doküman + CLAUDE.md; grep tek-site 0 satır; worktree `C:/dev/hukudok-wt/G148` merge edildi ve temizlendi. Kapsam dışı not: `.env.example:17` `SHAREPOINT_DRIVE_NAME` adını hiçbir kod okumaz (kod `SP_DRIVE_NAME` okur); `docs/plan/veri-ekibi-cevabi-karsilastirma-plani-2026-09-08.md:36` K1 hâlâ 'kuyrukta' + 'Kod tek-site' diyor. İnsan adımları (SharePoint klasör/paylaşım, prod .env, anahtar, e-posta bağlantısı) yapılmadı. |
| G152 | backend | 73838c3 | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (4 bulgu) | 2 tur: tur 1 ruff F811/B007 kırmızı; tur 2 `# noqa` KULLANILMADAN fixture nitelik atamasıyla çözüldü. 2899 passed / 3 skipped. Kararlar: eşik kesim GÜNÜNÜN başı (TR 00:00); `source IS NULL` kullanıcı sayılır; KORUNDU ayrı tür. İzlenecek: `routes/cases.py:299` update_case'e kullanıcı geçirilmiyor (routes kapsam dışıydı, changed_by yedeği 'panel'); veri ekibinden "Veri kesim tarihi" satırı istenmeli — gelmezse paket adındaki teslim günü kesim sayılır, 30.07-04.09 arası kullanıcı değişiklikleri korunmaz. |
| G153 | backend | 855b642 | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (5 bulgu) | 51 yeni test, 2955 passed / 3 skipped, 1 tur. Kök kuralı görev metnine göre genişletildi ('içeren' → 'müvekkili yalnız kökün sigortası olan kart'; ilk kural gerçek veride 0 çözüm verdi). Görevin '20 → ≤3' beklentisi TUTMADI: kalan 10 belirsizin 8'i hekim köklü, 2'si gerçek mükerrer kart (791/792, 747/748) → G154 harita işi. Çelişki 7 (H-6589, DN-11927, Corpus×4, Ergo) — grup şirketi/devir olabilir, ekibe sorulmalı. Lokal DB'ye YAZILMADI (kuru koşu). `docs/mimari/veri-teslim-hatti.md` eşleme sırası güncellenmedi (kapsam dışı, izlenecek). |
| G154 | backend | aae563d | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GEÇTİ (3 bulgu) | 22 yeni test, tam pytest 2977 passed, 1 tur (son parmak izi alanı boş). Kararlar: harita ön geçiş ikizine de girdi; harita föy kaydından önce; kök/müvekkil çelişki kapısı haritadan ÖNCE — H-6589 harita verilse de yazılmaz. İzlenecek: prod'da paket uygulaması sonrası cevaplı script → `--kart-esleme --dry-run` → apply (insan); `--kart-esleme` anlatımı docs/mimari'ye (docs kapsam dışıydı). |

Tüm işaretlenen görevlerde `.claude/settings.local.json` (M) ve `.claude/launch.json` (??) harness dosyaları kirliydi; dokunulmadı, commit'e alınmadı.

## Bloke

### G155 — Karar_Asamalari Başvuru Tarihi (backend)

**Durma sebebi (mekanik):** `test-degistirmek-gerekti` → **testi değiştirmeden geçilemedi, görev tanımı gözden geçirilmeli.** Bu bir başarısızlık değil, hattın DOĞRU çalıştığının kanıtıdır: işçi mevcut testi izinsiz değiştirmedi ve durdu.

**Son parmak izi:**
- `FAILED tests/test_g062_stage_decisions.py::test_model_ve_kolonlar_gorev_taslagina_uygun` — AssertionError: kolon kümesi `==` kilidi, `basvuru_tarihi` fazla
- `FAILED tests/test_g062_stage_decisions.py::test_mukerrer_yazim_gercek_postgreste_duzgun_donuyor` — psycopg2 UndefinedColumn `basvuru_tarihi` (lokal DB migrate edilmedi — ORTAM, kod kusuru değil)

**Denenen yaklaşımlar:**
- Tur 1: kolon + migrasyon (madde 47, koşullu `columns` op) + `_PHOTO_COLUMNS` İSTİNAF/TEMYİZ + CONTENT_FIELDS + ASAMA_SUTUNLARI/_IMZA_ALANLARI + `_basvuru_tarihi_uzlasi` (aşama önce, İstinaf'ta Sheet yedeği) + `asama_kaynakli_kart_alanlari` kart-yolu kapısı + schema alanı + UI 'Başvuru:' satırı; hedef dosyalar 174 passed / 3 failed.
- Tur 2: g155 migrasyon testi `_MIGRATIONS`'ı `case_stage_decisions` op'larına süzerek düzeltildi (`test_migration_path` deseni) → test_g155 16/16 yeşil, ruff+mypy temiz, vitest dosyası 34/34; kalan kırmızı yalnız mevcut testin tam-eşitlik kilidi → duruldu, taslak stash'lendi.

**Kök neden:** `backend/tests/test_g062_stage_decisions.py:67-75` `set(columns.keys()) == {...}` ile `CaseStageDecision` kolon kümesini TAM kilitliyor; görev dosyası `CaseStageDecision.basvuru_tarihi` kolonunu zorunlu kılıyor. Tek çıkış o kümeye `'basvuru_tarihi'` eklemek (tek satırlık kilit güncellemesi) — göreve bu izin yazılmamıştı (G138/G139/G151 dersi tekrar).

**Tasarım kararı (taslakta):** `KART_ALANLARI['istinaf_basvuru_tarihi']` KALDI (test_g123 kilitliyor); iki yazıcı salınımı, paketin İstinaf satırı Başvuru Tarihi taşıyorsa kart yolunun alanı atlamasıyla önlendi; aşama değeri boşken yedek Sheet değeri iki yoldan da aynı yazılır, ikinci koşu 0 (testli).

**Worktree:** yok (ana repoda koşuldu). HEAD değişmedi (bb8d500). Taslak: `git stash list` → stash@{0} 'G155 taslak - test izni bekliyor (test_g062 kolon kilidi)'; `git stash pop` ile döner. (stash@{1} eski, ilgisiz WIP — dokunulmamalı.) Çalışma alanında yalnız `gorevler/gorev/G155.md` (DURUM: BLOKE raporu) + harness dosyaları kirli. Commit yok, kapı/denetim koşulmadı.

**Önerilen sonraki adım:**
1. G155 görev dosyasına açık izin yaz: "test_g062 kolon kümesi kilidine `basvuru_tarihi` eklenebilir".
2. Yeniden kuyruğa al; işçi ÖNCE `git stash pop`, ardından pytest'ten ÖNCE `docker compose exec -T backend python migrate.py` (ya da backend recreate) — dbtest lokal Postgres'te yeni kolonu arıyor.
3. Tam pytest + frontend lint/tsc bu koşuda koşulmadı; yeniden koşuda tamamlanmalı.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok. `kabulKarsilanmayan` maddeleri (yalnız G155) soru olarak:

- **G155 / kabul 1:** "Kolon + migrasyon; Başvuru Tarihi okunur ve fotoğraflanır; sütun yok paketle geriye uyumlu (test)" — taslakta yapıldı ve testli ama commit'lenmedi. SORU: `test_g062` kolon-kümesi kilidinin `basvuru_tarihi` ile güncellenmesine izin veriliyor mu?
- **G155 / kabul 2:** "Sheet yedek kaynağı yalnız aşama değeri boşken yazar (test)" — taslakta yapıldı, commit'lenmedi. SORU: aynı izinle birlikte kabul ediliyor mu?
- **G155 / kabul 3:** "ruff + mypy temiz; frontend vitest/lint/tsc; pytest özet satırı" — ruff/mypy temiz, vitest dosyası yeşil; tam pytest, frontend lint ve tsc BLOKE nedeniyle koşulmadı. SORU: yeniden koşuda migrate adımı görev metnine yazılsın mı?

Ek karar soruları (işaretlenen görevlerin notlarından):
- G151: lokal `appeal_decisions` 'Karar' satırı (0/0) silinsin mi?
- G152: veri ekibinden "Veri kesim tarihi" satırı istenecek mi (SOZLESME.md plan #13)?
- G153: 7 kök/müvekkil çelişkisi (H-6589, DN-11927, Corpus×4, Ergo) — grup şirketi/devir mi, ekibe sorulsun mu?

## İzin engelleri

yok (altı görevin `izinEngelleri` listeleri boş).

## Atlananlar

yok — `atlandi`/`zincirHatasi`/`teslimHatasi` alanı dolu görev yok; tavan nedeniyle atlanan yok.

## Plan uyarıları (koşu öncesi)

- G151: KUYRUK satırında 'BLOKE' geçmiyordu (yalnız 'YENİDEN KUYRUKTA'); stash@{0} pop bu koşuda yapıldı, görev tamamlandı.
- G155 dosya kapsamı koşullu olarak `frontend/src/**/CaseTracking*` içeriyor — backend bandı; paralel frontend koşusu olmadığı için sorun çıkmadı.
- G161 kapsam ifadesi belirsiz ('dava-acma-akisi.md ya da ilgili mimari doküman'); üç görevi beklediği için bu koşuda sıraya girmedi.
- Zincir seri: G151→G152→G153→G154→G155→...; G155'te durdu, G156-G160 bu koşuda alınmadı.
