# Dava Takip — Delta İmplementasyon Planı

**Tarih:** 2026-04-15
**Durum:** Kısmen Tamamlandı — Devam Ediliyor
**Baz Plan:** `dava-takip-plani.md`

---

## Mevcut Durum

### ✅ Tamamlanan İşler (Faz 1.1 + 1.2)

**Backend:**
- `models.py` — `CaseStageLog` modeli + `Case`'e ilk set takip kolonları
- `database.py` — Migration Blok 7 (ilk set kolonlar) + Blok 8 (`case_stage_logs` tablosu)
- `schemas.py` — `CaseTrackingUpdate`, `CaseStageLogRead`, `CaseRead` güncellendi
- `managers/admin_manager.py` — `update_case_tracking()`, `get_case_stage_log()`
- `routes/cases.py` — `PATCH /api/cases/{id}/tracking`, `GET /api/cases/{id}/stage-log`

**Frontend:**
- `hooks/useCases.ts` — `updateCaseTracking()`, `getCaseStageLog()` + tipler
- `components/CaseTrackingPanel.tsx` — Yeni bileşen (timeline, tarih grid, karar badge, form, log)
- `pages/CaseDetails.tsx` — Takip tab'ı entegre edildi

**DB'de mevcut kolonlar:**
```
case_stage, karar_tarihi, karar_turu, karar_lehine,
istinaf_tarihi, istinaf_sonucu, istinaf_karar_tarihi,
temyiz_tarihi, temyiz_sonucu, temyiz_karar_tarihi,
kesinlesme_tarihi, infaz_tarihi
```

---

## Yapılması Gerekenler

### Faz 1.3 — Backend Genişletme

#### Adım 1 — `models.py`

**A) 4 kolon yeniden adlandırılacak:**

| Eski Ad (DB'de var) | Yeni Ad |
|---|---|
| `istinaf_tarihi` | `istinaf_basvuru_tarihi` |
| `istinaf_sonucu` | `istinaf_karar_durumu` |
| `temyiz_tarihi` | `temyiz_basvuru_tarihi` |
| `temyiz_sonucu` | `temyiz_karar_durumu` |

**B) Yeni kolonlar eklenecek:**

| Grup | Kolon | Tip |
|---|---|---|
| Yerel Karar | `karar_no` | VARCHAR(50) |
| Yerel Karar | `karar_teblig_tarihi` | DATE |
| Yerel Karar | `karar_aciklama` | TEXT |
| İstinaf | `istinaf_mahkemesi` | VARCHAR(200) |
| İstinaf | `istinaf_esas_no` | VARCHAR(50) |
| İstinaf | `istinaf_karar_no` | VARCHAR(50) |
| İstinaf | `istinaf_karar_aciklama` | TEXT |
| İstinaf | `istinaf_teblig_tarihi` | DATE |
| Temyiz | `temyiz_mahkemesi` | VARCHAR(200) |
| Temyiz | `temyiz_esas_no` | VARCHAR(50) |
| Temyiz | `temyiz_karar_no` | VARCHAR(50) |
| Temyiz | `temyiz_eden_durumu` | VARCHAR(100) |
| Temyiz | `temyiz_karar_aciklama` | TEXT |
| Temyiz | `temyiz_teblig_tarihi` | DATE |
| Karar Düzeltme | `karar_duzeltme_durumu` | VARCHAR(100) |
| Karar Düzeltme | `karar_duzeltme_esas_no` | VARCHAR(50) |
| Karar Düzeltme | `karar_duzeltme_karar_no` | VARCHAR(50) |
| Karar Düzeltme | `karar_duzeltme_tarihi` | DATE |
| Karar Düzeltme | `karar_duzeltme_teblig_tarihi` | DATE |
| Karar Düzeltme | `karar_duzeltme_aciklama` | TEXT |
| Karar Düzeltme | `yeni_esas_no` | VARCHAR(100) |

**C) `case_stage` yeni değer:** `KARAR_DUZELTME` (7 → 8 aşama)

Timeline sırası:
```
DERDEST → KARAR → ISTINAF → TEMYIZ → KARAR_DUZELTME → KESINLESME → INFAZ → KAPALI
```

---

#### Adım 2 — `database.py` — `check_and_migrate_tables()`

**Blok 7'ye rename migration eklenir (PostgreSQL destekler):**
```python
# Rename eski kolonlar
rename_map = {
    "istinaf_tarihi":  "istinaf_basvuru_tarihi",
    "istinaf_sonucu":  "istinaf_karar_durumu",
    "temyiz_tarihi":   "temyiz_basvuru_tarihi",
    "temyiz_sonucu":   "temyiz_karar_durumu",
}
for old_name, new_name in rename_map.items():
    if old_name in columns and new_name not in columns:
        conn.execute(text(f'ALTER TABLE cases RENAME COLUMN {old_name} TO {new_name}'))
        conn.commit()
```

**Blok 7 genişletilir — yeni kolonlar dict'e eklenir.**

---

#### Adım 3 — `schemas.py`

`CaseTrackingUpdate` ve `CaseRead` şemalarına tüm yeni alanlar eklenir.
Rename edilen 4 eski alan kaldırılır, yeni adları eklenir.

---

#### Adım 4 — `admin_manager.py`

`update_case_tracking()` içindeki `tracking_fields` listesi yeni alan adlarıyla güncellenir.
Rename sonrası eski adlar kaldırılır.

---

### Faz 1.4 — Frontend Genişletme

#### Adım 5 — `hooks/useCases.ts`

`CaseTrackingUpdate` interface'i yeni alanlarla güncellenir.
Rename edilen 4 alan güncellenir.

---

#### Adım 6 — `components/CaseTrackingPanel.tsx`

**a) Timeline:** `KARAR_DUZELTME` aşaması eklenir (8. aşama olarak)

**b) Tarih kartları genişler (8 → 12+):**
- Eklenenler: Karar Tebliğ, İstinaf Tebliğ, Temyiz Tebliğ, K.Düzeltme Tarihi, K.Düzeltme Tebliğ

**c) Karar bilgileri bölümü:** `karar_no` ve `karar_aciklama` eklenir

**d) Detay kartları — her aşamaya özel (sadece ilgili aşama aktifken görünür):**

- **İstinaf kartı:** mahkeme, esas no, karar no, karar durumu, açıklama
- **Temyiz kartı:** mahkeme, esas no, karar no, karar durumu, temyiz eden durumu, açıklama
- **Karar Düzeltme kartı:** durum, esas no, karar no, tarih, tebliğ tarihi, açıklama, yeni esas no

**e) Düzenleme formu:** Tüm yeni alanlar bölümlere ayrılmış şekilde eklenir

---

## Uygulama Sırası (Özet)

```
[x] 1. models.py        — rename + 21 yeni kolon + KARAR_DUZELTME stage
[x] 2. database.py      — Blok 7: rename migration + yeni kolonlar
[x] 3. schemas.py       — CaseTrackingUpdate + CaseRead güncelle
[x] 4. admin_manager.py — tracking_fields listesi güncelle
[x] 5. useCases.ts      — CaseTrackingUpdate interface güncelle
[x] 6. CaseTrackingPanel.tsx — timeline + tarih grid + detay kartlar + form
```

---

## Notlar

- Rename işlemi PostgreSQL `ALTER TABLE RENAME COLUMN` ile yapılır — mevcut veri korunur
- `update_case_tracking()` fonksiyonu `source` parametresi alıyor; Faz 2 için hazır
- Tüm yeni string alanlar `nullable=True` — mevcut davalar etkilenmez
