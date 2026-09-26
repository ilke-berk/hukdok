# Gece Kuyruğu (workflow) · 2026-09-26b

## Özet

8 görev alındı · 7 işaretlendi · 0 bloke · 1 atlandı

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G202 · Dev araçları: pytest 9.1.1 + ruff 0.16.8 + mypy 2.3.1 + ci-kontrol pip-audit düzeltmesi | backend | — (zaten tamamdı; plan uyarısı: rapor fd0e843) | — | GEÇTİ (5 bulgu) | Bu koşuda uygulama yapılmadı. Görev önceden bitmişti ama KUYRUK'ta [ ] kalmıştı; bu koşuda denetlenip işaretlendi. |
| G211 · Müvekkil Sektör etiketi → Çalıştığı Kurum | backend | c81c880 | geçti (kırmızı→yeşil kanıtlandı) | GEÇTİ (3 bulgu) | 1 tur. Anahtar `sektor` korundu. `ruff check .` 6 hata veriyor; hepsi git'te olmayan `calibration-data/_g179/ek3_cevapla.py` dosyasında ve önceden vardı. Merge yok, ana dalda. |
| G222 · QuickCaseModal avukat seçimi LawyerCombobox'a | frontend | abec9a5 | geçti (kırmızı→yeşil kanıtlandı) | GEÇTİ (3 bulgu) | 1 tur. Merge yapıldı, entegrasyon yeşil, worktree temizlendi. Config testine yalnız mock eklendi, mevcut satırlar değişmedi. |
| G223 · Ofis no B1: kategori kodu X1'e düşüyor + sigorta kodu tr-TR hatası | frontend | fb6d93b | geçti (kırmızı→yeşil kanıtlandı) | GEÇTİ (2 bulgu) | 2 tur. Frontend 106 dosya, 1160 passed; lint ve `tsc -b --force` temiz. Merge yapıldı, entegrasyon yeşil, worktree temizlendi. Kapsam dışında yalnız `docs/veri-teslim/ofis-no-formati.md` değişti (kabul kriteri istiyordu). |
| G214 · case_notes tablosu + migrasyon + /api/cases/{id}/notes uçları | backend | 8ee1132 | geçti (kırmızı→yeşil kanıtlandı) | GEÇTİ (3 bulgu) | 2 tur. Sonuç: 3675 passed, 12 skipped; mypy ve ruff (calibration-data hariç) temiz. `models.py`'ye ilk ekleme Git Bash heredoc ile yapıldı; UTF-8 ve LF olduğu doğrulandı. Merge yok. |
| G207 · Doküman + infra: karar 021, CLAUDE.md/genel-bakış/kimlik-ve-token, hukbot nginx sitesi kalkar | docs | 6a7bf1f | geçti (kırmızı→yeşil uygulanamaz, test yok) | GEÇTİ (3 bulgu) | Merge yapıldı, worktree temizlendi. Kapsam dışında `docs/mimari/deploy-ve-altyapi.md`'de bir tablo satırının üstü çizildi. Sunucu adımları (site rm, nginx reload, certbot delete) insan işi. |
| G216 · POST /api/transcribe: ses → Gemini Türkçe metin | backend | 4d1ef82 | geçti (kırmızı→yeşil kanıtlandı) | GEÇTİ (3 bulgu) | 2 tur. Sonuç: 3701 passed, 12 skipped; mypy temiz. Ses diske düşmez (spool tavanı yükseltildi, akış tavanı 2 MB + 64 KB). Kullanıcı başına limiter yok; yalnız slowapi'nin IP anahtarlı varsayılan limiti uygulanıyor. Merge yok. |

Push hiçbir görevde yapılmadı.

## Bloke

Yok.

## Karar bekleyenler

- `gorevTanimiHatali` işaretli görev yok; karşılanmayan kabul maddesi de yok.
- Bilgi: G216'da kullanıcı başına hız limiti kurulmadı, yalnız IP anahtarlı varsayılan limit (100/dk) geçerli. Kullanıcı başına limit istenip istenmediği sorusu açık.
- Bilgi: G207'nin sunucu adımları (hukbot nginx sitesinin kaldırılması, reload, certbot delete) insan kararı ve eli bekliyor.

## İzin engelleri

Yok.

## Atlananlar

- **G219 · CLAUDE.md + docs/mimari özetleri** (docs): bu koşuda bağımlılığı tamamlanmadı (G217). Plan uyarısına göre G217 BLOKE olduğu için G219 koşulamadı. Worktree `C:/dev/hukudok-wt/G219` temizlenmedi, korunuyor.
