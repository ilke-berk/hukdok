# Prod uygulama sırası — Deploy #21 sonrası veri adımları (10.09.2026)

**Amaç:** 08-10.09 gece koşularında main'e giren G147-G161 işini canlıya almak ve lokalde 05.09'dan beri
uygulanmış veri adımlarını (04.09 paketi, kart açma, ikiz birleştirme, 20 föy bağlama, yazım birliği)
prod'da aynı sırayla tekrarlamak. Her komut koddan okunarak yazıldı (kaynaklar satır sonlarında).
Bu doküman **koşu günü işaretlenerek** ilerletilir; bitince `docs/arsiv/`e taşınır.

> Kod blokları bilerek `text` etiketli: bu komutlar **sunucuda** koşar, uygulamanın "Run" düğmesi
> lokalde çalıştırırdı. `hukdok_aktarim.py` hariç bütün script'lerde kuru koşu varsayılan, `--apply`
> yazar. `hukdok_aktarim.py`'nin varsayılanı **YAZMAKTIR**: `--dry-run` unutulursa doğrudan yazar
> (`backend/scripts/hukdok_aktarim.py:3509`). Hiçbir script yedek almaz; yedek insan adımıdır.

## 0. Sabit bilgiler

| Ne | Değer | Kaynak |
| --- | --- | --- |
| Sunucu | `ssh hukukoid`, repo `~/hukdok`, main dalı | hafıza `prod_ssh_access` |
| Konteynerler | backend `hukdok_backend`, db `hukudok-postgres` | `docker-compose.yml:5,45` |
| Prod şu an | main **8585423** (Deploy #20, 04.09) | hafıza `deploy_20` |
| Hedef | main **f7ceb2b** (G147-G161 + gece raporları) | `git log` 10.09 |
| Yedek dizini | `~/backups/` (deploy öncesi `predeploy_<SHA>_<damga>.dump`; gecelik `hukudok_<tarih>.dump` 03:30 TR) | `deploy.sh:52,294-296`, `infra/scripts/backup_db.sh:11-23` |
| Kalıcı veri | `/app/data` (named volume `backend-data`) — recreate'te kalır | `docker-compose.yml:57` |
| Hazır paket | `C:\hukdok-veri\teslim\HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx` — ekibin 04.09 paketinin **kopyası**, `DEGISIKLIK_OZETI` 5. satırına `Veri kesim tarihi \| 30.07.2026` eklendi (G152 eşiği; ekip satırı koymadığı için paket adındaki 04.09 kesim sayılırdı). Konteynerde `teslim_kutusu.kesim_tarihi_oku` → 2026-07-30 doğrulandı; sayfa/satır sayıları aynı (11 sayfa, 8.409 föy, 8.362 aşama). Masaüstündeki orijinal dokunulmadı | bu oturum, 10.09 |
| Cevaplı xlsx | `C:\Users\ilkeb\OneDrive\Masaüstü\veri-ekibi-cevap-2026-09-06\HUKDOK_MUKERRER_VE_YENI_KARTLAR_20260905_CEVAPLI.xlsx` | ekip cevabı 06.09 |

Sunucuya iki dosyayı **sen** taşırsın (ajan scp koşmaz):

```text
scp "C:\hukdok-veri\teslim\HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx" hukukoid:~/
scp "C:\Users\ilkeb\OneDrive\Masaüstü\veri-ekibi-cevap-2026-09-06\HUKDOK_MUKERRER_VE_YENI_KARTLAR_20260905_CEVAPLI.xlsx" hukukoid:~/
```

## 1. Lokal: push (mesai içinde olur)

```text
git -C "C:\Users\ilkeb\OneDrive\Masaüstü\hukudok-automator-main" push origin main
```

Sunucu GitHub'a anonim fetch'te aralıklı 401 veriyor; olursa Deploy #19'daki bundle yolu
(hafıza `deploy_19`): lokalde `git bundle create`, scp, sunucuda geçici `set-url origin`.

## 2. Deploy #21 (mesai dışı, sunucuda)

```text
cd ~/hukdok
git fetch origin && git log --oneline HEAD..origin/main | wc -l      # 143 commit beklenir (8585423..f7ceb2b)
./deploy.sh --gate-only                                              # yalnız test kapısı, pull/dump/build/up YOK
./deploy.sh                                                          # ff-only pull → predeploy dump → build → test kapısı → up -d → /healthz 120 sn
curl -s http://localhost:8001/healthz                                # "version": "f7ceb2b" beklenir
docker logs --since 10m hukdok_backend 2>&1 | grep -c '"severity": "ERROR"'   # 0 beklenir
```

Kaynak: `deploy.sh:4-36,184-188,242-251`. Geri dönüş yalnız imaj: `./rollback.sh 8585423`
(`rollback.sh:4-7`); DB için `~/backups/predeploy_f7ceb2b_*.dump`.

**Deploy'un kendiliğinden yaptıkları (komut yok):**
- `migrate.py` açılışta koşar → `case_stage_decisions.basvuru_tarihi` (madde 47, G155) gelir.
- `seed_all_lists()` lifespan'da koşar (`backend/api.py:165-170`) → 7 yeni karar değeri eklenir
  (yerel `Red/Usulden`; istinaf `Düzeltilerek Karar Verildi`, `Düzeltilerek Kabul Edildi`,
  `Düzeltilerek Reddine`, `Kısmen Kabul`, `Davacı İstinaf Talebinin Kabulü`; temyiz
  `Kısmen Onama/Kısmen Bozma`). Seed yalnız EKLER; `Kapalı`/`Derdest` silme adım 4'te.
- G158 kuralı (çoklu avukatlı kart eksik sayılmaz) kodda; mevcut bayrakların yenilenmesi **ayrı script**
  (`backend/scripts/backfill_missing_required.py:4-5,29`, kuru koşu varsayılan, idempotent):

```text
docker compose exec -T backend python scripts/backfill_missing_required.py            # kuru koşu: toplam/değişecek
docker compose exec -T backend python scripts/backfill_missing_required.py --apply
```

Doğrulama:

```text
docker exec hukudok-postgres psql -U hukudok_user -d hukudok -c "select 'yerel',count(*) from local_decisions union all select 'istinaf',count(*) from appeal_decisions union all select 'temyiz',count(*) from cassation_decisions;"
```

Beklenen: yerel ≥ 29 (27 seed + eski `Kapalı`/`Derdest`), istinaf ≥ 8, temyiz ≥ 4. Prod'da
05.09 paket seed'i koşmadığı için lokaldeki 25 satırlık istinaf artığı prod'da YOK.

## 3. Prod `.env` + SharePoint (teslim hattı bağlantısı, G147)

**3a. SharePoint (tarayıcı, insan):** Hanyaloğlu tenant'ındaki `hukdok_arsiv` site'ında `Belgeler`
kütüphanesine `03_VERI_TESLIM/gelen/` ve `03_VERI_TESLIM/cevap/` klasörleri; `gelen`
veri ekibi hesabına (`hanyaloglu@hanyaloglu-acar.av.tr`) **düzenleyebilir**, `cevap` okunabilir paylaşım.
Bu tenant'ta uygulama kaydı zaten var (lokal `.env` `UPLOAD_SHAREPOINT_*`, hafıza
`teslim_tenant_ayrimi`); `Counter`/`log` listeleri gerekmez (arşiv LexisBio'da kalıyor).

**3b. `.env` (sunucuda `~/hukdok/.env`), yorumları aç ve doldur** — adlar `.env.example:41-48`:

```text
TESLIM_SHAREPOINT_TENANT_ID=<Hanyaloğlu tenant id>
TESLIM_SHAREPOINT_CLIENT_ID=<uygulama kaydı client id>
TESLIM_SHAREPOINT_CLIENT_SECRET=<secret>
TESLIM_SHAREPOINT_CLIENT_SECRET_EXPIRES_AT=<Entra bitiş tarihi, ISO>
TESLIM_SHAREPOINT_SITE_URL=https://hanyaloglu.sharepoint.com/sites/hukdok_arsiv
TESLIM_SP_DRIVE_NAME=Belgeler
```

Üçlüden biri eksikse sistem sessizce **arşiv kimliğine düşer** (`teslim_kutusu.py:67-73`);
`SHAREPOINT_FOLDER_TESLIM_NAME` varsayılan `03_VERI_TESLIM` (`:175-177`). Raporlama env'leri
(`RAPOR_*`) zorunlu değil, varsayılanlar yeter (`docs/mimari/raporlama.md:457`).

```text
cd ~/hukdok && docker compose up -d                 # .env yalnız create'te okunur; restart YETMEZ; tüm stack (nginx bayat upstream tuzağı)
docker logs --since 2m hukdok_backend 2>&1 | grep -i "teslim" | head        # açılış INFO: teslim kimliği/site'ı hangisi
```

**3c. Admin panel → Ayarlar:** `veri_teslim_otomasyonu` anahtarını AÇ (varsayılan KAPALI;
kapalıyken gözcü, gece turu, `/tara` ve cevap yükleme hiç çalışmaz — `app_settings.py:57-66`,
`teslim_kutusu.py:1417,1519,1566`). Elle **Uygula** anahtardan bağımsız çalışır (`routes/admin.py:231`).

## 4. Havuz temizliği (yedek → kaldır)

```text
mkdir -p ~/backups && docker exec hukudok-postgres pg_dump -U hukudok_user -Fc hukudok > ~/backups/pre_veri_$(date +%Y%m%d-%H%M).dump && ls -la ~/backups | tail -3
docker compose exec -T backend python scripts/deger_havuzu_seed.py --liste local_decisions --kaldir "Kapalı" --kaldir "Derdest"            # kuru koşu: kullanım sayıları
docker compose exec -T backend python scripts/deger_havuzu_seed.py --liste local_decisions --kaldir "Kapalı" --kaldir "Derdest" --apply    # kullanılan satır SİLİNMEZ, raporlanır
```

Kaynak: `deger_havuzu_seed.py:34-37,307-311`. Lokalde `Derdest` 1 kartta kullanımdaydı ve korundu;
prod'da kullanım varsa aynı olur (G151 kuralı gelen değeri zaten "karar yok" sayar).

## 5. 04.09 paketi — teslim hattından (zincir başlangıcı, K3)

1. Hazır paketi (kesim satırlı kopya) SharePoint `03_VERI_TESLIM/gelen/` klasörüne **aynı adla** bırak:
   `HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx` (ekibin sonraki paketi "Önceki teslim" satırında bu adı
   yazacak; `_uygulandi_var` birebir ad arar — `teslim_kutusu.py:373-382`).
2. Admin panel → Veri teslim kartı → **Tara** (`POST /api/admin/aktarim/tara`; senkron ~45 sn, yalnız
   kuru koşar — `routes/admin.py:311-366`). Beklenen durum: **inceleme_bekliyor** — ilk teslim daima
   insan onayı; ayrıca "Önceki teslim: HUKDOK_TESLIM_2026-08-31.xlsx" zinciri kopuk (31.08 hiç gelmedi)
   ve alan değişikliği 10.000 eşiğinin üstünde. Bunlar beklenen, hata değil.
3. Kuru koşu raporlarını oku (panelden `raporlar`): eşleşme ~%97, kesim tarihi 30.07 uyarısı YOK
   (satır okundu), `buro_durumu_atlanan` 1-2, `KORUNDU` satırları (30.07 sonrası prod'da elle
   arşivlenen kartlar) — bu sayı G152'nin işe yaradığının kanıtı.
   **Kullanıcı kararı (12.09.2026): prod'da elle yapılan düzeltmeler DOĞRU kabul edilir; paket bu
   alanları üzerine yazmaz, yalnız boş alanı doldurur.** 12.09 ölçümü (prod 88daf70, salt-okunur):
   30.07 sonrası kullanıcı imzalı tarihçe 47 satır / 37 kart — `status` 20, `esas_no` 18, `court` 10;
   44'ü paketin (= lokal uygulama sonrası) değerinden FARKLI, yalnız 3'ü aynı. Liste ekibe iletilmek
   üzere masaüstünde `HUKDOK_ELLE_DUZELTMELER_2026-09-12.xlsx` (OZET + ELLE_DUZELTMELER; sarı hücre =
   defteri HukDok değeriyle güncelleyin). `X1.I_KUTLUK...0005` (kart 14411) ofis içi test, listede yok.
   **KOD BOŞLUĞU — 12.09 KAPATILDI:** `hukdok_aktarim.kesim_sonrasi_kullanici_kaydi` eskiden yalnız
   `field_name == "status"` bakıyordu (G152); `esas_no` ve `court` için koruma yoktu → Uygula 18 esas +
   10 mahkeme düzeltmesini geri alırdı. 12.09 commit'i korumayı alan bazına genelledi (kesim sonrası
   kullanıcı imzalı tarihçesi olan HER dolu alan için paket o alanı yazmaz ve boşaltmaz, bizde boşsa
   doldurur, satır raporuna `<alan> korundu`, sayaç `korunan_alan`; `test_g152_status_koruma.py` §4).
   Prod kuru koşu kabulü: `KORUNDU` ≥ 44 satır (47 elle satırın 3'ü paketle zaten aynı → fark yok,
   sayılmaz) ve bu 37 kartta esas/mahkeme/durum değişikliği 0.
4. **Uygula** (`POST .../teslimler/{id}/uygula` `{"onay": true}`; yalnız `kuru_kosuldu`/`inceleme_bekliyor`
   durumundan — `routes/admin.py:225-261`). Belge envanteri denk değilse koşu kendini geri alır.
5. Sonuç: durum `uygulandi`, cevap paketi `cevap/HUKDOK_TESLIM_PAKETI_2026-09-04/` altına yüklenir
   (anahtar açıksa — `teslim_cevap.py:493`). Ekibe bu klasör bağlantısı gider.

Yedek fallback: SharePoint gecikirse panelden **Yükle** (multipart, ≤50 MB; `routes/admin.py:156-185`)
aynı deftere düşer, sonra aynı Uygula. Kuru koşu için CLI alternatifi (yazmaz, defterden bağımsız):

```text
docker cp ~/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx hukdok_backend:/app/data/
docker compose exec -T backend python scripts/hukdok_aktarim.py --input /app/data/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx --kesim-tarihi 30.07.2026 --dry-run --rapor-dizini /app/data/aktarim-raporlari
```

Paket değer havuzları (S5 — 13 listeye ekler, "önce geçir, sonra panelden temizle"):

```text
docker compose exec -T backend python scripts/deger_havuzu_seed.py --input /app/data/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx            # kuru koşu: liste başına yeni sayı (lokalde 1.579)
docker compose exec -T backend python scripts/deger_havuzu_seed.py --input /app/data/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx --apply
```

Kaynak: `deger_havuzu_seed.py:12-15`. G151 sayesinde dört karar listesine büro durumu GİRMEZ.

## 6. Lokalde yapılıp prod'da tekrarlanacak veri adımları (sırayla, her yazma öncesi yedek)

Dosya konteynerde `/app/data/` altında (adım 5'teki `docker cp`). Ortak yedek komutu:

```text
docker exec hukudok-postgres pg_dump -U hukudok_user -Fc hukudok > ~/backups/pre_<adim>_$(date +%Y%m%d-%H%M).dump
```

**6a. Kart açma (G126, 217 kartsız föy → 210 kart)** — `kartsiz_foy_kart_ac.py:18-21,243-246`:

```text
docker compose exec -T backend python scripts/kartsiz_foy_kart_ac.py --input /app/data/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx --rapor-dizini /app/data/kart          # kuru koşu; çıkış 1 = hatalı aday
docker compose exec -T backend python scripts/kartsiz_foy_kart_ac.py --input /app/data/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx --rapor-dizini /app/data/kart --apply
```

Lokal sonuç 217 föy → 210 kart. Prod'da 30.07'den sonra elle açılmış kart varsa aday sayısı düşer;
kuru koşu çıktısındaki sayıyı not et.

**6b. İkiz kart birleştirme (G127, 8 çift)** — `mukerrer_kart_birlestir.py:26-29,254-257`; biçim `kalan:mukerrer`:

```text
docker compose exec -T backend python scripts/mukerrer_kart_birlestir.py --cift 719:718 --cift 721:720 --cift 741:740 --cift 880:879 --cift 832:831 --cift 14314:14315 --cift 5057:5568 --cift 4556:4555
docker compose exec -T backend python scripts/mukerrer_kart_birlestir.py --cift 719:718 --cift 721:720 --cift 741:740 --cift 880:879 --cift 832:831 --cift 14314:14315 --cift 5057:5568 --cift 4556:4555 --apply --kim ilke
```

**Kuru koşu çıktısında sekiz çiftin ad/esas eşleştiğini gözle doğrula** — kimlikler lokal 30.07
kopyasından; eski kartlarda prod ile aynı olmalı ama `14314/14315` çifti kopyanın sonuna yakın,
prod'da o kimlikler başka kartsa **atla**. Mükerrer SOFT silinir, ofis no mükerrerde kalır.
747/748 ve 791/792 de ikiz ama ekibin cevabı gerekliydi — bu turda DEĞİL.

**6c. 20 föy bağlama haritası (G154)** — `cevapli_kart_eslemesi.py:11-12,315-317` (salt okunur):

```text
docker cp ~/HUKDOK_MUKERRER_VE_YENI_KARTLAR_20260905_CEVAPLI.xlsx hukdok_backend:/app/data/
docker compose exec -T backend python scripts/cevapli_kart_eslemesi.py --input /app/data/HUKDOK_MUKERRER_VE_YENI_KARTLAR_20260905_CEVAPLI.xlsx --output /app/data/kart_eslemesi.csv
```

Beklenen: 27 kart no + 1 müvekkil adı (id-1012 → Quick), `H-6589` BAĞLAMAYIN → CSV'ye girmez.

**6d. Aktarım tekrarı (yeni kartlara föy bağlama + harita)** — `hukdok_aktarim.py:3506-3525`:

```text
docker compose exec -T backend python scripts/hukdok_aktarim.py --input /app/data/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx --kesim-tarihi 30.07.2026 --kart-esleme /app/data/kart_eslemesi.csv --rapor-dizini /app/data/aktarim-raporlari --dry-run
docker compose exec -T backend python scripts/hukdok_aktarim.py --input /app/data/HUKDOK_TESLIM_PAKETI_2026-09-04.xlsx --kesim-tarihi 30.07.2026 --kart-esleme /app/data/kart_eslemesi.csv --rapor-dizini /app/data/aktarim-raporlari
```

Lokal beklenti: yeni föy 217 + 9 + 19, belirsiz satır **0**, kalan hata 10 (7 kök/müvekkil çelişkisi
+ 3 boş DosyaNo), kartsız 0, envanter DENK. Bu koşu defterde görünmez (CLI); zincir zaten adım 5'te
başladı. `--kesim-tarihi` UNUTMA (paket kopyasında satır var ama CLI da açık versin).

**6e. Yazım birliği (G160)** — `yazim_birligi.py:51-54,557-564`; `--apply` ile `--kim` ZORUNLU:

```text
docker compose exec -T backend python scripts/yazim_birligi.py --cikti-dizini /app/data/yazim_birligi            # kuru koşu, 6 adım, CSV'ler
docker compose exec -T backend python scripts/yazim_birligi.py --cikti-dizini /app/data/yazim_birligi --apply --kim ilke
docker compose exec -T backend python scripts/yazim_birligi.py --cikti-dizini /app/data/yazim_birligi            # ikinci koşu: 6 adımda 0 satır beklenir
```

Lokal: 6.574 tarihçe satırı (taraf 6.201 · sub_type 177 · subject 111 · court 83 · bureau_type 2).
**Adım 2b (G163):** aynı komut artık adım 2 ile birlikte 2b'yi de koşar (tek yazımlı, teslimsiz taraf adında yalnız
biçim farkı → `tr_title`; lokal kuru koşu 7.978 satır / 1.998 tekil, ilk üçü Koru 3.172 · Quıck 578 · Ankara 388) —
`--apply` 10.09 itibarıyla LOKALDE DE KOŞULMADI: kuru koşunun bastığı ilk 15 tekil kullanıcı onayından geçince
koşulur, prod'da da önce kuru koşu + ilk 15 gözle. "Türk Nippon Sigorta Aş" (204) 2b'ye GİRMEZ: paketin kendi yazımı
"Aş", teslim kazanır.
**Adım 0 (G165):** aynı komut artık combining-dot (U+0307) temizliğini adım 1'den ÖNCE koşar ("Si̇gorta" → "Sigorta",
`case_parties.name` + `cases.court`; lokal kuru koşu 11.09: 6.351 satır / 4.398 tekil, dokunulmayan 0, adım 0 sonrası
adım 2'de 57 nokta-ikizi satırı açığa çıkar) — `--apply` yine kullanıcı ilk 15 tekili onaylayınca, önce lokalde.
**Nokta ikizleri (G164):** aynı koşuda gelir — anahtar artık SON noktayı yutar ("Ak Sigorta A.Ş." ↔ "A.Ş" tek grup;
teslim kazanır, yoksa baskın), lokal kuru koşu adım 2'de nokta ikizi satırlarını bu yüzden gösterir; `--apply` yine
ilk 15 onayından sonra.
Sigortalı/Davalı İdare satırları, istinaf/temyiz mahkeme listeleri, avukat adları DOKUNULMAZ.
Envanter farkında rollback + çıkış 2. Kuru koşuda adım 2'de "… adına Velayeten" gibi bağlaç-küçük
teslim yazımları teslim olarak geçer (rapor notu).

**6f. Derdest listesi (ekibe güncel hâli)** — `foysuz_derdest_kartlar.py:4-5,254-255` (yazmaz):

```text
docker compose exec -T backend python scripts/foysuz_derdest_kartlar.py --out /app/data/
docker cp hukdok_backend:/app/data/HUKDOK_DERDEST_KARTLAR_$(date +%F).xlsx ~/
```

Sonra `scp hukukoid:~/HUKDOK_DERDEST_KARTLAR_*.xlsx .` ve ekibe "güncel hâli" olarak gönder
(09.09 mailinde söz verildi).

**6g. TKU kart birleştirmesi (11.09, main 7beafc6)** — `tku_kart_birlestir.py:248-252`; kuru koşu
varsayılan, `--apply --kim <ad>` yazar, `--rapor` plan CSV'si:

```text
docker exec hukudok-postgres pg_dump -U hukudok_user -Fc hukudok > ~/backups/pre_tku_$(date +%Y%m%d-%H%M).dump
docker compose exec -T backend python scripts/tku_kart_birlestir.py --rapor /app/data/tku_plan.csv
docker compose exec -T backend python scripts/tku_kart_birlestir.py --rapor /app/data/tku_sonuc.csv --apply --kim ilke
```

Lokal sonuç: 184 kart soft-delete, 186 föy taşındı, belge envanteri 229→229, 15 ret (10 tür, 5 mahkeme).
Prod'da lokalde silinen 192 kartın 5'ine 8 belge + 1 duruşma + 2 bildirim bağlı (12.09 ölçümü) — script
belgeleri kalan karta taşır; koşu sonrası bu 5 kart ayrıca doğrulanır (belge/duruşma/bildirim sayımı).
Sonra 6d aktarım tekrarı (birleşen kartlarda 2 belirsiz satır kendiliğinden çözülür).

**6h. Tarihçe temizliği (11.09, main c6cbe4b)** — `tarihce_temizligi.py:179-180`; kuru koşu varsayılan,
`--yedek` silinen satırların CSV dökümü (geri alma yedeği):

```text
docker exec hukudok-postgres pg_dump -U hukudok_user -Fc hukudok > ~/backups/pre_tarihce_$(date +%Y%m%d-%H%M).dump
docker compose exec -T backend python scripts/tarihce_temizligi.py
docker compose exec -T backend python scripts/tarihce_temizligi.py --apply --yedek /app/data/tarihce_silinen_$(date +%Y%m%d).csv
```

Lokal sonuç: 131.188 silindi, 8.965 kaldı. KALIR: föy bağlama satırı (`case_foys.sistem_no`, AKTARIM
provenance — silinirse 6.466 kart kova değiştirir), birleştirme izi, gerçek mahkeme/esas/status değişimi,
kullanıcı satırı (prod'daki 47 elle düzeltme de kalır).

## 7. Kapanış kontrolleri

```text
docker logs --since 3h hukdok_backend 2>&1 | grep -c '"severity": "ERROR"'      # 0 beklenir (yazım/aktarım rollback ERROR'u yoksa)
docker exec hukudok-postgres psql -U hukudok_user -d hukudok -c "select source, count(*) from case_history where changed_at > now() - interval '6 hours' group by 1 order by 2 desc;"
docker exec hukudok-postgres psql -U hukudok_user -d hukudok -c "select count(*) filter (where deleted_at is null) as aktif_kart, count(*) filter (where deleted_at is not null) as silinmis from cases;"
ls -la ~/backups | tail -8
```

Ardından: raporlar sekmesinden derdest/föy sayılarıyla mutabakat; ekibe cevap klasörü bağlantısı +
güncel derdest listesi; hafıza notu (`prod = f7ceb2b`, uygulanan adımlar, yedek adları).

## Ekibin cevabına bağlı, bu turda YAPILMAYANLAR

- "Karar" (74 föy) değeri havuza girmez; Corpus ×4 / Ergo ×1 kök çelişkisi istisnası; `Kapalı`/`Derdest`
  hücrelerinin boşaltılması; uzmanlık listesindeki iki yazım hatası (`Genel Cerrahisi`, `Hiperbarik Tip`)
  panelden düzeltme; 747/748 ve 791/792 ikizleri.
- Bilgilendirme belgesi 1.3 (BILGILENDIRME §3.8 sayıları 04.09 fotoğrafı) — ayrı küçük docs görevi.
