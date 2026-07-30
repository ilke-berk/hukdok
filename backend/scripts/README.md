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

İşi biten script silinebilir — git geçmişi saklar.
