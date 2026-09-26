# 020 — Dava durumu üçlüsü: DERDEST | DANIŞ | MAHZEN

**Tarih:** 12.09.2026 · **Karar veren:** kullanıcı (büro sahibi) · **Durum:** uygulandı (migrasyon 50)

## Karar

`cases.status` yalnız üç değer alır:

| Değer | Anlam |
| --- | --- |
| `DERDEST` | Aktif dava dosyası — yerel, istinaf ya da temyiz aşamasında olması fark etmez |
| `DANIŞ` | Danışma dosyası (dava yok) |
| `MAHZEN` | Arşiv — kapanmış/arşivlenmiş dosya |

Yargı aşaması (yerel karar, istinaf, temyiz, karar düzeltme, kesinleşme, infaz, kapalı) DURUM
değil AŞAMADIR: `cases.case_stage` + `case_stage_decisions`. "Temyizdeki dava da derdest davadır."

## Neden

Belge işleme hattı (`routes/processing.py` "auto-status") belge türünden `status`a KARAR / TEMYIZ /
INFAZ / KAPALI yazıyordu; Avukat Paneli "statü dağılımı" bunları ayrı kart (İstinaf / Yargıtay /
Kapalı) olarak gösteriyor, rapor kataloğu yedi değer listeliyordu. 12.09 prod ölçümü: TEMYIZ 26,
ISTINAF 2, KARAR 1 kart. Aynı bilgi zaten aşama katmanında vardı; durumda tekrarı hem sayımı
bozuyor (derdest 3.067 görünürken 29 derdest dava başka kutuda) hem de teslim paketinin
`Aktif/Arşiv` ikilisiyle çelişiyordu.

## Uygulama

- `constants.CASE_STATUSES` / `LEGACY_CASE_STATUS` / `normalize_case_status` — tek kapı: üçlü
  olduğu gibi, eski değer üçlü + korunacak aşama, tanınmayan metin dokunulmaz (tahmin yok).
- `routes/processing.py` `DOCTYPE_TO_STAGE_MAP`: belge türü artık `case_stage`'e yazar
  (`case_history.field_name = "case_stage"`, `source = "auto-stage"`); status'a dokunmaz.
- `case_manager.update_case` / `update_case_tracking`: gelen status üçlüye çevrilir, aşama boşsa
  eski değer oraya taşınır. `get_case_stats.appeal` aşamadan (ISTINAF/TEMYIZ) sayılır.
- `services/rapor/registry.DAVA_DURUMLARI` üçlü. Frontend: CaseList `STATUS_ORDER`, CaseDetails
  renkleri. Avukat Paneli 26.09.2026'dan beri dört kart (kullanıcı kararı): **Derdest ·
  İstinafta · Temyizde · Arşiv** (Arşiv = MAHZEN; Danış kartı kalktı, durum duruyor).
  İstinafta/Temyizde DURUM değil, derdest dosyanın ulaştığı EN İLERİ aşamadır:
  `get_case_stats.derdest_stages` — kaynak `case_stage_decisions` (+ dolu ise `case_stage`,
  çünkü o kolon kartların çoğunda boş); Temyiz = TEMYIZ | KARAR_DUZELTME ve istinafı ezer.
  Temyiz mercii dosya türünden ayrılır (26.09 kullanıcı kararı; "Yargıtayda" etiketi idare
  davalarını da sayıyordu): İdare → Danıştay, kalanı → Yargıtay. Dava listesi durum filtresi
  ağaçtır: Derdest → İstinafta / Temyizde → Yargıtay / Danıştay (`DERDEST_ASAMA_FILTRELERI`).
  Bozma sonrası yerele dönüş ayrılmaz (ilk sürüm kararı).
- **Migrasyon 50** (`database.py`, koşulsuz "index" op'u, idempotent): eski değerli kartlara
  sistem imzalı tarihçe satırı (`migrasyon_50_durum_uclusu`), aşama boşsa eski değer oraya,
  status KAPALI → MAHZEN, kalanlar → DERDEST. Soft-silinmiş kart dahil.

## Reddedilenler

- **Otomatik durum güncellemesini tamamen kaldırmak:** belge türünden aşama çıkarımı işe yarıyor
  (tebliğ/duruşma zincirinde kullanılıyor); yalnız hedef kolon yanlıştı.
- **TEMYIZ/ISTINAF'ı durum olarak tutup panelde gizlemek:** sayımlar ve rapor filtreleri yine
  bölünmüş kalırdı; veri ekibinin `Aktif/Arşiv` sözleşmesiyle de örtüşmezdi.
- **Eski değerleri migrasyonsuz bırakıp yalnız yazma yollarını kısmak:** prod'daki 29 kart panelde
  "bilinmeyen durum" olarak kalırdı.

İlgili: `docs/mimari/veri-teslim-hatti.md` (status kesim-sonrası koruması — üçlü değerlerle çalışır),
`tests/test_durum_uclusu.py`.
