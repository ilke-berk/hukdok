# Dava açma akışı — manuel form, intake sihirbazı, ofis numarası

> **Son doğrulama: 2026-09-04 · 88409da** (§1-§10 önceki doğrulama 2026-08-11 · 2eade56;
> §11-§13 bu tarihte koddan sayıldı)
> §3 uç tablosu, §4 ve §5: **2026-09-30 · c40e10c** (G240 — karar 023 ofis no düzeni, G235-G242 koduna karşı).
> Her iddia koddan doğrulanmıştır. Kod ile çelişirse kod haklıdır — bu dosyayı düzelt.

Dava iki yoldan açılır: elle doldurulan form (`/new-case/form`) ve belgeden türeten otonom
sihirbaz (`/new-case/auto`). İkisi de aynı `cases` kaydına iner; ofis numarasını ikisinde de
**sunucu** verir (§5).

## 1. Zorunlu alanlar — kaydı ENGELLEMEZ

Tek kaynak `backend/required_fields.py`'dir. Kural docstring'de yazılıdır: **zorunlu alan
eksikliği kaydı engellemez** — dosya `DERDEST` olarak açılır, eksikler dava kartında ve
listesinde uyarı olarak görünür ve panelden filtrelenebilir (`required_fields.py:1-11`).

Reddedilen alternatif de orada kayıtlıdır: "DANIŞ'a düşürme denendi, dönüşüm kaybı riski
nedeniyle vazgeçildi: DANIŞ yolunda müvekkil kaydı oluşturulmuyor" (`required_fields.py:5-6`).

`REQUIRED_CASE_FIELDS` (`required_fields.py:51-79`): `esas_no`, `court`, `file_type`,
`judicial_unit`, `sub_type`, `opening_date`, `subject`, `responsible_lawyer_name`,
`uyap_lawyer_name`, `service_type`, `acceptance_date`, `bureau_type`, `atama_tarihi`.

**Güncel not (G046, FAZ D — bu satır ADR-014'te de anlatılıyor):** liste artık düz bir
alan adı listesi DEĞİL, liste-of-dict + isteğe bağlı bir `skip_when` "kapı"sı taşıyor —
`esas_no` alanı `file_type ∈ ESAS_BEKLENMEYEN_TURLER` (ARABULUCULUK/SAVCILIK/DANIŞMANLIK/
TAHKİM) ise zorunlu SAYILMAZ (D2). İkinci kapı türü `skip_when_lawyers_at_least` (G158, M5):
`responsible_lawyer_name` kutusu boş AMA kartın `case_lawyers` satırı ≥ `COKLU_AVUKAT_ESIGI`
(2) ise alan eksik SAYILMAZ — aktarım çoklu isimli föyde kutuyu bilerek boş bırakır, sorumlu
"belirsiz"dir, "atanmamış" değil (`required_fields.py:39-49`, `:72-73`; tek satırda kutu boşsa
eksik kalır). 13 alanın **11'i koşulsuz**, `esas_no` ve `responsible_lawyer_name` bağlamsal.
Kapı SQL ikizinde de aynı sayımla çevrilir (`_sql_lawyer_count`, `required_fields.py:215-217`);
kural değiştiğinde bayrak `scripts/backfill_missing_required.py` ile (kuru koşu varsayılan,
`--apply`) yeniden hesaplanır. Aynı mekanizma (`missing_required_bucket` kolonu,
`MISSING_BUCKET_MANUAL`/`MISSING_BUCKET_AKTARIM` kovaları) `uyap_lawyer_name`'e henüz
**bağlanmadı** — bkz.
[`014-uyap-avukati-on-doldurulmaz.md`](../kararlar/014-uyap-avukati-on-doldurulmaz.md).

`sub_type_extra` (Uzmanlık / Tıbbi İşlem) listeden **geçici** olarak çıkarılmıştır
(2026-08-04): alan UI'da gizlendiği için görünmeyen alan "eksik" uyarısı üretmesin; alan
geri açılınca satır da geri alınacak (`required_fields.py:66-69`).

Ayrıca `compute_missing_fields` karşı taraf TC'sini denetler ama **yalnız COUNTER**
taraflar için: müvekkil TC'si `Client` kaydında yaşar, form yalnız karşı taraf TC'si
girebilir — aksi halde her yeni dosya yanlış "eksik" işaretlenirdi
(`required_fields.py:81-84`, mantık `:158-163`).

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
| `POST /api/case-intake/commit` | `:1068` | Yeni dava kaydı + belge arşivleme + poliçe beslemesi |
| `POST /api/case-intake/apply` | `:1237` | **Zenginleştirme modu**: mevcut davaya kısmi güncelleme |
| `POST /api/case-intake/keepalive` | `:1335` | Review adımında PROCESS_CACHE TTL'sini tazeler |

Sihirbaz akışı: yükle → analiz → (birden çok belge varsa) birleştir → kullanıcı incelemesi
→ commit (ya da mevcut davaya apply).

`keepalive` ucunun varlığı bir tasarım sonucudur: PROCESS_CACHE TTL'si 1800 sn'dir
(`config/settings.py:89`) ve kullanıcı inceleme adımında bundan uzun kalabilir; sihirbaz
periyodik olarak TTL'yi tazeler.

## 4. `/commit` ve tekrar eden isteğin tanınması (`istek_kimligi`)

Commit dava kaydını `DERDEST` durumuyla açar (`case_intake.py:1095`).

> **`cases.status` veritabanı kısıtı (G195, 14.09.2026):** durum yalnız
> `constants.CASE_STATUSES` üçlüsüdür (DERDEST | DANIŞ | MAHZEN; karar 020 — temyiz/istinaf
> AŞAMADIR). Migrasyon madde 52 (`backend/database.py::case_status_check_ddl`) bunu
> `ck_cases_status_uclu CHECK (status IN (...)) NOT VALID` kısıtıyla veritabanına indirir;
> değer listesi `CASE_STATUSES`'ten üretilir, op koşulsuzdur ve `pg_constraint` yoklamasıyla
> idempotenttir, madde 50'nin veri düzeltmesinden SONRA koşar. Uygulama/script/elle SQL
> üçlü dışı bir değer yazarsa Postgres `CheckViolation` (23514) döner — `add_case` bunu
> unique çakışması SAYMAZ, ERROR loglayıp `None` döner (route 500).
>
> - **`NOT VALID` uyarısı:** kısıt eklenirken mevcut satırlar TARANMAZ (prod'da eski bozuk
>   değer migrasyonu durdurmaz), ama o andan sonra her yeni satır sürümü denetlenir: üçlü
>   dışı eski bir satırın **HER UPDATE'i — yalnız başka bir kolon değişse bile —
>   reddedilir**. Böyle bir kart ancak `status`'u da üçlüye çeken bir güncellemeyle
>   düzenlenebilir.
> - **NULL:** `status` kolonu nullable'dır (`models.py:19`) ve SQL CHECK semantiğinde
>   `NULL` kısıttan geçer; NOT NULL ayrı karardır.
> - **`VALIDATE CONSTRAINT` koşulu:** prod'da `scripts/perf_olcum.py` raporunun durum
>   bölümü üçlü dışı satır = 0 gösterdiğinde ayrı görevle koşulur (kısıt o zaman
>   `convalidated = true` olur). Testler `backend/tests/test_g195_status_check.py`.

Numarayı sunucu verdiği için (§5) "numara dolu → 409" sınıfı kapandı; eski "aynı numara +
taraf kümesi = aynı istek" tahmini de (Faz 3-D) koddan çıktı. Tekrar eden commit — yanıtı
kaybolan istek, çift tıklama, taslaktan devam — artık **istek kimliğiyle** tanınır
(`/confirm`'deki `process_id` deseni; `case_intake.py:1096-1131`):

- İstemci kayıt isteğine bir UUID koyar: `case.istek_kimligi` (`schemas.CaseCreate`; bozuk
  biçim 422). Kolon `cases.istek_kimligi`, tekillik kısmi UNIQUE `uq_cases_istek_kimligi`
  (migrasyon madde 57 — `backend/database.py`, koşulsuz `("index", ...)` op'u).
- **Ön bakış:** route `add_case`'ten ÖNCE `case_manager.istek_kimligi_karti(kimlik, tenant_id)`
  çağırır; kart varsa `add_case` hiç koşmaz, sayaç artmaz, mevcut kart `idempotent_reuse`
  (= yanıttaki `case.reused`) `true` ile döner. Zaman penceresi yoktur — günler sonra
  taslaktan devam eden istek de kendi kartını bulur.
- **Eşzamanlı çift istek:** kaybeden transaction unique index'e çarpar, `add_case`
  `{"error": "duplicate_istek_kimligi"}` döner (WARNING; sıra tahsisi rollback'le geri gelir),
  route kazananın kartını döndürür.
- Kimlik dolu ama kart görünmüyorsa (soft-delete edilmiş ya da başka tenant'a damgalı) kart
  döndürülmez ve ikinci kart da açılmaz: **409** "Bu kayıt isteği daha önce kullanılmış".
- Müvekkilsiz commit numara üretemez → `OfisNoVerilemez` → **422**; hiçbir belge tüketilmez.

Aynı koruma `POST /api/cases`'te de vardır (`backend/routes/cases.py::api_add_case`).
Kimliksiz istek (eski istemci) korumasız ama geçerlidir. Testler
`backend/tests/test_g236_ofis_no_kayit.py`, `backend/tests/test_faz3_confirm_idempotency.py`.

## 5. Ofis dosya numarası (`tracking_no`) — karar 023

Şartname: [`023-ofis-no-formati.md`](../kararlar/023-ofis-no-formati.md). Üreticinin **tek
kanonik kaynağı** `backend/services/ofis_no.py`'dir; istemci numara ÜRETMEZ, yalnız önizler.

```
<MÜVEKKİL KODU>-<SIRA>[-<SİGORTALI>]-<TÜR>

DR.M.OZTURK-0003-HUK          kişi müvekkil
KR.ENTHONE-0015-CEZ           kurum müvekkil
AXA-3297-DR.E.ALTUNC-HUK      sigortacı müvekkil + sigortalı hekim
SG-0001-HUK                   listede olmayan sigortacı, sigortalı yok
```

Bloklar arası ayraç `-`, blok içinde `.`; yalnız ASCII büyük harf (`ofis_no.ascii_buyuk`);
dolgu karakteri ve ad kesme YOK; hizmet bloğu YOK. Boş/çözülemeyen ad `ValueError`dır —
yer tutucu numara üretilmez.

### Müvekkil kodu (ilk blok)

`ofis_no.musteri_kodu(muvekkiller, kod_listeleri)`:

- **Sigortacı varsa kod sigortacınındır** (`sigortaci_mi`: kategori ya da ad "sigorta"
  içeriyor; açık kategori ada üstündür — kategorisi "Acente" olan "… Sigorta" kurumdur).
  Şirket kodu `sigorta_kodu` ile müvekkil adında KELİME eşleşmesiyle bulunur; aktif listede
  eşleşme yoksa sabit `SG` (`SG_KODU` — tabloda satırı yoktur, listeye yazılamaz).
- **Sigortacı yoksa** kategori kodu + ad: kişi kategorilerinde (`KISI_KATEGORILERI`: Doktor,
  Sağlık Çalışanı, Hasta, Bireysel) `kisi_blogu` → `<KOD>.<ilk adın baş harfi>.<SOYAD>`
  (unvanlar atılır, tek kelimelik ad baş harfsiz); ötekilerde `kurum_blogu` → jenerik
  kelimeler (`CORP_STOP`) atılıp ilk anlamlı kelime.
- Kategorisiz (ya da tanınmayan kategorili) müvekkil: adında şirket işareti varsa `KR`,
  yoksa `BR` (`sirket_isareti_var`).

| Kategori (`client_categories.code`) | Varsayılan kod |
| --- | --- |
| `DOKTOR` | `DR` |
| `SAGLIK-CALISANI` | `SC` |
| `HASTA` | `HS` |
| `OZEL-HASTANE` (Klinik dahil) | `OH` |
| `KURUM` (Acente, Dernek dahil) | `KR` |
| `BIREYSEL` | `BR` |
| `DIGER` | `DG` |

Birden çok müvekkilde adı veren **ilk müvekkil değil**, önceliği en yüksek olandır
(`ofis_no._ONCELIK`, küçük = güçlü):

| Kategori | Öncelik |
| --- | --- |
| Doktor | 0 |
| Sağlık Çalışanı | 1 |
| Hasta | 2 |
| Bireysel | 3 |
| Diğer / kategori yok | 4 |
| Özel Hastane | 5 |
| Kurum | 6 |

> Bu öncelik kullanıcı tarafından bilinçle onaylanmıştır — **değiştirme**. Karar kaydı:
> [`002-ofis-no-isim-blogu-onceligi.md`](../kararlar/002-ofis-no-isim-blogu-onceligi.md)
> (karar 023 §5 sırayı korur; eski iki haneli kod önceliği kalktı).

### Sigortalı bloğu

Yalnız sigortacı müvekkilli kartta, TEK kişi, kişinin kendi kategori koduyla
(`ofis_no.sigortali_sec`). Kaynak sırası: föy `ham_veri["Sigortalı"]` (kapsam dışı föy
atlanır; `;` ile çok adlı değerde adlar kaynaştırılmaz — `_tek_sigortali`) → rolü
"Sigortalı" olan taraf → sigortacıyla birlikte müvekkil olan kişi/kurum → "Diğer Davalı"
içindeki ilk hekim. Bulunamazsa blok yazılmaz (`AXA-3297-HUK`).

### Tür bloğu

`ofis_no.tur_kodu(cases.file_type)`: Hukuk `HUK` · Ceza `CEZ` · İcra `ICR` · Arabuluculuk
`ARB` · Savcılık `SAV` · İdare / İdari Yargı `IDR` · Tahkim `THK` · Vergi `VRG` ·
Danışmanlık `DAN`; boş ya da haritada olmayan → `HUK`. İdari yargının **tek** dava türü
`İdare`'dir (17.09.2026): `normalizeFileType` (`frontend/src/lib/caseIntake.ts`) Gemini'nin
"İdari" etiketini "İdare"ye çevirir, seed "İdari Yargı"yı kurmaz. Sihirbazın tür seçicisi
`YARGI_TURLERI` AD listesidir (`frontend/src/lib/caseNumberUtils.ts`) — kod haritası değil.

### Sıra — DB sayacı, kayıtla aynı transaction

Sıra **müvekkil kodu başına** sayılır (`DR.M.OZTURK`'un üçüncü dosyası, AXA'nın 3297.
dosyası); 4 haneye sıfırla doldurulur, 9999'dan sonra doğal uzar (`numara_kur`). Sayaç
`ofis_no_sayaclari` tablosudur (`kod` PK, `son_sira`; migrasyon madde 56); **tek yazma yolu**
`ofis_no.sira_tahsis_et` — tek ifade `INSERT … ON CONFLICT (kod) DO UPDATE … RETURNING`,
commit ETMEZ: tahsis kartın kaydıyla aynı transaction'da yaşar, kayıt geri alınırsa sıra da
geri döner. Verilen numaranın parçaları kartta da durur: `cases.ofis_no_kodu`,
`cases.ofis_no_sira` (kısmi UNIQUE `uq_cases_ofis_no_kod_sira`; NULL = yeni formatla
numaralanmamış kart).

Kayıt yolu (`case_manager.add_case`): kullanıcı route'ları (`POST /api/cases`, intake commit)
veri sözlüğüne `SUNUCU_NUMARASI_BAYRAGI` (`ofis_no_sunucudan`) koyar → istemcinin
`tracking_no`'su okunmaz, `_ofis_no_parcalari` + `sira_tahsis_et` + `numara_kur` numarayı
kurar. Kontrol, avukat adı 422'sinden ve üçlü dışı durum 400'ünden SONRA koşar. Müvekkil
yoksa `OfisNoVerilemez` → 422. Sunucunun verdiği numara `ix_cases_tracking_no`'ya çarparsa
bu sayaç tutarsızlığıdır: nihai ERROR + route 500 (409'a çevrilmez). Bayraksız doğrudan
çağrılar (aktarım/script) kendi numarasını getirir ve eski `duplicate_tracking_no` dönüşünü
görür.

**Numara verildikten sonra DEĞİŞMEZ** — müvekkil / tür / sigortalı sonradan düzeltilse de:
`update_case` `tracking_no`'yu yazmaz, PUT'ta gelen değer sessizce yok sayılır.

### Önizleme

`GET /api/cases/ofis-no-onizleme` (`backend/routes/cases.py::get_ofis_no_onizleme`):
`muvekkiller` (tekrarlanabilir; yalnız rakam = müvekkil id'si, aksi serbest ad), `file_type`,
opsiyonel `sigortali` (tekrarlanabilir ad) → `{onizleme, kod, sigortali_eksik, aciklama}`.
Sayacı ARTIRMAZ (`ofis_no.onizle` → `siradaki`); araya başka kayıt girerse gerçek sıra farklı
olabilir, önizleme isteğe geri gönderilmez. Müvekkilsiz / bilinmeyen id 422. Eski sıra
önerisi ucu kalktı: yerinde şemaya girmeyen bir mezar taşı route 404 döner
(`routes/cases.py::client_sequence_kaldirildi`).

Frontend: üç ekran (`pages/NewCase.tsx`, `components/QuickCaseModal.tsx`,
`components/intake/IntakeReviewStep.tsx`) numarayı salt-okunur gösterir; ortak kanca
`useOfisNoOnizleme` (`hooks/useCases.ts`, debounce'lu), sorgu dizgisi
`caseNumberUtils.ofisNoOnizlemeSorgusu`, kimlik `yeniIstekKimligi`. Önizleme alınamasa da
kayıt yapılır; hata uydurma numaraya çevrilmez.

### Kod listeleri — admin paneli

Kategori → kod `client_categories.ofis_no_kodu`, sigorta şirketi → kod + eşleşme kelimeleri
`sigorta_kisa_kodlari` (satır silinmez, `aktif=false`). Üretici listeleri
`ofis_no.kod_listelerini_yukle` ile DB'den okur (pasif satır eşleşmede kullanılmaz; pasife
alınan şirket `SG`'ye düşer). Uçlar `require_admin` arkasında (`backend/routes/admin.py`):
`GET|POST /api/admin/sigorta-kodlari`, `PATCH /api/admin/sigorta-kodlari/{kod_id}`,
`GET /api/admin/kategori-kodlari`, `PATCH /api/admin/kategori-kodlari/{code}`. Kod 2-10 büyük
ASCII harf; kategori kodu ile sigorta kodu çakışamaz, `SG` yazılamaz (409). Panel:
Yönetim → "Ofis No Kodları" sekmesi (`components/admin/OfisNoKodlariPanel.tsx`). Tohum:
`managers/seed_data.py` (kategori kodu yalnız BOŞ alana, sigorta listesi yalnız tablo boşken).
**Kod değişikliği yalnız YENİ numaraları etkiler.**

### Göç ve eski numaralar

Eski numaralar (nokta ayraçlı, beş bloklu düzen) `scripts/ofis_no_gocu.py` ile yeni formata
çevrilir: varsayılan kuru koşu DB'ye hiçbir şey yazmaz, rapor dizinine
`ofis_no_esleme_<tarih>.csv` (`case_id, eski, yeni, silinmis, kategori_kaynagi,
sigortali_kaynagi`), `ofis_no_sigortali_eksik_<tarih>.csv` ve `ofis_no_ozet_<tarih>.txt`
düşer. `--apply` tek transaction'dır: müvekkilsiz kart varken DURUR; her karta `case_history`
(`tracking_no`, eski → yeni, `source='OFIS_NO_GOCU'`), `case_foys.onceki_tracking_no` aynı
eşlemeyle çevrilir, sayaçlar kod başına en yüksek sıraya çekilir; envanter kapısı tutmazsa
ROLLBACK. Eski numarayla arama `case_history.old_value` kolundan çalışmaya devam eder (exact
modda bu kol yoktur — `case_manager._term_case_id_selects`). **30.09.2026 itibarıyla `--apply` hiçbir DB'de
koşulmadı** (G238 raporu): mevcut kartlar eski numarasını taşır, yalnız yeni açılan kartlar
yeni formattadır; lokal ve prod göçü kullanıcı kararıdır. Eski formatın üreticileri
(`scripts/retag_tracking_nos.py`, `scripts/import_excel_cases.py`) EMEKLİdir — çalıştırılınca
hata ile çıkar. **Eski formatı ayrıştıran kod yazılmaz:** müvekkil kodu gerekiyorsa
`cases.ofis_no_kodu` okunur, kolon boşsa (göç öncesi kart) kartın müvekkilinden üreticiyle
hesaplanır (`scripts/kartsiz_foy_kart_ac.kart_kodu`).

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
- **Yerinde güncelleme ve koruma (G150, 08.09.2026):** tek yazma yoluna
  `update_stage_decision` eklendi (`managers/stage_decisions.py:435-490`): içerik alanları
  (`CONTENT_FIELDS`, `:360-363`) yerinde değişir, damga/imza tazelenir, fotoğraf yeniden
  senkronlanır; birebir aynı içerikte satıra dokunulmaz (ikinci koşu 0). `dogrulama_durumu ∈
  {BELGE, UYAP}` satır **korumalıdır** (`is_protected`, `:430-432`) → `ProtectedStageDecisionError`
  (`:168`); paket kaynaklı ve elle girilmiş (BELIRSIZ/TURETILDI) satırlar aynı yoldan
  güncellenir — kullanıcı kararı 06.09 §0 ("son paket elle düzeltmeden daha doğru"). Silme yolu
  yalnız `delete_stage_decision` (`:565`), aktarım silmez. Aktarımın uzlaşı/çok tur kuralları
  [`veri-teslim-hatti.md` §7.1](veri-teslim-hatti.md).
- **`basvuru_tarihi` (G155):** kanun yoluna başvuru tarihi satır alanı (`models.py:297`,
  migrasyon madde 47 `database.py:1063`); fotoğraf ISTINAF → `cases.istinaf_basvuru_tarihi`,
  TEMYIZ → `cases.temyiz_basvuru_tarihi` (`_PHOTO_COLUMNS`, `:125`, `:136`) — bu iki takip
  alanı o günden beri aşama fotoğrafıdır; YEREL/KARAR_DUZELTME için kart kolonu yok.
- **Büro durumu karar değil (G151):** `Kapalı`/`Derdest` yerel havuzdan çıktı
  (`managers/seed_data.py:427-454`, liste 27); aktarım bu iki değeri "karar yok" sayar
  (`scripts/hukdok_aktarim.BURO_DURUMLARI`). Dosyanın derdest/arşiv bilgisi `cases.status`tur.

Okuma/yazma uçları ve UI bu görevin kapsamı dışında bırakıldı (FAZ F aktarımı ve sonrası);
testler `backend/tests/test_g062_stage_decisions.py`, `test_g150_asama_kurali.py`,
`test_g155_basvuru_tarihi.py`.

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
- **Föy ↔ müvekkil bağı kuruldu (G153, 08.09.2026 — plan 06.09 #28 kararı):** aktarım
  `Müvekkil` hücresinin ilk parçasına eşit CLIENT taraf satırını `case_party_id`'ye bağlar
  (`scripts/hukdok_aktarim._foy_muvekkilini_bagla`, `upsert_foy` → `_validated_party` kapısı);
  boş hücre mevcut bağı korur, bağ başka tarafa geçerse satır raporuna `MUVEKKIL_DEGISTI`
  düşer ve eski taraf satırı silinmez. Müvekkil kimliği ayrıca `DosyaNo` kökünden okunur
  (1 Axa · 2 Quick · 3 Ak · … · 8000 Nippon; 13 hizmetsiz; ≥ 500 hekim/kurum) ve eşleştirmede
  esas/tür'den sonra, müvekkil adından önce ayırıcıdır; kök ile `Müvekkil` hücresi farklı
  sigortaları söylüyorsa satır hiçbir karta yazılmaz. Lokal ölçüm (04.09 paketi): 8.385 föy
  bağlandı, belirsiz eşleşme 20 → 10. Ayrıntı [`veri-teslim-hatti.md` §7.1](veri-teslim-hatti.md).
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
  araması o güne dek boş dönüyordu. G190 (14.09.2026): yazıcısı olmayan legacy
  `cases.tku_no`/`sistem_no` kolları aramadan ve relevance sıralamasından çıkarıldı;
  TKU/SistemNo araması yalnız föy kollarından yürür. Üç föy kolunun (`tku_no`, `sistem_no`,
  `onceki_tracking_no`) trigram index'leri G189'da `backend/database.py::_TRGM_INDEXES`e
  girdi (`idx_case_foys_*_trgm`); boş legacy `cases` index'leri düşürüldü. Aramanın tamamı
  (tek koşu, index'li/index'siz kollar) `CLAUDE.md` "Dava arama" paragrafında, nihai index
  tablosu [karar 018](../kararlar/018-index-temizligi-37-kalem.md) "Nihai index durumu"nda.

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
`case_manager.add_case` ile MİNİMAL kart açar: ofis no karar 023 üreticisiyle
(`ofis_numarasi`: `ofis_no.musteri_kodu` — kategori föyün Müvekkil Tipi'nden — + föyün ham
`Sigortalı` sütunundan `sigortali_sec` + sayaçtan `sira_tahsis_et` + `numara_kur`; G239'a dek
emekli `retag_tracking_nos` kuralıyla üretiliyordu), klasör no = DosyaNo, durum, tür, konu,
mahkeme, esas, dava tarihi. Kuru koşu sayaç yakmaz.
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

**Aynı tıbbi vaka tespiti (G128, 06.09.2026):** ilişki katmanı üç kademe oldu
(`services/case_relations_auto.py`): (1) **kesin, otomatik** — TKU grubu, esas + mahkeme +
tür ikizi ve YENİ **hasar dosya numarası** (`case_foys.hasar_no` + `cases.hasar_dosya_no`,
";" çok değerli, 4+ karakter, "0"/"-" yer tutucu; lokal ölçüm 237 çift / 61'i TKU'suz);
(2) **öneri, onay bekler** — `onerileri_bul`: aynı HASTA (karşı taraf, kişi) + aynı DOKTOR
(müvekkil/sigortalı, kişi) adı; sigorta ve kurum adları doktor SAYILMAZ (AXA üzerinden
4.660 sahte çift ölçüldü), ad karşılaştırması `normalize_party_key` ile tam eşleşme, bulanık
yok; route `suggested` listesinde döner, panelde "Öneri: aynı hasta ve doktor" bölümü,
rozete sayılmaz. "Bağla" mevcut elle bağ ucuna yazar; "Reddet"
(`POST /api/cases/{id}/relations/reject`) `case_relations`a `ONERI_RED` satırı düşer —
panelde görünmez, bir daha önerilmez. (3) **Destekleyici sinyaller (G129, 06.09.2026)** —
`destekleyici_sinyaller`: aynı tıbbi olay (+15; `tibbi_olay` çok değerli, en az bir ortak
değer) ve karşı tarafta ortak aile soyadı (+10; aynı soyadı altında iki karttan birden çok
kişi, tek kişinin kendi soyadı sayılmaz). Öneri üretmez, puanı artırır (taban 50, tavan 75),
öneriler puana göre sıralanır, panelde "puan N" rozeti; gerekçeye "+ aynı tıbbi olay (…)" /
"+ ortak aile soyadı (…)" eklenir. Tarih yakınlığı ve hastada oluşan zarar bilinçli dışarıda
(ölçülmeden puan yok). Testler `backend/tests/test_g128_hasar_ve_oneri.py`,
`frontend/src/components/RelatedCasesPanel.test.tsx`.

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
| `local_decisions` | `LOCAL_DECISIONS` | 27 | `case_stage_decisions.karar_durumu` (YEREL) | G060, 10.08 `DEGER_HAVUZLARI`; G151 (08.09): `Kapalı`/`Derdest` çıktı, `Red/Usulden` girdi |
| `appeal_decisions` | `APPEAL_DECISIONS` | 9 | aynı (ISTINAF) | G060; G151: HMK 353/1-b-2 düzelterek karar ailesi + `Kısmen Kabul` + `Davacı İstinaf Talebinin Kabulü` (`Karar` bilerek yok); 16.09: `Geri Çevirme` (15.09 paketinde 2 föy) |
| `cassation_decisions` | `CASSATION_DECISIONS` | 4 | aynı (TEMYIZ) | G060; G151: `Kısmen Onama/Kısmen Bozma` |
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
tablosu: karar durumu havuzları için `docs/veri-teslim/SOZLESME.md` §6 (10.09, G151 sonrası
27/8/4/2), öteki altı liste için `docs/veri-teslim/BILGILENDIRME_2026-09-03.md` §3.8 (04.09
fotoğrafı; oradaki 28/3/3 sayıları tarihseldir).

## 14. Tarihli dava notları — `case_notes` (G214)

26.09 toplantısı "not alma" kararı: davaya **tarihli, yazanı belli** notlar (zaman çizelgesi).
Tek serbest metin `cases.notes` ("Genel not") AYRI kalır ve dokunulmaz — veri taşınmadı.
Frontend paneli G215.

**Tablo** (`models.CaseNote`, `database.py` madde 53):

| Kolon | Tür | Not |
| --- | --- | --- |
| `id` | SERIAL PK | |
| `case_id` | INTEGER NOT NULL | FK `cases.id` **ON DELETE CASCADE** (dava soft-delete'inde satır durur, uçlar 404) |
| `body` | TEXT NOT NULL | trim'lenmiş, 1..5000 karakter (`schemas.CaseNoteCreate`) |
| `author_email` | VARCHAR(320) NOT NULL | token'dan üçlü claim fallback'i (`preferred_username \| upn \| email`), küçük harf |
| `author_name` | VARCHAR(200) | token'ın `name` claim'i; yoksa NULL |
| `created_at` | TIMESTAMPTZ NOT NULL | server default `now()` |
| `deleted_at` | TIMESTAMPTZ | soft-delete damgası |

Migrasyon `("table", "case_notes", ...)` op'u + index `idx_case_notes_case_created
(case_id, created_at)` AYRI, koşulsuz `("index", ...)` op'unda (create_all tabloyu önce
yarattığında table op'u atlanır; "koşullu op" tuzağı). Index hem listeyi hem FK'yi karşılar.

**Uçlar** (`routes/case_notes.py`, hepsi oturumlu — oturumsuz 401):

| Uç | Sonuç |
| --- | --- |
| `GET /api/cases/{case_id}/notes` | `200 [{id, body, author_name, author_email, created_at, can_delete}]`, en yeni üstte, silinmişler hariç; `created_at` UTC ofsetli ISO8601 |
| `POST /api/cases/{case_id}/notes` `{"body": str}` | `201` + tek not; trim sonrası boş ya da 5000'den uzun → `422` |
| `DELETE /api/cases/{case_id}/notes/{note_id}` | `204` (soft-delete); yazan değil ve yönetici değil → `403`; not bu davada yok / silinmiş → `404` |

Dava `auth_helpers.get_tenant_owned_case`'ten geçmezse (tenant dışı ya da soft-silinmiş) TÜM uçlar
`404`. `can_delete` = istek sahibi yazan ya da yönetici; yönetici kuralı `routes/config.require_admin`'e
sorulur (ADMIN_EMAILS, kopyası tutulmaz). Düzenleme ucu yok. Bekçi: `backend/tests/test_case_notes.py`.

## 15. Avukat envanteri — kimlik geçişinin kabul kapısı (G224)

Kullanıcı şartı (27.09): avukat kimliği geçişinde (kodlar kalkar → kurumsal kimlik, G225-G231) **hiçbir
dava kaybolmamalı**. Ölçüm `backend/services/avukat_envanteri.py` (salt okunur, `belge_envanteri` deseni),
betik `backend/scripts/avukat_envanteri.py`.

- `olc(db)`: avukat listesindeki HER kayıt (pasifler dahil; anahtar `kimlik`, yoksa `code`, kayıt ikisini de
  taşır) için `filtre_dava` (dava listesi filtresinin — `case_manager._lawyer_filter_case_ids`, seçim
  frontend gibi `code || name` — bulduğu AKTİF dava), `sorumlu_kart`, `case_lawyers` (bağlı + adı eşleşen
  bağsız), `case_lawyers_bagli`, `belge` (silinmemiş; `avukat_kodu`, G226 sonrası bağlıysa `lawyer_id`);
  toplamlar + bağsız `case_lawyers` adları.
- **Önbellek tuzağı:** filtre avukatı süreç-içi `DynamicConfig`'ten çözer; betik sürecinde önbellek BOŞTUR ve
  filtre ~0 sayar ("0 → 0 denk" sahte yeşili). `olc` önbelleği ölçtüğü oturumdan uygulamanın biçimiyle
  (aktifler, sıra no) doldurur, bitince eskisine döndürür.
- `karsilastir(once, sonra)`: avukat eşleşmesi kimlik → kod → normalize ad. Avukat başına herhangi bir
  sayımın düşmesi, avukatın bulunamaması ya da korunan bir toplamın (aktif dava, sorumlusu dolu dava,
  `case_lawyers` satırı/bağlı satırı, avukatlı belge) düşmesi **İHLAL**; artışlar, ad/kimlik değişikliği,
  yeni avukat ve bağsız satırların azalması **BİLGİ**.

**Kural — geçişin her veri adımı:** önce fotoğraf → adım → karşılaştır; **İHLAL = adım geri alınır**
(pre-adım dump'ı ya da adımın kendi geri alması), sebep bulunmadan tekrar koşulmaz.

```bash
docker compose exec -T backend python scripts/avukat_envanteri.py --kaydet /tmp/avukat_once.json
# ... veri adımı ...
docker compose exec -T backend python scripts/avukat_envanteri.py --karsilastir /tmp/avukat_once.json  # İHLAL → çıkış 1
```

Dosya yolları KONTEYNER yoludur (`/tmp` recreate'te silinir; adım aynı konteyner ömründe biter). Bekçi:
`backend/tests/test_avukat_envanteri.py`.

## 16. Avukat kaydı — kurumsal kimlik `AVK-00001` + silinmezlik (G225)

Kullanıcı kararı 27.09. **Kimlik:** `lawyers.kimlik` = `AVK-` + 5 hane (`VARCHAR(9)`). Sistem üretir,
kullanıcıya gösterilmez, bir kez verilir, değişmez, yeniden kullanılmaz; sistemler arası kimlik budur,
`lawyers.id` yalnız tablolar arası FK olarak içeride kalır (API'ye taşınması G227/G228).

- **Doldurma (migrasyon madde 54):** kolon op'u koşullu, doldurma + kısıtlar KOŞULSUZ `("index", ...)`
  op'unda: yalnız boş satırlar, `sequence` sonra `id` sırasıyla, mevcut en büyük numaranın üstünden
  (idempotent); `ix_lawyers_kimlik` UNIQUE (modeldeki index ile aynı ad), Postgres'te NOT NULL +
  `ck_lawyers_kimlik_bicim` CHECK `kimlik ~ '^AVK-[0-9]{5}$'`. Numara listenin o ortamdaki sırasından
  doğar — prod ile lokal listesi farklıysa numaralar da farklı olur; prod'da uygulamadan önce iki
  ortamın listesi karşılaştırılır (G231 "Prod sırası").
- **Üretim:** `models.sonraki_avukat_kimligi` = en büyük + 1 (oturumdaki flush edilmemiş yeni kayıtlar
  dahil); pasif kişinin numarası boşluk olarak kalır, doldurulmaz. `reference_lists._avukat_ekle`
  istemciden gelen `kimlik`i yok sayar, eşzamanlı eklemede `ix_lawyers_kimlik` ihlalini yeniden dener
  (yalnız kimlik çakışması; kod çakışması 409). Betikler (`avukat_yazim`, `import_lawyers_excel`) aynı
  fonksiyonu çağırır.
- **Değişmezlik:** `kimlik` hiçbir listenin `editable` alanında değil — PUT `/api/config/lawyers/{kimlik}`
  ve `/api/config/update` gövdesinde gelse **yok sayılır** (422 değil; eski istemciler kırılmasın).
  ORM bekçisi (`models._avukat_kimligi_degismez`, `before_flush`): verilmiş kimliği değiştiren/boşaltan
  flush `ValueError` ile durur.
- **Silinmezlik:** avukat kaydı ASLA silinmez. `DELETE /api/config/lawyers/{kimlik}` (G228; eski kod geriye uyumlu) ve
  `POST /api/config/delete` (`type=lawyers`) kaydı `active=false` yapar:
  `block` (varsayılan) kullanımda da pasife alır — kart adı, `case_lawyers` bağı ve kimlik aynen kalır;
  `reassign` kart alanlarını ve kaynağa BAĞLI `case_lawyers` satırlarını (ad + `lawyer_id`) hedefe taşır,
  kaynak yine pasif olur (hedef pasif/aynı ise 422); `clear` ve `keep` **422** (Türkçe mesaj,
  `LawyerDeleteRejected`). Diğer referans listelerinin silme davranışı DEĞİŞMEDİ.
- **Pasif avukat yeniden eklenirse** (aynı ad anahtarı, `ad_kimligi`) ikinci kayıt doğmaz: pasif kayıt
  kimliği ve koduyla geri açılır. Etkin kişi için mükerrer koruması (409) aynen.
- **Pasif avukat ve filtre (mevcut davranış korunur):** menüler/config listesi (`get_lawyers`) yalnız
  aktifleri verir → pasif avukat listeden SEÇİLEMEZ; adıyla gelen filtre toleranslı ad eşlemesine düşer
  ve eski kartlarını yine bulur.
- **FK:** `case_lawyers.lawyer_id` → `lawyers.id` **ON DELETE RESTRICT** (eski SET NULL bağı sessizce
  koparıyordu). Mevcut kurulumda madde 54 `confdeltype <> 'r'` olan kısıtı düşürüp RESTRICT'li
  `case_lawyers_lawyer_id_fkey`'i ekler (idempotent); ham SQL `DELETE FROM lawyers` bağlı kayıtta
  `ForeignKeyViolation` verir.

Bekçi: `backend/tests/test_g225_avukat_kimligi.py` (SQLite + scratch Postgres `dbtest`).

## 17. Avukat listesi kimlikle yönetilir; kod gizli (G228)

- **Tanımlayıcı:** `reference_lists.LIST_REGISTRY["lawyers"].key = "kimlik"`; kayıtlar (`GET /api/config/lawyers`,
  `DynamicConfig`) `kimlik` alanını taşır. `PUT|DELETE /api/config/lawyers/{kimlik}` ve genel uçlar (`/api/config/update`,
  `delete` + `target_code`, `reorder` `ordered_ids`, `usage` `code`, `rename`) `type=lawyers` için kimlik alır (harf
  duyarsız). Eski `code` değeri 1 sürüm GERİYE UYUMLU (`reference_lists._kayit_bul`; G231'de kalkar). Diğer listeler kod
  anahtarlı, DEĞİŞMEDİ.
- **POST:** gövde `schemas.LawyerConfigItem` — `code` opsiyonel ve YOK SAYILIR; iç kod (`lawyers.code`, NOT NULL UNIQUE)
  sunucuda = kimlik üretilir; yanıt `{"lawyer": {...}}` yeni (ya da yeniden açılan pasif) kaydı döner.
- **Kod eşleşme token'ı değil:** `lawyer_resolver.resolve_lawyer`, `_value_matches` (parametre imza uyumu için durur,
  yok sayılır) ve `notification_targeting._match_person` kodla eşlemez. Ölçüm (lokal, 27.09): kart sorumlu/UYAP
  avukatı, `case_lawyers.name`, `hearing_dates.lawyer_name` alanlarında kod biçimli değer 0.
- **Filtre:** `GET /api/cases?lawyer=<kimlik>` → `case_manager._lawyer_filter_case_ids`: kimlik yalnız avukat KAYDINI bulur
  (önbellekte yoksa — pasif — DB'den adına iner, `_kimligi_ada_cevir`), eşleşme toleranslı AD kurallarıyla koşar;
  yalnız adla yazılmış kartlar sonuçta kalır. Ölçüm (lokal, 27.09): 81/81 avukatta kimlikle filtre = G224 tarzı kodla
  filtre fotoğrafı.
- **Bağ:** `canonicalize_lawyers` `case_lawyers.lawyer_id`'yi kimlik → `lawyers.id` ile kurar (kod araması kalktı).
- **Rapor:** `belgeler.avukat_kodu` katalogdan çıktı; yerine türetilmiş `avukat_adi` ("Avukat", `lawyer_id` → `lawyers.name`,
  filtrelenebilir). Lokal `report_templates`: 1 şablon, 0'ı `avukat_kodu` kullanıyor.

Bekçi: `backend/tests/test_g228_avukat_kimlikle_yonetim.py`.
