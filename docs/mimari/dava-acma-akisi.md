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

`REQUIRED_CASE_FIELDS` (`required_fields.py:13-31`): `esas_no`, `court`, `file_type`,
`judicial_unit`, `sub_type`, `opening_date`, `subject`, `responsible_lawyer_name`,
`uyap_lawyer_name`, `service_type`, `acceptance_date`, `bureau_type`, `atama_tarihi`.

`sub_type_extra` (Uzmanlık / Tıbbi İşlem) listeden **geçici** olarak çıkarılmıştır
(2026-08-04): alan UI'da gizlendiği için görünmeyen alan "eksik" uyarısı üretmesin; alan
geri açılınca satır da geri alınacak (`required_fields.py:19-22`).

Ayrıca `compute_missing_fields` karşı taraf TC'sini denetler ama **yalnız COUNTER**
taraflar için: müvekkil TC'si `Client` kaydında yaşar, form yalnız karşı taraf TC'si
girebilir — aksi halde her yeni dosya yanlış "eksik" işaretlenirdi
(`required_fields.py:33-36`, `:55-58`).

Frontend bu listeyi `GET /api/config/required_case_fields` üzerinden okur; **ikinci bir
liste tutulmaz** (`required_fields.py:8-10`).

## 2. Mükerrer kontrolü

`GET /api/cases/check-duplicate` (`backend/routes/cases.py:173`) esas no (ve isteğe bağlı
mahkeme) ile mevcut davaları arar; form kaydetmeden önce uyarı gösterir.

## 3. Otonom intake sihirbazı

Backend uçları `backend/routes/case_intake.py`'dedir:

| Uç | Satır | İş |
| --- | --- | --- |
| `POST /api/case-intake/expand-eml` | `:208` | `.eml` dosyasını gövde + eklere açar (gövde PDF'e çevrilir) |
| `POST /api/case-intake/analyze` | `:329` | Tek belgeyi analiz eder, NDJSON stream döner, tam PDF'i PROCESS_CACHE'e koyar |
| `POST /api/case-intake/merge` | `:583` | N belgenin çıkarımlarını tek taslakta birleştirir |
| `POST /api/case-intake/commit` | `:998` | Yeni dava kaydı + belge arşivleme + poliçe beslemesi |
| `POST /api/case-intake/apply` | `:1156` | **Zenginleştirme modu**: mevcut davaya kısmi güncelleme |
| `POST /api/case-intake/keepalive` | `:1254` | Review adımında PROCESS_CACHE TTL'sini tazeler |

Sihirbaz akışı: yükle → analiz → (birden çok belge varsa) birleştir → kullanıcı incelemesi
→ commit (ya da mevcut davaya apply).

`keepalive` ucunun varlığı bir tasarım sonucudur: PROCESS_CACHE TTL'si 1800 sn'dir
(`config/settings.py:89`) ve kullanıcı inceleme adımında bundan uzun kalabilir; sihirbaz
periyodik olarak TTL'yi tazeler.

## 4. `/commit` ve 409'un idempotent çözümlenmesi

Commit dava kaydını `DERDEST` durumuyla açar (`case_intake.py:1025`). `add_case`
`duplicate_tracking_no` dönerse akış **nihai 409 vermez**; önce muhafazakâr bir eşleşme
denenir (`case_manager.find_idempotent_commit_match`).

Gerekçe kodda yazılı (`case_intake.py:1029-1033`):

> Faz 3-D (plan 3.5): 409 artık nihai değil — yanıtı kaybolan önceki commit'in KENDİ
> davasına çarpmış olabiliriz (çift tıklama / timeout sonrası tekrar). Muhafazakâr eşleşme
> tutarsa mevcut dava idempotent sonuç olarak döner; eski "sıra numarasını artırıp tekrar
> deneyin" yolu bu senaryoda aynı davayı İKİNCİ kez açtırıyordu.

Eşleşme tutarsa `idempotent_reuse = True` ile mevcut dava döner. Tutmazsa gerçek çakışmadır:
`[TRACKING_NO_COLLISION]` ERROR telemetrisi yazılır ve 409 atılır. Bu telemetrinin
`add_case`'ten buraya taşınması bilinçlidir — sayaç önerisi hâlâ dolu numara üretiyorsa
buradan görülür (`case_intake.py:1046-1053`).

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

`GET /api/cases/client-sequence` (`backend/routes/cases.py:116`) müvekkile/isim bloğuna ait
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

`POST /api/parties/check` (`backend/routes/parties.py:16`) uçtur; mantık `backend/party_check.py`
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
unvan temizliği → boşluk sadeleştirme (`party_check.py:53-68`). NFD adımı şart: bazı
kayıtlarda `i̇` (i + U+0307) gibi görünmez karakterler var; temizlenmezse birebir aynı isim
exact yerine fuzzy'ye düşer ya da hiç eşleşmez (`party_check.py:56-59`).

Kurumsal isimler fuzzy'den muaftır — sigorta şirketleri birbirine benzediği için gürültü
üretirdi; `_CORPORATE_WORDS` normalize edilmiş isimde **kelime olarak** aranır ("HASAN"daki
"AS" gibi substring yanlış pozitiflerini önlemek için) (`party_check.py:41-47`).

**`conflict=True` tek bir koşulda üretilir**: CLIENT olmayan bir sorgu, `contact_type="Client"`
bir cari kaydıyla eşleşirse (karşı taraf ofisin müvekkili → çıkar çatışması riski). Müvekkil
satırı çatışma üretmez; müvekkilin geçmiş dosyalarda karşı taraf olarak görünmesi yalnız
bilgi olarak listelenir. Bu 2026-08-01 kullanıcı kararıdır: "çıkar çatışması yalnız karşı
tarafa bakılır" (`party_check.py:19-25`).

## 8. Belge bağlandığında dava zenginleşmesi

Bir belge `/confirm`'de bir davaya bağlanınca iki yardımcı koşar:

- `_auto_update_case_status(case_id, belge_turu_kodu, uploaded_by)` — `backend/routes/processing.py:152`
- `_auto_enrich_case_data(case_id, avukat_kodu, karsi_taraf, uploaded_by)` — `:205`

İkisi de `/confirm` akışından çağrılır (`processing.py:861`, `:867`) ve hata durumunda
akışı devirmez; oturum kapatma/rollback davranışları test altındadır
(`backend/tests/test_faz0_hardening.py`, `backend/tests/test_faz3_e_hardening.py`).

Aşama geçişleri `case_stage_logs`, alan değişiklikleri `case_history` tablosuna yazılır
(`backend/models.py`); intake zenginleştirmesi kaynağını `intake-enrich: <belge adları>`
imzasıyla bırakır.
