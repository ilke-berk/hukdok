# Belge Analizi → Dava Otomatik Senkronizasyonu — Yol Haritası

**Tarih:** 2026-05-10
**Durum:** Planlama
**Bağlı Plan:** `dava-takip-plani.md` (Faz 2 — AUTO_DOCUMENT)
**Önkoşul:** `dava-takip-delta-plani.md` (tamamlandı — Case takip alanları + CaseStageLog mevcut)

---

## 1. Problem Tanımı

### Mevcut akış (kısaca)

```
PDF yüklendi
   ↓ analyzer.py
AI çıkarımı (esas_no, court, muvekkiller, tarih, özet)
   ↓ case_matcher.py
Eşleşen dava bulundu (suggested_case)
   ↓ /confirm
Kullanıcı onayladı → CaseDocument kaydı oluşur
   ↓ _auto_update_case_status   → sadece status alanı (DERDEST/KARAR/...)
   ↓ _auto_enrich_case_data     → sadece BOŞ alanları (avukat, karşı taraf) doldurur
```

### Ne çalışmıyor

1. **DB her zaman baskın geliyor.** Belge sisteme bağlandıktan sonra, davadan dönen veriler (eski avukat, eski esas no, eski mahkeme) belge analizinden gelen yeni bilgileri **eziyor**. Sonuç: belge-içi taze bilgi sisteme yansımıyor.

2. **`Case`'in yeni takip kolonları (Faz 1) hiç beslenmiyor.** `karar_tarihi`, `karar_no`, `karar_turu`, `karar_lehine`, `istinaf_basvuru_tarihi`, `temyiz_karar_durumu`, `kesinlesme_tarihi`, `yeni_esas_no` vb. ~30 alan boş duruyor. Manuel `CaseTrackingPanel`'den girmek zorunda kalıyoruz.

3. **`case_stage` hiç değişmiyor.** Belge `KARAR-BLG`, `ISTINAF-KARAR`, `TEMYIZ-KARAR` olduğunda davanın aşaması otomatik ilerlemeli. Şu an sadece `status` (eski 3-değerli alan) güncelleniyor.

4. **Esas no / mahkeme değiştiğinde tarihçe tutulmuyor.** Bir karar düzeltme sonrası dava yeni bir esas no'ya geçtiğinde, **eski esas no kaybolmamalı** — `CaseHistory`'ye yazılmalı, yenisi `Case.esas_no`'ya geçmeli, eski numara `yeni_esas_no` ya da history üzerinden geriye doğru görüntülenebilmeli.

5. **Aşamalı geri-dönüş kontrolü yok.** Bir KARAR çıkmış davaya bir DAVA-DLK belgesi gelirse, aşama yanlışlıkla DERDEST'e düşmemeli.

### Neden `_auto_enrich_case_data` yetmez

Mevcut fonksiyon sadece **null/boş alanları** dolduruyor. Bizim ihtiyacımız **delta kıyaslaması** — yani:
- DB'de değer var, belgedeki farklı → kullanıcıdan onay al, eskiyi `CaseHistory`'ye yaz, yenisini ata
- DB'de değer var, belgedeki aynı → bir şey yapma
- DB'de değer yok, belgede var → otomatik doldur (mevcut davranış)

---

## 2. Hedef Akış

```
PDF yüklendi
   ↓ analyzer.py
AI çıkarımı (TEMEL + BELGE TÜRÜNE ÖZEL alanlar)
   ↓ case_matcher.py
Eşleşen dava bulundu (suggested_case + güven skoru)
   ↓ delta_calculator.py (YENİ)
Belge ↔ DB karşılaştırması → ChangeSet
   {
     "auto_apply":   [...]   # boştu → dolduruldu, ya da yüksek güven
     "needs_review": [...]   # değişiklik var, kullanıcı onayı gerekir
     "ignored":      [...]   # aynı veya AI güveni düşük
   }
   ↓ /confirm (UI'da değişiklik onay paneli)
Kullanıcı onaylar → applier
   ↓ apply_document_changes (YENİ)
   • Case alanlarını günceller
   • Her değişiklik için CaseHistory satırı
   • case_stage değiştiyse CaseStageLog (source="AUTO_DOCUMENT", doc_id ile)
   • Eski esas_no değiştiyse Case.esas_no güncellenir + eski değer history'de kalır
   ↓ CaseDocument kaydı oluşur (mevcut akış)
```

---

## 3. Mimari Bileşenler

### 3.1 `extracted_fields` — Belge türüne özel AI çıkarımı

**`prompts.py`** içinde `belge_turu_kodu`'na göre `task_items`'a eklenecek yeni bloklar. AI sadece istenen alanları döner; kalanı `null` bırakır.

| `belge_turu_kodu` (prefix) | AI'nin çıkarması beklenen ek alanlar |
|---|---|
| `KARAR-BLG`, `KARAR` | `karar_no`, `karar_tarihi` (zaten var), `karar_turu` (KABUL/RED/KISMI_KABUL/FERAGAT/UZLASMA/DUSME), `karar_lehine` (LEHINE/ALEYHINE/KISMI), `karar_aciklama` (1-2 cümle) |
| `KARAR-TEBLIG` | `karar_teblig_tarihi` |
| `ISTINAF-DLK`, `ISTINAF-BLG` | `istinaf_basvuru_tarihi`, `istinaf_mahkemesi` |
| `ISTINAF-KARAR` | `istinaf_karar_no`, `istinaf_karar_tarihi`, `istinaf_karar_durumu`, `istinaf_karar_aciklama` |
| `ISTINAF-TEBLIG` | `istinaf_teblig_tarihi` |
| `TEMYIZ-DLK`, `TEMYIZ-BLG` | `temyiz_basvuru_tarihi`, `temyiz_mahkemesi`, `temyiz_eden_durumu` |
| `TEMYIZ-KARAR` | `temyiz_karar_no`, `temyiz_karar_tarihi`, `temyiz_karar_durumu`, `temyiz_karar_aciklama` |
| `TEMYIZ-TEBLIG` | `temyiz_teblig_tarihi` |
| `KARAR-DUZELTME-*` | `karar_duzeltme_esas_no`, `karar_duzeltme_karar_no`, `karar_duzeltme_tarihi`, `karar_duzeltme_durumu`, `karar_duzeltme_aciklama`, `yeni_esas_no` |
| `KESINLESME-BLG` | `kesinlesme_tarihi` |
| `INFAZ`, `ICRA-EMRI` | `infaz_tarihi` |
| `DAVA-DLK` | yok (sadece eşleştirme + esas_no) |

**Not:** Her ek alan için AI'a örnek formatlar verilecek (ör. `karar_turu`'nun değer setini kısıtlı liste olarak vereceğiz, hallüsinasyon önlemi).

**Çıktı şeması (JSON)** — yeni `extracted_tracking` bloğu:
```json
{
  "tarih": "...",
  "esas_no": "...",
  "court": "...",
  "muvekkiller": [...],
  "extracted_tracking": {
    "karar_no": "...",
    "karar_turu": "...",
    "karar_lehine": "...",
    "karar_aciklama": "...",
    "istinaf_basvuru_tarihi": "...",
    "...": "..."
  },
  "_extraction_confidence": {
    "karar_no": "HIGH | MEDIUM | LOW"
  }
}
```

`_extraction_confidence` AI'dan değil, post-processing'de regex doğrulama / tip kontrolü ile üretilir (örn. tarih ISO formatına uyuyor mu, karar_turu sabit listeden mi).

---

### 3.2 `delta_calculator.py` — YENİ dosya

Belge çıktısı + Case mevcut hali → `ChangeSet` üretir.

**Sözleşme:**
```
calculate_changes(
    case: Case,                    # SQLAlchemy nesnesi (snapshot)
    extracted_tracking: dict,      # AI'dan gelen ek alanlar
    extracted_core: dict,          # esas_no, court (bunlar mevcut Case alanları)
    doc_belge_turu: str,
    match_confidence: str,         # CaseMatcher'dan: HIGH/MEDIUM/LOW
) -> ChangeSet
```

**ChangeSet yapısı:**
```python
@dataclass
class FieldChange:
    field: str                     # "karar_no"
    old_value: Any
    new_value: Any
    action: str                    # "AUTO_FILL" | "OVERWRITE" | "IGNORE" | "NEEDS_REVIEW"
    reason: str                    # Kullanıcıya gösterilecek açıklama
    confidence: str                # AI çıkarım güveni

@dataclass
class StageTransition:
    from_stage: str
    to_stage: str
    allowed: bool                  # Geri dönüşler engelli
    reason: str

@dataclass
class ChangeSet:
    case_id: int
    auto_apply: List[FieldChange]
    needs_review: List[FieldChange]
    ignored: List[FieldChange]
    stage_transition: Optional[StageTransition]
```

**Karar matrisi:**

| DB değeri | Belge değeri | AI güveni | Match güveni | Aksiyon |
|---|---|---|---|---|
| boş | dolu | HIGH/MED | HIGH/MED | `AUTO_FILL` |
| boş | dolu | LOW | herhangi | `NEEDS_REVIEW` |
| dolu | boş | — | — | `IGNORE` (DB korunur) |
| dolu | aynı | — | — | `IGNORE` |
| dolu | farklı | HIGH | HIGH | `OVERWRITE` (history'ye yaz) |
| dolu | farklı | HIGH | MEDIUM | `NEEDS_REVIEW` |
| dolu | farklı | MED/LOW | herhangi | `NEEDS_REVIEW` |

**Stage transition kuralları (`_compute_stage_transition`):**

Aşama sırası:
```
DERDEST(0) → KARAR(1) → ISTINAF(2) → TEMYIZ(3) → KARAR_DUZELTME(4) → KESINLESME(5) → INFAZ(6) → KAPALI(7)
```

- `belge_turu_kodu` → hedef aşama mapping (`DOCTYPE_TO_STAGE_MAP` — yeni sabit)
- `to_stage_index >= current_stage_index` → izin
- `to_stage_index < current_stage_index` → engelle (eski belge geç eklenmiş olabilir), `NEEDS_REVIEW` olarak kullanıcıya sor
- Aynı aşama → no-op

**`yeni_esas_no` özel davranışı:**
- Karar düzeltme sonrası `yeni_esas_no` doluysa, hem `Case.yeni_esas_no` hem `Case.esas_no` güncellenir
- Eski `esas_no` `CaseHistory`'ye yazılır (`field_name="esas_no_pre_duzeltme"`)
- `case_stage` → `KARAR_DUZELTME`

---

### 3.3 `apply_document_changes` — YENİ fonksiyon (`admin_manager.py`)

**Sözleşme:**
```
apply_document_changes(
    case_id: int,
    changeset: ChangeSet,
    approved_review_fields: List[str],   # Kullanıcının onayladığı NEEDS_REVIEW alan adları
    changed_by: str,
    document_id: int,                    # CaseDocument.id (audit için)
    tenant_id: str = None,
) -> dict
```

**İşleyiş:**
1. Tek bir DB transaction içinde:
2. `auto_apply` listesi → tümü uygulanır
3. `needs_review` listesi → sadece `approved_review_fields`'da olanlar uygulanır
4. Her uygulanan alan için `CaseHistory(case_id, field_name, old_value, new_value, changed_at, source="AUTO_DOCUMENT")` satırı
5. `stage_transition.allowed` ise `Case.case_stage` güncellenir + `CaseStageLog(stage, source="AUTO_DOCUMENT", note=f"Belge: {doc.original_filename}")` satırı
6. `CaseHistory`'ye yeni bir kolon eklenir: `source_document_id` (FK → case_documents.id, nullable). Böylece "bu değişikliğin kaynağı hangi belge?" sorusu cevaplanır.
7. Commit, dönen `dict` içinde uygulanan/atlanan alanlar listesi.

**Migration ihtiyacı:** `case_history.source_document_id` kolonu ekle (`database.py` Blok 9).

---

### 3.4 Mevcut `update_case_tracking` ile ilişki

Yeni `apply_document_changes` farklı bir API:
- `update_case_tracking` — manuel form girdisini direkt yazıyor (kullanıcı zaten kararını vermiş)
- `apply_document_changes` — delta + onay tabanlı, audit trail tutuyor

Ortak yardımcılar (örn. tracking_fields listesi) `tracking_constants.py`'a taşınır, iki fonksiyon da oradan okur.

`_auto_update_case_status` ve `_auto_enrich_case_data` **silinmez ama içerikleri yeni mantığa devredilir** — geriye dönük uyumluluk için fonksiyonlar kalır, içleri `apply_document_changes` çağrısına döner. Çünkü `routes/processing.py` confirm akışında halen referans var.

---

### 3.5 `routes/processing.py` — `/process` ve `/confirm` değişiklikleri

**`/process` endpoint:**
- `analyze_file_generator` → `extracted_tracking` ve `_extraction_confidence` döner
- `find_matching_case` → `suggested_case` (mevcut)
- **YENİ:** Eğer `suggested_case` varsa, `delta_calculator.calculate_changes()` çağrılır
- Response'a `suggested_changes: ChangeSet` eklenir
- Frontend bu listeyi onay paneli olarak gösterir

**`/confirm` endpoint:**
- Yeni form alanı: `approved_review_fields_json: str = Form(None)` — kullanıcının onayladığı `NEEDS_REVIEW` alan adları
- `linked_case_id` doluysa ve `is_test_mode=False` ise:
  - Mevcut `_auto_update_case_status` → silinir
  - Mevcut `_auto_enrich_case_data` → tutulur (BOŞ avukat/karşı taraf hâlâ doldurulsun)
  - **YENİ:** `apply_document_changes(case_id, changeset, approved_review_fields, ...)` çağrılır
- Sonuç `results["auto_changes"]` ile dönülür: `{applied: [...], skipped: [...], stage_change: {...}}`

---

### 3.6 Frontend — Onay paneli (`DocumentReviewPanel`)

**Konum:** `pages/DocumentReview.tsx` (mevcut belge onay sayfası) içinde yeni bir bölüm.

**Yeni bileşen:** `components/SuggestedChangesPanel.tsx`

**Görünüm:**

```
┌─ Bu davada güncellenecekler ──────────────────────┐
│                                                   │
│ ✓ Otomatik uygulanacak (3)                        │
│   • Karar No: — → 2024/567                        │
│   • Karar Tarihi: — → 2024-03-15                  │
│   • Aşama: DERDEST → KARAR                        │
│                                                   │
│ ⚠ Onayınız gerekiyor (2)                          │
│   ☐ Esas No: 2024/123 → 2024/567                  │
│       (Karar düzeltme sonrası yeni numara)        │
│   ☐ Mahkeme: Ankara 5. Hukuk → Ankara BAM 3.HD    │
│                                                   │
│ ⊘ Atlandı (1)                                     │
│   • Karar Türü: KABUL (mevcut değerle aynı)       │
│                                                   │
│         [ Onayla ve Kaydet ]  [ Tümünü Atla ]    │
└───────────────────────────────────────────────────┘
```

**Davranış:**
- `auto_apply` alanları default olarak görünür ama tıklanamaz (zaten uygulanacak)
- `needs_review` checkbox'lı, default checked
- Kullanıcı onayladıklarının field name listesi `/confirm` POST'una gider

---

### 3.7 `CaseHistory` zenginleştirmesi

**Migration (Blok 9 — `database.py`):**
```python
if "case_history" in inspector.get_table_names():
    columns = [col['name'] for col in inspector.get_columns("case_history")]
    if "source" not in columns:
        conn.execute(text("ALTER TABLE case_history ADD COLUMN source VARCHAR(20) DEFAULT 'MANUAL'"))
    if "source_document_id" not in columns:
        conn.execute(text("ALTER TABLE case_history ADD COLUMN source_document_id INTEGER REFERENCES case_documents(id) ON DELETE SET NULL"))
    if "changed_by" not in columns:
        conn.execute(text("ALTER TABLE case_history ADD COLUMN changed_by VARCHAR(100)"))
    conn.commit()
```

**`models.py` — `CaseHistory` güncellenir:**
```python
source = Column(String(20), default="MANUAL")            # MANUAL | AUTO_DOCUMENT
source_document_id = Column(Integer, ForeignKey("case_documents.id", ondelete="SET NULL"), nullable=True)
changed_by = Column(String(100), nullable=True)
```

Böylece `CaseDetails` sayfasında "Tarihçe" bölümünde her değişiklik yanında: kim, hangi belge, manuel mi otomatik mi gösterilebilir.

---

## 4. Adım Adım Uygulama Sırası

### Faz A — Backend altyapı

- [ ] **A1.** `models.py` — `CaseHistory`'ye 3 yeni kolon (`source`, `source_document_id`, `changed_by`)
- [ ] **A2.** `database.py` — Blok 9 migration (case_history kolon eklemeleri)
- [ ] **A3.** `tracking_constants.py` (yeni) — `TRACKING_FIELDS`, `DOCTYPE_TO_TRACKING_FIELDS`, `DOCTYPE_TO_STAGE_MAP`, `STAGE_ORDER`
- [ ] **A4.** `delta_calculator.py` (yeni) — `calculate_changes()`, `_compute_stage_transition()`, `ChangeSet`/`FieldChange` dataclass'ları
- [ ] **A5.** Birim testler — `tests/test_delta_calculator.py` (10+ senaryo: boş→dolu, çakışma, geri dönüş, esas_no değişimi)

### Faz B — AI çıkarım genişletme

- [ ] **B1.** `prompts.py` — `belge_turu_kodu`'na göre `extracted_tracking` blok mantığı
- [ ] **B2.** `analyzer.py` — `extracted_tracking` post-processing (tip doğrulama, `_extraction_confidence` üretimi)
- [ ] **B3.** Belge örnekleri ile manuel doğrulama (her belge türü için en az 3 örnek üzerinde gözden geçirme)

### Faz C — Backend entegrasyon

- [ ] **C1.** `admin_manager.py` — `apply_document_changes()` fonksiyonu
- [ ] **C2.** `routes/processing.py /process` — `suggested_changes` üretimi ve response'a ekleme
- [ ] **C3.** `routes/processing.py /confirm` — `approved_review_fields_json` alımı, `apply_document_changes()` çağrısı, eski `_auto_update_case_status` kaldırılır
- [ ] **C4.** `_auto_enrich_case_data` — sadece avukat/karşı taraf gibi `Case` ana alanları için kalır; tracking alanları yeni akıştan
- [ ] **C5.** Entegrasyon testi — bir KARAR-BLG yüklenip case_stage geçişinin gerçekleşmesi, history kayıtlarının doğruluğu

### Faz D — Frontend

- [ ] **D1.** `hooks/useDocuments.ts` — `suggested_changes` tipi
- [ ] **D2.** `components/SuggestedChangesPanel.tsx` (yeni)
- [ ] **D3.** `pages/DocumentReview.tsx` — paneli `linked_case_id` olduğunda göster
- [ ] **D4.** `/confirm` çağrısına `approved_review_fields` ekleme
- [ ] **D5.** `CaseDetails > Tarihçe` tab'ı — `source`, `source_document_id` görünür hale getir (belge linkiyle)

### Faz E — Geri besleme & İzleme

- [ ] **E1.** `CaseStageLog` ve `CaseHistory` üzerinden bir "otomatik güncellemeler" raporu (admin sayfası)
- [ ] **E2.** Kullanıcının "AI yanlış güncelledi" geri çevirme (rollback) butonu — `CaseHistory` üzerinden tek değişiklik geri alınır
- [ ] **E3.** Metrik: kaç belgenin kaç alan otomatik güncellediği, kaç tanesi NEEDS_REVIEW'da kullanıcı tarafından reddedildi

---

## 5. Risk ve Karar Noktaları

### 5.1 Yanlış dava eşleşmesi → yanlış güncelleme

**Risk:** `case_matcher` MEDIUM güvenle yanlış davayı önerirse, otomatik OVERWRITE veriyi bozabilir.

**Çözüm:**
- `match_confidence == "MEDIUM"` ise: hiçbir alan `AUTO_FILL` değil, hepsi `NEEDS_REVIEW`
- `match_confidence == "LOW"` ise: zaten dava bağlanmıyor

### 5.2 AI hallüsinasyonu

**Risk:** AI olmayan bir karar tarihi uydurabilir (özellikle eski OCR'lı taramalar).

**Çözüm:**
- `_extraction_confidence` alanı: tarih regex'e uyuyor mu, enum değerleri sabit listeden mi
- LOW olanlar her halükarda `NEEDS_REVIEW`'a düşer
- Belge türüyle alan tutarlılığı: `DAVA-DLK`'dan `karar_turu` çıkarıldıysa şüpheli — atılır

### 5.3 Eski belgenin geç yüklenmesi → aşamayı geri çekme

**Risk:** KARAR aşamasındaki davaya eski bir DAVA-DLK yüklenirse `case_stage` DERDEST'e dönmemeli.

**Çözüm:** `STAGE_ORDER` indeksiyle kıyaslama, geri dönüş engellenir (`needs_review`'a düşer ve "geri dönüş" gerekçesi gösterilir).

### 5.4 Esas no değişikliği — gerçekten değişti mi yoksa OCR hatası mı?

**Risk:** `2024/123` belgede `2024/728` okundu — OCR yanlış olabilir, gerçek bir değişiklik de olabilir.

**Çözüm:**
- Esas no farkı her zaman `NEEDS_REVIEW` (HIGH/HIGH bile olsa) — kritik alan
- Karar düzeltme belgesi (`KARAR-DUZELTME-*`) ise farklı şablon: `yeni_esas_no` alanı kullanılır, eski numara da Case'de kalır

### 5.5 Çoklu belge eş zamanlı işlemesi

**Risk:** İki kullanıcı aynı davaya farklı belgeler yüklerse, race condition.

**Çözüm:** `apply_document_changes` SELECT FOR UPDATE ile satır kilidi alır, uygulamadan sonra commit eder. Mevcut `update_case_tracking` zaten tek transaction.

### 5.6 Geri alma mekanizması

**Risk:** Otomatik güncelleme yanlışsa kullanıcı manuel geri almak zorunda — zahmetli.

**Çözüm:** Faz E2 — `CaseHistory.source_document_id` üzerinden "bu belgeden kaynaklanan tüm değişiklikleri geri al" tek tıkla.

---

## 6. Kapsam Dışı (Bu plana dahil değil)

- Belge silindiğinde otomatik rollback (manuel rollback yeterli)
- Birden fazla aday davaya aynı anda güncelleme (her belge tek davaya bağlanır)
- LLM tabanlı "akıllı çelişki çözümü" (deterministik delta yeterli)
- E-posta ile değişiklik bildirimi (mevcut günlük rapor mekanizması üzerinden ileride)

---

## 7. Açık Sorular

- [ ] `karar_turu`, `karar_lehine` enum değerlerinin AI'a verilen listesi `dava-takip-plani.md` ile aynı mı, frontend dropdown'larıyla senkron mu?
- [ ] `KARAR-DUZELTME` sonrası `yeni_esas_no` set edildiğinde, davanın `tracking_no` (sistem dosya no) değişmeli mi, yoksa sabit mi kalmalı? — **Öneri:** sabit kalır, `esas_no` değişir, `yeni_esas_no` history rolü oynar.
- [ ] `_auto_update_case_status` tamamen kaldırılırsa, eski `status` alanı (DERDEST/DANIŞ/MAHZEN) artık `case_stage`'den mi türetilsin yoksa bağımsız mı kalsın?
- [ ] `NEEDS_REVIEW` alanları kullanıcı tarafından reddedildiğinde (uncheck), yine de `CaseHistory`'ye "önerildi-reddedildi" satırı yazılsın mı? (audit/öğrenme için faydalı olabilir)

---

## 8. Tahmini Çaba

| Faz | Karmaşıklık | Tahmini süre |
|---|---|---|
| A — Altyapı | Orta | 1-2 gün |
| B — AI çıkarım | Yüksek (her belge türünü test) | 2-3 gün |
| C — Backend entegrasyon | Orta | 1-2 gün |
| D — Frontend | Orta | 1-2 gün |
| E — İzleme | Düşük | 1 gün |
| **Toplam** | | **6-10 gün** |

İlk shippable parça: Faz A + B + C minimum (D olmadan, sadece HIGH güven otomatik uygulansın, MEDIUM olanlar şimdilik atlasın). Faz D ile kullanıcı kontrol kazansın.
