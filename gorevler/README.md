# Görev kuyruğu sistemi

Gelecek geliştirme planlarının **kalıcı yürütme sistemi**. Sertleştirme planındaki
"takip dosyası + bir oturum = bir paket" deseninin genelleştirilmiş hali:

- **`KUYRUK.md`** — sıra ve durum (tek doğruluk kaynağı). Yalnız runner ve planlayıcı yazar.
- **`gorev/<id>.md`** — her görevin tanımı: hedef, kabul kriterleri, dosya kapsamı, doğrulama
  komutları. İşçi oturumu raporunu bu dosyanın "Rapor" bölümüne yazar (KUYRUK'a asla dokunmaz —
  paralel çalışmada çakışma çıkmaması bu sayede garanti).

Akış: `/plan-hazirla` (gündüz, seninle) → onay → `otomasyon\kuyruk-kosusu.ps1` (gece, gözetimsiz).

## Arşivleme kuralı

**Bir plan kapandığında o planın görev dosyaları [`docs/arsiv/gorevler/`](../docs/arsiv/gorevler/README.md)
altına `git mv` ile taşınır** (silinmez — rapor bölümleri kararların gerekçesini taşıyan
kurumsal kayıttır; `git mv` sayesinde `git log --follow` geçmişi izlemeye devam eder).

- **`gorevler/gorev/` yalnız AÇIK işleri gösterir.** Amaç çalışma dizininin okunabilirliği:
  sıfır-context bir oturum kapanmış onlarca dosyayı taramasın.
- **`KUYRUK.md`'deki satırlar KALIR** — taşınmaz, silinmez. Kısa satırlardır ve sürecin
  izidir: hangi görev hangi plana aitti, hangi sırayla koştu, ne zaman `[x]` oldu.
- Taşıma bir **docs bandı görevi** olarak kuyruğa girer (ilk örnek: G029). Satır sayısını
  azaltmaz, yalnız çalışma dizinini sadeleştirir.

## KUYRUK.md satır formatı (runner bunu parse eder — bozma)

```
- [ ] G001 | bant:frontend | bagimli:- | Kısa başlık
- [ ] G002 | bant:backend | bagimli:- | Kısa başlık
- [ ] G003 | bant:frontend | bagimli:G001,G002 | Kısa başlık
```

- `[ ]` açık, `[x]` bitti (runner işaretler, işçi değil).
- `bant:` üç değer alır — **backend**: ana dizinde koşar (konteyner ana dizini bind-mount
  ettiği için pytest yalnız orada doğru kodu test eder; bu yüzden backend seri'dir);
  **frontend**: worktree'de koşar (vitest host'ta kendi `node_modules`'üyle);
  **docs**: worktree'de koşar, test yok.
- `bagimli:` virgüllü görev id'leri ya da `-`. Bağımlılığı bitmemiş görev başlatılmaz.
- Runner başarısızlıkta satır sonuna ` | BLOKE(sebep)` ekler; `BLOKE` içeren satır bir daha
  seçilmez. Çözünce eki elle sil.

## gorev/<id>.md şablonu

```markdown
# G001 — Kısa başlık

- **Bant:** frontend
- **Bağımlı:** -
- **Dosya kapsamı:** frontend/src/lib/upload/**, frontend/src/components/Upload*.tsx
- **Dokunma:** frontend/src/lib/api.ts, frontend/src/types/** (gerekiyorsa BLOKE bırak)

## Hedef
İki-üç cümle: ne yapılacak, neden.

## Kabul kriterleri
- [ ] Somut, denetlenebilir maddeler (denetçi bunlara bakar)

## Doğrulama
- `npm --prefix frontend test`
- `npm --prefix frontend run lint`
- `npx --prefix frontend tsc -b --force frontend`

## Rapor
(işçi oturumu doldurur: yapılanlar, kararlar, test sonuçları, izlenecekler)
```

### Frontend tip denetimi: çıplak `tsc --noEmit` YAZMA

`frontend/tsconfig.json` solution-style'dır (`"files": []` + `references`), bu yüzden
çıplak `npx tsc --noEmit` **hiçbir dosyayı denetlemez ve tip hatası dururken bile
exit 0 döner** (G026 bulgusu, G037'de kasıtlı hatayla kanıtlandı). Görev doğrulama
komutu olarak daima referansları izleyen biçimi yaz:

```
npx --prefix frontend tsc -b --force frontend                    # app + node, ikisi de
npx --prefix frontend tsc --noEmit -p frontend/tsconfig.app.json # yalnız src/
```

(`npx --prefix` yalnız `node_modules/.bin` arama yerini değiştirir, **çalışma dizinini
değiştirmez** — bu yüzden proje yolu repo köküne göre `frontend`/`frontend/...` yazılır.
Yolu düşürürsen tsc kökte `tsconfig.json` arar ve TS5083 ile patlar.)

`npm run build` (`vite build`) tip denetimi YAPMAZ — esbuild yalnız transpile eder.
Tip kapısı tek yerde: yukarıdaki komut ve CI'ın "TypeScript kontrolü" adımı.

## Paralellik kuralları (planlayıcı bunlara uyar)

1. **Aynı dosyaya dokunacak iki görev asla paralel olmaz** → `bagimli` ile zincirle.
2. **Hub dosyalar** (tip/şema tanımları, route kayıtları, `api.ts`, `index.ts` export'ları,
   migration'lar, `package.json`) ya önce tek bir "temel" görevde dondurulur ya da dokunan
   her görev birbirine zincirlenir.
3. Görev boyutu = **bir oturum** (sertleştirme paketi ölçüsü: aynı dosya kümesi, tek okuma
   turu). Sığmayacak iş ikiye bölünür.
4. Backend bandında paralellik yok (tek compose stack'i); gerçek paralellik backend×frontend
   ve frontend×docs çiftlerinden gelir.
5. Bağımlılık şüphesinde zincirle — yanlış "bağımsız" işareti gece merge çakışması üretir,
   yanlış "bağımlı" işareti sadece birkaç saat kaybettirir.
