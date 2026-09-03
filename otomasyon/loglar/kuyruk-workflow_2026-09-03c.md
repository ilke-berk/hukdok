# Gece Kuyrugu (workflow) · 2026-09-03c

## Ozet

3 gorev alindi · 2 isaretlendi · 1 bloke · 0 atlandi

Plan uyarilari: HEAD 072ec9f; calisma agaci `.claude/` disinda temiz. Backend bandi seri
G116→G115 (G115 G116'ya bagimli), G117 frontend paralel. G116'nin kabul kriteri
`gorevler/gorev/G109.md` Rapor bolumune not ekletir (gorev dosyasi disi dokunma, beklenen).
Tavan nedeniyle atlanan: yok.

## Isaretlenenler

| gorev | bant | commit | kapi | denetim | not |
| --- | --- | --- | --- | --- | --- |
| G116 — `POST /api/admin/aktarim/tara` yer tutucusu → `sharepoint_tara` + kuru kosu (G108 testi guncellendi) | backend | `5f5d6b3` | gecti (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI (6/6 kabul; pytest 2325 passed/3 skipped, ruff+mypy temiz; 3 bulgu) | 2 tur: tur 1'de ruff B904 (`raise ... from exc` eksik, routes/admin.py:340), tur 2 yesil. Yeni test dosyasi eklenmedi (gorev tanimi G108'deki tek testin yeniden yazilmasini istiyor); kirmizi-yesil `git stash` ile elle dogrulandi. "Bu cagrida alinan" tespiti tarama oncesi max(id) ile; `order_by(id.desc()).first()` tercih edildi; hata mesaji `str(exc)[:200]`. Merge YAPILMADI (ana repoda, worktree yok). Izlenecek: uc senkron (~45 sn); frontend zaman asimi G117'de uzatildi. |
| G117 — `veri_teslim` bildirimi → `/admin?tab=deliveries` + AdminPage `?tab` okuma + `/api/admin/aktarim/` uzun zaman asimi | frontend | `b60a56e` | gecti (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI (vitest 602/602, lint 0, `tsc -b --force` exit 0; 3 bulgu) | 2 tur: tur 1'de tum vitest paketi >10 dk askida kaldi — AdminPage.test `useConfig` mock'u her render'da yeni `[]` dondurup `useEffect(...,[lawyers])` sonsuz dongusune sokuyordu; worker'lar oldurulup mock `vi.hoisted` ile sabit kimlikli yapildi. Tur 2: 602 passed (49 dosya). `resolveInitialAdminTab` bilerek export edilmedi (react-refresh lint kurali); `DeliveryInboxCard`'da `ApiTimeoutError` `e.name` ile taninir. Worktree `C:/dev/hukudok-wt/G117` → merge yapildi, entegrasyon yesil, worktree temizlendi. Insan adimi: frontend imaj rebuild + tarayicida bildirime tiklayip sekmeyi gormek. |

## Bloke

### G115 — Teslim yapi farki tespiti (backend) — testi degistirmeden gecilemedi, gorev tanimi gozden gecirilmeli

Bu bir basarisizlik degil: hat DOGRU calisti — kod yazilmadan sozlesme ile mevcut test
kilitlerinin celistigi tespit edildi ve duruldu. `hukdok_aktarim.py` diff sifir, test
degistirilmedi, commit yok.

- **Durma sebebi:** `test-degistirmek-gerekti` (durmaSebebi). verify calistirilmadi, tur sayisi 0.
- **Son parmak izi:** yok (kod yazilmadi).
- **Denenen yaklasim:** kapsam okundu (`teslim_kutusu.py`, `models.py::AktarimTeslimi`,
  `database.py` madde 39, `schemas.py`, `test_g107/g108/g110`); celiski gorulunce duruldu.
- **Kok neden (iki test kilidi):**
  1. Sozlesmenin zorunlu maddesi olan yeni kolon `aktarim_teslimleri.yapi`,
     `backend/tests/test_g107_teslim_kutusu.py::test_model_sozlesme_kolonlari`
     (satir 96-106, `assert kolonlar == beklenen`, birebir 26 kolon) kilidini mekanik olarak
     kirar. Gorev dosyasi test_g107 icin YALNIZ ekleme diyor ve kabul kriteri G107 testlerinin
     degisiklik gerektirmeden yesil kalmasini istiyor — ikisi ayni anda saglanamaz.
  2. `backend/tests/test_g108_teslim_admin_uclari.py::test_liste_en_yeni_once_esikler_etkin`
     (satir 257-263, `assert set(satir) == beklenen`) liste ucunun anahtarlarini birebir
     kilitler; liste `AktarimTeslimiOzetOut` ile serilestirilir (`routes/admin.py:116`) ve
     sozlesme `yapi_farki`'yi liste+tekil ucta istiyor.
- **Worktree:** yok (backend bandi ana repoda; entegrasyon: uygulanamaz).
- **Yazilan not:** BLOKE notu `gorevler/gorev/G115.md` Rapor bolumune yazildi, commit edilmedi
  (kod yok; runner isaretler). Ortam: docker compose saglikli.
- **Onerilen sonraki adim:** kapsami, `test_g107` beklenen kumesine `yapi` ve `test_g108`
  beklenen kumesine `yapi_farki` eklenmesine izin verecek bicimde genislet (alternatif:
  `yapi_farki`'yi yalniz tekil uca daralt; kolon kilidi her halukarda guncellenmeli).
  Gorev dosyasi guncellendikten sonra G115 yeniden kuyruga alinabilir.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` olan gorev yok (teshis listeleri bos). Kabul kriteri
karsilanmayan maddeler (G115) SORU olarak:

1. G115 — Migration `yapi` kolonu: `test_g107` kolon kumesi kilidinin (`beklenen` listesine
   `yapi` eklenerek) guncellenmesine izin veriliyor mu? Gorev dosyasindaki "G107 testleri
   degismeden yesil" kriteri kaldirilacak mi?
2. G115 — `AktarimTeslimiOut.yapi_farki`: liste ucunda da istenecekse `test_g108` anahtar
   kumesi kilidine `yapi_farki` eklenmesine izin verilecek mi, yoksa alan yalniz tekil uca mi
   daraltilacak?
3. G115 — Bu iki karar netlesince asagidaki maddeler ayni gorevde kalacak mi:
   `teslim_dogrula` yapi doldurma; `yapi_farki` fonksiyonu + 5 parametrik test;
   kapi `yapi_degisti` kurali; bildirim "Yapi farki" blogu; `ozet.txt` yapi farki satiri?

## Izin engelleri

yok (G115, G116, G117 — izinEngelleri listeleri bos).

## Atlananlar

yok (atlandi / zincirHatasi / teslimHatasi olan gorev yok).
