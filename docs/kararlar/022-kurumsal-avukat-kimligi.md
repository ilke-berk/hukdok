# 022 — Kurumsal avukat kimliği `AVK-00001`; avukat kodları kalkar, avukat kaydı silinmez

**Tarih:** 27.09.2026 · **Karar veren:** kullanıcı (büro sahibi) · **Durum:** kabul — HUKDOK tarafı
uygulandı (G224-G229, main'de; prod'a deploy EDİLMEDİ), Hukukbot tarafı (G230) ve geçiş sonu
temizliği (G231) BLOKE

## Karar

- HUKDOK ve Hukukbot için **ORTAK** avukat kimliği `lawyers.kimlik`'tir: `AVK-00001` biçimi
  (önek + 5 hane, `models.AVUKAT_KIMLIK_REGEX`; Postgres'te `ck_lawyers_kimlik_bicim` CHECK +
  `ix_lawyers_kimlik` UNIQUE + NOT NULL — `database.py` madde 54).
  - **Sistem üretir** (`models.sonraki_avukat_kimligi`: tablodaki en büyük numara + 1), istemcinin
    gönderdiği değer yok sayılır (`reference_lists._avukat_ekle`).
  - **Değişmez:** verilmiş kimliği değiştiren/boşaltan flush `ValueError` (`models._avukat_kimligi_degismez`).
  - **Yeniden kullanılmaz:** en büyük üzerinden sayıldığı için pasif kişinin numarası tekrar verilmez.
  - **Kullanıcıya gösterilmez:** yönetim paneli ve dava listesi kimliği yalnız değer olarak taşır,
    ekrana ad basılır (G229).
- Veritabanının iç anahtarı `lawyers.id` yalnız tablolar arası FK'dır (`case_lawyers.lawyer_id`,
  `case_documents.lawyer_id`); API'de ve sistemler arasında **dışarı verilmez**.
- **Avukat kaydı silinmez, pasife alınır:** `lawyers` için DELETE (özel `DELETE /api/config/lawyers/{kimlik}`
  ve genel `/api/config/delete`) `active=false` yapar (`reference_lists._avukati_pasife_al`); "clear"/"keep"
  modları 422 ile reddedilir (`LawyerDeleteRejected`); "reassign" kartları hedefe taşır, kaynak yine
  pasife alınır.
- Avukata giden bağlar **`ON DELETE RESTRICT`**: `case_lawyers.lawyer_id` (`case_lawyers_lawyer_id_fkey`,
  migrasyon 54 eski SET NULL'u düşürüp yeniden kurar) ve `case_documents.lawyer_id` (migrasyon 55).
- Hukukbot kimlik ↔ ad eşlemesini API-key'li **`GET /export/lawyers`**'tan öğrenir
  (`routes/export.py`; yanıt `[{"kimlik", "ad", "aktif"}]`, `id`/e-posta/telefon/TC/sicil/görev sızmaz);
  belge kayıtları `avukat_kimlik` + `avukat_adi` taşır. Sözleşme: `docs/hukukbot-aktarim/PLAN.md` §2.
- Yönetim uçları ve dava listesi filtresi avukatı `kimlik` ile tanır (`PUT|DELETE /api/config/lawyers/{kimlik}`,
  `GET /api/cases?lawyer=<kimlik>`); eski kod/ad değeri 1 sürüm geriye uyumludur (G231'de kalkar).

## Bağlam ve gerekçe

27.09 keşfi (G224-G228 raporları, `gorevler/gorev/G22x.md`) avukat **kodunun** güvenilir bir kimlik
olmadığını gösterdi:

- **Kod belgeden okunmuyordu.** Belge hattı kodu bağlı davanın `responsible_lawyer_name`'inden, config'teki
  ada BİREBİR eşleyerek türetiyordu (farklı yazımda boş kalıyordu); `/confirm`'ün `avukat_kodu` Form alanını
  hiçbir istemci göndermiyordu. G226 bunu toleranslı çözümle `lawyer_id`'ye çevirdi
  (`services/document_pipeline.lawyer_id_for_text`).
- **İki sistemin kod kümeleri farklıydı.** Hukukbot sabit 9'lu 3-harf setinin dışındaki kodu — HUKDOK'un
  `TUGCEUNG`'u dahil — sessizce NULL'a çeviriyordu (hukukbot-ui `app/metadata.py` `sanitize_metadata`; keşif
  G227/G230). Bilgi zaten Hukukbot'a ulaşmıyordu.
- **Sahipsiz eski kodlar vardı:** `TUY`, `BYU`, `AGH` belgelerde duruyor ama listede karşılıkları yoktu
  (lokal: 5 + 5 + 1 belge). G226 bunları sabit haritayla bağladı (`scripts/belge_avukat_bagi.ESKI_KOD_HARITASI`).
- **Ad düzeltmesi bağ koparmamalı.** 27.09 yazım birliği ("Tuğçe Ungör Yanık") gibi ad değişiklikleri
  süreklidir; bağ ad üzerinden kurulursa her düzeltme bir kaybettirme riskidir. Kimlik adla değişmez.
- **Eski silme yolu dava kaybı üretebiliyordu:** `reference_lists.delete_item` kaydı `db.delete` ile
  siliyor, "clear" modu kartlardaki avukat alanını boşaltıyor, `case_lawyers.lawyer_id` `ON DELETE SET NULL`
  kart–avukat bağını sessizce koparıyordu. Üçü de kapandı (yukarıda).

Kullanıcı şartı: geçişte **hiçbir dava kaybolmamalı**.

## Geçiş güvenceleri

- **Envanter aracı (G224):** `services/avukat_envanteri.py` + `scripts/avukat_envanteri.py`
  (`--kaydet` / `--karsilastir`, İHLAL varsa çıkış 1). Avukat başına filtre dava sayısı, sorumlu kart,
  `case_lawyers` (bağlı dahil) ve belge sayısını ölçer; herhangi biri düşerse İHLAL.
- **Her veri adımı:** önce fotoğraf → adım → `--karsilastir`; İHLAL = geri al
  (`docs/mimari/dava-acma-akisi.md` §15). `scripts/belge_avukat_bagi.py` bunu kendi transaction'ında yapar
  (İHLAL → rollback). G225, G226, G228'in lokal koşularında sonuç 0 İHLAL.
- **Filtre ad eşlemesini korur (G228):** filtre asla yalnız kimliğe bakmaz — kimlik → avukat kaydı →
  mevcut toleranslı AD eşlemesi (`case_manager._lawyer_filter_case_ids`); yalnız adla kayıtlı kartlar
  filtrede kalır. Lokal ölçüm: 81 avukatın 81'inde kimlikle filtre = eski kodla filtre.
- Prod sırası (yedek + fotoğraf + kuru koşu + kullanıcı onayı) `gorevler/gorev/G231.md` "Prod sırası"nda.

## Reddedilenler

- **Kodları düzeltip yaşatmak:** iki sistemin kümesi zaten farklı, eski kodlar sahipsiz, kod adın
  kısaltması olduğu için ad düzeltmesiyle "yanlış" kalır; `ABDULLAH` gibi kodlar sıradan ad token'ı olup
  eşlemeyi yanıltıyordu (G228).
- **UUID:** okunmaz (log, rapor, destek konuşmasında kullanışsız); tek üretici HUKDOK olduğu için
  dağıtık üretim ihtiyacı da yok — sıralı numara yeterli.
- **Veritabanı `id`'sini dışarı vermek:** ortama bağlıdır (prod/lokal/yedek restore farklı `id` verebilir);
  sistemler arası kimlik her ortamda aynı olmalı.
- **Adla bağ:** ad değişir (yazım birliği, evlilik soyadı); bağı kırılgan yapan tam da buydu.

## Açık maddeler

- **G231 — geçiş sonu temizliği (BLOKE):** `case_documents.avukat_kodu` kolonu, export'taki DEPRECATED
  `avukat_kodu`, filtrenin kod/ad geriye uyum dalı kalkar. Önkoşul: G224-G229 prod'da + prod adımları
  tamam + Hukukbot G230 canlıda.
- **`lawyers.code` kolonunun akıbeti:** kolon NOT NULL UNIQUE kalıyor, yeni kayıtta sunucu üretiyor
  (G228) ama hiçbir yanıt/ekran onu kimlik olarak kullanmıyor. Kaldırılıp kaldırılmayacağı AYRI karar;
  G231 yalnız "kalmalı mı / kaldırma maliyeti" ölçümünü raporlar.
- **Numaranın her ortamda aynı olması:** migrasyon 54 mevcut satırları `sequence, id` sırasıyla numaralar;
  prod'a uygulamadan önce prod listesinin sırası lokalle karşılaştırılmalı, farklıysa prod numarası esas
  alınır (G225 raporu "İzlenecekler").

İlgili: `docs/mimari/dava-acma-akisi.md` §15-17, `docs/mimari/belge-isleme-hatti.md` §3,
`docs/hukukbot-aktarim/PLAN.md` §2, karar [012](012-soft-delete-baglar-korunur.md) (soft-delete'te bağlar korunur),
`backend/tests/test_avukat_envanteri.py`, `test_g225_avukat_kimligi.py`, `test_g226_belge_avukat_bagi.py`,
`test_g227_export_avukat_kimligi.py`, `test_g228_avukat_kimlikle_yonetim.py`.
