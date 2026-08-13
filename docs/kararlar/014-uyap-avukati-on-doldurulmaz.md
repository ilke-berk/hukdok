# 014 — UYAP Avukatı ön-doldurulmaz; zorunluluk bağlamsallaşır

> Son doğrulama: 2026-08-12 · 74bb425 (G039)

- **Durum:** kabul — kullanıcı yetkisiyle verildi (12.08.2026)
- **Bağlam:** HUKDOK teslim paketinde **UYAP Avukatı alanı boş geliyor** ve alan bugün
  koşulsuz zorunlu (`backend/required_fields.py:58`). Karşı taraf ekibi bir çıkış yolu
  önerdi: *"Sorumlu Avukatlar'ın ilk ismiyle ön-doldurup 'teyit bekliyor' işaretlemek
  mümkün mü?"* — çünkü aksi hâlde aktarılan her kayıt "eksik alan" filtresinde yanacak.
- **Karar:** **Ön-doldurma yapılmaz.** Alan boş kalır. Çözüm veri tarafında değil
  **filtre tarafında**: eksik-alan filtresi aktarım kaynaklı kayıtları ayrı kovada tutar,
  provenance `case_history.source = HUKDOK_TESLIM_*` üzerinden okunur
  (`backend/models.py:240`, `source = Column(String(300))`). Alan elle doldurulunca kayıt
  normal kovaya geçer. Karşı tarafa dönülen cevap budur.

## Gerekçe

1. **UYAP vekili ≠ büronun sorumlu avukatı.** UYAP'ta dosyaya kayıtlı vekil, büro içi iş
   dağılımından bağımsızdır; dosya devri, vekaletname kapsamı ve UYAP yetkilendirmesi
   birbirinden ayrı değişir. İki alan sistemde de ayrı yaşıyor: `responsible_lawyer_name`
   ve `uyap_lawyer_name` (`backend/models.py:31-32`) ayrı kolonlar ve ikisi de ayrı ayrı
   zorunlu listede (`required_fields.py:57-58`).
2. **Uydurma veri boş veriden pahalıdır.** Ön-doldurma 8.409 kaydın tamamına, doğruluğu
   hiç ölçülmemiş bir isim yazar. Provenance imzası bunu "uydurma" olmaktan çıkarmaz,
   yalnız izlenebilir kılar. Boş alan kimseyi yanıltmaz; yanlış dolu alan yanıltır —
   birisi ona güvenip UYAP işlemi yapar.
3. **Filtrenin kullanılabilir kalması bir gereksinimdir.** "Her zaman ateşleyen" bir eksik
   listesi, eksik listesi değildir. Ayrı kova hem filtreyi kullanılabilir tutar hem de
   8.409 dosyanın tamamlanması gereken alanını **görünür** bırakır — ön-doldurma onu
   gizlerdi.

## Reddedilenler

- **"Sorumlu Avukatlar'ın ilk ismiyle ön-doldur + 'teyit bekliyor' işaretle"**
  *(karşı tarafın önerisi)* — yukarıdaki 1. ve 2. maddeler. Ayrıca "ilk isim" kararsız bir
  anahtardır; aynı itiraz [`002`](002-ofis-no-isim-blogu-onceligi.md)'de ofis numarası isim
  bloğu için de yapıldı ve orada da reddedildi.
- **UYAP Avukatı'nı zorunlu listeden tamamen çıkarmak** — alan elle girilen dosyalarda
  gerçekten zorunlu; listeden düşürmek 8.409 kaydın borcunu kapatmak için 14.395 kaydın
  tamamındaki denetimi feda ederdi.
- **Aktarılan kayıtları eksik-alan filtresinden büsbütün gizlemek** — borç görünmez olur,
  hiç kapanmaz.

## Uygulama şerhi — desen var, UYAP alanı için kapı henüz açılmadı

**Güncel not (G046, FAZ D — bu ADR yazıldıktan sonra uygulandı):** kaynak belgenin
"kural `required_fields.py`'de zaten kapılı zorunlu alan deseni mevcut" iddiası bu ADR
yazıldığında yanlıştı ama artık **doğru** — D8 bağlamsal zorunluluk kapısı (`skip_when`
mekanizması + `missing_required_bucket` kolonu, `MISSING_BUCKET_MANUAL`/`MISSING_BUCKET_AKTARIM`
kovaları) `required_fields.py`'de kuruldu ve **D2 için kullanılıyor**: `esas_no` alanı
`skip_when={"field": "file_type", "in": ESAS_BEKLENMEYEN_TURLER}` kapısını taşıyor
(`REQUIRED_CASE_FIELDS`, `required_fields.py:39-63`). SQL karşılığı da artık
`required_fields.py`'de yaşıyor (`missing_required_sql`, `missing_bucket_sql`,
`case_manager.py`'deki eski `_missing_required_clause` **silindi** — tek yazma yolu
`case_manager.refresh_missing_required`, `case_manager.py:498`).

**Ama `uyap_lawyer_name`'in kendisi hâlâ kapısız** (`required_fields.py:58`'de
`skip_when` YOK) — bu ADR'nin asıl konusu olan alan için mekanizma kurulu ama
**kullanılmadı**. Mevcut tek bağlamsal kural hâlâ karşı taraf TC'sidir: denetim yalnız
`COUNTER` taraf varsa işler (`required_fields.py:65-68`, SQL karşılığı
`required_fields.py:175` `_sql_counter_party`). UYAP alanına D8 kapısını eklemek hâlâ
kalan iştir — mekanizma hazır, bu alana bağlanması gerekiyor.

Bu, D2 ile (Ana Tür ∈ {ARABULUCULUK, SAVCILIK, DANIŞMANLIK, TAHKİM} ise esas beklenmez)
**aynı sınıf** bir değişikliktir ve aynı mekanizmayı kullanır: zorunluluk mutlak değil
bağlamsaldır.

- **Test:** bu kayıt için yeni test yok (karar belgesi). Uygulaması (D8) FAZ F kapsamında;
  kabul kriteri `compute_missing_fields` + `_missing_required_clause` çiftinin **aynı**
  kovalamayı üretmesidir — iki taraf ayrışırsa panel ile liste sessizce çelişir.
- **İlgili:** [`docs/plan/faz-f-aktarim-gereksinimleri-2026-08-12.md`](../plan/faz-f-aktarim-gereksinimleri-2026-08-12.md) §4 K1 + §2 (D2/D8),
  [`002-ofis-no-isim-blogu-onceligi.md`](002-ofis-no-isim-blogu-onceligi.md)
