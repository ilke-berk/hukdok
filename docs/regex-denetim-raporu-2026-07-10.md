# Regex Sistemi Denetim Raporu ve İyileştirme Planı

**Tarih:** 2026-07-10
**Kapsam:** Backend çıkarıcılar (esas no, tarih, mahkeme, duruşma), eşleştirme motorları, frontend yardımcıları
**Yöntem:** Tüm `re.*` / RegExp kullanımının statik incelemesi + pipeline entegrasyon analizi

> **Uygulama durumu (2026-07-10):** Faz 1 (1.1–1.5) ve Faz 2'nin 2.1/2.2 maddeleri uygulandı.
> Ek olarak court_extractor'da `str.upper()` → `turkish_upper` düzeltmesi yapıldı (karışık
> harfli metinde `MAHKEMESİ` kalıpları hiç eşleşmiyordu; body katmanı kalıpları büyük harfe
> çevrildi çünkü Python `re.IGNORECASE` i↔İ çiftini eşleyemez). Test süiti: 282 yeşil
> (yeni: test_esas_no_extractor 31, test_court_extractor 17; test_date_extractor 14→25).
> Kalan işler: 2.3 golden corpus, 2.4 uyuşmazlık telemetrisi, Faz 3–4.

---

## 1. Yönetici Özeti

Sistem **"regex-önce, LLM-sonra" hibrit** bir mimari kullanıyor ve bu strateji doğru. Regex katmanı yapısal alanları (esas no, tarih, mahkeme, duruşma) LLM'den önce çıkarıyor; bulunamayanlar `missing_fields` olarak Gemini'ye devrediliyor ([analyzer.py:509-569](../backend/analyzer.py#L509-L569)). Bu, maliyeti düşürüyor, determinizm sağlıyor ve LLM halüsinasyonuna karşı çapa görevi görüyor.

Ancak denetimde **3 yüksek öncelikli hata**, **4 orta öncelikli risk** ve önemli bir **test açığı** tespit edildi: `esas_no_extractor` ve `court_extractor` için **hiç test yok** (0 test), buna karşın bu iki alan dava eşleştirmenin (case_matcher) ana sinyalleri.

**Ana mesaj:** Regex'i atmak değil, *sağlamlaştırmak + ölçmek* gerekiyor. Sorun regex stratejisinde değil, tekil kalıplardaki gevşekliklerde ve doğrulama/test eksikliğinde.

---

## 2. Mevcut Mimari Envanteri

### 2.1 Akış

```
PDF → metin çıkarma → [REGEX ÖN-ÇIKARIM] → eksik alan tespiti → dinamik LLM promptu → Gemini → birleştirme → case_matcher
```

| Alan | Modül | Yöntem | Test |
|---|---|---|---|
| Esas No | [esas_no_extractor.py](../backend/extractors/esas_no_extractor.py) | 3 kademeli regex + karar-no filtresi | ❌ **Yok** |
| Belge Tarihi | [date_extractor.py](../backend/extractors/date_extractor.py) | Regex adaylar + puanlama + LLM hakem | ✅ 14 test |
| Mahkeme | [court_extractor.py](../backend/extractors/court_extractor.py) | Header regex → body regex → LLM'e devir | ❌ **Yok** |
| Duruşma tarihi/saati | [analyzer.py:447-506](../backend/analyzer.py#L447-L506) | 6 kalıp + etiket-pencere taraması | ✅ 15 test |
| Müvekkil adayları | FlashText (list_searcher) | Regex değil — doğru tercih | — |
| Dava eşleştirme | [case_matcher.py](../backend/case_matcher.py) | Normalize + kelime kümesi (regex minimal) | ✅ 17 test |
| Belge türü tahmini (FE) | [predictDocType.ts](../frontend/src/lib/predictDocType.ts) | Token + Levenshtein | ✅ var |
| Takip no üretimi (FE) | [caseNumberUtils.ts](../frontend/src/lib/caseNumberUtils.ts) | Slug regex'leri | ✅ var |

### 2.2 İyi yapılmış olanlar

- Kalıplar modül seviyesinde **pre-compiled** (esas, tarih, mahkeme).
- Mahkeme kalıbı **DB'den dinamik** üretiliyor, cache'li, fallback listeli.
- Tarihte **güven skoru + LLM hakem** deseni var (belirsizse LLM'e sor) — örnek alınacak desen.
- Müvekkil taraması için regex yerine **FlashText** seçilmiş (N isim için doğru araç).
- ReDoS riski düşük: iç içe belirsiz niceleyici yok, pencereler sınırlı (`{0,80}` vb.).

---

## 3. Tespit Edilen Hatalar

### 🔴 Y1 — Esas No Kalıp 1'de her şey opsiyonel → çıplak `YYYY/N` "very_high" sayılıyor

[esas_no_extractor.py:12](../backend/extractors/esas_no_extractor.py#L12)

```python
(re.compile(r'(?:ESAS|DOSYA)?(?:NO|NUMARASI|SAYISI)?:?(\d{4}/\d+)', re.IGNORECASE), 'very_high'),
```

Tüm önekler `?` ile opsiyonel olduğundan bu kalıp fiilen **`(\d{4}/\d+)`** demektir: belgede geçen *herhangi bir* `2023/456` deseni, bağlamına bakılmaksızın `very_high` güvenle esas no adayı olur. Sonuçları:

1. **Karar numarası sızması:** Karar-no filtresi yalnız Kalıp 3'e uygulanıyor (`if i == 3`, [satır 58](../backend/extractors/esas_no_extractor.py#L58)). `KARAR NO: 2023/456` metni Kalıp 1 ile `very_high` eşleşir ve filtre atlanır. Karar no belgede esas no'dan önce geçiyorsa (`find_best_esas_no` ilk eşleşmeyi döner) **yanlış esas no** döner → case_matcher +50 puanı yanlış davaya gider.
2. **Mevzuat/genelge referansları:** "2004/85 sayılı genelge" gibi ifadeler yıl filtresinden (1990-2035) geçer.
3. Kalıp 3 (`E[.:]?...`) boşluksuz normalize metinde **E ile biten her kelimeye** takılır: `...GENELGE2022/3` → `E2022/3` → esas no "2022/3" (yanlış pozitif, `high` güven).

**Öneri:** Kalıp 1'de en az bir anahtar kelimeyi zorunlu yap (`(?:ESAS|DOSYA)(?:NO|NUMARASI|SAYISI)?:?` — ilk grup opsiyonel değil); çıplak `\d{4}/\d+` eşleşmesini ayrı bir `low` güven kalıbına indir; karar-no filtresini **tüm** kalıplara uygula; Kalıp 3'e normalize metinde sözcük sınırı taklidi ekle (öncesinde harf olmamalı: `(?<![A-ZÇĞİÖŞÜ])E[.:]`... — normalize sırasında harfler bitişik kaldığından lookbehind çalışır).

### 🔴 Y2 — Ay adı eşleşmesi çift yönlü substring: "5 ay 2020" → 05.05.2020

[date_extractor.py:133](../backend/extractors/date_extractor.py#L133)

```python
if norm_key in m_upper or m_upper in norm_key:
```

`m_upper in norm_key` yönü, ay adının *herhangi bir alt dizesi* olan kelimeyi ay sayar:
- `"AY"` ⊂ `"MAYIS"` → "taksitle 5 ay 2020 ..." → **05.05.2020** üretir.
- `"EK"` ⊂ `"EKİM"` → "bkz. 5 EK 2023" (ek = belge eki!) → **05.10.2023** üretir.
- `"MART"` ⊂ `"MARTI"` gibi ters yön de gürültülü.

**Öneri:** Tam eşleşme + en fazla bilinen kısaltmalar (`OCA`, `ŞUB`, ... ≥3 harf, **prefix** kontrolü: `norm_key.startswith(m_upper) and len(m_upper) >= 3`). Çift yönlü `in` kaldırılmalı.

### 🔴 Y3 — LLM hakemin seçtiği tarih aday listesine karşı doğrulanmıyor

[date_extractor.py:263-277](../backend/extractors/date_extractor.py#L263-L277)

Prompt "sadece listedeki tarihlerden seç" diyor ama kod `data.get("selected_date")` değerini **hiç kontrol etmeden** döndürüyor. LLM listede olmayan bir tarih uydurursa (kural ihlali) sisteme aynen girer. Ayrıca dönen değerin geçerli `YYYY-MM-DD` olduğu da yalnız string-fallback dalında kontrol ediliyor.

**Öneri:** `selected_date`'i ISO regex'ten geçir **ve** adayların ISO karşılıkları kümesinde olduğunu doğrula; değilse en yüksek skorlu adaya düş.

### 🟠 O1 — Tarih bulunamayınca "bugün" uyduruluyor

[date_extractor.py:236-246, 287](../backend/extractors/date_extractor.py#L231-L246)

`find_best_date` hiçbir aday bulamazsa **bugünün tarihini** belge tarihi olarak döndürüyor. Hukuki belgede sessizce üretilmiş bir tarih; dosya adlandırma, sıralama ve UYAP eşlemesinde yanıltıcı. Ayrıca alan hep dolu döndüğü için `_detect_missing_fields` "tarih eksik" diyemiyor → LLM'e "tarihi bul" görevi hiç gitmiyor.

**Öneri:** `None` döndür; `missing_fields`'a düşsün, LLM denesin; o da bulamazsa UI'da boş/uyarılı göster. "Bugün" fallback'i yalnızca en son katmanda ve `tarih_kaynagi: "fallback_today"` bayrağıyla.

### 🟠 O2 — Mahkeme DAIRE_PATTERN'i aşırı gevşek

[court_extractor.py:77-90](../backend/extractors/court_extractor.py#L77-L90)

`{TR_UPPER}+\.?` alternatifi "Roma rakamı" niyetiyle **herhangi bir büyük harfli kelimeyi** numara bölümü sayar; ardından iki opsiyonel sıfat + `DAİRESİ`. Bu, mahkeme adından sonra gelen alakasız 1-3 kelimeyi daire adına yapıştırabilir. Ayrıca aynı daire çıkarımı 3 yerde tekrar yazılmış (`_find_daire_after`, `_format_match` rakam + sözel dalları) — davranışları küçük farklarla ayrışıyor.

**Öneri:** Roma rakamı alternatifini gerçek Roma rakamı sınıfına daralt (`[IVX]+\.?`); daire çıkarımını tek yardımcı fonksiyonda topla.

### 🟠 O3 — `_get_full_pattern` her çağrıda DB/config okuyor

[court_extractor.py:108-157](../backend/extractors/court_extractor.py#L108-L157)

Pattern cache'i var ama cache anahtarını üretmek için her belgede (header + body = 2 çağrı) `DynamicConfig`'ten tüm mahkeme türleri ve iller çekiliyor. Config nadiren değişir.

**Öneri:** TTL'li cache (ör. 60 sn) veya config değişince invalidation sinyali; en azından `find_court_name` başında bir kez çözüp iki katmana parametre geçir.

### 🟠 O4 — Türkçe normalizasyon 5+ kopya halinde

Aynı "Türkçe karakteri sadeleştir / büyüt" mantığı en az beş yerde bağımsız yazılmış ve **birbirinden farklı** davranıyor:

- [text_utils.py](../backend/text_utils.py) `turkish_upper` + `slugify` (İ→I, şapkalılar dahil)
- [case_matcher.py:45](../backend/case_matcher.py#L45) `_normalize` (şapkalı harfleri **kapsamıyor**: "Â" olduğu gibi kalır)
- [caseNumberUtils.ts:48](../frontend/src/lib/caseNumberUtils.ts#L48) `normalizeAscii`
- [predictDocType.ts:21](../frontend/src/lib/predictDocType.ts#L21) `foldTr`
- [analyzer.py:794](../backend/analyzer.py#L794) satır içi ünvan temizliği (client_normalizer'daki `PRE_COMPILED_TITLE_PATTERNS` ile ayrışık)

Ör. `case_matcher._normalize("KÂZIM")` ≠ `slugify("KÂZIM")` → isim eşleşme puanı sessizce kaçar.

**Öneri:** Backend'de tek `turkish_fold()` (text_utils'e), frontend'de tek `foldTr` (lib/turkish.ts) ve tüm çağrıların oraya bağlanması. FE-BE davranış eşitliği için aynı test vektörleri iki tarafta da koşulmalı.

### 🟡 Küçük notlar

- [client_normalizer.py:14-18](../backend/client_normalizer.py#L13-L19): `\bDR\.?` kalıbı "DRAGOMAN" gibi kelimelerin başını yer (`\b` sonrası nokta opsiyonel, kelime devamı kontrolü yok) → `\bDR\.` veya `\bDR\b\.?` + sonrasında boşluk şartı.
- [esas_no_extractor.py:66](../backend/extractors/esas_no_extractor.py#L66): yorum "2010-2030" diyor, kod 1990-2035 — yorumu düzelt.
- Duruşma etiket-pencere taraması ([analyzer.py:489-504](../backend/analyzer.py#L489-L504)) "etikete en yakın" yerine "penceredeki son/ilk" tarihi alıyor; çok tarihli tebligatlarda yanlış seçim riski (testleri var, corpus genişletilince izlenmeli).

---

## 4. Performans Değerlendirmesi

Kısa yanıt: **regex performans sorunu değil.** Kalıplar derlenmiş, ReDoS'a açık yapı yok, belge başına maliyet milisaniye mertebesinde (LLM çağrısının yanında ihmal edilebilir). Yapılabilecekler:

1. **O3'teki config okuma** — belge başına gereksiz DB round-trip; asıl kazanç burada.
2. `esas_no_extractor` tüm metnin boşluksuz kopyasını üretiyor; büyük belgelerde ilk N + son N karakterle sınırlamak yeterli (esas no neredeyse daima başlıkta/ilk sayfada — court_extractor'daki 20 satır yaklaşımının aynısı).
3. `date_extractor` tüm belgeyi tarıyor; aday sayısı patlarsa (uzun kararlarda yüzlerce tarih) skor hesabı O(n) ama LLM hakem promptu zaten top-3 ile sınırlı — sorun yok, sadece aday sayısına üst sınır (ör. 200) eklenebilir.

---

## 5. Strateji: Belge analizinde regex mantıklı mı?

**Evet — ama tek başına değil, şu anki hibrit rolünde.** Değerlendirme:

| Alan | Regex uygun mu? | Gerekçe |
|---|---|---|
| Esas/karar no | ✅ İdeal | Katı biçimli (`YYYY/N`), sonlu varyasyon. Doğru araç. |
| Tarih | ✅ Aday üretimi için ideal | Biçim sonlu; *hangi* tarihin belge tarihi olduğu ise anlamsal → mevcut "regex aday + skor + LLM hakem" deseni tam doğru mimari. |
| Mahkeme adı | ✅ Kapalı sözlükle uygun | İl + tür listesi sonlu ve DB'den geliyor; regex yerine asıl güç sözlükte. |
| Duruşma tarihi | ⚠️ Sınırda | Kalıp çeşitliliği yüksek (tensip, zapt, tebligat zarfı...); regex kaçırdıkça kalıp ekleme sarmalına girilir. LLM'e per-alan devir mekanizması burada en değerli. |
| Müvekkil/taraf adları | ❌ Regex değil | Zaten FlashText + LLM — doğru. |
| Belge türü | ❌ Regex değil | FE'de token/Levenshtein, BE'de LLM — doğru. |

### Alternatifler ve neden (şimdilik) önermiyorum

- **NER modeli (spaCy/BERT tabanlı Türkçe hukuk NER):** Eğitim verisi + model servis yükü + Türkçe hukuk domain'inde olgun hazır model azlığı. Mevcut hacimde maliyet/fayda negatif. İleride duruşma/taraf çıkarımı regex'le doyuma ulaşırsa yeniden değerlendirilebilir.
- **Her şeyi LLM'e vermek:** Zaten LLM var; regex ön-çıkarım LLM'in çapası ve maliyet düşürücüsü. Kaldırmak halüsinasyon riskini artırır, determinizmi öldürür (aynı belge iki analizde farklı esas no verebilir).
- **Asıl eksik strateji parçası — ölçüm:** Regex'in mi LLM'in mi haklı olduğunu bugün bilmiyorsunuz. Regex ve LLM aynı alanda **farklı sonuç ürettiğinde** bunu loglayıp (uyuşmazlık telemetrisi) gerçek belgelerle bir doğruluk tablosu çıkarmak, "regex mi başka şey mi" sorusunu veriyle yanıtlar.

Ek iki somut strateji iyileştirmesi:

1. **Structured output:** `ask_llm_referee` yanıtı ` ```json ` temizleyerek parse ediyor ([date_extractor.py:225](../backend/extractors/date_extractor.py#L225)). Gemini'nin `response_mime_type="application/json"` + `response_schema` desteği kullanılmalı — parse hataları sınıfça yok olur. Aynısı ana analiz çağrısı için de geçerliyse oraya da.
2. **LLM hakem desenini genelleştir:** Tarihte çalışan "belirsizse LLM'e adaylarla sor" deseni, esas no (birden çok aday: ilk derece + istinaf esası) ve mahkeme (header/body çelişkisi) için de uygulanabilir. Uydurma önleme kuralı: LLM yalnız aday listesinden seçer, kod bunu **doğrular** (Y3'ün genel çözümü).

---

## 6. Eylem Planı

### Faz 1 — Hata düzeltmeleri (yüksek öncelik, ~1 gün)

| # | İş | Dosya | Kabul kriteri |
|---|---|---|---|
| 1.1 | Kalıp 1'de anahtar kelimeyi zorunlu yap; çıplak `YYYY/N`'i `low` güvene indir; karar filtresini tüm kalıplara uygula | esas_no_extractor.py | "KARAR NO: 2023/456" esas no dönmez |
| 1.2 | Kalıp 3'e lookbehind ekle (E ile biten kelime yanlış pozitifi) | esas_no_extractor.py | "GENELGE2022/3" eşleşmez |
| 1.3 | Ay eşleşmesini prefix-tabanlı yap (çift yönlü `in` kalksın) | date_extractor.py | "5 ay 2020" tarih üretmez |
| 1.4 | LLM hakem çıktısını aday kümesine karşı doğrula | date_extractor.py | Listede olmayan tarih reddedilir |
| 1.5 | "Bugün" fallback'ini kaldır → `None` + missing_fields akışı | date_extractor.py, analyzer.py | Tarihsiz belgede alan boş kalır, LLM'e devredilir |

### Faz 2 — Test ve ölçüm altyapısı (~1-2 gün)

| # | İş | Kabul kriteri |
|---|---|---|
| 2.1 | `test_esas_no_extractor.py`: gerçek başlık varyasyonları (Esas/E./Dosya No/karar karışık, istinaf çift esas) — **şu an 0 test** | ≥15 parametrik vaka, Faz 1 düzeltmeleri regresyon korumalı |
| 2.2 | `test_court_extractor.py`: header/body katmanları, daire (rakam+sözel), üst mahkemeler — **şu an 0 test** | ≥15 vaka |
| 2.3 | Anonimleştirilmiş **golden corpus** (20-30 gerçek belge metni + beklenen alanlar, `tests/fixtures/`) | Tüm çıkarıcılar corpus üzerinde tek testte koşar; alan bazlı isabet raporu |
| 2.4 | **Uyuşmazlık telemetrisi:** regex sonucu ile LLM sonucu farklıysa `TechnicalLogger`'a alan+iki değer logla | Prod loglarından haftalık doğruluk tablosu çıkarılabilir |

### Faz 3 — Konsolidasyon ve performans (~1 gün)

| # | İş |
|---|---|
| 3.1 | Backend tek `turkish_fold()` (text_utils) — case_matcher, analyzer, client_normalizer oraya bağlanır (şapkalı harf farkı kapanır) |
| 3.2 | Frontend tek `lib/turkish.ts` — caseNumberUtils, predictDocType, nameSimilarity oraya bağlanır; FE-BE ortak test vektörleri |
| 3.3 | Court pattern config okumasına TTL cache; daire çıkarımını tek fonksiyonda birleştir |
| 3.4 | Esas no taramasını ilk/son N karakterle sınırla |

### Faz 4 — Strateji geliştirmeleri (veri geldikçe, ~2 gün)

| # | İş | Ön koşul |
|---|---|---|
| 4.1 | Gemini structured output (`response_schema`) — hakem + ana analiz | — |
| 4.2 | LLM hakem desenini esas no ve mahkemeye genelleştir (aday listesinden seçim + kod doğrulaması) | 2.4 telemetrisi hangi alanın en çok uyuştuğunu/uyuşmadığını göstersin |
| 4.3 | Corpus isabet oranlarına göre skor ağırlıklarını (date_extractor sihirli sayıları) kalibre et | 2.3 |
| 4.4 | NER değerlendirmesi — yalnızca 4.2 sonrası duruşma/taraf alanlarında isabet hâlâ düşükse | Telemetri verisi |

**Sıralama gerekçesi:** Faz 1 düzeltmeleri test olmadan riskli görünebilir ama vakalar net ve dar; Faz 2 testleri aynı PR'da yazılırsa (önerilen: 1 + 2.1/2.2 birlikte) hem düzeltme hem koruma tek seferde gelir. Faz 4 kararları tahminle değil Faz 2.4 telemetri verisiyle verilmeli.

---

## 7. Özet Karar Matrisi

- **Regex stratejisi:** Koru. Yapısal alanlar için doğru araç; LLM ile hibrit kullanım örnek nitelikte.
- **En kritik risk:** Esas no Kalıp 1 gevşekliği (yanlış dava eşleştirmeye kadar gider) + tarihte "bugün" uydurma.
- **En büyük yapısal açık:** esas_no ve court çıkarıcılarında sıfır test; regex-LLM uyuşmazlığının ölçülmemesi.
- **Yatırımın yönü:** Yeni teknoloji değil — kalıp sıkılaştırma, doğrulama katmanı, golden corpus, telemetri.
