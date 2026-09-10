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
| `import_excel_cases.py` | Dava Açılış Excel'inden toplu dava import'u |
| `import_clients.py` | cari_mikro Excel'inden müvekkil import'u |
| `import_lawyers_excel.py` | vekalet_listesi.xlsx'ten avukat import/güncelleme |
| `migrate_from_staging.py` | Staging DB'den prod'a veri taşıma |
| `preview_migration.py` | Staging taşıma önizlemesi |
| `backfill_belge_turu_adi.py` | case_documents.belge_turu_adi backfill (dry-run varsayılan) |
| `retag_tracking_nos.py` | Takip numaralarını yeniden etiketleme |
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
| `yazim_birligi.py` | Tek seferlik yazım birliği (G160): teslim/ikiz yazımına göre 6 adım (anahtar SON noktayı yutar: "A.Ş." ↔ "A.Ş" ikiz, G164) + **adım 2b** (G163) — adım 2'nin atladığı tek yazımlı, teslimsiz taraf adlarında yalnız biçim farkı (`Quıck … A.ş` → `Quick … A.Ş`, `anahtar_genis` eşit) `tr_title`a çekilir; `--adim 2` daima 2+2b, kuru koşuda ilk 15 tekil satır sayısıyla basılır (onay listesi), `2b.csv`. Kuru koşu varsayılan; `--apply --kim` tarihçeli, envanter denk değilse rollback + çıkış 2 |
| `mukerrer_kart_raporu.py` | Aynı davayı gösteren kart grupları → iki CSV onay listesi (SALT OKUNUR; `--rapor-dizini`). Kart BİRLEŞTİRMEZ — `tracking_no` müvekkil bazlı ofis dosya numarasıdır, tek davada birden çok müvekkilin ayrı kartı olması doğrudur. "Aynı dava" hükmü `services/case_relations_auto.py`tan gelir |

İşi biten script silinebilir — git geçmişi saklar.
