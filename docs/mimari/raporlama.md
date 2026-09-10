# Raporlama modülü — kayıt defteri → süz-ve-gör ekranı → önizleme → Excel/CSV export + koşu logu → AI asistan

> **Son doğrulama: 2026-09-07 · a36e98f** (G140; ilk tur G136 · e31457e). **G166 (2026-09-10) eki: §2.4
> bağlı kaynak kolonları + §13 sınırlar + §15 test satırı** — o bölümlerdeki satır numaraları yok, işlev adları
> koddan; G166 öncesi bölümlerin satır numaraları a36e98f'e aittir (registry büyüdü, kaydılar).
> Her uç adı, env, tablo adı, alan ve limit koddan okunarak yazılmıştır; satır numaraları bu
> commit'e aittir. Kod ile çelişirse kod haklıdır — bu dosyayı düzelt. Plan/sözleşme dosyası
> [`docs/plan/raporlama-plani-2026-09-06.md`](../plan/raporlama-plani-2026-09-06.md);
> planla kod arasındaki farklar §11'de (ilk tur §2 farkları F1-F10, ikinci tur §4 farkları
> F11-F22) ve planın kendisinde "uygulamada değişti" şerhiyle.

Yönetici, DB'den kolon/filtre/sıralama seçerek liste üretir, önizler, Excel ya da CSV indirir;
her indirme "kim, ne zaman, hangi tanım, kaç satır, hangi dosya" olarak loglanır ve çıktının
kendisi diskte saklanır. Aynı ekranda AI asistan doğal dil isteğini rapor tanımına çevirir —
veriyi görmez, sorgu çalıştırmaz. **Test aşamasında yalnız yöneticiler** kullanır: bütün uçlar
`Depends(require_admin)` (`backend/routes/config.py:66`, `ADMIN_EMAILS`) +
`Depends(get_current_tenant)` (`backend/dependencies.py:71`) ile korunur.

İkinci tur (G137-G139, plan §4): v1'in "sorgu kurucu" ekranı (alan → operatör → değer, düz
`<select>`, sol sütunda kolon listesi) **"süz ve gör"** ekranına çevrildi — kaynak kartları →
katalogdan gelen filtre şeridi (operatör seçici YOK, op kontrolden türetilir) → "Kolonlar (N)"
yan paneli → otomatik önizleme → başlıktan sıralama. Katalog bunun için `grup`/`kontrol`/`oplar`/
`oneriler` (kolon) ve `hizli_filtreler`/`kolon_setleri` (kaynak) alanlarını taşır; dava kaynağında
taraf bağlantılı dört kolon EXISTS alt sorgusuyla süzülür. **Sunucu sözleşmesi (`RaporTanimi`,
uç adları, olaylar) DEĞİŞMEDİ** — §4.2/§4.3 yalnız katalog eki + sunum katmanıdır.

```
Rapor sekmesi (frontend/src/pages/ReportsPage.tsx:550-629 — G139 yerleşimi)
   SourceCards.tsx (4 kart) → QuickFilters.tsx (şerit: hızlı yuvalar + "Başka alan" + çipler)
   → araç çubuğu: ColumnSheet.tsx "Kolonlar (N)" yan paneli + TemplateBar + Excel/CSV + Asistan
   → PreviewTable.tsx (tam genişlik; başlıktan sıralama; "güncelleniyor…")
   │ GET /api/reports/catalog ──▶ registry.katalog()  (kaynaklar · kolonlar · gruplar · kontroller · seçenek/öneri ·
   │                               hızlı filtreler · kolon setleri · limitler) — tenant anahtarlı 60 sn süreç içi önbellek
   │ POST /api/reports/preview ─▶ motor.onizle()      (sayfalı, LOGLANMAZ; ekran her geçerli taslak değişiminde ister)
   │ POST /api/reports/export ──▶ COUNT → 413? → report_runs satırı → dosya <RAPOR_CIKTI_DIZINI>/<run_id>-<slug>.<ext>
   │                               → sha256/boyut → tembel temizlik → aynı dosya FileResponse (X-Rapor-Kosu-Id)
   │ GET  /api/reports/runs ────▶ tüm yöneticilerin koşuları;  /runs/{id}/download → saklanan dosya (410 = temizlendi)
   │ /api/reports/templates ────▶ favori şablonlar (kendi + paylaşımlı; soft delete)
   │
Asistan satırı (AssistantBar.tsx, G143) — yalnız admin anahtarı `rapor_asistani` AÇIKKEN görünür
   │ POST /api/reports/chat ────▶ NDJSON: info → [warning] → complete{cevap, tanim, eylem} | failed{error_ozet, error_kod}
   │                               Gemini JSON şemalı tek atış; `tanim` sunucuda AYNI doğrulamadan geçer (K6)
   │ G167 TEYİT DÖNGÜSÜ: `tanim` → okunur teyit kartı (AssistantMessage: kaynak · kolon etiketleri · filtre satırları ·
   │   sıralama; `tanimAyrintisi`), UYGULANMAZ; düzeltme mesajı `mevcut_tanim` = BEKLEYEN tanımla gider;
   │   onay = kartta "Onayla ve uygula" | "Excel indir" | "CSV indir" | sözle (aynı tanım + eylem, `tanimAyni`)
   └─ eylem: onizle → /preview · indir_xlsx|indir_csv → /export (kaynak:"asistan")  ← tek indirme = tek log yolu (K7)
```

## 1. Bileşenler

| Katman | Dosya | Rol |
| --- | --- | --- |
| Sözleşme | `backend/schemas_rapor.py` | `RaporTanimi`/`Filtre`/`Siralama`, sınırlar (`:19-23`), tip↔op tablosu `TIP_OPLARI` (`:29-36`), istek/cevap şemaları, asistan şema ailesi (`:188-273`) — G137-G139'da DEĞİŞMEDİ |
| Kayıt defteri | `backend/services/rapor/registry.py` | Dört veri kaynağı, kolon tanımları (SQLAlchemy ifadesi + tip + grup + seçenek/öneri + türetilmişte EXISTS filtre ifadesi + op alt kümesi), kaynak başına hızlı filtreler + kolon setleri, tenant/soft-delete kısıtları, katalog gövdesi, import anı öz-denetim |
| Motor | `backend/services/rapor/motor.py` | Tanım doğrulama (tip tablosu + kolon alt kümesi), Core `select` kurma (türetilmişte `filtre_ifadesi`), önizleme, `yield_per` satır akışı |
| Çıktı | `backend/services/rapor/cikti.py` | xlsx (openpyxl write-only) / csv üretimi, sha256 |
| Koşu logu | `backend/services/rapor/kosu_logu.py` | `report_runs` yazma yolu, saklama dizini, path denetimi, temizlik |
| Asistan | `backend/services/rapor/asistan.py` + `backend/prompts.py:449` | Gemini çağrısı, katalog metni (yeni katalog alanları GÖMÜLMEZ), asistan tanımı → `RaporTanimi` çevirisi |
| Uçlar | `backend/routes/reports.py` | `/api/reports/*` (prefix `:62`); katalog önbelleği (`:81-109`); `api.py:487`, `:509` ile kayıtlı — `/api` altında olduğu için `nginx.conf:77` `location /api` yeter, nginx istisnası YOK |
| Tablolar | `backend/models.py:1350-1432`, `backend/database.py:1050-1064` | `ReportTemplate`, `ReportRun`, migrasyon madde 46 — G137 migrasyon EKLEMEDİ (hepsi sorgu katmanı) |
| Anahtar / env | `backend/services/app_settings.py:66-79`, `backend/config/settings.py:103-112` | `rapor_asistani` anahtarı; dört env |
| Frontend — saf katman | `frontend/src/lib/reports.ts`, `frontend/src/components/reports/builderState.ts`, `frontend/src/lib/reportsChat.ts` | Katalog tipleri (`:62-104`), tip↔op ikizi `OP_BY_TIP` (`:207-214`), kontrol↔op çevirisi (`:337-466`), tarih kısayolları (`:519-555`), HTTP; şerit durumu ↔ `RaporTanimi` (`builderState.ts`) |
| Frontend — ekran | `frontend/src/pages/ReportsPage.tsx`, `frontend/src/components/reports/{SourceCards,QuickFilters,FilterControl,FilterChip,FieldPicker,ColumnSheet,ColumnPicker,PreviewTable,TemplateBar,ExportButtons,RunsTable,AssistantPanel}.tsx`, `frontend/src/components/ui/sheet.tsx` | Route `/reports` (`App.tsx:101-104`, `ProtectedAdminRoute`), Sidebar "Raporlar" (`components/shell/Sidebar.tsx:67`, yalnız yönetici), `/api/reports/` uzun zaman aşımı listesinde (`lib/api.ts:74`, 300 sn `:58`). `ReportBuilder.tsx` ve `FilterRow.tsx` KALDIRILDI (G138/G139) |

## 2. Kayıt defteri (registry) — beyaz liste

İstemciden (ve asistandan) gelen hiçbir string SQL'e ham girmez: motor yalnız
`Kolon.ifade` SQLAlchemy ifadelerini — türetilmişte `Kolon.filtre_ifadesi`nin ürettiği EXISTS
koşulunu — kullanır; anahtar sözlükte yoksa 422 (`registry.py:3-6`, `motor.py:9-15`). Kolon tipi
kolonun SQLAlchemy tipinden türetilir (`_tip_bul`, `registry.py:146-159`: Boolean→`mantik`,
DateTime/Date→`tarih`, Numeric→`para`, Integer→`sayi`, kalan `metin`); kapalı listeli alanlar
`liste` tipine seçeneklerle zorlanır.

| Kaynak | Çekirdek tablo + kısıt | Kolon (koddan sayıldı) | Türetilmiş kolonlar | Kod |
| --- | --- | --- | --- | --- |
| `davalar` | `cases`; `deleted_at IS NULL` + `tenant_filter_clause` (`:239-240`) | 88 (9 grup) | `muvekkil_adlari` (CLIENT), `karsi_taraf_adlari` (COUNTER), `sigortali_adlari` (`role='Sigortalı'`, her party_type) — `func.aggregate_strings(..., " ; ")` seçim + EXISTS filtre; `muvekkil_kategorisi` (`liste`, CLIENT tarafların canlı kart kategorileri + EXISTS filtre); `foy_sayisi`, `belge_sayisi` (silinmemiş belgeler; filtrelenemez) | `:341-523` |
| `muvekkiller` | `clients`; aynı kural `Client` üzerinden (`:527-528`) | 25 (5 grup) | `dava_sayisi` (case_parties.client_id → silinmemiş cases, DISTINCT; **filtrelenebilir**, `_skaler_filtre`) | `:542-616` |
| `belgeler` | `case_documents` INNER JOIN `cases`; belge `deleted_at IS NULL` + dava kısıtları (`:621-622`) | 20 (4 grup) | `dava_tracking_no`, `dava_subject` (JOIN kolonu, türetilmiş sayılır; filtrelenemez) | `:625-684` |
| `foyler` | `case_foys` INNER JOIN `cases`; dava kısıtları (`:689-690`) | 18 (4 grup) | `dava_tracking_no`, `dava_subject`; `ham_veri` katalog DIŞI | `:693-747` |

Kurallar (kayıt defteri import anında kendini denetler, `_kolonu_denetle` + `_kendini_denetle`,
`registry.py:760-815`):

- **Kataloga girmeyenler:** `YASAK_KOLONLAR = {tenant_id, deleted_at, deleted_by, delete_reason,
  notes, ham_veri, tc_no}` (`:757`); ayrıca `clients.source_ids`, belge `email_error` /
  `conversion_spool_path` listeye alınmamıştır (`:18-20`).
- **Seçeneksiz `liste` kolon yok** (`:764-765`). Seçenek üç katman: sabit çekirdek (seed sabitleri
  `EVENT_TYPES`/`CLIENT_TYPES`/`SERVICE_TYPES`/`CURRENCIES`/... + kod sözlükleri `:205-230`) +
  referans tablosunun aktif adları (`secenek_tablosu`) + kolondaki DISTINCT değerler (türetilmiş
  liste kolonda `secenek_ifadesi` — `muvekkil_kategorisi` → `clients.category`);
  `secenekleri_getir(kolon, db)` birleştirir, `db=None` ise yalnız çekirdek (asistan prompt'u)
  (`:822-850`). Katalog DB'den okur → seçenek listesi statik değildir, büyür (60 sn önbellek, §2.3).
- **Türetilmiş kolon kuralı G137'de gevşedi:** `filtrelenebilir` artık KOLON BAZINDA. Filtrelenebilir
  türetilmiş kolon `filtre_ifadesi` (EXISTS ya da skaler karşılaştırma üreten fonksiyon) taşımak
  ZORUNDA (`:771-772`) ve `izinli_oplar` ile tip tablosunun alt kümesine daralabilir (`:775-777`);
  `siralanabilir=False` DAİMA kalır (`_turetilmis`, `:178-188`; denetim `:769-770`). Filtre ifadesiz
  türetilmiş (`foy_sayisi`, `belge_sayisi`, JOIN kolonları) yine filtrelenemez (katalog
  `filtrelenebilir=false`, `kontrol=null`, `oplar=[]`).
- **Grup kapalı küme:** her kolon `grup` taşır (`_grup(...)`, `:191-193`), grup kaynağın
  `gruplar` demetinde olmak zorunda (`:766-767`); kümeler plan §4.2 ile birebir: Davalar
  `Kimlik · Taraflar · Mahkeme ve konu · Tarihler · Tutarlar · Karar ve aşama · Tıbbi · Aktarım · Sistem`
  (`:342-343`), Müvekkiller `Kimlik · İletişim · Vekalet · Sınıflandırma · Sistem` (`:543`), Belgeler
  `Belge · Dava · Yükleme · Sistem` (`:626`), Föyler `Kimlik · Sınıflandırma · Kapsam · Sistem` (`:694`).
  `gruplar` katalog gövdesine AYRICA yazılmaz — grup sırası kolon sırasından okunur (G137 kararı).
- **Tıbbi beşli** (`tibbi_surec`, `tibbi_olay`, `iddia_edilen_kusur`, `hastada_olusan_zarar`,
  `uygulanan_yontem`) `" ; "` ayraçlı ÇOK DEĞERLİ metindir → `liste` DEĞİL, `contains` ile
  aranır (`:461-469`).
- INNER JOIN sonucu: davasız (`case_id IS NULL`, TEST/UNLINKED) belge rapora GİRMEZ — tenant'a
  bağlanamadığı için bilinçli (`:10-16`).

### 2.1 Katalog sözleşmesi (G137, plan §4.2 + §4.3 şerhi) — `GET /api/reports/catalog`

Kolon gövdesi `_kolon_katalogu` (`registry.py:879-896`), kaynak gövdesi `katalog` (`:899-918`).
Örnek (kısaltılmış; `davalar.muvekkil_adlari` ve kaynak başlığı):

```json
{"veri_kaynaklari": [{
  "anahtar": "davalar", "etiket": "Davalar", "aciklama": "Dava kartları (silinmişler hariç); …",
  "varsayilan_kolonlar": ["tracking_no", "esas_no", "muvekkil_adlari", "court", "subject", "status",
                          "responsible_lawyer_name", "opening_date"],
  "kolonlar": [{
    "anahtar": "muvekkil_adlari", "etiket": "Müvekkiller", "tip": "metin", "grup": "Taraflar",
    "kontrol": "metin_icerir", "filtrelenebilir": true, "siralanabilir": false, "turetilmis": true,
    "oplar": ["contains", "is_null", "not_null"], "secenekler": null,
    "oneriler": ["Anadolu Sigorta A.Ş.", "…"], "oneri_kesik": false
  }, "…"],
  "hizli_filtreler": [{"alan": "opening_date", "alternatifler": ["karar_tarihi", "kesinlesme_tarihi", "created_at"]},
                      {"alan": "status", "alternatifler": []}, "…"],
  "kolon_setleri": [{"ad": "Temel", "kolonlar": ["tracking_no", "…"]}, {"ad": "Karar takibi", "kolonlar": ["…"]}, "…"]
}], "limitler": {"onizleme_sayfa_boyu_max": 200, "export_max_satir": 50000}}
```

| Alan | Değer | Kural / kaynak |
| --- | --- | --- |
| `grup` | kaynağın kapalı kümesinden string | `Kolon.grup`, denetim `registry.py:766-767` |
| `kontrol` | `tarih_araligi` ∣ `coklu_secim` ∣ `metin_icerir` ∣ `sayi_araligi` ∣ `mantik` ∣ `null` | tipten türetilir (`KONTROLLER`, `:66-73`; tarih→tarih_araligi, liste→coklu_secim, metin→metin_icerir, sayi/para→sayi_araligi, mantik→mantik); filtrelenemeyen kolonda `null` (`Kolon.kontrol`, `:112-114`) |
| `oplar` | kolon başına izinli op listesi; filtrelenemeyen kolonda `[]` | `Kolon.oplar` = `izinli_oplar` ∨ `TIP_OPLARI[tip]` (`:108-110`, `:892`). **Plan §4.2'de yoktu, §4.3'e şerh düşüldü** — frontend combobox seçiminde `eq` mi `contains` mı göndereceğini buradan bilir |
| `oneriler` / `oneri_kesik` | `onerili` metin kolonda DISTINCT değer listesi (≤300) + kesildi bayrağı; diğer kolonda `null` / `false` | `onerileri_getir` (`:865-876`): kaynağın `kisitlar(tenant_id)` + boş hariç + `ORDER BY` kolon + `LIMIT 301` (`ONERI_MAX=300`, `:63`); türetilmişte `oneri_sorgusu` (`_taraf_adi_onerileri`, `:280-290`: `case_parties JOIN cases`, dava kısıtları). `db=None` → `[]`. İşaretliler: Davalar `sub_type, responsible_lawyer_name, uyap_lawyer_name, court, judicial_unit, muvekkil_adlari, karsi_taraf_adlari, sigortali_adlari`; Müvekkiller `il, noterlik, specialty, sektor`; Belgeler `belge_turu_adi, uploaded_by` — plan listesiyle birebir |
| `hizli_filtreler` | `[{alan, alternatifler}]`, sıralı | `VeriKaynagi.hizli_filtreler` (`:139`); denetim: alan katalogda ve filtrelenebilir, tekrarsız, `alternatifler` yalnız tarih alanında (`:794-804`). Davalar `opening_date(karar_tarihi, kesinlesme_tarihi, created_at) · status · responsible_lawyer_name · court · muvekkil_adlari · muvekkil_kategorisi · hizmet_turu · maddi_tazminat` (`:503-512`); Müvekkiller `category · il · client_type · dava_sayisi` (`:603-608`); Belgeler `uploaded_at · belge_turu_adi · uploaded_by · link_mode` (`:676-681`); Föyler `durum · hizmet_turu · muvekkil_tipi · kapsam_durumu` (`:739-744`) — plan §4.2 birebir |
| `kolon_setleri` | `[{ad, kolonlar}]` | `VeriKaynagi.kolon_setleri` (`:140`); denetim: ad boş/tekrar değil, set boş değil, kolonlar katalogda (`:805-812`). Davalar `Temel` (= varsayılan) · `Karar takibi` · `Tazminat` · `Taraflar` (`:513-521`); Müvekkiller `Temel · İletişim · Vekalet` (`:609-614`); Belgeler/Föyler yalnız `Temel` (`:682`, `:745`) — plan §4.2 birebir |

Katalog gövdesi tenant'a özeldir (öneriler tenant kurallı) → route süreç içi önbellekler (§2.3).
Asistanın sistem talimatına gömülen katalog metni bu alanları BİLEREK içermez (§7).

### 2.2 Taraf bağlantılı filtreler (Davalar, K1/K2 korunarak)

| anahtar | etiket | tip | seçim ifadesi | filtre (EXISTS) | `oplar` |
| --- | --- | --- | --- | --- | --- |
| `muvekkil_adlari` | Müvekkiller | metin | `case_parties.party_type='CLIENT'` adları `" ; "` birleşik (`_taraf_adlari`, `registry.py:254-262`) | `_taraf_filtresi` (`:265-277`) | `contains, is_null, not_null` (`TARAF_METIN_OPLARI`, `:233`) |
| `karsi_taraf_adlari` | Karşı Taraflar | metin | `party_type='COUNTER'` | aynı | aynı |
| `sigortali_adlari` (YENİ) | Sigortalılar | metin | `role='Sigortalı'`, her party_type (`SIGORTALI_ROLU`, `:230`) | aynı | aynı |
| `muvekkil_kategorisi` (YENİ) | Müvekkil Kategorisi | liste | CLIENT tarafların **canlı** (`clients.deleted_at IS NULL`) kart kategorileri birleşik (`_muvekkil_kategorileri`, `:293-303`); seçenek = seed çekirdeği (`MUVEKKIL_KATEGORILERI`, `:224-225`) ∪ `client_categories` tablosu ∪ `clients.category` DISTINCT | `_muvekkil_kategorisi_filtresi` (`:306-318`): `case_parties JOIN clients`, `party_type='CLIENT'`, `clients.deleted_at IS NULL` | `eq, in, is_null` (`TARAF_KATEGORI_OPLARI`, `:234`) |

- **Semantik:** `contains` = "koşula uyan HERHANGİ bir tarafın adı içerir" (EXISTS; birleşik metin
  üzerinde değil), `is_null` = böyle taraf yok, `not_null` = var (`:266-268`, `:272-276`).
  `muvekkil_kategorisi is_null` = kategorili canlı müvekkil kartı olan CLIENT taraf yok (`:308`, `:316-317`).
- **K1 değişmedi:** EXISTS'i registry kurar, atom koşulu (`ILIKE` kaçışı, `ne` NULL-dahil, `in` bağlı
  parametre) motordan alır — `filtre_ifadesi(op, deger, _ifade_kosulu)` (`motor.py:223-230`,
  `:196-220`); kopya yok. **K2:** tenant kuralı yalnız `cases` üzerinden (`_dava_kisitlari`), taraf
  alt sorgusunda tenant kolonu OKUNMAZ; silinmiş müvekkil kartı `clients.deleted_at` ile elenir.
- `eq` bu üç metin kolonda izinli DEĞİL → frontend combobox seçiminde de `contains` gönderir (§8.2).
- Müvekkiller `dava_sayisi` de filtrelenebilir türetilmiştir (`_skaler_filtre`, `:336-338`, `:586-587`):
  COUNT alt sorgusu doğrudan karşılaştırılır, op tablosu `sayi` ile aynı; COUNT NULL olmadığından
  `is_null` boş küme döner ama 422 yemez (şeritteki "boş olanlar" anahtarı için).

### 2.3 Katalog önbelleği (`routes/reports.py:81-109`)

`_katalogu_getir(tenant_id)`: anahtar `(SessionLocal, tenant_id)`, `KATALOG_ONBELLEK_SN = 60.0`,
saat `_saat = time.monotonic` (testler monkeypatch'ler), `threading.Lock` (sync route threadpool'da
koşar), `katalog_onbellegini_sifirla()` test/yönetim için. Önbellek **worker başına** (2 uvicorn
worker → 60 sn içinde iki worker farklı fotoğraf verebilir; kabul edilebilir, §12). Oturum fabrikası
anahtarda: testlerde monkeypatch'lenen farklı fabrika = farklı DB, bayat gövde sızmaz.

### 2.4 Bağlı kaynak kolonları — kaynaklar arası birleştirme (G166, 2026-09-10)

**Sorun:** "Nisan'dan sonra açılan davaların ofis no + müvekkil adı + müvekkil telefonu" tek raporla
çıkmıyordu — telefon `muvekkiller`de, açılış tarihi `davalar`da; rapor tek kaynak seçer.
**Çözüm (K1/K2 korunarak):** her kaynak `VeriKaynagi.iliskiler` ile bağlı kaynaklarını bildirir
(`Iliski`, `registry.py`); bağlı kaynağın kolonları ana kataloğa **türetilir** (`_bagla` →
`_bagli_kolonlar` → `_bagli_kolon`): anahtar `<iliski>.<kolon>` (`muvekkil.phone`), etiket
`"<İlişki> · <Etiket>"` ("Müvekkil kartı · Telefon"), grup `"<İlişki> · <Grup>"` ("Müvekkil kartı ·
İletişim" — kaynağın kapalı grup kümesine `_bag_gruplari` ile eklenir). Elle kolon listesi YOK:
hedef kaynağa eklenen düz kolon bağlı tarafta kendiliğinden görünür. Bağlı kolonlar HEP çekirdek
(`CEKIRDEK`, bağsız) kaynaktan üretilir → ikinci derece anahtar (`muvekkil.dava.x`) yoktur.

| Kaynak | İlişki (`anahtar` · etiket) | Hedef | Bağ | Kolonlar |
| --- | --- | --- | --- | --- |
| `davalar` | `muvekkil` · Müvekkil kartı | `muvekkiller` | çoklu — `case_parties JOIN clients` `kart_eslesmesi` (id ya da ad anahtarı), `party_type='CLIENT'`, `clients.deleted_at IS NULL` (`_muvekkil_kumesi`) | hedefin seçilebilir düz kolonları; `dava_sayisi` hariç |
| `davalar` | `foy` · Föy | `foyler` | çoklu — `case_foys.case_id` (`_foy_kumesi`) | `case_id`/`dava_tracking_no`/`dava_subject` hariç |
| `davalar` | `belge` · Belge | `belgeler` | çoklu — `case_documents.case_id`, `deleted_at IS NULL` (`_belge_kumesi`) | aynı hariç listesi |
| `muvekkiller` | `dava` · Dava | `davalar` | çoklu — `case_parties JOIN cases` `kart_eslesmesi`, CLIENT, `cases.deleted_at IS NULL` (`_muvekkilin_davalari_kumesi`; `dava_sayisi` ile aynı bağ) | hedefin düz kolonları; türetilmişler (`muvekkil_adlari`… `foy_sayisi`) atlanır |
| `belgeler`, `foyler` | `dava` · Dava | `davalar` | **tekil** — `cases` zaten `from_clause` INNER JOIN'inde (`DAVA_ILISKISI_TEKIL`) | hedefin TÜM kolonları aynen kopyalanır (türetilmişler dahil: `dava.muvekkil_adlari` EXISTS'i `cases`e correlate olur) |
| `belgeler`, `foyler` | `muvekkil` · Müvekkil kartı | `muvekkiller` | çoklu — aynı `_muvekkil_kumesi` (`cases` FROM'da olduğu için çalışır) | `dava_sayisi` hariç |

Kolon sayıları (koddan, 10.09): davalar 88 → **145** (56 bağlı), müvekkiller 25 → 108, belgeler
20 → 133, föyler 18 → 131. Eski `dava_tracking_no`/`dava_subject` kolonları şablon uyumu için kaldı.

- **Çoklu bağ kolonu** (`turetilmis=True`, `filtrelenebilir=True`, `siralanabilir=False`, `bag=<iliski>`):
  seçim `_bagli_secim` — bağlı kayıtların değerleri iç alt sorguda `GROUP BY` ile tekilleşir + sıralanır,
  `aggregate_strings(..., " ; ")` ile birleşir (Postgres `string_agg` / sqlite `group_concat`; DISTINCT +
  ayraç sqlite'ta birlikte olmadığından tekilleştirme iç sorguda); tarih/sayı/mantık `CAST(... AS VARCHAR)`
  (Postgres `string_agg` metin ister; ISO tarih metni sıralamada kronolojik; `tip` hedef tipi KALIR →
  filtre kontrolü doğru, hücre gösterimi metin — `hucreBicimle`/`cikti.py` çevrilemeyen metni olduğu gibi
  yazar, tek değerli tarih hücresi Excel'de gerçek tarih olur). Boş değer (`_bos_kosulu`) birleşime girmez.
  Filtre `_bagli_filtre` — EXISTS: `op` = "koşula uyan HERHANGİ bir bağlı kaydın kolonu"; `is_null` = dolu
  değerli bağlı kayıt yok; `not_null` = var; `in` + `null` = `is_null OR in(dolu)` (`muvekkil_kategorisi`
  ile aynı anlam); tarih kolonunda `registry.tarih_kosulu` (DateTime gün aralığı; motorun `_tarih_kosulu`
  buna delege eder, kopya yok), diğerlerinde motorun atom koşulu. `oplar` hedef tipinin tablosu
  (`TIP_OPLARI[tip]`); liste kolonda `secenekler` sabit çekirdek + referans tablosu + DISTINCT
  (`secenek_ifadesi`, sayı yok → `secenek_sayilari=null`); hedefte `onerili` ya da `veriden_liste` kolon
  bağlı tarafta `onerili` — öneri sorgusu HEDEF kaynağın tenant + soft-delete kuralıyla (`_hedef_onerileri`);
  `bos_sayisi=null` (türetilmiş).
- **Tekil bağ kolonu** (`belgeler`/`foyler` → `dava.*`): `replace(k, anahtar, etiket, grup, bag)` — düz kolon
  düz kalır: filtre/sıralama/`bos_sayisi`/veriden liste (GROUP BY belge-satırı sayar) hedefle aynı;
  `liste_sayilari` UNION ALL'ı bu kaynaklarda 18 dava liste kolonuyla büyür (test_g145 beklentisi buna göre).
- **Tenant (K2):** kural ANA satırdan (`kisitlar`); bağlı kayıt tenant'a göre SÜZÜLMEZ — `dava_sayisi` ve
  `muvekkil_kategorisi` ile aynı bilinçli davranış (paylaşımlı havuz, kayıtlar `tenant_id=NULL`; bkz.
  `CLAUDE.md` tenant modeli). Soft-delete bağın içinde uygulanır (silinmiş kart/belge/dava sayılmaz).
- **Katalog (`GET /catalog`):** kaynak gövdesine `iliskiler: [{anahtar, etiket, hedef, coklu}]`, kolona
  `bag: str|null` eklendi; kalan alanlar aynı. Frontend değişmedi (tipler `reports.ts`'e eklendi): yan panel /
  "+ Başka alan" grupları katalogdan okuduğu için "Müvekkil kartı · İletişim" başlıkları kendiliğinden gelir.
  Gövde büyüdü: lokal 14.5k dava / 2k kart ile **~460 KB**, kurulum 743 ms (60 sn önbellek; ölçüm 10.09).
- **Asistan:** `katalog_metni` bağlı kolonları tek tek GÖMMEZ (prompt gürültüsü) — ilişki başına bir satır
  (`_iliski_satiri`: önek, hedef, hariç listesi, çoklu/tekil şerhi); prompt kuralı "BAĞLI KAYNAK KOLONLARI"
  (`prompts.py`) kaynak seçimini "satırı ne oluşturur" ile anlatır. Asistan tanımı aynı doğrulamadan geçer (K6).
- **Öz-denetim (`_kendini_denetle`):** ilişki anahtarı tekrarsız, hedef katalogda ve kendisi değil, çoklu bağ
  `kume` ister / tekil istemez, her ilişkinin en az bir kolonu var; `bag`li kolon bildirilmiş ilişkiye ve
  `<bag>.` önekine uyar, çoklu bağ kolonu türetilmiş+filtrelenebilir; noktalı anahtar yalnız bağlı kolonda.
- **Performans — ad anahtarı ifade index'i (migrasyon 48):** `kart_eslesmesi` correlated alt sorguda satır
  başına koşar; `_ad_anahtari` (`upper(trim(name))` + İ/ı→I) ifadesiz index'le her koşuda `clients`i baştan
  katlıyordu. Ölçüm 10.09 lokal (14.5k dava / 2k kart): "Müvekkil Kategorisi ∈ {Doktor, (boş)}" **21.9 s → 0.5 s**
  (bu, G137'den beri var olan `muvekkil_kategorisi` filtresinin de süresiydi), `muvekkil.vekaletname_tarihi ≥`
  5.5 s → 12 ms, `muvekkil.phone contains` 387 → 25 ms. DDL `idx_clients_ad_anahtari` /
  `idx_case_parties_ad_anahtari` `((replace(replace(upper(trim(name)), 'İ', 'I'), 'ı', 'I')))` — ifade
  `_ad_anahtari` ile BİREBİR (test bekçisi derleyip karşılaştırır); koşulsuz `("index", ...)` op, IF NOT EXISTS.

## 3. Rapor tanımı ve doğrulama

`RaporTanimi = {veri_kaynagi, kolonlar[], filtreler[{alan, op, deger}], siralama[{alan, yon}]}`
(`schemas_rapor.py:75-93`; `extra="forbid"`). Sınırlar (`:19-23`): kolon 1-60 tekrarsız, filtre ≤20,
`in` ≤200 değer, sıralama ≤3, önizleme `sayfa_boyu` ≤200. İki doğrulama katmanı, tek hata tipi:

1. **Yapısal** (Pydantic) — adet/tekrar/op sözlüğü; route gövdeyi `dict` alıp elle doğrular ki
   FastAPI'nin `[{loc,msg,type}]` listesi yerine sözleşmedeki tek `{"alan","sebep"}` dönsün
   (`pydantic_hatasini_cevir`, `:276-288`; `routes/reports.py:24-25`, `:72-76`).
2. **Kayıt defterine karşı** (`motor.tanimi_dogrula`, `motor.py:126-151`) — kaynak/kolon var mı,
   kolon filtrelenebilir mi (`:136-137`), op kolon TİPİNDE izinli mi (`:138-139`), op KOLONUN alt
   kümesinde mi (`kolon.oplar`, `:140-144`; sebep "… kolonunda izinli değil (izinli: …)"), değer
   biçimi doğru mu (`_deger_cevir`, `:96-123`: tarih ISO `YYYY-AA-GG`, sayı/para → `Decimal`,
   mantık `bool`, `between` tam iki öğe, `in` boş olmayan liste), sıralama kolonu sıralanabilir mi (`:149-150`).

Her iki katman `RaporDogrulamaHatasi(alan, sebep)` yükseltir → **422** `{"detail": {"alan", "sebep"}}`
(`schemas_rapor.py:40-49`). Aynı yol asistanın ürettiği tanıma da uygulanır (§7).

Tip ↔ izinli op tablosu (`TIP_OPLARI`, `schemas_rapor.py:29-36`; frontend ikizi
`lib/reports.ts:207-214` `OP_BY_TIP`) — kolonun `oplar`ı bu tablonun alt kümesidir:

| tip | op'lar | `deger` |
| --- | --- | --- |
| `metin` | eq, ne, contains, in, is_null, not_null | str / list[str] |
| `liste` | eq, ne, in, is_null, not_null | str / list[str] (seçeneklerden) |
| `tarih` | eq, gte, lte, between, is_null, not_null | ISO tarih / [başlangıç, bitiş] |
| `sayi`, `para` | eq, gte, lte, between, is_null, not_null | number / [min, max] |
| `mantik` | eq, is_null | bool |

Motor semantiği (`_ifade_kosulu`, `motor.py:196-220`): `contains` = ILIKE, `\`/`%`/`_` kaçışlı
(`ESCAPE '\'`, `:156-161`, `:209-210`); **`ne` NULL satırı da döndürür** (`or_(ifade != deger,
ifade.is_(None))`, `:206-208` — "durum ≠ X" sorusunda boş da farklıdır); DateTime kolonda tarih
filtresi gün aralığı (`eq` = `[gün, gün+1)`, `_tarih_kosulu`, `:172-193`; gün sınırı DB oturumunun
saat dilimine göre, prod UTC). Türetilmişte `_kosul` (`:223-230`) `filtre_ifadesi`ni çağırır.
Sıralama `desc → NULLS LAST`, `asc → NULLS FIRST`, sonda daima birincil anahtar (`:242-247`).
Serileştirme: tarih ISO, `Decimal → float`, NULL → `null` (`:253-260`).

## 4. HTTP uçları — `backend/routes/reports.py`

Hepsi `require_admin` + `get_current_tenant`; yönetici değilse 403 `"Yönetici yetkisi gerekli"`.

| Uç | Kod | Davranış |
| --- | --- | --- |
| `GET /api/reports/catalog` | `:112-119` | §2.1 gövdesi + `{"limitler":{"onizleme_sayfa_boyu_max":200, "export_max_satir":<RAPOR_MAX_SATIR>}}` (`registry.katalog`, `motor.limitler` `motor.py:40-47`); tenant anahtarlı 60 sn önbellek (§2.3) |
| `POST /api/reports/preview` | `:122-139` | `{"tanim", "sayfa"≥1, "sayfa_boyu"≤200}` → `{"kolonlar":[{anahtar,etiket,tip}], "satirlar", "toplam", "sayfa", "sayfa_boyu"}`; **loglanmaz** (K4) |
| `GET /api/reports/templates` | `:174-192` | kendi (`olusturan` = kullanıcı e-postası, küçük harf) + `paylasimli=true`; silinmişler hariç; ad sırası |
| `POST /api/reports/templates` | `:195-214` | `{"ad"≤120, "aciklama"≤500, "tanim", "paylasimli"}` → 201 `RaporSablonu`; tanım kayıt anında motor doğrulamasından geçer (422, `_tanimi_dogrula_422` `:167-171`) |
| `PUT /api/reports/templates/{id}` | `:217-240` | tam gövde (kısmi değil); sahibi değilse 403 (`_sahibi_dogrula`, `:162-164`); yoksa 404 (`:155-159`) |
| `DELETE /api/reports/templates/{id}` | `:243-260` | 204, soft delete (`deleted_at` + `deleted_by`); sahibi değilse 403 |
| `POST /api/reports/export` | `:270-328` | `{"tanim", "format":"xlsx"∣"csv", "sablon_id"∣null, "kaynak":"manuel"∣"asistan"}` → dosya; §5 |
| `GET /api/reports/runs?limit=50&offset=0` | `:351-369` | `limit` 1-200 (`RUNS_LIMIT_MAX`, `:64`, `:353`); `{"toplam", "kosular":[RaporKosusu]}`, tüm yöneticilerin koşuları, `baslangic desc, id desc`, tenant filtreli (`_kosu_sorgusu`, `:347-348`) |
| `GET /api/reports/runs/{id}/download` | `:372-399` | saklanan dosya; yol NULL ya da dosya yok → **410**; yol dizin dışında / izinsiz uzantı → **404** (`:391-392`); başka tenant → 404 |
| `POST /api/reports/chat` | `:404-428` | NDJSON (§7); anahtar kapalıysa gövde ayrıştırılmadan **409** `{"detail":"rapor_asistani kapalı"}` (`:412-413`) |

Kullanıcı kimliği `preferred_username | upn | email` üçlüsü, küçük harf (`_kullanici_epostasi`,
`:67-69`) — `require_admin` ile aynı okuma; frontend sahiplik karşılaştırması da küçük harf
(`lib/reports.ts:733-736` `sablonSahibiMi`).

## 5. Export — tek indirme yolu, tek log yolu

Sıra (`routes/reports.py:277-328`): gövde 422 (`:277`, `:281-285`) → `sablon_id` verildiyse var mı
(404, `:286-287`) → `COUNT` (`:289`) → tavan `settings.rapor_max_satir` aşımı **413**
`{"detail":{"sebep":"satir_limiti","toplam":n,"limit":m}}` (`:290-292`; koşu satırı YAZILMAZ)
→ `kosu_baslat` (satır COMMIT edilir, `id` dosya adına girer; `kosu_logu.py:77-90`)
→ `cikti.ciktiyi_yaz(format, kolonlar, motor.satirlari_akit(...), hedef)` (`:305`)
→ `kosu_bitir` (yol, boyut, sha256, satır sayısı, süre; `kosu_logu.py:93-107`)
→ `temizle_sessiz` (`:322`) → aynı dosya `FileResponse`, başlıklar `Content-Disposition:
attachment; filename="hukdok-rapor-<kaynak>-<YYYYMMDD-HHMM>.<ext>"` (`_indirme_adi`, `:265-267`;
`<kaynak>` = gövdedeki `manuel`/`asistan`) ve `X-Rapor-Kosu-Id: <run id>` (`:325-328`).

- **Dosya-önce kuralı:** çıktı önce `<RAPOR_CIKTI_DIZINI>/<run_id>-<slug>.<ext>` yoluna yazılır
  (`cikti_yolu`, `kosu_logu.py:45-51`; slug yalnız `[A-Za-z0-9-_]`, `Path.name` ile dizin bileşeni
  atılır), boyut + sha256 dosyadan parça parça hesaplanır (`cikti.dosya_ozeti`, `cikti.py:198-206`);
  indirilen dosya ile saklanan dosya AYNI bayttır, `report_runs.sha256` bunu kanıtlar.
- **Bellek disiplini (K3):** motor `yield_per=500` (`AKIS_PARCA`, `motor.py:36`, `:288-295`),
  xlsx `Workbook(write_only=True)` (`cikti.py:106`), csv doğrudan dosya akışı; tüm satır listesi
  hiçbir yerde tutulmaz.
- **Hücre kuralları** (`cikti.py:12-21`): xlsx'te `tarih` gerçek tarih hücresi (`DD.MM.YYYY` /
  `DD.MM.YYYY HH:MM`), `para` `#,##0.00`, `mantik` Evet/Hayır, başlık bordo `4A1530` + beyaz
  kalın, A2 dondurma, otomatik filtre; csv `utf-8-sig` + `;` (`:39-40`), tarih `GG.AA.YYYY`.
- **CSV formül enjeksiyonu:** `= + - @` ile başlayan METİN hücreye `'` öneki, sayılar (negatif
  dahil) dokunulmaz (`csv_hucresi_koru`, `cikti.py:88-93`).
- **Hata yolu** (`:306-316`): yarım dosya silinir, `db.rollback()`, koşu satırı `hata` (≤500 karakter)
  ile KALIR, TEK ERROR log (`:308`), istemciye 500 `"Rapor üretilemedi"`.

## 6. Tablolar ve migrasyon

`report_templates` (`models.py:1350-1384`): `id, ad(120), aciklama(500), tanim JSON, olusturan(255),
paylasimli bool, tenant_id(64), created_at, updated_at, deleted_at, deleted_by(255)`.
`report_runs` (`:1387-1432`): `id, sablon_id FK → report_templates ON DELETE SET NULL, tanim JSON
(anlık görüntü), format(8), kaynak(16) default 'manuel', veri_kaynagi(32), kolon_sayisi, satir_sayisi,
kullanici(255), tenant_id(64), baslangic timestamptz, sure_ms, dosya_adi(255), dosya_yolu(500),
dosya_boyutu, sha256(64), hata(500)`. `tenant_id` yazılır (gelecek ayrım), okuma
`tenant_filter_clause` ile (`auth_helpers.py:14`; `routes/reports.py:148-152`, `:347-348`).

Migrasyon madde 46 (`database.py:1050-1064`): iki tablo `create_all` ile doğar, `("table", ...)`
op'u YAZILMADI (G041 kuralı — ölü kod olurdu). Performans index'i YOK (K10: sıfır dolulukla doğan
tablo ölçülmeden index almaz). **Tek istisna** `idx_report_runs_sablon ON report_runs (sablon_id)`
(`:1062-1064`, koşulsuz `("index", ...)` op'u, `IF NOT EXISTS`) — G043 bekçisi
`test_index_siz_fk_kolonu_kalmadi` index'siz FK'yı yapısal olarak yasaklar; ölçüm sorusu değil.
`format IN ('xlsx','csv')` CHECK'i DB'de değil Pydantic `Literal`'da (`schemas_rapor.py:121-122`).
**G137-G139 şema değiştirmedi** (taraf filtreleri, öneriler, katalog alanları sorgu katmanında).

Neden DB'de, localStorage değil (model docstring'i, `models.py:1355-1358`): paylaşımlı şablonu
diğer yöneticiler görür; çıkıştaki `clearAppStorage()` tarayıcı deposunu siler; `report_runs.sablon_id`
denetim izi. `tanim` JSON şablon sonradan değişse/silinse de "o gün ne indirildi"yi cevaplar.

## 7. Asistan — `POST /api/reports/chat`

Gövde `SohbetIstegi` (`schemas_rapor.py:220-233`): `mesajlar[{rol:"user"|"assistant", icerik}]`
1-20 adet, içerik 1-4000 karakter, **son mesaj `user`** olmalı; `mevcut_tanim: RaporTanimi|null`.
Kapı sırası: 403 (yönetici) → 409 (anahtar, gövde ayrıştırılmadan) → 422 (gövde).

Akış (`services/rapor/asistan.py:238-288`):

```
{"status":"info","message":"Rapor tanımı hazırlanıyor"}
{"status":"warning","message":"Asistanın ürettiği tanım doğrulanamadı (<alan>: <sebep>); tanım olmadan devam ediliyor."}   # isteğe bağlı
{"status":"complete","cevap":"<Türkçe metin>","tanim":RaporTanimi|null,"eylem":"onizle"|"indir_xlsx"|"indir_csv"|null}
{"status":"failed","error_ozet":"... (Kod: xxxxxxxx)","error_kod":"gemini_saturated|gemini_blocked|gemini_truncated|schema_invalid|analysis_error"}
```

`complete`/`failed` SON olaydır; `failed` `analyzer._failed_event` ile üretilir (`analyzer.py:368`),
etiket sınıflandırması `_hata_esle` (`asistan.py:218-236`; 429/5xx/devre kesici → `gemini_saturated`
`analyzer._api_error_kod` ile). Route'un beklenmedik istisnası `{"status":"error","message":"Beklenmedik
hata (Kod: ...)"}` verir ve sözleşme dışıdır (`routes/reports.py:420-426`, `/process` ile aynı desen).

- **Gemini çağrısı YALNIZ `analyzer._gemini_call_with_retry`** (`analyzer.py:82`; devre kesici +
  retry + health sayacı tek yerde) — `asistan.py:257`; `analyzer` tembel import edilir çünkü modül
  import'u `GEMINI_MODEL_NAME` ister ve CI/lokal testler bu env olmadan `routes.reports`'u yükler
  (`:76-81`). `config`: `system_instruction` + `response_mime_type="application/json"` +
  `response_schema=RaporAsistanCevabi` (`:251-255`).
- **Model (K9):** `get_rapor_model()` (`:64-73`) → `GEMINI_RAPOR_MODEL` boşsa
  `case_intake_analyzer.get_intake_model()` (`case_intake_analyzer.py:60`, `GEMINI_INTAKE_MODEL`).
- **Sistem talimatı** (`prompts.py:449`): katalog `katalog_metni()` ile registry'den üretilir
  (`asistan.py:86-115`: `## kaynak — etiket: açıklama`, varsayılan kolonlar, `anahtar · etiket · tip[ ·
  seçenek|seçenek][ · türetilmiş (filtre yalnız: contains|is_null|not_null; sıralama yok)]`;
  seçenekler yalnız sabit çekirdek, DB'siz), elle kolon listesi YOK. **G137 katalog alanları
  (`grup`, `kontrol`, `oplar`, `oneriler`, `hizli_filtreler`, `kolon_setleri`) BİLEREK gömülmez**
  (`:100-105`; öneriler 300'e kadar değer = prompt gürültüsü); yeni dört taraf kolonu doğal olarak
  girer. Bugünün tarihi göreli ifadeler için; `mevcut_tanim` JSON olarak gömülür ("sıfırdan üretme,
  değiştir"). 07.09 duman testi sonrası kural: kaynak belli ama ayrıntı yoksa SORU SORMA, varsayılan
  tanım + `eylem=onizle`; yalnız kaynak/zorunlu bilgi eksikse `tanim=null` + tek soru (`prompts.py:500-505`).
- **Gemini şeması `RaporTanimi` DEĞİL** (`schemas_rapor.py:188-204`): `extra="forbid"`
  `additionalProperties:false` üretir (google-genai 2.11.0 Developer API modunda desteklenmez) ve
  `Filtre.deger: Any` tipsiz özellik olur. Bu yüzden `AsistanTanimi` filtre değerini METİN (`deger`)
  ya da metin listesi (`degerler`, `in`/`between`) taşır; sunucu kolon tipine göre çevirir
  (`asistan_tanimini_cevir`, `asistan.py:164-181`: mantık `true/false/evet/hayır`, sayı/para `Decimal`,
  tarih strip) ve sonucu **aynı** `RaporTanimi` + `motor.tanimi_dogrula` yolundan geçirir
  (`tanimi_dogrula`, `:184-194` — K6 tek doğrulama; taraf kolonunda `eq` gibi alt küme dışı op da
  burada 422'ye düşer). Geçmezse `warning` + `tanim=null` + `eylem=null` ile yine `complete`
  (`:270-288`); geçersiz tanım istemciye hiçbir zaman `tanim` olarak gitmez.
- **Sunucu koruması (07.09 duman testi):** model `tanim=null` + `eylem` döndürürse eylem düşürülür
  (WARNING, `:282-287`) — istemci eylemi mevcut tanım üzerinde yürütmesin.
- **Sohbet geçmişi sunucuda saklanmaz** (K6): istemci `mesajlar`ı taşır; `icerikleri_kur` son 20
  mesajı `user`/`model` rolüne eşler, baştaki asistan mesajlarını atar (Gemini dizisi kullanıcıyla
  başlar; `:198-209`). Frontend geçmişi bileşen state'inde tutar, sayfa yenilenince sıfırlanır
  (`lib/reportsChat.ts:86` `gecmisiKirp` en yeni 20).
- **Asistan DB'ye dokunmaz:** `asistan.py` oturum fabrikası import etmez, satır görmez; `tenant_id`
  yalnız ERROR log bağlamıdır — tanım tenant filtresini `/preview`/`/export`'ta alır (`:243-244`).
- **Eylem (K7):** `eylem` yalnız öneridir; indirme frontend'in `/export` çağrısıyla `kaynak:"asistan"`
  olarak yapılır → koşu logunda "Asistan" rozeti (`ReportsPage.tsx:523`, `lib/reports.ts:863`).
  G138'den beri uygulanan tanım `eylem=null` olsa da otomatik önizlenir; `eylem:"onizle"` aynı tanımda
  bile yeniden ister (`ReportsPage.tsx:497-537`, §8.4).
- **Teyit döngüsü (G167, 2026-09-10 — G143'ün otomatik uygulaması KALKTI):** kullanıcı bulgusu "kart yalnız
  sayı gösteriyor (Kolon 7), teyit/düzeltme/onay yok, indirme karttan olmuyor". `complete` + `tanim` artık
  uygulanmaz: `AssistantMessage` teyit kartı `lib/reportsChat.tanimAyrintisi(tanim, katalog)` ile kaynak etiketi,
  kolon etiketleri (bağlı kolon "Müvekkil kartı · Telefon" dahil), filtre satırları "Etiket · op etiketi · değer"
  (tarih dd.MM.yyyy, `between` "a – b", `in` virgüllü + "(boş)", mantık Evet/Hayır, seçenek etiketi) ve
  sıralama "Etiket ↓" basar; katalogda olmayan anahtar aynen yazılır. `AssistantBar` `bekleyenTanim` tutar: sonraki
  mesajlar sunucuya `mevcut_tanim` olarak BEKLEYEN tanımı taşır (düzeltme onu günceller, oluşturucudakini değil).
  Onay üç yol: "Onayla ve uygula" → `onTanimUygula(tanim, null)`; "Excel indir"/"CSV indir" → `onTanimUygula(tanim,
  indir_*)` (uygulanır + indirilir, K7 aynı yol; asistan `eylem: indir_*` önerdiyse o düğme birincil ama yine tık
  bekler); SÖZLE — asistan bekleyen tanımı AYNEN (`tanimAyni`) + eylemle döndürürse hemen yürür (prompt kuralı
  "TEYİT DÖNGÜSÜ": onay kelimelerinde tanım değişmeden + `onizle`, düzeltmede yalnız istenen alan). `tanim=null` +
  eylem → bekleyen (yoksa oluşturucudaki) tanımla; soru → yalnız balon. "Geri al" kartı yeniden onay bekleyen
  hâle döndürür (bekleyen = o tanım). Kart uygulandıktan sonra indirme düğmeleri kalır.

## 8. Kullanıcı akışı — Rapor sekmesi (G138 + G139, plan §4.1)

Ekran durumu tek doğruluk kaynağı `OlusturucuDurumu = {veri_kaynagi, kolonlar[], serit[], siralama[]}`
(`builderState.ts:18-23`); sunucu tanımı her render'da `tanimOlustur` ile türetilir (`:127-134`,
`ReportsPage.tsx:232`) — boş kontroller tanıma GİRMEZ, §2.1 JSON'u değişmez. Tek durum yazma yolu
`durumDegisti` (`ReportsPage.tsx:304-316`).

### 8.1 Kaynak kartları (`SourceCards.tsx`)

Dört kart `role="radiogroup"`/`role="radio"` + `aria-checked`, kimlik `[data-kaynak]` (`:29-44`);
etiket + tek satır `aciklama` (truncate) + simge; `lg` altında yatay kaydırma, `lg`+ 4 sütun (`:32`).
Kart tıklaması `onKaynakSec` (`ReportsPage.tsx:337-341`): aynı kart = işlem yok; farklı kart →
`kaynakIcinBaslangic(yeni)` (varsayılan kolonlar + boş hızlı yuvalar + sıralama yok,
`builderState.ts:54-62`) ve `durumDegisti` kaynak değişimini görür: `reqIdRef` artar (süren istek yok
sayılır), zamanlayıcı durur, `cevap/hata/sonTanim` ANINDA `null` (`:306-314`) → ekranda hiçbir zaman
başka kaynağın satırı kalmaz; efekt yeni kaynağın varsayılan tanımını hemen ister.
**Dolu açılış:** katalog gelince ilk kaynak (Davalar) + varsayılan kolonlar (`katalogYukle`,
`:157-161`) → otomatik önizleme efekti ilk isteği kendiliğinden atar (madde 6).

### 8.2 Filtre şeridi (`QuickFilters.tsx`, `FilterControl.tsx`, `FilterChip.tsx`, `FieldPicker.tsx`)

- **Yuvalar:** kaynağın `hizli_filtreler`i sırayla boş kontrol olarak açılır (`hizliYuvalar`,
  `builderState.ts:34-51`; katalogda olmayan/filtrelenemeyen alan atlanır); tarih yuvasında
  `alan + alternatifler` alan değiştirici `<select>` (`FilterControl.tsx:58-68`; alternatifler yalnız
  `kontrol === "tarih_araligi"` ise). Yuva × ile silinmez, boşa döner; "+ Başka alan" ile eklenen
  şeritten kalkar (`SeritOgesi.hizli`, `:8-16`; `QuickFilters.tsx:53-62`).
- **Kontroller** (operatör seçici YOK; `FilterControl.tsx:47-53`): `tarih_araligi` = başlangıç +
  bitiş `<input type=date>` + kısayol `<select>` (Bu yıl · Geçen yıl · Son 30 gün · Son 12 ay;
  `tarihKisayolu`, `lib/reports.ts:539-555`, `bugun` testte sabit); `coklu_secim` = checkbox'lı açılır
  liste (`CokluSecim`, `:258-313`, serbest metin YOK, seçenekler katalogdan); `metin_icerir` = düz
  girdi ya da öneri varsa cmdk combobox (`MetinCombobox`, `:332-378`; liste düz alt-dize ile daralır,
  `:27-31`); `sayi_araligi` = "en az / en çok" iki `number` girdisi; `mantik` = Hepsi/Evet/Hayır. Her
  kontrolde "boş olanlar" anahtarı (`:73-84`) değer girdisini kilitler.
- **Kontrol → op** (`kontroldenFiltre`, `lib/reports.ts:373-408`; plan §4.3 tablosu koddan doğrulandı):

  | kontrol | girdi | üretilen filtre | kod |
  | --- | --- | --- | --- |
  | `tarih_araligi` | iki uç / yalnız başlangıç / yalnız bitiş / kısayol | `between [b,e]` / `gte` / `lte` | `:379-386` |
  | `sayi_araligi` | iki uç / yalnız en az / yalnız en çok (JSON number) | `between [a,c]` / `gte` / `lte` | `:387-394` |
  | `coklu_secim` | 1 seçim / n seçim | `eq` / `in [...]` | `:395-398` |
  | `metin_icerir` | yazım / combobox seçimi (`tam`) | `contains` / `eq` — **yalnız kolonun `oplar`ında `eq` varsa**, aksi yine `contains` (`FilterControl.tsx:152`) | `:399-403` |
  | `mantik` | Evet/Hayır | `eq true/false` | `:404-406` |
  | (her kontrol) "boş olanlar" | — | `is_null` (değersiz) | `:377` |
  | `gelismis` | çipin "…" menüsü | op olduğu gibi | `:374-376` |

- **Çipler:** etkin (dolu) kontroller çip satırında `etiket · özet` (`kontrolOzeti`, `:480-513`) ·
  "…" menüsü · × (`FilterChip.tsx:79-137`). Menü = kolonun `oplar`ı ∖ kontrolün doğal op'ları
  (`KONTROL_DOGAL_OPLARI`, `gelismisOplar`, `lib/reports.ts:454-466`; ör. `ne`, `not_null`) + metinde
  "Tam eşitlik" anahtarı (yalnız `oplar`da `eq` varsa, `FilterChip.tsx:59-66`). Gelişmiş op seçilince
  çip `gelismis` durumuna geçer, değer girdisi `GelismisDeger` (`FilterControl.tsx:424-528`); menüde
  "Basit kontrole dön". Etkin filtre sayacı, tavan 20'de "Başka alan" pasif (`QuickFilters.tsx:45-47`).
  "Filtreleri temizle": yuvalar boşa döner, eklenenler kalkar (`:73-81`; aynı kural `seritiTemizle`,
  `builderState.ts:106-114`, boş sonuç kısayolu için).
- **"+ Başka alan"** (`FieldPicker.tsx`): cmdk `Command`, `grup` başlıklı, aranabilir (düz alt-dize,
  `:11-15`); yalnız `filtrelenebilir` ve şeritte olmayan kolonlar (`QuickFilters.tsx:40-43`; tarih
  alternatifleri de gizli).
- **Yükleme (şablon / koşu / asistan tanımı):** `tanimdanDurum` (`builderState.ts:71-100`) her filtreyi
  `filtredenKontrol` (`lib/reports.ts:415-451`) ile çözer: yuva alanına (ya da alternatifine) düşen
  filtre yuvayı doldurur, kalanlar eklenmiş alan olur; çözülemeyen op `gelismis` çip olur ve
  KAYBOLMAZ; gelişmiş çip yuvayı ezmez (yuva boş kalır, `:84-89`). Dolu öğeler TANIMDAKİ sırayla
  önce, boş yuvalar sonra — filtre sırası korunur (şablon eşitliği `JSON.stringify`,
  `ReportsPage.tsx:55`, `:240-242`). Gidiş-dönüşün tek istisnası tek değerli `in` → `eq` (eş anlamlı).

### 8.3 Kolonlar yan paneli (`ColumnSheet.tsx`, `ColumnPicker.tsx`, `ui/sheet.tsx`)

"Kolonlar (N)" düğmesi (`data-testid="kolon-dugmesi"`, `aria-expanded`, `ColumnSheet.tsx:24-40`) sağdan
`Sheet` açar (`@radix-ui/react-dialog` üzerine shadcn şablonu, yeni npm paketi YOK; portal, `sm:max-w-lg`,
`:41`). Panelde (`ColumnPicker.tsx`): hazır setler (`kolon_setleri`; katalogda "Temel" yoksa
`varsayilan_kolonlar`dan üretilir, `:52-59`; tık = seçimi setin SIRASIYLA değiştirir `:141`;
`aria-pressed` sıra bağımsız aynı küme `:33-37`) → arama → `grup` başlıklı checkbox listesi (grup
başlığı "tümünü seç": eksikleri tavana kadar ekler / tam seçiliyse kaldırır / kısmi `indeterminate`,
`:93-104`, `:254-281`) → "Seçili · sıra" (dnd-kit + ↑↓ + × + Temizle, `:195-239`). Tavan 60
(`TANIM_LIMITLERI.kolon_max`, `:85`). Tip rozeti YOK — tip yalnız satır `title` ipucunda (`:285`).
Her değişiklik anında sayfaya yazılır → otomatik önizleme (yapısal = hemen); panel kapanınca ek istek
yok (G139 kararı 1).

### 8.4 Otomatik önizleme (`ReportsPage.tsx:270-298`)

Efekt her `tanim` değişiminde: kaynak yok ya da taslak geçersizse (`tanimGecerliMi`,
`lib/reports.ts:309-325` — kolon 1-60 tekrarsız, filtre ≤20, sıralama ≤3, her filtre kolon bazında
`filtrelenebilir` + `oplar` + `filtreTamamMi`, her sıralama `siralanabilir`) istek GİTMEZ; taslak son
İSTENEN'le (`sonIstenenRef`, hata dönse de) aynıysa istek yok; yapısal değişiklik (kolon, kaynak, seçim,
tik, kısayol, sıralama) → hemen; yazarak girilen değer (`onChange(..., true)`: tarih/sayı/metin girdileri)
→ `ONIZLEME_GECIKME_MS = 600` (`:37`; her tuşta yeniden başlar) ya da odak çıkışında `hemenOnizle`
(`:291-298`). Yarış koruması `reqIdRef` (`:117`, `:244-261`). Sayfa değişimi son BAŞARIYLA önizlenen
tanımla (`sonTanim`, `:318-321`). "Bayat" rozeti ve Önizle düğmesi YOK; tabloda "güncelleniyor…"
(`PreviewTable.tsx:72-81`), geçersiz taslakta son geçerli önizleme ekranda kalır + "taslak eksik" ipucu
(`:62-71`), hata `DataErrorBanner` + "Tekrar dene" (`onRetry`, `ReportsPage.tsx:323-329`, hata anındaki
tanımla). Asistan tanımı `asistanTanimiUygula` (`:497-537`; G167'den beri yalnız kartın Onayla/İndir düğmesi ya da
sözle onayla çağrılır, asistan cevabı tek başına çağırmaz): `eylem=null` → otomatik önizleme;
`onizle` → `sonIstenenRef=null` ile aynı tanımda bile yeniden ister (`:516-520`); `indir_*` →
`/export` `kaynak:"asistan"` (`:521-526`).

### 8.5 Önizleme tablosu ve sıralama (`PreviewTable.tsx`)

Sayaç `"N kayıt · M kolon"` (`:59`, tr-TR binlik). `siralanabilir` başlıklar düğme (`aria-sort`, ok,
çok alanlıda sıra numarası, ipucu döngünün sonraki adımı; `:117-153`); tık → `siralamaDongusu`
(`builderState.ts:140-148`): yok → artan → azalan → kaldır, tavan 3, dördüncüde EN ESKİ düşer.
Türetilmiş kolon başlığı tıklanmaz (`siralanabilirMi`, `ReportsPage.tsx:334`). Boş sonuçta
(`data-testid="bos-sonuc"`, `:100-111`): filtre varken "Bu filtrelerle kayıt yok — filtreleri
gevşetin." + "Filtreleri temizle" kısayolu (`onFiltreleriTemizle`, `ReportsPage.tsx:344-347`),
filtresizken "Bu kaynakta kayıt yok.". Sayfalayıcı `sayfa / toplamSayfa` (`:184-213`).

## 9. Admin anahtarı — `rapor_asistani`

`SETTINGS_REGISTRY["rapor_asistani"]` (`services/app_settings.py:66-75`): label "Rapor asistanı (AI)",
**varsayılan KAPALI** (`default: False` — Gemini maliyetli özellikler repo kültüründe kapalı doğar;
`client_notice_enabled`, `veri_teslim_otomasyonu` gibi). Okuma `rapor_asistani_etkin()` (`:178-180`);
`GET/PUT /api/admin/settings` (`routes/admin.py:50`, `:56`) ile panelden açılır — Yönetim →
Özellikler kartı registry'den otomatik listeler. Kapalıyken `/chat` 409, araç çubuğundaki "Asistan"
düğmesi HİÇ render edilmez (`ReportsPage.tsx:541`, `:598-610`; frontend `raporAsistaniAcikMi()`
`GET /api/admin/settings`'i okur, hata/kayıt yok → false, sessiz; `lib/reportsChat.ts:196`).
**Manuel rapor anahtardan bağımsızdır**: katalog, önizleme, export, şablonlar açık/kapalı fark
etmez. Varsayılanı AÇIK yapmak tek satırdır (`app_settings.py:46-47`).

## 10. Env'ler (`config/settings.py:103-112`, `.env.example:55-66`)

| Env | Varsayılan | Ne | Okuyan |
| --- | --- | --- | --- |
| `RAPOR_MAX_SATIR` | `50000` | export satır tavanı; COUNT aşarsa 413 | `settings.rapor_max_satir` (`routes/reports.py:290`); katalogdaki `export_max_satir` ise `motor.limitler()` `os.getenv` ile okur (`motor.py:44`) — §13 |
| `RAPOR_CIKTI_DIZINI` | `""` → `<backend>/data/rapor_ciktilari` | saklanan çıktı dizini; konteynerde `/app/data` = `backend-data` volume'u (`docker-compose.yml:57`) → recreate'i atlatır | `kosu_logu.cikti_dizini` (`:34-42`) |
| `RAPOR_CIKTI_SAKLAMA_GUN` | `30` | dosya bu kadar günden eskiyse silinir, koşu satırı kalır, indirme 410 | `kosu_logu.temizle` (`:112-138`) |
| `GEMINI_RAPOR_MODEL` | `""` → `GEMINI_INTAKE_MODEL` | asistan modeli; devre kesici model-başına olduğundan intake'ten ayrılabilir | `asistan.get_rapor_model` (`:64-73`) |

Dördü de `.env.example`'da şerhli ve yorumlu (`:55`, `:59`, `:62`, `:66`); prod'da varsayılanlar
yeter. G137-G139 yeni env EKLEMEDİ (`KATALOG_ONBELLEK_SN` sabit, env değil). `.env` değişikliği
`restart` ile gelmez, `docker compose up -d` (recreate) ister.

## 11. Güvenlik modeli

| Tehdit | Savunma | Kod |
| --- | --- | --- |
| SQL enjeksiyonu / rastgele kolon | serbest SQL yok; anahtar registry'de yoksa 422; op tip tablosu + kolon alt kümesi; `contains` ILIKE bağlı parametre + kaçış; `in` bağlı parametre; türetilmişte EXISTS'i registry kurar, atom koşul motorda TEK yerde (K1 değişmedi) | `registry.py:3-6`, `motor.py:9-15`, `:136-144`, `:156-161`, `:196-230` |
| Tenant / soft-delete sızıntısı | her kaynağın `kisitlar(tenant_id)` = `deleted_at IS NULL` + `tenant_filter_clause`; `belgeler`/`foyler` `cases` INNER JOIN'i; **EXISTS taraf filtreleri** `cases` kısıtı altında korele (`case_id = cases.id`), `clients.deleted_at IS NULL`; **öneri listeleri** kaynağın kısıtlarıyla (taraf adları `case_parties JOIN cases` + dava kısıtları); **katalog önbelleği tenant anahtarlı**; şablon/koşu sorguları da tenant filtreli | `registry.py:239-240`, `:265-277`, `:280-290`, `:306-318`, `:527-528`, `:621-622`, `:689-690`, `:853-876`; `routes/reports.py:96`, `:148-152`, `:347-348` |
| PII / teknik alan sızması | `YASAK_KOLONLAR` + import anı öz-denetim; öneriler yalnız `onerili` işaretli metin kolonlarda (`notes`/`tc_no` katalogda yok → öneri de yok) | `registry.py:757-815`, `:778-782` |
| LLM'in ürettiği tanım | manuel tanımla AYNI Pydantic + registry doğrulaması (alt küme op dahil); geçmezse `tanim=null`; `tanim=null` iken `eylem` düşer | `asistan.py:184-194`, `:270-288` |
| Path traversal (indirme) | `yol_guvenli_mi`: `resolve()` sonrası çıktı dizini altında VE `.xlsx/.csv`; aksi 404 | `kosu_logu.py:54-66`, `routes/reports.py:391-392` |
| Dosya adı enjeksiyonu | `cikti_yolu` slug'ı yalnız `[A-Za-z0-9-_]`, `Path.name` | `kosu_logu.py:45-51` |
| CSV formül enjeksiyonu | `= + - @` öneki `'` (metin hücre) | `cikti.py:88-93` |
| Kaynak tüketimi | kolon ≤60 / filtre ≤20 / `in` ≤200 / sayfa ≤200 / export tavanı 413 / `yield_per` + write-only; sohbet ≤20×4000; öneri ≤300 değer/kolon; katalog DISTINCT sorguları 60 sn önbellekli | `schemas_rapor.py:19-23`, `:206-207`; `routes/reports.py:81-109`, `:290-292`; `registry.py:63`, `:874` |
| Yetki | tüm uçlar `require_admin` (`ADMIN_EMAILS`); şablon yazma yalnız sahibi (403) | `routes/config.py:66`, `routes/reports.py:162-164` |

## 12. Plan ile kod arasındaki farklar (uygulamada değişti)

Plan dosyasında aynı şerhle işaretlidir. **İlk tur — §2 sözleşmesi (G130-G136):**

| # | Plan | Kod | Sonuç |
| --- | --- | --- | --- |
| F1 | §2.4 `RaporKosusu` alan listesi | `hata: str|null` alanı eklendi (`schemas_rapor.py:179`) | ek alan; istemci yok sayabilir |
| F2 | §2.5 / K10 "v1'de index yok" | `idx_report_runs_sablon` FK index'i (`database.py:1062-1064`) | G043 "index'siz FK yok" bekçisi; K10'un tek istisnası |
| F3 | §2.6 Gemini şeması `RaporAsistanCevabi{tanim: RaporTanimi}` | `tanim: AsistanTanimi` (metin değerli filtre; `schemas_rapor.py:236-264`) | dış sözleşme değişmedi: `complete.tanim` yine `RaporTanimi` (`SohbetTamamlandi`, `:267-273`) |
| F4 | §2.4 `/chat` gövdesi | ek sınırlar: mesaj ≤20, içerik ≤4000, son mesaj `user` → 422 (`:206-233`) | plana ek |
| F5 | §2.4 `/runs` `limit` | tavan 200 (`routes/reports.py:64`, `:353`) | plana ek |
| F6 | §2.4 `/export` | `sablon_id` yoksa 404 (`:286-287`); üretim hatası 500 + satır `hata` ile kalır (`:306-316`); 413'te satır yazılmaz | plana ek |
| F7 | §2.2 `ne` | NULL satırı dahil (`motor.py:206-208`) | semantik netleştirme |
| F8 | §2.3 katalog dışı liste | `tc_no`, `source_ids`, `email_error`, `conversion_spool_path` de dışarıda (`registry.py:18-20`, `:757`) | plana ek (PII/teknik) |
| F9 | §2.3 JOIN kolonları | `dava_tracking_no`/`dava_subject` türetilmiş sayılır → filtrelenemez/sıralanamaz (`registry.py:643-644`, `:704-705`) | v2'de açılabilir, tek satır (G137 `_turetilmis(filtrelenebilir=True, filtre_ifadesi=...)` yolu hazır) |
| F10 | §2.6 olay listesi | route'un beklenmedik istisnası `{"status":"error","message"}` (`routes/reports.py:420-426`) | sözleşme dışı, `/process` deseni |

**İkinci tur — §4 (G137-G139):** dış sözleşme yine değişmedi; farklar katalog eki, sunum katmanı
kararları ve plandaki "ölçüm/etiket" ifadelerinin somutlaşmasıdır.

| # | Plan §4 | Kod | Sonuç |
| --- | --- | --- | --- |
| F11 | §4.2 katalog kolon alanları `grup/kontrol/oneriler` | + `oplar` (kolon başına izinli op listesi; `registry.py:892`) — §4.3'e şerhle eklendi | frontend combobox `eq`/`contains` kararı ve "…" menüsü buradan; taraf metin kolonlarında `eq` YOK |
| F12 | §4.2 taraf tablosu 4 kolon; hızlı filtre listesinde `dava_sayisi` | `dava_sayisi` de filtrelenebilir türetilmiş (`_skaler_filtre`, `registry.py:586-587`); `is_null` boş küme (COUNT NULL olmaz) | denetim "hızlı filtre filtrelenebilir olmalı" zorladı; `foy_sayisi`/`belge_sayisi` filtrelenemez kaldı |
| F13 | §4.2 öneriler "alfabetik" | `ORDER BY kolon` — DB collation sırası, Türkçe locale değil (`registry.py:861`, `:288`) | Türkçe sıra istenirse ayrı iş |
| F14 | §4.2 `muvekkil_kategorisi` seçim ifadesi | `aggregate_strings` DISTINCT DEĞİL (sqlite `group_concat(DISTINCT x, ayraç)` yok): iki Doktor müvekkil "Doktor ; Doktor" (`registry.py:293-303`) | yalnız görünüm; filtre EXISTS olduğundan doğruluk etkilenmez |
| F15 | §4.2 "katalog cevabı süreç içi 60 sn önbelleklenir" | worker başına (`UVICORN_WORKERS=2`), `(SessionLocal, tenant_id)` anahtarlı, `time.monotonic` (`routes/reports.py:81-109`) | 60 sn içinde iki worker farklı fotoğraf verebilir; `gruplar` kaynağa ayrıca yazılmadı |
| F16 | §4.1 madde 2 "Temizle hepsini siler" | etiket "Filtreleri temizle" (`QuickFilters.tsx:103`); kolon panelindeki "Temizle" ayrı (`ColumnPicker.tsx:208`) | çakışma önlendi |
| F17 | §4.1 madde 5 "600 ms gecikme ya da odak çıkışı" (G138 görevi: `useDebounce` ile) | `useDebounce` KULLANILMADI; efekt + `gecikmeliRef`/`zamanlayiciRef` (`ReportsPage.tsx:271-298`) — aynı sözleşme (600 ms, tek istek), yapısal/yazım ayrımı böyle kurulabildi | davranış plana uygun, mekanizma farklı |
| F18 | §4.3 "şablon/asistan tanımı yüklenince filtreler aynı kontrollere geri çözülür" | + tek değerli `in` → `eq` normalizasyonu; dolu filtreler şeridin BAŞINA (tanım sırası korunur); gelişmiş çip yuvayı ezmez (`builderState.ts:71-100`) | şablon eşitliği/yeniden isteme kapıları için şart |
| F19 | §4.1 madde 3 "shadcn `Sheet`" | `components/ui/sheet.tsx` `@radix-ui/react-dialog` üzerine yerel şablon, yeni paket yok; kenar sınıfları düz tablo | `package.json` değişmedi |
| F20 | §4.1 madde 3 kolon paneli | değişiklik panel açıkken ANINDA önizlenir (kapanışta toplu değil); `max-w-[1600px]` kaldırıldı (tam genişlik kuralı) | G139 kararları 1, 3 |
| F21 | §4.1 madde 7 metin azaltma | kaynak açıklaması yalnız kartta; sayfa başlığı ipucu `h1 title`; tip rozetleri kalktı ama `ColumnPicker` satır ipucu türetilmiş kolonda hâlâ "filtrelenemez, sıralanamaz" yazar (`ColumnPicker.tsx:285`) — taraf kolonlarında yanlış | frontend kapsamı, §13 NOT |
| F22 | §4.1 madde 5 "yalnız geçerli tanımda" | geçersiz taslakta SON GEÇERLİ önizleme ekranda kalır + "taslak eksik" ipucu; boşa düşürülmez (`PreviewTable.tsx:62-71`) | kullanıcı verisiz kalmaz, istek gitmez |

## 13. Bilinen sınırlar, işletme notları

- **Kapsam dışı (plan §1, bilinçli):** PDF çıktı, grafik/dashboard, zamanlanmış rapor e-postası,
  yönetici olmayan roller, sohbet geçmişinin DB'de saklanması, LLM'in SQL üretmesi. Ölçülen kullanım
  sonrası ayrı plan.
- **Taraf adı filtresi "herhangi bir taraf içerir":** `muvekkil_adlari contains "Anadolu"` davada
  bu adı taşıyan EN AZ BİR CLIENT taraf varsa döner; "tüm müvekkilleri X" sorusu sorulamaz. Aynı ad
  karşı tarafta olan dava dönmez (party_type ayrımı). Türetilmiş kolonlarda **sıralama yok**
  (`siralanabilir=False`, motor 422; başlık tıklanmaz).
- **Bağlı kolon (G166, §2.4) sınırları:** çoklu bağda hücre birleşik metindir ("0532 1 ; 0533 2") — kart
  başına ayrı satır isteniyorsa kaynak `muvekkiller` seçilip `dava.*` kullanılır (satırı ne oluşturuyorsa o
  kaynak). Bağ tek hoptur (`muvekkil.dava.x` yok). Bağlı kayıt tenant'a göre süzülmez (paylaşımlı havuz,
  `dava_sayisi` ile aynı). Çoklu bağ kolonu sıralanamaz. Excel'de çok değerli tarih hücresi metin kalır.
- **Öneri listesi tavanı:** 300'ü aşınca ilk 300 (DB sırası) + `oneri_kesik=true`; combobox başlığında
  "İlk 300 değer (liste kesildi)" (`FilterControl.tsx:361`). Sıra DB collation'ı (F13).
- **Önbellek 60 sn / worker başına:** referans listesi ya da yeni taraf adı ekledikten sonra şeritteki
  seçenek/öneri en geç 60 sn sonra görünür; iki worker aynı anda farklı fotoğraf verebilir (F15).
- **`RAPOR_MAX_SATIR` iki okuyucu:** export tavanı `settings.rapor_max_satir` (boot'ta donar),
  katalogdaki `export_max_satir` `motor.limitler()` `os.getenv` (önbellek süresi içinde bir kez).
  Prod'da aynı env'i okurlar, fark yalnız test zamanı; `motor.limitler()`ın `settings`'ten okuması
  bekleyen tek satır (G131/G132 raporları) — docs bandı kod değiştirmediği için açık.
- **NOT (frontend, kapsam dışı — G140 docs bandı dokunmadı):** `ColumnPicker.tsx:285` satır ipucu
  `turetilmis` kolonda "türetilmiş (filtrelenemez, sıralanamaz)" yazar; taraf kolonları ve
  `dava_sayisi` artık filtrelenebilir. Tek satırlık düzeltme (`k.filtrelenebilir`e bakmalı).
- **Saklama dizini volume'da:** `/app/data/rapor_ciktilari` `backend-data` volume'unda doğar, recreate'i
  atlatır; disk büyümesi ≈ 30 gün × günlük export × ~3 MB, ilk ay ölçülür. Temizlik **tembel**: yalnız
  export sonunda koşar (`temizle_sessiz`), zamanlayıcı yok; export yapılmayan dönemde eski dosya
  diskte kalır. Temizlik hatası export'u düşürmez (WARNING, `kosu_logu.py:132`, `:146`).
- **Bellek/süre ölçümü (G131 raporu, konteyner, 50.000 sentetik dava × 10 kolon, sqlite):** xlsx 2,6 MB /
  32,6 sn / tracemalloc tepe 8,4 MB; csv 7,3 MB / 2,3 sn / tepe 2,1 MB; `ru_maxrss` 75 → 89 MB.
  xlsx 50k satırda ~33 sn (openpyxl hücre maliyeti) — nginx 300 sn ve frontend 300 sn penceresi içinde.
- **Önizleme maliyeti:** `davalar` tüm kolonlarla 6 korele alt sorgu taşır (4 taraf + 2 sayaç); EXISTS
  filtreleri `case_parties(case_id)` üzerinden; otomatik önizleme her yapısal değişimde COUNT + sayfa
  sorgusu atar — büyük filtrelerde `toplam` COUNT'u ölçülmedi (K10: index ölçülmeden yazılmaz).
- **`/chat` NDJSON'u konteyner nginx'inden geçer** (`location /api`); `proxy_buffering` ayarı yok —
  `info` olayının canlı gelip gelmediği gündüz duman testinde gözle doğrulanır (G135 raporu adım 7).
- **Asistan kalitesi:** 07.09 lokal duman testi 8 istemle geçti (plan §0); nginx arkasında HTTP duman
  testi insan adımı. Şema kabulü sorun çıkarırsa `AsistanTanimi.filtreler` düz metin `deger`e
  indirgenebilir (çevirici hazır).
- **Anahtar yeniden açılınca sayfa yenilemesi gerekir:** frontend `asistan409` sayfa ömrü boyunca
  kalır (G135, bilinçli).
- **Gün sınırı saat dilimi:** DateTime kolonlarda tarih filtresi DB oturumunun saat dilimine göredir
  (prod UTC; Türkiye günü 03:00'te başlar). Tarih kısayolları tarayıcının yerel gününü ISO'ya çevirir
  (`isoGun`, `lib/reports.ts:529-532`).
- **CSV ondalık `.`:** `Decimal→float` olduğu gibi yazılır; Türkçe Excel `;` ayraçlı CSV'de `,` ondalık
  bekleyebilir — xlsx ana yol, CSV ham veri yolu; kullanıcı geri bildirimiyle karar.
- **Tarayıcıda görsel duman testi yapılmadı (G138/G139):** yerleşim/responsive kanıtı sınıf ve sıra
  düzeyinde testle; sabah gerçek ekranda kart satırının `lg` altı yatay kaydırması, Sheet genişliği,
  araç çubuğunda TemplateBar'ın sarması göz kontrolü ister (G139 raporu).
- **`lib/api.test.ts` "tek logout" testi** tam paket altında iki koşuda birer kez zaman aşımına düştü
  (G138/G139 raporları; tek başına yeşil) — hub dosyası, rapor kapsamı dışı, tekrarlarsa ayrı iş.

## 14. Log sözleşmesi

- Export üretim hatası: TEK ERROR (`routes/reports.py:308`), satır `hata` ile kalır.
- Temizlik: dosya silinemedi / temizlik atlandı → WARNING (`kosu_logu.py:132`, `:146`).
- Asistan: Gemini denemeleri `_gemini_call_with_retry` içinde WARNING; nihai başarısızlık TEK ERROR
  (`asistan.py:263-266`, `Kod:` kimliği ile); doğrulanamayan tanım WARNING (`:276`); tanımsız eylem
  düşürüldü WARNING (`:286`).
- `/chat` beklenmedik istisna: ERROR + `status:"error"` olayı (`routes/reports.py:424`).
- Katalog önbelleği log üretmez.

## 15. Testler (kanıt)

| Dosya | Kapsam |
| --- | --- |
| `backend/tests/test_g130_rapor_temeli.py` | katalog şekli (G137'de yeni alanlar eklendi), yasak kolonlar, 403 (gerçek `require_admin`), 422 yolları, op×tip kombinasyonları, `contains` kaçışı, bağlı parametre, tenant + soft-delete dört kaynakta, filtre ifadesiz türetilmiş filtrelenemez/sıralanamaz (`foy_sayisi`), sayfalama |
| `backend/tests/test_g131_rapor_export_ve_log.py` | şablon CRUD + sahiplik 403 + paylaşım, xlsx geri okuma + koşu satırı + sha256 = indirilen = saklanan, csv BOM/`;`/önek, 413, download traversal reddi, temizlik + 410, hata yolu, migrasyon kuralı bekçisi, akış (liste değil) |
| `backend/tests/test_g132_rapor_asistani.py` | anahtar varsayılan/409, 403, gövde sınırları, geçerli/geçersiz tanım akışı (taraf kolonunda `eq` → 422 → `warning`), 5 Gemini hatası → `error_kod` + TEK ERROR, yanıt hataları, prompt içeriği, kod incelemesi bekçileri (SessionLocal/`client.aio` yok), Developer API uyumlu şema, `tanim=null` + eylem → eylem düşer |
| `backend/tests/test_g137_rapor_katalog_genisleme.py` | katalog yeni alanların şekli; her kolonun `grup`u dolu ve kapalı kümede; `kontrol` tip eşlemesi; `hizli_filtreler`/`kolon_setleri` plan listeleriyle birebir; öneriler (DISTINCT, boş hariç, tenant/soft-delete, 300 kesme + `oneri_kesik`, `db=None`); taraf filtreleri (aynı adlı karşı taraf bulunmaz, `is_null`/`not_null`, rol bazlı sigortalı, silinmiş müvekkil kartı sayılmaz, ILIKE kaçışı + zehir string bağlı parametrede); `dava_sayisi` karşılaştırma; izinsiz op 7 varyant 422; türetilmişte sıralama 422; registry öz-denetimi 5 ret; önbellek 60 sn (monotonic monkeypatch + sorgu sayacı); asistan katalog metni öneri/hızlı filtre içermez ve 300+ değerle uzunluk sabit |
| `backend/tests/test_g166_rapor_bagli_kaynaklar.py` | bağlı kolon türetimi (her ilişki × hedef kolon birebir, hariç/türetilmiş atlama, ikinci derece bağ yok), öz-denetim 4 ret, katalog `iliskiler`/`bag`/kontrol/öneri (hedef tenant kuralı), kullanıcı örneği (Nisan sonrası + müvekkil telefonu; tekil + sıralı birleşim, silinmiş kart/tenant/silinmiş dava dışarıda, tarafsız dava boş hücre), ad anahtarıyla bağ, TKU tekilleşme, tarih/mantık cast, EXISTS filtre anlamı 16 varyant (is_null/not_null/in+null/tarih between+eq/mantık/iki bağ AND), müvekkilden dava + belgeden tekil dava (sıralama), 422 kuralları, asistan katalog metni ilişki satırları + prompt kuralı + aynı doğrulama, index DDL = `_ad_anahtari` derlemesi, tarih koşulu tek kaynak |
| `frontend/src/lib/reportsChat.test.ts` (G167 bölümü), `components/reports/AssistantBar.test.tsx`, `pages/ReportsPage.asistan.test.tsx`, `ReportsPage.favori.test.tsx` | teyit kartı okunur satırları (7 filtre biçimi, bağlı kolon etiketi, bilinmeyen anahtar), `tanimAyni`; tanım UYGULANMAZ → Onayla/Excel/CSV; düzeltme `mevcut_tanim` = bekleyen; sözle onay (aynı tanım + eylem) hemen yürür, sayfa reddederse beklemede kalır; tanımsız eylem bekleyen/oluşturucu tanımıyla; `indir_*` önerisi tık bekler, 413 yolu; kaynak katalogda yok → kart yine gösterir, onayda toast; Geri al → yeniden onay bekleyen; favori kartı indirme sonrası |
| `frontend/src/lib/reports.test.ts`, `reports.export.test.ts`, `reportsChat.test.ts` | tip↔op tablosu, kolon başına `oplar`, kontrol→op (§4.3) + 22 örnekli gidiş-dönüş, tarih kısayolları, `tanimGecerliMi` taraf kolonu kapısı, gövde biçimleri, hata çevirisi, `Content-Disposition`, NDJSON okuyucu, anahtar okuyucu |
| `frontend/src/components/reports/builderState.test.ts`, `QuickFilters.test.tsx`, `PreviewTable.test.tsx`, `ColumnSheet.test.tsx`, `SourceCards.test.tsx` | yuvalar/eklenen alanlar/temizle/tanımdan çözme (sıra korunur, gelişmiş çip), şerit etkileşimleri, başlıktan sıralama + "güncelleniyor…" + boş sonuç, yan panel setler/gruplar/sıra/tavan/"Temel" üretimi, kart radiogroup |
| `frontend/src/pages/ReportsPage.test.tsx`, `ReportsPage.sablon.test.tsx`, `ReportsPage.asistan.test.tsx` | dolu açılış (tek istek, varsayılan tanım), kart tıklaması (eski satırlar anında düşer), otomatik önizleme (yapısal hemen / 600 ms / odak), yan panel → önizleme, boş sonuç kısayolu, yerleşim sırası, şablon/indirme/geçmiş, asistan paneli + eylem + 409/anahtar |

Koşu sonuçları işçi raporlarından (G137/G138/G139; docs bandı yeniden koşmadı): backend `pytest`
**2670 passed / 3 skipped**, ruff + mypy temiz (G137); frontend `vitest` **798 passed / 65 dosya**,
eslint 0, `tsc -b --force` 0 (G139). Backend testleri konteynerde
(`docker compose exec -T backend python -m pytest tests/test_g13*.py`), frontend host'ta
(`npm --prefix frontend test`) koşar.

## 16. Nereye bakmalı

| Konu | Dosya |
| --- | --- |
| Sözleşme (plan, dondurulmuş §2 + ikinci tur §4 + şerhler) | [`docs/plan/raporlama-plani-2026-09-06.md`](../plan/raporlama-plani-2026-09-06.md) |
| Uçlar + katalog önbelleği | `backend/routes/reports.py` |
| Şemalar, sınırlar, tip↔op | `backend/schemas_rapor.py` |
| Kayıt defteri (kolonlar, gruplar, taraf EXISTS filtreleri, öneriler, hızlı filtre/set) | `backend/services/rapor/registry.py` |
| Motor / çıktı / koşu logu / asistan | `backend/services/rapor/{motor,cikti,kosu_logu,asistan}.py` |
| Sistem talimatı | `backend/prompts.py:449` |
| Tablolar + madde 46 | `backend/models.py:1350-1432`, `backend/database.py:1050-1064` |
| Anahtar / env | `backend/services/app_settings.py:41-79`, `backend/config/settings.py:103-112`, `.env.example:55-66` |
| Frontend tipler + kontrol↔op çevirisi + API | `frontend/src/lib/reports.ts`, `frontend/src/lib/reportsChat.ts` |
| Frontend şerit durumu ↔ tanım | `frontend/src/components/reports/builderState.ts` |
| Frontend sayfa + bileşenler | `frontend/src/pages/ReportsPage.tsx`, `frontend/src/components/reports/`, `frontend/src/components/ui/sheet.tsx` |
| Gemini devre kesici / retry / `_failed_event` | [`dis-bagimliliklar.md`](dis-bagimliliklar.md), `backend/analyzer.py:82`, `:368` |
| Görev raporları (G130-G140) | `gorevler/gorev/G130.md` … `G140.md` |
