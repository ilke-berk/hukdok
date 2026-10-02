# Gece Kuyruğu (workflow) · 2026-10-02

## Özet

9 görev alındı · 2 işaretlendi (G248, G256) · 2 bloke (G249, G252) · 5 atlandı (G257, G250, G251, G253, G254). Tavan nedeniyle atlanan yok. Push/deploy yapılmadı.

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G248 — Hizmet kaydı temeli (`case_hizmetleri` + tek yazma yolu + türetilmiş `cases.hizmet_turu` özeti + `/api/cases/{id}/hizmetler`) | backend | `aede5cf` | geçti (test temiz, kırmızı→yeşil kanıtlandı, ihlal yok) | GEÇTİ (7 bulgu, RET sebebi değil) | 2 turda yeşil: pytest 4218 passed / 15 skipped, ruff + mypy yeşil. Veride `mergeYapildi=false`, `entegrasyon` boş. İki SAPMA var (aşağıda "Karar bekleyenler"). Lokal konteyner yeniden başlatılmadı: migrasyon 59 lokal DB'ye bir sonraki açılışta uygulanır. |
| G256 — Admin paneli Hizmet Türleri sekmesi + `useConfig.typeToKey` önbellek tazeleme | frontend | `e5b6359` | geçti (test temiz, kırmızı→yeşil kanıtlandı, ihlal yok) | GEÇTİ (4 bulgu) | 1 turda yeşil: vitest 131 dosya / 1407 passed, lint 0 hata, `tsc -b --force` temiz. Merge yapıldı, entegrasyon yeşil, worktree temizlendi. Görsel doğrulama YAPILMADI. |

### G248 notları (sonraki görevleri etkiler)

- **Manager sözleşmesi (G249-G253 için):** `elle_ekle`, `elle_sil`, `elle_kumesini_yaz`, `taraflarin_elle_satirlarini_sil`, `foydan_yaz(db, foy, *, source=None) -> FoySonucu(durum, sebep, satir)`, `tarafi_tasi(db, *, eski_party_id, yeni_party_id, yeni_case_id)`, `liste_adi_degisti`, `ozeti_yenile`/`ozetleri_yenile`, `kart_hizmet_listesi`.
- Föyün zaten verdiği (müvekkil, hizmet) elle tekrar yazılmaz (POST 200 + föy satırı; PUT kümede "var" sayar); `foydan_yaz` mevcut elle satıra dokunmaz; yazılamayan föyde mevcut satır yerinde kalır (föy başka karta taşındıysa silinir); föy satırının ilk yazımı tarihçesiz.
- TEXT genişletmesi madde 44'ün çıplak ALTER deseni yerine tip yoklamalı `DO $$` bloğu ile, koşulsuz index op'unda.
- **İzlenecek (G250):** `get_cases(hizmet_turu=X)` hâlâ eşitlik — çok değerli özette kartı bulamaz; `PATCH /tracking` hâlâ `cases.hizmet_turu` yazabiliyor (özeti ezer); müvekkil tarafının `party_type`'ı CLIENT'tan çevrilirse hizmet satırları kalır.
- Çalışma ağacında görev öncesinden gelen kapsam dışı kirlilik vardı (`.claude/settings.local.json` M, `.claude/launch.json` ??); dokunulmadı, commit'e girmedi. `gorev-devam`'ın katı okuması BLOKE derdi; işçi devam etti.

### G256 notları

- Yeni test DOSYASI yok: 13 test iki mevcut dosyaya yeni `describe` blokları olarak eklendi; mevcut test satırlarına dokunulmadı. `useConfig` dosyasındaki 5 yeni testten biri ("başka listenin mutasyonu çekmez") eski kodda da geçer.
- Karar: hizmet türü kodu seed biçiminde üretilir (harf/rakam dışı koşular tek `-`, parantez koda girmez).
- Kapsam dışı backend notu: `add_item`/`update_item` adı `tr_title`'dan geçirir; seed adı "Takip (doktor müvekkil)" panelden kaydedilirse "Takip (Doktor Müvekkil)" olur — aktarımın hizmet adını harf duyarsız eşleyip eşlemediği G257'de kontrol edilmeli (işçi aktarım tarafını okumadı).
- Lint'te önceden var olan 1 uyarı (`ArkaplanCizgisi.tsx` react-refresh), dokunulmadı.

## Bloke

İki bloke görevin ikisi de aynı sınıftadır: **testi değiştirmeden geçilemedi, görev tanımı gözden geçirilmeli.** Bu bir uygulama başarısızlığı değildir; hattın TEST BÜTÜNLÜĞÜ kuralının doğru çalıştığının kanıtıdır (27.09 G228/G229 dersinin aynısı: koşuya `testTasimaIzni` verilmemişti).

### Testi değiştirmeden geçilemedi — G249 (backend)

**Hizmet kaydı: aktarım föy başına satır + geriye dönük doldurma script'i (kuru koşu) + kart birleştir/ayır satırları taşır**

- **Durma sebebi:** görev tanımı (kriter 5) mevcut aktarım testlerinin yeni davranışa uyarlanmasını istiyor; koşucunun test bütünlüğü kuralı mutlak ve bu çağrıda G249 için insan onaylı test taşıma istisnası yoktu. Kod yazılmadı (tur 0, verify çalıştırılmadı).
- **Son parmak izi (deney kopyasında):** `tests/test_g120_aktarim_muvekkil_hizmet.py` 7 test (`test_kayit_kilitleri_sutun_adaylari_kart_alanlari_ve_docstring`, `test_dry_run_iki_alan_farkta_gorunur_dbye_yazilmaz`, `test_gecerli_deger_yazilir_taninmayan_rapora_duser`, `test_cok_deger_yazilmaz_rapora_duser`, `test_ikinci_kosu_sifir_degisiklik_iki_alan_dahil`, `test_kardes_foyler_farkli_muvekkil_tipi_celiski_raporuna_duser`, `test_dolu_hucre_metin_sinifiyla_uzerine_yazilir`) + `tests/test_g123_tum_sutunlar.py::test_kardes_foy_celiskisinde_foy_degeri_kaybolmaz` — AssertionError/KeyError.
- **Denenen yaklaşımlar:**
  1. Statik inceleme: `test_g120` ve `test_g123`, `KART_ALANLARI['hizmet_turu']` kaydını, kart `hizmet_turu` yazımını, `case_history field_name=hizmet_turu` satırını, HATA "hizmet_turu yazilmadi" raporunu ve kardeş çelişkisinde `hizmet_turu` satırını kilitliyor — kabul kriterleri 1-2 ile doğrudan çelişiyor.
  2. Deney (repo dışı, konteyner `/tmp` kopyası, sonra silindi): yalnız `KART_ALANLARI`'ndan `hizmet_turu` satırı çıkarıldı, tam pytest → 8 failed (`test_g120` ×7, `test_g123` ×1), başka dosya düşmedi.
  3. Eski kart yazımını koruyup satırları EK olarak yazma seçeneği değerlendirildi ve reddedildi: iki yazıcı (kart yolu + `ozeti_yenile`) koşudan koşuya salınım üretir, kabul kriteri 2'yi ihlal eder, sahte yeşil olur.
- **Kök neden:** teşhis kaydı boş (teşhis adımı çalışmadı). İşçi notuna göre: görev tanımı ile mevcut test kilitleri çelişiyor ve koşuya test taşıma izni verilmedi.
- **Worktree:** yok (backend bandı ana dizinde). Görev commit'i yok. Yalnız görev dosyası G239 emsaliyle docs commit'i olarak atıldı: `7444ce1` (ana dizin kirli kalıp sonraki backend görevini bloklamasın diye).
- **Önerilen sonraki adım:** `/gece-kuyrugu` çağrısına `testTasimaIzni { G249: ["backend/tests/test_g120_aktarim_muvekkil_hizmet.py", "backend/tests/test_g123_tum_sutunlar.py"] }` verilsin. Emniyet payı için kapsamdaki `test_g064_aktarim_cekirdek.py` ve `test_mukerrer_kart_raporu.py` de eklenebilir (çekirdek değişiklikle düşmediler).
- **Ek bulgular (görev dosyasında ayrıntılı):**
  1. Lokal DB'de `case_hizmetleri` tablosu YOK — migrasyon 59 lokal konteynerde henüz koşmadı. Geriye dönük doldurma kuru koşusu için önce backend restart / `migrate.py` gerekir; işçi yapmadı.
  2. Lokal salt-okunur ölçüm: 8.416 föy; satır alacak 8.403; atlanacak 13 (8 kapsam dışı + 5 müvekkil bağı yok); listede olmayan ad 0; kardeş föyleri farklı hizmet taşıyan kart 1.060; özeti değişecek kart ~1.061.
  3. Tasarım notu: `foydan_yaz` çağrısı `kapsam_isaretlerini_yaz`'dan SONRA ayrı geçiş olmalı.
  4. G248 sözleşmesinde (`managers/case_hizmetleri.py`) eksik bulunmadı.
- **"Kuru koşu bitince gerçek koşuyu başlat" isteği hakkında:** işçi bu isteği kuyruk koşusu düzeyinde okudu. Görevdeki `hizmet_kayitlari_doldur.py --apply` görev tanımında açıkça İNSAN ADIMI (önce dump) — koşulmadı; script'in kendisi de yazılmadı.

### Testi değiştirmeden geçilemedi — G252 (frontend)

**Dava kartında Hizmetler paneli (müvekkile göre gruplu çipler, HizmetSecici, tek PUT, tüm müvekkillere uygula); Büro Bilgileri'ndeki tek değerli satır kalkar**

- **Durma sebebi:** kabul ölçütü "Büro Bilgileri kartından `hizmet_turu` satırı KALKAR" mevcut testlerle çelişiyor; görev dosyası bu dosyaları kapsamda sayıyor ama koşuya G252 için `testTasimaIzni` verilmemiş. Verify kırmızı (tur 1).
- **Son parmak izi:** 4 AssertionError / 3 dosya:
  - `frontend/src/lib/caseCardFields.test.ts` (satır 116-117) — "dosya_son_durumu karttan çıktı — OFFICE_CARD_FIELDS 4 anahtar bekliyor"
  - `frontend/src/lib/caseCardFields.serviceTypes.test.ts` (satır 29-36 ve 70-76) — "muvekkil_tipi ve hizmet_turu bureau_type'ın ALTINA girer"; "yeni alanlar doluysa kartta ... sırayla basılır"
  - `frontend/src/pages/CaseDetails.config.test.tsx` (satır 132-145) — "kapalı liste rozetleri doğru listeye bağlı" (`badgeFor('Hizmet Turu')` bulunamıyor)
- **Denenen yaklaşımlar:**
  1. Tur 1: görev tanımına göre tam uygulama (lib + `HizmetSecici` + `CaseHizmetPanel` + `CaseDetails` yerleşimi + `OFFICE_CARD_FIELDS`'ten `hizmet_turu` satırının çıkarılması) + 5 yeni test dosyası (48 test yeşil). Tam paket: 1438 geçti, 4 kaldı — dördü de kaldırılan satırın varlığını sabitleyen mevcut testler. Lint 0 hata, `tsc -b --force` temiz.
  2. Sabiti koruyup satırı yalnız render'da gizlemek değerlendirildi ve reddedildi: `CaseDetails.config.test.tsx` yine düşer, ayrıca görev satırın `caseCardFields.ts`'ten kalkmasını açıkça istiyor (sahte yeşil olurdu).
- **Kök neden:** teşhis kaydı boş. İşçi notuna göre: görev tanımı ile mevcut test kilitleri çelişiyor ve koşuya test taşıma izni verilmedi.
- **Worktree (KORUNUYOR):** `C:/dev/hukudok-wt/G252`, dal `gorev/G252`, HEAD hâlâ `c88879a` (commit yok). Tüm kod + 5 yeni test dosyası **COMMIT'SİZ** çalışma ağacında duruyor. Görev dosyasının worktree kopyasında (`C:/dev/hukudok-wt/G252/gorevler/gorev/G252.md`) Rapor bölümü dolu, önerilen eski→yeni beklentiler dahil.
- **Önerilen sonraki adım:** iki yol var.
  - (a) Aynı worktree'de elle bitir: kalan iş yalnız üç test dosyasındaki beklenti taşıması + tek commit.
  - (b) Yeniden koşu: `testTasimaIzni = { G252: [yukarıdaki üç dosya] }`. DİKKAT: sıfırdan koşulacaksa önce worktree ve dal temizlenmeli (kurulum adımı "eski worktree duruyor" diye durur) — bu durumda commit'siz iş KAYBOLUR.
- **İşçi kararları (ayrıntı görev dosyasında):** (1) frontend'de "kartı düzenleyemeyen" kavramı yok — panel `duzenlenebilir` prop'u alıyor (varsayılan true); (2) `useCases.ts`'e dokunulmadı: `CaseData` POST/PUT yük tipinde ve backend `CaseCreate`'te hizmetler alanı yok — okuma tipi `lib/caseHizmetleri.ts::CaseHizmeti`; G253 bunu bilmeli; (3) toplu uygulamada boş seçim uygulanamaz, bir müvekkil başarısız olsa da kalanlar denenir; (4) liste dışı elle ad seçiciye girmez (sunucu 422 verir), değişiklik uygulanırsa düşer — satırda uyarı var.
- **Yapılmayan:** görsel/tarayıcı doğrulaması; `docs/mimari` güncellemesi (kapsam dışı). Kalkan satırla birlikte `hizmet_turu` alan zili (`HataBildirButonu`) de kalktı; panelde alan zili yok.

## Karar bekleyenler

Hiçbir görevde `teshis.gorevTanimiHatali=true` kaydı yok (teşhis listeleri boş). Aşağıdakiler `kabulKarsilanmayan` maddelerinden ve işçi notlarından çıkan SORULARDIR.

**G249**

1. `test_g120_aktarim_muvekkil_hizmet.py` ve `test_g123_tum_sutunlar.py` için test taşıma izni verilecek mi? (Bu izin olmadan şunların hiçbiri yazılamıyor: aktarımın föy satırını `foydan_yaz` ile upsert etmesi; `hizmet_turu` kart alanının uzlaşma/çelişki hesabından çıkması; `hizmet_kayitlari_doldur.py` kuru koşu script'i; `mukerrer_kart_birlestir` / `birlesik_kart_ayir`'ın hizmet satırlarını taşıması; mevcut aktarım testlerinin uyarlanması; tam pytest + ruff + mypy.)
2. İzin emniyet payıyla `test_g064_aktarim_cekirdek.py` ve `test_mukerrer_kart_raporu.py`'yi de kapsasın mı?
3. Lokal backend konteyneri yeniden başlatılıp migrasyon 59 lokal DB'ye uygulansın mı? (Geriye dönük doldurma kuru koşusunun ön koşulu.)

**G252**

4. Üç test dosyası (`caseCardFields.test.ts`, `caseCardFields.serviceTypes.test.ts`, `CaseDetails.config.test.tsx`) için test taşıma izni verilecek mi?
5. İş mevcut worktree'de elle mi bitirilecek, yoksa sıfırdan yeniden mi koşulacak (commit'siz iş kaybolur)?
6. Kalkan satırla birlikte `hizmet_turu` alan zili de kalktı; Hizmetler paneline hata bildirimi zili eklenmeli mi?

**G248 (işaretlendi; sapmalar insan kararı isteyebilir)**

7. SAPMA 1: satır bağı `DEPENDENCIES['service_types']` yerine `reference_lists.SATIR_BAGIMLILIKLARI` haritasına yazıldı (+ `bagimliliklar(key)` birleşik okuyucu), çünkü `test_g119::test_registry_deps_titles_kayitli` o listeyi birebir kilitliyor. `test_g119` kilidi açılıp bağ `DEPENDENCIES`'e taşınsın mı, yoksa bu yapı kalsın mı? Kalırsa: `scripts/deger_havuzu_seed.satir_kullanimi` `DEPENDENCIES`'i doğrudan okuyor — G257'de `bagimliliklar(key)`'e geçmeli; G256/G257 görev metinleri "G248 DEPENDENCIES" diyor, düzeltilmeli.
8. SAPMA 2: `models.Case.hizmet_turu` bildirimi `String(100)` kaldı (`test_g119` `length==100` kilitli); DB kolonu migrasyon 59 ile TEXT. Yalnız `create_all` koşan migrasyonsuz bir Postgres'te kolon VARCHAR(100) kalır. Kabul mü, yoksa model + test birlikte mi güncellensin?

**Plan uyarıları (koşu öncesi plandan)**

9. G255: KUYRUK notuna göre G249/G257 ile `backend/scripts/hukdok_aktarim.py` ortak; aynı gece koşarsa G257'den SONRA koşmalı — ama `bagimli` alanında yazılı değil. Bağımlılık alanına eklensin mi?
10. G255: görev dosyasında "Rapor" bölüm başlığı yok (Kabul kriterleri dolu, `Durum: TAMAM` yok).
11. G254 ve G255 ikisi de `CLAUDE.md` + `docs/mimari/veri-teslim-hatti.md`'ye dokunur (dosya çakışması) — sıralama kararı gerekli.
12. Dosya kapsamı listeleri görev dosyalarındaki ters tırnaklı yollardan çıkarıldı; yalnız tam yolu yazılan dosyalar alındı (kısa adla anılan test dosyaları eksik olabilir).

## İzin engelleri

yok (dokuz görevin tamamında `izinEngelleri` listesi boş).

## Atlananlar

| görev | bant | sebep | worktree |
| --- | --- | --- | --- |
| G257 — Hizmet listesi veri ekibinin paketinden (`deger_havuzu_seed` + aktarım eşlemesi + uçtan uca test) | backend | bağımlılık bu koşuda tamamlanmadı: G249 | — |
| G250 — `CasePartyCreate.hizmet_turleri` + hizmetsiz müvekkil 422 + liste filtresi EXISTS + PATCH'te `hizmet_turu` kapanır | backend | bağımlılık bu koşuda tamamlanmadı: G257 | — |
| G251 — Raporlama Hizmetler kaynağı + çok değerli hizmet kolonu + asistan kataloğu | backend | bağımlılık bu koşuda tamamlanmadı: G250 | — |
| G253 — NewCase + intake + QuickCaseModal müvekkil başına hizmet seçici | frontend | bağımlılık bu koşuda tamamlanmadı: G250, G252 | `C:/dev/hukudok-wt/G253` (temizlenmedi) |
| G254 — CLAUDE.md + mimari dokümanları: müvekkil bazlı hizmet kaydı | docs | bağımlılık bu koşuda tamamlanmadı: G249, G250, G251, G252, G253, G257 | `C:/dev/hukudok-wt/G254` (temizlenmedi) |

`zincirHatasi` ya da `teslimHatasi` taşıyan görev yok.

**Not:** atlanan G253 ve G254 için worktree dizinleri veride kayıtlı ve temizlenmemiş görünüyor; bir sonraki koşunun kurulum adımı "eski worktree duruyor" diye durabilir — koşudan önce kontrol edilmeli. Zincirin tamamı G249'un bloke olmasına bağlı: G249 açılmadan G257 → G250 → G251 → G253 → G254 koşamaz.
