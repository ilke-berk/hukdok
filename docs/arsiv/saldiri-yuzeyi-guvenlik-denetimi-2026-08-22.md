# Saldırı Yüzeyi ve Güvenlik Denetimi — 2026-08-22

**Soru:** Son deploy'dan bu yana saldırı yüzeyimiz arttı mı?
**Kısa cevap:** Evet, HTTP yüzeyi net **+6 uç** arttı (140 → 146) ama artışın
tamamı kimlik doğrulamalı ve tenant filtreli; uygulama kodunda yeni bir kritik
açık bulunmadı. Bulunan en ciddi risk üretim kodunda değil, **geliştirme
ortamında**: LAN'a açık vite dev sunucusu + yükseltilmemiş vite (B-1).

**Kapsam:** `7864baf` (prod, Deploy #14) → `3a5801c` (main HEAD), 51 commit.
**Yöntem:** statik kod incelemesi + bağımlılık denetimi + uç envanteri.
Prod'a HİÇ dokunulmadı (lokal çalışma direktifi, 2026-08-19) — sızma testi
yapılmadı, prod güvenlik duvarı doğrulanmadı (bkz. B-4).

---

## 1. Yüzey deltası

`backend/routes/*.py` decorator sayımı, iki ağaç karşılaştırmalı:

| | 7864baf (prod) | HEAD | Δ |
| --- | --- | --- | --- |
| HTTP ucu | 140 | 146 | **+6** |

### Eklenen (8)

| Uç | Koruma | Not |
| --- | --- | --- |
| `GET /api/notifications` | `get_current_user` | Yalnız kendi satırları (`recipient_email` eşitliği) |
| `GET /api/notifications/count` | `get_current_user` | Aynı sahiplik kuralı |
| `POST /api/notifications/read-all` | `get_current_user` | Aynı sahiplik kuralı |
| `POST /api/notifications/{id}/read` | `get_current_user` | Başkasının id'si **404** (403 değil — id enumeration'a kapalı) |
| `GET /api/notifications/overview` | `get_current_user` + tenant | **Sahiplik kuralının dışında** → B-2 |
| `GET /api/notifications/unresolved-targets` | `get_current_user` | Tenant daraltması yok (bilinçli) → B-2 |
| `GET /api/cases/{id}/stage-decisions` | tenant | Dava ÖNCE çözülür (G016 dersi), sonra satırlar okunur |
| `GET /api/documents/recent` | tenant | `case_id IS NULL` inner join ile dışarıda; `since_hours ≤ 720`, `limit ≤ 200` |

### Kaldırılan (2) — yüzeyi daraltıyor

- `GET /api/documents` (bağlantısız belge listesi)
- `PATCH /api/documents/{doc_id}/link`

### Yüzey DIŞI yeni kod

`services/deadline_scanner.py` (409 satır) HTTP ucu değil: APScheduler işi
olarak 06:00 TR'de, **lider worker kilidi altında** koşar (`api.py` lifespan).
Dışarıdan tetiklenebilir bir yolu yok.

---

## 2. Bulgular

### B-1 · YÜKSEK (lokal geliştirme) — Vite dev sunucusu tüm arayüzlere bağlı, 4 açık açık

`frontend/vite.config.ts:8` → `server.host: "0.0.0.0"`. Kurulu sürüm
**vite 5.4.19**. `npm audit` çıktısı:

| Açık | Şiddet | Etkilenen |
| --- | --- | --- |
| [GHSA-fx2h-pf6j-xcff](https://github.com/advisories/GHSA-fx2h-pf6j-xcff) — `server.fs.deny` bypass **Windows alternate path**'lerde | high | vite ≤6.4.2 |
| [GHSA-4w7w-66w2-5vf9](https://github.com/advisories/GHSA-4w7w-66w2-5vf9) — optimized deps `.map` path traversal | moderate | vite ≤6.4.1 |
| [GHSA-v6wh-96g9-6wx3](https://github.com/advisories/GHSA-v6wh-96g9-6wx3) — launch-editor **NTLMv2 hash sızması**, UNC yolu, Windows | moderate | vite ≤6.4.2 |
| [GHSA-67mh-4wv8-2f99](https://github.com/advisories/GHSA-67mh-4wv8-2f99) — esbuild: **herhangi bir web sitesi** dev sunucusuna istek atıp yanıtı okuyabilir | moderate | esbuild ≤0.24.2 |

**Neden bu repoda ciddi:** üç faktör üst üste biniyor —
1. Geliştirme Windows 11'de yapılıyor; iki açık tam olarak Windows'a özgü.
2. `host: "0.0.0.0"` → dev sunucusu localhost'la sınırlı değil, aynı ağdaki
   (ofis/kafe Wi-Fi) herkese açık.
3. esbuild açığı ağ komşuluğu bile gerektirmiyor: dev sunucusu açıkken
   ziyaret edilen **herhangi bir kötücül sayfa** sunucudan yanıt okuyabilir.

**Etki:** dev sunucusu ayaktayken proje dosyalarının (ve `fs.deny` bypass'ı ile
dizin dışının) okunması; Windows'ta NTLMv2 kimlik özetinin dışarı sızması.

**CI neden yakalamıyor:** `.github/workflows/ci.yml:126` geliştirme zincirini
bilinçli olarak **bloklamıyor** (ADR-013 K3, gerekçe: "tarayıcıya inmez"). Bu
gerekçe üretilen bundle için doğru; ancak buradaki vektör bundle değil,
geliştirme makinesinin kendisi — yani kararın gerekçesi bu riski kapsamıyor.

**Yeni tetikleyici:** izlenmeyen `.claude/launch.json` bu dev sunucusunu 8010
portunda başlatan bir yapılandırma ekliyor. Dev sunucusunun ne sıklıkta ayakta
olduğu arttıkça pencere de büyüyor.

**Öneri (ucuzdan pahalıya):**
1. `server.host: "127.0.0.1"` — tek satır, LAN vektörünü kapatır (esbuild
   cross-origin vektörünü kapatmaz).
2. Vite yükseltmesi: npm'in gösterdiği düzeltme **vite 8.2.2** (semver major) —
   ayrı bir iş kalemi; ADR-013 K3'te zaten "vite major geçişine bağlı" olarak
   not edilmiş.
3. Ara çözüm: dev sunucusunu yalnız gerekince aç; lokal doğrulamayı Docker
   stack'i (8080) üzerinden yap.

---

### B-2 · DÜŞÜK–ORTA (bilinçli karar) — İdari bildirim uçları sahiplik kuralının dışında

`routes/notifications.py:181` (`/overview`) ve `:245` (`/unresolved-targets`)
kapıları `require_admin` DEĞİL, olağan `get_current_user`. Yani **giriş yapan
her kullanıcı** başkalarına giden süre/duruşma uyarılarını ve okunma durumunu
görebiliyor.

Dosya başlığındaki şerh bunu 2026-08-20 kullanıcı kararı olarak kaydediyor
(sistemde rol kavramı yok, "idari pano" bir `localStorage` toggle'ı, ofis ortak
havuzda çalışıyor). Denetim bunu **hata olarak değil, kabul edilmiş genişleme**
olarak raporluyor; kayda geçirme amacıyla sızan alanlar:

- `recipient_email` (personel adresi), `case_id`, `severity`, `read_at`, `title`
- **Gövde (`body`) bilinçli olarak yayınlanmıyor** — `_overview_serialize`
- Başlıklar müvekkil PII taşımıyor; doğrulandı: `deadline_scanner.py:240` ve
  `:328` başlıkları yalnız kural adı / duruşma tarihi / kalan süre üretiyor.
- `/unresolved-targets` tenant daraltması içermiyor (bilinçli — sayaç ortak
  `cases` havuzu üzerinden hesaplanıyor).

Ek not: `tenant_filter_clause` ortak havuz deseni olduğu için (`tenant_id == X
OR IS NULL`) ve bildirim satırları tenant'ını `tenant_id=NULL` davalardan
devraldığı için, `/overview` pratikte iki tenant'ın satırlarını da gösterir.
Bu, tenant modelinin bilinçli sonucudur, ayrı bir kusur değildir.

**Öneri (opsiyonel, karar kullanıcının):** `ADMIN_EMAILS` altyapısı zaten
mevcut (`routes/config.py:49-58`); iki ucu `require_admin`e almak tek satırlık
bir değişiklik. Rol kavramı istenmiyorsa mevcut hâl kalabilir — bu durumda
"idari pano"nun bir yetki sınırı olmadığı bilinçli kabul edilmelidir.

---

### B-3 · DÜŞÜK — Content-Security-Policy başlığı yok

`nginx.conf:38-41` dört başlık gönderiyor (`X-Frame-Options`,
`X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`) ama
**CSP yok**. React varsayılan kaçışı ve `dangerouslySetInnerHTML`
kullanılmaması sayesinde bilinen bir XSS yolu bulunamadı; CSP burada
derinlemesine savunma katmanıdır, açık kapatma değil.

HSTS repo dışındadır (TLS host nginx'inde sonlanır) — doğrulanamadı.

---

### B-4 · DOĞRULANMASI GEREKEN — frontend konteyneri 8080'i tüm arayüzlere yayınlıyor

`docker-compose.yml:126` → `"8080:80"` (IP öneki yok → `0.0.0.0`).
Karşılaştırma: backend `127.0.0.1:8001`, postgres `127.0.0.1:5432` bilinçli
olarak localhost'a sabitlenmiş; frontend değil.

Prod'da GCP güvenlik duvarı yalnız 80/443/22'ye izin veriyorsa risk yoktur.
Açıksa, konteyner nginx'ine **TLS'siz düz HTTP** ile doğrudan erişilir ve host
nginx katmanı (TLS + varsa ek kurallar) atlanır; `/api` proxy'si de o porttan
çalışır. `/export` bu yolda yine kapalıdır (`nginx.conf:62` — konteyner nginx'i
`/export`'u proxy'lemiyor).

Lokal çalışma direktifi gereği sunucuya bakılmadı. Kullanıcı onayıyla
doğrulama, ssh gerektirmeden:

```bash
gcloud compute firewall-rules list --format="table(name,direction,allowed[].map().firewall_rule().list(),sourceRanges.list())"
```

---

### B-5 · BİLGİ — pytest 8.3.5 / PYSEC-2026-1845

`pip-audit` konteyner içinde koşturuldu; **prod bağımlılıklarında 0 açık**.
Tek bulgu `pytest 8.3.5` (düzeltme 9.0.3) — `requirements-dev.txt` üyesi,
prod imajına girmez. CI'da `pip-audit --strict` zaten kapı olarak duruyor.

---

### B-6 · BİLGİ — `backend/scripts/` altında f-string SQL

`add_single_case.py:43,57,72`, `migrate_from_staging.py:99,116,163`,
`import_clients.py:168` (`ALTER TABLE ... ADD COLUMN {col_name} {col_type}`).
İnterpolasyon yalnız **kolon adları** içindir ve sabit sözlüklerden gelir;
değerler parametrelidir. Bu dosyalar HTTP yüzeyinde değil, elle koşulan çevrim
dışı araçlardır. Değiştirilmesi gerekmiyor; kayıt amaçlı listelenmiştir.

---

### B-7 · DÜŞÜK (ölü kod, mayın) — SRI'sız üçüncü taraf CDN script yükleyicisi

`frontend/src/lib/documentUtils.ts:57` çalışma zamanında
`document.head.appendChild(script)` ile **cdnjs.cloudflare.com'dan** pdf.js
çekiyor; `:66` aynı CDN'den worker yüklüyor. **`integrity` (SRI) yok.** Böyle bir
script uygulamanın origin'inde, Azure AD token'ı tutan bir sayfada çalışır.

**Bugün istismar edilemez: dosya ÖLÜ.** `extractTextFromPDF` ve `documentUtils`
için `frontend/src` altında dosyanın kendisi dışında referans yok; ES modülü
olduğundan bundle'a da girmiyor. Yani açık değil, **mayın** — ileride biri
import ettiği an canlı hale gelir.

Tarayıcıda PDF metin çıkarmaya ihtiyaç da yok: bu iş backend'de
(`analyzer.py`, Gemini + PyMuPDF). Dosya silinmeli. Gerçekten gerekirse doğru
yol `pdfjs-dist`i npm bağımlılığı yapmaktır, CDN değil.

Yan fayda: silinmesi B-3'ün CSP'sini sadeleştirir (`script-src 'self'` kalabilir).

---

## 3. Temiz çıkan kontroller

Aşağıdakiler koddan doğrulandı; kusur bulunmadı.

**Kimlik doğrulama zinciri.** `auth_verifier.py` RS256 imzasını JWKS'ten
çekilen anahtarla doğruluyor, `aud` (client_id ve `api://client_id`) ve `exp`
kontrol ediliyor, tenant `ALLOWED_TENANTS` allowlist'ine karşı sınanıyor. Dev
bypass'ı **üç env koşuluna birden** bağlı (`ENV=development` +
`ALLOW_DEV_TENANT=true` + `DEV_MODE=true`) ve ayrıca `tid == "dev-tenant"`
şartı var — prod'da kapalı.

**Korumasız uçların tamamı gerekçeli.** 146 ucun 140'ı dependency kapılı.
Kalan 6:
- `POST /api/client-error` — bilinçli auth'suz; 10/dk IP limiti, 16 KB gövde
  tavanı (`content-length` + gerçek gövde iki kez ölçülüyor), alan beyaz
  listesi + uzunluk kırpma, `kind` allowlist'i.
- 5 adet `/export/*` — router seviyesinde `X-API-Key`
  (`APIRouter(dependencies=[...])`), `hmac.compare_digest` ile sabit zamanlı
  karşılaştırma, env yoksa **503 fail-closed**, zayıf anahtar (<32 karakter
  veya `dev-` önekli) prod'da reddediliyor. Konteyner nginx'i `/export`'u
  proxy'lemiyor.

**Yeni koddaki tenant izolasyonu.**
- `stage-decisions`: davayı önce `get_tenant_owned_case` çözüyor, yoksa 404 —
  satırlar hiç okunmuyor.
- `documents/recent`: `Case` inner join + `tenant_filter_clause` + iki tarafta
  `deleted_at IS NULL`.
- `case_relations_auto`: aday üretimi (`_tku_eslesmeleri`, `_esas_eslesmeleri`)
  tenant + soft-delete filtreli; sondaki id ile toplu okuma bu yüzden güvenli.

**IDOR.** Bildirim tekil okuma başkasının id'sinde 404 döndürüyor;
`/api/download/{file_id}` sahiplik karşılaştırması yapıyor ve eşleşmezse yine
404 (geçerli id sızmıyor).

**SQL enjeksiyonu.** Yeni kodun tamamı ORM/parametreli. HTTP yüzeyinde ham
`text()` yok (tek istisna `case_manager.py:572-579` — sabit metin, kullanıcı
girdisi taşımıyor).

**XSS.** `dangerouslySetInnerHTML` hiç kullanılmıyor; tek `innerHTML` kullanımı
`YetkiBelgesiModal.tsx:201`, yazdırma için OKUMA yönünde. `eval`/`new Function`
yok.

**Komut çalıştırma.** Ghostscript ve LibreOffice çağrıları liste formunda
(`subprocess.run/Popen([...])`), `shell=True` hiçbir yerde yok.

**Dosya yükleme.** `sanitize_filename`: `basename` (yol geçişi),
null-byte temizliği, uzantı allowlist'i (9 uzantı), 200 karakter kırpma;
boyut tavanı `MAX_UPLOAD_MB` + global 50 MB gövde middleware'i.

**Hız sınırı.** Global `100/minute` varsayılan kova (`SlowAPIMiddleware`),
gerçek istemci IP'si `X-Forwarded-For`dan okunuyor.

**Sırlar.** Takip edilen tek env dosyası `.env.example`. Git geçmişinde hiç
`.env` eklenmemiş (`--diff-filter=A` taraması boş). Kaynak ağacında gömülü
anahtar/parola bulunamadı.

---

## 4. Önerilen sıra

1. **B-1/1** — `vite.config.ts`'te `host: "127.0.0.1"`. Tek satır, bugün.
2. **B-4** — prod güvenlik duvarında 8080 doğrulaması (kullanıcı onayıyla).
3. **B-1/2** — vite major yükseltmesi için ayrı görev; ADR-013 K3'ün gerekçesi
   "geliştirme makinesi de bir yüzeydir" notuyla güncellenmeli.
4. **B-7** — ölü pdf.js CDN yükleyicisi silinsin (mayın temizliği, tek dosya).
5. **B-2** — idari uçların yetki kararı gözden geçirilsin (karar kullanıcının).
6. **B-3** — CSP başlığı (derinlemesine savunma), B-7'den sonra.

---

## 5. Düzeltme planı — somut adımlar

Aşağıdaki maddeler denetimden sonra ayrıca doğrulandı (sürüm matrisi gerçekten
kurularak, tahminle değil). Hiçbiri henüz uygulanmadı.

### D-1 · ŞİMDİ · Vite dev sunucusunu localhost'a bağla — 1 satır

`frontend/vite.config.ts:9`

```diff
   server: {
-    host: "0.0.0.0",
+    host: "127.0.0.1",
     port: 8000,
```

**Neden güvenli:** dev sunucusu host'ta koşuyor, konteynerde değil
(`npm --prefix frontend run dev`); `package.json` `"dev": "vite"` — `--host`
bayrağı geçmiyor. Docker frontend'i ayrı bir nginx imajı, vite kullanmıyor.
Yani başka makineden erişim ihtiyacı yok.
**Kapattığı:** LAN vektörü (aynı Wi-Fi'daki herkes).
**Kapatmadığı:** esbuild cross-origin okuması — onun için D-2 şart.

### D-2 · AYRI GÖREV · Vite 6.4.3'e yükselt

**Hedef sürüm kanıtla belirlendi** (üç sürüm ayrı ayrı kurulup `npm audit`
koşturuldu):

| Sürüm | Sonuç |
| --- | --- |
| 5.4.19 (kurulu) | 1 high + 1 moderate |
| 5.4.21 (5.x'in sonu) | **1 high + 1 moderate — 5.x hattına yama GELMEDİ** |
| **6.4.3** | **temiz** |
| 7.3.6 | temiz |

**npm'in önerdiği 8.2.2 KULLANILMAMALI:** `lovable-tagger@1.1.11` peer'i
`vite >=5.0.0 <8.0.0` — vite 8 o eklentiyi kırar. Doğru hedef **6.4.3**
(muhafazakâr) ya da 7.3.6.

**Yükseltme sanıldığından hafif, çünkü ağaç zaten uyumsuz:**
- `vitest@4.1.10` peer'i `vite ^6 || ^7 || ^8` — yani vitest **şu an** vite 5
  ile eşleşmiyor; sessiz kalmasının sebebi `frontend/.npmrc`'deki
  `legacy-peer-deps=true`. Yükseltme bu gizli uyumsuzluğu da kapatır.
- `@vitejs/plugin-react-swc` peer'i `^4 || ^5 || ^6 || ^7 || ^8` — sorun yok.

**Doğrulama zinciri (hepsi yeşil olmadan commit yok):**

```bash
npm --prefix frontend ci && npm --prefix frontend run build && npm --prefix frontend test && npm --prefix frontend run lint && npx --prefix frontend tsc -b --force
```

Ardından `docker compose build frontend && docker compose up -d frontend` +
tarayıcı duman testi (login → dava listesi → belge yükleme).

**Ek iş:** `.github/workflows/ci.yml:124-127` — geliştirme zincirinin
bloklamama gerekçesi ("tarayıcıya inmez") bu denetimin bulgusuyla eksik
kalıyor; ADR-013 K3 notu "geliştirme makinesinin dosya sistemi de bir
yüzeydir" cümlesiyle güncellenmeli. Yükseltme sonrası bu kapı **bloklayıcıya
çevrilebilir** (artık temiz).

### D-3 · DOĞRULAMA ÖNCE · Prod 8080 yayını

Önce ölç (ssh gerektirmez, salt okuma):

```bash
gcloud compute firewall-rules list --format="table(name,direction,allowed[].map().firewall_rule().list(),sourceRanges.list())"
```

- **8080 kapalıysa:** iş yok, `docker-compose.yml:126` olduğu gibi kalır.
- **8080 açıksa:** düzeltme `- "8080:80"` → `- "127.0.0.1:8080:80"`
  (backend ve postgres zaten böyle). ÖN KOŞUL: host nginx'in upstream'i
  gerçekten `127.0.0.1:8080` olmalı — konfig repo dışında, sunucuda; önce
  okunmalı. Değişiklik `docker compose up -d` (recreate) ister → deploy kararı.

### D-4 · KARAR SİZİN · İdari bildirim uçlarının yetkisi

`routes/notifications.py:181` ve `:245` — `get_current_user` → `require_admin`.
Mekanik olarak iki satır; `ADMIN_EMAILS` altyapısı hazır
(`routes/config.py:49-58`). `backend/tests/test_g087_bildirim_yonetim_uclari.py`
güncellenmeli (yetkisiz kullanıcı 403 beklentisi).

**Ama bu 2026-08-20 kararınızı geri alır.** Denetimin görüşü: mevcut hâl bir
kod hatası değil; yalnızca "idari pano" bir yetki sınırı DEĞİL, bir görünüm
tercihidir — bu bilinçliyse iş yok. Rol kavramı ileride gelirse doğal yeri
burasıdır.

### D-5 · DÜŞÜK · CSP — önce Report-Only

Doğrudan zorlayıcı politika koymak riskli: sayfa Google Fonts çekiyor
(`index.html:53-55`), MSAL sessiz token yenilemede `login.microsoftonline.com`
iframe'i açıyor (`src/config/msalConfig.ts:12`) ve `index.html:38` bir inline
`application/ld+json` bloğu içeriyor. Bu yüzden **önce gözlem**:

`nginx.conf`, mevcut `add_header` bloğunun (satır 38-41) yanına:

```nginx
add_header Content-Security-Policy-Report-Only "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self' https://login.microsoftonline.com; frame-src https://login.microsoftonline.com; frame-ancestors 'self'; base-uri 'self'; form-action 'self'" always;
```

Birkaç gün ihlal raporu izlenir (tarayıcı konsolu + `/api/client-error`
beacon'ı zaten ERROR olarak topluyor), politika daraltılır, sonra
`-Report-Only` eki düşürülür.

### D-6 · İŞ YOK · pytest PYSEC-2026-1845

Zaten yönetiliyor: `backend/audit-ignore.txt` içinde gerekçeli ve
**2027-02-14 gözden geçirme tarihli** bir ignore satırı var; tarih kapısı
(`ci.yml:58`) kalıcılaşmasını engelliyor. Ayrıca prod imajına girmiyor.
Bu denetim yeni bir iş açmıyor.

### D-7 · Ölü pdf.js CDN yükleyicisini sil

`git rm frontend/src/lib/documentUtils.ts`. Silmeden önce ölülük tekrar
doğrulanmalı (`grep -rn "documentUtils\|extractTextFromPDF" frontend/src` yalnız
dosyanın kendisini vermeli). Import edilmediği için build/test etkilenmez —
etkilenirse ölçüm yanlıştı demektir. D-5'ten (CSP) önce yapılmalı.

### Özet tablo

| # | İş | Dosya | Efor | Deploy? | Karar |
| --- | --- | --- | --- | --- | --- |
| D-1 | vite host → 127.0.0.1 | `frontend/vite.config.ts:9` | 1 satır | hayır (lokal) | teknik |
| D-2 | vite 5.4.19 → 6.4.3 | `frontend/package.json` | ~yarım gün | evet (frontend imajı) | teknik |
| D-3 | 8080 yayını | `docker-compose.yml:126` | önce ölç | evet (recreate) | ölçüme bağlı |
| D-4 | idari uç yetkisi | `routes/notifications.py:181,245` | 2 satır + test | evet | **sizin** |
| D-5 | CSP (Report-Only) | `nginx.conf:41` | 1 satır + izleme | evet | teknik |
| D-6 | pytest | — | yok (yönetiliyor) | — | — |
| D-7 | ölü CDN yükleyicisi | `frontend/src/lib/documentUtils.ts` | 1 dosya silme | evet | teknik |

### Kuyruk karşılığı (2026-08-22'de yazıldı)

| Görev | Karşılığı | Bant |
| --- | --- | --- |
| `G088` | D-1 | frontend |
| `G090` | D-7 | frontend |
| `G089` | D-2 | backend (ana dizin — npm paketi) |
| `G091` | D-5 | docs, `bagimli:G090` |

D-3 ve D-4 bilinçli olarak **otomasyona verilmedi**: biri gcloud ölçümü +
deploy kararı ister, diğeri kullanıcının 2026-08-20 kararını tersine çevirir.
İkisi de `gorevler/KUYRUK.md` → "Kullanıcı kararı bekleyenler" bölümünde.

---

## Ek: kanıt komutları

```bash
docker compose exec -T backend sh -c "pip install -q pip-audit && python -m pip_audit"
npm --prefix frontend audit
git diff --stat 7864baf..HEAD -- backend/
```

Uç envanteri ve koruma haritası `backend/routes/*.py` üzerinde decorator +
fonksiyon imzası eşleştirmesiyle üretildi (dependency adları: `get_current_user`,
`get_current_tenant`, `require_admin`, `require_export_api_key`).
