# Gece Kuyrugu (workflow) · 2026-08-20b

## Ozet
3 gorev alindi · 2 isaretlendi · 1 bloke · 0 atlandi (tavan nedeniyle atlanan: yok)

## Isaretlenenler

| Gorev | Bant | Commit | Kapi | Denetim | Not |
| --- | --- | --- | --- | --- | --- |
| G085 — Gece tarayici 06:00 TR: yaklasan sure + durusma bildirimleri (T-15/7/3/1) | backend | `058b09d` | GECTI (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI (5 bulgu) | 2 tur. Son parmak izi: 1890 passed / 3 skipped, ruff temiz, mypy temiz. Merge yapilmadi, entegrasyon uygulanamaz (ana repoda calisildi). |
| G083 — Topbar zil paneli: dropdown + okunmamis rozeti + 60 sn polling | frontend | `41eea98` | GECTI (test temiz, kirmizi-yesil kanitlandi, ihlal yok) | GECTI (4 bulgu) | 1 tur. Son parmak izi: 430 passed (32 dosya), lint 0 error / 22 onceden var olan warning, tsc exit 0. Merge yapildi, entegrasyon yesil, worktree `C:/dev/hukudok-wt/G083` temizlendi. |

### G085 notlari
- Tek bilincli sapma: `dedupe_key` deseninin SONUNA alici e-postasi eklendi
  (`deadline:{sd_id}:{esik}:{email}` / `hearing:{h_id}:{esik}:{email}`). Gorev
  tanimindaki onek aynen korunuyor; gerekce G082'de odenen ders — dedupe_key GLOBAL
  tekil ve bir satir TEK `recipient_email` tasiyor, ciplak anahtar iki sorumlulu
  davada ikinci avukatin bildirimini sessizce yutardi (test ile kilitlendi).
- Esik kurali "kalan gune uyan EN DAR esik": bir gece kacirilinca uyari dusmez, ilk
  goruste de dort bildirim birden acilmaz.
- Zamanlayici kaydi (`is_leader` icinde, 06:00 TR, `replace_existing` +
  `misfire_grace_time`) `api.py` kaynagi AST ile parse edilerek denetleniyor; mevcut
  iki job'in saati de test ile kilitli.
- `services.notifications._case_label` private olarak import edildi (dosya kapsami
  disinda oldugu icin public'e cevrilemedi; `lawyer_resolver` deseniyle ayni gerekce).
- Yeni bagimlilik yok — saat dilimi icin stdlib `zoneinfo` (konteynerde dogrulandi),
  `pytz` yalniz apscheduler'in transitif bagimliligi.
- Kapsam disi kirli dosyalar (`.claude/settings.local.json`, `.claude/launch.json`)
  oturum basinda da kirliydi; dokunulmadi, commit'e girmedi.
- Veri gercegi: kaynak tablo bugun 750/4.971 dolu ve hepsi YEREL → panel ilk gun bir
  avuc uyari gosterir.

### G083 notlari
- Kurulum: `git worktree add -b gorev/G083 C:/dev/hukudok-wt/G083 HEAD` + `npm ci`
  sorunsuz; eski worktree yoktu. `docker compose` HIC kullanilmadi (frontend bandi,
  host'ta kosuldu).
- Mevcut hicbir test degistirilmedi/silinmedi; skip/only/xfail, noqa/ts-ignore/
  eslint-disable yok.
- `PlaceholderBadge.tsx` "Dokunma" listesinde oldugu icin SILINMEDI — iki dashboard
  sayfasi kullanmaya devam ediyor, yalniz Topbar'daki kullanimi kalkti.
- `lib/api.ts`'e dokunulmadi (useAuthRequest/apiClient deseni yeterli oldu).
- Tasarim: sayac istegi basarisiz olursa rozet sifirlanmaz (son bilinen deger kalir),
  liste hatasi bos listeye cevrilmez (ayri `role=alert` govdesi + "Tekrar dene"),
  `case_id`'siz bildirimde panel kapanmaz.
- Izlenecek: backend `created_at` naive ISO donuyor, `formatAgo` bunu tarayici yerel
  saati sayar — uca Z/offset eklenirse goreli zaman kayar.
- Push/ssh/deploy YAPILMADI, KUYRUK.md'ye dokunulmadi.

## Bloke

### G086 — "Sure Uyarilari" (avukat) + "Sureli Isler" (idari) panelleri · bant: frontend

- **Durma sebebi:** `kapsam-disi-gerekti` — gorevin idari yarisi icin var olmayan iki
  backend ucu yazilmasi gerekiyordu. `isaretlendi=false`, `uygulandi=false`, gorev
  TAMAMLANMADI. (Blokede kayitli sebep: "kapsam disi dosya gerekti — gorev
  dosyasindaki DURUM satirina bak".)
- **Son parmak izi (yesil):** 34 dosya / 471 test passed, 0 failed; lint 0 error + 22
  warning (taban ile ayni, yeni dosyalarda uyari yok); `tsc -b --force` exit 0.
- **Commit:** `a74909b` (kismi is; kapi ve denetim KOSMADI — ikisi de `null`).
- **Denenen yaklasimlar:**
  1. Tur 1: panel + saf yardimcilar yazildi; `npm test` → 1 kirmizi
     (`DeadlineWarningsPanel`: govdedeki "Son gun: ... (99 gun kaldi)" donmus metni
     ekranda kaliyor, taze rozetle celisiyordu).
  2. Tur 2: kokten duzeltme — `parseDeadlineBody` artik donmus geri sayim parantezini
     (`stripFrozenCountdown`, dar kalip) dusuruyor; `deadlineIdentity` sadelesti.
     `npm test` → 471 passed, lint 0 error, tsc exit 0.
  3. Idari panel icin backend ucu arandi (`routes/notifications.py`,
     `routes/admin.py`, `api.py`) — baskasinin bildirimlerini veren uc ve
     `unresolved_targets` ucu YOK; backend yazmak bant/kapsam disi oldugu icin bolum
     degistirilmedi.
- **Teshisin kok nedeni:** G086'nin idari yarisi iki backend ucuna bagimli ve bu uclar
  planda hicbir goreve yazilmamis — G080 `unresolved_targets` ve G081 notifications
  yalniz servis / kisisel uc duzeyinde kaldi. Bant frontend, dogrulama host'ta vitest;
  backend yazilsaydi ne pytest ne ruff/mypy kosturulabilirdi (docker compose yasak) —
  sahte yesil uretmemek icin `IdariDashboard.tsx`'e hic dokunulmadi.
- **Worktree:** `C:/dev/hukudok-wt/G086` (dal `gorev/G086`) — KORUNUYOR, temizlenmedi.
  `npm ci` temiz kurulu, `docker compose` kullanilmadi. Merge yapilmadi, entegrasyon
  uygulanamaz.
- **Onerilen sonraki adim** (takip gorevleri; KUYRUK.md'ye Teslim/planlayici yazar,
  bu koşuda dokunulmadi):
  1. bant:backend — `GET /api/notifications/overview`: sure/durusma bildirimlerinin
     `recipient_email` + `read_at` + `due_date` + `case_id` ozeti, idari/admin yetki
     kapisiyla; kisisel uclarin sahiplik kurali GEVSETILMEZ.
  2. bant:backend — `GET /api/notifications/unresolved-targets`:
     `unresolved_targets(db)` ciktisi (bugun 97 dava).
  3. bant:frontend — G086'nin idari yarisi: iki ucu tuketen "Sureli Isler" paneli +
     `PlaceholderBadge`'in kaldirilmasi.
- **Izlenecekler:** panel uctan son 200 bildirimi cekip istemcide suzuyor (ucta `type`
  filtresi yok); hacim artarsa uca `type=` filtresi gerekir. Satir tiklamasi bildirimi
  okundu ISARETLEMIYOR (yalniz dava kartina gider) — okuma zil panelinin isi.

## Karar bekleyenler

`teshis.gorevTanimiHatali=true` isaretli gorev YOK; dolayisiyla `insanaSoru` kaydi da
yok. Asagidaki sorular G086'nin `kabulKarsilanmayan` maddelerinden turetilmistir:

1. **SORU (G086):** Idari panelde "hangi sure kime bildirildi ve okundu mu"
   (`recipient_email` + `read_at`) gosterilecekse, `GET /api/notifications` sahiplik
   kurali (`routes/notifications.py:_visible`, yalniz istegi yapan kullanicinin
   satirlari) korunarak AYRI bir yonetim ucu mu acilsin? (Onerilen: evet, ayri uc;
   kisisel ucun kurali gevsetilmesin.)
2. **SORU (G086):** G080'in hedefsiz sayaci (97 dava) icin
   `services/notification_targeting.unresolved_targets` fonksiyonu var ama HTTP ucu
   yok. Bu uc acilsin mi, hangi yetki kapisiyla?
3. **SORU (G086):** `PlaceholderBadge` avukat panelinde kaldirildi; idari panelde
   bolum doldurulamadigi icin DURUYOR. Idari yarim ayri bir goreve mi bolunsun, yoksa
   G086 backend uclari gelene kadar acik mi kalsin?

## Izin engelleri

Yok. (G085, G083 ve G086'nin `izinEngelleri` listelerinin ucu de bos.)

## Atlananlar

Yok. Hicbir gorev `atlandi`, `zincirHatasi` ya da `teslimHatasi` ile sonlanmadi;
tavan nedeniyle atlanan gorev de yok.

---

### Hattin dogru calistiginin kaniti
G086'da testi degistirmeden gecilemedi; gorev tanimi (idari yarim icin var olmayan
backend uclari) gozden gecirilmeli. Panel bu yuzden yarim birakildi ve isaretlenmedi —
sahte yesil uretilmedi.

### Plan uyarilari (kosucudan)
- G086 bagimli G083 ve G085'e; ikisi de acikti — ayni gecede sirali kosulmali ya da
  atlanmali (sirali kosuldu).
- G085 bagimliliklari (G080, G081, G084) KUYRUK'ta `[x]` isaretli, hazirdi.
