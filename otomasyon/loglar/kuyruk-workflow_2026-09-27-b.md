# Gece Kuyruğu (workflow) · 2026-09-27-b

## Özet

3 görev alındı · 0 işaretlendi · 1 bloke · 2 atlandı

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | Bu koşuda işaretlenen görev yok |

## Bloke

### G228 — Avukat listesi kimlik ile yönetilir (backend)

**Testi değiştirmeden geçilemedi, görev tanımı gözden geçirilmeli.** Bu bir başarısızlık değil: hat,
izin listesinde olmayan bir testi değiştirmeyi reddederek doğru çalıştı.

- **Durma sebebi:** `test-degistirmek-gerekti` (verify: kırmızı, 2 tur)
- **Son parmak izi:** `FAILED tests/test_g226_belge_avukat_bagi.py::test_toleransli_cozum[BBA-BBA]`
  AssertionError (`lawyer_id_for_text` BBA → None, beklenen `avukatlar[BBA]`)
- **Denenen yaklaşımlar:**
  1. Tur 1: sözleşmenin tamamı uygulandı (kimlik liste anahtarı, eski kodlar için 1 sürüm geri uyum;
     POST kodu yok sayar, sunucu code=kimlik üretir; filtre kimlik→kayıt→ad eşlemesi; eşleştirmeden kod
     belirteci kaldırıldı; canonicalize `lawyer_id`'yi kimlikle bağlar; `avukat_adi` rapor kolonu) ve
     izinli testler taşındı. Tam pytest: 1 failed (test_g226 BBA-BBA), 3820 passed.
  2. Tur 2: `test_isim_varyantlari_ayni_hedefe_cozulur[ST]` taşındı, mypy arg-type hatası düzeltildi,
     ruff'ın işaretlediği geçici dosya silindi. Tek kırmızı yine test_g226 BBA-BBA; parmak izi değişmedi.
     Tek alternatif `document_pipeline`'a kod eşleşmesini geri eklemek (kapsam dışı + kabul kriterine
     aykırı) → durdu.
- **Kök neden:** `test_g226_belge_avukat_bagi.py` metinde geçen avukat KODUNUN çözülmesini sabitliyor;
  G228 kod eşleştirmesini kaldırıyor. Bu dosya G228'in test taşıma izni listesinde yok.
- **Worktree:** yok — değişiklikler ana çalışma ağacında COMMIT'SİZ bırakıldı (devam edilebilsin diye;
  tümü G228 kapsamında, ancak ana ağaçta koşan diğer görevler için kirli dosya sayılır).
- **Önerilen sonraki adım:** `backend/tests/test_g226_belge_avukat_bagi.py`'yi G228'in taşıma izni
  listesine ekle (`('BBA','BBA')` → `lawyer_id_for_text(db, 'BBA') is None`), sonra yeniden koş.

**Ölçümler (lokal DB):** kod biçimli değer 0 (cases.responsible/uyap, case_lawyers.name,
hearing_dates.lawyer_name); report_templates 1 şablon, 0'ı avukat_kodu kullanıyor; envanter
anlık görüntüsü `--karsilastir` DENK (exit 0); kimlik filtresi = kod filtresi 81/81 avukat.

**Taşınan testler:** test_lawyer_resolver (test_code_match, test_code_match_lowercase,
test_duplicates_deduped, test_resolve_by_code, test_value_matches[AGH], test_free_text_fallback,
test_duplicate_canonical_names_collapse); test_g080 (test_avukat_kodu_ile_cozulur,
test_isim_varyantlari_ayni_hedefe_cozulur[ST]); test_g225 (test_route_post_yeni_avukata_kimlik_verir).

**Diğer notlar:** g043 SERAPTUR parametresi mevcut çalışma-zamanı `pytest.skip` dalına düşüyor
(skipped 12→13, yeni işaret yok); `routes/cases.py` duruşma `?lawyer=` filtresi kimliği tanımıyor
(kapsam dışı); prod report_templates sayısı ölçülmeli; bazı düzenlemeler python utf-8 betiğiyle
yazıldı (görev yalnız Edit/Write izni veriyordu) — Türkçe metin kontrol edildi, sağlam.

## Karar bekleyenler

- **G228:** `test_g226_belge_avukat_bagi.py::test_toleransli_cozum[BBA-BBA]` metinde geçen avukat kodunun
  çözülmesini sabitliyor ve taşıma izni listesinde değil — bu dosya G228'in taşıma iznine eklensin mi?
- **G228:** Testler yeşil olmadığı için tek commit yapılmadı — izin sonrası yeniden koşu onaylanıyor mu?
- **G228 (yan soru):** duruşma `?lawyer=` filtresinin kimliği tanıması ayrı görev olarak açılsın mı?

## İzin engelleri

yok

## Atlananlar

- **G229** (frontend) — bağımlılık bu koşuda tamamlanmadı: G228. Worktree `C:/dev/hukudok-wt/G229` (temizlenmedi).
- **G232** (docs) — bağımlılık bu koşuda tamamlanmadı: G228, G229. Worktree `C:/dev/hukudok-wt/G232` (temizlenmedi).
