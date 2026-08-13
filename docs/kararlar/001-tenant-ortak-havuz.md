# 001 — Yeni kayıtlar `tenant_id=NULL`: iki tenant ortak havuzda çalışır

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul
- **Bağlam:** `cases` ve `clients` tablolarında `tenant_id` kolonu vardır ve giriş sırasında
  tenant `ALLOWED_TENANTS` listesine karşı doğrulanır (`backend/auth_verifier.py`). Ancak
  Hanyaloğlu Acar ve LexisBio aynı dosyalar üzerinde **birlikte** çalışır; katı tenant
  izolasyonu iki büronun ortak işini ikiye bölerdi.
- **Karar:** Yeni `cases` ve `clients` kayıtları bilinçli olarak `tenant_id=NULL` yazılır.
  Sorgular `tenant_id == X OR tenant_id IS NULL` deseniyle filtreler
  (`backend/auth_helpers.py:14-16`). `tenant_id` bağımlılığı endpoint imzalarında **kalır**
  ama damgalamada kullanılmaz.
- **Gerekçe:** Kodda birebir yazılıdır —
  `# Hanyaloğlu Acar + LexisBio ortak çalıştığı için yeni davalar paylaşımlı (tenant_id=NULL).`
  `# tenant_id Depends'i token doğrulaması için kalıyor ama damgalamada kullanılmıyor.`
  (`backend/routes/cases.py:55-56`; aynısı `backend/routes/clients.py:35-36`).
  `NULL` semantiği `auth_helpers.py` docstring'inde "paylaşılan/legacy" olarak tanımlıdır
  (`:1-4`) — yani hem eski kayıtlar hem yeni ortak kayıtlar aynı yolu kullanır.
- **Reddedilenler:** Katı tenant damgalaması (her kayda oluşturucu tenant yazmak). Kolon ve
  `Depends` şeması bu yolu açık bırakır: iki büro ayrılırsa yalnız yazma tarafı değişir,
  okuma filtresi zaten iki durumu da karşılar.
- **Sonuçları:** `tenant_id` bir güvenlik sınırı **değil**, hazırlık altyapısıdır — yeni bir
  izolasyon ihtiyacı çıkarsa bu kararın önce gözden geçirilmesi gerekir.
- **Test:** `backend/tests/test_soft_delete.py` (tenant + soft-delete filtreleri).
- **İlgili:** [`docs/mimari/genel-bakis.md`](../mimari/genel-bakis.md)
