# Tek Seferlik / Operasyonel Scriptler

Uygulama kodundan ayrı tutulan, elle çalıştırılan scriptler. Hiçbiri API
tarafından import edilmez; Docker imajına girseler de çalışma zamanında
kullanılmazlar.

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
| `hukdok_aktarim.py` | HUKDOK teslim paketi → kart aktarımı (idempotent; `--dry-run`, `--limit`, `--sheet`). Belge envanteri denk değilse koşuyu geri alır ve NONZERO çıkar. `import_excel_cases.py`'nin halefi — o script KULLANILMAZ (idempotent değil, hata yolunda veri kaybı) |

| `mukerrer_kart_raporu.py` | Aynı davayı gösteren kart grupları → iki CSV onay listesi (SALT OKUNUR; `--rapor-dizini`). Kart BİRLEŞTİRMEZ — `tracking_no` müvekkil bazlı ofis dosya numarasıdır, tek davada birden çok müvekkilin ayrı kartı olması doğrudur. "Aynı dava" hükmü `services/case_relations_auto.py`tan gelir |

İşi biten script silinebilir — git geçmişi saklar.
