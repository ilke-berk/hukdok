# 016 — Ofis no kategori rejimi: `K1` ileriye dönük, geçmiş dokunulmaz, raporlama kimlikten ayrılır

> Son doğrulama: 2026-08-12 · 74bb425 (G039)

- **Durum:** kabul — kullanıcı yetkisiyle verildi (12.08.2026). Temizlik planı **§2 madde
  0.5'in bekleyen kararı budur; bu ADR ile kapanır.**
- **Bağlam:** İki sorun aynı yerde kesişiyor.

  **(1) Kod tarafında çatallanma.** `generateTrackingNumber` birinci blok için kategori
  **adı** bekliyor ve `CATEGORY_MAP` anahtarlarıyla `includes()` karşılaştırması yapıyor
  (`frontend/src/lib/caseNumberUtils.ts:111-118`); anahtarlar `"Doktor"`, `"Sağlık
  Çalışanı"`, `"Özel Hastane"`, `"Sigorta"`, `"Hasta"`, `"Diğer"` (`:3-10`). Üç çağrı
  noktası ise **kodu** geçiyor: `NewCase.tsx:428,451` ve `IntakeReviewStep.tsx:245,249`
  ile `:571-572` `bestCategoryCode(...)` çıktısını (`"D1"`) `category` alanına koyuyor.
  `"D1"` hiçbir anahtarı içermediği için `block1` sessizce varsayılana,
  **`"X1"`e düşüyor** (`caseNumberUtils.ts:112`). `QuickCaseModal.tsx:319` doğru — ada
  göre geçiyor. Canlı sonuç: **X1 = 1.658 kayıt (%11,6)**.

  **(2) Kurum kategorisinin kendi kodu yok.** Kurum müvekkiller `"Diğer"` üzerinden yine
  `X1`e düşüyor; karşı taraf ekibi haklı olarak "diğer içinde kaybolursa müvekkil tipi
  raporlaması bozulur" dedi.

  Düzeltme deploy edilince aynı müvekkil kategorisi dün `X1`, bugün `D1`/`H1`/`K1`
  üretecek — arşivde iki rejim oluşacak. Bu **operasyonel** bir karardır, teknik değil:
  numaranın kendisi işletmede kimlik olarak dolaşıyor.

## Karar — üç parça

1. **`K1` kodu açılır ve YALNIZ bundan sonra açılan Kurum kayıtlarında kullanılır.**
   Kod bugün hiçbir eşleme tablosunda yok (`caseNumberUtils.ts:3-10` ve kanonik ikizi
   `backend/scripts/retag_tracking_nos.py:32-38`); eklenmesi ileriye dönüktür.
2. **Mevcut 1.658 `X1` kaydı ve 73 Kurum föyü DOKUNULMAZ.** Geriye dönük retag yapılmaz.
3. **Kategori raporlaması `clients.category` alanına taşınır.** Alan zaten var
   (`backend/models.py:239`) ve aktarımla 8.409 satırın tamamında dolu geliyor
   (Müvekkil Tipi eşlemesi). Rapor ve filtre bu alandan okur, ofis numarasının ilk
   bloğundan değil.

## Gerekçe

**Çekirdek ilke: ofis numarası bir kimliktir, bir sorgu boyutu değildir.**

Numaranın içine gömülü semantiği sonradan raporlama boyutu olarak kullanmak yanlış
katmandır. Kimlik **değişmez** olmalıdır; sorgu boyutu **değişebilir** olmalıdır. İkisi
aynı dizgeye sıkıştırıldığı için bugün "raporlamayı düzeltmek" cümlesi "14.395 kaydın
kimliğini yeniden yazmak" anlamına geliyor — bu, sorunun kendisidir, çözümü değil.

Bu ayrımı yaptığımız anda üçüncü parça bedavaya gelir: **1.658 `X1` kaydı, kodları `X1`
kalsa bile doğru raporlanır**, çünkü rapor artık numaraya değil `clients.category`'ye
bakmaktadır. Karşı tarafın endişesi kod değiştirmeden karşılanmış olur.

Kimliğin dokunulmazlığının somut sebebi: ofis numarası **kod tabanının dışında** yaşıyor —
SharePoint arşiv klasör adlarında ve gönderilmiş dış yazışmalarda. Bunlar DB'den geri
alınamaz. Aynı gerçeğin sistem içindeki izi de var: eski sistem numarası hâlâ aranabilir
bir kolon olarak taşınıyor (`Case.klasor_no_2`, `backend/models.py:49`, "Eski sistem no —
gizli, aranabilir"; arama yolu `managers/case_manager.py:317,332,361,366`). Bir kez
dağıtılan numara, sistem onu değiştirse bile aranmaya devam ediyor.

## Reddedilenler

- **(b) Geriye dönük retag — 1.658 kaydı düzelt.** Araç **var ve çalışıyor**
  (`backend/scripts/retag_tracking_nos.py`, `--dry-run` destekli), yani bu bir yetenek
  eksikliği değil bilinçli bir tercihtir. Reddedilme sebebi: DB'yi dosya sisteminden ve dış
  dünyadan ayrıştırır. SharePoint klasör adları ile yazışmalardaki referanslar eski numarayı
  taşımaya devam eder; retag sonrası aynı dosya iki farklı numarayla anılır. Kimliği
  değiştirmek, tanımı gereği kimliği yok etmektir.
  *Yeniden açma tetikleyicisi:* SharePoint klasör adları ile `cases.tracking_no` arasında
  otomatik ve **doğrulanmış** bir yeniden adlandırma yolu kurulursa — o zaman iki dünya
  birlikte taşınabilir.
- **(c) Yalnız yeni kayıtlar + eskiler için eşleme tablosu.** İkinci bir doğruluk kaynağı
  üretir: her tüketicinin (liste, panel, export, hukukbot) eşlemeyi bilmesi gerekir;
  bilmeyen sessizce yanlış raporlar. Üstelik `clients.category` **zaten** doğru katmanda
  duran ve aktarımla dolacak olan alandır — eşleme tablosu onun yerine geçen, bakımı
  gereken bir ikizdir.
- **Ofis numarası formatını semantikten arındırıp saf sayaca çevirmek** — teorik olarak
  doğru yön, ama 14.395 kayıt ve yıllardır dolaşan arşiv klasörleri karşısında (b)'nin
  bütün risklerini daha büyük ölçekte taşır. Aynı gerekçeyle reddedildi.

## Sonuçları ve sınırları

- **Kod çatallanmasının (0.5-(1)) düzeltilmesi bu ADR'nin kapsamı DEĞİLDİR.** Bu kayıt
  düzeltmenin **geçmiş veriye ne yapacağını** sabitler: hiçbir şey. Çağrı noktalarının
  kod yerine ad geçirmesi (ya da `generateTrackingNumber`'ın ikisini de kabul etmesi) ayrı
  bir frontend işidir ve deploy edildiği gün iki rejim resmen başlar.
- **Kod ile ad çatallanmasının kök nedeni tek değil, üçtür:** dava açma mantığının üç
  kopyası (`NewCase.tsx`, `IntakeReviewStep.tsx`, `QuickCaseModal.tsx`) ve üçünden ikisi
  sapmış. Tekilleştirme temizlik planında ayrı kalem olarak duruyor (§9 sonu).
- **Ofis numarası tekilliği bir index'e bağlı:** `ix_cases_tracking_no`
  (`backend/managers/case_manager.py:32`, `indisunique = true`, `pg_constraint` karşılığı
  YOK). FAZ D 6.2'nin "kullanılmayan index'i düşür" çalışması bu index'i **dışlamak
  zorundadır** — `idx_scan = 0` görünür, çünkü kısıt doğrulaması sayacı artırmaz.
- **`retag_tracking_nos.py` yaşayan bir risktir.** Karar (b)'yi reddettiğine göre script
  elle çalıştırıldığında bu ADR'yi ihlal eder; dosya başına bu şerh düşülmelidir.
- **`CATEGORY_MAP` ikizi ayrışık:** frontend haritasında `"Diğer": "X1"` var
  (`caseNumberUtils.ts:9`), kanonik ikizi sayılan Python haritasında yok
  (`retag_tracking_nos.py:32-38`). `K1` eklenirken **iki tarafa birden** eklenmelidir.

- **Test:** bu kayıt için yeni test yok (karar belgesi). `K1` eklenirken kabul kriteri
  `frontend/src/lib/caseNumberUtils.test.ts`'in mevcut öncelik testlerinin (`bestCategoryCode`)
  bozulmamasıdır — `K1`, `X1`den güçlü ama `D1`/`D2`/`H2`/`H1`den zayıf olmalıdır
  (`caseNumberUtils.ts:198-202`).
- **İlgili:** [`002-ofis-no-isim-blogu-onceligi.md`](002-ofis-no-isim-blogu-onceligi.md)
  (aynı numaranın ikinci bloğu),
  [`docs/plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md`](../plan/temizlik-ve-yapisal-saglik-plani-2026-08-11.md) §2 madde 0.5,
  [`docs/plan/faz-f-aktarim-gereksinimleri-2026-08-12.md`](../plan/faz-f-aktarim-gereksinimleri-2026-08-12.md) §4 K3
