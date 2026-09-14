# Gece Kuyruğu (workflow) · 2026-09-14-2

## Özet

6 görev alındı · 2 işaretlendi · 2 bloke · 2 atlandı

Tavan nedeniyle atlanan: yok · Plan uyarıları: yok · Push/deploy yapılmadı.

## İşaretlenenler

| Görev | Bant | Commit | Kapı | Denetim | Not |
| --- | --- | --- | --- | --- | --- |
| G190 · Arama tek koşu: id kümesi bir kez, boş legacy kollar çıkar, kanıtlı trgm index kararı (D1, D4) | backend | `8695382` | geçti · test temiz · kırmızı-yeşil kanıtlandı · 0 ihlal | GEÇTİ (5 bulgu) | 2 tur (tur 1: tam `ruff check .` repo dışı `calibration-data/_g179/ek3_cevapla.py` yüzünden kırmızı; tur 2 `--extend-exclude calibration-data` ile yeşil). pytest 3496 passed / 3 skipped, mypy temiz. Dört trgm index (court/subject/esas_no/tracking_no) `_TRGM_INDEXES`'e eklendi ve `_DUSURULECEK_INDEXLER['cases']`'tan çıkarıldı; CLAUDE.md "geri eklenmedi" iddiası düzeltildi. mergeYapildi=false, worktree yok. Kullanıcı kararı açık (aşağıda). |
| G186 · Rerender: CaseDetails DocCard modül düzeyine, Index lazy state + primitif effect bağımlılığı, NewCase düzenleme modu tek render (F5, F8, F9, F10) | frontend | `a6e735c` | geçti · test temiz · kırmızı-yeşil kanıtlandı · 0 ihlal | GEÇTİ (5 bulgu) | 1 tur; vitest 86 dosya / 992 passed, lint temiz, `tsc -b --force` 0. merge yapıldı, entegrasyon yeşil, worktree `C:/dev/hukudok-wt/G186` temizlendi. Tarayıcı el testi YAPILMADI (kabul kriteri 5 kısmen). Bilinçli davranış farkı: düzenleme formu açıkken state'siz aynı route'a geçişte artık boş yeni form geliyor. |

### Deploy/izleme notları (işaretlenenlerden)

- **G190:** `init_db` dört GIN index'i CONCURRENTLY olmadan kurar (lokalde 24-106 ms; prod'da daha uzun sürebilir). Sonraki teslimde aktarım süresi izlenmeli; prod'da `perf_olcum --term` tekrarı önerilir. Lokal DB'de dört index ölçüm sırasında elle kuruldu, reddedilen iki geçici index düşürüldü.
- **G186:** `getTodayUploads` artık kullanılmıyor ama dışa verim olarak bırakıldı. 4 maddelik el testi kontrol listesi görev raporunda.

## Bloke

### G191 · Bağlantı/sunucu ayarları: idle_in_transaction + lock_timeout env'li, compose postgres parametreleri, pg_stat_statements (D5, D6)

#### Testi değiştirmeden geçilemedi, görev tanımı gözden geçirilmeli

Bu bir başarısızlık değil: hat mevcut bekçi testlerine dokunmadan duramayacağını fark edip doğru şekilde durdu. Uygulama yapılmadı (uygulandi=false, verify çalıştırılmadı, 0 tur, commit yok).

- **Durma sebebi:** `test-degistirmek-gerekti`
- **Son parmak izi:** `test_faz3_e_hardening.py::test_engine_created_with_timeouts` kaynak-metin kilidi (satır 129) + `test_build_connect_args_*` tam eşitlik testleri (satır 109-122)
- **Denenen yaklaşımlar:**
  - Kilit testleri okundu ve koşuldu (`-k build_connect_args/engine_created_with_timeouts/migrate_sets_statement` → 4 passed; baz yeşil, kilit doğrulandı).
  - REDDEDİLDİ (denenmedi): idle/lock'u SQLAlchemy `do_connect` olayıyla `cparams` options'a eklemek — kaynak-metin bekçisini atlatmak için yapılandırmayı `create_engine`'den gizlemek olurdu.
  - REDDEDİLDİ: `PGOPTIONS` env / URL `?options=` — `connect_args` options verildiğinde yok sayılır/ezilir.
  - Diğer kilitler tarandı (`test_faz2_logging` compose, `test_g147` .env.example, `test_perf_olcum`, migrate muafiyet testi) — hiçbiri engel değil.
- **Kök neden (teşhis):** teşhis kaydı boş. Olgusal durum: görev `create_engine` çağrısına yeni bağlantı parametreleri eklemeyi istiyor, oysa `test_faz3_e_hardening.py:129` bu çağrının kaynak metnini birebir kilitliyor; görev tanımı bu testin güncellenmesine izin vermiyor.
- **Worktree:** yok (korunan worktree kaydı yok). `gorevler/gorev/G191.md`'deki BLOKE kaydı commit edilmedi, ana çalışma ağacında duruyor (G113 emsali).
- **Önerilen sonraki adım:** `test_faz3_e_hardening.py:129`'daki bekçi metnini `connect_args=_build_connect_args(DB_STATEMENT_TIMEOUT_MS, idle_ms=DB_IDLE_TX_TIMEOUT_MS, lock_ms=DB_LOCK_TIMEOUT_MS)` olarak güncelleme iznini görev dosyasına açıkça yaz. Yeni parametrelerin varsayılanı 0 olursa 109-122'deki iki birim test değişmeden kalır. Sonra G191'i kuyruğa geri koy.
- **KAPSAM DIŞI RİSK BULGUSU:** `idle_in_transaction_session_timeout=60 s` açılınca `services/teslim_cevap.py:487-545` riske girer: `eslesme_csv_uret` sorgusundan sonra SharePoint yükleme döngüsü aynı açık transaction'da koşuyor, commit en sonda. Yüklemeler 60 sn'yi aşarsa commit düşer ve `cevap_yuklendi` yazılmaz. G191 yeniden koşmadan önce bu yol ele alınmalı. Taranan diğer yollar (upload_queue, conversion_retry, case_intake merge, rapor asistanı, aktarımda xlsx okuma) oturumu uzun işten önce kapatıyor.

### G188 · theme-provider try/catch + ErrorBoundary içine; YetkiBelgesi TC önbelleklenmez, sicil/ad sessionStorage :v1 (F6, F7)

- **Durma sebebi:** görevin kendisi yeşil (`durmaSebebi=yesil`, 1 tur, commit `773a3e5`, kapı geçti, denetim GEÇTİ / 3 bulgu); bloke sebebi **"ana dizin kirli - merge ertelendi"**. entegrasyon=uygulanamaz, mergeYapildi=false, işaretlenmedi.
- **Son parmak izi:** yeşil — 88 test dosyası / 1005 passed; lint 0; `tsc -b --force` 0
- **Denenen yaklaşımlar:**
  - Önce 13 yeni test yazıldı, düzeltilmemiş koda karşı koşuldu: 11 kırmızı (doğru sebeple), 2 regresyon bekçisi yeşil.
  - Kırmızı turda test hatası: `setTheme('system')` jsdom'da olmayan `matchMedia`'ya gidiyordu; test `'light'` ile düzeltildi, kod yoluna dokunulmadı.
  - Uygulama: theme-provider `readStoredTheme` + `setItem` try/catch; `App.tsx`'te ThemeProvider ErrorBoundary içine alındı; YetkiBelgesiModal önbelleği TC'siz `{ad,sicil}` olarak sessionStorage `:v1`'e taşındı, eski kalıcı anahtar açılışta siliniyor.
- **Kök neden (teşhis):** teşhis kaydı boş. Merge ana dizin kirli olduğu için yapılmadı. Koşu başında kirli dosyalar `.claude/settings.local.json` (M), `.claude/launch.json` (??) ve G191'in commit edilmeyen BLOKE kaydı `gorevler/gorev/G191.md` (M) idi — muhtemel tetikleyici bunlar (veride kesin dosya adı yok).
- **Worktree:** `C:/dev/hukudok-wt/G188` — KORUNUYOR (temizlenmedi).
- **Önerilen sonraki adım:** ana dizini temizle (G191.md kaydını commit'le ya da kararlaştır; harness dosyalarını stash'le/ignore et), sonra `773a3e5`'i main'e merge et, frontend paketini ana dizinde yeniden koş (vitest/lint/`tsc -b --force`), görevi elle işaretle ve worktree'yi kaldır.
- **Kapsam dışı notlar:** theme-provider `'system'` temasında `window.matchMedia` korumasız çağrılıyor (artık boundary içinde → beyaz ekran yerine hata ekranı). Eski TC önbelleği prod'da yalnız ilgili tarayıcıda modal bir kez açılınca silinir; tam süpürme istenirse ayrı görev.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok. Karşılanmayan kabul kriterleri ve açık kullanıcı kararları:

**G191** (bloke, hiçbiri uygulanmadı):

1. Birim test `_build_connect_args(30000, idle_ms=60000, lock_ms=5000)` bekçi kilidi yüzünden yazılamadı — `test_faz3_e_hardening.py:129` bekçisini güncelleme izni verilecek mi?
2. dbtest `SHOW idle_in_transaction_session_timeout` (env / migrate=0) yapılmadı — izin sonrası aynı kapsamla yeniden koşulsun mu?
3. dbtest iki bağlantılı `lock_timeout` senaryosu yapılmadı — kapsamda kalsın mı?
4. Lokal stack recreate sonrası `SHOW effective_cache_size` / `shared_preload_libraries` + pg_stat_statements doğrulaması yapılmadı — gece bandında recreate izni verilecek mi, yoksa gündüz elle mi?
5. `docs/mimari/deploy-ve-altyapi.md` yeni env/compose/pg_stat_statements bölümü yazılmadı — G193 doküman görevine mi bırakılsın?
6. Bellek notu (effective_cache_size planlayıcı ipucu, 512m ilişkisi) yazılmadı — aynı soru.
7. `services/teslim_cevap.py:487-545` uzun transaction riski G191'den önce ayrı görevle mi kapatılsın?

**G186** (işaretlendi):

8. Kriter 5 kısmen: tarayıcıda el testi yapılmadı (MSAL + backend gerekiyor, bantta docker yasak). 4 maddelik kontrol listesini kim, ne zaman koşacak? Düzenleme formundan state'siz "Yeni Dava Aç"a geçişte boş form gelmesi kabul mü?

**G190** (işaretlendi, notlardan):

9. Normal modda `notes` / `case_history.old_value` arama kolları için: (A) aramadan çıkar, (B) `old_value` trgm index ekle (152 kB ölçüldü), (C) olduğu gibi bırak — hangisi?

## İzin engelleri

yok

## Atlananlar

| Görev | Bant | Sebep |
| --- | --- | --- |
| G192 · Düşük etkili: offset tavanı 422, N+1 → in_(), upload_queue vade filtresi SQL'de, PK index ikizleri kalkar, cases.status CHECK NOT VALID (D8-D11, D15) | backend | bağımlılık bu koşuda tamamlanmadı: G191 |
| G193 · Performans turu dokümantasyonu: CLAUDE.md, deploy-ve-altyapi, genel-bakis, karar 018, denetim raporu şerhi | docs | bağımlılık bu koşuda tamamlanmadı: G188, G192. Not: `C:/dev/hukudok-wt/G193` worktree kaydı var, temizlenmedi. |

zincirHatasi / teslimHatasi olan görev yok.
