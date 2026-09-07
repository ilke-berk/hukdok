# Gece Kuyruğu (workflow) · 2026-09-07b

## Özet

3 görev alındı · 1 işaretlendi · 1 bloke · 1 atlandı

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G138 — Rapor ekranı: filtre şeridi + operatörsüz kontroller + gruplu alan seçici + otomatik önizleme + başlıktan sıralama + kaynak değişiminde anında yenileme | frontend | `34fcf77` | geçti (test temiz, kırmızı-yeşil kanıtlandı, ihlal 0) | GEÇTİ (5 bulgu, onarım gerekmedi) | 5 tur; merge yapıldı, entegrasyon yeşil, worktree temizlendi. Görev dosyasındaki açık izinle ReportsPage/.sablon/.asistan sayfa testleri ve reports.test.ts katalog sahteleri yeniden yazıldı (gerekçe tablosu G138.md Rapor bölümünde); test sayısı düşmedi (reports.test 23→60), kilit testler (reports.export, reportsChat, RunsTable/TemplateBar), hub dosyalar ve package.json dokunulmadı. Worktree'de npm test 786/786 (63 dosya), lint 0, tsc -b --force 0. Tarayıcı önizlemesi yapılmadı (MSAL kapılı, bant test/lint/tsc). Plan sapmaları: useDebounce yerine efekt + ref bayrağı (yapısal-hemen / yazım-600ms / odak-çıkışı ayrımı); `tanimGecerliMi`'de "türetilmiş" engeli kaldırıldı (motor.py:136,149 yalnız filtrelenebilir/sıralanabilir'e bakıyor). |

**Yan gözlem (G138'e bağlı değil, ayrı bakılmalı):** tam paketin ilk koşusunda `lib/api.test.ts > apiClient.fetch > eşzamanlı iki token'sız istek tek logout tetikler` bir kez kırmızı düştü (`logoutRedirect` 1 beklenirken 2); dosya bu görevde dokunulmadı, tek başına (28/28) ve ikinci tam koşuda (786/786) yeşil. Hub testinde zamanlama kararsızlığı izi.

## Bloke

### G139 — Rapor ekranı: kaynak kartları + Kolonlar yan paneli (gruplar/setler/sıra) + dolu açılış + metin sadeleştirme + responsive (frontend)

**Durum:** testi değiştirmeden geçilemedi, görev tanımı gözden geçirilmeli. Bu bir başarısızlık değil — hattın sözleşmeye uygun çalıştığının kanıtı: işçi kod yazmadan önce mevcut testlerin kilitlediği DOM'u taradı, kabul kriterlerinin bunlarla doğrudan çeliştiğini gördü ve durdu. Kod yazılmadı, commit yok, verify koşulmadı (0 tur).

**Son parmak izi:** yok (test koşulmadı).

**Denenen yaklaşımlar:**
1. Kurulum: worktree + `gorev/G139` dalı + `npm ci` tamam (HEAD `ff75457`).
2. Mevcut testlerin kilitlediği DOM tarandı; çatışma tablosu görev dosyasına yazıldı (worktree'de, commit YOK).

**Teşhisin kök nedeni:** G139 kabul kriterleri mevcut testlerin doğruladığı arayüzü bilinçli kaldırıyor; G138'de olduğu gibi planlayıcının görev dosyasına "Test değiştirme İZNİ" bölümü yazması gerekiyor. Çatışmalar:
1. `ReportsPage.test.tsx:506-518` section.className için `xl:grid-cols-[320px_1fr]` bekliyor — madde 2 (sol sütun yok) bunu kaldırır.
2. `#rapor-kaynak` `<select>` beklentisi: ReportsPage.test ×6, sablon.test:502,523, asistan.test:341,404,498 — madde 1 (SourceCards) bunu kaldırır.
3. `[data-kolon]` listesi + kolon checkbox / "Ofis No aşağı" / "Temizle" sayfada doğrudan bekleniyor (ReportsPage.test:260-287,381,390,422; sablon:300,402,503,524,530; asistan:282,399,405,474,499,547) — madde 3 kolonları kapalı açılan ColumnSheet içine taşır.
4. Toplam rozeti tam metni "Toplam 120 kayıt" (ReportsPage.test:267,343,432; PreviewTable.test:102) — madde 4 "N kayıt · M kolon" ister.

Ek tasarım boşluğu: Sheet primitive'i repoda YOK (`ui/sheet.tsx` yok, yeni paket yasak) → mevcut `@radix-ui/react-dialog` üzerine yan panel mi, G138'in portal'sız `useDisariTiklama` deseni mi? (Radix portal jsdom'da container dışına düşer; testler `document.body` okumalı.)

**Karşılanmayan kabul maddeleri:** sayfa açılışında tablo dolu; sol sütun yok / kolonlar yalnız yan panelde; tip rozetleri / kaynak açıklaması yalnız kartta; şablon/Excel/asistan/geçmiş regresyonu; tam genişlik + lg altı; npm test/lint/tsc — tümü kod yazılmadığı/koşulmadığı için.

**Worktree:** `C:/dev/hukudok-wt/G139` (dal `gorev/G139`) korunuyor; çatışma tablosu görev dosyasında commit'siz duruyor.

**Önerilen sonraki adım:** planlayıcı G139.md'ye G138'dekine benzer "Test değiştirme İZNİ ve planlayıcı kararları" bölümü ekler (aşağıdaki sorulara cevaplarla), sonra görev yeniden kuyruğa alınır; G140 bunun arkasından açılır.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok. G139'un kabul maddeleri ve işçinin planlayıcıya soruları SORU olarak:

1. G139: `ReportsPage.test.tsx`, `ReportsPage.sablon.test.tsx`, `ReportsPage.asistan.test.tsx`, `PreviewTable.test.tsx` — bu dört test dosyasını değiştirme izni veriliyor mu? (Kilit korunacaklar: reports.export.test.ts, reportsChat.test.ts, QuickFilters.test.tsx, builderState.test.ts, RunsTable/TemplateBar testleri.)
2. G139: sablon/asistan testlerinde seçili kolon doğrulaması nasıl yapılsın — "Kolonlar (N)" düğmesi + istek gövdesi (işçinin önerisi) mi, panel açıp `[data-kolon]` mi?
3. G139: yan panel için Sheet primitive yok — `@radix-ui/react-dialog` üzerine yan panel mi, G138'in portal'sız `useDisariTiklama` deseni mi?
4. G139: "Sayfa açılışında tablo dolu", "Sol sütun yok; kolonlar yalnızca yan panelden", "Tip rozetleri yok / kaynak açıklaması yalnız kartta", "Tam genişlik + lg altı" maddeleri mevcut haliyle korunacak mı, yoksa yukarıdaki test çatışmaları ışığında yeniden yazılacak mı?

## İzin engelleri

yok (G138, G139, G140 — üçünde de izinEngelleri boş).

## Atlananlar

- **G140** — raporlama.md ikinci tur + plan §4 durum/kanıt şerhi (docs): atlandı, sebep "bağımlılık bu koşuda tamamlanmadı: G139". Worktree `C:/dev/hukudok-wt/G140` açıldı ve temizlenmedi (kod/commit yok).

## Plan uyarıları (koşucudan)

- G138 satırında artık BLOKE yok; HEAD `0a37e2f` "G138 blokesi çözüldü" — görev dosyasındaki izin bölümü işçi tarafından okundu ve kullanıldı.
- G138/G139 aynı frontend bandı, ReportsPage/PreviewTable/ReportBuilder dosyalarında kesişiyor — seri koşuldu.
- `docs/plan/veri-kalitesi-duzenleme-plani-2026-09-06.md` oturum başı snapshot'ında takipsizdi, güncel git status'ta yok (commit edilmiş olabilir).
- Tavan nedeniyle atlanan: yok.
