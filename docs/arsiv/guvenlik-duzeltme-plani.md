# Güvenlik Denetim & Düzeltme Planı

**Tarih:** 2026-05-02  
**Durum:** Plan aşaması — implementasyon başlamadı  
**Toplam açık:** 3 Kritik · 3 Yüksek · 4 Orta · 2 Düşük

---

## Genel Değerlendirme

- **API key reverse engineering:** GÜVENLİ — Gemini API key yalnızca backend env var olarak tutuluyor, frontend bundle'a gömülmüyor.
- **SQL Injection:** GÜVENLİ — SQLAlchemy ORM parametrized query kullanıyor.
- **`.env` git'te:** GÜVENLİ — `.gitignore` doğru ayarlanmış.
- **Kritik sorunlar:** Auth bypass, CORS misconfiguration, eksik backend authorization.

---

## ADIM 1 — Dev-Tenant Auth Bypass (KRİTİK)

**Dosya:** `backend/auth_verifier.py` satır 38-40

**Sorun:**
```python
# Dev Mode Bypass
if token_tenant == "dev-tenant":
    return unverified_claims   # İmza doğrulanmadan kabul ediliyor!
```
Herhangi biri `"tid": "dev-tenant"` içeren sahte bir JWT oluşturup sisteme giriş yapabilir. İmza kontrolü tamamen atlanıyor.

**Düzeltme:**
```python
import os
# Sadece development ortamında, açıkça etkinleştirilmişse
if os.getenv("ENV") == "development" and os.getenv("ALLOW_DEV_TENANT") == "true":
    if token_tenant == "dev-tenant":
        return unverified_claims
```

**Uygulama notları:**
- Production `.env` dosyasında `ALLOW_DEV_TENANT` değişkeni bulunmamalı
- `ENV=production` olduğunda bu blok hiç çalışmayacak
- Test sonrası dev bypass'ı tamamen kaldırmak tercih edilir

**Öncelik:** Hemen — 1 satır exploit

---

## ADIM 2 — Wildcard CORS + Credentials (KRİTİK)

**Dosya:** `backend/api.py`

**Sorun:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",   # Her origin kabul ediliyor
    allow_credentials=True,    # Cookie/token gönderiliyor
    allow_methods=["*"],
    allow_headers=["*"],
)
```
`allow_origin_regex=".*"` + `allow_credentials=True` kombinasyonu CORS spec'i ihlal eder ve CSRF saldırısına zemin hazırlar.

**Düzeltme:**
```python
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Uygulama notları:**
- `.env.production` dosyasına `ALLOWED_ORIGINS=https://app.domain.com` eklenecek
- Birden fazla origin varsa virgülle ayrılacak: `https://a.com,https://b.com`

**Öncelik:** Acil

---

## ADIM 3 — Frontend-Only Admin Kontrolü (KRİTİK)

**Dosya:** `frontend/src/components/ProtectedAdminRoute.tsx`

**Sorun:**
```typescript
const ADMIN_EMAILS = [
    "IlkeKutluk@lexisbio.onmicrosoft.com",
];
```
Bu liste frontend bundle'da herkesin görebileceği şekilde duruyor. Üstelik backend'de admin kontrolü olmadığından, authenticated herhangi bir kullanıcı config endpoint'lerine doğrudan istek atabilir.

**Düzeltme — 2 adımlı:**

**3a) Backend'e admin kontrolü ekle** (`backend/routes/config.py`):
```python
ADMIN_EMAILS = set(os.getenv("ADMIN_EMAILS", "").lower().split(","))

def require_admin(user: dict = Depends(get_current_user)):
    email = (user.get("preferred_username") or user.get("email") or "").lower()
    if email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Yönetici yetkisi gerekli")
    return user

# Tüm config endpoint'lerinde:
@router.post("/api/config/lawyers")
def api_add_lawyer(item: ConfigItem, user: dict = Depends(require_admin)):
    ...
```

**3b) Frontend'den hardcoded email kaldır** — Frontend yalnızca UI gizleme yapacak, yetki backend'de kontrol edilecek.

**Uygulama notları:**
- `.env` dosyasına `ADMIN_EMAILS=ilkekutluk@lexisbio.onmicrosoft.com` eklenecek
- Frontend'deki `ProtectedAdminRoute` componenti silinmeyecek — ama yalnızca UI/UX amaçlı kullanılacak
- Etkilenen endpoint'ler: `POST/DELETE /api/config/*` (lawyers, statuses, doc_types, settings)

**Öncelik:** Acil

---

## ADIM 4 — Tenant Isolation Eksikliği (YÜKSEK)

**Dosya:** `backend/routes/cases.py`, `backend/routes/documents.py`, diğer route'lar

**Sorun:**
LexisBio (tenant A) ve Hanyaloglu (tenant B) aynı veritabanını paylaşıyor. Ama sorgularda `tenant_id` filtresi yok. Tenant A'nın kullanıcısı Tenant B'nin davalarını görebilir.

**Düzeltme:**
```python
# Kullanıcının tenant_id'sini token'dan al
def get_current_tenant(user: dict = Depends(get_current_user)) -> str:
    return user.get("tid")  # JWT'deki tenant ID

# Tüm case sorgularına filtre:
@router.get("/api/cases")
def list_cases(tenant_id: str = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return db.query(Case).filter(Case.tenant_id == tenant_id).all()
```

**Uygulama notları:**
- `cases`, `clients`, `documents` tablolarına `tenant_id` kolonu eklenecek (migration)
- Mevcut veriler için hangi tenant'ın hangi dataya sahip olduğu belirlenip migrasyon yapılacak
- Bu adım öncesinde veri modelinin gözden geçirilmesi gerekiyor

**Öncelik:** Yüksek — mevcut tenant sayısı az ama büyümeden önce çözülmeli

---

## ADIM 5 — Hardcoded Tenant ID ve Şirket İsimleri (YÜKSEK)

**Dosya:** `backend/auth_verifier.py` satır 33-36

**Sorun:**
```python
ALLOWED_TENANTS = [
    "44f029f8-f2f7-4910-8c38-998dca5fad02",  # LexisBio
    "9776cf1f-e0b0-4923-9433-33f3fb4161de",  # Hanyaloglu
]
```
Tenant ID'ler ve şirket isimleri git geçmişinde kalıcı olarak kayıtlı.

**Düzeltme:**
```python
ALLOWED_TENANTS = set(
    t.strip() for t in os.getenv("ALLOWED_TENANTS", "").split(",") if t.strip()
)
```
`.env` dosyasına:
```
ALLOWED_TENANTS=44f029f8-f2f7-4910-8c38-998dca5fad02,9776cf1f-e0b0-4923-9433-33f3fb4161de
```

**Öncelik:** Yüksek — bilgi sızıntısı

---

## ADIM 6 — Kişisel Veri Şifreleme / KVKK (ORTA)

**Dosya:** `backend/models.py`

**Sorun:**
TC kimlik no, pasaport no, email adresleri veritabanında plain text saklanıyor. Veritabanına yetkisiz erişim durumunda tüm kişisel veriler açığa çıkar.

**Düzeltme seçenekleri (değerlendirilecek):**
- **Uygulama katmanı şifreleme:** `sqlalchemy-utils` `EncryptedType` ile hassas alanlar şifrelenir
- **Veritabanı seviyesi:** PostgreSQL `pgcrypto` extension
- **En az efor:** Yalnızca TC ve pasaport gibi yüksek hassasiyetli alanlar şifrelenir

**Uygulama notları:**
- Bu adım migrasyon gerektiriyor, önceki adımlar tamamlandıktan sonra ele alınacak
- Şifreleme anahtarı `.env` üzerinden yönetilecek

**Öncelik:** Orta — KVKK uyumu için gerekli, acil değil

---

## ADIM 7 — Hata Mesajları ve Log Güvenliği (ORTA/DÜŞÜK)

**Dosya:** `backend/routes/documents.py` ve diğer route'lar

**Sorun:**
```python
raise HTTPException(status_code=500, detail=str(e))  # Exception detayı frontend'e gidiyor
```
Stack trace, tablo adları, dosya yolları frontend'e sızabilir.

**Düzeltme:**
```python
logger.error(f"Internal error: {e}", exc_info=True)
raise HTTPException(status_code=500, detail="Bir hata oluştu. Lütfen tekrar deneyin.")
```

**Log'larda PII:**
- Gemini yanıtlarını loglarken müvekkil verilerini maskele
- TC numaralarını loglarken `***` ile değiştir

**Öncelik:** Düşük — ama iyi pratik

---

## Uygulama Sırası

| Adım | Konu | Süre tahmini | Bağımlılık |
|------|------|-------------|------------|
| **1** | Dev-tenant bypass kaldır | 15 dk | Yok |
| **2** | CORS whitelist | 15 dk | `.env` güncelleme |
| **3a** | Backend admin kontrolü | 45 dk | Yok |
| **3b** | Frontend admin email kaldır | 15 dk | 3a tamamlanmalı |
| **4** | Tenant isolation | 2-3 saat | Veritabanı migration |
| **5** | Tenant ID env'e taşı | 15 dk | Yok |
| **6** | KVKK şifreleme | 3-4 saat | Migration planı |
| **7** | Hata mesajları & log PII | 30 dk | Yok |

**Önerilen sıra:** 1 → 5 → 2 → 3a → 3b → 7 → 4 → 6

---

## Tamamlananlar

- [x] ADIM 1: Dev-tenant bypass
- [ ] ADIM 2: CORS whitelist
- [x] ADIM 3a: Backend admin kontrolü
- [x] ADIM 3b: Frontend admin email kaldır
- [x] ADIM 4: Tenant isolation
- [x] ADIM 5: Tenant ID env'e taşı
- [ ] ADIM 6: KVKK şifreleme
- [x] ADIM 7: Hata mesajları & log PII
