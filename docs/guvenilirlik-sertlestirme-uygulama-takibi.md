# Sertleştirme Uygulama Takibi (yaşayan dosya)

Ana plan: [guvenilirlik-sertlestirme-plani-2026-08-04.md](guvenilirlik-sertlestirme-plani-2026-08-04.md) — madde detayları ve gerekçeler orada. Bu dosya yalnız sırayı ve durumu tutar; her oturum sonunda güncellenir.

## Çalışma protokolü (her oturumda uy)

1. Oturum başında SADECE bu dosyayı + ana planın ilgili faz bölümünü oku. Denetim raporlarını ve eski planları açma.
2. Bir oturum = bir paket. Paket bitip context hâlâ rahatsa (≈%50 altı) sıradaki pakete geçilebilir.
3. Geniş keşif gerekirse Explore ajanına devret, ana oturuma özet dön. Büyük dosyaları (ör. `NewCase.tsx`, 1700 satır) bölüm bölüm oku.
4. Oturum sonunda: paketin kutusunu işaretle, "Durum notları"na TEK satır ekle, dokümanı kodla aynı commit'e koy.
5. Deploy'lar tablodaki deploy noktalarında; mesai dışı, öncesinde pg_dump, `--build` ile (frontend kuralı).
6. Test: backend pytest konteynerde (host py3.13 uyumsuz), frontend vitest host'ta. Dosya değişikliği daima Edit tool ile (PS5.1 UTF-8 tuzağı).

## Plandan düşülenler (2026-08-07 bağdaştırması — yeniden yapma)

- **Faz 1.5 gece yedeği:** 2026-08-05'ten beri canlı (systemd timer 03:30 TR, `pg_dump -Fc` → SharePoint; GCS yerine SharePoint varyantı). KALAN: script'ler repo'da değil, konteynere `docker cp` ile atılmış — recreate'te uçar → 1-B'de repo'ya alınacak.
- **"Faz 7 deploy bekliyor" notu:** geçersiz; Faz 7 + sertleştirme 2026-08-05'te prod'a çıktı (prod = main = 1c8ca71).
- **Container nginx 300 sn timeout:** repo'da ve prod'da (f72f13e). Host nginx config'i hâlâ sadece sunucuda → 1-B kapsamında.
- **Faz 3.5'in /commit 409 kullanıcı yüzü:** "henüz kaydedilmedi" bandı canlı (031e020, 1c8ca71). KALAN: idempotent çözümleme (409'da mevcut davayı bulup döndürme) — 3-D'de mevcut davranışı doğrulayıp üstüne kur.
- **Faz 3.8 Katman 1** (converter içi fallback + gerçek nedene göre hata mesajı): 2026-08-05'te kodlandı (e5df7b5) → 3-F yalnız Katman 2'yi yapar.
- **Faz 1 uvicorn `--workers 2` (2026-08-08 tespiti):** 1-A'da AÇILMADI — `PROCESS_CACHE`/`DOWNLOAD_CACHE` süreç içi bellekte (`routes/processing.py`); iki worker'da `/process`→`/confirm` ~%50 cache miss ile kırılır, ayrıca APScheduler günlük raporu + refresh thread'i duplike olur. Geçiş 3-E'ye taşındı; önkoşul: disk kalıcılığı + worker-tekil arkaplan işleri (lifespan `init_db` dahil).

## Paketler

Paketler dosya kümesine göre gruplandı: aynı dosyalara dokunan maddeler aynı oturumda, tek okuma turu yetsin diye.

### FAZ 0 — Acil düzeltmeler → Deploy #1
- [x] **0-A** · madde 0.1, 0.2, 0.8, 0.9, 0.10 — `routes/processing.py` + `document_pipeline.py` çekirdeği (event-loop, session sızıntısı, task sızıntısı, cache owner, ek doğrulama); canlı eşzamanlılık dumanı Deploy #1 sırasında
- [x] **0-B** · madde 0.3, 0.4, 0.7 — `analyzer.py`, `gemini_client.py`, `pdf/pdf_utils.py` hata yolları (JSON decode, Gemini timeout, MAX_PDF_PAGES → `PdfPageLimitError`)
- [x] **0-C** · madde 0.5, 0.6 — `email_sender.py`: kill-switch onarımı (config + gönderim kapısı), ek limiti 3 MB + arşiv referanslı gövde notu; toplu pytest yeşil → **Deploy #1 YAPILDI (2026-08-08, prod=9f1b202)**

### FAZ 1 — İnfra/deploy repo'ya → Deploy #2
- [x] **1-A** · docker-compose sertleştirme (mem/log limitleri, healthcheck, depends_on) + migration'ı entrypoint'ten tek seferlik ayrı adıma al (`migrate.py`) + `api.py` import-time migration çağrısını kaldır + sığ `/healthz` (limiter.exempt); `--workers 2` bilinçli ERTELENDİ → 3-E (bkz. Plandan düşülenler)
- [x] **1-B** · `infra/` dizini: sunucudan (`ssh hukukoid`) host nginx config, net-watchdog + unit'ler, mem-watch, daemon.json, **yedekleme script+timer** çekilip repo'ya alındı + idempotent `install.sh` (sunucuda HENÜZ koşmadı — 1-C provasında)
- [ ] **1-C** · `deploy.sh` yeniden yazımı (build→up, ff-only, imaj etiketleme, rollback.sh, deploy öncesi pg_dump, gerçek /healthz kapısı) + sunucuda elle prova → **Deploy #2**

### FAZ 2 — Monitoring ve alarm → Deploy #3
- [ ] **2-A** · derin `/healthz` endpoint'i + container nginx `location` + compose healthcheck bağlantısı + GCP uptime check'i /healthz'e çevir
- [ ] **2-B** · loglama: 11 modüldeki `basicConfig` → tek `dictConfig`, JSON formatter, request-id middleware
- [ ] **2-C** · GCP log tabanlı alarmlar (ERROR oranı, OOMKilled, watchdog KRITIK) + frontend hata beacon'ı (`/api/client-error`) + `CaseDocument.upload_status` migration → **Deploy #3**

### FAZ 3 — Dayanıklılık → Deploy #4 ve #5
- [ ] **3-A** · SharePoint yükleme outbox/retry kuyruğu (`export_publisher.py` deseni) [3.1] — büyük paket, tek başına
- [ ] **3-B** · Graph retry: paylaşılan Session + urllib3.Retry + 401 token yenileme + chunk resume [3.2]
- [ ] **3-C** · Gemini retry sınıflandırıcı (kod bazlı) + finish_reason + deadline bütçesi + devre kesici [3.3] → **Deploy #4**
- [ ] **3-D** · ofis no atomik rezervasyon + `/confirm` idempotency anahtarı + `/commit` 409 idempotent çözümleme [3.4, 3.5]
- [ ] **3-E** · DB timeout/rollback'ler + PROCESS_CACHE disk kalıcılığı [3.6, 3.7] + uvicorn `--workers 2` geçişi (1-A'dan devir; önkoşullar: cache disk kalıcılığı + lifespan `init_db`/APScheduler/refresh-thread tekilleştirme)
- [ ] **3-F** · `conversion_pending` katmanı: orijinali kendi uzantısıyla sakla, gece retry, hukukbot export hariç tutma [3.8] → **Deploy #5**

### FAZ 4 — Frontend dayanıklılığı → Deploy #6 (--build!)
- [ ] **4-A** · `apiClient` timeout/retry + `/confirm` yanıtında `response.ok` önce + ErrorBoundary [4.1, 4.3, 4.4]
- [ ] **4-B** · hata ≠ boş veri (`useCases`/`useClients` banner, `getClientCaseSequence` fail-hard) + analiz "failed" terminal olayı (backend+frontend) [4.2, 4.6]
- [ ] **4-C** · taslak kalıcılığı (`NewCase.tsx`, `Index.tsx` + beforeunload) + logout storage temizliğini daraltma [4.5] → **Deploy #6**

### FAZ 5 — Limit merkezileştirme → Deploy #7
- [ ] **5-A** · `config/settings.py` (pydantic-settings) + limitlerin göçü + zaman bütçesi hizalaması (LO+GS ≤ nginx 300) [5.1, 5.2]
- [ ] **5-B** · HTTP durum kodu disiplini (503/409/404/400) + `/process` LLM çıktısına Pydantic şeması [5.3, 5.4] → **Deploy #7**

### FAZ 6 — AI-dostu repo (deploy gerekmez)
- [ ] **6-A** · repo kökü `CLAUDE.md` + `docs/` reorg (mimari/, plan/, arsiv/, kararlar/ + 30+ eski dosyanın taşınması)
- [ ] **6-B** · mimari doküman içerikleri + ADR'ler + modül üstü docstring'ler (subagent fan-out'a uygun) + proje skill'leri

## Durum notları (her oturum tek satır, en yeni üstte)

- 2026-08-08 (4): 1-B tamam — `infra/` kuruldu: host nginx (default=hukukoid.com 300s + hukbot), net-watchdog/mem-watch/db-backup unit+script'leri, daemon.json sunucudan birebir çekildi (11 dosya diff'le doğrulandı); `scripts/prod` → `infra/scripts`e taşındı, README envanter+yeni-VM önkoşulları+restore ile `infra/README.md`de; idempotent `install.sh` yazıldı ama sunucuda HENÜZ koşmadı (1-C provasında); `.gitattributes` LF kuralı; compose'a pg/fe `memswap_limit` (sunucu override'ıyla hizalı — override Deploy #2 sonrası kalkacak); 554 test konteynerde yeşil.
- 2026-08-08 (3): 1-A kodlandı — compose'a mem/log limitleri + backend `/healthz` healthcheck + frontend depends_on:healthy (lokalde doğrulandı: backend healthy olana dek frontend bekledi, limitler HostConfig'te 2g/512m/128m); migrasyon `migrate.py` ile entrypoint'te tek seferlik, api.py import-time çağrı kaldırıldı; `--workers 2` → 3-E'ye ertelendi (PROCESS_CACHE süreç içi); 554 test konteynerde yeşil (6 yeni `test_faz1_infra.py`); prod'a Deploy #2 ile gidecek.
- 2026-08-08 (2): Deploy #1 yapıldı — prod=9f1b202; yedek alındı (SharePoint'e de), backend imajı yeniden derlendi, başlangıç temiz, HTTP 200, mem_limit 2g + MALLOC_ARENA_MAX=2 korundu; `upload_db_backup.py` artık imajda (docker-cp kırılganlığı kapandı); GS eşzamanlılık kanıtı ilk gerçek büyük /confirm'de loglardan izlenecek.
- 2026-08-08: Faz 0 tamamı kodlandı (0-A/0-B/0-C, 10 madde); 548 test konteynerde yeşil (17'si yeni `test_faz0_hardening.py`); 0.9 owner kontrolü intake set/touch/pop noktalarına da işlendi; 0.6 davranış notu: limit aşan ek artık hata değil, e-posta arşiv referansıyla gidiyor; Deploy #1 mesai dışı bekliyor.
- 2026-08-07: Takip dosyası oluşturuldu, paketler tanımlandı; henüz paket başlamadı.
