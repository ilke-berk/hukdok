---
name: test-kos
description: İki test paketini doğru yerde koşar — backend konteynerde (pytest+ruff+mypy), frontend host'ta (vitest); bind-mount/worktree tuzaklarına karşı uyarılı.
---

# Görev: testleri doğru yerde koş

## Backend — KONTEYNERDE (host Python uyumsuz; imaj python:3.10-slim)

Stack ayakta değilse önce: `docker compose up -d`

```bash
docker compose exec -T backend python -m pytest
```

- Komuta ekstra `-q` EKLEME: `backend/pyproject.toml` `addopts = "-q"` içerir; ikinci
  `-q` özet satırını ("N passed") yutar ve sonuç okunamaz.
- Taban (2026-08-11): **859 passed, 2 skipped**. Sayı tabanın ALTINA düşerse kırmızı bayrak —
  test silme/skip/gevşetme yasak.

Ruff + mypy (dev araçları prod imajına GİRMEZ — `requirements-dev.txt`; konteyner
recreate'inde uçar, gerekirse yeniden kur):

```bash
docker compose exec -T backend pip install -r requirements-dev.txt
docker compose exec -T backend python -m ruff check .
docker compose exec -T backend python -m mypy
```

- mypy kapsamı bilerek dar: yalnız `managers/ routes/ config/` (`backend/pyproject.toml:35`).

## Frontend — HOST'ta

```bash
npm --prefix frontend test
```

(`vitest run` koşar; 2026-08-11: **299 passed / 23 dosya**.) Gerekirse:
`npm --prefix frontend run lint`, `npm --prefix frontend run build`.

## Tuzaklar

- **Worktree'de `docker compose` YASAK:** konteyner ANA dizini mount eder (lokal
  `docker-compose.override.yml` → `./backend:/app`); worktree'den koşulan konteyner testi
  ana dizindeki kodu test eder — sonuç YANILTICI. Worktree'de yalnız frontend/vitest anlamlı.
- **Base compose'da mount YOK:** override dosyası olmayan ortamda (ör. prod) konteyner
  İMAJDAKİ kodu koşar; kod değişikliği için rebuild şart (bkz. `CLAUDE.md` Kritik tuzaklar).
- Sonucu daima sayılarla raporla (kaç passed/skipped, ruff/mypy çıktısı).
