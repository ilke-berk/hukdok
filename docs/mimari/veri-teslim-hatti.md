# Veri teslim hattı — panelden yükleme → defter → kapı → elle uygulama

> **17.09.2026 — SharePoint teslim klasörü yolu KALDIRILDI** (kullanıcı kararı; klasör bağlantısı
> veri ekibine hiç gitmemişti, defter boştu): G109 gözcüsü (`sharepoint_tara`,
> `list_folder_children`), 04:00 gece turu + boot telafisi, G110 `cevap/` yüklemesi, G147 ikinci
> SharePoint kimliği (`TESLIM_SHAREPOINT_*`), `POST /api/admin/aktarim/tara` ve
> `veri_teslim_otomasyonu` anahtarı koddan çıktı. §1, §2, §5, §6, §9 ve §10 bu koda göre yeniden
> yazıldı (satır numaraları 17.09 çalışma ağacına aittir); §3/§4/§7 eski doğrulama notlarını taşır.
>
> Önceki doğrulama: 2026-09-04 · 88409da; §3 doğrulama/özet satırları, §4 kapı, §7 `Düzeltme_Logu`
> ve kapsam referansları ile **§7.1 (aktarımın yazma kuralları, G150–G159)** 2026-09-10 · G161 ile
> `39fd10c` koduna göre yeniden doğrulandı. Her iddia koddan doğrulanmıştır. Kod ile çelişirse kod
> haklıdır — bu dosyayı düzelt. Veri ekibine verilen dış sözleşme ayrı dosyadadır:
> [`docs/veri-teslim/SOZLESME.md`](../veri-teslim/SOZLESME.md) (kod yolu içermez).

Veri ekibi (büro tarafı, MicroKolayOfis master'ını temizleyen ekip) teslim paketini
(`HUKDOK_TESLIM_*.xlsx`) bize iletir; yönetici paketi admin panelinden yükler. Hat dosyayı
deftere alır, yapısını doğrular, **kuru koşturur** ve kapı eşiklerine vurur; **uygulamayı daima
yönetici "Uygula" ile başlatır** (otomatik/gece uygulaması yok). Paketi panelsiz, doğrudan
uygulamanın yolu CLI'dır (`scripts/hukdok_aktarim.py`, kuru koşu → `--apply`; 15.09 ve Ek-4/Ek-5
turları bu yoldan uygulandı). Gerçek yazma yolu `scripts/hukdok_aktarim.aktarimi_kos`'tur — hat
onu yalnız import eder, değiştirmez (`backend/services/teslim_kutusu.py:12-20`).

```
veri ekibi ──xlsx──▶ yönetici ──▶ admin paneli "Dosya yükle"  (POST /api/admin/aktarim/teslimler)
                                          │
                                          ▼
              aktarim_teslimleri defteri  +  spool  <TESLIM_SPOOL_DIR>/<id>_<dosya>
                                          │
   alindi → dogrulandi → kuru_kosuldu → [kapı] → (admin "Uygula") → uygulaniyor → uygulandi
                │              │                                        │              │
            reddedildi   inceleme_bekliyor                          basarisiz   rapor dizini: eşleşme CSV,
                                                                                özet, raporlar (panelden indirilir)
```

## 1. Giriş — yükleme, spool, kimlik

| Ne | Değer | Kod |
| --- | --- | --- |
| Giriş yolu | yalnız admin paneli multipart yükleme (`kaynak="yukleme"`); SharePoint klasörü YOK | `backend/routes/admin.py:156-185` |
| Dosya | yalnız `.xlsx` (aksi 400), 50 MB üstü 413 | `routes/admin.py:40`, `:156-185` |
| Spool dizini | env `TESLIM_SPOOL_DIR`; tanımsızsa `<backend>/data/teslim_spool` (konteynerde `/app/data` volume'u → recreate'i atlatır) | `services/teslim_kutusu.py:228`; `.env.example` "Veri teslim hattı" bloğu |
| Açma/kapama anahtarı | **yok** (17.09'da `veri_teslim_otomasyonu` kalktı — açıp kapadığı gözcü ve gece uygulaması yok); DB'de kalan eski satır zararsız, ayar listesi yalnız registry'yi dolaşır | `services/app_settings.py` `SETTINGS_REGISTRY` |
| SharePoint | hat SharePoint'e **hiç** gitmez; tek SharePoint kimliği arşivindir (`config_type="default"`) | `sharepoint/auth_graph.py:19-24` |

`teslim_kaydet(kaynak=…, sharepoint_item_id=…)` imzası ve `KAYNAKLAR = ("sharepoint", "yukleme")`
tarihsel satırlar için kalır (`teslim_kutusu.py:137`, `:1008`); yeni satır yalnız `yukleme` ile açılır.

## 2. Yükleme ucu

`POST /api/admin/aktarim/teslimler` → `teslim_kaydet(kaynak="yukleme")` +
`teslimi_isle(otomatik_uygula=False)` → 201 `{id, durum}`; bozuk/`Sheet`'siz dosya HTTP hatası
değil `201 + durum="reddedildi"`dir (`backend/routes/admin.py:156-185`). Aynı içerik ikinci kez
yüklenirse `yinelenen` satırı açılır (§3).

## 3. Defter — `aktarim_teslimleri`

Model `backend/models.py:1080` (`AktarimTeslimi`), `UploadOutbox` deseninin kardeşi. Kolonlar
(`models.py:1110-1135`):

| Kolon | Anlamı |
| --- | --- |
| `dosya_adi`, `sha256`, `kaynak` (`sharepoint` \| `yukleme`) | kimlik; `sha256` içeriğin kimliğidir; 17.09'dan beri yeni satır yalnız `yukleme` |
| `sharepoint_item_id` | tarihsel (G109 gözcüsünün `<driveItem id>@<eTag>` anahtarı); yükleme yolunda NULL |
| `spool_path` | `<spool>/<id>_<dosya_adi>` |
| `durum`, `durum_gecmisi` (JSON `[{"durum","at","not"}, …]`) | durum makinesi + her geçişin zaman damgalı izi (`teslim_kutusu.py:307-319`) |
| `onceki_teslim_adi`, `zincir_tamam` | `DEGISIKLIK_OZETI` "Önceki teslim" + o teslim defterde `uygulandi` mı (NULL = özet sayfası yok) |
| `okunan`, `islenen`, `atlanan`, `hata_sayisi`, `alan_degisikligi`, `kart_degisen`, `envanter_denk` | `AktarimSonucu` sayaçları — kuru koşu yazar, gerçek uygulama üzerine yazar (`:349-356`) |
| `kapi_karari` (`otomatik` \| `inceleme`), `kapi_gerekcesi` | kapı sonucu; gerekçe `;` ayraçlı ihlal listesi |
| `rapor_dizini` | `<spool>/<id>_raporlar` (`:329-334`) |
| `cevap_yuklendi` | tarihsel (G110 SharePoint cevap yüklemesi); 17.09'dan beri yazılmaz, default false |
| `uygulayan` | admin e-postası (`gece-job` imzası `GECE_UYGULAYAN`, `:151`, üretimde çağıran yok) |
| `hata_mesaji` | `basarisiz`/`reddedildi` sebebi, ≤ 2000 karakter (`:199`) |
| `created_at`, `updated_at`, `done_at` | `done_at` nihai duruma geçiş anı (`:318-319`) |

İki index modelde değil migrasyonda (G041 kuralı — tabloyu `create_all` yaratır,
`("table", …)` op'u ölü kod olurdu), `backend/database.py:913-919` madde 39:

- `uq_aktarim_teslimleri_sha256` — **kısmi** UNIQUE, `WHERE durum <> 'yinelenen'`: aynı içerik
  ikinci kez gelince mevcut satıra dokunulmaz, izlenebilirlik için yeni bir `yinelenen` satırı
  açılır (notunda ilk id), spool'a yazılmaz; yarışta IntegrityError yakalanıp ikinci kayıt
  `yinelenen`e düşer (`teslim_kutusu.py:703-741`, `:754-767`).
- `idx_aktarim_teslimleri_bekleyen` — `created_at` üzerinde, dört bekleyen durumla partial;
  17.09'a dek gece turunun tarama deseniydi; index yerinde kalır (DROP gerekmez).

### Durum makinesi

`services/teslim_kutusu.py:125-151`:

| Durum | Anlamı | Kim geçirir |
| --- | --- | --- |
| `alindi` | dosya deftere ve spool'a girdi | `teslim_kaydet` (`:703`) |
| `yinelenen` | aynı sha256 daha önce alınmış; nihai, işlenmez, bildirim üretmez | `teslim_kaydet` |
| `reddedildi` | yapı doğrulaması geçemedi — nihai, **WARNING** + bildirim | `teslim_dogrula` (`:770-797`) |
| `dogrulandi` | `Sheet` var, zorunlu başlıklar var, zincir bakıldı | `teslim_dogrula` |
| `kuru_kosuldu` | `aktarimi_kos(dry_run=True)` koştu; sayaçlar deftere, raporlar spool'a | `teslim_kuru_kos` (`:800-827`) |
| `inceleme_bekliyor` | kapı eşik dışı — insan kararı; bildirim | `kapi_degerlendir`, `acilis_toparla` (`:1305`) |
| `uygulaniyor` | gerçek yazım sürüyor — **çökme izi**, commit'li (`:910-911`) | `_teslim_uygula` (`:899-941`) |
| `uygulandi` | commit oldu; nihai, bildirim, eşleşme + havuz farkı dosyaları rapor dizinine | `_teslim_uygula` (`:1227`) |
| `basarisiz` | uygulama istisnası ya da envanter kapısı geri aldı — nihai, **TEK ERROR** + bildirim | `_basarisiz` (`:415-423`) |

Geçişler tek yönlüdür; kapı `otomatik` derse durum **değişmez** (`kuru_kosuldu` kalır,
uygulama ayrı adımdır), `inceleme_bekliyor`dan yeniden değerlendirme geriye gitmez — yalnız
karar/gerekçe tazelenir. `teslimi_isle` (`:1274`) doğrula → kuru koş → kapı →
(`otomatik_uygula` ve kapı `otomatik` ise) uygula zincirini tek çağrıda yürütür; nihai ya da
`uygulaniyor` satıra **dokunmaz**, mevcut durumu döner. 17.09'dan beri üretimde bütün çağıranlar
(admin yükleme ve kuru-koş uçları) `otomatik_uygula=False` verir — `True` dalını yalnız durum
makinesi testleri koşar.

Yapı doğrulaması (`_yapi_dogrula`, `services/teslim_kutusu.py:1006`): dosya açılmalı, `Sheet`
sayfası olmalı, başlık satırında `sistem_no` **ve** `dosya_no` bulunmalı (`ZORUNLU_BASLIKLAR`,
`:218`; script tek başına yalnız `sistem_no`'yu zorunlu sayar ama `dosya_no` eşleştirme
köprüsüdür, onsuz her satır atlanırdı). `DEGISIKLIK_OZETI` (`OZET_SAYFASI`, `:215`) isteğe
bağlıdır; üç etiketi tek ayrıştırıcı okur (`_ozet_etiket_degeri`, `:876-899`: etiket ilk 200
satırda — `_OZET_TARAMA_SATIRI`, `:220` — aksan/boşluk duyarsız aranır, değer aynı hücrede `:`
sonrasında ya da sağdaki ilk dolu hücrede; yer tutucular `_YER_TUTUCULAR`, `:222`):

- **"Önceki teslim"** (`onceki_teslim_adi_oku`, `:902`; yer tutucu `—`/`yok`/`İLK` → None).
  Sayfa yoksa `zincir_tamam=NULL` (`teslim_dogrula`, `:1141`). Ad bulunduysa
  `zincir_tamam = (o ad defterde uygulandi)` (`_uygulandi_var`, `:403`; çağrı `:1153`); ad
  yoksa **G156 zincir başlangıcı kuralı** (`:1144-1151`): defterde hiç `uygulandi` teslim
  yoksa `True` (ilk teslim zaten `ilk_teslim` kuralıyla incelemeye düşer), uygulanmış teslim
  varken yer tutucu `False` (`zincir_eksik`). Durum geçmişi notu "zincir başlangıcı" /
  "belirtilmemiş ama defterde uygulanmış teslim var" der.
- **"Teslim türü: tam | delta"** (G156, `teslim_turu_oku`, `:919-943`; sabitler
  `TESLIM_TURU_TAM`/`TESLIM_TURU_DELTA`, `:231-233`) `yapi["teslim_turu"]` olarak yazılır
  (defter kolonu yok, `teslim_turu(teslim)` `:741` defter JSON'undan okur; satır yok/boş/yer
  tutucu → `tam`, tanınmayan değer WARNING + `tam`). Delta = yalnız değişen föy/sütunlar: yazma
  yolu zaten eksik sütun/föye dokunmaz (`scripts/hukdok_aktarim.py`), kapı ise delta'da
  kaybolan başlığı ihlal değil **bilgi** sayar (`_ihlal_kategorileri`, `:829-831`;
  `_DELTA_IHLAL_KATEGORILERI`, `:268`; §4 `yapi_degisti`); envanter denkliği, zincir ve eşik
  kuralları delta'da aynen geçerlidir. Sözleşmedeki delta kuralları (yalnız ilgili föylerin
  aşama/log satırları, zincir kesintisiz, aylık tam paket) kodun **dışında** kalan süreç
  kurallarıdır — kod delta'yı "eksik = dokunma" ile taşır.
- **"Veri kesim tarihi"** (G152, `kesim_tarihi_oku`, `:945-963`; `_tarih` ile çözülür, bozuk
  değer WARNING + None). `kesim_tarihi_bul` (`:965-1003`) üç kaynağı sırayla dener: özet
  sayfası (INFO) → paket adındaki ISO tarih (`_PAKET_ADI_TARIHI`, `:226`; WARNING: teslim günü
  kesim sayıldı) → None (kural kapalı). Değer deftere yazılmaz, `_aktarimi_calistir`
  `aktarimi_kos(kesim_tarihi=…)` parametresi olarak geçer (`:712`); ne işe yaradığı §7.1
  "status koruması".

### Aktarım ayrı bağlantıda koşar

`aktarimi_kos` oturum fabrikası ister ve `statement_timeout`'u oturum boyu yükseltir; havuza
o ayarla dönen bir bağlantı Faz 3-E'nin 30 sn korumasını sessizce kaldırırdı. Bu yüzden
`_aktarimi_calistir` bağlantıyı açıkça alır, iş bitince `RESET statement_timeout` + kapatır;
defter oturumu aktarım süresince kapalı transaction'dadır (önce commit)
(`services/teslim_kutusu.py:25-32`, `:593-625`). Çağrı daima `sheet="Sheet"` ve
`source="HUKDOK_TESLIM_<dosya adı>"` ile yapılır (`:615-622`; önek
`required_fields.py:100`).

## 4. Kapı — eşikler ve kurallar

`kapi_ihlalleri` (`services/teslim_kutusu.py:1207-1235`) kuralların **hepsini** değerlendirir ve
gerekçeyi `;` ile birleştirir — admin "neden inceleme" sorusuna tek bakışta cevap alsın, ilk
ihlalde durup diğerleri gizlenmesin. Boş liste = `otomatik` (= "eşik içi"; uygulamayı yine
yönetici başlatır — otomatik uygulama 17.09'da kalktı).

| Kural etiketi (`KAPI_KURALLARI`, `:193-196`) | Koşul | Eşik / kaynak |
| --- | --- | --- |
| `envanter_denk_degil` | `envanter_denk is not True` | zorunlu — belge koruma şartı (`services/belge_envanteri.py:1-20`) |
| `ilk_teslim` | defterde `uygulandi` teslim yok | zorunlu — ilk teslim daima incelemeye düşer |
| `zincir_eksik` | `zincir_tamam is False` (özet var ama önceki teslim uygulanmış değil; yer tutucu yalnız defter boşken zincir başlangıcıdır — G156) | — |
| `yapi_degisti` | önceki `uygulandi` teslime göre yeni başlık / kaybolan başlık / kaybolan sayfa (G115); **delta** teslimde kaybolan başlık ihlal değil bilgidir, yapı farkı bloğunda yine listelenir (G156) | `_IHLAL_KATEGORILERI` / `_DELTA_IHLAL_KATEGORILERI` |
| `bos_teslim` | `okunan == 0` | — |
| `hata_orani` | `hata_sayisi / okunan >` eşik | env `TESLIM_KAPI_HATA_ORANI`, varsayılan **0.02** |
| `eslesmeyen_orani` | `atlanan / okunan >` eşik | env `TESLIM_KAPI_ESLESMEYEN_ORANI`, varsayılan **0.05** |
| `alan_degisikligi` | `alan_degisikligi >` eşik | env `TESLIM_KAPI_ALAN_DEGISIKLIGI`, varsayılan **10000** |

**Eşik = kart hücresi (K2).** `alan_degisikligi` föy satırı değil, kartta değeri değişen alan
sayar: `_kart_alanlarini_yaz` değişen alan adlarını döner, `_satiri_isle` `len(degisenler)`
toplar (`scripts/hukdok_aktarim.py:2411`); deftere `AktarimSonucu.alan_degisikligi` olarak
geçer (`teslim_kutusu.py:420`). Tarih/tutar tip düzeyinde normalize edildiğinden biçim farkı
değişiklik üretmez (`_tarih` `:503`, `_sayi` `:562-575`); metin alanları ham `==` ile
karşılaştırılır (`:2004`) — ad yazımı farkı değişiklik sayılır ve paket yazar. Tek istisna
`ICERIK_KARSILASTIRMALI_ALANLAR = {"court"}` (`:921`): yalnız yazım farkında bizimki kalır
(`:2006-2008`). `status` istisnası (§7.1) kapı kuralı DEĞİLDİR: korunan alan `KORUNDU`
türüyle raporlanır, `hata_sayisi`'na ve eşiklere girmez.

**Zincir başlangıcı ve delta (G156):** `zincir_eksik` yalnız `zincir_tamam is False` iken
düşer; yer tutucu "Önceki teslim" defter boşken `True` verdiğinden ilk paket ihlal listesinde
yalnız `ilk_teslim` taşır (`:1213-1218`). `yapi_degisti` teslim türüne bakar
(`teslim_turu(teslim)` `:1232`, `_ihlal_var(fark, tur)` `:1233`): delta'da kaybolan başlık
gerekçeye girmez ama `fark_kalemleri` (`:817`) değişmediği için bildirim gövdesinde ve
`ozet.txt` "yapı farkı" satırında bilgi olarak listelenir.

Eşikler env'den **çağrı anında** okunur (`kapi_esikleri`, `teslim_kutusu.py:305`;
`.env.example` "Veri teslim hattı" bloğu üçünü yorumlu, varsayılanlarıyla taşır). Recreate'siz `.env` değişikliği
yine gelmez ama admin paneli `esikler` alanında anlık değeri görür (`routes/admin.py:101-121`).
Sayı olmayan değer WARNING + varsayılan (`teslim_kutusu.py:228-236`).

`KAPI_KURALLARI` dışında iki gerekçe etiketi daha `kapi_gerekcesi`ne yazılır:
`uygulama_kesildi` (açılışta `uygulaniyor` bulunan satır, `acilis_toparla`, `teslim_kutusu.py:1305`)
ve tarihsel `tek_uygulama` (17.09'a dek gece turunun ikinci uygulanabilir teslimi; artık üretilmez).

## 5. Zamanlama — açılış toparlaması ve admin paneli

**Zamanlayıcı job'ı YOK** (17.09: `id="veri_teslim"` 04:00 TR gece turu kalktı). Lider worker'ın
lifespan bloğu yalnız `boot_toparla`yı daemon thread'de bir kez başlatır (`backend/api.py:246-251`;
`services/teslim_kutusu.py:1337`): `acilis_toparla` (`:1305`) `uygulaniyor`da kalmış satırları
`inceleme_bekliyor`a düşürür (gerekçe `uygulama_kesildi`) — aktarım TEK transaction'dır, kesilen
uygulama ya tamamen yazdı ya hiç; hangisi olduğunu insan raporlardan görür ve yeniden "Uygula"
der. İstisna tek WARNING ile yutulur; bekleyen satırlar işlenmez, uygulama yapılmaz.

**Admin paneli, "Veri Teslimleri" sekmesi** (`frontend/src/components/admin/DeliveryInboxCard.tsx`):

| Uç | Ne yapar | Kod |
| --- | --- | --- |
| `GET /api/admin/aktarim/teslimler` | liste (en yeni önce, `limit` 1–500) + `esikler` | `routes/admin.py:102-121` |
| `GET …/teslimler/{id}` | tek teslim, `durum_gecmisi` + `spool_path` dahil | `:124` |
| `POST …/teslimler` | multipart yükleme (§2) | `:156-185` |
| `POST …/teslimler/{id}/kuru-kos` | `teslimi_isle(otomatik_uygula=False)`; yalnız `ISLENEBILIR_DURUMLAR`, aksi 409 | `:188` |
| `POST …/teslimler/{id}/uygula` | `teslim_uygula(uygulayan=<admin e-postası>)`; `onay` şart; yalnız `kuru_kosuldu`/`inceleme_bekliyor`, aksi 409 | `:225` |
| `GET …/teslimler/{id}/raporlar`, `…/raporlar/{ad}` | rapor dizinindeki `.csv`/`.txt` listesi ve indirme (yol bileşeni 400) | `:264`, `:276` |

Panel "Uygula"da mesai saatinde (09:00–18:00 TR) uyarı metni gösterir, karar kullanıcıda —
envanter kapısı eşzamanlı yüklemeye karşı muhafazakâr olduğundan uygulama mesai dışında önerilir.

## 6. Cevap dosyaları — `services/teslim_cevap.py`

SharePoint `cevap/` klasörüne yükleme 17.09'da kalktı. Dosyalar teslimin **rapor dizininde**
(`<spool>/<id>_raporlar`) üretilir; yönetici panelin rapor uçlarından indirip veri ekibine iletir.

| Dosya | İçerik | Üreten |
| --- | --- | --- |
| `eslesme_<teslim>.csv` | `Sheet`'teki her satır için `sistem_no, dosya_no, case_id, tracking_no, klasor_no_2, tku_no, case_party_id, durum (ESLESTI/ESLESMEDI), sebep` — Talep #9 (`ESLESME_BASLIKLARI`, `teslim_cevap.py:56`) | `eslesme_csv_uret` (`:193`); uygulama başarı yolunda `teslim_kutusu._eslesme_dene` (`:533`, çağrı `:1261`) |
| `ozet.txt` | `ozet_metni(sonuc)` + son satırda kapı kararı (+ gerekçe) | `teslim_kutusu._ozet_dosyasi_yaz` |
| `deger-havuzu-farki_<teslim>.csv` | `DEGER_HAVUZLARI` ↔ referans listeleri iki yönlü fark (`havuz, liste, yon, deger`); **fark yoksa dosya yok**, bayat kopya silinir | `havuz_farki_csv_yaz` (`teslim_cevap.py:377`); çağrı `teslim_kutusu._havuz_farki_dene` (`:553`) |
| `satir-raporu_<damga>.csv`, `kardes-foy-celiskileri_<damga>.csv` | aktarım scriptinin kendi raporları — yalnız sorunlu satır/çelişki varsa doğar | `scripts/hukdok_aktarim.py` |
| `kuru-kosu-ozeti.txt`, `uygulama-ozeti.txt` | iki koşunun `ozet_metni` çıktısı | `teslim_kutusu.py` |

Eşleşme dosyasında `sebep` **satır numarasıyla** eşlenir (aynı SistemNo dosyada iki kez
geçebilir) ve rapor dizinindeki **en yeni** `satir-raporu_*.csv`'den okunur (`_sebepleri_oku`,
`teslim_cevap.py:147`). CSV biçimi scriptle aynı: UTF-8 BOM + `;` (`_csv_yaz`, `:133`).
Eşleşme/havuz dosyası üretim hatası WARNING'dir, teslim durumunu değiştirmez.

## 7. İkinci faz sayfaları — `Düzeltme_Logu`, `DEGER_HAVUZLARI`, kapsam sayfaları

Hepsi `aktarimi_kos` içinde okunur (`scripts/hukdok_aktarim.py:3209`), `limit`ten
bağımsız; sayfa yoksa hata değil.

**`Düzeltme_Logu` (G112, `duzeltme_logunu_oku`, `scripts/hukdok_aktarim.py:1320`).** Her satır
bir (SistemNo, sütun) düzeltmesidir; "Gerekçe" değişen alanın `case_history.source` imzasına
provenance olarak eklenir, imza `HUKDOK_TESLIM_` ile başlamaya devam eder. Değişen sütunun
adı ya ayrı başlıktan ("Sütun", "Alan"…) ya da gerekçenin köşeli parantezli önekinden
(`[Hükmedilen Manevi] …`) okunur (`sutun_adi`, `:1376`); ikisi de yoksa satır yok sayılır.
Alan boşaltmanın **tek** yolu buradadır — **üçlü şart**: log Yeni Değer `(boş)` **VE**
`Sheet`'te o hücre gerçekten boş **VE** bizde dolu (`_bosaltma_talimatlari`, `:1423`). Partili
teslimde eksik sütun mevcut değeri **silmez** ("None = bu teslimde yok"). Boşaltılamayanlar
`BOSALTMA_DISI_ALANLAR` (`:1268`) = künye kaynakları (`_DUZELTME_KUNYE_KAYNAKLARI`, `:1246`:
`karar_no`/`karar_tarihi`/istinaf başvuran) + `BOSALTMA_YASAK_KART_ALANLARI` (`:926`) = içerik
modundaki `court` ve — G159'da içerik kümesinden çıkmasına rağmen — `sub_type` ("paket yazar,
silmez"); talimat satır raporuna düşer.

**`DEGER_HAVUZLARI` (G112, `services/teslim_cevap.py:94-142`).** Yedi havuz başlığı → altı
referans listesi eşlemesi (`HAVUZ_LISTE_ESLEMESI`, `:116-124`: İddia Edilen Kusur →
`alleged_faults`, İstinaf Karar Durumu → `appeal_decisions`, Yargıtay/Temyiz Onama Durumu →
`cassation_decisions`, Yerel Mahkeme Karar Durumu → `local_decisions`, Olay Türü →
`event_types`, Hükümdeki Rol → `judgment_roles`). G119'un iki listesi (`client_types`,
`service_types`) **eşlemede YOK**: `Müvekkil Tipi`/`Hizmet Türü` havuzu gelse de fark raporu
üretmez (bildirim sütunları `Sheet`te föy düzeyinde; tanınmayan değer aktarımın satır
raporuna düşer — aşağıda). Başlık satırı ilk 10 satırda aranır (gerçek paket 3. satırda
taşır, `:133-136`); uzun biçim ("Havuz / Sütun" + "Değer") önce, yoksa geniş biçim
(`:306-331`). Yalnız **rapor + bildirim**: referans listesine yazma **yok** — tahmin yasağı
(`:19-24`, `:294`). `alleged_faults` 04.09.2026'ya kadar bu yasak gereği boştu; dokuz değer
veri ekibinin DB-2026-001 yazılı bildirimiyle geldi ve `seed_data.ALLEGED_FAULTS` ile
seed'lendi (paketten değil, bildirimden; `9608031`). Aktarım `iddia_edilen_kusur`u yine
**metin** olarak yazar (`scripts/hukdok_aktarim.py:761`, `_metin_alan`) — liste doğrulaması
kart ekranı + bu fark raporu içindir.

**`Sheet` föy düzeyi kapalı listeler (G120, `scripts/hukdok_aktarim.py`).** DB-2026-002'nin
iki sütunu `Müvekkil Tipi` → `cases.muvekkil_tipi`, `Hizmet Türü` → `cases.hizmet_turu`
(`SUTUN_ADAYLARI` iki kayıt, `KART_ALANLARI` iki kayıt; başlık anahtarı MUVEKKILTIPI ≠
MUVEKKIL, taraf sütunuyla çapraz bağlanmaz). Değer eşlemesi AD bazlı, kanonik adların tek
kaynağı `seed_data.CLIENT_TYPES`/`SERVICE_TYPES` (literal kopya yok); tanınmayan değer ve
` ; ` ile çok değer `AlanHatasi` → alan yazılmaz, satır raporuna `tur=HATA`, föyün diğer
alanları işlenir (G104 deseni). Kardeş föy çelişkisi bu iki alanda **beklenen** durumdur
(bildirim: "föy başına değişir") — mekanizma neyse o, özel istisna yok. Okunan alan sayısı
bu ekle 42 (`SUTUN_ADAYLARI`, 54 başlık yazımı); veri ekibine giden liste
`docs/veri-teslim/BILGILENDIRME_2026-09-03.md` §3.2 (sürüm 1.1) ile birebir.

**DB-2026 bildirimi ve cevabı — tarihli şerh (04.09.2026).** Veri ekibinin Format
Değişiklik Bildirimi REV-2 on kalemdi (DB-2026-001…010; ilk geçerli paket
`HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx`); HukuDok aynı gün "hazır, bırakın" + beş cevap
verdi. Bizde iş çıkaran ikisi: DB-001 (`ALLEGED_FAULTS` 9 değer seed, `9608031`) ve DB-002
(G119 şema + G120 aktarım + G121 UI). Kod dokunulmadan kapananlar: DB-003 (on dört sütun
artık gelmiyor — "bu teslimde yok" sözleşmesi, mevcut değer korunur; `Arabuluculuk
Numarası` kimlik alanı değil, köprü `Dosya No`), DB-004 (`Karar_Asamalari`'nda `Önceki`
etiketi `ASAMA_ONCEKI` ile esas tarihçesine gider, `:1617-1623`; satırların gönderilmesi
istendi), DB-005 (kanonik karar listemiz = `seed_data` dört liste — 04.09'da 28/3/3/2; G151
ile **27/8/4/2**: `Kapalı`/`Derdest` yerelden çıktı, `Red/Usulden` + istinaf 5 + temyiz 1 girdi,
`managers/seed_data.py:427-467`; lehe/aleyhe ekseni yok), DB-006 (`Olay Türü`/`Hükümdeki Rol` veri ekibinde henüz üretilmiyor; NULL
meşru), DB-007 (`Uzmanlık Alanı` zaten `uzmanlik_alani`nın ikinci adayı, `:194`), DB-008
(ad alanları İlk Harf Büyük — taraf anahtarı `party_check.normalize_party_key` harf
duyarsız, `:1661`), DB-009/010 (tarih/tutar tipi ve serbest metin havuzları: değişiklik yok).
Ek sayfalar (`Kaldirilan_Sutunlar`, `S37_Kanonik`, `Yazim_Standardi`) okunmaz. Bildirimin
kendi metni repoda değildir; işlenmiş hâli bilgilendirme belgesi 1.1'dedir.

**`Silinen_Föyler` / `Kapsam_Dışı` (G113, `scripts/hukdok_aktarim.py:3014` `KAPSAM_SAYFALARI`,
`:3061` `kapsam_kayitlarini_oku`, `:3121` `kapsam_isaretlerini_yaz`).**
Föy **silinmez**, `case_foys.kapsam_durumu` (`SILINDI` | `KAPSAM_DISI`) + `kapsam_gerekcesi` +
`kapsam_tarihi` ile işaretlenir (`backend/models.py:336-339`; kolon op'u `database.py:921`
madde 40). İşaretli föy kardeş-föy uzlaşısına ve TKU ilişki hesabına katılmaz; ana sayfada
yeniden görünür ve kapsam sayfalarında yoksa işaret NULL'a çekilir (`:86-101`). Bizde olmayan
SistemNo ATLANDI raporuna düşer, koşu kırmızı olmaz.

### 7.1 Aktarımın yazma kuralları — G150–G159 (10.09.2026, `39fd10c`)

Kapı ve defter değişmedi; `aktarimi_kos`'un kart/aşama/föy yazma kuralları 08.09 planının
(`docs/plan/veri-ekibi-cevabi-karsilastirma-plani-2026-09-08.md`) kararlarıyla değişti.
Sözleşmedeki (§3–§7, §10) her cümlenin kod karşılığı burada.

**Aşama katmanı (G150, plan A1+A2; `asamalari_yaz` docstring `scripts/hukdok_aktarim.py:2720-2760`).**
Eski "aşamada satır varsa paket hiçbir şey yazmaz" kuralı kalktı. Kart başına, aşama başına:

- Kardeş föyler **alan bazında** uzlaştırılır (`_asama_uzlasisi`, `:2602`): imzaya yalnız
  DOLU alanlar girer (`_asama_imzasi`, `:2566-2587`; imza alanları `_IMZA_ALANLARI`,
  `:2552-2554` = mahkeme · esas · karar no · karar tarihi · karar durumu · başvuru tarihi),
  imza dışı alanlar ilk dolu (`_ILK_DOLU_ALANLARI`, `:2558-2560`). Boş hücre çelişki değildir;
  aynı alanda iki farklı dolu değer gerçek çelişkidir → aşama yazılmaz, çelişki raporuna düşer.
- Mevcut satırlara karşı uygulama (`_asama_satirini_uygula`, `:2932-2995`): içeriği birebir
  aynı satır varsa hiç (idempotent); konumdaki satır `dogrulama_durumu ∈ {BELGE, UYAP}` ise
  **korunur** (`stage_decisions.is_protected`, `managers/stage_decisions.py:430-432`;
  `update_stage_decision` bu satıra `ProtectedStageDecisionError` atar, `:168`, `:470-474`) +
  satır raporuna `ATLANDI` "belgeli aşama satırı korundu (…) — paket farkı: …" + WARNING +
  `asama_belgeli_korunan` sayacı (`:2961-2978`); **çok tur** (`_ikinci_tur_mu`, `:2915-2929`:
  esas VE karar tarihi farklı, dördü dolu, mevcut daha eski) → `add_stage_decision` ile
  `sira_no+1`, `asama_ikinci_tur`; aksi → **yerinde güncelleme** (`update_stage_decision`,
  `:435-490`: içerik alanları `CONTENT_FIELDS` `:360-363`, damga+imza tazelenir, fotoğraf
  `_resync_stage_photo` `:336`) + alan başına `case_history`
  `case_stage_decisions.<stage>.<sira_no>.<alan>` (`ASAMA_TARIHCE_ONEKI`, `:2563`). Paket
  kaynaklı ve elle girilmiş satır aynı yoldan güncellenir (kullanıcı kararı 06.09 §0);
  ayrımı yapan tek şey `dogrulama_durumu`. Silme yolu yok. Lokal kanıt G150 raporu: 04.09
  paketi 310 eklendi / 116 güncellendi, 12 bayat satır 0'a indi, ikinci koşu 0/0/0/0.

**Karar durumu havuzu ve büro durumu (G151, plan A4+A5).** `seed_data` dört liste 27/8/4/2
(`managers/seed_data.py:427-467`; `Kapalı`/`Derdest` yerelden çıktı, `Karar` bilerek yok).
Aktarımda `BURO_DURUMLARI = {KAPALI, DERDEST}` (`scripts/hukdok_aktarim.py:2122`,
`_buro_durumu_mu` `:2126`, toleranslı): büro durumu imzaya girmez (boş hücre gibi, `:2581`),
künyesiz satır (`_kunye_dolu`, `:2590-2600`) hiç yazılmaz, künyeli satır durumsuz +
"büro durumu, karar değil" şerhiyle (`BURO_DURUMU_SERHI`, `:2123`) yazılır; sayaç
`buro_durumu_atlanan`, INFO log. Havuz dışı öteki değerler G076 yolunda (durum boş + şerh +
WARNING). Mevcut kurulumdaki `Kapalı`/`Derdest` satırlarını `scripts/deger_havuzu_seed.py
--kaldir` kaldırır (kullanılan satır silinmez; prod'da deploy sonrası insan adımı).

**Kesim-sonrası kullanıcı koruması (G152, plan P2 — "paket kazanır"ın tek istisnası;
12.09.2026'da HER kart alanına genellendi).** `_kart_alanlarini_yaz` paket değeri bizdeki DOLU
değerden farklı olan her alan için `kesim_sonrasi_kullanici_kaydi(alan=...)` çağırır: kesim GÜNÜNÜN
başından (TR 00:00) itibaren `case_history.field_name == <alan>` (`status`, `esas_no`, `court`, ...;
panel yolu kolon adıyla yazar) ve `source` NULL **ya da** `AKTARIM_SOURCE_PREFIX` ile başlamayan
(`autoescape=True` — `_` LIKE jokeri) bir kayıt varsa alan yazılmaz, `korunanlar`a "<alan> korundu
(kullanıcı dd.mm.yyyy)" düşer; bizde BOŞ alan korunmaz — paket doldurur (kullanıcı kararı 12.09:
"elle düzeltilen doğru, boş olan dolsun"). Aynı kural `Düzeltme_Logu` `(boş)` talimatına da uygulanır
(kullanıcı kesimden sonra doldurduysa paket boşaltamaz); korunan `court` `sync_current_esas`a
geçmez (esas tarihçesine paket mahkemesi sızmaz). `_satiri_isle` bunu `korunan_alan` sayacına ve
satır raporuna `STATUS_KORUNDU_TURU = "KORUNDU"` ile yazar — `HATA` değil, `hata_sayisi`/çıkış
kodu/kapı etkilenmez. Gerekçe: 12.09 prod ölçümünde 30.07 sonrası 47 elle satır / 37 kart (status 20,
esas_no 18, court 10); yalnız-status kuralı 28 esas/mahkeme düzeltmesini geri alırdı. `kesim_tarihi`
None ise kural kapalı, TEK WARNING (`aktarimi_kos`). Kaynak §3 "Veri kesim tarihi";
CLI `--kesim-tarihi`. Elle yol imzası: `case_manager.PANEL_SOURCE = "panel"` (`:1041`),
`update_case(..., changed_by=)` tarihçeyi `changed_by or PANEL_SOURCE` + `source=PANEL_SOURCE`
ile yazar (`:1044`, `:1081-1082`), `update_case_tracking` `status` değişince aynı imzayla
(`:1891`, `:1934`). `source IS NULL` bilerek kullanıcı sayılır (dünkü imzasız panel kayıtları).

**Dosya No kökü → müvekkil, föy ↔ müvekkil bağı, "müvekkil değişti" (G153, plan M2+M4, 06.09 #28).**
Harita `DOSYANO_KOK_MUVEKKILI` (`:1097-1107`: 1 Axa · 2 Quick · 3 Ak · 5 Koru · 6 Sompo ·
7 Eureko · 8 HDI · 9 Anadolu · 8000 Nippon), `DOSYANO_KOK_HIZMETSIZ = "13"` (`:1108`),
`DOSYANO_KOK_HEKIM_ESIGI = 500` (`:1109`); kök `_dosya_no_koku` (`:1137`), `_kok_muvekkili`
(`:1154`). Eşleştirme sırası (`_ikinci_anahtarla_coz` docstring, `:1763-1790`): esas/tür →
**kök** (`_kokun_karti_mi`, `:1163`: kartın CLIENT anahtarlarının TAMAMI kökün sigortasını
içerir — ikiz hekim kartı sigortayı ortak müvekkil olarak da taşıdığından "içeren" yetmez;
marka sözcükleri `_sigorta_markasi`/`_KOK_MARKASI`, `:1123-1131`) → müvekkil adı. Kök bir
sigorta, `Müvekkil` hücresinin ilk parçası BAŞKA sigorta ise `_kok_muvekkil_celiskisi`
(`:1183`) satırı `KokMuvekkilCeliskisi` (`:346`) ile düşürür: hiçbir karta yazılmaz, rapor
`HATA` "kök/müvekkil çelişkisi", sayaç `kok_muvekkil_celiskisi`; hekim adı / boş hücre çelişki
değildir. Föy bağı `_foy_muvekkilini_bagla` (`:2216-2260`): `_taraflari_yaz`dan (`:2144`,
yalnız ekler) SONRA `Müvekkil` ilk parçasına eşit CLIENT satırı `foy_map.upsert_foy(case_party_id=…)`
ile (`managers/foy_map.py:175`, `_validated_party` `:108`; model `models.py:359`
`ON DELETE RESTRICT`), boş hücre mevcut bağı korur, ikinci koşu 0; bağ başka tarafa geçerse
satır raporu `MUVEKKIL_DEGISTI_TURU` (`:206`, `:2450`) + WARNING, eski CLIENT satırı silinmez.
"Taraf kaydı dondurma" diye bir işlem yoktur (sözleşme §4). Eşleşme CSV'sindeki `case_party_id`
kolonu (`services/teslim_cevap.py:221`, `:286`) `case_foys.case_party_id`'den okunduğu için
bu görevden itibaren dolu gelir. G154 cevaplı xlsx'i `--kart-esleme` haritasına çevirir
(`scripts/cevapli_kart_eslemesi.py`).

**DosyaNo `.00` eki, klasör listesinin ilk parçası, eski unvan istisnası (G178, ekibin 12.09 cevabı
§1/§3/§8).** MİCRO DosyaNo'su sondaki `.00` ekiyle gelir (`2.500.00`), 30.07 dışa aktarımındaki
kartların `klasor_no_2`'si eksiz (`2.500`); eşleşme anahtarı `_eslesme_anahtari` artık sondaki
`.00`'ı atar (`_DOSYANO_SIFIR_EKI`; kalan parça nokta taşımalı, `.01` AYRI dosyadır, `1.00`
dokunulmaz) — köprü haritası (`_dosya_no_haritasi`) ve paket tarafı aynı anahtarı kullandığından
`2.500` ↔ `2.500.00` tek anahtar; `scripts/kartsiz_foy_kart_ac.py` de `ha._dosya_no_parcalari`
üzerinden aynı anahtarı miras alır (05.09'da bu ek yüzünden 37 föye ikinci kart açılmıştı; 13.09
lokal ölçümü: `X` ve `X.00` farklı kartlarda 79 çift — birleştirme AYRI veri adımı). Kök çıkarımı
(`_dosya_no_koku`) ham değerden, değişmez. Belirsiz eşleşmede **beşinci anahtar** (12-15. adım,
`_ikinci_anahtarla_coz`): aday kartlardan `klasor_no_2` listesinin İLK parçası föyün DosyaNo'suyla
aynı olan kart — ekibin kuralı, 18 satırın 8 belirsizini tek başına çözdü (H-11235 → 794); sıra
esas/tür → kök → müvekkil adı → ilk parça, log `kriter=…+ilk parça`, satır raporu sebep metni
"… /ilk parça de ayırmadı" (her satırda denenir), gösterim ekibin gördüğü HAM DosyaNo.
`DOSYANO_KOK_ESKI_UNVANLARI` (2 → Corpus Sigorta = Quick'in eski unvanı, kök 27 20.07.2026'da
kapandı; 8 → Ergo Sigorta = HDI devri): `_kokun_markasi_mi` ile hem `_kok_muvekkil_celiskisi`
(çelişki DEĞİL, satır yazılır) hem `_kokun_karti_mi` (kök adımında kökün kartı sayılır) bunu
tanır; başka kökte aynı ad çelişki kalır. Test `tests/test_g178_dosyano_sifir_eki.py`.

**Tek aday künye kontrolü (Ek-5 › 10, 17.09).** Köprü TEK aday kart döndürdüğünde de künyeye bakılır
(`_tek_aday_kunye_celiskisi`): kartın esası VE mahkemesi föyünkiyle ikisi de dolu ve ikisi de farklıysa
satır bağlanmaz, `Künye çelişkisi: …` sebebiyle HATA'ya düşer (ön geçiş `_kart_id_tahmini` de satırı
uzlaşıya sokmaz); ekip doğru kartı `--kart-esleme` ile verir. Yalnız esas farkı (aynı mahkemede yeni
tur), yalnız mahkeme yazımı farkı, boş künye, föyün esasının kartın esas geçmişinde (`case_esas_numbers` /
`case_history`) geçmesi ya da kartın esas/mahkemesi için kullanıcı imzalı tarihçe satırı bulunması (G152: avukat
kartı yeni tura taşımış, alan koruması ayrıca işler) engellemez. Föy kaydıyla (`case_foys`) veya açık
haritayla bağlanan satıra uygulanmaz — orada künye farkı değişikliktir, bağlama sorusu değil. Sebep:
ekibin Corpus föylerine verdiği `2.554.00` uygulamada 24.07'de açılmış gerçek bir kartın numarasıydı;
15.09 paketi (16.09 prod) H-5441'i o karta bağlayıp künyesini ezdi (kart 14393). Kök 27 (Corpus'un
MİCRO dizisi, `27.00x.00`) `DOSYANO_KOK_MUVEKKILI`'de yok → Quick müvekkil koduyla gelen satır
kök/müvekkil kuralına hiç girmez (bekçi test). Ölçüm (17.09 lokal = 16.09 prod kopyası): mevcut
8.416 föyün 27'si bu kurala takılırdı — hepsi föy kaydıyla bağlı (etkilenmez); çoğu dava kartındaki
arabuluculuk föyü (Ek-5 › 08'in ayırma listesi). Test `tests/test_g064_aktarim_cekirdek.py`.

**Ekip cevaplarının kart düzeltmeleri prod id'siyle koşar (Ek-5, 17.09).** 13.09 düzenlemeleri
(`ekip_cevabi_1209.py` G179, `birlesik_kart_ayir.py` G180) yalnız lokal DB'de koşmuş, lokal 16.09'da prod
dump'ıyla yenilenince kaybolmuştu; G179'un sabit tabloları lokal id taşıdığından (14362-14364 SMOKE kartları
prod'da gerçek dosya) o script prod'da YENİDEN KOŞULMAZ. Aynı kararları Ek-5'in prod id'leriyle
`scripts/ekip_cevabi_1609.py` uygular (kart 14393 onarımı, `2.55x` klasör temizliği, 13.09 föy dönüşü,
mükerrer/yeni kart birleştirme, kapatma, ayırma, karar künyesi, son durum, ilişki); föyün kartı DB'den okunur.
`mukerrer_kart_birlestir.birlestir` bu iş için `esas_kontrolu=False` seçeneği aldı — yalnız adıyla verilen
çiftte (`CIFT_ISTISNALARI`). Kural: ekibe giden liste de, ekipten gelen düzeltmenin uygulanması da prod'dan.

**`Başvuru Tarihi` (G155, plan A6).** `case_stage_decisions.basvuru_tarihi`
(`models.py:297`; migrasyon madde 47, `database.py:1063`, koşullu `columns` op'u — kısıt yok).
Okuyucu `ASAMA_SUTUNLARI["basvuru_tarihi"] = ("Başvuru Tarihi",)` (`:2093`), imza alanı;
uzlaşı `_basvuru_tarihi_uzlasi` (`:2667-2685`): önce aşama sayfası, İstinaf'ta boşsa kardeş
föylerin Sheet "İstinaf Mahkeme Başvuru Tar." değeri (Temyiz'in Sheet yedeği yok). Fotoğraf
`_PHOTO_COLUMNS` ISTINAF → `cases.istinaf_basvuru_tarihi`, TEMYIZ → `cases.temyiz_basvuru_tarihi`
(`managers/stage_decisions.py:125`, `:136`). İki yazıcı salınımı kapısı
`asama_kaynakli_kart_alanlari` (`:2688`): paketin İstinaf satırı Başvuru Tarihi taşıyorsa Sheet
sütunu kart yolunda atlanır (`_kart_alanlarini_yaz(asama_kaynakli=…)`, `:2001-2002`);
`KART_ALANLARI["istinaf_basvuru_tarihi"]` durur (aşama satırı olmayan föyde Sheet karta gider).

**Yazım — `tr_title` DB-008 kuralı ve `sub_type` paket kazanır (G159, plan M6 + §5.3-C).**
`managers/reference_lists.tr_title` (`:107`): kelime sınırı boşluk + `(`/`-`/`/` sonrası;
noktalı kısaltma `X.Y.` büyük, `KISALTMALAR` (`:63`) kanonik, `BAGLACLAR` (`:57`: ve · ile ·
veya · adına · vb) küçük (ilk parça hariç), yabancı ad izi (`_YABANCI_IZI`, `:80`: Q/W/X ya da
I-ünlü komşuluğu) I/ı → i; `normalize_list_name` = `tr_title` (`:143`). Aktarımda
`ICERIK_KARSILASTIRMALI_ALANLAR = {"court"}` (`scripts/hukdok_aktarim.py:921`): `sub_type`
artık yazım farkında da yazılır (lokal ölçüm 4.521 → 196 YALNIZ_HARF çifti; kalan 196 kardeş
çelişkisi/kök çelişkisi kalıntısı), `court` yazımı bizde kalır (mahkeme adı kimliği
G067-G070). Boşaltma yasağı `sub_type` için sürer (`BOSALTMA_YASAK_KART_ALANLARI`, `:926`).
Tek seferlik DB dönüşümü `scripts/yazim_birligi.py` (G160; dry-run varsayılan, `--apply`,
tarihçeli; Sigortalı/Davalı İdare/istinaf-temyiz mahkemesi/avukat adlarına DOKUNMAZ — sözleşme
§11 DB-008 genişletme ricasının sebebi).

**Çoklu avukatlı kart (G158, plan M5).** `required_fields.COKLU_AVUKAT_ESIGI = 2` (`:49`),
`responsible_lawyer_name` tanımında `skip_when_lawyers_at_least` (`:73`): `case_lawyers` ≥ 2
iken boş kutu eksik alan sayılmaz (Python + SQL ikizi + `scripts/backfill_missing_required.py`).
Ayrıntı `dava-acma-akisi.md` §1.

**Çelişki raporu (G157, plan A7).** `services/asama_celiski_raporu.py` — 06.09 raporunun
üreticisi repoda; yer tutucu mahkeme adı ("daire no eksik") ayrı sınıf, E-8 "müvekkil yönü
farkı" etiketi (hata değil), cevaplı xlsx geri okuma.

### 7.2 TKU kart birleştirmesi — `scripts/tku_kart_birlestir.py` (11.09.2026)

Ekibin defterinde her müvekkil ayrı föydür; aynı davanın föyleri aynı TKU'yu paylaşır. Eski
aktarım bu föyleri müvekkil başına AYRI kartlara açmıştı. Hedef yapı sistemde zaten var
(bir kart, altında birden çok föy, üstünde birden çok müvekkil — lokalde 903 kart böyle);
script dağınık kalan grupları o şekle getirir. **Föyler değişmez, kartlar birleşir.**

- **Grup** = aynı `case_foys.tku_no` + aynı esas anahtarı + birden çok canlı kart
  (`gruplari_bul`). Esas anahtarı `case_relations_auto.esas_anahtari`: boşluk farkı yutulur,
  yer tutucu (`2021/`, `2014/???`) kimlik sayılmaz → o kart gruba girmez. TKU tek başına yetmez:
  ekip TKU'yu farklı davaları ilişkilendirmek için de kullanıyor (lokalde 480 grup farklı
  mahkeme/esas) — onlar `services/case_relations_auto.py` ile bağ olarak kalır.
- **Mahkeme uyumu** (`mahkeme_uyumu`): düz normalize eşitliği yoksa G067 yapısal kimliği
  (`court_name.parse_court_name`) — yer + kanonik tür + daire aynı, sıra aynı ya da bir tarafta
  yok. "Mahkemesi/Mahkemeleri", "(tüketici Mahkemesi sıfatıyla)" eki, eksik "1.", harf/aksan
  farkı yutulur; "Ankara 5." ≠ "Ankara 15.", yer/tür farkı, kimliği çıkmayan ad (güven YOK)
  eşleşme üretmez. Uyumsuz mahkeme ya da farklı dosya türü kart REDDEDİLİR ve rapora düşer
  (lokal kuru koşu 11.09: 184 birleşecek, 15 ret — 10 tür, 5 mahkeme; hepsi gerçek fark).
- **Taşıma yolu** G127'nin `mukerrer_kart_birlestir.birlestir`'i ile AYNIDIR (belge koruma,
  taraf tekilleştirme, aşama/esas tarihçesi, soft delete); yalnız `muvekkil_ayrimi=True` ile
  "müvekkil kümeleri aynı olmalı" koşulu gevşer, tarihçe alanı `tku_birlestirme`, silme
  gerekçesi "TKU kart birleştirmesi: …".
- **Kalan kart:** en çok belge → en çok föy → en eski id (`kalan_sec`). Bir kart birden çok
  grupta geçerse (çok TKU'lu kart) sonraki gruplarda kalan karta yeniden eşlenir.
- **Ofis dosya numarası kaybolmaz:** taşınan föy sönen kartın numarasını
  `case_foys.onceki_tracking_no`da taşır (migrasyon 49; ilk taşınma kazanır), arama bu kolu
  tarar (`case_manager._term_case_id_selects`), föy panelinde "eski ofis no" satırı olarak
  görünür. Sönen kartın kendi `tracking_no`su da üzerinde kalır (unique kısıt, yeniden verilmez).
- Varsayılan kuru koşu (rollback); `--rapor <csv>` plan/sonuç, `--tku`, `--limit`, `--apply --kim`.
  Test: `tests/test_tku_kart_birlestir.py`.

### 7.3 Tarihçe temizliği — `scripts/tarihce_temizligi.py` (11.09.2026, tek seferlik)

Aktarım paketleri ve yazım birliği turu her hücre yazımını `case_history`ye satır olarak
düşürdüğünden kart geçmişi paneli olay günlüğü değil dolgu izi gösteriyordu (lokal: 140.153
satır, kart başına ~10). Kullanıcı kararı: gerçek olay dışındaki otomatik satırlar silinir.
Kural (`karar`): otomatik imzalı (`HUKDOK_TESLIM*`, `yazim_birligi`) satır silinir; **istisna**
(1) `case_foys.sistem_no` föy bağlama satırı — AKTARIM provenance imzası
(`case_manager._is_aktarim_kaydi`, `required_fields.aktarim_kaydi_sql`) bu satırdan okunur, eksik
alan kovası buna bağlıdır; (2) `mukerrer_birlestirme`/`tku_birlestirme` izi; (3) mahkeme/esas/status
GERÇEK değişimi — esas `esas_anahtari` (yer tutucu kimlik değil), mahkeme `tku_kart_birlestir.
mahkeme_uyumu` (yapısal kimlik aynıysa biçim), status büyük/küçük harf farkı biçim. Kullanıcı imzalı
satıra dokunulmaz. `--apply` `--yedek <csv>` ister (silinen satırların dökümü). Lokalde uygulandı:
131.188 silindi, 8.965 kaldı (8.395 föy bağlama, 187 esas, 149 status, 36 mahkeme, 192 birleştirme,
6 kullanıcı); kova sayıları değişmedi. Sonraki paketler yine satır yazar (delta'da çok az); aktarımın
tarihçe yazım kapsamını daraltmak ayrı iş.

### 7.4 Ekip cevabı düzeltmeleri — `scripts/ekip_cevabi_1209.py` (13.09.2026, G179)

Veri ekibinin 12.09 cevabındaki kart id'li istekleri tek koşuda uygular; Ek-3 (`HUKDOK_CEVAP_EKI_3_2026-09-12.xlsx`,
repoya girmez, `--ek3`) + dosyadaki sabit tablolar (`SABIT_CIFTLER`, `SABIT_DUZELTMELER`, `SABIT_KAPATMALAR`; her kalemin
yanında kaynak satırı). Dört adım tek transaction'da, `--apply` yoksa geri alınır (`kos`): (1) çift kart — Ek-3 › 01'in
37 satırı (eski 30.07 kartı `2.500`, 05.09 kartı `2.500.00`; G178 öncesi `.00` eki yüzünden açılmıştı) + §3/Ek-2 › 03
özdeş çiftler; KALAN = 30.07 kartı / çiftin ilki, taşıma yolu `mukerrer_kart_birlestir.birlestir` (belge koruma, taraf
tekilleştirme, soft delete, föyde `onceki_tracking_no`); ön koşul reddederse (müvekkil kümeleri farklı — H-15496'nın
kartı iki müvekkilli Anadolu kartı) Ek-3 çiftinde kart birleşmez, yalnız föy 30.07 kartına taşınır (`_foy_tasi`); (2)
föy taşıma — Ek-3 › 02 "Önerdiğimiz kart" dolu 8 satır, taraf bağı hedefteki aynı adlı CLIENT'a, iki kartta
`case_history` `foy_tasima`; (3) kart düzeltmeleri — Ek-2 › 06 + §3 konu/hizmet: `muvekkil` (CLIENT adı + `clients`
bağı), `klasor_ekle` (mükerrersiz), `klasor`, `court`, `esas_no` (`case_manager.sync_current_esas`, boşaltma dahil),
`subject`/`hizmet_turu` (`case_subjects`/`service_types` listesinden kanonik ad, yoksa RET); eşit değer ATLANDI; (4)
kapatma — üst mahkeme aşamasının hatalı kopyası 4 HK kartı: belgeler ekibin gösterdiği gerçek dosyanın kartına
(`case_party_id=None`, `belge_tasima` tarihçesi), sonra soft delete (`api_delete_case` deseni); SMOKE/"Test İçin" 4
kart hedefsiz soft delete. İkinci koşu 0 (birleşmiş çift `delete_reason` "#kalan ", taşınmış föy hedefte, eşit alan,
kapalı kart). Uygulanmayanlar: 14393 "kontrol" (MİCRO teyidi), 28 "Rücu" kartı (liste yok; `bureau_type=Rücu`
föysüz AXA/Sompo kartlarının çoğu "İtirazın İptali"), 14321/14322 (esas farklı → ret). Tarihçe imzası
`changed_by=ekip_cevabi_1209`, `source="ekip cevabı 12.09.2026 (kim): kanıt"` — kesim-sonrası koruma bunu kullanıcı
kaydı sayar (paket bu alanları ezmez; ekibin kendi düzeltmesi olduğundan zaten eşit gelir). Lokal kuru koşu 13.09:
41 çift · 8 föy · 16 düzeltme · 8 kapatma (6 belge taşınır); `--apply` 13.09 gece uygulandı (canlı kart 14.363 → 14.315); yedek `C:\hukdok-veri\yedek\pre_g179_20260913.dump`.
Test `tests/test_g179_ekip_cevabi_1209.py`.

**Birleşik kartları ayırma — `scripts/birlesik_kart_ayir.py` (13.09.2026, G180).** Ekip §8/Ek-3 › 03: 30 kart
farklı tür/esas föyleri (arabuluculuk + dava, soruşturma + ceza davası, aynı türde farklı esas) tek kartta taşıyor;
kullanıcı kararı 13.09 (iki kez teyit): ekibin modeli — AYRI kart + "ilişkili dosya" bağı. Bu kartlar TKU birleştirmesinden
GELMİYOR (föylerde `onceki_tracking_no` yok): `scripts/kartsiz_foy_kart_ac.py` aynı DosyaNo'daki ARB + HUKUK föylerini
bilerek tek karta koyar (`TUR_ONCELIGI`), aktarımın DosyaNo köprüsü de öyle — MİCRO iki aşamaya aynı DosyaNo verir.
Script: kart listesi `--ek3` (Ek-3 › 03 `Kart` + Ek-3 › 02'de "Önerdiğimiz kart" boş satırların "Bağlı olduğu kart"ı;
`ek3_kartlari`) ya da `--kart`; föyün `ham_veri`si `hukdok_aktarim._sutun_indeksleri` ile HamSatir'a çevrilir
(`foy_satiri`), grup anahtarı (dosya türü `ANA_TUR_ESLEMESI`, `case_relations_auto.esas_anahtari`); kartın kendi grubu
(kart.file_type, esas) birebir, yoksa kartın türündeki en büyük grup (`gruplari_bul`); öteki her grup için yeni kart
(`yeni_kart_ac`: `kartsiz_foy_kart_ac.kart_adaylari` + `ofis_numarasi`, `klasor_no_2` kalan kartla PAYLAŞILIR — sonraki
aktarım köprüde iki kart görür, esas + tür ikinci anahtarı ayırır; esas `sync_current_esas`, taraflar
`_taraflari_yaz`, föy ↔ müvekkil `_foy_muvekkilini_bagla`), `case_relations` (`source=kalan`, `target=yeni`,
`AYRISTIRILAN`, çift başına bir satır), iki kartta `case_history` `kart_ayirma`, `refresh_missing_required`. Belgeler
kalan kartta KALIR (hangi föyün belgesi bilinmiyor). RET: `ham_veri`siz föy, `onceki_tracking_no` taşıyan föy (sönen
kart — elle), grup birden çok DosyaNo'ya bölünüyor, müvekkil boş. Tek transaction, `--apply` yoksa geri alınır; tek
gruplu kart ATLANDI → ikinci koşu 0. Lokal kuru koşu 13.09 (G179 uygulanmış DB): 30 kart → 23 ayrıldı / 23 yeni kart ·
6 atlandı (G179'un föy taşımaları sonrası tek föy/tek grup: 4370, 13897, 14287, 14328, 14334, 15276) · 1 ret (15291
G179'da 14333'e birleşmişti); `--apply` 13.09 gece uygulandı (canlı kart 14.315 → 14.338, 23 ilişki). Test `tests/test_g180_birlesik_kart_ayir.py`.

## 8. Log sözleşmesi ve bildirim

- Deneme/yapı düzeyi başarısızlık **WARNING** — `reddedildi` dahil (yapı hatası veri ekibinin
  düzelteceği şeydir, nöbetçi alarmı değil), eşleşme/havuz dosyası üretim hatası.
- Nihai `basarisiz` teslim başına **TEK ERROR**. Envanter kapısı kırmızı çıktığında o ERROR'u
  `aktarimi_kos` zaten basar ("Aktarım GERİ ALINDI", `scripts/hukdok_aktarim.py:2267-2272`);
  servis ikinci ERROR yazmaz, yalnız defteri işler (`teslim_kutusu.py:38-42`, `:933-940`).
- Açılış toparlaması (`boot_toparla`) istisnası tek WARNING.
- Bildirim (`bildir`, `:534-581`): `inceleme_bekliyor` / `reddedildi` / `basarisiz` / `uygulandi`
  geçişlerinde `ADMIN_EMAILS` kümesine uygulama içi bildirim, `type="veri_teslim"`,
  `dedupe_key = teslim:<id>:<durum>:<alıcı>` (alıcı sonda — G082 dersi, `:439-443`).
  `yinelenen` bildirim üretmez. Değer havuzu farkı ayrı bildirimdir (`teslim:<id>:havuz:<alıcı>`,
  `:469-503`). Bildirim yan üründür: her hatası WARNING ile yutulur, durum makinesi bozulmaz.

## 9. Bilinen sınırlar ve açık kalemler

- **Kart yaratılmaz.** Eşleşmeyen satır raporda kalır; kart açmak ofis dosya numarasını
  SharePoint sayacından atomik tahsis ister, çevrimdışı hattın işi değildir
  (`scripts/hukdok_aktarim.py:44-47`). Eşleşme köprüsü DosyaNo ↔ `klasor_no_2`.
- **İlk teslim daima inceleme** (`ilk_teslim` kuralı); her teslimi zaten insan "Uygula" der. Zincir o teslimden başlar: "Önceki teslim: —" yalnız defter
  boşken başlangıçtır (G156, §3); prod'da başlangıç paketi 04.09'dur ve teslim hattından
  (defter üzerinden) uygulanmalıdır — süreç adımı, kod değil (plan 08.09 K3).
- **`DEGISIKLIK_OZETI` yokken zincir denetlenmez ve kapı durmaz:** `zincir_tamam=NULL`
  (`services/teslim_kutusu.py:1141`), `kapi_ihlalleri` yalnız `is False`'u `zincir_eksik`
  sayar (§4 tablosu) — sayfasız paket öteki eşiklerin içindeyse kapı `otomatik` der.
  Sözleşme bunu açıkça söyler ("her teslime ekleyin"); NULL'ı da inceleme saydırmak
  plan §8'de açık kalem.
- **Frontend'de kapsam dışı föy rozeti yok**: `get_case` çıktısındaki `foyler[]`
  (`kapsam_durumu` dahil) hazır, kart panelinde gösterim sonraki tur.
- **SharePoint teslim klasörü yolu kapalıdır (17.09.2026, kullanıcı kararı):** veri ekibine
  klasör bağlantısı verilmez; paket bize iletilir, yönetici yükler (ya da CLI). Hanyaloğlu
  tenant'ındaki `hukdok_arsiv` site'ında ve LexisBio site'ındaki `03_VERI_TESLIM` klasörleri
  (03.09/08.09 hazırlığı) ile prod `.env`'de kalmış olabilecek `TESLIM_SHAREPOINT_*` /
  `SHAREPOINT_FOLDER_TESLIM_NAME` satırları kod tarafından okunmaz — temizliği insan adımıdır.
- Ters yön (bizim veriyi sigorta şirketi Excel'ine işlemek), WhatsApp/e-posta ekini otomatik
  okuma, mükerrer kart birleştirme (D6) — bilinçli kapsam dışı (plan §5).

## 10. Nereye bakmalı

| Konu | Dosya |
| --- | --- |
| Durum makinesi, kapı, bildirim, açılış toparlaması | `backend/services/teslim_kutusu.py` |
| Eşleşme CSV, `DEGER_HAVUZLARI` farkı | `backend/services/teslim_cevap.py` |
| Gerçek yazma yolu, envanter kapısı, `Düzeltme_Logu`, kapsam sayfaları | `backend/scripts/hukdok_aktarim.py` (`backend/scripts/README.md`) |
| Admin uçları | `backend/routes/admin.py` |
| Defter modeli + migrasyon madde 39/40 | `backend/models.py:1080`, `backend/database.py:913-919` |
| Açılış toparlama thread'i | `backend/api.py:246-251` |
| Veri ekibine verilen sözleşme | [`docs/veri-teslim/SOZLESME.md`](../veri-teslim/SOZLESME.md) |
| Plan ve açık kalanlar | [`docs/plan/veri-teslim-otomasyonu-plani-2026-09-03.md`](../plan/veri-teslim-otomasyonu-plani-2026-09-03.md) |
| Veri ekibine verilen bilgilendirme (sütun/sayfa/değer ayrıntısı, makine-okur özet) | [`docs/veri-teslim/BILGILENDIRME_2026-09-03.md`](../veri-teslim/BILGILENDIRME_2026-09-03.md) (sürüm 1.1; dosya adı sabit — yol veri ekibinde) |
| Aşama katmanı, havuz, status koruması, kök→müvekkil, başvuru tarihi, yazım (§7.1) | `backend/scripts/hukdok_aktarim.py`, `backend/managers/stage_decisions.py`, `backend/managers/case_manager.py:1041-1082`, `backend/managers/reference_lists.py` (`tr_title`), `backend/managers/seed_data.py:427-467` |
| Testler | `backend/tests/test_g107_teslim_kutusu.py`, `test_g108_teslim_admin_uclari.py`, `test_g110_teslim_cevap.py`, `test_g112_duzeltme_logu.py`, `test_g113_kapsam_disi_foy.py`, `test_g120_aktarim_muvekkil_hizmet.py`, `test_teslim_klasoru_kaldirildi.py` (kaldırılanın bekçisi); §7.1 kuralları: `test_g150_asama_kurali.py`, `test_g151_havuz_kurali.py`, `test_g152_status_koruma.py`, `test_g153_dosyano_koku.py`, `test_g155_basvuru_tarihi.py`, `test_g156_delta_ve_zincir.py`, `test_g159_tr_title.py` |
