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

- [ ] G014 | bant:backend | bagimli:- | 0.2+0.4-be: hata yutan kapılar (find_duplicate_cases + client-sequence)
- [ ] G015 | bant:backend | bagimli:- | 0.1: .eml gövdesinde SSRF — uzak kaynak taşıyan attribute'ları sök
- [ ] G016 | bant:backend | bagimli:- | 0.8: /api/documents bağlantısız belgelerde tenant izolasyonu yok
- [ ] G017 | bant:backend | bagimli:- | A.4: tanıdık sorgu aday indeksi TTL cache + normalizasyon memoize
- [ ] G018 | bant:backend | bagimli:- | A.1+A.3+0.7: gzip, eksik preview proxy'si, init:true, backend/.dockerignore
- [ ] G019 | bant:frontend | bagimli:G014 | 0.2+0.3-fe: checkDuplicateCase + useConfig hata yutması
- [ ] G020 | bant:frontend | bagimli:G019 | service_type kayıt yüküne eklensin + as CaseData cast'i kalksın
- [ ] G021 | bant:frontend | bagimli:- | A.5: ölü npm bağımlılıkları (docx/mammoth/file-saver/get-port)
- [ ] G022 | bant:docs | bagimli:- | A.5+A.6: bağımlılık + runtime yaşlanma ADR'si (yükseltme YAPMAZ)

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
