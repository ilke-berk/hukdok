# HUKDOK

Hukuk bürosu belge otomasyonu ve dava takip platformu. Belge yüklenir, Gemini ile belge türü,
taraflar, esas numarası ve mahkeme çıkarılır, kullanıcı onaylar, belge PDF/A-2b'ye dönüştürülüp
SharePoint arşivine ve PostgreSQL'e yazılır, dava kartına bağlanır. Hanyaloğlu & Acar Hukuk
Bürosu'nda Mart 2026'dan beri üretimde kullanılmaktadır.

> **English.** HUKDOK is a document-automation and case-tracking platform for a law firm:
> upload a document → Gemini extracts type, parties, case number and court → user confirms →
> PDF/A-2b archive on SharePoint + PostgreSQL record → linked to the case card. FastAPI backend,
> React/TypeScript frontend, PostgreSQL, Docker; identity via Microsoft Entra ID. In production
> since March 2026.

## Ne yapar

- **Belge hattı:** yükle → NDJSON akışlı analiz → onay ekranı → idempotent `/confirm` →
  Ghostscript ile PDF/A-2b → SharePoint'e outbox kuyruğuyla yükleme → sorumlu avukata bildirim.
  127 kayıtlı belge türü; UDF (UYAP), Office, görüntü ve PDF girdileri.
- **Dava takibi:** dava kartları, taraflar, avukatlar, aşama kararları, esas numarası tarihçesi,
  duruşma takvimi, kanuni süre motoru (T-15/7/3/1 uyarıları), tarihli dava notları, hata bildirimi.
- **Raporlama:** doğal dilde istek → doğrulanmış rapor tanımı → önizleme → Excel/CSV; her koşu loglanır.
  AI asistan tanımı üretir, veriyi görmez; serbest SQL yoktur.
- **Veri teslim hattı:** veri ekibinden gelen Excel paketleri admin panelinden yüklenir, doğrulanır,
  kuru koşulur, kapı eşiklerinden geçer, yönetici "Uygula" der; kullanıcı düzenlemeleri korunur.
- **Yetki belgesi üretimi, sesli giriş (Gemini transkripsiyon), toplu yükleme tezgâhı.**
- **Kardeş servisler:** Hukukbot (arşiv üzerinde kaynak gösteren soru-cevap) ve Lexis (medikolegal
  rapor aracı) ayrı depolarda gelişir, ortak Docker ağı ve tek giriş noktası üzerinden entegre edilir.

## Mimari

```
tarayıcı ──HTTPS──► host nginx (443, TLS)
                        │
                        ▼
              konteyner nginx (:8080) ── SPA + /api, /process, /confirm proxy
                        │                      ├─ /hukukbot-api/* ──► hukukbot_api:8010 (ayrı stack)
                        ▼                      └─ /lexis-api/*    ──► lexis_api:8020   (ayrı stack)
              FastAPI backend (:8001, 2 uvicorn worker + lider kilidi)
                 ├─ PostgreSQL 15 (59 tablo, trigram arama, soft-delete, tam tarihçe)
                 ├─ Microsoft Graph: SharePoint arşivi (app-only) + e-posta
                 ├─ Google Gemini: belge analizi, intake, rapor asistanı, transkripsiyon
                 ├─ Ghostscript / LibreOffice / PyMuPDF: dönüşüm ve PDF/A
                 └─ APScheduler (lider worker): gece raporu, dönüşüm retry, süre/duruşma taraması
```

Bilinçli tasarım kararları `docs/kararlar/` altında kayıtlıdır (ADR). Öne çıkanlar: outbox +
webhook + reconcile ile dış aktarım, `process_id` anahtarlı idempotent onay, iki worker için
dosya kilidiyle tek lider, dedupe anahtarlı bildirimler, tüm konteyner portlarının loopback'e
sabitlenmesi, swap yasağı ve bellek sınırları.

## Teknoloji

| Katman | Teknoloji |
| --- | --- |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Pydantic 2, APScheduler, PyJWT, MSAL |
| Frontend | React 18, TypeScript, Vite, Tailwind, shadcn/ui, TanStack Query, React Router 7 |
| Veri | PostgreSQL 15, SharePoint (Microsoft Graph, app-only) |
| AI | Google Gemini (`google-genai`) |
| Kimlik | Microsoft Entra ID (MSAL, PKCE; backend JWKS/RS256 doğrulaması, tenant allowlist) |
| Altyapı | Docker Compose, iki katmanlı nginx, GCP VM, Let's Encrypt, systemd timer'ları, Cloud Logging alarmları |
| Kalite | pytest (~4.000 test), Vitest (~1.600 test), ruff, mypy, pip-audit; GitHub Actions CI |

## Depo düzeni

```
backend/      FastAPI uygulaması: routes/, services/, managers/, models.py, migrate.py, tests/
frontend/     React/Vite SPA: src/pages, src/components, src/lib; vitest testleri
docs/mimari/  yaşayan mimari dokümanları (koddan doğrulanır)
docs/kararlar/ mimari karar kayıtları (ADR)
docs/plan/    yürüyen planlar
infra/        sunucu birimleri: nginx, systemd, GCP izleme, kurulum betiği
deploy.sh     şema ve sağlık kapılı prod deploy; rollback.sh geri alma
```

## Çalıştırma

```bash
cp .env.example .env            # değerleri doldur
docker network create hukuk_shared
docker compose up -d            # postgres + backend + frontend → http://localhost:8080
```

Testler:

```bash
docker compose exec -T backend pip install -r requirements-dev.txt
docker compose exec -T backend python -m pytest
npm --prefix frontend test
```

Geliştirme ayrıntıları, tuzaklar ve komutlar için [`CLAUDE.md`](CLAUDE.md); mimari için
[`docs/mimari/genel-bakis.md`](docs/mimari/genel-bakis.md).

## Güvenlik ve veri

Depoda gerçek müvekkil, dava veya kişi verisi yoktur; `.env` ve veri dosyaları gitignore'dadır.
API anahtarlı `/export` uçları yalnızca iç Docker ağından erişilebilir, nginx'e açılmaz.
Üç konteyner portu da loopback'e bağlıdır; dışarıya açık tek kapı TLS sonlandıran host nginx'tir.

## Geliştirici

İlke Berk Kutluk — tasarım, geliştirme ve işletme. 2026.
