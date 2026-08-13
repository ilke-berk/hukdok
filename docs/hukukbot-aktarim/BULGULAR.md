# Plan İncelemesi — Bulgular ve Düzeltme Önerileri

> [PLAN.md](PLAN.md)'deki aktarım planının hukdok koduna karşı incelenmesi (2026-07-06).
> Genel sonuç: mimari (export API + outbox + webhook + reconcile) sağlam; aşağıdaki
> düzeltmeler plana işlendi.

## Gerçek sorunlar

### 1. `after_id` cursor'ı async upload ile yarışıyor — belge sonsuza dek atlanabilir ⚠️ EN KRİTİK

**Sorun:** SharePoint upload'ı background task'te çalışır ve `sharepoint_url` DB'ye
upload bittikten *sonra* yazılır (`services/document_pipeline.py:249-330`,
`async_islenmis_upload`; yazım `:279`). Reconcile doğrudan `case_documents` tablosunu
`after_id` ile tararsa: id=100'ün upload'ı yavaş/retry'da, id=105 tamamlandı, cursor
105'i geçti → 100 hazır olduğunda cursor onu bir daha görmez. Belge sessizce kaybolur.

**Düzeltme:** `GET /export/documents` listesini ham belge tablosundan değil
**outbox tablosundan** servis et. Outbox satırı yalnızca "upload başarılı +
`webUrl` DB'ye yazıldı" anında oluştuğu için outbox `id` sırası = aktarılabilirlik
sırası olur; geç tamamlanan upload daha büyük outbox id'siyle listeye girer ve
yarış tamamen kaybolur. Webhook enqueue de aynı noktaya konur
(`document_pipeline.py:318-325`, `sharepoint_url` commit'inin hemen ardından).

**Ek kazanç:** Bu değişiklik #3'teki "başarısız upload listede görünmesin"
gereksinimini de bedavaya çözer.

**Güncel not (Faz 3-A, `services/upload_queue.py`):** yukarıdaki `async_islenmis_upload`
artık ASIL yol değil — kalıcı outbox/retry kuyruğu (`upload_queue.py`) asıl yol oldu,
`document_pipeline.py`'deki fire-and-forget fonksiyonlar kodun kendi docstring'inde
"Faz 3-A'dan beri yalnız fallback: asıl yol upload_queue outbox'ıdır" diye işaretli
(`document_pipeline.py:239,304`). Bu bulgunun asıl önerisi (outbox tabanlı liste)
zaten uygulandı; anlatı burada tarihsel bağlam olarak kalıyor.

### 2. `POST localhost:<hukukbot>` Docker'da çalışmaz

**Sorun:** Prod'da hukdok container içinde koşuyor (Docker Compose + container
nginx). Container içinden `localhost` container'ın kendisidir, host makine değil —
webhook hiçbir zaman hukukbot'a ulaşmaz.

**Düzeltme:** Hukukbot'u aynı compose network'üne al ve webhook URL'ini servis
adıyla kur: `http://hukukbot:<port>/ingest/hukdok`. Compose'a alınamıyorsa
`host.docker.internal` (Windows/Mac) veya `extra_hosts: host-gateway` (Linux)
kullan. Faz 3, Faz 4'ten önce test edilecekse bu ilk günden ayağa dolanır.

### 3. Export filtresinde `link_mode` ve `sharepoint_url` eksik

**Sorun:** `CaseDocument.link_mode` üç değer alır (`models.py:582-586`):
`LINKED`, `TEST` (deneme yüklemeleri), `UNLINKED` (davaya bağlanamamış).
Tür filtresi tek başına yetmez — TEST belgeleri hukukbot RAG'ine gitmemeli.
Ayrıca upload'ı kalıcı başarısız kayıtlarda `sharepoint_url` NULL kalır;
bunlar için `/file` endpoint'i patlar.

**Düzeltme:**
- Outbox satırı açarken `link_mode != "TEST"` şartı ekle.
- `UNLINKED` için bilinçli karar: **aktarılır** (içerik değerli; müvekkil
  eşleşmesi boş kalır). Farklı istenirse tek satırlık filtre.
- `/file` endpoint'i `sharepoint_url IS NULL` durumunda 404 döner; outbox
  tabanlı liste (#1) sayesinde bu kayıtlar listeye zaten hiç girmez.

## Bilinçli karar isteyen nokta

### 4. Metadata arşivden sonra değişebilir; plan tek atımlık

**Sorun:** `belge_turu` sonradan düzeltilebilir, `UNLINKED` → `LINKED` olabilir,
belge silinebilir. Sha256 dedup + tek yönlü aktarım bu değişiklikleri hukukbot'a
yansıtmaz. Özellikle: tür filtresi enqueue anında uygulandığından, başta yanlış
sınıflanmış bir karar sonradan düzeltilse bile ASLA aktarılmaz.

**Karar:** v1'de güncelleme/silme yayılımı kapsam dışı — bu plana açıkça yazıldı.

**Ucuz sigorta:** Arada bir tam tarama (backfill modu: outbox yerine belge
tablosunu güncel filtrelerle tarar, `after_id=0`) + hukukbot tarafında
"sha256 zaten var → atla" kontrolü. Düzeltilmiş türdeki belgeler bu koşuda yakalanır.

## Küçük notlar / iyi haberler

### 5. Güvenlik: `/export`'u public'e hiç açma

X-API-Key iyi ama tek başına kalmasın: her şey aynı sunucuda olduğu için
`/export` route'ları host nginx'e hiç bağlanmamalı — yalnızca iç Docker
network'ünden erişilir olmalı. API key + network izolasyonu birlikte.

### 6. Graph download zaten yazılmış — plandaki "eklenir" maddesi hazır iş

`download_file_from_sharepoint(folder, filename)` mevcut
(`sharepoint/sharepoint_uploader_graph.py:421-439`) ve `routes/documents.py:319-346`'daki
indirme akışı (klasör `SHAREPOINT_FOLDER_ISLENMIS_NAME` env'inden, dosya adı
`stored_filename`) export endpoint'inde aynen yeniden kullanılır. Tek not:
fonksiyon dosyayı komple belleğe alır, stream etmez — plandaki "stream'ler"
ifadesi teknik olarak yanlıştı; boyut limiti olduğu için kabul edilebilir.

### 7. Tür filtresi SQL `IN` ile yapılamaz — DB'de karışık kod formatı var

DB'de hem pad'li (`ARA-KRR_______`) hem kısa (`ARA-KRR`) kodlar karışık
(`routes/documents.py:452-453` yorumu + `scripts/backfill_belge_turu_adi.py` bunun
kanıtı). Normalize mantığı hazır: `file_utils.py:264-272`. Filtre ya Python'da
normalize edilerek yapılır ya da allowlist'in her iki varyantı SQL'e verilir.

### 8. Outbox retry'ının restart'ta kaybolması kabul edilebilir

FastAPI BackgroundTasks kalıcı değildir; process restart'ında bekleyen webhook
denemeleri kaybolur. Plan bunu reconcile ile zaten karşılıyor — outbox satırı
"pending" kalır, hukukbot 30 dk içinde toparlar. Ek iş gerekmez, tutarlı.

---

# Hukukbot Cevap Planının İncelenmesi (2. tur)

Hukukbot reposundan gelen karşı plan (§7.1–7.4) bizim planla büyük ölçüde tutarlı:
payload `{document_id, outbox_id}`, ACK endpoint'i, outbox-id cursor'ı birebir örtüşüyor.
İki iyi yakalamaları da var: **dedup'ta yine de ACK** (yoksa satır sonsuza dek pending
kalırdı) ve **iki yön için ayrı API anahtarı**. Aşağıdakiler ise düzeltme istiyor:

### 9. Cursor'lu reconcile + "pending kalır, reconcile toparlar" birbiriyle çelişiyor ⚠️ TASARIM BOŞLUĞU

**Sorun:** Hukukbot planı hem "cursor outbox id'sidir, lokal `ingest_state`'te tutulur"
hem "başarısız kayıt ACK'lenmez, pending kalır, reconcile toparlar" diyor. İkisi birden
olmaz: cursor başarısız kaydı geçip ilerlerse o kayıt bir daha ASLA taranmaz (sessiz
kayıp); cursor başarısız kayıtta beklerse tek bozuk PDF tüm kuyruğu kilitler
(poison message / head-of-line blocking).

**Düzeltme:** Cursor'ı tamamen bırak. Teslimat durumunu zaten hukdok biliyor (ACK →
"delivered"). Reconcile şunu sorsun: `GET /export/documents?status=pending`. Böylece:
- Geç tamamlanan, kaçan, başarısız olan her kayıt her turda yeniden denenir.
- Kayıt başına try/except — bir bozuk belge diğerlerini engellemez.
- Hukukbot tarafında `ingest_state` tablosuna gerek kalmaz (durum tek yerde: hukdok outbox).
- Sonsuz retry'a karşı: N denemeden sonra hukukbot
  `POST /export/outbox/{id}/nack {reason}` çağırır → satır "failed" olur,
  manuel incelemeye düşer. (Outbox şemasındaki `status="failed"` alanı böylece
  gerçekten kullanılmış olur.)

Hukdok export API'sine eklenmesi gerekenler: listeye `status=` filtresi + `nack` endpoint'i.
`after_id` parametresi yalnızca backfill modu için kalır.

### 10. `http://hukdok-backend:8001` çözünmez — hukdok'un compose'unda o isimde servis yok — ✅ ÇÖZÜLDÜ

**Sorun (o zamanki hâl):** Hukdok compose'unda backend servisi `backend` adında ve
`container_name` tanımlı değildi. Paylaşılan `hukuk_shared` network'ünde
`hukdok-backend` DNS'te çözünmez; `backend` adı ise fazla genel — hukukbot tarafında
da `backend`/`api` gibi bir servis olursa DNS çakışır.

**Düzeltme (uygulandı):** `docker-compose.yml:45`'te `container_name: hukdok_backend`
eklendi (yorumda "BULGULAR #10" diye anılıyor), `hukuk_shared` external network'üne
katıldı. Doğru URL'ler:
- Hukukbot → hukdok: `http://hukdok_backend:8001`
- Hukdok → hukukbot: `http://hukukbot_api:8010/ingest/hukdok` (onların verdiği isim doğru)

### 11. Hukdok backend portu host'ta herkese açık — /export eklenmeden önce daraltılmalı — ✅ ÇÖZÜLDÜ

**Sorun (o zamanki hâl):** `ports: "8001:8001"` → 0.0.0.0'a bind ederdi (postgres'in
aksine; o `127.0.0.1:5432:5432` ile doğru yapılmıştı). Bugün Azure AD auth her
route'u koruyor; ama API-key'li `/export` eklenince bu port üzerinden public erişim
riski doğar — BULGULAR #5'teki "sadece iç network" hedefiyle çelişir.

**Düzeltme (uygulandı):** `docker-compose.yml:54`'te `127.0.0.1:8001:8001` yapıldı
(yorumda "BULGULAR #11" diye anılıyor) — host nginx reverse proxy localhost'tan
erişmeye devam eder; hukukbot zaten paylaşılan Docker network'ünden konuşur.

### 12. Ingest'te crash penceresi: store'a çift yükleme

**Sorun (hukukbot tarafı):** Akış "4. PDF kaydet → 5. store'a yükle → 6. metadata_db'ye
yaz → 7. ACK" ve dedup metadata_db'deki hash'e bakıyor. 5 ile 6 arasında crash olursa:
hash metadata_db'ye yazılmamış → retry dedup'a takılmaz → File Search store'a
İKİNCİ kez yüklenir (store'da yetim/çift kayıt).

**Düzeltme (birini seç):** (a) metadata_db'ye hash'i store upload'ından ÖNCE
"pending" işaretiyle yaz, başarıda finalize et; veya (b) store upload'ını dosya
adıyla idempotent yap (aynı adla varsa önce sil/atlıyor). Nadir bir pencere ama
reconcile'ın retry mantığı bu pencereyi düzenli olarak kurcalayacak.

### 13. Belge türü kod listesi artık eksik değil

İki planın ortak ön koşulu olan liste hukdok referans verisinden çıkarıldı —
aday allowlist ve karar bekleyen kalemler için bkz. [KOD_LISTESI.md](KOD_LISTESI.md).

## Öncelik sırası

| # | Bulgu | Tip | Aksiyon |
|---|-------|-----|---------|
| 1 | Cursor / async upload yarışı | Veri kaybı riski | Export listesini outbox'tan servis et |
| 2 | localhost webhook Docker'da çalışmaz | Çalışmaz | Compose network + servis adı |
| 3 | TEST/NULL-url filtresi eksik | Kirli veri RAG'e sızar | `link_mode` filtresi + 404 |
| 4 | Metadata güncellemeleri yayılmaz | Bilinçli sınırlama | Plana "kapsam dışı" yazıldı + backfill modu |
| 5 | Export public'e açık olmasın | Güvenlik sıkılaştırma | Sadece iç network |
| 6 | Download hazır | İyi haber | `documents.py:319-346` akışını yeniden kullan |
| 7 | Karışık kod formatı | Uygulama detayı | Normalize ederek filtrele |
| 8 | BackgroundTasks kalıcı değil | Kabul edilebilir | Reconcile emniyet ağı yeterli |
| 9 | Cursor vs pending çelişkisi | Sessiz kayıp / kuyruk kilidi | `status=pending` polling + nack; cursor sadece backfill'de |
| 10 | `hukdok-backend` DNS çözünmez | Çalışmaz | `container_name: hukdok_backend` + `hukuk_shared` |
| 11 | Port 8001 host'ta public | Güvenlik | `127.0.0.1:8001:8001` |
| 12 | Ingest crash → store'da çift kayıt | Veri kirliliği (nadir) | Hash'i upload'dan önce "pending" yaz |
| 13 | Kod listesi çıkarıldı | İyi haber | [KOD_LISTESI.md](KOD_LISTESI.md) — karar bekliyor |
