# İş kuyruğu

Format: `- [ ] Gxxx | bant:backend|frontend|docs | bagimli:-|Gyyy,Gzzz | Kısa başlık`
Ayrıntılar ve kurallar: [README.md](README.md). Görev tanımları: `gorev/<id>.md`.

## ÖNCELİK 1 — Belgeleme olayı alanları (2026-09-02, kullanıcı kararı)

<!-- Kaynak: veri ekibinin HUKDOK_BELGELEME_OLAYI_BULGUSU_2026-08-25.md ölçümü (3.946
     belge tarandı, 302 isabet elle okundu: bağlı föylerin ~%14'ü belgeleme olayı taşıyor;
     45 dosyada "kusur yok ama tazminat var" görünümü). Kullanıcı 02.09'da iki alanın
     açılmasına karar verdi: cases.olay_turu + cases.hukumdeki_rol, ikisi de kapalı liste.
     KARARLAR: (1) listeler SEED'Lİ doğar (alleged_faults'un aksine karşı taraf teyidi
     GEREKMİYOR — değerleri 25.08 belgesi öneriyor, biz sabitledik); (2) olay_turu'na
     üçüncü değer KARMA ("Tıbbi + Belgeleme") — kart alanı tek slot, karma dosya tahminle
     tekilleştirilmez; (3) hukumdeki_rol TEK SLOT + güncel kademe kuralı — aşama bazlı rol
     TARİHÇESİ bilinçli ertelendi (ihtiyaç doğunca stage_decisions desenine taşınır);
     (4) alanlar hiçbir bağlamda ZORUNLU DEĞİL, boş = "karar okunmadı"; (5) rozet koşulu
     NULL≠0 kuralına bağlı (hukmedilen_maddi === 0, null değil).
     SÖZLEŞME G103 + G105 dosyalarında DONDURULDU (G001/G002 deseni) → G105 frontend
     bandında PARALEL koşabilir; dosya kesişimi yok. G104 aynı bant + G103'ün şemasını
     kullanıyor → zincirli.
     KUYRUĞA GİRMEYENLER: olay kaydı tablosunun kendisi (olay_id/TKU olay katmanı — FAZ F
     tasarım turu, ayrı plan); Gemini'nin karar metninden olay türü/rol ÖNERMESİ (tahmin
     yasağı — önce aktarım verisiyle isabet ölçülür, kullanıcı kararı); alleged_faults'a
     31.08 notundaki 9 değerin seed'lenmesi (karşı tarafın "kapalı liste" teyidi yazılı
     ama kullanıcı onayı alınmadı — gündüz işi); veri ekibine gidecek cevap yazısı
     (kullanıcı/gündüz işi). -->

- [x] G103 | bant:backend | bagimli:- | Belgeleme olayı alanları: iki kolon + iki kapalı liste (seed'li) + yazma/okuma yolu + olay_turu filtresi
- [x] G104 | bant:backend | bagimli:G103 | Aktarım eşlemesi: Olay Türü + Hükümdeki Rol sütunları teslimden kartlara (toleranslı başlık)
- [x] G105 | bant:frontend | bagimli:- | Kart UI: iki kapalı liste alanı + "belgeleme olayı olabilir" rozeti (NULL≠0) + liste filtresi
- [ ] G106 | bant:frontend | bagimli:- | Takip paneline Olay Türü + Hükümdeki Rol yazma arayüzü (02.09b BLOKE çözüldü: G073 kilidine tam-liste istisnası görev tanımına yazıldı; worktree'de hazır uygulama var)

## Tek görev: Otomatik ilişki katmanı ekrana bağlanır (2026-08-25, kullanıcı kararı)

<!-- Kaynak: 2026-08-25 migrasyon demosu hazırlığı. Kullanıcı Gökçınar kartında (14142)
     bağlantılı davaların görünmediğini bildirdi; teşhis: backend automatic listesi DOLU
     (servis 14142 için 4 ilişki üretiyor, TKU-788 → 14139/14140/14141/14143), ama
     RelatedCasesPanel (4e3eec4, 20.08) hiçbir sayfaya monte edilmemiş — commit yalnız
     bileşen + testine dokunmuş. CaseDetails yalnız result.manual çiziyor ve elle bağ
     0 satır (aktarım bilinçli ilişki YAZMAZ, okurken hesaplanır). Kullanıcı A (header
     çiplerine automatic'i katmak) yerine B'yi seçti: tasarlanan panel monte edilir,
     manual-only ikiz kod sökülür (tek yazar panel olur). Saf frontend; backend işi YOK.
     Tasarım kararı görev dosyasında: panel header kartı ile Tabs arasına her zaman
     görünür bölüm olarak, sekme içine DEĞİL; header'daki eski inline çip bölümü kalkar.
     İnsan adımı (KAPSAMADIĞI doğrulama): frontend imaj rebuild + girişli tarayıcı turu
     (14142'de 4 ilişki, 13364'te İcra+Tüketici paralelleri, 4442'de Bölge İdare bağı). -->

- [x] G102 | bant:frontend | bagimli:- | RelatedCasesPanel CaseDetails'e monte edilir; manual-only çip kodu sökülür

## ÖNCELİK 1 — Kimlik/token sertleştirmesi (2026-08-22, kullanıcı isteği)

<!-- Kaynak: 2026-08-22 token güvenliği analizi (bu oturum; kalıcı özeti G094'ün
     yazacağı docs/mimari/kimlik-ve-token.md olacak). Analiz koddan doğrulandı:
     MSAL Browser v5 + PKCE, sessionStorage, api:// scope'lu access token, backend
     stateless JWT doğrulaması. Sekiz bulgudan ÜÇÜ gözetimsiz koşulabilir.

     ÜÇÜ NEDEN GÖZETİMSİZ KOŞAMIYOR (bilinçli kuyruk DIŞI, kullanıcı adımı bekliyor):
     - CSP zorlayıcıya geçiş (O2): G091'in kendi notu bunu ayrı göreve bıraktı —
       ön koşul, tarayıcı turuyla toplanan ihlal listesi. Gece oturumu tarayıcı açamaz.
     - scp zorunluluğu + audience daraltma (O4 faz 2): Azure AD'nin gerçekte hangi
       aud/scp bastığı app registration ayarına bağlı, repodan bilinemez. G092 gözlem
       WARNING'lerini basacak; faz 2 O ÇIKTIYA bakan ayrı görev.
     - Token iptali gecikmesi / CAE (O1): mimari karar, kullanıcı onayı gerekir.

     SIRA: G092 ve G093 backend bandı (zaten seri). G094 docs bandıdır ama İKİSİNİ
     DE bekler — doküman son hale karşı yazılmazsa yazıldığı gece bayatlar.
     G095 frontend bandıdır ve hiçbirine bağlı değil: backend bandıyla PARALEL
     koşabilir (tek paralellik fırsatı bu). Dosya kesişimi yok — G092/G093 backend/**,
     G095 yalnız frontend/src/lib/api.ts + hooks/useIdleTimeout.ts.

     G095 KAYNAĞI: 2026-08-22 süre/çakışma incelemesi. Token ömürleri arasında
     kullanıcıya hata olarak yansıyan çakışma BULUNMADI (access token bitişini MSAL'in
     300 sn yenileme payı + api.ts'in 401-tekrar katmanı yutuyor; PROCESS_CACHE 30 dk
     dolsa bile /confirm dosya fallback'ine düşüyor). Çıkan iki kusur kozmetik/israf
     düzeyinde ve G095'te toplandı.

     G092 DEPLOY ÖNCESİ İNSAN TURU İSTER: iss zorlaması gerçek Azure AD token'ına
     karşı hiç denenmemiş olur (testler sentetik claim'lerle koşuyor). Lokal gerçek
     giriş turu görev dosyasındaki "KAPSAMADIĞI doğrulama" başlığında. -->

- [x] G092 | bant:backend | bagimli:- | Token doğrulama: issuer kontrolü + scp/aud gözlem modu
- [x] G093 | bant:backend | bagimli:- | Konfigürasyon uyarıları: DEV_MODE prod guard + SharePoint secret expiry
- [x] G094 | bant:docs | bagimli:G092,G093,G095 | Kimlik ve token mimarisi dokümanı
- [x] G095 | bant:frontend | bagimli:- | Oturum kapanış yolu: #/login artığı + boşa giden 401 turu
- [x] G096 | bant:backend | bagimli:- | Token doğrulama faz 2: scp zorunlu + audience yalnız api:// (G092 ölçümü 2026-08-22: 0 sapma)

## ÖNCELİK 1 — Bildirim sistemi denetim bulguları (2026-08-22, kullanıcı isteği)

<!-- Kaynak: 2026-08-22 bildirim sistemi incelemesi (canlı UI + DB + bağımsız kod
     denetimi ajanı). Sistem sağlam: dedupe UNIQUE koşulsuz index'te, lider kilidi
     canlıda teyitli (pid 10 kurdu / pid 11 atladı), IDOR+allowlist+saat dilimi testli,
     mail yolları git diff ile DOKUNULMAMIŞ. İki "orta" + dört "düşük" bulgu:
     G097 (backend): boot telafisi (misfire'da gün kaçıyor, T-1 hiç üretilmiyor) +
       retention (tablo sınırsız büyür, dismissed_at yazan yok) + bugun_tr/duruşma
       üst sınır testleri. Okunmamış satır ASLA silinmez.
     G098 (frontend): loadList updater içinde (canlıda mükerrer ÖLÇÜLMEDİ, hijyen) +
       markRead sessiz hata + 401/null testi.
     Bilinçli DIŞARIDA: idari uçların herkese açıklığı (20.08 kullanıcı kararı),
     dismissed_at'i yazan uç (ayrı tasarım), dedupe anahtarı sapması (gerekçeli+testli).
     Paralellik: G097 backend, G098 frontend — dosya kesişimi yok, paralel. G096 ile
     G097 aynı bant (seri), farklı dosyalar. -->

- [x] G097 | bant:backend | bagimli:- | Bildirim tarayıcısı: boot telafisi + retention + tz/duruşma sınırı testleri
- [x] G098 | bant:frontend | bagimli:- | Zil paneli hijyeni: updater yan etkisi + markRead geri bildirimi + 401 testi

## Tek görev: cache_manager makedirs yarışı (2026-08-22, kullanıcı isteği)

<!-- 22.08 gece koşularında iki açılışta da görüldü: 2 worker aynı anda
     ensure_cache_dir → biri EEXIST ile sahte ERROR. Log sözleşmesi + GCP ERROR
     alarmı + "açılış 0 ERROR" deploy kapısını kirletiyor. Tek satır: exist_ok=True. -->

- [x] G099 | bant:backend | bagimli:- | cache_manager: makedirs yarışı sahte ERROR basıyor (exist_ok=True)

## ÖNCELİK 1 — CSP zorlayıcıya geçiş (2026-08-22, kullanıcı isteği)

<!-- Kaynak: 2026-08-22 CSP ihlal turu (lokal 8080, Report-Only, SSO girişli
     tarayıcı turu: login/pano/upload/cases/clients/activity/admin/tema/zil).
     script/style/font/img/frame: 0 ihlal. connect-src 32 ihlal = lokal .env
     VITE_API_URL artefaktı (prod aynı origin, oluşmaz). Kod okumasıyla iki
     enforce kırıcı: yazdırma popup'larında inline onload/<script>
     (DashboardCalendar.tsx:203, YetkiBelgesiModal.tsx:226) — kontrol deneyi ana
     dokümanda script-src-attr/elem report'u verdi. Popup mirası lokal panelde
     doğrulanamadı (popup engelleyici); G100 belirsizliği kökten kaldırır.
     Sıra: G100 frontend → G101 docs (nginx.conf tek satır + doküman). G101
     DEPLOY GEREKTİRİR ve deploy sonrası insan turu ister (yazdır popup'ları,
     PDF aç, belge yükle); geri dönüş başlık adına -Report-Only eki. -->

- [x] G100 | bant:frontend | bagimli:- | Yazdırma popup'larında inline script/handler kaldırılır (CSP enforce ön koşulu)
- [x] G101 | bant:docs | bagimli:G100 | CSP zorlayıcıya geçer: -Report-Only eki düşer

## ÖNCELİK 1 — Güvenlik denetimi düzeltmeleri (2026-08-22, kullanıcı isteği)

<!-- Kaynak: docs/arsiv/saldiri-yuzeyi-guvenlik-denetimi-2026-08-22.md (§2 bulgular,
     §5 düzeltme planı). Denetim 7864baf (prod) → 3a5801c arası 51 commit'i taradı:
     HTTP yüzeyi 140 → 146 uç (+8 yeni / -2 kaldırılan), yeni uçların hepsi auth+tenant
     kapılı, uygulama kodunda yeni kritik açık YOK. Prod bağımlılıkları pip-audit ile
     temiz. Düzeltme gerektiren dört kalem burada.

     ÖLÇÜMLE BELİRLENEN İKİ NOKTA (tahmin değil, kurup denetleyerek):
     1. Vite 5.x hattına yama GELMEDİ — 5.4.21 (hattın sonu) hâlâ 1 high + 1 moderate.
        İlk temiz sürüm 6.4.3. npm'in önerdiği 8.2.2 lovable-tagger peer'ini
        (vite >=5.0.0 <8.0.0) kırar → hedef 6.4.3.
     2. frontend/src/lib/documentUtils.ts ÖLÜ (hiçbir yerden import edilmiyor) ama
        cdnjs'ten SRI'sız script enjekte ediyor → silinir, CSP'yi de sadeleştirir.

     Sıra: G088 ve G090 frontend bandı (aynı bant, seri; farklı dosyalar, zincir yok).
     G089 ana dizinde koşar (npm paketi — worktree'de kalıcı olmaz) ve G088'i bekler
     (ikisi de vite.config.ts'e dokunabilir). G091 G090'ı bekler.
     G089 ve G091 DEPLOY GEREKTİRİR; 19.08 direktifi gereği önce LOKALDE doğrulanır.

     GÖZETİMSİZ KOŞUDAN BİLİNÇLİ OLARAK ÇIKARILAN İKİ DOĞRULAMA (2026-08-22 kararı):
     - G089 tarayıcı duman testi: major sürüm geçişinin riski derleme değil çalışma
       zamanıdır; gece oturumu tarayıcı açamaz. Kapılar yeşil olsa bile deploy öncesi
       insan turu ŞART (görev dosyasında "KAPSAMADIĞI doğrulama" başlığı).
     - G091 `docker compose build/up`: docs bandı worktree'de koşar; ana stack'i
       ilgisiz bir işin yan etkisi olarak yeniden kurmak kabul edilmez. Görev yalnız
       tek seferlik konteynerle `nginx -t` yapar; başlığın canlı doğrulaması insana kalır. -->

- [x] G088 | bant:frontend | bagimli:- | Vite dev sunucusu 127.0.0.1'e bağlanır (LAN vektörü)
- [x] G090 | bant:frontend | bagimli:- | Ölü pdf.js CDN yükleyicisi silinir (SRI'sız üçüncü taraf script)
- [x] G089 | bant:backend | bagimli:G088 | Vite 5.4.19 → 6.4.3; CI dev-zincir kapısı bloklayıcıya döner
- [x] G091 | bant:docs | bagimli:G090 | CSP başlığı (Report-Only) konteyner nginx'ine eklenir

## ÖNCELİK 1 — Uygulama içi bildirim sistemi + pano placeholder'ları (2026-08-20, kullanıcı kararı)

<!-- Kullanıcı 2026-08-20'de "işlenen belgenin bildirimi sorumlu avukata gitsin, ayrıca
     yaklaşan tebliğ/dava bildirimleri olsun" dedi; aynı oturumda üç YAKINDA rozetli pano
     bölümünün de doldurulmasını istedi. Kararlar ve ölçümler (lokal prod-restore kopyası):

     KANAL: yalnız uygulama içi (zil). E-POSTA GÖNDERİMİ BUGÜNKÜ GİBİ KALIR — email_sender.py
     ve document_pipeline.py'nin mail yollarına DOKUNULMAZ (G082'de kabul kriteri).
     KAPSAM: yalnız Hanyaloğlu Acar. Alıcı allowlist'i NOTIFICATION_DOMAINS env'inden.
     KESİLENLER: arşiv/PDF-A hatası ve "müvekkil maili gitmedi" bildirimleri KAPSAM DIŞI.

     KİMLİK — yeni kolon GEREKMEDİ: lawyers.gorev='AVUKAT' olan 7 kişinin HEPSİ ofis mailli
     (@hanyaloglu-acar.av.tr); DIŞ AVUKAT 69 ve DİĞER 2 kaydın HİÇBİRİ ofis mailli değil.
     3 idari personel email_recipients'ta. Murat Arslan 294 davada sorumlu ama lawyers'ta YOK
     → ikinci kaynak şart. Kapsama ~%98,6; hedefsiz kalan 98 dava (Arşiv Dosya Yöneticisi 93,
     Asu Barış Karamık 4, AGH 1) idari panelde sayaçla görünür.
     [2026-08-24 duman turunda lokal restore kopyasında yeniden ölçüldü: sorumlusu yazılı
     7.093 davanın 98'i hedefsiz (kapsama %98,6 aynı). 20.08'de 97 yazılmıştı; üçüncü isim
     "AGH" (1 dava) o gün listede yoktu. G086/G087 görev raporlarındaki 97 rakamı
     20.08 fotoğrafıdır, bilerek DEĞİŞTİRİLMEDİ.]

     SÜRE VERİSİ: cases.karar_teblig_tarihi 0 DOLU — kaynak orası değil. Gerçek kaynak
     case_stage_decisions.teblig_tarihi (750 dolu, hepsi YEREL, en yeni 12.08, son 60 günde 23).
     Panel ilk gün bir avuç uyarı gösterecek; beklenti buna göre.

     G078 NOTU: eski GET /api/documents ucu G077 ile BİLİNÇLİ KALDIRILDI (83024b3) — DİRİLTİLMEZ.
     Pano akışı için amaca özel yeni uç yazılır, TEST/UNLINKED belge döndürmez.

     Sıra: G078 ve G080/G081/G084 backend bandı (seri). Frontend G079/G083/G086 paralel bant.
     Bu paket DEPLOY GEREKTİRİR; 19.08 direktifi gereği önce LOKALDE doğrulanır. -->

- [x] G078 | bant:backend | bagimli:- | Pano akışı için yeni uç: GET /api/documents/recent (+ mail durumu alanları)
- [x] G079 | bant:frontend | bagimli:G078 | Avukat panosu "Yeni İşlenen — son 24 saat" paneli + mail rozeti
- [x] G080 | bant:backend | bagimli:- | Bildirim hedefleme: dava → sorumlu avukatın ofis maili (allowlist, hedefsiz sayacı)
- [x] G081 | bant:backend | bagimli:- | notifications tablosu + yazma yolu (dedupe_key) + /api/notifications uçları
- [x] G082 | bant:backend | bagimli:G080,G081 | "Belge işlendi" bildirimi sorumlu avukata; mail yollarına dokunulmaz
- [x] G083 | bant:frontend | bagimli:G081 | Topbar zil paneli: dropdown + okunmamış rozeti + 60 sn polling
- [x] G084 | bant:backend | bagimli:- | legal_deadlines: kanuni süre motoru (adli tatil + tatil kaydırma, saf fonksiyon)
- [x] G085 | bant:backend | bagimli:G080,G081,G084 | Gece tarayıcı 06:00 TR: yaklaşan süre + duruşma bildirimleri (T-15/7/3/1)
- [x] G087 | bant:backend | bagimli:- | İdari bildirim görünümü uçları: dağılım (kime gitti/okundu) + hedefsiz sayacı
- [x] G086 | bant:frontend | bagimli:G087 | KALAN: "Süreli İşler" (idari) paneli — avukat yarısı eb89e02 ile main'de

## Tek görev: "Bağlantısız Belgeler" sayfasının kaldırılması (2026-08-20, kullanıcı kararı)

<!-- Sayfanın çözdüğü sorunu DANIŞ akışı çözdü: onay butonu dava bağlantısı yoksa
     QuickCaseModal'ı açıyor, bağlantısız onay yolu UI'da kalmadı. Lokal restore
     kopyasında da UNLINKED belge YOK (229 belgenin tamamı LINKED). Kullanıcı A+B
     (sayfa + ölü uçlar) birlikte dedi. DEPLOY GEREKTİRİR; deploy öncesi prod'da
     UNLINKED sayımı şart (görev dosyasındaki sorgu). -->

- [x] G077 | bant:frontend+backend | bagimli:- | Bağlantısız Belgeler sayfası + GET /api/documents + PATCH .../link kaldırılır

## Kapanmış öncelik — Aşama tarihçesi görünürlüğü + takip/kart ayrımı (2026-08-19, kullanıcı kararı)

<!-- Kullanıcı 2026-08-19'da "ilk önceliğimiz bu olsun" dedi. Kaynak: aynı gün yapılan
     HUKDOK tam aktarımı (3813ebe) `case_stage_decisions`e 4.971 satır yazdı — YEREL 3.098,
     İSTİNAF 1.236, TEMYİZ 574, K.Düzeltme 63 — ve tablonun NE ROUTE'U NE EKRANI var
     (G062 bilinçli olarak arayüzsüz bırakmıştı). Kullanıcı ayrıca takip/kart ayrımının
     yanlış yapıldığını söyledi; inceleme onu doğruladı, üç sapma ölçüldü (G073).
     DÖRDÜNCÜ sapma aynı gün kapandı: `istinaf_basvuran_taraf` kart eşlemesi ile aşama
     fotoğrafı arasında İKİ YAZICIYDI, ikinci koşuda 5 kart salınıyordu (3813ebe).
     Sıra: G072 ve G073 paralel (ikisi de backend bandı → seri koşar), G074 ikisini bekler.
     Bu paket DEPLOY GEREKTİRİR (backend route + frontend); deploy kararı kullanıcıda ve
     19.08 direktifi gereği ÖNCE LOKALDE doğrulanır. -->

- [x] G072 | bant:backend | bagimli:- | Aşama tarihçesi okuma yolu (route + şema); 4.971 satır bugün görünmüyor
- [x] G073 | bant:backend | bagimli:- | Takip/kart alan yerleşimi: arabuluculuk + arşiv tarihi takibe, dosya_son_durumu tek yere
- [x] G074 | bant:frontend | bagimli:G072,G073 | Takip panelinde aşama zaman çizgisi + kart gruplarının sadeleşmesi
- [x] G075 | bant:frontend | bagimli:G074 | Takip paneli 14.344 kartta kilitli: bilinmeyen aşama "gelinmemiş" sayılıyor
- [x] G076 | bant:backend | bagimli:G074 | Aktarımın iki açık kalemi: "havuz dışı durum: None" şerhi + arabuluculuk sütunu

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

- [x] G049 | bant:backend | bagimli:- | G045 RET: sync_current_esas geri dönüşte UniqueViolation + yalancı yeşil test
- [x] G050 | bant:backend | bagimli:- | Deploy kapısı kendi postgres'ini kaldırmalı (28 test sessizce atlanıyor)
- [x] G051 | bant:backend | bagimli:G049 | E1+E3: dava kartı selectinload + arama count()'unun atılması
- [x] G052 | bant:backend | bagimli:- | E2: intake mahkeme sözlüğü TTL cache (mekanizma hazır)
- [x] G053 | bant:backend | bagimli:- | E4: bantlı/erken çıkışlı Levenshtein (maliyetin %69'u)
- [x] G054 | bant:backend | bagimli:- | E5: find_matching_case SQL daraltma (işçi erişim kesilmesiyle düştü — dirijan devri; bağımsız denetim SONRADAN koşuldu: GECTI, 509 girdi / 0 fark)
- [x] G055 | bant:backend | bagimli:G051,G049 | E8: dava araması UNION + çok terimli INTERSECT-of-UNION (BLOKE hesap erişimiyle değil, ana oturumda çözüldü: yazmadan önce ölçüm koşuldu — kazanç index'siz de büyük çıktı, kullanıcı onayıyla index'ler geri eklenmedi; 20/20 gerçek sorgu eski koda eşdeğer, yol boyunca gerçek bir SQLAlchemy bug'ı bulunup kanıtlanmış kırmızıyla düzeltildi)
- [x] G056 | bant:docs | bagimli:G055 | Yaşayan dokümanlardaki bayat satır çıpalarını süpür (355 çıpa tarandı, 192 düzeltildi; CLAUDE.md test sayıları + FAZ D/E mimari notları güncellendi)

## Aktif plan: Kapsam boşlukları — korumasız kritik yollar (2026-08-13)

<!-- Kaynak: kapsam raporu (2026-08-13, konteynerde koşuldu): TOPLAM %64, 12.527
     ifadenin 4.517'si test edilmiyor. Bu üç görev "kapsamı yükseltmek" için DEĞİL,
     ölçülen üç somut riski kapatmak için var — kapsam kovalamak değersiz test üretir.
     G057 fazın çıpası: prod'da ölçüldü ki sır yolunun güvenliği docker-compose.yml:63'teki
     TEK bir env satırına yaslanıyor ve o satırın yorumu bile yok; düşerse keyring
     otomatik seçimle PlaintextKeyring'e (öncelik 0.5, kurulu backend'lerin en yükseği)
     düşer ve iki sırrı düz metin dosyaya yazar.
     G058 sadece kapsam değil, Deploy #10'un getirdiği CANLI kusuru da kapatıyor.
     KUYRUĞA GİRMEYEN (kullanıcı onayı bekler): yetki_belgesi_generator.py (%0, 116
     ifade, routes/documents.py'den canlı) ve report_builder.py (%0, 103 ifade,
     routes/cases.py takvim raporu) — ikisi de korumasız ama G057-G059 kadar keskin
     değil. reference_list_export.py (%0, 51) için ÖNCE getattr/dinamik-dispatch
     taraması gerekir: grep hiç çağıran bulamadı, ölü OLABİLİR ama projenin pazarlıksız
     kuralı taramasız ölü saymayı yasaklıyor. Büyük mutlak boşluklar (analyzer.py 281,
     routes/config.py 256, udf_converter.py 234 satır) bilinçli DIŞARIDA: oradaki
     dallanmayı kapsam uğruna test etmek değersiz test üretme riski taşır.
     Bant: üçü de backend = seri. Aralarında dosya çakışması YOK, bağımlılık yok. -->

- [x] G057 | bant:backend | bagimli:- | vault.py %0: sır yolu tek env satırına yaslanıyor (PlaintextKeyring riski)
- [x] G058 | bant:backend | bagimli:- | seed_data.py: worker yarışı (prod'da canlı ERROR) + %9 kapsam
- [x] G059 | bant:backend | bagimli:- | auth_verifier.py %25: kimlik kapısı test edilmiyor

## Aktif plan: Karar aşamaları düzeltmeleri — FAZ F ön hazırlık (2026-08-18)

<!-- Kaynak: KARAR_ASAMALARI_TASARIM_PAKETI_2026-08-17.xlsx (veri ekibinin çok-aşamalı
     karar tasarım görevi) + 18.08 oturum bulguları: bizim şemada da karar künyesi TEK SLOT
     (models.py:69-108) ve TÜM karar alanları prod kopyasında 0 dolu (temiz başlangıç,
     backfill yok). KULLANICI KARARLARI (18.08): (1) hedef model bizim sistem — dava TEK
     kart, çoklu müvekkil; kart föy bazında BÖLÜNMEZ (SistemNo'lar case_foys eşleme
     tablosunda yaşar); (2) işlenmiş belgeler KORUNUR — aktarım UPDATE-in-place, belge
     envanter denkliği kabul kriteri; (3) dropdown'lar resmi havuzlarla kurulsun — havuzlar
     10.08 paketinin DEGER_HAVUZLARI sayfasında bulundu (Yerel 28 · İstinaf 3 · Temyiz 3 ·
     KD 2), görev dosyasına gömüldü.
     ZİNCİR GEREKÇESİ: G060→G062→G063→G064 hepsi models.py+database.py hub'ına dokunur ve
     migration üretir → README kural 2 gereği zincirli; G061 tek paralel dilim (frontend).
     KUYRUĞA GİRMEYEN: FAZ F tam 68-sütun eşlemesi + D1-D7 davranış kuralları + 4 kabul
     raporu (final export + CEVAP xlsx bekliyor — ayrı plan turu); aşama zinciri UI görünümü
     (FAZ F sonrası); dağınık ~510 TKU grubunun birleştirme kararı (kullanıcı kararı bekler;
     öneri: ilk turda case_relations ile bağla); karar_turu 28→6 türetme eşlemesi (aktarım
     kuralları turunda). Bant: G061 frontend (paralel), kalanı backend = seri. -->

- [x] G060 | bant:backend | bagimli:- | Karar sonucu resmi listeleri (4 havuz) + yerel_karar_durumu kolonu + seed (ana oturumda koşuldu — CLI org engeli; bağımsız denetim GECTI; commit 5670b1e; NOT: get_case + takip whitelist'i alanı henüz tanımıyor → G061/G062 girdisi, G060.md raporunda)
- [x] G061 | bant:frontend | bagimli:G060 | Takip paneli karar dropdown'larını resmi listelere bağla
- [x] G062 | bant:backend | bagimli:G060 | case_stage_decisions: aşama/karar tarihçesi + BELİRSİZ damgası + son-aşama senkronu
- [x] G063 | bant:backend | bagimli:G062 | case_foys: SistemNo → kart+müvekkil föy eşleme tablosu
- [x] G064 | bant:backend | bagimli:G063 | Aktarım yazma yolu çekirdeği: idempotent iskelet + kuru koşu + belge envanter denkliği
- [x] G065 | bant:backend | bagimli:G060 | yerel_karar_durumu okuma/yazma yolu: get_case serialize + takip whitelist (G061 bulgusu; G062 ile dosya çakışması yok)

## Aktif plan: Kapalı havuz sınırı — 18.08 boşluk analizinin 3. maddesinin kalanı (2026-08-19)

<!-- Kaynak: KARAR_ASAMALARI_TASARIM_PAKETI_2026-08-17.xlsx "4 · Kapalı havuzlar" değişmezi +
     18.08'de teyit edilen 4 boşluk. Üçü bu gece kapandı: (1) tek slot → G062
     case_stage_decisions, (2) BELİRSİZ damgası → G062 dogrulama_durumu, (4) SistemNo
     tekilliği → G063 case_foys. 3. madde (karar durumu serbest String(100)) YARIM kaldı:
     G060 listeleri + G061 dropdown'ı + G065 yazma yolu geldi ama kapalılık YALNIZ ARAYÜZDE —
     manager katmanı doğrulamıyor (case_manager.py:371 yalnız yorum). Yeni tarihçe yolunda
     açık YOK (stage_decisions.py:170 doğruluyor); asimetri bu yüzden doğdu.
     Dört alan BİRLİKTE ele alınır — G065 raporunun şartı; tek alan sıkılaştırmak kardeş
     alanlar arasında yeni asimetri üretir.
     KUYRUĞA GİRMEYEN: şemayı sıkılaştırma (kolonlar String(100) kalır — değerler ada göre
     denormalize ve resmi liste panelden düzenlenebilir), backfill (alanlar 18.08 ölçümünde
     0 dolu), 4 listenin AdminPage yönetim sekmesi (G061 denetçisinin ayrı önerisi). -->

- [x] G066 | bant:backend | bagimli:- | Dört karar durumu alanında kapalı liste doğrulaması (takip yazma yolu; ana oturumda koşuldu; bağımsız denetim GECTI; commit 0e19afe — kapalılık artık manager katmanında, ret 400; NOT: liste BOŞSA doğrulama WARNING'le atlanır ve 400'ün detail'i arayüze ulaşmıyor, G066.md raporunda)

## Aktif plan: Mahkeme adı kimliği — okuma hatalarının kök nedeni (2026-08-19)

<!-- Tetikleyici: veri ekibinin 17.08 hata bildirimi (A: şehir bozulması 21 belge · E: daire
     basamak düşmesi 12 föy). Ekip TEKNİK DEĞİL — "ayrıştırıcıyı düzeltin" talebi bir çözüm
     reçetesi değil, semptom bildirimi. Tasarım bizim: adı serbest string üretmek yerine
     YAPISAL KİMLİĞE (yer · sıra · kanonik tür · daire) çevirip her bileşeni doğrulamak,
     doğrulanamayanı ÜRETMEMEK. İki mevcut ev desenimizin taşınmasıdır:
     case_intake.detect_conflicts (çelişki → hakem) ve stage_decisions.dogrulama_durumu
     (tahmin yasağı → BELİRSİZ damgası). Yeni sözlük yazılmaz: tür kanonikleştirmesi
     services/judicial_unit.PATTERNS'ten okunur.
     BU BİZİM DE SORUNUMUZ (2026-08-19 ölçümü, lokal prod kopyası): cases.court 2.163 tekil
     serbest string; 747 tekil (3.183 kayıt) değerin yeri il DEĞİL (Şişli/Bakırköy/Beyoğlu —
     ayrıştırıcı hiç kapsamıyor); kendi kartımızdaki "Tatvan 2. Asliye Hukuk" ayrıştırıcıya
     verildiğinde "VAN 2. ASLİYE HUKUK MAHKEMESİ" dönüyor (AGRI vakasıyla aynı sınıf).
     Bant seri, ikisi de backend; G068 G067'nin kapısını çağırır → zincirli.
     KUYRUĞA GİRMEYEN: (1) yargı yeri sözlüğünün panele taşınması (yeni tablo+migrasyon+
     AdminPage sekmesi — hub dosyalar, ayrı görev), (2) cases.court backfill'i (2.163 değerin
     kanonikleştirilmesi — gerçek müvekkil verisi, kullanıcı kararı), (3) analiz sonucu
     JSON'una güven alanı + UI rozeti (frontend bandı), (4) veri ekibinin 112 satırlık
     BELGE_KONTROLU okuması (xlsx elimizde yok — kullanıcı işi), (5) parti üreticisinin
     kendisi: 18.08 partisini üreten kod bu repoda DEĞİL (git + oturum kayıtlarında yok),
     yeri kullanıcıya soruldu. -->

- [x] G067 | bant:backend | bagimli:- | Mahkeme adı için yapısal kimlik kapısı (services/court_name.py: yer/tür doğrulaması + kelime sınırı + Yargıtay daire okuması)
- [x] G068 | bant:backend | bagimli:G067 | Analiz hattında mahkeme adı: güven kilidi + LLM çapraz kontrolü + BELİRSİZ

<!-- 2026-08-19 koşusu sonrası: G067 (cffc130) + G068 (a31cea6) GECTI, denetim 2/2 temiz,
     paket 1538+3. Bağımsız davranış doğrulaması (rapora güvenilmedi, probe yeniden koşuldu):
     YARGITAY 11. HD tek satırda korunuyor · MANAVGAT ve İSTANBUL ANADOLU artık okunuyor ·
     TATVAN→VAN ve BAĞRI→AĞRI bozulmaları BİTTİ (yer uydurulmuyor, boş kalıyor) · gerçek AĞRI
     hâlâ doğru. Kendi 2.163 kart değerimizde kapsam: TAM 1.983 · KISMİ 166 · YOK 14
     (koşu öncesi "yeri tanınmayan" 747 tekildi).
     Koşucunun bıraktığı 4 sorunun kararı (kullanıcı "sen karar ver" dedi, 2026-08-19):
     (1) judicial_unit üst mahkeme boşluğu → İŞ: G069. Ölçüldü, gerçek: "Yargıtay 11. Hukuk
         Dairesi" → BÖLGE ADLİYE MAH. HUKUK DAİRESİ, genel kurul → None. Bugün LATENT
         (Yargıtay taşıyan 0 kart; istinaf/temyiz mahkemesi kolonları 0 dolu) → düzeltmesi
         BEDAVA; FAZ F temyizi kartlara yazınca pahalı (G066'nın gerekçesiyle aynı sınıf).
     (2) yer sözlüğü → İŞ: G070, ama panele TAŞINMADAN: sözlük kullanıcı verisi değil
         ayrıştırıcı bilgisidir; panelde yanlış girdi belge okumasını sessizce bozar.
         Kapatma yöntemi ölçüm: kalan 166 KISMİ değer eksik yerleri isim isim söylüyor.
     (3) TAM güvende çapraz kontrol yapılmaması → KALICI KABUL, görev açılmadı. Regex TAM'ı
         yalnız başlıktan/hüküm cümlesinden ve yer+tür doğrulanmışken üretiyor; her belgede
         ikinci bir LLM okuması gecikme ve token maliyeti getirir, ölçülmüş bir kazancı yok.
         "Erişilemez dal" ÖLÜ KOD DEĞİL: kapı iki okumayla (ör. parti/aktarım yolu)
         çağrıldığında canlıdır, birim testiyle kilitli kalır.
     (4) Güven damgasının UI rozeti → ERTELENDİ, görev açılmadı. Tasarım gereği belirsiz
         değer YAZILMIYOR (alan boş geliyor) — kullanıcı onay ekranında zaten görüyor.
         Rozet ancak "dolu ama düşük güvenli" durum olsaydı bilgi taşırdı; o durum yok. -->

- [x] G069 | bant:backend | bagimli:- | judicial_unit üst mahkeme boşluğu: Yargıtay daireleri Bölge Adliye'ye yazılıyor (bugün latent, FAZ F'de pahalı)
- [x] G070 | bant:backend | bagimli:G069 | Yargı yeri sözlüğünü kendi verimizden kapat (166 KISMİ değer; panele taşınmaz — gerekçe yukarıda)

<!-- 2026-08-19b koşusu: G069 (6ce04e9) + G070 (8151d13) GECTI, paket 1601+3. Bağımsız
     doğrulama (rapora güvenilmedi, ölçüm kendi scriptimle tekrarlandı, sayılar birebir):
     Yargıtay 11. HD → YARGITAY HUKUK DAİRESİ (eskiden BÖLGE ADLİYE) · BAM vakaları
     değişmedi · kapsam TAM 1.983→2.039, KISMİ 166→110 tekil.
     G069'un BİLİNÇLİ SAPMASI KABUL EDİLDİ (2026-08-19): görev dosyası tek `YARGITAY`
     kanonik değeri önermişti, işçi `YARGITAY HUKUK DAİRESİ` + `YARGITAY CEZA DAİRESİ`
     ikilisini seçti. Gerekçe geçerli: `judicial_unit` değerleri TEK `parent_code` taşır,
     Yargıtay hem hukuk hem ceza dairesi barındırır → tek değer parent'ı keyfî seçmeye
     zorlardı; kardeş kurum Bölge Adliye de aynı sebeple ikili. Yan sonuç kabul edildi:
     "Yargıtay Hukuk Genel Kurulu" → YARGITAY HUKUK DAİRESİ (birim alanının çözünürlüğü
     daire/kurul ayrımını taşımıyor; tam ad `cases.court`ta duruyor, bugün 0 kart).
     G070'in bıraktığı iki kalem: (a) dolgu kelime + tür önceliği → İŞ: G071 (aşağıda,
     bağımsız doğrulandı: "Şişli Nöbetçi Sulh Hukuk" → yer=None olurken "Şişli 1. Sulh
     Hukuk" TAM okunuyor; ayrıca "İzmir İl Tüketici Hakem Heyeti" → TÜKETİCİ MAHKEMESİ
     sınıflanıyor). (b) varyant→kanonik yer eşlemesi (C+D sınıfı, 32 tekil: "Bakirköy",
     "Ereğli Kdz", "Afyon") KUYRUĞA YAZILMADI — `cases.court` backfill'iyle birlikte
     düşünülmeli, o da gerçek müvekkil verisi = KULLANICI KARARI. Sözlüğe ikinci yazım
     eklemek çözüm değil (aynı yere iki kimlik açar, G070 kararı). -->

- [x] G071 | bant:backend | bagimli:- | Dolgu kelime toleransı + tür önceliği: "Nöbetçi" mahkemede yer düşüyor, hakem heyeti mahkeme sayılıyor

## ADR-013 uygulaması (2026-08-14 gündüz oturumları — kuyruğa GİRMEDİ, kullanıcıyla koşuldu)

<!-- "Kullanıcı kararı bekleyenler"deki pip/npm yükseltmeleri kalemi burada kapandı.
     DEPLOY #12 (2026-08-14 ~19:00 TR, kullanıcı onayıyla): prod = 74c867a — bu bölümün
     tamamı canlıda. Akış: push → CI yeşil → deploy.sh (sunucu test kapısı 1280 passed /
     8 env-skip, healthz sürüm teyidi, açılışta 0 ERROR — G058 fix'i ilk gerçek prod
     açılışında doğrulandı). Rollback: ./rollback.sh 984aae8 · dump:
     predeploy_74c867a_20260814-154636.dump. -->

- ✅ **K1'in 7 adımı + K3 kapıları + K4 çalışma zamanları** (`fa645ab`..`431e384` + `78a47fb`):
  npm minör yamaları, dotenv/requests/multipart/Pillow/cryptography(49.0.0)/PyJWT(2.13.0)/
  msal, fastapi 0.141.1, node:20→24 + python:3.10→3.12, pip-audit + npm audit CI kapıları
  (tarihli ignore listeleriyle).
- ✅ **react-router-dom v6 → react-router v7.18.2** (`262333c` bayraklar + `eab6185` paket
  + `31580ec` ADR şerhi): v6.30.4'te iki future flag (`v7_startTransition`,
  `v7_relativeSplatPath`) önce ayrı commit'le açılıp konsol kanıtıyla doğrulandı; sonra
  22 dosyada import `react-router-dom` → `react-router`, `future` prop'u kaldırıldı
  (v7'de FutureConfig boş). `audit-ignore.txt`'ten 3 GHSA satırı silindi;
  `check-npm-audit.mjs` → **0 bilinen açık**. Kapılar: vitest 332/332, eslint 0 hata,
  `tsc -b --force` temiz, build OK, Docker imaj duman testi (login yönlendirme + 404 splat)
  geçti. Login arkası sayfalar MSAL istediğinden tıklanamadı — deploy öncesi girişli kısa
  gezinti önerilir.
- **Bilinçli AÇIK kalan:** vite 5.4 majörü (dev zinciri esbuild advisory'si; CI'da
  bloklamayan bilgi kapısında, ADR-013 K5 satır "vite (dev)" — ayrı iş).

## Deploy #10'da bulunanlar (2026-08-13, prod'da gözlendi — kuyruğa YAZILMADI)

- **DERS — kapı merdiveninin kör noktası: ÇIPLAK Postgres.** Deploy #10'un push'unda CI
  backend'i kırmızıya döndü, üç kapımızın (lokal konteyner, `deploy.sh --gate-only`, denetçi)
  üçü de yeşildi. Sebep: DB'li testler için üç ortam **üç farklı** DB durumu sunuyor —
  lokal konteyner *tablo + veri*, deploy kapısı *tablo, veri yok* (kendi postgres'ini
  **migrasyonlu** kaldırıyor, G050), CI ise **çıplak postgres, hiç tablo yok**.
  `test_case_matcher_sql.py` (G054) yalnız "veri boş mu"yu koruyordu, "tablo var mı"yı
  değil → `UndefinedTable` FAIL, ardından modül kapsamlı bağlantıda transaction abort
  olduğu için 3 test daha `InFailedSqlTransaction` ile domino (1 gerçek hata, 4 kırmızı).
  Düzeltildi: fixture `to_regclass` ile şema kontrolü yapıp SKIP ediyor + `autouse`
  rollback domino'yu kesiyor; CI koşulu çıplak postgres konteyneriyle **taklit edilerek**
  doğrulandı. **Kural: gerçek DB'ye bağlanan yeni bir test yazan, üç ortamın üçünü de
  düşünmeli** — "DB'ye ulaşılamıyorsa SKIP" yetmez, "şema göçmemişse de SKIP" gerekir.

- ✅ **KAPANDI — G058 (2026-08-13).** Yarış dokuz seed fonksiyonunun **hepsinde** varmış;
  yalnız `appealing_parties` görünür olmuş çünkü Deploy #10'un getirdiği tek YENİ (ve boş)
  tablo oydu. Düzeltme satır başına SAVEPOINT (`seed_data._ekle_yarissiz`) — lider kilidi
  DEĞİL, çünkü kilit konteyner içinde tekilleştirir ve `up -d` sırasında eski/yeni konteyner
  kısa süre birlikte yaşayabilir. Lokalde tablo boşaltılıp `--force-recreate` ile doğrulandı:
  **0 ERROR**, kazanan worker "Seeded 3 new appealing_parties" INFO'su basıyor, kaybeden
  sessiz. Aşağıdaki özgün kayıt tarihsel iz olarak duruyor.

- **`appealing_parties` seed'i iki worker arasında yarışıyor.** Prod açılışında tek ERROR:
  `Seed AppealingParties Error: UniqueViolation ... Key (code)=(DAVACI) already exists`
  (`seed_data.py:316`). İki uvicorn worker'ı (pid 16 + 17) aynı anda tohumluyor, biri
  kazanıyor, diğeri kısıta çarpıyor. **Veri DOĞRU** — prod'da 3 satır, 0 mükerrer;
  kısıt görevini yapmış. Ama her açılışta bir ERROR basılıyor ve bu, log sözleşmesini
  ("nihai başarısızlık TEK ERROR", `analyzer.py::_failed_event`) aşındırır: izleme
  gürültüye alışır. G044'ün getirdiği yeni tablo, yani bu deploy'un ürünü.
  Çözüm yönü: seed'i lider kilidine almak (`services/singleton_lock.py`, APScheduler ve
  upload outbox zaten orada) ya da `ON CONFLICT DO NOTHING`. Diğer seed'ler de aynı
  desende mi — taranmalı.

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

- **Güvenlik D-3: prod'da 8080 portu dışarı açık mı?** `docker-compose.yml:126`
  frontend'i `"8080:80"` ile TÜM arayüzlere yayınlıyor (backend `127.0.0.1:8001`,
  postgres `127.0.0.1:5432` — ikisi bilinçli localhost'ta, frontend değil). GCP
  güvenlik duvarı 8080'i kapatıyorsa iş yok; açıksa konteyner nginx'ine TLS'siz
  düz HTTP ile erişilir ve host nginx katmanı atlanır (`/export` yine kapalı —
  `nginx.conf:75`). Ölçüm ssh gerektirmez:
  `gcloud compute firewall-rules list --format="table(name,direction,allowed[].map().firewall_rule().list(),sourceRanges.list())"`
  Düzeltme `- "127.0.0.1:8080:80"` olur; ÖN KOŞUL host nginx upstream'inin
  gerçekten localhost olduğunun doğrulanması (konfig repo dışında). Recreate ister.
  Ayrıntı: `docs/arsiv/saldiri-yuzeyi-guvenlik-denetimi-2026-08-22.md` §5 D-3
- **Güvenlik D-4: idari bildirim uçlarının yetkisi.** `/api/notifications/overview`
  ve `/unresolved-targets` (`routes/notifications.py:181,245`) `require_admin`
  DEĞİL — giriş yapan herkes başkalarına giden süre/duruşma uyarılarını ve okunma
  durumunu görüyor. Bu 2026-08-20 kararınız (rol kavramı yok, "idari pano" bir
  localStorage toggle'ı) ve denetim bunu kod hatası saymıyor; sızan alanlar
  sınırlı (başlıklarda müvekkil PII yok, gövde yayınlanmıyor). Geri almak
  isterseniz iki satır + `test_g087_bildirim_yonetim_uclari.py` güncellemesi.
  **Otomasyona verilmedi: kararınızı sessizce tersine çevirmemek için.**
- 0.5 ofis no kategori rejimi: X1 = 1.658 kayıt → dokunma / retag / eşleme tablosu (ADR şart)
- 0.6 prod export + hukukbot sağlık denetimi (ssh)
- service_type backfill (reçete canlı veride çürüdü, ayrı keşif gerekiyor)
- ✅ KAPANDI (2026-08-17) — A.2 gerçek müvekkil verisi OneDrive senkronundan çıkarıldı:
  134 MB legacy SQLite + 139 MB kalibrasyon verisi `C:\hukdok-veri\` altına **taşındı**
  (silinmedi), veri taşıyan 3 eski lokal imaj etiketi silindi. Araçlar `CALIB_DATA_DIR`
  env'inden okuyor; konteynerde doğrulandı. Ayrıntı: temizlik planı A.2 altındaki blok
- ✅ KAPANDI (2026-08-14) — pip/npm yükseltmeleri: ADR-013 K1-K4 + react-router v6→v7
  uygulandı (yukarıdaki "ADR-013 uygulaması" bölümü). Kalan tek parça vite majörü
  (dev-zinciri, bloklamıyor); Deploy #12 ile 2026-08-14'te prod'a çıktı (74c867a)
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
