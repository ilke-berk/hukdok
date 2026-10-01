# Gece Kuyruğu (workflow) · 2026-10-01

## Özet

4 görev alındı · 4 işaretlendi · 0 bloke · 0 atlandı

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G243 · reportlab 4.2.5 → 4.5.1 + PDF önce/sonra karşılaştırması | backend | cca8920 | geçti (test temiz) | GEÇTİ (2 bulgu) | 11 kalibrasyon UDF + sentetik görselli tablo + rows_to_pdf ölçümü: sayfa sayıları ve metin hash'leri eşit. 4.5.1 Image+splitInRow çökmesini kendisi gideriyor; workaround yerinde bırakıldı. 4.3.x changelog sayfası 404 (o seri doğrulanamadı). Bağımlılık chardet → charset-normalizer. **İnsan adımı:** görselli 2 PDF'i gözle karşılaştırma. |
| G246 · Postgres 17 geçiş PROVASI + runbook | backend | 3cb53bd | geçti (test temiz) | GEÇTİ (3 bulgu) | Kod/konfig değişikliği yok. Geçici PG17 konteynerinde restore 0 hata, migrate şema diff'i boş, pytest 4082 passed / 15 skipped (PG15 ile aynı), örnek EXPLAIN kök düğümleri birebir. Konteyner+hacim silindi. Geçiş deploy.sh ile tek adımda yapılamaz; runbook ayrı pencere tarif ediyor. PG17 dump'ı PG15'e doğrudan dönmez. INTERSECT yolu ayrıca ölçülmedi. |
| G244 · reportlab 4.5.1 → 5.0.x + kaldırılan API taraması | backend | 7a672d5 | geçti (test temiz) | GEÇTİ (3 bulgu) | 5.0.1; CHANGES kalemleri grep'lendi, kullanım yok; --progress=plain rebuild (pip CACHED değil); ölçüm farkı yok. Uzak URL probu OSError (sebep ayrıştırılmadı). Ölçümler `C:\hukdok-veri\perf\g244\` (repo dışı). **İnsan adımı:** sentetik_gorselli.pdf + udf_02.pdf gözle karşılaştırma, deploy sonrası UDF yükleme dumanı. `dis-bagimliliklar.md` sürüm tablosu bayat (kapsam dışı). |
| G245 · Python 3.12 → 3.13 | backend | e830384 | geçti (test temiz) | GEÇTİ (3 bulgu) | İlk turda yeşil: 4082 passed, 15 skipped; ruff ok; mypy ok (65 dosya). Konteyner Python 3.13.15; yeni DeprecationWarning 0; /healthz 200, lider worker işleri başladı. **İnsan adımı:** push sonrası `gh run watch` ile CI 3.13 yeşil görülmeli. Kapsam dışı: `backend/api.py:200` yorumu hâlâ python:3.12-slim diyor. |

Not: Dört görevde de `mergeYapildi=false`, worktree yok — commit'ler doğrudan çalışma dalında. Push yapılmadı.

## Bloke

Yok.

## Karar bekleyenler

Görev tanımı hatalı işaretlenen ya da karşılanmayan kabul maddesi olan görev yok. Plan uyarılarından insan teyidi gereken sorular:

- **SORU:** Bellek notu "bagimlilik/2026-10 dalı main'e birleşmeden gece koşusu YOK" diyor; koşu HEAD main 0a948e1 üzerinde yapıldı. Dal durumu kontrol edilip bu kural ihlali mi, yoksa birleşme sonrası mı olduğu teyit edilmeli mi?
- **SORU:** G245 bağımlılık bilgisi KUYRUK'ta `bagimli:G243` ile görev dosyasındaki G243 tutarlı görünüyor; uyarı metni çelişkili ("'-' değil") — kuyruk satırı gözden geçirilsin mi?
- **SORU (G246):** PG17 geçişi için compose'da hacim anahtarını yeni ada taşıma önerisi ve ayrı bakım penceresi onaylanıyor mu?

## İzin engelleri

yok

## Atlananlar

Yok (tavan nedeniyle atlanan da yok).
