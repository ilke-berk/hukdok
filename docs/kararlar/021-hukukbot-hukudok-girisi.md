# 021 — Hukukbot'a tek giriş HUKDOK'tur: aynı access token, iç sayfa, `/hukukbot-api/` allowlist'i

**Tarih:** 26.09.2026 · **Karar veren:** kullanıcı (büro sahibi) · **Durum:** kabul — HUKDOK tarafı G203-G207,
Hukukbot tarafı G208 (`../hukukbot-ui`, hukbot `74b11b1` + `d02401c`); eski arayüzün silinmesi G209 (canlı
geçişten sonra)

## Bağlam

Hukukbot (hukuk sorularına RAG ile cevap veren ayrı uygulama, `../hukukbot-ui`) kendi React arayüzü, kendi MSAL
girişi ve kendi Azure uygulama kaydıyla ayrı bir sitede (hukbot.tragic.tr, host nginx → `:3000` frontend
konteyneri) yayındaydı. O Azure kaydı **tek kiracılıydı** (yalnız LexisBio): Hanyaloğlu Acar hesabıyla giriş
denenince hukbot'a girilemedi. HUKDOK ise iki kiracıyı zaten kabul ediyor (`ALLOWED_TENANTS`, karar 001,
[`mimari/kimlik-ve-token.md`](../mimari/kimlik-ve-token.md) §2).

## Karar

1. **Tek giriş HUKDOK.** Hukukbot'un kendi girişi, arayüzü ve Azure kaydı kalkar. Kullanıcı Hukukbot'u
   HUKDOK kabuğu içindeki `/hukukbot` sayfasından kullanır (`frontend/src/App.tsx` rotası, menüde "Araçlar →
   Hukukbot" iç bağlantı, `components/shell/Sidebar.tsx`).
2. **Aynı access token iki backend'de doğrulanır.** Sayfa Hukukbot'a HUKDOK'un MSAL access token'ını gönderir
   (`frontend/src/lib/hukukbotApi.ts` → `apiClient.fetch`; ID token değil). Hukukbot backend'i (`app/auth.py`)
   HUKDOK `backend/auth_verifier.py` kuralını birebir uygular: `tid ∈ ALLOWED_TENANTS` → kiracının JWKS'i →
   RS256, `aud` **yalnız** `api://<HUKDOK client id>` (çıplak client id reddedilir — ID token sızmasın), `iss`
   v2.0 (`login.microsoftonline.com/{tid}/v2.0`) ya da v1 (`sts.windows.net/{tid}/`), `exp` zorunlu, `scp`
   içinde `access_as_user`. Hukukbot env'i: `ALLOWED_TENANTS` + `HUKDOK_CLIENT_ID` (HUKDOK `AZURE_CLIENT_ID` ile
   aynı değer).
3. **API'ye tek yol konteyner nginx'inin allowlist'i.** Tarayıcı Hukukbot'a aynı origin'den
   `/hukukbot-api/(ask|sessions|download)` öneki ile ulaşır; önek atılıp `hukuk_shared` ağı üzerinden
   `hukukbot_api:8010`'a proxy'lenir (`nginx.conf`, G203). `/ingest` (API-key'li HUKDOK webhook'u), `/health` ve
   diğer her yol `return 404` — `/export` kuralının (karar 010) simetriği. `X-User-OID` başlığı proxy'de silinir
   (Hukukbot yalnız `DEV_AUTH_BYPASS`'ta okur). Upstream değişkenle ve Docker DNS'iyle (`resolver 127.0.0.11`)
   **gecikmeli** çözülür: Hukukbot stack'i kapalıyken HUKDOK nginx'i yine açılır, yalnız bu istekler 502 olur.
4. **Hukukbot'un kendi sitesi ve portu kalkar.** Yukarıdaki ayrı sitenin host nginx konfigi ve `:3000` frontend konteyneri
   kapanır; Hukukbot API'si yalnız `127.0.0.1:8010` + `hukuk_shared` ağında dinler. Sitenin sunucu konfig kopyası
   (`infra/nginx/sites-available/hukbot`) G207'de repodan kaldırıldı — VM yeniden kurulumunda geri gelmesin.
5. **Geçmiş korunur.** Hukukbot sohbetleri kullanıcı `oid`'i ile anahtarlıdır (`users.id = oid`). `oid` bir kişi
   için kiracı içinde sabittir, uygulama kaydından bağımsızdır → LexisBio kullanıcılarının eski hukbot girişiyle
   oluşmuş geçmişi yeni token'la aynen eşleşir. `sub`'a düşme kalktı (`sub` uygulamaya özgüdür, geçmişi bölerdi).

## Gerekçe

- Hanyaloğlu'nun girememesi bir Azure kayıt ayarı değil, iki ayrı kimlik adasının sonucuydu; HUKDOK'un iki
  kiracılı doğrulaması zaten üretimde sınanmış (G096 ölçümü) — aynı kuralı Hukukbot'a taşımak yeni bir güven
  sınırı açmaz.
- Tek giriş: kullanıcı iki kez oturum açmaz, iki idle/timeout davranışı yaşamaz, tek uygulama kaydı yönetilir.
- Allowlist'i konteyner nginx'inde tutmak Hukukbot'un iç uçlarını (özellikle `/ingest`) dış dünyadan yapısal
  olarak ayırır; bekçi `backend/tests/test_nginx_hukukbot.py`.

## Reddedilenler

- **Hanyaloğlu kullanıcılarını LexisBio kiracısına misafir (B2B guest) olarak davet etmek.** Her yeni avukat için
  elle Entra adımı; misafir hesabın `oid`'i ev kiracısındakinden farklıdır (geçmiş bölünür); HUKDOK'ta iki
  kiracının zaten doğrudan kabul edildiği gerçeğiyle çelişen ikinci bir kimlik modeli.
- **Hukukbot'u çok kiracılı kendi kaydıyla ayrı sitede bırakmak.** İkinci uygulama kaydı + ikinci giriş + ayrı
  TLS/DNS/sertifika bakımı; kiracı kısıtı `ALLOWED_TENANTS` yerine Entra'nın çok kiracılı kabulüne kalır (herhangi
  bir kiracı token alabilir, backend listesi tek kapı olur) — kazancı yok, yüzeyi büyük.
- **HUKDOK backend'i üzerinden proxy (`/api/hukukbot/...` → FastAPI → Hukukbot).** `/ask` uzun süren bir LLM
  NDJSON akışıdır; backend 2 uvicorn worker'la koşar (`UVICORN_WORKERS=2`, `docker-compose.yml`) ve belge işleme
  ile paylaşılan bu kapasiteyi akış süresince meşgul ederdi. Ayrıca Hukukbot'a kullanıcıyı "güvenilir iç başlıkla"
  (ör. `X-User-OID`) bildirmek gerekirdi — başlığa güvenen bir servis, başlığı sızdıran her yolda kimlik
  sahteciliğine açıktır. Nginx proxy'sinde her istek kendi token'ıyla doğrulanır, backend'e yük binmez.

## Açık konular

- **Canlı geçiş sırası (insan):** Hukukbot G208 → HUKDOK (G203-G207) → canlı duman (iki kiracıdan birer hesapla
  `/hukukbot`) → sunucu adımları ([`infra/README.md`](../../infra/README.md) "hukbot sitesinin kaldırılması") → G209.
  Eski hukbot arayüzü yeni kimlikle ÇALIŞMAZ; iki taraf aynı pencerede çıkar.
- **Hukukbot tarafı sağlamlaştırma (G208 denetimi):** `DEV_AUTH_BYPASS`'ın prod'da açılmasını engelleyen ikinci
  kapı yok (HUKDOK'taki `ENV` + `ALLOW_DEV_TENANT` + `DEV_MODE` üçlüsü gibi); `api` servisinin `.:/app`
  bind-mount'u prod'da kod-imaj ayrımını bozuyor.
- **401 bağı:** Hukukbot'un kurtarılamayan 401'i `apiClient`'ın oturum-bitti akışını tetikler (HUKDOK'tan da
  çıkış) — `hukukbotApi.ts`'in bilinçli tercihi; Hukukbot'ta `aud`/kiracı yanlış yapılandırılırsa belirti budur.
- Hukukbot'un eski Azure uygulama kaydının silinmesi ve DNS kaydı: G209 insan adımları.
