# Veri teslim otomasyonu ("teslim gelen kutusu") — plan

**Tarih:** 03.09.2026 · **Kaynaklar:** `HUKDOK_TESLIM_PAKETI_2026-08-18.xlsx` (9 sayfa),
`HUKDOK_VERI_SOZLUGU_2026-08-24.md`, WhatsApp anket cevapları (31.07),
[`faz-f-aktarim-gereksinimleri-2026-08-12.md`](faz-f-aktarim-gereksinimleri-2026-08-12.md) §0,
[`docs/arsiv/aktarim-performans-raporu-2026-08-20.md`](../arsiv/aktarim-performans-raporu-2026-08-20.md).

> **Yaşayan plan.** Kuyruk görevleri `gorevler/gorev/G107`–`G114`. Buradaki her "bugün
> şöyle" iddiası 03.09.2026'da koddan okunarak doğrulandı; kod değişince bu dosya düzeltilir.
>
> **Durum (03.09.2026 gece, G114):** G107–G113 kodu main'de; hattın yaşayan dokümanı
> [`docs/mimari/veri-teslim-hatti.md`](../mimari/veri-teslim-hatti.md), veri ekibine
> verilecek sözleşme [`docs/veri-teslim/SOZLESME.md`](../veri-teslim/SOZLESME.md). Plan
> KAPANMADI: §7 kabul kriterleri prod'da henüz gözlenmedi ve §8'deki kalemler açık.

---

## 0. Sorun

Veri ekibi (büro tarafı, MicroKolayOfis master'ını temizleyen ekip) teslim paketini WhatsApp
ya da e-posta ile gönderiyor; dosya masaüstüne kaydediliyor, konteynere elle kopyalanıyor ve
`scripts/hukdok_aktarim.py` elle koşuluyor. FAZ F §0 aktarımın **tekrar eden bir süreç**
olduğunu söyledi (partili teslim + düzeltme listeleri); süreç tekrar ediyor ama her tekrar
insan eli istiyor. Hedef: veri sağlayıcının değişiklikleri **kendiliğinden** sisteme işlensin,
insan yalnız eşik dışı durumlarda devreye girsin.

WhatsApp bir teslim kanalı olarak otomasyona kapalıdır (kişisel sohbetin API'si yok; Business
API Meta onayı ister ve ayrı bir webhook altyapısı gerektirir). Bu plan kanalı **SharePoint
klasörüne** taşır; WhatsApp yalnız "dosyayı bıraktım" haberi için kalır.

## 1. Bugün elimizde olanlar (koddan doğrulandı)

| Parça | Nerede | Durum |
| --- | --- | --- |
| İdempotent yazma yolu, kuru koşu, belge envanteri kapısı, çıkış kodları, CSV raporlar | `backend/scripts/hukdok_aktarim.py` (`aktarimi_kos`, `AktarimSonucu`) | Hazır; süreç içinden çağrılabilir (testler zaten `from scripts import hukdok_aktarim` yapıyor) |
| Graph app-only token + SharePoint indirme/yükleme | `backend/sharepoint/auth_graph.py`, `sharepoint_uploader_graph.py` (`download_file_from_sharepoint`, `upload_file_to_sharepoint`) | Hazır; klasör listeleme yardımcısı plan yazıldığında YOKTU — G109 `list_folder_children` ile eklendi |
| Kalıcı kuyruk + tek worker deseni | `services/upload_queue.py`, `models.UploadOutbox` | Desen olarak kopyalanır |
| Lider worker'da APScheduler (00:00 rapor, 02:30 dönüşüm, 06:00 süre taraması) + boot telafisi | `api.py` lifespan, `services/deadline_scanner.py` | Yeni job aynı scheduler'a eklenir |
| Admin anahtarları + `require_admin` | `services/app_settings.py`, `routes/admin.py`, `routes/config.py` | Toggle ve uçlar buraya |
| Uygulama içi bildirim (dedupe'lu) | `services/notifications.create_notification` | Admin'e teslim bildirimi |
| Kalıcı volume | `backend-data:/app/data` | Teslim spool'u buraya |

**Teslim paketinin yapısı** (18.08 paketi): `Sheet` (8.409 × 68), `DEGISIKLIK_OZETI`
(önceki/bu teslim adı, satır/sütun sayısı, kalem kalem değişiklik), `SUTUN_SOZLUGU`,
`SINIFLANDIRMA_MODELI`, `DEGER_HAVUZLARI` (kapalı liste değerleri), `HUKDOK_TALEPLERI`,
`Karar_Asamalari` (8.354 × 21), `Düzeltme_Logu` (20.042 × 7: Excel Satırı, SistemNo, DosyaNo,
Eski Değer, Yeni Değer, Gerekçe, Tarih), `Silinen_Föyler` (10 × 54 + gerekçe + tarih),
`Kapsam_Dışı` (51 × 54 + gerekçe + tarih).

**Script plan yazıldığında yalnız `Sheet` + `Karar_Asamalari` okuyordu.** G112/G113 ile
`Düzeltme_Logu`, `DEGER_HAVUZLARI` (servis tarafında, fark raporu), `Silinen_Föyler` ve
`Kapsam_Dışı` de okunur; `DEGISIKLIK_OZETI`'ni teslim gözcüsü zincir kontrolü için okur.
`SUTUN_SOZLUGU`, `SINIFLANDIRMA_MODELI`, `HUKDOK_TALEPLERI` okunmaz (bilinçli — insan
belgesi).

## 2. Hedef mimari

```
veri ekibi ──xlsx──▶ SharePoint 03_VERI_TESLIM/gelen/
                            │  (gece 04:00 TR, lider worker; admin "Şimdi tara" ile gündüz)
                            ▼
                   teslim gözcüsü (Graph children listesi, sha256 ile yeni dosya tespiti)
                            │
                            ▼
                   aktarim_teslimleri defteri  ──▶ spool /app/data/teslim_spool/<id>.xlsx
                            │
              alındı → doğrulandı → kuru_kosuldu → [kapı] → uygulandı
                                                     │            │
                                            inceleme_bekliyor    raporlar ──▶ 03_VERI_TESLIM/cevap/<teslim>/
                                                     │            │
                                              admin "Uygula"   bildirim (ADMIN_EMAILS)
```

Yedek giriş yolu: admin panelden dosya yükleme (`POST /api/admin/aktarim/teslimler`), aynı
deftere aynı durum makinesiyle düşer. Veri ekibinin SharePoint erişimi kesildiğinde ya da
tek seferlik bir düzeltme listesi için kullanılır.

### 2.1 Durum makinesi (`aktarim_teslimleri.durum`)

| Durum | Anlamı | Kim geçirir |
| --- | --- | --- |
| `alindi` | Dosya deftere ve spool'a girdi | gözcü / yükleme ucu |
| `yinelenen` | Aynı sha256 daha önce alınmış; işlenmez (nihai) | gözcü |
| `reddedildi` | Yapı doğrulaması geçemedi (sayfa/başlık) — nihai, bildirim | doğrulayıcı |
| `dogrulandi` | Yapı tamam, zincir kontrolü yapıldı | doğrulayıcı |
| `kuru_kosuldu` | `aktarimi_kos(dry_run=True)` koştu, sayaçlar deftere yazıldı, raporlar spool'da | kuru koşu |
| `inceleme_bekliyor` | Kapı eşik dışı; insan kararı gerek | kapı |
| `uygulaniyor` | Gerçek yazım sürüyor (çökme izi: açılışta `inceleme_bekliyor`a düşürülür) | uygulayıcı |
| `uygulandi` | Commit oldu, raporlar geri yüklendi (nihai) | uygulayıcı |
| `basarisiz` | Uygulama hata verdi ya da envanter kapısı geri aldı (nihai, ERROR + bildirim) | uygulayıcı |

Geçişler tek yönlüdür; `inceleme_bekliyor` yalnız admin "Uygula" ile `uygulaniyor`a geçer.
Her geçiş `durum_gecmisi` JSON kolonuna zaman damgasıyla eklenir.

### 2.2 Kapı (otomatik uygulama eşikleri)

Kuru koşu sonucuna bakılır. **Hepsi** sağlanırsa gece koşusu kendisi uygular:

| Kural | Eşik | Gerekçe |
| --- | --- | --- |
| Belge envanteri denk | zorunlu (`cikis_kodu != 2`) | belge koruma şartı (18.08) |
| Defter boş değil | ilk teslim daima `inceleme_bekliyor` | ilk koşu 40.908 alan değişikliği üretti; otomatik geçmemeli |
| Zincir tamam | `DEGISIKLIK_OZETI` "Önceki teslim" adı defterde `uygulandi` | atlanan teslim varsa insan baksın |
| Satır hata oranı | ≤ `TESLIM_KAPI_HATA_ORANI` (varsayılan 0,02) | 20.08 ölçümü %0,43 |
| Eşleşmeyen satır oranı | ≤ `TESLIM_KAPI_ESLESMEYEN_ORANI` (varsayılan 0,05) | 20.08 ölçümü %2,58 |
| Alan değişikliği | ≤ `TESLIM_KAPI_ALAN_DEGISIKLIGI` (varsayılan 10.000) | 10.08→18.08 deltası 5.813 hücre |

Eşikler env'den okunur, admin panelde görünür. Eşik dışı = `inceleme_bekliyor` + bildirim;
kuru koşu raporları panelden indirilir, admin "Uygula" der.

### 2.3 Zamanlama

Gece turu **04:00 TR**: 03:30 host `pg_dump`'ı bitmiş olur (doğal geri dönüş noktası);
00:00 rapor ve 02:30 dönüşüm retry'ı ile çakışmaz; envanter kapısı eşzamanlı yüklemeye karşı
muhafazakâr olduğundan mesai dışı şarttır. Boot telafisi `deadline_scanner` deseniyle
(lider açılışında bir kez, yalnız tarama + kuru koşu; **uygulama yalnız cron'da**).

Gündüz: admin "Şimdi tara" (tarama + doğrulama + kuru koşu) her zaman serbest; "Uygula"
serbest ama mesai saatinde uyarı metni gösterir (karar kullanıcıda).

### 2.4 Geri bildirim (veri ekibine borç, FAZ F §3 + HUKDOK_TALEPLERI #9)

Her `uygulandi` teslim için `03_VERI_TESLIM/cevap/<teslim dosya adı>/` altına:

1. `satir-raporu_*.csv`, `kardes-foy-celiskileri_*.csv` (mevcut çıktılar),
2. `eslesme_<teslim>.csv` — SistemNo → `cases.id` / `tracking_no` / `klasor_no_2` +
   eşleşmeyenler (Talep #9, "ÖNCELİKLİ"),
3. `ozet_<teslim>.txt` — `ozet_metni(sonuc)` çıktısı + kapı kararı.

Yükleme `upload_file_to_sharepoint` ile; başarısızlık teslimi `basarisiz` YAPMAZ (yazım
zaten commit oldu), WARNING + defterde `cevap_yuklendi=false`, ertesi gece yeniden dener.

## 3. Teslim sözleşmesi (veri ekibine yazılı verilecek — G114)

- Dosya adı `HUKDOK_TESLIM_*.xlsx`; klasör `03_VERI_TESLIM/gelen/`. Aynı dosya adı
  yeniden yüklenirse içerik sha256'sı farklıysa yeni teslim sayılır.
- Zorunlu sayfa: `Sheet` (68 sütun, ad ve sıra sabit — Talep 10 taahhüdü; `SistemNo` +
  `Dosya No` başlıkları yoksa red). `DEGISIKLIK_OZETI` ("Önceki teslim" ve "Bu teslim"
  satırları) plan yazılırken zorunlu düşünülmüştü; **kod isteğe bağlı sayıyor** —
  sayfa yoksa `zincir_tamam=NULL` ve kapı bunu ihlal saymaz (yalnız `is False` →
  `zincir_eksik`), paket öteki eşiklerin içindeyse otomatik uygulanır. Sözleşme koda göre
  yazıldı ("her teslime ekleyin"); zinciri sayfasız pakette de zorlamak istenirse kapıya
  ayrı kural gerekir (§8). `Karar_Asamalari` isteğe bağlı (yoksa aşama yazılmaz, hata değil).
- Partili teslim: eksik sütun mevcut değeri **silmez** ("None = bu teslimde yok").
  Alan boşaltma açık düzeltme yoluyla: `Düzeltme_Logu`'nda Yeni Değer `(boş)` (G112).
- Kapalı liste değerleri `DEGER_HAVUZLARI`'yla gelir; bizde karşılığı olmayan değer
  **yazılmaz**, rapora düşer, listeye kendiliğinden eklenmez (tahmin yasağı, G104 kuralı).
- Cevap klasörü `03_VERI_TESLIM/cevap/<teslim>/` — veri ekibi buradan okur.

## 4. İkinci faz — okunmayan sayfalar

| Sayfa | Ne yapılacak | Görev |
| --- | --- | --- |
| `Düzeltme_Logu` | Değişen alanın gerekçesi `case_history`'ye provenance olarak; `(boş)` yeni değer = açık boşaltma yolu | G112 |
| `DEGER_HAVUZLARI` | Referans listeleriyle fark raporu; yeni değer → bildirim (seed DEĞİL) | G112 |
| `Silinen_Föyler` / `Kapsam_Dışı` | `case_foys.kapsam_disi_gerekcesi` + tarih; kart dokunulmaz, föy işaretlenir; kart panelinde rozet | G113 |

## 5. Kapsam dışı (bilinçli)

- **Kart yaratma.** Eşleşmeyen satır (bugün 217) raporda kalır; ofis no SharePoint
  sayacından atomik tahsis ister, çevrimdışı hattın işi değil (script docstring'i).
- **WhatsApp Business API / e-posta ekini otomatik okuma.** Kanal SharePoint'tir.
- **Ters yön** (bizim veriyi sigorta şirketi Excel'ine işlemek — 31.07 anketi). Ayrı plan.
- **Mükerrer kart birleştirme.** D6 kuralı: otomatik birleştirme yok.
- **`aktarimi_kos`'u `managers/` altına taşımak.** 1.816 satırlık script yerinde kalır;
  servis `scripts.hukdok_aktarim`'ı import eder. `backend/scripts/README.md`'deki "hiçbiri
  API tarafından import edilmez" cümlesi G114'te düzeltildi (istisna açıkça yazılı).

## 6. Görevler ve bağımlılık

```
G107 (backend) defter + servis çekirdeği (kaydet/doğrula/kuru koş/kapı/uygula)      TAMAM
  └─▶ G108 (backend) admin uçları + bildirim + app_settings anahtarı                 TAMAM
        └─▶ G109 (backend) SharePoint listeleme + gece job 04:00 + boot telafisi     TAMAM (tara ucu hariç — §8)
              └─▶ G110 (backend) cevap paketi: eşleşme CSV + SharePoint'e geri yükleme TAMAM
                    └─▶ G112 (backend) Düzeltme_Logu provenance + DEGER_HAVUZLARI farkı TAMAM
                          └─▶ G113 (backend) Silinen_Föyler / Kapsam_Dışı föy işareti  TAMAM (rozet hariç — §8)
G111 (frontend) admin "Veri Teslimleri" sekmesi — sözleşme G108'de DONDURULDU, paralel   TAMAM
G114 (docs) mimari doküman + teslim sözleşmesi + README düzeltmeleri — G110, G111, G113 sonrası TAMAM
```

Durumlar görev dosyalarının `DURUM:` satırından (`gorevler/gorev/G107`–`G114`); kodun
güncel hâli [`docs/mimari/veri-teslim-hatti.md`](../mimari/veri-teslim-hatti.md)'de.

**İnsan adımları (kuyruk kapsamı DIŞI):** SharePoint'te `03_VERI_TESLIM/gelen` ve `cevap`
klasörlerini açmak + veri ekibine paylaşım vermek; `.env`'e `SHAREPOINT_FOLDER_TESLIM_NAME`
ve kapı eşiklerini yazmak (`up -d` recreate); ilk teslimin `inceleme_bekliyor`dan elle
uygulanması; sözleşme metnini veri ekibine iletmek.

## 7. Kabul (planın kapanış kriteri)

1. Veri ekibinin bıraktığı bir xlsx, insan dokunmadan ertesi sabah `uygulandi` ya da
   `inceleme_bekliyor` durumunda; ikisinde de admin'e bildirim düşmüş.
2. Aynı dosya ikinci kez bırakılınca `yinelenen`; aynı içerik ikinci kez uygulanınca 0
   değişiklik (mevcut idempotency testi bu hattan da geçer).
3. `cevap/<teslim>/` altında üç çıktı; Talep #9 eşleşme dosyası dahil.
4. Belge envanteri her koşuda denk; denk değilse `basarisiz` + tek ERROR.

Kriterlerin dördü de kodda testli (`backend/tests/test_g107`–`test_g113`), ama plan
**prod'da ilk gerçek teslim gözlenmeden kapanmaz**.

## 8. Açık kalanlar (03.09.2026, G114)

Plan kapanmadı; kuyruk turu bittiğinde şunlar açık:

| Kalem | Durum | Kim / ne |
| --- | --- | --- |
| `POST /api/admin/aktarim/tara` yer tutucu | Panelin "Şimdi tara" düğmesi gözcüyü ÇAĞIRMIYOR, sıfır + `not` dönüyor (`routes/admin.py:311-325`). G109 raporundaki sebep: G108 testi yanıtı birebir kilitliyor; uç gövdesi + test tek küçük görev | yeni kuyruk görevi (5 dk) |
| Kapsam dışı föy rozeti (frontend) | `get_case` çıktısında `foyler[]` (`kapsam_durumu` dahil) hazır; kart panelinde gösterim yok | yeni frontend görevi |
| Prod kurulumu | SharePoint'te `03_VERI_TESLIM/gelen` + `cevap` klasörleri, veri ekibine paylaşım; `.env`'e `SHAREPOINT_FOLDER_TESLIM_NAME` (+ isteğe bağlı `TESLIM_KAPI_*`), `docker compose up -d` (recreate); admin panelden anahtar | insan |
| `DEGISIKLIK_OZETI` yokken zincir kapısı | Sayfasız pakette `teslim_dogrula` `zincir_tamam=NULL` yazar (`services/teslim_kutusu.py:784-786`), `kapi_ihlalleri` yalnız `is False`'u `zincir_eksik` sayar (`:846`) → paket zincir kontrolü olmadan otomatik uygulanabilir. §3'ün "zorunlu" varsayımı kodda yok; sözleşme koda göre düzeltildi. İstenirse kapıya `zincir_bilinmiyor` (NULL → inceleme) kuralı + test: küçük görev, karar insanın | insan kararı → yeni kuyruk görevi |
| İlk teslim | Defter boşken kapı `ilk_teslim` der — ilk paket `inceleme_bekliyor`dan elle uygulanır; 20.08 ölçümü (40.908 alan değişikliği) burada insan gözü ister | insan |
| Sözleşmenin iletilmesi | `docs/veri-teslim/SOZLESME.md` veri ekibine gönderilir; `Düzeltme_Logu` sütun-adı öneki ve `(boş)` yazımı orada tanımlı | insan |
| Cevap klasörü ara klasörleri | Graph yol-adresli PUT'un `cevap/<teslim>/` klasörlerini açtığı koddan kanıtlanmadı; ilk gerçek yükleme gözle doğrulanır, açılmazsa klasörü önce yaratan küçük ek | ilk teslimden sonra |
| eTag ayrı kolon | Bugün `sharepoint_item_id` içinde `<id>@<eTag>`; ayrı kolon istenirse `sharepoint_item_anahtari` + `_bilinen_sp_anahtarlari` tek dokunma noktası | isteğe bağlı |
| Ters yön (sigorta Excel'i) | §5 — ayrı plan | — |
