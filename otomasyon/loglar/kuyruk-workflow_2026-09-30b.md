# Gece Kuyruğu (workflow) · 2026-09-30b

## Özet

7 görev alındı · 0 işaretlendi · 1 bloke · 6 atlandı

Koşu, zincirin ilk halkası G235'in ikinci bağımsız denetimde RET almasıyla durdu; kalan altı görev
bağımlılık nedeniyle hiç başlamadı. Tavan nedeniyle atlanan görev yok.

## İşaretlenenler

| görev | bant | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | Bu koşuda işaretlenen görev yok. |

## Bloke

### G235 — `services/ofis_no.py` üretici + atomik sayaç + kategori kodları + sigorta kısa kodları + admin uçları (migrasyon 56)

- **Bant:** backend
- **Durum:** uygulandı, `isaretlendi=false`, `bloke=true`. Merge yapılmadı (`mergeYapildi=false`,
  entegrasyon: uygulanamaz). Görev TAMAMLANMIŞ SAYILMAZ.
- **Commit:** `a4677e5` (işçi commit'i). Onarım turu 1 bulguyu düzeltti (`onar.basarili=true`,
  düzeltilen 1, düzeltilemeyen yok); git geçmişinde bunu izleyen `b4d9ed6` (denetim bulguları) ve
  `5df455a` (kuyruk durumu - G235 BLOKE) commit'leri var.
- **Durma sebebi (işçi):** `yesil` — 2 tur. Doğrulama yeşil, kapı geçti (test temiz, kırmızı-yeşil
  kanıtlandı, ihlal yok). Blokenin kaynağı işçi değil, DENETİMDİR.
- **Bloke sebebi:** denetim RET (ikinci denetim).
- **Son parmak izi:** `mypy arg-type services/ofis_no.py:256 + call-overload managers/seed_data.py:336 (giderildi)`

**Denenen yaklaşımlar**

1. Tur 1: üretici + modeller + migrasyon 56 + seed + admin uçları + testler; pytest 3973 passed /
   15 skipped, ruff temiz, mypy 2 hata (`Column[str]` tip uyumsuzluğu: `ofis_no.py` ve `seed_data.py`).
2. Tur 2: iki yerde `str()` sarmalaması; mypy temiz, ruff temiz, etkilenen test dosyaları
   (g235 x2, seed_data, migration_path) 148 passed.

**Denetim zinciri**

- **Denetim 1 — RET (6 bulgu):** `sigortali_sec`, föy "Sigortalı" alanındaki `;` ayraçlı çok adlı
  değeri (lokal veride 124/4300 föy) tek ad sayıp iki ayrı kişiyi/kurumu kaynaştırarak var olmayan
  bir sigortalı bloğu üretiyor (örn. `DR.U.S`, `DR.G.HASTANESI`, `DR.H.YILDIZ`). Karar 023 §7
  "TEK kişi, kendi kategori koduyla" kuralı gerçek veride karşılanmıyor; hiçbir test bu vakayı
  kapsamıyor.
- **Onarım:** başarılı, 1 bulgu düzeltildi, düzeltilemeyen kalmadı. (Denetim 1 "6 bulgu" saydı,
  onarım "1 düzeltilen" raporladı — kalan bulguların akıbeti veride yok; sabah elle bakılmalı.)
- **Denetim 2 — RET:** Karar 023 §2 "Acente → KR" kuralı uçtan uca karşılanmıyor: lokal verideki
  iki Acente müvekkilin ikisi de (KAYNAK SİGORTA, YKM SİGORTA) adında "sigorta" geçtiği için
  `musteri_kodu`'ndan `KR.<ad>` yerine `SG` alıyor; test yalnız `kategori_kodu`'nu ölçtüğü için yeşil.

**Teşhisin kök nedeni**

Teşhis adımı çıktı üretmedi (`teshis` boş). Denetim gerekçelerinden okunan ortak örüntü: testler
birim düzeyinde (tek fonksiyon, sentetik girdi) yeşil, ama kural gerçek lokal veriyle uçtan uca
ölçülmüyor. İki RET de aynı türden: (1) çok adlı "Sigortalı" alanı, (2) adında "sigorta" geçen
Acente müvekkil — ad sezgisi kategori kodunun önüne geçiyor. Bu bir çıkarımdır, teşhis verisi değildir.

**Worktree:** yok (`worktree=null`; görev ana çalışma ağacında koştu).

**Önerilen sonraki adım**

1. `musteri_kodu`'nda öncelik sırasını netleştir: müvekkilin kategorisi (Acente → KR) ad içindeki
   "sigorta" sezgisinden ÖNCE gelmeli; KAYNAK SİGORTA ve YKM SİGORTA için uçtan uca test ekle
   (`kategori_kodu` değil `musteri_kodu` çıktısı ölçülsün).
2. Denetim 1'in 6 bulgusundan onarımın kapatmadığı kalemleri gözden geçir; `;` ayraçlı çok adlı
   "Sigortalı" vakası için gerçek veriden örnekli test olduğunu doğrula.
3. Aşağıdaki "Karar bekleyenler" sorularını yanıtladıktan sonra G235'i yeniden denetime sok;
   G236 ve sonrası ancak G235 işaretlenince koşabilir.

**İşçi notları (aynen)**

1. Tam pytest koşusu mypy düzeltmesinden (iki `str()` sarmalaması) ÖNCE alındı; düzeltmeden sonra
   yalnız etkilenen 4 test dosyası (148 test) + ruff + mypy yeniden koşuldu.
2. Yorum kararı: "müvekkil kodu" = numaranın İLK bloğunun tamamı (`DR.M.OZTURK`, `AXA`) — sayaç
   anahtarı ve `cases.ofis_no_kodu` bunu taşır (VARCHAR(120)); G236/G238 sırayı bu anahtarla tahsis etmeli.
3. Kategori kodu için mevcut genel kategori ucuna alan eklemek yerine ayrı uç seçildi
   (`/api/admin/kategori-kodlari`) — `routes/config.py`, `reference_lists.py`, `schemas.py` kapsam
   dışıydı; şema sınıfları `routes/admin.py` içinde.
4. Görevde açıkça istenmeyen ek: kısmi unique index `uq_cases_ofis_no_kod_sira` (aynı kod+sıra iki
   karta verilemez; bugün 0 kart dolu).
5. `sigortali_sec` kaynak sırasına karar 023 §5 (sigortacıyla birlikte müvekkil) 3. sıra olarak
   eklendi; §7 yalnız üç kaynak sayıyor — denetçi/kullanıcı teyidi iyi olur.
6. Lokal backend restart edildi: migrasyon 56 lokal DB'ye uygulandı (2 tablo, 3 kolon, 2 index;
   7 kategori kodu + 11 sigorta kodu seed'li).
7. Skill "kapsam dışı kirli dosya → BLOKE" diyor; görev öncesinden kalan izlenmeyen
   `.claude/launch.json` (harness yapılandırması) için bloke edilmedi — dokunulmadı, commit'e girmedi.
8. Görev dosyasındaki `docker compose build backend` adımı koşulmadı: lokal compose `./backend`'i
   bind-mount ediyor, testler güncel kodu koşturdu.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan görev yok; `kabulKarsilanmayan` listeleri boş. Aşağıdakiler
denetim RET gerekçelerinden ve işçi notlarından doğan, insan kararı isteyen sorulardır:

- **G235 · Acente önceliği:** Adında "sigorta" geçen Acente müvekkil (KAYNAK SİGORTA, YKM SİGORTA)
  karar 023 §2 gereği `KR.<ad>` mı almalı, yoksa sigorta şirketi sayılıp `SG`/kısa kod mu? Kategori
  mi belirleyici, ad mı?
- **G235 · Çok adlı "Sigortalı":** Föyde `;` ile ayrılmış birden çok sigortalı varsa (124/4300 föy)
  numara bloğu hangisinden üretilir — ilki mi, belirli bir kategori önceliği mi, yoksa bu kartlar
  "sigortalı eksik/belirsiz" raporuna mı düşer?
- **G235 · §5 ile §7 uyumu:** `sigortali_sec`'e §5 (sigortacıyla birlikte müvekkil) 3. kaynak olarak
  eklendi; §7 yalnız üç kaynak sayıyor. Bu ek kaynak isteniyor mu?
- **G235 · Görev dışı ek:** `uq_cases_ofis_no_kod_sira` kısmi unique index'i görevde istenmemişti;
  kalsın mı?
- **G235 · Ayrı admin ucu:** Kategori kodu için `/api/admin/kategori-kodlari` ayrı ucu kabul mü
  (G241 frontend bunu tüketecek)?

## İzin engelleri

yok

## Atlananlar

| görev | bant | sebep |
| --- | --- | --- |
| G236 | backend | bağımlılık bu koşuda tamamlanmadı: G235 |
| G238 | backend | bağımlılık bu koşuda tamamlanmadı: G236 |
| G237 | frontend | bağımlılık bu koşuda tamamlanmadı: G236 |
| G239 | backend | bağımlılık bu koşuda tamamlanmadı: G237, G238 |
| G241 | frontend | bağımlılık bu koşuda tamamlanmadı: G235, G237 |
| G240 | docs | bağımlılık bu koşuda tamamlanmadı: G239, G241 |

Zincir hatası ya da teslim hatası bildiren görev yok.

**Temizlenmemiş worktree'ler** (`worktreeTemizlendi=false`; görevler başlamadı, içlerinde iş yok —
elle kontrol edilip kaldırılabilir):

- `C:/dev/hukudok-wt/G237`
- `C:/dev/hukudok-wt/G241`
- `C:/dev/hukudok-wt/G240`

## Plan uyarıları

- G235: Rapor bölümü boştu (`(isci oturumu doldurur)`) — kullanıcı isteği gereği baştan koşuldu;
  çalışma ağacı temizdi, önceki denemeden artık yoktu.
- G242: KUYRUK'ta `[x]` (30.09 kullanıcı kararı) — bitti sayıldı, G240 bağımlılığı karşılanmış kabul edildi.
- G241: dosya kapsamında adsız kalemler var (yeni hook/api yardımcısı, müşteri kategorisi yönetim
  bileşeni, testler) — `dosya[]` yalnız adı geçen yolları içerir.
- G237/G239: dosya kapsamında "ilgili testler" adsız — `dosya[]` yalnız adı geçen yolları içerir.
