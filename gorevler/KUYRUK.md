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

## Aktif plan: FAZ B — emniyet ağı (2026-08-12; deploy GEREKTİRMEZ)

<!-- Kaynak: docs/plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md §4 (B.1-B.6).
     Bu faz kullanıcıya doğrudan bir şey vermez; D/E/F'nin ön koşuludur.
     G031 (B.4) fazın çıpası: FAZ D 6.1'in kapısı. G032 (B.5) FAZ E'nin kapısı.
     KUYRUĞA GİRMEYEN: main'e branch protection (GitHub ayarı — kullanıcı işi,
     ci.yml:4-5 zaten manuel adım olduğunu yazıyor); frontend sayfa karakterizasyon
     testleri (plan §9 — tek müşterisi kapsam dışı bırakılan dosya bölme).
     PLANDA OLMAYAN İKİ EK (G036+G037): sahte tsc kapısı FAZ C'de keşfedildi, plan
     yazıldığında bilinmiyordu; "CI 5/5 yeşil" iddiasının beşte biri boş bir kapı —
     emniyet ağı faziyle aynı sınıf, bu yüzden buraya alındı.
     Bant: G036 frontend (tek gerçek paralel dilim), kalanı backend = seri.
     Zincir yalnız GERÇEK dosya çakışmasında kuruldu (pyproject.toml, ci.yml) —
     tek uzun zincir bir BLOKE'de tüm geceyi yakardı. -->

- [x] G030 | bant:backend | bagimli:- | B.1: pytest-cov + CI kapsam kapısı
- [x] G031 | bant:backend | bagimli:G030 | B.4: migrasyon yolu testi (gerçek Postgres) — FAZ D'nin kapısı
- [x] G032 | bant:backend | bagimli:- | B.5: X-Total-Count / sayfalama karakterizasyonu — FAZ E'nin kapısı
- [x] G033 | bant:backend | bagimli:- | B.3-1: "DB hatası → kapı KAPALI" karakterizasyonu (FAZ 0.2/0.3/0.4 kilidi)
- [x] G034 | bant:backend | bagimli:G033 | B.3-2: tenant + soft-delete ORM semantiği karakterizasyonu
- [x] G035 | bant:backend | bagimli:G031 | B.6: mypy kapsamı services/ (ölçüldü: 25 hata / 6 dosya)
- [x] G036 | bant:frontend | bagimli:- | Main'de canlı 4 tip hatası (sahte tsc kapısının borcu)
- [x] G037 | bant:backend | bagimli:G030,G036 | CI'daki sahte tsc kapısını gerçeğe çevir
- [x] G038 | bant:backend | bagimli:G030 | B.2: deploy.sh test kapısı (RİSKLİ — izin açıldı, --gate-only ZORUNLU)
- [x] G039 | bant:docs | bagimli:- | 12.08 kararlarını ADR'ye yaz (UYAP · kanonik yazım · K1 kodu · ES/Redis reddi)
- [x] G040 | bant:docs | bagimli:G039 | FAZ C görev dosyalarını arşivle (G026-G029)

## Aktif plan: FAZ D — veritabanı + FAZ F şeması (2026-08-12; sonunda DEPLOY #10)

<!-- Kaynak: temizlik planı §6 + faz-f-aktarim-gereksinimleri-2026-08-12.md §1.
     ÖN KOŞUL KARŞILANDI (2026-08-12, prod'da salt-okunur ölçüldü): case_relations ve
     daily_activity_reports üzerinde 0 mükerrer → iki UNIQUE de risksiz eklenebilir.
     case_relations'ta prod'da yalnız 1 satır var — FAZ F oraya 510 TKU grubu yazacak,
     yani UNIQUE'i eklemek için SON KOLAY AN.
     G041 fazın çıpası: mekanizma tamir edilmeden G044/G045'in kısıtları da doğmaz.
     G045 ve G046 aynı tuzağa düşmemeli — kısıt/index DAİMA ("index", ...) op'una.
     E'DEN TAŞINANLAR: E7 (avukat filtresi, D'nin index'ini bekliyordu) → G043,
     E6 (missing_required denormalize, şema işi) → G046. Plan §7 envanteri güncel kalır.
     G047 planda yoktu: G038'in kapısı migrasyon testlerini KOŞMUYOR (ölçüldü, 6 test
     sessizce SKIP) — D tamamen migrasyon işi olduğu için D deploy'undan ÖNCE kapanmalı.
     KUYRUĞA GİRMEYEN: index düşürme listesinin prod'da uygulanması (deploy kararı),
     FAZ F veri dolumu (ayrı faz), 220 mahsur export kaydı (2026-08-12'de pending'e
     çevrildi, kullanıcı işi bitti).
     Bant: G048 frontend (tek paralel dilim), kalanı backend = seri. -->

- [x] G041 | bant:backend | bagimli:- | D 6.1: eksik kısıt/index'leri çalışan op türüne taşı (8 kalem, prod'da doğrulandı)
- [x] G042 | bant:backend | bagimli:G041 | D 6.2-a: kullanılmayan index temizliği (52 aday / 31 MB — unique/primary ZORUNLU dışlanır)
- [x] G043 | bant:backend | bagimli:G042 | D 6.2-b: eksik FK/kısmi/fonksiyonel index'ler + E7 avukat filtresi
- [x] G044 | bant:backend | bagimli:G041 | Şema: FAZ F'nin 11 yeni kolonu + Uzmanlık Alanı adlandırması
- [x] G045 | bant:backend | bagimli:G044 | case_esas_numbers: esas tarihçesi (denetim RET — G049 DEVRALDI, satır kapatıldı)
- [x] G046 | bant:backend | bagimli:G044 | E6: missing_required denormalize + D2/D8 bağlamsal zorunluluk kapısı
- [x] G047 | bant:backend | bagimli:- | Deploy kapısı migrasyon testlerini koşmuyor (süreç dışarıdan öldü — G050 DEVRALDI)
- [x] G048 | bant:frontend | bagimli:G044 | Frontend: Uzmanlık Alanı + 11 yeni alanın arayüz karşılığı

## Aktif plan: FAZ E — sorgu algoritmaları + FAZ D devirleri (2026-08-12; DEPLOY #10 bunun sonunda)

<!-- Kaynak: temizlik planı §7 + §12 FAZ E madde envanteri. E6 ve E7 FAZ D'de bitti
     (G046, G043) — kalan altı madde burada, plan §7'nin RİSK SIRASINDA: ucuz olanlar
     önce, UNION (E8) en sonda ve kendi doğrulama kapısıyla.
     İKİ DEVİR FAZ D'DEN: G049 = G045'in denetim RET'i (main'de CANLI 500 — backend bandı
     doğrudan main'e yazar, RET commit'i geri almaz; G046 onun üstüne kuruldu). G050 =
     G047 (süreç dışarıdan öldürüldü, log'lar boş, commit yok — temiz yeniden deneme).
     G049 KUYRUĞUN İLKİ: main'deki canlı hata, ve G055 aynı arama koduna dokunacak.
     ÖLÇÜM GÜNCELLENDİ: deploy kapısında 6 değil **28** test sessizce atlanıyor
     (1156+31 vs konteynerde 1184+3) — FAZ D'nin DB'li testleri de aynı deliğe düştü.
     E8 UYARISI: kazanç ölçüldü ve KÜÇÜK (tek terim ≥3 karakter 4,0×; tipik 2 karakterlik
     aramada 1,27×). Riski kazancından büyük olabilir; görev dosyasında açık DURMA İZNİ var.
     Ayrıca G045 arama koluna esas tarihçesini ekledi — E8'in kapsamı planda yazandan geniş.
     KUYRUĞA GİRMEYEN: party_check SQL göçü (G017'nin durma kriteri düşürdü, plan §7),
     FAZ F veri dolumu, index düşürme listesinin prod'da uygulanması (deploy kararı).
     Bant: G056 docs (E8'den SONRA — erken koşarsa yazdığı çıpalar sabaha bayat olur),
     kalanı backend = seri. Bu kuyrukta gerçek paralellik YOK. -->

- [ ] G049 | bant:backend | bagimli:- | G045 RET: sync_current_esas geri dönüşte UniqueViolation + yalancı yeşil test
- [ ] G050 | bant:backend | bagimli:- | Deploy kapısı kendi postgres'ini kaldırmalı (28 test sessizce atlanıyor)
- [ ] G051 | bant:backend | bagimli:G049 | E1+E3: dava kartı selectinload + arama count()'unun atılması
- [ ] G052 | bant:backend | bagimli:- | E2: intake mahkeme sözlüğü TTL cache (mekanizma hazır)
- [ ] G053 | bant:backend | bagimli:- | E4: bantlı/erken çıkışlı Levenshtein (maliyetin %69'u)
- [ ] G054 | bant:backend | bagimli:- | E5: find_matching_case SQL daraltma (tepe bellek 244 MB)
- [ ] G055 | bant:backend | bagimli:G051,G049 | E8: dava araması UNION + çok terimli INTERSECT-of-UNION (RİSKLİ — durma izni var)
- [ ] G056 | bant:docs | bagimli:G055 | Yaşayan dokümanlardaki bayat satır çıpalarını süpür (FAZ D+E borcu)

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
- **B.2'nin ikinci yarısı: main dalına branch protection** (GitHub Settings → Branches →
  Require status checks: backend, frontend). `ci.yml:4-5` bunun manuel adım olduğunu
  zaten yazıyor; otomasyon GitHub ayarı değiştiremez
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
