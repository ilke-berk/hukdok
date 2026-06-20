# Güvenlik İncelemesi — HukuDok

**İnceleme tarihi:** 2026-05-10
**Kapsam:** Tüm backend (FastAPI), nginx, docker-compose, frontend MSAL ayarları, repo durumu
**Branch:** `main` (origin/main ile eşit)

> Diff yapılacak değişiklik bulunmadığı için inceleme tüm kod tabanına genişletildi.

---

## Kritik (CRITICAL)

### 1. Açık CORS + Credentials — [backend/api.py:181-187](../backend/api.py#L181-L187)
```python
app.add_middleware(CORSMiddleware,
    allow_origin_regex=".*", allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"])
```
**Risk:** Herhangi bir kötü amaçlı site, kurban tarayıcısından kimlik bilgisiyle (cookie/Authorization) bu API'ye CSRF benzeri istek atabilir. `allow_credentials=True` + `*` kombinasyonu standart olarak yasak — tarayıcı bunu reddetse de regex `.*` ile bypass ediliyor.
**Öneri:** Üretim domainlerini whitelist olarak listele (`allow_origins=["https://hukudok.example.com"]`).

### 2. Authenticated olmayan dosya indirme — [backend/routes/processing.py:492-505](../backend/routes/processing.py#L492-L505)
```python
@router.get("/api/download/{file_id}")
async def download_file(file_id: str):  # Depends YOK
```
**Risk:** UUID4'ün rastgeleliğine güveniyor ama auth yok. Loglara, hata mesajlarına veya header sızmasına bağlı UUID, KVKK kapsamındaki belgeyi açar.
**Öneri:** `Depends(get_current_user)` ekle ve cache anahtarına kullanıcı ID'sini bağla.

### 3. Multi-tenant izolasyon eksikleri (IDOR)
Aşağıdaki endpoint'ler `doc_id`/`hearing_id`/`relation_id` üzerinden erişimde belgeye ait davanın **tenant_id'sini doğrulamıyor**. Tenant A'daki kullanıcı, tenant B'nin doc_id'sini bilirse erişebilir:

| Endpoint | Dosya | Konum |
|---|---|---|
| `GET /api/documents/{doc_id}/download` | documents.py | [L230-262](../backend/routes/documents.py#L230-L262) |
| `PATCH /api/documents/{doc_id}/link` | documents.py | [L180-207](../backend/routes/documents.py#L180-L207) |
| `PATCH /api/documents/{doc_id}/party` | documents.py | [L265-306](../backend/routes/documents.py#L265-L306) |
| `GET /api/documents/{doc_id}/email-status` | documents.py | [L210-227](../backend/routes/documents.py#L210-L227) |
| `POST /api/documents/{doc_id}/resend-email` | documents.py | [L316-387](../backend/routes/documents.py#L316-L387) |
| `DELETE /api/hearing-dates/{hearing_id}` | cases.py | [L375-389](../backend/routes/cases.py#L375-L389) |
| `DELETE /api/cases/{case_id}/relations/{relation_id}` | cases.py | [L245-270](../backend/routes/cases.py#L245-L270) |
| `GET /api/cases/{case_id}/stage-log` | cases.py | [L288-294](../backend/routes/cases.py#L288-L294) — `tenant_id` parametresi alınıyor ama kullanılmıyor |
| `GET /api/cases/client-sequence` | cases.py | [L60-85](../backend/routes/cases.py#L60-L85) — tüm tenantların müvekkil sayımına bakıyor |

**Öneri:** Her `doc_id`/`hearing_id` lookup'ında ilişkili `Case.tenant_id == tenant_id` filtresi zorunlu kılınmalı; ortak helper (`get_doc_for_tenant(doc_id, tenant)`) yazılması tavsiye edilir.

### 4. Müvekkil (Client) endpoint'lerinde tenant filtresi yok — [backend/routes/clients.py](../backend/routes/clients.py)
```python
@router.get("/api/clients")  # Tüm tenantların tüm müvekkillerini döner
@router.put("/api/clients/{client_id}")  # Başka tenantın müvekkilini güncelleyebilir
@router.delete("/api/clients/{client_id}")  # Başka tenantın müvekkilini silebilir
```
**Risk:** `Client` modelinde `tenant_id` bulunmuyor olabilir; bu durumda tüm tenantlar arasında müvekkil listesi paylaşılıyor — KVKK ihlali. Authenticated her kullanıcı diğer şirketlerin müvekkillerini düzenleyebilir/silebilir.

### 5. "Admin" endpoint'lerinde admin kontrolü yok — [backend/routes/activity.py:260-436](../backend/routes/activity.py#L260-L436)
```python
@router.delete("/api/activity/admin/reset")
def admin_reset_report(..., user: dict = Depends(get_current_user)):  # require_admin yok
@router.get("/api/activity/admin/list")  # tüm kullanıcıların raporlarını döker
@router.get("/api/activity/admin/report/{report_id}")  # herkesin raporunu getirir
```
**Risk:** `require_admin` decorator'ı hiç kullanılmıyor. Authenticated her kullanıcı tüm kullanıcıların aktivite raporlarını listeleyip silebilir.
**Öneri:** `Depends(require_admin)` (config.py:37'deki helper) kullanılmalı.

---

## Yüksek (HIGH)

### 6. JWT `aud` doğrulaması atlanmış — [backend/auth_verifier.py:65-69](../backend/auth_verifier.py#L65-L69)
```python
options={"verify_aud": False, "verify_exp": True}
```
Bu uygulama için verilmemiş bir Microsoft Graph access token'ı (örn. başka bir multi-tenant uygulama tokeni) aynı tenant'tan geldiği sürece kabul edilir. Token replay riski.
**Öneri:** Uygulamanın `client_id`'sine eşit olarak `verify_aud=True` + `audience=...` zorunlu kılın.

### 7. Postgres dump (9.6MB) repo kökünde, `.gitignore`'da değil — [backup.sql](../backup.sql)
İçeriği gerçek prod dump'ı (`pg_dump`). `.gitignore`'da `*.sql` yok; `git add .` yapılırsa commit edilir. Ayrıca bu dosyanın diskte düz olarak durması da KVKK/PII açısından risk.
**Öneri:** `.gitignore`'a `*.sql`, `backup.sql` ekleyin; dosyayı şifrelenmiş dış depoya taşıyıp diskten silin.

### 8. Postgres host'ta açık — [docker-compose.yml:14-15](../docker-compose.yml#L14-L15)
```yaml
ports:
  - "5432:5432"
```
**Risk:** Üretim host'unda 5432 portu dış dünyaya açıksa Postgres credential brute-force hedefi. `POSTGRES_PASSWORD` `.env` üzerinden geliyor.
**Öneri:** `ports` bloğunu kaldırın veya `127.0.0.1:5432:5432` yapın; sadece `hukudok-network` içinden erişim yeterli.

### 9. nginx güvenlik header'ları — KISMEN ÇÖZÜLDÜ (2026-05-10)
**Gerçek mimari:** TLS terminasyonu host nginx'te (port 443), container nginx (`listen 80`) bunun arkasında çalışıyor — yani "HTTPS yok" iddiası yanlıştı.

**Eklendi (container nginx — bu repo):**
- `X-Frame-Options: SAMEORIGIN`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy` (kamera/mikrofon/konum kapalı)
- `X-Forwarded-Proto`: artık edge'den geleni passthrough ediyor (önceden `$scheme` ile overwrite ediliyordu — backend her zaman "http" görüyordu)

**Hâlâ yapılacak (host nginx — bu repo dışı, SSH ile):**
- **HSTS** (`Strict-Transport-Security`): TLS edge'de olduğu için orada eklenmeli. Önerilen: `max-age=31536000; includeSubDomains` (preload eklemeden önce subdomain'lerin hepsinin HTTPS olduğundan emin ol).
- **CSP**: app'in inline script/style ihtiyacı test edilmeden eklenirse prod kırılabilir → ileri tarihe (önce `Content-Security-Policy-Report-Only` ile sahaya çıkar, log topla).

### 10. ~~MSAL token'ı `localStorage`'da~~ — ÇÖZÜLDÜ (2026-05-10)
`cacheLocation: "sessionStorage"` olarak değiştirildi. Tab/uygulama kapandığında token uçar, kullanıcı tekrar login olur. Güvenlik > UX kararı.
- `dangerouslySetInnerHTML` (chart.tsx:70): CSS değişkenleri için, `ChartConfig` developer tarafından sabit, kullanıcı verisinden uzak — kabul edilen risk.
- `innerHTML` okuma (YetkiBelgesiModal.tsx:132): Sadece kendi kullanıcısının girdiği veriler print penceresine basılıyor → self-XSS, tek tenant modelinde önemsiz.

---

## Orta (MEDIUM)

### 11. Dosya boyutu sınırı tutarsız
- `RequestSizeLimitMiddleware`: 100 MB ([api.py:215](../backend/api.py#L215))
- nginx `client_max_body_size`: 100 MB ([nginx.conf:2](../nginx.conf#L2))
- `validate_file_size.MAX_MB`: 50 ([file_utils.py:178](../backend/file_utils.py#L178))
- `/process` chunked check'inde de 50 MB kullanılıyor

Hata mesajının "Maximum 100MB" demesi ([api.py:209](../backend/api.py#L209)) yanıltıcı; sınırın 50MB olması daha doğru.

### 12. Linked case `tenant_id` doğrulanmadan belge bağlanıyor — [backend/routes/processing.py:528-565](../backend/routes/processing.py#L528-L565)
`/confirm` endpoint'inde `linked_case_id` Form alanı geliyor; davanın istek sahibinin tenant'ında olduğu doğrulanmıyor. Saldırgan başka tenant'taki davaya belge bağlayabilir.

### 13. Global in-memory cache thread-safe değil — [processing.py:27,30](../backend/routes/processing.py#L27)
`DOWNLOAD_CACHE` ve `PROCESS_CACHE` plain `dict` — uvicorn worker'larında race + multiple worker'da paylaşılmıyor. Yapısal hata değil ama production riski (cache miss + temp dosya leak'i).

### 14. `/api/incomplete-tasks` müvekkil listesinde tenant filtresi yok — [cases.py:442-448](../backend/routes/cases.py#L442-L448)
Davalar tenant'a göre filtrelenirken müvekkiller filtresiz alınıyor. Aynı IDOR pattern.

### 15. Hata mesajlarında stack trace / detay sızması
Birçok handler `detail=f"...: {e}"` döndürüyor (örn. activity.py:317, 326, 360). İç DB hatalarını client'a yansıtmamak gerek.

---

## Düşük (LOW)

### 16. `ENV=development` + `ALLOW_DEV_TENANT=true` bypass — [auth_verifier.py:39-41](../backend/auth_verifier.py#L39-L41)
Açıkça ENV gerektiriyor (iyi) ama prod'da ENV variable'ı yanlışlıkla "development" set edilirse `tid="dev-tenant"` token kabul edilir. Üretim Docker imajında bu env vars zorla `production` olarak override edilmeli.

### 17. `secret_value` log riski ✅ DÜZELTİLDİ (2026-05-10)
`auth_verifier.py:46` warning içinde `ALLOWED_TENANTS` set'ini log'a yazıyor — tenant ID'leri sızar (sadece operasyonel risk, değişmez değer).

**Çözüm:** Yetkisiz tenant uyarısı artık yalnızca token'daki `tid`'i logluyor; whitelist set'i log'a yazılmıyor.

### 18. SharePoint download'da MIME doğrulaması yok — [documents.py:260](../backend/routes/documents.py#L260) ✅ DÜZELTİLDİ (2026-05-10)
SharePoint'in döndürdüğü `content_type` doğrulanmadan kullanıcıya verilmesi nadir bir reflected-content riski yaratır. Belgeleri her zaman `application/octet-stream` olarak servis etmek daha güvenli.

**Çözüm:** SharePoint'ten dönen `content_type` artık yok sayılıyor; download endpoint her zaman `media_type="application/octet-stream"` ile servis ediyor. `Content-Disposition: attachment` ile birleşince tarayıcı içeriği yorumlamıyor.

---

## İyi yapılan kontroller

- JWT imza doğrulaması (PyJWKClient)
- File magic-byte doğrulama (PDF/UDF)
- `defusedxml` kullanımı (XXE'ye karşı) — [udf_converter.py:13](../backend/udf_converter.py#L13)
- SQLAlchemy ORM/parameterized queries (SQLi yok)
- Rate limiting middleware tanımlı (ama endpoint başına `@limiter.limit` decorator'ı kullanılmamış — global 100/min korumada kalıyor)
- Filename sanitization — [file_utils.py:41](../backend/file_utils.py#L41)
- KVKK temp file cleanup — [api.py:152-168](../backend/api.py#L152-L168)
- Vault (Windows keyring) kullanımı

---

## Eylem planı (öncelik sırasıyla)

1. **CORS regex'i prod domain whitelist ile değiştir** (5 dk işi, anında etki)
2. **`/api/download/{file_id}`'ye auth ekle** (5 dk)
3. **Tenant doğrulama helper'ı yaz, IDOR olan tüm endpoint'lere uygula** (yarım gün)
4. **`activity/admin/*` endpoint'lerine `require_admin` ekle** (15 dk)
5. **`backup.sql` repo'dan ve diskten kaldır, `.gitignore`'a ekle** (5 dk)
6. **docker-compose'da Postgres portunu kapat veya 127.0.0.1'e bağla** (5 dk)
7. **JWT `aud` doğrulamayı aç** (15 dk)
8. **nginx security header + TLS** (1 saat)
