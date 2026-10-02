# Uygulama içi bildirimler

Zil ikonundan görülen uygulama içi bildirimlerin üreticileri, alıcı çözümü,
zamanlama ve saklama kuralları. Kanal **yalnız uygulama içi**; e-posta gönderimi bu
sistemin parçası değildir (kullanıcı kararı 20.08.2026). Tarihli ölçümler
`docs/arsiv/2026-09-13-bildirim-sistemi-canli-raporu.md`'de.

## 1. Bileşenler

| Parça | Kod | Görev |
| --- | --- | --- |
| Tablo | `models.Notification` (`notifications`) | Kişi başına satır; `dedupe_key` global UNIQUE (`uq_notifications_dedupe`, migrasyon 37); `link` = tıklanınca gidilecek uygulama içi yol (NULL → `case_id` kuralı) |
| Tek yazma yolu | `services/notifications.create_notification` | Aynı anahtarla ikinci çağrı satır ikilemez, mevcut satırı GÜNCELLEMEZ (okunmuş uyarı yeniden okunmamışa dönmez) |
| Alıcı çözümü | `services/notification_targeting.py` | Serbest metin sorumlu avukat → ofis e-postası; kopya alıcılar; nihai küme |
| Gece tarayıcısı | `services/deadline_scanner.scan_deadlines` | 06:00 TR, yalnız lider worker; boot telafisi `boot_catch_up_scan` |
| Okuma uçları | `routes/notifications.py` | `/api/notifications`, `/count`, `/read-all`, `/{id}/read`; idari `/overview`, `/unresolved-targets` |
| Arayüz | `hooks/useNotifications.ts`, `components/notifications/*`, `shell/Topbar.tsx` | 60 sn'de bir yenileme (`NOTIFICATION_POLL_MS`), sekme gizliyken durur. Odak modundaki sayfada (`/hukukbot`, `hooks/useOdakModu.ts`) Topbar ve zil çizilmez |

## 2. Üreticiler

| `type` | Ne zaman | Dedupe anahtarı | Yazan |
| --- | --- | --- | --- |
| `belge_islendi` | `sharepoint_url` COMMIT edildikten sonra — gündüz yolu `upload_queue._attempt_upload`, **gece dönüşüm retry'ı** `conversion_retry` (13.09.2026'dan beri; önce yalnız gündüz yolu üretiyordu) | `doc-processed:<doc_id>:<email>` | `notifications.notify_document_processed` |
| `sure_yaklasti` | Gece taraması: `case_stage_decisions.teblig_tarihi` → `services/legal_deadlines.deadline_for` (YEREL → istinaf, ISTINAF → temyiz süresi; TEMYİZ/KD kuralsız); eşik T-15/7/3/1, kalan güne uyan EN DAR eşik | `deadline:<stage_decision_id>:<eşik>:<email>` | `deadline_scanner._sure_adaylari` |
| `durusma_yaklasti` | Gece taraması: `hearing_dates.hearing_date`; eşik T-3/T-1 | `hearing:<hearing_id>:<eşik>:<email>` | `deadline_scanner._durusma_adaylari` |
| `veri_teslim` | Teslim hattı durum geçişleri | `teslim:<id>:<durum>:<email>` | `services/teslim_kutusu.bildir` (alıcı `ADMIN_EMAILS`) |
| `hata_bildirimi` | Kullanıcı karttaki zilden hata bildirince (§7) | `hata:<bildirim_id>:<email>` | `routes/hata_bildirimleri._alicilara_bildir` |
| `hata_sonucu` | Hata bildirimi kapatılınca, bildirene (§7) | `hata-sonuc:<bildirim_id>` | `routes/hata_bildirimleri._kapanisi_bildir` |

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

## 7. Hata bildirimi (02.10.2026)

Avukat dava ya da müvekkil kartında yanlış gördüğü bilgiyi mesajlaşma yerine kartın
içinden bildirir; idari personel zilden görür, kaydı düzeltir, bildirimi kapatır.

| Parça | Kod | Görev |
| --- | --- | --- |
| Tablo | `models.HataBildirimi` (`hata_bildirimleri`, migrasyon 58) | Hedef TEK: `case_id` ya da `client_id` (CHECK). `alan` + `alan_etiketi` + `mevcut_deger` bildirim anının fotoğrafı; `dogru_deger` / `aciklama` bildirenin yazdığı (en az biri zorunlu) |
| Uçlar | `routes/hata_bildirimleri.py` | `POST /api/hata-bildirimleri` · `GET` (`case_id` \| `client_id` \| hedefsiz = pano; `durum=acik\|hepsi`) · `GET /alicilar` (alıcı adayları) · `GET /dogrudan?case_id=` (doğrudan düzeltilebilir alanlar) · `POST /{id}/kapat` (`COZULDU` \| `REDDEDILDI`; zaten kapalı 409) |
| Alıcı | `notification_targeting.error_report_candidates` · `GET /api/hata-bildirimleri/alicilar` | **Bildiren pencerede seçer** (en az bir kişi). Aday havuzu üç grup: İdari personel (`email_recipients`, avukat olmayanlar) · Avukatlar (iç avukatlar: `lawyers.gorev='AVUKAT'` + adı bir iç avukatla eşleşen alıcı satırı) · Yönetici (`ADMIN_EMAILS`; allowlist'ten muaf, adı `ADMIN_ADLARI` env'inden). Dış avukat ve allowlist dışı adres listede yok; istek sahibi kendini görmez. Sunucu seçimi havuza karşı doğrular (listede olmayan adres 422) ve seçilenleri satıra yazar (`alicilar`, ad fotoğrafıyla) |
| Ön-seçim | `lib/hataBildirimleri.onSecim` · `error_report_recipients` | Tarayıcıda hatırlanan son seçim (hâlâ aday olanlar); yoksa `notify_error_reports` işaretliler (Yönetim > E-posta Alıcıları > Düzenle > "Hata bildirimi"), o da yoksa `notify_copy` alıcıları. İstemci alıcı göndermezse (aday listesi alınamadı) bildirim bu varsayılanlara gider |
| Zil hedefi | `notifications.link` | Sunucunun ürettiği uygulama içi yol (`/cases/<id>?hata=<n>`, `/clients?client=<id>&hata=<n>`); müvekkile bağlı bildirimin `case_id`si yoktur. Frontend yalnız `/` ile başlayan yolu izler (`lib/hataBildirimleri.guvenliIcYol`) |
| Arayüz | `components/hata/HataBildirimi.tsx` | `HataBildirimSaglayici` (kartı sarar) · `HataBildirButonu` (alan yanındaki kırmızı zil; açık bildirimi olan alanda dolu) · `AcikHataBildirimleri` (kartın üstündeki şerit: "Kaydı düzelt", "Düzeltildi", "Değişiklik gerekmiyor") |
| Pano | `components/dashboard/HataBildirimleriPanel.tsx` | İdari pano "05 · Düzeltme": kapatılmamış tüm bildirimler — zil okunduktan sonra iş unutulmasın |

- **Doğrudan düzeltme ("Kendim düzelt"):** davanın sorumlu avukatı (`resolve_case_recipients`) ya da
  yönetici (`ADMIN_EMAILS`) doğrusunu biliyorsa kimseye bildirmeden kaydı kendisi düzeltir:
  `POST` gövdesinde `dogrudan_duzelt=true`. Yalnız dava kartında ve `DOGRUDAN_DUZELTME_ALANLARI`nda
  (`esas_no`, `hasar_dosya_no`, `hukuk_no`, `klasor_no_2`, `judicial_unit` — serbest metinli kimlik
  alanları; liste/tarih/tutar/avukat/durum alanları bilinçli dışarıda, onlar bildirimle gider ve dava
  formundan düzeltilir). Pencere önce "Emin misiniz?" diye eski → yeni değeri gösterir. Sunucu kapıları
  hiçbir şey yazmadan koşar: alan listede değil 422 · yetkisiz 403 · ekrandaki değer artık kayıtlı değer
  değil 409 · değer aynı 422. Yazım `case_manager.enrich_case`ten geçer (tarihçe `source=HATA_DUZELTME`
  + yapan kişi; esas no `sync_current_esas`); bildirim GİTMEZ, kayıt `COZULDU` olarak denetim izi kalır
  (`durum=hepsi` listesinde). Düğmenin görünmesi için istemci `GET /dogrudan?case_id=` ile sorar.
- **Durum tek yönlü:** `ACIK → COZULDU | REDDEDILDI`; satır silinmez, yeniden açılmaz.
  Kapatma koşullu UPDATE'tir (`durum = 'ACIK'`): iki kişi aynı anda kapatırsa biri 409 alır.
- **Kapanışta:** bildirene `hata_sonucu` yazılır (kendi bildirimini kapattıysa yazılmaz);
  diğer alıcıların okunmamış `hata_bildirimi` satırları okundu işaretlenir.
- **Yetki:** rol yok — giriş yapmış herkes bildirir, listeler, kapatır; kapatan satıra yazılır.
  Görünürlük hedef kayıttan gelir (paylaşımlı havuz + soft-delete → 404).
- **Bildirim kaydı düşürmez:** zile yazım başarısız olursa WARNING; kayıt kartta ve panoda görünür.
- **Zillerin olduğu yerler:** dava kartı (başlık alanları, Dosya Bilgileri, Tıbbi / Kanun Yolu /
  Büro kartları, tazminat satırları, taraf kartları + alana bağlı olmayan "Hata Bildir" düğmesi),
  müvekkil hızlı bakış paneli. Takip sekmesinde (aşama kararları, duruşmalar) alan zili YOK —
  oradan gelen hata genel düğmeyle bildirilir. Yeni bir yere zil eklemek = sağlayıcının içinde
  `<HataBildirButonu alan etiket deger />`.
