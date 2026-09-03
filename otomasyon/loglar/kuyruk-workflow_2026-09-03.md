# Gece Kuyrugu (workflow) · 2026-09-03

## Ozet

8 görev alındı · 6 işaretlendi (G107, G111, G108, G109, G110, G112) · 1 bloke (G113) · 1 atlandı (G114)

Tavan nedeniyle atlanan: yok.

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G107 — Teslim defteri (`aktarim_teslimleri`) + `services/teslim_kutusu.py` çekirdeği | backend | `bb4d534` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GECTI (5 bulgu, tasarım notu düzeyi) | 3 tur; ilk turda uçtan uca testin verisi eşik dışıydı (3 satırlı paket 1/3 > 0.05), test verisi eşik içi 2 satıra çevrildi; ruff F811 / mypy 8 arg-type noqa'sız giderildi. Son parmak izi: pytest 2182 passed / 3 skipped, ruff+mypy temiz. Merge yapılmadı (ana repo dalında). Yorum kararları: sha256 UNIQUE **kısmi** (`WHERE durum <> 'yinelenen'`); `KAPI_ESIKLERI` fonksiyon takma adı (env çağrı anında okunur). `onceki_teslim_adi_oku` gerçek paketin `DEGISIKLIK_OZETI` yerleşimine karşı ölçülmedi — ilk gerçek teslimde kolon kontrol edilmeli. |
| G111 — Admin paneli "Veri Teslimleri" sekmesi | frontend | `c5951f5` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GECTI (5 bulgu) | 2 tur; ilk turda 3 react-refresh uyarısı, yardımcı export'lar çıkarılarak giderildi. Son parmak izi: vitest 48 dosya 596 passed, eslint 0/0, `tsc -b --force` exit 0. Worktree `C:/dev/hukudok-wt/G111` → **merge yapıldı**, entegrasyon yeşil, worktree temizlendi. İzlenecek: G108 uçlarıyla tarayıcı turu (eşik değer biçimi oran/yüzde belirsiz, kart ham sayı basıyor); AdminPage düzeyinde sekme testi yok (mevcut desende de yok). |
| G108 — Teslim admin uçları `/api/admin/aktarim/*` + admin bildirimi + `veri_teslim_otomasyonu` anahtarı | backend | `9c44965` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GECTI (3 bulgu) | 3 tur; iki kırmızı da test-verisi kusuruydu (httpx `..` segmentini istemcide çözüyor → `..%2F` varyantı; openpyxl docProps saniye damgası → aynı paket ikinci üretimde farklı sha256), üretim kodu değişmedi. Son parmak izi: 2217 passed / 3 skipped, ruff+mypy temiz. Merge yapılmadı. Kararlar: rapor indirme `..%2F` → 400; yükleme ucu senkron `def` (kuru koşu istek içinde, 300 sn nginx sınırı izlenecek); yapı hatası 201+reddedildi; tara kapalıyken 200 + 'kapali'; uygulama uçlarında ValueError → 409. |
| G109 — SharePoint gözcüsü + gece job 04:00 TR + boot telafisi | backend | `0c39cbf` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GECTI (3 bulgu) | 1 tur, ilk koşuda yeşil. Son parmak izi: 2249 passed / 3 skipped, ruff+mypy temiz. Merge yapılmadı. Kararlar: eTag için model kolonu kapsam dışı → `sharepoint_item_id` `<id>@<eTag>` anahtarı taşıyor; listeleme hatası `gece_turu`'nda TEK ERROR, `boot_catch_up`'ta tek WARNING; tek-uygulama kuralı (ikinci teslim `tek_uygulama` gerekçesiyle inceleme_bekliyor + bildirim). Kabul kriteri olmayan bir boşluk var — bkz. "Karar bekleyenler". İzlenecek: ilk 04:00 turunda prod logunda "Gece veri teslim turu bitti" + `03_VERI_TESLIM/gelen` klasörünün varlığı. |
| G110 — Cevap paketi: SistemNo→cases.id CSV (Talep #9) + raporların `03_VERI_TESLIM/cevap`'a yüklenmesi | backend | `dee4c94` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | GECTI (4 bulgu; sebep alanı boş) | 2 tur; ilk turda 2 test aktarımın ATLANDI WARNING'ini de sayıyordu (filtre `teslim_` katmanına daraltıldı), mypy 5 hata giderildi. Son parmak izi: 2269 passed / 3 skipped, ruff+mypy temiz. Merge yapılmadı. **Prod insan adımı:** `.env`'e `SHAREPOINT_FOLDER_TESLIM_NAME=03_VERI_TESLIM` yazılıp `up -d` (recreate) yapılmadan cevap paketi HİÇ yüklenmez (INFO ile atlanır). Görevdeki "Graph PUT ara klasörleri kendisi açar" iddiası koddan DOĞRULANAMADI — ilk gerçek cevap yüklemesi SharePoint'te gözle doğrulanmalı. |
| G112 — Düzeltme_Logu provenance + "(boş)" boşaltma yolu + DEGER_HAVUZLARI fark raporu | backend | `3a7d0b7` | geçti (test temiz, kırmızı-yeşil kanıtlandı) | 1. denetim **RET** → onarım (3 düzeltildi, 1 düzeltilemedi) → 2. denetim GECTI | 2 tur + onarım. Son parmak izi: 2298 passed / 3 skipped (denetçi koşusu 2303), ruff+mypy temiz. Merge yapılmadı. RET sebebi: DEGER_HAVUZLARI okuyucusu ilk satırı başlık sayıyordu, gerçek paket (`HUKDOK_TESLIM_PAKETI_2026-08-18.xlsx`) başlığı 3. satırda taşıyor → gerçek pakette `{}` dönüyordu (konteynerde doğrulandı); onarıldı. Düzeltilemeyen bulgu karar gerektiriyor — bkz. "Karar bekleyenler". |

Not: G107, G108, G109, G110, G112 için `mergeYapildi=false` — ana dalda doğrudan commit'lendikleri anlaşılıyor (worktree alanı boş); merge/entegrasyon adımı bu görevlerde uygulanmadı. Yalnız G111 worktree'den merge edildi.

## Bloke

### G113 — Silinen_Föyler / Kapsam_Dışı → `case_foys` kapsam işareti (backend)

**Durma sebebi:** `testi degistirmeden gecilemedi - gorev tanimi gozden gecirilmeli`. Bu bir işçi başarısızlığı DEĞİL; hattın "mevcut testi değiştirme" kuralını doğru uyguladığının kanıtıdır. Kod yazılmadı, tur koşulmadı (turSayisi 0, verify çalıştırılmadı), commit yok.

**Son parmak izi:** yok (test koşulmadı).

**Denenen yaklaşımlar:**
1. Bağlam kuruldu (skill, görev dosyası, `models.CaseFoy`, `foy_map`, `hukdok_aktarim`, `case_relations_auto`, `database._MIGRATIONS`, ilgili testler); kod yazılmadan kilit taraması yapıldı.
2. Alternatif — kolonları modele koymadan yalnız migration + ham SQL — değerlendirildi ve reddedildi: `foy_map`/`get_case`/`case_relations_auto` yollarında ORM'siz erişim gerektirir; kilidi korumak için kötü kod = sahte yeşilin ters yüzü.

**Teşhisin kök nedeni:** Sözleşme `case_foys`'a `kapsam_durumu`/`kapsam_gerekcesi`/`kapsam_tarihi` kolonlarını şart koşuyor. `backend/tests/test_g063_case_foys.py:73` (`test_model_ve_kolonlar_gorev_taslagina_uygun`) CaseFoy kolon kümesini `set(columns.keys()) == {...}` TAM eşitlikle kilitliyor (G063'ten beri değişmedi) ve bu dosya görevin dosya kapsamında YOK. Üç yeni kolon bu testi deterministik kırmızıya düşürür. Başka kilit görülmedi (`_UPDATABLE` testlerde kilitli değil; fixture'lar `case_foys` index op'larını olduğu gibi uyguluyor, yeni kolon `("columns")` op'uyla gelir).

**Worktree:** yok (ana repoda çalışıldı). Görev dosyasına `DURUM: BLOKE` + sabah önerisi yazıldı (uncommitted).

**Karşılanmayan kabul maddeleri (7/7, kod yazılmadığı için):** migration üç kolon; aktarım Silinen_Föyler/Kapsam_Dışı işaretleme + idempotency; geri dönüş (Sheet'e dönen föy NULL + tarihçe); kapsam dışı föy çelişki raporuna girmiyor; `case_relations_auto` kapsam dışı föy için ilişki üretmiyor; `get_case` föy listesinde üç alan; docstring güncellemesi.

**Önerilen sonraki adım:**
1. `test_g063_case_foys.py` beklenen kümeye üç kolonu ekle + length/nullable iddiaları (tam eşitlik korunur).
2. G113 görev dosyası kapsamına `test_g063_case_foys.py` satırını ekle.
3. G113'ü yeniden kuyruğa koy (G114 de arkasından açılır).

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok. Karar gerektiren kabul/onarım maddeleri:

1. **G113 (SORU):** Görev tanımı `test_g063_case_foys.py`'yi kapsama alacak şekilde güncellensin mi? (Bloke bölümündeki 1-2 adımları — bunlar yapılmadan görev tekrar koşulamaz.)
2. **G109 — kabul kriteri olmayan boşluk (SORU):** `routes/admin.py` `tara` ucu hâlâ G108 yer tutucusu; `test_g108::test_tara_kapaliyken_hicbir_sey_yapmaz_acikken_yer_tutucu` yanıtı birebir "SharePoint gozcusu henuz yok" olarak kilitliyor ve dosya G109 kapsamı dışındaydı. Reçete G109.md Rapor/NOT'ta (G108 testi + 5 satırlık uç gövdesi). Ayrı küçük görev açılsın mı?
3. **G112 — onarımda düzeltilemeyen bulgu (SORU):** Gerçek paketteki 229 "(boş)" satırı (218'i "Mhzn -> (boş), Format: geçersiz değer silindi") hiçbir sütun adı taşımıyor (konteynerde ölçüldü: (boş)+önek = 0); hangi sütunun boşaltılacağı bilinmeden boşaltmak tahmin olur (sözleşme yasağı). Kod yolu sentetik testlerle kilitli, her koşuda WARNING basar. Çözüm karşı tarafta: G114 sözleşmesine Düzeltme_Logu için sütun-adı başlığı (ya da her satırda `[Sutun]` öneki) yazılsın mı? Ayrıca "İstinaf Karar Durumu" `KART_ALANLARI`'nda değil → yok sayılıyor; kabul ediliyor mu?
4. **G110 — prod insan adımı (BİLGİ/ONAY):** `.env`'e `SHAREPOINT_FOLDER_TESLIM_NAME=03_VERI_TESLIM` + `up -d`. Ayrıca Graph PUT'un ara klasör açtığı iddiası koddan doğrulanamadı; ilk gerçek yüklemede SharePoint'te gözle kontrol.
5. **G111 (SORU):** Mesai saati görev "yerel saat" derken Europe/Istanbul'a çevrilerek hesaplandı (TR dışından bağlanan yönetici için); kabul ediliyor mu?

## Izin engelleri

yok (sekiz görevin hiçbirinde `izinEngelleri` kaydı yok).

## Atlananlar

- **G114** — docs bandı (`docs/mimari/veri-teslim-hatti.md` + `docs/veri-teslim/SOZLESME.md` + genel-bakis/scripts README/CLAUDE.md). Sebep: `bagimlilik bu kosuda tamamlanmadi: G113`. Plan uyarısında öngörülmüştü ("G114 docs bandı G110+G111+G113'ün üçünü bekler — tek gecede erişilemeyebilir"). Worktree `C:/dev/hukudok-wt/G114` **korunuyor** (temizlenmedi, içinde çalışma yok). G113 çözülünce koşulabilir; G112'nin sözleşmeye eklenmesini istediği Düzeltme_Logu sütun-adı başlığı da bu görevin SOZLESME.md'sine girmeli.

Zincir hatası / teslim hatası olan görev: yok.
