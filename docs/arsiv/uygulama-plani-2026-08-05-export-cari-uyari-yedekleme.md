# Uygulama Planı — Export soft-delete filtresi + cari silme uyarısı + rapor notları + Postgres yedekleme

**Tarih:** 2026-08-05 · **Statü:** Onaylı, uygulanacak
**Kaynak:** Büro cevabının ikinci tur backlog önerilerinin değerlendirmesi (kabul edilenler). Reddedilen/kapananlar en altta — yeniden açmayın.

## ⚠️ ÖN KOŞUL — mevcut çalışma ağacı durumu

2026-08-05 tarihli BÜYÜK paket (soft-delete, tku_no/sistem_no, hükmedilen tutarlar, PROCESS_MAP, Kayıt No) **uygulandı ve test edildi ama COMMIT'LENMEDİ**. Working tree'de duruyor. Bu plandaki işler o paketin ÜZERİNE gelir:
- Önce mevcut değişiklikleri gözden geçirip commit'leyin (tek commit veya mantıksal parçalara bölerek), SONRA bu plana başlayın.
- Doğrulama durumu: backend pytest 515 passed + ruff + mypy temiz (konteynerde); frontend vitest 148 passed + tsc temiz. Migration'lar lokal DB'ye uygulanıp doğrulandı (8 cases kolonu + 3 clients kolonu + 5 index).
- Test koşuları: backend `docker compose exec backend python -m pytest` (önce `pip install -r requirements-dev.txt` gerekebilir; host py3.13 uyumsuz), frontend host'ta `cd frontend && npm test && npx tsc --noEmit`.

---

## İş 1 — Hukukbot export hattına soft-delete filtresi

**Sorun (doğrulanmış):** `backend/routes/export.py` sorguları `Case.deleted_at`'e bakmıyor → soft-delete edilen davanın belgeleri `/export` hattından hukukbot'a akmaya devam ediyor. Yanlışlıkla açılıp silinen davanın kararı bilgi havuzuna girmemeli.

**Değişiklikler:**
1. `backend/routes/export.py`:
   - `GET /export/documents` (≈:120-160, `yield_per` döngüsü): sorguya ya da Python filtresine "davası silinmiş belgeyi atla" koşulu — `doc.case_id is None or doc.case.deleted_at is None` (UNLINKED belgeler bilinçli dahil kalmaya DEVAM eder, mevcut davranış). `joinedload(...CaseDocument.case)` zaten var (:141), N+1 yok.
   - `GET /export/documents/{id}` (≈:165) ve `GET /export/documents/{id}/file` (≈:209): `doc.case_id is not None and doc.case.deleted_at is not None` → 404.
   - `_doc_passes_filters` (≈:87-101) içine taşımak en temiz yol olabilir — üç uç da onu kullanıyorsa tek nokta yeter; kullanmıyorsa uçlara tek tek ekleyin.
2. `backend/services/export_publisher.py` `enqueue_document` (≈:36-82): aynı koşul — silinmiş davanın belgesi outbox'a hiç girmesin. (Zaten `delivered` olmuş satırlara DOKUNMAYIN — hukukbot tarafında yaşayan içerik ayrı konu.)
3. Bilinçli-açık yorumu: dava RESTORE edilirse belgeleri tekrar akmaya başlar (filtre dinamik) — bu istenen davranıştır, koda yorum düşün.

**Test (`backend/tests/test_export_filters.py`'a ekleme — mevcut monkeypatch desenini izleyin):**
- Silinmiş davalı belge `_doc_passes_filters`/listeden elenir; `case_id=None` (UNLINKED) belge elenMEZ; silinmemiş davalı belge geçer.

## İş 2 — Aktif davalı cari silme uyarısı

**Felsefe:** ENGELLEME YOK (sistem geneli kural: zorunlu alanlar, tanıdık sorgu hep uyarır, engellemez) — yalnız bilgilendirme.

**Değişiklikler:**
1. Backend — `backend/routes/clients.py`: yeni küçük uç `GET /api/clients/{client_id}/case-summary` → `{"active_cases": N, "total_cases": M}`. Sorgu: `CaseParty.client_id == id` join `Case`, `Case.deleted_at IS NULL`; aktif = `status != 'MAHZEN'` (veya `active.is_(True)` — mevcut stats semantiğine bakın: `get_case_stats`'ta "active" = DERDEST sayısı; burada "kapanmamış" anlamı için `status.in_(("DERDEST","DANIŞ"))` en dürüstü). `get_tenant_owned_client` ile sahiplik doğrulaması.
2. Frontend — `frontend/src/pages/NewClient.tsx` silme AlertDialog'u (≈:756-780, artık gerekçe textarea'lı): dialog açıldığında case-summary çekilir; `active_cases > 0` ise açıklamaya kırmızı satır: "Dikkat: bu müvekkilin N açık davası var. Silinse de davalardaki taraf kayıtları korunur." Buton engellenmez.
3. `frontend/src/hooks/useClients.ts`: `getClientCaseSummary(id)` fetch'i.

**Test:** backend'e saf test zor (DB) — mevcut gelenek gereği route imza/filtre kaynak kontrolü yeterli; asıl doğrulama el testi.

## İş 3 — Rapor notları (docs/sistem-teknik-raporu-2026-08-04.md)

Tek oturumda dört küçük ekleme:
1. **§6.6 tablosuna satır** veya altına kısa blok — "İkinci tur kararlar (2026-08-05)":
   - Export filtresi + cari silme uyarısı uygulandı (İş 1-2 bitince yazın).
   - **tku_no/sistem_no aktarım doğrulama kararı:** ayrı doğrulama ucu AÇILMAYACAK; doğrulama = aktarım script'inin dry-run raporu + doğrudan psql sorguları + `GET /api/cases/{id}` ham dict'inde iki alanın dönmesi.
   - **Retag kuru-çalışma sonucu:** lokal DB'de İdare/Tahkim/Vergi/Danışmanlık türündeki 4.414 dosyanın SIFIRINDA B4=HUKUK yanlış bloğu bulundu (bu türler Excel import script'iyle gelmişti, script'in haritası tamdı; UI'dan bu türlerde yeni-format numara hiç üretilmemiş). Toplu retag GEREKSİZ; PROCESS_MAP düzeltmesi ileriye dönük koruma. Prod'da teyit sorgusu: `SELECT count(*) FROM cases WHERE file_type IN ('İdare','Tahkim','Vergi','Danışmanlık') AND tracking_no LIKE '%.HUKUK.%';`
   - **calendar_events maddesi düştü:** tablo davaya bağlı değil (`case_id` yok, `models.py` docstring "Bir davaya bağlı değildir"); davaya bağlı takvim öğesi HearingDate'tir ve filtresi uygulandı.
2. **Kanonik kimlik cümlesi** (§8 veya §6.6 sonuna): "`cases.id` sistemin kanonik kimliğidir; hiçbir işlemde değişmez. Export sütun adları/sırası sürümlenir; değişiklikler duyurulmadan yapılmaz."
3. **Purge notu** (§6.4 soft-delete kısmına veya §16'ya): "Soft-delete imha değildir. KVKK imha yükümlülüğü kapsamında, saklama süresi dolan kayıtlar için kalıcı imha (purge) yolu İLERİKİ FAZ olarak planlanmalıdır (belge binary'lerinin SharePoint'ten silinmesi dahil)."
4. **Yedekleme bölümü** — İş 4 kurulunca rapora kısa bölüm: yöntem, zamanlama, saklama, geri dönüş adımı.
5. Aktarım planı notu (§6.5 sonuna 1 satır): aktarım gününde admin panelinden `party_roles`'a `Aleyhine Başvurulan / Alacaklı / Katılan` eklenecek; "Kurum" kategorisi B1 eşlemesi ve Hizmet Türü bitmask tablosu ekiple kararlaştırılacak (açık karar).

## İş 4 — Postgres yedekleme rutini (EN YÜKSEK ÖNCELİK, prod işi)

**Gerekçe:** Tüm kimlikler/ilişkiler/metadata tek Postgres'te; SharePoint yalnız binary tutar. DB kaybı = hangi belge hangi davanın bilgisinin kaybı. Şu an düzenli yedek YOK (raporda ve sunucu sertleştirme planında yedekleme geçmiyor).

**Erişim:** `ssh hukukoid` (docker sudo'suz + şifresiz sudo; yedek: `ssh hukukoid-cc`). Salt-ekleme bir iş, mesai-dışı şartı yok; yine de kurulumu düşük trafik saatinde yapmak nazik olur.

**Tasarım:**
1. **Dump:** gecelik cron (örn. 03:30 TR), `docker exec hukudok-postgres pg_dump -U hukudok_user -Fc hukudok > /home/<user>/backups/hukudok_$(date +%F).dump` (custom format — `pg_restore` ile seçmeli geri dönüş). Script'e `set -euo pipefail` + başarı/boyut logu.
2. **Yerel saklama:** `~/backups/` altında son 14 gün; daha eskisi silinir (`find -mtime +14 -delete`).
3. **VM dışına kopya — KARAR NOKTASI (kurulumda seçin):**
   - **Seçenek A (önerilen, sıfır yeni bağımlılık):** SharePoint'e yükleme — backend'in mevcut app-only Graph kimliğiyle küçük bir python script'i (`backend/sharepoint/sharepoint_uploader_graph.upload_file_to_sharepoint` yeniden kullanılabilir; hedef `02_YEDEK_ARSIV` içine `db_backup_YYYY-MM-DD.dump` — teknik loglarla aynı klasör deseni). Konteyner içinden koşturmak env'leri hazır bulur: `docker exec hukdok_backend python scripts/upload_db_backup.py <dosya>` gibi.
   - **Seçenek B:** GCS bucket (`gsutil cp`) — VM'de gcloud/gsutil ve servis hesabı yetkisi VARSA daha temiz; yoksa kurulum maliyeti var, A'yı seçin.
   - Dump'lar kişisel veri içerir → dış kopyanın erişimi de kısıtlı olmalı (SharePoint klasörü zaten app-only; bucket seçilirse private).
4. **Doğrulama:** kurulumdan sonra bir kez elle koştur, dump boyutunu kontrol et (beklenti: >10 MB), `pg_restore --list` ile açılabildiğini doğrula; ertesi gün cron çıktısını kontrol et.
5. **Geri dönüş tatbikatı (opsiyonel ama önerilir):** dump'ı LOKAL ortamda boş bir DB'ye `pg_restore` ile açıp `SELECT count(*) FROM cases;` doğrulaması — raporda "geri dönüş denendi" diyebilmek için.
6. Cron satırları + script'ler repo'ya da eklensin (`scripts/prod/backup_db.sh` + README notu) ki kurulum yeniden üretilebilir olsun.

**Prod notları (hafızadan):** prod `main` dalında; `.env` değişikliği gerektiren bir şey yok; `docker logs`'u `--since`'siz çalıştırmayın; VM 4 GB RAM — pg_dump gece saatinde sorun değil.

## Uygulama sırası
1. Mevcut büyük paketi commit'le (ön koşul).
2. İş 1 (export filtresi) + testi.
3. İş 2 (cari uyarısı).
4. İş 3 (rapor notları — 1. maddesi İş 1-2 sonrası).
5. Testler: konteynerde pytest+ruff+mypy, host'ta vitest+tsc.
6. Bu paketi commit'le.
7. İş 4 (prod yedekleme) — ayrı oturum/iş olarak; kurulum + doğrulama + rapora bölüm + commit.

## Reddedilen / kapanan maddeler (YENİDEN AÇMAYIN)
- **calendar_events dava filtresi:** konusuz — tablo davaya bağlı değil.
- **Toplu retag:** gereksiz — kuru çalışmada 0 yanlış kayıt bulundu (yukarıda).
- **tku/sistem için ayrı doğrulama ucu:** açılmayacak — karar İş 3'te belgeleniyor.
- **D-No/Luhn/Numarator:** büro geri çekti (rapor §6.4/§6.6).
- **"Dört taahhüt" kontrat çerçevesi:** iç standart olarak rapora yazıldı; ayrıca sözleşme belgesi üretilmeyecek.
