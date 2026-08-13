# 012 — Soft-delete: bağlar koparılmaz, `active` alanına dokunulmaz

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul
- **Bağlam:** Dava, müvekkil ve belge silme işlemleri hard-delete idi; yanlışlıkla silinen
  bir kaydı geri getirmek mümkün değildi. Hard-delete ayrıca `CaseParty.client_id`'yi
  `NULL`'layarak taraf bağlarını koparıyordu.
- **Karar:** `cases`, `clients`, `case_documents` tablolarında soft-delete —
  `deleted_at` / `deleted_by` / `delete_reason` kolonları. Kayıt DB'de kalır, listelerden
  gizlenir, admin geri alabilir. Silme sırasında **`CaseParty.client_id` NULL'lanmaz** ve
  **`Client.active` alanına dokunulmaz** (`backend/routes/clients.py:246-251`).
- **Gerekçe (docstring'den birebir):** "`CaseParty.client_id` BİLİNÇLİ NULL'lanmaz (eski
  hard-delete davranışıydı) — bağlar kopmadığı için restore sıfır maliyetli; taraf
  görünümleri zaten `p.client.name if p.client else p.name` ile çalışıyor.
  `Client.active`'e DOKUNULMAZ (kullanıcı-düzenlenebilir 'pasif cari' alanı)."

  İki ayrı fikir var burada: (a) restore'un ucuz olması için veri **bozulmamalı**;
  (b) `active` **kullanıcının** alanıdır — sistem onu silme sinyali olarak ele alırsa
  kullanıcının kendi "pasif cari" işaretiyle çakışır ve geri alma belirsizleşir.
- **Reddedilenler:** *Hard-delete* — geri alınamaz. *`active=false` ile silmeyi
  işaretlemek* — kullanıcı alanıyla sistem durumunu aynı kolona sıkıştırırdı.
  *Silmede bağları koparmak* — restore'u veri yeniden kurmaya dönüştürürdü.
- **Sonuçları:** Tüm kullanıcı sorguları `deleted_at IS NULL` filtreler
  (`backend/auth_helpers.py`); silinenleri gören tek yol admin panelidir (`api.py:411-412`).
  Silinmiş davanın belgesi hukukbot outbox'ına girmez, ama **dava restore edilirse belgeleri
  tekrar akabilir** — export filtresi dinamiktir, "istenen davranış"
  (`services/export_publisher.py:62-64`).
- **Test:** `backend/tests/test_soft_delete.py`, `backend/tests/test_migrations_drop.py`
- **İlgili:** [`001-tenant-ortak-havuz.md`](001-tenant-ortak-havuz.md)
