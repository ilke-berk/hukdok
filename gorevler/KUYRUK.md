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
