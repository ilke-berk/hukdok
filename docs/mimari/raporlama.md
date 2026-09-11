# Raporlama modülü — kayıt defteri → sohbet öncelikli ekran (asistan → tanım şeridi → tablo) → Excel/CSV export + koşu logu

> **Son doğrulama: 2026-09-11 · c839fdb** (G177 — sohbet öncelikli ekran G173-G176; kod HEAD'i, bu doküman
> commit'i onun üstündedir). Bu turda koddan YENİDEN okunan bölümler: giriş şeması, §1, §7 (asistan davranışı),
> §8 (tamamı), §9, §12, §13, §15, §16 — buradaki satır numaraları c839fdb'ye aittir. Önceki turlar: G140 ·
> a36e98f (2026-09-07; §2-§6, §10, §11, §14 satır numaraları o commit'e ait), G166 eki (2026-09-10; §2.4
> satır numarasız, işlev adları koddan). Her uç adı, env, tablo adı, alan ve limit koddan okunarak
> yazılmıştır. Kod ile çelişirse kod haklıdır — bu dosyayı düzelt. Plan/sözleşme dosyası
> [`docs/plan/raporlama-plani-2026-09-06.md`](../plan/raporlama-plani-2026-09-06.md);
> planla kod arasındaki farklar §12'de (ilk tur §2 farkları F1-F10, ikinci tur §4 farkları F11-F22,
> sohbet öncelikli tur F23-F28) ve planın kendisinde "uygulamada değişti" şerhiyle.

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
taraf bağlantılı dört kolon EXISTS alt sorgusuyla süzülür.

**Sohbet öncelikli tur (G173-G176, 2026-09-11, kullanıcı kararı "arayüz deli gibi sadeleşsin"):** manuel
kurucu (kaynak kartları, filtre şeridi, "Kolonlar (N)" yan paneli) KALKTI; sohbet tek giriş noktasıdır. Manuelin
üç gücü sohbetin ALTINDA korunur: (1) şeffaflık — uygulanan tanım her an **tanım şeridinde** (`TanimSeridi`,
G173) görünür; (2) düzeltme kanalı — şeritteki her çip yerinde düzenlenir (kaynak rozeti, kolon ×/"+ Kolon",
filtre çipi → popover'da aynı `FilterControl`, "+ Filtre", sıralama ×, Temizle); (3) değer listeleri — 300 önerili
combobox çip düzenlemesinde açılır, "hangi mahkemeler var" sorusu Gemini'ye gitmeden katalogdan liste balonu olur
(G174). Asistanın tanımı **düğme beklemeden uygulanır** (G174; G167 teyit döngüsü geri alındı), prompt buna göre
"onay sorma" der (G176). Anahtar kapalıyken sayfa boş kalmaz: bilgi kartı + şerit yedek kurucudur (G175).
**Sunucu sözleşmesi (`RaporTanimi`, uç adları, olaylar) bu turda da DEĞİŞMEDİ** — backend'de yalnız prompt
cümleleri değişti (`prompts.py`, G176); kontrol↔op çevirisi, `builderState`, katalog aynen.

```
Rapor sekmesi (frontend/src/pages/ReportsPage.tsx:740-852 — G175 yerleşimi: sohbet → şerit → tablo)
   AssistantBar.tsx (tam genişlik, örnek istemler, inline konuşma; :742-755)
     ‖ anahtar kapalı / 409 → yerinde bilgi kartı `asistan-kapali-karti` (:756-770), şerit + tablo çalışır
   → TanimSeridi.tsx (:773-782): Davalar ▾ · kolon çipleri · + Kolon · filtre çipleri · + Filtre · ↑/↓ sıralama · Temizle
   → sayaç satırı `sayac-satiri` (:785-821): "N kayıt" · TemplateBar (kompakt, "…" menüsü) · ExportButtons (Excel/CSV)
   → [FavoritePrompt (koşullu, :824-832)] → PreviewTable.tsx (:835-851; başlıktan sıralama; "güncelleniyor…")
   │ GET /api/reports/catalog ──▶ registry.katalog()  (kaynaklar · kolonlar · gruplar · kontroller · seçenek/öneri ·
   │                               hızlı filtreler · kolon setleri · ilişkiler · limitler) — tenant anahtarlı 60 sn önbellek
   │ POST /api/reports/preview ─▶ motor.onizle()      (sayfalı, LOGLANMAZ; ekran her geçerli taslak değişiminde ister)
   │ POST /api/reports/export ──▶ COUNT → 413? → report_runs satırı → dosya <RAPOR_CIKTI_DIZINI>/<run_id>-<slug>.<ext>
   │                               → sha256/boyut → tembel temizlik → aynı dosya FileResponse (X-Rapor-Kosu-Id)
   │ GET  /api/reports/runs ────▶ tüm yöneticilerin koşuları;  /runs/{id}/download → saklanan dosya (410 = temizlendi)
   │ /api/reports/templates ────▶ favori şablonlar (kendi + paylaşımlı; soft delete)
   │
Asistan satırı (AssistantBar.tsx, G143 → G174) — admin anahtarı `rapor_asistani` AÇIKKEN; ekranın BİRİNCİL yolu
   │ POST /api/reports/chat ────▶ NDJSON: info → [warning] → complete{cevap, tanim, eylem} | failed{error_ozet, error_kod}
   │                               Gemini JSON şemalı tek atış; `tanim` sunucuda AYNI doğrulamadan geçer (K6)
   │ G174 OTOMATİK UYGULAMA: `complete.tanim` → `degerEsle` temizse DÜĞMESİZ `onTanimUygula(tanim, eylem ?? "onizle")`
   │   (AssistantBar.tsx:244-263); kart KISA ("Uygulandı · Davalar · 7 kolon · 2 filtre" + Excel/CSV + Geri al).
   │   Kart yalnız BEKLER: metin filtre değeri katalog önerisine uymadı (sorun satırı + ≤5 aday çipi + "Yine de uygula")
   │   ya da sayfa reddetti / Geri al ("Onayla ve uygula"); bekleyen tanım sonraki mesajlarda `mevcut_tanim` olur.
   │ G174 LİSTE BALONU (Gemini'siz): "hangi mahkemeler var" → `listeNiyeti` → DegerListesi (:214-225); tık → `onFiltreEkle`
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
| Asistan | `backend/services/rapor/asistan.py` + `backend/prompts.py:449` | Gemini çağrısı, katalog metni (yeni katalog alanları GÖMÜLMEZ), asistan tanımı → `RaporTanimi` çevirisi; G176 prompt kuralları "UYGULAMA" / "YAKLAŞIK AD" / "LİSTE SORUSU" (`prompts.py:522-535`) |
| Uçlar | `backend/routes/reports.py` | `/api/reports/*` (prefix `:62`); katalog önbelleği (`:81-109`); `api.py:487`, `:509` ile kayıtlı — `/api` altında olduğu için `nginx.conf:77` `location /api` yeter, nginx istisnası YOK |
| Tablolar | `backend/models.py:1350-1432`, `backend/database.py:1050-1064` | `ReportTemplate`, `ReportRun`, migrasyon madde 46 — G137 migrasyon EKLEMEDİ (hepsi sorgu katmanı) |
| Anahtar / env | `backend/services/app_settings.py:66-79`, `backend/config/settings.py:103-112` | `rapor_asistani` anahtarı; dört env |
| Frontend — saf katman | `frontend/src/lib/reports.ts`, `frontend/src/components/reports/builderState.ts`, `frontend/src/lib/reportsChat.ts` | Katalog tipleri (`KatalogKolon :72`, `KatalogIliski :134`, `KatalogVeriKaynagi :141`, `Katalog :159`), tip↔op ikizi `OP_BY_TIP` (`:255-261`), kontrol↔op çevirisi (`kontroldenFiltre :489-534`, `filtredenKontrol :544`, `gelismisOplar :615-619`), `tanimGecerliMi` (`:397-414`), tarih kısayolları (`:777-811`), HTTP; şerit durumu ↔ `RaporTanimi` (`builderState.ts`; G173 ek yardımcıları `kolonEkle`/`kolonKaldir`/`filtreEkle`/`seritteBosOge` `:176-209`); asistan istemci mantığı (`reportsChat.ts`: NDJSON okuyucu, `onayNiyeti`, `kaydetNiyeti`, G174 `degerEsle`/`degerAdaylari`/`filtreDegeriDegistir`/`listeNiyeti` `:455-670`) |
| Frontend — ekran | `frontend/src/pages/ReportsPage.tsx`, `frontend/src/components/reports/{AssistantBar,AssistantThread,AssistantMessage,DegerListesi,TanimSeridi,FilterControl,FilterChip,FieldPicker,SearchBox,ChipSelect,ToggleFilter,PreviewTable,TemplateBar,ExportButtons,FavoritePrompt,SaveTemplateDialog,RunsTable}.tsx`, `ui.ts` (`ls frontend/src/components/reports`, c839fdb) | Route `/reports` (`App.tsx:101`, `ProtectedAdminRoute`), Sidebar "Raporlar" (`components/shell/Sidebar.tsx:67`, yalnız yönetici), `/api/reports/` uzun zaman aşımı listesinde (`lib/api.ts:74`, 300 sn `:58`). **KALDIRILDI (G175):** `SourceCards.tsx` (+test), `QuickFilters.tsx` (+test), `ColumnSheet.tsx` (+test), `ColumnPicker.tsx`, `components/ui/sheet.tsx` (başka kullanıcısı yoktu, G175 raporu `grep` kanıtı). Daha önce: `ReportBuilder.tsx`/`FilterRow.tsx` (G138/G139), `AssistantPanel.tsx` → `AssistantBar` (G143) |

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

Gövde `SohbetIstegi` (`schemas_rapor.py:226`): `mesajlar[{rol:"user"|"assistant", icerik}]`
1-20 adet, içerik 1-4000 karakter, **son mesaj `user`** olmalı; `mevcut_tanim: RaporTanimi|null`.
Kapı sırası: 403 (yönetici) → 409 (anahtar, gövde ayrıştırılmadan, `routes/reports.py:412-413`) → 422 (gövde).

Akış (`services/rapor/asistan.py:274-334` `sohbet`):

```
{"status":"info","message":"Rapor tanımı hazırlanıyor"}
{"status":"warning","message":"Asistanın ürettiği tanım doğrulanamadı (<alan>: <sebep>); tanım olmadan devam ediliyor."}   # isteğe bağlı
{"status":"complete","cevap":"<Türkçe metin>","tanim":RaporTanimi|null,"eylem":"onizle"|"indir_xlsx"|"indir_csv"|null}
{"status":"failed","error_ozet":"... (Kod: xxxxxxxx)","error_kod":"gemini_saturated|gemini_blocked|gemini_truncated|schema_invalid|analysis_error"}
```

`complete`/`failed` SON olaydır; `failed` `analyzer._failed_event` ile üretilir (`analyzer.py:368`),
etiket sınıflandırması `_hata_esle` (`asistan.py:254`; 429/5xx/devre kesici → `gemini_saturated`
`analyzer._api_error_kod` `analyzer.py:1427` ile). Route'un beklenmedik istisnası `{"status":"error","message":"Beklenmedik
hata (Kod: ...)"}` verir ve sözleşme dışıdır (`routes/reports.py:420-426`, `/process` ile aynı desen).

- **Gemini çağrısı YALNIZ `analyzer._gemini_call_with_retry`** (`analyzer.py:82`; devre kesici +
  retry + health sayacı tek yerde) — `asistan.py:293`; `analyzer` tembel import edilir çünkü modül
  import'u `GEMINI_MODEL_NAME` ister ve CI/lokal testler bu env olmadan `routes.reports`'u yükler
  (`_analyzer`, `:79`). `config`: `system_instruction` + `response_mime_type="application/json"` +
  `response_schema=RaporAsistanCevabi` (`:287-291`).
- **Model (K9):** `get_rapor_model()` (`:67`) → `GEMINI_RAPOR_MODEL` boşsa
  `case_intake_analyzer.get_intake_model()` (`case_intake_analyzer.py:60`, `GEMINI_INTAKE_MODEL`).
- **Sistem talimatı** (`prompts.py:449` `get_rapor_asistani_instruction`; `asistan._talimat :247`): katalog
  `katalog_metni()` ile registry'den üretilir (`asistan.py:106`; `_kolon_satiri :89`, ilişki başına tek satır
  `_iliski_satiri :126`: `## kaynak — etiket: açıklama`, varsayılan kolonlar, `anahtar · etiket · tip[ ·
  seçenek|seçenek][ · türetilmiş (filtre yalnız: contains|is_null|not_null; sıralama yok)]`;
  sabit seçenekler çekirdekten, DB'siz), elle kolon listesi YOK. **Veriden gelen seçenek listeleri (2026-09-12):**
  rota `/chat` 60 sn önbellekli tenant kataloğunu `run_in_threadpool` ile alır, `asistan.veri_secenekleri_katalogdan`
  yalnız `secenek_kaynagi == "veri"` + bağsız kolonları `(kaynak, kolon) → seçenekler` olarak çıkarır,
  `katalog_metni(veri_secenekleri)` kolon satırına `· seçenekler: a|b|c` ekler (8 bağsız kolon; katalog metni 11,3k → 15,8k karakter, lokal ölçüm 12.09;
  argümansız çağrı eski metinle birebir). Sebep: "konusu kadın doğum" isteği `subject contains "kadın doğum"`
  olmuş, gerçek değer `sub_type = "Kadın Hastalıkları ve Doğum"` → 0 satır; model listeyi görmüyordu. K6 korunur:
  bu listeler her istemciye zaten katalogla gider, satır verisi değil; asistan modülü DB'ye yine dokunmaz.
  **Varsayılan kolon taşınması (12.09):** sayfa dolu açıldığı için `mevcut_tanim` hep gidiyor, model her isteği
  "mevcut tanımı değiştir" sayıp istenen kolonları varsayılanların ÜSTÜNE ekliyordu. İki katman: `ReportsPage`
  `mevcutVarsayilan` (tanım kaynağın `kaynakIcinBaslangic` tanımına `tanimAyni` ile eşitse) → `AssistantBar`
  sunucuya `mevcut_tanim: null` yollar (bekleyen tanım varsa o gider; yerel yollar `mevcutTanim`i kullanmaya devam
  eder); prompt "KOLON SEÇİMİ" iki dal — (a) kolon sayıldıysa YALNIZ onlar, (b) sayılmadıysa varsayılan + istenenler —
  ve "sıfırdan üretme" kuralı yalnız değişiklik istekleri için, yeni liste isteği sıfırdan kurulur.
  Prompt kuralları: "seçenekler:" yazan kolonda değer listeden AYNEN + `eq`/`in`, yaklaşık ifade → en yakın
  seçenek + cevapta söyle; "KOLON SEÇİMİ DEĞERE GÖRE" (değer bir kolonun listesine benziyorsa o kolon, adı
  benzeyen serbest metin kolonu değil); "YAKLAŞIK AD" `contains` kuralı yalnız listesiz metin kolonunda. **G137 katalog alanları
  (`grup`, `kontrol`, `oplar`, `oneriler`, `hizli_filtreler`, `kolon_setleri`) BİLEREK gömülmez**
  (öneriler 300'e kadar değer = prompt gürültüsü); taraf kolonları ve bağlı kolon ilişki satırları doğal olarak
  girer. Bugünün tarihi göreli ifadeler için; `mevcut_tanim` JSON olarak prompt SONUNA gömülür ("sıfırdan üretme,
  değiştir", `prompts.py:519-521`, `:550-555`). 07.09 duman testi sonrası kural: kaynak belli ama ayrıntı yoksa
  SORU SORMA, varsayılan tanım + `eylem=onizle`; yalnız kaynak/zorunlu bilgi eksikse `tanim=null` + tek soru
  (`prompts.py:513-518`). **G176 (2026-09-11) — üç kural cümlesi, gerisi aynen:** (1) "TEYİT DÖNGÜSÜ" maddesi
  → **"UYGULAMA"** (`:522-528`): "hazırladığın tanım ekranda hemen uygulanır ve düzenlenebilir bir şeritte
  görünür; cevabında ne yaptığını 1-2 cümleyle söyle, onay SORMA ('Doğru mu, uygulayayım mı?' gibi soru YOK).
  Belirsizlikte (hangi kolon, hangi tarih alanı) tanim=null ve TEK soru"; sözlü onayda ("tamam/evet/doğru/uygula/
  onayla/göster") tanımı AYNEN döndür + `onizle`, "indir/Excel/CSV" → aynen + indirme eylemi (G167 `onayNiyeti`
  yolu için kalır), düzeltmede ("telefonu da ekle") mevcut tanımı o kadar değiştir, gerisine dokunma (sondaki
  "ve yine onay iste" kalktı). (2) **"YAKLAŞIK AD"** (`:529-532`): mahkeme/il/kurum/taraf adı yaklaşık ya da
  kısaltılmış yazılırsa ("Ankara 3. Ticaret") metin kolonunda `eq` DEĞİL `contains` + en ayırt edici parça; tam
  liste değerini bilmiyorsan uydurma; kapalı liste (seçenekli) kolonlarında "aynen kopyala" kuralı (`:505-506`)
  geçerli. (3) **"LİSTE SORUSU"** (`:533-535`): "hangi mahkemeler var", "il seçenekleri neler" → listeyi SEN
  VEREMEZSİN (veriyi görmüyorsun, K6): `tanim=null`, `eylem=null`; cevapta listeyi ekranda ilgili filtre çipine
  tıklayarak ya da "hangi <alan>lar var" yazarak görebileceğini söyle — frontend `listeNiyeti` kaçırırsa güvenlik
  ağı. Bekçi testler `test_g132_rapor_asistani.py::test_prompt_g176_*` (G176 raporu: eski prompt'ta kırmızı).
- **Gemini şeması `RaporTanimi` DEĞİL** (`schemas_rapor.py:199-204` şerhi): `extra="forbid"`
  `additionalProperties:false` üretir (google-genai 2.11.0 Developer API modunda desteklenmez) ve
  `Filtre.deger: Any` tipsiz özellik olur. Bu yüzden `AsistanTanimi` filtre değerini METİN (`deger`)
  ya da metin listesi (`degerler`, `in`/`between`) taşır; sunucu kolon tipine göre çevirir
  (`asistan_tanimini_cevir`, `asistan.py:200`: mantık `true/false/evet/hayır`, sayı/para `Decimal`,
  tarih strip) ve sonucu **aynı** `RaporTanimi` + `motor.tanimi_dogrula` yolundan geçirir
  (`tanimi_dogrula`, `:220` — K6 tek doğrulama; taraf kolonunda `eq` gibi alt küme dışı op da
  burada 422'ye düşer). Geçmezse `warning` + `tanim=null` + `eylem=null` ile yine `complete`
  (`:306-317`, `:334`); geçersiz tanım istemciye hiçbir zaman `tanim` olarak gitmez.
- **Sunucu koruması (07.09 duman testi):** model `tanim=null` + `eylem` döndürürse eylem düşürülür
  (WARNING, `:318-323`) — istemci eylemi mevcut tanım üzerinde yürütmesin. Her cevapta INFO teşhis izi
  (`:326-333`: eylem, kaynak, kolon sayısı, filtre `alan:op` listesi, `mevcut_ile_ayni`, son mesajın ilk 60
  karakteri — değer yok; G167 dersi).
- **Sohbet geçmişi sunucuda saklanmaz** (K6): istemci `mesajlar`ı taşır; `icerikleri_kur` (`:234`) son 20
  mesajı `user`/`model` rolüne eşler, baştaki asistan mesajlarını atar (Gemini dizisi kullanıcıyla
  başlar). Frontend geçmişi `AssistantBar` state'inde tutar (`kayitlar`, `AssistantBar.tsx:74`), sayfa
  yenilenince sıfırlanır (`lib/reportsChat.ts:87` `gecmisiKirp` en yeni 20; `sohbetGecmisi :275-280` hata ve
  boş kayıtları düşürür, yerel satırlar geçmişe GİRER).
- **Asistan DB'ye dokunmaz:** `asistan.py` oturum fabrikası import etmez, satır görmez; `tenant_id`
  yalnız ERROR log bağlamıdır — tanım tenant filtresini `/preview`/`/export`'ta alır (`:279-280`).
- **Eylem (K7):** `eylem` yalnız öneridir; indirme frontend'in `/export` çağrısıyla `kaynak:"asistan"`
  olarak yapılır (`ReportsPage.tsx:671-679`) → koşu logunda "Asistan" rozeti (`RunsTable.tsx:34`,
  `lib/reports.ts:1121` `KAYNAK_ETIKETLERI`). Uygulanan tanım `eylem=null` olsa da otomatik önizlenir;
  `eylem:"onizle"` aynı tanımda bile yeniden ister (`asistanTanimiUygula`, `ReportsPage.tsx:646-690`, §8.4).
- **Otomatik uygulama (G174, 2026-09-11 — G167 teyit döngüsü GERİ ALINDI, kullanıcının 11.09 sadeleşme
  kararıyla):** G167'nin "kart + Onayla" döngüsü (10.09 bulgusu: "kart yalnız sayı gösteriyor, teyit/düzeltme/onay
  yok") tanım şeridi (G173) her an ekranda olduğu için gereksiz sürtünme oldu. Kural (`AssistantBar.tsx` `gonder`
  `complete` işleyicisi, `:244-270`): `sonuc.tanim` varsa — sözle onay (`Boolean(eylem) && tanimAyni(tanim,
  bekleyenTanim)`, `:246`) ya da `degerEsle(tanim, katalog).temiz` (`:247-248`) → **düğme beklemeden**
  `onTanimUygula(tanim, eylem ?? "onizle")` (`:250-252`; G143 davranışına dönüş). Başarıda kayıt `uygulandi=true`,
  "Geri al" kimliği (`uygulandiIsaretle :111-115`), `bekleyenTanim=null`, `sonucBeklenen` (G168 "N kayıt bulundu"
  satırı aynen, `:99-108`); sayfa reddederse (`false`: kaynak katalogda yok) kart bekler, `bekleyenTanim` = o tanım
  (`:258-261`). Temiz değilse kayıt `sorunlar` ile bekleyen olur (`:264-269`). Kart iki hâlde
  (`AssistantMessage.tsx:31-41`): UYGULANMIŞ → KISA (`data-kisa`, tek satır "Uygulandı · <kaynak> · N kolon · M
  filtre" + Excel/CSV + Geri al, `:149-174`; ayrıntı şeritte); BEKLEYEN → okunur `<dl>` (`tanimAyrintisi`,
  `reportsChat.ts:341-354`) + sorun satırları + "Onayla ve uygula" (yalnız sorunsuz bekleyen kartta, `:254-263`).
  Bekleyen tanım varken sonraki mesajlar sunucuya `mevcut_tanim` olarak onu taşır (`AssistantBar.tsx:234`);
  `tanim=null` + eylem → bekleyen (yoksa oluşturucudaki) tanımla eylem (`:271-285`); soru → yalnız balon (`:286`).
  "Geri al" (`geriAl :369-378`) kartı yeniden bekleyen hâle döndürür. `indir_*` eylemiyle gelen temiz tanım doğrudan
  indirilir (K7 aynı yol). Sayfa tarafı DEĞİŞMEDİ: `onTanimUygula` = `asistanTanimiUygula` (§8.4),
  `oncekiTaslak` + "Geri al" G143'ten beri duruyordu.
- **Değer eşleme — Gemini'siz, K6 korunur (G174, `lib/reportsChat.ts:455-568`):** öneriler zaten katalogla istemcide;
  asistan veri görmez, eşleme arayüzde çözülür. `degerEsle(tanim, katalog)` (`:530-550`) yalnız `contains`/`eq` +
  string değer + kolonun `oneriler` listesi varsa bakar: **`contains` için normalize değer en az bir önerinin ALT
  DİZESİ** ("Ankara" → "Ankara 3. Asliye Ticaret" temiz), **`eq` için birebir**; `in`/`between`/`ne`/`is_null`/
  tarih/sayı/mantık, öneri listesi olmayan/boş kolon, katalogda olmayan kolon/kaynak, `katalog=null` daima temiz.
  Normalize `degerAnahtari` (`:471-478`): trim + `toLocaleLowerCase("tr-TR")` + NFD birleşik işaret temizliği
  (İ/i̇ U+0307/ş/ç/ğ katlanır) + iç boşluk tekilleştirme. Tutmayan filtre `sorunlar`a `{indeks, alan, deger,
  adaylar, kesik}` (`DegerSorunu :484-494`) ile düşer; **aday ≤5** (`DEGER_ADAY_MAX=5`, `:461`; `degerAdaylari
  :505-521`: kelime kesişimi çok→az → ortak önek → katalog sırası; kesişimsiz ve <2 karakter ortak önekli öneri
  aday değil); `kesik` = kolonun `oneri_kesik` (300 tavanı — aranan değer listede olmayabilir, kart notu
  `AssistantMessage.tsx:227-231`). Aday çipi (`deger-adayi`, `:210-226`) → `onAdaySec` (`AssistantBar.tsx:332-340`):
  değer katalog yazımıyla `filtreDegeriDegistir` (`reportsChat.ts:556-568`; **op: kolonda `eq` izinliyse `eq`,
  yoksa `contains`**, kolon bilinmiyorsa op kalır) ile yazılır, başka sorun kalmadıysa tanım o an uygulanır
  (`kartiUygula :137-152`), kaldıysa kart kalan adaylarla bekler (iki sorunlu filtrede sırayla). "Yine de uygula"
  (`yine-de-uygula`, `AssistantMessage.tsx:234-241`; `onYineDeUygula :343-346`) ham tanımı `kayit.eylem ??
  "onizle"` ile uygular.
- **Liste balonu — "hangi X'ler var", Gemini'siz (G174):** `gonder` sırası: şablon kaydı (`kaydetNiyeti`) → yerel
  onay (`onayNiyeti`, yalnız bekleyen tanım varken) → **liste niyeti** → Gemini (`AssistantBar.tsx:164-227`).
  `listeNiyeti(metin, kaynak)` (`reportsChat.ts:642-670`; kaynak = bekleyen tanımınki, yoksa oluşturucudaki,
  `:216`): ≤12 kelime; eylem fiili ("kaldır, çıkar, sil, ekle, listele, sırala, değiştir, güncelle, indir, kaydet,
  uygula, filtrele, oluştur, yap, koy" — `LISTE_EYLEM_KELIMELERI :576-579`) geçen mesaj liste sorusu DEĞİL;
  kalıplar "hangi … (var/mevcut/kayıtlı)", "… listesi", "… seçenekleri (neler)", "… değerleri", "… neler",
  "… var mı" (≤4 kelime) (`:647-651`). Kolon çözümü yalnız `oneriler` ya da `secenekler` taşıyan filtrelenebilir
  kolonlarda (`:657-658`): etiket (bağlı kolonda "·" sonrası parça) + hızlı filtre etiketi + anahtar + eşanlamlı
  grupları (il/şehir/city, mahkeme/court, durum/status, avukat/lawyer, tür/type/tip, aşama/stage, … `:588-604`),
  çoğul/iyelik eki düşümü ("iller"→"il", `sozcukBicimleri :610-615`), ≥3 harfli ortak gövde (`bicimUyar
  :618-622`). En yüksek puanı paylaşanlar döner: 1 → `DegerListesi` balonu (`listeKaydi :123-131`), >1 → "Hangisi?"
  çipleri (`kolon-adayi`, `AssistantMessage.tsx:132-147`; tık → o kolonun balonu), eşleşme yoksa `null` → mesaj
  Gemini'ye gider (prompt "LİSTE SORUSU" güvenlik ağı). `DegerListesi.tsx` (`:22-113`): `oneriler` (yoksa
  `secenekler`), arama kutusu `degerAnahtari` ile süzer, en çok **300** satır (`DEGER_LISTESI_MAX`,
  `reportsChat.ts:464`), `secenek_sayilari` varsa `SayiRozeti`, `oneri_kesik`/300 aşımı notu; `role="listbox"` +
  `role="option"` düğmeleri (Tab girer, ok/Home/End gezer, Enter/boşluk seçer). Değer tıkı (`onListeSec`,
  `AssistantBar.tsx:352-361`): **`onFiltreEkle(alan, hamDeğer)`** verilmişse (G175 bağlar, `ReportsPage.tsx:754`)
  mevcut tanıma filtre + yerel satır "<Etiket> · <değer> filtre olarak eklendi."; verilmezse girdiye
  `<Etiket> "<değer>" olanlar` yazılır ve odaklanır. Sayfadaki `onFiltreEkle` (`ReportsPage.tsx:426-457`): op
  kolonda `eq` varsa `eq`, yoksa `contains`; kontrol `filtredenKontrol` ile doğal çipe çözülür (liste → çoklu seçim,
  metin → tam eşitlik); aynı alanın DOLU çoklu seçimi varsa değer ona eklenir (`in` — "şunlardan biri", boş sonuç
  tuzağı önlendi), başka dolu kontrol varsa değeri değişir, yoksa `filtreEkle` + `seritteBosOge` ile boş yuva/
  eklenen öğe doldurulur (yuvaya oturmazsa gelişmiş çip — filtre kaybolmaz); `durumDegisti` → önizleme hemen;
  toast "Filtre eklendi · <Kolon>: <değer>"; filtre tavanı / filtrelenemez alan → hata toast'ı. Örnek istemler:
  kaynak başına üçüncü çip "Hangi mahkemeler/şehirler/belge türleri/aşamalar var?" (`reportsChat.ts:214-235`).
- **Yerel onay (G167 ek, 10.09 prod dersi — G174'te KORUNDU, yalnız bekleyen tanım varken anlamlı):** Deploy #22
  sonrası kullanıcı "tamam" yazdı, kart yeniden onay istedi — sunucuda tekrar oynatıldığında Gemini tanımı aynen
  döndürdü, ama LLM çıktısı her turda birebir garanti değil (`tanimAyni` düşer). Bu yüzden kısa onay/indirme
  mesajları ARAYÜZDE tanınır (`reportsChat.onayNiyeti :389-404`: yalnız onay/indirme/dolgu kelimelerinden oluşan
  ≤8 kelimelik mesaj → `onizle` | `indir_xlsx` | `indir_csv`; "tamam ama telefonu ekle" gibi başka kelime içeren
  mesaj → `null`, Gemini'ye gider) ve bekleyen tanım Gemini'ye gitmeden uygulanır/indirilir
  (`AssistantBar.tsx:186-212`); sohbete `yerel: true` bir asistan satırı düşer ("Onaylandı, …"), geçmişe de girer.
  Sözle onayın Gemini yolu (aynen dönen tanım + eylem) onay dışı cümleler için kalır. Otomatik uygulamadan sonra
  bekleyen tanım yoksa "tamam" normal yoldan Gemini'ye gider (prompt: tanımı aynen döndür + `onizle`).
- **Sonuç odaklı sohbet + sohbetten şablon kaydı + sınır açıklaması (G168, 2026-09-10 gece):**
  (1) Uygulama (otomatik / Onayla / aday / yerel onay / sözle onay; indirmede değil, `sonucBekle :106-108`)
  sonrası sayfanın önizleme sonucu (`onizlemeSonucu = {tanim: sonTanim, toplam: cevap.toplam}`,
  `ReportsPage.tsx:752`) uygulanan tanıma aitse (`tanimAyni`) sohbete yerel satır düşer: `sonucSatiri`
  (`reportsChat.ts:435-442`) — "3.216 kayıt bulundu." ya da boşta filtre satırları + "hangisini kaldırayım
  ya da genişleteyim?" (asistan veriyi görmez, K6 korunur — sayı önizlemeden). Bir kez, yalnız o tanım için
  (`sonucBeklenen`). (2) `kaydetNiyeti` (`:417-427`): "bunu haftalık rapor olarak kaydet" / "X adıyla kaydet" /
  "kaydet" / "favorilere ekle" → sayfanın `asistanSablonKaydet`i (`ReportsPage.tsx:696-715`; `POST /templates`,
  `favoriEkle` ile aynı gövde; ad yoksa `sablonAdiOner`); bekleyen (yoksa oluşturucudaki) tanım kaydedilir,
  UYGULANMAZ; Gemini'ye gitmez; yerel satır "'…' adıyla şablonlara kaydedildi". "telefonu kaydet" gibi başka
  kelimeli mesaj eşleşmez. (3) Prompt: reddederken sebep + alternatif (çoklu bağ kolonu birleşik metin →
  sıralanamaz, ana kaynak kolonuyla sırala; bağ tek kademe → satırı belge yapıp `dava.*`/`muvekkil.*`;
  `prompts.py:487-496`).

## 8. Kullanıcı akışı — Rapor sekmesi (G173-G175 sohbet öncelikli; temel G138/G139)

Ekran durumu tek doğruluk kaynağı `OlusturucuDurumu = {veri_kaynagi, kolonlar[], serit[], siralama[]}`
(`builderState.ts:29-34`); sunucu tanımı her render'da `tanimOlustur` ile türetilir (`:158-165`,
`ReportsPage.tsx:271`) — boş kontroller tanıma GİRMEZ, §2.1 JSON'u değişmez. Tek durum yazma yolu
`durumDegisti` (`ReportsPage.tsx:372-386`). Şerit semantiği (`SeritOgesi`, `:10-22`) DEĞİŞMEDİ: kaynağın
`hizli_filtreler` yuvaları boş kontrol olarak açılır (`hizliYuvalar :45-66`; × ile boşa döner, durumda kalır),
"+ Filtre" ile eklenen alan × ile şeritten kalkar; boş kontrol çip olarak GÖRÜNMEZ.

### 8.1 Yerleşim (`ReportsPage.tsx:740-852`, G175)

Rapor sekmesi üç bloktur (`section[data-testid=rapor-sekmesi]`, `grid gap-5`, max-w cap YOK — tam genişlik kuralı):

1. **Asistan satırı** — `AssistantBar` (`:742-755`; §7) ya da anahtar kapalı/409'da yerinde tek satırlık bilgi
   kartı `asistan-kapali-karti` (`:756-770`, `role="note"`, `title=ASISTAN_KAPALI_MESAJI`: "Rapor asistanı kapalı —
   yönetici panelinden `rapor_asistani` anahtarını açın. Tanım şeridi ve tablo çalışmaya devam eder."); anahtar
   okunana dek iskelet (`yukleniyor`, `asistanAnahtari === null`). Karar `asistanSatiriGorunur` (`:731`).
   `AssistantBar`'a bağlananlar: `onTanimUygula=asistanTanimiUygula`, `onizlemeSonucu`, `onSablonKaydet`,
   **`onFiltreEkle`** (`:754`, G175 — liste balonu tıkı; §7).
2. **Tanım şeridi** — `TanimSeridi` (`:773-782`; §8.2): `katalog`, `durum`, `onChange=durumDegisti`,
   `onHemen=hemenOnizle`, `onKaynakSec` (`:407-411`: aynı kaynak no-op; farklı → `kaynakIcinBaslangic(yeni)`
   `builderState.ts:69-77`, onay diyaloğu YOK — kart tıklaması gibi; şablon/koşu yüklemesi `tanimiYukle :465-482`
   onayı aynen), `bugun` (yerel gün `YYYY-MM-DD`, `yerelGun :59-63`; sayfa ömrü boyunca sabit `:134`).
3. **Sayaç satırı** `sayac-satiri` (`:785-821`, `flex-wrap`, `lg` altında sarar): `kayit-sayaci` (`:786-792`) —
   son BAŞARILI önizlemeden "N kayıt" (tr-TR binlik), yüklenirken "sayılıyor…", hata varken "— kayıt" ·
   `TemplateBar` kompakt (`TemplateBar.tsx:65-`, `sablon-cubugu :73`: etiket + seçim (açıklama `title`da) +
   paylaşım rozeti + "☆ Favorilere ekle"/"★ Kayıtlı: <ad>" (`:101`, `:113`) + Yükle + Kaydet + yalnız sahibinde
   `sablon-menu` "…" Radix `DropdownMenu` (`:143`; Güncelle `data-islem="guncelle" :158`, Sil `:168`); davranış/
   prop sözleşmesi aynı) · `ExportButtons` (Excel/CSV; `exportSablonId :280`, `onizlenenSatirSayisi :282`).
   Altında koşullu `FavoritePrompt` (`:824-832`, G144 aynen).
4. **Önizleme** — `PreviewTable` ince çerçeveli düz `div` içinde (`:835-851`; `HairlineCard` sarmalı yok; §8.5).

Kaynak değişince `durumDegisti` (`:376-384`): `reqIdRef` artar (süren istek yok sayılır), zamanlayıcı durur,
`cevap/hata/sonTanim` ANINDA `null` → ekranda hiçbir zaman başka kaynağın satırı kalmaz; efekt yeni kaynağın
varsayılan tanımını hemen ister. **Dolu açılış:** katalog gelince ilk kaynak (Davalar) + varsayılan kolonlar
(`katalogYukle :190-208`, `:196-200`) → otomatik önizleme efekti ilk isteği kendiliğinden atar (§8.4).
`HairlineCard` yalnız "katalog yükleniyor" (`:736-738`) ve Şablonlar/İndirme geçmişi sekmelerinde kaldı.
Sayfa başlığı ipucu (`h1 title`, `:862`): "Ne istediğinizi asistana yazın ya da tanım şeridinden düzenleyin…".

### 8.2 Tanım şeridi (`TanimSeridi.tsx`, G173)

Kontrollü bileşen (iç kopya yok; yalnız "hangi popover açık" yereldir, `acikId :103`,
`kolonSeciciAcik :104`): `<div role="group" aria-label="Rapor tanımı" data-testid="tanim-seridi">`, `flex
flex-wrap` (`:197`; sarar, sayfa yatay kaydırmaz), açılır paneller `max-w-[min(90vw,28rem)]` (`PANEL_CLS :58`).
Prop sözleşmesi (`:17-31`, "G175 sayfaya bunu bağlar — DEĞİŞTİRME"):

```ts
interface TanimSeridiProps {
  katalog: Katalog; durum: OlusturucuDurumu;
  onChange: (durum: OlusturucuDurumu, gecikmeli?: boolean) => void;  // sayfa durumDegisti
  onHemen: () => void;                                                // odak çıkışı → önizleme hemen
  onKaynakSec: (anahtar: string) => void;                             // farklı kaynak seçilince
  bugun?: string;                                                     // YYYY-MM-DD, tarih kısayolları
  salt?: boolean;                                                     // true → düzenleme kontrolleri gizli
}
```

Yedi öğe sırayla (`:196-428`):

1. **Kaynak rozeti** `serit-kaynak` (`:198-236`): `"Davalar ▾"` — Radix `DropdownMenu` ile `katalog.veri_kaynaklari`
   (etiket + açıklama, `data-kaynak`); farklı kaynak → `onKaynakSec(anahtar)`, aynı kaynağa tık no-op (`:226`).
   `salt` → düz rozet (`:199-203`). Ana kaynak rengi çubuğu (`ANA_KAYNAK_RENGI`, `ui.ts:51`).
2. **Kolon çipleri** `serit-kolon-<anahtar>` (`:238-263`): etiket; bağlı kolonda (`kolon.bag`) `"<İlişki> · "` öneki
   (`kolonAdi :63-68` — sunucu etiketi zaten önekliyse ikilenmez) + ayrık renk çubuğu `kaynak-cubugu`
   (`kaynakRengi`, `ui.ts:65-69`: ilişki sırasına göre `BAG_RENKLERI :54-59`, tema token'ları, renk yalnız
   ipucu). `×` → `kolonKaldir` (`builderState.ts:189-192`; **son kolon kaldırılamaz**: düğme disabled + "En az bir
   kolon gerekli", `:253-254`). Sürükle-sırala / ↑↓ bilerek YOK — sıra = ekleme sırası (G173 kararı).
3. **"+ Kolon"** `serit-kolon-ekle` (`:265-322`): `Popover` + cmdk `Command` (`kolon-secici`; düz alt-dize araması
   `altDizeFiltresi :34-38`, tr-TR küçük harf, anahtar da `keywords`). En üstte **"Hazır setler"** grubu
   (`kolon_setleri`; katalogda olmayan/seçilemeyen anahtarlar düşer, boş set listelenmez, `hazirSetler :127-133`;
   seçince set kolonları tekrarsız EKLENİR — seçimi değiştirmez), sonra `grup` / `"<İlişki> · <grup>"` başlıkları
   (`kolonGruplari :112-125`, `grupBasligi :70-76`) — yalnız `secilebilir` ve henüz seçilmemiş kolonlar. 60 tavanı
   (`TANIM_LIMITLERI.kolon_max`; `:108`, `:273-274`: disabled + "En çok 60 kolon"). Ekleme `kolonEkle`
   (`builderState.ts:176-186`: tekrar/tavan koruması, değişiklik yoksa aynı nesne).
4. **Filtre çipleri** (`:324-376`): dolu kontroller mevcut `FilterChip` ile (`etiket · özet` · "…" menüsü · ×);
   G173'ün geriye uyumlu prop'ları `onAc`/`acik` ile çip gövdesi `aria-haspopup="dialog"` düğmesi olur
   (`FilterChip.tsx:14-19`, `:111-122`) → tık popover'daki düzenleyiciyi açar (§8.3). Aynı anda tek popover.
   `×` (`ogeKaldir :163-172`): hızlı yuva boş kontrole döner (durumda kalır, çip düşer), eklenen alan şeritten kalkar.
   Boş öğe yalnız düzenleyicisi açıkken kesik kenarlı **taslak çapa** `serit-filtre-taslak` olarak çizilir
   (`:344-349`); kapanınca kaybolur, öğe durumda kalır. Çapa `PopoverAnchor`; çapanın kendisine tık dışarı
   sayılmaz (`onInteractOutside :358-362`; aksi hâlde açık çipe tık kapatıp yeniden açıyordu).
5. **"+ Filtre"** `serit-filtre-ekle` (`:378-389`): mevcut `FieldPicker` (`etiket="Filtre"`, `alan-secici`;
   `FieldPicker.tsx:32`, `:22-25` isteğe bağlı `etiket`/`title`). Liste = `filtrelenebilir` ve **dolu filtresi
   olmayan** alanlar (`filtreEklenebilir :148-154`; boş hızlı yuvalar görünmez olduğundan listede KALIR — seçilince
   yeni öğe eklenmez, yuvanın düzenleyicisi açılır); bağlı kolonlar "+ Kolon" ile aynı önekli grup başlığında.
   Seçim `filtreAlaniSec` (`:174-181`) → `filtreEkle` (`builderState.ts:200-204`: `eklenenOge(bosKontrol(kolon))`,
   `hizli:false`; aynı alanda boş öğe varsa ya da 20 dolu filtre varsa eklemez — idempotent) + `seritteBosOge`
   (`:207-209`) ile düzenleyici açık gelir; doldurulmadan kapatılırsa çip yok. 20 tavanı (`filtre_max`; `:147`,
   `:384-385`: disabled + "En çok 20 filtre"). Aynı alanda ikinci filtre yalnız asistan/şablon yolundan gelir; çip
   olarak yine görünür/düzenlenir.
6. **Sıralama çipleri** `serit-siralama-<alan>` (`:391-413`): `"↑ Etiket"` / `"↓ Etiket"` (`data-yon`), `×` sıralamayı
   düşürür. Ekleme yolu tablo başlığı (§8.5); şeritte "+ Sıralama" YOK.
7. **Temizle** `serit-temizle` (`:415-427`): `onChange(kaynakIcinBaslangic(kaynak))` — filtreler boş, kolonlar
   kaynağın varsayılanı, sıralama boş, kaynak DEĞİŞMEZ; onay yok (geri al sayfanın işi değil). Zaten temizken
   disabled (`zatenTemiz :185-187`).

`builderState.ts` yardımcıları: mevcut `kaynakIcinBaslangic :69-77`, `tanimdanDurum :101-131`, `seritiTemizle
:137-145` (boş sonuç kısayolu `onFiltreleriTemizle`, `ReportsPage.tsx:414-417`), `seritFiltreleri :148-155`,
`tanimOlustur :158-165`, `siralamaDongusu :215-223` — imzaları DEĞİŞMEDİ; G173 ekleri `kolonEkle`, `kolonKaldir`,
`filtreEkle`, `seritteBosOge` (`:167-209`, saf, kataloğa bakmaz).
**Yükleme (şablon / koşu / asistan tanımı):** `tanimdanDurum` her filtreyi `filtredenKontrol` (`lib/reports.ts:544`)
ile yuvanın `sunum`una göre çözer: yuva alanına (ya da alternatifine) düşen filtre yuvayı doldurur, kalanlar eklenmiş
alan olur; çözülemeyen op `gelismis` çip olur ve KAYBOLMAZ; gelişmiş çip yuvayı ezmez (`yuvayaUyarMi :83-88`,
`:112-120`). Dolu öğeler TANIMDAKİ sırayla önce, boş yuvalar sonra — filtre sırası korunur (şablon eşitliği
`JSON.stringify`, `ReportsPage.tsx:56`, `:280`, `:284`). Gidiş-dönüşün tek istisnası tek değerli `in` → `eq`.

### 8.3 Çip düzenleme popover'ı (`FilterControl.tsx` yeniden kullanımı) — kontrol → op tablosu

Filtre çipine tık → `Popover` (`filtre-duzenleyici`, `data-alan`; `TanimSeridi.tsx:352-373`) içinde **mevcut
`FilterControl`** (`FilterControl.tsx:67`; aynı `SeritOgesi`, `onChange=(d, gecikmeli) => ogeDegistir(...)`
`:156-157`, `onHemen`, `bugun`). Kontrol mantığı DEĞİŞMEDİ (operatör seçici YOK): tarih yuvasında `alanSecenekleri`
alan değiştirici `<select>` (`:88-100`; alternatifler yalnız `kontrol === "tarih_araligi"`); `tarih_araligi`
(`:115`) = başlangıç + bitiş `<input type=date>` + kısayol (Bu yıl · Geçen yıl · Son 30 gün · Son 12 ay;
`tarihKisayolu` `lib/reports.ts:797-811`, `isoGun :787`, `bugun` testte sabit); `sayi_araligi` (`:126`) = "en az /
en çok"; `coklu_secim` (`:151`, `CokluSecim :301`) = aranabilir açılır liste, serbest metin YOK, sonda "Boş"
(`:285`); `metin_icerir` (`:170-197`) = düz girdi ya da öneri varsa cmdk combobox (`MetinCombobox :490`; 300
öneri, kesikte başlık "İlk 300 değer (liste kesildi)" `:519`); **yazım `onChange(..., true)` = gecikmeli**
(`:179`, `:190`), combobox seçimi hemen ve `tam: kolon.oplar.includes("eq")` (`:180`); `mantik` (`:198`) =
Hepsi/Evet/Hayır; `gelismis` (`:210`, `GelismisDeger :588`). Tarih/sayı/metin kontrolünde girdinin sağında "Boş"
toggle çipi (`is_null` izinli kolonda; `:229`, `:479` — açıkken girdi kilitli). Odak çıkışı `onHemen`; popover
kapanışı da blur ürettiğinden bekleyen gecikmeli önizleme kapanışta atılır.

**Kontrol → op** (`kontroldenFiltre`, `lib/reports.ts:489-534`; plan §4.3 tablosu — sunucu sözleşmesi AYNEN,
satırlar c839fdb'de yeniden okundu):

| kontrol | girdi | üretilen filtre | kod |
| --- | --- | --- | --- |
| `gelismis` | çipin "…" menüsü | op olduğu gibi (`deger` yalnız taşıyan op'ta) | `:491-492` |
| `tarih_araligi` | iki uç / yalnız başlangıç / yalnız bitiş / kısayol | `between [b,e]` / `gte` / `lte` | `:493-501` |
| `sayi_araligi` | iki uç / yalnız en az / yalnız en çok (JSON number) | `between [a,c]` / `gte` / `lte` | `:502-510` |
| `coklu_secim` | 1 seçim / n seçim / yalnız "Boş" | `eq` / `in [...]` (`null` = "Boş" öğesi) / `is_null` | `:511-517` |
| `metin_icerir` | yazım / combobox seçimi (`tam`) | `contains` / `eq` — **yalnız kolonun `oplar`ında `eq` varsa**, aksi yine `contains` (`FilterControl.tsx:180`) | `:518-523` |
| `mantik` | Evet/Hayır | `eq true/false` | `:524-526` |
| `var_yok` (§5.3 sunum) | var / yok / hepsi | `gte 1` / `eq 0` / yok | `:527-530` |
| `bos_anahtari` (§5.3 sunum) | açık | `is_null` | `:531-532` |
| (tarih/sayı/metin) "Boş" çipi | — | `is_null` (değersiz) | `:494`, `:503`, `:519` |

**"…" menüsü** (`FilterChip.tsx:50-86`): kolonun `oplar`ı ∖ kontrolün doğal op'ları (`KONTROL_DOGAL_OPLARI`
`lib/reports.ts:601-609`, `gelismisOplar :615-619`; ör. `ne`, `not_null`) + metinde "Tam eşitlik" anahtarı
(yalnız `oplar`da `eq` varsa, `:67-74`). Gelişmiş op seçilince çip `gelismis` durumuna geçer (`GelismisDeger`);
menüde "Basit kontrole dön" (`:63-65`, yuvanın sunumuyla boş kontrol). Çip özeti `kontrolOzeti` (`:639-`).

### 8.4 Otomatik önizleme (`ReportsPage.tsx:338-356`) — mekanizma DEĞİŞMEDİ, tetik artık şerit

Efekt her `tanim` değişiminde: kaynak yok ya da taslak geçersizse (`tanimGecerliMi`,
`lib/reports.ts:397-414` — kolon 1-60 tekrarsız + `secilebilir`, filtre ≤20, sıralama ≤3, her filtre kolon bazında
`filtrelenebilir` + `oplar` + `filtreTamamMi`, her sıralama `siralanabilir`) istek GİTMEZ; taslak son
İSTENEN'le (`sonIstenenRef :146`, hata dönse de) aynıysa istek yok; yapısal değişiklik (kolon ×/ekle, kaynak,
liste seçimi, tik, kısayol, sıralama, şerit Temizle, çip ×) → hemen; yazarak girilen değer (`onChange(..., true)`:
popover'daki tarih/sayı/metin girdileri, §8.3) → `ONIZLEME_GECIKME_MS = 600` (`:38`; her tuşta yeniden başlar) ya
da odak çıkışında `hemenOnizle` (`:358-366`). Yarış koruması `reqIdRef` (`:144`, `onizlemeAl :296-320`). Sayfa
değişimi son BAŞARIYLA önizlenen tanımla (`sonTanim`, `onSayfa :388-391`); örnek boyu (10/25/50) değişince 1.
sayfadan yenilenir (`:322-329`). "Bayat" rozeti ve Önizle düğmesi YOK; tabloda "güncelleniyor…"
(`PreviewTable.tsx:75-84`), geçersiz taslakta son geçerli önizleme ekranda kalır + "taslak eksik" ipucu
(`:65-74`), hata `DataErrorBanner` + "Tekrar dene" (`onRetry`, `ReportsPage.tsx:393-399`, hata anındaki tanımla).
**Asistan tanımı** `asistanTanimiUygula` (`:646-690`; G174'ten beri `AssistantBar` `complete` işleyicisi DÜĞMESİZ
çağırır — ayrıca aday çipi, "Yine de uygula", kart Onayla/İndir, yerel/sözle onay): `tanimdanDurum` → `durumDegisti`,
`oncekiTaslak` = önceki durum ("Geri al" tek adım, `asistanGeriAl :718-722`; her başka taslak yazımı düşürür
`:375`), şablon seçimi düşer; geçersiz tanım yine konur + hata toast'ı (`:659-664`); `eylem=null` → otomatik
önizleme; `onizle` → `sonIstenenRef=null` ile aynı tanımda bile yeniden ister (`:665-670`); önizleme gelince
"Rapor hazırlandı · N kayıt" toast'ı (`asistanToastRef :188`, `:305-309`); `indir_*` → `/export`
`kaynak:"asistan"` + favori önerisi (`:671-689`).

### 8.5 Önizleme tablosu ve sıralama (`PreviewTable.tsx`) — DEĞİŞMEDİ

Başlıkta toplam rozeti `"N kayıt · M kolon"` (`toplam-rozeti`, `:56-64`, tr-TR binlik; sayaç satırındaki
"N kayıt" ile ekranda iki kez görünür — §13 NOT). `siralanabilir` başlıklar düğme (`aria-sort`, ok, çok alanlıda
sıra numarası, ipucu döngünün sonraki adımı; `:120-156`); tık → `onSirala` → `siralamaDongusu`
(`builderState.ts:215-223`): yok → artan → azalan → kaldır, tavan 3, dördüncüde EN ESKİ düşer; sıralama şeritte
çip olarak da görünür (§8.2 madde 6). Türetilmiş/çoklu bağ kolon başlığı tıklanmaz (`siralanabilirMi`,
`ReportsPage.tsx:404`). Boş sonuçta (`bos-sonuc`, `:103-114`): filtre varken "Bu filtrelerle kayıt yok —
filtreleri gevşetin." + "Filtreleri temizle" kısayolu (`onFiltreleriTemizle`, `ReportsPage.tsx:414-417` —
`seritiTemizle`: yuvalar boşa döner, eklenenler kalkar; kolon/sıralama DOKUNULMAZ, şerit Temizle'den farkı bu),
filtresizken "Bu kaynakta kayıt yok.". Alt çubuk: örnek boyu `<select>` 10/25/50 (`ORNEK_BOYU_SECENEKLERI :32`,
`:189-203`) + sayfalayıcı `sayfa / toplamSayfa` (`:204-226`). Hücreler `hucreBicimle` (tarih dd.MM.yyyy, para
tr-TR, `null` "—"; sayı/para sağa yaslı).

## 9. Admin anahtarı — `rapor_asistani`

`SETTINGS_REGISTRY["rapor_asistani"]` (`services/app_settings.py:66-75`): label "Rapor asistanı (AI)",
**varsayılan KAPALI** (`default: False`, `:67` — Gemini maliyetli özellikler repo kültüründe kapalı doğar;
`client_notice_enabled`, `veri_teslim_otomasyonu` gibi). Okuma `rapor_asistani_etkin()` (`:178`);
`GET/PUT /api/admin/settings` (`routes/admin.py:50`, `:56`) ile panelden açılır — Yönetim →
Özellikler kartı registry'den otomatik listeler. Kapalıyken `/chat` 409 (`routes/reports.py:412-413`).

**Sohbet artık ekranın BİRİNCİL yoludur (G175) — kapalıyken sayfa boş KALMAZ:** frontend
`raporAsistaniAcikMi()` `GET /api/admin/settings`'i okur (hata/kayıt yok → false, sessiz;
`lib/reportsChat.ts:197-207`); anahtar `false` ya da `/chat` 409 (`asistan409`, `ReportsPage.tsx:184`,
`:724-728`) → `AssistantBar` yerine tek satırlık bilgi kartı `asistan-kapali-karti` (`:730-731`, `:756-770`:
"Rapor asistanı kapalı — yönetici panelinden `rapor_asistani` anahtarını açın. Tanım şeridi ve tablo çalışmaya
devam eder."); **tanım şeridi tam bir yedek kurucudur** — kaynak, kolon, filtre (300 önerili combobox dahil),
sıralama şeritten düzenlenir; önizleme, export, şablonlar, indirme geçmişi anahtardan bağımsız çalışır (test:
`ReportsPage.test.tsx` "anahtar kapalı: bilgi kartı + şerit/tablo/şablon/indirme çalışır"). Kullanıcı bunu bilerek
kabul etti (G175 hedefi: "yedek bedavaya geliyor"). Anahtar yeniden açılınca sayfa yenilemesi gerekir (§13).
**Prod durumu:** anahtar Deploy #21 (2026-09-10) ile prod'da AÇILDI (bellek notu; koddan doğrulanamaz —
`GET /api/admin/settings` ya da Yönetim → Özellikler kartından bakılır). Uyarı: anahtar kapatılırsa kullanıcılar
birincil yolu kaybeder, yalnız şeritle çalışır — kapatma kararı bilinçli olmalı. Varsayılanı AÇIK yapmak tek
satırdır (`app_settings.py:46-47` yorumu, `:67`).

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
kararları ve plandaki "ölçüm/etiket" ifadelerinin somutlaşmasıdır. (F16/F19/F20/F21'deki `QuickFilters`,
`ColumnPicker`, `ui/sheet.tsx` G175'te SİLİNDİ — satırlar tarihsel, bkz. F23.)

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
| F22 | §4.1 madde 5 "yalnız geçerli tanımda" | geçersiz taslakta SON GEÇERLİ önizleme ekranda kalır + "taslak eksik" ipucu; boşa düşürülmez (`PreviewTable.tsx:65-74`) | kullanıcı verisiz kalmaz, istek gitmez |

**Sohbet öncelikli tur — G173-G176 (2026-09-11, kullanıcı kararı "arayüz deli gibi sadeleşsin"):** plan §4.1/§6.1/§8
gövdeleri tarihsel bırakıldı (planın başında şerh); sunucu sözleşmesi yine değişmedi.

| # | Plan | Kod | Sonuç / sebep |
| --- | --- | --- | --- |
| F23 | §4.1 yerleşim: kaynak kartları → filtre şeridi → "Kolonlar (N)" yan paneli → araç çubuğu → tablo; §6.1 "asistan önde, manuel kurucu altta" | `AssistantBar` → `TanimSeridi` → sayaç/şablon/indirme satırı → `PreviewTable` (`ReportsPage.tsx:740-852`, G175); `SourceCards`/`QuickFilters`/`ColumnSheet`/`ColumnPicker`/`ui/sheet.tsx` SİLİNDİ | manuel kurucu KALKTI; şeffaflık + düzeltme kanalı tanım şeridine indi (G173) |
| F24 | §8 teyit döngüsü (G167): kart onay bekler, "Onayla ve uygula" / karttan indirme | `complete.tanim` → `degerEsle` temizse DÜĞMESİZ uygulanır (`AssistantBar.tsx:244-263`, G174); kart yalnız değer uyuşmazlığı / sayfa reddi / Geri al'da bekler; karttan indirme ve "Geri al" kaldı | şerit her an ekranda olduğu için onay adımı sürtünme oldu — G167 kararı 11.09'da geri alındı; yerel onay (`onayNiyeti`) bekleyen tanım için korunur |
| F25 | Kapsam kararı "manuel yol her zaman açık kalır"; K8 "anahtar kapalıyken manuel akış çalışır" | manuel KURUCU yok; yedek = tanım şeridi (kaynak/kolon/filtre/sıralama tamamı düzenlenebilir); anahtar kapalı/409 → bilgi kartı `asistan-kapali-karti` (`ReportsPage.tsx:756-770`) | karar biçim değiştirdi, özü korundu — Gemini düşse de rapor alınır (§9) |
| F26 | Üç aşama planı (G169-G172; plan dışı kuyruk kalemi, 10-11.09 gece taslağı) | koşulmadan İPTAL; dosyalar `docs/arsiv/gorevler/G169-G172` (iptal şerhli); teşhisi ("bağlı kolonlar 145 kolonlu listede kayboluyor") "+ Kolon" combobox'ının `"<İlişki> · <grup>"` başlıkları karşıladı (`TanimSeridi.tsx:70-76`) | kullanıcı 11.09 gündüz sohbet öncelikli ekranı seçti |
| F27 | §8.3 prompt "TEYİT DÖNGÜSÜ" (onay sorusuyla bitir) | "UYGULAMA" (onay SORMA) + "YAKLAŞIK AD" (`contains`) + "LİSTE SORUSU" (ekrana yönlendir) (`prompts.py:522-535`, G176); bekçi testler `test_prompt_g176_*` | ekranla çelişen kural düzeltildi; Gemini duman testi insan adımı (G176 raporu: 3 istem) |
| F28 | (planda yok) asistan değer doğruluğu yalnız sunucu doğrulaması (K6) | istemcide Gemini'siz **değer eşleme** (`degerEsle`, aday çipleri) ve **liste balonu** (`listeNiyeti`, `DegerListesi`) — öneriler zaten katalogla istemcide (`reportsChat.ts:455-670`) | K6 korunur (asistan veri görmez); "Ankara 3. Ticaret" gibi yaklaşık değerler kataloğa bağlanır |

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
  "İlk 300 değer (liste kesildi)" (`FilterControl.tsx:519`). Sıra DB collation'ı (F13).
- **Aday eşleme yalnız listesi olan kolonlarda (G174 + 2026-09-12):** `degerEsle` (`reportsChat.ts`) `oneriler`
  yoksa `secenekler`e bakar (veriden kapalı liste ör. Uzmanlık Alanı; kodlu listede `secenek_etiketleri` etiketi
  de kabul); listesiz serbest metin kolonunu (ör. `subject`) daima temiz sayar — orada asistanın yazdığı değer
  kontrolsüz uygulanır. Boş sonuç satırının örnek istemleri (`gevsetmeOrnekleri`) gerçek filtrelerden türer. **300 kesik listede aday bulunamayabilir:** aranan değer ilk 300'ün dışında
  kalırsa satır "eşleşmedi" olur ve aday çipi çıkmayabilir; kart "Liste kesik (300 tavanı)" notu + "Yine de uygula"
  verir (`AssistantMessage.tsx:227-231`). Aday sıralaması kelime kesişimi/önek — eşanlamlı bilmez.
- **Liste balonu yalnız kalıp eşleşince (G174):** `listeNiyeti` (`reportsChat.ts:642-670`) Gemini'ye GİTMEZ — kalıp
  dışı yazımlar ("mahkeme adlarını görebilir miyim") Gemini'ye düşer ve prompt "LİSTE SORUSU" kuralı çipe/`hangi
  <alan>lar var` yazımına yönlendirir (güvenlik ağı). Gerçek katalogda "mahkeme" birden çok kolona uyarsa (Mahkeme +
  Mahkeme İli gibi) "Hangisi?" çipleri çıkar — kullanıcıyla gözlenmeli, eşanlamlı tablosu (`ES_ANLAM_GRUPLARI
  :588-604`) buna göre genişletilebilir (G174 raporu). Balon en çok 300 satır; `secenekler`li kolonda sayı rozeti
  yalnız `secenek_sayilari` varsa.
- **Gemini / anahtar kapalıyken sohbet yok — şeritle çalışılır:** `rapor_asistani` kapalı, `/chat` 409 ya da Gemini
  `failed` (devre kesici/429) durumunda rapor yine şeritten kurulur (§9); sohbet balonu hata kaydını gösterir,
  şerit etkilenmez. Sohbet birincil yol olduğundan Gemini kesintisi kullanıcı deneyimini düşürür, veri kaybettirmez.
- **Sohbet geçmişi sayfa yenilemede sıfırlanır (değişmedi):** `AssistantBar` state'i (`kayitlar`), sunucu saklamaz
  (K6); "Kapat" alanı kapatır ama geçmiş kalır (`AssistantThread` "Kapat (geçmiş kalır)"), "Temizle" siler.
- **Önbellek 60 sn / worker başına:** referans listesi ya da yeni taraf adı ekledikten sonra şeritteki
  seçenek/öneri en geç 60 sn sonra görünür; iki worker aynı anda farklı fotoğraf verebilir (F15).
- **`RAPOR_MAX_SATIR` iki okuyucu:** export tavanı `settings.rapor_max_satir` (boot'ta donar),
  katalogdaki `export_max_satir` `motor.limitler()` `os.getenv` (önbellek süresi içinde bir kez).
  Prod'da aynı env'i okurlar, fark yalnız test zamanı; `motor.limitler()`ın `settings`'ten okuması
  bekleyen tek satır (G131/G132 raporları) — docs bandı kod değiştirmediği için açık.
- **KAPANDI (G175):** eski NOT "`ColumnPicker.tsx:285` satır ipucu türetilmiş kolonda 'filtrelenemez' yazar" —
  dosya silindi; "+ Kolon" combobox'ı tip/ipucu basmaz.
- **NOT (frontend, kapsam dışı — G175/G177 docs bandı dokunmadı):** `FilterControl.tsx:65` yorumu "Arama kutusu
  QuickFilters'ta ayrı satırdadır" bayat — `QuickFilters` silindi; şeritte `sunum=arama` yuvası popover'daki metin
  kontrolüyle düzenlenir. Tek satırlık yorum düzeltmesi.
- **NOT (frontend, kapsam dışı):** "N kayıt" ekranda İKİ kez — sayaç satırı `kayit-sayaci` (`ReportsPage.tsx:786-792`)
  ve `PreviewTable` başlık rozeti `toplam-rozeti` (`:56-64`; dosya G175 dokunma listesindeydi). Küçük temizlik
  görevi: rozeti düşürmek (G175 raporu kararı).
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
  kalır (G135, bilinçli; G175'te bilgi kartı da aynı bayrağa bakar, `ReportsPage.tsx:731`).
- **Gün sınırı saat dilimi:** DateTime kolonlarda tarih filtresi DB oturumunun saat dilimine göredir
  (prod UTC; Türkiye günü 03:00'te başlar). Tarih kısayolları tarayıcının yerel gününü ISO'ya çevirir
  (`isoGun`, `lib/reports.ts:529-532`).
- **CSV ondalık `.`:** `Decimal→float` olduğu gibi yazılır; Türkçe Excel `;` ayraçlı CSV'de `,` ondalık
  bekleyebilir — xlsx ana yol, CSV ham veri yolu; kullanıcı geri bildirimiyle karar.
- **Tarayıcıda görsel duman testi yapılmadı (G173-G175 de gece koştu):** yerleşim/responsive kanıtı jsdom'da
  sınıf ve sıra düzeyinde (`flex-wrap`, max-w yok); gerçek Radix popover konumlanması, `lg` altında sayaç
  satırının/şeridin sarması, 300 önerili combobox'ın popover içinde kaydırması göz kontrolü ister (G173/G175
  raporları). Gemini duman testi (3 istem: yaklaşık mahkeme adı → `contains`; "hangi mahkemeler var" → liste;
  "telefonu da ekle" → yalnız `muvekkil.phone` eklenir, onay istenmez) insan adımı (G176 raporu).
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
| `backend/tests/test_g132_rapor_asistani.py` (G176 eki, 2 test; dosyada 30 test fonksiyonu — `grep -c "def test_"`, c839fdb) | `test_prompt_g176_uygulama_kurali_teyit_dongusu_yok` ("TEYİT DÖNGÜSÜ"/"hemen uygulanmaz"/"yine onay iste" YOK; "hemen uygulanır", "düzenlenebilir bir şeritte", "onay SORMA", belirsizlik, sözlü onay, "SIFIRDAN ÜRETME", düzeltme cümlesi VAR), `test_prompt_g176_yaklasik_ad_contains_ve_liste_sorusu` (`contains` + liste sorusu cümleleri; "aynen kopyala" korunmuş; yerleşim kurallar < KATALOG < MEVCUT TANIM) — eski prompt'ta kırmızı (G176 raporu, stash ile doğrulandı) |
| `frontend/src/lib/reportsChat.test.ts` (**42**: G167 + G174 bölümleri), `components/reports/AssistantBar.test.tsx` (**16**), `pages/ReportsPage.asistan.test.tsx` (**23**), `ReportsPage.favori.test.tsx` (**12**) | teyit kartı okunur satırları (7 filtre biçimi, bağlı kolon etiketi, bilinmeyen anahtar), `tanimAyni`, `onayNiyeti`, `kaydetNiyeti`; **G174:** `degerEsle` (alt dize temiz, birebir `eq`, tutmayan → adaylar kelime kesişimine göre sıralı ≤5, öneri listesiz kolon temiz, `in`/`between`/tarih/sayı/mantık atlanır, İ/ı ve U+0307 normalize), `listeNiyeti` (olumlu kalıplar + eylem fiilli olumsuzlar, etiket/hızlı filtre/eşanlamlı çözümü, belirsizde adaylar); otomatik uygulama (temiz tanım düğmesiz uygulanır, `uygulandi` + Geri al; sorunlu değer kartı + aday tık → uygula; "Yine de uygula"; liste balonu + liste tık → `onFiltreEkle`; "Hangisi?"); düzeltme `mevcut_tanim` = bekleyen; sözle onay hemen; sayfa reddederse kart bekler; tanımsız eylem; `indir_*` ile gelen temiz tanım doğrudan indirilir, 413 yolu; Geri al → yeniden bekleyen; sayfa düzeyinde liste balonu → `eq` → `in` birleşmesi → × ile düşme + toast; favori kartı indirme sonrası |
| `frontend/src/lib/reports.test.ts` (**50**), `reports.export.test.ts` (**14**), `reports.favori.test.ts` (**10**) | tip↔op tablosu, kolon başına `oplar`, kontrol→op (§4.3) + gidiş-dönüş, tarih kısayolları, `tanimGecerliMi` taraf kolonu kapısı, gövde biçimleri, hata çevirisi, `Content-Disposition`, şablon sahipliği, favori ad önerisi |
| `frontend/src/components/reports/TanimSeridi.test.tsx` (**14**, G173), `builderState.test.ts` (**18**: 12 + G173 `kolonEkle` ×2, `kolonKaldir`, `filtreEkle` ×3), `FilterControl.test.tsx` (**11**), `PreviewTable.test.tsx` (**7**), `TemplateBar.test.tsx` (**4**) | yedi şerit öğesi + sarma + bağlı kolon önek/renk; kontrollü davranış; kaynak menüsü (farklı → `onKaynakSec`, aynı → çağrı yok); kolon × / tek kolon disabled; "+ Kolon" grup başlıkları + arama + seçim, hazır set tekrarsız + 60 tavanı; filtre popover (metin `gecikmeli=true`, liste hemen, odak çıkışı `onHemen`, ×); 300 önerili combobox + kesik başlığı + tarih kısayolu; "+ Filtre" akışı (boş → popover açık, çip yok → doldurunca çip; boş yuva yeniden kullanımı; Escape → durumda kalır; 20 tavanı); sıralama çipi ×; Temizle; "…" gelişmiş/"Basit kontrole dön"/boş kontrol çip vermez; `salt`; yuvalar/eklenen alanlar/temizle/tanımdan çözme; kontrol→op (değişmedi); başlıktan sıralama + "güncelleniyor…" + boş sonuç; kompakt şablon çubuğu |
| `frontend/src/pages/ReportsPage.test.tsx` (**18**), `ReportsPage.sablon.test.tsx` (**13**) | dolu açılış (tek istek, varsayılan tanım), kaynak değişimi rozet menüsünden (eski satırlar anında düşer), otomatik önizleme (yapısal hemen / 600 ms popover'daki girdide / odak), şeritten filtre kaldırınca (×) ve şerit Temizle ile önizleme HEMEN, boş sonuç kısayolu, geçersiz tanım (gelişmiş çip değeri silinerek), arama kutusu (popover'da), 422/ağ/katalog hatası, anahtar kapalı → bilgi kartı + şerit/tablo/şablon/indirme çalışır, yerleşim sırası (`flex-wrap`, max-w yok), /reports kapısı, Sidebar; şablon yükle/kaydet/Güncelle-Sil "…" menüsünden, başkasının şablonunda menü yok, koşu tanımı yükleme (çip düzenleyicisinden okunur) |
| **KALDIRILDI (G175):** `QuickFilters.test.tsx` (23), `ColumnSheet.test.tsx` (6), `SourceCards.test.tsx` (2) | bileşenleriyle birlikte silindi; çip/kontrol davranış testleri `TanimSeridi.test.tsx`'e taşındı |

Koşu sonuçları: frontend `npm --prefix frontend test` **916 passed / 69 dosya** — G177 docs oturumu
2026-09-11'de c839fdb worktree'sinde KOŞTU (vitest 4.1.11, 27,8 sn; G175 raporuyla aynı sayı: 945 − 31
kaldırılan + 2 yeni). Backend konteynerde koşmadı (docs bandı, worktree); G176 raporu (2026-09-11): `pytest`
**3292 passed / 3 skipped**, `tests/test_g132_rapor_asistani.py` + `test_g166_rapor_bagli_kaynaklar.py` 65 passed,
ruff + mypy temiz. Backend testleri konteynerde (`docker compose exec -T backend python -m pytest
tests/test_g13*.py tests/test_g166*.py`), frontend host'ta (`npm --prefix frontend test`) koşar.

## 16. Nereye bakmalı

| Konu | Dosya |
| --- | --- |
| Sözleşme (plan, dondurulmuş §2 + ikinci tur §4 + şerhler; başındaki "sohbet öncelikli ekran" şerhi §4.1/§6.1/§8'i tarihsel kılar) | [`docs/plan/raporlama-plani-2026-09-06.md`](../plan/raporlama-plani-2026-09-06.md) |
| Uçlar + katalog önbelleği | `backend/routes/reports.py` |
| Şemalar, sınırlar, tip↔op | `backend/schemas_rapor.py` |
| Kayıt defteri (kolonlar, gruplar, taraf EXISTS filtreleri, öneriler, hızlı filtre/set) | `backend/services/rapor/registry.py` |
| Motor / çıktı / koşu logu / asistan | `backend/services/rapor/{motor,cikti,kosu_logu,asistan}.py` |
| Sistem talimatı (G176 kuralları UYGULAMA / YAKLAŞIK AD / LİSTE SORUSU) | `backend/prompts.py:449`, `:522-535` |
| Tablolar + madde 46 | `backend/models.py:1350-1432`, `backend/database.py:1050-1064` |
| Anahtar / env | `backend/services/app_settings.py:41-79`, `backend/config/settings.py:103-112`, `.env.example:55-66` |
| Frontend tipler + kontrol↔op çevirisi + API | `frontend/src/lib/reports.ts`, `frontend/src/lib/reportsChat.ts` (asistan istemci mantığı: `onayNiyeti`, `kaydetNiyeti`, `degerEsle`, `listeNiyeti`) |
| Frontend şerit durumu ↔ tanım | `frontend/src/components/reports/builderState.ts` |
| Frontend sayfa + bileşenler | `frontend/src/pages/ReportsPage.tsx` (yerleşim, `onFiltreEkle`, `asistanTanimiUygula`), `frontend/src/components/reports/` (`TanimSeridi.tsx` şerit; `AssistantBar.tsx` otomatik uygulama + liste balonu; `AssistantMessage.tsx` kart hâlleri; `DegerListesi.tsx`) |
| Gemini devre kesici / retry / `_failed_event` | [`dis-bagimliliklar.md`](dis-bagimliliklar.md), `backend/analyzer.py:82`, `:368` |
| Görev raporları | `gorevler/gorev/G130.md` … `G168.md`, `G173.md` … `G177.md`; iptal edilen üç aşama planı `docs/arsiv/gorevler/G169.md` … `G172.md` (tarihsel) |
