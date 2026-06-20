# IDOR İncelemesi — HukuDok

**İnceleme tarihi:** 2026-05-10
**Kapsam:** Multi-tenant erişim kontrolleri; cross-tenant Insecure Direct Object Reference (IDOR) bulguları
**Branch:** `main`

> Bu rapor `docs/guvenlik-incelemesi-2026-05-10.md` belgesinin §3, §4, §12, §14 maddelerinin detaylı incelemesidir. Ana incelemede "tek tenant modeli" varsayımıyla düşük öncelik verilen bulgular, **iki tenantın aktif olduğu doğrulandığı için** kritik seviyeye yükseltilmiştir.

---

## 0. Mevcut tenant modeli (önemli context)

| Öğe | Değer |
|---|---|
| Whitelist'teki tenantlar (`ALLOWED_TENANTS`) | `44f029f8-…fad02`, `9776cf1f-…61de` |
| `cases` tablosunda kayıt | 14.341 |
| `cases.tenant_id IS NULL` olan | **14.341 (hepsi)** |
| `clients` tablosunda kayıt | 1.996 |
| `clients` tablosundaki `tenant_id` sütunu | **YOK** |
| Helper | [`_apply_tenant_filter`](../backend/managers/admin_manager.py#L348) — `tenant_id == X OR tenant_id IS NULL` |

**Yorum:** Veritabanındaki tüm mevcut veri `tenant_id IS NULL` durumunda olduğu için iki tenant **şu anda aynı havuzu paylaşıyor.** Mevcut kod tabanında "NULL = paylaşılan/legacy, yeni kayıtlar tenant'a damgalanır" şeklinde bir konvansiyon var. Bu raporda önerilen tüm düzeltmeler bu semantiği koruyacak şekilde tasarlanmıştır.

### "Sıfır kesinti" prensibi

Her IDOR fix önerisi şu üç testten geçmelidir:

1. **Mevcut 14k case + 2k client kaydı her iki tenant tarafından erişilebilir kalır** (NULL = paylaşılan).
2. **Yeni oluşturulan kayıtlar otomatik olarak yaratıcının `tenant_id`'sine damgalanır** — başka tenanta sızmaz.
3. **Cross-tenant erişim girişimi (Tenant A kullanıcısı → Tenant B'ye damgalı kayıt) 404 ile reddedilir.**

Bu üç madde aşağıda her bulguda "✓ Geriye dönük uyum" kontrol listesi altında ayrıca işaretlenmiştir.

---

## Kritik (CRITICAL)

### IDOR-1. `Client` modelinde `tenant_id` sütunu yok — tüm müvekkil endpoint'leri paylaşımlı

**Dosya:** [backend/models.py:184-220](../backend/models.py#L184-L220), [backend/routes/clients.py](../backend/routes/clients.py)

```python
class Client(Base):
    __tablename__ = "clients"
    # ... 30+ sütun, AMA tenant_id YOK
```

```python
# routes/clients.py — hiçbir endpoint'te tenant filtresi yok:
@router.get("/api/clients")           # Tüm tenantların müvekkillerini döner
@router.put("/api/clients/{client_id}")     # Tenant doğrulamasız update
@router.delete("/api/clients/{client_id}")  # Tenant doğrulamasız delete
```

**Risk:** Tenant A'nın bir kullanıcısı Tenant B'nin müvekkillerini listeleyebilir, düzenleyebilir veya silebilir. KVKK kapsamında ad-soyad, TC, telefon, e-posta, vekaletname numarası dahil tüm PII sızar.

**Düzeltme planı:**

1. **Schema migration**: `clients` tablosuna nullable `tenant_id String, index` ekle.
   ```python
   tenant_id = Column(String, index=True, nullable=True)
   ```
   Migration sonrası **mevcut 1.996 müvekkilin tenant_id'si NULL kalır → her iki tenant görmeye devam eder.**

2. `dependencies.py`'a yeni helper ekle:
   ```python
   from sqlalchemy import or_
   def tenant_filter_clause(model_with_tenant_id, tenant_id: str):
       return or_(model_with_tenant_id.tenant_id == tenant_id,
                  model_with_tenant_id.tenant_id.is_(None))
   ```

3. `routes/clients.py`'ı `get_current_tenant`'a geçir:
   ```python
   @router.get("/api/clients")
   def get_clients_api(tenant_id: str = Depends(get_current_tenant)):
       q = (db.query(models.Client)
              .filter(tenant_filter_clause(models.Client, tenant_id))
              .filter(models.Client.active == True)
              .order_by(models.Client.name.asc()))
       return q.all()

   @router.post("/api/clients")
   def api_add_client(client: ClientCreate,
                      tenant_id: str = Depends(get_current_tenant)):
       data = client.model_dump()
       data["tenant_id"] = tenant_id    # ← yeni kayıtlar damgalanır
       success = add_client(data)

   # update / delete: önce tenant ownership doğrula, sonra işlem
   @router.put("/api/clients/{client_id}")
   def api_update_client(client_id: int, ...,
                         tenant_id: str = Depends(get_current_tenant)):
       client = (db.query(models.Client)
                   .filter(models.Client.id == client_id,
                           tenant_filter_clause(models.Client, tenant_id))
                   .first())
       if not client:
           raise HTTPException(status_code=404, detail="Client not found")
       # ... mevcut update kodu
   ```

**✓ Geriye dönük uyum:**
- Mevcut 1.996 müvekkil `tenant_id=NULL` → iki tenant da listeler. ✓
- Yeni `POST /api/clients` çağrısı kullanıcının tenant'ını damgalar. ✓
- Tenant A'nın kullanıcısı, Tenant B'nin (gelecekte oluşturduğu) müvekkilini ne görebilir ne update/delete edebilir. ✓

**Test senaryoları:** Bölüm "Test planı" → T1, T2.

---

### IDOR-2. `/api/cases/client-sequence` tüm tenantları sayıyor

**Dosya:** [backend/routes/cases.py:60-85](../backend/routes/cases.py#L60-L85)

```python
@router.get("/api/cases/client-sequence")
def get_client_case_sequence(client_name: str, tenant_id: str = Depends(get_current_tenant)):
    # ...
    count = (
        db.query(func.count(func.distinct(models.CaseParty.case_id)))
        .filter(models.CaseParty.party_type == "CLIENT")
        .filter(models.CaseParty.name.ilike(query_pattern))
        .scalar()  # ← tenant_id parametresi alınıyor ama kullanılmıyor!
    )
    return {"sequence": (count or 0) + 1}
```

**Risk:** Tenant A, "AYŞE YILMAZ" adında müvekkil yaratırken sequence numarası alıyor; eğer Tenant B'de aynı isimde müvekkil varsa numara onu da sayıyor → bilgi sızıntısı (Tenant B'de kaç tane "AYŞE YILMAZ" davası var). KVKK ve iş gizliliği ihlali.

**Düzeltme:**
```python
count = (
    db.query(func.count(func.distinct(models.CaseParty.case_id)))
    .join(models.Case, models.CaseParty.case_id == models.Case.id)
    .filter(models.CaseParty.party_type == "CLIENT")
    .filter(models.CaseParty.name.ilike(query_pattern))
    .filter(or_(models.Case.tenant_id == tenant_id,
                models.Case.tenant_id.is_(None)))
    .scalar()
)
```

**✓ Geriye dönük uyum:**
- Mevcut 14k NULL-tenant case'leri her iki tenant da kendi sayımına dahil eder. ✓
- Tenant A, Tenant B'nin yeni damgalanmış davalarını sayımına almaz. ✓

---

### IDOR-3. `/api/hearing-dates/{hearing_id}` DELETE — tenant doğrulaması yok

**Dosya:** [backend/routes/cases.py:375-389](../backend/routes/cases.py#L375-L389)

```python
@router.delete("/api/hearing-dates/{hearing_id}")
def delete_hearing_date(hearing_id: int, tenant_id: str = Depends(get_current_tenant)):
    db = SessionLocal()
    try:
        row = db.query(models.HearingDate).filter(models.HearingDate.id == hearing_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Duruşma tarihi bulunamadı")
        db.delete(row)        # ← Hangi davaya ait olduğu hiç sorgulanmadan silinir
```

**Risk:** Tenant A'nın kullanıcısı, Tenant B'ye ait bir davanın duruşma tarihini sayısal ID enumerationıyla silebilir → adli kayıp.

**Düzeltme:**
```python
row = (db.query(models.HearingDate)
         .join(models.Case, models.HearingDate.case_id == models.Case.id)
         .filter(models.HearingDate.id == hearing_id,
                 or_(models.Case.tenant_id == tenant_id,
                     models.Case.tenant_id.is_(None)))
         .first())
if not row:
    raise HTTPException(status_code=404, detail="Duruşma tarihi bulunamadı")
```

**✓ Geriye dönük uyum:** NULL-tenant case'lere bağlı duruşmalar her iki tenant tarafından silinebilir kalır. ✓

---

### IDOR-4. `/api/cases/{case_id}/relations/{relation_id}` DELETE — tenant doğrulamasız

**Dosya:** [backend/routes/cases.py:245-270](../backend/routes/cases.py#L245-L270)

```python
relation = db.query(models.CaseRelation).filter(
    models.CaseRelation.id == relation_id,
    ((models.CaseRelation.source_case_id == case_id) |
     (models.CaseRelation.target_case_id == case_id))
).first()
# case_id'nin istek sahibinin tenant'ında olduğu kontrol edilmiyor
```

**Risk:** Tenant A, başka tenant'taki davanın ilişki kayıtlarını silebilir.

**Düzeltme — endpoint'in başına tenant ownership kontrolü ekle:**
```python
case = (db.query(models.Case)
          .filter(models.Case.id == case_id,
                  or_(models.Case.tenant_id == tenant_id,
                      models.Case.tenant_id.is_(None)))
          .first())
if not case:
    raise HTTPException(status_code=404, detail="Dava bulunamadı")
# ... mevcut relation lookup
```

**✓ Geriye dönük uyum:** Hem source hem target case NULL-tenant ise her iki tenant erişebilir. ✓

---

### IDOR-5. `/api/documents/{doc_id}/*` — belge → dava → tenant zinciri doğrulanmıyor

**Dosyalar:**
- [routes/documents.py:180-207](../backend/routes/documents.py#L180-L207) — PATCH /link
- [routes/documents.py:210-227](../backend/routes/documents.py#L210-L227) — GET /email-status
- [routes/documents.py:230-262](../backend/routes/documents.py#L230-L262) — GET /download
- [routes/documents.py:265-306](../backend/routes/documents.py#L265-L306) — PATCH /party
- [routes/documents.py:316-387](../backend/routes/documents.py#L316-L387) — POST /resend-email

**Pattern:**
```python
doc = db.query(models.CaseDocument).filter(models.CaseDocument.id == doc_id).first()
if not doc:
    raise HTTPException(status_code=404, detail="Belge bulunamadı")
# ↑ Belge alındı ama doc.case.tenant_id KONTROL EDİLMEDİ
```

`tenant_id: str = Depends(get_current_tenant)` parametre olarak alınıyor ama hiçbir filtreye bağlanmamış (5 endpoint'te de aynı bug).

**Risk (en ağır):** `/download` endpoint'i SharePoint'ten gelen ham PDF/Word'ü döner. Tenant A, doc_id enumeration ile Tenant B'nin dava dosyalarını indirebilir.

**Düzeltme — ortak helper:**

`backend/dependencies.py`'a ekle:
```python
def get_tenant_owned_document(db, doc_id: int, tenant_id: str) -> models.CaseDocument:
    """Belgeyi yalnızca istek sahibi tenant'ın davasına aitse (veya legacy NULL ise) döndürür."""
    doc = (db.query(models.CaseDocument)
             .outerjoin(models.Case, models.CaseDocument.case_id == models.Case.id)
             .filter(models.CaseDocument.id == doc_id,
                     or_(models.Case.tenant_id == tenant_id,
                         models.Case.tenant_id.is_(None),
                         models.CaseDocument.case_id.is_(None)))  # UNLINKED test belgeleri
             .first())
    return doc
```

**`outerjoin` + `case_id IS NULL`** kuralı, "TEST modunda yüklenmiş ama henüz davaya bağlanmamış" belgelerin sahibinin tespit edilemediği bir gri alan yaratır. Bu durum için ek ownership kontrolü:

```python
if doc.case_id is None:
    # UNLINKED/TEST — sadece yükleyen kullanıcı görebilir
    upn = (user.get("preferred_username") or "").lower()
    if (doc.uploaded_by_email or "").lower() != upn:
        return None
```

5 endpoint'te de:
```python
@router.get("/api/documents/{doc_id}/download")
def download_document(doc_id: int,
                      tenant_id: str = Depends(get_current_tenant),
                      user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = get_tenant_owned_document(db, doc_id, tenant_id, user)
        if not doc:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")
        # ... mevcut SharePoint indirme
```

**✓ Geriye dönük uyum:**
- NULL-tenant case'lere bağlı belgeler iki tenanta da açık kalır. ✓
- UNLINKED/TEST belgeler yalnızca yükleyene gösterilir (test akışını bozmaz; tenant ne olursa olsun yükleyici kendi belgesini görür). ✓
- Cross-tenant doc_id enumeration 404 alır. ✓

---

### IDOR-6. `/confirm` endpoint'inde `linked_case_id` tenant doğrulamasız

**Dosya:** [backend/routes/processing.py:520-587](../backend/routes/processing.py#L520-L587), özellikle [L574-587](../backend/routes/processing.py#L574-L587)

```python
if not avukat_kodu and linked_case_id:
    case_fetch = db_fetch.query(models.Case).filter(
        models.Case.id == linked_case_id
    ).first()  # ← tenant filtresi yok
```

Aynı `linked_case_id` aşağıda `_save_case_document(case_id=linked_case_id, ...)` çağrısına gidiyor — yani başka tenant'taki bir davaya belge bağlanabiliyor.

**Risk:** Tenant A, Tenant B'nin dava ID'sini biliyorsa o davaya istemediği bir belge yapıştırabilir; KVKK + bütünlük ihlali.

**Düzeltme — `linked_case_id` boş değilse ownership kontrolü zorunlu:**
```python
user_tenant = user.get("tid")  # /confirm zaten get_current_user istiyor

if linked_case_id:
    db_fetch = SessionLocal()
    try:
        case_fetch = (db_fetch.query(models.Case)
                              .filter(models.Case.id == linked_case_id,
                                      or_(models.Case.tenant_id == user_tenant,
                                          models.Case.tenant_id.is_(None)))
                              .first())
        if not case_fetch:
            raise HTTPException(status_code=404, detail="Belirtilen dava bulunamadı")
        if not avukat_kodu and case_fetch.responsible_lawyer_name:
            # ... mevcut lawyer lookup
    finally:
        db_fetch.close()
```

**✓ Geriye dönük uyum:** NULL-tenant davalara her iki tenant belge ekleyebilir; yeni tenant-stamped davalar yalıtılır. ✓

---

## Yüksek (HIGH)

### IDOR-7. `/api/incomplete-tasks` müvekkil listesi tenant'sız

**Dosya:** [backend/routes/cases.py:442-448](../backend/routes/cases.py#L442-L448)

```python
clients = (
    db.query(models.Client)
    .filter(models.Client.active == True)   # ← tenant filtresi yok
    .order_by(models.Client.updated_at.desc())
    .limit(50).all()
)
```

**Risk:** "Eksik bilgili müvekkiller" widget'ı tüm tenantların müvekkillerini karıştırarak gösterir.

**Düzeltme — IDOR-1'deki `Client.tenant_id` migration sonrası:**
```python
clients = (
    db.query(models.Client)
    .filter(models.Client.active == True,
            tenant_filter_clause(models.Client, tenant_id))
    .order_by(models.Client.updated_at.desc())
    .limit(50).all()
)
```

**✓ Geriye dönük uyum:** Migration sonrası tüm mevcut müvekkiller `tenant_id=NULL` → her iki tenant gösterir. ✓

---

### IDOR-8. `/api/cases/{case_id}/stage-log` tenant filtresi uygulamıyor

**Dosya:** [backend/routes/cases.py:288-294](../backend/routes/cases.py#L288-L294)

```python
@router.get("/api/cases/{case_id}/stage-log", response_model=List[CaseStageLogRead])
def api_get_case_stage_log(case_id: int,
                            tenant_id: str = Depends(get_current_tenant)):
    return get_case_stage_log(case_id)   # ← tenant_id alınıyor ama helper'a verilmiyor
```

`managers/admin_manager.py:get_case_stage_log` imzası tenant parametresi almıyor; eklenmeli.

**Düzeltme:**
1. `admin_manager.get_case_stage_log(case_id, tenant_id)` imzasına `tenant_id` ekle, içeride önce `Case` ownership doğrula:
   ```python
   def get_case_stage_log(case_id: int, tenant_id: str = None):
       db = SessionLocal()
       try:
           case_q = db.query(models.Case).filter(models.Case.id == case_id)
           case_q = _apply_tenant_filter(case_q, tenant_id)
           if not case_q.first():
               return []   # ya da raise
           # ... mevcut stage_log query
   ```
2. Route'ta çağrıyı düzelt: `return get_case_stage_log(case_id, tenant_id=tenant_id)`

**✓ Geriye dönük uyum:** NULL-tenant davaların stage log'u iki tenanta da açık kalır. ✓

---

## Orta (MEDIUM)

### IDOR-9. `case_party_id` tenant cross-check yok (PATCH /documents/{doc_id}/party)

**Dosya:** [routes/documents.py:265-306](../backend/routes/documents.py#L265-L306)

Endpoint `case_party.case_id == doc.case_id` kontrolü yapıyor — bu mantıken iyi, ama IDOR-5'teki `doc` tenant doğrulaması olmadığı için zincirle birlikte sömürülebilir. IDOR-5 çözümü uygulanırsa bu da kapanır.

**Eylem:** IDOR-5 ile birlikte. Ek aksiyon yok.

---

### IDOR-10. SharePoint folder leakage potansiyeli

**Konum:** `SHAREPOINT_FOLDER_ISLENMIS_NAME` env'i tüm tenantlar için tek klasör.

Dava belgeleri SharePoint'te tek klasörde saklanıyor; `download_file_from_sharepoint(folder_name, doc.stored_filename)` `stored_filename`'ı doğrudan kullanır. IDOR-5 düzeltildikten sonra DB seviyesinde erişim kapalı, ama:

**Risk (rezidüel):** Bir saldırgan SharePoint URL'sini ele geçirse (örn. PDF içine link kaçtı), klasör yapısı tenant'lara göre ayrılmadığı için doğrudan SharePoint'e SSO ile gidip indirebilir.

**Öneri:** `stored_filename` üretiminde tenant ID ön ek olarak kullanılabilir (örn. `{tenant_short_id}_{counter}.pdf`) — ancak bu daha büyük bir refactor; ayrı epic olarak değerlendirin.

---

## Düzeltme önerisi: ortak helper'lar

Tek bir yerden yönetebilmek için `backend/dependencies.py` veya yeni bir `backend/auth_helpers.py`'a şu fonksiyonları ekleyin:

```python
from sqlalchemy import or_
from sqlalchemy.orm import Session
import models


def tenant_filter_clause(model, tenant_id: str):
    """`tenant_id == X OR tenant_id IS NULL` clause'u — NULL = paylaşılan legacy."""
    return or_(model.tenant_id == tenant_id, model.tenant_id.is_(None))


def get_tenant_owned_case(db: Session, case_id: int, tenant_id: str):
    return (db.query(models.Case)
              .filter(models.Case.id == case_id,
                      tenant_filter_clause(models.Case, tenant_id))
              .first())


def get_tenant_owned_document(db: Session, doc_id: int,
                              tenant_id: str, user: dict):
    """Belge → dava → tenant zincirini doğrular. UNLINKED belgeler için yükleyene
    sahiplik tanır."""
    doc = (db.query(models.CaseDocument)
             .outerjoin(models.Case, models.CaseDocument.case_id == models.Case.id)
             .filter(models.CaseDocument.id == doc_id,
                     or_(models.Case.tenant_id == tenant_id,
                         models.Case.tenant_id.is_(None),
                         models.CaseDocument.case_id.is_(None)))
             .first())
    if doc and doc.case_id is None:
        upn = (user.get("preferred_username") or user.get("upn") or "").lower()
        if (doc.uploaded_by_email or "").lower() != upn:
            return None
    return doc


def get_tenant_owned_hearing(db: Session, hearing_id: int, tenant_id: str):
    return (db.query(models.HearingDate)
              .join(models.Case, models.HearingDate.case_id == models.Case.id)
              .filter(models.HearingDate.id == hearing_id,
                      tenant_filter_clause(models.Case, tenant_id))
              .first())
```

Tüm IDOR-1…IDOR-8 düzeltmelerinde bu helper'lar kullanılırsa kod tekrarı önlenir ve "NULL = paylaşılan" semantiği tek noktadan yönetilir.

---

## Şema migration'ı (zorunlu — IDOR-1, IDOR-7 için)

`backend/database.py`'daki migration runner'a yeni adım ekle:

```python
# clients tablosuna tenant_id kolonu (idempotent)
ALTER TABLE clients ADD COLUMN IF NOT EXISTS tenant_id VARCHAR;
CREATE INDEX IF NOT EXISTS ix_clients_tenant_id ON clients (tenant_id);
```

`models.py:Client`'a:
```python
tenant_id = Column(String, index=True, nullable=True)
```

**Backfill yapma.** Mevcut 1.996 müvekkili NULL bırak → her iki tenant erişmeye devam eder. Yeni eklenenler `add_client(data)` içinden tenant ile damgalanır.

---

## Test planı

Aşağıdaki testler `backend/security_smoke_test.py` benzeri bir suite olarak yazılıp CI'a alınmalı.

| ID | Senaryo | Beklenen |
|---|---|---|
| **T1** | Tenant A kullanıcısı `GET /api/clients` | Sadece NULL-tenant + Tenant A müvekkilleri |
| **T2** | Tenant A `PUT /api/clients/{B'nin_yeni_müvekkili}` | 404 |
| **T3** | Tenant A `GET /api/cases/client-sequence?client_name=AYŞE`| Sayım Tenant B'nin AYŞE'lerini içermez |
| **T4** | Tenant A `DELETE /api/hearing-dates/{B'nin_hearing_id}` | 404, kayıt durur |
| **T5** | Tenant A `DELETE /api/cases/{B_case}/relations/{rel_id}` | 404 |
| **T6** | Tenant A `GET /api/documents/{B_doc_id}/download` | 404 (SharePoint çağrısı YAPILMAZ) |
| **T7** | Tenant A `PATCH /api/documents/{B_doc_id}/link` | 404 |
| **T8** | Tenant A `POST /confirm` `linked_case_id={B_case}` | 404, belge SharePoint'e gitmez |
| **T9** | NULL-tenant case için her iki tenant → `GET /api/cases/{id}/stage-log` | 200, içerik |
| **T10** | Tenant A `POST /api/clients` → DB'de yeni satırın `tenant_id`'si | Tenant A'nın UUID'si |
| **T11** | Migration sonrası `SELECT COUNT(*) FROM clients WHERE tenant_id IS NULL` | 1996 (backfill yapılmadı) |
| **T12** | Tenant A "UNLINKED" belge yükledi, Tenant B aynı doc_id ile `GET /download` | 404 |

---

## Eylem planı (öncelik sırası)

1. **Helper fonksiyonları yaz** (`auth_helpers.py`) — yarım gün
2. **`Client.tenant_id` migration + `models.py` güncelle** — 1 saat (test ortamında migration çalıştır, satır sayısını doğrula)
3. **IDOR-1: `routes/clients.py` 4 endpoint'i tenant'a bağla** — 1 saat
4. **IDOR-5: 5 belge endpoint'ine helper'ı uygula** — 2 saat
5. **IDOR-6: `/confirm` linked_case_id doğrulaması** — 30 dk
6. **IDOR-2, 3, 4, 7, 8: tek satırlık fix'ler** — toplam 1 saat
7. **Test suite (T1-T12) yaz ve çalıştır** — 2 saat
8. **Production deploy** (mesai dışı, `--build` flag'i ile) — 30 dk

**Toplam efor:** ~1 iş günü.

**Risk:** Migration sırasında DB lock'u uzun sürmez (tek `ALTER TABLE ADD COLUMN`); 14k case'in tenant_id'sine dokunulmuyor. Postgres bunu metadata-only operation olarak yapar.

---

## "Sıfır kesinti" doğrulama checklist'i

Düzeltme deploy'u sonrası elle test edilecek:

- [ ] Tenant A kullanıcısı login olur, dava listesi 14k görünür (NULL-tenant'lar)
- [ ] Tenant B kullanıcısı login olur, dava listesi 14k görünür (NULL-tenant'lar)
- [ ] Her iki tenant'ta müvekkil arama/listeleme `tenant_id=NULL` müvekkilleri gösterir
- [ ] Her iki tenant'ta belge yükleme + `linked_case_id` ile NULL-tenant davaya bağlama çalışır
- [ ] SharePoint indirme her iki tenant için NULL-tenant davalarda çalışır
- [ ] Aktivite raporu admin paneli her iki tenantın admin'i için kendi raporlarını gösterir (orijinal güvenlik incelemesi #5 fix'iyle birlikte)
- [ ] Yeni oluşturulan müvekkil/dava sadece oluşturucunun tenantında görünür (bu noktadan sonra tenant izolasyonu başlar)
