# Açık İşler Bitirme Planı (2026-08-01)

Kendi kendine yeten kickoff dokümanı: yeni oturum bu dosyayla başlayabilir.
Ana plan: [otonom-dava-acma-gelistirme-plani-2026-07-24.md](otonom-dava-acma-gelistirme-plani-2026-07-24.md)
(faz tanımları orada; bu doküman kalan işleri sıralar ve günceller).

## Durum (2026-08-01 itibarıyla)

Prod `b395873`'te. Canlıda: otonom dava açma Faz 0+2+3+4+5 (sihirbaz),
anket açılış fazları (judicial_unit, DANIŞ-kapılı zorunlu alanlar,
check-duplicate), sihirbaza .eml desteği (expand-eml; gerçek Quick/Maher
maili ile uçtan uca doğrulandı). Deploy öncesi DB yedeği:
`~/hukdok-backup-pre-eml-20260801-1526.sql.gz`.

**2026-08-01 akşam güncellemesi:** Faz 6 TAMAMEN bitti — 6.1+6.3
(`5ffb95a`), 6.2 (`a7e0064`), 6.4 (`3630c24`, karar: service_type kalıcı +
düzenlenebilir) main'de, deploy bekliyor. Backend 467 pytest + frontend
114 vitest yeşil, tsc temiz. **Adım 0 KOŞULDU:** backfill_judicial_unit
prod'da uygulandı — 13.594 kayıt dolduruldu, 33 eşleşmeyen (%0,24; serbest
metin/yazım hatası, kalıp düzeltmesi gereksiz), 751 mahkeme adı boş.
**Faz 6 PROD'DA CANLI (2026-08-01 ~20:30, f67b615):** bundle + ff-merge,
öncesinde pg_dump (`~/hukdok-backup-pre-faz6-20260801-1728.sql.gz`).
Doğrulandı: konteynerler ayakta, backend startup temiz, yeni bundle'da
intake-draft var, analyze/keepalive 405 + client-sequence 403, site 200.
**Adım 2 (Faz 1) TAMAM (2026-08-01 gece):** CaseTrackingPanel panel geneli
tek taslak (`lib/trackingDraft.ts` saf modül) + tek Kaydet + kaydedilmemiş
rozeti; `handleStageClick` taslağı sıfırlamıyor, refresh/aşama geçişinde
dirty alanlar `rebaseDraft` ile korunuyor. Aşama geçişi (confirmStage)
dialog onaylı ve anlık kaldı. Ayrılma koruması: `beforeunload` + CaseDetails
sekme değişiminde confirm (`onDirtyChange` prop). Backend: route
`model_dump(exclude_unset=True)`, manager `tracking_changes` — gönderilmeyen
alan dokunulmaz, null gönderilen SİLİNİR. Testler: backend 475 pytest +
frontend 126 vitest yeşil, tsc/mypy/ruff temiz.
**Faz 1 PROD'DA CANLI (2026-08-01 ~21:00, 9f08513):** 821e0fa + 9f08513
bundle + ff-merge ile çıktı, öncesinde pg_dump
(`~/hukdok-backup-pre-faz1-20260801-1758.sql.gz`). Doğrulandı: konteynerler
ayakta, backend startup temiz, site yeni bundle'ı servis ediyor
(Faz 1 işareti bundle'da), tracking PATCH authsuz 401.
**Adım 3 (Faz 7 — zenginleştirme modu) KODU TAMAM (2026-08-02):** karar
noktaları kullanıcı onayıyla plan önerileri yönünde kapandı — (1) ayrı
`POST /api/case-intake/apply`, (2) CaseHistory imzası `changed_by` (kullanıcı)
+ `source` ("intake-enrich: <belge adı>"; `case_history`'ye iki kolon eklendi,
bildirimsel migration #20), (3) sessiz `_auto_enrich`/`_auto_status` kalır,
artık imzalı CaseHistory yazar (tam taşıma v2). Uygulanan: merge'e opsiyonel
`case_id` (kayıtlı dava değerleri "kayıtlı dava" kaynaklı aday; alan başına
fill/confirm/conflict/keep; esas_no/mahkeme farkı Katman 3 hakeme gider;
taraflar mevcutlarla TC/normalize-ad eşlenir), `case_manager.enrich_case`
(exclude_unset kısmi güncelleme + yalnız-EKLEME taraf + imzalı history),
apply endpoint'i commit'in belge-başı best-effort arşiv + poliçe yardımcılarını
paylaşır (refactor: `_archive_intake_documents` / `_feed_intake_policies`).
UI: dava detayında "Belgeden Doldur / Teyit Et" (`/new-case/auto?enrichCase=`),
duplicate uyarısında "Bu davayı zenginleştir →" köprüsü, review enrich modunda
fark listesi (teyitler çipe katlanır; ofis no / hizmet türü / avukat blokları
gizli; tik = UYGULA), sonuç ekranında uygulanan değişiklik listesi.
Test: backend 501 pytest (26 yeni: `test_case_intake_enrich.py`) + frontend
138 vitest (12 yeni: `intakeEnrich.test.ts`), tsc/ruff/mypy temiz. Duman
(lokal Docker): migration kolonları doğrulandı; `enrich_case` gerçek DB'de
doldur + idempotens + ünvan-eşitlemeli taraf dedupe + imzalı history geçti;
apply route'u openapi'de. Kalan: canlı benzeri UI dumanı (gerçek tensip +
mevcut dava, tarayıcıdan) + prod deploy.

## Sıralama ve gerekçe

| Adım | İş | Efor | Neden bu sırada |
|---|---|---|---|
| 0 | `backfill_judicial_unit` prod koşusu | 10 dk (kullanıcı) | Hazır script, veri bekliyor |
| 1 | Faz 6 — sertleştirme paketi | 1.5–2 g | 6.1 Faz 7'nin ÖNKOŞULU; oturum kaybı canlı sihirbazın bilinen riski |
| 2 | Faz 1 — takip paneli tek-Kaydet | 1–1.5 g | Bağımsız, anında UX kazanımı; Adım 1 ile yer değiştirebilir |
| 3 | Faz 7 — zenginleştirme modu | 2–3 g | Önkoşulu (6.1) Adım 1'de kapanır; başlamadan 3 karar noktası kullanıcıya |
| 4 (ops.) | .eml Faz 2 | ~1 g | Değer kanıtlandıktan sonra konfor iyileştirmesi |

Toplam (Adım 1–3): **~5–6.5 gün**; Adım 4 ile ~7.5 gün.
Her adım bağımsız deploy edilebilir (standart: bundle + `docker compose up -d --build`, mesai dışı).

## Adım 0 — backfill_judicial_unit prod koşusu (kullanıcıda)

```bash
docker exec hukdok_backend python scripts/backfill_judicial_unit.py          # kuru
docker exec hukdok_backend python scripts/backfill_judicial_unit.py --apply  # yaz
```
Yalnız boş `judicial_unit`'e yazar, tekrar koşması güvenli. Kuru çıktıda
"Eşleşmeyen" listesi büyükse (ör. >%10) apply öncesi kalıplara bakılır
(`services/judicial_unit.py` PATTERNS — backfill ile sihirbaz aynı modülü
kullanır, kalıp düzeltmesi ikisini birden iyileştirir).

## Adım 1 — Faz 6: Sertleştirme paketi

Dört kalem; 6.1 + 6.2 aynı deploy'da, 6.3 + 6.4 küçük ve fırsatçı.

### 6.1 `update_case` taraf öksüzleşmesi düzeltmesi (Faz 7 önkoşulu)

Bugün `update_case` tarafları sil-yeniden-oluştur yapıyor → `case_party_id`'ye
bağlı kayıtlar (belge-taraf bağı) öksüzleşiyor. Çözüm (ana plan İK 4.1):
diff bazlı güncelleme — gelen taraf listesi mevcutla normalize ada (+tc_no)
göre eşlenir; eşleşen satır UPDATE, yeni satır INSERT, kalkan satır DELETE.
Eşleşme anahtarı `party_check.normalize_party_key` (kurumsal ünvan
normalizasyonu dahil — A.Ş./ANONİM ŞİRKETİ). Test: `tests/test_cases_update.py`
(yeni) — taraf değişmeden alan güncelle → party id'leri SABİT kalmalı;
taraf ekle/sil/rol değiştir senaryoları.

### 6.2 Sihirbaz oturum kaybı (Faz 5'in bilinen açığı)

30+ dk review'da Azure oturumu düşünce sihirbaz durumu kayboluyor. İki katman:
1. **MSAL sessiz yenileme:** `apiClient.fetch` 401'inde `acquireTokenSilent`
   → tek tekrar; olmuyorsa redirect öncesi taslak kaydet.
2. **Taslak dayanıklılığı:** review form durumu (alan onayları, taraflar,
   poliçe seçimi) `sessionStorage`'a debounce'lu yazılır; sihirbaz açılışında
   "yarım kalan taslak bulundu — devam et / at" teklifi. DİKKAT: process_id'ler
   PROCESS_CACHE TTL'ine (30 dk, keepalive'lı) bağlı — taslak restore'unda
   keepalive sonucu expired dönen belgeler listede "yeniden yükle" işaretlenir.
KVKK notu: sessionStorage sekme kapanınca ölür, kalıcı localStorage KULLANILMAZ.
Test: vitest — taslak serialize/restore reducer'ı; elle senaryo: token süresi
kısaltılarak (env) redirect dönüşünde taslağın geri gelmesi.

### 6.3 client-sequence fallback / 409 telemetrisi

Bilinen bug (2026-07-16 kaydı): ofis no önerisi client-sequence COUNT tabanlı —
silinen/eşleşmeyen kayıtlarda dolu numara önerip 409/UniqueViolation üretiyor.
Çözüm: COUNT yerine mevcut numaralardan max+1 (aynı prefix içinde); 409
yakalandığında TechnicalLogger'a `TRACKING_NO_COLLISION` olayı (telemetri).
Test: `test_case_duplicate.py`'ye komşu — araya silinmiş kayıtla öneri
çakışmamalı.

### 6.4 `service_type` kararı (kullanıcıya tek soru)

Persist mi, formdan kaldırma mı? Karar "kaldır" ise: form alanı + şema alanı
temizliği tek küçük commit.

## Adım 2 — Faz 1: CaseTrackingPanel tek-Kaydet

Ana plan İş Kalemi 3 aynen (dosyalar: `CaseTrackingPanel.tsx`,
`case_manager.update_case_tracking`, `routes/cases.py`):
1. Üç kayıt yolu → tüm aşamaların STAGE_FIELDS'ı + `dosya_son_durumu`'nu
   kapsayan TEK taslak; panel-geneli tek "Kaydet" + kaydedilmemiş rozeti.
   `handleStageClick` taslağı sıfırlamaz (mevcut veri kaybı bug'ı kapanır).
2. Aşama geçişi (`confirmStage`) istisna: dialog onaylı, anlık (CaseStageLog
   olayı).
3. Ayrılma koruması: `beforeunload` + panel içi sekme/aşama değişiminde confirm.
4. Backend: `update_case_tracking` `exclude_unset` semantiği — alan SİLME
   (null yazma) çalışır olur.
Test: pytest (exclude_unset: gönderilmeyen alan dokunulmaz, null gönderilen
silinir) + vitest (taslak reducer) + elle UI (aşamalar arası veri kaybolmaz,
tarih sil+kaydet → DB null).

## Adım 3 — Faz 7: Zenginleştirme modu (İş Kalemi 5)

Tasarım ana planda hazır (İK 5); özet: `/analyze` değişmez; `/merge`'e
opsiyonel `case_id` → alan başına `fill` / `confirm` / `conflict` durumu
(mevcut dava değerleri "kayıtlı dava" kaynaklı aday olarak katılır; taraflarda
yalnız EKLEME); yeni ince `POST /api/case-intake/apply` — tik'lenen alanların
kısmi güncellemesi (`exclude_unset`) + `CaseHistory` + taraf ekleme + commit'in
belge-başı best-effort arşiv döngüsü + poliçe beslemesi. UI: dava detayına
"Belgeden Doldur / Teyit Et"; sihirbazın `duplicate_case` uyarısından
"bu davayı zenginleştir" köprüsü; review bileşenleri (IntakeFieldRow, tik
kapısı) "mevcut dava" modunda yeniden kullanılır.

**Başlamadan kullanıcıyla netleşecek 3 karar** (ana plan İK 5 karar noktaları):
1. Ayrı `apply` endpoint'i mi, `commit`'e `mode=enrich` mi? (öneri: ayrı)
2. `CaseHistory` kaynak imzası: "intake-enrich: <belge adı>" yeterli mi?
3. Mevcut sessiz `_auto_enrich` davranışları kalsın mı? (öneri: kalsın,
   CaseHistory'ye yazsın; tam taşıma v2)

Test: merge case_id'li senaryolar (fill/confirm/conflict + hakem), apply
kısmi güncelleme + expired belge izolasyonu (commit test desenleri kopyalanır);
vitest: fark listesi reducer'ı. Duman: canlı benzeri lokalde gerçek tensip +
mevcut dava.

## Adım 4 (opsiyonel) — .eml Faz 2

Kapsam ([eml planındaki](eml-intake-gelistirme-plani-2026-08-01.md) ertelenenler):
1. `.msg` desteği — `extract-msg` bağımlılığı; expand-eml içinde format tespiti
   (OLE magic `D0 CF 11 E0` → .msg yolu), çıktı sözleşmesi AYNI kalır.
2. Orijinal `.eml`/`.msg`'in HAM arşive gitmesi (bugün atılıyor) — commit
   belgelerine `source_eml` iliştirme kararıyla birlikte.
3. Prompt notu: "Maher Holding = Quick Sigorta'nın operasyon şirketi" —
   duman testinde `sigorta_sirketi` gövdeden Maher çıktı, üst yazıdan Quick;
   tek satırlık kural aday karmaşasını azaltır.

Mailbox otomasyonu (Graph ile gelen kutusu izleme) bu planın DIŞINDA — ayrı
plan dokümanı ister; .eml hattı onun ön koşulunu üretmiş durumda.

## Çalışma kuralları (her adım için)

- Backend pytest KONTEYNERDE (host py3.13 uyumsuz), frontend vitest host'ta.
- Dosya değişikliği daima Edit tool ile (PS5.1 Get/Set-Content Türkçe bozar).
- Deploy: commit → bundle → `ssh hukukoid` → pull → pg_dump yedek →
  `docker compose up -d --build`; sonrası endpoint + bundle + log doğrulaması.
- Bilinen ön-mevcut tsc hataları (AdminPage, NewCase, 2 dashboard) bu işlerin
  kapsamı dışında; build'i kırmıyor.
