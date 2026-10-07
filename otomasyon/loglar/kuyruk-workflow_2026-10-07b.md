# Gece Kuyruğu (workflow) · 2026-10-07b

## Özet

8 görev alındı (1'i uygulandı) · 0 işaretlendi · 1 bloke · 7 atlandı

## İşaretlenenler

| görev | bant | depo | commit | kapı | denetim | not |
| --- | --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — | Bu koşuda hiçbir görev işaretlenmedi (`isaretlendi=false`). |

## Bloke

### G258 — Tam metin arama (`karar_arama` tsvector + GIN, `lexis_rapor/arama.py`, `karar_arama_kur.py`, raf araması FTS, 20 sorguluk ölçüm)

- **Bant / depo:** lexis / **lexis-rapor** (`../lexis-rapor`, push'suz). Worktree YOK; commit o depodadır.
- **Durum:** `uygulandi=true`, `verify=yesil`, 1 tur, `durmaSebebi=yesil`, `mergeYapildi=false`, `entegrasyon=uygulanamaz`, `isaretlendi=false`, `bloke=true`.
- **Commit (lexis-rapor):** `0200695bedb99a38c37565a3a8bf05fb5805b38e`
- **Durma sebebi (bloke):** KAPI — test bütünlüğü ihlali. Kapı sonucu: `gecti=false`, `test=ihlal`, `kirmiziYesil=kanitlandi`.
  İhlal: `araclar/karar_arama_kur.py:40` yeni `# noqa: E402` (`from servis import karar_depo  # noqa: E402 — yol yukarıda eklendi`).
  Koşucunun notu: aynı `# noqa: E402` deseni f6fb843'teki 18 `araclar/` betiğinin tamamında var (sys.path ekleme sonrası import) ve bu import fonksiyon gövdesinde olduğundan E402 zaten tetiklenmiyor — işaret kozmetik, ama kural mekanik olduğundan kaydedildi; `lexis_rapor/` ve `servis/` altında yeni noqa / type: ignore YOK. Karar sabaha.
- **Son parmak izi:** `399 passed, 14 skipped` (tests/test_arama.py Postgres FTS testleri: `LEXIS_TEST_DB_URL` yok); ruff All checks passed.
- **Denenen yaklaşımlar:**
  1. `sorgu_coz` ilk sürüm — üst düzey AND parantezli çıktı ve `-"ibare"` NOT kaybı; sadeleştirme geçişi + bare `-` kuralı ile düzeltildi (smoke testle).
  2. `karar_depo`: `CAST(bind AS REGCONFIG)` literal derlenemedi → sabit `literal_column` cast.
  3. ranked seçim: EXISTS + outer join auto-correlation hatası → yardımcı `_uygunluk_secimi`.
  4. Ölçüm 1 (EXISTS, index doldurmadan önce): her sorgu ~120 ms, GIN kullanılmadı → tanı: pending list + TOAST'lu tsvector için planlayıcı seq scan seçiyor.
  5. Tanı 2: index doldurduktan sonra GIN 0.17 ms; `fastupdate=off` (34 s doldurma, plan aynı) ile `gin_clean_pending_list` + ANALYZE karşılaştırıldı → ikincisi seçildi.
  6. `id IN (ilişkisiz alt sorgu)` + `SET LOCAL enable_seqscan=off`; ölçüm 2 iki geçiş (varsayılan / GIN tercihi) README tablosunda.
  7. `test_kucult` beklentisi yanlıştı (I→i, i→i = "ii"); test düzeltildi, kod değişmedi.
- **Teşhisin kök nedeni:** Kod ve testler yeşil; blok yalnız kapının mekanik "yeni noqa" kuralından. Teknik tarafta kök neden: TOAST'lu tsvector yüzünden varsayılan planlayıcı 19 sorgunun 13'ünü seq scan'e düşürüyordu (110-130 ms); arama transaction'ında `SET LOCAL enable_seqscan=off` ile GIN (12-28 ms tipik); tek başına `NOT x` pahalı (182 ms), README'de.
- **Diğer notlar (koşucudan):** Postgres'e özgü 14 test skip (görevde açıkça izinli); deyimlerin SQL'i derlenip kilitlendi, davranış aynı deyimlerle ROLLBACK ölçümünde doğrulandı. `karar_raf.py` / `app.py` dokunulmadı: `raf_listesi` ikiliyi koruyan `RafSonucu(tuple)` + sıralama/uyarı öznitelikleri döndürür, ekrana bağlama G264'te. `--apply` gerçek `lexis_db`'de KOŞULMADI (insan adımı); kurulana dek Postgres'te raf araması yalnız künye bulur. lexis-rapor CLAUDE.md Komutlar listesi ve test sayısı kapsam dışı, güncellenmedi.
- **Worktree yolu:** yok (lexis bandı worktree kullanmaz; çalışma doğrudan `../lexis-rapor`'da).
- **Önerilen sonraki adım:** Sabah `../lexis-rapor`'da `0200695` incelenir. `# noqa: E402` için karar: (a) mevcut 18 betikle aynı desen olduğundan kabul edilip G258 elle işaretlenir, ya da (b) satır noqa'sız yazılır (import zaten fonksiyon gövdesinde, ruff'ı tetiklemiyor) ve küçük bir düzeltme commit'i atılır. Ardından `karar_arama_kur.py --apply` insan adımı (lokal `lexis_db`), G259 zinciri serbest kalır.

## Karar bekleyenler

- `teshis.gorevTanimiHatali=true` olan görev: yok.
- `kabulKarsilanmayan` madde: yok.
- G258 kapı kararı (yukarıda): `araclar/karar_arama_kur.py:40` noqa kabul edilsin mi, yoksa kaldırılsın mı? (Testi değiştirmeden geçilemedi başlığı altına GİRMEZ — test değişimi `test_kucult` beklentisinin düzeltilmesiydi, görev tanımı sorunu değil, kod değişmedi.)

## İzin engelleri

yok

## Atlananlar

Lexis bandı SERİ (G258 → G259 → G260 → G261 → G263 → G265); G258 işaretlenmeyince zincirin tamamı bağımlılıktan atlandı.

| görev | bant | depo | sebep |
| --- | --- | --- | --- |
| G259 | lexis | lexis-rapor | bağımlılık bu koşuda tamamlanmadı: G258 |
| G260 | lexis | lexis-rapor | bağımlılık bu koşuda tamamlanmadı: G259 |
| G261 | lexis | lexis-rapor | bağımlılık bu koşuda tamamlanmadı: G258, G259 |
| G263 | lexis | lexis-rapor | bağımlılık bu koşuda tamamlanmadı: G261, G260 |
| G264 | frontend | hukdok | bağımlılık bu koşuda tamamlanmadı: G261, G263 (worktree `C:/dev/hukudok-wt/G264` açıldı, temizlenmedi) |
| G265 | lexis | lexis-rapor | bağımlılık bu koşuda tamamlanmadı: G261, G263 |
| G266 | docs | hukdok | bağımlılık bu koşuda tamamlanmadı: G264 (worktree `C:/dev/hukudok-wt/G266` açıldı, temizlenmedi) |

Tavan nedeniyle atlanan: yok.

Plan uyarıları (koşucudan): Lexis bandı görevlerinin (G258-G265) dosya kapsamları `../lexis-rapor` deposuna görelidir (HUKDOK'ta değil). G255 görev dosyasında "Rapor" bölümü yok (Notlar var); `zatenTamam=false` kabul edildi. Bu gece seçilebilir bağımsız görevler G255 (backend) ve G258 (lexis) idi.
