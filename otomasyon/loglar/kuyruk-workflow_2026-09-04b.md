# Gece Kuyruğu (workflow) · 2026-09-04b

## Özet

2 görev alındı · 2 işaretlendi · 0 bloke · 0 atlandı

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G121 — Kart UI: iki kapalı liste alanı büro kartında + liste filtresi Hizmet Türü (G119 sözleşmesi) | frontend | `5595942` | geçti (test temiz, kırmızı-yeşil kanıtlandı, ihlal yok) | GEÇTİ (2 bulgu) | 1 tur. Tur-1 yaması `git apply` ile alındı; planlayıcı istisnası (OFFICE_CARD_FIELDS kilidi dört anahtara) uygulandı; yamanın CaseList'te atladığı üç yer (sayfa sıfırlama effect deps, clearFilters, activeFilterCount) tamamlandı. Son parmak izi: vitest 52 dosya/614 passed, eslint 0, tsc -b --force 0. `api.ts`'e dokunulmadı. Kart alanları G105 emsaliyle salt-okunur `ClosedListValue`. Merge yapıldı, entegrasyon yeşil, worktree temizlendi. **Backend G119 ile birleşince canlı doğrulama gerekir.** |
| G122 — Bilgilendirme sürüm 1.1 + SOZLESME + veri-teslim-hatti + dava-acma-akisi | docs | `1918e24` | geçti (test temiz; kırmızı-yeşil docs bandında uygulanamaz) | GEÇTİ (3 bulgu) | 1 tur, test yok (docs bandı). SUTUN_ADAYLARI/seed_data/HAVUZ_LISTE_ESLEMESI/ASAMA_ONCEKI/party_check ast+grep ile koddan okundu; karşılaştırma: kod 42 alan/54 yazım = dok 42/54 birebir, fark kümeleri boş. Diff yalnız 4 docs + görev dosyası. Merge yapıldı, entegrasyon uygulanamaz, worktree temizlendi. |

Notlar (G122'den izlenecekler): (1) `iddia_edilen_kusur` aktarımda doğrulamasız metin — istenirse G104 deseniyle doğrulamalı yazım, küçük backend görevi; (2) REV-2 bildirim metni repoya/SharePoint arşivine konursa §3.2'deki genel DB-003 şerhi adlı listeye çevrilebilir; (3) Bilgilendirme 1.1'in veri ekibine gönderilmesi insan adımı. `veri-teslim-hatti`'ndaki iki tablo satırı (90, 96) kaçışlı pipe nedeniyle sayımda uyumsuz görünür — önceden vardı, değiştirilmedi.

## Bloke

yok

## Karar bekleyenler

`gorevTanimiHatali=true` teşhisi olan görev yok.

Kabul karşılanmayan maddeler (SORU):

- **G122 / DB-003 kalemi:** Görev tanımı "bu başlıklar artık gelmiyor (04.09) şerhiyle işaretlenir" diyor; on dört sütunun ADLARI işaretlenemedi çünkü REV-2 bildirim metni repoda/scratchpad/Downloads/Masaüstü'nde yok (yalnız bizim cevabımız var). §3.2'ye adsız genel şerh yazıldı. **Soru:** REV-2 bildirim metni repoya ya da SharePoint arşivine konulacak mı? Konulursa genel şerh adlı listeye çevrilebilir (küçük docs görevi). Kabul kriterleri listesindeki 5 madde karşılandı; bu kalem kabul listesi dışında, görev tanımı gövdesindeydi.

## İzin engelleri

yok

## Atlananlar

yok (atlandı/zincirHatası/teslimHatası olan görev yok; tavan nedeniyle atlanan yok)

## Plan uyarıları (koşucudan)

- G121: KUYRUK satırında BLOKE yok; görev dosyasında 04.09 1. tur BLOKE sonrası "Planlayıcı istisnası" bölümü vardı (tek izinli mevcut-test değişikliği) — işçi bu bölümü uyguladı. `api.ts`'e dokunma kısıtına uyuldu.
- G122: G121'e bağımlıydı, G121 bitince seçildi; docs bandı kod dosyası değiştirmedi, `docs/arsiv/`'e dosya eklenmedi.

## Ana dizin notu

`.claude/settings.local.json` (kirli) ve `.claude/launch.json` (izlenmeyen) harness dosyalarıdır; koşu dokunmadı.
