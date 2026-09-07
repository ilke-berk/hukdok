# Gece Kuyruğu (workflow) · 2026-09-07

## Özet

4 görev alındı · 1 işaretlendi · 1 bloke · 2 atlandı (tavan nedeniyle atlanan: yok)

## İşaretlenenler

| Görev | Bant | Commit | Kapı | Denetim | Not |
| --- | --- | --- | --- | --- | --- |
| G137 — Rapor kataloğu genişlemesi: grup/kontrol/hızlı filtre/kolon seti/öneriler + taraf bağlantılı 4 filtre (EXISTS, tenant kurallı) + 60 sn önbellek | backend | `23372ac` | GEÇTİ (test temiz, kırmızı-yeşil kanıtlandı, ihlal yok) | GEÇTİ (4 bulgu) | 2 tur. Tur 1'de tek kırmızı kendi testindeydi ('Taraflar' grup adı 'Karşı Taraflar' etiketiyle çakıştı — kod değil test hatası). Tur 2: 192 rapor testi, tam paket 2670 passed / 3 skipped, ruff + mypy temiz. Kolon kümesi 149→151 (yalnız iki yeni). Sözleşme farkı yok, plan dosyasına dokunulmadı. İzlenecek (G138/G140): `metin_icerir` combobox'ı öneri seçince `eq` üretir ama taraf kolonlarında eq izinli DEĞİL (yalnız contains/is_null/not_null) — frontend bu dört kolonda contains göndermeli ya da 4.3'e şerh. Merge yapılmadı (mergeYapildi=false), entegrasyon alanı boş. Ayrıca: çalışma ağacında baştan kirli olan kapsam dışı `.claude/settings.local.json` (M) ve `.claude/launch.json` (??) dokunulmadan bırakıldı ve commit'e alınmadı; işçi kapsam-dışı-kirli kuralını bu yüzden bloke olarak uygulamadı — koşucu gözden geçirsin. |

## Bloke

### G138 — Rapor ekranı: filtre şeridi + operatörsüz kontroller + gruplu alan seçici + otomatik önizleme + başlıktan sıralama + kaynak değişiminde anında yenileme (frontend)

**Durma sebebi:** testi değiştirmeden geçilemedi — görev tanımı gözden geçirilmeli.
Bu bir başarısızlık değil, hattın doğru çalıştığının kanıtıdır: işçi sözleşmesi
mevcut testleri değiştirmeyi yasaklar, görev ise mevcut testlerin sınadığı davranışı
bilinçli olarak kaldırmayı ister; işçi kod yazmadan durdu.

**Son parmak izi:** yok (kod yazılmadı, tur 0, verify çalıştırılmadı). Baz durum:
HEAD `93e0fbf` üzerinde `vitest run` 4 dosya / 64 test yeşil.

**Denenen yaklaşımlar:**
- Kurulum: worktree `C:/dev/hukudok-wt/G138` (dal `gorev/G138`, HEAD 93e0fbf) + `npm ci` başarılı.
- Görev dosyası + plan §2/§4 + reports.ts / ReportsPage / ReportBuilder / FilterRow / PreviewTable / builderState okundu.
- Üç ReportsPage test dosyası kabul kriterlerine karşı eşleştirildi: Operatör select, "Filtre ekle"/filtre-satırı, "Sıralama ekle"/sıralama-satırı, "Önizle" düğmesi, bayat-rozeti `not.toBeNull`, asistan eylem=null'da preview sayısının 1'de kalması → görevin özüyle doğrudan çelişiyor.
- Yan yana yaşatma (eski select'leri gizli tutma, Önizle düğmesini koruma) değerlendirildi: kabul kriteri 1 ve §4.1-5'i ihlal eder → reddedildi.
- Görev dosyasına `DURUM: BLOKE` + çelişki tablosu yazıldı (uncommitted); commit atılmadı.

**Kök neden (teşhis):** Görevin kabul kriterleri mevcut `ReportsPage.test.tsx`,
`ReportsPage.sablon.test.tsx` ve `ReportsPage.asistan.test.tsx` ile yapısal olarak
çelişiyor (operatör açılır listesinin kalkması, bayat rozetinin kalkması, Önizle
düğmesinin kalkması/otomatik önizleme, asistan eylem=null'da otomatik önizleme,
Sıralama bölümünün kalkması). Görev dosyası kapsamında "ilgili *.test.ts(x)" yazıyor
(planlayıcı test güncellemesini öngörmüş) ama işçi sözleşmesi mutlak: karar insanın.
Ek gözlem: KATALOG test sahteleri §4.2 alanlarını (grup/kontrol/öneriler/hızlı_filtreler/
kolon_setleri) içermiyor; tipler zorunlu tanımlanırsa `tsc -b` sahteleri de reddeder →
test sahtelerinin güncellenmesi zaten kaçınılmaz.

**Worktree:** `C:/dev/hukudok-wt/G138` korunuyor; tek değişiklik görev dosyası
(uncommitted). Geçici dosya kalmadı. Entegrasyon: uygulanamaz.

**Önerilen sonraki adım (iki seçenek):**
1. G138'e `ReportsPage.test.tsx` / `ReportsPage.sablon.test.tsx` /
   `ReportsPage.asistan.test.tsx` için açık test-değiştirme izni verilip yeniden koşulması; ya da
2. İşin ikiye bölünmesi — (a) yalnız ek: lib fonksiyonları + yeni bileşenler kendi
   testleriyle, sayfaya bağlanmadan; (b) entegrasyon + eski testlerin yeniden yazımı.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok. Karşılanmayan kabul maddeleri (G138)
soru olarak:

1. G138: Operatör açılır listesinin tamamen kalkması isteniyor; mevcut testler Operatör select'ini ve op listelerini sınıyor. Bu testler yeniden yazılabilir mi?
2. G138: Bayat rozetinin koddan çıkması isteniyor; mevcut testler rozetin ÇIKMASINI (var olmasını) bekliyor. Test beklentisi ters çevrilsin mi?
3. G138: Otomatik önizleme / Önizle düğmesinin kalkması isteniyor; mevcut testler Önizle'ye basıp elle basılana dek istek sayısının artmamasını bekliyor. Otomatik önizleme davranışı bu testleri geçersiz kılar — onay?
4. G138: Asistan tanımı eylem=null'da otomatik önizlenecek; `asistan.test.tsx:387-390` tam tersini bekliyor. Hangisi doğru davranış?
5. G138: Başlıktan sıralama ile Sıralama bölümünün kaldırılması isteniyor; mevcut testler "Sıralama ekle" + select'lerini sınıyor. Kaldırma onaylanıyor mu?
6. G138: Liste alanlarında serbest metin yok / combobox — bloke nedeniyle uygulanmadı; yukarıdaki kararlar sonrası tek parça mı, bölünmüş görev mi?
7. G138: Kaynak değişince eski satırların temizlenmesi — bloke nedeniyle uygulanmadı; aynı karar kapsamında.
8. G137 notu (G138/G140'a etki): taraf kolonlarında `eq` izinli değil; frontend combobox öneri seçince `contains` mi göndersin, yoksa plan 4.3'e şerh mi düşülsün?

## İzin engelleri

yok

## Atlananlar

| Görev | Sebep |
| --- | --- |
| G139 — Rapor ekranı: kaynak kartları + Kolonlar yan paneli + dolu açılış + metin sadeleştirme + responsive (frontend) | Bağımlılık bu koşuda tamamlanmadı: G138 (bloke). Worktree `C:/dev/hukudok-wt/G139` açıldı, temizlenmedi. |
| G140 — raporlama.md ikinci tur + plan §4 durum/kanıt şerhi (docs) | Bağımlılık bu koşuda tamamlanmadı: G139 (atlandı). Worktree `C:/dev/hukudok-wt/G140` açıldı, temizlenmedi. |

Zincir hatası / teslim hatası olan görev yok. Tavan nedeniyle atlanan yok.

## Plan uyarıları (koşucudan)

- G138 ve G139 aynı frontend bandında ve ReportsPage.tsx / ReportBuilder.tsx / PreviewTable.tsx dosyalarında kesişiyor; G139 zaten G138'e bağımlı, seri koşulmalı.
- G137 ve G138 paralel: dosya kesişimi yok (backend/** vs frontend/**).
- Son günlük KUYRUK'ta belirtilen `docs/plan/veri-kalitesi-duzenleme-plani-2026-09-06.md` gitStatus başlangıç anlık görüntüsünde untracked görünüyordu; güncel git status'ta yok (commit edilmiş ya da kaldırılmış).
