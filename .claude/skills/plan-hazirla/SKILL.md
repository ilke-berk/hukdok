---
name: plan-hazirla
description: Bir geliştirme planını/özelliği bir-oturumluk görevlere böler, dosya kapsamı + bant + bağımlılık grafiği çıkarır, gorevler/ kuyruğuna yazar ve kullanıcıya onaylatır. Gece koşusundan ÖNCE, gündüz kullanılır.
---

# Görev: planı kuyruğa dönüştür

Kullanıcının anlattığı planı (argüman ya da sohbet) `gorevler/KUYRUK.md` + `gorevler/gorev/<id>.md`
dosyalarına dönüştür. Format ve kurallar: `gorevler/README.md` — önce onu oku.

## 1. Keşif
- Planın dokunacağı alanları belirle. Geniş keşfi Explore ajanına devret ("hangi dosyalar
  X'i yapıyor, Y nereden çağrılıyor"), ana oturuma özet dön.
- Var olan desenleri tespit et: benzer bir özellik nasıl yapılmış, hangi test dosyası kalıbı var.

## 2. Bölümleme
- Görev boyutu = bir oturum. Ölçü, sertleştirme paketlerindeki ölçüdür: **aynı dosya kümesine
  dokunan işler aynı görevde** (tek okuma turu yetsin), sığmayan iş ikiye bölünür.
- Her görev için belirle:
  - **Dosya kapsamı** (glob'lar) ve **Dokunma listesi** (kapsam dışı ama riskli komşular).
  - **Bant**: backend (ana dizin, seri — konteyner bind-mount gerçeği), frontend (worktree,
    vitest host), docs (worktree, test yok).
  - **Bağımlılıklar**: iki görev aynı dosyaya dokunuyorsa zincirle. Hub dosyalara
    (tipler/şemalar, route kayıtları, `api.ts`, migration, `package.json`) dokunan işleri ya
    tek "temel" göreve topla ya da hepsini zincirle. Şüphede zincirle.
  - **Kabul kriterleri**: denetçinin bakacağı somut maddeler; "çalışıyor" değil, "X durumunda
    Y oluyor, testi Z".
  - **Doğrulama komutları**: backend `docker compose exec -T backend python -m pytest -q`
    (+ ruff + mypy), frontend `npm --prefix frontend test`.
- Yeni bağımlılık (pip/npm paketi) gerektiren işleri ayrı, erken ve `bant:backend` (ana dizin)
  göreve koy — worktree'de paket kurulumu kalıcı olmaz.

## 3. Yazım
- Her görev için `gorevler/gorev/<id>.md` (şablon README'de; id'ler `G` + üç hane, mevcut en
  büyükten devam et). KUYRUK.md'ye satırları sırayla ekle.
- Migration içeren görevlerde sıraya dikkat: migration üreten görevler birbirine zincirlenir
  (numara çakışması).

## 4. Onay (atlama!)
Kullanıcıya şunu sun ve düzeltmelerini işle:
- Görev listesi + bağımlılık grafiği (hangi çiftler paralel koşabilecek).
- Kaç gece süreceği tahmini (paralellik hesaba katılmış).
- Riskli gördüğün noktalar ("şu iki görevin bağımsızlığından emin değilim" gibi).
Onay gelmeden gece koşusu önerme; onaydan sonra çalıştırılacak komutu hatırlat:
`powershell -ExecutionPolicy Bypass -File otomasyon\kuyruk-kosusu.ps1`
