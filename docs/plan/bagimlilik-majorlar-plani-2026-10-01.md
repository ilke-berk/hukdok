# Bağımlılık majorları planı — 2026-10-01

Kaynak: `docs/arsiv/bagimlilik-raporu-2026-10.md` §6 (İnsan kararı bekleyenler). 2026-10-01 kullanıcı kararı:
Office365-REST-Python-Client kaldırıldı (dal `bagimlilik/2026-10`, `0bc902c`); kalan dört major bu plana göre
yürür. Görevler: `gorevler/KUYRUK.md` "Bağımlılık majorları" bölümü, G243-G247.

## Sıra ve gerekçe

| # | İş | Görev | Ne zaman | Neden bu sırada |
| --- | --- | --- | --- | --- |
| 1 | reportlab 4.2.5 → 4.5.1 (son 4.x) | G243 | Gece 1 | PDF üretiminin iki yolu da (UDF→PDF `udf_converter.py`, rapor PDF'i `report_builder.py`) reportlab'da. 28.08 prod arızası (görselli tablo bölme) bu kodda çıktı → önce aynı major içinde, küçük adımla |
| 2 | reportlab 4.5.1 → 5.0.x | G244 | Gece 1 | 5.0 kaldırmaları (`_renderPM`, pyRXP, uzak görsel `trustedHosts` varsayılanı) ayrı commit'te ölçülür; geri almak tek satır |
| 3 | python:3.12-slim → 3.13-slim | G245 | Gece 1 | 3.14 DEĞİL: reportlab 4.x'in kullandığı `ast.NameConstant` 3.14'te kalkıyor; 3.13 tüm pinlerin wheel'iyle güvenli ara durak. 3.12 güvenlik desteği 2028-10'a dek sürer — acele yok, ama imaj/CI/mypy hedefi tek seferde hizalanır |
| 4 | postgres:15 → 17 PROVASI | G246 | Gece 1 | 18 DEĞİL: 17 olgun (17.11), 18 genç. PG15 desteği 2027-11'e dek. Gece işi yalnız PROVA + runbook; gerçek geçiş insan adımı (aşağıda) |
| 5 | node:24 → 26 | G247 | Node 26 LTS'e geçince (≈2026-10-28) | Node yalnız frontend build aşamasında; çalışan uygulama nginx → risk düşük. LTS öncesi BLOKE |

Tahmin: G243-G246 tek gece (hepsi `bant:backend`, seri). G247 Kasım başı ayrı koşu.

## Sınırlar (bütün görevler)

- Push / deploy / ssh YOK. Prod'a hiçbir şey çıkmaz; her görev tek commit.
- Test silme / gevşetme / skip YASAK. Kırmızıda görev BLOKE bırakılır, sürüm geri alınır.
- Gerçek müvekkil verisi (DB dump'ı) repo ve OneDrive altına yazılmaz → `C:\hukdok-veri\yedek\`.
- `docker-compose.yml` postgres imajı, `deploy.sh` `GATE_PG_IMAGE`, `.github/workflows/ci.yml` postgres servisi
  gece DEĞİŞMEZ: lokal veri hacmi PG15 biçiminde, imaj değişirse lokal stack açılmaz.

## Postgres 17 — gerçek geçiş (İNSAN ADIMI, G246 provasından sonra)

G246'nın ürettiği runbook'a göre, önce lokalde sonra prod'da, mesai dışı:

1. `pg_dump -Fc` (prod'da `deploy.sh` öncesi dump ile aynı yöntem) + dump'ın SharePoint yedeğinde olduğunu doğrula.
2. Stack'i durdur; PG15 hacmini SİLME — yeniden adlandır/yerinde bırak (geri dönüş yolu).
3. Üç yerde imajı aynı commit'te değiştir: `docker-compose.yml:4`, `deploy.sh:86` (`GATE_PG_IMAGE`),
   `ci.yml:28`; dokümanlar: `CLAUDE.md:14`, `docs/mimari/genel-bakis.md:22`, `docs/mimari/deploy-ve-altyapi.md:112`.
4. Boş PG17 hacmiyle kaldır → `pg_restore` → `migrate.py` → `/healthz` → `ANALYZE` → arama EXPLAIN ölçümü
   (`scripts/perf_olcum.py --term`), G246 rapor değerleriyle karşılaştır.
5. Geri dönüş: imajı 15'e çevir + eski hacmi geri bağla (`rollback.sh` DB'yi döndürmez — bu adım elle).

## Python 3.14 ve sonrası

reportlab 5 (G244) yeşil kalırsa 3.14 engeli kalkar; 3.14'e geçiş ayrı bir sonraki adım olarak bir sonraki aylık
denetimde değerlendirilir.

## Node 26 sonrası (bu planın dışında, sıradaki frontend majorları)

vite 8 + `@vitejs/plugin-react-swc` 4 + vitest 5 (Eylül raporu §5.11). Node 26'ya geçtikten sonra ayrı plan.
Not: host'ta Node v22.16.0 kurulu (vitest host'ta koşar); CI ve imaj Node 24. Host sürümünün yükseltilmesi
kullanıcı adımıdır (gece koşucusu sistem kurulumu yapmaz).
