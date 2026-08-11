# İş kuyruğu

Format: `- [ ] Gxxx | bant:backend|frontend|docs | bagimli:-|Gyyy,Gzzz | Kısa başlık`
Ayrıntılar ve kurallar: [README.md](README.md). Görev tanımları: `gorev/<id>.md`.

## Aktif plan: Sertleştirme kalanı — FAZ 4/5 (4-A ve 5-A klasik yolla bitti; kalan 3 paket burada)

<!-- 4-B iki göreve bölündü (G001 backend + G002 frontend); "failed" olay sözleşmesi iki görev
     dosyasında da dondurulmuş durumda. Takip dosyası güncellemelerini YALNIZ G005 yapar.
     Deploy #6+#7 kararı kullanıcıda. FAZ 6 bu kuyrukta DEĞİL (gündüz, kullanıcıyla). -->

- [x] G001 | bant:backend | bagimli:- | 4-B-be: analiz akışına "failed" terminal olayı
- [x] G002 | bant:frontend | bagimli:- | 4-B-fe: hata≠boş veri + getClientCaseSequence fail-hard + failed işleme
- [x] G003 | bant:backend | bagimli:G001 | 5-B: HTTP durum kodu disiplini + /process Pydantic şeması
- [x] G004 | bant:frontend | bagimli:G002 | 4-C: taslak kalıcılığı + beforeunload + logout daraltma
- [x] G005 | bant:backend | bagimli:G001,G002,G003,G004 | Takip senkronizasyonu + DEPLOY #6+#7 HAZIR notu

## Aktif plan: FAZ 6 — AI-dostu repo (2026-08-12 gecesi; deploy GEREKMEZ, hepsi seri/ana dizin)

<!-- Eski md'ler SİLİNMEZ, arşivlenir; yeni dokümanlar KODDAN türetilir (eski model bulguları
     doğrulanmadan giremez — kural görev dosyalarında). G008 takip dosyasını kapatır. -->

- [x] G006 | bant:backend | bagimli:- | 6-A: CLAUDE.md + docs reorg (arsiv şerhi + referans güncelleme)
- [x] G007 | bant:backend | bagimli:G006 | 6-B-1: docs/mimari içerikleri + ADR'ler (koddan türetilmiş)
- [x] G008 | bant:backend | bagimli:G007 | 6-B-2: modül docstring'leri + proje skill'leri + plan kapanışı

## Aktif plan: Temizlik planı FAZ 0 + FAZ A (2026-08-11; deploy kararı kullanıcıda)

<!-- Kaynak: docs/plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md (25 ajanlı keşif+denetim).
     KUYRUĞA GİRMEYENLER: 0.5 ofis no kategori rejimi (X1=1.658 kayıt — geçmiş veri kararı
     kullanıcıda, ADR şart), 0.6 prod export/hukukbot denetimi (ssh gerekir, otomasyon yapamaz),
     A.2'nin veri silme/taşıma kısmı (gerçek müvekkil verisi — kullanıcı işi), service_type
     backfill (reçete canlı veride çürüdü, ayrı keşif gerekiyor), pip/npm yükseltmelerinin
     kendisi (G022 kararı sonrası, kullanıcı onayıyla).
     Backend bandı SERİ: G014→G015→G016→G017→G018 sırayla koşar (bağımlılık değil, bant kuralı).
     Gerçek paralellik: backend × frontend × docs üçlüsünden gelir. -->

- [x] G014 | bant:backend | bagimli:- | 0.2+0.4-be: hata yutan kapılar (find_duplicate_cases + client-sequence)
- [x] G015 | bant:backend | bagimli:- | 0.1: .eml SSRF (denetim RET — G023 DEVRALDI, satır kapatıldı)
- [x] G016 | bant:backend | bagimli:- | 0.8: /api/documents bağlantısız belgelerde tenant izolasyonu yok
- [x] G017 | bant:backend | bagimli:- | A.4: tanıdık sorgu aday indeksi TTL cache + normalizasyon memoize
- [x] G018 | bant:backend | bagimli:- | A.1+A.3+0.7: gzip, eksik preview proxy'si, init:true, backend/.dockerignore
- [x] G019 | bant:frontend | bagimli:G014 | 0.2+0.3-fe: checkDuplicateCase + useConfig hata yutması
- [x] G020 | bant:frontend | bagimli:G019 | service_type kayıt yüküne eklensin + as CaseData cast'i kalksın
- [x] G021 | bant:frontend | bagimli:- | A.5: ölü npm bağımlılıkları (docx/mammoth/file-saver/get-port)
- [x] G022 | bant:docs | bagimli:- | A.5+A.6: bağımlılık + runtime yaşlanma ADR'si (yükseltme YAPMAZ)

## Aktif plan: SSRF kapatma (2026-08-11 gecesi bypass avından; G015'in RET'ini kapatır)

<!-- Kaynak: 13 ajanlı bypass avı (wf_e88f2d18-1b5). G015'in regex tabanlı düzeltmesi 8 ayrı
     yükle delindi (hepsi gerçek soffice GET'i üretti) → G023 tokenizer'a taşıyor.
     Ofis formatları (.docx/.xlsx) AYRI ve DAHA GENİŞ bir açık: /process ana belge hattı da
     etkileniyor → G024. İkisi de backend bandı, seri koşar; G024 G023'ü bekler (aynı sınıf,
     G023'ün kalan-açık beyanı G024'ün girdisi).
     KUYRUĞA GİRMEYEN: çıkış ağı denetimi (RFC1918 + 169.254.0.0/16 + loopback kapatma) —
     infra + ADR işi, ssh gerekir, KULLANICI KARARI. -->

- [x] G023 | bant:backend | bagimli:- | .eml gövde temizliğini tokenizer'a taşı (G015 RET'ini kapatır)
- [x] G024 | bant:backend | bagimli:G023 | Ofis dosyalarında SSRF: harici bağlı görsel temizliksiz soffice'e gidiyor
- [x] G025 | bant:backend | bagimli:- | G023 gerilemesi: "&lt;" ile başlayan gövde metni sessizce yok oluyor

<!-- G025 kaynağı: bağımsız ÜÇÜNCÜ denetim (2026-08-12). İki SSRF iddiası da DOĞRULANDI —
     denetçi 50 YENİ varyant yazdı, pozitif kontrol 83 istek üretti, temizlenmiş korpus 0;
     üstelik G024 tohumu BİLEREK KAPALIYKEN sanitizer tek başına ayakta kaldı. Ama G023
     güvenlik dışı bir gerileme getirdi: handle_data `<` ile başlayan metin koşusunu atıyor,
     convert_charrefs=True olduğu için `&lt;` çözülmüş `<` olarak geliyor → Outlook
     gövdelerindeki `<ad@firma.com>` ve `<<yer tutucu>>` metinleri sessizce kayboluyor.
     Gemini analizini besleyen yol bu. Düzeltme ölçüldü: at yerine kaçışla.
     AYRICA (kuyruğa girmedi): backend imajı BAYAT, html_sanitizer.py imajda yok — lokal
     testler override bind-mount'u sayesinde doğru kodu koşuyor, imaj deploy'da kurulacak. -->

## Aktif plan: FAZ C — temizlik (2026-08-12; kullanıcı "temizliğe başla" dedi)

<!-- Bu fazın ölçüsü net satır deltasının NEGATİF olmasıdır — silme görev tipi.
     PAZARLIKSIZ KURAL: getattr/string-dispatch/dinamik import taraması yapılmadan hiçbir
     sembol ölü sayılmaz. Taslak plan config_manager setter'larını "ölü" sanmıştı, denetim
     çürüttü (8'i reference_lists.py:532 getattr'ıyla canlı) — o yüzden her aday yeniden
     doğrulanır, görev dosyasındaki listeye güvenilmez.
     Silinecekler test kaybı ÜRETMİYOR (tarandı: hedef sembollerin testlerde 0 eşleşmesi var),
     bu yüzden denetçinin "test sayısı düştü" kırmızı bayrağı bu fazda tetiklenmemeli.
     Bant dağılımı: frontend zinciri (G026→G027) + backend (G028) + docs (G029) paralel.
     G029 satır SAYISINI azaltmaz, yalnız çalışma dizinini sadeleştirir — dürüst çerçeve
     görev dosyasında yazılı. -->

- [x] G026 | bant:frontend | bagimli:- | Ölü ui/sidebar.tsx (637) + kaskadını sil
- [x] G027 | bant:frontend | bagimli:G026 | CaseGroup.tsx (666) + kalan ölü ui/ bileşenleri + sahipsiz npm
- [x] G028 | bant:backend | bagimli:- | Backend ölü katmanlar: LogManager sınıfı, DatabaseManager, SyncLog, AnalysisCache, ölü route alias'ları
- [x] G029 | bant:docs | bagimli:- | Kapanmış görev dosyalarını arşivle (G001-G025 → docs/arsiv/gorevler/)

## Sıradaki temizlik adayları (FAZ C'den çıktı, kuyruğa YAZILMADI — kullanıcı onayı bekler)

<!-- FAZ C işçilerinin bulduğu, kapsam dışı bırakılan kalemler. -->

- **`npx tsc --noEmit` KAPISI SAHTE** (G026 buldu, doğrulandı): `frontend/tsconfig.json`
  solution-style (`"files": []` + `references`) → komut yardım metnini basıp **exit 0**
  dönüyor, tek dosya denetlemiyor. Bu gecenin G019/G020/G021/G026/G027 görevlerinde
  "tsc temiz" kriteri **boştu**. Gerçek denetim: `tsc --noEmit -p tsconfig.app.json`.
  Görev şablonundaki doğrulama komutu düzeltilmeli.
- **4 tip hatası main dalında canlı** (gerçek denetim ilk kez koşunca çıktı):
  `AdminPage.tsx:427`, `CaseDetails.tsx:561`, `AvukatDashboard.tsx:120`,
  `IdariDashboard.tsx:99` — hepsi `TS2352`/`TS2322`. FAZ C'nin ürünü değil, önceden vardı.
- `hooks/use-mobile.tsx` (11 satır) — tek tüketicisi silinen `ui/sidebar.tsx`'ti (G026 notu)
- `docs/plan/guvenilirlik-sertlestirme-uygulama-takibi.md:67,69` bayat düz-metin atıfları
  artık `docs/arsiv/gorevler/` altını kastediyor (G029 notu; link değiller, kırık yok)
- `/plan-hazirla` skill'i plan kapanışında arşivleme görevi üretmiyor; kural yalnız
  `gorevler/README.md`'de yazılı (G029 notu)

## Kullanıcı kararı bekleyenler (otomasyona GİRMEZ — ssh/deploy/veri kararı ister)

- 0.5 ofis no kategori rejimi: X1 = 1.658 kayıt → dokunma / retag / eşleme tablosu (ADR şart)
- 0.6 prod export + hukukbot sağlık denetimi (ssh)
- A.2 gerçek müvekkil verisinin OneDrive senkronundan çıkarılması (140 MB SQLite + 139 MB PDF)
- service_type backfill (reçete canlı veride çürüdü, ayrı keşif gerekiyor)
- pip/npm yükseltmeleri (G022 ADR'si hazır; uygulama onayı kullanıcıda)
- Çıkış ağı denetimi: G024'ten sonra **zorunlu değil** (SSRF ağ katmanında kapandı);
  yalnız derinlik savunması olarak değerlendirilebilir

## Kapanmış plan: Denetim bulguları (2026-08-11 bağımsız denetim; deploy kararı kullanıcıda)

<!-- Kaynak: 6-ajanlı bağımsız denetim (2026-08-11 sohbet raporu). G009 davranışsız
     (diff yalnız yorum/docstring/md). G012→G011 zinciri test_faz3_e_hardening.py ortaklığı
     ihtimalinden ("şüphede zincirle").
     KAPANIŞ (2026-08-11 akşam): 5/5 tamam; beşi de ayrı temiz-context denetçiyle
     denetlendi, 5/5 GECTI (G013 dirijan devriyle — izin kapısı, ders: bash -n
     allowlist'e eklendi 04c9789). Kapılar nihai HEAD'de: 868+2 / ruff / mypy temiz.
     Prod'a YANSIMADI — deploy kararı kullanıcıda. -->

- [x] G009 | bant:backend | bagimli:- | Denetim: bayat yol referansları + docstring/şerh düzeltmeleri (davranışsız)
- [x] G010 | bant:backend | bagimli:- | Denetim: analyzer nihai hataları failed olayına bağla (pdf_page_limit)
- [x] G011 | bant:backend | bagimli:- | Denetim: outbox 'uploaded' + belge URL yazımı atomik/self-heal
- [x] G012 | bant:backend | bagimli:G011 | Denetim: lider kilidi fallback yolu + CRITICAL alarm
- [x] G013 | bant:docs | bagimli:- | Denetim: backup_db.sh trap temizliği + deploy/rollback sessiz çıkış
