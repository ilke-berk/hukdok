---
name: ci-kontrol
description: Push ÖNCESİ GitHub CI'nın (.github/workflows/ci.yml) koştuğu adımların aynısını lokalde koşar, push SONRASI CI sonucunu izler, kırmızıyı sınıflandırıp çözüm yolunu seçer; deploy kapısını tanımlar. Kırmızıdayken yeni iş push'lanmaz. Push/deploy BAŞLATMAZ.
---

# Görev: CI kırmızısını push'tan önce yakala, push'tan sonra izle

**Neden (2026-09-14 ölçümü):** 01.09–14.09 arası main'deki 40 CI koşusunun 9'u kırmızı.
- 4'ü **dış advisory** (npm audit geliştirme zinciri — kod değişmeden, upstream ilan çıkınca; G089 bilinçli bloklayıcı).
- 5'i **kendi hatamız**, 2 kök neden: `749e373` `tsc -b --force` koşulmadan push'landı (vite build tip
  denetlemez) ve CI kırmızıyken **Deploy #27 ile prod'a çıktı** → hotfix #28; G179/G180 script'lerinde
  `logging.basicConfig` pytest bekçisine takıldı ve kırmızıdayken **üst üste 4 push** daha gitti.
- Gece koşucusu işçileri kapıları kendi koştuğu için yeşil geçti; kırmızılar gündüz elle yapılan işlerden.

**Bu skill push/deploy BAŞLATMAZ** — push ve deploy kararı kullanıcıda (CLAUDE.md "Kod konvansiyonları").

## 1. Push öncesi — CI eşdeğeri

`ci.yml`'de yol filtresi YOK: her push'ta backend + frontend job'ları birlikte koşar. Yalnız doküman
değişse bile audit kapıları dış advisory'ye kızarabilir.

Hangi taraf değişti:

```bash
git fetch origin main
git diff --name-only origin/main...HEAD
```

- **Her push'ta:** üç audit kapısı (hızlı, ağ ister) — §1.1 adım 1 ve §1.2 adım 1-2.
- `backend/**` değiştiyse: §1.1 tamamı.
- `frontend/**` değiştiyse: §1.2 tamamı.

**Kural: bir adım kırmızıysa PUSH YOK.** Audit kırmızısı kodla ilgisiz olsa da push'u kızartır → önce §3.

### 1.1 Backend — KONTEYNERDE, ana dizinde (`ci.yml` backend job'u)

Worktree'de `docker compose` YASAK (konteyner ana dizini görür — `test-kos` tuzağı). Konteynerin güncel
kodu gördüğünden emin ol (bind-mount override yoksa önce `docker compose build backend && docker compose up -d backend`).
Dev araçları prod imajına girmez; konteyner recreate'inde uçar → önce kur:

```bash
docker compose exec -T backend pip install -q -r requirements-dev.txt
```

1. **pip-audit** (`ci.yml:78-83`; ignore listesi `backend/audit-ignore.txt`, satır tarihleri CI'da `ci.yml:58-76`
   kapısıyla ayrıca denetlenir). Konsol betiği konteyner PATH'inde YOK → `python -m pip_audit`
   (2026-09-14 doğrulandı: `No known vulnerabilities found, 2 ignored`):
   ```bash
   docker compose exec -T backend sh -c 'python -m pip_audit --strict $(grep -v "^\s*#" audit-ignore.txt | grep -v "^\s*$" | awk "{print \"--ignore-vuln \" \$1}")'
   ```
2. **ruff** — lokalde git dışı `calibration-data/` bind-mount'u var, CI'nın temiz checkout'unda yok:
   ```bash
   docker compose exec -T backend python -m ruff check . --extend-exclude calibration-data
   ```
3. **mypy:** `docker compose exec -T backend python -m mypy`
4. **pytest + kapsam kapısı** (CI ile aynı bayraklar; ekstra `-q` EKLEME — `addopts` zaten `-q`; ~5 dk):
   ```bash
   docker compose exec -T backend python -m pytest --cov=. --cov-report=term-missing:skip-covered --cov-fail-under=58
   ```
   Fark: CI ÇIPLAK postgres kullanır, lokal DB doludur (CLAUDE.md "Migrasyon op türleri" tuzağı) — migrasyon
   değiştiyse bu fark kırmızı üretebilir.

### 1.2 Frontend — HOST'ta (`ci.yml` frontend job'u)

`check-npm-audit.mjs` `audit-ignore.txt`'i ÇALIŞMA DİZİNİNDEN okur → komutlar `frontend/` içinde koşar.
`package-lock.json` değiştiyse önce `npm ci` (CI temiz kurulum yapar).

```bash
cd frontend
node scripts/check-npm-audit.mjs          # 1. prod kapısı — her seviye bloklar
node scripts/check-npm-audit.mjs --dev    # 2. geliştirme zinciri — moderate+ bloklar (G089)
npm run lint                              # 3. ESLint
npx tsc -b --force                        # 4. GERÇEK tip kapısı — çıplak `tsc --noEmit` SAHTE, `vite build` tip denetlemez
npm test                                  # 5. vitest
npm run build                             # 6. build
```

PowerShell'de `cd` kalıcıdır: `Push-Location frontend; ...; Pop-Location` kullan.

## 2. Push sonrası — sonucu izle

```bash
gh run list --commit <sha> --json databaseId,status,conclusion
gh run watch <run-id> --exit-status
```

- `success` → bitti.
- `failure` → §3. **Kırmızıdayken yeni iş push'lanmaz**; bir sonraki push düzeltme commit'idir.
- Koşu ~5-7 dk sürer; ajan oturumunda `gh run watch`'ı arka planda koştur ya da aralıklı `gh run list`.

## 3. Kırmızıyı sınıflandır

Düşen job/adım ve hata satırları:

```bash
gh run view <run-id> --json jobs --jq '.jobs[] | select(.conclusion=="failure") | .name + " :: " + ([.steps[] | select(.conclusion=="failure") | .name] | join(", "))'
gh run view <run-id> --log-failed | grep -E "FAILED|error TS|GHSA-|SÜRESİ GEÇMİŞ|Found [0-9]+ error"
```

| Düşen adım | Tür | Yol |
| --- | --- | --- |
| `npm audit (prod ...)` / `npm audit (geliştirme zinciri ...)` / `pip-audit` | Dış advisory (kod değişmemiş olabilir) | Frontend: `npm audit fix` (`--force`SUZ; package.json değişmez, yalnız lockfile) → §1.2 tamamı → tek commit. Backend: pin'i yamalı sürüme çek → §1.1. Yama YOKSA GHSA'yı ilgili `audit-ignore.txt`'e gerekçe + `Gözden geçirme: YYYY-MM-DD` ile yaz (ADR-013 K3; iki npm kapısı aynı listeyi okur). **Prod kapısı** kırmızıysa canlı bağımlılıkta açık var → öncelik yüksek. |
| `audit-ignore.txt tarih kapısı` / "SÜRESİ GEÇMİŞ" | Ignore süresi doldu | Advisory kapandıysa satırı sil; kapanmadıysa gerekçeyle yeni tarih — bilinçli uzatma, sessiz değil. |
| `ruff` / `mypy` / `ESLint` / `TypeScript kontrolü` / `Build` | Kod hatası | Hemen düzeltme commit'i → §1 → push. |
| `pytest` / `vitest` | Kod hatası ya da kararsız test | Log'daki test adına bak. Kodla ilgiliyse düzelt. Kod değişmemiş ve lokalde tekrarlanmıyorsa `gh run rerun <run-id> --failed` **bir kez**; yine kızarırsa gerçek hata say. Rerun'ı rapora/commit mesajına yaz. Testi skip etmek, silmek, gevşetmek YASAK. |
| `pytest (kapsam kapısı)` — `--cov-fail-under` | Test eklenmeden kod büyüdü | Test ekle; eşik bir TABANdır, düşürülmez (`ci.yml:91-95`). |

## 4. Deploy kapısı

Deploy edilecek SHA'nın CI koşusu `completed/success` değilse **deploy YOK** — `deploy-prosedur` §1
bu kontrolü ön koşul olarak koşar. `in_progress` → bitmesini bekle; `failure` → §3.
