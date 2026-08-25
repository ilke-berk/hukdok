# 019 — Süreç/konteyner ayrımı kapsam dışı: modüler monolit korunur

> Son doğrulama: 2026-08-24 · e56b26b (W0 ölçüm kapısı)

- **Durum:** kabul
- **Bağlam:** "Monolit mi mikroservis mi" tartışmasının pratik hali gündeme geldi: ağır iş
  (GhostScript PDF/A, LibreOffice, Gemini öncesi görüntü normalizasyonu) bugün **web
  sürecinin içinde** koşuyor. `/confirm` dönüşümü uvicorn'un thread pool'unda çalışıyor
  (`routes/processing.py:735`), arkaplan işleri (APScheduler, upload outbox) de aynı
  konteynerde lider kilidiyle ayrılıyor (`services/singleton_lock.py`,
  [`005`](005-upload-outbox-tek-worker.md)). Bu düzenin üç izi var: nginx
  `proxy_read_timeout 300s`, `MALLOC_ARENA_MAX=2` + 2 GB limit, ve `conversion_pending`
  emniyet katmanı ([`008`](008-conversion-pending-ayri-kolon.md)).
  Öneri, ağır işi **aynı imajdan kalkan ayrı bir worker konteynerine** taşımaktı
  (mikroservis DEĞİL — tek imaj, tek SHA, tek rollback korunarak).
- **Karar:** Süreç/konteyner ayrımı **kapsam dışıdır**. Mikroservis mimarisi de kapsam
  dışıdır. Aşağıdaki eşiklerden biri gerçekleşmeden yeniden ele alınmaz.

## Ölçüm — kararın dayanağı

Ayrım önerisi bir **sigortaydı**; sigortalanan iki risk (OOM ve uzun dönüşüm) ölçüldü ve
ikisi de bugünkü kodda mevcut değil.

**Yöntem.** Lokal `hukdok_backend` konteynerinde, **dosya başına ayrı süreç** (tepe RSS
izole ölçülsün diye), `resource.getrusage` ile `RUSAGE_SELF` + `RUSAGE_CHILDREN`.
`/confirm` yolu için `pdf.pdf_converter.convert_to_pdfa2b` (bütçesiz), `/process` yolu
için `analyzer.py`'nin gerçek dağıtımı (`.udf` → `udf_converter`, görüntü/office →
`ensure_pdf`, `.pdf` → doğrudan; sonra `pdf_utils.extract_key_pages`).
Corpus: `CALIB_DATA_DIR/demetler` **41 gerçek belge** + ağır uç için üretilen sentetik
belgeler (corpus'taki en büyük belge yalnız 15 sayfaydı).

| Ölçüm | Değer |
| --- | --- |
| Dönüşüm p50 / p95 / max (41 gerçek belge, 39 başarılı) | **0,62 / 2,55 / 2,60 sn** |
| Tepe RSS — gerçek corpus | **218 MB** (`.docx`→soffice; `.tif` 136 MB, `.pdf` 75 MB) |
| 300 sayfa / 325 MB taranmış PDF → PDF/A | **7,84 sn · 75 MB** |
| 300 sayfa / 32 MB **1-bit G4 TIFF** → PDF/A | **16,1 sn · 127 MB** |
| `/process` ön işleme p50 / p95 (Gemini hariç) | **0,49 / 1,12 sn** · tepe 218 MB |
| `/process` ön işleme, 300 sayfa G4 TIFF | **12,1 sn · 128 MB** |

Tür kırılımı (dönüşüm, p50 / max / tepe RSS): `.pdf` (23 dosya) 0,59 / 0,95 / 75 MB ·
`.tif` (6) 0,99 / 1,87 / 136 MB · `.udf` (5) 0,62 / 0,71 / 86 MB · `.jpeg` (3)
0,58 / 0,59 / 91 MB · `.docx` (2) 2,60 / 2,60 / 218 MB.

**Kritik satır G4 TIFF'tir.** 1-bit G4 TIFF, 2026-07-29 OOM'unun tam şeklidir: düzeltme
öncesi 10 sayfa ≈ +1 GB anon bellek üretiyordu (`docs/mimari/deploy-ve-altyapi.md`, OOM
incelemesi). Ölçüm **30 kat sayfada (300) 127 MB** gösteriyor — TIFF normalizasyonu +
`MALLOC_ARENA_MAX=2` düzeltmesi ([`011`](011-bellek-swap-yasagi.md)) ölçekte de tutuyor,
yani ayrımın sigortalayacağı arıza sınıfı **kapalı**.

**Tavanlar ölçülene göre 15-100 kat geniş.** `gs_timeout_seconds=240`
(`config/settings.py:59`), `confirm_conversion_budget_seconds=270` (`:75`),
`request_time_budget_seconds=300` (`:71`, nginx penceresiyle hizalama çıpası). En ağır
sentetik belge bütçesinin **~%6'sını** kullanıyor. Bu tavanlar bir gözlem değil, muhafazakâr
bir tavandır — 300 sn'lik nginx penceresi ölçülmüş bir dönüşüm süresini yansıtmaz.

**Prod kanıtı.** Yerel restore kopyasında 229 belge (2026-02-27 → 2026-08-05):
`conversion_status IS NOT NULL` = **0**. Senkron dönüşüm bu dönemde `conversion_pending`
katmanına **hiç** düşmemiş; emniyet ağı yerinde duruyor ve hiç tetiklenmemiş.

**Bellek bütçesi ayrıma karşı çalışıyor.** VM **e2-medium = 2 vCPU / 4 GB**
(`gcloud compute instances list`, 2026-08-24). Mevcut limitler backend 2g
(`docker-compose.yml:92`) + postgres 512m (`:21`) + frontend 128m (`:128`) = 2,64 GB.
Ayrım toplam RAM'i **artırmaz**, konteyner başına tavanı **böler** — ölçülen tepe 218 MB
iken 2 GB'lık tek tavanı 1 GB + 1 GB yapmak kazanç değil, gereksiz bir daraltmadır.

## Gerekçe

1. **Sigortalanan risk yok.** Ayrımın çözdüğü iki şey — dönüşüm belleğinin web sürecini
   öldürmesi ve dönüşümün nginx penceresini doldurması — ölçümde görünmüyor. Ölçülen
   kazanç yokken iş açılmaz.
2. **Mikroservisin çözdüğü üç problem bizde yok.** Bağımsız ölçekleme (tek VM, ~10
   kullanıcı), bağımsız takım/deploy temposu (tek geliştirici), teknoloji çeşitliliği
   (tek Python yığını). Geriye yalnız bedelleri kalır: sürüm uyumluluk matrisi, dağıtık
   şema koordinasyonu, servis başına test kapısı.
3. **Deploy garantileri monolit olduğu için sağlam.** `deploy.sh`'ın zinciri (ff-only pull
   → pre-deploy dump → çalışan stack'i bozmadan build → test kapısı → `up -d` → 120 sn
   `/healthz` kapısı) ve `rollback.sh <SHA>`'nın atomikliği, deploy biriminin **tek** olmasına
   dayanır. Süreçleri bölmek deploy birimini bölmese de sağlık kapısını, rollback
   yüzeyini ve log korelasyonunu genişletir.
4. **Asenkronlaşmanın gizli bedeli UX'tir.** Dönüşüm kuyruğa alınırsa `/confirm` "yüklendi,
   e-posta gitti" diyemez; hata kullanıcının yüzünden **logun içine** düşer. Telafisi
   (belge listesinde durum yüzeyi + bildirim) ayrımın kendisinden pahalıdır ve bugün
   karşılığında hiçbir ölçülmüş sorun çözülmemektedir.

## Reddedilenler

- **"Ağır işi ayrı konteynere alalım, aynı imaj kalsın" (worker ayrımı).** Mimari olarak
  doğru desen, ama bugün çözeceği sorun ölçümde yok (yukarıdaki tablo). Ayrıca
  `services/singleton_lock.py` kilidi **bilinçli konteyner-yereldir** — ikinci konteyner
  ikinci lider üretir; ayrım, liderliği rol kapısına ya da `pg_advisory_lock`'a taşımayı
  zorunlu kılar. Bedel gerçek, karşılığı yok.
- **"Sadece arkaplan işlerini (APScheduler + outbox) ayıralım" (ucuz varyant).** UX'e
  dokunmadığı için cazip; tek kazancı "web OOM'u arkaplan teslimatını öldürmesin"dir. Web
  OOM'u ölçümle olasılıksız hâle geldiği için bu kazanç da teoriktir. Yeniden açma
  eşiklerinden biri gerçekleşirse **ilk denenecek adım budur** — ayrımın en ucuz ve en az
  riskli parçasıdır.
- **"Analizi (`/process`) worker'a taşıyalım."** En pahalı seçenek: canlı NDJSON stream'i
  frontend ile **ortak sözleşmedir** ([`004`](004-failed-olay-sozlesmesi.md)); worker'a
  taşımak olayların bir tabloya yazılıp web tarafından relay edilmesini, yani sözleşmenin
  yeniden yazımını gerektirir. Ölçümde `/process` ön işlemesi p95 1,12 sn ve tepe 218 MB.
- **"Dönüşümü kısa bütçeli senkron dene, aşarsa kuyruğa" (hibrit).** UX'i korur ama
  dönüşüm belleği web sürecinde kaldığı için izolasyon kazancı yarımdır — yani bedelin
  tamamı ödenip faydanın yarısı alınır.
- **"Şimdiden bölelim, sonra ölçekleniriz."** 4 GB'lık tek VM'de ikinci bir konteyner,
  bugünkü tek gerçek kısıtı (bellek) bugün mevcut olmayan bir arıza moduna harcamaktır.
  [`017`](017-elasticsearch-ve-redis-kapsam-disi.md) ile aynı aritmetik.

## Yeniden açma eşikleri

Biri yeterlidir:

- **OOM tekrar ederse** — backend konteyneri bellek limitinden OOM-kill edilirse (Faz 2-C
  alarmları ya da `docker events`).
- **Prod'da dönüşüm p95'i > 30 sn olursa** — ölçüm kaynağı `timings["3a_pdfa_convert"]`
  (`services/document_pipeline.py:505`) ve `pdf/pdf_converter.py:195`'in
  `PDF → PDF/A-2b başarılı ({elapsed:.1f}s)` INFO satırı.
- **`conversion_pending`'e düşen belge oranı anlamlı hâle gelirse** — bugün 229/229'da 0.
- **Tek VM'den çıkılırsa** (yatay ölçekleme) — o noktada lider kilidi zaten yeniden
  tasarlanmak zorundadır ([`005`](005-upload-outbox-tek-worker.md)).

> Ölçüm sınırı, kararın parçasıdır: ölçüm **lokal makinede (16 vCPU)** koşuldu, prod
> e2-medium **2 vCPU**'dur. Mutlak süreler muhafazakâr bir 3-5× çarpanla okunmalıdır —
> çarpanla bile en ağır sentetik belge (16,1 sn → ~50-80 sn) 240 sn'lik GS tavanının
> altında kalır. Gemini çağrısı ölçüme dahil **değildir** (`/process` süresinin çoğu
> orada geçer), ama o ağ/model gecikmesidir; süreç ayrımının çözdüğü bir bellek ya da
> CPU baskısı değildir.

## Ölçüm sırasında çıkan yan bulgular

Bu kararın parçası değil; ayrı iş kalemleri olarak not edilir.

- **`.odt` dönüşümde desteklenmiyor.** `OFFICE_EXTENSIONS = {".docx", ".doc", ".xlsx",
  ".xls"}` (`pdf/format_converter.py:39`) `.odt` içermiyor → `convert_to_pdfa2b`
  `ValueError: Desteklenmeyen format: .odt` fırlatıyor. Corpus'ta 2 tensip zaptı bu
  formatta. LibreOffice imajda zaten kurulu.
- **53 belge `upload_status='failed'` ve `sharepoint_url` NULL** (yerel restore kopyası,
  2026-02-27..2026-07-30; `upload_attempts=0`). Outbox öncesi dönemin artığı olabilir —
  **prod'da doğrulanmadı**, ayrı bir denetim kalemi.

- **Test:** bu kayıt için yeni test yok (karar belgesi). Bütçe tavanlarının hizası
  `backend/tests` içindeki `test_faz5_settings_budget` bekçisiyle kilitli
  (`config/settings.py:74` yorumu: bütçe + 30 ≤ `request_time_budget`).
- **İlgili:** [`005-upload-outbox-tek-worker.md`](005-upload-outbox-tek-worker.md),
  [`008-conversion-pending-ayri-kolon.md`](008-conversion-pending-ayri-kolon.md),
  [`011-bellek-swap-yasagi.md`](011-bellek-swap-yasagi.md),
  [`017-elasticsearch-ve-redis-kapsam-disi.md`](017-elasticsearch-ve-redis-kapsam-disi.md),
  [`docs/mimari/deploy-ve-altyapi.md`](../mimari/deploy-ve-altyapi.md),
  [`docs/mimari/belge-isleme-hatti.md`](../mimari/belge-isleme-hatti.md)
