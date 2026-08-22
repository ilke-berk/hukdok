# 013 — Bağımlılık yamalama sırası, denetim kapısı ve çalışma zamanı hedefleri

> Son doğrulama: 2026-08-11 · 48e7e58 (G022)

- **Durum:** kabul
- **Bağlam:** Temizlik planı FAZ A.5/A.6 (`docs/plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md`).
  Bağımlılıklar yamasız, çalışma zamanları yaşlanmış. Ama yükseltmenin kendisi gözetimsiz
  yapılamaz: listede **kimlik doğrulamanın kendisi** (PyJWT) ve **tüm dosya yüklemelerinin
  ayrıştırıcısı** (python-multipart) var. Bu kayıt **kararı** sabitler; uygulama ayrı iştir.

---

## Ölçüm (bu kayıt için 2026-08-11'de yeniden alındı)

> **Yöntem şerhi — okuma sırasında bilinmesi gereken.** Bu görev `docs` bandında, bir
> worktree'de koştu: `docker` yasak (bant kuralı), konteynere erişim yok, host'ta `pip`
> kurulumu izinli değil. Bu yüzden **`pip-audit` ikilisi çalıştırılamadı**; onun yerine
> `pip-audit`'in **varsayılan zafiyet servisi** olan PyPI JSON API'si
> (`https://pypi.org/pypi/<paket>/<sürüm>/json` → `vulnerabilities[]`) `requirements.txt` +
> `requirements-dev.txt` içindeki **28 sabit sürümün** hepsi için tek tek sorgulandı.
> Sonuç aynı veri kaynağıdır, **ama kapsamı dardır:** yalnız doğrudan pinler taranır,
> `pip-audit`'in taradığı **transitif kapanış taranmaz** (aşağıda ayrı ele alındı).
> `npm audit` ise gerçekten koşuldu.
>
> **Uygulamadan önce zorunlu:** aynı ölçüm backend bandında
> `docker compose exec -T backend pip-audit` ile tekrarlanır; sayılar farklıysa **bu kaydın
> tabloları değil, o çıktı geçerlidir**.

### Python — 28 sabit sürüm (24 prod + 4 dev)

| Ölçüm | Değer |
| --- | --- |
| Ham kayıt sayısı (`vulnerabilities[]`, geri çekilenler hariç) | **73** |
| Mükerrer ayıklandıktan sonra (GHSA/CVE/PYSEC/BIT alias birleştirmesi) | **39 distinct** |
| Etkilenen paket | **7** (6 prod + 1 dev) |
| Fix sürümü olmayan | **1** |

Mükerrer ayıklaması gerçek: aynı açık PyPI'da 2–4 ayrı kimlikle (GHSA + CVE + PYSEC +
BIT) listeleniyor. Örnek: Pillow'un 33 ham kaydı 17 gerçek açığa iniyor.

| Paket | Sabit sürüm | Ham | Distinct | Bant |
| --- | --- | --- | --- | --- |
| Pillow | 11.1.0 | 33 | **17** | prod |
| cryptography | 42.0.5 | 12 | **7** | prod |
| python-multipart | 0.0.20 | 12 | **6** | prod |
| PyJWT | 2.8.0 | 10 | **6** | prod |
| requests | 2.32.5 | 2 | 1 | prod |
| python-dotenv | 1.2.1 | 2 | 1 | prod |
| pytest | 8.3.5 | 2 | 1 | dev |

Temiz çıkan 21 pin: fastapi, uvicorn, google-genai, pymupdf, msal, keyring, pydantic,
pydantic-settings, slowapi, defusedxml, Office365-REST-Python-Client, flashtext,
keyrings.alt, sqlalchemy, psycopg2-binary, reportlab, openpyxl, apscheduler, httpx,
ruff, mypy.

### Transitif körlük — ölçülemeyen ama ispatlanabilir olan

`requirements.txt` yalnız **doğrudan** bağımlılıkları sabitliyor; lock dosyası yok. Yani
`docker build` her koştuğunda starlette/anyio/certifi/urllib3 sürümleri **yeniden çözülür**
ve imajda hangi sürümün olduğu repodan okunamaz. Buna rağmen starlette için kesin sonuç
metadata'dan çıkarılabilir:

- `fastapi==0.121.3` → `starlette<0.51.0,>=0.40.0` (PyPI `requires_dist`).
- Bu aralıktaki **her** starlette sürümü açıklı: 0.47.1 → 14 kayıt, 0.49.1–0.50.0 → 10 kayıt.
- İlk **temiz** starlette **1.5.0**. Ona ulaşmanın tek yolu fastapi'yi yükseltmek:
  `fastapi==0.141.1` → `starlette>=0.46.0` (üst sınır yok) ve fastapi'nin kendisinde 0 açık.

Sonuç: **starlette bugün kesinlikle açıklı ve fastapi yükseltilmeden yamalanamaz.**
Yukarıdaki 39 distinct rakamı bu 10'u **içermez** — gerçek prod tabanı en az 49'dur.

### npm — `frontend/package-lock.json` ağacı

| Kapsam | Paket | Şiddet | Distinct advisory kaydı |
| --- | --- | --- | --- |
| Tümü (`npm audit`) | **22** | 7 moderate / 15 high | **73** |
| Yalnız prod (`npm audit --omit=dev`) | **10** | 4 moderate / 6 high | **44** |

Yani **22 açığın 12'si yalnız derleme/geliştirme zincirinde** (vite, esbuild, rollup, eslint,
typescript-eslint, vitest'in altı) — tarayıcıya inen bundle'da değil. Plan bu ayrımı yapmıyordu.

**G021 sonrası beklenen değer.** `mammoth` ve `docx` silinince şu kalemler düşer:
`@xmldom/xmldom` (5 kayıt, high — tek sahibi mammoth), `underscore` (1 kayıt, high — mammoth
ve onun `lop`/`duck` bağımlılıkları), `docx/node_modules/nanoid` (prod sayımında 1 kayıt, high).

| Kapsam | G021 sonrası beklenen |
| --- | --- |
| Tümü | **20 paket** (7 moderate / 13 high), 67 kayıt |
| Yalnız prod | **7 paket** (4 moderate / 3 high), 37 kayıt |

> **G021'in bir iddiası bugün geçersiz:** `jszip`'in advisory'si YOK. `jszip@3.10.1` bugünkü
> `npm audit` çıktısında hiç geçmiyor. `docx`'i silmenin advisory getirisi `jszip` değil,
> `docx/node_modules/nanoid`. `@xmldom/xmldom` + `underscore` iddiası ise doğrulandı.

---

## Karar

### K1 — Yükseltme sırası: ucuzdan pahalıya, kimlik doğrulama EN SONA DEĞİL, testin ARKASINA

| # | Adım | Bant | Getiri | Ön koşul |
| --- | --- | --- | --- | --- |
| 1 | G021: ölü npm paketlerini sil | frontend | prod 6 high → 3 high | — |
| 2 | `npm audit fix` (**majör olmayan**): axios ≥1.18, `@remix-run/router` 1.23.3, lodash ≥4.17.24, postcss ≥8.5.23 | frontend | prod açığı **0**'a iner | 1 |
| 3 | python-dotenv 1.2.2, requests 2.33.0, python-multipart 0.0.31, Pillow 12.3.0, cryptography 49.0.0 | backend | 32 distinct kapanır | — |
| 4 | **PyJWT 2.13.0** | backend | 5 distinct kapanır | **`auth_verifier` karakterizasyon testi** (plan B.3) |
| 5 | fastapi 0.141.1 + starlette ≥1.5.0 | backend | ≥10 distinct kapanır | 3 |
| 6 | `node:20` → `node:24`, `python:3.10` → `python:3.12` | backend (altyapı) | EOL borcu kapanır | 2, 3 |
| 7 | Denetim kapıları (K3) | CI | regresyon kapanır | 1–6 yeşil |

**Adım 4 pazarlıksız ön koşullu — ✅ KARŞILANDI (G059, 2026-08-13, `c1dd168`).**
Bu kayıt yazıldığında `backend/auth_verifier.py` **hiçbir testte çalışmıyordu**
(`backend/tests/` altında `AuthVerifier`/`verify_token` için sıfır eşleşme) ve arıza
modeli "herkes içeri girer" ya da "kimse giremez"di. `backend/tests/test_auth_verifier.py`
artık var: `AuthVerifier.verify_token`'ı gerçek RS256 imzalarla, tenant allowlist'i,
dev-bypass ve süre dolumu yollarıyla test ediyor. **Adım 4'ün (PyJWT 2.13.0) ön koşulu
karşılandı** — yükseltme artık kör değil.

> **Ölçüm düzeltmesi (yazıldığı an için doğruydu, artık KISMEN bayat):** görev tanımı
> "PyJWT ve python-multipart'ın ikisinin de test kapsamı ince" diyordu. O zamanki gerçek
> asimetrik: python-multipart **5 test dosyasında** gerçek multipart gövdesiyle uçtan uca
> koşuyordu (`test_case_intake_analyze.py:263`, `test_eml_expand.py:128`,
> `test_faz3_confirm_idempotency.py:324`, `test_faz3_f_conversion_pending.py:441`,
> `test_faz4_failed_event.py:426`); PyJWT'nin kapsamı **sıfırdı** — G059 bunu kapattı,
> yukarıdaki not bkz.

### K2 — Fix sürümü olmayan tek açık: PyJWT `PYSEC-2025-183` / `CVE-2025-45768` — **ignore**

Metin (PyPI'dan birebir): *"pyjwt v2.10.1 was discovered to contain weak encryption.
NOTE: this is disputed by the Supplier because the key length is chosen by the application
that uses the library."*

**Neden ignore edilebilir — kodla:** HukuDok `jwt.encode` **hiç çağırmıyor**; PyJWT yalnız
doğrulama tarafında kullanılıyor ve anahtar Azure AD JWKS'inden gelen **asimetrik açık
anahtar** (`auth_verifier.py:74-83`, `algorithms=["RS256"]`). Uygulamanın seçtiği bir
simetrik gizli anahtar yok → açığın gerektirdiği ön koşul bu kod tabanında oluşmuyor.
**Azaltıcı önlem gerekmiyor; sabit `algorithms=["RS256"]` zaten önlemin kendisi.**

Kalan 5 PyJWT açığının bu koda uygulanabilirliği (yükseltme gerekçesinin özü):

| Açık | Fix | Bu kodda |
| --- | --- | --- |
| `crit` başlığı doğrulanmıyor (RFC 7515 §4.1.11) | 2.12.0 | **Ulaşılabilir**, etki düşük: yine de geçerli RS256 imzası gerekir |
| Bilinmeyen `kid` → sınırsız JWKS isteği | 2.13.0 | **Ulaşılabilir ve kimlik doğrulamasından ÖNCE**: `tid` doğrulanmamış token'dan okunuyor (`:30-31`) ve `get_signing_key_from_jwt` imza doğrulamasından önce koşuyor (`:61`). Tenant GUID'ini bilen bir saldırgan dışarı doğru istek üretebilir. **Yükseltmenin en güçlü tek gerekçesi** |
| HMAC/JWK karışıklığı | 2.13.0 | **Uygulanmaz** — `algorithms=["RS256"]` tek; anahtar ham JSON JWK değil |
| `PyJWKClient` uri şeması (`file:`/`data:`) | 2.13.0 | **Uygulanmaz** — jwks_url `ALLOWED_TENANTS` kontrolünden geçmiş `tid` ile kuruluyor (`:50-55`) |
| `b64:false` detached JWS bellek çoğaltması | 2.13.0 | Düşük — token Authorization başlığında; nginx başlık tamponu sınırlıyor |

python-multipart tarafının uygulanabilirliği de aynı yöntemle ayrıştı:
`UPLOAD_DIR`/`UPLOAD_KEEP_FILENAME` path traversal'ı (0.0.22) **uygulanmaz** — starlette bu
seçenekleri kullanmaz; preamble/epilogue ve part-header DoS'ları (0.0.26/0.0.27)
**ulaşılabilir** — `nginx.conf:7,91` `client_max_body_size 50M` bayt sayısını sınırlar,
CPU'yu sınırlamaz; `QuerystringParser` `;` ayırıcı farklılığı (0.0.30) `Form(...)` uçları
üzerinden **ulaşılabilir** (`routes/processing.py:306+`).

### K3 — Denetim kapısı: kurulu ortamı denetle, ignore listesini **tarihle**, kapıyı **yeşile** aç

**Backend kapısı** — `ci.yml` backend job'ına, `pip install -r requirements.txt
-r requirements-dev.txt` adımından **sonra** (aynı job, aynı ortam):

```
- name: pip-audit
  run: pip-audit --strict $(grep -v '^\s*#' ../backend/audit-ignore.txt | grep -v '^\s*$' \
       | awk '{print "--ignore-vuln " $1}' | tr '\n' ' ')
```

Argümansız `pip-audit` **kurulu ortamı** tarar — böylece transitif körlük (starlette!)
lock dosyası eklemeden kapanır. Eşik: **ignore edilmemiş tek bulgu = kırmızı**.

**Ignore listesi nerede yaşar:** `backend/audit-ignore.txt`, satır başına bir kimlik:

```
PYSEC-2025-183  # PyJWT, fix YOK, tedarikçi itirazlı; jwt.encode çağrılmıyor,
                # anahtar Azure AD RS256 açık anahtarı. Gözden geçirme: 2027-02-11
```

**Nasıl tarihlenip gözden geçirilir:** her satır zorunlu `Gözden geçirme: YYYY-MM-DD`
taşır ve CI'da ayrı bir adım tarihi geçmiş satır bulursa **kapıyı kırmızıya çevirir**.
Böylece ignore sessizce kalıcılaşamaz: ya açık gerçekten kapanır, ya insan tarihi bilinçli
uzatır. Varsayılan pencere 6 ay.

**Frontend kapısı** — `npm audit --omit=dev --audit-level=moderate`.
K1'in 1. ve 2. adımından sonra prod tarafı **0'a** indiği için kapı kurulduğu gün yeşildir.
Geliştirme zinciri (12 açık, vite 8 majörüne bağlı) **ayrı ve bloke etmeyen** bir bilgi
adımında raporlanır; adım 6'dan sonra o da kapıya alınır.

> **Şerh — 2026-08-22 (G089): geliştirme zinciri artık BLOKLAYICI, "beklemede" değil.**
>
> Bu kaydın "tarayıcıya inmez" gerekçesi eksikti: **geliştirme makinesinin dosya sistemi
> de bir saldırı yüzeyidir.** 2026-08-22 güvenlik denetiminin B-1 bulgusu vite 5.4.19'da
> iki somut yol gösterdi — `server.fs.deny` bypass'ı (dev sunucusundan repo dışı dosya
> okuma) ve esbuild'in dev sunucusuna cross-origin istek atıp yanıtı okuyabilme kusuru.
> İkisinin de kurbanı bundle değil, geliştiricinin diski.
>
> Bekleme sebebi ("vite majörü") kapandı: **vite ^6.4.3** kuruldu ve `npm audit` ağacın
> tamamında (dev dahil) **0 açık** veriyor. `ci.yml`'daki bilgi adımından `|| true`
> düştü — kapının açık kalması bundan sonra yeni bir açığın sessizce girmesi demekti.
>
> **Hedef neden 6, 8 değil (ölçümle):** 5.4.21 (5.x hattının sonu) hâlâ 1 high + 1
> moderate — 5.x'e yama gelmedi. 6.4.3 ve 7.3.6 temiz. npm'in önerdiği 8.2.2 ise
> `lovable-tagger@1.1.11`'in `vite >=5.0.0 <8.0.0` peer'ini kırar
> (`frontend/vite.config.ts:4,57`, yalnız `mode === 'development'` altında kullanılıyor
> ama peer çözümü yine de patlar). Muhafazakâr olan 6 seçildi.
>
> **Yan kazanç:** `vitest@4.1.10`'un peer'i `vite ^6 || ^7 || ^8` — yani ağaç bugüne
> kadar **gizliden uyumsuzdu**, sessiz kalmasının tek sebebi `frontend/.npmrc`'deki
> `legacy-peer-deps=true` idi. Yükseltme bu uyumsuzluğu da kapattı.

> **Frontend kapısının ön koşulu — bugün kapı yanlış ağacı ölçüyor.**
> `frontend/Dockerfile:8-9` yalnız `package.json`'ı kopyalayıp `npm install` koşuyor;
> `package-lock.json` kurulum anında **ortamda değil**. Yani prod imajı lock'un tarif
> ettiği ağacı değil, build anında yeniden çözülmüş bir ağacı yayınlıyor — oysa CI
> `npm ci` ile lock'u kuruyor (`ci.yml:86`). **Denetlenen ağaç ile yayınlanan ağaç aynı
> değil.** Kapıdan önce Dockerfile `COPY frontend/package.json frontend/package-lock.json
> frontend/.npmrc ./` + `npm ci` yapmalı.

### K4 — Çalışma zamanı hedefleri: `node:20` → **`node:24`**, `python:3.10` → **`python:3.12`**

Doğrulanmış takvimler (kaynak: nodejs/Release `schedule.json`, endoflife.date):

| Çalışma zamanı | Bugünkü | EOL | Hedef | Hedefin EOL'ü |
| --- | --- | --- | --- | --- |
| Node | 20 | **2026-04-30 — 3,5 ay önce geçti** | **24** (Aktif LTS 2025-10-28'den beri) | 2028-04-30 |
| Python | 3.10 | **2026-10-31 — 2,7 ay kaldı** | **3.12** | 2028-10-31 |

**Tahmini kırılma yüzeyi — Node 20 → 24.** İki yerde birden değişir: `frontend/Dockerfile:2`
(`FROM node:20 AS builder`) ve `ci.yml:80` (`node-version: "20"`). İkisi de aynı commit'te
değişmezse CI ile imaj ayrışır. Doğrulama zaten var: `npm ci` + `eslint` + `tsc --noEmit` +
299 vitest + `npm run build`. Ek getiri: vite 8 (`engines: ^20.19.0 || >=22.12.0`) ancak bu
adımdan sonra rahatça alınabilir → 12 dev advisory'sinin yolu açılır.

**Tahmini kırılma yüzeyi — Python 3.10 → 3.12.** `backend/Dockerfile:2` +
`ci.yml:43`. Tekerlek taraması yapıldı: **mevcut pinlerin hepsi 3.12'de tekerlekli**
(`psycopg2-binary==2.9.9` → cp312 tekerleği var). Kod tarafında 3.11/3.12'nin kaldırdığı
bir API kullanılmıyor; 868 test + ruff + mypy kapısı doğrulamayı taşır.

**Neden 3.13 değil:** `psycopg2-binary==2.9.9`'un **cp313 tekerleği yok** (cp37–cp312).
3.13, pin yükseltmesini (≥2.9.10) zorunlu kılar — kendi başına sorun değil ama "çalışma
zamanı yükseltmesi" işini "bağımlılık yükseltmesi" işine bağlar. Ayrı iş olarak sıraya alınır.

**Ayrıca ölçülen bağ:** yamaların hedef sürümleri **zaten** `>=3.10` istiyor
(requests 2.33.0, python-dotenv 1.2.2, python-multipart 0.0.31, Pillow 12.3.0, pytest 9.0.3,
fastapi 0.141.1, starlette 1.5.0). Yani çalışma zamanı yükseltmesi bir hijyen kalemi değil,
**gelecekteki yamalamanın ön koşulu**: bir sonraki dalga `>=3.11` isteyecek.

### K5 — Yükseltme adayları ve kırılma riski (tek tablo)

| Paket | Mevcut | Hedef | Distinct | Kırılma riski / etkilenen kod yolu |
| --- | --- | --- | --- | --- |
| Pillow | 11.1.0 | 12.3.0 | 17 | `pdf/format_converter.py:126-209`, `udf_converter.py:90-112`. Kullanılan API: `Image.open`, `convert`, `thumbnail`, `resize`, `Image.LANCZOS`. **Somut kontrol:** Pillow 12'de `Image.LANCZOS` takma adının durduğu doğrulanmalı. Emniyet ağı var: `test_format_converter.py` + `test_udf_converter.py` |
| cryptography | 42.0.5 | 49.0.0 | 7 | **Doğrudan import YOK** (kod tabanında `from cryptography` sıfır eşleşme) — yalnız PyJWT/msal/office365 üzerinden transitif. Risk ABI/tekerlek düzeyinde; abi3 tekerlekleri mevcut. **En düşük riskli 7 açık** |
| python-multipart | 0.0.20 | 0.0.31 | 6 | starlette `FormParser`/`MultiPartParser` üzerinden **tüm** `UploadFile`/`Form` uçları (`routes/processing.py`, `routes/case_intake.py`). Ayrıştırıcı davranış değişikliği: `;` artık ayırıcı değil — `application/x-www-form-urlencoded` gövdesinde `;` kullanan bir istemci varsa alan bölünmesi değişir (frontend axios `&` üretir → risk düşük). 5 test dosyası bu yolu gerçekten koşuyor |
| PyJWT | 2.8.0 | 2.13.0 | 6 (5 fix'li + 1 fix'siz) | `auth_verifier.py` **tek kullanıcı**, **sıfır test**. 2.10'dan sonra `jwt.decode` çağrısında `algorithms` zorunlu (zaten veriliyor, `:77`), kaldırılan `verify=` kwarg'ı kullanılmıyor. Risk teknik olarak düşük, **kapsamsızlık yüzünden operasyonel olarak yüksek** |
| requests | 2.32.5 | 2.33.0 | 1 | Yaygın ama sığ kullanım; `requires_python>=3.10` |
| python-dotenv | 1.2.1 | 1.2.2 | 1 | Yama sürümü |
| starlette (transitif) | ≤0.50.0 | ≥1.5.0 | ≥10 | **fastapi 0.121.3 → 0.141.1 gerekir.** En geniş yüzey: tüm route/middleware/TestClient. Ayrı iş |
| pytest (dev) | 8.3.5 | 9.0.3 | 1 | Majör; 868 testin toplanmasını etkileyebilir. Prod imajına girmiyor → **en düşük öncelik** |
| axios | 1.13.2 | ≥1.18.0 | 29 kayıt (+ `form-data` 1, `follow-redirects` 1) | `^1` içinde minör; frontend'in tek HTTP istemcisi |
| `@remix-run/router` | 1.23.2 | 1.23.3 | 1 (+ `react-router` 3 + `react-router-dom` 1) | **Transitif yama — `react-router-dom` v6→v7 majörü GEREKMEZ.** Açık aralığı `6.0.0 - 7.17.0` görünse de kök neden router'da ve 1.23.3 yaması `^6.30` altında çözülüyor |
| lodash (recharts üzerinden) | 4.17.23 | ≥4.17.24 | 2 | `^4` içinde yama |
| postcss (dev) | ≤8.5.22 | ≥8.5.23 | 2 | `^8` içinde yama |
| vite (dev) | ~~5.4.x~~ **6.4.3 (uygulandı, G089)** | ~~8.2.1~~ **6.4.3** | 3 (+ esbuild 1, rollup 1) | **UYGULANDI 2026-08-22.** 8 hedefi reddedildi: `lovable-tagger` peer'i `<8.0.0`. 6.4.3 ile ağaç (dev dahil) 0 açık; kapı bloklayıcıya çevrildi — bkz. K3 şerhi |

---

## Gerekçe

1. **Kapı kurulduğu gün yeşil olmalı, yoksa kapı değildir.** Planın uyardığı tuzak gerçek:
   PyJWT `PYSEC-2025-183`'ün fix sürümü **yok** (ölçümle doğrulandı — 39 distinct açığın
   fix'siz olan tek tanesi). Kırmızı doğan bir kapı iki hafta içinde `continue-on-error`
   olur. Bu yüzden sıra tersine çevrildi: **önce yamalar, sonra kapı.**
2. **Gerekçesiz ignore, ignore değil susturmadır.** Her satır kod-referanslı gerekçe ve
   tarih taşır; tarih geçince kapı kendi kendini kırmızıya çevirir.
3. **`--omit=dev` ayrımı olmadan npm sayısı yanıltıyor.** 22 açığın 12'si tarayıcıya hiç
   inmiyor. Aynı eşiği ikisine uygulamak, gerçek prod açığını gürültüde saklar.
4. **Kimlik doğrulama testsiz yükseltilmez.** PyJWT'nin tek tüketicisi 103 satırlık bir
   dosya ve sıfır testi var. Sıralamada 4. adımın ön koşulu bu yüzden konuldu.
5. **Çalışma zamanı yükseltmesi bir hijyen kalemi değil, yamalamanın ön koşulu.**
   Hedef sürümlerin hepsi zaten `>=3.10` istiyor; Node 20 EOL'ü **geçti** (planın
   "bugün EOL" ifadesi yanlış — 2026-04-30).
6. **Bu karar hiçbir bağımlılık dosyasını değiştirmedi.** Karar belgesi ile uygulamayı
   ayırmak, PyJWT/python-multipart gibi kalemlerin gece koşusunda gözetimsiz
   yükseltilmesini yapısal olarak engelliyor.

---

## Reddedilenler

- **"`pip-audit`'i olduğu gibi CI kapısı yap"** *(planın taslak hali)* — kapı ilk gün
  kırmızı doğar (fix'siz PyJWT açığı) ve devre dışı bırakılır.
- **Ignore listesini `ci.yml` içine gömmek** — gerekçesiz ve tarihsiz kalır; YAML'e gömülü
  bir `--ignore-vuln` bayrağı bir daha okunmaz. Ayrı, yorumlu, tarihli dosya seçildi.
- **`requirements.lock` / `pip-compile` / `uv lock` ile transitif kilitleme** — doğru yön
  ama bugünkü tek somut arıza (transitif körlük) "kur, sonra kurulu ortamı denetle" ile de
  kapanıyor; lock ayrı emek ve ayrı bir arıza yüzeyi (hash uyuşmazlığı). **Yeniden açma
  tetikleyicisi:** CI'ın çözdüğü sürümlerle prod imajının çözdüğü sürümlerin ayrıştığı
  kanıtlanırsa, ya da bir transitif regresyon yaşanırsa.
- **Dependabot / Renovate ile otomatik PR akışı** — `main` bugün korumasız ve `deploy.sh`'ta
  test kapısı yok (plan B.2). Otomatik yükseltme PR'ları bu düzende koruma değil, gürültü
  üretir. Önce kapı, sonra otomasyon.
- **`npm audit fix --force`** — vite 5 → 8 majörünü, dolayısıyla Node engine kısıtını
  sessizce içeri alır. Yalnız majör olmayan düzeltme uygulanır.
- **vite 8.2.2 (npm'in önerdiği hedef)** *(2026-08-22, G089)* — `lovable-tagger@1.1.11`
  peer'i `vite >=5.0.0 <8.0.0`; eklenti yalnız `mode === 'development'` altında yükleniyor
  ama peer çözümü yine de kırılır. **vite 7.3.6** de temiz ve elenmedi, yalnız ertelendi:
  aynı açıkları 6 da kapatıyor, majörü tek adım atmak tercih edildi. **Yeniden açma
  tetikleyicisi:** 6.x hattına yamasız yeni bir açık gelmesi, ya da `lovable-tagger`'ın
  düşmesi/peer aralığını genişletmesi.
- **`python:3.13-slim`** — `psycopg2-binary==2.9.9`'un cp313 tekerleği yok; çalışma zamanı
  işini bağımlılık işine bağlar. **Yeniden açma:** psycopg2-binary yükseltildikten sonra.
- **`node:22`** — LTS ama 2025-10-21'den beri bakım fazında; 24 ile aynı emeğe iki yıl daha
  uzun ömür alınıyor.
- **PyJWT'yi 2.12.0'da durdurmak** — `crit` açığını kapatır ama asıl ulaşılabilir olanı
  (kimlik doğrulaması öncesi sınırsız JWKS isteği) kapatmaz; hedef 2.13.0.
- **Hiçbir şey yapmamak / "10 kullanıcı, iç ağ"** — açıkların en az üçü kimlik doğrulaması
  **öncesinde** ulaşılabilir (PyJWT JWKS taşkını, python-multipart ayrıştırıcı DoS'ları) ve
  `/api` public host nginx'inin arkasında.

---

## İzleme ve kabul

- Uygulama işleri kuyruğa **bu sırayla** girer (K1 tablosu); her adım kendi bandında.
- 3, 4, 5 ve 6. adımlar prod imajını değiştirir → her biri için **hukukbot export duman
  testi** (bir belge → `export_outbox` pending → webhook/reconcile) kabul kriteridir.
- Kapılar (K3) yalnız 1–6 yeşile döndükten sonra açılır.
- **Test:** bu kayıt için yeni test yok (karar belgesi). Adım 4'ün ön koşulu olan
  `auth_verifier` karakterizasyon testi plan B.3 kapsamındadır.
- **İlgili:** [`docs/plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md`](../plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md) §3 (A.5/A.6),
  [`docs/mimari/deploy-ve-altyapi.md`](../mimari/deploy-ve-altyapi.md)

> **ŞERH (2026-08-14) — K5'teki "`react-router-dom` v6→v7 majörü GEREKMEZ" hükmü aşıldı;
> migrasyon yapıldı.** K5 satırı 2026-08-11 ölçümündeki advisory seti için doğruydu
> (`@remix-run/router` 1.23.3 transitif yaması yetiyordu). K1 adım 7'de (`431e384`)
> `audit-ignore.txt`'e tarihli girilen üç yeni kayıt — `GHSA-wrjc-x8rr-h8h6`,
> `GHSA-337j-9hxr-rhxg`, `GHSA-jjmj-jmhj-qwj2` — yalnız react-router 7.13+/7.18+ ile
> kapanıyor ve v6 hattına yama hiç yayımlanmadı ("Patched versions: None").
> 2026-08-14'te `react-router-dom ^6.30.1` → `react-router ^7.18.2` geçişi iki commit'le
> yapıldı (v6 future-flag ön adımı `262333c` + paket değişimi `eab6185`); üç ignore
> satırı silindi, `scripts/check-npm-audit.mjs` 0 bilinen açıkla yeşil.
