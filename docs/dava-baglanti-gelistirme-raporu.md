# Belge → Dava Bağlama Özelliği — Geliştirme Raporu

**Tarih:** 2026-06-24
**Kapsam:** Yüklenen belgenin bir davaya bağlanması akışı (otomatik eşleştirme + manuel seçim + sonradan bağlama)

---

## 1. Mevcut Akış

1. Kullanıcı belge yükler → analiz (`analyzeDocument`).
2. Backend belgeyi okuyup otomatik dava eşleştirmesi yapar: `find_matching_case` ([case_matcher.py:132](../backend/case_matcher.py#L132)), çağrısı [processing.py:498](../backend/routes/processing.py#L498). Sonuç `suggested_case` (skor + güven `HIGH`/`MEDIUM`/`LOW`).
3. [Index.tsx](../frontend/src/pages/Index.tsx) öneri kutusunu gösterir: "Yapay Zeka Tespiti", belgedeki isimlerin eşleşme rozetleri, **"Evet, Bu Davaya Bağla"** butonu ([Index.tsx:1255](../frontend/src/pages/Index.tsx#L1255)).
4. Kullanıcı farklı dava ararsa arama kutusu (artık tüm davalarda arıyor — son düzeltme).
5. `/confirm` ile `linked_case_id` gönderilir → belge `link_mode` ile kaydedilir: `LINKED` / `TEST` / `UNLINKED` ([processing.py:127](../backend/routes/processing.py#L127), [1023](../backend/routes/processing.py#L1023)).

### Skorlama motoru ([case_matcher.py](../backend/case_matcher.py))
| Sinyal | Puan |
|--------|------|
| Esas no tam eşleşme (sıfır-dolgu toleranslı) | +50 |
| Mahkeme tam eşleşme | +50 |
| Mahkeme şehir + tür eşleşmesi | +25 |
| İsim tam eşleşme (her biri) | +30 |
| İsim kısmi eşleşme (her biri) | +15 |

Eşikler: `HIGH ≥ 90`, `MEDIUM ≥ 45`, `LOW < 45`; `min_score = 40` altındaki adaylar elenir.

---

## 2. Tespit Edilen Sorunlar ve Eksikler

### 🔴 Yüksek Etki

**G1 — Bağlantısız (UNLINKED) belgeler yetim kalıyor.**
Bir belge dava seçilmeden (ve test modu da değilken) yüklenirse `link_mode = "UNLINKED"` olarak kaydediliyor ([processing.py:131](../backend/routes/processing.py#L131)). Backend'de bunu sonradan bağlamak için endpoint **hazır**: `PATCH /api/documents/{id}/link` ([documents.py:190](../backend/routes/documents.py#L190)). Ancak:
- Frontend bu endpoint'i **hiç çağırmıyor** (grep: 0 sonuç).
- `UNLINKED` belgeleri listeleyen **hiçbir ekran yok**.

➡️ Sonuç: davaya bağlanmamış belge kaybolur; bulup bağlamanın yolu yok. **En kritik eksik.** Çözüm: "Bağlantısız Belgeler" kutusu/sayfası + mevcut `/link` endpoint'iyle tek tık bağlama.

**G2 — Eşleştirme her belgede tüm davaları tarıyor (O(N), Python tarafında).**
`find_matching_case` veritabanındaki **tüm** davaları (`active == True`) belleğe çekip ([case_matcher.py:161](../backend/case_matcher.py#L161)) Python'da tek tek skorluyor. Veri büyüdükçe her belge analizinde lineer maliyet. [database.py](../backend/database.py) diff'inde eklenen `pg_trgm` arama index'lerinden **faydalanmıyor** (DB ön-filtreleme yok).

➡️ Ölçeklenmez. Çözüm: DB seviyesinde aday ön-filtreleme (esas_no / şehir-mahkeme / taraf adı trgm), sonra dar kümede Python skorlama.

### 🟡 Orta Etki

**G3 — Alternatif adaylar üretiliyor ama gösterilmiyor.**
Matcher en iyi adayın yanında `all_candidates` (2.–5. adaylar) döndürüyor ([case_matcher.py:297](../backend/case_matcher.py#L297)), ama UI yalnızca "best"i gösteriyor. Kullanıcı 2. en iyi adayı seçmek için sıfırdan elle arama yapmak zorunda.
➡️ Öneri kutusuna "Diğer olası davalar" listesi ekle (tek tık seçim).

**G4 — Karşı taraf isimleri müvekkil gibi puanlanıyor (yanlış pozitif riski).**
Skorlama, belgedeki isimleri davanın **tüm** taraflarıyla karşılaştırıyor; `party_type` ayrımı yok ([case_matcher.py:213](../backend/case_matcher.py#L213)). Yani bir COUNTER (karşı taraf) eşleşmesi de müvekkil gibi +30 alıyor. "AXA Sigorta", bir banka vb. çok sayıda davada karşı taraf olduğundan yanlış eşleşme üretebilir.
➡️ Müvekkil (CLIENT) eşleşmesine yüksek, karşı taraf eşleşmesine düşük ağırlık ver.

**G5 — HIGH güvende bile her zaman manuel onay.**
Esas no + mahkeme tam eşleştiğinde (≥90, neredeyse kesin) dahi kullanıcı "Evet, Bu Davaya Bağla" tıklamak zorunda. Opsiyonel otomatik bağlama yok.
➡️ Ayarla açılabilen "HIGH güvende otomatik bağla" seçeneği (geri alınabilir şekilde).

### 🟢 Düşük Etki

**G6 — Şehir tespiti kırılgan.** `_court_similarity` şehri "ilk kelime" sayıyor ([case_matcher.py:113](../backend/case_matcher.py#L113)); "İstanbul Anadolu", "İstanbul Bakırköy" gibi çift kelimeli adliyelerde yanlış sonuç verir.

**G7 — Eşikler sabit kodlu, öğrenme yok.** Yanlış eşleşme için kullanıcı geri bildirimi toplanmıyor; eşikler ayarlanamıyor.

**G8 — Toplu yüklemede tek tek onay.** Toplu akışta her belge için `suggested_case` var ama bağlama onayı tek tek. HIGH güvenli olanlar için toplu/otomatik bağlama yok (yeni toplu yükleme tezgâhıyla sinerji mümkün).

---

## 3. Önerilen Yol Haritası

### Aşama 1 — Görünür Kazanımlar
- **G1:** "Bağlantısız Belgeler" görünümü + mevcut `/api/documents/{id}/link` ile tek tık bağlama. *(Endpoint hazır, sadece UI gerekiyor.)*
- **G3:** Öneri kutusunda alternatif adayları (`all_candidates`) göster.

### Aşama 2 — Eşleştirme Kalitesi
- **G4:** Skorlamada `party_type` ayrımı (karşı taraf yanlış pozitiflerini azalt).
- **G5:** HIGH güvende opsiyonel otomatik bağlama.

### Aşama 3 — Ölçeklenebilirlik & İnce Ayar
- **G2:** Eşleştirmeyi DB ön-filtreleme ile optimize et (trgm index'lerini kullan).
- **G6:** Çift kelimeli şehir / adliye adı ayrıştırmasını iyileştir.
- **G8:** Toplu yüklemede HIGH güvenli belgeleri toplu bağla.

---

## 4. Özet

En acil eksik **G1**: backend endpoint'i hazır olmasına rağmen bağlantısız belgeleri sonradan bağlamanın UI yolu yok — yüklenen belgeler yetim kalabiliyor. Hemen ardından eşleştirme doğruluğunu artıran düzeltmeler (**G3, G4**) gelir; **G2** ise veri büyüdükçe performans için kritikleşecek. Aşama 1 görece küçük bir işle en gözle görülür faydayı sağlar.
