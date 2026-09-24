---
name: bagimlilik-denetle
description: Aylık bağımlılık denetimi — Python/npm paketleri ve Docker imajlarında yeni sürümleri bulur, sürüm notlarını okuyup kodumuza etkisini tartar, GÜVENLİ sınıftakileri ayrı dalda uygulayıp tüm test kapılarından geçirir, tek commit + tarihli rapor bırakır. Major/altyapı atlamalarını UYGULAMAZ, önerir. Push/deploy YAPMAZ.
---

# Görev: bağımlılıkları denetle, güvenli olanları uygula, gerisini raporla

**Neden (2026-09-24):** CI yalnız güvenlik AÇIĞINI denetler (`pip-audit`, `frontend/scripts/check-npm-audit.mjs`,
`audit-ignore.txt`); "daha yeni sürüm var mı, bizimle uyumlu mu" denetimi yoktu. Dependabot bilinçli kurulmadı:
sürüm notunu okuyup kod etkisini tartan yargı bu skill'dedir. Zamanlayıcı ayda bir koşar (her ayın 1'i);
elle de `/bagimlilik-denetle` ile çağrılabilir.

**Sınırlar:** push YOK, deploy YOK, ssh YOK (CLAUDE.md "Kod konvansiyonları"). main'e commit YOK — iş
`bagimlilik/YYYY-MM` dalında kalır, birleştirme kullanıcı kararıdır. Test silme/gevşetme/skip YASAK.

## 0. Ön kontrol — geçmezse DUR

```bash
git status --porcelain                 # .claude/ altı dışında izlenen değişiklik varsa DUR
git branch --show-current              # main değilse DUR
docker compose ps backend              # ayakta değilse: docker compose up -d
```

- Aynı ay için `bagimlilik/YYYY-MM` dalı ya da `docs/arsiv/bagimlilik-raporu-YYYY-MM.md` zaten varsa DUR
  (ay içinde ikinci koşu yok; kullanıcı elle isterse dala `-2` eki ver).
- Ana dizinde çalış — worktree'de `docker compose` YASAK (konteyner ana dizini mount eder, `test-kos` tuzağı).
- Durursan yine de §7 raporunu `SONUC: DURDU — sebep` ile yaz.

## 1. Envanter

Dev araçları prod imajına girmez → önce kur: `docker compose exec -T backend pip install -q -r requirements-dev.txt`

| Katman | Komut | Kaynak dosya |
| --- | --- | --- |
| Python | `docker compose exec -T backend pip list --outdated --format=json` | `backend/requirements.txt` (`==` pin) |
| Python açık | `docker compose exec -T backend python -m pip_audit --format=json` | `backend/audit-ignore.txt` |
| npm | `npm --prefix frontend outdated --json` (çıkış kodu 1 = güncellenecek var, hata değil) | `frontend/package.json` + lock |
| npm açık | `cd frontend && node scripts/check-npm-audit.mjs --dev` | `frontend/audit-ignore.txt` |
| İmaj | `backend/Dockerfile` (python), `frontend/Dockerfile` (node, nginx), `docker-compose.yml` (postgres) — güncel etiketleri Docker Hub'dan bak | — |

`pip list --outdated` dev araçlarını ve dolaylı bağımlılıkları da listeler: yalnız `requirements.txt`'teki
doğrudan pinler aday olur; dolaylı paketler ancak güvenlik açığı varsa konuşulur.

## 2. Sürüm notu + kod etkisi (yargı adımı)

Her aday için:
1. Mevcut → hedef arası sürüm notlarını oku (PyPI "Release history"/GitHub releases/CHANGELOG — WebFetch).
   Aradaki TÜM sürümleri tara, yalnız sonuncuyu değil.
2. "Breaking", "removed", "deprecated", davranış değişikliği maddelerini çıkar.
3. Etkilenen API'yi kodda Grep'le ara (`backend/`, `frontend/src/`). Kullanım varsa dosya:satır yaz.
4. Hedef sürümün diğer paketlerle uyumunu kontrol et (ör. `pydantic` ↔ `fastapi`/`pydantic-settings`,
   `vite` ↔ `@vitejs/plugin-react-swc`/`vitest`, `@types/react` ↔ `react`, `typescript` ↔ `typescript-eslint`).
   Birlikte gitmesi gerekenler TEK birim olarak sınıflanır.

## 3. Sınıflandırma — kurallar SABİT

| Sınıf | Ne | İşlem |
| --- | --- | --- |
| **GÜVENLİ** | Aynı major içinde yama/minor; notlarda kırılma yok ya da kırılan API kodda kullanılmıyor | §4'te uygula |
| **AYRI GÖREV** | Her major atlama (npm'de `0.x` minor'ı da major sayılır); ya da minor ama kodu etkileyen kırılma | UYGULAMA; raporda görev taslağı (kapsam, etkilenen dosyalar, risk) — `gorevler/`'e YAZMA, kullanıcı `/plan-hazirla` ile açar |
| **İNSAN KARARI** | Postgres major (dump/restore ister), Python/Node imaj major, `google-genai` major, `msal`/`@azure/msal-*` major (kimlik), `Office365-REST-Python-Client` major (arşiv) | UYGULAMA; raporda gerekçe + önerilen yol |
| **GEÇİLMEZ** | `apscheduler` 4.x (API baştan değişti; 3.x yamaları GÜVENLİ sayılır) | Raporda tek satır |

- Güvenlik açığı olan paket sınıfından bağımsız rapor başına çıkar; açığı kapatan sürüm GÜVENLİ ise önce o uygulanır.
- Şüphedeysen bir üst sınıfa koy. Az ama yeşil güncelleme, çok ama riskli güncellemeden iyidir.
- İmaj etiketleri (`python:3.12-slim`, `node:24`, `nginx:alpine`, `postgres:15-alpine`) kayan etikettir; yama
  zaten rebuild'de gelir — yalnız major önerisi raporlanır, Dockerfile'a dokunulmaz.

## 4. Uygulama

```bash
git switch -c bagimlilik/YYYY-MM
```

- **Python:** `backend/requirements.txt` pinlerini Edit tool ile değiştir (shell ile dosya yazma YOK — PS5.1 UTF-8
  tuzağı). Sonra imajı yeniden kur; OneDrive cache tuzağına karşı pip adımının gerçekten koştuğunu gör:
  ```bash
  docker compose build --progress=plain backend
  docker compose up -d backend
  docker compose exec -T backend pip install -q -r requirements-dev.txt
  docker compose exec -T backend pip show <paket>     # her güncellenen paket için sürümü doğrula
  ```
  Backend yalnız recreate edilince nginx bayat upstream'le 502 verebilir; gerekirse `docker compose up -d` (tüm stack).
- **npm:** `package.json` aralığı hedefi zaten kapsıyorsa `npm --prefix frontend update <paket...>` (yalnız lock
  değişir); kapsamıyorsa `package.json`'ı Edit ile güncelle + `npm --prefix frontend install`. `npm audit fix --force` YASAK.

## 5. Kapılar — hepsi yeşil olmalı

`ci-kontrol` §1.1 + §1.2'nin AYNISI (bayraklar oradan; ekstra `-q` EKLEME):

- Backend (konteyner): pip-audit · `ruff check . --extend-exclude calibration-data` · `mypy` ·
  `pytest --cov=. --cov-report=term-missing:skip-covered --cov-fail-under=58`
- Frontend (`frontend/` içinde): `check-npm-audit.mjs` · `--dev` · `npm run lint` · `npx tsc -b --force` ·
  `npm test` · `npm run build`

Test sayısı main'deki tabanın altına düşerse kırmızıdır (CLAUDE.md "Komutlar" satırındaki son sayı).

**Kırmızıysa — ikiye böl:** güncellenen birimleri iki yarıya ayır, bir yarıyı geri al, kapıları koş; suçlu
birim kalana dek tekrarla. Suçluyu geri al → AYRI GÖREV sınıfına taşı (hata çıktısının ilk anlamlı satırlarıyla).
Kalan set yeşil olana dek devam. Hiçbir birim yeşil geçmezse commit YOK, §7 `DEGISIKLIK YOK`.

## 6. Commit

Yeşilse TEK commit, dosya listesiyle (`git add -A` YOK):

```bash
git add backend/requirements.txt frontend/package.json frontend/package-lock.json docs/arsiv/bagimlilik-raporu-YYYY-MM.md
git commit -m 'chore(deps): aylik bagimlilik guncellemesi YYYY-MM - N paket (rapor docs/arsiv/...)'
```

(PS5.1'de commit mesajı tek tırnakla — çift tırnak argümanı böler.) Sonra main'e dön ve lokal stack'i main'in
paketlerine geri çek — yoksa kullanıcının lokal ortamı dalın paketleriyle kalır:

```bash
git switch main
docker compose build backend && docker compose up -d
npm --prefix frontend ci
```

## 7. Rapor — `docs/arsiv/bagimlilik-raporu-YYYY-MM.md`

Değişiklik olmasa da DURDU olsa da yazılır (commit yoksa main'de izlenmeyen dosya olarak kalır). İçerik:

1. Özet: tarih, main SHA, dal, SONUC satırı, kapı sayıları (pytest "N passed", vitest "N passed", build).
2. **Güvenlik açıkları** (varsa, en üstte): paket · CVE/GHSA · kapatan sürüm · durum.
3. **Uygulananlar** tablosu: paket · eski · yeni · sürüm notu linki · kod etkisi (yok / dosya:satır).
4. **Bölmede elenenler:** paket · hata özeti.
5. **Ayrı görev önerileri:** her major için kapsam, etkilenen dosyalar, tahmini risk, önerilen sıra.
6. **İnsan kararı bekleyenler** + **Geçilmez** satırı.
7. Kullanıcıya sonraki adım: dalı incele → `/ci-kontrol` → push → CI yeşil → deploy kararı.

## 8. Son satır

Çıktının SON satırı tam olarak biri:

- `SONUC: GUNCELLENDI N paket — dal bagimlilik/YYYY-MM`
- `SONUC: DEGISIKLIK YOK`
- `SONUC: DURDU — sebep`
