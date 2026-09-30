# Gece Kuyruğu (workflow) · 2026-09-30e

## Özet

2 görev alındı · 2 işaretlendi · 0 bloke · 0 atlandı

Tavan nedeniyle atlanan: yok.

Plan uyarıları (koşu öncesi):

- **G239:** görev dosyasının Rapor bölümünde önceki koşudan "DURUM: BLOKE" kaydı duruyordu (kod yazılmamış, commit yok). KUYRUK satırında BLOKE yoktu ve 30.09 insan kararıyla test taşıma izni genişletilmişti (`test_g043_index_ve_avukat_filtresi.py`, `test_g236_ofis_no_kayit.py`) → yeniden koşulabilir sayıldı.
- **G240:** G239'a bağımlı; G239 bu koşuda bittiği için seçilebildi.

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G239 | backend | `595661c` | geçti (test: temiz, kırmızı→yeşil: kanıtlandı, ihlal yok) | GEÇTİ (5 bulgu) | 1 tur, yeşil: 4085 passed, 15 skipped; ruff temiz; mypy temiz. Veride `mergeYapildi=false`, `entegrasyon` boş, worktree kaydı yok. |
| G240 | docs | `09b9aa0` | geçti (test: temiz, kırmızı→yeşil: uygulanamaz, ihlal yok) | GEÇTİ (6 bulgu) | 1 tur, verify `test-yok` (doküman görevi); doğrulama grep'leri boş. `mergeYapildi=true`, entegrasyon: uygulanamaz, worktree `C:/dev/hukudok-wt/G240` temizlendi. **Kabul 2 KISMİ** (aşağıda). |

### G239 ayrıntı

Başlık: eski formatı ayrıştıran kod uyarlanır (mükerrer rapor, kart ayırma, cevaplı eşleme iki format, kartsız föy); client-sequence + `idx_cases_tracking_name_block` kalkar; eski üreticiler emekli.

Yaklaşım (tur 1, ilk koşuda yeşil): kolon tabanlı uyarlama (`ofis_no_kodu` + ofis no üreticisi + sayaç), client-sequence için 404 mezar taşı route, index DROP listesine taşıma, cevaplı eşlemede çift desen + göç eşlemesi (CSV ya da `case_history`).

Denetçi gerekçesi: altı kabul kriteri de karşılanmış; denetçi koşusunda pytest 4085 passed / 15 skipped, ruff ve mypy temiz; kapsam, bant ve test taşıma kurallarında ihlal yok.

Taşınan testler (işçi beyanı: silinen test yok, assert sayısı azalmadı, skip/xfail eklenmedi; test adları korundu, docstring'lerde "test adı tarihsel" notu var):

- `test_tracking_sequence.py` (6 test): "numara listesinden max+1" → "sayaçtan sıra" (`sira_tahsis_et`/`siradaki`); eski formatlı numara sıra üretmez; `max_tracking_sequence` artık yok.
- `test_g014_error_gates.py` (3 test): client-sequence 503 / boş isimde 200+`{sequence:1}` → 404, sıra yok, DB oturumu açılmaz.
- `test_gate_closed_on_db_error.py` (4 test): 200+`{sequence:8|13|1}` ve 503 → 404, sıra yok, oturum açılmaz.
- `test_soft_delete.py::test_client_sequence_deliberately_ignores_soft_delete`: uç kaynağında `deleted_at` yok → uç yok + sayaç tahsisinde `deleted_at` yok.
- `test_tenant_softdelete_semantics.py`: `KNOWN_UNPAIRED_SITES`'tan `get_client_case_sequence` çıktı; `test_client_sequence_counts_deleted_but_still_isolates_tenant`: `{sequence:10}` → uç 404 + silinen kartın sırası sayaçta sayılır (sıradaki 10).
- `test_g236_ofis_no_kayit.py::test_client_sequence_ucu_hala_calisir`: 200+`{sequence:1}` → 404.
- `test_g043_index_ve_avukat_filtresi.py` (5 test): `idx_cases_tracking_name_block` "var / sorguda kullanılıyor / düşürülecekler listesinde değil" → "tek ifadesi DROP / şemada yok / plan kullanmıyor / düşürülecekler listesinde; route substr içermiyor". Diğer dört index ve avukat filtresi beklentilerine dokunulmadı.
- `test_g126_kartsiz_foy_kart_ac.py` (2 test): `D1.H_ARTUC....0004.HUKUK.00000` → `DR.H.ARTUC-0004-HUK`, `S4.QUICK......0001.IDARE.00000` → `QUICK-0001-IDR`; sıra sayaçtan; fixture sigorta kod listesini ve sayacı kurar.
- `test_g180_birlesik_kart_ayir.py` (3 test): `'.ARABU.' in tracking` → `QUICK-0001-ARB` + kolonlar; `split('.')[1] in (A_AYRIM, D_ESINLER)` → `split('-')[0] in (DR.A.AYRIM, DR.D.ESINLER)`; fixture kartı `ofis_no_kodu` taşır.
- `test_mukerrer_kart_raporu.py` (2 test): `_isim_blogu(numara)` → `_musteri_kodu(kart)`; eski numara ayrıştırılmaz.
- `test_g154_cevapli_esleme.py`: DEĞİŞMEDİ.

İşçinin kararları / sapmaları:

1. 404 için mezar taşı route bırakıldı (`client_sequence_kaldirildi`, `include_in_schema=False`): uç düz silinince yol `/api/cases/{case_id}` kalıbına düşüp 422 dönüyordu, kabul 404 istiyor.
2. Mükerrer raporunda sigortalı koda KATILMADI (görev "(+ sigortalı)" diyordu): eski isim bloğu da sigortalıyı taşımıyordu; katılsaydı "göç öncesi = sonrası" eşdeğerliği bozulur ve `FARKLI_SIGORTALI` referans satırları listeden düşerdi. Sigortalı ayrımı `_hukum`'da duruyor. **Sabah incelemesinde teyit edilmeli** (bkz. Karar bekleyenler).
3. Emekli scriptler silinmedi (dokümanlar ve karar 016/023 satır atfı yapıyor); çalıştırılınca `.env`/DB import'larından önce hata ile çıkar, `run()` RuntimeError.
4. Göç öncesi kartta (`ofis_no_kodu` boş) numara ayrıştırılmıyor: kod kartın CLIENT taraflarından üreticiyle hesaplanıyor; kart ayırmada ise müvekkil tarafının adıyla.
5. `scripts/README.md` görev dosya kapsamında açıkça yazmıyordu ama görev metni ona atıf yapıyor; emekli iki satır güncellendi.
6. `routes/cases.py` ilk düzenlemesi Python ile (açık utf-8) yazıldı, sonraki tüm düzenlemeler Edit/Write ile; işçi beyanına göre içerik bozulması yok (testler + diff).

Doğrulama notu: `docker compose build backend` KOŞULMADI — işçi beyanına göre lokal konteyner `./backend`'i bind-mount ediyor, testler çalışma ağacındaki kodu koşturdu.

Ortam notu: çalışma ağacında izlenmeyen `.claude/launch.json` vardı (görev dışı harness dosyası); dokunulmadı, commit'e girmedi.

Operasyonel (deploy/göç öncesi bilinmeli):

- Veri ekibinin eski numaralı cevabı göç sonrası `cevapli_kart_eslemesi.py --goc-db` (ya da `--goc-esleme <csv>`) ile koşulmalı; bayraksız koşu eski numarayı olduğu gibi yazar.
- Deploy'da `idx_cases_tracking_name_block` düşer; `rollback.sh` geri getirmez (kullanan kod yok).

### G240 ayrıntı

Başlık: CLAUDE.md + dava-acma-akisi + veri-teslim-hatti güncellenir; veri ekibine not taslağı (gönderilmez).

Yaklaşım (tur 1): kod okunarak dokümanlar yazıldı; doğrulama grep'leri (`client-sequence|generateTrackingNumber|name_block` ve SharePoint sayaç) boş.

Denetçi gerekçesi: commit `09b9aa0` yalnız kapsamdaki 6 doküman + görev raporuna dokunuyor (kod, test, KUYRUK.md değişmemiş); doğrulama grep'leri boş; örneklenen yol/uç/satır/sabit iddialarının hepsi koddan doğrulandı. Kabul 2'nin tek eksiği kapsam DIŞI iki dosyada ve işçi bunu raporda açıkça yazmış.

İşçi notları:

- `rg SharePoint sayac` hiç eşleşme vermiyor (kaldırma notları "eski belge sayacı kaldırıldı" kalıbıyla yazıldı).
- Kapsam dışı bayat yerler rapora NOT olarak düştü, dokunulmadı: `docs/mimari/kimlik-ve-token.md:203` ("ofis-no sayacı"), `backend/scripts/hukdok_aktarim.py:44-47` yorumu, `frontend/src/lib/caseIntakeFields.ts:86` yorumu.
- Koddan değil görev raporlarından alınan iddialar raporda ayrıca işaretli (göç `--apply` hiçbir DB'de koşulmadı; `import_excel_cases` emekli davranışı).
- CLAUDE.md Komutlar bölümündeki test sayıları güncellenmedi (test koşulmadı).
- Commit attribution satırı oturum talimatına göre "Claude Opus 5.5" (skill metnindeki "Claude Fable 5" yerine).
- Veri ekibi notu GÖNDERİLMEDİ; göç tarihi ve eşleme dosyası adı `[..]` ile boş.

## Bloke

Yok. Bu koşuda bloke olan görev yok (iki görevde de `bloke=false`, `durmaSebebi=yesil`, teşhis listeleri boş).

"Testi değiştirmeden geçilemedi" durumu da bu koşuda oluşmadı. G239'un önceki koşudaki BLOKE kaydı, 30.09 insan kararıyla test taşıma izni genişletildikten sonra bu koşuda tek turda yeşile döndü.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok. Karşılanmayan kabul maddesi ve işçinin teyit istediği sapma, soru olarak:

1. **G240 · Kabul 2 KISMİ:** CLAUDE.md ve `docs/mimari` temiz; ancak `docs/veri-teslim/ofis-no-formati.md` (26.09) eski beş bloklu formatı hâlâ güncel gibi anlatıyor ve `docs/veri-teslim/SOZLESME.md:268` ona atıf yapıyor. İki dosya da görevin dosya kapsamında değildi, dokunulmadı. **Soru:** bu iki dosya için ayrı görev açılsın mı? Sözleşme veri ekibine giden belge olduğundan değişikliğin içeriği ve zamanlaması (göçle birlikte mi, önce mi) insan kararı gerektiriyor.
2. **G239 · mükerrer raporunda sigortalı:** görev metni müşteri koduna "(+ sigortalı)" katılmasını söylüyordu; işçi "göç öncesi = sonrası" eşdeğerliğini ve `FARKLI_SIGORTALI` referans satırlarını korumak için KATMADI. Denetim GEÇTİ dedi, ancak işçi sabah teyidi istedi. **Soru:** bu sapma kabul mü, yoksa sigortalı koda katılmalı mı?
3. **G240 · kapsam dışı bayat yerler:** `docs/mimari/kimlik-ve-token.md:203`, `backend/scripts/hukdok_aktarim.py:44-47` yorumu, `frontend/src/lib/caseIntakeFields.ts:86` yorumu eski durumu anlatıyor. **Soru:** küçük bir temizlik görevi açılsın mı?
4. **G240 · CLAUDE.md test sayıları:** Komutlar bölümündeki sayılar (3701 passed) güncellenmedi; G239 koşusunda 4085 passed / 15 skipped ölçüldü. **Soru:** sayılar bir sonraki tam koşuda güncellensin mi?

## İzin engelleri

yok

(İki görevin `izinEngelleri` listesi de boş.)

## Atlananlar

Yok. `atlandi`, `zincirHatasi`, `teslimHatasi` alanları iki görevde de boş.
