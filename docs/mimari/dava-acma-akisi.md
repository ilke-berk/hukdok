# Dava açma akışı — manuel form, intake sihirbazı, ofis numarası

> **Son doğrulama: 2026-09-04 · 88409da** (§1-§10 önceki doğrulama 2026-08-11 · 2eade56;
> §11-§13 bu tarihte koddan sayıldı)
> Her iddia koddan doğrulanmıştır. Kod ile çelişirse kod haklıdır — bu dosyayı düzelt.

Dava iki yoldan açılır: elle doldurulan form (`/new-case/form`) ve belgeden türeten otonom
sihirbaz (`/new-case/auto`). İkisi de aynı `cases` kaydına iner, aynı ofis numarası
kurallarını kullanır.

## 1. Zorunlu alanlar — kaydı ENGELLEMEZ

Tek kaynak `backend/required_fields.py`'dir. Kural docstring'de yazılıdır: **zorunlu alan
eksikliği kaydı engellemez** — dosya `DERDEST` olarak açılır, eksikler dava kartında ve
listesinde uyarı olarak görünür ve panelden filtrelenebilir (`required_fields.py:1-11`).

Reddedilen alternatif de orada kayıtlıdır: "DANIŞ'a düşürme denendi, dönüşüm kaybı riski
nedeniyle vazgeçildi: DANIŞ yolunda müvekkil kaydı oluşturulmuyor" (`required_fields.py:5-6`).

`REQUIRED_CASE_FIELDS` (`required_fields.py:39-63`): `esas_no`, `court`, `file_type`,
`judicial_unit`, `sub_type`, `opening_date`, `subject`, `responsible_lawyer_name`,
`uyap_lawyer_name`, `service_type`, `acceptance_date`, `bureau_type`, `atama_tarihi`.

**Güncel not (G046, FAZ D — bu satır ADR-014'te de anlatılıyor):** liste artık düz bir
alan adı listesi DEĞİL, liste-of-dict + isteğe bağlı bir `skip_when` "kapı"sı taşıyor —
`esas_no` alanı `file_type ∈ ESAS_BEKLENMEYEN_TURLER` (ARABULUCULUK/SAVCILIK/DANIŞMANLIK/
TAHKİM) ise zorunlu SAYILMAZ (D2). 13 alanın **12'si hâlâ koşulsuz**, yalnız `esas_no`
bağlamsal. Aynı mekanizma (`missing_required_bucket` kolonu, `MISSING_BUCKET_MANUAL`/
`MISSING_BUCKET_AKTARIM` kovaları) `uyap_lawyer_name`'e henüz **bağlanmadı** — bkz.
[`014-uyap-avukati-on-doldurulmaz.md`](../kararlar/014-uyap-avukati-on-doldurulmaz.md).

`sub_type_extra` (Uzmanlık / Tıbbi İşlem) listeden **geçici** olarak çıkarılmıştır
(2026-08-04): alan UI'da gizlendiği için görünmeyen alan "eksik" uyarısı üretmesin; alan
geri açılınca satır da geri alınacak (`required_fields.py:51-54`).

Ayrıca `compute_missing_fields` karşı taraf TC'sini denetler ama **yalnız COUNTER**
taraflar için: müvekkil TC'si `Client` kaydında yaşar, form yalnız karşı taraf TC'si
girebilir — aksi halde her yeni dosya yanlış "eksik" işaretlenirdi
(`required_fields.py:65-68`, mantık `:127-132`).

Frontend bu listeyi `GET /api/config/required_case_fields` üzerinden okur; **ikinci bir
liste tutulmaz** (`required_fields.py:8-10`).

## 2. Mükerrer kontrolü

`GET /api/cases/check-duplicate` (`backend/routes/cases.py:190`) esas no (ve isteğe bağlı
mahkeme) ile mevcut davaları arar; form kaydetmeden önce uyarı gösterir.

## 3. Otonom intake sihirbazı

Backend uçları `backend/routes/case_intake.py`'dedir:

| Uç | Satır | İş |
| --- | --- | --- |
| `POST /api/case-intake/expand-eml` | `:209` | `.eml` dosyasını gövde + eklere açar (gövde PDF'e çevrilir) |
| `POST /api/case-intake/analyze` | `:330` | Tek belgeyi analiz eder, NDJSON stream döner, tam PDF'i PROCESS_CACHE'e koyar |
| `POST /api/case-intake/merge` | `:651` | N belgenin çıkarımlarını tek taslakta birleştirir |
| `POST /api/case-intake/commit` | `:1066` | Yeni dava kaydı + belge arşivleme + poliçe beslemesi |
| `POST /api/case-intake/apply` | `:1224` | **Zenginleştirme modu**: mevcut davaya kısmi güncelleme |
| `POST /api/case-intake/keepalive` | `:1322` | Review adımında PROCESS_CACHE TTL'sini tazeler |

Sihirbaz akışı: yükle → analiz → (birden çok belge varsa) birleştir → kullanıcı incelemesi
→ commit (ya da mevcut davaya apply).

`keepalive` ucunun varlığı bir tasarım sonucudur: PROCESS_CACHE TTL'si 1800 sn'dir
(`config/settings.py:89`) ve kullanıcı inceleme adımında bundan uzun kalabilir; sihirbaz
periyodik olarak TTL'yi tazeler.

## 4. `/commit` ve 409'un idempotent çözümlenmesi

Commit dava kaydını `DERDEST` durumuyla açar (`case_intake.py:1093`). `add_case`
`duplicate_tracking_no` dönerse akış **nihai 409 vermez**; önce muhafazakâr bir eşleşme
denenir (`case_manager.find_idempotent_commit_match`).

Gerekçe kodda yazılı (`case_intake.py:1097-1101`):

> Faz 3-D (plan 3.5): 409 artık nihai değil — yanıtı kaybolan önceki commit'in KENDİ
> davasına çarpmış olabiliriz (çift tıklama / timeout sonrası tekrar). Muhafazakâr eşleşme
> tutarsa mevcut dava idempotent sonuç olarak döner; eski "sıra numarasını artırıp tekrar
> deneyin" yolu bu senaryoda aynı davayı İKİNCİ kez açtırıyordu.

Eşleşme tutarsa `idempotent_reuse = True` ile mevcut dava döner. Tutmazsa gerçek çakışmadır:
`[TRACKING_NO_COLLISION]` ERROR telemetrisi yazılır ve 409 atılır. Bu telemetrinin
`add_case`'ten buraya taşınması bilinçlidir — sayaç önerisi hâlâ dolu numara üretiyorsa
buradan görülür (`case_intake.py:1114-1120`).

## 5. Ofis dosya numarası (`tracking_no`)

Numara beş bloktan oluşur ve doğrulaması `frontend/src/lib/caseNumberUtils.ts:205-208`'deki
regex'tir: `AA.BBBBBBBBBB.CCCC.DDDD.EEEEE`.

### Sayaç bloğu — atomik tahsis

Sayaç `/process` sırasında SharePoint'ten ETag/`If-Match` ile atomik tahsis edilir; ayrıntı
ve timeout davranışı [`belge-isleme-hatti.md` §6](belge-isleme-hatti.md#6-ofis-dosya-numarası--atomik-tahsis)'da.

### İsim bloğu — kategori önceliği

Birden çok müvekkil varsa isim bloğuna girecek olan **ilk müvekkil değil**, kategori
önceliği en yüksek olandır (`caseNumberUtils.ts:150-167`). `pickNameClient`'in öncelik
fonksiyonu birebir:

| Kategori | Öncelik (küçük = güçlü) |
| --- | --- |
| `Doktor` | 0 |
| `Sağlık Çalışanı` | 1 |
| `Hasta` | 2 |
| `Bireysel` | 3 |
| kategori yok | 4 |
| diğer (kurum vb.) | 6 |
| adında/kategorisinde "sigorta" geçen | 10 |

Kategori **kodu** ayrı bir fonksiyondur (`bestCategoryCode`, `:173-203`) ve sırası:
özgül sigorta (S1–S7) > S0 > D1 > D2 > H2 > H1 > X1. Kodda bu sıranın bir düzeltme olduğu
not düşülmüş: "Docstring'deki açık öncelik: D1 > D2 > H2 > H1 (önceden 'ilk X1 olmayan'
idi)" (`caseNumberUtils.ts:197`).

> Bu öncelik kullanıcı tarafından bilinçle onaylanmıştır — **değiştirme**. Karar kaydı:
> [`002-ofis-no-isim-blogu-onceligi.md`](../kararlar/002-ofis-no-isim-blogu-onceligi.md).

### Sıra bloğu

`GET /api/cases/client-sequence` (`backend/routes/cases.py:123`) müvekkile/isim bloğuna ait
bir sonraki sırayı önerir.

## 6. Taslak kalıcılığı ve logout susturması

Taslak motoru `frontend/src/lib/formDraft.ts`'tir: sürümlü zarf + **sessionStorage** +
debounce'lu yazım. Depo seçimi KVKK gerekçesiyle kodda yazılıdır: "taslaklar
sessionStorage'da tutulur — sekme kapanınca ölür. TC/isim içeren form verisi kalıcı
localStorage'a YAZILMAZ" (`formDraft.ts:10-11`). Sürüm değişince eski taslak sessizce
atılır (`:14`), `maxAgeMs`'ten eski taslak bayat sayılıp silinir (`:31-32`).

Üç tüketici var: `intakeDraft.ts` (sihirbaz — desenin ilk hâli), `newCaseDraft.ts` (yeni
dava formu), `uploadFlowDraft.ts` (belge yükleme akışı) (`formDraft.ts:4-8`).

### Neden bir "susturma" bayrağı var

Çıkışta `clearAppStorage()` taslakları siliyordu ama hemen ardından gelen `logoutRedirect`
navigasyonu `pagehide` + `beforeunload` tetikliyor, bu flush'lar taslağı sessionStorage'a
**geri** yazıyordu. sessionStorage aynı sekmedeki AAD gidiş-dönüşünde hayatta kaldığı için
sonraki kullanıcı, önceki kullanıcının TC içeren taslağını "geri yükle" şeridiyle görürdü
(`formDraft.ts:49-53`).

Çözüm: Sidebar, temizlikten **önce** `suppressAllDrafts()` çağırır. Bayrak kuruluyken hiçbir
`DraftStore.save` diske yazmaz ve `attachUnloadGuard` ne uyarı diyaloğu ne flush üretir.
Bayrak modül-içi bellektedir; redirect/reload sayfayı tazeleyince kendiliğinden sıfırlanır
(`formDraft.ts:55-59`).

Önemli istisna, kodda büyük harflerle: **oturum düşmesi (401 → `SESSION_EXPIRED_EVENT`) bu
bayrağı KURMAZ** — orada flush bilinçli bir özelliktir, aynı kullanıcı tekrar girince emeği
geri gelir (`formDraft.ts:61-64`).

Karar kaydı: [`007-logout-taslak-susturmasi.md`](../kararlar/007-logout-taslak-susturmasi.md).

## 7. Taraf eşleştirme — tanıdık sorgu / çıkar çatışması

`POST /api/parties/check` (`backend/routes/parties.py:143`) uçtur; mantık `backend/party_check.py`
içinde **saf modül** olarak durur — DB erişimi yoktur, satırlar route katmanından dict olarak
gelir, böylece DB'siz birim test edilebilir (`party_check.py:4-7`).

Eşleşme kademeleri, güçlüden zayıfa (`party_check.py:9-17`):

| Kademe | Güven | Kural |
| --- | --- | --- |
| `tc_no` | `certain` | 11 haneli TC tam eşleşme |
| `name_exact` | `probable` | normalize isim eşitliği; kelime sırası farklı olsa da tüm kelimeler aynıysa exact |
| `name_fuzzy` | `possible` | **kelime bazlı** Levenshtein: kelime sayısı eşit olmalı ve HER kelime kendi içinde eşleşmeli (≤7 harf→1, daha uzun→2 tolerans) |

Fuzzy kademesinin dar tutulması bilinçli: "'Ali Veli' ↔ 'Ali Beki' eşleşmez — yalnızca ilk
ismin aynı olması yetmez, soyisim de eşleşmeli" (`party_check.py:16-17`).

**Normalizasyon**: NFD + birleşik-işaret temizliği → Türkçe upper → diakritik katlama →
unvan temizliği → boşluk sadeleştirme (`party_check.py:61-80`, `normalize_person_name`).
NFD adımı şart: bazı kayıtlarda `i̇` (i + U+0307) gibi görünmez karakterler var;
temizlenmezse birebir aynı isim exact yerine fuzzy'ye düşer ya da hiç eşleşmez
(`party_check.py:65-67`).

Kurumsal isimler fuzzy'den muaftır — sigorta şirketleri birbirine benzediği için gürültü
üretirdi; `_CORPORATE_WORDS` normalize edilmiş isimde **kelime olarak** aranır ("HASAN"daki
"AS" gibi substring yanlış pozitiflerini önlemek için) (`party_check.py:51-54`).

**`conflict=True` tek bir koşulda üretilir**: CLIENT olmayan bir sorgu, `contact_type="Client"`
bir cari kaydıyla eşleşirse (karşı taraf ofisin müvekkili → çıkar çatışması riski). Müvekkil
satırı çatışma üretmez; müvekkilin geçmiş dosyalarda karşı taraf olarak görünmesi yalnız
bilgi olarak listelenir. Bu 2026-08-01 kullanıcı kararıdır: "çıkar çatışması yalnız karşı
tarafa bakılır" (`party_check.py:19-25`).

## 8. Belge bağlandığında dava zenginleşmesi

Bir belge `/confirm`'de bir davaya bağlanınca iki yardımcı koşar:

- `_auto_update_case_status(case_id, belge_turu_kodu, uploaded_by)` — `backend/routes/processing.py:160`
- `_auto_enrich_case_data(case_id, avukat_kodu, karsi_taraf, uploaded_by)` — `:213`

İkisi de `/confirm` akışından çağrılır (`processing.py:869`, `:875`) ve hata durumunda
akışı devirmez; oturum kapatma/rollback davranışları test altındadır
(`backend/tests/test_faz0_hardening.py`, `backend/tests/test_faz3_e_hardening.py`).

Aşama geçişleri `case_stage_logs`, alan değişiklikleri `case_history` tablosuna yazılır
(`backend/models.py`); intake zenginleştirmesi kaynağını `intake-enrich: <belge adları>`
imzasıyla bırakır.

## 9. Aşama/karar tarihçesi — `case_stage_decisions` (G062)

Karar künyesi `cases`te aşama başına **tek slottu** (yerel `karar_no`/`karar_tarihi`,
`istinaf_*`, `temyiz_*`, `karar_duzeltme_*`); aynı aşamanın ikinci kararı eskisini
eziyordu (kanıt vakası id-2271: Danıştay 2023 Bozma + 2026 Onama). `case_stage_decisions`
tablosu bu kararların tarihçesini taşır — desen `case_esas_numbers`ın (G045) karar ikizidir
(`backend/models.py::CaseStageDecision`).

- **Tek yazma yolu** `backend/managers/stage_decisions.py`'dir (add/delete/get). Aşama
  kümesi `DECISION_STAGES = YEREL|ISTINAF|TEMYIZ|KARAR_DUZELTME` — `ONCEKI` bilinçli yok,
  o yalnız esas numarası kavramıdır.
- **Sıralama `sira_no` iledir, tarihle değil** (tasarım paketi: 170 föyde karar tarihleri
  güvenilmez). `UNIQUE (case_id, stage, sira_no)` kısıtı `uq_case_stage_decision`
  migrasyonun `("index", …)` op'undadır (`backend/database.py` madde 35, G041 kuralı).
- **Senkron kuralı:** her yazım/silmeden sonra aşamanın **en yüksek `sira_no`'lu** satırı
  `cases`teki o aşamanın slot kolonlarına "son aşama fotoğrafı" olarak yazılır
  (`stage_decisions._PHOTO_COLUMNS`); satır kalmazsa fotoğraf temizlenir. Slot kolonları
  o andan itibaren türetilmiştir. `cases.esas_no`/`court`a asla yazılmaz (tek yazma yolu
  `sync_current_esas`), `karar_turu`/`karar_lehine` türetmesi kapsam dışıdır.
- **Kapalı havuz:** `karar_durumu` stage'in G060 resmi listesine karşı doğrulanır
  (YEREL→`local_decisions`, ISTINAF→`appeal_decisions`, TEMYIZ→`cassation_decisions`,
  KARAR_DUZELTME→`revision_decisions`).
- **Tahmin yasağı:** `dogrulama_durumu` UYAP|BELGE|TURETILDI|BELIRSIZ; verilmezse
  BELIRSIZ (server_default dahil — ham INSERT bile damgasız satır bırakamaz). `kaynak_id`
  self-FK'sı kararın soyunu tutar (bozma → yeni yerel), ON DELETE SET NULL.

Okuma/yazma uçları ve UI bu görevin kapsamı dışında bırakıldı (FAZ F aktarımı ve sonrası);
testler `backend/tests/test_g062_stage_decisions.py`.

## 10. Föy modeli — kart bölünmez, SistemNo `case_foys`ta yaşar (G063)

Kullanıcı kararı (18.08): **dava TEK kart kalır, müvekkiller kartın altında; kart föy
bazında BÖLÜNMEZ.** Karşı tarafın teslimleri ise sonsuza dek SistemNo anahtarlıdır ve bir
kartta birden çok SistemNo yaşar (ön analiz: 1.211 mevcut kart 2+ föyü birleşik taşıyor;
TKU'da 1.537 çok üyeli grup / 4.030 satır). `cases.sistem_no` **tek kolonu** bunu taşıyamaz:
föyler arası farklı kalan kimlik alanları (10.08 ölçümü — Hasar No 144, Dava Değeri 211, Son
Durum 332, Durum 137 grupta farklı) tek karta ezilirse veri kaybolur.

`case_foys` bu yüzden kartın kimliğini bölmeden föyleri kartın altına asar
(`backend/models.py::CaseFoy`): `sistem_no` · `case_id` · `case_party_id` · `tku_no` ·
`hasar_no` · `source`. Desen `case_esas_numbers` (G045) ve `case_stage_decisions` (G062)
kardeşlerinin aynısıdır.

- **Tek yazma yolu** `backend/managers/foy_map.py`: `upsert_foy` / `get_foy` /
  `get_case_foys` / `map_sistem_no_to_case`. Fonksiyonlar commit etmez (flush eder).
- **`sistem_no` UNIQUE = aktarımın idempotency anahtarı.** Teslim partiler hâlinde ve
  düzeltme listeleriyle tekrar gelecek; ikinci yazım satır ikilemez, günceller. Kısıt
  `uq_case_foys_sistem_no` migrasyonun `("index", …)` op'undadır (`backend/database.py`
  madde 36, G041 kuralı) — modelde `unique=True` yoktur, iki kurulum yolu aynı adı üretsin
  diye. Anahtar kırpılmaz, sınırı aşarsa reddedilir (kırpma iki föyü tek satıra çökertirdi);
  kimlik olmayan alanlar WARNING'le kırpılır.
- **Silme kuralları — sessiz kopma yok.** `case_id` FK'sında `ondelete` bilinçli VERİLMEDİ
  (NO ACTION/RESTRICT): dava silmesi zaten SOFT'tur (`deleted_at`) ve föy envanterine
  dokunmaz; bir hard-delete denemesi ise veritabanınca reddedilir. `case_party_id` ise
  `ON DELETE RESTRICT` — `CaseDocument.case_party_id`'nin SET NULL tuzağının tekrarı
  istenmiyor: föyün hangi müvekkile ait olduğu bir taraf silmesiyle unutulamaz. `Case.foys`
  ilişkisi `passive_deletes="all"` ile ORM'in araya girmesini de kapatır.
- **Kapsam sınırı:** `cases.sistem_no` / `cases.tku_no` kolonlarına bu turda DOKUNULMADI
  (prod'da ikisi de 0 dolu); nihai tekilleştirme FAZ F aktarım turunun işidir. Çekirdek =
  kimlik + bağ.
- **Föy düzeyi alanlar (G123, 05.09.2026 — "54 sütunun tamamı" kullanıcı kararı):**
  `mko_id` (teslimin "Dosya - Föy Bilgileri" kimliği) · `muvekkil_no` ("MüvekkilNo") ·
  `muvekkil_tipi` · `hizmet_turu` · `durum`. Gerekçe ölçülü: 04.09 paketinde kart tek
  slotuna sığmayan kardeş-föy çelişkisi hizmet türünde 973, müvekkil tipinde 891, durumda
  181 kart — kart alanı D9 gereği yazılmaz, bilgi föyde kayıpsız durur (tanınan değer
  kanonik adla, tanınmayan hücre teslimdeki ham yazımıyla; `hukdok_aktarim.foy_degerleri`).
  Kolonlar migrasyon madde 43'te; `("columns", …)` op'u + create_all aynı şemaya çıkar.
- **Ham satır (G125, 05.09.2026 — "kayıpsız" şartı):** `case_foys.ham_veri` JSON, teslimdeki
  satırın tamamı orijinal başlıklarla (tarih ISO, Decimal metin; boş hücre hariç,
  tanınmayan sütun dahil; `HamSatir.ham`, `xlsx_oku`). Kart alanına yazılamayan değer
  (kardeş föy çelişkisi — 04.09 paketinde 1.180 kart / 6.835 alan —, mükerrer eşleşme,
  henüz açılmamış alan) föyde durur; paket dosyasına dönmek gerekmez. Son teslimin
  fotoğrafıdır (üzerine yazılır; dar paket dar fotoğraf bırakır). Kartın föy panelinde
  "Teslimdeki ham satırlar" açılır bloğu. Migrasyon madde 45.
- **Okuma ve UI (G123):** `case_manager.get_case` föyleri `foyler` listesinde döner; kart
  ekranındaki `CaseFoyPanel` (frontend/src/components) SistemNo/TKU/hasar no + föy düzeyi
  üçlü + kapsam rozetini basar. Dava araması `case_foys.tku_no` ve `sistem_no` kollarını da
  UNION'a katar (`_term_case_id_selects`) — legacy `cases.tku_no` boş olduğu için TKU
  araması o güne dek boş dönüyordu.

Yazma ucu yoktur (tek yazıcı aktarım); testler `backend/tests/test_g063_case_foys.py`
(şema kilitleri + sqlite davranışı + gerçek Postgres'te UNIQUE/RESTRICT) ve
`test_g123_tum_sutunlar.py` (föy düzeyi alanlar, çelişkide kayıpsızlık, arama kolları).

## 11. Değer havuzları ve çok değerli alanlar (G124)

Kullanıcı kararı (05.09.2026): "menüleri listedeki bilgilerden oluşturalım; onların
hatalısını geçirelim, lokal migrasyon bitince hepsini elden geçiririz." 04.09 paketinin
54 sütunu değer yapısı açısından ölçüldü; sonuç üç kalem:

- **Çok değerli beşli.** Tıbbi Süreç · Tıbbi Olay · İddia Edilen Kusur · Hastada Oluşan
  Zarar · Uygulanan Yöntem bir hücrede 9 parçaya kadar değer taşır (`" ; "` ayraçlı);
  200/300 kolon sınırı kuru koşuda 18 hücreyi kırpıyordu. Sınır kalktı (migrasyon madde
  44, `ALTER … TYPE VARCHAR`), değer aynı metin kolonunda birleşik durur; ayırma/birleştirme
  tek yerde: `services/multi_value.py` (frontend ikizi `lib/multiValue.ts`, aynı ayraç,
  virgül ayraç DEĞİLDİR). Takip paneli beşliyi çok seçimli düzenler
  (`trackingDraft.MEDICAL_FIELDS`, tip `multiselect`); yazma kapısı her parçayı kendi
  listesine karşı doğrular (`case_manager._MULTI_LIST_COLUMNS` → tanınan parça KANONİK
  yazımla birleşir, tanınmayan 400, liste boşsa atlanır). Kart "Tıbbi Bilgiler" bölümü
  salt okunur; `closedListState` parça parça bakar.
- **Sekiz yeni kapalı liste** (ClientType deseni, `LIST_REGISTRY` + `DEPENDENCIES` +
  `LIST_TITLES` + DynamicConfig getter/setter + `/api/config/<liste>` üçlüsü — route'lar
  `routes/config._register_simple_list` fabrikasından): `currencies` (seed sabiti TL/USD/EUR,
  TL varsayılan; `cases.para_birimi`, takip paneli `VALUE_FIELDS`), `medical_processes`,
  `medical_events`, `patient_harms`, `applied_methods` (tıbbi beşlinin dördü;
  `alleged_faults` zaten vardı), `cassation_courts` ve `appeal_courts` (temyiz/istinaf
  mahkemesi ÖNERİ listesi — alan serbest metin kalır, panelde `combo` tipi = datalist,
  doğrulanmaz), `defendant_administrations` (davalı idare taraf adı önerisi, bağsız).
- **Havuz seed'i paketten:** `scripts/deger_havuzu_seed.py --input <paket> [--apply]`
  `Sheet` sütunlarının atomik değerlerini ilgili listeye YENİ satır olarak ekler (mevcut
  ada dokunmaz, silmez, yeniden adlandırmaz; kod `_karar_kodu`, çakışmada `_2` soneki;
  sıra = sıklık). Dört karar durumu listesi de buradan beslenir — ekibin bozuk yazımları
  ("Karar Aaleyhe", "YARGITAY .....HD") OLDUĞU GİBİ girer; temizlik yönetim panelinden.
  Lokal koşu (05.09): 1.579 yeni satır, ikinci koşu 0. Gerçek paket repoya girmez;
  testler `backend/tests/test_g124_deger_havuzlari.py`.
- **Taraf rolü:** `Aleyhine Başvurulan`, `Alacaklı`, `Katılan` seed'e girdi (paket: 429 ·
  83 · 3 föy) — aktarım rol metnini zaten yazıyordu, dropdown "liste dışı" gösteriyordu.

**Kartsız föyler için kart açma (G126, 05.09.2026):** aktarımın "kart yaratmaz" kuralı
değişmedi; `scripts/kartsiz_foy_kart_ac.py --input <paket> [--apply]` ayrı bir adımdır.
Ne SistemNo'su ne DosyaNo parçası bir karta düşen föyleri DosyaNo'ya göre gruplar
(aynı DosyaNo'daki ARB + HUKUK föyleri tek kart; künye asıl davanın föyünden) ve
`case_manager.add_case` ile MİNİMAL kart açar: ofis no `retag_tracking_nos` kuralıyla
(kategori kodu Müvekkil Tipi'nden, 10 karakter isim bloğu, blok başına DB max+1 sıra,
tür, `00000`), klasör no = DosyaNo, durum, tür, konu, mahkeme, esas, dava tarihi.
Taraf/avukat YAZMAZ (aktarımın işi; add_case'in otomatik cari kart davranışı böylece
tetiklenmez). Sonraki aktarım koşusu föyleri DosyaNo köprüsüyle bağlar. Lokal 05.09:
217 föy → 210 kart, ardından aktarım 217 yeni föy / 632 taraf / 244 avukat, kartsız 0.
Testler `backend/tests/test_g126_kartsiz_foy_kart_ac.py`.

**Mükerrer kart birleştirme (G127, 05.09.2026):** eski aktarımın aynı dava için açtığı ikiz
kartlar (aynı esas + müvekkil kümesi; mahkeme ikisi de doluysa aynı) aktarımın "belirsiz
eşleşme" kuralına takılıyor, föy hiçbir karta yazılmıyordu. `scripts/mukerrer_kart_birlestir.py
--cift kalan:mukerrer [--apply]` mükerrerin her şeyini kalan karta taşır (taraf/avukat AD bazlı
tekil; belge `case_id` + `case_party_id` yeniden bağlanır — SET NULL tuzağı yok; föy, aşama
satırı [kalanda o aşama boşsa], esas tarihçesi, ilişki, duruşma, bildirim, aşama günlüğü
yeniden işaretlenir; `klasor_no_2` birleşimi; boş kart alanları tamamlanır; DERDEST üstün) ve
mükerreri SOFT siler (`deleted_at`/`active=False`/`delete_reason`, ofis no mükerrerde kalır).
Tarihçe mükerrerde kalır, kalana `mukerrer_birlestirme` notu düşer. "Kartlar birleştirilmez,
bağlanır" (TKU) kuralı ayrı davalar içindir; burada AYNI dava iki kez açılmış. Mükerrer
olmayan çift ön koşulda REDDEDİLİR. Lokal 05.09: 8 çift birleşti, aktarım 9 föyü bağladı,
belge envanteri DENK. Testler `backend/tests/test_g127_mukerrer_kart_birlestir.py`.

Dropdown yapılmayanlar (bilinçli): kimlikler, tarihler, tutarlar, taraf adları, esas
numaraları, açıklama metinleri, Para Birimi dışında tek değerli sütunlar. Tıbbi Olay 667
değerle dropdown değil arama-önerili çok seçimlidir. İlişkisel tasnif tablosu (parça
başına satır) ertelendi: filtre/istatistik ihtiyacı doğunca `multi_value` tek yeri
değişir.

## 11. Belgeleme olayı alanları — `olay_turu` + `hukumdeki_rol` (G103)

Veri ekibinin 25.08 ölçümü (HUKDOK_BELGELEME_OLAYI_BULGUSU_2026-08-25): bağlı föylerin
~%14'ünde tazminatın kaynağı tıbbi olay değil **belgeleme olayı** (aydınlatma ihlali /
tıbbi kayıt eksikliği) — 45 dosyada "kusur yok ama tazminat var" görünümü doğdu; ayrıca
aynı olgu yargı kademesine göre rol değiştiriyor ("saptandı" ≠ "kazandırdı"). Kullanıcı
kararı (02.09): iki alan, kapalı liste mekanizmasının kopyası, zorunluluk yok, tahmin
yazılmaz.

- **İki kolon:** `cases.olay_turu` ve `cases.hukumdeki_rol`, VARCHAR(100) NULL +
  DEFAULT'suz (`backend/database.py` madde 38). **NULL = "karar okunmadı"** — meşru
  durumdur, backfill YOK. Hiçbir bağlamda zorunlu değiller (`required_fields.py`
  DEĞİŞMEDİ; kilit: test dosyasındaki `test_alanlar_hicbir_baglamda_zorunlu_degil`).
- **İki KAPALI liste** — `appealing_parties` deseninin kopyası (model + LIST_REGISTRY +
  DEPENDENCIES + seed + config route + DynamicConfig setter'ı):
  `event_types` (Olay Türleri, seed'li 3 değer: Tıbbi Olay · Belgeleme Olayı ·
  Tıbbi + Belgeleme) ve `judgment_roles` (Hükümdeki Roller, seed'li 4 değer:
  Tek Gerekçe · Yan Gerekçe · Yalnız Saptama · Reddedilmiş İddia) —
  `backend/models.py::EventType/JudgmentRole`, `seed_data.EVENT_TYPES/JUDGMENT_ROLES`.
  SEED'LİDİR: değerler karşı taraf teyidi beklemiyor (`alleged_faults` da 04.09.2026'dan
  beri seed'li: 9 değer DB-2026-001 bildirimiyle geldi, `seed_data.ALLEGED_FAULTS`). KARMA
  bilinçli: kart alanı tek slot, ölçümün "yan gerekçe" sınıfında iki tür birlikte
  görülüyor — karma durum açık değerle taşınır, tahminle tekilleştirilmez.
- **Hükümdeki Rol'ün anlamı:** belgeleme olgusunun **güncel kademedeki** hükümde
  oynadığı rol; kademe değişince değer düzeltme partisiyle güncellenir (E-9/bayat
  hüküm kuralıyla uyumlu).
- **Yazma yolu takip panelidir:** iki alan `TRACKING_FIELDS`te; `update_case_tracking`
  yazımdan önce G066 davranış eşi bir kapıdan geçirir
  (`case_manager._EVENT_LIST_COLUMNS` + `validated_event_list_value`): liste dışı
  değer `InvalidDecisionStatusError` ile reddedilir (api.py 400'e çevirir), liste
  BOŞSA doğrulama WARNING'le atlanır (seed'i koşmamış kurulum kilitlenmez), None
  gönderimi alanı temizler, `active` filtresi yok.
- **Okuma/filtre:** `get_case` çıktısında iki alan; `get_cases(olay_turu=...)` +
  `GET /api/cases?olay_turu=` `file_type` kalıbıyla eşitlik filtresi (değer listenin
  ADIDIR, "ALL" = filtre yok).
- **Uçlar:** `GET/POST/DELETE /api/config/event_types` ve `/api/config/judgment_roles`
  (`backend/routes/config.py`; POST/DELETE admin — alleged_faults kalıbı).

UI (kart alanları, rozet, liste filtresi dropdown'ı) G105'in işidir; testler
`backend/tests/test_g103_belgeleme_olayi.py` (şema kilitleri + sqlite seed/kapı/filtre
davranışı + route 400/403 + gerçek Postgres'te migrasyon yolu).

## 12. Müvekkil Tipi + Hizmet Türü — `muvekkil_tipi` + `hizmet_turu` (G119)

Veri ekibinin Format Değişiklik Bildirimi **DB-2026-002** (04.09.2026): ilk teslim
paketinden itibaren `Sheet` sayfasında föy düzeyinde iki yeni sütun geliyor, 8.409 föyün
tamamında dolu. **Müvekkil Tipi** büronun bu föyde kimi temsil ettiğidir — kaydın hangi
yönden okunacağını belirler (E-8: karar durumu ve tutarlar müvekkil yönünden yazılır).
**Hizmet Türü** büronun verdiği hizmetin türüdür — "Lexis Rapor" föyleri dava takibi
değil rapor işidir; ayrım yapılmazsa dava sonucu istatistikleri yanlış çıkar. Bu turdan
önce iki sütun sessizce yok sayılıyordu.

- **Tasarım kararı (04.09):** mevcut `client_categories` (müvekkil VARLIĞININ kategorisi,
  `Client.category`) ve `bureau_types` ("Büro Özel Türü" — ayrı bir teslim sütunu,
  `cases.bureau_type`) **kullanılmadı ve değişmedi**: ikisi de başka varlık/sütunun
  listesi, değer havuzları örtüşmüyor (Hizmet Türü 9 ≠ bureau_types 8; Müvekkil Tipi föy
  düzeyi, `Client.category` müvekkil düzeyi). İki YENİ liste açıldı; Müvekkil Tipi ↔
  `Client.category` köprüsü gündüz kararıdır. Mevcut `cases.service_type` (ofis dosya
  numarasının 5 haneli hizmet bloğu, `required_fields.py`'de "Hizmet Türü" etiketli) de
  AYRI bir alandır — yeni `hizmet_turu` onunla karıştırılmaz.
- **İki kolon:** `cases.muvekkil_tipi` ve `cases.hizmet_turu`, VARCHAR(100) NULL +
  DEFAULT'suz (`backend/database.py` madde 42, madde 38'in kopyası). **NULL =
  "bilinmiyor"**, backfill YOK (aktarım eşlemesi G120). Hiçbir bağlamda zorunlu değiller
  (`required_fields.py` DEĞİŞMEDİ; kilit `test_alanlar_hicbir_baglamda_zorunlu_degil`).
- **İki KAPALI liste** — `event_types` deseninin kopyası (model + LIST_REGISTRY +
  DEPENDENCIES + seed + config route + DynamicConfig setter'ı):
  `client_types` (Müvekkil Tipleri, seed'li 5 değer: Sigorta · Doktor · Kurum · Hasta ·
  Diğer Sağlık Çalışanı) ve `service_types` (Hizmet Türleri, seed'li 9 değer: Takip
  (doktor müvekkil) · Lexis Rapor · Vekaletsiz Takip · Vekaletli Takip · Vekalet Ücreti
  Alacağı · Takip (hasta vekilliği) · Takip (kurum vekilliği) · Danışmanlık · Takip
  (sağlık personeli)) — `backend/models.py::ClientType/ServiceType`,
  `seed_data.CLIENT_TYPES/SERVICE_TYPES`, sıra bildirimdeki sıra, kodlar ASCII ve değişmez.
- **Yazma yolu takip panelidir:** iki alan `TRACKING_FIELDS`te; `update_case_tracking`
  aynı kapıdan geçirir (`case_manager._EVENT_LIST_COLUMNS`e iki satır eklendi,
  `validated_event_list_value` değişmedi): liste dışı değer `InvalidDecisionStatusError`
  (400), liste BOŞSA WARNING'le geç, None gönderimi temizler, `active` filtresi yok.
- **Okuma/filtre:** `get_case` çıktısında iki alan; `get_cases(hizmet_turu=...)` +
  `GET /api/cases?hizmet_turu=` `olay_turu` kalıbıyla eşitlik filtresi (değer listenin
  ADIDIR, "ALL" = filtre yok). Müvekkil Tipi için filtre BİLİNÇLİ yok (sözleşme).
- **Uçlar:** `GET/POST/DELETE /api/config/client_types` ve `/api/config/service_types`
  (`backend/routes/config.py`; POST/DELETE admin — event_types kalıbı).

Aktarım eşlemesi (`scripts/hukdok_aktarim.py`, iki yeni `Sheet` sütunu) G120'nin işidir
ve **uygulandı** (`SUTUN_ADAYLARI` + `KART_ALANLARI` iki kayıt; tanınmayan/çok değer
`AlanHatasi`, `backend/tests/test_g120_aktarim_muvekkil_hizmet.py`); kart UI'ı G121'in
işidir ve uygulandı (büro kartında `bureau_type` altında iki alan, liste filtresi
`hizmet_turu`). G119 testleri `backend/tests/test_g119_muvekkil_tipi_hizmet_turu.py`
(şema kilitleri + sqlite seed/kapı/filtre davranışı + route 400/403 + gerçek Postgres'te
migrasyon yolu + `client_categories`/`bureau_types` değişmezlik kilidi).

## 13. Kapalı liste envanteri — dava kartının FAZ F listeleri (04.09.2026)

`managers/reference_lists.LIST_REGISTRY` toplam **23** liste taşır; hepsi aynı mekanizmadır
(model + `ListSpec` + `DynamicConfig` setter'ı, `seed_all_lists` yalnız boş tabloyu
doldurur). Bunların **10'u** dava kartının kapalı-havuz alanlarını besler ve 04.09.2026
itibarıyla **hepsi seed'lidir** — sayılar `managers/seed_data.py` sabitlerinden:

| Liste anahtarı | Seed sabiti | Değer | Beslediği alan | Kaynak / görev |
| --- | --- | --- | --- | --- |
| `alleged_faults` | `ALLEGED_FAULTS` | 9 | `cases.iddia_edilen_kusur` (aktarım METİN yazar; liste kart seçimi + `DEGER_HAVUZLARI` farkı) | DB-2026-001 (04.09), `9608031` — **G044'ten 04.09'a kadar bilinçli boştu**, "seed'lenmez" ifadesi tarihseldir |
| `appealing_parties` | `APPEALING_PARTIES` | 3 | aşama `basvuran_taraf` (`İstinaf Mahkemesi Başvuran Taraf`) | G044 |
| `local_decisions` | `LOCAL_DECISIONS` | 28 | `case_stage_decisions.karar_durumu` (YEREL) | G060, 10.08 `DEGER_HAVUZLARI` |
| `appeal_decisions` | `APPEAL_DECISIONS` | 3 | aynı (ISTINAF) | G060 |
| `cassation_decisions` | `CASSATION_DECISIONS` | 3 | aynı (TEMYIZ) | G060 |
| `revision_decisions` | `REVISION_DECISIONS` | 2 | aynı (KARAR_DUZELTME) | G060 |
| `event_types` | `EVENT_TYPES` | 3 | `cases.olay_turu` | G103 (§11) |
| `judgment_roles` | `JUDGMENT_ROLES` | 4 | `cases.hukumdeki_rol` | G103 (§11) |
| `client_types` | `CLIENT_TYPES` | 5 | `cases.muvekkil_tipi` | G119 (§12), DB-2026-002 |
| `service_types` | `SERVICE_TYPES` | 9 | `cases.hizmet_turu` | G119 (§12), DB-2026-002 |

Kalan 13 liste (`lawyers`, `statuses`, `doctypes`, `case_subjects`, `emails`, `file_types`,
`court_types`, `party_roles`, `bureau_types`, `cities`, `specialties`, `client_categories`,
`file_statuses`) kart havuzu değil, kurulum listeleridir; `lawyers`/`statuses`/`doctypes`/
`case_subjects`/`emails` seed'siz doğar (`seed_all_lists`'te çağrı yok), diğer sekizi
seed'lidir (`court_types` için `COURT_TYPES_SEED` sözlüğü). `DEGER_HAVUZLARI` fark raporu bu
envanterin yalnız altısını karşılaştırır (`services/teslim_cevap.py::HAVUZ_LISTE_ESLEMESI`;
`client_types`/`service_types` eşlemede yok — bkz.
[`veri-teslim-hatti.md` §7](veri-teslim-hatti.md)). Veri ekibine verilen değer
tablosu `docs/veri-teslim/BILGILENDIRME_2026-09-03.md` §3.8 ile birebir aynıdır.
