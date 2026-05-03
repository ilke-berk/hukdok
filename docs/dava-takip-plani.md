# Dava Durumu Takip Özelliği — İmplementasyon Planı

**Tarih:** 2026-04-15  
**Durum:** Planlama  
**Faz:** 1 (Manuel Takip) + Faz 2 (Otomatik — sonra eklenecek)

---

## Genel Bakış

Her davanın kendi takip paneli olacak. `CaseDetails` sayfasında yeni bir **"Takip"** tab'ı açılacak. Her davanın takibi birbirinden bağımsız tutulacak.

### Mimari Yaklaşım

İki katmanlı yapı:

1. **`Case` tablosuna** kritik tarih/karar alanları eklenir — hızlı sorgu ve listeleme için
2. **`CaseStageLog` yeni tablosu** — aşama değişikliklerinin tarihçesi için (kim, ne zaman, hangi kaynaktan)

---

## Faz 1 — Manuel Takip

### 1. Backend — Model Değişiklikleri

#### `models.py` — `Case` tablosuna yeni kolonlar

**Yerel Mahkeme Karar Bilgileri**

| Kolon | Tip | Açıklama |
|---|---|---|
| `case_stage` | String | Mevcut aşama: `DERDEST`, `KARAR`, `ISTINAF`, `TEMYIZ`, `KARAR_DUZELTME`, `KESINLESME`, `INFAZ`, `KAPALI` |
| `karar_tarihi` | Date | Yerel mahkeme karar tarihi |
| `karar_no` | String | Yerel mahkeme karar no (örn. 2023/139) |
| `karar_turu` | String | `KABUL`, `RED`, `KISMI_KABUL`, `FERAGAT`, `UZLASMA`, `DUSME` |
| `karar_lehine` | String | `LEHINE`, `ALEYHINE`, `KISMI` |
| `karar_teblig_tarihi` | Date | Kararın tebliğ edildiği tarih |
| `karar_aciklama` | Text | Karar açıklama metni |
| `kesinlesme_tarihi` | Date | Kararın kesinleşme tarihi |

**İstinaf Bilgileri**

| Kolon | Tip | Açıklama |
|---|---|---|
| `istinaf_basvuru_tarihi` | Date | İstinaf başvuru tarihi |
| `istinaf_mahkemesi` | String | İstinaf mahkemesi adı |
| `istinaf_esas_no` | String | İstinaf esas no |
| `istinaf_karar_no` | String | İstinaf karar no |
| `istinaf_karar_tarihi` | Date | İstinaf karar tarihi |
| `istinaf_karar_durumu` | String | İstinaf karar durumu (dropdown) |
| `istinaf_karar_aciklama` | Text | İstinaf karar açıklaması |
| `istinaf_teblig_tarihi` | Date | İstinaf kararının tebliğ tarihi |

**Temyiz Bilgileri**

| Kolon | Tip | Açıklama |
|---|---|---|
| `temyiz_basvuru_tarihi` | Date | Temyiz başvuru tarihi |
| `temyiz_mahkemesi` | String | Temyiz mahkemesi adı |
| `temyiz_esas_no` | String | Temyiz esas no |
| `temyiz_karar_no` | String | Temyiz karar no |
| `temyiz_karar_tarihi` | Date | Temyiz karar tarihi |
| `temyiz_karar_durumu` | String | Temyizde dosya karar durumu (dropdown) |
| `temyiz_eden_durumu` | String | Temyiz eden tarafın durumu (dropdown) |
| `temyiz_karar_aciklama` | Text | Temyiz karar açıklaması |
| `temyiz_teblig_tarihi` | Date | Temyiz kararının tebliğ tarihi |

**Karar Düzeltme Bilgileri**

| Kolon | Tip | Açıklama |
|---|---|---|
| `karar_duzeltme_durumu` | String | Karar düzeltme durumu (dropdown) |
| `karar_duzeltme_esas_no` | String | Karar düzeltme esas no |
| `karar_duzeltme_karar_no` | String | Karar düzeltme karar no |
| `karar_duzeltme_tarihi` | Date | Karar düzeltme karar tarihi |
| `karar_duzeltme_teblig_tarihi` | Date | K. Düzeltme tebliğ tarihi |
| `karar_duzeltme_aciklama` | Text | Karar düzeltme açıklaması |
| `yeni_esas_no` | String | Karar düzeltme sonrası yeni esas no / mahkemesi |

**İnfaz**

| Kolon | Tip | Açıklama |
|---|---|---|
| `infaz_tarihi` | Date | İnfaz / icra başlangıç tarihi |

#### `models.py` — Yeni `CaseStageLog` tablosu

```
CaseStageLog
  id            Integer PK
  case_id       Integer FK → cases.id
  stage         String        # Geçilen aşama
  changed_at    DateTime
  changed_by    String        # Kullanıcı adı
  source        String        # "MANUAL" | "AUTO_DOCUMENT"
  note          String        # Opsiyonel açıklama
```

---

### 2. Backend — Schema Değişiklikleri

#### `schemas.py` — Yeni şemalar

**`CaseTrackingUpdate`** (tüm alanlar opsiyonel):
```python
# Genel
case_stage

# Yerel Mahkeme Karar
karar_tarihi, karar_no, karar_turu, karar_lehine,
karar_teblig_tarihi, karar_aciklama, kesinlesme_tarihi

# İstinaf
istinaf_basvuru_tarihi, istinaf_mahkemesi, istinaf_esas_no,
istinaf_karar_no, istinaf_karar_tarihi, istinaf_karar_durumu,
istinaf_karar_aciklama, istinaf_teblig_tarihi

# Temyiz
temyiz_basvuru_tarihi, temyiz_mahkemesi, temyiz_esas_no,
temyiz_karar_no, temyiz_karar_tarihi, temyiz_karar_durumu,
temyiz_eden_durumu, temyiz_karar_aciklama, temyiz_teblig_tarihi

# Karar Düzeltme
karar_duzeltme_durumu, karar_duzeltme_esas_no, karar_duzeltme_karar_no,
karar_duzeltme_tarihi, karar_duzeltme_teblig_tarihi,
karar_duzeltme_aciklama, yeni_esas_no

# İnfaz
infaz_tarihi

# Log notu
note
```

**`CaseStageLogRead`**:
```python
id, case_id, stage, changed_at, changed_by, source, note
```

**`CaseRead`** güncellenir — yeni takip alanları eklenir.

---

### 3. Backend — Manager Değişiklikleri

#### `managers/admin_manager.py` — Yeni fonksiyonlar

**`update_case_tracking(case_id, data, changed_by, source="MANUAL")`**
- `cases` tablosunu günceller
- `case_stage` değişmişse `CaseStageLog`'a yeni kayıt ekler
- Mevcut `CaseHistory` pattern'ı ile tutarlı çalışır

**`get_case_stage_log(case_id)`**
- Davanın tüm aşama tarihçesini döner

---

### 4. Backend — Route Değişiklikleri

#### `routes/cases.py` — Yeni endpoint'ler

```
PATCH /api/cases/{case_id}/tracking
  → Takip bilgilerini güncelle (aşama + tarihler + karar bilgileri)
  → Body: CaseTrackingUpdate
  → Auth: get_current_user

GET /api/cases/{case_id}/stage-log
  → Aşama tarihçesini getir
  → Response: List[CaseStageLogRead]
```

---

### 5. Database Migration

**Proje Alembic kullanmıyor.** Migration `database.py` içindeki `check_and_migrate_tables()` fonksiyonuna eklenir. Uygulama her başladığında bu fonksiyon çalışır, kolonun var olup olmadığını kontrol eder, yoksa otomatik ekler. Mevcut veriler sıfırlanmaz, elle SQL çalıştırmak gerekmez.

#### `database.py` — `check_and_migrate_tables()` fonksiyonuna eklenecek bloklar

**Blok 7 — `cases` tablosuna takip kolonları:**
```python
# 7. CASES TRACKING MIGRATION
if "cases" in inspector.get_table_names():
    columns = [col['name'] for col in inspector.get_columns("cases")]
    tracking_columns = {
        # Genel
        "case_stage":                    "VARCHAR(50)",
        # Yerel Mahkeme Karar
        "karar_tarihi":                  "DATE",
        "karar_no":                      "VARCHAR(50)",
        "karar_turu":                    "VARCHAR(50)",
        "karar_lehine":                  "VARCHAR(20)",
        "karar_teblig_tarihi":           "DATE",
        "karar_aciklama":                "TEXT",
        "kesinlesme_tarihi":             "DATE",
        # İstinaf
        "istinaf_basvuru_tarihi":        "DATE",
        "istinaf_mahkemesi":             "VARCHAR(200)",
        "istinaf_esas_no":               "VARCHAR(50)",
        "istinaf_karar_no":              "VARCHAR(50)",
        "istinaf_karar_tarihi":          "DATE",
        "istinaf_karar_durumu":          "VARCHAR(100)",
        "istinaf_karar_aciklama":        "TEXT",
        "istinaf_teblig_tarihi":         "DATE",
        # Temyiz
        "temyiz_basvuru_tarihi":         "DATE",
        "temyiz_mahkemesi":              "VARCHAR(200)",
        "temyiz_esas_no":                "VARCHAR(50)",
        "temyiz_karar_no":               "VARCHAR(50)",
        "temyiz_karar_tarihi":           "DATE",
        "temyiz_karar_durumu":           "VARCHAR(100)",
        "temyiz_eden_durumu":            "VARCHAR(100)",
        "temyiz_karar_aciklama":         "TEXT",
        "temyiz_teblig_tarihi":          "DATE",
        # Karar Düzeltme
        "karar_duzeltme_durumu":         "VARCHAR(100)",
        "karar_duzeltme_esas_no":        "VARCHAR(50)",
        "karar_duzeltme_karar_no":       "VARCHAR(50)",
        "karar_duzeltme_tarihi":         "DATE",
        "karar_duzeltme_teblig_tarihi":  "DATE",
        "karar_duzeltme_aciklama":       "TEXT",
        "yeni_esas_no":                  "VARCHAR(100)",
        # İnfaz
        "infaz_tarihi":                  "DATE",
    }
    for col_name, col_type in tracking_columns.items():
        if col_name not in columns:
            try:
                conn.execute(text(f'ALTER TABLE cases ADD COLUMN {col_name} {col_type}'))
                conn.commit()
                logger.info(f"Added {col_name} to cases")
            except Exception as e:
                logger.error(f"Migration error for cases.{col_name}: {e}")
```

**Blok 8 — `case_stage_logs` yeni tablosu:**
```python
# 8. CASE_STAGE_LOGS TABLE
if "case_stage_logs" not in inspector.get_table_names():
    try:
        conn.execute(text("""
            CREATE TABLE case_stage_logs (
                id SERIAL PRIMARY KEY,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                stage VARCHAR(50) NOT NULL,
                changed_at TIMESTAMPTZ DEFAULT NOW(),
                changed_by VARCHAR(100),
                source VARCHAR(20) DEFAULT 'MANUAL',
                note TEXT
            )
        """))
        conn.execute(text("CREATE INDEX idx_stage_logs_case ON case_stage_logs(case_id)"))
        conn.commit()
        logger.info("Created case_stage_logs table")
    except Exception as e:
        logger.error(f"Migration error for case_stage_logs: {e}")
```

**Akış:**
```
backend restart
    └── init_db()
        └── Base.metadata.create_all()   ← yeni CaseStageLog modeli tabloyu oluşturur (ilk kez)
        └── check_and_migrate_tables()   ← cases tablosuna yeni kolonları ekler
```

---

### 6. Frontend — Hook Değişiklikleri

#### `hooks/useCases.ts` — Yeni fonksiyonlar

```typescript
updateCaseTracking(caseId: number, data: CaseTrackingUpdate): Promise<boolean>
getCaseStageLog(caseId: number): Promise<CaseStageLogEntry[]>
```

---

### 7. Frontend — Yeni Bileşen

#### `components/CaseTrackingPanel.tsx` (yeni dosya)

**Alt bölümler:**

**a) Aşama Timeline**
- Davanın geçtiği aşamalar soldan sağa ilerleme çubuğu
- `DERDEST → KARAR → İSTİNAF → TEMYİZ → KESİNLEŞME → İNFAZ → KAPALI`
- Tamamlanmış = renkli, aktif = parlak, gelecek = gri

**b) Önemli Tarihler**
- Grid kartları: Dava Açılış, Karar, Karar Tebliğ, Kesinleşme, İstinaf Başvuru, İstinaf Karar, İstinaf Tebliğ, Temyiz Başvuru, Temyiz Karar, Temyiz Tebliğ, K. Düzeltme, İnfaz
- Her kart tarih varsa renkli, yoksa `—` gösterir

**c) Karar Bilgileri** (sadece KARAR+ aşamasında görünür)
- Karar türü badge (KABUL=yeşil, RED=kırmızı, KISMI=sarı, FERAGAT=turuncu, vs.)
- Lehine/Aleyhine badge
- Karar no + karar açıklama metni

**c2) İstinaf / Temyiz / Karar Düzeltme detay bölümleri**
- Her aşama için ayrı kart: mahkeme, esas no, karar no, durum, açıklama
- Sadece ilgili aşamaya gelindiğinde görünür hale gelir

**d) Düzenleme Formu**
- "Takibi Güncelle" butonu → modal veya inline form
- Tüm takip alanları düzenlenebilir
- Kaydet → `PATCH /api/cases/{id}/tracking`

**e) Aşama Tarihçesi**
- `CaseStageLog` verisini kronolojik liste olarak gösterir
- Her girişde: aşama, tarih, kullanıcı, kaynak (MANUAL/AUTO_DOCUMENT)

---

### 8. Frontend — CaseDetails Değişikliği

#### `pages/CaseDetails.tsx`

- Mevcut tab'ların yanına yeni **"Takip"** tab'ı eklenir
- `CaseTrackingPanel` bu tab'ın içine yerleştirilir
- `CaseDetailsData` interface'ine yeni takip alanları eklenir

---

### Uygulama Sırası

- [ ] 1. `models.py` — yeni kolonlar + `CaseStageLog` modeli
- [ ] 2. `database.py` — `check_and_migrate_tables()` içine Blok 7 ve Blok 8 eklenir
- [ ] 3. `schemas.py` — yeni şemalar (`CaseTrackingUpdate`, `CaseStageLogRead`, `CaseRead` güncelleme)
- [ ] 4. `managers/admin_manager.py` — `update_case_tracking()` ve `get_case_stage_log()` fonksiyonları
- [ ] 5. `routes/cases.py` — yeni endpoint'ler (`PATCH /tracking`, `GET /stage-log`)
- [ ] 6. `hooks/useCases.ts` — yeni hook fonksiyonları
- [ ] 7. `components/CaseTrackingPanel.tsx` — yeni bileşen
- [ ] 8. `pages/CaseDetails.tsx` — tab entegrasyonu

---

## Faz 2 — Otomatik Takip (Sonra Eklenecek)

### Konsept

Belirli belge türleri yüklendiğinde, belge AI tarafından okunur ve dava takibi otomatik güncellenir.

### Tetikleyici Belge Türleri (Örnekler)

| `belge_turu_kodu` | Tetiklenen Güncelleme |
|---|---|
| `KARAR-BLG` | `karar_tarihi`, `karar_no`, `karar_turu`, `karar_lehine`, `karar_aciklama`, `case_stage=KARAR` |
| `KARAR-TEBLIG` | `karar_teblig_tarihi` |
| `ISTINAF-BLG` | `istinaf_basvuru_tarihi`, `istinaf_mahkemesi`, `case_stage=ISTINAF` |
| `ISTINAF-KARAR` | `istinaf_karar_no`, `istinaf_karar_tarihi`, `istinaf_karar_durumu`, `istinaf_karar_aciklama` |
| `TEMYIZ-BLG` | `temyiz_basvuru_tarihi`, `temyiz_mahkemesi`, `case_stage=TEMYIZ` |
| `TEMYIZ-KARAR` | `temyiz_karar_no`, `temyiz_karar_tarihi`, `temyiz_karar_durumu`, `temyiz_karar_aciklama` |
| `KARAR-DUZELTME` | `karar_duzeltme_*` alanları, `case_stage=KARAR_DUZELTME` |
| `KESINLESME-BLG` | `kesinlesme_tarihi`, `case_stage=KESINLESME` |

### Mimari Entegrasyon

Faz 1'deki `update_case_tracking()` fonksiyonu `source` parametresi alacak şekilde tasarlandı:

```python
# Faz 2'de belge analizi sonrası çağrılacak
update_case_tracking(
    case_id=case_id,
    data={
        "karar_tarihi": extracted_date,
        "karar_turu": extracted_result,
        "case_stage": "KARAR"
    },
    changed_by=user,
    source="AUTO_DOCUMENT"   # CaseStageLog'da görünür
)
```

Mevcut `CaseDocument.belge_turu_kodu` alanı tetikleyici olarak kullanılacak.  
Otomatik güncellemeler `CaseStageLog`'da `source="AUTO_DOCUMENT"` ile işaretlenir → kullanıcı hangi güncellemelerin otomatik yapıldığını görebilir.

---

## Açık Sorular

- [ ] Karar türleri tam listesi onaylanacak (KABUL, RED, KISMI_KABUL, FERAGAT, UZLASMA, DUSME — başka var mı?)
- [ ] İstinaf/Temyiz sonuçları: sabit enum mi, serbest metin mi?
- [ ] Mevcut `status` alanı (DERDEST, DANIŞ, MAHZEN) ile yeni `case_stage` ilişkisi netleştirilecek
