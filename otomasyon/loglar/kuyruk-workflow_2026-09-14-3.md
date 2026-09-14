# Gece Kuyruğu (workflow) · 2026-09-14-3

## Özet

4 görev alındı · 2 işaretlendi · 1 bloke · 1 atlandı

Hiçbir görevde merge/entegrasyon yapılmadı (`mergeYapildi=false`). Push/deploy yapılmadı.

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G194 — Teslim cevap yüklemesi transaction'ı yükleme döngüsünden önce kapatır | backend | `bf62085` | geçti (test temiz, kırmızı-yeşil kanıtlandı, ihlal yok) | GEÇTİ (3 bulgu) | 1 tur. Eski kodda 5 yeni test kırmızı; yenide 3501 passed / 3 skipped, ruff + mypy temiz. Kapsam dışı izlenecek: `eslesme_csv_uret` xlsx okuma + eşleşme sorgusu ve `teslim_havuz_farki` hâlâ açık transaction içinde. |
| G191 — idle_in_transaction + lock_timeout env, compose postgres parametreleri, pg_stat_statements | backend | `f9b51b7` | geçti (test temiz, kırmızı-yeşil kanıtlandı, ihlal yok) | GEÇTİ (3 bulgu) | 1 tur. 3517 passed / 3 skipped, mypy temiz; ruff'ın 6 hatası yalnız git dışı `calibration-data/_g179/ek3_cevapla.py`. Canlı SHOW doğrulandı (effective_cache_size=384MB, pg_stat_statements yüklü). Test değişikliği yalnız izinli `test_faz3_e_hardening.py:129`. İzlenecek: prod'da `up -d` postgres'i yeniden oluşturur (kısa DB kesintisi); `lock_timeout` 5 sn → 04:00 aktarım loglarında "lock timeout" aranmalı; `scripts/hukdok_aktarim.py` sınırları yükseltmiyor (gerekirse ayrı görev). |

## Bloke

### G192 — Düşük etkili: offset tavanı 422, N+1 → in_(), _scan_once vade filtresi SQL'de, PK index ikizleri, cases.status CHECK NOT VALID

**Testi değiştirmeden geçilemedi, görev tanımı gözden geçirilmeli.** Bu bir başarısızlık değil: hat mevcut testleri gevşetmek yerine durdu, yani doğru çalıştı.

- **Durma sebebi:** `test-degistirmek-gerekti` (işaretlenmedi, commit YOK)
- **Son parmak izi:** `test_perf_olcum.py::olcum_db` fixture'ının TEMYIZ INSERT'i ↔ CHECK NOT VALID; `test_index_envanteri.py::test_dusurulen_ikizlerin_kapsamasi_semada_duruyor` içindeki `len(dusenler) >= 25` ↔ `models.py`'den `index=True` kaldırma.
- **Denenen yaklaşımlar:**
  1. D8 / D11 (cases+clients `in_()`) / D15 (SQL vade filtresi) / D10-DROP (20 `ix_<tablo>_id` `_DUSURULECEK_INDEXLER`'e) uygulandı: yeni test dosyası 14 passed (dbtest dahil), tam koşu 3531 passed / 3 skipped, ruff + mypy temiz, build+up migrasyon logu temiz.
  2. D10 `models.py` yarısı: `create_all` 46 PK ikizi üretiyor, 26'sı listede, 20'si eksik. `index=True` kalkınca listedeki create_all index sayısı 26→0 olur ve `test_index_envanteri.py:258` (≥25) kırılır → uygulanmadı.
  3. D9: `olcum_db` fixture'ı `init_db` SONRASI `status='TEMYIZ'` INSERT ediyor; NOT VALID kısıt yeni INSERT'i zorlar → fixture kırılır; oysa kabul kriteri aynı INSERT'in reddini istiyor → uygulanmadı.
  4. Sahte yeşil yolları reddedildi: ikizleri `__table_args__` Index'e taşımak, eşik için ek index düşürmek, testi değiştirmek.
  5. G191 emsali (yarım görev commit'lenmez) gereği kaynak değişiklikleri geri alındı (4 dosyada `git diff --quiet` temiz); yeni test dosyası ve patch oturum scratchpad'ine taşındı (GEÇİCİ); HEAD imajı yeniden build edildi.
- **Kök neden:** Görev tanımı iki mevcut testle çelişiyor. (a) D9 kabul kriteri (TEMYIZ INSERT reddi) ile `test_perf_olcum.py:302` civarındaki fixture'ın aynı INSERT'e dayanması; (b) D10 AST kabul maddesi (PK kolonunda `index=True` yok) ile `test_index_envanteri.py:258` eşiği. Görev dosyası bu testlere değişiklik izni vermiyor.
- **Worktree:** yok (ana repoda çalıştı). Çalışma ağacı HEAD 15a4378 ile birebir; yalnız `gorevler/gorev/G192.md` (Rapor + DURUM: BLOKE) değişti.
- **Yan etki (yalnız lokal DB):** doğrulama koşusu 20 `ix_<tablo>_id` index'ini düşürdü, HEAD bunları geri yaratmıyor (0/20; PK'lar yerinde, plan etkisi yok). Prod'a dokunulmadı.
- **Önerilen sonraki adım:**
  1. `test_perf_olcum.py::olcum_db` için değişiklik izni: `init_db` → `DROP CONSTRAINT ck_cases_status_uclu` → TEMYIZ INSERT → kısıtı NOT VALID ile yeniden ekle (prod'daki kısıt öncesi bozuk satırın taklidi; satır 332 beklentisi değişmez).
  2. `test_index_envanteri.py:258` için karar: ya eski kurulum elle taklit edilir (PK ikizleri `init_db` öncesi CREATE INDEX), ya `models.py` değiştirilmez (G042 deseni) ve yalnız DROP yarısı kabul edilip AST kabul maddesi kaldırılır.
  3. Karar sonrası ikinci koşu, G192.md Rapor'undaki yol haritasıyla tamamlar. Prod'a çıkmadan G183 ölçümüyle status ihlali 0 doğrulanmalı (NOT VALID kısıt bozuk eski satırın her UPDATE'ini de reddeder).
  4. Scratchpad'deki patch geçici; ikinci koşuda kaybolmuş olabileceği varsayılmalı.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok. Kabulü karşılanmayan maddeler (G192) soru olarak:

1. `GET /api/cases?offset=10001 → 422` testi doğrulandı ama commit'lenmedi — D9/D10 kararı beklenmeden bu kısım ayrı commit'lensin mi?
2. İlişki bloğu tek SELECT + poliçe listesi `case_documents` sorgusu 1 testi doğrulandı ama commit'lenmedi — ayrı commit'lensin mi?
3. `_scan_once` vadesi gelmemiş satırı DB'den çekmez testi doğrulandı ama commit'lenmedi — ayrı commit'lensin mi?
4. "`models.py`'de `primary_key=True` kolonunda `index=True` yok" maddesi `test_index_envanteri.py:258` ile çelişiyor: test mi değişsin, madde mi kaldırılsın (yalnız DROP yolu yeterli mi)?
5. dbtest "CHECK kısıtı convalidated=false, TEMYIZ INSERT reddi, idempotent" maddesi `test_perf_olcum.py:302` ile çelişiyor: `olcum_db` fixture'ını değiştirme izni verilecek mi?
6. "CHECK değer listesi `constants.CASE_STATUSES`'ten üretilir" testi D9'a bağlı, yapılmadı — D9 kararıyla birlikte mi ele alınsın?
7. `docs/mimari/dava-acma-akisi.md` status CHECK NOT VALID notu D9'a bağlı, yapılmadı — D9 kararıyla birlikte mi?

## İzin engelleri

yok

## Atlananlar

- **G193** — Performans turu dokümantasyonu (bant: docs): atlandı — *bağımlılık bu koşuda tamamlanmadı: G192*. Worktree `C:/dev/hukudok-wt/G193` korunuyor (`worktreeTemizlendi=false`).

Tavan nedeniyle atlanan: yok.

### Plan uyarıları (koşucudan)

- G191: Rapor bölümünde önceki gece kaydı "DURUM: BLOKE — test değiştirmek gerekti" var; KUYRUK satırında BLOKE yok; 14.09 kullanıcı kararı dar test değiştirme izni verdi (`test_faz3_e_hardening.py:129`) ve G194'e bağımlı kıldı.
- G191 dosya kapsamında test dosyası alternatifli yazılı (`test_faz*_connect_args*.py` ya da yeni `test_g191_baglanti_ayarlari.py`).
- G192 ve G193 dosya kapsamında "ilgili testler" / "KUYRUK.md DOKUNMA" gibi yol dışı ifadeler var; `dosya[]` yalnız somut yolları içerir.
- G192 ve G191 ikisi de `backend/database.py`'ye dokunur (seri zincir).
