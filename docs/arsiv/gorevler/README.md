# docs/arsiv/gorevler — kapanmış görev dosyaları

> **TARİHSELDİR — GÜNCEL BİLGİ KAYNAĞI DEĞİLDİR.** Üst klasörün şerhi
> ([`docs/arsiv/README.md`](../README.md)) burada da aynen geçerlidir: bu dosyalar
> yazıldıkları gecenin fotoğrafıdır. İçlerindeki "şu an şöyle çalışıyor", "şu dosyada
> şu satır var", "test sayısı N" ifadeleri o gün doğruydu; bugün yanlış olabilir.
> Bir iddiayı buradan alıp güncel kabul etme — **koddan doğrula.**

## Bunlar ne

`gorevler/` gece kuyruğu sisteminin kapanmış görev dosyaları. Her dosya bir oturumluk
işin tanımı (hedef, kabul kriterleri, dosya kapsamı, doğrulama) **ve** o oturumun
kendi yazdığı Rapor bölümüdür: alınan kararlar, gerekçeleri, ölçüm tabloları,
reddedilen yaklaşımlar, izlenecekler.

Neden saklanıyor: rapor bölümleri gerçek kurumsal kayıttır. Bir kararın *neden* öyle
verildiğini (örn. G015'in denetimde RET edilip G023'e devredilmesi, G022'nin
"yükseltme yapma, ADR yaz" hükmü) yalnız buradan öğrenebilirsin. Neden arşivde:
`gorevler/gorev/` çalışma dizinidir, yalnız **açık** işleri göstermelidir.

Kuyruk kaydının kendisi (`gorevler/KUYRUK.md`) taşınmaz — kısa satırlardır ve sürecin
izidir; hangi görevin hangi plana ait olduğunu oradan okursun.

## İçindekiler

Kapanış tarihi = dosyaya dokunan son commit'in tarihi.

### Sertleştirme kalanı — FAZ 4/5 (kapanış: 2026-08-11)

| Dosya | Bant | Konu |
| --- | --- | --- |
| [G001](G001.md) | backend | Analiz akışına "failed" terminal olayı (4-B-be) |
| [G002](G002.md) | frontend | Hata ≠ boş veri + "failed" olayının işlenmesi (4-B-fe) |
| [G003](G003.md) | backend | HTTP durum kodu disiplini + /process Pydantic şeması (5-B) |
| [G004](G004.md) | frontend | Taslak kalıcılığı + beforeunload + logout daraltma (4-C) |
| [G005](G005.md) | backend | Takip dosyası senkronizasyonu + deploy hazır notu |

### FAZ 6 — AI-dostu repo (kapanış: 2026-08-11)

| Dosya | Bant | Konu |
| --- | --- | --- |
| [G006](G006.md) | backend | CLAUDE.md + docs/ reorganizasyonu (arşiv şerhi) |
| [G007](G007.md) | backend | docs/mimari içerikleri + ADR'ler (koddan türetilmiş) |
| [G008](G008.md) | backend | Modül docstring'leri + proje skill'leri + plan kapanışı |

### Bağımsız denetim bulguları (kapanış: 2026-08-11)

| Dosya | Bant | Konu |
| --- | --- | --- |
| [G009](G009.md) | backend | Bayat yol referansları + docstring/şerh düzeltmeleri (davranışsız) |
| [G010](G010.md) | backend | Analyzer nihai hataları failed olayına bağla (pdf_page_limit) |
| [G011](G011.md) | backend | Outbox 'uploaded' + belge URL yazımı atomik/self-heal |
| [G012](G012.md) | backend | Lider kilidi fallback yolu + CRITICAL alarm |
| [G013](G013.md) | docs | backup_db.sh trap temizliği + deploy/rollback sessiz çıkış |

### Temizlik planı — FAZ 0 + FAZ A (kapanış: 2026-08-11)

| Dosya | Bant | Konu |
| --- | --- | --- |
| [G014](G014.md) | backend | Hata yutan kapılar: mükerrer dava + ofis no sıra tahsisi |
| [G015](G015.md) | backend | .eml SSRF ilk denemesi — **denetimde RET**, G023 devraldı |
| [G016](G016.md) | backend | /api/documents: bağlantısız belgelerde tenant izolasyonu |
| [G017](G017.md) | backend | Tanıdık sorgu aday indeksi TTL cache + normalizasyon memoize |
| [G018](G018.md) | backend | gzip, eksik preview proxy'si, init:true, backend/.dockerignore |
| [G019](G019.md) | frontend | Hata ≠ boş veri: checkDuplicateCase + useConfig |
| [G020](G020.md) | frontend | service_type kayıt yüküne eklendi, `as CaseData` cast'i kalktı |
| [G021](G021.md) | frontend | Ölü npm bağımlılıkları (docx/mammoth/file-saver/get-port) |
| [G022](G022.md) | docs | Bağımlılık + runtime yaşlanma ADR'si (yükseltme YAPMAZ) |

### SSRF kapatma (kapanış: G023 2026-08-11, G024–G025 2026-08-12)

| Dosya | Bant | Konu |
| --- | --- | --- |
| [G023](G023.md) | backend | .eml gövde temizliğini tokenizer'a taşı (G015'in RET'ini kapatır) |
| [G024](G024.md) | backend | Ofis dosyalarında SSRF: harici bağlı görsel temizliksiz soffice'e gidiyor |
| [G025](G025.md) | backend | G023 gerilemesi: `&lt;` ile başlayan gövde metni sessizce yok oluyordu |

## Bilinen tuzak: dosya içindeki yol yazımları

Bu dosyalar `gorevler/gorev/` altındayken yazıldı; içlerinde `gorevler/gorev/G0NN.md`
biçimli **düz metin** atıflar var (markdown link değil — taşınmadan önce de link yoktu,
taşımayla kırılan bir bağlantı oluşmadı). Tarihsel içerik bilerek yeniden yazılmadı:
o atıfları `docs/arsiv/gorevler/G0NN.md` diye oku.
