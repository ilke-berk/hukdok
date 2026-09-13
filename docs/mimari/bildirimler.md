# Uygulama içi bildirimler

Zil ikonundan görülen uygulama içi bildirimlerin üreticileri, alıcı çözümü,
zamanlama ve saklama kuralları. Kanal **yalnız uygulama içi**; e-posta gönderimi bu
sistemin parçası değildir (kullanıcı kararı 20.08.2026). Tarihli ölçümler
`docs/arsiv/2026-09-13-bildirim-sistemi-canli-raporu.md`'de.

## 1. Bileşenler

| Parça | Kod | Görev |
| --- | --- | --- |
| Tablo | `models.Notification` (`notifications`) | Kişi başına satır; `dedupe_key` global UNIQUE (`uq_notifications_dedupe`, migrasyon 37) |
| Tek yazma yolu | `services/notifications.create_notification` | Aynı anahtarla ikinci çağrı satır ikilemez, mevcut satırı GÜNCELLEMEZ (okunmuş uyarı yeniden okunmamışa dönmez) |
| Alıcı çözümü | `services/notification_targeting.py` | Serbest metin sorumlu avukat → ofis e-postası; kopya alıcılar; nihai küme |
| Gece tarayıcısı | `services/deadline_scanner.scan_deadlines` | 06:00 TR, yalnız lider worker; boot telafisi `boot_catch_up_scan` |
| Okuma uçları | `routes/notifications.py` | `/api/notifications`, `/count`, `/read-all`, `/{id}/read`; idari `/overview`, `/unresolved-targets` |
| Arayüz | `hooks/useNotifications.ts`, `components/notifications/*`, `shell/Topbar.tsx` | 60 sn'de bir yenileme (`NOTIFICATION_POLL_MS`), sekme gizliyken durur |

## 2. Üreticiler

| `type` | Ne zaman | Dedupe anahtarı | Yazan |
| --- | --- | --- | --- |
| `belge_islendi` | `sharepoint_url` COMMIT edildikten sonra — gündüz yolu `upload_queue._attempt_upload`, **gece dönüşüm retry'ı** `conversion_retry` (13.09.2026'dan beri; önce yalnız gündüz yolu üretiyordu) | `doc-processed:<doc_id>:<email>` | `notifications.notify_document_processed` |
| `sure_yaklasti` | Gece taraması: `case_stage_decisions.teblig_tarihi` → `services/legal_deadlines.deadline_for` (YEREL → istinaf, ISTINAF → temyiz süresi; TEMYİZ/KD kuralsız); eşik T-15/7/3/1, kalan güne uyan EN DAR eşik | `deadline:<stage_decision_id>:<eşik>:<email>` | `deadline_scanner._sure_adaylari` |
| `durusma_yaklasti` | Gece taraması: `hearing_dates.hearing_date`; eşik T-3/T-1 | `hearing:<hearing_id>:<eşik>:<email>` | `deadline_scanner._durusma_adaylari` |
| `veri_teslim` | Teslim hattı durum geçişleri | `teslim:<id>:<durum>:<email>` | `services/teslim_kutusu.bildir` (alıcı `ADMIN_EMAILS`) |

Geçmiş tarihli süre/duruşma için bildirim üretilmez ("yaklaşıyor" denemez);
kaçan T-1 telafi edilmez (bilinçli kabul, `deadline_scanner` modül şerhi).

## 3. Alıcı kuralı

Nihai alıcı kümesi `notification_targeting.resolve_notification_recipients`:

1. **Sorumlu avukat(lar):** `cases.responsible_lawyer_name` serbest metni (`;`/`,`/`ve`
   ayraçlı çoklu kişi) `lawyers` (`gorev='AVUKAT'`) ve `email_recipients` havuzunda
   kod → iki ad token'ı → benzersiz soyad sırasıyla eşlenir (`_match_person`).
   Duruşmada sorumlu çözülemezse zaptaki avukat adı denenir.
2. **Kopya alıcılar** (13.09.2026): `email_recipients.notify_copy = TRUE` olan aktif
   adresler (`copy_recipients`). Yönetim paneli > E-posta Alıcıları > Düzenle >
   "Bildirim kopyası". Gerekçe: prod ölçümünde sorumlu avukat hesapları sisteme hiç
   girmiyor, belgeyi yükleyen/duruşmayı giren personel hiç bildirim almıyordu
   (240/240 okunmamış).
3. **Yükleyen hariç:** "belge işlendi" bildiriminde `case_documents.uploaded_by_email`
   listeden düşer — kişi kendi işlediği belgenin bildirimini almaz; sorumlu avukat
   belgeyi kendisi yüklediyse o da almaz (kural kişiye değil eyleme bağlı).
4. **Allowlist:** `NOTIFICATION_DOMAINS` (varsayılan `hanyaloglu-acar.av.tr`) her iki
   kaynağa da kapıdır; dış avukatların kişisel adresleri hiçbir yoldan dönmez.

"Hedefsiz" sayacı ve WARNING'i **sorumlu avukat çözülemediğinde** düşer; kopya
alıcı varsa bildirim yine yazılır ama hedefsizlik veri kalitesi sinyali olarak
görünür kalır (`/api/notifications/unresolved-targets` bu adları listeler).

## 4. Tebliğ tarihi → aşama kararı (13.09.2026)

Kanuni süre uyarısının tek kaynağı `case_stage_decisions.teblig_tarihi`dir.
`/confirm`'de girilen "Tebliğ Tarihi" (e-posta penceresi) artık yalnız e-posta
metnine değil aşama kararına da yazılır — **yalnız karar belgelerinde**
(`routes/processing.KARAR_DOCTYPE_TO_DECISION_STAGE`: Gerekçeli Karar → YEREL,
İstinaf Kararı → ISTINAF, Yargıtay Kararı → TEMYIZ, Karar Düzeltme Kararı →
KARAR_DUZELTME; kod harf/rakam dışı karakterlerden arındırılarak eşlenir).
TEBLIGAT (mazbata) eşlenmez: her şeyin tebliği olabilir, ondan süre türetmek yanlış
alarm üretirdi. Yazma yolu `managers/stage_decisions.fill_teblig_tarihi`: satır
yoksa BELGE damgalı yeni satır, boş alan dolar, **dolu alan ezilmez**; kart
fotoğrafı tazelenir; `case_history` kaydı `source="auto-teblig"`. Sonuç
`results["teblig_kaydi"]`. Arayüz: e-posta penceresi karar belgesinde açıklama
metnini değiştirir (`lib/kararDoctype.ts`), takip paneli karar tarihi dolu ama
tebliğ boş olan yerel/istinaf aşamasında uyarı gösterir.

## 5. Zamanlama, retention, yetki

- `api.py` lifespan, lider worker: `scan_deadlines` 06:00 TR, `misfire_grace_time`
  1 saat; boot'ta bir kez telafi taraması (her deploy'da koşar, dedupe ikilemez).
- Retention (`NOTIFICATION_RETENTION_DAYS`, varsayılan 90): okunmuş ve eski satır
  silinir, **okunmamış satır asla silinmez**; okunmamış-eski sayısı loglanır.
- Sahiplik `recipient_email` eşitliğidir (token `preferred_username|upn|email`,
  küçük harf); başkasının satırı 404. İdari `/overview` ve `/unresolved-targets`
  olağan `get_current_user` ile açıktır (kullanıcı kararı 20.08.2026).

## 6. Bilinen sınırlar

- Sorumlu adı "Arşiv Dosya Yöneticisi" olan kartlar (prod 13.09: 92, tamamı MAHZEN)
  hiçbir avukata çözülmez; kopya alıcı yoksa uyarıları düşer.
- Süre uyarısı yalnız YEREL/ISTINAF tebliğinden üretilir; TEMYİZ/KD için kural yok.
- Log: gece taraması yalnız `docker logs`'ta (json-file, recreate'te sıfırlanır);
  kalıcı sayaç için `notifications` tablosu ve `/overview` kullanılır.
