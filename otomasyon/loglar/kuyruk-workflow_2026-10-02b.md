# Gece Kuyruğu (workflow) · 2026-10-02b

## Özet

6 görev alındı · 6 işaretlendi · 0 bloke · 0 atlandı

Tavan nedeniyle atlanan: yok. Push/deploy yapılmadı. Hiçbir `--apply` prod'da koşulmadı; lokal DB'ye tek yazım G250'deki `backfill_missing_required.py --apply` (1 satır, aşağıda).

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G249 — Hizmet kaydı: aktarım föy başına satır + geriye dönük doldurma script'i + birleştir/ayır | backend | `127d6e7` | geçti (test temiz, kırmızı→yeşil kanıtlandı) | GEÇTİ (5 bulgu) | 2 tur. pytest 4236 passed / 15 skipped, ruff + mypy temiz. 8 test insan onaylı izinle yeni davranışa taşındı (g120 ×7, g123 ×1; silme/skip yok) + `test_g249_hizmet_aktarim.py` (18 test). `hizmet_kayitlari_doldur.py --apply` KOŞULMADI. mergeYapildi=false, worktree yok (veriye göre). |
| G257 — Hizmet listesi paketten: `deger_havuzu_seed` + aktarım eşlemesi DB listesinden | backend | `2eb3769` | geçti (test temiz, kırmızı→yeşil kanıtlandı) | GEÇTİ (5 bulgu) | 1 tur, ilk tam koşu yeşil. pytest 4252 passed / 15 skipped. Taşınan test YOK (eşleme koşuya özel ContextVar ile; modül sözlüğü yerinde değişmedi). mergeYapildi=false, worktree yok. |
| G250 — `CasePartyCreate.hizmet_turleri` + hizmetsiz müvekkil 422 + filtre EXISTS + PATCH'te `hizmet_turu` kapanır | backend | `c9fa991` | geçti (test temiz, kırmızı→yeşil kanıtlandı) | GEÇTİ (6 bulgu — denetçi: "RET sebebi değil, sabah insan kararı gerektiren notlar") | 2 tur. pytest 4277 passed / 15 skipped. `test_g119` içinde 14 test izinle taşındı. Lokal DB'ye 1 satırlık backfill yazıldı. mergeYapildi=false, worktree yok. |
| G251 — Raporlama "Hizmetler" kaynağı + davalarda çok değerli hizmet kolonu + asistan kataloğu | backend (+ `frontend/src/lib/reportsChat.ts`) | `03771d4` | geçti (test temiz, kırmızı→yeşil kanıtlandı) | GEÇTİ (6 bulgu) | 1 tur. pytest 4295 passed / 15 skipped, vitest 1456 passed, `tsc -b --force` temiz. Kaynak listesini sabitleyen 6 dosyada beklentiler 4→5 kaynağa taşındı. mergeYapildi=false, worktree yok. |
| G253 — NewCase + intake + QuickCaseModal: müvekkil başına hizmet seçici | frontend | `895af01` | geçti (test temiz, kırmızı→yeşil kanıtlandı) | GEÇTİ (5 bulgu) | 2 tur. vitest 140 dosya / 1531 passed, lint 0 hata, `tsc -b --force` temiz. Merge yapıldı, entegrasyon yeşil, worktree `C:/dev/hukudok-wt/G253` temizlendi. Görsel doğrulama YAPILMADI. |
| G254 — CLAUDE.md + dava-acma-akisi + veri-teslim-hatti + raporlama dokümanları | docs | `f5c00a0` | geçti (kırmızı→yeşil uygulanamaz) | GEÇTİ (5 bulgu) | 1 tur, verify = test-yok (docs bandı). 99 dosya:satır referansı kontrol edildi (işçi beyanı; denetçi bağımsız doğruladı). Merge yapıldı, entegrasyon uygulanamaz, worktree `C:/dev/hukudok-wt/G254` temizlendi. |

### Denetimde bağımsız doğrulanamayanlar (başarıyı abartmamak için)

- **G249:** denetçi doldurma script'inin kuru koşusunu kendisi koşamadı (izin sınıflandırıcısı yazıp-geri-alan komutu reddetti). 8416 föy / 8403 satır / 8 kapsam dışı / 5 müvekkilsiz / 6496 kart salt okunur SQL ile doğrulandı; **"özeti değişen kart 1061" sayısı bağımsız doğrulanmadı**.
- **G257:** denetçi 01.10 paketiyle seed kuru koşusunu tekrar koşamadı (izin reddedildi); "service_types 0 yeni" iddiası yalnız dolaylı doğrulandı (lokal DB'de 9 liste adı = föylerdeki 9 farklı değer).
- **G251:** lokalde `case_hizmetleri` 0 satır → "Hizmetler" kaynağı gerçek veriyle ölçülmedi (satır sayısı/süre yok); asistan ipucu gerçek Gemini ile denenmedi.
- **G253:** görsel doğrulama yok (worktree'de backend/oturum yok).
- **G254:** `hizmet_kayitlari_doldur.py` kuru koşusu koşulmadı; 8.403 / 13 atlanan / 1.061 sayıları G249 raporundan kaynak gösterilerek alındı.

## Bloke

Bloke görev yok.

(`test-degistirmek-gerekti` ile duran görev de yok. Plan uyarısı: G249'un görev dosyasındaki Rapor bölümünde önceki koşudan kalma "DURUM: BLOKE" metni duruyor — o koşuda test taşıma izni yoktu; bu koşuda insan onaylı izinle geçildi.)

## Karar bekleyenler

Biçimsel kaynak boş: hiçbir görevde `teshis.gorevTanimiHatali=true` yok, `kabulKarsilanmayan` listelerinin tamamı boş.

İşçi/denetçi notlarından çıkan, sabah insan kararı isteyen SORULAR:

1. **G250 — boş liste istisnası onaylanıyor mu?** `service_types` listesi BOŞSA "her müvekkilin en az bir hizmeti olmalı" kuralı atlanıyor (WARNING). İşçinin açık beyanı: istisna olmasaydı izin listesinde OLMAYAN `tests/test_g196_status_kapisi.py` düşerdi ve görev BLOKE kalırdı. Koşulsuz kural isteniyorsa `_taraf_hizmetlerini_dogrula`'daki boş-liste dalı kalkar ve `test_g196` için taşıma izni gerekir. (G253 frontend'de aynı kuralı uyguluyor; orada da izinsiz `NewCase.ofisNo.test.tsx` düşerdi.)
2. **G250 — lokal DB yazımı kabul mü?** Görev kuru koşuda 0 bekliyordu, ölçüm 1 çıktı (kart 14355 bayrağı bayat); `test_g046` nöbetçi testi yakaladığı için `backfill_missing_required.py --apply` LOKALDE koşuldu (1 satır; kova MANUAL 7899→7898, NULL 22→23). Prod'a dokunulmadı.
3. **G250 — PATCH'te `hizmet_turu` yok sayılsın mı, 422 mi?** İşçi "yok say" seçti (aynı gövdedeki öteki takip alanları kaydolsun diye).
4. **G250/G253 — PUT'ta `service_type`:** backend PUT alan yoksa kolonu None'a çekiyor; frontend bu yüzden düzenlemede kayıttaki değeri geri gönderiyor. Backend tarafı düzeltilsin mi (kapsam dışı NOT)?
5. **G251 — müvekkil kartı bağı:** görev metni "client_id → müvekkiller" diyordu; işçi raporun öteki bağlarıyla aynı `kart_eslesmesi` kuralını (id doluysa o kart, boşsa ad anahtarı) kullandı. Sapma kabul mü?
6. **G251 — `prompts.py` ÖZET RAPOR kuralı** hâlâ "müvekkil başına dağılım → müvekkiller" diyor (dosya kapsam dışıydı). Güncellensin mi?
7. **G257 — `service_types` tek değerli havuz:** pakette "A ; B" hücresi gelirse seed onu tek ad olarak ekler ve aktarım o adla satır yazar (bugünkü pakette yok). Ayrıca seed `casefold`, aktarım `_baslik_anahtari` kullanıyor — yalnız Türkçe büyük harfle farklı yazım seed'de yeni ad sayılabilir. Hizalansın mı?
8. **G249 — boş listede doğrulama atlanır** (`foydan_yaz`, G248 sözleşmesi); ayırmada föyün hizmeti listede yoksa satır taşınmaz, eski karttaki satır silinir. Kabul mü?
9. **G254 — SOZLESME.md'ye eklenen tarihli not veri ekibine iletilecek mi?** (Ana metin ve sürüm no değişmedi.)
10. **Co-Authored-By yazımı tutarsız:** G254 "Claude Fable 5", öteki işçi commit'leri "Claude Fable 5.1" kullandı. Skill metni mi düzeltilsin?

İnsan adımları (koşulmadı, sıra önemli):

- `deger_havuzu_seed --apply` ÖNCE, aktarım SONRA (lokal + prod, mesai dışı). Bugünkü pakette `service_types` için yazılacak satır yok.
- `hizmet_kayitlari_doldur.py`: dump → kopyada kuru koşu → `--apply` (prod mesai dışı). Koşulana dek hizmet filtresi (G250) ve "Hizmetler" rapor kaynağı (G251) BOŞ döner; lokalde özeti dolu 5.800 kartın hiçbiri hizmet filtresinde çıkmıyor.
- **Deploy sırası:** G250 + G253 birlikte deploy edilmeli (G250 tek başına inerse seed'li listede her yeni kart ve intake commit 422 alır).

Kapsam dışı kalan doküman/iş notları:

- `backend/scripts/README.md`'ye doldurma script'i satırı eklenmedi (G249 ve G254 ikisi de not düştü).
- `docs/mimari/raporlama.md` §7 (asistan) değişmedi; veri-teslim-hatti.md ve raporlama.md'nin dokunulmayan bölümlerinde eski satır numaraları duruyor; `BILGILENDIRME_2026-09-03.md` okunmadı/güncellenmedi.
- G250 raporunda geçen `scripts/export_davalar_ornek_excel.py` okuyucusu `backend/scripts` altında yok (G254 tespiti).
- G249: aktarım koşusuna föy başına ~4 sorgu + 1 SAVEPOINT eklendi; süre etkisi ÖLÇÜLMEDİ (tahmin +20-30 sn / 8,4k föy).

Süreç sapmaları (işçi beyanı):

- G250: yeni test dosyasının son bloğu Git Bash heredoc'uyla eklendi (Edit/Write kuralından sapma; UTF-8/LF doğrulandı).
- G253: `lib/newCasePayload.ts` bir kez Python betiğiyle düzenlendi (git diff ile Türkçe içerik doğrulandı). Kapsam listesinde adıyla olmayan yeni dosya: `frontend/src/lib/muvekkilHizmetleri.ts` (+testi).
- G257: konteynerdeki geçici paket kopyası (`/tmp/g257_paket.xlsx`) `docker compose exec -u root ... rm -f` ile silindi.
- G251: tam pytest arka plan komutu exit 1 bildirdi — sebep pytest değil, geçici logun erken silinmesi; rapor testleri ayrıca exit=0 ile yeniden koşuldu.
- Tüm görevlerde çalışma ağacında görev öncesinden kalan `.claude/settings.local.json` (M) ve `.claude/launch.json` (??) vardı; dokunulmadı, commit'lere girmedi.

## İzin engelleri

yok (altı görevin `izinEngelleri` listelerinin tamamı boş).

Gözlem (liste kaynağı DEĞİL, yalnız bilgi): G249 ve G257 denetçilerinin `sebep` metinleri izin reddi anıyor (yazıp-geri-alan kuru koşu komutu; seed kuru koşusu) ama bunlar `izinEngelleri` alanına düşmemiş. İzin listesi bu bölümden genişletileceği için bu iki ret listeye girmedi; denetçinin izin engellerini alana yazmaması ayrıca ele alınmalı.

## Atlananlar

yok (atlandı / zincirHatasi / teslimHatasi taşıyan görev yok; tavan nedeniyle atlanan yok).

Plan uyarıları (koşu öncesi):

- G249: görev dosyasında önceki koşudan "DURUM: BLOKE" metni duruyor; KUYRUK satırında BLOKE eki silinmiş, "İnsan kararı 02.10 - test taşıma izni" bölümü var.
- G257, G250, G251, G253: yeniden koşuda `testTasimaIzni` argümanı görev dosyalarındaki listelerle birebir verilmeli.
- G255: görev dosyasında "Rapor" bölümü yok; `hukdok_aktarim.py`'yi G249/G257 ile paylaşır → G257'den SONRA koşmalı (bağımlı alanında yazmıyor). Bu koşuda alınmadı.
- G251: bant backend ama `frontend/src/lib/reportsChat.ts`'e de dokunur (pytest + vitest).
- G253: `dosya[]` içindeki test adları görev dosyasında yolsuz/glob verilmiş.
- Docker çalışıyordu (server 29.7.2); konteyner durumu sorgulanmadı.
