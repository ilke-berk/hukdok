"""Raporlama modülü (G130+): kayıt defteri (`registry`), sorgu motoru (`motor`).

Kullanıcı tanımlı listeler: istemci yalnız kayıt defterindeki veri kaynağı /
kolon / filtre anahtarlarını gönderir (serbest SQL YOK — plan K1), sorgu
sunucuda SQLAlchemy Core ile kurulur; tenant + soft-delete tek yerden uygulanır
(K2). Sözleşme: `docs/plan/raporlama-plani-2026-09-06.md` §2.
"""
