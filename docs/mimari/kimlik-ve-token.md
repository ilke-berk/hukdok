# Kimlik ve token — kullanıcı oturumu, backend doğrulama zinciri, Graph app-only akışı

Bu doküman HukuDok'taki iki ayrı kimlik akışını anlatır: **kullanıcının** tarayıcıdan
Azure AD (Entra ID) ile oturum açıp backend'e Bearer token taşıması ve **backend'in**
kendi başına (kullanıcıdan bağımsız) Microsoft Graph'a client-credentials ile gitmesi.
Her iddia koddan okunmuştur; dosya:satır atıfları bu commit'teki ağaca göredir.
Entra tarafında belirlenen süreler ise **koddan okunamaz** — o kalemler ayrı ve açıkça
"teyit edilmedi" diye işaretlidir (bkz. §3).

Kısa harita: tenant modeli (paylaşımlı havuz, `tenant_id IS NULL`) burada değil,
[`genel-bakis.md` §4](genel-bakis.md#4-kimlik-ve-tenant)'tedir; Graph/SharePoint'in
retry ve chunk mekaniği [`dis-bagimliliklar.md` §2](dis-bagimliliklar.md)'dedir.

## 1. Kullanıcı akışı (tarayıcı → Azure AD → backend)

### 1.1 MSAL yapılandırması

`frontend/src/config/msalConfig.ts`:

| Ayar | Değer | Satır |
| --- | --- | --- |
| `clientId` | `VITE_AZURE_CLIENT_ID` | `:11` |
| `authority` | `https://login.microsoftonline.com/${VITE_AZURE_TENANT_ID}` (tek tenant authority; çok-tenant kabulü backend `ALLOWED_TENANTS` ile, §2) | `:12` |
| `redirectUri` | `window.location.origin` | `:13` |
| `cache.cacheLocation` | `"sessionStorage"` — token'lar **sekme ömrüyle** sınırlı; sekme/pencere kapanınca uçar, yeni sekme yeni giriş ister | `:16` |
| istenen scope | `api://<client_id>/access_as_user` (`loginRequest.scopes`) | `:28-31` |

Kütüphane `@azure/msal-browser ^5.1.0` + `@azure/msal-react ^5.0.3`
(`frontend/package.json:15-16`). MSAL Browser'ın redirect akışı Authorization Code + PKCE'dir;
konfigürasyonda implicit akışı açan bir ayar yoktur (`msalConfig.ts` tamamı 31 satır).

### 1.2 Açılış ve giriş

- `App.tsx:133-160`: uygulama `msalInstance.initialize()` → `handleRedirectPromise()`
  koşar; redirect yanıtı varsa `setActiveAccount(response.account)`, yoksa
  sessionStorage'daki ilk hesap aktif yapılır. MSAL hazır olana dek "Yükleniyor…"
  ekranı (`App.tsx:186-196`).
- Giriş `pages/Login.tsx:43`: `instance.loginRedirect(loginRequest)`. Zaten hesap varsa
  `/`'e yönlendirir (`Login.tsx:32-37`).
- Rota koruması `components/ProtectedRoute.tsx:9-22`: **yalnız** `accounts.length > 0`
  bakar; hesap yoksa `/login`. Token geçerliliği burada DEĞİL, her API isteğinde
  (§1.3) sınanır.
- Admin rotası `components/ProtectedAdminRoute.tsx:10-40`: hesap yoksa `/login`,
  `useIsAdmin()` false ise `/`. Kararı backend verir (`GET /api/config/is_admin`, §2.3).

### 1.3 Her API isteği (`frontend/src/lib/api.ts`)

1. `getAuthToken()` (`:22-47`): aktif hesap (yoksa ilk hesap) ile
   `acquireTokenSilent({...loginRequest, account, forceRefresh})`; dönen
   **`accessToken`** gönderilir, idToken değil (`:40-42`).
2. Token alınamazsa (hesap yok / sessiz yenileme tutmadı) **ağa çıkılmaz**: oturum-bitti
   dalı koşar ve çağırana sentetik `401 Response` döner (`:163-172`, G095).
3. `Authorization: Bearer <token>` (`:176`).
4. Yanıt 401 ise `getAuthToken(true)` (forceRefresh) ile **bir kez** taze token alınır;
   token gerçekten değiştiyse istek **bir kez** tekrarlanır (`:250-258`).
5. Hâlâ 401 → `handleSessionExpired()` (`:119-149`): önce `SESSION_EXPIRED_EVENT`
   (`"hukdok:session-expired"`, `:19`) yayınlanır (sihirbaz taslağını sessionStorage'a
   flush etmesi için), `_isLoggingOut` bekçisiyle tek seferlik toast + 500 ms sonra
   `msalInstance.logoutRedirect({ postLogoutRedirectUri: origin + '/login' })` (`:141-143`).

### 1.4 Oturum kapanış yolları

| Yol | Tetikleyici | Hedef | Kaynak |
| --- | --- | --- | --- |
| Oturum süresi doldu | yenileme sonrası da 401 ya da token hiç alınamadı | `logoutRedirect` → `/login` | `lib/api.ts:141-143` |
| Idle timeout | 30 dk etkinlik yok (uyarı 25. dakikada) | `logoutRedirect` → `/login` | `hooks/useIdleTimeout.ts:36-38`, `App.tsx:43` |
| Sekme kapanışı | sessionStorage temizlenir; Entra tarafındaki SSO çerezi ayrı bir şeydir, dokunulmaz | — | `msalConfig.ts:16` |

Her iki `logoutRedirect` hedefi `window.location.origin + '/login'` (BrowserRouter rotası;
hash fragment'li eski hedef G095'te düzeltildi — `useIdleTimeout.ts:34-35`, `api.ts:140`).

## 2. Backend doğrulama zinciri (`backend/auth_verifier.py`)

`dependencies.get_current_user` (`dependencies.py:55-68`) `HTTPBearer(auto_error=True)`
ile başlığı alır ve `AuthVerifier.verify_token` çağırır; `None` dönerse `401 Invalid token`.
`get_current_tenant` (`dependencies.py:71-76`) claim'lerdeki `tid`'i döndürür, yoksa 403.
**Durum tutulmaz: sunucu tarafı oturum/session yoktur**, her istek token'ıyla kendi
başına doğrulanır.

`verify_token` adımları (`auth_verifier.py:61-142`):

| # | Adım | Satır | Başarısızlıkta |
| --- | --- | --- | --- |
| 1 | İmzasız decode (`verify_signature: False`) — yalnız `tid` okumak için | `:72-73` | — |
| 2 | Dev bypass: **üç env birden** (`ENV=development` + `ALLOW_DEV_TENANT=true` + `DEV_MODE=true`) ve `tid == "dev-tenant"` ise imzasız claim'ler kabul (WARNING) | `:84-88` | prod'da kapalı (§2.2) |
| 3 | `tid ∈ ALLOWED_TENANTS` (env, virgülle ayrık) | `:76-78`, `:92-94` | `None` → 401 |
| 4 | Tenant'ın JWKS'i: `https://login.microsoftonline.com/{tid}/discovery/v2.0/keys`, `PyJWKClient` tenant başına cache'lenir | `:97-103` | — |
| 5 | `AZURE_CLIENT_ID` env şart | `:109-112` | ERROR + `None` |
| 6 | `jwt.decode`: **RS256** imza + `aud ∈ {client_id, api://client_id}` + `iss ∈ {login.microsoftonline.com/{tid}/v2.0, sts.windows.net/{tid}/}` + `exp` | `:114-130`, `_expected_issuers` `:24-35` | `ExpiredSignatureError` → WARNING; diğer `InvalidTokenError` → ERROR; `None` → 401 |
| 7 | G092 gözlem (davranışsız): `scp`'de `access_as_user` yoksa ya da `aud` çıplak client_id ise süreç başına **bir kez** WARNING — token yine kabul | `_observe_scope_audience` `:38-58`, `:132` | — |

Issuer'ın iki biçimi birden kabul edilir çünkü hangisinin geleceği app registration'daki
`accessTokenAcceptedVersion`'a bağlıdır ve repodan bilinemez (`:27-30`). `scp`/`aud`
gözlemi faz 2 (zorlama) için ölçüm verisidir; §6'da açık kalem.

Kullanıcı kimliği claim'lerden **üçlü fallback** ile okunur:
`preferred_username | upn | email` (`auth_verifier.py:149`, `routes/config.py:55,65`).

### 2.1 Token'ı kim, nerede kullanır

Tüm korumalı route'lar `Depends(get_current_user)` ya da ondan türeyen
`get_current_tenant`/`require_admin` alır. Tenant filtresi (`tenant_id == tid OR IS NULL`)
`auth_helpers.py`'de; karar kaydı
[`kararlar/001-tenant-ortak-havuz.md`](../kararlar/001-tenant-ortak-havuz.md).

### 2.2 DEV_MODE guard'ları (G5 + G093)

`api.py` lifespan'i açılışta iki yönü de kollar, ikisi de **yalnız CRITICAL log basar,
uygulamayı düşürmez**:

- `ENV=development + ALLOW_DEV_TENANT=true` ama `DEV_MODE` true değil → bypass devre
  dışı, muhtemel yanlış konfig (`api.py:120-127`).
- `warn_if_dev_mode_outside_development` (`api.py:93-115`, çağrı `:130`): `DEV_MODE=true`
  ama `ENV != development` → CORS `allow_origin_regex=".*"` + `allow_credentials=True`
  açık (`api.py:316-322`), prod'da tehlikeli.

### 2.3 Admin kapısı

`routes/config.py:49-56`: `ADMIN_EMAILS` env (virgülle ayrık, küçük harfe normalize)
— `require_admin` e-posta listede değilse `403 Yönetici yetkisi gerekli`.
`GET /api/config/is_admin` (`:63-66`) aynı kümeye bakar; frontend `ProtectedAdminRoute`
bunu kullanır. Yetki modeli bundan ibarettir: **tenant üyeliği = tam kullanıcı erişimi,
ADMIN_EMAILS = yönetim uçları**; rol/grup claim'i okunmaz (§6).

## 3. Süre tablosu

### 3.1 Koddan okunan (doğrulanmış)

| Kalem | Değer | Kaynak |
| --- | --- | --- |
| Idle timeout | 30 dk | `App.tsx:43` `useIdleTimeout(30, 5)`; hook `useIdleTimeout.ts:14,20` |
| Idle uyarısı | çıkıştan 5 dk önce (25. dk), "Devam Et" aksiyonu sayacı sıfırlar | `useIdleTimeout.ts:21,41-55` |
| Etkinlik sayılan olaylar | mousedown, mousemove, keypress, scroll, touchstart, click | `useIdleTimeout.ts:72-79` |
| Token cache ömrü | sekme/pencere ömrü (sessionStorage) | `msalConfig.ts:16` |
| 401 sonrası tekrar | 1 forceRefresh + 1 tekrar istek | `api.ts:250-258` |
| Oturum-bitti toast → redirect | 500 ms | `api.ts:139-147` |
| Backend `exp` kontrolü | `verify_exp: True` — süresi dolan token reddedilir, pay (leeway) verilmez | `auth_verifier.py:128` |
| Graph token yeniden deneme | 2 deneme, arada 5 s | `auth_graph.py:138-149` |

### 3.2 Entra tarafında belirlenen — **TEYİT EDİLMEDİ**

Aşağıdaki değerler Microsoft'un **yayımlanmış varsayılanlarıdır**; bu tenant'ta
değiştirilip değiştirilmediği repodan okunamaz ve **doğrulanmamıştır**. Kesin değer
gibi alıntılanmamalı.

| Kalem | Entra varsayılanı (teyit edilmedi) | Nerede teyit edilir |
| --- | --- | --- |
| Access token ömrü | ~60-90 dk | Entra admin center → app registration / token lifetime policy |
| SPA refresh token tavanı | 24 saat (SPA'larda sessiz yenileme bu tavana kadar; sonra etkileşimli giriş) | Entra admin center → token lifetime; Conditional Access "sign-in frequency" |
| SSO çerezi / oturum kalıcılığı | tenant politikası | Conditional Access → session controls |

Teyit kullanıcıya ait bir adımdır; teyit edildiğinde bu tablo güncellenir ve
"teyit edilmedi" işareti düşer.

Pratik sonuç (kod + varsayılan birlikte okununca): uzun bir belge inceleme sırasında
access token düşse de `api.ts` 401 yakalayıp sessizce yeniler; kullanıcı yalnız refresh
token tavanına çarpınca ya da 30 dk hareketsiz kalınca `/login`'e döner.

## 4. Backend → Graph: ayrı, app-only akış (`backend/sharepoint/auth_graph.py`)

Kullanıcı oturumundan **tamamen bağımsızdır**; kullanıcı token'ı Graph'a hiç gitmez.

- `msal.ConfidentialClientApplication(client_id, authority=login.microsoftonline.com/{SHAREPOINT_TENANT_ID}, client_credential=secret)` (`:102-108`); secret önce `vault`, yoksa env (`:93-95`). Uygulama nesnesi süreç-içi `_MSAL_APPS` sözlüğünde cache'lenir (`:15`, `:110`).
- `get_graph_token(config_type, force_refresh)` (`:115-153`): scope
  `https://graph.microsoft.com/.default`; MSAL kendi token cache'inden döndürür, başarı
  `health.record_graph_token_ok()` ile `/healthz`'e yansır (`:143-146`).
- `force_refresh=True`: `remove_tokens_for_client()` ile cache düşürülür (eski msal'da app
  nesnesi atılıp yeniden kurulur) (`:126-135`). Çağıran: uploader'daki
  `_with_fresh_token_on_401` — ilk Graph 401'inde token zorla yenilenip **bir kez** daha
  denenir (`sharepoint_uploader_graph.py:102-117`).
- Python bağımlılıkları: `msal==1.37.0`, `PyJWT==2.13.0`, `cryptography==50.0.0`
  (`backend/requirements.txt:7,20,21`).

**Secret ömrü uyarısı (G093):** `check_client_secret_expiry` (`auth_graph.py:25-65`)
lifespan'de bir kez koşar (`api.py:131-132`). `SHAREPOINT_CLIENT_SECRET_EXPIRES_AT`
(ISO tarih, `.env.example:15`) tanımsızsa sessiz; kalan gün ≤ 30 (`SECRET_EXPIRY_WARN_DAYS`,
`:21`) → WARNING; tarih geçmişse → CRITICAL; ayrıştırılamazsa bir kez WARNING. Secret'ın
kendisi fonksiyona girmez, `/healthz`'e bilinçli eklenmez (`:34-36`). Bu env'i doldurmak
operatörün işidir; boşken secret ömrü **hiçbir yerde izlenmez**.

## 5. Kapı gibi görünen ama kapı OLMAYAN: `ALLOWED_DOMAINS`

`pages/Login.tsx:9-12`'deki `ALLOWED_DOMAINS` sabiti (`@hanyaloglu-acar.av.tr`,
`@lexisbio.onmicrosoft.com`) repoda **yalnız iki yerde** geçer: tanımı ve giriş ekranındaki
"Yetkili Erişim" kutusunda metin olarak listelenmesi (`Login.tsx:191-195`). Ne
`loginRequest`'e girer, ne `handleRedirectPromise` sonrası kontrol edilir, ne backend'e
ulaşır (`grep -rn ALLOWED_DOMAINS frontend/src backend` → yalnız `Login.tsx:9` ve `:191`).
Kutudaki "diğer hesaplar otomatik reddedilir" cümlesi de bu listeye değil Entra'ya
dayanır.

**Gerçek kapılar:**

1. Azure AD app registration (hangi tenant/hesapların bu uygulamaya giriş yapabildiği —
   Entra tarafı, repoda değil).
2. Backend `ALLOWED_TENANTS` allowlist'i (`auth_verifier.py:76-94`) — `tid` listede
   değilse token reddedilir.
3. Yönetim uçları için `ADMIN_EMAILS` (§2.3).

Yani "e-posta domain kısıtımız var" doğru DEĞİLDİR; kısıt tenant düzeyindedir.

## 6. Bilinen açık kalemler (envanter — çözüm iddiası değil)

| Kalem | Durum | Kaynak |
| --- | --- | --- |
| CSP zorlayıcı değil | Konteyner nginx yalnız `Content-Security-Policy-Report-Only` basar (`nginx.conf:54`, G091). Zorlayıcıya geçişin ön koşulu insan turuyla toplanan ihlal listesi — [`deploy-ve-altyapi.md` §11](deploy-ve-altyapi.md#11-konteyner-nginx-güvenlik-başlıkları-g091) | açık |
| `scp` zorunluluğu + audience daraltma | G092 **gözlem modunda** bıraktı: `access_as_user` eksik ya da `aud` çıplak client_id ise yalnız WARNING, token kabul (`auth_verifier.py:38-58`). Zorlama faz 2, ayrı görev | açık |
| Token iptali gecikmesi | CAE (Continuous Access Evaluation) yok; verilmiş access token `exp`'e kadar backend'de geçerli. Azaltıcılar: idle timeout (30 dk) ve refresh token tavanı (§3.2, teyit edilmedi) | açık |
| Yetkilendirme granülaritesi | Tenant üyeliği = tam erişim; rol/grup claim'i okunmaz; tek ayrım `ADMIN_EMAILS` | açık |
| Entra süre politikaları | §3.2'deki değerler tenant'ta teyit edilmedi | kullanıcı adımı |
| Secret ömrü izleme | yalnız `SHAREPOINT_CLIENT_SECRET_EXPIRES_AT` dolduysa çalışır; boşsa kör | operatör adımı |
