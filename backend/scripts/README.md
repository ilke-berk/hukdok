# Tek Seferlik / Operasyonel Scriptler

Uygulama kodundan ayrı tutulan, elle çalıştırılan scriptler. **Tek istisna
`hukdok_aktarim.py`:** veri teslim hattı (`services/teslim_kutusu.py`,
`services/teslim_cevap.py`) `from scripts import hukdok_aktarim` ile onu
çalışma zamanında import eder ve `aktarimi_kos` / `xlsx_oku` / `ozet_metni`'yi
çağırır — script yine elle de koşulabilir, ama artık API'nin bir bağımlılığıdır
(imza değişikliği `services/` tarafını kırar; bkz.
`docs/mimari/veri-teslim-hatti.md`). Diğerleri API tarafından import edilmez;
Docker imajına girseler de çalışma zamanında kullanılmazlar.

Çalıştırma (backend kökünden veya konteyner içinden `/app`):

```bash
docker compose exec backend python scripts/<script>.py [--dry-run|--apply ...]
```

| Script | Amaç |
|---|---|
| `import_excel_cases.py` | **EMEKLİ (G239) — çalıştırılınca hata ile çıkar.** 27.04.2026 ilk yüklemesinin scripti; eski ofis no formatıyla kart açardı. Halefi `hukdok_aktarim.py` + `kartsiz_foy_kart_ac.py` |
| `import_clients.py` | cari_mikro Excel'inden müvekkil import'u |
| `import_lawyers_excel.py` | vekalet_listesi.xlsx'ten avukat import/güncelleme |
| `migrate_from_staging.py` | Staging DB'den prod'a veri taşıma |
| `preview_migration.py` | Staging taşıma önizlemesi |
| `backfill_belge_turu_adi.py` | case_documents.belge_turu_adi backfill (dry-run varsayılan) |
| `retag_tracking_nos.py` | **EMEKLİ (G239) — çalıştırılınca hata ile çıkar.** ESKİ ofis no formatının üreticisiydi; numaranın tek üreticisi `services/ofis_no.py`, toplu numaralama `ofis_no_gocu.py` (karar 023) |
| `normalize_lawyers.py` | responsible_lawyer_name'i canonical hale getirme (Track B) |
| `normalize_list_names.py` | Referans listesi adlarını başlık formatına çevirme (dry-run varsayılan) |
| `add_single_case.py` | Tek dava ekleme (psycopg2, elle) |
| `check_sent_emails.py` | Graph API'den gönderilen mailleri kontrol |
| `compare_emails_docs.py` | Mail ↔ belge kaydı karşılaştırması |
| `export_avukatlar_excel.py` | avukat CSV'sinden xlsx üretimi |
| `export_davalar_ornek_excel.py` | Örnek 10 davayı xlsx'e aktarma |
| `index_envanteri.py` | Index envanteri + güvenli düşürme listesi (SALT OKUNUR; `--json`) |
| `hukdok_aktarim.py` | HUKDOK teslim paketi → kart aktarımı (idempotent; `--dry-run`, `--limit`, `--sheet`). Belge envanteri denk değilse koşuyu geri alır ve NONZERO çıkar. `import_excel_cases.py`'nin halefi — o script KULLANILMAZ (idempotent değil, hata yolunda veri kaybı). **API tarafından da import edilir** (`services/teslim_kutusu.py` — otomatik teslim hattı; yukarıdaki istisna) |

| `backfill_missing_required.py` | `cases.missing_required_bucket` toplu tazeleme — yalnız KURAL değişikliği sonrası (G158 M5: çoklu avukatlı kart); kuru koşu varsayılan, `--apply` yazar, ikinci koşu 0. Bayat bayrağın sebebi kaçan bir yazma yoluysa bunu değil `audit_missing_required_flags`ı kullan |
| `yazim_birligi.py` | Tek seferlik yazım birliği (G160): teslim/ikiz yazımına göre 6 adım (anahtar SON noktayı yutar: "A.Ş." ↔ "A.Ş" ikiz, G164) + **adım 2b** (G163) — adım 2'nin atladığı tek yazımlı, teslimsiz taraf adlarında yalnız biçim farkı (`Quıck … A.ş` → `Quick … A.Ş`, `anahtar_genis` eşit) `tr_title`a çekilir; `--adim 2` daima 2+2b, kuru koşuda ilk 15 tekil satır sayısıyla basılır (onay listesi), `2b.csv` (**adım 0**, G165: combining-dot U+0307 temizliği `Si̇gorta` → `Sigorta` — NFC + `i̇`→`i`, `case_parties.name` + `cases.court`, adım 1'den ÖNCE koşar ki 2/2b/3 temiz metni görsün; `0.csv`, ilk 15 tekil; "Sağlik" ı→i kapsam dışı). Kuru koşu varsayılan (adım değişiklikleri aynı transaction'da uygulanıp sonunda geri alınır); `--apply --kim` tarihçeli, envanter denk değilse rollback + çıkış 2 |
| `ekip_cevabi_1209.py` | Veri ekibinin 12.09.2026 cevabındaki kart düzeltmeleri (G179): Ek-3 › 01 çift kart birleştirme (`mukerrer_kart_birlestir.birlestir` yolu; ön koşul reddederse yalnız föy 30.07 kartına) + Ek-3 › 02 föy taşıma + Ek-2 › 06/§3 kart düzeltmeleri (sabit tablo, konu/hizmet listeden kanonik) + hatalı kopya/deneme kartlarını kapatma (belgeler gerçek karta, sonra soft delete). Ek-3 yolu `--ek3` (repoya girmez), kuru koşu varsayılan, `--apply --kim`; ikinci koşu 0 |
| `idari_yargi_birlestir.py` | "İdari Yargı" dava türünü "İdare"ye birleştirir (ekibe söz 17.09): kartların `file_type`'ı tarihçeli taşınır (silinmişler dahil; **ofis no değişmez**), `court_types`'taki kopya üst tür satırları ve `file_types` satırı silinir. Kuru koşu varsayılan, `--apply --kim`; ikinci koşu 0 |
| `parantez_duzeltme.py` | Kapanmamış parantezli 5 hücre (ekibe söz 17.09; kaynak 27.04 ilk yükleme, paketlerde 0 örnek → aktarıma kontrol eklenmedi): 4 taraf adı + kart 12398 mahkemesi tarihçeli düzelir, mahkemeye gömülü eski esas `add_historical_esas` ile ONCEKI satırı olur. Beklenmeyen değer RET; sonda aktif kartlarda kalan dengesiz parantez sayısı basılır. Kuru koşu varsayılan, `--apply --kim`; ikinci koşu 0 |
| `ekip_cevabi_1709.py` | Veri ekibinin 17.09.2026 cevabındaki (Ek-6) kart düzeltmeleri: 5546 kapatma, 5567 konu + 2553 yerel karar türü, 15 mükerrer çift (A nokta yazımı · B föysüz ikinci kart · C klasörsüz kart, belgeler taşınır · D Başsavcılık + Bursa), A sınıfında klasör numarasının tek yazıma çekilmesi + `212.001.00` düşürme, 14334'ün müvekkil ayrımıyla ayrılması, 14571 ↔ 14730 `ILGILI` bağı. `--ek6` verilirse sabit tablolar ekle doğrulanır (kart ekte var mı, kalan föylü / sönen föysüz mü) ve uyuşmazlıkta hiçbir şey yazılmaz. Kuru koşu varsayılan, `--apply --kim`; ikinci koşu 0. Kart id'leri PROD'dur — lokalde koşmak "uygulandı" saymaz |
| `korunan_alan_kaynaklari.py` | Ek-6 › 03: kesim sonrası korunan alanların KAYNAĞINI sınıflayan rapor (SALT OKUNUR; `--ek6`, `--rapor`). `case_history.source` imzası → `BELGE` / `BELGEDEN_TURETME` / `PANELDEN_ELLE` / `PAKET` / `KAYNAK_YOK` / `TARIHCE_YOK`; belge adı çıkarsa SharePoint bağlantısı, `esas_no`'da `case_esas_numbers` zinciri de yazılır |
| `birlesik_kart_ayir.py` | Birleşik kartları geri ayırma (G180, ekibin kart modeli): kartın föyleri (`ham_veri` → tür + esas anahtarı) gruplanır, kartın kendi grubu kalır, öteki her grup için yeni kart (`kartsiz_foy_kart_ac.kart_adaylari`/`ofis_numarasi`, taraflar `hukdok_aktarim._taraflari_yaz`, esas `sync_current_esas`), föyler taşınır, `case_relations` AYRISTIRILAN bağı + iki kartta `kart_ayirma` tarihçesi; belgeler kalan kartta kalır. Kart listesi `--ek3` (Ek-3 › 03 + Ek-3 › 02 öneri boş satırlar) ya da `--kart`; kuru koşu varsayılan, `--apply --kim`; tek gruplu kart ATLANDI (ikinci koşu 0). `--muvekkil-ayrimi` (Ek-6 › 01, kart 14334): grup anahtarına müvekkil boyutu eklenir (aynı tür + esastaki iki müvekkil de ayrılır), kartta kalan grup ofis numarasının isim bloğuyla seçilir, yeni kartın klasör numarası GRUBUN kendi DosyaNo'sudur; bayrak yalnız adıyla verilen kartta açılır |
| `dava_kartlari_listesi.py` | Veri ekibine giden dava kartları listesi `HUKDOK_DAVA_KARTLARI_<tarih>.xlsx` (G181; 11.09 biçimi: `Dava Kartlari` 89 sütun + `İlişkili kartlar`, `Foyler`, `Aciklama` sayımlar + dışa aktarım SAATİ). SALT OKUNUR; `--out` |
| `mukerrer_kart_raporu.py` | Aynı davayı gösteren kart grupları → iki CSV onay listesi (SALT OKUNUR; `--rapor-dizini`). Kart BİRLEŞTİRMEZ — `tracking_no` müvekkil bazlı ofis dosya numarasıdır, tek davada birden çok müvekkilin ayrı kartı olması doğrudur. "Aynı dava" hükmü `services/case_relations_auto.py`tan gelir |
| `ofis_no_gocu.py` | Ofis no göçü (G238, karar 023): TÜM kartları (silinmişler dahil) `<MÜVEKKİL KODU>-<SIRA>[-<SİGORTALI>]-<TÜR>` formatına numaralar; numaranın her parçası `services/ofis_no`'dan. Kategori kaynağı zinciri: müvekkil kaydı (bağlı ya da aynı adlı) > föy `muvekkil_tipi` > eski numaranın ilk bloğu > ad kuralı; sıra kod içinde `opening_date` → `created_at` → `id`. Kuru koşu varsayılan ve DB'ye HİÇBİR ŞEY yazmaz — `--rapor-dizini`'ne (varsayılan geçici dizin; müvekkil adı taşır, repoya girmez) `ofis_no_esleme_*.csv`, `ofis_no_sigortali_eksik_*.csv`, `ofis_no_ozet_*.txt`. `--apply --kim`: tek transaction, iki aşamalı yazım (`__GOC__<id>`), `case_history` (`source='OFIS_NO_GOCU'`), föy `onceki_tracking_no` çevirisi, sayaç = kod başına en yüksek sıra, envanter kapısı tutmazsa rollback + çıkış 2; müvekkilsiz kart varken DURUR; zaten yeni formattaki kart atlanır (ikinci koşu 0). Çalıştırma `python -m scripts.ofis_no_gocu`. **Prod göçü yalnız kullanıcı kararıyla** |

İşi biten script silinebilir — git geçmişi saklar.
