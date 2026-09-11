# Veri teslim hattı — SharePoint gelen kutusu → defter → 04:00 kapısı → cevap paketi

> **Son doğrulama: 2026-09-04 · 88409da** — §1 "Site/kimlik" satırı, §2 madde 2/5 ve §9 prod kurulumu
> 2026-09-08 · G147 ile yeniden doğrulandı; §3 doğrulama/özet satırları, §4 kapı, §7 `Düzeltme_Logu`
> ve kapsam referansları ile **§7.1 (aktarımın yazma kuralları, G150–G159)** 2026-09-10 · G161 ile
> `39fd10c` koduna göre yeniden doğrulandı (o bölümlerin satır numaraları bu commit'e aittir; diğer
> bölümler 88409da/G147 satırlarını taşır). Her iddia koddan doğrulanmıştır. Kod ile çelişirse kod haklıdır — bu dosyayı düzelt.
> Veri ekibine verilen dış sözleşme ayrı dosyadadır:
> [`docs/veri-teslim/SOZLESME.md`](../veri-teslim/SOZLESME.md) (kod yolu içermez).

Veri ekibi (büro tarafı, MicroKolayOfis master'ını temizleyen ekip) teslim paketini
(`HUKDOK_TESLIM_*.xlsx`) bir SharePoint klasörüne bırakır; hat dosyayı deftere alır, yapısını
doğrular, **kuru koşturur**, kapı eşiklerine vurur ve eşik içindeyse gece 04:00'te kendisi
uygular; her uygulanan teslim için SharePoint'e bir cevap paketi geri yükler. İnsan yalnız
eşik dışı durumlarda ("inceleme bekliyor") devreye girer. Gerçek yazma yolu
`scripts/hukdok_aktarim.aktarimi_kos`'tur — hat onu yalnız import eder, değiştirmez
(`backend/services/teslim_kutusu.py:15-17`).

```
veri ekibi ──xlsx──▶ SharePoint <SHAREPOINT_FOLDER_TESLIM_NAME>/gelen/
                            │  gece 04:00 TR (lider worker) · boot telafisi · admin "Dosya yükle"
                            ▼
                 sharepoint_tara  (list_folder_children → id@eTag eleme → indir → sha256)
                            │
                            ▼
              aktarim_teslimleri defteri  +  spool  <TESLIM_SPOOL_DIR>/<id>_<dosya>
                            │
   alindi → dogrulandi → kuru_kosuldu → [kapı] → uygulaniyor → uygulandi ──▶ cevap/<teslim>/
                │              │                      │                        (eşleşme CSV,
            reddedildi   inceleme_bekliyor        basarisiz                     özet, raporlar)
                          (admin "Uygula")
```

## 1. İniş alanı — klasör, ad kalıbı, anahtar

| Ne | Değer | Kod |
| --- | --- | --- |
| Klasör kökü | env `SHAREPOINT_FOLDER_TESLIM_NAME`; tanımsızsa `03_VERI_TESLIM` | `services/teslim_kutusu.py:154`, `:1010-1013`; `.env.example:27-29` |
| Gelen alt klasörü | `<kök>/gelen` | `services/teslim_kutusu.py:155` |
| Cevap alt klasörü | `<kök>/cevap/<teslim adı uzantısız>` — **yalnız env tanımlıysa**, varsayılan türetilmez | `services/teslim_cevap.py:79`, `:154-159` |
| Dosya adı kalıbı | `^HUKDOK_TESLIM_.*\.xlsx$`, harf duyarsız; dışındakiler `atlanan` sayılır | `services/teslim_kutusu.py:157`, `:1051-1054` |
| Açma/kapama anahtarı | admin paneli `veri_teslim_otomasyonu`, **varsayılan KAPALI**; env'de değil | `services/app_settings.py:50-58`, `:155-157` |
| Spool dizini | env `TESLIM_SPOOL_DIR`; tanımsızsa `<backend>/data/teslim_spool` (konteynerde `/app/data` volume'u → recreate'i atlatır) | `services/teslim_kutusu.py:213-225`; `.env.example:44-46` |
| **Site/kimlik** (G147) | Teslim hattının üç Graph çağrısı (gözcü listeleme + indirme, cevap yükleme) `config_type="teslim"` ile gider — tek sabit `TESLIM_SP_CONFIG`. Kimlik: `TESLIM_SHAREPOINT_TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET` (secret önce vault, sonra env); **üçünden biri bile boşsa arşiv kimliğine (`SHAREPOINT_*`) düşer, süreç başına TEK INFO**, istisna yok. Site: `TESLIM_SHAREPOINT_SITE_URL` (boşsa `SHAREPOINT_SITE_URL`); drive adı `TESLIM_SP_DRIVE_NAME` > `SP_DRIVE_NAME` > `Belgeler`. Site+drive çözümü `(token, config_type)` anahtarlı `lru_cache(maxsize=4)` — iki config art arda koşunca ikinci turda Graph'a gidilmez; 401'de çağrının KENDİ config'i yenilenir. Arşiv, ofis-no sayacı, `log` listesi, outbox, e-posta ve hukukbot export'u `default` (LexisBio) ile aynen kalır; klasör adları site'tan bağımsızdır | `services/teslim_kutusu.py:171-178`, `:1274`, `:1287`; `services/teslim_cevap.py:532`; `sharepoint/auth_graph.py:19-31`, `:101-115` (`_read_credentials`), `:118-160` (`_get_msal_app` düşüş + INFO `:135-143`); `sharepoint/sharepoint_uploader_graph.py:17-40` (`_site_url_for`/`_drive_name_for`), `:125-142` (`_with_fresh_token_on_401`), `:145-209` (`_get_site_and_drive_id`); `.env.example:31-48` |

Anahtar kapalıyken: SharePoint'e ne bakılır ne yazılır (gözcü ve cevap yüklemesi INFO ile
atlanır), gece turu hiçbir durum değiştirmez; **elle yükleme ve elle "Uygula" çalışmaya devam
eder** (`services/app_settings.py:35-39`, `teslim_kutusu.py:1043-1045`, `:1145-1147`,
`teslim_cevap.py:487-489`).

Cevap tarafında ikinci bir kapı daha var: yazma hedefinin kökü env'den **açıkça** gelmek
zorundadır; okuma tarafındaki `03_VERI_TESLIM` varsayılanı yazma için türetilmez (env yoksa
INFO + atlanır, defter değişmez). Gerekçe modül şerhinde: cevap dosyaları ortak arşive
yazılır, kurulumu yapılmamış hedefe varsayılanla yazılmaz; aynı kapı gerçek Graph kimliği
taşıyan lokal konteynerde koşan testlerin prod SharePoint'e dosya bırakmasını da önler
(`services/teslim_cevap.py:30-40`, `:490-496`).

## 2. Gözcü — `sharepoint_tara`

`services/teslim_kutusu.py:1259-1305`. Sıra:

1. Anahtar kapalıysa listelemeden `{"yeni":0,"yinelenen":0,"atlanan":0}` döner (`:1270-1272`).
2. `sharepoint_uploader_graph.list_folder_children(<kök>/gelen, config_type=TESLIM_SP_CONFIG)`
   (`:1274`) — G109'da eklenen tek yeni Graph çağrısı: `GET /drives/{drive}/root:/{folder}:/children`,
   `$select=id,name,size,eTag,file,lastModifiedDateTime`, `$top=200`, `@odata.nextLink` sonuna
   kadar izlenir, yalnız `file` anahtarlı öğeler döner. **Klasör yoksa (404) boş liste + WARNING** —
   "klasör henüz açılmadı" bir kurulum eksiğidir, arıza değil; diğer HTTP hataları yükselir
   (`backend/sharepoint/sharepoint_uploader_graph.py:483-518`). **Config notu (G147):** çağrı
   `"teslim"` config'iyle gider — `TESLIM_SHAREPOINT_*` tanımlıysa Hanyaloğlu tenant'ındaki site ve
   o tenant'ın token'ı, tanımsızsa arşiv kimliği/site'ı (§1 "Site/kimlik"); klasör yolu değişmez.
3. Ad kalıbına uymayan dosya `atlanan` (`teslim_kutusu.py:1051-1054`).
4. **Ucuz eleme:** `sharepoint_item_id` kolonuna driveItem id'si ile eTag birlikte
   (`<id>@<eTag>`, tırnaksız) yazılır; aynı anahtar defterdeyse dosya **indirilmez** ve
   `yinelenen` sayılır (`teslim_kutusu.py:1016-1020`, `:1055-1058`). eTag değiştiyse (dosya
   yerinde güncellendi) indirilir; içerik aynıysa `teslim_kaydet` sha256 ile zaten `yinelenen`
   satırı açar. Ayrı eTag kolonu yok — G109'da model kapsam dışıydı (`:56-63`).
5. `download_file_from_sharepoint(..., config_type=TESLIM_SP_CONFIG)`
   (`sharepoint_uploader_graph.py:453-474`; çağrı `teslim_kutusu.py:1287`) →
   `teslim_kaydet(kaynak="sharepoint")` (`teslim_kutusu.py:1288-1291`).

Tek dosyanın indirme/kayıt hatası **WARNING**, tur sürer; **listeleme** hatası yükselir ve
tur düzeyindeki kararı çağıran verir — gece turu TEK ERROR basar ve bekleyenleri yine işler,
boot telafisi tek WARNING ile yutar (`teslim_kutusu.py:1064-1068`, `:1150-1155`, `:1200-1202`).

Yedek giriş yolu: admin panelden multipart yükleme `POST /api/admin/aktarim/teslimler` —
yalnız `.xlsx` (aksi 400), 50 MB üstü 413, `teslim_kaydet(kaynak="yukleme")` +
`teslimi_isle(otomatik_uygula=False)` → 201 `{id, durum}`; bozuk/`Sheet`'siz dosya HTTP
hatası değil `201 + durum="reddedildi"`dir (`backend/routes/admin.py:39`, `:156-185`).

## 3. Defter — `aktarim_teslimleri`

Model `backend/models.py:1080` (`AktarimTeslimi`), `UploadOutbox` deseninin kardeşi. Kolonlar
(`models.py:1110-1135`):

| Kolon | Anlamı |
| --- | --- |
| `dosya_adi`, `sha256`, `kaynak` (`sharepoint` \| `yukleme`) | kimlik; `sha256` içeriğin kimliğidir |
| `sharepoint_item_id` | `<driveItem id>@<eTag>` ucuz-eleme anahtarı; yükleme yolunda NULL |
| `spool_path` | `<spool>/<id>_<dosya_adi>` |
| `durum`, `durum_gecmisi` (JSON `[{"durum","at","not"}, …]`) | durum makinesi + her geçişin zaman damgalı izi (`teslim_kutusu.py:307-319`) |
| `onceki_teslim_adi`, `zincir_tamam` | `DEGISIKLIK_OZETI` "Önceki teslim" + o teslim defterde `uygulandi` mı (NULL = özet sayfası yok) |
| `okunan`, `islenen`, `atlanan`, `hata_sayisi`, `alan_degisikligi`, `kart_degisen`, `envanter_denk` | `AktarimSonucu` sayaçları — kuru koşu yazar, gerçek uygulama üzerine yazar (`:349-356`) |
| `kapi_karari` (`otomatik` \| `inceleme`), `kapi_gerekcesi` | kapı sonucu; gerekçe `;` ayraçlı ihlal listesi |
| `rapor_dizini` | `<spool>/<id>_raporlar` (`:329-334`) |
| `cevap_yuklendi` | cevap paketi SharePoint'e tam gitti mi (NOT NULL, default false) |
| `uygulayan` | admin e-postası ya da `gece-job` (`:176`) |
| `hata_mesaji` | `basarisiz`/`reddedildi` sebebi, ≤ 2000 karakter (`:199`) |
| `created_at`, `updated_at`, `done_at` | `done_at` nihai duruma geçiş anı (`:318-319`) |

İki index modelde değil migrasyonda (G041 kuralı — tabloyu `create_all` yaratır,
`("table", …)` op'u ölü kod olurdu), `backend/database.py:913-919` madde 39:

- `uq_aktarim_teslimleri_sha256` — **kısmi** UNIQUE, `WHERE durum <> 'yinelenen'`: aynı içerik
  ikinci kez gelince mevcut satıra dokunulmaz, izlenebilirlik için yeni bir `yinelenen` satırı
  açılır (notunda ilk id), spool'a yazılmaz; yarışta IntegrityError yakalanıp ikinci kayıt
  `yinelenen`e düşer (`teslim_kutusu.py:703-741`, `:754-767`).
- `idx_aktarim_teslimleri_bekleyen` — `created_at` üzerinde, dört bekleyen durumla partial;
  gece turunun ve boot telafisinin tek tarama deseni.

### Durum makinesi

`services/teslim_kutusu.py:125-151`:

| Durum | Anlamı | Kim geçirir |
| --- | --- | --- |
| `alindi` | dosya deftere ve spool'a girdi | `teslim_kaydet` (`:703`) |
| `yinelenen` | aynı sha256 daha önce alınmış; nihai, işlenmez, bildirim üretmez | `teslim_kaydet` |
| `reddedildi` | yapı doğrulaması geçemedi — nihai, **WARNING** + bildirim | `teslim_dogrula` (`:770-797`) |
| `dogrulandi` | `Sheet` var, zorunlu başlıklar var, zincir bakıldı | `teslim_dogrula` |
| `kuru_kosuldu` | `aktarimi_kos(dry_run=True)` koştu; sayaçlar deftere, raporlar spool'a | `teslim_kuru_kos` (`:800-827`) |
| `inceleme_bekliyor` | kapı eşik dışı — insan kararı; bildirim | `kapi_degerlendir` (`:865-885`), `acilis_toparla`, `_tek_uygulama_incelemeye` |
| `uygulaniyor` | gerçek yazım sürüyor — **çökme izi**, commit'li (`:910-911`) | `_teslim_uygula` (`:899-941`) |
| `uygulandi` | commit oldu; nihai, bildirim, cevap paketi denenir | `_teslim_uygula` |
| `basarisiz` | uygulama istisnası ya da envanter kapısı geri aldı — nihai, **TEK ERROR** + bildirim | `_basarisiz` (`:415-423`) |

Geçişler tek yönlüdür; kapı `otomatik` derse durum **değişmez** (`kuru_kosuldu` kalır,
uygulama ayrı adımdır), `inceleme_bekliyor`dan yeniden değerlendirme geriye gitmez — yalnız
karar/gerekçe tazelenir (`:865-871`). `teslimi_isle` (`:944-972`) doğrula → kuru koş → kapı →
(`otomatik_uygula` ve kapı `otomatik` ise) uygula zincirini tek çağrıda yürütür; nihai ya da
`uygulaniyor` satıra **dokunmaz**, mevcut durumu döner.

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
ihlalde durup diğerleri gizlenmesin. Boş liste = `otomatik`.

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
`.env.example:32-43` üçünü yorumlu, varsayılanlarıyla taşır). Recreate'siz `.env` değişikliği
yine gelmez ama admin paneli `esikler` alanında anlık değeri görür (`routes/admin.py:101-121`).
Sayı olmayan değer WARNING + varsayılan (`teslim_kutusu.py:228-236`).

`KAPI_KURALLARI` dışında iki gerekçe etiketi daha `kapi_gerekcesi`ne yazılır:
`uygulama_kesildi` (açılışta `uygulaniyor` bulunan satır, `teslim_kutusu.py:975-1003`) ve
`tek_uygulama` (`:159`, aşağıda §5).

## 5. Zamanlama — gece turu, boot telafisi, gündüz

**Gece turu `gece_turu`** (`services/teslim_kutusu.py:1136-1161`) APScheduler'a `id="veri_teslim"`,
`CronTrigger(hour=4, minute=0, Europe/Istanbul)`, `misfire_grace_time=3600` ile kayıtlıdır ve
**yalnız lider worker'da** koşar (`backend/api.py:232-239`; lider bloğu `:185`). 04:00'ün
gerekçesi kodda: host `pg_dump`'ı (03:30 TR) bitmiş olur = doğal geri dönüş noktası; 00:00
rapor ve 02:30 dönüşüm retry'ı ile çakışmaz; 06:00 süre taramasından önce biter; envanter
kapısı eşzamanlı yüklemeye karşı muhafazakâr olduğundan mesai dışı şarttır (`api.py:227-231`).
Tur sırası:

1. anahtar kapalıysa çık (hiçbir durum değişmez, `teslim_kutusu.py:1145-1147`);
2. `acilis_toparla` — `uygulaniyor`da kalmış satırları `inceleme_bekliyor`a düşürür (`:975-1003`);
3. `sharepoint_tara` — hata **tur başına TEK ERROR**, bekleyenlerin işlenmesini engellemez
   (dün indirilen paket bugün yine uygulanabilir, `:1150-1155`);
4. `alindi` / `dogrulandi` / `kuru_kosuldu` satırlar `created_at` sırasıyla
   `teslimi_isle(otomatik_uygula=True)` ile — `inceleme_bekliyor` satırlarına **dokunulmaz**
   (insan bekliyor; her gece 90 sn'lik kuru koşuyu tekrarlamak boşuna, `:146-148`);
5. **aynı turda en fazla BİR teslim uygulanır**: ilki uygulandıysa sonrakiler
   `otomatik_uygula=False` ile koşar ve kapı "otomatik" dese bile `tek_uygulama` gerekçesiyle
   `inceleme_bekliyor`a alınır + bildirim (`:1091-1133`);
6. `uygulandi` + `cevap_yuklendi=false` kalan teslimlerin cevap paketi yeniden denenir — bu
   turda uygulanan hariç, az önce denendi (`:1159`, `:1164-1179`).

Otomatik uygulama `uygulayan="gece-job"` imzasıyla yapılır (`teslim_kutusu.py:176`, `:967-968`).

**Boot telafisi `boot_catch_up`** (`teslim_kutusu.py:1182-1202`): lider açılışında daemon
thread'de bir kez (`api.py:257-262`; `deadline_scanner.boot_catch_up_scan` deseni,
`services/deadline_scanner.py:469`). `acilis_toparla` anahtardan **bağımsız** koşar (kesilmiş
elle uygulama da toparlanmalı); anahtar açıksa tarama + yalnız `alindi`/`dogrulandi`
satırlara `teslimi_isle(otomatik_uygula=False)`. **Uygulama yalnız cron'dadır**;
`kuru_kosuldu` satırlar her restart'ta yeniden kuru koşturulmaz (`teslim_kutusu.py:149-151`).
Her istisna tek WARNING ile yutulur — thread'den taşan istisna kimseye ulaşmaz, 04:00 turu
asıl iştir.

**Gündüz (admin paneli, "Veri Teslimleri" sekmesi, `frontend/src/components/admin/DeliveryInboxCard.tsx`):**

| Uç | Ne yapar | Kod |
| --- | --- | --- |
| `GET /api/admin/aktarim/teslimler` | liste (en yeni önce, `limit` 1–500) + `esikler` + `etkin` | `routes/admin.py:101-121` |
| `GET …/teslimler/{id}` | tek teslim, `durum_gecmisi` + `spool_path` dahil | `:124-129` |
| `POST …/teslimler` | multipart yükleme (§2) | `:156-185` |
| `POST …/teslimler/{id}/kuru-kos` | `teslimi_isle(otomatik_uygula=False)`; yalnız `ISLENEBILIR_DURUMLAR`, aksi 409 | `:188-222` |
| `POST …/teslimler/{id}/uygula` | `teslim_uygula(uygulayan=<admin e-postası>)`; `onay` şart; yalnız `kuru_kosuldu`/`inceleme_bekliyor`, aksi 409 | `:225-261` |
| `GET …/teslimler/{id}/raporlar`, `…/raporlar/{ad}` | rapor dizinindeki `.csv`/`.txt` listesi ve indirme (yol bileşeni 400) | `:264-308` |
| `POST /api/admin/aktarim/tara` | **yer tutucu** — G109 gözcüsünü ÇAĞIRMAZ, sıfır + `not` döner (açık kalem, §9) | `:311-325` |

Panel "Uygula"da mesai saatinde (09:00–18:00 TR) uyarı metni gösterir, karar kullanıcıda
(`DeliveryInboxCard.tsx:136`, `:492-497`). Elle "Uygula" anahtardan bağımsızdır.

## 6. Cevap paketi — `services/teslim_cevap.py`

Her `uygulandi` teslim için `<kök>/cevap/<teslim adı uzantısız>/` altına (`:78-79`,
`:149-159`) rapor dizinindeki **bütün** `.csv`/`.txt` dosyaları yüklenir (`:460-468`,
`:519-526`):

| Dosya | İçerik | Üreten |
| --- | --- | --- |
| `eslesme_<teslim>.csv` | `Sheet`'teki her satır için `sistem_no, dosya_no, case_id, tracking_no, klasor_no_2, tku_no, case_party_id, durum (ESLESTI/ESLESMEDI), sebep` — Talep #9 (`ESLESME_BASLIKLARI`, `:81-86`) | `eslesme_csv_uret` (`:242-290`), yükleme anında |
| `ozet_<teslim>.txt` | `ozet_metni(sonuc)` + son satırda kapı kararı (+ gerekçe); rapor dizinindeki `ozet.txt`in yüklenirken aldığı ad | `teslim_kutusu.py:204`, `:375-400`; ad `teslim_cevap.py:466` |
| `deger-havuzu-farki_<teslim>.csv` | `DEGER_HAVUZLARI` ↔ referans listeleri iki yönlü fark (`havuz, liste, yon, deger`); **fark yoksa dosya yok**, bayat kopya silinir | `havuz_farki_csv_yaz` (`:426-437`); çağrı `teslim_kutusu.py:506-531` |
| `satir-raporu_<damga>.csv`, `kardes-foy-celiskileri_<damga>.csv` | aktarım scriptinin kendi raporları — yalnız sorunlu satır/çelişki varsa doğar | `scripts/hukdok_aktarim.py:2290-2318` |
| `kuru-kosu-ozeti.txt`, `uygulama-ozeti.txt` | iki koşunun `ozet_metni` çıktısı | `teslim_kutusu.py:821`, `:921` |

Eşleşme dosyasında `sebep` **satır numarasıyla** eşlenir (aynı SistemNo dosyada iki kez
geçebilir) ve rapor dizinindeki **en yeni** `satir-raporu_*.csv`'den okunur (`:54-56`,
`:179-203`). CSV biçimi scriptle aynı: UTF-8 BOM + `;` (`:170-176`).

Yükleme sırası: `teslim_uygula` başarı yolunda **bir** deneme (admin "Uygula" da buradan
geçer, `teslim_kutusu.py:888-896`, `:403-412`); kalanı gece turu. Kısmi başarısızlık teslimi
`basarisiz` **yapmaz** — yazım zaten commit'li; dosya başına WARNING, `cevap_yuklendi=false`
kalır, her deneme `durum_gecmisi`ne durum değişmeden "cevap yükleme denemesi #N" notu düşer
(`teslim_cevap.py:41-44`, `:90`, `:527-546`). Anahtar kapalı / env tanımsız atlamaları deneme
**sayılmaz** (`:484-496`).

Bilinen sınır (modül şerhi `:45-51`): `cevap/<teslim>/` ara klasörleri Graph'ın yol-adresli
PUT davranışıyla açılır; kod tabanında bu davranışa yaslanan başka çağrı yok — ilk gerçek
cevap yüklemesi gözle doğrulanmalı.

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

**`status` kesim-sonrası koruması (G152, plan P2 — "paket kazanır"ın tek istisnası).**
`_kart_alanlarini_yaz` yalnız `status` alanında ve paket değeri farklıyken
`kesim_sonrasi_kullanici_kaydi` (`:1931-1956`) çağırır: kesim GÜNÜNÜN başından (TR 00:00)
itibaren `case_history.field_name == "status"` ve `source` NULL **ya da** `AKTARIM_SOURCE_PREFIX`
ile başlamayan (`autoescape=True` — `_` LIKE jokeri) bir kayıt varsa alan yazılmaz,
`korunanlar`a "status korundu (kullanıcı dd.mm.yyyy)" düşer (`:2009-2016`); `_satiri_isle`
bunu `status_korunan` sayacına ve satır raporuna `STATUS_KORUNDU_TURU = "KORUNDU"` (`:199`,
`:2431`) ile yazar — `HATA` değil, `hata_sayisi`/çıkış kodu/kapı etkilenmez. `kesim_tarihi`
None ise kural kapalı, TEK WARNING (`aktarimi_kos`, `:3213`). Kaynak §3 "Veri kesim tarihi";
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

## 8. Log sözleşmesi ve bildirim

- Deneme/yapı düzeyi başarısızlık **WARNING** — `reddedildi` dahil (yapı hatası veri ekibinin
  düzelteceği şeydir, nöbetçi alarmı değil), tek dosya indirme hatası, cevap yükleme hatası.
- Nihai `basarisiz` teslim başına **TEK ERROR**. Envanter kapısı kırmızı çıktığında o ERROR'u
  `aktarimi_kos` zaten basar ("Aktarım GERİ ALINDI", `scripts/hukdok_aktarim.py:2267-2272`);
  servis ikinci ERROR yazmaz, yalnız defteri işler (`teslim_kutusu.py:38-42`, `:933-940`).
- Gece turunda tarama hatası tur başına tek ERROR (`:1154-1155`); boot telafisinde WARNING.
- Bildirim (`bildir`, `:534-581`): `inceleme_bekliyor` / `reddedildi` / `basarisiz` / `uygulandi`
  geçişlerinde `ADMIN_EMAILS` kümesine uygulama içi bildirim, `type="veri_teslim"`,
  `dedupe_key = teslim:<id>:<durum>:<alıcı>` (alıcı sonda — G082 dersi, `:439-443`).
  `yinelenen` bildirim üretmez. Değer havuzu farkı ayrı bildirimdir (`teslim:<id>:havuz:<alıcı>`,
  `:469-503`). Bildirim yan üründür: her hatası WARNING ile yutulur, durum makinesi bozulmaz.

## 9. Bilinen sınırlar ve açık kalemler

- **Kart yaratılmaz.** Eşleşmeyen satır raporda kalır; kart açmak ofis dosya numarasını
  SharePoint sayacından atomik tahsis ister, çevrimdışı hattın işi değildir
  (`scripts/hukdok_aktarim.py:44-47`). Eşleşme köprüsü DosyaNo ↔ `klasor_no_2`.
- **İlk teslim daima inceleme** (`ilk_teslim` kuralı) — defter boşken otomatik uygulama yok;
  ilk teslimi insan "Uygula" der. Zincir o teslimden başlar: "Önceki teslim: —" yalnız defter
  boşken başlangıçtır (G156, §3); prod'da başlangıç paketi 04.09'dur ve teslim hattından
  (defter üzerinden) uygulanmalıdır — süreç adımı, kod değil (plan 08.09 K3).
- **Aynı gecede tek uygulama** (§5).
- **`DEGISIKLIK_OZETI` yokken zincir denetlenmez ve kapı durmaz:** `zincir_tamam=NULL`
  (`services/teslim_kutusu.py:1141`), `kapi_ihlalleri` yalnız `is False`'u `zincir_eksik`
  sayar (`:1215`, §4 tablosu) — sayfasız paket öteki eşiklerin içindeyse otomatik uygulanır.
  Sözleşme bunu açıkça söyler ("her teslime ekleyin"); NULL'ı da inceleme saydırmak
  plan §8'de açık kalem.
- **`POST /api/admin/aktarim/tara` yer tutucudur**: panelin "Şimdi tara" düğmesi
  (`DeliveryInboxCard.tsx:238`) gözcüyü çağırmaz, sıfır + `not` döner
  (`routes/admin.py:311-325`). Sebep G109 raporunda: G108 testi yanıtı birebir kilitliyor,
  uç + test tek küçük görev.
- **Frontend'de kapsam dışı föy rozeti yok**: `get_case` çıktısındaki `foyler[]`
  (`kapsam_durumu` dahil) hazır, kart panelinde gösterim sonraki tur.
- **Cevap klasörü ara klasör davranışı** koddan kanıtlanmadı (§6); ilk gerçek yükleme gözle
  doğrulanır.
- **Prod kurulumu insan adımıdır (G147 sonrası, ikinci site):** veri ekibi Hanyaloğlu
  tenant'ındadır, arşiv site'ı LexisBio'da; tenant'lar arası paylaşım misafir davetine düşüp
  ulaşmadığı için teslim hattı Hanyaloğlu tenant'ındaki `hukdok_arsiv` site'ına taşınır (arşiv
  taşınmaz). Sıra: (1) o site'ın `Belgeler` drive'ında `03_VERI_TESLIM/gelen` (veri ekibine
  düzenleme) ve `03_VERI_TESLIM/cevap` (görüntüleme) klasörleri açılıp paylaşılır — aynı tenant,
  davet gerekmez; (2) Hanyaloğlu tenant'ındaki uygulama kaydının app-only `Sites.ReadWrite.All`
  (ya da `Sites.Selected` + site izni) iznine sahip olduğu Entra'da teyit edilir, secret bitiş
  tarihi `TESLIM_SHAREPOINT_CLIENT_SECRET_EXPIRES_AT`'a yazılır (lifespan ikinci çağrı,
  `backend/api.py:133`); (3) prod `.env`'e `TESLIM_SHAREPOINT_TENANT_ID` / `CLIENT_ID` /
  `CLIENT_SECRET` / `SITE_URL` + `SHAREPOINT_FOLDER_TESLIM_NAME` (cevap yüklemesi onsuz HİÇ
  çalışmaz) ve isteniyorsa eşikler → `docker compose up -d` (recreate; `restart` env'i almaz,
  bayat upstream için frontend de recreate edilir); (4) admin panelden anahtar — ilk teslim daima
  `inceleme_bekliyor`; (5) LexisBio site'ındaki eski `03_VERI_TESLIM` (03.09 lokal testinin izi)
  kullanıcı kararıyla silinir ya da bırakılır. Dörtlü tanımsız kaldığı sürece hat arşiv
  kimliği/site'ıyla çalışmaya devam eder (§1 "Site/kimlik").
- Ters yön (bizim veriyi sigorta şirketi Excel'ine işlemek), WhatsApp/e-posta ekini otomatik
  okuma, mükerrer kart birleştirme (D6) — bilinçli kapsam dışı (plan §5).

## 10. Nereye bakmalı

| Konu | Dosya |
| --- | --- |
| Durum makinesi, gözcü, gece turu, kapı, bildirim | `backend/services/teslim_kutusu.py` |
| Eşleşme CSV, cevap yükleme, `DEGER_HAVUZLARI` farkı | `backend/services/teslim_cevap.py` |
| Gerçek yazma yolu, envanter kapısı, `Düzeltme_Logu`, kapsam sayfaları | `backend/scripts/hukdok_aktarim.py` (`backend/scripts/README.md`) |
| Admin uçları | `backend/routes/admin.py` |
| Defter modeli + migrasyon madde 39/40 | `backend/models.py:1080`, `backend/database.py:913-919` |
| Zamanlayıcı kaydı + boot telafisi | `backend/api.py:227-262` |
| Graph klasör listeleme | `backend/sharepoint/sharepoint_uploader_graph.py:483-518` — bkz. [`dis-bagimliliklar.md`](dis-bagimliliklar.md) |
| İkinci kimlik/site (`teslim` config'i, düşüş kuralı) | `backend/sharepoint/auth_graph.py:19-31`, `:118-160`; `backend/sharepoint/sharepoint_uploader_graph.py:17-40`, `:145-209` |
| Veri ekibine verilen sözleşme | [`docs/veri-teslim/SOZLESME.md`](../veri-teslim/SOZLESME.md) |
| Plan ve açık kalanlar | [`docs/plan/veri-teslim-otomasyonu-plani-2026-09-03.md`](../plan/veri-teslim-otomasyonu-plani-2026-09-03.md) |
| Veri ekibine verilen bilgilendirme (sütun/sayfa/değer ayrıntısı, makine-okur özet) | [`docs/veri-teslim/BILGILENDIRME_2026-09-03.md`](../veri-teslim/BILGILENDIRME_2026-09-03.md) (sürüm 1.1; dosya adı sabit — yol veri ekibinde) |
| Aşama katmanı, havuz, status koruması, kök→müvekkil, başvuru tarihi, yazım (§7.1) | `backend/scripts/hukdok_aktarim.py`, `backend/managers/stage_decisions.py`, `backend/managers/case_manager.py:1041-1082`, `backend/managers/reference_lists.py` (`tr_title`), `backend/managers/seed_data.py:427-467` |
| Testler | `backend/tests/test_g107_teslim_kutusu.py`, `test_g108_teslim_admin_uclari.py`, `test_g109_teslim_gozcusu.py`, `test_g110_teslim_cevap.py`, `test_g112_duzeltme_logu.py`, `test_g113_kapsam_disi_foy.py`, `test_g120_aktarim_muvekkil_hizmet.py`, `test_g147_teslim_sharepoint_kimligi.py`; §7.1 kuralları: `test_g150_asama_kurali.py`, `test_g151_havuz_kurali.py`, `test_g152_status_koruma.py`, `test_g153_dosyano_koku.py`, `test_g155_basvuru_tarihi.py`, `test_g156_delta_ve_zincir.py`, `test_g159_tr_title.py` |
