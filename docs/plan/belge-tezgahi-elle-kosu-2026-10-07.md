# Belge tezgâhı — elle (sohbette) koşu rehberi (07.10.2026)

> **Amaç:** `docs/plan/pdf-araclari-plani-2026-10-07.md` planının görevlerini gece kuyruğu YERİNE kullanıcıyla
> birlikte, sohbet oturumunda koşmak. Bu dosya yeni bir sohbetin giriş noktasıdır: sıfır-context oturum önce
> `CLAUDE.md`, sonra bunu, sonra sıradaki görev dosyasını okur. Kuyruk kayıtları (`gorevler/KUYRUK.md`,
> `gorevler/gorev/G*.md`) **tek doğruluk kaynağı olarak kalır**: elle koşulan görev de orada `[x]` olur ve Rapor'u yazılır.

## Yeni sohbete yapıştırılacak açılış

```
docs/plan/belge-tezgahi-elle-kosu-2026-10-07.md dosyasını oku ve "Sıradaki görev" bölümündeki ilk açık görevle
başla. Görev dosyasındaki kabul kriterlerini birebir uygula, doğrulama komutlarını koş, tek commit at, KUYRUK'ta
[x] işaretle ve Rapor'u yaz. Bitince bu rehberin "Sıradaki görev" tablosunu güncelle ve bana özet ver; sonraki
göreve ben "devam" deyince geç.
```

## Sıradaki görev (işçi her görevden sonra günceller)

| Sıra | Görev | Bant | Bağımlı | Durum | Commit |
| --- | --- | --- | --- | --- | --- |
| 1 | G267 PDF çekirdeği `pdf/pdf_araclari.py` | backend | - | bitti | 35cebfb |
| 2 | G268 uçlar `yukle/islem/onizleme` + cache temizliği | backend | G267 | bitti | 0539ad4 |
| 3 | G282 migrasyon 61: yön/kaynak/durum + sürüm defteri | backend | - | bitti | 4ef2621 |
| 4 | G269 `karta-bagla` (kesin/taslak) + `karttan-al` | backend | G268, G282 | bitti | 66f0483 |
| 5 | G270 Belge tezgâhı sayfa iskeleti (PDF yolu) | frontend | - | bitti | fa0479b |
| 6 | G271 sayfa ızgarası | frontend | G270 | bitti | 94948c1 |
| 7 | G272 karartma + not çizim katmanı | frontend | G271 | bitti | d7c799e |
| 8 | G273 karta bağla / karttan al diyalogları + `CaseDetails` | frontend | G269, G271 | bitti | e2876ad |
| 9 | G274 doküman (PDF yolu) | docs | G272, G273 | bitti | (SHA G283 commit'inde işlenir) |
| — | **DURAK: PDF yolu gerçek girişle tarayıcıda denenir (insan adımı), sonra deploy kararı** | | | | |
| 10 | G283 kartta Gelen · Taslak · Giden | frontend | G273, G282 | açık | |
| 11 | G284 Word yaşam döngüsü uçları | backend | G282, G269 | açık | |
| 12 | G285 Word yolu ekranı | frontend | G284, G283 | açık | |
| 13 | G286 eklenti altyapısı (CSP + kimlik ÖLÇÜMÜ — kullanıcıyla) | backend | G284 | açık | |
| 14 | G287 eklenti görev bölmesi `/eklenti` | frontend | G286, G285 | açık | |
| 15 | G288 doküman (bütün) | docs | G287, G274 | açık | |

Sıra 1-4 backend'i önce bitirir ki frontend (5-8) gerçek uçlara karşı yazılabilsin — sohbette sahte API'ye gerek
yok (gece kuyruğundaki paralellik gerekçesi burada geçersiz). Yine de `types/pdfAraclari.ts` plan §3 ile birebir
kalır; backend'de sözleşmeden sapma olduysa önce plan §3 düzeltilir.

## Her görevde aynı döngü

1. **Oku:** `gorevler/gorev/<id>.md` (hedef, kabul kriterleri, dosya kapsamı, Dokunma listesi) + planın ilgili
   bölümü (§3 ya da §6.3 sözleşme). Kapsam dışına çıkma; gerekiyorsa kullanıcıya söyle, görev dosyasını güncelle.
2. **Yaz:** kod + test + (görev istiyorsa) doküman. Dosya değişikliği DAİMA Edit/Write aracıyla (PS5.1 UTF-8 tuzağı).
3. **Doğrula:** görev dosyasındaki komutlar. Backend konteynerde; **bind-mount yok** → kod değişikliği için
   `docker compose build backend && docker compose up -d backend`, sonra `docker compose exec -T backend python -m pytest`
   (ekstra `-q` EKLEME). Dev araçları konteynerde yoksa `pip install -r requirements-dev.txt`. Frontend host'ta:
   `npm --prefix frontend test`, `run lint`, `npx --prefix frontend tsc -b --force frontend`, `run build`.
4. **Commit:** TEK commit, dosya listesiyle (`git add -A` yok), mesaj Türkçe ASCII özet + gövde; `Co-Authored-By` satırı.
   Push YOK (kullanıcı kararı).
5. **Kayıt:** `gorevler/KUYRUK.md` satırı `[x]`; görev dosyasının **Rapor** bölümü: yapılanlar, kararlar, test sayıları
   (`N passed`), açık kalanlar. Bu rehberin tablosu: Durum = `bitti`, Commit = SHA. Bu kayıt değişikliği görev
   commit'ine GİRER (aynı commit).
6. **Özet:** kullanıcıya 5-8 satır: ne yapıldı, test sonucu, karar istenen nokta varsa o. "devam" bekle.

## Kırmızı çizgiler (plan ve CLAUDE.md'den)

- `/api/pdf-araclari/*` dışında uç adı icat etme; sözleşme §3/§6.3. Değişiklik planı düzeltmekle başlar.
- nginx PDF yolunda DEĞİŞMEZ (G268 bekçisi); yalnız G286 CSP'ye dokunur, üç kopya birlikte.
- Migrasyon yalnız G282 (madde 61): `columns`/`table` koşullu, kalıcı kısıt/index AYRI `("index", ...)` op'unda.
- Doctype kodları `_` pad'li — normalize etmeden karşılaştırma yok. `yon/kaynak/durum` pad'siz düz string.
- TASLAK: Hukukbot'a gitmez, bildirim üretmez, raporda giden sayılmaz (G282 filtreleri; G269/G284 testle kanıtlar).
- Kesinleştirme AYNI `case_documents` satırını günceller; `convert_pdfa_and_queue_uploads` yeni satır açtığı için
  G284'te KULLANILMAZ.
- Karartma gerçek silme (`apply_redactions`), koordinat görünür düzlem; damga DejaVuSans (`fontfile`).
- Log sözleşmesi: deneme WARNING, nihai TEK ERROR (`error_kod`). Stream sözleşmesine dokunulmaz (bu plan NDJSON kullanmaz).
- Avukat adı, ofis no, taraf anahtarı kurallarına bu plan dokunmaz; dokunan kod yazma.
- **G275 bu planın görevi DEĞİL** (lexis kademeli okuma). Word yolu G282'den başlar.

## İnsan adımları (sohbette kullanıcıyla, kuyruğa/işçiye verilmez)

- PDF yolu bitince (sıra 9 sonrası) gerçek girişle tarayıcıda zincir: yükle → birleştir → karart → indir → karta bağla →
  kartta görünür. Sonra deploy kararı (`deploy-prosedur`, mesai dışı, CI yeşil şartı).
- G286: eklenti kimlik ölçümü (NAA aynı scope?) kullanıcının Azure portal erişimiyle; gerekirse uygulama kaydına
  platform eklenir — kullanıcı yapar.
- G287 sonrası: Microsoft 365 yönetici merkezinden eklenti dağıtımı (önce test kullanıcısı, sonra herkes).
- Prod'da migrasyon (G282) deploy ile gelir; `deploy.sh` şema kapısı geçici Postgres'te dener.

## Kuyrukla birlikte yaşama

- Gece kuyruğu bu sırada da çalışabilir: Lexis bandı (G260, G261, G263-G266, G275) bu plana dokunmaz. Ama **aynı gece
  bu planın görevlerini kuyruğa KOŞTURMA** — elle koşulan görev yarımken runner aynı görevi alabilir. Gece koşusu
  başlatılacaksa önce elle koşulan görevin commit'i atılmış ve KUYRUK'ta `[x]` olmalı; ya da `/gece-kuyrugu` çağrısında
  yalnız lexis bandı seçilmeli.
- Frontend görevlerini sohbette ana dizinde koşuyoruz (worktree yok); Vite dev sunucusu MSAL'a düştüğü için ekran
  doğrulaması `npm run build` + Docker frontend imajı ile ya da test harness'ıyla yapılır (bellek: "Lokal görsel
  doğrulama · giriş duvarı").

## Bitiş ölçütü

Tablo 15/15 `bitti`, `KUYRUK.md`'de G267-G274 + G282-G288 `[x]`, her görev dosyasında Rapor dolu, planın başındaki
Durum notu G288'de güncellenmiş, insan adımları listesinde yapılanlar işaretli.
