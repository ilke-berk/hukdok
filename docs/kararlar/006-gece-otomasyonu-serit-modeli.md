# 006 — Gece otomasyonunda şerit (bant) modeli: backend ana dizinde seri

> Son doğrulama: 2026-08-11 · 2eade56

- **Durum:** kabul
- **Bağlam:** Gece kuyruğu (`gorevler/KUYRUK.md`) işleri paralel yürütmek ister; git
  worktree'leri bunu ucuza sağlar. Ancak backend testleri konteynerde koşar ve konteyner
  **ana dizini** bind-mount eder — bir worktree'de yapılan değişikliği görmez.
- **Karar:** Her görev bir **şerit**e (bant) atanır; şerit başına aynı anda en fazla bir
  görev koşar (`otomasyon/kuyruk-kosusu.ps1`):

  | Şerit | Çalışma alanı | Doğrulama |
  | --- | --- | --- |
  | `backend` | **ANA dizin, seri** | `docker compose exec -T backend python -m pytest` + ruff + mypy |
  | `frontend` | ayrı git worktree | `npm --prefix frontend test` (host'ta) |
  | `docs` | ayrı git worktree | test yok, iç tutarlılık kontrolü |

- **Gerekçe:** Script'in kendi açıklaması: `backend -> ANA dizinde kosar (konteyner
  ./backend'i bind-mount eder; pytest yalniz ana dizindeki kodu dogru test eder - bu yuzden
  backend seridir, seri'dir)`. Bunun doğal sonucu işçi talimatında yasak olarak yazılıdır:
  `bant:frontend` görevlerinde **`docker compose` komutları yasaktır** — "konteyner ANA
  dizini bind-mount eder, senin worktree kodunu test etmez; sonuç yanıltıcı olur"
  (`.claude/skills/gorev-devam/SKILL.md:34-36`).
- **Reddedilenler:**
  - *Her görev için worktree + kendi compose stack'i* — port çakışması, imaj/DB
    çoğaltması ve OneDrive altında disk maliyeti; tek makinede karşılığı yok.
  - *Backend işlerini de worktree'de koşturmak* — testler ana dizindeki (eski) kodu test
    ederdi; **yeşil ama anlamsız** sonuç, en tehlikeli başarısızlık biçimi.
- **Sonuçları:** Gerçek paralellik yalnız şerit çiftlerinden gelir (backend×frontend,
  backend×docs, frontend×docs). Aynı dosyaya dokunacak iki görev asla paralel olmaz —
  planlayıcı bunları `bagimli:` ile zincirler.
- **İlgili:** [`docs/mimari/deploy-ve-altyapi.md`](../mimari/deploy-ve-altyapi.md),
  `gorevler/README.md`, `otomasyon/README.md`
