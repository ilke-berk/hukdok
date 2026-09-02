# Dava açma akışı — manuel form, intake sihirbazı, ofis numarası

> **Son doğrulama: 2026-08-11 · 2eade56**
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
  (prod'da ikisi de 0 dolu); nihai tekilleştirme FAZ F aktarım turunun işidir. Per-föy ek
  alanlar (dava değeri, son durum, hizmet türü…) da açılmadı — kolon seti 68 sütunluk eşleme
  tablosuyla birlikte kararlaştırılacak (YAGNI). Çekirdek = kimlik + bağ.

Okuma/yazma uçları ve UI kapsam dışıdır; testler `backend/tests/test_g063_case_foys.py`
(şema kilitleri + sqlite davranışı + gerçek Postgres'te UNIQUE/RESTRICT).

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
  `alleged_faults`un aksine SEED'LİDİR: değerler karşı taraf teyidi beklemiyor. KARMA
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
