---
name: gorev-devam
description: Kuyruktan verilen TEK görevi uçtan uca bitirir (kod+test+rapor+tek commit). Bulunduğu dizinde (ana repo ya da worktree) çalışır; KUYRUK.md'ye dokunmaz; deploy/push yapmaz.
---

# Görev: verilen kuyruk görevini bitir

Prompt'un sonunda `GOREV: <id>` verilir. Tek çağrı = o TEK görev. Bitince (commit dahil) dur.

## 1. Bağlamı kur
- `gorevler/gorev/<id>.md` dosyasını oku: hedef, kabul kriterleri, dosya kapsamı, doğrulama.
- Repo kökündeki `CLAUDE.md` varsa oku. Görev dosyasının işaret ettiği ek bağlam dışında
  arşiv/plan dosyası açma.
- **Bulunduğun dizin çalışma alanındır** — worktree olabilir. Başka dizine (ana repoya) geçme,
  `git worktree` komutları kullanma; dallama/birleştirme runner'ın işi.

## 2. Çalışma ağacı
- `git status --porcelain`: kirli dosyalar görev kapsamındaysa önceki yarım oturumun işidir —
  OKU ve üzerine devam et, ezme. Kapsam dışı kirli dosya varsa (worktree'de olmaz, ana dizinde
  olabilir): dokunma; görev dosyasına `DURUM: BLOKE — kapsam dışı kirli dosyalar: <liste>` yaz,
  kod commit'leme, son mesajında `BLOKE` geçir, dur.

## 3. Uygula
- SADECE görevin dosya kapsamına dokun; "Dokunma" listesindeki dosyalara ihtiyaç doğarsa
  değişiklik yapma → BLOKE bırak (sebep: hangi dosya, neden gerekti). Bu, planlayıcının
  bağımlılık grafiğini korur.
- Dosya değişikliği daima Edit/Write tool ile (PS5.1 shell yazımı Türkçe içeriği bozar).
- Kapsam dışı ciddi bulguyu düzeltme; görev raporuna `NOT:` olarak yaz.
- Log sözleşmesi: deneme-düzeyi hatalar WARNING, nihai başarısızlık TEK ERROR.

## 4. Doğrula (bant kuralları kritik)
- **bant:backend** (ana dizindesin): `docker compose exec -T backend python -m pytest -q` +
  konteynerde ruff + mypy.
- **bant:frontend** (worktree'desin): `npm --prefix frontend test`. **`docker compose` komutları
  YASAK** — konteyner ANA dizini bind-mount eder, senin worktree kodunu test etmez; sonuç
  yanıltıcı olur.
- **bant:docs**: test yok; iç tutarlılık (bozuk link, yanlış yol) kontrolü yeterli.
- Kırmızı → düzelt. Düzeltemiyorsan: kod commit'leme, görev dosyasına `DURUM: BLOKE — <sebep>`
  yaz, son mesajında `BLOKE` geçir, dur.

## 5. Kapat
- Görev dosyasının **Rapor** bölümünü doldur: yapılanlar, alınan kararlar + gerekçeleri, test
  sonuçları (sayılarla), izlenecekler. `KUYRUK.md`'ye DOKUNMA — işaretlemeyi runner yapar.
- Kod + görev dosyası TEK commit: `feat: <özet> (<id>)` (içeriğe göre fix/refactor öneki) +
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Yalnız dokunduğun dosyaları
  `git add` et; `git add -A` yasak.
- Son mesajında: görev id'si, commit hash'i, test sonuçları, izlenecekler. Sonraki göreve geçme.
- Son mesajının EN SON SATIRI kesinlikle şu ikisinden biri olsun (koşucu yalnız bu satıra bakar;
  metnin başka yerinde "BLOKE" kelimesini serbestçe kullanabilirsin):
  - `GOREV-SONUC: TAMAM`
  - `GOREV-SONUC: BLOKE — <tek cümle sebep>`

## Koşulsuz yasaklar
`git push`, `ssh`, `scp`, `gcloud`, deploy/rollback scriptleri, `git merge`, `git worktree`,
`git reset --hard`, `git checkout`/`restore` ile değişiklik silme, `docker compose down -v`,
KUYRUK.md'yi değiştirmek, başka görevin dosyalarına dokunmak.
