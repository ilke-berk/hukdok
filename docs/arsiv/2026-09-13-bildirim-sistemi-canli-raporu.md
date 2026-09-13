# Bildirim sistemi — canlı (prod) durum raporu, 13.09.2026

> Tarihli fotoğraf. Sayılar 13.09.2026 02:50 TR'de prod veritabanından (`notifications`,
> `hearing_dates`, `case_stage_decisions`, `daily_activity_reports`, `case_documents`)
> ve `hukdok_backend` konteyner logundan okunmuştur. Prod sürümü `c184c9a`.

## 1. Sistem nasıl çalışıyor (koddan)

**Kanal:** yalnız uygulama içi. E-posta gönderimi bildirim sisteminin parçası DEĞİL
(kullanıcı kararı 20.08.2026; `services/notifications.py` modül şerhi). Kullanıcı
üst çubuktaki zil ikonundan görür (`frontend/src/components/shell/Topbar.tsx` →
`NotificationBell`), panel 60 saniyede bir `GET /api/notifications/count` ve listeyi
yeniler (`hooks/useNotifications.ts`, `NOTIFICATION_POLL_MS = 60_000`; sekme gizliyken durur).

**Tek yazma yolu:** `services/notifications.create_notification`. `dedupe_key` global
UNIQUE (`uq_notifications_dedupe`); aynı anahtarla ikinci çağrı satır ikilemez ve mevcut
satırı GÜNCELLEMEZ (okunmuş uyarı yeniden okunmamışa dönmez).

**Üç üretici:**

| Tür (`type`) | Ne zaman | Alıcı | Dedupe anahtarı |
| --- | --- | --- | --- |
| `belge_islendi` | Belge SharePoint'e yüklenip `sharepoint_url` COMMIT edilince (`upload_queue._attempt_upload` başarı yolu, en sonda) | Davanın sorumlu avukat(lar)ı | `doc-processed:<doc_id>:<email>` |
| `sure_yaklasti` | Gece 06:00 TR taraması: `case_stage_decisions.teblig_tarihi` → G084 kanuni süre motoru; eşikler T-15/7/3/1 (YEREL, İSTİNAF; TEMYİZ/KD kuralsız) | Davanın sorumlu avukat(lar)ı | `deadline:<stage_decision_id>:<eşik>:<email>` |
| `durusma_yaklasti` | Gece 06:00 TR taraması: `hearing_dates.hearing_date`; eşikler T-3/T-1 | Sorumlu avukat, yoksa zaptaki avukat | `hearing:<hearing_id>:<eşik>:<email>` |
| `veri_teslim` | Teslim hattı durum geçişleri (reddedildi/uygulandı/başarısız/inceleme) | `ADMIN_EMAILS` | `teslim:<id>:<durum>:<email>` |

**Hedefleme (`services/notification_targeting.py`):** `cases.responsible_lawyer_name`
serbest metni → `lawyers` (gorev=AVUKAT) ve `email_recipients` havuzunda ad/kod/soyad
eşleşmesi → e-posta. Alan adı allowlist'i `NOTIFICATION_DOMAINS` (prod'da env YOK →
varsayılan `hanyaloglu-acar.av.tr`). Çözülemeyen ad "hedefsiz" sayılır, bildirim üretilmez,
WARNING loglanır.

**Zamanlama:** APScheduler yalnız lider worker'da; `scan_deadlines` 06:00 TR,
`misfire_grace_time` 1 saat. Lider boot'unda bir kerelik telafi taraması
(`boot_catch_up_scan`) koşar — her deploy'da tarama tekrar koşar, dedupe sayesinde
satır ikilenmez. Tur sonunda retention: okunmuş ve 90 günden eski satır silinir,
okunmamış satır ASLA silinmez.

**Okuma/yetki:** sahiplik `recipient_email` eşitliği (token'daki
`preferred_username|upn|email`, küçük harfe indirgenir). Başkasının bildirimi görünmez.
İdari özet `GET /api/notifications/overview` (süre+duruşma, kime gitti/okundu mu) ve
`/unresolved-targets` — panelde "zamanlı iş" görünümü (`dashboard/timedWorkOverview.ts`).

## 2. Canlıda ne oldu (03.09 – 13.09)

Sistem prod'a **03.09.2026 03:48 TR**'de girdi (Deploy #19 boot'u; ilk satır id=1,
o günkü duruşma için "son gün bugün" uyarısı).

### 2.1 Genel

| Ölçüm | Değer |
| --- | --- |
| Toplam bildirim | 240 |
| Okunmamış | **240 (%100)** |
| Kapatılmış (`dismissed_at`) | 0 |
| `belge_islendi` | 221 (info) |
| `durusma_yaklasti` | 19 (warning) |
| `sure_yaklasti` | **0** |
| `veri_teslim` | 0 (anahtar kapalı, defter boş) |
| Retention'a takılan | 0 (en eski satır 10 günlük) |

### 2.2 Alıcı dağılımı

| Alıcı | Toplam | Belge | Duruşma | Okunmuş |
| --- | --- | --- | --- | --- |
| turgal@ | 129 | 127 | 2 | 0 |
| ungor@ | 55 | 48 | 7 | 0 |
| basyurt@ | 35 | 30 | 5 | 0 |
| yucel@ | 20 | 16 | 4 | 0 |
| gumus@ | 1 | 0 | 1 | 0 |

### 2.3 Sisteme fiilen giriş yapanlar (`daily_activity_reports`)

| Kullanıcı | Rapor günü | Son |
| --- | --- | --- |
| meral@ (Nurten Meral) | 71 | 09.09 |
| tel@ (Çiğdem Tel) | 34 | 09.09 |
| ilkekutluk@lexisbio | 6 | 10.08 |
| hanyaloglu@ | 3 | 01.09 |

03.09'dan beri yüklenen 225 belgenin 117'sini meral@, 108'ini tel@ yüklemiş. Beş
bildirim alıcısının hiçbiri bu listede YOK.

### 2.4 Günlük akış

| Gün | Adet | Not |
| --- | --- | --- |
| 03.09 Per | 31 | go-live; 1 duruşma (boot) + 30 belge |
| 04.09 Cum | 27 | belge |
| 06.09 Cmt | 3 | 06:00 cron: 09.09 duruşmaları T-3 |
| 07.09 Pzt | 83 | 1 duruşma T-3 + 82 belge |
| 08.09 Sal | 68 | 3 duruşma T-1 (06:00) + 1 duruşma (18:53 boot) + belge |
| 09.09 Çar | 20 | 2 duruşma + belge |
| 11.09 Cum | 1 | duruşma T-1 |
| 12.09 Cmt | 4 | 3 boot (03:07) + 1 cron (06:00), 15.09 duruşmaları T-3 |
| 13.09 Paz | 3 | 02:21 boot: 16.09 duruşmaları T-3 |

Belge bildirimleri mesai saatlerine yayılıyor (10:00–18:59; tepe 14:00 ve 18:00).

### 2.5 Tarayıcı sağlığı

- 06:00 cron'u **her gün koştu** (06, 07, 08, 09, 11, 12.09 06:00 damgaları; 10.09'da eşiğe
  giren duruşma yoktu). Deploy boot'ları (08.09 18:53, 12.09 03:07, 13.09 02:21) da telafi
  taraması koştu, dedupe çift satır üretmedi.
- Bu gece (13.09 02:41 TR boot) telafi turu logu: `sure_bildirim 0, durusma_bildirim 6,
  hedefsiz 0, kuralsiz 0, atlanan 256, hata 0, purged 0`. 6 duruşma adayının 6'sı zaten
  vardı (dedupe).
- Aynı anda kuru koşu (yalnız okuma fazı): süre adayı 0, duruşma adayı 6, hedefsiz 0.
- Hedefe çözülemeyen sorumlu adları (`unresolved_targets`): 4 ad / 98 dava —
  "Arşiv Dosya Yöneticisi" 92, "Asu Barış Karamık" 4, "AGH" 1, "ZEYNEP AYAN" 1.
- Konteyner logunda ERROR yok (yalnız bu boot'tan itibaren görünür; json-file 3×50 MB,
  recreate'te sıfırlanır).

### 2.6 Belge kapsaması

03.09 03:48'den beri `sharepoint_url` yazılan 225 belgenin **221'i** bildirim üretti.
Üretmeyen 4: 3'ü "Arşiv Dosya Yöneticisi" sorumlu (hedefsiz, beklenen), 1'i (doc 2391,
08.09 18:53:15) tam deploy boot anında yüklendi — bildirim adımı yeniden başlatmaya
denk gelmiş görünüyor.

## 3. Bulgular (önem sırasıyla)

1. **Bildirimler, sistemi kullanmayan kişilere yazılıyor.** Alıcı = davanın sorumlu
   avukatı (turgal/ungor/basyurt/yucel/gumus); bu beş hesap 10 günde bir kez bile
   giriş yapmamış. Fiilen sistemi kullanan meral@ ve tel@ hiçbir davada sorumlu
   görünmediği için hiç bildirim almıyor. Sonuç: 240/240 okunmamış — sistem teknik
   olarak doğru, işlevsel olarak kimseye ulaşmıyor.
2. **Kanuni süre uyarısı (`sure_yaklasti`) hiç üretilmedi ve mevcut veriyle
   üretilmeyecek.** Tek kaynak `case_stage_decisions.teblig_tarihi` (780 dolu satır)
   ve bunların TAMAMI 04.09 aktarım paketinden; en yeni tebliğ 12.08.2026, son 120
   gündeki 66 satırın son günü çoktan geçmiş ("atlanan"). Günlük kullanımda tebliğ
   tarihi girilmiyor → kaynak beslenmiyor. Duruşma tarafı ise besleniyor (30 günde 72
   duruşma elle girildi: Meral 41, Tel 31) ve çalışıyor.
3. **Gece dönüşüm retry'ı bildirim üretmiyor.** `services/conversion_retry.py`
   başarı yolu `notify_hukukbot` çağırıyor ama `notify_document_processed`
   çağırmıyor; 02:30 turunda tamamlanan belge "belge işlendi" bildirimi almaz.
   Sayısal etkisi bu dönemde görülmedi (kapsam 221/225), ama kod boşluğu.
4. **Hedefsiz 98 dava:** 92'si "Arşiv Dosya Yöneticisi" — gerçek kişi değil, kalıcı
   olarak çözülemez. Bu davaların belge/duruşma uyarıları sessizce düşüyor (WARNING).
5. Tarayıcı, dedupe, boot telafisi, retention: **ölçülen davranış tasarıma birebir
   uyuyor.** Cron her gün koştu, hata 0, çift satır 0.

## 4. Öneriler ve uygulama (aynı gün, kullanıcı kararı)

Kullanıcı 13.09 gecesi dört öneriyi de onayladı; ek kural: **belgeyi yükleyen kişi
kendi işlediği belgenin bildirimini almaz** (personel ya da avukat fark etmez).
Uygulama tek commit'te (`docs/mimari/bildirimler.md` yaşayan doküman):

- **Kopya alıcı bayrağı:** `email_recipients.notify_copy` (migrasyon 51), yönetim
  paneli > E-posta Alıcıları > Düzenle > "Bildirim kopyası". İşaretli adres sorumlu
  avukata yazılan her bildirimin (belge/süre/duruşma) kopyasını alır; yükleyen hariç.
  **Prod'da insan adımı:** deploy sonrası meral@ ve tel@ için bayrağı açmak.
- **Tebliğ tarihi:** `/confirm`'de karar belgesiyle (Gerekçeli / İstinaf / Yargıtay /
  Karar Düzeltme kararı) girilen tebliğ tarihi aşama kararına yazılır; TEBLIGAT
  (mazbata) türünde yazılmaz. E-posta penceresi karar belgesinde açıklamayı değiştirir,
  takip paneli tebliğsiz yerel/istinaf kararında uyarı gösterir.
- **Gece dönüşüm retry'ı** artık "belge işlendi" bildirimi üretir.
- **92 "Arşiv Dosya Yöneticisi" kartı:** prod'da başka bir avukat izi YOK
  (`case_lawyers` 52 kartta tüm ofisi listeliyor, 40 kartta boş; `uyap_lawyer_name`
  boş; tarihçe yok) → gerçek sorumlu koddan türetilemez, kullanıcı kararı bekliyor.
  Kopya alıcı bayrağı açılınca bu kartların uyarıları da personele ulaşır.
