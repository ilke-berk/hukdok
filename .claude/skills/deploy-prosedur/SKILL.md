---
name: deploy-prosedur
description: Prod deploy prosedürü — ön kontroller, nohup+ayrı-ssh-poll deseni, sağlık kapısı, deploy sonrası doğrulama, rollback yolu. Deploy'u KENDİLİĞİNDEN BAŞLATMAZ; yalnız kullanıcı açıkça isteyince uygulanır.
---

# Görev: prod deploy'u güvenli prosedürle yürüt

**Bu skill deploy başlatmaz.** Kullanıcı bu oturumda açıkça deploy istediyse prosedürü
uygula; istemediyse yalnız bilgilendir. Otomasyon/gece oturumları push/ssh/deploy YAPMAZ.

## 1. Ön kontroller

- **Pencere:** mesai dışı tercih edilir; aktif kullanım kontrolü (prod'da `docker logs`
  DAİMA `--since` ile — sınırsız log okuma geçmişte prod'u dondurdu):

```bash
ssh hukukoid "docker logs hukdok_backend --since 3m 2>&1 | grep -cE 'POST /(process|confirm)'"
```

  → `0` beklenir; değilse pencereyi bekle.
- **Kod:** deploy sunucuda `git pull --ff-only` yapar → main önce push'lanmış olmalı
  (push kararı kullanıcıda).
- **SSH:** birincil `ssh hukukoid` (docker sudo'suz + şifresiz sudo), yedek `ssh hukukoid-cc`.

## 2. Koşu — nohup + AYRI ssh ile poll (Deploy #3+#4 ile kanıtlı desen)

Uzun build'de tek ssh oturumuna bağlı kalma (kopma = yarım deploy belirsizliği):

```bash
ssh hukukoid "cd ~/hukdok && nohup ./deploy.sh > /tmp/deploy.log 2>&1 & echo basladi"
```

İlerlemeyi AYRI çağrılarla izle:

```bash
ssh hukukoid "tail -30 /tmp/deploy.log"
```

## 3. deploy.sh akışı ve güvenlik kapıları (kaynak: `deploy.sh:6-9` + gövde)

Önkoşullar (.env zorunlu anahtarları, `hukuk_shared` ağı) → `git pull --ff-only`
(başarısızsa DURUR) → pre-deploy `pg_dump -Fc` (alt sınır `MIN_DUMP_BYTES` = 1 MB;
~1.7 MB dump NORMALDİR) → build ESKİ stack çalışırken (kesinti yalnız up'taki değişim) →
imajlara git-SHA etiketi (`APP_VERSION` gömülür) → `up -d --remove-orphans` → `/healthz`
kapısı 120 sn + sürüm teyidi (`version` ≠ yeni SHA ⇒ bayat imaj uyarısı) → frontend
30 sn poll → `db-backup.timer` aktiflik kontrolü → etiket bakımı (son 3 SHA kalır).

## 4. Deploy sonrası doğrulama

- `ssh hukukoid "curl -fsS http://localhost:8001/healthz"` → `"version"` alanı yeni
  SHA olmalı (login rozeti de aynı SHA'yı gösterir).
- Script'in son satırındaki üçlüyü kullanıcıya raporla:
  `✅ Deploy tamam: <SHA> · rollback: ./rollback.sh <eski SHA> · DB dump: <yol>`.
- Şüphede: `ssh hukukoid "docker logs hukdok_backend --since 5m"` (yine `--since` ile).

## 5. Geri dönüş

- `ssh hukukoid "cd ~/hukdok && ./rollback.sh <eski SHA>"` — İMAJI döndürür, **DB'yi
  DÖNDÜRMEZ**; kötü migration'ın tek geri yolu pre-deploy dump'tır (`deploy.sh:70-71`).
- `.env` değişikliği `restart` ile GELMEZ — env yalnız konteyner create'te okunur →
  `docker compose up -d` (recreate) gerekir.
