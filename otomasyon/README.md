# Gece koşusu — sertleştirme paketlerinin gözetimsiz yürütülmesi

Sertleştirme planının kalan paketlerini (FAZ 4 → FAZ 5) sen uyurken sırayla işletir.
Her paket **sıfır context'li ayrı bir Claude oturumunda** koşar; durum, context'te değil
diskte tutulur: `docs/plan/guvenilirlik-sertlestirme-uygulama-takibi.md` tek doğruluk kaynağıdır.

## Mekanizma

```
gece-kosusu.ps1 döngüsü (paket başına):
  1. takip dosyasına bak: BLOCKED var mı, [ ] paket kaldı mı?
  2. claude -p  →  .claude/skills/faz-devam   (kod + test + doküman + TEK commit, sonra durur)
  3. claude -p  →  .claude/skills/faz-denetle (AYRI temiz context; diff'i plana karşı denetler)
  4. denetim "SONUC: GECTI" ise sıradaki pakete; "RET" ise koşu durur (commit geri alınmaz)
```

Koşu şunlarda kendiliğinden durur: `BLOCKED`, denetim RET'i, FAZ 6'ya gelinmesi,
paket zaman aşımı (varsayılan 180 dk), claude'un sıfır-dışı çıkışı (kota bitmesi dahil),
`otomasyon\DURDUR` dosyasının varlığı.

## Çalıştırma

Gece koşusu (repo kökünden):

```bash
powershell -ExecutionPolicy Bypass -File otomasyon\gece-kosusu.ps1 -MaxPaket 5 -KirliAgacKabul
```

- `-MaxPaket` — bu koşuda en fazla kaç paket (varsayılan 3).
- `-KirliAgacKabul` — çalışma ağacı kirliyken başlamaya izin verir; skill kirli dosyalar
  paket kapsamındaysa **üzerine devam eder** (yarım kalmış oturumu devralma senaryosu).
  Kapsam dışı kirli dosya varsa yine BLOCKED bırakıp durur.
- İlk kullanımda gündüz, göz önünde `-MaxPaket 1` ile bir deneme koşusu yapman önerilir.

Durdurmak için (koşu sırasında, paket sınırında durur):

```bash
type nul > otomasyon\DURDUR
```

## Gece öncesi kontrol listesi

1. Docker Desktop açık (backend pytest konteynerde koşar; script stack'i `up -d` ile kaldırır).
2. Bilgisayar fişte; script sunum modunu açar ama **kapak kapatılırsa yine uyur** — kapağı açık
   bırak ya da kapak eylemini "Hiçbir şey yapma"ya al.
3. OneDrive senkronunu gece için duraklat (önerilir — repo OneDrive altında, dosya kilitleri
   ve senkron gürültüsü olabilir).
4. `claude` CLI oturumu açık ve kotan yeterli (koşu kota bitince kendiliğinden durur, iş kaybolmaz).

## Sabah kontrol listesi

1. `otomasyon\loglar\gece_*.log` — koşu özeti (kaç paket bitti, neden durdu).
2. `git log --oneline` — gece atılan commit'ler; takip dosyasındaki yeni durum notları.
3. `otomasyon\loglar\denetim_*.out.log` — denetçinin bulguları (GECTI verse de bulgu yazmış olabilir).
4. Frontend paketlerinde görsel kontrol: `npm --prefix frontend test` yeşil olsa da
   arayüzü bir kez gözle gör (banner, ErrorBoundary, taslak geri yükleme).
5. Memnunsan: `git push` → GitHub Actions (ruff) yeşilini bekle.
6. Deploy noktası hazırsa ("DEPLOY #N HAZIR" notu): mesai dışı, Claude Code oturumunda
   deploy'u başlat (bilinen "başlat" akışı — pg_dump + healthz kapısı + rollback hedefi).

## Guardrail'ler (bilerek böyle)

- Runner ve skill **asla**: `git push`, `ssh`, `gcloud`, deploy/rollback, `git reset --hard`,
  `docker compose down -v` çalıştırmaz — bunlar `--disallowedTools` ile de kilitli.
- Bir çağrı = bir paket; skill sonraki pakete geçmez, sırayı script yönetir.
- Denetçi oturumu yazma izni olmadan koşar (edit isteği otomatik reddedilir).
- FAZ 6 (docs reorg + CLAUDE.md) gözetimsiz koşuya **kapalı** — takip dosyasının kendisini
  taşıyacağı için gündüz, seninle yapılır.
- `BLOCKED` çözüldüğünde takip dosyasındaki satırı sil ya da "çözüldü" diye yeniden yaz —
  runner dosyada `BLOCKED` kelimesini gördüğü sürece başlamaz.

---

# Kuyruk koşusu (v2) — gelecek planlar için kalıcı sistem

> **DURUM (2026-08-18): bu koşucu ÇALIŞAMIYOR.** Kurumsal ayar `claude` CLI erişimini
> kapattı; `kuyruk-kosusu.ps1` görevleri `claude -p` süreçleri açarak koşturur ve ilk
> çağrıda düşer (G060'ın BLOKE sebebi buydu). Güncel koşucu aşağıdaki **v3 Workflow
> koşucusu**dur; bu bölüm mekanizma referansı olarak ve CLI geri açılırsa diye korunuyor.

`gece-kosusu.ps1` sertleştirme planına özeldir ve onu bitirecek. Ondan sonraki tüm planlar
için genel sistem: **görev kuyruğu + şerit bazlı paralellik**.

```
/plan-hazirla  (gündüz, seninle: planı görevlere böler, bağımlılık grafiğini çıkarır, ONAYLATIR)
      ↓  gorevler/KUYRUK.md + gorevler/gorev/<id>.md
kuyruk-kosusu.ps1  (gece: şeritlere dağıtır)
      ├─ backend şeridi  → ANA dizinde, seri (konteyner ./backend'i bind-mount eder —
      │                    worktree'de backend testi YANLIŞ kodu test ederdi)
      ├─ frontend şeridi → C:\dev\hukudok-wt\<id> worktree'sinde (npm ci + vitest, paralel)
      └─ docs şeridi     → worktree'de, test yok
her biten görev: temiz-context denetim → GECTİ → worktree dalı ana dala TEK TEK merge →
merge sonrası ana dizinde tam vitest (kırmızıysa merge geri alınır) → KUYRUK'ta [x]
```

```bash
powershell -ExecutionPolicy Bypass -File otomasyon\kuyruk-kosusu.ps1 -MaxGorev 6 -MaxSaat 7
```

- Format/kurallar: [gorevler/README.md](../gorevler/README.md). KUYRUK satırına dokunan tek
  yazar runner'dır; işçiler yalnız kendi `gorev/<id>.md` dosyasına rapor yazar (çakışma sıfır).
- Başarısızlıklar KUYRUK satırına ` | BLOKE(sebep)` olarak işlenir; worktree/dal incelemen
  için korunur. Çözünce eki sil.
- Worktree kökü bilinçli olarak **OneDrive dışında** (`C:\dev\hukudok-wt`) — senkron
  gürültüsü ve dosya kilidi riski olmasın diye.
- Her gece otomatik başlatmak istersen (isteğe bağlı):

```bash
schtasks /create /tn hukudok-kuyruk /sc daily /st 01:00 /tr "powershell -ExecutionPolicy Bypass -File \"C:\Users\ilkeb\OneDrive\Masaüstü\hukudok-automator-main\otomasyon\kuyruk-kosusu.ps1\" -MaxSaat 6"
```

- İlk kullanımdan önce **gündüz pilotu şart**: 2-3 küçük gerçek görevle (`-MaxGorev 3`)
  göz önünde bir koşu yap — runner'ın merge/worktree akışı ilk kez gerçek işte kanıtlanacak.

## Neden backend şeridi paralel değil? (v1'in "neden paralel değil"i)

Sertleştirme planının kalan paketleri için paralel worktree bilinçli olarak kullanılmıyor:
1. Her paket aynı takip dosyasına yazıyor → her birleşmede çakışma garanti.
2. 4-B'nin backend ucu (analiz "failed" terminal olayı) ile 5-B (/process Pydantic şeması,
   durum kodları) aynı dosyalara (`routes/processing.py`, `analyzer.py`) dokunuyor;
   4-A/4-B/4-C üçü de `api.ts`–`Index.tsx` hattında kesişiyor.
3. Backend pytest tek compose stack'inde koşuyor — iki paralel oturum aynı konteyneri ve
   lokal PG'yi paylaşır, testler birbirini bozar (flaky → model olmayan hatayı "düzeltir").
4. Seri koşu zaten yetişiyor: kalan 5 kod paketi ≈ 1-2 gece.

---

# Kuyruk koşusu (v3) — Workflow koşucusu (GÜNCEL)

CLI erişimi kurumsal ayarla kapanınca (2026-08-18, G060 BLOKE'si) koşucu, ayrı `claude -p`
süreçleri yerine **açık bir Claude Code oturumunun İÇİNDE Workflow aracıyla** koşan çok-ajanlı
bir betiğe taşındı: [`.claude/workflows/gece-kuyrugu.js`](../.claude/workflows/gece-kuyrugu.js).
Desen, kolay-ilan projesinin gece hattından uyarlandı; **kuyruk sözleşmesi değişmedi** —
`KUYRUK.md` satır formatı, `gorev/<id>.md` dosyaları, bant kuralları, `gorev-devam` /
`gorev-denetle` skill sözleşmeleri ve ` | BLOKE(sebep)` işaretleri aynen geçerli.
`/plan-hazirla` çıktısı olduğu gibi koşulur.

## Mekanizma (görev başına zincir)

```
Plan (KUYRUK.md + gorev/<id>.md + ön kontroller → bağımlılık dalgaları)
  └─ her görev:
     Uygula   → gorev-devam sözleşmesi + ilerleme-kapılı döngü (hata "parmak izi"
                aynı kalırsa erken durur; sert tavan 8 tur)
     Teşhis   → takılırsa TAZE bağlamda kök neden + farklı yaklaşımla 1 yeniden deneme
                (üçüncü cevabı en değerlisi: "sorun görev tanımında" → sabaha SORU)
     Kapı     → MEKANİK: test bütünlüğü (silinen/gevşetilen test, skip/xfail,
                pyproject-vitest zayıflatma, noqa/ts-ignore) + kırmızı-yeşil kanıtı
                (eklenen test, taban koddan açılan kanıt worktree'sinde KOŞULUR ve
                kırmızı olmak ZORUNDADIR; backend kanıtı DATABASE_URL'siz tek seferlik
                `docker run` konteynerinde — dbtest'ler 3-ortam kuralı gereği SKIP)
     Denetle  → gorev-denetle sözleşmesi, temiz context (GECTI/RET + bulgular)
     Onar     → yalnız RET'te TEK hak: bulguyu önce doğrula, düzelt, YENİDEN denetim
     Teslim   → backend: KUYRUK'ta [x] (iş zaten main'de). frontend/docs: yerel
                `merge --no-ff` + ana dizinde TAM vitest (kırmızıysa merge geri alınır,
                worktree korunur, BLOKE) → [x] + pathspec commit
Rapor (otomasyon/loglar/kuyruk-workflow_<tarih>.md + commit)
```

- **Bant kuralları aynı:** backend ana dizinde ve SERİ (lokal konteyner
  `docker-compose.override.yml` ile `./backend:/app` bind-mount eder — pytest yalnız ana
  dizini doğru test eder); frontend/docs `C:\dev\hukudok-wt\<id>` worktree'sinde
  (OneDrive dışı), dal `gorev/<id>`.
- **Ana dizin mutex'i:** backend görev zinciri bütünüyle + tüm merge/işaretleme adımları
  tek sıradan geçer; worktree bantlarının uygulaması paralel kalır.
- **`Durum: TAMAM` kısayolu:** görev dosyasının Rapor'unda "Durum: TAMAM" yazan ama
  KUYRUK'ta açık kalan görev (ana oturumda bitirilmiş iş — ilk örnek G060) yeniden
  UYGULANMAZ; doğrudan bağımsız denetime girer, GECTI ise işaretlenir.
- Push/PR YOK — kolay-ilan uyarlamasından bilinçli fark: bu projede push + deploy daima
  insan kararı (CLAUDE.md; agent push'u auto-mode sınıflandırıcısınca zaten engelli).

## Çalıştırma

Önerilen: açık bir oturumda **`/gece-kuyrugu`** skill'i (ön kontrolleri + çağrıyı + sabah
özetini o yönetir). Elle: Workflow aracı, `scriptPath: .claude/workflows/gece-kuyrugu.js`,
`args: { "tarih": "YYYY-AA-GG" }`. Parametre tablosu skill dosyasında.

- **İlk koşu ve her yeni plandan sonraki ilk koşu KURU olmalı** (`kuru: true`) — plan ve
  dalgalar yazılmadan görünür.
- Koşu sırasında ana dizinde başka oturum/koşucu ÇALIŞMAMALI (tek koşucu kuralı).
- Oturum açık kalmalı; makine uykusu için sunum modu (skill adım 1.4).

## Sabah kontrol listesi

1. `otomasyon/loglar/kuyruk-workflow_<tarih>.md` — özet, **Bloke** ve **Karar bekleyenler**
   bölümleri (en değerli kısım), **İzin engelleri**.
2. `gorevler/KUYRUK.md` — yeni `[x]`'ler ve ` | BLOKE(sebep)` ekleri (çözünce eki elle sil).
3. `git log --oneline` — görev commit'leri + `chore: kuyruk durumu` işaretleri.
4. `C:\dev\hukudok-wt\` — bloke görevlerin korunan worktree'leri (incele, birleştir/sil).
5. Memnunsan push + CI + (nokta hazırsa) deploy — hepsi senin kararın.

## Guardrail'ler (bilerek böyle)

- Koşucu ve tüm ajanları **asla**: `git push`, `ssh`, `scp`, `gcloud`, deploy/rollback,
  `git reset --hard` (tek istisna: teslim adımının kendi kaydettiği SHA'ya merge geri alma),
  `docker compose down -v`, KUYRUK'a işçi eliyle dokunma.
- **İzin listesi bilinçli genişletilmedi.** Engellenen komutlar rapora "İzin engelleri"
  olarak düşer; `.claude/settings*.json` YALNIZ bu ölçümle ve elle genişletilir — koşucu
  kendi izin dosyasına dokunamaz (kolay-ilan hattının "ajan kendi iznini genişletemez"
  ilkesi).
- Token bütçesi tabanı: kalan bütçe eşiğin altına inince yeni görev başlatılmaz; kuyruk
  açık kalır, yarım iş bırakılmaz.
