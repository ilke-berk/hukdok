# Gece Kuyrugu (workflow) · 2026-09-04

## Ozet

4 gorev alindi · 2 isaretlendi · 1 bloke · 1 atlandi

Tavan nedeniyle atlanan: yok. Merge yapilan gorev yok (`mergeYapildi=false` tumunde); isaretlenen iki gorevin commit'leri `gorev/G119` ve `gorev/G120` dallarinda, entegrasyon alani bos.

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G119 — Müvekkil Tipi + Hizmet Türü: cases'e iki kolon + client_types(5)/service_types(9) seed'li listeler + config uçları + kart yolu + hizmet_turu filtresi | backend | `1e7b1e2` | GECTI (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI (3 bulgu, kapsam disi notlar) | 2 tur. Tur 1'de tam kosuda 4 kirmizi: lokal dev DB'de `cases.muvekkil_tipi` kolonu yoktu (UndefinedColumn) — kod hatasi degil, konteynerde `python migrate.py` kosulunca yesil. Son parmak izi: 2398 passed / 3 skipped, ruff + mypy temiz. Mevcut `cases.service_type` (ofis dosya no hizmet blogu) yeni `hizmet_turu` ile ILGISIZ; G121 UI etiket cakismasina dikkat etmeli. |
| G120 — Aktarım eşlemesi: Müvekkil Tipi + Hizmet Türü sütunları teslimden kartlara (G104 deseni, AlanHatasi) | backend | `dc124af` | GECTI (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI (2 bulgu) | 1 tur, ilk kosuda yesil: 2435 passed / 3 skipped, ruff + mypy temiz; 37 yeni test, kabul 6/6. Gercek teslim paketi kosulmadi (kapsam kod+test). |

Her iki gorevin ortak kapsam disi notu: `services/teslim_cevap.py` `HAVUZ_LISTE_ESLEMESI` yeni iki listeyi (client_types/service_types) icermiyor — bilincli birakildi, ayri karar gerekir. Prod deploy'da `migrate.py` iki kolonu ekler, seed 5+9 satir yazar.

Calisma agacinda oturum oncesinden kirli `.claude/settings.local.json` ve `.claude/launch.json` (harness dosyalari) iki gorevde de dokunulmadi ve commit'e alinmadi.

## Bloke

### G121 — Kart UI: iki kapalı liste alanı büro kartında + liste filtresi Hizmet Türü (frontend)

**Durma sebebi:** `test-degistirmek-gerekti` — bu bir basarisizlik DEGIL: hat kurali geregi ajan mevcut bir testi degistirmeden gecemedi ve durdu (hattin dogru calistiginin kaniti). Baslik altinda: **testi degistirmeden gecilemedi, gorev tanimi gozden gecirilmeli.**

**Son parmak izi:** vitest 613 passed / 1 failed — `src/lib/caseCardFields.test.ts:112` > `'dosya_son_durumu karttan cikti'`: `toEqual` beklentisi `[acceptance_date, bureau_type]`, alinan `+muvekkil_tipi +hizmet_turu`. lint temiz; `tsc -b --force` exit 0.

**Denenen yaklasimlar:**
- Tur 1: G105 deseniyle tam uygulama (`caseCardFields` + `useConfig` + `useCases` + `CaseDetails` closedLists tek nesne + `CaseList` Hizmet Turu Select) + 12 yeni test. Tek kirmizi yukaridaki tam-liste kilidi. Alternatif (alanlari ayri sabit `OFFICE_SERVICE_FIELDS`'ta tutup kartta birlestirmek) testi oyalama sayilacagi icin bilincli denenmedi.

**Kok neden:** Mevcut test `OFFICE_CARD_FIELDS`'i tam liste olarak kilitliyor; gorev tanimi ise bu listeye iki satir eklemeyi istiyor. Iki gereksinim birbirini dislar — kodda hata yok, gorev tanimi ile test beklentisi celisiyor. Ayni durumda G105, `MEDICAL_CARD_FIELDS` testini guncellemisti ("G105 ile yedi alan" yorumu); G121 tanimi bu izne acikca yer vermedigi icin ajan durdu.

**Worktree (korunuyor):** `C:/dev/hukudok-wt/G121` — dal `gorev/G121`, HEAD `38a4d07`, kirli: 5 M + gorev dosyasi + 3 yeni test. `api.ts`'e dokunulmadi ('Dokunma' notu ihlal edilmedi). Backend G119 paralel oldugu icin canli uc duman testi yapilmadi. Commit yok.

**Onerilen sonraki adim:** Planlayici karari (bkz. Karar bekleyenler). Karar (a) verilirse tek satirlik test degisikligi + worktree'deki degisiklikler tek commit olur; sonra G119 main'e alinmis haliyle canli uc duman testi. Ardindan G122 kilidi acilir.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan gorev yok (teshis listeleri bos). Kabul karsilanmayan madde SORU olarak:

- **G121 / kabul "Mevcut testlerde gerileme yok":** `caseCardFields.test.ts:112` `OFFICE_CARD_FIELDS`'i `[acceptance_date, bureau_type]` olarak kilitliyor; iki yeni alan eklenince kacinilmaz kiriliyor. SORU: (a) test beklentisi `["acceptance_date","bureau_type","muvekkil_tipi","hizmet_turu"]` yapilsin ya da testin asil amacina (`not.toContain("dosya_son_durumu")`) indirgensin — G105 emsali (onerilen); (b) alanlar ayri sabitte tutulup kartta birlestirilsin — test dokunulmaz ama karti yanlis anlatir (onerilmez). Hangisi? Karar gorev tanimina yazilmali.
- **G119/G120 ortak (karar notu):** `services/teslim_cevap.py` `HAVUZ_LISTE_ESLEMESI`'ne client_types/service_types eklensin mi? Her iki gorev kapsam disi birakti; cevap paketinde bu listeler gorunmeyecek.

## Izin engelleri

yok (G119, G120, G121 izinEngelleri bos; G122 kosulmadi).

## Atlananlar

- **G122** — Bilgilendirme sürüm 1.1 + SOZLESME + veri-teslim-hatti + dava-acma-akisi (docs): `atlandi` = "bagimlilik bu kosuda tamamlanmadi: G121". 0 tur, dokunulmadi. Worktree `C:/dev/hukudok-wt/G122` olusturulmus ve temizlenmemis (`worktreeTemizlendi=false`) — bos/kullanilmamis olmali, ertesi kosuda yeniden kullanilabilir ya da silinir. G121 karari verilip isaretlenince kilidi acilir.

Zincir hatasi / teslim hatasi olan gorev yok.

## Plan uyarilari (kosu girdisi)

- G121 'Dokunma' notu: `frontend/src/lib/api.ts` yalniz `hizmet_turu` parametresi gerekirse degistirilebilir; baska degisiklik BLOKE — uyuldu, dosyaya dokunulmadi.
- G119 tasarim karari: `client_categories`/`bureau_types` KULLANILMAZ, iki yeni liste acilir — uyuldu, denetim dokunulmadigini teyit etti.
